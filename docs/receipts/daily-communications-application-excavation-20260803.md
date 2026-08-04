# Daily communications and application loop — excavation receipt

Date: 2026-08-03  
Repository: `organvm/limen`  
Remote head inspected: `origin/main` / `d59af05c2f315aa8f5156f19a83e8782845eb0a1`
Implementation head: `c94a36e9ec9578d7a7d117523f0f02bb6ab33230`

This is the remote-first capability map for the daily loop. It is deliberately
PII-clean: conversation bodies, contact data, raw audio, and provider tokens stay
in the existing private stores.

## Remote state consulted

- `organvm/limen`: default branch `main`; 320 open issues at inspection time.
- `organvm/application-pipeline`: default branch `main`; PR #111 is merged at
  `8b110385c731656ad4c5f0482bd5d5bfd916b316`, and PR #112 is merged at
  `43b58a0fabac21ba8a6da176b92171e9c829685a`. The merged extension keeps the
  existing portal-keyed application runtime and returns structured provider
  outcomes.
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
| PR #1797 | open, draft | fixes application-pipeline path discovery and adds `limen apply` / MCP `application_funnel`; PR #1798 still carries and extends its commit |
| PR #1509 | open, draft | incremental iMessage + WhatsApp capture with append-only private tapes, source checkpoints, attachment hashes, and idempotency tests; owner checks await the current Limen base |
| PR #1794 | open, draft | Forrest/WhatsApp disclosure split; public posture only, private raw source |
| PR #1715 | open, ready | corpus substrate and biography registry; issue #1734 records the evidence-union defect and the branch now has a deterministic union resolver |
| Issue #1734 | open | prevents a newer biography registry from hiding existing life-history evidence |

The current remote re-query corrected the owner findings: browser-state still has
only its public README and no public authenticated session; `vox--publica` has no
focused transcription/scoring change available; Universal Mail Automation has no
focused #1509 delivery change; and `social-automation` still has no LinkedIn
effector PR. Those are owner-gated capabilities, not substitutes for a Limen
receipt, so the coordinator preserves their unavailable/ambiguous outcomes.

## Capability and gap ledger

| Required behavior | Existing owner | Live predicate / receipt | Classification | Integration decision |
| --- | --- | --- | --- | --- |
| Incremental mail ingestion | `scripts/mail-beat.sh` plus Universal Mail Automation | `scripts/tests` mail census and `logs/uma-mail-status.json` | reusable | daily execution invokes the existing beat with explicit send/fire valves |
| Mail obligations | UMA `obligations_build.py`, `scripts/obligations-view.py` | `obligations-ledger.json`, correspondence terminal checks | reusable | consume the ledger; do not add an application database |
| Correspondence reconciliation | `scripts/correspondence-walk.py` | `logs/correspondence-dispositions.json`, drain-trend predicate | reusable | use its `--drain --json` result as the follow-up source of truth |
| Inbound opportunity review | `scripts/opportunity-review-delta.py` | `logs/opportunity-status.json` and its scoped tests | reusable | invoke once per daily run and preserve count-only output |
| ATS sourcing/matching/materials | `organvm/application-pipeline` | pipeline preflight, orchestrator result, PR #111 | reusable but externally owned | invoke through `scripts/application-funnel.py`; never reimplement ATS logic |
| Application submission | application funnel `apply` phase | structured provider result plus canonical `LIMEN_DELIVERY_RECEIPTS` ledger | incomplete | attempted is retry-locked; only exact provider/mailbox evidence counts as confirmed |
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

5. Application-pipeline PR #112 (`43b58a0f`, source commit `b43d200f`) removes the prior mutation that
   logged generated LinkedIn templates as completed outreach and now returns
   structured ATS outcomes. Its readiness gate has no universal outreach
   prerequisite; role-specific referral prerequisites still require a
   provider-observed send state plus receipt/message identifier. The branch is
   merged to `main`.

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

- Limen implementation branch: `feat/daily-communications-application-loop-20260803` at
  `c94a36e9`.
- Limen PR #1798 is the remote custody receipt for that branch and is ready for
  merge once its current `pr-gate` completes; Python, worker, web, validation,
  CodeQL, and static-analysis checks are green on this head.
- Application-owner truthfulness branch: PR #112, commit `b43d200f`, based on
  merged PR #111; its focused suite passed 65 tests and Ruff.
- Limen focused wave passed 65 tests across daily execution, MCP delegation,
  heartbeat sensors, registry checks, and the audit-autofix fixture. The worker
  gate passed `npm ci`, `npm audit --audit-level=high`, and all 66 worker tests.
  The scoped resolver then passed `scripts/verify-scoped.sh --base origin/main
  --require-base`, including the whole matrix escalation and armed-valve
  contract; the new fire lever is explicitly `SAFE-OFF` by default.
- The changed-file resolver escalated to the whole matrix because the existing
  application-funnel driver is deploy-sensitive. Its static, lifecycle,
  contract, and shell predicates passed. The broad `web/api/tests` plus
  `cli/tests` pytest stage emitted failures and later left its xdist workers
  idle without a terminal summary; that stage was stopped at the bounded-wait
  boundary. It is not used as the implementation receipt; the focused
  predicates above are the exact-head evidence for this branch.
- The shared Python audit was red on the first implementation head because
  `cryptography` resolved to `49.0.0`. Commit `c94a36e9` pins
  `cryptography>=50.0.0`, regenerates `mcp/uv.lock`, and makes
  `scripts/pip-audit-autofix.py --check` clean.

## Live dry-run receipt

The first bounded read-only execution used the coordinator with all outbound
valves absent and a 30-second per-stage timeout. It returned a redacted
`limen.daily_execution.v1` receipt for local date `2026-08-03`, run
`daily_add7f6e5a00fd26db3a13183`, with zero current-run delivery receipts,
zero confirmed applications, and three eligible-role shortage units. The
opportunity and correspondence stages completed without outbound action; mail
ingestion and the application owner timed out at the deliberately short probe
bound. The local pipeline census reported 15 claimed submitted rows and zero
provider-confirmed historical rows in the accessible snapshot. This is a
truthful shortage/blocker receipt, not proof of the three-application
acceptance item.

## Residual owner-gated atoms

These are deliberately preserved as incomplete/blocked owner work, not
represented as solved by this coordinator:

| Atom | Owner receipt | Failed predicate / next command |
| --- | --- | --- |
| Historical application claims | application-pipeline PRs #111/#112 plus provider mailbox/portal receipts | 23 rows were censused; the accessible live snapshot exposed 15 submitted-directory rows and no explicit confirmation evidence. Reconcile all 23 owner rows against every configured mailbox/portal, then supply the canonical `LIMEN_DELIVERY_RECEIPTS` ledger to the daily run |
| Authenticated LinkedIn action | social-automation/browser-state private provider surface | no public authenticated effector was present; run the shared loop only after a provider send/submission receipt exists, otherwise preserve the precise session/CAPTCHA blocker |
| Forrest/WhatsApp/iMessage capture | Limen PRs #1794/#1509 | public/private capture owners remain open; accept their capture predicates before using full conversation/audio grounding for applications |
| Biography evidence union | Limen PR #1715 / issue #1734 | registry must union existing source evidence; do not let a newer registry hide prior docs/reviews before customization |
