#!/usr/bin/env python3
"""Probe the existing owner CI cache; optionally deliver it through the exact UCC App principal."""

from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import re
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
    expected_sha = os.environ.get("EXPECTED_SHA", "")
    source_token = os.environ.get("SOURCE_GITHUB_TOKEN", "")
    if not re.fullmatch(r"[0-9a-f]{40}", expected_sha) or not source_token:
        print("FAIL: current-main verification inputs are unavailable; destination unchanged")
        return 1
    try:
        minted = subprocess.run(
            ["bash", str(ROOT / "scripts/gh-app-token.sh"), "--repo", TARGET, "--app-only", "--require-secrets-write"],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
        )
        if minted.returncode != 0 or not minted.stdout.strip():
            if "exact-repository App token lacks the required Secrets-write grant" in minted.stderr:
                print("FAIL: exact UCC App principal lacks Secrets-write; destination unchanged")
            else:
                print("FAIL: exact UCC App principal could not be established; destination unchanged")
            return 1
        read_environment = {**os.environ, "GH_TOKEN": source_token}
        for key in ("GITHUB_TOKEN", "GITHUB_APP_PRIVATE_KEY", SECRET_NAME):
            read_environment.pop(key, None)
        current = subprocess.run(
            ["gh", "api", "repos/4444J99/limen/git/ref/heads/main", "--jq", ".object.sha"],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
            env=read_environment,
        )
        if current.returncode != 0 or current.stdout.strip() != expected_sha:
            print(
                "FAIL: source main changed or could not be verified immediately before delivery; destination unchanged"
            )
            return 1
        environment = {**os.environ, "GH_TOKEN": minted.stdout.strip()}
        for key in ("GITHUB_TOKEN", "GITHUB_APP_PRIVATE_KEY", "SOURCE_GITHUB_TOKEN", SECRET_NAME):
            environment.pop(key, None)
        if not hydrate.gh_secret_set(TARGET, SECRET_NAME, candidate, env=environment):
            print("FAIL: verified UCC App principal could not write the target secret")
            return 1
    except Exception:  # noqa: BLE001 — no subprocess payload or exception may expose credentials
        print("FAIL: credential delivery transport unavailable; inspect only sanitized owner receipts")
        return 1
    print("PASS: UCC secret delivered; UCC resource/write preflight and deployment remain required")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
