"""Real loopback exchanges prove redirect refusal and bounded response handling."""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from limen.bounded_subprocess import BoundedSubprocessError
from limen.conduct.assessment_transport import LIMIT, AssessmentHttpClient
from limen.conduct.client import BrokerUnavailable


@pytest.fixture
def server():
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append((self.path, body))
            assert self.headers["Authorization"] == "Bearer fixture-read-only"
            assert self.headers["Content-Type"] == "application/json"
            encoded = json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_GET(self):
            calls.append(self.path)
            assert self.headers["Authorization"] == "Bearer fixture-read-only"
            if "/redirect/" in self.path:
                self.send_response(302)
                self.send_header("Location", "/api/conduct/runs/redirect-target/graph")
                self.end_headers()
                return
            status = 403 if "/denied/" in self.path else 200
            if "/oversize/" in self.path:
                body = b"x" * (LIMIT + 1)
            elif "/duplicate/" in self.path:
                body = b'{"measured":true,"measured":false}'
            elif "/malformed/" in self.path:
                body = b"[]"
            elif status == 403:
                body = b"private provider detail must not escape"
            else:
                body = json.dumps({"measured": True}).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{http.server_port}", calls
    finally:
        http.shutdown()
        http.server_close()
        thread.join(timeout=2)


def test_real_exchange_ignores_ambient_proxy_and_isolates_credential(server, monkeypatch):
    from limen.conduct import assessment_transport as module

    endpoint, calls = server
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("LIMEN_CONDUCT_TOKEN", "ambient-private-value")
    original = module.run_bounded_subprocess

    def inspect(command, **kwargs):
        assert command[1] == "-I"
        assert "fixture-read-only" not in str(command)
        assert kwargs["env"] == {"LANG": "C.UTF-8"}
        assert kwargs["timeout_seconds"] == 20
        assert json.loads(kwargs["input_bytes"])["credential"] == "fixture-read-only"
        return original(command, **kwargs)

    monkeypatch.setattr(module, "run_bounded_subprocess", inspect)
    assert AssessmentHttpClient(endpoint, "fixture-read-only").graph("success") == {"measured": True}
    assert calls == ["/api/conduct/runs/success/graph"]


@pytest.mark.parametrize("run", ["redirect", "oversize", "malformed", "duplicate", "denied"])
def test_bad_exchange_fails_once_without_provider_details(server, run):
    endpoint, calls = server
    with pytest.raises(BrokerUnavailable, match="^assessment broker exchange is unmeasured; no automatic retry$"):
        AssessmentHttpClient(endpoint, "fixture-read-only").graph(run)
    assert calls == [f"/api/conduct/runs/{run}/graph"]


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://user:secret@example.invalid",
        "https://example.invalid#fragment",
        "https://example.invalid?token=secret",  # allow-secret: rejected synthetic URL
        "https://example.invalid/unreviewed/path",
        "http://example.invalid",
    ],
)
def test_ambiguous_endpoints_are_rejected(endpoint):
    with pytest.raises(ValueError):
        AssessmentHttpClient(endpoint, "fixture-read-only")


def test_oversized_request_never_starts_process(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("oversized request must not launch")

    monkeypatch.setattr("limen.conduct.assessment_transport.run_bounded_subprocess", forbidden)
    client = AssessmentHttpClient("https://keeper.example.invalid", "fixture-read-only")
    with pytest.raises(BrokerUnavailable):
        client._request("POST", "/api/conduct/runs", {"oversize": "x" * LIMIT})


def test_wall_timeout_is_redacted_without_retry(monkeypatch):
    calls = []

    def timeout(*args, **kwargs):
        calls.append(1)
        raise BoundedSubprocessError("timeout")

    monkeypatch.setattr("limen.conduct.assessment_transport.run_bounded_subprocess", timeout)
    client = AssessmentHttpClient("https://keeper.example.invalid", "fixture-read-only")
    with pytest.raises(BrokerUnavailable, match="no automatic retry"):
        client.graph("run-1")
    assert calls == [1]


def test_real_post_preserves_claim_binding(server):
    endpoint, calls = server
    assert AssessmentHttpClient(endpoint, "fixture-read-only").claim("lease-1", 7) == {"generation": 7}
    assert calls == [("/api/conduct/leases/lease-1/claim", {"generation": 7})]
