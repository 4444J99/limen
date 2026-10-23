"""Shared reader for the SCHEDULES registry (institutio/governance/schedules.yaml).

One definition of what a job IS — declared rows plus the rows DERIVED from limen's own source files
(.github/workflows cron triggers, sensors.yaml cadence blocks, cloud-routines.json + the newest
claude-triggers snapshot receipt) — so check-schedules.py (the pr-gate parity predicate) and
schedule-utilization.py (the beat sensor) cannot disagree about the estate they measure.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

REGISTRY_REL = Path("institutio/governance/schedules.yaml")
BASELINE_REL = Path("institutio/governance/schedule-stagger-baseline.txt")
SENSORS_REL = Path("institutio/governance/sensors.yaml")
CLOUD_ROUTINES_REL = Path("cloud-routines.json")
WORKFLOWS_REL = Path(".github/workflows")
SNAPSHOT_GLOB = "docs/receipts/claude-triggers-snapshot-*.json"
# A sensor `cadence` is counted in BEATS (beat-sensors.py `_due`: `beat % cadence == 0`, or stamp age ≥
# cadence × loop_max). The beat is adaptive (LIMEN_LOOP_MIN…LIMEN_LOOP_MAX seconds), so the only wall-clock
# bound a cadence carries is its WORST case: cadence × LIMEN_LOOP_MAX. `cadence: 48` is 24h at the default
# 1,800s ceiling — a daily sensor — never "48 hours".
BEAT_LOOP_MAX_SECONDS = 1800
SECONDS_PER_HOUR = 3600

PLANE_SURFACES = {"cron", "launchd", "ui", "ui+api", "api"}
PLANE_WINDOWS = {"calendar-day", "rolling-24h", "per-hour", "active-tasks", "per-beat"}
PLANE_ENTITLEMENTS = {"verified", "unverified", "unpublished"}
PLANE_FILL_POLICIES = {"declared", "floor", "idle-by-design"}
EVIDENCE_KINDS = {
    "gh-actions-runs",
    "bookend-tsv",
    "witness-audit",
    "voice-stamps",
    "claude-snapshot",
    "board-dispatch-receipts",
    "issue-comments",
    "none",
}
JOBS_SOURCE_KINDS = {"workflows", "sensors", "cloud-routines"}
JOB_CLASSES = {"report", "keepalive", "witness", "dispatch", "landing", "ingest", "audit", "unknown"}
STAGGER_RULES = ("on-the-hour", "shared-minute")

_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


class CronError(ValueError):
    """A cron string this registry refuses (names, L/W/?, wrong arity, out-of-range values)."""


def _expand_field(spec: str, lo: int, hi: int) -> set[int]:
    values: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"empty list element in {spec!r}")
        step = 1
        if "/" in part:
            part, step_s = part.split("/", 1)
            if not step_s.isdigit() or int(step_s) < 1:
                raise CronError(f"bad step in {spec!r}")
            step = int(step_s)
        if part == "*":
            start, end = lo, hi
        elif "-" in part:
            a, b = part.split("-", 1)
            if not (a.isdigit() and b.isdigit()):
                raise CronError(f"bad range in {spec!r}")
            start, end = int(a), int(b)
        elif part.isdigit():
            start = end = int(part)
            if step != 1:
                end = hi
        else:
            raise CronError(f"unsupported token {part!r} in {spec!r} (names, L, W and ? are not accepted)")
        if start < lo or end > hi or start > end:
            raise CronError(f"value out of range in {spec!r} (allowed {lo}-{hi})")
        values.update(range(start, end + 1, step))
    return values


@dataclass(frozen=True)
class Cron:
    text: str
    minutes: frozenset[int]
    hours: frozenset[int]
    dom: frozenset[int]
    months: frozenset[int]
    dow: frozenset[int]
    dom_restricted: bool
    dow_restricted: bool

    def matches(self, when: datetime) -> bool:
        if when.minute not in self.minutes or when.hour not in self.hours or when.month not in self.months:
            return False
        dom_ok = when.day in self.dom
        dow_ok = (when.isoweekday() % 7) in self.dow  # Sunday = 0
        if self.dom_restricted and self.dow_restricted:
            return dom_ok or dow_ok  # vixie semantics
        return dom_ok and dow_ok

    @property
    def on_the_hour(self) -> bool:
        return 0 in self.minutes


def parse_cron(text: str) -> Cron:
    if not isinstance(text, str):
        raise CronError(f"cron must be a string, got {type(text).__name__}")
    parts = text.split()
    if len(parts) != 5:
        raise CronError(f"cron needs exactly 5 fields: {text!r}")
    sets = [_expand_field(p, lo, hi) for p, (lo, hi) in zip(parts, _FIELD_RANGES)]
    dow = {0 if v == 7 else v for v in sets[4]}
    return Cron(
        text=text,
        minutes=frozenset(sets[0]),
        hours=frozenset(sets[1]),
        dom=frozenset(sets[2]),
        months=frozenset(sets[3]),
        dow=frozenset(dow),
        dom_restricted=parts[2] != "*",
        dow_restricted=parts[4] != "*",
    )


def resolve_tz(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError) as exc:
        raise CronError(f"unknown time zone {name!r}") from exc


def fires_on_utc_day(cron: Cron, tz: ZoneInfo, day: date) -> list[datetime]:
    """Every UTC instant on `day` at which `cron` (written in `tz`) fires. 1,440 checks, no library."""
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    out: list[datetime] = []
    for minute in range(1440):
        instant = start + timedelta(minutes=minute)
        if cron.matches(instant.astimezone(tz)):
            out.append(instant)
    return out


@dataclass
class Job:
    id: str
    plane: str
    crons: list[str]
    tz: str
    enabled: bool
    derived: bool
    source: str
    klass: str = "unknown"
    delivery: dict = field(default_factory=dict)
    allotment: dict | None = None
    # beat sensors only. cadence_beats is the declared `cadence` as written (beats between due-checks);
    # cadence_hours is its WORST-CASE wall-clock bound, ceil(cadence_beats × loop_max / 3600).
    cadence_hours: int | None = None
    cadence_beats: int | None = None
    extra: dict = field(default_factory=dict)

    def parsed(self) -> list[Cron]:
        return [parse_cron(c) for c in self.crons]


def load_registry(root: Path) -> dict:
    data = yaml.safe_load((root / REGISTRY_REL).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("schedules.yaml must be a mapping")
    data.setdefault("planes", {})
    data.setdefault("jobs", [])
    return data


def load_baseline(root: Path) -> set[str]:
    path = root / BASELINE_REL
    if not path.exists():
        return set()
    lines = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            lines.add(line)
    return lines


def _workflow_on_block(doc: dict) -> dict:
    # PyYAML (YAML 1.1) reads the bare key `on:` as boolean True.
    block = doc.get("on", doc.get(True))
    return block if isinstance(block, dict) else {}


def derive_workflow_jobs(root: Path, plane: str, locator: str | Path = WORKFLOWS_REL, prefix: str = "limen") -> list[Job]:
    jobs: list[Job] = []
    wf_dir = root / locator
    if not wf_dir.is_dir():
        return jobs
    for path in sorted(wf_dir.glob("*.yml")) + sorted(wf_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(doc, dict):
            continue
        schedule = _workflow_on_block(doc).get("schedule")
        if not isinstance(schedule, list):
            continue
        crons = [str(entry.get("cron")) for entry in schedule if isinstance(entry, dict) and entry.get("cron")]
        if not crons:
            continue
        jobs.append(
            Job(
                id=f"{prefix}/{path.stem}",
                plane=plane,
                crons=crons,
                tz="UTC",
                enabled=True,
                derived=True,
                source=str(Path(locator) / path.name),
                klass="unknown",
                extra={"workflow_file": path.name},
            )
        )
    return jobs


def beat_loop_max(env: dict[str, str] | None = None) -> int:
    """The heartbeat's maximum beat interval in seconds (heartbeat-loop.sh `MAX="${LIMEN_LOOP_MAX:-1800}"`)."""
    raw = (env if env is not None else os.environ).get("LIMEN_LOOP_MAX", "")
    try:
        value = int(str(raw).strip() or BEAT_LOOP_MAX_SECONDS)
    except ValueError:
        value = BEAT_LOOP_MAX_SECONDS
    return value if value > 0 else BEAT_LOOP_MAX_SECONDS


def beats_to_hours(cadence_beats: int, loop_max: int) -> int:
    """Worst-case wall-clock hours one cadence window can span: ceil(beats × loop_max / 3600), at least 1."""
    return max(1, -(-(cadence_beats * max(1, loop_max)) // SECONDS_PER_HOUR))


def derive_sensor_jobs(
    root: Path, plane: str, locator: str | Path = SENSORS_REL, *, loop_max: int | None = None
) -> list[Job]:
    path = root / locator
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sensors = data.get("sensors") if isinstance(data, dict) else None
    ceiling = loop_max if loop_max is not None else beat_loop_max()
    jobs: list[Job] = []
    for sid, sensor in (sensors or {}).items():
        if not isinstance(sensor, dict):
            continue
        cadence = sensor.get("cadence")
        beats: int | None = None
        if isinstance(cadence, dict):
            default = cadence.get("default")
            beats = int(default) if isinstance(default, (int, float)) and default > 0 else None
        elif isinstance(cadence, (int, float)) and cadence > 0:
            beats = int(cadence)
        if beats is None:
            continue
        hours = beats_to_hours(beats, ceiling)
        jobs.append(
            Job(
                id=f"beat/{sid}",
                plane=plane,
                crons=[],
                tz="UTC",
                enabled=True,
                derived=True,
                source=str(locator),
                klass="audit",
                cadence_hours=hours,
                cadence_beats=beats,
                extra={"sources": list(sensor.get("source") or []), "loop_max_seconds": ceiling},
            )
        )
    return jobs


def newest_snapshot(root: Path) -> tuple[Path | None, dict | None]:
    candidates = sorted(root.glob(SNAPSHOT_GLOB))
    if not candidates:
        return None, None
    path = candidates[-1]
    try:
        return path, json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return path, None


def snapshot_age_days(snapshot: dict | None, today: date) -> int | None:
    stamp = (snapshot or {}).get("observed_at")
    if not isinstance(stamp, str):
        return None
    try:
        observed = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).date()
    except ValueError:
        return None
    return (today - observed).days


def derive_cloud_routine_jobs(root: Path, plane: str, locator: str | Path = CLOUD_ROUTINES_REL) -> list[Job]:
    path = root / locator
    if not path.exists():
        return []
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    _, snapshot = newest_snapshot(root)
    by_routine: dict[str, dict] = {}
    for row in (snapshot or {}).get("triggers") or []:
        if isinstance(row, dict) and isinstance(row.get("routine"), str):
            by_routine[row["routine"]] = row
    jobs: list[Job] = []
    for routine in manifest.get("routines") or []:
        if not isinstance(routine, dict) or not isinstance(routine.get("name"), str):
            continue
        live = by_routine.get(routine["name"])
        cron = live.get("cron") if live else None
        jobs.append(
            Job(
                id=f"claude/{routine['name']}",
                plane=plane,
                crons=[cron] if isinstance(cron, str) else [],
                tz="UTC",
                enabled=bool(routine.get("enabled", True)),
                derived=True,
                source=str(locator),
                klass=str(routine.get("class") or "audit"),
                extra={
                    "cadence": routine.get("cadence"),
                    "live": live,
                    "issue_repo": routine.get("issue_repo"),
                    "issue": routine.get("issue"),
                },
            )
        )
    return jobs


def declared_jobs(registry: dict) -> list[Job]:
    jobs: list[Job] = []
    for row in registry.get("jobs") or []:
        if not isinstance(row, dict):
            continue
        cron = row.get("cron")
        crons = [str(c) for c in cron] if isinstance(cron, list) else ([str(cron)] if cron else [])
        jobs.append(
            Job(
                id=str(row.get("id")),
                plane=str(row.get("plane")),
                crons=crons,
                tz=str(row.get("tz") or "UTC"),
                enabled=bool(row.get("enabled", True)),
                derived=False,
                source=str(row.get("source_of_truth") or ""),
                klass=str(row.get("class") or "unknown"),
                delivery=row.get("delivery") if isinstance(row.get("delivery"), dict) else {},
                allotment=row.get("allotment") if isinstance(row.get("allotment"), dict) else None,
                extra={"note": row.get("note")},
            )
        )
    return jobs


def derived_jobs(root: Path, registry: dict) -> list[Job]:
    jobs: list[Job] = []
    for plane_id, plane in (registry.get("planes") or {}).items():
        src = plane.get("jobs_source") if isinstance(plane, dict) else None
        if not isinstance(src, dict):
            continue
        kind, locator = src.get("kind"), src.get("locator")
        if kind == "workflows":
            jobs.extend(derive_workflow_jobs(root, plane_id, locator or WORKFLOWS_REL))
        elif kind == "sensors":
            jobs.extend(derive_sensor_jobs(root, plane_id, locator or SENSORS_REL))
        elif kind == "cloud-routines":
            jobs.extend(derive_cloud_routine_jobs(root, plane_id, locator or CLOUD_ROUTINES_REL))
    return jobs


def all_jobs(root: Path, registry: dict) -> list[Job]:
    return derived_jobs(root, registry) + declared_jobs(registry)


# ── sibling clones (cross-repo projections) ──────────────────────────────────────────────────

SIBLING_ENV = {"4444J99/ops": "LIMEN_OPS_ROOT", "4444J99/ops-witness": "LIMEN_OPS_WITNESS_ROOT"}


def sibling_root(repo: str, env: dict[str, str], home: Path) -> Path | None:
    """Where a sibling repository's clone lives on this host, if anywhere. Never clones."""
    explicit = env.get(SIBLING_ENV.get(repo, ""))
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.is_dir() else None
    name = repo.split("/", 1)[1]
    workdir = env.get("LIMEN_WORKDIR")
    for base in ([Path(workdir).expanduser()] if workdir else []) + [home / "Workspace"]:
        candidate = base / name
        if (candidate / ".git").exists():
            return candidate
    return None


_MANIFEST_TARGET_RX = re.compile(
    r"name:\s*'(?P<name>[^']+)'.*?maxInvocationsPerDay:\s*(?P<cap>\d+).*?\n\s*schedule:\s*'(?P<cron>[^']+)'",
    re.S,
)


def manifest_targets(manifest_path: Path) -> dict[str, dict]:
    """Parse name/schedule/maxInvocationsPerDay out of ops cloudflare/src/manifest.ts (no TS parser)."""
    text = manifest_path.read_text(encoding="utf-8")
    targets: dict[str, dict] = {}
    for match in _MANIFEST_TARGET_RX.finditer(text):
        targets[match.group("name")] = {"cron": match.group("cron"), "runs": int(match.group("cap"))}
    return targets


CADENCE_CLASSES = {"daily", "weekdays", "weekly"}


def cadence_class(cron: Cron) -> str:
    """The cadence class a claude routine's live cron implies, for parity with cloud-routines.json."""
    if cron.dow_restricted and cron.dow == frozenset({1, 2, 3, 4, 5}):
        return "weekdays"
    if cron.dow_restricted and len(cron.dow) == 1:
        return "weekly"
    if not cron.dow_restricted and not cron.dom_restricted:
        return "daily"
    return "other"
