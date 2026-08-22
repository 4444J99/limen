#!/usr/bin/env python3
"""DIVRNAL — the three-phase daily organ that cuts itself.

Morning / midday / evening are three phases of ONE organ, reaching forward and backward
toward each other:

    morning  →  reads last evening's carry + the night's alerts; EMITS claims
    midday   →  re-probes each morning claim mid-flight; EMITS corrections
    evening  →  SCORES every claim held/missed/noop; EMITS carry + CUTS

The loop closes because a section that is never acted on is measurably noop, and the
evening phase has authority to remove it. The morning starts as a full dashboard; the
evening carves it down to what actually earns its place.

TWO DOCTRINES, both inherited from institutio/governance/ideal-forms.yaml:

  1. Freshness is DERIVED, never asserted. A source older than its declared
     max_age_seconds renders as STALE with its age — never as a number that looks
     current. Founded on the measured defect: organ-health.json 10d stale, omega.json
     9d, money-view.json 10d, fleet-status.json 27d, all presenting as authoritative.

  2. You cannot prune what you cannot score. A section with `metric: null` is
     cuttable: false, enforced by scripts/check-diurnal.py.

CLAIMS AND SECTION SCORES ARE THE SAME MEASUREMENT. A claim is "section X's metric will
decrease today" (or, where `acted_when: metric_changed`, "will move at all"). Evening
re-reads the metric: decreased = held, unchanged = noop, increased = missed. A noop claim
IS a noop section — which is what accrues toward a cut.

BUT A SECTION CAN FAIL TO EARN ITS PLACE WITHOUT EVER EMITTING A CLAIM, and that gap is
what let `cuttable: true` sit on 11 sections while only 3 could ever be cut. So every
cuttable section advances exactly ONE counter per engaged evening:

  noop_streak     it was claimed and did not move        → the evening may CUT it
  blind_streak    its source was stale, so no claim      → PROPOSE: repair or retire
  dormant_streak  fresh, but its metric sat at the floor → PROPOSE: confirm or retire

Only the first auto-cuts. The other two describe conditions the organ can observe but not
adjudicate — a dead producer and a healthy zero look identical from here — so they become
proposals that need a PR.

Registry:  institutio/governance/diurnal.yaml
Predicate: scripts/check-diurnal.py
Emissions: docs/diurnal/YYYY-MM-DD.md (marker-delimited; human text outside survives)
State:     logs/diurnal/{state,section-scores,proposals}.json, ledger.jsonl, cuts.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import yaml
except ImportError:  # fail open — advisory sensor, never breaks the beat
    yaml = None

try:
    import _notify
except ImportError:
    _notify = None

# Imported HARD, unlike the two above. yaml and _notify degrade to less output; _root IS the guard
# that decides whether this root may be reported on at all. A soft `_root = None` fallback would
# reopen the exact hole it closes — emitting a confident briefing from a body that isn't there.
import _root

PHASES = ("morning", "midday", "evening")
SUMMARY_NOTIFICATION_IDS = {"morning": "limen.summary.morning", "midday": "limen.summary.midday"}
REGISTRY_REL = "institutio/governance/diurnal.yaml"
MARKER_RX = "<!-- diurnal:{phase}:start -->"
MARKER_END = "<!-- diurnal:{phase}:end -->"


# ── parameters (every one declared in institutio/governance/parameters.yaml) ────────


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default


def _on(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default) == "1"


# Root resolution and the liveness guard are shared, not local. The local pair this replaced
# claimed "True iff this root is a live organism, not a bare projection" while testing only that
# `logs/.voice/` was a directory — which ONE stray sensor stamp satisfies. It opened in a worktree
# holding a single stamp and emitted a briefing in which five live-present sections read ABSENT.
# See scripts/_root.py for the measurement and for why the fix could not stay in this file.


# ── section rendering ──────────────────────────────────────────────────────────────


@dataclass
class Rendered:
    """One section's emission. `metric` is the integer the cut loop scores."""

    key: str
    title: str
    lines: list[str] = field(default_factory=list)
    metric: int | None = None
    stale: bool = False
    age_s: float | None = None
    exception: bool = False  # a cut section raising this auto-restores
    absent: str | None = None


def _age(path: Path) -> float | None:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None


def _human_age(seconds: float | None) -> str:
    if seconds is None:
        return "absent"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def _load_json(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _run(cmd: str, root: Path, timeout: int = 120) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.TimeoutExpired, OSError) as exc:
        return 124, str(exc)


# Each renderer: (root, spec, ctx) -> Rendered. Every one fails open with a legible line.


def r_pause_marker(root: Path, spec: dict, ctx: dict) -> Rendered:
    marker = root / "logs" / "AUTONOMY_PAUSED"
    if not marker.exists():
        return Rendered("autonomy", spec["title"], ["unpaused"])
    fields = {}
    for line in marker.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fields[k.strip()] = v.strip()
    lines = [f"PAUSED ({fields.get('class', 'unknown')}) — {fields.get('reason', 'no reason given')}"]
    for key in ("pr", "owner", "next_command"):
        if fields.get(key):
            lines.append(f"  {key}: {fields[key]}")
    return Rendered("autonomy", spec["title"], lines, exception=True)


def r_overnight_alerts(root: Path, spec: dict, ctx: dict) -> Rendered:
    path = root / "logs" / "overnight-watch.md"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    alerts: list[str] = []
    if "## WATCH_ALERT" in text:
        # stop at the NEXT heading — the HEAL verdict block below it is not an alert
        tail = re.split(r"^##\s", text.split("## WATCH_ALERT", 1)[-1], maxsplit=1, flags=re.M)[0]
        alerts = [a.strip() for a in re.findall(r"^\s*[-*]\s*(\S.*)$", tail, re.M) if a.strip()][:8]
    m = re.search(r"^\s*[-*]?\s*(?:\*\*)?Status(?:\*\*)?:\s*`?(\w+)", text, re.M)
    status = m.group(1) if m else ("alert" if alerts else "clear")
    nxt = re.search(r"^Next command:\s*(.+)$", text, re.M)
    lines = [f"status {status} · {len(alerts)} alert(s)"]
    lines += [f"  {a}" for a in alerts]
    if nxt:
        lines.append(f"  next: {nxt.group(1).strip()}")
    return Rendered("overnight", spec["title"], lines or ["clear"], metric=len(alerts), exception=bool(alerts))


def _one_line(val) -> str | None:
    """handoff.json carries task objects — render them as a human line, never a raw dict."""
    if val is None or val == [] or val == {}:
        return None
    if isinstance(val, list):
        return " · ".join(filter(None, (_one_line(v) for v in val[:2]))) or None
    if isinstance(val, dict):
        for key in ("title", "label", "reason", "summary"):
            if val.get(key):
                bits = [str(val[key])]
                if val.get("id") or val.get("agent"):
                    bits.append(f"[{val.get('id') or val.get('agent')}]")
                if val.get("priority"):
                    bits.append(f"({val['priority']})")
                return " ".join(bits)
        counts = {k: v for k, v in val.items() if isinstance(v, int)}
        return " · ".join(f"{k} {v}" for k, v in sorted(counts.items())[:4]) or None
    return str(val)


def r_next_action(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "logs" / "handoff.json") or {}
    lines = []
    for key, label in (("next_action", "next"), ("dispatchable_next", "dispatchable"), ("last_blocker", "blocker")):
        val = _one_line(data.get(key))
        if val:
            lines.append(f"{label}: {val}")
    return Rendered("next", spec["title"], lines or ["handoff.json carries no next action"])


def r_board_counts(root: Path, spec: dict, ctx: dict) -> Rendered:
    """Count task states without parsing 5.8MB of YAML.

    INDENTATION IS LOAD-BEARING. Task-level status is at indent 2; `dispatch_log` entries
    carry their OWN `status:` at indent 4. A flat grep conflates them and over-counts ~6x
    (measured 2026-07-31: 702 vs the true 109). Anchor to two spaces exactly.
    """
    counts = {}
    for state in ("needs_human", "open", "in_progress", "failed_blocked"):
        _, o = _run(rf"grep -c '^  status: {state}' tasks.yaml || true", root, timeout=60)
        counts[state] = int(o.strip()) if o.strip().isdigit() else 0
    needs_human = counts["needs_human"]
    lines = [
        f"needs_human {needs_human} · open {counts['open']} · in_progress {counts['in_progress']}"
        f" · failed_blocked {counts['failed_blocked']}"
    ]
    # Second independent method — handoff.json derives the same figure. Disagreement means one
    # of the two is scoped wrong, and a briefing must say so rather than pick a favourite.
    blocker = (_load_json(root / "logs" / "handoff.json") or {}).get("last_blocker") or {}
    cross = blocker.get("needs_human_count")
    if isinstance(cross, int) and needs_human and abs(cross - needs_human) > max(5, needs_human * 0.1):
        lines.append(f"  ⚠ COUNT DISAGREEMENT — handoff.json says {cross}, tasks.yaml says {needs_human}")
    return Rendered("board", spec["title"], lines, metric=needs_human)


def r_budget(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "logs" / "handoff.json") or {}
    board = data.get("board_budget") or {}
    remaining = board.get("remaining")
    lines = [f"runs {remaining}/{board.get('daily', '?')} remaining (spent {board.get('spent', '?')})"]
    headroom = data.get("budget_remaining") or {}
    vendors = [(k, v) for k, v in headroom.items() if isinstance(v, dict) and "headroom_pct" in v]
    if vendors:
        lines.append("  " + " · ".join(f"{k} {v['headroom_pct']}%" for k, v in sorted(vendors)[:6]))
    return Rendered("budget", spec["title"], lines, metric=remaining if isinstance(remaining, int) else None)


def r_his_hand(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "his-hand-levers.json") or {}
    levers = data.get("levers") or []
    # `status` is free-text and absent on 47/66 levers — absent means open (session-orient's read).
    closed = {"discharged", "retired", "done", "closed"}
    open_levers = [lv for lv in levers if str(lv.get("status", "")).strip().lower() not in closed]
    lines = [f"{len(open_levers)} open of {len(levers)} — the registry holds them, not this page"]
    return Rendered("levers", spec["title"], lines, metric=len(open_levers))


def r_owed_mail(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "logs" / "obligations-view.json") or {}
    items = data.get("obligations") or data.get("items") or []
    owed = len(items) if isinstance(items, list) else 0
    lines = [f"{owed} owed → obligations.html"]
    return Rendered("mail", spec["title"], lines, metric=owed)


def r_organ_liveness(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "logs" / "organ-health.json") or {}
    summary = data.get("summary") or {}
    not_green = sum(int(summary.get(k, 0) or 0) for k in ("stale", "down"))
    down = [o.get("rung") or o.get("key") for o in (data.get("organs") or []) if o.get("status") == "down"][:6]
    lines = [
        f"{summary.get('green', '?')}/{summary.get('total', '?')} green · "
        f"{summary.get('stale', 0)} stale · {summary.get('down', 0)} down"
    ]
    if down:
        lines.append("  down: " + ", ".join(str(d) for d in down))
    return Rendered("organs", spec["title"], lines, metric=not_green, exception=bool(down))


def r_ideal_forms_distance(root: Path, spec: dict, ctx: dict) -> Rendered:
    out = ctx.get("refresh_output", {}).get("ideal_forms", "")
    remains = len(re.findall(r"distance-remains", out))
    unmeasured = len(re.findall(r"unmeasured", out))
    at_ideal = len(re.findall(r"at-ideal", out))
    lines = [f"{at_ideal} at-ideal · {remains} distance-remains · {unmeasured} unmeasured"]
    return Rendered("ideal_forms", spec["title"], lines, metric=remains)


def r_omega_verdict(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "logs" / "omega.json") or {}
    fail = data.get("fail")
    fail_n = len(fail) if isinstance(fail, list) else (fail if isinstance(fail, int) else 0)
    lines = [f"{data.get('verdict', 'unknown')} — {fail_n} failing rung(s)"]
    return Rendered("omega", spec["title"], lines, metric=fail_n)


def r_pr_state(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "docs" / "github-pr-debt-ledger.json") or {}
    open_prs = data.get("open_pr_count")
    lines = [f"{open_prs} open across the estate"]
    return Rendered("prs", spec["title"], lines, metric=open_prs if isinstance(open_prs, int) else None)


def r_revenue(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "state" / "aug1" / "revenue-received.json") or {}
    received = data.get("received") or []
    n = len(received) if isinstance(received, list) else 0
    lines = [f"{n} cleared payment(s)" + ("" if n else " — the gate is honestly FALSE")]
    return Rendered("revenue", spec["title"], lines, metric=n)


def r_opportunity(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "logs" / "opportunity-status.json") or {}
    red = data.get("red_count", 0) or 0
    lines = [f"{data.get('total_inbound', '?')} inbound · {red} red · {data.get('stale_state_count', '?')} stale"]
    return Rendered("opportunity", spec["title"], lines, metric=int(red))


def r_routine_freshness(root: Path, spec: dict, ctx: dict) -> Rendered:
    data = _load_json(root / "logs" / "routine-freshness.json") or {}
    rows = data.get("routines") or data.get("results") or []
    overdue = [
        r for r in rows if isinstance(r, dict) and str(r.get("verdict", "")).lower() in {"overdue", "stale", "silent"}
    ]
    lines = [f"{len(overdue)} overdue of {len(rows)}"]
    if overdue:
        lines.append("  " + ", ".join(str(r.get("name", "?")) for r in overdue[:5]))
    return Rendered("routines", spec["title"], lines, metric=len(overdue))


def r_absent(root: Path, spec: dict, ctx: dict) -> Rendered:
    return Rendered(spec["_key"], spec["title"], [], absent=spec.get("absent_reason", "no source"))


# ── loop renderers: claims, scoring, cuts, carry ───────────────────────────────────


def _render_cap(rows: list, lines: list[str]) -> list[str]:
    """Bound what the PAGE shows without bounding what the ORGAN scores.

    Every elision says how much it elided. A briefing that silently shows 5 of 11 is how the
    render cap passed for a score cap in the first place — the page looked complete.
    """
    cap = _int("LIMEN_DIURNAL_CLAIM_RENDER_MAX", 5)
    if len(rows) <= cap:
        return lines
    return lines[:cap] + [f"… and {len(rows) - cap} more scored, not shown (all {len(rows)} accrue streaks)"]


def r_claims(root: Path, spec: dict, ctx: dict) -> Rendered:
    claims = ctx.get("claims") or []
    if not claims:
        return Rendered("claims", spec["title"], ["no falsifiable claim available today"])
    return Rendered("claims", spec["title"], _render_cap(claims, [f"{c['id']}. {c['text']}" for c in claims]))


# What MOVED is the news; a noop is the absence of news. When the render cap elides, it must
# elide noops — the reverse would hide the day's only real signal behind sections that did nothing.
_VERDICT_ORDER = {"missed": 0, "held": 1, "noop": 2}


def _by_news(scored: list[dict]) -> list[dict]:
    return sorted(scored, key=lambda s: (_VERDICT_ORDER.get(s["verdict"], 3), s["id"]))


def r_claim_midflight(root: Path, spec: dict, ctx: dict) -> Rendered:
    scored = ctx.get("midflight") or []
    if not scored:
        return Rendered("claims_midflight", spec["title"], ["no morning emission to test"])
    lines = [f"{s['id']}. [{s['verdict']}] {s['text']}" for s in _by_news(scored)]
    return Rendered("claims_midflight", spec["title"], _render_cap(scored, lines))


def r_drift(root: Path, spec: dict, ctx: dict) -> Rendered:
    drifts = ctx.get("drift") or []
    lines = drifts or ["nothing broke since morning"]
    return Rendered("drift", spec["title"], lines, metric=len(drifts), exception=bool(drifts))


def r_claim_scores(root: Path, spec: dict, ctx: dict) -> Rendered:
    scored = ctx.get("scored") or []
    if not scored:
        return Rendered("score", spec["title"], ["no morning emission to score"])
    tally = {"held": 0, "missed": 0, "noop": 0}
    lines = []
    for s in _by_news(scored):
        tally[s["verdict"]] = tally.get(s["verdict"], 0) + 1
        lines.append(f"{s['id']}. [{s['verdict']}] {s['text']} ({s['was']} → {s['now']})")
    # The tally counts EVERY scored section; only the per-claim listing is capped. A summary
    # derived from the visible rows would understate the day and mis-denominate the streaks.
    lines = _render_cap(scored, lines)
    lines.append(f"— held {tally['held']} · missed {tally['missed']} · noop {tally['noop']}")
    return Rendered("score", spec["title"], lines)


def r_happened(root: Path, spec: dict, ctx: dict) -> Rendered:
    lines = []
    _, commits = _run("git log --since=midnight --oneline 2>/dev/null | wc -l", root, timeout=30)
    lines.append(f"{commits.strip() or 0} commit(s) today")
    voice = root / "logs" / ".voice"
    if voice.is_dir():
        cutoff = time.time() - 86400
        fired = [p.name for p in voice.iterdir() if _age(p) is not None and p.stat().st_mtime >= cutoff]
        allv = list(voice.iterdir())
        lines.append(f"{len(fired)}/{len(allv)} organ voices fired in 24h")
        silent = sorted({p.name for p in allv} - set(fired))
        if silent:
            lines.append("  silent: " + ", ".join(silent[:8]))
    return Rendered("happened", spec["title"], lines)


def r_cuts(root: Path, spec: dict, ctx: dict) -> Rendered:
    applied = ctx.get("cuts_applied") or []
    proposed = ctx.get("cuts_proposed") or []
    restored = ctx.get("restored") or []
    lines = []
    for c in applied:
        lines.append(f"CUT {c['section']} — {c['reason']} (reverse: diurnal.py --uncut {c['section']})")
    for c in restored:
        lines.append(f"RESTORED {c} — it raised an exception while cut")
    # The AGE is the whole point of the proposal book: an undated "needs a PR" reads the same on
    # day 1 and day 40, which is how three of these accumulated to 10, 22 and 36 days unread.
    book = ctx.get("proposal_book") or {}
    for p in proposed:
        first = (book.get(p["what"]) or {}).get("first_seen")
        since = f" — open since {first}" if first else ""
        lines.append(f"PROPOSE {p['what']} — {p['reason']} (needs a PR{since})")
    return Rendered("cuts", spec["title"], lines or ["nothing earned a cut today"])


def r_carry(root: Path, spec: dict, ctx: dict) -> Rendered:
    carry = ctx.get("carry") or []
    return Rendered("carry", spec["title"], carry or ["nothing carries forward"])


RENDERERS = {
    "pause_marker": r_pause_marker,
    "overnight_alerts": r_overnight_alerts,
    "next_action": r_next_action,
    "board_counts": r_board_counts,
    "budget": r_budget,
    "his_hand": r_his_hand,
    "owed_mail": r_owed_mail,
    "organ_liveness": r_organ_liveness,
    "ideal_forms_distance": r_ideal_forms_distance,
    "omega_verdict": r_omega_verdict,
    "pr_state": r_pr_state,
    "revenue": r_revenue,
    "opportunity": r_opportunity,
    "routine_freshness": r_routine_freshness,
    "absent": r_absent,
    "claims": r_claims,
    "claim_midflight": r_claim_midflight,
    "drift": r_drift,
    "claim_scores": r_claim_scores,
    "happened": r_happened,
    "cuts": r_cuts,
    "carry": r_carry,
}


# ── state ──────────────────────────────────────────────────────────────────────────


def state_dir(root: Path, *, create: bool = True) -> Path:
    """The organ's state directory. `create=False` for read paths, so --dry-run writes NOTHING.

    The unconditional mkdir meant a --dry-run left an empty logs/diurnal/ behind — harmless, but
    "write nothing" was not literally true, and a dry run whose only side effect is small is still
    a dry run that lies.
    """
    d = root / "logs" / "diurnal"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(root: Path) -> dict:
    return _load_json(state_dir(root, create=False) / "state.json") or {"last_run": {}}


def save_state(root: Path, state: dict) -> None:
    (state_dir(root) / "state.json").write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def load_scores(root: Path) -> dict:
    return _load_json(state_dir(root, create=False) / "section-scores.json") or {}


def save_scores(root: Path, scores: dict) -> None:
    (state_dir(root) / "section-scores.json").write_text(json.dumps(scores, indent=2, sort_keys=True), encoding="utf-8")


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def engaged_today(root: Path) -> bool:
    """A day with no commits is UNSCORED, not noop — otherwise a week away prunes everything."""
    _, out = _run("git log --since=midnight --oneline 2>/dev/null | wc -l", root, timeout=30)
    try:
        return int(out.strip()) > 0
    except ValueError:
        return False


# ── the registry ───────────────────────────────────────────────────────────────────


def load_registry(root: Path) -> dict:
    if yaml is None:
        return {}
    path = root / REGISTRY_REL
    if not path.exists():  # worktree/live split — fall back to this checkout's copy
        path = Path(__file__).resolve().parent.parent / REGISTRY_REL
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    sections = data.get("sections") or {}
    for key, spec in sections.items():
        spec["_key"] = key
    return sections


# ── emission ───────────────────────────────────────────────────────────────────────


def render_phase(root: Path, sections: dict, phase: str, ctx: dict) -> list[Rendered]:
    scores = ctx["scores"]
    out: list[Rendered] = []
    for key, spec in sections.items():
        if phase not in (spec.get("phases") or []):
            continue
        cut = bool(scores.get(key, {}).get("cut"))
        renderer = RENDERERS.get(spec.get("render"))
        if renderer is None:
            out.append(Rendered(key, spec.get("title", key), [f"no renderer for '{spec.get('render')}'"]))
            continue
        # A CUT section still probes silently: if it raises an exception it auto-restores.
        try:
            rendered = renderer(root, spec, ctx)
        except Exception as exc:  # fail open, always legible
            rendered = Rendered(key, spec.get("title", key), [f"render failed: {exc}"])
        rendered.key = key

        src = spec.get("source")
        if src:
            path = root / src
            age = _age(path)
            rendered.age_s = age
            max_age = spec.get("max_age_seconds")
            if age is None:
                rendered.stale, rendered.lines = True, [f"ABSENT — {src} does not exist"]
            elif max_age and age > max_age:
                rendered.stale = True
                # A stale CACHE may hold a wrong value → withhold it. A stale REGISTRY holds a
                # frozen but still-true value → report it and say how old the state is.
                if spec.get("stale_policy", "withhold") == "annotate":
                    rendered.lines = rendered.lines + [
                        f"  FROZEN {_human_age(age)} — state unchanged since, counts still true"
                    ]
                else:
                    rendered.lines = [
                        f"STALE ({_human_age(age)}) — {src} exceeds its {_human_age(max_age)} tolerance",
                        "  value withheld rather than reported as current",
                    ]
                    rendered.metric = None

        if cut:
            if rendered.exception:
                ctx.setdefault("restored", []).append(key)
                scores.setdefault(key, {})["cut"] = False
                scores[key]["noop_streak"] = 0
            else:
                continue  # stays cut, stays silent
        out.append(rendered)
    return out


def build_claims(root: Path, sections: dict, rendered: list[Rendered]) -> list[dict]:
    """A claim is 'section X's metric will decrease today' — falsifiable, and identical to
    the section score, so scoring a claim and scoring a section are one measurement.

    EVERY eligible section is claimed. There is deliberately no cap here, and that is the fix
    for a defect this function shipped with: it used to `break` at a now-retired CLAIM_MAX
    parameter (5), written to keep the briefing short. But the claim list is also the score
    list, and the score list is what accrues noop streaks, and noop streaks are the only thing
    that fires a cut. A parameter meant to bound the PAGE was silently bounding the ORGAN'S
    GOVERNANCE: `diurnal.yaml` declared `cuttable: true` on 11 sections, section-scores.json
    held 4, and the other 7 could never accrue a streak, so they could never be cut — forever,
    invisibly. Length is a rendering concern; see LIMEN_DIURNAL_CLAIM_RENDER_MAX in r_claims().

    BOTH declared `acted_when` rules are honoured. check-diurnal.py's check C — "THE LOAD-BEARING
    RULE: cuttable: true ⟹ metric AND acted_when present" — admits `metric_changed`, and two
    sections use it (`budget.runs_remaining`, `revenue.received_count`) precisely because a FALL
    is bad news there, not progress. This function only ever implemented `metric_decreased`, so
    both passed the load-bearing rule, declared themselves cuttable, and were unclaimable. Note
    the floor differs by rule on purpose: you cannot claim a decrease below zero, but "changes
    from 0" is the most consequential claim the organ can make — it is IF-FIRST-DOLLAR.
    """
    claims = []
    by_key = {r.key: r for r in rendered}
    for key, spec in sections.items():
        kind = spec.get("acted_when")
        if kind not in ("metric_decreased", "metric_changed") or spec.get("metric") is None:
            continue
        r = by_key.get(key)
        if r is None or r.metric is None or r.stale:
            continue
        if r.metric < 0 or (kind == "metric_decreased" and r.metric <= 0):
            continue
        verb = "falls below" if kind == "metric_decreased" else "changes from"
        claims.append(
            {
                "id": len(claims) + 1,
                "section": key,
                "metric": spec["metric"],
                "acted_when": kind,
                "was": r.metric,
                "text": f"{spec['title']}: {spec['metric']} {verb} {r.metric}",
            }
        )
    return claims


def score_claims(claims: list[dict], rendered: list[Rendered]) -> list[dict]:
    by_key = {r.key: r for r in rendered}
    out = []
    for c in claims:
        r = by_key.get(c["section"])
        now = r.metric if r is not None else None
        # Claims written before `acted_when` rode on the claim default to the original rule, so a
        # morning emitted by the previous version still scores correctly in tonight's evening.
        if now is None:
            verdict = "noop"
        elif c.get("acted_when", "metric_decreased") == "metric_changed":
            # No direction is declared for this rule, so there is no wrong way to move: the only
            # failure it can express is not moving at all. Never emits `missed` — by design.
            verdict = "held" if now != c["was"] else "noop"
        elif now < c["was"]:
            verdict = "held"
        elif now > c["was"]:
            verdict = "missed"
        else:
            verdict = "noop"
        out.append({**c, "now": now, "verdict": verdict})
    return out


def apply_cuts(
    root: Path,
    sections: dict,
    scored: list[dict],
    scores: dict,
    threshold: int,
    max_per_day: int,
    engaged: bool,
    rendered: list[Rendered] | None = None,
) -> tuple[list, list]:
    """Evening authority. Auto-cuts only this organ's OWN sections; fleet-wide changes
    become proposals that need a PR.

    `rendered` is the evening's re-probe of the morning sections — the SAME objects the page is
    built from, so a section counted blind below is a section the reader saw rendered as STALE.
    Deriving staleness a second time here would let the counter and the page disagree.
    """
    applied, proposed = [], []
    if not engaged:
        return applied, proposed  # unscored day — no streak moves, no cut
    for s in scored:
        key = s["section"]
        rec = scores.setdefault(key, {"noop_streak": 0, "cut": False})
        if s["verdict"] == "noop":
            rec["noop_streak"] = int(rec.get("noop_streak", 0)) + 1
        else:
            rec["noop_streak"] = 0
    for key, rec in sorted(scores.items(), key=lambda kv: -int(kv[1].get("noop_streak", 0))):
        if len(applied) >= max_per_day:
            break
        spec = sections.get(key) or {}
        if rec.get("cut") or spec.get("protected") or not spec.get("cuttable"):
            continue
        if int(rec.get("noop_streak", 0)) >= threshold:
            rec["cut"] = True
            rec["cut_at"] = datetime.now().isoformat(timespec="seconds")
            reason = f"noop {rec['noop_streak']} consecutive engaged days"
            applied.append({"section": key, "reason": reason})
            append_jsonl(
                state_dir(root) / "cuts.jsonl", {"ts": rec["cut_at"], "action": "cut", "section": key, "reason": reason}
            )
    # A cuttable section reading a dead source is telling you nothing, every day — and the noop
    # machinery above cannot see it. build_claims() skips a stale section, so it is never claimed,
    # never scored, and its noop_streak never moves. Staleness was therefore a SHIELD: the sections
    # most worth examining were the only ones the cut could never reach, while the handful that
    # actually worked were the only candidates. `blind_streak` is the missing counter.
    #
    # It PROPOSES and never cuts. "The producer is dead" and "the section is worthless" are
    # different findings with different repairs, and nothing here can tell them apart — cutting
    # the section would silence the only evidence that the producer died.
    # DORMANT is the third way a section escapes the cut, and it was found by driving the fix
    # rather than by reading it: a fresh, cuttable section whose metric sits at its floor emits no
    # claim ("falls below 0" is not falsifiable), so it is neither scored nor blind. It would carry
    # a record with two zero counters and read as reachable while remaining uncuttable forever.
    #
    # It is PROPOSED, never cut, for a reason the blind case does not share: a zero can mean the
    # section is dead OR that its subject is in a healthy state (mail.owed == 0 is good news).
    # Nothing here can tell those apart, and a cut section only auto-restores on an exception —
    # not on a value change — so cutting a healthy zero would hide the row the day it matters.
    blind_threshold = _int("LIMEN_DIURNAL_BLIND_THRESHOLD", 5)
    dormant_threshold = _int("LIMEN_DIURNAL_DORMANT_THRESHOLD", 5)
    claimed = {s["section"] for s in scored}
    for r in rendered or []:
        spec = sections.get(r.key) or {}
        if not spec.get("cuttable"):
            continue
        rec = scores.setdefault(r.key, {"noop_streak": 0, "cut": False})
        # Exactly one of the three counters advances per engaged evening, so a cuttable section
        # can never again sit in a gap between them — which is what check 7b now asserts.
        if r.stale:
            rec["blind_streak"], rec["dormant_streak"] = int(rec.get("blind_streak", 0)) + 1, 0
            if rec["blind_streak"] >= blind_threshold:
                proposed.append(
                    {
                        "what": f"section:{r.key}",
                        "reason": (
                            f"blind {rec['blind_streak']} consecutive engaged days — "
                            f"{spec.get('source') or 'its source'} never went fresh; "
                            "repair the producer or retire the section"
                        ),
                    }
                )
        elif r.key in claimed:
            rec["blind_streak"] = rec["dormant_streak"] = 0
        else:
            rec["blind_streak"], rec["dormant_streak"] = 0, int(rec.get("dormant_streak", 0)) + 1
            if rec["dormant_streak"] >= dormant_threshold:
                proposed.append(
                    {
                        "what": f"section:{r.key}",
                        "reason": (
                            f"dormant {rec['dormant_streak']} consecutive engaged days — fresh source, "
                            f"but {spec.get('metric')} sat at its floor and made no falsifiable claim; "
                            "confirm the quiet is real or retire the section"
                        ),
                    }
                )
    # Fleet-wide: a source stale past a week is a fleet problem, not a briefing problem.
    for key, spec in sections.items():
        src = spec.get("source")
        if not src:
            continue
        age = _age(root / src)
        if age is not None and age > 7 * 86400:
            proposed.append({"what": src, "reason": f"source stale {_human_age(age)} — retire or repair the producer"})
    return applied, proposed


# ── markdown ───────────────────────────────────────────────────────────────────────


def record_proposals(root: Path, proposed: list[dict], today: str) -> dict:
    """Give the evening's proposals a durable home, an AGE, and a disposition.

    Before this they existed for the length of one render: apply_cuts() built the list, emit()
    put it on ctx, r_cuts() printed it into the page, and nothing read it again — no file, no
    dedup, no age, no owner. The organ had been printing "retire or repair logs/omega.json" on
    every evening page since 2026-07-31 while that file aged from 8 days stale to 10, and
    printing it is all that ever happened. Same species as the defects this arc opened with, one
    level up: a value is computed and consumed by nothing.

    A keyed map rather than an append-only log, because a proposal has STATE — open until
    someone disposes of it — and `disposition` is a field a human edits by hand. The history
    still lands, as `action: "propose"` rows in the cuts.jsonl the organ already writes, so
    nothing forks a new substrate to hold it.

    A proposal that stops recurring is auto-resolved. The condition went away — the producer was
    repaired, the section was retired — and a gate that stayed red on a solved problem would be
    the same defect wearing the opposite sign. Only ENGAGED evenings call this, so a week away
    cannot resolve every open proposal by simply not observing them.
    """
    path = state_dir(root) / "proposals.json"
    book = _load_json(path)
    book = book if isinstance(book, dict) else {}
    seen = {p["what"] for p in proposed}
    for p in proposed:
        rec = book.get(p["what"])
        if not isinstance(rec, dict):
            rec = book[p["what"]] = {"first_seen": today, "disposition": None}
            append_jsonl(
                state_dir(root) / "cuts.jsonl",
                {"ts": today, "action": "propose", "what": p["what"], "reason": p["reason"]},
            )
        rec["last_seen"], rec["reason"] = today, p["reason"]
    for what, rec in book.items():
        if what not in seen and isinstance(rec, dict) and rec.get("disposition") is None:
            rec["disposition"] = f"resolved {today} — the condition stopped recurring"
    path.write_text(json.dumps(book, indent=2, sort_keys=True), encoding="utf-8")
    return book


def render_markdown(phase: str, rendered: list[Rendered], stamp: str) -> str:
    lines = [MARKER_RX.format(phase=phase), "", f"## {stamp} · {phase}", ""]
    for r in rendered:
        lines.append(f"### {r.title}")
        if r.absent:
            lines.append(f"_ABSENT_ — {r.absent}")
        else:
            for ln in r.lines:
                lines.append(f"- {ln}" if not ln.startswith("  ") else f"  {ln.strip()}")
            if r.age_s is not None and not r.stale:
                lines.append(f"  <sub>source {_human_age(r.age_s)} old</sub>")
        lines.append("")
    lines.append(MARKER_END.format(phase=phase))
    return "\n".join(lines)


def write_block(page: Path, phase: str, block: str) -> None:
    """Replace only the marker-delimited block. Anything the operator typed OUTSIDE the
    markers survives regeneration — the studium.py never-overwrite-his-hand precedent."""
    page.parent.mkdir(parents=True, exist_ok=True)
    start, end = MARKER_RX.format(phase=phase), MARKER_END.format(phase=phase)
    existing = page.read_text(encoding="utf-8") if page.exists() else ""
    if start in existing and end in existing:
        head, _, rest = existing.partition(start)
        _, _, tail = rest.partition(end)
        new = head + block + tail
    else:
        header = "" if existing else f"# diurnal · {page.stem}\n\n"
        base = existing or header
        # Insert in CHRONOLOGICAL order, not write order. A phase re-run out of sequence
        # (or a backfilled midday) must not leave the day reading scrambled.
        later = [MARKER_RX.format(phase=p) for p in PHASES[PHASES.index(phase) + 1 :]]
        cut_at = min((base.index(m) for m in later if m in base), default=-1)
        if cut_at >= 0:
            new = base[:cut_at] + block + "\n" + base[cut_at:]
        else:
            new = base + ("\n" if base and not base.endswith("\n") else "") + block + "\n"
    page.write_text(new, encoding="utf-8")


def _clip(text: str, limit: int = 90) -> str:
    """Shorten for a push notification without guillotining the actionable part.

    The raw `[:90]` this replaces cut mid-identifier, and what it cut was the bracketed task id —
    observed live: "…for the whole PR estate [GITVS-UNCAPPED-". The id is the one token a reader
    can act on, so it is preserved even when the prose around it has to go, and the cut lands on a
    word boundary with an ellipsis so a truncated line reads as truncated.
    """
    if len(text) <= limit:
        return text
    tag = re.search(r"\[[A-Z][A-Z0-9-]{2,}\]\s*$", text.strip())
    if tag:
        ident = tag.group(0).strip()
        room = limit - len(ident) - 2
        if room > 12:
            head = text[:room].rsplit(" ", 1)[0].rstrip(" ·-—")
            return f"{head}… {ident}"
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ·-—") + "…"


def headline(phase: str, rendered: list[Rendered], ctx: dict) -> str:
    bits = []
    by = {r.key: r for r in rendered}
    if phase == "morning":
        nxt = by.get("next")
        if nxt and nxt.lines:
            bits.append(_clip(nxt.lines[0]))
        ov = by.get("overnight")
        if ov and ov.metric:
            bits.append(f"{ov.metric} overnight alert(s)")
    elif phase == "midday":
        drift = ctx.get("drift") or []
        bits.append(f"{len(drift)} drift")
        if drift:
            bits.append(_clip(str(drift[0])))
    else:
        scored = ctx.get("scored") or []
        held = sum(1 for s in scored if s["verdict"] == "held")
        bits.append(f"{held}/{len(scored)} claims held")
    return " · ".join(b for b in bits if b) or phase


# ── phases ─────────────────────────────────────────────────────────────────────────


def due_phase(now: datetime, state: dict, force: str | None) -> str | None:
    if force:
        return force
    today = now.strftime("%Y-%m-%d")
    hours = {
        "morning": _int("LIMEN_DIURNAL_MORNING_HOUR", 6),
        "midday": _int("LIMEN_DIURNAL_MIDDAY_HOUR", 12),
        "evening": _int("LIMEN_DIURNAL_EVENING_HOUR", 21),
    }
    # latest due phase whose hour has passed and which has not run today
    for phase in reversed(PHASES):
        if now.hour >= hours[phase] and state.get("last_run", {}).get(phase) != today:
            return phase
    return None


def emit(root: Path, phase: str, dry_run: bool) -> int:
    sections = load_registry(root)
    if not sections:
        print("diurnal: registry unreadable (PyYAML absent or diurnal.yaml malformed)", file=sys.stderr)
        return 1
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")
    scores = load_scores(root)
    ctx: dict = {"scores": scores, "refresh_output": {}}

    # refresh sources whose caches are known to lie
    for key, spec in sections.items():
        if phase in (spec.get("phases") or []) and spec.get("refresh") and not scores.get(key, {}).get("cut"):
            rc, out = _run(spec["refresh"], root, timeout=_int("LIMEN_DIURNAL_TIMEOUT", 240))
            ctx["refresh_output"][key] = out

    prev_morning = _load_json(state_dir(root, create=False) / f"{today}-morning.json") or {}

    if phase in ("midday", "evening"):
        claims = prev_morning.get("claims") or []
        # The claims this phase is ABOUT, carried so the receipt below records them in the one shape
        # every reader already expects. Set here rather than reconstructed at write time: the sidecar
        # tried to recover them from the scored rows and produced `text` STRINGS, while morning wrote
        # claim DICTS under the identical key. score_claims() indexes `c["section"]`, so a consumer
        # that fed a midday receipt back in the way midday itself consumes the morning one would hit
        # `TypeError: string indices must be integers`. One key, one type, one place that sets it.
        ctx["claims"] = claims
        probe = render_phase(root, sections, "morning", dict(ctx, claims=claims))
        scored = score_claims(claims, probe)
        ctx["midflight" if phase == "midday" else "scored"] = scored
        if phase == "midday":
            ctx["drift"] = [
                f"{s['text']} — worsened ({s['was']} → {s['now']})" for s in scored if s["verdict"] == "missed"
            ]
        else:
            # Bound here and CARRIED to the ledger below. The first draft consumed this only as an
            # apply_cuts() argument and dropped it, so the one fact the whole cut runway is
            # denominated in — how many days actually earned a score — existed for the length of a
            # function call and was never written down. done-diurnal.sh then read an `engaged_days`
            # key that no writer produced, and its `.get(..., 0)` default reported "0 days, not
            # there yet" instead of "this check has no writer" for as long as it would ever run.
            engaged = ctx["engaged"] = engaged_today(root)
            applied, proposed = apply_cuts(
                root,
                sections,
                scored,
                scores,
                _int("LIMEN_DIURNAL_CUT_THRESHOLD", 5),
                _int("LIMEN_DIURNAL_CUT_MAX_PER_DAY", 1),
                engaged,
                probe,
            )
            ctx["cuts_applied"], ctx["cuts_proposed"] = applied, proposed
            # Only reached when engaged — apply_cuts() returns ([], []) otherwise, so an away-week
            # can neither manufacture a proposal nor resolve one by failing to observe it.
            if engaged and not dry_run:
                ctx["proposal_book"] = record_proposals(root, proposed, today)
            ctx["carry"] = [s["text"] for s in scored if s["verdict"] in ("missed", "noop")][:5]
            if not engaged:
                ctx["carry"].insert(0, "day UNSCORED (no commits) — no streak moved, no cut fired")

    rendered = render_phase(root, sections, phase, ctx)
    if phase == "morning":
        ctx["claims"] = build_claims(root, sections, rendered)
        rendered = render_phase(root, sections, phase, ctx)  # re-render with claims populated

    block = render_markdown(phase, rendered, today)
    if dry_run:
        print(block)
        return 0

    write_block(root / "docs" / "diurnal" / f"{today}.md", phase, block)
    # THE RECEIPT MUST CARRY WHAT THE NOTIFICATION ANNOUNCED. `"scored": ctx.get("scored", [])` was
    # hardcoded, but midday writes its scoring to ctx["midflight"] (see the phase branch above), so
    # every midday sidecar persisted `claims: []` and `scored: []` — while the push notification,
    # built from ctx["drift"] a few lines earlier, went out saying "2 drift". The 2026-08-07 receipt
    # is 539 bytes, byte-for-byte the same empty shell as 2026-08-06's.
    #
    # The prose block was never lossy — docs/diurnal/2026-08-07.md carries both drifted claims by
    # name ("open_levers ... 68 → 73", "open_prs ... 1293 → 1297"). So a human could always answer
    # "which two?" and a machine could not: it read zero drift out of a run that alerted on two.
    # That asymmetry is the whole defect, and it is the quiet kind — an empty list is a valid
    # answer, so nothing anywhere reports an error.
    #
    # Derived from the phase rather than looked up under one fixed key: the midday/evening split
    # lives in exactly one place (that branch), and a receipt that re-guesses it is how the two got
    # out of step to begin with.
    scored_this_phase = ctx.get("midflight") if phase == "midday" else ctx.get("scored")
    sidecar = {
        "phase": phase,
        "date": today,
        "generated_at": now.isoformat(timespec="seconds"),
        # Morning EMITS claims; midday and evening SCORE the morning's. Both now set ctx["claims"]
        # to the same list-of-dicts shape, so this is a plain read — no phase-dependent fallback,
        # because that fallback is exactly what made one key carry two types.
        "claims": ctx.get("claims") or [],
        "scored": scored_this_phase or [],
        "sections": [{"key": r.key, "metric": r.metric, "stale": r.stale} for r in rendered],
    }
    # Only midday derives a drift list, and its ABSENCE on the other phases is meaningful rather
    # than missing data — the same conditional-key discipline `engaged` uses on the ledger row below.
    if phase == "midday":
        sidecar["drift"] = ctx.get("drift") or []
    (state_dir(root) / f"{today}-{phase}.json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8"
    )
    if phase in ("morning", "midday") and _on("LIMEN_DIURNAL_PUSH") and _notify is not None:
        text = headline(phase, rendered, ctx)
        active_ids = ",".join(_notify.active_conditions(root)) or "none"
        snapshot_time = now.strftime("%H:%M")
        delivery = _notify.emit_event_v1(
            root,
            stable_id=SUMMARY_NOTIFICATION_IDS[phase],
            transition="summary",
            subject_key=today,
            event_id=f"diurnal-{phase}-{today}",
            facts={"snapshot_time": snapshot_time, "summary": text, "active_alert_ids": active_ids},
            evidence_ref=str(state_dir(root) / f"{today}-{phase}.json"),
            producer="scripts/diurnal.py",
        )
        if delivery.status == "failed":
            print(f"diurnal: {phase} delivery failed — phase state not advanced")
            return 1
        _prune_notify_keys(root)
    # `engaged` rides only on evening rows — it is the evening that scores, and only a scored day
    # advances the cut runway. Its ABSENCE on a morning/midday row is meaningful, not missing data,
    # so it is written conditionally rather than defaulted to False: a reader counting the runway
    # must not be able to mistake "this phase does not score" for "this day earned nothing."
    row = {
        "ts": sidecar["generated_at"],
        "phase": phase,
        "sections": len(rendered),
        "cuts": len(ctx.get("cuts_applied") or []),
    }
    if "engaged" in ctx:
        row["engaged"] = bool(ctx["engaged"])
    append_jsonl(state_dir(root) / "ledger.jsonl", row)
    save_scores(root, scores)
    state = load_state(root)
    state.setdefault("last_run", {})[phase] = today
    save_state(root, state)

    write_index(root)

    print(f"diurnal: {phase} emitted — {len(rendered)} section(s) -> docs/diurnal/{today}.md")
    return 0


def write_index(root: Path) -> Path | None:
    """Regenerate docs/diurnal/INDEX.md — the organ's own reading surface.

    Until this existed the emission was WRITE-ONLY: `docs/diurnal/` was registered in
    docs-manifest.yaml with an owner, and nothing read it back — no route, no nav, no index,
    and `web/app`'s static-data generator has zero references to `docs/`. A daily briefing
    nobody can navigate to is a log file with better prose.

    Derived on every emission rather than appended to, so it cannot drift from the directory it
    describes: a hand-maintained index is the same failure one surface over. Rebuilt from the
    files themselves, so deleting a page removes its row and no bookkeeping is owed.
    """
    pages = sorted(
        (p for p in (root / "docs" / "diurnal").glob("*.md") if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.stem)),
        reverse=True,
    )
    if not pages:
        return None

    rows = []
    for page in pages:
        try:
            text = page.read_text(encoding="utf-8")
        except OSError:
            continue
        phases = [ph for ph in PHASES if MARKER_RX.format(phase=ph) in text]
        first = next(
            (ln.strip("- ").strip() for ln in text.splitlines() if ln.startswith("- ") and len(ln) > 4),
            "",
        )
        rows.append(f"| [{page.stem}]({page.name}) | {' · '.join(phases) or '—'} | {first[:80]} |")

    body = [
        "<!-- generated by scripts/diurnal.py — every emission rebuilds this file; do not hand-edit -->",
        "# DIVRNAL — daily emissions",
        "",
        f"{len(rows)} day(s). Newest first. Each page is marker-delimited: human text written",
        "outside the markers survives regeneration.",
        "",
        "| day | phases | first line |",
        "|-----|--------|------------|",
        *rows,
        "",
    ]
    path = root / "docs" / "diurnal" / "INDEX.md"
    path.write_text("\n".join(body), encoding="utf-8")
    return path


def _prune_notify_keys(root: Path) -> None:
    """notify_once is onset-deduped; date-keyed conditions would accrete forever."""
    if _notify is None:
        return
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    for key in list(_notify.active_conditions(root)):
        if key.startswith("diurnal:") and key.rsplit(":", 1)[-1] < cutoff:
            _notify.clear_condition(root, key)


# ── durability ─────────────────────────────────────────────────────────────────────
#
# The organ wrote its first live page and the page was UNTRACKED. `docs/diurnal/` is a tracked
# directory registered in docs-manifest.yaml, the emission lands inside it as `??`, and the beat's
# only committing rung — capture.sh — explicitly refuses an in-place commit on the live default
# branch and diverts dirt to a side ref instead. So the page was preserved in custody and never
# published: local-only, against Rule #2, rediscovered every day. An organ owns the durability of
# its own emission.


def _merge_prohibited(root: Path) -> str | None:
    """The pause that binds publication is the MARKER, not the governor's mode.

    Mirrors await-pr.sh's guard verbatim in intent: a marker whose `prohibitions:` line names
    merge binds every actor, the beat included. The governor's *window* pause is a different
    thing — it withdraws DISPATCH, the authority to spend other agents' capacity. Recording what
    the machine already observed spends nothing, sends nothing, deletes nothing. Conflating the
    two is precisely how a four-hour window that expired nine days ago also stopped the fleet
    from keeping its own record; the whole point of `heal(beat)` #1723 is that a pause withdraws
    acting on the world, not the machine's own coherence.
    """
    try:
        text = (root / "logs" / "AUTONOMY_PAUSED").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        if line.lower().startswith("prohibitions:") and "merge" in line.lower():
            return line.strip()
    return None


def _digest(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    except OSError:
        return ""


def shipped_receipts(root: Path) -> dict[str, dict]:
    """Normalize to `{rel: {"digest": ..., "pr": ...}}`, accepting the original bare-digest form.

    The first shape was `{rel: digest}`, which recorded THAT a page was handed off but not WHERE
    it went — so nothing could ever ask whether the handoff completed. That is the whole defect
    below: five CLEARED PRs sat open for two days while this file reported every page shipped.
    """
    out: dict[str, dict] = {}
    for rel, val in (_load_json(root / "logs" / "diurnal" / "shipped.json") or {}).items():
        out[rel] = {"digest": val} if isinstance(val, str) else dict(val)
    return out


def unshipped_pages(root: Path) -> list[str]:
    """Repo-relative diurnal pages on disk but neither committed nor already handed to a PR.

    `git status --porcelain` alone is NOT the predicate, and driving this live is what proved it:
    after a successful ship the page is still `??` in the live checkout, because it becomes
    tracked only once the PR merges AND the beat pulls. Git state alone would therefore re-ship
    the same page on every emission — three duplicate PRs a day for one file. So a content-keyed
    receipt (`logs/diurnal/shipped.json`) carries the gap, exactly as _notify.notify_once dedupes
    on onset rather than on the condition clearing. Keying on the DIGEST, not the path, is what
    makes a later phase re-ship the page it genuinely rewrote.

    Read-only against the daemon-contended live checkout: ship-docs.sh copies into its own
    worktree and never touches this tree. A staged deletion is skipped rather than shipped —
    ship-docs requires the file to exist, and a page deleted on purpose is not an emission.
    """
    rc, out = _run("git status --porcelain --untracked-files=all -- docs/diurnal", root, timeout=60)
    if rc != 0:
        return []
    receipts = shipped_receipts(root)
    pages = []
    for line in out.splitlines():
        rel = line[3:].strip()
        if not rel.endswith(".md") or rel.endswith("/README.md"):
            continue
        path = root / rel
        if path.is_file() and receipts.get(rel, {}).get("digest") != _digest(path):
            pages.append(rel)
    return sorted(set(pages))


def reap_shipped(root: Path, receipts: dict[str, dict]) -> int:
    """Merge the organ's OWN still-open page PRs. Returns how many reached MERGED.

    ship-docs.sh self-merges only if merge-policy clears within its own wait; otherwise it exits 2
    and hands the PR to "the beat's merge rung, per the charter". That rung is drain.sh, called at
    scripts/heartbeat-loop.sh:466 — 113 lines BELOW the paused branch's `continue` at line 353.
    Autonomy has been window-paused since 2026-07-22, so the named owner has not run once. Five
    CLEARED, non-deploy, organ-authored PRs sat open across three days while shipped.json reported
    every page published: the receipt recorded the HANDOFF, not the LANDING.

    So the organ closes its own loop, which is the ownership its own module docstring claims. This
    is not a general un-pausing and deliberately is not one:

      * scope — only PRs this organ opened, recorded by number in its own receipts;
      * class — ship-docs.sh REFUSES deploy-trigger paths, so no page here can reach the live site;
      * authority — the gate is _merge_prohibited(), the pause MARKER, exactly as the shipping path
        already reads it and for the reason written there: a window pause withdraws dispatch, not
        the machine's record of what it already observed. await-pr.sh independently refuses to
        start under a merge-prohibiting marker, so the guard holds even if this one were wrong.

    Bounded on purpose. merge-policy is only consulted for PRs still open, at most
    LIMEN_DIURNAL_REAP_MAX per run, and the merge itself goes through await-pr.sh — the one
    sanctioned waiter, with its own hard deadline. A hand-rolled poll loop here is exactly the
    banned pattern (the 2026-07-15 endless-watcher incident); anything past the deadline stays a
    PR and is retried next phase.
    """
    prs = sorted({r["pr"] for r in receipts.values() if isinstance(r.get("pr"), int)})
    if not prs:
        return 0
    merged = 0
    for pr in prs[: _int("LIMEN_DIURNAL_REAP_MAX", 3)]:
        rc, out = _run(f"gh pr view {pr} --json state --jq .state", root, timeout=60)
        if rc != 0 or out.strip() != "OPEN":
            continue  # already merged or closed — the receipt is stale, not the PR
        rc, _ = _run(f"bash {shlex.quote(str(root / 'scripts' / 'merge-policy.sh'))} {pr}", root, timeout=180)
        if rc != 0:
            print(f"diurnal: PR #{pr} not cleared (merge-policy exit {rc}) — left for the next phase")
            continue
        rc, out = _run(
            f"bash {shlex.quote(str(root / 'scripts' / 'await-pr.sh'))} {pr} --merge",
            root,
            timeout=_int("LIMEN_DIURNAL_REAP_TIMEOUT", 600),
        )
        if rc == 0:
            merged += 1
            print(f"diurnal: PR #{pr} MERGED — the page is on main")
        else:
            print(f"diurnal: PR #{pr} still open after await-pr (exit {rc}) — retried next phase")
    return merged


def ship_pages(root: Path, phase: str = "evening") -> int:
    """Land emitted pages on main through the sanctioned docs path. Never fails the beat.

    ship-docs.sh is the charter's answer to this exact class (it calls itself the side-door
    closer): named files only — never `git add -A` — onto a fresh branch cut from origin/main in
    an isolated worktree, PR opened, self-merged the moment merge-policy.sh clears. It refuses
    deploy-trigger paths outright, so a diurnal page can never blind-deploy the live site.

    Shipping is EVENING-ONLY for the current day. Every phase rewrites the page and regenerates
    INDEX.md, so a digest-keyed re-ship — correct behavior when pages land — opened three PRs for
    one file on 2026-08-01 while none of them merged. The page is only complete at evening; morning
    and midday are intermediate states of the same file. Earlier days still ship from any phase, so
    a crashed evening is caught the next morning rather than waiting a full day.
    """
    if not _on("LIMEN_DIURNAL_SHIP"):
        return 0
    prohibition = _merge_prohibited(root)
    if prohibition:
        print(f"diurnal: pages held local — pause marker {prohibition}", file=sys.stderr)
        return 0
    receipts = shipped_receipts(root)
    reap_shipped(root, receipts)
    pages = unshipped_pages(root)
    if phase != "evening":
        today = datetime.now().strftime("%Y-%m-%d")
        dated = [p for p in pages if Path(p).stem < today]
        # INDEX.md is not a day and rides along only when a dated page is actually shipping.
        pages = dated + [p for p in pages if Path(p).stem == "INDEX"] if dated else []
    if not pages:
        return 0
    script = root / "scripts" / "ship-docs.sh"
    if not script.is_file():
        print(f"diurnal: {len(pages)} page(s) unshipped — {script} absent", file=sys.stderr)
        return 0
    days = " ".join(Path(p).stem for p in pages)
    cmd = " ".join(
        [
            "bash",
            shlex.quote(str(script)),
            "diurnal",
            shlex.quote(f"docs(diurnal): {days}"),
            *(shlex.quote(p) for p in pages),
        ]
    )
    rc, out = _run(cmd, root, timeout=_int("LIMEN_DIURNAL_TIMEOUT", 240))
    verdict = {0: "merged", 2: "PR open — merge rung owns it", 124: "timed out; the PR owns itself"}
    print(f"diurnal: shipped {len(pages)} page(s) [{days}] — {verdict.get(rc, f'refused (exit {rc})')}")
    if rc not in (0, 2):
        print(out.strip()[-800:], file=sys.stderr)
    # Receipt on every outcome EXCEPT 1. ship-docs' exit 1 is its pre-flight `die` — bad slug,
    # deploy-trigger path, missing file — which happens before the branch or PR exist, so there
    # is nothing to dedupe against and a retry is correct. Every other exit means the PR was
    # created (0 merged it, 2 handed it to the merge rung, 124 timed out waiting on one), and
    # re-shipping would open a duplicate. A dropped page still surfaces: `--ship` is a manual
    # drain and `git status` never stops reporting it.
    if rc != 1:
        # The PR NUMBER, not just the digest. Without it the receipt says a page was handed off and
        # gives no way to ask whether the handoff completed — which is how five open PRs coexisted
        # with a receipt file reporting everything shipped. rc == 0 means ship-docs already merged
        # it, so there is nothing left to reap and no number is stored.
        m = re.search(r"opened PR #(\d+)", out)
        record = {"digest": None, "pr": int(m.group(1)) if m and rc != 0 else None}
        receipts = shipped_receipts(root)
        receipts.update({rel: {**record, "digest": _digest(root / rel)} for rel in pages})
        # Date-keyed records accrete forever otherwise — the same reason _prune_notify_keys exists.
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        receipts = {k: v for k, v in receipts.items() if Path(k).stem >= cutoff}
        (state_dir(root) / "shipped.json").write_text(json.dumps(receipts, indent=2), encoding="utf-8")
    return 0


# ── cli ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--phase", choices=(*PHASES, "auto"), default="auto")
    ap.add_argument("--dry-run", action="store_true", help="render to stdout; write nothing, push nothing")
    ap.add_argument("--force", action="store_true", help="emit even if this phase already ran today")
    ap.add_argument("--uncut", metavar="SECTION", help="restore a cut section")
    ap.add_argument("--list", action="store_true", help="print the section registry with cut state")
    ap.add_argument("--ship", action="store_true", help="land any unshipped pages on main; emit nothing")
    args = ap.parse_args()

    resolved, why = _root.resolve()
    if resolved is None:
        print(f"diurnal: {why}", file=sys.stderr)
        return 0  # advisory: never fail the beat
    root = resolved

    live, why = _root.has_body(root)
    if not live:
        # The reason is printed verbatim rather than summarised, because the three ways to fail
        # this guard need different fixes: a worktree needs LIMEN_ROOT, a cold checkout needs the
        # beat to have run, and a non-checkout needs the path corrected. "has no logs/.voice" —
        # the message this replaced — described only the case that never actually fired.
        print(f"diurnal: refusing to emit a false 'all quiet' — {why}", file=sys.stderr)
        return 0  # advisory: never fail the beat

    if args.ship:
        # A standalone drain, so the capability is observable and re-runnable without forcing a
        # re-emission. Idempotent via the shipped receipt, NOT via git state — a shipped page
        # stays untracked until its PR merges and the beat pulls. Explicitly evening-shaped: a
        # hand-run drain is asked for, so it takes today's page too rather than deferring it.
        return ship_pages(root, "evening")

    if args.list:
        sections, scores = load_registry(root), load_scores(root)
        for key, spec in sections.items():
            rec = scores.get(key, {})
            flag = (
                "CUT "
                if rec.get("cut")
                else ("prot" if spec.get("protected") else ("cut?" if spec.get("cuttable") else "keep"))
            )
            print(
                f"{flag:5} {key:20} {','.join(spec.get('phases') or []):22} "
                f"noop={rec.get('noop_streak', 0)} metric={spec.get('metric')}"
            )
        return 0

    if args.uncut:
        # A name the registry does not know is a TYPO, and must not be answerable with the same
        # sentence as a real section that simply isn't cut. Someone restoring a genuinely cut
        # section who fumbles the name would otherwise read "is not cut" and conclude nothing was
        # ever cut — the reassuring answer being the wrong one. The registry is already loaded two
        # branches down for --list; membership costs one lookup.
        sections = load_registry(root)
        if args.uncut not in sections:
            near = [k for k in sections if k.startswith(args.uncut[:3])] if len(args.uncut) >= 3 else []
            hint = f" Did you mean: {', '.join(sorted(near))}?" if near else ""
            print(
                f"diurnal: no section named {args.uncut!r} in the registry ({len(sections)} declared)."
                f"{hint} Run --list to see them.",
                file=sys.stderr,
            )
            return 2
        scores = load_scores(root)
        rec = scores.get(args.uncut)
        if not rec or not rec.get("cut"):
            print(f"diurnal: {args.uncut} is declared but not cut — nothing to restore")
            return 0
        rec["cut"], rec["noop_streak"] = False, 0
        save_scores(root, scores)
        append_jsonl(
            state_dir(root) / "cuts.jsonl",
            {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "action": "uncut",
                "section": args.uncut,
                "reason": "manual",
            },
        )
        print(f"diurnal: {args.uncut} restored")
        return 0

    if not _on("LIMEN_DIURNAL"):
        return 0

    state = load_state(root)
    phase = due_phase(datetime.now(), state, args.phase if args.phase != "auto" else None)
    if phase is None:
        return 0
    if (
        not args.force
        and not args.dry_run
        and state.get("last_run", {}).get(phase) == datetime.now().strftime("%Y-%m-%d")
    ):
        return 0
    rc = emit(root, phase, args.dry_run)
    # Shipping sits in main(), not in emit(): rendering a day and publishing it are different
    # concerns, and --dry-run must never reach the world. A failed emission ships nothing.
    if rc == 0 and not args.dry_run:
        ship_pages(root, phase)
    return rc


if __name__ == "__main__":
    sys.exit(main())
