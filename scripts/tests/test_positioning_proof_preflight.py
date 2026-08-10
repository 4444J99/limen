import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/positioning-proof-preflight.py"
SPEC = importlib.util.spec_from_file_location("positioning_proof_preflight", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PositioningProofPreflightTest(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = MODULE.load_contract(MODULE.DEFAULT_CONTRACT)

    def test_tracked_contract_is_valid(self) -> None:
        self.assertEqual([], MODULE.validate(self.contract))

    def test_missing_observation_date_fails_closed(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["sources"][0].pop("observed_at")
        self.assertIn("source limen_exact_head has no observation date", MODULE.validate(changed))

    def test_publication_and_outreach_states_are_rejected(self) -> None:
        changed = json.loads(json.dumps(self.contract))
        changed["status"] = "DONE"
        changed["external_validation"]["status"] = "outreach_started"
        errors = MODULE.validate(changed)
        self.assertIn("status must remain PREPARED/PREFLIGHT", errors)
        self.assertIn("external validation must remain rubric-only/no-outreach", errors)

    def test_resolver_withholds_all_preflight_claims(self) -> None:
        claims = MODULE.resolve_claims(self.contract)
        self.assertEqual(3, len(claims))
        self.assertTrue(all(not claim["publishable"] for claim in claims))
        self.assertTrue(all(claim["observation_dates"] for claim in claims))

    def test_surface_audit_has_an_explicit_denominator(self) -> None:
        rows = MODULE.build_surface_audit_skeleton(self.contract)
        surface_count = len(self.contract["surface_audit_model"]["surfaces"])
        self.assertEqual(surface_count * len(self.contract["flagships"]), len(rows))
        self.assertTrue(all(row["canonical_or_drift"] == "not_audited" for row in rows))


if __name__ == "__main__":
    unittest.main()
