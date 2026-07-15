from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.cli import main  # noqa: E402


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stdout}\n{result.stderr}")
    return result


def test_workstream_command_writes_private_kickstart_packet(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--prompt",
            "Ship a bounded packet.",
            str(repo),
            "Demo Packet",
        ],
    )

    assert result.exit_code == 0, result.output
    wt = repo / ".worktrees" / "demo-packet"
    readme = wt / ".limen-workstream" / "README.md"
    intent = wt / ".limen-workstream" / "intent.md"
    kickstart = wt / ".limen-workstream" / "kickstart.sh"
    assert readme.exists()
    assert intent.exists()
    assert kickstart.exists()
    assert "Ship a bounded packet." in intent.read_text(encoding="utf-8")
    assert "Ship a bounded packet." not in readme.read_text(encoding="utf-8")
    assert "bash " in result.output and "kickstart.sh" in result.output
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout


def test_autonomous_workstream_requires_prompt_and_launches_with_dynamic_readme(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    missing = CliRunner().invoke(main, ["workstream", "--autonomous", str(repo), "No Prompt"])
    assert missing.exit_code == 2
    assert "requires --prompt or --prompt-file" in missing.output
    assert not (repo / ".worktrees" / "no-prompt").exists()

    no_readme = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--no-readme",
            "--prompt",
            "This cannot be durable.",
            str(repo),
            "No Readme",
        ],
    )
    assert no_readme.exit_code == 2
    assert "cannot be combined with --no-readme" in no_readme.output
    assert not (repo / ".worktrees" / "no-readme").exists()

    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )

    assert result.exit_code == 0, result.output
    wt = repo / ".worktrees" / "next-epoch"
    capsule = wt / ".limen-workstream"
    readme = capsule / "README.md"
    manifest = capsule / "manifest.md"
    intent = capsule / "intent.md"
    runtime = capsule / "runtime.md"
    closeout = capsule / "closeout.md"
    kickstart = capsule / "kickstart.sh"
    readme_text = readme.read_text(encoding="utf-8")
    manifest_text = manifest.read_text(encoding="utf-8")
    intent_text = intent.read_text(encoding="utf-8")
    runtime_text = runtime.read_text(encoding="utf-8")
    kickstart_text = kickstart.read_text(encoding="utf-8")
    assert "Derive the next safe leaf from live receipts." in intent_text
    assert "Derive the next safe leaf from live receipts." not in readme_text
    assert "Autonomous: `yes`" in manifest_text
    assert "Runtime decision contract" in runtime_text
    assert "Reality determines the state" in runtime_text
    assert "Workstream: `substrate`" in manifest_text
    for module in (manifest, intent, runtime, closeout):
        assert module.exists()
        assert module.name in readme_text
    assert "IFS= read -r -d '' capsule_prompt" in kickstart_text
    assert 'exec codex "$capsule_prompt"' in kickstart_text
    assert str(readme) in kickstart_text
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout

    capsule_files = (readme, manifest, intent, runtime, closeout, kickstart)
    bytes_before = {path: path.read_bytes() for path in capsule_files}
    mtimes_before = {path: path.stat().st_mtime_ns for path in capsule_files}
    repeated = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )
    assert repeated.exit_code == 0, repeated.output
    assert "capsule index:" in repeated.output and "(unchanged)" in repeated.output
    assert {path: path.read_bytes() for path in capsule_files} == bytes_before
    assert {path: path.stat().st_mtime_ns for path in capsule_files} == mtimes_before

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        '#!/usr/bin/env bash\nprintf "%s" "$1" > "$SESSION_PROMPT_CAPTURE"\n',
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    prompt_capture = tmp_path / "prompt.txt"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SESSION_PROMPT_CAPTURE": str(prompt_capture),
    }
    launched = subprocess.run(["bash", str(kickstart)], cwd=wt, env=env, text=True, capture_output=True)
    assert launched.returncode == 0, launched.stderr
    launched_prompt = prompt_capture.read_text(encoding="utf-8")
    assert launched_prompt == readme_text
    assert "intent.md" in launched_prompt

    runtime.unlink()
    invalid = subprocess.run(["bash", str(kickstart)], cwd=wt, env=env, text=True, capture_output=True)
    assert invalid.returncode == 2
    assert "invalid capsule: missing or empty module" in invalid.stderr
