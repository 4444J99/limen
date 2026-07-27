"""Regression tests for the unchanged-input institutional Omega proof."""

from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest
from limen.omega_owner_receipt import build_owner_receipt, write_owner_receipt
from limen.omega_remediation import load_omega_remediations, remediation_payload

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "omega-two-pass.py"


def _mod():
    spec = importlib.util.spec_from_file_location("omega_two_pass_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sensor_payload(rung_id: str = "sensor.dynamic") -> dict:
    return {
        "rungs": [
            {
                "id": rung_id,
                "label": "dynamic sensor",
                "command": "python3 scripts/sensor-input.txt",
                "semantic_inputs": [{"normalization": "raw", "path": "scripts/sensor-input.txt"}],
                "tier": "det",
            }
        ],
        "schema": "limen.omega_sensor_rungs.v1",
    }


@pytest.fixture
def proof_root(tmp_path):
    root = tmp_path / "checkout"
    remote = tmp_path / "origin.git"
    for directory in (
        root / "scripts",
        root / "institutio" / "governance",
        root / "logs",
        root / "cli" / "src" / "limen",
        root / ".limen-private" / "session-corpus" / "prompt-atoms",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    (root / ".gitignore").write_text(
        "logs/*\n.limen-private/\ninstitutio/governance/sensor-rungs.json\n", encoding="utf-8"
    )
    (root / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    (root / "scripts" / "omega.sh").write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    (root / "scripts" / "omega-two-pass.py").write_text("# proof contract\n", encoding="utf-8")
    (root / "scripts" / "omega-owner-receipt.py").write_text("# owner receipt runner\n", encoding="utf-8")
    (root / "scripts" / "omega-remediation.py").write_text("# remediation contract\n", encoding="utf-8")
    (root / "cli" / "src" / "limen" / "omega_owner_receipt.py").write_text(
        "# owner receipt contract\n",
        encoding="utf-8",
    )
    (root / "scripts" / "input.txt").write_text("core input\n", encoding="utf-8")
    (root / "scripts" / "sensor-input.txt").write_text("sensor input\n", encoding="utf-8")
    (root / "scripts" / "beat-sensors.py").write_text(
        """#!/usr/bin/env python3
from pathlib import Path
root = Path(__file__).resolve().parent.parent
print((root / 'institutio/governance/sensor-rungs.json').read_text())
""",
        encoding="utf-8",
    )
    (root / "institutio" / "governance" / "sensors.yaml").write_text(
        "schema_version: test\nsensors: {}\n", encoding="utf-8"
    )
    core = {
        "rungs": [
            {
                "id": "core.input",
                "label": "core input",
                "semantic_inputs": [{"normalization": "raw", "path": "scripts/input.txt"}],
                "tier": "det",
            },
            {
                "id": "core.tasks",
                "label": "tasks owner",
                "semantic_inputs": [{"normalization": "raw", "path": "tasks.yaml", "role": "owner_receipt"}],
                "tier": "det",
            },
            {
                "id": "core.trial",
                "label": "trial owner",
                "semantic_inputs": [
                    {
                        "normalization": "json",
                        "path": "logs/overnight-trial.json",
                        "volatile_fields": ["generated_at"],
                    },
                    {
                        "max_age_seconds": 300,
                        "normalization": "json",
                        "path": "logs/owner-receipts/core.trial.json",
                        "role": "owner_receipt",
                        "volatile_fields": ["observed_at"],
                    },
                ],
                "tier": "live",
            },
            {
                "id": "core.owner",
                "label": "owner receipt",
                "semantic_inputs": [
                    {
                        "normalization": "json",
                        "path": "logs/owner-receipts/core.owner.json",
                        "role": "owner_receipt",
                        "volatile_fields": ["observed_at"],
                        "max_age_seconds": 300,
                    }
                ],
                "tier": "live",
            },
        ],
        "schema": "limen.omega_rung_registry.v1",
    }
    for rung in core["rungs"]:
        rung["predicate"] = f"python3 scripts/{rung['id'].replace('.', '-')}.py --check"
    _write_json(root / "institutio" / "governance" / "omega-core-rungs.json", core)
    _write_json(root / "institutio" / "governance" / "sensor-rungs.json", _sensor_payload())
    _write_json(
        root / "institutio" / "governance" / "omega-remediations.json",
        {
            "schema": "limen.omega_remediation_registry.v1",
            "defaults": {
                "authority": {
                    "schema_version": "limen.authority_envelope.v1",
                    "actions": ["read"],
                    "repositories": ["organvm/limen"],
                    "path_prefixes": ["."],
                    "external_effects": [],
                    "may_delegate": False,
                },
                "effect": "read",
                "output_ceiling_bytes": 4096,
                "receipt_target": "github:organvm/limen:issue:1571",
                "required_capabilities": ["shell"],
                "work_loan": {
                    "schema_version": "limen.work_loan.v1",
                    "source_origin": "system_debt",
                    "horizon": "present",
                    "value_case": "Close one typed strict-Omega predicate.",
                    "budget_cost": 1,
                    "owner_surface": "fixture",
                    "external_deadline": False,
                    "due_at": None,
                },
            },
            "rungs": [
                {
                    "id": rung["id"],
                    "owner": "fixture-owner",
                    "next_action": "Run the exact fixture predicate.",
                }
                for rung in [*core["rungs"], *_sensor_payload()["rungs"]]
            ],
        },
    )
    _write_json(root / "logs" / "overnight-trial.json", {"generated_at": "one", "verdict": "PASS"})
    prompt_root = root / ".limen-private" / "session-corpus" / "prompt-atoms"
    _write_json(prompt_root / "prompt-atom-ledger.json", {"validation": {"ok": True}})
    (prompt_root / "prompt-events.jsonl").write_text('{"event":"one"}\n', encoding="utf-8")
    _write_json(prompt_root / "source-cursor.json", {"cursor": "sealed"})

    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "omega@example.invalid")
    _git(root, "config", "user.name", "Omega Test")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "fixture")
    _git(root, "commit", "--allow-empty", "-m", "exact main")
    _git(tmp_path, "init", "--bare", str(remote))
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "main")
    return root


def _stamp(root: Path, *, ids: list[str] | None = None, fail: int = 0, skip: int = 0, pass_no: int = 1):
    ids = ids or ["core.input", "core.tasks", "core.trial", "core.owner", "sensor.dynamic"]
    _rungs, remediations = load_omega_remediations(root)
    verdict = "HOLDS" if fail == 0 and skip == 0 else ("BROKEN" if fail else "INCOMPLETE")
    payload = {
        "contract_hash": "a" * 64,
        "fail": fail,
        "generated": f"volatile-{pass_no}",
        "generated_at": f"volatile-{pass_no}",
        "offline": False,
        "pass": len(ids) - fail - skip,
        "rungs": [
            {
                "id": rung_id,
                "rung": rung_id,
                "status": "FAIL" if fail and index == 0 else "SKIP" if skip and index == 0 else "PASS",
                "tier": "det",
                "remediation": remediation_payload(remediations[rung_id]),
            }
            for index, rung_id in enumerate(ids)
        ],
        "schema_version": 3,
        "skip": skip,
        "strict": True,
        "verdict": verdict,
    }
    _write_json(root / "logs" / "omega.json", payload)


def _write_live_owner_receipts(
    root: Path,
    *,
    pass_no: int,
    changed_owner_evidence: bool = False,
    failed_owner: bool = False,
    omit_owner: bool = False,
) -> None:
    payload = json.loads((root / "institutio/governance/omega-core-rungs.json").read_text())
    for rung in payload["rungs"]:
        if rung["tier"] != "live":
            continue
        if omit_owner and rung["id"] == "core.owner":
            continue
        descriptor = next(item for item in rung["semantic_inputs"] if item.get("role") == "owner_receipt")
        evidence = f"{rung['id']}:green"
        if changed_owner_evidence and pass_no == 2 and rung["id"] == "core.owner":
            evidence += ":changed"
        receipt = build_owner_receipt(
            rung_id=rung["id"],
            predicate=rung["predicate"],
            returncode=1 if failed_owner and rung["id"] == "core.owner" else 0,
            stdout=evidence.encode(),
        )
        write_owner_receipt(root / descriptor["path"], receipt)


def _runner(
    mutation=None,
    *,
    mutation_pass: int = 1,
    fail: int = 0,
    skip: int = 0,
    changed_owner_evidence: bool = False,
    failed_owner: bool = False,
    omit_owner: bool = False,
):
    def run(root: Path, pass_no: int) -> int:
        _write_live_owner_receipts(
            root,
            pass_no=pass_no,
            changed_owner_evidence=changed_owner_evidence,
            failed_owner=failed_owner,
            omit_owner=omit_owner,
        )
        _stamp(root, fail=fail, skip=skip, pass_no=pass_no)
        if pass_no == mutation_pass and mutation:
            mutation(root)
        return 0

    return run


def test_two_pass_success_is_content_addressed_byte_idempotent_and_check_only(proof_root):
    module = _mod()
    receipt = proof_root / "logs" / "omega-two-pass.json"
    first = module.run_two_pass(proof_root, receipt, _runner())
    before = receipt.read_bytes()
    assert first["changed"] is True
    assert first["passes"] == 2
    second = module.run_two_pass(proof_root, receipt, _runner())
    assert second["changed"] is False
    assert receipt.read_bytes() == before
    checked = module.check_receipt(proof_root, receipt)
    assert checked["changed"] is False
    assert receipt.read_bytes() == before


@pytest.mark.parametrize(
    "mutation",
    [
        lambda root: (root / "tasks.yaml").write_text("tasks: [changed]\n", encoding="utf-8"),
        lambda root: (root / "scripts" / "input.txt").write_text("dirty tree\n", encoding="utf-8"),
        lambda root: (root / "new-work.txt").write_text("new work\n", encoding="utf-8"),
    ],
    ids=["tasks-change", "tree-change", "new-untracked-work"],
)
def test_tracked_or_new_work_between_passes_fails_closed(proof_root, mutation):
    module = _mod()
    with pytest.raises(module.OmegaProofError, match="checkout is not clean"):
        module.run_two_pass(proof_root, proof_root / "logs" / "receipt.json", _runner(mutation))


def test_head_drift_between_passes_fails_closed(proof_root):
    module = _mod()

    def mutate(root):
        _git(root, "commit", "--allow-empty", "-m", "drift")

    with pytest.raises(module.OmegaProofError, match="not exact origin/main"):
        module.run_two_pass(
            proof_root,
            proof_root / "logs" / "receipt.json",
            _runner(mutate, mutation_pass=2),
        )


def test_origin_drift_between_passes_fails_closed(proof_root):
    module = _mod()

    def mutate(root):
        _git(root, "update-ref", "refs/remotes/origin/main", "HEAD^")

    with pytest.raises(module.OmegaProofError, match="not exact origin/main"):
        module.run_two_pass(proof_root, proof_root / "logs" / "receipt.json", _runner(mutate))


@pytest.mark.parametrize("mode", ["append", "rewrite"])
def test_prompt_append_or_rewrite_between_passes_fails_closed(proof_root, mode):
    module = _mod()

    def mutate(root):
        path = root / ".limen-private/session-corpus/prompt-atoms/prompt-events.jsonl"
        if mode == "append":
            path.write_text(path.read_text(encoding="utf-8") + '{"event":"two"}\n', encoding="utf-8")
        else:
            path.write_text('{"event":"rewritten"}\n', encoding="utf-8")

    with pytest.raises(module.OmegaProofError, match="prompt_digest"):
        module.run_two_pass(
            proof_root,
            proof_root / "logs" / "receipt.json",
            _runner(mutate, mutation_pass=2),
        )


def test_trial_or_owner_receipt_change_between_passes_fails_closed(proof_root):
    module = _mod()

    def mutate_trial(root):
        _write_json(root / "logs/overnight-trial.json", {"generated_at": "two", "verdict": "FAIL"})

    with pytest.raises(module.OmegaProofError, match="trial_digest|owner_receipt_digest"):
        module.run_two_pass(
            proof_root,
            proof_root / "logs" / "receipt.json",
            _runner(mutate_trial, mutation_pass=2),
        )


def test_declared_volatile_trial_field_does_not_change_identity(proof_root):
    module = _mod()

    def mutate(root):
        _write_json(root / "logs/overnight-trial.json", {"generated_at": "two", "verdict": "PASS"})

    result = module.run_two_pass(
        proof_root,
        proof_root / "logs" / "receipt.json",
        _runner(mutate, mutation_pass=2),
    )
    assert result["ok"] is True


def test_owner_receipt_change_or_missing_evidence_fails_closed(proof_root):
    module = _mod()
    with pytest.raises(module.OmegaProofError, match="owner_receipt_digest"):
        module.run_two_pass(
            proof_root,
            proof_root / "logs" / "receipt.json",
            _runner(changed_owner_evidence=True),
        )


def test_missing_semantic_evidence_fails_before_suites(proof_root):
    module = _mod()
    with pytest.raises(module.OmegaProofError, match="missing source-owned receipt"):
        module.run_two_pass(
            proof_root,
            proof_root / "logs" / "receipt.json",
            _runner(omit_owner=True),
        )


def test_failed_live_owner_receipt_cannot_be_downgraded_by_a_green_stamp(proof_root):
    module = _mod()
    with pytest.raises(module.OmegaProofError, match="source-owned receipt is FAIL"):
        module.run_two_pass(
            proof_root,
            proof_root / "logs" / "receipt.json",
            _runner(failed_owner=True),
        )


@pytest.mark.parametrize("change", ["add", "remove", "rename"])
def test_sensor_add_remove_or_rename_between_passes_fails_closed(proof_root, change):
    module = _mod()

    def mutate(root):
        path = root / "institutio/governance/sensor-rungs.json"
        payload = _sensor_payload()
        if change == "add":
            payload["rungs"].append(
                {
                    "id": "sensor.added",
                    "label": "added",
                    "command": "python3 scripts/sensor-input.txt --added",
                    "semantic_inputs": [{"normalization": "raw", "path": "scripts/sensor-input.txt"}],
                    "tier": "det",
                }
            )
        elif change == "remove":
            payload["rungs"] = []
        else:
            payload = _sensor_payload("sensor.renamed")
        _write_json(path, payload)

    with pytest.raises(module.OmegaProofError, match="rung|registry is empty|remediation"):
        module.run_two_pass(proof_root, proof_root / "logs" / "receipt.json", _runner(mutate))


@pytest.mark.parametrize("fail,skip", [(1, 0), (0, 1)])
def test_fail_or_skip_stamp_is_rejected_even_if_runner_returns_zero(proof_root, fail, skip):
    module = _mod()
    with pytest.raises(module.OmegaProofError, match="did not hold"):
        module.run_two_pass(
            proof_root,
            proof_root / "logs" / "receipt.json",
            _runner(fail=fail, skip=skip),
        )


@pytest.mark.parametrize("mode", ["missing", "tampered"])
def test_missing_or_tampered_remediation_stamp_cannot_settle(proof_root, mode):
    module = _mod()

    def run(root: Path, pass_no: int) -> int:
        _stamp(root, pass_no=pass_no)
        stamp = root / "logs" / "omega.json"
        payload = json.loads(stamp.read_text(encoding="utf-8"))
        if mode == "missing":
            payload["rungs"][0].pop("remediation")
        else:
            payload["rungs"][0]["remediation"]["owner"] = "wrong-owner"
        _write_json(stamp, payload)
        return 0

    with pytest.raises(module.OmegaProofError, match="remediation metadata differs"):
        module.run_two_pass(proof_root, proof_root / "logs" / "receipt.json", run)


def test_check_detects_tamper_without_rewriting_receipt(proof_root):
    module = _mod()
    receipt = proof_root / "logs" / "receipt.json"
    module.run_two_pass(proof_root, receipt, _runner())
    receipt.write_bytes(receipt.read_bytes() + b" ")
    tampered = receipt.read_bytes()
    with pytest.raises(module.OmegaProofError, match="canonical or content-addressed"):
        module.check_receipt(proof_root, receipt)
    assert receipt.read_bytes() == tampered
