from __future__ import annotations

import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INSTALL = ROOT / "install.sh"


def _write_executable(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(0o755)


def _fake_path(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_executable(
        bin_dir / "git",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "clone" ]]; then
  mkdir -p "$3/cli"
  exit 0
fi
if [[ "${1:-}" == "-C" ]]; then
  exit 0
fi
exit 0
""",
    )
    _write_executable(
        bin_dir / "python3",
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "-m" && "${2:-}" == "venv" ]]; then
  mkdir -p "$3/bin"
  cat > "$3/bin/pip" <<'PIP'
#!/usr/bin/env bash
exit 0
PIP
  chmod +x "$3/bin/pip"
  exit 0
fi
exit 0
""",
    )
    return bin_dir


def _run_install(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    home = tmp_path / "home"
    home.mkdir()
    fake_bin = _fake_path(tmp_path)
    env = {
        **os.environ,
        "HOME": str(home),
        "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        "LIMEN_TARGET": str(tmp_path / "target" / "limen"),
        "LIMEN_LINK": str(home / "limen"),
        "LIMEN_SOURCE": "https://example.invalid/limen.git",
    }
    env.pop("ZDOTDIR", None)
    return subprocess.run(
        ["bash", str(INSTALL), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_default_does_not_mutate_shell_or_wrappers(tmp_path):
    result = _run_install(tmp_path)
    home = tmp_path / "home"

    assert result.returncode == 0, result.stderr
    assert not (home / ".zshenv").exists()
    assert not (home / ".local" / "bin" / "limen").exists()
    assert "skipped host PATH/wrapper mutation" in result.stdout


def test_install_host_mutation_is_explicit_opt_in(tmp_path):
    result = _run_install(tmp_path, "--host-mutation")
    home = tmp_path / "home"

    assert result.returncode == 0, result.stderr
    assert (home / ".zshenv").exists()
    assert (home / ".local" / "bin" / "limen").exists()
    assert "LIMEN_ROOT" in (home / ".zshenv").read_text(encoding="utf-8")
