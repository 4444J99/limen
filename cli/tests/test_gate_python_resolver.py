"""The gate rail must resolve a PyYAML-capable python regardless of the caller's PATH.

Regression for 2026-10-16: an agent shell's first ``python3`` was Homebrew 3.15 (no PyYAML), so
``scripts/verify-scoped.sh`` died with ``ModuleNotFoundError: No module named 'yaml'`` while a
Terminal (different PATH) passed. Each case runs the real wrapper with PATH restricted to a temp dir.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCOPED = ROOT / "scripts" / "verify-scoped.sh"
VERIFY = ROOT / "scripts" / "verify.py"

FAKE_NO_YAML = """#!/bin/sh
echo "Traceback (most recent call last):" >&2
echo "ModuleNotFoundError: No module named 'yaml'" >&2
exit 1
"""


def _real_python_has_yaml() -> bool:
    return subprocess.run([sys.executable, "-c", "import yaml"], capture_output=True).returncode == 0


needs_yaml = pytest.mark.skipif(not _real_python_has_yaml(), reason="test interpreter lacks PyYAML")


def _make_path_dir(tmp_path: Path) -> Path:
    """A bin dir holding only `dirname` (the wrapper's one external dependency) and a yaml-less python3."""

    bindir = tmp_path / "bin"
    bindir.mkdir()
    dirname = shutil.which("dirname")
    assert dirname
    (bindir / "dirname").symlink_to(dirname)
    fake = bindir / "python3"
    fake.write_text(FAKE_NO_YAML)
    fake.chmod(0o755)
    return bindir


def _run_scoped(bindir: Path, *args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": str(bindir)}
    env.update(extra_env or {})
    return subprocess.run(
        ["/bin/bash", str(SCOPED), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_no_pyyaml_python_fails_with_hint_never_a_traceback(tmp_path: Path) -> None:
    result = _run_scoped(_make_path_dir(tmp_path), "--help")

    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Traceback" not in combined
    assert "ModuleNotFoundError" not in combined
    assert "no interpreter on PATH can import PyYAML" in result.stderr
    assert "LIMEN_GATE_PYTHON" in result.stderr
    assert "pip install PyYAML" in result.stderr


@needs_yaml
def test_resolves_a_pyyaml_python_when_bare_python3_lacks_it(tmp_path: Path) -> None:
    bindir = _make_path_dir(tmp_path)
    # python3 on PATH is the yaml-less fake; a yaml-capable interpreter exists only under another name.
    alt = bindir / "python3.13"
    alt.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    alt.chmod(0o755)

    result = _run_scoped(bindir, "--help")

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stdout + result.stderr
    assert "usage:" in result.stdout.lower()


@needs_yaml
def test_explicit_override_wins_over_a_broken_path(tmp_path: Path) -> None:
    result = _run_scoped(_make_path_dir(tmp_path), "--help", extra_env={"LIMEN_GATE_PYTHON": sys.executable})

    assert result.returncode == 0, result.stdout + result.stderr
    assert "usage:" in result.stdout.lower()


def test_broken_override_is_reported_and_not_trusted(tmp_path: Path) -> None:
    bindir = _make_path_dir(tmp_path)
    result = _run_scoped(bindir, "--help", extra_env={"LIMEN_GATE_PYTHON": str(bindir / "python3")})

    assert result.returncode != 0
    assert "cannot import yaml; ignoring it" in result.stderr
    assert "Traceback" not in result.stdout + result.stderr


@needs_yaml
def test_spawned_gate_commands_inherit_the_resolved_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """verify.py pins bare python3 for the whole gate subtree, so sub-gates stop re-resolving it."""

    bindir = _make_path_dir(tmp_path)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("LIMEN_GATE_PYTHON", "")  # registers restore: the shim helper writes os.environ directly
    spec = importlib.util.spec_from_file_location("verify_gate_python_uut", VERIFY)
    assert spec and spec.loader
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)

    shim_dir = verify.install_gate_python_shim(sys.executable)
    try:
        # What run_command does: `bash -c <registry command>` under the mutated environment.
        out = subprocess.run(
            ["bash", "-c", 'python3 -c "import sys, yaml; print(sys.executable)"'],
            env=os.environ.copy(),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert out.returncode == 0, out.stdout + out.stderr
        assert os.path.realpath(out.stdout.strip()) == os.path.realpath(sys.executable)
        assert os.environ["LIMEN_GATE_PYTHON"] == sys.executable
    finally:
        shutil.rmtree(shim_dir, ignore_errors=True)


RESOLVER = ROOT / "scripts" / "lib" / "gate-python.sh"

# Answers the two import probes the resolver issues: yaml-only passes the narrow probe, fails the full one.
FAKE_YAML_ONLY = """#!/bin/sh
case "$*" in
  *"import yaml, pytest, ruff"*) exit 1 ;;
  *"import yaml"*) exit 0 ;;
esac
exit 1
"""
FAKE_FULL = """#!/bin/sh
exit 0
"""


def _resolve(path: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {"PATH": path}
    env.update(extra_env or {})
    return subprocess.run(
        ["/bin/bash", "-c", f'source "{RESOLVER}"; limen_gate_python'],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_prefers_the_full_toolchain_even_when_it_is_shadowed_on_path(tmp_path: Path) -> None:
    """Regression: Homebrew's python3.13 (PyYAML only) shadowed /usr/local's (yaml+pytest+ruff) on PATH,
    so a first-hit-only resolver picked the one whose ruff-lint/ruff-format gates cannot run."""

    first, second = tmp_path / "first", tmp_path / "second"
    for directory, body in ((first, FAKE_YAML_ONLY), (second, FAKE_FULL)):
        directory.mkdir()
        fake = directory / "python3.13"
        fake.write_text(body)
        fake.chmod(0o755)

    result = _resolve(f"{first}{os.pathsep}{second}")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(second / "python3.13")


def test_falls_back_to_a_pyyaml_only_interpreter_and_says_so(tmp_path: Path) -> None:
    fake = tmp_path / "python3.13"
    fake.write_text(FAKE_YAML_ONLY)
    fake.chmod(0o755)

    result = _resolve(str(tmp_path))

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(fake)
    assert "PyYAML only" in result.stderr
