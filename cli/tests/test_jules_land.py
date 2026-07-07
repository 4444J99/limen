from __future__ import annotations

import importlib.util
import subprocess
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "jules-land.py"


def load_jules_land():
    spec = importlib.util.spec_from_file_location("jules_land_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_land_one_retains_local_worktree_and_branch_after_pr(monkeypatch, tmp_path: Path) -> None:
    module = load_jules_land()
    repo = tmp_path / "repo"
    repo.mkdir()
    module.WT_ROOT = tmp_path / "worktrees"

    git_calls: list[tuple[str, ...]] = []

    def fake_git(args, cwd, timeout=30):
        git_calls.append(tuple(args))
        if args[:2] == ["worktree", "add"]:
            Path(args[4]).mkdir(parents=True, exist_ok=True)
        if args == ["diff", "--cached", "--quiet"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_run(args, **kwargs):
        if args[:3] == [module.JULES, "remote", "pull"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:3] == ["gh", "pr", "create"]:
            return subprocess.CompletedProcess(args, 0, "https://github.com/organvm/example/pull/42\n", "")
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(module, "_resolve_repo_dir", lambda task: repo)
    monkeypatch.setattr(module, "_default_branch", lambda cwd: "main")
    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.secrets, "token_hex", lambda n: "abcd")

    task = module.Task(
        id="T1",
        title="Ship Jules patch",
        repo="organvm/example",
        target_agent="jules",
        created=date(2026, 7, 6),
    )

    message = module.land_one(task, "123", True)

    assert message.startswith("LANDED T1 -> https://github.com/organvm/example/pull/42")
    assert "local root retained" in message
    assert "branch retained" in message
    assert "generated cleanup removed:0" in message
    assert "worktree-reclaim-acceptance.jsonl" in message
    assert "branch-reap-acceptance.jsonl" in message
    assert module.landed_pr_url(message, "123") == "https://github.com/organvm/example/pull/42"
    assert ("clean", "-Xdf", "--", *module._GENERATED_CLEAN_PATHS) in git_calls
    assert ("worktree", "remove", "--force", str(module.WT_ROOT / "limen_jules-t1-abcd")) not in git_calls
    assert ("branch", "-D", "limen/jules-t1-abcd") not in git_calls
