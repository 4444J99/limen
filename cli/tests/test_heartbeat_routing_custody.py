from __future__ import annotations

import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_heartbeat_balance_voice_never_applies_board_routing() -> None:
    heartbeat = (ROOT / "scripts" / "heartbeat-loop.sh").read_text(encoding="utf-8")

    assert 'route.py" --apply' not in heartbeat
    assert 'rebalance.py" --lanes "$EFFECTIVE_LANES" --apply' not in heartbeat


def test_route_plan_leaves_board_byte_identical(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    board.write_text(
        yaml.safe_dump(
            {
                "version": "1.0",
                "portal": {
                    "budget": {"daily": 10, "per_agent": {}, "track": {"date": "", "spent": 0, "per_agent": {}}}
                },
                "tasks": [],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    before = board.read_bytes()

    subprocess.run(
        ["python3", str(ROOT / "scripts" / "route.py"), "--tasks", str(board), "--workdir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    assert board.read_bytes() == before


def test_route_apply_flag_fails_closed_without_board_mutation(tmp_path: Path) -> None:
    board = tmp_path / "tasks.yaml"
    board.write_text(
        "version: '1.0'\ntasks: []\n",
        encoding="utf-8",
    )
    before = board.read_bytes()

    proc = subprocess.run(
        ["python3", str(ROOT / "scripts" / "route.py"), "--tasks", str(board), "--apply"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 2
    assert "--apply is retired" in proc.stderr
    assert board.read_bytes() == before
