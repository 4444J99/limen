# Source-bound Insights and runtime acceptance implementation plan

Issue: #2892
PR: (pending)
Date: 2026-10-16, America/New_York
Status: planned; this document does not certify implementation or deployment

> For agentic workers: use the existing bounded workstream and the subagent-driven-development or executing-plans skill to implement one owned task at a time. Preserve the dependencies and acceptance boundaries below.

**Goal:** Make Insights judgments reproducible from identified, bounded captures, then connect accepted source changes to installation, real consumer use, and scoped completion.

**Architecture:** Extend the current ingest registry, reader, generation binding, native snapshot archive, immutable runtime installer, and closeout receipts. Reporting and runtime adoption are two bounded tracks that converge at consumer acceptance; neither needs a new scheduler, task registry, or verification runner.

**Tech stack:** Python fixture tests and existing JSON contracts; the GATES registry and scoped verifier; chezmoi-owned configuration sources; immutable runtime packages; existing GitHub issue and PR rails.

**Spec:** [Issue #2892](https://github.com/4444J99/limen/issues/2892), the current cross-agent protocol in `AGENTS.md`, and the existing component contracts cited below. Private usage reports remain outside this public plan.

## Evidence boundary and decisions

- **Confirmed source defects:** synthetic fixtures omit a fresh session beneath an old parent directory, produce two index records with one ambiguous native ID, and return 4,184 characters for a 128-character read request. The responsible code paths were also inspected at remote main `8d2a9421bcb9d2a66a9bbbb98e015c1c56c3b974`.
- **Confirmed source limitations:** activity-window membership can use file modification time while displayed counts cover lifetime messages; Antigravity history-only indexing and reading disagree; undecodable content can collapse into not-found or prompt-only output. These are properties of the evidence pipeline, not proof of provider failure.
- **Historical workflow evidence:** repetitive status narration, corrected scope or readiness claims, configuration drift, and incomplete acceptance occur in selected conversation excerpts. A transcript establishes the statements and visible dialogue; it does not independently establish present deployment, time lost, task failure, or productivity.
- **Missing evidence:** missing replies, tool-only records, pruned blobs, unavailable tool results, and no recent indexed record remain explicit unknowns. They must not become silence, inactivity, dissatisfaction, or a failed outcome.
- **Classification:** source defects reproduced with fixtures may drive immediate fixes. Reported operational defects require current reproduction or an independently read receipt. Existing successful corrections are retained; unavailable acceptance remains open under its current owner.

## Global constraints

- Preserve original reports, native conversations, databases, private payloads, dirty checkouts, and concurrent work. Source changes use an isolated branch and checkout or an isolated remote documentation branch.
- Keep all personal usage data, source locators, transcripts, and private acceptance evidence in their existing private owners. Public tests use synthetic data.
- Keep intended capabilities visible. The desired-state manifest determines required services and adapters; low sampled use cannot authorize disabling or uninstalling them.
- Use one writer for each configuration or deployment target. Inspect current broker ownership and fresh admission before mutation; cached status is not fresh admission proof.
- Bound each implementation attempt to 30 minutes, including at most 10 minutes of verification, and 120 cumulative agent-minutes per approved outcome. At most two autonomous implementation tasks and one heavy workload run concurrently. A changed input is required for the single corrective retry.
- The existing verifier derives gates and deadlines from `institutio/governance/gates.yaml`. Preserve exit codes, timeouts, unrun shards, exact heads, and environment fingerprints. Passing publication does not establish installation or runtime acceptance.
- Session release, task completion, artistic/device acceptance, custody, and retirement are distinct. No cleanup is part of this plan's acceptance shortcut.

## Existing owners to reuse

| Work | Reconciled state | How this plan uses it |
|---|---|---|
| [Limen #2868](https://github.com/4444J99/limen/pull/2868), head `3e1d4dbe` | Open | Effective runtime-root discovery and explicit capture source. Reconcile and verify this patch; preserve its owner. |
| [Limen #2888](https://github.com/4444J99/limen/pull/2888), head `cac8b9fd` | Open | Reuse generation binding, stale-artifact rejection, estimate/proposal labels, and identity-checked process observation. Complete missing verification through its owner. |
| [Limen #2891](https://github.com/4444J99/limen/pull/2891), head `217c831` | Draft open | Finish the existing shared-context admission and finite bootstrap path before rollout. |
| [Limen #2848](https://github.com/4444J99/limen/issues/2848) | Open | Retain shared-OS acceptance and watch-coverage disposition; do not restart recovery from retrospective findings. |
| [Limen #2887](https://github.com/4444J99/limen/issues/2887) | Open, vendor-owned | Native generator timezone, denominator, and recommendation defects remain upstream work. Local interpretation does not fix the vendor executable. |
| Domus shared context, skills, and successor rollout owners | Source integration has landed; separate rollout owners remain open | Reuse the existing private context/skills PRs and receipts. A landed source packet does not establish fleet-wide retrieval. |

Before implementation, reconcile current remote heads with the exact installed immutable package and current checkout ownership. An ancestor package does not contain open PRs merely because their sources exist. A lagging or concurrently edited primary checkout is an inspection input, not an implementation checkout.

## Review focus

1. Same-ID files can be copied, truncated, continued, or conflicting: preserve provenance and resolve the exact indexed source (Task 1).
2. Parent timestamps, touched old transcripts, and cross-boundary resumed sessions can distort activity selection and counts (Task 1).
3. Oversized messages, Unicode, prefixes, and expanded reads can exceed bounds or exceed the evidence covered by a digest (Task 2).
4. History-only, unreadable, unsupported, prompt-only, and tool-only captures can be mistaken for absent replies or task failure (Task 3).
5. Concurrent snapshots, same-minute reports, relocated sidecars, and failed pushes can lose archive or delivery identity (Task 4).

## Dependency and execution order

The reporting track is **registered source → record identity and window → bounded read receipt → availability classification → bound facets/narrative → immutable archive and delivery**. The adoption track is **desired-state manifest → verified exact source → immutable installation → effective configuration → native discovery and safe functional use**. Both converge at **consumer acceptance → published scoped receipt → session release**.

Tasks 1–3 share the reader and must be integrated sequentially by one owner, reusing #2868/#2888 rather than competing edits. Task 4 can proceed in a disjoint Domus checkout after its input contract is agreed. Task 5 can progress independently under the existing rollout owner and resource limits. Task 6 consumes both tracks.

## Task 1 — P0: identify the exact source and make window selection truthful

**Canonical files:** Limen `scripts/vendor-insights.py` (`_index_claude`, `_cat_claude`, `cmd_cat`, `cmd_render`); `scripts/insight-cross-vendor-ingest.py` (`claude_estate_roots`, `_ingest_claude`); `cli/tests/test_vendor_insights.py`; existing cross-vendor health tests.

**Consumes:** registered roots and surface identities, candidate files, native session ID, file timestamps, and embedded event timestamps. **Produces:** unique source/capture records with native logical identity retained and explicitly named population/window semantics.

- [ ] Reconcile remote main and the exact #2868/#2888 heads; retain existing accepted changes and assign one owner for overlapping source edits.
- [ ] Add fixture tests for physical aliases; identical, shorter, longer, and conflicting copies sharing a native ID; deterministic lookup; and index→read→facet→render agreement.
- [ ] Remove the parent-directory mtime shortcut in both Claude index and ingest. Test an old parent with a fresh existing child, an old message in a touched file, and a resumed session crossing the boundary.
- [ ] Retain the native `id` for compatibility and add an opaque `record_id` plus a private `source_ref`. Resolve reads from the indexed record. Legacy `--session` lookup must report ambiguity when several distinct records match; it must not silently select the first root.
- [ ] Keep record counts and deduplicated logical counts separate. Consolidate copies only when identity/content or continuation evidence proves equivalence; conflicting captures remain retained.
- [ ] Declare selection basis and count basis separately: “sessions selected by modification/activity time, lifetime messages” versus “messages inside the event window.” Pin start/end inclusivity and out-of-order timestamps with fixtures.
- [ ] Run the implicated fixture gate and one exact-tree scoped verification batch, then publish this independently reviewable correction through the existing PR rail.

**Acceptance:** a fresh child is included regardless of parent mtime; no facet is read from one same-ID source and rendered against another; every displayed denominator names its unit and window basis.

## Task 2 — P0: bound and fingerprint the evidence actually read

**Canonical files:** Limen `scripts/vendor-insights.py` (all `_cat_*` adapters, shared capture utility, index/read/render generation paths); `cli/tests/test_vendor_insights.py`; existing #2888 generation-binding tests.

**Consumes:** Task 1 record identity and the requested excerpt budget. **Produces:** a bounded read receipt for the actual text used by judgment, consumable by the existing generation-binding mechanism.

- [ ] Add failing cases for an oversized first message, large history prefix, Unicode, a budget shorter than headers, exact-boundary text, and a changed tail beyond an unchanged indexed prefix.
- [ ] Route every adapter through one budget writer. Count headers, text, and truncation markers; returned character count must not exceed the advertised budget. Preserve raw source bytes.
- [ ] Add structured read metadata containing record identity, limit, actual returned length, truncation/coverage status, and digest of the actual capture. Human-readable output remains available through the existing CLI.
- [ ] Reuse #2888 fingerprint fields and stale/unindexed/invalid-artifact rejection. An expanded read needs its own capture receipt or a reindex with that budget; the smaller prefix digest proves only its prefix.
- [ ] Require facets and narrative to name their bound capture and excerpt depth. Reader completeness, analyst inspection coverage, model estimates, and externally corroborated outcomes remain different fields or labels.
- [ ] Have ingest health consume the same semantic generation result as rendering. A recently touched narrative alone must not make stale judgment current.
- [ ] Complete the existing #2888 owner's missing implicated verification under the current aggregate deadline, preserving already valid fingerprints and any still-unrun shard; publish the correction once its required predicate passes.

**Acceptance:** the 128-character fixture returns at most 128 characters; changed content inside the judged capture invalidates its binding; stale or wrong-source facets cannot influence aggregates; expanded evidence is explicitly covered.

## Task 3 — P0: expose missing and undecodable evidence honestly

**Canonical files:** Limen `scripts/vendor-insights.py` (`_index_antigravity`, `_cat_antigravity`, `_agy_scrape_blob`, Copilot/Gemini readers, `cmd_cat`, renderer); `scripts/insight-cross-vendor-ingest.py` registry/health; `cli/tests/test_vendor_insights.py`; `cli/tests/test_insight_cross_vendor_health.py`.

**Consumes:** identified records and Task 2 read receipts. **Produces:** explicit source availability and readable-response coverage, independent of outcome judgments.

- [ ] Add history-only Antigravity, pruned blob, unreadable blob, malformed payload, unsupported encoding, metadata-only Copilot, prompt-only Gemini, and tool-label-only fixtures.
- [ ] Read history-only Antigravity records that the index admits. Distinguish missing source, pruned source, read error, unsupported/undecodable content, metadata-only, prompt-only, tool-only, and readable response states. A read error must not collapse into not-found.
- [ ] Report structural assistant-step counts separately from decoded assistant text and available tool-result coverage. Preserve the current prohibition on private summary title/preview extraction.
- [ ] Add coverage denominators for indexed, attempted, retrieved, goal-bearing, response-readable, faceted, and externally corroborated records. “Unfaceted” must use matching identity units.
- [ ] Validate one minimal, non-sensitive exchange through each intended native capture route when the route is available and admitted. Diagnose absent logging, wrong roots, or decoder limitations through its owner; retain “unavailable” where the native product does not expose replies.
- [ ] Defer a full proprietary/protobuf decoder until a supported schema or bounded synthetic specification exists. Keep non-scriptable provider export work with its existing owner rather than scraping unrelated stores.

**Acceptance:** all fixture states remain distinct through rendering; absence of a readable reply never becomes a failed goal, inactivity, silence, or a performance comparison. A controlled exchange establishes only its own tested route.

## Task 4 — P1: make native snapshots immutable and delivery independently retryable

**Canonical files:** Domus `dot_local/bin/executable_insights-snapshot`; `tests/test_insights_snapshot.py`; Limen `scripts/hooks/insights-capture.sh` and its existing #2868 owner. Native generator interpretation remains in #2887 and the existing disposition ledger.

**Consumes:** exact source report, authorized source-relative sidecars, and capture/generation identity. **Produces:** an immutable private archive bundle and separate local-archive, commit, and push receipts.

- [ ] Add tests for two different reports in one minute, identical-content idempotence, relocated sidecars, concurrent capture, failed push, and retry of delivery when the source report has not changed.
- [ ] Replace minute-only snapshot identity with content-bound identity; preserve originals and avoid collisions between distinct reports.
- [ ] Resolve authorized sidecars relative to the selected report source. Remove the assumption that an explicit relocated report must equal the legacy home report path.
- [ ] Persist bounded archive/commit/push results even in quiet mode. Reattempt pending delivery independently of new report creation; an up-to-date source must not hide an earlier failed push.
- [ ] Keep SessionEnd capture nonblocking. Use the existing pending-delivery lineage or on-demand retry, with no new recurring scheduler.
- [ ] Apply the source-owned hook through the actual effective runtime configuration and observe one real SessionEnd capture. Confirm original bytes and sidecar membership before classifying archive and remote delivery separately.

**Acceptance:** distinct same-minute reports remain distinct; unchanged content is idempotent; failed delivery stays visible and can recover without creating a new report; source-relative sidecars and original hashes agree.

## Task 5 — P1: complete immutable adoption and declared capability coverage

**Canonical files:** Limen #2891 `cli/src/limen/shared_context_admission.py` and `cli/tests/test_shared_context_admission.py`; existing `cli/src/limen/host_admission.py`, `scripts/verify.py`, `institutio/governance/gates.yaml`, `scripts/mcp_estate.py`, `scripts/mcp_native_observer.py`. Domus `.chezmoidata/config-ownership.json`, `dot_config/ai-context/agent-instruction-surfaces.json.tmpl`, `dot_local/bin/executable_domus-limen-runtime`, `dot_local/bin/executable_domus-shared-context`, managed runtime modifiers, and the current private skills/capture rollout patch.

**Tests:** existing Limen host-admission/MCP estate tests; Domus `tests/test_domus_limen_runtime.py`, `tests/test_shared_context.py`, `tests/test_config_ownership.py`, `tests/test_capability_runtime.py`; the skills consolidation tests carried by the existing private rollout owner.

**Consumes:** accepted exact source revisions and the canonical desired-state manifest. **Produces:** verified immutable installation, effective managed configuration, and adapter-specific native observations.

- [ ] Recover or replace unavailable source checkouts through their owner with isolated branches. Read current source and remote receipts rather than replaying a stale handoff.
- [ ] Finish #2891's missing verification and governed landing. Use the Domus installer and bounded signed bootstrap; verify source, package, launcher, interpreter, and installed artifact identities.
- [ ] Test exact-manifest refusal, changed destinations, failure rollback, and a no-change second pass. Keep before-images and concurrent target edits protected.
- [ ] Complete the existing skills/capture rollout against effective native roots, preserving personal variants, plugin dependencies, app-owned settings, and changes made during activation.
- [ ] Derive the adapter/capability denominator from the desired-state manifest. For each intended route record effective configuration, native discovery, protocol/auth state, safe functional use, process ownership, and restore/readback. “Installed” or “listed” alone does not prove actual use.
- [ ] Use the current shared-context producer and successor rollout owner to verify root and supported child retrieval of the intended version, authority labels, provenance, and uncertainty boundaries. Keep account memory, project reference files, and local inherited context as separate acceptance claims.
- [ ] Reproduce any still-reported false admission or interpreter failure against current exact source before changing its owning policy. Preserve legitimate host-pressure and writer protections.

**Acceptance:** every intended manifest entry has a current evidence-backed state; missing/disabled/auth-needed/unmeasured entries remain visible and retain owners. Installed changes match accepted exact source; rollback and native consumer use pass independently.

## Task 6 — P1: prove scoped acceptance and close the evidence loop

**Canonical files:** existing `spec/contracts/conduct/run-receipt-v1.schema.json`, `cli/src/limen/session_closeout.py`, process-ownership and workstream/continuation receipts; `cli/tests/test_session_closeout.py` and scoped closeout tests. Domain-specific artistic/device acceptance remains with the consuming project.

**Consumes:** Tasks 1–5 receipts and the original task's requested outcome. **Produces:** one owner-bound status that separates evidence coverage, accepted work, session release, and retained custody.

- [ ] Reuse the existing receipt schema and workstream owner. Bind requested outcome, source revision, installed identity, consumer, predicate command/exit status, observation time, evidence class, and remaining acceptance without adding a parallel registry.
- [ ] Add a regression only where existing contracts fail to distinguish proposed, staged, validated, published, integrated, installed, runtime-observed, and accepted claims. Preserve valid partial states.
- [ ] Regenerate one bounded report per vendor from the corrected capture contract. Retain old snapshots and show changes caused by identity/window/coverage semantics separately from new activity.
- [ ] Check that missing responses remain unknown, duplicate ancestry is not counted as independent work, and every quantitative claim uses the correct read/index/population denominator.
- [ ] Run the session-bound read-only closeout predicate after publication and scoped acceptance. Unknown shared process ownership remains unknown; no process is stopped merely to make release pass.
- [ ] Record checkout retention or independently custody-verified retirement. Session release must not imply task completion, device/artistic acceptance, or deletion eligibility.

**Acceptance:** publication, installation, use, and acceptance each have their own inspectable evidence. A task may be partially achieved with a valid owned handoff; a released session does not silently close unresolved work.

## Verification and final disposition

For reader work, use the existing fixture entry point `bash scripts/run-pytest-hermetic.sh cli/tests/test_vendor_insights.py -q`, then one final `bash scripts/verify-scoped.sh` batch on the owned exact tree. Domus changes run their implicated existing test suites with the repository's declared interpreter and source-owned verification route. Test fixtures do not access live vendor stores or the network.

Use the existing aggregate deadline and gate resource tiers. Complete or explicitly retain unrun shards; do not expand deadlines, repeat unchanged green checks, poll CI, or turn advisory remote checks into an invented local blocker. Each repository-qualified head is submitted through its owning integration rail once.

The plan is complete when it is reviewed and durably published. Implementation is complete only when the owning tasks' source, integration, installation, capture, and scoped acceptance predicates pass. Native vendor-generator defects remain open with their vendor owner until a supported corrected release is independently reproduced.
