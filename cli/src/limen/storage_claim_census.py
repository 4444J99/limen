"""Authoritative broker storage claims; never infer an empty graph from sessions."""

from __future__ import annotations

import os
import shlex
import stat
from datetime import UTC, datetime
from pathlib import Path

from limen.prima_materia import ResourceClaimV1

SCHEMA = "limen.storage_claim_census.v1"


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


def broker_storage_claims():
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
    return claims
