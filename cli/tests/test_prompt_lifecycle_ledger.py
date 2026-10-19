from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prompt-lifecycle-ledger.py"


def _load():
    spec = importlib.util.spec_from_file_location("prompt_lifecycle_ledger", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_malformed_lane_timeout_uses_default_dispatch_grace(monkeypatch):
    monkeypatch.setenv("LIMEN_LANE_TIMEOUT", "not-an-int")
    monkeypatch.setenv("LIMEN_GH_RECEIPT_RETRIES", "also-bad")
    pll = _load()

    assert pll.DISPATCH_GRACE_SECONDS == 1500
    assert pll.GH_RETRIES == 3


def test_cloud_receipts_uses_configured_runtime_fallback(tmp_path: Path, monkeypatch):
    pll = _load()
    pll.ROOT = tmp_path
    (tmp_path / "runtime.config.json").write_text('{"apiUrl":"https://runtime.example"}')
    for name in ("LIMEN_WORKER_URL", "NEXT_PUBLIC_API_URL", "LIMEN_API_URL"):
        monkeypatch.delenv(name, raising=False)
    seen = []

    def fake_probe(url, **_kwargs):
        seen.append(url)
        return {"url": url, "ok": True}

    monkeypatch.setattr(pll, "probe_url", fake_probe)

    receipt = pll.cloud_receipts()

    assert receipt["runtime_url_configured"] is True
    assert "https://runtime.example/health" in seen
    assert receipt["env_flags"]["LIMEN_API_URL"] is False


def test_task_snapshot_distinguishes_jules_async_from_stranded_no_pr(tmp_path: Path):
    pll = _load()
    pll.ROOT = tmp_path
    pll.TASKS_PATH = tmp_path / "tasks.yaml"
    (tmp_path / "logs" / "async-runs").mkdir(parents=True)
    pll.TASKS_PATH.write_text(
        """
tasks:
  - id: JULES-ASYNC
    status: dispatched
    target_agent: jules
    updated: '2020-01-01T00:00:00Z'
    dispatch_log:
      - status: dispatched
        session_id: '123456789'
  - id: LOCAL-STRANDED
    status: dispatched
    target_agent: codex
    updated: '2020-01-01T00:00:00Z'
    dispatch_log:
      - status: dispatched
        session_id: cli
  - id: LOCAL-RUNNING
    status: dispatched
    target_agent: opencode
    updated: '2999-01-01T00:00:00Z'
    dispatch_log:
      - status: dispatched
        session_id: reserve
  - id: WITH-PR
    status: dispatched
    target_agent: codex
    updated: '2020-01-01T00:00:00Z'
    dispatch_log:
      - status: dispatched
        session_id: https://github.com/organvm/limen/pull/1
  - id: CHRONIC
    status: open
    target_agent: codex
    dispatch_log:
      - status: open
      - status: open
      - status: open
  - id: DONE-PR
    status: done
    target_agent: codex
    dispatch_log:
      - status: done
        session_id: https://github.com/organvm/limen/pull/2
""",
        encoding="utf-8",
    )

    snap = pll.load_task_snapshot([])

    assert snap["dispatched_jules_async"] == 1
    assert snap["dispatched_without_pr_receipt"] == 1
    assert snap["dispatched_running"] == 1
    assert snap["dispatched_with_pr_receipt"] == 1
    assert snap["chronic_reopen_candidates"] == 1
    assert snap["done_with_pr_receipt"] == 1


def _ledger_sessions(store: Path) -> tuple[dict[str, dict], object]:
    pll = _load()
    pll.OPENCODE_DB = store
    return {s["session_id_hash"]: s for s in pll.opencode_virtual_sessions(None)}, pll


def test_opencode_ledger_keeps_legacy_rows_authoritative_and_adds_the_v2_tail(opencode_migrated_store: Path) -> None:
    sessions, pll = _ledger_sessions(opencode_migrated_store)
    frozen = sessions[pll.stable_hash("frozen", 20)]
    v2_only = sessions[pll.stable_hash("v2-only", 20)]

    # The migrated session keeps the legacy prompt exactly as the ledger already recorded it (synthetic text
    # included), then gains the post-freeze turn that only v2 holds.
    assert frozen["prompt_hashes"] == [pll.full_hash("Frozen ask\n\nInjected note"), pll.full_hash("Tail ask")]
    assert frozen["event_count"] == 2 + 4 + 1, "legacy messages + parts + the v2 tail"
    # A v2-only session was invisible to the legacy readers; its idle row is not a turn.
    assert v2_only["prompt_hashes"] == [pll.full_hash("V2 ask")]
    assert v2_only["event_count"] == 2


def test_opencode_ledger_on_a_legacy_only_store_sees_no_v2_sessions(opencode_migrated_store: Path) -> None:
    with sqlite3.connect(opencode_migrated_store) as db:
        db.execute("DROP TABLE session_v2")
        db.execute("DROP TABLE session_message")
    sessions, pll = _ledger_sessions(opencode_migrated_store)

    assert set(sessions) == {pll.stable_hash("frozen", 20)}
    assert sessions[pll.stable_hash("frozen", 20)]["prompt_hashes"] == [pll.full_hash("Frozen ask\n\nInjected note")]


def test_opencode_ledger_survives_dropped_legacy_message_tables(opencode_migrated_store: Path) -> None:
    with sqlite3.connect(opencode_migrated_store) as db:
        db.execute("DROP TABLE message")
        db.execute("DROP TABLE part")
    sessions, pll = _ledger_sessions(opencode_migrated_store)

    assert sessions[pll.stable_hash("v2-only", 20)]["prompt_hashes"] == [pll.full_hash("V2 ask")]
    assert sessions[pll.stable_hash("frozen", 20)]["prompt_hashes"] == [pll.full_hash("Tail ask")]
