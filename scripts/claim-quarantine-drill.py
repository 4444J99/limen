#!/usr/bin/env python3
"""Run the hermetic W07 false-claim quarantine drill against synthetic surfaces."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "scripts" / "claim-policy.py"
QUARANTINE = ROOT / "scripts" / "claim-surface-quarantine.py"


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    fixture = args.fixture_dir.resolve()
    claims = fixture / "claims.json"
    manifest = fixture / "public-surfaces.json"
    generated = fixture / "generated"
    if not claims.is_file() or not manifest.is_file() or not generated.is_dir():
        print("claim-quarantine-drill: FAIL: incomplete synthetic fixture", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="limen-claim-drill-") as temporary:
        stage = Path(temporary)
        source = stage / "generated"
        output = stage / "quarantined"
        report = stage / "policy-report.json"
        shutil.copytree(generated, source)
        policy = _run([
            sys.executable, str(POLICY), "--claims", str(claims), "--as-of", "2026-08-10T00:00:00Z", "--report", str(report)
        ])
        if policy.returncode != 1:
            print("claim-quarantine-drill: FAIL: synthetic false claim was not quarantined", file=sys.stderr)
            return 1
        quarantine = _run([
            sys.executable, str(QUARANTINE), "--source-root", str(source), "--output-root", str(output),
            "--manifest", str(manifest), "--policy-report", str(report)
        ])
        if quarantine.returncode != 0:
            print("claim-quarantine-drill: FAIL: quarantine staging did not complete", file=sys.stderr)
            return 1
        manifest_doc = json.loads(manifest.read_text(encoding="utf-8"))
        for surface in manifest_doc["surfaces"]:
            relative = Path(surface["path"])
            text = (output / relative).read_text(encoding="utf-8")
            if "SYNTHETIC FALSE CLAIM" in text or "positioning-claim: claim.synthetic.false:start" in text:
                print(f"claim-quarantine-drill: FAIL: claim remains in {relative}", file=sys.stderr)
                return 1
            if "positioning-claim: claim.synthetic.false:quarantined" not in text:
                print(f"claim-quarantine-drill: FAIL: missing quarantine marker in {relative}", file=sys.stderr)
                return 1
        result = {
            "schema_version": "limen.positioning.claim-quarantine-drill.v1",
            "fixture": "synthetic_false_claim",
            "public_surface_count": len(manifest_doc["surfaces"]),
            "publication_effect": "none",
            "restoration_criteria": "a corrected public claim export passes policy before staged regeneration",
        }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    print(
        f"claim-quarantine-drill: PASS ({result['public_surface_count']} generated public surface(s) quarantined)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
