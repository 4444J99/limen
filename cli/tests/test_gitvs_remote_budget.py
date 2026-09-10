"""GitHub's configured Actions budget is evidence separate from local policy."""

import json

import pytest

from test_gitvs import _load, _result


def budget_row(identity="private-budget-id", amount=25, **overrides):
    return {
        "id": identity,
        "budget_type": "ProductPricing",
        "budget_product_skus": ["actions"],
        "budget_scope": "organization",
        "budget_amount": amount,
        "prevent_further_usage": True,
        **overrides,
    }


def page(rows, total=None, has_next=False):
    return {"budgets": rows, "has_next_page": has_next, "total_count": len(rows) if total is None else total}


def observe(module):
    return module._actions_budget_observation("fixture", actions_net=0, projected=0, policy_budget=25)


def test_remote_budget_pagination_uses_documented_scope_and_preserves_privacy(monkeypatch):
    module = _load()
    responses = iter(
        [
            page([budget_row("copilot", budget_product_skus=["copilot"])], total=2, has_next=True),
            page([budget_row()], total=2),
        ]
    )
    calls = []

    def fake_read(args, timeout):
        calls.append((args, timeout))
        return _result(next(responses))

    monkeypatch.setattr(module, "_gh_user", fake_read)
    observation = observe(module)
    assert observation["status"] == "observed"
    assert observation["policy_matches"] is True
    assert observation["enforced_headroom_available"] is True
    assert [call[0][1] for call in calls] == [
        "/organizations/fixture/settings/billing/budgets?scope=organization&per_page=100&page=1",
        "/organizations/fixture/settings/billing/budgets?scope=organization&per_page=100&page=2",
    ]
    assert all(call[1] == 5 for call in calls)
    assert "private-budget-id" not in json.dumps(observation)
    assert "budget_amount" not in observation


@pytest.mark.parametrize("returncode", [1, 403, 404])
def test_unreadable_remote_budget_cannot_be_invented_from_local_policy(monkeypatch, returncode):
    module = _load()
    monkeypatch.setattr(module, "_gh_user", lambda *_args, **_kwargs: _result({}, returncode))
    monkeypatch.setenv("LIMEN_ACTIONS_BUDGET", "1000000")
    assert observe(module)["reason"] == "budget_endpoint_unreadable"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        page([]),
        page([budget_row()], total=2),
        page([budget_row(), budget_row()]),
        page([budget_row(amount=True)]),
        page([budget_row(amount=-1)]),
        page([budget_row(amount=float("nan"))]),
        page([budget_row(budget_scope="repository")]),
        page([budget_row(budget_product_skus=["actions_linux"])]),
        page([budget_row()], total=True),
        page([], total=1, has_next=True),
    ],
)
def test_missing_malformed_or_incomplete_budget_evidence_is_unavailable(monkeypatch, payload):
    module = _load()
    monkeypatch.setattr(module, "_gh_user", lambda *_args, **_kwargs: _result(payload))
    assert observe(module)["status"] == "unavailable"


def test_changing_remote_budget_total_fails_closed(monkeypatch):
    module = _load()
    responses = iter([page([budget_row("one")], total=2, has_next=True), page([budget_row("two")], total=3)])
    monkeypatch.setattr(module, "_gh_user", lambda *_args, **_kwargs: _result(next(responses)))
    assert observe(module)["reason"] == "budget_total_changed"


def test_product_budget_cannot_hide_a_sku_specific_actions_stop(monkeypatch):
    module = _load()
    rows = [
        budget_row(),
        budget_row("linux", amount=0, budget_type="SkuPricing", budget_product_skus=["actions_linux"]),
    ]
    monkeypatch.setattr(module, "_gh_user", lambda *_args, **_kwargs: _result(page(rows)))
    assert observe(module)["reason"] == "actions_sku_budget_requires_scoped_usage"


def test_budget_page_limit_is_finite(monkeypatch):
    module = _load()
    calls = []

    def fake_read(args, **_kwargs):
        calls.append(args)
        return _result(page([budget_row(str(len(calls)))], total=1001, has_next=True))

    monkeypatch.setattr(module, "_gh_user", fake_read)
    assert observe(module)["reason"] == "budget_page_limit_reached"
    assert len(calls) == 10


@pytest.mark.parametrize(("amount", "expected"), [(0, 1), (10, 1), (25, 0)])
def test_live_budget_drift_is_not_hidden_by_local_policy(tmp_path, monkeypatch, capsys, amount, expected):
    module = prepare_usage(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "_gh_user", lambda *_args, **_kwargs: _result(page([budget_row(amount=amount)])))
    monkeypatch.setenv("LIMEN_ACTIONS_BUDGET", "25")
    assert module.usage({}, check=True, strict=True, print_json=False) == expected
    doc = json.loads(module.USAGE_DOC.read_text())
    assert doc["budget_net_usd"] == 25
    assert doc["budget_source"] == "local_policy"
    assert doc["remote_budget_observation"]["policy_matches"] is (amount == 25)
    assert "private-budget-id" not in capsys.readouterr().out
    assert "private-budget-id" not in json.dumps(doc)


def prepare_usage(tmp_path, monkeypatch):
    module = _load()
    monkeypatch.delenv("LIMEN_OFFLINE", raising=False)
    monkeypatch.setattr(module.shutil, "which", lambda _command: "/usr/bin/gh")
    monkeypatch.setattr(module, "owners", lambda _estate: ["fixture"])
    monkeypatch.setattr(module, "_usage_month", lambda *_args: {"by_product": {"actions": {"net_usd": 0}}})
    monkeypatch.setattr(module, "_runner_admission_observation", lambda _repo: (False, "annotation absent"))
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "USAGE_DOC", tmp_path / "usage.json")
    monkeypatch.setattr(module, "USAGE_STAMP", tmp_path / "usage-stamp.json")
    return module


@pytest.mark.parametrize(("check", "strict"), [(True, False), (False, True), (True, True)])
def test_unavailable_budget_is_explicit_and_non_green_without_losing_usage(
    tmp_path, monkeypatch, capsys, check, strict
):
    module = prepare_usage(tmp_path, monkeypatch)
    monkeypatch.setattr(module, "_gh_user", lambda *_args, **_kwargs: _result({}, 403))
    assert module.usage({}, check=check, strict=strict, print_json=False) == 77
    assert "budget observation unavailable" in capsys.readouterr().out
    doc = json.loads(module.USAGE_DOC.read_text())
    assert doc["actions_net_usd_mtd"] == 0
    assert doc["remote_budget_observation"]["status"] == "unavailable"
