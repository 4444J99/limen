"""Read-only handoff predicate; never claims implementation or estate completion."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIVATE = ROOT / ".limen-workstream"
PUBLIC_MODULES = (
    "README.md",
    "intent.md",
    "runtime.md",
    "closeout.md",
    "workstream.json",
    "launch.sh",
)
PRIVATE_MODULES = (
    "README.md",
    "manifest.md",
    "workstream.json",
    "workstream-contract.py",
    "intent.md",
    "runtime.md",
    "closeout.md",
    "kickstart.sh",
)

for name in PUBLIC_MODULES:
    assert (HERE / name).is_file(), name

receipt = json.loads((HERE / "workstream.json").read_text(encoding="utf-8"))
helper = PRIVATE / "workstream-contract.py"
spec = importlib.util.spec_from_file_location("capsule_contract", helper)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.validate_workstream_receipt(receipt)

contract = json.loads((PRIVATE / "workstream.json").read_text(encoding="utf-8"))
assert receipt["contract"] == contract
assert contract["schema"] == "limen.workstream.contract.v3"
assert contract["authorization"]["sandbox"] == "danger-full-access"
assert contract["authorization"]["approval_mode"] == "never"
assert contract["authorization"]["retained_gates"] == [
    "destructive",
    "credential",
    "paid_spend",
    "public_send",
    "runtime_or_host_mutation",
]
assert 0 < contract["runway"]["duration_seconds"] <= 5400
assert receipt["predecessor"]["slug"] == "spine-closeout-20260916"
assert receipt["predecessor"]["branch"] == "work/spine-closeout-20260916"

branch = subprocess.check_output(
    ["git", "-C", str(ROOT), "branch", "--show-current"],
    text=True,
).strip()
assert branch == receipt["branch"]

identity = json.loads((PRIVATE / "capsule.identity").read_text(encoding="utf-8"))
args = [
    sys.executable,
    str(helper),
    "verify-identity",
    "--identity",
    str(PRIVATE / "capsule.identity"),
    "--invocation-sha256",
    identity["invocation_sha256"],
]
for name in PRIVATE_MODULES:
    args += ["--module", f"{name}={PRIVATE / name}"]
subprocess.run(args, check=True, stdout=subprocess.DEVNULL)

kickstart = (PRIVATE / "kickstart.sh").read_text(encoding="utf-8")
assert "launch_sandbox=danger-full-access" in kickstart
assert "conduct=1" in kickstart
assert kickstart.count("--dangerously-bypass-approvals-and-sandbox") == 1
assert "codex_args+=(--dangerously-bypass-approvals-and-sandbox)" in kickstart
register_at = kickstart.rindex('workstream_register_conduct_session "$agent"')
proof_at = kickstart.rindex('if [[ "$launch_sandbox" == "danger-full-access"')
admit_at = kickstart.rindex("\nrefresh_workstream_runway\n")
assert register_at < proof_at < admit_at
subprocess.run(["bash", "-n", str(PRIVATE / "kickstart.sh")], check=True)

status = subprocess.check_output(
    ["git", "-C", str(ROOT), "status", "--porcelain"],
    text=True,
).strip()
assert not status, "owned worktree is dirty"
print("PASS: clean, finite, protected bypass-all continuation capsule; estate completion unproven")
