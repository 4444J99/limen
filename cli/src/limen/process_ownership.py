"""Bounded, read-only process identity and session ownership observation.

Raw argv/environ stay in memory. Reports expose only identities and reason codes.
Service authority comes from effective configuration, never a daemon subtree.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import re
import shlex
import struct
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from limen.conduct.liveness import invocation_subcommand
from limen.host_admission import pid_is_alive, process_identity

SCHEMA = "limen.process_ownership.v1"
ENV_KEYS = frozenset({"CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_HOME"})
CATEGORIES = ("checker", "shared_service", "foreign_session", "owned_survivor", "unknown", "unmeasured")


class ObservationUnavailable(ValueError):
    """A required observation could not establish a complete, stable identity."""


@dataclass
class Process:
    pid: int
    parent: int
    uid: int
    started: str | None
    argv: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None
    readable: bool = True


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def native_details(pid: int) -> tuple[tuple[str, ...], dict[str, str]]:
    """Read bounded native arguments; retain ONLY allowlisted environment keys."""
    if sys.platform == "darwin":
        libc = ctypes.CDLL(None, use_errno=True)
        libc.sysctl.argtypes = [
            ctypes.POINTER(ctypes.c_int),
            ctypes.c_uint,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        libc.sysctl.restype = ctypes.c_int
        mib = (ctypes.c_int * 3)(1, 49, pid)  # CTL_KERN, KERN_PROCARGS2
        size = ctypes.c_size_t(0)
        if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or not 5 <= size.value <= 2 * 1024 * 1024:
            raise ObservationUnavailable("native_identity_unreadable")
        buffer = ctypes.create_string_buffer(size.value)
        if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
            raise ObservationUnavailable("native_identity_unreadable")
        raw = buffer.raw[: size.value]
        if len(raw) < 5:
            raise ObservationUnavailable("native_identity_malformed")
        argc = struct.unpack("=i", raw[:4])[0]
        if not 1 <= argc <= 4096:
            raise ObservationUnavailable("native_identity_malformed")
        offset = raw.find(b"\0", 4)
        if offset < 0:
            raise ObservationUnavailable("native_identity_malformed")
        offset += 1
        while offset < len(raw) and raw[offset] == 0:
            offset += 1
        fields = raw[offset:].split(b"\0")
        if len(fields) < argc:
            raise ObservationUnavailable("native_identity_malformed")
        argv = tuple(os.fsdecode(word) for word in fields[:argc])
        env_fields = fields[argc:]
    elif sys.platform.startswith("linux"):
        root = Path("/proc") / str(pid)
        argv = tuple(os.fsdecode(word) for word in root.joinpath("cmdline").read_bytes().split(b"\0") if word)
        env_fields = root.joinpath("environ").read_bytes().split(b"\0")
    else:
        raise ObservationUnavailable("native_identity_unsupported")
    # npm rewrites argv[0] to its exact process title and clears remaining argv.
    if argv and argv[0].startswith("npm exec ") and all(not word for word in argv[1:]):
        argv = tuple(shlex.split(argv[0]))
    env = {}
    for word in env_fields:
        key, separator, value = word.partition(b"=")
        name = os.fsdecode(key)
        if separator and name in ENV_KEYS:
            if name in env or len(value) > 4096:
                raise ObservationUnavailable("native_identity_malformed")
            env[name] = os.fsdecode(value)
    return argv, env


def snapshot(root: Path) -> tuple[dict[int, Process], set[int]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,uid=,command="], capture_output=True, text=True, check=True, timeout=20
    )
    processes = {}
    for line in result.stdout.splitlines():
        bits = line.strip().split(None, 3)
        if len(bits) != 4:
            raise ObservationUnavailable("process_table_incomplete")
        pid, parent, uid = map(int, bits[:3])
        try:
            argv = tuple(shlex.split(bits[3]))
        except ValueError:
            argv = ()
        processes[pid] = Process(pid, parent, uid, None, argv)
    excluded = {os.getpid()}
    cursor = os.getpid()
    while cursor in processes and processes[cursor].parent not in excluded:
        cursor = processes[cursor].parent
        excluded.add(cursor)
    # A permission-limited lsof is unmeasured, including nonempty partial output.
    with subprocess.Popen(
        ["lsof", "-nP", "-a", "-d", "cwd", "-F", "pn"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ) as observer:
        try:
            output, _ = observer.communicate(timeout=20)
        except subprocess.TimeoutExpired:
            observer.kill()  # The checker-owned observer ONLY.
            observer.communicate()
            raise ObservationUnavailable("cwd_observation_timeout") from None
        if observer.returncode:
            raise ObservationUnavailable("cwd_observation_incomplete")
        excluded.add(observer.pid)
    cwd_pid: int | None = None
    for line in output.decode().splitlines():
        if line.startswith("p"):
            cwd_pid = int(line[1:])
        elif line.startswith("n") and cwd_pid in processes:
            processes[cwd_pid].cwd = Path(line[1:]).resolve()
    for process in processes.values():
        if process.uid != os.getuid():
            continue
        before = process_identity(process.pid)
        if before is None:
            process.readable = False
            continue
        try:
            argv, env = native_details(process.pid)
            after = process_identity(process.pid)
            if before != after:
                raise ObservationUnavailable("process_identity_changed")
            process.argv, process.env, process.started = argv, env, before
        except (OSError, ValueError):
            process.started, process.readable = before, False
    return processes, excluded


def canonical_argv(argv: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Resolve executable/script symlinks; never expand arguments or environment."""
    import shutil

    result = []
    for index, word in enumerate(argv):
        path = Path(word)
        if index == 0 and not path.is_absolute():
            word = shutil.which(word) or word
            path = Path(word)
        if index == 0 and path.is_file():
            resolved = path.resolve()
            # Homebrew's framework stub execs this app binary in the SAME framework.
            if (
                resolved.parent.name == "bin"
                and "Python.framework" in resolved.parts
                and resolved.name.startswith("python")
            ):
                app = resolved.parent.parent / "Resources/Python.app/Contents/MacOS/Python"
                if app.is_file():
                    path = app
        result.append(str(path.resolve()) if path.is_absolute() and path.exists() else word)
    return tuple(result)


def native_thread_witness(process: Process, witnesses: dict[str, dict]) -> str | None:
    thread = process.env.get("CODEX_THREAD_ID")
    if not thread:
        return None
    witness = witnesses.get(thread)
    if not witness or witness.get("session_id") != process.env.get("CODEX_SESSION_ID"):
        raise ObservationUnavailable("native_thread_witness_missing")
    return thread


def belongs_to_subject(thread: str, subject: str, witnesses: dict[str, dict]) -> bool:
    seen = set()
    while thread and thread not in seen:
        if thread == subject:
            return True
        seen.add(thread)
        thread = witnesses.get(thread, {}).get("parent_thread_id") or ""
    return False


def transcript_witness(path: Path) -> dict:
    with path.open() as source:
        row = json.loads(source.readline(64 * 1024))
    payload = row.get("payload", {})
    if not isinstance(payload, dict):
        raise ObservationUnavailable("native_metadata_invalid")
    thread = payload.get("id")
    if row.get("type") != "session_meta" or not isinstance(thread, str):
        raise ObservationUnavailable("native_metadata_invalid")
    session = payload.get("session_id", thread)
    parent = payload.get("source", {})
    parent = (
        parent.get("subagent", {}).get("thread_spawn", {}).get("parent_thread_id") if isinstance(parent, dict) else None
    )
    if session != thread and (not parent or payload.get("forked_from_id") != parent):
        raise ObservationUnavailable("native_ancestry_invalid")
    return {"thread_id": thread, "session_id": session, "parent_thread_id": parent}


def read_native_witnesses(home: Path, ids: set[str], seen: frozenset[str] = frozenset()) -> dict[str, dict]:
    """Read only exact-ID transcript headers from the declared native runtime."""
    if seen.intersection(ids) or len(seen) > 32:
        raise ObservationUnavailable("native_ancestry_cycle")
    found: dict[str, dict] = {}
    if any(not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", thread) for thread in ids):
        raise ObservationUnavailable("native_thread_identifier_invalid")
    for directory in (home / "sessions", home / "archived_sessions"):
        for thread in ids:
            for path in directory.glob(f"**/rollout-*{thread}.jsonl"):
                value = transcript_witness(path)
                if value["thread_id"] != thread or (thread in found and found[thread] != value):
                    raise ObservationUnavailable("native_metadata_conflict")
                found[thread] = value
    # Validate child->parent lineage all the way to the root, not just one tag.
    parents = {w["parent_thread_id"] for w in found.values() if w["parent_thread_id"]} - found.keys()
    if parents:
        found.update(read_native_witnesses(home, parents, seen | ids))
    for value in found.values():
        parent = value["parent_thread_id"]
        if parent and (parent not in found or found[parent]["session_id"] != value["session_id"]):
            raise ObservationUnavailable("native_ancestry_invalid")
    return found


def assess(
    processes: dict[int, Process],
    excluded: set[int],
    root: Path,
    session_id: str,
    *,
    contracts: list[dict] | tuple[dict, ...] = (),
    witnesses: dict[str, dict] | None = None,
    evidence: list[dict] | tuple[dict, ...] = (),
    identity=process_identity,
) -> dict:
    """Classify each exact instance; a shared host never exempts its whole tree."""
    witnesses = witnesses or {}
    argv_cache: dict[tuple[str, ...], tuple[str, ...]] = {}

    def normalized(argv: tuple[str, ...] | list[str]) -> tuple[str, ...]:
        key = tuple(argv)
        if key not in argv_cache:
            argv_cache[key] = canonical_argv(key)
        return argv_cache[key]

    rows = []
    service_instances: dict[int, str] = {}
    evidence_index = {row["pid"]: row for row in evidence}
    if len(evidence_index) != len(evidence):
        raise ObservationUnavailable("duplicate_process_evidence")
    pending = sorted(processes.values(), key=lambda p: p.pid)
    # Parent-first classification without assuming PID ordering or trusting ancestry alone.
    ordered = []
    visited = set()

    def visit(process):
        if process.pid in visited:
            return
        visited.add(process.pid)
        if process.parent in processes:
            visit(processes[process.parent])
        ordered.append(process)

    for process in pending:
        visit(process)
    for process in ordered:
        in_scope = bool(process.cwd and process.cwd.is_relative_to(root))
        thread = process.env.get("CODEX_THREAD_ID")
        if process.pid in excluded:
            if in_scope:
                rows.append({"pid": process.pid, "category": "checker", "reason": "checker_ancestry"})
            continue
        if not in_scope and not thread and process.pid not in evidence_index:
            # Still classify configured parents needed as bootstrap witnesses.
            relevant = any(normalized(process.argv) == normalized(c["argv"]) for c in contracts)
            if not relevant:
                continue
        category, reason, owner = "unknown", "ownership_unresolved", None
        service_witness = None
        if not process.readable or not process.started:
            category, reason = "unmeasured", "process_identity_unreadable"
        elif identity(process.pid) != process.started:
            if identity(process.pid) is None and not pid_is_alive(process.pid):
                continue  # Exact observed instance exited; one bounded recheck.
            category, reason = "unmeasured", "process_identity_changed"
        else:
            claim = evidence_index.get(process.pid)
            if claim and (
                claim.get("process_identity") != process.started
                or claim.get("argv_sha256") != digest(normalized(process.argv))
            ):
                category, reason = "unmeasured", "process_evidence_stale"
            else:
                try:
                    execution = native_thread_witness(process, witnesses)
                except ObservationUnavailable:
                    category, reason = "unmeasured", "native_thread_witness_missing"
                    execution = None
                if execution:
                    category = (
                        "owned_survivor" if belongs_to_subject(execution, session_id, witnesses) else "foreign_session"
                    )
                    reason, owner = "exact_native_thread", execution
                elif category != "unmeasured":
                    matches = []
                    for contract in contracts:
                        if normalized(process.argv) != normalized(contract["argv"]):
                            continue
                        parent_service = service_instances.get(process.parent)
                        if contract.get("parent_service") and parent_service != contract["parent_service"]:
                            continue
                        cursor, seen = process.parent, set()
                        host = None
                        while cursor in processes and cursor not in seen:
                            seen.add(cursor)
                            ancestor = processes[cursor]
                            home_matches = (
                                "config_home" not in contract
                                or Path(ancestor.env.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
                                == Path(contract["config_home"]).resolve()
                            )
                            if (
                                ancestor.readable
                                and ancestor.started
                                and ancestor.uid == process.uid
                                and home_matches
                                and invocation_subcommand(ancestor.argv) == "app-server"
                                and normalized(ancestor.argv) == normalized(contract["host_argv"])
                            ):
                                if identity(cursor) == ancestor.started:
                                    host = ancestor
                                break
                            cursor = ancestor.parent
                        if host and (contract.get("parent_service") or process.parent == host.pid):
                            matches.append((contract, host))
                    identities = {c["service_id"] for c, _ in matches}
                    if len(identities) == 1:
                        contract, host = matches[0]
                        category, reason, owner = "shared_service", "verified_service_contract", contract["service_id"]
                        service_instances[process.pid] = owner
                        service_witness = {
                            "service_id": owner,
                            "argv_sha256": digest(normalized(process.argv)),
                            "contract_sha256": contract["contract_sha256"],
                            "host_pid": host.pid,
                            "host_identity": host.started,
                        }
                        if claim and (
                            claim.get("service_id") != owner
                            or claim.get("contract_sha256") != contract["contract_sha256"]
                            or claim.get("host_pid") != host.pid
                            or claim.get("host_identity") != host.started
                        ):
                            category, reason = "unmeasured", "process_evidence_conflict"
                    elif len(identities) > 1:
                        category, reason = "unmeasured", "service_registration_ambiguous"
        if in_scope or (thread and belongs_to_subject(thread, session_id, witnesses)) or process.pid in evidence_index:
            row = {"pid": process.pid, "process_identity": process.started, "category": category, "reason": reason}
            if owner:
                row["owner"] = owner
            if service_witness and category == "shared_service":
                row.update(service_witness)
            rows.append(row)
    counts = {category: sum(row["category"] == category for row in rows) for category in CATEGORIES}
    return {
        "schema": SCHEMA,
        "complete": counts["unmeasured"] == 0,
        "process_count": counts["owned_survivor"] + counts["unknown"],
        "observed_count": len(rows),
        "counts": counts,
        "processes": rows,
    }


def observe(root: Path, session_id: str, *, evidence: list[dict] | tuple[dict, ...] = ()) -> dict:
    from limen.process_services import service_contracts

    processes, excluded = snapshot(root)
    ids = {p.env["CODEX_THREAD_ID"] for p in processes.values() if p.env.get("CODEX_THREAD_ID")}
    homes = {Path(p.env["CODEX_HOME"]) for p in processes.values() if p.env.get("CODEX_HOME")}
    homes.add(Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    witnesses: dict[str, dict] = {}
    for home in homes:
        for key, value in read_native_witnesses(home, ids).items():
            if key in witnesses and witnesses[key] != value:
                raise ObservationUnavailable("native_metadata_conflict")
            witnesses[key] = value
    contracts = service_contracts(processes)
    operational = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "domus/process-ownership"
    claims = {row["pid"]: row for row in evidence}
    if operational.exists():
        state = operational.stat()
        if operational.is_symlink() or state.st_uid != os.getuid() or state.st_mode & 0o077:
            raise ObservationUnavailable("unsafe_process_evidence_root")
        for process in processes.values():
            if not process.cwd or not process.cwd.is_relative_to(root) or process.pid in excluded:
                continue
            path = operational / f"{process.pid}.json"
            if not path.exists():
                continue
            info = path.stat()
            if path.is_symlink() or info.st_uid != os.getuid() or info.st_mode & 0o077 or info.st_size > 65536:
                raise ObservationUnavailable("unsafe_process_evidence_file")
            row = json.loads(path.read_bytes())
            if row.get("schema") != SCHEMA or row.get("pid") != process.pid:
                raise ObservationUnavailable("invalid_process_evidence_file")
            if process.pid in claims and any(
                claims[process.pid].get(field) != row.get(field)
                for field in (
                    "process_identity",
                    "argv_sha256",
                    "service_id",
                    "contract_sha256",
                    "host_pid",
                    "host_identity",
                )
            ):
                raise ObservationUnavailable("process_evidence_conflict")
            claims[process.pid] = row
    return assess(
        processes, excluded, root, session_id, contracts=contracts, witnesses=witnesses, evidence=list(claims.values())
    )
