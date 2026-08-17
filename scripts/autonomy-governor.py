#!/usr/bin/env python3
"""Small policy gate for Limen autonomy.

The heartbeat is allowed to exist without being allowed to spend. This file is the
single local switch:

  mode=paused   -> exit immediately
  mode=observe  -> telemetry/status only, no queue mutation or dispatch
  mode=dispatch -> full conductor loop, still subject to usage health gates
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
POLICY_PATH = ROOT / "logs" / "autonomy-policy.json"
MAINTENANCE_BLOCKER_PATH = ROOT / "logs" / "autonomy-maintenance-blocker.json"
PAUSE_MARKER = ROOT / "logs" / "AUTONOMY_PAUSED"
MARKER_RECHECK_STAMP = ROOT / "logs" / ".autonomy-marker-recheck"
MAINTENANCE_RESUME_PATH = ROOT / "logs" / "autonomy-maintenance-resume.json"
MAINTENANCE_CLAUSE_CACHE = ROOT / "logs" / ".autonomy-clause-cache.json"
VALID_MODES = {"paused", "observe", "dispatch"}

DEFAULT_POLICY = {
    "mode": "observe",
    "dispatch_enabled": False,
    "reason": "Default after 2026-06-20 usage audit: observe safely; dispatch requires an explicit policy change.",
}


def load_policy() -> dict[str, Any]:
    if not POLICY_PATH.exists():
        POLICY_PATH.parent.mkdir(parents=True, exist_ok=True)
        POLICY_PATH.write_text(json.dumps(DEFAULT_POLICY, indent=2) + "\n")
        return dict(DEFAULT_POLICY)
    try:
        policy = json.loads(POLICY_PATH.read_text())
    except Exception:
        return {"mode": "paused", "dispatch_enabled": False, "reason": "invalid autonomy-policy.json"}
    if not isinstance(policy, dict):
        return {"mode": "paused", "dispatch_enabled": False, "reason": "autonomy policy must be an object"}
    mode = str(policy.get("mode", "observe")).lower()
    if mode not in VALID_MODES:
        policy["mode"] = "paused"
        policy["dispatch_enabled"] = False
        policy["reason"] = f"invalid mode {mode!r}"
    return policy


def _parse_timestamp(value: Any) -> datetime.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed.astimezone(datetime.timezone.utc)


def maintenance_blocker(policy: dict[str, Any], *, now: datetime.datetime | None = None) -> dict[str, Any] | None:
    """Return a stable blocker when a finite observe window expired or is malformed.

    A maintenance window is an executable lifecycle boundary, not decoration. Before its
    expiry the requested observe mode remains intact. After expiry the governor fails loudly
    toward paused until the declared resume predicate is satisfied; once it is,
    _try_restore_dispatch flips the policy back to dispatch with a receipt (unless the window
    declares `restore: manual`). Ordinary indefinite observe policies are unchanged — only a
    finite window with a passing runnable predicate self-restores.
    """
    if str(policy.get("mode", "")).lower() != "observe":
        return None
    if "maintenance_window" not in policy:
        return None
    window = policy["maintenance_window"]
    if not isinstance(window, dict):
        return {
            "schema_version": "limen.autonomy-maintenance-blocker.v1",
            "state": "invalid-window",
            "reason": "finite autonomy maintenance_window must be an object",
            "owner": "autonomy-policy-owner",
            "expires_at": "",
            "resume_predicate": "",
            "policy_path": str(POLICY_PATH),
            "next_command": "python3 scripts/autonomy-governor.py explain",
        }

    expires_raw = window.get("expires_at")
    expires = _parse_timestamp(expires_raw)
    unsatisfied: list[dict[str, str]] = []
    if expires is None:
        state = "invalid-expiry"
        reason = "finite autonomy maintenance window has an invalid expires_at value"
    else:
        observed = now or datetime.datetime.now(datetime.timezone.utc)
        if observed.astimezone(datetime.timezone.utc) <= expires:
            return None
        state = "expired"
        reason = "finite autonomy maintenance window expired without a recorded resume"
        completed, results = _try_complete_maintenance_window(window)
        if completed:
            return None
        unsatisfied = [{"clause": r["clause"], "detail": r["detail"]} for r in results if not r["passed"]]
        if not _clauses(window):
            # A prose sentence (or an empty/blank clause list) is not "still waiting on a
            # condition" — it is UNRUNNABLE and will NEVER auto-complete, no matter how long the
            # estate waits. That is a categorically different failure than a window with real
            # clauses that simply haven't passed yet, and the generic "expired" state made the two
            # indistinguishable. Measured 2026-07-21 → 08-05: this exact shape (a prose
            # resume_predicate) held the estate paused for 15 days with no signal louder than
            # "expired" to tell the two apart.
            state = "expired-unrunnable-predicate"
            reason = (
                "finite autonomy maintenance window expired and its resume_predicate can never "
                "self-complete (prose sentence or empty clause list) — a human must convert it to "
                "a runnable list of shell clauses"
            )

    predicate = window.get("resume_predicate")
    return {
        "schema_version": "limen.autonomy-maintenance-blocker.v1",
        "state": state,
        "reason": reason,
        "owner": str(window.get("owner") or "autonomy-policy-owner"),
        "expires_at": str(expires_raw or ""),
        "resume_predicate": predicate if isinstance(predicate, list) else str(predicate or ""),
        "unsatisfied_clauses": unsatisfied,
        "policy_path": str(POLICY_PATH),
        "next_command": "python3 scripts/autonomy-governor.py explain",
    }


def _clauses(window: dict[str, Any]) -> list[str]:
    """The resume predicate as RUNNABLE clauses, or [] when it is prose.

    Back-compatible by construction: a string `resume_predicate` is a sentence, and a sentence
    cannot fire. It keeps today's behaviour exactly — blocked until a human edits the policy —
    so no existing window changes meaning. Only a list opts into self-completion.
    """
    predicate = window.get("resume_predicate")
    if not isinstance(predicate, list):
        return []
    return [str(c) for c in predicate if str(c).strip()]


def _run_clause(command: str) -> tuple[bool, str]:
    """(passed, detail). Fail CLOSED: unrunnable, timed out, or non-zero all count as unsatisfied."""
    try:
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120, check=False, cwd=str(ROOT)
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"did not run: {exc}"
    detail = (proc.stdout.strip() or proc.stderr.strip() or "").splitlines()
    return proc.returncode == 0, (detail[-1][:300] if detail else f"exit {proc.returncode}")


def _clause_cache(window: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Recent clause results for THIS window, or None when the cache is stale/absent/foreign.

    current_mode() is the chokepoint the heartbeat AND every dispatch admission read, so it runs
    many times a minute. The clauses are real work — a git fetch-state read, a bash plist render,
    a host-pressure probe — and re-running them on every read would turn a status query into
    sustained load on a 16GB host that already logs jetsam kills. `_marker_owner_merged` throttles
    its `gh` calls for exactly this reason; this mirrors that bound.
    """
    try:
        cached = json.loads(MAINTENANCE_CLAUSE_CACHE.read_text())
        age = time.time() - MAINTENANCE_CLAUSE_CACHE.stat().st_mtime
    except (OSError, ValueError):
        return None
    try:
        window_secs = float(os.environ.get("LIMEN_AUTONOMY_CLAUSE_RECHECK_SECS", "300"))
    except ValueError:
        window_secs = 300.0
    if age >= window_secs:
        return None
    if not isinstance(cached, dict) or cached.get("window_expires_at") != str(window.get("expires_at") or ""):
        return None
    results = cached.get("results")
    return results if isinstance(results, list) else None


def _resume_receipt_matches(window: dict[str, Any]) -> bool:
    """True iff a recorded resume already covers THIS window (matched on expires_at)."""
    try:
        receipt = json.loads(MAINTENANCE_RESUME_PATH.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(receipt, dict) and receipt.get("window_expires_at") == str(window.get("expires_at") or "")


def _try_complete_maintenance_window(window: dict[str, Any]) -> tuple[bool, list[dict[str, Any]]]:
    """COMPLETE an expired maintenance window instead of merely reporting it — the same
    deadly-embrace fix `_try_complete_release` applies to marker-owned pauses, one blocker over.

    That fix was never extended to WINDOW-owned pauses, and the window in force carried no marker
    at all, so the single self-completing path in this file could not fire. Measured 2026-07-31:
    a four-hour window that expired 2026-07-22 had held the estate for nine days, and its own
    resume predicate required "live root exact origin/main" — a state produced ONLY by
    sync-release.sh, which ran solely when NOT paused. The halt could not clear itself by
    construction, and no amount of waiting was ever going to change that.

    Fail-CLOSED everywhere: prose predicate, empty clause list, any clause non-zero, any exception
    — all leave the blocker standing. True only when every declared clause exits 0, and the resume
    is then RECORDED (a receipt keyed to this window) rather than silently assumed, so the next
    read is idempotent and the reason a window lifted is auditable afterwards.
    """
    if _resume_receipt_matches(window):
        return True, []
    clauses = _clauses(window)
    if not clauses:
        return False, []  # prose, or nothing declared — never auto-completes

    results = _clause_cache(window)
    if results is None:
        results = []
        for command in clauses:
            passed, detail = _run_clause(command)
            results.append({"clause": command, "passed": passed, "detail": detail})
            if not passed:
                break  # first failure decides; do not pay for the rest
        try:
            MAINTENANCE_CLAUSE_CACHE.parent.mkdir(parents=True, exist_ok=True)
            MAINTENANCE_CLAUSE_CACHE.write_text(
                json.dumps(
                    {"window_expires_at": str(window.get("expires_at") or ""), "results": results},
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
        except OSError:
            pass

    if len(results) != len(clauses) or not all(r.get("passed") for r in results):
        return False, results

    receipt = {
        "schema_version": "limen.autonomy-maintenance-resume.v1",
        "window_expires_at": str(window.get("expires_at") or ""),
        "owner": str(window.get("owner") or "autonomy-policy-owner"),
        "clauses": results,
        "resumed_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        MAINTENANCE_RESUME_PATH.parent.mkdir(parents=True, exist_ok=True)
        MAINTENANCE_RESUME_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    except OSError:
        return False, results  # a resume that cannot be recorded did not happen
    print(
        f"autonomy-governor: maintenance window resumed — {len(results)} clause(s) satisfied",
        file=sys.stderr,
    )
    try:
        MAINTENANCE_BLOCKER_PATH.unlink()
    except OSError:
        pass
    return True, results


def _persist_maintenance_blocker(blocker: dict[str, Any]) -> None:
    """Write the stable owner receipt once; repeated governor reads are byte-idempotent."""
    rendered = json.dumps(blocker, indent=2, sort_keys=True) + "\n"
    try:
        MAINTENANCE_BLOCKER_PATH.parent.mkdir(parents=True, exist_ok=True)
        if MAINTENANCE_BLOCKER_PATH.exists() and MAINTENANCE_BLOCKER_PATH.read_text() == rendered:
            return
        MAINTENANCE_BLOCKER_PATH.write_text(rendered)
    except OSError:
        # Admission still fails closed through current_mode even when the receipt path is unwritable.
        pass


def usage_dead_lanes() -> set[str]:
    path = ROOT / "logs" / "usage.json"
    try:
        vendors = (json.loads(path.read_text()) or {}).get("vendors", {})
    except Exception:
        return set()
    return {
        name
        for name, info in vendors.items()
        if isinstance(info, dict) and info.get("health") in {"exhausted", "rate-limited"}
    }


def _marker_fields(marker: Path) -> dict[str, str]:
    """Parse the marker's structured lines by strict ``<name>:`` prefix — an ``owner_surface:``
    line never reads as ``owner:`` (the 2026-07-15 operator study-pause relies on exactly that)."""
    try:
        lines = marker.read_text().splitlines()
    except OSError:
        return {}

    def field(name: str) -> str:
        return next(
            (ln.split(":", 1)[1].strip() for ln in lines if ln.strip().startswith(f"{name}:")),
            "",
        )

    # `expires_at`/`source_of_intent`/`authorised_by`/`class` joined this set with the pause-authority
    # work: the parser dropped every field it did not name, so an `expires_at:` line was written by
    # pause.py and then silently discarded here — the expiry read as absent and the marker bound
    # forever. Consumers index by name, so widening the set is additive.
    return {
        name: field(name)
        for name in (
            "class",
            "owner",
            "pr",
            "repo",
            "prohibitions",
            "release_predicate",
            "expires_at",
            "source_of_intent",
            "authorised_by",
        )
    }


def _pr_owned_pause(fields: dict[str, str]) -> bool:
    """True iff the marker DECLARES its own release to be the merge of an identifiable PR.

    Every clause fails toward check-only (today's behavior). An operator pause is structurally
    ineligible twice over: its prohibitions mention merge, and it carries no ``owner:``/``pr:``
    identity (``owner_surface:`` does not parse as ``owner:``).
    """
    if os.environ.get("LIMEN_AUTONOMY_MARKER_AUTOMERGE", "1") != "1":
        return False
    if not (fields.get("owner") or fields.get("pr")):
        return False
    if "merge" not in fields.get("release_predicate", "").lower():
        return False  # the marker's author did not declare merge as the release — never infer it
    if "merge" in fields.get("prohibitions", "").lower():
        return False  # the marker forbids merging — the governor is bound like everyone else
    return True


def _resolve_release_pr(fields: dict[str, str]) -> str:
    """The marker's release PR number: an explicit ``pr:`` line, else the single OPEN PR whose
    head is the ``owner:`` branch. Zero or multiple candidates → '' (ambiguity → check-only)."""
    pr_match = re.search(r"(\d+)\s*$", fields.get("pr", ""))
    if pr_match:
        return pr_match.group(1)
    owner = fields.get("owner", "")
    if not owner:
        return ""
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--head", owner, "--state", "open", "--json", "number"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if proc.returncode != 0:
        return ""
    try:
        rows = json.loads(proc.stdout)
    except ValueError:
        return ""
    if isinstance(rows, list) and len(rows) == 1 and isinstance(rows[0], dict) and rows[0].get("number"):
        return str(rows[0]["number"])
    return ""


def _try_complete_release(fields: dict[str, str]) -> bool:
    """COMPLETE a PR-owned pause instead of merely checking it — the deadly-embrace fix.

    A pause whose release predicate is "the owner PR merges" used to wait on an organ that lives
    INSIDE the paused beat (merge-drain runs on the drain voice; the heartbeat exits when paused),
    so a session or human always had to babysit the merge (the 2026-07-15 endless-watcher
    incident). Here the governor itself runs the ONE merge predicate (scripts/merge-policy.sh)
    and, only on CLEARED (exit 0), performs the squash merge head-pinned to the predicate's
    MERGE-HEAD line. Fail-CLOSED everywhere: HOLD/BLOCKED/broken-predicate/failed-merge all
    return False and the estate stays paused for the next throttled cycle. True only after gh
    re-confirms the PR is MERGED — the caller then unlinks the marker.
    """
    if not _pr_owned_pause(fields):
        return False
    pr = _resolve_release_pr(fields)
    if not pr:
        return False
    policy = os.environ.get("LIMEN_MERGE_POLICY_BIN") or str(Path(__file__).resolve().parent / "merge-policy.sh")
    try:
        verdict = subprocess.run(
            ["bash", policy, pr], capture_output=True, text=True, timeout=90, check=False, cwd=str(ROOT)
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if verdict.returncode != 0:
        return False  # HOLD (2) / BLOCKED (3) / broken predicate — stay paused, retry next window
    merge_cmd = ["gh", "pr", "merge", pr, "--squash"]
    sha = re.search(r"^MERGE-HEAD: ([0-9a-f]+)", verdict.stdout, re.M)
    if sha:
        merge_cmd += ["--match-head-commit", sha.group(1)]
    try:
        if (
            subprocess.run(merge_cmd, capture_output=True, text=True, timeout=90, check=False, cwd=str(ROOT)).returncode
            != 0
        ):
            return False
        confirm = subprocess.run(
            ["gh", "pr", "view", pr, "--json", "state"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    try:
        merged = confirm.returncode == 0 and str(json.loads(confirm.stdout).get("state")) == "MERGED"
    except ValueError:
        return False
    if merged:
        print(
            f"autonomy-governor: completed pause release — merge-policy CLEARED and PR #{pr} squash-merged",
            file=sys.stderr,
        )
    return merged


def _marker_owner_merged(marker: Path) -> bool:
    """True iff the pause marker's release PR merged — via ``pr:`` line or ``owner:`` branch.

    A stale "integration drain" marker whose owner PR already merged is the exact 21h-freeze
    incident (2026-07-10, owner codex/dynamic-routing-closeout-20260710, PR #921 merged the next
    morning): under launchd KeepAlive the beat respawn-spins on ``return "paused"`` forever
    because nothing clears the marker. This lets current_mode() — the single chokepoint the
    heartbeat and dispatch admission both read — clear it within one cycle of the merge.

    When the release PR is NOT yet merged, a PR-owned marker (see _pr_owned_pause) gets its
    release COMPLETED here via _try_complete_release — merge-policy CLEARED → squash merge —
    so the pause can never deadly-embrace the paused beat that would have merged it.

    Fail-CLOSED: any ambiguity (autoclear disabled, no owner line, gh missing/errored, offline,
    not-yet-merged-and-not-completable) returns False so the beat stays paused. Throttled to at
    most once per LIMEN_AUTONOMY_MARKER_RECHECK_SECS so rapid callers don't hammer ``gh`` while
    a marker exists — the completion attempt runs inside the same throttle window.
    """
    if os.environ.get("LIMEN_AUTONOMY_MARKER_AUTOCLEAR", "1") != "1":
        return False
    try:
        recheck = float(os.environ.get("LIMEN_AUTONOMY_MARKER_RECHECK_SECS", "120"))
    except ValueError:
        recheck = 120.0
    now = time.time()
    try:
        if now - MARKER_RECHECK_STAMP.stat().st_mtime < recheck:
            return False  # checked recently — stay paused until the throttle window elapses
    except OSError:
        pass
    fields = _marker_fields(marker)
    owner = fields.get("owner", "")
    # An explicit ``pr:`` line names the release PR directly (e.g. ``pr: 1036`` or
    # ``pr: organvm/limen#1036``). The 2026-07-15 freeze recurrence: the marker's owner said
    # ``manual/overnight-watch-pause-guard-20260714`` but the guard merged from branch
    # ``agent/overnight-watch-pause-guard`` — the --head search can never match a hand-written
    # owner label, so the beat stayed paused after its release predicate was already satisfied.
    pr_match = re.search(r"(\d+)\s*$", fields.get("pr", ""))
    pr_number = pr_match.group(1) if pr_match else ""
    if not owner and not pr_number:
        return False
    try:
        MARKER_RECHECK_STAMP.parent.mkdir(parents=True, exist_ok=True)
        MARKER_RECHECK_STAMP.write_text(str(now))
    except OSError:
        pass
    if pr_number:
        try:
            proc = subprocess.run(
                ["gh", "pr", "view", pr_number, "--json", "state"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
                cwd=str(ROOT),
            )
        except (OSError, subprocess.SubprocessError):
            return False
        if proc.returncode == 0:
            try:
                if str(json.loads(proc.stdout).get("state")) == "MERGED":
                    return True
            except ValueError:
                pass
        if not owner:
            return _try_complete_release(fields)
    try:
        proc = subprocess.run(
            ["gh", "pr", "list", "--head", owner, "--state", "merged", "--json", "number", "--limit", "1"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            cwd=str(ROOT),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0:
        return False
    # A merged PR row survives branch deletion in GitHub's PR index, so --head is reliable here.
    if proc.stdout.strip() not in ("", "[]"):
        return True
    return _try_complete_release(fields)


def _marker_expired(marker: Path) -> bool:
    """An expired marker is an ABSENT marker.

    A halt nobody renews is a halt nobody is still choosing. The 2026-07-27 marker stood for four
    days because standing cost nothing — no TTL, no renewal, no one asked. Markers authored by
    scripts/pause.py now carry `expires_at`; this is the reader. Fails toward caution: a marker with
    no expiry, or an unparseable one, is NOT expired and still pauses.
    """
    try:
        fields = _marker_fields(marker)
    except OSError:
        return False
    raw = (fields.get("expires_at") or "").strip()
    if not raw:
        return False
    try:
        expiry = datetime.datetime.strptime(raw, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except ValueError:
        return False
    return datetime.datetime.now(datetime.timezone.utc) >= expiry


RESTORE_RECEIPT_PATH = ROOT / "logs" / "autonomy-policy-restore.json"


def _try_restore_dispatch(policy: dict[str, Any]) -> bool:
    """Flip a RESUMED finite maintenance window back to dispatch — with a receipt.

    The missing half of _try_complete_maintenance_window: satisfying the resume predicate
    only cleared the BLOCKER, it never rewrote `mode`, so the policy stayed observe forever
    (measured 2026-07-21 -> 08-06: predicates all passing since 08-05 while the estate sat
    at observe with a frozen 8/600 budget and zero dispatch). Restoring is scoped tightly:

      * only `mode: observe` with a finite `maintenance_window` dict — an indefinite
        observe policy (no window) is an operator statement and is never auto-flipped;
      * only when the recorded resume receipt covers THIS window (the predicate ran and
        passed, auditable at logs/autonomy-maintenance-resume.json);
      * never while the pause marker artifact exists, never when the window declares
        `restore: manual`, and never under LIMEN_AUTONOMY_WINDOW_RESTORE=0;
      * fail-closed: a policy file that cannot be rewritten means no flip happened.

    On success the window moves to `completed_maintenance_window` (so the flip can never
    re-trigger) and a restore receipt lands at logs/autonomy-policy-restore.json.
    """
    if os.environ.get("LIMEN_AUTONOMY_WINDOW_RESTORE", "1") == "0":
        return False
    if str(policy.get("mode", "")).lower() != "observe":
        return False
    window = policy.get("maintenance_window")
    if not isinstance(window, dict):
        return False
    if str(window.get("restore") or "").lower() == "manual":
        return False
    if PAUSE_MARKER.exists():
        return False
    if not _resume_receipt_matches(window):
        return False

    restored_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prior_mode = str(policy.get("mode", "observe"))
    updated = dict(policy)
    updated.pop("maintenance_window", None)
    updated["mode"] = "dispatch"
    updated["dispatch_enabled"] = True
    updated["reason"] = (
        f"auto-restored {restored_at}: finite maintenance window (expired {window.get('expires_at')}) "
        "resumed via its declared predicate — receipt logs/autonomy-policy-restore.json"
    )
    updated["completed_maintenance_window"] = {**window, "restored_at": restored_at}
    try:
        POLICY_PATH.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n")
    except OSError:
        return False  # a restore that cannot be recorded did not happen
    receipt = {
        "schema_version": "limen.autonomy-policy-restore.v1",
        "window_expires_at": str(window.get("expires_at") or ""),
        "prior_mode": prior_mode,
        "restored_at": restored_at,
        "resume_receipt": str(MAINTENANCE_RESUME_PATH),
    }
    try:
        RESTORE_RECEIPT_PATH.parent.mkdir(parents=True, exist_ok=True)
        RESTORE_RECEIPT_PATH.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    except OSError:
        pass  # the policy flip is the authoritative state; the receipt is evidence, not a gate
    print(
        f"autonomy-governor: dispatch auto-restored — window {window.get('expires_at')} resumed",
        file=sys.stderr,
    )
    return True


def current_mode() -> str:
    if PAUSE_MARKER.exists() and os.environ.get("LIMEN_FORCE_AUTONOMY") != "1":
        if _marker_expired(PAUSE_MARKER):
            # Leave the file in place — removing it is scripts/pause.py release's job, which writes
            # a receipt. Expiry only stops it from BINDING; the artifact stays for the audit trail.
            pass
        elif _marker_owner_merged(PAUSE_MARKER):
            try:
                PAUSE_MARKER.unlink()
            except OSError:
                pass
            # owner PR merged — fall through to policy mode; a merged-owner marker
            # can never freeze the next cycle. (Merge is a strict prerequisite of the
            # marker's release_predicate; the remaining conditions are separately enforced
            # by the ship-gate / omega sensors.)
        else:
            return "paused"
    policy = load_policy()
    blocker = maintenance_blocker(policy)
    if blocker is not None:
        _persist_maintenance_blocker(blocker)
        return "paused"
    if _try_restore_dispatch(policy):
        return "dispatch"
    return str(policy.get("mode", "observe")).lower()


def dispatch_allowed() -> tuple[bool, str]:
    policy = load_policy()
    mode = current_mode()
    if mode != "dispatch":
        return False, f"autonomy mode is {mode}"
    if not bool(policy.get("dispatch_enabled")) and os.environ.get("LIMEN_FORCE_AUTONOMY") != "1":
        return False, "dispatch_enabled is false"
    dead = usage_dead_lanes()
    if {"codex", "claude", "jules"}.issubset(dead):
        return False, "primary paid lanes exhausted/rate-limited"
    return True, "dispatch allowed"


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("mode")
    sub.add_parser("dispatch-ok")
    sub.add_parser("explain")
    sub.add_parser("acting")
    args = ap.parse_args()

    if args.cmd == "mode":
        print(current_mode())
        return 0
    if args.cmd == "dispatch-ok":
        ok, reason = dispatch_allowed()
        print(reason)
        return 0 if ok else 2
    if args.cmd == "acting":
        # The omega core.autonomy-acting rung's predicate: exit 0 ⟺ no maintenance blocker stands
        # (the estate is a live actor, not a halted observer waiting on an owner). Distinct from
        # `mode`, which reports "paused" as a normal string with no way for a shell predicate to
        # tell a legitimate short pause from a stale one — this is the loud yes/no omega needs.
        blocker = maintenance_blocker(load_policy())
        if blocker is None:
            print("autonomy-governor: acting — no maintenance blocker")
            return 0
        print(f"autonomy-governor: NOT acting — {blocker['state']}: {blocker['reason']}")
        return 1
    policy = load_policy()
    blocker = maintenance_blocker(policy)
    ok, reason = dispatch_allowed()
    print(
        json.dumps(
            {
                "mode": current_mode(),
                "policy": policy,
                "maintenanceBlocker": blocker,
                "maintenanceBlockerReceipt": str(MAINTENANCE_BLOCKER_PATH) if blocker else None,
                "dispatchAllowed": ok,
                "dispatchReason": reason,
                "deadLanes": sorted(usage_dead_lanes()),
                "pauseMarker": str(PAUSE_MARKER),
                "pauseMarkerExists": PAUSE_MARKER.exists(),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
