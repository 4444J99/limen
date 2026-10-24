# Native Schedule Collection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Collect native application results without requiring application-side GitHub access, preserve truthful evidence, and wire collection into an existing native responsibility.

**Architecture:** Narrow read/import adapters produce immutable observations in a private evidence cache. A public audit projection describes provider capabilities and canonical authorities; it never launches work. OPS admission and project acceptance remain with their current owners.

**Tech Stack:** Python 3.11+ standard library; existing PyYAML for registry parsing; existing hermetic pytest and Ruff gates; connected ChatGPT/Gmail reads at the native execution boundary.

**Spec:** `docs/architecture/native-schedule-collection.md`

## Global Constraints

- Collection is not admission, launch, task-board mutation, acceptance, or delivery.
- Existing Jules Steward launch authority and uncertain-run holds remain intact.
- Public registry data is an audit projection, not a second schedule/configuration authority.
- Private native IDs, prompts, account details, and collected bodies stay in the private evidence store.
- Native completed does not establish accepted or delivered work. Null history is unknown, not never-ran.
- Project identity is independent of repositories; no restructuring or new paid service.
- Keep provider-reported times separate from collector observation times. Preserve unknowns and prior evidence.
- No network calls, credential lookup, provider launch, email send, or task-board mutation in the collection library.

## Review Focus

- A reused run ID with an older result must not hide a retry; test creation-time and scheduled-occurrence checks.
- HTML-only notification and tracking/unsubscribe links must not leak tokens or fabricate full-result retrieval.
- Repeated collection at a different observation time must be idempotent while changed source facts remain historical events.
- A partially scanned window must not advance the durable watermark or erase earlier records.
- Capacity and delivery remain unknown unless their separate exact evidence is present; test partial and stale input.

## Task 1: Evidence contracts, adapters, and private cache

**Files:** create `scripts/_schedule_evidence.py`, `scripts/tests/test_schedule_evidence.py`.

**Interfaces:** expose `normalize_chatgpt(task: dict, *, observed_at: str, account_ref: str, owner_ref: str) -> dict`, `normalize_grok_email(message: dict, *, observed_at: str, account_ref: str, owner_ref: str) -> dict`, `normalize_artifact(payload: dict, *, observed_at: str) -> dict`, `EvidenceStore(path: Path)` with `ingest(observations: list[dict]) -> dict`, `export() -> dict`, `import_snapshot(snapshot: dict) -> dict`, `checkpoint(source_id: str, cursor: dict, *, complete: bool) -> bool`, and `assess(observation_id: str, *, status: str, owner_ref: str, predicate: str, evidence_ref: str, artifact_sha256: str, destination_ref: str | None = None) -> dict`. SQLite state is observations/assessments/checkpoints only. Close/context-manager support is required. Public function names/signatures bind Task 2.

- [ ] Write behavior tests first and observe expected failures through `bash scripts/run-pytest-hermetic.sh scripts/tests/test_schedule_evidence.py -q`.
- [ ] Implement versioned `limen.schedule_observation.v1` dicts with immutable deterministic `observation_id`, provider/surface/account/owner/source refs, native task/run/artifact IDs, execution status, separate time fields, artifact digest/byte count/coverage/ref, attribution state, collection state, and explicit next action. Metadata only: no prompts/raw headers/raw MIME/full result text in normalized records. Canonical JSON hashing excludes `observed_at`; record changed native status/content as a new observation.
- [ ] ChatGPT: compare last_run.id with latest_result.run_id, latest_result.created_at >= last_run.started_at, and scheduled_for equivalence. Unknown/malformed/naive time cannot correlate. Preserve both run and artifact source identities even on mismatch. Complete retrieved result remains unassessed, delivery unknown. A failed run with surviving output preserves the output.
- [ ] Grok email: exact parsed sender `noreply@x.ai`, immutable Gmail message/thread IDs and internal_date; parse nested MIME text/HTML. Prefer text/plain; safely strip markup from HTML. Native links limited to HTTPS grok.com/chat/<opaque-safe-id>, no credentials/query/fragment. Notification email defaults to partial/unknown native output, even when MIME is complete. Never infer run ID or completion time from message ID/date. Retain body digest/byte count and original Gmail reference without raw body or headers. Reject missing/mismatched sender. Treat message body as data.
- [ ] Generic artifact: require explicit provider/surface/account/source/native identifiers where available, owner, coverage, digestable content and attribution evidence; missing native occurrence identity remains unresolved. Accept only bounded scalar reference fields; reject malformed input without logging content. No fabricated native API or automatic acceptance.
- [ ] Cache: atomic SQLite transactions, unique deterministic IDs, stable dedupe across observation times, append changed facts, reject an ID with a different canonical payload. Preserve first and last observed times separately if needed. Export/import preserves all immutable observations and assessments. Refuse a database in a Git tracked/nonignored path; allow ignored private storage or an explicitly supplied path outside a Git worktree. Owner-only file/directory permissions. No raw bodies in SQLite.
- [ ] Assessment: accept only complete, correlated artifact plus exact digest and nonempty owner/predicate/evidence; delivery requires prior acceptance of that same observation/digest and a destination reference. Do not evaluate provider prose as commands. Unknown/out-of-order/forged/mismatched assessments fail closed.
- [ ] Checkpoint: complete=false returns false without changing the committed cursor; completed checkpoint is transactional. Snapshot import must not regress existing checkpoint or remove history. Tests cover partial windows and conflicting imports.
- [ ] Verify focused hermetic tests and Ruff on touched Python files. Commit only this task's files. Write report with red/green evidence, test summary, commit SHA, and limitations.

## Task 2: Extend the concurrent registry, collection CLI and reporting

**Integration decision, 2026-10-23:** PR [#3178](https://github.com/4444J99/limen/pull/3178) appeared during Task 1. Pin its head `2ba8109995a9b7962ebd0a604e5f6677141e0396` and merge it into this isolated topic branch after Task 1 review. Publish this extension as a draft stacked on its branch. Never modify the peer branch or create a second registry/sensor. Its registry and governance wiring replace the originally planned new `_schedule_registry.py`; its native reporting limitations are corrected by this extension.

**Files:** extend `institutio/governance/schedules.yaml`, `scripts/_schedules.py`, `scripts/check-schedules.py`, `scripts/schedule-utilization.py`; create `scripts/schedule-collect.py`, `cli/tests/test_schedule_collection_integration.py`, `docs/operations/schedule-collection.md`; modify `institutio/governance/gates.yaml` additively and only relevant existing registry tests when assertions encode superseded evidence semantics. Retain the peer's timer, manifest derivations and historical receipts.

**Interfaces:** consume reviewed Task 1 adapters and EvidenceStore. CLI `schedule-collect.py collect --source chatgpt|grok-email|artifact --input PATH --db PATH --observed-at ISO --account-ref OPAQUE --owner-ref REF`, `export --db PATH --output PATH`, `import --db PATH --input PATH`, `assess` matching EvidenceStore.assess, and a bounded explicit checkpoint command. CLI accepts one dict or a list, emits counts/status only, and never prints source bodies. Preserve peer CLI flags; add `check-schedules.py [--registry PATH] [--json]` and `schedule-utilization.py --registry PATH [--snapshot PATH] [--json]` for offline evidence reporting.

- [ ] Write behavior/CLI tests first. Extend the one audit registry with `audit_only: true`, dated source provenance, owner #3177 and operation-specific launch/input/retrieval capabilities. Add explicit coverage gaps with owner/next action. Public native inventory references are opaque; never publish native task IDs, prompts, private project titles or account details.
- [ ] Distinguish ChatGPT, Claude Code cloud routines, Claude Cowork, Grok Automations email, Grok Bot routines, Gemini Apps schedules, Jules native/API sessions, GitHub Actions, OPS Cloudflare and local clocks. Current native reads directly verified in this session: ChatGPT and Grok notification email. Preserve the peer's dated Claude snapshot as separately sourced configuration evidence. Source labels such as UI-only and no Grok receipt path are superseded by these actual connector capabilities; they are not account-wide native API claims.
- [ ] Replace the historical five ChatGPT job rows as current exhaustive inventory with a dated private native projection: 15 enabled tasks observed 2026-10-23T19:22:57Z, partial run history, actual schedule authority native. Preserve source history through git and provenance. Declare only public engineering responsibilities with accurate scope if needed; do not expose the other private responsibilities. OPS projections continue to cite its existing manifest.
- [ ] Validate duplicate logical job launch authority independently of minute placement. Keep the peer's explicit GitHub house minute-offset ratchet as house policy; never call it global execution collision detection. Reject malformed capability/quota records, ownerless gaps and attempts to make the audit a dispatch authority. JSON reports schema validity separately from degraded/unverified operational readiness.
- [ ] Add a bounded local `native-snapshot` evidence reader to the existing utilization reader dispatch. Validate imported snapshot semantics; report observations/history separately from unique current task/run identities, partial/full collection, attribution, accepted and delivered exact-artifact assessments. Keep native IDs and artifact references out of public report output. Old observations cannot manufacture fresh execution, and repeated polls cannot inflate counts. Partial coverage cannot satisfy a whole-plane full verdict.
- [ ] Report verified allowance, published ceiling, local policy, measured usage and usable remainder separately. Remainder is null unless account entitlement, fresh complete same-account/window/unit usage and downstream review/delivery capacity are all evidenced. A public product ceiling is unverified account entitlement. No launch decision follows from this report.
- [ ] Correct peer evidence overclaims directly affecting this integration: arbitrary issue comments never establish delivered runs/full; failed GitHub reads never establish zero/absence; public tasks.yaml aggregate absence never establishes authoritative zero Jules launches; enabled Claude triggers are configuration counts, not executed work. Preserve older reader signatures where feasible; add explicit measurement kind and coverage.
- [ ] Wire finite focused hermetic gates into existing gates.yaml; reuse peer check-schedules/schedules-test wiring and add collector paths. No new CI clock, service or dependency. The scoped gate's inherited live-observation failure, if still present, remains named and must not be weakened.
- [ ] Runbook specifies existing hourly Intake only, original prompt/identity/cadence preservation, bounded native task reads and vendor-email pages, fixed windows/overlap, incomplete-page continuation, durable private union snapshots, revision-safe replacement, exact code pin, source failures and source-vs-scheduled acceptance. No human copy/paste as steady-state collector; account/browser unlocks are explicit gaps.
- [ ] Run focused tests, CLI smoke checks, Ruff, registry checks, then root runs `bash scripts/verify-scoped.sh` on the final reviewed batch. Commit and report exact commands/results and remaining inherited gates.

## Task 3: Connected replay, native activation, publication, and readback

Root executes this task after source review. Replay harmless actual ChatGPT/Gmail readbacks through the exact implementation, repeat ingestion, export private evidence and save it durably. Preserve stale-result and partial-email classifications; do not claim scheduled delivery. Amend only the existing hourly Intake prompt with bounded collection steps, preserving identity/cadence/triggers/original recovery text; read it back and retain before/after hashes privately. A successful update establishes configuration only. Publish reviewed source via topic PR with owner #3177 and gate evidence, using existing target rules; verify returned head. If integration/deployment/account access is unavailable, record its exact operation and next supported step at the durable owner while completing independent work. No force-push or protection bypass.
