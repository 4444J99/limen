#!/usr/bin/env python3
"""Rank possible attack paths from the redacted session/prompt corpus.

The point is to avoid willy-nilly delegation. This script reads the private
hash-only lifecycle indexes, scores possible lanes, and emits:

* tracked docs/session-attack-paths.md: redacted ranked paths and rules;
* ignored .limen-private/.../session-attack-paths.json: structured evidence.

No raw prompt text is read from the source app stores here; ordering derives from
the already-built private redacted indexes and receipt ledgers.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(
    os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus")
)
PROMPT_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
CODEX_INDEX = PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
BLOCKER_INDEX = PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
PRESSURE_INDEX = ROOT / "logs" / "session-lifecycle-pressure.json"
DOC_PATH = ROOT / "docs" / "session-attack-paths.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
PRESERVATION_RECEIPTS = ROOT / "docs" / "worktree-preservation-receipts.json"


FAMILY_WEIGHTS = {
    "worktree_lifecycle": {"score": 32, "agent": "codex/openCode", "path": "Preserve dirty or missing-remote roots, then reclaim duplicate local state."},
    "session_lifecycle": {"score": 30, "agent": "codex", "path": "Keep corpus/session ledgers current, collapse repeats into owner receipts."},
    "github_review": {"score": 26, "agent": "opencode/jules", "path": "Review PR/issue receipts only after owner repo, predicate, and blocker are explicit."},
    "technical_debt_ci": {"score": 24, "agent": "opencode/jules", "path": "Run narrow predicates and preserve failures in owner repos."},
    "agent_coordination": {"score": 22, "agent": "codex", "path": "Packetize bounded work; do not dispatch broad sprawl prompts."},
    "convergence_corpus": {"score": 20, "agent": "codex", "path": "Promote durable atoms through session-meta and knowledge-corpus."},
    "product_surface": {"score": 18, "agent": "opencode/jules", "path": "Route by repo and revenue/product predicate after preservation."},
    "auth_credentials": {"score": 4, "agent": "human/codex-prep", "path": "Park unless directly required by a scoped account/setup task."},
    "uncategorized": {"score": 10, "agent": "codex", "path": "Inspect privately and add classifier/owner route."},
}

REASON_WEIGHTS = {
    "dirty": 50,
    "not-a-git-dir": 42,
    "not-merged-to-default": 36,
    "clean+merged+idle": 20,
    "active(<6h)": 10,
}


def load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def fmt_bytes(n: int) -> str:
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    value = float(n)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{n} B"


def parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def recency_weight(latest: str | None, now: dt.datetime) -> tuple[int, str]:
    parsed = parse_ts(latest)
    if parsed is None:
        return 0, "unknown"
    age = now - parsed
    if age.total_seconds() < 0:
        return 18, "future/clock-skew"
    days = age.total_seconds() / 86400
    if days <= 1:
        return 18, "<=1d"
    if days <= 7:
        return 12, "<=7d"
    if days <= 30:
        return 6, "<=30d"
    return 2, ">30d lineage"


def remote_receipts_by_root(prompt: dict[str, Any]) -> dict[str, dict[str, Any]]:
    receipts = {}
    for receipt in ((prompt.get("remote") or {}).get("worktrees") or {}).get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        name = receipt.get("name")
        if name:
            receipts[str(name)] = receipt
    return receipts


def preservation_receipts_by_root(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    receipts: dict[str, dict[str, Any]] = {}
    for receipt in data.get("receipts") or []:
        if not isinstance(receipt, dict):
            continue
        root = receipt.get("root") or receipt.get("id")
        if root:
            receipts[str(root)] = receipt
    return receipts


def latest_by_worktree(prompt: dict[str, Any]) -> dict[str, str]:
    latest: dict[str, str] = {}
    for session in prompt.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        slug = session.get("worktree_slug")
        mtime = session.get("mtime")
        if not slug or not mtime:
            continue
        slug = str(slug)
        if slug not in latest or str(mtime) > latest[slug]:
            latest[slug] = str(mtime)
    return latest


def build_worktree_paths(
    prompt: dict[str, Any],
    pressure: dict[str, Any],
    now: dt.datetime,
    preservation_receipts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    sessions_by_worktree = Counter(prompt.get("sessions_by_worktree") or {})
    prompts_by_worktree = Counter(prompt.get("prompt_events_by_worktree") or {})
    latest_by_root = latest_by_worktree(prompt)
    remote_by_root = remote_receipts_by_root(prompt)
    paths: list[dict[str, Any]] = []
    local_pressure_bonus = 10 if int((pressure.get("worktrees") or {}).get("bytes") or 0) > 1024**3 else 0
    for item in (prompt.get("worktree_report") or {}).get("items") or []:
        if not isinstance(item, dict):
            continue
        root = str(item.get("name") or "")
        reason = str(item.get("reason") or "unknown")
        receipt = remote_by_root.get(root, {})
        remote_missing = receipt.get("remote_branch") == "missing"
        not_git = receipt.get("remote_branch") == "not-a-git-dir" or reason == "not-a-git-dir"
        open_prs = [pr for pr in receipt.get("prs", []) if isinstance(pr, dict) and pr.get("state") == "OPEN"]
        merged_prs = [pr for pr in receipt.get("prs", []) if isinstance(pr, dict) and pr.get("state") == "MERGED"]
        preservation = preservation_receipts.get(root)
        prompt_events = int(prompts_by_worktree.get(root, 0))
        recency_score, recency_label = recency_weight(latest_by_root.get(root), now)
        score = (
            REASON_WEIGHTS.get(reason, 18)
            + min(12, prompt_events // 10)
            + recency_score
            + local_pressure_bonus
            + (12 if remote_missing else 0)
            + (10 if not_git else 0)
            - (18 if open_prs else 0)
            - (24 if merged_prs and reason == "clean+merged+idle" else 0)
        )
        if reason == "active(<6h)":
            lane = "observe"
            action = "Keep active work visible; do not interrupt unless it becomes stale."
        elif preservation:
            lane = str(preservation.get("lane") or "owner-blocker")
            action = str(
                preservation.get("next_action")
                or "Private preservation receipt exists; classify owner intent before cleanup or delegation."
            )
            score -= int(preservation.get("score_discount") or 30)
        elif not_git:
            lane = "residue"
            action = "Inspect for unique files; if only cache/generated residue, record owner receipt before reclaiming."
        elif reason == "dirty":
            lane = "preserve"
            action = "Inspect diff, run owner predicate, push branch/open draft PR or record blocker."
        elif open_prs:
            lane = "remote-close"
            action = "Review PR state/checks, then merge or name supersession before local reclaim."
        else:
            lane = "remote-proof"
            action = "Verify remote/default preservation; reclaim local checkout only after exact proof."
        paths.append(
            {
                "kind": "worktree",
                "id": root,
                "score": score,
                "lane": lane,
                "reason": reason,
                "session_files": int(sessions_by_worktree.get(root, 0)),
                "prompt_events": prompt_events,
                "latest_receipt": latest_by_root.get(root),
                "recency": recency_label,
                "remote_branch": receipt.get("remote_branch", "unknown"),
                "open_prs": len(open_prs),
                "merged_prs": len(merged_prs),
                "preservation_status": (preservation or {}).get("status"),
                "preservation_receipt": (preservation or {}).get("private_receipt"),
                "agent_fit": "codex first; opencode/jules after packetization",
                "next_action": action,
            }
        )
    return paths


def latest_by_family(codex: dict[str, Any]) -> dict[str, str]:
    latest: dict[str, str] = {}
    for session in codex.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        family = session.get("family")
        mtime = session.get("mtime")
        if not family or not mtime:
            continue
        family = str(family)
        if family not in latest or str(mtime) > latest[family]:
            latest[family] = str(mtime)
    return latest


def build_family_paths(codex: dict[str, Any], blockers: dict[str, Any], now: dt.datetime) -> list[dict[str, Any]]:
    blocker_categories = Counter(
        item.get("category")
        for item in blockers.get("blockers", [])
        if isinstance(item, dict) and item.get("category")
    )
    latest = latest_by_family(codex)
    paths = []
    for family in codex.get("families") or []:
        if not isinstance(family, dict):
            continue
        name = str(family.get("family") or "uncategorized")
        weights = FAMILY_WEIGHTS.get(name, FAMILY_WEIGHTS["uncategorized"])
        states = family.get("states") or {}
        stalled = int(states.get("STALLED") or 0)
        parked = int(states.get("PARKED") or 0)
        sessions = int(family.get("sessions") or 0)
        prompt_events = int(family.get("prompt_events") or 0)
        recency_score, recency_label = recency_weight(latest.get(name), now)
        score = weights["score"] + min(12, sessions // 20) + min(10, prompt_events // 200) + recency_score
        if parked and name == "auth_credentials":
            score -= 45
        if stalled:
            score += min(25, stalled)
        if name == "worktree_lifecycle" and blocker_categories.get("worktree_lifecycle"):
            score += 10
        if name == "auth_credentials" and blocker_categories.get("auth_credentials"):
            lane = "parked"
            next_action = "Keep hung as credential workstream; prepare only non-secret prerequisites."
        else:
            lane = "family"
            next_action = weights["path"]
        paths.append(
            {
                "kind": "family",
                "id": name,
                "score": score,
                "lane": lane,
                "sessions": sessions,
                "states": states,
                "prompt_events": prompt_events,
                "latest_receipt": latest.get(name),
                "recency": recency_label,
                "agent_fit": weights["agent"],
                "next_action": next_action,
            }
        )
    return paths


def build_blocker_paths(blockers: dict[str, Any]) -> list[dict[str, Any]]:
    paths = []
    for blocker in blockers.get("blockers") or []:
        if not isinstance(blocker, dict):
            continue
        category = str(blocker.get("category") or "unknown")
        status = str(blocker.get("status") or "parked")
        base = {
            "capability_substrate": 38,
            "local_lean": 74,
            "worktree_lifecycle": 70,
            "owner_state": 42,
            "remote_receipt": 62,
            "cloud_runtime": 18,
            "auth_credentials": 6,
        }.get(category, 20)
        if status == "needs_refresh":
            base += 10
        if category == "auth_credentials":
            lane = "parked"
            agent = "human/codex-prep"
        elif category == "local_lean":
            lane = "drain"
            agent = "codex"
        elif category == "capability_substrate":
            lane = "blocker"
            agent = "codex"
        else:
            lane = "blocker"
            agent = "codex"
        paths.append(
            {
                "kind": "blocker",
                "id": str(blocker.get("id") or category),
                "score": base,
                "lane": lane,
                "category": category,
                "status": status,
                "agent_fit": agent,
                "next_action": str(blocker.get("route") or "Record owner route before action."),
            }
        )
    return paths


def build_snapshot() -> dict[str, Any]:
    prompt = load_json(PROMPT_INDEX)
    codex = load_json(CODEX_INDEX)
    blockers = load_json(BLOCKER_INDEX)
    pressure = load_json(PRESSURE_INDEX)
    preservation_receipts = preservation_receipts_by_root(load_json(PRESERVATION_RECEIPTS))
    now = dt.datetime.now(dt.timezone.utc)
    candidates = (
        build_worktree_paths(prompt, pressure, now, preservation_receipts)
        + build_family_paths(codex, blockers, now)
        + build_blocker_paths(blockers)
    )
    ranked = sorted(candidates, key=lambda item: (-int(item["score"]), item["kind"], item["id"]))
    lane_counts = Counter(item["lane"] for item in ranked)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "inputs": {
            "prompt_lifecycle_index": {"path": str(PROMPT_INDEX), "present": bool(prompt)},
            "codex_session_lifecycle": {"path": str(CODEX_INDEX), "present": bool(codex)},
            "session_lifecycle_blockers": {"path": str(BLOCKER_INDEX), "present": bool(blockers)},
            "session_lifecycle_pressure": {"path": str(PRESSURE_INDEX), "present": bool(pressure)},
            "worktree_preservation_receipts": {
                "path": str(PRESERVATION_RECEIPTS),
                "present": bool(preservation_receipts),
            },
        },
        "coverage": {
            "prompt_files": sum(int(s.get("files", 0)) for s in prompt.get("sources", []) if isinstance(s, dict)),
            "prompt_events": sum(int(s.get("prompt_events", 0)) for s in prompt.get("sources", []) if isinstance(s, dict)),
            "worktree_debt": (prompt.get("worktree_report") or {}).get("debt", 0),
            "local_pressure_bytes": pressure.get("local_total_bytes", 0),
            "codex_sessions": codex.get("session_count", 0),
            "blockers": len(blockers.get("blockers") or []),
            "preservation_receipts": len(preservation_receipts),
        },
        "lane_counts": dict(sorted(lane_counts.items())),
        "ranked_paths": ranked,
        "private_index": str(PRIVATE_INDEX),
    }


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    coverage = snapshot["coverage"]
    shown = snapshot["ranked_paths"][:limit]
    lane_bits = ", ".join(f"`{k}` {v}" for k, v in snapshot["lane_counts"].items()) or "none"
    lines = [
        "# Session Attack Paths",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- Do not assign Jules, Gemini, Agy, OpenCode, or Claude broad sprawl prompts.",
        "- Attack order comes from corpus evidence: prompt recurrence, local disk pressure, preservation risk, remote proof, blocker status, and agent fit.",
        "- Auth/secrets/login/key/password/provider-access work stays parked unless directly required by a scoped path.",
        "- Local cleanup comes after preservation proof: pushed branch, open/merged PR, default-branch equivalence, owner blocker, or documented non-source residue.",
        "",
        "## Coverage",
        "",
        f"- Redacted prompt corpus: `{coverage.get('prompt_files', 0)}` files, `{coverage.get('prompt_events', 0)}` prompt-like events.",
        f"- Codex classified sessions: `{coverage.get('codex_sessions', 0)}`.",
        f"- Worktree debt roots: `{coverage.get('worktree_debt', 0)}`.",
        f"- Worktree preservation receipts: `{coverage.get('preservation_receipts', 0)}`.",
        f"- Parked blockers: `{coverage.get('blockers', 0)}`.",
        f"- Local lifecycle footprint: `{fmt_bytes(int(coverage.get('local_pressure_bytes') or 0))}`.",
        f"- Candidate lanes: {lane_bits}.",
        "",
        "## Ordering Model",
        "",
        "- Highest priority: system clogs that prevent the lifecycle machine from draining: broken hooks, invalid states, missing preservation receipts, stale remote proof, or owner ledgers that make downstream cleanup unsafe.",
        "- Next: dirty or non-Git local roots with prompt evidence and missing remote preservation, because they consume disk and risk unique work.",
        "- Then: open remote-proof lanes where local copies can become lean after PR/default evidence is checked.",
        "- Then: repeated lifecycle/family loops that need owner packets before delegation.",
        "- Credential/auth lanes stay parked unless they are the direct clog blocking the selected path; then prepare only the bounded non-secret setup or human handoff.",
        "",
        "## Ranked Paths",
        "",
        "| Rank | Path | Kind | Lane | Score | Evidence | Agent Fit | Next Action |",
        "|---:|---|---|---|---:|---|---|---|",
    ]
    for idx, path in enumerate(shown, start=1):
        if path["kind"] == "worktree":
            evidence = (
                f"reason `{path.get('reason')}`; prompts {path.get('prompt_events', 0)}; "
                f"remote `{path.get('remote_branch')}`; open PRs {path.get('open_prs', 0)}"
            )
            if path.get("preservation_status"):
                evidence += f"; receipt `{path.get('preservation_status')}`"
        elif path["kind"] == "family":
            states = ", ".join(f"{k} {v}" for k, v in sorted((path.get("states") or {}).items())) or "none"
            evidence = f"sessions {path.get('sessions', 0)}; states {states}; prompts {path.get('prompt_events', 0)}"
        else:
            evidence = f"category `{path.get('category')}`; status `{path.get('status')}`"
        lines.append(
            f"| {idx} | `{path['id']}` | `{path['kind']}` | `{path['lane']}` | {path['score']} | "
            f"{evidence} | {path['agent_fit']} | {path['next_action']} |"
        )
    if not shown:
        lines.append("| 0 | none | n/a | n/a | 0 | No candidates derived. | n/a | n/a |")

    lines += [
        "",
        "## Delegation Gate",
        "",
        "- A path may be assigned only when it has an owner repo or owner ledger, a bounded next action, no raw-secret dependency, and a verification predicate or blocker receipt.",
        "- Claude is a context source while near limit; it should not be the default executor.",
        "- Jules/OpenCode/Agy get packets only after the ranked path is narrowed to a repo, branch, predicate, and expected receipt.",
        "- Gemini stays parked if auth is not already repaired.",
        "",
        "## Private Output",
        "",
        f"- Private attack-path index: `{relpath(PRIVATE_INDEX)}`.",
        "- The private index keeps structured path evidence from redacted indexes; it contains no raw prompt text.",
        "",
        "## Commands",
        "",
        "- Refresh prerequisites: `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/session-blockers-ledger.py --write`",
        "- Refresh attack paths: `python3 scripts/session-attack-paths.py --write`",
        "- Refresh prompt priority/task map: `python3 scripts/prompt-priority-map.py --write`",
        "- Refresh prompt batch review ledger: `python3 scripts/prompt-batch-review-ledger.py --write`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Rank session/prompt lifecycle attack paths.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--limit", type=int, default=25, help="ranked paths to show in tracked docs")
    args = parser.parse_args()

    snapshot = build_snapshot()
    markdown = render_markdown(snapshot, limit=max(1, args.limit))
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = f"session-attack-paths: {len(snapshot['ranked_paths'])} candidate paths"
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
