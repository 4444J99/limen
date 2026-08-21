"""Tests for scripts/background-items-census.py — declaration parity for the background-item estate.

The LaunchAgents directory is redirected to tmp via env and the sfltool boundary is
monkeypatched, so the tests never read the host's real launchd surface. The classes exercised:
estate (with the rendered-basename pathology), third-party exemption, tombstone, UNDECLARED
(the gating class), missing-estate reporting, and BTM corroboration parsing.
"""

import importlib.util
import json
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "scripts" / "background-items-census.py"

REGISTRY = {
    "estate_agents": {
        "com.limen.heartbeat": {"role": "beat", "program_basename": "DomusAgentHost"},
        "com.limen.moneta": {"role": "mint", "program_basename": "node"},
    },
    "third_party_prefixes": ["com.google.", "homebrew.mxcl."],
}


def write_plist(directory, label, program_args=None):
    payload = {"Label": label}
    if program_args is not None:
        payload["ProgramArguments"] = program_args
    with open(directory / f"{label}.plist", "wb") as fp:
        plistlib.dump(payload, fp)


def load_module(tmp_path, monkeypatch, *, btm_text=None):
    agents = tmp_path / "LaunchAgents"
    agents.mkdir(exist_ok=True)
    monkeypatch.setenv("LIMEN_LAUNCHAGENTS_DIR", str(agents))
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    spec = importlib.util.spec_from_file_location("bic_under_test", SPEC)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    m._sfltool_dumpbtm = lambda timeout=30: btm_text
    registry_path = tmp_path / "background-items.json"
    registry_path.write_text(json.dumps(REGISTRY), encoding="utf-8")
    return m, agents, registry_path


def run_main(m, registry_path, monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["background-items-census.py", "--registry", str(registry_path), *args])
    return m.main()


def test_all_declared_passes_check(tmp_path, monkeypatch, capsys):
    m, agents, registry_path = load_module(tmp_path, monkeypatch)
    write_plist(agents, "com.limen.heartbeat", ["/x/DomusAgentHost", "run"])
    write_plist(agents, "com.limen.moneta", ["/opt/homebrew/bin/node", "tsx"])
    write_plist(agents, "com.google.GoogleUpdater.wake", ["/x/GoogleUpdater", "--wake-all"])
    write_plist(agents, "homebrew.mxcl.postgresql@16", ["/x/postgres", "-D"])
    assert run_main(m, registry_path, monkeypatch, "--check") == 0
    out = capsys.readouterr().out
    assert "2 estate, 2 third-party, 0 tombstone, 0 UNDECLARED" in out
    assert "renders as 'DomusAgentHost'" in out


def test_undeclared_plist_fails_check_and_names_the_label(tmp_path, monkeypatch, capsys):
    m, agents, registry_path = load_module(tmp_path, monkeypatch)
    write_plist(agents, "com.mystery.daemon", ["/usr/bin/python3", "evil.py"])
    assert run_main(m, registry_path, monkeypatch, "--check") == 1
    out = capsys.readouterr().out
    assert "UNDECLARED  com.mystery.daemon" in out
    assert "spec/background-items.json" in out


def test_undeclared_reports_but_exits_zero_without_check(tmp_path, monkeypatch):
    m, agents, registry_path = load_module(tmp_path, monkeypatch)
    write_plist(agents, "com.mystery.daemon", ["/usr/bin/python3", "evil.py"])
    assert run_main(m, registry_path, monkeypatch) == 0


def test_tombstone_is_advisory_not_gating(tmp_path, monkeypatch, capsys):
    m, agents, registry_path = load_module(tmp_path, monkeypatch)
    write_plist(agents, "com.legacy.stub")  # no Program/ProgramArguments
    assert run_main(m, registry_path, monkeypatch, "--check") == 0
    assert "1 tombstone, 0 UNDECLARED" in capsys.readouterr().out


def test_unparseable_plist_is_undeclared(tmp_path, monkeypatch):
    m, agents, registry_path = load_module(tmp_path, monkeypatch)
    (agents / "com.broken.thing.plist").write_bytes(b"not a plist at all")
    assert run_main(m, registry_path, monkeypatch, "--check") == 1


def test_missing_estate_agent_reported_not_gated(tmp_path, monkeypatch, capsys):
    m, agents, registry_path = load_module(tmp_path, monkeypatch)
    write_plist(agents, "com.limen.heartbeat", ["/x/DomusAgentHost", "run"])
    # com.limen.moneta declared but not installed
    assert run_main(m, registry_path, monkeypatch, "--check") == 0
    assert "declared estate agent not installed: com.limen.moneta" in capsys.readouterr().out


def test_btm_corroboration_parses_and_flags_unmatched(tmp_path, monkeypatch, capsys):
    dump = (
        "  Identifier: 8.com.limen.heartbeat\n"
        "  Identifier: 2.com.google.Chrome\n"
        "  Identifier: 8.com.shadow.agent\n"
        "  Identifier: Unknown Developer\n"
    )
    m, agents, registry_path = load_module(tmp_path, monkeypatch, btm_text=dump)
    write_plist(agents, "com.limen.heartbeat", ["/x/DomusAgentHost", "run"])
    assert run_main(m, registry_path, monkeypatch, "--check") == 0  # BTM never gates
    out = capsys.readouterr().out
    assert "3 identifiers; 1 unmatched" in out
    assert "btm-extra   com.shadow.agent" in out


def test_missing_dir_and_no_sfltool_fail_open(tmp_path, monkeypatch, capsys):
    m, agents, registry_path = load_module(tmp_path, monkeypatch, btm_text=None)
    agents.rmdir()
    assert run_main(m, registry_path, monkeypatch, "--check") == 0
    out = capsys.readouterr().out
    assert "0 estate, 0 third-party, 0 tombstone, 0 UNDECLARED" in out
    assert "btm         skipped" in out


def test_receipt_written_pii_clean(tmp_path, monkeypatch):
    m, agents, registry_path = load_module(tmp_path, monkeypatch)
    write_plist(agents, "com.limen.moneta", ["/opt/homebrew/bin/node", "tsx", "--token", "sekrit"])
    assert run_main(m, registry_path, monkeypatch) == 0
    receipt = json.loads((tmp_path / "logs" / "background-items-census.json").read_text())
    assert receipt["counts"]["estate"] == 1
    assert "sekrit" not in json.dumps(receipt)  # argv tails never reach the receipt
    assert receipt["rows"][0]["rendered_as"] == "node"


def test_no_receipt_mode_leaves_runtime_source_immutable(tmp_path, monkeypatch):
    m, _agents, registry_path = load_module(tmp_path, monkeypatch)
    assert run_main(m, registry_path, monkeypatch, "--check", "--no-receipt") == 0
    assert not (tmp_path / "logs" / "background-items-census.json").exists()
