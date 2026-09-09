"""Read-only GitHub RPC over inherited pipes for connector-owned authentication.

The host must service each request with its authenticated GitHub connector. This
transport does not grant authority, load recorded responses, or impersonate gh.
"""

from __future__ import annotations

import json
import os
import re
import select
import sys
import time
import termios
import tty
import uuid
from urllib.parse import urlsplit

SCHEMA = "limen.github_connector.v1"
PREFIX = "limen.github.request "
MAX_RESPONSE_BYTES = 16 * 1024 * 1024


class ConnectorError(RuntimeError):
    """The host did not supply a complete correlated live observation."""


def read_url(args: list[str], input_value: object | None = None) -> str:
    """Accept only the REST GET subset used by the positioning controller."""
    if len(args) != 2 or args[0] != "api" or input_value is not None:
        raise ConnectorError("connector transport supports REST GET observations only")
    path = args[1]
    parsed = urlsplit(path)
    if parsed.scheme or parsed.netloc or parsed.fragment or "%" in path or "\\" in path:
        raise ConnectorError("invalid GitHub observation path")
    if any(part in {".", ".."} for part in parsed.path.split("/")):
        raise ConnectorError("invalid GitHub observation path")
    if not re.fullmatch(
        r"(?:repositories/[1-9][0-9]*|repos/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/"
        r"(?:issues|pulls|git/trees|contents|commits|labels|milestones)(?:/[A-Za-z0-9_./-]+)?)",
        parsed.path,
    ):
        raise ConnectorError("unsupported GitHub observation endpoint")
    if parsed.query and not re.fullmatch(r"[A-Za-z0-9_=&.-]+", parsed.query):
        raise ConnectorError("invalid GitHub observation query")
    return f"https://api.github.com/{path}"


class StdioGitHubConnector:
    """One outstanding request, fresh correlation ID, finite response deadline."""

    def __init__(self, *, timeout: float = 120.0, input_fd: int | None = None, output=None):
        self.timeout = timeout
        self.input_fd = sys.stdin.fileno() if input_fd is None else input_fd
        self.output = sys.stderr if output is None else output
        self.terminal_state = termios.tcgetattr(self.input_fd) if os.isatty(self.input_fd) else None
        if self.terminal_state is not None:
            # Some hosts keep stdin open only for PTYs. Disable echo and the
            # terminal's canonical line cap before receiving private JSON.
            tty.setraw(self.input_fd, termios.TCSANOW)

    def close(self) -> None:
        if self.terminal_state is not None:
            termios.tcsetattr(self.input_fd, termios.TCSANOW, self.terminal_state)
            self.terminal_state = None

    def request(self, args: list[str], input_value: object | None = None):
        url = read_url(args, input_value)
        request_id = uuid.uuid4().hex
        request = {"schema": SCHEMA, "id": request_id, "method": "GET", "url": url}
        self.output.write(PREFIX + json.dumps(request, separators=(",", ":")) + "\n")
        self.output.flush()
        deadline = time.monotonic() + self.timeout
        raw = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.input_fd], [], [], max(0, remaining))[0]:
                raise ConnectorError("GitHub connector response deadline exceeded")
            chunk = os.read(self.input_fd, min(65536, MAX_RESPONSE_BYTES + 1 - len(raw)))
            if not chunk:
                raise ConnectorError("GitHub connector response stream closed")
            raw.extend(chunk)
            if len(raw) > MAX_RESPONSE_BYTES:
                raise ConnectorError("GitHub connector response exceeds size limit")
            if b"\n" in raw:
                line, extra = raw.split(b"\n", 1)
                if extra.strip():
                    raise ConnectorError("unsolicited GitHub connector response")
                break
        try:
            response = json.loads(line)
        except (ValueError, UnicodeDecodeError) as exc:
            raise ConnectorError("GitHub connector returned invalid JSON") from exc
        if not isinstance(response, dict) or any(
            response.get(k) != request[k] for k in ("schema", "id", "method", "url")
        ):
            raise ConnectorError("GitHub connector response correlation mismatch")
        if response.get("ok") is not True or "value" not in response:
            raise ConnectorError("authenticated GitHub connector observation unavailable")
        return response["value"]
