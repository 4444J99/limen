---
name: ship
description: Drive one change from implemented to merged and observed live — scoped gates, PR, exact-head merge, live-artifact proof, session closeout predicate — with no status stalls and no waiting in between. Use when asked to ship, land, or deliver a change end-to-end.
---

# Ship

One concern → one branch → merged into `main` → **proven live** — executed end-to-end without
pausing to report status (2026-07-04 censor precedent `friction-shallow-first`; the standing
autonomy grant in `CLAUDE.md` → Standing Autonomy). This skill COMPOSES the existing machinery —
it introduces no new predicate; every step names the script that owns it.

Status words match `.agents/skills/closeout/SKILL.md` step 5 and are never blurred: **merged**
(`git merge-base --is-ancestor SHA origin/main` exits 0 after a fetch), **live** (the live
checkout contains the SHA and `scripts/check-live-checkout.py` prints `state=coherent`;
`scripts/sync-release.sh` reconciles that checkout, never a hand fast-forward), **observed**
(runtime evidence of the behavior itself: probe output, beat log line, sensor receipt).
Agent sessions never wait on PR state — no poll, no sleep loop, no synchronous waiter.

## Steps

1. **Isolate + implement.** Work in a git worktree on a topic branch cut from `origin/main`,
   named by intent (`feat/`, `fix/`, `heal/`, `chore/`, `docs/`, `refactor/` — CLAUDE.md → Merge &
   Branch Protocol). One concern per branch; stage explicitly with `git add <path>`, never `-A`.
   For a one-file docs append, use `scripts/ship-docs.sh <slug> "<msg>" <file…>` instead of steps
   2-4 — it is this whole skill in one command for the docs class.
2. **Gate scoped to the diff.** `bash scripts/verify-scoped.sh` — it maps changed paths to only
   the gates they implicate and names every skipped gate. Fix root-to-leaf and re-run until green.
   Never hand-run the full matrix for a scoped diff; never chase a gate the diff doesn't implicate.
3. **Push + PR.** Push the branch, `gh pr create` with the green gate run cited in the body.
4. **Merge on the predicate, not on memory.** Read `logs/AUTONOMY_PAUSED` first — a marker whose
   `prohibitions:` forbid merges means no submission and no merge. Then
   `scripts/merge-policy.sh <PR#> --repo OWNER/NAME`:
   - exit 0 CLEARED → it prints `MERGE-MODE` and an exact `MERGE-HEAD`. Where the charter grants
     the single-owner fast lane (this repo), merge that head once:
     `gh pr merge <PR#> --repo OWNER/NAME --squash --match-head-commit <MERGE-HEAD>`. Elsewhere
     submit it once: `scripts/merge-drain.py --repo OWNER/NAME --pr <PR#> --expected-head <MERGE-HEAD>`,
     then return control. `QUEUED` is durable GitHub ownership, not merged.
   - exit 2 HOLD → required checks still running, a draft, or a website-sensitive rollup not yet
     green. Return control and continue other lanes; the recurring merge drain owns the later
     observation. Never wait, poll, or retry from the session.
   - exit 3 BLOCKED → repair the real conflict or missing check, then re-run once. Never force.
   `scripts/await-pr.sh` is retired and fails closed; do not cite or invoke it.
   Non-deploy verdicts count **required** checks only; advisory checks and automated reviews never
   hold a merge (residual findings become follow-up issues; at most two fix-on-review rounds).
   Website-sensitive PRs require the implicated local build/deploy predicate in the scoped
   gate run — merging IS the deploy.
5. **Prove it LIVE — the artifact, not the merge.** A merged PR is not a shipped change
   (2026-07-24 insights lineage: a redesign verified only on synthetic renders; the live surface
   never changed). Report the evidence-bound words separately: "merged" after the fetch-and-
   ancestor check, "live" only once `scripts/check-live-checkout.py` prints `state=coherent` (an
   installed-runtime change also needs `scripts/check-runtime-lag.py`; exit 77 is unmeasured,
   never pass), "observed" only with runtime evidence of the behavior itself. Never write
   "verified end-to-end" without observed. For any user-visible/product-facing claim, run
   `python3 scripts/ship-gate.py` (reachable deployed URL, from `spec/ship-surfaces.json`) or the
   change's own probe (`scripts/probe-runtime-adapter.py`, `scripts/experience-audit.py`,
   `scripts/link-health.py` — whichever owns the surface). If the live checkout lags, the owner is
   `scripts/sync-release.sh`, never a hand fast-forward. If the artifact needs regeneration after
   merge, regenerate and push it — the engine merging is not the profile changing.
6. **Close out.** Run the session-bound predicate, never the no-argument estate diagnostic:
   `scripts/no-tasks-on-me.sh --session-id ID --worktree PATH --receipt RECEIPT --json`, bare, twice,
   quoting both exit codes (both 0; the second mutates nothing). `scripts/credential-wall.py --check`
   covers any secret the change used. Loose work is committed and published; then the relay: what
   shipped, predicate verdicts as proof, one registry pointer for anything homed. No caveat tail.
   For a full session closeout, run `/closeout` (`.agents/skills/closeout/SKILL.md`) — this step is
   its per-change instance.

## Gate

A change is SHIPPED only when: the implicated scoped gates are green, the PR is **merged** through
the step 4 rail (`merge-policy.sh` CLEARED, then an exact-head `gh pr merge` or one `merge-drain.py`
submission), the artifact is **live** and **observed** (step 5 predicate exit 0 or a cited probe),
and the session predicate in step 6 exits 0. Merged-but-not-live is NOT shipped — say "merged, not
live" plainly, with the failing probe output.
