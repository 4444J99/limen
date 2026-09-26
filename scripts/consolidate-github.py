#!/usr/bin/env python3
"""Consolidate repository hosting into 4444J99 without changing logical organs.

Read-only by default. Apply requires the existing owner's authorization, a
repository-ID-bound preservation preflight, and a private receipt destination.
An accepted transfer is NOT a verified transfer or integration acceptance.
See docs/consolidation/RUNBOOK.md. No deletion, visibility changes,
organization archival, billing changes, or protection bypasses are performed.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

TARGET = "4444J99"
OWNERS = (
    "a-organvm", "meta-organvm", "organvm", "organvm-i-theoria",
    "organvm-ii-poiesis", "organvm-iii-ergon", "organvm-iv-taxis",
    "organvm-v-logos", "organvm-vi-koinonia", "organvm-vii-kerygma",
)
PREFLIGHT_SCHEMA = "limen.github_consolidation_preflight.v1"
RECEIPT_SCHEMA = "limen.github_consolidation_receipt.v1"
MAX_PAGES = 1000


class ConsolidationError(RuntimeError):
    """An incomplete observation or failed effect; never an empty inventory."""


def gh_json(args, t=60):
    """Call the existing authenticated CLI; never print provider error bodies."""
    try:
        result = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=t, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ConsolidationError("GitHub CLI unavailable or timed out") from exc
    if result.returncode:
        raise ConsolidationError(f"GitHub CLI failed (exit {result.returncode})")
    try:
        return json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ConsolidationError("GitHub returned invalid JSON") from exc


def pages(endpoint):
    """Exhaust an array endpoint, failing on malformed or incomplete pagination."""
    rows = []
    separator = "&" if "?" in endpoint else "?"
    for page in range(1, MAX_PAGES + 1):
        batch = gh_json(["api", f"{endpoint}{separator}per_page=100&page={page}"])
        if not isinstance(batch, list) or len(batch) > 100:
            raise ConsolidationError("GitHub returned an invalid inventory page")
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise ConsolidationError("Inventory pagination bound reached; census is incomplete")


def snapshot(row):
    """Retain only the identity and state needed for migration, not private prose."""
    if not isinstance(row, dict):
        raise ConsolidationError("Repository metadata is not an object")
    owner = row.get("owner")
    login = owner.get("login") if isinstance(owner, dict) else None
    repo_id, name = row.get("id"), row.get("name")
    private, archived = row.get("private"), row.get("archived")
    topics, branch = row.get("topics"), row.get("default_branch")
    if (type(repo_id) is not int or repo_id <= 0 or not isinstance(login, str)
            or not login or not isinstance(name, str) or not name or "/" in name
            or not isinstance(row.get("full_name"), str)
            or row["full_name"].casefold() != f"{login}/{name}".casefold()
            or type(private) is not bool or type(archived) is not bool
            or not isinstance(topics, list) or not all(isinstance(x, str) for x in topics)
            or not isinstance(branch, str) or not branch
            or type(row.get("has_pages")) is not bool):
        raise ConsolidationError("Required repository identity/state is missing or malformed")
    visibility = row.get("visibility")
    if visibility not in {"public", "private"} or private != (visibility == "private"):
        raise ConsolidationError("Unsupported or contradictory repository visibility")
    return {
        "id": repo_id, "owner": login, "name": name, "full_name": row["full_name"],
        "visibility": visibility, "archived": archived, "topics": topics,
        "default_branch": branch, "has_pages": row["has_pages"],
    }


def inventory():
    """Read all ten sources and the authenticated destination, including private repos."""
    user = gh_json(["api", "/user"])
    if not isinstance(user, dict) or str(user.get("login", "")).casefold() != TARGET.casefold():
        raise ConsolidationError("Authenticate the GitHub CLI as the destination owner")
    target = [snapshot(r) for r in pages(
        "/user/repos?affiliation=owner&visibility=all&sort=full_name&direction=asc"
    )]
    if any(r["owner"].casefold() != TARGET.casefold() for r in target):
        raise ConsolidationError("Destination inventory contains another owner")
    source = []
    for owner in OWNERS:
        batch = [snapshot(r) for r in pages(
            f"/orgs/{owner}/repos?type=all&sort=full_name&direction=asc"
        )]
        if any(r["owner"].casefold() != owner.casefold() for r in batch):
            raise ConsolidationError("Source ownership changed during inventory; reread")
        source.extend(batch)
    ids = [r["id"] for r in source + target]
    if len(set(ids)) != len(ids):
        raise ConsolidationError("Duplicate repository identity; inventory may have drifted")
    return source, target


def sphere_topic(owner):
    """Historical hosting provenance only; never infer or replace the logical organ."""
    return owner.replace("organvm-", "sphere-").lower()


def desired_topics(before, current):
    topics = sorted(set(before["topics"]) | set(current["topics"]) | {"organvm", sphere_topic(before["owner"])})
    if len(topics) > 20:
        raise ConsolidationError("Topic capacity exceeded; existing topics must not be dropped")
    return topics


def build_plan(source, target):
    """Destination and source collisions are both case-insensitive."""
    counts = Counter(r["name"].casefold() for r in source + target)
    plan = []
    for row in sorted(source, key=lambda r: r["full_name"].casefold()):
        holds = []
        if counts[row["name"].casefold()] > 1:
            holds.append("name-collision")
        if row["name"].casefold() == ".github":
            holds.append("organization-profile-and-shared-workflow-retention")
        if row["has_pages"] or row["name"].casefold().endswith(".github.io"):
            holds.append("pages-migration-required")
        if not row["archived"]:
            try:
                desired_topics(row, row)
            except ConsolidationError:
                holds.append("topic-capacity")
        plan.append({**row, "destination": f"{TARGET}/{row['name']}", "holds": holds})
    return plan


def load_preflight(path):
    """A technical preservation record, not a substitute for user authorization."""
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ConsolidationError("Preservation preflight is unreadable") from exc
    if (not isinstance(value, dict) or value.get("schema") != PREFLIGHT_SCHEMA
            or value.get("target") != TARGET or not isinstance(value.get("repositories"), list)):
        raise ConsolidationError("Preservation preflight schema or destination is invalid")
    index = {}
    for row in value["repositories"]:
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] in index:
            raise ConsolidationError("Malformed or duplicate preflight identity")
        index[row["id"]] = row
    return index


def preflight_matches(row, record):
    fields = ("id", "full_name", "destination", "visibility", "archived", "default_branch")
    return (isinstance(record, dict) and record.get("preservation_checked") is True
            and isinstance(record.get("evidence_ref"), str) and bool(record["evidence_ref"].strip())
            and all(type(record.get(k)) is type(row[k]) and record[k] == row[k] for k in fields))


def write_receipt(path, data):
    """Write atomically and privately; failure before an effect stops the effect."""
    path = Path(path)
    if path.is_symlink():
        raise ConsolidationError("Receipt path must not be a symbolic link")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".consolidation-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            os.fchmod(fh.fileno(), 0o600)
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def claim_receipt_path(args):
    """Fail closed before any checkpoint: never overwrite prior evidence by accident.

    Returns the prior receipt when --resume is given, or None for a fresh path.
    """
    if args.receipt is None:
        return None
    path = Path(args.receipt)
    if path.is_symlink():
        raise ConsolidationError("Receipt path must not be a symbolic link")
    if not path.exists():
        return None
    if not args.resume:
        raise ConsolidationError(
            "Receipt path already exists. Use a fresh --receipt path, or pass --resume "
            "to continue the previous run while preserving its audit evidence.")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise ConsolidationError("Existing receipt is unreadable; refusing to resume or overwrite") from exc
    if (not isinstance(value, dict) or value.get("schema") != RECEIPT_SCHEMA
            or value.get("target") != TARGET or not isinstance(value.get("results"), list)):
        raise ConsolidationError("Existing receipt is foreign or malformed; refusing to resume or overwrite")
    return value


def read_repository(repo_id):
    return snapshot(gh_json(["api", f"/repositories/{repo_id}"]))

def verify_state(before, after, owner):
    for field in ("id", "name", "visibility", "archived", "default_branch", "has_pages"):
        if before[field] != after[field]:
            raise ConsolidationError(f"Repository {field} changed; stop and reconcile")
    if after["owner"].casefold() != owner.casefold():
        raise ConsolidationError("Repository owner does not match the expected owner")


def transfer(row, result, checkpoint, attempts=10, delay=1):
    """Revalidate each identity, transfer natively, and distinguish accepted from verified."""
    before = read_repository(row["id"])
    verify_state(row, before, row["owner"])
    if before["has_pages"] != row["has_pages"]:
        raise ConsolidationError("Pages state changed after planning")
    if not before["archived"]:
        desired_topics(before, before)  # Capacity check before any outward effect.
    result.update(status="submission_pending", before=before)
    checkpoint()
    endpoint = f"/repos/{quote(before['owner'], safe='')}/{quote(before['name'], safe='')}/transfer"
    gh_json(["api", "-X", "POST", endpoint, "-f", f"new_owner={TARGET}"])
    result["status"] = "accepted_unverified"
    checkpoint()
    after = None
    for attempt in range(attempts):
        candidate = read_repository(row["id"])
        if candidate["owner"].casefold() == TARGET.casefold():
            after = candidate
            break
        if candidate["owner"].casefold() != before["owner"].casefold():
            raise ConsolidationError("Repository transferred to an unexpected owner")
        if attempt + 1 < attempts:
            time.sleep(delay)
    if after is None:
        return  # An invitation or async operation may still be pending. Never count it as moved.
    verify_state(before, after, TARGET)
    result.update(status="ownership_verified", after=after, integration_verification="pending")
    checkpoint()
    if before["archived"]:
        if not set(before["topics"]).issubset(set(after["topics"])):
            raise ConsolidationError("Archived repository lost topics; no automatic unarchive")
    else:
        topics = desired_topics(before, after)
        payload = ["api", "-X", "PUT", f"/repos/{TARGET}/{quote(before['name'], safe='')}/topics"]
        for topic in topics:
            payload.extend(["-f", f"names[]={topic}"])
        gh_json(payload)
        final = read_repository(row["id"])
        verify_state(before, final, TARGET)
        if not set(topics).issubset(set(final["topics"])):
            raise ConsolidationError("Topic preservation did not verify")
        result["after"] = final
    result["status"] = "transfer_verified"
    checkpoint()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--allow-partial", action="store_true", help="Apply eligible rows while retaining explicit holds")
    parser.add_argument("--preflight", type=Path)
    parser.add_argument("--receipt", type=Path, help="Private, non-published JSON receipt; mandatory for apply")
    parser.add_argument("--resume", action="store_true",
                        help="Continue a previous run from an existing receipt, preserving its audit evidence")
    args = parser.parse_args(argv)
    if args.apply and (args.preflight is None or args.receipt is None):
        parser.error("--apply requires --preflight and --receipt; authorization alone is not a preservation audit")
    if args.preflight and args.receipt and args.preflight.resolve() == args.receipt.resolve():
        parser.error("preflight and receipt must be different files")
    try:
        prior = claim_receipt_path(args)
    except ConsolidationError as exc:
        print(f"Consolidation refused: {exc}", file=sys.stderr)
        return 1
    receipt = {"schema": RECEIPT_SCHEMA, "target": TARGET, "mode": "apply" if args.apply else "dry-run",
               "observed_at": datetime.now(timezone.utc).isoformat(), "inventory_pages_complete": False, "visibility_coverage": "credential_visible_only",
               "plan": [], "results": [], "organization_retirement": "not_attempted"}
    if prior is not None:
        # Resume: keep the earlier waves' audit evidence; the new run appends to it.
        receipt.update(resumed_from=prior.get("observed_at"),
                       prior_inventory_pages_complete=prior.get("inventory_pages_complete", False),
                       results=prior.get("results", []))

    def checkpoint():
        if args.receipt:
            write_receipt(args.receipt, receipt)

    try:
        preflight = load_preflight(args.preflight) if args.apply else {}
        source, target = inventory()
        plan = build_plan(source, target)
        receipt.update(inventory_pages_complete=True, plan=plan)
        for row in plan:
            if args.apply and not preflight_matches(row, preflight.get(row["id"])):
                row["holds"].append("preservation-preflight-required")
        held = sum(bool(r["holds"]) for r in plan)
        owners = {r["owner"] for r in source}
        name_counts = Counter(r["name"].casefold() for r in plan)
        collision_groups = sum(1 for count in name_counts.values() if count > 1)
        checkpoint()
        # Machine-readable counts for scripts/consolidation-gates.py::build_snapshot,
        # which opens the irreversible apply gate on exactly these fields.
        print(f"  {len(plan)} repos across {len(owners)} owners")
        print(f"  name collisions (must rename before transfer): {collision_groups}")
        print(f"Destination {TARGET}: {len(plan)} source repositories; {held} held. Details stay in the private receipt.")
        if not args.apply:
            print("DRY-RUN: no transfers, topic changes, or organization changes performed.")
            return 0
        if held and not args.allow_partial:
            print("No effects: held repositories remain. Use --allow-partial for the reviewed eligible subset.")
            return 2
        for row in plan:
            result = {"id": row["id"], "status": "held" if row["holds"] else "pending"}
            receipt["results"].append(result)
            checkpoint()
            if row["holds"]:
                continue
            try:
                transfer(row, result, checkpoint)
            except (ConsolidationError, OSError) as exc:
                result.update(last_status=result["status"], status="failed", failure_class=type(exc).__name__)
                checkpoint()
                # Stop after an uncertain/failed effect; do not amplify a migration defect.
                print("Migration stopped after a failed or uncertain effect; inspect the private receipt.")
                return 1
            if result["status"] != "transfer_verified":
                print("Transfer accepted but not verified. Stop here; do not resubmit until reconciled.")
                return 3
        count = sum(r["status"] == "transfer_verified" for r in receipt["results"])
        print(f"Verified repository transfers: {count}; held: {held}. Integration acceptance and organization retirement remain separate.")
        return 2 if held else 0
    except (ConsolidationError, OSError) as exc:
        receipt["failure_class"] = type(exc).__name__
        try:
            checkpoint()
        except (OSError, ConsolidationError):
            pass
        print("Consolidation failed; no completion claim. Check CLI access and the private receipt.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
