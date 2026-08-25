#!/usr/bin/env python3
"""Freeze and individually restore transfer-sensitive GitHub workflows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.repository_identity import LIMEN_REPOSITORY_IDENTITY  # noqa: E402
from limen.repository_transfer import canonical_sha256  # noqa: E402


POLICY_PATH = ROOT / "institutio" / "github" / "workflow-transfer-policy.json"


class WorkflowTransferError(RuntimeError):
    pass


def _gh_json(arguments: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        ["gh", "api", *arguments],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkflowTransferError("GitHub workflow API request failed")
    value = json.loads(result.stdout) if result.stdout.strip() else {}
    if not isinstance(value, dict):
        raise WorkflowTransferError("GitHub workflow API returned a non-object")
    return value


def _workflow_rows(repo: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        [
            "gh",
            "api",
            "--paginate",
            "--slurp",
            f"/repos/{repo}/actions/workflows?per_page=100",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkflowTransferError("GitHub workflow census failed")
    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowTransferError("GitHub workflow census returned invalid JSON") from exc
    if not isinstance(pages, list) or not pages:
        raise WorkflowTransferError("GitHub workflow census returned no pages")
    rows: list[dict[str, Any]] = []
    totals: set[int] = set()
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get("workflows"), list):
            raise WorkflowTransferError("GitHub workflow census page is malformed")
        if not isinstance(page.get("total_count"), int):
            raise WorkflowTransferError("GitHub workflow census omitted its denominator")
        totals.add(page["total_count"])
        if any(not isinstance(row, dict) for row in page["workflows"]):
            raise WorkflowTransferError("GitHub workflow census contains a non-object row")
        rows.extend(page["workflows"])
    if len(totals) != 1 or totals.pop() != len(rows):
        raise WorkflowTransferError("workflow census is incomplete")
    ids = [row.get("id") for row in rows]
    if any(not isinstance(value, int) for value in ids) or len(ids) != len(set(ids)):
        raise WorkflowTransferError("workflow census contains invalid or duplicate identities")
    return rows


def _set_state(repo: str, workflow_id: int, action: str) -> None:
    result = subprocess.run(
        ["gh", "api", "--method", "PUT", f"/repos/{repo}/actions/workflows/{workflow_id}/{action}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkflowTransferError(f"workflow {action} failed for ID {workflow_id}")


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise WorkflowTransferError(f"expected JSON object: {path}")
    return value


def _private_manifest(path: Path) -> dict[str, Any]:
    if ".limen-private" not in path.resolve().parts:
        raise WorkflowTransferError("transfer manifest must remain under .limen-private")
    manifest = _load(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != canonical_sha256(manifest):
        raise WorkflowTransferError("transfer manifest content digest is absent or invalid")
    if manifest.get("identity") != LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json"):
        raise WorkflowTransferError("transfer manifest repository identity differs from runtime")
    settings = (manifest.get("github") or {}).get("repository_settings") or {}
    actions = (manifest.get("github") or {}).get("actions") or {}
    required_settings = {
        "description",
        "homepage",
        "topics",
        "has_downloads",
        "allow_update_branch",
        "custom_properties",
    }
    bundle = manifest.get("git_bundle") or {}
    if (
        manifest.get("schema_version") != "limen.repository_transfer_manifest.v2"
        or not required_settings.issubset(settings)
        or "fork_pr_contributor_approval" not in actions
        or bundle.get("restore_verified") is not True
    ):
        raise WorkflowTransferError("transfer manifest predates the complete v2 capture contract")
    return manifest


def _required_predicates(policy: dict[str, Any], row: dict[str, Any]) -> set[str]:
    predicates = set(policy["enable_predicates"]["base"])
    if row.get("recovery_ci"):
        predicates.update(policy["enable_predicates"]["recovery_ci"])
        return predicates
    predicates.update(policy["enable_predicates"]["effectful"])
    if row.get("app_dependent"):
        predicates.update(policy["enable_predicates"]["app_dependent"])
    if row.get("trusted_publisher_owner_bound"):
        predicates.update(policy["enable_predicates"]["release"])
    return predicates


def _policy_partition(policy: dict[str, Any]) -> set[str]:
    groups = [
        [value["path"] for value in policy["freeze"]],
        list(policy["leave_active_during_freeze"]),
        [value["path"] for value in policy["observe_and_requery_after_transfer"]],
    ]
    flattened = [path for group in groups for path in group]
    if len(flattened) != len(set(flattened)):
        raise WorkflowTransferError("workflow transfer policy contains duplicate path ownership")
    return set(flattened)


def _require_exact_partitions(
    live: dict[str, dict[str, Any]],
    initial: dict[str, dict[str, Any]],
    partition: set[str],
) -> None:
    if set(live) != partition or set(initial) != partition:
        raise WorkflowTransferError("live, manifest, and policy workflow partitions differ")


def _enable_target(values: list[str], freeze_rows: dict[str, dict[str, Any]]) -> str:
    if len(values) != 1:
        raise WorkflowTransferError("restore exactly one workflow per invocation")
    path = values[0]
    if path not in freeze_rows:
        raise WorkflowTransferError(f"enable target is not transfer-governed: {path}")
    if freeze_rows[path].get("zero_spend_prohibited"):
        raise WorkflowTransferError(f"{path} cannot be enabled while the zero-spend transfer constraint is active")
    if freeze_rows[path].get("non_enableable_tombstone"):
        raise WorkflowTransferError(f"{path} is a frozen API tombstone and cannot be enabled")
    return path


def _predicate_evidence(
    path: Path,
    *,
    required: set[str],
    repo: str,
    workflow: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    if ".limen-private" not in resolved.parts:
        raise WorkflowTransferError("workflow enable evidence must remain under .limen-private")
    evidence = _load(resolved)
    sidecar = resolved.with_suffix(resolved.suffix + ".sha256")
    if not sidecar.is_file() or sidecar.read_text().strip() != canonical_sha256(evidence):
        raise WorkflowTransferError("workflow enable evidence digest is absent or invalid")
    predicates = evidence.get("predicates")
    if (
        evidence.get("schema_version") != "limen.workflow_enable_evidence.v1"
        or evidence.get("repository_id") != LIMEN_REPOSITORY_IDENTITY.repository_id
        or str(evidence.get("observed_coordinate") or "").casefold() != repo.casefold()
        or str(evidence.get("canonical_coordinate") or "").casefold()
        != LIMEN_REPOSITORY_IDENTITY.canonical_coordinate.casefold()
        or evidence.get("default_sha") != manifest["github"]["default_sha"]
        or evidence.get("workflow_path") != workflow.get("path")
        or evidence.get("workflow_id") != workflow.get("id")
        or not isinstance(predicates, dict)
        or set(predicates) != required
    ):
        raise WorkflowTransferError("workflow enable evidence does not bind the exact target")
    for name, row in predicates.items():
        proof = row.get("evidence") if isinstance(row, dict) else None
        if (
            not isinstance(row, dict)
            or row.get("satisfied") is not True
            or not isinstance(proof, dict)
            or row.get("evidence_sha256") != canonical_sha256(proof)
            or proof.get("schema_version") != "limen.workflow_enable_predicate_evidence.v1"
            or proof.get("predicate") != name
            or proof.get("repository_id") != LIMEN_REPOSITORY_IDENTITY.repository_id
            or str(proof.get("canonical_coordinate") or "").casefold()
            != LIMEN_REPOSITORY_IDENTITY.canonical_coordinate.casefold()
            or proof.get("default_sha") != manifest["github"]["default_sha"]
            or proof.get("workflow_path") != workflow.get("path")
            or proof.get("workflow_id") != workflow.get("id")
            or not isinstance(proof.get("command"), str)
            or not proof["command"].strip()
            or proof.get("exit_code") != 0
            or not isinstance(proof.get("observed_at"), str)
        ):
            raise WorkflowTransferError(f"workflow enable predicate lacks durable evidence: {name}")
        try:
            observed_at = datetime.fromisoformat(proof["observed_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise WorkflowTransferError(f"workflow enable predicate timestamp is invalid: {name}") from exc
        if observed_at.tzinfo is None:
            raise WorkflowTransferError(f"workflow enable predicate timestamp lacks timezone: {name}")
    return evidence


def _states(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        ({"id": value.get("id"), "path": value.get("path"), "state": value.get("state")} for value in rows),
        key=lambda value: str(value["path"]),
    )


def _intent_path(receipt_path: Path) -> Path:
    return receipt_path.with_name(f"{receipt_path.name}.intent")


def _receipt_target(path: Path) -> Path:
    expanded = path.expanduser()
    return expanded.parent.resolve() / expanded.name


def _operation_intent(
    *,
    repo: str,
    manifest: dict[str, Any],
    operation: str,
    before: list[dict[str, Any]],
    plan: list[dict[str, Any]],
) -> dict[str, Any]:
    intent = {
        "schema_version": "limen.repository_transfer_workflow_intent.v1",
        "prepared_at": datetime.now(UTC).isoformat(),
        "operation": operation,
        "repository_identity": manifest["identity"],
        "observed_repo": repo,
        "manifest_sha256": canonical_sha256(manifest),
        "selected_paths": sorted(value["path"] for value in plan),
        "before_states_sha256": canonical_sha256(_states(before)),
        "transitions": sorted(
            (
                {
                    "id": value["id"],
                    "path": value["path"],
                    "from": value["current_state"],
                    "to": value["desired_state"],
                    "mutation_required": value["current_state"] != value["desired_state"],
                }
                for value in plan
            ),
            key=lambda value: str(value["path"]),
        ),
    }
    return {**intent, "intent_payload_sha256": canonical_sha256(intent)}


def _terminal_receipt(
    *,
    intent: dict[str, Any],
    status: str,
    after: list[dict[str, Any]] | None,
    failure: BaseException | None = None,
    observation_failure: BaseException | None = None,
) -> dict[str, Any]:
    if status not in {"succeeded", "failed"}:
        raise WorkflowTransferError("workflow receipt terminal status is invalid")
    if (status == "succeeded") != (failure is None):
        raise WorkflowTransferError("workflow receipt terminal status and failure disagree")
    after_states = _states(after) if after is not None else None
    receipt: dict[str, Any] = {
        "schema_version": "limen.repository_transfer_workflow_receipt.v2",
        "recorded_at": datetime.now(UTC).isoformat(),
        "status": status,
        "operation": intent["operation"],
        "repository_identity": intent["repository_identity"],
        "observed_repo": intent["observed_repo"],
        "manifest_sha256": intent["manifest_sha256"],
        "selected_paths": intent["selected_paths"],
        "intent_sha256": canonical_sha256(intent),
        "before_states_sha256": intent["before_states_sha256"],
        "after_states_available": after_states is not None,
        "after_states_sha256": canonical_sha256(after_states) if after_states is not None else None,
        "after_states": after_states,
    }
    if failure is not None:
        receipt["failure"] = {
            "error_class": type(failure).__name__,
            "error_sha256": canonical_sha256(str(failure)),
        }
    if observation_failure is not None:
        receipt["after_observation_failure"] = {
            "error_class": type(observation_failure).__name__,
            "error_sha256": canonical_sha256(str(observation_failure)),
        }
    return receipt


def _write_receipt(path: Path, receipt: dict[str, Any], *, immutable: bool = False) -> None:
    resolved = _receipt_target(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    if resolved.exists() or resolved.is_symlink():
        raise WorkflowTransferError("workflow operation receipt path already exists")
    temporary = resolved.with_name(f".{resolved.name}.{os.getpid()}.tmp")
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, resolved)
        except FileExistsError as exc:
            raise WorkflowTransferError("workflow operation receipt path already exists") from exc
        if immutable:
            resolved.chmod(0o400)
        directory = os.open(resolved.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _require_new_receipt_pair(path: Path) -> tuple[Path, Path]:
    receipt_path = _receipt_target(path)
    intent_path = _intent_path(receipt_path)
    if receipt_path.exists() or receipt_path.is_symlink() or intent_path.exists() or intent_path.is_symlink():
        raise WorkflowTransferError("workflow operation receipt or intent path already exists")
    return receipt_path, intent_path


def _mutate_with_journal(
    *,
    repo: str,
    manifest: dict[str, Any],
    operation: str,
    before: list[dict[str, Any]],
    plan: list[dict[str, Any]],
    receipt_path: Path,
) -> None:
    resolved_receipt, intent_path = _require_new_receipt_pair(receipt_path)
    intent = _operation_intent(
        repo=repo,
        manifest=manifest,
        operation=operation,
        before=before,
        plan=plan,
    )
    _write_receipt(intent_path, intent, immutable=True)

    after: list[dict[str, Any]] | None = None
    try:
        for value in plan:
            if value["current_state"] == value["desired_state"]:
                continue
            allowed_current = "disabled_manually" if operation == "enable" else "active"
            if value["current_state"] != allowed_current:
                raise WorkflowTransferError(f"unexpected workflow state for {value['path']}: {value['current_state']}")
            _set_state(repo, int(value["id"]), operation)

        after = _workflow_rows(repo)
        after_map = {value["path"]: value for value in after}
        desired = "active" if operation == "enable" else "disabled_manually"
        if any(path not in after_map or after_map[path].get("state") != desired for path in intent["selected_paths"]):
            raise WorkflowTransferError("post-operation workflow state verification failed")
    except Exception as exc:
        observation_failure: BaseException | None = None
        if after is None:
            try:
                after = _workflow_rows(repo)
            except Exception as observe_exc:  # the immutable intent still proves the exact attempted denominator
                observation_failure = observe_exc
        failure_receipt = _terminal_receipt(
            intent=intent,
            status="failed",
            after=after,
            failure=exc,
            observation_failure=observation_failure,
        )
        _write_receipt(resolved_receipt, failure_receipt)
        raise

    success_receipt = _terminal_receipt(intent=intent, status="succeeded", after=after)
    _write_receipt(resolved_receipt, success_receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--repo", default=LIMEN_REPOSITORY_IDENTITY.canonical_coordinate)
    parser.add_argument("--receipt", type=Path)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--plan", action="store_true")
    operation.add_argument("--freeze", action="store_true")
    operation.add_argument("--check", action="store_true")
    operation.add_argument("--enable", action="append", metavar="WORKFLOW_PATH")
    parser.add_argument("--predicate-receipt", type=Path)
    args = parser.parse_args()

    try:
        manifest = _private_manifest(args.manifest.expanduser().resolve())
        if (args.freeze or args.enable) and args.receipt is None:
            raise WorkflowTransferError("workflow mutations require a new durable --receipt path")
        if args.receipt is not None:
            _require_new_receipt_pair(args.receipt)
        metadata = _gh_json([f"/repos/{args.repo}"])
        if metadata.get("id") != LIMEN_REPOSITORY_IDENTITY.repository_id:
            raise WorkflowTransferError("live repository ID differs from transfer manifest")
        if not LIMEN_REPOSITORY_IDENTITY.accepts(str(metadata.get("full_name") or "")):
            raise WorkflowTransferError("live repository coordinate is not a registered alias")
        policy = _load(POLICY_PATH)
        partition = _policy_partition(policy)
        freeze_rows = {value["path"]: value for value in policy["freeze"]}
        initial = {value["path"]: value for value in manifest["github"]["actions"]["workflow_states"]}
        before = _workflow_rows(args.repo)
        live = {value["path"]: value for value in before}
        if len(live) != len(before) or len(initial) != len(manifest["github"]["actions"]["workflow_states"]):
            raise WorkflowTransferError("workflow census contains duplicate paths")
        _require_exact_partitions(live, initial, partition)

        selected: list[str]
        action: str
        if args.enable:
            selected = [_enable_target(list(args.enable), freeze_rows)]
            path = selected[0]
            if args.predicate_receipt is None:
                raise WorkflowTransferError(f"{path} requires one durable predicate receipt")
            action = "enable"
        else:
            selected = sorted(freeze_rows)
            action = "disable"

        plan = []
        for path in selected:
            current = live[path]
            snapshot = initial.get(path)
            if snapshot is None or snapshot.get("id") != current.get("id"):
                raise WorkflowTransferError(f"workflow identity drift since manifest: {path}")
            desired = "active" if action == "enable" else "disabled_manually"
            plan.append(
                {
                    "id": current["id"],
                    "path": path,
                    "class": freeze_rows[path]["class"],
                    "current_state": current["state"],
                    "desired_state": desired,
                }
            )

        if args.plan:
            print(json.dumps({"operation": "freeze", "workflows": plan}, indent=2, sort_keys=True))
            return 0

        if args.enable:
            if str(metadata.get("full_name") or "").casefold() != (
                LIMEN_REPOSITORY_IDENTITY.canonical_coordinate.casefold()
            ):
                raise WorkflowTransferError("workflow restoration requires the canonical post-transfer coordinate")
            if metadata.get("private") is not False:
                raise WorkflowTransferError("workflow restoration requires verified public repository state")
            default_branch = str(metadata.get("default_branch") or "")
            live_default = _gh_json([f"/repos/{args.repo}/commits/{default_branch}"])
            if live_default.get("sha") != manifest["github"]["default_sha"]:
                raise WorkflowTransferError("workflow restoration default SHA differs from the evidence manifest")
            path = selected[0]
            _predicate_evidence(
                args.predicate_receipt,
                required=_required_predicates(policy, freeze_rows[path]),
                repo=args.repo,
                workflow=live[path],
                manifest=manifest,
            )

        if args.check:
            wrong = [value for value in plan if value["current_state"] != "disabled_manually"]
            if wrong:
                raise WorkflowTransferError(f"{len(wrong)} transfer-sensitive workflows are not frozen")
            print(f"repository-transfer-workflows: PASS frozen={len(plan)}")
            return 0

        if args.receipt is None:
            raise WorkflowTransferError("workflow mutation receipt path disappeared after preflight")
        _mutate_with_journal(
            repo=args.repo,
            manifest=manifest,
            operation=action,
            before=before,
            plan=plan,
            receipt_path=args.receipt,
        )
        print(f"repository-transfer-workflows: PASS operation={action} workflows={len(selected)}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError, WorkflowTransferError) as exc:
        print(f"repository-transfer-workflows: FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
