# S10 — Axis coverage: make "every axis is green" one command, not a hand-loop

## Objective

Each governance axis has a drift predicate that is individually robust. **The set of axes has
none.** No shipped command asserts that every axis is green right now; establishing it requires
hand-looping the predicates in a shell, which is exactly the hand-maintained knowledge this whole
registry pattern exists to delete.

Measured 2026-07-29 on `6bac5cad`:

- **27** `scripts/check-*.py` on disk. **19** carry a `command:` entry in
  `institutio/governance/gates.yaml`; **9** appear in `institutio/governance/sensors.yaml`
  (4 in both) → **3 are wired nowhere**: `check-review-engine.py`,
  `check-ask-gate-migration.py`, `check-student-email-grounding.py`.
- `scripts/verify-whole.sh` — the whole-system predicate — invokes **4** of the 27 literally
  (`check-agent-docs`, `check-dispatch-admission`, `check-gates`, `check-removal-acceptance`).
- `.github/workflows/pr-gate.yml`'s `LIMEN_PRGATE_SCOPED=0` "full literal matrix" fallback lists
  **7**, omitting `check-corpora`, `check-convergence`, `check-atom-homing`, `check-custody`,
  `check-ideal-forms`, `check-session-streams`, and more.
- `check-gates.py`'s consumers-derive check F verifies only that `verify-whole.sh` derives its
  **file_set** lists via `verify.py --print-files` — nothing about its check-script invocations.
- None of the six named axis predicates appear in `sensors.yaml`, so `scripts/omega.sh` does not
  cover them either.

Per-axis coverage is therefore real but *conditional*: it holds only across the union of whichever
PRs happened to touch which paths. **This is the CORPORA founding defect one level up** — two
consumers each carrying their own wrong copy of a list, both wrong the same way, with nothing to
catch it.

Re-measure every number above before acting on it. This document is a hypothesis until you verify it.

## Mission

Make the axis set itself declared data, so a forgotten axis is a red check rather than a silence.

1. **Ratchet the unwired set.** Add `institutio/governance/unwired-checks-baseline.txt` — the
   committed ceiling of `check-*.py` files registered in neither `gates.yaml` nor `sensors.yaml`,
   in the shape of the sibling baselines (`orphan-params-baseline.txt`,
   `atom-residue-baseline.txt`). Extend `check-gates.py` with a check asserting every
   `scripts/check-*.py` is gate-registered, sensor-registered, or listed in that baseline — and
   that the baseline only ever **shrinks**. A new predicate that nothing runs then cannot merge.
2. **Make the two literal fallbacks derive.** `verify-whole.sh` and pr-gate's full-literal-matrix
   step must build their check list from the registry rather than restate it. Prefer extending
   `scripts/verify.py` (which already owns registry-derived gate selection) over teaching either
   consumer to parse YAML itself — a third copy of "how to read gates.yaml" would re-commit the
   defect while fixing it.
3. **Bind each axis to an ideal form.** CUSTODY (8th axis, #1615) and STREAMS (9th, #1612) each
   shipped a registry, a predicate and a gate row with **no `IF-*` entry** in
   `institutio/governance/ideal-forms.yaml` — the identical gap IF-ATOM-HOMING had when the 6th
   axis shipped. A defect that recurs across three consecutive axes is unenforced coupling, not an
   oversight. Assert the binding, and add the two missing ideals with a `probe` or a required
   `probe_absent_reason`.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible registry and predicate work.
- Retained gates: destructive, credential, paid-spend, public-send, runtime/host mutation.
- **Do not wire the three unwired predicates by fiat.** `check-review-engine.py` and
  `check-student-email-grounding.py` may have deliberate reasons to be off (network dependence,
  frozen-receipt scope). Record each in the baseline with its reason; deciding their fate is not
  this domain's job — *counting* them is.
- **This domain adds no new axis.** It closes the coupling between the axes that exist. Resist
  minting a tenth registry to govern the nine.

## Fan-out

At most **2** children, only via `limen conduct split <parent_run> --packet`, which reserves each
child against this session's lineage before launch. Never nest a git worktree inside this one — the
reclaim organ sweeps roots, so a nested worktree leaks. Tier every child explicitly; no worker
inherits this session's model.

## Constraints

Fresh branch `feat/axis-coverage-registry` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh` as the push gate; `merge-policy.sh` → `await-pr.sh <PR#> --merge`.
**Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s10-axis-coverage`. The STREAMS registry derives this domain's settled
state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must
also change something outside the registry and `docs/{plans,continuations}/` — bookkeeping
records an outcome, it cannot produce one.

## Done

`check-gates.py` green with the new coverage check present and the baseline committed; **prove the
failure mode** by adding a scratch `scripts/check-nothing.py` and observing a nonzero exit, not by
reading the code. `verify-whole.sh` and pr-gate's literal matrix both derive their check list from
the registry — verified by adding a gate row and seeing both pick it up with no second edit.
`check-ideal-forms.py` green with `IF-CUSTODY` and an ideal for STREAMS present. Re-running mutates
nothing.
