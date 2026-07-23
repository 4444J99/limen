from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "done-insight-cadence.sh"


def test_done_insight_cadence_uses_retained_sandbox_not_live_log_reset() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "LIMEN_INSIGHT_CADENCE_VERIFY_ROOT" in text
    assert "Verification sandbox retained" in text
    assert "rm -rf" not in text
    assert "rm -f" not in text
    assert 'python3 "$TOOL"' in text
