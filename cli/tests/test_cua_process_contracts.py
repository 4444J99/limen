"""CUA temp workers require embedded vendor bytes and an exact parent chain."""

import os

import pytest
from limen.process_ownership import Process
from limen.process_services import _cua_embedded_commands


@pytest.fixture
def workers(tmp_path):
    source = b"vendor-worker-source\n" * 100
    helper = tmp_path / "node_repl"
    helper.write_bytes(b"vendor-binary-prefix" + source + b"vendor-binary-suffix")
    node = tmp_path / "node"
    node.write_bytes(b"node-binary")
    script = tmp_path / "trusted-worker.js"
    script.write_bytes(source)
    parent = Process(1, 99, os.getuid(), "parent", (str(helper),), cwd=tmp_path)
    child = Process(2, 1, os.getuid(), "child", (str(node), str(script), str(tmp_path)), cwd=tmp_path)
    return helper, script, {1: parent, 2: child}


def test_exact_embedded_worker_is_a_candidate(workers):
    helper, _, processes = workers
    assert _cua_embedded_commands(helper, processes, []) == [list(processes[2].argv)]


def test_modified_source_is_not_vendor_code(workers):
    helper, script, processes = workers
    script.write_bytes(script.read_bytes() + b"altered")
    assert _cua_embedded_commands(helper, processes, []) == []


def test_matching_basename_with_unrelated_parent_is_not_authority(workers):
    helper, _, processes = workers
    processes[1].argv = ("/unrelated/node_repl",)
    assert _cua_embedded_commands(helper, processes, []) == []


def test_unrelated_node_executable_is_not_authority(workers):
    helper, script, processes = workers
    processes[2].argv = ("/unrelated/node", str(script), str(script.parent))
    assert _cua_embedded_commands(helper, processes, []) == []


def test_argument_or_working_directory_expansion_is_rejected(workers):
    helper, _, processes = workers
    processes[2].argv += ("--extra",)
    assert _cua_embedded_commands(helper, processes, []) == []


def test_kernel_requires_exact_session_shape_and_embedded_source(workers):
    helper, script, processes = workers
    kernel = script.with_name("kernel.js")
    kernel.write_bytes(script.read_bytes())
    processes[2].argv = (
        str(helper.with_name("node")),
        "--experimental-vm-modules",
        str(kernel),
        "--session-id",
        "a" * 32,
        "--working-dir",
        str(script.parent),
    )
    assert _cua_embedded_commands(helper, processes, []) == [list(processes[2].argv)]
    processes[2].argv = (*processes[2].argv[:4], "not-native-session-shape", *processes[2].argv[5:])
    assert _cua_embedded_commands(helper, processes, []) == []


def test_script_symlink_is_rejected(workers):
    helper, script, processes = workers
    alias = script.with_name("alias.js")
    script.rename(alias)
    script.symlink_to(alias)
    assert _cua_embedded_commands(helper, processes, []) == []


def test_other_user_or_unknown_cwd_is_rejected(workers):
    helper, _, processes = workers
    processes[2].uid += 1
    assert _cua_embedded_commands(helper, processes, []) == []
    processes[2].uid -= 1
    processes[2].cwd = None
    assert _cua_embedded_commands(helper, processes, []) == []


def test_nested_app_server_must_match_declared_native_host(workers):
    helper, _, processes = workers
    codex = helper.with_name("codex")
    codex.write_bytes(b"declared native host")
    processes[2].argv = (str(codex), "app-server", "--listen", "stdio://")
    assert _cua_embedded_commands(helper, processes, []) == []
    assert _cua_embedded_commands(helper, processes, [{"argv": list(processes[2].argv)}]) == [list(processes[2].argv)]
    codex.unlink()
    assert _cua_embedded_commands(helper, processes, [{"argv": list(processes[2].argv)}]) == []


def test_embedded_byte_witnesses_bind_later_contract_hashes(workers):
    import hashlib

    helper, script, processes = workers
    witnesses = {}
    assert _cua_embedded_commands(helper, processes, [], witnesses)
    assert witnesses[str(script.resolve())] == hashlib.sha256(script.read_bytes()).hexdigest()
    assert witnesses[str(helper.resolve())] == hashlib.sha256(helper.read_bytes()).hexdigest()
