# S3 — Governance case law: 1,343 atoms into precedents and counted vacuums

## Precondition

`s1-homing-spine` merged. `institutio/governance/atom-homing.yaml` declares both kinds' contracts —
read the registry first and obey it.

## Objective

`decisions` = **877 atoms**, `vacuums` = **466 atoms**. Both un-homed as of 2026-07-29.

> **RE-MEASURED 2026-07-29 (later same day).** This section read *"12 capabilities, 7 converged,
> 5 lifting, **zero** unresolved rows"*. Now **14 capabilities — 8 converged, 5 lifting, 1
> unresolved** (`mirror-drift-detection`, added by #1611 as a counted vacuum under Rule #1).
> Reproduce:
>
> ```bash
> python3 -c "import yaml,collections; c=yaml.safe_load(open('institutio/governance/convergence.yaml'))['capabilities']; print(len(c), collections.Counter(v.get('status') for v in c.values()))"
> ```
>
> **The mission is unchanged and the argument below still holds** — 1 unresolved row against 466
> un-homed vacuum atoms is very nearly the same indictment as 0. Only the number moved. Do not read
> the existence of one counted vacuum as the work being started.

Re-measure before trusting these numbers.

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
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s3-governance-case-law`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must
also change something outside the registry and `docs/{plans,continuations}/` — bookkeeping
records an outcome, it cannot produce one.

## Done

`check-atom-homing.py` check C shows both kinds fully homed or bounded-dispositioned;
`check-convergence.py` green **with** the new unresolved rows present; residue baseline shrank; leak
clean. **State the precedent count you added and justify it** — a large number is a defect to
explain, not an achievement to report.
