#!/usr/bin/env python3
"""Wrap the canonical dry-run reclaimer in a frozen-wave census receipt."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.alpha_omega import (
    ReclaimCensusReceiptV1,
    frozen_wave_digest,
    load_frozen_wave,
)
from limen.protected_exclusions import ProtectedExclusionRegistry


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
    parser.add_argument("--repository-root", type=Path, default=ROOT)
    parser.add_argument("--frozen-wave", type=Path, required=True)
    parser.add_argument(
        "--protected-registry",
        type=Path,
        default=ROOT / "institutio" / "governance" / "reconciliation-protected-exclusions.json",
    )
    parser.add_argument("--max-seconds", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args(argv)
    try:
        if not 30 <= arguments.max_seconds <= 1800:
            raise ValueError("--max-seconds must be between 30 and 1800")
        repository_root = arguments.repository_root.expanduser().resolve(strict=True)
        wave = load_frozen_wave(arguments.frozen_wave)
        wave_sha256 = frozen_wave_digest(wave)
        protected = ProtectedExclusionRegistry.load(
            repository_root,
            arguments.protected_registry,
        )
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "reclaim-worktrees.py"),
                    "--check",
                    "--json",
                    "--repository-root",
                    str(repository_root),
                ],
                cwd=repository_root,
                capture_output=True,
                text=True,
                check=False,
                timeout=arguments.max_seconds,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            receipt = ReclaimCensusReceiptV1(
                observed_at=datetime.now(UTC),
                frozen_wave_sha256=wave_sha256,
                plan_sha256=None,
                protected_registry_digest=protected.registry_digest,
                scanned_count=0,
                candidate_count=None,
                deferred_count=0,
                failure_count=1,
                complete=False,
            )
            _write_json(arguments.output, receipt.model_dump(mode="json"))
            print(
                json.dumps(
                    {
                        "schema": "limen.prima_materia_reclaim_census_run.v1",
                        "complete": False,
                        "candidate_count": None,
                        "plan_sha256": None,
                        "reason": "canonical-census-timeout",
                    },
                    sort_keys=True,
                )
            )
            return 1
        if result.returncode != 0:
            raise ValueError("canonical reclaim census failed")
        payload = json.loads(result.stdout)
        manifest = payload.get("candidate_manifest")
        if (
            not isinstance(payload, dict)
            or not isinstance(manifest, dict)
            or manifest.get("schema") != "limen.worktree_reclaim_plan.v1"
            or manifest.get("protected_exclusion_registry_digest") != protected.registry_digest
        ):
            raise ValueError("canonical reclaim census is not plan-bound")
        failed = payload.get("failed")
        deferred = payload.get("deferred_over_cap")
        candidates = manifest.get("candidates")
        if not isinstance(failed, list) or not isinstance(deferred, list) or not isinstance(candidates, list):
            raise TypeError("canonical reclaim census has an invalid shape")
        complete = not failed and not deferred
        receipt = ReclaimCensusReceiptV1(
            observed_at=datetime.now(UTC),
            frozen_wave_sha256=wave_sha256,
            plan_sha256=str(payload.get("plan_sha256") or ""),
            protected_registry_digest=protected.registry_digest,
            scanned_count=int(payload.get("scanned") or 0),
            candidate_count=len(candidates) if complete else None,
            deferred_count=len(deferred),
            failure_count=len(failed),
            complete=complete,
        )
        _write_json(arguments.output, receipt.model_dump(mode="json"))
    except (
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        print(f"prima-materia-reclaim-census: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "schema": "limen.prima_materia_reclaim_census_run.v1",
                "complete": receipt.complete,
                "candidate_count": receipt.candidate_count,
                "plan_sha256": receipt.plan_sha256,
            },
            sort_keys=True,
        )
    )
    return 0 if receipt.complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
