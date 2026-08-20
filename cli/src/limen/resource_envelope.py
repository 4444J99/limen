"""Telemetry-backed storage envelope for a selected task graph."""

from __future__ import annotations

import json
import hashlib
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import rfc8785

from limen.prima_materia import ResourceClaimV1

TASK_GRAPH_SCHEMA = "limen.resource_task_graph.v1"
MAX_TASK_GRAPH_BYTES = 4 * 1024 * 1024
_NATIVE_POPEN = subprocess.Popen


class ResourceGraphError(ValueError):
    """Base class for selected-graph admission failures."""


class ResourceGraphMissing(ResourceGraphError):
    """No selected graph was supplied."""


class ResourceGraphInvalid(ResourceGraphError):
    """A selected graph exists but cannot be trusted."""


class ResourceTelemetryUnavailable(RuntimeError):
    """The host cannot provide the telemetry needed for admission."""


def _canonical_digest(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _capture_command(args: list[str], *, timeout: int = 5) -> str:
    """Read host telemetry without borrowing a caller's patched launch seam."""

    process = _NATIVE_POPEN(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        raise
    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode,
            args,
            output=stdout,
            stderr=stderr,
        )
    return stdout


@dataclass(frozen=True)
class ResourceTelemetry:
    observed_at: datetime
    ram_total_bytes: int
    ram_available_bytes: int
    swap_used_bytes: int
    updater_claim_bytes: int
    apfs_churn_bytes: int
    telemetry_error_bytes: int

    def validate(self) -> None:
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("resource telemetry time must include an explicit UTC offset")
        values = (
            self.ram_total_bytes,
            self.ram_available_bytes,
            self.swap_used_bytes,
            self.updater_claim_bytes,
            self.apfs_churn_bytes,
            self.telemetry_error_bytes,
        )
        if any(isinstance(value, bool) or value < 0 for value in values):
            raise ValueError("resource telemetry must contain nonnegative byte counts")
        if self.ram_available_bytes > self.ram_total_bytes:
            raise ValueError("available RAM cannot exceed total RAM")

    @property
    def projected_swap_expansion_bytes(self) -> int:
        # Live swap use is the observable backing-store claim. Available RAM
        # offsets it because those pages can return without additional disk.
        return max(0, self.swap_used_bytes - self.ram_available_bytes)


@dataclass(frozen=True)
class ResourceEnvelope:
    observed_at: datetime
    observed_system_reserve_bytes: int
    peak_concurrent_task_bytes: int
    custody_and_rollback_staging_bytes: int
    telemetry_error_bytes: int
    required_free_bytes: int

    @property
    def required_free_gib(self) -> float:
        return self.required_free_bytes / (1024**3)

    @property
    def peak_concurrent_memory_bytes(self) -> int:
        return self.peak_concurrent_task_bytes

    @property
    def memory_nonnegative(self) -> bool:
        return self.required_free_bytes >= 0


def evaluate_resource_envelope(
    telemetry: ResourceTelemetry,
    claims: tuple[ResourceClaimV1, ...],
    *,
    observed_at: datetime | None = None,
) -> ResourceEnvelope:
    telemetry.validate()
    instant = observed_at or telemetry.observed_at
    if instant.tzinfo is None or instant.utcoffset() is None:
        raise ValueError("resource envelope time must include an explicit UTC offset")
    live_claims = tuple(claim for claim in claims if claim.rollback_until > instant)
    boundaries = {
        instant,
        *(max(instant, claim.effective_from) for claim in live_claims),
    }
    peak = max(
        (sum(claim.active_bytes(boundary) for claim in live_claims) for boundary in boundaries),
        default=0,
    )
    staging = max(
        (
            sum(
                claim.encryption_chunking_bytes + claim.rollback_bytes
                for claim in live_claims
                if claim.effective_from <= boundary < claim.rollback_until
            )
            for boundary in boundaries
        ),
        default=0,
    )
    system = telemetry.projected_swap_expansion_bytes + telemetry.updater_claim_bytes + telemetry.apfs_churn_bytes
    required = system + peak + staging + telemetry.telemetry_error_bytes
    return ResourceEnvelope(
        observed_at=instant,
        observed_system_reserve_bytes=system,
        peak_concurrent_task_bytes=peak,
        custody_and_rollback_staging_bytes=staging,
        telemetry_error_bytes=telemetry.telemetry_error_bytes,
        required_free_bytes=required,
    )


def _nonnegative_env_bytes(name: str) -> int:
    raw = os.environ.get(name, "0")
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a nonnegative byte count") from exc
    if value < 0:
        raise ValueError(f"{name} must be a nonnegative byte count")
    return value


def _linux_memory() -> tuple[int, int, int] | None:
    try:
        fields: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            name, raw = line.split(":", 1)
            match = re.search(r"([0-9]+)", raw)
            if match:
                fields[name] = int(match.group(1)) * 1024
        return fields["MemTotal"], fields["MemAvailable"], fields.get("SwapTotal", 0) - fields.get("SwapFree", 0)
    except (OSError, KeyError, ValueError):
        return None


def _darwin_memory() -> tuple[int, int, int] | None:
    try:
        total = int(_capture_command(["/usr/sbin/sysctl", "-n", "hw.memsize"]).strip())
        page_size = int(_capture_command(["/usr/sbin/sysctl", "-n", "hw.pagesize"]).strip())
        vm = _capture_command(["/usr/bin/vm_stat"])
        pages = 0
        for label in ("Pages free", "Pages inactive", "Pages speculative", "Pages purgeable"):
            match = re.search(rf"^{re.escape(label)}:\s+([0-9]+)\.", vm, re.MULTILINE)
            if match:
                pages += int(match.group(1))
        swap = _capture_command(["/usr/sbin/sysctl", "-n", "vm.swapusage"])
        used = re.search(r"used = ([0-9.]+)([MG])", swap)
        swap_used = 0
        if used:
            scale = 1024**2 if used.group(2) == "M" else 1024**3
            swap_used = int(float(used.group(1)) * scale)
        return total, pages * page_size, swap_used
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def observe_resource_telemetry() -> ResourceTelemetry:
    memory = _darwin_memory() if os.uname().sysname == "Darwin" else _linux_memory()
    if memory is None:
        raise ResourceTelemetryUnavailable("live RAM/swap telemetry is unavailable")
    total, available, swap = memory
    return ResourceTelemetry(
        observed_at=datetime.now(UTC),
        ram_total_bytes=total,
        ram_available_bytes=available,
        swap_used_bytes=swap,
        updater_claim_bytes=_nonnegative_env_bytes("LIMEN_RESOURCE_UPDATER_CLAIM_BYTES"),
        apfs_churn_bytes=_nonnegative_env_bytes("LIMEN_RESOURCE_APFS_CHURN_BYTES"),
        telemetry_error_bytes=_nonnegative_env_bytes("LIMEN_RESOURCE_TELEMETRY_ERROR_BYTES"),
    )


def load_task_graph_claims(
    path: Path | None = None,
    *,
    expected_run_id: str | None = None,
) -> tuple[ResourceClaimV1, ...]:
    """Load the selected graph's bounded claims without inventing defaults."""

    selected = path
    if selected is None:
        raw = os.environ.get("LIMEN_RESOURCE_TASK_GRAPH")
        if not raw:
            raise ResourceGraphMissing("selected resource task graph is required")
        selected = Path(raw).expanduser()
    try:
        info = selected.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_size <= 0
            or info.st_size > MAX_TASK_GRAPH_BYTES
        ):
            raise ResourceGraphInvalid("resource task graph must be a bounded regular file")
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o600:
            raise ResourceGraphInvalid("resource task graph must be owner-controlled mode 0600")
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResourceGraphInvalid("resource task graph is unavailable or invalid") from exc
    if not isinstance(payload, dict) or payload.get("schema") != TASK_GRAPH_SCHEMA:
        raise ResourceGraphInvalid("resource task graph has an invalid shape")
    legacy = set(payload) == {"schema", "claims"}
    bound = set(payload) == {"schema", "run_id", "root_run_id", "claims", "digest"}
    if not (legacy or bound) or not isinstance(payload.get("claims"), list):
        raise ResourceGraphInvalid("resource task graph has an invalid shape")
    if expected_run_id is not None:
        if not bound or payload.get("run_id") != expected_run_id:
            raise ResourceGraphInvalid("resource task graph is not bound to the selected run")
    if bound:
        unsigned = {key: value for key, value in payload.items() if key != "digest"}
        if payload.get("digest") != _canonical_digest(unsigned):
            raise ResourceGraphInvalid("resource task graph digest does not match its contents")
        expected_digest = os.environ.get("LIMEN_RESOURCE_TASK_GRAPH_SHA256")
        if expected_digest is not None and payload.get("digest") != expected_digest:
            raise ResourceGraphInvalid("resource task graph digest does not match selected admission")
    try:
        claims = tuple(ResourceClaimV1.model_validate(value) for value in payload["claims"])
    except (TypeError, ValueError) as exc:
        raise ResourceGraphInvalid("resource task graph contains an invalid storage claim") from exc
    identifiers = [claim.claim_id for claim in claims]
    if len(identifiers) != len(set(identifiers)):
        raise ResourceGraphInvalid("resource task graph contains duplicate claim IDs")
    if bound:
        now = datetime.now(UTC)
        if any(not (claim.effective_from <= now <= claim.effective_until) for claim in claims):
            raise ResourceGraphInvalid("resource task graph contains an inactive storage claim")
    return claims


def materialize_run_task_graph(
    graph: dict[str, Any],
    *,
    run_id: str,
    destination: Path,
) -> dict[str, Any]:
    """Write one broker-observed run graph as a bounded mode-0600 admission file."""

    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    root_run_id = graph.get("root_run_id") if isinstance(graph, dict) else None
    if graph.get("schema_version") != "limen.conduct_graph.v1" or not isinstance(nodes, list):
        raise ResourceGraphInvalid("broker run graph has an invalid shape")
    selected = [node for node in nodes if isinstance(node, dict) and node.get("run_id") == run_id]
    if len(selected) != 1 or not isinstance(root_run_id, str):
        raise ResourceGraphInvalid("selected run is absent from the broker graph")
    claims: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for node in nodes:
        packet = node.get("packet") if isinstance(node, dict) else None
        raw_claims = packet.get("storage_envelope_claims", []) if isinstance(packet, dict) else []
        if not isinstance(raw_claims, list):
            raise ResourceGraphInvalid("broker packet storage claims have an invalid shape")
        for raw in raw_claims:
            try:
                claim = ResourceClaimV1.model_validate(raw)
            except (TypeError, ValueError) as exc:
                raise ResourceGraphInvalid("broker graph contains an invalid storage claim") from exc
            if claim.claim_id in identifiers:
                raise ResourceGraphInvalid("broker graph contains duplicate storage claim IDs")
            identifiers.add(claim.claim_id)
            claims.append(claim.model_dump(mode="json"))
    unsigned = {
        "schema": TASK_GRAPH_SCHEMA,
        "run_id": run_id,
        "root_run_id": root_run_id,
        "claims": claims,
    }
    payload = {**unsigned, "digest": _canonical_digest(unsigned)}
    encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    if not encoded or len(encoded) > MAX_TASK_GRAPH_BYTES:
        raise ResourceGraphInvalid("materialized resource task graph exceeds its size bound")
    destination = destination.expanduser()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        existing = destination.lstat()
    except FileNotFoundError:
        existing = None
    if existing is not None and (stat.S_ISLNK(existing.st_mode) or not stat.S_ISREG(existing.st_mode)):
        raise ResourceGraphInvalid("resource task graph destination must be a regular file")
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    return {
        "schema_version": "limen.resource_task_graph_receipt.v1",
        "path": str(destination.resolve()),
        "run_id": run_id,
        "root_run_id": root_run_id,
        "digest": payload["digest"],
        "claim_count": len(claims),
    }


def current_required_free_gib(
    claims: tuple[ResourceClaimV1, ...] | None = None,
) -> float:
    expected_run_id = os.environ.get("LIMEN_RESOURCE_TASK_GRAPH_RUN_ID") or None
    selected = load_task_graph_claims(expected_run_id=expected_run_id) if claims is None else claims
    return evaluate_resource_envelope(
        observe_resource_telemetry(),
        selected,
    ).required_free_gib


def main() -> int:
    try:
        print(f"{current_required_free_gib():.6f}")
    except (RuntimeError, ValueError) as exc:
        print(f"resource-envelope-unavailable:{type(exc).__name__}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
