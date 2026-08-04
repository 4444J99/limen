import sys
import json
import subprocess
from datetime import datetime
from pathlib import Path

# Try to import yaml
try:
    import yaml
except ImportError:
    print("yaml not found, trying pip install pyyaml")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyyaml"])
    import yaml

def main():
    root_run_id = "run-435aecdf55cdc45df0ed62ac5d7bc4e8"
    dag_path = Path("docs/continuations/collaboration-operations-platform-alpha-omega-20260803/execution-dag.yaml")
    with open(dag_path) as f:
        dag = yaml.safe_load(f)
    
    # We will track submitted work_ids to use them as dependencies
    # Wait, the broker expects the 'work_id' in dependencies.
    # So if ALPHA-01 has work_id "ALPHA-01", ALPHA-02 depends on "ALPHA-01".
    
    for phase in dag.get("phases", []):
        for packet in phase.get("packets", []):
            packet_id = packet["id"]
            title = packet["title"]
            depends_on = packet.get("depends_on", [])
            # Some dependencies might be phase IDs, some might be packet IDs.
            # We map phase IDs to the last packet of that phase, or just leave them if broker handles it?
            # Actually, the broker expects the dependency to be a registered `work_id`.
            # Let's just use the packet ID as work_id.
            
            # Resolve phase dependencies to the packets in that phase?
            # If a packet depends on "alpha", it probably means all packets in alpha.
            # For simplicity, if it's a phase id, replace with all packets in that phase.
            resolved_deps = []
            for dep in depends_on:
                # find if it's a phase
                is_phase = False
                for p in dag.get("phases", []):
                    if p["id"] == dep:
                        is_phase = True
                        for pp in p.get("packets", []):
                            resolved_deps.append(pp["id"])
                if not is_phase:
                    resolved_deps.append(dep)
            # Use resolved_deps as is
            
            work_packet = {
              "schema_version": "limen.work_packet.v1",
              "work_id": packet_id,
              "work_key": packet_id.lower(),
              "intent": {
                "objective": title,
                "plan": "\\n".join(packet.get("deliverables", []))
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
              "resource_claims": [],
              "authority": {
                "schema_version": "limen.authority_envelope.v1",
                "actions": ["*"],
                "external_effects": [],
                "may_delegate": False,
                "path_prefixes": ["/Users/4jp/Workspace/limen/.worktrees/collaboration-operations-platform-alpha-omega-20260803"],
                "repositories": []
              },
              "deadline": "2026-09-02T14:50:57+00:00",
              "spend": {
                "schema_version": "limen.spend_envelope.v1",
                "limit": 10,
                "reserve": 0,
                "unit": "runs"
              },
              "fanout": {
                "schema_version": "limen.fanout_bounds.v1",
                "max_children": 0,
                "max_depth": 0
              },
              "parent_run_id": root_run_id,
              "root_run_id": root_run_id,
              "depth": 1,
              "execution": {
                "dependencies": resolved_deps
              },
              "work_loan": {
                "schema_version": "limen.work_loan.v1",
                "source_origin": "human_prompt",
                "horizon": "present",
                "value_case": title,
                "budget_cost": 10,
                "owner_surface": f"git:organvm-iii-ergon/collaboration-operations-platform:{packet.get('receipt_target', '')}"
              }
            }
            
            packet_file = Path(f"/Users/4jp/.gemini/antigravity-cli/brain/e99814bf-6b4a-4a2c-a6bb-da8d8036b797/scratch/packet_{packet_id}.json")
            packet_file.write_text(json.dumps(work_packet, indent=2))
            
            print(f"Submitting {packet_id}...")
            cmd = [
                "limen", "conduct", "split",
                root_run_id,
                "--packet", str(packet_file)
            ]
            res = subprocess.run(cmd, env={"LIMEN_CONDUCT_STATE": "local", **import_os_env()}, capture_output=True, text=True)
            if res.returncode != 0 or '"busy"' in res.stdout:
                print(f"Failed to submit {packet_id}:\\n{res.stdout}\\n{res.stderr}")
                sys.exit(1)
            else:
                print(f"Success {packet_id}")

def import_os_env():
    import os
    return dict(os.environ)

if __name__ == "__main__":
    main()
