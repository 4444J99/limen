"""Inventory admission consumes the existing collector's emitted receipts."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest

from limen.github_estate_census import _canonical_sha256
from limen.inventory_admission import InventoryAdmissionError, inventory_count


NOW = datetime(2026, 9, 8, 16, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


def _load_collector():
    spec = importlib.util.spec_from_file_location(
        "inventory_actual_collector", ROOT / "scripts/github-estate-census.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _emit(monkeypatch, tmp_path, total, *, metadata_available=True):
    collector = _load_collector()
    gitvs = collector._gitvs()
    monkeypatch.delenv("LIMEN_OFFLINE", raising=False)
    monkeypatch.setattr(collector.shutil, "which", lambda command: "/synthetic/gh" if command == "gh" else None)
    monkeypatch.setattr(collector, "_gitvs", lambda: gitvs)
    monkeypatch.setattr(collector, "PRIVATE_CURSOR_CACHE", tmp_path / "private-cache.json")
    monkeypatch.setattr(gitvs, "load_estate", lambda: {})
    monkeypatch.setattr(gitvs, "owners", lambda _estate: ["example"])
    monkeypatch.setattr(gitvs, "_resolve_owner_login", lambda _owner, _token: "example")
    monkeypatch.setattr(
        gitvs,
        "_owner_repo_inventory",
        lambda _owner, _token: {
            "page_count": 1,
            "repositories": [
                {
                    "name_with_owner": "example/project",
                    "repository_id": "42",
                    "private": False,
                    "archived": False,
                    "open_pr_total": total,
                }
            ],
        },
    )
    metadata = {
        "updated_at": NOW.isoformat(),
        "default_branch": "main",
        "default_sha": "a" * 40,
        "default_check_status": "no_required_checks",
        "default_check_policy": "no_required_checks",
        "default_check_policy_complete": True,
        "default_check_policy_error": None,
        "default_check_policy_receipt": {"status": "no_required_checks", "complete": True},
        "required_check_count": 0,
        "issues": 0,
        "branches": 1,
        "checks": [],
        "check_total": 0,
    }
    monkeypatch.setattr(collector, "_metadata", lambda _gitvs, _repo: metadata if metadata_available else None)
    fetched = []

    def remote_page(_gitvs, _repo, kind, cursor, *, default_sha=None):
        fetched.append(kind)
        assert cursor is None
        if kind == "branches":
            nodes = [{"name": "main", "target": {"oid": "a" * 40}}]
        else:
            assert kind == "pull_requests"
            nodes = [
                {
                    "number": number,
                    "url": f"https://example.invalid/project/pull/{number}",
                    "title": "synthetic integration work",
                    "isDraft": False,
                    "updatedAt": NOW.isoformat(),
                    "headRefName": "topic",
                    "headRefOid": "b" * 40,
                    "body": "",
                    "author": {"login": "4444J99" if number % 2 else "dependabot[bot]"},
                    "assignees": {"nodes": []},
                    "labels": {"nodes": []},
                }
                for number in range(1, total + 1)
            ]
        return {"total_count": len(nodes), "nodes": nodes, "has_next_page": False, "end_cursor": None}

    monkeypatch.setattr(collector, "_remote_page", remote_page)
    # Local host inventory is an independent authority boundary; the real remote
    # collector, classifier, paginator, builder and receipt digest run unchanged.
    monkeypatch.setattr(
        collector,
        "collect_local_git_census",
        lambda _root, **_kwargs: ({"summary": {"failure_count": 0}, "roots": [], "worktrees": []}, {}),
    )
    full, _tracked = collector.collect(workers=1)
    return full, fetched


def _count(snapshot):
    return inventory_count(
        snapshot,
        expected_repository_ids=frozenset({"42"}),
        expected_generation=snapshot["source_report"]["source_generation"],
        now=datetime.fromisoformat(snapshot["source_report"]["generated_at"].replace("Z", "+00:00")),
    )


def test_actual_collector_per_repository_generation_is_accepted(monkeypatch, tmp_path):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 2)
    assert snapshot["source_report"]["exhaustive"] is True
    generations = {cursor["source_generation"] for cursor in snapshot["cursors"]}
    assert len(generations) == 1
    assert snapshot["source_report"]["source_generation"] not in generations
    assert snapshot["repository_receipts"][0]["connection_receipt_digest"] == _canonical_sha256(snapshot["cursors"])
    assert _count(snapshot) == 1


def test_actual_collector_zero_prs_needs_no_pr_page(monkeypatch, tmp_path):
    snapshot, fetched = _emit(monkeypatch, tmp_path, 0)
    cursor = next(row for row in snapshot["cursors"] if row["kind"] == "pull_requests")
    assert cursor["expected_total"] == cursor["known_count"] == cursor["page_count"] == 0
    assert cursor["complete"] is cursor["exhaustive"] is True
    assert "pull_requests" not in fetched
    assert _count(snapshot) == 0


@pytest.mark.parametrize("field", ["expected_total", "known_count", "page_count"])
def test_zero_pr_cursor_unknown_counts_fail_closed(monkeypatch, tmp_path, field):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 0)
    snapshot["cursors"][0][field] = None
    snapshot["repository_receipts"][0]["connection_receipt_digest"] = _canonical_sha256(snapshot["cursors"])
    with pytest.raises(InventoryAdmissionError):
        _count(snapshot)


def test_actual_collector_partial_zero_is_not_empty_inventory(monkeypatch, tmp_path):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 0, metadata_available=False)
    assert snapshot["source_report"]["exhaustive"] is False
    with pytest.raises(InventoryAdmissionError, match="partial_or_unknown"):
        _count(snapshot)


@pytest.mark.parametrize(
    "change",
    [
        "cursor",
        "receipt",
        "missing_receipt",
        "inconsistent_generation",
        "incomplete_partition",
        "consistently_forged_generation",
        "metadata_identity",
    ],
)
def test_existing_repository_receipt_binds_connection_generation(monkeypatch, tmp_path, change):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 2)
    if change == "cursor":
        snapshot["cursors"][0]["source_generation"] = "f" * 64
    elif change == "receipt":
        snapshot["repository_receipts"][0]["source_generation"] = "f" * 64
    elif change == "missing_receipt":
        snapshot.pop("repository_receipts")
    elif change == "inconsistent_generation":
        snapshot["cursors"][0]["source_generation"] = "f" * 64
        snapshot["repository_receipts"][0]["connection_receipt_digest"] = _canonical_sha256(snapshot["cursors"])
    elif change == "consistently_forged_generation":
        for cursor in snapshot["cursors"]:
            cursor["source_generation"] = "f" * 64
        snapshot["repository_receipts"][0]["connection_receipt_digest"] = _canonical_sha256(snapshot["cursors"])
    elif change == "metadata_identity":
        snapshot["repositories"][0]["default_sha"] = "f" * 40
    else:
        snapshot["cursors"][1]["complete"] = False
        snapshot["repository_receipts"][0]["connection_receipt_digest"] = _canonical_sha256(snapshot["cursors"])
    with pytest.raises(InventoryAdmissionError):
        _count(snapshot)


def test_actual_collector_content_digest_binds_authored_count(monkeypatch, tmp_path):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 2)
    assert _count(snapshot) == 1
    original_digest = snapshot["source_report"]["content_sha256"]
    for leaf in snapshot["leaves"]:
        if leaf["kind"] == "pull_request":
            leaf["author_login"] = "another-author"
    assert _canonical_sha256(snapshot["leaves"]) != original_digest
    with pytest.raises(InventoryAdmissionError, match="inventory_content_digest_invalid"):
        _count(snapshot)


@pytest.mark.parametrize("digest", [None, "", "0" * 64, 42])
def test_actual_collector_requires_content_digest(monkeypatch, tmp_path, digest):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 2)
    snapshot["source_report"]["content_sha256"] = digest
    with pytest.raises(InventoryAdmissionError, match="inventory_content_digest_invalid"):
        _count(snapshot)


@pytest.mark.parametrize("field", ["normalized_leaf_count", "known_leaf_count"])
@pytest.mark.parametrize("value", [None, True, -1, 0, "3"])
def test_actual_collector_reported_leaf_count_is_exact(monkeypatch, tmp_path, field, value):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 2)
    report = snapshot["source_report"]
    target = report["cursor"] if field == "known_leaf_count" else report
    target[field] = value
    with pytest.raises(InventoryAdmissionError, match="inventory_leaf_count_invalid"):
        _count(snapshot)


def test_actual_collector_incomplete_leaf_count_fails_closed(monkeypatch, tmp_path):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 0)
    snapshot["source_report"]["cursor"]["leaf_count_complete"] = False
    with pytest.raises(InventoryAdmissionError, match="inventory_leaf_count_invalid"):
        _count(snapshot)


def test_actual_collector_hashes_all_leaf_kinds(monkeypatch, tmp_path):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 2)
    branch = next(leaf for leaf in snapshot["leaves"] if leaf["kind"] == "branch")
    branch["private_note"] = "sensitive-synthetic-value"
    with pytest.raises(InventoryAdmissionError) as error:
        _count(snapshot)
    assert str(error.value) == "inventory_content_digest_invalid"


def test_actual_collector_unhashable_content_has_redacted_denial(monkeypatch, tmp_path):
    snapshot, _fetched = _emit(monkeypatch, tmp_path, 2)
    snapshot["leaves"][0]["private_note"] = {"sensitive-synthetic-value"}
    with pytest.raises(InventoryAdmissionError) as error:
        _count(snapshot)
    assert str(error.value) == "inventory_content_digest_invalid"
