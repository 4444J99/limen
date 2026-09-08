"""Persistent, private custody for one owner repair and verification per episode.

The owner effector retains configuration mutation and conditional rollback authority.
This journal never replays an interrupted side effect or treats old verification as fresh.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _private(path, *, directory=False):
    info = path.lstat()
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if path.is_symlink() or not kind(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError("unsafe healing custody")


def _write(path, data):
    fd, name = tempfile.mkstemp(prefix=".episode-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(data, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temporary.unlink(missing_ok=True)


def heal(state_root: Path, *, owner: str, repair_id: str, bindings: dict, repair, verify):
    """Serialize the owner target, journal before callbacks, and never replay them.

    Callbacks must be bounded by their existing owner interfaces. Bindings contain
    fingerprints, never credentials or raw configurations. A completed repair may
    resume its not-yet-started verification after interruption. An uncertain repair
    or verification requires owner disposition, including any conditional rollback.
    """
    required = {"registration", "configuration", "dependency", "policy", "failure"}
    if set(bindings) != required or any(
        not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value)
        for value in bindings.values()
    ):
        raise ValueError("incomplete healing episode bindings")
    episode = fingerprint([owner, repair_id, bindings])
    target = fingerprint([owner, repair_id])
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    _private(state_root, directory=True)
    fd = os.open(state_root / (target + ".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as lock:
        _private(state_root / (target + ".lock"))
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return {"outcome": "busy", "episode": episode, "owner": owner}
        path = state_root / (episode + ".json")
        if path.exists() or path.is_symlink():
            _private(path)
            record = json.loads(path.read_text())
            if (not isinstance(record, dict) or record.get("episode") != episode or record.get("bindings") != bindings
                    or record.get("owner") != owner or record.get("repair_id") != repair_id):
                raise ValueError("healing custody identity mismatch")
        else:
            record = {"schema": "limen.mcp_healing_episode.v1", "episode": episode,
                      "owner": owner, "repair_id": repair_id, "bindings": bindings,
                      "state": "repair_started"}
            _write(path, record)
            try:
                result = repair()
                if not isinstance(result, dict) or not isinstance(result.get("outcome"), str):
                    raise ValueError("invalid owner repair receipt")
                # Retain only the owner's outcome and rollback identity; its private
                # backup location and other response data stay with that effector.
                record["repair"] = {k: result[k] for k in ("outcome", "episode") if k in result}
                record["state"] = "verify_pending"
                _write(path, record)
            except Exception:
                record["state"] = "repair_interrupted"
                _write(path, record)
                raise
        if record["state"] == "verify_pending":
            record["state"] = "verify_started"
            _write(path, record)
            try:
                result = verify()
                if result not in ("pass", "fail", "unmeasured"):
                    raise ValueError("invalid healing verification")
                record["verification"] = result
                record["state"] = "finished"
                _write(path, record)
            except Exception:
                record["state"] = "verify_interrupted"
                _write(path, record)
                raise
            reused = False
        else:
            reused = True
        uncertain = record["state"] != "finished"
        return {"episode": episode, "owner": owner, "reused": reused,
                "outcome": "owner_record_required" if uncertain else record.get("repair", {}).get("outcome", "unavailable"),
                "verification": record.get("verification", "unmeasured"),
                "rollback_episode": record.get("repair", {}).get("episode"),
                "state": record["state"]}
