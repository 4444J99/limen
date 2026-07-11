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
ORGAN_HEALTH_PATH = ROOT / "logs" / "organ-health.json"

try:
    import yaml
except ImportError:
    yaml = None


def _load(path):
    return yaml.safe_load(path.read_text()) or {}


def discover_doors(canon):
    """The living door-list — shell beats plus scheduled registry sensors, never a roster."""
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
        doors[key] = {"key": key, "name": name, "cadence": int(cadence), "role": role, "dormant": dormant}
    if re.search(r"beat-sensors\.py[^\n]*--source\s+heartbeat[^\n]*--scheduled-only", text):
        sensors_path = ROOT / "institutio" / "governance" / "sensors.yaml"
        try:
            sensors = (_load(sensors_path).get("sensors") or {}) if yaml is not None else {}
        except OSError:
            sensors = {}
        derive_match = re.search(r"LIMEN_BEAT_DERIVE:-(\d+)", text)
        derive_default = derive_match.group(1) if derive_match else "0"
        derive_live = os.environ.get("LIMEN_BEAT_DERIVE", derive_default) == "1"
        for sensor_id, sensor in sensors.items():
            if sensor_id in doors or "heartbeat" not in (sensor.get("source") or []):
                continue
            cadence_spec = sensor.get("cadence")
            if cadence_spec is None:
                continue
            if isinstance(cadence_spec, dict):
                cadence_value = os.environ.get(str(cadence_spec.get("env") or ""), str(cadence_spec.get("default", "")))
                cadence_default = cadence_spec.get("default")
            else:
                cadence_value = cadence_spec
                cadence_default = cadence_spec
            try:
                cadence = int(cadence_value)
            except (TypeError, ValueError):
                try:
                    cadence = int(cadence_default)
                except (TypeError, ValueError):
                    continue
            if cadence <= 0:
                continue
            gate_default = str(sensor.get("default", "1"))
            doors[sensor_id] = {
                "key": sensor_id,
                "name": sensor_id.upper().replace("-", "_").replace(".", "_"),
                "cadence": cadence,
                "role": str(sensor.get("title") or f"{sensor_id} sensor"),
                "dormant": (not derive_live) or bool(sensor.get("gate") and gate_default == "0"),
                "registry_sensor": True,
            }
    return list(doors.values())


def _script_path_refs(text):
    refs = []
    scripts_root = ROOT / "scripts"
    for rel in re.findall(r"(?:\$LIMEN_ROOT/)?scripts/([^\"'\s;)]+)", text):
        path = (scripts_root / rel).resolve()
        try:
            path.relative_to(scripts_root.resolve())
        except ValueError:
            continue
        if path.exists() and path.is_file():
            refs.append(path)
    return refs


def _heartbeat_command_block(lines, index):
    """Return the shell command block around a beat invocation."""
    block = [lines[index]]
    stripped = lines[index].strip()
    if stripped.startswith("if ") or stripped.endswith("then"):
        for line in lines[index + 1 : index + 40]:
            block.append(line)
            if line.strip() == "fi":
                break
        return "\n".join(block)

    brace_depth = lines[index].count("{") - lines[index].count("}")
    cursor = index
    while cursor + 1 < len(lines) and (lines[cursor].rstrip().endswith("\\") or brace_depth > 0):
        cursor += 1
        block.append(lines[cursor])
        brace_depth += lines[cursor].count("{") - lines[cursor].count("}")
        if cursor - index >= 30:
            break
    return "\n".join(block)


def _heartbeat_scripts_for(key):
    source = ROOT / "scripts" / "heartbeat-loop.sh"
    try:
        lines = source.read_text(errors="ignore").splitlines()
    except OSError:
        return []
    upper = key.upper()
    markers = (f"$C_{upper}", f"due_voice {key}", f'play "$C_{upper}"')
    hits = []
    for index, line in enumerate(lines):
        if not any(marker in line for marker in markers):
            continue
        hits.extend(_script_path_refs(_heartbeat_command_block(lines, index)))
    return hits


def _sensor_scripts_for(key):
    """Resolve an arbitrary scheduled sensor id to its declared implementation."""
    try:
        sensors = _load(ROOT / "institutio" / "governance" / "sensors.yaml").get("sensors") or {}
    except OSError:
        return []
    sensor = sensors.get(key)
    if not isinstance(sensor, dict):
        return []
    hits = []
    for step in sensor.get("steps") or []:
        hits.extend(_script_path_refs(str(step.get("command") or "")))
    return hits


def _door_scripts(key):
    """The implementing script(s) for a door — resolved from heartbeat, then by name fallback."""
    variants = {key, key.replace("_", "-"), key.replace("_", "")}
    hits = _heartbeat_scripts_for(key) + _sensor_scripts_for(key)
    scripts_root = ROOT / "scripts"
    for p in sorted(scripts_root.glob("*.py")) + sorted(scripts_root.glob("*.sh")):
        stem = p.stem.lower()
        if stem in variants or any(v and (stem.startswith(f"{v}-") or stem.startswith(f"{v}_")) for v in variants):
            hits.append(p)
    out = []
    seen = set()
    for path in hits:
        key_path = str(path)
        if key_path in seen:
            continue
        seen.add(key_path)
        out.append(path)
    return out


_ORGAN_HEALTH_CACHE = None


def _organ_health():
    """Latest proprioception snapshot, if available. Fail open to the heartbeat-derived fallback."""
    global _ORGAN_HEALTH_CACHE
    if _ORGAN_HEALTH_CACHE is not None:
        return _ORGAN_HEALTH_CACHE
    try:
        data = json.loads(ORGAN_HEALTH_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        data = {}
    organs = data.get("organs") if isinstance(data, dict) else None
    if not isinstance(organs, list):
        _ORGAN_HEALTH_CACHE = {}
        return _ORGAN_HEALTH_CACHE
    by_key = {}
    for item in organs:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").lower()
        if key:
            by_key[key] = item
    _ORGAN_HEALTH_CACHE = by_key
    return by_key


def _present_from_organ_health(key):
    entry = _organ_health().get(key)
    if not entry:
        return None
    status = str(entry.get("status") or "").lower()
    if status == "green":
        return 1.0
    if status == "down":
        return 0.0
    if status in {"gated", "stale", "unknown"}:
        return 0.5
    return None


def assess_past(door, canon):
    """Metabolizes its own history: redacted proof from source paths and configured signatures."""
    sigs = ((canon.get("senses") or {}).get("past") or {}).get("metabolize_signatures") or []
    scripts = []
    for p in _door_scripts(door["key"]):
        try:
            body = p.read_text(errors="ignore")
        except OSError:
            continue
        matches = [s for s in sigs if s in body]
        scripts.append({"path": str(p.relative_to(ROOT)), "signatures": matches})
    matched = [script for script in scripts if script["signatures"]]
    return {
        "score": 1.0 if matched else 0.0,
        "source": "script-signature",
        "reason": "metabolizes-history" if matched else "missing-metabolize-signature",
        "scripts": scripts,
    }


def sense_past(door, canon):
    return float(assess_past(door, canon)["score"])


def assess_present(door, _canon):
    """Runs unbidden: redacted liveness source and score."""
    entry = _organ_health().get(door["key"])
    if entry:
        status = str(entry.get("status") or "").lower()
        sensed = _present_from_organ_health(door["key"])
        if sensed is not None:
            return {
                "score": sensed,
                "source": "logs/organ-health.json",
                "reason": status or "unknown",
                "dormant": bool(door["dormant"]),
            }
    score = 0.5 if door["dormant"] else 1.0
    return {
        "score": score,
        "source": "heartbeat-wiring",
        "reason": "dormant" if door["dormant"] else "wired",
        "dormant": bool(door["dormant"]),
    }


def sense_present(door, canon):
    return float(assess_present(door, canon)["score"])


def _normalized_door_values(value):
    if value is None:
        return set()
    if isinstance(value, str):
        return {value.lower().replace("-", "_").strip()} if value.strip() else set()
    if isinstance(value, list):
        out = set()
        for item in value:
            out.update(_normalized_door_values(item))
        return out
    return set()


def _declared_lever_doors(lever):
    out = set()
    for key in ("door", "doors", "organ", "organs"):
        out.update(_normalized_door_values(lever.get(key) if isinstance(lever, dict) else None))
    return out


def _lever_tokens(lever):
    text = json.dumps(lever).lower()
    return {token.replace("-", "_") for token in re.findall(r"[a-z0-9_]+", text)}


def lever_mentions_door(lever, door):
    needles = {door["key"].lower().replace("-", "_"), door["name"].lower().replace("-", "_")}
    declared = _declared_lever_doors(lever)
    if declared:
        return bool(needles & declared)
    return bool(needles & _lever_tokens(lever))


def assess_future(door, canon):
    """Self-evolves, asks less: counts-only his-hand ownership proof."""
    fut = (canon.get("senses") or {}).get("future") or {}
    reg = ROOT / fut.get("his_hand_registry", "his-hand-levers.json")
    penalty = float(fut.get("penalty_per_lever", 0.5))
    if not reg.exists():
        return {
            "score": 1.0,
            "source": str(reg.relative_to(ROOT)),
            "reason": "registry-missing",
            "open_levers": 0,
            "penalty_per_lever": penalty,
        }
    try:
        data = json.loads(reg.read_text())
    except (OSError, json.JSONDecodeError):
        return {
            "score": 1.0,
            "source": str(reg.relative_to(ROOT)),
            "reason": "registry-unreadable",
            "open_levers": 0,
            "penalty_per_lever": penalty,
        }
    levers = data.get("levers") if isinstance(data, dict) else data
    owned = sum(1 for lv in (levers or []) if lever_mentions_door(lv, door))
    return {
        "score": max(0.0, 1.0 - owned * penalty),
        "source": str(reg.relative_to(ROOT)),
        "reason": "counts-only-open-levers",
        "open_levers": owned,
        "penalty_per_lever": penalty,
    }


def sense_future(door, canon):
    return float(assess_future(door, canon)["score"])


SENSES = {"past": sense_past, "present": sense_present, "future": sense_future}
ASSESSORS = {"past": assess_past, "present": assess_present, "future": assess_future}


def primary_gap(tenses):
    tense, score = min(tenses.items(), key=lambda kv: (kv[1], kv[0]))
    return {"tense": tense, "gap": round(1.0 - float(score), 3)}


def score_door(door, canon):
    tenses = canon.get("tenses") or {}
    evidence = {t: ASSESSORS[t](door, canon) for t in ASSESSORS}
    senses = {t: round(float(evidence[t].get("score", 0.0)), 3) for t in SENSES}
    total = sum(float(spec.get("weight", 0)) * senses.get(t, 0.0) for t, spec in tenses.items())
    return senses, round(total, 3), evidence


def summarize(rows, threshold):
    total = len(rows)
    alive = sum(1 for r in rows if r["alive"])
    below = total - alive
    mean_score = round(sum(float(r["score"]) for r in rows) / total, 3) if total else 0.0
    tense_averages = {}
    for tense in SENSES:
        tense_averages[tense] = (
            round(sum(float(r["tenses"].get(tense, 0.0)) for r in rows) / total, 3) if total else 0.0
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
        senses, total, evidence = score_door(d, canon)
        rows.append(
            {
                **d,
                "tenses": senses,
                "evidence": evidence,
                "score": total,
                "alive": total >= threshold,
                "primary_gap": primary_gap(senses),
            }
        )
    rows.sort(key=lambda r: (r["score"], r["key"]))
    return {"threshold": threshold, "doors": rows, "summary": summarize(rows, threshold)}


def render_text(v):
    s = v["summary"]
    out = [
        f"AVTOPOIESIS — {s['alive']}/{s['total']} doors alive (score ≥ {v['threshold']}); {s['below']} below the line",
        f"  mean score {s['mean_score']:.3f}; distance from ideal {s['distance_from_ideal']:.1%}; "
        f"weakest tense {s['weakest_tense']}",
        "  (past = metabolizes · present = runs unbidden · future = asks less)\n",
        f"  {'door':<15}{'past':>6}{'present':>8}{'future':>7}{'score':>7}  state",
    ]
    for r in v["doors"]:
        t = r["tenses"]
        mark = "✓ alive" if r["alive"] else "✗ nota"
        out.append(
            f"  {r['key']:<15}{t['past']:>6.2f}{t['present']:>8.2f}{t['future']:>7.2f}{r['score']:>7.3f}  {mark}"
        )
    return "\n".join(out)


def _evidence_summary(row, tense):
    evidence = row.get("evidence", {}).get(tense, {})
    if tense == "past":
        matched = [
            f"{Path(script['path']).name}:{','.join(script.get('signatures') or [])}"
            for script in evidence.get("scripts", [])
            if script.get("signatures")
        ]
        if matched:
            return "matched " + "; ".join(matched[:3])
        scripts = [Path(script["path"]).name for script in evidence.get("scripts", []) if script.get("path")]
        if scripts:
            return "missing metabolize signature in " + ", ".join(scripts[:3])
        return "no implementing script found"
    if tense == "present":
        return f"{evidence.get('source', 'unknown')}:{evidence.get('reason', 'unknown')}"
    if tense == "future":
        return f"{evidence.get('open_levers', 0)} open his-hand levers from {evidence.get('source', 'unknown')}"
    return str(evidence.get("reason") or "unknown")


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
        "- Present tense source: `logs/organ-health.json` when available; heartbeat wiring fallback otherwise.",
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
                f"- `{r['key']}`: score `{r['score']:.3f}`, primary gap `{gap['tense']}` (`{gap['gap']:.3f}`)."
            )

    lines += [
        "",
        "## Evidence",
        "",
        "Evidence is redacted metadata only: paths, configured signatures, liveness status, and counts.",
        "",
        "| Door | Past evidence | Present evidence | Future evidence |",
        "|---|---|---|---|",
    ]
    for r in v["doors"]:
        lines.append(
            f"| `{r['key']}` | {_evidence_summary(r, 'past')} | "
            f"{_evidence_summary(r, 'present')} | {_evidence_summary(r, 'future')} |"
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
