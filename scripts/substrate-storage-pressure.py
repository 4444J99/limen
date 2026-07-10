#!/usr/bin/env python3
"""Write a current storage-pressure ledger for the local substrate.

This is a receipt, not a deletion tool. It names the remaining large buckets and
the gate that owns each one after safe generated/cache/model reclaim has run.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


HOME = Path(os.environ.get("HOME", "/Users/4jp")).expanduser()
ROOT = Path(os.environ.get("LIMEN_ROOT", HOME / "Workspace" / "limen")).expanduser()
DOC_PATH = ROOT / "docs" / "substrate-storage-pressure.md"
PRIVATE_PATH = ROOT / ".limen-private" / "session-corpus" / "lifecycle" / "substrate-storage-pressure.json"
TARGET_FREE_GIB = float(os.environ.get("LIMEN_ALWAYS_WORKING_TARGET_FREE_GIB", "200"))

RECLAIM_LOGS = {
    "generated-state": ROOT / "logs" / "reclaim-generated-state.jsonl",
    "tool-cache": ROOT / "logs" / "reclaim-tool-caches.jsonl",
    "ollama-models": ROOT / "logs" / "reclaim-ollama-models.jsonl",
}
OPENCODE_INTAKE_DOC = ROOT / "docs" / "opencode-db-corpus-intake.md"
OPENCODE_INTAKE_LOG = ROOT / "logs" / "opencode-db-corpus-intake.jsonl"

BUCKETS = (
    {
        "id": "opencode-db",
        "path": "~/.local/share/opencode/opencode.db",
        "class": "protected-agent-state",
        "owner": "aw-opencode-db-corpus-intake-0709",
        "gate": "extract/export into prompt-corpus intake before vendor retention decision; never delete outright",
    },
    {
        "id": "limen-private-session-corpus",
        "path": "~/Workspace/limen/.limen-private/session-corpus",
        "class": "protected-private-corpus",
        "owner": "docs/session-corpus-ledger.md",
        "gate": "two-copy/restore archive gate before move or purge",
    },
    {
        "id": "photos-library",
        "path": "~/Pictures/Photos Library.photoslibrary",
        "class": "personal-media",
        "owner": "media/photos custody",
        "gate": "personal-data human gate plus two-copy restore proof",
    },
    {
        "id": "messages",
        "path": "~/Library/Messages",
        "class": "personal-communications",
        "owner": "communications custody",
        "gate": "personal-data human gate plus two-copy restore proof",
    },
    {
        "id": "session-meta",
        "path": "~/Workspace/session-meta",
        "class": "repo-corpus-state",
        "owner": "organvm/session-meta",
        "gate": "repo/archive custody proof before local cache eviction",
    },
    {
        "id": "antigravity-scratch",
        "path": "~/.gemini/antigravity-cli/scratch",
        "class": "agy-scratch",
        "owner": "docs/antigravity-scratch-bridge.md",
        "gate": "antigravity scratch archive/redaction acceptance ledger before removal",
    },
    {
        "id": "limen-worktrees",
        "path": "~/Workspace/.limen-worktrees",
        "class": "worktree-cache",
        "owner": "docs/worktree-reclaim-acceptance.md",
        "gate": "clean+merged+idle or explicit acceptance; current worktree-debt gate reports zero reapable",
    },
    {
        "id": "gemini-agent-state",
        "path": "~/.gemini/antigravity-cli",
        "class": "protected-agent-state",
        "owner": "agy conductor",
        "gate": "preserve conversations/brain before eviction; scratch handled separately",
    },
)


def stable(path: Path) -> str:
    try:
        resolved = path.expanduser().resolve()
    except OSError:
        resolved = path.expanduser()
    try:
        return "~/" + str(resolved.relative_to(HOME))
    except ValueError:
        return str(resolved)


def expand(path: str) -> Path:
    return Path(path.replace("~", str(HOME), 1)).expanduser()


def du_kib(path: Path, timeout: int = 60) -> int | None:
    try:
        proc = subprocess.run(["du", "-sk", str(path)], text=True, capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    try:
        return int(proc.stdout.split()[0])
    except (IndexError, ValueError):
        return None


def fmt_bytes(value: int | None) -> str:
    if value is None:
        return "unknown"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{int(amount)} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def disk_free_gib(path: Path = HOME) -> float | None:
    try:
        stat = os.statvfs(path)
    except OSError:
        return None
    return round((stat.f_bavail * stat.f_frsize) / 1024**3, 1)


def reclaim_summary(path: Path) -> dict[str, Any]:
    total = 0
    events = 0
    latest: dict[str, Any] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if not isinstance(row, dict):
            continue
        latest = row
        if row.get("apply") is True:
            events += 1
            try:
                total += int(row.get("total_reclaimed_kib") or row.get("reclaimed_kib") or 0)
            except (TypeError, ValueError):
                pass
    return {
        "present": bool(latest),
        "apply_events": events,
        "latest_generated_at": latest.get("generated_at"),
        "cumulative_reclaimed_kib": total,
        "cumulative_reclaimed_size": fmt_bytes(total * 1024),
    }


def latest_opencode_intake() -> dict[str, Any]:
    latest: dict[str, Any] = {}
    try:
        lines = OPENCODE_INTAKE_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        lines = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            latest = row
    return {
        "present": bool(latest),
        "doc_present": OPENCODE_INTAKE_DOC.exists(),
        "status": latest.get("status"),
        "archive_status": latest.get("archive_status"),
        "generated_at": latest.get("generated_at"),
        "run_id": latest.get("run_id"),
        "private_manifest": latest.get("private_manifest"),
        "doc": stable(OPENCODE_INTAKE_DOC),
    }


def worktree_lifecycle_summary() -> dict[str, Any]:
    script = ROOT / "scripts" / "worktree-debt.py"
    if not script.exists():
        return {"present": False, "ok": False, "error": "scripts/worktree-debt.py missing"}
    try:
        proc = subprocess.run(
            ["python3", str(script), "--json"],
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"present": True, "ok": False, "error": str(exc)}
    if proc.returncode != 0:
        return {
            "present": True,
            "ok": False,
            "returncode": proc.returncode,
            "error": (proc.stderr or proc.stdout or "worktree-debt failed").strip()[:500],
        }
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        return {"present": True, "ok": False, "returncode": proc.returncode, "error": "invalid JSON"}
    by_reason = data.get("by_reason") if isinstance(data.get("by_reason"), dict) else {}
    by_reapable_reason = data.get("by_reapable_reason") if isinstance(data.get("by_reapable_reason"), dict) else {}
    total = int(data.get("total") or 0)
    debt = int(data.get("debt") or 0)
    reapable = int(data.get("reapable") or 0)
    return {
        "present": True,
        "ok": True,
        "total": total,
        "debt": debt,
        "reapable": reapable,
        "limit": data.get("limit"),
        "reapable_limit": data.get("reapable_limit"),
        "by_reason": by_reason,
        "by_reapable_reason": by_reapable_reason,
        "summary": f"{debt} debt roots / {total} scanned; {reapable} reapable roots",
    }


def build_snapshot() -> dict[str, Any]:
    free = disk_free_gib()
    shortfall = round(max(TARGET_FREE_GIB - (free or 0), 0), 1) if free is not None else None
    opencode_intake = latest_opencode_intake()
    rows = []
    for bucket in BUCKETS:
        path = expand(str(bucket["path"]))
        size_kib = du_kib(path)
        gate = str(bucket["gate"])
        evidence: dict[str, Any] = {}
        if bucket["id"] == "opencode-db" and opencode_intake.get("archive_status") == "verified":
            gate = "external archive and private intake verified; local retention decision remains; never delete outright"
            evidence["opencode_intake"] = opencode_intake
        rows.append(
            {
                **bucket,
                "gate": gate,
                "evidence": evidence,
                "display_path": stable(path),
                "exists": path.exists(),
                "size_kib": size_kib or 0,
                "size": fmt_bytes((size_kib or 0) * 1024),
            }
        )
    rows.sort(key=lambda row: int(row["size_kib"]), reverse=True)
    reclaim = {name: reclaim_summary(path) for name, path in RECLAIM_LOGS.items()}
    return {
        "schema": "limen.substrate_storage_pressure.v1",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "target_free_gib": TARGET_FREE_GIB,
        "internal_free_gib": free,
        "shortfall_gib": shortfall,
        "safe_reclaim": reclaim,
        "opencode_intake": opencode_intake,
        "worktree_lifecycle": worktree_lifecycle_summary(),
        "buckets": rows,
        "status": "needs-owner-gates" if shortfall else "clear",
    }


def render(snapshot: dict[str, Any]) -> str:
    lines = [
        "# Substrate Storage Pressure",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        f"Status: `{snapshot['status']}`",
        f"Internal free: `{snapshot['internal_free_gib']} GiB`",
        f"Target free: `{snapshot['target_free_gib']} GiB`",
        f"Shortfall: `{snapshot['shortfall_gib']} GiB`",
        "",
        "## Safe Reclaim Already Run",
        "",
    ]
    for name, row in snapshot["safe_reclaim"].items():
        lines.append(
            f"- `{name}`: `{row['cumulative_reclaimed_size']}` over `{row['apply_events']}` apply event(s); "
            f"latest `{row['latest_generated_at']}`."
        )
    lifecycle = snapshot.get("worktree_lifecycle") or {}
    lines += [
        "",
        "## Scratch / Worktree Lifecycle",
        "",
    ]
    if lifecycle.get("ok"):
        lines.append(f"- Summary: `{lifecycle.get('summary')}`.")
        lines.append(f"- Debt cap: `{lifecycle.get('limit')}`; reapable cap: `{lifecycle.get('reapable_limit')}`.")
        by_reason = lifecycle.get("by_reason") if isinstance(lifecycle.get("by_reason"), dict) else {}
        if by_reason:
            lines += ["", "| Reason | Roots |", "|---|---:|"]
            for reason, count in sorted(by_reason.items(), key=lambda item: (-int(item[1]), str(item[0]))):
                lines.append(f"| `{reason}` | `{count}` |")
    else:
        lines.append(f"- Worktree lifecycle unavailable: `{lifecycle.get('error', 'unknown')}`.")
    lines += [
        "",
        "## Remaining Large Buckets",
        "",
        "| Bucket | Size | Class | Owner | Gate |",
        "|---|---:|---|---|---|",
    ]
    for row in snapshot["buckets"]:
        lines.append(
            f"| `{row['display_path']}` | `{row['size']}` | `{row['class']}` | `{row['owner']}` | {row['gate']} |"
        )
    opencode_intake = snapshot.get("opencode_intake") if isinstance(snapshot.get("opencode_intake"), dict) else {}
    if opencode_intake.get("present"):
        lines += [
            "",
            "## OpenCode DB Intake",
            "",
            f"- Status: `{opencode_intake.get('status')}`.",
            f"- Archive status: `{opencode_intake.get('archive_status')}`.",
            f"- Receipt: `{opencode_intake.get('doc')}`.",
            f"- Private manifest: `{(opencode_intake.get('private_manifest') or {}).get('path', 'none')}`.",
        ]
    lines += [
        "",
        "## Contract",
        "",
        "- Do not delete personal communications, photos, private corpus, or agent session databases as cache.",
        "- Worktree and Agy scratch removal stay behind their acceptance ledgers.",
        "- More disk reduction now requires owner gates, archive/restore proof, or explicit product decision to lower the hot-cache target.",
    ]
    return "\n".join(lines) + "\n"


def write(snapshot: dict[str, Any]) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(render(snapshot), encoding="utf-8")
    PRIVATE_PATH.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Write substrate storage pressure receipts.")
    parser.add_argument("--write", action="store_true", help="write docs and private JSON")
    parser.add_argument("--json", action="store_true", help="print JSON")
    args = parser.parse_args()
    snapshot = build_snapshot()
    if args.write:
        write(snapshot)
    if args.json or not args.write:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(
            f"substrate-storage-pressure: {snapshot['status']} free={snapshot['internal_free_gib']}GiB "
            f"shortfall={snapshot['shortfall_gib']}GiB"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
