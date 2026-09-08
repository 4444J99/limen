# TEST_INFRA.md — Ecosystem PR Remediation & Verification Test Infrastructure

## Overview & Mission

This document defines the comprehensive end-to-end (E2E) testing infrastructure, validation matrix, and verification architecture for the Limen Ecosystem PR Remediation and Verification Pipeline across all 11 chambers (`4444J99`, `organvm`, `meta-organvm`, `a-organvm`, `organvm-i-theoria`, `organvm-ii-poiesis`, `organvm-iii-ergon`, `organvm-iv-taxis`, `organvm-v-logos`, `organvm-vi-koinonia`, `organvm-vii-kerygma`), encompassing 249 non-archived repositories and 780 active open pull requests.

The mission of this test harness is to provide an independent, requirement-driven, opaque-box verification framework ensuring that:
1. **R1: Git Rebase & Conflict Resolution (Tier 1)**: Every candidate PR branch is cleanly rebased onto the latest default branch head (`main` / `master`), resolving merge conflicts while preserving both upstream changes and the PR's intended functionality.
2. **R2: Test & CI Workflow Repair (Tier 2)**: All remediated PRs pass local repository verification gates (`pytest`, `npm test`, `cargo test`, `scripts/verify-scoped.sh`, `mypy`, `ruff`) to confirm 100% green local status prior to pushing.
3. **R3: GitHub Protocol Merge & Branch Reaping (Tier 3)**: Remediated branches enforce force-with-lease safety, exact-head commit matching (`--match-head-commit <SHA>`), standard GitHub merge protocols (`gh pr merge --squash --delete-branch` or `--rebase --delete-branch`), and remote branch deletion.
4. **R4: Zero Unceremonious Closures & Diagnostic Retention (Tier 4)**: No open PR is closed without merging or an explicit, verifiable blocker report. Sensitive architectural PRs remain OPEN with structured diagnostic assessment receipts (`limen.diagnostic_assessment.v1`). Temporary worktrees are completely reaped and pruned (`git worktree remove --force` && `git worktree prune`).
5. **R5: Protected Boundary Invariant Enforcement (Invariant Testing)**: Absolute zero read/write touches to reserved sessions (`limen-private-document-review-20260825`), protected branches (`feat/conduct-role-hardening-and-permissions`), protected chambers (`4444J99/universal-mail--automation`), and active runtime daemons (41 background processes under Codex/OpenCode).

---

## 4-Tier (+ Tier 5 Adversarial & Invariants) Architecture

```
+=========================================================================================+
| TIER 5 / INVARIANT TESTING: Protected Boundary & Adversarial Hardening                  |
| - Private Document Review Isolation (100% untouched)   - Role Hardening Branch Guard    |
| - Universal Mail Automation Protected Chamber          - Active Daemon Preservation     |
| - Forged Receipt & Tampered Hash Detection             - Path Traversal & Alias Intercept|
+--------------------------------------------+--------------------------------------------+
                                             |
+--------------------------------------------v--------------------------------------------+
| TIER 4: Real-World Operational Scenarios (R4)                                           |
| - Temporary Worktree Creation & Reaping              - 0 Unceremonious Closures         |
| - Diagnostic Assessment Schema & Retention           - Multi-Chamber Batch Fault Isolation|
| - Superseded PR Consolidation & Reference Tracking   - Closeout Task Ledger Hygiene     |
+--------------------------------------------+--------------------------------------------+
                                             |
+--------------------------------------------v--------------------------------------------+
| TIER 3: Cross-Feature Combinations (R3)                                                 |
| - Force-With-Lease Remote Push Safety                - Exact-Head Commit Match Policy   |
| - GitHub Standard Merge Execution (--squash/--rebase)- Remote Branch Deletion            |
| - Cryptographic Scoped Receipt Minting               - RFC 8785 Canonical Hash Integrity|
+--------------------------------------------+--------------------------------------------+
                                             |
+--------------------------------------------v--------------------------------------------+
| TIER 2: Boundary & Corner Cases (R2)                                                    |
| - Local Test Suite Execution Gate (pytest/npm/cargo) - Syntax, Lint, and Typecheck Gates|
| - CI Workflow Diagnostics & Minimal Fix Application  - Timeout & Resource Bounding      |
| - Hermetic Environment Isolation (0 Side-Effects)    - Empty & Broken Fixture Handling  |
+--------------------------------------------+--------------------------------------------+
                                             |
+--------------------------------------------v--------------------------------------------+
| TIER 1: Feature Coverage & Unit Contracts (R1)                                          |
| - Default Branch Discovery (main / master)           - Clean Rebase Against Default Head|
| - 3-Way Merge Conflict Resolution Preservation       - Detached HEAD & Rebase Abort Safe|
| - Fast-Forward Mergeability Identification           - Commit Author Provenance Retain  |
+=========================================================================================+
```

---

## Requirements Verification Matrix (R1–R5 / F1–F9)

| Requirement | Category | Primary Target | Scope & Assertions | Harness Tests | Pipeline Tests | Liveness Tests |
|---|---|---|---|---|---|---|
| **R1** | Git Rebase & Conflict Resolution | Candidate PRs | Clean rebase onto default branch, 3-way conflict resolution, author provenance | T1.1–T1.5 | 15 tests | — |
| **R2** | Test & CI Workflow Repair | Local Test Gates | `pytest`, `npm test`, `cargo test`, `scripts/verify-scoped.sh`, lint/typecheck | T2.1–T2.5 | 20 tests | 9 tests |
| **R3** | GitHub Merge & Branch Deletion | Push & Merge Flow | Force-with-lease, exact-head match, `--delete-branch`, `limen.scoped_verification_receipt.v1` | T3.1–T3.5 | 15 tests | 4 tests |
| **R4** | Zero Unceremonious Closures & Reaping | Worktree & Lifecycle | Zero unceremonious closes, worktree reaping, `limen.diagnostic_assessment.v1`, closeout | T4.1–T4.5 | 15 tests | 3 tests |
| **R5** | Protected Boundary Invariants | Reserved Sessions | Zero-touch on private review, role hardening branch, universal mail, 41 active daemons | INV.1–INV.5 | 20 tests | 11 tests |

---

## Test Inventory & Execution Catalog

### Test Suites
1. **`tests/e2e/verify_ecosystem_prs.py`** (**26 tests + Standalone CLI Runner**)
   - Tier 1: Feature Coverage (R1 - 5 tests)
   - Tier 2: Boundary & Corner Cases (R2 - 5 tests)
   - Tier 3: Cross-Feature Combinations (R3 - 5 tests)
   - Tier 4: Real-World Scenarios (R4 - 5 tests)
   - Invariant Testing: Protected Boundary Invariants (R5 - 5 tests)
   - Full E2E Ecosystem Verification Cycle (1 test)
2. **`tests/e2e/test_pr_remediation_pipeline.py`** (**111 tests**)
   - Tier 1: Feature Coverage F1–F9 (45 tests)
   - Tier 2: Boundary & Corner Cases F1–F9 (45 tests)
   - Tier 3: Pairwise Cross-Feature Combinations (10 tests)
   - Tier 4: Real-World Multi-Chamber Scenarios (5 tests)
   - Tier 5: Adversarial Challenger Hardening (6 tests)
3. **`tests/e2e/test_ecosystem_liveness.py`** (**27 tests**)
   - Tier 1: Liveness & Telemetry contracts (11 tests)
   - Tier 2: Boundary & Corner conditions (9 tests)
   - Tier 3: Cross-Organ Telemetry integration (4 tests)
   - Tier 4: Real-World Heartbeat & Autonomic recovery (3 tests)

**Total Test Count**: **164 tests** across all comprehensive E2E verification suites.

---

## Execution Commands

```bash
# 1. Run standalone requirement-driven E2E verification harness:
python3 tests/e2e/verify_ecosystem_prs.py

# 2. Run standalone harness with live environment invariant probes:
python3 tests/e2e/verify_ecosystem_prs.py --live

# 3. Run standalone harness by specific tier:
python3 tests/e2e/verify_ecosystem_prs.py --tier 1
python3 tests/e2e/verify_ecosystem_prs.py --tier 2
python3 tests/e2e/verify_ecosystem_prs.py --tier 3
python3 tests/e2e/verify_ecosystem_prs.py --tier 4
python3 tests/e2e/verify_ecosystem_prs.py --invariants

# 4. Generate JSON verification report:
python3 tests/e2e/verify_ecosystem_prs.py --json --output docs/receipts/e2e_verification_report.json

# 5. Run full E2E test suites via pytest:
python3 -m pytest tests/e2e/verify_ecosystem_prs.py -v
python3 -m pytest tests/e2e/test_pr_remediation_pipeline.py -v
python3 -m pytest tests/e2e/test_ecosystem_liveness.py -v

# 6. Run all PR remediation suites combined:
python3 -m pytest tests/e2e/test_pr_remediation_pipeline.py tests/e2e/verify_ecosystem_prs.py -v
```

---

## Authoritative Output & Hash Verification

1. **Receipt Schema Contract (`limen.scoped_verification_receipt.v1`)**:
   - Stored in `docs/receipts/remediation_<repo>_<pr>.json`.
   - Contains exact git head commit SHA, verification command, timestamp, cheap wave results, and SHA256 content hash.
2. **Diagnostic Schema Contract (`limen.diagnostic_assessment.v1`)**:
   - Stored in `docs/receipts/diagnostic_<repo>_<pr>.json`.
   - Contains target PR, state (`OPEN`), disposition (`LEAVE_OPEN_WITH_DIAGNOSTIC`), identified blocker taxonomy, and action items.
3. **Protected Boundary Invariant (R5)**:
   - Verified via `EcosystemVerifier.verify_protected_path_guard()` and `ProtectedBoundaryGuard.audit_workspace_integrity()` ensuring 0 file modifications and 0 unapproved accesses.
