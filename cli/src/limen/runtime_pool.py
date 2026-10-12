"""Disk-backed agent growth admission under the existing machine-wide host lock.

The pool is shared by every vendor and checkout. It reserves managed growth,
not ordinary vendor writes. Resource envelopes remain the reserve authority.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import stat
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.host_admission import AdmissionController, AdmissionStateError
from limen.prima_materia import ResourceClaimV1
from limen.resource_envelope import (
    ResourceGraphError,
    ResourceTelemetryUnavailable,
    evaluate_resource_envelope,
    load_task_graph_claims,
    observe_resource_telemetry,
)

SCHEMA = "limen.runtime_pool.v1"
MAX_AGE_SECONDS = 120
MAX_STATE_BYTES = 4 * 1024 * 1024


class PoolUnavailable(RuntimeError):
    """A typed, path-free admission failure."""


def selected_claims() -> tuple[ResourceClaimV1, ...]:
    claims = load_task_graph_claims(
        expected_run_id=os.environ.get("LIMEN_RESOURCE_TASK_GRAPH_RUN_ID") or None,
    )
    path = Path(os.environ["LIMEN_RESOURCE_TASK_GRAPH"])
    age = time.time() - path.stat().st_mtime
    if not 0 <= age <= MAX_AGE_SECONDS:
        raise PoolUnavailable("resource_graph_stale")
    return claims


class RuntimePool(AdmissionController):
    """Reuse the host lock, process identities, and atomic private-file writer."""

    @property
    def pool_path(self) -> Path:
        return self.root / "runtime-pool.json"

    def _read_pool(self) -> dict[str, Any]:
        try:
            fd = os.open(self.pool_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return {"schema": SCHEMA, "reservations": []}
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_nlink != 1
            ):
                raise ValueError()
            with os.fdopen(fd, "rb", closefd=False) as stream:
                data = stream.read(MAX_STATE_BYTES + 1)
            state = json.loads(data)
            if len(data) > MAX_STATE_BYTES or not isinstance(state, dict) or state.get("schema") != SCHEMA:
                raise ValueError()
            rows = state["reservations"]
            if not isinstance(rows, list) or len(rows) > 4096:
                raise ValueError()
            ids = set()
            for row in rows:
                if (
                    not isinstance(row, dict)
                    or row["id"] in ids
                    or type(row["bytes"]) is not int
                    or row["bytes"] <= 0
                    or type(row["pid"]) is not int
                    or row["pid"] <= 0
                    or type(row["expires"]) not in (int, float)
                    or not math.isfinite(row["expires"])
                    or not isinstance(row["identity"], str)
                    or not isinstance(row["owner"], str)
                    or not isinstance(row["volume"], int)
                    or row.get("claim_id") is not None
                    and not isinstance(row["claim_id"], str)
                ):
                    raise ValueError()
                ids.add(row["id"])
                for claim in row["claims"]:
                    ResourceClaimV1.model_validate(claim)
            return state
        except (KeyError, TypeError, ValueError) as exc:
            raise PoolUnavailable("pool_state_invalid") from exc
        finally:
            os.close(fd)

    def _retained(self, rows: list[dict]) -> list[dict]:
        # Expiry alone cannot release capacity while a writer still runs.
        return [
            row
            for row in rows
            if not (
                self.clock() >= row["expires"]
                and (
                    not self.alive(row["pid"])
                    or (self.identity(row["pid"]) is not None and self.identity(row["pid"]) != row["identity"])
                )
            )
        ]

    def _observe(self, path: Path, rows: list[dict], claims: tuple) -> dict:
        instant = datetime.fromtimestamp(self.clock(), UTC)
        telemetry = observe_resource_telemetry()
        age = (instant - telemetry.observed_at).total_seconds()
        if not -1 <= age <= MAX_AGE_SECONDS:
            raise PoolUnavailable("resource_telemetry_stale")
        all_claims = {claim.claim_id: claim for claim in claims}
        for row in rows:
            for raw in row["claims"]:
                claim = ResourceClaimV1.model_validate(raw)
                prior = all_claims.get(claim.claim_id)
                if prior is not None and prior != claim:
                    raise PoolUnavailable("resource_claim_conflict")
                all_claims[claim.claim_id] = claim
        envelope = evaluate_resource_envelope(telemetry, tuple(all_claims.values()), observed_at=instant)
        volume = path.stat().st_dev
        reserved = 0
        for row in rows:
            if row["volume"] != volume:
                continue
            claim = all_claims.get(row.get("claim_id"))
            included = claim.active_bytes(instant) if claim else 0
            reserved += max(0, row["bytes"] - included)
        free = shutil.disk_usage(path).free
        available = free - envelope.required_free_bytes - reserved
        return {
            "schema": SCHEMA,
            "pool_mode": "shared_disk_aware",
            "observed_at": telemetry.observed_at.isoformat(),
            "max_age_seconds": MAX_AGE_SECONDS,
            "filesystem_free_bytes": free,
            "required_reserve_bytes": envelope.required_free_bytes,
            "outstanding_growth_bytes": reserved,
            "available_growth_bytes": available,
            "reservation_count": sum(row["volume"] == volume for row in rows),
            "allowed": available > 0,
            "denial_reasons": [] if available > 0 else ["shared_pool_exhausted"],
        }

    def observe(self, path: Path, *, claims: tuple | None = None) -> dict:
        try:
            with self._locked():
                rows = self._retained(self._read_pool()["reservations"])
                return self._observe(path, rows, selected_claims() if claims is None else claims)
        except (
            ResourceGraphError,
            ResourceTelemetryUnavailable,
            AdmissionStateError,
            PoolUnavailable,
            OSError,
            ValueError,
        ) as exc:
            reason = str(exc) if isinstance(exc, PoolUnavailable) else type(exc).__name__
            return {
                "schema": SCHEMA,
                "pool_mode": "shared_disk_aware",
                "allowed": False,
                "denial_reasons": [reason],
                "available_growth_bytes": None,
            }

    def reserve(
        self,
        path: Path,
        *,
        owner: str,
        pid: int,
        growth_bytes: int,
        ttl_seconds: int = 1800,
        claim_id: str | None = None,
        claims: tuple | None = None,
    ) -> dict:
        if (
            not owner
            or len(owner) > 160
            or type(growth_bytes) is not int
            or growth_bytes <= 0
            or not 1 <= ttl_seconds <= 1800
        ):
            raise ValueError("invalid_growth_reservation")
        identity = self.identity(pid)
        if identity is None or not self.alive(pid):
            raise PoolUnavailable("reservation_process_unavailable")
        with self._locked():
            state = self._read_pool()
            rows = self._retained(state["reservations"])
            selected = selected_claims() if claims is None else claims
            if claim_id is not None:
                if not any(claim.claim_id == claim_id for claim in selected):
                    raise PoolUnavailable("reservation_claim_missing")
                if any(row.get("claim_id") == claim_id for row in rows):
                    raise PoolUnavailable("reservation_claim_already_owned")
            row = {
                "id": uuid.uuid4().hex,
                "owner": owner,
                "pid": pid,
                "identity": identity,
                "bytes": growth_bytes,
                "expires": self.clock() + ttl_seconds,
                "volume": path.stat().st_dev,
                "claim_id": claim_id,
                "claims": [claim.model_dump(mode="json") for claim in selected],
            }
            decision = self._observe(path, [*rows, row], selected)
            if decision["available_growth_bytes"] < 0:
                decision.update(allowed=False, denial_reasons=["shared_pool_exhausted"])
                return decision
            state["reservations"] = [*rows, row]
            self._write_file(self.pool_path, state)
            decision.update(allowed=True, denial_reasons=[], reservation_id=row["id"])
            return decision

    def release_growth(self, reservation_id: str, *, owner: str, pid: int) -> dict:
        with self._locked():
            state = self._read_pool()
            row = next((row for row in state["reservations"] if row["id"] == reservation_id), None)
            if row is not None and (
                row["owner"] != owner or row["pid"] != pid or row["identity"] != self.identity(pid)
            ):
                raise PoolUnavailable("reservation_owner_mismatch")
            state["reservations"] = [row for row in state["reservations"] if row["id"] != reservation_id]
            self._write_file(self.pool_path, state)
            return {"schema": SCHEMA, "released": True, "already_released": row is None}
