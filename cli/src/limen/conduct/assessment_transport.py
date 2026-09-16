"""Credential-isolated, bounded HTTP transport for dependency assessment callbacks."""

from __future__ import annotations

import json
import sys
import urllib.parse
from pathlib import Path
from typing import Any

from limen.bounded_subprocess import BoundedSubprocessError, run_bounded_subprocess
from limen.conduct.client import BrokerUnavailable, HttpConductClient
from limen.conduct._assessment_http import LIMIT


class AssessmentHttpClient(HttpConductClient):
    """Use existing protocol methods with a finite process per HTTP exchange."""

    def __init__(self, endpoint: str, token: str):  # allow-secret: parameter, no literal secret
        parsed = urllib.parse.urlsplit(endpoint)
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
            or not parsed.hostname
            or not isinstance(token, str)
            or any(char in token for char in "\r\n\x00")
        ):
            raise ValueError("invalid assessment transport configuration")
        super().__init__(endpoint, token)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            if method not in {"GET", "POST"} or not path.startswith("/api/conduct/"):
                raise ValueError
            request = json.dumps(
                {"url": self.endpoint + path, "method": method, "credential": self.token, "payload": payload}
            ).encode()
            if len(request) > LIMIT:
                raise ValueError
            helper = Path(__file__).with_name("_assessment_http.py")
            result = run_bounded_subprocess(
                [sys.executable, "-I", str(helper)],
                cwd=helper.parent,
                input_bytes=request,
                env={"LANG": "C.UTF-8"},
                timeout_seconds=20,
                stdout_ceiling=2 * LIMIT,
                stderr_ceiling=4096,
            )
            if result.returncode != 0:
                raise ValueError
            response = json.loads(result.stdout)
            if (
                not isinstance(response, dict)
                or type(response.get("status")) is not int
                or not 200 <= response["status"] < 300
                or not isinstance(response.get("payload"), dict)
            ):
                raise ValueError
            return response["payload"]
        except (OSError, ValueError, TypeError, RecursionError, BoundedSubprocessError):
            raise BrokerUnavailable("assessment broker exchange is unmeasured; no automatic retry") from None
