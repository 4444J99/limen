from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "harvest-pull-completed.py"


def test_broker_logical_jules_session_is_harvestable(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location("harvest_pull_completed_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.TASKS = tmp_path / "tasks.yaml"
    module.TASKS.write_text(
        yaml.safe_dump(
            {
                "tasks": [
                    {
                        "id": "JULES-BROKER",
                        "target_agent": "jules",
                        "status": "dispatched",
                        "dispatch_log": [
                            {
                                "session_id": "keeper-session",
                                "logical_session_id": "123456789012",
                            }
                        ],
                    }
                ]
            }
        )
    )

    assert module.dispatched_by_session() == {"123456789012": "JULES-BROKER"}
