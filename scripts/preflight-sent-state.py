#!/usr/bin/env python3
"""preflight-sent-state.py — the ground-truth predicate behind the `mail.send` outbound gate.

WHAT IT ANSWERS: "has anything already gone OUT to this recipient?" — read from the server
([Gmail]/Sent Mail over IMAP), never from a local artifact, a ledger, or an inbox screenshot.

WHY IT EXISTS: on 2026-07-31 a redundant reply reached a live recruiter because the inbox was
read and Sent was not — the operator had answered the same thread three hours after it arrived.
That is instance 33 of a class the estate has recorded since 2026-03-24, and the first one to
complete an outward action. See institutio/governance/outbound-effectors.yaml for the full
measurement (10 prose rules for this class, 10 recurrences, 100% failure rate).

EXIT CONTRACT (this is what makes the gate a gate, not a checklist):
  0  nothing has gone out to this recipient recently  — OR — a prior send exists AND has been
     explicitly acknowledged via --acknowledge for that exact message id.
  1  a prior send EXISTS and is unacknowledged. The gate denies. The prior message is printed
     in full so the next decision is made with it in hand, not around it.
  77 the check could not run (no credential pair, no network). SKIP — the gate still denies,
     because "I could not look" is not "there is nothing there".

The two-step is deliberate. A one-step "did you look?" is self-certifiable and demonstrably
fails: ~/.claude/settings.json already carries exactly that question as advisory text on
`gh pr comment` and it is answered "yes" and walked past. Acknowledgement requires naming a
specific Message-ID that only the server can have told you about.

CREDENTIALS: pair-atomic by construction — a COMPLETE (user, password) pair from one lane, never
mixed. The 2026-07-31 audit found send_drafts.py:_smtp_creds and correspondence-walk.py both
resolving `IMAP_USER or GMAIL_USER` / `IMAP_PASS or GMAIL_APP_PASSWORD` field-by-field, which on
this host yields a live user paired with a dead credential, so sends fail AND already-answered
detection fails, from one bug. Values are never printed. ([[logic-over-inherited-config]])

PII: addresses are hashed into every path this writes. Acknowledgement markers live under
logs/ (gitignored). Nothing here writes a recipient into a committed file.
"""

from __future__ import annotations

import argparse
import email
import hashlib
import imaplib
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from email.header import decode_header, make_header
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ACK_DIR = ROOT / "logs" / "preflight-acks"
DEFAULT_WINDOW_DAYS = 30
SENT_MAILBOX = os.environ.get("LIMEN_MAIL_SENT_MAILBOX", "[Gmail]/Sent Mail")

# Credential lanes, in preference order. Each entry is a COMPLETE pair — the whole point.
_CRED_LANES: tuple[tuple[str, str], ...] = (
    ("IMAP_USER", "IMAP_PASS"),
    ("GMAIL_USER", "GMAIL_APP_PASSWORD"),
)


def _target_digest(value: str) -> str:
    """Stable, address-free handle for a recipient (also the receipt/ack filename)."""
    return hashlib.sha256(value.strip().lower().encode("utf-8")).hexdigest()[:16]


def _load_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _credentials() -> tuple[str, str] | None:
    """A COMPLETE pair from ONE lane. Never mix lanes — that is the bug this file refuses to
    repeat. Environment wins over the hydrated env file; values are never logged."""
    env = dict(_load_env_file(Path.home() / ".limen.env"))
    env.update({k: v for k, v in os.environ.items() if v})
    for user_key, password_key in _CRED_LANES:
        user, password = env.get(user_key), env.get(password_key)  # allow-secret: names only, no value
        if user and password:
            return user, password
    return None


def _header(message: email.message.Message, name: str) -> str:
    raw = message.get(name)
    if not raw:
        return ""
    try:
        return str(make_header(decode_header(raw)))
    except (UnicodeDecodeError, LookupError, ValueError):
        return str(raw)


def _normalize_subject(subject: str) -> str:
    stem = re.sub(r"^\s*(?:re|fwd?|fw)\s*:\s*", "", subject or "", flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", stem).strip().lower()


def _search_sent(recipient: str, window_days: int) -> tuple[str, list[dict]]:
    """Return (state, rows). state ∈ {ok, unavailable}. Read-only; never mutates the mailbox."""
    creds = _credentials()
    if creds is None:
        return "unavailable", []
    user, password = creds  # allow-secret: unpacks a runtime pair, no literal value
    since = (datetime.now(UTC) - timedelta(days=window_days)).strftime("%d-%b-%Y")
    connection: imaplib.IMAP4_SSL | None = None
    try:
        connection = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        connection.login(user, password)
        # Python 3.14's imaplib no longer auto-quotes names containing spaces or brackets, so an
        # unquoted SELECT "[Gmail]/Sent Mail" returns BAD. That exact regression silently no-opped
        # UMA's own duplicate-send guard (draft_writer.thread_already_handled) from 2026-07-17
        # onward — flagged then, never fixed. Quote it.
        status, _ = connection.select(f'"{SENT_MAILBOX}"', readonly=True)
        if status != "OK":
            return "unavailable", []
        status, data = connection.search(None, "SINCE", since, "TO", f'"{recipient}"')
        if status != "OK":
            return "unavailable", []
        rows: list[dict] = []
        for uid in (data[0] or b"").split():
            status, payload = connection.fetch(
                uid,
                "(BODY.PEEK[HEADER.FIELDS (DATE SUBJECT TO MESSAGE-ID)])",
            )
            if status != "OK" or not payload or not payload[0]:
                continue
            message = email.message_from_string(payload[0][1].decode("utf-8", "replace"))
            rows.append(
                {
                    "date": _header(message, "Date"),
                    "subject": _header(message, "Subject"),
                    "subject_stem": _normalize_subject(_header(message, "Subject")),
                    "message_id": _header(message, "Message-ID").strip(),
                }
            )
        return "ok", rows
    except (imaplib.IMAP4.error, OSError, UnicodeError):
        return "unavailable", []
    finally:
        if connection is not None:
            try:
                connection.logout()
            except (imaplib.IMAP4.error, OSError):
                pass


def _ack_path(recipient: str) -> Path:
    return ACK_DIR / f"mail.send.{_target_digest(recipient)}.json"


def _load_acks(recipient: str) -> set[str]:
    try:
        payload = json.loads(_ack_path(recipient).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    known = payload.get("acknowledged_message_ids")
    return set(known) if isinstance(known, list) else set()


def _write_acks(recipient: str, message_ids: set[str]) -> None:
    path = _ack_path(recipient)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "limen.preflight_ack.v1",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "target_digest": _target_digest(recipient),  # never the address itself
        "acknowledged_message_ids": sorted(message_ids),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--recipient", required=True, help="the address a message is about to go to")
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument(
        "--acknowledge",
        action="store_true",
        help="record that every prior send printed below has been READ; only then can the gate pass",
    )
    args = parser.parse_args()

    recipient = args.recipient.strip()
    state, rows = _search_sent(recipient, max(1, args.window_days))

    if state == "unavailable":
        print("preflight-sent-state: SKIP — could not read the Sent mailbox (no complete credential")
        print("  pair, or no network). 'I could not look' is not 'there is nothing there'; the gate")
        print("  stays closed. Check that ONE lane is complete: IMAP_USER+IMAP_PASS, or")
        print("  GMAIL_USER+GMAIL_APP_PASSWORD. Never a mix — a live user with a dead password from")
        print("  the other lane is exactly the 2026-07-31 defect.")
        return 77

    if not rows:
        print(f"preflight-sent-state: PASS — no message sent to this recipient in {args.window_days}d.")
        print(f"  mailbox={SENT_MAILBOX} target_digest={_target_digest(recipient)}")
        return 0

    acknowledged = _load_acks(recipient)
    outstanding = [row for row in rows if row["message_id"] and row["message_id"] not in acknowledged]

    if args.acknowledge:
        _write_acks(recipient, acknowledged | {row["message_id"] for row in rows if row["message_id"]})
        print(f"preflight-sent-state: acknowledged {len(rows)} prior send(s) to this recipient.")
        print("  Re-run WITHOUT --acknowledge to mint the PASS receipt the gate requires.")
        return 0

    if not outstanding:
        print(f"preflight-sent-state: PASS — {len(rows)} prior send(s), all previously acknowledged.")
        return 0

    print(f"preflight-sent-state: FAIL — {len(outstanding)} prior send(s) to this recipient, UNREAD.")
    print("  You are about to talk over a message that already went out. Read it first:")
    for row in outstanding:
        print(f"    · {row['date']}")
        print(f"      subject: {row['subject']}")
        print(f"      message-id: {row['message_id']}")
    print("")
    print("  If a further message is still the right move, acknowledge these explicitly:")
    print(f"    python3 scripts/preflight-sent-state.py --recipient {recipient} --acknowledge")
    return 1


if __name__ == "__main__":
    sys.exit(main())
