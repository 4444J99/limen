#!/usr/bin/env python3
"""PRIVATE-VAULT — git-tracked ciphertext custody for high-value private artifacts.

THE MEASURED DEFECT (2026-08-09). The professional-positioning research dossier — ten
research dispatches of paid model spend, the controlling input to a strategy engagement —
lived in exactly two places: a gitignored file under `.limen-private/reports/` and a
Copilot session-state orphan under `~/.copilot/session-state/`. One host, one device, no
remote, no custody receipts. `.gitignore` is a *secrecy* mechanism; it is not a *custody*
mechanism — an ignored file is precisely the file every clone, every evacuation sweep, and
every `git`-based replication path silently skips. The estate already measured this shape
once: the 2026-07-27 evacuation made "absent = custodied or unaccounted?" load-bearing and
built the CUSTODY axis for corpora roots. This organ is the same answer for *individual
documents*: too small for an archive-class corpora root, too valuable for `/tmp`.

THE MECHANISM. Ciphertext is TRACKED; plaintext is IGNORED. `vault add <file>` encrypts to
the committed GPG public key (docs/keys/anthony-padavano-gpg.asc — Anthony's ed25519/cv25519
pair, private half on his hardware only) and writes `<sha>.gpg` + a manifest row under
`institutio/vault/`. The ciphertext then rides ordinary git replication — every clone,
every GitHub mirror, every evacuation copy carries it — while decryption stays gated on
his private key. No new secret is minted; no plaintext ever enters the object store.

  add      encrypt a file into the vault + manifest row (idempotent on content sha)
  verify   exit 0 ⟺ every manifest row's ciphertext exists, sha matches, and no
           plaintext original is tracked by git (the leak check)
  restore  decrypt one entry (or --all) to a destination (requires the private key)
  list     manifest rows, newest first

The manifest never carries plaintext content — only filenames, sizes, shas, and a short
operator-supplied description. Filenames of private artifacts are treated as public-safe
metadata; if a NAME is itself sensitive, pass --slug to store it under a neutral one.

Recipient derivation: the committed pubkey file is the single source of truth. The key is
imported into an isolated GNUPGHOME per run, so nothing depends on host keyring state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUBKEY = ROOT / "docs" / "keys" / "anthony-padavano-gpg.asc"
VAULT_DIR = ROOT / "institutio" / "vault"
MANIFEST = VAULT_DIR / "manifest.jsonl"
FINGERPRINT = "205A566A5FFE43D2E28E05A4C5B98FFAF8ED000E"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _gpg_env(gnupghome: str) -> dict:
    env = dict(os.environ)
    env["GNUPGHOME"] = gnupghome
    return env


def _import_pubkey(gnupghome: str) -> None:
    if not PUBKEY.exists():
        sys.exit(f"FAIL: committed public key missing: {PUBKEY}")
    run = subprocess.run(
        ["gpg", "--batch", "--import", str(PUBKEY)],
        env=_gpg_env(gnupghome),
        capture_output=True,
        text=True,
    )
    if run.returncode != 0:
        sys.exit(f"FAIL: pubkey import: {run.stderr.strip()}")


def _read_manifest() -> list[dict]:
    if not MANIFEST.exists():
        return []
    rows = []
    for line in MANIFEST.read_text().splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def cmd_add(args: argparse.Namespace) -> int:
    src = Path(args.file).expanduser().resolve()
    if not src.is_file():
        sys.exit(f"FAIL: not a file: {src}")
    plain_sha = _sha256(src)
    rows = _read_manifest()
    for row in rows:
        if row["plaintext_sha256"] == plain_sha:
            print(f"OK: already vaulted as {row['ciphertext']} ({row['slug']})")
            return 0
    slug = args.slug or src.stem
    cipher_name = f"{plain_sha[:16]}-{slug}.gpg"
    VAULT_DIR.mkdir(parents=True, exist_ok=True)
    cipher_path = VAULT_DIR / cipher_name

    with tempfile.TemporaryDirectory() as gnupghome:
        os.chmod(gnupghome, 0o700)
        _import_pubkey(gnupghome)
        run = subprocess.run(
            [
                "gpg",
                "--batch",
                "--yes",
                "--trust-model",
                "always",
                "--recipient",
                FINGERPRINT,
                "--output",
                str(cipher_path),
                "--encrypt",
                str(src),
            ],
            env=_gpg_env(gnupghome),
            capture_output=True,
            text=True,
        )
    if run.returncode != 0 or not cipher_path.exists():
        sys.exit(f"FAIL: encrypt: {run.stderr.strip()}")

    row = {
        "slug": slug,
        "ciphertext": cipher_name,
        "ciphertext_sha256": _sha256(cipher_path),
        "plaintext_sha256": plain_sha,
        "plaintext_bytes": src.stat().st_size,
        "source_path": str(src),
        "description": args.description or "",
        "recipient_fpr": FINGERPRINT,
        "vaulted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with MANIFEST.open("a") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")
    print(f"OK: vaulted {src.name} -> institutio/vault/{cipher_name}")
    print(f"    plaintext sha256 {plain_sha}")
    print("    next: git add the ciphertext + manifest; plaintext stays untracked")
    return 0


def cmd_verify(_args: argparse.Namespace) -> int:
    rows = _read_manifest()
    if not rows:
        print("OK: vault empty (0 rows)")
        return 0
    failures = []
    tracked = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    tracked_set = set(tracked)
    seen_ciphers = set()
    for row in rows:
        name = row["ciphertext"]
        seen_ciphers.add(name)
        path = VAULT_DIR / name
        if not path.exists():
            failures.append(f"missing ciphertext: {name}")
            continue
        if _sha256(path) != row["ciphertext_sha256"]:
            failures.append(f"ciphertext sha mismatch: {name}")
        rel = path.relative_to(ROOT).as_posix()
        if rel not in tracked_set:
            failures.append(f"ciphertext not git-tracked (custody gap): {rel}")
        # leak check: the plaintext source must never be tracked
        src = row.get("source_path", "")
        if src:
            try:
                rel_src = Path(src).resolve().relative_to(ROOT).as_posix()
                if rel_src in tracked_set:
                    failures.append(f"PLAINTEXT TRACKED (leak): {rel_src}")
            except ValueError:
                pass  # plaintext outside repo — fine
    for stray in VAULT_DIR.glob("*.gpg"):
        if stray.name not in seen_ciphers:
            failures.append(f"unmanifested ciphertext: {stray.name}")
    if failures:
        print("FAIL: private-vault custody:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"OK: private-vault custody ({len(rows)} row(s); ciphertext tracked, no plaintext leak)")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    rows = _read_manifest()
    targets = rows if args.all else [r for r in rows if r["slug"] == args.slug]
    if not targets:
        sys.exit(f"FAIL: no vault entry with slug '{args.slug}' (use list)")
    dest_dir = Path(args.dest).expanduser().resolve()
    dest_dir.mkdir(parents=True, exist_ok=True)
    for row in targets:
        cipher_path = VAULT_DIR / row["ciphertext"]
        out = dest_dir / row["ciphertext"].removesuffix(".gpg")
        run = subprocess.run(
            ["gpg", "--batch", "--yes", "--output", str(out), "--decrypt", str(cipher_path)],
            capture_output=True,
            text=True,
        )
        if run.returncode != 0:
            sys.exit(f"FAIL: decrypt {row['slug']} (private key required): {run.stderr.strip()}")
        if _sha256(out) != row["plaintext_sha256"]:
            sys.exit(f"FAIL: restored plaintext sha mismatch for {row['slug']}")
        print(f"OK: restored {row['slug']} -> {out} (sha verified)")
    return 0


def cmd_list(_args: argparse.Namespace) -> int:
    rows = _read_manifest()
    if not rows:
        print("(vault empty)")
        return 0
    for row in sorted(rows, key=lambda r: r["vaulted_at"], reverse=True):
        print(f"{row['vaulted_at']}  {row['slug']:40s}  {row['plaintext_bytes']:>9d}B  {row['ciphertext']}")
        if row.get("description"):
            print(f"{'':27s}{row['description']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add", help="encrypt a file into the vault")
    p_add.add_argument("file")
    p_add.add_argument("--slug", help="neutral name if the filename is itself sensitive")
    p_add.add_argument("--description", help="short public-safe description for the manifest")
    p_add.set_defaults(fn=cmd_add)

    p_ver = sub.add_parser("verify", help="custody predicate: exit 0 iff coherent + no leak")
    p_ver.set_defaults(fn=cmd_verify)

    p_res = sub.add_parser("restore", help="decrypt entries (requires private key)")
    p_res.add_argument("--slug", help="entry to restore")
    p_res.add_argument("--all", action="store_true")
    p_res.add_argument("--dest", default=str(Path.home() / ".limen-restore"))
    p_res.set_defaults(fn=cmd_restore)

    p_list = sub.add_parser("list", help="manifest rows, newest first")
    p_list.set_defaults(fn=cmd_list)

    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
