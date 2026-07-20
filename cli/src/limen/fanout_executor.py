"""Dynamic provider launch and exact-receipt landing for direct-session fanout."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import fcntl
import urllib.parse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, cast

from limen.conduct.models import (
    CheckEvidenceV1,
    ConductorSessionV1,
    ExecutorAttemptV1,
    PredicateEvidenceV1,
    RunReceiptV1,
    canonical_hash,
)
from limen.conduct.client import HttpConductClient, client_from_env
from limen.jules_remote import probe_jules_remote_sessions


CODE_RECEIPT_CAPABILITIES = frozenset(
    {
        "code",
        "exact-base-receipt",
        "exact-diff-receipt",
        "exact-head-receipt",
        "predicate-receipt",
        "pull-request-receipt",
    }
)
_SESSION_ID_RE = re.compile(r"\b(\d{12,64})\b")
_CODEX_TASK_RE = re.compile(r"\b(task_[A-Za-z0-9_]+)\b")
_URL_RE = re.compile(r"https://[^\s]+")
_TERMINAL_ATTEMPT_STATES = frozenset({"succeeded", "failed", "blocked"})


class FanoutExecutionError(RuntimeError):
    """A provider launch, probe, or landing failed closed."""


class TransientFanoutExecutionError(FanoutExecutionError):
    """A bounded retry or another live executor may clear this failure."""


class StaleResultError(FanoutExecutionError):
    """A provider result no longer matches the packet's exact remote heads."""


class AmbiguousProviderLaunchError(FanoutExecutionError):
    """A launch may have reached the provider but returned no durable identity."""


@dataclass(frozen=True)
class ProviderLaunch:
    provider_run_id: str
    provider_run_url: str


@dataclass(frozen=True)
class ProviderState:
    status: str
    detail: str = ""
    failure_class: str | None = None


@dataclass(frozen=True)
class ExecutionLane:
    primary: ExecutionAdapter
    adapters: tuple[ExecutionAdapter, ...]
    client: Any


class ExecutionAdapter(Protocol):
    name: str
    transport: str
    local_heavy: bool
    concurrency: int
    receipt_quality: float
    cost_per_run: float | None
    quota_remaining: float | None
    capabilities: frozenset[str]
    conduct_token_env: str
    worker_env_allowlist: frozenset[str]

    def eligible(self, packet: dict[str, Any]) -> bool: ...

    def launch(self, packet: dict[str, Any], attempt_id: str) -> ProviderLaunch: ...

    def recover(self, packet: dict[str, Any], attempt_id: str) -> ProviderLaunch | None: ...

    def probe(self, provider_run_id: str) -> ProviderState: ...

    def land(
        self,
        node: dict[str, Any],
        attempt: ExecutorAttemptV1,
        *,
        capability_token: str,
        client: Any,
    ) -> RunReceiptV1: ...


def _run(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AmbiguousProviderLaunchError(f"{command[0]} timed out after submission may have begun") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise FanoutExecutionError(f"{command[0]} execution failed: {exc}") from exc


def _checked(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = 120,
    input_text: str | None = None,
) -> str:
    completed = _run(command, cwd=cwd, timeout=timeout, input_text=input_text)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or f"exit {completed.returncode}").strip()
        raise FanoutExecutionError(f"{shlex.join(command[:4])} failed: {detail[-1200:]}")
    return completed.stdout


def _provider_prompt(packet: dict[str, Any], attempt_id: str) -> str:
    if packet.get("effect") != "write":
        raise FanoutExecutionError("code-generation adapters accept write leaves only")
    execution = packet["execution"]
    allowed = "\n".join(f"- {path}" for path in packet["authority"]["path_prefixes"])
    return (
        f"[limen-fanout:{attempt_id}]\n"
        "Implement this directly. Do not ask for feedback or approval. Limen will create the pull request.\n"
        f"Repository: {execution['owner_repository']}\n"
        f"Exact base: {execution['exact_base']}\n"
        f"Topic branch receipt target: {execution['topic_branch']}\n"
        f"Intended effect: {packet['intent']['intended_effect']}\n"
        "You may change only these repository-relative paths:\n"
        f"{allowed}\n"
        f"Completion predicate: {packet['predicate']}\n"
        "Do not edit tasks.yaml. Keep the patch bounded and leave the repository ready for the predicate."
    )


def _attempt_from(
    node: dict[str, Any],
    *,
    attempt_id: str,
    adapter: str,
    status: Literal["launching", "submitted", "running", "succeeded", "failed", "blocked"],
    provider_run_id: str | None = None,
    provider_run_url: str | None = None,
    submitted_at: datetime | str | None = None,
    detail: str = "",
) -> ExecutorAttemptV1:
    lease = node["lease"]
    executor = lease["executor"]
    when = submitted_at or lease["acquired_at"]
    if isinstance(when, str):
        when = datetime.fromisoformat(when.replace("Z", "+00:00"))
    return ExecutorAttemptV1(
        attempt_id=attempt_id,
        run_id=node["run_id"],
        lease_id=lease["lease_id"],
        lease_generation=lease["generation"],
        executor=executor,
        adapter=adapter,
        provider_run_id=provider_run_id,
        provider_run_url=provider_run_url,
        status=status,
        submitted_at=when,
        updated_at=datetime.now(timezone.utc),
        detail=detail[:4096],
    )


def _changed_paths(repo: Path, base: str, head: str = "HEAD") -> tuple[str, ...]:
    output = _checked(["git", "diff", "--name-only", "-z", base, head], cwd=repo)
    return tuple(sorted(path for path in output.split("\0") if path))


def _working_tree_changed_paths(repo: Path, base: str) -> tuple[str, ...]:
    """Return tracked, deleted, staged, and untracked paths relative to exact base."""

    tracked = _checked(["git", "diff", "--name-only", "-z", base, "--"], cwd=repo)
    untracked = _checked(["git", "ls-files", "--others", "--exclude-standard", "-z"], cwd=repo)
    return tuple(sorted({path for path in (tracked + untracked).split("\0") if path}))


def _authorized_paths(changed: tuple[str, ...], allowed: tuple[str, ...]) -> bool:
    return all(
        any(prefix == "." or path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in allowed)
        for path in changed
    )


def _default_branch(repository: str) -> str:
    output = _checked(
        ["gh", "repo", "view", repository, "--json", "defaultBranchRef", "--jq", ".defaultBranchRef.name"],
        timeout=120,
    ).strip()
    if not output:
        raise FanoutExecutionError(f"{repository} has no default branch receipt")
    return output


def remote_default_head(repository: str) -> str:
    branch = _default_branch(repository)
    output = _checked(
        ["gh", "api", f"repos/{repository}/git/ref/heads/{branch}", "--jq", ".object.sha"],
        timeout=120,
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", output):
        raise FanoutExecutionError(f"{repository} returned no exact default head")
    return output


def remote_branch_head(repository: str, branch: str) -> str:
    encoded = urllib.parse.quote(branch, safe="")
    output = _checked(
        ["gh", "api", f"repos/{repository}/git/ref/heads/{encoded}", "--jq", ".object.sha"],
        timeout=120,
    ).strip()
    if not re.fullmatch(r"[0-9a-f]{40,64}", output):
        raise FanoutExecutionError(f"{repository}:{branch} returned no exact remote head")
    return output


def _assert_topic_branch(repository: str, branch: str) -> str:
    base_branch = _default_branch(repository)
    if branch == base_branch:
        raise FanoutExecutionError("fanout landing refuses the repository default branch")
    return base_branch


def _predicate_timeout(packet: dict[str, Any]) -> int:
    remaining = int(
        (datetime.fromisoformat(packet["deadline"].replace("Z", "+00:00")) - datetime.now(timezone.utc)).total_seconds()
    )
    return max(1, min(1800, remaining))


def _predicate_environment(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin"),
        "HOME": str(home),
        "TMPDIR": str(home),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
        "CI": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }


def _run_predicate(packet: dict[str, Any], worktree: Path) -> subprocess.CompletedProcess[str]:
    """Run provider-controlled predicates without network or ambient credentials."""

    from limen.host_admission import hold_lease

    with tempfile.TemporaryDirectory(prefix="limen-fanout-predicate-") as temporary:
        home = Path(temporary)
        git_common = Path(
            _checked(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=worktree).strip()
        ).resolve()
        if sys.platform == "darwin" and shutil.which("sandbox-exec"):
            escaped_worktree = str(worktree).replace('"', '\\"')
            escaped_home = str(home).replace('"', '\\"')
            escaped_git_common = str(git_common).replace('"', '\\"')
            profile = (
                "(version 1)(deny default)"
                "(allow process*)"
                "(deny network*)"
                '(allow file-read* (subpath "/System") (subpath "/usr") '
                '(subpath "/bin") (subpath "/sbin") (subpath "/Library") '
                '(subpath "/opt/homebrew") '
                f'(subpath "{escaped_worktree}") (subpath "{escaped_home}") '
                f'(subpath "{escaped_git_common}"))'
                f'(allow file-write* (subpath "{escaped_worktree}") (subpath "{escaped_home}"))'
            )
            command = ["sandbox-exec", "-p", profile, "bash", "-lc", str(packet["predicate"])]
        elif shutil.which("bwrap"):
            command = [
                "bwrap",
                "--unshare-net",
                "--die-with-parent",
                "--proc",
                "/proc",
                "--dev",
                "/dev",
                "--tmpfs",
                "/tmp",
            ]
            for runtime_path in (
                "/usr",
                "/bin",
                "/sbin",
                "/lib",
                "/lib64",
                "/opt",
                "/etc/alternatives",
                "/etc/ld.so.cache",
                "/etc/ld.so.conf",
                "/etc/ld.so.conf.d",
            ):
                if Path(runtime_path).exists():
                    command.extend(["--ro-bind", runtime_path, runtime_path])
            command.extend(
                [
                    "--bind",
                    str(worktree),
                    str(worktree),
                    "--bind",
                    str(git_common),
                    str(git_common),
                    "--bind",
                    str(home),
                    str(home),
                    "--chdir",
                    str(worktree),
                    "bash",
                    "-lc",
                    str(packet["predicate"]),
                ]
            )
        else:
            raise FanoutExecutionError("no sanctioned network-denying predicate sandbox is available")
        try:
            with hold_lease(
                "heavy",
                owner=f"fanout:{canonical_hash(packet['work_id'])[:24]}",
                surface="fanout-predicate",
            ):
                return subprocess.run(
                    command,
                    cwd=str(worktree),
                    env=_predicate_environment(home),
                    text=True,
                    capture_output=True,
                    timeout=_predicate_timeout(packet),
                    check=False,
                )
        except (OSError, subprocess.SubprocessError) as exc:
            raise FanoutExecutionError(f"predicate sandbox failed: {exc}") from exc


class PatchLandingMixin:
    """Apply one provider result in a disposable clone and leave only remote custody."""

    def apply_result(self, provider_run_id: str, worktree: Path) -> None:
        raise NotImplementedError

    def land(
        self,
        node: dict[str, Any],
        attempt: ExecutorAttemptV1,
        *,
        capability_token: str,
        client: Any,
    ) -> RunReceiptV1:
        del capability_token, client
        packet = node["packet"]
        execution = packet["execution"]
        repository = str(execution["owner_repository"])
        exact_base = str(execution["exact_base"])
        branch = str(execution["topic_branch"])
        allowed = tuple(str(path) for path in packet["authority"]["path_prefixes"])
        if not attempt.provider_run_id or not attempt.provider_run_url:
            raise FanoutExecutionError("terminal provider attempt has no exact run receipt")
        if remote_default_head(repository) != exact_base:
            raise StaleResultError(f"{repository} default head moved from exact base {exact_base}")

        with tempfile.TemporaryDirectory(prefix="limen-fanout-land-") as temporary:
            root = Path(temporary)
            clone = root / "repository"
            worktree = root / "worktree"
            _checked(
                ["gh", "repo", "clone", repository, str(clone), "--", "--filter=blob:none", "--no-checkout"],
                timeout=300,
            )
            _checked(["git", "fetch", "origin", exact_base], cwd=clone, timeout=300)
            remote_branch = _run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], cwd=clone)
            if remote_branch.returncode == 0:
                return self._receipt_from_existing(node, attempt, clone, branch, exact_base, allowed)
            if remote_branch.returncode != 2:
                detail = (remote_branch.stderr or remote_branch.stdout).strip()
                raise FanoutExecutionError(f"remote branch probe failed: {detail[-800:]}")
            _checked(["git", "worktree", "add", "-b", branch, str(worktree), exact_base], cwd=clone, timeout=180)
            return self._land_new_result(
                node,
                attempt,
                worktree,
                repository,
                branch,
                exact_base,
                allowed,
            )

    def _land_new_result(
        self,
        node: dict[str, Any],
        attempt: ExecutorAttemptV1,
        worktree: Path,
        repository: str,
        branch: str,
        exact_base: str,
        allowed: tuple[str, ...],
    ) -> RunReceiptV1:
        from limen.host_admission import hold_lease, worktree_scope

        packet = node["packet"]
        scope = worktree_scope(worktree)
        with hold_lease(
            scope.lease_kind,
            owner=f"fanout:{node['run_id']}",
            surface="fanout-result-landing",
        ):
            self.apply_result(str(attempt.provider_run_id), worktree)
            provider_head = _checked(["git", "rev-parse", "HEAD"], cwd=worktree).strip()
            if provider_head != exact_base:
                _checked(["git", "merge-base", "--is-ancestor", exact_base, provider_head], cwd=worktree)
                _checked(["git", "reset", "--soft", exact_base], cwd=worktree)
            changed = _working_tree_changed_paths(worktree, exact_base)
            if not changed:
                raise FanoutExecutionError("provider result produced no code diff")
            if not _authorized_paths(changed, allowed):
                unauthorized = [path for path in changed if not _authorized_paths((path,), allowed)]
                raise FanoutExecutionError(f"provider changed unauthorized paths: {unauthorized}")
            _checked(["git", "add", "-A", "--", *changed], cwd=worktree)
            _checked(
                [
                    "git",
                    "-c",
                    f"user.name={os.environ.get('LIMEN_COMMIT_NAME', '4444J99')}",
                    "-c",
                    "user.email=" + os.environ.get("LIMEN_COMMIT_EMAIL", "4444J99@users.noreply.github.com"),
                    "commit",
                    "-m",
                    f"{packet['intent']['intended_effect']}\n\nlimen fanout {node['run_id']} ({attempt.attempt_id})",
                ],
                cwd=worktree,
            )
            head = _checked(["git", "rev-parse", "HEAD"], cwd=worktree).strip()
            diff = _checked(["git", "diff", "--binary", exact_base, head], cwd=worktree)
            diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()
            predicate = self._verify_committed_head(packet, worktree, head)
            if predicate.returncode != 0:
                detail = (predicate.stdout + predicate.stderr).strip()[-1200:]
                raise FanoutExecutionError(f"predicate failed ({predicate.returncode}): {detail}")
            base_branch = _assert_topic_branch(repository, branch)
            _checked(["git", "push", "-u", "origin", f"HEAD:refs/heads/{branch}"], cwd=worktree, timeout=300)
            pr_url = self._create_or_adopt_pr(
                repository,
                branch,
                base_branch,
                head,
                packet,
                attempt,
            )
            self._verify_remote_receipts(repository, branch, base_branch, head, pr_url, exact_base)
            return self._receipt(node, attempt, exact_base, head, changed, diff_hash, pr_url, predicate)

    def _receipt_from_existing(
        self,
        node: dict[str, Any],
        attempt: ExecutorAttemptV1,
        clone: Path,
        branch: str,
        exact_base: str,
        allowed: tuple[str, ...],
    ) -> RunReceiptV1:
        _checked(["git", "fetch", "origin", branch], cwd=clone, timeout=300)
        head = _checked(["git", "rev-parse", "FETCH_HEAD"], cwd=clone).strip()
        _checked(["git", "merge-base", "--is-ancestor", exact_base, head], cwd=clone)
        changed = _changed_paths(clone, exact_base, head)
        if not changed or not _authorized_paths(changed, allowed):
            raise FanoutExecutionError("existing provider branch has no authorized exact diff")
        marker = _checked(["git", "log", "-1", "--format=%B", head], cwd=clone)
        if attempt.attempt_id not in marker:
            raise FanoutExecutionError("existing provider branch is not owned by this attempt")
        diff = _checked(["git", "diff", "--binary", exact_base, head], cwd=clone)
        diff_hash = hashlib.sha256(diff.encode("utf-8")).hexdigest()
        predicate = self._verify_committed_head(node["packet"], clone, head)
        if predicate.returncode != 0:
            detail = (predicate.stdout + predicate.stderr).strip()[-1200:]
            raise FanoutExecutionError(f"existing branch predicate failed ({predicate.returncode}): {detail}")
        repository = str(node["packet"]["execution"]["owner_repository"])
        base_branch = _assert_topic_branch(repository, branch)
        pr_url = self._existing_pr(repository, branch, base_branch, head)
        if not pr_url:
            pr_url = self._create_or_adopt_pr(
                repository,
                branch,
                base_branch,
                head,
                node["packet"],
                attempt,
            )
        self._verify_remote_receipts(repository, branch, base_branch, head, pr_url, exact_base)
        return self._receipt(node, attempt, exact_base, head, changed, diff_hash, pr_url, predicate)

    @staticmethod
    def _verify_committed_head(
        packet: dict[str, Any],
        repository: Path,
        head: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run a possibly mutating predicate in a disposable detached worktree."""

        from limen.host_admission import hold_lease, worktree_scope

        verification = repository.parent / f"verify-{canonical_hash(head)[:16]}"
        git_root = repository
        if _run(["git", "rev-parse", "--is-bare-repository"], cwd=repository).stdout.strip() != "true":
            git_root = Path(
                _checked(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repository).strip()
            ).parent
        _checked(["git", "worktree", "add", "--detach", str(verification), head], cwd=git_root)
        scope = worktree_scope(verification)
        with hold_lease(
            scope.lease_kind,
            owner=f"fanout-verify:{canonical_hash(head)[:24]}",
            surface="fanout-result-verification",
        ):
            return _run_predicate(packet, verification)

    @staticmethod
    def _existing_pr(repository: str, branch: str, base_branch: str, head: str) -> str:
        output = _checked(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repository,
                "--head",
                branch,
                "--state",
                "all",
                "--json",
                "url,state,mergedAt,headRefOid,baseRefName,headRepository",
                "--limit",
                "20",
            ]
        )
        rows = json.loads(output or "[]")
        for row in rows:
            head_repository = row.get("headRepository") or {}
            if (
                row.get("headRefOid") == head
                and row.get("baseRefName") == base_branch
                and head_repository.get("nameWithOwner") == repository
                and (row.get("state") == "OPEN" or row.get("mergedAt"))
            ):
                return str(row["url"])
        return ""

    @staticmethod
    def _verify_remote_receipts(
        repository: str,
        branch: str,
        base_branch: str,
        head: str,
        pr_url: str,
        exact_base: str,
    ) -> None:
        if remote_default_head(repository) != exact_base:
            raise StaleResultError("remote default branch moved before receipt submission")
        if remote_branch_head(repository, branch) != head:
            raise StaleResultError("remote topic branch moved before receipt submission")
        output = _checked(
            [
                "gh",
                "pr",
                "view",
                pr_url,
                "--repo",
                repository,
                "--json",
                "url,baseRefName,headRefName,headRefOid,headRepository",
            ],
            timeout=120,
        )
        row = json.loads(output)
        head_repository = row.get("headRepository") or {}
        if (
            row.get("url") != pr_url
            or row.get("baseRefName") != base_branch
            or row.get("headRefName") != branch
            or row.get("headRefOid") != head
            or head_repository.get("nameWithOwner") != repository
        ):
            raise StaleResultError("pull request no longer matches the exact repo/base/branch/head receipt")

    def _create_or_adopt_pr(
        self,
        repository: str,
        branch: str,
        base_branch: str,
        head: str,
        packet: dict[str, Any],
        attempt: ExecutorAttemptV1,
    ) -> str:
        existing = self._existing_pr(repository, branch, base_branch, head)
        if existing:
            return existing
        created = _run(
            [
                "gh",
                "pr",
                "create",
                "--repo",
                repository,
                "--head",
                branch,
                "--base",
                base_branch,
                "--title",
                f"[limen fanout] {packet['intent']['intended_effect']}"[:120],
                "--body",
                (
                    f"Fanout run `{attempt.run_id}`; provider attempt `{attempt.attempt_id}`.\n\n"
                    f"Exact base: `{packet['execution']['exact_base']}`\n"
                    f"Predicate: `{packet['predicate']}`"
                ),
            ],
            timeout=180,
        )
        if created.returncode != 0:
            adopted = self._existing_pr(repository, branch, base_branch, head)
            if adopted:
                return adopted
            detail = (created.stderr or created.stdout).strip()
            raise FanoutExecutionError(f"pull request creation failed: {detail[-1000:]}")
        pr_url = created.stdout.strip().splitlines()[-1]
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/pull/\d+", pr_url):
            adopted = self._existing_pr(repository, branch, base_branch, head)
            if not adopted:
                raise FanoutExecutionError("pull request creation returned no canonical URL")
            pr_url = adopted
        return pr_url

    @staticmethod
    def _receipt(
        node: dict[str, Any],
        attempt: ExecutorAttemptV1,
        exact_base: str,
        head: str,
        changed: tuple[str, ...],
        diff_hash: str,
        pr_url: str,
        predicate: subprocess.CompletedProcess[str],
    ) -> RunReceiptV1:
        packet = node["packet"]
        summary = ((predicate.stdout or "") + (predicate.stderr or "")).strip()[-1000:]
        return RunReceiptV1(
            receipt_id=f"receipt-{attempt.attempt_id}",
            run_id=node["run_id"],
            lease_id=attempt.lease_id,
            lease_generation=attempt.lease_generation,
            executor=attempt.executor,
            provider_identity=attempt.adapter,
            observed_heads_before={packet["execution"]["owner_repository"]: exact_base},
            observed_heads_after={packet["execution"]["owner_repository"]: head},
            changed_paths=changed,
            provider_run_url=attempt.provider_run_url,
            predicate=PredicateEvidenceV1(
                command=packet["predicate"],
                exit_code=0,
                summary=summary,
            ),
            checks=(
                CheckEvidenceV1(
                    name="exact-diff",
                    status="success",
                    url=f"{pr_url}/files",
                    head=diff_hash,
                ),
                CheckEvidenceV1(name="pull-request", status="success", url=pr_url, head=head),
            ),
            spend={packet["spend"]["unit"]: 1},
            outcome="succeeded",
        )


class JulesExecutionAdapter(PatchLandingMixin):
    name = "jules-remote"
    transport = "remote-jules"
    local_heavy = False
    concurrency = 5
    receipt_quality = 0.95
    cost_per_run = 0.0
    quota_remaining = None
    capabilities = CODE_RECEIPT_CAPABILITIES
    conduct_token_env = "LIMEN_CONDUCT_TOKEN_JULES"
    worker_env_allowlist = frozenset({"LIMEN_JULES_BIN"})

    def __init__(self, repositories: frozenset[str], binary: str | None = None):
        self.binary = binary or os.environ.get("LIMEN_JULES_BIN", "jules")
        self.repositories = repositories

    @classmethod
    def discover(cls, repositories: frozenset[str]) -> "JulesExecutionAdapter | None":
        binary = os.environ.get("LIMEN_JULES_BIN", "jules")
        if shutil.which(binary) is None:
            return None
        listed = _run([binary, "remote", "list", "--repo"], timeout=180)
        if listed.returncode != 0:
            return None
        reachable = frozenset(line.strip() for line in listed.stdout.splitlines() if "/" in line)
        eligible = repositories & reachable
        return cls(eligible, binary=binary) if eligible else None

    def eligible(self, packet: dict[str, Any]) -> bool:
        return packet.get("effect") == "write" and packet["execution"]["owner_repository"] in self.repositories

    def launch(self, packet: dict[str, Any], attempt_id: str) -> ProviderLaunch:
        repository = packet["execution"]["owner_repository"]
        result = _run(
            [
                self.binary,
                "remote",
                "new",
                "--repo",
                repository,
                "--session",
                _provider_prompt(packet, attempt_id),
            ],
            timeout=600,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise TransientFanoutExecutionError(f"Jules launch failed: {detail[-1200:]}")
        match = re.search(r"^\s*ID:\s*(\d{12,64})", result.stdout, re.MULTILINE)
        if not match:
            match = re.search(r"jules\.google\.com/session/(\d{12,64})", result.stdout)
        if not match:
            raise FanoutExecutionError("Jules launch returned no exact session ID")
        session_id = match.group(1)
        url_match = re.search(r"https://jules\.google\.com/session/\d+", result.stdout)
        return ProviderLaunch(
            provider_run_id=session_id,
            provider_run_url=url_match.group(0) if url_match else f"https://jules.google.com/session/{session_id}",
        )

    def recover(self, packet: dict[str, Any], attempt_id: str) -> ProviderLaunch | None:
        del packet
        result = _run([self.binary, "remote", "list", "--session"], timeout=180)
        marker = f"[limen-fanout:{attempt_id}]"
        for line in result.stdout.splitlines() if result.returncode == 0 else ():
            if marker not in line:
                continue
            match = _SESSION_ID_RE.search(line)
            if match:
                session_id = match.group(1)
                return ProviderLaunch(session_id, f"https://jules.google.com/session/{session_id}")
        return None

    def probe(self, provider_run_id: str) -> ProviderState:
        snapshot = probe_jules_remote_sessions(binary=self.binary, timeout=180)
        if not snapshot.available:
            return ProviderState("running", snapshot.error or "Jules status unavailable")
        session = snapshot.sessions.get(provider_run_id)
        if session is None:
            return ProviderState("running", "Jules catalog miss is non-authoritative")
        return ProviderState(
            {
                "completed": "succeeded",
                "failed": "failed",
                "awaiting_user_feedback": "blocked",
                "awaiting_plan_approval": "blocked",
                "planning": "running",
                "in_progress": "running",
                "unknown": "running",
            }[session.status],
            session.status,
            "permanent" if session.status in {"failed", "awaiting_user_feedback", "awaiting_plan_approval"} else None,
        )

    def apply_result(self, provider_run_id: str, worktree: Path) -> None:
        _checked(
            [self.binary, "remote", "pull", "--session", provider_run_id, "--apply"],
            cwd=worktree,
            timeout=600,
        )


class CodexCloudExecutionAdapter(PatchLandingMixin):
    name = "codex-cloud"
    transport = "remote-codex-cloud"
    local_heavy = False
    concurrency = 4
    receipt_quality = 0.95
    cost_per_run = None
    quota_remaining = None
    capabilities = CODE_RECEIPT_CAPABILITIES
    conduct_token_env = "LIMEN_CONDUCT_TOKEN_CODEX_CLOUD"
    worker_env_allowlist = frozenset({"LIMEN_CODEX_BIN", "LIMEN_CODEX_CLOUD_ENVIRONMENTS"})

    def __init__(self, environments: dict[str, str], binary: str = "codex"):
        self.environments = environments
        self.binary = binary

    @classmethod
    def discover(cls, repositories: frozenset[str]) -> "CodexCloudExecutionAdapter | None":
        binary = os.environ.get("LIMEN_CODEX_BIN", "codex")
        if shutil.which(binary) is None:
            return None
        try:
            configured = json.loads(os.environ.get("LIMEN_CODEX_CLOUD_ENVIRONMENTS", "{}"))
        except json.JSONDecodeError:
            return None
        if not isinstance(configured, dict):
            return None
        environments = {
            str(repository): str(environment)
            for repository, environment in configured.items()
            if repository in repositories and isinstance(environment, str) and environment
        }
        return cls(environments, binary=binary) if environments else None

    def eligible(self, packet: dict[str, Any]) -> bool:
        return packet.get("effect") == "write" and packet["execution"]["owner_repository"] in self.environments

    def launch(self, packet: dict[str, Any], attempt_id: str) -> ProviderLaunch:
        repository = packet["execution"]["owner_repository"]
        branch = _default_branch(repository)
        result = _run(
            [
                self.binary,
                "cloud",
                "exec",
                "--env",
                self.environments[repository],
                "--branch",
                branch,
                _provider_prompt(packet, attempt_id),
            ],
            timeout=600,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise TransientFanoutExecutionError(f"Codex Cloud launch failed: {detail[-1200:]}")
        match = _CODEX_TASK_RE.search(result.stdout + result.stderr)
        if not match:
            raise FanoutExecutionError("Codex Cloud launch returned no exact task ID")
        task_id = match.group(1)
        url = next(
            (
                value.rstrip(".,")
                for value in _URL_RE.findall(result.stdout + result.stderr)
                if "/codex/tasks/" in value
            ),
            f"https://chatgpt.com/codex/tasks/{task_id}",
        )
        return ProviderLaunch(task_id, url)

    def recover(self, packet: dict[str, Any], attempt_id: str) -> ProviderLaunch | None:
        del packet
        result = _run([self.binary, "cloud", "list", "--json", "--limit", "100"], timeout=180)
        if result.returncode != 0:
            return None
        try:
            tasks = json.loads(result.stdout).get("tasks", [])
        except (AttributeError, json.JSONDecodeError):
            return None
        marker = f"[limen-fanout:{attempt_id}]"
        for task in tasks:
            if marker in str(task.get("title", "")) and task.get("id"):
                task_id = str(task["id"])
                return ProviderLaunch(task_id, str(task.get("url") or f"https://chatgpt.com/codex/tasks/{task_id}"))
        return None

    def probe(self, provider_run_id: str) -> ProviderState:
        result = _run([self.binary, "cloud", "list", "--json", "--limit", "100"], timeout=180)
        if result.returncode != 0:
            return ProviderState("running", "Codex Cloud status unavailable")
        try:
            tasks = json.loads(result.stdout).get("tasks", [])
        except (AttributeError, json.JSONDecodeError):
            return ProviderState("running", "Codex Cloud returned invalid status JSON")
        task = next((row for row in tasks if row.get("id") == provider_run_id), None)
        if task is None:
            return ProviderState("running", "Codex Cloud task not in bounded recent catalog")
        status = str(task.get("status") or "").casefold()
        if status in {"ready", "completed", "succeeded"}:
            return ProviderState("succeeded", status)
        if status in {"failed", "error", "cancelled"}:
            return ProviderState("failed", status, "permanent")
        return ProviderState("running", status)

    def apply_result(self, provider_run_id: str, worktree: Path) -> None:
        diff = _checked([self.binary, "cloud", "diff", provider_run_id], timeout=300)
        if not diff.strip():
            raise FanoutExecutionError("Codex Cloud task produced no diff")
        _checked(["git", "apply", "--index", "--whitespace=error-all", "-"], cwd=worktree, input_text=diff)


def discover_execution_adapters(repositories: frozenset[str]) -> tuple[ExecutionAdapter, ...]:
    """Discover live provider capacity; no manifest or routing table names a provider."""

    if not repositories:
        return ()
    adapters: list[ExecutionAdapter] = []
    for candidate in (
        CodexCloudExecutionAdapter.discover(repositories),
        JulesExecutionAdapter.discover(repositories),
    ):
        if candidate is not None:
            adapters.append(cast(ExecutionAdapter, candidate))
    try:
        entries = importlib.metadata.entry_points(group="limen.fanout_execution")
    except TypeError:  # pragma: no cover - Python compatibility
        entries = importlib.metadata.entry_points().select(group="limen.fanout_execution")
    for entry in entries:
        adapter = entry.load()()
        if any(adapter.eligible({"execution": {"owner_repository": repo}}) for repo in repositories):
            adapters.append(adapter)
    return tuple(adapters)


def _client_for_adapter(conductor_client: Any, adapter: ExecutionAdapter) -> Any:
    if not isinstance(conductor_client, HttpConductClient):
        return conductor_client
    token_env = str(getattr(adapter, "conduct_token_env", "LIMEN_CONDUCT_EXECUTOR_TOKEN"))
    token = os.environ.get(token_env, "").strip()
    if not token:
        raise FanoutExecutionError(f"live adapter {adapter.name} has no executor credential in {token_env}")
    return HttpConductClient(
        conductor_client.endpoint,
        token,
        timeout=conductor_client.timeout,
    )


def _client_for_existing_session(
    conductor_client: Any,
    session_id: str,
    primary: ExecutionAdapter,
) -> Any:
    if not isinstance(conductor_client, HttpConductClient):
        return conductor_client
    token_env = next(
        (
            env
            for marker, env in (
                ("-jules-remote-", "LIMEN_CONDUCT_TOKEN_JULES"),
                ("-codex-cloud-", "LIMEN_CONDUCT_TOKEN_CODEX_CLOUD"),
            )
            if marker in session_id
        ),
        str(getattr(primary, "conduct_token_env", "LIMEN_CONDUCT_EXECUTOR_TOKEN")),
    )
    token = os.environ.get(token_env, "").strip()
    if not token:
        raise FanoutExecutionError(f"executor session {session_id} has no credential in {token_env}")
    return HttpConductClient(
        conductor_client.endpoint,
        token,
        timeout=conductor_client.timeout,
    )


def register_execution_sessions(
    manifest: Any,
    client: Any,
    adapters: tuple[ExecutionAdapter, ...],
) -> dict[str, ExecutionLane]:
    """Register conductors and executors with separate authenticated principals."""

    conductor = ConductorSessionV1(
        session_id=manifest.conductor.session_id,
        identity=manifest.conductor,
        origin="direct",
        capabilities=frozenset({"conduct"}),
        transport="native",
        concurrency=1,
        human_protected=True,
    )
    registered = client.register(conductor)
    if registered.get("identity") != manifest.conductor.model_dump(mode="json"):
        raise FanoutExecutionError("authenticated principal does not match the manifest conductor identity")
    by_session: dict[str, ExecutionLane] = {}
    for adapter in adapters:
        executor_client = _client_for_adapter(client, adapter)
        session_id = f"{manifest.conductor.session_id}-{adapter.name}-{manifest.manifest_hash[:10]}"
        identity = manifest.conductor.model_copy(
            update={
                "session_id": session_id,
                "native_run_id": None,
                "provider_identity": None,
            }
        )
        repository_capabilities = frozenset(
            f"repository:{canonical_hash(leaf.owner_repository)[:32]}"
            for leaf in manifest.leaves
            if adapter.eligible(
                {
                    "execution": {"owner_repository": leaf.owner_repository},
                    "intent": {"intended_effect": leaf.intended_effect},
                    "authority": {"path_prefixes": list(leaf.allowed_paths)},
                    "effect": leaf.effect,
                }
            )
        )
        response = executor_client.register(
            ConductorSessionV1(
                session_id=session_id,
                identity=identity,
                origin="relay",
                capabilities=adapter.capabilities
                | repository_capabilities
                | frozenset({f"campaign:{manifest.manifest_hash}"})
                | (frozenset({"local-heavy"}) if adapter.local_heavy else frozenset()),
                transport=adapter.transport,
                harvest_method="provider-attempt-receipt",
                concurrency=adapter.concurrency,
                quota_remaining=adapter.quota_remaining,
                cost_per_run=adapter.cost_per_run,
                receipt_quality=adapter.receipt_quality,
                accepting_work=True,
            )
        )
        by_session[str(response["session_id"])] = ExecutionLane(
            primary=adapter,
            adapters=(adapter,),
            client=executor_client,
        )
    return by_session


def resume_execution_sessions(
    graph: dict[str, Any],
    client: Any,
    adapters: tuple[ExecutionAdapter, ...],
) -> dict[str, ExecutionLane]:
    """Rehydrate executor services from keeper-owned sessions, not local campaign state."""

    sessions = {
        str(row.get("session_id")): row for row in client.capabilities().get("sessions", []) if isinstance(row, dict)
    }
    manifest_hashes = {
        str(node.get("packet", {}).get("execution", {}).get("manifest_hash") or "")
        for node in graph.get("nodes", [])
        if node.get("packet", {}).get("intent", {}).get("kind") == "fanout-root"
    }
    suffixes = tuple(f"-{digest[:10]}" for digest in manifest_hashes if digest)
    wanted = {
        str(node.get("executor_session_id"))
        for node in graph.get("nodes", [])
        if node.get("executor_session_id") and node.get("packet", {}).get("intent", {}).get("kind") == "fanout-leaf"
    }
    wanted.update(session_id for session_id in sessions if suffixes and session_id.endswith(suffixes))
    lanes: dict[str, ExecutionLane] = {}
    model_fields = set(ConductorSessionV1.model_fields)
    for session_id in sorted(wanted):
        row = sessions.get(session_id)
        if not row:
            continue
        primary = next(
            (
                adapter
                for adapter in adapters
                if adapter.transport == row.get("transport") or f"-{adapter.name}-" in session_id
            ),
            None,
        )
        if primary is None:
            continue
        executor_client = _client_for_existing_session(client, session_id, primary)
        session = ConductorSessionV1.model_validate({key: value for key, value in row.items() if key in model_fields})
        executor_client.register(session)
        lanes[session_id] = ExecutionLane(
            primary=primary,
            adapters=(primary,),
            client=executor_client,
        )
    return lanes


def launch_ready_nodes(
    root_run_id: str,
    *,
    client: Any,
    adapters_by_session: dict[str, ExecutionLane],
) -> list[dict[str, Any]]:
    """Claim and submit every dependency-ready reservation exactly once."""

    graph = client.graph(root_run_id)
    launched: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if node.get("status") not in {"reserved", "running"} or not node.get("lease"):
            continue
        packet = node.get("packet") or {}
        if packet.get("intent", {}).get("kind") != "fanout-leaf":
            continue
        execution_lane = adapters_by_session.get(str(node.get("executor_session_id") or ""))
        if execution_lane is None:
            continue
        executor_client = execution_lane.client
        eligible_adapters = [adapter for adapter in execution_lane.adapters if adapter.eligible(packet)]
        if not eligible_adapters:
            continue
        existing = [ExecutorAttemptV1.model_validate(row) for row in node.get("attempts", [])]
        adapter_by_name = {adapter.name: adapter for adapter in eligible_adapters}
        used = [attempt.adapter for attempt in existing if attempt.status in {"failed", "blocked"}]
        unused = [adapter for adapter in eligible_adapters if adapter.name not in used]
        adapter = (
            adapter_by_name.get(existing[-1].adapter) if existing and existing[-1].status == "launching" else None
        ) or (unused or eligible_adapters)[0]
        if existing:
            current = existing[-1]
            if current.status not in {"launching", "failed", "blocked"}:
                continue
            if (
                current.status in {"failed", "blocked"}
                and packet["retry"].get("transient_only", True)
                and current.failure_class != "transient"
            ):
                continue
            if current.status == "launching":
                recovered = adapter.recover(packet, current.attempt_id)
                if recovered is None:
                    claim = executor_client.claim(node["lease"]["lease_id"], node["lease"]["generation"])
                    executor_client.heartbeat(
                        node["lease"]["lease_id"],
                        claim["capability_token"],
                        generation=node["lease"]["generation"],
                        observed_heads=packet["execution"]["observed_heads"],
                        attempt=current.model_copy(update={"updated_at": datetime.now(timezone.utc)}),
                    )
                    launched.append(
                        {
                            "run_id": node["run_id"],
                            "attempt_id": current.attempt_id,
                            "status": "launch-identity-pending",
                        }
                    )
                    continue
                claim = executor_client.claim(node["lease"]["lease_id"], node["lease"]["generation"])
                submitted = current.model_copy(
                    update={
                        "provider_run_id": recovered.provider_run_id,
                        "provider_run_url": recovered.provider_run_url,
                        "status": "submitted",
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                executor_client.heartbeat(
                    node["lease"]["lease_id"],
                    claim["capability_token"],
                    generation=node["lease"]["generation"],
                    observed_heads=packet["execution"]["observed_heads"],
                    attempt=submitted,
                )
                launched.append(submitted.model_dump(mode="json"))
                continue
        attempt_number = len(existing) + 1
        if attempt_number > int(packet["retry"]["max_attempts"]) or attempt_number > int(packet["spend"]["limit"]):
            continue
        attempt_id = f"attempt-{node['run_id'].removeprefix('run-')[:24]}-{attempt_number}"
        claim = executor_client.claim(node["lease"]["lease_id"], node["lease"]["generation"])
        expected = str(packet["execution"]["exact_base"])
        actual = remote_default_head(str(packet["execution"]["owner_repository"]))
        if actual != expected:
            executor_client.heartbeat(
                node["lease"]["lease_id"],
                claim["capability_token"],
                generation=node["lease"]["generation"],
                observed_heads={packet["execution"]["owner_repository"]: actual},
            )
            raise FanoutExecutionError(
                f"{packet['execution']['owner_repository']} moved from exact base {expected} to {actual}"
            )
        launching = _attempt_from(
            node,
            attempt_id=attempt_id,
            adapter=adapter.name,
            status="launching",
        )
        heartbeat = executor_client.heartbeat(
            node["lease"]["lease_id"],
            claim["capability_token"],
            generation=node["lease"]["generation"],
            observed_heads=packet["execution"]["observed_heads"],
            attempt=launching,
        )
        if heartbeat.get("status") != "active":
            raise FanoutExecutionError(f"keeper fenced launch attempt {attempt_id}: {heartbeat}")
        if heartbeat.get("attempt_created") is False:
            recovered = adapter.recover(packet, attempt_id)
            launched.append(
                {
                    "run_id": node["run_id"],
                    "attempt_id": attempt_id,
                    "status": ("launch-identity-pending" if recovered is None else "launch-owned-by-peer-worker"),
                }
            )
            continue
        try:
            if adapter.local_heavy:
                from limen.host_admission import hold_lease

                with hold_lease(
                    "heavy",
                    owner=f"fanout:{node['run_id']}",
                    surface=f"fanout-launch:{adapter.name}",
                ):
                    provider = adapter.launch(packet, attempt_id)
            else:
                provider = adapter.launch(packet, attempt_id)
        except AmbiguousProviderLaunchError as exc:
            pending = launching.model_copy(
                update={
                    "updated_at": datetime.now(timezone.utc),
                    "detail": str(exc)[:4096],
                }
            )
            executor_client.heartbeat(
                node["lease"]["lease_id"],
                claim["capability_token"],
                generation=node["lease"]["generation"],
                observed_heads=packet["execution"]["observed_heads"],
                attempt=pending,
            )
            launched.append(
                {
                    "run_id": node["run_id"],
                    "attempt_id": attempt_id,
                    "status": "launch-identity-pending",
                }
            )
            continue
        except Exception as exc:
            failed = launching.model_copy(
                update={
                    "status": "failed",
                    "failure_class": ("transient" if isinstance(exc, TransientFanoutExecutionError) else "permanent"),
                    "updated_at": datetime.now(timezone.utc),
                    "detail": str(exc)[:4096],
                }
            )
            executor_client.heartbeat(
                node["lease"]["lease_id"],
                claim["capability_token"],
                generation=node["lease"]["generation"],
                observed_heads=packet["execution"]["observed_heads"],
                attempt=failed,
            )
            launched.append(failed.model_dump(mode="json"))
            continue
        submitted = launching.model_copy(
            update={
                "provider_run_id": provider.provider_run_id,
                "provider_run_url": provider.provider_run_url,
                "status": "submitted",
                "updated_at": datetime.now(timezone.utc),
            }
        )
        executor_client.heartbeat(
            node["lease"]["lease_id"],
            claim["capability_token"],
            generation=node["lease"]["generation"],
            observed_heads=packet["execution"]["observed_heads"],
            attempt=submitted,
        )
        launched.append(submitted.model_dump(mode="json"))
    return launched


def refresh_provider_attempts(
    root_run_id: str,
    *,
    client: Any,
    adapters: tuple[ExecutionAdapter, ...],
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    by_name = {adapter.name: adapter for adapter in adapters}
    graph = client.graph(root_run_id)
    refreshed: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if session_id and node.get("executor_session_id") != session_id:
            continue
        if not node.get("lease") or not node.get("attempts"):
            continue
        attempt = ExecutorAttemptV1.model_validate(node["attempts"][-1])
        if attempt.status in _TERMINAL_ATTEMPT_STATES or not attempt.provider_run_id:
            continue
        adapter = by_name.get(attempt.adapter)
        if adapter is None:
            continue
        state = adapter.probe(attempt.provider_run_id)
        updated = attempt.model_copy(
            update={
                "status": state.status,
                "failure_class": state.failure_class,
                "detail": state.detail[:4096],
                "updated_at": datetime.now(timezone.utc),
            }
        )
        claim = client.claim(attempt.lease_id, attempt.lease_generation)
        client.heartbeat(
            attempt.lease_id,
            claim["capability_token"],
            generation=attempt.lease_generation,
            observed_heads=node["packet"]["execution"]["observed_heads"],
            attempt=updated,
        )
        refreshed.append(updated.model_dump(mode="json"))
    return refreshed


def settle_exhausted_attempts(
    root_run_id: str,
    *,
    client: Any,
    execution_lanes: dict[str, ExecutionLane],
) -> list[dict[str, Any]]:
    """Emit one exact blocked receipt when finite provider attempts are exhausted."""

    graph = client.graph(root_run_id)
    settled: list[dict[str, Any]] = []
    now = datetime.now(timezone.utc)
    for node in graph.get("nodes", []):
        packet = node.get("packet") or {}
        lane = execution_lanes.get(str(node.get("executor_session_id") or ""))
        attempts = [ExecutorAttemptV1.model_validate(row) for row in node.get("attempts", [])]
        if lane is None or node.get("status") not in {"reserved", "running"} or node.get("receipts") or not attempts:
            continue
        current = attempts[-1]
        deadline = datetime.fromisoformat(str(packet["deadline"]).replace("Z", "+00:00"))
        terminal_failure = current.status in {"failed", "blocked"}
        exhausted = terminal_failure and (
            len(attempts) >= int(packet["retry"]["max_attempts"])
            or len(attempts) >= int(packet["spend"]["limit"])
            or (bool(packet["retry"].get("transient_only", True)) and current.failure_class != "transient")
        )
        deadline_imminent = deadline <= now + timedelta(seconds=60)
        if not exhausted and not deadline_imminent:
            continue
        executor_client = lane.client
        claim = executor_client.claim(current.lease_id, current.lease_generation)
        repository = str(packet["execution"]["owner_repository"])
        exact_base = str(packet["execution"]["exact_base"])
        receipt = RunReceiptV1(
            receipt_id=f"receipt-exhausted-{node['run_id'].removeprefix('run-')[:24]}",
            run_id=node["run_id"],
            lease_id=current.lease_id,
            lease_generation=current.lease_generation,
            executor=current.executor,
            provider_identity=current.adapter,
            observed_heads_before={repository: exact_base},
            observed_heads_after={repository: exact_base},
            changed_paths=(),
            provider_run_url=current.provider_run_url,
            predicate=PredicateEvidenceV1(
                command=packet["predicate"],
                exit_code=1,
                summary=(
                    "finite provider attempt limit exhausted"
                    if exhausted
                    else "campaign deadline reached without an exact provider receipt"
                ),
            ),
            checks=(
                CheckEvidenceV1(
                    name="provider-attempt",
                    status="failure",
                    url=current.provider_run_url,
                ),
            ),
            spend={packet["spend"]["unit"]: len(attempts)},
            outcome="blocked",
        )
        result = executor_client.report(
            current.lease_id,
            claim["capability_token"],
            receipt,
            generation=current.lease_generation,
        )
        if not result.get("mutation_authorized"):
            raise FanoutExecutionError(f"keeper rejected exhausted receipt {receipt.receipt_id}")
        settled.append(result)
    return settled


def land_succeeded_attempts(
    root_run_id: str,
    *,
    client: Any,
    adapters: tuple[ExecutionAdapter, ...],
    session_id: str | None = None,
) -> list[dict[str, Any]]:
    by_name = {adapter.name: adapter for adapter in adapters}
    graph = client.graph(root_run_id)
    landed: list[dict[str, Any]] = []
    for node in graph.get("nodes", []):
        if session_id and node.get("executor_session_id") != session_id:
            continue
        packet = node.get("packet") or {}
        if packet.get("intent", {}).get("kind") != "fanout-leaf" or node.get("receipts") or not node.get("attempts"):
            continue
        attempt = ExecutorAttemptV1.model_validate(node["attempts"][-1])
        if attempt.status != "succeeded":
            continue
        adapter = by_name.get(attempt.adapter)
        if adapter is None:
            raise FanoutExecutionError(f"no live adapter can harvest {attempt.adapter}")
        claim = client.claim(attempt.lease_id, attempt.lease_generation)
        try:
            receipt = adapter.land(
                node,
                attempt,
                capability_token=claim["capability_token"],
                client=client,
            )
        except StaleResultError as exc:
            repository = str(packet["execution"]["owner_repository"])
            actual = remote_default_head(repository)
            if actual != str(packet["execution"]["exact_base"]):
                client.heartbeat(
                    attempt.lease_id,
                    claim["capability_token"],
                    generation=attempt.lease_generation,
                    observed_heads={repository: actual},
                )
            else:
                failed = attempt.model_copy(
                    update={
                        "status": "blocked",
                        "failure_class": "permanent",
                        "updated_at": datetime.now(timezone.utc),
                        "detail": str(exc)[:4096],
                    }
                )
                client.heartbeat(
                    attempt.lease_id,
                    claim["capability_token"],
                    generation=attempt.lease_generation,
                    observed_heads=packet["execution"]["observed_heads"],
                    attempt=failed,
                )
            landed.append(
                {
                    "run_id": node["run_id"],
                    "attempt_id": attempt.attempt_id,
                    "status": "stale-result-fenced",
                }
            )
            continue
        except Exception as exc:
            try:
                from limen.host_admission import AdmissionDenied

                transient = isinstance(exc, (TransientFanoutExecutionError, AdmissionDenied))
            except ImportError:  # pragma: no cover - package integrity failure
                transient = isinstance(exc, TransientFanoutExecutionError)
            failed = attempt.model_copy(
                update={
                    "status": "failed",
                    "failure_class": "transient" if transient else "permanent",
                    "updated_at": datetime.now(timezone.utc),
                    "detail": str(exc)[:4096],
                }
            )
            heartbeat = client.heartbeat(
                attempt.lease_id,
                claim["capability_token"],
                generation=attempt.lease_generation,
                observed_heads=packet["execution"]["observed_heads"],
                attempt=failed,
            )
            landed.append(
                {
                    "run_id": node["run_id"],
                    "attempt_id": attempt.attempt_id,
                    "status": heartbeat.get("status", "landing-failed"),
                }
            )
            continue
        result = client.report(
            attempt.lease_id,
            claim["capability_token"],
            receipt,
            generation=attempt.lease_generation,
        )
        if not result.get("mutation_authorized"):
            raise FanoutExecutionError(f"keeper rejected exact receipt {receipt.receipt_id}")
        landed.append(
            {
                "run_id": node["run_id"],
                "attempt_id": attempt.attempt_id,
                "receipt_id": receipt.receipt_id,
                "provider_run_url": attempt.provider_run_url,
                "pr": next(check.url for check in receipt.checks if check.name == "pull-request"),
            }
        )
    return landed


def wake_executor_workers(
    root_run_id: str,
    execution_lanes: dict[str, ExecutionLane],
) -> list[dict[str, str]]:
    """Wake detached executor services; the remote keeper remains their only state."""

    wakes: list[dict[str, str]] = []
    for session_id, lane in execution_lanes.items():
        if not isinstance(lane.client, HttpConductClient):
            continue
        environment = {
            key: value
            for key, value in os.environ.items()
            if key
            in {
                "PATH",
                "HOME",
                "TMPDIR",
                "LANG",
                "LC_ALL",
                "XDG_CONFIG_HOME",
                "LIMEN_COMMIT_NAME",
                "LIMEN_COMMIT_EMAIL",
                *getattr(lane.primary, "worker_env_allowlist", frozenset()),
            }
        }
        environment.update(
            {
                "LIMEN_CONDUCT_URL": lane.client.endpoint,
                "LIMEN_CONDUCT_TOKEN": lane.client.token,
            }
        )
        try:
            graph = lane.client.graph(root_run_id)
            root = next(node for node in graph.get("nodes", []) if node.get("run_id") == graph.get("root_run_id"))
            environment["LIMEN_FANOUT_WORKER_DEADLINE"] = str(root["packet"]["deadline"])
        except (KeyError, StopIteration, RuntimeError):
            # The worker retains its finite lease-TTL fallback if this optional
            # wake-time read is temporarily unavailable.
            pass
        with open(os.devnull, "r+", encoding="utf-8") as null:
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "limen.fanout_executor",
                    "--worker",
                    root_run_id,
                    "--session",
                    session_id,
                    "--adapter",
                    lane.primary.name,
                ],
                stdin=null,
                stdout=null,
                stderr=null,
                env=environment,
                close_fds=True,
                start_new_session=True,
            )
        wakes.append(
            {
                "session_id": session_id,
                "adapter": lane.primary.name,
                "status": "woken",
            }
        )
    return wakes


def run_executor_worker(root_run_id: str, session_id: str, primary_adapter: str) -> int:
    """Drive one authenticated executor lane until the keeper campaign is terminal."""

    lock_hash = hashlib.sha256(f"{root_run_id}\0{session_id}".encode()).hexdigest()
    lock_path = Path(tempfile.gettempdir()) / f"limen-fanout-worker-{lock_hash}.lock"
    with lock_path.open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 0
        raw_deadline = os.environ.get("LIMEN_FANOUT_WORKER_DEADLINE", "")
        try:
            worker_deadline = datetime.fromisoformat(raw_deadline.replace("Z", "+00:00"))
        except ValueError:
            worker_deadline = datetime.now(timezone.utc) + timedelta(hours=6)
        client = None
        primary = None
        lanes: dict[str, ExecutionLane] = {}
        while True:
            if datetime.now(timezone.utc) >= worker_deadline:
                return 1
            try:
                client = client or client_from_env()
                graph = client.graph(root_run_id)
                if primary is None:
                    repositories = frozenset(
                        str(node.get("packet", {}).get("execution", {}).get("owner_repository"))
                        for node in graph.get("nodes", [])
                        if node.get("packet", {}).get("intent", {}).get("kind") == "fanout-leaf"
                    )
                    adapters = discover_execution_adapters(repositories)
                    primary = next(
                        (adapter for adapter in adapters if adapter.name == primary_adapter),
                        None,
                    )
                    if primary is None:
                        return 2
                    lanes = {
                        session_id: ExecutionLane(
                            primary=primary,
                            adapters=(primary,),
                            client=client,
                        )
                    }
            except (FanoutExecutionError, RuntimeError, OSError):
                time.sleep(20)
                continue
            root = next(
                (node for node in graph.get("nodes", []) if node.get("run_id") == graph.get("root_run_id")),
                None,
            )
            if root is None or root.get("status") in {
                "succeeded",
                "failed",
                "blocked",
                "cancelled",
                "fenced",
                "expired",
            }:
                return 0
            progressed = False
            try:
                progressed = bool(
                    launch_ready_nodes(
                        root_run_id,
                        client=client,
                        adapters_by_session=lanes,
                    )
                )
                refreshed = refresh_provider_attempts(
                    root_run_id,
                    client=client,
                    adapters=(primary,),
                    session_id=session_id,
                )
                landed = land_succeeded_attempts(
                    root_run_id,
                    client=client,
                    adapters=(primary,),
                    session_id=session_id,
                )
                settled = settle_exhausted_attempts(
                    root_run_id,
                    client=client,
                    execution_lanes=lanes,
                )
                progressed = progressed or bool(refreshed or landed or settled)
            except (FanoutExecutionError, RuntimeError, OSError):
                # Provider and landing errors stay recoverable through keeper attempts.
                progressed = False
            time.sleep(5 if progressed else 20)


def _worker_main() -> int:
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--adapter", required=True)
    args = parser.parse_args()
    return run_executor_worker(args.worker, args.session, args.adapter)


if __name__ == "__main__":  # pragma: no cover - detached service entrypoint
    raise SystemExit(_worker_main())
