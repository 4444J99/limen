#!/usr/bin/env python3
"""check-decorum.py — the DECORVM registry+wiring drift predicate AND the offline egg-face gate.

Sibling of scripts/check-sensors.py / scripts/check-params.py: a deterministic, network-free
predicate wired into pr-gate so a surface-affecting diff cannot silently rot DECORVM or merge a
*provable* new egg-face. It splits responsibility correctly:

  - the continuous BEAT (scripts/decorum-keeper.py --sweep, sensor `decorum`) owns the
    network-dependent classes — visual/experience/links probes — which can't be a hard pre-merge
    gate (they need live surfaces, and the keeper is fail-open by law).
  - this GATE owns only the offline-provable egg-faces: the registry is valid, the keeper's own
    --doctor passes, the `decorum` sensor is declared, the voice-judgment register is well-formed,
    and — the actual prevention — no vendored misspelling exists in the tracked PUBLIC prose that
    DECORVM lints. That last check is what makes "a typo can't merge onto the front door" true at
    the source, not just caught after the fact by the beat.

Exit 0 ⟺ no drift and no offline egg-face. Run:  python3 scripts/check-decorum.py
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

# A GATE validates the checkout it runs in — NOT an ambient LIMEN_ROOT (which may point at a stale
# live checkout). Resolve script-relative like every sibling check-* gate, and pin the keeper we
# import / subprocess to the same tree so its ROOT-derived globs and --doctor read THIS checkout too.
ROOT = Path(__file__).resolve().parent.parent
os.environ["LIMEN_ROOT"] = str(ROOT)
REGISTRY = ROOT / "institutio" / "governance" / "decorum-surfaces.yaml"
SENSORS = ROOT / "institutio" / "governance" / "sensors.yaml"
JUDGMENTS = ROOT / "institutio" / "observatory" / "decorum-judgments.yaml"
KEEPER = ROOT / "scripts" / "decorum-keeper.py"

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a hard dep of the beat
    yaml = None

problems: list[str] = []
oks: list[str] = []


def _load_yaml(path: Path):
    if yaml is None or not path.exists():
        return None
    try:
        return yaml.safe_load(path.read_text()) or {}
    except Exception as e:  # noqa: BLE001
        problems.append(f"{path.relative_to(ROOT)} is unreadable: {e}")
        return None


def _keeper_module():
    """Import scripts/decorum-keeper.py (hyphenated filename) to reuse its spellcheck + prose globs."""
    try:
        spec = importlib.util.spec_from_file_location("decorum_keeper", KEEPER)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
        return mod
    except Exception as e:  # noqa: BLE001
        problems.append(f"cannot import decorum-keeper.py for offline lint: {e}")
        return None


def check_registry(reg) -> None:
    if not isinstance(reg, dict):
        problems.append("decorum-surfaces.yaml missing or not a mapping")
        return
    if reg.get("schema_version") != 1:
        problems.append("decorum-surfaces.yaml: schema_version must be 1")
    depts = reg.get("departments") or {}
    if not depts:
        problems.append("decorum-surfaces.yaml: no departments declared")
    for name, cfg in depts.items():
        if not isinstance(cfg, dict):
            problems.append(f"department '{name}' is not a mapping")
            continue
        if "artifact" not in cfg and "command" not in cfg:
            problems.append(f"department '{name}' has neither artifact nor command")
        if "severity" not in cfg:
            problems.append(f"department '{name}' missing severity")
        # a command department's referenced script must exist (offline-checkable)
        cmd = cfg.get("command")
        if cmd:
            for tok in cmd.split():
                if tok.startswith("scripts/") and not (ROOT / tok).exists():
                    problems.append(f"department '{name}': command references missing script {tok}")
        art = cfg.get("artifact")
        if art:
            if Path(art).is_absolute() or art.startswith(".."):
                problems.append(f"department '{name}': artifact path must be repo-relative, got {art}")
    order = ((reg.get("verdict") or {}).get("severity_order")) or []
    floor = (reg.get("verdict") or {}).get("floor")
    if floor not in order:
        problems.append(f"verdict.floor '{floor}' not in severity_order {order}")
    if depts:
        oks.append(f"registry: {len(depts)} departments, floor={floor}, all addressable")


def check_doctor() -> None:
    try:
        p = subprocess.run([sys.executable, str(KEEPER), "--doctor"],
                           capture_output=True, text=True, cwd=str(ROOT), timeout=60)
    except Exception as e:  # noqa: BLE001
        problems.append(f"decorum-keeper --doctor could not run: {e}")
        return
    if p.returncode != 0:
        problems.append(f"decorum-keeper --doctor failed: {p.stdout.strip() or p.stderr.strip()}")
    else:
        oks.append("keeper --doctor: OK")


def check_sensor() -> None:
    data = _load_yaml(SENSORS)
    if data is None:
        return
    sensors = data.get("sensors") or data
    entry = sensors.get("decorum") if isinstance(sensors, dict) else None
    if not entry:
        problems.append("sensors.yaml: no `decorum` sensor declared (the keeper is not beat-wired)")
        return
    if entry.get("gate") != "LIMEN_DECORUM":
        problems.append(f"decorum sensor gate must be LIMEN_DECORUM, got {entry.get('gate')}")
    steps = entry.get("steps") or []
    blob = str(steps)
    if "decorum-keeper.py" not in blob:
        problems.append("decorum sensor steps do not invoke scripts/decorum-keeper.py")
    else:
        oks.append("sensor: `decorum` declared, gate LIMEN_DECORUM, invokes the keeper")


def check_judgments() -> None:
    data = _load_yaml(JUDGMENTS)
    if data is None:
        problems.append("decorum-judgments.yaml missing (the voice-judgment register)")
        return
    if data.get("schema_version") != 1:
        problems.append("decorum-judgments.yaml: schema_version must be 1")
    j = data.get("judgments")
    if not isinstance(j, dict):
        problems.append("decorum-judgments.yaml: `judgments` must be a mapping (path → rows)")
        return
    # every row must pin the exact bytes it judged (content_sha256) — else the judgment can't be invalidated on edit
    for surface, rows in j.items():
        for row in rows or []:
            if not isinstance(row, dict) or "content_sha256" not in row:
                problems.append(f"judgment for '{surface}' missing content_sha256 (unpinned verdict)")
                break
    oks.append(f"judgments: well-formed ({len(j)} surface(s) on record)")


def check_offline_egg_face(reg) -> None:
    """The prevention: no vendored misspelling in the tracked PUBLIC prose DECORVM lints.
    A new typo on a public README/positioning doc cannot merge — the beat would only catch it after."""
    mod = _keeper_module()
    if mod is None or not isinstance(reg, dict):
        return
    pol = reg.get("polish") or {}
    try:
        files = mod._prose_files(pol)  # reuse the keeper's own glob/exclude discipline
    except Exception as e:  # noqa: BLE001
        problems.append(f"could not enumerate prose files: {e}")
        return
    hits_total = 0
    for rel, path in files:
        try:
            for word, fix, ln in mod._spellcheck(path.read_text(errors="ignore")):
                problems.append(f"public prose egg-face: misspelling '{word}' → '{fix}' ({rel}:{ln})")
                hits_total += 1
        except Exception:
            continue
    if hits_total == 0:
        oks.append(f"offline lint: {len(files)} public prose file(s) clean (no vendored misspelling)")


def check_off_platform(reg) -> None:
    """If an off-platform surface needs a human capture, it must be homed as a lever — never a chat ask."""
    if not isinstance(reg, dict):
        return
    off = reg.get("off_platform") or {}
    if not off:
        return
    levers = _load_yaml(ROOT / "his-hand-levers.json")  # json loads as yaml too
    lever_blob = str(levers) if levers else ""
    for name, cfg in off.items() if isinstance(off, dict) else []:
        if isinstance(cfg, dict) and cfg.get("capture") == "human":
            lever = cfg.get("lever")
            if not lever:
                problems.append(f"off_platform '{name}' needs human capture but declares no `lever:`")
            elif lever not in lever_blob:
                problems.append(f"off_platform '{name}' lever '{lever}' not found in his-hand-levers.json")
    oks.append(f"off_platform: {len(off)} slot(s), human-capture atoms homed as levers")


def main() -> int:
    reg = _load_yaml(REGISTRY)
    check_registry(reg)
    check_doctor()
    check_sensor()
    check_judgments()
    check_offline_egg_face(reg)
    check_off_platform(reg)

    if problems:
        print("check-decorum: FAIL")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("check-decorum: OK")
    for o in oks:
        print(f"  ✓ {o}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
