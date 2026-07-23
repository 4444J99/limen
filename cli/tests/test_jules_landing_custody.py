from __future__ import annotations

import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

import limen.jules_landing_custody as custody


def load_jules_land():
    return custody


def test_land_one_retains_local_worktree_and_branch_after_pr(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    repo = tmp_path / "repo"
    repo.mkdir()
    module.WT_ROOT = tmp_path / "worktrees"

    git_calls: list[tuple[str, ...]] = []
    state = {"pulled": False, "committed": False, "pr": False}

    def fake_git(args, cwd, timeout=30):
        git_calls.append(tuple(args))
        if args[:2] == ["ls-remote", "--exit-code"]:
            return subprocess.CompletedProcess(args, 2, "", "")
        if args[:2] == ["show-ref", "--verify"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:2] == ["worktree", "add"]:
            Path(args[4]).mkdir(parents=True, exist_ok=True)
        if args == ["status", "--porcelain"]:
            dirty = state["pulled"] and not state["committed"]
            return subprocess.CompletedProcess(
                args,
                0,
                " M patch.py\n" if dirty else "",
                "",
            )
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "commit\n" if state["committed"] else "base\n",
                "",
            )
        if args == ["rev-parse", "origin/main"]:
            return subprocess.CompletedProcess(args, 0, "base\n", "")
        if args == ["diff", "--cached", "--quiet"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        if "commit" in args:
            state["committed"] = True
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_run(args, **kwargs):
        if args[:3] == [module.JULES, "remote", "pull"]:
            state["pulled"] = True
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "commit\n", "")
        if args[:3] == ["gh", "pr", "list"]:
            rows = (
                [
                    {
                        "url": "https://github.com/organvm/example/pull/42",
                        "state": "OPEN",
                        "mergedAt": None,
                        "headRefName": module.landing_branch("T1", "123"),
                        "headRefOid": "commit",
                        "headRepositoryOwner": {"login": "organvm"},
                    }
                ]
                if state["pr"]
                else []
            )
            return subprocess.CompletedProcess(args, 0, json.dumps(rows), "")
        if args[:3] == ["gh", "pr", "create"]:
            state["pr"] = True
            return subprocess.CompletedProcess(
                args,
                0,
                "https://github.com/organvm/example/pull/42\n",
                "",
            )
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(module, "_resolve_repo_dir", lambda task: repo)
    monkeypatch.setattr(module, "_default_branch", lambda cwd: "main")
    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module.subprocess, "run", fake_run)

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
    branch = module.landing_branch("T1", "123")
    worktree = module.WT_ROOT / branch.replace("/", "_")
    assert ("worktree", "remove", "--force", str(worktree)) not in git_calls
    assert ("branch", "-D", branch) not in git_calls


def test_land_one_existing_remote_branch_creates_missing_pr(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    repo = tmp_path / "repo"
    repo.mkdir()
    module.WT_ROOT = tmp_path / "worktrees"
    creates = 0
    pr_exists = False
    branch = module.landing_branch("T-REMOTE", "123")

    def fake_git(args, cwd, timeout=30):
        if args[:2] == ["ls-remote", "--exit-code"]:
            return subprocess.CompletedProcess(args, 0, "remote-sha\n", "")
        if args[:2] == ["worktree", "add"] or args[:2] == ["push", "-u"]:
            raise AssertionError(f"remote retry must not repeat local mutation: {args}")
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_run(args, **kwargs):
        nonlocal creates, pr_exists
        if args[:3] == ["gh", "pr", "list"]:
            rows = (
                [
                    {
                        "url": "https://github.com/organvm/example/pull/62",
                        "state": "OPEN",
                        "mergedAt": None,
                        "headRefName": branch,
                        "headRefOid": "remote-sha",
                        "headRepositoryOwner": {"login": "organvm"},
                    }
                ]
                if pr_exists
                else []
            )
            return subprocess.CompletedProcess(args, 0, json.dumps(rows), "")
        if args[:3] == ["gh", "pr", "create"]:
            creates += 1
            pr_exists = True
            return subprocess.CompletedProcess(
                args,
                0,
                "https://github.com/organvm/example/pull/62\n",
                "",
            )
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(module, "_resolve_repo_dir", lambda task: repo)
    monkeypatch.setattr(module, "_default_branch", lambda cwd: "main")
    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    task = module.Task(
        id="T-REMOTE",
        title="resume pushed branch",
        repo="organvm/example",
        target_agent="jules",
        created=date(2026, 7, 17),
    )

    message = module.land_one(task, "123", True)

    assert message.startswith("LANDED T-REMOTE -> https://github.com/organvm/example/pull/62")
    assert creates == 1


def test_land_one_resumes_retained_committed_branch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    repo = tmp_path / "repo"
    repo.mkdir()
    module.WT_ROOT = tmp_path / "worktrees"
    branch = module.landing_branch("T-LOCAL", "123")
    worktree = module.WT_ROOT / branch.replace("/", "_")
    worktree.mkdir(parents=True)
    git_calls: list[tuple[str, ...]] = []
    pr_exists = False

    def fake_git(args, cwd, timeout=30):
        git_calls.append(tuple(args))
        if args[:2] == ["ls-remote", "--exit-code"]:
            return subprocess.CompletedProcess(args, 2, "", "")
        if args[:3] == ["symbolic-ref", "--quiet", "--short"]:
            return subprocess.CompletedProcess(args, 0, f"{branch}\n", "")
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, "commit\n", "")
        if args == ["rev-parse", "origin/main"]:
            return subprocess.CompletedProcess(args, 0, "base\n", "")
        if args == ["log", "-1", "--format=%B"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "resume retained branch\n\nlimen task T-LOCAL (jules session 123)\n",
                "",
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_run(args, **kwargs):
        nonlocal pr_exists
        if args[:3] == ["gh", "pr", "list"]:
            rows = (
                [
                    {
                        "url": "https://github.com/organvm/example/pull/63",
                        "state": "OPEN",
                        "mergedAt": None,
                        "headRefName": branch,
                        "headRefOid": "commit",
                        "headRepositoryOwner": {"login": "organvm"},
                    }
                ]
                if pr_exists
                else []
            )
            return subprocess.CompletedProcess(args, 0, json.dumps(rows), "")
        if args[:3] == ["gh", "pr", "create"]:
            pr_exists = True
            return subprocess.CompletedProcess(
                args,
                0,
                "https://github.com/organvm/example/pull/63\n",
                "",
            )
        if args[:3] == [module.JULES, "remote", "pull"]:
            raise AssertionError("committed retained branch must not pull the patch again")
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(module, "_resolve_repo_dir", lambda task: repo)
    monkeypatch.setattr(module, "_default_branch", lambda cwd: "main")
    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    task = module.Task(
        id="T-LOCAL",
        title="resume retained branch",
        repo="organvm/example",
        target_agent="jules",
        created=date(2026, 7, 17),
    )

    message = module.land_one(task, "123", True)

    assert message.startswith("LANDED T-LOCAL -> https://github.com/organvm/example/pull/63")
    assert ("push", "-u", "origin", branch) in git_calls
    assert all(call[:2] != ("worktree", "add") for call in git_calls)


@pytest.mark.parametrize(
    ("state", "merged_at", "prefix"),
    [
        ("CLOSED", None, "BLOCKED"),
        ("MERGED", "2026-07-17T00:00:00Z", "LANDED"),
    ],
)
def test_pr_adoption_requires_open_or_merged_exact_head(
    state: str,
    merged_at: str | None,
    prefix: str,
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    repo = tmp_path / "repo"
    repo.mkdir()
    branch = module.landing_branch("T-PR-STATE", "123")

    def fake_run(args, **kwargs):
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(args, 0, "commit\n", "")
        if args[:3] != ["gh", "pr", "list"]:
            raise AssertionError(f"unexpected mutation for existing PR: {args}")
        return subprocess.CompletedProcess(
            args,
            0,
            json.dumps(
                [
                    {
                        "url": "https://github.com/organvm/example/pull/70",
                        "state": state,
                        "mergedAt": merged_at,
                        "headRefName": branch,
                        "headRefOid": "commit",
                        "headRepositoryOwner": {"login": "organvm"},
                    }
                ]
            ),
            "",
        )

    monkeypatch.setattr(
        module,
        "_resolve_repo_dir",
        lambda task: pytest.fail("remote PR custody must not require a local checkout"),
    )
    monkeypatch.setattr(
        module,
        "_git",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("existing PR lookup should decide before git mutation")
        ),
    )
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    task = module.Task(
        id="T-PR-STATE",
        title="validate PR state",
        repo="organvm/example",
        target_agent="jules",
        created=date(2026, 7, 17),
    )

    message = module.land_one(task, "123", True)

    assert message.startswith(f"{prefix} T-PR-STATE")
    if state == "CLOSED":
        assert "closed-unmerged" in message


def test_pr_adoption_rejects_same_branch_from_fork_owner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    branch = module.landing_branch("T-FORK", "123")

    def fake_run(args, **kwargs):
        if args[:2] == ["gh", "api"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "current-target-head\n",
                "",
            )
        assert args[:3] == ["gh", "pr", "list"]
        return subprocess.CompletedProcess(
            args,
            0,
            json.dumps(
                [
                    {
                        "number": 71,
                        "url": "https://github.com/organvm/example/pull/71",
                        "state": "OPEN",
                        "mergedAt": None,
                        "headRefName": branch,
                        "headRefOid": "fork-head",
                        "headRepositoryOwner": {"login": "someone-else"},
                    },
                    {
                        "number": 70,
                        "url": "https://github.com/organvm/example/pull/70",
                        "state": "OPEN",
                        "mergedAt": None,
                        "headRefName": branch,
                        "headRefOid": "stale-target-head",
                        "headRepositoryOwner": {"login": "organvm"},
                    },
                ]
            ),
            "",
        )

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_resolve_repo_dir", lambda task: None)
    task = module.Task(
        id="T-FORK",
        title="reject fork owner",
        repo="organvm/example",
        target_agent="jules",
        created=date(2026, 7, 17),
    )

    message = module.land_one(task, "123", True)

    assert message == "BLOCKED T-FORK: no local checkout of organvm/example"
    assert "/pull/71" not in message
    assert "/pull/70" not in message


def test_failed_jules_pull_is_a_blocker_without_partial_commit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    repo = tmp_path / "repo"
    repo.mkdir()
    module.WT_ROOT = tmp_path / "worktrees"
    git_calls: list[tuple[str, ...]] = []

    def fake_git(args, cwd, timeout=30):
        git_calls.append(tuple(args))
        if args[:2] == ["ls-remote", "--exit-code"]:
            return subprocess.CompletedProcess(args, 2, "", "")
        if args[:2] == ["show-ref", "--verify"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[:2] == ["worktree", "add"]:
            Path(args[4]).mkdir(parents=True, exist_ok=True)
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args == ["rev-parse", "HEAD"] or args == ["rev-parse", "origin/main"]:
            return subprocess.CompletedProcess(args, 0, "base\n", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_run(args, **kwargs):
        if args[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if args[:3] == [module.JULES, "remote", "pull"]:
            return subprocess.CompletedProcess(args, 1, "", "partial pull")
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(module, "_resolve_repo_dir", lambda task: repo)
    monkeypatch.setattr(module, "_default_branch", lambda cwd: "main")
    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    task = module.Task(
        id="T-PULL-FAIL",
        title="failed pull",
        repo="organvm/example",
        target_agent="jules",
        created=date(2026, 7, 17),
    )

    message = module.land_one(task, "123", True)

    assert message.startswith("BLOCKED T-PULL-FAIL: Jules pull failed")
    assert ("add", "-A") not in git_calls
    assert all("commit" not in call for call in git_calls)


def test_retained_dirty_worktree_is_never_auto_committed(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = load_jules_land()
    repo = tmp_path / "repo"
    repo.mkdir()
    module.WT_ROOT = tmp_path / "worktrees"
    branch = module.landing_branch("T-DIRTY", "123")
    worktree = module.WT_ROOT / branch.replace("/", "_")
    worktree.mkdir(parents=True)

    def fake_git(args, cwd, timeout=30):
        if args[:2] == ["ls-remote", "--exit-code"]:
            return subprocess.CompletedProcess(args, 2, "", "")
        if args[:3] == ["symbolic-ref", "--quiet", "--short"]:
            return subprocess.CompletedProcess(args, 0, f"{branch}\n", "")
        if args == ["status", "--porcelain"]:
            return subprocess.CompletedProcess(args, 0, " M partial.py\n", "")
        if args == ["add", "-A"] or "commit" in args:
            raise AssertionError(f"dirty retained worktree must not mutate: {args}")
        return subprocess.CompletedProcess(args, 0, "", "")

    def fake_run(args, **kwargs):
        if args[:3] == ["gh", "pr", "list"]:
            return subprocess.CompletedProcess(args, 0, "[]", "")
        if args[:3] == [module.JULES, "remote", "pull"]:
            raise AssertionError("dirty retained worktree must not pull again")
        raise AssertionError(f"unexpected subprocess: {args}")

    monkeypatch.setattr(module, "_resolve_repo_dir", lambda task: repo)
    monkeypatch.setattr(module, "_default_branch", lambda cwd: "main")
    monkeypatch.setattr(module, "_git", fake_git)
    monkeypatch.setattr(module.subprocess, "run", fake_run)
    task = module.Task(
        id="T-DIRTY",
        title="dirty retained state",
        repo="organvm/example",
        target_agent="jules",
        created=date(2026, 7, 17),
    )

    message = module.land_one(task, "123", True)

    assert message.startswith("BLOCKED T-DIRTY: retained worktree")
    assert "dirty" in message
