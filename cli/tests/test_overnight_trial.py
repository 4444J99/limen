"""Prospective, append-bound eight-hour unattended-trial contract tests."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "overnight-watch.py"


class Clock:
    def __init__(self, value: dt.datetime):
        self.value = value


def _fresh_module(tmp_path, monkeypatch, start: dt.datetime):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_PRIVATE_SESSION_CORPUS", str(tmp_path / "private"))
    monkeypatch.setenv("LIMEN_OVERNIGHT_WATCH_RECEIPT", str(tmp_path / "logs" / "watch.jsonl"))
    monkeypatch.setenv("LIMEN_OVERNIGHT_TRIAL_RECEIPT", str(tmp_path / "logs" / "trial.json"))
    monkeypatch.setenv("LIMEN_OVERNIGHT_TRIAL_WINDOW", str(tmp_path / "logs" / "window.json"))
    monkeypatch.setenv("LIMEN_OVERNIGHT_TRIAL_OBSERVATIONS", str(tmp_path / "logs" / "trial-observations.jsonl"))
    (tmp_path / "logs" / "async-runs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tasks.yaml").write_text('{"version":1,"tasks":[]}\n', encoding="utf-8")
    (tmp_path / "logs" / "handoff.json").write_text('{"fresh":true}\n', encoding="utf-8")
    spec = importlib.util.spec_from_file_location("overnight_trial_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    clock = Clock(start)
    monkeypatch.setattr(module, "utc_now", lambda: clock.value)
    monotonic_base = 10_000_000_000_000
    monkeypatch.setattr(
        module.time,
        "monotonic_ns",
        lambda: monotonic_base + int((clock.value - start).total_seconds() * 1_000_000_000),
    )
    monkeypatch.setattr(module, "_anchor_created_ns", lambda _path: int(start.timestamp() * 1_000_000_000))
    monkeypatch.setattr(
        module,
        "_observation_custody_created_ns",
        lambda path: int(
            module.parse_iso(json.loads(path.read_text(encoding="utf-8"))["observed_at"]).timestamp() * 1_000_000_000
        ),
    )
    monkeypatch.setattr(
        module,
        "handoff_relay_snapshot",
        lambda **_kwargs: {"ok": True, "check_returncode": 0},
    )
    return module, clock


def _path_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "mode": stat.st_mode & 0o777}


def _terminal_sidecar_state(module, receipt: dict) -> dict[str, tuple[bytes, int]]:
    state = {}
    for name, descriptor in receipt["terminal_custody"]["sources"].items():
        path = module._terminal_custody_path(receipt["trial_id"], name, descriptor["digest"])
        state[name] = (path.read_bytes(), path.stat().st_mode & 0o777)
    return state


def _write_fake_executable(path: Path, marker: Path, *, stdout: str = "") -> None:
    path.write_text(
        f"#!/bin/sh\n: > {shlex.quote(str(marker))}\nprintf '%s\\n' {shlex.quote(stdout)}\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def _write_prompt_authority(
    module,
    at: dt.datetime,
    *,
    operator_count: int = 0,
    scope: str = "all",
    stale: bool = False,
    unsupported: int = 0,
    unresolved: int = 0,
    future_seconds: int = 0,
):
    at = at.astimezone(dt.timezone.utc).replace(microsecond=0)
    source = module.PROMPT_ATOM_SNAPSHOT
    source.parent.mkdir(parents=True, exist_ok=True)
    events = source.parent / "prompt-events.jsonl"
    outcomes = source.parent / "prompt-atom-outcomes.jsonl"
    if not events.exists():
        events.write_text("", encoding="utf-8")
    if not outcomes.exists():
        outcomes.write_text("", encoding="utf-8")
    actual_count, errors = module._operator_count_from_event_bytes(events.read_bytes())
    assert errors == 0
    assert actual_count == operator_count
    cursor = {
        "version": 2,
        "scanner_version": 2,
        "scope": scope,
        "target_scope": "all",
        "all_baseline_complete": scope == "all",
        "pending_files": 0,
        "source_errors": [],
        "unsupported_source_count": unsupported,
        "unresolved_unit_count": unresolved,
        "adapter_gaps": [],
        "source_families": {"fixture": {"discovered": 1, "converged": 1, "pending": 0, "errors": 0, "unsupported": 0}},
        "files": {},
        "last_scan_at": (
            at - dt.timedelta(minutes=20) if stale else at + dt.timedelta(seconds=future_seconds)
        ).isoformat(timespec="seconds"),
    }
    cursor_path = source.parent / "source-cursor.json"
    cursor_path.write_text(json.dumps(cursor, sort_keys=True), encoding="utf-8")
    snapshot = {
        "version": 1,
        "source_cursor_digest": module._cursor_digest(cursor),
        "source_scope": module._cursor_semantic(cursor),
        "coverage": {"operator_occurrences": operator_count},
        "validation": {"ok": True, "errors": []},
        "journal_signatures": {
            "events": _path_signature(events),
            "outcomes": _path_signature(outcomes),
            "cursor": _path_signature(cursor_path),
        },
    }
    source.write_text(json.dumps(snapshot, sort_keys=True), encoding="utf-8")


def _append_operator_occurrence(module, index: int) -> None:
    path = module.PROMPT_ATOM_SNAPSHOT.parent / "prompt-events.jsonl"
    row = {
        "occurrence": {"occurrence_id": f"operator-{index}", "authority": "operator"},
        "atoms": [],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def _load_board(module) -> dict:
    return json.loads(module.TASKS_PATH.read_text())


def _append_task_event(
    module,
    at: dt.datetime,
    index: int,
    status: str,
    *,
    agent: str = "codex",
    session_id: str | None = None,
    predicate: str | None = None,
    receipt_target: str | None = None,
) -> None:
    board = _load_board(module)
    board.setdefault("tasks", []).append(
        {
            "id": f"TRIAL-{index:03d}",
            "status": status,
            "target_agent": agent,
            "predicate": predicate or "python3 -c 'raise SystemExit(0)'",
            "receipt_target": receipt_target or f"git:organvm/limen:docs/receipts/trial-{index}.json",
            "dispatch_log": [
                {
                    "timestamp": at.isoformat(timespec="seconds"),
                    "agent": agent,
                    "session_id": session_id or f"session-{index}",
                    "status": status,
                    "output": f"durable owner receipt {index}",
                }
            ],
        }
    )
    module.TASKS_PATH.write_text(json.dumps(board, sort_keys=True), encoding="utf-8")


def _watch_snapshot(at: dt.datetime) -> dict:
    return {
        "timestamp": at.isoformat(timespec="seconds"),
        "launchd": {"ok": True, "state": "running", "env": {}},
        "log_age_sec": 0,
        "heartbeat": {"latest_tick": {"timestamp": at.isoformat(timespec="seconds")}},
        "worker_count": 0,
        "heartbeat_child_count": 0,
        "stale_tick_count": 0,
        "handoff_relay": {"ok": True, "check_returncode": 0},
        "value_gate": {"returncode": 0},
        "dispatch_control": {"allow_dispatch": True},
        "plist_drift": [],
        "throughput": {"below_floor": False},
    }


def _install_proof_stubs(module, monkeypatch) -> None:
    monkeypatch.setattr(
        module,
        "_prove_terminal_event",
        lambda entry: {"event_id": entry["event_id"], "proof_hash": module.canonical_hash(entry)},
    )
    monkeypatch.setattr(
        module,
        "_prove_session_event",
        lambda entry, **_kwargs: (
            {
                "event_id": entry["event_id"],
                "provider": "jules",
                "proof_hash": module.canonical_hash(entry),
            }
            if entry.get("agent") == "jules" and str(entry.get("session_id") or "").isdigit()
            else None
        ),
    )


def _start(module, start: dt.datetime):
    _write_prompt_authority(module, start)
    marker, changed = module.start_trial()
    assert changed is True
    return marker


def _observe(module, clock: Clock, at: dt.datetime, *, operator_count: int = 0):
    clock.value = at
    _write_prompt_authority(module, at, operator_count=operator_count)
    snapshot = _watch_snapshot(at)
    module.write_jsonl(snapshot)
    return module.append_trial_observation(snapshot)


def _run_trial(
    module,
    clock: Clock,
    start: dt.datetime,
    *,
    value_minutes: tuple[int, ...] = (60, 150, 240, 330, 420),
    seam_agent: str = "jules",
    seam_session: str = "12345678901234567890",
    omit_samples: set[int] | None = None,
    operator_at: int | None = None,
    event_timestamp_offsets: dict[int, int] | None = None,
    extra_alert_at: int | None = None,
):
    marker = _start(module, start)
    operator_count = 0
    for minute in range(5, 481, 5):
        at = start + dt.timedelta(minutes=minute)
        if minute in value_minutes:
            offset = (event_timestamp_offsets or {}).get(minute, 0)
            _append_task_event(module, at + dt.timedelta(seconds=offset), minute, "done")
        if minute == 30:
            _append_task_event(
                module,
                at,
                900,
                "in_progress",
                agent=seam_agent,
                session_id=seam_session,
            )
        if operator_at is not None and minute == operator_at:
            _append_operator_occurrence(module, 1)
            operator_count = 1
        if minute not in (omit_samples or set()):
            if extra_alert_at == minute:
                alert = _watch_snapshot(at - dt.timedelta(seconds=1))
                alert["launchd"] = {"ok": False, "state": "stopped", "env": {}}
                module.write_jsonl(alert)
            _observe(module, clock, at, operator_count=operator_count)
    clock.value = start + dt.timedelta(hours=8)
    return marker, module.maybe_finalize_trial()


def test_trial_passes_rebuilds_and_is_byte_idempotent(tmp_path, monkeypatch, capsys):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    active, result = _run_trial(module, clock, start)
    assert result and result.get("receipt")
    first_bytes = module.TRIAL_PATH.read_bytes()

    second, changed_again = module.finalize_trial(active)

    assert result["receipt"]["pass"] is True
    assert result["receipt"]["operator_interventions"] == 0
    assert result["receipt"]["seam_count"] == 1
    assert result["receipt"]["max_value_gap_seconds"] == 5400
    assert changed_again is False
    assert second == result["receipt"]
    assert module.TRIAL_PATH.read_bytes() == first_bytes
    assert module.check_trial_receipt() == (True, [])
    terminal_bytes = module.TRIAL_WINDOW_PATH.read_bytes()
    repeated = module.maybe_finalize_trial()
    assert repeated and repeated["changed"] is False and repeated["already_finalized"] is True
    assert repeated["receipt"] == result["receipt"]
    assert module.main(["--finalize-trial", "--json"]) == 0
    advertised = json.loads(capsys.readouterr().out)
    assert advertised["changed"] is False
    assert module.TRIAL_PATH.read_bytes() == first_bytes
    assert module.TRIAL_WINDOW_PATH.read_bytes() == terminal_bytes
    serialized = module.TRIAL_PATH.read_text()
    assert "TRIAL-" not in serialized
    assert "session-" not in serialized
    assert "predicate" not in serialized
    assert "receipt_target" not in serialized


def test_extra_mid_window_alert_watch_row_cannot_be_skipped(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)

    _, result = _run_trial(module, clock, start, extra_alert_at=240)

    assert result["receipt"]["watch_alerts"] >= 1
    assert result["receipt"]["pass"] is False
    ok, errors = module.check_trial_receipt()
    assert ok is False
    assert "trial receipt is not passing" in errors


def test_unbound_terminal_window_alert_row_invalidates_receipt(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    alert = _watch_snapshot(start + dt.timedelta(hours=8))
    alert["launchd"] = {"ok": False, "state": "stopped", "env": {}}
    module.write_jsonl(alert)

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert any("in-window watch append is not bound" in error for error in errors)


def test_preseeded_future_events_and_samples_cannot_count(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    for index, minute in enumerate((60, 150, 240, 330, 420), start=1):
        _append_task_event(module, start + dt.timedelta(minutes=minute), index, "done")
    _append_task_event(
        module,
        start + dt.timedelta(minutes=30),
        99,
        "in_progress",
        agent="jules",
        session_id="12345678901234567890",
    )
    synthetic = [_watch_snapshot(start + dt.timedelta(minutes=minute)) for minute in range(5, 481, 5)]
    module.RECEIPT_JSONL.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in synthetic), encoding="utf-8"
    )
    marker = _start(module, start)
    for minute in range(5, 481, 5):
        _observe(module, clock, start + dt.timedelta(minutes=minute))
    clock.value = start + dt.timedelta(hours=8)
    receipt = module.build_trial_receipt(marker)

    assert receipt["value_done_events"] == 0
    assert receipt["seam_count"] == 0
    assert receipt["pass"] is False


@pytest.mark.parametrize("offset_seconds", [-(62 * 60), 2 * 60])
def test_pre_window_or_future_task_timestamp_cannot_earn_credit(tmp_path, monkeypatch, offset_seconds):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)

    _, result = _run_trial(
        module,
        clock,
        start,
        event_timestamp_offsets={60: offset_seconds},
    )

    assert result["receipt"]["value_done_events"] == 4
    assert result["receipt"]["pass"] is False


def test_finalize_refuses_before_due_time(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    marker = _start(module, start)
    clock.value = start + dt.timedelta(hours=1)

    with pytest.raises(module.TrialContractError, match="cannot be finalized before"):
        module.finalize_trial(marker)


def test_wall_clock_jump_cannot_backfill_eight_hours(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    marker = _start(module, start)
    clock.value = start + dt.timedelta(hours=8)
    monkeypatch.setattr(module.time, "monotonic_ns", lambda: marker["monotonic_start_ns"] + 1_000_000_000)

    with pytest.raises(module.TrialContractError, match="monotonic custody"):
        module.finalize_trial(marker)


@pytest.mark.parametrize(
    "scope,stale,unsupported,unresolved",
    [("partial:all", False, 0, 0), ("all", True, 0, 0), ("all", False, 2, 0), ("all", False, 0, 3)],
)
def test_start_fails_closed_without_fresh_exact_prompt_authority(
    tmp_path, monkeypatch, scope, stale, unsupported, unresolved
):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _write_prompt_authority(
        module,
        start,
        scope=scope,
        stale=stale,
        unsupported=unsupported,
        unresolved=unresolved,
    )

    with pytest.raises(module.TrialContractError, match="fresh exact all/all"):
        module.start_trial()


def test_stored_prompt_freshness_lie_is_rejected(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _write_prompt_authority(module, start)
    snapshot = module.prompt_authority_snapshot(start)
    snapshot.update({"last_scan_at": "2000-01-01T00:00:00+00:00", "age_sec": 0, "fresh": True})

    errors = module._prompt_snapshot_errors(snapshot, start)

    assert "prompt authority age is not derived from scan time" in errors
    assert "prompt authority freshness claim is invalid" in errors


def test_prompt_scan_ten_minutes_in_future_is_rejected(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _write_prompt_authority(module, start, future_seconds=10 * 60)

    snapshot = module.prompt_authority_snapshot(start)

    assert snapshot["age_sec"] == -(10 * 60)
    assert snapshot["fresh"] is False
    with pytest.raises(module.TrialContractError, match="fresh exact all/all"):
        module.start_trial()


def test_arbitrary_session_string_does_not_count_as_seam(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(
        module,
        clock,
        start,
        seam_agent="not-a-provider",
        seam_session="arbitrary-string",
    )

    assert result["receipt"]["seam_count"] == 0
    assert result["receipt"]["pass"] is False


def test_failed_predicate_or_missing_receipt_does_not_count(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    monkeypatch.setattr(module, "_receipt_target_proof", lambda _target: None)
    monkeypatch.setattr(
        module,
        "_prove_session_event",
        lambda entry, **_kwargs: {
            "event_id": entry["event_id"],
            "provider": "jules",
            "proof_hash": module.canonical_hash(entry),
        },
    )
    _, result = _run_trial(module, clock, start)

    assert result["receipt"]["value_done_events"] == 0
    assert result["receipt"]["pass"] is False


def test_real_predicate_and_receipt_proof_are_both_required(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    entry = {
        "event_id": "a" * 64,
        "predicate": "test -f tasks.yaml",
        "receipt_target": "git:organvm/limen:docs/receipt.json",
        "output_present": True,
    }
    monkeypatch.setattr(module, "_receipt_target_proof", lambda _target: {"object_hash": "b" * 64})
    assert module._prove_terminal_event(entry) is not None
    entry["predicate"] = "test -f missing-file"
    assert module._prove_terminal_event(entry) is None


@pytest.mark.parametrize(
    "predicate",
    [
        "sh -c 'rm -rf /tmp/x'",
        "gh issue close 1 --repo organvm/limen",
        "test -f tasks.yaml && touch x",
        "test -f tasks.yaml | touch x",
        "test -f tasks.yaml & touch x",
        "test -f tasks.yaml > result",
        "test -f tasks.yaml < result",
        "(test -f tasks.yaml)",
        "{ test -f tasks.yaml; }",
        "test -f tasks.yaml\ntouch x",
        "test -f `touch x`",
    ],
)
def test_mutating_predicates_are_never_executed(tmp_path, monkeypatch, predicate):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)

    assert module._predicate_is_observation_only(predicate) is False
    assert module._predicate_proof(predicate) is None


@pytest.mark.parametrize(
    "predicate",
    [
        "gh api repos/organvm/limen --jq .full_name",
        "gh run view 123 --repo organvm/limen --json conclusion --jq .conclusion",
        'test "$(gh pr view 980 --repo organvm/limen --json state --jq .state)" = MERGED',
        "gh run list --repo organvm/limen --json conclusion --jq '[.[] | select(.conclusion == \"success\")] | length'",
    ],
)
def test_safe_predicate_classification_never_executes(tmp_path, monkeypatch, predicate):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    monkeypatch.setattr(
        module,
        "_run_predicate_argv",
        lambda _argv: pytest.fail("classification must not execute a command"),
    )

    assert module._predicate_is_observation_only(predicate) is True


@pytest.mark.parametrize(
    "predicate",
    [
        "gh api repos/organvm/limen -XPOST -fbody=changed",
        "gh api repos/organvm/limen -X POST",
        "gh api repos/organvm/limen -fbody=changed",
        "gh api repos/organvm/limen -Fbody=changed",
        "gh api repos/organvm/limen --field=body=changed",
        "gh api repos/organvm/limen --fie body=changed",
        "gh api repos/organvm/limen --raw-field=body=changed",
        "gh api repos/organvm/limen --raw-f body=changed",
        "gh api repos/organvm/limen --input=payload.json",
        "gh api repos/organvm/limen --inp payload.json",
        "gh api repos/organvm/limen --i payload.json",
        "gh api repos/organvm/limen --method=POST",
        "gh api repos/organvm/limen --met POST",
        "gh api repos/organvm/limen --r body=changed",
        "gh api repos/organvm/limen -iXPOST",
        "gh api repos/organvm/limen --cache 1h",
        "gh api repos/organvm/limen --cache=1h",
        "gh pr view 980 -Rorganvm/limen --json state",
        "gh pr view 980 --web",
        "gh pr view 980 --we",
        "gh pr view 980 --help",
        "gh pr view 980 --he",
        "gh pr view 980 --h",
        "gh pr view 980 --v",
        "gh pr view 980 --w",
        "gh repo view -w",
        "gh pr checks 980 --watch",
    ],
)
def test_gh_mutation_or_external_view_flags_are_rejected_without_execution(tmp_path, monkeypatch, predicate):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    calls = []
    monkeypatch.setattr(module, "_run_predicate_argv", lambda argv: calls.append(argv))

    assert module._predicate_is_observation_only(predicate) is False
    assert module._predicate_proof(predicate) is None
    assert calls == []


def test_non_git_predicate_families_do_not_execute_inherited_path_or_startup_hooks(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    markers = {}
    for name in ("[", "bash", "check-fake.py", "gh", "python", "python3", "sh", "test", "zsh"):
        marker = tmp_path / f"{name.replace('[', 'bracket')}-invoked"
        markers[name] = marker
        _write_fake_executable(fake_bin / name, marker, stdout="forged")
    python_startup = tmp_path / "python-startup"
    python_startup.mkdir()
    python_startup_marker = tmp_path / "python-startup-invoked"
    (python_startup / "sitecustomize.py").write_text(
        f"from pathlib import Path\nPath({str(python_startup_marker)!r}).touch()\n",
        encoding="utf-8",
    )
    bash_startup_marker = tmp_path / "bash-startup-invoked"
    bash_startup = tmp_path / "bash-startup.sh"
    bash_startup.write_text(f": > {shlex.quote(str(bash_startup_marker))}\n", encoding="utf-8")
    zsh_startup_marker = tmp_path / "zsh-startup-invoked"
    zsh_startup = tmp_path / "zsh-startup"
    zsh_startup.mkdir()
    (zsh_startup / ".zshenv").write_text(
        f": > {shlex.quote(str(zsh_startup_marker))}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PATH", f"{fake_bin}{module.os.pathsep}{module.os.environ.get('PATH', '')}")
    monkeypatch.setenv("PYTHONPATH", str(python_startup))
    monkeypatch.setenv("BASH_ENV", str(bash_startup))
    monkeypatch.setenv("ENV", str(bash_startup))
    monkeypatch.setenv("ZDOTDIR", str(zsh_startup))
    monkeypatch.setenv("GH_CONFIG_DIR", str(tmp_path / "untrusted-gh-config"))
    monkeypatch.setenv("GH_HOST", "forged.example.invalid")
    monkeypatch.setenv("SSL_CERT_FILE", str(tmp_path / "forged-ca.pem"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "untrusted-xdg"))

    trusted_gh = module._trusted_fixed_executable("gh")
    if trusted_gh is not None:
        gh_result = module._run_predicate_argv(["gh", "--version"])
        assert gh_result is not None and gh_result[0] == 0
    assert module._predicate_proof("test -f tasks.yaml") is not None
    assert module._predicate_proof("[ -f tasks.yaml ]") is not None
    for predicate in (
        "python scripts/check-agent-docs.py --check",
        "python3 scripts/check-agent-docs.py --check",
        "bash scripts/verify-whole.sh",
        "sh scripts/verify-whole.sh",
        "zsh scripts/verify-whole.sh",
        "check-fake.py --check",
    ):
        assert module._predicate_is_observation_only(predicate) is False
        assert module._predicate_proof(predicate) is None

    assert not any(marker.exists() for marker in markers.values())
    assert python_startup_marker.exists() is False
    assert bash_startup_marker.exists() is False
    assert zsh_startup_marker.exists() is False
    proof_environment = module._trusted_tool_environment()
    for name in (
        "BASH_ENV",
        "ENV",
        "GH_CONFIG_DIR",
        "GH_HOST",
        "PYTHONPATH",
        "SSL_CERT_FILE",
        "XDG_CONFIG_HOME",
        "ZDOTDIR",
    ):
        assert name not in proof_environment


def test_receipt_and_jules_proofs_do_not_execute_inherited_path_tools(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_gh_marker = tmp_path / "fake-gh-invoked"
    fake_jules_marker = tmp_path / "fake-jules-invoked"
    _write_fake_executable(fake_bin / "gh", fake_gh_marker, stdout='{"sha":"forged"}')
    _write_fake_executable(
        fake_bin / "jules",
        fake_jules_marker,
        stdout="123456789012  forged session  in progress",
    )
    monkeypatch.setenv("PATH", f"{fake_bin}{module.os.pathsep}{module.os.environ.get('PATH', '')}")
    monkeypatch.setenv("LIMEN_JULES_BIN", str(fake_bin / "jules"))
    original_resolver = module._trusted_fixed_executable

    def deny_remote_tools(name, *, system_only=False):
        if name in {"gh", "jules"}:
            return "/bin/false"
        return original_resolver(name, system_only=system_only)

    monkeypatch.setattr(module, "_trusted_fixed_executable", deny_remote_tools)

    assert module._github_api_proof("repos/organvm/limen") is None
    assert module._receipt_target_proof("git:organvm/limen:docs/receipt.json") is None
    assert (
        module._prove_session_event(
            {
                "event_id": "a" * 64,
                "agent": "jules",
                "session_id": "123456789012",
            }
        )
        is None
    )
    assert fake_gh_marker.exists() is False
    assert fake_jules_marker.exists() is False


@pytest.mark.parametrize(
    "target",
    [
        "https://github.com/organvm/limen/blob/main/does-not-exist.txt",
        "https://github.com/organvm/limen/tree/main/does-not-exist",
        "https://github.com/organvm/limen/blob/feature/slash-ref/does-not-exist.txt",
        "https://github.com/organvm/limen/tree/feature/slash-ref/does-not-exist",
    ],
)
def test_blob_and_tree_urls_cannot_prove_only_ref_existence(tmp_path, monkeypatch, target):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    monkeypatch.setattr(
        module,
        "_github_api_proof",
        lambda _endpoint: pytest.fail("ambiguous blob/tree URL must not degrade to a commit proof"),
    )

    assert module._receipt_target_proof(target) is None


def test_declared_github_receipt_requires_exact_terminal_task_key(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    objects = [
        {
            "number": 1,
            "body": "closes TASK-100 only",
            "title": "unrelated",
            "state": "MERGED",
            "mergedAt": "2026-07-01T00:00:00Z",
            "mergeCommit": {"oid": "a" * 40},
        }
    ]
    monkeypatch.setattr(
        module,
        "_run_trusted_tool_argv",
        lambda *_args, **_kwargs: (0, json.dumps(objects), ""),
    )

    target = "github:organvm/limen:pull-request:TASK-10"
    assert module._receipt_target_proof(target) is None
    objects[0]["body"] = "closes TASK-10 with exact owner receipt"
    assert module._receipt_target_proof(target) is not None

    objects[:] = [
        {
            "number": 2,
            "title": "owner packet for TASK-100",
            "state": "CLOSED",
            "closedAt": "2026-07-01T00:00:00Z",
        }
    ]
    issue_target = "github:organvm/limen:issue:TASK-10"
    assert module._receipt_target_proof(issue_target) is None
    objects[0]["title"] = "owner packet for TASK-10"
    assert module._receipt_target_proof(issue_target) is not None


def test_git_receipt_anchor_must_exist_exactly(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)

    def content(task_id):
        encoded = module.base64.b64encode(json.dumps({"task_id": task_id}).encode()).decode()
        return {"type": "file", "sha": "a" * 40, "encoding": "base64", "content": encoded}

    payload = content("TASK-100")
    monkeypatch.setattr(module, "_github_api_object", lambda _endpoint: payload)
    target = "git:organvm/limen:docs/receipt.json#TASK-10"

    assert module._receipt_target_proof(target) is None
    payload = content("TASK-10")
    assert module._receipt_target_proof(target) is not None


def test_terminal_url_receipt_requires_claimed_terminal_state(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    payload = {"number": 957, "state": "open", "closed_at": None}
    monkeypatch.setattr(module, "_github_api_object", lambda _endpoint: payload)

    target = "https://github.com/organvm/limen/issues/957"
    assert module._receipt_target_proof(target) is None
    payload.update({"state": "closed", "closed_at": "2026-07-01T00:00:00Z"})
    assert module._receipt_target_proof(target) is not None

    payload = {"number": 980, "state": "closed", "merged_at": None, "merge_commit_sha": None}
    monkeypatch.setattr(module, "_github_api_object", lambda _endpoint: payload)
    pull_target = "https://github.com/organvm/limen/pull/980"
    assert module._receipt_target_proof(pull_target) is None
    payload.update({"merged_at": "2026-07-01T00:00:00Z", "merge_commit_sha": "a" * 40})
    assert module._receipt_target_proof(pull_target) is not None

    payload = {"id": 123, "status": "completed", "conclusion": "failure"}
    monkeypatch.setattr(module, "_github_api_object", lambda _endpoint: payload)
    run_target = "https://github.com/organvm/limen/actions/runs/123"
    assert module._receipt_target_proof(run_target) is None
    payload["conclusion"] = "success"
    assert module._receipt_target_proof(run_target) is not None


def test_github_actions_seam_requires_current_in_window_run(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    observed_at = start + dt.timedelta(minutes=30)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    run_id = "123456789012"
    entry = {
        "event_id": "a" * 64,
        "agent": "github_actions",
        "session_id": f"https://github.com/organvm/limen/actions/runs/{run_id}",
        "timestamp": (start + dt.timedelta(minutes=10)).isoformat(timespec="seconds"),
    }
    payload = {
        "id": int(run_id),
        "status": "completed",
        "conclusion": "success",
        "created_at": (start - dt.timedelta(days=1)).isoformat(timespec="seconds"),
        "run_started_at": (start - dt.timedelta(days=1)).isoformat(timespec="seconds"),
        "updated_at": (start - dt.timedelta(days=1)).isoformat(timespec="seconds"),
    }
    monkeypatch.setattr(module, "_github_api_object", lambda _endpoint: payload)

    assert module._prove_session_event(entry, window_start=start, observed_at=observed_at) is None
    payload.update(
        {
            "status": "in_progress",
            "conclusion": None,
            "created_at": (start + dt.timedelta(minutes=5)).isoformat(timespec="seconds"),
            "run_started_at": (start + dt.timedelta(minutes=6)).isoformat(timespec="seconds"),
            "updated_at": (start + dt.timedelta(minutes=20)).isoformat(timespec="seconds"),
            "html_url": entry["session_id"],
            "head_sha": "b" * 40,
            "head_branch": "main",
        }
    )
    active_proof = module._prove_session_event(entry, window_start=start, observed_at=observed_at)
    assert active_proof is not None
    payload.update({"status": "completed", "conclusion": "success"})
    assert (
        module._prove_session_event(
            entry,
            window_start=start,
            observed_at=observed_at,
            require_active=False,
        )
        == active_proof
    )


def test_jules_seam_requires_active_recent_exact_session(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    observed_at = start + dt.timedelta(minutes=30)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    session_id = "123456789012"
    entry = {
        "event_id": "a" * 64,
        "agent": "jules",
        "session_id": session_id,
        "timestamp": (start + dt.timedelta(minutes=10)).isoformat(timespec="seconds"),
    }

    monkeypatch.setattr(
        module,
        "_run_trusted_tool_argv",
        lambda *_args, **_kwargs: (0, f"{session_id}  in progress  5m ago\n", ""),
    )
    active_proof = module._prove_session_event(entry, window_start=start, observed_at=observed_at)
    assert active_proof is not None
    monkeypatch.setattr(
        module,
        "_run_trusted_tool_argv",
        lambda *_args, **_kwargs: (0, f"{session_id}  in progress  2h ago\n", ""),
    )
    assert module._prove_session_event(entry, window_start=start, observed_at=observed_at) is None
    monkeypatch.setattr(
        module,
        "_run_trusted_tool_argv",
        lambda *_args, **_kwargs: (0, f"{session_id}  completed  just now\n", ""),
    )
    assert module._prove_session_event(entry, window_start=start, observed_at=observed_at) is None
    assert (
        module._prove_session_event(
            entry,
            window_start=start,
            observed_at=observed_at,
            require_active=False,
        )
        == active_proof
    )


@pytest.mark.parametrize(
    "predicate",
    [
        "git diff --output=/tmp/x",
        "git diff --output /tmp/x",
        "git diff -o /tmp/x",
        "git diff -o/tmp/x",
        "git diff --out=/tmp/x",
        "git show --output=/tmp/x HEAD",
        "git diff --ext-diff",
        "git diff --ext",
        "git show --textconv HEAD:file",
        "git show --textc HEAD:file",
        "git show --show-signature HEAD",
        "git show --show-sig HEAD",
        "git log --format=%G? -1",
        "git log --format=pretty -1",
        "git log --for=pretty -1",
        "git log --pretty=unsafe -1",
        "git log --pre=unsafe -1",
        "git --paginate log -1",
        "git -c core.pager=/tmp/x log -1",
        "git --config-env=core.pager:PAGER log -1",
        "git diff --pager=/tmp/x",
        "git diff --external-diff=/tmp/x",
        "git ls-remote --upload-pack=/tmp/x origin",
        "git ls-remote origin",
        "git ls-remote ext::/tmp/executable-helper",
        "git ls-remote ssh://example.invalid/repo.git",
        "git log --exec=/tmp/x",
        "git --exec-path=/tmp/x status",
        "git status --porcelain --help",
        "git status --porcelain --hel",
        "git status --porcelain --he",
        "git diff --stat -h",
        "git log -1 --help",
        "git status --version",
        "git status --ver",
        "git status -v",
    ],
)
def test_git_write_or_exec_flags_are_rejected_without_execution(tmp_path, monkeypatch, predicate):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    calls = []
    monkeypatch.setattr(module, "_run_predicate_argv", lambda argv: calls.append(argv))

    assert module._predicate_is_observation_only(predicate) is False
    assert module._predicate_proof(predicate) is None
    assert calls == []


def test_safe_git_classifier_is_nonexecuting(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    monkeypatch.setattr(
        module,
        "_run_predicate_argv",
        lambda _argv: pytest.fail("classification must not execute git"),
    )

    assert module._predicate_is_observation_only("git diff --no-ext-diff --no-textconv --exit-code") is True


def test_safe_git_executor_scrubs_ambient_exec_hooks(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    poisoned = {
        "GIT_ALTERNATE_OBJECT_DIRECTORIES": "/tmp/untrusted-objects",
        "GIT_ALLOW_PROTOCOL": "ext:ssh:https:file",
        "GIT_COMMON_DIR": "/tmp/untrusted-common",
        "GIT_CONFIG": "/tmp/untrusted-config",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_GLOBAL": "/tmp/untrusted-global-config",
        "GIT_CONFIG_KEY_0": "protocol.ext.allow",
        "GIT_CONFIG_PARAMETERS": "'protocol.ext.allow=always'",
        "GIT_CONFIG_SYSTEM": "/tmp/untrusted-system-config",
        "GIT_CONFIG_VALUE_0": "always",
        "GIT_DIFF_OPTS": "--ext-diff",
        "GIT_DIR": "/tmp/untrusted-git-dir",
        "GIT_EXEC_PATH": "/tmp/untrusted-exec-path",
        "GIT_EXTERNAL_DIFF": "/tmp/untrusted-diff",
        "GIT_NO_LAZY_FETCH": "0",
        "GIT_OBJECT_DIRECTORY": "/tmp/untrusted-object-dir",
        "GIT_PAGER": "/tmp/untrusted-pager",
        "GIT_PROTOCOL_FROM_USER": "1",
        "GIT_SSH": "/tmp/untrusted-ssh",
        "GIT_SSH_COMMAND": "/tmp/untrusted-ssh-command",
        "GIT_TRACE": "/tmp/untrusted-trace",
        "GIT_TRACE2": "/tmp/untrusted-trace2",
        "GIT_WORK_TREE": "/tmp/untrusted-work-tree",
        "HTTPS_PROXY": "http://untrusted.invalid",
        "SSH_AUTH_SOCK": "/tmp/untrusted-agent",
    }
    for name, value in poisoned.items():
        monkeypatch.setenv(name, value)
    captured = {}

    class Process:
        returncode = 0

        def communicate(self, timeout=None):
            assert timeout == module.TRIAL_PREDICATE_TIMEOUT_SEC
            return "", ""

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["env"] = kwargs["env"]
        return Process()

    monkeypatch.setattr(module.subprocess, "Popen", fake_popen)

    assert module._run_predicate_argv(["git", "diff", "--check"]) == (0, "", "")
    controlled = {
        "GIT_ALLOW_PROTOCOL": "",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "",
        "GIT_PROTOCOL_FROM_USER": "0",
        "GIT_TERMINAL_PROMPT": "0",
    }
    assert {name: captured["env"].get(name) for name in controlled} == controlled
    assert {name for name in captured["env"] if name.startswith("GIT_")} == set(controlled)
    assert set(captured["env"]) == {*controlled, "LANG", "LC_ALL", "PAGER", "PATH"}
    assert not any(name in captured["env"] for name in poisoned if name not in controlled)
    assert "HTTPS_PROXY" not in captured["env"]
    assert "SSH_AUTH_SOCK" not in captured["env"]
    assert captured["env"]["PAGER"] == ""
    assert captured["env"]["PATH"] == module.os.defpath
    assert captured["env"]["GIT_OPTIONAL_LOCKS"] == "0"
    assert captured["argv"][0] == module._trusted_git_executable()
    assert captured["argv"][-3:] == ["--no-ext-diff", "--no-textconv", "--check"]
    assert "--no-optional-locks" in captured["argv"]
    assert "--no-replace-objects" in captured["argv"]
    for setting in (
        "core.alternateRefsCommand=",
        "core.askPass=",
        "core.fsmonitor=false",
        "core.hooksPath=/dev/null",
        "core.pager=",
        "core.sshCommand=",
        "credential.helper=",
        "diff.external=",
        "format.pretty=medium",
        "log.showSignature=false",
        "protocol.allow=never",
        "protocol.ext.allow=never",
        "protocol.file.allow=never",
        "protocol.git.allow=never",
        "protocol.http.allow=never",
        "protocol.https.allow=never",
        "protocol.ssh.allow=never",
    ):
        assert setting in captured["argv"]


def test_safe_git_executor_does_not_resolve_git_from_inherited_path(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    trusted_git = module._trusted_git_executable()
    assert trusted_git is not None
    subprocess.run([trusted_git, "-C", str(tmp_path), "init", "--quiet"], check=True)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    marker = tmp_path / "fake-git-invoked"
    fake_git = fake_bin / "git"
    fake_git.write_text(f'#!/bin/sh\n: > "{marker}"\nexit 99\n', encoding="utf-8")
    fake_git.chmod(0o700)
    monkeypatch.setenv("PATH", f"{fake_bin}{module.os.pathsep}{module.os.defpath}")

    result = module._run_predicate_argv(["git", "status", "--short"])

    assert result is not None and result[0] == 0
    assert marker.exists() is False


def test_safe_git_executor_neutralizes_repo_signature_helpers(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    trusted_git = module._trusted_git_executable()
    ssh_keygen = shutil.which("ssh-keygen", path=module.os.defpath)
    if trusted_git is None or ssh_keygen is None:
        pytest.skip("trusted git and ssh-keygen are required for the signed-commit fixture")

    def git(*args, check=True):
        return subprocess.run(
            [trusted_git, "-C", str(tmp_path), *args],
            check=check,
            capture_output=True,
            text=True,
        )

    git("init", "--quiet")
    git("config", "user.email", "signed-fixture@example.invalid")
    git("config", "user.name", "Signed Fixture")
    signing_key = tmp_path / "signing-key"
    subprocess.run(
        [ssh_keygen, "-q", "-t", "ed25519", "-N", "", "-f", str(signing_key)],
        check=True,
        capture_output=True,
        text=True,
    )
    git("config", "gpg.format", "ssh")
    git("config", "user.signingkey", str(signing_key))
    (tmp_path / "signed.txt").write_text("signed fixture\n", encoding="utf-8")
    git("add", "signed.txt")
    git("commit", "--quiet", "-S", "-m", "signed fixture")

    helper_marker = tmp_path / "signature-helper-invoked"
    helper = tmp_path / "signature-helper.sh"
    helper.write_text(
        f"#!/bin/sh\n: > {shlex.quote(str(helper_marker))}\nexit 1\n",
        encoding="utf-8",
    )
    helper.chmod(0o700)
    public_key = signing_key.with_suffix(".pub").read_text(encoding="utf-8").split()
    allowed_signers = tmp_path / "allowed-signers"
    allowed_signers.write_text(
        f"signed-fixture@example.invalid {public_key[0]} {public_key[1]}\n",
        encoding="utf-8",
    )
    # Probe for gpg.ssh.program capability (added in git 2.34.0).  On older runners
    # the helper is never invoked and the "B" assertion would be vacuously wrong.
    version_out = subprocess.run(
        [trusted_git, "--version"], capture_output=True, text=True, check=True
    ).stdout  # e.g. "git version 2.34.1" or "git version 2.34.0 (Apple Git-156)"
    # The version token is always the third word ("git version X.Y.Z [...]")
    version_parts = version_out.split()
    try:
        major, minor = (int(x) for x in version_parts[2].split(".")[:2])
    except (IndexError, ValueError):
        major, minor = 0, 0
    if (major, minor) < (2, 34):
        pytest.skip(f"gpg.ssh.program not supported by {version_out.strip()} (requires git >= 2.34)")

    git("config", "gpg.ssh.allowedSignersFile", str(allowed_signers))
    git("config", "gpg.ssh.program", str(helper))
    # Pass --format=%G? explicitly; relying on format.pretty config alone is fragile
    # across git versions and is the defect that caused empty output on CI runners.
    uncontrolled = git("log", "-1", "--format=%G?", check=False)
    assert uncontrolled.stdout.strip() == "B", (
        f"expected 'B' (bad sig via custom helper), got {uncontrolled.stdout!r}; stderr: {uncontrolled.stderr!r}"
    )
    assert helper_marker.is_file()
    helper_marker.unlink()

    result = module._run_predicate_argv(["git", "log", "-1"])

    assert result is not None and result[0] == 0
    assert helper_marker.exists() is False
    git("config", "pretty.oneline", "%G?")
    oneline_result = module._run_predicate_argv(["git", "log", "--oneline", "-1"])
    assert oneline_result is not None and oneline_result[0] == 0
    assert helper_marker.exists() is False


def test_safe_git_executor_denies_alternate_and_promisor_transport(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)

    def git(*args, env=None):
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

    git("init", "--quiet")
    git("config", "user.email", "trial-fixture@example.invalid")
    git("config", "user.name", "Trial Fixture")
    tracked = tmp_path / "tracked.txt"
    tracked.write_text("alternate-only-payload\n", encoding="utf-8")
    git("add", "tracked.txt")
    git("commit", "--quiet", "-m", "fixture")
    safe_read = module._run_predicate_argv(["git", "show", "HEAD:tracked.txt"])
    assert safe_read is not None and safe_read[:2] == (0, "alternate-only-payload\n")
    blob_oid = git("rev-parse", "HEAD:tracked.txt").stdout.strip()
    object_path = tmp_path / ".git" / "objects" / blob_oid[:2] / blob_oid[2:]
    assert object_path.is_file()
    alternate_objects = tmp_path.parent / f"{tmp_path.name}-alternate-objects"
    shutil.copytree(tmp_path / ".git" / "objects", alternate_objects)
    object_path.unlink()

    alternate_env = dict(module.os.environ)
    alternate_env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(alternate_objects)
    alternate_env["GIT_NO_LAZY_FETCH"] = "1"
    assert git("show", "HEAD:tracked.txt", env=alternate_env).stdout == "alternate-only-payload\n"

    helper_marker = tmp_path / "transport-helper-invoked"
    helper = tmp_path / "transport-helper.sh"
    helper.write_text('#!/bin/sh\n: > "$1"\nexit 1\n', encoding="utf-8")
    helper.chmod(0o700)
    git("config", "remote.origin.url", f"ext::{helper} {helper_marker}")
    git("config", "remote.origin.promisor", "true")
    git("config", "remote.origin.partialclonefilter", "blob:none")
    git("config", "protocol.ext.allow", "always")
    git("config", "core.repositoryformatversion", "1")
    git("config", "extensions.partialClone", "origin")
    uncontrolled_env = {name: value for name, value in module.os.environ.items() if not name.startswith("GIT_")}
    uncontrolled_env.update(
        {
            "GIT_ALLOW_PROTOCOL": "ext",
            "GIT_PROTOCOL_FROM_USER": "1",
            "GIT_TERMINAL_PROMPT": "0",
        }
    )
    uncontrolled = subprocess.run(
        ["git", "-C", str(tmp_path), "show", "HEAD:tracked.txt"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
        env=uncontrolled_env,
    )
    assert uncontrolled.returncode != 0
    assert helper_marker.is_file()
    helper_marker.unlink()
    monkeypatch.setenv("GIT_ALTERNATE_OBJECT_DIRECTORIES", str(alternate_objects))
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "ext:file:ssh:https")
    monkeypatch.setenv("GIT_PROTOCOL_FROM_USER", "1")
    monkeypatch.setenv("GIT_NO_LAZY_FETCH", "0")

    result = module._run_predicate_argv(["git", "show", "HEAD:tracked.txt"])

    assert result is not None
    assert result[0] != 0
    assert "alternate-only-payload" not in result[1]
    assert helper_marker.exists() is False


def test_rolling_value_gap_over_ninety_minutes_fails(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(module, clock, start, value_minutes=(5, 175, 180, 355, 360, 480))

    receipt = result["receipt"]
    assert receipt["max_value_gap_seconds"] == 10500
    assert receipt["rolling_value_ok"] is False
    assert receipt["pass"] is False


def test_sample_gap_over_ten_minutes_fails(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(module, clock, start, omit_samples={100, 105})

    assert result["receipt"]["max_sample_gap_seconds"] == 900
    assert result["receipt"]["coverage_ok"] is False
    assert result["receipt"]["pass"] is False


def test_operator_journal_delta_fails_trial(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(module, clock, start, operator_at=240)

    assert result["receipt"]["operator_interventions"] == 1
    assert result["receipt"]["pass"] is False


@pytest.mark.parametrize(
    "source",
    ["watch", "observation", "tasks", "prompt"],
)
def test_source_rewrite_or_truncation_breaks_checker(tmp_path, monkeypatch, source):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    if source == "prompt":
        events = module.PROMPT_ATOM_SNAPSHOT.parent / "prompt-events.jsonl"
        events.parent.mkdir(parents=True, exist_ok=True)
        events.write_text(
            json.dumps(
                {"occurrence": {"occurrence_id": "derived-1", "authority": "derived"}, "atoms": []},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    _run_trial(module, clock, start)
    if source == "watch":
        payload = bytearray(module.RECEIPT_JSONL.read_bytes())
        payload[5] = ord("X")
        module.RECEIPT_JSONL.write_bytes(bytes(payload))
    elif source == "observation":
        module.TRIAL_OBSERVATION_PATH.write_bytes(module.TRIAL_OBSERVATION_PATH.read_bytes()[:-10])
    elif source == "tasks":
        board = _load_board(module)
        board["tasks"] = board["tasks"][1:]
        module.TASKS_PATH.write_text(json.dumps(board), encoding="utf-8")
    else:
        events = module.PROMPT_ATOM_SNAPSHOT.parent / "prompt-events.jsonl"
        events.write_text("", encoding="utf-8")

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert errors


def test_post_window_self_consistent_chain_rebuild_lacks_prospective_custody(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    terminal_marker = json.loads(module.TRIAL_WINDOW_PATH.read_text())
    active_marker = terminal_marker["active_marker"]
    original_rows, parse_errors = module._jsonl_bytes(module.TRIAL_OBSERVATION_PATH.read_bytes())
    assert parse_errors == 0 and original_rows
    rebuilt = []
    previous_hash = active_marker["content_hash"]
    for original in original_rows:
        row = {key: value for key, value in original.items() if key != "content_hash"}
        row["previous_hash"] = previous_hash
        row["post_window_rebuild"] = True
        row["content_hash"] = module.canonical_hash(row)
        rebuilt.append(row)
        previous_hash = row["content_hash"]
    module.TRIAL_OBSERVATION_PATH.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rebuilt),
        encoding="utf-8",
    )
    for row in rebuilt:
        module._write_observation_custody(active_marker, row)
    monkeypatch.setattr(
        module,
        "_observation_custody_created_ns",
        lambda _path: int(clock.value.timestamp() * 1_000_000_000),
    )

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert any("observation custody creation time" in error for error in errors)


def test_terminal_proofs_are_reexecuted_during_receipt_check(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    monkeypatch.setattr(module, "_prove_terminal_event", lambda _entry: None)

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert any("proof no longer re-executes exactly" in error for error in errors)


@pytest.mark.parametrize(
    "source",
    [
        "receipt",
        "marker",
        "anchor",
        "observation",
        "watch",
        "tasks",
        "prompt_events",
        "prompt_outcomes",
        "prompt_cursor",
        "prompt_snapshot",
    ],
)
def test_byte_identical_source_symlink_redirect_fails_closed(tmp_path, monkeypatch, source):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    terminal_marker = json.loads(module.TRIAL_WINDOW_PATH.read_text())
    active_marker = terminal_marker["active_marker"]
    prompt_paths = module._prompt_paths(module.PROMPT_ATOM_SNAPSHOT)
    paths = {
        "receipt": module.TRIAL_PATH,
        "marker": module.TRIAL_WINDOW_PATH,
        "anchor": module._trial_anchor_path(active_marker),
        "observation": module.TRIAL_OBSERVATION_PATH,
        "watch": module.RECEIPT_JSONL,
        "tasks": module.TASKS_PATH,
        "prompt_events": prompt_paths["events"],
        "prompt_outcomes": prompt_paths["outcomes"],
        "prompt_cursor": prompt_paths["cursor"],
        "prompt_snapshot": prompt_paths["snapshot"],
    }
    selected = paths[source]
    preserved = selected.with_name(f"{selected.name}.preserved")
    selected.rename(preserved)
    selected.symlink_to(preserved)

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert any("symlink" in error for error in errors)


@pytest.mark.parametrize("redirect", ["ledger", "lock", "ancestor"])
def test_watch_writer_rejects_symlink_redirect_before_trial_append(tmp_path, monkeypatch, redirect):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    module.write_jsonl({"baseline": True})
    _start(module, start)
    watch_path = module.RECEIPT_JSONL
    lock_path = watch_path.with_suffix(watch_path.suffix + ".lock")
    outside = tmp_path / f"outside-{redirect}"
    outside.write_bytes(b"outside-must-not-change\n")
    observation_before = module._file_custody(module.TRIAL_OBSERVATION_PATH)

    if redirect == "ledger":
        watch_path.unlink()
        watch_path.symlink_to(outside)
        preserved_watch = outside
    elif redirect == "lock":
        lock_path.unlink()
        lock_path.symlink_to(outside)
        preserved_watch = outside
    else:
        logs = watch_path.parent
        preserved_logs = logs.with_name(f"{logs.name}-preserved")
        logs.rename(preserved_logs)
        logs.symlink_to(preserved_logs, target_is_directory=True)
        preserved_watch = preserved_logs / watch_path.name
    preserved_bytes = preserved_watch.read_bytes()

    with pytest.raises(module.TrialContractError, match="symlink"):
        module.write_jsonl({"forged": True})

    assert preserved_watch.read_bytes() == preserved_bytes
    assert module._file_custody(module.TRIAL_OBSERVATION_PATH) == observation_before


@pytest.mark.parametrize("redirect", ["ledger", "lock", "ancestor"])
def test_trial_start_rejects_watch_redirect_before_any_trial_write(tmp_path, monkeypatch, redirect):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _write_prompt_authority(module, start)
    watch_path = module.RECEIPT_JSONL
    lock_path = watch_path.with_suffix(watch_path.suffix + ".lock")
    outside = tmp_path / f"outside-start-{redirect}"
    outside.write_bytes(b"outside-must-not-change\n")
    if redirect == "ledger":
        watch_path.symlink_to(outside)
    elif redirect == "lock":
        lock_path.symlink_to(outside)
    else:
        logs = watch_path.parent
        preserved_logs = logs.with_name(f"{logs.name}-preserved")
        logs.rename(preserved_logs)
        logs.symlink_to(preserved_logs, target_is_directory=True)
    outside_bytes = outside.read_bytes()

    with pytest.raises(module.TrialContractError, match="symlink"):
        module.start_trial()

    assert outside.read_bytes() == outside_bytes
    if redirect == "ancestor":
        preserved_logs = watch_path.parent.with_name(f"{watch_path.parent.name}-preserved")
        assert not (preserved_logs / module.TRIAL_WINDOW_PATH.name).exists()
        assert not (preserved_logs / module.TRIAL_OBSERVATION_PATH.name).exists()
        assert not (preserved_logs / "overnight-trial-anchors").exists()
    else:
        assert not module.TRIAL_WINDOW_PATH.exists()
        assert not module.TRIAL_OBSERVATION_PATH.exists()
        assert not module._trial_anchor_path({"content_hash": "0" * 64}).parent.exists()


def test_evaluator_hash_binds_every_local_semantic_dependency(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    dependency_root = tmp_path / "evaluator-dependencies"
    copies = {}
    for name, source in module._evaluator_dependency_paths().items():
        destination = dependency_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copies[name] = destination
    assert {
        "cli/src/limen/intake.py",
        "cli/src/limen/jules_remote.py",
        "cli/src/limen/prompt_corpus.py",
        "scripts/autonomy-governor.py",
        "scripts/handoff-relay.py",
        "scripts/overnight-watch.py",
        "scripts/session-value-review.py",
    }.issubset(copies)
    monkeypatch.setattr(module, "_evaluator_dependency_paths", lambda: copies)
    _, result = _run_trial(module, clock, start)
    terminal_marker = json.loads(module.TRIAL_WINDOW_PATH.read_text())
    active_marker = terminal_marker["active_marker"]
    expected_hash = result["receipt"]["evaluator_hash"]
    assert module.evaluator_hash() == expected_hash

    for name, dependency in copies.items():
        original = dependency.read_bytes()
        dependency.write_bytes(original + f"\n# mutated {name}\n".encode())

        assert module.evaluator_hash() != expected_hash
        assert "trial marker evaluator changed during the window" in module._active_marker_errors(active_marker)
        ok, errors = module.check_trial_receipt()
        assert ok is False
        assert any("evaluator" in error for error in errors)

        dependency.write_bytes(original)
        assert module.evaluator_hash() == expected_hash
        assert module.check_trial_receipt() == (True, [])


def test_trial_start_rejects_unavailable_evaluator_dependency_set(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _write_prompt_authority(module, start)
    monkeypatch.setattr(module, "evaluator_hash", lambda: "unavailable")

    with pytest.raises(module.TrialContractError, match="dependency set is unavailable"):
        module.start_trial()


def test_live_terminal_projections_may_advance_after_immutable_custody(tmp_path, monkeypatch, capsys):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _, result = _run_trial(module, clock, start)
    receipt_bytes = module.TRIAL_PATH.read_bytes()
    terminal_bytes = module.TRIAL_WINDOW_PATH.read_bytes()
    terminal_sidecars = _terminal_sidecar_state(module, result["receipt"])
    later = start + dt.timedelta(hours=8, minutes=5)
    clock.value = later

    _write_prompt_authority(module, later)
    (module.LOGS / "handoff.json").write_text('{"advanced":true}\n', encoding="utf-8")
    module.write_jsonl(_watch_snapshot(later))
    _append_task_event(module, later, 1001, "done")

    repeated = module.maybe_finalize_trial()
    assert repeated and repeated["changed"] is False and repeated["receipt"] == result["receipt"]
    assert module.check_trial_receipt() == (True, [])
    assert module.main(["--finalize-trial", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["changed"] is False
    assert module.TRIAL_PATH.read_bytes() == receipt_bytes
    assert module.TRIAL_WINDOW_PATH.read_bytes() == terminal_bytes
    assert _terminal_sidecar_state(module, result["receipt"]) == terminal_sidecars


@pytest.mark.parametrize("name", ["handoff", "prompt_cursor", "prompt_snapshot"])
@pytest.mark.parametrize("mutation", ["remove", "rewrite"])
def test_terminal_custody_sidecar_removal_or_rewrite_fails(tmp_path, monkeypatch, name, mutation):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    receipt = json.loads(module.TRIAL_PATH.read_text())
    descriptor = receipt["terminal_custody"]["sources"][name]
    sidecar = module._terminal_custody_path(receipt["trial_id"], name, descriptor["digest"])

    if mutation == "remove":
        sidecar.unlink()
    else:
        sidecar.chmod(0o600)
        sidecar.write_bytes(b"rewritten\n")

    ok, errors = module.check_trial_receipt()
    assert ok is False
    assert any("custody sidecar" in error for error in errors)
    repeated = module.maybe_finalize_trial()
    assert repeated and "error" in repeated


def test_terminal_custody_fifo_fails_without_blocking_checker(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    receipt = json.loads(module.TRIAL_PATH.read_text())
    descriptor = receipt["terminal_custody"]["sources"]["handoff"]
    sidecar = module._terminal_custody_path(receipt["trial_id"], "handoff", descriptor["digest"])
    sidecar.unlink()
    module.os.mkfifo(sidecar, 0o400)

    result = subprocess.run(
        [module.sys.executable, str(SCRIPT), "--check-trial"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        env=module.os.environ.copy(),
    )

    assert result.returncode == 1
    assert "custody sidecar is not a regular file" in result.stderr


@pytest.mark.parametrize("source", ["marker", "watch", "prompt_events"])
def test_authoritative_fifo_source_fails_without_blocking_checker(tmp_path, monkeypatch, source):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    prompt_paths = module._prompt_paths(module.PROMPT_ATOM_SNAPSHOT)
    path = {
        "marker": module.TRIAL_WINDOW_PATH,
        "watch": module.RECEIPT_JSONL,
        "prompt_events": prompt_paths["events"],
    }[source]
    path.unlink()
    module.os.mkfifo(path, 0o400)

    result = subprocess.run(
        [module.sys.executable, str(SCRIPT), "--check-trial"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
        env=module.os.environ.copy(),
    )

    assert result.returncode == 1
    assert "not a regular file" in result.stderr


def test_terminal_custody_final_symlink_fails_before_read(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    receipt = json.loads(module.TRIAL_PATH.read_text())
    descriptor = receipt["terminal_custody"]["sources"]["handoff"]
    sidecar = module._terminal_custody_path(receipt["trial_id"], "handoff", descriptor["digest"])
    preserved = sidecar.with_name(f"{sidecar.name}.preserved")
    sidecar.rename(preserved)
    sidecar.symlink_to(preserved)

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert "terminal handoff custody sidecar is a symlink" in errors


def test_terminal_custody_device_is_rejected_before_read(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    monkeypatch.setattr(module, "ROOT", Path("/dev"))

    payload, mode, errors = module._read_trusted_regular_file(
        Path("/dev/null"),
        label="terminal device custody sidecar",
    )

    assert payload is None
    assert mode is None
    assert errors == ["terminal device custody sidecar is not a regular file"]


def test_terminal_custody_descriptor_cannot_be_substituted(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    receipt = json.loads(module.TRIAL_PATH.read_text())
    marker = json.loads(module.TRIAL_WINDOW_PATH.read_text())
    active_marker = marker["active_marker"]
    forged = {
        "schema_version": module.TRIAL_TERMINAL_CUSTODY_SCHEMA_VERSION,
        "sources": {},
    }
    for name in receipt["terminal_custody"]["sources"]:
        payload = f"substituted-{name}\n".encode()
        digest = module._sha256_bytes(payload)
        sidecar = module._terminal_custody_path(receipt["trial_id"], name, digest)
        sidecar.write_bytes(payload)
        sidecar.chmod(0o400)
        forged["sources"][name] = {"size": len(payload), "digest": digest}

    with pytest.raises(module.TrialContractError, match="does not match the terminal observation"):
        module.build_trial_receipt(active_marker, terminal_custody=forged)

    observations, errors = module._read_observation_chain(active_marker)
    assert errors == []
    end = module.parse_iso(active_marker["window_end"])
    assert end is not None
    bounded = [
        record
        for record in observations
        if (observed_at := module.parse_iso(record["observed_at"]))
        and observed_at <= end + dt.timedelta(seconds=module.TRIAL_EDGE_TOLERANCE_SEC)
    ]
    normalized_input = {
        "trial_id": active_marker["content_hash"],
        "baseline": active_marker["baseline"],
        "observation_hashes": [record["content_hash"] for record in bounded],
        "source_errors": [],
        "terminal_custody": forged,
        "task_window_end": bounded[-1]["task_source"],
        "task_windows": receipt["windows"],
    }
    receipt["terminal_custody"] = forged
    receipt["input_hash"] = module.canonical_hash(normalized_input)
    deterministic = {key: value for key, value in receipt.items() if key not in {"generated_at", "content_hash"}}
    receipt["content_hash"] = module.canonical_hash(deterministic)
    module._write_json_atomic(module.TRIAL_PATH, receipt)
    marker["receipt_content_hash"] = receipt["content_hash"]
    marker["receipt_input_hash"] = receipt["input_hash"]
    marker_payload = {key: value for key, value in marker.items() if key != "content_hash"}
    marker["content_hash"] = module.canonical_hash(marker_payload)
    module._write_json_atomic(module.TRIAL_WINDOW_PATH, marker)

    ok, check_errors = module.check_trial_receipt()
    assert ok is False
    assert "terminal custody descriptor does not match the terminal observation" in check_errors


def test_terminal_custody_ancestor_symlink_fails_closed(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    receipt = json.loads(module.TRIAL_PATH.read_text())
    directory = module._terminal_custody_directory(receipt["trial_id"])
    preserved = directory.with_name(f"{directory.name}-preserved")
    directory.rename(preserved)
    directory.symlink_to(preserved, target_is_directory=True)
    preserved_mode = preserved.stat().st_mode & 0o777

    ok, errors = module.check_trial_receipt()
    assert ok is False
    assert any("terminal custody directory component" in error and "symlink" in error for error in errors)
    with pytest.raises(module.TrialContractError, match="trial directory is a symlink"):
        module._preserve_terminal_custody(receipt["trial_id"], receipt["terminal_custody"])
    assert preserved.stat().st_mode & 0o777 == preserved_mode


def test_configured_terminal_root_replacement_symlink_fails_closed(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, clock = _fresh_module(tmp_path, monkeypatch, start)
    _install_proof_stubs(module, monkeypatch)
    _run_trial(module, clock, start)
    configured_root = module.TRIAL_WINDOW_PATH.parent
    preserved = configured_root.with_name(f"{configured_root.name}-preserved")
    configured_root.rename(preserved)
    configured_root.symlink_to(preserved, target_is_directory=True)

    ok, errors = module.check_trial_receipt()

    assert ok is False
    assert any("component" in error and "symlink" in error for error in errors)
    repeated = module.maybe_finalize_trial()
    assert repeated and "error" in repeated


def test_active_trial_cannot_be_replaced_or_backfilled(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    _start(module, start)

    with pytest.raises(module.TrialContractError, match="already active"):
        module.start_trial()
    with pytest.raises(SystemExit):
        module.main(["--start-trial", "--trial-start", "2026-06-30T00:00:00Z"])


def test_missing_or_backdated_prospective_anchor_fails_closed(tmp_path, monkeypatch):
    start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    module, _ = _fresh_module(tmp_path, monkeypatch, start)
    marker = _start(module, start)
    module._trial_anchor_path(marker).unlink()

    assert "prospective trial anchor is missing or malformed" in module._active_marker_errors(marker)
