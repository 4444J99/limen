from __future__ import annotations

import hashlib
import json
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from limen.estate_audit_custody import CustodyPlan, GeneratedRootRecord
from limen.estate_audit_paired_custody import (
    PRIVATE_RECEIPT_SCHEMA,
    PROJECTION_SCHEMA,
    PairedCustodyError,
    RailRequest,
    VolumeIdentity,
    blocked_projection,
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
    same_physical: bool = False,
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
    )
    recovery = VolumeIdentity(
        mount=str(recovery_mount),
        device="/dev/disk71s1",
        physical_device=archive.physical_device if same_physical else "/dev/disk71",
        volume_uuid=archive.volume_uuid if same_uuid else "BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB",
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
            },
            {
                "ref": "t7recovery",
                "inventory_name": "T7Recovery",
                "custody_root": str(recovery_mount / t7_target_relative),
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
        verify_content_mismatch: str | None = None,
    ) -> None:
        self.plan = plan
        self.fail = fail
        self.verify_content_mismatch = verify_content_mismatch
        self.requests: list[RailRequest] = []
        self.apply_counts = {ref: 0 for ref in ("archive4t", "t7recovery")}

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
        content_marker = "1" if ref == "archive4t" else "2"
        if request.mode == "verify-receipt" and ref == self.verify_content_mismatch:
            content_marker = "3"
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
        plan_discoverer=lambda _root, _limit: plan,
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
        "verify-receipt",
        "apply",
        "verify-receipt",
    ]
    assert lease.calls == lease.entries == lease.exits == 1
    source = (Path(__file__).parents[1] / "src" / "limen" / "estate_audit_paired_custody.py").read_text(
        encoding="utf-8"
    )
    assert "root_count=41" not in source
    assert "root_count=48" not in source
    assert "root_count=50" not in source


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
                plan_discoverer=lambda _root, _limit: plan,
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
                plan_discoverer=lambda _root, _limit: plan,
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
                plan_discoverer=lambda _root, _limit: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "registry-proof-status-invalid"
    )
    assert runner.requests == []


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"same_physical": True}, "targets-share-physical-device"),
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
                plan_discoverer=lambda _root, _limit: plan,
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
        **{**t7.__dict__, "device": "/dev/disk99s1"},
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
                plan_discoverer=lambda _root, _limit: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "t7recovery-identity-mismatch"
    )
    assert runner.requests == []

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
                plan_discoverer=lambda _root, _limit: plan,
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
                plan_discoverer=lambda _root, _limit: plan,
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
                plan_discoverer=lambda _root, _limit: overlapping,
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
                plan_discoverer=lambda _root, _limit: plan,
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
                plan_discoverer=lambda _root, _limit: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "paired-receipt-not-regular"
    )
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
            plan_discoverer=lambda _root, _limit: plan,
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
            ["check", "apply", "verify-receipt", "apply"],
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
            plan_discoverer=lambda _root, _limit: plan,
            lease_factory=lease.hold,
            require_mount=False,
        )
    ).startswith("fixture-")
    assert [request.mode for request in runner.requests] == expected_modes
    assert not any(path.name == "paired-receipts" for path in tmp_path.rglob("*"))


def test_apply_and_full_restore_must_identify_the_same_rail_receipt(tmp_path: Path) -> None:
    plan = make_plan(tmp_path)
    runner = FixtureRail(plan, verify_content_mismatch="archive4t")
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
                plan_discoverer=lambda _root, _limit: plan,
                lease_factory=lease.hold,
                require_mount=False,
            )
        )
        == "single-rail-receipt-mismatch"
    )
    assert [request.mode for request in runner.requests] == [
        "check",
        "apply",
        "verify-receipt",
    ]
    assert not any(path.name == "paired-receipts" for path in tmp_path.rglob("*"))


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
            plan_discoverer=lambda _root, _limit: plan,
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
    assert private["restoration_passed"] is True
    assert private["independent_physical_devices"] is True
    assert private["source_retired"] is False
    assert private["reclaim_performed"] is False
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in receipt_paths)
    assert [request.mode for request in runner.requests].count("verify-receipt") == 4
    assert lease.calls == lease.entries == lease.exits == 2


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
