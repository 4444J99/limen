from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pr-lifecycle-estate-manifest.py"


def _load():
    loader = importlib.machinery.SourceFileLoader("pr_lifecycle_estate_manifest", str(SCRIPT))
    spec = importlib.util.spec_from_loader("pr_lifecycle_estate_manifest", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MODULE = _load()


def ledger() -> dict:
    return {
        "exhaustive": True,
        "cursor_reconciliation": {"failure_count": 0},
        "content_sha256": "a" * 64,
        "pull_requests": [
            {
                "repository": "owner/two",
                "number": 2,
                "head_oid": "b" * 40,
                "title": "two",
                "draft": False,
                "url": "https://example.test/two/2",
                "pr_key": "2" * 64,
                "lifecycle_disposition": None,
            },
            {
                "repository": "owner/one",
                "number": 1,
                "head_oid": "a" * 40,
                "title": "one",
                "draft": True,
                "url": "https://example.test/one/1",
                "pr_key": "1" * 64,
                "lifecycle_disposition": "lifecycle:preservation",
            },
        ],
    }


def test_estate_plan_is_exhaustive_and_sorted() -> None:
    plan = MODULE.build_plan(ledger(), review_basis="Fail closed pending review.")

    assert [(item["repository"], item["number"]) for item in plan["items"]] == [("owner/two", 2)]
    assert plan["repository_count"] == 1
    MODULE.validate(plan, plan["plan_sha256"])


def test_non_exhaustive_ledger_fails_closed() -> None:
    source = ledger()
    source["cursor_reconciliation"]["failure_count"] = 1

    with pytest.raises(MODULE.ManifestError, match="not exhaustive"):
        MODULE.build_plan(source, review_basis="Fail closed.")


def test_preflight_detects_exact_head_drift() -> None:
    item = {
        "repository": "owner/two",
        "number": 2,
        "head_oid": "b" * 40,
    }
    row = {
        "number": 2,
        "headRefOid": "changed",
        "labels": [],
    }

    with pytest.raises(MODULE.ManifestError, match="exact head drifted"):
        MODULE._preflight_repo("owner/two", [item], [row])


def test_public_receipt_redacts_private_coordinates() -> None:
    source = ledger()
    source["pull_requests"][0]["private"] = True
    plan = MODULE.build_plan(source, review_basis="Fail closed.")
    plan["status"] = "applied_verified"
    plan["apply_receipt"] = {"effect_count": 1}

    receipt = MODULE.public_receipt(plan)

    assert receipt["private_item_count"] == 1
    assert receipt["private_pr_keys"] == ["2" * 64]
    assert "owner/two" not in str(receipt)


def test_apply_records_archived_repository_as_immutable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = ledger()
    source["pull_requests"].append(
        {
            "repository": "owner/archived",
            "number": 3,
            "head_oid": "c" * 40,
            "title": "archived",
            "draft": False,
            "url": "https://example.test/archived/3",
            "pr_key": "3" * 64,
            "lifecycle_disposition": None,
        }
    )
    plan = MODULE.build_plan(source, review_basis="Fail closed.")
    labeled: set[tuple[str, int]] = set()

    def fetch(repository: str) -> list[dict]:
        item = next(item for item in plan["items"] if item["repository"] == repository)
        labels = [{"name": MODULE.DISPOSITION}] if (repository, item["number"]) in labeled else []
        return [
            {
                "number": item["number"],
                "headRefOid": item["head_oid"],
                "labels": labels,
            }
        ]

    def run_gh(args: list[str]) -> str:
        if args[:2] == ["pr", "edit"]:
            labeled.add((args[4], int(args[2])))
        return ""

    monkeypatch.setattr(MODULE.BASE, "fetch_open_prs", fetch)
    monkeypatch.setattr(MODULE.BASE, "_run_gh", run_gh)
    monkeypatch.setattr(MODULE, "_ensure_label", lambda repository: None)
    monkeypatch.setattr(
        MODULE,
        "_repo_is_archived",
        lambda repository: repository == "owner/archived",
    )

    result = MODULE.apply_plan(plan, plan["plan_sha256"])

    assert result["status"] == "applied_verified_with_immutable_residual"
    assert result["apply_receipt"]["effect_count"] == 1
    assert result["apply_receipt"]["immutable_archived_item_count"] == 1
