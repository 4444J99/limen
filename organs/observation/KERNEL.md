# OBSERVATORY — KERNEL (Legibility & Traction)

> **Boundary (load-bearing):** OBSERVATORY is a **read-only** research organ. It studies public
> material, scores it, and *proposes* exactly one reversible experiment per day. It never mutates a
> public surface, never sends, never spends. The single irreducible human act it produces is the
> **approval** of a proposed experiment (a `his-hand-levers.json` lever) — never recited in chat,
> never auto-applied. Stars and counts are *signals*, never truth; the organ is built to resist the
> vanity metric it studies.

## Why this organ exists

An institution-sized body of work was built before one unmistakable public artifact existed through
which outsiders could understand, experience, use, and circulate it. The deficit is not production —
it is **activation, compression, concentration, and distribution**. The successful projects that trend
each day concentrate attention on one object, name one user, make one promise, and show that promise
becoming true immediately. Diagnosing *why they win and we don't* — honestly, controlling for
inherited advantage — is a system, not an opinion. This organ is that system.

The rival institution is a growth / DevRel desk fused with a competitive-intelligence team: a body that
watches the field, benchmarks its own surfaces against it, and runs one measured experiment at a time.

## The loop (OBSERVATORY is GITVS's twin)

GITVS runs `observe → diff → reconcile` on the estate's **configuration** (invariant: drift = ∅).
OBSERVATORY runs the *same loop* on the estate's **legibility & traction** — how the world understands,
trusts, uses, and circulates the estate. One loop, the standard organ **two faces** (see the FACE docs):

| | micro — internal legibility | macro — external legibility |
|---|---|---|
| **question** | are our own public numbers true & coherent? | why do comparable winners get adopted and we don't? |
| **sensor** | VVLTVS + `face-ownership.json` (already exist) | trending + competitor collectors (`gh api`) |
| **diff** | claim drift / severed pipe (already computed) | matched-cohort mechanism scoring → activation gap |
| **reconcile** | revive the pipe / project from the register (the missing effector) | one reversible experiment for the hero repo |

Both faces write **one** append-only evidence store and feed **one** experiment selector: the day's
single highest-priority gap — "your bio lies" or "winners demo above the fold and you don't" — flows
through the same priority formula and becomes one proposed lever. The reconciler is not a separate
system; it is internal-legibility gaps flowing through the same pipe.

## The 5-primitive kernel, mapped to the legibility domain

| Primitive | Legibility meaning | Concretely |
|---|---|---|
| **Member** | a repo / public surface | a comparable winner, a matched control, or one of our own surfaces |
| **Mandate** | a legibility / traction gap | a transferable mechanism we lack, or a claim of ours that is untrue/incoherent |
| **Standing** | drift / gap state | how far our surface sits from truth (internal) or from an adopted winner (external) |
| **Standard** | the priority formula + honesty rule | `explanatory_strength × controllability × similarity × EV ÷ activation_cost`; confounders discount strength; star count never enters a numerator |
| **Governance** | the experiment gate | the human approves the one proposed reversible experiment; the fleet may prepare it, the human publishes it |

This is the *same* kernel as the legal, governance, and GITVS organs — only the skin changes.

## Fractal deployment

- **MACRO** — a portable legibility-and-traction engine any operator can hold: study the field, prove
  your own surfaces true, get one reversible experiment at a time. See [`MACRO-FACE.md`](MACRO-FACE.md).
- **MICRO** — the ORGANVM estate's activation program: daily winners vs. matched controls, the estate's
  own claim-drift reconciled through the face-ownership loop, one experiment/day on the hero repo
  (`value-repos.json` rank 1). See [`MICRO-FACE.md`](MICRO-FACE.md).

## Invariant (the done-predicate)

`observatory doctor` exits 0 ⟺ the organ is wired, deterministic (a re-run reproduces byte-identical
derived state — the idempotent fixed point), shape-complete (each brief carries both faces + exactly 3
mechanisms, 3 confounders, 1 hero, 1 experiment, 1 measurement contract, no score using stars), and
**read-only against public surfaces** (default runs write only under `logs/observatory/`; the only
public action is a filed proposal). Offline is fail-open: live rungs SKIP, never a faked PASS.
