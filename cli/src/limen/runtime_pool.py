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
from dataclasses import dataclass
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
from limen.storage_claim_census import SNAPSHOT_NAME, broker_storage_claims, read_claim_snapshot

SCHEMA = "limen.runtime_pool.v1"
MAX_AGE_SECONDS = 120
MAX_STATE_BYTES = 4 * 1024 * 1024


class PoolUnavailable(RuntimeError):
    """A typed, path-free admission failure."""


@dataclass(frozen=True)
class ClaimSelection:
    """The claims the pool reserves against, and which broker ledger they came from.

    ``broker_ledger`` is ``None`` when the caller supplied the claims itself, ``{"broker_ledger":
    "live"}`` after a successful broker read, and the frozen marker (``broker_ledger``, ``frozen_at``,
    ``reason``) when the claims came from the last-good snapshot. The pool copies it onto every
    decision, so ``scripts/runtime-pool.py --json`` carries it to the launcher unchanged.
    """

    claims: tuple[ResourceClaimV1, ...]
    broker_ledger: dict[str, str] | None = None


def _broker_claims(
    snapshot_path: Path | None, now: datetime | None
) -> tuple[tuple[ResourceClaimV1, ...], dict[str, str]]:
    """Live broker claims — or, while the keeper's write quota is spent, the frozen last-good set.

    Why memory is exact here and nowhere else. The keeper is a Cloudflare Durable Object on the free
    tier: once its daily WRITE cap trips (4444J99/limen#2054), the keeper refuses every write until
    the 00:00 UTC reset — and its reads fail with the same refusal, which is how this path is reached
    at all. Nothing can register, heartbeat, release, or expire a claim on a keeper that accepts no
    writes, so from the instant the wall went up the broker's claim set is frozen. The snapshot that
    the last successful read wrote is therefore not a stale cache of a moving ledger: for the whole
    outage it IS the ledger. (The one thing it cannot see is a claim written in the gap between that
    read and the wall. Every agent launch reads, so the gap is the launch cadence, and the pool still
    measures free disk live — a missed claim narrows the margin, it does not blind the gate.)

    That is also why there is no max-age cutoff beyond each claim's own ``rollback_until``. Honouring
    a remembered claim to its own expiry can only over-reserve: a claim the broker would have released
    early cannot be released while writes are refused, and a claim past ``rollback_until`` is dropped
    here exactly as the broker's own census drops it. Every OTHER broker failure — network, auth, an
    incomplete, stale or conflicting census — says nothing about whether the ledger moved, so memory
    would be a guess; those still fail closed, byte-for-byte as before.
    """
    try:
        return broker_storage_claims(snapshot_path), {"broker_ledger": "live"}
    except Exception as exc:
        # Lazy, like storage_claim_census: keeps the conduct package off this module's import path.
        from limen.conduct.client import BrokerQuotaExhausted

        snapshot = (
            read_claim_snapshot(snapshot_path)
            if isinstance(exc, BrokerQuotaExhausted) and snapshot_path is not None
            else None
        )
        if snapshot is None:
            # Every other failure — and a quota wall with nothing remembered — fails closed exactly
            # as before; selected_claims() names the reason.
            raise
        instant = now if now is not None else datetime.now(UTC)
        claims = tuple(claim for claim in snapshot.claims if claim.rollback_until > instant)
        return claims, {
            "broker_ledger": "frozen",
            "frozen_at": snapshot.observed_at.isoformat(),
            "reason": "broker_quota_exhausted",
        }


def selected_claims(snapshot_path: Path | None = None, *, now: datetime | None = None) -> ClaimSelection:
    try:
        machine, ledger = _broker_claims(snapshot_path, now)
        if not os.environ.get("LIMEN_RESOURCE_TASK_GRAPH"):
            return ClaimSelection(machine, ledger)
        selected = load_task_graph_claims(expected_run_id=os.environ.get("LIMEN_RESOURCE_TASK_GRAPH_RUN_ID") or None)
        path = Path(os.environ["LIMEN_RESOURCE_TASK_GRAPH"])
        if not 0 <= time.time() - path.stat().st_mtime <= MAX_AGE_SECONDS:
            raise PoolUnavailable("resource_graph_stale")
        claims = {claim.claim_id: claim for claim in machine}
        for claim in selected:
            if claim.claim_id in claims and claims[claim.claim_id] != claim:
                raise PoolUnavailable("resource_claim_conflict")
            claims[claim.claim_id] = claim
        return ClaimSelection(tuple(claims.values()), ledger)
    except PoolUnavailable:
        raise
    except Exception as exc:
        # Lazy, like storage_claim_census: keeps the conduct package off this module's import path.
        from limen.conduct.client import BrokerQuotaExhausted

        if isinstance(exc, BrokerQuotaExhausted):
            # The keeper's storage plan is spent (4444J99/limen#2054), not the disk and not a bug in
            # the census, and nothing was remembered to stand in for it. The gate still fails closed;
            # only the reason stops reading as a census fault.
            raise PoolUnavailable("broker_quota_exhausted") from exc
        reason = (
            str(exc)
            if isinstance(exc, ValueError) and str(exc).startswith("broker_storage_census_")
            else "broker_storage_census_unavailable"
        )
        raise PoolUnavailable(reason) from exc


class RuntimePool(AdmissionController):
    """Reuse the host lock, process identities, and atomic private-file writer."""

    @property
    def pool_path(self) -> Path:
        return self.root / "runtime-pool.json"

    @property
    def snapshot_path(self) -> Path:
        # Beside the pool file: the same private 0700 root, the same owner, the same lock. Not a new root.
        return self.root / SNAPSHOT_NAME

    def _select(self, claims: tuple | None) -> ClaimSelection:
        if claims is not None:
            return ClaimSelection(tuple(claims))
        return selected_claims(self.snapshot_path, now=datetime.fromtimestamp(self.clock(), UTC))

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

    def _observe(self, path: Path, rows: list[dict], claims: tuple, *, ledger: dict[str, str] | None = None) -> dict:
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
            reserved_claim = all_claims.get(row.get("claim_id"))
            included = reserved_claim.active_bytes(instant) if reserved_claim else 0
            reserved += max(0, row["bytes"] - included)
        free = shutil.disk_usage(path).free
        available = free - envelope.required_free_bytes - reserved
        decision: dict[str, Any] = {
            "schema": SCHEMA,
            "pool_mode": "shared_disk_aware",
            "observed_at": telemetry.observed_at.isoformat(),
            "max_age_seconds": MAX_AGE_SECONDS,
            "filesystem_free_bytes": free,
            "required_reserve_bytes": envelope.required_free_bytes,
            "reserve_components": {
                "projected_swap_expansion_bytes": telemetry.projected_swap_expansion_bytes,
                "updater_claim_bytes": telemetry.updater_claim_bytes,
                "apfs_churn_bytes": telemetry.apfs_churn_bytes,
                "peak_concurrent_task_bytes": envelope.peak_concurrent_task_bytes,
                "custody_and_rollback_staging_bytes": envelope.custody_and_rollback_staging_bytes,
                "telemetry_error_bytes": telemetry.telemetry_error_bytes,
            },
            "observation_age_seconds": max(0, age),
            "storage_claim_count": len(all_claims),
            "outstanding_growth_bytes": reserved,
            "available_growth_bytes": available,
            "reservation_count": sum(row["volume"] == volume for row in rows),
            "allowed": available > 0,
            "denial_reasons": [] if available > 0 else ["shared_pool_exhausted"],
        }
        if ledger:
            decision.update(ledger)
        return decision

    def observe(self, path: Path, *, claims: tuple | None = None) -> dict:
        try:
            with self._locked():
                rows = self._retained(self._read_pool()["reservations"])
                selection = self._select(claims)
                return self._observe(path, rows, selection.claims, ledger=selection.broker_ledger)
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
            selection = self._select(claims)
            selected = selection.claims
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
            decision = self._observe(path, [*rows, row], selected, ledger=selection.broker_ledger)
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
