#!/usr/bin/env python3
"""bifrons-organ.py — BIFRONS, the star<->contribution portal made alive (the limen beat face).

Doctrine: BIFRONS (Janus, two-faced) absorbs the repos we star and prepares contributions back —
one exchange_id threads the whole traversal. The engine half (organvm-engine `portal/`) owns the
loop mechanics; THIS is the heartbeat face that keeps it *alive*: each beat it metabolizes its own
past (crawls the prior state estate), runs one bounded effector cycle (`organvm portal metabolize`,
which absorbs new stars, maps resonance, and prepares inbound draft PRs — never submits), and renders
a deterministic proof surface. It asks nothing of the operator: the single external write (opening an
upstream PR) rides the existing system-wide outbound-send valve, never a BIFRONS-owned lever.

Fail-open on the beat: a missing `organvm`/`alchemia` CLI, an empty portal, or a slow upstream
degrades to rendering from existing state — the organ shows its dust honestly and still exits 0,
never gating the beat. The render is stamped from portal state (not the clock), so re-runs against an
unchanged portal are byte-identical — the idempotent fixed point the closeout discipline demands.
The explicit `--doctor` predicate is stricter: it exits 0 only when both the portal store and engine
CLI are reachable.

  python3 scripts/bifrons-organ.py            # metabolize one beat + render organs/observation/bifrons/PORTAL.md
  python3 scripts/bifrons-organ.py --no-beat  # render only (skip the effector cycle)
  python3 scripts/bifrons-organ.py --check    # predicate: committed PORTAL.md matches a fresh render (omega det)
  python3 scripts/bifrons-organ.py --doctor   # liveness: the portal store + engine CLI are reachable (omega live)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
from contextlib import closing
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
ORGAN_HOME = ROOT / "organs" / "observation" / "bifrons"
PORTAL_MD = ORGAN_HOME / "PORTAL.md"
SIGNAL = LOGS / "bifrons-portal.json"

STATE_DIR = Path(os.environ.get("BIFRONS_STATE_DIR", "~/.organvm/bifrons")).expanduser()
PORTAL_DB = Path(os.environ.get("BIFRONS_DB", str(STATE_DIR / "portal.db"))).expanduser()
BUDGET = int(os.environ.get("LIMEN_BIFRONS_BUDGET", "3"))

# The exchange lifecycle states we count as "prepared, pooling at the human gate".
_AWAITING = ("PATCH_PREPARED", "HUMAN_APPROVED")


def metabolize_estate() -> dict:
    """Reach into the past: CRAWL our own state estate and read the portal store.

    This is the metabolize signature (`.glob`/`rglob`) that proves the organ regenerates its
    understanding from its own history rather than a hand-fed input — the AVTOPOIESIS past tense.
    """
    snapshots = sorted(STATE_DIR.glob("*.json")) if STATE_DIR.is_dir() else []
    beat_logs = sorted(LOGS.glob("bifrons*.json*")) + sorted(ROOT.rglob("bifrons/state.json"))
    latest: dict = {}
    for snap in snapshots:
        if snap.name == "state.json":
            try:
                latest = json.loads(snap.read_text())
            except (OSError, json.JSONDecodeError):
                latest = {}
    return {"snapshots": len(snapshots), "beat_logs": len(beat_logs), "latest": latest}


def portal_counts() -> dict:
    """Read the shared portal store (read-only). Absent store -> empty counts (fail-open)."""
    counts = {
        "external_repo": 0,
        "dossier": 0,
        "resonance_edge": 0,
        "transmutation_proposal": 0,
        "backflow_signal": 0,
    }
    by_state: dict[str, int] = {}
    if not PORTAL_DB.exists():
        return {"counts": counts, "by_state": by_state, "present": False, "status": "absent"}
    try:
        with closing(sqlite3.connect(f"file:{PORTAL_DB}?mode=ro", uri=True)) as conn:
            conn.row_factory = sqlite3.Row
            # Opening a SQLite connection is lazy: corrupt or unreadable files can fail only on the
            # first schema read. Probe the store before suppressing optional-table errors below.
            conn.execute("SELECT 1 FROM sqlite_schema LIMIT 1").fetchone()
            for table in counts:
                try:
                    counts[table] = conn.execute(f"SELECT COUNT(*) n FROM {table}").fetchone()["n"]  # noqa: S608
                except sqlite3.OperationalError:
                    pass
            try:
                for row in conn.execute("SELECT state, COUNT(*) n FROM exchange GROUP BY state"):
                    by_state[row["state"]] = row["n"]
            except sqlite3.OperationalError:
                pass
    except sqlite3.Error:
        return {"counts": counts, "by_state": by_state, "present": False, "status": "unreadable"}
    return {"counts": counts, "by_state": by_state, "present": True, "status": "present"}


def run_beat() -> str:
    """One bounded effector cycle via the engine CLI. Fail-open: no CLI -> render-only."""
    if not shutil.which("organvm"):
        return "skip (organvm CLI not on PATH — rendered from existing state)"
    try:
        subprocess.run(  # noqa: S603
            ["organvm", "portal", "metabolize", "--budget", str(BUDGET), "--db", str(PORTAL_DB)],
            check=False, capture_output=True, timeout=int(os.environ.get("LIMEN_BIFRONS_TIMEOUT", "180")),
        )
        return "ran"
    except (OSError, subprocess.SubprocessError) as exc:
        return f"skip ({type(exc).__name__} — rendered from existing state)"


def render(portal: dict) -> str:
    counts = portal["counts"]
    by_state = portal["by_state"]
    awaiting = sum(by_state.get(s, 0) for s in _AWAITING)
    lines = [
        "# BIFRONS — the star ↔ contribution portal",
        "",
        "> Janus, two-faced: every starred repo is both **absorbed** (inbound) and **contributed-to**",
        "> (outbound); one `exchange_id` threads the traversal. Rendered by `scripts/bifrons-organ.py`",
        "> from the shared portal store. **Nothing here sends** — the one external write (an upstream",
        "> PR) is the human's hand, riding the existing outbound-send valve, never a BIFRONS lever.",
        "",
        "## Absorption (inbound)",
        "",
        "| stars | dossiers | resonance edges | transmutation proposals |",
        "|---:|---:|---:|---:|",
        f"| {counts['external_repo']} | {counts['dossier']} | {counts['resonance_edge']} "
        f"| {counts['transmutation_proposal']} |",
        "",
        "## Exchange lifecycle",
        "",
    ]
    if by_state:
        lines += ["| state | count |", "|---|---:|"]
        lines += [f"| {state} | {n} |" for state, n in sorted(by_state.items())]
    else:
        lines += ["_No exchanges yet — the portal store is empty or unreachable (honest dust)._"]
    lines += [
        "",
        "## The human gate (a valve, not a wall)",
        "",
        f"- **{awaiting}** contribution(s) prepared and pooling at the gate "
        "(`PATCH_PREPARED`/`HUMAN_APPROVED`).",
        f"- **{counts['backflow_signal']}** backflow signal(s) metabolized through the seven organs.",
        "- The autonomous loop runs to `HUMAN_APPROVED`; only the upstream PR is his hand.",
        "",
        "## Proof of life",
        "",
        f"- Portal store: `{'present' if portal['present'] else 'absent'}` (`~/.organvm/bifrons/portal.db`).",
        "- Engine loop: `organvm portal metabolize` (bounded, idempotent, never submits).",
        "- Outbound feeds SPECVLVM + `organvm/contrib/LEDGER.yaml` `source: starred` — not a rebuild.",
        "",
    ]
    return "\n".join(lines)


def write_signal(estate: dict, portal: dict, beat: str) -> None:
    counts = portal["counts"]
    by_state = portal["by_state"]
    SIGNAL.parent.mkdir(parents=True, exist_ok=True)
    SIGNAL.write_text(json.dumps({
        "organ": "bifrons",
        "beat": beat,
        "portal_present": portal["present"],
        "counts": counts,
        "exchanges_by_state": by_state,
        "prepared_awaiting_gate": sum(by_state.get(s, 0) for s in _AWAITING),
        "snapshots_crawled": estate["snapshots"],
        "portal_md": "organs/observation/bifrons/PORTAL.md",
    }, indent=2, sort_keys=True) + "\n")


def doctor() -> int:
    """Liveness (omega live tier): the portal store is reachable and the engine CLI resolves."""
    portal = portal_counts()
    cli = bool(shutil.which("organvm"))
    print(
        f"bifrons doctor: portal_store={portal['status']}  "
        f"engine_cli={'yes' if cli else 'no'}  "
        f"stars={portal['counts']['external_repo']}"
    )
    return 0 if portal["present"] and cli else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="BIFRONS — the star<->contribution portal beat face")
    ap.add_argument("--no-beat", action="store_true", help="render only; skip the effector cycle")
    ap.add_argument("--check", action="store_true", help="exit 0 iff committed PORTAL.md matches a fresh render")
    ap.add_argument("--doctor", action="store_true", help="liveness of the portal store + engine CLI")
    args = ap.parse_args()

    if args.doctor:
        return doctor()

    beat = "render-only"
    if not args.no_beat and not args.check:
        beat = run_beat()

    estate = metabolize_estate()
    portal = portal_counts()
    body = render(portal)

    if args.check:
        current = PORTAL_MD.read_text() if PORTAL_MD.exists() else ""
        if current == body:
            print(f"bifrons: PORTAL.md current ({portal['counts']['external_repo']} stars)")
            return 0
        print("bifrons: PORTAL.md STALE — re-run scripts/bifrons-organ.py")
        return 1

    ORGAN_HOME.mkdir(parents=True, exist_ok=True)
    changed = not PORTAL_MD.exists() or PORTAL_MD.read_text() != body
    if changed:
        PORTAL_MD.write_text(body)
    write_signal(estate, portal, beat)
    print(f"bifrons: PORTAL.md {'re-rendered' if changed else 'unchanged'} "
          f"(beat={beat}; {portal['counts']['external_repo']} stars, "
          f"{portal['counts']['resonance_edge']} edges)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
