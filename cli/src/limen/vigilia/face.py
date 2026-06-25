"""The face — one read-only pane onto the seat (CCO).

Renders the C-suite from ``institutio/registry/organs.yaml`` (the ``officers`` map
+ the ``organs``) overlaid with the live autonomic status (``logs/vigilia/status.json``).
The officer list is DERIVED from the seat — nothing here hardcodes who the officers
are, so the pane stays correct as the institution grows. Read-only; fail-open.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml

from . import params

_GLYPH = {"built": "●", "partial": "◐", "missing": "○"}


def _seat_path() -> Path | None:
    root = params._repo_root()
    return root / "institutio" / "registry" / "organs.yaml" if root else None


def load_seat() -> dict:
    path = _seat_path()
    if not path or not path.exists():
        return {"organs": [], "officers": {}}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except Exception:
        return {"organs": [], "officers": {}}
    return {"organs": data.get("organs") or [], "officers": data.get("officers") or {}}


def _live_overlay() -> dict:
    """organ name -> a short live-status string from logs/vigilia/status.json."""
    root = params._repo_root() or Path(".")
    sp = root / "logs" / "vigilia" / "status.json"
    overlay: dict[str, str] = {}
    try:
        data = json.loads(sp.read_text())
    except Exception:
        return overlay
    v = data.get("vitals") or {}
    if "level" in v:
        overlay["vitals"] = f"L{v.get('level')}/{v.get('action', '?')}"
    c = data.get("continuity") or {}
    if c.get("status"):
        overlay["continuity"] = str(c["status"])
    i = data.get("integrity") or {}
    if i.get("status"):
        overlay["integrity"] = str(i["status"]) + ("/DRIFT" if i.get("drift") else "")
    return overlay


def render() -> str:
    seat = load_seat()
    organs = {o["name"]: o for o in seat["organs"] if isinstance(o, dict) and o.get("name")}
    officers = seat["officers"]
    overlay = _live_overlay()
    nomen = params.get("INSTITVTIO_NOMEN", "VIGILIA")

    lines = [f"{nomen} — the C-suite (read-only)"]
    if not officers:
        lines.append("  (no officers declared in the seat)")
        return "\n".join(lines)

    total = sum(len(info.get("organs", []) or []) for info in officers.values())
    built = sum(
        1
        for info in officers.values()
        for n in (info.get("organs", []) or [])
        if organs.get(n, {}).get("status") == "built"
    )
    lines.append(f"  {built}/{total} organs built\n")

    for officer, info in officers.items():
        lines.append(f"┌─ {officer} — {info.get('mandate', '')}")
        for name in info.get("organs", []) or []:
            o = organs.get(name, {})
            status = o.get("status", "?")
            glyph = _GLYPH.get(status, "·")
            live = overlay.get(name)
            live_s = f"  [{live}]" if live else ""
            lines.append(f"│   {glyph} {name:<16} {status:<8}{live_s}")
        lines.append("│")

    placed = {n for info in officers.values() for n in (info.get("organs", []) or [])}
    orphans = [n for n in organs if n not in placed]
    if orphans:
        lines.append(f"└─ (unassigned organs: {', '.join(orphans)})")
    return "\n".join(lines).rstrip()
