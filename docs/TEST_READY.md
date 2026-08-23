# TEST_READY.md — Ecosystem Liveness & Telemetry Test Suite

## Executive Summary

The end-to-end (E2E) test infrastructure and validation test suite for organ liveness and telemetry across `organvm/limen` is established, fully automated, and verified.

- **Test Suite Path**: `tests/e2e/test_ecosystem_liveness.py`
- **Test Infrastructure Doc**: `TEST_INFRA.md`
- **Total Test Count**: 27 tests across 4 tiers
- **Suite Execution Result**: **27 PASSED / 0 FAILED** (100% pass rate)
- **Execution Time**: ~27.7s

---

## Tier Summary & Coverage Breakdown

| Tier | Focus Area | Test Count | Status |
|---|---|:---:|:---:|
| **Tier 1** | Feature Coverage & Unit Contracts (11 Primary Assertions) | 11 | **PASSED** |
| **Tier 2** | Boundary & Corner Conditions (9 Edge Cases) | 9 | **PASSED** |
| **Tier 3** | Cross-Feature & Multi-Organ Integration (4 Pipeline Flows) | 4 | **PASSED** |
| **Tier 4** | Real-World Operational Scenarios (3 Scenarios) | 3 | **PASSED** |
| **Total** | **Comprehensive E2E Liveness Test Suite** | **27** | **100% PASS** |

---

## Feature Checklist

### Tier 1: Feature Coverage (11 Features)
- [x] **T1.1**: `test_tier1_01_bifrons_doctor_liveness_probe` — Portal store, engine CLI, and alchemia module validation.
- [x] **T1.2**: `test_tier1_02_bifrons_check_predicate_determinism` — Deterministic `PORTAL.md` render checking & staleness detection.
- [x] **T1.3**: `test_tier1_03_bifrons_metabolize_and_signal_generation` — Estate crawling, beat execution, and `logs/bifrons-portal.json` generation.
- [x] **T1.4**: `test_tier1_04_observation_vitals_collection` — `collect_vitals()` system pressure level, action (`ok`/`throttle`/`shed`), and metrics.
- [x] **T1.5**: `test_tier1_05_observation_bifrons_collection` — `collect_bifrons()` star absorption, dossiers, resonance edges, and gate counts.
- [x] **T1.6**: `test_tier1_06_observation_observatory_collection` — `collect_observatory()` hero repository, external/internal gap metrics, and mechanisms.
- [x] **T1.7**: `test_tier1_07_observation_composite_status_derivation` — `determine_status()` status reduction across vitals and organ statuses.
- [x] **T1.8**: `test_tier1_08_observation_feed_schema_validation` — `validate_feed_record()` strict compliance against `limen.observation.feed.v1`.
- [x] **T1.9**: `test_tier1_09_observation_feed_emission_and_check` — `emit_feed_record()` and `check_feed()` lifecycle validation.
- [x] **T1.10**: `test_tier1_10_organ_health_matrix_derivation` — `organ-health.py` cadence discovery, door parsing, and status matrix derivation.
- [x] **T1.11**: `test_tier1_11_closeout_no_tasks_on_me_predicate` — `no-tasks-on-me.sh` levers registry validation, PII firewall, and issue pointers.

### Tier 2: Boundary & Edge Conditions (9 Edge Cases)
- [x] **T2.1**: `test_tier2_01_observation_feed_missing_files_fail_check` — Missing feed files detected with explicit errors.
- [x] **T2.2**: `test_tier2_02_observation_feed_empty_jsonl_detected` — Empty `feed.jsonl` detected and reported.
- [x] **T2.3**: `test_tier2_03_observation_feed_corrupted_jsonl_detected` — Exact line number identified for corrupted JSON lines.
- [x] **T2.4**: `test_tier2_04_observation_feed_corrupted_timestamp_rejected` — Non-ISO and invalid timestamps rejected by schema validator.
- [x] **T2.5**: `test_tier2_05_bifrons_absent_database_fails_open` — Missing database fails open gracefully with 0 counts on beat run.
- [x] **T2.6**: `test_tier2_06_bifrons_corrupted_database_fails_doctor` — Corrupted database returns `status="unreadable"` and doctor exit 1.
- [x] **T2.7**: `test_tier2_07_vitals_extreme_pressure_shedding_and_throttling` — Load pressure level 3/4 transitions action to `throttle`/`shed`.
- [x] **T2.8**: `test_tier2_08_organ_health_defect_overrides_fresh_timestamp` — Self-reported defect inside artifact overrides fresh voice stamp.
- [x] **T2.9**: `test_tier2_09_organ_health_trail_order_and_timestamp_accuracy` — Multi-trail defect searching order and UTC offset parsing accuracy.

### Tier 3: Cross-Feature Integrations (4 Integration Flows)
- [x] **T3.1**: `test_tier3_01_vitals_shedding_to_observation_feed_to_health_matrix` — Vitals shedding -> Feed status `shed` -> Health matrix proprioception.
- [x] **T3.2**: `test_tier3_02_bifrons_star_intake_to_observation_telemetry_to_portal_render` — Star intake in DB -> Observation feed -> `PORTAL.md` render.
- [x] **T3.3**: `test_tier3_03_dark_disabled_safety_gate_drift_triggers_strict_failure` — Strict mode catches dark-disabled default-ON safety gates.
- [x] **T3.4**: `test_tier3_04_observation_continuous_multi_beat_emission_and_integrity` — Multi-beat sequential emission, append-only JSONL, and fresh latest.

### Tier 4: Real-World Scenarios (3 Scenarios)
- [x] **T4.1**: `test_tier4_01_full_heartbeat_telemetry_cycle` — Full heartbeat tick generating `bifrons-portal.json`, `feed.jsonl`, `feed-latest.json`, `organ-health.json`, `organ-health.html`.
- [x] **T4.2**: `test_tier4_02_organ_failure_and_autonomic_recovery_lifecycle` — Autonomic recovery cycle (`green` -> `down` -> `green`).
- [x] **T4.3**: `test_tier4_03_closeout_idempotent_fixed_point` — Closeout validation reaches idempotent fixed point with zero dangling tasks.

---

## Runner Commands

```bash
# Run the entire E2E liveness test suite:
python3 -m pytest tests/e2e/test_ecosystem_liveness.py -v

# Run individual tiers:
python3 -m pytest tests/e2e/test_ecosystem_liveness.py -k "test_tier1" -v
python3 -m pytest tests/e2e/test_ecosystem_liveness.py -k "test_tier2" -v
python3 -m pytest tests/e2e/test_ecosystem_liveness.py -k "test_tier3" -v
python3 -m pytest tests/e2e/test_ecosystem_liveness.py -k "test_tier4" -v

# Run scoped pre-push verification:
scripts/verify-scoped.sh
```
