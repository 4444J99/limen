"""A lifetime bridge requires reciprocal kernel endpoints, not shared names."""

import struct

import pytest
from limen.process_lifetime import decode_pipe, live_lifetime_bridge, reciprocal_pipe
from limen.process_ownership import Process


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
