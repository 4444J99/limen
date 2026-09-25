#!/usr/bin/env python3
"""Publish opaque ARCA ciphertext as neutral GitHub Release assets.

Large payloads stay outside Git's object database. A digest-addressed encrypted
catalog names each ciphertext asset; the release tag derives from that catalog's
ciphertext digest, making interrupted batches safely resumable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

MAX_ASSET_BYTES = 2 * 1024**3 - 1  # GitHub requires each release asset to be under 2 GiB.
MAX_RELEASE_ASSETS = 1000
BATCH_DEADLINE_SECONDS = 25 * 60
MAX_UPLOAD_FILES = int(os.environ.get("ARCA_MAX_UPLOAD_FILES", "16"))
MAX_UPLOAD_BYTES = 128 * 1024**2
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OPENPGP_ARMOR = b"-----BEGIN PGP MESSAGE-----"


class AssetError(RuntimeError):
    """An asset batch could not be published and verified safely."""


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            size += len(chunk)
            digest.update(chunk)
    return digest.hexdigest(), size


def _run(args: list[str], *, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AssetError(f"GitHub asset operation failed ({type(exc).__name__})") from exc
    if result.returncode:
        detail = re.search(
            r"HTTP [0-9]{3}|rate limit|already exists|Validation Failed|timeout|connection reset",
            result.stderr,
            re.IGNORECASE,
        )
        reason = detail.group(0) if detail else f"exit {result.returncode}"
        raise AssetError(f"GitHub asset operation failed ({reason}); source ciphertext retained")
    return result


def _canonical_repository(repo: str) -> tuple[int, str, str]:
    if not REPO_RE.fullmatch(repo):
        raise AssetError("repository must be owner/name")
    try:
        discovered = json.loads(_run(["gh", "api", f"repos/{repo}"], timeout=30).stdout)
        if not isinstance(discovered, dict):
            raise TypeError("repository alias response is not an object")
        stable_id = int(discovered["id"])
        live = json.loads(_run(["gh", "api", f"repositories/{stable_id}"], timeout=30).stdout)
        if not isinstance(live, dict):
            raise TypeError("immutable repository response is not an object")
        coordinate = str(live["full_name"])
        default_branch = str(live["default_branch"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AssetError("cannot resolve immutable GitHub repository identity") from exc
    if (
        stable_id <= 0
        or int(live.get("id", -1)) != stable_id
        or discovered.get("private") is not True
        or live.get("private") is not True
        or coordinate != str(discovered.get("full_name", ""))
        or not REPO_RE.fullmatch(coordinate)
        or not re.fullmatch(r"[A-Za-z0-9_./-]+", default_branch)
    ):
        raise AssetError("repository identity changed or is not verified private")
    return stable_id, coordinate, default_branch


def _authorize_write(repo: str) -> None:
    """Mint a fresh registry-bound owner receipt before every remote mutation."""
    root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            [
                sys.executable,
                str(root / "scripts" / "preflight-receipt.py"),
                "--action",
                "arca.release-assets",
                "--target",
                repo,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AssetError("outbound preflight could not complete; no release mutation performed") from exc
    sys.stderr.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode:
        raise AssetError("outbound preflight failed; no release mutation performed")


def _preflight(
    catalog: Path,
    objects: list[Path],
    expected_digests: dict[Path, str] | None = None,
) -> tuple[list[tuple[Path, str, str, int]], str, int]:
    paths = [catalog, *objects]
    if len({path.resolve() for path in paths}) != len(paths):
        raise AssetError("catalog and object paths must be unique")
    assets: list[tuple[Path, str, str, int]] = []
    total = 0
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise AssetError("asset sources must be regular non-symlink files")
        name = path.name.lower()
        if not (name.endswith((".enc", ".gpg")) or re.search(r"\.(?:enc|gpg)\.part\.[a-z]+$", name)):
            raise AssetError("catalog and payload filenames must identify encrypted material")
        if path == catalog:
            with path.open("rb") as handle:
                header = handle.read(32)
            binary_openpgp = bool(header) and header[0] & 0xC0 in (0x80, 0xC0)
            if not (header.startswith((b"Salted__", OPENPGP_ARMOR)) or binary_openpgp):
                raise AssetError("catalog must have a recognized OpenSSL or OpenPGP ciphertext header")
        digest, size = _digest(path)
        if expected_digests is not None and path in expected_digests and digest != expected_digests[path]:
            raise AssetError("asset source changed after encrypted catalog construction")
        if size > MAX_ASSET_BYTES:
            raise AssetError("release asset exceeds the under-2-GiB per-file limit")
        label = "catalog" if path == catalog else "object"
        name = f"{label}-{digest}.enc"
        assets.append((path, name, digest, size))
        total += size
    catalog_digest = assets[0][2]
    # The encrypted catalog is the commit marker. Publish it only after every
    # ciphertext object has uploaded and passed remote readback.
    return [*assets[1:], assets[0]], f"arca-objects-{catalog_digest[:32]}", total


def publish(
    repo: str,
    catalog: Path,
    objects: list[Path],
    *,
    apply: bool,
    expected_digests: dict[Path, str] | None = None,
    verify_existing_by_server_digest: bool = False,
    batch_deadline_seconds: int = BATCH_DEADLINE_SECONDS,
) -> dict[str, object]:
    if not REPO_RE.fullmatch(repo):
        raise AssetError("repository must be owner/name")
    if not 60 <= batch_deadline_seconds <= BATCH_DEADLINE_SECONDS:
        raise AssetError("batch deadline must be between 60 and 1500 seconds")
    if not 1 <= MAX_UPLOAD_FILES <= 16:
        raise AssetError("ARCA_MAX_UPLOAD_FILES must be between 1 and 16")
    stable_id, canonical, default_branch = _canonical_repository(repo) if apply else (None, repo, "main")
    assets, tag, total = _preflight(catalog, objects, expected_digests)
    object_assets = assets[:-1]
    groups = (
        [(tag, assets)]
        if len(assets) <= MAX_RELEASE_ASSETS else
        [
            (f"{tag}-part-{index // MAX_RELEASE_ASSETS + 1:04d}", object_assets[index:index + MAX_RELEASE_ASSETS])
            for index in range(0, len(object_assets), MAX_RELEASE_ASSETS)
        ] + [(tag, [assets[-1]])]
    )
    if not apply:
        return {
            "state": "planned",
            "repo": canonical,
            "tag": tag,
            "asset_count": len(assets),
            "release_count": len(groups),
            "bytes": total,
        }

    deadline = time.monotonic() + batch_deadline_seconds

    def remaining_timeout(limit: int = 900) -> int:
        remaining = deadline - time.monotonic()
        if remaining <= 1:
            raise AssetError("batch deadline reached; local source and verified remote assets retained for resume")
        return min(limit, max(1, int(remaining)))

    prior_assets = _existing_assets(canonical)
    for group_tag, group_assets in groups:
        _publish_group(canonical, default_branch, group_tag, group_assets, prior_assets,
                       remaining_timeout, verify_existing_by_server_digest)
        for _source, name, _digest_value, _size in group_assets:
            prior_assets.setdefault(name, group_tag)
    return {
        "state": "verified",
        "repository_id": stable_id,
        "tag": tag,
        "asset_count": len(assets),
        "release_count": len(groups),
        "bytes": total,
    }


def _publish_group(
    canonical: str,
    default_branch: str,
    tag: str,
    assets: list[tuple[Path, str, str, int]],
    prior_assets: dict[str, str],
    remaining_timeout: Callable[..., int],
    verify_existing_by_server_digest: bool,
) -> None:
    existing = (
        _run(
            ["gh", "release", "view", tag, "--repo", canonical, "--json", "assets", "--jq", ".assets[].name"],
            timeout=remaining_timeout(30),
        )
        if _release_exists(canonical, tag)
        else None
    )
    names = set(existing.stdout.splitlines()) if existing else set()
    remote_digests = (
        _release_asset_digests(canonical, tag)
        if names and verify_existing_by_server_digest else {}
    )
    if existing is None:
        _authorize_write(canonical)
        _run(
            [
                "gh",
                "release",
                "create",
                tag,
                "--repo",
                canonical,
                "--title",
                "ARCA encrypted object batch",
                "--notes",
                "Encrypted objects and catalog.",
                "--target",
                default_branch,
            ],
            timeout=remaining_timeout(120),
        )

    with tempfile.TemporaryDirectory(prefix="arca-release-readback-") as directory:
        readback = Path(directory)
        verified_in_batch: set[str] = set()
        for index, (source, asset_name, expected_digest, _size) in enumerate(assets, start=1):
            if asset_name in verified_in_batch:
                continue
            source_tag = tag if asset_name in names else prior_assets.get(asset_name)
            if source_tag == tag and verify_existing_by_server_digest:
                remote = remote_digests.get(asset_name)
                if remote != (expected_digest, _size):
                    raise AssetError("existing release asset has no matching server digest and size")
                print(f"ARCA asset verified {index}/{len(assets)} (server digest)", file=sys.stderr, flush=True)
                continue
            if source_tag is None:
                # One gh invocation is one authorized mutation. Keep batches small
                # enough for the deadline and never include the catalog marker.
                pending: list[tuple[Path, str, str]] = []
                pending_bytes = 0
                remaining_objects = assets[index - 1:-1] if assets[-1][1].startswith("catalog-") else assets[index - 1:]
                for next_source, next_name, next_digest, next_size in remaining_objects:
                    if next_name in names or next_name in prior_assets:
                        break
                    if pending and (len(pending) >= MAX_UPLOAD_FILES or pending_bytes + next_size > MAX_UPLOAD_BYTES):
                        break
                    if _digest(next_source) != (next_digest, next_size):
                        raise AssetError("asset source changed before upload; no mismatched bytes sent")
                    pending.append((next_source, next_name, next_digest))
                    pending_bytes += next_size
                if not pending:
                    pending = [(source, asset_name, expected_digest)]
                    if _digest(source) != (expected_digest, _size):
                        raise AssetError("asset source changed before upload; no mismatched bytes sent")
                upload_paths: list[Path] = []
                for pending_source, pending_name, _ in pending:
                    upload_path = readback / pending_name
                    upload_path.symlink_to(pending_source.resolve())
                    upload_paths.append(upload_path)
                _authorize_write(canonical)
                _run(["gh", "release", "upload", tag, *map(str, upload_paths), "--repo", canonical], timeout=remaining_timeout())
                for upload_path in upload_paths:
                    upload_path.unlink()
                    names.add(upload_path.name)
                download_args = ["gh", "release", "download", tag, "--repo", canonical]
                for _pending_source, pending_name, _pending_digest in pending:
                    download_args.extend(["--pattern", pending_name])
                download_args.extend(["--dir", str(readback)])
                _run(download_args, timeout=remaining_timeout())
                for _pending_source, pending_name, pending_digest in pending:
                    downloaded = readback / pending_name
                    if not downloaded.is_file() or _digest(downloaded)[0] != pending_digest:
                        raise AssetError("release readback digest mismatch; local source retained")
                    downloaded.unlink()
                    verified_in_batch.add(pending_name)
                print(f"ARCA assets verified {len(verified_in_batch)}/{len(assets)} (batched readback)", file=sys.stderr, flush=True)
                continue
            _run(
                [
                    "gh",
                    "release",
                    "download",
                    source_tag,
                    "--repo",
                    canonical,
                    "--pattern",
                    asset_name,
                    "--dir",
                    str(readback),
                ],
                timeout=remaining_timeout(),
            )
            downloaded = readback / asset_name
            if not downloaded.is_file() or _digest(downloaded)[0] != expected_digest:
                raise AssetError("release readback digest mismatch; local source retained")
            downloaded.unlink()
            print(f"ARCA asset verified {index}/{len(assets)}", file=sys.stderr, flush=True)


def _release_exists(repo: str, tag: str) -> bool:
    tags = _run(
        ["gh", "api", f"repos/{repo}/releases?per_page=100", "--paginate", "--jq", ".[].tag_name"],
        timeout=60,
    ).stdout.splitlines()
    return tag in tags


def _release_asset_digests(repo: str, tag: str) -> dict[str, tuple[str, int]]:
    """Require GitHub's uploaded-state SHA-256 and size for existing assets."""
    try:
        data = json.loads(_run(["gh", "api", f"repos/{repo}/releases/tags/{tag}"], timeout=30).stdout)
        rows = data["assets"]
        if not isinstance(rows, list):
            raise TypeError("assets are not a list")
        result: dict[str, tuple[str, int]] = {}
        for row in rows:
            name = row["name"]
            digest = row["digest"]
            size = row["size"]
            if (
                not isinstance(name, str) or name in result
                or row["state"] != "uploaded" or not isinstance(digest, str)
                or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
                or not isinstance(size, int) or size < 0
            ):
                raise ValueError("existing asset metadata is incomplete")
            result[name] = (digest.removeprefix("sha256:"), size)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AssetError("cannot verify existing release asset digests") from exc
    return result


def _existing_assets(repo: str) -> dict[str, str]:
    """Index neutral assets across releases once for incremental reuse."""
    rows = _run(
        [
            "gh",
            "api",
            f"repos/{repo}/releases?per_page=100",
            "--paginate",
            "--jq",
            ".[] | . as $r | $r.assets[]? | [$r.tag_name, .name] | @tsv",
        ],
        timeout=90,
    ).stdout.splitlines()
    result: dict[str, str] = {}
    for row in rows:
        tag, separator, name = row.partition("\t")
        if separator and re.fullmatch(r"arca-objects-[a-f0-9]{32}(?:-part-[0-9]{4})?", tag):
            result.setdefault(name, tag)
    return result


def _objects_from_dir(directory: Path) -> list[Path]:
    if directory.is_symlink() or not directory.is_dir():
        raise AssetError("object directory must be a real directory")
    objects = sorted(directory.glob("*.gpg"))
    if not objects:
        raise AssetError("object directory has no encrypted objects")
    return objects


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--catalog", type=Path, required=True, help="already encrypted catalog")
    parser.add_argument(
        "--object", type=Path, action="append", default=[], help="encrypted payload object; repeatable"
    )
    parser.add_argument("--objects-dir", type=Path, help="directory of encrypted .gpg objects")
    parser.add_argument("--batch-deadline-seconds", type=int, default=BATCH_DEADLINE_SECONDS)
    parser.add_argument("--verify-existing-by-server-digest", action="store_true")
    parser.add_argument(
        "--apply", action="store_true", help="create/reuse a private release and upload/read back assets"
    )
    args = parser.parse_args()
    try:
        if bool(args.object) == bool(args.objects_dir):
            raise AssetError("provide exactly one of --object or --objects-dir")
        objects = _objects_from_dir(args.objects_dir) if args.objects_dir else args.object
        result = publish(args.repo, args.catalog, objects, apply=args.apply,
                         batch_deadline_seconds=args.batch_deadline_seconds,
                         verify_existing_by_server_digest=args.verify_existing_by_server_digest)
    except AssetError as exc:
        print(f"arca-release-assets: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
