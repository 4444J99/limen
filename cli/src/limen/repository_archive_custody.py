"""Exact-allowlist, encrypted filesystem custody. This module cannot retire sources.

Broken Git markers are preservable payloads, never proof of Git reconstruction.
Private manifests and archive names leave encrypted scratch only as ARCA ciphertext.
"""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import shutil
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Any

from limen.agent_state.crypto import _OPENSSL_DECRYPT, _OPENSSL_ENCRYPT, keychain_key
from limen.personal_custody import _diskutil_volume_identity, _inventory_volume
from limen.repository_retirement import RetirementError, Runtime, atomic_json, digest, identity, lock, records
from limen.repository_retirement_custody import logical

SCHEMA = "limen.repository_archive_custody.v1"


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()


def allowlist(path: Path) -> tuple[str, list[dict[str, Any]]]:
    raw = path.read_bytes()
    value = json.loads(raw)
    entries = value.get("repositories")
    if not isinstance(entries, list) or not entries or len(entries) > 500:
        raise RetirementError("archive-exact-allowlist-required")
    seen: set[str] = set()
    for entry in entries:
        root = Path(entry["path"])
        if not root.is_absolute() or str(root) != os.path.normpath(root) or str(root) in seen:
            raise RetirementError("archive-allowlist-path-invalid")
        seen.add(str(root))
        for name in ("gitdir", "common"):
            store = entry.get(name)
            if store and (not Path(store).is_absolute() or store != os.path.normpath(store)):
                raise RetirementError("archive-allowlist-store-invalid")
    if any(Path(a) in Path(b).parents for a in seen for b in seen if a != b):
        raise RetirementError("archive-overlapping-roots")
    return hashlib.sha256(raw).hexdigest(), entries


class ArchiveCustody:
    def __init__(
        self,
        runtime: Runtime,
        scratch: Path,
        *,
        key_provider=keychain_key,
        volume_probe=_diskutil_volume_identity,
        encrypted_probe=None,
    ):
        self.runtime, self.scratch = runtime, scratch
        self.key_provider, self.volume_probe = key_provider, volume_probe
        self.encrypted_probe = encrypted_probe or self._encrypted
        self.diagnostics: list[dict[str, Any]] = []

    def command(self, argv: list[str], *, key: str | None = None):
        result = self.runtime.run(argv, timeout=self.runtime.check(), environment={"ARCA_KEY": key} if key else None)
        if result.returncode:
            self.diagnostics.append({"argv": argv, "exit": result.returncode, "stderr": result.stderr[:3000]})
            raise RetirementError(f"archive-{Path(argv[0]).name}-failed")
        return result

    def _encrypted(self, path: Path) -> bool:
        result = self.runtime.run(["/bin/df", "-P", str(path)])
        if result.returncode or len(result.stdout.splitlines()) != 2:
            return False
        device = result.stdout.splitlines()[1].split()[0]
        result = self.runtime.run(["/usr/sbin/diskutil", "info", "-plist", device])
        if result.returncode:
            return False
        value = plistlib.loads(result.stdout.encode())
        return value.get("FileVault") is True or value.get("Encrypted") is True

    def targets(self, config: dict[str, Any]) -> list[Path]:
        raw = Path(config["inventory"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != config["inventory_sha256"]:
            raise RetirementError("custody-registration-digest-mismatch")
        inventory = json.loads(raw)
        if inventory.get("schema") != "limen.storage_evacuation_inventory.v1":
            raise RetirementError("custody-registration-schema-mismatch")
        roots, volumes = [], []
        for name, field in (("Archive4T", "archive_root"), ("T7Recovery", "recovery_root")):
            root = Path(config[field])
            if root.resolve(strict=True) != root or not os.path.ismount(root):
                raise RetirementError("archive-custody-device-not-mounted")
            actual = self.volume_probe(root)
            _inventory_volume(inventory, name, actual)
            roots.append(root)
            volumes.append(asdict(actual))
        if volumes[0]["physical_device"] == volumes[1]["physical_device"]:
            raise RetirementError("custody-targets-share-physical-device")
        self.volumes = volumes
        return roots

    def sources(self, entry: dict[str, Any]) -> list[Path]:
        root = Path(entry["path"])
        identity(root)
        for current, dirs, _files in os.walk(root, followlinks=False):
            self.runtime.check()
            if Path(current) != root and ".git" in dirs:
                raise RetirementError("archive-unlisted-nested-repository")
            if Path(current) != root and (Path(current) / ".git").is_file():
                raise RetirementError("archive-unlisted-nested-repository")
            if ".git" in dirs:
                dirs.remove(".git")
        sources = [root]
        marker = root / ".git"
        if marker.is_symlink():
            raise RetirementError("archive-unlisted-git-marker-symlink")
        if marker.is_dir() and (marker / "commondir").exists():
            raise RetirementError("archive-external-common-store-requires-pointer-scope")
        for store in {marker, Path(entry.get("common") or marker)}:
            alternate = store / "objects/info/alternates"
            if alternate.exists() and alternate.read_bytes().strip():
                raise RetirementError("archive-external-object-alternate")
        if marker.is_file():
            text = marker.read_text().strip()
            if not text.startswith("gitdir: "):
                raise RetirementError("archive-git-marker-invalid")
            target = (root / text[8:]).resolve()
            if str(target) != entry.get("gitdir"):
                raise RetirementError("archive-git-marker-manifest-mismatch")
        for field in ("gitdir", "common"):
            path = Path(entry[field]) if entry.get(field) else None
            if path and path.exists() and path != root and root not in path.parents:
                identity(path)
                if not any(p == path or p in path.parents for p in sources):
                    sources = [p for p in sources if path not in p.parents]
                    sources.append(path)
        return sources

    def content(self, source: Path) -> list[dict[str, Any]]:
        values = logical(records(self.runtime, source))
        if any(str(v.get(k, "")).startswith("unavailable:") for v in values for k in ("xattrs_sha256", "acl_sha256")):
            raise RetirementError("archive-native-metadata-unavailable")
        return values

    def git_signature(self, root: Path) -> dict[str, Any]:
        # A pointer's original external administrative path must never be followed
        # from a restoration probe. Those roots have filesystem-only coverage.
        if not (root / ".git").is_dir():
            return {"coverage": "filesystem-only", "reason": "git-pointer-or-store-unavailable"}
        output = {}
        for name, args in (
            ("head", ["rev-parse", "HEAD"]),
            ("refs", ["for-each-ref", "--format=%(refname) %(objectname)"]),
            ("objects", ["cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype) %(objectsize)"]),
            ("index", ["ls-files", "--stage", "-z"]),
            ("integrity", ["fsck", "--full", "--no-reflogs", "--unreachable"]),
        ):
            result = self.runtime.git(root, *args)
            if result.returncode:
                self.diagnostics.append(
                    {"argv": ["git", "-C", str(root), *args], "exit": result.returncode, "stderr": result.stderr[:3000]}
                )
                raise RetirementError(f"archive-git-{name}-failed")
            output[name] = digest(sorted(result.stdout.splitlines()))
        return {"coverage": "git-and-filesystem", **output}

    def preview(self, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for entry in entries:
            row: dict[str, Any] = {"candidate": digest(entry["path"])[:16]}
            try:
                sources = self.sources(entry)
                row.update(
                    status="preservable",
                    source_count=len(sources),
                    git_coverage=self.git_signature(sources[0])["coverage"],
                )
            except (RetirementError, OSError, ValueError) as exc:
                row.update(
                    status="retained",
                    reason=str(exc) if isinstance(exc, RetirementError) else "archive-inspection-unavailable",
                )
            rows.append(row)
        return rows

    def scratch_ready(self) -> None:
        self.scratch.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.scratch.resolve() != self.scratch or self.scratch.stat().st_mode & 0o077:
            raise RetirementError("archive-scratch-not-private")
        if not self.encrypted_probe(self.scratch):
            raise RetirementError("archive-scratch-encryption-unverified")

    def seal(self, source: Path, destination: Path, key: str) -> None:
        self.command([*_OPENSSL_ENCRYPT, "-in", str(source), "-out", str(destination)], key=key)
        destination.chmod(0o600)

    def unseal(self, source: Path, destination: Path, key: str) -> None:
        self.command([*_OPENSSL_DECRYPT, "-in", str(source), "-out", str(destination)], key=key)
        destination.chmod(0o600)

    def verify(self, locator: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        self.scratch_ready()
        targets = self.targets(config)
        if locator.get("schema") != SCHEMA or locator.get("volumes") != self.volumes:
            raise RetirementError("archive-custody-volume-identity-drift")
        archive_id = locator.get("archive_digest", "")
        if not re.fullmatch(r"[0-9a-f]{64}", archive_id):
            raise RetirementError("archive-digest-invalid")
        key = self.key_provider()
        proofs: list[dict[str, Any]] = []
        for target in targets:
            with tempfile.TemporaryDirectory(dir=self.scratch, prefix="restore-") as temporary:
                temp = Path(temporary)
                base = target / "limen-private" / "repository-archives" / archive_id
                if base.resolve(strict=True) != base:
                    raise RetirementError("archive-custody-symlink")
                for name, expected in locator["ciphertext"].items():
                    if not re.fullmatch(r"(?:manifest|payload-[0-9]{3})\.enc", name):
                        raise RetirementError("archive-ciphertext-name-invalid")
                    if file_digest(base / name) != expected:
                        raise RetirementError("archive-ciphertext-mismatch")
                self.unseal(base / "manifest.enc", temp / "manifest.json", key)
                manifest = json.loads((temp / "manifest.json").read_text())
                if digest(manifest) != archive_id:
                    raise RetirementError("archive-manifest-digest-mismatch")
                source_digest = digest(
                    {
                        "sources": [{k: v for k, v in s.items() if k != "archive_sha256"} for s in manifest["sources"]],
                        "git": manifest["git"],
                        "allowlist_sha256": manifest["allowlist_sha256"],
                    }
                )
                if source_digest != locator["source_digest"]:
                    raise RetirementError("archive-source-binding-mismatch")
                for i, source in enumerate(manifest["sources"]):
                    archive = temp / f"payload-{i:03d}.tar"
                    self.unseal(base / f"payload-{i:03d}.enc", archive, key)
                    if file_digest(archive) != source["archive_sha256"]:
                        raise RetirementError("archive-plaintext-digest-mismatch")
                    restored = temp / f"root-{i:03d}"
                    restored.mkdir(mode=0o700)
                    self.command(
                        [
                            "/usr/bin/tar",
                            "--acls",
                            "--xattrs",
                            "--mac-metadata",
                            "-xf",
                            str(archive),
                            "-C",
                            str(restored),
                        ]
                    )
                    if self.content(restored) != source["records"]:
                        raise RetirementError("archive-restored-metadata-mismatch")
                    if i == 0 and self.git_signature(restored) != manifest["git"]:
                        raise RetirementError("archive-restored-git-mismatch")
                proofs.append(
                    {
                        "physical_device": self.volumes[len(proofs)]["physical_device"],
                        "content_sha256": archive_id,
                        "passed": True,
                    }
                )
        return {
            "schema": SCHEMA,
            "candidate": locator["candidate"],
            "restorations": proofs,
            "git_coverage": manifest["git"]["coverage"],
            "retirement_authorized": False,
        }

    def capture(self, entry: dict[str, Any], binding: str, config: dict[str, Any], state: Path) -> dict[str, Any]:
        self.scratch_ready()
        targets = self.targets(config)
        sources = self.sources(entry)
        if any(p == t or p in t.parents or t in p.parents for p in sources for t in targets):
            raise RetirementError("archive-custody-overlaps-source")
        candidate = digest(entry["path"])[:16]
        previous = state / f"{candidate}.json"
        with lock(state / f"{candidate}.lock"):
            expected = [{"identity": identity(p), "records": self.content(p)} for p in sources]
            git = self.git_signature(sources[0])
            source_digest = digest({"sources": expected, "git": git, "allowlist_sha256": binding})
            if previous.exists():
                locator = json.loads(previous.read_text())
                if locator.get("source_digest") == source_digest:
                    return {**self.verify(locator, config), "changed": False}
            key = self.key_provider()
            with tempfile.TemporaryDirectory(dir=self.scratch, prefix="capture-") as temporary:
                temp = Path(temporary)
                for i, (source, value) in enumerate(zip(sources, expected, strict=True)):
                    archive = temp / f"payload-{i:03d}.tar"
                    self.command(
                        [
                            "/usr/bin/tar",
                            "--acls",
                            "--xattrs",
                            "--mac-metadata",
                            "-cf",
                            str(archive),
                            "-C",
                            str(source),
                            ".",
                        ]
                    )
                    value["archive_sha256"] = file_digest(archive)
                manifest = {"schema": SCHEMA, "allowlist_sha256": binding, "sources": expected, "git": git}
                archive_id = digest(manifest)
                atomic_json(temp / "manifest.json", manifest)
                names = ["manifest", *(f"payload-{i:03d}" for i in range(len(sources)))]
                for name in names:
                    self.seal(temp / (name + (".json" if name == "manifest" else ".tar")), temp / f"{name}.enc", key)
                hashes = {f"{name}.enc": file_digest(temp / f"{name}.enc") for name in names}
                locator = {
                    "schema": SCHEMA,
                    "candidate": candidate,
                    "source_digest": source_digest,
                    "archive_digest": archive_id,
                    "ciphertext": hashes,
                    "volumes": self.volumes,
                }
                for target in targets:
                    base = target / "limen-private" / "repository-archives" / archive_id
                    base.mkdir(parents=True, exist_ok=True, mode=0o700)
                    if base.resolve() != base:
                        raise RetirementError("archive-custody-symlink")
                    for name, h in hashes.items():
                        dest = base / name
                        if dest.exists():
                            if file_digest(dest) != h:
                                raise RetirementError("archive-existing-ciphertext-mismatch")
                        else:
                            shutil.copyfile(temp / name, dest)
                            dest.chmod(0o600)
                    atomic_json(base / "locator.json", locator)
                result = self.verify(locator, config)
                current = [{"identity": identity(p), "records": self.content(p)} for p in sources]
                if (
                    digest({"sources": current, "git": self.git_signature(sources[0]), "allowlist_sha256": binding})
                    != source_digest
                ):
                    raise RetirementError("archive-source-drift")
                atomic_json(previous, locator)
                return {**result, "changed": True}


def default_config(root: Path) -> dict[str, Any]:
    registry = json.loads((root / "institutio/governance/estate-audit-custody-targets.json").read_text())
    inventory = root / registry["inventory"]
    return {
        "inventory": str(inventory),
        "inventory_sha256": registry["inventory_sha256"],
        "archive_root": "/Volumes/Archive4T",
        "recovery_root": "/Volumes/T7Recovery",
    }


class EnvelopePairCustody:
    """ARCA backend for the existing keeper-authorized retirement runner.

    The runner still owns remote identity, admission, dependencies, and acceptance.
    Only its private FileVault journal holds plaintext source/record mappings.
    """

    def __init__(self, config: dict[str, Any], runtime: Runtime):
        self.config, self.runtime = config, runtime
        data = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))
        self.state = data / "limen/repository-archives/retirement-backend"
        self.engine = ArchiveCustody(runtime, data / "limen/repository-archives/scratch")

    def capture(self, sources: list[Path], *, journal_root: Path) -> dict[str, Any]:
        root = sources[0]
        entry = {"path": str(root), "gitdir": str(root / ".git"), "common": str(sources[-1])}
        if (root / ".git").is_file():
            entry["gitdir"] = str((root / (root / ".git").read_text().strip()[8:]).resolve())
        if self.engine.sources(entry) != sources:
            raise RetirementError("archive-retirement-source-scope-mismatch")
        self.engine.capture(entry, digest([str(p) for p in sources]), self.config, self.state)
        locator = json.loads((self.state / f"{digest(str(root))[:16]}.json").read_text())
        values = [
            {
                "identity": identity(p),
                "key": digest(identity(p))[:24],
                "records": [asdict(v) for v in records(self.runtime, p)],
            }
            for p in sources
        ]
        proof = {
            "schema": "limen.repository_custody.v1",
            "sources": values,
            "volumes": self.engine.volumes,
            "journal_root": str(journal_root),
            "envelope_locator": locator,
            "git": self.engine.git_signature(root),
            "archive_binding": digest([str(p) for p in sources]),
        }
        proof["digest"] = digest(proof)
        self.verify(proof)
        return proof

    def verify_source(self, source: Path, expected: dict[str, Any]) -> None:
        if identity(source) != expected["identity"] or self.engine.content(source) != logical(expected["records"]):
            raise RetirementError("custody-source-drift")

    def verify(self, proof: dict[str, Any], *, restore: bool = True) -> None:
        if digest({k: v for k, v in proof.items() if k != "digest"}) != proof["digest"]:
            raise RetirementError("archive-retirement-proof-drift")
        expected = digest(
            {
                "sources": [{"identity": s["identity"], "records": logical(s["records"])} for s in proof["sources"]],
                "git": proof["git"],
                "allowlist_sha256": proof["archive_binding"],
            }
        )
        if expected != proof["envelope_locator"]["source_digest"]:
            raise RetirementError("archive-retirement-source-proof-mismatch")
        # Even the retirement runner's cheaper readback request does a real
        # isolated restoration; ciphertext hashes alone cannot authorize purge.
        self.engine.verify(proof["envelope_locator"], self.config)
