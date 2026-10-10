from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from limen.fanout import compile_packets


def test_original_key_serial_roles_and_deadline_use_keeper_root():
    path = Path(__file__).resolve().parents[2] / "scripts/ops6-recovery-graph.py"
    spec = importlib.util.spec_from_file_location("ops6_graph", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    deadline = datetime.now(UTC) + timedelta(minutes=20)
    manifest = module.build_manifest("native-session", deadline)
    routes = {
        "routes": [
            {"work_id": leaf.work_id, "local_heavy": False, "session_id": "native-session", "agent": "codex"}
            for leaf in manifest.leaves
        ]
    }
    packets = compile_packets(manifest, routes)
    assert packets[0].intent["kind"] == "fanout-root"
    assert packets[0].work_key == "ops6-coordinate-20261009"
    assert len(packets) == 4
    assert all(packet.deadline == deadline for packet in packets)
    assert packets[2].execution["dependencies"] == [packets[1].work_id]
    assert packets[3].execution["dependencies"] == [packets[2].work_id]
    assert all(packet.retry.max_attempts == 1 for packet in packets)
