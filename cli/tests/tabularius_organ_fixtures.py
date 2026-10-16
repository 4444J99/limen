"""Test support for the TABVLARIVS keeper memory-pass regression tests.

Issue #2866. Provides disposable-sandbox construction, filesystem inventory, and
a PEP 578 write-attempt observer for `scripts/tabularius-organ.py`.

Scope note carried from the reproduction: PEP 578 audit hooks are an
EVENT-OBSERVATION mechanism, not an operating-system-wide write trace and not a
sandbox. They can show that a mutation call was made by this interpreter; they
cannot prove that no other process wrote, and a create-then-delete between two
snapshots leaves no persistent trace. `WriteAttemptLog.observation_limits`
records this explicitly so a passing no-write test cannot be over-read.
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
STATE_RELPATH = os.path.join("logs", "tabularius-organ-state.json")


class ChildInterpreterMissingError(RuntimeError):
    """No interpreter capable of running the entry point was found."""


def _interpreter_has_yaml(candidate: str) -> bool:
    try:
        return subprocess.run(
            [candidate, "-c", "import yaml"],
            capture_output=True, timeout=60,
        ).returncode == 0
    except Exception:
        return False


def discover_child_interpreter() -> str:
    """Find an interpreter that can import the entry point's dependencies.

    The sandbox deliberately redirects HOME, which disables interpreter
    *user-site* resolution. An interpreter that relies on user site-packages
    (e.g. Homebrew's, where PyYAML lives under ~/Library/Python) therefore cannot
    run the entry point inside a sandbox and would crash before reaching the
    behaviour under test. Select an interpreter whose dependencies resolve from
    its own site-packages.
    """
    override = os.environ.get("LIMEN_TEST_CHILD_PYTHON")
    if override:
        if not _interpreter_has_yaml(override):
            raise ChildInterpreterMissingError(
                f"LIMEN_TEST_CHILD_PYTHON={override} cannot import yaml"
            )
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
    raise ChildInterpreterMissingError(
        "no interpreter with PyYAML was found; set LIMEN_TEST_CHILD_PYTHON"
    )


CHILD_INTERPRETER = discover_child_interpreter()


def assert_child_started(proc: subprocess.CompletedProcess) -> None:
    """Fail loudly if the child crashed before reaching the behaviour under test.

    Without this, a child that dies on a missing dependency makes every
    no-write assertion pass vacuously.

    Scope is deliberately narrow. The `ImportError: cannot import name
    'MEMORY_DIR'` message printed by `_memory_pass` is the defect under test, not
    a startup failure, so it is not treated as one. Only genuine interpreter or
    module-load failures are.
    """
    stderr = proc.stderr or ""
    for marker in ("Traceback (most recent call last)", "ModuleNotFoundError",
                   "SyntaxError", "ImportError: No module named"):
        if marker in stderr:
            raise AssertionError(
                f"child process failed to start ({marker}); assertions would be "
                f"vacuous.\nstdout: {proc.stdout}\nstderr: {stderr}"
            )

# The observer installed into the child interpreter. Kept faithful to the
# reproduction harness, with write-intent detected from CPython's `open` audit
# args (mode string AND flags), and rename/remove/truncate/chmod/lock covered.
_AUDITOR = '''
import atexit, os, sys
_LOG = os.environ.get("REPRO_WRITE_LOG")
_busy = False
_lines = []
_MODE_CHARS = ("w", "a", "x", "+")
_FLAGS = (os.O_WRONLY, os.O_RDWR, os.O_CREAT, os.O_TRUNC, os.O_APPEND)
_EVENTS = frozenset((
    "open", "os.mkdir", "os.rename", "os.replace", "os.remove", "os.rmdir",
    "os.truncate", "os.link", "os.symlink", "os.chmod", "os.chown",
    "shutil.copyfile", "shutil.copymode", "shutil.copystat", "shutil.rmtree",
    "os.lock",
))
def _flush():
    global _busy
    if not _LOG or not _lines:
        return
    _busy = True
    try:
        fd = os.open(_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.write(fd, ("\\n".join(_lines) + "\\n").encode())
        os.close(fd)
    except Exception:
        pass
    finally:
        _busy = False
def _hook(event, args):
    global _busy
    if _busy or not _LOG or event not in _EVENTS:
        return
    try:
        if event == "open":
            mode = args[1] if len(args) > 1 and isinstance(args[1], str) else ""
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            if not (any(c in mode for c in _MODE_CHARS)
                    or (flags and any(flags & f for f in _FLAGS))):
                return
            detail = "mode=%s flags=0x%x" % (mode or "-", flags)
            path = args[0]
        else:
            detail = ""
            path = args[0] if args else None
        _lines.append("%s\\t%s\\t%s" % (event, detail, path))
    except Exception:
        pass
if _LOG:
    sys.addaudithook(_hook)
    atexit.register(_flush)


def _inject_board_boundary():
    """Stub ONLY the external board boundary so no remote keeper is contacted.

    The outer entry point and the real _stamp() writer are left untouched, so the
    deferred and processed branches are exercised through the real code path.
    """
    _mode = os.environ.get("REPRO_BOARD_MODE")
    _src = os.environ.get("REPRO_SRC")
    if not _mode or not _src:
        return
    if _src not in sys.path:
        # insert(0): the venv's site-packages also provides `limen`, and the
        # pinned worktree source must win for provenance to hold.
        sys.path.insert(0, _src)
    try:
        import limen.tabularius as _tb
    except Exception:
        return

    class _Result:
        def __init__(self):
            if _mode == "deferred":
                self.deferred, self.pending = True, 3
                self.applied, self.rejected, self.wrote = 0, 0, 0
                self.note = "synthetic deferral (fault injection)"
            else:
                self.deferred, self.pending = False, 2
                self.applied, self.rejected, self.wrote = 2, 1, 2
                self.note = "synthetic processed (fault injection)"

    _tb.drain_once = lambda board, dry_run=False: _Result()


_inject_board_boundary()
'''

OBSERVATION_LIMITS = (
    "PEP 578 audit hooks observe events raised by this interpreter only.",
    "They are not an OS-wide write trace and not a sandbox.",
    "They cannot detect a concurrent external writer.",
    "A create-then-delete between two snapshots leaves no persistent trace.",
)


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
            rel = str(p.relative_to(root))
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
            out[rel] = rec
    return out


class KeeperSandbox:
    """Disposable sandbox with every writable destination redirected.

    No host environment is inherited. Live credentials are never present, so the
    entry point fails closed on the broker and no remote keeper is contacted.
    """

    def __init__(self, base: Path, name: str, *, memoria: bool = True,
                 memory_populated: bool = False, health_state: str | None = None,
                 board_mode: str | None = None):
        self.root = base / name
        if self.root.exists():
            shutil.rmtree(self.root)
        for sub in ("home", "tmp", "xdg-cache", "xdg-config", "xdg-data",
                    "board", "auditor"):
            (self.root / sub).mkdir(parents=True, exist_ok=True)

        # The entry point derives STATE as ROOT/"logs"/"tabularius-organ-state.json",
        # where ROOT is LIMEN_ROOT. These MUST agree, or every no-write assertion
        # silently checks a path the application never writes.
        self.limen_root = self.root / "root"
        self.state_path = self.limen_root / STATE_RELPATH
        self.memory_dir = self.root / "mem"
        self.board_path = self.root / "board" / "tasks.yaml"
        self.board_path.write_text("")
        self.write_log = self.root / "auditor" / "writes.jsonl"

        if memory_populated:
            inbox = self.memory_dir / ".covenant-inbox"
            inbox.mkdir(parents=True, exist_ok=True)
            (inbox / "synthetic.json").write_text(
                json.dumps({"id": "synthetic", "slug": "repro", "title": "synthetic"})
            )

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
            "LIMEN_MEMORY_DIR": str(self.memory_dir),
        }
        if memoria:
            self.env["LIMEN_MEMORIA"] = "1"
        self.board_mode = board_mode
        if board_mode:
            self.env["REPRO_BOARD_MODE"] = board_mode
            self.env["REPRO_SRC"] = str(REPO_ROOT / "cli" / "src")

    def run(self, *argv: str, timeout: int = 120) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            [CHILD_INTERPRETER, str(ENTRY_POINT), *argv],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(REPO_ROOT),
        )
        assert_child_started(proc)
        return proc

    def state_payload(self) -> dict:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text())
        except json.JSONDecodeError:
            return {}

    def write_attempts(self) -> list[str]:
        if not self.write_log.exists():
            return []
        return [ln for ln in self.write_log.read_text().splitlines() if ln.strip()]

    def write_attempts_in(self, needle: str) -> list[str]:
        return [ln for ln in self.write_attempts() if needle in ln]


def provenance() -> dict:
    """Record what was actually executed, so a stray checkout cannot pass a test."""
    return {
        "repo_root": str(REPO_ROOT),
        "entry_point": str(ENTRY_POINT),
        "parent_interpreter": sys.executable,
        "child_interpreter": CHILD_INTERPRETER,
        "child_python_version": subprocess.run(
            [CHILD_INTERPRETER, "-c", "import sys;print(sys.version.split()[0])"],
            capture_output=True, text=True, timeout=60,
        ).stdout.strip(),
        "python_version": sys.version.split()[0],
    }