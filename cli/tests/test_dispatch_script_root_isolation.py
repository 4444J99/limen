"""Dispatch verification and healing must stay in the checkout that owns the scripts."""

import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFY_SCRIPT = "verify-dispatch.py"
HEAL_SCRIPT = "heal-dispatch.py"


def _make_checkout(path: Path, *, scripts: bool = False) -> Path:
    (path / "logs").mkdir(parents=True)
    (path / "tasks.yaml").write_text("tasks: []\n", encoding="utf-8")
    if scripts:
        (path / "scripts").mkdir()
        for name in (VERIFY_SCRIPT, HEAL_SCRIPT):
            shutil.copy2(REPO_ROOT / "scripts" / name, path / "scripts" / name)
    return path


def _run(script: Path, *args: str, env: dict[str, str], cwd: Path) -> None:
    result = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, (
        f"{script.name} exited {result.returncode}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )


def _run_verify_then_heal(checkout: Path, *, env: dict[str, str], cwd: Path) -> None:
    _run(checkout / "scripts" / VERIFY_SCRIPT, "--quiet", env=env, cwd=cwd)
    _run(checkout / "scripts" / HEAL_SCRIPT, env=env, cwd=cwd)


def _base_env(home: Path) -> dict[str, str]:
    env = dict(os.environ)
    env.pop("LIMEN_ROOT", None)
    env.pop("LIMEN_TASKS", None)
    env.pop("LIMEN_QUEUE_LOCK_HELD", None)
    env["HOME"] = str(home)
    # Changing HOME also changes Python's user-site lookup. Preserve the interpreter's
    # already-resolved import paths so the copied scripts still see their normal dependencies.
    import_paths = [str(REPO_ROOT / "cli" / "src"), *(path for path in sys.path if path)]
    env["PYTHONPATH"] = os.pathsep.join(import_paths)
    return env


def test_dispatch_scripts_default_to_their_own_checkout(tmp_path: Path) -> None:
    checkout = _make_checkout(tmp_path / "isolated-checkout", scripts=True)
    decoy_home = tmp_path / "home"
    decoy_live_root = _make_checkout(decoy_home / "Workspace" / "limen")
    unrelated_cwd = tmp_path / "unrelated-cwd"
    unrelated_cwd.mkdir()

    _run_verify_then_heal(
        checkout,
        env=_base_env(decoy_home),
        cwd=unrelated_cwd,
    )

    assert (checkout / "logs" / "dispatch-verify.json").exists()
    assert not (decoy_live_root / "logs" / "dispatch-verify.json").exists()


def test_explicit_limen_root_override_wins(tmp_path: Path) -> None:
    checkout = _make_checkout(tmp_path / "isolated-checkout", scripts=True)
    override_root = _make_checkout(tmp_path / "explicit-root")
    decoy_home = tmp_path / "home"
    decoy_live_root = _make_checkout(decoy_home / "Workspace" / "limen")
    unrelated_cwd = tmp_path / "unrelated-cwd"
    unrelated_cwd.mkdir()
    env = _base_env(decoy_home)
    env["LIMEN_ROOT"] = str(override_root)

    _run_verify_then_heal(checkout, env=env, cwd=unrelated_cwd)

    assert (override_root / "logs" / "dispatch-verify.json").exists()
    assert not (checkout / "logs" / "dispatch-verify.json").exists()
    assert not (decoy_live_root / "logs" / "dispatch-verify.json").exists()
