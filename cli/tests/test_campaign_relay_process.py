from __future__ import annotations

import threading
from dataclasses import replace
from pathlib import Path

import limen.census as census
import limen.conduct.campaign_relay_process as relay_process
import pytest
from limen.conduct.campaign_relay import _STARTUP_OUTPUT_CEILING
from limen.conduct.campaign_relay_process import _BoundedStreamDigest


class _HeldOpenOversizedStream:
    def __init__(self) -> None:
        self._remaining = _STARTUP_OUTPUT_CEILING + 1
        self._release = threading.Event()
        self.closed = False

    def read(self, size: int) -> bytes:
        if self._remaining:
            amount = min(size, self._remaining)
            self._remaining -= amount
            return b"x" * amount
        self._release.wait(timeout=2)
        return b""

    def close(self) -> None:
        self.closed = True

    def release(self) -> None:
        self._release.set()


def test_startup_output_ceiling_signal_precedes_stream_eof() -> None:
    stream = _HeldOpenOversizedStream()
    evidence = _BoundedStreamDigest()
    consumer = threading.Thread(target=evidence.consume, args=(stream,))
    consumer.start()

    assert evidence.wait_for_output_ceiling(timeout=1) is True
    assert evidence.output_ceiling_crossed() is True
    assert consumer.is_alive()

    stream.release()
    consumer.join(timeout=1)
    assert not consumer.is_alive()
    assert stream.closed is True


def test_live_relay_lane_resolves_a_renamed_registry_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import capacity

    source = next(
        vendor
        for vendor in census.VENDORS
        if vendor.execution.transport == "native-cli" or vendor.execution.transport.startswith("ianva-")
    )
    renamed = replace(
        source,
        name="fixture-relay-provider-renamed",
        aliases=(),
        binary="fixture-relay-provider-cli",
    )
    monkeypatch.setattr(census, "_BY_NAME", {renamed.name: renamed})
    monkeypatch.setattr(capacity, "select_lanes", lambda _selector: [renamed.name])
    monkeypatch.setattr(
        relay_process.shutil,
        "which",
        lambda binary: f"/fixture/{binary}" if binary == renamed.binary else None,
    )
    monkeypatch.delenv("LIMEN_FIXTURE_RELAY_PROVIDER_RENAMED_BIN", raising=False)

    assert relay_process._live_relay_lanes(Path("/fixture")) == (renamed.name,)


def test_live_relay_lane_includes_a_renamed_jules_adapter_for_its_autonomous_launch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import capacity

    source = next(vendor for vendor in census.VENDORS if vendor.execution.workstream_adapter == "jules")
    renamed = replace(
        source,
        name="fixture-jules-relay-renamed",
        aliases=(),
        binary="fixture-jules-relay-cli",
    )
    monkeypatch.setattr(census, "_BY_NAME", {renamed.name: renamed})
    monkeypatch.setattr(capacity, "select_lanes", lambda _selector: [renamed.name])
    monkeypatch.setattr(
        relay_process.shutil,
        "which",
        lambda binary: f"/fixture/{binary}" if binary == renamed.binary else None,
    )
    monkeypatch.delenv("LIMEN_FIXTURE_JULES_RELAY_RENAMED_BIN", raising=False)

    assert relay_process._live_relay_lanes(Path("/fixture")) == (renamed.name,)


def test_live_relay_lane_excludes_issue_assignment_even_when_its_binary_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from limen import capacity
    from limen.conduct.campaign_relay import CampaignRelayError

    issue_assignment = next(vendor for vendor in census.VENDORS if vendor.issue_assignment)
    monkeypatch.setattr(census, "_BY_NAME", {issue_assignment.name: issue_assignment})
    monkeypatch.setattr(capacity, "select_lanes", lambda _selector: [issue_assignment.name])
    monkeypatch.setattr(
        relay_process.shutil,
        "which",
        lambda binary: f"/fixture/{binary}" if binary == issue_assignment.binary else None,
    )

    with pytest.raises(CampaignRelayError, match="no healthy provider lane"):
        relay_process._live_relay_lanes(Path("/fixture"))
