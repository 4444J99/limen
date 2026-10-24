"""Shared reader for the SCHEDULES registry (institutio/governance/schedules.yaml).

One definition of what a job IS — declared rows plus the rows DERIVED from limen's own source files
(.github/workflows cron triggers, sensors.yaml cadence blocks, cloud-routines.json + the newest
claude-triggers snapshot receipt) and, for the planes that own the undeclared fleet, from the
git-ignored schedule-census receipt (every Actions cron and launchd plist the census read, selected
by FACT — visibility, archived, live state — never by repository name) — so check-schedules.py (the
pr-gate parity predicate), schedule-utilization.py (the beat sensor) and schedule-census.py (the
universe reader) cannot disagree about the estate they measure.
"""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
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
    "native-snapshot",
    "gh-actions-runs",
    "bookend-tsv",
    "witness-audit",
    "voice-stamps",
    "claude-snapshot",
    "board-dispatch-receipts",
    "issue-comments",
    "census-receipt",
    "launchctl",
    "none",
}
JOBS_SOURCE_KINDS = {"workflows", "sensors", "cloud-routines", "census"}
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
    # beat sensors only. cadence_beats resolves the runtime environment override (beats between due-checks);
    # cadence_hours is its WORST-CASE wall-clock bound, ceil(cadence_beats × loop_max / 3600).
    cadence_hours: int | None = None
    cadence_beats: int | None = None
    extra: dict = field(default_factory=dict)

    def parsed(self) -> list[Cron]:
        return [parse_cron(c) for c in self.crons]


def load_registry(root: Path, registry_path: Path | None = None) -> dict:
    data = yaml.safe_load((registry_path or root / REGISTRY_REL).read_text(encoding="utf-8")) or {}
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


def derive_workflow_jobs(
    root: Path, plane: str, locator: str | Path = WORKFLOWS_REL, prefix: str = "limen"
) -> list[Job]:
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


def _positive_int(spec, *, fallback: int | None = None) -> int | None:
    """Mirror beat-sensors.py's registry/env/default fallback order; parity is tested against the runner."""
    if spec is None:
        return fallback
    value = spec
    declared_default = fallback
    if isinstance(spec, dict):
        declared_default = spec.get("default", fallback)
        value = os.environ.get(str(spec.get("env") or ""), declared_default)
    for candidate in (value, declared_default, fallback):
        try:
            number = int(candidate)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


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
        beats = _positive_int(cadence)
        if beats is None:
            continue
        default_beats = _positive_int(cadence.get("default") if isinstance(cadence, dict) else cadence)
        cadence_env = str(cadence.get("env") or "") if isinstance(cadence, dict) else ""
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
                extra={
                    "sources": list(sensor.get("source") or []),
                    "loop_max_seconds": ceiling,
                    "cadence_default_beats": default_beats,
                    "cadence_env": cadence_env,
                },
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
        elif kind == "census":
            jobs.extend(derive_census_jobs(root, plane_id, src, registry))
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


# ── census-derived planes: the undeclared fleet, owned by fact selectors, never by name ──────────
#
# A census plane's `jobs_source` is {kind: census, locator, carrier: gh-workflow|launchd, scope:
# residual|all, visibility?: private|public}. Its rows exist only in memory and in the git-ignored
# ledgers under logs/: the receipt names private repositories, so nothing derived here may be written
# into a committed file, and every consumer prints COUNTS for these planes, never ids (schedules.yaml
# header, redaction convention R1–R4; check-schedules.py check H).

CENSUS_REL = Path("logs/schedule-census.json")
CENSUS_SCHEMA = "limen.schedule_census.v1"
CENSUS_CARRIERS = {"gh-workflow", "launchd"}
CENSUS_SCOPES = {"residual", "all"}
CENSUS_VISIBILITIES = {"private", "public"}
CEILING_KEYS = {"active", "on-the-hour", "shared-minute"}
RATCHET_CEILING_KEYS = ("on-the-hour", "shared-minute")  # shrink-only across commits (check J); `active` may rise
DECLARED_OFF_MATCH_KEYS = {"archived", "state"}
WORKFLOW_OFF_STATES = {"disabled_manually", "disabled_inactivity", "disabled_fork"}
# Evidence kinds whose locator is documented as owner/repo[:path|#N]; only these name a repository.
REPO_LOCATOR_EVIDENCE_KINDS = {"gh-actions-runs", "bookend-tsv", "witness-audit", "issue-comments"}
CENSUS_MAX_INCOMPLETE_SHARE = 0.25
CENSUS_RECEIPT_STATES = ("absent", "unreadable", "wrong-schema", "incomplete", "stale", "present")
HOURS_PER_DAY, DAYS_PER_WEEK, DAYS_PER_MONTH, MONTHS_PER_YEAR = 24, 7, 30.44, 12

# owner/name, optionally followed by :path or #N. The name must start alphanumeric so `logs/.voice` and
# `docs/receipts/…` (a third segment) are never read as repositories.
_REPO_LOCATOR_RX = re.compile(r"^([A-Za-z0-9-]+/[A-Za-z0-9][\w.-]*)(?:[:#]|$)")


def is_census_plane(plane: object) -> bool:
    return (
        isinstance(plane, dict)
        and isinstance(plane.get("jobs_source"), dict)
        and plane["jobs_source"].get("kind") == "census"
    )


def repo_of_locator(locator: object) -> str | None:
    m = _REPO_LOCATOR_RX.match(str(locator or ""))
    return m.group(1) if m else None


def self_repos_from_registry(registry: dict) -> set[str]:
    """The repositories whose workflow files limen itself derives (planes with jobs_source kind `workflows`),
    read from each such plane's repository-shaped gh-actions-runs evidence locator — the one place the
    registry has to name its own repository for the sensor to read its runs at all."""
    out: set[str] = set()
    for plane in (registry.get("planes") or {}).values():
        if not isinstance(plane, dict) or (plane.get("jobs_source") or {}).get("kind") != "workflows":
            continue
        evidence = plane.get("evidence") if isinstance(plane.get("evidence"), dict) else {}
        repo = repo_of_locator(evidence.get("locator")) if evidence.get("kind") in REPO_LOCATOR_EVIDENCE_KINDS else None
        if repo:
            out.add(repo)
    return out


def specific_plane_repos(registry: dict, self_repo: str | None = None) -> set[str]:
    """Every repository some NON-census plane already owns: authority.owner_repo, a repository-shaped
    evidence locator of a GitHub-backed evidence kind, a declared job's `source_of_truth` repo, and the
    workflows planes' own repositories (self_repos_from_registry, plus `self_repo` when a caller names one
    explicitly). The gate, the sensor and the census all derive the residual against THIS set — there is no
    second covered set anywhere."""
    covered: set[str] = set(self_repos_from_registry(registry))
    planes = registry.get("planes") or {}
    for plane in planes.values():
        if not isinstance(plane, dict) or is_census_plane(plane):
            continue
        owner_repo = (
            (plane.get("authority") or {}).get("owner_repo") if isinstance(plane.get("authority"), dict) else None
        )
        if owner_repo:
            covered.add(str(owner_repo))
        evidence = plane.get("evidence") if isinstance(plane.get("evidence"), dict) else {}
        if evidence.get("kind") in REPO_LOCATOR_EVIDENCE_KINDS:
            repo = repo_of_locator(evidence.get("locator"))
            if repo:
                covered.add(repo)
        if self_repo and (plane.get("jobs_source") or {}).get("kind") == "workflows":
            covered.add(self_repo)
    for row in registry.get("jobs") or []:
        if isinstance(row, dict):
            repo = repo_of_locator(row.get("source_of_truth"))
            if repo:
                covered.add(repo)
    return covered


def disclosed_repo_tokens(registry: dict) -> set[str]:
    """Tokens a committed registry line may legitimately carry even when they name a private repository —
    exactly rule R1, nothing wider: a plane's authority.owner_repo (slug and bare name) and the job-id
    components of declared rows on planes that carry `authority` (ops/<job>, cloudflare/<target> —
    projections the owner repository publishes). A `source_of_truth` or an evidence locator is NOT a
    disclosure: a commit must never be able to exempt its own leak by adding the name somewhere else."""
    tokens: set[str] = set()
    planes = registry.get("planes") or {}
    authority_planes: set[str] = set()
    for pid, plane in planes.items():
        if not isinstance(plane, dict) or not isinstance(plane.get("authority"), dict):
            continue
        authority_planes.add(pid)
        owner_repo = plane["authority"].get("owner_repo")
        if isinstance(owner_repo, str) and "/" in owner_repo:
            tokens.add(owner_repo)
            tokens.add(owner_repo.split("/", 1)[1])
    for row in registry.get("jobs") or []:
        if isinstance(row, dict) and row.get("plane") in authority_planes and isinstance(row.get("id"), str):
            tokens.update(part for part in row["id"].split("/") if part)
    return tokens


def residual_planes(registry: dict, carrier: str = "gh-workflow") -> dict[str | None, str]:
    """visibility (or None = both) → plane id, for every census plane of `carrier` with scope residual."""
    out: dict[str | None, str] = {}
    for pid, plane in (registry.get("planes") or {}).items():
        if not is_census_plane(plane):
            continue
        src = plane["jobs_source"]
        if src.get("carrier", "gh-workflow") == carrier and src.get("scope", "residual") == "residual":
            vis = src.get("visibility")
            out[str(vis) if vis else None] = pid
    return out


def cron_fires_per_day(cron: Cron) -> float:
    """Nominal fires per day from the cron's own fields (day-of-week and day-of-month as shares of a week
    and a 30.44-day month, vixie OR when both are restricted). The census and the sensor share this so a
    `*/30 * * * *` is 48/day for both and never 'daily' because no day field is restricted."""
    base = float(len(cron.minutes) * len(cron.hours))
    dow_share = len(cron.dow) / DAYS_PER_WEEK
    dom_share = len(cron.dom) / DAYS_PER_MONTH
    if cron.dow_restricted and cron.dom_restricted:
        day_share = min(1.0, dow_share + dom_share)
    elif cron.dow_restricted:
        day_share = dow_share
    elif cron.dom_restricted:
        day_share = dom_share
    else:
        day_share = 1.0
    return round(base * day_share * (len(cron.months) / MONTHS_PER_YEAR), 3)


def cadence_label(cron: Cron) -> str:
    """weekdays | weekly | monthly | sub-hourly | hourly | intraday | daily | other — the census ledger's vocabulary.
    A day field spelled out to cover every day (`0-6`, `1-31`) is unrestricted; the named labels need every month."""
    base = len(cron.minutes) * len(cron.hours)
    per_day = cron_fires_per_day(cron)
    dow_restricted = cron.dow_restricted and len(cron.dow) < 7
    dom_restricted = cron.dom_restricted and len(cron.dom) < 31
    every_month = len(cron.months) == 12
    day_share_full = not dow_restricted and not dom_restricted
    if dow_restricted and cron.dow == frozenset({1, 2, 3, 4, 5}) and base == 1 and every_month and not dom_restricted:
        return "weekdays"
    if dow_restricted and len(cron.dow) == 1 and base == 1 and not dom_restricted and every_month:
        return "weekly"
    if dom_restricted and len(cron.dom) == 1 and base == 1 and not dow_restricted and every_month:
        return "monthly"
    if per_day > HOURS_PER_DAY:
        return "sub-hourly"
    if len(cron.hours) == HOURS_PER_DAY and len(cron.minutes) == 1 and day_share_full and every_month:
        return "hourly"
    if per_day > 1:
        return "intraday"
    if per_day == 1:
        return "daily"
    return "other"


def census_receipt_is_complete(report: dict, *, max_incomplete_share: float = CENSUS_MAX_INCOMPLETE_SHARE) -> bool:
    """A receipt that read nothing, whose universe is missing an owner (`universe_unlisted_owners`), or that left
    more than `max_incomplete_share` of its universe unread — unreachable, unscanned, partially read or errored —
    is not a census to rest on: the sensor reads it as a stale readback, never as the fleet."""
    d = report.get("denominators") or {}
    try:
        scanned = int(d.get("scanned") or 0)
        universe = int(d.get("universe_count") or 0)
        unlisted = int(d.get("universe_unlisted_owners") or 0)
        unread = (
            int(d.get("unreachable") or 0)
            + int(d.get("unscanned_by_budget") or 0)
            + int(d.get("internal_errors") or 0)
            + int(d.get("scanned_partial") or 0)
        )
    except (TypeError, ValueError):
        return False
    if scanned == 0 or unlisted:
        return False
    return universe == 0 or unread / universe <= max_incomplete_share


def census_receipt_path(root: Path, locator: str | Path | None) -> Path:
    path = Path(str(locator)) if locator else CENSUS_REL
    return path if path.is_absolute() else root / path


_CENSUS_CACHE: dict[tuple[str, int, int], dict | None] = {}


def _read_census_json(path: Path) -> dict | None:
    try:
        st = path.stat()
    except OSError:
        return None
    key = (str(path), st.st_mtime_ns, st.st_size)
    if key not in _CENSUS_CACHE:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            data = None
        _CENSUS_CACHE.clear()
        _CENSUS_CACHE[key] = data if isinstance(data, dict) else None
    return _CENSUS_CACHE[key]


def census_generated_at(data: dict | None) -> datetime | None:
    stamp = (data or {}).get("generated_at")
    if not isinstance(stamp, str):
        return None
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when.replace(tzinfo=timezone.utc) if when.tzinfo is None else when.astimezone(timezone.utc)


def load_census_receipt(
    root: Path, locator: str | Path | None, *, max_age_days: int | None = None, now: datetime | None = None
) -> tuple[Path, dict | None, str]:
    """(path, data, state) with state ∈ CENSUS_RECEIPT_STATES. `data` is returned for incomplete, stale and
    present receipts (rows can still be derived; the caller decides what they prove) and is None otherwise.
    absent is the ordinary state of a CI runner or a worktree: the census runs where gh carries the owner's
    auth, and the receipt is git-ignored by convention (R1) — so absent is 'not this host', never drift."""
    path = census_receipt_path(root, locator)
    if not path.exists():
        return path, None, "absent"
    data = _read_census_json(path)
    if data is None:
        return path, None, "unreadable"
    if data.get("schema") != CENSUS_SCHEMA:
        return path, None, "wrong-schema"
    if not census_receipt_is_complete(data):
        return path, data, "incomplete"
    if max_age_days is not None:
        generated = census_generated_at(data)
        moment = now or datetime.now(timezone.utc)
        if generated is None or (moment - generated) > timedelta(days=max_age_days):
            return path, data, "stale"
    return path, data, "present"


def census_unread(data: dict | None) -> dict[str, int]:
    """What the receipt did NOT read, from its own denominators — the reasons a count below a ceiling is an
    undercount rather than a floor: repositories unreachable, unscanned (budget/quota), errored, or read only
    partially. Non-zero means 'do not lower a ceiling from this receipt'."""
    d = (data or {}).get("denominators") or {}
    out: dict[str, int] = {}
    for key in ("unreachable", "unscanned_by_budget", "internal_errors", "scanned_partial", "universe_unlisted_owners"):
        try:
            n = int(d.get(key) or 0)
        except (TypeError, ValueError):
            n = 0
        if n:
            out[key] = n
    return out


def census_floor_unmeasured(data: dict | None, jobs: list[Job]) -> dict[str, int]:
    """Why a plane's ceiling counts may be undercounts: receipt-wide unread repositories (census_unread) plus
    this plane's rows on partially read repositories and live rows whose Actions state could not be read.
    Empty ⟺ every count is a floor and "lower the ceiling to N" is sound advice (the ratchet only falls, so
    lowering from an undercount makes the next complete census red on unchanged repositories)."""
    out = census_unread(data)
    source = str(((data or {}).get("denominators") or {}).get("universe_source") or "")
    if source.startswith("explicit"):
        out["explicit_scope"] = 1  # a targeted census (--repos) is a subset of the fleet, never its floor
    partial = sum(1 for j in jobs if j.extra.get("partial"))
    unverified = sum(
        1 for j in jobs if not j.enabled and str(j.extra.get("state")) == "unknown" and not j.extra.get("archived")
    )
    if partial:
        out["partial_rows"] = partial
    if unverified:
        out["unverified_rows"] = unverified
    return out


def _census_rows(data: dict) -> list[dict]:
    return [
        r
        for r in data.get("repos") or []
        if isinstance(r, dict) and r.get("reach") == "ok" and isinstance(r.get("repo"), str)
    ]


def derive_census_jobs(
    root: Path, plane_id: str, src: dict, registry: dict, *, receipt: dict | None = None
) -> list[Job]:
    """Rows for one census plane. gh-workflow: one job per cron-bearing Actions workflow the census read in a
    repository of the plane's visibility that no specific plane covers (scope residual) — enabled ⟺ live state
    `active` in a non-archived repository; the receipt's live state, archived flag, partial flag and the
    workflow's scheduled-run summary ride in `extra`. launchd: one job per distinct plist Label (fallback: the
    file stem), deduplicated across repositories. Returns [] when the receipt is absent or unreadable."""
    if receipt is None:
        _, receipt, state = load_census_receipt(root, src.get("locator"))
        if receipt is None:
            return []
    carrier = str(src.get("carrier") or "gh-workflow")
    scope = str(src.get("scope") or "residual")
    visibility = src.get("visibility")
    covered = specific_plane_repos(registry) if scope == "residual" else set()
    generated_at = receipt.get("generated_at")
    jobs: list[Job] = []
    if carrier == "gh-workflow":
        for row in _census_rows(receipt):
            repo = row["repo"]
            if repo in covered:
                continue
            private = bool(row.get("private"))
            if visibility == "private" and not private or visibility == "public" and private:
                continue
            archived = bool(row.get("archived"))
            partial = bool(row.get("partial"))
            decls = [
                d
                for d in row.get("declarations") or []
                if isinstance(d, dict) and d.get("kind") == "gh-workflow" and d.get("crons")
            ]
            names = [d.get("name") for d in decls]
            fired_row = row.get("fired") if isinstance(row.get("fired"), dict) else {}
            by_workflow = fired_row.get("by_workflow") or {}
            for d in decls:
                path = str(d.get("path") or "")
                name = d.get("name")
                state = str(d.get("state") or "unknown")
                # the run summary is keyed by workflow path from #3196 on (exact join, never ambiguous) and by display
                # name on older receipts (ambiguous when two files share a name)
                ambiguous = path not in by_workflow and (not isinstance(name, str) or names.count(name) > 1)
                crons = [str(c) for c in d["crons"]]
                unparseable: list[str] = []
                for c in crons:
                    try:
                        parse_cron(c)
                    except CronError:
                        unparseable.append(c)
                jobs.append(
                    Job(
                        id=f"fleet/{repo}/{Path(path).stem}",
                        plane=plane_id,
                        crons=crons,
                        tz="UTC",
                        enabled=state == "active" and not archived,
                        derived=True,
                        source=str(src.get("locator") or CENSUS_REL),
                        klass="unknown",
                        extra={
                            "repo": repo,
                            "private": private,
                            "archived": archived,
                            "state": state,
                            "name": name,
                            "workflow_file": Path(path).name,
                            "partial": partial,
                            "fires_per_day": d.get("fires_per_day"),
                            "fired": by_workflow.get(path)
                            or (by_workflow.get(name) if isinstance(name, str) and not ambiguous else None),
                            "fired_oldest_seen": fired_row.get("oldest_seen"),
                            "fired_oldest_page_read": bool(fired_row.get("oldest_page_read")),
                            "fired_page_oldest_seen": fired_row.get("page_oldest_seen"),
                            "fired_listed": fired_row.get("total_scheduled_runs"),
                            "fired_capped": bool(fired_row.get("listing_capped")),
                            "ambiguous": ambiguous,
                            "unparseable_crons": unparseable,
                            "generated_at": generated_at,
                        },
                    )
                )
        return jobs
    if carrier == "launchd":
        by_label: dict[str, Job] = {}
        for row in _census_rows(receipt):
            repo = row["repo"]
            if repo in covered:
                continue
            for d in row.get("declarations") or []:
                if not isinstance(d, dict) or d.get("kind") != "launchd" or d.get("unparseable"):
                    continue
                if not (d.get("interval_seconds") or d.get("calendar")):
                    continue
                path = str(d.get("path") or "")
                label = str(d.get("label") or Path(path).stem)
                job = by_label.get(label)
                if job is None:
                    job = by_label[label] = Job(
                        id=f"launchd/{label}",
                        plane=plane_id,
                        crons=[],
                        tz="UTC",
                        enabled=True,
                        derived=True,
                        source=str(src.get("locator") or CENSUS_REL),
                        klass="unknown",
                        extra={
                            "label": label,
                            "repos": [],
                            "paths": [],
                            "interval_seconds": d.get("interval_seconds"),
                            "calendar": d.get("calendar"),
                            "private": False,
                            "partial": False,
                            "generated_at": generated_at,
                        },
                    )
                job.extra["repos"].append(repo)
                job.extra["paths"].append(path)
                job.extra["private"] = job.extra["private"] or bool(row.get("private"))
                job.extra["partial"] = job.extra["partial"] or bool(row.get("partial"))
        return list(by_label.values())
    return jobs


def census_plane_counts(jobs: list[Job]) -> dict[str, int]:
    """The three ceiling counts for one census plane over its ENABLED rows: active, on-the-hour (any cron with
    minute 0) and shared-minute — two workflows of one repository sharing a minute (the ops house rule is per
    repository; two repositories firing at :17 is not a collision). Unparseable crons count as active only."""
    enabled = [j for j in jobs if j.enabled]
    on_hour = 0
    by_repo_minute: dict[tuple[str, int], set[str]] = defaultdict(set)
    for job in enabled:
        hour_hit = False
        for c in job.crons:
            try:
                cron = parse_cron(c)
            except CronError:
                continue
            hour_hit = hour_hit or cron.on_the_hour
            for m in cron.minutes:
                by_repo_minute[(str(job.extra.get("repo")), m)].add(job.id)
        on_hour += int(hour_hit)
    sharing: set[str] = set()
    for ids in by_repo_minute.values():
        if len(ids) > 1:
            sharing |= ids
    return {"active": len(enabled), "on-the-hour": on_hour, "shared-minute": len(sharing)}


def declared_off_match(match: dict, job: Job) -> bool:
    """A declared_off match row selects by FACT: `archived: bool` and/or `state: [..]` (a str is one state)."""
    if "archived" in match and bool(job.extra.get("archived")) != bool(match["archived"]):
        return False
    if "state" in match:
        states = match["state"] if isinstance(match["state"], list) else [match["state"]]
        if str(job.extra.get("state")) not in {str(s) for s in states}:
            return False
    return True


def census_off_counts(plane: dict, jobs: list[Job]) -> tuple[list[dict[str, int]], list[Job], int]:
    """(per-rule counts, undeclared-off jobs, unverified count) over the plane's NON-enabled rows. Each declared_off
    match rule gets a dict of state → count (archived rows count under 'archived' as well as their state); a row
    no rule matches is undeclared-off (an off-switch nobody owns); a live row whose state the census could not
    read (`unknown`) is unverified — neither on nor off — and is counted separately."""
    rules = [r for r in plane.get("declared_off") or [] if isinstance(r, dict) and isinstance(r.get("match"), dict)]
    per_rule: list[dict[str, int]] = [defaultdict(int) for _ in rules]
    undeclared: list[Job] = []
    unverified = 0
    for job in jobs:
        if job.enabled:
            continue
        state = str(job.extra.get("state"))
        archived = bool(job.extra.get("archived"))
        if state == "unknown" and not archived:
            unverified += 1
            continue
        for i, rule in enumerate(rules):
            if declared_off_match(rule["match"], job):
                per_rule[i][state] += 1
                if archived:
                    per_rule[i]["archived"] += 1
                break
        else:
            undeclared.append(job)
    return [dict(c) for c in per_rule], undeclared, unverified
