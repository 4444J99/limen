"""DNS/TLS/slow-body time is bounded; cancellation never implies remote absence."""

import json
import time
from unittest.mock import patch

import pytest

from limen import jules_api
from limen.bounded_subprocess import BoundedCompletedProcess


@pytest.mark.parametrize(
    "method,exception", [("GET", jules_api.JulesApiError), ("POST", jules_api.JulesMutationUnknown)]
)
def test_real_child_that_stalls_is_killed_at_wall_deadline(tmp_path, monkeypatch, method, exception):
    child = tmp_path / "stalled-http.py"
    child.write_text("import sys,time\nsys.stdin.buffer.read()\ntime.sleep(60)\n")
    monkeypatch.setattr(jules_api, "__file__", str(child))
    before = time.monotonic()
    with pytest.raises(exception):
        jules_api._transport(method, "sessions", "synthetic-key", {}, 0.2, 1024)
    assert time.monotonic() - before < 3


def test_key_never_enters_child_command_environment_or_logs():
    key = "synthetic-secret-not-real"
    value = BoundedCompletedProcess(0, b'{"result":{"sessions":[]}}', b"")
    with patch("limen.bounded_subprocess.run_bounded_subprocess", return_value=value) as run:
        assert jules_api._transport("GET", "sessions", key, None, 2, 1024) == {"sessions": []}
    args, kwargs = run.call_args
    assert key not in str(args)
    assert key not in str(kwargs["env"])
    assert kwargs["timeout_seconds"] == 2
    assert json.loads(kwargs["input_bytes"])[2] == key


@pytest.mark.parametrize("unknown", [False, True])
def test_only_classified_child_errors_escape(unknown):
    row = {"error_code": "provider_rejected", "http_status": 403, "mutation_unknown": unknown}
    value = BoundedCompletedProcess(0, json.dumps(row).encode(), b"")
    with patch("limen.bounded_subprocess.run_bounded_subprocess", return_value=value):
        with pytest.raises(jules_api.JulesApiError) as error:
            jules_api._transport("POST", "sessions", "synthetic", {}, 2, 1024)
    assert isinstance(error.value, jules_api.JulesMutationUnknown) is unknown
    assert error.value.status == 403


def test_unclassified_child_failure_is_indeterminate_not_retryable():
    value = BoundedCompletedProcess(1, b"private-provider-body", b"synthetic-secret")
    with patch("limen.bounded_subprocess.run_bounded_subprocess", return_value=value):
        with pytest.raises(jules_api.JulesMutationUnknown) as error:
            jules_api._transport("POST", "sessions", "synthetic", {}, 2, 1024)
    assert str(error.value) == "invalid_response"
