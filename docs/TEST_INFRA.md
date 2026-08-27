# TEST_INFRA.md — Ecosystem Liveness & Telemetry Test Infrastructure

## Overview & Mission

This document defines the comprehensive end-to-end (E2E) testing infrastructure and validation matrix for organ liveness, proprioception, and telemetry across `organvm/limen`.

The mission of this test suite is to provide an authoritative, automated, multi-tiered test framework ensuring that:
1. All core telemetry collectors (Vitals, Bifrons, Observatory, Observation Feed) operate reliably and produce schema-valid outputs (`limen.observation.feed.v1`).
2. Proprioceptive health matrices (`scripts/organ-health.py`) derive true autonomic state from live signals rather than faith, correctly identifying `green`, `stale`, `down`, and `gated` rungs.
3. Dark-disabling of default-ON safety organs is strictly caught before production impact.
4. Edge conditions, boundary pressures, missing databases, and corrupted artifacts fail open gracefully while preserving accurate defect reporting.
5. The full operational heartbeat cycle, autonomic recovery workflows, and idempotent closeout fixed points are mathematically verified.

---

## 4-Tier Test Architecture

```
+-------------------------------------------------------------------------------+
| Tier 4: Real-World Operational Scenarios                                      |
| - Full Heartbeat Telemetry Cycle Execution                                    |
| - Organ Failure & Autonomic Recovery Lifecycle                                |
| - Closeout Idempotent Fixed-Point Verification                                |
+---------------------------------------+---------------------------------------+
                                        |
+---------------------------------------v---------------------------------------+
| Tier 3: Cross-Feature & Multi-Organ Integration                               |
| - Vitals Shedding -> Feed Status -> Organ Health -> Scoped Gates              |
| - Bifrons Star Intake -> Observation Feed -> PORTAL.md -> Signal Matrix       |
| - Dark-Disabled Gate Drift Detection (--strict enforcement)                  |
| - Continuous Multi-Beat Telemetry Accumulation & Validation                   |
+---------------------------------------+---------------------------------------+
                                        |
+---------------------------------------v---------------------------------------+
| Tier 2: Boundary & Corner Conditions                                          |
| - Missing / Empty / Corrupted Observation Feed Files Fail-Open & Detection   |
| - Corrupted Timestamps & Malformed JSON Validation Rejections                |
| - Absent & Unreadable Portal SQLite Databases (Fail-Open vs Doctor)           |
| - Extreme System Pressure (Load/RAM/Swap) Throttling & Shedding              |
| - Defect Trail Precedence Over Freshness Timestamps                          |
+---------------------------------------+---------------------------------------+
                                        |
+---------------------------------------v---------------------------------------+
| Tier 1: Feature Coverage & Unit Contracts (11 Primary Assertions)             |
| 1. Bifrons Doctor Liveness Probe       7. Observation Composite Status        |
| 2. Bifrons Check Determinism           8. Observation Feed Schema Validation  |
| 3. Bifrons Metabolize & Signal Gen     9. Observation Feed Emission & Check   |
| 4. Observation Vitals Collector       10. Organ Health Matrix Derivation      |
| 5. Observation Bifrons Collector      11. Closeout / No-Tasks-On-Me Predicate |
| 6. Observation Observatory Collector                                          |
+-------------------------------------------------------------------------------+
```

---

## Test Inventory & Verification Matrix

| Tier | Test ID | Description | Primary Target | Expected Output / Assertion |
|---|---|---|---|---|
| **Tier 1** | `test_tier1_01_bifrons_doctor_liveness_probe` | Doctor probe validates portal store, engine CLI, and alchemia module | `scripts/bifrons-organ.py` (`doctor()`) | Returns 0 when all 3 legs present; returns 1 on any missing/broken leg |
| **Tier 1** | `test_tier1_02_bifrons_check_predicate_determinism` | Rendered `PORTAL.md` compared against current database state | `scripts/bifrons-organ.py` (`--check`) | Returns 0 on identical content; returns 1 on stale or modified content |
| **Tier 1** | `test_tier1_03_bifrons_metabolize_and_signal_generation` | Full metabolize execution renders markdown and generates `bifrons-portal.json` | `scripts/bifrons-organ.py` (`write_signal()`) | Valid signal JSON with `organ`, `beat`, `counts`, `exchanges_by_state` |
| **Tier 1** | `test_tier1_04_observation_vitals_collection` | System vitals collected via `limen.vigilia.vitals` | `limen.observation.collect_vitals` | Level int (1-4), action in `('ok', 'throttle', 'shed')`, valid load/mem |
| **Tier 1** | `test_tier1_05_observation_bifrons_collection` | Star portal counts and gate status extracted | `limen.observation.collect_bifrons` | `stars`, `dossiers`, `resonance_edges`, `awaiting_gate` >= 0, valid status |
| **Tier 1** | `test_tier1_06_observation_observatory_collection` | Legibility and traction metrics collected | `limen.observation.collect_observatory` | `hero`, `external_gaps`, `internal_gaps`, `top_mechanism` extracted |
| **Tier 1** | `test_tier1_07_observation_composite_status_derivation` | Composite status derived across vitals action and collector statuses | `limen.observation.determine_status` | Returns `'shed'`, `'degraded'`, or `'ok'` based on priority reduction |
| **Tier 1** | `test_tier1_08_observation_feed_schema_validation` | Strict JSON schema verification for `limen.observation.feed.v1` | `limen.observation.validate_feed_record` | Zero violations on compliant records; explicit error messages on malformed records |
| **Tier 1** | `test_tier1_09_observation_feed_emission_and_check` | Emits to `feed.jsonl` & `feed-latest.json` and verifies both | `scripts/observation-feed.py` | `check_feed()` passes with `ok=True, errors=[]` |
| **Tier 1** | `test_tier1_10_organ_health_matrix_derivation` | Derives health matrix from loop cadences and voice stamps | `scripts/organ-health.py` (`build()`) | Status computed (`green`, `stale`, `down`, `gated`, `unknown`), gate integrity tracked |
| **Tier 1** | `test_tier1_11_closeout_no_tasks_on_me_predicate` | Validates his-hand-levers registry integrity, PII firewall, and issue pointers | `scripts/no-tasks-on-me.sh` logic | Levers owned, traceable, zero clinical PII shapes, all have issue pointers |
| **Tier 2** | `test_tier2_01_observation_feed_missing_files_fail_check` | Missing `feed-latest.json` or `feed.jsonl` handled gracefully | `limen.observation.check_feed` | `ok=False`, explicit missing file error strings reported |
| **Tier 2** | `test_tier2_02_observation_feed_empty_jsonl_detected` | Empty `feed.jsonl` file identified as check violation | `limen.observation.check_feed` | `ok=False`, reports `feed.jsonl is empty` |
| **Tier 2** | `test_tier2_03_observation_feed_corrupted_jsonl_detected` | Non-JSON text inside `feed.jsonl` identified with line number | `limen.observation.check_feed` | `ok=False`, reports `feed.jsonl line N parse error` |
| **Tier 2** | `test_tier2_04_observation_feed_corrupted_timestamp_rejected` | Non-ISO timestamp strings in feed records rejected | `limen.observation.validate_feed_record` | Violation contains `observed_at ... is not a valid ISO-8601 timestamp` |
| **Tier 2** | `test_tier2_05_bifrons_absent_database_fails_open` | Missing `portal.db` fails open during beat run | `scripts/bifrons-organ.py` (`portal_counts()`) | `present=False`, `status="absent"`, 0 counts; beat exits 0 |
| **Tier 2** | `test_tier2_06_bifrons_corrupted_database_fails_doctor` | Unreadable/corrupted database detected by doctor probe | `scripts/bifrons-organ.py` (`doctor()`) | `status="unreadable"`, doctor exits 1 |
| **Tier 2** | `test_tier2_07_vitals_extreme_pressure_shedding_and_throttling` | High system load triggers vitals level 3/4 and action `shed`/`throttle` | `limen.vigilia.vitals` & `limen.observation` | Composite status switches to `"shed"` or `"degraded"` |
| **Tier 2** | `test_tier2_08_organ_health_defect_overrides_fresh_timestamp` | Self-reported defect in organ artifact overrides 0.0h voice stamp | `scripts/organ-health.py` (`build()`) | Status marks `down`, note records defect message and recorded age |
| **Tier 2** | `test_tier2_09_organ_health_trail_order_and_timestamp_accuracy` | Multi-trail defect searching respects declared precedence | `scripts/organ-health.py` (`_json_nested_error`) | First matching trail wins; UTC offsets handled without artificial youth |
| **Tier 3** | `test_tier3_01_vitals_shedding_to_observation_feed_to_health_matrix` | End-to-end integration: Vitals shed -> Feed status shed -> Health matrix | Full telemetry chain | Feed records `status="shed"`, latest JSON updated, organ health reflects state |
| **Tier 3** | `test_tier3_02_bifrons_star_intake_to_observation_telemetry_to_portal_render` | Integration: Portal DB update -> Observation feed -> `PORTAL.md` render | Portal & Observation chain | Incremented star count reflected in both `PORTAL.md` and `feed-latest.json` |
| **Tier 3** | `test_tier3_03_dark_disabled_safety_gate_drift_triggers_strict_failure` | Dark-disabled safety gate (`LIMEN_VIGILIA=0`) detected and rejected | `scripts/organ-health.py` (`main(["--strict"])`) | Exit code 1 returned; dark-disabled organ identified in `gate_integrity` |
| **Tier 3** | `test_tier3_04_observation_continuous_multi_beat_emission_and_integrity` | Consecutive beat emissions maintain append-only JSONL and fresh latest | `scripts/observation-feed.py` | Multi-line `feed.jsonl` validates completely with all records matching schema |
| **Tier 4** | `test_tier4_01_full_heartbeat_telemetry_cycle` | Comprehensive simulated heartbeat cycle across all organs | Entire liveness architecture | All artifacts produced (`feed.jsonl`, `feed-latest.json`, `bifrons-portal.json`, `organ-health.json`, `organ-health.html`) and valid |
| **Tier 4** | `test_tier4_02_organ_failure_and_autonomic_recovery_lifecycle` | Organ state degradation -> detection -> healing -> green restoration | Autonomic recovery loop | Status accurately transitions `green` -> `down` -> `green` across beats |
| **Tier 4** | `test_tier4_03_closeout_idempotent_fixed_point` | Closeout validation lifecycle achieves idempotent fixed point | `scripts/no-tasks-on-me.sh` & closeout | Verification produces zero mutations, zero dangling tasks, exit code 0 on repeat |

---

## Test Infrastructure Design

### 1. Test Suite Location & Conventions
- **Test File**: `cli/tests/e2e/test_ecosystem_liveness.py`
- **Framework**: `pytest` (>= 8.0)
- **Isolation**: Every test operates within isolated `tmp_path` fixtures or temporary directories, preventing mutation of live repository data (`logs/`, `tasks.yaml`, `his-hand-levers.json`).
- **Dependencies**: Uses Python standard library, `pytest`, and `limen` CLI packages (`cli/src/limen`).

### 2. Execution Commands

```bash
# Run full E2E ecosystem liveness test suite:
python3 -m pytest cli/tests/e2e/test_ecosystem_liveness.py -v

# Run by specific tier:
python3 -m pytest cli/tests/e2e/test_ecosystem_liveness.py -k "test_tier1" -v
python3 -m pytest cli/tests/e2e/test_ecosystem_liveness.py -k "test_tier2" -v
python3 -m pytest cli/tests/e2e/test_ecosystem_liveness.py -k "test_tier3" -v
python3 -m pytest cli/tests/e2e/test_ecosystem_liveness.py -k "test_tier4" -v

# Run scoped pre-push verification:
scripts/verify-scoped.sh
```

---

## Authoritative Output Derivation

Expected outputs are derived directly from the canonical system contracts:
1. `SCHEMA_V1 = "limen.observation.feed.v1"` in `cli/src/limen/observation/collector.py`.
2. Discovery contracts in `spec/avtopoiesis/canon.yaml` and `scripts/heartbeat-loop.sh`.
3. Gate specifications in `institutio/governance/gates.yaml`.
4. Closeout predicates in `scripts/no-tasks-on-me.sh` and `AGENTS.md`.
5. Bifrons doctor contract in `scripts/bifrons-organ.py`.
