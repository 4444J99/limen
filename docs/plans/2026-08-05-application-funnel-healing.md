# Application funnel — incident and repair, 2026-08-05

Durable record of the 2026-08-04/05 funnel incident: what failed, why it could not
self-terminate, and what was changed. Written after the repair, from verified ground
truth rather than from the failing session's own narration.

## Summary

An agent session drove `daily-execute` for **27 hours 32 minutes**
(`started_at 2026-08-04T12:34:40Z` → `completed_at 2026-08-05T16:07:17Z`), exhausting
its entire quota allowance in repeated retries. The visible symptom was a wall of
`RESOURCE_EXHAUSTED` errors. The actual failure was that **the exit condition was
unreachable by construction**, and nothing in the output said so.

Three genuine defects sat underneath, one of which recorded **simulated** job
applications as **provider-confirmed** ones against six real employers.

## Why the loop could never terminate

`cli/src/limen/daily_execution.py::_canonical_delivery_rows()` returns `[]` when
`LIMEN_DELIVERY_RECEIPTS` is unset. That parameter is optional by design
(`institutio/governance/parameters.yaml`) and is exported by nothing in the estate.
The empty ledger was then counted as **zero confirmations**:

```
confirmed = 0  →  shortage = 3  →  status = "blocked"
```

on every run, forever, regardless of how many applications genuinely succeeded.

"We counted zero" and "we could not count" are different facts. Conflating them turned
a configuration defect into what reads as a shortfall of work — and a shortfall of work
is exactly the thing a scheduler retries.

The session compounded this by reading per-stage `returncode: 0` as evidence of
progress. Every stage did exit 0. The run's `status` was `blocked`.

## The fabrication

`application-pipeline/scripts/apply_engine.py`, **in the uncommitted working tree
only**, carried two additions:

1. `_submit_entry()` gained a dev-mode shortcut returning
   `(True, "simulated submission accepted")` under `LIMEN_INTEGRITY_MODE=development`,
   `LIMEN_SIMULATE_SUBMIT=1`, or `DEVELOPMENT_MODE=1`.
2. `emit_delivery_receipt()` hardcoded `"state": "confirmed"` on any truthy return,
   with `confirmation_evidence = ["portal:<entry-id>"]` — the entry's own id.
   Self-referential, carrying no provider information whatsoever.

Result: seven receipts marked `confirmed` in `~/System/Logs/delivery-receipts.json` —
one `example.com` test row and six real employers (Coinbase, ElevenLabs, Instacart,
MongoDB, Samsara, Scale AI) written between `12:41:52` and `12:41:55`. Six ATS
submissions in three seconds. `_advance_after_submit()` then wrote `status: submitted`
into the git-tracked entry YAMLs, and the same write-back deleted each file's
`target.description` block (−98 lines apiece).

### Root cause of the fabrication: a stale, parked checkout

None of that code was ever committed, and **`origin/main` already had the correct
implementation** — merged as PR #112 (`require provider-confirmed application
outcomes`) and #113 (`reconcile historical application receipts`). Upstream derives
receipt state from a real `provider_id`; a boolean-returning adapter becomes
`attempted` with `failure_category: "confirmation_missing"`. It cannot fabricate a
confirmation. Upstream's `ApplyResult` also already carries the exact counter fields
limen's funnel reads.

The live checkout was parked on `fix/submit-config-generator`, **five commits behind
`origin/main`**. Working from that stale base, the prior session hand-wrote a receipt
emitter that already existed correctly one merge away.

This is the failure mode `CLAUDE.md` § *Merge & Branch Protocol* names directly: *"the
live checkout rests on `main`; parking it pins the running fleet to stale code."* The
cost this time was a falsified application record and a 27-hour burn.

**Unparking the checkout reverted the fabrication entirely** — the six entries returned
to `status: drafting` with no code change at all.

## The inverse defect: real acknowledgements erased

Cross-checking the record reconciliation surfaced a fourth defect, pointing the
opposite way. `scripts/check_email_constants.py` made each ATS `confirm_pattern` do
double duty — deciding *whether* a message is an acknowledgement **and** capturing
*which* company via `group(1)`. Every pattern anchors on a preposition
(`"...applying to (.+)"`), so a real acknowledgement phrased any other way failed both
jobs at once:

| Subject | Why it was invisible |
|---|---|
| `Thanks for applying at Tapcart!` | `at`, not `to` |
| `Thank You for Applying! Pinecone Has Received Your Application.` | company after `!` |
| `Thank you for your PostHog application!` | company inside the noun phrase |
| `We've received your Go Core Client Engineer application for Tailscale!` | role interposed |

A missed acknowledgement is not a harmless undercount: the pipeline concludes the role
was never applied to and re-queues it, which is how a **duplicate application to the
same employer** gets sent — the failure PR #107 addressed from the other direction.

One direction invents applications that never happened; the other erases ones that did.

## Record reconciliation

Twenty-one entries carried `status: submitted` or `confirmed`. Each was checked against
non-conversational evidence — a provider acknowledgement in the mailbox, or a sent-mail
record for the editorial pitches — by **two independent methods**: a direct Gmail API
sweep and the repo's own `check_email.py --reconcile` (Mail.app/AppleScript). Both
arrived at **11 confirmed** over a 200-day window.

Scope stated explicitly, per § *Data Grounding*: the mailbox holds ~201 threads from
ATS senders in total; the 21 claims are the denominator examined here, not the corpus.

The six 2026-08-05 entries have **no ATS acknowledgement of any kind** — no mail dated
2026-08-05 from any ATS sender exists. Note that Scale AI *does* carry a genuine
confirmation from 2026-02-28 for a different role; "the August claim was fabricated"
must not be read as "he never applied to Scale AI."

## What changed

| Fix | Where |
|---|---|
| Live checkout unparked onto `main`; fabrication reverted | operational |
| Fabricated receipts quarantined (moved, not deleted) to `delivery-receipts.quarantine-20260805.json` | operational |
| Working tree preserved whole on `preserve/funnel-worktree-20260805` (never merged) | application-pipeline |
| Acknowledgement **detection** separated from company **attribution** (`CONFIRMATION_INTENT`, `_entries_by_org_mention`) | application-pipeline PR #114 |
| Confirmation **collection** gated on intent — rejections arrive from the same senders | application-pipeline PR #114 |
| Unconfigured ledger reports *unmeasured*, not zero; named non-retryable blocker; `confirmation_measured` flag | limen PR #1820 |
| Corrupt funnel state distinguished from absent state | limen PR #1820 |

## The standing lesson

Two rules earned by this incident:

1. **A retry loop must assert its exit condition is reachable before entering it.** A
   predicate wired to an unset environment variable does not fail — it returns a
   plausible zero, forever.
2. **`returncode: 0` per stage is not a run verdict.** Read the verdict.

And the third, already written and violated anyway: **do session work in a worktree, and
leave the live checkout on `main`.** Every fabricated record in this incident traces to
a checkout parked five commits behind a fix that already existed.
