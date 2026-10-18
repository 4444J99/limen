import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

MARKER = "runtime-python-ready"
RUNTIME_ENV = "LIMEN_TEST_RUNTIME_PYTHON_USED"


def _install_fixture(tmp_path: Path, *, runtime_python: bool, resolver: bool = False) -> tuple[Path, Path]:
    """Build an installed-closeout layout: <runtime>/{receipt.json,source/scripts,venv/bin}.

    The runtime venv python is a hermetic shell wrapper that execs the current
    interpreter, so the test does not depend on how the host Python prefix is
    laid out (system prefixes ship python3, not python) nor on which packages
    that interpreter has installed. The wrapper exports a marker variable that
    only the runtime python can set, and the stub closeout script proves it
    ran under that wrapper rather than under a PATH python3.
    """
    root = Path(__file__).resolve().parents[2]
    scripts = tmp_path / "runtime/source/scripts"
    scripts.mkdir(parents=True)
    (tmp_path / "runtime/receipt.json").write_text("{}\n")
    shutil.copy2(root / "scripts/no-tasks-on-me.sh", scripts / "no-tasks-on-me.sh")
    (scripts / "session-closeout.py").write_text(
        "import os, sys\n"
        f"if os.environ.get({RUNTIME_ENV!r}) != '1':\n"
        "    sys.stderr.write('not launched through the runtime python\\n')\n"
        "    sys.exit(3)\n"
        f"print({MARKER!r})\n"
    )
    if resolver:
        (scripts / "lib").mkdir()
        shutil.copy2(root / "scripts/lib/gate-python.sh", scripts / "lib/gate-python.sh")
    if runtime_python:
        venv_bin = tmp_path / "runtime/venv/bin"
        venv_bin.mkdir(parents=True)
        wrapper = venv_bin / "python"
        wrapper.write_text(f'#!/bin/sh\nexport {RUNTIME_ENV}=1\nexec {shlex.quote(sys.executable)} "$@"\n')
        wrapper.chmod(0o700)
    poisoned = tmp_path / "path"
    poisoned.mkdir()
    python = poisoned / "python3"
    python.write_text("#!/bin/sh\nexit 99\n")
    python.chmod(0o700)
    return scripts, poisoned


def _run_closeout(
    scripts: Path, poisoned: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k != RUNTIME_ENV and not k.startswith("LIMEN_GATE_PYTHON")  # the resolver's own overrides
    }
    env["PATH"] = f"{poisoned}:/usr/bin:/bin"
    env.update(extra_env or {})
    return subprocess.run(
        ["/bin/bash", str(scripts / "no-tasks-on-me.sh"), "--session-id", "fixture"],
        env=env,
        capture_output=True,
        text=True,
        # The script under test returns in about a second; the limit only has to
        # outlast a host running a full xdist suite alongside other sessions.
        timeout=60,
    )


def test_installed_closeout_uses_its_runtime_python(tmp_path: Path) -> None:
    scripts, poisoned = _install_fixture(tmp_path, runtime_python=True)
    result = _run_closeout(scripts, poisoned)
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{MARKER}\n"


def test_closeout_without_runtime_python_falls_back_to_path_python3(tmp_path: Path) -> None:
    # Negative control: with no runtime venv python the script must take the
    # PATH python3 branch, which is poisoned (exit 99). This proves the
    # positive test discriminates between the runtime python and PATH python3.
    scripts, poisoned = _install_fixture(tmp_path, runtime_python=False)
    result = _run_closeout(scripts, poisoned)
    assert result.returncode == 99, result.stderr
    assert MARKER not in result.stdout


def _fake_gate_interpreter(tmp_path: Path) -> Path:
    """An interpreter that satisfies the resolver's `-c 'import yaml'` probe without needing PyYAML.

    The probe is answered with exit 0; any other invocation runs the real interpreter with the marker
    variable set, so the stub proves it was launched through the *resolved* interpreter and not PATH python3.
    """
    fake = tmp_path / "gate-python"
    fake.write_text(
        f'#!/bin/sh\ncase "$1" in -c) exit 0;; esac\nexport {RUNTIME_ENV}=1\nexec {shlex.quote(sys.executable)} "$@"\n'
    )
    fake.chmod(0o700)
    return fake


def test_direct_closeout_uses_the_gate_resolver_not_path_python3(tmp_path: Path) -> None:
    # PATH python3 is poisoned (exit 99) and there is no runtime venv, so only the resolver can make this pass.
    scripts, poisoned = _install_fixture(tmp_path, runtime_python=False, resolver=True)
    fake = _fake_gate_interpreter(tmp_path)
    result = _run_closeout(scripts, poisoned, {"LIMEN_GATE_PYTHON": str(fake)})
    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{MARKER}\n"


def test_direct_closeout_with_no_usable_interpreter_is_unmeasured_not_a_traceback(tmp_path: Path) -> None:
    # Resolver present but nothing it can pick: exit 2 (evidence unavailable), the resolver's own hint, and
    # neither the poisoned PATH python3 (99) nor a ModuleNotFoundError traceback.
    scripts, poisoned = _install_fixture(tmp_path, runtime_python=False, resolver=True)
    result = _run_closeout(scripts, poisoned, {"LIMEN_GATE_PYTHON_CANDIDATES": "no-such-python-anywhere"})
    assert result.returncode == 2, result.stderr
    assert "gate-python:" in result.stderr
    assert "Traceback" not in result.stderr
    assert MARKER not in result.stdout
