from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "positioning_claims.py"
FIXTURE = ROOT / "cli" / "tests" / "fixtures" / "positioning-claims" / "forbidden-overclaims.md"


def _load():
    spec = importlib.util.spec_from_file_location("positioning_claims_uut", MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_forbidden_overclaims_fixture_covers_the_truth_contract():
    claims = _load()

    assert claims.public_claim_violations(FIXTURE.read_text()) == [
        "unreproducible-ranking",
        "unsupported-product-count",
        "manual-only-authorship",
        "unsupported-daily-adoption",
        "unsupported-commercial-proof",
        "unsupported-executive-title",
        "unsupported-implemented-coverage",
        "unsupported-live-deployment",
        "unsupported-collection-scale",
        "unsupported-lead-delivery",
        "unsupported-employment-outcome",
    ]


def test_reconciled_inbound_doctrine_contains_no_forbidden_public_claim():
    claims = _load()
    inbound = (ROOT / "docs" / "inbound-magnet-system.md").read_text()

    assert claims.public_claim_violations(inbound) == []
