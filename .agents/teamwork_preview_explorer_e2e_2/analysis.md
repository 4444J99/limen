# Technical Analysis & E2E Test Suite Specification (Features 5–8)

**Agent**: `teamwork_preview_explorer_e2e_2`  
**Working Directory**: `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_e2e_2`  
**Parent Conversation ID**: `1de93b40-afd7-4994-824e-895814f42697`  
**Date**: 2026-08-15  
**Scope**: Features 5, 6, 7, 8 of the PSP Omega Recovery Program E2E Test Suite.

---

## 1. Executive Summary

This document provides the exhaustive technical analysis and test specifications for Features 5 through 8 of the PSP Omega Recovery expert-positioning program:
- **Feature 5**: Proof & Case-Study Architecture (`scripts/positioning-proof-preflight.py`, `psp-c04-proof-contract.json`, `flagship-proof-set.yaml`, `case-study-template.md`, proof runners).
- **Feature 6**: Public Portfolio & Front Door (`_frontdoor.md`, `_capture.md`, `positioning-seeds.json`, `scripts/generate-positioning.py`, 3 visual direction mockups, `organvm-vii-kerygma/portfolio`).
- **Feature 7**: Durable Receipts & Verification Schemas (`limen.positioning_work_receipt.v1`, `limen.positioning_phase_receipt.v1`, `scripts/positioning-program.py --verify-work <ID>`, corruption/tampering guards).
- **Feature 8**: Terminal Two-Pass Omega Proof (`scripts/positioning-program.py --omega --require-two-pass`, `limen.positioning_omega_pass.v1`, convergence validation, phase state progression).

For each feature, this specification defines:
1. **Tier 1 (Feature Coverage / Functional Specification)**: ≥5 test cases with exact inputs, execution flows, and assertions.
2. **Tier 2 (Boundary & Corner Cases / Negative & Security Specification)**: ≥5 test cases covering empty inputs, corrupt data, schema violations, tampering attempts, and edge cases.
3. **Python `unittest` Structure**: Complete mock/sandboxing strategies, directory homing (`tests/e2e_psp_omega/tier1_features/` and `tests/e2e_psp_omega/tier2_boundaries/`), and hermetic invocation patterns.

---

## 2. Codebase Architecture & Invariant Analysis

### 2.1 Feature 5: Proof & Case-Study Architecture
- **Canonical Files**:
  - `docs/positioning/proof/psp-c04-proof-contract.json` (schema `limen.psp_c04_proof_preflight.v3`)
  - `scripts/positioning-proof-preflight.py` (fail-closed validator and resolution harness)
  - `docs/positioning/flagship-proof-set.yaml` (schema `limen.positioning_flagship_proof_set.v1`)
  - `docs/positioning/case-study-template.md` (Level-2 canonical case-study blueprint)
  - `docs/positioning/evidence/` (`flagship-evidence.yaml`, `limen.md`, `public-records.md`, `ai-chat-exporter.md`)
  - `scripts/positioning-flagship-receipt.py` & `scripts/positioning-cost-failure-reproduction.py`
- **Core Invariants**:
  1. **Flagship Triad**: Exactly 3 flagships are selected:
     - `limen` (`organvm/limen` / `C02-PROOF-LIMEN`)
     - `public_records` (`organvm-iii-ergon/public-record-data-scrapper` / `C02-PROOF-PUBLIC-RECORDS`)
     - `ai_chat_exporter` (`organvm-iii-ergon/a-i-chat--exporter` / `C02-PROOF-AI-CHAT-EXPORTER`)
  2. **Preflight Boundary**: Status must remain `PREPARED/PREFLIGHT` and `counts_as_closure: false`. It must never close PSP-P05, P05 leaves, or formal dependencies.
  3. **Exact Upstream Binding**: Contract pins exact git commit heads (`P02_ACCEPTED_HEAD = 8faa5fb9...`, `C03_CURRENT_HEAD = b6af8086...`, `C03_MERGE_COMMIT = 8f89ad16...`) and exact blob SHAs for manifest, evidence, claims ledger, and commercial offers.
  4. **No L1 Commercial Leaks**: Generated offer bindings in `commercial_artifact_set` must expose only `L2`/`L3` levels (never `L1`). `product_operating_partnership_review` must be `L3`-only and off the public front door.
  5. **Denylist / Private Field Guard**: Synthetic fixtures and demo fixtures strictly ban forbidden keys: `credential`, `customer`, `email`, `private_path`, `private_repository`, `secret`, `tasks_yaml_body`, `token`.

### 2.2 Feature 6: Public Portfolio & Front Door
- **Canonical Files**:
  - `scripts/generate-positioning.py` (multi-sink inbound positioning generator)
  - `positioning-seeds.json` & `value-repos.json`
  - `docs/positioning/_frontdoor.md` & `docs/positioning/_capture.md`
  - `docs/positioning/visual-directions/psp-c06/` (`option-1-evidence-ledger.png`, `option-2-systems-field-guide.png`, `option-3-decision-brief.png`)
  - `link-surfaces.json` & `scripts/link-health.py`
  - `docs/positioning/estate-classification.md` & `organvm/.github/profile/README.md`
- **Core Invariants**:
  1. **Price Leak Guard (`_assert_no_prices`)**: Rejects any currency symbol (`$`, `€`, `£`), `<num>k` pricing bands, or `/mo` cadences in public pages (`.md`). Prices exist strictly in `.internal.md` files stamped `NOT FOR PUBLICATION`.
  2. **Awaiting Publish Quarantine**: Repositories marked `awaiting_publish: true` are tested and banked but suppressed from `_frontdoor.md` and public rendering to prevent dead 404 links.
  3. **Two-Door Capture Funnel**: When `frontdoor.contact` is set, CTAs generate pre-tagged `mailto:` URLs (`[<slug> · deploy]` for clients / `[<slug> · hire]` for recruiters). When unset, CTAs render as plain bold text without exposing email addresses.
  4. **Visual Direction Gate**: All 3 mockup directions remain explicitly `UNSELECTED`. No UI implementation or deployment in `organvm-vii-kerygma/portfolio` is authorized without a human selection receipt.
  5. **Discoverability Purity**: Recommends compliant GitHub topics (≤20 topics, alphanumeric+hyphens, ≤35 chars) and SEO descriptions; never mutates remote repos automatically.

### 2.3 Feature 7: Durable Receipts & Verification Schemas
- **Canonical Files**:
  - `scripts/positioning-program.py` (CLI & validation engine)
  - `limen.positioning_work_receipt.v1` (Leaf work receipt schema)
  - `limen.positioning_phase_receipt.v1` (Aggregate phase receipt schema)
  - `docs/receipts/positioning/` (relays, preflights, and durable receipts)
- **Core Invariants**:
  1. **Work Receipt Schema (`limen.positioning_work_receipt.v1`)**:
     - `acceptance_sha256`: Must match `acceptance_digest(packet)` calculated from canonical manifest `program.yaml`.
     - `authority`: `kind: "broker"` requires `run_id`, `lease_id`, `executor`. `kind: "direct_human_session"` requires `session_id`, `executor`, and `human_protected: true`.
     - `observed_heads`: Exact 40-char git commit SHA for the target repository (or all `resolved_repositories` for multi-repo packets).
     - `predicate`: Must have `exit_code: 0`, lowercase 64-char `output_sha256`, RFC3339 timestamp, and **must not call `--verify-work` circularly**.
  2. **Phase Receipt Schema (`limen.positioning_phase_receipt.v1`)**:
     - `exit_gate_sha256`: SHA-256 of the exit gate contract.
     - `child_receipts_sha256`, `remote_state_sha256`, `parity_sha256`: Exact SHA-256 digests over child receipts, remote issue projection states, and issue parity.
     - `predicate.command`: Must exactly match manifest-owned proof predicate `python3 scripts/positioning-program.py --phase-proof <PHASE>`.
  3. **Verification Command**: `python3 scripts/positioning-program.py --verify-work <WORK-ID>` must be bare, non-circular, and read from marked GitHub issue comments `<!-- positioning-receipt:PSP-Pxx-Wyy -->`.

### 2.4 Feature 8: Terminal Two-Pass Omega Proof
- **Canonical Files**:
  - `scripts/positioning-program.py` (`omega`, `validate_omega_pass`, `omega_pass_record`)
  - `limen.positioning_omega_pass.v1` (Omega pass receipt schema)
  - `docs/receipts/positioning/omega-pass-1.json` & `docs/receipts/positioning/omega-pass-2.json`
- **Core Invariants**:
  1. **Two-Pass Convergence**: Pass 1 and Pass 2 must record identical `state_digest` covering remote parity, remote state, all child work receipts, and all phase receipts, while having distinct `observed_at` RFC3339 timestamps.
  2. **Acyclic Topological Progression**: Phase and leaf dependencies are strictly enforced. Dependent work packets (e.g. P12 vs P10) unlock cleanly via topological sorting in `ready_work` without global stalling.
  3. **Closure Integrity**: All non-terminal objects must be closed with valid receipts. Open terminal objects (`PSP-ROOT`, `PSP-P14`, `PSP-P14-W09`) are permitted only during the readiness/two-pass proof window.
  4. **Single-Snapshot Evaluation**: Omega proof executes against a single coherent remote snapshot, preventing race conditions or partial updates during verification.

---

## 3. Test Specification: Feature 5 — Proof & Case-Study Architecture

### 3.1 Tier 1: Feature Coverage Specifications

#### Test 5.1.1: `test_flagship_proof_set_three_candidates_locked`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_5_proof_architecture.py`
- **Method**: `test_flagship_proof_set_three_candidates_locked()`
- **Input**: `docs/positioning/flagship-proof-set.yaml`
- **Execution**: Load YAML manifest using `yaml.safe_load`.
- **Assertions**:
  - `schema_version == "limen.positioning_flagship_proof_set.v1"`
  - Exactly 3 flagships defined: `limen`, `public_records`, `ai_chat_exporter`.
  - Check flagship properties:
    - `limen`: `claim_id == "C02-PROOF-LIMEN"`, target repo `organvm/limen`.
    - `public_records`: `claim_id == "C02-PROOF-PUBLIC-RECORDS"`, target repo `organvm-iii-ergon/public-record-data-scrapper`.
    - `ai_chat_exporter`: `claim_id == "C02-PROOF-AI-CHAT-EXPORTER"`, target repo `organvm-iii-ergon/a-i-chat--exporter`.
  - All flagships specify explicit `limitations` and `max_disclosure`.

#### Test 5.1.2: `test_case_study_level2_template_sections`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_5_proof_architecture.py`
- **Method**: `test_case_study_level2_template_sections()`
- **Input**: `docs/positioning/case-study-template.md`
- **Execution**: Read markdown file content.
- **Assertions**:
  - Contains required 7 structural sections:
    1. `## The expensive problem`
    2. `## What was built`
    3. `## Decisions and tradeoffs`
    4. `## The verification story`
    5. `## What it proves about the method`
    6. `## Current state and honest limits`
    7. `## Doors`
  - Verifies presence of anti-hype disclosure and capture CTA markers.

#### Test 5.1.3: `test_proof_contract_psp_c04_validation`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_5_proof_architecture.py`
- **Method**: `test_proof_contract_psp_c04_validation()`
- **Input**: `docs/positioning/proof/psp-c04-proof-contract.json`
- **Execution**: Run `scripts/positioning-proof-preflight.py` validation function `validate(contract)`.
- **Assertions**:
  - Returned error list is empty (`[]`).
  - `contract["status"] == "PREPARED/PREFLIGHT"`
  - `contract["counts_as_closure"] is False`
  - `contract["program_binding"]["leaf_audit"]` covers all 6 leaves (`PSP-P05-W01` through `PSP-P05-W06`).
  - Commercial artifact set contains all 5 offer bindings (`agentic_delivery_audit`, `governance_install`, `bounded_governance_retainer`, `qualification_and_routing`, `product_operating_partnership_review`).

#### Test 5.1.4: `test_cost_failure_reproduction_synthetic_pass`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_5_proof_architecture.py`
- **Method**: `test_cost_failure_reproduction_synthetic_pass()`
- **Input**: `scripts/tests/fixtures/positioning-proof/synthetic-cost-failure.json`
- **Execution**: Invoke `positioning_cost_failure_reproduction.reproduce(payload)`.
- **Assertions**:
  - `result["status"] == "regenerated"`
  - `result["denominator"] == 3`
  - `result["terminal_states"]["failed"] == 1`
  - `result["terminal_states"]["failed_blocked"] == 1`
  - `len(result["dimensions"]) == 5`
  - `len(result["data_digest"]) == 64` (valid SHA-256 digest).
  - `result["publication_eligible"] is True`

#### Test 5.1.5: `test_exact_head_receipt_runner_execution`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_5_proof_architecture.py`
- **Method**: `test_exact_head_receipt_runner_execution()`
- **Input**: Hermetic temporary git repo with committed test file.
- **Execution**: Create temporary git repo with git commit, construct request dictionary, invoke `positioning_flagship_receipt.run_request(request)`.
- **Assertions**:
  - `result["result"] == "current_pass"`
  - `result["exact_head"] == head_sha`
  - `len(result["artifact_digest"]) == 64`
  - Return code of predicate was 0.

#### Test 5.1.6: `test_claims_resolution_withholds_unformalized_preflights`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_5_proof_architecture.py`
- **Method**: `test_claims_resolution_withholds_unformalized_preflights()`
- **Input**: `psp-c04-proof-contract.json`
- **Execution**: Invoke `positioning_proof_preflight.resolve_claims(contract, as_of=date(2026, 8, 12))`.
- **Assertions**:
  - Returned claims count == 3.
  - All claims have `publishable is False`.
  - All claims contain `"c04_formalization_pending"` in `reason_codes`.
  - Action is `"withhold_until_refresh_and_formalization"`.

---

### 3.2 Tier 2: Boundary & Corner Case Specifications

#### Test 5.2.1: `test_proof_preflight_fails_on_missing_or_stale_source_metadata`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_5_proof_architecture.py`
- **Method**: `test_proof_preflight_fails_on_missing_or_stale_source_metadata()`
- **Input**: Mutated contract dictionary with deleted `observed_at` or `max_age_days` in `sources[0]`.
- **Execution**: Invoke `validate(contract)`.
- **Assertions**:
  - Returns error matching `"has no observation date"` or `"has no freshness budget"`.
  - Process exits non-zero if run via CLI `--json`.

#### Test 5.2.2: `test_proof_preflight_rejects_premature_counts_as_closure`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_5_proof_architecture.py`
- **Method**: `test_proof_preflight_rejects_premature_counts_as_closure()`
- **Input**: Mutated contract with `counts_as_closure: True` and `status: "DONE"`.
- **Execution**: Invoke `validate(contract)`.
- **Assertions**:
  - Errors list contains `"counts_as_closure must remain false"`.
  - Errors list contains `"status must remain PREPARED/PREFLIGHT"`.

#### Test 5.2.3: `test_proof_preflight_rejects_blob_hash_mismatch`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_5_proof_architecture.py`
- **Method**: `test_proof_preflight_rejects_blob_hash_mismatch()`
- **Input**: Mutated contract with `expected_blob = "0"*40` on `p02_live_registry`.
- **Execution**: Invoke `resolve_dependency_sources(contract)`.
- **Assertions**:
  - Row for `p02_live_registry` has `resolved is False`.
  - Reason is `"blob_mismatch"`.

#### Test 5.2.4: `test_demo_fixture_rejects_forbidden_private_keys`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_5_proof_architecture.py`
- **Method**: `test_demo_fixture_rejects_forbidden_private_keys()`
- **Input**: Synthetic demo fixture with injected forbidden keys (`token`, `secret`, `customer`, `credential`).
- **Execution**: Invoke `validate_demo_fixture(contract, fixture)`.
- **Assertions**:
  - `result["status"] == "fail"`
  - `result["errors"]` contains `"contains forbidden keys: credential, customer, secret, token"`.

#### Test 5.2.5: `test_cost_failure_rejects_customer_leak`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_5_proof_architecture.py`
- **Method**: `test_cost_failure_rejects_customer_leak()`
- **Input**: Synthetic cost failure fixture with `rows[0]["customer"] = "private-corp"`.
- **Execution**: Invoke `positioning_cost_failure_reproduction.reproduce(payload)`.
- **Assertions**:
  - `result["status"] == "withheld"`
  - `result["publication_eligible"] is False`
  - `result["errors"]` indicates private/unsupported keys.

#### Test 5.2.6: `test_external_validation_requires_no_outreach_and_public_consent`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_5_proof_architecture.py`
- **Method**: `test_external_validation_requires_no_outreach_and_public_consent()`
- **Input**: Payload with `outreach_performed: True` or objects missing consent status.
- **Execution**: Invoke `validate_external_objects(contract, payload)`.
- **Assertions**:
  - `result["status"] == "fail"`
  - Errors contain `"preflight payload must prove no outreach"`.

---

## 4. Test Specification: Feature 6 — Public Portfolio & Front Door

### 4.1 Tier 1: Feature Coverage Specifications

#### Test 6.1.1: `test_frontdoor_markdown_generation_from_seeds`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_6_portfolio_frontdoor.py`
- **Method**: `test_frontdoor_markdown_generation_from_seeds()`
- **Input**: Hermetic `positioning-seeds.json` and `value-repos.json`.
- **Execution**: Execute `generate-positioning.py --frontdoor --apply` within hermetic temporary environment.
- **Assertions**:
  - Emits `docs/positioning/_frontdoor.md`.
  - Contains system cards for all publishable flagships.
  - Contains two-door CTAs with pre-tagged mailto subjects.
  - Passes claims ledger validation (`assert_public_claims`).

#### Test 6.1.2: `test_inbound_capture_funnel_tagging_and_no_autosend`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_6_portfolio_frontdoor.py`
- **Method**: `test_inbound_capture_funnel_tagging_and_no_autosend()`
- **Input**: Helper function `_mailto(contact="contact@4444j99.dev", slug="public-records", door="deploy")`.
- **Execution**: Render mailto URLs for client door, recruiter door, and aggregate front door.
- **Assertions**:
  - Client door subject is `[public-records · deploy] — inbound`.
  - Recruiter door subject is `[public-records · hire] — inbound`.
  - Aggregate frontdoor subject is `[front door · deploy] — inbound`.
  - Verifies documentation in `_capture.md` confirming zero auto-send / draft-only by design.

#### Test 6.1.3: `test_portfolio_visual_directions_unselected_state`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_6_portfolio_frontdoor.py`
- **Method**: `test_portfolio_visual_directions_unselected_state()`
- **Input**: `docs/receipts/positioning/relays/2026-08-10-psp-c06-public-surfaces-preflight.md`
- **Execution**: Inspect relay text and visual mockup references.
- **Assertions**:
  - References exactly 3 digest-pinned mockup directions:
    - `option-1-evidence-ledger.png`
    - `option-2-systems-field-guide.png`
    - `option-3-decision-brief.png`
  - Documents that all 3 options are strictly `UNSELECTED`.
  - Confirms no UI coding or deployment is authorized without human operator selection receipt.

#### Test 6.1.4: `test_estate_ia_classification_partitioning`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_6_portfolio_frontdoor.py`
- **Method**: `test_estate_ia_classification_partitioning()`
- **Input**: `docs/positioning/estate-classification.md`
- **Execution**: Parse classification categories.
- **Assertions**:
  - Total 235 repositories classified.
  - Clear partition into:
    - Front-door proof candidates (15 repos).
    - Production systems.
    - Utility packages.
    - Private custody / archived repos.
  - Verifies no unclassified repos or orphan public faces.

#### Test 6.1.5: `test_discoverability_buyer_search_topics_and_seo`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_6_portfolio_frontdoor.py`
- **Method**: `test_discoverability_buyer_search_topics_and_seo()`
- **Input**: Hermetic seeds with valid topics (`search_topics: ["data-scraping", "ucc-records"]`).
- **Execution**: Invoke `render_discoverability(repos_seeds, fetch=False)`.
- **Assertions**:
  - Renders markdown with `# Discoverability recommendations`.
  - Generates exact `gh api -X PUT repos/{repo}/topics` copy-paste shell commands.
  - Asserts no automatic mutation of GitHub repositories.

#### Test 6.1.6: `test_census_redacted_metrics_emission`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_6_portfolio_frontdoor.py`
- **Method**: `test_census_redacted_metrics_emission()`
- **Input**: Environment configured with seeds and value-repos.
- **Execution**: Invoke `generate-positioning.py --census` and parse stdout JSON.
- **Assertions**:
  - Returns dictionary with integer counts: `value_repo_count`, `seed_repo_count`, `publishable_seed_count`, `awaiting_publish_count`, `missing_seed_count`.
  - Contains zero repository slugs or private text copy (redacted shape only).

---

### 4.2 Tier 2: Boundary & Corner Case Specifications

#### Test 6.2.1: `test_public_positioning_hard_guard_rejects_price_leak`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_6_portfolio_frontdoor.py`
- **Method**: `test_public_positioning_hard_guard_rejects_price_leak()`
- **Input**: Seed dictionary containing price token `$50k` or `/mo` in `expensive_problem` or `what_it_is`.
- **Execution**: Invoke `render_public(repo, seed)`.
- **Assertions**:
  - `_assert_no_prices` raises `ValueError` with `"refusing to emit PUBLIC positioning: price/currency token(s) leaked"`.
  - No public markdown file is written.

#### Test 6.2.2: `test_awaiting_publish_private_repos_suppressed`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_6_portfolio_frontdoor.py`
- **Method**: `test_awaiting_publish_private_repos_suppressed()`
- **Input**: Seed dictionary with `awaiting_publish: true`.
- **Execution**: Execute `generate-positioning.py --repo <repo> --apply`.
- **Assertions**:
  - Target repo is held in `held` list.
  - Stderr outputs `"AWAITING PUBLISH (private repo -> not rendered until it's public)"`.
  - Neither public `.md` nor `.internal.md` is emitted in output directory.

#### Test 6.2.3: `test_frontdoor_without_contact_omits_mailto_links`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_6_portfolio_frontdoor.py`
- **Method**: `test_frontdoor_without_contact_omits_mailto_links()`
- **Input**: Seeds document where `frontdoor.contact` is `null` or `""`.
- **Execution**: Invoke `render_frontdoor(repos_seeds, frontdoor={})`.
- **Assertions**:
  - Generated markdown contains `**Deploy this for your shop →**` (plain bold text).
  - No `mailto:` link appears in the document.

#### Test 6.2.4: `test_discoverability_topic_validation_filters_invalid_topics`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_6_portfolio_frontdoor.py`
- **Method**: `test_discoverability_topic_validation_filters_invalid_topics()`
- **Input**: List of topics containing invalid formats: `["Valid-Topic-1", "Invalid Topic with Space", "-leading-hyphen", "a"*36, "good-topic"]`.
- **Execution**: Invoke `_validate_topics(topics)`.
- **Assertions**:
  - `good == ["good-topic"]`
  - `bad == ["Valid-Topic-1", "Invalid Topic with Space", "-leading-hyphen", "a"*36]`
  - Surfaces invalid topics in discoverability report warning block.

#### Test 6.2.5: `test_link_health_detects_legacy_dead_links`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_6_portfolio_frontdoor.py`
- **Method**: `test_link_health_detects_legacy_dead_links()`
- **Input**: `link-surfaces.json` containing unmapped legacy URLs (`organvm.github.io/portfolio`).
- **Execution**: Validate link surface mappings.
- **Assertions**:
  - Confirms remapping rules to `https://organvm-vii-kerygma.github.io/portfolio/`.
  - Flags unresolved legacy links as pending remediation.

---

## 5. Test Specification: Feature 7 — Durable Receipts & Verification Schemas

### 5.1 Tier 1: Feature Coverage Specifications

#### Test 7.1.1: `test_work_receipt_schema_v1_validation`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_7_receipt_schemas.py`
- **Method**: `test_work_receipt_schema_v1_validation()`
- **Input**: Valid `limen.positioning_work_receipt.v1` dictionary for `PSP-P02-W08`.
- **Execution**: Invoke `positioning_program.validate_work_receipt(receipt, "PSP-P02-W08", graph)`.
- **Assertions**:
  - Returns identical receipt dictionary without error.
  - Matches `acceptance_sha256` computed from `graph["work_by_id"]["PSP-P02-W08"]`.
  - Validates broker authority (`run_id`, `lease_id`, `executor`).
  - Validates exact 40-char commit SHA in `observed_heads["organvm/limen"]`.

#### Test 7.1.2: `test_phase_receipt_schema_v1_validation`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_7_receipt_schemas.py`
- **Method**: `test_phase_receipt_schema_v1_validation()`
- **Input**: Valid `limen.positioning_phase_receipt.v1` dictionary for `PSP-P00`.
- **Execution**: Invoke `positioning_program.validate_phase_receipt(receipt, "PSP-P00", graph, ...)`.
- **Assertions**:
  - Returns identical receipt dictionary.
  - Verifies `predicate.command == "python3 scripts/positioning-program.py --phase-proof PSP-P00"`.
  - Verifies matching `exit_gate_sha256`, `child_receipts_sha256`, `remote_state_sha256`, `parity_sha256`.

#### Test 7.1.3: `test_verify_work_cli_bare_execution`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_7_receipt_schemas.py`
- **Method**: `test_verify_work_cli_bare_execution()`
- **Input**: Monkeypatched issue comments containing marked receipt block `<!-- positioning-receipt:PSP-P01-W01 --> ```json {...} ``` `.
- **Execution**: Invoke `positioning_program.main(["--verify-work", "PSP-P01-W01"])`.
- **Assertions**:
  - Exits with returncode `0`.
  - Stdout JSON contains `"status": "pass"`, `"work_id": "PSP-P01-W01"`, `"receipt_url"`, and `"receipt_sha256"`.

#### Test 7.1.4: `test_direct_human_session_authority_protection`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_7_receipt_schemas.py`
- **Method**: `test_direct_human_session_authority_protection()`
- **Input**: Work receipt with `authority: {"kind": "direct_human_session", "session_id": "sess-1", "executor": "human", "human_protected": True}`.
- **Execution**: Invoke `validate_work_receipt(receipt, work_id, graph)`.
- **Assertions**:
  - Validates successfully.
  - If `human_protected` is omitted or False, validation raises `ProgramError` with `"direct authority must record human_protected=true"`.

#### Test 7.1.5: `test_multi_repository_receipt_resolution`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_7_receipt_schemas.py`
- **Method**: `test_multi_repository_receipt_resolution()`
- **Input**: Work packet with `target_repo: "multi-repository:..."` (e.g. `PSP-P07-W05`), receipt with `resolved_repositories: ["organvm/alpha", "organvm/beta"]` and `observed_heads: {"organvm/alpha": "a"*40, "organvm/beta": "b"*40}`.
- **Execution**: Invoke `validate_work_receipt(receipt, "PSP-P07-W05", graph)`.
- **Assertions**:
  - Validation passes.
  - Fails if `resolved_repositories` is missing or does not match `observed_heads` keys.

#### Test 7.1.6: `test_receipt_template_generation_purity`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_7_receipt_schemas.py`
- **Method**: `test_receipt_template_generation_purity()`
- **Input**: Work ID `PSP-P01-W01`.
- **Execution**: Invoke `receipt_template("PSP-P01-W01", graph, mapping)`.
- **Assertions**:
  - Returns template with schema `limen.positioning_work_receipt.v1`.
  - `acceptance_sha256` prefilled with canonical digest.
  - `predicate.command` is placeholder `"REPLACE_WITH_NON_CIRCULAR_EXECUTABLE_PREDICATE"`.

---

### 5.2 Tier 2: Boundary & Corner Case Specifications

#### Test 7.2.1: `test_work_receipt_detects_acceptance_hash_tampering`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_7_receipt_schemas.py`
- **Method**: `test_work_receipt_detects_acceptance_hash_tampering()`
- **Input**: Valid work receipt with `acceptance_sha256` altered to `"0"*64`.
- **Execution**: Invoke `validate_work_receipt(receipt, work_id, graph)`.
- **Assertions**:
  - Raises `ProgramError` matching `"acceptance_sha256 is stale or incorrect"`.

#### Test 7.2.2: `test_work_receipt_rejects_circular_predicate`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_7_receipt_schemas.py`
- **Method**: `test_work_receipt_rejects_circular_predicate()`
- **Input**: Work receipt with `predicate.command = "python3 scripts/positioning-program.py --verify-work PSP-P01-W01"`.
- **Execution**: Invoke `validate_work_receipt(receipt, work_id, graph)`.
- **Assertions**:
  - Raises `ProgramError` matching `"predicate.command cannot call the receipt verifier itself"`.

#### Test 7.2.3: `test_work_receipt_rejects_invalid_or_extra_observed_heads`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_7_receipt_schemas.py`
- **Method**: `test_work_receipt_rejects_invalid_or_extra_observed_heads()`
- **Input**: Work receipt with 39-character head or unmapped extra repository in `observed_heads`.
- **Execution**: Invoke `validate_work_receipt(receipt, work_id, graph)`.
- **Assertions**:
  - Raises `ProgramError` matching `"observed_heads must contain exactly the packet target repository"` or `"has invalid exact head"`.

#### Test 7.2.4: `test_phase_receipt_detects_digest_tampering`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_7_receipt_schemas.py`
- **Method**: `test_phase_receipt_detects_digest_tampering()`
- **Input**: Phase receipt with tampered `child_receipts_sha256`, `remote_state_sha256`, or `parity_sha256`.
- **Execution**: Invoke `validate_phase_receipt(receipt, phase_id, graph, ...)`.
- **Assertions**:
  - Raises `ProgramError` matching `"child receipt digest is stale or incorrect"`, `"remote state digest is stale or incorrect"`, or `"parity digest is stale or incorrect"`.

#### Test 7.2.5: `test_receipt_parser_rejects_duplicate_or_corrupt_blocks`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_7_receipt_schemas.py`
- **Method**: `test_receipt_parser_rejects_duplicate_or_corrupt_blocks()`
- **Input**: Comment text containing two `<!-- positioning-receipt:PSP-P01-W01 -->` JSON blocks or invalid JSON.
- **Execution**: Invoke `fetch_work_receipt("PSP-P01-W01", graph, mapping)`.
- **Assertions**:
  - Raises `ProgramError` matching `"must contain exactly one JSON receipt block"` or `"is invalid JSON"`.

#### Test 7.2.6: `test_closure_integrity_rejects_premature_closures`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_7_receipt_schemas.py`
- **Method**: `test_closure_integrity_rejects_premature_closures()`
- **Input**: Remote snapshot with `PSP-P01` marked closed while `PSP-P00` is open, or `PSP-P00-W02` closed while `PSP-P00-W01` is open.
- **Execution**: Invoke `closure_integrity(graph, mapping, remote)`.
- **Assertions**:
  - Raises `ProgramError` matching `"is closed before dependency issues"` or `"is closed before upstream phase issues"`.

---

## 6. Test Specification: Feature 8 — Terminal Two-Pass Omega Proof

### 6.1 Tier 1: Feature Coverage Specifications

#### Test 8.1.1: `test_omega_pass_schema_validation`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_8_omega_proof.py`
- **Method**: `test_omega_pass_schema_validation()`
- **Input**: Valid `limen.positioning_omega_pass.v1` record for pass 1 and pass 2 with matching 64-char `state_digest`.
- **Execution**: Invoke `validate_omega_pass(record, pass_number, digest)`.
- **Assertions**:
  - Returns validated record dictionary.
  - Enforces `schema_version == "limen.positioning_omega_pass.v1"`, `status == "pass"`, `pass == pass_number`.

#### Test 8.1.2: `test_two_pass_omega_convergence_validation`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_8_omega_proof.py`
- **Method**: `test_two_pass_omega_convergence_validation()`
- **Input**: Fully closed program remote snapshot + two valid pass files `omega-pass-1.json` and `omega-pass-2.json` in `docs/receipts/positioning/`.
- **Execution**: Invoke `positioning_program.omega(graph, mapping, require_two_pass=True)`.
- **Assertions**:
  - `result["status"] == "pass"`
  - `result["ok"] is True`
  - `result["state_digest"] == pass1["state_digest"] == pass2["state_digest"]`
  - `result["open"] == []`

#### Test 8.1.3: `test_omega_pass_record_cli_generation`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_8_omega_proof.py`
- **Method**: `test_omega_pass_record_cli_generation()`
- **Input**: Closed remote snapshot allowing open terminal objects.
- **Execution**: Invoke `positioning_program.main(["--omega", "--omega-pass", "1"])`.
- **Assertions**:
  - Exits with returncode `0`.
  - Stdout JSON contains `pass: 1`, `schema_version: "limen.positioning_omega_pass.v1"`, and valid RFC3339 `observed_at`.

#### Test 8.1.4: `test_phase_state_progression_acyclic_readiness`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_8_omega_proof.py`
- **Method**: `test_phase_state_progression_acyclic_readiness()`
- **Input**: Remote snapshot progressing phase-by-phase from `PSP-P00` to `PSP-P14`.
- **Execution**: Invoke `ready_work(graph, mapping)` at each state transition.
- **Assertions**:
  - Initial state: only `PSP-P00-W01` ready.
  - Closing `PSP-P00-W01` unlocks `PSP-P00-W02` and `PSP-P00-W04`.
  - P12 work (`PSP-P12-W01`) unlocks when its specific predecessor work is closed, without waiting for entire P10 closure (avoids phase-gating deadlocks).

#### Test 8.1.5: `test_phase_proof_transitive_dependency_enforcement`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_8_omega_proof.py`
- **Method**: `test_phase_proof_transitive_dependency_enforcement()`
- **Input**: Phase `PSP-P02` tested with `PSP-P00` open and `PSP-P01` closed.
- **Execution**: Invoke `phase_proof("PSP-P02", graph, mapping)`.
- **Assertions**:
  - Raises `ProgramError` matching `"PSP-P02 upstream phase PSP-P00 is not closed"`.
  - Setting `PSP-P00` closed allows `phase_proof("PSP-P02", ...)` to pass.

#### Test 8.1.6: `test_omega_single_remote_snapshot_reuse`
- **Test File**: `tests/e2e_psp_omega/tier1_features/test_feature_8_omega_proof.py`
- **Method**: `test_omega_single_remote_snapshot_reuse()`
- **Input**: Monkeypatched remote fetch tracking object identity.
- **Execution**: Invoke `omega(graph, mapping, require_two_pass=False)`.
- **Assertions**:
  - Asserts `fetch_program_issues` was called exactly once.
  - All downstream verifiers (`remote_parity`, `_remote_state_digest`, `_phase_binding_values`, `closure_integrity`, `fetch_phase_receipt`) operate on the exact identical snapshot object.

---

### 6.2 Tier 2: Boundary & Corner Case Specifications

#### Test 8.2.1: `test_omega_two_pass_rejects_divergent_state_digests`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_8_omega_proof.py`
- **Method**: `test_omega_two_pass_rejects_divergent_state_digests()`
- **Input**: Pass 1 with digest `"a"*64` and Pass 2 with digest `"b"*64`.
- **Execution**: Invoke `omega(graph, mapping, require_two_pass=True)`.
- **Assertions**:
  - Raises `ProgramError` matching `"Omega pass digests differ"`.

#### Test 8.2.2: `test_omega_two_pass_rejects_identical_timestamps`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_8_omega_proof.py`
- **Method**: `test_omega_two_pass_rejects_identical_timestamps()`
- **Input**: Pass 1 and Pass 2 with identical `observed_at: "2026-08-15T12:00:00Z"`.
- **Execution**: Invoke `omega(graph, mapping, require_two_pass=True)`.
- **Assertions**:
  - Raises `ProgramError` matching `"Omega passes must record distinct observations"`.

#### Test 8.2.3: `test_omega_rejects_open_non_terminal_objects`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_8_omega_proof.py`
- **Method**: `test_omega_rejects_open_non_terminal_objects()`
- **Input**: Remote snapshot with `PSP-P05-W02` in `state: "open"`.
- **Execution**: Invoke `omega(graph, mapping, require_two_pass=True)`.
- **Assertions**:
  - Raises `ProgramError` matching `"open program objects: ['PSP-P05-W02']"`.

#### Test 8.2.4: `test_omega_incompatible_cli_flags_fail_closed`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_8_omega_proof.py`
- **Method**: `test_omega_incompatible_cli_flags_fail_closed()`
- **Input**: CLI arguments `["--check", "--omega-pass", "1"]` or `["--omega", "--omega-pass", "1", "--require-two-pass"]`.
- **Execution**: Invoke `main(argv)`.
- **Assertions**:
  - Returns exit code `2`.
  - Stderr contains `"valid only with --omega"` or `"incompatible with --require-two-pass"`.

#### Test 8.2.5: `test_omega_detects_corrupt_or_missing_pass_files`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_8_omega_proof.py`
- **Method**: `test_omega_detects_corrupt_or_missing_pass_files()`
- **Input**: Non-existent or malformed JSON in `docs/receipts/positioning/omega-pass-1.json`.
- **Execution**: Invoke `omega(graph, mapping, require_two_pass=True)`.
- **Assertions**:
  - Raises `ProgramError` matching `"missing or invalid.*omega-pass-1.json"`.

#### Test 8.2.6: `test_phase_proof_rejects_orphan_or_duplicate_markers`
- **Test File**: `tests/e2e_psp_omega/tier2_boundaries/test_boundary_8_omega_proof.py`
- **Method**: `test_phase_proof_rejects_orphan_or_duplicate_markers()`
- **Input**: Remote snapshot containing duplicate issue marker `PSP-P00-W01` on two different issue numbers, or orphan marker `PSP-P00-W99`.
- **Execution**: Invoke `phase_proof("PSP-P00", graph, mapping)`.
- **Assertions**:
  - Raises `ProgramError` matching `"duplicate program issue markers"` or `"orphan phase-local markers"`.

---

## 7. Python `unittest` Suite Architecture & Sandboxing Strategy

### 7.1 Test Hierarchy & Directory Structure
The test suite is placed under `tests/e2e_psp_omega/` using standard Python `unittest`:
```
tests/e2e_psp_omega/
├── __init__.py
├── conftest.py / fixtures.py      # Common mock generators, hermetic repo builders
├── runner.py                      # Master suite runner (Tiers 1–4)
├── tier1_features/
│   ├── __init__.py
│   ├── test_feature_5_proof_architecture.py
│   ├── test_feature_6_portfolio_frontdoor.py
│   ├── test_feature_7_receipt_schemas.py
│   └── test_feature_8_omega_proof.py
└── tier2_boundaries/
    ├── __init__.py
    ├── test_boundary_5_proof_architecture.py
    ├── test_boundary_6_portfolio_frontdoor.py
    ├── test_boundary_7_receipt_schemas.py
    └── test_boundary_8_omega_proof.py
```

### 7.2 Hermetic Mocking & Sandboxing Principles
1. **Zero Live Network / Zero GitHub Mutation**: All GitHub API calls (`_pages`, `_api`, `_gh`, `gh`) are monkeypatched using test doubles (`unittest.mock.patch` or fixture dictionaries).
2. **Dynamic Module Loading**: Scripts (`positioning-program.py`, `positioning-proof-preflight.py`, `generate-positioning.py`) are loaded dynamically using `importlib.util.spec_from_file_location`, ensuring test independence from installation state.
3. **Isolated File Sandboxes**: File modifications (`--apply`, `--frontdoor`, `--census`, git repositories) execute inside `tempfile.TemporaryDirectory()`, parameterized via `LIMEN_ROOT`, `LIMEN_POSITIONING_DIR`, etc.
4. **Deterministic Time Control**: Date/time evaluations use fixed timestamps (e.g., `date(2026, 8, 12)` or `2026-08-09T12:00:00Z`), ensuring deterministic test outcomes.

---

## 8. Verification Matrix & Coverage Assessment

| Feature | # | Tier 1 Tests | Tier 2 Tests | Total Tests | Target Met |
|---|---|---|---|---|:---:|
| **Feature 5: Proof & Case-Study Architecture** | 5 | 6 | 6 | 12 | **>=5 (YES)** |
| **Feature 6: Public Portfolio & Front Door** | 6 | 6 | 5 | 11 | **>=5 (YES)** |
| **Feature 7: Durable Receipts & Verification** | 7 | 6 | 6 | 12 | **>=5 (YES)** |
| **Feature 8: Terminal Two-Pass Omega Proof** | 8 | 6 | 6 | 12 | **>=5 (YES)** |
| **Total Features 5–8** | — | **24** | **23** | **47** | **>=40 (YES)** |

All requirements from `ORIGINAL_REQUEST.md`, `PROJECT.md`, `TEST_INFRA.md`, and `AGENTS.md` are rigorously satisfied.
