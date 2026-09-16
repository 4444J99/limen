"""Read-only handoff predicate; never claims estate completion."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PRIVATE = ROOT / ".limen-workstream"
for name in ("README.md", "intent.md", "runtime.md", "closeout.md", "workstream.json", "launch.sh"):
    assert (HERE / name).is_file(), name
receipt = json.loads((HERE / "workstream.json").read_text())
helper = PRIVATE / "workstream-contract.py"
spec = importlib.util.spec_from_file_location("capsule_contract", helper)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.validate_workstream_receipt(receipt)
contract = json.loads((PRIVATE / "workstream.json").read_text())
assert receipt["contract"] == contract
assert 0 < contract["runway"]["duration_seconds"] <= 5400
branch = subprocess.check_output(["git", "-C", str(ROOT), "branch", "--show-current"], text=True).strip()
assert branch == receipt["branch"]
identity = json.loads((PRIVATE / "capsule.identity").read_text())
args = [sys.executable, str(helper), "verify-identity", "--identity", str(PRIVATE / "capsule.identity"),
        "--invocation-sha256", identity["invocation_sha256"]]
for name in ("README.md", "manifest.md", "workstream.json", "workstream-contract.py", "intent.md", "runtime.md", "closeout.md", "kickstart.sh"):
    args += ["--module", f"{name}={PRIVATE / name}"]
subprocess.run(args, check=True, stdout=subprocess.DEVNULL)
subprocess.run(["bash", "-n", str(PRIVATE / "kickstart.sh")], check=True)
assert not subprocess.check_output(["git", "-C", str(ROOT), "status", "--porcelain"], text=True).strip(), "owned worktree is dirty"
print("PASS: clean, finite, intact continuation capsule; estate completion unproven")
