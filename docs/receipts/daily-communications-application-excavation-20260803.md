# Daily communications and application loop — excavation receipt

Date: 2026-08-03; final state re-query: 2026-08-04
Repository: `organvm/limen`  
Remote head inspected: `origin/main` / `f7c7461e229b47f24de1b42337284dca68637d89`
Implementation PR head: `71d463bc100ecd32d7be6a2fc07165436b25f9e1`; merged to `main` as
`3487abc5f427d6268e0b67e15e4e36880d8339e6`.

This is the remote-first capability map for the daily loop. It is deliberately
PII-clean: conversation bodies, contact data, raw audio, and provider tokens stay
in the existing private stores.

## Remote state consulted

- `organvm/limen`: default branch `main`; 320 open issues at inspection time.
- `organvm/application-pipeline`: default branch `main`; PR #111 is merged at
  `8b110385c731656ad4c5f0482bd5d5bfd916b316`, and PR #112 is merged at
  `43b58a0fabac21ba8a6da176b92171e9c829685a`. The merged extension keeps the
  existing portal-keyed application runtime and returns structured provider
  outcomes. Historical reconciliation is now merged as PR #113 at
  `13b9931bc080fe1a034ee61994dfa1412084e63e`.
- `organvm/universal-mail--automation`: default branch `main` at `37cf2bd`; owns
  provider ingestion, obligations construction, draft/send policy, and delivery
  evidence. Its existing `mail-send` lane has signed exact-target authorization,
  attachment checks, one-shot attempt claims, thread-aware replies, and
  SMTP-to-Sent verification; no live send was authorized here.
- `organvm/social-automation`: default branch `main`; owns social-provider
  adapters. LinkedIn delivery support is present at default-branch commit
  `218f516bdc716975d341f48bfaa3ddb210c946f9`; authenticated browser context
  remains runtime-private and no live provider receipt was available.
- `organvm/browser-state`: default branch `main`; public repository contains only
  a README, so authenticated browser state remains private/provider-owned.
- `organvm/koinonia-db`: default branch `main`; owns a database engine, not the
  Limen correspondence ledger.
- `organvm/daily-engine`: default branch `main`; is the fitness/day-card engine,
  not the professional communications scheduler.

The relevant Limen remote receipts were also inspected:

| Receipt | Final state | Canonical contribution |
| --- | --- | --- |
| PR #1798 | merged as `3487abc5` | daily coordinator, V1 contracts, truthful lifecycle/receipt counting, worker-security pins, and generic heartbeat registration |
| PR #1509 | merged as `06824f44` | incremental iMessage + WhatsApp capture with append-only private tapes, source checkpoints, attachment hashes, and idempotency tests |
| PR #1794 | open, draft | Forrest/WhatsApp disclosure split; public posture only, private raw source |
| PR #1715 | merged as `f7c7461e` | corpus substrate and biography registry with a deterministic union resolver |
| Issue #1734 | closed by #1715 | evidence-union defect is resolved; older `docs/reviews` evidence remains visible and nonexistent `current.md` is explicit unavailable state |
| PR #1797 | closed as superseded | dormant application-funnel path was carried into and superseded by #1798 |

The final remote re-query corrected the owner findings: browser-state still has
only its public README and no public authenticated session; `vox--publica` has no
real Whisper execution receipt available for this run; Universal Mail Automation
already owns the relevant verified mail-send primitive but has no live provider
send receipt in scope; and `social-automation` now has a LinkedIn effector on its
default branch, while authentication and browser context remain private. These
are owner/provider capabilities, not substitutes for a Limen receipt, so the
coordinator preserves unavailable, ambiguous, and blocked outcomes.

## Capability and gap ledger

| Required behavior | Existing owner | Live predicate / receipt | Classification | Integration decision |
| --- | --- | --- | --- | --- |
| Incremental mail ingestion | `scripts/mail-beat.sh` plus Universal Mail Automation | `scripts/tests` mail census and `logs/uma-mail-status.json` | reusable | daily execution invokes the existing beat with explicit send/fire valves |
| Mail obligations | UMA `obligations_build.py`, `scripts/obligations-view.py` | `obligations-ledger.json`, correspondence terminal checks | reusable | consume the ledger; do not add an application database |
| Correspondence reconciliation | `scripts/correspondence-walk.py` | `logs/correspondence-dispositions.json`, drain-trend predicate | reusable | use its `--drain --json` result as the follow-up source of truth |
| Inbound opportunity review | `scripts/opportunity-review-delta.py` | `logs/opportunity-status.json` and its scoped tests | reusable | invoke once per daily run and preserve count-only output |
| ATS sourcing/matching/materials | `organvm/application-pipeline` | pipeline preflight, orchestrator result, PR #111 | reusable but externally owned | invoke through `scripts/application-funnel.py`; never reimplement ATS logic |
| Application submission | application funnel `apply` phase | structured provider result plus canonical `LIMEN_DELIVERY_RECEIPTS` ledger | implemented, provider-gated | attempted is retry-locked; only exact provider/mailbox evidence counts as confirmed |
| LinkedIn follow-up | social-automation effector plus private browser state | default-branch effector receipt and provider session state | implemented, provider-gated | preserve `needs-human`/CAPTCHA/session blockers; no fake template completion |
| WhatsApp/iMessage ingestion | merged PR #1509 plus open PR #1794 | private capture receipts, public posture PR | partial | shared capture is durable; full Forest grounding remains private-owner gated |
| Voice transcription | existing local capture/transcription tools | private source receipts | reusable but private | no public transcript or second transcriber is introduced |
| Public prose voice | `vox--publica` and DECORVM surfaces | voice/decorum predicates | reusable | coordinator stores only safe judgments and receipt references |
| Shared event/obligation/delivery contracts | Limen CLI package | merged `InteractionEventV1`, `ObligationV1`, `DeliveryReceiptV1` tests | implemented | preserve exact provider evidence and lifecycle validation |
| One daily execution front door | Limen CLI/MCP plus generic heartbeat registry | merged `limen daily-execute`, MCP `daily_execution`, and sensor receipt | implemented | reuse one persisted run; keep fire valves stage-scoped and safe-off by default |

## Truthfulness and ownership findings

1. The existing application pipeline may report `submitted`, but that is not a
   provider-confirmed receipt. The coordinator keeps `confirmed` at zero unless a
   receipt includes explicit portal or mailbox evidence; ambiguous ATS attempts
   remain retry-locked.
2. Existing correspondence disposition rows are count-only and already distinguish
   `sent`, `awaiting-them`, `held`, and `needs-human`. A generated LinkedIn/email
   template is therefore never promoted to `delivered` or `confirmed`.
3. Forrest’s public posture and private source are separate owner surfaces. This
   receipt does not publish names, handles, company details, audio, or conversation
   text; the open PR #1794 remains the disclosure owner.
4. The biography registry defect in issue #1734 was resolved by merged PR #1715.
   Any corpus grounding used by future application customization must continue to
   union existing evidence; the resolver marks the nonexistent `current.md`
   source unavailable rather than inventing it.

5. Application-pipeline PR #112 (`43b58a0f`, source commit `b43d200f`) removes the prior mutation that
   logged generated LinkedIn templates as completed outreach and now returns
   structured ATS outcomes. Its readiness gate has no universal outreach
   prerequisite; role-specific referral prerequisites still require a
   provider-observed send state plus receipt/message identifier. The branch is
   merged to `main`.
6. Application-pipeline PR #113 (`13b9931b`) extends that same email checker
   across five configured Mail.app targets and records a redacted, exact-coverage
   reconciliation receipt. It classifies 8 rows as provider-confirmed and 15 as
   deferred/blocked; the named Hamming, Pinecone, and Tapcart rows remain
   duplicate-guarded until exact provider evidence appears.

7. The 23-row reconciliation is complete as a bounded historical accounting:
   `confirmed=8`, `blocked/deferred=15`, `superseded=0`, summing to 23. The daily
   run counts only current-date, current-run `DeliveryReceiptV1` rows; historical
   confirmations never satisfy today’s application count.

8. The daily coordinator’s LinkedIn and mail fire valves remain safe-off in the
   recorded run. A live provider-authenticated send, a Forest private coverage
   receipt, and three current confirmed applications were not available, so no
   outbound action or three-application claim is made.

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

- Limen PR #1798 is merged as `3487abc5`; its exact-head `pr-gate` passed and its
  synthetic `merge_group` run `30868934955` passed before queue merge. Python,
  worker, web, validation, CodeQL, and static-analysis checks are green.
- Application-owner truthfulness is merged as PR #112 at
  `43b58a0fabac21ba8a6da176b92171e9c829685a`, based on merged PR #111; its
  focused suite passed 65 tests and Ruff.
- Historical application reconciliation: application-pipeline PR #113 merged
  at `13b9931b`; its live receipt covers all 23 rows with counts
  `confirmed=8`, `blocked=15`, `superseded=0`, and its focused owner wave passed
  104 tests.
- Limen’s post-merge focused batch passed 78 tests across daily execution, MCP,
  heartbeat sensors, capture, biography resolution, and the owner predicates;
  `npm-audit-autofix`, `pip-audit-autofix`, `check-sensors`, `check-params`, and
  `check-biography` also passed. The worker gate passed `npm ci`,
  `npm audit --audit-level=high`, and all 66 worker tests.
- `scripts/verify-scoped.sh --base origin/main --require-base` passed its cheap
  wave, while local heavy admission was denied by the preserved machine-wide
  `verify-whole` lease (`heavy-lease-held`) rather than stealing that run. The
  remote exact-head `pr-gate` and synthetic `merge_group` receipts are the heavy
  evidence; the new fire lever is explicitly `SAFE-OFF` by default.
- The changed-file resolver escalated to the whole matrix because the existing
  application-funnel driver is deploy-sensitive. Its static, lifecycle,
  contract, and shell predicates passed. The broad `web/api/tests` plus
  `cli/tests` pytest stage emitted failures and later left its xdist workers
  idle without a terminal summary; that stage was stopped at the bounded-wait
  boundary. It is not used as the implementation receipt; the focused
  predicates above are the exact-head evidence for this branch.
- The shared Python audit was red on the first implementation head because
  `cryptography` resolved to `49.0.0`. The merged implementation pins
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
bound. The local pipeline census reported 15 claimed submitted rows and no
current-run provider evidence in the accessible snapshot. Separately, the
independent 23-row reconciliation receipt accounts for 8 provider-confirmed
historical rows and 15 deferred/blocked rows. This is a truthful shortage/
blocker receipt, not proof of the three-application acceptance item.

## Residual owner-gated atoms

These are deliberately preserved as incomplete/blocked owner work, not
represented as solved by this coordinator:

| Atom | Owner receipt | Failed predicate / next command |
| --- | --- | --- |
| Current-day application acceptance | Limen #1798 plus application-pipeline #112/#113 | dry run found a truthful shortage of 3 eligible confirmations and no provider fire receipt; keep fire safe-off until three live, exact provider confirmations exist |
| Historical application claims | application-pipeline PRs #111/#112/#113 plus provider mailbox/portal receipts | all 23 rows are covered by the redacted reconciliation receipt: 8 confirmed, 15 deferred/blocked, 0 superseded. Deferred rows retain duplicate guards and require exact provider evidence before any retry |
| Authenticated LinkedIn action | social-automation/browser-state private provider surface | the effector exists at `218f516`, but no authenticated provider receipt was available; preserve the precise session/CAPTCHA/identity blocker |
| Forest/WhatsApp private coverage | Limen PR #1794 | public posture remains draft-only; do not use full conversation/audio grounding until the private coverage receipt and referral prerequisite are present |
| Biography evidence union | merged Limen PR #1715; issue #1734 closed | resolved with deterministic union and explicit unavailable `current.md`; future customization must continue to consume the unioned registry |
