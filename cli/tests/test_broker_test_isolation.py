"""Regression coverage for dispatch rehydrating live credentials during tests."""

import os
from pathlib import Path

import pytest

from limen.conduct.client import HttpConductClient, client_from_env
from limen.dispatch import _load_limen_env


def test_dispatch_reload_retains_temporary_keeper(tmp_path):
    environment = Path(os.environ["LIMEN_ENV"])
    assert environment.read_text() == ""
    assert environment.stat().st_mode & 0o777 == 0o600
    assert environment.parent != tmp_path
    assert list(tmp_path.iterdir()) == []
    assert not Path(os.environ["LIMEN_CONDUCT_ENV_FILE"]).exists()
    assert _load_limen_env() == 0
    assert "LIMEN_CONDUCT_URL" not in os.environ
    assert "LIMEN_CONDUCT_TOKEN" not in os.environ
    assert not isinstance(client_from_env(), HttpConductClient)


@pytest.mark.parametrize("path", ["/api/conduct/runs", "/api/board/private"])
def test_real_broker_transport_fails_before_network(path):
    client = HttpConductClient("https://broker.invalid", "fixture-token")
    with pytest.raises(AssertionError, match="test attempted real broker access"):
        client._request("POST", path, {})
