#!/usr/bin/env python3
"""_notify — onset-deduped macOS notification helper (the VIGILIA escalation path).

IF-HOST-PRESSURE form 4: before 2026-07-16 the only pressure signal was an advisory
line in a beat log — the operator was the sensor of last resort. This helper gives
sensors a LOUD path (osascript display notification, the conducting-report.py
precedent; works from launchd) with onset dedup so a condition notifies once when it
begins, not once per beat.

Persistent-condition state lives in ``logs/vigilia/relief-state.json`` under the
caller's root: a key per active condition. ``notify_once`` records + fires on first
sight of a key; ``clear_condition`` removes it when the condition ends so a future
onset re-fires. Discrete source events use ``notify_event`` and a separate,
cross-process-safe daily ledger.
Kill-switch: LIMEN_NOTIFY=0 keeps the dedup bookkeeping but never calls osascript
(also how the hermetic tests stay silent). Persistent-condition bookkeeping remains
fail-open; a discrete event whose reservation cannot be proven is withheld fail-closed.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

# The liveness guard lives next to this file ON DISK. Resolving it by path rather than by
# `import _root` is the whole point — see _load_root().
_ROOT_MODULE_PATH = Path(__file__).resolve().parent / "_root.py"
_ROOT_MODULE = None
EVENT_RETENTION_DAYS = 31
EVENT_RETENTION_RECORDS = 2048
EVENT_LOCK_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class NotificationResult:
    """Structured outcome for a discrete source event."""

    status: Literal["emitted", "duplicate", "withheld", "delivery_failed"]
    event_key: str
    local_day: str
    identifier: str
    reserved: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class DeliveryReceipt:
    """Channel-aware receipt returned by the machine-global Domus broker."""

    status: Literal["delivered", "deduped", "recorded", "withheld", "cleared", "failed"]
    stable_id: str
    event_id: str
    channels: dict[str, str]
    reason: str | None = None


NOTIFICATION_REGISTRY = (
    Path(__file__).resolve().parents[1] / "institutio" / "governance" / "notification-events.limen.json"
)


def _state_path(root: Path | str) -> Path:
    return Path(root) / "logs" / "vigilia" / "relief-state.json"


def _event_state_path(root: Path | str) -> Path:
    return Path(root) / "logs" / "vigilia" / "event-notifications.json"


def _event_lock_path(root: Path | str) -> Path:
    return Path(root) / "logs" / "vigilia" / "event-notifications.lock"


def _load(root: Path | str) -> dict:
    try:
        state = json.loads(_state_path(root).read_text())
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _save(root: Path | str, state: dict) -> None:
    try:
        path = _state_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=1, sort_keys=True))
    except Exception:
        pass


def _atomic_json_replace(path: Path, payload: dict[str, Any]) -> None:
    """Replace a JSON ledger atomically in its own directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, raw_temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(raw_temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=1, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
        try:
            directory = os.open(path.parent, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


class _EventLock:
    """Finite, advisory lock for the machine-local event ledger."""

    def __init__(self, root: Path | str, timeout: float) -> None:
        self.path = _event_lock_path(root)
        self.timeout = max(0.0, float(timeout))
        self.stream = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = self.path.open("a+")
        try:
            os.chmod(self.path, 0o600)
            deadline = time.monotonic() + self.timeout
            while True:
                try:
                    fcntl.flock(self.stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return self
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise TimeoutError(f"notification event lock timed out after {self.timeout:.3f}s") from None
                    time.sleep(min(0.02, max(0.001, deadline - time.monotonic())))
        except BaseException:
            self.stream.close()
            self.stream = None
            raise

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        if self.stream is None:
            return
        try:
            fcntl.flock(self.stream.fileno(), fcntl.LOCK_UN)
        finally:
            self.stream.close()
            self.stream = None


def _normalize_payload(value: Any) -> Any:
    """Normalize JSON-shaped payloads without erasing meaningful state changes."""
    if isinstance(value, str):
        return " ".join(value.split())
    if isinstance(value, dict):
        return {str(key): _normalize_payload(item) for key, item in sorted(value.items(), key=lambda row: str(row[0]))}
    if isinstance(value, (list, tuple)):
        return [_normalize_payload(item) for item in value]
    if isinstance(value, set):
        normalized = [_normalize_payload(item) for item in value]
        return sorted(normalized, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _payload_digest(payload: Any) -> str:
    canonical = json.dumps(
        _normalize_payload(payload),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _event_identity(
    source: str,
    event: str,
    local_day: str,
    stable_id: str | None,
    payload: Any,
) -> tuple[str, str]:
    identifier = f"id:{stable_id.strip()}" if stable_id and stable_id.strip() else f"sha256:{_payload_digest(payload)}"
    canonical = json.dumps(
        {
            "event": " ".join(str(event).split()),
            "identifier": identifier,
            "local_day": local_day,
            "source": " ".join(str(source).split()),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest(), identifier


def _load_event_state(root: Path | str) -> dict[str, Any]:
    path = _event_state_path(root)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {"schema_version": "limen.notification_events.v1", "events": {}}
    except OSError as exc:
        raise OSError(f"notification event ledger is unreadable: {exc}") from exc
    try:
        value = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("notification event ledger is corrupt") from exc
    if (
        not isinstance(value, dict)
        or value.get("schema_version") != "limen.notification_events.v1"
        or not isinstance(value.get("events"), dict)
    ):
        raise ValueError("notification event ledger has an invalid schema")
    return value


def _prune_event_state(state: dict[str, Any], today: str) -> None:
    events = state.setdefault("events", {})
    if not isinstance(events, dict):
        state["events"] = events = {}
    try:
        cutoff = date.fromisoformat(today) - timedelta(days=EVENT_RETENTION_DAYS)
    except ValueError:
        cutoff = date.min
    retained = {
        key: value
        for key, value in events.items()
        if isinstance(value, dict)
        and isinstance(value.get("local_day"), str)
        and _safe_event_day(value["local_day"]) >= cutoff
    }
    newest = sorted(
        retained.items(),
        key=lambda row: str(row[1].get("reserved_at") or ""),
        reverse=True,
    )[:EVENT_RETENTION_RECORDS]
    state["events"] = dict(newest)


def _safe_event_day(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.min


def _update_event_status(
    root: Path | str,
    event_key: str,
    status: str,
    *,
    lock_timeout: float,
) -> None:
    """Best-effort status annotation; the reservation is already the dedupe fence."""
    try:
        with _EventLock(root, lock_timeout):
            state = _load_event_state(root)
            record = state.get("events", {}).get(event_key)
            if not isinstance(record, dict):
                return
            record["status"] = status
            record["updated_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            _atomic_json_replace(_event_state_path(root), state)
    except (OSError, TimeoutError, TypeError, ValueError):
        pass


def _enabled(enabled: bool | None) -> bool:
    if enabled is not None:
        return enabled
    return os.environ.get("LIMEN_NOTIFY", "1") not in ("0", "false", "False")


def _load_root():
    """Load the sibling ``_root`` module BY ABSOLUTE PATH, never via ambient ``sys.path``.

    ``import _root`` resolves only when the calling script happened to run
    ``sys.path.insert(0, scripts/)`` first. Six of the seven ``_notify`` callers do;
    ``check-effectors.py`` does not. A guard whose availability depends on every caller
    remembering a convention is exactly the shape of guard a single omission defeats —
    the founding lesson of this entire lineage (``_root.py``'s own docstring: "a guard
    that a single write can satisfy is not a guard"). The module sits next to this file
    on disk, so load it from there and the whole failure mode is gone.
    """
    global _ROOT_MODULE
    if _ROOT_MODULE is None:
        spec = importlib.util.spec_from_file_location("_limen_root_for_notify", _ROOT_MODULE_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {_ROOT_MODULE_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ROOT_MODULE = module
    return _ROOT_MODULE


def _root_may_speak(root: Path | str) -> bool:
    """Only the live organism reaches the phone.

    2026-08-05: four "LIMEN · morning — ABSENT" notifications in one afternoon, all real
    osascript pops, none from the live root. cli/tests calls diurnal's ``emit()`` directly
    (bypassing main()'s has_body guard) against a pytest tmp root whose relief-state is
    deleted with the root — so onset dedup can never dedupe, and every test run fires. The
    per-caller convention (each test remembers LIMEN_NOTIFY=0) is exactly the kind of guard
    a single omission defeats; this gates the EFFECTOR instead, at the one chokepoint every
    notifier shares. Bookkeeping still writes for any root — only the osascript call is
    withheld.

    FAIL CLOSED, reversing this function's first shipped form. It fell back to ``return
    True`` so "the live beat's escalations must not die of an import error" — but with the
    predicate now loaded by absolute path, an import error means the tree is missing its
    own ``_root.py``, and a tree that damaged is not the organism. The asymmetry decides
    it: a withheld notification is recoverable and observable in the beat log, while a
    false one is neither — it is already on his phone. The unexpected case is announced on
    stderr rather than swallowed, so silence is never silent about itself.
    """
    try:
        return bool(_load_root().has_body(Path(root))[0])
    except Exception as exc:
        print(f"_notify: withholding notification — liveness predicate unavailable ({exc})", file=sys.stderr)
        return False


def _deliver(message: str, title: str) -> bool:
    """Delegate legacy delivery to the one machine-global Domus transport."""
    try:
        broker = os.environ.get("DOMUS_NOTIFY_BIN", str(Path.home() / ".local" / "bin" / "domus-notify"))
        delivered = subprocess.run(
            [broker, "--title", title, "--message", message],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return delivered.returncode == 0
    except Exception:
        return False


def notify_ntfy(
    root: Path | str,
    message: str,
    title: str = "LIMEN",
    tags: str = "limen",
) -> bool:
    """Delegate the legacy ntfy-only route to the Domus broker."""
    topic = os.environ.get("LIMEN_NTFY_TOPIC")
    if not topic or not _enabled(None) or not _root_may_speak(root):
        return False
    try:
        event_id = hashlib.sha256(f"{title}\0{message}\0{tags}".encode()).hexdigest()
        receipt = emit_event_v1(
            root,
            stable_id="limen.legacy.ntfy",
            transition="milestone",
            subject_key=tags,
            event_id=f"legacy-ntfy-{event_id[:20]}",
            facts={"title": title, "message": message},
            evidence_ref="legacy-notify-ntfy",
            producer="scripts/_notify.py",
        )
        return receipt.channels.get("ntfy") == "delivered"
    except Exception:
        return False


def emit_event_v1(
    root: Path | str,
    *,
    stable_id: str,
    transition: str,
    subject_key: str,
    event_id: str,
    facts: dict[str, str | int | float | bool | None],
    evidence_ref: str,
    producer: str,
    observed_at: str | None = None,
    enabled: bool | None = None,
    level: str | None = None,
) -> DeliveryReceipt:
    """Validate at the broker boundary and return its channel-aware receipt."""
    if not _root_may_speak(root):
        return DeliveryReceipt("withheld", stable_id, event_id, {}, "root is not the live organism")
    event = {
        "event_id": event_id,
        "transition": transition,
        "subject_key": subject_key,
        "observed_at": observed_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "stable_id": stable_id,
        "facts": facts,
        "evidence_ref": evidence_ref,
        "producer": producer,
        "owner": "limen",
    }
    broker = os.environ.get("DOMUS_NOTIFY_BIN", str(Path.home() / ".local" / "bin" / "domus-notify"))
    command = [broker, "emit", "--event-json", "-"]
    if level:
        command.extend(["--level", level])
    env = dict(os.environ)
    env["DOMUS_NOTIFY_REGISTRY"] = str(NOTIFICATION_REGISTRY)
    if os.environ.get("LIMEN_NTFY_TOPIC") and not env.get("DOMUS_NOTIFY_NTFY_URL"):
        base = os.environ.get("LIMEN_NTFY_URL", "https://ntfy.sh").rstrip("/")
        env["DOMUS_NOTIFY_NTFY_URL"] = f"{base}/{os.environ['LIMEN_NTFY_TOPIC']}"
    if not _enabled(enabled):
        env["DOMUS_NOTIFY"] = "0"
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env=env,
        )
        if completed.returncode != 0:
            return DeliveryReceipt(
                "failed", stable_id, event_id, {}, f"Domus broker exited {completed.returncode}"
            )
        payload = json.loads(completed.stdout or "{}")
        if not isinstance(payload, dict):
            return DeliveryReceipt("failed", stable_id, event_id, {}, "invalid Domus broker response")
        status = payload.get("status")
        if status not in {"delivered", "deduped", "recorded", "withheld", "cleared", "failed"}:
            status = "failed"
        return DeliveryReceipt(status, stable_id, event_id, dict(payload.get("channels") or {}), payload.get("reason"))
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return DeliveryReceipt("failed", stable_id, event_id, {}, f"Domus broker unavailable ({exc})")


def notify(
    root: Path | str,
    message: str,
    title: str = "LIMEN",
    enabled: bool | None = None,
) -> bool:
    """Deliver a non-deduplicated notification through the shared liveness gate."""
    if not _enabled(enabled) or not _root_may_speak(root):
        return False
    return _deliver(message, title)


def notify_event(
    root: Path | str,
    *,
    source: str,
    event: str,
    message: str,
    title: str = "LIMEN",
    stable_id: str | None = None,
    payload: Any = None,
    local_day: str | None = None,
    enabled: bool | None = None,
    lock_timeout: float = EVENT_LOCK_TIMEOUT_SECONDS,
    force: bool = False,
) -> NotificationResult:
    """Emit one card per canonical source event and local calendar day.

    The event reservation is persisted before invoking ``osascript``. A replay therefore
    remains suppressed even if delivery fails or the first process dies immediately after
    the effector call. Callers with a durable source identifier (run, comment, or exact
    head) pass it as ``stable_id``; only identifier-less sources fall back to a normalized
    payload digest.
    """
    day = local_day or datetime.now().astimezone().date().isoformat()
    event_payload = payload if payload is not None else {"message": message, "title": title}
    event_key, identifier = _event_identity(source, event, day, stable_id, event_payload)
    if not _root_may_speak(root):
        return NotificationResult(
            "withheld",
            event_key,
            day,
            identifier,
            reason="root is not the live organism",
        )

    local_now = datetime.now().astimezone()
    now = local_now.isoformat(timespec="seconds")
    today = local_now.date().isoformat()
    try:
        with _EventLock(root, lock_timeout):
            state = _load_event_state(root)
            _prune_event_state(state, today)
            events = state["events"]
            previous = events.get(event_key)
            if isinstance(previous, dict) and not force:
                return NotificationResult(
                    "duplicate",
                    event_key,
                    day,
                    identifier,
                    reason=f"already reserved ({previous.get('status') or 'reserved'})",
                )
            events[event_key] = {
                "event": " ".join(str(event).split()),
                "identifier": identifier,
                "local_day": day,
                "reserved_at": now,
                "source": " ".join(str(source).split()),
                "status": "reserved",
            }
            _atomic_json_replace(_event_state_path(root), state)
    except TimeoutError as exc:
        return NotificationResult("withheld", event_key, day, identifier, reason=str(exc))
    except (OSError, TypeError, ValueError) as exc:
        return NotificationResult(
            "withheld",
            event_key,
            day,
            identifier,
            reason=f"event reservation failed ({exc})",
        )

    if not _enabled(enabled):
        _update_event_status(root, event_key, "withheld", lock_timeout=lock_timeout)
        return NotificationResult(
            "withheld",
            event_key,
            day,
            identifier,
            reserved=True,
            reason="notifications disabled",
        )
    if _deliver(message, title):
        _update_event_status(root, event_key, "emitted", lock_timeout=lock_timeout)
        return NotificationResult("emitted", event_key, day, identifier, reserved=True)
    _update_event_status(root, event_key, "delivery_failed", lock_timeout=lock_timeout)
    return NotificationResult(
        "delivery_failed",
        event_key,
        day,
        identifier,
        reserved=True,
        reason="macOS delivery failed",
    )


def notify_once(
    root: Path | str,
    key: str,
    message: str,
    title: str = "LIMEN host pressure",
    enabled: bool | None = None,
) -> bool:
    """Fire one notification per condition onset. Returns True iff this call fired.

    The dedup record is written even when notifications are disabled, so arming
    LIMEN_NOTIFY later does not replay every already-active condition.

    Hysteresis: if the key exists with a pending ``clean_since`` (a ``clear_condition``
    with a cooldown observed the condition clean but the cooldown has not elapsed), the
    onset has RETURNED before the clear could complete — cancel the pending clear (it is
    still one continuous episode) and stay quiet. It is not a re-onset, so it must not
    re-fire.
    """
    state = _load(root)
    if key in state:
        if "clean_since" in state[key]:
            del state[key]["clean_since"]
            _save(root, state)
        return False
    state[key] = {"first_seen": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "message": message[:300]}
    _save(root, state)
    if _enabled(enabled) and _root_may_speak(root):
        _deliver(message, title)
    return True


def clear_condition(root: Path | str, key: str, cooldown: int = 0) -> bool:
    """Forget an ended condition so its next onset notifies again.

    ``cooldown`` adds hysteresis for conditions sampled through a ROTATING window (e.g.
    merge-drain's CI-RED count, which assesses only a slice of the PR universe per beat):
    a single clean observation could be window rotation, not recovery, and an immediate
    clear re-arms the notification — so the next beat's red slice re-fires, paging the
    operator for one continuous episode (measured 2026-08-09: six CI-RED notifications in
    ~24h over a persistently red fleet). With ``cooldown > 0`` the clear does not complete
    until the condition has stayed clean for that many seconds: the first clean beat stamps
    ``clean_since`` and returns False; the clear lands only on a later clean beat once the
    window has elapsed. A returning onset (``notify_once`` on a ``clean_since`` record)
    cancels the pending clear, so the episode stays one notification.
    """
    state = _load(root)
    if key not in state:
        return False
    if cooldown > 0:
        record = state[key]
        clean_since = record.get("clean_since")
        now = time.time()
        if clean_since is None:
            record["clean_since"] = now
            _save(root, state)
            return False
        if now - clean_since < cooldown:
            return False
    del state[key]
    _save(root, state)
    return True


def active_conditions(root: Path | str) -> list[str]:
    return sorted(_load(root))


def main(argv: list[str] | None = None) -> int:
    """Small CLI bridge for shell callers such as netmode.sh."""
    parser = argparse.ArgumentParser(description="deliver a liveness-gated macOS notification")
    parser.add_argument("--root", default=os.environ.get("LIMEN_ROOT", str(Path(__file__).resolve().parents[1])))
    parser.add_argument("--title", default="LIMEN")
    parser.add_argument("--message", required=True)
    args = parser.parse_args(argv)
    notify(args.root, args.message, title=args.title)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
