import os
import tempfile
from pathlib import Path

import yaml

from limen.models import LimenFile


def load_limen_file(path: Path) -> LimenFile:
    raw = yaml.safe_load(path.read_text())
    if raw is None:
        # an empty/whitespace file is corruption, not an empty queue — refuse to load it as
        # None (which would crash downstream); the caller should restore from git/backup.
        raise ValueError(f"{path} is empty or invalid YAML — refusing to load (restore from git HEAD)")
    return LimenFile.model_validate(raw)


def save_limen_file(path: Path, limen: LimenFile) -> None:
    data = limen.model_dump(mode="json", exclude_none=True)
    text = yaml.dump(data, sort_keys=False, default_flow_style=False)
    # ATOMIC write: serialize to a temp file in the same dir, fsync, then os.replace().
    # os.replace is atomic on POSIX, so a crash or a concurrent writer can NEVER leave the
    # queue file truncated/empty — the race that emptied tasks.yaml to 0 bytes on 2026-06-19.
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
