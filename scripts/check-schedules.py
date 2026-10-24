#!/usr/bin/env python3
"""SCHEDULES registry drift predicate — hold institutio/governance/schedules.yaml to the estate.

The registry declares every scheduler plane the operator runs (its allotment, surface, evidence and
owner) and the jobs scheduled against it. Planes limen itself configures are DERIVED from their
source files by scripts/_schedules.py (workflows, sensors.yaml cadences, cloud-routines.json + the
newest claude-triggers snapshot receipt); planes another repository operates are declared rows
with a `source_of_truth` pointer. Exit 0 ⟺ no drift.

Named checks (the check-*.py ratchet discipline):
  A schema        — plane/job required fields, enums, every cron parses (5 fields, no names), tz resolves
  B derived       — every `jobs_source` resolves and yields ≥1 row; no declared row duplicates a derived plane
  C claude parity — every enabled cloud-routines.json routine appears in the newest snapshot receipt by
                    `routine`, its live cron's cadence class matches the manifest cadence, and every live
                    contracted routine appears in the manifest (no snapshot ⇒ unverifiable here, not drift)
  D sibling parity— rows for 4444J99/ops, 4444J99/ops-witness and the Cloudflare manifest agree with the
                    sibling clone when one is present on this host (LIMEN_OPS_ROOT / LIMEN_OPS_WITNESS_ROOT /
                    $LIMEN_WORKDIR/<repo> / ~/Workspace/<repo>); absent ⇒ unverifiable here, not drift
  E stagger       — github-provider planes: no enabled job on the hour and no two jobs in one plane sharing
                    a minute, except lines in schedule-stagger-baseline.txt (shrink-only: a listed line whose
                    violation is gone is itself a failure, so the baseline cannot rot)
  F consumers     — sensors.yaml runs scripts/schedule-utilization.py; gates.yaml registers this predicate
  G not-a-scheduler — every reader of the registry (any scripts/*.py importing _schedules) is on the
                    declared allowlist, and none of them is an outbound effector: a new reader must be
                    added here deliberately, which is how "nothing that reads this can start a run" stays
                    a predicate instead of prose

  python3 scripts/check-schedules.py              # gate (CI): exit 1 on any drift
  python3 scripts/check-schedules.py --slot-map   # print the 24h UTC slot map of every clock-scheduled job
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _schedules as S  # noqa: E402

_failures: list[str] = []
_advisories: list[str] = []


def fail(check: str, message: str) -> None:
    _failures.append(f"[{check}] {message}")


def advise(check: str, message: str) -> None:
    _advisories.append(f"[{check}] {message}")


def _require(
    check: str, where: str, mapping: dict, key: str, allowed: set | None = None, kind: type | tuple | None = None
) -> object:
    if key not in mapping:
        fail(check, f"{where}: missing `{key}`")
        return None
    value = mapping[key]
    if kind is not None and not isinstance(value, kind):
        fail(check, f"{where}: `{key}` must be {kind}, got {type(value).__name__}")
        return None
    if allowed is not None and value not in allowed:
        fail(check, f"{where}: `{key}`={value!r} not in {sorted(allowed)}")
    return value


def check_schema(registry: dict) -> None:
    audited = "audit_only" in registry
    if audited and registry["audit_only"] is not True:
        fail("A", "audit_only must remain true; the audit cannot dispatch")
    if audited:
        for gap in registry.get("coverage_gaps", []):
            if not isinstance(gap, dict) or any(
                not isinstance(gap.get(k), str) or not gap[k].strip() for k in ("gap", "owner", "next_action")
            ):
                fail("A", "coverage gap requires gap, owner and next_action")
    planes = registry.get("planes") or {}
    if not isinstance(planes, dict) or not planes:
        fail("A", "registry declares no planes")
        return
    for pid, plane in planes.items():
        where = f"plane {pid}"
        if not isinstance(plane, dict):
            fail("A", f"{where}: not a mapping")
            continue
        _require("A", where, plane, "provider", kind=str)
        _require("A", where, plane, "surface", allowed=S.PLANE_SURFACES)
        _require("A", where, plane, "owner", kind=str)
        _require("A", where, plane, "effector", kind=str)
        _require("A", where, plane, "enabled", kind=bool)
        if audited:
            capabilities = plane.get("capabilities")
            if not isinstance(capabilities, dict) or set(capabilities) != {"launch", "input", "retrieval"}:
                fail("A", f"{where}: capabilities require separate launch/input/retrieval records")
            else:
                for operation, capability in capabilities.items():
                    if not isinstance(capability, dict):
                        fail("A", f"{where}: capability {operation} must be a mapping")
                        continue
                    if capability.get("state") not in {"verified", "documented", "unknown", "unavailable"}:
                        fail("A", f"{where}: invalid capability state for {operation}")
                    if not isinstance(capability.get("source"), str) or not capability["source"].strip():
                        fail("A", f"{where}: capability {operation} requires source")
                    stamp = capability.get("observed_at")
                    try:
                        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                        if parsed.tzinfo is None:
                            raise ValueError("undated capability")
                    except ValueError:
                        fail("A", f"{where}: capability {operation} requires dated provenance")
            inventory = plane.get("native_inventory")
            if inventory is not None and (
                not isinstance(inventory, dict)
                or type(inventory.get("enabled_count")) is not int
                or inventory["enabled_count"] < 0
                or inventory.get("coverage") not in {"complete", "partial", "unknown"}
                or not inventory.get("observed_at")
                or not inventory.get("source")
            ):
                fail("A", f"{where}: malformed native_inventory projection")
        policy = _require("A", where, plane, "fill_policy", allowed=S.PLANE_FILL_POLICIES)
        floor = plane.get("floor")
        if policy == "floor" and not (isinstance(floor, int) and floor > 0):
            fail("A", f"{where}: fill_policy floor needs a positive integer `floor`")
        allot = _require("A", where, plane, "allotment", kind=dict)
        if isinstance(allot, dict):
            if allot.get("classification", "published-ceiling") not in {
                "published-ceiling",
                "local-policy",
                "unmeasured",
            }:
                fail("A", f"{where}.allotment: invalid quota classification")
            if allot.get("classification") == "published-ceiling":
                publication = allot.get("publication")
                valid = False
                if isinstance(publication, dict):
                    try:
                        source = urlsplit(str(publication.get("source", "")))
                        stamp = datetime.fromisoformat(str(publication.get("observed_at")).replace("Z", "+00:00"))
                        valid = stamp.tzinfo is not None and source.scheme == "https" and bool(source.netloc)
                    except ValueError:
                        pass
                if not valid:
                    fail("A", f"{where}.allotment: published ceiling requires dated publication source")
            _require("A", f"{where}.allotment", allot, "window", allowed=S.PLANE_WINDOWS)
            _require("A", f"{where}.allotment", allot, "entitlement", allowed=S.PLANE_ENTITLEMENTS)
            _require("A", f"{where}.allotment", allot, "source", kind=str)
            runs = allot.get("runs")
            if runs is not None and not (type(runs) is int and runs >= 0):
                fail("A", f"{where}.allotment: runs must be a non-negative int or null")
            concurrency = allot.get("concurrency")
            if concurrency is not None and (type(concurrency) is not int or concurrency < 0):
                fail("A", f"{where}.allotment: concurrency must be a non-negative int or null")
        capacity = plane.get("capacity")
        if capacity is not None:
            if not isinstance(capacity, dict) or set(capacity) - {"verified_allowance", "usage", "downstream"}:
                fail("A", f"{where}: malformed capacity record")
            else:
                for label, record in capacity.items():
                    needed = (
                        {"review", "delivery", "evidence_ref", "observed_at"}
                        if label == "downstream"
                        else {"value", "account_ref", "window", "unit", "evidence_ref"}
                    )
                    if label == "usage":
                        needed |= {"coverage", "observed_at"}
                    if not isinstance(record, dict) or not needed <= set(record):
                        fail("A", f"{where}: incomplete capacity {label}")
                        continue
                    numbers = {"review", "delivery"} if label == "downstream" else {"value"}
                    if any(type(record[k]) is not int or record[k] < 0 for k in numbers):
                        fail("A", f"{where}: invalid capacity quantity")
                    if any(not isinstance(record[k], str) or not record[k].strip() for k in needed - numbers):
                        fail("A", f"{where}: invalid capacity provenance")
                    if label == "usage" and record["coverage"] not in {"complete", "partial", "unknown"}:
                        fail("A", f"{where}: invalid capacity coverage")
        evidence = _require("A", where, plane, "evidence", kind=dict)
        if isinstance(evidence, dict):
            kind = _require("A", f"{where}.evidence", evidence, "kind", allowed=S.EVIDENCE_KINDS)
            if kind != "none" and not evidence.get("locator"):
                fail("A", f"{where}.evidence: kind {kind} needs a locator")
        src = plane.get("jobs_source")
        if src is not None:
            if not isinstance(src, dict) or src.get("kind") not in S.JOBS_SOURCE_KINDS or not src.get("locator"):
                fail("A", f"{where}: jobs_source must be {{kind ∈ {sorted(S.JOBS_SOURCE_KINDS)}, locator}}")
    seen: set[str] = set()
    for i, row in enumerate(registry.get("jobs") or []):
        where = f"job[{i}]"
        if not isinstance(row, dict):
            fail("A", f"{where}: not a mapping")
            continue
        jid = row.get("id")
        where = f"job {jid or i}"
        if not isinstance(jid, str) or "/" not in jid:
            fail("A", f"{where}: id must be '<plane-short>/<job>'")
        elif jid in seen:
            fail("A", f"{where}: duplicate id")
        seen.add(str(jid))
        plane_id = row.get("plane")
        if plane_id not in planes:
            fail("A", f"{where}: plane {plane_id!r} is not declared")
        elif isinstance(planes.get(plane_id), dict) and planes[plane_id].get("jobs_source"):
            fail(
                "B",
                f"{where}: plane {plane_id} derives its jobs from {planes[plane_id]['jobs_source'].get('locator')} — a declared row duplicates it",
            )
        _require("A", where, row, "class", allowed=S.JOB_CLASSES)
        _require("A", where, row, "enabled", kind=bool)
        _require("A", where, row, "source_of_truth", kind=str)
        delivery = _require("A", where, row, "delivery", kind=dict)
        if isinstance(delivery, dict) and not delivery.get("kind"):
            fail("A", f"{where}: delivery needs a kind")
        cron = row.get("cron")
        crons = cron if isinstance(cron, list) else [cron]
        for c in crons:
            try:
                S.parse_cron(c)
            except S.CronError as exc:
                fail("A", f"{where}: {exc}")
        try:
            S.resolve_tz(str(row.get("tz") or "UTC"))
        except S.CronError as exc:
            fail("A", f"{where}: {exc}")


def check_derived(root: Path, registry: dict, derived: list[S.Job]) -> None:
    for pid, plane in (registry.get("planes") or {}).items():
        src = plane.get("jobs_source") if isinstance(plane, dict) else None
        if not isinstance(src, dict):
            continue
        locator = root / str(src.get("locator"))
        if not locator.exists():
            fail("B", f"plane {pid}: jobs_source locator {src.get('locator')} does not exist")
            continue
        rows = [j for j in derived if j.plane == pid]
        if not rows:
            fail("B", f"plane {pid}: jobs_source {src.get('locator')} derived zero jobs")
        for job in rows:
            for c in job.crons:
                try:
                    S.parse_cron(c)
                except S.CronError as exc:
                    fail("B", f"{job.id} ({job.source}): {exc}")


def check_claude_parity(root: Path, registry: dict, derived: list[S.Job]) -> None:
    claude_planes = [
        pid
        for pid, p in (registry.get("planes") or {}).items()
        if isinstance(p, dict) and (p.get("jobs_source") or {}).get("kind") == "cloud-routines"
    ]
    if not claude_planes:
        return
    path, snapshot = S.newest_snapshot(root)
    if path is None:
        advise("C", f"no {S.SNAPSHOT_GLOB} receipt on disk — live-vs-manifest parity unverifiable here, not drift")
        return
    if snapshot is None:
        fail("C", f"{path.name}: unreadable snapshot receipt")
        return
    live = {
        r["routine"]: r
        for r in snapshot.get("triggers") or []
        if isinstance(r, dict) and isinstance(r.get("routine"), str)
    }
    manifest_names: set[str] = set()
    for job in derived:
        if job.plane not in claude_planes:
            continue
        name = job.id.split("/", 1)[1]
        manifest_names.add(name)
        if not job.enabled:
            continue
        row = live.get(name)
        if row is None:
            fail("C", f"routine {name}: enabled in cloud-routines.json but absent from {path.name} (routine key)")
            continue
        cadence = (job.extra.get("cadence") or "").lower()
        cron = row.get("cron")
        if not isinstance(cron, str):
            fail("C", f"routine {name}: snapshot row has no cron")
            continue
        try:
            klass = S.cadence_class(S.parse_cron(cron))
        except S.CronError as exc:
            fail("C", f"routine {name}: snapshot cron {cron!r}: {exc}")
            continue
        if cadence in S.CADENCE_CLASSES and klass != cadence:
            fail("C", f"routine {name}: manifest cadence {cadence!r} but live cron {cron!r} is {klass}")
    for name in sorted(set(live) - manifest_names):
        fail("C", f"live trigger routine {name!r} ({live[name].get('id')}) is not in cloud-routines.json")


def _sibling_workflow_crons(clone: Path) -> dict[str, list[str]]:
    rows = S.derive_workflow_jobs(clone, plane="sibling", prefix="sibling")
    return {job.extra["workflow_file"]: sorted(job.crons) for job in rows}


def check_sibling_parity(registry: dict, declared: list[S.Job], env: dict[str, str], home: Path) -> None:
    by_repo: dict[str, list[S.Job]] = defaultdict(list)
    for job in declared:
        repo = job.source.split(":", 1)[0] if ":" in job.source else ""
        if repo in S.SIBLING_ENV:
            by_repo[repo].append(job)
    for repo, jobs in sorted(by_repo.items()):
        clone = S.sibling_root(repo, env, home)
        if clone is None:
            advise(
                "D", f"{repo}: no sibling clone on this host — {len(jobs)} projected rows unverifiable here, not drift"
            )
            continue
        live = _sibling_workflow_crons(clone)
        manifest_rows = [j for j in jobs if j.source.endswith("manifest.ts")]
        workflow_rows = [j for j in jobs if ".github/workflows/" in j.source]
        for job in workflow_rows:
            wf = job.source.split(".github/workflows/", 1)[1]
            if wf not in live:
                fail("D", f"{job.id}: {repo}:{wf} has no schedule trigger in the sibling clone ({clone})")
            elif sorted(job.crons) != live[wf]:
                fail("D", f"{job.id}: crons {sorted(job.crons)} != sibling {live[wf]}")
        declared_files = {j.source.split(".github/workflows/", 1)[1] for j in workflow_rows}
        for wf in sorted(set(live) - declared_files):
            fail("D", f"{repo}:.github/workflows/{wf} has crons {live[wf]} but no registry row")
        if manifest_rows:
            manifest_path = clone / "cloudflare" / "src" / "manifest.ts"
            if not manifest_path.exists():
                fail("D", f"{repo}: manifest rows declared but {manifest_path} is absent in the clone")
            else:
                targets = S.manifest_targets(manifest_path)
                for job in manifest_rows:
                    name = job.id.split("/", 1)[1]
                    target = targets.get(name)
                    if target is None:
                        fail("D", f"{job.id}: not a target in {repo}:cloudflare/src/manifest.ts")
                        continue
                    if job.crons != [target["cron"]]:
                        fail("D", f"{job.id}: cron {job.crons} != manifest {target['cron']!r}")
                    runs = (job.allotment or {}).get("runs")
                    if runs != target["runs"]:
                        fail("D", f"{job.id}: allotment.runs {runs} != manifest maxInvocationsPerDay {target['runs']}")
                for name in sorted(set(targets) - {j.id.split("/", 1)[1] for j in manifest_rows}):
                    fail("D", f"{repo}: manifest target {name!r} has no registry row")
        advise("D", f"{repo}: verified against sibling clone {clone}")


def stagger_violations(registry: dict, jobs: list[S.Job]) -> set[str]:
    planes = registry.get("planes") or {}
    out: set[str] = set()
    minutes_by_plane: dict[str, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    for job in jobs:
        plane = planes.get(job.plane) or {}
        if plane.get("provider") != "github" or not job.enabled:
            continue
        for c in job.crons:
            try:
                cron = S.parse_cron(c)
            except S.CronError:
                continue
            if cron.on_the_hour:
                out.add(f"{job.plane}:{job.id}:on-the-hour")
            for m in cron.minutes:
                minutes_by_plane[job.plane][m].add(job.id)
    for plane_id, by_minute in minutes_by_plane.items():
        for ids in by_minute.values():
            if len(ids) > 1:
                for jid in ids:
                    out.add(f"{plane_id}:{jid}:shared-minute")
    return out


def check_stagger(registry: dict, jobs: list[S.Job], baseline: set[str]) -> None:
    current = stagger_violations(registry, jobs)
    for line in sorted(current - baseline):
        fail(
            "E",
            f"new stagger violation {line} — move the cron off the hour / off a shared minute (house offsets {registry.get('house_offsets')}) or baseline it deliberately",
        )
    for line in sorted(baseline - current):
        fail(
            "E",
            f"baseline line {line} names a violation that no longer exists — delete the line (the baseline is shrink-only and must not rot)",
        )


def check_launch_authority(registry: dict) -> None:
    """Logical launch authority is independent of the GitHub minute-offset house policy."""
    by_job = defaultdict(set)
    for row in list(registry.get("jobs") or []) + list(registry.get("logical_launch_authorities") or []):
        if isinstance(row, dict) and row.get("enabled", True) and row.get("logical_job"):
            authority = row.get("launch_authority")
            if not isinstance(authority, str) or not authority.strip():
                fail("H", "logical job requires a launch_authority")
            else:
                by_job[row["logical_job"]].add(authority)
    for logical, authorities in by_job.items():
        if len(authorities) > 1:
            fail("H", f"duplicate logical launch authority for {logical}")


def check_consumers(root: Path) -> None:
    sensors_path = root / S.SENSORS_REL
    gates_path = root / "institutio" / "governance" / "gates.yaml"
    try:
        sensors = (yaml.safe_load(sensors_path.read_text(encoding="utf-8")) or {}).get("sensors") or {}
    except (OSError, yaml.YAMLError):
        sensors = {}
    runs_sensor = any(
        "scripts/schedule-utilization.py" in str(step.get("command", ""))
        for s in sensors.values()
        if isinstance(s, dict)
        for step in (s.get("steps") or [])
        if isinstance(step, dict)
    )
    if not runs_sensor:
        fail(
            "F",
            "sensors.yaml has no step running scripts/schedule-utilization.py — the registry would be audited by nothing",
        )
    try:
        gates = (yaml.safe_load(gates_path.read_text(encoding="utf-8")) or {}).get("gates") or {}
    except (OSError, yaml.YAMLError):
        gates = {}
    if "check-schedules" not in gates:
        fail("F", "gates.yaml does not register check-schedules — this predicate would run nowhere in CI")


REGISTRY_READERS = frozenset(
    {"scripts/check-schedules.py", "scripts/schedule-utilization.py", "scripts/schedule-census.py"}
)


def check_readers(root: Path) -> None:
    """G: the registry's readers are an allowlist, and none of them may be an outbound effector."""
    readers: set[str] = set()
    for path in sorted((root / "scripts").glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if "import _schedules" in text or "from _schedules" in text:
            readers.add(f"scripts/{path.name}")
    for extra in sorted(readers - REGISTRY_READERS):
        fail(
            "G",
            f"{extra} reads the SCHEDULES registry but is not an allowlisted reader — a reader that can start, retry or deploy a run would make the registry a scheduler",
        )
    effectors_path = root / "institutio" / "governance" / "outbound-effectors.yaml"
    try:
        effectors_text = effectors_path.read_text(encoding="utf-8")
    except OSError:
        effectors_text = ""
    for reader in sorted(readers & REGISTRY_READERS):
        if reader in effectors_text:
            fail("G", f"{reader} is named in outbound-effectors.yaml — a registry reader must never be an effector")


def slot_map(registry: dict, jobs: list[S.Job], day: date) -> list[dict]:
    rows: list[dict] = []
    violations = stagger_violations(registry, jobs)
    for job in jobs:
        if not job.crons:
            continue
        tz = S.resolve_tz(job.tz)
        for c in job.crons:
            cron = S.parse_cron(c)
            fires = S.fires_on_utc_day(cron, tz, day)
            if len(fires) > 24:
                rows.append(
                    {
                        "utc": "every " + ("minute" if len(fires) == 1440 else f"{1440 // len(fires)} min"),
                        "sort": "00:00",
                        "job": job.id,
                        "plane": job.plane,
                        "cron": c,
                        "tz": job.tz,
                        "enabled": job.enabled,
                        "fires": len(fires),
                        "flags": "",
                    }
                )
                continue
            for when in fires:
                flags = ",".join(sorted(r.split(":")[-1] for r in violations if r.startswith(f"{job.plane}:{job.id}:")))
                rows.append(
                    {
                        "utc": when.strftime("%H:%M"),
                        "sort": when.strftime("%H:%M"),
                        "job": job.id,
                        "plane": job.plane,
                        "cron": c,
                        "tz": job.tz,
                        "enabled": job.enabled,
                        "fires": 1,
                        "flags": flags,
                    }
                )
    rows.sort(key=lambda r: (r["sort"], r["plane"], r["job"]))
    return rows


def print_slot_map(registry: dict, jobs: list[S.Job], day: date, compact: bool = False) -> None:
    """The 24h UTC map. --compact folds a job that fires more than once a day into one row
    ('hourly at :17 (24/day)') so the table reads as a day, not as a log."""
    rows = slot_map(registry, jobs, day)
    if compact:
        folded: dict[tuple[str, str], list[dict]] = {}
        for r in rows:
            folded.setdefault((r["job"], r["cron"]), []).append(r)
        rows = []
        for (job, cron), group in folded.items():
            first = dict(group[0])
            n = sum(g["fires"] for g in group)
            if len(group) > 1:
                minute = cron.split()[0]
                first["utc"] = (
                    f"{group[0]['utc']}–{group[-1]['utc']} ({n}/day at :{minute.zfill(2)})"
                    if minute.isdigit()
                    else f"{n}/day"
                )
                first["sort"] = group[0]["sort"]
            rows.append(first)
        rows.sort(key=lambda r: (r["sort"], r["plane"], r["job"]))
    print(f"| UTC | job | plane | cron | tz | enabled | flags |  _(fires on {day.isoformat()})_")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['utc']} | {r['job']} | {r['plane']} | `{r['cron']}` | {r['tz']} | {'yes' if r['enabled'] else 'NO'} | {r['flags']} |"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--slot-map", action="store_true", help="print the 24h UTC slot map and exit 0")
    parser.add_argument("--day", default=None, help="UTC day for --slot-map (YYYY-MM-DD; default today)")
    parser.add_argument("--compact", action="store_true", help="with --slot-map: one row per job, hourly jobs folded")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    _failures.clear()
    _advisories.clear()
    root = Path(args.root)
    try:
        registry = S.load_registry(root, args.registry)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"FAILED: check-schedules — cannot read registry: {exc}")
        return 1
    derived = S.derived_jobs(root, registry)
    declared = S.declared_jobs(registry)
    jobs = derived + declared
    for job in derived:
        cadence_env = job.extra.get("cadence_env")
        default_beats = job.extra.get("cadence_default_beats")
        if cadence_env and job.cadence_beats != default_beats:
            advise(
                "B",
                f"{job.id}: cadence override {cadence_env}={job.cadence_beats} beats "
                f"(registry default {default_beats}; worst-case {job.cadence_hours}h)",
            )
    if args.slot_map:
        if not args.quiet:
            for advisory in _advisories:
                print(f"  · {advisory}")
        day = date.fromisoformat(args.day) if args.day else datetime.now(timezone.utc).date()
        print_slot_map(registry, jobs, day, compact=args.compact)
        return 0
    check_schema(registry)
    schema_valid = not _failures
    check_derived(root, registry, derived)
    check_claude_parity(root, registry, derived)
    check_sibling_parity(registry, declared, dict(os.environ), Path.home())
    check_stagger(registry, jobs, S.load_baseline(root))
    check_launch_authority(registry)
    check_consumers(root)
    check_readers(root)
    if args.json:
        print(
            json.dumps(
                {
                    "schema_valid": schema_valid,
                    "inventory_valid": not _failures,
                    "operational_readiness": "unverified",
                    "audit_only": registry.get("audit_only", True),
                    "failures": _failures,
                    "advisories": _advisories,
                },
                sort_keys=True,
            )
        )
        return int(bool(_failures))
    if not args.quiet:
        for a in _advisories:
            print(f"  · {a}")
    if _failures:
        print("SCHEDULES DRIFT — registry does not match the estate:")
        for f in _failures:
            print(f"  ✗ {f}")
        print("FAILED: check-schedules")
        return 1
    planes = registry.get("planes") or {}
    print(
        f"check-schedules: OK — {len(planes)} planes, {len(declared)} declared + {len(derived)} derived jobs; "
        f"schema valid, derivations resolve, claude parity, sibling parity, stagger ratchet, consumers wired, readers allowlisted"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
