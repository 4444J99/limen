#!/usr/bin/env python3
"""Track C closeout for the stable Domus agent-host App Management campaign.

Ideal-form predicate (architecture item 5):

  non_noop_update ∧ normalized_inventory_green

where non_noop means Claude Code advanced past the cutover baseline version
(currently 2.1.220). A no-op ``claude update`` ("up to date") is wait evidence,
never completion. Fixture-only green is never completion.

Modes:
  --probe     version + inventory snapshot only (no update attempt)
  --run       baseline audit → hosted update → post audit → classify
  --beat      heartbeat entry: wait quietly while baseline holds; run when a
              version advance is already present or after a non-noop update
  --finalize  discharge local lever surfaces only when a met receipt exists

Exit codes:
  0  external_vendor_wait (clean) OR track_c.met
  1  inventory regression / host failure / finalize without met proof
  2  usage error
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "limen.tcc_track_c_closeout.v1"
STATUS_SCHEMA = "limen.tcc_track_c_status.v1"
CUTOVER_BASELINE_VERSION = "2.1.220"
ISSUE_NUMBER = 1703
LEVER_ID = "L-DOMUS-AGENT-HOST-TCC"
HOST_BIN_CANDIDATES = ("domus-agent-host",)
UPDATE_ARGV = ("claude", "update")
VERSION_ARGV = ("claude", "--version")
VERSION_RE = re.compile(r"(\d+\.\d+\.\d+)")

Runner = Callable[..., subprocess.CompletedProcess[str]]


class CloseoutError(RuntimeError):
    """Track C closeout could not establish its predicate."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_root() -> Path:
    override = os.environ.get("LIMEN_ROOT")
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _default_runner(
    *argv: str, env: Mapping[str, str] | None = None, timeout: float = 120.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        capture_output=True,
        check=False,
        env=dict(env or os.environ),
        text=True,
        timeout=timeout,
    )


def parse_claude_version(text: str) -> str | None:
    match = VERSION_RE.search(text or "")
    return match.group(1) if match else None


def version_tuple(version: str) -> tuple[int, ...]:
    parts = version.strip().split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise CloseoutError(f"unparseable version: {version!r}")
    return tuple(int(part) for part in parts)


def version_advanced(current: str, baseline: str = CUTOVER_BASELINE_VERSION) -> bool:
    return version_tuple(current) > version_tuple(baseline)


def _resolve_host_bin(env: Mapping[str, str]) -> str:
    override = env.get("LIMEN_AGENT_HOST_BIN") or env.get("DOMUS_AGENT_HOST_BIN")
    if override:
        return str(Path(override).expanduser())
    for name in HOST_BIN_CANDIDATES:
        found = shutil.which(name, path=env.get("PATH"))
        if found:
            return found
    raise CloseoutError("domus-agent-host not found on PATH")


def hosted_run(
    argv: Sequence[str],
    *,
    env: Mapping[str, str],
    runner: Runner,
    host_bin: str | None = None,
    timeout: float = 180.0,
) -> subprocess.CompletedProcess[str]:
    host = host_bin or _resolve_host_bin(env)
    return runner(host, "run", "--", *argv, env=env, timeout=timeout)


def probe_version(
    *,
    env: Mapping[str, str],
    runner: Runner,
    host_bin: str | None = None,
) -> dict[str, Any]:
    completed = hosted_run(VERSION_ARGV, env=env, runner=runner, host_bin=host_bin, timeout=60.0)
    text = (completed.stdout or "") + (completed.stderr or "")
    version = parse_claude_version(text)
    return {
        "command": ["domus-agent-host", "run", "--", *VERSION_ARGV],
        "exit_code": completed.returncode,
        "output": text.strip(),
        "version": version,
        "ok": completed.returncode == 0 and version is not None,
    }


def attempt_update(
    *,
    env: Mapping[str, str],
    runner: Runner,
    host_bin: str | None = None,
) -> dict[str, Any]:
    completed = hosted_run(UPDATE_ARGV, env=env, runner=runner, host_bin=host_bin, timeout=300.0)
    text = (completed.stdout or "") + (completed.stderr or "")
    lowered = text.lower()
    noop = "up to date" in lowered or "already up to date" in lowered
    return {
        "command": ["domus-agent-host", "run", "--", *UPDATE_ARGV],
        "exit_code": completed.returncode,
        "output": text.strip(),
        "noop_text_signal": noop,
        "ok": completed.returncode == 0,
    }


def run_strict_audit(
    *,
    env: Mapping[str, str],
    runner: Runner,
    repo: Path,
) -> dict[str, Any]:
    script = repo / "scripts" / "tcc-identity-audit.py"
    completed = runner(sys.executable, str(script), "--json", "--strict", env=env, timeout=180.0)
    text = (completed.stdout or "").strip()
    if not text:
        raise CloseoutError(
            "tcc-identity-audit produced no JSON: "
            + ((completed.stderr or "").strip() or f"exit {completed.returncode}")
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CloseoutError(f"tcc-identity-audit JSON decode failed: {exc}") from exc
    return {
        "exit_code": completed.returncode,
        "payload": payload,
        "ok": bool(payload.get("ok")) and completed.returncode == 0,
    }


def normalized_inventory_view(audit_payload: Mapping[str, Any]) -> dict[str, Any]:
    predicates = audit_payload.get("predicates") or {}
    active = predicates.get("active_leaks") or {}
    visible = predicates.get("visible_app_management_path_rows") or {}
    unhosted = predicates.get("unhosted_configured_ingresses") or {}
    summary = audit_payload.get("summary") or {}
    auto = audit_payload.get("automatic_updates") or {}
    preservation = audit_payload.get("unrelated_app_management_preservation") or {}
    host = audit_payload.get("stable_host") or {}
    return {
        "schema": audit_payload.get("schema"),
        "ok": bool(audit_payload.get("ok")),
        "status": audit_payload.get("status"),
        "failures": list(audit_payload.get("failures") or []),
        "active_leaks": int(active.get("count") or summary.get("active_leaks") or 0),
        "visible_app_management_path_rows": int(
            visible.get("count") or summary.get("visible_app_management_path_rows") or 0
        ),
        "stable_host_app_management_grants": int(visible.get("stable_host_grant_count") or 0),
        "unhosted_configured_ingresses": int(
            unhosted.get("count") or summary.get("unhosted_configured_ingresses") or 0
        ),
        "new_managed_identities": int(summary.get("new_managed") or 0),
        "automatic_updates_enabled": bool(auto.get("enabled")),
        "unrelated_grants_preserved": bool(preservation.get("ok")),
        "stable_host_ok": bool(host.get("ok")),
        "stable_host_cdhash": host.get("cdhash"),
        "summary": dict(summary),
    }


def inventory_green(view: Mapping[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not view.get("ok"):
        reasons.append("strict_audit_not_ok")
    if int(view.get("active_leaks") or 0) != 0:
        reasons.append("active_leaks_nonzero")
    if int(view.get("visible_app_management_path_rows") or 0) != 0:
        reasons.append("visible_app_management_path_rows_nonzero")
    if int(view.get("stable_host_app_management_grants") or 0) != 1:
        reasons.append("stable_host_app_management_grant_missing")
    if int(view.get("unhosted_configured_ingresses") or 0) != 0:
        reasons.append("unhosted_configured_ingresses_nonzero")
    if int(view.get("new_managed_identities") or 0) != 0:
        reasons.append("new_managed_identities_nonzero")
    if not view.get("automatic_updates_enabled"):
        reasons.append("automatic_updates_disabled")
    if not view.get("unrelated_grants_preserved"):
        reasons.append("unrelated_grants_not_preserved")
    if not view.get("stable_host_ok"):
        reasons.append("stable_host_invalid")
    return (not reasons, reasons)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def receipt_dir(repo: Path) -> Path:
    return repo / "docs" / "receipts" / "tcc-track-c-1703"


def status_path(repo: Path) -> Path:
    return repo / "logs" / "tcc-track-c-status.json"


def latest_met_receipt(repo: Path) -> Path | None:
    root = receipt_dir(repo)
    if not root.is_dir():
        return None
    # Only immutable timestamped receipts qualify as discharge evidence: the
    # closeout-latest.json alias is rewritten every beat, so pinning it lets a
    # later regression silently invalidate an already-recorded discharge.
    candidates = sorted(
        (path for path in root.glob("closeout-*.json") if path.name != "closeout-latest.json"),
        reverse=True,
    )
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("schema") == SCHEMA and payload.get("track_c", {}).get("met") is True:
            return path
    return None


def classify(
    *,
    version_before: str | None,
    version_after: str | None,
    update: Mapping[str, Any] | None,
    inventory: Mapping[str, Any] | None,
    inventory_reasons: Sequence[str],
    inventory_ok: bool,
    update_attempted: bool,
) -> dict[str, Any]:
    baseline = CUTOVER_BASELINE_VERSION
    after = version_after or version_before
    non_noop = bool(after and version_advanced(after, baseline))
    failure_classes: list[str] = []
    if not after:
        failure_classes.append("version_unreadable")
    if update_attempted and update is not None and not update.get("ok"):
        failure_classes.append("update_command_failed")
    if after and not non_noop:
        failure_classes.append("noop_update_proof_missing")
    if inventory is not None and not inventory_ok:
        failure_classes.extend(list(inventory_reasons))

    hard_blockers = [cls for cls in failure_classes if cls not in {"noop_update_proof_missing"}]
    met = bool(non_noop and inventory_ok and not hard_blockers and after)
    if met:
        status = "met"
        failure_classes = []
    elif not non_noop and not hard_blockers:
        status = "external_vendor_wait"
    else:
        status = "blocked"

    reason = {
        "met": (f"Track C met: Claude Code advanced beyond {baseline} to {after} and normalized inventory is green."),
        "external_vendor_wait": (
            f"Blocked cleanly: Claude Code remains at {after or 'unknown'} "
            f"(cutover baseline {baseline}); non-noop vendor update proof is missing. "
            "No-op 'up to date' is wait evidence, never completion."
        ),
        "blocked": ("Track C blocked: " + (", ".join(failure_classes) if failure_classes else "unclassified failure")),
    }[status]

    return {
        "status": status,
        "met": met,
        "non_noop": non_noop,
        "cutover_baseline_version": baseline,
        "version_before": version_before,
        "version_after": after,
        "update_attempted": update_attempted,
        "failure_classes": failure_classes,
        "met_reason": reason,
        "requirement": (
            "An external-host update through domus-agent-host must complete with a "
            "non-noop Claude Code version advance beyond the cutover baseline, then "
            "normalized v2 tcc-identity-audit predicates must remain green."
        ),
    }


def build_receipt(
    *,
    mode: str,
    track_c: Mapping[str, Any],
    version_probe_before: Mapping[str, Any],
    version_probe_after: Mapping[str, Any] | None,
    update: Mapping[str, Any] | None,
    baseline_audit: Mapping[str, Any] | None,
    post_audit: Mapping[str, Any] | None,
    inventory: Mapping[str, Any] | None,
    paths: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "observed_at": _utc_now(),
        "mode": mode,
        "issue": ISSUE_NUMBER,
        "lever_id": LEVER_ID,
        "architecture": "docs/architecture/tcc-stable-agent-host.md#live-acceptance",
        "doctrine": {
            "non_noop_means": "claude --version advances past cutover baseline",
            "noop_is_not_completion": True,
            "fixture_only_is_not_completion": True,
            "formula": "track_c_pass = non_noop_update AND normalized_inventory_green",
        },
        "version_probe_before": version_probe_before,
        "version_probe_after": version_probe_after,
        "update": update,
        "baseline_audit": (
            {
                "ok": baseline_audit.get("ok"),
                "exit_code": baseline_audit.get("exit_code"),
                "normalized": normalized_inventory_view(baseline_audit["payload"]),
            }
            if baseline_audit
            else None
        ),
        "post_audit": (
            {
                "ok": post_audit.get("ok"),
                "exit_code": post_audit.get("exit_code"),
                "normalized": normalized_inventory_view(post_audit["payload"]),
            }
            if post_audit
            else None
        ),
        "normalized_inventory": inventory,
        "track_c": dict(track_c),
        "paths": dict(paths),
        "next_commands": _next_commands(track_c),
    }


def _next_commands(track_c: Mapping[str, Any]) -> list[str]:
    if track_c.get("met"):
        return [
            "python3 scripts/tcc-track-c-closeout.py --finalize --write-lever",
            f"gh issue close {ISSUE_NUMBER} --repo organvm/limen --comment 'Track C met: vendor version advanced; normalized TCC inventory green. Receipt: docs/receipts/tcc-track-c-1703/'",
            "python3 scripts/tcc-identity-audit.py --json --strict",
        ]
    return [
        "python3 scripts/tcc-track-c-closeout.py --beat",
        "python3 scripts/tcc-track-c-closeout.py --run",
        f"# wait until Claude Code > {CUTOVER_BASELINE_VERSION}; do not discharge {LEVER_ID} on no-op",
    ]


def write_status(repo: Path, receipt: Mapping[str, Any]) -> Path:
    track = receipt.get("track_c") or {}
    status = {
        "schema": STATUS_SCHEMA,
        "observed_at": receipt.get("observed_at"),
        "status": track.get("status"),
        "met": track.get("met"),
        "non_noop": track.get("non_noop"),
        "version": track.get("version_after"),
        "cutover_baseline_version": track.get("cutover_baseline_version"),
        "failure_classes": track.get("failure_classes"),
        "met_reason": track.get("met_reason"),
        "receipt_path": (receipt.get("paths") or {}).get("receipt"),
        "issue": ISSUE_NUMBER,
        "lever_id": LEVER_ID,
    }
    path = status_path(repo)
    _write_json(path, status)
    return path


def persist_receipt(repo: Path, receipt: dict[str, Any], *, stem: str | None = None) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    name = stem or f"closeout-{stamp}"
    path = receipt_dir(repo) / f"{name}.json"
    paths = dict(receipt.get("paths") or {})
    paths["receipt"] = str(path.relative_to(repo))
    paths["status"] = str(status_path(repo).relative_to(repo))
    receipt["paths"] = paths
    _write_json(path, receipt)
    write_status(repo, receipt)
    latest = receipt_dir(repo) / "closeout-latest.json"
    _write_json(latest, receipt)
    return path


def run_closeout(
    *,
    mode: str,
    env: Mapping[str, str] | None = None,
    runner: Runner | None = None,
    repo: Path | None = None,
    do_update: bool = True,
    write: bool = True,
    write_audit_snapshots: bool = False,
) -> dict[str, Any]:
    env_map = dict(env or os.environ)
    run = runner or _default_runner
    root = repo or _repo_root()

    before = probe_version(env=env_map, runner=run)
    if not before.get("ok"):
        track = classify(
            version_before=None,
            version_after=None,
            update=None,
            inventory=None,
            inventory_reasons=["version_unreadable"],
            inventory_ok=False,
            update_attempted=False,
        )
        receipt = build_receipt(
            mode=mode,
            track_c=track,
            version_probe_before=before,
            version_probe_after=None,
            update=None,
            baseline_audit=None,
            post_audit=None,
            inventory=None,
            paths={},
        )
        if write:
            persist_receipt(root, receipt)
        return receipt

    version_before = before["version"]
    assert isinstance(version_before, str)

    # Already advanced: inventory-only proof against cutover baseline.
    if version_advanced(version_before):
        post = run_strict_audit(env=env_map, runner=run, repo=root)
        inventory = normalized_inventory_view(post["payload"])
        ok, reasons = inventory_green(inventory)
        track = classify(
            version_before=version_before,
            version_after=version_before,
            update=None,
            inventory=inventory,
            inventory_reasons=reasons,
            inventory_ok=ok,
            update_attempted=False,
        )
        receipt = build_receipt(
            mode=mode,
            track_c=track,
            version_probe_before=before,
            version_probe_after=before,
            update=None,
            baseline_audit=None,
            post_audit=post,
            inventory=inventory,
            paths={},
        )
        if write:
            path = persist_receipt(root, receipt)
            if write_audit_snapshots and post.get("payload") is not None:
                snap = receipt_dir(root) / f"{path.stem}-audit.json"
                _write_json(snap, post["payload"])
                receipt["paths"]["post_audit_snapshot"] = str(snap.relative_to(root))
                _write_json(path, receipt)
                _write_json(receipt_dir(root) / "closeout-latest.json", receipt)
                write_status(root, receipt)
        return receipt

    # Still at/below baseline.
    if not do_update:
        inventory = None
        inventory_ok = True
        reasons: list[str] = []
        post = None
        baseline_audit = None
        update = None
        after_probe = before
        # Optional inventory health check without claiming update proof.
        try:
            post = run_strict_audit(env=env_map, runner=run, repo=root)
            inventory = normalized_inventory_view(post["payload"])
            inventory_ok, reasons = inventory_green(inventory)
        except CloseoutError:
            inventory_ok = True
            reasons = []
        track = classify(
            version_before=version_before,
            version_after=version_before,
            update=update,
            inventory=inventory,
            inventory_reasons=reasons,
            inventory_ok=inventory_ok if inventory is not None else True,
            update_attempted=False,
        )
        # Probe-only never meets solely from inventory.
        if track["met"] and not track["non_noop"]:
            track["met"] = False
            track["status"] = "external_vendor_wait"
        receipt = build_receipt(
            mode=mode,
            track_c=track,
            version_probe_before=before,
            version_probe_after=after_probe,
            update=update,
            baseline_audit=baseline_audit,
            post_audit=post,
            inventory=inventory,
            paths={},
        )
        if write:
            persist_receipt(root, receipt)
        return receipt

    baseline_audit = run_strict_audit(env=env_map, runner=run, repo=root)
    baseline_view = normalized_inventory_view(baseline_audit["payload"])
    baseline_ok, baseline_reasons = inventory_green(baseline_view)
    update = attempt_update(env=env_map, runner=run)
    after_probe = probe_version(env=env_map, runner=run)
    version_after = after_probe.get("version") if after_probe.get("ok") else None
    post = run_strict_audit(env=env_map, runner=run, repo=root)
    inventory = normalized_inventory_view(post["payload"])
    ok, reasons = inventory_green(inventory)
    if not baseline_ok:
        # Baseline already red — still classify, but surface baseline debt.
        reasons = list(dict.fromkeys([*baseline_reasons, *reasons, "baseline_inventory_red"]))
        ok = False
    track = classify(
        version_before=version_before,
        version_after=version_after if isinstance(version_after, str) else None,
        update=update,
        inventory=inventory,
        inventory_reasons=reasons,
        inventory_ok=ok,
        update_attempted=True,
    )
    receipt = build_receipt(
        mode=mode,
        track_c=track,
        version_probe_before=before,
        version_probe_after=after_probe,
        update=update,
        baseline_audit=baseline_audit,
        post_audit=post,
        inventory=inventory,
        paths={},
    )
    if write:
        path = persist_receipt(root, receipt)
        if write_audit_snapshots:
            base_snap = receipt_dir(root) / f"{path.stem}-baseline-audit.json"
            post_snap = receipt_dir(root) / f"{path.stem}-post-audit.json"
            _write_json(base_snap, baseline_audit["payload"])
            _write_json(post_snap, post["payload"])
            receipt["paths"]["baseline_audit_snapshot"] = str(base_snap.relative_to(root))
            receipt["paths"]["post_audit_snapshot"] = str(post_snap.relative_to(root))
            _write_json(path, receipt)
            _write_json(receipt_dir(root) / "closeout-latest.json", receipt)
            write_status(root, receipt)
    return receipt


def finalize(
    *,
    repo: Path | None = None,
    write_lever: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    root = repo or _repo_root()
    met_path = latest_met_receipt(root)
    if met_path is None:
        raise CloseoutError(
            "no met Track C receipt found under docs/receipts/tcc-track-c-1703/; "
            "refuse to finalize on wait/blocked evidence"
        )
    met_receipt = json.loads(met_path.read_text(encoding="utf-8"))
    if not met_receipt.get("track_c", {}).get("met"):
        raise CloseoutError(f"receipt is not met: {met_path}")

    result: dict[str, Any] = {
        "schema": "limen.tcc_track_c_finalize.v1",
        "observed_at": _utc_now(),
        "met_receipt": str(met_path.relative_to(root)),
        "issue": ISSUE_NUMBER,
        "lever_id": LEVER_ID,
        "write_lever": write_lever,
        "lever_updated": False,
        "continuation_updated": False,
        "organs_updated": False,
        "next_commands": met_receipt.get("next_commands") or _next_commands(met_receipt["track_c"]),
    }

    if write_lever:
        lever_path = root / "his-hand-levers.json"
        registry = json.loads(lever_path.read_text(encoding="utf-8"))
        rows = [row for row in registry.get("levers", []) if row.get("id") == LEVER_ID]
        if len(rows) != 1:
            raise CloseoutError(f"{LEVER_ID} missing or duplicated in his-hand-levers.json")
        row = rows[0]
        version = met_receipt.get("track_c", {}).get("version_after")
        row["status"] = "discharged"
        row["discharged"] = {
            "at": _utc_now(),
            "by": "scripts/tcc-track-c-closeout.py --finalize",
            "receipt": str(met_path.relative_to(root)),
            "version": version,
            "issue": ISSUE_NUMBER,
        }
        row["label"] = (
            f"DISCHARGED: real Claude Code vendor update advanced to {version} through "
            "the fixed Domus host; normalized TCC inventory remained green "
            f"(receipt {met_path.name})."
        )
        steps = list(row.get("steps") or [])
        pending = (
            f"Completed external predicate: Claude Code advanced to {version}; "
            "normalized inventory remained green "
            f"(docs/receipts/tcc-track-c-1703/{met_path.name})."
        )
        if steps and "Pending external predicate" in str(steps[-1]):
            steps[-1] = pending
        else:
            steps.append(pending)
        row["steps"] = steps
        _write_json(lever_path, registry)
        result["lever_updated"] = True

        # Keep the registry guard test honest only after real met discharge:
        # test_his_hand_registry asserts open until this path runs.

        cont = root / "docs" / "continuations" / "tcc-app-management-closure-20260803" / "acceptance.json"
        if cont.is_file():
            acceptance = json.loads(cont.read_text(encoding="utf-8"))
            acceptance["completion"] = {
                "complete": True,
                "status": "met",
                "remaining_predicate": None,
                "closed_by": str(met_path.relative_to(root)),
                "closed_at": _utc_now(),
            }
            tcc_block = acceptance.get("tcc_track_c") or {}
            tcc_block["status"] = "met"
            tcc_block["met"] = True
            tcc_block["closeout_receipt"] = str(met_path.relative_to(root))
            acceptance["tcc_track_c"] = tcc_block
            _write_json(cont, acceptance)
            result["continuation_updated"] = True

        organs_path = root / "institutio" / "registry" / "organs.yaml"
        text = organs_path.read_text(encoding="utf-8")
        old_integrity = (
            'residual: "The 2026-08-03 local cutover passed: fixed-host signature unchanged, '
            "App Management has one host row and zero path rows, and the unrelated grant map is preserved. "
            "Keep alerting if an updater is disabled, any managed identity appears outside the redacted baseline, "
            "or a path client returns. Final acceptance waits for a real Claude version advance beyond 2.1.220 "
            'with the inventory still green. Never re-pin/re-disable a rotating tool."'
        )
        new_integrity = (
            f'residual: "Track C met at Claude Code {version}: fixed-host signature + App Management '
            "cleanliness hold under real vendor rotation. Keep alerting if an updater is disabled, any "
            "managed identity appears outside the redacted baseline, or a path client returns. "
            'Never re-pin/re-disable a rotating tool. Closeout: scripts/tcc-track-c-closeout.py."'
        )
        old_hygiene = (
            'residual: "Local predicates passed 2026-08-03: ten managed GUI ingresses enter through '
            "domus-agent-host ensure; App Management has one enabled host row, zero path rows, and the "
            "baseline's unrelated bundle grants unchanged; renamed-runner and cold-start matrices added no "
            "identity. The real Claude vendor-update predicate remains open because 2.1.220 was already "
            "current. The three HEAL valves remain separately armed. No recurring cleanup, updater "
            'suppression, global TCC reset, direct database edit, or version pin is an accepted closure."'
        )
        new_hygiene = (
            f'residual: "Track C met at Claude Code {version} via scripts/tcc-track-c-closeout.py. '
            "Standing beat keeps auto-updates enabled beneath the fixed host and rejects new managed "
            "identities / path clients / unhosted ingresses. The three HEAL valves remain separately armed. "
            'No recurring cleanup, updater suppression, global TCC reset, direct database edit, or version pin."'
        )
        updated = text
        if old_integrity in updated:
            updated = updated.replace(old_integrity, new_integrity, 1)
        if old_hygiene in updated:
            updated = updated.replace(old_hygiene, new_hygiene, 1)
        if updated != text:
            organs_path.write_text(updated, encoding="utf-8")
            result["organs_updated"] = True

    _write_json(root / "logs" / "tcc-track-c-finalize.json", result)
    return result


def exit_code_for(receipt: Mapping[str, Any]) -> int:
    track = receipt.get("track_c") or {}
    status = track.get("status")
    if status in {"met", "external_vendor_wait"}:
        return 0
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--probe", action="store_true", help="version + inventory only; never update")
    mode.add_argument("--run", action="store_true", help="full baseline→update→post proof attempt")
    mode.add_argument("--beat", action="store_true", help="heartbeat entrypoint")
    mode.add_argument("--finalize", action="store_true", help="discharge local surfaces only if met")
    parser.add_argument(
        "--write-lever",
        action="store_true",
        help="with --finalize, discharge L-DOMUS-AGENT-HOST-TCC and clear residuals",
    )
    parser.add_argument("--json", action="store_true", help="print receipt/status JSON")
    parser.add_argument("--no-write", action="store_true", help="do not persist receipts")
    args = parser.parse_args(list(argv) if argv is not None else None)

    try:
        if args.finalize:
            result = finalize(write_lever=args.write_lever)
            if args.json:
                print(json.dumps(result, indent=2, sort_keys=True))
            else:
                print(f"Track C finalize: met receipt {result['met_receipt']}")
                if result.get("lever_updated"):
                    print(f"  lever {LEVER_ID} discharged")
                for cmd in result.get("next_commands") or []:
                    print(f"  next: {cmd}")
            return 0

        selected = "beat" if args.beat else "run" if args.run else "probe" if args.probe else "beat"
        # Beat/run: attempt update (may no-op) so a real vendor offer is captured
        # the moment it appears. Probe never updates.
        receipt = run_closeout(
            mode=selected,
            do_update=selected in {"run", "beat"},
            write=not args.no_write,
        )
        if args.json:
            print(json.dumps(receipt, indent=2, sort_keys=True))
        else:
            track = receipt["track_c"]
            print(f"Track C: {track['status']}")
            print(f"  version: {track.get('version_after')} (baseline {track.get('cutover_baseline_version')})")
            print(f"  non_noop: {track.get('non_noop')}")
            print(f"  met: {track.get('met')}")
            print(f"  reason: {track.get('met_reason')}")
            paths = receipt.get("paths") or {}
            if paths.get("receipt"):
                print(f"  receipt: {paths['receipt']}")
            if paths.get("status"):
                print(f"  status: {paths['status']}")
        return exit_code_for(receipt)
    except CloseoutError as exc:
        print(f"Track C closeout error: {exc}", file=sys.stderr)
        return 1
    except subprocess.TimeoutExpired as exc:
        print(f"Track C closeout timeout: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
