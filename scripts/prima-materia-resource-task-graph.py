#!/usr/bin/env python3
"""Materialize concrete bounded observation claims for one frozen source wave."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from math import ceil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.alpha_omega import load_frozen_wave
from limen.prima_materia import ResourceClaimV1
from limen.prima_materia_store import SourceRegistry


def _opaque(prefix: str, value: str) -> str:
    return f"{prefix}{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frozen-wave", type=Path, required=True)
    parser.add_argument(
        "--source-registry",
        type=Path,
        default=ROOT / "institutio" / "governance" / "prima-materia-source-registry.json",
    )
    parser.add_argument("--horizon-seconds", type=int, default=900)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if not 30 <= arguments.horizon_seconds <= 86_400:
            raise ValueError("--horizon-seconds must be between 30 and 86400")
        wave = load_frozen_wave(arguments.frozen_wave)
        registry = SourceRegistry.load(arguments.source_registry)
        recipes = {adapter.source_id: adapter.claim_recipe for adapter in registry.adapters}
        observed_at = datetime.now(UTC)
        batch_count = ceil(len(wave.source_instances) / 3)
        slot_seconds = max(
            30,
            ceil(arguments.horizon_seconds / batch_count),
        )
        graph_end = observed_at + timedelta(seconds=batch_count * slot_seconds)
        claims = []
        for index, source in enumerate(wave.source_instances):
            recipe = recipes.get(source.source_id)
            if recipe is None:
                raise ValueError("frozen source instance has no resource-claim recipe")
            effective_from = observed_at + timedelta(
                seconds=(index // 3) * slot_seconds,
            )
            claim = ResourceClaimV1(
                claim_id=_opaque("claim", source.instance_id),
                source_instance_id=source.instance_id,
                operation_id=_opaque("observe", f"{recipe}\0{source.instance_id}"),
                hydrated_inputs_bytes=0,
                workspace_bytes=0,
                temporary_expansion_bytes=0,
                output_bytes=0,
                encryption_chunking_bytes=0,
                rollback_bytes=0,
                memory_bytes=64 * 1024**2,
                file_count=1,
                network_bytes=1024**2 if source.source_id == "gitEstateSource01" else 0,
                wall_time_seconds=slot_seconds,
                effective_from=effective_from,
                effective_until=effective_from + timedelta(seconds=slot_seconds),
                rollback_until=graph_end,
            )
            claims.append(claim)
        if not claims:
            raise ValueError("frozen wave contains no source instances")
        _write_json(
            arguments.output,
            {
                "schema": "limen.resource_task_graph.v1",
                "claims": [claim.model_dump(mode="json") for claim in sorted(claims, key=lambda item: item.claim_id)],
            },
        )
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"prima-materia-resource-task-graph: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "schema": "limen.prima_materia_resource_task_graph_run.v1",
                "claim_count": len(claims),
                "graph_horizon_seconds": batch_count * slot_seconds,
                "max_concurrency": 3,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
