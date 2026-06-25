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

ROOT = Path(os.environ.get("LIMEN_ROOT") or Path(__file__).resolve().parents[1])
# The auto-memory index lives outside the repo (per-user projects dir); resolve it from
# this repo's identity so the lookup is derived, never pinned to a machine path.
MEMORY_INDEX = (
    Path.home()
    / ".claude"
    / "projects"
    / "-Users-4jp-Workspace-limen"
    / "memory"
    / "MEMORY.md"
)


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
    if not isinstance(levers, list) or not levers:
        return ""
    ids = [str(lev.get("id") or lev.get("label", "?")) for lev in levers if isinstance(lev, dict)]
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
    """tasks.yaml status mix — streamed line-count, no full YAML parse (the file is large)."""
    counts = {}
    try:
        with (ROOT / "tasks.yaml").open("r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                m = re.match(r"\s*status:\s*(\S+)", line)
                if m:
                    counts[m.group(1)] = counts.get(m.group(1), 0) + 1
    except Exception:
        return ""
    if not counts:
        return ""
    parts = []
    for k in ("open", "dispatched", "done", "needs_human"):
        if counts.get(k):
            parts.append(f"{counts[k]} {k}")
    return "**Board** — " + " · ".join(parts) if parts else ""


def section_git():
    """Current branch, ahead/behind main, dirty flag."""
    def _git(*args):
        try:
            return subprocess.run(
                ["git", "-C", str(ROOT), *args],
                capture_output=True, text=True, timeout=4,
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


def section_pointers():
    """A fixed 'read these first' footer — the things he asks me to read every session."""
    return (
        "**Read first** — EVERY-ASK-LEDGER.md (present-over-past) · "
        "CLAUDE.md (operating charter) · his-hand-levers.json (owned, don't nag)"
    )


# ── main ────────────────────────────────────────────────────────────────────


def main():
    sections = (
        section_north_star,
        section_levers,
        section_organs,
        section_health,
        section_board,
        section_git,
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
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(digest, encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
