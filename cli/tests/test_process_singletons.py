"""A matching health response alone is never a singleton identity witness."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from limen.process_ownership import Process
from limen.process_singletons import SERENA_TRAY_COMMAND, exact_loopback_listener, serena_tray_alive


@pytest.mark.parametrize("output", [
    b"p99\nn127.0.0.1:24224\n",
    b"p10\nn*:24224\n",
    b"p10\nn[::1]:24224\n",
    b"p10\nn127.0.0.1:24224\nn127.0.0.1:24224\n",
    b"p10\np11\nn127.0.0.1:24224\n",
    b"p10\nn127.0.0.1:242240\n",
    b"\xff",
])
def test_listener_identity_failures(output):
    assert not exact_loopback_listener(output, 10)


def test_exact_listener():
    assert exact_loopback_listener(b"p10\nf4\nn127.0.0.1:24224\n", 10)


@pytest.mark.parametrize("body", [b'{"status":"dead"}', b'{"status":"alive","extra":1}', b'x' * 257])
def test_wrong_health_fails_closed(body):
    assert not _check(body, ["start", "start"])


def _check(body, identities):
    process = Process(10, 1, 501, "start", ("/vendor/bin/python", "-c", SERENA_TRAY_COMMAND))
    class Response:
        status = 200
        def read(self, limit):
            return body[:limit]
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return None
    values = iter(identities)
    listener = SimpleNamespace(returncode=0, stdout=b"p10\nf4\nn127.0.0.1:24224\n")
    with patch("limen.process_singletons.subprocess.run", return_value=listener), patch(
        "limen.process_singletons.urllib.request.build_opener",
        return_value=SimpleNamespace(open=lambda *args, **kwargs: Response()),
    ):
        return serena_tray_alive(process, lambda pid: next(values))


def test_typed_health_and_stable_identity():
    assert _check(b'{"status":"alive"}', ["start", "start"])


def test_pid_reuse_after_health_fails_closed():
    assert not _check(b'{"status":"alive"}', ["start", "replacement"])
