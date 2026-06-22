#!/usr/bin/env python3
"""studium-converge.py — consolidate the scattered curriculum estate into one Studium face.

This is the alchemical-reduction half of the build (his "consolidation of alchemical reduction albeit
evolutionary expansion"). It gathers the dribs and drabs — his verbatim seed, the 15-week macro
schedule, the Derek craft notes, the carrier-wave reading list — as convergence Shots and drives the
limen converge() engine to distill ONE better version (the reading-arc rationale), CITING the losers
as provenance and surfacing gaps as the expansion backlog. NON-DESTRUCTIVE: originals are read-only;
the prior converged version stays in git ([[distillation-not-reduction]], [[alchemical-convergence-method]]).

Offline by default (dry-run kit — a provenance-cited assembly, no network). --live distills for real
via the keyless `claude -p` synthesizer (same path the corpus-converge organ uses in the daemon).

Usage:
  python3 scripts/studium-converge.py            # offline preview (writes the converged face)
  python3 scripts/studium-converge.py --live     # real distillation via claude -p
"""
import os
import sys
import json
import hashlib
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(ROOT / "cli" / "src"))
STUDIUM = ROOT / "studium"
HOME = Path(os.path.expanduser("~"))

# The scattered estate — (label, path-or-glob). Missing sources are skipped (fail-open).
SOURCES = [
    ("seed", STUDIUM / "_seed" / "*.md"),
    ("15-week-macro-schedule", HOME / "Workspace/organvm/_agent/Archive4/Finalized 15-Week Macro Schedule*"),
    ("derek-craft-notes", HOME / "Workspace/edu-organism/skins/private-classes/derek-narrative-program/_raw/*.md"),
    ("carrier-wave-reading-list", HOME / "Workspace/carrier-wave--zeitgeist-thesis/research/reading-list.md"),
]

IDEA = ("The Studium reading arc — the canonical transmission curriculum (read the canon · copy the "
        "original script · translate · compare translations · one note · one fitting composition · log), "
        "distilled from every scattered curriculum source into one organism.")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def gather_shots():
    """Read every scattered source as a convergence Shot (bounded text). Fail-open per source."""
    from limen.converge import Shot
    shots = []
    for label, pat in SOURCES:
        for p in sorted(Path(pat.parent).glob(pat.name)) if "*" in pat.name else ([pat] if pat.exists() else []):
            try:
                text = p.read_text(errors="replace")
            except OSError:
                continue
            if not text.strip():
                continue
            sid = f"{label}:{hashlib.sha1(str(p).encode()).hexdigest()[:8]}"
            shots.append(Shot(id=sid, text=text[:20000], source=str(p)))
    return shots


def _kit(live):
    from limen.converge import _build_dry_run_kit
    kit = _build_dry_run_kit()
    if not live:
        return kit
    try:  # keyless live synthesis (the daemon path); fall back to offline on any import/env failure
        from limen.converge import ClaudeCliSynthesizer
        kit["synthesizer"] = ClaudeCliSynthesizer()
    except Exception as e:  # noqa: BLE001 — cascade, never hard-fail ([[no-never-happens-again]])
        print(f"studium-converge: live synth unavailable ({e}); using offline kit")
    return kit


def main():
    live = "--live" in sys.argv
    try:
        from limen.converge import converge
    except Exception as e:  # noqa: BLE001
        print(f"studium-converge: converge engine unavailable ({e}); skipping (no-op, fail-open)")
        return 0

    shots = gather_shots()
    if not shots:
        print("studium-converge: no scattered sources found; nothing to consolidate")
        return 0

    result = converge(IDEA, shots, **_kit(live), threshold=0.6)

    out = STUDIUM / "_converged" / "reading-arc.md"
    losers = ", ".join(s.id for s in result.cited_losers) or "—"
    header = (f"# The Studium reading arc — converged\n\n"
              f"> _Converged {date.today()} from {len(shots)} scattered sources "
              f"({'live' if live else 'offline preview'}); cited as provenance: {losers}. "
              f"Originals untouched; prior version in git history. ([[distillation-not-reduction]])_\n\n")
    _atomic_write(out, header + (result.better_version or ""))

    log = STUDIUM / "_converged" / "converge-log.jsonl"
    rec = {"ts": str(date.today()), "idea": "studium-reading-arc", "shots": len(shots),
           "sources": [s.source for s in shots], "score": round(result.score, 3),
           "promoted": result.promoted, "cited_losers": [s.id for s in result.cited_losers],
           "gaps": result.next_shots[:20]}
    with open(log, "a") as f:
        f.write(json.dumps(rec) + "\n")

    print(f"studium-converge: consolidated {len(shots)} sources -> {out} "
          f"(score {result.score:.2f}, promoted={result.promoted}, {len(result.next_shots)} gaps) "
          f"[{'live' if live else 'offline'}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
