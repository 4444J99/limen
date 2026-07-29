# S5 — Commercial offerings: 54 atoms into the funnel

## Precondition

`s1-homing-spine` merged. `institutio/governance/atom-homing.yaml` declares the contract — read the
registry first and obey it.

## Objective

`client-offerings` = **54 atoms** — the smallest kind, the only one with direct revenue consequence,
and the sole input to S8's mint gate. Un-homed as of 2026-07-29.

The constellation program **already exists** at `organs/consulting/constellation/`;
`constellation-streams.py::find_echoes` is a **converged** owner in
`institutio/governance/convergence.yaml`. **Do not build a second one** — a new engine where an owner
exists is a regression ("never build the 7th").

Home all 54 into the `organs/consulting/` funnel and the constellation register, and emit the demand
evidence S8 consumes:

1. Each offering distills to a funnel entry with a real stage on the ladder
   `idea → dossier → building → mvp → live → funnelized`, and a tier (T1/T2/T3).
2. The constellation **public register is first-name slugs only** — surnames are mechanically banned
   by the program's Rule #2, and the private overlay is ARCA-sealed. **Verify the ban is enforced by
   a predicate, not by your carefulness.** If no predicate exists, that absence is the first thing
   you ship in this domain.
3. Emit the **G1 demand-evidence reference** S8's `repo-genesis` gate requires: an extract path,
   dossier path, or `CONST-`/`IRF` id per offering. *"I want it"* is not evidence.
4. **review-before-rails holds:** an offering earns a rail by *reviewed demand*, never by enthusiasm.

## Why 54 atoms get their own domain

It is the only kind whose homing produces revenue surface, and it is the sole input to S8's mint
gate. Bundled into a bulk homing pass it gets buried under 877 decisions and never resurfaces.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible work.
- Retained gates: destructive, credential, paid-spend, **public-send**, runtime/host mutation.
- Atom statement text may never enter the public `organvm/limen` tree. **Surname-free, PII-free** —
  `organs/consulting/` and the constellation register both publish; `scripts/no-tasks-on-me.sh`
  enforces PII-cleanliness.

## Fan-out

At most **4** children, only via `limen conduct split <parent_run> --packet`. Never nest a git
worktree inside this one — the reclaim organ sweeps roots, so a nested worktree leaks. Tier every
child explicitly; no worker inherits this session's model.

## Constraints

Fresh branch `feat/home-client-offerings` off updated `origin/main`, one concern.
`scripts/verify-scoped.sh`; `merge-policy.sh` → `await-pr.sh --merge`. **Claim the settlement with an anchored trailer in the merge commit message** — a line at
column 0 reading `Settles: s5-commercial-offerings`. The STREAMS registry derives this domain's
settled state from that claim, and *only* from it: an unanchored mention no longer counts (it once
settled `s10-axis-coverage` off a docs commit that merely named it). The claiming commit must also
change something outside the registry and `docs/{plans,continuations}/` — bookkeeping records an
outcome, it cannot produce one. **S8 unblocks on this**, so a missing trailer strands that domain.

## Done

`check-atom-homing.py` check C shows `client-offerings` fully homed; the surname ban has a **passing
predicate** you can point at; every offering carries a G1-admissible demand-evidence reference;
`scripts/no-tasks-on-me.sh` exits 0.
