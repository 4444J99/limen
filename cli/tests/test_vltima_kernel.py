import json
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from click.testing import CliRunner

from limen.cli import main


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate-vltima-kernel.py"


def load_validator_module():
    spec = importlib.util.spec_from_file_location("validate_vltima_kernel_uut", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def run_validator(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *(str(arg) for arg in args)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_vltima_kernel_passes_current_organs():
    result = run_validator("--quiet")
    assert result.returncode == 0, result.stdout + result.stderr


def test_vltima_kernel_rejects_missing_universal_term(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    kernel = copy_root / "organs" / "vltima" / "KERNEL.md"
    kernel.write_text(kernel.read_text().replace("Entitlement", "Access").replace("entitlement", "access"))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "organs/vltima/KERNEL.md is missing term(s): Entitlement" in result.stderr


def test_vltima_kernel_rejects_registry_missing_required_primitive(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    registry = copy_root / "organs" / "vltima" / "kernel.yaml"
    data = yaml.safe_load(registry.read_text())
    data["layers"]["value"] = [item for item in data["layers"]["value"] if item["label"] != "Entitlement"]
    registry.write_text(yaml.safe_dump(data, sort_keys=False))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "organs/vltima/kernel.yaml missing required primitive(s): Entitlement" in result.stderr


def test_vltima_kernel_rejects_registry_unknown_source(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    registry = copy_root / "organs" / "vltima" / "kernel.yaml"
    data = yaml.safe_load(registry.read_text())
    data["layers"]["institutional"][0]["sources"] = ["missing-source"]
    registry.write_text(yaml.safe_dump(data, sort_keys=False))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "primitive member references unknown source(s): missing-source" in result.stderr


def test_vltima_kernel_rejects_projection_unknown_primitive(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    registry = copy_root / "organs" / "vltima" / "kernel.yaml"
    data = yaml.safe_load(registry.read_text())
    data["projection"]["value_proof"] = ["exchange", "missing-primitive"]
    registry.write_text(yaml.safe_dump(data, sort_keys=False))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "projection.value_proof references unknown primitive(s): missing-primitive" in result.stderr


def test_vltima_kernel_emits_derived_projection_json():
    result = run_validator("--json-output")

    assert result.returncode == 0, result.stdout + result.stderr
    data = json.loads(result.stdout)
    assert data["kind"] == "vltima.kernel-projection"
    assert data["schema_version"] == 1
    assert data["projections"]["organ_kernel"][0] == {"id": "member", "label": "Member"}
    assert data["projections"]["record_proof"] == [
        {"id": "event", "label": "Event"},
        {"id": "record", "label": "Record"},
        {"id": "standing", "label": "Standing"},
    ]
    by_id = {primitive["id"]: primitive for primitive in data["primitives"]}
    assert by_id["governance"]["sources"] == ["actor", "agent", "system", "record", "covenant"]
    assert {"from": "record", "to": "standing", "type": "source"} in data["edges"]
    assert {"from": "covenant", "to": "governance", "type": "source"} in data["edges"]
    graph_nodes = {node["id"]: node for node in data["graph"]["nodes"]}
    assert graph_nodes["layer:lower"]["kind"] == "layer"
    assert graph_nodes["primitive:record"]["kind"] == "primitive"
    assert graph_nodes["projection:organ_kernel"]["kind"] == "projection"
    assert graph_nodes["organ:legal"]["kind"] == "organ"
    assert {"from": "layer:lower", "to": "primitive:record", "type": "contains"} in data["graph"]["edges"]
    assert {"from": "organ:legal", "to": "projection:organ_kernel", "type": "implements"} in data["graph"]["edges"]
    assert {"from": "projection:record_proof", "to": "primitive:record", "type": "projects"} in data["graph"]["edges"]
    assert {"from": "primitive:record", "to": "primitive:standing", "type": "source"} in data["graph"]["edges"]
    assert any(organ["pillar"] == "legal" and organ["organ_kernel"] for organ in data["organs"])
    legal = next(organ for organ in data["organs"] if organ["pillar"] == "legal")
    assert legal["kernel_map"]["Member"] == "client/party"
    education = next(organ for organ in data["organs"] if organ["pillar"] == "education")
    assert education["kernel_map"] == {
        "Member": "learner",
        "Mandate": "quest",
        "Standing": "progression",
        "Standard": "rubric",
        "Governance": "institution",
    }


def test_vltima_kernel_writes_and_checks_canonical_projection(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")

    write = run_validator("--root", copy_root, "--write-projection")

    assert write.returncode == 0, write.stdout + write.stderr
    projection = copy_root / "organs" / "vltima" / "projection.json"
    assert projection.exists()
    data = json.loads(projection.read_text())
    assert data["kind"] == "vltima.kernel-projection"

    check = run_validator("--root", copy_root, "--check-projection", "--quiet")

    assert check.returncode == 0, check.stdout + check.stderr

    projection.write_text("{}\n")
    stale = run_validator("--root", copy_root, "--check-projection")

    assert stale.returncode == 1
    assert "projection stale: organs/vltima/projection.json" in stale.stderr


def test_vltima_projection_schema_names_canonical_contract():
    schema = json.loads((ROOT / "spec" / "contracts" / "vltima-kernel-projection.schema.json").read_text())

    assert schema["$id"] == "https://limen.local/contracts/vltima-kernel-projection.schema.json"
    assert schema["properties"]["kind"]["enum"] == ["vltima.kernel-projection"]
    assert schema["properties"]["schema_version"]["enum"] == [1]
    assert {"primitives", "edges", "layers", "projections", "organs", "graph"}.issubset(schema["required"])
    assert "kernel_map" in schema["$defs"]["organ"]["required"]


def test_vltima_kernel_rejects_organ_missing_kernel_map(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    ladder = json.loads((copy_root / "organ-ladder.json").read_text())
    ladder["organs"][0].pop("kernel_map")
    (copy_root / "organ-ladder.json").write_text(json.dumps(ladder, indent=2))

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "legal: organ-ladder.json missing kernel_map" in result.stderr


def test_vltima_kernel_cli_emits_projection_json():
    result = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--json-output"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["kind"] == "vltima.kernel-projection"
    assert data["projections"]["organ_kernel"][0] == {"id": "member", "label": "Member"}


def test_vltima_kernel_cli_checks_current_projection_and_reports_missing_custom_path(tmp_path):
    current = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--check-projection"])

    assert current.exit_code == 0, current.output
    assert "projection current at organs/vltima/projection.json" in current.output

    missing = CliRunner().invoke(
        main,
        [
            "vltima-kernel",
            "--root",
            str(ROOT),
            "--check-projection",
            "--projection-path",
            str(tmp_path / "missing-projection.json"),
        ],
    )

    assert missing.exit_code == 1
    assert "projection missing:" in missing.output


def test_vltima_kernel_cli_selects_primitive_by_id_or_label():
    by_id = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--primitive", "record"])
    by_label = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--primitive", "Record"])

    assert by_id.exit_code == 0, by_id.output
    assert by_label.exit_code == 0, by_label.output
    assert json.loads(by_id.output) == json.loads(by_label.output)
    payload = json.loads(by_id.output)
    assert payload["id"] == "record"
    assert payload["label"] == "Record"
    assert payload["layer"] == "lower"


def test_vltima_kernel_cli_selects_organ_by_pillar_or_home():
    by_pillar = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--organ", "education"])
    by_home = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--organ", "organs/education"])

    assert by_pillar.exit_code == 0, by_pillar.output
    assert by_home.exit_code == 0, by_home.output
    assert json.loads(by_pillar.output) == json.loads(by_home.output)
    payload = json.loads(by_pillar.output)
    assert payload["pillar"] == "education"
    assert payload["kernel_map"]["Member"] == "learner"


def test_vltima_kernel_cli_selects_projection_group():
    result = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--projection", "organ_kernel"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0] == {"id": "member", "label": "Member"}
    assert payload[-1] == {"id": "governance", "label": "Governance"}


def test_vltima_kernel_cli_selects_layer_group():
    result = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--layer", "lower"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload == [
        {"id": "object", "label": "Object"},
        {"id": "subject", "label": "Subject"},
        {"id": "agent", "label": "Agent"},
        {"id": "actor", "label": "Actor"},
        {"id": "system", "label": "System"},
        {"id": "event", "label": "Event"},
        {"id": "record", "label": "Record"},
        {"id": "covenant", "label": "Covenant"},
    ]


def test_vltima_kernel_cli_selector_stays_json_when_checking_projection():
    result = CliRunner().invoke(
        main,
        ["vltima-kernel", "--root", str(ROOT), "--check-projection", "--organ", "education"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["pillar"] == "education"
    assert "projection current" not in result.output


def test_vltima_kernel_cli_reports_unknown_selector_and_selector_conflict():
    missing = CliRunner().invoke(main, ["vltima-kernel", "--root", str(ROOT), "--primitive", "missing"])

    assert missing.exit_code == 1
    assert "primitive not found: missing" in missing.output

    conflict = CliRunner().invoke(
        main,
        ["vltima-kernel", "--root", str(ROOT), "--primitive", "record", "--organ", "legal"],
    )

    assert conflict.exit_code == 2
    assert "choose only one of --primitive, --organ, --layer, or --projection" in conflict.output


def test_vltima_graph_validation_rejects_dangling_edges():
    module = load_validator_module()

    errors = module._validate_graph(
        {
            "nodes": [{"id": "primitive:record", "kind": "primitive"}],
            "edges": [{"from": "primitive:record", "to": "primitive:missing", "type": "source"}],
        }
    )

    assert errors == ["vltima graph edge[0] references missing target node: primitive:missing"]


def test_vltima_projection_contract_rejects_wrong_kind_and_missing_graph():
    module = load_validator_module()

    errors = module._validate_projection_contract(
        {
            "kind": "wrong",
            "schema_version": 1,
            "primitives": [{"id": "record"}],
            "edges": [],
            "layers": {},
            "projections": {},
            "organs": [{"pillar": "legal"}],
        }
    )

    assert "vltima projection kind must be 'vltima.kernel-projection'" in errors
    assert "vltima projection graph must be a mapping" in errors


def test_vltima_kernel_rejects_organ_missing_projection(tmp_path):
    copy_root = tmp_path / "repo"
    shutil.copytree(ROOT / "organs", copy_root / "organs")
    shutil.copy2(ROOT / "organ-ladder.json", copy_root / "organ-ladder.json")
    kernel = copy_root / "organs" / "hr" / "KERNEL.md"
    kernel.write_text("# HR\n\nMember Mandate Standard Governance\n\nMACRO deployment\n\nMICRO deployment\n")

    result = run_validator("--root", copy_root)

    assert result.returncode == 1
    assert "hr: organs/hr/KERNEL.md missing primitive(s): Standing" in result.stderr
