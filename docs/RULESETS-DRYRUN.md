# setup-rulesets.py — DRY-RUN report (self-draining merge gate)

**Date:** 2026-06-19 · **Run by:** subagent (read-only) · **Source:** `scripts/setup-rulesets.py`
**Status:** DRY-RUN ONLY — nothing was changed. Apply is GATED on the user.

## Why this is THE bottleneck (START-HERE.md #5)

Repos have **zero branch protection** → GitHub auto-merge cannot arm → every PR must be
hand-merged, which races the fleet's continuous PR output (a treadmill). This script fixes the
gate **principally** (gate on CI, not on a non-existent human reviewer) so PRs self-merge on green.

## What the script does (verified from source)

For each repo that currently has open author PRs (`gh search prs --author @me --state open`):

1. **`PATCH /repos/{repo}`** → `allow_auto_merge=true`, `delete_branch_on_merge=false`.
2. If genuine CI checks are detected on the newest open PR's status rollup:
   **`PUT /repos/{repo}/branches/{branch}/protection`** with:
   - `required_status_checks = {strict:false, contexts:[detected CI names]}`
     (`strict:false` is deliberate — strict would deadlock auto-merge behind out-of-date branches).
   - `required_pull_request_reviews = null` (NO human review requirement — this is the faulty old
     element that forced admin-bypass; the gate is CI instead).
   - `enforce_admins = false`, `restrictions = null`.
3. If no CI is detected: only `allow_auto_merge` is set (auto-merge is moot — those PRs merge on
   creation).

**Check classifier** (lines 50-57): a "real gate" name matches
`test|build|lint|typecheck|e2e|tox|matrix|smoke|unit|compile|gates|pytest|jest|vitest|doctor`
AND is NOT noise (`cla|dependabot|release-draft|sourcery|coderabbit|gitguardian|semgrep|secret|
codeql|analyze|scan|...`). So scanners/CLA/release-drafters are correctly excluded from the gate —
requiring those would permanently block merges since they don't reliably pass per-PR.

> Note: the script has **no argparse**; `--help` does NOT print help, it runs the dry-run.
> That is harmless (dry-run is read-only), but the real apply trigger is the literal `--apply` flag.

## Plan (dry-run output, 2026-06-19)

- **43 repos targeted** (all repos with open author PRs).
- **32 gateable via CI** → would get branch protection + auto-merge.
- **11 have no CI** → would only get `allow_auto_merge` (moot; they merge on creation):
  `a-organvm/organvm-corpvs-testamentvm`, `4444J99/relationship-pipeline`,
  `a-organvm/public-record-data-scrapper`, `4444J99/limen`, `a-organvm/tab-bookmark-manager`,
  `a-organvm/a-i-chat--exporter`, `4444J99/session-meta`, `organvm-v-logos/.github`,
  `organvm-iv-taxis/.github`, `a-organvm/call-function--ontological`, `a-organvm/a-mavs-olevm`.
- Default branches are mostly `main`; 4 use `master`
  (`4444J99/domus-genoma`, `a-organvm/a-i-chat--exporter`, `a-organvm/metasystem-master`,
  `a-organvm/a-mavs-olevm`) — the script reads `defaultBranchRef` per repo, so this is handled.

Highest-value repos in scope include the exporter/revenue chain and product repos
(`media-ark`, `domus-genoma`, `mirror-mirror`, `the-invisible-ledger`, `universal-mail--automation`,
`my--father-mother`).

## Verification I performed (read-only)

- `gh api /repos/4444J99/trendpulse/branches/main/protection` → **404 "Branch not protected"**:
  confirms protection is genuinely absent today (the premise is real).
- `allow_auto_merge` currently **false** on samples (`trendpulse`, `mirror-mirror`, `limen`);
  `allow_squash_merge` **true** everywhere checked (so the `gh pr merge --auto --squash` follow-up
  will work); `delete_branch_on_merge` currently **false** and the script now keeps it false.
- `permissions.admin = true` on samples → the apply has the rights to PUT protection / PATCH repo.
- `gh auth` scopes: `repo, read:org, gist` — sufficient for branch protection + repo settings.

## Reversibility

**Fully reversible.** Each change is undoable:
- Branch protection: `gh api -X DELETE /repos/{repo}/branches/{branch}/protection`.
- Auto-merge: `gh api -X PATCH /repos/{repo} -F allow_auto_merge=false`.
- Source-branch retention: `gh api -X PATCH /repos/{repo} -F delete_branch_on_merge=false`.
No commits, no merges, no history rewrite — only repo/branch settings. The script's own docstring
states "Reversible: branch protection can be removed."

## Risks

1. **Detection blind spot:** CI names are read from the *single newest* open PR's status rollup. A
   repo whose newest PR didn't trigger CI (or whose CI was added later) could be misclassified as
   "no CI" and left ungated, or detect a partial set of contexts. Mitigation: re-run after PRs
   refresh, or pass `--repo` to fix specific repos.
2. **Source branches are retained** after merge. That creates local/remote residue, but the residue
   is intentional: branch removal belongs to `scripts/reap-branches.py` after receipt-backed
   archive/redaction proof, not to GitHub's automatic merge cleanup.
3. **No human review on the default branch:** by design (there is no reviewer team), but it means CI
   green is the *only* gate. If a repo's CI is weak/missing, weak PRs can auto-merge. Pair with the
   no-CI list above — those 11 repos have no gate at all and merge on creation.
4. **`strict:false`** means a PR can merge while behind the base branch (no up-to-date requirement).
   Deliberate to avoid auto-merge deadlock, but allows a stale-but-green PR to merge.
5. **`enforce_admins:false`** leaves an admin able to bypass — acceptable (the point is to NOT need
   bypass), but it is not a hard lock.
6. **Scope creep over time:** target set = repos with open PRs *right now* (43). New repos that get
   PRs later won't be covered until re-run.

## Recommendation

**Recommend the user authorize `--apply`.** This is the highest-leverage move per START-HERE.md:
it converts hand-merging (which loses the race against fleet output) into a self-draining,
zero-bypass gate, and it is fully reversible with admin rights already in place. The premise is
verified (protection absent, auto-merge off today). Two caveats to flag before applying:
(a) source branches remain after merge and need receipt-backed reaping later; (b) detection relies
on the newest PR, so a post-apply re-run (or targeted `--repo` passes) may be needed to catch any
repo whose CI wasn't visible on its newest PR. The 11 no-CI repos gain no real gate — track those
separately.

Suggested sequencing after apply: `gh pr merge <n> --auto --squash` on the already-green merge-ready
PRs (see merge-readiness map) to prime the self-draining loop.

## Exact command the human runs to apply (GATED — do not run without go-ahead)

```bash
cd ~/Workspace/limen && export LIMEN_ROOT="$PWD" PYTHONPATH="$PWD/cli/src"
python3 scripts/setup-rulesets.py --apply
# optional: limit to specific repos
# python3 scripts/setup-rulesets.py --apply --repo a-organvm/mirror-mirror 4444J99/media-ark
```
