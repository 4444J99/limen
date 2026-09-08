import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ianva/src"))
import mcp_gateway_evidence as gateway
from ianva.upstreams import Upstream


@pytest.mark.parametrize(
    "field,value",
    [("command", "wrong"), ("args", ["wrong"]), ("env", {"KEY": "wrong"}), ("enabled", False), ("group", "wrong")],
)
def test_materialized_launch_drift_prevents_equivalence(field, value):
    upstream = Upstream(name="fixture", command="synthetic", env={"KEY": "private-value"})
    spec = gateway.declared_spec(upstream)
    spec[field] = value
    result = gateway.reconcile([upstream], {"mcpServers": {"fixture": spec}})
    assert result["configuration_mismatches"] == 1
    assert not result["cutover_eligible"]
    assert "private-value" not in json.dumps(result)


def test_rotated_backend_custody_is_provenance_not_source_drift():
    upstream = Upstream(name="fixture", url="https://example.invalid", transport="http")
    spec = gateway.declared_spec(upstream)
    spec["oauthTokens"] = {"access_token": "private-rotated"}
    result = gateway.reconcile([upstream], {"mcpServers": {"fixture": spec}})
    assert result["configuration_mismatches"] == 0
    assert result["upstreams"][0]["capabilities"] == "unmeasured"
    assert not result["cutover_eligible"]
    assert "private-rotated" not in json.dumps(result)


def test_missing_extra_and_disabled_upstreams_remain_in_population():
    wanted = [
        Upstream(name="missing", command="synthetic"),
        Upstream(name="disabled", command="synthetic", enabled=False),
    ]
    actual = {"mcpServers": {"extra": {"command": "synthetic"}, "disabled": gateway.declared_spec(wanted[1])}}
    result = gateway.reconcile(wanted, actual)
    assert result["expected_upstreams"] == result["materialized_upstreams"] == 2
    assert len(result["upstreams"]) == 3
    assert result["missing_upstreams"] == result["undeclared_upstreams"] == 1
    assert result["configuration_mismatches"] == 2


@pytest.mark.parametrize(
    "blob",
    [{"mcpServers": {"x": False}}, {"mcpServers": {}, "servers": {}}, [{"name": "x"}, {"name": "x"}], [None], False],
)
def test_gateway_loader_cannot_silently_discard_malformed_population(blob):
    with pytest.raises(ValueError):
        gateway.server_table(blob)


def test_complete_capability_equivalence_includes_schema_and_prompts():
    direct = {
        "tools": [{"name": "health", "inputSchema": {"type": "object"}}],
        "resources": [{"uri": "private://doc", "mimeType": "text/plain"}],
        "prompts": [{"name": "explain", "arguments": []}],
    }
    routed = {
        "tools": [{"name": "fixture_health", "inputSchema": {"type": "object"}}],
        "resources": [{"uri": "gateway://doc", "mimeType": "text/plain"}],
        "prompts": [{"name": "fixture_explain", "arguments": []}],
    }
    mapping = {
        "tools": {"health": "fixture_health"},
        "resources": {"private://doc": "gateway://doc"},
        "prompts": {"explain": "fixture_explain"},
    }
    result = gateway.reconcile_capabilities(direct, routed, mapping)
    assert all(row["state"] == "pass" for row in result.values())
    assert "private://doc" not in json.dumps(result)
    routed["tools"][0]["inputSchema"] = {"type": "string"}
    assert gateway.reconcile_capabilities(direct, routed, mapping)["tools"]["changed"] == 1


def test_incomplete_native_catalog_is_unmeasured_not_empty_equivalence():
    assert gateway.reconcile_capabilities({}, {}, {})["tools"]["state"] == "unmeasured"


def test_duplicate_capability_or_mapping_collision_fails():
    catalog = {"tools": [{"name": "one"}, {"name": "two"}], "resources": [], "prompts": []}
    result = gateway.reconcile_capabilities(catalog, catalog, {"tools": {"one": "same", "two": "same"}})
    assert result["tools"]["state"] == "fail"
    with pytest.raises(ValueError):
        gateway.reconcile_capabilities({"tools": [{"name": "one"}, {"name": "one"}]}, catalog, {})


def test_gateway_gap_controls_estate_exit(tmp_path, monkeypatch, capsys):
    import mcp_estate as estate

    policy = {"schema_version": 1, "services": {}, "registrations": [], "required_client_adapters": ["ianva"]}
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(policy))
    monkeypatch.setattr(estate, "inventory", lambda *a, **kw: ([], [], [], []))
    monkeypatch.setattr(
        estate,
        "gateway_reconciliation",
        lambda: {"state": "configuration_observed", "configuration_mismatches": 1, "cutover_eligible": False},
    )
    assert estate.main(["--policy", str(path), "--inventory-only", "--json"]) == 77
    result = json.loads(capsys.readouterr().out)
    assert {g["reason"] for g in result["coverage_gaps"]} >= {
        "gateway_configuration_mismatch",
        "gateway_equivalence_required",
    }
