"""Contracts for lane-neutral reserved-tier accounting.

Fixtures, never host state: the live indexes are gitignored and absent in CI, and a
gate that silently passes because its input is missing is the exact defect this
check exists to name.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-reserved-tier.py"


def _load(monkeypatch, root: Path):
    """Import the script fresh — its path constants are resolved at module load."""
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_VENDOR_INSIGHTS_DIR", str(root / "logs" / "vendor-insights"))
    monkeypatch.setenv("LIMEN_FABLE_RECEIPTS_DIR", str(root / "logs" / "fable-acceptance"))
    spec = importlib.util.spec_from_file_location("check_reserved_tier_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _write_index(root: Path, lane: str, sessions: list[dict], *, total_in_window: int | None = None) -> None:
    d = root / "logs" / "vendor-insights" / lane
    d.mkdir(parents=True, exist_ok=True)
    meta = {
        "total_in_window": len(sessions) if total_in_window is None else total_in_window,
        "shown": len(sessions),
        "capped": total_in_window is not None and total_in_window > len(sessions),
    }
    (d / "index.json").write_text(json.dumps({"meta": meta, "sessions": sessions}))


def _write_receipt(root: Path, created_at: str, slug: str = "run") -> None:
    d = root / "logs" / "fable-acceptance"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{slug}.json").write_text(json.dumps({"created_at": created_at, "slug": slug}))


def _baseline(root: Path, lanes: list[str]) -> None:
    p = root / "institutio" / "governance"
    p.mkdir(parents=True, exist_ok=True)
    (p / "reserved-tier-blind-baseline.txt").write_text("# header\n" + "\n".join(lanes) + "\n")


def test_a_non_claude_lane_on_a_reserved_tier_without_acceptance_fails(tmp_path, monkeypatch, capsys):
    """The whole point: the rule was enforced Claude-lane-only, and copilot burned Fable."""
    _write_index(
        tmp_path,
        "copilot",
        [{"id": "s1", "models": ["claude-fable-5"], "started_at": "2026-08-12T01:50:48Z"}],
    )
    module = _load(monkeypatch, tmp_path)

    rc = module.main([])

    assert rc == 1
    out = capsys.readouterr().out
    assert "copilot/s1" in out
    assert "no covering acceptance receipt" in out


def test_a_receipt_written_before_the_run_covers_it(tmp_path, monkeypatch, capsys):
    _write_receipt(tmp_path, "2026-08-11T00:00:00Z")
    _write_index(
        tmp_path,
        "copilot",
        [{"id": "s1", "models": ["claude-fable-5"], "started_at": "2026-08-12T01:50:48Z"}],
    )
    module = _load(monkeypatch, tmp_path)

    assert module.main([]) == 0
    assert "accepted=1" in capsys.readouterr().out


def test_a_receipt_written_after_the_run_does_not_cover_it(tmp_path, monkeypatch):
    """Acceptance is written BEFORE the run; retroactive approval is not acceptance."""
    _write_receipt(tmp_path, "2026-08-20T00:00:00Z")
    _write_index(
        tmp_path,
        "copilot",
        [{"id": "s1", "models": ["claude-fable-5"], "started_at": "2026-08-12T01:50:48Z"}],
    )
    module = _load(monkeypatch, tmp_path)

    assert module.main([]) == 1


def test_a_run_with_no_start_time_is_not_treated_as_covered(tmp_path, monkeypatch):
    """Unprovable is not the same as fine — it cannot be shown to postdate any receipt."""
    _write_receipt(tmp_path, "2026-08-11T00:00:00Z")
    _write_index(tmp_path, "copilot", [{"id": "s1", "models": ["claude-fable-5"], "started_at": None}])
    module = _load(monkeypatch, tmp_path)

    assert module.main([]) == 1


def test_a_lane_with_no_model_identity_fails_rather_than_reading_as_clean(tmp_path, monkeypatch, capsys):
    """Green through absence: 'never used a reserved tier' and 'cannot say' must differ."""
    _write_index(tmp_path, "opencode", [{"id": "s1", "models": [], "started_at": "2026-08-12T00:00:00Z"}])
    module = _load(monkeypatch, tmp_path)

    rc = module.main([])

    out = capsys.readouterr().out
    assert rc == 1
    assert "records no model identity and is not baselined" in out
    assert "BLIND" in out


def test_a_baselined_blind_lane_passes_but_stays_visible(tmp_path, monkeypatch, capsys):
    _write_index(tmp_path, "opencode", [{"id": "s1", "models": [], "started_at": "2026-08-12T00:00:00Z"}])
    _baseline(tmp_path, ["opencode"])
    module = _load(monkeypatch, tmp_path)

    rc = module.main([])

    out = capsys.readouterr().out
    assert rc == 0
    assert "BLIND" in out, "baselining records the blindness; it must not hide it"
    assert "recorded, not forgiven" in out


def test_a_lane_that_regains_model_identity_fails_the_stale_baseline(tmp_path, monkeypatch, capsys):
    """Shrink-only: a stale line must fail, or the ratchet accumulates permission."""
    _write_index(
        tmp_path,
        "opencode",
        [{"id": "s1", "models": ["claude-sonnet-5"], "started_at": "2026-08-12T00:00:00Z"}],
    )
    _baseline(tmp_path, ["opencode"])
    module = _load(monkeypatch, tmp_path)

    rc = module.main([])

    assert rc == 1
    assert "baseline is shrink-only" in capsys.readouterr().out


def test_the_denominator_is_total_in_window_not_the_shown_sample(tmp_path, monkeypatch, capsys):
    """The antigravity index is capped 40 of 157 — a sample is not the corpus."""
    _write_index(
        tmp_path,
        "claude",
        [{"id": "s1", "models": ["claude-sonnet-5"], "started_at": "2026-08-12T00:00:00Z"}],
        total_in_window=54,
    )
    module = _load(monkeypatch, tmp_path)
    module.main([])

    out = capsys.readouterr().out
    assert "1 session(s) read of 54 in window" in out
    assert "CAPPED 1/54" in out


def test_a_clean_lane_passes(tmp_path, monkeypatch, capsys):
    _write_index(
        tmp_path,
        "codex",
        [{"id": "s1", "models": ["gpt-5.6-sol"], "started_at": "2026-08-12T00:00:00Z"}],
    )
    module = _load(monkeypatch, tmp_path)

    assert module.main([]) == 0
    assert "no unaccepted reserved-tier run in any lane" in capsys.readouterr().out


@pytest.mark.parametrize("tiers", ["claude-fable-5", "claude-fable-5,some-other-reserved-tier"])
def test_the_reserved_tier_set_is_configurable(tmp_path, monkeypatch, tiers):
    monkeypatch.setenv("LIMEN_RESERVED_TIERS", tiers)
    _write_index(
        tmp_path,
        "copilot",
        [{"id": "s1", "models": ["claude-fable-5"], "started_at": "2026-08-12T00:00:00Z"}],
    )
    module = _load(monkeypatch, tmp_path)

    assert module.main([]) == 1
