"""Stop governor: every decision path, the real wrapper's fail-open contract, the real git probes,
concurrency, privacy of the event log, and the predicate's own discrimination.

Stdlib only (the hook runs on an interpreter that may lack PyYAML). The behavioral matrix is shared with
scripts/check-stop-governor.py through scripts/tests/fixtures/stop-governor-cases.json.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GOVERNOR = ROOT / "scripts" / "stop-governor.py"
WRAPPER = ROOT / "scripts" / "hooks" / "stop-governor.sh"
RUNNER = ROOT / "scripts" / "hooks" / "codex-hook-runner.sh"
PREDICATE = ROOT / "scripts" / "check-stop-governor.py"
REGISTRY = ROOT / "institutio" / "governance" / "post-opener-intents.json"
FIXTURES = ROOT / "scripts" / "tests" / "fixtures" / "stop-governor-cases.json"
CONT = "I fixed the first two. Want me to also fix the other two?"


def _load():
    spec = importlib.util.spec_from_file_location("stop_governor_under_test", GOVERNOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules["stop_governor_under_test"] = module
    spec.loader.exec_module(module)
    return module


sg = _load()
CASES = json.loads(FIXTURES.read_text(encoding="utf-8"))
REGISTRY_DATA = json.loads(REGISTRY.read_text(encoding="utf-8"))


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    env.update(extra)
    return env


def _git(cwd: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env=_env(cwd),
    )
    return out.stdout


def _payload(message: str, **overrides) -> dict:
    payload = {
        "hook_event_name": "Stop",
        "session_id": "s-1",
        "cwd": "/nowhere",
        "permission_mode": "default",
        "stop_hook_active": False,
        "last_assistant_message": message,
    }
    payload.update(overrides)
    return payload


def _registry_file(tmp_path: Path, *live: str, name: str = "registry.json") -> Path:
    reg = copy.deepcopy(REGISTRY_DATA)
    for rule in reg["rules"].values():
        rule["mode"] = "shadow"
    for rule in live:
        reg["rules"][rule]["mode"] = "live"
    path = tmp_path / name
    path.write_text(json.dumps(reg), encoding="utf-8")
    return path


def _limen_like_repo(tmp_path: Path) -> Path:
    """A real git repo carrying the scope marker, so the real probe (not a fake) puts it in scope."""
    repo = tmp_path / "repo"
    marker = repo / REGISTRY_DATA["scope_marker"]
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    return repo


def _run_wrapper(argv: list[str], stdin: bytes, tmp_path: Path, runner: Path = WRAPPER):
    return subprocess.run(
        ["bash", str(runner), *argv],
        input=stdin,
        capture_output=True,
        cwd=ROOT,
        env=_env(tmp_path),
        timeout=60,
        check=False,
    )


# --------------------------------------------------------------------------- the shared matrix


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_fixture_case(case, tmp_path):
    decision, output = sg.run_case(case, tmp_path)
    assert sg.case_failures(case, decision, output) == []


def test_fixture_ids_are_unique_and_cover_both_vendors():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    assert {c.get("vendor", "claude") for c in CASES} == {"claude", "codex"}


@pytest.mark.parametrize("pair", [("claude-clean-cont", "codex-clean-cont"), ("claude-close", "codex-close")])
def test_same_stop_is_byte_identical_across_vendors(pair, tmp_path):
    outputs = []
    for cid in pair:
        case = next(c for c in CASES if c["id"] == cid)
        outputs.append(sg.run_case(case, tmp_path / cid)[1])
    assert outputs[0] and outputs[0] == outputs[1]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_shadow_never_alters_output(case, tmp_path):
    quiet = dict(case)
    quiet["registry_patch"] = sg._deep_merge(
        case.get("registry_patch") or {}, {"rules": {r: {"mode": "shadow"} for r in REGISTRY_DATA["rules"]}}
    )
    _, output = sg.run_case(quiet, tmp_path)
    assert output == ""


def test_the_shipped_registry_promotes_nothing_without_evidence():
    for name, rule in REGISTRY_DATA["rules"].items():
        if rule["mode"] == "live":
            assert rule["promotion"], f"{name} is live without a promotion block"


def test_every_block_output_is_exactly_decision_and_reason(tmp_path):
    seen = 0
    for case in CASES:
        decision, output = sg.run_case(case, tmp_path / case["id"])
        if decision.action == "block":
            shape = json.loads(output)
            assert set(shape) == {"decision", "reason"} and shape["decision"] == "block"
            assert shape["reason"].startswith("[stop-governor:")
            assert len(shape["reason"]) <= 1200
            seen += 1
    assert seen >= 8


# --------------------------------------------------------------------------- the real wrapper


@pytest.mark.parametrize(
    "stdin",
    [b"", b"not json", b"[]", b'{"hook_event_name": "Stop"}', b"x" * (1 << 21)],
    ids=["empty", "garbage", "not-an-object", "no-fields", "oversize"],
)
def test_wrapper_fails_open_on_bad_input(stdin, tmp_path):
    reg = _registry_file(tmp_path, "CONT")
    proc = _run_wrapper(
        ["--vendor", "claude", "--event", "Stop", "--registry", str(reg), "--state-dir", str(tmp_path / "state")],
        stdin,
        tmp_path,
    )
    assert proc.returncode == 0 and proc.stdout == b""


def test_wrapper_fails_open_without_a_registry(tmp_path):
    proc = _run_wrapper(
        ["--vendor", "claude", "--event", "Stop", "--registry", str(tmp_path / "missing.json")],
        json.dumps(_payload(CONT)).encode(),
        tmp_path,
    )
    assert proc.returncode == 0 and proc.stdout == b""


def test_wrapper_fails_open_on_an_unwritable_ledger_and_on_other_events(tmp_path):
    repo = _limen_like_repo(tmp_path)
    reg = _registry_file(tmp_path, "CONT")
    blocker = tmp_path / "state-is-a-file"
    blocker.write_text("", encoding="utf-8")
    payload = json.dumps(_payload(CONT, cwd=str(repo))).encode()
    proc = _run_wrapper(
        ["--vendor", "claude", "--event", "Stop", "--registry", str(reg), "--state-dir", str(blocker)],
        payload,
        tmp_path,
    )
    assert proc.returncode == 0 and proc.stdout == b""
    proc = _run_wrapper(
        ["--vendor", "claude", "--event", "SessionStart", "--registry", str(reg), "--state-dir", str(tmp_path / "s")],
        payload,
        tmp_path,
    )
    assert proc.returncode == 0 and proc.stdout == b""


def test_live_rule_through_both_entry_points_prints_one_identical_object(tmp_path):
    repo = _limen_like_repo(tmp_path)
    reg = _registry_file(tmp_path, "CONT")
    payload = json.dumps(_payload(CONT, cwd=str(repo))).encode()
    claude = _run_wrapper(
        ["--vendor", "claude", "--event", "Stop", "--registry", str(reg), "--state-dir", str(tmp_path / "a")],
        payload,
        tmp_path,
    )
    codex = _run_wrapper(
        ["stop-governor", "--event", "Stop", "--registry", str(reg), "--state-dir", str(tmp_path / "b")],
        payload,
        tmp_path,
        runner=RUNNER,
    )
    assert claude.returncode == 0 and codex.returncode == 0
    shape = json.loads(claude.stdout)
    assert set(shape) == {"decision", "reason"} and shape["decision"] == "block"
    assert codex.stdout == claude.stdout


def test_out_of_scope_repo_is_silent_and_writes_nothing(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    _git(other, "init", "-q", "-b", "main")
    reg = _registry_file(tmp_path, "CONT")
    state = tmp_path / "state"
    proc = _run_wrapper(
        ["--vendor", "claude", "--event", "Stop", "--registry", str(reg), "--state-dir", str(state)],
        json.dumps(_payload(CONT, cwd=str(other))).encode(),
        tmp_path,
    )
    assert proc.returncode == 0 and proc.stdout == b""
    assert not (state / "events.jsonl").exists()


def test_two_processes_on_one_stop_produce_exactly_one_block(tmp_path):
    repo = _limen_like_repo(tmp_path)
    reg = _registry_file(tmp_path, "CONT")
    state = tmp_path / "state"
    payload = json.dumps(_payload(CONT, cwd=str(repo))).encode()
    argv = [
        "bash",
        str(WRAPPER),
        "--vendor",
        "claude",
        "--event",
        "Stop",
        "--registry",
        str(reg),
        "--state-dir",
        str(state),
    ]
    procs = [
        subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd=ROOT, env=_env(tmp_path)
        )
        for _ in range(4)
    ]
    outputs = []
    for proc in procs:
        out, _ = proc.communicate(payload, timeout=60)
        assert proc.returncode == 0
        outputs.append(out)
    assert sum(1 for out in outputs if out) == 1


def test_event_log_carries_metadata_only_never_message_text(tmp_path):
    repo = _limen_like_repo(tmp_path)
    reg = _registry_file(tmp_path)  # all shadow: the stop is logged as would_block
    state = tmp_path / "state"
    secret = "Want me to also fix the other two? (private-note-4f9a)"
    proc = _run_wrapper(
        ["--vendor", "claude", "--event", "Stop", "--registry", str(reg), "--state-dir", str(state)],
        json.dumps(_payload(secret, cwd=str(repo), session_id="private-session-id")).encode(),
        tmp_path,
    )
    assert proc.returncode == 0 and proc.stdout == b""
    raw = (state / "events.jsonl").read_text(encoding="utf-8")
    row = json.loads(raw.splitlines()[-1])
    assert row["action"] == "would_block" and "CONT" in row["shadow"]
    assert "private-note" not in raw and "private-session-id" not in raw and "Want me" not in raw
    assert len(row["sid"]) == 8


# --------------------------------------------------------------------------- the real git probes


def test_probe_git_reads_branch_dirty_and_ahead_in_a_real_repo(tmp_path):
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    repo = _limen_like_repo(tmp_path)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "main")
    _git(repo, "checkout", "-q", "-b", "feat/x")
    state = sg.probe_git(str(repo))
    assert state.branch == "feat/x" and not state.dirty and not state.has_upstream
    assert state.canonical == repo.resolve() and not state.work_present
    (repo / "new.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "new.txt")
    _git(repo, "commit", "-q", "-m", "work")
    state = sg.probe_git(str(repo))
    assert state.commits_vs_main == 1 and state.work_present and not state.clean_pushed
    _git(repo, "push", "-q", "-u", "origin", "feat/x")
    state = sg.probe_git(str(repo))
    assert state.has_upstream and state.ahead == 0 and state.clean_pushed and not state.work_present
    (repo / REGISTRY_DATA["scope_marker"]).write_text('{"edited": true}', encoding="utf-8")
    state = sg.probe_git(str(repo))
    assert state.dirty and state.work_present and not state.clean_pushed
    (repo / "untracked.txt").write_text("u", encoding="utf-8")
    _git(repo, "checkout", "-q", "--", REGISTRY_DATA["scope_marker"])
    assert not sg.probe_git(str(repo)).dirty  # untracked files are not unpublished work


def test_probe_git_resolves_the_canonical_root_from_a_linked_worktree(tmp_path):
    repo = _limen_like_repo(tmp_path)
    linked = tmp_path / "linked"
    _git(repo, "worktree", "add", "-q", "-b", "feat/wt", str(linked))
    state = sg.probe_git(str(linked))
    assert state.toplevel == linked.resolve()
    assert state.canonical == repo.resolve()
    assert sg.probe_git(str(tmp_path / "not-a-repo-dir-that-does-not-exist")) is None


# --------------------------------------------------------------------------- pause marker and ledger units


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (None, ("none", False)),
        ("class: wall\nreason: safety halt\n", ("wall", True)),
        ("class: fence\nreason: peer lane\nprohibitions: merge\n", ("fence", True)),
        ("class: fence\nreason: peer lane\nprohibitions: sends\n", ("fence", False)),
        ("reason: peer agent coordination\n", ("fence", False)),
        ("reason: stop everything\n", ("wall", True)),
        ("", ("wall", True)),
    ],
)
def test_pause_state_matches_the_orientation_class_parse(tmp_path, text, expected):
    if text is not None:
        (tmp_path / "logs").mkdir()
        (tmp_path / "logs" / "AUTONOMY_PAUSED").write_text(text, encoding="utf-8")
    assert sg.pause_state(tmp_path) == expected


def test_day_counter_is_per_utc_day(tmp_path):
    ledger = sg.FileLedger(tmp_path / "state")
    assert ledger.ready()
    day_one, day_two = 1_700_000_000.0, 1_700_000_000.0 + 86_400
    assert ledger.record("claude", "s", ("CONT",), day_one) and ledger.day_total(day_one) == 1
    assert ledger.day_total(day_two) == 0
    assert ledger.session("claude", "s")["rules"] == {"CONT": 1}
    assert ledger.claim("abc") and not ledger.claim("abc")


def test_load_registry_returns_none_for_missing_or_malformed(tmp_path):
    assert sg.load_registry(tmp_path / "nope.json") is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert sg.load_registry(bad) is None
    bad.write_text(json.dumps({"rules": []}), encoding="utf-8")
    assert sg.load_registry(bad) is None


def test_int_env_ignores_garbage_and_negatives():
    assert sg._int_env({"X": "7"}, "X", 4) == 7
    assert sg._int_env({"X": "abc"}, "X", 4) == 4
    assert sg._int_env({"X": "-3"}, "X", 4) == 4
    assert sg._int_env({}, "X", 4) == 4


# --------------------------------------------------------------------------- the CLI modes


def test_emit_prints_the_operators_lexicon_and_list_shows_modes():
    emitted = subprocess.run(
        [sys.executable, str(GOVERNOR), "--emit", "VERIFY"], capture_output=True, text=True, check=False
    )
    assert emitted.returncode == 0
    assert "were all of the findings healed and addressed?" in emitted.stdout
    assert "BLOCKED: <atom>" in emitted.stdout
    listed = subprocess.run([sys.executable, str(GOVERNOR), "--list"], capture_output=True, text=True, check=False)
    assert listed.returncode == 0
    assert {line.split("\t")[0] for line in listed.stdout.splitlines()} == set(sg.DETECTORS)
    unknown = subprocess.run(
        [sys.executable, str(GOVERNOR), "--emit", "NOPE"], capture_output=True, text=True, check=False
    )
    assert unknown.returncode == 2


def test_decide_cli_is_a_dry_run_that_writes_no_ledger(tmp_path):
    payload = tmp_path / "p.json"
    payload.write_text(json.dumps(_payload(CONT, cwd=str(tmp_path))), encoding="utf-8")
    reg = _registry_file(tmp_path, "CONT")
    git_state = json.dumps(
        {
            "toplevel": str(tmp_path),
            "canonical": str(tmp_path),
            "branch": "feat/x",
            "dirty": False,
            "ahead": 0,
            "has_upstream": True,
            "commits_vs_main": 0,
        }
    )
    marker = tmp_path / REGISTRY_DATA["scope_marker"]
    marker.parent.mkdir(parents=True)
    marker.write_text("{}", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(GOVERNOR), "--decide", str(payload), "--registry", str(reg), "--git-state", git_state],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result["action"] == "block" and result["rules"] == ["CONT"]
    assert not (tmp_path / "logs").exists()


# --------------------------------------------------------------------------- the predicate itself


def _run_predicate(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PREDICATE), *args], capture_output=True, text=True, cwd=ROOT, check=False, timeout=300
    )


def _status() -> str:
    return subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True, cwd=ROOT, check=False
    ).stdout


def test_predicate_is_green_and_idempotent_and_writes_nothing():
    before = _status()
    first, second = _run_predicate(), _run_predicate()
    assert first.returncode == 0, first.stdout
    assert second.returncode == 0, second.stdout
    assert "check-stop-governor: OK" in first.stdout
    assert _status() == before


@pytest.mark.parametrize(
    ("label", "tag", "mutate"),
    [
        ("study count drift", "A", lambda r: r["intents"]["CONT"].update(n=130)),
        ("a study row removed", "A", lambda r: r["intents"].pop("MERGE")),
        ("NEWTASK made automatable", "A", lambda r: r["intents"]["NEWTASK"].update({"class": "stop"})),
        ("live without promotion", "B", lambda r: r["rules"]["CONT"].update(mode="live")),
        ("an invented lexicon phrase", "C", lambda r: r["rules"]["CONT"]["lexicon"].append("make it so number one")),
        (
            "uppercase operator voice",
            "C",
            lambda r: r["rules"]["CONT"].update(text=r["rules"]["CONT"]["text"] + " Please."),
        ),
        ("slash command as mechanism", "C", lambda r: r["rules"]["CONT"].update(text="/proceed and keep going")),
        ("deny gate dropped", "D", lambda r: r["rules"]["CONT"].update(deny_gated=False)),
        ("cap raised", "D", lambda r: r["rules"]["CONT"].update(cap=9)),
        ("plan mode allowed", "D", lambda r: r["permission_modes"]["claude"].append("plan")),
        ("fleet dontAsk allowed", "D", lambda r: r["permission_modes"]["claude"].append("dontAsk")),
    ],
)
def test_predicate_goes_red_when_the_registry_is_wrong(tmp_path, label, tag, mutate):
    reg = copy.deepcopy(REGISTRY_DATA)
    mutate(reg)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(reg), encoding="utf-8")
    proc = _run_predicate("--registry", str(path))
    assert proc.returncode == 1, f"{label}: {proc.stdout}"
    assert f"[{tag}]" in proc.stdout, f"{label}: {proc.stdout}"


def test_predicate_accepts_a_legitimately_promoted_rule(tmp_path):
    reg = copy.deepcopy(REGISTRY_DATA)
    reg["rules"]["CONT"]["mode"] = "live"
    reg["rules"]["CONT"]["promotion"] = {
        "source": "operator",
        "date": "2026-10-19",
        "decision_ref": "https://example.test/x",
    }
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(reg), encoding="utf-8")
    proc = _run_predicate("--registry", str(path))
    assert proc.returncode == 0, proc.stdout
    assert "(1 live)" in proc.stdout


def test_predicate_goes_red_when_the_staged_snippet_is_wrong(tmp_path):
    snippet = json.loads((ROOT / "docs" / "keys" / "stop-governor-settings-snippet.json").read_text(encoding="utf-8"))
    snippet["claude"]["hooks"]["UserPromptSubmit"] = copy.deepcopy(snippet["claude"]["hooks"]["Stop"])
    path = tmp_path / "snippet.json"
    path.write_text(json.dumps(snippet), encoding="utf-8")
    proc = _run_predicate("--snippet", str(path))
    assert proc.returncode == 1 and "[G]" in proc.stdout


def test_predicate_goes_red_when_a_decision_code_loses_its_fixture(tmp_path):
    cases = [c for c in CASES if c["id"] not in ("kill-env", "kill-file")]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    proc = _run_predicate("--cases", str(path))
    assert proc.returncode == 1 and "kill_switch" in proc.stdout


def test_armed_report_never_changes_the_exit_code():
    proc = _run_predicate("--armed")
    assert proc.returncode == 0
    assert "armed[claude]" in proc.stdout and "armed[codex]" in proc.stdout


def _paste_snippet(tmp_path: Path) -> tuple[Path, Path]:
    """Apply the staged snippet to copies of the real tracked files, the way the operator's paste would."""
    snippet = json.loads((ROOT / "docs" / "keys" / "stop-governor-settings-snippet.json").read_text(encoding="utf-8"))
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    settings.setdefault("hooks", {}).update(snippet["claude"]["hooks"])
    hooks = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    hooks["hooks"]["Stop"] = hooks["hooks"]["Stop"] + snippet["codex"]["hooks"]["Stop"]
    claude_path, codex_path = tmp_path / "settings.json", tmp_path / "hooks.json"
    claude_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    codex_path.write_text(json.dumps(hooks, indent=2), encoding="utf-8")
    return claude_path, codex_path


def test_require_armed_is_the_lever_acceptance_and_the_paste_simulation_arms_both(tmp_path):
    parked = _run_predicate("--require-armed")
    assert parked.returncode == 1 and "STOP-GOVERNOR NOT ARMED" in parked.stdout
    assert parked.stdout.count("[ARMED]") == 2
    claude_path, codex_path = _paste_snippet(tmp_path)
    armed = _run_predicate("--require-armed", "--claude-settings", str(claude_path), "--codex-hooks", str(codex_path))
    assert armed.returncode == 0, armed.stdout
    assert "armed[claude]: ARMED" in armed.stdout and "armed[codex]: ARMED" in armed.stdout
    # The existing host-admission Stop entry survives the paste, and the pasted file is still valid JSON.
    pasted = json.loads(codex_path.read_text(encoding="utf-8"))["hooks"]["Stop"]
    assert any("host-admission" in json.dumps(group) for group in pasted)
    assert any("stop-governor" in json.dumps(group) for group in pasted)


def test_require_armed_needs_both_vendors(tmp_path):
    claude_path, codex_path = _paste_snippet(tmp_path)
    codex_path.write_text(json.dumps({"hooks": {"Stop": []}}), encoding="utf-8")
    proc = _run_predicate("--require-armed", "--claude-settings", str(claude_path), "--codex-hooks", str(codex_path))
    assert proc.returncode == 1
    assert "[ARMED] codex" in proc.stdout and "[ARMED] claude" not in proc.stdout
    missing = _run_predicate(
        "--require-armed", "--claude-settings", str(tmp_path / "absent.json"), "--codex-hooks", str(codex_path)
    )
    assert missing.returncode == 1 and "[ARMED] claude" in missing.stdout


def test_a_wrapper_run_stays_inside_the_hook_budget(tmp_path):
    reg = _registry_file(tmp_path, "CONT")
    started = time.monotonic()
    proc = _run_wrapper(
        ["--vendor", "claude", "--event", "Stop", "--registry", str(reg), "--state-dir", str(tmp_path / "s")],
        json.dumps(_payload(CONT)).encode(),
        tmp_path,
    )
    assert proc.returncode == 0
    assert time.monotonic() - started < 8
