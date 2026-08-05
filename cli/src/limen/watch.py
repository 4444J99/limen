"""Real-time fleet dashboard for the Limen CLI."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from limen.capacity import PAID_AGENT_ORDER
from limen.io import load_limen_file


def _default_root() -> Path:
    env_root = os.environ.get("LIMEN_ROOT")
    if env_root:
        return Path(env_root).expanduser().resolve()
    cwd = Path.cwd()
    if (cwd / "tasks.yaml").exists():
        return cwd
    return Path(__file__).resolve().parents[3]


ROOT = _default_root()
TASKS = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))

ACTIVE = {"dispatched", "in_progress"}
PROCESS_NAMES = {
    "codex": "codex",
    "claude": "claude",
    "opencode": "opencode",
    "agy": "antigravity",
    "gemini": "gemini",
    "ollama": "ollama",
    "copilot": None,
    "warp": None,
    "oz": None,
    "github_actions": None,
    "jules": None,
}


def proc_counts() -> Counter[str]:
    try:
        output = subprocess.run(
            ["ps", "-eo", "command"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        ).stdout
    except Exception:
        return Counter()

    counts: Counter[str] = Counter()
    for lane, process_name in PROCESS_NAMES.items():
        if process_name:
            counts[lane] = sum(
                1
                for line in output.splitlines()
                if process_name in line and "limen watch" not in line and "watch.py" not in line
            )
    return counts


def _bar(fraction: float, width: int = 24) -> str:
    bounded = max(0.0, min(1.0, fraction))
    full = int(bounded * width)
    return "#" * full + "." * (width - full)


def snapshot():
    limen = load_limen_file(TASKS)
    board = Counter(task.status for task in limen.tasks)
    per_lane: dict[str, Counter[str]] = defaultdict(Counter)
    working: dict[str, list[tuple[str, str, str]]] = defaultdict(list)

    for task in limen.tasks:
        lane = task.target_agent or "unknown"
        per_lane[lane][task.status] += 1
        if task.status in ACTIVE:
            working[lane].append((task.id, (task.repo or "").split("/")[-1], (task.title or "")[:48]))

    return limen, board, per_lane, working, proc_counts(), limen.portal.budget


def render_compact(board, per_lane, procs, budget) -> str:
    total = sum(board.values())
    done = board.get("done", 0)
    active = sum(board.get(status, 0) for status in ACTIVE)
    open_count = board.get("open", 0)
    parts = [
        f"LIMEN done={done} active={active} open={open_count} total={total} budget={budget.track.spent}/{budget.daily}"
    ]
    for lane in PAID_AGENT_ORDER:
        counts = per_lane.get(lane, Counter())
        lane_done = counts.get("done", 0)
        lane_active = sum(counts.get(status, 0) for status in ACTIVE)
        lane_open = counts.get("open", 0)
        live = procs.get(lane, 0)
        state = "live" if live > 0 else "cloud" if PROCESS_NAMES.get(lane) is None and lane_active else "idle"
        parts.append(f"{lane}:{lane_done}/{lane_active}/{lane_open}:{state}")
    return " | ".join(parts)


def render(board, per_lane, working, procs, budget) -> str:
    total = sum(board.values())
    done = board.get("done", 0)
    active = sum(board.get(status, 0) for status in ACTIVE)
    open_count = board.get("open", 0)
    lines = [
        "LIMEN FLEET - live",
        f"done {done}  in-flight {active}  open {open_count}  total {total}  budget {budget.track.spent}/{budget.daily}",
        "-" * 78,
    ]

    for lane in PAID_AGENT_ORDER:
        counts = per_lane.get(lane, Counter())
        lane_done = counts.get("done", 0)
        lane_active = sum(counts.get(status, 0) for status in ACTIVE)
        lane_open = counts.get("open", 0)
        lane_total = sum(counts.values()) or 1
        process_name = PROCESS_NAMES.get(lane)
        live = procs.get(lane, 0)
        state = "cloud" if process_name is None else f"{live} proc"
        lines.append(
            f"{lane:<14} {_bar(lane_done / lane_total)} "
            f"{lane_done:>4} done {lane_active:>3} active {lane_open:>4} open  {state}"
        )
        for task_id, repo, title in working.get(lane, [])[:2]:
            lines.append(f"  - {repo}: {title} [{task_id}]")

    lines.extend(["-" * 78, "refresh: Ctrl-C to exit | feed: logs/fleet-status.json"])
    return "\n".join(lines)


def emit_json(board, per_lane, working, procs, budget) -> None:
    data = {
        "board": dict(board),
        "budget": {"spent": budget.track.spent, "daily": budget.daily},
        "lanes": {
            lane: {
                "done": per_lane.get(lane, Counter()).get("done", 0),
                "in_flight": sum(per_lane.get(lane, Counter()).get(status, 0) for status in ACTIVE),
                "open": per_lane.get(lane, Counter()).get("open", 0),
                "live_procs": procs.get(lane, 0),
                "working": [
                    {"id": task_id, "repo": repo, "title": title} for task_id, repo, title in working.get(lane, [])[:5]
                ],
            }
            for lane in PAID_AGENT_ORDER
        },
    }
    try:
        (ROOT / "logs").mkdir(exist_ok=True)
        (ROOT / "logs" / "fleet-status.json").write_text(json.dumps(data, indent=2) + "\n")
    except Exception:
        pass


def render_frame(compact: bool = False) -> str:
    _limen, board, per_lane, working, procs, budget = snapshot()
    emit_json(board, per_lane, working, procs, budget)
    if compact:
        return render_compact(board, per_lane, procs, budget)
    return render(board, per_lane, working, procs, budget)


def run(once: bool = False, compact: bool = False, interval: float = 2.0) -> None:
    while True:
        frame = render_frame(compact=compact)
        if once:
            print(frame)
            return
        sys.stdout.write("\033[2J\033[H" + frame + "\n")
        sys.stdout.flush()
        time.sleep(interval)
