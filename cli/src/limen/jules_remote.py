from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import Mapping


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


def task_jules_session_id(task: object) -> str:
    for entry in reversed(getattr(task, "dispatch_log", None) or []):
        session_id = str(getattr(entry, "session_id", "") or "")
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
