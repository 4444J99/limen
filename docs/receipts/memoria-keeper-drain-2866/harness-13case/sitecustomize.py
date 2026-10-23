"""Test instrumentation for #2866 reproduction.

Instruments the child process with a PEP 578 audit hook so write ATTEMPTS are
recorded, not just persistent filesystem state. It observes only; it does not
replace or stub any application function, with the single documented exception of
the board-boundary fault injection used for the deferred/processed cases, which
is applied via REPRO_BOARD_MODE and recorded as such.

Evidence flushes at exit to $REPRO_WRITE_LOG, always OUTSIDE the measured sandbox
so the hook's own I/O cannot be mistaken for an application write.

CHANGES FROM THE PRESERVED 11-CASE BUNDLE (bundle-11case-original/harness/):
  * `open` filtering now inspects CPython's separate `flags` argument in addition
    to the mode string. The preserved bundle's filter was mode-string-only.
  * Added REPRO_BOARD_MODE fault injection for the deferred/processed cases.
  * Added os.lock / fcntl.flock to the observed event set.
"""

import atexit
import os
import sys

_LOG = os.environ.get("REPRO_WRITE_LOG")
_busy = False
_lines = []

_WRITE_MODE_CHARS = ("w", "a", "x", "+")
# CPython audit 'open' flags: O_WRONLY/O_RDWR plus O_CREAT/O_TRUNC/O_APPEND are
# the write-intent bits. Checked in addition to the mode string.
_WRITE_FLAGS = (
    os.O_WRONLY,
    os.O_RDWR,
    os.O_CREAT,
    os.O_TRUNC,
    os.O_APPEND,
)
_INTERESTING = frozenset(
    (
        "open",
        "os.mkdir",
        "os.rename",
        "os.replace",
        "os.remove",
        "os.rmdir",
        "os.truncate",
        "os.link",
        "os.symlink",
        "os.chmod",
        "os.chown",
        "shutil.copyfile",
        "shutil.copymode",
        "shutil.copystat",
        "shutil.rmtree",
        "os.lock",
    )
)


def _flush():
    global _busy
    if not _LOG or not _lines:
        return
    _busy = True
    try:
        fd = os.open(_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        os.write(fd, ("\n".join(_lines) + "\n").encode())
        os.close(fd)
    except Exception:
        pass
    finally:
        _busy = False


def _hook(event, args):
    global _busy
    if _busy or not _LOG or event not in _INTERESTING:
        return
    try:
        if event == "open":
            mode = args[1] if len(args) > 1 and isinstance(args[1], str) else ""
            flags = args[2] if len(args) > 2 and isinstance(args[2], int) else 0
            mode_write = any(ch in mode for ch in _WRITE_MODE_CHARS)
            flag_write = any(f & _WRITE_FLAGS for f in (_WRITE_FLAGS if not flags else (flags,)))
            if not (mode_write or flag_write):
                return
            detail = f"mode={mode or '-'} flags=0{flags:x}"
            path = args[0]
        else:
            detail = ""
            path = args[0] if args else None
        _lines.append(f"{event}\t{detail}\t{path}")
    except Exception:
        pass


def _install_board_fault_injection():
    """Stub ONLY the external board boundary so no remote keeper is contacted.

    The outer entry point and the real _stamp() writer are left untouched.
    """
    mode = os.environ.get("REPRO_BOARD_MODE")
    src = os.environ.get("REPRO_SRC")
    if not mode or not src:
        return
    if src not in sys.path:
        # insert(0), not append: the venv's site-packages also provides `limen`,
        # and the pinned worktree source must win for provenance to hold.
        sys.path.insert(0, src)
    try:
        import limen.tabularius as tb
    except Exception:
        return

    class _Result:
        def __init__(self):
            if mode == "deferred":
                self.deferred = True
                self.pending = 3
                self.applied = 0
                self.rejected = 0
                self.wrote = 0
                self.note = "synthetic deferral (fault injection)"
            else:  # processed
                self.deferred = False
                self.pending = 2
                self.applied = 2
                self.rejected = 1
                self.wrote = 2
                self.note = "synthetic processed (fault injection)"

    def _fake_drain_once(board, dry_run=False):
        return _Result()

    tb.drain_once = _fake_drain_once


if _LOG:
    sys.addaudithook(_hook)
    atexit.register(_flush)

_install_board_fault_injection()