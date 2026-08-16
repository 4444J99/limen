# Handoff Report: Investigation of Synthetic Receipt Failure in `test_positioning_c10_readiness.py`

**Agent ID**: `teamwork_preview_explorer_m1_3`  
**Working Directory**: `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_m1_3`  
**Target File**: `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json`  
**Test File**: `scripts/tests/test_positioning_c10_readiness.py`  
**Generator File**: `scripts/positioning-c10-readiness.py`  

---

## 1. Observation

### 1.1 Test Failure
Running `pytest scripts/tests/test_positioning_c10_readiness.py` fails on exactly one test:
```text
=================================== FAILURES ===================================
__________ test_committed_receipt_is_the_deterministic_synthetic_run ___________

    def test_committed_receipt_is_the_deterministic_synthetic_run() -> None:
>       result = MODULE.verify_receipt(RECEIPT)
                 ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

scripts/tests/test_positioning_c10_readiness.py:300: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
scripts/positioning-c10-readiness.py:1334: in verify_receipt
    _expect(observed == expected, f"synthetic receipt drifted from deterministic dry run: {receipt_path}")
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

condition = False
message = 'synthetic receipt drifted from deterministic dry run: /Users/4jp/Workspace/limen/docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json'

    def _expect(condition: bool, message: str) -> None:
        if not condition:
>           raise ReadinessError(message)
E           positioning_c10_readiness.ReadinessError: synthetic receipt drifted from deterministic dry run: /Users/4jp/Workspace/limen/docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json

scripts/positioning-c10-readiness.py:198: ReadinessError
=========================== short test summary info ============================
FAILED scripts/tests/test_positioning_c10_readiness.py::test_committed_receipt_is_the_deterministic_synthetic_run
========================= 1 failed, 14 passed in 1.32s =========================
```

### 1.2 Full Test Suite Status
Running `pytest scripts/tests/test_positioning_*.py cli/tests/test_positioning_*.py`:
- 252 tests collected across 12 test modules.
- 251 passed, 1 failed (`test_committed_receipt_is_the_deterministic_synthetic_run`).

### 1.3 Exact JSON Drift Diff
A structural and cryptographic comparison between the committed receipt `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` and the output of `MODULE.build_receipt()` (`scripts/positioning-c10-readiness.py:build_receipt()`) reveals exactly two value discrepancies:

```diff
--- a/docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json
+++ b/docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json
@@ -135,7 +135,7 @@
     "fixture_path": "docs/positioning/program/psp-c10-readiness/synthetic-fixture.json",
     "fixture_sha256": "aa2712df09413f107956c70a24df81249259708228945e2f98bba720c9f45d3a",
     "program_manifest_path": "institutio/positioning/program.yaml",
-    "program_registry_projection_sha256": "6a4e1221a88f304726273339470e29d208e59282e236f39744c71ac4ecfb8a73",
+    "program_registry_projection_sha256": "ad1237b9432371157f4b21f45bf551b218fba525eb6c6cbd8b6a61e4ab8a4bc5",
     "source_bindings": [
       {
         "counts_as_closure": false,
@@ -482,7 +482,7 @@
           "src/content/case-studies",
           "public"
         ],
-        "target_repo": "organvm/portfolio",
+        "target_repo": "organvm-vii-kerygma/portfolio",
         "title": "Produce the first consented public case study"
       },
       {
```

### 1.4 Canonical Source Inspection
In `institutio/positioning/program.yaml:1892-1896`:
```yaml
      - id: PSP-P12-W04
        title: Produce the first consented public case study
        outcome: Commercial proof shows problem, decisions, intervention, outcome, limitations, and authorship without client leakage.
        target_repo: organvm-vii-kerygma/portfolio
        target_paths: [src/content/case-studies, public]
```
The canonical program manifest specifies `target_repo: organvm-vii-kerygma/portfolio`.

### 1.5 Generator CLI and Interface
In `scripts/positioning-c10-readiness.py:1309-1360`:
```python
def write_receipt(
    receipt_path: Path = DEFAULT_RECEIPT,
    contract_path: Path = DEFAULT_CONTRACT,
    fixture_path: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    receipt = build_receipt(contract_path, fixture_path)
    content = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(content, encoding="utf-8")
    return {
        "status": "written",
        "receipt": _relative(receipt_path),
        "receipt_sha256": _sha256_path(receipt_path),
        "commercial_proof": False,
        "external_effects": [],
    }

def verify_receipt(
    receipt_path: Path,
    contract_path: Path = DEFAULT_CONTRACT,
    fixture_path: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    observed = _load_json(receipt_path)
    expected = build_receipt(contract_path, fixture_path)
    _expect(observed == expected, f"synthetic receipt drifted from deterministic dry run: {receipt_path}")
    return {
        "status": "ok",
        "receipt": _relative(receipt_path),
        "receipt_sha256": _sha256_path(receipt_path),
        "commercial_proof": False,
        "external_effects": [],
    }
```
CLI arguments supported by `scripts/positioning-c10-readiness.py`:
- `--check`: validates contract against registry projection and synthetic fixture.
- `--dry-run`: outputs computed deterministic JSON receipt to stdout.
- `--write-receipt [PATH]`: writes deterministic JSON receipt to `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` (or specified path).
- `--verify-receipt PATH`: verifies a receipt file against live deterministic computation.

---

## 2. Logic Chain

1. **Test Execution & Expectation**:
   - `test_committed_receipt_is_the_deterministic_synthetic_run()` calls `MODULE.verify_receipt(RECEIPT)` where `RECEIPT` is `/Users/4jp/Workspace/limen/docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json`.
   - `verify_receipt()` compares `_load_json(receipt_path)` against `build_receipt()`.
   - If `observed != expected`, `verify_receipt()` raises `ReadinessError("synthetic receipt drifted from deterministic dry run: ...")`.

2. **Mechanism of Projection & Digest**:
   - `build_receipt()` invokes `validate_contract()`, which extracts the C10 work items from `graph` (derived from `institutio/positioning/program.yaml`) via `_registry_projection(program, graph, "PSP-C10", work_ids)`.
   - For `PSP-P12-W04`, `graph["work_by_id"]["PSP-P12-W04"]["target_repo"]` was updated to `"organvm-vii-kerygma/portfolio"`.
   - `_registry_projection()` builds a dictionary containing `registry_projection["work"]` with all 7 leaf contracts for C10.
   - At line 615 of `scripts/positioning-c10-readiness.py`, `registry_projection_sha256` is calculated as `_sha256_json(registry_projection)`.
   - Because `target_repo` in `PSP-P12-W04` changed from `"organvm/portfolio"` to `"organvm-vii-kerygma/portfolio"`, the canonical JSON digest of `registry_projection` evaluates to `ad1237b9432371157f4b21f45bf551b218fba525eb6c6cbd8b6a61e4ab8a4bc5` (instead of the prior `6a4e1221a88f304726273339470e29d208e59282e236f39744c71ac4ecfb8a73`).

3. **Cause of Test Failure**:
   - The committed receipt file `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` was not regenerated when `program.yaml` repo slug was updated.
   - It retains the obsolete `organvm/portfolio` repo name on line 485 and the obsolete hash `6a4e1221...` on line 138.
   - `observed == expected` fails in `verify_receipt()`.

4. **Resolution Path**:
   - Executing `python3 scripts/positioning-c10-readiness.py --write-receipt` updates `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` with the exact computed JSON.
   - Once written, `verify_receipt()` passes (`observed == expected`).
   - Consequently, all 15 tests in `scripts/tests/test_positioning_c10_readiness.py` and all 252 tests across `pytest scripts/tests/test_positioning_*.py cli/tests/test_positioning_*.py` pass with exit code 0 (100% green).

---

## 3. Caveats

- **Read-Only Explorer Boundary**: In accordance with the system constraints, this agent has NOT directly overwritten `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json`. Instead, the ready-to-apply patch (`receipt_update.patch`) and full proposed JSON (`proposed_2026-08-10-psp-c10-readiness-synthetic.json`) have been placed in this agent's folder.
- **Relay Document Note**: `docs/receipts/positioning/relays/2026-08-10-psp-c10-readiness-preflight.md` is a frozen historical relay record for PR #2321 describing the preflight run at that commit timestamp. It does not gate automated tests, but if the team chooses to refresh documentation digests in relays, that would be a documentation-only update.

---

## 4. Conclusion

- The single test failure in the entire positioning test suite (`test_committed_receipt_is_the_deterministic_synthetic_run`) is caused solely by an unregenerated synthetic receipt file (`docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json`) after `target_repo` in `institutio/positioning/program.yaml` was renamed to `organvm-vii-kerygma/portfolio`.
- The fix is 100% deterministic, self-contained, and requires running a single standard generator command:
  ```bash
  python3 scripts/positioning-c10-readiness.py --write-receipt
  ```
- Alternatively, applying `receipt_update.patch` or copying `proposed_2026-08-10-psp-c10-readiness-synthetic.json` to `docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json` produces the exact same result.

---

## 5. Verification Method

### 5.1 Generator Execution (for Implementation Worker)
```bash
python3 scripts/positioning-c10-readiness.py --write-receipt
```

### 5.2 Direct Receipt Verification
```bash
python3 scripts/positioning-c10-readiness.py --verify-receipt docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json
```
**Expected Output**:
```json
{
  "commercial_proof": false,
  "external_effects": [],
  "receipt": "docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json",
  "receipt_sha256": "b27784d8fe8734fa818d8c985bd09e6b98916c2a12306212c6fa24b6e373f07c",
  "status": "ok"
}
```

### 5.3 Narrow Focused Test Suite
```bash
pytest scripts/tests/test_positioning_c10_readiness.py
```
**Expected Result**: 15 passed, 0 failed, exit code 0.

### 5.4 Full Positioning Test Suite
```bash
pytest scripts/tests/test_positioning_*.py cli/tests/test_positioning_*.py
```
**Expected Result**: 252 passed, 0 failed, exit code 0.

### 5.5 Invalidation Conditions
- Any subsequent edit to `institutio/positioning/program.yaml` affecting chunk `PSP-C10` leaf attributes (such as `target_repo`, `acceptance`, `predicate`, `capabilities`, `human_gates`, `depends_on`) will alter `program_registry_projection_sha256` and require another run of `python3 scripts/positioning-c10-readiness.py --write-receipt`.
