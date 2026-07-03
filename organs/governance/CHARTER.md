# Governance Organism — CHARTER (the governance office)

> **Boundary:** an AI-run governance *operations* office that works under and for the human
> fiduciaries. It does not issue binding decisions, sign on behalf of entities, or replace board
> judgment. The humans ratify; the organ tracks, validates, and enforces between their decisions. See
> [KERNEL.md](KERNEL.md) for the full guardrails.

## What it rivals

A constitutional state's governance office or a foundation board — the **cursus honorum standard**:
not one founder with a spreadsheet, but a system where every role is earned in sequence, every
decision is traceable, every promotion is validated against the rules, and every entity's standing
is auditable at any moment. This organ supplies that system.

## The org-chart (AI roles, human-supervised)

| Role | Does | Human check |
|---|---|---|
| **The Senate / Board** (the humans) | entity formation, binding resolutions, ratification of promotions | — (these are the humans) |
| **Standing Clerk** | maintains the single source of truth: every member's current office, the offices held, and what is next | fiduciaries verify the register on any promotion |
| **Sequencing Auditor** | validates every promotion attempt against the cursus rules; the primary machine-enforcement role | fiduciaries ratify; the audit rejects skipped stages |
| **Entity Registrar** | tracks the legal standing of each entity (NPO, LLC, project commons); records what each may and may not do | fiduciaries confirm entity state matches legal reality |
| **Compliance Sentinel** | flags any action that would blur entity roles, skip a governance step, or bypass a rule | fiduciaries are final arbiter; sentinel never self-corrects |

## The workflows it runs

1. **Intake → standing.** Capture a new member or repo against the kernel (Member/Mandate/Standing/
   Standard/Governance). Assign them to their starting office (INCUBATOR). Output: a standing record.

2. **Promotion → audit.** When a member or repo claims advancement, the Sequencing Auditor validates
   the claim against the cursus rules. Output: PASS (with next office) or FAIL (with the rule violated).

3. **Seed → validate.** For every repo with a `seed.yaml`, run the contract validator against the
   canonical schema. Output: a validation report (pass/fail with line-level findings).

4. **Entity → register.** Track the legal state of each dual-entity component (NPO and LLC): formation
   status, mandates, fiduciary roles, and what each entity may not delegate to the other. Output: the
   entity register.

5. **Audit → log.** Every governance action is appended to the audit log with timestamp, actor, rule
   applied, and outcome. The log is append-only; entries are never amended. Output: the standing audit
   trail.

## First proof: the seed validator

The first two executable rules are `validate-seed.py`:

- **Rule #1: Valid Office** — a seed contract must declare `promotion_status` as one of the
  recognized offices in the sequence (INCUBATOR → ALPHA → BETA → STABLE → MATURE), and
  `implementation_status` must match. Skipping is a hard failure.
- **Rule #2: Structured edges** — `produces` and `consumes` blocks must be list-structured and
  explicit in partner targeting (`consumers` / `source`) when represented as mappings.

Run it:

```bash
python organs/governance/validate-seed.py path/to/seed.yaml
python organs/governance/validate-seed.py --fleet   # validate all seed.yaml files in the working tree
python organs/governance/validate-seed.py /path/to/seed.yaml --strict-graph
```

This is the micro instance: every repo in the ORGANVM estate is validated against the cursus on every
beat. The macro form is a standalone library any multi-repo ecosystem can import.

## Inputs / outputs

- **Inputs:** seed.yaml files (the standing declarations), entity formation documents, governance
  decisions recorded by fiduciaries.
- **Outputs:** standing records, audit trail, validation reports, entity register. All advisory to the
  fiduciaries; none self-executing.

## The dual-entity boundary (ORGANVM micro instance)

| Entity | Mandate | What it may NOT do |
|---|---|---|
| **Cind & Sol Foundation** (NPO, Panama) | open-project commons; grant-receiving; public benefit | generate private profit; execute commercial contracts for revenue |
| **Sovereign Systems LLC** (commercial) | service delivery; revenue generation; commercial contracts | receive charitable grants; claim public-benefit status |

The Compliance Sentinel watches every action against this boundary. Any action that would blur these
mandates is staged and surfaced — never self-resolved.

## Maturity and next steps

The governance organ is **75% mature** (maturing stage, rank 5 on the organ ladder). The entity
register with dual-entity boundary matrix, cursus validator, entity-integrity checker, and both
faces (macro + micro) are operational. The remaining lift to 90%:

1. Wire the governance beat into the heartbeat loop (`C_GOVERNANCE` cadence)
2. Operationalize the compliance sentinel as a continuous beat
3. Automate the append-only audit log
4. Close one complete promotion cycle with full validation trail

Validation:

```bash
python organs/governance/validate-seed.py --fleet --strict-graph
python organs/governance/validate-entities.py --fleet
```

Both validators are expected to pass "Concordia" on every governance beat.

---

*Companion documents: [`KERNEL.md`](KERNEL.md) (architecture + 5-primitive map),
[`MACRO-FACE.md`](MACRO-FACE.md) (portable standard), [`MICRO-FACE.md`](MICRO-FACE.md)
(ORGANVM's live instance).*
