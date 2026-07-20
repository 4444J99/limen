"""Authenticated remote client and explicit local test adapter for the conduct broker."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from limen.conduct.broker import ConductBroker, ConductError
from limen.conduct.models import ConductorSessionV1, ExecutorAttemptV1, RunReceiptV1, WorkPacketV1
from limen.conduct.store import SQLiteStateStore


class BrokerUnavailable(ConductError):
    pass


class HttpConductClient:
    def __init__(self, endpoint: str, token: str, *, timeout: int = 30):
        if not endpoint.startswith("https://") and not endpoint.startswith("http://127.0.0.1:"):
            raise ValueError("conduct endpoint must use HTTPS (loopback HTTP is allowed for ianva)")
        if not token:
            raise BrokerUnavailable("authenticated conduct token is required")
        self.endpoint = endpoint.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.endpoint}{path}",
            data=body,
            method=method,
            headers={
                "authorization": f"Bearer {self.token}",
                "accept": "application/json",
                **({"content-type": "application/json"} if body is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            raise ConductError(f"conduct broker rejected request ({exc.code}): {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise BrokerUnavailable(f"conduct broker unavailable: {exc}") from exc
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError as exc:
            raise ConductError("conduct broker returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise ConductError("conduct broker response must be an object")
        return parsed

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/api/conduct/capabilities")

    def register(self, session: ConductorSessionV1) -> dict[str, Any]:
        return self._request("POST", "/api/conduct/sessions", session.model_dump(mode="json"))

    def submit(self, packet: WorkPacketV1) -> dict[str, Any]:
        return self._request("POST", "/api/conduct/runs", packet.model_dump(mode="json"))

    def submit_graph(self, packets: tuple[WorkPacketV1, ...]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/conduct/graphs",
            {"packets": [packet.model_dump(mode="json") for packet in packets]},
        )

    def split(self, parent_run_id: str, packet: WorkPacketV1) -> dict[str, Any]:
        parent = urllib.parse.quote(parent_run_id, safe="")
        return self._request("POST", f"/api/conduct/runs/{parent}/children", packet.model_dump(mode="json"))

    def graph(self, root_run_id: str) -> dict[str, Any]:
        root = urllib.parse.quote(root_run_id, safe="")
        return self._request("GET", f"/api/conduct/runs/{root}/graph")

    def claim(self, lease_id: str, generation: int) -> dict[str, Any]:
        lease = urllib.parse.quote(lease_id, safe="")
        return self._request(
            "POST",
            f"/api/conduct/leases/{lease}/claim",
            {"generation": generation},
        )

    def heartbeat(
        self,
        lease_id: str,
        capability_token: str,
        *,
        generation: int,
        observed_heads: dict[str, str] | None = None,
        attempt: ExecutorAttemptV1 | None = None,
    ) -> dict[str, Any]:
        lease = urllib.parse.quote(lease_id, safe="")
        return self._request(
            "POST",
            f"/api/conduct/leases/{lease}/heartbeat",
            {
                "capability_token": capability_token,
                "generation": generation,
                "observed_heads": observed_heads or {},
                **({"attempt": attempt.model_dump(mode="json")} if attempt is not None else {}),
            },
        )

    def report(
        self,
        lease_id: str,
        capability_token: str,
        receipt: RunReceiptV1,
        *,
        generation: int,
    ) -> dict[str, Any]:
        lease = urllib.parse.quote(lease_id, safe="")
        return self._request(
            "POST",
            f"/api/conduct/leases/{lease}/receipt",
            {
                "capability_token": capability_token,
                "generation": generation,
                "receipt": receipt.model_dump(mode="json"),
            },
        )

    def harvest(self, root_run_id: str) -> dict[str, Any]:
        root = urllib.parse.quote(root_run_id, safe="")
        return self._request("GET", f"/api/conduct/runs/{root}/harvest")

    def adopt(self, run_id: str, session_id: str) -> dict[str, Any]:
        run = urllib.parse.quote(run_id, safe="")
        return self._request("POST", f"/api/conduct/runs/{run}/adopt", {"session_id": session_id})

    def cancel(self, run_id: str, session_id: str) -> dict[str, Any]:
        run = urllib.parse.quote(run_id, safe="")
        return self._request("POST", f"/api/conduct/runs/{run}/cancel", {"session_id": session_id})

    def request_stop(self, run_id: str, session_id: str) -> dict[str, Any]:
        run = urllib.parse.quote(run_id, safe="")
        return self._request("POST", f"/api/conduct/runs/{run}/request-stop", {"session_id": session_id})


class LocalConductClient:
    """Explicit SQLite adapter for tests and disconnected development only."""

    def __init__(self, path: Path | str):
        self.path = Path(path).expanduser().resolve()
        self.store = SQLiteStateStore(self.path)
        self.broker = ConductBroker(self.store)

    def capabilities(self) -> dict[str, Any]:
        return self.broker.capabilities()

    def register(self, session: ConductorSessionV1) -> dict[str, Any]:
        return self.broker.register(session)

    def submit(self, packet: WorkPacketV1) -> dict[str, Any]:
        return self.broker.submit(packet)

    def submit_graph(self, packets: tuple[WorkPacketV1, ...]) -> dict[str, Any]:
        return self.broker.submit_graph(packets)

    def submit_projection(
        self,
        packet: WorkPacketV1,
        project_task_event,
    ) -> dict[str, Any]:
        """Submit one task packet through the local keeper's atomic projection seam.

        The callback computes an acknowledged projection in memory while the
        SQLite keeper transaction is held. TABVLARIVS serializes that receipt to
        its temporary cache only after this method returns successfully.
        """

        return self.broker.submit(packet, project_task_event=project_task_event)

    def replay_projection(self, work_id: str) -> dict[str, Any] | None:
        return self.broker.replay_work(work_id)

    def local_board_projection(self) -> dict[str, Any] | None:
        return self.broker.local_board_projection()

    def split(self, parent_run_id: str, packet: WorkPacketV1) -> dict[str, Any]:
        return self.broker.split(parent_run_id, packet)

    def graph(self, root_run_id: str) -> dict[str, Any]:
        return self.broker.graph(root_run_id)

    def claim(self, lease_id: str, generation: int) -> dict[str, Any]:
        return self.broker.claim(lease_id, generation)

    def heartbeat(
        self,
        lease_id: str,
        capability_token: str,
        *,
        generation: int,
        observed_heads: dict[str, str] | None = None,
        attempt: ExecutorAttemptV1 | None = None,
    ) -> dict[str, Any]:
        return self.broker.heartbeat(
            lease_id,
            capability_token,
            generation=generation,
            observed_heads=observed_heads,
            attempt=attempt,
        )

    def report(
        self,
        lease_id: str,
        capability_token: str,
        receipt: RunReceiptV1,
        *,
        generation: int,
    ) -> dict[str, Any]:
        return self.broker.report(
            lease_id,
            capability_token,
            receipt,
            generation=generation,
        )

    def harvest(self, root_run_id: str) -> dict[str, Any]:
        return self.broker.harvest(root_run_id)

    def adopt(self, run_id: str, session_id: str) -> dict[str, Any]:
        return self.broker.adopt(run_id, session_id)

    def cancel(self, run_id: str, session_id: str) -> dict[str, Any]:
        return self.broker.cancel(run_id, session_id)

    def request_stop(self, run_id: str, session_id: str) -> dict[str, Any]:
        return self.broker.request_stop(run_id, session_id)


def client_from_env():
    endpoint = os.environ.get("LIMEN_CONDUCT_URL", "").strip()
    token = os.environ.get("LIMEN_CONDUCT_TOKEN", "").strip()
    if endpoint:
        return HttpConductClient(endpoint, token)
    local_state = os.environ.get("LIMEN_CONDUCT_STATE", "").strip()
    if local_state:
        return LocalConductClient(Path(local_state).expanduser())
    raise BrokerUnavailable(
        "conduct broker is not configured; set LIMEN_CONDUCT_URL and LIMEN_CONDUCT_TOKEN "
        "(LIMEN_CONDUCT_STATE is an explicit local test adapter)"
    )
