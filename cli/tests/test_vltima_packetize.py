from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vltima-packetize.py"


def _load(name: str = "vltima_packetize_test"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _certainty():
    return {
        "generated_at": "2026-07-06T00:00:00+00:00",
        "coverage": {"claim_count": 2},
        "claims": [
            {
                "id": "claim-a",
                "owner": "limen:priority-routing",
                "owner_status": "owned_current",
                "action_level": "packet_candidate",
                "surface": "session-attack-paths",
                "subject": "local_pressure_bytes",
                "summary": "local pressure exists",
                "next_action": "write the bounded packet",
                "privacy_class": "public_redacted",
                "evidence_label": "fixture",
            },
            {
                "id": "claim-b",
                "owner": "",
                "owner_status": "unowned_ore",
                "action_level": "not_dispatchable",
                "surface": "",
                "subject": "old idea",
                "summary": "old idea",
                "next_action": "",
                "privacy_class": "public_redacted",
                "evidence_label": "fixture",
            },
        ],
    }


def test_packetize_only_owner_certified_current_claims() -> None:
    packetize = _load("vltima_packetize_candidates")

    packet_index = packetize.build_packets(_certainty())

    assert packet_index["coverage"]["packet_count"] == 1
    assert packet_index["coverage"]["candidate_claim_count"] == 1
    packet = packet_index["packets"][0]
    assert packet["owner"] == "limen:priority-routing"
    assert packet["enqueue"] is False
    assert packet["verification_command"] == "python3 scripts/vltima-organ.py --check"


def test_packetize_marks_destructive_or_secret_actions_human_gated() -> None:
    packetize = _load("vltima_packetize_human_gated")
    certainty = _certainty()
    certainty["claims"][0]["next_action"] = "delete stale secret material"

    packet_index = packetize.build_packets(certainty)

    assert packet_index["packets"][0]["mutation_level"] == "human_gated"


def test_render_markdown_preserves_non_dispatch_contract() -> None:
    packetize = _load("vltima_packetize_markdown")

    markdown = packetize.render_markdown(packetize.build_packets(_certainty()))

    assert "v1 never mutates `tasks.yaml`" in markdown
    assert "`candidate` is not `queued`" in markdown
    assert "VLTIMA-PACKET" in markdown

