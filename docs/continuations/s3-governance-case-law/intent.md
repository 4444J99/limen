# S3 — Governance case law: 1,343 atoms into precedents and counted vacuums

## Precondition

`s1-homing-spine` merged. `institutio/governance/atom-homing.yaml` declares both kinds' contracts —
read the registry first and obey it.

## Objective

`decisions` = **877 atoms**, `vacuums` = **466 atoms**. Both un-homed as of 2026-07-29.
`institutio/governance/convergence.yaml` today: 12 capabilities, 7 converged, 5 lifting, **zero
unresolved rows**. Re-measure before trusting these numbers.

Home both kinds:

- **decisions 877 → `censor/precedents.jsonl`** for the ones that **bind future behavior**;
  stream-local design decisions → private IRF in `organvm-corpvs-testamentvm`.
  **Precedents stay curated.** 877 rows destroys the file's function: a precedent is *consulted*, and
  a corpus nobody can read is consulted by nobody. Expect single digits to low double digits to reach
  precedent status. The rest are IRF — or they are nothing, and "nothing, with a reason" is a valid
  bounded disposition under the G-check.
- **vacuums 466 → capability-shaped ones become `convergence.yaml` `unresolved` rows** (`owner: null`,
  counted loudly per Rule #1); the rest become private `IRF-VAC` rows.
  A registry asserting "0 unresolved" while 466 vacuum atoms sit un-homed is declared data
  contradicting measurement — the exact defect class S6 is correcting one file over. **Do not
  reproduce it here.**

## Counted vacuums, not prose

An `unresolved` row **names** a capability with no chosen owner; it is not a paragraph of
description. `scripts/check-convergence.py` must stay green with the new rows, and its B-check
rejects prose owners — do not add one.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible work.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- **Atom statement text may never enter the public tree.** `censor/precedents.jsonl` **publishes**:
  a precedent is *your* restatement of the binding rule, never the atom. The D-check fails the PR on
  a pasted shingle.

## Fan-out

At most **8** children, only via `limen conduct split <parent_run> --packet`. Never nest a git
worktree inside this one — the reclaim organ sweeps roots, so a nested worktree leaks.
Pattern: partition → **explicitly tiered** workers → audit script → commit. No worker inherits this
session's model.

## Constraints

Fresh branch `feat/home-decisions-and-vacuums` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Include the string
`s3-governance-case-law` in the merge commit subject** — settled state is derived from
`git log origin/main --grep=s3-governance-case-law`.

## Done

`check-atom-homing.py` check C shows both kinds fully homed or bounded-dispositioned;
`check-convergence.py` green **with** the new unresolved rows present; residue baseline shrank; leak
clean. **State the precedent count you added and justify it** — a large number is a defect to
explain, not an achievement to report.
