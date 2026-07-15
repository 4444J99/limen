#!/usr/bin/env python3
"""session-orient.py — the PII-free session-orientation digest.

The originating pain: the orienting context re-pasted at the top of every session
(north star, open his-hand levers, organ liveness, the board, git state). The daemon
already computes this state every beat; the session should *read* it, not recompute it.
This generator reads ONLY small persisted artifacts (never the ~1s HTML renderer),
prints a compact markdown digest to stdout, AND writes logs/session-orientation.md so
the SessionStart hook (and a daemon pre-warm) can serve the last-good copy instantly.

Every section FAILS OPEN: a missing/torn input yields an empty section, never a crash.
The whole thing is read-only.

PII FIREWALL (non-negotiable): counts-only. logs/ is committed and capture.sh auto-pushes
to the PUBLIC origin, so this digest echoes NO chart/health content and hardcodes NO
medical literal — it reads numeric liveness counts by field NAME from the already-committed,
counts-only logs/health-organ-state.json, and lever IDs/titles that already live PII-free in
the committed registry. The firewall guards this generator, not just its output.
"""

import json
import os
import re
import subprocess
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover - dependency absence is a fail-open hook path.
    yaml = None

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
# The auto-memory index lives outside the repo (per-user projects dir); resolve it from
# this repo's identity so the lookup is derived, never pinned to a machine path.
MEMORY_INDEX = Path.home() / ".claude" / "projects" / "-Users-4jp-Workspace-limen" / "memory" / "MEMORY.md"


def _read_text(path, limit_bytes=None):
    try:
        p = Path(path)
        if limit_bytes is not None:
            with p.open("r", encoding="utf-8", errors="replace") as fh:
                return fh.read(limit_bytes)
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_json(path, default):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def _trunc(s, n):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ── sections ──────────────────────────────────────────────────────────────────


def section_north_star():
    """The one-line north-star anchor from the auto-memory index's first entry."""
    txt = _read_text(MEMORY_INDEX, limit_bytes=4096)
    for line in txt.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        # "- [Title](file) — hook …[[link]]"  → take the hook after the em dash.
        hook = line.split(" — ", 1)[1] if " — " in line else line
        hook = re.sub(r"\[\[[^\]]+\]\]", "", hook).strip(" .")
        return f"**North star** — {_trunc(hook, 170)}"
    return ""


def section_levers():
    """Open his-hand levers: count + the top few IDs (all PII-free in the registry)."""
    d = _read_json(ROOT / "his-hand-levers.json", {})
    levers = d.get("levers") if isinstance(d, dict) else (d if isinstance(d, list) else [])
    if not isinstance(levers, list):
        return ""
    levers = [lev for lev in levers if isinstance(lev, dict) and not lev.get("discharged")]
    if not levers:
        return ""
    ids = [str(lev.get("id") or lev.get("label", "?")) for lev in levers]
    head = ", ".join(ids[:4])
    more = f" +{len(ids) - 4} more" if len(ids) > 4 else ""
    return f"**His-hand levers** — {len(levers)} open · {head}{more} (detail: his-hand-levers.json)"


def section_organs():
    """Organ liveness: live/total + any gated/stale organs by key. No content, just status."""
    d = _read_json(ROOT / "logs" / "organ-health.json", {})
    summ = d.get("summary", {}) if isinstance(d, dict) else {}
    organs = d.get("organs", []) if isinstance(d, dict) else []
    total = summ.get("total")
    live = summ.get("live")
    if total is None or live is None:
        return ""
    flags = []
    gated = [o.get("key") for o in organs if isinstance(o, dict) and o.get("status") == "gated"]
    stale = [o.get("key") for o in organs if isinstance(o, dict) and o.get("status") == "stale"]
    if gated:
        flags.append("gated: " + ", ".join(filter(None, gated)))
    if stale:
        flags.append("stale: " + ", ".join(filter(None, stale)))
    tail = f" ({' · '.join(flags)})" if flags else ""
    return f"**Organs** — {live}/{total} live{tail}"


def section_health():
    """Health organ — LIVENESS COUNTS ONLY (firewall). Reads numeric fields by name; no content."""
    d = _read_json(ROOT / "logs" / "health-organ-state.json", {})
    if not isinstance(d, dict) or not d:
        return ""
    if not d.get("chart_present"):
        return "**Health organ** — no chart yet (counts only; PII stays off-repo)"
    bits = []
    loops = d.get("open_loops")
    if loops is not None:
        bits.append(f"{loops} open loops")
    atoms = d.get("human_atoms_open")
    if atoms is not None:
        bits.append(f"{atoms} human-atoms")
    nappt = d.get("next_appt_in_days")
    if nappt is not None:
        bits.append(f"next appt in {nappt}d")
    return "**Health organ** — chart present · " + " · ".join(bits) + " (counts only; no PII)"


def section_board():
    """tasks.yaml status mix, counting only task records, not dispatch_log transitions."""
    if yaml is None:
        return ""
    counts = {}
    tasks_path = Path(os.environ.get("LIMEN_ORIENT_TASKS") or ROOT / "tasks.yaml")
    try:
        data = yaml.safe_load(tasks_path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return ""
    tasks = data.get("tasks") if isinstance(data, dict) else []
    for task in tasks if isinstance(tasks, list) else []:
        if not isinstance(task, dict):
            continue
        status = task.get("status")
        if status:
            counts[str(status)] = counts.get(str(status), 0) + 1
    if not counts:
        return ""
    parts = []
    for k in ("open", "dispatched", "in_progress", "done", "needs_human", "failed_blocked"):
        if counts.get(k):
            parts.append(f"{counts[k]} {k}")
    return "**Board** — " + " · ".join(parts) if parts else ""


def section_git():
    """Current branch, ahead/behind main, dirty flag."""
    if "LIMEN_ORIENT_GIT_SECTION" in os.environ:
        return os.environ.get("LIMEN_ORIENT_GIT_SECTION", "")

    def _git(*args):
        try:
            return subprocess.run(
                ["git", "-C", str(ROOT), *args],
                capture_output=True,
                text=True,
                timeout=4,
            ).stdout.strip()
        except Exception:
            return ""

    branch = _git("rev-parse", "--abbrev-ref", "HEAD")
    if not branch:
        return ""
    dirty = "dirty" if _git("status", "--porcelain") else "clean"
    ahead = behind = None
    counts = _git("rev-list", "--left-right", "--count", "origin/main...HEAD")
    if counts and len(counts.split()) == 2:
        behind, ahead = counts.split()
    pos = f" · ahead {ahead}/behind {behind} of main" if ahead is not None else ""
    return f"**Git** — {branch}{pos} · {dirty}"


def section_lifecycle_pressure():
    """Local/remote lifecycle pressure from the last SessionEnd refresh."""
    txt = _read_text(ROOT / "logs" / "session-lifecycle-pressure.md", limit_bytes=1024)
    line = next((ln.strip() for ln in txt.splitlines() if ln.strip()), "")
    if line:
        return _trunc(line, 260)
    gen = ROOT / "scripts" / "session-lifecycle-pressure.py"
    if not gen.is_file():
        return ""
    try:
        proc = subprocess.run(
            ["python3", str(gen)],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    return _trunc(proc.stdout.strip(), 260)


def section_tranche():
    """Current bounded conductor tranche, if one has been selected."""
    txt = _read_text(ROOT / "docs" / "conductor-tranche.md", limit_bytes=4096)
    summary = next((ln.strip() for ln in txt.splitlines() if ln.startswith("Summary:")), "")
    if not summary:
        return ""
    summary = summary.removeprefix("Summary:").strip()
    return f"**Current tranche** — {_trunc(summary, 260)}"


def section_pointers():
    """A fixed 'read these first' footer — the things he asks me to read every session."""
    return (
        "**Read first** — EVERY-ASK-LEDGER.md (present-over-past) · "
        "CLAUDE.md (operating charter) · his-hand-levers.json (owned, don't nag)"
    )


# ── main ────────────────────────────────────────────────────────────────────


def section_handoff() -> str:
    """Inject the seam-survival handoff (scripts/handoff-relay.py) so a resuming session picks up
    WARM — open lanes, in-flight/stale claims, budget, and the single next action — instead of
    cold-deriving. Silent if no fresh handoff exists."""
    data = _read_json(ROOT / "logs" / "handoff.json", {})
    if not isinstance(data, dict) or not data.get("generated"):
        return ""
    lanes = data.get("open_lanes") or {}
    inflight = data.get("in_flight_claims") or {}
    blk = data.get("last_blocker") or {}
    b = data.get("budget_remaining") or {}
    na = data.get("next_action") or {}
    line = (
        f"**Resume (handoff)** — {lanes.get('total_open', 0)} open / "
        f"{len(lanes.get('by_lane', {}))} lanes · {inflight.get('count', 0)} in-flight "
        f"({inflight.get('stale', 0)} stale) · needs_human {blk.get('needs_human_count', 0)}"
    )
    if b.get("overnight_remaining") is not None:
        line += f" · beat budget {b.get('overnight_spent')}/{b.get('overnight_cap')}"
    if na.get("id"):
        line += f"\n  next → `{na.get('id')}` [{na.get('priority')}] {na.get('title', '')}"
    return line


def section_omega() -> str:
    """Inject the autonomic fixed-point verdict (scripts/omega.sh → logs/omega.json) so a resuming
    session sees at a glance whether the WHOLE holds — not just that individual gates are green. A
    SKIP count is honest unverified-rungs, not failure. Silent if no stamp exists."""
    data = _read_json(ROOT / "logs" / "omega.json", {})
    if not isinstance(data, dict) or not data.get("verdict"):
        return ""
    verdict = data.get("verdict")
    line = (
        f"**Omega** — {verdict} · {data.get('pass', 0)} PASS / "
        f"{data.get('fail', 0)} FAIL / {data.get('skip', 0)} SKIP"
        f"{' (offline subset)' if data.get('offline') else ''}"
    )
    if data.get("fail"):
        broken = [r.get("rung") for r in data.get("rungs", []) if isinstance(r, dict) and r.get("status") == "FAIL"]
        if broken:
            line += f"\n  off fixed-point: {', '.join(filter(None, broken))[:160]}"
    return line


def section_autonomy() -> str:
    """Surface a live autonomy pause so a session honors it — the marker's prohibitions bind
    interactive sessions too (2026-07-15 endless-watcher incident: sessions armed auto-merge
    watchers while the marker prohibited merges, because orientation never showed it).
    Silent when no marker exists."""
    marker = ROOT / "logs" / "AUTONOMY_PAUSED"
    try:
        lines = marker.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""

    def field(name: str) -> str:
        return next((ln.split(":", 1)[1].strip() for ln in lines if ln.strip().startswith(f"{name}:")), "")

    line = f"**Autonomy** — PAUSED: {(field('reason') or 'see logs/AUTONOMY_PAUSED')[:140]}"
    prohibitions = field("prohibitions")
    if prohibitions:
        line += f"\n  prohibitions (bind THIS session too): {prohibitions[:140]}"
    return line


def main():
    sections = (
        section_north_star,
        section_autonomy,
        section_omega,
        section_handoff,
        section_levers,
        section_organs,
        section_health,
        section_board,
        section_git,
        section_lifecycle_pressure,
        section_tranche,
        section_pointers,
    )
    parts = []
    for fn in sections:
        try:
            out = fn()
        except Exception:
            out = ""
        if out:
            parts.append(out)

    header = "## Session orientation (auto)"
    digest = header + "\n\n" + "\n".join(parts) + "\n"
    print(digest, end="")

    out_path = ROOT / "logs" / "session-orientation.md"
    if os.environ.get("LIMEN_ORIENT_NO_WRITE") == "1":
        return
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(digest, encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
