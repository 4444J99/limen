import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOVERNOR = ROOT / "scripts" / "autonomy-governor.py"


def run_governor(tmp_path, *args, extra_env=None):
    return subprocess.run(
        [sys.executable, str(GOVERNOR), *args],
        capture_output=True,
        text=True,
        env={"LIMEN_ROOT": str(tmp_path), **(extra_env or {})},
    )


def test_missing_policy_defaults_to_observe(tmp_path):
    proc = run_governor(tmp_path, "mode")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "observe"
    assert (tmp_path / "logs" / "autonomy-policy.json").exists()


def test_dispatch_ok_requires_dispatch_mode_and_flag(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "observe", "dispatch_enabled": False}))
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 2
    assert "autonomy mode is observe" in proc.stdout

    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": False}))
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 2
    assert "dispatch_enabled is false" in proc.stdout


def test_dispatch_ok_blocks_when_primary_paid_lanes_are_dead(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "usage.json").write_text(
        json.dumps(
            {
                "vendors": {
                    "codex": {"health": "exhausted"},
                    "claude": {"health": "rate-limited"},
                    "jules": {"health": "exhausted"},
                    "agy": {"health": "ok"},
                }
            }
        )
    )
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 2
    assert "primary paid lanes exhausted" in proc.stdout


def test_dispatch_ok_allows_dispatch_mode_with_headroom(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "usage.json").write_text(json.dumps({"vendors": {"codex": {"health": "ok"}, "claude": {"health": "ok"}}}))
    proc = run_governor(tmp_path, "dispatch-ok")
    assert proc.returncode == 0
    assert "dispatch allowed" in proc.stdout


def _fake_gh(tmp_path, script_body):
    """Install a fake `gh` on PATH so the marker autoclear's subprocess calls are hermetic."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text("#!/bin/bash\n" + script_body)
    gh.chmod(0o755)
    return bin_dir


def run_governor_with_gh(tmp_path, gh_body, *args):
    bin_dir = _fake_gh(tmp_path, gh_body)
    return subprocess.run(
        [sys.executable, str(GOVERNOR), *args],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(tmp_path),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "LIMEN_AUTONOMY_MARKER_RECHECK_SECS": "0",
        },
    )


def test_marker_pr_line_autoclears_when_that_pr_merged(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "AUTONOMY_PAUSED").write_text("reason: safety gate\nowner: manual/hand-written-label-20260714\npr: 1036\n")
    # fake gh: `pr view 1036 --json state` -> MERGED; the owner --head search would find nothing
    body = 'if [ "$1" = "pr" ] && [ "$2" = "view" ]; then echo \'{"state":"MERGED"}\'; else echo "[]"; fi'
    proc = run_governor_with_gh(tmp_path, body, "mode")
    assert proc.stdout.strip() == "dispatch"
    assert not (logs / "AUTONOMY_PAUSED").exists()


def test_marker_hand_written_owner_alone_stays_paused(tmp_path):
    # The 2026-07-15 recurrence: owner label matches no branch; without a pr: line the
    # autoclear must stay fail-closed.
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "AUTONOMY_PAUSED").write_text("reason: safety gate\nowner: manual/hand-written-label-20260714\n")
    body = 'echo "[]"'
    proc = run_governor_with_gh(tmp_path, body, "mode")
    assert proc.stdout.strip() == "paused"
    assert (logs / "AUTONOMY_PAUSED").exists()


def test_marker_pr_line_unmerged_stays_paused(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "AUTONOMY_PAUSED").write_text("reason: safety gate\npr: 1036\n")
    body = 'if [ "$1" = "pr" ] && [ "$2" = "view" ]; then echo \'{"state":"OPEN"}\'; else echo "[]"; fi'
    proc = run_governor_with_gh(tmp_path, body, "mode")
    assert proc.stdout.strip() == "paused"
    assert (logs / "AUTONOMY_PAUSED").exists()


# ── pause-release COMPLETION (the deadly-embrace fix, 2026-07-15) ──────────────────────────────
# A PR-owned marker (owner:/pr: identity + release_predicate declares the merge + no merge
# prohibition) gets its release performed by the governor: merge-policy CLEARED → head-pinned
# squash. Operator pauses are structurally ineligible. Every ambiguity stays paused.

OPERATOR_MARKER = (
    "reason: operator requested a safe restart and a study interval\n"
    "owner_surface: work/next-autonomous-epoch continuation capsule\n"
    "release_predicate: operator has restarted, studied the receipts, and explicitly resumes\n"
    "prohibitions: no dispatch, merge, rebase, PR mutation, worktree reclaim\n"
)

PR_OWNED_MARKER = (
    "reason: integration drain\nowner: codex/some-release-branch\nrelease_predicate: the drain PR is merged into main\n"
)

LOGGING_GH = """echo "$*" >> "$GH_LOG"
case "$*" in
  *"--state merged"*) echo "[]" ;;
  *"--state open"*) echo '[{"number":7}]' ;;
  *"pr merge 7"*) exit 0 ;;
  *"pr view 7 --json state"*) echo '{"state":"MERGED"}' ;;
  *) echo "[]" ;;
esac
"""

TWO_OPEN_GH = LOGGING_GH.replace("'[{\"number\":7}]'", '\'[{"number":7},{"number":8}]\'')

CLEARED_POLICY = (
    'echo "VERDICT: CLEARED — ok"\necho "MERGE-HEAD: abc123 (use gh pr merge --match-head-commit abc123)"\nexit 0\n'
)
HOLD_POLICY = 'echo "VERDICT: HOLD — checks running"\nexit 2\n'


def run_governor_completion(tmp_path, gh_body, policy_body, *args, extra_env=None):
    bin_dir = _fake_gh(tmp_path, gh_body)
    policy = bin_dir / "policy"
    policy.write_text("#!/bin/bash\n" + policy_body)
    policy.chmod(0o755)
    env = {
        "LIMEN_ROOT": str(tmp_path),
        "PATH": f"{bin_dir}:/usr/bin:/bin",
        "LIMEN_AUTONOMY_MARKER_RECHECK_SECS": "0",
        "LIMEN_MERGE_POLICY_BIN": str(policy),
        "GH_LOG": str(tmp_path / "gh.log"),
    }
    env.update(extra_env or {})
    return subprocess.run([sys.executable, str(GOVERNOR), *args], capture_output=True, text=True, env=env)


def _seed_pause(tmp_path, marker_text):
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "autonomy-policy.json").write_text(json.dumps({"mode": "dispatch", "dispatch_enabled": True}))
    (logs / "AUTONOMY_PAUSED").write_text(marker_text)
    return logs


def _gh_log(tmp_path):
    log = tmp_path / "gh.log"
    return log.read_text() if log.exists() else ""


def test_operator_marker_is_never_touched(tmp_path):
    logs = _seed_pause(tmp_path, OPERATOR_MARKER)
    proc = run_governor_completion(tmp_path, LOGGING_GH, CLEARED_POLICY, "mode")
    assert proc.stdout.strip() == "paused"
    assert (logs / "AUTONOMY_PAUSED").exists()
    assert _gh_log(tmp_path) == ""  # owner_surface: is not owner: — gh is never even consulted


def test_pr_owned_marker_completes_release(tmp_path):
    logs = _seed_pause(tmp_path, PR_OWNED_MARKER)
    proc = run_governor_completion(tmp_path, LOGGING_GH, CLEARED_POLICY, "mode")
    assert proc.stdout.strip() == "dispatch"
    assert not (logs / "AUTONOMY_PAUSED").exists()
    assert "pr merge 7 --squash --match-head-commit abc123" in _gh_log(tmp_path)
    assert "completed pause release" in proc.stderr


def test_pr_owned_marker_stays_paused_on_hold(tmp_path):
    logs = _seed_pause(tmp_path, PR_OWNED_MARKER)
    proc = run_governor_completion(tmp_path, LOGGING_GH, HOLD_POLICY, "mode")
    assert proc.stdout.strip() == "paused"
    assert (logs / "AUTONOMY_PAUSED").exists()
    assert "pr merge" not in _gh_log(tmp_path)


def test_ambiguity_battery_stays_paused(tmp_path):
    cases = [
        # release_predicate does not declare the merge
        (PR_OWNED_MARKER.replace("the drain PR is merged into main", "operator review complete"), LOGGING_GH, None),
        # prohibitions forbid merging even with a PR identity
        (PR_OWNED_MARKER + "prohibitions: no merge until the operator resumes\n", LOGGING_GH, None),
        # owner branch resolves to two open PRs
        (PR_OWNED_MARKER, TWO_OPEN_GH, None),
        # the valve is off
        (PR_OWNED_MARKER, LOGGING_GH, {"LIMEN_AUTONOMY_MARKER_AUTOMERGE": "0"}),
    ]
    for i, (marker, gh_body, extra_env) in enumerate(cases):
        case_dir = tmp_path / f"case{i}"
        case_dir.mkdir()
        logs = _seed_pause(case_dir, marker)
        proc = run_governor_completion(case_dir, gh_body, CLEARED_POLICY, "mode", extra_env=extra_env)
        assert proc.stdout.strip() == "paused", f"case {i}: {proc.stdout} {proc.stderr}"
        assert (logs / "AUTONOMY_PAUSED").exists(), f"case {i}"
        assert "pr merge" not in _gh_log(case_dir), f"case {i}"


def test_throttle_bounds_the_completion_attempt(tmp_path):
    _seed_pause(tmp_path, PR_OWNED_MARKER)
    extra = {"LIMEN_AUTONOMY_MARKER_RECHECK_SECS": "10000"}
    run_governor_completion(tmp_path, LOGGING_GH, HOLD_POLICY, "mode", extra_env=extra)
    first = _gh_log(tmp_path).count("\n")
    proc = run_governor_completion(tmp_path, LOGGING_GH, HOLD_POLICY, "mode", extra_env=extra)
    assert proc.stdout.strip() == "paused"
    assert _gh_log(tmp_path).count("\n") == first  # second call throttled — zero new gh reads


# ── finite maintenance-window lifecycle (#1578) ────────────────────────────────


def _seed_maintenance_policy(tmp_path, *, expires_at):
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    policy = {
        "mode": "observe",
        "dispatch_enabled": False,
        "maintenance_window": {
            "owner": "whole-estate-custody-reset",
            "expires_at": expires_at,
            "resume_predicate": "host admission valid; live root exact and clean",
        },
    }
    (logs / "autonomy-policy.json").write_text(json.dumps(policy))
    return logs


def test_explicit_observe_without_maintenance_window_is_unchanged(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(
        json.dumps({"mode": "observe", "dispatch_enabled": False, "reason": "explicit operator observation"})
    )
    proc = run_governor(tmp_path, "mode")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "observe"
    assert not (logs / "autonomy-maintenance-blocker.json").exists()


def test_unexpired_maintenance_window_stays_observe(tmp_path):
    logs = _seed_maintenance_policy(tmp_path, expires_at="2999-01-01T00:00:00Z")
    proc = run_governor(tmp_path, "mode")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "observe"
    assert not (logs / "autonomy-maintenance-blocker.json").exists()


def test_expired_maintenance_window_fails_loud_with_stable_receipt(tmp_path):
    logs = _seed_maintenance_policy(tmp_path, expires_at="2000-01-01T00:00:00Z")
    proc = run_governor(tmp_path, "mode")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "paused"

    receipt = logs / "autonomy-maintenance-blocker.json"
    blocker = json.loads(receipt.read_text())
    # A prose resume_predicate can NEVER auto-complete — distinct from the generic "expired"
    # a window with real, still-unsatisfied clauses gets (see test_an_unsatisfied_clause_is_...
    # and test_prose_predicate_state_differs_from_a_still_waiting_clause below).
    assert blocker["state"] == "expired-unrunnable-predicate"
    assert blocker["owner"] == "whole-estate-custody-reset"
    assert blocker["resume_predicate"] == "host admission valid; live root exact and clean"
    first = receipt.read_bytes()

    second = run_governor(tmp_path, "mode")
    assert second.returncode == 0
    assert second.stdout.strip() == "paused"
    assert receipt.read_bytes() == first

    explained = run_governor(tmp_path, "explain")
    assert explained.returncode == 0
    payload = json.loads(explained.stdout)
    assert payload["mode"] == "paused"
    assert payload["maintenanceBlocker"]["state"] == "expired-unrunnable-predicate"
    assert payload["maintenanceBlockerReceipt"] == str(receipt)


def test_malformed_maintenance_expiry_fails_closed(tmp_path):
    logs = _seed_maintenance_policy(tmp_path, expires_at="not-a-timestamp")
    proc = run_governor(tmp_path, "mode")
    assert proc.returncode == 0
    assert proc.stdout.strip() == "paused"
    blocker = json.loads((logs / "autonomy-maintenance-blocker.json").read_text())
    assert blocker["state"] == "invalid-expiry"


def test_non_object_maintenance_window_fails_closed(tmp_path):
    for index, malformed in enumerate((None, [], "until later")):
        case = tmp_path / f"case-{index}"
        logs = case / "logs"
        logs.mkdir(parents=True)
        (logs / "autonomy-policy.json").write_text(
            json.dumps({"mode": "observe", "dispatch_enabled": False, "maintenance_window": malformed})
        )
        proc = run_governor(case, "mode")
        assert proc.returncode == 0
        assert proc.stdout.strip() == "paused"
        blocker = json.loads((logs / "autonomy-maintenance-blocker.json").read_text())
        assert blocker["state"] == "invalid-window"


# ── the expired maintenance window must be able to complete itself ────────────────
#
# The deadly-embrace fix `_try_complete_release` gives MARKER-owned pauses was never extended to
# WINDOW-owned ones. Measured 2026-07-31: a four-hour window that expired 2026-07-22 had held the
# estate for nine days, and its own resume predicate required "live root exact origin/main" — a
# state produced ONLY by sync-release.sh, which ran solely when NOT paused. The halt could not
# clear itself by construction.


def _expired_window(tmp_path, predicate, expires="2026-07-22T03:14:24Z"):
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "autonomy-policy.json").write_text(
        json.dumps(
            {
                "mode": "observe",
                "dispatch_enabled": False,
                "maintenance_window": {
                    "started_at": "2026-07-21T23:14:24Z",
                    "expires_at": expires,
                    "owner": "whole-estate-custody-reset",
                    "resume_predicate": predicate,
                },
            }
        )
    )
    return logs


def test_a_prose_resume_predicate_never_auto_completes(tmp_path):
    """Back-compat, and the whole diagnosis: a sentence cannot fire. This is the live policy's
    exact shape, and it must keep behaving precisely as it does today — blocked until a human
    edits it. Only a list opts in."""
    _expired_window(tmp_path, "host admission valid; live root exact origin/main and clean")
    assert run_governor(tmp_path, "mode").stdout.strip() == "paused"


def test_an_unsatisfied_clause_is_named_rather_than_merely_expired(tmp_path):
    """A halt that says only 'expired without a recorded resume' is indistinguishable from a halt
    with no way out. Naming the failing clause is the difference between a halt and a to-do list."""
    _expired_window(tmp_path, ["true", "false # the clause that blocks", "true"])
    assert run_governor(tmp_path, "mode").stdout.strip() == "paused"
    blocker = json.loads(run_governor(tmp_path, "explain").stdout)["maintenanceBlocker"]
    assert [c["clause"] for c in blocker["unsatisfied_clauses"]] == ["false # the clause that blocks"]


def test_all_clauses_satisfied_resumes_restores_dispatch_and_records_both(tmp_path):
    """The 15-day incident's missing half: satisfying the resume predicate used to clear only
    the BLOCKER while `mode: observe` stood forever. A resumed finite window now restores
    dispatch, moves the window to completed_maintenance_window, and leaves two receipts."""
    logs = _expired_window(tmp_path, ["true", "echo all-clear"])
    assert run_governor(tmp_path, "mode").stdout.strip() == "dispatch"

    receipt = json.loads((logs / "autonomy-maintenance-resume.json").read_text())
    assert receipt["window_expires_at"] == "2026-07-22T03:14:24Z"
    assert all(c["passed"] for c in receipt["clauses"])

    policy = json.loads((logs / "autonomy-policy.json").read_text())
    assert policy["mode"] == "dispatch" and policy["dispatch_enabled"] is True
    assert "maintenance_window" not in policy
    assert policy["completed_maintenance_window"]["expires_at"] == "2026-07-22T03:14:24Z"
    restore = json.loads((logs / "autonomy-policy-restore.json").read_text())
    assert restore["window_expires_at"] == "2026-07-22T03:14:24Z"

    # idempotent: the rewritten policy answers the next read without re-running anything
    assert run_governor(tmp_path, "mode").stdout.strip() == "dispatch"


def test_a_recorded_resume_does_not_cover_a_different_window(tmp_path):
    """A resume is scoped to the window it satisfied. Otherwise one lift would silently license
    every future maintenance window, which is the opposite of a finite lifecycle boundary."""
    logs = _expired_window(tmp_path, ["true"])
    assert run_governor(tmp_path, "mode").stdout.strip() == "dispatch"

    _expired_window(tmp_path, ["false"], expires="2026-07-25T00:00:00Z")
    (logs / ".autonomy-clause-cache.json").unlink(missing_ok=True)
    assert run_governor(tmp_path, "mode").stdout.strip() == "paused"


def test_restore_manual_window_stays_observe_after_resume(tmp_path):
    logs = _expired_window(tmp_path, ["true"])
    policy = json.loads((logs / "autonomy-policy.json").read_text())
    policy["maintenance_window"]["restore"] = "manual"
    (logs / "autonomy-policy.json").write_text(json.dumps(policy))
    assert run_governor(tmp_path, "mode").stdout.strip() == "observe"
    persisted = json.loads((logs / "autonomy-policy.json").read_text())
    assert persisted["mode"] == "observe" and "maintenance_window" in persisted


def test_pause_marker_blocks_restore(tmp_path):
    logs = _expired_window(tmp_path, ["true"])
    (logs / "AUTONOMY_PAUSED").write_text("paused: operator hold\n")
    assert run_governor(tmp_path, "mode").stdout.strip() == "paused"
    persisted = json.loads((logs / "autonomy-policy.json").read_text())
    assert persisted["mode"] == "observe" and "maintenance_window" in persisted


def test_restore_kill_switch_preserves_old_contract(tmp_path):
    logs = _expired_window(tmp_path, ["true"])
    proc = run_governor(tmp_path, "mode", extra_env={"LIMEN_AUTONOMY_WINDOW_RESTORE": "0"})
    assert proc.stdout.strip() == "observe"
    persisted = json.loads((logs / "autonomy-policy.json").read_text())
    assert persisted["mode"] == "observe" and "maintenance_window" in persisted


def test_indefinite_observe_is_never_auto_flipped(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir(exist_ok=True)
    (logs / "autonomy-policy.json").write_text(
        json.dumps({"mode": "observe", "dispatch_enabled": False, "reason": "operator observe"})
    )
    # even a lingering resume receipt from some prior window cannot flip an indefinite observe
    (logs / "autonomy-maintenance-resume.json").write_text(json.dumps({"window_expires_at": "2026-07-22T03:14:24Z"}))
    assert run_governor(tmp_path, "mode").stdout.strip() == "observe"


def test_unwritable_policy_means_no_flip(tmp_path):
    logs = _expired_window(tmp_path, ["true"])
    policy_path = logs / "autonomy-policy.json"
    policy_path.chmod(0o444)
    try:
        assert run_governor(tmp_path, "mode").stdout.strip() == "observe"
    finally:
        policy_path.chmod(0o644)


def test_an_unrunnable_clause_fails_closed(tmp_path):
    """Fail-CLOSED everywhere, matching _try_complete_release: a broken predicate leaves the
    blocker standing rather than being read as satisfied."""
    _expired_window(tmp_path, ["definitely-not-a-real-command-xyz"])
    assert run_governor(tmp_path, "mode").stdout.strip() == "paused"


def test_prose_predicate_state_differs_from_a_still_waiting_clause(tmp_path):
    """The two ways a window stays paused past expiry are not the same failure: one is
    unrunnable and needs a human edit no matter how long anyone waits; the other has a real
    clause that just hasn't passed yet. Collapsing both into 'expired' is exactly what let a
    prose predicate hold the estate for 15 days indistinguishably from a window still waiting
    on legitimate conditions."""
    (tmp_path / "prose").mkdir()
    prose_logs = _expired_window(tmp_path / "prose", "host admission valid; live root clean")
    run_governor(tmp_path / "prose", "mode")
    prose_blocker = json.loads((prose_logs / "autonomy-maintenance-blocker.json").read_text())
    assert prose_blocker["state"] == "expired-unrunnable-predicate"

    (tmp_path / "waiting").mkdir()
    waiting_logs = _expired_window(tmp_path / "waiting", ["true", "false # still pending", "true"])
    run_governor(tmp_path / "waiting", "mode")
    waiting_blocker = json.loads((waiting_logs / "autonomy-maintenance-blocker.json").read_text())
    assert waiting_blocker["state"] == "expired"
    assert waiting_blocker["unsatisfied_clauses"]


def test_acting_subcommand_reflects_blocker_presence(tmp_path):
    """The omega core.autonomy-acting rung's predicate: exit 0 with no blocker, exit 1 with one,
    never the ambiguous 'paused' string `mode` prints for both a short pause and a stale one."""
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "autonomy-policy.json").write_text(
        json.dumps({"mode": "observe", "dispatch_enabled": False, "reason": "no window"})
    )
    clear = run_governor(tmp_path, "acting")
    assert clear.returncode == 0

    _expired_window(tmp_path, "host admission valid; live root clean")
    blocked = run_governor(tmp_path, "acting")
    assert blocked.returncode == 1
    assert "expired-unrunnable-predicate" in blocked.stdout
