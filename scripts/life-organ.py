#!/usr/bin/env python3
"""life-organ.py — THE EXECUTIVE LIFE OFFICE (digital accounts, assets & subscriptions).

The institutional force a person with civilizational wealth pays a staff to run — a records
keeper, an estate/asset steward, a subscriptions manager, the person who knows which account
is the real one and what gets deleted when — rebuilt as an organ. It is the digital-life
sibling of the health office (scripts/health-organ.py): same instinct, same firewall, a
different domain. Its constitution is docs/life-office/CHARTER.md.

The office runs standing DEPARTMENTS, each fail-open, none blocking another:

  THE INVENTORY SPINE (reactive — nothing about your accounts/assets silently lost):
    LEDGER     — keeps the Life Chart's integrity (platforms, accounts, IDs, ownership).
    ASSETS     — what you own and on which platform; the cross-platform transfer rules
                 (e.g. a save that can move PC<->Switch but never off PlayStation).
    DEDUP      — flags duplicate / conflicting accounts (which is canonical, which is dross)
                 so you never act on the wrong one.

  THE STEWARDSHIP WING (proactive — carry the load so he doesn't have to remember):
    SUBSCRIPTIONS — recurring memberships, and the DERIVED purge clock: when a membership
                    lapses, what data gets deleted and WHEN. The office computes the deadline
                    from the lapse date + a known purge rule (it never pins the date).
    INBOX         — the open actions only he can do (a save check on a physical console).
    BRIEFING      — rolls every department into one Executive Life Briefing + an append-only
                    chronicle, so the office has memory of the digital life over time.

DATA SEPARATION (the whole point — same firewall as health):
  - THE LIFE CHART lives OUTSIDE any git checkout, at $LIMEN_LIFE_DIR (default
    ~/Workspace/_life-private/digital-accounts.json). It holds account IDs / handles / partial
    payment refs and is structurally uncommittable.
  - This organ READS the chart and never mutates it.
  - It writes human-readable products (briefing, open-actions, chronicle) back into the
    PRIVATE dir, and writes a COUNTS-ONLY, PII-FREE liveness stamp into the repo's logs/ so
    organ-health.py can see it fired. No account ID ever reaches logs/, web/, or stdout.

Anti-waste + never-"NO": read-only on the chart, lockless (a pure generator — touches no
shared queue), fail-open everywhere. A missing chart yields a "no chart yet" stamp, never a
crash, and never blocks the beat.
"""
import json
import os
from datetime import date, datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
LIFE_DIR = Path(os.environ.get("LIMEN_LIFE_DIR", Path.home() / "Workspace" / "_life-private"))
CHART = LIFE_DIR / "digital-accounts.json"
CHRONICLE = LIFE_DIR / "chronicle.jsonl"
OVERDUE_DAYS = int(os.environ.get("LIMEN_LIFE_OVERDUE_DAYS", "0"))  # a purge deadline is overdue the moment it passes

# ── PURGE protocol library (general knowledge — derived, not pinned in the chart) ─────────────
# When a membership lapses, vendor policy deletes data after a known window. We DERIVE the
# deadline from the lapse date + the rule, so the chart records only WHAT lapsed and WHEN —
# never the computed deadline. Add a subscription that names a rule here and its clock lights up.
PURGE_RULES = {
    "nso_cloud_save": {
        "after_days": 183,  # ~6 months
        "what": "NSO cloud save data is deleted ~6 months after the membership lapses; "
                "re-subscribing does NOT restore a purged save (a local console save re-uploads fresh).",
        "source": "Nintendo Switch Online — Save Data Cloud policy",
    },
    "psplus_cloud_save": {
        "after_days": 183,
        "what": "PS Plus cloud saves are removed ~6 months after the subscription lapses.",
        "source": "PlayStation Plus — cloud storage policy",
    },
}


# ── chart access (fail-open) ──────────────────────────────────────────────────────────────────
def load_chart():
    try:
        obj = json.loads(CHART.read_text())
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


def _parse_date(s):
    """First YYYY-MM(-DD) in a string → date (month-only anchors to the 1st), else None."""
    if not s:
        return None
    import re
    m = re.search(r"(\d{4})-(\d{2})(?:-(\d{2}))?", str(s))
    if not m:
        return None
    y, mo, dd = int(m.group(1)), int(m.group(2)), m.group(3)
    try:
        return date(y, mo, int(dd) if dd else 1)
    except ValueError:
        return None


# ── SUBSCRIPTIONS department — derive the purge clock ─────────────────────────────────────────
def purge_watch(chart):
    """For each lapsed subscription that names a known purge rule, compute when the data is
    deleted and whether that deadline has passed. Returns a list of purge tracks."""
    tracks = []
    for s in (chart.get("subscriptions", []) or []):
        rule = PURGE_RULES.get(s.get("purge_rule"))
        if not rule or (s.get("status") or "").lower() != "lapsed":
            continue
        lapsed = _parse_date(s.get("lapsed_on"))
        track = {"service": s.get("service", "?"), "lapsed_on": s.get("lapsed_on"),
                 "what": rule["what"], "source": rule["source"], "note": s.get("note", ""),
                 "purge_on": None, "status": "unknown", "detail": "lapse date not recorded"}
        if lapsed:
            from datetime import timedelta
            purge_on = lapsed + timedelta(days=rule["after_days"])
            track["purge_on"] = purge_on.isoformat()
            days = (purge_on - date.today()).days
            if days > 0:
                track["status"] = "upcoming"
                track["detail"] = f"data deletes {purge_on.isoformat()} (in {days}d) — act before then"
            else:
                track["status"] = "purged" if -days > OVERDUE_DAYS else "due"
                track["detail"] = f"deadline {purge_on.isoformat()} passed {-days}d ago — assume the cloud copy is gone"
        tracks.append(track)
    return tracks


# ── DEDUP department — flag duplicate / conflicting accounts ──────────────────────────────────
def duplicates(chart):
    """Group accounts by platform; where a platform has more than one, surface which is
    canonical (role MAIN) and which is dross, with the merge/transfer constraint."""
    by_plat = {}
    for a in (chart.get("accounts", []) or []):
        by_plat.setdefault(a.get("platform", "?"), []).append(a)
    out = []
    for plat, accts in by_plat.items():
        if len(accts) < 2:
            continue
        main = next((a for a in accts if (a.get("role") or "").upper() == "MAIN"), None)
        out.append({"platform": plat, "count": len(accts), "accounts": accts, "main": main})
    return out


# ── INBOX department — the open actions only he can do ────────────────────────────────────────
def open_actions(chart):
    return [a for a in (chart.get("open_actions", []) or []) if (a.get("status") or "open") == "open"]


# ── derived view (all departments feed this) ─────────────────────────────────────────────────
def derive(chart):
    tracks = purge_watch(chart)
    dups = duplicates(chart)
    acts = open_actions(chart)
    return dict(
        platforms=chart.get("platforms", {}) or {},
        accounts=chart.get("accounts", []) or [],
        assets=chart.get("assets", []) or [],
        tracks=tracks,
        purge_due=sum(1 for t in tracks if t["status"] in ("due", "purged")),
        purge_upcoming=sum(1 for t in tracks if t["status"] == "upcoming"),
        dups=dups,
        actions=acts,
    )


# ── renderers (PRIVATE dir only — these carry PII) ──────────────────────────────────────────
def _stamp_line():
    return f"_Generated by the Executive Life Office · {datetime.now().isoformat(timespec='seconds')}_\n"


def _bottom_line(d):
    bits = []
    if d["actions"]:
        bits.append(f"**{len(d['actions'])} action(s)** waiting on you")
    if d["purge_due"]:
        bits.append(f"**{d['purge_due']} data-purge deadline(s) passed**")
    if d["purge_upcoming"]:
        bits.append(f"{d['purge_upcoming']} purge deadline(s) upcoming")
    if d["dups"]:
        bits.append(f"{sum(x['count'] for x in d['dups'])} duplicate account(s) to reconcile")
    if not bits:
        return "Nothing open — the office is quiet."
    return "; ".join(bits) + "."


def render_briefing(chart, d):
    L = ["# Executive Life Briefing\n", _stamp_line(), ""]
    L.append("> The standing report from your life office — the records keeper / asset steward / "
             "subscriptions manager for your digital life. Behind it: **`open-actions.md`** (only "
             "you can do these) and the chronicle of what's changed.\n")

    L.append("## The bottom line")
    L.append(_bottom_line(d))
    L.append("")

    if d["actions"]:
        L.append("## Waiting on you (only you can do these)")
        for a in d["actions"]:
            L.append(f"- **{a.get('ask','?')}**")
            if a.get("why"):
                L.append(f"  - _why:_ {a['why']}")
        L.append("")

    if d["tracks"]:
        L.append("## Data on the clock — subscriptions & purge deadlines")
        for t in d["tracks"]:
            icon = {"purged": "⏰", "due": "🔴", "upcoming": "🗓️", "unknown": "❔"}.get(t["status"], "•")
            L.append(f"- {icon} **{t['service']}** (lapsed {t.get('lapsed_on','?')}) — _{t['detail']}_")
            L.append(f"  - {t['what']}")
            L.append(f"  - _Source: {t['source']}_")
        L.append("")

    if d["assets"]:
        L.append("## What you own — and what can move where")
        for a in d["assets"]:
            L.append(f"- **{a.get('name','?')}** — owned on: {', '.join(a.get('owned_on', []) or ['?'])}")
            if a.get("cross_save"):
                L.append(f"  - _transfer:_ {a['cross_save']}")
            if a.get("note"):
                L.append(f"  - _note:_ {a['note']}")
        L.append("")

    if d["dups"]:
        L.append("## Duplicate accounts to reconcile")
        for x in d["dups"]:
            mainid = (x["main"] or {}).get("email") or (x["main"] or {}).get("handle") or "—"
            L.append(f"- **{x['platform']}** — {x['count']} accounts; canonical: **{mainid}**")
            for a in x["accounts"]:
                who = a.get("email") or a.get("handle") or "?"
                tag = " · MAIN" if (a.get("role") or "").upper() == "MAIN" else ""
                note = f" — _{a['note']}_" if a.get("note") else ""
                L.append(f"  - {who}{tag}{note}")
        L.append("")

    return "\n".join(L) + "\n"


def render_actions(chart, d):
    L = ["# What only you can do — your digital life\n", _stamp_line(),
         "The irreducible human acts (a save check on a physical console, a setting only you "
         "can change). Surfaced once; the office stops nagging after.\n"]
    if not d["actions"]:
        L.append("- _(nothing waiting on you right now)_")
    for a in d["actions"]:
        L.append(f"- **{a.get('ask','?')}**")
        if a.get("why"):
            L.append(f"  - _why:_ {a['why']}")
    return "\n".join(L) + "\n"


# ── BRIEFING department — append-only chronicle (institutional memory) ───────────────────────
def append_chronicle(d):
    today = date.today().isoformat()
    entry = {
        "date": today,
        "accounts": len(d["accounts"]),
        "assets": len(d["assets"]),
        "open_actions": len(d["actions"]),
        "purge_due": d["purge_due"],
        "purge_upcoming": d["purge_upcoming"],
        "duplicate_accounts": sum(x["count"] for x in d["dups"]),
    }
    try:
        lines = []
        if CHRONICLE.exists():
            lines = [ln for ln in CHRONICLE.read_text().splitlines()
                     if ln.strip() and json.loads(ln).get("date") != today]
        lines.append(json.dumps(entry))
        CHRONICLE.write_text("\n".join(lines) + "\n")
    except (OSError, ValueError):
        pass  # memory, not load-bearing — never block on it


# ── PII-free liveness stamp (repo logs/) ────────────────────────────────────────────────────
def write_stamp(present, d=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    rec = {"ran_at": datetime.now().isoformat(timespec="seconds"), "chart_present": present}
    if d is not None:
        rec.update({
            "accounts": len(d["accounts"]),
            "assets": len(d["assets"]),
            "open_actions": len(d["actions"]),
            "purge_due": d["purge_due"],
            "purge_upcoming": d["purge_upcoming"],
            "duplicate_accounts": sum(x["count"] for x in d["dups"]),
        })
    (LOGS / "life-organ-state.json").write_text(json.dumps(rec, indent=2))
    try:
        vd = LOGS / ".voice"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "life").write_text(rec["ran_at"])
    except OSError:
        pass


def main():
    chart = load_chart()
    if chart is None:
        write_stamp(present=False)
        print("life-office: no chart yet (expected at $LIMEN_LIFE_DIR/digital-accounts.json) — stamped, no-op")
        return 0

    d = derive(chart)
    try:
        LIFE_DIR.mkdir(parents=True, exist_ok=True)
        (LIFE_DIR / "briefing.md").write_text(render_briefing(chart, d))
        (LIFE_DIR / "open-actions.md").write_text(render_actions(chart, d))
        append_chronicle(d)
    except OSError as e:
        write_stamp(present=True, d=d)
        print(f"life-office: chart read but private dir unwritable ({e.__class__.__name__}) — stamped")
        return 0

    write_stamp(present=True, d=d)
    print(f"life-office: {len(d['accounts'])} accounts · {len(d['assets'])} assets · "
          f"{len(d['actions'])} action(s) waiting · "
          f"purge: {d['purge_due']} passed/{d['purge_upcoming']} upcoming · "
          f"{sum(x['count'] for x in d['dups'])} dupes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
