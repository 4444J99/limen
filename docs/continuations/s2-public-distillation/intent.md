# S2 — Public distillation: 1,194 atoms into ideal forms and schemas

## Precondition

`s1-homing-spine` merged. `institutio/governance/atom-homing.yaml` declares both kinds' contracts —
**read the registry first and obey it**; do not re-derive the home from this document. The registry
owns the answer.

## Objective

`functionality-to-repeat` = **518 atoms**, `schema-proposals` = **676 atoms**. Both un-homed as of
2026-07-29. Re-measure before trusting these counts.

Home both kinds **by distillation**:

- **functionality-to-repeat 518 → `docs/IDEAL-FORMS-LEDGER.md` `IF-*` entries.** An IF entry is a
  **generalization**, never an atom. 518 atoms cluster to a *handful* of entries. The ledger has no
  validator today — author one in this domain: an IF entry must carry its ideal form, a **measured**
  distance (with the date and method of measurement), and a named predicate.
- **schema-proposals 676 → the registries and specs each one amends;** genuine portable contracts to
  `spec/`. **Most land as private candidates** in `organvm-corpvs-testamentvm`, not as public
  schemas. A schema no consumer reads is not a schema; it is a wish with a filename.

## The volume discipline is the point

If your output is proportional to your input, you have **transferred** rather than distilled — the
failure mode this entire arc exists to prevent. `check-atom-homing.py`'s G-check catches a
wholly-deferred kind but **not a padded ledger**. You are the only guard against padding. A
518-entry ideal-forms ledger is a worse outcome than no homing at all, because it looks done.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible work.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- **Atom statement text may never enter the public `organvm/limen` tree.** Every IF entry is *your*
  generalization in your own words. `check-atom-homing.py`'s D-check (leak: no statement shingle in
  the public tree) fails the PR if you paste.

## Fan-out

At most **8** children, only via `limen conduct split <parent_run> --packet`, which reserves each
child against this session's lineage before launch. Never nest a git worktree inside this one — the
reclaim organ sweeps roots, so a nested worktree leaks.

Pattern: **partition → explicitly tiered workers → audit script → commit.** No worker inherits this
session's model (`scripts/claude-workflow-guard.py` audits untiered expensive fan-out post-hoc, and
its default ceiling is **1** Opus subagent per session transcript — tier the rest cheaply).

## Constraints

Fresh branch `feat/home-functionality-and-schemas` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s2-public-distillation`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must
also change something outside the registry and `docs/{plans,continuations}/` — bookkeeping
records an outcome, it cannot produce one.

## Done

Both kinds show `homed + dispositioned == total` in `check-atom-homing.py` check C; the residue
baseline **shrank**; leak check clean; the new IDEAL-FORMS-LEDGER validator exits 0 and is
gate-wired.
