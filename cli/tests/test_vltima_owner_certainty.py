from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vltima-owner-certainty.py"


def _load(name: str = "vltima_owner_certainty_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _claim(**overrides):
    claim = {
        "id": "session-attack-paths:attack_coverage:local_pressure_bytes",
        "surface": "session-attack-paths",
        "lane": "priority-routing",
        "authority": "current_doctrine",
        "trust": "high",
        "freshness": "fresh",
        "source_status": "current",
        "subject": "local_pressure_bytes",
        "summary": "local_pressure_bytes = 1",
        "next_action": "rank the next bounded packet",
        "evidence_label": ".limen-private/session-corpus/lifecycle/session-attack-paths.json",
    }
    claim.update(overrides)
    return claim


def test_current_claim_with_lane_owner_becomes_packet_candidate() -> None:
    owner = _load("vltima_owner_current")

    item = owner.classify_owner_claim(_claim())

    assert item["owner"] == "limen:priority-routing"
    assert item["owner_status"] == "owned_current"
    assert item["action_level"] == "packet_candidate"
    assert item["dispatchable"] is True


def test_missing_owner_signal_becomes_unowned_ore() -> None:
    owner = _load("vltima_owner_unowned")

    item = owner.classify_owner_claim(
        _claim(surface="", lane="", evidence_label="", authority="dormant_ore", source_status="tracked-only")
    )

    assert item["owner"] == ""
    assert item["owner_status"] == "unowned_ore"
    assert item["action_level"] == "not_dispatchable"
    assert item["dispatchable"] is False


def test_quarantined_claim_is_parked_even_when_owner_is_known() -> None:
    owner = _load("vltima_owner_quarantine")

    item = owner.classify_owner_claim(_claim(authority="quarantined_ghost", subject="auth_credentials"))

    assert item["owner"] == "limen:priority-routing"
    assert item["owner_status"] == "parked"
    assert item["action_level"] == "parked"
    assert item["dispatchable"] is False


def test_build_certainty_counts_unowned_dispatchable_as_zero(tmp_path: Path) -> None:
    owner = _load("vltima_owner_build")
    digest = tmp_path / "digest.json"
    digest.write_text(
        """
{
  "generated_at": "2026-07-06T00:00:00+00:00",
  "claims": [
    {
      "id": "x",
      "surface": "session-attack-paths",
      "lane": "priority-routing",
      "authority": "current_doctrine",
      "trust": "high",
      "freshness": "fresh",
      "source_status": "current",
      "subject": "x",
      "summary": "x",
      "next_action": "do x",
      "evidence_label": "fixture"
    }
  ]
}
""",
        encoding="utf-8",
    )

    certainty = owner.build_certainty(digest_path=digest, root=tmp_path, private_root=tmp_path / ".private")

    assert certainty["coverage"]["claim_count"] == 1
    assert certainty["coverage"]["owner_status_counts"] == {"owned_current": 1}
    assert certainty["coverage"]["unowned_dispatchable_count"] == 0

