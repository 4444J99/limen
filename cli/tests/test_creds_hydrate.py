"""Credential durability: a credential minted ONCE (into ~/.limen.env / 1Password) must reach the
agent subprocess env — so a SET key never reads as 'auth not configured' again, and a one-time login
is never repeated. Covers dispatch._load_limen_env() (the propagation fix) and the creds-hydrate
organ's --dry-run/--check (no `op`, no secret reads, no writes) and --verify (VALIDITY, not just
presence — the predicate that catches a dead token sitting behind a green --check)."""
import importlib.util
import io
import os
import subprocess
import sys
import urllib.error
from pathlib import Path

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
        capture_output=True, text=True, timeout=30,
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
    s = mod._scrub("Consumer 'api_key:AIzaSyCO8P_ooVY6dCYzNm7rPK15WdRrPYR63F0' suspended; ghp_abcd1234EFGH5678ijkl")
    assert "AIzaSy" not in s and "ghp_abcd1234" not in s and "api_key:AIza" not in s
    assert "<redacted>" in s


def test_env_value_reads_both_forms_and_strips_quotes(tmp_path):
    mod = _hydrate_module()
    f = tmp_path / ".limen.env"
    f.write_text('export GH_TOKEN=ghp_plain\nCLOUDFLARE_API_TOKEN="cf_quoted"\n')
    mod.ENV_FILE = f
    assert mod._env_value("GH_TOKEN") == "ghp_plain"          # export form
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
    assert "Invalid API Token" in mod._probe_reason(b'{"success":false,"errors":[{"code":1000,"message":"Invalid API Token"}]}')


def test_probe_cred_unverifiable_without_spec():
    mod = _hydrate_module()
    assert mod.probe_cred({"lane": "x"}, "tok")[0] == "unverifiable"


def test_probe_cred_classifies_valid_invalid_unverifiable(monkeypatch):
    mod = _hydrate_module()
    entry = {"verify": {"url": "https://svc.example/whoami", "auth": "bearer"}}

    class _OK:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda *a, **k: _OK())
    assert mod.probe_cred(entry, "tok") == ("valid", "HTTP 200")

    def _raise_401(*a, **k):
        raise urllib.error.HTTPError(entry["verify"]["url"], 401, "Unauthorized", {},
                                     io.BytesIO(b'{"message":"Bad credentials"}'))
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
    assert mod.derive_value(["gh", "auth", "token"]) == "keyring_tok"   # stripped
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
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "LIMEN_ENV": str(env_file)},
    )
    assert r.returncode == 0
    assert "not materialized" in r.stdout


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
    assert seen["input"] == "super-secret-value"            # value flows through stdin
    assert "super-secret-value" not in seen["cmd"]          # and NEVER through the argv
    assert seen["cmd"][:3] == ["gh", "secret", "set"]


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
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "LIMEN_ENV": str(env_file), "LIMEN_CREDS_MAP": str(map_file)},
    )
    assert r.returncode == 0
    assert "CI-secret gh:organvm/domus:GMAIL_APP_PASSWORD" in r.stdout
