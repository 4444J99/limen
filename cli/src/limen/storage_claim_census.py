"""Authoritative broker storage claims; never infer an empty graph from sessions."""

from __future__ import annotations

import contextlib
import json
import os
import shlex
import stat
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from limen.prima_materia import ResourceClaimV1

SCHEMA = "limen.storage_claim_census.v1"
SNAPSHOT_SCHEMA = "limen.broker_claim_snapshot.v1"
SNAPSHOT_NAME = "broker-claims-snapshot.json"
MAX_SNAPSHOT_BYTES = 4 * 1024 * 1024


def storage_claim_census(state, now, pending=lambda run: ()):
    occupied = set()
    for lease in state["leases"].values():
        run = state["runs"].get(lease["run_id"])
        if run and (
            (lease["state"] in {"reserved", "active"} and datetime.fromisoformat(lease["hard_deadline"]) > now)
            or any(row.get("lease_id") == lease["lease_id"] for row in pending(run))
        ):
            occupied.add(lease["run_id"])
    claims = {}
    errors = set()
    for run_id, run in state["runs"].items():
        packet = run.get("packet", {})
        raw_claims = packet.get("storage_envelope_claims") or []
        session = state["sessions"].get(run.get("executor_session_id"), {})
        if (
            run_id in occupied
            and packet.get("effect") == "write"
            and "local-worktree" in session.get("capabilities", [])
            and not raw_claims
        ):
            errors.add("active_local_writer_without_claim")
        for raw in raw_claims:
            try:
                claim = ResourceClaimV1.model_validate(raw)
            except ValueError:
                errors.add("invalid_storage_claim")
                continue
            if claim.rollback_until <= now:
                if run_id in occupied:
                    errors.add("active_writer_claim_expired")
                continue
            prior = claims.get(claim.claim_id)
            if prior is not None and prior != claim:
                errors.add("conflicting_storage_claim")
            claims[claim.claim_id] = claim
    return {
        "schema": SCHEMA,
        "observed_at": now.isoformat(),
        "complete": not errors,
        "active_run_count": len(occupied),
        "denial_reasons": sorted(errors),
        "claims": [claims[key].model_dump(mode="json") for key in sorted(claims)],
    }


def cached_conduct_credentials():
    keys = ("LIMEN_CONDUCT_URL", "LIMEN_CONDUCT_TOKEN")
    values = {key: os.environ[key] for key in keys if os.environ.get(key)}
    if len(values) == len(keys):
        return values
    path = Path(os.environ.get("LIMEN_ENV", str(Path.home() / ".limen.env")))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o600
            or info.st_size > 65536
        ):
            raise ValueError("credential_cache_unsafe")
        with os.fdopen(fd, "r", closefd=False) as stream:
            text = stream.read(65537)
    finally:
        os.close(fd)
    found = {}
    for line in text.splitlines():
        line = line.strip().removeprefix("export ")
        key, separator, raw = line.partition("=")
        key = key.strip()
        if separator and key in keys:
            if key in found:
                raise ValueError("credential_cache_ambiguous")
            tokens = shlex.split(raw, comments=True)
            if len(tokens) != 1:
                raise ValueError("credential_cache_invalid")
            found[key] = tokens[0]
    values = {**found, **values}
    if any(not values.get(key) for key in keys):
        raise ValueError("conduct_credentials_unavailable")
    return values


@dataclass(frozen=True)
class ClaimSnapshot:
    """The broker's claim set exactly as this host last read it successfully."""

    observed_at: datetime
    broker_observed_at: datetime
    claims: tuple[ResourceClaimV1, ...]


def write_claim_snapshot(
    path: Path, claims: Iterable[ResourceClaimV1], *, broker_observed_at: str, now: datetime | None = None
) -> bool:
    """Remember the last-good broker claim set beside the pool file: private (0600), atomic, best effort.

    Best effort is deliberate. The snapshot is consulted only while the broker's write quota is spent
    (``runtime_pool._broker_claims`` explains why that is the one failure memory is exact for); it is
    never an input to a live verdict. A failed write must therefore never turn a successful live read
    into a denial — that would make the launch gate *less* available than before the snapshot
    existed, the opposite of its purpose. The caller holds the live claims either way.
    """
    state = {
        "schema": SNAPSHOT_SCHEMA,
        "observed_at": (now if now is not None else datetime.now(UTC)).isoformat(),
        "broker_observed_at": broker_observed_at,
        "claims": [claim.model_dump(mode="json") for claim in claims],
    }
    payload = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(tmp, flags, 0o600)
    except OSError:
        return False
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        return True
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)
        return False
    finally:
        os.close(fd)


def read_claim_snapshot(path: Path) -> ClaimSnapshot | None:
    """The last-good snapshot, or ``None`` when there is nothing worth trusting.

    Absent, unreadable, not a private regular file owned by this user, hard-linked, oversized,
    malformed, naive-timestamped, or carrying claims that do not validate or repeat an id: every one
    of those is "no snapshot", because the only consumer is a fallback that fails closed without one.
    A damaged snapshot is never partially honoured and never becomes a stranger denial reason.
    """
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_nlink != 1:
            return None
        with os.fdopen(fd, "rb", closefd=False) as stream:
            data = stream.read(MAX_SNAPSHOT_BYTES + 1)
        if len(data) > MAX_SNAPSHOT_BYTES:
            return None
        state = json.loads(data)
        if (
            not isinstance(state, dict)
            or state.get("schema") != SNAPSHOT_SCHEMA
            or not isinstance(state.get("claims"), list)
        ):
            return None
        observed_at = datetime.fromisoformat(state["observed_at"])
        broker_observed_at = datetime.fromisoformat(state["broker_observed_at"])
        if observed_at.tzinfo is None or broker_observed_at.tzinfo is None:
            return None
        claims = tuple(ResourceClaimV1.model_validate(raw) for raw in state["claims"])
        if len({claim.claim_id for claim in claims}) != len(claims):
            return None
        return ClaimSnapshot(observed_at, broker_observed_at, claims)
    except (KeyError, TypeError, ValueError):
        return None
    finally:
        os.close(fd)


def broker_storage_claims(snapshot_path: Path | None = None):
    from limen.conduct.client import HttpConductClient

    values = cached_conduct_credentials()
    capabilities = HttpConductClient(
        values["LIMEN_CONDUCT_URL"], values["LIMEN_CONDUCT_TOKEN"], timeout=5
    ).capabilities()
    census = capabilities.get("storage_claim_census")
    if not isinstance(census, dict) or census.get("schema") != SCHEMA:
        raise ValueError("broker_storage_census_unavailable")
    age = (datetime.now(UTC) - datetime.fromisoformat(census["observed_at"])).total_seconds()
    if not -1 <= age <= 120:
        raise ValueError("broker_storage_census_stale")
    if census.get("complete") is not True or not isinstance(census.get("claims"), list):
        raise ValueError("broker_storage_census_incomplete")
    claims = tuple(ResourceClaimV1.model_validate(raw) for raw in census["claims"])
    if len({claim.claim_id for claim in claims}) != len(claims):
        raise ValueError("broker_storage_census_duplicate")
    if snapshot_path is not None:
        # Only a read that passed every check above is worth remembering: a stale, incomplete or
        # duplicate census raised before this line, so the snapshot can never hold a claim set the
        # live gate would have refused.
        write_claim_snapshot(snapshot_path, claims, broker_observed_at=census["observed_at"])
    return claims
