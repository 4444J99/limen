#!/usr/bin/env python3
"""Read-only, bounded recovery from canonical escrow; never extract plaintext."""

import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile

LIMIT = 1024 * 1024


def run(args: list[str], data: bytes | None = None) -> bytes:
    env = dict(os.environ)
    env.pop("OP_SERVICE_ACCOUNT_TOKEN", None)
    return subprocess.run(
        args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=True, timeout=30, env=env,
    ).stdout


def inspect_tar(plaintext: bytes) -> dict[str, int]:
    """Read regular members fully without following links or writing files."""
    if not plaintext or len(plaintext) > LIMIT:
        raise ValueError("archive bound")
    count = size = members = 0
    with tarfile.open(fileobj=io.BytesIO(plaintext), mode="r:") as archive:
        for member in archive:
            members += 1
            if members > 1024 or member.size < 0 or member.size > LIMIT:
                raise ValueError("member bound")
            if member.isfile():
                size += member.size
                if size > LIMIT:
                    raise ValueError("content bound")
                stream = archive.extractfile(member)
                if stream is None or len(stream.read(LIMIT + 1)) != member.size:
                    raise ValueError("incomplete member")
                count += 1
    if count == 0:
        raise ValueError("no regular content")
    return {"regular_files": count, "plaintext_bytes": size}


def recover(vault: Path) -> dict:
    # Read committed manifest/ciphertext, not mutable working-copy replacements.
    head = run(["git", "-C", str(vault), "rev-parse", "HEAD"]).decode().strip()
    manifest_size = int(run(["git", "-C", str(vault), "cat-file", "-s", f"{head}:manifest.json"]))
    if not 0 < manifest_size <= LIMIT:
        raise ValueError("manifest bound")
    manifest_bytes = run(["git", "-C", str(vault), "show", f"{head}:manifest.json"])
    if len(manifest_bytes) > LIMIT:
        raise ValueError("manifest bound")
    manifest = json.loads(manifest_bytes)
    if not isinstance(manifest, dict):
        raise ValueError("manifest shape")
    candidates = []
    for name, record in manifest.items():
        if name in {"_generation", "_generations"}:
            continue
        if not isinstance(record, dict) or not re.fullmatch(r"[\w.-]+", name):
            continue
        length = record.get("bytes")
        if record.get("parts") == 0 and type(length) is int and 0 < length <= LIMIT:
            candidates.append((length, name))
    if not candidates:
        raise ValueError("no bounded committed archive")
    length, name = min(candidates)
    ref = f"{head}:{name}.tar.enc"
    actual = int(run(["git", "-C", str(vault), "cat-file", "-s", ref]))
    if actual != length:
        raise ValueError("ciphertext size mismatch")
    ciphertext = run(["git", "-C", str(vault), "show", ref])
    key = run(["op", "read", "op://Private/limen-arca-vault/password"]).strip()
    if not re.fullmatch(rb"[0-9a-fA-F]{64}", key):
        raise ValueError("escrow key shape")
    # Separate anonymous pipe for the password keeps it out of argv/environment.
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, key + b"\n")
        os.close(write_fd)
        write_fd = -1
        plaintext = subprocess.run(
            ["openssl", "enc", "-d", "-aes-256-cbc", "-pbkdf2", "-iter", "200000",
             "-pass", f"fd:{read_fd}"],
            input=ciphertext, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            pass_fds=(read_fd,), check=True, timeout=30,
        ).stdout
    finally:
        os.close(read_fd)
        if write_fd != -1:
            os.close(write_fd)
    return {"schema": "limen.arca-escrow-check.v1", "accepted": True,
            "scope": "one-bounded-committed-archive", "ciphertext_bytes": actual,
            **inspect_tar(plaintext)}


def main() -> int:
    try:
        result = recover(Path.home() / ".arca-vault")
    except (OSError, ValueError, subprocess.SubprocessError, tarfile.TarError):
        # Neither private archive names nor provider stderr belongs in public receipts.
        print(json.dumps({"schema": "limen.arca-escrow-check.v1", "accepted": False}))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
