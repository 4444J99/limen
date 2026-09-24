#!/usr/bin/env python3
"""Build incremental, encrypted, per-file ARCA objects and an encrypted catalog.

Names, relative paths, metadata, and plaintext digests occur only inside the encrypted
catalog. Each regular file is independently encrypted with private-vault's pinned GPG
recipient; unchanged files reuse ciphertext referenced by the previous encrypted catalog.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIVATE_VAULT = ROOT / "scripts" / "private-vault.py"
SPEC = importlib.util.spec_from_file_location("limen_private_vault", PRIVATE_VAULT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("private-vault encryption module unavailable")
PRIVATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRIVATE)
OBJECT_PART_BYTES = int(os.environ.get("ARCA_OBJECT_PART_BYTES", str(1024**3)))


class ObjectError(RuntimeError):
    pass


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def inventory(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for base, dirs, files in os.walk(root, topdown=True, followlinks=False):
        base_path = Path(base)
        kept: list[str] = []
        for name in sorted(dirs):
            path = base_path / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                rows.append({"path": rel, "type": "symlink", "target": os.readlink(path), "mode": stat.S_IMODE(info.st_mode)})
            else:
                kept.append(name)
                rows.append({"path": rel, "type": "directory", "mode": stat.S_IMODE(info.st_mode)})
        dirs[:] = kept
        for name in sorted(files):
            path = base_path / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                rows.append({"path": rel, "type": "symlink", "target": os.readlink(path), "mode": mode})
            elif stat.S_ISREG(info.st_mode):
                rows.append({"path": rel, "type": "file", "mode": mode, "sha256": digest_file(path)})
            else:
                raise ObjectError(f"unsupported filesystem object at {rel!r}; source retained")
    return sorted(rows, key=lambda row: str(row["path"]))


def _decrypt_catalog(path: Path, destination: Path) -> dict[str, object]:
    PRIVATE._decrypt_file(path, destination)
    try:
        value = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ObjectError("previous encrypted catalog is unreadable; no objects changed") from exc
    if not isinstance(value, dict) or value.get("schema") not in {"arca-file-catalog-v1", "arca-file-catalog-v2"} or not isinstance(value.get("entries"), list):
        raise ObjectError("previous catalog schema is invalid; no objects changed")
    return value


def build(source: Path, out: Path, *, previous: Path | None = None) -> dict[str, object]:
    if OBJECT_PART_BYTES <= 0 or OBJECT_PART_BYTES >= 2 * 1024**3:
        raise ObjectError("ARCA_OBJECT_PART_BYTES must be positive and below GitHub's 2-GiB asset limit")
    if source.is_symlink() or not source.is_dir():
        raise ObjectError("source must be a real directory")
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if out.resolve() == source.resolve() or source.resolve() in out.resolve().parents:
        raise ObjectError("object output must be outside the source tree")
    current = inventory(source)
    old_by_path: dict[str, dict[str, object]] = {}
    old_root: Path | None = None
    old_catalog: dict[str, object] | None = None
    if previous is not None:
        with tempfile.TemporaryDirectory(prefix="arca-catalog-") as temporary:
            old_catalog = _decrypt_catalog(previous, Path(temporary) / "catalog.json")
        old_by_path = {str(row["path"]): row for row in old_catalog["entries"] if isinstance(row, dict) and "path" in row}
        old_root = previous.parent

    entries: list[dict[str, object]] = []
    staged: list[tuple[Path, Path]] = []
    reused_count = 0
    for row in current:
        entry = dict(row)
        if row["type"] == "file":
            old = old_by_path.get(str(row["path"]))
            reused = False
            if old and old.get("type") == "file" and old.get("sha256") == row.get("sha256") and old.get("mode") == row.get("mode") and old_root:
                old_parts = old.get("objects")
                if not isinstance(old_parts, list):
                    old_parts = [{"object_id": old.get("object_id"), "ciphertext_sha256": old.get("ciphertext_sha256") }]
                candidates = [old_root / "objects" / f"{part.get('object_id')}.gpg" for part in old_parts if isinstance(part, dict)]
                if len(candidates) == len(old_parts) and candidates and all(
                    candidate.is_file() and not candidate.is_symlink() and digest_file(candidate) == part.get("ciphertext_sha256")
                    for candidate, part in zip(candidates, old_parts, strict=True)
                ):
                    entry["objects"] = old_parts
                    entry["ciphertext_sha256"] = old.get("ciphertext_sha256")
                    if len(old_parts) == 1:
                        entry["object_id"] = old_parts[0]["object_id"]
                    for candidate, part in zip(candidates, old_parts, strict=True):
                        copied = out / "objects" / f"{part['object_id']}.gpg"
                        copied.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        if not copied.exists():
                            shutil.copyfile(candidate, copied)
                    reused = True
                    reused_count += 1
            if not reused:
                with tempfile.TemporaryDirectory(prefix="arca-encrypted-file-") as temporary_dir:
                    encrypted = Path(temporary_dir) / "cipher.gpg"
                    PRIVATE._encrypt_file(source / str(row["path"]), encrypted)
                    if not encrypted.is_file() or encrypted.stat().st_size == 0:
                        raise ObjectError("encryption produced an empty object; catalog was not published")
                    if digest_file(source / str(row["path"])) != row["sha256"]:
                        raise ObjectError("source changed during encryption; catalog was not published")
                    parts: list[dict[str, object]] = []
                    cipher_digest = hashlib.sha256()
                    with encrypted.open("rb") as stream:
                        while block := stream.read(OBJECT_PART_BYTES):
                            cipher_digest.update(block)
                            object_id = secrets.token_hex(24)
                            target = out / "objects" / f"{object_id}.gpg"
                            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                            partial = target.with_name(f".{target.name}.partial")
                            partial.write_bytes(block)
                            if partial.stat().st_size >= 2 * 1024**3:
                                partial.unlink(missing_ok=True)
                                raise ObjectError("encrypted object part exceeds GitHub's per-asset limit")
                            staged.append((partial, target))
                            parts.append({"object_id": object_id, "ciphertext_sha256": hashlib.sha256(block).hexdigest(), "ciphertext_bytes": len(block)})
                entry["objects"] = parts
                if len(parts) == 1:
                    entry["object_id"] = parts[0]["object_id"]
                entry["ciphertext_sha256"] = cipher_digest.hexdigest()
            entries.append(entry)
        else:
            entries.append(entry)

    # Publish objects first. The encrypted catalog is the commit point and cannot reference
    # incomplete writes. Existing random object names are never overwritten.
    for temporary, target in staged:
        if target.exists():
            raise ObjectError("random object identifier collision; catalog was not published")
        os.replace(temporary, target)
    catalog = {"schema": "arca-file-catalog-v2", "root_mode": stat.S_IMODE(source.stat().st_mode), "entries": entries}
    catalog_path = out / "catalog.gpg"
    if old_catalog == catalog:
        if previous is not None and previous.resolve() != catalog_path.resolve():
            temporary_cipher = out / ".catalog.gpg.partial"
            shutil.copyfile(previous, temporary_cipher)
            os.replace(temporary_cipher, catalog_path)
        state = "unchanged"
    else:
        with tempfile.TemporaryDirectory(prefix="arca-catalog-build-") as temporary:
            plaintext = Path(temporary) / "catalog.json"
            plaintext.write_text(json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            os.chmod(plaintext, 0o600)
            temp_cipher = out / ".catalog.gpg.partial"
            PRIVATE._encrypt_file(plaintext, temp_cipher)
            if not temp_cipher.is_file() or temp_cipher.stat().st_size == 0:
                raise ObjectError("catalog encryption failed; catalog was not published")
            os.replace(temp_cipher, catalog_path)
        state = "ready"
    return {"state": state, "files": sum(row["type"] == "file" for row in entries), "new_objects": len(staged), "reused_objects": reused_count, "catalog": str(catalog_path)}


def restore(catalog_path: Path, objects_root: Path, destination: Path) -> dict[str, object]:
    """Decrypt and atomically create a previously absent directory tree."""
    if destination.exists() or destination.is_symlink():
        raise ObjectError("restore destination already exists; refusing to overwrite")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".arca-restore-", dir=destination.parent) as temporary:
        base = Path(temporary)
        catalog_file = base / "catalog.json"
        catalog = _decrypt_catalog(catalog_path, catalog_file)
        entries = catalog["entries"]
        by_path: dict[str, dict[str, object]] = {}
        for raw in entries:
            if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
                raise ObjectError("catalog contains an invalid entry")
            rel = Path(str(raw["path"]))
            if rel.is_absolute() or not rel.parts or any(part in ("", ".", "..") for part in rel.parts) or "\\" in str(raw["path"]):
                raise ObjectError("catalog contains an unsafe relative path")
            normalized = rel.as_posix()
            if normalized in by_path:
                raise ObjectError("catalog contains duplicate paths")
            by_path[normalized] = raw
        for name, row in by_path.items():
            parts = Path(name).parts
            for index in range(1, len(parts)):
                parent_name = Path(*parts[:index]).as_posix()
                parent = by_path.get(parent_name)
                if parent and parent.get("type") != "directory":
                    raise ObjectError("catalog has a non-directory path ancestor")
        staging = base / "tree"
        staging.mkdir(mode=0o700)
        for name, row in sorted(by_path.items(), key=lambda pair: len(Path(pair[0]).parts)):
            target = staging / name
            if row.get("type") == "directory":
                target.mkdir(mode=0o700, parents=True, exist_ok=True)
            elif row.get("type") == "file":
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                parts = row.get("objects")
                if not isinstance(parts, list) or not parts:
                    object_id = row.get("object_id")
                    parts = [{"object_id": object_id, "ciphertext_sha256": row.get("ciphertext_sha256")}]
                with (base / "cipher.gpg").open("wb") as combined:
                    for part in parts:
                        if not isinstance(part, dict):
                            raise ObjectError("catalog contains an invalid object part")
                        object_id = part.get("object_id")
                        if not isinstance(object_id, str) or not re.fullmatch(r"[0-9a-f]{48}", object_id):
                            raise ObjectError("catalog contains an invalid object identifier")
                        cipher = objects_root / "objects" / f"{object_id}.gpg"
                        if cipher.is_symlink() or not cipher.is_file() or digest_file(cipher) != part.get("ciphertext_sha256"):
                            raise ObjectError("encrypted object is missing or failed integrity verification")
                        with cipher.open("rb") as fragment:
                            shutil.copyfileobj(fragment, combined, length=1024 * 1024)
                combined_cipher = base / "cipher.gpg"
                if digest_file(combined_cipher) != row.get("ciphertext_sha256"):
                    raise ObjectError("reassembled ciphertext failed integrity verification")
                PRIVATE._decrypt_file(combined_cipher, target)
                if digest_file(target) != row.get("sha256"):
                    raise ObjectError("decrypted object failed plaintext integrity verification")
                os.chmod(target, int(row.get("mode", 0o600)))
            elif row.get("type") != "symlink":
                raise ObjectError("catalog contains an unsupported filesystem object")
        for name, row in by_path.items():
            if row.get("type") == "symlink":
                target = staging / name
                target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                link_target = row.get("target")
                if not isinstance(link_target, str):
                    raise ObjectError("catalog contains an invalid symlink target")
                os.symlink(link_target, target)
        for name, row in by_path.items():
            if row.get("type") == "directory":
                os.chmod(staging / name, int(row.get("mode", 0o700)))
        os.chmod(staging, int(catalog.get("root_mode", 0o700)))
        os.replace(staging, destination)
    return {"state": "restored", "files": sum(row.get("type") == "file" for row in entries)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="source directory to build, or destination directory to restore into")
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--previous", type=Path, help="prior encrypted catalog; objects must sit beside it in objects/")
    parser.add_argument("--restore-catalog", type=Path)
    parser.add_argument("--objects-root", type=Path)
    args = parser.parse_args()
    try:
        if args.restore_catalog:
            if not args.objects_root or args.output is not None or args.previous:
                raise ObjectError("restore requires source as destination plus --restore-catalog and --objects-root")
            result = restore(args.restore_catalog, args.objects_root, args.source)
        else:
            if args.output is None or args.objects_root:
                raise ObjectError("build requires source and output directories")
            result = build(args.source, args.output, previous=args.previous)
        print(json.dumps(result, sort_keys=True))
    except (ObjectError, PRIVATE.VaultError, OSError) as exc:
        print(f"arca-file-objects: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
