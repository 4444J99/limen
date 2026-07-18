#!/usr/bin/env python3
"""correspondence-walk — the walk-to-terminal driver for the correspondence organ.

THE PROBLEM IT CLOSES: reply-owed mail lives in obligations-ledger.json, and the beat's
send_drafts.py already SENDS the SAFE tier and DRAFTS the HOLD tier — but nothing stamps
EVERY reply-owed row with a single terminal disposition and proves the set is drained. The
three send pathways (autonomic beat, keyed single-fire, interactive CLI) coexist with no
iterator that walks the whole ledger to a fixed point. This is that iterator: each run it
reads the ledger, classifies every reply-owed obligation with the SAME tier logic the sender
uses (imported from UMA, never re-derived), and writes a PII-CLEAN disposition ledger where
each reply-owed row is exactly one of:

    sent | suppressed | held | steered-to-email | awaiting-them | needs-human

It is the effector twin of check-correspondence-terminal.py (the done-predicate sensor) and a
sibling of opportunity-review-delta.py one lane over: same fail-open, count-only, PII-clean
contract. It NEVER auto-sends HOLD — the load-bearing invariant (HOLD = legal/money/security
is drafted, never transmitted on a beat) is untouched; a `held` row is terminal-for-the-beat
(drafted, awaiting the operator's explicit key). The genuine transmission of a HOLD/precedent
reply stays the operator's keyed fire (send_drafts.py --fire), which this driver PROPOSES
(records the ready command in the sealed sidecar) but never performs. The only thing --drain
may transmit is the SAFE tier, and only when LIMEN_CORRESPONDENCE_FIRE=1 arms it.

DESIGN (bounded, fail-open, PII-clean, idempotent):
  - Reads the ledger (LIMEN_OBLIGATIONS_LEDGER). Imports tier_of/_ob_key/load_tiers from the
    UMA checkout (~/Workspace/universal-mail--automation). UMA absent ⇒ every reply-owed row
    fails open to `needs-human` (never a crash, never a wrong send).
  - Disposition is a PURE function of (tier, _ob_key ∈ drafts_sent, pending_on, has-draft,
    reply-path). Re-running on an unchanged ledger + unchanged drafts_sent yields identical
    rows ⇒ fixed_point:true. That is what the sensor asserts.
  - Writes logs/correspondence-dispositions.json — counts + ob_key/tier/disposition/reason
    only, NO sender/subject/body. Any PII (recipient, subject, fire command) goes to the
    sealed sidecar ~/Workspace/_people-private/correspondence/dispositions-detail.jsonl (0700).
  - --drain: ensure HOLD rows carry a composed draft (shells draft_writer.py --ledger); run
    contact_discovery for a LinkedIn row with no reply path; SAFE-tier auto-send ONLY when
    LIMEN_CORRESPONDENCE_FIRE=1 (default 0). HOLD/precedent are never transmitted here.
  - FAIL-OPEN: any error prints a PII-clean note and exits 0. It runs on the live beat; it
    must never red the beat and never leak a name.

Usage:
  python3 scripts/correspondence-walk.py            # dry: classify + write dispositions + counts
  python3 scripts/correspondence-walk.py --json     # machine-readable (count-only) summary
  python3 scripts/correspondence-walk.py --drain     # + compose held drafts, discover linkedin path
"""

from __future__ import annotations

import argparse
import imaplib
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
LEDGER = Path(os.environ.get("LIMEN_OBLIGATIONS_LEDGER", ROOT / "obligations-ledger.json"))
STATUS_JSON = LOGS / "correspondence-dispositions.json"
# The append-only drain-trend series: the counts-only MEMORY the snapshot above lacks, so a sensor
# can answer "is reply_owed draining across beats?" without a human reading it. One point per ledger
# rebuild (deduped by ledger_generated_at), soft-capped so the beat-read tail stays cheap.
TREND_JSONL = LOGS / "correspondence-drain-trend.jsonl"
TREND_MAX_ROWS = int(os.environ.get("LIMEN_CORRESPONDENCE_TREND_MAX_ROWS", "2000"))
MAX_AGE_HOURS = float(os.environ.get("LIMEN_MAIL_LEDGER_MAX_AGE_HOURS", "12"))

# The UMA checkout supplies the ONE tier truth (tier_of / _ob_key / load_tiers) and the send
# audit (audit/drafts_sent.json). Overridable for alt hosts; absent ⇒ fail-open to needs-human.
UMA_ROOT = Path(os.environ.get("UMA_ROOT", HOME / "Workspace" / "universal-mail--automation"))
APPLICATION_PIPELINE = HOME / "Workspace" / "application-pipeline"

# The sealed private correspondence estate (ARCA-sealed, never committed, never public).
CORR_PRIVATE = HOME / "Workspace" / "_people-private" / "correspondence"
DETAIL_SIDECAR = CORR_PRIVATE / "dispositions-detail.jsonl"

# The six terminal dispositions (closed enum). Every reply-owed row is exactly one.
DISPOSITIONS = ("sent", "suppressed", "held", "steered-to-email", "awaiting-them", "needs-human")
LINKEDIN_CLASS = "inbound-linkedin"


def _log_clean(msg: str) -> None:
    """PII-clean note to STDERR (captured by the beat log). Never a name, email, or subject."""
    print(f"correspondence-walk: {msg}", file=sys.stderr)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _import_uma():
    """Import the UMA send_drafts module (which pulls draft_writer). Returns the module or None.
    Fail-open: any import failure ⇒ None ⇒ every reply-owed row disposes to needs-human."""
    if not UMA_ROOT.exists():
        return None
    try:
        if str(UMA_ROOT) not in sys.path:
            sys.path.insert(0, str(UMA_ROOT))
        import send_drafts  # noqa: PLC0415 — deliberate runtime import from the UMA checkout
        return send_drafts
    except Exception as exc:  # noqa: BLE001 — beat safety: a broken UMA never crashes the walk
        _log_clean(f"UMA import failed ({type(exc).__name__}) — every reply-owed row → needs-human")
        return None


def _load_ledger() -> dict:
    try:
        data = json.loads(LEDGER.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _reply_owed(ledger: dict) -> list[dict]:
    obligations = ledger.get("obligations")
    if not isinstance(obligations, list):
        return []
    return [o for o in obligations if isinstance(o, dict) and o.get("requires_reply")]


def _has_draft(ob: dict) -> bool:
    return bool(str(ob.get("draft_text") or "").strip())


def _has_reply_path(ob: dict) -> bool:
    return bool(ob.get("reply_to") or ob.get("email") or ob.get("contact") or ob.get("reply_path"))


def _hold_reason(ob: dict) -> str:
    tags = set(ob.get("tags") or [])
    if "legal" in tags or ob.get("cls") in ("legal-correspondence", "legal-sign", "registered-agent"):
        return "legal — never auto-send; drafted for operator/client-side send"
    if "money" in tags:
        return "money — never auto-send; drafted for operator review"
    if "security" in tags or ob.get("verify_first"):
        return "security/verify-first — never auto-send; drafted for operator review"
    if ob.get("cls") == "precedent" or "human" in tags:
        return "precedent-human: fail-closed (no safe_intent) — draft composed for operator keyed send"
    return "hold tier — drafted, awaiting operator key"


def _recipient_addr(ob: dict) -> str:
    """Bare email to search Sent by: reply_to preferred, else sender. Strips 'Name <addr>'."""
    raw = (ob.get("reply_to") or ob.get("sender") or "").strip()
    if "<" in raw and ">" in raw:
        raw = raw[raw.find("<") + 1:raw.find(">")].strip()
    return raw if "@" in raw else ""


def _norm_subject(subject: str) -> str:
    """Strip leading Re:/Fwd:/Fw: prefixes (case-insensitive, repeatable) → the bare subject stem
    to match a sent reply against. Mirrors the normalization UMA's own handled-check uses."""
    s = str(subject or "")
    while True:
        m = re.match(r"^\s*(re|fwd|fw)\s*:\s*", s, re.IGNORECASE)
        if not m:
            break
        s = s[m.end():]
    return s.strip()


# Reason marker for a stale awaiting-them row flipped to a needs-human nudge. A module constant (not
# a magic string) so the status tally can count stale nudges without re-deriving the reason text.
STALE_NUDGE_PREFIX = "awaiting them "


def _parse_internaldate(fetch_data) -> datetime | None:
    """Parse the UTC datetime out of an IMAP FETCH (INTERNALDATE) response — PURE + offline-testable
    (no live IMAP). imaplib.Internaldate2tuple locates the INTERNALDATE "..." token itself and returns
    a local time.struct_time; time.mktime → epoch → an aware UTC datetime. Accepts the raw bytes line
    or a fetch tuple element. Returns None on any shape it can't parse (fail-open)."""
    parts = fetch_data if isinstance(fetch_data, (list, tuple)) else [fetch_data]
    for part in parts:
        raw = part
        if isinstance(part, tuple) and part:
            raw = part[0]
        if isinstance(raw, str):
            raw = raw.encode("utf-8", "replace")
        if not isinstance(raw, (bytes, bytearray)):
            continue
        try:
            t = imaplib.Internaldate2tuple(bytes(raw))
        except Exception:  # noqa: BLE001 — unparseable ⇒ try the next part, else None
            t = None
        if t:
            return datetime.fromtimestamp(time.mktime(t), tz=timezone.utc)
    return None


def _make_answered_checker(sd):
    """Build a callable ob->(datetime|None) that detects an ALREADY-SENT reply in [Gmail]/Sent Mail
    and returns WHEN it was sent, reusing ONE IMAP connection across rows. Returns (checker, provider)
    or (None, None).

    This is the SENT-state truth the ledger lacks: obligations_build sets requires_reply purely by
    classification (blind to whether a reply already went out — the operator's, a peer agent's, or
    via another channel). Reuses UMA's own read-only detector (providers/imap.py::_search_mailbox).
    FAIL-OPEN at every step: no creds / no UMA / connect error ⇒ (None, None) ⇒ SENT detection is
    simply skipped (never suppresses a genuine reply-owed row). Gated by LIMEN_CORRESPONDENCE_SENT_CHECK."""
    if os.environ.get("LIMEN_CORRESPONDENCE_SENT_CHECK", "1") != "1" or sd is None:
        return None, None
    user = os.environ.get("IMAP_USER") or os.environ.get("GMAIL_USER")
    pw = os.environ.get("IMAP_PASS") or os.environ.get("GMAIL_APP_PASSWORD")
    if not (user and pw):
        return None, None
    sent_mbx = os.environ.get("LIMEN_MAIL_SENT_MAILBOX", "[Gmail]/Sent Mail")
    try:
        from providers.imap import IMAPProvider  # UMA checkout already on sys.path via _import_uma
        prov = IMAPProvider(user=user, password=pw, use_gmail_extensions=True)
        prov.connect()
        # QUOTED mailbox — Python 3.14's imaplib no longer auto-quotes names with spaces/brackets,
        # so an unquoted SELECT "[Gmail]/Sent Mail" fails BAD (the latent bug that no-ops UMA's own
        # _search_mailbox / draft_writer.thread_already_handled on this host — flagged for a UMA fix).
        conn = prov._connection
        typ, _ = conn.select(f'"{sent_mbx}"', readonly=True)
        if typ != "OK":
            prov.disconnect()
            return None, None
    except Exception as exc:  # noqa: BLE001 — fail-open: no SENT detection this run
        _log_clean(f"sent-check disabled ({type(exc).__name__}) — dispositions from ledger only")
        return None, None

    def _answered(ob: dict) -> datetime | None:
        """The newest [Gmail]/Sent reply TO this recipient with the same subject stem, as its
        INTERNALDATE (aware UTC) — or None if no reply / any error (fail-open). The datetime is
        truthy, so a caller needing only a bool still works; _disposition uses the date to age
        a thread where the ball has sat on the counterparty too long."""
        to = _recipient_addr(ob)
        stem = _norm_subject((ob.get("sample_subjects") or [""])[0])
        if not to or not stem:
            return None
        try:  # a reply already exists in Sent TO this recipient with the same subject stem
            code, data = conn.uid("search", None, "TO", f'"{to}"', "SUBJECT", f'"{stem}"')
            if code != "OK" or not data or not data[0].split():
                return None
            newest = data[0].split()[-1]  # UIDs ascend ⇒ the last is the most-recent reply
            fcode, fdata = conn.uid("fetch", newest, "(INTERNALDATE)")
            if fcode != "OK" or not fdata:
                return None
            return _parse_internaldate(fdata)
        except Exception:  # noqa: BLE001 — fail-open per row (BAD search/fetch ⇒ not-answered)
            return None

    return _answered, prov


def _disposition(ob: dict, tiers, sent_keys: set, sd, answered_fn=None,
                 now: datetime | None = None, stale_days: int = 0) -> tuple[str, str, bool]:
    """Pure-ish disposition for one reply-owed obligation. Returns (disposition, reason, draft_missing).

    draft_missing marks a HOLD row that still lacks a composed draft — the one non-terminal
    residue the done-predicate sensor fails on (mirrors check-mail-answered's undrafted rule).
    answered_fn (optional) is the SENT-state checker (ob -> datetime|None) — its only impurity, and
    it fails open. now/stale_days age an out-of-band-answered thread: a reply older than stale_days
    (stale_days>0) flips awaiting-them → a needs-human nudge (follow up or drop)."""
    # UMA unavailable ⇒ we cannot classify or trust idempotency ⇒ fail-open to needs-human.
    if sd is None:
        return "needs-human", "UMA tier logic unavailable — cannot classify safely", True

    key = sd._ob_key(ob)
    # 1. Already transmitted via the system's own audit (idempotent). A re-run can never re-send.
    if key in sent_keys:
        return "sent", "transmitted (present in drafts_sent.json)", False

    # 1b. SENT-state truth: a reply already exists in [Gmail]/Sent Mail — answered by the operator,
    #     a peer agent, or another channel (the out-of-band send the ledger is blind to). Ball on them.
    #     If that reply is older than stale_days, the ball has sat on them too long: flip to a
    #     needs-human nudge (follow up or drop) instead of a silent, ageless awaiting-them. A stale
    #     nudge is NOT recorded as answered upstream, so it keeps surfacing until the operator acts.
    if answered_fn is not None:
        sent_at = answered_fn(ob)
        if sent_at is not None:
            ref = now or datetime.now(timezone.utc)
            age_days = (ref - sent_at).days
            if stale_days and age_days > stale_days:
                return ("needs-human",
                        f"{STALE_NUDGE_PREFIX}{age_days}d — we replied {sent_at:%Y-%m-%d}, no response; follow up or drop",
                        False)
            return "awaiting-them", "reply already in [Gmail]/Sent — thread answered out-of-band", False

    cls = ob.get("cls", "")
    # 2. LinkedIn / noreply relay — structurally unsendable in place.
    if cls == LINKEDIN_CLASS:
        if _has_reply_path(ob):
            return "steered-to-email", "linkedin inbound with a reply path — steer/keyed-fire to email", False
        return "needs-human", "linkedin inbound, no reply path — reply in LinkedIn UI or run contact discovery", False

    tier = sd.tier_of(ob, tiers) if tiers is not None else "hold"

    # 3. Bulk / ESP — reply not owed.
    if tier == "no_reply":
        return "suppressed", "no_reply tier — bulk/ESP, reply not owed", False

    # 4. Ball already on the counterparty (we replied earlier by another channel).
    if str(ob.get("pending_on") or "").lower() in ("them", "counterparty"):
        return "awaiting-them", "reply previously sent — ball on the counterparty", False

    # 5. SAFE tier — the only tier the armed beat auto-sends. Unsent ⇒ pending armed send.
    if tier == "safe":
        return "held", "safe-tier — awaiting armed auto-send (flips to sent once fired)", False

    # 6. HOLD (or unknown → fail-closed hold). Terminal-for-the-beat iff a draft exists.
    if _has_draft(ob):
        return "held", _hold_reason(ob), False
    return "held", _hold_reason(ob) + " [DRAFT MISSING — draft effector has not run]", True


def _draft_writer_pass() -> str | None:
    """Ensure every reply-owed HOLD row is enriched with a composed draft (the draft effector).
    Shells UMA draft_writer.py --ledger. Fail-open: absent/erroring ⇒ a PII-clean note."""
    dw = UMA_ROOT / "draft_writer.py"
    if not dw.exists():
        return "draft_writer.py not found — held rows may lack drafts (fail-open)"
    try:
        proc = subprocess.run(
            [sys.executable, str(dw), "--ledger", str(LEDGER)],
            capture_output=True, timeout=120, cwd=str(UMA_ROOT),
        )
        return None if proc.returncode == 0 else f"draft_writer exited {proc.returncode} (fail-open)"
    except (OSError, subprocess.SubprocessError):
        return "draft_writer could not run (fail-open)"


def _contact_discovery(entry_slug: str) -> str | None:
    """For a LinkedIn row with no reply path, shell application-pipeline contact_discovery.py.
    Fail-open, public-sources only (the script itself never SMTP-probes). Returns a PII-clean note."""
    if not APPLICATION_PIPELINE.exists():
        return None
    for sub in ("scripts", "tools"):
        cand = APPLICATION_PIPELINE / sub / "contact_discovery.py"
        if cand.exists():
            try:
                subprocess.run(
                    [sys.executable, str(cand), "--entry", entry_slug, "--json"],
                    capture_output=True, timeout=120, cwd=str(APPLICATION_PIPELINE),
                )
                return "contact_discovery ran (result in sealed sidecar)"
            except (OSError, subprocess.SubprocessError):
                return "contact_discovery could not run (fail-open)"
    return "contact_discovery.py not found (fail-open)"


def _write_sidecar(rows_pii: list[dict]) -> None:
    """Append the PII detail (recipient, subject, ready fire command) to the sealed 0700 sidecar.
    Never committed, never public. Best-effort — a write error is noted, never fatal."""
    if not rows_pii:
        return
    try:
        CORR_PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
        stamp = _now()
        with DETAIL_SIDECAR.open("a", encoding="utf-8") as fh:
            for r in rows_pii:
                fh.write(json.dumps({**r, "recorded_at": stamp}) + "\n")
    except OSError:
        _log_clean("could not append sealed sidecar (fail-open)")


def _write_status(status: dict) -> None:
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        STATUS_JSON.write_text(json.dumps(status, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        _log_clean("could not write logs/correspondence-dispositions.json (fail-open)")


def _append_trend(status: dict) -> None:
    """Append ONE counts-only point per new ledger snapshot to logs/correspondence-drain-trend.jsonl —
    the append-only memory the disposition SNAPSHOT lacks, so check-correspondence-drain-trend.py can
    answer "is reply_owed draining across beats?" without a human reading it.

    Deduped by ledger_generated_at: re-running the walk on the SAME ledger adds nothing (matching the
    walk's own fixed-point contract), so the series is one point per beat, not per invocation. Soft-
    capped to the last TREND_MAX_ROWS. Counts only — never a name/subject; this face publishes. Fail-
    open at every step: a read/write error is noted, never fatal (it runs on the live beat)."""
    point = {
        "timestamp": status.get("generated_at"),
        "ledger_generated_at": status.get("ledger_generated_at"),
        "reply_owed": status.get("reply_owed"),
        "terminal": status.get("terminal"),
        "needs_human": status.get("needs_human"),
        "draft_missing": status.get("non_terminal"),
        "fixed_point": status.get("fixed_point"),
    }
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        lines = []
        try:
            lines = [ln for ln in TREND_JSONL.read_text(encoding="utf-8").splitlines() if ln.strip()]
        except OSError:
            lines = []
        # Dedup: skip when the last point is the SAME ledger rebuild (a re-walk, not a new beat). A
        # None ledger stamp is never deduped (would collapse distinct unstamped runs into one).
        if lines and point["ledger_generated_at"] is not None:
            try:
                if json.loads(lines[-1]).get("ledger_generated_at") == point["ledger_generated_at"]:
                    return
            except ValueError:
                pass  # a torn last line ⇒ just append a fresh point
        lines.append(json.dumps(point))
        if len(lines) > TREND_MAX_ROWS:
            lines = lines[-TREND_MAX_ROWS:]
        TREND_JSONL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError:
        _log_clean("could not append logs/correspondence-drain-trend.jsonl (fail-open)")


def _record_answered_keys(keys: set[str]) -> None:
    """Persist the _ob_keys of rows answered out-of-band (disposition sent/awaiting-them) to UMA's
    audit/answered_keys.json — the offline drain signal obligations_build.build() reads to RETIRE
    those rows so reply_owed falls instead of re-materializing every beat. UNION with the existing
    set: receipts persist, so a key must stay recorded until its own receipt ages out. The file is
    gitignored (it holds _ob_keys); a missing/torn file starts empty. Fail-open at every step — a
    write error is noted, never fatal, so the beat never reds and the drain simply no-ops that run."""
    if not keys:
        return
    path = UMA_ROOT / "audit" / "answered_keys.json"
    try:
        existing: set[str] = set()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                existing = set(data)
        except (OSError, ValueError):
            existing = set()
        merged = sorted(existing | keys)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    except OSError:
        _log_clean("could not write audit/answered_keys.json (fail-open)")


def _emit_notify(title: str, msg: str) -> None:
    """Push a COUNT-ONLY line through the EXISTING notify cascade (notify-events._emit → macOS + ntfy),
    the same effector opportunity-review-delta uses. Fail-open: unimportable/erroring ⇒ skip silently,
    never crash the beat, never a click-list."""
    try:
        spec = importlib.util.spec_from_file_location(
            "_notify_events_probe", ROOT / "scripts" / "notify-events.py")
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        emit = getattr(module, "_emit", None)
        if callable(emit):
            emit(title, msg)
    except Exception:  # noqa: BLE001 — best-effort; never red the beat
        pass


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Correspondence walk-to-terminal driver (count-only, PII-clean).")
    ap.add_argument("--drain", action="store_true", help="compose held drafts + run linkedin contact discovery")
    ap.add_argument("--notify", action="store_true",
                    help="push a count-only macOS/ntfy line when items need a human (never a click-list)")
    ap.add_argument("--json", action="store_true", help="print a machine-readable (count-only) summary")
    args = ap.parse_args(argv)

    try:  # FAIL-OPEN wrapper: nothing below may red the beat or leak a name.
        sd = _import_uma()
        tiers = sd.load_tiers() if sd is not None else None
        sent_keys = sd._load_sent() if sd is not None else set()
        # SENT-state truth (the ledger is blind to out-of-band sends): one reused IMAP connection,
        # fail-open to (None, None) when creds/UMA/connection are unavailable.
        answered_fn, answered_prov = _make_answered_checker(sd)

        # The keyed-fire arm + cap. LIMEN_CORRESPONDENCE_FIRE (default 0) governs whether --drain
        # may actually transmit SAFE-tier rows (HOLD is never fired here — that invariant lives in
        # send_drafts.py); LIMEN_CORRESPONDENCE_MAX bounds how many fires a single walk may propose
        # or perform, mirroring LIMEN_MAIL_SEND_MAX so one run can never blast the whole ledger.
        fire_armed = os.environ.get("LIMEN_CORRESPONDENCE_FIRE", "0") == "1"
        fire_cap = _int_env("LIMEN_CORRESPONDENCE_MAX", 10)
        fires_proposed = 0

        ledger = _load_ledger()
        gen_at = str(ledger.get("generated_at") or "")
        reply_owed = _reply_owed(ledger)

        # --drain: run the draft effector FIRST so held rows carry composed drafts, then reclassify.
        drain_notes: list[str] = []
        if args.drain:
            note = _draft_writer_pass()
            if note:
                drain_notes.append(note)
            ledger = _load_ledger()  # re-read: draft_writer enriched draft_text in place
            reply_owed = _reply_owed(ledger)

        rows: list[dict] = []          # PII-CLEAN — safe for the committed-ish logs face
        rows_pii: list[dict] = []      # sealed sidecar only
        by_disposition = {d: 0 for d in DISPOSITIONS}
        draft_missing = 0
        needs_human = 0
        answered_this_run: set[str] = set()   # drain signal → audit/answered_keys.json
        stale_awaiting = 0                     # awaiting-them rows aged past the stale threshold → nudge
        # Age a thread where the ball has sat on them too long. 0 (or an unparseable value) disables
        # the nudge — awaiting-them then behaves exactly as before. Same clock for every row this walk.
        stale_days = _int_env("LIMEN_CORRESPONDENCE_AWAIT_STALE_DAYS", 14)
        walk_now = datetime.now(timezone.utc)

        for ob in reply_owed:
            disp, reason, missing = _disposition(ob, tiers, sent_keys, sd, answered_fn,
                                                 now=walk_now, stale_days=stale_days)
            key = sd._ob_key(ob) if sd is not None else f"?|?|{(ob.get('sample_subjects') or [''])[0][:40]}"
            by_disposition[disp] += 1
            if disp == "needs-human" and reason.startswith(STALE_NUDGE_PREFIX):
                stale_awaiting += 1
            # A row answered out-of-band (a reply already in [Gmail]/Sent) is terminal — record its
            # canonical key so obligations_build retires it and reply_owed drains. Only when sd is
            # real (never the "?|?|" placeholder, which would poison the set with a non-canonical key).
            if disp in ("sent", "awaiting-them") and sd is not None:
                answered_this_run.add(key)
            if missing:
                draft_missing += 1
            if disp == "needs-human":
                needs_human += 1
            channel = "linkedin" if ob.get("cls") == LINKEDIN_CLASS else "email"
            rows.append({
                "ob_key": key,
                "cls": ob.get("cls", ""),
                "tier": (sd.tier_of(ob, tiers) if sd is not None else "hold"),
                "disposition": disp,
                "reason": reason,
                "has_draft": _has_draft(ob),
                "channel": channel,
                "draft_missing": missing,
            })
            # Sidecar: only rows that need an action carry PII (recipient, subject, ready command).
            if disp in ("held", "steered-to-email", "needs-human"):
                # Propose a keyed-fire command only for actionable rows, bounded by fire_cap so a
                # large ledger never emits an unbounded fire list. needs-human never gets a command.
                propose = disp in ("held", "steered-to-email") and fires_proposed < fire_cap
                rows_pii.append({
                    "ob_key": key,
                    "disposition": disp,
                    "recipient": ob.get("reply_to") or ob.get("sender") or "",
                    "subject": (ob.get("sample_subjects") or [""])[0],
                    "fire_command": (f'send_drafts.py --fire-obligation "{key}" --fire' if propose else ""),
                    "fire_capped": disp in ("held", "steered-to-email") and not propose,
                })
                if propose:
                    fires_proposed += 1
            # --drain effector for a LinkedIn no-path row: DEFER to the opportunity lane's own
            # auto-discovery (opportunity_sync.py::maybe_run_discovery, which already runs
            # contact_discovery for inbound-linkedin no-path rows) when application-pipeline is
            # present — one owner for the LinkedIn→email steer, no double discovery. Only fall back
            # to a direct call when that lane is absent.
            if args.drain and disp == "needs-human" and ob.get("cls") == LINKEDIN_CLASS:
                if APPLICATION_PIPELINE.exists():
                    if "discovery deferred" not in " ".join(drain_notes):
                        drain_notes.append("linkedin no-path — discovery deferred to opportunity_sync (application-pipeline owns it)")
                else:
                    cnote = _contact_discovery("linkedin-com--inbound")
                    if cnote:
                        drain_notes.append(cnote)

        # Persist the drain signal for build's retire step — unconditional (SENT-detection runs on
        # every walk, not only --drain). Count-only note; the keys live in the gitignored audit file,
        # never the committed logs face.
        if answered_this_run:
            _record_answered_keys(answered_this_run)
            drain_notes.append(
                f"drain: recorded {len(answered_this_run)} answered key(s) → obligations_build retires them next build")

        if args.drain and fire_armed:
            drain_notes.append(
                f"LIMEN_CORRESPONDENCE_FIRE armed — SAFE-tier fires delegated to the beat sender "
                f"(send_drafts.py, LIMEN_MAIL_SEND); HOLD stays operator-keyed. "
                f"{fires_proposed}/{fire_cap} fires proposed this run.")

        terminal = len(reply_owed) - draft_missing
        fixed_point = (draft_missing == 0) and (sd is not None)

        status = {
            "schema": "limen.correspondence.dispositions.v1",
            "generated_at": _now(),
            "ledger_generated_at": gen_at,
            "reply_owed": len(reply_owed),
            "terminal": terminal,
            "non_terminal": draft_missing,
            "needs_human": needs_human,
            "stale_awaiting": stale_awaiting,   # awaiting-them threads aged past the nudge threshold
            "by_disposition": by_disposition,
            "fixed_point": fixed_point,
            "uma_available": sd is not None,
            "sent_check_active": answered_fn is not None,
            "fire_armed": fire_armed,
            "fires_proposed": fires_proposed,
            "fire_cap": fire_cap,
            "rows": rows,  # PII-clean by construction (ob_key/cls/tier/disposition/reason/flags)
            "drain_notes": drain_notes,
        }
        _write_status(status)
        _append_trend(status)   # append one drain-trend point per ledger rebuild (convergence memory)
        _write_sidecar(rows_pii)

        if answered_prov is not None:
            try:
                answered_prov.disconnect()
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass

        # --notify: push a COUNT-ONLY line ONLY when something genuinely needs a human (a needs-human
        # row or a HOLD row still missing its draft). A fully-drained walk pushes nothing. No names,
        # ever — the count face, not a click-list.
        if args.notify and (needs_human or draft_missing):
            _emit_notify(
                "LIMEN correspondence",
                f"{needs_human} need-human, {draft_missing} draft-missing across {len(reply_owed)} reply-owed",
            )

        summary = (
            f"correspondence-walk: {len(reply_owed)} reply-owed — "
            + ", ".join(f"{v} {k}" for k, v in by_disposition.items() if v)
            + (f" · {draft_missing} draft-missing" if draft_missing else "")
            + (" · fixed_point" if fixed_point else " · NOT fixed_point")
        )
        if args.json:
            print(json.dumps({
                "reply_owed": len(reply_owed),
                "by_disposition": by_disposition,
                "non_terminal": draft_missing,
                "needs_human": needs_human,
                "fixed_point": fixed_point,
                "uma_available": sd is not None,
            }))
        else:
            print(summary)
        return 0
    except Exception as exc:  # noqa: BLE001 — beat safety: never propagate, never leak the message
        _log_clean(f"skipped on error ({type(exc).__name__})")
        return 0


if __name__ == "__main__":
    sys.exit(main())
