#!/usr/bin/env python3
"""Content-addressed proof that strict institutional Omega holds twice on unchanged inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

CLI_SRC = Path(__file__).resolve().parent.parent / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.omega_remediation import (  # noqa: E402
    OmegaRemediationError,
    load_omega_remediations,
    remediation_payload,
)

SCHEMA = "limen.omega_two_pass_receipt.v1"
CORE_SCHEMA = "limen.omega_rung_registry.v1"
SENSOR_SCHEMA = "limen.omega_sensor_rungs.v1"
RUNG_ID_RX = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
NORMALIZATIONS = {"json", "raw"}
VOLATILE_FIELDS = {"generated", "generated_at"}
ROLES = {"input", "owner_receipt"}
PROMPT_REQUIRED = {"prompt-atom-ledger.json", "prompt-events.jsonl", "source-cursor.json"}
STATE_KEYS = (
    "head",
    "tree",
    "origin",
    "tasks_digest",
    "prompt_digest",
    "trial_digest",
    "contract_digest",
    "rung_digest",
    "owner_receipt_digest",
    "semantic_input_digest",
)
CONTRACT_PATHS = (
    "scripts/omega.sh",
    "scripts/omega-two-pass.py",
    "scripts/omega-remediation.py",
    "scripts/beat-sensors.py",
    "institutio/governance/omega-core-rungs.json",
    "institutio/governance/omega-remediations.json",
    "institutio/governance/sensors.yaml",
)


class OmegaProofError(RuntimeError):
    """A fail-closed proof error suitable for a concise operator message."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode("ascii")


def _run(root: Path, *argv: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, cwd=root, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise OmegaProofError(f"command failed ({' '.join(argv)}): {detail or result.returncode}")
    return result


def _git(root: Path, *args: str) -> str:
    return _run(root, "git", *args).stdout.strip()


def _safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if not relative or path.is_absolute() or ".." in path.parts:
        raise OmegaProofError(f"unsafe semantic input path: {relative!r}")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise OmegaProofError(f"semantic input escapes root: {relative!r}") from exc
    return resolved


def _load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise OmegaProofError(f"missing evidence: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OmegaProofError(f"invalid JSON evidence {path}: {exc}") from exc


def _normalized_file(path: Path, normalization: str, volatile_fields: list[str]) -> bytes:
    if normalization not in NORMALIZATIONS:
        raise OmegaProofError(f"unknown normalization {normalization!r} for {path}")
    if set(volatile_fields) - VOLATILE_FIELDS:
        raise OmegaProofError(f"undeclared volatile field for {path}")
    if volatile_fields and normalization != "json":
        raise OmegaProofError(f"volatile fields require JSON normalization for {path}")
    if not path.is_file() or path.is_symlink():
        raise OmegaProofError(f"missing evidence: {path}")
    if normalization == "raw":
        return path.read_bytes()
    value = _load_json(path)
    if volatile_fields:
        if not isinstance(value, dict):
            raise OmegaProofError(f"volatile fields require a JSON object: {path}")
        value = {key: item for key, item in value.items() if key not in volatile_fields}
    return _canonical(value)


def _descriptor(rung_id: str, index: int, raw: object) -> dict:
    if not isinstance(raw, dict):
        raise OmegaProofError(f"{rung_id}: semantic_inputs[{index}] must be a mapping")
    unknown = set(raw) - {"path", "normalization", "volatile_fields", "role"}
    if unknown:
        raise OmegaProofError(f"{rung_id}: semantic_inputs[{index}] has unknown fields {sorted(unknown)}")
    path = str(raw.get("path") or "")
    normalization = str(raw.get("normalization") or "")
    volatile = raw.get("volatile_fields") or []
    role = str(raw.get("role") or "input")
    if not path or Path(path).is_absolute() or ".." in Path(path).parts:
        raise OmegaProofError(f"{rung_id}: semantic input path is unsafe")
    if normalization not in NORMALIZATIONS:
        raise OmegaProofError(f"{rung_id}: unknown normalization {normalization!r}")
    if not isinstance(volatile, list) or any(not isinstance(field, str) for field in volatile):
        raise OmegaProofError(f"{rung_id}: volatile_fields must be a string list")
    if set(volatile) - VOLATILE_FIELDS:
        raise OmegaProofError(f"{rung_id}: undeclared volatile field")
    if volatile and normalization != "json":
        raise OmegaProofError(f"{rung_id}: volatile fields require JSON normalization")
    if role not in ROLES:
        raise OmegaProofError(f"{rung_id}: unknown semantic input role {role!r}")
    return {
        "normalization": normalization,
        "path": path,
        "role": role,
        "volatile_fields": sorted(set(volatile)),
    }


def _validated_rungs(payload: object, schema: str, source: str) -> list[dict]:
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        raise OmegaProofError(f"unknown {source} rung schema")
    raw_rungs = payload.get("rungs")
    if not isinstance(raw_rungs, list) or not raw_rungs:
        raise OmegaProofError(f"{source} rung registry is empty")
    rungs: list[dict] = []
    for index, raw in enumerate(raw_rungs):
        if not isinstance(raw, dict):
            raise OmegaProofError(f"{source} rung[{index}] must be a mapping")
        rung_id = str(raw.get("id") or "")
        if not RUNG_ID_RX.fullmatch(rung_id):
            raise OmegaProofError(f"{source} rung[{index}] has missing or invalid id")
        semantic_inputs = raw.get("semantic_inputs")
        if not isinstance(semantic_inputs, list) or not semantic_inputs:
            raise OmegaProofError(f"{rung_id}: semantic_inputs must be a non-empty list")
        tier = str(raw.get("tier") or "")
        if tier not in {"det", "live"}:
            raise OmegaProofError(f"{rung_id}: invalid tier")
        if not str(raw.get("label") or ""):
            raise OmegaProofError(f"{rung_id}: label is required")
        predicate_field = "predicate" if source == "core" else "command"
        predicate = str(raw.get(predicate_field) or "")
        if not predicate or "\x00" in predicate or len(predicate) > 8192:
            raise OmegaProofError(f"{rung_id}: typed predicate is required")
        rungs.append(
            {
                "id": rung_id,
                "label": str(raw["label"]),
                "predicate": predicate,
                "semantic_inputs": [
                    _descriptor(rung_id, item_index, item) for item_index, item in enumerate(semantic_inputs)
                ],
                "tier": tier,
            }
        )
    return rungs


def discover_rungs(root: Path) -> tuple[list[dict], dict, dict]:
    core_path = root / "institutio" / "governance" / "omega-core-rungs.json"
    core_payload = _load_json(core_path)
    core = _validated_rungs(core_payload, CORE_SCHEMA, "core")
    discovery = _run(root, sys.executable, str(root / "scripts" / "beat-sensors.py"), "--list-omega-json")
    try:
        sensor_payload = json.loads(discovery.stdout)
    except json.JSONDecodeError as exc:
        raise OmegaProofError(f"invalid sensor rung discovery JSON: {exc}") from exc
    sensors = _validated_rungs(sensor_payload, SENSOR_SCHEMA, "sensor")
    rungs = [*core, *sensors]
    ids = [rung["id"] for rung in rungs]
    if len(ids) != len(set(ids)):
        raise OmegaProofError("duplicate Omega rung identity")
    try:
        remediation_rungs, remediations = load_omega_remediations(root, sensor_payload=sensor_payload)
    except OmegaRemediationError as exc:
        raise OmegaProofError(f"invalid Omega remediation contract: {exc}") from exc
    if [rung.id for rung in remediation_rungs] != ids:
        raise OmegaProofError("Omega remediation rung identity differs from the semantic manifest")
    for rung in rungs:
        rung["remediation"] = remediation_payload(remediations[rung["id"]])
    return rungs, core_payload, sensor_payload


def _prompt_digest(root: Path) -> str:
    prompt_root = root / ".limen-private" / "session-corpus" / "prompt-atoms"
    if not prompt_root.is_dir():
        raise OmegaProofError(f"missing prompt authority: {prompt_root}")
    paths = sorted(path for path in prompt_root.rglob("*") if path.is_file() and not path.is_symlink())
    names = {path.relative_to(prompt_root).as_posix() for path in paths}
    missing = PROMPT_REQUIRED - names
    if missing:
        raise OmegaProofError(f"missing prompt authority inputs: {sorted(missing)}")
    entries = [
        {
            "path_digest": _sha256(path.relative_to(prompt_root).as_posix().encode("utf-8")),
            "sha256": _sha256(path.read_bytes()),
        }
        for path in paths
    ]
    return _sha256(_canonical(entries))


def _semantic_digests(root: Path, rungs: list[dict]) -> tuple[str, str]:
    all_entries = []
    owner_entries = []
    for rung in rungs:
        for descriptor in rung["semantic_inputs"]:
            path = _safe_path(root, descriptor["path"])
            digest = _sha256(_normalized_file(path, descriptor["normalization"], descriptor["volatile_fields"]))
            entry = {
                "normalization": descriptor["normalization"],
                "path_digest": _sha256(descriptor["path"].encode("utf-8")),
                "role": descriptor["role"],
                "rung_id": rung["id"],
                "sha256": digest,
                "volatile_fields": descriptor["volatile_fields"],
            }
            all_entries.append(entry)
            if descriptor["role"] == "owner_receipt":
                owner_entries.append(entry)
    if not owner_entries:
        raise OmegaProofError("Omega contract declares no owner receipts")
    return _sha256(_canonical(all_entries)), _sha256(_canonical(owner_entries))


def _unique_semantic_descriptor(rungs: list[dict], relative: str, role: str) -> dict:
    matches = [
        descriptor
        for rung in rungs
        for descriptor in rung["semantic_inputs"]
        if descriptor["path"] == relative and descriptor["role"] == role
    ]
    if len(matches) != 1:
        raise OmegaProofError(f"semantic manifest must declare exactly one {role} descriptor for {relative}")
    return matches[0]


def _contract_digest(root: Path, core_payload: dict, sensor_payload: dict) -> str:
    entries = []
    for relative in CONTRACT_PATHS:
        path = _safe_path(root, relative)
        if not path.is_file() or path.is_symlink():
            raise OmegaProofError(f"missing contract input: {relative}")
        entries.append({"path": relative, "sha256": _sha256(path.read_bytes())})
    entries.append({"core": core_payload, "sensors": sensor_payload})
    return _sha256(_canonical(entries))


def _assert_clean_exact_main(root: Path) -> tuple[str, str, str]:
    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    origin = _git(root, "rev-parse", "refs/remotes/origin/main")
    if head != origin:
        raise OmegaProofError(f"checkout is not exact origin/main: head={head} origin={origin}")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise OmegaProofError("checkout is not clean")
    return head, tree, origin


def capture_state(root: Path) -> tuple[dict, list[str]]:
    head, tree, origin = _assert_clean_exact_main(root)
    rungs, core_payload, sensor_payload = discover_rungs(root)
    semantic_input_digest, owner_receipt_digest = _semantic_digests(root, rungs)
    trial_descriptor = _unique_semantic_descriptor(rungs, "logs/overnight-trial.json", "owner_receipt")
    trial_path = root / trial_descriptor["path"]
    trial_digest = _sha256(
        _normalized_file(
            trial_path,
            trial_descriptor["normalization"],
            trial_descriptor["volatile_fields"],
        )
    )
    tasks_path = root / "tasks.yaml"
    if not tasks_path.is_file() or tasks_path.is_symlink():
        raise OmegaProofError(f"missing tasks projection: {tasks_path}")
    rung_manifest = [
        {
            "id": rung["id"],
            "label": rung["label"],
            "predicate": rung["predicate"],
            "remediation": rung["remediation"],
            "semantic_inputs": rung["semantic_inputs"],
            "tier": rung["tier"],
        }
        for rung in rungs
    ]
    state = {
        "contract_digest": _contract_digest(root, core_payload, sensor_payload),
        "head": head,
        "origin": origin,
        "owner_receipt_digest": owner_receipt_digest,
        "prompt_digest": _prompt_digest(root),
        "rung_digest": _sha256(_canonical(rung_manifest)),
        "semantic_input_digest": semantic_input_digest,
        "tasks_digest": _sha256(tasks_path.read_bytes()),
        "tree": tree,
        "trial_digest": trial_digest,
    }
    return state, rungs


def _omega_stamp(root: Path, expected_rungs: list[dict]) -> tuple[str, str]:
    path = root / "logs" / "omega.json"
    payload = _load_json(path)
    if not isinstance(payload, dict):
        raise OmegaProofError("omega stamp must be a JSON object")
    rungs = payload.get("rungs")
    if payload.get("schema_version") != 3 or not isinstance(rungs, list):
        raise OmegaProofError("omega stamp has an unknown schema")
    expected_ids = [rung["id"] for rung in expected_rungs]
    ids = [str(rung.get("id") or "") for rung in rungs if isinstance(rung, dict)]
    if len(ids) != len(rungs) or ids != expected_ids or len(ids) != len(set(ids)):
        raise OmegaProofError("omega stamp rung identity differs from the semantic manifest")
    expected_remediations = {rung["id"]: rung["remediation"] for rung in expected_rungs}
    if any(row.get("remediation") != expected_remediations.get(str(row.get("id") or "")) for row in rungs):
        raise OmegaProofError("omega stamp remediation metadata differs from the semantic manifest")
    if payload.get("verdict") != "HOLDS" or payload.get("fail") != 0 or payload.get("skip") != 0:
        raise OmegaProofError("strict Omega did not hold without FAIL/SKIP")
    normalized = {key: value for key, value in payload.items() if key not in VOLATILE_FIELDS}
    return _sha256(_canonical(normalized)), str(payload.get("contract_hash") or "")


def _default_omega_runner(root: Path, _pass_number: int) -> int:
    return subprocess.run(["bash", "scripts/omega.sh", "--full", "--strict"], cwd=root, check=False).returncode


def _same_states(states: list[dict]) -> None:
    baseline = states[0]
    for position, state in enumerate(states[1:], start=2):
        changed = [key for key in STATE_KEYS if state.get(key) != baseline.get(key)]
        if changed:
            raise OmegaProofError(f"semantic state changed at checkpoint {position}: {', '.join(changed)}")


def _receipt_bytes(payload: dict) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")


def _seal(payload: dict) -> dict:
    sealed = dict(payload)
    sealed["content_hash"] = _sha256(_canonical(payload))
    return sealed


def _write_atomic(path: Path, data: bytes) -> bool:
    try:
        if path.read_bytes() == data:
            return False
    except FileNotFoundError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        handle.write(data)
        temporary = Path(handle.name)
    os.replace(temporary, path)
    return True


def run_two_pass(
    root: Path,
    receipt: Path,
    omega_runner: Callable[[Path, int], int] | None = None,
) -> dict:
    runner = omega_runner or _default_omega_runner
    before, before_rungs = capture_state(root)
    before_ids = [rung["id"] for rung in before_rungs]
    if runner(root, 1) != 0:
        raise OmegaProofError("strict Omega pass 1 failed")
    pass_one_digest, pass_one_contract = _omega_stamp(root, before_rungs)
    middle, middle_rungs = capture_state(root)
    middle_ids = [rung["id"] for rung in middle_rungs]
    if middle_ids != before_ids:
        raise OmegaProofError("Omega rung identity changed after pass 1")
    if runner(root, 2) != 0:
        raise OmegaProofError("strict Omega pass 2 failed")
    pass_two_digest, pass_two_contract = _omega_stamp(root, middle_rungs)
    after, after_rungs = capture_state(root)
    after_ids = [rung["id"] for rung in after_rungs]
    if after_ids != before_ids:
        raise OmegaProofError("Omega rung identity changed after pass 2")
    _same_states([before, middle, after])
    if pass_one_digest != pass_two_digest or pass_one_contract != pass_two_contract:
        raise OmegaProofError("strict Omega pass evidence changed")
    payload = {
        "omega_contract_hash": pass_one_contract,
        "omega_digest": pass_one_digest,
        "passes": 2,
        "rung_count": len(before_ids),
        "rung_ids": before_ids,
        "schema": SCHEMA,
        "state": before,
    }
    sealed = _seal(payload)
    changed = _write_atomic(receipt, _receipt_bytes(sealed))
    return {"changed": changed, "head": before["head"], "ok": True, "receipt": str(receipt), **sealed}


def _load_receipt(path: Path) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
        receipt = json.loads(raw)
    except FileNotFoundError as exc:
        raise OmegaProofError(f"missing two-pass receipt: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OmegaProofError(f"invalid two-pass receipt {path}: {exc}") from exc
    if not isinstance(receipt, dict) or receipt.get("schema") != SCHEMA:
        raise OmegaProofError("unknown two-pass receipt schema")
    content_hash = receipt.get("content_hash")
    unsigned = {key: value for key, value in receipt.items() if key != "content_hash"}
    if content_hash != _sha256(_canonical(unsigned)) or raw != _receipt_bytes(receipt):
        raise OmegaProofError("two-pass receipt is not canonical or content-addressed")
    return receipt, raw


def check_receipt(root: Path, receipt_path: Path) -> dict:
    receipt, _raw = _load_receipt(receipt_path)
    state, rungs = capture_state(root)
    rung_ids = [rung["id"] for rung in rungs]
    omega_digest, omega_contract_hash = _omega_stamp(root, rungs)
    changed = (
        receipt.get("state") != state
        or receipt.get("rung_ids") != rung_ids
        or receipt.get("rung_count") != len(rung_ids)
        or receipt.get("passes") != 2
        or receipt.get("omega_digest") != omega_digest
        or receipt.get("omega_contract_hash") != omega_contract_hash
    )
    if changed:
        raise OmegaProofError("current semantic state does not reproduce the two-pass receipt")
    return {
        "changed": False,
        "content_hash": receipt["content_hash"],
        "head": state["head"],
        "ok": True,
        "receipt": str(receipt_path),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--run", action="store_true", help="run two strict Omega passes and seal a receipt")
    mode.add_argument("--check", action="store_true", help="reproduce an existing receipt without running suites")
    parser.add_argument("--receipt", type=Path, default=None, help="receipt path (default: logs/omega-two-pass.json)")
    args = parser.parse_args(argv)
    root = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)).resolve()
    receipt = (args.receipt or (root / "logs" / "omega-two-pass.json")).resolve()
    try:
        result = run_two_pass(root, receipt) if args.run else check_receipt(root, receipt)
    except OmegaProofError as exc:
        print(json.dumps({"changed": True, "error": str(exc), "ok": False}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
