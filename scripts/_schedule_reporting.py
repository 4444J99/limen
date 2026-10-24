"""Metadata-only, bounded reporting helpers; no execution authority or provider reads."""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from _schedule_evidence import EvidenceStore


def utc(value):
    try:
        stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo else None
    except (ValueError, TypeError):
        return None


def capacity_report(plane, now):
    """Published ceilings and policy are never account entitlement or usable capacity."""
    allot = plane.get("allotment") or {}
    capacity = plane.get("capacity") or {}
    allowance = capacity.get("verified_allowance") or {}
    usage = capacity.get("usage") or {}
    downstream = capacity.get("downstream") or {}
    publication = allot.get("publication") or {}
    published = False
    if isinstance(publication, dict):
        try:
            source = urlsplit(str(publication.get("source", "")))
            published = (
                allot.get("classification") == "published-ceiling"
                and source.scheme == "https"
                and bool(source.netloc)
                and utc(publication.get("observed_at")) is not None
            )
        except ValueError:
            pass

    def fresh(record):
        stamp = utc(record.get("observed_at"))
        return stamp is not None and 0 <= (now - stamp).total_seconds() <= 3600

    def number(record, key="value"):
        value = record.get(key)
        return value if type(value) is int and value >= 0 else None

    verified = (
        number(allowance) is not None
        and allowance.get("evidence_ref")
        and all(allowance.get(k) for k in ("account_ref", "window", "unit"))
    )
    measured = (
        number(usage) is not None
        and usage.get("evidence_ref")
        and usage.get("coverage") == "complete"
        and fresh(usage)
        and all(usage.get(k) == allowance.get(k) for k in ("account_ref", "window", "unit"))
    )
    downstream_known = (
        all(number(downstream, k) is not None for k in ("review", "delivery"))
        and downstream.get("evidence_ref")
        and fresh(downstream)
    )
    remainder = (
        min(max(0, allowance["value"] - usage["value"]), downstream["review"], downstream["delivery"])
        if verified and measured and downstream_known
        else None
    )
    return {
        "verified_allowance": number(allowance) if verified else None,
        "published_ceiling": number(allot, "runs") if published else None,
        "local_policy": {
            "floor": plane.get("floor"),
            "limit": allot.get("runs") if allot.get("classification") == "local-policy" else None,
        },
        "measured_usage": number(usage),
        "usage_coverage": usage.get("coverage", "unknown"),
        "usage_fresh": fresh(usage),
        "usage_matches_allowance": bool(verified and measured),
        "usable_remainder": remainder,
        "admission_authority": False,
    }


def read_native_snapshot(plane_id, plane, jobs, today, root, *, now=None):
    """Validate through the canonical store in a private temporary directory, then aggregate.

    Poll timestamps establish collection history only. Execution requires native completion
    time in the requested UTC day. Account/window coverage cannot be inferred from this cache.
    """
    now = now or datetime.now(timezone.utc)
    try:
        max_age_days = int(os.environ.get("LIMEN_SCHEDULE_SNAPSHOT_MAX_AGE_DAYS", "") or 7)
    except ValueError:
        max_age_days = 7
    if max_age_days <= 0:
        max_age_days = 7
    evidence = plane.get("evidence") or {}
    path = Path(evidence.get("locator") or "")
    path = path if path.is_absolute() else root / path
    try:
        with path.open("rb") as stream:
            raw = stream.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise ValueError("snapshot bound")
        snapshot = json.loads(raw)
        if any(len(snapshot.get(k, [])) > 10000 for k in ("observations", "assessments", "checkpoints")):
            raise ValueError("snapshot row bound")
        with tempfile.TemporaryDirectory(prefix="limen-native-report-") as private:
            with EvidenceStore(Path(private) / "evidence.db") as store:
                store.import_snapshot(snapshot)
                snapshot = store.export()
    except (OSError, ValueError, TypeError, KeyError):
        return (
            None,
            "native snapshot unavailable or invalid",
            {"coverage": "unknown", "measurement_kind": "native-evidence"},
        )
    rows = [
        r
        for r in snapshot["observations"]
        if (not evidence.get("provider") or r["provider"] == evidence["provider"])
        and (not evidence.get("surface") or r["surface"] == evidence["surface"])
    ]
    current = {}
    for row in rows:
        key = (row["provider"], row["surface"], row["account_ref"], row["native_task_id"] or row["source_ref"])
        # Last actual readback determines current state, including a repeated A after A-B-A.
        # Imports preserve supplied source times; import time is never a fresh native read.
        order = (
            utc(row["last_observed_at"]),
            utc(row["times"]["started_at"]) or datetime.min.replace(tzinfo=timezone.utc),
            row["observation_id"],
        )
        if key not in current or order > current[key][0]:
            current[key] = (order, row)
    latest = [value[1] for value in current.values()]
    # Task readbacks describe current state; taskless immutable events describe source history.
    # New mail can refresh that account's event source without refreshing old tasks/other accounts.
    readbacks = {}
    for row in latest:
        key = (row["provider"], row["surface"], row["account_ref"],
               "task" if row["native_task_id"] else "events", row["native_task_id"])
        stamp = utc(row["last_observed_at"])
        if key not in readbacks or stamp is None or (readbacks[key] is not None and stamp > readbacks[key]):
            readbacks[key] = stamp
    ages = [(now - stamp).total_seconds() if stamp else None for stamp in readbacks.values()]
    max_age_seconds = max_age_days * 86400
    readback_fresh = bool(ages) and all(age is not None and 0 <= age <= max_age_seconds for age in ages)
    readback_overdue = any(age is not None and age > max_age_seconds for age in ages)
    executions = [
        r
        for r in latest
        if r["native_run_id"]
        and r["execution_status"] in ("completed", "succeeded", "success")
        and utc(r["times"]["completed_at"]) is not None
        and utc(r["times"]["completed_at"]).date() == today
    ]
    assessments = {(a["observation_id"], a["artifact_sha256"], a["status"]) for a in snapshot["assessments"]}
    counts = {
        "observations": len(rows),
        "current_tasks": sum(bool(r["native_task_id"]) for r in latest),
        "current_runs": len(
            {
                (
                    r["account_ref"],
                    r["native_task_id"],
                    r["native_run_id"],
                    r["times"]["scheduled_for"],
                    r["times"]["started_at"],
                )
                for r in latest
                if r["native_run_id"]
            }
        ),
        "executed_in_window": len(executions),
        "collected_complete": sum(r["collection_state"] == "complete" for r in latest),
        "collected_partial": sum(r["collection_state"] == "partial" for r in latest),
        "attributed": sum(r["attribution_state"] == "correlated" for r in latest),
        "unresolved": sum(r["attribution_state"] == "unresolved" for r in latest),
    }
    for status in ("accepted", "delivered"):
        counts[status] = sum((r["observation_id"], r["artifact"]["sha256"], status) in assessments for r in latest)
        identities = {r["observation_id"] for r in rows}
        counts[status + "_history"] = len(
            {
                (a["observation_id"], a["artifact_sha256"])
                for a in snapshot["assessments"]
                if a["status"] == status and a["observation_id"] in identities
            }
        )
    return (
        len(executions) if readback_fresh else None,
        f"bounded native evidence; account and history coverage incomplete; source readback {'within' if readback_fresh else 'not within'} {max_age_days}d cache-age bound; counts retain latest known history",
        {"measurement_kind": "native-evidence", "coverage": "partial", "native_counts": counts,
         "readback_fresh": readback_fresh, "readback_overdue": readback_overdue,
         "readback_max_age_days": max_age_days},
    )
