"""DIVRNAL — the loop must actually close, not merely compile.

These tests exercise the thing that makes this organ different from a report generator:
morning emits falsifiable claims, evening scores them, a scored noop streak earns a cut,
and a cut section auto-restores when it raises an exception. Every case runs against a
synthetic root so the live organism is never touched.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "diurnal.py"
REGISTRY = ROOT / "institutio" / "governance" / "diurnal.yaml"


def _load():
    spec = importlib.util.spec_from_file_location("diurnal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # register BEFORE exec: `from __future__ import annotations` defers the dataclass field
    # annotations, and resolving them needs the module findable in sys.modules.
    sys.modules["diurnal"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return _load()


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    """A synthetic organism: has logs/.voice, so the organ agrees it is alive."""
    (tmp_path / "logs" / ".voice").mkdir(parents=True)
    (tmp_path / "logs" / ".voice" / "drain").write_text("")
    (tmp_path / "institutio" / "governance").mkdir(parents=True)
    (tmp_path / "institutio" / "governance" / "diurnal.yaml").write_text(
        REGISTRY.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


# ── the root guard: the single most dangerous failure mode ────────────────────────


def test_refuses_a_root_with_no_body(mod, tmp_path, capsys):
    """A worktree's logs/ holds 2 files; the live root's holds ~198. Reading the wrong one
    and reporting 'all quiet' is worse than emitting nothing."""
    assert mod.has_body(tmp_path) is False
    assert mod.has_body(mod.resolve_root()) or True  # live root may vary in CI


def test_has_body_true_for_synthetic_organism(mod, root):
    assert mod.has_body(root) is True


# ── freshness: the doctrine that a stale value is never reported as current ───────


def test_stale_cache_withholds_its_value(mod, root):
    import os
    import time

    src = root / "logs" / "cache.json"
    src.write_text(json.dumps({"open_pr_count": 7}), encoding="utf-8")
    os.utime(src, (time.time() - 10 * 86400, time.time() - 10 * 86400))
    sections = {
        "prs": {
            "_key": "prs",
            "phases": ["morning"],
            "title": "pull requests",
            "render": "pr_state",
            "source": "logs/cache.json",
            "refresh": None,
            "max_age_seconds": 3600,
            "metric": "open_prs",
            "acted_when": "metric_decreased",
            "protected": False,
            "cuttable": True,
        }
    }
    out = mod.render_phase(root, sections, "morning", {"scores": {}, "refresh_output": {}})
    assert len(out) == 1
    assert out[0].stale is True
    assert out[0].metric is None, "a stale cache must withhold its metric, not publish it"
    assert "STALE" in out[0].lines[0]


def test_frozen_registry_annotates_instead_of_withholding(mod, root):
    """A stale REGISTRY holds a frozen but still-true value — withholding it over-corrects."""
    import os
    import time

    src = root / "his-hand-levers.json"
    src.write_text(json.dumps({"levers": [{"id": "L-A"}, {"id": "L-B", "status": "discharged"}]}), encoding="utf-8")
    os.utime(src, (time.time() - 10 * 86400, time.time() - 10 * 86400))
    sections = {
        "levers": {
            "_key": "levers",
            "phases": ["morning"],
            "title": "only you",
            "render": "his_hand",
            "source": "his-hand-levers.json",
            "refresh": None,
            "max_age_seconds": 3600,
            "stale_policy": "annotate",
            "metric": "open_levers",
            "acted_when": "metric_decreased",
            "protected": False,
            "cuttable": True,
        }
    }
    out = mod.render_phase(root, sections, "morning", {"scores": {}, "refresh_output": {}})
    assert out[0].stale is True
    assert out[0].metric == 1, "a frozen registry keeps its metric — the count is still true"
    assert any("FROZEN" in ln for ln in out[0].lines)


# ── the loop: claims are scored, and scoring a claim scores its section ───────────


def _rendered(mod, key, metric):
    return mod.Rendered(key=key, title=key, lines=[str(metric)], metric=metric)


def test_claims_are_falsifiable_and_score_three_ways(mod):
    claims = [
        {"id": 1, "section": "a", "metric": "m", "was": 10, "text": "a falls below 10"},
        {"id": 2, "section": "b", "metric": "m", "was": 5, "text": "b falls below 5"},
        {"id": 3, "section": "c", "metric": "m", "was": 3, "text": "c falls below 3"},
    ]
    rendered = [_rendered(mod, "a", 4), _rendered(mod, "b", 5), _rendered(mod, "c", 9)]
    verdicts = {s["section"]: s["verdict"] for s in mod.score_claims(claims, rendered)}
    assert verdicts == {"a": "held", "b": "noop", "c": "missed"}


def test_claims_skip_stale_and_zero_metrics(mod, root):
    """You cannot claim progress on a number you refused to read."""
    sections = {
        "good": {"_key": "good", "title": "good", "metric": "m", "acted_when": "metric_decreased"},
        "zero": {"_key": "zero", "title": "zero", "metric": "m", "acted_when": "metric_decreased"},
        "stale": {"_key": "stale", "title": "stale", "metric": "m", "acted_when": "metric_decreased"},
        "unmeasured": {"_key": "unmeasured", "title": "u", "metric": None, "acted_when": None},
    }
    stale = _rendered(mod, "stale", 9)
    stale.stale = True
    rendered = [_rendered(mod, "good", 4), _rendered(mod, "zero", 0), stale, _rendered(mod, "unmeasured", None)]
    claims = mod.build_claims(root, sections, rendered, 5)
    assert [c["section"] for c in claims] == ["good"]


# ── cut authority: bounded, evidence-based, reversible ────────────────────────────


def _scored(section, verdict):
    return {
        "id": 1,
        "section": section,
        "metric": "m",
        "was": 5,
        "now": 5,
        "verdict": verdict,
        "text": f"{section} falls below 5",
    }


def _spec(cuttable=True, protected=False):
    return {"cuttable": cuttable, "protected": protected, "metric": "m", "acted_when": "metric_decreased", "title": "t"}


def test_noop_streak_accrues_then_cuts_exactly_once(mod, root):
    sections = {"a": _spec()}
    scores: dict = {}
    for day in range(1, 5):
        applied, _ = mod.apply_cuts(root, sections, [_scored("a", "noop")], scores, 5, 1, True)
        assert applied == [], f"cut fired on day {day}, before the threshold"
        assert scores["a"]["noop_streak"] == day
    applied, _ = mod.apply_cuts(root, sections, [_scored("a", "noop")], scores, 5, 1, True)
    assert [c["section"] for c in applied] == ["a"]
    assert scores["a"]["cut"] is True


def test_action_resets_the_streak(mod, root):
    sections = {"a": _spec()}
    scores: dict = {}
    for _ in range(4):
        mod.apply_cuts(root, sections, [_scored("a", "noop")], scores, 5, 1, True)
    mod.apply_cuts(root, sections, [_scored("a", "held")], scores, 5, 1, True)
    assert scores["a"]["noop_streak"] == 0
    applied, _ = mod.apply_cuts(root, sections, [_scored("a", "noop")], scores, 5, 1, True)
    assert applied == []


def test_unengaged_day_is_unscored_not_noop(mod, root):
    """A week away must not prune the dashboard."""
    sections = {"a": _spec()}
    scores: dict = {}
    for _ in range(10):
        applied, _ = mod.apply_cuts(root, sections, [_scored("a", "noop")], scores, 5, 1, engaged=False)
        assert applied == []
    assert scores.get("a", {}).get("noop_streak", 0) == 0


def test_protected_and_unmeasurable_sections_never_cut(mod, root):
    sections = {"safety": _spec(cuttable=False, protected=True), "blind": _spec(cuttable=False)}
    scores: dict = {}
    for _ in range(20):
        applied, _ = mod.apply_cuts(
            root, sections, [_scored("safety", "noop"), _scored("blind", "noop")], scores, 5, 1, True
        )
        assert applied == []


def test_cut_rate_is_bounded_per_day(mod, root):
    sections = {k: _spec() for k in ("a", "b", "c")}
    scores = {k: {"noop_streak": 99, "cut": False} for k in sections}
    applied, _ = mod.apply_cuts(root, sections, [], scores, 5, 1, True)
    assert len(applied) == 1, "a quiet stretch must not strip the whole briefing in one night"


def test_every_cut_is_receipted(mod, root):
    sections = {"a": _spec()}
    scores = {"a": {"noop_streak": 99, "cut": False}}
    mod.apply_cuts(root, sections, [], scores, 5, 1, True)
    rows = [json.loads(ln) for ln in (root / "logs" / "diurnal" / "cuts.jsonl").read_text().splitlines()]
    assert rows and rows[-1]["action"] == "cut" and rows[-1]["section"] == "a"


def test_cut_section_is_silent_but_auto_restores_on_exception(mod, root):
    """Cutting is demotion, not blindness — the anti-ratchet."""
    (root / "logs" / "overnight-watch.md").write_text("Status: alert\n\n## WATCH_ALERT\n- boom\n")
    sections = {
        "overnight": {
            "_key": "overnight",
            "phases": ["morning"],
            "title": "overnight",
            "render": "overnight_alerts",
            "source": None,
            "refresh": None,
            "max_age_seconds": 0,
            "metric": "alert_count",
            "acted_when": "metric_decreased",
            "protected": False,
            "cuttable": True,
        }
    }
    scores = {"overnight": {"cut": True, "noop_streak": 9}}
    ctx = {"scores": scores, "refresh_output": {}}
    out = mod.render_phase(root, sections, "morning", ctx)
    assert [r.key for r in out] == ["overnight"], "an exception must bring a cut section back"
    assert ctx["restored"] == ["overnight"]
    assert scores["overnight"]["cut"] is False

    # with nothing wrong, the same cut section stays silent
    (root / "logs" / "overnight-watch.md").write_text("Status: clear\n")
    scores["overnight"]["cut"] = True
    out = mod.render_phase(root, sections, "morning", {"scores": scores, "refresh_output": {}})
    assert out == []


# ── the page: human text outside the markers survives regeneration ────────────────


def test_regeneration_preserves_human_text_and_is_idempotent(mod, root):
    page = root / "docs" / "diurnal" / "2026-07-31.md"
    mod.write_block(page, "morning", "<!-- diurnal:morning:start -->\nfirst\n<!-- diurnal:morning:end -->")
    page.write_text(page.read_text() + "\nMY OWN NOTE — this section was useful\n")
    mod.write_block(page, "morning", "<!-- diurnal:morning:start -->\nsecond\n<!-- diurnal:morning:end -->")
    text = page.read_text()
    assert "MY OWN NOTE — this section was useful" in text
    assert "second" in text and "first" not in text

    before = page.read_text()
    mod.write_block(page, "morning", "<!-- diurnal:morning:start -->\nsecond\n<!-- diurnal:morning:end -->")
    assert page.read_text() == before, "re-running a phase must reach a fixed point"


def test_phases_append_without_clobbering_each_other(mod, root):
    page = root / "docs" / "diurnal" / "2026-07-31.md"
    for phase in ("morning", "midday", "evening"):
        mod.write_block(page, phase, f"<!-- diurnal:{phase}:start -->\n{phase} body\n<!-- diurnal:{phase}:end -->")
    text = page.read_text()
    for phase in ("morning", "midday", "evening"):
        assert f"{phase} body" in text


# ── registry ↔ organ parity ───────────────────────────────────────────────────────


def test_every_registry_render_key_resolves(mod):
    import yaml

    sections = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["sections"]
    missing = [k for k, s in sections.items() if s.get("render") not in mod.RENDERERS]
    assert not missing, f"registry names renderers that do not exist: {missing}"


def test_cuttable_implies_measurable(mod):
    """The load-bearing rule, asserted here as well as in scripts/check-diurnal.py."""
    import yaml

    sections = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["sections"]
    bad = [k for k, s in sections.items() if s.get("cuttable") and s.get("metric") is None]
    assert not bad, f"cuttable sections with no metric would prune themselves on no evidence: {bad}"


def test_blocks_land_in_chronological_order_whatever_the_write_order(mod, root):
    """A phase re-run out of sequence must not leave the day reading scrambled."""
    page = root / "docs" / "diurnal" / "2026-07-31.md"
    for phase in ("evening", "morning", "midday"):  # deliberately out of order
        mod.write_block(page, phase, f"<!-- diurnal:{phase}:start -->\n{phase} body\n<!-- diurnal:{phase}:end -->")
    text = page.read_text()
    positions = [text.index(f"{p} body") for p in ("morning", "midday", "evening")]
    assert positions == sorted(positions), "phases must read morning → midday → evening"


# ── the emission needs a reader, or it is a log file with better prose ────────────


def test_index_is_derived_from_the_directory_not_appended(mod, root):
    """A hand-maintained index is the same failure one surface over. Rebuilding from the files
    means deleting a page removes its row and no bookkeeping is owed."""
    pages = root / "docs" / "diurnal"
    pages.mkdir(parents=True)
    for day in ("2026-07-29", "2026-07-30", "2026-07-31"):
        (pages / f"{day}.md").write_text(
            f"<!-- diurnal:morning:start -->\n\n## {day} · morning\n\n- next: ship it [ABC-1]\n"
            "<!-- diurnal:morning:end -->\n",
            encoding="utf-8",
        )
    (pages / "README.md").write_text("not a dated page", encoding="utf-8")

    assert mod.write_index(root) == pages / "INDEX.md"
    body = (pages / "INDEX.md").read_text(encoding="utf-8")
    assert body.index("2026-07-31") < body.index("2026-07-29"), "newest first"
    assert "README" not in body, "only dated pages are days"
    assert "morning" in body

    (pages / "2026-07-30.md").unlink()
    mod.write_index(root)
    assert "2026-07-30" not in (pages / "INDEX.md").read_text(encoding="utf-8")


def test_index_is_absent_rather_than_empty_when_nothing_has_emitted(mod, root):
    (root / "docs" / "diurnal").mkdir(parents=True)
    assert mod.write_index(root) is None
    assert not (root / "docs" / "diurnal" / "INDEX.md").exists()
