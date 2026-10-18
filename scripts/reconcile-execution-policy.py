#!/usr/bin/env python3
"""Reconcile one explicitly authorized outcome; never use a local empty projection."""

import argparse
import json
from pathlib import Path
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli/src"))
from limen.conduct.client import client_from_env
from limen.conduct.models import canonical_hash
from limen.dispatch import _load_limen_env
from limen.execution_policy import native_policy_record, policy_binding_for_runtime, reconcile_policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source", type=Path)
    source_group.add_argument("--native-record", type=Path)
    parser.add_argument("--record-line", type=int, default=257)
    parser.add_argument("--outcome", required=True)
    parser.add_argument("--work-key", required=True)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--install", action="store_true")
    args = parser.parse_args()
    _load_limen_env()
    receipt = {
        "schema": "limen.execution_policy_reconciliation.v1",
        "installed": False,
        "outcome": args.outcome,
        "work_key": args.work_key,
        "owner": args.owner,
    }
    try:
        client = client_from_env()
        live = client._request("GET", "/api/conduct/execution/policy")
        source = (
            native_policy_record(args.native_record, args.record_line)
            if args.native_record
            else json.loads(args.source.read_text())
        )
        candidate = reconcile_policy(source, live, outcome=args.outcome, work_key=args.work_key, owner=args.owner)
        receipt.update(
            prior_fingerprint=canonical_hash(source),
            candidate_fingerprint=canonical_hash(candidate),
            prior_runtime=live["runtime"],
            preserved_priorities=len(source["approved_priorities"]),
        )
        binding = policy_binding_for_runtime(candidate, live)
        receipt.update(
            binding_bytes=len(binding.encode("utf-8")),
            binding_encoding="gzip+base64" if json.loads(binding).get("encoding") == "gzip+base64" else "json",
        )
        if args.install and candidate != source:
            # Recheck immediately before installation; this route has no provider CAS.
            if client._request("GET", "/api/conduct/execution/policy") != live:
                raise ValueError("execution_policy_generation_changed")
            completed = subprocess.run(
                [
                    "bash",
                    "scripts/cf-wrangler.sh",
                    "secret",
                    "put",
                    "LIMEN_EXECUTION_POLICY",
                    "--config",
                    "web/worker/wrangler.toml",
                ],
                input=binding,
                text=True,
                capture_output=True,
                timeout=90,
                cwd=Path(__file__).resolve().parents[1],
                check=False,
            )
            if completed.returncode:
                raise ValueError("execution_policy_install_rejected")
            after = client._request("GET", "/api/conduct/execution/policy")
            if after.get("configuration_fingerprint") != canonical_hash(candidate):
                raise ValueError("execution_policy_install_readback_mismatch")
            receipt.update(installed=True, runtime=after["runtime"])
        receipt["status"] = "verified"
    except Exception as exc:
        # Provider exceptions can contain settings. Keep only fixed classification/status.
        receipt.update(
            status="blocked",
            gate=str(exc)
            if isinstance(exc, ValueError)
            else "execution_policy_readback_unavailable"
            if getattr(exc, "status", None) == 404
            else "owner_route_rejected",
            http_status=getattr(exc, "status", None),
        )
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt))
    return 0 if receipt["status"] == "verified" else 75


if __name__ == "__main__":
    raise SystemExit(main())
