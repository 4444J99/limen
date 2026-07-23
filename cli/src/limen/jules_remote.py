from __future__ import annotations

import json
import os
import re
import selectors
import signal
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field, replace

from limen.models import dispatch_session_id

JULES_RECOVERY_STATES = frozenset(
    {
        "failed",
        "awaiting_user_feedback",
        "awaiting_plan_approval",
    }
)
_LAST_ACTIVE_RE = re.compile(
    r"^(?:(?:\d+[dhms])+\s+ago|\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago|just now)$",
    re.IGNORECASE,
)
# The CLI's table header — used to anchor fixed-width column offsets. Split-on-whitespace
# parsing cannot represent an EMPTY Status cell: the last populated column ("1 day ago", or
# the repo) bled into the status slot and classified as "unknown", which held stale claims
# forever (the 29-claim forever-HOLD defect, 2026-07-14).
_HEADER_RE = re.compile(r"^\s*ID\s{2,}.*\bStatus\b")
_SESSION_ID_RE = re.compile(r"\d{12,64}")
_NOT_FOUND_ENVELOPE_RE = re.compile(
    rb"\AError: api error: status 404, content:\s*(\{.*\})\s*\Z",
    re.DOTALL,
)
JULES_SESSION_PROBE_TIMEOUT = 10.0
JULES_SESSION_PROBE_TOTAL_TIMEOUT = 45.0
JULES_SESSION_PROBE_OUTPUT_LIMIT = 64 * 1024


def _idle_at_least_a_day(last_active: str) -> bool:
    """True when the Last-active cell shows >=1 day of inactivity ('1 day ago', '2 weeks ago',
    '1d4h ago'); sub-day forms ('5h36m5s ago', 'just now') and blanks are False."""
    return bool(re.search(r"\b\d+\s*(?:d\b|d\d|day|week|month|year)", last_active.strip().lower()))


@dataclass(frozen=True)
class JulesRemoteSession:
    session_id: str
    status: str
    raw: str = ""
    # >=1 day since the CLI's Last-active column moved — only derivable when the listing
    # carries a header (fixed-width offsets); the legacy fallback leaves it False (hold-safe).
    idle: bool = False


@dataclass(frozen=True)
class JulesSessionAbsenceProbe:
    """A bounded observation for one exact session ID.

    Only ``confirmed_absent`` is release authority. Every other outcome is deliberately
    non-authoritative and therefore keeps the claim held.
    """

    session_id: str
    outcome: str

    @property
    def confirmed_absent(self) -> bool:
        return self.outcome == "confirmed_absent"


@dataclass(frozen=True)
class _BoundedCommandResult:
    returncode: int | None
    output: bytes = b""
    failure: str = ""


SessionProbeRunner = Callable[[Sequence[str], float, int], _BoundedCommandResult]
SessionAbsenceProbe = Callable[..., JulesSessionAbsenceProbe]


@dataclass(frozen=True)
class JulesRemoteSnapshot:
    """One remote-list observation.

    ``available`` means the provider answered; it does *not* mean a list response is exhaustive.
    The Jules CLI currently exposes neither pagination nor an explicit completeness marker, so a
    successful list miss is only ``unknown``.  Absence is authoritative only when an upstream
    probe explicitly marks the whole catalog exhaustive or confirms the individual session absent.
    """

    available: bool
    sessions: Mapping[str, JulesRemoteSession]
    error: str = ""
    exhaustive: bool = False
    confirmed_absent: frozenset[str] = field(default_factory=frozenset)
    absence_probe_outcomes: Mapping[str, str] = field(default_factory=dict)

    def status(self, session_id: str) -> str | None:
        session = self.sessions.get(session_id)
        return session.status if session is not None else None

    def proves_absent(self, session_id: str) -> bool:
        return session_id in self.confirmed_absent or (self.exhaustive and session_id not in self.sessions)


def classify_jules_remote_status(status: str) -> str:
    """Normalize only the CLI's terminal Status column, never task-description text."""
    low = status.lower()
    if "failed" in low:
        return "failed"
    if "awaiting plan" in low:
        return "awaiting_plan_approval"
    if "awaiting user" in low or "awaiting feedback" in low:
        return "awaiting_user_feedback"
    if "completed" in low:
        return "completed"
    if "planning" in low:
        return "planning"
    if "in progress" in low or "running" in low:
        return "in_progress"
    return "unknown"


def parse_jules_remote_sessions(output: str) -> dict[str, JulesRemoteSession]:
    lines = output.splitlines()
    # Anchor the trailing column WIDTHS on the header when present: the CLI pads fixed-width
    # columns, so a header-derived slice reads an EMPTY Status cell as empty instead of
    # promoting the previous column ("1 day ago", or the repo) into it. Widths are measured
    # from the RIGHT edge — the Description cell truncates by DISPLAY width (its "…" is one
    # code point), so left-anchored offsets skew, while the tail columns (repo / Last active /
    # Status) are ASCII and stay aligned from the end of the padded row.
    status_width: int | None = None
    last_active_width: int | None = None
    for raw in lines:
        if _HEADER_RE.match(raw):
            status_start = raw.index("Status")
            status_width = len(raw) - status_start
            match = re.search(r"\bLast active\b", raw)
            if match:
                last_active_width = status_start - match.start()
            break
    sessions: dict[str, JulesRemoteSession] = {}
    for raw in lines:
        columns = re.split(r"\s{2,}", raw.strip())
        if not columns or not columns[0].isdigit():
            continue
        session_id = columns[0]
        idle = False
        if status_width is not None and len(raw) >= status_width:
            status_text = raw[-status_width:].strip()
            if last_active_width is not None and len(raw) >= status_width + last_active_width:
                idle = _idle_at_least_a_day(raw[-(status_width + last_active_width) : -status_width])
        else:
            # legacy headerless output: last column unless it reads as a Last-active cell
            status_text = ""
            if len(columns) >= 2 and not _LAST_ACTIVE_RE.fullmatch(columns[-1]):
                status_text = columns[-1]
        sessions[session_id] = JulesRemoteSession(
            session_id=session_id,
            status=classify_jules_remote_status(status_text),
            raw=raw,
            idle=idle,
        )
    return sessions


def probe_jules_remote_sessions(
    *,
    binary: str | None = None,
    timeout: int = 90,
) -> JulesRemoteSnapshot:
    executable = binary or os.environ.get("LIMEN_JULES_BIN", "jules")
    try:
        result = subprocess.run(
            [executable, "remote", "list", "--session"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return JulesRemoteSnapshot(available=False, sessions={}, error=str(exc)[:160])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or f"exit {result.returncode}").strip()
        return JulesRemoteSnapshot(available=False, sessions={}, error=detail[:160])
    # `jules remote list --session` has no pagination/all-pages flag and emits no
    # next-page or completeness metadata.  Never infer completeness from a row count: the
    # provider may change its page size at any time.
    return JulesRemoteSnapshot(
        available=True,
        sessions=parse_jules_remote_sessions(result.stdout or ""),
        exhaustive=False,
    )


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        with suppress(OSError):
            process.terminate()
    try:
        process.wait(timeout=0.5)
        return
    except subprocess.TimeoutExpired:
        pass
    with suppress(OSError):
        os.killpg(process.pid, signal.SIGKILL)
    with suppress(OSError):
        process.kill()
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=1.0)


def _run_bounded_command(
    command: Sequence[str],
    timeout: float,
    output_limit: int,
) -> _BoundedCommandResult:
    """Run one read-only probe with a wall-clock and combined-output hard bound."""

    if timeout <= 0 or output_limit <= 0:
        return _BoundedCommandResult(returncode=None, failure="invalid_probe_limits")
    try:
        process = subprocess.Popen(
            list(command),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError:
        return _BoundedCommandResult(returncode=None, failure="cli_unavailable")
    if process.stdout is None:  # pragma: no cover - invariant for stdout=PIPE
        _terminate_process_group(process)
        return _BoundedCommandResult(returncode=None, failure="pipe_unavailable")

    chunks: list[bytes] = []
    size = 0
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    failure = ""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "timeout"
                break
            events = selector.select(timeout=min(remaining, 0.1))
            if not events:
                if process.poll() is not None:
                    break
                continue
            chunk = os.read(process.stdout.fileno(), min(65_536, output_limit + 1))
            if not chunk:
                break
            size += len(chunk)
            if size > output_limit:
                failure = "output_truncated"
                break
            chunks.append(chunk)
    finally:
        selector.close()

    if failure:
        _terminate_process_group(process)
        return _BoundedCommandResult(returncode=process.returncode, failure=failure)
    try:
        returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        _terminate_process_group(process)
        return _BoundedCommandResult(returncode=process.returncode, failure="timeout")
    return _BoundedCommandResult(returncode=returncode, output=b"".join(chunks))


def _is_exact_not_found_response(output: bytes) -> bool:
    """Accept only the Jules API's complete structured 404/NOT_FOUND envelope."""

    match = _NOT_FOUND_ENVELOPE_RE.fullmatch(output)
    if match is None:
        return False
    try:
        payload = json.loads(match.group(1).decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, dict) or set(payload) != {"error"}:
        return False
    error = payload.get("error")
    return (
        isinstance(error, dict)
        and type(error.get("code")) is int
        and error.get("code") == 404
        and error.get("status") == "NOT_FOUND"
    )


def probe_jules_remote_session_absence(
    session_id: str,
    *,
    binary: str | None = None,
    timeout: float = JULES_SESSION_PROBE_TIMEOUT,
    output_limit: int = JULES_SESSION_PROBE_OUTPUT_LIMIT,
    runner: SessionProbeRunner | None = None,
) -> JulesSessionAbsenceProbe:
    """Probe one catalog miss without applying or materializing its patch.

    The Jules CLI currently exits zero for API errors, so exit status is not treated as evidence.
    The command is authoritative only when its entire bounded response is the structured
    404/NOT_FOUND envelope from an exact ``--session`` pull. Successful pulls, other API errors,
    malformed output, transport failures, timeouts, and output overflow all remain unknown.
    """

    if _SESSION_ID_RE.fullmatch(session_id) is None:
        return JulesSessionAbsenceProbe(session_id=session_id, outcome="invalid_session_id")
    executable = binary or os.environ.get("LIMEN_JULES_BIN", "jules")
    command = (executable, "remote", "pull", "--session", session_id)
    result = (runner or _run_bounded_command)(command, timeout, output_limit)
    if result.failure:
        return JulesSessionAbsenceProbe(session_id=session_id, outcome=result.failure)
    if _is_exact_not_found_response(result.output):
        return JulesSessionAbsenceProbe(session_id=session_id, outcome="confirmed_absent")
    return JulesSessionAbsenceProbe(session_id=session_id, outcome="response_unconfirmed")


def probe_jules_remote_session_absences(
    snapshot: JulesRemoteSnapshot,
    session_ids: Iterable[str],
    *,
    binary: str | None = None,
    per_probe_timeout: float = JULES_SESSION_PROBE_TIMEOUT,
    total_timeout: float = JULES_SESSION_PROBE_TOTAL_TIMEOUT,
    output_limit: int = JULES_SESSION_PROBE_OUTPUT_LIMIT,
    probe: SessionAbsenceProbe | None = None,
) -> JulesRemoteSnapshot:
    """Attach authoritative absence evidence for missing sessions within one total budget."""

    if not snapshot.available or snapshot.exhaustive:
        return snapshot
    candidates = tuple(
        dict.fromkeys(
            str(session_id)
            for session_id in session_ids
            if str(session_id) not in snapshot.sessions and str(session_id) not in snapshot.confirmed_absent
        )
    )
    if not candidates:
        return snapshot

    confirmed_absent = set(snapshot.confirmed_absent)
    outcomes = dict(snapshot.absence_probe_outcomes)
    deadline = time.monotonic() + max(0.0, total_timeout)
    probe_one = probe or probe_jules_remote_session_absence
    for index, session_id in enumerate(candidates):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            for unprobed in candidates[index:]:
                outcomes.setdefault(unprobed, "budget_exhausted")
            break
        result = probe_one(
            session_id,
            binary=binary,
            timeout=min(per_probe_timeout, remaining),
            output_limit=output_limit,
        )
        outcomes[session_id] = result.outcome
        if result.confirmed_absent:
            confirmed_absent.add(session_id)
    return replace(
        snapshot,
        confirmed_absent=frozenset(confirmed_absent),
        absence_probe_outcomes=outcomes,
    )


def task_jules_session_id(task: object) -> str:
    for entry in reversed(getattr(task, "dispatch_log", None) or []):
        session_id = dispatch_session_id(entry)
        if session_id.isdigit() and len(session_id) >= 12:
            return session_id
    return ""


def coerce_jules_snapshot(value: JulesRemoteSnapshot | Mapping[str, str]) -> JulesRemoteSnapshot:
    """Compatibility adapter for callers/tests that historically returned ``{id: status}``."""

    if isinstance(value, JulesRemoteSnapshot):
        return value
    return JulesRemoteSnapshot(
        available=True,
        sessions={
            str(session_id): JulesRemoteSession(str(session_id), str(status)) for session_id, status in value.items()
        },
        # A legacy mapping preserves known session statuses but carries no completeness evidence.
        # Treat missing keys as unknown rather than preserving the old unsafe absent inference.
        exhaustive=False,
    )


def classify_jules_claim(snapshot: JulesRemoteSnapshot, session_id: str) -> tuple[str, str]:
    """Return ``(action, remote_status)`` for a stale Jules claim.

    Actions are deliberately routing decisions, not mutations:
    ``hold`` keeps the claim, ``harvest`` and ``recover`` hand it to their existing organs, and
    only ``release`` proves the remote session absent.
    """

    if not snapshot.available:
        return "hold", "cli_unavailable"
    if not session_id:
        return "hold", "session_id_unavailable"
    session = snapshot.sessions.get(session_id)
    if session is None:
        if snapshot.proves_absent(session_id):
            return "release", "absent"
        return "hold", "absence_unconfirmed"
    if session.status == "completed":
        return "harvest", session.status
    if session.status in JULES_RECOVERY_STATES:
        return "recover", session.status
    if session.status == "unknown" and session.idle:
        # The list shows this session with no recognizable Status and >=1 day idle. A finished
        # session renders "Completed" (→ harvest above), so idle-with-no-status is dead work —
        # route it to the recovery funnel instead of holding the claim forever.
        return "recover", "idle_no_status"
    return "hold", session.status
