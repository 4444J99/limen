#!/usr/bin/env python3
"""health-organ.py — THE EXECUTIVE HEALTH OFFICE.

The institutional force a person with civilizational wealth pays a small staff to run —
care coordinator, patient advocate, records keeper, medical librarian, chief-of-staff —
rebuilt as an organ. It is NOT a clinician. The doctor/therapist is a human input; this is
the OFFICE around the clinician. Its constitution is docs/health-office/CHARTER.md.

The office runs ten standing DEPARTMENTS in two wings, each fail-open, none blocking another.

  THE CLINICAL SPINE — the office *around the clinician* (reactive: nothing drops):
    RECORDS       — keeps the Chart's integrity (problem list, meds, providers, results).
    COORDINATION  — appointments, the calendar bridge, and the results ledger (nothing
                    ordered is allowed to silently never come back).
    ADVOCACY      — per-visit prep, the visit script, ready-to-read provider messages.
    SURVEILLANCE  — protocol-driven monitoring/screening recalls derived from the meds and
                    risk factors (e.g. the antipsychotic metabolic-monitoring schedule).
    PHARMACY      — the medication list and the monitoring each drug obligates.

  THE HABILITATION WING — the office that runs the life toward fitness (proactive: it
  carries the cognitive load so he doesn't have to think about it or remember it):
    REGIMEN       — the shape of the day; the schedule lives here, not in his head.
    KITCHEN       — the weekly menu + consolidated grocery list, so "what do I eat / cook"
                    is already answered.
    MOVEMENT      — a gently-ramped weekly movement plan; sessions meant for the calendar.
    SLEEP         — the keystone: a steady wake/bed target + a nightly protocol.

    BRIEFING      — rolls every department into one Executive Health Briefing + an append-
                    only chronicle, so the office has memory of the health over time.

DATA SEPARATION (the whole point):
  - THE CHART lives OUTSIDE any git checkout, at $LIMEN_HEALTH_DIR (default
    ~/Workspace/_health-private/chart.json). It holds medical PII and is structurally
    uncommittable — same instinct as the FERPA quarantine.
  - This organ READS the chart and never mutates it (your record changes only deliberately).
  - It writes human-readable products (briefing, surveillance, visit-prep, chronicle) back
    into the PRIVATE dir, and writes a COUNTS-ONLY, PII-FREE liveness stamp into the repo's
    logs/ so organ-health.py can see it fired. No medical text ever reaches logs/, web/, or
    stdout. The office's general REFERENCE library (docs/health-office/reference/) names no
    patient and may live in the repo.

Anti-waste + never-"NO": read-only on the chart, lockless (a pure generator — touches no
shared queue), fail-open everywhere. A missing chart yields a "no chart yet" stamp, never a
crash, and never blocks the beat.
"""

import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
HEALTH_HOME = ROOT / "organs" / "health"
HEALTH_DIR = Path(os.environ.get("LIMEN_HEALTH_DIR", Path.home() / "Workspace" / "_health-private"))
CHART = HEALTH_DIR / "chart.json"
PREP = HEALTH_DIR / "prep"
CHRONICLE = HEALTH_DIR / "chronicle.jsonl"
OBSERVATIONS = (
    HEALTH_DIR / "observations.jsonl"
)  # off-repo: what ACTUALLY happened (he logs it / another organ feeds it)


def _env_positive_int(name, default):
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


OVERDUE_DAYS = _env_positive_int("LIMEN_HEALTH_OVERDUE_DAYS", 14)
LEARN_WINDOW_DAYS = _env_positive_int("LIMEN_HEALTH_LEARN_DAYS", 21)  # how far back the office learns your real rhythm
MIN_OBSERVATIONS = _env_positive_int("LIMEN_HEALTH_MIN_OBS", 3)  # won't reshape an anchor on fewer days than this

_WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}

# ── SURVEILLANCE protocol library (general clinical knowledge — derived, not patient data) ──
# Second-generation ("atypical") antipsychotics carry an FDA hyperglycemia warning and an
# ADA/APA consensus metabolic-monitoring schedule. We DERIVE the obligation from the drug
# name (never pin it in the chart), so adding any drug in this class lights up the schedule.
ANTIPSYCHOTICS = {
    "quetiapine",
    "olanzapine",
    "risperidone",
    "paliperidone",
    "aripiprazole",
    "clozapine",
    "ziprasidone",
    "lurasidone",
    "asenapine",
    "cariprazine",
    "brexpiprazole",
}
# weeks-after-start → panel that comes due at that visit (ADA/APA consensus)
METABOLIC_SCHEDULE = [
    {
        "key": "baseline",
        "week": 0,
        "label": "Baseline (at start)",
        "items": [
            "weight / BMI",
            "waist",
            "blood pressure",
            "fasting glucose",
            "fasting lipids",
            "personal & family history",
        ],
    },
    {"key": "wk4", "week": 4, "label": "4 weeks", "items": ["weight / BMI", "fasting lipids"]},
    {"key": "wk8", "week": 8, "label": "8 weeks", "items": ["weight / BMI"]},
    {
        "key": "wk12",
        "week": 12,
        "label": "12 weeks",
        "items": ["weight / BMI", "waist", "blood pressure", "fasting glucose or A1c", "fasting lipids"],
    },
]
METABOLIC_RECURRING = [
    {
        "key": "annual",
        "every_weeks": 52,
        "label": "Annually",
        "items": ["weight / BMI", "waist", "blood pressure", "fasting glucose or A1c", "fasting lipids"],
    },
]
METABOLIC_SOURCE = "ADA/APA consensus on antipsychotic drugs, obesity & diabetes — see docs/health-office/reference/quetiapine-metabolic-monitoring.md"

# ── KITCHEN starter menu (general knowledge — a simple, higher-protein/higher-fiber, lower-
# added-sugar rotation that's easy to cook; the EMPHASIS is derived from the chart's conditions,
# never a fad. Filtered around the principal's stated likes/dislikes/allergies). ──
MENU = {
    "breakfast": [
        {"name": "Greek yogurt with berries & walnuts", "buy": ["Greek yogurt", "frozen berries", "walnuts"]},
        {"name": "Veggie scramble (eggs, spinach, tomato)", "buy": ["eggs", "spinach", "tomatoes"]},
        {"name": "Overnight oats with chia & apple", "buy": ["rolled oats", "chia seeds", "apples", "milk"]},
        {"name": "Cottage cheese, sliced pear & flax", "buy": ["cottage cheese", "pears", "ground flax"]},
        {"name": "Whole-grain toast, eggs & avocado", "buy": ["whole-grain bread", "eggs", "avocado"]},
    ],
    "lunch": [
        {"name": "Chicken & chickpea salad bowl", "buy": ["chicken breast", "chickpeas", "mixed greens", "olive oil"]},
        {"name": "Tuna & white-bean lettuce wraps", "buy": ["canned tuna", "white beans", "lettuce", "lemon"]},
        {"name": "Lentil soup with a side salad", "buy": ["lentils", "carrots", "onion", "mixed greens"]},
        {
            "name": "Turkey & hummus whole-grain wrap",
            "buy": ["turkey slices", "hummus", "whole-grain wraps", "spinach"],
        },
        {"name": "Quinoa bowl, black beans & salsa", "buy": ["quinoa", "black beans", "salsa", "bell pepper"]},
    ],
    "dinner": [
        {"name": "Baked salmon, roasted broccoli, brown rice", "buy": ["salmon", "broccoli", "brown rice"]},
        {
            "name": "Chicken & vegetable stir-fry",
            "buy": ["chicken breast", "frozen stir-fry vegetables", "soy sauce", "brown rice"],
        },
        {"name": "Turkey chili with beans", "buy": ["ground turkey", "kidney beans", "canned tomatoes", "onion"]},
        {"name": "Sheet-pan tofu & vegetables", "buy": ["firm tofu", "mixed vegetables", "olive oil"]},
        {"name": "White-fish tacos with cabbage slaw", "buy": ["white fish", "corn tortillas", "cabbage", "lime"]},
    ],
}
MENU_SOURCE = "general healthy-eating emphasis for metabolic risk — see docs/health-office/reference/nutrition-for-metabolic-risk.md"


# ── chart access (fail-open) ──────────────────────────────────────────────────────────────────
def load_chart():
    try:
        obj = json.loads(CHART.read_text())
        return obj if isinstance(obj, dict) else None
    except (OSError, ValueError):
        return None


def _days_since(iso):
    try:
        return (date.today() - date.fromisoformat(iso[:10])).days
    except (ValueError, TypeError):
        return None


def _fmt_time(hhmm):
    """24h 'HH:MM' → friendly '7:00 AM'. Tolerant of junk."""
    try:
        h, m = (int(x) for x in str(hhmm).split(":")[:2])
        ap = "AM" if h < 12 else "PM"
        return f"{h % 12 or 12}:{m:02d} {ap}"
    except (ValueError, AttributeError):
        return str(hhmm or "")


def _next_appt_days(appt):
    """Days until the next occurrence of a weekly appointment (None if day-of-week unknown)."""
    dow = (appt.get("day_of_week") or "").strip().lower()
    if dow not in _WEEKDAYS:
        return None
    delta = (_WEEKDAYS[dow] - date.today().weekday()) % 7
    return delta  # 0 = today


def _ledger(chart):
    """Results ledger, tolerant of either a bare list or a {_comment, entries:[]} block."""
    rl = chart.get("results_ledger", []) or []
    if isinstance(rl, dict):
        rl = rl.get("entries", []) or []
    return rl if isinstance(rl, list) else []


def _parse_start(s):
    """Extract a start date from a possibly-approximate 'started' string.
    Returns (date|None, approximate:bool). Month-only anchors to the 1st (approximate)."""
    if not s:
        return None, True
    m = re.search(r"(\d{4})-(\d{2})(?:-(\d{2}))?", str(s))
    if not m:
        return None, True
    y, mo, dd = int(m.group(1)), int(m.group(2)), m.group(3)
    approx = ("approx" in str(s).lower()) or ("~" in str(s)) or (dd is None)
    try:
        return date(y, mo, int(dd) if dd else 1), approx
    except ValueError:
        return None, True


# ══ THE LIVING LAYER — the office reaches into the past and reshapes the future ══════════════
# Autopoiesis: the office does not merely render the chart. It (1) METABOLIZES ITS OWN MEMORY —
# the append-only chronicle it has kept — to see where the health is heading, not just where it
# is; and (2) LEARNS THE REAL RHYTHM from observations of what actually happened, then reshapes
# the day's frame toward it. It never mutates the Chart: the learned frame is computed at
# render-time and narrated, so the schedule fits the principal instead of the principal fitting
# the schedule, and so being well costs a little less thought each week.


def _to_min(hhmm):
    """'HH:MM' → minutes since midnight, or None."""
    try:
        h, m = (int(x) for x in str(hhmm).split(":")[:2])
        return h * 60 + m
    except (ValueError, AttributeError):
        return None


def _from_min(m):
    """minutes → 'HH:MM' (24h)."""
    m = int(round(m)) % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def _median(xs):
    xs = sorted(xs)
    n = len(xs)
    if not n:
        return None
    mid = n // 2
    return xs[mid] if n % 2 else (xs[mid - 1] + xs[mid]) / 2


def _round5(m):
    return int(round(m / 5.0)) * 5


def load_observations():
    """Off-repo log of what ACTUALLY happened — one JSON object per line, every field optional:
        {"date":"2026-06-23","wake":"07:25","sleep":"23:05","moved":true}
    The office reads it; it never requires it. A missing or garbled file simply means
    'still learning' — the office holds the stated frame until real days accumulate."""
    try:
        out = []
        for ln in OBSERVATIONS.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                o = json.loads(ln)
                if isinstance(o, dict):
                    out.append(o)
            except ValueError:
                continue
        return out
    except OSError:
        return []


def _recent_obs(obs):
    cutoff = date.today() - timedelta(days=LEARN_WINDOW_DAYS)
    keep = []
    for o in obs:
        try:
            if date.fromisoformat(str(o.get("date", ""))[:10]) >= cutoff:
                keep.append(o)
        except (ValueError, TypeError):
            continue
    return keep


def learn_rhythm(chart, obs):
    """Produce the office's OWN knowledge of the rhythm from what actually happened, and a
    working 'frame' that bends toward it. Anchored: a keystone only moves once there's real
    evidence (>= MIN_OBSERVATIONS days); otherwise it holds the stated target. Returns the dict
    the renderers use to shape the day — and to narrate what changed and why."""
    reg = chart.get("regimen", {}) or {}
    recent = _recent_obs(obs)
    out = {
        "learned": False,
        "n": len(recent),
        "window": LEARN_WINDOW_DAYS,
        "wake": None,
        "sleep": None,
        "moved_rate": None,
        "changes": [],
    }

    def fit(field, target_hhmm, label):
        vals = [_to_min(o.get(field)) for o in recent if o.get(field)]
        vals = [v for v in vals if v is not None]
        tgt = _to_min(target_hhmm)
        if len(vals) < MIN_OBSERVATIONS:
            return {"target": target_hhmm, "observed": None, "frame": target_hhmm, "n": len(vals), "learned": False}
        observed = _round5(_median(vals))
        info = {
            "target": target_hhmm,
            "observed": _from_min(observed),
            "frame": _from_min(observed),
            "n": len(vals),
            "learned": True,
        }
        if tgt is not None and abs(observed - tgt) >= 10:
            out["changes"].append(
                f"Set your **{label}** frame to {_fmt_time(_from_min(observed))} — that's your real "
                f"median over {len(vals)} days (your stated target is {_fmt_time(target_hhmm)}). "
                "The office fit the day to you, not the other way around."
            )
        return info

    out["wake"] = fit("wake", reg.get("wake"), "wake")
    out["sleep"] = fit("sleep", reg.get("sleep_target"), "bed")
    moved = [bool(o.get("moved")) for o in recent if "moved" in o]
    if moved:
        out["moved_rate"] = sum(moved) / len(moved)
    out["learned"] = bool(out["wake"]["learned"] or out["sleep"]["learned"])
    return out


def eff_time(d, key, fallback):
    """The frame the office is actually using for a keystone — the learned value when it has
    earned the evidence, else the chart's stated target."""
    info = ((d or {}).get("learn") or {}).get(key)
    if info and info.get("learned"):
        return info.get("frame") or fallback
    return fallback


def read_chronicle():
    """The office's own memory, oldest-first."""
    try:
        out = []
        for ln in CHRONICLE.read_text().splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                out.append(json.loads(ln))
            except ValueError:
                continue
        out.sort(key=lambda e: e.get("date", ""))
        return out
    except OSError:
        return []


def chronicle_trends(entries, chart):
    """Metabolize that memory: where things are heading vs where they were."""
    t = {
        "days_on_record": len(entries),
        "since": entries[0]["date"] if entries else None,
        "lines": [],
        "habit_streak": 0,
    }
    if len(entries) >= 2:
        a, b = entries[-2], entries[-1]

        def delta(key, noun):
            x, y = a.get(key), b.get(key)
            if x is None or y is None or x == y:
                return
            arrow = "↑" if y > x else "↓"
            tone = "easing" if y < x else "climbing"
            t["lines"].append(f"{noun}: {x} → {y} {arrow} ({tone})")

        delta("open_loops", "Open clinical loops")
        delta("surveillance_due", "Monitoring due")
        delta("overdue_loops", "Overdue items")
    # habit streak — trailing days where the day actually had a shape
    streak = 0
    for e in reversed(entries):
        if (e.get("regimen_today_blocks") or 0) > 0:
            streak += 1
        else:
            break
    t["habit_streak"] = streak
    # nocturia trend — a real signal, from the chart's own nightly log
    noct = (chart.get("logs", {}) or {}).get("nocturia", []) or []
    vals = [n.get("wakes") for n in noct if isinstance(n.get("wakes"), int)]
    if len(vals) >= 4:
        half = len(vals) // 2
        early, late = _median(vals[:half]), _median(vals[half:])
        if early is not None and late is not None and early != late:
            dirn = "down" if late < early else "up"
            t["lines"].append(
                f"Night-time wake-ups trending **{dirn}** ({early:g}→{late:g} median) — the fluid cutoff is the lever."
            )
    return t


# ── SURVEILLANCE department — derive what monitoring is due ──────────────────────────────────
def surveillance(chart, meds_active):
    """For each active drug that obligates monitoring, compute which windows are due and
    whether a covering result is on file. Returns a list of monitoring tracks."""
    ledger = _ledger(chart)
    tracks = []
    for m in meds_active:
        name = (m.get("name") or "").strip().lower()
        if name not in ANTIPSYCHOTICS:
            continue
        start, approx = _parse_start(m.get("started"))
        track = {
            "drug": m.get("brand") or m.get("name"),
            "start": start.isoformat() if start else None,
            "approx": approx,
            "weeks_in": (None if not start else max(0, (date.today() - start).days // 7)),
            "source": METABOLIC_SOURCE,
            "windows": [],
            "due_count": 0,
            "overdue_count": 0,
        }
        # results that plausibly cover a metabolic panel, by date
        result_dates = []
        for r in ledger:
            d = _days_since(r.get("date", ""))
            if d is not None:
                result_dates.append(date.fromisoformat(r["date"][:10]))
        for win in METABOLIC_SCHEDULE:
            if not start:
                track["windows"].append({**win, "status": "unknown", "detail": "start date not recorded"})
                continue
            due_on = start + timedelta(weeks=win["week"])
            covered = any(rd >= due_on for rd in result_dates)
            if covered:
                status, detail = "done", "result on file"
            elif date.today() < due_on:
                status = "upcoming"
                detail = f"due {due_on.isoformat()} (in {(due_on - date.today()).days}d)"
            else:
                overdue = (date.today() - due_on).days
                status = "overdue" if overdue > OVERDUE_DAYS else "due"
                detail = f"due {due_on.isoformat()}" + (f" — {overdue}d ago, not on file" if overdue > 0 else "")
                track["due_count"] += 1
                if status == "overdue":
                    track["overdue_count"] += 1
            track["windows"].append(
                {**win, "status": status, "detail": detail, "due_on": due_on.isoformat() if start else None}
            )
        tracks.append(track)
    return tracks


# ── COORDINATION department — results ledger recall ─────────────────────────────────────────
def open_results(chart):
    """Items ordered but not yet resulted — nothing the office is owed should vanish."""
    return [r for r in _ledger(chart) if r.get("status") == "ordered"]


# ── derived view (all departments feed this) ─────────────────────────────────────────────────
def derive(chart):
    loops = chart.get("open_loops", []) or []
    open_loops = [lp for lp in loops if lp.get("status") == "open"]
    high = [lp for lp in open_loops if lp.get("priority") == "high"]
    overdue = [lp for lp in open_loops if (_days_since(lp.get("opened", "")) or 0) >= OVERDUE_DAYS]
    atoms = [a for a in (chart.get("human_atoms", []) or []) if a.get("status") == "open"]
    appts = chart.get("appointments", []) or []
    next_days = min([d for d in (_next_appt_days(a) for a in appts) if d is not None], default=None)
    meds_active = [m for m in (chart.get("medications", []) or []) if m.get("status") == "active"]
    tracks = surveillance(chart, meds_active)
    surv_due = sum(t["due_count"] for t in tracks)
    surv_overdue = sum(t["overdue_count"] for t in tracks)
    # the living layer — learn the real rhythm, metabolize the office's own memory
    learn = learn_rhythm(chart, load_observations())
    trends = chronicle_trends(read_chronicle(), chart)
    return dict(
        open_loops=open_loops,
        high=high,
        overdue=overdue,
        atoms=atoms,
        appts=appts,
        next_days=next_days,
        meds_active=meds_active,
        tracks=tracks,
        surv_due=surv_due,
        surv_overdue=surv_overdue,
        open_results=open_results(chart),
        results_on_file=len(_ledger(chart)),
        learn=learn,
        trends=trends,
    )


# ── renderers (PRIVATE dir only — these carry PII) ──────────────────────────────────────────
def _stamp_line():
    return f"_Generated by the Executive Health Office · {datetime.now().isoformat(timespec='seconds')}_\n"


def _bottom_line(d):
    """The chief-of-staff one-paragraph synthesis."""
    bits = []
    if d["open_loops"]:
        bits.append(f"**{len(d['open_loops'])} clinical loop(s)** open ({len(d['high'])} high)")
    if d["surv_due"]:
        od = f", {d['surv_overdue']} overdue" if d["surv_overdue"] else ""
        bits.append(f"**{d['surv_due']} monitoring item(s) due and not on file**{od}")
    if d["next_days"] is not None:
        when = "today" if d["next_days"] == 0 else f"in {d['next_days']}d"
        bits.append(f"next appointment **{when}**")
    if d["atoms"]:
        bits.append(f"**{len(d['atoms'])} thing(s)** waiting on you")
    if not bits:
        return "Nothing open — the office is quiet."
    return "; ".join(bits) + "."


def render_briefing(chart, d):
    """The flagship — the Executive Health Briefing. The office's front door."""
    L = ["# Executive Health Briefing\n", _stamp_line(), ""]
    L.append(
        "> The standing report from your health office. Behind it: the clinical spine — the "
        "**board** (`health-digest.md`), the **recall** (`surveillance.md`), your **visit kit** "
        "(`prep/`), your **inbox** (`human-atoms.md`) — and the habilitation wing that runs your "
        "day: **`regimen.md`**, **`kitchen/`**, **`movement.md`**, **`sleep.md`** — plus the office "
        "watching itself: **`office-log.md`** (what it's learned about you, and changed).\n"
    )

    safety = chart.get("safety", {}) or {}
    if safety.get("urgent_care_if"):
        L.append("## ⚠️ Seek care now if")
        for s in safety["urgent_care_if"]:
            L.append(f"- {s}")
        if safety.get("standing_rule"):
            L.append(f"\n> {safety['standing_rule']}")
        L.append("")

    L.append("## The bottom line")
    L.append(_bottom_line(d))
    L.append("")

    # Coordination — what's on the calendar
    if d["appts"]:
        L.append("## On the calendar")
        for a in d["appts"]:
            nd = _next_appt_days(a)
            innd = "" if nd is None else (" — **today**" if nd == 0 else f" — in {nd}d")
            synced = " · ✅ on calendar" if a.get("calendar_synced") else " · ⚠️ not yet on calendar"
            L.append(
                f"- **{a.get('title', '?')}** — {a.get('day_of_week', 'day TBD')} {a.get('time', '')}{innd}{synced}"
            )
        L.append("")

    # Habilitation wing — the office runs the day toward fitness
    prod = []
    if chart.get("regimen"):
        prod.append(("regimen.md", "a frame for the day — bends to you; the office holds it so you don't have to"))
    if chart.get("nutrition"):
        prod.append(("kitchen/meal-plan.md", "this week's meals + a one-pass grocery list"))
    if chart.get("fitness"):
        prod.append(("movement.md", "this week's movement, gently ramped"))
    if chart.get("regimen") or chart.get("sleep"):
        prod.append(("sleep.md", "tonight's plan — the keystone habit"))
    if prod:
        L.append("## Getting fit — the office runs your day")
        L.append("So you don't have to think about it or remember it:")
        for f, desc in prod:
            L.append(f"- **{f}** — {desc}")
        L.append("")

    # The living office — what it has learned and is watching (autopoiesis, made legible)
    learn = d.get("learn") or {}
    trends = d.get("trends") or {}
    living = list(learn.get("changes", []))
    if trends.get("habit_streak", 0) >= 3:
        living.append(f"You've had a shaped day **{trends['habit_streak']} days running** — that's the habit forming.")
    living.extend(trends.get("lines", []))
    if living:
        L.append("## What the office is learning")
        for x in living[:4]:
            L.append(f"- {x}")
        L.append("\n_Full memory + what it's watching: `office-log.md`._")
        L.append("")
    elif trends.get("days_on_record", 0) <= 1:
        L.append("## What the office is learning")
        L.append(
            "- Just getting started. As the days accumulate, the office learns your real rhythm "
            "and reshapes the day's frame to fit you — tell it when you wake, sleep, or move "
            "(or log a line in `observations.jsonl`)."
        )
        L.append("\n_See `office-log.md`._")
        L.append("")

    # Surveillance — what's due
    if d["tracks"]:
        L.append("## What's due — preventive monitoring")
        for t in d["tracks"]:
            wk = "" if t["weeks_in"] is None else f" (~{t['weeks_in']} weeks in)"
            L.append(f"**{t['drug']}**{wk} — metabolic monitoring:")
            for w in t["windows"]:
                icon = {"done": "✅", "due": "🔴", "overdue": "⏰", "upcoming": "🗓️", "unknown": "❔"}.get(
                    w["status"], "•"
                )
                if w["status"] in ("due", "overdue", "unknown"):
                    L.append(f"- {icon} **{w['label']}** — {', '.join(w['items'])} · _{w['detail']}_")
                else:
                    L.append(f"- {icon} {w['label']} — _{w['detail']}_")
            L.append(f"\n_Why this matters: {t['source']}_")
            L.append("")

    # Records / the plan — open loops
    L.append("## The plan — clinical loops the office is chasing")
    if d["open_loops"]:
        for lp in d["open_loops"]:
            mark = "\U0001f534" if lp.get("priority") == "high" else "•"
            L.append(f"- {mark} **{lp.get('title', '?')}** — _{lp.get('next_action', '')}_")
    else:
        L.append("- _(none open)_")
    L.append("")

    # Advocacy pointer
    L.append("## Your visit kit")
    L.append("When you next see *any* clinician, the office has these ready in `prep/`:")
    L.append("- **visit-script.md** — what to say and ask for, in order.")
    L.append("- **prescriber-note.md** — a message ready to read or send to the prescriber.")
    for a in d["appts"]:
        L.append(f"- **{a.get('id', 'appt')}-prep.md** — prep for your {a.get('title', 'appointment')}.")
    L.append("")

    # Pharmacy
    L.append("## Medications")
    for m in d["meds_active"]:
        dose = m.get("dose") or "_dose TBD_"
        mon = " · ⚕️ requires metabolic monitoring" if (m.get("name", "").lower() in ANTIPSYCHOTICS) else ""
        L.append(
            f"- **{m.get('brand') or m.get('name', '?')}** ({m.get('name', '')}) — {dose} · {m.get('purpose', '')} · started {m.get('started', '?')}{mon}"
        )
    L.append("")

    # Inbox
    if d["atoms"]:
        L.append("## Waiting on you (only you can do these)")
        for a in d["atoms"]:
            L.append(f"- {a.get('ask', '?')}")
        L.append("")

    return "\n".join(L) + "\n"


def render_digest(chart, d):
    L = ["# Health — where things stand (the board)\n", _stamp_line(), ""]
    safety = chart.get("safety", {}) or {}
    if safety.get("urgent_care_if"):
        L.append("## ⚠️ Seek care now if")
        for s in safety["urgent_care_if"]:
            L.append(f"- {s}")
        if safety.get("standing_rule"):
            L.append(f"\n> {safety['standing_rule']}")
        L.append("")

    if d["overdue"]:
        L.append("## ⏰ Overdue — has been open too long")
        for lp in d["overdue"]:
            L.append(
                f"- **{lp.get('title', '?')}** (open {_days_since(lp.get('opened', ''))}d) — {lp.get('next_action', '')}"
            )
        L.append("")

    L.append("## The plan — open loops the office is chasing")
    if d["open_loops"]:
        for lp in d["open_loops"]:
            pr = lp.get("priority", "")
            mark = "\U0001f534" if pr == "high" else "•"
            L.append(f"- {mark} **{lp.get('title', '?')}**")
            if lp.get("why"):
                L.append(f"  - _why:_ {lp['why']}")
            L.append(f"  - _next:_ {lp.get('next_action', '')}")
            L.append(f"  - _owner:_ {lp.get('owner', '')}")
    else:
        L.append("- _(none open)_")
    L.append("")

    L.append("## Medications")
    for m in d["meds_active"]:
        dose = m.get("dose") or "dose TBD"
        L.append(
            f"- **{m.get('brand') or m.get('name', '?')}** ({m.get('name', '')}) — {dose} · {m.get('purpose', '')} · started {m.get('started', '?')}"
        )
    L.append("")

    L.append("## Appointments")
    for a in d["appts"]:
        when = a.get("day_of_week") or "_day TBD_"
        nd = _next_appt_days(a)
        innd = "" if nd is None else (" — today" if nd == 0 else f" — in {nd}d")
        synced = " · ✅ on calendar" if a.get("calendar_synced") else " · not yet on calendar"
        L.append(f"- **{a.get('title', '?')}** — {when} {a.get('time', '')}{innd}{synced}")
    L.append("")

    L.append("## Trackers")
    noct = (chart.get("logs", {}) or {}).get("nocturia", []) or []
    if noct:
        recent = noct[-7:]
        L.append(
            "- Nocturia (wakes/night): " + ", ".join(f"{n.get('date', '?')[5:]}={n.get('wakes', '?')}" for n in recent)
        )
    else:
        L.append('- Nocturia: _no nights logged yet — say "I woke up N times last night"_')
    L.append("")
    return "\n".join(L) + "\n"


def render_surveillance(chart, d):
    L = [
        "# Surveillance — what preventive care is due\n",
        _stamp_line(),
        "Protocol-driven recalls the office tracks so they don't get dropped. "
        "Nothing here is a diagnosis — it's what the standard of care schedules, and "
        "what to ask a clinician to order.\n",
    ]
    if not d["tracks"]:
        L.append("- _(no monitoring obligations derived from the current medications)_")
    for t in d["tracks"]:
        wk = "" if t["weeks_in"] is None else f", about **{t['weeks_in']} weeks in**"
        approx = " _(start date approximate — confirm for exact timing)_" if t["approx"] else ""
        L.append(f"## {t['drug']} — metabolic monitoring{wk}{approx}")
        if t["due_count"]:
            L.append(
                f"**{t['due_count']} item(s) due and not on file"
                + (f", {t['overdue_count']} overdue" if t["overdue_count"] else "")
                + ".**\n"
            )
        for w in t["windows"]:
            icon = {"done": "✅", "due": "🔴", "overdue": "⏰", "upcoming": "🗓️", "unknown": "❔"}.get(w["status"], "•")
            L.append(f"- {icon} **{w['label']}** — {', '.join(w['items'])}")
            L.append(f"  - _{w['detail']}_")
        L.append(f"\n_Source: {t['source']}_\n")
    if d["open_results"]:
        L.append("## Ordered, awaiting result")
        for r in d["open_results"]:
            L.append(f"- **{r.get('what', '?')}** — ordered {r.get('date', '?')}")
        L.append("")
    return "\n".join(L) + "\n"


def render_atoms(chart, d):
    L = [
        "# What only you can do\n",
        _stamp_line(),
        "The irreducible human acts. Surfaced once; the office stops nagging after.\n",
    ]
    if not d["atoms"]:
        L.append("- _(nothing waiting on you right now)_")
    for a in d["atoms"]:
        L.append(f"- **{a.get('ask', '?')}**")
        if a.get("why"):
            L.append(f"  - _why:_ {a['why']}")
    return "\n".join(L) + "\n"


def render_prescriber_note(chart, d):
    # FIREWALL: everything specific (drug, dose, symptom, ask) comes from the Chart (off-repo).
    # This code names no medication and no symptom — only generic connective scaffolding.
    meds = d["meds_active"]
    med = next((m for m in meds if m.get("flag_for_prescriber")), None) or (meds[0] if meds else {})
    name = med.get("brand") or med.get("name") or "a new medication"
    started = med.get("started", "recently")
    dose = med.get("dose")
    dose_str = f" ({dose})" if dose else ""
    purpose_str = f" for {med['purpose']}" if med.get("purpose") else ""
    concerns = [lp.get("title", "").strip() for lp in (d["high"] or d["open_loops"]) if lp.get("title")]
    asks = [lp.get("next_action", "").strip() for lp in (d["high"] or d["open_loops"]) if lp.get("next_action")]
    log = (chart.get("logs", {}) or {}).get("nocturia", []) or []
    log_str = ""
    if log:
        log_str = (
            "\n\nRecent nights logged: "
            + ", ".join(f"{n.get('date', '?')}: {n.get('wakes', '?')}" for n in log[-7:])
            + "."
        )
    opening = f"Hi — I started taking {name}{dose_str}{purpose_str}, around {started}."
    if concerns:
        opening += " Since then, here's what I want to raise: " + "; ".join(concerns) + "."
    ask_line = (" Specifically, I'd like to: " + "; ".join(asks) + ".") if asks else ""
    return (
        "# Note for the prescriber\n\n" + _stamp_line() + "\n"
        "_Short message — ready to send or read aloud._\n\n"
        "---\n\n"
        + opening
        + ask_line
        + " I'm not changing anything on my own — should the medication or dose be reviewed?"
        + log_str
        + "\n\n---\n"
    )


def render_visit_script(chart, d):
    L = ["# Visit script — bring this to your next medical contact\n", _stamp_line(), ""]
    safety = chart.get("safety", {}) or {}
    L.append("## Say this")
    # FIREWALL: name + purpose come from the Chart; the specific concerns are the open loops below.
    meds = d["meds_active"]
    med = next((m for m in meds if m.get("flag_for_prescriber")), None) or (meds[0] if meds else {})
    if med:
        name = med.get("brand") or med.get("name") or "a medication"
        purpose = f" for {med['purpose']}" if med.get("purpose") else ""
        L.append(
            f"- I started **{name}**{purpose} around {med.get('started', 'recently')}, "
            "and I've noticed some things since then that I want to raise (below)."
        )
    else:
        L.append("- Here's what I'd like to raise today (below).")
    L.append("")
    L.append("## Ask for")
    for lp in d["high"] or d["open_loops"]:
        L.append(f"- {lp.get('next_action', lp.get('title', ''))}")
    # surveillance items that are due become explicit asks
    due_items = []
    for t in d["tracks"]:
        for w in t["windows"]:
            if w["status"] in ("due", "overdue"):
                due_items.extend(w["items"])
    due_items = list(dict.fromkeys(i for i in due_items if "history" not in i))
    if due_items:
        L.append(f"- The monitoring that's due on my medication: {', '.join(due_items)}.")
    L.append("")
    if safety.get("urgent_care_if"):
        L.append("## When to go in urgently (don't wait)")
        for s in safety["urgent_care_if"]:
            L.append(f"- {s}")
        L.append("")
    if safety.get("standing_rule"):
        L.append(f"> {safety['standing_rule']}\n")
    return "\n".join(L) + "\n"


def render_appt_prep(chart, d, appt):
    """ADVOCACY — a short, gentle prep sheet for a specific appointment."""
    title = appt.get("title", "appointment")
    nd = _next_appt_days(appt)
    when = "today" if nd == 0 else (f"in {nd} days" if nd is not None else "soon")
    L = [f"# Prep — your {title} ({when})\n", _stamp_line(), ""]
    L.append(f"You have **{title}** {when}" + (f" at {appt['time']}" if appt.get("time") else "") + ".")
    L.append("")
    L.append("## If it's useful to raise")
    L.append("_Only if you want to — these are yours to bring up or not._")
    for lp in d["high"] or d["open_loops"]:
        L.append(f"- {lp.get('title', '')}")
    if "therap" in title.lower():
        L.append(
            "- Anything affecting your sleep, mood, or energy is worth naming here — your "
            "therapist can help you think it through, and coordinate with your prescriber if "
            "a medication is involved."
        )
    L.append("")
    L.append("_The office isn't in the room with you. This is just so you don't walk in cold._")
    return "\n".join(L) + "\n"


# ══ THE HABILITATION WING — the proactive day (carry the load; he shouldn't think or remember) ══


# ── REGIMEN department — the shape of the day ────────────────────────────────────────────────
def regimen_plan(chart, d):
    """Today's blocks, each tagged with a 'kind' so the day reads as scaffolding, not a timetable:

    - 'fixed'    — a real appointment; immovable, because it's actually on the calendar.
    - 'keystone' — one of the few points where consistency actually buys something (wake,
                   bed, the evening fluid cutoff). Worth holding steady; the evidence backs it.
    - 'flex'     — suggested scaffolding (meals, movement, wind-down). Bends to the day.
    """
    reg = chart.get("regimen", {}) or {}
    meals = reg.get("meals", {}) or {}
    blocks = []

    def add(t, label, kind, note=""):
        if t:
            blocks.append({"time": str(t), "label": label, "kind": kind, "note": note})

    add(
        eff_time(d, "wake", reg.get("wake")),
        "Wake",
        "keystone",
        "the one to keep steady — consistency is the biggest sleep lever",
    )
    add(meals.get("breakfast"), "Breakfast", "flex", "protein + fiber")
    for a in d.get("appts", []):
        if _next_appt_days(a) == 0 and a.get("time"):
            add(a.get("time"), a.get("title", "Appointment"), "fixed", "on the calendar")
    add(meals.get("lunch"), "Lunch", "flex", "")
    add(reg.get("movement_slot"), "Movement", "flex", "today's session — see movement.md")
    add(meals.get("dinner"), "Dinner", "flex", "")
    add(
        reg.get("evening_fluid_cutoff"),
        "Last fluids",
        "keystone",
        "the one clinical win — cuts the night-time wake-ups",
    )
    add(reg.get("wind_down_start"), "Wind-down", "flex", "dim lights, screens off")
    add(
        eff_time(d, "sleep", reg.get("sleep_target")),
        "Bed",
        "keystone",
        "keep steady with wake — the pair that sets your rhythm",
    )
    blocks.sort(key=lambda b: b["time"])
    return blocks


def render_regimen(chart, d):
    reg = chart.get("regimen", {}) or {}
    L = [
        "# Your day — the regimen\n",
        _stamp_line(),
        "> Scaffolding, not a timetable. This bends to you — it's here to make a good day the easy "
        "default, not to box you in. Only the few points marked ⚓ are worth keeping steady; "
        "everything marked ~ slides to fit the day. A schedule that's *right* is one that fits you — "
        "so reshape any of it, and tell the office to make the change stick.\n",
    ]
    blocks = regimen_plan(chart, d)
    fixed = [b for b in blocks if b["kind"] == "fixed"]
    L.append(f"## Today — {date.today().strftime('%A')}")
    if not blocks:
        L.append("- _(no regimen set yet)_")
    elif fixed:
        L.append("**What's actually fixed today** — the real, on-the-calendar anchors:")
        for b in fixed:
            note = f" — _{b['note']}_" if b.get("note") else ""
            L.append(f"- **{_fmt_time(b['time'])}** · {b['label']}{note}")
        L.append("\n**A frame to lean on around them** — all of it moveable:")
    else:
        L.append("_Nothing's locked today. Here's a frame to lean on — all of it moveable:_")
    for b in blocks:
        if b["kind"] == "fixed":
            continue
        mark = "⚓" if b["kind"] == "keystone" else "~"
        note = f" — _{b['note']}_" if b.get("note") else ""
        L.append(f"- {mark} **{_fmt_time(b['time'])}** · {b['label']}{note}")
    L.append("")
    wake_f = eff_time(d, "wake", reg.get("wake"))
    bed_f = eff_time(d, "sleep", reg.get("sleep_target"))
    L.append("## The few anchors worth keeping (⚓)")
    L.append(
        f"- Wake **{_fmt_time(wake_f)}** and bed **{_fmt_time(bed_f)}** — "
        "holding *just these two* steady is the single biggest sleep lever. Everything else can move around them."
    )
    L.append(
        f"- Last fluids by **{_fmt_time(reg.get('evening_fluid_cutoff'))}** — the one change with a direct "
        "payoff: fewer night-time wake-ups."
    )
    if ((d or {}).get("learn") or {}).get("learned"):
        L.append(
            "\n_These reflect what you **actually do** — your real rhythm over the last few weeks, "
            "not a target handed to you. The office fit the frame to you; see `office-log.md`._"
        )
    else:
        L.append(
            "\n_These are still the starting frame. Tell the office when you actually wake or turn in "
            "(or log a line in `observations.jsonl`) and it reshapes the anchors to your real rhythm — "
            "see `office-log.md`._"
        )
    L.append(
        "\n_Nothing here is a rule except what you make one. The office holds the frame so you don't have to — "
        "you decide what the day actually looks like._"
    )
    L.append("\n_Reference: docs/health-office/reference/sleep-hygiene.md_")
    return "\n".join(L) + "\n"


# ── KITCHEN department — the weekly menu + grocery list ──────────────────────────────────────
def nutrition_menu(chart):
    """A deterministic week of simple meals from the starter library, filtered around the
    principal's dislikes/allergies. Returns (plan, grocery_counts)."""
    nut = chart.get("nutrition", {}) or {}
    avoid = [str(x).lower() for x in (nut.get("dislikes", []) or []) + (nut.get("allergies", []) or [])]

    def ok(item):
        hay = (item["name"] + " " + " ".join(item["buy"])).lower()
        return not any(a and a in hay for a in avoid)

    pick = {slot: ([i for i in items if ok(i)] or items) for slot, items in MENU.items()}
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    plan, grocery = [], {}
    for n, day in enumerate(days):
        row = {"day": day}
        for slot in ("breakfast", "lunch", "dinner"):
            opts = pick[slot]
            item = opts[n % len(opts)]
            row[slot] = item["name"]
            for g in item["buy"]:
                grocery[g] = grocery.get(g, 0) + 1
        plan.append(row)
    return plan, grocery


def render_kitchen(chart, plan):
    nut = chart.get("nutrition", {}) or {}
    L = [
        "# This week's kitchen — meals, already decided\n",
        _stamp_line(),
        "> So you're not thinking about what to eat or cook. A simple rotation, emphasis on "
        f"**{nut.get('pattern', 'balanced, whole foods')}**. This is a starting menu — tell the "
        "office your likes, dislikes, and allergies and it rebuilds around them.\n",
    ]
    if nut.get("dislikes") or nut.get("allergies"):
        L.append(
            "_Already steering around: "
            + ", ".join((nut.get("dislikes", []) or []) + (nut.get("allergies", []) or []))
            + "._\n"
        )
    L.append("| Day | Breakfast | Lunch | Dinner |")
    L.append("|---|---|---|---|")
    for r in plan:
        L.append(f"| {r['day']} | {r['breakfast']} | {r['lunch']} | {r['dinner']} |")
    L.append(
        f"\n_Goal: {nut.get('goal', 'balanced eating')}. The grocery list for all of this is in "
        f"`kitchen/grocery-list.md`._"
    )
    L.append(f"\n_Why these foods: {MENU_SOURCE}_")
    return "\n".join(L) + "\n"


def render_grocery(grocery):
    L = [
        "# Grocery list — one pass for the week\n",
        _stamp_line(),
        "> Everything this week's menu needs, consolidated into a single shop. Pantry staples "
        "(oil, salt, spices) assumed on hand.\n",
    ]
    if not grocery:
        L.append("- _(no menu generated)_")
    for item in sorted(grocery):
        n = grocery[item]
        L.append(f"- [ ] {item}" + (f" ×{n}" if n > 1 else ""))
    return "\n".join(L) + "\n"


# ── MOVEMENT department — the weekly movement plan ───────────────────────────────────────────
def movement_plan(chart):
    """A gentle starting week, calibrated to 'starting out', honoring stated preferences."""
    fit = chart.get("fitness", {}) or {}
    likes = [str(x).lower() for x in (fit.get("likes", []) or [])]
    yoga = (not likes) or ("yoga" in likes)
    sessions = [
        {"day": "Mon", "what": "Walk 15 min", "note": "after a meal if you can — blunts the blood-sugar rise"},
        {"day": "Tue", "what": "Gentle yoga 20 min", "note": "mobility, and winds you down for sleep"},
        {"day": "Wed", "what": "Walk 15 min", "note": "easy pace"},
        {"day": "Thu", "what": "Light strength 15 min", "note": "sit-to-stands, wall push-ups, rows"},
        {"day": "Fri", "what": "Walk 15 min", "note": ""},
        {"day": "Sat", "what": "Gentle yoga 20 min, or a longer walk", "note": "your pick"},
        {"day": "Sun", "what": "Rest, or an easy stroll", "note": "recovery counts"},
    ]
    if not yoga:
        for s in sessions:
            s["what"] = s["what"].replace("Gentle yoga 20 min", "Walk 20 min")
    return sessions


def render_movement(chart):
    reg = chart.get("regimen", {}) or {}
    slot = reg.get("movement_slot")
    L = [
        "# Movement — this week, gently\n",
        _stamp_line(),
        "> So you don't have to remember to move — small and sustainable beats heroic and "
        "abandoned. "
        + (f"Your daily slot is **{_fmt_time(slot)}**. " if slot else "")
        + "Clear a new program with a clinician given your weight.\n",
    ]
    L.append("| Day | Session | Why |")
    L.append("|---|---|---|")
    for s in movement_plan(chart):
        L.append(f"| {s['day']} | {s['what']} | {s.get('note', '')} |")
    L.append("")
    L.append(
        "> **Want these on your calendar?** Say the word and the office will add the week's "
        "sessions to your Google Calendar — it won't fill your calendar uninvited."
    )
    L.append("\n_Reference: docs/health-office/reference/movement-when-starting-out.md_")
    return "\n".join(L) + "\n"


# ── SLEEP department — the keystone habit ────────────────────────────────────────────────────
def render_sleep(chart, d):
    reg = chart.get("regimen", {}) or {}
    L = [
        "# Sleep — the keystone\n",
        _stamp_line(),
        "> Fix sleep and the rest gets easier: appetite, blood sugar, mood, the energy to move. "
        "This is the office's nightly protocol — a sleep *disorder* (insomnia, apnea) is a "
        "clinician's to treat.\n",
    ]
    L.append("## Tonight's plan")
    L.append(
        f"- Last fluids by **{_fmt_time(reg.get('evening_fluid_cutoff'))}** — the most direct "
        "lever on the night-time wake-ups."
    )
    L.append(
        f"- Wind-down from **{_fmt_time(reg.get('wind_down_start'))}**: dim lights, screens off, nothing stimulating."
    )
    L.append(
        f"- Lights out **{_fmt_time(eff_time(d, 'sleep', reg.get('sleep_target')))}**, up at "
        f"**{_fmt_time(eff_time(d, 'wake', reg.get('wake')))}** — the same times every day, weekends included."
    )
    L.append("")
    L.append("## The trend")
    noct = (chart.get("logs", {}) or {}).get("nocturia", []) or []
    if noct:
        recent = noct[-7:]
        L.append("- Wakes to urinate: " + ", ".join(f"{n.get('date', '?')[5:]}={n.get('wakes', '?')}" for n in recent))
    else:
        L.append(
            '- _No nights logged yet — tell the office "I woke up N times last night" and it\'ll track the trend._'
        )
    L.append("")
    L.append(
        "> If the wake-ups persist despite the fluid cutoff and a steady schedule, that routes "
        "back to the clinical workup — high blood sugar and sleep apnea both cause this and are "
        "both checkable."
    )
    L.append("\n_Reference: docs/health-office/reference/sleep-hygiene.md_")
    return "\n".join(L) + "\n"


# ── THE OFFICE, LEARNING — autopoiesis made legible (a product you can read) ─────────────────
def render_office_log(chart, d):
    learn = d.get("learn") or {}
    trends = d.get("trends") or {}
    L = [
        "# The office, learning\n",
        _stamp_line(),
        "> An institution is alive only if it reaches into its past, lives in the present, and "
        "reshapes its future. This is the office watching itself: what it has learned about you, "
        "what it changed, and what it's keeping an eye on — so being well costs you a little less "
        "thought each week, not the same amount forever.\n",
    ]

    L.append("## What I've learned about your rhythm")
    if learn.get("learned"):
        for key, label in (("wake", "Wake"), ("sleep", "Bed")):
            info = learn.get(key) or {}
            if info.get("learned"):
                L.append(
                    f"- **{label}** — you actually land near **{_fmt_time(info['observed'])}** "
                    f"(over {info['n']} days). Stated target: {_fmt_time(info['target'])}. "
                    f"Working frame: **{_fmt_time(info['frame'])}**."
                )
        if learn.get("moved_rate") is not None:
            L.append(f"- **Movement** — you moved on about **{round(learn['moved_rate'] * 100)}%** of logged days.")
    else:
        L.append(
            f"- Still learning. I have **{learn.get('n', 0)} day(s)** of your real wake/sleep on "
            f"record and reshape the anchors once I have {MIN_OBSERVATIONS}. Until then I hold "
            "the starting frame."
        )
        L.append(
            "- **Teach me in one line** — append to `observations.jsonl`, e.g. "
            '`{"date":"2026-06-24","wake":"07:25","sleep":"23:10","moved":true}` — '
            'or just tell me "I woke at 7:30" and I\'ll record it.'
        )

    L.append("\n## What I changed this cycle")
    if learn.get("changes"):
        for c in learn["changes"]:
            L.append(f"- {c}")
    else:
        L.append("- Nothing yet — I won't move your anchors until your real pattern earns it.")

    L.append("\n## What I'm watching")
    watching = list(trends.get("lines", []))
    if d.get("surv_due"):
        watching.append(f"{d['surv_due']} monitoring item(s) due and not on file.")
    if d.get("overdue"):
        watching.append(f"{len(d['overdue'])} clinical loop(s) open past {OVERDUE_DAYS} days.")
    if trends.get("habit_streak", 0) >= 3:
        watching.append(f"A {trends['habit_streak']}-day streak of shaped days — protect it.")
    if watching:
        for w in watching:
            L.append(f"- {w}")
    else:
        L.append("- Quiet. Nothing trending the wrong way.")

    L.append("\n## My memory")
    if trends.get("days_on_record"):
        L.append(
            f"- **{trends['days_on_record']} day(s)** on record"
            + (f", since {trends['since']}" if trends.get("since") else "")
            + "."
        )
    else:
        L.append(
            "- This is the first entry. From here the office keeps a memory of your health "
            "over time, not just today's snapshot."
        )
    return "\n".join(L) + "\n"


# ── BRIEFING department — append-only chronicle (institutional memory) ───────────────────────
def append_chronicle(d):
    """One entry per day in the private dir — the office's memory of the health over time."""
    today = date.today().isoformat()
    entry = {
        "date": today,
        "open_loops": len(d["open_loops"]),
        "high": len(d["high"]),
        "overdue_loops": len(d["overdue"]),
        "surveillance_due": d["surv_due"],
        "surveillance_overdue": d["surv_overdue"],
        "results_on_file": d["results_on_file"],
        "human_atoms_open": len(d["atoms"]),
        "next_appt_in_days": d["next_days"],
        "meds_active": len(d["meds_active"]),
        "regimen_today_blocks": d.get("regimen_today_blocks", 0),
        "menu_days": d.get("menu_days", 0),
        "movement_sessions": d.get("movement_sessions", 0),
        "learned_rhythm": bool((d.get("learn") or {}).get("learned")),
        "observation_days": (d.get("learn") or {}).get("n", 0),
    }
    try:
        lines = []
        if CHRONICLE.exists():
            lines = [
                ln for ln in CHRONICLE.read_text().splitlines() if ln.strip() and json.loads(ln).get("date") != today
            ]
        lines.append(json.dumps(entry))
        CHRONICLE.write_text("\n".join(lines) + "\n")
    except (OSError, ValueError):
        pass  # chronicle is memory, not load-bearing — never block on it


# ── PII-free liveness stamp (repo logs/) ────────────────────────────────────────────────────
def _health_public_census():
    """Counts-only census of the public health organ surface; no private chart data."""
    public_files = sorted(path for path in HEALTH_HOME.glob("*") if path.is_file())
    case_root = HEALTH_HOME / "cases"
    case_dirs = sorted(path for path in case_root.glob("*") if path.is_dir()) if case_root.exists() else []
    case_files = sorted(path for path in case_root.glob("*/*") if path.is_file()) if case_root.exists() else []
    return {
        "public_artifacts": len(public_files),
        "case_dirs": len(case_dirs),
        "case_files": len(case_files),
        "has_safety_sentinel": (HEALTH_HOME / "safety-sentinel.sh").exists(),
        "has_workflow_runner": (HEALTH_HOME / "workflow-runner.sh").exists(),
    }


def write_stamp(present, d=None):
    LOGS.mkdir(parents=True, exist_ok=True)
    rec = {
        "ran_at": datetime.now().isoformat(timespec="seconds"),
        "chart_present": present,
        "public_census": _health_public_census(),
    }
    if d is not None:
        rec.update(
            {
                "open_loops": len(d["open_loops"]),
                "high_priority_loops": len(d["high"]),
                "overdue_loops": len(d["overdue"]),
                "surveillance_due": d["surv_due"],
                "surveillance_overdue": d["surv_overdue"],
                "results_on_file": d["results_on_file"],
                "human_atoms_open": len(d["atoms"]),
                "appointments": len(d["appts"]),
                "next_appt_in_days": d["next_days"],
                "meds_active": len(d["meds_active"]),
                "regimen_today_blocks": d.get("regimen_today_blocks", 0),
                "menu_days": d.get("menu_days", 0),
                "movement_sessions": d.get("movement_sessions", 0),
            }
        )
    (LOGS / "health-organ-state.json").write_text(json.dumps(rec, indent=2))
    # voice-stamp (ground-truth fire signal for organ-health), mtime is what matters
    try:
        vd = LOGS / ".voice"
        vd.mkdir(parents=True, exist_ok=True)
        (vd / "health").write_text(rec["ran_at"])
    except OSError:
        pass


def main():
    chart = load_chart()
    if chart is None:
        write_stamp(present=False)
        print("health-office: no chart yet (expected at $LIMEN_HEALTH_DIR/chart.json) — stamped, no-op")
        return 0

    d = derive(chart)
    try:
        PREP.mkdir(parents=True, exist_ok=True)
        # BRIEFING (front door) + RECORDS board + SURVEILLANCE recall + inbox
        (HEALTH_DIR / "briefing.md").write_text(render_briefing(chart, d))
        (HEALTH_DIR / "health-digest.md").write_text(render_digest(chart, d))
        (HEALTH_DIR / "surveillance.md").write_text(render_surveillance(chart, d))
        (HEALTH_DIR / "human-atoms.md").write_text(render_atoms(chart, d))
        # ADVOCACY visit kit
        (PREP / "prescriber-note.md").write_text(render_prescriber_note(chart, d))
        (PREP / "visit-script.md").write_text(render_visit_script(chart, d))
        for a in d["appts"]:
            (PREP / f"{a.get('id', 'appt')}-prep.md").write_text(render_appt_prep(chart, d, a))
        # HABILITATION wing — the proactive day (off-repo products)
        if chart.get("regimen"):
            (HEALTH_DIR / "regimen.md").write_text(render_regimen(chart, d))
            d["regimen_today_blocks"] = len(regimen_plan(chart, d))
        if chart.get("regimen") or chart.get("sleep"):
            (HEALTH_DIR / "sleep.md").write_text(render_sleep(chart, d))
        if chart.get("nutrition"):
            plan, grocery = nutrition_menu(chart)
            kitchen = HEALTH_DIR / "kitchen"
            kitchen.mkdir(parents=True, exist_ok=True)
            (kitchen / "meal-plan.md").write_text(render_kitchen(chart, plan))
            (kitchen / "grocery-list.md").write_text(render_grocery(grocery))
            d["menu_days"] = len(plan)
        if chart.get("fitness"):
            (HEALTH_DIR / "movement.md").write_text(render_movement(chart))
            d["movement_sessions"] = len(movement_plan(chart))
        # THE LIVING LAYER — the office's self-knowledge, written where he can read it
        (HEALTH_DIR / "office-log.md").write_text(render_office_log(chart, d))
        # BRIEFING memory
        append_chronicle(d)
    except OSError as e:
        # private dir unwritable — still stamp liveness so the rung doesn't read "down"
        write_stamp(present=True, d=d)
        print(f"health-office: chart read but private dir unwritable ({e.__class__.__name__}) — stamped")
        return 0

    write_stamp(present=True, d=d)
    # NON-PII one-liner only (counts, no medical content)
    nd = d["next_days"]
    appt = "next appt: day TBD" if nd is None else ("next appt: today" if nd == 0 else f"next appt: in {nd}d")
    habits = [
        name
        for name, key in (("day", "regimen_today_blocks"), ("meals", "menu_days"), ("movement", "movement_sessions"))
        if d.get(key)
    ]
    hb = (" · habits: " + "+".join(habits)) if habits else ""
    learn = d.get("learn") or {}
    learning = "adapting" if learn.get("learned") else f"seed ({learn.get('n', 0)} obs)"
    print(
        f"health-office: {len(d['open_loops'])} open loops "
        f"({len(d['high'])} high, {len(d['overdue'])} overdue) · "
        f"{d['surv_due']} monitoring due ({d['surv_overdue']} overdue) · "
        f"{len(d['atoms'])} inputs needed · {appt}{hb} · learning: {learning}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
