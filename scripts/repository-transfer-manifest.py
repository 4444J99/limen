#!/usr/bin/env python3
"""Capture or verify the private Limen repository-transfer manifest."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.repository_identity import LIMEN_REPOSITORY_IDENTITY  # noqa: E402
from limen.repository_transfer import (  # noqa: E402
    GhClient,
    TransferCaptureError,
    build_manifest,
    canonical_sha256,
    compare_manifests,
    create_verified_bundle,
    public_receipt,
    verify_existing_bundle,
)


def _named_path(raw: str) -> tuple[str, Path]:
    if "=" not in raw:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    name, path = raw.split("=", 1)
    if not name or not path:
        raise argparse.ArgumentTypeError("expected nonblank NAME=PATH")
    return name, Path(path).expanduser().resolve()


def _require_private(path: Path) -> None:
    if ".limen-private" not in path.resolve().parts:
        raise TransferCaptureError("full transfer manifest and bundle must remain under .limen-private")


def _write_text(path: Path, value: str, *, private: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(value, encoding="utf-8")
        if private:
            temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, value: object, *, private: bool) -> None:
    _write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n", private=private)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=LIMEN_REPOSITORY_IDENTITY.canonical_coordinate)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--existing-bundle", type=Path)
    parser.add_argument("--public-receipt", type=Path)
    parser.add_argument("--verify-against", type=Path)
    parser.add_argument("--protected-attribution", type=Path)
    parser.add_argument("--protected-checkout", action="append", default=[], type=_named_path)
    parser.add_argument("--protected-path", action="append", default=[], type=_named_path)
    args = parser.parse_args()

    try:
        output = args.output.expanduser().resolve()
        _require_private(output)
        if args.bundle and args.existing_bundle:
            raise TransferCaptureError("choose --bundle or --existing-bundle, not both")
        if not args.bundle and not args.existing_bundle:
            raise TransferCaptureError("transfer manifest requires --bundle or --existing-bundle")
        bundle_path = args.bundle.expanduser().resolve() if args.bundle else None
        existing_bundle = args.existing_bundle.expanduser().resolve() if args.existing_bundle else None
        public_path = args.public_receipt.expanduser().resolve() if args.public_receipt else None
        baseline_path = args.verify_against.expanduser().resolve() if args.verify_against else None
        attribution_path = args.protected_attribution.expanduser().resolve() if args.protected_attribution else None
        if bundle_path is not None:
            _require_private(bundle_path)
        if existing_bundle is not None:
            _require_private(existing_bundle)
        if baseline_path is not None:
            _require_private(baseline_path)
        if attribution_path is not None:
            _require_private(attribution_path)
            if baseline_path is None:
                raise TransferCaptureError("protected attribution requires --verify-against")
        artifacts = [
            value
            for value in (output, bundle_path, existing_bundle, public_path, baseline_path, attribution_path)
            if value is not None
        ]
        artifacts.extend(
            value.with_suffix(value.suffix + ".sha256") for value in (output, baseline_path) if value is not None
        )
        if len(artifacts) != len(set(artifacts)):
            raise TransferCaptureError("transfer artifact paths must be pairwise distinct")
        before = json.loads(baseline_path.read_text()) if baseline_path is not None else None
        if before is not None:
            baseline_sidecar = baseline_path.with_suffix(baseline_path.suffix + ".sha256")
            if not baseline_sidecar.is_file() or baseline_sidecar.read_text().strip() != canonical_sha256(before):
                raise TransferCaptureError("verification baseline content digest is absent or invalid")
        attribution = json.loads(attribution_path.read_text()) if attribution_path is not None else None
        bundle = (
            create_verified_bundle(args.repo, bundle_path)
            if bundle_path
            else verify_existing_bundle(existing_bundle)
            if existing_bundle
            else None
        )
        manifest = build_manifest(
            client=GhClient(),
            identity=LIMEN_REPOSITORY_IDENTITY,
            coordinate=args.repo,
            checkouts=dict(args.protected_checkout),
            protected_paths=dict(args.protected_path),
            bundle=bundle,
        )
        digest = canonical_sha256(manifest)
        _write_json(output, manifest, private=True)
        _write_text(output.with_suffix(output.suffix + ".sha256"), digest + "\n", private=True)

        if before is not None:
            failures = compare_manifests(before, manifest, protected_attribution=attribution)
            if failures:
                for failure in failures:
                    print(f"repository-transfer-manifest: FAIL: {failure}", file=sys.stderr)
                return 1

        if public_path is not None:
            _write_json(public_path, public_receipt(manifest, digest), private=False)
        print(f"repository-transfer-manifest: PASS sha256={digest}")
        return 0
    except (OSError, ValueError, TransferCaptureError, json.JSONDecodeError) as exc:
        print(f"repository-transfer-manifest: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
