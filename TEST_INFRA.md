# E2E Test Infra: PSP Omega Recovery

## Test Philosophy
- Opaque-box, requirement-driven. Derived strictly from `ORIGINAL_REQUEST.md`, `AGENTS.md`, and repo specifications.
- Methodology: Category-Partition + Boundary Value Analysis + Pairwise Combinatorial Testing + Real-World Workload Testing.

## Feature Inventory & Test Coverage Map
| # | Feature | Source (Requirement) | Tier 1 (Feature) | Tier 2 (Boundary) | Tier 3 (Pairwise) | Tier 4 (Scenario) |
|---|---------|----------------------|:----------------:|:-----------------:|:-----------------:|:-----------------:|
| 1 | Worktree Isolation & Topic Branches | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 2 | Review-Loop Circuit Breaker & Quarantine | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 3 | Single-Push Exact-Tree Verification | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 4 | Canonical Identity & 4-Tier Offers | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 5 | Proof & Case-Study Architecture | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 6 | Public Portfolio & Front Door | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 7 | Durable Receipts & Verification Schemas | ORIGINAL_REQUEST §Acceptance | 5 | 5 | ✓ | ✓ |
| 8 | Terminal Two-Pass Omega Proof | AGENTS.md, PSP-C12 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- **Test Harness Runner**: `tests/e2e_psp_omega/runner.py` (or test runner script)
- **Invocation**: `python3 -m unittest discover -s tests/e2e_psp_omega` or dedicated pytest invocation
- **Pass/Fail Semantics**: Exit code 0 on 100% pass; non-zero on any test failure.
- **Directory Layout**:
  - `tests/e2e_psp_omega/tier1_features/` (Unit / functional feature tests)
  - `tests/e2e_psp_omega/tier2_boundaries/` (Boundary, empty input, invalid token, corrupt receipt tests)
  - `tests/e2e_psp_omega/tier3_combinations/` (Pairwise interaction tests, e.g. circuit-breaker + worktree isolation)
  - `tests/e2e_psp_omega/tier4_scenarios/` (End-to-end recovery, positioning delivery, and receipt verification flows)

## Real-World Application Scenarios (Tier 4)
| # | Scenario | Features Exercised | Complexity |
|---|----------|--------------------|------------|
| 1 | Full Lifecycle Positioning Run: Identity → Proof → Front Door | F1, F4, F5, F6, F7 | High |
| 2 | Automated Review Loop Detection & Circuit Breaker Eviction | F2, F3, F7 | High |
| 3 | Parallel Worktree Execution with Concurrent Isolation | F1, F3, F7 | High |
| 4 | Corrupted Receipt Recovery & Exact-Tree Validation | F3, F7, F8 | Medium |
| 5 | End-to-End Terminal Omega Proof Verification | F4, F5, F6, F7, F8 | High |

## Coverage Thresholds
- Tier 1: ≥ 40 test cases (≥5 per feature across 8 features)
- Tier 2: ≥ 40 test cases (≥5 per feature across 8 features)
- Tier 3: ≥ 8 test cases (covering major feature pairs)
- Tier 4: ≥ 5 realistic application scenarios
- **Total minimum**: ≥ 93 test cases
