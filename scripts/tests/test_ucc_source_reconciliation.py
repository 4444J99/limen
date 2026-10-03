import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def load():
    path = Path(__file__).resolve().parents[1] / "creds-provision.py"
    spec = importlib.util.spec_from_file_location("provision_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.parametrize("apply", [False, True])
@pytest.mark.parametrize("failure", [None, "existing", "conflict", "duplicate", "scope", "transport"])
def test_source_reconciliation_preserves_custody(monkeypatch, capsys, apply, failure):
    mod = load()
    policy = mod.load_policy(strict=True)
    candidate = "inert-source-test-value"
    item_id = "a" * 26
    items = (
        [{"id": item_id, "title": "Cloudflare API Token"}] if failure in ("existing", "conflict", "duplicate") else []
    )
    if failure == "duplicate":
        items *= 2
    delivery = SimpleNamespace(cached_candidate=lambda: candidate, TARGET="target", SECRET_NAME="CLOUDFLARE_API_TOKEN")
    hydrate = SimpleNamespace(
        DEFAULT_MAP=[{"gh_secret": {"repo": "target", "name": "CLOUDFLARE_API_TOKEN"}}],
        verify_cloudflare_delivery=lambda *args: (failure != "scope", "result"),
    )
    monkeypatch.setattr(
        mod.importlib.util,
        "spec_from_file_location",
        lambda name, path: SimpleNamespace(name=name, loader=SimpleNamespace(exec_module=lambda module: None)),
    )
    monkeypatch.setattr(
        mod.importlib.util, "module_from_spec", lambda spec: delivery if spec.name == "ucc_delivery" else hydrate
    )
    monkeypatch.setattr(mod, "_read_private", lambda path: "inert-service-account-test-value")
    writes = []

    def op(args, env, payload=None):
        assert candidate not in args
        if failure == "transport":
            raise OSError(candidate)
        if args[:2] == ["vault", "list"]:
            return json.dumps([{"id": "vault", "name": "Limen-Automation"}])
        if args[:2] == ["item", "list"]:
            return json.dumps(items)
        if args[:2] == ["item", "create"]:
            writes.append(args)
            item = json.loads(payload)
            assert item["fields"][0]["value"] == candidate
            assert "original source op://Personal/" in item["fields"][1]["value"]
            items.append({"id": item_id, "title": "Cloudflare API Token"})
            return json.dumps(items[0])
        assert args[0] == "read"
        return "different" if failure == "conflict" else candidate

    monkeypatch.setattr(mod, "_op", op)
    assert mod.cmd_reconcile_cloudflare(policy, apply) == (
        2 if failure in ("conflict", "duplicate", "scope", "transport") else 0
    )
    assert len(writes) == (1 if apply and failure is None else 0)
    assert candidate not in capsys.readouterr().out
