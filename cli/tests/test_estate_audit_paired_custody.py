from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import limen.estate_audit_paired_custody as paired_module
import pytest
from limen.estate_audit_custody import CustodyPlan, GeneratedRootRecord
from limen.estate_audit_paired_custody import (
    PRIVATE_RECEIPT_SCHEMA,
    PROJECTION_SCHEMA,
    PairedCustodyError,
    RailRequest,
    VolumeIdentity,
    blocked_projection,
    invoke_single_rail,
    load_target_registry,
    run_paired_custody,
)
from limen.host_admission import AdmissionDenied


def error_code(callable_) -> str:
    with pytest.raises(PairedCustodyError) as raised:
        callable_()
    return raised.value.code


def make_plan(tmp_path: Path, root_count: int = 3) -> CustodyPlan:
    records: list[GeneratedRootRecord] = []
    sources = tmp_path / "sources"
    sources.mkdir(exist_ok=True)
    for ordinal in range(root_count):
        path = sources / f"estate-audit-fixture-{20260730010000 + ordinal}"
        path.mkdir()
        encoded = str(path).encode()
        records.append(
            GeneratedRootRecord(
                path=str(path),
                path_sha256=hashlib.sha256(encoded).hexdigest(),
                source="fixture",
                repository=f"organvm/fixture-{ordinal % 2}",
                head=f"{ordinal + 1:040x}",
                tree=f"{ordinal + 101:040x}",
                tree_entry_count=2,
                index_entry_count=0,
                index_sha256=hashlib.sha256(b"").hexdigest(),
                device=1,
                inode=ordinal + 1,
                mtime_ns=ordinal + 1,
            )
        )
    return CustodyPlan(roots=tuple(records), plan_sha256="a" * 64)


def make_registration(
    tmp_path: Path,
    *,
    include_t7_device: bool = True,
    t7_target_relative: str = "limen-private/estate-audit-git-custody",
    same_stable_identity: bool = False,
    same_uuid: bool = False,
) -> tuple[Path, Path, dict[str, VolumeIdentity]]:
    repository = tmp_path / "repository"
    docs = repository / "docs"
    governance = repository / "institutio" / "governance"
    scripts = repository / "scripts"
    docs.mkdir(parents=True)
    governance.mkdir(parents=True)
    scripts.mkdir(parents=True)
    (scripts / "estate-audit-custody.py").write_text("# fixture\n", encoding="utf-8")

    archive_mount = tmp_path / "Archive4T"
    recovery_mount = tmp_path / "T7Recovery"
    archive_mount.mkdir()
    recovery_mount.mkdir()
    archive = VolumeIdentity(
        mount=str(archive_mount),
        device="/dev/disk41s1",
        physical_device="/dev/disk41",
        volume_uuid="AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        physical_identity="device_" + "1" * 32,
    )
    recovery = VolumeIdentity(
        mount=str(recovery_mount),
        device="/dev/disk71s1",
        physical_device="/dev/disk71",
        volume_uuid=archive.volume_uuid if same_uuid else "BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB",
        physical_identity=archive.physical_identity if same_stable_identity else "device_" + "2" * 32,
    )
    devices = [
        {
            "name": "Archive4T",
            **archive.__dict__,
        }
    ]
    if include_t7_device:
        devices.append(
            {
                "name": "T7Recovery",
                **recovery.__dict__,
            }
        )
    inventory = {
        "schema": "limen.storage_evacuation_inventory.v1",
        "inventory_id": "fixture-inventory",
        "custody_devices": devices,
    }
    inventory_path = docs / "storage-evacuation-inventory-20260727.json"
    inventory_bytes = json.dumps(inventory, indent=2, sort_keys=True).encode() + b"\n"
    inventory_path.write_bytes(inventory_bytes)
    registry = {
        "schema": "limen.estate_audit_paired_custody_targets.v1",
        "inventory": "docs/storage-evacuation-inventory-20260727.json",
        "inventory_id": "fixture-inventory",
        "inventory_sha256": hashlib.sha256(inventory_bytes).hexdigest(),
        "targets": [
            {
                "ref": "archive4t",
                "inventory_name": "Archive4T",
                "custody_root": str(archive_mount / "limen-private" / "estate-audit-git-custody"),
                "stable_physical_identity": archive.physical_identity,
            },
            {
                "ref": "t7recovery",
                "inventory_name": "T7Recovery",
                "custody_root": str(recovery_mount / t7_target_relative),
                "stable_physical_identity": recovery.physical_identity,
            },
        ],
        "proof_status": "registered_not_live_verified",
    }
    registry_path = governance / "estate-audit-custody-targets.json"
    registry_path.write_text(
        json.dumps(registry, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return (
        repository,
        registry_path,
        {
            str(archive_mount): archive,
            str(recovery_mount): recovery,
        },
    )


class FixtureRail:
    def __init__(
        self,
        plan: CustodyPlan,
        *,
        fail: tuple[str, str] | None = None,
        payload_mismatch: str | None = None,
    ) -> None:
        self.plan = plan
        self.fail = fail
        self.payload_mismatch = payload_mismatch
        self.requests: list[RailRequest] = []
        self.apply_counts = {ref: 0 for ref in ("archive4t", "t7recovery")}
        self.content_markers = {"archive4t": "1", "t7recovery": "2"}

    def _ref(self, request: RailRequest) -> str:
        assert request.custody_root is not None
        return "archive4t" if "Archive4T" in str(request.custody_root) else "t7recovery"

    def __call__(self, request: RailRequest) -> dict[str, Any]:
        self.requests.append(request)
        public = self.plan.public_payload()
        if request.mode == "check":
            return {
                "result_schema": "limen.estate_audit_custody_result.v1",
                **public,
                "content_preflight_ok": True,
            }
        ref = self._ref(request)
        if self.fail == (ref, request.mode):
            raise PairedCustodyError(f"fixture-{ref}-{request.mode}-failure")
        if request.mode == "apply":
            assert request.custody_root is not None
            request.custody_root.mkdir(parents=True, exist_ok=True)
            changed = self.apply_counts[ref] == 0
            self.apply_counts[ref] += 1
        else:
            changed = False
        content_marker = self.content_markers[ref]
        payload_marker = "4" if ref == self.payload_mismatch else "3"
        return {
            "result_schema": "limen.estate_audit_custody_result.v1",
            "schema": "limen.estate_audit_custody_receipt.v1",
            "status": "restored",
            **{
                field: public[field]
                for field in (
                    "plan_sha256",
                    "root_count",
                    "repository_count",
                    "head_count",
                    "empty_index_root_count",
                    "indexed_root_count",
                )
            },
            "content_sha256": content_marker * 64,
            "working_payload_manifest_sha256": payload_marker * 64,
            "restoration_passed": True,
            "changed": changed,
        }


class LeaseCounter:
    def __init__(self) -> None:
        self.calls = 0
        self.entries = 0
        self.exits = 0

    @contextmanager
    def hold(self, kind: str, **_kwargs: Any):
        assert kind == "heavy"
        self.calls += 1
        self.entries += 1
        try:
            yield {"allowed": True}
        finally:
            self.exits += 1


def run_fixture(
    tmp_path: Path,
    *,
    plan: CustodyPlan | None = None,
    runner: FixtureRail | None = None,
    registration_options: dict[str, Any] | None = None,
    lease: LeaseCounter | None = None,
) -> tuple[dict[str, Any], FixtureRail, LeaseCounter, Path, Path]:
    plan = plan or make_plan(tmp_path)
    repository, registry, identities = make_registration(
        tmp_path,
        **(registration_options or {}),
    )
    runner = runner or FixtureRail(plan)
    lease = lease or LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()
    projection = run_paired_custody(
        repository_root=repository,
        limen_root=limen_root,
        registry_path=registry,
        single_rail_script=repository / "scripts" / "estate-audit-custody.py",
        max_roots=100,
        max_seconds=60,
        runner=runner,
        volume_probe=lambda mount: identities[str(mount)],
        plan_discoverer=lambda _root, _limit, _deadline: plan,
        lease_factory=lease.hold,
        require_mount=False,
    )
    return projection, runner, lease, repository, registry


def test_dynamic_denominator_comes_from_fresh_underlying_check(tmp_path: Path) -> None:
    plan = make_plan(tmp_path, root_count=7)
    projection, runner, lease, _repository, _registry = run_fixture(
        tmp_path,
        plan=plan,
    )

    assert projection["root_count"] == 7
    assert projection["plan_sha256"] == plan.plan_sha256
    assert [request.mode for request in runner.requests] == [
        "check",
        "apply",
        "apply",
    ]
    applies = [request for request in runner.requests if request.mode == "apply"]
    assert [request.expected_volume_uuid for request in applies] == [
        "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",
        "BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB",
    ]
    assert [request.expected_physical_identity for request in applies] == [
        "device_" + "1" * 32,
        "device_" + "2" * 32,
    ]
    assert lease.calls == lease.entries == lease.exits == 1
    source = (Path(__file__).parents[1] / "src" / "limen" / "estate_audit_paired_custody.py").read_text(
        encoding="utf-8"
    )
    assert "root_count=41" not in source
    assert "root_count=48" not in source
    assert "root_count=50" not in source


def test_fresh_plan_scan_cannot_reset_the_shared_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()
    now = [100.0]
    observed_deadlines: list[float] = []

    monkeypatch.setattr(paired_module.time, "monotonic", lambda: now[0])

    def expired_discovery(_root: Path, _limit: int, deadline: float) -> CustodyPlan:
        observed_deadlines.append(deadline)
        now[0] = deadline
        return plan

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                max_seconds=60,
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=expired_discovery,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "paired-custody-time-limit-exceeded"
    )
    assert observed_deadlines == [160.0]
    assert [request.mode for request in runner.requests] == ["check"]
    assert runner.requests[0].deadline == observed_deadlines[0]
    assert lease.calls == lease.entries == lease.exits == 1
    assert not any(path.name == "paired-receipts" for path in tmp_path.rglob("*"))


def test_missing_or_unregistered_t7_target_fails_before_any_rail(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(
        tmp_path,
        include_t7_device=False,
    )
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "registry-target-invalid"
    )
    assert runner.requests == []

    other = tmp_path / "other"
    repository, registry, identities = make_registration(
        other,
        t7_target_relative="unregistered",
    )
    runner = FixtureRail(plan)
    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "registry-target-path-invalid"
    )
    assert runner.requests == []


def test_registry_cannot_claim_live_proof(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["proof_status"] = "restored"
    registry.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    runner = FixtureRail(plan)
    lease = LeaseCounter()

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=tmp_path / "limen-root",
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "registry-proof-status-invalid"
    )
    assert runner.requests == []


def test_registry_requires_owner_recorded_stable_physical_identity(tmp_path: Path) -> None:
    repository, registry, _identities = make_registration(tmp_path)
    payload = json.loads(registry.read_text(encoding="utf-8"))
    payload["targets"][0]["stable_physical_identity"] = None
    registry.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert (
        error_code(lambda: load_target_registry(registry, repository_root=repository))
        == "registry-stable-physical-identity-missing"
    )


@pytest.mark.parametrize("missing_from", ["inventory", "registry"])
def test_inventory_binding_requires_nonempty_identifiers(
    tmp_path: Path,
    missing_from: str,
) -> None:
    repository, registry, _identities = make_registration(tmp_path)
    registry_payload = json.loads(registry.read_text(encoding="utf-8"))
    if missing_from == "inventory":
        inventory = repository / registry_payload["inventory"]
        inventory_payload = json.loads(inventory.read_text(encoding="utf-8"))
        inventory_payload.pop("inventory_id")
        inventory_bytes = json.dumps(inventory_payload, indent=2, sort_keys=True).encode() + b"\n"
        inventory.write_bytes(inventory_bytes)
        registry_payload["inventory_sha256"] = hashlib.sha256(inventory_bytes).hexdigest()
    else:
        registry_payload["inventory_id"] = ""
    registry.write_text(json.dumps(registry_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    assert (
        error_code(lambda: load_target_registry(registry, repository_root=repository))
        == "registry-inventory-binding-mismatch"
    )


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"same_stable_identity": True}, "targets-share-physical-device"),
        ({"same_uuid": True}, "targets-share-volume-uuid"),
    ],
)
def test_identical_device_identity_fails_before_writes(
    tmp_path: Path,
    options: dict[str, Any],
    expected: str,
) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path, **options)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == expected
    )
    assert runner.requests == []


def test_mismatched_live_identity_and_symlink_fail_before_writes(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()
    t7 = identities[next(path for path in identities if "T7Recovery" in path)]
    mismatched = VolumeIdentity(
        **{**t7.__dict__, "physical_identity": "device_" + "9" * 32},
    )

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: mismatched if "T7Recovery" in str(mount) else identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "t7recovery-identity-mismatch"
    )
    assert runner.requests == []


def test_identity_swap_after_single_rail_returns_blocks_before_pair_write(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()
    calls = 0

    def swapping_probe(mount: Path) -> VolumeIdentity:
        nonlocal calls
        calls += 1
        observed = identities[str(mount)]
        if calls == 4:
            return VolumeIdentity(**{**observed.__dict__, "physical_identity": "device_" + "9" * 32})
        return observed

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=swapping_probe,
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "archive4t-identity-mismatch"
    )
    assert [request.mode for request in runner.requests] == ["check", "apply"]
    assert not any(path.name == "paired-receipts" for path in tmp_path.rglob("*"))


def test_symlink_and_redirected_output_fail_before_writes(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    path_case = tmp_path / "path-case"
    repository, registry, identities = make_registration(path_case)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = path_case / "limen-root"
    limen_root.mkdir()
    t7 = identities[next(path for path in identities if "T7Recovery" in path)]
    target = Path(t7.mount) / "limen-private" / "estate-audit-git-custody"
    target.parent.mkdir()
    target.symlink_to(tmp_path / "elsewhere", target_is_directory=True)
    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "target-path-symlink"
    )
    assert runner.requests == []

    output_case = tmp_path / "output-case"
    repository, registry, identities = make_registration(output_case)
    runner = FixtureRail(plan)
    limen_root = output_case / "limen-root"
    limen_root.mkdir()
    registered = load_target_registry(registry, repository_root=repository)
    archive_target = registered.targets[0].custody_root
    archive_target.mkdir(parents=True)
    (archive_target / "repositories").symlink_to(
        output_case / "redirected",
        target_is_directory=True,
    )
    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "target-output-invalid"
    )
    assert runner.requests == []


def test_source_target_and_control_output_overlap_fail_before_apply(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    registered = load_target_registry(registry, repository_root=repository)
    archive_target = registered.targets[0].custody_root
    overlapping_record = GeneratedRootRecord(**{**plan.roots[0].__dict__, "path": str(archive_target / "source")})
    overlapping = CustodyPlan(
        roots=(overlapping_record, *plan.roots[1:]),
        plan_sha256=plan.plan_sha256,
    )
    runner = FixtureRail(overlapping)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: overlapping,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "target-source-overlap"
    )
    assert [request.mode for request in runner.requests] == ["check"]

    runner = FixtureRail(plan)
    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=archive_target / "live",
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "target-control-path-overlap"
    )
    assert runner.requests == []


def test_existing_pair_receipt_symlink_fails_before_any_apply(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    registered = load_target_registry(registry, repository_root=repository)
    receipt_directory = registered.targets[0].custody_root / "paired-receipts"
    receipt_directory.mkdir(parents=True)
    (receipt_directory / f"{plan.plan_sha256}.json").symlink_to(
        tmp_path / "redirected-receipt.json",
    )
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "paired-receipt-not-regular"
    )
    assert [request.mode for request in runner.requests] == ["check"]


def test_oversized_prepared_record_fails_before_any_apply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    registered = load_target_registry(registry, repository_root=repository)
    receipt_directory = registered.targets[0].custody_root / "paired-receipts"
    receipt_directory.mkdir(parents=True)
    receipt = receipt_directory / f"{plan.plan_sha256}.json"
    monkeypatch.setattr(paired_module, "MAX_PREPARED_RECORD_BYTES", 64)
    receipt.write_bytes(b"x" * 65)
    receipt.chmod(0o600)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    with pytest.raises(PairedCustodyError) as raised:
        run_paired_custody(
            repository_root=repository,
            limen_root=limen_root,
            registry_path=registry,
            single_rail_script=repository / "scripts" / "estate-audit-custody.py",
            runner=runner,
            volume_probe=lambda mount: identities[str(mount)],
            plan_discoverer=lambda _root, _limit, _deadline: plan,
            lease_factory=lease.hold,
            require_mount=False,
        )
    public = blocked_projection(raised.value)
    assert public["error"] == "paired-receipt-size-limit"
    assert str(tmp_path) not in json.dumps(public, sort_keys=True)
    assert [request.mode for request in runner.requests] == ["check"]


def test_admission_denial_is_path_free_and_precedes_every_write(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    runner = FixtureRail(plan)

    @contextmanager
    def denied(_kind: str, **_kwargs: Any):
        raise AdmissionDenied(
            {
                "allowed": False,
                "reasons": ["pressure-sensor-unavailable"],
            }
        )
        yield {}

    with pytest.raises(PairedCustodyError) as raised:
        run_paired_custody(
            repository_root=repository,
            limen_root=tmp_path / "limen-root",
            registry_path=registry,
            single_rail_script=repository / "scripts" / "estate-audit-custody.py",
            runner=runner,
            volume_probe=lambda mount: identities[str(mount)],
            plan_discoverer=lambda _root, _limit, _deadline: plan,
            lease_factory=denied,
            require_mount=False,
        )
    public = blocked_projection(raised.value)
    encoded = json.dumps(public, sort_keys=True)
    assert public == {
        "schema": PROJECTION_SCHEMA,
        "status": "blocked",
        "error": "host-admission-denied",
        "reasons": ["pressure-sensor-unavailable"],
    }
    assert str(tmp_path) not in encoded
    assert runner.requests == []
    assert not any(path.name == "paired-receipts" for path in tmp_path.rglob("*"))


@pytest.mark.parametrize(
    ("failure", "expected_modes"),
    [
        (("archive4t", "apply"), ["check", "apply"]),
        (
            ("t7recovery", "apply"),
            ["check", "apply", "apply"],
        ),
    ],
)
def test_first_or_second_rail_failure_never_projects_terminal(
    tmp_path: Path,
    failure: tuple[str, str],
    expected_modes: list[str],
) -> None:
    plan = make_plan(tmp_path)
    runner = FixtureRail(plan, fail=failure)
    repository, registry, identities = make_registration(tmp_path)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    assert error_code(
        lambda: run_paired_custody(
            repository_root=repository,
            limen_root=limen_root,
            registry_path=registry,
            single_rail_script=repository / "scripts" / "estate-audit-custody.py",
            runner=runner,
            volume_probe=lambda mount: identities[str(mount)],
            plan_discoverer=lambda _root, _limit, _deadline: plan,
            lease_factory=lease.hold,
            require_mount=False,
        )
    ).startswith("fixture-")
    assert [request.mode for request in runner.requests] == expected_modes
    assert not any(path.name == "paired-receipts" for path in tmp_path.rglob("*"))


def test_both_rails_must_restore_the_same_working_payload_manifest(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    runner = FixtureRail(plan, payload_mismatch="archive4t")
    repository, registry, identities = make_registration(tmp_path)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    assert (
        error_code(
            lambda: run_paired_custody(
                repository_root=repository,
                limen_root=limen_root,
                registry_path=registry,
                single_rail_script=repository / "scripts" / "estate-audit-custody.py",
                runner=runner,
                volume_probe=lambda mount: identities[str(mount)],
                plan_discoverer=lambda _root, _limit, _deadline: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "rail-working-payload-mismatch"
    )
    assert [request.mode for request in runner.requests] == [
        "check",
        "apply",
        "apply",
    ]
    assert not any(path.name == "paired-receipts" for path in tmp_path.rglob("*"))


def test_interrupted_pair_write_leaves_only_nonterminal_prepared_evidence(
    tmp_path: Path,
) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    def interrupt_after_first(_target, index: int) -> None:
        if index == 0:
            raise RuntimeError("fixture-crash")

    with pytest.raises(RuntimeError, match="fixture-crash"):
        run_paired_custody(
            repository_root=repository,
            limen_root=limen_root,
            registry_path=registry,
            single_rail_script=repository / "scripts" / "estate-audit-custody.py",
            runner=runner,
            volume_probe=lambda mount: identities[str(mount)],
            plan_discoverer=lambda _root, _limit, _deadline: plan,
            lease_factory=lease.hold,
            require_mount=False,
            prepared_write_hook=interrupt_after_first,
        )

    registered = load_target_registry(registry, repository_root=repository)
    receipt_paths = [
        target.custody_root / "paired-receipts" / f"{plan.plan_sha256}.json" for target in registered.targets
    ]
    assert receipt_paths[0].exists()
    assert not receipt_paths[1].exists()
    unilateral = json.loads(receipt_paths[0].read_text(encoding="utf-8"))
    assert unilateral["status"] == "prepared"
    assert unilateral["requires_peer_match"] is True
    assert "restoration_passed" not in unilateral
    assert "copy_count" not in unilateral

    recovered = run_paired_custody(
        repository_root=repository,
        limen_root=limen_root,
        registry_path=registry,
        single_rail_script=repository / "scripts" / "estate-audit-custody.py",
        runner=runner,
        volume_probe=lambda mount: identities[str(mount)],
        plan_discoverer=lambda _root, _limit, _deadline: plan,
        lease_factory=lease.hold,
        require_mount=False,
    )
    fixed_point = run_paired_custody(
        repository_root=repository,
        limen_root=limen_root,
        registry_path=registry,
        single_rail_script=repository / "scripts" / "estate-audit-custody.py",
        runner=runner,
        volume_probe=lambda mount: identities[str(mount)],
        plan_discoverer=lambda _root, _limit, _deadline: plan,
        lease_factory=lease.hold,
        require_mount=False,
    )
    assert recovered["status"] == fixed_point["status"] == "restored"
    assert recovered["changed"] is True
    assert fixed_point["changed"] is False
    assert receipt_paths[0].read_bytes() == receipt_paths[1].read_bytes()


def test_both_restores_and_second_complete_pass_are_byte_idempotent(
    tmp_path: Path,
) -> None:
    plan = make_plan(tmp_path, root_count=5)
    repository, registry, identities = make_registration(tmp_path)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    def execute() -> dict[str, Any]:
        return run_paired_custody(
            repository_root=repository,
            limen_root=limen_root,
            registry_path=registry,
            single_rail_script=repository / "scripts" / "estate-audit-custody.py",
            max_roots=100,
            max_seconds=60,
            runner=runner,
            volume_probe=lambda mount: identities[str(mount)],
            plan_discoverer=lambda _root, _limit, _deadline: plan,
            lease_factory=lease.hold,
            require_mount=False,
        )

    first = execute()
    registered = load_target_registry(registry, repository_root=repository)
    receipt_paths = [
        target.custody_root / "paired-receipts" / f"{plan.plan_sha256}.json" for target in registered.targets
    ]
    first_bytes = [path.read_bytes() for path in receipt_paths]
    second = execute()
    second_bytes = [path.read_bytes() for path in receipt_paths]

    assert first["status"] == second["status"] == "restored"
    assert first["changed"] is True
    assert second["changed"] is False
    assert first_bytes[0] == first_bytes[1] == second_bytes[0] == second_bytes[1]
    private = json.loads(first_bytes[0])
    assert private["schema"] == PRIVATE_RECEIPT_SCHEMA
    assert private["status"] == "prepared"
    assert private["requires_peer_match"] is True
    assert "restoration_passed" not in private
    assert "copy_count" not in private
    assert all(target["rail_restoration_passed"] is True for target in private["targets"].values())
    assert private["independent_physical_devices"] is True
    assert private["source_retired"] is False
    assert private["reclaim_performed"] is False
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in receipt_paths)
    assert [request.mode for request in runner.requests] == [
        "check",
        "apply",
        "apply",
        "check",
        "apply",
        "apply",
    ]
    assert lease.calls == lease.entries == lease.exits == 2


def test_repaired_rail_evidence_appends_one_content_addressed_pair(
    tmp_path: Path,
) -> None:
    plan = make_plan(tmp_path)
    repository, registry, identities = make_registration(tmp_path)
    runner = FixtureRail(plan)
    lease = LeaseCounter()
    limen_root = tmp_path / "limen-root"
    limen_root.mkdir()

    def execute() -> dict[str, Any]:
        return run_paired_custody(
            repository_root=repository,
            limen_root=limen_root,
            registry_path=registry,
            single_rail_script=repository / "scripts" / "estate-audit-custody.py",
            runner=runner,
            volume_probe=lambda mount: identities[str(mount)],
            plan_discoverer=lambda _root, _limit, _deadline: plan,
            lease_factory=lease.hold,
            require_mount=False,
        )

    first = execute()
    registered = load_target_registry(registry, repository_root=repository)
    legacy_paths = [
        target.custody_root / "paired-receipts" / f"{plan.plan_sha256}.json" for target in registered.targets
    ]
    legacy_bytes = [path.read_bytes() for path in legacy_paths]

    runner.content_markers = {"archive4t": "5", "t7recovery": "6"}
    repaired = execute()
    repaired_paths = [
        target.custody_root / "paired-receipts" / f"{plan.plan_sha256}.{repaired['paired_receipt_sha256']}.json"
        for target in registered.targets
    ]
    repaired_bytes = [path.read_bytes() for path in repaired_paths]
    fixed_point = execute()

    assert first["changed"] is True
    assert repaired["changed"] is True
    assert fixed_point["changed"] is False
    assert [path.read_bytes() for path in legacy_paths] == legacy_bytes
    assert repaired_bytes[0] == repaired_bytes[1]
    assert all(path.exists() for path in repaired_paths)
    assert [
        sorted(path.name for path in (target.custody_root / "paired-receipts").iterdir())
        for target in registered.targets
    ] == [
        sorted([legacy_paths[0].name, repaired_paths[0].name]),
        sorted([legacy_paths[1].name, repaired_paths[1].name]),
    ]


@pytest.mark.parametrize(
    ("stream", "limit_name", "expected"),
    [
        ("stdout", "MAX_CHILD_STDOUT_BYTES", "single-rail-check-stdout-limit"),
        ("stderr", "MAX_CHILD_STDERR_BYTES", "single-rail-check-stderr-limit"),
    ],
)
def test_single_rail_output_is_rejected_at_limit_plus_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stream: str,
    limit_name: str,
    expected: str,
) -> None:
    monkeypatch.setattr(paired_module, limit_name, 64)
    limit = 64
    script = tmp_path / "noisy-child.py"
    descriptor = 1 if stream == "stdout" else 2
    prefix = b"" if stream == "stdout" else b"{}"
    script.write_text(
        f"import os\nos.write(1, {prefix!r})\nos.write({descriptor}, b'x' * ({limit} + 1))\n",
        encoding="utf-8",
    )
    request = RailRequest(
        mode="check",
        limen_root=tmp_path,
        max_roots=1,
        max_seconds=5,
    )

    assert error_code(lambda: invoke_single_rail(script, request)) == expected


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        ("output", "single-rail-check-stdout-limit"),
        ("timeout", "single-rail-check-unavailable"),
    ],
)
def test_single_rail_failure_reaps_term_ignoring_descendant_group(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure: str,
    expected: str,
) -> None:
    monkeypatch.setattr(paired_module, "MAX_CHILD_STDOUT_BYTES", 64)
    pid_path = tmp_path / "descendant.pid"
    script = tmp_path / "process-group-child.py"
    output = "os.write(1, b'x' * 65)" if failure == "output" else "None"
    script.write_text(
        "\n".join(
            [
                "import os",
                "import signal",
                "import subprocess",
                "import sys",
                "import time",
                "from pathlib import Path",
                "child = subprocess.Popen([",
                "    sys.executable,",
                "    '-c',",
                "    'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)',",
                "])",
                f"Path({str(pid_path)!r}).write_text(str(child.pid), encoding='utf-8')",
                output,
                "time.sleep(60)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    request = RailRequest(
        mode="check",
        limen_root=tmp_path,
        max_roots=1,
        max_seconds=5,
        deadline=(paired_module.time.monotonic() + 0.5 if failure == "timeout" else None),
    )

    assert error_code(lambda: invoke_single_rail(script, request)) == expected
    descendant_pid = int(pid_path.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(descendant_pid, 0)


def test_receipt_directory_parent_is_fsynced_after_mkdir_and_chmod(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    custody_root = tmp_path / "custody"
    custody_root.mkdir()
    events: list[str] = []
    real_open = os.open
    real_mkdir = os.mkdir
    real_fchmod = os.fchmod
    real_fsync = os.fsync

    def tracked_open(path, *args, **kwargs):
        events.append(f"open:{path}")
        return real_open(path, *args, **kwargs)

    def tracked_mkdir(path, *args, **kwargs):
        events.append(f"mkdir:{path}")
        return real_mkdir(path, *args, **kwargs)

    def tracked_fchmod(descriptor, mode):
        events.append("fchmod")
        return real_fchmod(descriptor, mode)

    def tracked_fsync(descriptor):
        events.append("fsync")
        return real_fsync(descriptor)

    monkeypatch.setattr(paired_module.os, "open", tracked_open)
    monkeypatch.setattr(paired_module.os, "mkdir", tracked_mkdir)
    monkeypatch.setattr(paired_module.os, "fchmod", tracked_fchmod)
    monkeypatch.setattr(paired_module.os, "fsync", tracked_fsync)
    directory = paired_module._open_receipt_directory(custody_root)
    os.close(directory)

    assert events[:5] == [
        f"open:{custody_root}",
        "mkdir:paired-receipts",
        "open:paired-receipts",
        "fchmod",
        "fsync",
    ]


def test_frozen_inventory_change_implicates_paired_gate() -> None:
    repository = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        [
            sys.executable,
            str(repository / "scripts" / "verify.py"),
            "--explain",
            "docs/storage-evacuation-inventory-20260727.json",
        ],
        cwd=repository,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "estate-audit-paired-custody-test" in result.stdout.splitlines()


def test_fleet_entrypoint_redacts_missing_dependencies(tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    copied = scripts / "estate-audit-paired-custody.py"
    copied.write_bytes((repository / "scripts" / "estate-audit-paired-custody.py").read_bytes())
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(copied), "--apply", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 4
    payload = json.loads(result.stdout)
    assert payload == {
        "schema": PROJECTION_SCHEMA,
        "status": "blocked",
        "error": "dependency-unavailable",
    }
    assert str(tmp_path) not in json.dumps(payload, sort_keys=True)


def test_projection_is_path_free_and_no_arca_invocation_exists(tmp_path: Path) -> None:
    projection, runner, _lease, _repository, _registry = run_fixture(tmp_path)
    encoded = json.dumps(projection, sort_keys=True)

    assert projection["schema"] == PROJECTION_SCHEMA
    assert projection["target_refs"] == ["archive4t", "t7recovery"]
    assert projection["copy_count"] == 2
    assert projection["restoration_passed"] is True
    assert projection["source_retired"] is False
    assert projection["reclaim_performed"] is False
    assert str(tmp_path) not in encoded
    assert "/Volumes/" not in encoded
    assert "/dev/disk" not in encoded
    assert "AAAAAAAA-AAAA" not in encoded
    assert "BBBBBBBB-BBBB" not in encoded
    assert "credential" not in encoded.lower()
    assert "secret" not in encoded.lower()
    assert "arca" not in encoded.lower()
    assert all("arca" not in repr(request).lower() for request in runner.requests)
