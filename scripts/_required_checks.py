#!/usr/bin/env python3
"""_required_checks.py — ONE shared required-check failure policy for the self-* organs.

merge-drain.py and self-heal.py are two halves of one verdict: merge-drain refuses to
merge CI-RED PRs and self-heal emits repair tasks for them. Each carried its own copy of
"which failed checks count", and the copies drifted: self-heal treated EVERY failed
status in ``statusCheckRollup`` as CI-RED while merge-drain only counted required
checks, so optional diagnostic failures could generate unnecessary fleet work even when
merge-drain considered the required rail green (issue #2764).

This module is the single, testable policy. Both organs call it; neither keeps a copy.

Return convention (fail-closed):
- ``tuple[str, ...]`` — measured; these required checks are in the queried states.
- ``()`` — measured; no required check is in the queried states.
- ``None`` — UNMEASURED: the required-check policy could not be read. This is neither
  green nor an observed failure; callers must surface it as unknown and refuse to act
  on it (no merge, no heal task).
"""

import json
from urllib.parse import quote

# Required-check states, as reported by `gh pr checks --required` (bucket/state, lowercase).
FAIL_STATES = frozenset(
    {"fail", "failure", "error", "cancel", "cancelled", "timed_out", "action_required"}
)
PENDING_STATES = frozenset(
    {"pending", "in_progress", "queued", "expected", "waiting", "requested"}
)
KNOWN_STATES = frozenset(
    {
        "pass",
        "success",
        "neutral",
        "skipping",
        "skipped",
        *FAIL_STATES,
        *PENDING_STATES,
    }
)

# statusCheckRollup literals (uppercase conclusion/state) for the same two classes.
ROLLUP_FAIL_STATES = frozenset(
    {"FAILURE", "ERROR", "CANCELLED", "TIMED_OUT", "ACTION_REQUIRED"}
)
ROLLUP_PENDING_STATES = frozenset({"PENDING", "IN_PROGRESS", "QUEUED", "EXPECTED", ""})

# Ruleset types that protect a branch WITHOUT requiring any CI context. Unknown rule
# types remain unmeasured, never proof of absent checks.
_NON_CHECK_RULES = frozenset(
    {
        "pull_request",
        "creation",
        "update",
        "deletion",
        "non_fast_forward",
        "required_linear_history",
        "required_signatures",
    }
)

# Verdicts returned by classify_required_failure().
CI_RED = "CI-RED"
UNMEASURED = "REQUIRED-CHECKS-UNMEASURED"
OPTIONAL_ONLY = "OPTIONAL-ONLY"


def no_required_policy(gh, repo: str, branch: str | None) -> bool:
    """Prove absence of required checks through both branch protection and rules."""
    if not isinstance(branch, str) or not branch.strip():
        return False
    encoded = quote(branch, safe="")
    try:
        metadata = gh(["api", f"repos/{repo}/branches/{encoded}"], timeout=20)
        rules = gh(["api", f"repos/{repo}/rules/branches/{encoded}"], timeout=20)
        if metadata.returncode or rules.returncode:
            return False
        info = json.loads(metadata.stdout)
        effective = json.loads(rules.stdout)
        if (
            not isinstance(info, dict)
            or info.get("name") != branch
            or type(info.get("protected")) is not bool
        ):
            return False
        if not isinstance(effective, list):
            return False
        # A PR-only ruleset protects the branch without requiring a CI context.
        # Unknown rule types remain unmeasured, not proof of absent checks.
        if any(
            not isinstance(rule, dict) or rule.get("type") not in _NON_CHECK_RULES
            for rule in effective
        ):
            return False
        if info["protected"] is False:
            return True
        protection = info.get("protection")
        required = (
            protection.get("required_status_checks")
            if isinstance(protection, dict)
            else None
        )
        return (
            isinstance(required, dict)
            and required.get("contexts") == []
            and required.get("checks") == []
        )
    except (OSError, ValueError, TypeError):
        return False


def required_checks_in_states(
    gh, repo: str, num: int, branch: str | None, states
) -> tuple | None:
    """Required checks of PR ``num`` currently in ``states``; None when unmeasured."""
    result = gh(
        [
            "pr",
            "checks",
            str(num),
            "-R",
            repo,
            "--required",
            "--json",
            "name,bucket,state",
        ],
        timeout=40,
    )
    try:
        rows = json.loads(result.stdout)
    except (TypeError, ValueError):
        message = (getattr(result, "stderr", "") or result.stdout or "").strip()
        if (
            result.returncode == 1
            and message.startswith("no required checks reported on the ")
            and no_required_policy(gh, repo, branch)
        ):
            return ()
        return None
    if not isinstance(rows, list):
        return None
    if any(
        not isinstance(row, dict)
        or not isinstance(row.get("name"), str)
        or not row["name"]
        or str(row.get("bucket") or row.get("state") or "").lower() not in KNOWN_STATES
        for row in rows
    ):
        return None
    wanted = {str(s).lower() for s in states}
    return tuple(
        sorted(
            str(row["name"])
            for row in rows
            if str(row.get("bucket") or row.get("state") or "").lower() in wanted
        )
    )


def failing_required_checks(
    gh, repo: str, num: int, branch: str | None = None
) -> tuple | None:
    """Required checks of PR ``num`` currently failing; None when unmeasured."""
    return required_checks_in_states(gh, repo, num, branch, FAIL_STATES)


def pending_required_checks(
    gh, repo: str, num: int, branch: str | None = None
) -> tuple | None:
    """Required checks of PR ``num`` currently pending; None when unmeasured."""
    return required_checks_in_states(gh, repo, num, branch, PENDING_STATES)


def classify_required_failure(failing_required) -> str:
    """One shared verdict for a PR whose rollup shows check failures.

    - ``CI-RED``: a required check failed — merge-drain must refuse, self-heal may
      emit a targeted repair task.
    - ``REQUIRED-CHECKS-UNMEASURED``: the required policy could not be read — fail
      closed: neither green nor an observed required failure.
    - ``OPTIONAL-ONLY``: only optional diagnostics failed while the required rail
      is green — visible in GitHub, but creates no CI-red work.
    """
    if failing_required is None:
        return UNMEASURED
    if failing_required:
        return CI_RED
    return OPTIONAL_ONLY
