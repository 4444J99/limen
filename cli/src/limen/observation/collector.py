"""Observation Organ Telemetry Collector.

Unified telemetry collector combining:
1. System vitals (via limen.vigilia.vitals)
2. Bifrons star <-> contribution portal counts (via scripts/bifrons-organ.py)
3. Observatory legibility & traction metrics (via limen.observatory)

Emits records conforming to schema `limen.observation.feed.v1`.
"""

from __future__ import annotations

import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from limen.vigilia import params

SCHEMA_V1 = "limen.observation.feed.v1"


def _repo_root() -> Path:
    """Resolve repo root from environment or params."""
    root = params._repo_root()
    if root:
        return root
    return Path(os.environ.get("LIMEN_ROOT", ".")).expanduser().resolve()


def collect_vitals() -> dict[str, Any]:
    """Collect live system vitals via limen.vigilia.vitals.beat_gate(shed=False)."""
    try:
        from limen.vigilia import vitals

        gate = vitals.beat_gate(shed=False)
        return {
            "level": int(gate.get("level", 1)),
            "action": str(gate.get("action", "ok")),
            "load_per_core": float(gate.get("load_per_core", 0.0)),
            "swap_used_gib": gate.get("swap_used_gib"),
            "ram_gib": gate.get("ram_gib"),
            "status": "ok",
        }
    except Exception as exc:
        return {
            "level": 1,
            "action": "ok",
            "load_per_core": 0.0,
            "swap_used_gib": None,
            "ram_gib": None,
            "status": f"degraded: {exc}",
        }


def collect_bifrons(root: Path | None = None) -> dict[str, Any]:
    """Collect Bifrons star<->contribution portal counts."""
    repo_root = (root or _repo_root()).resolve()
    script_path = repo_root / "scripts" / "bifrons-organ.py"
    if script_path.exists():
        try:
            spec = importlib.util.spec_from_file_location("bifrons_organ_collector", script_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                res = mod.portal_counts()
                counts = res.get("counts", {})
                by_state = res.get("by_state", {})
                awaiting = sum(by_state.get(s, 0) for s in ("PATCH_PREPARED", "HUMAN_APPROVED"))
                return {
                    "stars": int(res.get("exchange_rows", 0)),
                    "dossiers": int(counts.get("dossier", 0)),
                    "resonance_edges": int(counts.get("resonance_edge", 0)),
                    "awaiting_gate": int(awaiting),
                    "status": str(res.get("status", "present" if res.get("present") else "absent")),
                }
        except Exception as exc:
            return {
                "stars": 0,
                "dossiers": 0,
                "resonance_edges": 0,
                "awaiting_gate": 0,
                "status": f"degraded: {exc}",
            }
    return {
        "stars": 0,
        "dossiers": 0,
        "resonance_edges": 0,
        "awaiting_gate": 0,
        "status": "absent",
    }


def collect_observatory(root: Path | None = None) -> dict[str, Any]:
    """Collect Observatory legibility metrics."""
    try:
        from limen.observatory import brief, config

        latest_brief = brief.config_latest("brief-latest.json")
        external_gaps = len(brief._external_gaps())
        internal_gaps = len(brief._internal_gaps())

        hero: str | None = None
        if latest_brief and isinstance(latest_brief, dict) and latest_brief.get("hero"):
            hero = str(latest_brief["hero"])
        else:
            val_repos = config.value_repos()
            if val_repos:
                hero = str(val_repos[0])

        top_mech: str | None = None
        if latest_brief and isinstance(latest_brief, dict) and latest_brief.get("mechanisms"):
            mechs = latest_brief["mechanisms"]
            if mechs and isinstance(mechs, list) and isinstance(mechs[0], dict):
                top_mech = str(mechs[0].get("mechanism") or "")

        if not top_mech:
            top_mechs = brief._top_mechanisms(1)
            if top_mechs and isinstance(top_mechs[0], dict) and top_mechs[0].get("mechanism"):
                top_mech = str(top_mechs[0]["mechanism"])

        return {
            "hero": hero,
            "external_gaps": external_gaps,
            "internal_gaps": internal_gaps,
            "top_mechanism": top_mech if top_mech else None,
            "status": "ok",
        }
    except Exception as exc:
        return {
            "hero": None,
            "external_gaps": 0,
            "internal_gaps": 0,
            "top_mechanism": None,
            "status": f"degraded: {exc}",
        }


def determine_status(vitals_data: dict[str, Any], bifrons_data: dict[str, Any], obs_data: dict[str, Any]) -> str:
    """Compute composite status across collectors ('ok' | 'degraded' | 'shed')."""
    v_action = vitals_data.get("action", "ok")
    if v_action == "shed":
        return "shed"
    if v_action == "throttle":
        return "degraded"
    if "degraded" in str(vitals_data.get("status", "")) or "degraded" in str(obs_data.get("status", "")):
        return "degraded"
    return "ok"


def build_feed_record(source: str = "composite", root: Path | None = None) -> dict[str, Any]:
    """Assemble a single schema-valid observation feed record."""
    vitals_data = collect_vitals()
    bifrons_data = collect_bifrons(root)
    obs_data = collect_observatory(root)
    status = determine_status(vitals_data, bifrons_data, obs_data)

    return {
        "schema": SCHEMA_V1,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "vitals": {
            "level": vitals_data["level"],
            "action": vitals_data["action"],
            "load_per_core": vitals_data["load_per_core"],
            "swap_used_gib": vitals_data["swap_used_gib"],
            "ram_gib": vitals_data["ram_gib"],
        },
        "bifrons": {
            "stars": bifrons_data["stars"],
            "dossiers": bifrons_data["dossiers"],
            "resonance_edges": bifrons_data["resonance_edges"],
            "awaiting_gate": bifrons_data["awaiting_gate"],
        },
        "observatory": {
            "hero": obs_data["hero"],
            "external_gaps": obs_data["external_gaps"],
            "internal_gaps": obs_data["internal_gaps"],
            "top_mechanism": obs_data["top_mechanism"],
        },
        "status": status,
    }


def validate_feed_record(record: Any) -> list[str]:
    """Validate a dictionary against the `limen.observation.feed.v1` schema.

    Returns a list of violation messages (empty list if valid).
    """
    violations: list[str] = []
    if not isinstance(record, dict):
        return ["record is not a dict"]

    if record.get("schema") != SCHEMA_V1:
        violations.append(f"invalid schema: {record.get('schema')!r}, expected {SCHEMA_V1!r}")

    observed_at = record.get("observed_at")
    if not isinstance(observed_at, str):
        violations.append("observed_at must be an ISO-8601 string")
    else:
        try:
            datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        except Exception:
            violations.append(f"observed_at {observed_at!r} is not a valid ISO-8601 timestamp")

    source = record.get("source")
    if not isinstance(source, str) or not source.strip():
        violations.append("source must be a non-empty string")

    status = record.get("status")
    if status not in ("ok", "degraded", "shed"):
        violations.append(f"status {status!r} must be one of ('ok', 'degraded', 'shed')")

    vitals = record.get("vitals")
    if not isinstance(vitals, dict):
        violations.append("vitals must be a dict")
    else:
        if not isinstance(vitals.get("level"), int):
            violations.append("vitals.level must be an int")
        if vitals.get("action") not in ("ok", "throttle", "shed"):
            violations.append(f"vitals.action {vitals.get('action')!r} must be one of ('ok', 'throttle', 'shed')")
        if not isinstance(vitals.get("load_per_core"), (int, float)):
            violations.append("vitals.load_per_core must be a number")
        if vitals.get("swap_used_gib") is not None and not isinstance(vitals.get("swap_used_gib"), (int, float)):
            violations.append("vitals.swap_used_gib must be a number or null")
        if vitals.get("ram_gib") is not None and not isinstance(vitals.get("ram_gib"), (int, float)):
            violations.append("vitals.ram_gib must be a number or null")

    bifrons = record.get("bifrons")
    if not isinstance(bifrons, dict):
        violations.append("bifrons must be a dict")
    else:
        for key in ("stars", "dossiers", "resonance_edges", "awaiting_gate"):
            val = bifrons.get(key)
            if not isinstance(val, int) or val < 0:
                violations.append(f"bifrons.{key} must be a non-negative int")

    obs = record.get("observatory")
    if not isinstance(obs, dict):
        violations.append("observatory must be a dict")
    else:
        hero = obs.get("hero")
        if hero is not None and not isinstance(hero, str):
            violations.append("observatory.hero must be a string or null")
        for key in ("external_gaps", "internal_gaps"):
            val = obs.get(key)
            if not isinstance(val, int) or val < 0:
                violations.append(f"observatory.{key} must be a non-negative int")
        mech = obs.get("top_mechanism")
        if mech is not None and not isinstance(mech, str):
            violations.append("observatory.top_mechanism must be a string or null")

    return violations


def emit_feed_record(
    record: dict[str, Any] | None = None, base_dir: Path | None = None
) -> tuple[dict[str, Any], Path, Path]:
    """Emit an observation record to `logs/observation/feed.jsonl` and `feed-latest.json`.

    Returns (record, jsonl_path, latest_path).
    """
    root = (base_dir or _repo_root()).resolve()
    log_dir = root / "logs" / "observation"
    log_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = log_dir / "feed.jsonl"
    latest_path = log_dir / "feed-latest.json"

    if record is None:
        record = build_feed_record(root=root)

    violations = validate_feed_record(record)
    if violations:
        raise ValueError(f"Invalid observation feed record: {'; '.join(violations)}")

    # Append to JSONL feed
    with open(jsonl_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    # Update latest pointer
    latest_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")

    return record, jsonl_path, latest_path


def check_feed(base_dir: Path | None = None) -> tuple[bool, list[str]]:
    """Validate that the feed files exist and all records adhere to the schema.

    Returns (is_valid, list_of_errors).
    """
    root = (base_dir or _repo_root()).resolve()
    log_dir = root / "logs" / "observation"
    jsonl_path = log_dir / "feed.jsonl"
    latest_path = log_dir / "feed-latest.json"

    if not latest_path.exists() or not jsonl_path.exists():
        emit_feed_record(base_dir=root)

    errors: list[str] = []
    if not latest_path.exists():
        errors.append(f"missing feed-latest.json at {latest_path}")
    else:
        try:
            data = json.loads(latest_path.read_text(encoding="utf-8"))
            errs = validate_feed_record(data)
            if errs:
                errors.extend([f"feed-latest.json: {e}" for e in errs])
        except Exception as exc:
            errors.append(f"feed-latest.json is unreadable: {exc}")

    if not jsonl_path.exists():
        errors.append(f"missing feed.jsonl at {jsonl_path}")
    else:
        try:
            content = jsonl_path.read_text(encoding="utf-8")
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            if not lines:
                errors.append("feed.jsonl is empty")
            else:
                for idx, line in enumerate(lines, 1):
                    try:
                        item = json.loads(line)
                        errs = validate_feed_record(item)
                        if errs:
                            errors.extend([f"feed.jsonl line {idx}: {e}" for e in errs])
                    except Exception as exc:
                        errors.append(f"feed.jsonl line {idx} parse error: {exc}")
        except Exception as exc:
            errors.append(f"feed.jsonl is unreadable: {exc}")

    return len(errors) == 0, errors
