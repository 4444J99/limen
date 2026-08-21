#!/usr/bin/env python3
"""Run one bounded, operator-invoked cloud maintenance pass.

The runner hydrates authenticated board custody into an ephemeral file, suppresses
task-bearing subprocess output, and publishes only aggregate counts.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.conduct.client import client_from_env  # noqa: E402


def _board_payload(payload: dict[str, Any]) -> dict[str, Any]:
    board = payload.get("board") if isinstance(payload.get("board"), dict) else payload
    if not isinstance(board, dict) or not isinstance(board.get("tasks"), list):
        raise ValueError("authenticated keeper returned no canonical tasks array")
    return board


def _handoff_counts() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location("cloud_handoff_relay", ROOT / "scripts" / "handoff-relay.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("handoff relay could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    payload = module.build()
    admission = payload.get("dispatch_admission") or {}
    return {
        "keeper_available": bool(admission.get("keeper_available")),
        "open": int((payload.get("open_lanes") or {}).get("total_open") or 0),
        "in_flight": int((payload.get("in_flight_claims") or {}).get("count") or 0),
        "admissible": int(admission.get("admissible") or 0),
        "gated": int(admission.get("gated") or 0),
    }


def _summary_count(output: str, key: str) -> int:
    matches = re.findall(rf"(?:^|[ |]){re.escape(key)}=(\d+)(?=$|[ )|])", output)
    return int(matches[-1]) if matches else 0


def run(mode: str, receipt_path: Path, expected_sha: str) -> dict[str, Any]:
    client = client_from_env()
    capabilities = client.capabilities()
    before = _board_payload(client.private_board())
    with tempfile.TemporaryDirectory(prefix="limen-cloud-maintenance-") as temp_dir:
        custody = Path(temp_dir) / "private-board.yaml"
        custody.write_text(yaml.safe_dump(before, sort_keys=False), encoding="utf-8")
        command = [sys.executable, str(ROOT / "scripts" / "self-heal.py"), "--tasks", str(custody)]
        if mode == "dry-run":
            command.append("--dry-run")
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, "LIMEN_ROOT": str(ROOT)},
            text=True,
            capture_output=True,
            timeout=900,
            check=False,
        )
    combined = f"{completed.stdout}\n{completed.stderr}"
    after = _board_payload(client.private_board())
    statuses = collections.Counter(str(row.get("status") or "unknown") for row in after["tasks"])
    handoff = _handoff_counts()
    receipt = {
        "schema_version": "limen.cloud_maintenance_receipt.v1",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "mode": mode,
        "expected_sha": expected_sha,
        "head_sha": os.environ.get("GITHUB_SHA", ""),
        "conduct_preflight": bool(capabilities.get("schema_version")),
        "self_heal": {
            "exit_code": completed.returncode,
            "scan_success": completed.returncode == 0 and "BLOCKED" not in combined,
            "partition_skipped": _summary_count(combined, "partition-skipped"),
            "emitted": _summary_count(combined, "emitted"),
            "retired": _summary_count(combined, "retired"),
        },
        "board_counts": {
            "total": len(after["tasks"]),
            "by_status": dict(sorted(statuses.items())),
        },
        "handoff": handoff,
    }
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if completed.returncode != 0 or not handoff["keeper_available"]:
        raise RuntimeError("cloud maintenance pass failed; counts-only receipt was written")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dry-run", "apply"), required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    args = parser.parse_args()
    try:
        receipt = run(args.mode, args.receipt, args.expected_sha)
    except Exception as exc:
        print(f"cloud-maintenance: FAIL — {exc}", file=sys.stderr)
        return 1
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
