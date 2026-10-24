#!/usr/bin/env python3
"""SCHEDULES registry drift predicate — hold institutio/governance/schedules.yaml to the estate.

The registry declares every scheduler plane the operator runs (its allotment, surface, evidence and
owner) and the jobs scheduled against it. Planes limen itself configures are DERIVED from their
source files by scripts/_schedules.py (workflows, sensors.yaml cadences, cloud-routines.json + the
newest claude-triggers snapshot receipt); planes another repository operates are declared rows
with a `source_of_truth` pointer. Exit 0 ⟺ no drift.

Named checks (the check-*.py ratchet discipline):
  A schema        — plane/job required fields, enums, every cron parses (5 fields, no names), tz resolves;
                    census planes: jobs_source carrier/scope/visibility, `ceilings` keys, declared_off rows
                    select by FACT (`match: {archived, state}` + per-state `ceiling`), residual gh-workflow
                    planes partition by visibility exactly; workflows planes: every declared_off `file` still
                    exists (a row for a reaped file has rotted); with a census receipt on this host, every
                    ceiling holds (count above = undeclared growth, FAIL; below = advisory "lower to N"),
                    every off-state workflow is owned by a match row, and declared_off ceilings hold
  B derived       — every `jobs_source` resolves and yields ≥1 row; no declared row duplicates a derived plane;
                    a census locator is git-ignored (R1: the receipt names private repositories) and its
                    absence is "not this host", never drift
  C claude parity — every enabled cloud-routines.json routine appears in the newest snapshot receipt by
                    `routine`, its live cron's cadence class matches the manifest cadence, and every live
                    contracted routine appears in the manifest (no snapshot ⇒ unverifiable here, not drift)
  D sibling parity— rows for 4444J99/ops, 4444J99/ops-witness and the Cloudflare manifest agree with the
                    sibling clone when one is present on this host (LIMEN_OPS_ROOT / LIMEN_OPS_WITNESS_ROOT /
                    $LIMEN_WORKDIR/<repo> / ~/Workspace/<repo>); absent ⇒ unverifiable here, not drift
  E stagger       — github-provider planes limen configures or projects: no enabled job on the hour and no two
                    jobs in one plane sharing a minute, except lines in schedule-stagger-baseline.txt
                    (shrink-only: a listed line whose violation is gone is itself a failure, so the baseline
                    cannot rot); census planes are exempt here — their on-the-hour / shared-minute counts are
                    owned by `ceilings` (A) and may never rise (J)
  F consumers     — sensors.yaml runs scripts/schedule-utilization.py; gates.yaml registers this predicate
  G not-a-scheduler — every reader of the registry (any scripts/*.py importing _schedules) is on the
                    declared allowlist, and none of them is an outbound effector: a new reader must be
                    added here deliberately, which is how "nothing that reads this can start a run" stays
                    a predicate instead of prose
  H redaction     — with a census receipt on this host: no committed registry line (schedules.yaml, the
                    stagger baseline) names a private repository the receipt lists — slug or compound bare
                    name — except the disclosed projection tokens (authority.owner_repo, job ids on authority
                    planes); the failure names file:line, never the token (R1)
  J ratchet       — against the merge-base with origin/main: a census plane's on-the-hour and shared-minute
                    ceilings and every declared_off per-state ceiling may only fall; `active` may rise

  python3 scripts/check-schedules.py              # gate (CI): exit 1 on any drift
  python3 scripts/check-schedules.py --slot-map   # print the 24h UTC slot map of every clock-scheduled job
                                                 # (census planes fold to counts per slot — never ids)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

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
        policy = _require("A", where, plane, "fill_policy", allowed=S.PLANE_FILL_POLICIES)
        floor = plane.get("floor")
        if policy == "floor" and not (isinstance(floor, int) and floor > 0):
            fail("A", f"{where}: fill_policy floor needs a positive integer `floor`")
        allot = _require("A", where, plane, "allotment", kind=dict)
        if isinstance(allot, dict):
            _require("A", f"{where}.allotment", allot, "window", allowed=S.PLANE_WINDOWS)
            _require("A", f"{where}.allotment", allot, "entitlement", allowed=S.PLANE_ENTITLEMENTS)
            _require("A", f"{where}.allotment", allot, "source", kind=str)
            runs = allot.get("runs")
            if runs is not None and not (isinstance(runs, int) and runs >= 0):
                fail("A", f"{where}.allotment: runs must be a non-negative int or null")
        evidence = _require("A", where, plane, "evidence", kind=dict)
        if isinstance(evidence, dict):
            kind = _require("A", f"{where}.evidence", evidence, "kind", allowed=S.EVIDENCE_KINDS)
            if kind != "none" and not evidence.get("locator"):
                fail("A", f"{where}.evidence: kind {kind} needs a locator")
        src = plane.get("jobs_source")
        if src is not None:
            if not isinstance(src, dict) or src.get("kind") not in S.JOBS_SOURCE_KINDS or not src.get("locator"):
                fail("A", f"{where}: jobs_source must be {{kind ∈ {sorted(S.JOBS_SOURCE_KINDS)}, locator}}")
            elif src.get("kind") == "census":
                _validate_census_source(where, plane, src)
        if plane.get("ceilings") is not None and not S.is_census_plane(plane):
            fail("A", f"{where}: `ceilings` belongs to census planes only (other planes are ratcheted by the stagger baseline)")
        _validate_declared_off(where, plane)
    _validate_residual_partition(planes)
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


def _validate_census_source(where: str, plane: dict, src: dict) -> None:
    carrier = src.get("carrier", "gh-workflow")
    if carrier not in S.CENSUS_CARRIERS:
        fail("A", f"{where}: jobs_source.carrier={carrier!r} not in {sorted(S.CENSUS_CARRIERS)}")
    if src.get("scope", "residual") not in S.CENSUS_SCOPES:
        fail("A", f"{where}: jobs_source.scope={src.get('scope')!r} not in {sorted(S.CENSUS_SCOPES)}")
    visibility = src.get("visibility")
    if visibility is not None and visibility not in S.CENSUS_VISIBILITIES:
        fail("A", f"{where}: jobs_source.visibility={visibility!r} not in {sorted(S.CENSUS_VISIBILITIES)}")
    if visibility is not None and carrier != "gh-workflow":
        fail("A", f"{where}: jobs_source.visibility applies to the gh-workflow carrier only")
    ceilings = plane.get("ceilings")
    if ceilings is not None:
        if not isinstance(ceilings, dict) or not ceilings:
            fail("A", f"{where}: `ceilings` must be a non-empty mapping of {sorted(S.CEILING_KEYS)} to ints ≥ 0")
        else:
            for key, value in ceilings.items():
                if key not in S.CEILING_KEYS:
                    fail("A", f"{where}: ceilings key {key!r} not in {sorted(S.CEILING_KEYS)}")
                elif not (isinstance(value, int) and not isinstance(value, bool) and value >= 0):
                    fail("A", f"{where}: ceilings.{key} must be an int ≥ 0")
    evidence = plane.get("evidence") if isinstance(plane.get("evidence"), dict) else {}
    if evidence.get("kind") not in {"census-receipt", "launchctl", "none"}:
        fail("A", f"{where}: a census plane's evidence kind must be census-receipt, launchctl or none (its rows are read from the receipt, never from gh)")


def _validate_declared_off(where: str, plane: dict) -> None:
    rows = plane.get("declared_off")
    if rows is None:
        return
    kind = (plane.get("jobs_source") or {}).get("kind") if isinstance(plane.get("jobs_source"), dict) else None
    if kind not in {"workflows", "census"}:
        fail("A", f"{where}: declared_off belongs to workflows and census planes only")
        return
    if not isinstance(rows, list):
        fail("A", f"{where}: declared_off must be a list")
        return
    for i, row in enumerate(rows):
        rw = f"{where}.declared_off[{i}]"
        if not isinstance(row, dict):
            fail("A", f"{rw}: not a mapping")
            continue
        for key in ("since", "reason"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                fail("A", f"{rw}: `{key}` must be a non-empty string")
        if kind == "workflows":
            if not isinstance(row.get("file"), str) or "match" in row or "ceiling" in row:
                fail("A", f"{rw}: a workflows plane declares off-switches by `file` (match/ceiling are census-plane forms)")
            continue
        match = row.get("match")
        if "file" in row or not isinstance(match, dict) or not match:
            fail("A", f"{rw}: a census plane declares off-switches by FACT — `match: {{archived: bool, state: [..]}}`, never by name")
            continue
        extra_keys = set(match) - S.DECLARED_OFF_MATCH_KEYS
        if extra_keys:
            fail("A", f"{rw}: match keys {sorted(extra_keys)} not in {sorted(S.DECLARED_OFF_MATCH_KEYS)}")
        if "archived" in match and not isinstance(match["archived"], bool):
            fail("A", f"{rw}: match.archived must be a bool")
        states: list[str] = []
        if "state" in match:
            raw = match["state"] if isinstance(match["state"], list) else [match["state"]]
            states = [str(x) for x in raw]
            bad = sorted(set(states) - S.WORKFLOW_OFF_STATES)
            if bad:
                fail("A", f"{rw}: match.state {bad} not in {sorted(S.WORKFLOW_OFF_STATES)} (an `active` workflow is never declared off)")
        if not states and match.get("archived") is not True:
            fail("A", f"{rw}: a match must name off states or select `archived: true` — `archived: false` alone owns every live off-switch blindly")
        ceiling = row.get("ceiling")
        if ceiling is not None:
            if not isinstance(ceiling, dict) or not ceiling:
                fail("A", f"{rw}: `ceiling` must be a mapping of matched state → int ≥ 0")
            else:
                for key, value in ceiling.items():
                    if key not in states:
                        fail("A", f"{rw}: ceiling key {key!r} is not one of this row's matched states {states}")
                    elif not (isinstance(value, int) and not isinstance(value, bool) and value >= 0):
                        fail("A", f"{rw}: ceiling.{key} must be an int ≥ 0")


def _validate_residual_partition(planes: dict) -> None:
    """Residual gh-workflow census planes own 'everything outside the specific planes' — so either one plane owns
    it whole (no visibility) or the visibilities partition it: each of private/public exactly once, no bare plane."""
    by_visibility: dict[str | None, list[str]] = defaultdict(list)
    for pid, plane in planes.items():
        if not S.is_census_plane(plane):
            continue
        src = plane["jobs_source"]
        if src.get("carrier", "gh-workflow") == "gh-workflow" and src.get("scope", "residual") == "residual":
            by_visibility[src.get("visibility")].append(pid)
    if not by_visibility:
        return
    for vis, pids in by_visibility.items():
        if len(pids) > 1:
            fail("A", f"planes {pids} both derive the residual gh-workflow fleet for visibility {vis!r} — one owner per fact")
    if None in by_visibility and len(by_visibility) > 1:
        fail("A", f"plane {by_visibility[None]} derives the whole residual fleet while {sorted(k for k in by_visibility if k)} split it by visibility — overlap")
    if None not in by_visibility and set(by_visibility) != S.CENSUS_VISIBILITIES:
        missing = sorted(S.CENSUS_VISIBILITIES - set(by_visibility))
        fail("A", f"residual gh-workflow planes cover {sorted(by_visibility)} only — a {missing} cron would be owned by nobody; declare the missing visibility")


def _git(root: Path, *args: str) -> tuple[int, str]:
    try:
        run = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return -1, ""
    return run.returncode, run.stdout


def _check_census_source(root: Path, pid: str, plane: dict, src: dict, derived: list[S.Job]) -> None:
    locator = str(src.get("locator") or S.CENSUS_REL)
    path, data, state = S.load_census_receipt(root, locator)
    rc, _ = _git(root, "check-ignore", "-q", locator)
    if rc == 1:
        fail("B", f"plane {pid}: census locator {locator} is not git-ignored — the receipt names private repositories (R1); add it to logs/.gitignore")
    elif rc != 0:
        advise("B", f"plane {pid}: cannot ask git whether {locator} is ignored (not a repository here) — unverifiable here, not drift")
    if state == "absent":
        advise("B", f"plane {pid}: no census receipt at {locator} on this host — census planes derive zero rows here; the census runs where gh carries the owner's auth (not this host, not drift)")
        return
    if data is None:
        fail("B", f"plane {pid}: {path} is {state} — not a {S.CENSUS_SCHEMA} receipt; the locator points at something that is not the census")
        return
    rows = [j for j in derived if j.plane == pid]
    if not rows:
        fail("B", f"plane {pid}: a readable census receipt ({state}) derived zero rows — the carrier/scope/visibility selector selects nothing")
        return
    unparseable = sum(1 for j in rows if j.extra.get("unparseable_crons"))
    if unparseable:
        advise("B", f"plane {pid}: {unparseable} fleet workflow(s) carry a cron this registry's parser rejects — counted as active, excluded from stagger counts (facts of the fleet, not rows to fix here)")


def check_derived(root: Path, registry: dict, derived: list[S.Job]) -> None:
    for pid, plane in (registry.get("planes") or {}).items():
        src = plane.get("jobs_source") if isinstance(plane, dict) else None
        if not isinstance(src, dict):
            continue
        if src.get("kind") == "census":
            _check_census_source(root, pid, plane, src, derived)
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
        if plane.get("provider") != "github" or not job.enabled or S.is_census_plane(plane):
            continue  # census planes: on-the-hour / shared-minute are owned by `ceilings` (A) and ratcheted by J
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


def check_declared_off_rot(root: Path, registry: dict) -> None:
    """A-off: a workflows plane's declared_off `file` must still exist — a row for a reaped file has rotted."""
    for pid, plane in (registry.get("planes") or {}).items():
        if not isinstance(plane, dict):
            continue
        src = plane.get("jobs_source") if isinstance(plane.get("jobs_source"), dict) else None
        if not src or src.get("kind") != "workflows":
            continue
        wf_dir = root / str(src.get("locator") or S.WORKFLOWS_REL)
        for row in plane.get("declared_off") or []:
            if isinstance(row, dict) and isinstance(row.get("file"), str) and not (wf_dir / row["file"]).exists():
                fail("A", f"plane {pid}: declared_off names {row['file']} but {src.get('locator')}/{row['file']} no longer exists — delete the row (the declaration rotted)")


def _census_receipt(root: Path, registry: dict) -> tuple[dict | None, str, Path | None]:
    """The one receipt every census plane in this registry reads (they share a locator by construction)."""
    for plane in (registry.get("planes") or {}).values():
        if S.is_census_plane(plane):
            path, data, state = S.load_census_receipt(root, plane["jobs_source"].get("locator"))
            return data, state, path
    return None, "no-census-planes", None


def check_census(root: Path, registry: dict, jobs: list[S.Job], now: datetime) -> None:
    """A (census): with a receipt on this host, every ceiling holds and every off-state row is owned."""
    data, state, path = _census_receipt(root, registry)
    if data is None:
        return
    generated = S.census_generated_at(data)
    age = f"{(now - generated).days}d old" if generated else "undated"
    advise("A", f"census receipt {path.name if path else ''} is {state} ({age}); ceilings compared against it (counts only)")
    for pid, plane in (registry.get("planes") or {}).items():
        if not S.is_census_plane(plane):
            continue
        rows = [j for j in jobs if j.plane == pid]
        counts = S.census_plane_counts(rows)
        for key, cap in (plane.get("ceilings") or {}).items():
            if not isinstance(cap, int) or key not in counts:
                continue
            if counts[key] > cap:
                fail("A", f"plane {pid}: {key} is {counts[key]}, above its ceiling {cap} — undeclared growth; retire or disable what grew (receipt-backed reap), or raise `active` deliberately ({key} ceilings other than active may never rise, check J)")
            elif counts[key] < cap:
                advise("A", f"plane {pid}: {key} is {counts[key]}, below its ceiling {cap} — lower ceilings.{key} to {counts[key]} (shrink-only ratchet)")
        per_rule, undeclared, unverified = S.census_off_counts(plane, rows)
        for i, row in enumerate(r for r in plane.get("declared_off") or [] if isinstance(r, dict) and isinstance(r.get("match"), dict)):
            for state_key, cap in (row.get("ceiling") or {}).items():
                n = per_rule[i].get(str(state_key), 0) if i < len(per_rule) else 0
                if n > cap:
                    fail("A", f"plane {pid}: declared_off[{i}] counts {n} {state_key} workflow(s), above its ceiling {cap} — a new off-switch nobody owns")
                elif n < cap:
                    advise("A", f"plane {pid}: declared_off[{i}] counts {n} {state_key}, below its ceiling {cap} — lower it to {n}")
        if undeclared:
            states = Counter(str(j.extra.get("state")) + (" (archived)" if j.extra.get("archived") else "") for j in undeclared)
            fail("A", f"plane {pid}: {len(undeclared)} off-state workflow(s) no declared_off match owns — {dict(states)}; add a match row (by fact, never by name)")
        if unverified:
            advise("A", f"plane {pid}: {unverified} live workflow(s) whose Actions state the census could not read — unverified, counted neither on nor off")


_PRIVATE_SKIP_BARE = re.compile(r"^[A-Za-z0-9]+$")  # single-word names are English words too; only compound bare names are checked


def check_redaction(root: Path, registry: dict) -> None:
    """H: no committed registry line names a private repository the census lists (R1)."""
    data, _state, _path = _census_receipt(root, registry)
    if data is None:
        if _state != "no-census-planes":
            advise("H", "no census receipt on this host — redaction unverifiable here, not drift")
        return
    disclosed = S.disclosed_repo_tokens(registry)
    private = sorted({r["repo"] for r in (data.get("repos") or []) if isinstance(r, dict) and r.get("private") and isinstance(r.get("repo"), str)})
    patterns: list[re.Pattern[str]] = []
    skipped_bare = 0
    for slug in private:
        if slug not in disclosed:
            patterns.append(re.compile(r"(?<![\w-])" + re.escape(slug) + r"(?![\w.-])"))
        name = slug.split("/", 1)[1]
        if name in disclosed:
            continue
        if _PRIVATE_SKIP_BARE.match(name):
            skipped_bare += 1
            continue
        patterns.append(re.compile(r"(?<![\w./-])" + re.escape(name) + r"(?![\w.-])"))
    for rel in (S.REGISTRY_REL, S.BASELINE_REL):
        try:
            lines = (root / rel).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if any(p.search(line) for p in patterns):
                fail("H", f"{rel}:{n} names a private repository the census lists (token withheld here, R1) — fleet membership is a fact selector, never a name")
    if skipped_bare:
        advise("H", f"{skipped_bare} private repositories have single-word names that double as prose — only their owner/name slugs were checked")


def _registry_at(root: Path, ref: str) -> dict | None:
    rc, text = _git(root, "show", f"{ref}:{S.REGISTRY_REL.as_posix()}")
    if rc != 0:
        return None
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def _match_key(row: dict) -> str:
    return json.dumps(row.get("match"), sort_keys=True)


def check_ratchet_direction(root: Path, registry: dict) -> None:
    """J: on-the-hour / shared-minute ceilings and declared_off per-state ceilings never rise against the merge-base."""
    census_planes = {pid: p for pid, p in (registry.get("planes") or {}).items() if S.is_census_plane(p)}
    if not census_planes:
        return
    rc, base = _git(root, "merge-base", "HEAD", "origin/main")
    base = base.strip()
    if rc != 0 or not base:
        advise("J", "no merge-base with origin/main here — ceiling ratchet direction unverifiable here, not drift")
        return
    old = _registry_at(root, base)
    if old is None:
        return  # the registry did not exist at the base: every ceiling is new
    for pid, plane in census_planes.items():
        before = (old.get("planes") or {}).get(pid)
        if not isinstance(before, dict):
            continue
        old_ceilings = before.get("ceilings") or {}
        for key in S.RATCHET_CEILING_KEYS:
            new_v, old_v = (plane.get("ceilings") or {}).get(key), old_ceilings.get(key)
            if isinstance(new_v, int) and isinstance(old_v, int) and new_v > old_v:
                fail("J", f"plane {pid}: ceilings.{key} rose {old_v} → {new_v} against {base[:9]} — this ceiling only falls; a new on-the-hour or shared-minute cron is a stagger regression to fix in its repository")
        old_rules = {_match_key(r): r for r in before.get("declared_off") or [] if isinstance(r, dict) and isinstance(r.get("match"), dict)}
        for row in plane.get("declared_off") or []:
            if not (isinstance(row, dict) and isinstance(row.get("match"), dict)):
                continue
            prior = old_rules.get(_match_key(row))
            if prior is None:
                continue
            for state_key, new_v in (row.get("ceiling") or {}).items():
                old_v = (prior.get("ceiling") or {}).get(state_key)
                if isinstance(new_v, int) and isinstance(old_v, int) and new_v > old_v:
                    fail("J", f"plane {pid}: declared_off ceiling {state_key} rose {old_v} → {new_v} against {base[:9]} — an off-switch count only falls (reap or re-enable), it is never re-declared upward")


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
            try:
                cron = S.parse_cron(c)
            except S.CronError:
                continue  # a fleet cron this parser rejects (names, 6 fields) is a fact of the fleet, not a slot
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
    census = {pid for pid, p in (registry.get("planes") or {}).items() if S.is_census_plane(p)}
    if census:
        # R2: census planes fold to counts per slot — how many ENABLED fleet workflows fire there — never ids.
        # Off-switches are owned by declared_off, not by a slot, so disabled/archived rows are not folded in.
        kept = [r for r in rows if r["plane"] not in census]
        folded: dict[tuple[str, str, str], list[int]] = defaultdict(lambda: [0, 0])
        for r in rows:
            if r["plane"] in census and r["enabled"]:
                cell = folded[(r["plane"], r["utc"], r["sort"])]
                cell[0] += 1
                cell[1] += r["fires"]
        for (plane, utc, sort), (workflows, fires) in folded.items():
            kept.append(
                {"utc": utc, "sort": sort, "job": f"{workflows} fleet workflow{'s' if workflows != 1 else ''} (counts only)", "plane": plane, "cron": "—", "tz": "UTC", "enabled": True, "fires": fires, "flags": ""}
            )
        rows = kept
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
    parser.add_argument("--slot-map", action="store_true", help="print the 24h UTC slot map and exit 0")
    parser.add_argument("--day", default=None, help="UTC day for --slot-map (YYYY-MM-DD; default today)")
    parser.add_argument("--compact", action="store_true", help="with --slot-map: one row per job, hourly jobs folded")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.root)
    try:
        registry = S.load_registry(root)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"FAILED: check-schedules — cannot read registry: {exc}")
        return 1
    derived = S.derived_jobs(root, registry)
    declared = S.declared_jobs(registry)
    jobs = derived + declared
    if args.slot_map:
        day = date.fromisoformat(args.day) if args.day else datetime.now(timezone.utc).date()
        print_slot_map(registry, jobs, day, compact=args.compact)
        return 0
    check_schema(registry)
    check_derived(root, registry, derived)
    check_declared_off_rot(root, registry)
    check_census(root, registry, jobs, datetime.now(timezone.utc))
    check_claude_parity(root, registry, derived)
    check_sibling_parity(registry, declared, dict(os.environ), Path.home())
    check_stagger(registry, jobs, S.load_baseline(root))
    check_consumers(root)
    check_readers(root)
    check_redaction(root, registry)
    check_ratchet_direction(root, registry)
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
        f"schema valid, derivations resolve, census ceilings, claude parity, sibling parity, stagger ratchet, consumers wired, readers allowlisted, redaction, ratchet direction"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
