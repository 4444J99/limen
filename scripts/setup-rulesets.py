#!/usr/bin/env python3
"""setup-rulesets — configure bounded, repository-declared merge rails.

For each repo that currently has open author PRs, configure the default branch so that:
  • required_status_checks = the repo's declared CI checks (strict:false), or NONE for a
    registry-declared single-owner fast lane
  • required_pull_request_reviews = NONE  (there is no human reviewer team — requiring one is the
    faulty old element that forced the admin-bypass; we gate on CI instead)
  • allow_auto_merge = false on a single-owner fast lane (merge the locally verified exact head
    immediately); true elsewhere when remote checks own admission
  • delete_branch_on_merge = false  (source branches are retained for receipt-backed reaping)

Required checks and the single-owner fast-lane declaration come from
`institutio/github/estate.yaml`; live check-rollup detection is never a substitute for declared
desired state. For 4444J99/limen, clear remote required checks while retaining
enforce_admins:true, and idempotently ensure a default-branch ruleset holding a zero-approval,
review-thread-advisory pull-request rule with no bypass actors: every mutation, including
Tabularius board publication, must enter through a PR. The native merge queue was removed 2026-08-06
(proven-at-submission rail): its serialized re-validation lane re-derived proofs the scoped local
gates had already produced, and its evict-to-back failure mode turned a GitHub Actions incident
into a day-long merge outage for green PRs. Limen's rail is immediate exact-head squash after local
scoped verification; repositories with declared remote checks retain their check-gated rail.

SAFE: dry-run by default — prints the exact per-repo plan and executes NOTHING. Reversible:
branch protection can be removed. `--apply` is GATED on the user.

  python3 scripts/setup-rulesets.py            # dry-run plan (read-only)
  python3 scripts/setup-rulesets.py --apply     # ⚠ GATED: configure protection + auto-merge
  python3 scripts/setup-rulesets.py --repo owner/name [...]   # limit to specific repos
  python3 scripts/setup-rulesets.py --contexts pr-gate,python,web   # explicit one-run override
"""

import json
from fnmatch import fnmatchcase
from pathlib import Path
import subprocess
import sys
from collections import OrderedDict

import yaml

MERGE_QUEUE_REPO = "4444J99/limen"
MERGE_QUEUE_REPO_KEY = MERGE_QUEUE_REPO.casefold()
ROOT = Path(__file__).resolve().parents[1]
ESTATE = ROOT / "institutio" / "github" / "estate.yaml"
# Historical name retained: this is the live ruleset's identity on GitHub (id 19147990) and
# renaming it would churn every external reference for zero behavioral gain. The queue rule
# itself was removed 2026-08-06; only the pull_request rule remains.
MERGE_QUEUE_RULESET_NAME = "limen-default-merge-queue"

APPLY = "--apply" in sys.argv
EXPLICIT = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--repo" and i + 1 < len(sys.argv)]
# --contexts a,b,c explicitly overrides the registry for this invocation. Applied to every target.
FORCED = next(
    (sys.argv[i + 1].split(",") for i, a in enumerate(sys.argv) if a == "--contexts" and i + 1 < len(sys.argv)), None
)
FORCED = [c.strip() for c in FORCED if c.strip()] if FORCED else None


def gh(args, t=45):
    return subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=t)


def gh_json(args, t=45, default=None):
    try:
        return json.loads(gh(args, t).stdout or "null") or default
    except json.JSONDecodeError:
        return default


def gh_json_checked(args, t=45):
    """Return decoded JSON plus an error string; never turn an API failure into an empty estate."""
    result = gh(args, t)
    if result.returncode != 0:
        return None, (result.stderr or result.stdout or "github request failed").strip()[:160]
    try:
        return json.loads(result.stdout or "null"), ""
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def gh_input(method, path, body, t=45):
    """Call a mutating GitHub endpoint once with an explicit JSON body."""
    return subprocess.run(
        ["gh", "api", "-X", method, path, "--input", "-"],
        input=json.dumps(body),
        capture_output=True,
        text=True,
        timeout=t,
    )


def target_repos():
    if EXPLICIT:
        return EXPLICIT
    prs = (
        gh_json(
            ["search", "prs", "--author", "@me", "--state", "open", "--limit", "200", "--json", "repository"],
            default=[],
        )
        or []
    )
    seen = OrderedDict()
    for p in prs:
        seen[p["repository"]["nameWithOwner"]] = True
    return list(seen.keys())


class EstateContractError(RuntimeError):
    """The declared GitHub estate cannot safely determine a repository's merge checks."""


def _repo_coordinate_key(repo):
    """Return the case-insensitive identity key GitHub uses for OWNER/REPO coordinates."""
    return repo.strip().casefold()


def _is_limen_repo(repo):
    return _repo_coordinate_key(repo) == MERGE_QUEUE_REPO_KEY


def _load_estate():
    try:
        document = yaml.safe_load(ESTATE.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise EstateContractError(f"cannot read {ESTATE}: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("classes"), dict):
        raise EstateContractError("estate classes mapping is missing")
    return document


def _repo_facts(repo):
    observed, error = gh_json_checked(["repo", "view", repo, "--json", "isArchived,isFork,isPrivate"])
    if error or not isinstance(observed, dict):
        raise EstateContractError(f"cannot derive repository facts for {repo}: {error or 'unexpected response'}")
    return {
        "archived": observed.get("isArchived"),
        "fork": observed.get("isFork"),
        "private": observed.get("isPrivate"),
    }


def _class_for_repo(document, repo, facts=None):
    classes = document["classes"]
    repo_key = _repo_coordinate_key(repo)
    overrides = document.get("repo_overrides") or {}
    override = next(
        (
            row
            for coordinate, row in overrides.items()
            if isinstance(coordinate, str) and _repo_coordinate_key(coordinate) == repo_key
        ),
        None,
    )
    if isinstance(override, dict) and override.get("class"):
        name = override["class"]
        row = classes.get(name)
        if not isinstance(row, dict):
            raise EstateContractError(f"repo override for {repo} names unknown class {name!r}")
        return name, row

    observed_facts = facts
    for name, row in classes.items():
        if not isinstance(row, dict):
            continue
        patterns = row.get("match")
        if not isinstance(patterns, list) or not any(
            isinstance(pattern, str) and fnmatchcase(repo_key, pattern.casefold()) for pattern in patterns
        ):
            continue
        expected_facts = row.get("match_facts")
        if expected_facts:
            if not isinstance(expected_facts, dict):
                raise EstateContractError(f"class {name!r} has invalid match_facts")
            observed_facts = observed_facts if observed_facts is not None else _repo_facts(repo)
            if any(observed_facts.get(key) != value for key, value in expected_facts.items()):
                continue
        return name, row
    raise EstateContractError(f"no estate class matches {repo}")


def _policy_for_repo(repo, facts=None):
    """Return the first-match estate class and its merge policy."""
    return _class_for_repo(_load_estate(), repo, facts=facts)


def checks_for_repo(repo, facts=None):
    """Return the registry-declared required checks for the repository's first matching class."""
    if FORCED:
        return list(FORCED)
    class_name, row = _policy_for_repo(repo, facts=facts)
    checks = row.get("required_checks")
    if not isinstance(checks, list) or any(not isinstance(check, str) or not check for check in checks):
        raise EstateContractError(f"estate class {class_name!r} has invalid required_checks")
    return list(checks)


def single_owner_fast_lane_for_repo(repo, facts=None):
    """Whether local exact-tree verification replaces remote merge admission for this repo."""
    class_name, row = _policy_for_repo(repo, facts=facts)
    value = row.get("single_owner_fast_lane", False)
    if not isinstance(value, bool):
        raise EstateContractError(f"estate class {class_name!r} has invalid single_owner_fast_lane")
    return value


def classic_protection_body(checks):
    """Classic CI protection stays non-strict; the ruleset owns the no-direct-push edge."""
    return {
        # strict:false — gate on checks passing, NOT on branch-up-to-date, else auto-merge
        # deadlocks (nothing auto-updates behind branches) and we're back on the treadmill.
        "required_status_checks": {"strict": False, "contexts": checks} if checks else None,
        "enforce_admins": True,
        "required_pull_request_reviews": None,
        "restrictions": None,
    }


def classic_protection_contract_holds(actual, checks):
    """Read-after-write verification for the exact non-strict, admin-enforced check gate."""
    if not isinstance(actual, dict):
        return False
    status = actual.get("required_status_checks")
    enforce_admins = actual.get("enforce_admins") or {}
    if checks:
        status_ok = (
            isinstance(status, dict)
            and status.get("strict") is False
            and (status.get("contexts") or []) == checks
        )
    else:
        status_ok = status is None
    return (
        status_ok
        and enforce_admins.get("enabled") is True
        and actual.get("required_pull_request_reviews") is None
        and actual.get("restrictions") is None
    )


def default_ruleset_body():
    """A no-bypass PR requirement with automated review advisory on the single-owner rail."""
    return {
        "name": MERGE_QUEUE_RULESET_NAME,
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["squash"],
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_approving_review_count": 0,
                    "required_review_thread_resolution": False,
                },
            },
        ],
    }


def _contains_contract(actual, expected):
    """Recursively require the exact security-relevant fields while tolerating API metadata."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and _contains_contract(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return isinstance(actual, list) and actual == expected
    return actual == expected


def _ruleset_contract_holds(actual):
    expected = default_ruleset_body()
    if not _contains_contract(
        actual,
        {
            "name": expected["name"],
            "target": expected["target"],
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": expected["conditions"],
        },
    ):
        return False
    rules = actual.get("rules") if isinstance(actual, dict) else None
    if not isinstance(rules, list) or [rule.get("type") for rule in rules] != ["pull_request"]:
        return False
    return all(
        _contains_contract(rule.get("parameters"), wanted.get("parameters"))
        for rule, wanted in zip(rules, expected["rules"], strict=True)
    )


def actions_workflow_permissions_body():
    """Keep the token read-only by default while allowing explicit workflows to create board PRs."""
    return {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": True,
    }


def ensure_actions_pr_permissions(repo):
    """Enable and verify the repository switch required for GITHUB_TOKEN-created pull requests."""
    if not _is_limen_repo(repo):
        return True
    body = actions_workflow_permissions_body()
    result = gh_input("PUT", f"/repos/{repo}/actions/permissions/workflow", body)
    if result.returncode != 0:
        print("      ✗ Actions PR permission: " + result.stderr.strip()[:80])
        return False
    observed, error = gh_json_checked(["api", f"/repos/{repo}/actions/permissions/workflow"])
    ok = not error and _contains_contract(observed, body)
    print("      " + ("✓ Actions PR permission verified" if ok else f"✗ Actions PR permission unverified: {error}"))
    return ok


def ensure_default_ruleset(repo):
    """Idempotently create/update and read-after-write verify Limen's default-branch ruleset."""
    if not _is_limen_repo(repo):
        return True
    existing, error = gh_json_checked(["api", f"/repos/{repo}/rulesets"])
    if error or not isinstance(existing, list):
        print("      ✗ limen default ruleset list: " + (error or "unexpected response"))
        return False
    rid = next((r.get("id") for r in existing if r.get("name") == MERGE_QUEUE_RULESET_NAME), None)
    method, path = ("PUT", f"/repos/{repo}/rulesets/{rid}") if rid else ("POST", f"/repos/{repo}/rulesets")
    result = gh_input(method, path, default_ruleset_body())
    if result.returncode != 0:
        print("      ✗ limen default ruleset: " + result.stderr.strip()[:80])
        return False
    if not rid:
        try:
            rid = json.loads(result.stdout or "{}").get("id")
        except json.JSONDecodeError:
            rid = None
    if not rid:
        refreshed, error = gh_json_checked(["api", f"/repos/{repo}/rulesets"])
        if error or not isinstance(refreshed, list):
            print("      ✗ limen default ruleset id unverified: " + (error or "unexpected response"))
            return False
        rid = next((r.get("id") for r in refreshed if r.get("name") == MERGE_QUEUE_RULESET_NAME), None)
    observed, error = gh_json_checked(["api", f"/repos/{repo}/rulesets/{rid}"]) if rid else (None, "missing id")
    ok = not error and _ruleset_contract_holds(observed)
    print("      " + ("✓ limen default ruleset verified" if ok else f"✗ limen default ruleset unverified: {error}"))
    return ok


_COPILOT_AVAILABLE = {}


def copilot_available(org):
    """One cached probe per org: does it hold ANY Copilot seat? (/orgs/{org}/copilot/billing
    .seat_breakdown.total > 0 — a 200 alone is NOT enough; the endpoint answers 200 with 0 seats
    while Copilot is unconfigured.) Gate for the copilot-review ruleset: no seat → clean no-op.
    Individual Copilot Pro (restored free 2026-07-17, #1186) is NOT an org Business seat — this
    stays a no-op unless org seats ever exist (docs/github-estate-runbook.md)."""
    if org not in _COPILOT_AVAILABLE:
        data = gh_json(["api", f"/orgs/{org}/copilot/billing"], t=20, default=None)
        total = ((data or {}).get("seat_breakdown") or {}).get("total") or 0
        _COPILOT_AVAILABLE[org] = total > 0
    return _COPILOT_AVAILABLE[org]


def ensure_copilot_review(repo):
    """Idempotently ensure the `copilot-review` repo RULESET (rulesets, not classic protection —
    automatic Copilot code review only exists there) requesting Copilot review on default-branch
    PRs. required_approving_review_count stays 0 so merge-drain is never blocked on an approval.
    Arms itself on the next --apply after the Copilot seat lands; until then a one-line skip."""
    org = repo.split("/", 1)[0]
    if not copilot_available(org):
        print(
            "      · copilot-review ruleset skipped — no org Copilot Business seat (individual Pro doesn't count; see runbook)"
        )
        return True
    existing = gh_json(["api", f"/repos/{repo}/rulesets"], default=[]) or []
    rid = next((r.get("id") for r in existing if r.get("name") == "copilot-review"), None)
    body = {
        "name": "copilot-review",
        "target": "branch",
        "enforcement": "active",
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {
                "type": "pull_request",
                "parameters": {
                    "automatic_copilot_code_review_enabled": True,
                    "required_approving_review_count": 0,
                    "dismiss_stale_reviews_on_push": False,
                    "require_code_owner_review": False,
                    "require_last_push_approval": False,
                    "required_review_thread_resolution": False,
                },
            }
        ],
    }
    method, path = ("PUT", f"/repos/{repo}/rulesets/{rid}") if rid else ("POST", f"/repos/{repo}/rulesets")
    r = gh_input(method, path, body)
    ok = r.returncode == 0
    print(f"      {'✓ copilot-review ruleset ensured' if ok else '✗ copilot-review ruleset: ' + r.stderr.strip()[:60]}")
    return ok


def main():
    repos = target_repos()
    print(f"=== ruleset plan — {len(repos)} repos with open PRs ({'APPLY' if APPLY else 'DRY-RUN'}) ===")
    if FORCED:
        print(f"    contexts forced (detection skipped): {FORCED}")
    print()
    no_ci = []
    fast_lanes = []
    failures = []
    for repo in repos:
        info = (
            gh_json(
                ["repo", "view", repo, "--json", "defaultBranchRef,isArchived,isFork,isPrivate"],
                default={},
            )
            or {}
        )
        branch = (info.get("defaultBranchRef") or {}).get("name") or "main"
        facts = {
            "archived": info.get("isArchived"),
            "fork": info.get("isFork"),
            "private": info.get("isPrivate"),
        }
        try:
            checks = checks_for_repo(repo, facts=facts)
            fast_lane = single_owner_fast_lane_for_repo(repo, facts=facts)
        except EstateContractError as exc:
            failures.append(f"{repo}:estate-contract")
            print(f"  {repo}@{branch}: ✗ {exc}")
            continue
        if fast_lane:
            fast_lanes.append(repo)
            print(
                f"  {repo}@{branch}: single-owner fast lane → local exact-tree verification; "
                "no remote admission checks or auto-merge wait"
            )
        elif not checks:
            no_ci.append(repo)
            print(
                f"  {repo}@{branch}: ⚠ no CI checks detected → auto-merge N/A (PRs merge immediately); "
                f"would only set allow_auto_merge"
            )
        else:
            print(
                f"  {repo}@{branch}: require {len(checks)} check(s) {checks[:4]}"
                f"{'…' if len(checks) > 4 else ''} · no human review · allow_auto_merge=true"
            )
        if _is_limen_repo(repo):
            print(
                "      + default-branch PR-only ruleset (zero approvals, bot threads advisory, no bypass, "
                "squash-only; exact-head direct rail)"
            )
        if not APPLY:
            continue
        # --- APPLY ---
        # Install and read-after-write verify the no-bypass rule before touching the weaker
        # classic branch-protection surface. A rejected ruleset can therefore never be hidden by
        # a later successful API call.
        if _is_limen_repo(repo):
            prerequisites_ok = True
            if not ensure_actions_pr_permissions(repo):
                failures.append(f"{repo}:actions-pr-permission")
                prerequisites_ok = False
            if not ensure_default_ruleset(repo):
                failures.append(f"{repo}:default-ruleset")
                prerequisites_ok = False
            if not prerequisites_ok:
                print("      ✗ refusing weaker repository/classic mutations until prerequisites verify")
                continue

        repo_settings = gh(
            [
                "api",
                "-X",
                "PATCH",
                f"/repos/{repo}",
                "-F",
                f"allow_auto_merge={'false' if fast_lane else 'true'}",
                "-F",
                "delete_branch_on_merge=false",
            ]
        )
        if repo_settings.returncode != 0:
            failures.append(f"{repo}:repository-settings")
            print("      ✗ repository settings: " + repo_settings.stderr.strip()[:70])
            continue
        observed_settings, settings_error = gh_json_checked(["api", f"/repos/{repo}"])
        settings_ok = (
            not settings_error
            and isinstance(observed_settings, dict)
            and observed_settings.get("allow_auto_merge") is (not fast_lane)
            and observed_settings.get("delete_branch_on_merge") is False
        )
        if not settings_ok:
            failures.append(f"{repo}:repository-settings-unverified")
            print("      ✗ repository settings unverified: " + (settings_error or "contract mismatch"))
            continue
        print("      ✓ repository settings verified")
        if checks or fast_lane:
            body = classic_protection_body(checks)
            r = gh_input("PUT", f"/repos/{repo}/branches/{branch}/protection", body)
            if r.returncode != 0:
                failures.append(f"{repo}:classic-protection")
                print("      ✗ classic protection: " + r.stderr.strip()[:70])
                continue
            observed_protection, protection_error = gh_json_checked(
                ["api", f"/repos/{repo}/branches/{branch}/protection"]
            )
            ok = not protection_error and classic_protection_contract_holds(observed_protection, checks)
            print(
                "      "
                + (
                    "✓ classic protection verified"
                    if ok
                    else "✗ classic protection unverified: " + (protection_error or "contract mismatch")
                )
            )
            if not ok:
                failures.append(f"{repo}:classic-protection-unverified")
                continue
        else:
            print("      ✓ allow_auto_merge set (no protection — no CI to gate on)")
        # The review engine's Copilot lane — a ruleset, orthogonal to the classic protection above.
        if not ensure_copilot_review(repo):
            failures.append(f"{repo}:copilot-review")

    ci_gated = len(repos) - len(no_ci) - len(fast_lanes)
    print(
        f"\n{ci_gated} repos gateable via remote CI; {len(fast_lanes)} single-owner fast lane(s); "
        f"{len(no_ci)} have neither required checks nor a fast-lane declaration."
    )
    if not APPLY:
        print("\nDRY-RUN — nothing changed. Re-run with --apply (GATED) to configure.")
        if any(_is_limen_repo(repo) for repo in repos):
            print(
                "After scoped local verification and --apply succeeds: "
                "`gh pr merge <n> --repo 4444J99/limen --squash --match-head-commit <sha>` "
                "→ immediate exact-head merge; do not wait or retry."
            )
        if any(not _is_limen_repo(repo) for repo in repos):
            print("For non-queue repos: `gh pr merge <n> --auto --squash` on green PRs.")
    if failures:
        print("\nAPPLY FAILED: " + ", ".join(failures), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
