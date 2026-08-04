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

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import _root  # noqa: E402  — the shared root predicate the organ's guard now delegates to


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
    """A synthetic root for the rendering/scoring tests below.

    Deliberately NOT organism-shaped — none of these tests go through main()'s liveness guard,
    they call the render and score functions directly. The guard's own cases build their roots
    explicitly via _organism() above, so this fixture never has to lie about being alive.
    """
    (tmp_path / "logs" / ".voice").mkdir(parents=True)
    (tmp_path / "logs" / ".voice" / "drain").write_text("")
    (tmp_path / "institutio" / "governance").mkdir(parents=True)
    (tmp_path / "institutio" / "governance" / "diurnal.yaml").write_text(
        REGISTRY.read_text(encoding="utf-8"), encoding="utf-8"
    )
    return tmp_path


# ── the root guard: the single most dangerous failure mode ────────────────────────
#
# These two tests replace a pair that encoded the defect rather than catching it. The old
# `test_has_body_true_for_synthetic_organism` asserted that a tmp_path carrying ONE voice stamp
# IS a live organism — which is exactly the false positive that let a worktree emit a briefing
# where five live-present sections read ABSENT. Its sibling's second assertion was
# `assert mod.has_body(mod.resolve_root()) or True`, a tautology that could never fail.


def _organism(path: Path, voices: int) -> Path:
    """A root shaped like the real body: a primary checkout (.git is a DIR) that has beaten."""
    (path / ".git").mkdir(parents=True, exist_ok=True)
    (path / "institutio" / "governance").mkdir(parents=True, exist_ok=True)
    (path / "institutio" / "governance" / "sensors.yaml").write_text("", encoding="utf-8")
    voice = path / "logs" / ".voice"
    voice.mkdir(parents=True, exist_ok=True)
    for i in range(voices):
        (voice / f"sensor{i}").write_text("", encoding="utf-8")
    return path


def test_a_worktree_is_never_the_organism(tmp_path):
    """THE REGRESSION. A linked worktree's .git is a gitdir-pointer FILE, and a single scheduled
    sensor stamping it is enough to populate logs/.voice — which is all the guard this replaced
    ever checked. Voices present, body absent."""
    wt = _organism(tmp_path / "wt", voices=9)
    (wt / ".git").rmdir()
    (wt / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n", encoding="utf-8")

    assert _root.is_worktree(wt) is True
    live, why = _root.has_body(wt)
    assert live is False
    assert "worktree" in why  # the reason must name the real cause, not "no logs/.voice"


def test_a_checkout_that_never_beat_is_not_the_organism(tmp_path):
    """A second clone, a fresh CI checkout, a restored backup: .git is a directory, so the exact
    worktree test passes it. The voice floor is what separates it from the living body."""
    cold = _organism(tmp_path / "cold", voices=1)
    assert _root.is_worktree(cold) is False
    assert _root.has_body(cold)[0] is False

    beaten = _organism(tmp_path / "beaten", voices=_root.DEFAULT_VOICE_FLOOR)
    assert _root.has_body(beaten)[0] is True


def test_an_explicitly_wrong_LIMEN_ROOT_is_an_error_not_a_fallback(tmp_path, monkeypatch):
    """Silently correcting bad config is what makes config errors invisible (_uma_root's lesson)."""
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "nowhere"))
    resolved, why = _root.resolve()
    assert resolved is None
    assert "not a limen checkout" in why


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
    """You cannot claim progress on a number you refused to read.

    The floor rule is per-`acted_when`, not global: nothing falls below zero, so a
    `metric_decreased` section at 0 stays unclaimable — but "changes from 0" is the single most
    consequential claim the organ can make, and excluding it would have made IF-FIRST-DOLLAR
    unspeakable. See cli/tests/test_diurnal_claims.py for that rule's own cases.
    """
    sections = {
        "good": {"_key": "good", "title": "good", "metric": "m", "acted_when": "metric_decreased"},
        "zero": {"_key": "zero", "title": "zero", "metric": "m", "acted_when": "metric_decreased"},
        "zero_changed": {"_key": "zero_changed", "title": "zc", "metric": "m", "acted_when": "metric_changed"},
        "stale": {"_key": "stale", "title": "stale", "metric": "m", "acted_when": "metric_decreased"},
        "unmeasured": {"_key": "unmeasured", "title": "u", "metric": None, "acted_when": None},
    }
    stale = _rendered(mod, "stale", 9)
    stale.stale = True
    rendered = [
        _rendered(mod, "good", 4),
        _rendered(mod, "zero", 0),
        _rendered(mod, "zero_changed", 0),
        stale,
        _rendered(mod, "unmeasured", None),
    ]
    claims = mod.build_claims(root, sections, rendered)
    assert [c["section"] for c in claims] == ["good", "zero_changed"]


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


# ── durability: an emission nobody commits is an emission that never happened ──────
#
# The organ's first live page landed UNTRACKED inside a tracked directory, and the beat's only
# committing rung refuses in-place commits on the live default branch. These cover the predicate
# that decides what to publish and the two gates that decide whether to publish at all.


def _fake_git(mod, monkeypatch, porcelain: str, rc: int = 0):
    """Stub the ONE shell-out unshipped_pages makes, so no test touches a real repo."""
    calls: list[str] = []

    def fake_run(cmd, root, timeout=120):
        calls.append(cmd)
        return rc, porcelain

    monkeypatch.setattr(mod, "_run", fake_run)
    return calls


def test_unshipped_pages_finds_untracked_and_modified_but_not_readme(mod, tmp_path, monkeypatch):
    for name in ("2026-07-31.md", "2026-08-01.md", "README.md"):
        p = tmp_path / "docs" / "diurnal" / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    _fake_git(
        mod,
        monkeypatch,
        "?? docs/diurnal/2026-07-31.md\n M docs/diurnal/2026-08-01.md\n M docs/diurnal/README.md\n",
    )
    assert mod.unshipped_pages(tmp_path) == ["docs/diurnal/2026-07-31.md", "docs/diurnal/2026-08-01.md"]


def test_unshipped_pages_skips_a_page_that_is_gone(mod, tmp_path, monkeypatch):
    """A staged deletion is not an emission to publish — ship-docs requires the file to exist."""
    _fake_git(mod, monkeypatch, " D docs/diurnal/2026-07-30.md\n")
    assert mod.unshipped_pages(tmp_path) == []


def test_unshipped_pages_fails_closed_when_git_errors(mod, tmp_path, monkeypatch):
    _fake_git(mod, monkeypatch, "fatal: not a git repository\n", rc=128)
    assert mod.unshipped_pages(tmp_path) == []


def test_a_pause_marker_prohibiting_merge_holds_publication(mod, tmp_path, monkeypatch):
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "AUTONOMY_PAUSED").write_text("owner: operator\nprohibitions: merge, send\n", encoding="utf-8")
    assert "merge" in (mod._merge_prohibited(tmp_path) or "")

    shipped: list[str] = []
    monkeypatch.setattr(mod, "unshipped_pages", lambda root: shipped.append("asked") or [])
    assert mod.ship_pages(tmp_path) == 0
    assert shipped == [], "a merge-prohibiting marker must short-circuit BEFORE any shipping work"


def test_a_pause_marker_that_does_not_prohibit_merge_does_not_hold_publication(mod, tmp_path):
    (tmp_path / "logs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "AUTONOMY_PAUSED").write_text("prohibitions: send, spend\n", encoding="utf-8")
    assert mod._merge_prohibited(tmp_path) is None


def test_no_marker_at_all_does_not_hold_publication(mod, tmp_path):
    assert mod._merge_prohibited(tmp_path) is None


def test_ship_is_gated_by_its_declared_parameter(mod, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_DIURNAL_SHIP", "0")
    monkeypatch.setattr(mod, "unshipped_pages", lambda root: pytest.fail("must not look when gated off"))
    assert mod.ship_pages(tmp_path) == 0


def test_ship_never_fails_the_beat_when_the_shipper_is_absent(mod, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_DIURNAL_SHIP", "1")
    monkeypatch.setattr(mod, "unshipped_pages", lambda root: ["docs/diurnal/2026-07-31.md"])
    assert mod.ship_pages(tmp_path) == 0, "a missing ship-docs.sh is advisory, never a beat failure"


def test_a_shipped_page_is_not_reshipped_while_its_pr_is_still_open(mod, tmp_path, monkeypatch):
    """The defect driving this live exposed: after a successful ship the page is STILL `??`,
    because it becomes tracked only when the PR merges and the beat pulls. Git state alone
    re-ships it every emission — three duplicate PRs a day for one file."""
    page = tmp_path / "docs" / "diurnal" / "2026-07-31.md"
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text("morning\n", encoding="utf-8")
    _fake_git(mod, monkeypatch, "?? docs/diurnal/2026-07-31.md\n")

    assert mod.unshipped_pages(tmp_path) == ["docs/diurnal/2026-07-31.md"]

    (tmp_path / "logs" / "diurnal").mkdir(parents=True, exist_ok=True)
    (tmp_path / "logs" / "diurnal" / "shipped.json").write_text(
        json.dumps({"docs/diurnal/2026-07-31.md": mod._digest(page)}), encoding="utf-8"
    )
    assert mod.unshipped_pages(tmp_path) == [], "git still says `??` — the receipt must carry the gap"

    page.write_text("morning\nmidday\n", encoding="utf-8")
    assert mod.unshipped_pages(tmp_path) == ["docs/diurnal/2026-07-31.md"], (
        "keying on the digest, not the path, is what lets a later phase re-ship what it rewrote"
    )


# ── CLI edges found by driving the organ, not by reading it ───────────────────────


def test_uncut_rejects_a_name_the_registry_does_not_know(mod, tmp_path, monkeypatch, capsys):
    """A typo must not be answerable with the same sentence as a real, uncut section. Someone
    restoring a genuinely cut section who fumbles the name would otherwise read 'is not cut' and
    conclude nothing was ever cut — the reassuring answer being the wrong one.

    This one goes through main(), so its root must be organism-shaped: _root's guard now demands a
    primary checkout that has actually beaten, and the render-level `root` fixture deliberately is
    not one. monkeypatch, not os.environ — the first draft set LIMEN_ROOT and never restored it,
    leaking a dead tmp path into every test that ran after it.
    """
    body = _organism(tmp_path / "body", voices=_root.DEFAULT_VOICE_FLOOR)
    (body / "institutio" / "governance" / "diurnal.yaml").write_text(
        REGISTRY.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setenv("LIMEN_ROOT", str(body))
    monkeypatch.setattr(sys, "argv", ["diurnal.py", "--uncut", "levrs"])

    assert mod.main() == 2
    err = capsys.readouterr().err
    assert "no section named 'levrs'" in err
    assert "Did you mean: levers?" in err


def test_headline_keeps_the_task_id_it_used_to_guillotine(mod):
    """Observed live in a push: '…for the whole PR estate [GITVS-UNCAPPED-'. The bracketed id is
    the one token a reader can act on, and a raw [:90] cut it in half."""
    line = "Add an uncapped exact owner-route predicate for the whole PR estate and its successors [GITVS-UNCAPPED-PR]"
    out = mod._clip(line)
    assert out.endswith("[GITVS-UNCAPPED-PR]"), "the actionable id must survive truncation"
    assert len(out) <= 90
    assert "…" in out, "a truncated line must read as truncated"
    assert not out.rstrip("… [GITVS-UNCAPPED-PR]").endswith(" "), "cut on a word boundary"


def test_a_short_headline_is_left_alone(mod):
    assert mod._clip("short one [ABC-1]") == "short one [ABC-1]"


def test_dry_run_creates_no_state_directory(mod, root):
    """'Write nothing' has to be literally true — state_dir's unconditional mkdir meant a dry run
    left an empty logs/diurnal/ behind."""
    mod.load_state(root)
    mod.load_scores(root)
    assert not (root / "logs" / "diurnal").exists()


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
