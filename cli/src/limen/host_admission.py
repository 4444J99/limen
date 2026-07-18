"""Machine-wide admission for bounded local execution.

The lease store is deliberately outside any checkout: one host decision must cover
all Limen worktrees and all local agent families.  Admission never signals another
process.  It only denies new work, refreshes work that already owns a lease, and
reaps records whose PID/start identity or finite TTL proves they are stale.
"""

from __future__ import annotations

import ctypes
import fcntl
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from limen.vigilia import params

STATE_SCHEMA = "limen.host_admission_state.v1"
DECISION_SCHEMA = "limen.host_admission_decision.v1"
LEASE_KINDS = frozenset({"execution", "heavy"})
DENIED_EXIT = 3
USAGE_EXIT = 64

Clock = Callable[[], float]
PidAlive = Callable[[int], bool]
ProcessIdentity = Callable[[int], str | None]
DescendantCheck = Callable[[int, int], bool]
PressureProbe = Callable[[], dict[str, Any]]

_PROC_PIDTBSDINFO = 3
_PROC_BSDINFO_MAXCOMLEN = 16


class _ProcBsdInfo(ctypes.Structure):
    """Darwin ``struct proc_bsdinfo`` from ``<sys/proc_info.h>``."""

    _fields_ = [
        ("pbi_flags", ctypes.c_uint32),
        ("pbi_status", ctypes.c_uint32),
        ("pbi_xstatus", ctypes.c_uint32),
        ("pbi_pid", ctypes.c_uint32),
        ("pbi_ppid", ctypes.c_uint32),
        ("pbi_uid", ctypes.c_uint32),
        ("pbi_gid", ctypes.c_uint32),
        ("pbi_ruid", ctypes.c_uint32),
        ("pbi_rgid", ctypes.c_uint32),
        ("pbi_svuid", ctypes.c_uint32),
        ("pbi_svgid", ctypes.c_uint32),
        ("rfu_1", ctypes.c_uint32),
        ("pbi_comm", ctypes.c_char * _PROC_BSDINFO_MAXCOMLEN),
        ("pbi_name", ctypes.c_char * (2 * _PROC_BSDINFO_MAXCOMLEN)),
        ("pbi_nfiles", ctypes.c_uint32),
        ("pbi_pgid", ctypes.c_uint32),
        ("pbi_pjobc", ctypes.c_uint32),
        ("e_tdev", ctypes.c_uint32),
        ("e_tpgid", ctypes.c_uint32),
        ("pbi_nice", ctypes.c_int32),
        ("pbi_start_tvsec", ctypes.c_uint64),
        ("pbi_start_tvusec", ctypes.c_uint64),
    ]


class AdmissionStateError(RuntimeError):
    """The lease store cannot be trusted without operator repair."""


class AdmissionDenied(RuntimeError):
    """A new lease was denied by a live owner or host pressure."""

    def __init__(self, decision: dict[str, Any]):
        self.decision = decision
        super().__init__(", ".join(decision.get("reasons") or ["host admission denied"]))


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _bounded_label(value: str, field: str) -> str:
    value = value.strip()
    if not value or len(value) > 160 or any(ord(char) < 32 for char in value):
        raise ValueError(f"{field} must be 1-160 printable characters")
    return value


def default_state_root() -> Path:
    configured = str(params.get("LIMEN_HOST_ADMISSION_ROOT", "auto") or "auto")
    if configured != "auto":
        expanded = os.path.expandvars(os.path.expanduser(configured.replace("$UID", str(os.getuid()))))
        return Path(expanded)
    return Path(tempfile.gettempdir()) / f"limen-host-admission-{os.getuid()}"


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _darwin_process_identity(
    pid: int,
    *,
    proc_pidinfo: Callable[..., int] | None = None,
) -> str | None:
    """Read one exact process start timeval through Darwin's bounded libproc ABI."""

    if pid <= 0 or (sys.platform != "darwin" and proc_pidinfo is None):
        return None
    try:
        if proc_pidinfo is None:
            library = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
            proc_pidinfo = library.proc_pidinfo
            proc_pidinfo.argtypes = [
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint64,
                ctypes.c_void_p,
                ctypes.c_int,
            ]
            proc_pidinfo.restype = ctypes.c_int
        info = _ProcBsdInfo()
        info_size = ctypes.sizeof(info)
        returned = proc_pidinfo(
            pid,
            _PROC_PIDTBSDINFO,
            0,
            ctypes.byref(info),
            info_size,
        )
    except (AttributeError, OSError, TypeError, ValueError, ctypes.ArgumentError):
        return None
    start_seconds = int(info.pbi_start_tvsec)
    start_microseconds = int(info.pbi_start_tvusec)
    if (
        returned != info_size
        or int(info.pbi_pid) != pid
        or start_seconds <= 0
        or not 0 <= start_microseconds < 1_000_000
    ):
        return None
    return f"darwin-proc-start:{start_seconds}:{start_microseconds}"


def process_identity(pid: int) -> str | None:
    """Return a PID-reuse-resistant process start identity when the host exposes one."""

    if pid <= 0:
        return None
    proc_stat = Path(f"/proc/{pid}/stat")
    try:
        raw = proc_stat.read_text(encoding="utf-8")
        # Field 22 is process start time. The command field may contain spaces and
        # parentheses, so split only after its final closing parenthesis.
        tail = raw.rsplit(")", 1)[1].split()
        if len(tail) >= 20:
            return f"proc-start:{tail[19]}"
    except (OSError, IndexError):
        pass
    if identity := _darwin_process_identity(pid):
        return identity
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "lstart="],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    started = " ".join(result.stdout.split())
    return f"ps-start:{started}" if result.returncode == 0 and started else None


def _parent_table() -> dict[int, int]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,ppid="],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    if result.returncode != 0:
        return {}
    table: dict[int, int] = {}
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            table[int(parts[0])] = int(parts[1])
    return table


def is_descendant(pid: int, ancestor_pid: int) -> bool:
    """True when ``pid`` is a live child of the process holding a parent lease."""

    parents = _parent_table()
    seen: set[int] = set()
    current = pid
    for _ in range(64):
        if current == ancestor_pid:
            return True
        if current <= 1 or current in seen:
            return False
        seen.add(current)
        parent = parents.get(current)
        if parent is None:
            return False
        current = parent
    return False


_SIZE_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*([KMGT])", re.IGNORECASE)
_SIZE_FACTORS = {
    "K": 1024,
    "M": 1024**2,
    "G": 1024**3,
    "T": 1024**4,
}


def _parse_size(raw: str) -> int | None:
    match = _SIZE_RE.search(raw)
    if not match:
        return None
    return int(float(match.group(1)) * _SIZE_FACTORS[match.group(2).upper()])


def parse_iostat_mib_samples(raw: str) -> list[float]:
    """Return interval totals from macOS ``iostat -d`` output.

    Each disk contributes a ``KB/t xfrs MB/s`` triplet.  Header and cumulative
    baseline rows are discarded by the caller; this parser only returns numeric
    row totals in their emitted order.
    """

    samples: list[float] = []
    for line in raw.splitlines():
        tokens = line.split()
        if len(tokens) < 3:
            continue
        try:
            numbers = [float(token) for token in tokens]
        except ValueError:
            continue
        if len(numbers) % 3:
            continue
        samples.append(round(sum(numbers[index] for index in range(2, len(numbers), 3)), 3))
    return samples


def _backblaze_observation(errors: list[str]) -> tuple[float | None, int | None]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pcpu=,rss=,comm="],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        errors.append("backblaze-process-sensor")
        return None, None
    if result.returncode != 0:
        errors.append("backblaze-process-sensor")
        return None, None
    cpu = 0.0
    rss_kib = 0
    for line in result.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) != 3:
            continue
        command = parts[2].lower()
        if "bztransmit" not in command and "backblaze" not in command:
            continue
        try:
            cpu += float(parts[0])
            rss_kib += int(parts[1])
        except ValueError:
            continue
    return round(cpu, 3), rss_kib * 1024


def _swap_observation(errors: list[str]) -> tuple[int | None, int | None]:
    if sys.platform == "darwin":
        try:
            observation = subprocess.run(
                ["sysctl", "-n", "vm.swapusage", "hw.memsize"],
                capture_output=True,
                text=True,
                timeout=1,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            errors.append("swap-sensor")
            return None, None
        lines = observation.stdout.splitlines()
        swap_line = lines[0] if lines else ""
        memory_line = lines[-1].strip() if len(lines) >= 2 else ""
        used_match = re.search(r"\bused\s*=\s*([^ ]+)", swap_line)
        used = _parse_size(used_match.group(1)) if used_match else None
        total = int(memory_line) if memory_line.isdigit() else None
        if observation.returncode != 0 or used is None or total is None:
            errors.append("swap-sensor")
            return None, None
        return used, total

    try:
        values: dict[str, int] = {}
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            name, raw = line.split(":", 1)
            match = re.search(r"([0-9]+)", raw)
            if match:
                values[name] = int(match.group(1)) * 1024
        total = values["MemTotal"]
        used = values["SwapTotal"] - values["SwapFree"]
        return max(0, used), total
    except (OSError, KeyError, ValueError):
        errors.append("swap-sensor")
        return None, None


def _disk_observation(errors: list[str]) -> list[float] | None:
    try:
        result = subprocess.run(
            ["iostat", "-d", "-w", "1", "-c", "3"],
            capture_output=True,
            text=True,
            timeout=min(
                4,
                max(
                    2,
                    int(params.get("LIMEN_HOST_ADMISSION_PROBE_TIMEOUT", 4, cast=int)),
                ),
            ),
            check=False,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        errors.append("disk-sensor")
        return None
    samples = parse_iostat_mib_samples(result.stdout)
    if result.returncode != 0 or len(samples) < 3:
        errors.append("disk-sensor")
        return None
    return samples[-2:]


def collect_pressure() -> dict[str, Any]:
    """Collect one bounded host-pressure observation without mutating peer state."""

    errors: list[str] = []

    def vitals_observation() -> str:
        try:
            from limen.vigilia.vitals import beat_gate

            vitals = beat_gate(shed=False)
            return str(vitals.get("action") or "unknown")
        except Exception:  # pragma: no cover - defensive boundary around host sensor
            errors.append("vitals-sensor")
            return "unknown"

    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="limen-admission-probe") as pool:
        backblaze_future = pool.submit(_backblaze_observation, errors)
        swap_future = pool.submit(_swap_observation, errors)
        disk_future = pool.submit(_disk_observation, errors)
        vitals_future = pool.submit(vitals_observation)
        backblaze_cpu, backblaze_rss = backblaze_future.result()
        swap_used, memory_bytes = swap_future.result()
        disk_samples = disk_future.result()
        vitals_action = vitals_future.result()
    return {
        "observed_epoch": time.time(),
        "backblaze_cpu_percent": backblaze_cpu,
        "backblaze_rss_bytes": backblaze_rss,
        "swap_used_bytes": swap_used,
        "memory_bytes": memory_bytes,
        "disk_mib_per_second_samples": disk_samples,
        "vitals_action": vitals_action,
        "sensor_errors": sorted(set(errors)),
    }


def _thresholds() -> dict[str, float]:
    return {
        "backblaze_cpu_percent": params.get(
            "LIMEN_HOST_ADMISSION_BACKBLAZE_CPU_PERCENT",
            50.0,
            cast=float,
        ),
        "backblaze_rss_bytes": float(params.get("LIMEN_HOST_ADMISSION_BACKBLAZE_RSS_BYTES", 1024**3, cast=int)),
        "swap_fraction": float(params.get("LIMEN_HOST_ADMISSION_SWAP_FRACTION", 0.25, cast=float)),
        "swap_growth_bytes_per_minute": float(
            params.get("LIMEN_HOST_ADMISSION_SWAP_GROWTH_BYTES_PER_MINUTE", 512 * 1024**2, cast=int)
        ),
        "disk_mib_per_second": params.get(
            "LIMEN_HOST_ADMISSION_DISK_MIB_PER_SECOND",
            100.0,
            cast=float,
        ),
    }


class AdmissionController:
    """Atomic lease and pressure decisions over one per-user host store."""

    def __init__(
        self,
        root: Path | None = None,
        *,
        clock: Clock = time.time,
        alive: PidAlive = pid_is_alive,
        identity: ProcessIdentity = process_identity,
        descendant: DescendantCheck = is_descendant,
        pressure_probe: PressureProbe = collect_pressure,
        thresholds: dict[str, float] | None = None,
    ) -> None:
        self.root = root or default_state_root()
        self.clock = clock
        self.alive = alive
        self.identity = identity
        self.descendant = descendant
        self.pressure_probe = pressure_probe
        self.thresholds = thresholds or _thresholds()

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            root_stat = self.root.lstat()
        except OSError as exc:
            raise AdmissionStateError(f"host admission root unavailable: {exc}") from exc
        if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
            raise AdmissionStateError("host admission root must be a real directory")
        if root_stat.st_uid != os.getuid():
            raise AdmissionStateError("host admission root has the wrong owner")
        if stat.S_IMODE(root_stat.st_mode) & 0o077:
            raise AdmissionStateError("host admission root permissions must be 0700")

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self._ensure_root()
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            fd = os.open(self.root / ".lock", flags, 0o600)
        except OSError as exc:
            raise AdmissionStateError(f"host admission lock unavailable: {exc}") from exc
        try:
            os.fchmod(fd, 0o600)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @property
    def state_path(self) -> Path:
        return self.root / "state.json"

    def _empty_state(self) -> dict[str, Any]:
        return {"schema": STATE_SCHEMA, "leases": [], "pressure": None}

    def _load(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return self._empty_state()
        try:
            if stat.S_ISLNK(self.state_path.lstat().st_mode):
                raise AdmissionStateError("host admission state must not be a symlink")
        except OSError as exc:
            raise AdmissionStateError("host admission state is unavailable") from exc
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise AdmissionStateError("host admission state is corrupt; preserved for inspection") from exc
        if not isinstance(raw, dict) or raw.get("schema") != STATE_SCHEMA:
            raise AdmissionStateError("host admission state schema is invalid; preserved for inspection")
        leases = raw.get("leases")
        if not isinstance(leases, list) or any(not self._valid_lease(lease) for lease in leases):
            raise AdmissionStateError("host admission lease record is invalid; preserved for inspection")
        if raw.get("pressure") is not None and not isinstance(raw.get("pressure"), dict):
            raise AdmissionStateError("host admission pressure record is invalid; preserved for inspection")
        return raw

    @staticmethod
    def _valid_lease(lease: object) -> bool:
        if not isinstance(lease, dict):
            return False
        pid = lease.get("pid")
        expires_epoch = lease.get("expires_epoch")
        if pid is None or expires_epoch is None:
            return False
        try:
            return bool(
                lease.get("lease_id")
                and lease.get("kind") in LEASE_KINDS
                and lease.get("owner")
                and lease.get("surface")
                and int(pid) > 0
                and float(expires_epoch) > 0
                and lease.get("process_identity")
            )
        except (TypeError, ValueError):
            return False

    def _write(self, state: dict[str, Any]) -> None:
        payload = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
        tmp = self.root / f".state.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.state_path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        finally:
            os.close(fd)
        directory = os.open(self.root, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def _cleanup(self, state: dict[str, Any], now: float) -> list[dict[str, str]]:
        kept: list[dict[str, Any]] = []
        reaped: list[dict[str, str]] = []
        for lease in state["leases"]:
            reason = ""
            pid = int(lease["pid"])
            if now >= float(lease["expires_epoch"]):
                reason = "stale-ttl"
            elif not self.alive(pid):
                reason = "dead-pid"
            else:
                current_identity = self.identity(pid)
                if current_identity is not None and current_identity != lease["process_identity"]:
                    reason = "pid-reused"
            if reason:
                reaped.append({"lease_id": str(lease["lease_id"]), "reason": reason})
            else:
                kept.append(lease)
        state["leases"] = kept
        return reaped

    def _complete_pressure(
        self,
        observed: dict[str, Any] | None,
        previous: dict[str, Any] | None,
        now: float,
    ) -> dict[str, Any] | None:
        if observed is None:
            return previous
        pressure = dict(observed)
        observed_epoch = float(pressure.get("observed_epoch") or now)
        pressure["observed_epoch"] = observed_epoch
        pressure["observed_at"] = _iso(observed_epoch)
        used = pressure.get("swap_used_bytes")
        memory = pressure.get("memory_bytes")
        pressure["swap_fraction"] = (
            float(used) / float(memory) if used is not None and memory is not None and memory != 0 else None
        )
        growth = None
        if previous and used is not None and previous.get("swap_used_bytes") is not None:
            prior_epoch = float(previous.get("observed_epoch") or 0)
            elapsed = observed_epoch - prior_epoch
            if 1 <= elapsed <= 600:
                delta = max(0.0, float(used) - float(previous["swap_used_bytes"]))
                growth = round(delta * 60 / elapsed, 3)
        pressure["swap_growth_bytes_per_minute"] = growth
        pressure["sensor_errors"] = sorted(set(pressure.get("sensor_errors") or []))
        return pressure

    def _pressure_reasons(self, pressure: dict[str, Any] | None) -> list[str]:
        if pressure is None:
            return ["pressure-unavailable"]
        reasons: list[str] = []
        threshold = self.thresholds
        cpu = pressure.get("backblaze_cpu_percent")
        rss = pressure.get("backblaze_rss_bytes")
        swap_fraction = pressure.get("swap_fraction")
        swap_growth = pressure.get("swap_growth_bytes_per_minute")
        disk = pressure.get("disk_mib_per_second_samples")
        if cpu is not None and float(cpu) > threshold["backblaze_cpu_percent"]:
            reasons.append("backblaze-cpu")
        if rss is not None and float(rss) > threshold["backblaze_rss_bytes"]:
            reasons.append("backblaze-rss")
        if swap_fraction is not None and float(swap_fraction) > threshold["swap_fraction"]:
            reasons.append("swap-fraction")
        if swap_growth is not None and float(swap_growth) > threshold["swap_growth_bytes_per_minute"]:
            reasons.append("swap-growth")
        if (
            isinstance(disk, list)
            and len(disk) >= 2
            and all(float(sample) > threshold["disk_mib_per_second"] for sample in disk[-2:])
        ):
            reasons.append("disk-throughput")
        if pressure.get("vitals_action") == "shed":
            reasons.append("vitals-shed")
        # These probes are stock, required host inputs on macOS. Other platforms
        # expose their unknowns but do not fabricate a denial from missing iostat.
        if sys.platform == "darwin" and pressure.get("sensor_errors"):
            reasons.append("pressure-sensor-unavailable")
        return reasons

    def _decision(
        self,
        operation: str,
        *,
        allowed: bool,
        reasons: list[str],
        state: dict[str, Any],
        lease: dict[str, Any] | None = None,
        inherited: bool = False,
        reaped: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema": DECISION_SCHEMA,
            "operation": operation,
            "allowed": allowed,
            "reasons": reasons,
            "lease": lease,
            "inherited": inherited,
            "leases": state["leases"],
            "pressure": state.get("pressure"),
            "reaped": reaped or [],
        }

    def acquire(
        self,
        kind: str,
        *,
        owner: str,
        surface: str,
        pid: int,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        if kind not in LEASE_KINDS:
            raise ValueError(f"kind must be one of {sorted(LEASE_KINDS)}")
        owner = _bounded_label(owner, "owner")
        surface = _bounded_label(surface, "surface")
        if pid <= 0:
            raise ValueError("pid must be positive")
        identity = self.identity(pid)
        if not self.alive(pid) or identity is None:
            raise ValueError("lease owner PID/start identity is unavailable")
        ttl = (
            int(params.get("LIMEN_HOST_ADMISSION_LEASE_SECONDS", 900, cast=int)) if ttl_seconds is None else ttl_seconds
        )
        if ttl < 30 or ttl > 86400:
            raise ValueError("ttl_seconds must be between 30 and 86400")
        observed = self.pressure_probe() if kind == "heavy" else None
        now = self.clock()
        with self._locked():
            state = self._load()
            reaped = self._cleanup(state, now)
            state["pressure"] = self._complete_pressure(observed, state.get("pressure"), now)
            current = next((lease for lease in state["leases"] if lease["kind"] == kind), None)
            if current is not None:
                same_owner = (
                    current["owner"] == owner and int(current["pid"]) == pid and current["process_identity"] == identity
                )
                if same_owner:
                    current["refreshed_epoch"] = now
                    current["refreshed_at"] = _iso(now)
                    current["expires_epoch"] = now + ttl
                    current["expires_at"] = _iso(now + ttl)
                    self._write(state)
                    return self._decision(
                        "acquire",
                        allowed=True,
                        reasons=[],
                        state=state,
                        lease=current,
                        reaped=reaped,
                    )
                if kind == "heavy" and self.descendant(pid, int(current["pid"])):
                    self._write(state)
                    return self._decision(
                        "acquire",
                        allowed=True,
                        reasons=[],
                        state=state,
                        lease=current,
                        inherited=True,
                        reaped=reaped,
                    )
                self._write(state)
                return self._decision(
                    "acquire",
                    allowed=False,
                    reasons=[f"{kind}-lease-held"],
                    state=state,
                    lease=current,
                    reaped=reaped,
                )
            pressure_reasons = self._pressure_reasons(state.get("pressure")) if kind == "heavy" else []
            if pressure_reasons:
                self._write(state)
                return self._decision(
                    "acquire",
                    allowed=False,
                    reasons=pressure_reasons,
                    state=state,
                    reaped=reaped,
                )
            lease = {
                "lease_id": uuid.uuid4().hex,
                "kind": kind,
                "owner": owner,
                "surface": surface,
                "pid": pid,
                "process_identity": identity,
                "acquired_epoch": now,
                "acquired_at": _iso(now),
                "refreshed_epoch": now,
                "refreshed_at": _iso(now),
                "expires_epoch": now + ttl,
                "expires_at": _iso(now + ttl),
            }
            state["leases"].append(lease)
            self._write(state)
            return self._decision(
                "acquire",
                allowed=True,
                reasons=[],
                state=state,
                lease=lease,
                reaped=reaped,
            )

    def refresh(
        self,
        *,
        lease_id: str,
        owner: str,
        pid: int,
        ttl_seconds: int | None = None,
    ) -> dict[str, Any]:
        owner = _bounded_label(owner, "owner")
        ttl = (
            int(params.get("LIMEN_HOST_ADMISSION_LEASE_SECONDS", 900, cast=int)) if ttl_seconds is None else ttl_seconds
        )
        if ttl < 30 or ttl > 86400:
            raise ValueError("ttl_seconds must be between 30 and 86400")
        now = self.clock()
        identity = self.identity(pid)
        with self._locked():
            state = self._load()
            reaped = self._cleanup(state, now)
            lease = next((item for item in state["leases"] if item["lease_id"] == lease_id), None)
            if (
                lease is None
                or lease["owner"] != owner
                or int(lease["pid"]) != pid
                or identity is None
                or lease["process_identity"] != identity
            ):
                self._write(state)
                return self._decision(
                    "refresh",
                    allowed=False,
                    reasons=["lease-owner-mismatch"],
                    state=state,
                    reaped=reaped,
                )
            lease["refreshed_epoch"] = now
            lease["refreshed_at"] = _iso(now)
            lease["expires_epoch"] = now + ttl
            lease["expires_at"] = _iso(now + ttl)
            self._write(state)
            return self._decision(
                "refresh",
                allowed=True,
                reasons=[],
                state=state,
                lease=lease,
                reaped=reaped,
            )

    def release(self, *, lease_id: str, owner: str, pid: int) -> dict[str, Any]:
        owner = _bounded_label(owner, "owner")
        now = self.clock()
        identity = self.identity(pid)
        with self._locked():
            state = self._load()
            reaped = self._cleanup(state, now)
            lease = next((item for item in state["leases"] if item["lease_id"] == lease_id), None)
            exact = bool(
                lease
                and lease["owner"] == owner
                and int(lease["pid"]) == pid
                and identity is not None
                and lease["process_identity"] == identity
            )
            if lease is None:
                self._write(state)
                return self._decision(
                    "release",
                    allowed=True,
                    reasons=[],
                    state=state,
                    reaped=reaped,
                )
            if not exact:
                self._write(state)
                return self._decision(
                    "release",
                    allowed=False,
                    reasons=["lease-owner-mismatch"],
                    state=state,
                    lease=lease,
                    reaped=reaped,
                )
            state["leases"] = [item for item in state["leases"] if item["lease_id"] != lease_id]
            self._write(state)
            return self._decision(
                "release",
                allowed=True,
                reasons=[],
                state=state,
                lease=lease,
                reaped=reaped,
            )

    def release_owned(self, kind: str, *, owner: str, pid: int) -> dict[str, Any]:
        """Atomically release this owner's lease without a prior status scan."""

        if kind not in LEASE_KINDS:
            raise ValueError(f"kind must be one of {sorted(LEASE_KINDS)}")
        owner = _bounded_label(owner, "owner")
        if pid <= 0:
            raise ValueError("pid must be positive")
        now = self.clock()
        identity = self.identity(pid)
        with self._locked():
            state = self._load()
            lease = next(
                (
                    item
                    for item in state["leases"]
                    if item["kind"] == kind and item["owner"] == owner and int(item["pid"]) == pid
                ),
                None,
            )
            exact = bool(lease and identity is not None and lease["process_identity"] == identity)
            if lease is not None and exact:
                state["leases"] = [item for item in state["leases"] if item["lease_id"] != lease["lease_id"]]
            reaped = self._cleanup(state, now)
            self._write(state)
            if lease is not None and not exact:
                return self._decision(
                    "release",
                    allowed=False,
                    reasons=["lease-owner-mismatch"],
                    state=state,
                    lease=lease,
                    reaped=reaped,
                )
            return self._decision(
                "release",
                allowed=True,
                reasons=[],
                state=state,
                lease=lease,
                reaped=reaped,
            )

    def status(self, *, probe: bool = True) -> dict[str, Any]:
        observed = self.pressure_probe() if probe else None
        now = self.clock()
        with self._locked():
            state = self._load()
            reaped = self._cleanup(state, now)
            state["pressure"] = self._complete_pressure(observed, state.get("pressure"), now)
            reasons = self._pressure_reasons(state.get("pressure"))
            self._write(state)
            return self._decision(
                "status",
                allowed=not reasons,
                reasons=reasons,
                state=state,
                reaped=reaped,
            )


@contextmanager
def hold_lease(
    kind: str,
    *,
    owner: str,
    surface: str,
    pid: int | None = None,
    controller: AdmissionController | None = None,
    ttl_seconds: int | None = None,
) -> Iterator[dict[str, Any]]:
    """Hold and refresh one lease for the duration of a bounded entrypoint."""

    controller = controller or AdmissionController()
    pid = pid or os.getpid()
    decision = controller.acquire(
        kind,
        owner=owner,
        surface=surface,
        pid=pid,
        ttl_seconds=ttl_seconds,
    )
    if not decision["allowed"]:
        raise AdmissionDenied(decision)
    if decision.get("inherited"):
        yield decision
        return
    lease = decision["lease"]
    stop = threading.Event()
    ttl = int(params.get("LIMEN_HOST_ADMISSION_LEASE_SECONDS", 900, cast=int)) if ttl_seconds is None else ttl_seconds
    interval = max(10, min(60, ttl // 3))

    def refresher() -> None:
        while not stop.wait(interval):
            refreshed = controller.refresh(
                lease_id=lease["lease_id"],
                owner=owner,
                pid=pid,
                ttl_seconds=ttl,
            )
            if not refreshed["allowed"]:
                return

    thread = threading.Thread(target=refresher, name=f"host-admission-{kind}", daemon=True)
    thread.start()
    try:
        yield decision
    finally:
        stop.set()
        thread.join(timeout=2)
        controller.release(lease_id=lease["lease_id"], owner=owner, pid=pid)
