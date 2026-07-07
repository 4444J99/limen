#!/usr/bin/env python3
"""Build a private mail-story atom ledger plus a redacted public summary.

This is the C_MAIL story-mining surface: Apple Mail's Envelope Index supplies a
read-only metadata inventory, ignored `.limen-private/mail-story/` receives the
raw-ish atom stream, and `docs/mail-story-ledger.md` receives only redacted
cluster/count evidence.

The script never changes Mail, Gmail, labels, flags, archives, drafts, or
`tasks.yaml`. Full thread/body enrichment is deliberately modeled as a next
action, not performed here.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote


ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
DOC_PATH = ROOT / "docs" / "mail-story-ledger.md"
LOG_PATH = ROOT / "logs" / "mail-story-ledger.json"
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_MAIL_STORY", ROOT / ".limen-private" / "mail-story"))
PRIVATE_ATOMS = PRIVATE_ROOT / "inventory" / "mail-story-atoms.jsonl"
PRIVATE_SNAPSHOT = PRIVATE_ROOT / "inventory" / "mail-story-snapshot.json"
MAIL_INDEX = Path(
    os.environ.get(
        "LIMEN_MAIL_ENVELOPE_INDEX",
        Path.home() / "Library" / "Mail" / "V10" / "MailData" / "Envelope Index",
    )
)

SCHEMA = "limen.mail_story.v1"


CLUSTERS: dict[str, dict[str, str]] = {
    "billing-continuity": {
        "blocker_type": "billing",
        "title": "Billing continuity",
        "personal_consequence": "A renewal, card, invoice, or subscription problem can silently break an account or workflow.",
        "universal_pain_point": "People are expected to monitor scattered payment warnings across vendors and inboxes.",
        "software_thesis": "A custody layer should turn billing and renewal mail into one verified account-continuity queue.",
    },
    "debt-default-navigation": {
        "blocker_type": "debt",
        "title": "Debt and default navigation",
        "personal_consequence": "Loan, tax, or repayment notices create high-stakes ambiguity without a clear action path.",
        "universal_pain_point": "Debt systems expose consequences faster than they expose trustworthy next steps.",
        "software_thesis": "A debt-navigation copilot should map notices into verified options, deadlines, and escalation paths.",
    },
    "identity-compliance": {
        "blocker_type": "identity",
        "title": "Identity and compliance gates",
        "personal_consequence": "KYC, verification, and account-review requests block money movement or platform access.",
        "universal_pain_point": "Compliance workflows arrive as email fragments instead of an explainable case file.",
        "software_thesis": "A compliance dossier should collect requests, evidence, deadline state, and safe verification routes.",
    },
    "legal-government-accountability": {
        "blocker_type": "legal",
        "title": "Legal and government accountability",
        "personal_consequence": "Legal, benefits, government, and accountability notices carry consequences that are hard to sequence.",
        "universal_pain_point": "Institutional email makes citizens assemble their own procedural memory.",
        "software_thesis": "A civic/legal organizer should translate notices into timelines, obligations, and evidence packets.",
    },
    "career-routing": {
        "blocker_type": "career",
        "title": "Career routing",
        "personal_consequence": "Recruiting and opportunity messages need evaluation without swallowing the day.",
        "universal_pain_point": "Opportunity inboxes mix real leads, staffing noise, and identity fit with little ranking help.",
        "software_thesis": "A career router should score fit, extract next steps, and preserve opportunity history.",
    },
    "infra-custody": {
        "blocker_type": "infra",
        "title": "Infrastructure and domain custody",
        "personal_consequence": "Cloud, domain, developer, and platform notices can break production or ownership if missed.",
        "universal_pain_point": "Solo operators hold production custody through vendor emails instead of a coherent control plane.",
        "software_thesis": "An operator custody ledger should unify infra notices, owners, renewals, and blast-radius state.",
    },
    "security-risk": {
        "blocker_type": "security",
        "title": "Security and fraud risk",
        "personal_consequence": "Fraud, login, and account-security alerts demand fast action but are spoof-prone.",
        "universal_pain_point": "Security email mixes real incidents with phish-like UX and no trusted verification path.",
        "software_thesis": "A verify-first security queue should route alerts through safe channels and preserve audit receipts.",
    },
    "life-creative-logistics": {
        "blocker_type": "creative_life",
        "title": "Life and creative logistics",
        "personal_consequence": "Events, creative practice, and life logistics become another operational queue.",
        "universal_pain_point": "Calendar-adjacent life mail is not treated as part of a personal operating system.",
        "software_thesis": "A life-logistics layer should connect tickets, commitments, receipts, and story context.",
    },
    "relationship-personal-admin": {
        "blocker_type": "relationship",
        "title": "Relationship and personal administration",
        "personal_consequence": "Human-origin messages and self-sent reminders carry context that generic triage loses.",
        "universal_pain_point": "Personal administration is structurally mixed with automated vendor mail.",
        "software_thesis": "A relationship memory layer should separate human context from institutional noise.",
    },
    "platform-intelligence": {
        "blocker_type": "platform",
        "title": "Platform and developer ecosystem intelligence",
        "personal_consequence": "Platform updates, AI/vendor notices, and developer ecosystem signals shape product decisions.",
        "universal_pain_point": "Operators need a way to convert ecosystem noise into strategic intelligence.",
        "software_thesis": "A platform-intelligence digest should cluster vendor signals into product and risk theses.",
    },
    "uncategorized-pressure": {
        "blocker_type": "other",
        "title": "Uncategorized pressure",
        "personal_consequence": "Flagged mail without a clear class still carries enough pressure to be preserved.",
        "universal_pain_point": "People flag uncertainty because inbox tools do not support partial understanding.",
        "software_thesis": "A story-mining workflow should park ambiguous mail with evidence and a next read action.",
    },
}


PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "identity-compliance",
        (
            r"\bkyc\b",
            r"provide information",
            r"action required",
            r"verify (your )?(identity|account|information)",
            r"account review",
            r"\bstripe\b",
        ),
    ),
    (
        "security-risk",
        (
            r"\bfraud\b",
            r"security alert",
            r"suspicious",
            r"new sign-?in",
            r"password",
            r"login",
            r"\bsantander\b",
        ),
    ),
    (
        "debt-default-navigation",
        (
            r"student ?loan",
            r"\bnelnet\b",
            r"\bstudentaid\b",
            r"\bdebt\b",
            r"\bdefault\b",
            r"\btaxrise\b",
            r"auto pay",
        ),
    ),
    (
        "billing-continuity",
        (
            r"billing",
            r"payment",
            r"invoice",
            r"renew(al|ing)?",
            r"subscription",
            r"receipt",
            r"card",
            r"declin",
            r"charge",
            r"\bamazon\b",
            r"\banthropic\b",
            r"\bgithub\b",
            r"\bapple\b",
        ),
    ),
    (
        "infra-custody",
        (
            r"domain",
            r"\bcloud\b",
            r"\bdns\b",
            r"hostinger",
            r"cloudflare",
            r"google cloud",
            r"openai",
            r"api",
            r"developer",
        ),
    ),
    (
        "legal-government-accountability",
        (
            r"\blegal\b",
            r"\bcourt\b",
            r"\bdocusign\b",
            r"\blongo\b",
            r"social security",
            r"\bssa\b",
            r"government",
            r"accountability",
            r"\bbenefit",
        ),
    ),
    (
        "career-routing",
        (
            r"\brecruit",
            r"\binterview\b",
            r"\brole\b",
            r"\bjob\b",
            r"\bcareer\b",
            r"\bresume\b",
            r"\bopportunity\b",
            r"ux specialist",
            r"stage4solutions",
        ),
    ),
    (
        "life-creative-logistics",
        (
            r"\bticket",
            r"\bcomedy\b",
            r"\bevent\b",
            r"order complete",
            r"laughing buddha",
        ),
    ),
    (
        "platform-intelligence",
        (
            r"\bsocket\b",
            r"\bnewsletter\b",
            r"release",
            r"platform",
            r"\bai\b",
            r"developer ecosystem",
        ),
    ),
    (
        "relationship-personal-admin",
        (
            r"\bgmail\.com\b",
            r"\breturn\b",
            r"personal",
            r"reminder",
        ),
    ),
)

TYPE_WEIGHT = {
    "security": 5,
    "identity": 5,
    "debt": 5,
    "billing": 4,
    "legal": 4,
    "infra": 4,
    "career": 2,
    "platform": 2,
    "relationship": 2,
    "creative_life": 1,
    "other": 1,
}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def scoped_receipt_path(path: Path, scope: str) -> Path:
    return path.with_name(f"{path.stem}-{scope}{path.suffix}")


def iso_from_unix(value: int | None) -> str | None:
    if not value:
        return None
    try:
        return dt.datetime.fromtimestamp(int(value), tz=dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except (OSError, OverflowError, ValueError):
        return None


def sha(prefix: str, *parts: Any, length: int = 16) -> str:
    material = "|".join(str(part or "") for part in parts)
    return f"{prefix}_{hashlib.sha256(material.encode('utf-8')).hexdigest()[:length]}"


def connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"Apple Mail Envelope Index not found: {path}")
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def normalize_domain(address: str | None) -> str:
    if not address or "@" not in address:
        return "unknown"
    domain = address.rsplit("@", 1)[-1].strip().strip(">[]).,;:'\"").lower()
    return domain or "unknown"


def mailbox_scope(url: str | None) -> str:
    decoded = unquote(url or "").lower()
    if "[gmail]/all mail" in decoded:
        return "gmail/all-mail"
    if "[gmail]/sent mail" in decoded or decoded.endswith("/sent"):
        return "sent"
    if "icloud" in decoded:
        return "icloud"
    if decoded.endswith("/inbox") or "/inbox" in decoded:
        return "inbox"
    if "archive" in decoded:
        return "archive"
    if "trash" in decoded or "deleted" in decoded:
        return "trash"
    if "junk" in decoded or "spam" in decoded:
        return "junk"
    return "mailbox"


def searchable_text(row: sqlite3.Row) -> str:
    return " ".join(
        str(row[key] or "")
        for key in ("sender_address", "sender_name", "subject", "summary", "mailbox_url")
        if key in row.keys()
    ).lower()


def classify(row: sqlite3.Row) -> tuple[str, list[str], float]:
    text = searchable_text(row)
    hits: list[str] = []
    chosen = "uncategorized-pressure"
    for cluster_id, patterns in PATTERNS:
        cluster_hits = [pattern for pattern in patterns if re.search(pattern, text, re.IGNORECASE)]
        if cluster_hits:
            chosen = cluster_id
            hits = cluster_hits[:5]
            break
    confidence = 0.56 if chosen == "uncategorized-pressure" else min(0.96, 0.7 + 0.05 * len(hits))
    return chosen, hits, confidence


def next_action(cluster_id: str, confidence: float) -> str:
    blocker_type = CLUSTERS[cluster_id]["blocker_type"]
    if confidence < 0.65:
        return "read_thread"
    if blocker_type in {"billing", "debt", "identity", "legal", "security", "infra"}:
        return "human_review"
    if blocker_type in {"career", "platform", "creative_life", "relationship"}:
        return "product_research"
    return "parked"


def atom_from_row(row: sqlite3.Row, *, scope: str) -> dict[str, Any]:
    cluster_id, hits, confidence = classify(row)
    cluster = CLUSTERS[cluster_id]
    sender_domain = normalize_domain(row["sender_address"])
    subject = str(row["subject"] or "")
    status = "hot_flagged" if int(row["flagged"] or 0) == 1 else "historical_candidate"
    atom_id = sha(
        "ms",
        row["apple_rowid"],
        row["global_message_id"],
        row["message_id_header"],
        row["date_received"],
        row["sender_address"],
        subject,
    )
    return {
        "schema": SCHEMA,
        "stable_id": atom_id,
        "status": status,
        "scope": scope,
        "source_refs": {
            "apple_rowid": row["apple_rowid"],
            "global_message_id": row["global_message_id"],
            "conversation_id": row["conversation_id"],
            "mailbox_url": row["mailbox_url"],
            "mailbox_scope": mailbox_scope(row["mailbox_url"]),
            "message_id_header_hash": sha("mid", row["message_id_header"]) if row["message_id_header"] else None,
        },
        "received_at": iso_from_unix(row["date_received"]),
        "sender_domain": sender_domain,
        "sender_address": row["sender_address"],
        "sender_name": row["sender_name"],
        "subject": subject,
        "subject_hash": sha("subject", subject),
        "summary": row["summary"],
        "labels": {
            "flagged": bool(row["flagged"]),
            "flag_color": row["flag_color"],
            "read": bool(row["read"]),
            "deleted": bool(row["deleted"]),
        },
        "blocker_type": cluster["blocker_type"],
        "cluster_id": cluster_id,
        "cluster_title": cluster["title"],
        "classification_hits": hits,
        "immediate_fact": f"{status} metadata from {sender_domain} matched {cluster['title']}.",
        "personal_consequence": cluster["personal_consequence"],
        "universal_pain_point": cluster["universal_pain_point"],
        "software_thesis": cluster["software_thesis"],
        "confidence": round(confidence, 2),
        "evidence_scope": "metadata_summary" if row["summary"] else "metadata",
        "privacy_level": "private_only",
        "next_action": next_action(cluster_id, confidence),
    }


def fetch_message_rows(conn: sqlite3.Connection, *, scope: str, limit: int | None) -> list[sqlite3.Row]:
    where = "m.deleted = 0"
    if scope == "flagged":
        where += " AND m.flagged = 1"
    sql = f"""
        SELECT
            m.ROWID AS apple_rowid,
            m.global_message_id,
            mgd.message_id_header,
            m.conversation_id,
            m.date_received,
            m.flagged,
            m.flag_color,
            m.read,
            m.deleted,
            a.address AS sender_address,
            a.comment AS sender_name,
            s.subject AS subject,
            sm.summary AS summary,
            mb.url AS mailbox_url
        FROM messages m
        LEFT JOIN addresses a ON a.ROWID = m.sender
        LEFT JOIN subjects s ON s.ROWID = m.subject
        LEFT JOIN summaries sm ON sm.ROWID = m.summary
        LEFT JOIN mailboxes mb ON mb.ROWID = m.mailbox
        LEFT JOIN message_global_data mgd ON mgd.ROWID = m.global_message_id
        WHERE {where}
        ORDER BY m.date_received DESC, m.ROWID DESC
    """
    params: list[Any] = []
    if limit is not None:
        sql += " LIMIT ?"
        params.append(limit)
    return list(conn.execute(sql, params))


def _single_row(conn: sqlite3.Connection, sql: str) -> dict[str, Any]:
    row = conn.execute(sql).fetchone()
    return dict(row) if row else {}


def mail_stats(conn: sqlite3.Connection) -> dict[str, Any]:
    totals = _single_row(
        conn,
        """
        SELECT
            COUNT(*) AS total_messages,
            SUM(CASE WHEN deleted = 0 THEN 1 ELSE 0 END) AS not_deleted_messages,
            SUM(CASE WHEN flagged = 1 AND deleted = 0 THEN 1 ELSE 0 END) AS flagged_non_deleted,
            MIN(datetime(date_received, 'unixepoch')) AS first_received_at,
            MAX(datetime(date_received, 'unixepoch')) AS last_received_at
        FROM messages
        """,
    )
    by_year = [
        {"year": row["year"], "messages": row["messages"]}
        for row in conn.execute(
            """
            SELECT strftime('%Y', datetime(date_received, 'unixepoch')) AS year, COUNT(*) AS messages
            FROM messages
            WHERE deleted = 0
            GROUP BY year
            ORDER BY year DESC
            """
        )
    ]
    flagged_by_year = [
        {"year": row["year"], "messages": row["messages"]}
        for row in conn.execute(
            """
            SELECT strftime('%Y', datetime(date_received, 'unixepoch')) AS year, COUNT(*) AS messages
            FROM messages
            WHERE deleted = 0 AND flagged = 1
            GROUP BY year
            ORDER BY year DESC
            """
        )
    ]
    flagged_by_mailbox = [
        {
            "mailbox_scope": mailbox_scope(row["mailbox_url"]),
            "mailbox_url": row["mailbox_url"],
            "messages": row["messages"],
        }
        for row in conn.execute(
            """
            SELECT mb.url AS mailbox_url, COUNT(*) AS messages
            FROM messages m
            LEFT JOIN mailboxes mb ON mb.ROWID = m.mailbox
            WHERE m.deleted = 0 AND m.flagged = 1
            GROUP BY mb.url
            ORDER BY messages DESC, mb.url
            """
        )
    ]
    return {
        **totals,
        "by_year": by_year,
        "flagged_by_year": flagged_by_year,
        "flagged_by_mailbox": flagged_by_mailbox,
    }


def cluster_summary(atoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_cluster: dict[str, list[dict[str, Any]]] = {}
    for atom in atoms:
        by_cluster.setdefault(atom["cluster_id"], []).append(atom)
    rows: list[dict[str, Any]] = []
    for cluster_id, cluster_atoms in by_cluster.items():
        cluster = CLUSTERS[cluster_id]
        domains = Counter(atom["sender_domain"] for atom in cluster_atoms).most_common(8)
        actions = Counter(atom["next_action"] for atom in cluster_atoms)
        priority = len(cluster_atoms) * 10 + TYPE_WEIGHT.get(cluster["blocker_type"], 1) * 15
        rows.append(
            {
                "cluster_id": cluster_id,
                "title": cluster["title"],
                "blocker_type": cluster["blocker_type"],
                "atom_count": len(cluster_atoms),
                "priority": priority,
                "top_domains": [{"domain": domain, "messages": count} for domain, count in domains],
                "next_actions": dict(sorted(actions.items())),
                "example_atom_ids": [atom["stable_id"] for atom in cluster_atoms[:5]],
                "personal_consequence": cluster["personal_consequence"],
                "universal_pain_point": cluster["universal_pain_point"],
                "software_thesis": cluster["software_thesis"],
            }
        )
    return sorted(rows, key=lambda row: (-row["priority"], -row["atom_count"], row["cluster_id"]))


def build_snapshot(
    mail_index: Path, *, scope: str = "flagged", limit: int | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    with connect_readonly(mail_index) as conn:
        stats = mail_stats(conn)
        rows = fetch_message_rows(conn, scope=scope, limit=limit)
    atoms = [atom_from_row(row, scope=scope) for row in rows]
    top_domains = Counter(atom["sender_domain"] for atom in atoms).most_common(25)
    by_type = Counter(atom["blocker_type"] for atom in atoms)
    generated_at = utc_now()
    snapshot = {
        "schema": SCHEMA,
        "generated_at": generated_at,
        "mode": {
            "source": "apple_mail_envelope_index",
            "mail_index": str(mail_index),
            "scope": scope,
            "limit": limit,
            "read_only": True,
            "mailbox_mutations": False,
            "body_reads": False,
            "gmail_writes": False,
        },
        "privacy": {
            "private_root": str(PRIVATE_ROOT),
            "tracked_report": str(DOC_PATH),
            "raw_mail_in_git": False,
            "public_report_redacted": True,
        },
        "stats": stats,
        "atom_count": len(atoms),
        "top_domains": [{"domain": domain, "messages": count} for domain, count in top_domains],
        "by_blocker_type": dict(sorted(by_type.items())),
        "clusters": cluster_summary(atoms),
    }
    return snapshot, atoms


def md_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return out


def render_markdown(snapshot: dict[str, Any]) -> str:
    stats = snapshot["stats"]
    lines = [
        "# Mail Story Ledger",
        "",
        "Redacted control-plane view over the local mail story corpus. Raw/private atoms stay in the ignored",
        "`.limen-private/mail-story/` cartridge; this tracked report keeps only counts, domains, hashes,",
        "cluster ids, and synthesized pain-point theses.",
        "",
        "## Snapshot",
        "",
        f"- Generated: `{snapshot['generated_at']}`",
        "- Source: Apple Mail Envelope Index, opened read-only.",
        f"- Processed scope: `{snapshot['mode']['scope']}`",
        f"- Body/thread reads: `{str(snapshot['mode']['body_reads']).lower()}`",
        f"- Mailbox mutations: `{str(snapshot['mode']['mailbox_mutations']).lower()}`",
        "- Private atom store: `.limen-private/mail-story/inventory/mail-story-atoms.jsonl`",
        "",
        "## Corpus Counts",
        "",
        f"- Total indexed messages: `{stats.get('total_messages', 0)}`",
        f"- Non-deleted messages: `{stats.get('not_deleted_messages', 0)}`",
        f"- Flagged non-deleted messages: `{stats.get('flagged_non_deleted', 0)}`",
        f"- First received: `{stats.get('first_received_at') or 'unknown'}`",
        f"- Last received: `{stats.get('last_received_at') or 'unknown'}`",
        f"- Atoms emitted in this run: `{snapshot['atom_count']}`",
        "",
        "## Pain Point Clusters",
        "",
    ]
    cluster_rows = [
        [
            row["title"],
            row["blocker_type"],
            row["atom_count"],
            row["priority"],
            ", ".join(f"{k}:{v}" for k, v in row["next_actions"].items()) or "-",
            row["software_thesis"],
        ]
        for row in snapshot["clusters"]
    ]
    lines += md_table(
        ["cluster", "type", "atoms", "priority", "next actions", "software thesis"],
        cluster_rows or [["-", "-", 0, 0, "-", "-"]],
    )
    lines += [
        "",
        "## Top Sender Domains In Processed Scope",
        "",
    ]
    lines += md_table(
        ["domain", "messages"],
        [[row["domain"], row["messages"]] for row in snapshot["top_domains"][:20]] or [["-", 0]],
    )
    lines += [
        "",
        "## Flagged By Mailbox",
        "",
    ]
    lines += md_table(
        ["mailbox scope", "messages"],
        [[row["mailbox_scope"], row["messages"]] for row in stats.get("flagged_by_mailbox", [])] or [["-", 0]],
    )
    lines += [
        "",
        "## Flagged By Year",
        "",
    ]
    lines += md_table(
        ["year", "messages"],
        [[row["year"], row["messages"]] for row in stats.get("flagged_by_year", [])] or [["-", 0]],
    )
    lines += [
        "",
        "## Privacy Boundary",
        "",
        "- No message body text is read by this pass.",
        "- Full sender addresses, sender display names, subjects, summaries, and Apple row ids stay in ignored private JSON.",
        "- The tracked report intentionally exposes only domains, counts, cluster names, and synthesized theses.",
        "- Gmail thread enrichment is a later gated action for atoms whose `next_action` requires it.",
        "",
        "## Commands",
        "",
        "- Preview the hot flagged pass: `python3 scripts/mail-story-ledger.py`",
        "- Refresh the redacted report and ignored private atoms: `python3 scripts/mail-story-ledger.py --write`",
        "- Process all non-deleted indexed mail privately: `python3 scripts/mail-story-ledger.py --scope all --write`",
        "",
    ]
    return "\n".join(lines)


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
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    doc_path.write_text(markdown, encoding="utf-8")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    scoped_log = scoped_receipt_path(log_path, str(snapshot["mode"]["scope"]))
    if scoped_log != log_path:
        scoped_log.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    private_atoms.parent.mkdir(parents=True, exist_ok=True)
    private_atoms.write_text("".join(json.dumps(atom, sort_keys=True) + "\n" for atom in atoms), encoding="utf-8")
    scoped_atoms = scoped_receipt_path(private_atoms, str(snapshot["mode"]["scope"]))
    if scoped_atoms != private_atoms:
        scoped_atoms.write_text("".join(json.dumps(atom, sort_keys=True) + "\n" for atom in atoms), encoding="utf-8")
    private_snapshot.parent.mkdir(parents=True, exist_ok=True)
    private_snapshot.write_text(json.dumps({**snapshot, "atoms": atoms}, indent=2, sort_keys=True), encoding="utf-8")
    scoped_snapshot = scoped_receipt_path(private_snapshot, str(snapshot["mode"]["scope"]))
    if scoped_snapshot != private_snapshot:
        scoped_snapshot.write_text(
            json.dumps({**snapshot, "atoms": atoms}, indent=2, sort_keys=True),
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the redacted Limen mail story ledger.")
    parser.add_argument("--mail-index", type=Path, default=MAIL_INDEX, help="Apple Mail Envelope Index path")
    parser.add_argument("--scope", choices=("flagged", "all"), default="flagged", help="messages to emit as atoms")
    parser.add_argument("--limit", type=int, default=None, help="optional atom limit for previews/tests")
    parser.add_argument("--write", action="store_true", help="write docs, logs, and ignored private atom files")
    parser.add_argument("--doc", type=Path, default=DOC_PATH, help="tracked redacted Markdown output")
    parser.add_argument("--log", type=Path, default=LOG_PATH, help="ignored structured public-ish snapshot")
    parser.add_argument(
        "--private-atoms",
        type=Path,
        default=PRIVATE_ATOMS,
        help="ignored private atom JSONL output",
    )
    parser.add_argument(
        "--private-snapshot",
        type=Path,
        default=PRIVATE_SNAPSHOT,
        help="ignored private snapshot JSON output",
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit <= 0:
        parser.error("--limit must be positive")
    return args


def main() -> int:
    args = parse_args()
    snapshot, atoms = build_snapshot(args.mail_index, scope=args.scope, limit=args.limit)
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
        print(f"mail-story-ledger: {len(atoms)} atoms over scope={args.scope}; wrote {args.doc}")
    else:
        print(markdown)
        print(f"mail-story-ledger: {len(atoms)} atoms over scope={args.scope}; preview only")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
