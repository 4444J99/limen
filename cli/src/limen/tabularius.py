"""TABVLARIVS — the one record-keeper over the board (`tasks.yaml`).

The disease this dissolves: ~32 uncoordinated writers each do *read-whole-board → mutate →
rewrite-whole-board* on the single `tasks.yaml` blob. `io.atomic_write_text` already stops torn
*bytes* (temp-file + `os.replace`), but two writers that both `load→save` still lost-update-clobber
(last-writer-wins on the whole board), and the worst offenders (the MCP server) skip even the
atomic write. Locking every `save` would give write-*atomicity* but not read-modify-write
*isolation* — the clobber survives. The only correct cure is the **single-writer principle**:
workers stop mutating shared state and instead APPEND one immutable *ticket* per unit of work to a
lock-free inbox; exactly **one** keeper drains the inbox, folds the tickets onto the board in
timestamp order, validates (per-task + the collapse-guard), and seals the result with the atomic
write. It is the only process that ever holds the write lock, so there is no interleave to tear.

This is Step 2+3 of `board-is-event-log-projection` (PR#543): `materialize.fold` is the proven pure
reducer — this module gives it a live stream to consume. A ticket **is** a `materialize` Event with
provenance (who did the work, when), and the archived ticket files are the append-only event log
that the board is a projection of (`board = fold(events)`).

Ticket lifecycle::

    logs/tickets/inbox/<id>.json  --drain-->  applied → archive/   (the event log)
                                              rejected → rejected/  (+ <id>.reason.txt)

Design invariants (each carried over from a shipped safety precedent):
  * **A worker never touches `tasks.yaml`.** It calls `submit_ticket`, an exclusive atomic create
    into the inbox — no read, no lock, no collapse risk, no interleave. (Preserves the one writer
    the fleet must never starve, `ingest-backlog.py`, which deliberately skipped the lock.)
  * **One bad ticket never rejects the batch.** Each ticket is applied + validated individually;
    a bad one is quarantined to `rejected/` and the rest still land (the `_sanitize_dispatch_logs`
    tolerate-and-salvage philosophy from `io.py`).
  * **The seal is collapse-guarded.** The board is written through `save_limen_file`, so the
    2026-06-26 shrink-to-1 clobber remains impossible; a batch that would collapse the board is
    rejected whole and the good board is left intact.
  * **Never dead-stop the beat.** If the queue lock is held (a legacy writer, mid-migration), the
    keeper defers to the next beat rather than blocking — exactly like `heal-board.py`.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from limen.intake import validate_intake_contract
from limen.io import BoardCollapseError, load_limen_file, queue_lock, save_limen_file
from limen.materialize import EV_BOARD_META, EV_BOARD_ORDER, EV_TASK_UPSERT, Event, fold
from limen.models import VALID_STATUSES, LimenFile, Task
from limen.workstream_contract import WORKSTREAM_SUCCESSOR_REQUIRED_LABEL

# --- ticket intents (a superset of materialize's Event tags, plus the status convenience) --------
INTENT_UPSERT = "task.upsert"  # create-or-merge a task field-set (patch may be full or partial)
INTENT_STATUS = "task.status"  # the common worker ticket: set status + append a dispatch_log entry
INTENT_REMOVE = "task.remove"  # drop a task id (prune/archive-out)
INTENT_ORDER = "board.order"  # set the task display order (patch = {"ids": [...]})
INTENT_META = "board.meta"  # set board version/portal (patch = {"version":..,"portal":..})
_INTENTS = frozenset({INTENT_UPSERT, INTENT_STATUS, INTENT_REMOVE, INTENT_ORDER, INTENT_META})
BOARD_PUBLICATION_BRANCH = "tabularius/board-projection"
BOARD_PUBLICATION_TITLE = "tabularius: publish board projection"


class Ticket(BaseModel):
    """One immutable unit of board work a worker hands to the record-keeper.

    A worker builds a Ticket describing the transition it performed ("here's the work I did") and
    drops it into the inbox via `submit_ticket`. It is an Event with provenance — the `patch` is a
    *field-level delta*, never a whole-board rewrite, so a torn ticket can at worst be quarantined
    and never corrupts the SSOT.
    """

    ticket_id: str
    timestamp: datetime
    agent: str
    session_id: str = "unknown"
    intent: str
    task_id: str | None = None
    # field-level delta: for upsert/status the task field-patch; for board.order {"ids": [...]};
    # for board.meta {"version": .., "portal": ..}.
    patch: dict[str, Any] | None = None
    # optional dispatch_log payload appended to the task's log — {"status": .., "output"?: ..}.
    log: dict[str, Any] | None = None
    # Optional optimistic concurrency guard, evaluated by the keeper against
    # the exact current task immediately before this ticket is folded.  A
    # migration can therefore never archive a task that another ticket claimed
    # after compilation.
    precondition: dict[str, Any] | None = None


def task_state_sha256(fields: dict[str, Any]) -> str:
    """Content hash for one JSON-mode task state, including its append-only log."""

    encoded = json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def new_ticket_id(session_id: str = "unknown", now: datetime | None = None) -> str:
    """A sortable, collision-free ticket id: `<utc-timestamp>-<session>-<rand>`. The timestamp
    prefix makes a plain filename sort chronological (the keeper's drain order), and the random
    tail guarantees two tickets from the same session in the same microsecond never collide."""
    now = now or datetime.now(timezone.utc)
    safe_session = "".join(c if c.isalnum() or c in "._-" else "_" for c in session_id)[:40]
    return f"{now.strftime('%Y%m%dT%H%M%S_%f')}Z-{safe_session}-{uuid.uuid4().hex[:8]}"


# --- inbox geometry ------------------------------------------------------------------------------
def tickets_root(board_path: Path) -> Path:
    return Path(board_path).parent / "logs" / "tickets"


def _inbox(board_path: Path) -> Path:
    return tickets_root(board_path) / "inbox"


def _archive(board_path: Path) -> Path:
    return tickets_root(board_path) / "archive"


def _rejected(board_path: Path) -> Path:
    return tickets_root(board_path) / "rejected"


def submit_ticket(board_path: Path, ticket: Ticket) -> Path:
    """Append a ticket to the inbox — the worker's *only* board-write surface.

    Exclusive + atomic: write to a temp file, fsync, then `os.link` it into place. `os.link` fails
    if the destination exists, so a duplicate `ticket_id` raises instead of clobbering, and a reader
    can never observe a half-written ticket. No lock, no board read — many workers submit
    concurrently without contending.
    """
    if ticket.intent not in _INTENTS:
        raise ValueError(f"unknown ticket intent: {ticket.intent!r}")
    inbox = _inbox(board_path)
    inbox.mkdir(parents=True, exist_ok=True)
    dest = inbox / f"{ticket.ticket_id}.json"
    fd, tmp = tempfile.mkstemp(dir=inbox, prefix=f".{ticket.ticket_id}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(ticket.model_dump_json())
            f.flush()
            os.fsync(f.fileno())
        os.link(tmp, dest)  # atomic exclusive create — raises FileExistsError on a duplicate id
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return dest


def submit_task_upsert(
    board_path: Path,
    task: "Task | dict[str, Any]",
    *,
    agent: str,
    session_id: str = "unknown",
    now: datetime | None = None,
) -> Path:
    """One-line producer: hand the keeper a whole task field-set as an upsert ticket.

    This is the conversion target for every writer that used to `load → extend → save_limen_file`.
    A generator/miner drops the ``save_limen_file`` and instead calls this once per NEW task; the
    keeper folds it onto the board on the next beat. The full field-set becomes the ticket ``patch``.

    The task is validated HERE (fail-fast, exactly like the old ``Task(**t)`` before a direct write),
    so a producer never emits an invalid task — the keeper's per-ticket validation stays a second
    line of defense, not the first. The emitted absent precondition makes this a create-only producer
    seam: a duplicate/stale generator ticket is quarantined instead of merging over a live lifecycle
    row. Owners use ``submit_task_status`` or an explicitly preconditioned raw ticket for updates.
    """
    validated = task if isinstance(task, Task) else Task.model_validate(task)
    validate_intake_contract(validated, is_new=True)
    fields = validated.model_dump(mode="json", exclude_none=True)
    tid = fields.get("id")
    if not tid:
        raise ValueError("task upsert requires an 'id'")
    now = now or datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_UPSERT,
        task_id=tid,
        patch=fields,
        precondition={"absent": True},
    )
    return submit_ticket(board_path, ticket)


def submit_task_status(
    board_path: Path,
    task_id: str,
    *,
    status: str,
    agent: str,
    session_id: str = "unknown",
    output: str | None = None,
    patch: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> Path:
    """One-line producer for status/result writers.

    A dispatcher/harvester that used to mutate ``task.status`` and append a dispatch log can hand
    the transition to TABVLARIVS instead. The optional ``patch`` is a field-level delta folded with
    the status; it must not carry a conflicting status.
    """
    if not task_id:
        raise ValueError("task status requires a task_id")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {', '.join(sorted(VALID_STATUSES))}")
    fields = dict(patch or {})
    if "status" in fields and fields["status"] != status:
        raise ValueError("status patch conflicts with status argument")
    fields["status"] = status
    now = now or datetime.now(timezone.utc)
    ticket = Ticket(
        ticket_id=new_ticket_id(session_id, now),
        timestamp=now,
        agent=agent,
        session_id=session_id,
        intent=INTENT_STATUS,
        task_id=task_id,
        patch=fields,
        log={"status": status, "output": output},
    )
    return submit_ticket(board_path, ticket)


@dataclass
class DrainResult:
    """The outcome of one drain pass — counts only (safe to log)."""

    pending: int = 0
    applied: int = 0
    rejected: int = 0
    wrote: bool = False
    deferred: bool = False
    note: str = ""
    applied_ids: list[str] = field(default_factory=list)
    rejected_ids: list[str] = field(default_factory=list)


@dataclass
class PreserveResult:
    changed: bool = False
    pushed: bool = False
    published: bool = False
    deferred: bool = False
    skipped: bool = False
    reason: str = ""
    commit: str = ""
    branch: str = ""
    pr_number: int = 0


def pending_count(board_path: Path) -> int:
    inbox = _inbox(board_path)
    return len(list(inbox.glob("*.json"))) if inbox.is_dir() else 0


def pending_upsert_patches(board_path: Path) -> list[dict[str, Any]]:
    """Return valid pending upsert patches without mutating the board.

    Producers use this as a read-side dedup hint: a task can be absent from the board but already
    waiting in the keeper inbox. Malformed tickets are ignored here; the drain pass owns quarantine.
    """
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return []
    patches: list[dict[str, Any]] = []
    for path in sorted(inbox.glob("*.json")):
        try:
            ticket = Ticket.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if ticket.intent == INTENT_UPSERT and isinstance(ticket.patch, dict):
            patches.append(ticket.patch)
    return patches


def pending_task_ids(board_path: Path) -> set[str]:
    ids: set[str] = set()
    for patch in pending_upsert_patches(board_path):
        tid = patch.get("id")
        if isinstance(tid, str) and tid:
            ids.add(tid)
    return ids


def _git(repo: Path, args: list[str], env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        ["git", *args],
        cwd=str(repo),
        env=merged_env,
        capture_output=True,
        text=True,
        timeout=120,
    )


def _short_output(proc: subprocess.CompletedProcess[str]) -> str:
    return (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[:220]


def _commit_identity_env(repo: Path, env: dict[str, str]) -> dict[str, str]:
    """Provide commit-tree identity defaults without mutating repo git config."""
    identity = dict(env)
    name = _git(repo, ["config", "user.name"], env=env).stdout.strip() or "Limen Tabularius"
    email = _git(repo, ["config", "user.email"], env=env).stdout.strip() or "tabularius@limen.local"
    identity.setdefault("GIT_AUTHOR_NAME", os.environ.get("GIT_AUTHOR_NAME", name))
    identity.setdefault("GIT_AUTHOR_EMAIL", os.environ.get("GIT_AUTHOR_EMAIL", email))
    identity.setdefault("GIT_COMMITTER_NAME", os.environ.get("GIT_COMMITTER_NAME", name))
    identity.setdefault("GIT_COMMITTER_EMAIL", os.environ.get("GIT_COMMITTER_EMAIL", email))
    return identity


def _gh(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _gh_json(repo: Path, args: list[str]) -> tuple[Any, str]:
    result = _gh(repo, args)
    if result.returncode != 0:
        return None, _short_output(result)
    try:
        return json.loads(result.stdout or "null"), ""
    except json.JSONDecodeError as exc:
        return None, f"invalid-json:{exc}"


def _repository_slug(repo: Path) -> tuple[str, str]:
    result = _gh(repo, ["repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"])
    slug = result.stdout.strip()
    if result.returncode != 0 or "/" not in slug:
        return "", _short_output(result) or "repository-unresolved"
    return slug, ""


def _remote_branch_sha(repo: Path, remote: str, branch: str) -> tuple[str, str]:
    result = _git(repo, ["ls-remote", "--heads", remote, f"refs/heads/{branch}"])
    if result.returncode != 0:
        return "", _short_output(result)
    line = result.stdout.strip()
    if not line:
        return "", ""
    fields = line.split()
    if len(fields) != 2 or fields[1] != f"refs/heads/{branch}":
        return "", "malformed-remote-ref"
    return fields[0], ""


_PUBLICATION_PR_FIELDS = (
    "number,headRefOid,baseRefName,isDraft,state,autoMergeRequest,mergeStateStatus,statusCheckRollup"
)


def _open_publication_pr(repo: Path, slug: str, publication_branch: str) -> tuple[dict[str, Any] | None, str]:
    data, error = _gh_json(
        repo,
        [
            "pr",
            "list",
            "--repo",
            slug,
            "--state",
            "open",
            "--head",
            publication_branch,
            "--limit",
            "1",
            "--json",
            _PUBLICATION_PR_FIELDS,
        ],
    )
    if error:
        return None, error
    if not isinstance(data, list):
        return None, "unexpected-pr-list"
    return (data[0] if data else None), ""


def _view_publication_pr(repo: Path, slug: str, pr_number: int) -> tuple[dict[str, Any] | None, str]:
    data, error = _gh_json(
        repo,
        ["pr", "view", str(pr_number), "--repo", slug, "--json", _PUBLICATION_PR_FIELDS],
    )
    if error:
        return None, error
    if not isinstance(data, dict):
        return None, "unexpected-pr-view"
    return data, ""


def _publication_pr_error(pr: dict[str, Any], *, expected_head: str, base_branch: str) -> str:
    """Validate the exact immutable PR custody contract."""

    if str(pr.get("state") or "") != "OPEN":
        return "pr-not-open"
    if bool(pr.get("isDraft")):
        return "pr-is-draft"
    if str(pr.get("baseRefName") or "") != base_branch:
        return "pr-base-mismatch"
    if str(pr.get("headRefOid") or "") != expected_head:
        return "pr-head-mismatch"
    return ""


def _publication_diff_error(
    repo: Path,
    *,
    base_sha: str,
    head_sha: str,
    rel_board: str,
) -> str:
    """Require the full PR diff—not merely the newest commit—to be exactly the board."""

    merge_base = _git(repo, ["merge-base", base_sha, head_sha])
    if merge_base.returncode != 0 or not merge_base.stdout.strip():
        return f"publication-merge-base-failed:{_short_output(merge_base)}"
    changed = _git(repo, ["diff", "--name-only", merge_base.stdout.strip(), head_sha])
    if changed.returncode != 0:
        return f"publication-diff-failed:{_short_output(changed)}"
    paths = {line.strip() for line in changed.stdout.splitlines() if line.strip()}
    if paths != {rel_board}:
        extras = sorted(paths - {rel_board})
        if extras:
            return f"publication-non-board-paths:{','.join(extras[:8])}"
        return "publication-empty-or-missing-board-diff"
    return ""


def _ensure_publication_pr(
    repo: Path,
    *,
    slug: str,
    base_branch: str,
    publication_branch: str,
    expected_head: str,
) -> tuple[int, str]:
    existing, error = _open_publication_pr(repo, slug, publication_branch)
    if error:
        return 0, f"pr-list-failed:{error}"
    if existing:
        validation_error = _publication_pr_error(
            existing,
            expected_head=expected_head,
            base_branch=base_branch,
        )
        if validation_error:
            return 0, validation_error
        return int(existing["number"]), ""

    created = _gh(
        repo,
        [
            "pr",
            "create",
            "--repo",
            slug,
            "--base",
            base_branch,
            "--head",
            publication_branch,
            "--title",
            BOARD_PUBLICATION_TITLE,
            "--body",
            (
                "Keeper-owned `tasks.yaml` projection. The branch is data-only, "
                "fast-forward-only, and must enter `main` through the normal merge queue."
            ),
        ],
    )
    if created.returncode != 0:
        return 0, f"pr-create-failed:{_short_output(created)}"
    try:
        pr_number = int(created.stdout.strip().rstrip("/").rsplit("/", 1)[-1])
    except ValueError:
        return 0, "pr-create-returned-no-number"

    viewed, error = _view_publication_pr(repo, slug, pr_number)
    if error:
        return 0, f"pr-view-failed:{error}"
    validation_error = _publication_pr_error(
        viewed or {},
        expected_head=expected_head,
        base_branch=base_branch,
    )
    if validation_error:
        return 0, f"pr-exact-head-unproven:{validation_error}"
    return pr_number, ""


def _dispatch_pr_gate(repo: Path, slug: str, publication_branch: str) -> str:
    """Give an Actions-authored PR its required check without polling.

    GitHub suppresses ordinary workflow cascades created by ``GITHUB_TOKEN``.
    ``workflow_dispatch`` is the documented exception, so the scheduled
    publisher explicitly starts the existing PR gate on the exact publication
    branch. Local/keyring pushes use the normal ``pull_request`` event.
    """

    if os.environ.get("GITHUB_ACTIONS", "").lower() != "true":
        return ""
    result = _gh(
        repo,
        ["workflow", "run", "pr-gate.yml", "--repo", slug, "--ref", publication_branch],
    )
    return "" if result.returncode == 0 else f"pr-gate-dispatch-failed:{_short_output(result)}"


def _arm_publication_pr(repo: Path, slug: str, pr_number: int, expected_head: str) -> str:
    """Arm the exact head; the remote squash-only queue owns the eventual merge method."""

    result = _gh(
        repo,
        [
            "pr",
            "merge",
            str(pr_number),
            "--repo",
            slug,
            "--auto",
            "--squash",
            "--match-head-commit",
            expected_head,
        ],
    )
    return "" if result.returncode == 0 else f"pr-auto-merge-failed:{_short_output(result)}"


def _pr_gate_observed(pr: dict[str, Any]) -> bool:
    return any(
        str(check.get("name") or check.get("context") or "") == "pr-gate"
        for check in (pr.get("statusCheckRollup") or [])
        if isinstance(check, dict)
    )


def _pr_merge_armed(pr: dict[str, Any]) -> bool:
    return pr.get("autoMergeRequest") is not None or str(pr.get("mergeStateStatus") or "") == "QUEUED"


def _ensure_publication_effects(
    repo: Path,
    *,
    slug: str,
    publication_branch: str,
    pr: dict[str, Any],
    expected_head: str,
) -> str:
    """Recoverably install the check and exact-head auto-merge effects once."""

    if os.environ.get("GITHUB_ACTIONS", "").lower() == "true" and not _pr_gate_observed(pr):
        dispatch_error = _dispatch_pr_gate(repo, slug, publication_branch)
        if dispatch_error:
            return dispatch_error
    if not _pr_merge_armed(pr):
        return _arm_publication_pr(repo, slug, int(pr.get("number") or 0), expected_head)
    return ""


def board_publication_preflight(
    board_path: Path,
    *,
    branch: str = "main",
    remote: str = "origin",
    publication_branch: str = BOARD_PUBLICATION_BRANCH,
) -> PreserveResult:
    """Admit an ephemeral producer only when no prior board publication is outstanding.

    The two Actions producers share a repository-wide concurrency group, but a previous run may
    already have a board PR waiting on CI or the merge queue. This probe runs before either producer
    mutates its disposable checkout. It also recovers a pushed-but-not-opened publication branch,
    verifies the complete PR diff is data-only, and arms exact-head auto-merge.
    """

    board_path = Path(board_path)
    top = _git(board_path.parent, ["rev-parse", "--show-toplevel"])
    if top.returncode != 0 or not top.stdout.strip():
        return PreserveResult(reason="not-a-git-repo", branch=publication_branch)
    repo = Path(top.stdout.strip())
    try:
        rel_board = board_path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return PreserveResult(reason="board-outside-git-root", branch=publication_branch)

    current = _git(repo, ["symbolic-ref", "--quiet", "--short", "HEAD"])
    if current.returncode != 0 or current.stdout.strip() != branch:
        return PreserveResult(reason=f"not-on-{branch}", branch=publication_branch)
    fetch = _git(repo, ["fetch", "--quiet", remote, branch])
    if fetch.returncode != 0:
        return PreserveResult(reason=f"fetch-failed:{_short_output(fetch)}", branch=publication_branch)
    base_sha = _git(repo, ["rev-parse", f"{remote}/{branch}"]).stdout.strip()
    if not base_sha:
        return PreserveResult(reason=f"missing-{remote}/{branch}", branch=publication_branch)

    slug, error = _repository_slug(repo)
    if error:
        return PreserveResult(reason=f"github-unavailable:{error}", branch=publication_branch)
    open_pr, error = _open_publication_pr(repo, slug, publication_branch)
    if error:
        return PreserveResult(reason=f"pr-list-failed:{error}", branch=publication_branch)
    publication_sha, error = _remote_branch_sha(repo, remote, publication_branch)
    if error:
        return PreserveResult(reason=f"publication-ref-failed:{error}", branch=publication_branch)
    if publication_sha:
        fetched = _git(repo, ["fetch", "--quiet", remote, f"refs/heads/{publication_branch}"])
        if fetched.returncode != 0:
            return PreserveResult(
                reason=f"publication-fetch-failed:{_short_output(fetched)}",
                branch=publication_branch,
            )

    if open_pr:
        pr_number = int(open_pr.get("number") or 0)
        validation_error = _publication_pr_error(
            open_pr,
            expected_head=publication_sha,
            base_branch=branch,
        )
        if not publication_sha or validation_error:
            return PreserveResult(
                reason=validation_error or "publication-pr-head-missing",
                branch=publication_branch,
                pr_number=pr_number,
            )
        diff_error = _publication_diff_error(
            repo,
            base_sha=base_sha,
            head_sha=publication_sha,
            rel_board=rel_board,
        )
        if diff_error:
            return PreserveResult(reason=diff_error, branch=publication_branch, pr_number=pr_number)
        effect_error = _ensure_publication_effects(
            repo,
            slug=slug,
            publication_branch=publication_branch,
            pr=open_pr,
            expected_head=publication_sha,
        )
        if effect_error:
            return PreserveResult(reason=effect_error, branch=publication_branch, pr_number=pr_number)
        return PreserveResult(
            published=True,
            deferred=True,
            reason="publication-in-flight",
            commit=publication_sha,
            branch=publication_branch,
            pr_number=pr_number,
        )

    if not publication_sha:
        return PreserveResult(published=True, skipped=True, reason="preflight-clear", branch=publication_branch)
    base_blob = _git(repo, ["rev-parse", f"{base_sha}:{rel_board}"]).stdout.strip()
    publication_blob = _git(repo, ["rev-parse", f"{publication_sha}:{rel_board}"]).stdout.strip()
    if not publication_blob:
        return PreserveResult(reason="publication-board-missing", branch=publication_branch)
    branch_tree_diff = _git(repo, ["diff", "--quiet", base_sha, publication_sha])
    if branch_tree_diff.returncode not in {0, 1}:
        return PreserveResult(
            reason=f"publication-diff-failed:{_short_output(branch_tree_diff)}",
            branch=publication_branch,
        )
    if branch_tree_diff.returncode == 0:
        return PreserveResult(published=True, skipped=True, reason="preflight-clear", branch=publication_branch)
    diff_error = _publication_diff_error(
        repo,
        base_sha=base_sha,
        head_sha=publication_sha,
        rel_board=rel_board,
    )
    if diff_error:
        return PreserveResult(reason=diff_error, branch=publication_branch)
    if publication_blob == base_blob:
        return PreserveResult(published=True, skipped=True, reason="preflight-clear", branch=publication_branch)
    pr_number, error = _ensure_publication_pr(
        repo,
        slug=slug,
        base_branch=branch,
        publication_branch=publication_branch,
        expected_head=publication_sha,
    )
    if error:
        return PreserveResult(reason=error, commit=publication_sha, branch=publication_branch)
    pr, error = _view_publication_pr(repo, slug, pr_number)
    if error:
        return PreserveResult(
            reason=f"pr-view-failed:{error}",
            commit=publication_sha,
            branch=publication_branch,
            pr_number=pr_number,
        )
    effect_error = _ensure_publication_effects(
        repo,
        slug=slug,
        publication_branch=publication_branch,
        pr=pr or {},
        expected_head=publication_sha,
    )
    if effect_error:
        return PreserveResult(
            reason=effect_error,
            commit=publication_sha,
            branch=publication_branch,
            pr_number=pr_number,
        )
    return PreserveResult(
        published=True,
        deferred=True,
        reason="publication-recovered",
        commit=publication_sha,
        branch=publication_branch,
        pr_number=pr_number,
    )


def preserve_board_projection(
    board_path: Path,
    *,
    branch: str = "main",
    remote: str = "origin",
    publication_branch: str = BOARD_PUBLICATION_BRANCH,
    manage_pr: bool = True,
    dry_run: bool = False,
    lock_timeout: int = 2,
) -> PreserveResult:
    """Publish the sealed board on a stable, fast-forward-only PR branch.

    ``main`` is never pushed or advanced locally. The temporary index starts
    from current ``origin/main`` (and, when needed, a synthetic merge parent
    that joins the prior publication head to current main), stages only the
    board, and pushes a normal fast-forward commit to
    ``tabularius/board-projection``. Exactly one open PR owns that immutable
    remote head; newer local board state coalesces while it is in flight.
    Competing publishers serialize at the remote ref because a stale
    non-fast-forward push is rejected. No force push or TOCTOU queue-ref probe
    is involved.
    """
    board_path = Path(board_path)
    with queue_lock(board_path, timeout=lock_timeout) as locked:
        if not locked:
            return PreserveResult(deferred=True, reason="queue-lock-held", branch=publication_branch)

        top = _git(board_path.parent, ["rev-parse", "--show-toplevel"])
        if top.returncode != 0 or not top.stdout.strip():
            return PreserveResult(skipped=True, reason="not-a-git-repo", branch=publication_branch)
        repo = Path(top.stdout.strip())
        try:
            rel_board = board_path.resolve().relative_to(repo.resolve()).as_posix()
        except ValueError:
            return PreserveResult(skipped=True, reason="board-outside-git-root", branch=publication_branch)

        status = _git(repo, ["status", "--porcelain", "--", rel_board])
        if status.returncode != 0:
            return PreserveResult(
                skipped=True,
                reason=f"status-failed:{_short_output(status)}",
                branch=publication_branch,
            )
        if not status.stdout.strip():
            return PreserveResult(published=True, skipped=True, reason="no-board-changes", branch=publication_branch)
        if dry_run:
            return PreserveResult(
                changed=True,
                skipped=True,
                reason=f"would-publish:{rel_board}",
                branch=publication_branch,
            )

        current = _git(repo, ["symbolic-ref", "--quiet", "--short", "HEAD"])
        if current.returncode != 0 or current.stdout.strip() != branch:
            return PreserveResult(skipped=True, reason=f"not-on-{branch}", branch=publication_branch)
        fetch = _git(repo, ["fetch", "--quiet", remote, branch])
        if fetch.returncode != 0:
            return PreserveResult(
                skipped=True,
                reason=f"fetch-failed:{_short_output(fetch)}",
                branch=publication_branch,
            )
        remote_ref = f"{remote}/{branch}"
        base_sha = _git(repo, ["rev-parse", remote_ref]).stdout.strip()
        if not base_sha:
            return PreserveResult(changed=True, skipped=True, reason=f"missing-{remote_ref}", branch=publication_branch)

        slug = ""
        open_pr: dict[str, Any] | None = None
        if manage_pr:
            slug, error = _repository_slug(repo)
            if error:
                return PreserveResult(
                    changed=True,
                    deferred=True,
                    reason=f"github-unavailable:{error}",
                    branch=publication_branch,
                )
            open_pr, error = _open_publication_pr(repo, slug, publication_branch)
            if error:
                return PreserveResult(
                    changed=True,
                    deferred=True,
                    reason=f"pr-list-failed:{error}",
                    branch=publication_branch,
                )

        publication_sha, error = _remote_branch_sha(repo, remote, publication_branch)
        if error:
            return PreserveResult(
                changed=True,
                deferred=True,
                reason=f"publication-ref-failed:{error}",
                branch=publication_branch,
            )
        if publication_sha:
            fetch_publication = _git(
                repo,
                [
                    "fetch",
                    "--quiet",
                    remote,
                    f"refs/heads/{publication_branch}",
                ],
            )
            if fetch_publication.returncode != 0:
                return PreserveResult(
                    changed=True,
                    deferred=True,
                    reason=f"publication-fetch-failed:{_short_output(fetch_publication)}",
                    branch=publication_branch,
                )

        local_blob = _git(repo, ["hash-object", "--", rel_board]).stdout.strip()
        publication_blob = (
            _git(repo, ["rev-parse", f"{publication_sha}:{rel_board}"]).stdout.strip() if publication_sha else ""
        )

        if open_pr:
            pr_number = int(open_pr.get("number") or 0)
            validation_error = _publication_pr_error(
                open_pr,
                expected_head=publication_sha,
                base_branch=branch,
            )
            if not publication_sha or validation_error:
                return PreserveResult(
                    changed=True,
                    deferred=True,
                    reason=validation_error or "publication-pr-head-missing",
                    branch=publication_branch,
                    pr_number=pr_number,
                )
            diff_error = _publication_diff_error(
                repo,
                base_sha=base_sha,
                head_sha=publication_sha,
                rel_board=rel_board,
            )
            if diff_error:
                return PreserveResult(
                    changed=True,
                    deferred=True,
                    reason=diff_error,
                    commit=publication_sha,
                    branch=publication_branch,
                    pr_number=pr_number,
                )
            effect_error = _ensure_publication_effects(
                repo,
                slug=slug,
                publication_branch=publication_branch,
                pr=open_pr,
                expected_head=publication_sha,
            )
            return PreserveResult(
                changed=True,
                published=bool(not effect_error and local_blob and local_blob == publication_blob),
                deferred=True,
                reason=effect_error or "publication-in-flight",
                commit=publication_sha,
                branch=publication_branch,
                pr_number=pr_number,
            )

        base_blob = _git(repo, ["rev-parse", f"{base_sha}:{rel_board}"]).stdout.strip()
        if local_blob and local_blob == base_blob:
            return PreserveResult(
                changed=True,
                published=True,
                skipped=True,
                reason="already-on-main",
                commit=base_sha,
                branch=publication_branch,
            )

        if manage_pr and publication_sha and publication_blob != base_blob:
            diff_error = _publication_diff_error(
                repo,
                base_sha=base_sha,
                head_sha=publication_sha,
                rel_board=rel_board,
            )
            if diff_error:
                return PreserveResult(
                    changed=True,
                    deferred=True,
                    reason=diff_error,
                    commit=publication_sha,
                    branch=publication_branch,
                )
            if publication_blob:
                pr_number, error = _ensure_publication_pr(
                    repo,
                    slug=slug,
                    base_branch=branch,
                    publication_branch=publication_branch,
                    expected_head=publication_sha,
                )
                if error:
                    return PreserveResult(
                        changed=True,
                        deferred=True,
                        reason=error,
                        commit=publication_sha,
                        branch=publication_branch,
                    )
                pr, error = _view_publication_pr(repo, slug, pr_number)
                if error:
                    return PreserveResult(
                        changed=True,
                        deferred=True,
                        reason=f"pr-view-failed:{error}",
                        commit=publication_sha,
                        branch=publication_branch,
                        pr_number=pr_number,
                    )
                effect_error = _ensure_publication_effects(
                    repo,
                    slug=slug,
                    publication_branch=publication_branch,
                    pr=pr or {},
                    expected_head=publication_sha,
                )
                return PreserveResult(
                    changed=True,
                    published=bool(not effect_error and local_blob and local_blob == publication_blob),
                    deferred=True,
                    reason=effect_error or "publication-in-flight",
                    commit=publication_sha,
                    branch=publication_branch,
                    pr_number=pr_number,
                )
            return PreserveResult(
                changed=True,
                deferred=True,
                reason="publication-board-missing",
                commit=publication_sha,
                branch=publication_branch,
            )

        parent_sha = base_sha
        read_tree_sha = base_sha
        if publication_sha:
            base_is_ancestor = _git(repo, ["merge-base", "--is-ancestor", base_sha, publication_sha])
            if base_is_ancestor.returncode == 0:
                parent_sha = publication_sha
                read_tree_sha = publication_sha
            else:
                base_tree = _git(repo, ["rev-parse", f"{base_sha}^{{tree}}"])
                if base_tree.returncode != 0 or not base_tree.stdout.strip():
                    return PreserveResult(
                        changed=True,
                        deferred=True,
                        reason=f"base-tree-failed:{_short_output(base_tree)}",
                        branch=publication_branch,
                    )
                bridge = _git(
                    repo,
                    [
                        "commit-tree",
                        base_tree.stdout.strip(),
                        "-p",
                        publication_sha,
                        "-p",
                        base_sha,
                        "-m",
                        f"tabularius: reconcile board branch with {branch} {base_sha[:12]}",
                    ],
                    env=_commit_identity_env(repo, {}),
                )
                if bridge.returncode != 0 or not bridge.stdout.strip():
                    return PreserveResult(
                        changed=True,
                        deferred=True,
                        reason=f"bridge-commit-failed:{_short_output(bridge)}",
                        branch=publication_branch,
                    )
                parent_sha = bridge.stdout.strip()
                read_tree_sha = parent_sha

        with tempfile.NamedTemporaryFile(prefix="tabularius-board-index-") as tmp:
            env = {"GIT_INDEX_FILE": tmp.name}
            read_tree = _git(repo, ["read-tree", read_tree_sha], env=env)
            if read_tree.returncode != 0:
                return PreserveResult(
                    changed=True,
                    skipped=True,
                    reason=f"read-tree-failed:{_short_output(read_tree)}",
                    branch=publication_branch,
                )
            add = _git(repo, ["add", "-A", "--", rel_board], env=env)
            if add.returncode != 0:
                return PreserveResult(
                    changed=True,
                    skipped=True,
                    reason=f"add-failed:{_short_output(add)}",
                    branch=publication_branch,
                )
            # DATA_ONLY invariant: the publication branch may carry only the
            # board projection; all code reaches main through its own PR.
            staged = _git(repo, ["diff", "--cached", "--name-only", parent_sha], env=env)
            staged_paths = {line.strip() for line in staged.stdout.splitlines() if line.strip()}
            if not staged_paths <= {rel_board}:
                raise AssertionError(
                    f"tabularius publication would carry non-board paths {sorted(staged_paths - {rel_board})}; "
                    "the DATA_ONLY invariant (only tasks.yaml may reach the board PR) was violated"
                )
            diff = _git(repo, ["diff", "--cached", "--quiet", parent_sha, "--", rel_board], env=env)
            if diff.returncode == 0:
                return PreserveResult(
                    published=True,
                    skipped=True,
                    reason="no-index-diff",
                    commit=parent_sha,
                    branch=publication_branch,
                )
            tree = _git(repo, ["write-tree"], env=env)
            if tree.returncode != 0 or not tree.stdout.strip():
                return PreserveResult(
                    changed=True,
                    skipped=True,
                    reason=f"write-tree-failed:{_short_output(tree)}",
                    branch=publication_branch,
                )
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            commit = _git(
                repo,
                [
                    "commit-tree",
                    tree.stdout.strip(),
                    "-p",
                    parent_sha,
                    "-m",
                    f"tabularius: preserve board projection {stamp}",
                ],
                env=_commit_identity_env(repo, env),
            )
            if commit.returncode != 0 or not commit.stdout.strip():
                return PreserveResult(
                    changed=True,
                    skipped=True,
                    reason=f"commit-tree-failed:{_short_output(commit)}",
                    branch=publication_branch,
                )
            commit_sha = commit.stdout.strip()

        candidate_diff_error = _publication_diff_error(
            repo,
            base_sha=base_sha,
            head_sha=commit_sha,
            rel_board=rel_board,
        )
        if candidate_diff_error:
            return PreserveResult(
                changed=True,
                deferred=True,
                reason=candidate_diff_error,
                commit=commit_sha,
                branch=publication_branch,
            )

        push = _git(repo, ["push", remote, f"{commit_sha}:refs/heads/{publication_branch}"])
        if push.returncode != 0:
            return PreserveResult(
                changed=True,
                deferred=True,
                reason=f"push-rejected:{_short_output(push)}",
                branch=publication_branch,
            )

        if not manage_pr:
            return PreserveResult(
                changed=True,
                pushed=True,
                published=True,
                commit=commit_sha,
                branch=publication_branch,
            )

        pr_number, error = _ensure_publication_pr(
            repo,
            slug=slug,
            base_branch=branch,
            publication_branch=publication_branch,
            expected_head=commit_sha,
        )
        if error:
            return PreserveResult(
                changed=True,
                pushed=True,
                deferred=True,
                reason=error,
                commit=commit_sha,
                branch=publication_branch,
            )
        pr, error = _view_publication_pr(repo, slug, pr_number)
        if error:
            return PreserveResult(
                changed=True,
                pushed=True,
                deferred=True,
                reason=f"pr-view-failed:{error}",
                commit=commit_sha,
                branch=publication_branch,
                pr_number=pr_number,
            )
        effect_error = _ensure_publication_effects(
            repo,
            slug=slug,
            publication_branch=publication_branch,
            pr=pr or {},
            expected_head=commit_sha,
        )
        return PreserveResult(
            changed=True,
            pushed=True,
            published=not effect_error,
            deferred=bool(effect_error),
            reason=effect_error,
            commit=commit_sha,
            branch=publication_branch,
            pr_number=pr_number,
        )


def _parse_pending(inbox: Path) -> tuple[list[tuple[Path, Ticket]], list[tuple[Path, str]]]:
    """Load every inbox ticket, splitting parseable from garbage, then order the good ones by
    (timestamp, id) so concurrent submissions replay in a single deterministic total order."""
    good: list[tuple[Path, Ticket]] = []
    bad: list[tuple[Path, str]] = []
    for p in sorted(inbox.glob("*.json")):
        try:
            good.append((p, Ticket.model_validate_json(p.read_text())))
        except Exception as exc:  # a torn/invalid ticket is quarantined, never fatal
            bad.append((p, f"unparseable/invalid ticket: {exc}"))
    good.sort(key=lambda pt: (pt[1].timestamp, pt[1].ticket_id))
    return good, bad


def _admit_exact_preconditions(
    pending: list[tuple[Path, Ticket]],
) -> tuple[list[tuple[Path, Ticket]], list[tuple[Path, str]]]:
    """Reject exact-state tickets that conflict anywhere in the captured batch.

    Sequential optimistic checks are insufficient: an archive ticket at T can
    satisfy its precondition and then a same-task claim at T+1 can reopen it in
    the same keeper drain.  Admission therefore inspects the entire
    lock-captured batch before folding any task.  Any other pending state event
    for the same task invalidates a ``task_sha256`` precondition regardless of
    timestamp order.  Only the guarded ticket is rejected; unrelated tickets
    and the conflicting owner event retain their normal append-only custody.
    """

    task_mutations = {INTENT_UPSERT, INTENT_STATUS, INTENT_REMOVE}
    by_task: dict[str, list[tuple[Path, Ticket]]] = {}
    for path, ticket in pending:
        if ticket.task_id and ticket.intent in task_mutations:
            by_task.setdefault(ticket.task_id, []).append((path, ticket))

    rejected: list[tuple[Path, str]] = []
    rejected_paths: set[Path] = set()
    for path, ticket in pending:
        if not ticket.task_id or "task_sha256" not in (ticket.precondition or {}):
            continue
        peers = [(peer_path, peer) for peer_path, peer in by_task.get(ticket.task_id, []) if peer_path != path]
        if not peers:
            continue
        peer_ids = sorted(peer.ticket_id for _, peer in peers)
        rejected_paths.add(path)
        rejected.append(
            (
                path,
                f"batch precondition failed: {ticket.task_id} has {len(peers)} other pending state event(s) "
                f"{peer_ids}; exact task state is invalidated regardless of timestamp order",
            )
        )
    return [(path, ticket) for path, ticket in pending if path not in rejected_paths], rejected


def _apply(ticket: Ticket, tasks: OrderedDict[str, dict[str, Any]], meta: dict[str, Any]) -> None:
    """Fold one ticket onto the in-memory board state (mutates `tasks`/`meta` in place).

    Validates the resulting single task so a malformed ticket raises HERE and is quarantined alone,
    rather than failing the whole-board validation at seal time and taking good tickets down with it.
    """
    if ticket.intent == INTENT_REMOVE:
        if not ticket.task_id:
            raise ValueError("task.remove requires task_id")
        existing = tasks.get(ticket.task_id)
        if (
            existing
            and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (existing.get("labels") or [])
            and existing.get("status") != "archived"
        ):
            raise ValueError(f"successor-required task {ticket.task_id} cannot be removed before explicit archival")
        tasks.pop(ticket.task_id, None)
        return

    if ticket.intent in (INTENT_UPSERT, INTENT_STATUS):
        if not ticket.task_id:
            raise ValueError(f"{ticket.intent} requires task_id")
        is_new = ticket.task_id not in tasks
        base = dict(tasks.get(ticket.task_id, {}))
        precondition = ticket.precondition or {}
        unknown_preconditions = set(precondition) - {"absent", "status", "task_sha256"}
        if unknown_preconditions:
            raise ValueError(f"unknown task preconditions: {sorted(unknown_preconditions)}")
        if precondition.get("absent") is True and not is_new:
            raise ValueError(f"task precondition failed: {ticket.task_id} is no longer absent")
        if "task_sha256" in precondition:
            if is_new:
                raise ValueError(f"task precondition failed: {ticket.task_id} is absent")
            actual_hash = task_state_sha256(base)
            if actual_hash != precondition["task_sha256"]:
                raise ValueError(
                    f"task precondition failed: {ticket.task_id} exact state changed "
                    f"({actual_hash[:12]} != {str(precondition['task_sha256'])[:12]})"
                )
        if "status" in precondition and base.get("status") != precondition["status"]:
            raise ValueError(
                f"task precondition failed: {ticket.task_id} status is {base.get('status')!r}, "
                f"expected {precondition['status']!r}"
            )
        merged = {**base, **(ticket.patch or {})}
        merged["id"] = ticket.task_id
        merged["updated"] = ticket.timestamp.isoformat()
        if ticket.log:
            status = ticket.log.get("status") or merged.get("status")
            entry = {
                "timestamp": ticket.timestamp.isoformat(),
                "agent": ticket.agent,
                "session_id": ticket.session_id,
                "status": status,
                "output": ticket.log.get("output"),
            }
            merged["dispatch_log"] = list(base.get("dispatch_log", [])) + [entry]
            # a task.status ticket carries the transition in its log payload; honor it as the status
            if ticket.intent == INTENT_STATUS and "status" not in (ticket.patch or {}) and status:
                merged["status"] = status
        if not is_new and WORKSTREAM_SUCCESSOR_REQUIRED_LABEL in (base.get("labels") or []):
            next_status = str(merged.get("status") or "")
            if next_status not in {"failed", "done", "archived"}:
                raise ValueError(
                    f"successor-required task {ticket.task_id} is terminal; create a new successor task "
                    f"instead of transitioning it to {next_status!r}"
                )
            if WORKSTREAM_SUCCESSOR_REQUIRED_LABEL not in (merged.get("labels") or []):
                raise ValueError(f"successor-required task {ticket.task_id} cannot drop its terminal hold label")
        validated = Task.model_validate(merged)  # reject a bad ticket individually
        # A caller can bypass ``submit_task_upsert`` by constructing a raw Ticket.
        # The keeper repeats admission independently so that ticket is quarantined
        # alone while valid siblings still land.
        validate_intake_contract(validated, is_new=is_new)
        tasks[ticket.task_id] = merged  # dict update keeps first-seen position; new id appends
        return

    if ticket.intent == INTENT_META:
        p = ticket.patch or {}
        candidate = dict(meta)
        if "version" in p:
            candidate["version"] = p["version"]
        if "portal" in p:
            if p["portal"] is not None and not isinstance(p["portal"], dict):
                raise ValueError("board.meta portal must be a mapping")
            candidate["portal"] = p["portal"]
        LimenFile.model_validate(
            {
                "version": candidate.get("version", "1.0"),
                "portal": candidate.get("portal"),
                "tasks": list(tasks.values()),
            }
        )
        meta.clear()
        meta.update(candidate)
        return

    if ticket.intent == INTENT_ORDER:
        ids = (ticket.patch or {}).get("ids", [])
        if not isinstance(ids, list) or any(not isinstance(tid, str) for tid in ids):
            raise ValueError("board.order ids must be a list of task id strings")
        meta["order"] = list(ids)
        return

    raise ValueError(f"unknown ticket intent: {ticket.intent!r}")


def _move(paths: list[Path], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p in paths:
        try:
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def _quarantine(rejected: list[tuple[Path, str]], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for p, reason in rejected:
        try:
            (dest_dir / f"{p.name}.reason.txt").write_text(reason)
            p.rename(dest_dir / p.name)
        except OSError:
            pass


def drain_once(board_path: Path, *, dry_run: bool = False, lock_timeout: int = 20) -> DrainResult:
    """Drain the inbox once: fold every pending ticket onto the board, seal, archive.

    The whole load→fold→seal runs under the queue lock, and the keeper is the only drainer, so there
    is no read-modify-write race. An empty inbox is an instant no-op (no lock, no board I/O) — which
    is what makes it safe to run every beat while no producers exist yet.
    """
    board_path = Path(board_path)
    inbox = _inbox(board_path)
    if not inbox.is_dir():
        return DrainResult(note="inbox empty")

    pending_hint = len(list(inbox.glob("*.json")))
    if pending_hint == 0:
        return DrainResult(note="inbox empty")

    if dry_run:
        good, bad = _parse_pending(inbox)
        admitted, precondition_rejections = _admit_exact_preconditions(good)
        pending = len(good) + len(bad)
        return DrainResult(
            pending=pending,
            applied=len(admitted),
            rejected=len(bad) + len(precondition_rejections),
            note=(
                f"dry-run: {len(admitted)} applicable, "
                f"{len(bad)} unparseable, {len(precondition_rejections)} precondition conflict(s)"
            ),
        )

    with queue_lock(board_path, timeout=lock_timeout) as locked:
        if not locked:
            return DrainResult(pending=pending_hint, deferred=True, note="queue lock held; deferred to next beat")

        # Parse only after taking the same lock used by phase publishers.  A
        # keeper can therefore observe either the complete published phase or
        # none of it, never an in-flight prefix captured before the lock.
        good, bad = _parse_pending(inbox)
        pending = len(good) + len(bad)
        if pending == 0:
            return DrainResult(note="inbox empty")

        board = load_limen_file(board_path)
        board_json = board.model_dump(mode="json", exclude_none=True)
        tasks: OrderedDict[str, dict[str, Any]] = OrderedDict((t["id"], t) for t in board_json.get("tasks", []))
        meta: dict[str, Any] = {"version": board_json.get("version", "1.0"), "portal": board_json.get("portal")}

        applied: list[tuple[Path, Ticket]] = []
        admitted, precondition_rejections = _admit_exact_preconditions(good)
        rejected: list[tuple[Path, str]] = [*bad, *precondition_rejections]
        for p, ticket in admitted:
            try:
                _apply(ticket, tasks, meta)
                applied.append((p, ticket))
            except Exception as exc:
                rejected.append((p, f"apply failed: {exc}"))

        wrote = False
        if applied:
            events: list[Event] = [
                {"type": EV_BOARD_META, "data": {"version": meta["version"], "portal": meta["portal"]}}
            ]
            for tid, fields in tasks.items():
                events.append({"type": EV_TASK_UPSERT, "task_id": tid, "data": fields})
            if meta.get("order"):
                events.append({"type": EV_BOARD_ORDER, "data": {"ids": meta["order"]}})
            try:
                new_board = fold(events)  # the proven reducer assembles + validates the whole board
            except Exception as exc:
                rejected.extend((p, f"batch rejected by board validation: {exc}") for p, _ in applied)
                applied = []
            else:
                try:
                    save_limen_file(board_path, new_board)  # collapse-guard + atomic seal
                    wrote = True
                except BoardCollapseError as exc:
                    # the batch would collapse the board — never write; quarantine it whole, board intact
                    rejected.extend((p, f"batch rejected by collapse-guard: {exc}") for p, _ in applied)
                    applied = []

        _move([p for p, _ in applied], _archive(board_path))
        _quarantine(rejected, _rejected(board_path))

    return DrainResult(
        pending=pending,
        applied=len(applied),
        rejected=len(rejected),
        wrote=wrote,
        note=("sealed" if wrote else "no board change"),
        applied_ids=[t.ticket_id for _, t in applied],
        rejected_ids=[p.stem for p, _ in rejected],
    )
