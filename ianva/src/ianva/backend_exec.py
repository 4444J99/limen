"""Least-authority exec boundary for the long-lived ianva backend."""

from __future__ import annotations

import os
import sys

from .creds import sanitize_backend_env


def main(argv: list[str] | None = None) -> int:
    backend_argv = list(sys.argv[1:] if argv is None else argv)
    if not backend_argv:
        print("ianva backend exec: missing backend command", file=sys.stderr)
        return 127
    os.execvpe(backend_argv[0], backend_argv, sanitize_backend_env())
    return 127  # pragma: no cover - a successful exec never returns


if __name__ == "__main__":
    raise SystemExit(main())
