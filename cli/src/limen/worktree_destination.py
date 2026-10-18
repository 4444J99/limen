"""Validate an explicit workstream destination without creating or reserving it."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from limen.storage_headroom import _existing_volume_path


def validate_destination(repository: Path, branch: str, destination: Path) -> None:
    if (
        not destination.is_absolute()
        or ".." in destination.parts
        or any(path.is_symlink() for path in (destination, *destination.parents))
    ):
        raise ValueError("destination must be absolute without symlinks or parent traversal")
    _existing_volume_path(destination)
    if not destination.exists():
        return

    def git(path: Path, *args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(path), *args], capture_output=True, text=True, check=True, timeout=5
        ).stdout.strip()

    if (
        git(destination, "rev-parse", "--show-toplevel") != str(destination)
        or git(destination, "rev-parse", "--path-format=absolute", "--git-common-dir")
        != git(repository, "rev-parse", "--path-format=absolute", "--git-common-dir")
        or git(destination, "branch", "--show-current") != branch
    ):
        raise ValueError("destination is not this repository's exact worktree and branch")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    try:
        validate_destination(args.repository, args.branch, args.destination)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        parser.exit(2, "destination refused: " + type(exc).__name__ + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
