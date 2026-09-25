#!/usr/bin/env python3
"""Build incremental, encrypted, per-file ARCA objects and an encrypted catalog.

Names, relative paths, metadata, and plaintext digests occur only inside the encrypted
catalog. Each regular file is independently encrypted with private-vault's pinned GPG
recipient; unchanged files reuse ciphertext referenced by the previous encrypted catalog.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import ctypes
import fcntl
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
OBJECT_PART_BYTES = int(os.environ.get("ARCA_OBJECT_PART_BYTES", str(32 * 1024**2)))
MAX_XATTR_BYTES = 8 * 1024**2


class ObjectError(RuntimeError):
    pass


def digest_file(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _native_xattr_names(path: Path) -> list[str]:
    if sys.platform != "darwin":
        return os.listxattr(path, follow_symlinks=False)
    library = ctypes.CDLL(None, use_errno=True)
    call = library.listxattr
    call.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_int]
    call.restype = ctypes.c_ssize_t
    encoded = os.fsencode(path)
    size = call(encoded, None, 0, 0x0001)
    if size < 0 or size > MAX_XATTR_BYTES:
        raise OSError(ctypes.get_errno(), "extended metadata names unavailable")
    if size == 0:
        return []
    buffer = ctypes.create_string_buffer(size)
    if call(encoded, buffer, size, 0x0001) != size:
        raise OSError(ctypes.get_errno(), "extended metadata names changed")
    raw = buffer.raw
    if not raw.endswith(b"\x00"):
        raise OSError("extended metadata names malformed")
    return [name.decode("utf-8") for name in raw[:-1].split(b"\x00")]


def _native_getxattr(path: Path, name: str) -> bytes:
    if sys.platform != "darwin":
        return os.getxattr(path, name, follow_symlinks=False)
    library = ctypes.CDLL(None, use_errno=True)
    call = library.getxattr
    call.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    call.restype = ctypes.c_ssize_t
    encoded = os.fsencode(path)
    key = name.encode("utf-8")
    size = call(encoded, key, None, 0, 0, 0x0001)
    if size < 0 or size > MAX_XATTR_BYTES:
        raise OSError(ctypes.get_errno(), "extended metadata value unavailable")
    buffer = ctypes.create_string_buffer(max(1, size))
    if call(encoded, key, buffer, size, 0, 0x0001) != size:
        raise OSError(ctypes.get_errno(), "extended metadata value changed")
    return buffer.raw[:size]


def _native_setxattr(path: Path, name: str, value: bytes) -> None:
    if sys.platform != "darwin":
        os.setxattr(path, name, value, follow_symlinks=False)
        return
    library = ctypes.CDLL(None, use_errno=True)
    call = library.setxattr
    call.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_uint32, ctypes.c_int]
    call.restype = ctypes.c_int
    buffer = ctypes.create_string_buffer(value, max(1, len(value)))
    if call(os.fsencode(path), name.encode("utf-8"), buffer, len(value), 0, 0x0001) != 0:
        raise OSError(ctypes.get_errno(), "extended metadata restoration failed")


def _xattrs(path: Path) -> list[dict[str, str]]:
    """Keep native extended metadata inside the encrypted catalog."""
    try:
        names = sorted(_native_xattr_names(path))
        result = []
        total = 0
        for name in names:
            value = _native_getxattr(path, name)
            total += len(value)
            if total > MAX_XATTR_BYTES:
                raise ObjectError("extended metadata exceeds the bounded catalog limit")
            result.append({"name": name, "value_b64": base64.b64encode(value).decode("ascii")})
        return result
    except (OSError, UnicodeError, AttributeError) as exc:
        raise ObjectError("extended metadata unavailable; source retained") from exc


def _apply_xattrs(path: Path, raw: object) -> None:
    if not isinstance(raw, list):
        raise ObjectError("encrypted catalog lacks extended metadata")
    total = 0
    seen: set[str] = set()
    for row in raw:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("name"), str)
            or not isinstance(row.get("value_b64"), str)
        ):
            raise ObjectError("encrypted catalog has invalid extended metadata")
        name = row["name"]
        if not name or name in seen or "\x00" in name:
            raise ObjectError("encrypted catalog has duplicate or invalid extended metadata")
        seen.add(name)
        try:
            value = base64.b64decode(row["value_b64"], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ObjectError("encrypted catalog has invalid extended metadata") from exc
        total += len(value)
        if total > MAX_XATTR_BYTES:
            raise ObjectError("extended metadata exceeds the bounded catalog limit")
        try:
            _native_setxattr(path, name, value)
        except (OSError, AttributeError) as exc:
            raise ObjectError("extended metadata restoration failed; destination unpublished") from exc


def inventory(root: Path) -> list[dict[str, object]]:
    def unreadable(_error: OSError) -> None:
        # os.walk otherwise silently omits unreadable/disappearing directories,
        # making an incomplete capture indistinguishable from an empty source.
        raise ObjectError("source traversal incomplete; source retained") from _error

    rows: list[dict[str, object]] = []
    for base, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=unreadable):
        base_path = Path(base)
        kept: list[str] = []
        for name in sorted(dirs):
            path = base_path / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                rows.append(
                    {
                        "path": rel,
                        "type": "symlink",
                        "target": os.readlink(path),
                        "mode": stat.S_IMODE(info.st_mode),
                        "xattrs": _xattrs(path),
                    }
                )
            else:
                kept.append(name)
                rows.append(
                    {"path": rel, "type": "directory", "mode": stat.S_IMODE(info.st_mode), "xattrs": _xattrs(path)}
                )
        dirs[:] = kept
        for name in sorted(files):
            path = base_path / name
            rel = path.relative_to(root).as_posix()
            info = path.lstat()
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                rows.append(
                    {"path": rel, "type": "symlink", "target": os.readlink(path), "mode": mode, "xattrs": _xattrs(path)}
                )
            elif stat.S_ISREG(info.st_mode):
                rows.append(
                    {"path": rel, "type": "file", "mode": mode, "sha256": digest_file(path), "xattrs": _xattrs(path)}
                )
            else:
                raise ObjectError(f"unsupported filesystem object at {rel!r}; source retained")
    return sorted(rows, key=lambda row: str(row["path"]))


def _decrypt_catalog(path: Path, destination: Path) -> dict[str, object]:
    PRIVATE._decrypt_file(path, destination)
    try:
        value = json.loads(destination.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ObjectError("previous encrypted catalog is unreadable; no objects changed") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema")
        not in {"arca-file-catalog-v1", "arca-file-catalog-v2", "arca-file-catalog-v3", "arca-file-catalog-v4"}
        or not isinstance(value.get("entries"), list)
    ):
        raise ObjectError("previous catalog schema is invalid; no objects changed")
    return value


def build(source: Path, out: Path, *, previous: Path | None = None) -> dict[str, object]:
    """Serialize one output capture and retain crash debris for investigation."""
    if out.is_symlink():
        raise ObjectError("object output cannot be a symlink")
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    lock_fd = os.open(out / ".capture.lock", os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(lock_fd, "w") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        object_dir = out / "objects"
        if object_dir.is_symlink():
            raise ObjectError("object directory cannot be a symlink")
        if (out / ".catalog.gpg.partial").exists() or (object_dir.is_dir() and any(object_dir.glob(".*.partial"))):
            raise ObjectError("incomplete prior capture requires investigation; catalog retained")
        staged: list[tuple[Path, Path]] = []
        try:
            return _build_locked(source, out, previous=previous, staged=staged)
        except BaseException:
            for partial, _target in staged:
                partial.unlink(missing_ok=True)
            (out / ".catalog.gpg.partial").unlink(missing_ok=True)
            raise


def _build_locked(
    source: Path,
    out: Path,
    *,
    previous: Path | None,
    staged: list[tuple[Path, Path]],
) -> dict[str, object]:
    if OBJECT_PART_BYTES <= 0 or OBJECT_PART_BYTES > 32 * 1024**2:
        raise ObjectError("ARCA_OBJECT_PART_BYTES must be positive and at most 32 MiB")
    if source.is_symlink() or not source.is_dir():
        raise ObjectError("source must be a real directory")
    out.mkdir(mode=0o700, parents=True, exist_ok=True)
    if out.resolve() == source.resolve() or source.resolve() in out.resolve().parents:
        raise ObjectError("object output must be outside the source tree")
    current = inventory(source)
    root_xattrs = _xattrs(source)
    old_by_path: dict[str, dict[str, object]] = {}
    old_root: Path | None = None
    old_catalog: dict[str, object] | None = None
    if previous is not None:
        with tempfile.TemporaryDirectory(prefix="arca-catalog-") as temporary:
            old_catalog = _decrypt_catalog(previous, Path(temporary) / "catalog.json")
        old_by_path = {
            str(row["path"]): row for row in old_catalog["entries"] if isinstance(row, dict) and "path" in row
        }
        old_root = previous.parent

    entries: list[dict[str, object]] = []
    reused_count = 0
    for row in current:
        entry = dict(row)
        if row["type"] == "file":
            old = old_by_path.get(str(row["path"]))
            reused = False
            if (
                old
                and old.get("type") == "file"
                and old.get("sha256") == row.get("sha256")
                and old.get("mode") == row.get("mode")
                and old_root
            ):
                old_parts = old.get("objects")
                if not isinstance(old_parts, list):
                    old_parts = [{"object_id": old.get("object_id"), "ciphertext_sha256": old.get("ciphertext_sha256")}]
                candidates = [
                    old_root / "objects" / f"{part.get('object_id')}.gpg"
                    for part in old_parts
                    if isinstance(part, dict)
                ]
                if (
                    len(candidates) == len(old_parts)
                    and candidates
                    and all(
                        candidate.is_file()
                        and not candidate.is_symlink()
                        and digest_file(candidate) == part.get("ciphertext_sha256")
                        for candidate, part in zip(candidates, old_parts, strict=True)
                    )
                ):
                    entry["objects"] = old_parts
                    entry["ciphertext_sha256"] = old.get("ciphertext_sha256")
                    if old.get("encryption") == "per-part":
                        entry["encryption"] = "per-part"
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
                parts: list[dict[str, object]] = []
                cipher_digest = hashlib.sha256()
                with (source / str(row["path"])).open("rb") as source_stream:
                    while True:
                        block = source_stream.read(OBJECT_PART_BYTES)
                        if not block and parts:
                            break
                        with tempfile.TemporaryDirectory(prefix="arca-part-", dir=out) as temporary_dir:
                            plain_part = Path(temporary_dir) / "plain"
                            plain_part.write_bytes(block)
                            object_id = secrets.token_hex(24)
                            target = out / "objects" / f"{object_id}.gpg"
                            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                            partial = target.with_name(f".{target.name}.partial")
                            staged.append((partial, target))
                            PRIVATE._encrypt_file(plain_part, partial)
                            if not partial.is_file() or partial.stat().st_size == 0:
                                raise ObjectError("encryption produced an empty object; catalog was not published")
                            if partial.stat().st_size >= 2 * 1024**3:
                                partial.unlink(missing_ok=True)
                                raise ObjectError("encrypted object part exceeds GitHub's per-asset limit")
                            cipher_sha = digest_file(partial)
                            with partial.open("rb") as cipher_stream:
                                for cipher_block in iter(lambda: cipher_stream.read(4 * 1024**2), b""):
                                    cipher_digest.update(cipher_block)
                            parts.append(
                                {
                                    "object_id": object_id,
                                    "ciphertext_sha256": cipher_sha,
                                    "ciphertext_bytes": partial.stat().st_size,
                                    "plaintext_sha256": hashlib.sha256(block).hexdigest(),
                                }
                            )
                        if not block:
                            break
                if digest_file(source / str(row["path"])) != row["sha256"]:
                    raise ObjectError("source changed during encryption; catalog was not published")
                entry["objects"] = parts
                entry["encryption"] = "per-part"
                if len(parts) == 1:
                    entry["object_id"] = parts[0]["object_id"]
                entry["ciphertext_sha256"] = cipher_digest.hexdigest()
            entries.append(entry)
        else:
            entries.append(entry)

    if inventory(source) != current or _xattrs(source) != root_xattrs:
        raise ObjectError("source or extended metadata changed during capture; catalog was not published")
    # Publish objects first. The encrypted catalog is the commit point and cannot reference
    # incomplete writes. Existing random object names are never overwritten.
    for temporary, target in staged:
        if target.exists():
            raise ObjectError("random object identifier collision; catalog was not published")
        os.replace(temporary, target)
    catalog = {
        "schema": "arca-file-catalog-v4",
        "root_mode": stat.S_IMODE(source.stat().st_mode),
        "root_xattrs": root_xattrs,
        "metadata_coverage": {
            "captured": ["content", "mode", "symlink_target", "xattrs"],
            "unverified": ["acl", "ownership", "timestamps"],
        },
        "entries": entries,
    }
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
            plaintext.write_text(
                json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":")), encoding="utf-8"
            )
            os.chmod(plaintext, 0o600)
            temp_cipher = out / ".catalog.gpg.partial"
            PRIVATE._encrypt_file(plaintext, temp_cipher)
            if not temp_cipher.is_file() or temp_cipher.stat().st_size == 0:
                raise ObjectError("catalog encryption failed; catalog was not published")
            os.replace(temp_cipher, catalog_path)
        state = "ready"
    return {
        "state": state,
        "coverage": "incomplete-native-metadata",
        "files": sum(row["type"] == "file" for row in entries),
        "new_objects": len(staged),
        "reused_objects": reused_count,
        "catalog": str(catalog_path),
    }


def restore(catalog_path: Path, objects_root: Path, destination: Path) -> dict[str, object]:
    """Decrypt and atomically create a previously absent directory tree."""
    if destination.exists() or destination.is_symlink():
        raise ObjectError("restore destination already exists; refusing to overwrite")
    destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".arca-restore-", dir=destination.parent) as temporary:
        base = Path(temporary)
        catalog_file = base / "catalog.json"
        catalog = _decrypt_catalog(catalog_path, catalog_file)
        has_xattrs = catalog["schema"] == "arca-file-catalog-v4"
        entries = catalog["entries"]
        by_path: dict[str, dict[str, object]] = {}
        for raw in entries:
            if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
                raise ObjectError("catalog contains an invalid entry")
            rel = Path(str(raw["path"]))
            if (
                rel.is_absolute()
                or not rel.parts
                or any(part in ("", ".", "..") for part in rel.parts)
                or "\\" in str(raw["path"])
            ):
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
                checked_parts: list[tuple[Path, dict[str, object]]] = []
                for part in parts:
                    if not isinstance(part, dict):
                        raise ObjectError("catalog contains an invalid object part")
                    object_id = part.get("object_id")
                    if not isinstance(object_id, str) or not re.fullmatch(r"[0-9a-f]{48}", object_id):
                        raise ObjectError("catalog contains an invalid object identifier")
                    cipher = objects_root / "objects" / f"{object_id}.gpg"
                    if (
                        cipher.is_symlink()
                        or not cipher.is_file()
                        or digest_file(cipher) != part.get("ciphertext_sha256")
                    ):
                        raise ObjectError("encrypted object is missing or failed integrity verification")
                    checked_parts.append((cipher, part))
                if row.get("encryption") == "per-part":
                    with target.open("wb") as restored:
                        for cipher, part in checked_parts:
                            plain_part = base / "part.plain"
                            PRIVATE._decrypt_file(cipher, plain_part)
                            if digest_file(plain_part) != part.get("plaintext_sha256"):
                                raise ObjectError("decrypted part failed integrity verification")
                            with plain_part.open("rb") as fragment:
                                shutil.copyfileobj(fragment, restored, length=4 * 1024**2)
                            plain_part.unlink()
                elif row.get("encryption") is None:
                    with (base / "cipher.gpg").open("wb") as combined:
                        for cipher, _part in checked_parts:
                            with cipher.open("rb") as fragment:
                                shutil.copyfileobj(fragment, combined, length=4 * 1024**2)
                    combined_cipher = base / "cipher.gpg"
                    if digest_file(combined_cipher) != row.get("ciphertext_sha256"):
                        raise ObjectError("reassembled ciphertext failed integrity verification")
                    PRIVATE._decrypt_file(combined_cipher, target)
                else:
                    raise ObjectError("catalog contains an unsupported encryption mode")
                if digest_file(target) != row.get("sha256"):
                    raise ObjectError("decrypted object failed plaintext integrity verification")
                os.chmod(target, int(row.get("mode", 0o600)))
                if has_xattrs:
                    _apply_xattrs(target, row.get("xattrs"))
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
                if has_xattrs:
                    _apply_xattrs(target, row.get("xattrs"))
        for name, row in by_path.items():
            if row.get("type") == "directory":
                os.chmod(staging / name, int(row.get("mode", 0o700)))
                if has_xattrs:
                    _apply_xattrs(staging / name, row.get("xattrs"))
        os.chmod(staging, int(catalog.get("root_mode", 0o700)))
        if has_xattrs:
            _apply_xattrs(staging, catalog.get("root_xattrs"))
        os.replace(staging, destination)
    return {
        "state": "restored",
        "coverage": "incomplete-native-metadata" if has_xattrs else "legacy-unverified-metadata",
        "files": sum(row.get("type") == "file" for row in entries),
    }


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
