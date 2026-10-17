import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_installed_closeout_uses_its_runtime_python(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    scripts = tmp_path / "runtime/source/scripts"
    scripts.mkdir(parents=True)
    (tmp_path / "runtime/receipt.json").write_text("{}\n")
    shutil.copy2(root / "scripts/no-tasks-on-me.sh", scripts / "no-tasks-on-me.sh")
    (scripts / "session-closeout.py").write_text("import rfc8785; print('runtime-python-ready')\n")
    (tmp_path / "runtime/venv").symlink_to(sys.prefix, target_is_directory=True)
    poisoned = tmp_path / "path"
    poisoned.mkdir()
    python = poisoned / "python3"
    python.write_text("#!/bin/sh\nexit 99\n")
    python.chmod(0o700)
    result = subprocess.run(
        ["/bin/bash", str(scripts / "no-tasks-on-me.sh"), "--session-id", "fixture"],
        env={**os.environ, "PATH": f"{poisoned}:/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout == "runtime-python-ready\n"
