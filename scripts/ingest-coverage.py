#!/usr/bin/env python3
"""ingest-coverage — the diagnostic that answers "are we at 100% context?" on screen, not by asking.

Reads the session-meta ingest manifest (every prompt from every source, content-addressed) and computes
a coverage snapshot → logs/ingest-coverage.json (which omni-view renders): how many atoms, from which
sources, how FRESH the ingest is (staleness is the real gap — a corpus that stopped being fed decays),
and which known prompt-sources still have NO adapter (the honest gaps). No re-ingest — read-only over the
existing manifest, so it's cheap enough to run every web beat. Fail-open: any error writes nothing.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
MANIFEST = Path(os.environ.get(
    "LIMEN_INGEST_MANIFEST", ROOT.parent / "session-meta" / "ingest" / "manifest.jsonl"))
# the universe we WANT ingested — every prompt from every source. Adapters present vs. this = coverage.
TARGET_SOURCES = {
    "claude", "claude-code-sessions", "claude-projects", "codex", "chatgpt", "gemini",
    "antigravity", "opencode", "cowork-sessions", "downloads", "intake",
    "session-transcripts", "notes",
    # known gaps (no adapter yet) — counted as missing so coverage is honest, not flattering:
    "copilot", "ollama", "workbench", "perplexity",
}
KNOWN_GAPS = {"copilot", "ollama", "workbench", "perplexity"}


def main() -> int:
    try:
        lines = MANIFEST.read_text().splitlines()
    except OSError:
        print(f"ingest-coverage: no manifest at {MANIFEST} — wrote nothing (fail-open).")
        return 0

    atoms = 0
    by_source: dict[str, int] = {}   # records (blobs) per source — the populated, honest volume
    atoms_by_source: dict[str, int] = {}
    latest = None
    for ln in lines:
        try:
            r = json.loads(ln)
        except ValueError:
            continue
        n = int(r.get("atom_count", 0) or 0)
        src = r.get("source") or "?"
        atoms += n
        by_source[src] = by_source.get(src, 0) + 1
        atoms_by_source[src] = atoms_by_source.get(src, 0) + n
        mt = r.get("mtime")
        if isinstance(mt, str) and (latest is None or mt > latest):
            latest = mt

    # a source counts as INGESTED if it has any records (atoms are extracted downstream; atom_count is
    # only populated in the atoms store, so blob presence is the reliable coverage signal here).
    present = {s for s, n in by_source.items() if n > 0}
    blobs = sum(by_source.values())
    missing = sorted(s for s in TARGET_SOURCES if s not in present)
    coverage_pct = round(100 * len(present & TARGET_SOURCES) / max(1, len(TARGET_SOURCES)))

    age_days = None
    try:
        # freshness: the manifest file's own mtime is when the ingest last RAN.
        last_run_dt = datetime.fromtimestamp(MANIFEST.stat().st_mtime, tz=timezone.utc)
        age_days = round((datetime.now(timezone.utc) - last_run_dt).total_seconds() / 86400, 1)
        last_run = last_run_dt.date().isoformat()
    except OSError:
        last_run = (latest or "")[:10]

    snap = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "atoms": atoms or blobs,            # populated atoms if present, else the blob volume
        "atoms_extracted": atoms,
        "blobs": blobs,
        "sources": len(present),
        "coverage_pct": coverage_pct,
        "last_run": last_run,
        "age_days": age_days,
        "stale": bool(age_days is not None and age_days > 2),
        "by_source": dict(sorted(by_source.items(), key=lambda kv: -kv[1])),
        "missing_adapters": [m for m in missing if m in KNOWN_GAPS],
    }
    (ROOT / "logs").mkdir(exist_ok=True)
    try:
        (ROOT / "logs" / "ingest-coverage.json").write_text(json.dumps(snap, indent=2))
    except OSError as e:
        print(f"ingest-coverage: could not write ({e})")
        return 0
    flag = " ⚠STALE" if snap["stale"] else ""
    vol = f"{atoms:,} atoms" if atoms else f"{blobs:,} blobs"
    print(f"ingest-coverage: {vol} · {snap['sources']} sources · {coverage_pct}% adapter coverage "
          f"· last ingest {last_run} ({age_days}d ago){flag} · gaps: {', '.join(snap['missing_adapters']) or 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
