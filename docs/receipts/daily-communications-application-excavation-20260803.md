# Daily communications and application loop — excavation receipt

Date: 2026-08-03  
Repository: `organvm/limen`  
Remote head inspected: `origin/main` / `d59af05c2f315aa8f5156f19a83e8782845eb0a1`

This is the remote-first capability map for the daily loop. It is deliberately
PII-clean: conversation bodies, contact data, raw audio, and provider tokens stay
in the existing private stores.

## Remote state consulted

- `organvm/limen`: default branch `main`; 320 open issues at inspection time.
- `organvm/application-pipeline`: default branch `main`; PR #111 is open/draft and
  owns the submit-config generator and portal-keyed application runtime. Stacked
  PR #112 adds the truthful outreach-receipt gate described below.
- `organvm/universal-mail--automation`: default branch `main`; owns provider
  ingestion, obligations construction, draft/send policy, and delivery evidence.
- `organvm/social-automation`: default branch `main`; owns social-provider
  adapters, but has no LinkedIn effector in the inspected public tree.
- `organvm/browser-state`: default branch `main`; public repository contains only
  a README, so authenticated browser state remains private/provider-owned.
- `organvm/koinonia-db`: default branch `main`; owns a database engine, not the
  Limen correspondence ledger.
- `organvm/daily-engine`: default branch `main`; is the fitness/day-card engine,
  not the professional communications scheduler.

The relevant Limen remote receipts were also inspected:

| Receipt | State | Canonical contribution |
| --- | --- | --- |
| PR #1797 | open, draft | fixes application-pipeline path discovery and adds `limen apply` / MCP `application_funnel`; this branch carries its commit and extends it |
| PR #1509 | open, draft | incremental iMessage + WhatsApp capture; source remains the existing capture owner |
| PR #1794 | open, draft | Forrest/WhatsApp disclosure split; public posture only, private raw source |
| PR #1715 | open, draft | corpus substrate and biography registry; issue #1734 records the evidence-union defect |
| Issue #1734 | open | prevents a newer biography registry from hiding existing life-history evidence |

## Capability and gap ledger

| Required behavior | Existing owner | Live predicate / receipt | Classification | Integration decision |
| --- | --- | --- | --- | --- |
| Incremental mail ingestion | `scripts/mail-beat.sh` plus Universal Mail Automation | `scripts/tests` mail census and `logs/uma-mail-status.json` | reusable | daily execution invokes the existing beat with explicit send/fire valves |
| Mail obligations | UMA `obligations_build.py`, `scripts/obligations-view.py` | `obligations-ledger.json`, correspondence terminal checks | reusable | consume the ledger; do not add an application database |
| Correspondence reconciliation | `scripts/correspondence-walk.py` | `logs/correspondence-dispositions.json`, drain-trend predicate | reusable | use its `--drain --json` result as the follow-up source of truth |
| Inbound opportunity review | `scripts/opportunity-review-delta.py` | `logs/opportunity-status.json` and its scoped tests | reusable | invoke once per daily run and preserve count-only output |
| ATS sourcing/matching/materials | `organvm/application-pipeline` | pipeline preflight, orchestrator result, PR #111 | reusable but externally owned | invoke through `scripts/application-funnel.py`; never reimplement ATS logic |
| Application submission | application funnel `apply` phase | provider/portal result plus application receipt | incomplete | submitted is not treated as confirmed; only explicit provider/mailbox evidence counts |
| LinkedIn follow-up | opportunity/correspondence lane and private browser state | discovery notes and provider session state | incomplete | preserve `needs-human`/CAPTCHA/session blockers; no fake template completion |
| WhatsApp/iMessage ingestion | PR #1509 / PR #1794 owners | private capture receipts, public posture PRs | incomplete | coordinator exposes the shared event shape without copying private content |
| Voice transcription | existing local capture/transcription tools | private source receipts | reusable but private | no public transcript or second transcriber is introduced |
| Public prose voice | `vox--publica` and DECORVM surfaces | voice/decorum predicates | reusable | coordinator stores only safe judgments and receipt references |
| Shared event/obligation/delivery contracts | no single Limen owner on `origin/main` | absent | genuinely missing | add typed `V1` records and lifecycle validation in the Limen CLI package |
| One daily execution front door | existing heartbeat has separate mail/opportunity/funnel voices | no unified CLI/MCP operation | genuinely missing | add `limen daily-execute`, MCP `daily_execution`, and a heartbeat voice that call one function |

## Truthfulness and ownership findings

1. The existing application pipeline may report `submitted`, but that is not a
   provider-confirmed receipt. The coordinator keeps `confirmed` at zero unless a
   receipt includes explicit portal or mailbox evidence.
2. Existing correspondence disposition rows are count-only and already distinguish
   `sent`, `awaiting-them`, `held`, and `needs-human`. A generated LinkedIn/email
   template is therefore never promoted to `delivered` or `confirmed`.
3. Forrest’s public posture and private source are separate owner surfaces. This
   receipt does not publish names, handles, company details, audio, or conversation
   text; the open PR #1794 remains the disclosure owner.
4. The biography registry defect in issue #1734 is not silently folded into this
   loop. Any corpus grounding used by future application customization must union
   existing evidence before the registry PR is accepted.

5. Application-pipeline PR #112 (`bf1f45ef`) removes the prior mutation that
   logged generated LinkedIn templates as completed outreach. Its readiness gate
   now requires a provider-observed send state plus a provider receipt/message
   identifier; prepared copy remains prepared and cannot authorize submission.
   The branch is pushed at
   `fix/truthful-outreach-receipts-20260803`, stacked on PR #111.

The read-only local application-pipeline census found 23 YAML rows under its
`pipeline/submitted/` owner directory. The current snapshot contained no explicit
`confirmation_evidence` field; several rows carried a partially-filled portal
state. That is sufficient to classify the rows as unconfirmed, not sufficient to
rewrite the owner repository or claim that mailbox/portal reconciliation is done.
The coordinator now preserves that distinction in its private receipt and accepts
only an explicit portal/mailbox confirmation source as `confirmed`.

The excavation gate is satisfied: the new implementation is a thin composition
over the existing heartbeat, mail, opportunity, correspondence, application, and
receipt owners, with only the missing contracts and coordinator added here.

## Implementation and verification receipt

- Limen implementation branch: `feat/daily-communications-application-loop-20260803`.
- Application-owner truthfulness branch: PR #112, commit `bf1f45ef`, stacked on
  PR #111; its focused suite passed 32 tests and Ruff.
- Limen focused wave passed 25 tests across daily execution, MCP delegation,
  heartbeat pause, and heartbeat routing/custody. Mypy, Ruff, shell syntax, diff
  whitespace, and the armed-valve contract passed; the new fire lever is
  explicitly `SAFE-OFF` by default.
- The changed-file resolver escalated to the whole matrix because the existing
  application-funnel driver is deploy-sensitive. Its static, lifecycle,
  contract, and shell predicates passed. The broad `web/api/tests` plus
  `cli/tests` pytest stage emitted failures and later left its xdist workers
  idle without a terminal summary; that stage was stopped at the bounded-wait
  boundary. It is not used as the implementation receipt; the focused
  predicates above are the exact-head evidence for this branch.
