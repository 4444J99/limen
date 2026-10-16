"""Test support for the TABVLARIVS keeper memory-pass regression tests.

Issue #2866. Provides disposable-sandbox construction, filesystem inventory, and
a PEP 578 mutation observer for `scripts/tabularius-organ.py`.

Three guards exist because a no-write assertion can pass without observing
anything. Each closes a distinct way that happens:

1. `assert_child_started` requires a case-specific exit status AND positive
   evidence that the intended entry point was actually invoked. A child that
   exits early, silently, or by signal is rejected rather than accepted.
2. `write_attempts(require=True)` raises when the observer produced no usable
   evidence, so "no mutation observed" can never be confused with "nothing was
   watching".
3. The observer records both endpoints of multi-path operations and covers the
   real CPython lock event.

Observation limits carried from the reproduction: PEP 578 audit hooks observe
events raised by the child interpreter only. They are NOT an operating-system-
wide write trace and NOT a sandbox, cannot detect a concurrent external writer,
and cannot exclude a create-then-delete between two snapshots. They do not
establish the safety of a path the code never exercised.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINT = REPO_ROOT / "scripts" / "tabularius-organ.py"
STATE_RELPATH = "logs/tabularius-organ-state.json"

# Areas a read-only mode must leave byte-for-byte unchanged.
PROTECTED_RELPATHS = ("root", "mem", "board")


OBSERVATION_LIMITS_DOC = (
    "PEP 578 audit hooks observe events raised by the child interpreter only.",
    "They are NOT an operating-system-wide write trace and NOT a sandbox.",
    "They cannot detect a concurrent external writer.",
    "A create-then-delete between two snapshots leaves no persistent trace.",
    "They do not establish the safety of a code path that was never exercised.",
)


class ChildDidNotStart(RuntimeError):
    """The child never reached the entry point; any assertion would be vacuous."""


class ObservationUnavailable(RuntimeError):
    """The mutation observer produced no usable evidence."""


# --- child interpreter selection ---------------------------------------------

def _interpreter_has_yaml(candidate: str, env: dict | None = None) -> bool:
    try:  # discovery-time probe: any failure means "not usable"
        return subprocess.run(
            [candidate, "-c", "import yaml"], capture_output=True, timeout=60,
            env=env, check=False,
        ).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def discover_child_interpreter() -> str:
    """Find an interpreter whose dependencies resolve without user site-packages.

    The sandbox redirects HOME, which disables user-site resolution. An
    interpreter that needs it (Homebrew's, where PyYAML lives under
    ~/Library/Python) crashes before reaching the behaviour under test.
    """
    override = os.environ.get("LIMEN_TEST_CHILD_PYTHON")
    if override:
        if not _interpreter_has_yaml(override):
            raise RuntimeError(f"LIMEN_TEST_CHILD_PYTHON={override} cannot import yaml")
        return override
    runtimes = sorted(
        Path.home().glob(".local/share/limen/runtimes/*/venv/bin/python"),
        key=lambda p: p.parent.parent.name,
        reverse=True,
    )
    for cand in runtimes:
        if _interpreter_has_yaml(str(cand)):
            return str(cand)
    if _interpreter_has_yaml(sys.executable):
        return sys.executable
    raise RuntimeError("no interpreter with PyYAML; set LIMEN_TEST_CHILD_PYTHON")


CHILD_INTERPRETER = discover_child_interpreter()


# --- the mutation observer, installed into the child interpreter --------------

_AUDITOR = r'''
import atexit, json, os, sys

_LOG = os.environ.get("REPRO_WRITE_LOG")
_state = {"busy": False, "lines": [], "installed": False}

# 'open' audit args: (path, mode, flags)
_MODE_CHARS = ("w", "a", "x", "+")
_WRITE_FLAGS = (os.O_WRONLY, os.O_RDWR, os.O_CREAT, os.O_TRUNC, os.O_APPEND)

# Multi-path operations: both endpoints must be retained or a destination-based
# check silently misses the file arriving in the protected area.
_MULTIPATH = {
    "os.rename": (0, 1),
    "os.replace": (0, 1),
    "os.link": (0, 1),
    "os.symlink": (0, 1),
    "shutil.copymode": (0, 1),
    "shutil.copystat": (0, 1),
}

# 'fcntl.flock' is the real CPython locking event (args: fd, operation).
# 'os.lock' is NOT emitted by CPython and is deliberately absent here.
_EVENTS = frozenset((
    "open", "os.mkdir", "os.makedirs", "os.rename", "os.replace", "os.remove",
    "os.rmdir", "os.truncated", "os.truncate", "os.link", "os.symlink",
    "os.chmod", "os.chown", "shutil.copyfile", "shutil.copymode",
    "shutil.copystat", "shutil.rmtree", "fcntl.flock", "os.listdir",
))


def _emit(lines, rec):
    lines.append(json.dumps(rec, sort_keys=True))


def _write(lines):
    if not _LOG or not lines:
        return
    try:
        fd = os.open(_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.write(fd, ("\n".join(lines) + "\n").encode())
        os.close(fd)
    except Exception as exc:
        # Never fail silently: an unusable evidence file must be visible.
        try:
            sys.stderr.write(
                "REPRO_OBSERVER_FLUSH_FAILED %r\n" % (exc,)
            )
            sys.stderr.flush()
        except Exception:
            pass


def _hook(event, args):
    if _state["busy"] or not _LOG or event not in _EVENTS:
        return
    try:
        if event == "open":
            mode = args[1] if len(args) > 1 and isinstance(args[1], str) else ""
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            if not (any(c in mode for c in _MODE_CHARS)
                    or (flags and any(flags & f for f in _WRITE_FLAGS))):
                return
            _emit(_state["lines"], {
                "kind": "mutation", "event": event, "mode": mode,
                "flags": flags, "paths": [args[0]],
            })
            return
        if event == "fcntl.flock":
            _emit(_state["lines"], {
                "kind": "mutation", "event": event,
                "fd": args[0] if args else None,
                "operation": args[1] if len(args) > 1 else None,
                "paths": [],
            })
            return
        idx = _MULTIPATH.get(event)
        paths = [args[i] for i in idx if len(args) > i] if idx else (
            [args[0]] if args else []
        )
        _emit(_state["lines"], {
            "kind": "mutation", "event": event, "paths": paths,
        })
    except Exception:
        pass


def _install():
    _state["busy"] = True
    try:
        sys.addaudithook(_hook)
        _state["installed"] = True
        _emit(_state["lines"], {
            "kind": "marker", "marker": "observer_installed",
            "entry": sys.argv[0] if sys.argv else None,
            "cwd": os.getcwd(), "pid": os.getpid(),
        })
    finally:
        _state["busy"] = False


def _finish():
    _state["busy"] = True
    try:
        _emit(_state["lines"], {
            "kind": "marker", "marker": "observer_completed",
            "mutations": sum(
                1 for ln in _state["lines"] if '"kind": "mutation"' in ln
            ),
        })
    finally:
        _state["busy"] = False
    _write(_state["lines"])


if _LOG:
    _install()
    atexit.register(_finish)
'''

# A valid MemoryTicket: the model requires ticket_id, timestamp, agent, slug,
# title and desc. A partial dict is malformed input and cannot establish a
# successful lifecycle.
VALID_TICKET = {
    "ticket_id": "synthetic-2866-0001",
    "timestamp": "2026-10-16T00:00:00+00:00",
    "agent": "opencode",
    "session_id": "synthetic-repro",
    "slug": "synthetic-repro-2866",
    "title": "synthetic ticket for #2866 reproduction",
    "desc": "Synthetic ticket. Never drained against live state.",
    "star": False,
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def inventory(root: Path) -> dict:
    """Snapshot path/type/mode/size/mtime_ns/sha256 beneath `root`."""
    out: dict = {}
    if not root.exists():
        return out
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(dirnames) + sorted(filenames):
            p = Path(dirpath) / name
            st = p.lstat()
            kind = "link" if p.is_symlink() else ("dir" if p.is_dir() else "file")
            rec = {
                "type": kind,
                "mode": oct(st.st_mode & 0o7777),
                "size": st.st_size,
                "mtime_ns": st.st_mtime_ns,
            }
            if kind == "file":
                rec["sha256"] = _sha256(p)
            out[str(p.relative_to(root))] = rec
    return out


class KeeperSandbox:
    """Disposable sandbox with every writable destination redirected.

    No host environment is inherited and no live credential is present, so the
    entry point fails closed on the broker and no remote keeper is contacted.
    """

    def __init__(self, base: Path, name: str, *, memoria: bool = True,
                 memory_populated: bool = False, memory_ticket: dict | None = None,
                 health_state: str | None = None, board_mode: str | None = None,
                 omit_memory_dir: bool = False):
        self.root = base / name
        if self.root.exists():
            shutil.rmtree(self.root)
        for sub in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data",
                    "board", "auditor"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        # The entry point resolves STATE as LIMEN_ROOT / STATE_RELPATH. These
        # MUST agree or every no-write assertion checks a path never written.
        self.limen_root = self.root / "root"
        self.state_path = self.limen_root / STATE_RELPATH
        self.memory_dir = self.root / "mem"
        self.board_path = self.root / "board" / "tasks.yaml"
        self.board_path.write_text("")
        self.write_log = self.root / "auditor" / "writes.jsonl"

        if memory_populated:
            inbox = self.memory_dir / ".covenant-inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            payload = VALID_TICKET if memory_ticket is None else memory_ticket
            (inbox / "synthetic.json").write_text(json.dumps(payload))

        if health_state == "preexisting":
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(
                '{"updated": "1970-01-01T00:00:00+00:00", "preExisting": true}'
            )

        (self.root / "auditor" / "sitecustomize.py").write_text(_AUDITOR)

        self.env = {
            "PATH": "/usr/bin:/bin",
            "HOME": str(self.root / "home"),
            "TMPDIR": str(self.root / "tmp"),
            "XDG_CACHE_HOME": str(self.root / "xdg-cache"),
            "XDG_CONFIG_HOME": str(self.root / "xdg-config"),
            "XDG_DATA_HOME": str(self.root / "xdg-data"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(self.root / "auditor"),
            "REPRO_WRITE_LOG": str(self.write_log),
            "NO_COLOR": "1",
            "LIMEN_ROOT": str(self.limen_root),
            "LIMEN_TASKS": str(self.board_path),
        }
        if not omit_memory_dir:
            self.env["LIMEN_MEMORY_DIR"] = str(self.memory_dir)
        if memoria:
            self.env["LIMEN_MEMORIA"] = "1"
        self.board_mode = board_mode
        if board_mode:
            self.env["REPRO_BOARD_MODE"] = board_mode
            self.env["REPRO_SRC"] = str(REPO_ROOT / "cli" / "src")

    # --- execution ----------------------------------------------------------

    def run(self, *argv: str, expect_exit: int | None = 0, timeout: int = 120):
        """Run the entry point and prove it actually reached the code under test."""
        proc = subprocess.run(
            [CHILD_INTERPRETER, str(ENTRY_POINT), *argv],
            env=self.env, capture_output=True, text=True,
            timeout=timeout, cwd=str(REPO_ROOT), check=False,
        )
        self.last_proc = proc
        self._guard(proc, expect_exit)
        return proc

    def run_unchecked(self, *argv: str, timeout: int = 120):
        """Run without the guard. For negative-control probes only."""
        proc = subprocess.run(
            [CHILD_INTERPRETER, str(ENTRY_POINT), *argv],
            env=self.env, capture_output=True, text=True,
            timeout=timeout, cwd=str(REPO_ROOT), check=False,
        )
        self.last_proc = proc
        return proc

    def _guard(self, proc, expect_exit):
        stderr = proc.stderr or ""
        for marker in ("Traceback (most recent call last)", "ModuleNotFoundError",
                       "SyntaxError", "ImportError: No module named",
                       "REPRO_OBSERVER_FLUSH_FAILED"):
            if marker in stderr:
                raise ChildDidNotStart(
                    f"child failed to start cleanly ({marker}); assertions would be "
                    f"vacuous.\nstdout: {proc.stdout}\nstderr: {stderr}"
                )
        if proc.returncode < 0:
            raise ChildDidNotStart(
                f"child terminated by signal {-proc.returncode}; assertions would "
                f"be vacuous.\nstdout: {proc.stdout}"
            )
        if expect_exit is not None and proc.returncode != expect_exit:
            raise ChildDidNotStart(
                f"exit status {proc.returncode} != expected {expect_exit}.\n"
                f"stdout: {proc.stdout}\nstderr: {stderr}"
            )
        # Positive evidence: the intended entry point was the process's script.
        blob = proc.stdout + proc.stderr
        if str(ENTRY_POINT) not in blob and not (proc.stdout or "").strip():
            raise ChildDidNotStart(
                "child produced no output identifying the entry point; assertions "
                f"would be vacuous.\nstdout: {proc.stdout!r}\nstderr: {stderr!r}"
            )

    # --- observation --------------------------------------------------------

    def write_attempts(self, require: bool = True) -> list[dict]:
        """Parsed observer records. Raises unless evidence is available."""
        if not self.write_log.exists():
            if require:
                raise ObservationUnavailable(
                    f"observer produced no evidence at {self.write_log}"
                )
            return []
        records = []
        for line in self.write_log.read_text().splitlines():
            if line.strip():
                records.append(json.loads(line))
        markers = {r.get("marker") for r in records if r.get("kind") == "marker"}
        if require and not {"observer_installed", "observer_completed"} <= markers:
            raise ObservationUnavailable(
                f"observer evidence incomplete; markers={sorted(m for m in markers if m)}"
            )
        return records

    def mutations(self, require: bool = True) -> list[dict]:
        return [r for r in self.write_attempts(require=require)
                if r.get("kind") == "mutation"]

    def mutations_touching(self, needle: str, require: bool = True) -> list[dict]:
        hits = []
        for rec in self.mutations(require=require):
            if any(needle in str(p) for p in rec.get("paths", [])):
                hits.append(rec)
        return hits

    def child_reported_entry(self) -> str | None:
        for rec in self.write_attempts(require=False):
            if rec.get("marker") == "observer_installed":
                return rec.get("entry")
        return None

    # --- state --------------------------------------------------------------

    def state_payload(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text())
        except json.JSONDecodeError:
            return {}

    def protected_inventory(self) -> dict:
        """Inventory of every area a read-only mode must not change."""
        snap = {}
        for rel in PROTECTED_RELPATHS:
            snap[rel] = inventory(self.root / rel)
        return snap

    def provenance(self) -> dict:
        return {
            "repo_root": str(REPO_ROOT),
            "entry_point": str(ENTRY_POINT),
            "parent_interpreter": sys.executable,
            "child_interpreter": CHILD_INTERPRETER,
            "child_python_version": subprocess.run(
                [CHILD_INTERPRETER, "-c", "import sys;print(sys.version.split()[0])"],
                capture_output=True, text=True, timeout=60, check=False,
            ).stdout.strip(),
        }