# Contributions Organism — SPECVLVM — CHARTER (the mirror)

> Doctrine: see `KERNEL.md`. Outward to learn inward; community and name
> recognition are byproducts of genuine value; the organ never sends.

## What it rivals

A big-tech **Open Source Program Office** (the Google/Microsoft OSPO) fused
with a guild's journeyman practice: the standing institution that turns
scattered upstream PRs into a disciplined program — targets chosen for what
their wiring can teach, contributions tracked through one ledger, knowledge
routed back into the house, reputation accruing as a matter of record instead
of memory.

## The org-chart (AI roles, human-supervised)

| Role | Runs | Never |
|---|---|---|
| Scout (fieldwork) | discovers upstream targets worth learning from; vets norms + CONTRIBUTING bars | picks a target for reputation alone |
| Orchestrator | initializes `contrib--*` workspaces (fork, seed, journal, registry entry) | pushes to the upstream itself |
| Monitor | tracks PR lifecycle + staleness against the stagger protocol | posts a bump — bumps are queued receipts |
| Backflow router | routes what each contribution taught into the receiving organs | invents learnings not evidenced in the work |
| Mirror keeper | renders the proof surface + health signal from hub-ledger outputs | scrapes private sessions; publishes local paths or notes |

Every outbound act — PR submission, comment, bump, social post — is staged as
a receipt and fired by the human hand. The organ's autonomy is inward-facing:
tracking, rendering, routing, reconciling.

## The workflows it runs

1. **Scout** — a candidate upstream becomes a vetted target with its mandate
   named: *what wiring do we want to study here?*
2. **Workspace** — the orchestrator opens a `contrib--*` tracking workspace;
   the contribution is authored there under the upstream's own Standard.
3. **Campaign** — engine B's sequencer (UNBLOCK → ENGAGE → CULTIVATE →
   HARVEST → INJECT) carries the relationship; all engagement sends are
   human-gated.
4. **Mirror** — `scripts/contributions-organ.py` re-renders the proof surface
   on the beat: merged · open · no-PR · closed · protocol-due · post-close.
5. **Backflow** — merged (or closed-with-learning) contributions route their
   lessons inward via the backflow manifest; the mirror tallies the flow so
   the *inward* product stays visible next to the outward proof.

## Inputs / outputs

- **Consumes:** the hub ledger (`organvm/contrib` `LEDGER.yaml`, or the
  committed cache when the local checkout is absent); the backflow manifest
  (`organvm-corpvs-testamentvm/backflow-manifest.yaml`, optional); the
  PLAN-06 owner packets (`docs/current-session-fanout/PLAN-06-contrib-mirror.md`).
- **Produces:** `organs/contributions/MIRROR.md` (public-safe proof surface),
  `logs/contributions.json` (health signal), and the product ledger's
  `contrib-mirror` outward-path records (`scripts/product-ledger.py` already
  consumes the same hub ledger).

## Standing estate (what this institution owns)

| Layer | Where | State at charter time |
|---|---|---|
| Hub (state surface) | `organvm/contrib` — generated `LEDGER.yaml`/`LEDGER.md` via `refresh-ledger.py` | live on GitHub; local checkout absent; seed root missing (PLAN-06-OWNER-01) |
| Engine A | `a-organvm/organvm-engine` → `organvm_engine.contrib` | present; ledger-backed discovery pending (PLAN-06-OWNER-02) |
| Engine B | `a-organvm/orchestration-start-here` → `contrib_engine/` | present, 111+ tests; parity map pending (PLAN-06-OWNER-03) |
| Workspaces | 22+ `organvm/contrib--*` repos | live; ~19 open upstream PRs, first merges landed |
| Backflow | `organvm-corpvs-testamentvm` — manifest + `pr-status-checker.py` | live; 50 signals routed across 5 organs at first count |
| Mirror | `organs/contributions/MIRROR.md` + `logs/contributions.json` (this organ) | **this charter's first proof** — resolves PLAN-06-OWNER-04 |
| Inbound | Omega H4 — attract 3+ external contributions; first absorption: adenhq/hive | in progress (tracked upstream in `orchestration-start-here` #142/#143) |

## First proof

The mirror renders from real hub-ledger data (or an honest staleness receipt),
`logs/contributions.json` stamps the beat, and this kernel/charter pair is
registered in `organ-ladder.json` — the institution exists in the census with
its whole prior estate converged under it instead of re-litigated.
