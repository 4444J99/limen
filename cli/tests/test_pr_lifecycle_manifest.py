from __future__ import annotations

import importlib.machinery
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pr-lifecycle-manifest.py"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("pr_lifecycle_manifest", str(SCRIPT))
    spec = importlib.util.spec_from_loader("pr_lifecycle_manifest", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MODULE = _load_module()


def row(number: int, head: str, labels: tuple[str, ...] = ()) -> dict:
    return {
        "number": number,
        "headRefOid": head,
        "title": f"PR {number}",
        "isDraft": True,
        "url": f"https://example.test/pull/{number}",
        "labels": [{"name": label} for label in labels],
    }


def test_plan_includes_only_untyped_exact_heads() -> None:
    plan = MODULE.build_plan(
        "owner/repo",
        "lifecycle:blocked",
        [
            row(3, "c" * 40),
            row(1, "a" * 40, ("lifecycle:preservation",)),
            row(2, "b" * 40),
        ],
        review_basis="Pending review; no merge or close effect.",
    )

    assert [item["number"] for item in plan["items"]] == [2, 3]
    MODULE.validate_manifest(plan, plan["plan_sha256"])


def test_apply_preflights_every_head_before_writing(monkeypatch) -> None:
    plan = MODULE.build_plan(
        "owner/repo",
        "lifecycle:blocked",
        [row(1, "a" * 40), row(2, "b" * 40)],
        review_basis="Pending review.",
    )
    calls = []
    snapshots = [
        [row(1, "a" * 40), row(2, "changed")],
    ]
    monkeypatch.setattr(MODULE, "fetch_open_prs", lambda _repo: snapshots.pop(0))
    monkeypatch.setattr(MODULE, "_run_gh", lambda args: calls.append(args) or "")

    with pytest.raises(MODULE.ManifestError, match="exact head drifted"):
        MODULE.apply_manifest(plan, plan["plan_sha256"])

    assert calls == []


def test_apply_is_idempotent_and_verifies_exact_label(monkeypatch) -> None:
    plan = MODULE.build_plan(
        "owner/repo",
        "lifecycle:blocked",
        [row(1, "a" * 40)],
        review_basis="Pending review.",
    )
    snapshots = [
        [row(1, "a" * 40)],
        [row(1, "a" * 40, ("lifecycle:blocked",))],
    ]
    calls = []
    monkeypatch.setattr(MODULE, "fetch_open_prs", lambda _repo: snapshots.pop(0))
    monkeypatch.setattr(MODULE, "_run_gh", lambda args: calls.append(args) or "")

    applied = MODULE.apply_manifest(plan, plan["plan_sha256"])

    assert applied["status"] == "applied_verified"
    assert applied["apply_receipt"]["effect_count"] == 1
    assert calls[0][-1] == "lifecycle:blocked"


def test_digest_mismatch_fails_closed() -> None:
    plan = MODULE.build_plan(
        "owner/repo",
        "lifecycle:blocked",
        [row(1, "a" * 40)],
        review_basis="Pending review.",
    )

    with pytest.raises(MODULE.ManifestError, match="digest"):
        MODULE.validate_manifest(plan, "0" * 64)
