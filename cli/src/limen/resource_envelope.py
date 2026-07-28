"""Telemetry-backed storage envelope for a selected task graph."""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from limen.prima_materia import ResourceClaimV1

TASK_GRAPH_SCHEMA = "limen.resource_task_graph.v1"
MAX_TASK_GRAPH_BYTES = 4 * 1024 * 1024
_NATIVE_POPEN = subprocess.Popen


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
        raise RuntimeError("live RAM/swap telemetry is unavailable")
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


def load_task_graph_claims(path: Path | None = None) -> tuple[ResourceClaimV1, ...]:
    """Load the selected graph's bounded claims without inventing defaults."""

    selected = path
    if selected is None:
        raw = os.environ.get("LIMEN_RESOURCE_TASK_GRAPH")
        if not raw:
            raise ValueError("selected resource task graph is required")
        selected = Path(raw).expanduser()
    try:
        info = selected.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_size <= 0
            or info.st_size > MAX_TASK_GRAPH_BYTES
        ):
            raise ValueError("resource task graph must be a bounded regular file")
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("resource task graph is unavailable or invalid") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"schema", "claims"}
        or payload.get("schema") != TASK_GRAPH_SCHEMA
        or not isinstance(payload.get("claims"), list)
    ):
        raise ValueError("resource task graph has an invalid shape")
    claims = tuple(ResourceClaimV1.model_validate(value) for value in payload["claims"])
    identifiers = [claim.claim_id for claim in claims]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("resource task graph contains duplicate claim IDs")
    return claims


def current_required_free_gib(
    claims: tuple[ResourceClaimV1, ...] | None = None,
) -> float:
    selected = load_task_graph_claims() if claims is None else claims
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
