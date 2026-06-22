"""Tests for the single surface of surfaces (omni-view.py).

omni.html consolidates every feed onto one page: the value verdict on top, then present (board +
governor + fleet), past (trend + ships), future (revenue + levers + knowledge), and an everything-index.
Every section fails OPEN — a missing feed yields an empty section, never a crash.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "omni-view.py"


def _seed(tmp: Path):
    logs = tmp / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "ledger.json").write_text(json.dumps({
        "verdict": "net WORTH IT — 10 shipped, 2 wasted; 30 of 34 debits productive, 4 sunk",
        "net": "WORTH IT", "lane_rank": ["codex", "jules"], "worst_sink": "o/sink",
        "lanes": {"codex": {"tasks": 8, "success_rate": 0.9, "sunk": 0, "cost_per_shipped": 1.2},
                  "jules": {"tasks": 6, "success_rate": 0.2, "sunk": 9, "cost_per_shipped": 9.0}},
        "revenue_attribution": [{"product": "Exporter", "spent": 5, "shipped": 4, "wasted": 1}],
    }))
    (logs / "autonomy-policy.json").write_text(json.dumps(
        {"mode": "dispatch", "bounds": {"reserve_pct": 15, "daily_dispatch_cap": 600}}))
    (logs / "usage.json").write_text(json.dumps(
        {"vendors": {"codex": {"health": "ok", "headroom_pct": 95, "runway_h": 40}}}))
    (tmp / "tasks.yaml").write_text(yaml.safe_dump({"version": "1.0", "portal": {"name": "t"},
        "tasks": [{"id": "a", "status": "done"}, {"id": "b", "status": "open"}]}))
    (tmp / "revenue-ladder.json").write_text(json.dumps({
        "spine": "income in <10 weeks",
        "your_levers": ["create the Ko-fi account", "create the LemonSqueezy product"],
        "products": [{"rank": 1, "product": "ChatGPT Exporter", "repo": "o/exp",
                      "stage": "deploy-ready", "whose_hand": "yours"}]}))
    (tmp / "memory").mkdir(exist_ok=True)
    (tmp / "memory" / "m1.md").write_text("x")
    (tmp / "plans").mkdir(exist_ok=True)
    (tmp / "plans" / "p1.md").write_text("x")


def _run(tmp: Path) -> str:
    env = {**os.environ, "LIMEN_ROOT": str(tmp),
           "LIMEN_MEMORY_DIR": str(tmp / "memory"), "LIMEN_PLANS_DIR": str(tmp / "plans")}
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    return (tmp / "web" / "app" / "out" / "omni.html").read_text()


def test_consolidates_all_sections(tmp_path: Path):
    _seed(tmp_path)
    html = _run(tmp_path)
    # value verdict on top
    assert "net" in html and "WORTH IT" in html and "earning its keep" in html.lower()
    assert "codex" in html and "jules" in html, "per-lane scorecard rendered"
    # present
    assert "dispatch" in html and "governor" in html.lower()
    assert "done 1" in html or "done" in html  # board mix
    # future: levers + revenue
    assert "Ko-fi" in html and "LemonSqueezy" in html, "YOUR LEVERS rendered verbatim"
    assert "ChatGPT Exporter" in html
    # everything index
    assert "1 memories" in html and "1 plans" in html


def test_fails_open_with_no_feeds(tmp_path: Path):
    # no logs, no ladder, no board — every section must render empty, not crash
    (tmp_path / "memory").mkdir()
    (tmp_path / "plans").mkdir()
    html = _run(tmp_path)
    assert "the one surface" in html.lower()
    assert "no ledger yet" in html, "absent ledger → graceful placeholder, not a crash"
