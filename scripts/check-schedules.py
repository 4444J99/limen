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
                    planes partition by visibility exactly, a census plane's evidence locator is its
                    jobs_source locator, and once a census plane exists every workflows plane names its own
                    repository in a gh-actions-runs locator (the residual selector covers it from there);
                    workflows planes: every declared_off `file` still exists (a row for a reaped file has
                    rotted); with a census receipt on this host, every ceiling holds (count above = undeclared
                    growth, FAIL on any data-bearing receipt since an undercount cannot overshoot; below =
                    advisory "lower to N" only when the receipt is complete and the plane has no partial or
                    unverified rows — an undercount is never a floor), every off-state workflow is owned by a
                    match row, and declared_off ceilings hold
  B derived       — every `jobs_source` resolves and yields ≥1 row; no declared row duplicates a derived plane;
                    a census locator is git-ignored (R1: the receipt names private repositories); an absent
                    receipt is "not this host", an incomplete or stale one is unmeasured, and a present receipt
                    that derives zero rows for a plane is the ratchet's goal state (advisory), never drift
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
  H launch authority — every logical job (jobs / logical_launch_authorities rows with `logical_job`) names
                    exactly one launch_authority; two authorities for one logical job is drift
  I redaction     — with a census receipt on this host: no committed registry line (schedules.yaml, the
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
from urllib.parse import urlsplit

import yaml

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _schedules as S  # noqa: E402


def _census_max_age_days() -> int:
    try:
        value = int(os.environ.get("LIMEN_SCHEDULE_CENSUS_MAX_AGE_DAYS", "") or 8)
    except ValueError:
        return 8
    return value if value > 0 else 8

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
            elif src.get("kind") == "census":
                _validate_census_source(where, plane, src)
        if plane.get("ceilings") is not None and not S.is_census_plane(plane):
            fail("A", f"{where}: `ceilings` belongs to census planes only (other planes are ratcheted by the stagger baseline)")
        _validate_declared_off(where, plane)
    _validate_residual_partition(planes)
    if any(S.is_census_plane(p) for p in planes.values()):
        for pid, plane in planes.items():
            if not isinstance(plane, dict) or (plane.get("jobs_source") or {}).get("kind") != "workflows":
                continue
            evidence = plane.get("evidence") if isinstance(plane.get("evidence"), dict) else {}
            repo = S.repo_of_locator(evidence.get("locator")) if evidence.get("kind") in S.REPO_LOCATOR_EVIDENCE_KINDS else None
            if not repo:
                fail("A", f"plane {pid}: a workflows plane must name its own repository in a gh-actions-runs evidence locator (owner/name) once census planes exist — the residual selector covers it from there, and nothing else keeps its crons out of the fleet")
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
    if evidence.get("kind") == "census-receipt" and str(evidence.get("locator") or "") != str(src.get("locator") or ""):
        fail("A", f"{where}: evidence.locator {evidence.get('locator')!r} differs from jobs_source.locator {src.get('locator')!r} — the sensor would read one receipt while the rows derive from another")


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
    path, data, state = S.load_census_receipt(root, locator, max_age_days=_census_max_age_days())
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
    if state != "present":
        unread = S.census_unread(data)
        advise("B", f"plane {pid}: census receipt is {state} ({unread or 'aged out'}) — {len(rows)} row(s) derive from it but nothing is concluded about their floor (unmeasured, not drift)")
    elif not rows:
        advise("B", f"plane {pid}: a complete census receipt derived zero rows — the selector selects nothing, which is the ratchet's goal state; retire the plane or keep it as a guard")
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
            path, data, state = S.load_census_receipt(root, plane["jobs_source"].get("locator"), max_age_days=_census_max_age_days())
            return data, state, path
    return None, "no-census-planes", None


def _is_cap(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def check_census(root: Path, registry: dict, jobs: list[S.Job], now: datetime) -> None:
    """A (census): with a receipt on this host, every ceiling holds and every off-state row is owned. A count
    above a ceiling fails on any data-bearing receipt — an incomplete or stale receipt can only undercount, so
    the overshoot is real. "Lower to N" is advised only from a complete receipt with no partial or unverified
    rows in the plane: the ratchet only falls, and lowering from an undercount makes the next complete census
    red on unchanged repositories."""
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
        unmeasured = S.census_floor_unmeasured(data, rows)
        if state != "present":
            unmeasured = {"receipt_" + state: 1, **unmeasured}
        floor_note = f"floor unmeasured ({', '.join(f'{k} {v}' for k, v in sorted(unmeasured.items()))}) — do not lower" if unmeasured else None
        ceilings = plane.get("ceilings") if isinstance(plane.get("ceilings"), dict) else {}
        for key, cap in ceilings.items():
            if not _is_cap(cap) or key not in counts:
                continue
            if counts[key] > cap:
                fail("A", f"plane {pid}: {key} is {counts[key]}, above its ceiling {cap} — undeclared growth; retire or disable what grew (receipt-backed reap), or raise `active` deliberately ({key} ceilings other than active may never rise, check J)")
            elif counts[key] < cap:
                advise("A", f"plane {pid}: {key} is {counts[key]}, below its ceiling {cap} — " + (floor_note or f"lower ceilings.{key} to {counts[key]} (shrink-only ratchet)"))
        per_rule, undeclared, unverified = S.census_off_counts(plane, rows)
        for i, row in enumerate(r for r in plane.get("declared_off") or [] if isinstance(r, dict) and isinstance(r.get("match"), dict)):
            ceiling = row.get("ceiling") if isinstance(row.get("ceiling"), dict) else {}
            for state_key, cap in ceiling.items():
                if not _is_cap(cap):
                    continue
                n = per_rule[i].get(str(state_key), 0) if i < len(per_rule) else 0
                if n > cap:
                    fail("A", f"plane {pid}: declared_off[{i}] counts {n} {state_key} workflow(s), above its ceiling {cap} — a new off-switch nobody owns")
                elif n < cap:
                    advise("A", f"plane {pid}: declared_off[{i}] counts {n} {state_key}, below its ceiling {cap} — " + (floor_note or f"lower it to {n}"))
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
            advise("I", "no census receipt on this host — redaction unverifiable here, not drift")
        return
    disclosed = S.disclosed_repo_tokens(registry)
    private = sorted({r["repo"] for r in (data.get("repos") or []) if isinstance(r, dict) and r.get("private") and isinstance(r.get("repo"), str)})
    patterns: list[re.Pattern[str]] = []
    skipped_bare = 0
    # A token ends where a word character, `-`, or `.<word>` would continue it: `name.` at a sentence end and
    # `name.git` are still the name; `name.yml` is a different token. Case-insensitive: GitHub names are.
    tail = r"(?:\.git)?(?!(?:[\w-]|\.[\w-]))"
    for slug in private:
        if slug not in disclosed:
            patterns.append(re.compile(r"(?<![\w-])" + re.escape(slug) + tail, re.I))
        name = slug.split("/", 1)[1]
        if name in disclosed:
            continue
        if _PRIVATE_SKIP_BARE.match(name):
            skipped_bare += 1
            continue
        patterns.append(re.compile(r"(?<![\w./-])" + re.escape(name) + tail, re.I))
    for rel in (S.REGISTRY_REL, S.BASELINE_REL):
        try:
            lines = (root / rel).read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if any(p.search(line) for p in patterns):
                fail("I", f"{rel}:{n} names a private repository the census lists (token withheld here, R1) — fleet membership is a fact selector, never a name")
    if skipped_bare:
        advise("I", f"{skipped_bare} private repositories have single-word names that double as prose — only their owner/name slugs were checked")


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
    """A declared_off rule's identity across commits: its match, normalized (state as a sorted list of str,
    `archived: false` the same as absent) so reordering or respelling the selector cannot shake off its ceiling."""
    match = row.get("match") if isinstance(row.get("match"), dict) else {}
    norm: dict = {}
    if match.get("archived") is True:
        norm["archived"] = True
    if "state" in match:
        raw = match["state"] if isinstance(match["state"], list) else [match["state"]]
        norm["state"] = sorted(str(x) for x in raw)
    return json.dumps(norm, sort_keys=True)


def _rule_ceilings(row: dict) -> dict[str, int]:
    ceiling = row.get("ceiling") if isinstance(row.get("ceiling"), dict) else {}
    return {str(k): v for k, v in ceiling.items() if _is_cap(v)}


def check_ratchet_direction(root: Path, registry: dict) -> None:
    """J: on-the-hour / shared-minute ceilings and declared_off per-state ceilings never rise against the merge-base.
    Continuity is by FACT: a plane renamed but deriving the same carrier/scope/visibility inherits the old ratchet,
    and a plane may leave the registry only once every ratchet ceiling it carried is 0."""
    census_planes = {pid: p for pid, p in (registry.get("planes") or {}).items() if S.is_census_plane(p)}
    rc, base = _git(root, "merge-base", "HEAD", "origin/main")
    base = base.strip()
    if rc != 0 or not base:
        if census_planes:
            advise("J", "no merge-base with origin/main here — ceiling ratchet direction unverifiable here, not drift")
        return
    old = _registry_at(root, base)
    if old is None:
        return  # the registry did not exist at the base: every ceiling is new
    old_census = {pid: p for pid, p in (old.get("planes") or {}).items() if isinstance(p, dict) and S.is_census_plane(p)}
    by_fact = {_census_fact(p): pid for pid, p in census_planes.items()}
    for old_pid, before in old_census.items():
        pid = old_pid if old_pid in census_planes else by_fact.get(_census_fact(before))
        if pid is None:
            live = _live_ratchets(before)
            if live:
                fail("J", f"plane {old_pid} at {base[:9]} is gone with live ceilings {live} — a census plane leaves only once its ratchet ceilings reach 0; a rename keeps its id or derives the same fact (carrier/scope/visibility) so the ratchet carries over")
            continue
        plane = census_planes[pid]
        if pid != old_pid:
            pid = f"{pid} (was {old_pid})"
        old_ceilings = before.get("ceilings") if isinstance(before.get("ceilings"), dict) else {}
        new_ceilings = plane.get("ceilings") if isinstance(plane.get("ceilings"), dict) else {}
        for key in S.RATCHET_CEILING_KEYS:
            new_v, old_v = new_ceilings.get(key), old_ceilings.get(key)
            if not _is_cap(old_v):
                continue
            if not _is_cap(new_v):
                fail("J", f"plane {pid}: ceilings.{key} was {old_v} at {base[:9]} and is gone now — dropping a ratchet ceiling is a rise to unlimited; lower it, never delete it")
            elif new_v > old_v:
                fail("J", f"plane {pid}: ceilings.{key} rose {old_v} → {new_v} against {base[:9]} — this ceiling only falls; a new on-the-hour or shared-minute cron is a stagger regression to fix in its repository")
        old_rules = {_match_key(r): r for r in before.get("declared_off") or [] if isinstance(r, dict) and isinstance(r.get("match"), dict)}
        new_rules = {_match_key(r): r for r in plane.get("declared_off") or [] if isinstance(r, dict) and isinstance(r.get("match"), dict)}
        for key, prior in old_rules.items():
            old_caps = _rule_ceilings(prior)
            row = new_rules.get(key)
            if row is None:
                live = {k: v for k, v in old_caps.items() if v > 0}
                if live:
                    fail("J", f"plane {pid}: declared_off rule {key} with ceilings {live} at {base[:9]} is gone — a rule leaves only once its ceilings reach 0 (reap or re-enable), never by deletion")
                continue
            new_caps = _rule_ceilings(row)
            for state_key, old_v in old_caps.items():
                new_v = new_caps.get(state_key)
                if new_v is None:
                    if old_v > 0:
                        fail("J", f"plane {pid}: declared_off ceiling {state_key} was {old_v} at {base[:9]} and is gone now — lower it to 0 before dropping it")
                elif new_v > old_v:
                    fail("J", f"plane {pid}: declared_off ceiling {state_key} rose {old_v} → {new_v} against {base[:9]} — an off-switch count only falls (reap or re-enable), it is never re-declared upward")

def _census_fact(plane: dict) -> tuple[str, str, str | None]:
    """The fact a census plane derives: (carrier, scope, visibility) — its identity across renames."""
    src = plane.get("jobs_source") if isinstance(plane.get("jobs_source"), dict) else {}
    return (str(src.get("carrier", "gh-workflow")), str(src.get("scope", "residual")), src.get("visibility"))


def _live_ratchets(plane: dict) -> dict[str, int]:
    """Every ratchet ceiling above 0 a plane carries: on-the-hour / shared-minute and each declared_off state ceiling."""
    ceilings = plane.get("ceilings") if isinstance(plane.get("ceilings"), dict) else {}
    live = {k: v for k, v in ceilings.items() if k in S.RATCHET_CEILING_KEYS and _is_cap(v) and v > 0}
    for r in plane.get("declared_off") or []:
        if isinstance(r, dict) and isinstance(r.get("match"), dict):
            live.update({f"declared_off[{_match_key(r)}].{k}": v for k, v in _rule_ceilings(r).items() if v > 0})
    return live


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
                {"utc": utc, "sort": sort, "job": f"{workflows} fleet workflow{'s' if workflows != 1 else ''} (counts only)", "plane": plane, "cron": "—", "tz": "UTC", "enabled": True, "fires": fires, "flags": "", "census": True}
            )
        rows = kept
    rows.sort(key=lambda r: (r["sort"], r["plane"], r["job"]))
    return rows


def print_slot_map(registry: dict, jobs: list[S.Job], day: date, compact: bool = False) -> None:
    """The 24h UTC map. --compact folds a job that fires more than once a day into one row
    ('hourly at :17 (24/day)') so the table reads as a day, not as a log."""
    rows = slot_map(registry, jobs, day)
    if compact:
        # census planes are already one count per slot; folding them by (job, cron) would merge slots and planes
        census_rows = [r for r in rows if r.get("census")]
        folded: dict[tuple[str, str], list[dict]] = {}
        for r in rows:
            if not r.get("census"):
                folded.setdefault((r["job"], r["cron"]), []).append(r)
        rows = list(census_rows)
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
    check_declared_off_rot(root, registry)
    check_census(root, registry, jobs, datetime.now(timezone.utc))
    check_claude_parity(root, registry, derived)
    check_sibling_parity(registry, declared, dict(os.environ), Path.home())
    check_stagger(registry, jobs, S.load_baseline(root))
    check_launch_authority(registry)
    check_consumers(root)
    check_readers(root)
    check_redaction(root, registry)
    check_ratchet_direction(root, registry)
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
        f"schema valid, derivations resolve, census ceilings, claude parity, sibling parity, stagger ratchet, consumers wired, readers allowlisted, redaction, ratchet direction"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
