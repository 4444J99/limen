"""Stop governor: every decision path, the real wrapper's fail-open contract, the real git probes,
concurrency, privacy of the event log, and the predicate's own discrimination.

Stdlib only (the hook runs on an interpreter that may lack PyYAML). The behavioral matrix is shared with
scripts/check-stop-governor.py through scripts/tests/fixtures/stop-governor-cases.json.
"""

from __future__ import annotations

import ast
import copy
import importlib.util
import json
import os
import re
import shutil
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
    secret = "(private-note-4f9a) Want me to also fix the other two?"
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


def _published_repo(tmp_path: Path) -> tuple[Path, Path]:
    """A limen-like repo with a bare origin and a pushed feature branch that tracks its own upstream."""
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(remote))
    repo = _limen_like_repo(tmp_path)
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "main")
    _git(repo, "checkout", "-q", "-b", "feat/x")
    (repo / "new.txt").write_text("x", encoding="utf-8")
    _git(repo, "add", "new.txt")
    _git(repo, "commit", "-q", "-m", "work")
    _git(repo, "push", "-q", "-u", "origin", "feat/x")
    return repo, remote


def test_probe_git_reads_branch_dirty_and_ahead_in_a_real_repo(tmp_path):
    repo, _ = _published_repo(tmp_path)
    state = sg.probe_git(str(repo))
    assert state.branch == "feat/x" and state.has_upstream and state.ahead == 0 and not state.dirty
    assert state.clean_pushed and not state.work_present and state.canonical == repo.resolve()
    (repo / "more.txt").write_text("y", encoding="utf-8")
    _git(repo, "add", "more.txt")
    _git(repo, "commit", "-q", "-m", "more")
    state = sg.probe_git(str(repo))
    assert state.ahead == 1 and state.work_present and not state.clean_pushed
    _git(repo, "push", "-q")
    (repo / REGISTRY_DATA["scope_marker"]).write_text('{"edited": true}', encoding="utf-8")
    state = sg.probe_git(str(repo))
    assert state.dirty and state.work_present and not state.clean_pushed


def test_an_untracked_new_file_is_unpublished_work(tmp_path):
    repo, _ = _published_repo(tmp_path)
    assert not sg.probe_git(str(repo)).work_present
    (repo / "scripts-new-thing.py").write_text("print(1)", encoding="utf-8")  # never git-added
    state = sg.probe_git(str(repo))
    assert state.dirty and state.work_present and not state.clean_pushed


def test_a_branch_that_only_tracks_origin_main_has_no_upstream_of_its_own(tmp_path):
    repo, _ = _published_repo(tmp_path)
    _git(repo, "checkout", "-q", "-b", "cell/zero", "--track", "origin/main")
    state = sg.probe_git(str(repo))
    assert not state.has_upstream and state.commits_vs_main == 0
    assert not state.work_present and not state.clean_pushed  # zero commits: nothing to merge, nothing to verify
    (repo / "c.txt").write_text("c", encoding="utf-8")
    _git(repo, "add", "c.txt")
    _git(repo, "commit", "-q", "-m", "c")
    state = sg.probe_git(str(repo))
    assert not state.has_upstream and state.commits_vs_main == 1 and state.work_present
    _git(repo, "push", "-q", "origin", "HEAD:refs/heads/cell/zero")  # pushed without -u: still tracking origin/main
    state = sg.probe_git(str(repo))
    assert state.work_present and not state.clean_pushed


def test_a_gone_upstream_is_unknown_not_work(tmp_path):
    repo, remote = _published_repo(tmp_path)
    _git(repo, "checkout", "-q", "main")
    _git(tmp_path, "-C", str(remote), "branch", "-D", "feat/x")
    _git(repo, "fetch", "-q", "--prune", "origin")
    _git(repo, "checkout", "-q", "feat/x")
    state = sg.probe_git(str(repo))
    assert state.upstream_gone and not state.has_upstream
    assert not state.work_present  # a squash-merged branch whose remote is gone is not unpublished work


def test_detached_head_and_unborn_repos_do_not_crash_the_probe(tmp_path):
    repo, _ = _published_repo(tmp_path)
    _git(repo, "checkout", "-q", "--detach")
    state = sg.probe_git(str(repo))
    assert state.branch == "HEAD" and not state.clean_pushed
    unborn = tmp_path / "unborn"
    unborn.mkdir()
    _git(unborn, "init", "-q", "-b", "main")
    state = sg.probe_git(str(unborn))
    assert state is not None and state.branch == "main" and not state.work_present


def test_the_probe_ignores_a_hostile_git_dir_environment(tmp_path, monkeypatch):
    repo, _ = _published_repo(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    _git(elsewhere, "init", "-q", "-b", "other")
    monkeypatch.setenv("GIT_DIR", str(elsewhere / ".git"))
    monkeypatch.setenv("GIT_WORK_TREE", str(elsewhere))
    state = sg.probe_git(str(repo))
    assert state.branch == "feat/x" and state.toplevel == repo.resolve()


def test_a_separate_git_dir_falls_back_to_the_working_tree_for_the_canonical_root(tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    (work / REGISTRY_DATA["scope_marker"]).parent.mkdir(parents=True)
    (work / REGISTRY_DATA["scope_marker"]).write_text("{}", encoding="utf-8")
    _git(work, "init", "-q", "-b", "main", "--separate-git-dir", str(tmp_path / "gitdir"))
    state = sg.probe_git(str(work))
    assert state.canonical == work.resolve()  # not the parent of the git dir


def test_the_probe_never_runs_a_configured_fsmonitor_and_costs_few_git_calls(tmp_path, monkeypatch):
    repo, _ = _published_repo(tmp_path)
    flag = tmp_path / "fsmonitor-ran"
    hook = tmp_path / "fsmonitor.sh"
    hook.write_text(f"#!/bin/sh\ntouch {flag}\n", encoding="utf-8")
    hook.chmod(0o755)
    _git(repo, "config", "core.fsmonitor", str(hook))
    calls: list[list[str]] = []
    real = sg._run_git
    monkeypatch.setattr(sg, "_run_git", lambda args, cwd, deadline: (calls.append(args), real(args, cwd, deadline))[1])
    assert sg.probe_git(str(repo)) is not None
    assert not flag.exists()
    assert len(calls) <= 3


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


CAPS = {"CONT": 2, "VERIFY": 1, "CLOSE": 1}


def test_reserve_checks_claims_and_charges_as_one_step_and_the_day_is_utc(tmp_path):
    ledger = sg.FileLedger(tmp_path / "state")
    day_one, day_two = 1_700_000_000.0, 1_700_000_000.0 + 86_400
    assert ledger.reserve("claude", "s", ("CONT",), "k1", day_one, CAPS, 4, 40) == "ok"
    assert ledger.day_total(day_one) == 1 and ledger.day_total(day_two) == 0
    assert ledger.session("claude", "s")["rules"] == {"CONT": 1}
    assert ledger.reserve("claude", "s", ("CONT",), "k1", day_one, CAPS, 4, 40) == "dup_claim"  # same stop
    assert ledger.reserve("claude", "s", ("CONT",), "k2", day_one, CAPS, 4, 40) == "ok"
    assert ledger.reserve("claude", "s", ("CONT",), "k3", day_one, CAPS, 4, 40) == "intent_cap"
    assert ledger.reserve("claude", "s", ("VERIFY",), "k4", day_one, CAPS, 2, 40) == "session_cap"
    assert ledger.reserve("claude", "s2", ("VERIFY",), "k5", day_one, CAPS, 4, 2) == "daily_cap"
    assert ledger.session("claude", "s")["total"] == 2  # a refused reserve charges nothing


def test_reserve_fails_open_when_the_ledger_cannot_be_made_or_locked(tmp_path):
    blocker = tmp_path / "state-is-a-file"
    blocker.write_text("", encoding="utf-8")
    assert sg.FileLedger(blocker).reserve("claude", "s", ("CONT",), "k", 0.0, CAPS, 4, 40) == "no_ledger"
    ledger = sg.FileLedger(tmp_path / "state")
    assert ledger.ready()
    (tmp_path / "state" / ".lock").mkdir()  # a directory where the lock file should be: cannot be opened
    assert ledger.reserve("claude", "s", ("CONT",), "k", 0.0, CAPS, 4, 40) == "no_ledger"


def test_log_claims_make_a_duplicate_registration_log_once(tmp_path):
    ledger = sg.FileLedger(tmp_path / "state")
    assert ledger.claim_log("0123456789abcdef0123") and not ledger.claim_log("0123456789abcdef0123")


def test_the_session_cap_holds_across_concurrent_processes_with_different_stops(tmp_path):
    repo = _limen_like_repo(tmp_path)
    reg = _registry_file(tmp_path, "CONT")
    state = tmp_path / "state"
    procs = []
    for n in range(12):  # one session, twelve DIFFERENT stops at once: only the cap may decide who blocks
        payload = json.dumps(
            _payload(f"I did part {n}. Want me to also fix the other two?", cwd=str(repo), session_id="one")
        ).encode()
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
        procs.append(
            (
                subprocess.Popen(
                    argv,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    cwd=ROOT,
                    env=_env(tmp_path),
                ),
                payload,
            )
        )
    blocks = 0
    for proc, payload in procs:
        out, _ = proc.communicate(payload, timeout=120)
        assert proc.returncode == 0
        blocks += 1 if out else 0
    assert blocks == 2  # CONT's per-rule cap, enforced atomically


def test_prefilter_pays_for_no_git_when_nothing_could_fire(tmp_path):
    reg = copy.deepcopy(REGISTRY_DATA)

    def boom(_cwd):
        raise AssertionError("git was probed")

    def run(payload, env=None):
        return sg.decide(
            payload, vendor="claude", registry=reg, env=env or {}, probe=boom, ledger_factory=lambda _g: None
        )

    assert run(_payload(CONT, permission_mode="plan")).code == "mode:plan"
    assert run(_payload(CONT), {"LIMEN_STOP_GOVERNOR": "0"}).code == "kill_switch"
    assert run(_payload("Working on it, here is a summary of the files I read.")).code == "no_signal"
    assert run(_payload(CONT, stop_hook_active=True)).code == "continuation_active"
    assert run(_payload(CONT, background_tasks=[{"id": "b"}])).code == "background_tasks"


def test_the_hook_resolves_the_ledger_from_one_probe_and_never_invents_one(tmp_path):
    # Not a git repo: no probe result, so no state dir, so no ledger and no block, and nothing written anywhere.
    reg = _registry_file(tmp_path, "CONT")
    elsewhere = tmp_path / "not-a-repo"
    elsewhere.mkdir()
    proc = _run_wrapper(
        ["--vendor", "claude", "--event", "Stop", "--registry", str(reg)],
        json.dumps(_payload(CONT, cwd=str(elsewhere))).encode(),
        tmp_path,
    )
    assert proc.returncode == 0 and proc.stdout == b""
    assert not any(elsewhere.rglob("*")) and not (elsewhere / "logs").exists()


def test_a_block_is_ascii_even_when_stdout_is_not_utf8(tmp_path):
    repo = _limen_like_repo(tmp_path)
    reg = _registry_file(tmp_path, "CLOSE")
    env = _env(tmp_path, PYTHONIOENCODING="ascii", LC_ALL="C", PYTHONUTF8="0")
    proc = subprocess.run(
        [
            "bash",
            str(WRAPPER),
            "--vendor",
            "claude",
            "--event",
            "Stop",
            "--registry",
            str(reg),
            "--state-dir",
            str(tmp_path / "s"),
        ],
        input=json.dumps(_payload("Done. verify-scoped exited 0.", cwd=str(repo))).encode(),
        capture_output=True,
        cwd=ROOT,
        env=env,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0 and proc.stdout
    assert proc.stdout.isascii() and "\\u00b7" in proc.stdout.decode()
    assert json.loads(proc.stdout)["reason"].count("\u00b7") >= 1  # decodes back to the middle dot


def test_a_pathological_message_cannot_stall_the_hook():
    reg = copy.deepcopy(REGISTRY_DATA)
    nasty = "\n" * 60_000 + "All done and verified: tests passed."
    started = time.monotonic()
    result = sg.prefilter(_payload(nasty), vendor="claude", registry=reg, env={})
    assert time.monotonic() - started < 1.0
    assert not isinstance(result, sg.Decision) and "NEXT" in result.wanted


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


def _scrubbed_env() -> dict[str, str]:
    """The ambient environment can legitimately carry CLAUDE_JOB_DIR, a fleet marker or GIT_DIR; none of that may
    turn the predicate red, so its subprocesses run in a minimal one."""
    env = {k: os.environ[k] for k in ("PATH", "HOME", "TMPDIR", "LANG", "LC_ALL") if k in os.environ}
    env.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_SYSTEM="/dev/null")
    return env


def _run_predicate(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(PREDICATE), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=_scrubbed_env() if env is None else env,
        check=False,
        timeout=300,
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


def _predicate_on(tmp_path: Path, mutate) -> subprocess.CompletedProcess:
    reg = copy.deepcopy(REGISTRY_DATA)
    mutate(reg)
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(reg), encoding="utf-8")
    return _run_predicate("--registry", str(path))


OPERATOR_REF = "https://github.com/4444J99/limen/issues/3128#issuecomment-6271878076"


def test_predicate_accepts_a_declared_evidence_promotion_of_either_kind(tmp_path):
    def operator(reg):
        reg["rules"]["CONT"].update(
            mode="live", promotion={"source": "operator", "date": "2026-10-19", "decision_ref": OPERATOR_REF}
        )

    def replay(reg):
        reg["rules"]["VERIFY"].update(
            mode="live",
            promotion={
                "source": "replay",
                "date": "2026-10-19",
                "n": 40,
                "precision": 0.9,
                "receipt": "docs/plans/2026-10-19-stop-governor.md",
            },
        )

    for label, mutate in (("operator", operator), ("replay", replay)):
        proc = _predicate_on(tmp_path, mutate)
        assert proc.returncode == 0, f"{label}: {proc.stdout}"
        assert "(1 live)" in proc.stdout


@pytest.mark.parametrize(
    ("label", "promotion"),
    [
        ("a one-character decision_ref", {"source": "operator", "date": "2026-10-19", "decision_ref": "x"}),
        (
            "a non-GitHub decision_ref",
            {"source": "operator", "date": "2026-10-19", "decision_ref": "https://example.test/x"},
        ),
        (
            "a decision_ref that is not an issue or PR",
            {"source": "operator", "date": "2026-10-19", "decision_ref": "https://github.com/4444J99/limen"},
        ),
        ("no date", {"source": "operator", "decision_ref": OPERATOR_REF}),
        ("replay without a receipt", {"source": "replay", "date": "2026-10-19", "n": 40, "precision": 0.9}),
        (
            "replay with a receipt that does not exist",
            {"source": "replay", "date": "2026-10-19", "n": 40, "precision": 0.9, "receipt": "docs/receipts/nope.json"},
        ),
        (
            "replay with an absolute receipt",
            {"source": "replay", "date": "2026-10-19", "n": 40, "precision": 0.9, "receipt": "/etc/passwd"},
        ),
        (
            "replay with a traversing receipt",
            {"source": "replay", "date": "2026-10-19", "n": 40, "precision": 0.9, "receipt": "../outside"},
        ),
        (
            "replay with too few samples",
            {
                "source": "replay",
                "date": "2026-10-19",
                "n": 12,
                "precision": 0.95,
                "receipt": "docs/plans/2026-10-19-stop-governor.md",
            },
        ),
        (
            "replay below the precision floor",
            {
                "source": "replay",
                "date": "2026-10-19",
                "n": 40,
                "precision": 0.5,
                "receipt": "docs/plans/2026-10-19-stop-governor.md",
            },
        ),
        ("an unknown source", {"source": "vibes", "date": "2026-10-19"}),
    ],
)
def test_predicate_refuses_a_live_rule_whose_declared_evidence_is_empty(tmp_path, label, promotion):
    proc = _predicate_on(tmp_path, lambda reg: reg["rules"]["CONT"].update(mode="live", promotion=promotion))
    assert proc.returncode == 1 and "[B]" in proc.stdout, f"{label}: {proc.stdout}"


def test_merge_needs_the_stricter_precision_floor(tmp_path):
    promo = {
        "source": "replay",
        "date": "2026-10-19",
        "n": 40,
        "precision": 0.85,
        "receipt": "docs/plans/2026-10-19-stop-governor.md",
    }
    proc = _predicate_on(tmp_path, lambda reg: reg["rules"]["MERGE"].update(mode="live", promotion=promo))
    assert proc.returncode == 1 and "precision must be >= 0.9" in proc.stdout


def _predicate_module():
    spec = importlib.util.spec_from_file_location("check_stop_governor_under_test", PREDICATE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_stop_governor_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_the_governor_is_python_39_clean_and_the_portability_check_bites(tmp_path, monkeypatch):
    text = GOVERNOR.read_text(encoding="utf-8")
    ast.parse(text, feature_version=(3, 9))  # macOS ships 3.9; a hook that cannot import is silent
    assert not re.search(r"from datetime import[^\n]*\bUTC\b", text)
    module = _predicate_module()
    module.failures.clear()
    module.check_portability()
    assert module.failures == []
    bad = tmp_path / "bad-governor.py"
    bad.write_text("from datetime import UTC, datetime\nimport tomllib\n", encoding="utf-8")
    monkeypatch.setattr(module, "GOVERNOR", bad)
    module.failures.clear()
    module.check_portability()
    assert any("datetime.UTC" in f for f in module.failures) and any("tomllib" in f for f in module.failures)
    modern = tmp_path / "match.py"
    modern.write_text("match 1:\n    case 1:\n        pass\n", encoding="utf-8")
    monkeypatch.setattr(module, "GOVERNOR", modern)
    module.failures.clear()
    module.check_portability()
    assert any("Python 3.9 syntax" in f for f in module.failures)


def test_a_failing_interpreter_leaves_one_breadcrumb_and_still_exits_zero(tmp_path):
    tree = tmp_path / "tree"
    (tree / "scripts" / "hooks").mkdir(parents=True)
    shutil.copy(WRAPPER, tree / "scripts" / "hooks" / "stop-governor.sh")
    (tree / "scripts" / "stop-governor.py").write_text("import sys\nsys.exit(3)\n", encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(tree / "scripts" / "hooks" / "stop-governor.sh"), "--vendor", "claude", "--event", "Stop"],
        input=b"{}",
        capture_output=True,
        env=_env(tmp_path),
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0 and proc.stdout == b""
    log = (tree / "logs" / "stop-governor" / "wrapper-errors.log").read_text(encoding="utf-8")
    assert log.count("\n") == 1 and "rc=3" in log


def _orient_module():
    spec = importlib.util.spec_from_file_location("session_orient_under_test", ROOT / "scripts" / "session-orient.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["session_orient_under_test"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "marker",
    [
        "class: wall\nreason: safety halt\n",
        "class: fence\nreason: peer lane\nprohibitions: merge\n",
        "class: fence\nreason: protect a peer\nprohibitions: sends\n",
        "reason: peer agent coordination\n",
        "reason: concurrent lanes\n",
        "reason: stop everything\n",
        "reason: safety halt\nprohibitions: merge, send\n",
        "class: WALL\nreason: peer\n",
    ],
)
def test_pause_class_parse_agrees_with_session_orient(tmp_path, monkeypatch, marker):
    """The governor re-implements the AUTONOMY_PAUSED class parse; feed the same marker to both and compare."""
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "AUTONOMY_PAUSED").write_text(marker, encoding="utf-8")
    orient = _orient_module()
    monkeypatch.setattr(orient, "ROOT", tmp_path)
    rendered = orient.section_autonomy()
    orient_class = "fence" if "PEER-COORDINATION FENCE" in rendered else "wall"
    assert sg.pause_state(tmp_path)[0] == orient_class, rendered


def test_predicate_goes_red_when_the_staged_snippet_is_wrong(tmp_path):
    snippet = json.loads((ROOT / "docs" / "keys" / "stop-governor-settings-snippet.json").read_text(encoding="utf-8"))
    snippet["claude"]["hooks"]["UserPromptSubmit"] = copy.deepcopy(snippet["claude"]["hooks"]["Stop"])
    path = tmp_path / "snippet.json"
    path.write_text(json.dumps(snippet), encoding="utf-8")
    proc = _run_predicate("--snippet", str(path))
    assert proc.returncode == 1 and "[G]" in proc.stdout


def test_predicate_goes_red_when_a_decision_code_loses_its_fixture(tmp_path):
    cases = [c for c in CASES if c["id"] not in ("kill-env", "kill-file", "kill-env-off")]
    path = tmp_path / "cases.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    proc = _run_predicate("--cases", str(path))
    assert proc.returncode == 1 and "kill_switch" in proc.stdout


def test_armed_report_never_changes_the_exit_code():
    proc = _run_predicate("--armed")
    assert proc.returncode == 0
    assert "armed[claude]" in proc.stdout and "armed[codex]" in proc.stdout


def _unarmed_copies(tmp_path: Path) -> tuple[Path, Path]:
    """Temp copies of the real tracked files with any governor entry removed: the 'parked' state, whatever the
    real tree says today (the operator's paste must never turn this suite red)."""
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    settings.get("hooks", {}).pop("Stop", None)
    hooks = json.loads((ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    hooks["hooks"]["Stop"] = [g for g in hooks["hooks"]["Stop"] if "stop-governor" not in json.dumps(g)]
    claude_path, codex_path = tmp_path / "settings.json", tmp_path / "hooks.json"
    claude_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    codex_path.write_text(json.dumps(hooks, indent=2), encoding="utf-8")
    return claude_path, codex_path


def _paste_snippet(tmp_path: Path) -> tuple[Path, Path]:
    """Apply the staged snippet to unarmed copies of the real tracked files, the way the operator's paste would."""
    snippet = json.loads((ROOT / "docs" / "keys" / "stop-governor-settings-snippet.json").read_text(encoding="utf-8"))
    claude_path, codex_path = _unarmed_copies(tmp_path)
    settings = json.loads(claude_path.read_text(encoding="utf-8"))
    settings.setdefault("hooks", {}).update(snippet["claude"]["hooks"])
    hooks = json.loads(codex_path.read_text(encoding="utf-8"))
    hooks["hooks"]["Stop"] = hooks["hooks"]["Stop"] + snippet["codex"]["hooks"]["Stop"]
    claude_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    codex_path.write_text(json.dumps(hooks, indent=2), encoding="utf-8")
    return claude_path, codex_path


def test_require_armed_is_the_lever_acceptance_and_the_paste_simulation_arms_both(tmp_path):
    parked_dir = tmp_path / "parked"
    parked_dir.mkdir()
    parked_claude, parked_codex = _unarmed_copies(parked_dir)
    parked = _run_predicate(
        "--require-armed", "--claude-settings", str(parked_claude), "--codex-hooks", str(parked_codex)
    )
    assert parked.returncode == 1 and "STOP-GOVERNOR NOT ARMED" in parked.stdout
    assert parked.stdout.count("[ARMED]") == 2
    armed_dir = tmp_path / "armed"
    armed_dir.mkdir()
    claude_path, codex_path = _paste_snippet(armed_dir)
    armed = _run_predicate("--require-armed", "--claude-settings", str(claude_path), "--codex-hooks", str(codex_path))
    assert armed.returncode == 0, armed.stdout
    assert "armed[claude]: ARMED" in armed.stdout and "armed[codex]: ARMED" in armed.stdout
    # The existing host-admission Stop entry survives the paste, and the pasted file is still valid JSON.
    pasted = json.loads(codex_path.read_text(encoding="utf-8"))["hooks"]["Stop"]
    assert any("host-admission" in json.dumps(group) for group in pasted)
    assert any("stop-governor" in json.dumps(group) for group in pasted)


def test_require_armed_needs_both_vendors_and_a_governor_that_runs(tmp_path):
    claude_path, codex_path = _paste_snippet(tmp_path)
    codex_path.write_text(json.dumps({"hooks": {"Stop": []}}), encoding="utf-8")
    proc = _run_predicate("--require-armed", "--claude-settings", str(claude_path), "--codex-hooks", str(codex_path))
    assert proc.returncode == 1
    assert "[ARMED] codex" in proc.stdout and "[ARMED] claude" not in proc.stdout
    missing = _run_predicate(
        "--require-armed", "--claude-settings", str(tmp_path / "absent.json"), "--codex-hooks", str(codex_path)
    )
    assert missing.returncode == 1 and "[ARMED] claude" in missing.stdout


def test_require_armed_fails_when_no_python3_can_run_the_governor(tmp_path):
    claude_path, codex_path = _paste_snippet(tmp_path)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = {**_scrubbed_env(), "PATH": str(empty_bin)}
    proc = subprocess.run(
        [
            sys.executable,
            str(PREDICATE),
            "--require-armed",
            "--claude-settings",
            str(claude_path),
            "--codex-hooks",
            str(codex_path),
        ],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
        check=False,
        timeout=300,
    )
    assert proc.returncode == 1 and "the governor does not run on this machine" in proc.stdout


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
