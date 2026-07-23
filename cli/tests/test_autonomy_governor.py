import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GOVERNOR = ROOT / "scripts" / "autonomy-governor.py"


def run_governor(tmp_path, *args):
    return subprocess.run(
        [sys.executable, str(GOVERNOR), *args],
        capture_output=True,
        text=True,
        env={"LIMEN_ROOT": str(tmp_path)},
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
