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
decrease today." Evening re-reads the metric: decreased = held, unchanged = noop,
increased = missed. A noop claim IS a noop section — which is what accrues toward a cut.

Registry:  institutio/governance/diurnal.yaml
Predicate: scripts/check-diurnal.py
Emissions: docs/diurnal/YYYY-MM-DD.md (marker-delimited; human text outside survives)
State:     logs/diurnal/{state,section-scores}.json, ledger.jsonl, cuts.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
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

PHASES = ("morning", "midday", "evening")
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


def resolve_root() -> Path:
    """Resolve the LIVE organism root, never a worktree projection.

    A worktree's logs/ holds 2 files; the live root's holds ~198. A script that resolves
    the worktree reads an empty body and cheerfully reports "all quiet" — the single
    most dangerous failure mode this organ has.
    """
    env = os.environ.get("LIMEN_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parent.parent


def has_body(root: Path) -> bool:
    """True iff this root is a live organism (has beat voice stamps), not a bare projection."""
    return (root / "logs" / ".voice").is_dir()


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


def r_claims(root: Path, spec: dict, ctx: dict) -> Rendered:
    claims = ctx.get("claims") or []
    if not claims:
        return Rendered("claims", spec["title"], ["no falsifiable claim available today"])
    lines = [f"{c['id']}. {c['text']}" for c in claims]
    return Rendered("claims", spec["title"], lines)


def r_claim_midflight(root: Path, spec: dict, ctx: dict) -> Rendered:
    scored = ctx.get("midflight") or []
    if not scored:
        return Rendered("claims_midflight", spec["title"], ["no morning emission to test"])
    lines = [f"{s['id']}. [{s['verdict']}] {s['text']}" for s in scored]
    return Rendered("claims_midflight", spec["title"], lines)


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
    for s in scored:
        tally[s["verdict"]] = tally.get(s["verdict"], 0) + 1
        lines.append(f"{s['id']}. [{s['verdict']}] {s['text']} ({s['was']} → {s['now']})")
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
    for p in proposed:
        lines.append(f"PROPOSE {p['what']} — {p['reason']} (needs a PR)")
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


def state_dir(root: Path) -> Path:
    d = root / "logs" / "diurnal"
    d.mkdir(parents=True, exist_ok=True)
    return d


def load_state(root: Path) -> dict:
    return _load_json(state_dir(root) / "state.json") or {"last_run": {}}


def save_state(root: Path, state: dict) -> None:
    (state_dir(root) / "state.json").write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def load_scores(root: Path) -> dict:
    return _load_json(state_dir(root) / "section-scores.json") or {}


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


def build_claims(root: Path, sections: dict, rendered: list[Rendered], limit: int) -> list[dict]:
    """A claim is 'section X's metric will decrease today' — falsifiable, and identical to
    the section score, so scoring a claim and scoring a section are one measurement."""
    claims = []
    by_key = {r.key: r for r in rendered}
    for key, spec in sections.items():
        if spec.get("acted_when") != "metric_decreased" or spec.get("metric") is None:
            continue
        r = by_key.get(key)
        if r is None or r.metric is None or r.metric <= 0 or r.stale:
            continue
        claims.append(
            {
                "id": len(claims) + 1,
                "section": key,
                "metric": spec["metric"],
                "was": r.metric,
                "text": f"{spec['title']}: {spec['metric']} falls below {r.metric}",
            }
        )
        if len(claims) >= limit:
            break
    return claims


def score_claims(claims: list[dict], rendered: list[Rendered]) -> list[dict]:
    by_key = {r.key: r for r in rendered}
    out = []
    for c in claims:
        r = by_key.get(c["section"])
        now = r.metric if r is not None else None
        if now is None:
            verdict = "noop"
        elif now < c["was"]:
            verdict = "held"
        elif now > c["was"]:
            verdict = "missed"
        else:
            verdict = "noop"
        out.append({**c, "now": now, "verdict": verdict})
    return out


def apply_cuts(
    root: Path, sections: dict, scored: list[dict], scores: dict, threshold: int, max_per_day: int, engaged: bool
) -> tuple[list, list]:
    """Evening authority. Auto-cuts only this organ's OWN sections; fleet-wide changes
    become proposals that need a PR."""
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


def headline(phase: str, rendered: list[Rendered], ctx: dict) -> str:
    bits = []
    by = {r.key: r for r in rendered}
    if phase == "morning":
        nxt = by.get("next")
        if nxt and nxt.lines:
            bits.append(nxt.lines[0][:90])
        ov = by.get("overnight")
        if ov and ov.metric:
            bits.append(f"{ov.metric} overnight alert(s)")
    elif phase == "midday":
        bits.append(f"{len(ctx.get('drift') or [])} drift")
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

    prev_morning = _load_json(state_dir(root) / f"{today}-morning.json") or {}

    if phase in ("midday", "evening"):
        claims = prev_morning.get("claims") or []
        probe = render_phase(root, sections, "morning", dict(ctx, claims=claims))
        scored = score_claims(claims, probe)
        ctx["midflight" if phase == "midday" else "scored"] = scored
        if phase == "midday":
            ctx["drift"] = [
                f"{s['text']} — worsened ({s['was']} → {s['now']})" for s in scored if s["verdict"] == "missed"
            ]
        else:
            engaged = engaged_today(root)
            applied, proposed = apply_cuts(
                root,
                sections,
                scored,
                scores,
                _int("LIMEN_DIURNAL_CUT_THRESHOLD", 5),
                _int("LIMEN_DIURNAL_CUT_MAX_PER_DAY", 1),
                engaged,
            )
            ctx["cuts_applied"], ctx["cuts_proposed"] = applied, proposed
            ctx["carry"] = [s["text"] for s in scored if s["verdict"] in ("missed", "noop")][:5]
            if not engaged:
                ctx["carry"].insert(0, "day UNSCORED (no commits) — no streak moved, no cut fired")

    rendered = render_phase(root, sections, phase, ctx)
    if phase == "morning":
        ctx["claims"] = build_claims(root, sections, rendered, _int("LIMEN_DIURNAL_CLAIM_MAX", 5))
        rendered = render_phase(root, sections, phase, ctx)  # re-render with claims populated

    block = render_markdown(phase, rendered, today)
    if dry_run:
        print(block)
        return 0

    write_block(root / "docs" / "diurnal" / f"{today}.md", phase, block)
    sidecar = {
        "phase": phase,
        "date": today,
        "generated_at": now.isoformat(timespec="seconds"),
        "claims": ctx.get("claims", []),
        "scored": ctx.get("scored", []),
        "sections": [{"key": r.key, "metric": r.metric, "stale": r.stale} for r in rendered],
    }
    (state_dir(root) / f"{today}-{phase}.json").write_text(
        json.dumps(sidecar, indent=2, sort_keys=True), encoding="utf-8"
    )
    append_jsonl(
        state_dir(root) / "ledger.jsonl",
        {
            "ts": sidecar["generated_at"],
            "phase": phase,
            "sections": len(rendered),
            "cuts": len(ctx.get("cuts_applied") or []),
        },
    )
    save_scores(root, scores)
    state = load_state(root)
    state.setdefault("last_run", {})[phase] = today
    save_state(root, state)

    if phase in ("morning", "midday") and _on("LIMEN_DIURNAL_PUSH") and _notify is not None:
        text = headline(phase, rendered, ctx)
        if phase != "midday" or ctx.get("drift"):
            _notify.notify_once(root, f"diurnal:{phase}:{today}", text, title=f"LIMEN · {phase}")
        _prune_notify_keys(root)

    print(f"diurnal: {phase} emitted — {len(rendered)} section(s) -> docs/diurnal/{today}.md")
    return 0


def _prune_notify_keys(root: Path) -> None:
    """notify_once is onset-deduped; date-keyed conditions would accrete forever."""
    if _notify is None:
        return
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    for key in list(_notify.active_conditions(root)):
        if key.startswith("diurnal:") and key.rsplit(":", 1)[-1] < cutoff:
            _notify.clear_condition(root, key)


# ── cli ────────────────────────────────────────────────────────────────────────────


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--phase", choices=(*PHASES, "auto"), default="auto")
    ap.add_argument("--dry-run", action="store_true", help="render to stdout; write nothing, push nothing")
    ap.add_argument("--force", action="store_true", help="emit even if this phase already ran today")
    ap.add_argument("--uncut", metavar="SECTION", help="restore a cut section")
    ap.add_argument("--list", action="store_true", help="print the section registry with cut state")
    args = ap.parse_args()

    root = resolve_root()
    if not has_body(root):
        print(
            f"diurnal: {root} has no logs/.voice — refusing to emit a false 'all quiet'. "
            "Set LIMEN_ROOT to the live organism.",
            file=sys.stderr,
        )
        return 0  # advisory: never fail the beat

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
        scores = load_scores(root)
        rec = scores.get(args.uncut)
        if not rec or not rec.get("cut"):
            print(f"diurnal: {args.uncut} is not cut")
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
    return emit(root, phase, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
