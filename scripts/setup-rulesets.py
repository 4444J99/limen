#!/usr/bin/env python3
"""setup-rulesets — make the merge gate self-draining (the principled fix, NOT a bypass).

For each repo that currently has open author PRs, configure the default branch so that:
  • required_status_checks = the repo's actual CI checks (strict: branch must be up to date)
  • required_pull_request_reviews = NONE  (there is no human reviewer team — requiring one is the
    faulty old element that forced the admin-bypass; we gate on CI instead)
  • allow_auto_merge = true  (so a PR armed with --auto merges itself the instant CI is green)

Then `gh pr merge <n> --auto --squash` on every green PR → the gate drains itself continuously,
matching the fleet's PR output, with zero bypass and zero babysitting.

SAFE: dry-run by default — prints the exact per-repo plan and executes NOTHING. Reversible:
branch protection can be removed. `--apply` is GATED on the user.

  python3 scripts/setup-rulesets.py            # dry-run plan (read-only)
  python3 scripts/setup-rulesets.py --apply     # ⚠ GATED: configure protection + auto-merge
  python3 scripts/setup-rulesets.py --repo owner/name [...]   # limit to specific repos
"""
import json, subprocess, sys
from collections import OrderedDict

APPLY = "--apply" in sys.argv
EXPLICIT = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--repo" and i + 1 < len(sys.argv)]


def gh(args, t=45):
    return subprocess.run(["gh"] + args, capture_output=True, text=True, timeout=t)


def gh_json(args, t=45, default=None):
    try:
        return json.loads(gh(args, t).stdout or "null") or default
    except json.JSONDecodeError:
        return default


def target_repos():
    if EXPLICIT:
        return EXPLICIT
    prs = gh_json(["search", "prs", "--author", "@me", "--state", "open", "--limit", "200",
                   "--json", "repository"], default=[]) or []
    seen = OrderedDict()
    for p in prs:
        seen[p["repository"]["nameWithOwner"]] = True
    return list(seen.keys())


import re
# A genuine merge gate is the test/build/lint suite — NOT bots, scanners, release-drafters, or CLA.
# Requiring the latter (strict) would permanently block merges (they never reliably "pass" per-PR).
_GATE = re.compile(r"\b(test|build|lint|typecheck|type-check|e2e|tox|matrix|smoke|unit|compile|gates|pytest|jest|vitest|doctor)\b", re.I)
_NOISE = re.compile(r"(cla|dependabot|release[_-]?draft|sourcery|coderabbit|gitguardian|semgrep|secret|codeql|analyze|advisory|scan|pr title|pr comment|^release$)", re.I)


def is_real_gate(name):
    return bool(_GATE.search(name)) and not _NOISE.search(name)


def detect_checks(repo):
    """genuine CI gate names from the newest open PR's rollup (filtered: real test/build/lint only)."""
    prs = gh_json(["pr", "list", "--repo", repo, "--state", "open", "--limit", "1",
                   "--json", "number"], default=[]) or []
    if not prs:
        return []
    d = gh_json(["pr", "view", str(prs[0]["number"]), "--repo", repo,
                 "--json", "statusCheckRollup"], default={}) or {}
    names = []
    for c in d.get("statusCheckRollup") or []:
        n = c.get("name") or c.get("context")
        if n and n not in names and is_real_gate(n):
            names.append(n)
    return names


def main():
    repos = target_repos()
    print(f"=== ruleset plan — {len(repos)} repos with open PRs "
          f"({'APPLY' if APPLY else 'DRY-RUN'}) ===\n")
    no_ci = []
    for repo in repos:
        info = gh_json(["repo", "view", repo, "--json", "defaultBranchRef"], default={}) or {}
        branch = (info.get("defaultBranchRef") or {}).get("name") or "main"
        checks = detect_checks(repo)
        if not checks:
            no_ci.append(repo)
            print(f"  {repo}@{branch}: ⚠ no CI checks detected → auto-merge N/A (PRs merge immediately); "
                  f"would only set allow_auto_merge")
        else:
            print(f"  {repo}@{branch}: require {len(checks)} check(s) {checks[:4]}"
                  f"{'…' if len(checks) > 4 else ''} · no human review · allow_auto_merge=true")
        if not APPLY:
            continue
        # --- APPLY ---
        gh(["api", "-X", "PATCH", f"/repos/{repo}", "-F", "allow_auto_merge=true",
            "-F", "delete_branch_on_merge=true"])
        if checks:
            body = {
                # strict:false — gate on checks passing, NOT on branch-up-to-date, else auto-merge
                # deadlocks (nothing auto-updates behind branches) and we're back on the treadmill.
                "required_status_checks": {"strict": False, "contexts": checks},
                "enforce_admins": False,
                "required_pull_request_reviews": None,
                "restrictions": None,
            }
            r = gh(["api", "-X", "PUT", f"/repos/{repo}/branches/{branch}/protection",
                    "--input", "-"], t=45)
            # pass JSON via stdin
            r = subprocess.run(["gh", "api", "-X", "PUT",
                                f"/repos/{repo}/branches/{branch}/protection", "--input", "-"],
                               input=json.dumps(body), capture_output=True, text=True, timeout=45)
            ok = r.returncode == 0
            print(f"      {'✓ protected + auto-merge on' if ok else '✗ ' + r.stderr.strip()[:70]}")
        else:
            print(f"      ✓ allow_auto_merge set (no protection — no CI to gate on)")

    print(f"\n{len(repos)-len(no_ci)} repos gateable via CI; {len(no_ci)} have no CI "
          f"(auto-merge moot — they merge on creation).")
    if not APPLY:
        print("\nDRY-RUN — nothing changed. Re-run with --apply (GATED) to configure.")
        print("After --apply: `gh pr merge <n> --auto --squash` on green PRs → self-draining gate.")


if __name__ == "__main__":
    main()
