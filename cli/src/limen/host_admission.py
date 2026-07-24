"""Machine-wide admission for bounded local execution.

The lease store is deliberately outside any checkout: one host decision must cover
all Limen worktrees and all local agent families.  Admission never signals another
process.  It only denies new work, refreshes work that already owns a lease, and
reaps records whose PID/start identity or finite TTL proves they are stale.
"""

from __future__ import annotations

import ctypes
import fcntl
import hashlib
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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from limen.vigilia import params

STATE_SCHEMA = "limen.host_admission_state.v1"
SCOPED_STATE_SCHEMA = "limen.host_admission_scoped_state.v1"
DECISION_SCHEMA = "limen.host_admission_decision.v1"
READER_PROTOCOL = "limen.host_admission_reader.v2"
POLICY_REVISION = "2026-07-20.dual-state.v1"
LEASE_KINDS = frozenset({"execution", "heavy"})
SCOPED_EXECUTION_RE = re.compile(r"^execution:[0-9a-f]{64}$")
DENIED_EXIT = 3
USAGE_EXIT = 64

Clock = Callable[[], float]
PidAlive = Callable[[int], bool]
ProcessIdentity = Callable[[int], str | None]
ProcessCwd = Callable[[int], Path | None]
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
    """The lease store cannot be trusted without operator repair.

    The structured fields intentionally describe the protocol seam, never the
    contents of a hook prompt or transcript.  Callers can therefore give an
    operator a useful fail-closed diagnostic without dumping the state file.
    """

    def __init__(
        self,
        message: str,
        *,
        invalid_field: str = "unknown",
        writer_protocol: str = "unknown",
        state_path: Path | None = None,
        lease_pid: int | None = None,
        lease_process_identity: str | None = None,
    ) -> None:
        super().__init__(message)
        self.invalid_field = invalid_field
        self.reader_protocol = READER_PROTOCOL
        self.writer_protocol = writer_protocol
        self.state_path = state_path
        self.lease_pid = lease_pid
        self.lease_process_identity = lease_process_identity

    def diagnostic(self) -> dict[str, Any]:
        return {
            "error": str(self),
            "invalid_field": self.invalid_field,
            "reader_protocol": self.reader_protocol,
            "writer_protocol": self.writer_protocol,
            "state_file": self.state_path.name if self.state_path is not None else None,
            "lease_pid": self.lease_pid,
            "lease_process_identity": self.lease_process_identity,
            "safe_next_command": "python3 scripts/host-work-admission.py diagnose",
        }


class AdmissionDenied(RuntimeError):
    """A new lease was denied by a live owner or host pressure."""

    def __init__(self, decision: dict[str, Any]):
        self.decision = decision
        super().__init__(", ".join(decision.get("reasons") or ["host admission denied"]))


@dataclass(frozen=True)
class WorktreeScope:
    """Canonical identity for one Git checkout; paths are never persisted."""

    scope_hash: str
    common_dir: Path
    git_dir: Path
    top_level: Path
    linked: bool

    @property
    def lease_kind(self) -> str:
        return f"execution:{self.scope_hash}"


def _valid_lease_kind(kind: object) -> bool:
    return isinstance(kind, str) and (kind in LEASE_KINDS or bool(SCOPED_EXECUTION_RE.fullmatch(kind)))


def _is_execution_kind(kind: object) -> bool:
    return isinstance(kind, str) and (kind == "execution" or bool(SCOPED_EXECUTION_RE.fullmatch(kind)))


def _is_interrupted_migration(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Return True when two records with the same lease_id are a plausible crash-interrupted migration pair.

    A write crash between the two ``_write_file()`` calls in ``_write()`` can
    leave the same lease_id in both stores with only the ``kind`` field
    differing: the legacy store retains the old ``"execution"`` kind and the
    scoped store already holds the promoted ``"execution:<sha256>"`` kind.  All
    other fields are identical in that case, so ``_load()`` can converge
    automatically instead of permanently wedging the admission surface.
    """
    kinds = {str(a.get("kind", "")), str(b.get("kind", ""))}
    if "execution" not in kinds:
        return False
    if not any(SCOPED_EXECUTION_RE.fullmatch(k) for k in kinds):
        return False
    # Every field except 'kind' must be identical for a plausible migration.
    rest_a = {k: v for k, v in a.items() if k != "kind"}
    rest_b = {k: v for k, v in b.items() if k != "kind"}
    return rest_a == rest_b


def _is_interrupted_scoped_refresh(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Accept only one torn refresh of the same scoped lease identity."""

    kind_a = str(a.get("kind", ""))
    kind_b = str(b.get("kind", ""))
    if kind_a != kind_b or not SCOPED_EXECUTION_RE.fullmatch(kind_a):
        return False
    volatile = {"refreshed_at", "refreshed_epoch", "expires_at", "expires_epoch"}
    identity_a = {key: value for key, value in a.items() if key not in volatile}
    identity_b = {key: value for key, value in b.items() if key not in volatile}
    return identity_a == identity_b


def worktree_scope(cwd: str | os.PathLike[str]) -> WorktreeScope:
    """Resolve a stable linked-worktree scope, folding symlink aliases together."""

    try:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(Path(cwd).expanduser()),
                "rev-parse",
                "--path-format=absolute",
                "--git-common-dir",
                "--git-dir",
                "--show-toplevel",
            ],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("workspace-scope-unavailable") from exc
    rows = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode != 0 or len(rows) != 3:
        raise ValueError("workspace-scope-unavailable")
    try:
        common_dir, git_dir, top_level = (Path(row).resolve(strict=True) for row in rows)
    except OSError as exc:
        raise ValueError("workspace-scope-unavailable") from exc
    scope_hash = hashlib.sha256(f"{common_dir}\0{git_dir}".encode()).hexdigest()
    return WorktreeScope(
        scope_hash=scope_hash,
        common_dir=common_dir,
        git_dir=git_dir,
        top_level=top_level,
        linked=git_dir != common_dir,
    )


def process_cwd(pid: int) -> Path | None:
    """Resolve a live process cwd without treating failure as stale authority."""

    try:
        return Path(f"/proc/{pid}/cwd").resolve(strict=True)
    except OSError:
        pass
    try:
        result = subprocess.run(
            ["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"],
            capture_output=True,
            text=True,
            timeout=0.5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("n") and len(line) > 1:
            try:
                return Path(line[1:]).resolve(strict=True)
            except OSError:
                return None
    return None


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
        process_cwd_probe: ProcessCwd = process_cwd,
        descendant: DescendantCheck = is_descendant,
        pressure_probe: PressureProbe = collect_pressure,
        thresholds: dict[str, float] | None = None,
    ) -> None:
        self.root = root or default_state_root()
        self.clock = clock
        self.alive = alive
        self.identity = identity
        self.process_cwd_probe = process_cwd_probe
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
        """Legacy store consumed by readers that only understand global leases."""

        return self.root / "state.json"

    @property
    def scoped_state_path(self) -> Path:
        """Sibling store for worktree-scoped execution leases."""

        return self.root / "scoped-state.json"

    def _empty_state(self) -> dict[str, Any]:
        return {"schema": STATE_SCHEMA, "leases": [], "pressure": None}

    def _empty_scoped_state(self) -> dict[str, Any]:
        return {"schema": SCOPED_STATE_SCHEMA, "leases": []}

    @staticmethod
    def _lease_invalid_field(lease: object, *, scoped_only: bool) -> str | None:
        if not isinstance(lease, dict):
            return "record"
        required = (
            "lease_id",
            "kind",
            "owner",
            "surface",
            "pid",
            "process_identity",
            "expires_epoch",
        )
        for field in required:
            value = lease.get(field)
            if value is None or value == "":
                return field
        kind = lease.get("kind")
        if scoped_only:
            if not isinstance(kind, str) or SCOPED_EXECUTION_RE.fullmatch(kind) is None:
                return "kind"
        elif not _valid_lease_kind(kind):
            # The legacy reader accepts scoped records only long enough for the
            # current writer to migrate them under the shared lock.
            return "kind"
        try:
            if int(lease["pid"]) <= 0:
                return "pid"
            if float(lease["expires_epoch"]) <= 0:
                return "expires_epoch"
        except (TypeError, ValueError):
            return "pid_or_expires_epoch"
        return None

    def _read_state_file(
        self,
        path: Path,
        *,
        schema: str,
        scoped_only: bool,
        missing: dict[str, Any],
    ) -> dict[str, Any]:
        if not path.exists():
            return missing
        try:
            if stat.S_ISLNK(path.lstat().st_mode):
                raise AdmissionStateError(
                    "host admission state must not be a symlink",
                    invalid_field="path.symlink",
                    state_path=path,
                )
        except OSError as exc:
            raise AdmissionStateError(
                "host admission state is unavailable",
                invalid_field="path",
                state_path=path,
            ) from exc
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise AdmissionStateError(
                "host admission state is unavailable; preserved for inspection",
                invalid_field="file.read",
                state_path=path,
            ) from exc
        except json.JSONDecodeError as exc:
            raise AdmissionStateError(
                "host admission state is corrupt; preserved for inspection",
                invalid_field=f"json:{exc.lineno}:{exc.colno}",
                state_path=path,
            ) from exc
        writer_protocol = str(raw.get("schema") or "missing") if isinstance(raw, dict) else type(raw).__name__
        if not isinstance(raw, dict) or raw.get("schema") != schema:
            raise AdmissionStateError(
                "host admission state schema is invalid; preserved for inspection",
                invalid_field="schema",
                writer_protocol=writer_protocol,
                state_path=path,
            )
        leases = raw.get("leases")
        if not isinstance(leases, list):
            raise AdmissionStateError(
                "host admission lease record is invalid; preserved for inspection",
                invalid_field="leases",
                writer_protocol=writer_protocol,
                state_path=path,
            )
        for index, lease in enumerate(leases):
            invalid = self._lease_invalid_field(lease, scoped_only=scoped_only)
            if invalid is not None:
                lease_map = lease if isinstance(lease, dict) else {}
                pid = lease_map.get("pid")
                raise AdmissionStateError(
                    "host admission lease record is invalid; preserved for inspection",
                    invalid_field=f"leases[{index}].{invalid}",
                    writer_protocol=writer_protocol,
                    state_path=path,
                    lease_pid=int(pid) if isinstance(pid, int) and not isinstance(pid, bool) else None,
                    lease_process_identity=(
                        str(lease_map.get("process_identity"))
                        if lease_map.get("process_identity") not in {None, ""}
                        else None
                    ),
                )
        if not scoped_only and raw.get("pressure") is not None and not isinstance(raw.get("pressure"), dict):
            raise AdmissionStateError(
                "host admission pressure record is invalid; preserved for inspection",
                invalid_field="pressure",
                writer_protocol=writer_protocol,
                state_path=path,
            )
        return raw

    def _load(self) -> dict[str, Any]:
        legacy = self._read_state_file(
            self.state_path,
            schema=STATE_SCHEMA,
            scoped_only=False,
            missing=self._empty_state(),
        )
        scoped = self._read_state_file(
            self.scoped_state_path,
            schema=SCOPED_STATE_SCHEMA,
            scoped_only=True,
            missing=self._empty_scoped_state(),
        )
        union: list[dict[str, Any]] = []
        by_id: dict[str, dict[str, Any]] = {}
        for lease in [*legacy["leases"], *scoped["leases"]]:
            lease_id = str(lease["lease_id"])
            prior = by_id.get(lease_id)
            if prior is not None:
                if prior != lease:
                    if _is_interrupted_migration(prior, lease):
                        # Write crash: the legacy store kept the old "execution" kind
                        # while the scoped store already received the promoted kind.
                        # Prefer the scoped record; prior is shared by both by_id and union.
                        prior["kind"] = next(
                            k
                            for k in (str(prior.get("kind", "")), str(lease.get("kind", "")))
                            if SCOPED_EXECUTION_RE.fullmatch(k)
                        )
                    elif _is_interrupted_scoped_refresh(prior, lease):
                        # A refresh can tear between the two atomic store writes. Keep
                        # the newest copy only when the durable lease identity matches.
                        if float(lease["refreshed_epoch"]) > float(prior["refreshed_epoch"]):
                            prior.clear()
                            prior.update(lease)
                    else:
                        raise AdmissionStateError(
                            "host admission lease identity is duplicated with different records; preserved for inspection",
                            invalid_field=f"leases[{lease_id}].duplicate",
                            writer_protocol=f"{STATE_SCHEMA}+{SCOPED_STATE_SCHEMA}",
                            state_path=self.scoped_state_path,
                        )
                continue
            copied = dict(lease)
            by_id[lease_id] = copied
            union.append(copied)
        return {"schema": STATE_SCHEMA, "leases": union, "pressure": legacy.get("pressure")}

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
                and _valid_lease_kind(lease.get("kind"))
                and lease.get("owner")
                and lease.get("surface")
                and int(pid) > 0
                and float(expires_epoch) > 0
                and lease.get("process_identity")
            )
        except (TypeError, ValueError):
            return False

    def _write_file(self, path: Path, state: dict[str, Any]) -> None:
        payload = (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
        tmp = self.root / f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(tmp, flags, 0o600)
        try:
            with os.fdopen(fd, "wb", closefd=False) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        finally:
            os.close(fd)

    def _write(self, state: dict[str, Any]) -> None:
        legacy = {
            "schema": STATE_SCHEMA,
            "leases": [
                ({**dict(lease), "kind": "execution"} if SCOPED_EXECUTION_RE.fullmatch(lease["kind"]) else dict(lease))
                for lease in state["leases"]
                if lease["kind"] in LEASE_KINDS or SCOPED_EXECUTION_RE.fullmatch(lease["kind"])
            ],
            "pressure": state.get("pressure"),
        }
        scoped = {
            "schema": SCOPED_STATE_SCHEMA,
            "leases": [dict(lease) for lease in state["leases"] if SCOPED_EXECUTION_RE.fullmatch(lease["kind"])],
        }
        # Both stores share the same advisory lock. Publish the scoped file first,
        # then project each scoped lease into legacy as a global execution lease.
        # Older readers remain conservatively serialized during the rolling update,
        # while current readers pair the projection with its exact scoped record.
        self._write_file(self.scoped_state_path, scoped)
        self._write_file(self.state_path, legacy)
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
        if not _valid_lease_kind(kind):
            raise ValueError("kind must be execution, heavy, or execution:<sha256>")
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
            if SCOPED_EXECUTION_RE.fullmatch(kind):
                legacy = next((lease for lease in state["leases"] if lease["kind"] == "execution"), None)
                if legacy is not None:
                    same_owner = (
                        legacy["owner"] == owner
                        and int(legacy["pid"]) == pid
                        and legacy["process_identity"] == identity
                    )
                    if same_owner:
                        legacy["kind"] = kind
                    else:
                        legacy_pid = int(legacy["pid"])
                        legacy_cwd = self.process_cwd_probe(legacy_pid)
                        legacy_identity = self.identity(legacy_pid)
                        try:
                            legacy_scope = worktree_scope(legacy_cwd) if legacy_cwd is not None else None
                        except ValueError:
                            legacy_scope = None
                        if legacy_identity != legacy["process_identity"] or legacy_scope is None:
                            self._write(state)
                            return self._decision(
                                "acquire",
                                allowed=False,
                                reasons=["legacy-execution-scope-unproven"],
                                state=state,
                                lease=legacy,
                                reaped=reaped,
                            )
                        legacy["kind"] = legacy_scope.lease_kind
            if kind == "execution":
                current = next(
                    (lease for lease in state["leases"] if _is_execution_kind(lease["kind"])),
                    None,
                )
            else:
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
                held_reason = (
                    "workspace-writer-lease-held" if SCOPED_EXECUTION_RE.fullmatch(kind) else f"{kind}-lease-held"
                )
                return self._decision(
                    "acquire",
                    allowed=False,
                    reasons=[held_reason],
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

        if not _valid_lease_kind(kind):
            raise ValueError("kind must be execution, heavy, or execution:<sha256>")
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

    def diagnose(self) -> dict[str, Any]:
        """Inspect protocol compatibility without mutating or cleaning either store."""

        try:
            with self._locked():
                state = self._load()
        except AdmissionStateError as exc:
            return {
                "schema": "limen.host_admission_diagnostic.v1",
                "valid": False,
                **exc.diagnostic(),
            }
        return {
            "schema": "limen.host_admission_diagnostic.v1",
            "valid": True,
            "reader_protocol": READER_PROTOCOL,
            "legacy_schema": STATE_SCHEMA,
            "scoped_schema": SCOPED_STATE_SCHEMA,
            "legacy_state_file": self.state_path.name,
            "scoped_state_file": self.scoped_state_path.name,
            "legacy_lease_count": sum(lease["kind"] in LEASE_KINDS for lease in state["leases"]),
            "scoped_lease_count": sum(bool(SCOPED_EXECUTION_RE.fullmatch(lease["kind"])) for lease in state["leases"]),
            "safe_next_command": "python3 scripts/host-work-admission.py status --no-probe",
        }


def host_admission_capabilities() -> dict[str, Any]:
    """Versioned protocol response consumed by immutable host wrappers."""

    return {
        "schema": "limen.codex_host_admission_capabilities.v1",
        "reader_protocol": READER_PROTOCOL,
        "policy_revision": POLICY_REVISION,
        "state_schemas": {
            "legacy": STATE_SCHEMA,
            "scoped": SCOPED_STATE_SCHEMA,
        },
        "lease_kinds": ["execution", "heavy", "execution:<sha256>"],
        "stable_action_denial": True,
        "single_rejection_channel": True,
        "migration": "scoped-leases-move-out-of-legacy-under-shared-lock",
    }


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
