import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
import yaml

from limen.conduct.models import WorkPacketV1
from limen.conduct.client import client_from_env
from limen.conduct.broker import ConductBroker

def main():
    client = client_from_env()

    # Load root packet
    with open("/Users/4jp/.gemini/antigravity-cli/brain/e99814bf-6b4a-4a2c-a6bb-da8d8036b797/scratch/root_packet.json", "r") as f:
        root_data = json.load(f)
    
    # Make root a fanout-root
    root_data["intent"]["kind"] = "fanout-root"
    root_data["authority"]["path_prefixes"] = ["*"]
    root_packet = WorkPacketV1.model_validate(root_data)

    # Load execution DAG
    with open("docs/continuations/collaboration-operations-platform-alpha-omega-20260803/execution-dag.yaml", "r") as f:
        dag = yaml.safe_load(f)
    
    packets = [root_packet]

    for phase in dag["phases"]:
        for packet in phase.get("packets", []):
            packet_id = packet["id"]
            child_data = {
                "schema_version": "limen.work_packet.v1",
                "work_key": packet_id,
                "work_id": packet_id,
                "parent_run_id": ConductBroker._run_id(root_packet),
                "intent": {
                    "objective": f"Execute {packet_id}",
                    "plan": f"dependencies: {packet.get('dependencies', [])}",
                    "kind": "task"
                },
                "effect": "write",
                "depth": 1,
                "fanout": {
                    "schema_version": "limen.fanout_bounds.v1",
                    "max_children": 0,
                    "max_depth": 0
                },
                "retry": {
                    "schema_version": "limen.retry_policy.v1",
                    "max_attempts": 1,
                    "transient_only": True
                },
                "initiator": {
                    "schema_version": "limen.agent_identity.v1",
                    "agent": "launcher",
                    "surface": "direct",
                    "session_id": "human"
                },
                "conductor": {
                    "schema_version": "limen.agent_identity.v1",
                    "agent": "agy",
                    "surface": "workstream",
                    "session_id": "workstream-alpha-omega"
                },
                "predicate": packet.get("predicate", ""),
                "receipt_target": f"git:organvm-iii-ergon/collaboration-operations-platform:{packet.get('receipt_target', '')}",
                "resource_claims": [
                    {
                        "schema_version": "limen.resource_claim.v1",
                        "key": f"path/organvm-iii-ergon/collaboration-operations-platform/main/{packet_id}",
                        "mode": "exclusive"
                    }
                ],
                "authority": {
                    "schema_version": "limen.authority_envelope.v1",
                    "actions": ["*"],
                    "external_effects": [],
                    "may_delegate": False,
                    "path_prefixes": ["*"],
                    "repositories": ["organvm-iii-ergon/collaboration-operations-platform"]
                },
                "deadline": root_packet.deadline.isoformat(),
                "spend": {
                    "schema_version": "limen.spend_envelope.v1",
                    "limit": 1,
                    "reserve": 0,
                    "unit": "runs"
                },
                "work_loan": {
                    "schema_version": "limen.work_loan.v1",
                    "source_origin": "human_prompt",
                    "horizon": "present",
                    "budget_cost": 1,
                    "owner_surface": "git:organvm-iii-ergon/collaboration-operations-platform:docs/continuations/collaboration-operations-platform-alpha-omega-20260803/workstream.json",
                    "value_case": f"Complete {packet_id}",
                    "external_deadline": False
                }
            }
            packets.append(WorkPacketV1.model_validate(child_data))

    print(f"Submitting graph with {len(packets)} packets...")
    result = client.submit_graph(tuple(packets))
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
