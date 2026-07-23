from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from click.testing import CliRunner
from limen.cli import main
from limen.progress_source_registry import (
    REGISTRATION_SCHEMA,
    REPORT_SCHEMA,
    build_source_registry,
)

NOW = datetime(2026, 7, 21, 12, tzinfo=UTC)


def _write_report(
    root: Path,
    source_id: str,
    *,
    status: str = "ready",
    exhaustive: bool = True,
    generated_at: str = "2026-07-21T11:59:00Z",
    leaf_count: int = 3,
    cursor: object = None,
) -> Path:
    token = sha256(source_id.encode()).hexdigest()[:16]
    path = root / "runtime" / f"{token}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": REPORT_SCHEMA,
                "source_id": source_id,
                "cursor": cursor,
                "exhaustive": exhaustive,
                "generated_at": generated_at,
                "content_sha256": sha256(f"content:{source_id}".encode()).hexdigest(),
                "semantic_status": status,
                "normalized_leaf_count": leaf_count,
            }
        )
    )
    return path


def _register(root: Path, source_id: str, *, report_path: str | None = None, required: bool = True) -> Path:
    directory = root / "registry"
    directory.mkdir(parents=True, exist_ok=True)
    token = sha256(source_id.encode()).hexdigest()[:16]
    path = directory / f"{token}.json"
    path.write_text(
        json.dumps(
            {
                "schema": REGISTRATION_SCHEMA,
                "source_id": source_id,
                "owner": {"id": f"owner/{source_id}", "surface": f"receipt:{source_id}"},
                "report_path": report_path or f"runtime/{token}.json",
                "required": required,
                "max_age_seconds": 3600,
            }
        )
    )
    return path


def test_registry_discovers_arbitrary_added_removed_and_renamed_sources(tmp_path: Path) -> None:
    for source_id in ("renamed-owner/private-estate", "zeta"):
        _register(tmp_path, source_id)
        _write_report(tmp_path, source_id, cursor={"page": 2})

    first = build_source_registry(tmp_path, registration_dirs=[tmp_path / "registry"], now=NOW)

    assert [row["source_id"] for row in first["sources"]] == ["renamed-owner/private-estate", "zeta"]
    assert first["semantic_status"] == "ready"
    assert first["summary"] == {
        "source_count": 2,
        "required_source_count": 2,
        "ready_required_source_count": 2,
        "coverage_debt": 0,
        "unknown_leaf_count_sources": 0,
        "known_normalized_leaf_count": 6,
        "normalized_leaf_count": 6,
    }
    row = first["sources"][0]
    assert row["owner"] == {
        "id": "owner/renamed-owner/private-estate",
        "surface": "receipt:renamed-owner/private-estate",
    }
    assert row["cursor"] == {"page": 2}
    assert row["exhaustive"] is True
    assert row["content_sha256"] == sha256(b"content:renamed-owner/private-estate").hexdigest()

    (tmp_path / "registry" / f"{sha256(b'zeta').hexdigest()[:16]}.json").unlink()
    _register(tmp_path, "new-source")
    _write_report(tmp_path, "new-source", leaf_count=5)
    second = build_source_registry(tmp_path, registration_dirs=[tmp_path / "registry"], now=NOW)

    assert [row["source_id"] for row in second["sources"]] == ["new-source", "renamed-owner/private-estate"]
    assert second["summary"]["normalized_leaf_count"] == 8


def test_missing_report_is_debt_and_unknown_leaf_count_is_not_zero(tmp_path: Path) -> None:
    _register(tmp_path, "prompt-lineage")

    registry = build_source_registry(tmp_path, registration_dirs=[tmp_path / "registry"], now=NOW)
    source = registry["sources"][0]

    assert source["semantic_status"] == "unavailable"
    assert source["normalized_leaf_count"] is None
    assert source["coverage_debt"] is True
    assert registry["summary"]["coverage_debt"] == 1
    assert registry["summary"]["unknown_leaf_count_sources"] == 1
    assert registry["summary"]["known_normalized_leaf_count"] == 0
    assert registry["summary"]["normalized_leaf_count"] is None


def test_non_exhaustive_ready_and_stale_reports_fail_closed(tmp_path: Path) -> None:
    _register(tmp_path, "github-estate", required=False)
    _write_report(tmp_path, "github-estate", exhaustive=False, leaf_count=1068)
    _register(tmp_path, "mail")
    _write_report(tmp_path, "mail", generated_at="2026-07-20T00:00:00Z")

    registry = build_source_registry(tmp_path, registration_dirs=[tmp_path / "registry"], now=NOW)
    sources = {row["source_id"]: row for row in registry["sources"]}

    assert sources["github-estate"]["reported_semantic_status"] == "ready"
    assert sources["github-estate"]["semantic_status"] == "partial"
    assert sources["github-estate"]["debt_reasons"] == ["non-exhaustive-ready-claim"]
    assert sources["mail"]["semantic_status"] == "stale"
    assert "report-stale" in sources["mail"]["debt_reasons"]
    assert registry["summary"]["coverage_debt"] == 2


def test_duplicate_malformed_and_unavailable_roots_remain_discovery_debt(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    for directory in (first, second):
        directory.mkdir()
    registration = {
        "schema": REGISTRATION_SCHEMA,
        "source_id": "same-source",
        "owner": {"id": "owner", "surface": "surface"},
        "report_path": "runtime/same-source.json",
        "required": True,
        "max_age_seconds": 60,
    }
    (first / "a.json").write_text(json.dumps(registration))
    (second / "b.json").write_text(json.dumps(registration))
    (first / "broken.json").write_text("{")

    registry = build_source_registry(
        tmp_path,
        registration_dirs=[first, second, tmp_path / "absent"],
        now=NOW,
    )

    by_id = {row["source_id"]: row for row in registry["sources"]}
    assert by_id["same-source"]["semantic_status"] == "failed"
    assert by_id["same-source"]["debt_reasons"] == ["duplicate-source-registration"]
    assert any(source_id.startswith("invalid-registration-") for source_id in by_id)
    assert registry["discovery"]["exhaustive"] is False
    assert registry["discovery"]["debt_reasons"] == ["registration-root-unavailable"]
    assert registry["summary"]["coverage_debt"] == 3


def test_empty_registry_is_unknown_coverage_debt(tmp_path: Path) -> None:
    directory = tmp_path / "registry"
    directory.mkdir()

    registry = build_source_registry(tmp_path, registration_dirs=[directory], now=NOW)

    assert registry["semantic_status"] == "unknown"
    assert registry["discovery"]["exhaustive"] is True
    assert registry["sources"] == []
    assert registry["summary"]["coverage_debt"] == 1
    assert registry["summary"]["normalized_leaf_count"] is None


def test_cli_exposes_the_same_runtime_discovered_registry(tmp_path: Path) -> None:
    _register(tmp_path, "board")
    _write_report(tmp_path, "board", leaf_count=3025)

    result = CliRunner().invoke(
        main,
        ["progress-sources", "--registry-dir", str(tmp_path / "registry"), "--json-output"],
        env={"LIMEN_ROOT": str(tmp_path)},
    )

    assert result.exit_code == 0, result.output
    registry = json.loads(result.output)
    assert registry["sources"][0]["source_id"] == "board"
    assert registry["summary"]["normalized_leaf_count"] == 3025
