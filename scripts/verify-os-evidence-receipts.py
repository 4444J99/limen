#!/usr/bin/env python3
"""Resolve the existing redacted OS ledger's exact repository-qualified receipts."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli/src"))
from limen.operating_system_evidence import link_receipts, render  # noqa: E402


def resolve(url):
    _, _, _, owner, repo, kind, identity = url.split("/")
    endpoint = f"repos/{owner}/{repo}/" + ("pulls/" if kind == "pull" else "commits/") + identity
    query = (
        "{sha:.head.sha, state:.state, merged:.merged, merge_sha:.merge_commit_sha}" if kind == "pull" else "{sha:.sha}"
    )
    result = subprocess.run(
        ["gh", "api", endpoint, "--jq", query], capture_output=True, text=True, timeout=8, check=False
    )
    if result.returncode:
        raise ValueError("receipt_identity_unavailable")
    return json.loads(result.stdout)


def main():
    path = Path(sys.argv[1])
    public = link_receipts(json.loads(path.read_text()), resolve)
    path.write_text(json.dumps(public, indent=2) + "\n")
    path.with_suffix(".md").write_text(render(public))
    print(
        json.dumps(
            {
                "receipts": len(public["receipt_verifications"]),
                "unavailable": sum(row["status"] != "identity_verified" for row in public["receipt_verifications"]),
            }
        )
    )


if __name__ == "__main__":
    main()
