"""Tests for generate-seo-backlog.py — the SEO gap -> bounded-task generator.

Focus: the traffic-aware prioritization (the DISCOVERY sensor->effector closure). `_plan()` must
order work so a value-repo with a MEASURED 0 unique visitors (`logs/observatory/traffic.jsonl`,
written by traffic-collect.py) is planned BEFORE a better-seen repo, overriding the static
value-repos.json rank — while staying correct-when-empty: no traffic ledger -> the static rank is
preserved exactly, and a 403/unmeasured snapshot never gets mistaken for "unseen".

The script deliberately resolves its artifacts from its own tree (ROOT), not env (the gitvs ROOT
convention documented in the module), so we load it by path and monkeypatch its readers rather than
shelling out with env overrides.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "generate-seo-backlog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_seo_backlog", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _audit(repos: dict) -> dict:
    # repos: {repo: {"pass": bool, "standard": str, "rungs": {...}}}
    return {"audited": len(repos), "repos": repos}


def _write_traffic(path: Path, rows: list[tuple[str, str, int | None]]) -> None:
    # rows: (repo, date, uniques); uniques None -> a 403/_error snapshot (unmeasured).
    lines = []
    for repo, date, uniques in rows:
        views = {"_error": "403"} if uniques is None else {"count": uniques * 2, "uniques": uniques}
        lines.append(
            json.dumps({"repo": repo, "date": date, "views": views, "clones": {}, "referrers": [], "top_paths": []})
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


_FAILING_TWO = {
    "o/high": {"pass": False, "standard": "class", "rungs": {"S1": False}},
    "o/zero": {"pass": False, "standard": "class", "rungs": {"S1": False}},
}


def _patch_plan_inputs(mod, monkeypatch, *, audit_repos: dict, rank: dict) -> None:
    monkeypatch.setattr(mod, "_audit", lambda: _audit(audit_repos))
    monkeypatch.setattr(mod, "_value_rank", lambda: rank)
    monkeypatch.setattr(mod, "_seeded", lambda: set())


def test_zero_view_repo_boosted_ahead_of_value_rank(tmp_path, monkeypatch):
    mod = _load_module()
    # Static value rank favors o/high (rank 0); traffic says o/high is well-seen and o/zero is unseen.
    _patch_plan_inputs(mod, monkeypatch, audit_repos=_FAILING_TWO, rank={"o/high": 0, "o/zero": 1})
    traffic = tmp_path / "traffic.jsonl"
    _write_traffic(traffic, [("o/high", "2026-07-18", 500), ("o/zero", "2026-07-18", 0)])
    monkeypatch.setattr(mod, "TRAFFIC", traffic)

    new, _info = mod._plan([], floor=6, max_new=6)
    repos = [t.repo for t in new]
    assert repos.index("o/zero") < repos.index("o/high"), (
        f"a measured zero-view repo must be planned before a better-seen one, overriding value rank: {repos}"
    )


def test_no_traffic_ledger_preserves_static_value_rank(tmp_path, monkeypatch):
    mod = _load_module()
    _patch_plan_inputs(mod, monkeypatch, audit_repos=_FAILING_TWO, rank={"o/high": 0, "o/zero": 1})
    monkeypatch.setattr(mod, "TRAFFIC", tmp_path / "does-not-exist.jsonl")

    new, _info = mod._plan([], floor=6, max_new=6)
    repos = [t.repo for t in new]
    assert repos.index("o/high") < repos.index("o/zero"), (
        f"with no traffic data the static value rank must hold (correct-when-empty): {repos}"
    )


def test_unmeasured_403_snapshot_is_not_treated_as_unseen(tmp_path, monkeypatch):
    mod = _load_module()
    # o/high has rank 0; o/zero has rank 1 but only a 403 snapshot -> unmeasured, NOT boosted.
    _patch_plan_inputs(mod, monkeypatch, audit_repos=_FAILING_TWO, rank={"o/high": 0, "o/zero": 1})
    traffic = tmp_path / "traffic.jsonl"
    _write_traffic(traffic, [("o/high", "2026-07-18", 500), ("o/zero", "2026-07-18", None)])
    monkeypatch.setattr(mod, "TRAFFIC", traffic)

    new, _info = mod._plan([], floor=6, max_new=6)
    repos = [t.repo for t in new]
    assert repos.index("o/high") < repos.index("o/zero"), (
        f"a 403/unmeasured repo must stay neutral (value rank), never boosted like a measured zero: {repos}"
    )


def test_traffic_seen_latest_wins_and_skips_errors(tmp_path, monkeypatch):
    mod = _load_module()
    traffic = tmp_path / "traffic.jsonl"
    _write_traffic(
        traffic,
        [
            ("o/a", "2026-07-01", 10),  # older
            ("o/a", "2026-07-18", 3),  # newer -> wins
            ("o/b", "2026-07-18", None),  # 403 -> unmeasured -> omitted
        ],
    )
    monkeypatch.setattr(mod, "TRAFFIC", traffic)
    assert mod._traffic_seen() == {"o/a": 3}
