"""Private loopback receiver for the owned Codex process's native render metrics.

No file or caller receipt is accepted as a rendering witness. The process-local
OTLP override affects only this observer process and is never written to config.
All unrelated metrics, resource attributes and private content are discarded.
"""

from __future__ import annotations

import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import secrets
import threading
import time


METRICS = {
    "codex.thread.skills.enabled_total": "enabled",
    "codex.thread.skills.kept_total": "kept",
    "codex.thread.skills.truncated": "omitted",
    "codex.thread.skills.description_truncated_chars": "truncated_chars",
}
LIMIT = 4 * 1024 * 1024


def render_metrics(payload, version, started_ns):
    """Return complete, fresh, constant histograms from one native render surface."""
    found = {}
    for resource in payload.get("resourceMetrics", []):
        attrs = resource.get("resource", {}).get("attributes", [])
        versions = [a.get("value", {}).get("stringValue") for a in attrs if a.get("key") == "service.version"]
        if versions != [version]:
            continue
        for scope in resource.get("scopeMetrics", []):
            for metric in scope.get("metrics", []):
                name = METRICS.get(metric.get("name"))
                if name is None:
                    continue
                for point in metric.get("histogram", {}).get("dataPoints", []):
                    surfaces = [
                        a.get("value", {}).get("stringValue")
                        for a in point.get("attributes", [])
                        if a.get("key") == "catalog_surface"
                    ]
                    if surfaces != ["thread_context"]:
                        continue
                    count = int(point.get("count", 0))
                    timestamp = int(point.get("timeUnixNano", 0))
                    minimum, maximum, total = (point.get(k) for k in ("min", "max", "sum"))
                    if (
                        name in found
                        or count <= 0
                        or timestamp < started_ns
                        or any(
                            type(v) not in (int, float) or not math.isfinite(v) or v < 0
                            for v in (minimum, maximum, total)
                        )
                        or minimum != maximum
                        or total != minimum * count
                    ):
                        return None
                    found[name] = {"value": minimum, "count": count, "timestamp": timestamp}
    if set(found) != set(METRICS.values()) or len({v["count"] for v in found.values()}) != 1:
        return None
    timestamps = [v["timestamp"] for v in found.values()]
    if max(timestamps) - min(timestamps) > 1_000_000_000:
        return None
    values = {key: value["value"] for key, value in found.items()}
    if (
        any(int(v) != v for v in values.values())
        or values["kept"] > values["enabled"]
        or values["omitted"] not in (0, 1)
    ):
        return None
    return values


class RenderMetrics:
    def __init__(self, version):
        self.version = version
        self.started_ns = time.time_ns()
        self.token = secrets.token_urlsafe(32)  # allow-secret: ephemeral owned loopback capability, never persisted
        self.bytes_read = 0
        self.latest = None
        self.lock = threading.Lock()
        self.received = threading.Event()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.connection.settimeout(1)
                if self.path != "/v1/metrics" or not hmac.compare_digest(
                    self.headers.get("Authorization", ""), "Bearer " + owner.token
                ):
                    self.send_error(403)
                    return
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    if not 0 < length <= LIMIT or owner.bytes_read + length > LIMIT:
                        raise ValueError("native telemetry output ceiling")
                    raw = self.rfile.read(length)
                    owner.bytes_read += length
                    if len(raw) != length:
                        raise ValueError("short native telemetry")
                    metrics = render_metrics(json.loads(raw), owner.version, owner.started_ns)
                    if metrics:
                        with owner.lock:
                            owner.latest = metrics
                        owner.received.set()
                    body = b"{}"
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (ValueError, TypeError, AttributeError, KeyError, OSError):
                    self.send_error(400)

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.server.timeout = 0.1
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._serve, name="native-render-metrics", daemon=True)

    def _serve(self):
        while not self.stopping.is_set():
            self.server.handle_request()

    def start(self):
        self.thread.start()

    def configuration(self):
        port = self.server.server_address[1]
        # JSON quoting is valid for these TOML basic-string values.
        endpoint = json.dumps(f"http://127.0.0.1:{port}/v1/metrics")
        authorization = json.dumps("Bearer " + self.token)
        return (
            "otel.metrics_exporter={otlp-http={endpoint="
            + endpoint
            + ',protocol="json",headers={Authorization='
            + authorization
            + "}}}"
        )

    def evidence(self, expected_skills, timeout=1):
        self.received.wait(max(0, min(1, timeout)))
        with self.lock:
            values = dict(self.latest) if self.latest else None
        complete = bool(values and expected_skills > 0 and values["enabled"] == expected_skills)
        return {
            "source": "owned-native-otlp",
            "state": "pass"
            if complete
            and values["kept"] == expected_skills
            and values["omitted"] == 0
            and values["truncated_chars"] == 0
            else "fail"
            if complete
            else "unmeasured",
            "native_metrics": values,
            "expected_enabled_skills": expected_skills,
            "fresh_native_loading_witness": complete,
        }

    def close(self):
        self.stopping.set()
        if self.thread.is_alive():
            self.thread.join(2)
        self.server.server_close()
