#!/usr/bin/env python3
"""capture-threads.py — durable primary-source capture of local message threads.

THE PROBLEM IT CLOSES: the relationship records under ~/Workspace/_people-private are
already sealed + committed encrypted by ARCA (scripts/arca.sh), but the PRIMARY SOURCE —
the actual message threads — was only ever re-queried live per session and dumped to
throwaway scratch files. iMessage was ephemeral; WhatsApp was never captured at all. One
dead Mac (or a rotated chat.db) and the source is gone, leaving only interpretations.

This organ exports the real threads to decoded, structured transcripts INSIDE the private
store, where ARCA then encrypts + commits them for free on the next beat. The engine is
PUBLIC and contains no PII: every handle/JID comes from a private roster.

SOURCES (both local, read-only):
  - iMessage/SMS : ~/Library/Messages/chat.db                     (message.date = ns since 2001)
  - WhatsApp     : ~/Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite
                   (ZWAMESSAGE.ZMESSAGEDATE = Core Data float-seconds since 2001)

ROSTER (private, PII lives here — never in this file):
  ~/Workspace/_people-private/people/roster.json
  {"people": {"<slug>": {"imessage": ["+1..."], "whatsapp_jid": ["...@s.whatsapp.net"]}}}

OUTPUT (per person, fixed names → idempotent overwrite; re-run = fixed point):
  <out-root>/<slug>/tape/imessage.jsonl + imessage.md
  <out-root>/<slug>/tape/whatsapp.jsonl + whatsapp.md
  <out-root>/<slug>/tape/media/<file>            (voice-memo / audio blobs, preserved)

USAGE:
  python3 scripts/capture-threads.py                 # all people in the roster
  python3 scripts/capture-threads.py --person chris-notarnicola
  python3 scripts/capture-threads.py --list-whatsapp # dump WA sessions (Z_PK|JID|name) to find a JID

Exit 0 on success. Prints a per-person summary for verification.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone

try:
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
except Exception:  # pragma: no cover
    ET = None

APPLE_EPOCH = 978307200  # seconds from 1970-01-01 to 2001-01-01 (UTC)

HOME = os.path.expanduser("~")
DEF_CHATDB = os.path.join(HOME, "Library/Messages/chat.db")
DEF_WADB = os.path.join(
    HOME, "Library/Group Containers/group.net.whatsapp.WhatsApp.shared/ChatStorage.sqlite"
)
DEF_WA_CONTAINER = os.path.dirname(DEF_WADB)
DEF_ROSTER = os.path.join(HOME, "Workspace/_people-private/people/roster.json")
DEF_OUT_ROOT = os.path.join(HOME, "Workspace/_people-private/people")

# iMessage reaction (tapback) association types.
REACTIONS = {2000: "loved", 2001: "liked", 2002: "disliked",
             2003: "laughed", 2004: "emphasized", 2005: "questioned", 2006: "reacted"}
# WhatsApp ZMESSAGETYPE (iOS) — best-effort labels; unknown → "type-N".
WA_TYPE = {0: "text", 1: "image", 2: "video", 3: "audio", 4: "contact",
           5: "location", 7: "link", 8: "document", 11: "call", 15: "sticker"}


def open_ro(path: str) -> sqlite3.Connection:
    """Open read-only, tolerating a live WAL (mode=ro) or a locked writer (immutable=1)."""
    last = None
    for uri in (f"file:{path}?mode=ro", f"file:{path}?immutable=1"):
        try:
            c = sqlite3.connect(uri, uri=True)
            c.execute("select 1")
            return c
        except sqlite3.OperationalError as e:
            last = e
    raise last


def _dt_utc(seconds: float | None) -> datetime | None:
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds + APPLE_EPOCH, tz=timezone.utc)


def stamp(dt: datetime | None) -> dict:
    if dt is None:
        return {"utc": None, "et": None}
    et = dt.astimezone(ET) if ET else dt
    return {"utc": dt.strftime("%Y-%m-%d %H:%M:%S"),
            "et": et.strftime("%Y-%m-%d %H:%M:%S %Z")}


def decode_attributed_body(blob: bytes | None) -> str | None:
    """Pull the plain string out of a NSAttributedString typedstream (text-null rows)."""
    if not blob:
        return None
    i = blob.find(b"NSString")
    if i < 0:
        return None
    i += len(b"NSString") + 5
    if i >= len(blob):
        return None
    ln_byte = blob[i]
    if ln_byte == 0x81:
        ln = int.from_bytes(blob[i + 1:i + 3], "little"); start = i + 3
    elif ln_byte == 0x82:
        ln = int.from_bytes(blob[i + 1:i + 5], "little"); start = i + 5
    else:
        ln = ln_byte; start = i + 1
    try:
        return blob[start:start + ln].decode("utf-8", "replace")
    except Exception:
        return None


def capture_imessage(chatdb: str, handles: list[str]) -> list[dict]:
    c = open_ro(chatdb)
    cols = {r[1] for r in c.execute("PRAGMA table_info(message)")}
    amt = "m.associated_message_type" if "associated_message_type" in cols else "NULL"
    has_attach = "m.cache_has_attachments" if "cache_has_attachments" in cols else "0"
    qm = ",".join("?" * len(handles))
    q = f"""
        SELECT m.ROWID, m.date, m.is_from_me, m.text, m.attributedBody,
               {amt} AS amt, {has_attach} AS att, h.id
        FROM message m JOIN handle h ON m.handle_id = h.ROWID
        WHERE h.id IN ({qm})
        ORDER BY m.date, m.ROWID
    """
    out = []
    for rid, date, from_me, text, ab, amt_v, att, hid in c.execute(q, handles):
        body = text if text else decode_attributed_body(ab)
        kind = "message"
        if amt_v and amt_v in REACTIONS:
            kind = "reaction:" + REACTIONS[amt_v]
        elif amt_v and amt_v >= 3000:
            kind = "reaction-removed"
        elif not body and att:
            kind = "attachment"
        out.append({
            "seq": rid,
            "ts": stamp(_dt_utc(date / 1e9)),  # chat.db date is NANOSECONDS since 2001
            "direction": "sent" if from_me else "received",
            "kind": kind,
            "text": body,
            "handle": hid,
        })
    c.close()
    return out


def capture_whatsapp(wadb: str, jids: list[str], container: str,
                     media_dst: str, copy_audio: bool = True) -> list[dict]:
    c = open_ro(wadb)
    qm = ",".join("?" * len(jids))
    sessions = list(c.execute(
        f"SELECT Z_PK, ZCONTACTJID, ZPARTNERNAME FROM ZWACHATSESSION WHERE ZCONTACTJID IN ({qm})",
        jids,
    ))
    out = []
    for pk, jid, name in sessions:
        q = """
            SELECT m.Z_PK, m.ZMESSAGEDATE, m.ZISFROMME, m.ZTEXT, m.ZMESSAGETYPE,
                   md.ZMEDIALOCALPATH, md.ZMOVIEDURATION, md.ZTITLE,
                   md.ZVCARDNAME, md.ZFILESIZE
            FROM ZWAMESSAGE m
            LEFT JOIN ZWAMEDIAITEM md ON md.ZMESSAGE = m.Z_PK
            WHERE m.ZCHATSESSION = ?
            ORDER BY m.ZMESSAGEDATE, m.Z_PK
        """
        for (zpk, zdate, from_me, ztext, ztype, mpath, mdur, mtitle,
             vcard, fsize) in c.execute(q, (pk,)):
            kind = WA_TYPE.get(ztype, f"type-{ztype}")
            media = None
            if mpath:
                media = {"path": mpath, "duration_s": mdur, "title": mtitle,
                         "vcard": vcard, "bytes": fsize, "preserved": None}
                if copy_audio and (ztype == 3 or (mdur and mdur > 0)):
                    src = _resolve_wa_media(container, mpath)
                    if src:
                        os.makedirs(media_dst, exist_ok=True)
                        base = f"{zpk}_{os.path.basename(mpath)}"
                        dst = os.path.join(media_dst, base)
                        try:
                            shutil.copy2(src, dst)
                            media["preserved"] = os.path.join("media", base)
                        except Exception as e:
                            media["preserved"] = f"copy-failed: {e}"
            out.append({
                "seq": zpk,
                "ts": stamp(_dt_utc(float(zdate)) if zdate is not None else None),
                "direction": "sent" if from_me else "received",
                "kind": kind,
                "text": ztext,
                "media": media,
                "partner": name,
            })
    c.close()
    return out


def _resolve_wa_media(container: str, rel: str) -> str | None:
    for cand in (os.path.join(container, rel),
                 os.path.join(container, "Message", rel),
                 os.path.join(container, "Media", rel)):
        if os.path.isfile(cand):
            return cand
    return None


def write_jsonl(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_md(path: str, rows: list[dict], title: str, source: str, name: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    now = datetime.now(ET) if ET else datetime.now()
    lines = [f"# {title}",
             f"Captured {now.strftime('%Y-%m-%d %H:%M %Z')} · source `{source}` · {len(rows)} rows",
             ""]
    for r in rows:
        et = r["ts"]["et"] or "?"
        if r["direction"] == "sent":
            who = "→ (sent)"
        else:
            who = f"← {name}"
        if r["kind"].startswith("reaction"):
            lines.append(f"[{et}] {who} [{r['kind'].replace('reaction:', '')} a message]")
            continue
        txt = (r.get("text") or "").replace("\n", " ⏎ ")
        media = r.get("media")
        if media and not txt:
            dur = f", {media['duration_s']:.0f}s" if media.get("duration_s") else ""
            pres = f" [preserved → {media['preserved']}]" if media.get("preserved") else ""
            txt = f"[{r['kind']}{dur}]{pres}"
        elif not txt:
            txt = f"[{r['kind']}]"
        lines.append(f"[{et}] {who}: {txt}")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def run_person(slug: str, cfg: dict, args) -> dict:
    tape = os.path.join(args.out_root, slug, "tape")
    summary = {"slug": slug, "imessage": 0, "whatsapp": 0, "audio_preserved": 0}
    if cfg.get("imessage"):
        rows = capture_imessage(args.chatdb, cfg["imessage"])
        write_jsonl(os.path.join(tape, "imessage.jsonl"), rows)
        write_md(os.path.join(tape, "imessage.md"), rows,
                 f"{slug} — iMessage/SMS tape", args.chatdb, slug)
        summary["imessage"] = len(rows)
    if cfg.get("whatsapp_jid"):
        rows = capture_whatsapp(args.wadb, cfg["whatsapp_jid"], args.wa_container,
                                os.path.join(tape, "media"), copy_audio=not args.no_audio)
        write_jsonl(os.path.join(tape, "whatsapp.jsonl"), rows)
        write_md(os.path.join(tape, "whatsapp.md"), rows,
                 f"{slug} — WhatsApp tape", args.wadb, slug)
        summary["whatsapp"] = len(rows)
        summary["audio_preserved"] = sum(
            1 for r in rows if r.get("media") and str(r["media"].get("preserved", "")).startswith("media/"))
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description="Durable capture of iMessage + WhatsApp threads.")
    ap.add_argument("--roster", default=DEF_ROSTER)
    ap.add_argument("--out-root", default=DEF_OUT_ROOT)
    ap.add_argument("--chatdb", default=DEF_CHATDB)
    ap.add_argument("--wadb", default=DEF_WADB)
    ap.add_argument("--wa-container", default=DEF_WA_CONTAINER)
    ap.add_argument("--person", help="capture only this slug")
    ap.add_argument("--no-audio", action="store_true", help="do not copy voice-memo/audio blobs")
    ap.add_argument("--list-whatsapp", action="store_true",
                    help="print WhatsApp sessions (Z_PK | JID | name) and exit")
    args = ap.parse_args()

    if args.list_whatsapp:
        c = open_ro(args.wadb)
        for r in c.execute("SELECT Z_PK, ZCONTACTJID, ZPARTNERNAME FROM ZWACHATSESSION "
                           "ORDER BY ZLASTMESSAGEDATE DESC"):
            print(r)
        c.close()
        return 0

    if not os.path.exists(args.roster):
        print(f"roster not found: {args.roster}\n"
              f'create it as {{"people": {{"<slug>": {{"imessage": ["+1..."]}}}}}}',
              file=sys.stderr)
        return 2
    roster = json.load(open(args.roster))["people"]
    if args.person:
        roster = {args.person: roster[args.person]}

    total = {"imessage": 0, "whatsapp": 0, "audio_preserved": 0}
    for slug, cfg in roster.items():
        s = run_person(slug, cfg, args)
        total["imessage"] += s["imessage"]
        total["whatsapp"] += s["whatsapp"]
        total["audio_preserved"] += s["audio_preserved"]
        print(f"  {slug:22s} iMessage={s['imessage']:5d}  WhatsApp={s['whatsapp']:5d}  "
              f"audio_preserved={s['audio_preserved']}")
    print(f"  {'TOTAL':22s} iMessage={total['imessage']:5d}  WhatsApp={total['whatsapp']:5d}  "
          f"audio_preserved={total['audio_preserved']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
