from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SYNC_README = ROOT / "scripts" / "sync-readme.py"


def _load():
    spec = importlib.util.spec_from_file_location("sync_readme_uut", SYNC_README)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_profile_renderer_emits_maturity_and_verified_proof_without_raw_dicts():
    mod = _load()
    positioning = mod._load_positioning()
    repo = "organvm/example"
    manifest = {
        "display_name": "Example Builder",
        "generated": "2026-08-10",
        "stats": {
            "ecosystem_public_repos": {"value": 10, "attest": "api"},
            "ecosystem_original_repos": {"value": 8, "attest": "api"},
            "contributions_last_year": {"value": 100, "attest": "api"},
        },
    }
    seeds = {
        "frontdoor": {
            "authorship": ("Architected and directed by one person through a governed, multi-agent production system.")
        },
        "repos": {
            repo: {
                "display_name": "Example System",
                "what_it_is": "An inspectable system.",
                "product_state": "Working prototype; deployment unvalidated.",
                "proof_signals": [
                    {"claim": "four collectors implemented", "status": "verified"},
                    {"claim": "3,399 tests", "status": "repository-asserted"},
                ],
                "cta_client": "Inspect it",
            }
        },
    }

    rendered = mod.render_readme(manifest, seeds, None, [repo], set(), positioning)

    assert "Current state:** Working prototype; deployment unvalidated" in rendered
    assert "verified: four collectors implemented" in rendered
    assert "3,399 tests" not in rendered
    assert "{'claim':" not in rendered
    assert "Architected and directed by one person" in rendered
    assert "https://github.com/organvm/limen/blob/main/docs/positioning/example.md" in rendered
