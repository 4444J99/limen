#!/usr/bin/env python3
"""Probe the existing owner CI cache; optionally deliver it through the exact UCC App principal."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TARGET = "organvm-iii-ergon/public-record-data-scrapper"
SECRET_NAME = "CLOUDFLARE_API_TOKEN"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("preflight", "apply"), default="preflight")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("clavis_hydrate", ROOT / "scripts/creds-hydrate.py")
    hydrate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hydrate)
    entry = next(
        entry for entry in hydrate.DEFAULT_MAP if entry.get("gh_secret") == {"repo": TARGET, "name": SECRET_NAME}
    )
    candidate = os.environ.get(SECRET_NAME, "")
    if not candidate:
        print("FAIL: owning repository Cloudflare cache is absent; no destination write attempted")
        return 1
    ok, detail = hydrate.verify_cloudflare_delivery(entry, candidate)
    print(f"{'PASS' if ok else 'FAIL'}: Cloudflare candidate: {detail}")
    if not ok:
        return 1
    if args.mode == "preflight":
        print("PASS: read-only candidate preflight; no destination write attempted")
        return 0
    if not os.environ.get("GITHUB_APP_ID") or not os.environ.get("GITHUB_APP_PRIVATE_KEY"):
        print("FAIL: UCC delivery App credential configuration is absent; destination unchanged")
        return 1
    try:
        minted = subprocess.run(
            ["bash", str(ROOT / "scripts/gh-app-token.sh"), "--repo", TARGET, "--app-only"],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
        )
        if minted.returncode != 0 or not minted.stdout.strip():
            print("FAIL: exact UCC App principal could not be established; destination unchanged")
            return 1
        environment = {**os.environ, "GH_TOKEN": minted.stdout.strip()}
        environment.pop("GITHUB_TOKEN", None)
        delivered = subprocess.run(
            ["gh", "secret", "set", SECRET_NAME, "--repo", TARGET],
            input=candidate,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
        if delivered.returncode != 0:
            print("FAIL: verified UCC App principal could not write the target secret")
            return 1
    except Exception:  # noqa: BLE001 — no subprocess payload or exception may expose credentials
        print("FAIL: credential delivery transport unavailable; inspect only sanitized owner receipts")
        return 1
    print("PASS: UCC secret delivered; UCC resource/write preflight and deployment remain required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
