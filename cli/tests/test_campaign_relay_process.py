from __future__ import annotations

import threading

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
