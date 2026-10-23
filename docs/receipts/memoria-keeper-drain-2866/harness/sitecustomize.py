"""Test instrumentation for #2866 reproduction.

Instruments the child process with a PEP 578 audit hook so write ATTEMPTS are
recorded, not just persistent filesystem state. It observes only; it does not
replace or stub any application function. The application writer runs unmodified.

Evidence is flushed at exit to $REPRO_WRITE_LOG, which always lives OUTSIDE the
measured sandbox so the hook's own I/O cannot be mistaken for an application write.
"""

import atexit
import os
import sys

_LOG = os.environ.get("REPRO_WRITE_LOG")
_busy = False
_lines = []

# 'open' audit args are (path, mode, flags); only record write-intent modes.
_WRITE_MODES = ("w", "a", "x", "+")
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
        "shutil.copyfile",
        "shutil.copymode",
        "shutil.copystat",
        "shutil.rmtree",
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
            if len(args) < 2 or not isinstance(args[1], str):
                return
            mode = args[1]
            if not any(ch in mode for ch in _WRITE_MODES):
                return
            detail = f"mode={mode}"
            path = args[0]
        else:
            detail = ""
            path = args[0] if args else None
        _lines.append(f"{event}\t{detail}\t{path}")
    except Exception:
        pass


if _LOG:
    sys.addaudithook(_hook)
    atexit.register(_flush)