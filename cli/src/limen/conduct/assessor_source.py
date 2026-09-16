"""Capture the exact reviewed assessor blob as bounded data, never execute it.

The trusted deployment policy supplies the commit and SHA-256. This verifies
integrity, not independent approval. Working-tree files and repository hooks are
not execution inputs; a later launcher must use the returned immutable bytes.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ASSESSOR_PATH = "scripts/dependabot-admission.py"
MAX_SOURCE_BYTES = 256 * 1024


class AssessorSourceError(ValueError):
    """Source is unavailable or does not match the deployment's reviewed pin."""


@dataclass(frozen=True)
class AssessorSnapshot:
    source_commit: str
    script_sha256: str
    source: bytes


def capture_assessor(repository: Path, source_commit: str, script_sha256: str) -> AssessorSnapshot:
    """Read only a regular Git blob from the named commit, with finite bounds."""
    if (
        not isinstance(source_commit, str)
        or not isinstance(script_sha256, str)
        or not re.fullmatch(r"[a-f0-9]{40}", source_commit)
        or not re.fullmatch(r"[a-f0-9]{64}", script_sha256)
    ):
        raise AssessorSourceError("assessor source pin is invalid")
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    environment.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull, GIT_TERMINAL_PROMPT="0")

    def git(*arguments: str) -> bytes:
        result = subprocess.run(
            [
                "git",
                "--no-pager",
                "--no-replace-objects",
                "-C",
                str(repository),
                "-c",
                "core.fsmonitor=false",
                *arguments,
            ],
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if result.returncode:
            raise AssessorSourceError("assessor source is unavailable")
        return result.stdout

    try:
        if git("cat-file", "-t", source_commit).strip() != b"commit":
            raise AssessorSourceError("assessor source must identify a commit")
        row = git("ls-tree", source_commit, "--", ASSESSOR_PATH)
        match = re.fullmatch(rb"100(?:644|755) blob ([a-f0-9]{40})\tscripts/dependabot-admission\.py\n", row)
        if not match:
            raise AssessorSourceError("assessor source must be a regular blob")
        blob = match[1].decode("ascii")
        size = int(git("cat-file", "-s", blob).strip())
        if not 0 < size <= MAX_SOURCE_BYTES:
            raise AssessorSourceError("assessor source exceeds its size bound")
        source = git("cat-file", "blob", blob)
        if len(source) != size or hashlib.sha256(source).hexdigest() != script_sha256:
            raise AssessorSourceError("assessor source digest does not match")
        return AssessorSnapshot(source_commit, script_sha256, source)
    except (OSError, subprocess.SubprocessError, ValueError) as error:
        if isinstance(error, AssessorSourceError):
            raise
        raise AssessorSourceError("assessor source is unmeasured") from None
