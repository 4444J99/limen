"""Fresh-shell regression coverage for issue 2984; no live whole-system workloads."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def environment(tmp_path: Path) -> dict[str, str]:
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("dirname", "bash"):
        target = shutil.which(name)
        assert target
        (bindir / name).symlink_to(target)
    first = bindir / "python3"
    first.write_text("#!/bin/sh\necho wrong-PATH-python >&2\nexit 97\n")
    first.chmod(0o755)
    alternate = bindir / "python3.13"
    alternate.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    alternate.chmod(0o755)
    return {"PATH": str(bindir), "PYTHONDONTWRITEBYTECODE": "1"}


@pytest.mark.parametrize("mode", ["--list", "--explain"])
def test_selection_resolves_python_without_exported_override(tmp_path: Path, mode: str) -> None:
    args = ["/bin/bash", str(ROOT / "scripts/verify-select.sh"), mode]
    if mode == "--explain":
        args.append("AGENTS.md")
    result = subprocess.run(args, env=environment(tmp_path), capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "agent-docs" in result.stdout
    assert "wrong-PATH-python" not in result.stderr


def test_selection_rejects_execution_mode(tmp_path: Path) -> None:
    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts/verify-select.sh"), "--changed"],
        env=environment(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 64
    assert "Usage:" in result.stderr


@pytest.mark.parametrize("succeeds", [True, False])
def test_hermetic_runner_resolves_after_scrub_and_preserves_status(tmp_path: Path, succeeds: bool) -> None:
    env = environment(tmp_path)
    env.update({"LIMEN_OPERATOR_PRIVATE": "must disappear", "LIMEN_GATE_PYTHON": "/missing/python"})
    case = tmp_path / "test_isolation.py"
    case.write_text(
        "import os, sys\n"
        "def test_isolation():\n"
        "    assert 'LIMEN_OPERATOR_PRIVATE' not in os.environ\n"
        "    assert 'LIMEN_GATE_PYTHON' not in os.environ\n"
        "    assert os.environ['LIMEN_NOTIFY'] == '0'\n"
        "    assert os.environ['GIT_CONFIG_GLOBAL'] == '/dev/null'\n"
        "    assert os.environ['GIT_CONFIG_SYSTEM'] == '/dev/null'\n"
        "    assert os.environ['XDG_CONFIG_HOME'] == '/dev/null'\n"
        "    assert os.environ['GIT_EDITOR'] == 'true'\n"
        f"    assert os.path.realpath(sys.executable) == {os.path.realpath(sys.executable)!r}\n"
        f"    assert os.environ['PYTHONPATH'].split(os.pathsep)[0] == {str(ROOT / 'cli/src')!r}\n"
        f"    assert {succeeds!r}\n"
    )
    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts/run-pytest-hermetic.sh"), str(case), "-q", "-p", "no:cacheprovider"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == (0 if succeeds else 1), result.stdout + result.stderr
    assert "wrong-PATH-python" not in result.stderr


def test_hermetic_runner_rejects_yaml_only_candidate(tmp_path: Path) -> None:
    env = environment(tmp_path)
    candidate = Path(env["PATH"]) / "python3.13"
    candidate.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        '  *"import yaml, pytest, ruff"*) exit 1 ;;\n'
        '  *"import yaml"*) exit 0 ;;\n'
        "esac\nexit 1\n"
    )
    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts/run-pytest-hermetic.sh"), "--version"],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "resolved interpreter lacks pytest" in result.stderr


def test_selection_forwards_parser_failure(tmp_path: Path) -> None:
    result = subprocess.run(
        ["/bin/bash", str(ROOT / "scripts/verify-select.sh"), "--list", "--invalid-option"],
        env=environment(tmp_path), capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_whole_uses_resolved_python_before_first_controlled_failure(tmp_path: Path) -> None:
    env = environment(tmp_path)
    env["LIMEN_VERIFY_NO_LOCK"] = "1"
    fixture = tmp_path / "repo"
    scripts = fixture / "scripts"
    (scripts / "lib").mkdir(parents=True)
    shutil.copy(ROOT / "scripts/verify-whole.sh", scripts / "verify-whole.sh")
    shutil.copy(ROOT / "scripts/lib/gate-python.sh", scripts / "lib/gate-python.sh")
    (scripts / "lib/host-admission.sh").write_text(
        "host_admission_acquire() { return 0; }\nhost_admission_exit_trap() { :; }\n"
    )
    (scripts / "verify.py").write_text(
        "import sys, yaml\n"
        "assert sys.argv[1:] == ['--print-files', 'py-syntax']\n"
        "print('controlled_failure.py')\n"
    )
    (fixture / "controlled_failure.py").write_text("def invalid syntax\n")
    result = subprocess.run(
        ["/bin/bash", str(scripts / "verify-whole.sh")], cwd=fixture,
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert "SyntaxError" in result.stderr
    assert "wrong-PATH-python" not in result.stderr
    assert "Validate Cvrsvs" not in result.stdout
