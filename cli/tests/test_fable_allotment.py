import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
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


def with_slug(args: list[str], slug: str) -> list[str]:
    out = list(args)
    out[out.index("--slug") + 1] = slug
    return out


def receipt_data(category: str, percent: float) -> dict:
    now = datetime.now(timezone.utc)
    monday = (now - timedelta(days=now.weekday())).date().isoformat()
    return {
        "schema": "limen.fable_acceptance.v1",
        "created_at": now.isoformat().replace("+00:00", "Z"),
        "week": monday,
        "category": category,
        "percent": percent,
        "slug": f"{category}-{percent}",
        "why": "test",
        "sources": ["docs/fable-allotment.md"],
        "redacted_packets": [],
        "verification": ["python3 scripts/fable-allotment.py audit"],
        "reserve_unlocked": category == "reserve",
    }


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


def test_weekly_category_cap_is_cumulative(tmp_path):
    receipts_dir = tmp_path / "receipts"
    first = run_fable(*with_slug(base_accept_args(receipts_dir, category="governance", percent="6"), "g1"))
    assert first.returncode == 0, first.stderr
    second = run_fable(*with_slug(base_accept_args(receipts_dir, category="governance", percent="5"), "g2"))
    assert second.returncode == 2
    assert "governance weekly spend would be 11%" in second.stderr

    # Audit also catches an already-bad receipt directory, not just future accept commands.
    bad_dir = tmp_path / "bad-receipts"
    bad_dir.mkdir()
    (bad_dir / "a.json").write_text(json.dumps(receipt_data("adversarial-review", 3)))
    (bad_dir / "b.json").write_text(json.dumps(receipt_data("adversarial-review", 3)))
    audit = run_fable("audit", "--receipts-dir", str(bad_dir))
    assert audit.returncode == 2
    assert "adversarial-review spend 6% exceeds category cap 5%" in audit.stdout


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
    assert "governance weekly spend would be 11%" in extra.stderr

    audit = run_fable("audit", "--receipts-dir", str(receipts_dir))
    assert audit.returncode == 0, audit.stderr
    report = json.loads(audit.stdout)
    assert report["deliberate_percent"] == 40
    assert report["total_percent"] == 40


def _this_monday() -> str:
    now = datetime.now(timezone.utc)
    return (now - timedelta(days=now.weekday())).date().isoformat()


def test_balance_writes_current_week_report(tmp_path):
    """`balance` writes logs/fable-allotment.json with the cap fields for the current ISO-week."""
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    empty_transcripts = tmp_path / "no-transcripts"
    empty_transcripts.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "balance"],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(root),
            "LIMEN_CLAUDE_TRANSCRIPTS_DIR": str(empty_transcripts),
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["week"] == _this_monday()
    assert out["deliberate_cap"] == 40 and out["hard_cap"] == 50
    assert out["spent_tokens"] == 0 and out["spent_pct"] == 0.0
    assert out["over_cap"] is False
    written = json.loads((root / "logs" / "fable-allotment.json").read_text())
    assert written == out


def _write_fable_transcript(projects_dir: Path, tokens: tuple[int, int, int] = (100, 200, 300)):
    """One relocated-layout transcript holding a fresh Fable usage record."""
    session_dir = projects_dir / "proj"
    session_dir.mkdir(parents=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message": {
            "model": "claude-fable-5",
            "usage": {
                "input_tokens": tokens[0],
                "output_tokens": tokens[1],
                "cache_creation_input_tokens": tokens[2],
            },
        },
    }
    (session_dir / "s.jsonl").write_text(json.dumps(record) + "\n")


def test_balance_reads_relocated_agent_runtime_tree(tmp_path):
    """With no transcripts env, balance resolves via harness_paths and finds the repo-local
    .agent-runtime tree — the relocation that blinded the meter for five weeks."""
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    _write_fable_transcript(root / ".agent-runtime" / "claude" / "projects")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "balance"],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(root),
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["week"] == _this_monday()
    assert out["spent_tokens"] == 600
    assert out["source"] == "transcript-token-sum"


def test_transcripts_env_override_wins_over_relocated(tmp_path):
    """An explicit LIMEN_CLAUDE_TRANSCRIPTS_DIR pin outranks the harness_paths resolution."""
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    _write_fable_transcript(root / ".agent-runtime" / "claude" / "projects")
    empty = tmp_path / "pinned-empty"
    empty.mkdir()
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "balance"],
        capture_output=True,
        text=True,
        env={
            "LIMEN_ROOT": str(root),
            "LIMEN_CLAUDE_TRANSCRIPTS_DIR": str(empty),
            "PATH": __import__("os").environ.get("PATH", ""),
        },
    )
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert out["spent_tokens"] == 0


def test_balance_is_idempotent(tmp_path):
    """Re-running balance on the same inputs produces an identical file (fixed point)."""
    root = tmp_path / "root"
    (root / "logs").mkdir(parents=True)
    empty = tmp_path / "t"
    empty.mkdir()
    env = {
        "LIMEN_ROOT": str(root),
        "LIMEN_CLAUDE_TRANSCRIPTS_DIR": str(empty),
        "PATH": __import__("os").environ.get("PATH", ""),
    }
    subprocess.run([sys.executable, str(SCRIPT), "balance"], capture_output=True, text=True, env=env)
    first = (root / "logs" / "fable-allotment.json").read_text()
    subprocess.run([sys.executable, str(SCRIPT), "balance"], capture_output=True, text=True, env=env)
    assert (root / "logs" / "fable-allotment.json").read_text() == first
