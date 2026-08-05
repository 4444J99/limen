# The Gatekeeper Boundary — decision record (2026-07-08)

**Task:** `ARCH-gatekeeper-repository-owner-0704` — "Decide and activate the dedicated
gatekeeper repository boundary" (closeout residue from 2026-07-04: the keeper-of-records
surface exists and should be active; a separate gatekeeper repository was *probably* needed).

## Decision

**The gatekeeper is not a repository. It is the Limen gate surface** — the family of
executable gate predicates in `scripts/`, each wired to the station where its decision is
made. No `organvm/gatekeeper` repo is created.

- **TABVLARIVS stays in Limen** as the single-writer record keeper
  (`cli/src/limen/tabularius.py`, `scripts/tabularius-organ.py`, tickets inbox → fold →
  archive). The "keeper-of-records surface" the ask presumed is this, and it is live.
- **`organvm/custodia-securitatis` keeps its own charter** — an operational-security
  *records* registry (credential inventories, rotation logs, incident records). Records
  live there; **enforcement never does**. That records/enforcement line *is* the owner
  boundary this task asked to settle.

## Why (cascade: protocol → precedent → exploration → ideal-form)

1. **Federation, not fusion** (VIGILIA, limen#232/#234): institutions whose substrate is
   the board and the beat live *in* Limen and federate there. Every gate below gates
   Limen's own lifecycle — moving them out splits the gates from the beat that runs them.
2. **Seams predict drift** (retro 2026-06-24→07-08, encoded in `ask-gate.py`): work
   survives when it is seam-independent. A dedicated repo adds a permanent seam (second
   checkout, second CI, cross-repo version skew) and buys nothing a path prefix doesn't.
3. **Permissions don't need repo walls** (App-not-orgs): scoping is done by the GitHub
   App / token lanes, not by repository boundaries.
4. `custodia-securitatis` was inspected before deciding (option b in the ask): its
   charter is records, and fusing execution into a records registry inverts it.

## The gate surface (derived from live wiring, 2026-07-08)

| Station | Gate predicate | What it refuses |
|---|---|---|
| beat 0a | `creds-hydrate.py --verify` | dead credentials pretending to be homed |
| beat 0e | `armed-valve-audit.py --check` | deliverable valves silently OFF (unlevered) |
| beat 0f | `ship-gate.py --check` | product-facing "done" with no reachable artifact |
| beat 0g | `heal-convergence.py --check` | chronic heal loops that never converge |
| beat 0h | `ask-gate.py --audit` (report-only) | predicate-less / unbounded asks at intake |
| beat | `tabularius-organ.py` | any board write that isn't a folded ticket |
| merge seam | `merge-policy.sh <PR#>` | merges that would break the live site/API |
| session seam | `no-tasks-on-me.sh` + `credential-wall.py --check` | closeouts that hand the operator a list |
| session seam | `claude-workflow-guard.py` (SessionEnd) | untiered expensive-tier fan-outs |
| CI / verify | `verify-whole.sh` (runs `check-params.py`, gate regression tests) | hardcoded knobs; gate regressions |
| anytime | `dialogs-silenced.sh` | recurring permission/auth dialog classes |

**Activation proof:** every row above is already wired and running — beat steps in
`scripts/metabolize.sh`, merge seam in the Merge & Branch Protocol (CLAUDE.md), session
seam in the closeout discipline + SessionEnd hook, CI in `scripts/verify-whole.sh`. There
is nothing left to "activate"; the ask's remaining atom was the *decision*, recorded here.

## Reversal path

This record is reversible. If a future gate must gate **Limen itself from outside** (the
only structural reason for an external gatekeeper), the first move is still not a repo:
it is a bot-scoped permission lane. A dedicated repository becomes justified only when an
external party must run the gate without Limen checkout access — none does today.
