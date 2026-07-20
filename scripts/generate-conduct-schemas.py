#!/usr/bin/env python3
"""Generate the portable JSON Schemas consumed by the Worker and relay lanes."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.conduct.models import (  # noqa: E402
    ConductorSessionV1,
    LeaseV1,
    RunReceiptV1,
    WorkPacketV1,
)


MODELS = {
    "conductor-session-v1.schema.json": ConductorSessionV1,
    "work-packet-v1.schema.json": WorkPacketV1,
    "lease-v1.schema.json": LeaseV1,
    "run-receipt-v1.schema.json": RunReceiptV1,
}


def main() -> int:
    destination = ROOT / "spec" / "contracts" / "conduct"
    destination.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema(mode="validation")
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}
        (destination / name).write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
