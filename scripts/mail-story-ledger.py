#!/usr/bin/env python3
"""Render Limen mail-story surfaces from UMA mail status receipts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


# UMA_MAIL_TRIAGE_WRAPPER
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
UMA_ROOT = Path(os.environ.get("UMA_ROOT", Path.home() / "Workspace" / "universal-mail--automation"))
DOC_PATH = ROOT / "docs" / "mail-story-ledger.md"
LOG_PATH = ROOT / "logs" / "mail-story-ledger.json"
STATUS_PATH = Path(os.environ.get("LIMEN_MAIL_STATUS_OUT", ROOT / "logs" / "uma-mail-status.json"))
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_MAIL_STORY", ROOT / ".limen-private" / "mail-story"))
PRIVATE_ATOMS = PRIVATE_ROOT / "inventory" / "mail-story-atoms.jsonl"
PRIVATE_SNAPSHOT = PRIVATE_ROOT / "inventory" / "mail-story-snapshot.json"
OPS_REPORT = Path(os.environ.get("UMA_OPS_REPORT_PATH", Path.home() / "System" / "Reports" / "mail-triage" / "latest.json"))
HISTORY_REPORT = Path(os.environ.get("UMA_HISTORICAL_MAIL_PATH", Path.home() / "System" / "Reports" / "mail-history" / "latest.json"))

SCHEMA = "limen.mail_story.wrapper.v1"
ATOM_SCHEMA = "limen.mail_story_atom.wrapper.v1"
UMA_STATUS_SCHEMA = "uma.mail.status.v1"
OWNER = "organvm/universal-mail--automation"


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return data


def uma_command(override: str | None = None) -> list[str]:
    if override:
        return [override]
    if os.environ.get("UMA_BIN"):
        return [os.environ["UMA_BIN"]]
    cli = UMA_ROOT / "cli.py"
    if cli.exists():
        return [os.environ.get("LIMEN_PY", "python3"), str(cli)]
    return ["umail"]


def blocked_status(detail: str) -> dict[str, Any]:
    return {
        "schema": UMA_STATUS_SCHEMA,
        "status": "blocked",
        "generated_at": now_iso(),
        "mode": {"read_only": True, "mailbox_mutations": False, "sends": False},
        "privacy": {"redacted": True, "public_safe": True},
        "blockers": [
            {
                "surface": "uma_mail_status",
                "status": "blocked",
                "detail_hash": hashlib.sha256(detail.encode("utf-8")).hexdigest()[:16],
            }
        ],
        "current_ops": {"available": False, "kpis": {}},
        "historical_crosswalk": {"available": False, "kpis": {}},
        "answers": {},
        "next_queue": [],
    }


def fetch_status(
    *,
    status_path: Path = STATUS_PATH,
    uma_bin: str | None = None,
    ops_report: Path = OPS_REPORT,
    history_report: Path = HISTORY_REPORT,
    max_age_hours: int = 24,
) -> tuple[dict[str, Any], Path | None]:
    if status_path.exists():
        return load_json(status_path), status_path

    command = [
        *uma_command(uma_bin),
        "mail-status",
        "--ops-report",
        str(ops_report),
        "--history",
        str(history_report),
        "--max-age-hours",
        str(max_age_hours),
        "--output",
        str(status_path),
    ]
    proc = subprocess.run(command, text=True, capture_output=True, check=False)
    if proc.returncode in (0, 2) and status_path.exists():
        return load_json(status_path), status_path
    detail = proc.stderr.strip() or proc.stdout.strip() or "UMA status command failed"
    return blocked_status(detail), None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_scalar(value: Any) -> Any:
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    if isinstance(value, str):
        if "@" in value or len(value) > 96:
            return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return value
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def _safe_map(source: dict[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    return {key: _safe_scalar(source[key]) for key in keys if key in source}


def _fmt(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _terminal_counts(historical: dict[str, Any], kpis: dict[str, Any]) -> dict[str, int]:
    candidates = historical.get("terminal_status_counts") or kpis.get("terminal_status_counts") or {}
    if not isinstance(candidates, dict):
        return {}
    return {str(key): int(value) for key, value in candidates.items() if isinstance(value, int)}


def _queue_atoms(status: dict[str, Any], *, limit: int) -> list[dict[str, Any]]:
    atoms: list[dict[str, Any]] = []
    for index, item in enumerate(_list(status.get("next_queue"))[:limit]):
        if not isinstance(item, dict):
            continue
        visible = _safe_map(
            item,
            (
                "id",
                "receipt_id",
                "terminal_status",
                "processing_state",
                "surface",
                "status",
                "owner",
                "reason_code",
                "blocker_type",
            ),
        )
        item_hash = hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
        atoms.append(
            {
                "schema": ATOM_SCHEMA,
                "source_schema": status.get("schema"),
                "source_item_hash": item_hash,
                "ordinal": index,
                "classification_owner": OWNER,
                "visible": visible,
            }
        )
    return atoms


def build_snapshot(
    status: dict[str, Any],
    *,
    scope: str = "flagged",
    limit: int = 50,
    source_path: Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    current = _dict(status.get("current_ops"))
    historical = _dict(status.get("historical_crosswalk"))
    current_kpis = _dict(current.get("kpis"))
    historical_kpis = _dict(historical.get("kpis"))
    mode = _dict(status.get("mode"))
    privacy = _dict(status.get("privacy"))
    blockers = _list(status.get("blockers"))
    terminal_counts = _terminal_counts(historical, historical_kpis)
    atoms = _queue_atoms(status, limit=limit)

    snapshot = {
        "schema": SCHEMA,
        "generated_at": now_iso(),
        "classification_owner": OWNER,
        "source_receipt": {
            "schema": status.get("schema"),
            "status": status.get("status"),
            "path": str(source_path) if source_path else None,
            "redacted": bool(privacy.get("redacted", True)),
            "public_safe": bool(privacy.get("public_safe", True)),
        },
        "mode": {
            "scope": scope,
            "limit": limit,
            "read_only": bool(mode.get("read_only", True)),
            "mailbox_mutations": bool(mode.get("mailbox_mutations", False)),
            "sends": bool(mode.get("sends", False)),
        },
        "stats": {
            "current_status": status.get("status"),
            "current_ops_available": bool(current.get("available")),
            "current_inbox_total": current_kpis.get("inbox_total", current_kpis.get("inbox_messages")),
            "current_changed_count": current_kpis.get("changed_count", 0),
            "historical_crosswalk_available": bool(historical.get("available")),
            "historical_messages": historical_kpis.get("source_messages"),
            "historical_reconciled": historical_kpis.get("reconciled"),
            "terminal_status_counts": terminal_counts,
            "historical_open": terminal_counts.get("open", historical_kpis.get("open")),
            "historical_blocked": terminal_counts.get("blocked", historical_kpis.get("blocked")),
            "historical_needs_human": terminal_counts.get("needs_human", historical_kpis.get("needs_human")),
            "next_queue_count": len(_list(status.get("next_queue"))),
            "atom_count": len(atoms),
            "blocker_count": len(blockers),
        },
        "answers": _safe_map(
            _dict(status.get("answers")),
            (
                "what_ran",
                "what_mailbox_surface_was_covered",
                "what_changed",
                "what_remains_open",
                "what_is_blocked",
                "historical_backlog_accounted_for",
            ),
        ),
        "privacy": {
            "raw_mail_in_git": False,
            "raw_prompt_in_git": False,
            "source_status_expected_redacted": True,
        },
    }
    return snapshot, atoms


def render_markdown(snapshot: dict[str, Any]) -> str:
    stats = _dict(snapshot.get("stats"))
    mode = _dict(snapshot.get("mode"))
    source = _dict(snapshot.get("source_receipt"))
    terminal_counts = _dict(stats.get("terminal_status_counts"))
    lines = [
        "# Mail Story Ledger",
        "",
        "Limen is a UMA wrapper for mail-story evidence. Classification, crosswalk, and resolver truth live in `organvm/universal-mail--automation`.",
        "",
        "## Snapshot",
        "",
        f"- Generated: `{snapshot.get('generated_at')}`",
        f"- Wrapper schema: `{snapshot.get('schema')}`",
        f"- Source receipt schema: `{source.get('schema')}`",
        f"- Source status: `{source.get('status')}`",
        f"- Classification owner: `{snapshot.get('classification_owner')}`",
        f"- Scope: `{mode.get('scope')}`",
        f"- Read only: `{_fmt(mode.get('read_only'))}`",
        f"- Mailbox mutation allowed: `{_fmt(mode.get('mailbox_mutations'))}`",
        f"- Sends allowed: `{_fmt(mode.get('sends'))}`",
        "",
        "## Counts",
        "",
        f"- Current ops available: `{_fmt(stats.get('current_ops_available'))}`",
        f"- Current inbox total: `{_fmt(stats.get('current_inbox_total'))}`",
        f"- Current changed count: `{_fmt(stats.get('current_changed_count'))}`",
        f"- Historical crosswalk available: `{_fmt(stats.get('historical_crosswalk_available'))}`",
        f"- Historical source messages: `{_fmt(stats.get('historical_messages'))}`",
        f"- Historical reconciled: `{_fmt(stats.get('historical_reconciled'))}`",
        f"- Next queue count: `{_fmt(stats.get('next_queue_count'))}`",
        f"- Blocker count: `{_fmt(stats.get('blocker_count'))}`",
        "",
        "## Terminal Status Counts",
        "",
    ]
    if terminal_counts:
        for key in sorted(terminal_counts):
            lines.append(f"- `{key}`: `{terminal_counts[key]}`")
    else:
        lines.append("- No terminal status counts were present in the UMA receipt.")
    lines.extend(
        [
            "",
            "## Privacy",
            "",
            "- Raw mail text is not written to tracked Limen outputs.",
            "- Limen does not send, delete, draft, label, or otherwise mutate mailbox state from this wrapper.",
            "",
        ]
    )
    return "\n".join(lines)


def _scoped_path(path: Path, scope: str) -> Path:
    return path.with_name(f"{path.stem}-{scope}{path.suffix}")


def write_outputs(
    snapshot: dict[str, Any],
    atoms: list[dict[str, Any]],
    markdown: str,
    *,
    doc_path: Path = DOC_PATH,
    log_path: Path = LOG_PATH,
    private_atoms: Path = PRIVATE_ATOMS,
    private_snapshot: Path = PRIVATE_SNAPSHOT,
) -> None:
    scope = str(_dict(snapshot.get("mode")).get("scope") or "flagged")
    for path in (doc_path, log_path, private_atoms, private_snapshot):
        path.parent.mkdir(parents=True, exist_ok=True)

    doc_path.write_text(markdown, encoding="utf-8")
    log_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    private_snapshot.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    private_atoms.write_text(
        "".join(json.dumps(atom, sort_keys=True) + "\n" for atom in atoms),
        encoding="utf-8",
    )

    _scoped_path(log_path, scope).write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _scoped_path(private_snapshot, scope).write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _scoped_path(private_atoms, scope).write_text(
        "".join(json.dumps(atom, sort_keys=True) + "\n" for atom in atoms),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("flagged", "all"), default="flagged")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--write", action="store_true", help="Write Limen doc/log wrapper outputs")
    parser.add_argument("--status", type=Path, default=STATUS_PATH, help="Existing UMA status receipt path")
    parser.add_argument("--uma-bin", help="UMA executable override")
    parser.add_argument("--ops-report", type=Path, default=OPS_REPORT)
    parser.add_argument("--history", type=Path, default=HISTORY_REPORT)
    parser.add_argument("--max-age-hours", type=int, default=24)
    parser.add_argument("--doc", type=Path, default=DOC_PATH)
    parser.add_argument("--log", type=Path, default=LOG_PATH)
    parser.add_argument("--private-atoms", type=Path, default=PRIVATE_ATOMS)
    parser.add_argument("--private-snapshot", type=Path, default=PRIVATE_SNAPSHOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    status, source_path = fetch_status(
        status_path=args.status,
        uma_bin=args.uma_bin,
        ops_report=args.ops_report,
        history_report=args.history,
        max_age_hours=args.max_age_hours,
    )
    snapshot, atoms = build_snapshot(status, scope=args.scope, limit=args.limit, source_path=source_path)
    markdown = render_markdown(snapshot)
    if args.write:
        write_outputs(
            snapshot,
            atoms,
            markdown,
            doc_path=args.doc,
            log_path=args.log,
            private_atoms=args.private_atoms,
            private_snapshot=args.private_snapshot,
        )
        print(json.dumps({"status": "ok", "message": "UMA wrapper wrote Limen mail-story surfaces"}, sort_keys=True))
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
