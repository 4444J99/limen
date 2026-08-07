from __future__ import annotations

import importlib.machinery
import importlib.util
import json
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
        "generated_at": "2026-08-07T10:00:00Z",
        "exhaustive": True,
        "cursor_reconciliation": {"failure_count": 0},
        "content_sha256": "a" * 64,
        "lifecycle_untyped_count": 1,
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


def _row(repository: str, number: int, **extra) -> dict:
    return {
        "repository": repository,
        "number": number,
        "head_oid": format(number, "x") * 40,
        "title": f"pr {number}",
        "draft": False,
        "url": f"https://example.test/{repository}/{number}",
        "pr_key": str(number) * 64,
        "lifecycle_disposition": None,
        **extra,
    }


def cohort_ledger() -> dict:
    return {
        "generated_at": "2026-08-07T10:00:00Z",
        "exhaustive": True,
        "cursor_reconciliation": {"failure_count": 0},
        "content_sha256": "c" * 64,
        "lifecycle_untyped_count": 4,
        "pull_requests": [
            _row("org/bump", 1, owner="dependabot", classification="active_custody"),
            _row("org/mine", 2, owner="operator", classification="active_custody"),
            _row("org/stale", 3, owner="operator", classification="owner_route"),
            _row("org/secret", 4, owner="dependabot", classification="active_custody", private=True),
            _row("org/typed", 5, owner="operator", lifecycle_disposition="lifecycle:delivery"),
        ],
    }


def _plan(source: dict, **overrides) -> dict:
    kwargs = {
        "disposition": "lifecycle:blocked",
        "cohort": "all",
        "review_basis": "Fail closed pending review.",
    }
    kwargs.update(overrides)
    return MODULE.build_plan(source, **kwargs)


def test_estate_plan_is_exhaustive_and_sorted() -> None:
    plan = _plan(ledger())

    assert [(item["repository"], item["number"]) for item in plan["items"]] == [("owner/two", 2)]
    assert plan["repository_count"] == 1
    assert plan["selected_count"] == 1
    assert plan["unselected_untyped_count"] == 0
    MODULE.validate(plan, plan["plan_sha256"])


def test_non_exhaustive_ledger_fails_closed() -> None:
    source = ledger()
    source["cursor_reconciliation"]["failure_count"] = 1

    with pytest.raises(MODULE.ManifestError, match="not exhaustive"):
        _plan(source)


def test_unknown_disposition_and_cohort_fail_closed() -> None:
    with pytest.raises(MODULE.ManifestError, match="unknown disposition"):
        _plan(ledger(), disposition="lifecycle:bogus")
    with pytest.raises(MODULE.ManifestError, match="unknown cohort"):
        _plan(ledger(), cohort="everyone")
    with pytest.raises(MODULE.ManifestError, match="requires --owner"):
        _plan(ledger(), cohort="operator-active")


def test_plan_sha_binds_disposition_and_cohort() -> None:
    blocked = _plan(ledger())
    delivery = _plan(ledger(), disposition="lifecycle:delivery")

    assert blocked["plan_sha256"] != delivery["plan_sha256"]
    with pytest.raises(MODULE.ManifestError, match="digest does not match"):
        MODULE.validate(blocked, delivery["plan_sha256"])
    tampered = dict(delivery, cohort="dependabot")
    with pytest.raises(MODULE.ManifestError, match="digest does not match"):
        MODULE.validate(tampered, delivery["plan_sha256"])


def test_cohort_selectors_partition_the_untyped_estate() -> None:
    source = cohort_ledger()
    facts = cohort_ledger()

    dependabot = _plan(source, cohort="dependabot")
    active = _plan(source, cohort="operator-active", owner="operator")
    stale = _plan(source, cohort="operator-stale", owner="operator")
    private = _plan(source, cohort="private", facts=facts)

    assert [item["repository"] for item in dependabot["items"]] == ["org/bump"]
    assert [item["repository"] for item in active["items"]] == ["org/mine"]
    assert [item["repository"] for item in stale["items"]] == ["org/stale"]
    assert [item["repository"] for item in private["items"]] == ["org/secret"]
    untyped_total = 4
    selected = sum(plan["selected_count"] for plan in (dependabot, active, stale, private))
    assert selected == untyped_total
    assert dependabot["unselected_untyped_count"] == untyped_total - 1


def test_private_cohort_requires_matching_facts() -> None:
    source = cohort_ledger()
    with pytest.raises(MODULE.ManifestError, match="requires --facts"):
        _plan(source, cohort="private")

    drifted = cohort_ledger()
    drifted["generated_at"] = "2026-08-06T10:00:00Z"
    with pytest.raises(MODULE.ManifestError, match="different census"):
        _plan(source, cohort="private", facts=drifted)


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
        MODULE._preflight_repo("owner/two", [item], [row], "lifecycle:blocked")


def test_public_receipt_redacts_private_coordinates() -> None:
    source = ledger()
    source["pull_requests"][0]["private"] = True
    plan = _plan(source)
    plan["status"] = "applied_verified"
    plan["apply_receipt"] = {"effect_count": 1}

    receipt = MODULE.public_receipt(plan)

    assert receipt["cohort"] == "all"
    assert receipt["private_item_count"] == 1
    assert receipt["private_pr_keys"] == ["2" * 64]
    assert "owner/two" not in str(receipt)


def test_ensure_label_uses_disposition_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def run_gh(args: list[str]) -> str:
        calls.append(args)
        return "[]" if args[:2] == ["label", "list"] else ""

    monkeypatch.setattr(MODULE.BASE, "_run_gh", run_gh)

    MODULE._ensure_label("org/mine", "lifecycle:active-human")

    create = next(args for args in calls if args[:2] == ["label", "create"])
    assert create[2] == "lifecycle:active-human"
    assert "0969da" in create
    with pytest.raises(MODULE.ManifestError, match="no label metadata"):
        MODULE._ensure_label("org/mine", "lifecycle:bogus")


def test_private_manifest_refuses_docs_path(tmp_path: Path) -> None:
    source = cohort_ledger()
    ledger_path = tmp_path / "ledger.json"
    ledger_path.write_text(json.dumps(source))
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(cohort_ledger()))
    manifest_path = ROOT / "docs" / "tmp-test-private-manifest.json"

    rc = MODULE.main(
        [
            "--plan",
            "--ledger",
            str(ledger_path),
            "--facts",
            str(facts_path),
            "--manifest",
            str(manifest_path),
            "--disposition",
            "lifecycle:blocked",
            "--cohort",
            "private",
            "--review-basis",
            "Fail closed.",
        ]
    )

    assert rc == 2
    assert not manifest_path.exists()


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
    plan = _plan(source)
    labeled: set[tuple[str, int]] = set()

    def fetch(repository: str) -> list[dict]:
        item = next(item for item in plan["items"] if item["repository"] == repository)
        labels = [{"name": plan["disposition"]}] if (repository, item["number"]) in labeled else []
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
    monkeypatch.setattr(MODULE, "_ensure_label", lambda repository, disposition: None)
    monkeypatch.setattr(
        MODULE,
        "_repo_is_archived",
        lambda repository: repository == "owner/archived",
    )

    result = MODULE.apply_plan(plan, plan["plan_sha256"])

    assert result["status"] == "applied_verified_with_immutable_residual"
    assert result["apply_receipt"]["effect_count"] == 1
    assert result["apply_receipt"]["immutable_archived_item_count"] == 1
