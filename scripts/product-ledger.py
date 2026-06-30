#!/usr/bin/env python3
"""Build the global prompt-to-product ledger.

The private index carries per-source owner records. The tracked summary only
keeps counts and public-safe routing information.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "product-ledger.json"
DOC_PATH = ROOT / "docs" / "product-ledger.md"
LIFECYCLE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
ACCEPTANCE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-acceptance-ledger.json"
REPO_SURFACE_INDEX = PRIVATE_ROOT / "lifecycle" / "repo-surface-ledger.json"
TASKS_PATH = Path(os.environ.get("LIMEN_TASKS", ROOT / "tasks.yaml"))
VALUE_REPOS_PATH = Path(os.environ.get("LIMEN_VALUE_REPOS", ROOT / "value-repos.json"))
POSITIONING_SEEDS_PATH = Path(os.environ.get("LIMEN_POSITIONING_SEEDS", ROOT / "positioning-seeds.json"))
CONTRIB_LEDGER_PATH = Path(os.environ.get("LIMEN_CONTRIB_LEDGER", HOME / "Workspace" / "organvm" / "contrib" / "LEDGER.yaml"))

PRODUCT_STATES = ("idea", "alpha", "build", "verify", "ship", "omega")
ACTIVE_STATES = {"idea", "alpha", "build", "verify", "ship"}


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def stable_hash(text: str, length: int = 20) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:length]


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def load_yaml(path: Path, default: Any) -> Any:
    try:
        obj = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return default
    return default if obj is None else obj


def value_repos(path: Path = VALUE_REPOS_PATH) -> set[str]:
    obj = load_json(path, {"repos": []})
    repos = obj.get("repos", []) if isinstance(obj, dict) else []
    return {str(item) for item in repos if item}


def positioned_repos(path: Path = POSITIONING_SEEDS_PATH) -> set[str]:
    obj = load_json(path, {"repos": {}})
    repos = obj.get("repos", {}) if isinstance(obj, dict) else {}
    if isinstance(repos, dict):
        return {str(key) for key in repos}
    return set()


def product_id(kind: str, source_key: str) -> str:
    return f"PROD-{kind}-{stable_hash(source_key, 16)}"


def record(
    *,
    kind: str,
    source_key: str,
    title: str,
    state: str,
    disposition: str,
    outward_path: str,
    owner: str,
    blocked: bool = False,
    gate: str = "",
    priority: int = 50,
    evidence: str = "",
) -> dict[str, Any]:
    if state not in PRODUCT_STATES:
        raise ValueError(f"invalid product state {state}")
    return {
        "id": product_id(kind, source_key),
        "source_kind": kind,
        "source_key_hash": stable_hash(source_key, 24),
        "title": title[:180],
        "state": state,
        "disposition": disposition,
        "outward_path": outward_path,
        "owner": owner,
        "blocked": blocked,
        "gate": gate,
        "priority": priority,
        "evidence": evidence[:240],
    }


def task_state(status: str) -> tuple[str, str, bool, str]:
    if status in {"open", "dispatched", "in_progress", "failed"}:
        return "build", "build", False, ""
    if status == "done":
        return "verify", "verify", False, ""
    if status == "archived":
        return "omega", "retire", False, ""
    if status == "failed_blocked":
        return "omega", "human-gated", True, "external blocker"
    if status == "needs_human":
        return "omega", "human-gated", True, "human decision required"
    return "idea", "build", False, ""


def records_from_tasks(path: Path = TASKS_PATH) -> list[dict[str, Any]]:
    raw = load_yaml(path, {"tasks": []})
    tasks = raw.get("tasks", []) if isinstance(raw, dict) else []
    rows: list[dict[str, Any]] = []
    for item in tasks:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        status = str(item.get("status") or "open")
        state, disposition, blocked, gate = task_state(status)
        labels = {str(label) for label in item.get("labels") or []}
        outward = "revenue-path" if labels & {"revenue", "product", "ship-order"} else "not_applicable"
        if "seo" in labels or "positioning" in labels:
            outward = "seo-proof"
        rows.append(
            record(
                kind="task",
                source_key=str(item["id"]),
                title=str(item.get("title") or item["id"]),
                state=state,
                disposition=disposition,
                outward_path=outward,
                owner=str(item.get("repo") or item.get("target_agent") or "tasks.yaml"),
                blocked=blocked,
                gate=gate,
                priority=20 if labels & {"revenue", "product", "ship-order"} else 60,
                evidence=f"tasks.yaml status={status}",
            )
        )
    return rows


def records_from_prompt_lifecycle(path: Path = LIFECYCLE_INDEX) -> list[dict[str, Any]]:
    obj = load_json(path, {"sessions": []})
    sessions = obj.get("sessions", []) if isinstance(obj, dict) else []
    rows: list[dict[str, Any]] = []
    for session in sessions:
        if not isinstance(session, dict):
            continue
        key = str(session.get("session_key") or session.get("path") or "")
        if not key:
            continue
        source = str(session.get("source") or "prompt-session")
        rows.append(
            record(
                kind="prompt",
                source_key=key,
                title=f"{source} prompt cluster",
                state="idea",
                disposition="build",
                outward_path="not_applicable",
                owner=source,
                priority=70,
                evidence=f"session source={source}",
            )
        )
    return rows


def records_from_value_repos() -> list[dict[str, Any]]:
    valued = value_repos()
    positioned = positioned_repos()
    rows: list[dict[str, Any]] = []
    for repo in sorted(valued | positioned):
        outward = "seo-proof" if repo in positioned else "publish-stage"
        disposition = "sell-ready" if repo in valued else "publish-stage"
        rows.append(
            record(
                kind="repo",
                source_key=repo,
                title=repo,
                state="ship" if repo in valued else "alpha",
                disposition=disposition,
                outward_path=outward,
                owner=repo,
                priority=10 if repo in valued else 35,
                evidence="value repo" if repo in valued else "positioning seed",
            )
        )
    return rows


def records_from_repo_surface(path: Path = REPO_SURFACE_INDEX) -> list[dict[str, Any]]:
    obj = load_json(path, {"repos": []})
    repos = obj.get("repos", []) if isinstance(obj, dict) else []
    rows: list[dict[str, Any]] = []
    for repo in repos:
        if not isinstance(repo, dict):
            continue
        key = str(repo.get("remote") or repo.get("path") or "")
        if not key:
            continue
        dirty = int(repo.get("dirty_entries") or 0)
        rows.append(
            record(
                kind="repo-surface",
                source_key=key,
                title=str(repo.get("display_path") or key),
                state="alpha",
                disposition="consolidate" if dirty else "build",
                outward_path="seo-proof" if repo.get("remote") else "not_applicable",
                owner=str(repo.get("remote") or repo.get("display_path") or "local repo"),
                blocked=False,
                priority=45 if dirty else 65,
                evidence=f"dirty_entries={dirty}",
            )
        )
    return rows


def records_from_contrib(path: Path = CONTRIB_LEDGER_PATH) -> list[dict[str, Any]]:
    obj = load_yaml(path, {})
    if not isinstance(obj, dict):
        return []
    items = obj.get("contributions") or obj.get("items") or obj.get("prs") or []
    rows: list[dict[str, Any]] = []
    if isinstance(items, dict):
        items = list(items.values())
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("url") or item.get("repo") or idx)
        status = str(item.get("status") or item.get("state") or "open").lower()
        blocked = status in {"blocked", "needs_human"}
        rows.append(
            record(
                kind="contrib",
                source_key=key,
                title=str(item.get("title") or item.get("repo") or key),
                state="ship" if status in {"merged", "closed"} else "build",
                disposition="publish-stage",
                outward_path="contrib-mirror",
                owner=str(item.get("repo") or item.get("owner") or "contrib"),
                blocked=blocked,
                gate="human-gated outbound action" if blocked else "",
                priority=25,
                evidence=f"contrib status={status}",
            )
        )
    return rows


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_id: dict[str, dict[str, Any]] = {}
    for row in records:
        old = by_id.get(row["id"])
        if old is None or int(row["priority"]) < int(old["priority"]):
            by_id[row["id"]] = row
    return sorted(by_id.values(), key=lambda row: (row["blocked"], int(row["priority"]), row["id"]))


def next_unblocked(records: list[dict[str, Any]], *, limit: int = 25) -> list[dict[str, Any]]:
    return [
        row
        for row in records
        if not row["blocked"] and row["state"] in ACTIVE_STATES
    ][:limit]


def build_snapshot() -> dict[str, Any]:
    records = dedupe_records(
        records_from_value_repos()
        + records_from_tasks()
        + records_from_prompt_lifecycle()
        + records_from_repo_surface()
        + records_from_contrib()
    )
    counts = {
        "states": dict(Counter(row["state"] for row in records)),
        "dispositions": dict(Counter(row["disposition"] for row in records)),
        "source_kinds": dict(Counter(row["source_kind"] for row in records)),
        "outward_paths": dict(Counter(row["outward_path"] for row in records)),
    }
    next_rows = next_unblocked(records)
    return {
        "generated_at": now_iso(),
        "product_count": len(records),
        "blocked_count": sum(1 for row in records if row["blocked"]),
        "global_status": "active" if next_rows else "blocked_or_complete",
        "counts": counts,
        "next_unblocked": next_rows,
        "products": records,
    }


def render_markdown(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Product Ledger",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Products: `{snapshot['product_count']}`",
        f"Blocked local: `{snapshot['blocked_count']}`",
        f"Global status: `{snapshot['global_status']}`",
        "",
        "## Counts",
        "",
    ]
    for group, counts in snapshot["counts"].items():
        rendered = ", ".join(f"`{key}` {value}" for key, value in sorted(counts.items())) or "none"
        lines.append(f"- {group}: {rendered}")
    lines += [
        "",
        "## Next Unblocked Products",
        "",
        "| Product | State | Disposition | Outward | Owner |",
        "|---|---|---|---|---|",
    ]
    for row in snapshot["next_unblocked"][:30]:
        lines.append(
            f"| `{row['id']}` | `{row['state']}` | `{row['disposition']}` | "
            f"`{row['outward_path']}` | `{row['owner']}` |"
        )
    lines += [
        "",
        "## Contract",
        "",
        "- A blocked product is local state, not a global stop condition.",
        "- Raw prompt bodies stay private; this tracked summary contains only product receipts and counts.",
        "- Every active product should eventually carry a build, proof, inward-money, or contribution mirror path.",
    ]
    return "\n".join(lines) + "\n"


def write_private(snapshot: dict[str, Any]) -> None:
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_summary(markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the alpha-to-omega product ledger.")
    parser.add_argument("--refresh", action="store_true", help="accepted for operator symmetry")
    parser.add_argument("--write", action="store_true", help="write private and redacted tracked outputs")
    parser.add_argument("--private", action="store_true", help="write ignored private product index")
    parser.add_argument("--redacted-summary", action="store_true", help="write tracked redacted summary")
    args = parser.parse_args()
    snapshot = build_snapshot()
    markdown = render_markdown(snapshot)
    write_private_flag = args.write or args.private
    write_summary_flag = args.write or args.redacted_summary
    if write_private_flag:
        write_private(snapshot)
    if write_summary_flag:
        write_summary(markdown)
    if not write_private_flag and not write_summary_flag:
        print(markdown, end="")
        print("product-ledger: dry-run")
    else:
        wrote = []
        if write_private_flag:
            wrote.append(str(PRIVATE_INDEX))
        if write_summary_flag:
            wrote.append(str(DOC_PATH))
        print(f"product-ledger: {snapshot['global_status']} products={snapshot['product_count']}; wrote {', '.join(wrote)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
