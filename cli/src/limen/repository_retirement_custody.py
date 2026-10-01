"""Two registered-device, full-filesystem custody for exact repository batches."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path

from limen.personal_custody import ContentRecord, _diskutil_volume_identity, _inventory_volume
from limen.repository_retirement import RetirementError, Runtime, atomic_json, digest, identity, records

LOCAL_CUSTODY_POLICY = "registered-independent-devices.v2"


def logical(values) -> list[dict]:
    return [
        {
            key: value
            for key, value in (asdict(row) if isinstance(row, ContentRecord) else row).items()
            if key != "physical_bytes"
        }
        for row in values
    ]


class PairCustody:
    def __init__(
        self,
        config: dict,
        runtime: Runtime,
        *,
        volume_probe=_diskutil_volume_identity,
        copy_tree=None,
    ):
        self.config = config
        self.runtime = runtime
        self.volume_probe = volume_probe
        self.copy_tree = copy_tree or self._copy

    def targets(self, sources: list[Path]) -> list[Path]:
        inventory_bytes = Path(self.config["inventory"]).read_bytes()
        if hashlib.sha256(inventory_bytes).hexdigest() != self.config["inventory_sha256"]:
            raise RetirementError("custody-registration-digest-mismatch")
        inventory = json.loads(inventory_bytes)
        if inventory.get("schema") != "limen.storage_evacuation_inventory.v1":
            raise RetirementError("custody-registration-schema-mismatch")
        roots = [Path(self.config[name]).resolve(strict=True) for name in ("archive_root", "recovery_root")]
        volumes = []
        for name, root in zip(("Archive4T", "T7Recovery"), roots, strict=True):
            self.runtime.check()
            actual = self.volume_probe(root)
            _inventory_volume(inventory, name, actual)
            if any(root == source or source in root.parents or root in source.parents for source in sources):
                raise RetirementError("custody-overlaps-source")
            if root.is_symlink() or any(p.is_symlink() for p in root.parents):
                raise RetirementError("custody-target-symlink")
            volumes.append(actual)
        if volumes[0].physical_device == volumes[1].physical_device:
            raise RetirementError("custody-targets-share-physical-device")
        if any(
            Path(volume.mount) == source or Path(volume.mount) in source.parents
            for source in sources
            for volume in volumes
        ):
            raise RetirementError("custody-on-source-volume")
        self.volume_identities = [asdict(volume) for volume in volumes]
        return roots

    def _copy(self, source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        result = self.runtime.run(
            ["/usr/bin/ditto", "--rsrc", "--extattr", "--acl", "--noqtn", str(source), str(target)],
            timeout=self.runtime.check(),
        )
        if result.returncode:
            raise RetirementError("custody-copy-failed")

    def verify_source(self, source: Path, expected: dict) -> None:
        if identity(source) != expected["identity"] or logical(records(self.runtime, source)) != logical(
            expected["records"]
        ):
            raise RetirementError("custody-source-drift")

    def verify(self, proof: dict, *, restore: bool = True) -> None:
        if proof.get("policy") != LOCAL_CUSTODY_POLICY:
            raise RetirementError("custody-policy-recapture-required")
        sources = [Path(row["identity"]["path"]) for row in proof["sources"]]
        targets = self.targets(sources)
        if self.volume_identities != proof["volumes"]:
            raise RetirementError("custody-volume-identity-drift")
        for target in targets:
            for source in proof["sources"]:
                archived = target / "limen-private" / "repository-retirement" / proof["digest"] / source["key"]
                if archived.is_symlink() or any(p.is_symlink() for p in archived.parents):
                    raise RetirementError("custody-archive-path-unsafe")
                if logical(records(self.runtime, archived)) != logical(source["records"]):
                    raise RetirementError("custody-archive-content-mismatch")
                if restore:
                    probe = archived.parent / f".restore-{source['key']}-{os.getpid()}"
                    if probe.exists():
                        raise RetirementError("custody-restore-probe-already-exists")
                    try:
                        self.copy_tree(archived, probe)
                        if logical(records(self.runtime, probe)) != logical(source["records"]):
                            raise RetirementError("custody-restore-mismatch")
                    finally:
                        # Only our newly created disposable probe may be removed.
                        if probe.exists() and not probe.is_symlink():
                            shutil.rmtree(probe)
        self.runtime.check()

    def capture(self, sources: list[Path], *, journal_root: Path) -> dict:
        targets = self.targets(sources)
        values: list[dict] = []
        for source in sources:
            before = identity(source)
            content = records(self.runtime, source)
            values.append(
                {"identity": before, "key": digest(before)[:24], "records": [asdict(value) for value in content]}
            )
        proof: dict = {
            "schema": "limen.repository_custody.v1",
            "policy": LOCAL_CUSTODY_POLICY,
            "sources": values,
            "volumes": self.volume_identities,
            "journal_root": str(journal_root),
        }
        proof["digest"] = digest(proof)
        for target in targets:
            parent = target / "limen-private"
            parent.mkdir(exist_ok=True, mode=0o700)
            private = parent / "repository-retirement"
            private.mkdir(exist_ok=True, mode=0o700)
            if private.stat().st_mode & 0o077 or (private.parent.stat().st_mode & 0o077):
                raise RetirementError("custody-root-is-not-private")
            for source, value in zip(sources, values, strict=True):
                archived = private / proof["digest"] / value["key"]
                if archived.exists():
                    if logical(records(self.runtime, archived)) != logical(value["records"]):
                        if (archived.parent / "receipt.json").exists():
                            raise RetirementError("custody-existing-object-mismatch")
                        # Only an incomplete, unreceipted copy may resume. A
                        # previously verified immutable archive is never repaired
                        # by overwriting it from a potentially changed source.
                        self.copy_tree(source, archived)
                else:
                    self.copy_tree(source, archived)
                self.verify_source(source, value)
            atomic_json(private / proof["digest"] / "receipt.json", proof)
        self.verify(proof)
        for source, value in zip(sources, values, strict=True):
            self.verify_source(source, value)
        return proof
