# PSP Omega Recovery — Positioning Architecture & Assets Survey Report

**Explorer**: `teamwork_preview_explorer_survey_2`  
**Working Directory**: `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_survey_2`  
**Parent**: `teamwork_preview_orchestrator_1` (`06fefed7-b402-47f8-845b-70619ce1bd5e`)  
**Date**: 2026-08-15T15:10:00Z  

---

## 1. Observation

### A. Program Topology & Control Plane
1. **Canonical Manifest**: `institutio/positioning/program.yaml` (schema `limen.positioning_program.v1`, lines 1–2244) defines the root program `PSP-ROOT` ("Production-Systems Positioning — Alpha to Omega"), 15 execution phases (`PSP-P00` through `PSP-P14`), and 13 execution chunks (`PSP-C00` through `PSP-C12`).
2. **Issue Mapping & Execution Projections**:
   - Manifest check: `python3 scripts/positioning-program.py --check` exits `0`, reporting 15 phases, 111 work packets, 13 execution chunks, and 127 mapped/projected objects.
   - Projections: `docs/positioning/program/ISSUE-INDEX.md` and `docs/positioning/program/EXECUTION-CHUNKS.md`.
   - Worktree topology: Active worktree `/Users/4jp/Workspace/.worktrees/limen-psp-omega-lane-proof-architecture` operates on branch `codex/psp-omega-lane-proof-architecture`.
3. **Closed Phases & Upstream Foundations**:
   - `PSP-P00` / `PSP-C00` (Control Plane): Formally closed at commit `fbab1543a863ba2a86546de1eb31bdb9f0f50388` (PR #2300).
   - `PSP-P01` / `PSP-C01` (Foundation Repair): Formally closed with frozen baseline receipt.
   - `PSP-P02` / `PSP-C02` (Estate Truth & Evidence): Formally closed at exact main head `8faa5fb9899231ebf5f87e78bb171544c11b79d7` (receipt on issue #2172 comment 5270095170, SHA-256 `f312ae3536ced23aa782701b4a437866707c2eec4b6b194ba05a735e2d8bb434`).

---

### B. Canonical Identity & Offer Assets (PSP-C03 / PSP-P03 & PSP-P04)
1. **Canonical Identity Files & Contracts**:
   - `institutio/positioning/commercial-contract.yaml` & `docs/positioning/commercial-contract.md`: Ratifies the core positioning identity as **Production-Systems Architect**, 3 audience contracts (Clients, Recruiters/Executives, Gated Partners), and Level-1/2/3 progressive disclosure.
   - `docs/positioning/authority-and-trust-language.md` (PSP-P03-W06): Anti-hype, zero-trust mechanics, boundaries, plain language, and developer-credibility norms.
   - `docs/positioning/client-narrative-and-problem-map.md` (PSP-P03-W04): ICP definitions, buyer problem map, business impact, and decision criteria.
   - `docs/positioning/claims-ledger.md` (PSP-P02-W06/W07): Ground-truth register of all verifiable claims with source blobs and verification methods.
   - `docs/positioning/estate-classification.md` (PSP-P02-W02): 235 public repositories classified into 15 front-door proof candidates, archive, private custody, etc.
   - `docs/positioning/authorship-disclosure-policy.md`: Rules on human architect direction vs autonomous multi-agent production systems.
2. **Offer Assets & Directory** (`docs/positioning/offers/`):
   - `agentic-delivery-audit.md` (PSP-P04-W01): Diagnostic Audit offer ($5k–$15k symbolic anchor / `PRICE-AUDIT`), bounded 2-week read-only assessment.
   - `agentic-delivery-audit-decision-record.json` (PSP-P04-W01, PR #2422 / commit `9c8a87215`): Formal schema-valid decision record with pricing, deliverables, scope boundaries, and rejection rules.
   - `governance-install.md` (PSP-P04-W02): Governance Install offer ($25k–$60k symbolic anchor / `PRICE-INSTALL`), bounded 4–6 week write implementation.
   - `bounded-delivery-governance-retainer.md` (PSP-P04-W03): Delivery Retainer offer ($10k–$25k/mo symbolic anchor / `PRICE-RETAINER`), capacity-bounded oversight.
   - `product-operating-partnership-review.md` (PSP-P04-W07): Gated partnership diligence (equity/revenue share / `PRICE-PARTNERSHIP`), isolated from L1/L2 front doors.
   - `qualification-and-routing.md` (PSP-P04-W06): Deterministic routing matrix (7 routes: `human_review`, `decline`, `recruiter`, `partnership_review`, `retainer`, `install`, `audit`).
3. **Offer Validation & Tests**:
   - `python3 scripts/positioning-commercial-contract.py --check` → `PASS: PSP-C03 contract binds accepted P02/P03 evidence, the open W07 reader gate, and staged bounded P04 offers`.
   - `python3 scripts/positioning-offer-artifacts.py --check` → `PASS: 5 PSP-P04 offer artifacts match the canonical contract and public-safety boundaries`.
   - `python3 docs/positioning/offers/verify_agentic_delivery_audit_decision.py` → `PASS: PSP-P04-W01 audit is priceable, scopeable, deliverable, and declineable without oral exceptions`.
   - `python3 scripts/tests/positioning-commercial-contract.test.py` → 17 unit tests passed (`Ran 17 tests in 0.441s, OK`).
   - `python3 scripts/tests/positioning-offer-artifacts.test.py` → 13 unit tests passed (`Ran 13 tests in 0.312s, OK`).
4. **Current Status & Blocker**:
   - PSP-P03-W01 through PSP-P03-W06 are accepted.
   - `PSP-P03-W07` (Issue #2188) is the sole open P03 leaf, requiring 5 genuine independent target-like readers.
   - All P04 offer artifacts are materialized and integrated on `main` (PR #2312 and PR #2422), but formal chunk closure remains blocked on `PSP-P03-W07`.

---

### C. Proof & Case-Study Architecture (PSP-C04 / PSP-P05 & PSP-P06)
1. **Proof Architecture Files**:
   - `docs/positioning/case-study-template.md`: Canonical template for Level-2 flagship case study pages (sections: *The expensive problem, What was built, Decisions and tradeoffs, The verification story, What it proves about the method, Current state and honest limits, Doors*).
   - `docs/positioning/flagship-proof-set.yaml` (schema `limen.positioning_flagship_proof_set.v1`): Screened 22 candidate repositories and selected 3 primary flagships:
     1. **Limen** (`organvm/limen`): Governed multi-agent delivery with public operating, failure, and verification receipts (`C02-PROOF-LIMEN`).
     2. **UCC Public-Records Intelligence Platform** (`organvm-iii-ergon/public-record-data-scrapper`): 4 implemented state collectors on a 50-state architecture (`C02-PROOF-PUBLIC-RECORDS`).
     3. **AI Chat Exporter** (`organvm-iii-ergon/a-i-chat--exporter`): Zero-server, 5-format browser export tool (`C02-PROOF-AI-CHAT-EXPORTER`).
   - `docs/positioning/proof/psp-c04-proof-contract.json` (schema `limen.psp_c04_proof_preflight.v3`): Governs the 6 proof classes across PSP-P05 (Limen Engineering Report, Public-Surface Audit, Cost/Failure Economics, Test-Reproduction Receipts, Visual Interactive Architecture Demo, Third-Party Validation).
   - `docs/positioning/proof/PSP-C04-P05-PREFLIGHT.md`: Narrative preflight and downstream binding specification.
   - `docs/positioning/evidence/`: Holds verifiable evidence rows in `flagship-evidence.yaml`, `limen.md`, `ai-chat-exporter.md`, and `public-records.md`.
2. **Proof Tooling & Tests**:
   - `python3 scripts/positioning-proof-preflight.py --json` → Exits `0` with `status: "pass"`, validating all source bindings (`p02_live_registry`, `p02_flagship_selection`, `p02_public_evidence`, `p02_claim_policy`, `p02_claims_ledger`, `c03_identity_offers`) and offer files.
   - Flagship evidence runner: `scripts/positioning-flagship-receipt.py`.
   - Cost & failure reproduction: `scripts/positioning-cost-failure-reproduction.py` (tested via `scripts/tests/fixtures/positioning-proof/synthetic-cost-failure.json`).
3. **Recent Landings**:
   - PR #2421 (commit `97d7d36c3`): Updated Limen's `README.md` and `link-surfaces.json` to make Limen a truthful, bounded Level-2 proof destination with live endpoints and dated gate runs.

---

### D. Public Portfolio & Front Door Implementations (PSP-C06 / PSP-P07)
1. **Public Surfaces & Repositories**:
   - **Canonical Portfolio Repository**: `organvm-vii-kerygma/portfolio` (GitHub repo id `1155412125`, URL `https://organvm-vii-kerygma.github.io/portfolio/`).
   - **GitHub Profile README**: `organvm/4444J99` (personal front door) and `organvm/.github/profile/README.md` (organization estate map).
   - **Front Door Markdown**: `docs/positioning/_frontdoor.md` (generated from `positioning-seeds.json` via `scripts/generate-positioning.py --frontdoor`).
   - **Link Surfaces Registry**: `link-surfaces.json` (tracks public surfaces, remaps historical `4444j99.github.io` and `organvm.github.io` hosts to `organvm-vii-kerygma.github.io`, verified by `scripts/link-health.py`).
   - **Inbound Capture Funnel**: `docs/positioning/_capture.md` (inbound mail flow via `contact@4444j99.dev`, tagged `[<repo> · deploy]` / `[<repo> · hire]`, routed to `obligations-ledger.json` without auto-send).
2. **Visual Directions**:
   - Three digest-pinned visual mockup directions generated in `docs/positioning/visual-directions/psp-c06/`:
     1. `option-1-evidence-ledger.png` (Evidence Ledger layout)
     2. `option-2-systems-field-guide.png` (Systems Field Guide layout)
     3. `option-3-decision-brief.png` (Decision Brief layout)
   - **Status**: All 3 directions remain explicitly **`UNSELECTED`**. PSP-C06 relay (`docs/receipts/positioning/relays/2026-08-10-psp-c06-public-surfaces-preflight.md`) documents that no visual implementation or deployment is authorized until an operator selection receipt is recorded.
3. **Link Health**:
   - 11 legacy dead links to `organvm.github.io/portfolio` remain tracked as an unresolved finding in the C06 relay awaiting path remediation.

---

### E. Durable Receipts System & Verification Infrastructure
1. **Receipt Schemas** (implemented in `scripts/positioning-program.py`):
   - `limen.positioning_work_receipt.v1`: Leaf work receipt with fields `work_id`, `acceptance_sha256`, `outcome: succeeded`, `authority` (broker or direct human session + `human_protected: true`), `observed_heads` (40-char git commit SHA per repo), `changed_paths`, `predicate` (`command`, `exit_code: 0`, `output_sha256`, `observed_at`), `evidence_urls`, and `rollback`.
   - `limen.positioning_phase_receipt.v1`: Aggregate phase receipt with `phase_id`, `outcome: succeeded`, `accepted_head`, `child_receipt_sha256`, `parity_sha256`, and `evidence_urls`.
   - `limen.positioning_omega_pass.v1`: Terminal two-pass convergence receipt.
   - `limen.positioning_model_assignments.v1`: Model & effort assignment validator.
2. **Receipt Storage**:
   - Relays: `docs/receipts/positioning/relays/` (covers C03, C04, C05, C06, C07, C09, C10, C11, C12).
   - Preflights: `docs/receipts/positioning/preflights/` (e.g. `2026-08-10-psp-c10-readiness-synthetic.json`).
   - Remote GitHub Markers: `<!-- positioning-receipt:PSP-Pxx-Wyy -->` and `<!-- positioning-phase-receipt:PSP-Pxx -->` on issue comments.
3. **Observed Synthetic Receipt Drift**:
   - In `pytest scripts/tests/test_positioning_*.py cli/tests/test_positioning_*.py`: 251 tests passed, 1 failed (`test_committed_receipt_is_the_deterministic_synthetic_run` in `scripts/tests/test_positioning_c10_readiness.py`).
   - Root Cause: `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` contains a stale `program_registry_projection_sha256` (`6a4e1221...` vs current `ad1237b9...`) and stale repo string `organvm/portfolio` instead of `organvm-vii-kerygma/portfolio` after `institutio/positioning/program.yaml` was updated.

---

## 2. Logic Chain

1. **Premise**: The PSP Omega Recovery initiative requires completing user-facing positioning outcomes without getting blocked by review-hardening loops.
2. **Observation → Readiness**:
   - Control-plane foundation (`PSP-P00`, `PSP-P01`, `PSP-P02`) is already closed on `main` with durable receipts.
   - Identity & Offer assets (`PSP-P03`, `PSP-P04`) are fully drafted, validated, and integrated into `main` (PR #2312, PR #2422). The sole open leaf in P03 is `PSP-P03-W07` (blind reader intake), which is an external human gate.
   - Proof & Case-Study architecture (`PSP-P05`, `PSP-P06` / `PSP-C04`) is fully articulated: `case-study-template.md`, `flagship-proof-set.yaml`, and `psp-c04-proof-contract.json` are committed, and Limen's `README.md` was recently updated into a bounded proof destination (PR #2421).
   - Public front door & surfaces (`PSP-P07` / `PSP-C06`) are prepared with 3 visual directions in `docs/positioning/visual-directions/psp-c06/`, waiting for the operator visual-direction selection gate.
3. **Deduction on Worktree Isolation**:
   - Because all reversible preparation contracts and validators already pass locally and operate on decoupled file boundaries (`docs/positioning/offers`, `docs/positioning/proof`, `docs/positioning/visual-directions`, `organvm-vii-kerygma/portfolio`), each autonomous lane can execute in an isolated worktree under `/Users/4jp/Workspace/.worktrees/` without cross-lane interference or review-loop deadlocks.
4. **Deduction on Review-Loop Circuit Breaker**:
   - Hardening and preflight relays (such as C04, C05, C06, C11) explicitly decouple the formal execution frontier (`counts_as_closure: false`) from reversible code preparation. A blocker or looping review on one leaf (e.g. W07 reader testing or visual selection) does not block synthetic validation, documentation formalization, or test verification on other independent leaves.

---

## 3. Caveats

1. **External Human Gates**:
   - `PSP-P03-W07` requires 5 genuine target-like readers. Synthetic responses are strictly forbidden.
   - `PSP-C06` visual implementation requires an operator direction selection among the 3 committed PNG options before UI coding begins in `organvm-vii-kerygma/portfolio`.
2. **Zero Auto-Send / No Unsolicited External Mutation**:
   - All email capture and inbound routes (`mailto:contact@4444j99.dev`) and sales pipelines operate in draft/read-only mode. No automated sending, DNS change, or production credential mutation is authorized.
3. **Synthetic Receipt Regeneration Needed**:
   - The test failure in `scripts/tests/test_positioning_c10_readiness.py` is caused by a deterministic sha256 mismatch in `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` after the portfolio slug was normalized in `program.yaml`. Regenerating this receipt will restore a 100% green test suite (252/252 passing).

---

## 4. Conclusion

The positioning architecture and codebase are highly structured, fully specified, and in an advanced preflight/preparation state:
1. **Canonical Identity & Offers**: The "Production-Systems Architect" narrative and 4-tier offer ladder (Audit $5k–$15k, Install $25k–$60k, Retainer $10k–$25k/mo, Operating Partnership) are formally contracted and validated.
2. **Proof & Case Studies**: 3 flagships (Limen, UCC Public-Records Platform, AI Chat Exporter) are locked into `flagship-proof-set.yaml` with passing preflight validators and a canonical case-study template.
3. **Public Portfolio & Front Door**: 3 visual directions exist for `organvm-vii-kerygma/portfolio`, and public markdown front doors (`_frontdoor.md`, `README.md`) are wired to capture funnels.
4. **Durable Receipts**: The schema-enforced receipt system (`limen.positioning_work_receipt.v1` and `limen.positioning_phase_receipt.v1`) ensures immutable, reproducible verification across all phases.

Autonomous positioning lanes can proceed cleanly in isolated topic worktrees under `/Users/4jp/Workspace/.worktrees/`.

---

## 5. Verification Method

To independently verify these findings, run the following commands:

```bash
# 1. Verify program manifest, issue map, and execution chunks:
python3 scripts/positioning-program.py --check

# 2. Verify commercial contract and P02/P03 bindings:
python3 scripts/positioning-commercial-contract.py --check
python3 scripts/tests/positioning-commercial-contract.test.py

# 3. Verify offer artifacts and public safety constraints:
python3 scripts/positioning-offer-artifacts.py --check
python3 scripts/tests/positioning-offer-artifacts.test.py
python3 docs/positioning/offers/verify_agentic_delivery_audit_decision.py

# 4. Verify proof contract and claim bindings:
python3 scripts/positioning-proof-preflight.py --json

# 5. Verify C11 foundry preflight and handoff records:
python3 scripts/positioning-foundry-preflight.py --json
python3 scripts/positioning-foundry-handoff.py --json

# 6. Run positioning unit test suite:
pytest scripts/tests/test_positioning_*.py cli/tests/test_positioning_*.py
```
