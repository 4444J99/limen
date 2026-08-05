"""Tests for the value-ledger rollup (ledger.py).

The rollup turns weighed records into the verdict: per-lane earns-its-keep ranking, sunk-cost totals,
revenue attribution, and a net WORTH IT / WASTE call. These are the numbers that justify (or indict)
the spend.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ledger.py"


def _rec(task_id, lane, grade, repo, spent, sunk=0):
    return {
        "ts": "2026-06-22T00:00:00Z",
        "task_id": task_id,
        "repo": repo,
        "lane": lane,
        "status": "done",
        "grade": grade,
        "budget_cost": 1,
        "attempts": 1,
        "spent": spent,
        "sunk": sunk,
        "pr": None,
        "note": "",
    }


def _run(tmp: Path, records: list[dict], ladder: dict | None = None, extra_env: dict[str, str] | None = None) -> dict:
    logs = tmp / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "ledger.jsonl").write_text("\n".join(json.dumps(r) for r in records))
    if ladder is not None:
        (tmp / "revenue-ladder.json").write_text(json.dumps(ladder))
    env = {**os.environ, "LIMEN_ROOT": str(tmp)}
    if extra_env:
        env.update(extra_env)
    r = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True, timeout=60, env=env)
    assert r.returncode == 0, r.stderr
    return json.loads((logs / "ledger.json").read_text())


def test_lane_rank_puts_best_earner_first(tmp_path: Path):
    records = [
        # good lane: 3 shipped, 0 sunk
        _rec("a", "codex", "worth_it", "o/x", 1),
        _rec("b", "codex", "worth_it", "o/x", 1),
        _rec("c", "codex", "worth_it", "o/x", 1),
        # bad lane: 1 shipped, lots wasted+sunk
        _rec("d", "jules", "worth_it", "o/y", 1),
        _rec("e", "jules", "wasted", "o/y", 5, sunk=5),
        _rec("f", "jules", "wasted", "o/y", 5, sunk=5),
    ]
    rep = _run(tmp_path, records)
    assert rep["lane_rank"][0] == "codex", "the lane that earns its keep ranks first"
    assert rep["lane_rank"][-1] == "jules"
    assert rep["lanes"]["jules"]["sunk"] == 10


def test_net_verdict_and_worst_sink(tmp_path: Path):
    records = [
        _rec("a", "codex", "worth_it", "o/good", 2),
        _rec("b", "opencode", "wasted", "o/sink", 9, sunk=9),
    ]
    rep = _run(tmp_path, records)
    assert rep["net"] in ("WORTH IT", "WASTE", "EVEN")
    assert rep["worst_sink"] == "o/sink", "the repo with the most sunk cost is named"
    assert "wasted" in rep["verdict"] and "sunk" in rep["verdict"]


def test_revenue_attribution_maps_spend_to_products(tmp_path: Path):
    ladder = {"products": [{"repo": "organvm/exporter", "product": "ChatGPT Exporter"}]}
    records = [
        _rec("a", "codex", "worth_it", "organvm/exporter", 3),
        _rec("b", "codex", "wasted", "organvm/exporter", 1, sunk=1),
        _rec("c", "codex", "worth_it", "organvm/unlisted", 2),  # not a product → not attributed
    ]
    rep = _run(tmp_path, records, ladder=ladder)
    attr = {a["product"]: a for a in rep["revenue_attribution"]}
    assert "ChatGPT Exporter" in attr
    assert attr["ChatGPT Exporter"]["spent"] == 4 and attr["ChatGPT Exporter"]["shipped"] == 1
    assert all(a["product"] != "organvm/unlisted" for a in rep["revenue_attribution"])


def test_malformed_numeric_inputs_fall_back(tmp_path: Path):
    records = [
        _rec("a", "codex", "worth_it", "o/good", "bad"),
        _rec("b", "jules", "wasted", "o/sink", True, sunk="bad"),
    ]
    rep = _run(
        tmp_path,
        records,
        extra_env={"LIMEN_WASTE_RATE": "bad", "LIMEN_WIN_RATE": "nan", "LIMEN_WASTE_MIN": "bad"},
    )

    assert rep["records"] == 2
    assert rep["totals"]["spent"] == 0
    assert rep["totals"]["sunk"] == 0
