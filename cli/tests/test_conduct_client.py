"""Focused transport contracts for the authenticated conduct client."""

from __future__ import annotations

from limen.conduct.client import HttpConductClient


def test_http_client_sends_stable_user_agent(monkeypatch):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"schema_version":"limen.conduct_capabilities.v1"}'

    def fake_urlopen(request, *, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr("limen.conduct.client.urllib.request.urlopen", fake_urlopen)
    client = HttpConductClient(
        "https://limen-runtime.example",
        "fixture-token",
        timeout=17,
    )

    assert client.capabilities()["schema_version"] == ("limen.conduct_capabilities.v1")
    assert captured["request"].get_header("User-agent") == ("limen-conduct-client/1")
    assert captured["timeout"] == 17
