#!/usr/bin/env python3
"""Bounded source-bound Domus observation for the existing heartbeat."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli/src"))
from limen.runtime_maintenance_observation import observe  # noqa: E402


def main():
    try:
        manifest = json.loads((ROOT / "spec/runtime-maintenance-observation.json").read_text())
    except (OSError, ValueError):
        print(json.dumps({"status": "failed", "reason": "observation_contract_unavailable"}))
        return 78
    code, report = observe(Path.home(), manifest)
    print(json.dumps(report, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
