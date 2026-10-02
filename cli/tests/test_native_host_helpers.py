"""Explicit helper declarations retain exact host and direct-parent requirements."""

import os

import pytest
from limen.process_ownership import Process, assess
from limen.process_services import _native_helper_contracts


@pytest.fixture
def native(tmp_path):
    host_binary = tmp_path / "codex"
    helper_binary = tmp_path / "codex-code-mode-host"
    host_binary.write_bytes(b"registered native host")
    helper_binary.write_bytes(b"declared native helper")
    host = {
        "argv": [str(host_binary), "app-server", "--listen", "unix://", "--managed-daemon"],
        "helpers": [{"service_id": "codex/code-mode-host", "executable_relative": helper_binary.name, "args": []}],
    }
    return tmp_path, host, helper_binary


def test_no_helper_can_be_inferred_from_a_sibling_binary(native):
    root, host, _ = native
    host.pop("helpers")
    assert _native_helper_contracts(host, str(root), "policy") == []


def test_exact_declared_helper_requires_exact_direct_native_parent(native):
    root, host, binary = native
    contracts = _native_helper_contracts(host, str(root), "policy")
    parent = Process(1, 0, os.getuid(), "host-start", tuple(host["argv"]), cwd=root, env={"CODEX_HOME": str(root)})
    child = Process(2, 1, os.getuid(), "helper-start", (str(binary),), cwd=root)
    processes = {1: parent, 2: child}

    def identity(pid):
        return processes[pid].started if pid in processes else None

    report = assess(processes, set(), root, "subject", contracts=contracts, identity=identity)
    assert next(row for row in report["processes"] if row["pid"] == 2)["category"] == "shared_service"
    child.parent = 0
    report = assess(processes, set(), root, "subject", contracts=contracts, identity=identity)
    assert next(row for row in report["processes"] if row["pid"] == 2)["category"] == "unknown"


def test_argument_expansion_and_foreign_host_home_remain_unknown(native):
    root, host, binary = native
    contracts = _native_helper_contracts(host, str(root), "policy")
    parent = Process(1, 0, os.getuid(), "host", tuple(host["argv"]), cwd=root, env={"CODEX_HOME": str(root)})
    child = Process(2, 1, os.getuid(), "helper", (str(binary), "--extra"), cwd=root)
    processes = {1: parent, 2: child}

    def identity(pid):
        return processes[pid].started if pid in processes else None

    report = assess(processes, set(), root, "subject", contracts=contracts, identity=identity)
    assert next(row for row in report["processes"] if row["pid"] == 2)["category"] == "unknown"
    child.argv = (str(binary),)
    parent.env["CODEX_HOME"] = str(root / "unrelated")
    report = assess(processes, set(), root, "subject", contracts=contracts, identity=identity)
    assert next(row for row in report["processes"] if row["pid"] == 2)["category"] == "unknown"


def test_relative_path_escape_and_symlinks_are_rejected(native):
    root, host, binary = native
    for name in ("../codex-code-mode-host", str(binary), "..", ""):
        host["helpers"][0]["executable_relative"] = name
        assert _native_helper_contracts(host, str(root), "policy") == []
    host["helpers"][0]["executable_relative"] = binary.name
    alias = binary.with_name("vendor-helper")
    binary.rename(alias)
    binary.symlink_to(alias)
    assert _native_helper_contracts(host, str(root), "policy") == []


def test_host_helper_and_policy_bytes_all_bind_provenance(native):
    root, host, binary = native
    before = _native_helper_contracts(host, str(root), "policy")[0]["contract_sha256"]
    binary.write_bytes(b"changed helper")
    changed = _native_helper_contracts(host, str(root), "policy")[0]["contract_sha256"]
    assert before != changed
    assert changed != _native_helper_contracts(host, str(root), "different-policy")[0]["contract_sha256"]
    (root / "codex").write_bytes(b"changed host")
    assert changed != _native_helper_contracts(host, str(root), "policy")[0]["contract_sha256"]
