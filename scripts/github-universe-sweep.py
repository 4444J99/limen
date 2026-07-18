#!/usr/bin/env python3
"""github-universe-sweep — discover the live GitHub universe without bypassing the value gate.

The estate problem is not just "what repos exist?" but "what live obligations / opportunities already
exist across the repo universe?" Open issues and PRs are real discovery signals: they say a repo is not
actually dark, even when it is absent from value-repos.json. But the value-repos.json guard still stands:
Everything NOT listed there gets ZERO auto-generated / auto-mined dev work. So this sweep does NOT
promote every open GitHub item into budget-spending tasks. Instead it builds a durable item ledger at
repo#number granularity across the organvm org and the 4444J99 personal account, so unranked repos feed
into the existing discovery/ranking pipeline rather than vanishing.

For unranked repos, new open items land in github-universe-ledger.json with disposition `queued`; under
--retroactive, previously unseen closed items land as `reopen-candidate` (closed is reference state,
never a terminal disposition). For ranked repos ONLY, --emit-tasks may also submit bounded task-upsert
signals through TABVLARIVS, using the same intake contract validation path as discover-value.py.

Anti-flood: stable deterministic repo order, hard --max-new cap, resume seams (--since-repo / --repo),
read-only by default, atomic writes on --apply, and fail-open per repo so one bad API call never breaks
the beat. ([[no-never-happens-again]])
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
from limen.intake import contract_fields, github_existing_pr_contract, github_issue_contract  # noqa: E402
from limen.io import atomic_write_text, load_limen_file  # noqa: E402
from limen.models import Task  # noqa: E402
from limen.tabularius import pending_task_ids, submit_task_upsert  # noqa: E402

_LEDGER_SCHEMA = "limen.github_universe_ledger.v1"
_THINK_LANES = ["codex", "claude", "opencode"]
_DEFAULT_ORGS = "organvm"
_DEFAULT_USERS = "4444J99"
_TASK_PREFIX = "GH-UNIVERSE"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _root() -> Path:
    return Path(__file__).resolve().parent.parent


def _default_ledger_path() -> Path:
    return _root() / "github-universe-ledger.json"


def _default_tasks_path() -> Path:
    return Path(os.environ.get("LIMEN_TASKS", _root() / "tasks.yaml"))


def _scaffold_ledger() -> dict[str, Any]:
    return {
        "_doc": (
            "Durable item-granularity GitHub universe sweep ledger. Keys are <repo>#<number>. "
            "New open items seed as disposition queued; retroactive previously unseen closed items seed as "
            "reopen-candidate. Later engagement may promote rows to states such as evolving, distilled, "
            "merged, or superseded:<durable-receipt>. The vocabulary MUST NOT include closed or dismissed as "
            "ledger dispositions — GitHub state is reference data only, never terminal forgetting. "
            "Automatic task emission remains gated by value-repos.json: unranked repos are recorded here and "
            "fed into discovery/ranking, not directly budgeted into dev work.",
        ),
        "schema_version": _LEDGER_SCHEMA,
        "items": {},
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _scaffold_ledger()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if payload.get("schema_version") != _LEDGER_SCHEMA:
        raise ValueError(
            f"{path} has schema_version={payload.get('schema_version')!r}; expected {_LEDGER_SCHEMA!r}"
        )
    items = payload.get("items")
    if not isinstance(items, dict):
        raise ValueError(f"{path} must contain an object-valued 'items'")
    return payload


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    atomic_write_text(path, text)


def _split_csv_env(name: str, default: str) -> list[str]:
    raw = os.environ.get(name, default)
    return [part.strip() for part in raw.split(",") if part.strip()]


def _task_id(repo: str, kind: str, number: int) -> str:
    slug = repo.replace("/", "-").replace("_", "-").lower()
    return f"{_TASK_PREFIX}-{slug}-{kind}-{number}"


def _run_gh_json(args: list[str], *, timeout: int = 120) -> tuple[Any | None, str | None]:
    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except Exception as exc:
        return None, str(exc)
    if proc.returncode != 0:
        msg = (proc.stderr or proc.stdout or "gh api failed").strip().replace("\n", " ")[:300]
        return None, msg
    text = proc.stdout.strip()
    if not text:
        return None, None
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON from gh: {exc}"


def _flatten_slurp(payload: Any) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        out: list[dict[str, Any]] = []
        for item in payload:
            if isinstance(item, list):
                out.extend(obj for obj in item if isinstance(obj, dict))
            elif isinstance(item, dict):
                out.append(item)
        return out
    return []


def _repo_candidates(repo_overrides: list[str], include_forks: bool) -> tuple[list[str], list[str]]:
    override = repo_overrides or [r.strip() for r in os.environ.get("LIMEN_SWEEP_REPOS", "").split(",") if r.strip()]
    if override:
        return sorted(set(override), key=str.casefold), []

    repos: set[str] = set()
    errors: list[str] = []

    for org in _split_csv_env("LIMEN_ORGS", _DEFAULT_ORGS):
        payload, err = _run_gh_json(
            [
                "api",
                f"/orgs/{org}/repos",
                "--method",
                "GET",
                "--paginate",
                "--slurp",
                "-f",
                "per_page=100",
            ]
        )
        if err:
            errors.append(f"org {org}: {err}")
            continue
        for repo in _flatten_slurp(payload):
            if repo.get("archived"):
                continue
            if repo.get("fork") and not include_forks:
                continue
            full_name = str(repo.get("full_name") or "").strip()
            if full_name:
                repos.add(full_name)

    for user in _split_csv_env("LIMEN_GITHUB_USERS", _DEFAULT_USERS):
        payload, err = _run_gh_json(
            [
                "api",
                f"/users/{user}/repos",
                "--method",
                "GET",
                "--paginate",
                "--slurp",
                "-f",
                "per_page=100",
            ]
        )
        if err:
            errors.append(f"user {user}: {err}")
            continue
        for repo in _flatten_slurp(payload):
            if repo.get("archived"):
                continue
            if repo.get("fork") and not include_forks:
                continue
            full_name = str(repo.get("full_name") or "").strip()
            if full_name:
                repos.add(full_name)

    return sorted(repos, key=str.casefold), errors


def _trim_since_repo(repos: list[str], since_repo: str | None) -> list[str]:
    if not since_repo:
        return repos
    return [repo for repo in repos if repo.casefold() >= since_repo.casefold()]


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _priority(item: dict[str, Any], now: datetime) -> int:
    """Simple rank signal: age in days + 3*comment_count + 2*reaction_total_count.

    This is deliberately cheap and monotonic: older, discussed, reacted-to items float upward without
    pretending to be a full triage model.
    """

    created = _parse_dt(item.get("created_at"))
    age_days = max(0, int((now - created).total_seconds() // 86400)) if created else 0
    comments = int(item.get("comments") or 0)
    reactions = item.get("reactions") if isinstance(item.get("reactions"), dict) else {}
    reaction_total = int((reactions or {}).get("total_count") or 0)
    return age_days + (3 * comments) + (2 * reaction_total)


def _kind(item: dict[str, Any]) -> str:
    return "pr" if isinstance(item.get("pull_request"), dict) else "issue"


def _ledger_key(repo: str, number: int) -> str:
    return f"{repo}#{number}"


def _ranked_repos() -> set[str]:
    repos: set[str] = set()
    path = Path(os.environ.get("LIMEN_VALUE_REPOS_FILE", _root() / "value-repos.json"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return repos
    for raw in data.get("repos", []) if isinstance(data, dict) else []:
        if isinstance(raw, str):
            repos.add(raw)
        elif isinstance(raw, dict):
            repo = str(raw.get("repo") or "").strip()
            if repo:
                repos.add(repo)
    return repos


def _fetch_repo_items(repo: str, state: str) -> tuple[list[dict[str, Any]], str | None]:
    payload, err = _run_gh_json(
        [
            "api",
            f"repos/{repo}/issues",
            "--method",
            "GET",
            "--paginate",
            "--slurp",
            "-H",
            "Accept: application/vnd.github+json",
            "-f",
            f"state={state}",
            "-f",
            "per_page=100",
        ]
    )
    return _flatten_slurp(payload), err


def _default_disposition(state: str, item: dict[str, Any] | None = None) -> str:
    if state == "open":
        return "queued"
    # A closed PR that was actually merged is a resolved item, not a dismissal --
    # the issues API's `pull_request.merged_at` sub-field tells us this without a
    # second API call. Only genuinely closed-unmerged items are reopen-candidates.
    pr = (item or {}).get("pull_request") if isinstance(item, dict) else None
    if isinstance(pr, dict) and pr.get("merged_at"):
        return "merged"
    return "reopen-candidate"


def _upsert_entry(
    items: dict[str, Any],
    *,
    repo: str,
    item: dict[str, Any],
    now: datetime,
    retroactive: bool,
) -> tuple[str, bool, bool]:
    number = int(item.get("number"))
    key = _ledger_key(repo, number)
    existing = items.get(key)
    existed = isinstance(existing, dict)
    kind = _kind(item)
    state = str(item.get("state") or "")
    disposition = _default_disposition(state, item)
    if existed and str(existing.get("disposition") or "").strip():
        disposition = str(existing.get("disposition")).strip()
    elif state == "closed" and not retroactive:
        disposition = "queued"

    fresh = {
        "repo": repo,
        "number": number,
        "kind": kind,
        "title": str(item.get("title") or ""),
        "url": str(item.get("html_url") or ""),
        "state": state,
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "comments": int(item.get("comments") or 0),
        "reaction_count": int(((item.get("reactions") or {}) if isinstance(item.get("reactions"), dict) else {}).get("total_count") or 0),
        "priority": _priority(item, now),
        "disposition": disposition,
        "last_seen": _iso_z(now),
        "first_seen": str(existing.get("first_seen") or _iso_z(now)) if existed else _iso_z(now),
    }
    merged = dict(existing) if existed else {}
    merged.update(fresh)
    items[key] = merged
    is_new = not existed
    counted = state == "open" or (retroactive and state == "closed" and is_new)
    return key, is_new, counted


def _load_board_task_ids(tasks_path: Path) -> set[str]:
    try:
        board = load_limen_file(tasks_path)
    except Exception:
        return set()
    ids = {task.id for task in board.tasks if task.id}
    ids.update(pending_task_ids(tasks_path))
    return ids


def _emit_task(
    tasks_path: Path,
    *,
    repo: str,
    item: dict[str, Any],
    task_id: str,
    lane_index: int,
    session_id: str,
) -> None:
    number = int(item["number"])
    kind = _kind(item)
    contract = github_existing_pr_contract(repo, number) if kind == "pr" else github_issue_contract(repo, number)
    title = f"Sweep {repo}#{number}: engage open {kind.upper()}"
    context = (
        f"GitHub universe sweep found open {kind} {repo}#{number}: {item.get('title') or ''}. "
        f"This repo is already ranked in value-repos.json, so it is eligible for real follow-up work. "
        f"Triage the item, decide whether to act, and land the durable next receipt without bypassing the "
        f"existing repo priority contract."
    )
    task = Task(
        id=task_id,
        title=title,
        repo=repo,
        type="research",
        target_agent=_THINK_LANES[lane_index % len(_THINK_LANES)],
        priority="medium",
        budget_cost=1,
        status="open",
        labels=["github-universe", kind, "triage"],
        urls=[str(item.get("html_url") or "")],
        context=context,
        depends_on=[],
        created=_utc_now().date().isoformat(),
        dispatch_log=[],
        **contract_fields(contract),
    )
    submit_task_upsert(tasks_path, task, agent="github-universe-sweep", session_id=session_id)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=str(_default_tasks_path()))
    ap.add_argument("--ledger", default=str(_default_ledger_path()))
    ap.add_argument("--max-new", type=int, default=int(os.environ.get("LIMEN_GITHUB_UNIVERSE_MAX_NEW", "200")))
    ap.add_argument("--since-repo", help="resume from this full_name (inclusive, lexical order)")
    ap.add_argument("--repo", action="append", default=[], help="scan only this repo (repeatable)")
    ap.add_argument("--include-forks", action="store_true")
    ap.add_argument("--retroactive", action="store_true", help="seed unseen closed items as reopen-candidate")
    ap.add_argument("--apply", action="store_true", help="write github-universe-ledger.json atomically")
    ap.add_argument(
        "--emit-tasks",
        action="store_true",
        help="for ranked repos only, submit task-upsert signals for newly seen open items (requires --apply)",
    )
    ap.add_argument(
        "--max-task-upserts",
        type=int,
        default=int(os.environ.get("LIMEN_GITHUB_UNIVERSE_MAX_TASK_UPSERTS", "25")),
        help="hard cap on task upserts emitted in one run",
    )
    args = ap.parse_args()

    if args.max_new < 1:
        print("max-new must be >= 1")
        return 0
    if args.max_task_upserts < 0:
        print("max-task-upserts must be >= 0")
        return 0
    if args.emit_tasks and not args.apply:
        print("--emit-tasks requires --apply (read-only runs never submit task tickets).")
        return 0

    now = _utc_now()
    ledger_path = Path(args.ledger)
    tasks_path = Path(args.tasks)
    try:
        ledger = _load_json(ledger_path)
    except ValueError as exc:
        print(f"ledger unreadable; refusing to write: {exc}")
        return 0

    items = ledger.setdefault("items", {})
    if not isinstance(items, dict):
        print(f"ledger unreadable; refusing to write: {ledger_path} has non-object 'items'")
        return 0

    ranked = _ranked_repos()
    repos, repo_errors = _repo_candidates(args.repo, args.include_forks)
    repos = _trim_since_repo(repos, args.since_repo)
    if not repos:
        print("no repos selected — nothing to sweep.")
        if repo_errors:
            print("errors:")
            for err in repo_errors:
                print(f"- {err}")
        return 0

    existing_task_ids = _load_board_task_ids(tasks_path) if args.emit_tasks else set()
    session_id = os.environ.get("LIMEN_SESSION_ID", "github-universe-sweep")

    repos_scanned = 0
    open_found = 0
    closed_found = 0
    new_entries = 0
    known_entries = 0
    emitted_tasks = 0
    errors = list(repo_errors)
    stop_repo: str | None = None
    lane_index = 0

    for repo in repos:
        if new_entries >= args.max_new:
            stop_repo = repo
            break

        repos_scanned += 1
        open_items, err = _fetch_repo_items(repo, "open")
        if err:
            errors.append(f"{repo} open: {err}")
            continue

        for item in open_items:
            if not isinstance(item, dict) or not item.get("number"):
                continue
            open_found += 1
            key, is_new, counted = _upsert_entry(items, repo=repo, item=item, now=now, retroactive=False)
            if is_new and counted:
                new_entries += 1
            else:
                known_entries += 1
            if args.emit_tasks and is_new and repo in ranked and emitted_tasks < args.max_task_upserts:
                task_id = _task_id(repo, _kind(item), int(item["number"]))
                if task_id not in existing_task_ids:
                    try:
                        _emit_task(
                            tasks_path,
                            repo=repo,
                            item=item,
                            task_id=task_id,
                            lane_index=lane_index,
                            session_id=session_id,
                        )
                        emitted_tasks += 1
                        existing_task_ids.add(task_id)
                        lane_index += 1
                    except Exception as exc:
                        errors.append(f"{repo}#{item['number']} task-upsert: {exc}")
            if new_entries >= args.max_new:
                stop_repo = repo
                break

        if stop_repo:
            break

        if not args.retroactive or new_entries >= args.max_new:
            continue

        closed_items, err = _fetch_repo_items(repo, "closed")
        if err:
            errors.append(f"{repo} closed: {err}")
            continue
        for item in closed_items:
            if not isinstance(item, dict) or not item.get("number"):
                continue
            key = _ledger_key(repo, int(item["number"]))
            if key in items:
                continue
            closed_found += 1
            _, is_new, counted = _upsert_entry(items, repo=repo, item=item, now=now, retroactive=True)
            if is_new and counted:
                new_entries += 1
            else:
                known_entries += 1
            if new_entries >= args.max_new:
                stop_repo = repo
                break

    print(
        f"# github-universe-sweep: repos-scanned={repos_scanned}/{len(repos)} "
        f"open-found={open_found} closed-found={closed_found} new={new_entries} known={known_entries} "
        f"task-upserts={emitted_tasks} errors={len(errors)}"
    )
    print(f"ledger: {ledger_path}")
    if stop_repo:
        print(f"stopped at cap (--max-new={args.max_new}); resume with --since-repo {stop_repo}")
    if errors:
        print("errors:")
        for err in errors[:20]:
            print(f"- {err}")
        if len(errors) > 20:
            print(f"- ... {len(errors) - 20} more")

    if args.apply:
        _save_json(ledger_path, ledger)
        print(f"applied: wrote ledger -> {ledger_path}")
        if args.emit_tasks:
            print(f"applied: submitted {emitted_tasks} ranked-repo task upserts -> {tasks_path}")
    else:
        print("dry-run — re-run with --apply to write the ledger.")
        if args.emit_tasks:
            print("dry-run note: task upserts suppressed until --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
