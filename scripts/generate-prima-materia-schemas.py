#!/usr/bin/env python3
"""Generate portable Prima Materia JSON Schemas."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.prima_materia import (
    ActionReceiptV1,
    CompositionManifestV1,
    CustodyReceiptV1,
    PrimaMateriaEventV1,
    SourceAdapterV1,
    SourceCoverageV1,
    StandingAuthorityV1,
    TransformRecipeV1,
)

MODELS = {
    "prima-materia-event-v1.schema.json": PrimaMateriaEventV1,
    "source-adapter-v1.schema.json": SourceAdapterV1,
    "transform-recipe-v1.schema.json": TransformRecipeV1,
    "action-receipt-v1.schema.json": ActionReceiptV1,
    "custody-receipt-v1.schema.json": CustodyReceiptV1,
    "composition-manifest-v1.schema.json": CompositionManifestV1,
    "standing-authority-v1.schema.json": StandingAuthorityV1,
    "source-coverage-v1.schema.json": SourceCoverageV1,
}


def main() -> int:
    destination = ROOT / "spec" / "contracts" / "prima-materia"
    destination.mkdir(parents=True, exist_ok=True)
    for name, model in MODELS.items():
        schema = model.model_json_schema(mode="validation")
        schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema}
        (destination / name).write_text(
            json.dumps(schema, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
