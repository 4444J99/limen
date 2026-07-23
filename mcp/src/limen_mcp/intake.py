"""Provider-neutral task intake contracts.

The board contains legacy tasks that predate typed acceptance criteria, so the
``Task`` model keeps ``predicate`` and ``receipt_target`` optional.  Every
*new* task and every task submitted in ``open`` state is nevertheless admitted
through this module before it can enter the keeper or dispatch machinery.

The contract is deliberately about durable evidence, not a particular agent:

* ``predicate`` is one executable command whose exit status is the done check;
* ``receipt_target`` is a durable GitHub owner or a repository-owned path;
* the task is one bounded objective (large numbered bundles are rejected).

Selected legacy tasks may be normalized at dispatch time, but only from owner
data already present on the task.  No provider/model names or fixed lane tables
are involved.
"""

# This provider-neutral module is byte-mirrored into the standalone web and
# MCP runtime packages.  ``test_portable_runtime_mirrors_match_canonical`` is
# the drift gate: edit this canonical copy, then refresh both mirrors together.

from __future__ import annotations

import re
import shlex
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

EXECUTABLES = frozenset(
    {
        "[",
        "bash",
        "bundle",
        "cargo",
        "curl",
        "gh",
        "git",
        "go",
        "just",
        "limen",
        "make",
        "node",
        "nox",
        "npm",
        "pnpm",
        "py.test",
        "pytest",
        "python",
        "python3",
        "ruby",
        "sh",
        "test",
        "tox",
        "uv",
        "yarn",
        "zsh",
    }
)
PLACEHOLDER_RE = re.compile(r"(?:<[^>]+>|\b(?:tbd|todo|fixme|replace[-_ ]me)\b)", re.IGNORECASE)
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
GITHUB_DECLARED_TARGET_RE = re.compile(
    r"^github:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):"
    r"(?P<kind>pull-request|issue):(?P<key>[A-Za-z0-9][A-Za-z0-9._/-]*)$"
)
GIT_PATH_TARGET_RE = re.compile(
    r"^git:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+):"
    r"(?P<path>[^\s#]+)(?:#(?P<anchor>[^\s]+))?$"
)
ENUM_ITEM_RE = re.compile(r"(?:^|\s)\((\d+)\)\s")
SEQUENCED_CLAUSE_RE = re.compile(r"(?i)(?:;\s*then\b|\band\s+then\s+also\b)")
PREDICATE_LINE_RE = re.compile(r"(?im)^\s*predicate\s*:\s*(?P<command>[^\r\n]+?)\s*$")
RECEIPT_LINE_RE = re.compile(r"(?im)^\s*receipt\s+target\s*:\s*(?P<target>\S+)\s*$")
GITHUB_URL_RE = re.compile(
    r"^https://github\.com/(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/"
    r"(?P<kind>issues|pull|actions/(?:runs|workflows)|commit|blob|tree)/(?P<key>[^/?#]+)"
)


class IntakeContractError(ValueError):
    """A task cannot enter or leave the queue under the typed contract."""


@dataclass(frozen=True)
class IntakeContract:
    predicate: str
    receipt_target: str


def _task_value(task: Mapping[str, Any] | object, name: str, default: Any = None) -> Any:
    if isinstance(task, Mapping):
        return task.get(name, default)
    return getattr(task, name, default)


def task_text(task: Mapping[str, Any] | object) -> str:
    return "\n".join(
        str(_task_value(task, key) or "") for key in ("title", "description", "context") if _task_value(task, key)
    )


def boundedness_finding(task: Mapping[str, Any] | object) -> str | None:
    """Return a structural bundle finding, without treating ordinary ``and`` as a separator.

    The old ask-gate counted every uppercase ``AND`` as a new objective.  That
    falsely classified prose such as a rebase instruction that said "keep X AND
    drop Y".  Only explicit numbered bundles or explicit sequenced clauses are
    counted here.
    """

    text = task_text(task)
    enumerated = {int(value) for value in ENUM_ITEM_RE.findall(text)}
    if len(enumerated) >= 4:
        return f"multi-goal bundle ({len(enumerated)} numbered objectives)"
    sequenced = len(SEQUENCED_CLAUSE_RE.findall(text))
    if sequenced >= 4:
        return f"multi-goal bundle ({sequenced + 1} sequenced objectives)"
    return None


def is_executable_predicate(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    command = value.strip()
    if not command or "\n" in command or "\r" in command or PLACEHOLDER_RE.search(command):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if not argv:
        return False
    command_index = 0
    while command_index < len(argv) and (
        argv[command_index] in {"command", "env", "sudo"}
        or ("=" in argv[command_index] and not argv[command_index].startswith(("/", "./", "../")))
        or argv[command_index].startswith("-")
    ):
        command_index += 1
    if command_index >= len(argv):
        return False
    first = argv[command_index]
    return bool(first in EXECUTABLES or "/" in first or first.endswith((".py", ".sh")))


def is_durable_receipt_target(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    target = value.strip()
    if not target or PLACEHOLDER_RE.search(target):
        return False
    if GITHUB_DECLARED_TARGET_RE.fullmatch(target):
        return True
    git_target = GIT_PATH_TARGET_RE.fullmatch(target)
    if git_target:
        path = git_target.group("path")
        parts = path.split("/")
        return not path.startswith("/") and all(part not in {"", ".", "..", ".git"} for part in parts)
    parsed = urlparse(target)
    if parsed.scheme != "https" or parsed.netloc.lower() != "github.com":
        return False
    return GITHUB_URL_RE.match(target) is not None


def validate_intake_contract(
    task: Mapping[str, Any] | object,
    *,
    is_new: bool = False,
    require_when_active: bool = True,
) -> IntakeContract | None:
    """Validate a new/active task and return its normalized typed fields.

    Legacy terminal tasks remain loadable: when a task is neither new nor active,
    missing typed fields are tolerated.  Present fields are still validated so a
    malformed partial contract cannot masquerade as evidence.
    """

    status = str(_task_value(task, "status", "open") or "open")
    required = is_new or (require_when_active and status in {"open", "dispatched", "in_progress"})
    predicate = str(_task_value(task, "predicate", "") or "").strip()
    receipt_target = str(_task_value(task, "receipt_target", "") or "").strip()
    has_partial_contract = bool(predicate or receipt_target)
    errors: list[str] = []
    if required or has_partial_contract:
        if not is_executable_predicate(predicate):
            errors.append("predicate must be one executable command with no placeholders")
    if required or has_partial_contract:
        if not is_durable_receipt_target(receipt_target):
            errors.append("receipt_target must name a durable GitHub receipt or repository-owned path")
    finding = boundedness_finding(task)
    if required and finding:
        errors.append(finding)
    if errors:
        raise IntakeContractError("; ".join(errors))
    if not predicate and not receipt_target:
        return None
    return IntakeContract(predicate=predicate, receipt_target=receipt_target)


def github_issue_contract(repo: str, issue: int | str) -> IntakeContract:
    if not REPO_RE.fullmatch(repo) or not str(issue).isdigit():
        raise IntakeContractError("cannot build issue contract without exact owner/repo and issue number")
    number = str(issue)
    return IntakeContract(
        predicate=f'test "$(gh issue view {number} --repo {repo} --json state --jq .state)" = CLOSED',
        receipt_target=f"https://github.com/{repo}/issues/{number}",
    )


def github_issue_owner_contract(repo: str, task_id: str) -> IntakeContract:
    if not REPO_RE.fullmatch(repo) or not TASK_ID_RE.fullmatch(task_id):
        raise IntakeContractError("cannot build issue owner contract without exact owner/repo and task id")
    return IntakeContract(
        predicate=(
            f"test \"$(gh issue list --repo {repo} --state closed --search '{task_id} in:title' "
            '--json number --jq length)" -gt 0'
        ),
        receipt_target=f"github:{repo}:issue:{task_id}",
    )


def github_pr_contract(repo: str, task_id: str) -> IntakeContract:
    if not REPO_RE.fullmatch(repo) or not TASK_ID_RE.fullmatch(task_id):
        raise IntakeContractError("cannot build PR contract without exact owner/repo and task id")
    return IntakeContract(
        predicate=(
            f"test \"$(gh pr list --repo {repo} --state merged --search '{task_id} in:body' "
            '--json number --jq length)" -gt 0'
        ),
        receipt_target=f"github:{repo}:pull-request:{task_id}",
    )


def github_existing_pr_contract(repo: str, number: int | str) -> IntakeContract:
    if not REPO_RE.fullmatch(repo) or not str(number).isdigit():
        raise IntakeContractError("cannot build existing-PR contract without exact owner/repo and PR number")
    pr_number = str(number)
    return IntakeContract(
        predicate=f'test "$(gh pr view {pr_number} --repo {repo} --json state --jq .state)" = MERGED',
        receipt_target=f"https://github.com/{repo}/pull/{pr_number}",
    )


def github_main_green_contract(repo: str, head_sha: str, workflow: str = "ci.yml") -> IntakeContract:
    if not REPO_RE.fullmatch(repo) or not re.fullmatch(r"[0-9a-fA-F]{40}", head_sha):
        raise IntakeContractError("cannot build main-green contract without exact owner/repo and 40-character head SHA")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", workflow):
        raise IntakeContractError("cannot build main-green contract with invalid workflow name")
    return IntakeContract(
        predicate=(
            f'test "$(gh run list --repo {repo} --workflow {workflow} --branch main --event push '
            f'--status completed --limit 20 --json headSha,conclusion --jq \'[.[] | select(.headSha == "{head_sha}" '
            'and .conclusion == "success")] | length\')" -gt 0'
        ),
        receipt_target=f"https://github.com/{repo}/actions/workflows/{workflow}",
    )


def contract_fields(contract: IntakeContract) -> dict[str, str]:
    return {"predicate": contract.predicate, "receipt_target": contract.receipt_target}


def _github_contract_from_url(url: str) -> IntakeContract | None:
    match = GITHUB_URL_RE.match(url)
    if not match:
        return None
    repo = match.group("repo")
    kind = match.group("kind")
    key = match.group("key")
    if kind == "issues" and key.isdigit():
        return github_issue_contract(repo, key)
    if kind == "pull" and key.isdigit():
        return github_existing_pr_contract(repo, key)
    return None


def normalize_selected_legacy_task(task: MutableMapping[str, Any] | object) -> IntakeContract:
    """Derive the selected legacy task's contract from its own owner data.

    The function never scans or mutates other tasks.  Explicit typed fields win;
    then exact ``Predicate:``/``Receipt target:`` lines and GitHub URLs are used;
    finally a repo/task-id keyed merged-PR receipt is defensible for machine work.
    If owner data is insufficient, dispatch fails closed.
    """

    try:
        existing = validate_intake_contract(task)
    except IntakeContractError:
        existing = None
    if existing is not None:
        return existing

    text = task_text(task)
    predicate_match = PREDICATE_LINE_RE.search(text)
    receipt_match = RECEIPT_LINE_RE.search(text)
    predicate = predicate_match.group("command").strip() if predicate_match else ""
    receipt_target = receipt_match.group("target").strip() if receipt_match else ""

    urls = _task_value(task, "urls", []) or []
    url_contract = next(
        (contract for url in urls if isinstance(url, str) for contract in [_github_contract_from_url(url)] if contract),
        None,
    )
    if url_contract:
        predicate = predicate if is_executable_predicate(predicate) else url_contract.predicate
        receipt_target = receipt_target if is_durable_receipt_target(receipt_target) else url_contract.receipt_target

    if not is_executable_predicate(predicate) or not is_durable_receipt_target(receipt_target):
        repo = str(_task_value(task, "repo", "") or "").strip()
        task_id = str(_task_value(task, "id", "") or "").strip()
        fallback = github_pr_contract(repo, task_id)
        predicate = predicate if is_executable_predicate(predicate) else fallback.predicate
        receipt_target = receipt_target if is_durable_receipt_target(receipt_target) else fallback.receipt_target

    if isinstance(task, MutableMapping):
        task["predicate"] = predicate
        task["receipt_target"] = receipt_target
    else:
        task.predicate = predicate
        task.receipt_target = receipt_target
    contract = validate_intake_contract(task)
    if contract is None:  # pragma: no cover - defensive, required open tasks return a contract
        raise IntakeContractError("selected task lacks a typed intake contract")
    return contract
