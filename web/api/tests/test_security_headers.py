"""Exercise the actual API middleware stack, including CORS preflight."""

from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import main


@pytest.mark.parametrize(("path", "status"), [("/health", 200), ("/missing-route", 404)])
def test_api_response_headers_preserve_payload_and_embedding(path: str, status: int) -> None:
    response = TestClient(main.app).get(path)
    assert response.status_code == status
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-xss-protection"] == "0"
    assert response.headers["content-type"] == "application/json"
    assert "x-frame-options" not in response.headers
    assert "permissions-policy" not in response.headers
    assert "content-security-policy" not in response.headers
    assert response.json().get("status", response.json().get("detail")) == ("ok" if status == 200 else "Not Found")


def test_security_headers_do_not_short_circuit_cors_preflight() -> None:
    origin = main.get_cors_origins()[0]
    response = TestClient(main.app).options(
        "/api/tasks",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "PATCH" in response.headers["access-control-allow-methods"]
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert response.headers["x-xss-protection"] == "0"
