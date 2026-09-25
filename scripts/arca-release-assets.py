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
import re
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_ASSET_BYTES = 2 * 1024**3 - 1  # GitHub requires each release asset to be under 2 GiB.
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
        raise AssetError("GitHub asset operation failed; source ciphertext retained")
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
) -> dict[str, object]:
    if not REPO_RE.fullmatch(repo):
        raise AssetError("repository must be owner/name")
    stable_id, canonical, default_branch = _canonical_repository(repo) if apply else (None, repo, "main")
    assets, tag, total = _preflight(catalog, objects, expected_digests)
    if not apply:
        return {
            "state": "planned",
            "repo": canonical,
            "tag": tag,
            "asset_count": len(assets),
            "bytes": total,
        }

    existing = (
        _run(
            ["gh", "release", "view", tag, "--repo", canonical, "--json", "assets", "--jq", ".assets[].name"],
            timeout=30,
        )
        if _release_exists(canonical, tag)
        else None
    )
    names = set(existing.stdout.splitlines()) if existing else set()
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
            timeout=120,
        )

    prior_assets = _existing_assets(canonical)
    with tempfile.TemporaryDirectory(prefix="arca-release-readback-") as directory:
        readback = Path(directory)
        for source, asset_name, expected_digest, _size in assets:
            source_tag = tag if asset_name in names else prior_assets.get(asset_name)
            if source_tag is None:
                if _digest(source)[0] != expected_digest:
                    raise AssetError("asset source changed before upload; no mismatched bytes sent")
                upload_path = readback / asset_name
                upload_path.symlink_to(source.resolve())
                _authorize_write(canonical)
                _run(["gh", "release", "upload", tag, str(upload_path), "--repo", canonical])
                upload_path.unlink()
                source_tag = tag
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
                ]
            )
            downloaded = readback / asset_name
            if not downloaded.is_file() or _digest(downloaded)[0] != expected_digest:
                raise AssetError("release readback digest mismatch; local source retained")
            downloaded.unlink()
    return {
        "state": "verified",
        "repository_id": stable_id,
        "tag": tag,
        "asset_count": len(assets),
        "bytes": total,
    }


def _release_exists(repo: str, tag: str) -> bool:
    tags = _run(
        ["gh", "api", f"repos/{repo}/releases?per_page=100", "--paginate", "--jq", ".[].tag_name"],
        timeout=60,
    ).stdout.splitlines()
    return tag in tags


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
        if separator and re.fullmatch(r"arca-objects-[a-f0-9]{32}", tag):
            result.setdefault(name, tag)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", required=True)
    parser.add_argument("--catalog", type=Path, required=True, help="already encrypted catalog")
    parser.add_argument(
        "--object", type=Path, action="append", required=True, help="encrypted payload object; repeatable"
    )
    parser.add_argument(
        "--apply", action="store_true", help="create/reuse a private release and upload/read back assets"
    )
    args = parser.parse_args()
    try:
        result = publish(args.repo, args.catalog, args.object, apply=args.apply)
    except AssetError as exc:
        print(f"arca-release-assets: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
