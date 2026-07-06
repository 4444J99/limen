#!/usr/bin/env python3
"""avtopoiesis.py — AVTOPOIESIS, the law that each door must be alive in its own existence.

NOT A SOLID. The door-list is DISCOVERED from the living heartbeat (never a hand-roster); the
rubric is DERIVED from spec/avtopoiesis/canon.yaml (retune there, the gate follows); the verdict
is REGENERATED every run (no stored scorecard to rot); and the gate INCLUDES ITSELF as a door —
it has its own heartbeat beat, so it is discovered like any other (operational closure). It reports
DISTANCE-FROM-IDEAL per tense, not a frozen stamp: the ideal form is approached, not reached.

Three tenses of aliveness (canon-tunable):
  PAST    — metabolizes its own history (its source regenerates state from the estate, not fed by hand)
  PRESENT — runs unbidden (wired to a heartbeat beat, not gated dormant)
  FUTURE  — self-evolves, asks less (carries no open his-hand lever of its own)
A door alive in all three needs nothing from his hand.

  python3 scripts/avtopoiesis.py            # AUDIT — score every door, report distance-from-ideal
  python3 scripts/avtopoiesis.py --strict   # PREDICATE — exit 1 if any door is below the alive threshold
  python3 scripts/avtopoiesis.py --json     # machine form (organ-health / dashboards)
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1])).expanduser().resolve()
SPEC = ROOT / "spec" / "avtopoiesis"
CANON = SPEC / "canon.yaml"
SCRIPTS = ROOT / "scripts"
DOC_PATH = ROOT / "docs" / "avtopoiesis.md"
LOG_PATH = ROOT / "logs" / "avtopoiesis.json"

try:
    import yaml
except ImportError:
    yaml = None


def _load(path):
    return yaml.safe_load(path.read_text()) or {}


def discover_doors(canon):
    """The living door-list — every heartbeat beat is a door. Read from the heartbeat, never a roster."""
    disc = canon.get("discovery") or {}
    loop = ROOT / disc.get("source", "scripts/heartbeat-loop.sh")
    text = loop.read_text() if loop.exists() else ""
    beat_re = re.compile(disc.get("beat_pattern", ""))
    gate_tmpl = disc.get("gate_pattern", "")
    doors = {}
    for m in beat_re.finditer(text):
        name, cadence, role = m.group(1), m.group(2), (m.group(3) or "").strip()
        key = name.lower()
        if key in doors:
            continue
        dormant = False
        if "%s" in gate_tmpl:
            dormant = bool(re.search(gate_tmpl % name, text))
        doors[key] = {"key": key, "name": name, "cadence": int(cadence),
                      "role": role, "dormant": dormant}
    return list(doors.values())


def _door_scripts(key):
    """The implementing script(s) for a door — found by name across scripts/ (derived, not a roster)."""
    variants = {key, key.replace("_", "-"), key.replace("_", "")}
    hits = []
    for p in sorted(SCRIPTS.glob("*.py")) + sorted(SCRIPTS.glob("*.sh")):
        stem = p.stem.lower()
        if stem in variants or any(v and v in stem for v in variants):
            hits.append(p)
    return hits


def sense_present(door, _canon):
    """Runs unbidden: discovered from a beat (so it is wired); half-alive if gated dormant by default."""
    return 0.5 if door["dormant"] else 1.0


def sense_past(door, canon):
    """Metabolizes its own history: does its source CRAWL/regenerate, or only read a hand-fed input?"""
    sigs = ((canon.get("senses") or {}).get("past") or {}).get("metabolize_signatures") or []
    for p in _door_scripts(door["key"]):
        try:
            body = p.read_text(errors="ignore")
        except OSError:
            continue
        if any(s in body for s in sigs):
            return 1.0
    return 0.0


def sense_future(door, canon):
    """Self-evolves, asks less: how many open his-hand levers does this door still own?"""
    fut = (canon.get("senses") or {}).get("future") or {}
    reg = ROOT / fut.get("his_hand_registry", "his-hand-levers.json")
    penalty = float(fut.get("penalty_per_lever", 0.5))
    if not reg.exists():
        return 1.0
    try:
        data = json.loads(reg.read_text())
    except (OSError, json.JSONDecodeError):
        return 1.0
    levers = data.get("levers") if isinstance(data, dict) else data
    needles = {door["key"], door["name"].lower()}
    owned = sum(1 for lv in (levers or []) if any(n in json.dumps(lv).lower() for n in needles))
    return max(0.0, 1.0 - owned * penalty)


SENSES = {"past": sense_past, "present": sense_present, "future": sense_future}


def primary_gap(tenses):
    tense, score = min(tenses.items(), key=lambda kv: (kv[1], kv[0]))
    return {"tense": tense, "gap": round(1.0 - float(score), 3)}


def score_door(door, canon):
    tenses = canon.get("tenses") or {}
    senses = {t: round(SENSES[t](door, canon), 3) for t in SENSES}
    total = sum(float(spec.get("weight", 0)) * senses.get(t, 0.0) for t, spec in tenses.items())
    return senses, round(total, 3)


def summarize(rows, threshold):
    total = len(rows)
    alive = sum(1 for r in rows if r["alive"])
    below = total - alive
    mean_score = round(sum(float(r["score"]) for r in rows) / total, 3) if total else 0.0
    tense_averages = {}
    for tense in SENSES:
        tense_averages[tense] = (
            round(sum(float(r["tenses"].get(tense, 0.0)) for r in rows) / total, 3)
            if total else 0.0
        )
    weakest_tense = min(tense_averages.items(), key=lambda kv: (kv[1], kv[0]))[0] if total else None
    below_by_primary_gap = {tense: 0 for tense in SENSES}
    for row in rows:
        if row["alive"]:
            continue
        tense = row["primary_gap"]["tense"]
        below_by_primary_gap[tense] = below_by_primary_gap.get(tense, 0) + 1
    return {
        "total": total,
        "alive": alive,
        "below": below,
        "alive_ratio": round(alive / total, 3) if total else 0.0,
        "mean_score": mean_score,
        "distance_from_ideal": round(1.0 - mean_score, 3),
        "threshold": threshold,
        "tense_averages": tense_averages,
        "weakest_tense": weakest_tense,
        "below_by_primary_gap": below_by_primary_gap,
    }


def build():
    canon = _load(CANON)
    threshold = float(canon.get("alive_threshold", 0.67))
    rows = []
    for d in discover_doors(canon):
        senses, total = score_door(d, canon)
        rows.append({
            **d,
            "tenses": senses,
            "score": total,
            "alive": total >= threshold,
            "primary_gap": primary_gap(senses),
        })
    rows.sort(key=lambda r: (r["score"], r["key"]))
    return {"threshold": threshold, "doors": rows, "summary": summarize(rows, threshold)}


def render_text(v):
    s = v["summary"]
    out = [f"AVTOPOIESIS — {s['alive']}/{s['total']} doors alive (score ≥ {v['threshold']}); "
           f"{s['below']} below the line",
           f"  mean score {s['mean_score']:.3f}; distance from ideal {s['distance_from_ideal']:.1%}; "
           f"weakest tense {s['weakest_tense']}",
           "  (past = metabolizes · present = runs unbidden · future = asks less)\n",
           f"  {'door':<15}{'past':>6}{'present':>8}{'future':>7}{'score':>7}  state"]
    for r in v["doors"]:
        t = r["tenses"]
        mark = "✓ alive" if r["alive"] else "✗ nota"
        out.append(f"  {r['key']:<15}{t['past']:>6.2f}{t['present']:>8.2f}{t['future']:>7.2f}"
                   f"{r['score']:>7.3f}  {mark}")
    return "\n".join(out)


def render_markdown(v):
    s = v["summary"]
    generated = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    lines = [
        "# AVTOPOIESIS",
        "",
        f"Generated: `{generated}`",
        "",
        "## How Far",
        "",
        f"- Alive doors: `{s['alive']}/{s['total']}` (`{s['alive_ratio']:.1%}`).",
        f"- Mean score: `{s['mean_score']:.3f}`.",
        f"- Distance from ideal: `{s['distance_from_ideal']:.1%}`.",
        f"- Weakest tense: `{s['weakest_tense']}`.",
        "- Below-threshold doors by primary gap: "
        + ", ".join(f"`{tense}` {count}" for tense, count in s["below_by_primary_gap"].items())
        + ".",
        "",
        "## Tense Averages",
        "",
        "| Tense | Average |",
        "|---|---:|",
    ]
    for tense, avg in s["tense_averages"].items():
        lines.append(f"| `{tense}` | `{avg:.3f}` |")

    lines += [
        "",
        "## Doors",
        "",
        "| Door | Past | Present | Future | Score | State | Primary gap |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for r in v["doors"]:
        t = r["tenses"]
        gap = r["primary_gap"]
        state = "alive" if r["alive"] else "nota"
        lines.append(
            f"| `{r['key']}` | `{t['past']:.2f}` | `{t['present']:.2f}` | "
            f"`{t['future']:.2f}` | `{r['score']:.3f}` | `{state}` | "
            f"`{gap['tense']}` `{gap['gap']:.3f}` |"
        )

    below = [r for r in v["doors"] if not r["alive"]]
    if below:
        lines += [
            "",
            "## Largest Gaps",
            "",
        ]
        for r in sorted(below, key=lambda row: (-row["primary_gap"]["gap"], row["key"]))[:10]:
            gap = r["primary_gap"]
            lines.append(
                f"- `{r['key']}`: score `{r['score']:.3f}`, primary gap `{gap['tense']}` "
                f"(`{gap['gap']:.3f}`)."
            )

    lines += [
        "",
        "## Commands",
        "",
        "- Audit: `python3 scripts/avtopoiesis.py`",
        "- Machine output: `python3 scripts/avtopoiesis.py --json`",
        "- Strict predicate: `python3 scripts/avtopoiesis.py --strict`",
        "- Refresh this receipt: `python3 scripts/avtopoiesis.py --write`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(v):
    DOC_PATH.write_text(render_markdown(v))
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(v, indent=2))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit AVTOPOIESIS door aliveness.")
    parser.add_argument("--json", action="store_true", help="print machine-readable audit JSON")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any door is below threshold")
    parser.add_argument("--write", action="store_true", help="write docs/avtopoiesis.md and ignored log JSON")
    args = parser.parse_args(argv)
    if yaml is None:
        print("avtopoiesis: PyYAML required", file=sys.stderr)
        return 1
    if not CANON.exists():
        print(f"avtopoiesis: no canon ({CANON}) — nothing to gate", file=sys.stderr)
        return 1
    v = build()
    if args.write:
        write_outputs(v)
    print(json.dumps(v, indent=2) if args.json else render_text(v))
    if args.write:
        print(f"avtopoiesis: wrote {DOC_PATH}")
    if args.strict and v["summary"]["below"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
