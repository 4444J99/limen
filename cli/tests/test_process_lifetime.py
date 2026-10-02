"""A lifetime bridge requires reciprocal kernel endpoints, not shared names."""

import struct
from pathlib import Path
from types import SimpleNamespace

import pytest
from limen.process_lifetime import (
    decode_pipe,
    find_lifetime_descriptors,
    live_lifetime_bridge,
    reciprocal_pipe,
    signed_responsible_host,
)
from limen.process_ownership import Process, assess


@pytest.fixture
def endpoints():
    reader = {"uid": 501, "handle": 1, "peer": 2, "device": 0, "inode": 0, "flags": 5}
    writer = {"uid": 501, "handle": 2, "peer": 1, "device": 0, "inode": 0, "flags": 2}
    return reader, writer


def test_reciprocal_reader_writer(endpoints):
    assert reciprocal_pipe(*endpoints, 501)


@pytest.mark.parametrize(
    "field,value", [("uid", 502), ("handle", 3), ("peer", 4), ("device", 1), ("inode", 2), ("flags", 1)]
)
def test_unrelated_kernel_endpoint_is_rejected(endpoints, field, value):
    reader, writer = endpoints
    writer[field] = value
    assert not reciprocal_pipe(reader, writer, 501)


def test_decoder_requires_exact_fifo_abi():
    payload = bytearray(184)
    struct.pack_into("<H", payload, 28, 0o010000)
    struct.pack_into("<QQ", payload, 160, 1, 2)
    assert decode_pipe(payload)["handle"] == 1
    for invalid in (bytes(183), bytes(184), bytes(185)):
        with pytest.raises(ValueError):
            decode_pipe(invalid)


def test_live_bridge_requires_stable_native_instances(endpoints, monkeypatch):
    host = Process(10, 1, 501, "host", ("/declared-host", "run"))
    peer = Process(20, 1, 501, "peer", ("/verified-peer",))
    processes = {10: host, 20: peer}
    monkeypatch.setattr("limen.process_lifetime.native_details", lambda pid: (processes[pid].argv, {}))
    monkeypatch.setattr("limen.process_lifetime.kernel_pipe", lambda pid, fd: endpoints[0 if pid == 10 else 1])
    assert live_lifetime_bridge(host, peer, 3, 4, lambda pid: processes[pid].started)
    assert not live_lifetime_bridge(host, peer, 3, 4, lambda pid: "reused")


def test_kernel_observation_failure_is_not_a_match(monkeypatch):
    host = Process(10, 1, 501, "host", ("/declared-host",))
    peer = Process(20, 1, 501, "peer", ("/verified-peer",))
    monkeypatch.setattr(
        "limen.process_lifetime.native_details", lambda pid: (("/declared-host",) if pid == 10 else peer.argv, {})
    )

    def missing(pid, fd):
        raise ValueError("unmeasured")

    monkeypatch.setattr("limen.process_lifetime.kernel_pipe", missing)
    assert not live_lifetime_bridge(host, peer, 3, 4, lambda pid: "host" if pid == 10 else "peer")


def test_descriptor_discovery_requires_one_reciprocal_pair(endpoints, monkeypatch):
    reader, writer = endpoints
    monkeypatch.setattr(
        "limen.process_lifetime.kernel_pipes", lambda pid, limit: [(3, reader)] if pid == 10 else [(4, writer)]
    )
    assert find_lifetime_descriptors(10, 20, 501, 128) == (3, 4)
    assert find_lifetime_descriptors(10, 20, 502, 128) is None
    assert find_lifetime_descriptors(10, 10, 501, 128) is None


def test_multiple_matching_descriptors_are_not_silently_selected(endpoints, monkeypatch):
    reader, writer = endpoints
    monkeypatch.setattr(
        "limen.process_lifetime.kernel_pipes",
        lambda pid, limit: [(3, reader), (5, reader)] if pid == 10 else [(4, writer)],
    )
    assert find_lifetime_descriptors(10, 20, 501, 128) is None


def test_command_replacement_during_witness_is_rejected(endpoints, monkeypatch):
    host = Process(10, 1, 501, "host", ("/declared-host",))
    peer = Process(20, 1, 501, "peer", ("/verified-peer",))
    calls = iter([(host.argv, {}), (peer.argv, {}), (("/replacement",), {})])
    monkeypatch.setattr("limen.process_lifetime.native_details", lambda pid: next(calls))
    monkeypatch.setattr("limen.process_lifetime.kernel_pipe", lambda pid, fd: endpoints[0 if pid == 10 else 1])
    assert not live_lifetime_bridge(host, peer, 3, 4, lambda pid: "host" if pid == 10 else "peer")


def test_descriptor_replacement_during_witness_is_rejected(endpoints, monkeypatch):
    host = Process(10, 1, 501, "host", ("/declared-host",))
    peer = Process(20, 1, 501, "peer", ("/verified-peer",))
    monkeypatch.setattr(
        "limen.process_lifetime.native_details", lambda pid: (host.argv if pid == 10 else peer.argv, {})
    )
    reader, writer = endpoints
    calls = iter([reader, writer, {**reader, "handle": 3}])
    monkeypatch.setattr("limen.process_lifetime.kernel_pipe", lambda pid, fd: next(calls))
    assert not live_lifetime_bridge(host, peer, 3, 4, lambda pid: "host" if pid == 10 else "peer")


@pytest.fixture
def signed_host(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    executable = tmp_path / "Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"managed executable")
    receipt = tmp_path / "Applications/.DomusAgentHost.designated-requirement"
    receipt.write_text('cdhash H"' + "a" * 40 + '"\n')
    monkeypatch.setattr("limen.process_lifetime.subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=0))
    return executable, receipt


def test_signed_fixed_host_binds_binary_and_requirement(signed_host, monkeypatch):
    executable, receipt = signed_host
    calls = []

    def verify(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("limen.process_lifetime.subprocess.run", verify)
    assert set(signed_responsible_host(executable)) == {str(executable), str(receipt)}
    assert calls[0][4] == "=" + receipt.read_text().strip()


def test_failed_codesign_is_not_host_authority(signed_host, monkeypatch):
    executable, _ = signed_host
    monkeypatch.setattr("limen.process_lifetime.subprocess.run", lambda *args, **kwargs: SimpleNamespace(returncode=1))
    assert signed_responsible_host(executable) == {}


def test_bad_designated_requirement_is_rejected(signed_host):
    executable, receipt = signed_host
    receipt.write_text("arbitrary requirement")
    assert signed_responsible_host(executable) == {}


@pytest.mark.parametrize(
    "field,value",
    [
        ("client", "other"),
        ("launch_prefix", ["run"]),
        ("lifetime_contract", "ancestry"),
        ("peer_service_ids", ["unrelated"]),
        ("require_signed_deployment", False),
        ("descriptor_limit", 0),
        ("descriptor_limit", 129),
        ("descriptor_limit", "128"),
        ("descriptor_limit", True),
        ("executable", None),
    ],
)
def test_invalid_source_authority_never_probes_host(field, value, monkeypatch):
    from limen.process_services import _responsible_host_contracts

    authority = {
        "client": "codex",
        "launch_prefix": ["run", "--"],
        "lifetime_contract": "pipe-handle-device-inode",
        "peer_service_ids": ["codex/code-mode-host"],
        "require_signed_deployment": True,
        "descriptor_limit": 128,
        "executable": "/declared-host",
    }
    authority[field] = value

    def forbidden(*args):
        pytest.fail("invalid authority reached native host probe")

    monkeypatch.setattr("limen.process_lifetime.signed_responsible_host", forbidden)
    assert _responsible_host_contracts({}, [], {"responsible_host": authority}, "policy") == []


def test_responsible_host_assessor_requires_finally_verified_peer(tmp_path, monkeypatch):
    import hashlib

    native = Process(100, 1, 501, "native", ("/codex", "app-server"), cwd=tmp_path)
    peer = Process(101, 100, 501, "peer", ("/code-mode-host",), cwd=tmp_path)
    host = Process(10, 1, 501, "responsible", ("/signed-host", "run", "--", "codex"), cwd=tmp_path)
    vendor = tmp_path / "host"
    vendor.write_bytes(b"signed")
    processes = {p.pid: p for p in (native, peer, host)}
    parent = {
        "service_id": "codex/code-mode-host",
        "argv": list(peer.argv),
        "host_argv": list(native.argv),
        "contract_sha256": "peer-contract",
    }
    contract = {
        "service_id": "codex/responsible-host",
        "argv": list(host.argv),
        "host_argv": list(native.argv),
        "contract_sha256": "host-contract",
        "singleton_pid": host.pid,
        "singleton_identity": host.started,
        "singleton_peer": {
            "pid": peer.pid,
            "identity": peer.started,
            "argv": list(peer.argv),
            "contract_sha256": "peer-contract",
        },
        "singleton_vendor_files": {str(vendor): hashlib.sha256(vendor.read_bytes()).hexdigest()},
        "lifetime_fds": [3, 4],
    }
    monkeypatch.setattr("limen.process_lifetime.live_lifetime_bridge", lambda *args: True)

    def evaluate(evidence=(), witnesses=None):
        return {
            r["pid"]: r
            for r in assess(
                processes,
                set(),
                tmp_path,
                "subject",
                contracts=[parent, contract],
                witnesses=witnesses,
                identity=lambda pid: processes[pid].started,
                evidence=evidence,
            )["processes"]
        }

    assert evaluate()[10]["category"] == "shared_service"
    assert evaluate()[10]["service_id"] == "codex/responsible-host"
    contract["singleton_peer"]["contract_sha256"] = "wrong"
    assert evaluate()[10]["category"] == "unknown"
    contract["singleton_peer"]["contract_sha256"] = "peer-contract"
    witnesses = {key: {"thread_id": key, "session_id": key, "parent_thread_id": None} for key in ("subject", "foreign")}
    for thread, expected in (("subject", "owned_survivor"), ("foreign", "foreign_session")):
        host.env = {"CODEX_THREAD_ID": thread, "CODEX_SESSION_ID": thread}
        assert evaluate(witnesses=witnesses)[10]["category"] == expected
    host.env = {"CODEX_THREAD_ID": "missing", "CODEX_SESSION_ID": "missing"}
    assert evaluate(witnesses=witnesses)[10]["category"] == "unmeasured"
    host.env = {}
    peer.env = {"CODEX_THREAD_ID": "foreign", "CODEX_SESSION_ID": "foreign"}
    assert evaluate(witnesses=witnesses)[10]["category"] == "unknown"
