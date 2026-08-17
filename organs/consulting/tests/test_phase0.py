from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / "organs/consulting/validate-phase0.py"
PACKET_PATH = ROOT / "organs/consulting/prospects/bbnc/phase-0/preparation.json"

SPEC = importlib.util.spec_from_file_location("validate_phase0", VALIDATOR_PATH)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def packet() -> dict:
    return json.loads(PACKET_PATH.read_text(encoding="utf-8"))


def digest(seed: str) -> str:
    return "sha256:" + (seed.encode().hex() + "0" * 64)[:64]


def authority_receipt(preparation: dict) -> dict:
    return {
        "schema": "bbnc.phase0.authority-receipt.v1",
        "engagement_id": preparation["engagement_id"],
        "authority_owner": "BBNC",
        "delivery_party": "Padavano",
        "preparation_digest": VALIDATOR.canonical_digest(preparation),
        "charter_digest": digest("charter"),
        "executed_at": "2026-07-22T18:00:00Z",
        "effective_at": "2026-07-23T00:00:00Z",
        "accepted_work_package": "phase-1-current-state-discovery",
        "grants": {
            "phase_1_discovery": True,
            "production_access": False,
            "repository_creation": False,
            "public_launch": False,
            "later_work_packages": False,
        },
        "roles": [
            {"role_id": role_id, "principal_ref": f"bbnc-role:{role_id}"}
            for role_id in sorted(VALIDATOR.REQUIRED_ROLES)
        ],
        "gates": [
            {
                "gate_id": gate_id,
                "state": "passed",
                "owner_ref": f"bbnc-gate-owner:{gate_id}",
                "evidence_digest": digest(gate_id),
            }
            for gate_id in sorted(VALIDATOR.REQUIRED_GATES)
        ],
        "delivery_accounts": [
            {
                "account_id": account_id,
                "owner": "BBNC",
                "evidence_digest": digest(account_id),
            }
            for account_id in sorted(VALIDATOR.REQUIRED_ACCOUNTS)
        ],
        "signatures_verified": True,
        "verification": {
            "verified_by_role": "legal_compliance_owner",
            "verified_at": "2026-07-22T18:05:00Z",
        },
    }


class Phase0ValidationTests(unittest.TestCase):
    def test_current_preparation_is_workshop_ready(self) -> None:
        self.assertEqual(VALIDATOR.validate_preparation(packet()), [])

    def test_preparation_cannot_stand_in_for_authority(self) -> None:
        errors = VALIDATOR.validate_authority_receipt(packet(), None)
        self.assertIn("BBNC-owned Phase 0 authority receipt is required", errors)

    def test_vendor_authority_claim_fails_closed(self) -> None:
        candidate = copy.deepcopy(packet())
        candidate["delivery_party"]["has_bbnc_authority"] = True
        errors = VALIDATOR.validate_preparation(candidate)
        self.assertIn("delivery_party.has_bbnc_authority must be false", errors)

    def test_synthetic_bbnc_receipt_authorizes_phase_1_only(self) -> None:
        preparation = packet()
        receipt = authority_receipt(preparation)
        self.assertEqual(
            VALIDATOR.validate_authority_receipt(preparation, receipt), []
        )

    def test_open_gate_rejects_authority_receipt(self) -> None:
        preparation = packet()
        receipt = authority_receipt(preparation)
        receipt["gates"][0]["state"] = "open"
        errors = VALIDATOR.validate_authority_receipt(preparation, receipt)
        self.assertTrue(any("must be passed" in error for error in errors))

    def test_expanded_grant_rejects_authority_receipt(self) -> None:
        preparation = packet()
        receipt = authority_receipt(preparation)
        receipt["grants"]["production_access"] = True
        errors = VALIDATOR.validate_authority_receipt(preparation, receipt)
        self.assertIn(
            "receipt grants must authorize Phase 1 discovery only", errors
        )


if __name__ == "__main__":
    unittest.main()
