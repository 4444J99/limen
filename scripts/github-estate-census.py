#!/usr/bin/env python3
"""Produce the exhaustive GitHub-estate source report without GitHub search."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.github_estate_census import (  # noqa: E402
    ConnectionCensus,
    CursorFailure,
    build_github_estate_census,
    github_connection_query,
    paginate_exact,
)
from limen.local_git_census import collect_local_git_census  # noqa: E402
from limen.universe_baseline import build_universe_baseline_receipt  # noqa: E402


SOURCE_REPORT = ROOT / "logs" / "progress-sources" / "github-estate.json"
PRIVATE_FACTS = ROOT / "logs" / "github-estate-census-facts.json"
PRIVATE_CURSOR_CACHE = ROOT / "logs" / "github-estate-census-cursor-cache.json"
TRACKED_LEDGER = ROOT / "docs" / "github-estate-census.json"
UNIVERSE_BASELINE_RECEIPT = ROOT / "docs" / "receipts" / "universe-baseline.json"
SHIP = "scripts/ship-docs.sh"

# Every key whose value moves with the wall clock rather than with the estate, stripped at any
# depth before hashing. The pr-debt-trend.py lesson applies verbatim: the ledger's own
# `content_sha256` is computed over clock-driven fields, so it moves on every run and cannot
# answer "did anything but the clock move?".
VOLATILE_KEYS = frozenset(
    {
        "census_digest",
        "connection_receipt_digest",
        "content_sha256",
        "generated_at",
        "observed_at",
        "source_generation",
    }
)
CURSOR_CACHE_SCHEMA = "limen.github-estate-cursor-cache.v1"
CURSOR_RETRY_ATTEMPTS = 3


def _write_private_json(path: Path, value: object) -> None:
    """Atomically replace a private local receipt with owner-only permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            temporary = Path(handle.name)
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def _repository_generation(repositories: dict[str, dict[str, Any]]) -> str:
    return _canonical_sha256(
        [
            {
                "name_with_owner": name,
                "repository_id": row.get("repository_id"),
                "private": bool(row.get("private")),
                "archived": bool(row.get("archived")),
            }
            for name, row in sorted(repositories.items())
        ]
    )


def _load_cursor_cache(denominator_generation: str) -> tuple[str | None, dict[str, dict[str, Any]]]:
    if not PRIVATE_CURSOR_CACHE.exists():
        return None, {}
    try:
        payload = json.loads(PRIVATE_CURSOR_CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cursor-cache-corrupt:{exc.__class__.__name__}") from exc
    if not isinstance(payload, dict) or payload.get("schema") != CURSOR_CACHE_SCHEMA:
        raise RuntimeError("cursor-cache-corrupt:schema")
    if payload.get("denominator_generation") != denominator_generation or payload.get("complete") is True:
        return None, {}
    source_generation = payload.get("source_generation")
    if not isinstance(source_generation, str) or not source_generation:
        raise RuntimeError("cursor-cache-corrupt:source-generation")
    connections = payload.get("connections")
    if not isinstance(connections, dict) or not all(
        isinstance(key, str) and isinstance(value, dict) for key, value in connections.items()
    ):
        raise RuntimeError("cursor-cache-corrupt:connections")
    return source_generation, {str(key): dict(value) for key, value in connections.items()}


def _write_cursor_cache(
    denominator_generation: str,
    source_generation: str,
    connections: dict[str, dict[str, Any]],
    *,
    complete: bool,
) -> None:
    _write_private_json(
        PRIVATE_CURSOR_CACHE,
        {
            "schema": CURSOR_CACHE_SCHEMA,
            "denominator_generation": denominator_generation,
            "source_generation": source_generation,
            "complete": complete,
            "connections": dict(sorted(connections.items())),
        },
    )


def _connection_key(repository: str, kind: str) -> str:
    return f"{repository}\u0000{kind}"


def _failed_connection(
    repository: str,
    kind: str,
    expected_total: int | None,
    error: str,
    source_generation: str,
) -> ConnectionCensus:
    failure = CursorFailure(
        repository=repository,
        connection_kind=kind,
        cursor=None,
        error_class=error,
        attempt=1,
        expected_total=expected_total,
        retry_class="permanent",
    )
    return ConnectionCensus(
        kind=kind,
        expected_total=expected_total,
        page_count=0,
        exhaustive=False,
        end_cursor=None,
        nodes=(),
        error=error,
        failures=(failure,),
        source_generation=source_generation,
    )


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _git(*args: str, timeout: int = 60) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(ROOT), *args], capture_output=True, text=True, timeout=timeout, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return 1, ""
    return proc.returncode, proc.stdout


def _strip_volatile(node: object) -> object:
    if isinstance(node, dict):
        return {k: _strip_volatile(v) for k, v in node.items() if k not in VOLATILE_KEYS}
    if isinstance(node, list):
        return [_strip_volatile(v) for v in node]
    return node


def _stable_digest(blob: str) -> str | None:
    """Identity of an observation: the whole ledger minus every clock-driven field."""
    try:
        data = json.loads(blob)
    except ValueError:
        return None
    canonical = json.dumps(_strip_volatile(data), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _last_census_utc() -> datetime | None:
    """When THIS CHECKOUT last ran the census, from the gitignored receipt's mtime. None ⇒ never."""
    if not PRIVATE_FACTS.is_file():
        return None
    try:
        return datetime.fromtimestamp(PRIVATE_FACTS.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def _last_recorded_utc() -> datetime | None:
    """When an observation was last RECORDED, read from the committed ledger. None ⇒ unknown.

    The shared half of the clock (the pr-debt-trend two-clock rule): read from git rather than
    the working tree so every checkout — beat, worktree, session — answers "has anyone recorded
    recently?" identically.
    """
    rel = str(TRACKED_LEDGER.relative_to(ROOT))
    for ref in ("origin/main", "main", "HEAD"):
        rc, blob = _git("show", f"{ref}:{rel}")
        if rc != 0 or not blob.strip():
            continue
        try:
            stamp = (json.loads(blob).get("source_report") or {}).get("generated_at")
        except ValueError:
            continue
        if not isinstance(stamp, str) or not stamp:
            continue
        try:
            return datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            continue
    return None


def _due_reason(now: datetime, interval: int) -> str | None:
    """None ⇒ due. A string ⇒ why not. Due requires BOTH clocks stale (pr-debt #1859 lesson)."""
    for label, last in (
        ("this checkout swept", _last_census_utc()),
        ("an observation was recorded", _last_recorded_utc()),
    ):
        if last is None:
            continue
        age_h = (now - last).total_seconds() / 3600.0
        if age_h < interval:
            return f"not due — {label} {age_h:.1f}h ago (interval {interval}h)"
    return None


def record(*, workers: int, dry_run: bool) -> int:
    """Run the census when due; ship the tracked ledger only if the estate actually moved."""
    interval = _int("LIMEN_ESTATE_CENSUS_RECORD_INTERVAL_HOURS", 24)
    now = datetime.now(UTC)
    blocked = _due_reason(now, interval)
    if blocked is not None:
        print(f"estate-census-record: {blocked}")
        return 0

    rel = str(TRACKED_LEDGER.relative_to(ROOT))
    baseline_rel = str(UNIVERSE_BASELINE_RECEIPT.relative_to(ROOT))
    before = TRACKED_LEDGER.read_text(encoding="utf-8") if TRACKED_LEDGER.is_file() else ""
    before_digest = _stable_digest(before)

    if dry_run:
        print(f"estate-census-record: DUE (interval {interval}h, both clocks stale) — would run the census,")
        print(f"  then ship {rel} via {SHIP} only if the stable digest moves from {before_digest}")
        return 0

    full, tracked = collect(workers=workers)
    report = full["source_report"]
    SOURCE_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    _write_private_json(PRIVATE_FACTS, full)
    summary = tracked["summary"]
    debt = summary.get("debt_counts") or {}
    print(
        f"estate-census-record: census -> repositories={summary['repository_count']} "
        f"issues={debt.get('issue')} branches={debt.get('branch')} "
        f"exhaustive={str(report['exhaustive']).lower()}"
    )

    if not report["exhaustive"]:
        # A clipped census remains private diagnostic evidence and never replaces
        # either tracked authority. No working-tree rollback is needed because
        # the tracked files have not been touched.
        print("  ✗ census not exhaustive — partial estate not recorded")
        return 1

    after = json.dumps(tracked, indent=2, sort_keys=True) + "\n"
    after_digest = _stable_digest(after)
    if after_digest is None:
        print("  ✗ the census produced no readable ledger — nothing to record")
        return 1

    if after_digest == before_digest:
        print(f"  · no change (stable digest {after_digest[:12]}) — nothing shipped")
        return 0

    TRACKED_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    TRACKED_LEDGER.write_text(after, encoding="utf-8")
    UNIVERSE_BASELINE_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    UNIVERSE_BASELINE_RECEIPT.write_text(
        json.dumps(tracked["universe_baseline"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    msg = f"docs(fleet): record estate census observation (issues={debt.get('issue')}, branches={debt.get('branch')})"
    ship = subprocess.run(
        ["bash", str(ROOT / SHIP), "estate-census-observation", msg, rel, baseline_rel],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    tail = (ship.stdout or "").strip().splitlines()
    print(f"  ship-docs exit {ship.returncode}: {tail[-1] if tail else '(no output)'}")
    # 0 = merged, 2 = PR open awaiting merge-policy. Both preserve the observation on origin.
    if ship.returncode in (0, 2):
        print(f"  ✓ observation recorded ({(before_digest or '')[:12]} -> {after_digest[:12]})")
        return 0
    print(f"  ✗ ship-docs refused the observation: {(ship.stderr or '').strip()[:300]}")
    return 1


def _gitvs():
    path = ROOT / "scripts" / "gitvs.py"
    spec = importlib.util.spec_from_file_location("limen_gitvs_estate_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("gitvs adapter unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metadata(gitvs, repo: str) -> dict[str, Any] | None:
    try:
        owner, name = repo.split("/", 1)
    except ValueError:
        return None
    query = (
        "query($owner:String!,$name:String!){repository(owner:$owner,name:$name){"
        'updatedAt issues(states:OPEN){totalCount} refs(refPrefix:"refs/heads/"){totalCount} '
        "defaultBranchRef{name target{... on Commit{oid statusCheckRollup{state}}}}}}"
    )
    result = gitvs._gh_user(
        [
            "api",
            "graphql",
            "-f",
            f"query={query}",
            "-F",
            f"owner={owner}",
            "-F",
            f"name={name}",
        ],
        timeout=90,
    )
    if result.returncode != 0:
        return None
    try:
        repository = (json.loads(result.stdout or "{}").get("data") or {}).get("repository")
        if not isinstance(repository, dict):
            return None
        default_ref = repository.get("defaultBranchRef") or {}
        target = default_ref.get("target") or {}
        rollup = target.get("statusCheckRollup") or {}
        check_state = rollup.get("state")
        check_nodes = []
        if check_state:
            check_nodes.append(
                {
                    "id": f"default:{target.get('oid') or 'unknown'}",
                    "name": "default-branch-rollup",
                    "state": str(check_state),
                    "head_oid": target.get("oid"),
                    "url": None,
                }
            )
        normalized_check_state = str(check_state or "").upper()
        if normalized_check_state == "SUCCESS":
            default_check_status = "green"
        elif normalized_check_state in {"FAILURE", "ERROR"}:
            default_check_status = "red"
        elif normalized_check_state in {"PENDING", "EXPECTED"}:
            default_check_status = "pending"
        else:
            default_check_status = "unknown"
        return {
            "issues": int((repository.get("issues") or {})["totalCount"]),
            "branches": int((repository.get("refs") or {})["totalCount"]),
            "updated_at": repository.get("updatedAt"),
            "default_branch": default_ref.get("name"),
            "default_sha": target.get("oid"),
            "default_check_status": default_check_status,
            "checks": check_nodes,
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _remote_page(gitvs, repo: str, kind: str, cursor: str | None) -> dict[str, Any]:
    owner, name = repo.split("/", 1)
    query = github_connection_query(kind)
    args = [
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={name}",
    ]
    if cursor:
        args.extend(["-F", f"cursor={cursor}"])
    result = gitvs._gh_user(args, timeout=90)
    if result.returncode != 0:
        raise ValueError("github-page-unavailable")
    try:
        repository = (json.loads(result.stdout or "{}").get("data") or {}).get("repository")
        block = repository["connection"]
        nodes = []
        for raw in block.get("nodes") or []:
            node = dict(raw)
            if kind == "branches":
                node["head_oid"] = (node.pop("target", None) or {}).get("oid")
            nodes.append(node)
        page = block["pageInfo"]
        return {
            "total_count": int(block["totalCount"]),
            "nodes": nodes,
            "has_next_page": bool(page["hasNextPage"]),
            "end_cursor": page.get("endCursor"),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("github-page-invalid") from exc


def collect(*, workers: int = 8) -> tuple[dict[str, Any], dict[str, Any]]:
    gitvs = _gitvs()
    estate = gitvs.load_estate()
    requested = gitvs.owners(estate)
    online = not os.environ.get("LIMEN_OFFLINE") and shutil.which("gh") is not None
    canonical: list[str] = []
    owner_failures = 0
    if online:
        for owner in requested:
            resolved = gitvs._resolve_owner_login(owner, "user-native")
            if not resolved:
                owner_failures += 1
            elif resolved not in canonical:
                canonical.append(resolved)
    else:
        owner_failures = len(requested)

    def inventory_all() -> tuple[dict[str, dict[str, Any]], int, int]:
        inventory_rows: dict[str, dict[str, Any]] = {}
        page_count = 0
        failures = 0
        for owner in canonical:
            inventory = gitvs._owner_repo_inventory(owner, "user-native")
            if inventory is None:
                failures += 1
                continue
            page_count += int(inventory["page_count"])
            for raw in inventory["repositories"]:
                row = dict(raw)
                name = str(row["name_with_owner"])
                if name in inventory_rows:
                    failures += 1
                    continue
                inventory_rows[name] = row
        return inventory_rows, page_count, failures

    repositories, repository_pages, inventory_failures = inventory_all()
    owner_failures += inventory_failures
    denominator_generation = _repository_generation(repositories)
    cache_failure: str | None = None
    try:
        cached_generation, cursor_cache = _load_cursor_cache(denominator_generation)
    except RuntimeError as exc:
        cached_generation, cursor_cache = None, {}
        cache_failure = str(exc)
    now = datetime.now(UTC)
    source_generation = cached_generation or _canonical_sha256(
        {
            "denominator_generation": denominator_generation,
            "owners": canonical,
            "started_at": now.isoformat().replace("+00:00", "Z"),
        }
    )
    policy = estate.get("pr_debt_policy") or {}

    def resume_for(repo: str, kind: str) -> dict[str, Any] | None:
        return cursor_cache.get(_connection_key(repo, kind))

    def page_connection(
        repo: str,
        kind: str,
        expected_total: int,
        connection_generation: str,
    ) -> ConnectionCensus:
        return paginate_exact(
            kind,
            lambda cursor: _remote_page(gitvs, repo, kind, cursor),
            expected_total=expected_total,
            repository=repo,
            source_generation=connection_generation,
            resume=resume_for(repo, kind),
            max_attempts=CURSOR_RETRY_ATTEMPTS,
        )

    def collect_repository(
        repo: str,
    ) -> tuple[dict[str, Any], dict[str, ConnectionCensus], dict[str, ConnectionCensus]]:
        row = repositories[repo]
        metadata = _metadata(gitvs, repo)
        connection_generation = _canonical_sha256(
            {
                "source_generation": source_generation,
                "repository": repo,
                "repository_updated_at": metadata.get("updated_at") if metadata is not None else None,
                "default_sha": metadata.get("default_sha") if metadata is not None else None,
                "open_pr_total": int(row["open_pr_total"]),
                "issue_total": metadata.get("issues") if metadata is not None else None,
                "branch_total": metadata.get("branches") if metadata is not None else None,
            }
        )
        raw_results: dict[str, ConnectionCensus] = {}
        build_results: dict[str, ConnectionCensus] = {}

        pull_requests = page_connection(
            repo,
            "pull_requests",
            int(row["open_pr_total"]),
            connection_generation,
        )
        raw_results["pull_requests"] = pull_requests
        classified_nodes = tuple(
            gitvs._classify_open_pr(repo, node, policy, now) for node in pull_requests.nodes
        )
        build_results["pull_requests"] = replace(pull_requests, nodes=classified_nodes)

        if metadata is None:
            for kind in ("issues", "branches", "checks"):
                failed = _failed_connection(
                    repo,
                    kind,
                    None,
                    "repository-metadata-unavailable",
                    connection_generation,
                )
                raw_results[kind] = failed
                build_results[kind] = failed
            totals: dict[str, int] = {"pull_requests": int(row["open_pr_total"])}
            default_branch = None
            default_sha = None
            default_check_status = "unknown"
        else:
            issues = page_connection(repo, "issues", int(metadata["issues"]), connection_generation)
            branches = page_connection(repo, "branches", int(metadata["branches"]), connection_generation)
            checks = paginate_exact(
                "checks",
                lambda cursor: {
                    "total_count": len(metadata["checks"]),
                    "nodes": list(metadata["checks"]),
                    "has_next_page": False,
                    "end_cursor": None,
                }
                if cursor is None
                else (_ for _ in ()).throw(ValueError("unexpected-local-cursor")),
                expected_total=len(metadata["checks"]),
                repository=repo,
                source_generation=connection_generation,
                resume=resume_for(repo, "checks"),
                max_attempts=1,
            )
            for kind, result in (("issues", issues), ("branches", branches), ("checks", checks)):
                raw_results[kind] = result
                build_results[kind] = result
            totals = {
                "pull_requests": int(row["open_pr_total"]),
                "issues": int(metadata["issues"]),
                "branches": int(metadata["branches"]),
                "checks": len(metadata["checks"]),
            }
            default_branch = metadata["default_branch"]
            default_sha = metadata["default_sha"]
            default_check_status = metadata["default_check_status"]
        return (
            {
                "name_with_owner": repo,
                "repository_id": row.get("repository_id"),
                "private": bool(row["private"]),
                "archived": bool(row.get("archived")),
                "default_branch": default_branch,
                "default_sha": default_sha,
                "default_check_status": default_check_status,
                "connection_totals": totals,
            },
            raw_results,
            build_results,
        )

    evidence: list[dict[str, Any]] = []
    connection_results: dict[tuple[str, str], ConnectionCensus] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="github-estate") as executor:
        for repository, raw_results, build_results in executor.map(collect_repository, sorted(repositories)):
            repo = str(repository["name_with_owner"])
            evidence.append(repository)
            for kind, result in raw_results.items():
                cursor_cache[_connection_key(repo, kind)] = result.as_resume_dict()
            for kind, result in build_results.items():
                connection_results[(repo, kind)] = result
            _write_cursor_cache(
                denominator_generation,
                source_generation,
                cursor_cache,
                complete=False,
            )

    final_repositories, _, final_inventory_failures = inventory_all()
    repository_failures: list[dict[str, Any]] = []
    if cache_failure is not None:
        repository_failures.append(
            {
                "repository": None,
                "connection_kind": "cursor_cache",
                "cursor": None,
                "error_class": cache_failure,
                "attempt": 1,
                "expected_total": len(repositories),
                "retry_class": "corrupt",
            }
        )
    if final_inventory_failures or _repository_generation(final_repositories) != denominator_generation:
        repository_failures.append(
            {
                "repository": None,
                "connection_kind": "repositories",
                "cursor": None,
                "error_class": "repository-denominator-moved-during-generation",
                "attempt": 1,
                "expected_total": len(repositories),
                "retry_class": "corrupt",
            }
        )
    repository_complete = owner_failures == 0 and not repository_failures

    def unused_fetch(_repo: str, _kind: str, _cursor: str | None) -> dict[str, Any]:
        raise ValueError("precomputed-connection-missing")

    full, tracked = build_github_estate_census(
        evidence,
        unused_fetch,
        repository_cursor={
            "expected_total": len(repositories) if owner_failures == 0 else None,
            "page_count": repository_pages,
            "exhaustive": repository_complete,
            "failures": repository_failures,
        },
        now=now,
        connection_results=connection_results,
        source_generation=source_generation,
    )
    local_full, local_tracked = collect_local_git_census(ROOT, observed_at=now)
    baseline = build_universe_baseline_receipt(full, local_full)
    full["local_git_census"] = local_full
    full["universe_baseline"] = baseline.model_dump(mode="json")
    tracked["local_git_census"] = local_tracked
    tracked["universe_baseline"] = baseline.model_dump(mode="json")
    _write_cursor_cache(
        denominator_generation,
        source_generation,
        cursor_cache,
        complete=bool(full["source_report"]["exhaustive"]),
    )
    return full, tracked


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 unless every cursor is exhaustive")
    parser.add_argument(
        "--check-repositories",
        action="store_true",
        help="exit 1 unless the paginated repository denominator is exhaustive",
    )
    parser.add_argument("--json", action="store_true", help="print the redacted report summary")
    parser.add_argument("--write", action="store_true", help="write owner, source, and tracked receipts")
    parser.add_argument("--workers", type=int, default=8, help="bounded concurrent repository packets (1-32)")
    parser.add_argument(
        "--record", action="store_true", help="run the census when due; ship the tracked ledger on change"
    )
    parser.add_argument("--dry-run", action="store_true", help="with --record: report the decision, touch nothing")
    args = parser.parse_args()
    if args.workers < 1 or args.workers > 32:
        parser.error("--workers must be between 1 and 32")
    if args.record:
        return record(workers=args.workers, dry_run=args.dry_run)
    full, tracked = collect(workers=args.workers)
    report = full["source_report"]
    if args.write:
        SOURCE_REPORT.parent.mkdir(parents=True, exist_ok=True)
        SOURCE_REPORT.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        _write_private_json(PRIVATE_FACTS, full)
        TRACKED_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        TRACKED_LEDGER.write_text(json.dumps(tracked, indent=2, sort_keys=True) + "\n")
        UNIVERSE_BASELINE_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        UNIVERSE_BASELINE_RECEIPT.write_text(
            json.dumps(tracked["universe_baseline"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.json:
        print(json.dumps({"source_report": report, "summary": tracked["summary"]}, indent=2, sort_keys=True))
    else:
        mark = "✓" if report["exhaustive"] else "✗"
        print(
            f"{mark} github-estate-census: repositories={tracked['summary']['repository_count']} "
            f"known_leaves={tracked['summary']['known_leaf_count']} "
            f"exhaustive={str(report['exhaustive']).lower()} failures={tracked['summary']['failure_count']}"
        )
    repository_cursor = report["cursor"]["repository"]
    repository_census_complete = (
        repository_cursor["exhaustive"]
        and repository_cursor["expected_total"] is not None
        and repository_cursor["known_count"] == repository_cursor["expected_total"]
    )
    if args.check and not report["exhaustive"]:
        return 1
    if args.check_repositories and not repository_census_complete:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
