#!/usr/bin/env python3
"""Refresh the PSP-P01-W05 public-surface preflight receipt from live truth.

This helper records the current public-surface state without fabricating URLs or
inventing merged-main truth. It is intentionally read-only with respect to
remote systems; it only emits a durable JSON receipt under docs/receipts/.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SURFACES_PATH = ROOT / "link-surfaces.json"
RECEIPTS_DIR = ROOT / "docs" / "receipts" / "psp-p01-w05-preflight"


def run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True).strip()


def head(ref: str) -> str:
    return run(["git", "ls-remote", ref, "HEAD"]).split()[0]


def probe(url: str) -> dict[str, object]:
    proc = subprocess.run(
        ["curl", "-I", "-L", "--max-time", "20", url],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    headers = proc.stdout.splitlines()
    status = None
    title = None
    for line in headers:
        if line.startswith("HTTP/"):
            try:
                status = int(line.split()[1])
            except Exception:
                pass
    return {
        "status": status,
        "title": title,
        "ok": proc.returncode == 0,
        "stderr": proc.stderr.strip() or None,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", help="override output path")
    args = ap.parse_args()

    surfaces = json.loads(SURFACES_PATH.read_text())["surfaces"]
    data = {
        "schema": "limen.psp_p01_w05_baseline_preflight.v1",
        "task": "PSP-P01-W05",
        "status": "PREFLIGHT",
        "captured_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "branch": run(["git", "branch", "--show-current"]),
        "repo_head": run(["git", "rev-parse", "HEAD"]),
        "candidate_state": {
            "source_branch": "feat/private-artifact-vault",
            "source_head": run(["git", "rev-parse", "feat/private-artifact-vault"]),
        },
        "public_surfaces": [],
        "selected_flagships": [
            {
                "name": "Limen",
                "repo": "organvm/limen",
                "repo_head": head("https://github.com/organvm/limen.git"),
                "surface_docs": ["docs/positioning/limen.md"],
            },
            {
                "name": "UCC Public-Records Intelligence Platform",
                "repo": "organvm/public-record-data-scrapper",
                "repo_head": head("https://github.com/organvm/public-record-data-scrapper.git"),
                "surface_docs": ["docs/positioning/public-record-data-scrapper.md"],
            },
            {
                "name": "AI Chat Exporter",
                "repo": "organvm/a-i-chat--exporter",
                "repo_head": head("https://github.com/organvm/a-i-chat--exporter.git"),
                "surface_docs": ["docs/positioning/a-i-chat--exporter.md"],
            },
        ],
        "verification": {
            "predicate": "python3 scripts/positioning-program.py --verify-work PSP-P01-W05",
            "not_run_reason": "refresh helper only",
        },
    }

    for surface in surfaces:
        ref = surface["ref"]
        entry = {"id": surface["id"], "ref": ref}
        if ref.startswith("https://"):
            entry["probe"] = probe(ref)
            entry["repo_head"] = head("https://github.com/organvm/4444J99.git") if surface["id"] == "profile-readme" else None
        else:
            entry["repo_head"] = head("https://github.com/organvm/4444J99.git")
        data["public_surfaces"].append(entry)

    out = Path(args.out) if args.out else RECEIPTS_DIR / f"refresh-{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    print(out)


if __name__ == "__main__":
    main()
