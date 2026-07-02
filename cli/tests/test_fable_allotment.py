import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "fable-allotment.py"


def run_fable(*args):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def base_accept_args(receipts_dir: Path, category: str = "governance", percent: str = "10"):
    return [
        "accept",
        "--category",
        category,
        "--percent",
        percent,
        "--slug",
        f"{category}-run",
        "--why",
        "bounded canonical synthesis",
        "--source",
        "docs/fable-allotment.md",
        "--verification",
        "python3 scripts/fable-allotment.py audit",
        "--receipts-dir",
        str(receipts_dir),
    ]


def test_accept_writes_receipt_and_env_export(tmp_path):
    receipts_dir = tmp_path / "receipts"
    proc = run_fable(*base_accept_args(receipts_dir))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads("\n".join(proc.stdout.splitlines()[:-1]))
    receipt = Path(payload["receipt"])
    assert receipt.exists()
    data = json.loads(receipt.read_text())
    assert data["category"] == "governance"
    assert data["percent"] == 10
    assert "export LIMEN_FABLE_ACCEPTANCE=" in proc.stdout


def test_category_cap_and_reserve_lock_are_enforced(tmp_path):
    receipts_dir = tmp_path / "receipts"
    over = run_fable(*base_accept_args(receipts_dir, category="governance", percent="11"))
    assert over.returncode == 2
    assert "above category cap" in over.stderr

    reserve = run_fable(*base_accept_args(receipts_dir, category="reserve", percent="5"))
    assert reserve.returncode == 2
    assert "reserve spend requires --reserve-unlock" in reserve.stderr


def test_audit_fails_when_deliberate_cap_is_exceeded(tmp_path):
    receipts_dir = tmp_path / "receipts"
    for category, percent in (
        ("substrate", "15"),
        ("prompt-corpus", "10"),
        ("governance", "10"),
        ("adversarial-review", "5"),
    ):
        proc = run_fable(*base_accept_args(receipts_dir, category=category, percent=percent))
        assert proc.returncode == 0, proc.stderr

    extra = run_fable(*base_accept_args(receipts_dir, category="governance", percent="1"))
    assert extra.returncode == 2
    assert "deliberate Fable spend would be 41%" in extra.stderr

    audit = run_fable("audit", "--receipts-dir", str(receipts_dir))
    assert audit.returncode == 0, audit.stderr
    report = json.loads(audit.stdout)
    assert report["deliberate_percent"] == 40
    assert report["total_percent"] == 40
