# Handoff Report: E2E Test Suite Specification for Features 5–8

**Agent**: `teamwork_preview_explorer_e2e_2`  
**Working Directory**: `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_e2e_2`  
**Parent Conversation ID**: `1de93b40-afd7-4994-824e-895814f42697`  
**Date**: 2026-08-15  
**Deliverable**: Comprehensive Tier 1 (Feature Coverage) and Tier 2 (Boundary & Corner Cases) E2E test suite specifications for Features 5, 6, 7, and 8.

---

## 1. Observation

### A. Feature 5: Proof & Case-Study Architecture
1. **Proof Preflight Harness**: `scripts/positioning-proof-preflight.py` (897 lines) enforces `validate(contract)`, `resolve_dependency_sources`, `verify_upstream_bindings`, `resolve_claims`, and `audit_surface_manifest`.
   - Lines 19–23 pin exact upstream heads: `P02_ACCEPTED_HEAD = "8faa5fb9899231ebf5f87e78bb171544c11b79d7"`, `C03_CURRENT_HEAD = "b6af8086c9050634313f519c29a6dfcb922c3721"`, `C03_MERGE_COMMIT = "8f89ad16ca1df84b00cb8227c88f368d0d64631a"`.
   - Lines 24–43 define the 3 flagships: `limen` (`C02-PROOF-LIMEN`), `public_records` (`C02-PROOF-PUBLIC-RECORDS`), `ai_chat_exporter` (`C02-PROOF-AI-CHAT-EXPORTER`).
   - Lines 103–112 forbid demo fixture keys: `"credential"`, `"customer"`, `"email"`, `"private_path"`, `"private_repository"`, `"secret"`, `"tasks_yaml_body"`, `"token"`.
2. **Contract & Template**: `docs/positioning/proof/psp-c04-proof-contract.json` (schema `limen.psp_c04_proof_preflight.v3`) binds 6 proof classes; `docs/positioning/case-study-template.md` formalizes Level-2 sections: *The expensive problem, What was built, Decisions and tradeoffs, The verification story, What it proves about the method, Current state and honest limits, Doors*.
3. **Proof Runners**: `scripts/positioning-flagship-receipt.py` runs exact-head tests; `scripts/positioning-cost-failure-reproduction.py` reproduces failure dimensions from synthetic fixtures (`synthetic-cost-failure.json`).

### B. Feature 6: Public Portfolio & Front Door
1. **Inbound Positioning Generator**: `scripts/generate-positioning.py` (775 lines) renders public `.md` and `.internal.md` sinks.
   - Lines 178–188 enforce `_assert_no_prices` (`[$€£]|\b\d[\d,]*\s*k\b|/\s*mo\b`), throwing `ValueError` if prices leak onto public pages.
   - Lines 98–100 enforce `_awaiting_publish` filtering, suppressing unreleased private repos to prevent 404 links.
   - Lines 163–174 construct capture funnels via pre-tagged mailto links (`[<slug> · deploy]` / `[<slug> · hire]`).
2. **Capture Funnel & Visual Directions**: `docs/positioning/_capture.md` specifies zero auto-send lead routing to `obligations-ledger.json`. Relay `docs/receipts/positioning/relays/2026-08-10-psp-c06-public-surfaces-preflight.md` freezes 3 visual mockup options (`option-1-evidence-ledger.png`, `option-2-systems-field-guide.png`, `option-3-decision-brief.png`) as strictly `UNSELECTED`.

### C. Feature 7: Durable Receipts & Verification Schemas
1. **Schema & Verifier Implementations**: `scripts/positioning-program.py` (2654 lines) implements:
   - Leaf receipt `limen.positioning_work_receipt.v1` (lines 1322–1416): validates `acceptance_sha256`, broker authority (`run_id`, `lease_id`, `executor`) or direct authority (`session_id`, `human_protected: true`), exact 40-char `observed_heads`, non-zero `exit_code: 0`, and bans circular `--verify-work` predicate calls (line 1387).
   - Phase receipt `limen.positioning_phase_receipt.v1` (lines 1518–1581): validates `exit_gate_sha256`, `child_receipts_sha256`, `remote_state_sha256`, `parity_sha256`, and predicate `python3 scripts/positioning-program.py --phase-proof <PHASE>`.
2. **Verification CLI**: Lines 1866–1875 define `verify_work(work_id, graph, mapping)` reading marked comments `<!-- positioning-receipt:PSP-Pxx-Wyy -->`.

### D. Feature 8: Terminal Two-Pass Omega Proof
1. **Two-Pass Convergence Engine**: `scripts/positioning-program.py`:
   - Lines 2407–2425 define `validate_omega_pass(value, number, digest)` for schema `limen.positioning_omega_pass.v1`.
   - Lines 2445–2545 define `omega(graph, mapping, require_two_pass, allow_open_terminal)` verifying identical state digests across pass 1 and pass 2 (`omega-pass-1.json` and `omega-pass-2.json`) with distinct timestamps, zero open non-terminal objects, and complete phase receipt bindings.
   - Lines 1061–1104 in `cli/tests/test_positioning_program.py` prove acyclic topological progression in `ready_work` without global stalls.

---

## 2. Logic Chain

1. **Premise**: `TEST_INFRA.md` requires ≥5 Tier 1 (Feature Coverage) and ≥5 Tier 2 (Boundary & Corner Cases) tests per feature across all 8 features.
2. **Observation → Test Design**:
   - For **Feature 5**, the preflight contract (`validate`), source resolver (`resolve_dependency_sources`), demo fixture validator (`validate_demo_fixture`), and cost/failure runner (`reproduce`) exhibit deterministic pass/fail rules. We designed 6 Tier 1 tests (flagship selection, Level-2 template, contract validation, cost/failure reproduction, exact-head runner, claims resolution) and 6 Tier 2 tests (missing source date, premature closure flag, blob mismatch, forbidden keys, customer leak, outreach violation).
   - For **Feature 6**, the generator (`generate-positioning.py`), price guard (`_assert_no_prices`), capture funnel (`_mailto`), and visual mockups define clear public safety boundaries. We designed 6 Tier 1 tests (frontdoor rendering, capture funnel tagging, visual directions unselected state, estate IA classification, discoverability topics, census metrics) and 5 Tier 2 tests (price token leak, awaiting publish suppression, no-contact plain text, topic validator filters, legacy dead-link detection).
   - For **Feature 7**, the work and phase receipt schemas (`validate_work_receipt`, `validate_phase_receipt`, `verify_work`) define strict cryptographic and structural validation. We designed 6 Tier 1 tests (work receipt schema, phase receipt schema, verify-work CLI, direct human session protection, multi-repo resolution, template generation) and 6 Tier 2 tests (acceptance hash tampering, circular predicate rejection, invalid/extra observed heads, phase digest tampering, corrupt JSON blocks, premature closure).
   - For **Feature 8**, the omega proof engine (`omega`, `validate_omega_pass`, `ready_work`) requires two-pass convergence, distinct observation timestamps, and acyclic phase progression. We designed 6 Tier 1 tests (omega pass schema, two-pass convergence, omega pass record generation, acyclic readiness progression, transitive phase proof enforcement, single remote snapshot reuse) and 6 Tier 2 tests (divergent state digests, identical timestamps, open non-terminal objects, incompatible CLI flags, corrupt/missing pass files, orphan/duplicate markers).
3. **Conclusion**: The resulting test specification comprises **24 Tier 1 tests** and **23 Tier 2 tests** (Total: **47 tests**), surpassing the minimum requirement of 40 tests across Features 5–8.

---

## 3. Caveats

1. **No Production Code Writes**: This investigation was strictly read-only; no production files or test fixtures were modified in the repository.
2. **Hermetic Test Double Requirement**: When implementing the test suite under `tests/e2e_psp_omega/`, all GitHub API interactions (`gh`, `_pages`, `_api`) must be hermetically mocked without live network calls.
3. **Pre-existing Synthetic Receipt Mismatch**: The standalone test `test_committed_receipt_is_the_deterministic_synthetic_run` in `scripts/tests/test_positioning_c10_readiness.py` remains known to fail until the synthetic receipt digest in `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` is regenerated by Milestone 1.

---

## 4. Conclusion

The test specifications for Features 5 through 8 are fully designed, documented, and structured:
- **Comprehensive Detail**: Every test case specifies its target file, test method name, exact inputs, execution commands, and expected assertions.
- **Hermetic Architecture**: Python `unittest` test classes are architected to run with zero network dependencies, isolated temporary directory sandboxes, and monkeypatched GitHub doubles.
- **Specification Delivered**: Full technical analysis and test specifications are written to `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_e2e_2/analysis.md`.

---

## 5. Verification Method

To verify the findings and specifications:

1. **Inspect Analysis and Handoff Reports**:
   ```bash
   view_file /Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_e2e_2/analysis.md
   view_file /Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_e2e_2/handoff.md
   ```

2. **Verify Feature 5 Proof Preflight & Runners**:
   ```bash
   python3 scripts/positioning-proof-preflight.py --json
   pytest scripts/tests/test_positioning_proof_preflight.py scripts/tests/test_positioning_proof_runners.py
   ```

3. **Verify Feature 6 Inbound Positioning Generator**:
   ```bash
   python3 scripts/generate-positioning.py --census
   pytest cli/tests/test_generate_positioning.py
   ```

4. **Verify Feature 7 & 8 Program Verifier & Omega Engine**:
   ```bash
   python3 scripts/positioning-program.py --check
   pytest cli/tests/test_positioning_program.py
   ```
