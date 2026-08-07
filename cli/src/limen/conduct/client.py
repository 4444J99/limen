"""Authenticated remote client and explicit local test adapter for the conduct broker."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from limen.conduct.broker import ConductBroker, ConductConflict, ConductError
from limen.conduct.models import ConductorSessionV1, ExecutorAttemptV1, RunReceiptV1, WorkPacketV1
from limen.conduct.store import SQLiteStateStore


class BrokerUnavailable(ConductError):
    pass


class BrokerQuotaExhausted(ConductError):
    """The keeper's storage plan is spent — every relay WRITE is refused until it is raised or resets.

    Not a bug and not a transient network fault, which is why it needs its own type: no retry, no
    backoff, and no amount of correct client code makes the next write land. The resolution is a
    spend/billing decision by the owner, so the condition's real home is a lever in
    ``his-hand-levers.json`` (``L-CLOUDFLARE-DO-QUOTA``), not a traceback in a beat log.

    Measured 2026-08-07: ``POST /api/conduct/sessions`` began answering

        500 {"detail": "Exceeded allowed rows written in Durable Objects free tier."}

    ``_register_relay_session`` is on EVERY relay write path, so this one wall blocked the
    canonical-heal rung, dispatch receipts, and board publication simultaneously — while twelve
    regressed ``needs-human`` atoms stayed regressed and the beat log showed a bare ``}``.

    **This classifies on the rejection PROSE, which the estate otherwise forbids** (see
    ``ConductError``: three keepers word the same condition differently, so callers are told to
    classify on ``status``). The exemption is narrow and deliberate: a Cloudflare storage-quota
    refusal surfaces as an undifferentiated 500 with no machine-readable field to read, so prose is
    the ONLY available signal. The durable fix is for the keeper to answer a structured code — that
    work is recorded on the lever, and this detection becomes the compatibility fallback for a
    keeper that has not been redeployed. Until then, matching a generic 500 is strictly better than
    the alternative, which is what actually happened: a 61-line traceback nobody could see.
    """


# Substrings that identify a storage-plan wall rather than a keeper defect. Kept narrow on purpose:
# a broad match here would reclassify real 500s as "blocked on the owner" and hide genuine bugs.
_QUOTA_MARKERS = (
    "exceeded allowed rows written",
    "durable objects free tier",
    "exceeded your storage limit",
)


def _is_quota_refusal(status: int | None, detail: str) -> bool:
    """A storage-plan wall, as opposed to a keeper defect or a rate limit.

    A quota marker is REQUIRED — status alone is never enough, because 500 is exactly what a real
    bug also returns. 429 is included because a plan ceiling can surface as a throttle, but only
    when the body still names the ceiling.
    """
    if status not in (429, 500, 503):
        return False
    lowered = detail.lower()
    return any(marker in lowered for marker in _QUOTA_MARKERS)


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
                "user-agent": "limen-conduct-client/1",
                **({"content-type": "application/json"} if body is not None else {}),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:1000]
            message = f"conduct broker rejected request ({exc.code}): {detail}"
            # The status code is the stable signal; `detail` is keeper-authored prose that
            # differs per implementation. Carry the code so callers never parse the text.
            if exc.code == 409:
                raise ConductConflict(message, status=exc.code) from exc
            if _is_quota_refusal(exc.code, detail):
                # Distinguished from a generic 500 so callers can report "blocked on the owner's
                # spend lever" instead of retrying a write that cannot land until he acts.
                raise BrokerQuotaExhausted(message, status=exc.code) from exc
            raise ConductError(message, status=exc.code) from exc
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

    def task_run(self, task_id: str) -> dict[str, Any]:
        task = urllib.parse.quote(task_id, safe="")
        return self._request("GET", f"/api/conduct/tasks/{task}/run")

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

    def task_run(self, task_id: str) -> dict[str, Any]:
        return self.broker.task_run(task_id)

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
