# Native schedule collection

Status: implementation authorized on 2026-10-23; activation and delivery require separate observed evidence. Owner: [schedule estate, #3177](https://github.com/4444J99/limen/issues/3177).

## Purpose and ownership

Make applications useful participants even when their native features cannot contact GitHub. Existing native schedules keep their launch authority. A read-only collector retrieves outputs, preserves their attribution, and exposes missing handoffs. OPS retains shared schedule/admission and budget policy; Limen aggregates engineering evidence; each project retains its work, private data, acceptance, and delivery. Existing ops-witness remains an independent observer. A project may have several repositories or none.

Collection is not admission, launch, task-board mutation, acceptance, or delivery. This implementation introduces no scheduler service, public ingress endpoint, new credentials, provider spending, or model-API substitute for included native features. Existing Jules Steward launch authority and uncertain-run holds remain intact.

## Required behavior

1. Inventory exact provider surfaces separately: ChatGPT tasks, Claude Code cloud routines, Claude Cowork, Grok Automations email, Grok Bot routines, Gemini Apps schedules, Jules sessions/native schedules, and existing infrastructure clocks. Product/API naming similarity does not establish shared access.
2. Record launch, context-input, and result-retrieval capabilities independently, with source and observation date. Public registry data is an audit projection, not a second schedule/configuration authority. Private native IDs, prompts, account details, and collected bodies stay in the private evidence store.
3. Normalize source observations through narrow adapters. ChatGPT result attribution requires matching run IDs AND result creation at or after the current attempt start AND matching scheduled occurrence. Preserve an older or earlier-attempt result under its actual identities. Native completed does not establish accepted or delivered work. Null history is unknown, not never-ran.
4. For Grok notification email, accept the verified exact vendor sender, parse text or HTML MIME safely, retain immutable message/thread identity and a safe native conversation link. Email arrival/header dates are not provider start/completion times. Notifications or Continue-reading excerpts cannot establish full result retrieval. Strip tracking/unsubscribe links and query credentials; never persist raw MIME/headers in derived records or log them.
5. A generic import supports an externally collected artifact with explicit provenance and complete/partial/unknown coverage. It does not invent a provider API, authenticate a browser, or execute provider-returned instructions. No imported text executes shell commands or creates work automatically.
6. Keep normalized observations in a private append-only SQLite evidence cache, with transactional deduplication and conflicting-identity rejection. It is not an execution queue or lease authority. Stable observation identity excludes collector wall-clock time, so repeated polling does not duplicate an unchanged observation; changed source facts append another event. Default storage is ignored private state; refuse writes to tracked/public paths.
7. Acceptance and delivery are separate explicit evidence records bound to the exact artifact digest and original work/occurrence identity. An acceptance requires an owner, a predicate, and an evidence reference; delivery additionally requires a prior accepted artifact and destination evidence. A partial, uncorrelated, or unknown artifact cannot be marked accepted/delivered through the collector. These attestations record evidence supplied by an authorized owner; they do not execute the predicate or grant authority.
8. Collection checkpoints advance only after durable ingestion of the entire requested page/window. Partial pagination, unavailable source, duplicate polling, or malformed input must not discard unseen results. Private import/export snapshots preserve the union of observations and assessment history.
9. Report inventory validity, observation coverage, execution, collection, acceptance, delivery, and capacity independently. Unknown quota is unmeasured. Remaining capacity requires verified account entitlement, fresh complete usage coverage for the same unit/window, and known downstream capacity; a published provider ceiling is insufficient. Missing expected occurrences retain owner and next action; overlap alone is not a conflict when logical jobs/resources differ.

## Available initial collection routes

- ChatGPT: per-task native read returns current run and independently attributable latest result. Collect existing tasks through the connected automation surface.
- Grok Automations: connected Gmail contains provider email excerpts. An excerpt is collectible partial evidence; complete native result access remains unverified. This route says nothing about Grok Bot account access.
- Claude Code/Cowork, Grok Bot, Gemini Apps, Jules: record documented routes and current access unknown. Use the generic artifact adapter only after an actual supported collector retrieves an artifact. Never call launch endpoints to test observation.

The production entry point is an additive collection responsibility on the existing hourly ChatGPT Intake task, preserving its ID, cadence, original recovery contract and sole-Steward launch boundary. The collector handles bounded native lookups and vendor-email reads, writes private receipts, and routes material findings to existing owners. Its scheduled execution capability and delivery are unverified until a natural occurrence produces linked evidence. The implementation session may replay real connector readbacks locally; that is an interactive collection proof, not a scheduled delivery.

## Acceptance

Offline tests must prove stale/earlier-attempt joins, partial email handling, sender/link validation, private persistence, deduplication, history union, cursor safety, explicit acceptance/delivery binding, unknown-capacity handling, and no second launch authority. A real connector replay must ingest current ChatGPT readback and Grok email, repeat safely, and preserve a detected attribution gap. Source verification, PR publication, native prompt update, actual scheduled execution, accepted project output and external delivery remain separate recorded gates.

## Context and boundaries

This follows packet 2026-10-16-v1.1 and sanitized projection 2026-10-16-v1.1-r2: CF02 project identity is independent of repositories; CF29 allows flat catalogs and manifest-owned nesting without authorizing restructuring. Historical approvals remain evidence, not new grants. Original snapshots and source IDs must not be rewritten to improve counts. No direct access to the private memory project or other-provider account persistence is implied.
