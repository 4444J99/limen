from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from typing import Mapping


JULES_RECOVERY_STATES = frozenset(
    {
        "failed",
        "awaiting_user_feedback",
        "awaiting_plan_approval",
    }
)
_LAST_ACTIVE_RE = re.compile(r"^(?:(?:\d+[dhms])+\s+ago|just now)$", re.IGNORECASE)


@dataclass(frozen=True)
class JulesRemoteSession:
    session_id: str
    status: str
    raw: str = ""


@dataclass(frozen=True)
class JulesRemoteSnapshot:
    """One remote-list observation.

    ``available`` distinguishes a successful empty catalog from a missing/broken CLI.  That
    distinction is the release safety boundary: only a successful catalog may prove that a
    recorded session is absent.
    """

    available: bool
    sessions: Mapping[str, JulesRemoteSession]
    error: str = ""

    def status(self, session_id: str) -> str | None:
        session = self.sessions.get(session_id)
        return session.status if session is not None else None


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
    sessions: dict[str, JulesRemoteSession] = {}
    for raw in output.splitlines():
        columns = re.split(r"\s{2,}", raw.strip())
        if not columns or not columns[0].isdigit():
            continue
        session_id = columns[0]
        status_text = ""
        if len(columns) >= 2 and not _LAST_ACTIVE_RE.fullmatch(columns[-1]):
            status_text = columns[-1]
        sessions[session_id] = JulesRemoteSession(
            session_id=session_id,
            status=classify_jules_remote_status(status_text),
            raw=raw,
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
    return JulesRemoteSnapshot(available=True, sessions=parse_jules_remote_sessions(result.stdout or ""))


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
    status = snapshot.status(session_id)
    if status is None:
        return "release", "absent"
    if status == "completed":
        return "harvest", status
    if status in JULES_RECOVERY_STATES:
        return "recover", status
    return "hold", status
