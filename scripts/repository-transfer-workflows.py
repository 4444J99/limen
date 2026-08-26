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
from urllib.parse import quote


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.repository_identity import LIMEN_REPOSITORY_IDENTITY  # noqa: E402
from limen.repository_transfer import canonical_sha256  # noqa: E402


POLICY_PATH = ROOT / "institutio" / "github" / "workflow-transfer-policy.json"
PUBLIC_CI_ADMISSION_RECEIPT = (
    ROOT / "docs" / "continuations" / "personal-control-plane-20260825" / "public-ci-admission-receipt.json"
)
TRUSTED_PREDICATE_WORKFLOW = ".github/workflows/ci.yml"
TRUSTED_PREDICATE_JOB = "verify"
TRUSTED_PREDICATE_STEP = "Run whole-repo verification (verify-whole.sh)"


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


def _gh_connection(endpoint: str, key: str) -> dict[str, Any]:
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise WorkflowTransferError(f"GitHub {key} census failed")
    try:
        pages = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise WorkflowTransferError(f"GitHub {key} census returned invalid JSON") from exc
    if not isinstance(pages, list) or not pages:
        raise WorkflowTransferError(f"GitHub {key} census returned no pages")
    rows: list[dict[str, Any]] = []
    totals: set[int] = set()
    for page in pages:
        if not isinstance(page, dict) or not isinstance(page.get(key), list):
            raise WorkflowTransferError(f"GitHub {key} census page is malformed")
        if not isinstance(page.get("total_count"), int):
            raise WorkflowTransferError(f"GitHub {key} census omitted its denominator")
        totals.add(page["total_count"])
        if any(not isinstance(row, dict) for row in page[key]):
            raise WorkflowTransferError(f"GitHub {key} census contains a non-object row")
        rows.extend(page[key])
    if len(totals) != 1 or totals.pop() != len(rows):
        raise WorkflowTransferError(f"GitHub {key} census is incomplete")
    return {"total_count": len(rows), key: rows}


def _live_name_census(endpoint: str, key: str) -> dict[str, Any]:
    payload = _gh_connection(endpoint, key)
    rows = payload[key]
    if any(not isinstance(row.get("name"), str) for row in rows):
        raise WorkflowTransferError(f"GitHub {key} census contains a nameless row")
    names = sorted(row["name"] for row in rows)
    if len(names) != len(set(names)):
        raise WorkflowTransferError(f"GitHub {key} census contains duplicate names")
    return {"available": True, "names": names, "total_count": len(names)}


def _live_environments(repo: str) -> list[dict[str, Any]]:
    payload = _gh_connection(f"/repos/{repo}/environments?per_page=100", "environments")
    environments: list[dict[str, Any]] = []
    for row in payload["environments"]:
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise WorkflowTransferError("GitHub environments census contains a nameless row")
        encoded = quote(name, safe="")
        environments.append(
            {
                "name": name,
                "id": row.get("id"),
                "node_id": row.get("node_id"),
                "protection_rules": row.get("protection_rules"),
                "deployment_branch_policy": row.get("deployment_branch_policy"),
                "secret_names": _live_name_census(
                    f"/repos/{repo}/environments/{encoded}/secrets?per_page=100",
                    "secrets",
                ),
                "variable_names": _live_name_census(
                    f"/repos/{repo}/environments/{encoded}/variables?per_page=100",
                    "variables",
                ),
            }
        )
    return sorted(environments, key=lambda value: value["name"])


def _metadata(repo: str, context: dict[str, Any]) -> dict[str, Any]:
    if "metadata" not in context:
        context["metadata"] = _gh_json([f"/repos/{repo}"])
    return context["metadata"]


def _live_workflows(repo: str, context: dict[str, Any]) -> list[dict[str, Any]]:
    if "workflows" not in context:
        context["workflows"] = _workflow_rows(repo)
    return context["workflows"]


def _verify_ci_admission(
    *,
    repo: str,
    manifest: dict[str, Any],
    policy: dict[str, Any],
    context: dict[str, Any],
) -> None:
    if context.get("ci_admission_verified"):
        return
    receipt = _load(PUBLIC_CI_ADMISSION_RECEIPT)
    unsigned = {key: value for key, value in receipt.items() if key != "receipt_digest"}
    workflow = receipt.get("workflow") or {}
    identity = receipt.get("repository_identity") or {}
    zero_spend = receipt.get("zero_spend") or {}
    if (
        receipt.get("schema_version") != "limen.ci_admission_receipt.v1"
        or receipt.get("receipt_digest") != canonical_sha256(unsigned)
        or receipt.get("admission_passed") is not True
        or receipt.get("admission_result") != "CI_EXECUTED_STEP_ADMISSION"
        or identity != LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json")
        or (receipt.get("controller") or {}).get("repository") != repo
        or (receipt.get("controller") or {}).get("sha") != manifest["github"]["default_sha"]
        or (receipt.get("target") or {}).get("repository") != repo
        or (receipt.get("target") or {}).get("sha") != manifest["github"]["default_sha"]
        or workflow.get("path") != TRUSTED_PREDICATE_WORKFLOW
        or not isinstance(workflow.get("id"), int)
        or not isinstance(workflow.get("run_id"), int)
        or zero_spend
        != {
            "github_hosted_standard_runners": True,
            "paid_workflow_disabled": True,
            "repository_public": True,
        }
    ):
        raise WorkflowTransferError("public CI admission receipt is malformed or not exact-target bound")

    run = _gh_json([f"/repos/{repo}/actions/runs/{workflow['run_id']}"])
    if (
        run.get("id") != workflow["run_id"]
        or run.get("workflow_id") != workflow["id"]
        or run.get("path") != TRUSTED_PREDICATE_WORKFLOW
        or run.get("head_sha") != manifest["github"]["default_sha"]
        or run.get("event") != workflow.get("event")
        or run.get("status") != "completed"
        or run.get("conclusion") != workflow.get("conclusion")
        or (run.get("repository") or {}).get("id") != LIMEN_REPOSITORY_IDENTITY.repository_id
        or str((run.get("repository") or {}).get("full_name") or "").casefold() != repo.casefold()
    ):
        raise WorkflowTransferError("public CI admission run no longer matches its exact receipt")

    jobs_payload = _gh_connection(
        f"/repos/{repo}/actions/runs/{workflow['run_id']}/jobs?per_page=100",
        "jobs",
    )
    live_jobs: list[dict[str, Any]] = []
    for job in jobs_payload["jobs"]:
        steps = job.get("steps")
        if not isinstance(steps, list):
            raise WorkflowTransferError("public CI admission job omitted executed-step evidence")
        executed_steps = sum(1 for step in steps if step.get("conclusion") != "skipped")
        runner_id = job.get("runner_id")
        if executed_steps:
            if (
                isinstance(runner_id, bool)
                or not isinstance(runner_id, int)
                or runner_id <= 0
                or job.get("runner_group_name") != "GitHub Actions"
                or not str(job.get("runner_name") or "").startswith("GitHub Actions ")
            ):
                raise WorkflowTransferError("public CI admission job did not use a GitHub-hosted runner")
        live_jobs.append(
            {
                "id": job.get("id"),
                "name": job.get("name"),
                "conclusion": job.get("conclusion"),
                "runner_id": runner_id,
                "executed_steps": executed_steps,
            }
        )
    expected_jobs = receipt.get("jobs")
    if (
        not isinstance(expected_jobs, list)
        or sorted(live_jobs, key=lambda value: int(value["id"]))
        != sorted(expected_jobs, key=lambda value: int(value["id"]))
        or sum(int(value["executed_steps"]) for value in live_jobs) <= 0
    ):
        raise WorkflowTransferError("public CI admission job denominator or exact execution evidence drifted")

    workflows = {row.get("path"): row for row in _live_workflows(repo, context)}
    if workflows.get(TRUSTED_PREDICATE_WORKFLOW, {}).get("id") != workflow["id"]:
        raise WorkflowTransferError("public CI admission workflow identity drifted")
    paid_paths = [row["path"] for row in policy["freeze"] if row.get("zero_spend_prohibited")]
    if len(paid_paths) != 1 or workflows.get(paid_paths[0], {}).get("state") != "disabled_manually":
        raise WorkflowTransferError("zero-spend-prohibited workflow is not verifiably disabled")
    if _metadata(repo, context).get("private") is not False:
        raise WorkflowTransferError("public CI admission repository is no longer public")
    context["ci_admission_verified"] = True


def _verify_trusted_predicate_job(
    proof: dict[str, Any],
    *,
    repo: str,
    manifest: dict[str, Any],
) -> None:
    provider = proof.get("provider_receipt")
    if (
        not isinstance(provider, dict)
        or provider.get("schema_version") != "limen.github_predicate_job.v1"
        or provider.get("repository_id") != LIMEN_REPOSITORY_IDENTITY.repository_id
        or provider.get("head_sha") != manifest["github"]["default_sha"]
        or not isinstance(provider.get("run_id"), int)
        or not isinstance(provider.get("job_id"), int)
    ):
        raise WorkflowTransferError("exact predicate requires an authenticated GitHub job receipt")
    run = _gh_json([f"/repos/{repo}/actions/runs/{provider['run_id']}"])
    if (
        run.get("id") != provider["run_id"]
        or run.get("path") != TRUSTED_PREDICATE_WORKFLOW
        or run.get("head_sha") != manifest["github"]["default_sha"]
        or run.get("status") != "completed"
        or run.get("conclusion") != "success"
        or (run.get("repository") or {}).get("id") != LIMEN_REPOSITORY_IDENTITY.repository_id
    ):
        raise WorkflowTransferError("authenticated predicate run is not a successful exact-head verification")
    job = _gh_json([f"/repos/{repo}/actions/jobs/{provider['job_id']}"])
    steps = job.get("steps")
    matching_steps = [
        step for step in steps or [] if isinstance(step, dict) and step.get("name") == TRUSTED_PREDICATE_STEP
    ]
    if (
        job.get("id") != provider["job_id"]
        or job.get("run_id") != provider["run_id"]
        or job.get("head_sha") != manifest["github"]["default_sha"]
        or job.get("name") != TRUSTED_PREDICATE_JOB
        or job.get("conclusion") != "success"
        or job.get("runner_group_name") != "GitHub Actions"
        or isinstance(job.get("runner_id"), bool)
        or not isinstance(job.get("runner_id"), int)
        or job["runner_id"] <= 0
        or len(matching_steps) != 1
        or matching_steps[0].get("conclusion") != "success"
    ):
        raise WorkflowTransferError("authenticated predicate job lacks exact whole-repository success")


def _verify_live_enable_predicate(
    name: str,
    proof: dict[str, Any],
    *,
    repo: str,
    workflow: dict[str, Any],
    manifest: dict[str, Any],
    policy: dict[str, Any],
    context: dict[str, Any],
) -> None:
    metadata = _metadata(repo, context)
    identity = LIMEN_REPOSITORY_IDENTITY
    snapshot = {row["path"]: row for row in manifest["github"]["actions"]["workflow_states"]}.get(workflow.get("path"))
    if name == "repository_transferred":
        if (
            metadata.get("id") != identity.repository_id
            or str(metadata.get("full_name") or "").casefold() != identity.canonical_coordinate.casefold()
        ):
            raise WorkflowTransferError("repository transfer is not live at the canonical coordinate")
        for alias in identity.historical_aliases:
            if _gh_json([f"/repos/{alias}"]).get("id") != identity.repository_id:
                raise WorkflowTransferError("historical repository alias no longer resolves the stable identity")
        return
    if name == "repository_id_verified":
        if metadata.get("id") != identity.repository_id:
            raise WorkflowTransferError("live repository ID differs from the stable identity")
        return
    if name == "default_sha_verified":
        default_branch = str(metadata.get("default_branch") or "")
        if (
            not default_branch
            or _gh_json([f"/repos/{repo}/commits/{default_branch}"]).get("sha") != manifest["github"]["default_sha"]
        ):
            raise WorkflowTransferError("live default SHA differs from the transfer manifest")
        return
    if name == "workflow_state_matches_manifest":
        if (
            not isinstance(snapshot, dict)
            or snapshot.get("id") != workflow.get("id")
            or snapshot.get("path") != workflow.get("path")
            or snapshot.get("state") != "active"
            or workflow.get("state") not in {"active", "disabled_manually"}
        ):
            raise WorkflowTransferError("workflow state or identity does not match its active manifest owner")
        return
    if name == "public_repository_verified":
        if metadata.get("private") is not False:
            raise WorkflowTransferError("repository is not public")
        return
    if name in {"github_hosted_standard_runner_verified", "zero_spend_policy_verified"}:
        _verify_ci_admission(repo=repo, manifest=manifest, policy=policy, context=context)
        return
    if name == "repository_secrets_verified":
        actions = manifest["github"]["actions"]
        if _live_name_census(f"/repos/{repo}/actions/secrets?per_page=100", "secrets") != actions.get(
            "secret_names"
        ) or _live_name_census(f"/repos/{repo}/actions/variables?per_page=100", "variables") != actions.get(
            "variable_names"
        ):
            raise WorkflowTransferError("repository secret or variable name census differs from the manifest")
        return
    if name == "environment_bindings_verified":
        if _live_environments(repo) != manifest["github"].get("environments"):
            raise WorkflowTransferError("repository environment bindings differ from the manifest")
        return
    if name == "exact_predicates_verified":
        _verify_trusted_predicate_job(proof, repo=repo, manifest=manifest)
        return
    if name == "exact_repository_app_access_verified":
        result = subprocess.run(
            ["bash", str(ROOT / "scripts" / "gh-app-token.sh"), "--repo", repo, "--verify-app"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        if result.returncode != 0:
            raise WorkflowTransferError("exact-repository GitHub App access is unavailable")
        return
    if name == "pypi_trusted_publisher_owner_updated":
        raise WorkflowTransferError("PyPI trusted-publisher owner has no independently verified receipt")
    raise WorkflowTransferError(f"workflow enable predicate has no live verifier: {name}")


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
    access = (manifest.get("github") or {}).get("access") or {}
    access_policy = access.get("policy") or {}
    access_denominators = access.get("denominators") or {}
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
        manifest.get("schema_version") != "limen.repository_transfer_manifest.v3"
        or not required_settings.issubset(settings)
        or "fork_pr_contributor_approval" not in actions
        or access.get("schema_version") != "limen.repository_access_census.v1"
        or access_policy.get("mode") != "never_grant"
        or access_policy.get("satisfied") is not True
        or access_denominators.get("unexpected_access") != 0
        or bundle.get("restore_verified") is not True
    ):
        raise WorkflowTransferError("transfer manifest predates the complete v3 capture contract")
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
    policy: dict[str, Any] | None = None,
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
    proofs: dict[str, dict[str, Any]] = {}
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
        proofs[name] = proof
    live_context: dict[str, Any] = {}
    live_policy = policy or _load(POLICY_PATH)
    for name in sorted(required):
        _verify_live_enable_predicate(
            name,
            proofs[name],
            repo=repo,
            workflow=workflow,
            manifest=manifest,
            policy=live_policy,
            context=live_context,
        )
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


def _load_interrupted_intent(
    *,
    repo: str,
    manifest: dict[str, Any],
    receipt_path: Path,
) -> tuple[Path, dict[str, Any]]:
    resolved_receipt = _receipt_target(receipt_path)
    intent_path = _intent_path(resolved_receipt)
    if resolved_receipt.exists() or resolved_receipt.is_symlink():
        raise WorkflowTransferError("interrupted workflow operation already has a terminal receipt")
    if intent_path.is_symlink() or not intent_path.is_file():
        raise WorkflowTransferError("interrupted workflow operation has no regular intent file")
    intent = _load(intent_path)
    payload = {key: value for key, value in intent.items() if key != "intent_payload_sha256"}
    transitions = intent.get("transitions")
    selected_paths = intent.get("selected_paths")
    operation = intent.get("operation")
    desired = "active" if operation == "enable" else "disabled_manually"
    allowed_source = "disabled_manually" if operation == "enable" else "active"
    if (
        intent.get("schema_version") != "limen.repository_transfer_workflow_intent.v1"
        or intent.get("intent_payload_sha256") != canonical_sha256(payload)
        or intent.get("repository_identity") != manifest["identity"]
        or str(intent.get("observed_repo") or "").casefold() != repo.casefold()
        or intent.get("manifest_sha256") != canonical_sha256(manifest)
        or operation not in {"enable", "disable"}
        or not isinstance(selected_paths, list)
        or not selected_paths
        or selected_paths != sorted(selected_paths)
        or any(not isinstance(path, str) or not path for path in selected_paths)
        or not isinstance(transitions, list)
        or len(transitions) != len(selected_paths)
        or not isinstance(intent.get("before_states_sha256"), str)
    ):
        raise WorkflowTransferError("interrupted workflow intent is invalid or not bound to this operation")
    transition_paths: list[str] = []
    transition_ids: list[int] = []
    for transition in transitions:
        if not isinstance(transition, dict):
            raise WorkflowTransferError("interrupted workflow intent contains a malformed transition")
        path = transition.get("path")
        workflow_id = transition.get("id")
        mutation_required = transition.get("mutation_required")
        source = transition.get("from")
        target = transition.get("to")
        if (
            not isinstance(path, str)
            or not path
            or not isinstance(workflow_id, int)
            or not isinstance(mutation_required, bool)
            or target != desired
            or (mutation_required and source != allowed_source)
            or (not mutation_required and source != desired)
        ):
            raise WorkflowTransferError("interrupted workflow intent contains an invalid transition")
        transition_paths.append(path)
        transition_ids.append(workflow_id)
    if (
        sorted(transition_paths) != selected_paths
        or len(transition_paths) != len(set(transition_paths))
        or len(transition_ids) != len(set(transition_ids))
    ):
        raise WorkflowTransferError("interrupted workflow intent transition identity is ambiguous")
    return resolved_receipt, intent


def _reconcile_interrupted_journal(
    *,
    repo: str,
    manifest: dict[str, Any],
    receipt_path: Path,
    observed: list[dict[str, Any]],
) -> dict[str, Any]:
    resolved_receipt, intent = _load_interrupted_intent(
        repo=repo,
        manifest=manifest,
        receipt_path=receipt_path,
    )
    observed_by_path = {row.get("path"): row for row in observed if isinstance(row, dict)}
    if len(observed_by_path) != len(observed):
        raise WorkflowTransferError("live workflow census contains duplicate paths")
    incomplete: list[str] = []
    for transition in intent["transitions"]:
        live = observed_by_path.get(transition["path"])
        if live is None or live.get("id") != transition["id"]:
            raise WorkflowTransferError("live workflow identity differs from interrupted intent")
        if live.get("state") != transition["to"]:
            incomplete.append(transition["path"])
    failure: WorkflowTransferError | None = None
    if incomplete:
        failure = WorkflowTransferError(
            f"interrupted workflow operation left {len(incomplete)} selected workflow(s) incomplete"
        )
    receipt = _terminal_receipt(
        intent=intent,
        status="failed" if failure is not None else "succeeded",
        after=observed,
        failure=failure,
    )
    receipt["reconciliation"] = {
        "schema_version": "limen.repository_transfer_workflow_reconciliation.v1",
        "interrupted_intent_sha256": canonical_sha256(intent),
        "observed_without_mutation": True,
        "incomplete_paths": sorted(incomplete),
    }
    _write_receipt(resolved_receipt, receipt)
    return receipt


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
    operation.add_argument("--reconcile", action="store_true")
    parser.add_argument("--predicate-receipt", type=Path)
    args = parser.parse_args()

    try:
        manifest = _private_manifest(args.manifest.expanduser().resolve())
        if (args.freeze or args.enable or args.reconcile) and args.receipt is None:
            raise WorkflowTransferError("workflow mutations require a new durable --receipt path")
        if args.receipt is not None and not args.reconcile:
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

        if args.reconcile:
            if args.receipt is None:
                raise WorkflowTransferError("workflow reconciliation receipt path disappeared after preflight")
            receipt = _reconcile_interrupted_journal(
                repo=args.repo,
                manifest=manifest,
                receipt_path=args.receipt,
                observed=before,
            )
            if receipt["status"] != "succeeded":
                print(
                    f"repository-transfer-workflows: FAIL reconciled_status={receipt['status']}",
                    file=sys.stderr,
                )
                return 1
            print("repository-transfer-workflows: PASS reconciled_status=succeeded")
            return 0

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
                policy=policy,
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
