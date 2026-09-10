"""Credential durability: a credential minted ONCE (into ~/.limen.env / 1Password) must reach the
agent subprocess env — so a SET key never reads as 'auth not configured' again, and a one-time login
is never repeated. Covers dispatch._load_limen_env() (the propagation fix) and the creds-hydrate
organ's --dry-run/--check (no `op`, no secret reads, no writes) and --verify (VALIDITY, not just
presence — the predicate that catches a dead token sitting behind a green --check)."""

import importlib.util
import io
import json
import os
import subprocess
import sys
import urllib.error
from pathlib import Path
from types import SimpleNamespace

import pytest

from limen.dispatch import _load_limen_env

HYDRATE = Path(__file__).resolve().parents[2] / "scripts" / "creds-hydrate.py"


def _hydrate_module(name="creds_hydrate_t"):
    spec = importlib.util.spec_from_file_location(name, HYDRATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_load_limen_env_fills_missing_keys(tmp_path, monkeypatch):
    env_file = tmp_path / ".limen.env"
    env_file.write_text('export GEMINI_API_KEY=abc123\nOPENAI_API_KEY="def456"\n# a comment\n\n')
    monkeypatch.setenv("LIMEN_ENV", str(env_file))
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    n = _load_limen_env()

    assert n == 2
    assert os.environ["GEMINI_API_KEY"] == "abc123"
    assert os.environ["OPENAI_API_KEY"] == "def456"  # quotes stripped, no `export` prefix needed


def test_load_limen_env_never_overwrites_explicit(tmp_path, monkeypatch):
    """An explicitly-exported var wins — the cache only fills what's MISSING (no clobber)."""
    env_file = tmp_path / ".limen.env"
    env_file.write_text("export GH_TOKEN=from_file\n")
    monkeypatch.setenv("LIMEN_ENV", str(env_file))
    monkeypatch.setenv("GH_TOKEN", "from_real_env")

    _load_limen_env()

    assert os.environ["GH_TOKEN"] == "from_real_env"


def test_load_limen_env_fail_open_when_absent(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ENV", str(tmp_path / "does-not-exist.env"))
    assert _load_limen_env() == 0  # no file → loads nothing, never raises


def test_hydrate_dry_run_reads_nothing_writes_nothing(tmp_path, monkeypatch):
    """--dry-run prints the op://→target plan without touching `op` or the env file."""
    env_file = tmp_path / ".limen.env"
    monkeypatch.setenv("LIMEN_ENV", str(env_file))
    r = subprocess.run(
        [sys.executable, str(HYDRATE), "--dry-run"],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "LIMEN_ENV": str(env_file)},
    )
    assert r.returncode == 0
    assert "plan:" in r.stdout or "op:" not in r.stdout  # plan lines, no secret material
    assert not env_file.exists()  # dry-run wrote nothing


def test_hydrate_map_override(tmp_path, monkeypatch):
    """The map is a named, tweakable param — an override file is honored over the built-in default."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("creds_hydrate", HYDRATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    map_file = tmp_path / "map.json"
    map_file.write_text('[{"lane":"x","ref":"op://V/I/credential","env":["X_KEY"]}]')
    monkeypatch.setenv("LIMEN_CREDS_MAP", str(map_file))
    loaded = mod.load_map()
    assert loaded == [{"lane": "x", "ref": "op://V/I/credential", "env": ["X_KEY"]}]


def test_hydrate_write_env_idempotent(tmp_path, monkeypatch):
    """write_env is add-or-replace: re-running yields exactly ONE line per key (no duplication)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("creds_hydrate2", HYDRATE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    env_file = tmp_path / ".limen.env"
    monkeypatch.setenv("LIMEN_ENV", str(env_file))
    mod.ENV_FILE = env_file  # the module bound ENV_FILE at import from the old env; point it at tmp

    mod.write_env("FOO", "v1")
    mod.write_env("FOO", "v2")
    lines = [ln for ln in env_file.read_text().splitlines() if ln.startswith("export FOO=")]
    assert lines == ["export FOO=v2"]
    assert oct(env_file.stat().st_mode)[-3:] == "600"


# --- VALIDITY PROBE (--verify): presence is not validity -------------------------------------------


def test_scrub_redacts_key_shapes():
    """A provider error must never carry a live key into our logs."""
    mod = _hydrate_module()
    # obviously-synthetic key SHAPES (matches _SECRET_RX so the scrubber must redact them) — never a real credential
    s = mod._scrub("Consumer 'api_key:AIzaSyFAKEFIXTURE0000000000000000000000' suspended; ghp_abcd1234EFGH5678ijkl")
    assert "AIzaSy" not in s and "ghp_abcd1234" not in s and "api_key:AIza" not in s
    assert "<redacted>" in s


def test_env_value_reads_both_forms_and_strips_quotes(tmp_path):
    mod = _hydrate_module()
    f = tmp_path / ".limen.env"
    f.write_text('export GH_TOKEN=ghp_plain\nCLOUDFLARE_API_TOKEN="cf_quoted"\n')
    mod.ENV_FILE = f
    assert mod._env_value("GH_TOKEN") == "ghp_plain"  # export form
    assert mod._env_value("CLOUDFLARE_API_TOKEN") == "cf_quoted"  # bare form, quotes stripped
    assert mod._env_value("ABSENT") is None


def test_probe_reason_extracts_clean_reason_per_provider():
    mod = _hydrate_module()
    # gemini — prefers the machine `reason`, never echoes the inline key
    gem = b'{"error":{"code":403,"status":"PERMISSION_DENIED","message":"Consumer api_key:AIzaSyXYZ suspended","details":[{"reason":"CONSUMER_SUSPENDED"}]}}'
    assert mod._probe_reason(gem) == "CONSUMER_SUSPENDED"
    # github
    assert mod._probe_reason(b'{"message":"Bad credentials"}') == "Bad credentials"
    # cloudflare
    assert "Invalid API Token" in mod._probe_reason(
        b'{"success":false,"errors":[{"code":1000,"message":"Invalid API Token"}]}'
    )


def test_probe_cred_unverifiable_without_spec():
    mod = _hydrate_module()
    assert mod.probe_cred({"lane": "x"}, "tok")[0] == "unverifiable"


def test_probe_cred_classifies_valid_invalid_unverifiable(monkeypatch):
    mod = _hydrate_module()
    entry = {"verify": {"url": "https://svc.example/whoami", "auth": "bearer"}}

    class _OK:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: _OK())
    assert mod.probe_cred(entry, "tok") == ("valid", "HTTP 200")

    def _raise_401(*a, **k):
        raise urllib.error.HTTPError(
            entry["verify"]["url"], 401, "Unauthorized", {}, io.BytesIO(b'{"message":"Bad credentials"}')
        )

    monkeypatch.setattr(mod.urllib.request, "urlopen", _raise_401)
    state, detail = mod.probe_cred(entry, "tok")
    assert state == "invalid" and "Bad credentials" in detail

    def _raise_neterr(*a, **k):
        raise urllib.error.URLError("name resolution failed")

    monkeypatch.setattr(mod.urllib.request, "urlopen", _raise_neterr)
    assert mod.probe_cred(entry, "tok")[0] == "unverifiable"  # offline never cries wolf


# --- DERIVE (live-minted source, e.g. gh keyring) --------------------------------------------------


def test_derive_value_runs_with_dead_floor_token_scrubbed(monkeypatch):
    """The gh keyring must be read with GH_TOKEN/GITHUB_TOKEN unset — else a dead floor token shadows it."""
    mod = _hydrate_module()
    monkeypatch.setenv("GH_TOKEN", "dead_pat")
    monkeypatch.setenv("GITHUB_TOKEN", "dead_pat")
    seen = {}

    class _R:
        returncode = 0
        stdout = "  keyring_tok\n"

    def _run(cmd, **kw):
        seen["cmd"] = cmd
        seen["env"] = kw.get("env", {})
        return _R()

    monkeypatch.setattr(mod.subprocess, "run", _run)
    assert mod.derive_value(["gh", "auth", "token"]) == "keyring_tok"  # stripped
    assert seen["cmd"] == ["gh", "auth", "token"]
    assert "GH_TOKEN" not in seen["env"] and "GITHUB_TOKEN" not in seen["env"]  # dead token can't shadow


def test_derive_value_failopen(monkeypatch):
    """Missing binary / nonzero exit / empty output → None, so the caller falls back to op://."""
    mod = _hydrate_module()

    def _missing(*a, **k):
        raise FileNotFoundError("gh")

    monkeypatch.setattr(mod.subprocess, "run", _missing)
    assert mod.derive_value(["gh", "auth", "token"]) is None

    class _Fail:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Fail())
    assert mod.derive_value(["gh", "auth", "token"]) is None


def test_verify_cli_no_creds_materialized_exits_zero(tmp_path):
    """--verify over an empty floor reports 'not materialized' and exits 0 — no network, no false alarm."""
    env_file = tmp_path / ".limen.env"  # does not exist
    r = subprocess.run(
        [sys.executable, str(HYDRATE), "--verify"],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "LIMEN_ENV": str(env_file)},
    )
    assert r.returncode == 0
    assert "not materialized" in r.stdout


def test_verify_required_missing_on_populated_floor_exits_one(tmp_path):
    """A `required` lane absent while the floor is OTHERWISE configured is a LOUD defect (exit 1) —
    the silent-skip failure mode that let GMAIL_APP_PASSWORD rot green (op:// read fails, --apply
    fail-open skips, --verify used to shrug '?'). Distinct from an EMPTY floor (fresh/CI), which
    stays quiet at exit 0 (test above): this is the configured-but-broken case that must scream."""
    env_file = tmp_path / ".limen.env"
    env_file.write_text("CONFIGURED_KEY=present\n")  # floor populated — but NOT with the required key
    map_file = tmp_path / "map.json"
    map_file.write_text(
        '[{"lane":"other","env":["CONFIGURED_KEY"]},'
        '{"lane":"gmail req","ref":"op://V/I/password","env":["REQ_KEY"],"required":true}]'
    )
    r = subprocess.run(
        [sys.executable, str(HYDRATE), "--verify"],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "LIMEN_ENV": str(env_file), "LIMEN_CREDS_MAP": str(map_file)},
    )
    assert r.returncode == 1
    assert "REQUIRED, NOT materialized" in r.stdout


# --- OP IS OPT-IN: the root-to-leaf fix for the 1Password Touch-ID prompt storm -------------------
def test_op_read_is_opt_in_no_prompt_by_default(tmp_path, monkeypatch):
    """`op read` is OPT-IN. A default --apply (non-TTY, no --op, no service-account token) must NEVER
    invoke op_read — the bare-TTY auto-trigger it replaces was the Touch-ID prompt storm (every daemon
    beat AND every interactive session presents as a TTY). Only an explicit --op may reach 1Password."""
    mod = _hydrate_module("creds_hydrate_optin")
    env_file = tmp_path / ".limen.env"
    mod.ENV_FILE = env_file
    map_file = tmp_path / "map.json"
    # a single op://-only lane (no `derive`) so op_read is the ONLY way it could hydrate
    map_file.write_text('[{"lane":"x","ref":"op://V/I/credential","env":["X_KEY"]}]')
    monkeypatch.setenv("LIMEN_CREDS_MAP", str(map_file))
    for v in ("OP_SERVICE_ACCOUNT_TOKEN", "OP_CONNECT_HOST", "OP_CONNECT_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(mod, "have_op", lambda: True)
    monkeypatch.setattr(mod, "SA_TOKEN_FILE", tmp_path / "absent-token")  # no silent-auth token

    calls = []
    monkeypatch.setattr(mod, "op_read", lambda ref, timeout=15: (calls.append(ref), "SECRET")[1])

    # default --apply: op must NOT be touched — no prompt path at all
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", "--apply"])
    assert mod.main() == 0
    assert calls == [], "op_read fired without --op — the prompt-storm regression is back"
    assert (not env_file.exists()) or ("X_KEY" not in env_file.read_text())

    # explicit --op: op IS read (the deliberate, human-initiated path)
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", "--apply", "--op"])
    assert mod.main() == 0
    assert calls == ["op://V/I/credential"], "op_read must run when --op is passed"
    assert "export X_KEY=SECRET" in env_file.read_text()


# --- gh_secret CI-SECRET sink: credentials land as GitHub Actions secrets, owned by the organ --------


def test_gh_secret_present_parses_names_only(monkeypatch):
    """gh_secret_present reads `gh secret list` (NAME<TAB>UPDATED rows) and matches the name — never a value."""
    mod = _hydrate_module()
    monkeypatch.setattr(mod, "have_gh", lambda: True)

    class _R:
        returncode = 0
        stdout = "GMAIL_APP_PASSWORD\t2026-06-25T21:27:18Z\nIMAP_USER\t2026-06-22T20:44:00Z\n"

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _R())
    assert mod.gh_secret_present("organvm/domus", "GMAIL_APP_PASSWORD") is True
    assert mod.gh_secret_present("organvm/domus", "NOT_THERE") is False


def test_gh_secret_present_fail_open_without_gh(monkeypatch):
    """No gh binary → None ('unknown'), never a crash and never a false 'absent'."""
    mod = _hydrate_module()
    monkeypatch.setattr(mod, "have_gh", lambda: False)
    assert mod.gh_secret_present("o/r", "X") is None


def test_gh_secret_set_pipes_value_via_stdin_not_argv(monkeypatch):
    """The secret VALUE is piped via stdin (input=), never placed in argv where `ps` could read it."""
    mod = _hydrate_module()
    monkeypatch.setattr(mod, "have_gh", lambda: True)
    seen = {}

    class _R:
        returncode = 0

    def _fake_run(cmd, *a, **k):
        seen["cmd"] = cmd
        seen["input"] = k.get("input")
        return _R()

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    ok = mod.gh_secret_set("organvm/domus", "GMAIL_APP_PASSWORD", "super-secret-value")
    assert ok is True
    assert seen["input"] == "super-secret-value"  # value flows through stdin
    assert "super-secret-value" not in seen["cmd"]  # and NEVER through the argv
    assert seen["cmd"][:3] == ["gh", "secret", "set"]


def test_sweep_all_refuses_without_promptless_op(tmp_path, monkeypatch):
    """--sweep-all NEVER touches `op` unless it can read silently — else it would pop a Touch-ID storm.
    With no service-account token it must refuse, call `op` zero times, and exit 0 (fail-open)."""
    mod = _hydrate_module("creds_hydrate_sweep_refuse")
    env_file = tmp_path / ".limen.env"
    mod.ENV_FILE = env_file
    monkeypatch.setattr(mod, "have_op", lambda: True)
    monkeypatch.setattr(mod, "op_can_read_silently", lambda: False)
    called = {"op": 0}
    monkeypatch.setattr(mod, "_op_json", lambda *a, **k: called.__setitem__("op", called["op"] + 1))
    rc = mod.sweep_all(apply=True)
    assert rc == 0
    assert called["op"] == 0  # refused before any op call
    assert not env_file.exists()  # wrote nothing


def test_sweep_all_materializes_uncurated_and_skips_logins(tmp_path, monkeypatch):
    """The catch-all sweep writes every credential field EXCEPT: curated-map items, LOGIN items (personal
    web logins), and names the curated map already owns. Values reach the env file, never the log."""
    mod = _hydrate_module("creds_hydrate_sweep")
    env_file = tmp_path / ".limen.env"
    mod.ENV_FILE = env_file
    monkeypatch.setenv("LIMEN_CREDS_SWEEP_VAULTS", "TestVault")
    monkeypatch.delenv("LIMEN_CREDS_SWEEP_LOGINS", raising=False)
    monkeypatch.setattr(mod, "have_op", lambda: True)
    monkeypatch.setattr(mod, "op_can_read_silently", lambda: True)

    listing = [
        {"id": "1", "title": "Stripe Live Key", "category": "API_CREDENTIAL"},
        {"id": "2", "title": "Personal Bank", "category": "LOGIN"},  # skipped (login)
        {"id": "3", "title": "DB Prod", "category": "DATABASE"},
        {"id": "4", "title": "Random Note", "category": "SECURE_NOTE"},  # no cred field → nothing
    ]
    items = {
        "1": {"fields": [{"label": "credential", "type": "CONCEALED", "value": "sk_live_ABC"}]},
        "3": {"fields": [{"label": "password", "purpose": "PASSWORD", "type": "CONCEALED", "value": "dbpw123"}]},
        "4": {"fields": [{"label": "notesPlain", "type": "STRING", "value": "just a note"}]},
    }

    def fake_op_json(cmd, *a, **k):
        if cmd[:2] == ["item", "list"]:
            return listing
        if cmd[:2] == ["item", "get"]:
            return items.get(cmd[2])
        return None

    monkeypatch.setattr(mod, "_op_json", fake_op_json)
    rc = mod.sweep_all(apply=True)
    assert rc == 0

    written = env_file.read_text()
    assert "export STRIPE_LIVE_KEY=sk_live_ABC" in written  # API credential swept
    assert "export DB_PROD=dbpw123" in written  # database password swept
    assert "PERSONAL_BANK" not in written  # LOGIN item skipped
    assert "RANDOM_NOTE" not in written  # no credential-shaped field → skipped


def test_gh_secret_only_entry_verify_is_neutral_and_offline(tmp_path):
    """A gh_secret-only map entry is reported neutrally by --verify with NO network call and exit 0."""
    map_file = tmp_path / "map.json"
    map_file.write_text(
        '[{"lane":"mail (ci)","ref":"op://V/I/password",'
        '"gh_secret":{"repo":"organvm/domus","name":"GMAIL_APP_PASSWORD"}}]'
    )
    env_file = tmp_path / ".limen.env"
    r = subprocess.run(
        [sys.executable, str(HYDRATE), "--verify"],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "LIMEN_ENV": str(env_file), "LIMEN_CREDS_MAP": str(map_file)},
    )
    assert r.returncode == 0
    assert "CI-secret gh:organvm/domus:GMAIL_APP_PASSWORD" in r.stdout


def test_gh_sinks_normalizes_dict_list_and_none():
    """_gh_sinks accepts a single dict (legacy), a LIST of sinks (new multi-repo fan-out), or nothing —
    always returning a list, so every consumption site iterates uniformly and old single-sink entries
    behave identically (one-element list)."""
    mod = _hydrate_module()
    assert mod._gh_sinks({}) == []
    assert mod._gh_sinks({"gh_secret": None}) == []
    one = {"repo": "o/r", "name": "X"}
    assert mod._gh_sinks({"gh_secret": one}) == [one]
    two = [{"repo": "o/a", "name": "K"}, {"repo": "o/b", "name": "K"}]
    assert mod._gh_sinks({"gh_secret": two}) == two


# --- ONE-PROMPT BATCH: all op:// lanes in a single `op inject` pass ---------------------------------


def test_op_read_batch_one_subprocess_and_multiline_values(monkeypatch):
    """op_read_batch renders EVERY ref through ONE `op inject` subprocess (one biometric prompt
    total) and the sentinel template survives multi-line values (the rclone.conf class) verbatim —
    the reason the template is sentinels, not JSON."""
    mod = _hydrate_module("creds_hydrate_batch")
    calls = []

    class _R:
        returncode = 0

        def __init__(self, stdout):
            self.stdout = stdout

    def _fake_run(cmd, **kw):
        calls.append(cmd)
        template = kw["input"]
        # substitute like `op inject` does: plain text, no escaping
        import re as _re

        def _sub(m):
            ref = m.group(1).strip()
            if ref.endswith("notesPlain"):
                return '[gdrive]\ntype = drive\ntoken = {"x":"y"}'
            return f"VAL::{ref}"

        return _R(_re.sub(r"\{\{\s*(op://[^}]+?)\s*\}\}", _sub, template))

    monkeypatch.setattr(mod.subprocess, "run", _fake_run)
    refs = ["op://Personal/Gemini API Key/credential", "op://Limen-Automation/rclone.conf/notesPlain"]
    out = mod.op_read_batch(refs)
    assert len(calls) == 1 and calls[0][:2] == ["op", "inject"]  # exactly ONE op process
    assert out["op://Personal/Gemini API Key/credential"] == "VAL::op://Personal/Gemini API Key/credential"
    assert out["op://Limen-Automation/rclone.conf/notesPlain"].splitlines()[0] == "[gdrive]"  # newlines survive
    assert "token = " in out["op://Limen-Automation/rclone.conf/notesPlain"]


def test_op_read_batch_fail_open(monkeypatch):
    """`op inject` is all-or-nothing: nonzero exit or a missing binary → None, so the caller falls
    back to sequential per-entry op_read and per-entry fail-open is preserved."""
    mod = _hydrate_module("creds_hydrate_batch_fail")

    class _Fail:
        returncode = 1
        stdout = ""

    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: _Fail())
    assert mod.op_read_batch(["op://V/I/credential", "op://V/J/credential"]) is None

    def _missing(*a, **k):
        raise FileNotFoundError("op")

    monkeypatch.setattr(mod.subprocess, "run", _missing)
    assert mod.op_read_batch(["op://V/I/credential", "op://V/J/credential"]) is None
    assert mod.op_read_batch([]) == {}  # empty input never touches a subprocess


def test_op_read_batch_real_shim_round_trip(tmp_path, monkeypatch):
    """End-to-end through a REAL subprocess: a fake `op` on PATH counts invocations and renders the
    template. Three refs → ONE invocation, every value parsed back by sentinel."""
    mod = _hydrate_module("creds_hydrate_batch_shim")
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir()
    count_file = tmp_path / "op-calls"
    shim = shim_dir / "op"
    shim.write_text(
        "#!/usr/bin/env python3\n"
        "import sys, re, pathlib\n"
        f"cf = pathlib.Path({str(count_file)!r})\n"
        "cf.open('a').write('x\\n')\n"
        "t = sys.stdin.read()\n"
        "sys.stdout.write(re.sub(r'\\{\\{\\s*(op://[^}]+?)\\s*\\}\\}', lambda m: 'S::' + m.group(1).strip(), t))\n"
    )
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim_dir}:{os.environ['PATH']}")
    refs = ["op://V/A/credential", "op://V/B/password", "op://V/C/credential"]
    out = mod.op_read_batch(refs)
    assert out == {r: f"S::{r}" for r in refs}
    assert count_file.read_text().count("x") == 1  # one op process for all three refs


def _batch_wiring_module(tmp_path, monkeypatch, name, map_json):
    """Common setup for main()-level batch wiring tests: module + tmp env file + map + no silent op."""
    mod = _hydrate_module(name)
    env_file = tmp_path / ".limen.env"
    mod.ENV_FILE = env_file
    map_file = tmp_path / "map.json"
    map_file.write_text(map_json)
    monkeypatch.setenv("LIMEN_CREDS_MAP", str(map_file))
    monkeypatch.delenv("LIMEN_CREDS_BATCH", raising=False)
    for v in ("OP_SERVICE_ACCOUNT_TOKEN", "OP_CONNECT_HOST", "OP_CONNECT_TOKEN"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(mod, "have_op", lambda: True)
    monkeypatch.setattr(mod, "SA_TOKEN_FILE", tmp_path / "absent-token")
    return mod, env_file


_THREE_OP_LANES = (
    '[{"lane":"a","ref":"op://V/A/credential","env":["A_KEY"]},'
    '{"lane":"b","ref":"op://V/B/credential","env":["B_KEY"]},'
    '{"lane":"c","ref":"op://V/C/credential","env":["C_KEY"]}]'
)


def test_apply_op_reads_all_lanes_in_one_batch(tmp_path, monkeypatch):
    """--apply --op with several op:// lanes goes through op_read_batch ONCE (all refs) and never
    touches per-entry op_read — the one-prompt contract."""
    mod, env_file = _batch_wiring_module(tmp_path, monkeypatch, "creds_hydrate_wire1", _THREE_OP_LANES)
    batches, reads = [], []
    monkeypatch.setattr(
        mod,
        "op_read_batch",
        lambda refs, timeout=120: (batches.append(list(refs)), {r: f"v-{i}" for i, r in enumerate(refs)})[1],
    )
    monkeypatch.setattr(mod, "op_read", lambda ref, timeout=15: (reads.append(ref), "SEQ")[1])
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", "--apply", "--op"])
    assert mod.main() == 0
    assert batches == [["op://V/A/credential", "op://V/B/credential", "op://V/C/credential"]]
    assert reads == [], "per-entry op_read fired despite a successful batch — that's a prompt per lane again"
    text = env_file.read_text()
    assert "export A_KEY=v-0" in text and "export B_KEY=v-1" in text and "export C_KEY=v-2" in text


def test_apply_batch_failure_falls_back_to_sequential(tmp_path, monkeypatch):
    """A failed batch (None) degrades to the old per-entry op_read reads — fail-open, never a lost lane."""
    mod, env_file = _batch_wiring_module(tmp_path, monkeypatch, "creds_hydrate_wire2", _THREE_OP_LANES)
    reads = []
    monkeypatch.setattr(mod, "op_read_batch", lambda refs, timeout=120: None)
    monkeypatch.setattr(mod, "op_read", lambda ref, timeout=15: (reads.append(ref), "SEQ")[1])
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", "--apply", "--op"])
    assert mod.main() == 0
    assert reads == ["op://V/A/credential", "op://V/B/credential", "op://V/C/credential"]
    assert "export A_KEY=SEQ" in env_file.read_text()


def test_apply_batch_disabled_by_env(tmp_path, monkeypatch):
    """LIMEN_CREDS_BATCH=0 is the escape hatch: no batch call at all, sequential reads as before."""
    mod, _env_file = _batch_wiring_module(tmp_path, monkeypatch, "creds_hydrate_wire3", _THREE_OP_LANES)
    monkeypatch.setenv("LIMEN_CREDS_BATCH", "0")
    batches, reads = [], []
    monkeypatch.setattr(mod, "op_read_batch", lambda refs, timeout=120: (batches.append(list(refs)), {})[1])
    monkeypatch.setattr(mod, "op_read", lambda ref, timeout=15: (reads.append(ref), "SEQ")[1])
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", "--apply", "--op"])
    assert mod.main() == 0
    assert batches == []
    assert len(reads) == 3


def test_apply_batch_excludes_derive_lanes(tmp_path, monkeypatch):
    """Derive-first lanes never enter the batch — their op:// ref is a last-resort fallback, and
    pre-reading it would touch 1Password for a value the keyring already mints."""
    map_json = (
        '[{"lane":"gh","ref":"op://V/GH/password","env":["T_GH"],"derive":["gh","auth","token"]},'
        '{"lane":"a","ref":"op://V/A/credential","env":["A_KEY"]},'
        '{"lane":"b","ref":"op://V/B/credential","env":["B_KEY"]}]'
    )
    mod, env_file = _batch_wiring_module(tmp_path, monkeypatch, "creds_hydrate_wire4", map_json)
    batches = []
    monkeypatch.setattr(mod, "derive_value", lambda cmd, timeout=15: "keyring_tok")
    monkeypatch.setattr(
        mod, "op_read_batch", lambda refs, timeout=120: (batches.append(list(refs)), {r: "V" for r in refs})[1]
    )
    monkeypatch.setattr(mod, "op_read", lambda ref, timeout=15: "SEQ")
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", "--apply", "--op"])
    assert mod.main() == 0
    assert batches == [["op://V/A/credential", "op://V/B/credential"]]  # derive lane's ref NOT pre-read
    assert "export T_GH=keyring_tok" in env_file.read_text()


def test_gh_secret_list_fans_out_to_every_repo_in_verify(tmp_path):
    """A gh_secret LIST (one op:// value → many repos' CI secrets, e.g. the shared GCP deploy SA) is
    reported as ALL its sinks by --verify, network-free, exit 0 — the multi-repo fan-out the media-ark
    Cloud Run deploy relies on."""
    map_file = tmp_path / "map.json"
    map_file.write_text(
        '[{"lane":"gcp (ci)","ref":"op://V/I/credential","gh_secret":['
        '{"repo":"organvm/media-ark","name":"GCP_SA_KEY"},'
        '{"repo":"organvm/limen","name":"GCP_SA_KEY"}]}]'
    )
    env_file = tmp_path / ".limen.env"
    r = subprocess.run(
        [sys.executable, str(HYDRATE), "--verify"],
        capture_output=True,
        text=True,
        timeout=30,
        env={**os.environ, "LIMEN_ENV": str(env_file), "LIMEN_CREDS_MAP": str(map_file)},
    )
    assert r.returncode == 0
    assert "gh:organvm/media-ark:GCP_SA_KEY" in r.stdout
    assert "gh:organvm/limen:GCP_SA_KEY" in r.stdout


_UCC_SINK = "gh:organvm-iii-ergon/public-record-data-scrapper:CLOUDFLARE_API_TOKEN"
_UCC_ACCOUNT = "e0921b840fd656d8ea46426f1f114c30"


def _refresh_fixture(tmp_path, monkeypatch):
    mod = _hydrate_module("creds_refresh")
    ucc = next(e for e in mod.DEFAULT_MAP if e["lane"] == "cloudflare (public-record-data-scrapper CI secret)")
    # Exercise exact-destination selection even if this becomes a shared entry later.
    entry = {
        **ucc,
        "env": ["UNRELATED_CACHE"],
        "file": {"path": str(tmp_path / "unrelated-auth"), "template": "{value}"},
        "gh_secret": [ucc["gh_secret"], {"repo": "other/repo", "name": "OTHER_TOKEN"}],
    }
    mod, env_file = _batch_wiring_module(tmp_path, monkeypatch, "creds_refresh_wired", json.dumps([entry]))
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", "--apply", "--op", "--refresh-ci-secret", _UCC_SINK])
    return mod, env_file, ucc


def test_refresh_existing_secret_selects_only_requested_destination(tmp_path, monkeypatch, capsys):
    mod, env_file, ucc = _refresh_fixture(tmp_path, monkeypatch)
    reads, writes = [], []
    monkeypatch.setattr(mod, "op_read", lambda ref: (reads.append(ref), "synthetic-private-value")[1])
    monkeypatch.setattr(mod, "verify_cloudflare_delivery", lambda entry, value: (True, "confirmed"))
    monkeypatch.setattr(mod, "gh_sink_present", lambda sink: pytest.fail("refresh must not presence-skip"))
    monkeypatch.setattr(mod, "gh_sink_set", lambda sink, value: (writes.append((sink, value)), True)[1])
    assert mod.main() == 0
    assert reads == [ucc["ref"]]
    assert writes == [(ucc["gh_secret"], "synthetic-private-value")]
    assert not env_file.exists()
    assert not (tmp_path / "unrelated-auth").exists()
    assert "synthetic-private-value" not in capsys.readouterr().out


@pytest.mark.parametrize("failure", ["no_op", "unreadable", "write", "scope"])
def test_refresh_failure_is_nonzero_and_scope_failure_never_writes(tmp_path, monkeypatch, failure):
    mod, env_file, _ucc = _refresh_fixture(tmp_path, monkeypatch)
    writes = []
    monkeypatch.setattr(mod, "have_op", lambda: failure != "no_op")
    monkeypatch.setattr(mod, "op_read", lambda ref: None if failure == "unreadable" else "synthetic-token")
    monkeypatch.setattr(mod, "verify_cloudflare_delivery", lambda entry, value: (failure != "scope", "D1 rejected"))
    monkeypatch.setattr(mod, "gh_sink_set", lambda sink, value: (writes.append(sink), False)[1])
    assert mod.main() == 1
    assert bool(writes) is (failure == "write")
    assert not env_file.exists()


def test_refresh_plan_needs_no_op_and_does_not_read_auth(tmp_path, monkeypatch):
    mod, env_file, _ucc = _refresh_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", "--dry-run", "--refresh-ci-secret", _UCC_SINK])
    monkeypatch.setattr(mod, "have_op", lambda: False)
    for method in (
        "load_service_account_token",
        "op_read",
        "gh_sink_present",
        "gh_sink_set",
        "verify_cloudflare_delivery",
    ):
        monkeypatch.setattr(mod, method, lambda *a, **k: pytest.fail("plan touched credentials or network"))
    assert mod.main() == 0
    assert not env_file.exists()


@pytest.mark.parametrize(
    "args",
    [
        ["--apply", "--refresh-ci-secret", "gh:unknown/repo:TOKEN"],
        ["--apply", "--refresh-ci-secret", ""],
        ["--sweep-all", "--refresh-ci-secret", ""],
        ["--sweep-all", "--refresh-ci-secret", _UCC_SINK],
        ["--verify", "--refresh-ci-secret", _UCC_SINK],
    ],
)
def test_refresh_rejects_unknown_or_broad_operations_before_auth(tmp_path, monkeypatch, args):
    mod, _env_file, _ucc = _refresh_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(sys, "argv", ["creds-hydrate", *args])
    monkeypatch.setattr(mod, "load_service_account_token", lambda: pytest.fail("invalid target read auth"))
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "failure", [None, "wrong_account", "d1_denied", "redirect", "malformed", "oversized", "header", "body_error"]
)
def test_cloudflare_delivery_preflight_is_bounded_exact_and_secret_safe(monkeypatch, capsys, failure):
    mod = _hydrate_module("creds_delivery_probe")
    token = "synthetic-private-value"
    requests = []

    class Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, limit):
            assert limit == 65537
            if failure == "body_error":
                raise OSError(token)
            if failure == "oversized":
                return b"x" * limit
            if failure == "malformed":
                return b"not-json"
            result = [] if len(requests) == 2 else {"id": "other" if failure == "wrong_account" else _UCC_ACCOUNT}
            return json.dumps({"success": True, "result": result}).encode()

    class Opener:
        def open(self, request, timeout):
            assert timeout == 15
            assert request.get_method() == "GET"
            assert request.get_header("Authorization") == f"Bearer {token}"
            requests.append(request.full_url)
            if failure == "header":
                raise ValueError(token)
            if failure == "redirect" or (failure == "d1_denied" and len(requests) == 2):
                raise urllib.error.HTTPError(request.full_url, 302 if failure == "redirect" else 401, token, {}, None)
            return Response()

    def build_opener(handler):
        assert handler.redirect_request(None, None, 302, "", {}, "https://untrusted.example") is None
        return Opener()

    monkeypatch.setattr(mod.urllib.request, "build_opener", build_opener)
    ok, detail = mod.verify_cloudflare_delivery({"cloudflare_delivery_account": _UCC_ACCOUNT}, token)
    assert ok is (failure is None)
    assert token not in detail + capsys.readouterr().out
    expected = f"https://api.cloudflare.com/client/v4/accounts/{_UCC_ACCOUNT}"
    assert requests[0] == expected
    if len(requests) == 2:
        assert requests[1] == expected + "/d1/database?per_page=1"


@pytest.mark.parametrize(
    "mode,failure",
    [
        ("preflight", None),
        ("apply", None),
        ("apply", "candidate"),
        ("apply", "app"),
        ("apply", "mint"),
        ("apply", "grant"),
        ("apply", "stale"),
        ("apply", "source_query"),
        ("apply", "write"),
        ("apply", "transport"),
    ],
)
def test_hosted_delivery_uses_exact_app_principal_and_never_exposes_tokens(monkeypatch, capsys, mode, failure):
    path = HYDRATE.parent / "ucc-cloudflare-delivery.py"
    spec = importlib.util.spec_from_file_location("ucc_delivery", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source_token, app_token = "synthetic-source-private", "synthetic-app-private"
    sink_transport = _hydrate_module("clavis_existing_sink")
    monkeypatch.setattr(sink_transport, "have_gh", lambda: True)
    entry = {"gh_secret": {"repo": module.TARGET, "name": module.SECRET_NAME}}
    fake_hydrate = SimpleNamespace(
        DEFAULT_MAP=[entry],
        verify_cloudflare_delivery=lambda entry, value: (failure != "candidate", "bounded result"),
        gh_secret_set=sink_transport.gh_secret_set,
    )
    monkeypatch.setattr(
        module.importlib.util,
        "spec_from_file_location",
        lambda *args: SimpleNamespace(loader=SimpleNamespace(exec_module=lambda mod: None)),
    )
    monkeypatch.setattr(module.importlib.util, "module_from_spec", lambda *args: fake_hydrate)
    monkeypatch.setattr(sys, "argv", ["ucc-delivery", "--mode", mode])
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", source_token)
    monkeypatch.setenv("GITHUB_APP_ID", "fixture-app")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "" if failure == "app" else "fixture-key")
    monkeypatch.setenv("GITHUB_TOKEN", "unrelated-workflow-token")
    monkeypatch.setenv("EXPECTED_SHA", "a" * 40)
    monkeypatch.setenv("SOURCE_GITHUB_TOKEN", "source-read-token")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        assert source_token not in command and app_token not in command
        assert kwargs["capture_output"] is True
        if command[0] == "bash":
            assert command[-4:] == ["--repo", module.TARGET, "--app-only", "--require-secrets-write"]
            assert kwargs["timeout"] == 60
            return SimpleNamespace(
                returncode=1 if failure in ("mint", "grant") else 0,
                stdout=app_token,
                stderr="exact-repository App token lacks the required Secrets-write grant"
                if failure == "grant"
                else "",
            )
        if command[1] == "api":
            assert command == ["gh", "api", "repos/4444J99/limen/git/ref/heads/main", "--jq", ".object.sha"]
            assert kwargs["env"]["GH_TOKEN"] == "source-read-token"
            assert "GITHUB_APP_PRIVATE_KEY" not in kwargs["env"]
            assert "CLOUDFLARE_API_TOKEN" not in kwargs["env"]
            assert kwargs["timeout"] == 15
            return SimpleNamespace(
                returncode=1 if failure == "source_query" else 0, stdout="b" * 40 if failure == "stale" else "a" * 40
            )
        assert command == ["gh", "secret", "set", "CLOUDFLARE_API_TOKEN", "-R", module.TARGET]
        assert kwargs["input"] == source_token
        assert kwargs["env"]["GH_TOKEN"] == app_token
        assert "GITHUB_TOKEN" not in kwargs["env"]
        assert kwargs["timeout"] == 30
        if failure == "transport":
            raise OSError(source_token)
        return SimpleNamespace(returncode=1 if failure == "write" else 0)

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main() == (1 if failure else 0)
    if mode == "preflight" or failure in ("candidate", "app"):
        assert calls == []
    if failure in ("stale", "source_query"):
        assert not any(command[:3] == ["gh", "secret", "set"] for command in calls)
    output = capsys.readouterr().out
    assert source_token not in output and app_token not in output
