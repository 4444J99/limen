#!/usr/bin/env python3
"""preflight-receipt.py — mint the proof-of-observation receipt an outbound action requires.

The producer half of the outbound gate. `scripts/hooks/outbound-preflight-guard.py` is the
enforcer; `institutio/governance/outbound-effectors.yaml` is the registry that binds an effector
to its ground-truth predicate.

    python3 scripts/preflight-receipt.py --action mail.send --target someone@example.com

Runs the registry's predicate FOR REAL (bounded, process-group-killed on timeout) via
cli/src/limen/omega_owner_receipt.run_owner_predicate, streams its output so the operator/agent
actually SEES what the server said, and writes a content-free receipt to
logs/preflight-receipts/<action>.<target-digest>.json.

The receipt records `predicate_digest` — a SHA-256 of the exact predicate string, target
substituted. That is what makes it unforgeable in the only way that matters here: a receipt
minted for one recipient can never satisfy a send to a different recipient, and a receipt minted
for a different check can never satisfy this one. Combined with `max_age_seconds`, there is no
path from "I believe I looked" to "the gate opens".

Exit code mirrors the predicate: 0 PASS · 1 FAIL · 77 SKIP. Only PASS opens the gate.

PII: the recipient is hashed into the receipt filename and never written into the payload — the
receipt stores digests of evidence, never evidence (omega_owner_receipt's founding property).
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
REGISTRY = Path(
    os.environ.get("LIMEN_OUTBOUND_REGISTRY") or ROOT / "institutio" / "governance" / "outbound-effectors.yaml"
)

sys.path.insert(0, str(ROOT / "cli" / "src"))


def target_digest(value: str) -> str:
    """MUST match scripts/hooks/outbound-preflight-guard.py._target_digest — the hermetic test
    asserts the round trip, so a drift here fails outbound-preflight-guard.test.sh."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:16]


def resolve(action_id: str, target: str) -> tuple[str, str, Path, int]:
    """(rung_id, predicate, receipt_path, timeout) for one (action, target) pair."""
    import yaml

    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    effectors = registry.get("effectors") or {}
    if action_id not in effectors:
        known = ", ".join(sorted(effectors)) or "(none)"
        raise SystemExit(f"preflight-receipt: unknown action '{action_id}'. Declared: {known}")
    spec = effectors[action_id]
    receipts_dir = ROOT / (registry.get("receipts_dir") or "logs/preflight-receipts")
    rung_id = f"{action_id}.{target_digest(target)}".lower()
    predicate = str(spec.get("predicate") or "").replace("{target}", target.strip())
    timeout = int(spec.get("timeout_seconds") or 120)
    return rung_id, predicate, receipts_dir / f"{rung_id}.json", timeout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--action", required=True, help="effector id from outbound-effectors.yaml")
    parser.add_argument("--target", required=True, help="the recipient / thread this action is aimed at")
    args = parser.parse_args()

    from limen.omega_owner_receipt import run_owner_predicate

    rung_id, predicate, receipt_path, timeout = resolve(args.action, args.target)
    print(f"preflight-receipt: running the ground-truth check for {args.action}")
    print(f"  $ {predicate}")
    print("")

    exit_code, stdout, stderr, receipt = run_owner_predicate(
        root=ROOT,
        rung_id=rung_id,
        predicate=predicate,
        receipt_path=receipt_path,
        timeout_seconds=timeout,
    )
    # Stream the predicate's own words through — the whole point is that the decision is made
    # holding what the server said, not a summary of it.
    sys.stdout.write(stdout.decode("utf-8", "replace"))
    sys.stderr.write(stderr.decode("utf-8", "replace"))

    print("")
    print(f"preflight-receipt: {receipt.status} -> {receipt_path.relative_to(ROOT)}")
    if receipt.status != "PASS":
        print("  The gate stays CLOSED. Only a PASS receipt opens it — resolve the finding above,")
        print("  then re-run this command.")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
