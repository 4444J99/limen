from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
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
                "frontdoor_summary": "An inspectable system.",
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
    assert "Solves —" not in rendered
    assert "https://github.com/organvm/limen/blob/main/docs/positioning/example.md" in rendered


def test_profile_generator_refuses_forbidden_overclaim(tmp_path: Path):
    out = tmp_path / "out"
    assets = out / "assets"
    assets.mkdir(parents=True)
    (assets / "stats-manifest.json").write_text(json.dumps({"display_name": "Example", "stats": {}}))
    seeds = tmp_path / "seeds.json"
    seeds.write_text(
        json.dumps(
            {
                "repos": {
                    "organvm/example": {
                        "display_name": "Example",
                        "product_state": "Top 1% platform with paying customers.",
                    }
                }
            }
        )
    )
    value_repos = tmp_path / "value-repos.json"
    value_repos.write_text(json.dumps({"repos": ["organvm/example"]}))

    result = subprocess.run(
        [
            sys.executable,
            str(SYNC_README),
            "--out",
            str(out),
            "--seeds",
            str(seeds),
            "--value-repos",
            str(value_repos),
        ],
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "unreproducible-ranking" in result.stderr
    assert not (out / "README.md").exists()
