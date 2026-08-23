#!/usr/bin/env python3
"""Read-only aggregate predicate for the tracked universe-recovery manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.universe_recovery import UniverseRecoveryManifestV1, evaluate_recovery  # noqa: E402


DEFAULT_MANIFEST = ROOT / "docs" / "continuations" / "universe-recovery-20260823" / "manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate universe-recovery denominators and receipts")
    parser.add_argument("--check", action="store_true", help="read-only validation; no repair or effect is available")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    if not args.check:
        parser.error("--check is required; this predicate has no mutation mode")
    try:
        raw = json.loads(args.manifest.read_text(encoding="utf-8"))
        manifest = UniverseRecoveryManifestV1.model_validate(raw)
        result = evaluate_recovery(manifest)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema_version": "limen.universe_recovery_evaluation.v1", "ok": False, "error": str(exc)}))
        return 1
    print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
    return 0 if result.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
