# Handoff Report: Investigation of C04 / PR #2414 Dictionary Lookup Guard in `scripts/positioning-proof-preflight.py`

**Agent:** `teamwork_preview_explorer_m1_1`  
**Working Directory:** `/Users/4jp/Workspace/limen/.agents/teamwork_preview_explorer_m1_1`  
**Parent:** `teamwork_preview_orchestrator_m1_circuit_breaker` (Conversation ID: `77054add-a69a-4859-b1fb-458f9988742d`)  
**Timestamp:** 2026-08-15T15:23:00Z  

---

## 1. Observation

### 1.1 Context & PR #2414 Review Finding
In PR #2414 (`fix(positioning): harden C04 proof receipts`, branch `codex/psp-c04-proof-experience-preflight` on commit `70521ebd6d41f9d595f7106b1ea9ace27ab5d11c`), an automated review comment by `chatgpt-codex-connector` raised a P2 finding:
```text
https://github.com/organvm/limen/blob/70521ebd6d41f9d595f7106b1ea9ace27ab5d11c/scripts/positioning-proof-preflight.py#L973
P2 Badge: Filter malformed commercial artifacts during lookup

When an external contract puts a non-object before the partnership row in `commercial_artifact_set.artifacts`, such as `[null, ...]`, the preceding loop records `commercial artifact must be an object` but this generator nevertheless calls `.get()` on that value. The resulting `AttributeError` is not caught by `main()`, so malformed evidence produces a traceback instead of the structured fail-closed validation result; restrict this lookup to dictionary rows.
```

### 1.2 Exact Location & Code in `scripts/positioning-proof-preflight.py`
- **On branch `codex/psp-c04-proof-experience-preflight` (lines 972–976):**
  ```python
  972:            partnership = next(
  973:                (artifact for artifact in artifacts if artifact.get("id") == "product_operating_partnership_review"),
  974:                {},
  975:            )
  ```
- **On `main` (lines 318–321):**
  ```python
  318:            partnership = next(
  319:                (artifact for artifact in artifacts if artifact.get("id") == "product_operating_partnership_review"),
  320:                {},
  321:            )
  ```

### 1.3 Verbatim Defect Reproduction
Executing `scripts/positioning-proof-preflight.py` `validate()` against a contract where `commercial_artifact_set.artifacts` contains non-dict elements (e.g. `[None, ...]` or `["malformed", ...]`) reproduces the failure:
```python
contract = mod.load_contract(mod.DEFAULT_CONTRACT)
contract['commercial_artifact_set']['artifacts'].insert(0, None)
errors = mod.validate(contract)
```
**Output:**
```text
CAUGHT EXCEPTION: <class 'AttributeError'> 'NoneType' object has no attribute 'get'
```
The unhandled `AttributeError` bypasses `main()`'s structured exception handler (which catches `OSError, json.JSONDecodeError, subprocess.TimeoutExpired, ValueError`), resulting in an uncaught process crash instead of a structured fail-closed validation report.

### 1.4 Exhaustive Audit of All Artifact & Generator Lookups
We performed an AST and pattern scan across `scripts/positioning-proof-preflight.py` (both on `main` and branch `codex/psp-c04-proof-experience-preflight`):
1. **`c03_dependency` lookup (line 907 branch / line 261 main):**
   - On branch: `c03_dependency = next((dependency for dependency in dependencies if isinstance(dependency, dict) and dependency.get("id") == "c03_identity_offers"), {})` — **Guarded with `isinstance(dependency, dict)`**.
   - On `main`: lacked `isinstance(dependency, dict)`.
2. **`partnership` lookup (line 972 branch / line 318 main):**
   - `partnership = next((artifact for artifact in artifacts if artifact.get("id") == "product_operating_partnership_review"), {})` — **UNGUARDED (DEFECT)**.
3. **`audited_ids` lookup (line 811 branch / line 172 main):**
   - `audited_ids = [row.get("work_id") for row in audits if isinstance(row, dict)]` — **Guarded with `isinstance(row, dict)`**.
4. **`artifact_ids` lookup (line 947 branch / line 293 main):**
   - `artifact_ids = {artifact.get("id") for artifact in artifacts if isinstance(artifact, dict)}` — **Guarded with `isinstance(artifact, dict)`**.
5. **`source_ids` lookup (line 981 branch / line 329 main):**
   - `source_ids = {source.get("id") for source in sources if isinstance(source, dict)}` — **Guarded with `isinstance(source, dict)`**.
6. **`_contract_canonical_binding_request` lookups (lines 3936, 3947 branch):**
   - Both `dependency_sources` and `artifacts` comprehensions include `if isinstance(row, dict)` / `if isinstance(artifact, dict)` — **Guarded**.
7. **`validate_demo_fixture` `records_by_id` lookups (lines 2794, 2797 branch):**
   - `records_by_id` is populated only with validated `dict` items (`if not isinstance(record, dict): continue`), making downstream `.get()` lookups safe.

---

## 2. Logic Chain

1. **Root Cause:** In `validate()`, the validation of `commercial_artifact_set.artifacts` iterates through `artifacts` and records validation errors for non-dict items (`if not isinstance(artifact, dict): errors.append(...)`). However, immediately afterwards, `partnership = next((artifact for artifact in artifacts if artifact.get("id") == ...), {})` iterates over the same raw `artifacts` list. If any non-dict object precedes the matching dictionary (or if all items are malformed), Python evaluates `artifact.get("id")` on a non-dict object, raising `AttributeError`.
2. **Impact:** `main()` only traps expected system and serialization exceptions (`OSError, json.JSONDecodeError, subprocess.TimeoutExpired, ValueError`). `AttributeError` crashes the preflight CLI with a raw Python stack trace instead of returning structured JSON with exit code 1.
3. **Defensive Fix:** Updating the generator filter to:
   ```python
   partnership = next(
       (
           artifact
           for artifact in artifacts
           if isinstance(artifact, dict) and artifact.get("id") == "product_operating_partnership_review"
       ),
       {},
   )
   ```
   guarantees that non-dict items are skipped during the search.
4. **Fallback Safety:** If no matching dictionary is found or if `artifacts` contains only malformed rows, `partnership` falls back to `{}`. The subsequent check:
   ```python
   if partnership.get("levels") != ["L3"] or partnership.get("public_front_door") is not False:
       errors.append("product operating partnership review must remain L3-only and off the public front door")
   ```
   runs safely against `{}` (`partnership.get("levels")` returns `None != ["L3"]`), correctly appending a structured error without raising exceptions.
5. **Circuit Breaker Resolution:** Applying this exact single-change fix to the worktree branch, verifying all preflight test suites, and pushing in one clean commit resolves the PR #2414 review loop without triggering further automated review ping-pong.

---

## 3. Caveats

- **Scope boundary:** This report covers `scripts/positioning-proof-preflight.py` and its test suite. It does not modify source code directly in accordance with read-only explorer constraints.
- **Dependency on other M1 items:** Feature 5 (`docs/receipts/positioning/preflights/2026-08-10-psp-c10-readiness-synthetic.json`) is being investigated by explorer `m1_3` to restore the 1 failing test out of 252 in the broader positioning suite (`test_committed_receipt_is_the_deterministic_synthetic_run`). The C04 proof preflight unit tests (`scripts/tests/test_positioning_proof_preflight.py`) currently pass 20/20.

---

## 4. Conclusion & Proposed Code Fix

### 4.1 Proposed Code Patch for `scripts/positioning-proof-preflight.py`

#### On Branch `codex/psp-c04-proof-experience-preflight` (around line 972):
```python
<<<<
            partnership = next(
                (artifact for artifact in artifacts if artifact.get("id") == "product_operating_partnership_review"),
                {},
            )
====
            partnership = next(
                (
                    artifact
                    for artifact in artifacts
                    if isinstance(artifact, dict) and artifact.get("id") == "product_operating_partnership_review"
                ),
                {},
            )
>>>>
```

#### On `main` (lines 318–321 and line 261 for complete consistency):
```python
<<<<
    c03_dependency = next(
        (dependency for dependency in dependencies if dependency.get("id") == "c03_identity_offers"),
        {},
    )
...
            partnership = next(
                (artifact for artifact in artifacts if artifact.get("id") == "product_operating_partnership_review"),
                {},
            )
====
    c03_dependency = next(
        (
            dependency
            for dependency in dependencies
            if isinstance(dependency, dict) and dependency.get("id") == "c03_identity_offers"
        ),
        {},
    )
...
            partnership = next(
                (
                    artifact
                    for artifact in artifacts
                    if isinstance(artifact, dict) and artifact.get("id") == "product_operating_partnership_review"
                ),
                {},
            )
>>>>
```

### 4.2 Proposed Regression Unit Test
Add the following test to `scripts/tests/test_positioning_proof_preflight.py`:
```python
    def test_malformed_commercial_artifacts_fail_closed_without_attribute_error(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["commercial_artifact_set"]["artifacts"].insert(0, None)
        changed["commercial_artifact_set"]["artifacts"].append("not-a-dict")
        errors = MODULE.validate(changed)
        self.assertIn("commercial artifact must be an object", errors)
```

---

## 5. Verification Method

### 5.1 Python Reproducer Probe
Execute the following verification command to confirm that `validate()` handles malformed artifacts cleanly without `AttributeError`:
```bash
python3 -c "
import json
import importlib.util

spec = importlib.util.spec_from_file_location('preflight', 'scripts/positioning-proof-preflight.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

contract = mod.load_contract(mod.DEFAULT_CONTRACT)
contract['commercial_artifact_set']['artifacts'].insert(0, None)
contract['commercial_artifact_set']['artifacts'].append('not-a-dict')

errors = mod.validate(contract)
assert 'commercial artifact must be an object' in errors
print('PROBE PASSED: validate() failed closed with structured errors:', errors)
"
```

### 5.2 Unit Test Execution
Run the dedicated preflight test suite:
```bash
pytest scripts/tests/test_positioning_proof_preflight.py scripts/tests/test_positioning_proof_runners.py
```
Expected: 100% tests pass (20/20).

### 5.3 CLI Execution
Run the script directly in validate mode:
```bash
python3 scripts/positioning-proof-preflight.py --mode validate
python3 scripts/positioning-proof-preflight.py --mode validate --json
```
Expected: exit code 0 and `PASS`.
