from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from click.testing import CliRunner

from limen.cli import main
from limen.models import LimenFile
from limen.progress import build_progress_snapshot, progress_bar, render_progress


SOURCE_PATHS = {
    "omega": "logs/omega.json",
    "handoff": "logs/handoff.json",
    "prompt_authority": "docs/prompt-authority-seal.json",
    "lifecycle": "logs/session-lifecycle-pressure.json",
    "mail": "logs/uma-mail-status.json",
    "contributions": "logs/contributions.json",
    "financial": "logs/financial-organ-state.json",
    "portfolio": "logs/portfolio-debt.json",
}


def _write_source(root: Path, source_id: str, payload: dict[str, object]) -> None:
    path = root / SOURCE_PATHS[source_id]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _board() -> LimenFile:
    return LimenFile.model_validate(
        {
            "portal": {"budget": {"track": {"date": "2026-07-13"}}},
            "tasks": [
                {
                    "id": "DUE-1",
                    "title": "Pay a real obligation",
                    "repo": "organvm/finance",
                    "target_agent": "claude",
                    "priority": "critical",
                    "status": "open",
                    "labels": [
                        "origin:obligation",
                        "horizon:present",
                        "due:2026-07-14",
                        "money",
                    ],
                    "predicate": "test -f receipt.json",
                    "receipt_target": "git:organvm/finance:receipts/DUE-1.json",
                    "value_case": "Clears a time-bound financial liability",
                    "created": "2026-07-13",
                },
                {
                    "id": "ASK-1",
                    "title": "Finish the explicit ask",
                    "repo": "organvm/limen",
                    "target_agent": "codex",
                    "priority": "high",
                    "status": "in_progress",
                    "labels": [
                        "origin:human-prompt",
                        "horizon:present",
                        "contributions",
                    ],
                    "created": "2026-07-13",
                },
                {
                    "id": "PAST-1",
                    "title": "Preserve old work",
                    "repo": "organvm/limen",
                    "target_agent": "jules",
                    "priority": "medium",
                    "status": "needs_human",
                    "labels": ["origin:system-debt", "horizon:past"],
                    "created": "2026-07-12",
                },
                {
                    "id": "DONE-1",
                    "title": "Already shipped",
                    "repo": "organvm/limen",
                    "target_agent": "codex",
                    "priority": "low",
                    "status": "done",
                    "labels": ["origin:agent-recommendation", "horizon:future"],
                    "predicate": "true",
                    "receipt_target": "https://example.invalid/pr/1",
                    "created": "2026-07-11",
                },
            ],
        }
    )


def test_snapshot_keeps_origins_horizons_and_unknown_coverage_distinct(
    tmp_path: Path,
) -> None:
    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )

    assert snapshot["summary"]["total"] == 4
    assert snapshot["summary"]["complete"] == 1
    assert snapshot["summary"]["board_debt"] == 3
    assert snapshot["summary"]["active_debt"] == 3
    assert snapshot["summary"]["coverage_debt"] == 8
    assert snapshot["summary"]["verified_receipt_debt"] == 1
    assert snapshot["summary"]["closure_pct"] == 25.0
    assert snapshot["summary"]["contract_ready_active"] == 1
    assert snapshot["summary"]["underwritten_active"] == 1
    assert snapshot["summary"]["underwriting_denial_counts"] == {
        "task-not-underwritten:value_case,predicate,receipt_target": 2,
    }
    assert snapshot["summary"]["underwriting_coverage_pct"] == 33.3
    assert snapshot["summary"]["requested_active_debit_runs"] == 3
    assert snapshot["summary"]["underwritten_active_debit_runs"] == 1
    assert snapshot["summary"]["ununderwritten_active_debit_runs"] == 2
    assert snapshot["summary"]["debit_underwriting_coverage_pct"] == 33.3
    assert snapshot["summary"]["forecast_credit_active"] == 1
    assert snapshot["summary"]["forecast_credit_coverage_pct"] == 33.3
    assert snapshot["summary"]["board_credit_claims"] == 1
    assert snapshot["summary"]["unsubstantiated_terminal_claims"] == 0
    assert snapshot["summary"]["credit_claim_contract_pct"] == 100.0
    assert snapshot["summary"]["origin_coverage_pct"] == 100.0
    assert snapshot["summary"]["horizon_coverage_pct"] == 100.0
    assert snapshot["summary"]["due_metadata_coverage_pct"] == 33.3
    assert snapshot["scope"] == "partial"
    assert snapshot["surface"] == "board_progress_and_source_coverage_lens"
    by_origin = {row["origin"]: row for row in snapshot["dimensions"]["origin"]}
    assert set(by_origin) == {
        "obligation",
        "human_prompt",
        "system_debt",
        "agent_recommendation",
    }
    assert snapshot["dimensions"]["source_lineage"][0]["source_lineage"] == "unknown"


def test_snapshot_marks_missing_sensors_dark_and_does_not_invent_zero(
    tmp_path: Path,
) -> None:
    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    assert snapshot["summary"]["source_freshness_pct"] == 0.0
    assert snapshot["summary"]["source_readiness_pct"] == 0.0
    assert snapshot["summary"]["coverage_debt"] == 8
    assert {row["status"] for row in snapshot["source_coverage"]} == {"dark"}


def test_fresh_semantic_source_debt_never_becomes_ready(tmp_path: Path) -> None:
    generated_at = "2026-07-13T11:30:00Z"
    _write_source(tmp_path, "omega", {"generated_at": generated_at, "status": "partial"})
    _write_source(tmp_path, "handoff", {"generated_at": generated_at, "verdict": "BROKEN"})
    _write_source(tmp_path, "prompt_authority", {"generated_at": generated_at, "capped": True})
    _write_source(tmp_path, "lifecycle", {"generated_at": generated_at, "available": False})
    _write_source(tmp_path, "mail", {"generated_at": generated_at, "complete": False})
    for source_id in ("contributions", "financial", "portfolio"):
        _write_source(
            tmp_path,
            source_id,
            {
                "generated_at": generated_at,
                "status": "ready",
                "complete": True,
                "exhaustive": True,
            },
        )

    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    by_id = {row["id"]: row for row in snapshot["source_coverage"]}

    assert by_id["omega"]["status"] == "partial"
    assert by_id["handoff"]["status"] == "failed"
    assert by_id["prompt_authority"]["status"] == "capped"
    assert by_id["lifecycle"]["status"] == "unavailable"
    assert by_id["mail"]["status"] == "incomplete"
    assert {by_id[source_id]["status"] for source_id in ("contributions", "financial", "portfolio")} == {"ready"}
    assert snapshot["summary"]["source_freshness_pct"] == 100.0
    assert snapshot["summary"]["source_readiness_pct"] == 37.5
    assert snapshot["summary"]["coverage_debt"] == 5


def test_non_exhaustive_source_is_capped_debt(tmp_path: Path) -> None:
    _write_source(
        tmp_path,
        "portfolio",
        {
            "generated_at": "2026-07-13T11:30:00Z",
            "status": "ready",
            "complete": True,
            "exhaustive": False,
        },
    )

    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    portfolio = next(row for row in snapshot["source_coverage"] if row["id"] == "portfolio")

    assert portfolio["status"] == "capped"
    assert "capped" in portfolio["debt_reasons"]


def test_explicit_false_scope_inclusion_is_partial_debt(tmp_path: Path) -> None:
    _write_source(
        tmp_path,
        "portfolio",
        {
            "generated_at": "2026-07-13T11:30:00Z",
            "status": "ready",
            "scope": {
                "source": "remote API",
                "local_only_and_other_forges_included": False,
            },
        },
    )

    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    portfolio = next(row for row in snapshot["source_coverage"] if row["id"] == "portfolio")

    assert portfolio["status"] == "partial"
    assert "partial" in portfolio["debt_reasons"]


def test_explicit_false_completeness_is_incomplete_debt(tmp_path: Path) -> None:
    _write_source(
        tmp_path,
        "portfolio",
        {
            "generated_at": "2026-07-13T11:30:00Z",
            "status": "ready",
            "completeness": False,
        },
    )

    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    portfolio = next(row for row in snapshot["source_coverage"] if row["id"] == "portfolio")

    assert portfolio["status"] == "incomplete"
    assert "incomplete" in portfolio["debt_reasons"]


def test_invalid_nonempty_timestamp_is_freshness_debt(tmp_path: Path) -> None:
    _write_source(
        tmp_path,
        "handoff",
        {"generated_at": "not-a-timestamp", "status": "ready"},
    )

    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    handoff = next(row for row in snapshot["source_coverage"] if row["id"] == "handoff")

    assert handoff["semantic_status"] == "ready"
    assert handoff["freshness_status"] == "failed"
    assert handoff["status"] == "failed"
    assert "failed" in handoff["debt_reasons"]


def test_nested_incomplete_and_fresh_stale_flags_are_debt(tmp_path: Path) -> None:
    generated_at = "2026-07-13T11:30:00Z"
    _write_source(
        tmp_path,
        "lifecycle",
        {"generated_at": generated_at, "worktrees": {"complete": False}},
    )
    _write_source(
        tmp_path,
        "contributions",
        {"generated_at": generated_at, "status": "ready", "stale": True},
    )

    snapshot = build_progress_snapshot(
        _board(),
        tmp_path,
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    by_id = {row["id"]: row for row in snapshot["source_coverage"]}

    assert by_id["lifecycle"]["status"] == "incomplete"
    assert by_id["contributions"]["status"] == "stale"
    assert by_id["contributions"]["freshness_status"] == "ready"


def test_snapshot_content_addresses_board_and_source_inputs(tmp_path: Path) -> None:
    now = datetime(2026, 7, 13, 12, tzinfo=UTC)
    first = build_progress_snapshot(_board(), tmp_path, now=now)
    second = build_progress_snapshot(_board(), tmp_path, now=now)

    assert first["input_contract"] == second["input_contract"]
    assert len(first["input_contract"]["board"]["normalized_sha256"]) == 64
    assert len(first["input_contract"]["sha256"]) == 64

    _write_source(
        tmp_path,
        "omega",
        {"generated_at": "2026-07-13T11:30:00Z", "status": "ready", "complete": True},
    )
    changed = build_progress_snapshot(_board(), tmp_path, now=now)

    assert changed["input_contract"]["sha256"] != first["input_contract"]["sha256"]
    omega = next(row for row in changed["source_coverage"] if row["id"] == "omega")
    assert len(omega["content_sha256"]) == 64
    assert len(omega["normalized_sha256"]) == 64


def test_source_contract_hash_normalizes_valid_json_formatting(tmp_path: Path) -> None:
    now = datetime(2026, 7, 13, 12, tzinfo=UTC)
    path = tmp_path / SOURCE_PATHS["omega"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"generated_at":"2026-07-13T11:30:00Z","status":"ready","complete":true}',
        encoding="utf-8",
    )
    compact = build_progress_snapshot(_board(), tmp_path, now=now)
    compact_omega = next(row for row in compact["source_coverage"] if row["id"] == "omega")

    path.write_text(
        '{\n  "complete": true,\n  "status": "ready",\n  "generated_at": "2026-07-13T11:30:00Z"\n}\n',
        encoding="utf-8",
    )
    reformatted = build_progress_snapshot(_board(), tmp_path, now=now)
    reformatted_omega = next(row for row in reformatted["source_coverage"] if row["id"] == "omega")

    assert compact_omega["content_sha256"] != reformatted_omega["content_sha256"]
    assert compact_omega["normalized_sha256"] == reformatted_omega["normalized_sha256"]
    assert compact["input_contract"]["sha256"] == reformatted["input_contract"]["sha256"]

    path.write_text(
        '{"generated_at":"2026-07-13T11:30:00Z","status":"partial","complete":true}',
        encoding="utf-8",
    )
    changed = build_progress_snapshot(_board(), tmp_path, now=now)
    assert changed["input_contract"]["sha256"] != compact["input_contract"]["sha256"]


def test_verified_receipt_debt_requires_explicit_evidence(tmp_path: Path) -> None:
    unverified = build_progress_snapshot(_board(), tmp_path)
    board = _board().model_dump(mode="json")
    board["tasks"][-1]["receipt_verified"] = True
    verified = build_progress_snapshot(LimenFile.model_validate(board), tmp_path)

    assert unverified["summary"]["verified_receipt_claims"] == 0
    assert unverified["summary"]["verified_receipt_debt"] == 1
    assert verified["summary"]["verified_receipt_claims"] == 1
    assert verified["summary"]["verified_receipt_debt"] == 0


def test_render_supports_macro_and_micro_zoom() -> None:
    snapshot = build_progress_snapshot(
        _board(),
        Path("."),
        now=datetime(2026, 7, 13, 12, tzinfo=UTC),
    )
    rendered = render_progress(snapshot, view="origin", scope="human_prompt", ascii_only=True, limit=None)
    assert "BOARD CLOSURE" in rendered
    assert "WORK LOANS" in rendered
    assert "CAPITAL DEBITS" in rendered
    assert "CREDIT FORECAST" in rendered
    assert "CREDIT CLAIMS" in rendered
    assert "VERIFIED CREDIT" in rendered
    assert "DEBT COUNTS" in rendered
    assert "ORIGIN ZOOM" in rendered
    assert "human_prompt" in rendered
    assert "debit=" in rendered
    assert "underwritten=" in rendered
    assert "funded=" not in rendered
    assert "ASK-1" in rendered
    assert "DEBIT:1" in rendered
    assert "CREDIT:DARK" in rendered
    assert "DUE-1" not in rendered
    assert "never estimated effort" in rendered
    assert "scope=partial" in rendered
    assert "Limen board progress + source coverage" in rendered
    assert progress_bar(50, width=10, ascii_only=True) == "[#####.....]"


def test_progress_cli_prints_partial_json_lens(tmp_path: Path, monkeypatch) -> None:
    board = _board().model_dump(mode="json")
    (tmp_path / "tasks.yaml").write_text(json.dumps(board), encoding="utf-8")
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))

    result = CliRunner().invoke(main, ["progress", "--json-output"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["schema"] == "limen.progress-universe.v1"
    assert payload["surface_schema"] == "limen.board-progress-source-coverage.v1"
    assert payload["scope"] == "partial"
    assert len(payload["tasks"]) == 4


def test_progress_cli_can_write_a_bounded_receipt(tmp_path: Path, monkeypatch) -> None:
    board = _board().model_dump(mode="json")
    (tmp_path / "tasks.yaml").write_text(json.dumps(board), encoding="utf-8")
    receipt = tmp_path / "logs" / "board-progress-source-coverage.json"
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))

    result = CliRunner().invoke(
        main,
        ["progress", "--level", "macro", "--ascii", "--report-file", str(receipt)],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["summary"]["active_debt"] == 3
    assert payload["summary"]["board_debt"] == 3
    assert payload["summary"]["coverage_debt"] == 8
    assert payload["summary"]["requested_active_debit_runs"] == 3
    assert len(payload["tasks"]) == 4
