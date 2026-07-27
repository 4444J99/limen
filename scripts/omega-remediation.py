#!/usr/bin/env python3
"""Validate and attach typed remediation metadata to strict-Omega output."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent)).resolve()
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.omega_remediation import (  # noqa: E402
    OmegaRemediationError,
    annotate_omega_stamp,
    load_omega_remediations,
    remediation_payload,
)


def _write_atomic(path: Path, payload: dict) -> None:
    data = (json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n").encode("ascii")
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _stamp_path(raw: Path) -> Path:
    logs = (ROOT / "logs").resolve()
    if raw.is_symlink() or raw.name != "omega.json" or raw.parent.resolve() != logs:
        raise OmegaRemediationError("Omega annotation target must be the real logs/omega.json")
    return raw.absolute()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="validate full remediation coverage")
    mode.add_argument("--json", action="store_true", help="emit materialized remediation contracts")
    mode.add_argument("--annotate", type=Path, help="atomically annotate logs/omega.json")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        rungs, remediations = load_omega_remediations(ROOT)
        if args.annotate is not None:
            stamp = _stamp_path(args.annotate)
            try:
                payload = json.loads(stamp.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise OmegaRemediationError(f"cannot read Omega stamp {stamp}: {exc}") from exc
            if not isinstance(payload, dict):
                raise OmegaRemediationError("Omega stamp must be an object")
            _write_atomic(stamp, annotate_omega_stamp(payload, rungs, remediations))
        elif args.json:
            print(
                json.dumps(
                    {
                        "rungs": [remediation_payload(remediations[rung.id]) for rung in rungs],
                        "schema": "limen.omega_remediations.v1",
                    },
                    ensure_ascii=True,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        elif not args.quiet:
            print(
                "omega-remediation: PASS — "
                f"{len(rungs)} rungs have typed owner, action, authority, value, and receipt contracts"
            )
    except OmegaRemediationError as exc:
        print(f"omega-remediation: FAIL — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
