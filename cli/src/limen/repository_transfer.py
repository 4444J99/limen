"""Read-only repository-transfer census and invariant comparison.

The full manifest is private custody material.  Only its content digest and
non-sensitive denominator counts belong in a public transfer receipt.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import rfc8785

from limen.repository_identity import LIMEN_TRANSFER_FALLBACK_COORDINATE, RepositoryIdentityV1


Json = dict[str, Any] | list[Any]
Runner = Callable[..., subprocess.CompletedProcess[str]]


class TransferCaptureError(RuntimeError):
    """The transfer census could not be completed exhaustively."""


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class GhClient:
    """Small fail-closed wrapper around the authenticated GitHub CLI."""

    def __init__(self, runner: Runner = subprocess.run) -> None:
        self._runner = runner

    def _json(self, arguments: list[str], *, stdin: Mapping[str, Any] | None = None) -> Json:
        result = self._runner(
            ["gh", "api", *arguments],
            input=(json.dumps(stdin) if stdin is not None else None),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            suffix = detail[-1][:240] if detail else "unknown GitHub API error"
            raise TransferCaptureError(f"GitHub API request failed: {suffix}")
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise TransferCaptureError("GitHub API returned invalid JSON") from exc

    def object(self, endpoint: str) -> dict[str, Any]:
        value = self._json([endpoint])
        if not isinstance(value, dict):
            raise TransferCaptureError(f"expected an object from {endpoint}")
        return value

    def optional_object(self, endpoint: str) -> dict[str, Any]:
        try:
            return {"available": True, "value": self.object(endpoint)}
        except TransferCaptureError as exc:
            return {
                "available": False,
                "error_class": "github_api_unavailable",
                "error_digest": hashlib.sha256(str(exc).encode()).hexdigest(),
            }

    def list(self, endpoint: str) -> list[Any]:
        value = self._json(["--paginate", "--slurp", endpoint])
        if not isinstance(value, list):
            raise TransferCaptureError(f"expected paginated pages from {endpoint}")
        flattened: list[Any] = []
        for page in value:
            if not isinstance(page, list):
                raise TransferCaptureError(f"expected list page from {endpoint}")
            flattened.extend(page)
        return flattened

    def optional_list(self, endpoint: str) -> dict[str, Any]:
        try:
            return {"available": True, "value": self.list(endpoint)}
        except TransferCaptureError as exc:
            return {
                "available": False,
                "error_class": "github_api_unavailable",
                "error_digest": hashlib.sha256(str(exc).encode()).hexdigest(),
            }

    def connection(self, endpoint: str, key: str) -> dict[str, Any]:
        value = self._json(["--paginate", "--slurp", endpoint])
        if not isinstance(value, list):
            raise TransferCaptureError(f"expected paginated pages from {endpoint}")
        flattened: list[Any] = []
        total_count: int | None = None
        for page in value:
            if not isinstance(page, dict) or not isinstance(page.get(key), list):
                raise TransferCaptureError(f"expected {key} connection page from {endpoint}")
            flattened.extend(page[key])
            if isinstance(page.get("total_count"), int):
                total_count = page["total_count"]
        if total_count is not None and len(flattened) != total_count:
            raise TransferCaptureError(f"incomplete {key} pagination from {endpoint}")
        return {"total_count": total_count if total_count is not None else len(flattened), key: flattened}

    def optional_connection(self, endpoint: str, key: str) -> dict[str, Any]:
        try:
            return {"available": True, "value": self.connection(endpoint, key)}
        except TransferCaptureError as exc:
            return {
                "available": False,
                "error_class": "github_api_unavailable",
                "error_digest": hashlib.sha256(str(exc).encode()).hexdigest(),
            }

    def graphql(self, query: str, variables: Mapping[str, Any]) -> dict[str, Any]:
        value = self._json(["graphql", "--input", "-"], stdin={"query": query, "variables": variables})
        if not isinstance(value, dict) or value.get("errors"):
            raise TransferCaptureError("GitHub GraphQL request failed or returned errors")
        data = value.get("data")
        if not isinstance(data, dict):
            raise TransferCaptureError("GitHub GraphQL response omitted data")
        return data


_REPOSITORY_SETTING_KEYS = (
    "id",
    "node_id",
    "name",
    "full_name",
    "private",
    "visibility",
    "default_branch",
    "description",
    "homepage",
    "topics",
    "has_issues",
    "has_projects",
    "has_wiki",
    "has_downloads",
    "has_discussions",
    "is_template",
    "archived",
    "disabled",
    "allow_forking",
    "web_commit_signoff_required",
    "allow_squash_merge",
    "allow_merge_commit",
    "allow_rebase_merge",
    "allow_auto_merge",
    "allow_update_branch",
    "delete_branch_on_merge",
    "use_squash_pr_title_as_default",
    "squash_merge_commit_message",
    "squash_merge_commit_title",
    "merge_commit_message",
    "merge_commit_title",
    "security_and_analysis",
    "custom_properties",
)


def _select(source: Mapping[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    return {key: source.get(key) for key in keys}


def _without_github_links(value: Any) -> Any:
    """Remove API-navigation fields while retaining repository settings and predicates."""

    if isinstance(value, list):
        return [_without_github_links(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: _without_github_links(item)
        for key, item in value.items()
        if key != "_links" and key != "url" and not key.endswith("_url")
    }


def _webhook_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    return _select(raw, ("id", "type", "name", "active", "events", "config", "created_at", "updated_at"))


def _deploy_key_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    return _select(raw, ("id", "title", "key", "read_only", "created_at", "verified"))


def _required_object_value(result: dict[str, Any], label: str) -> dict[str, Any]:
    """Return one readable object without allowing an unavailable envelope into a manifest."""

    if not result.get("available"):
        raise TransferCaptureError(f"{label} census is unavailable")
    payload = result.get("value")
    if not isinstance(payload, Mapping):
        raise TransferCaptureError(f"{label} census is malformed")
    return _without_github_links(dict(payload))


def _required_record_values(result: dict[str, Any], label: str) -> list[Mapping[str, Any]]:
    """Return a fully paginated readable record list or fail the transfer capture."""

    if not result.get("available"):
        raise TransferCaptureError(f"{label} census is unavailable")
    payload = result.get("value")
    if not isinstance(payload, list) or any(not isinstance(value, Mapping) for value in payload):
        raise TransferCaptureError(f"{label} census is malformed")
    return payload


def _required_webhook_census(client: GhClient, coordinate: str) -> dict[str, Any]:
    raw = _required_record_values(
        client.optional_list(f"/repos/{coordinate}/hooks?per_page=100"),
        "repository webhooks",
    )
    records = [_webhook_record(value) for value in raw]
    ids = [value.get("id") for value in records]
    if (
        any(not isinstance(value, int) or value <= 0 for value in ids)
        or len(ids) != len(set(ids))
        or any(
            not isinstance(value.get("active"), bool)
            or not isinstance(value.get("events"), list)
            or any(not isinstance(event, str) for event in value.get("events") or [])
            or not isinstance(value.get("config"), Mapping)
            for value in records
        )
    ):
        raise TransferCaptureError("repository webhooks census is incomplete")
    return {"available": True, "value": sorted(records, key=lambda value: int(value["id"]))}


def _required_deploy_key_census(client: GhClient, coordinate: str) -> dict[str, Any]:
    raw = _required_record_values(
        client.optional_list(f"/repos/{coordinate}/keys?per_page=100"),
        "repository deploy keys",
    )
    records = [_deploy_key_record(value) for value in raw]
    ids = [value.get("id") for value in records]
    if (
        any(not isinstance(value, int) or value <= 0 for value in ids)
        or len(ids) != len(set(ids))
        or any(
            not isinstance(value.get("title"), str)
            or not isinstance(value.get("key"), str)
            or not isinstance(value.get("read_only"), bool)
            for value in records
        )
    ):
        raise TransferCaptureError("repository deploy keys census is incomplete")
    return {"available": True, "value": sorted(records, key=lambda value: int(value["id"]))}


def _required_branch_protection_census(
    client: GhClient,
    coordinate: str,
    branch_rows: list[Any],
) -> dict[str, dict[str, Any]]:
    if any(
        not isinstance(value, Mapping)
        or not isinstance(value.get("name"), str)
        or not isinstance(value.get("protected"), bool)
        for value in branch_rows
    ):
        raise TransferCaptureError("repository branches census contains a nameless or non-object row")
    names = [str(value["name"]) for value in branch_rows]
    if len(names) != len(set(names)):
        raise TransferCaptureError("repository branches census contains duplicate identities")

    protection: dict[str, dict[str, Any]] = {}
    for branch in sorted(branch_rows, key=lambda value: str(value["name"])):
        if branch.get("protected") is True:
            name = str(branch["name"])
            encoded_name = quote(name, safe="")
            protection[name] = {
                "available": True,
                "value": _required_object_value(
                    client.optional_object(f"/repos/{coordinate}/branches/{encoded_name}/protection"),
                    f"protected branch {name}",
                ),
            }
    return protection


def _required_actions_settings(client: GhClient, coordinate: str) -> dict[str, Any]:
    prefix = f"/repos/{coordinate}/actions/permissions"
    permissions_value = _required_object_value(
        client.optional_object(prefix),
        "GitHub Actions permissions",
    )
    allowed_actions = permissions_value.get("allowed_actions")
    if (
        not isinstance(permissions_value.get("enabled"), bool)
        or allowed_actions not in {"all", "local_only", "selected"}
        or not isinstance(permissions_value.get("sha_pinning_required"), bool)
    ):
        raise TransferCaptureError("GitHub Actions permissions census is incomplete")
    permissions = {"available": True, "value": permissions_value}

    workflow_permissions_value = _required_object_value(
        client.optional_object(f"{prefix}/workflow"),
        "GitHub Actions workflow permissions",
    )
    if workflow_permissions_value.get("default_workflow_permissions") not in {"read", "write"} or not isinstance(
        workflow_permissions_value.get("can_approve_pull_request_reviews"), bool
    ):
        raise TransferCaptureError("GitHub Actions workflow permissions census is incomplete")
    workflow_permissions = {"available": True, "value": workflow_permissions_value}

    if allowed_actions == "selected":
        selected_value = _required_object_value(
            client.optional_object(f"{prefix}/selected-actions"),
            "GitHub Actions selected actions",
        )
        if (
            not isinstance(selected_value.get("github_owned_allowed"), bool)
            or not isinstance(selected_value.get("verified_allowed"), bool)
            or not isinstance(selected_value.get("patterns_allowed"), list)
            or any(not isinstance(value, str) for value in selected_value.get("patterns_allowed") or [])
        ):
            raise TransferCaptureError("GitHub Actions selected actions census is incomplete")
        selected_actions: dict[str, Any] = {"available": True, "value": selected_value}
    else:
        selected_actions = dict(_SELECTED_ACTIONS_NOT_APPLICABLE)

    fork_approval_value = _required_object_value(
        client.optional_object(f"{prefix}/fork-pr-contributor-approval"),
        "GitHub Actions fork PR contributor approval",
    )
    if not isinstance(fork_approval_value.get("approval_policy"), str) or not fork_approval_value["approval_policy"]:
        raise TransferCaptureError("GitHub Actions fork PR contributor approval census is incomplete")
    fork_approval = {"available": True, "value": fork_approval_value}

    retention_value = _required_object_value(
        client.optional_object(f"{prefix}/artifact-and-log-retention"),
        "GitHub Actions artifact and log retention",
    )
    if (
        not isinstance(retention_value.get("days"), int)
        or retention_value["days"] <= 0
        or not isinstance(retention_value.get("maximum_allowed_days"), int)
        or retention_value["maximum_allowed_days"] <= 0
    ):
        raise TransferCaptureError("GitHub Actions artifact and log retention census is incomplete")
    retention = {"available": True, "value": retention_value}

    return {
        "permissions": permissions,
        "workflow_permissions": workflow_permissions,
        "selected_actions": selected_actions,
        "fork_pr_contributor_approval": fork_approval,
        "artifact_and_log_retention": retention,
    }


def _permission_map(raw: Any) -> dict[str, bool]:
    if not isinstance(raw, Mapping):
        return {}
    return {
        str(name): value
        for name, value in sorted(raw.items(), key=lambda item: str(item[0]))
        if isinstance(value, bool)
    }


def _collaborator_access_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "node_id": raw.get("node_id"),
        "login": raw.get("login"),
        "type": raw.get("type"),
        "role_name": raw.get("role_name"),
        "permissions": _permission_map(raw.get("permissions")),
    }


def _team_access_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    organization = raw.get("organization") or {}
    return {
        "id": raw.get("id"),
        "node_id": raw.get("node_id"),
        "slug": raw.get("slug"),
        "organization_id": organization.get("id") if isinstance(organization, Mapping) else None,
        "organization_login": organization.get("login") if isinstance(organization, Mapping) else None,
        "permission": raw.get("permission"),
        "permissions": _permission_map(raw.get("permissions")),
    }


def _invitation_access_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    invitee = raw.get("invitee") or {}
    email = raw.get("email")
    return {
        "id": raw.get("id"),
        "node_id": raw.get("node_id"),
        "invitee_id": invitee.get("id") if isinstance(invitee, Mapping) else None,
        "invitee_login": invitee.get("login") if isinstance(invitee, Mapping) else None,
        "invitee_email_sha256": (
            hashlib.sha256(email.encode()).hexdigest() if isinstance(email, str) and email else None
        ),
        "role_name": raw.get("role_name"),
        "permissions": raw.get("permissions"),
        "created_at": raw.get("created_at"),
        "expired": raw.get("expired"),
    }


def _repository_access_census(
    client: GhClient,
    identity: RepositoryIdentityV1,
    coordinate: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    owner = metadata.get("owner") or {}
    owner_login = owner.get("login") if isinstance(owner, Mapping) else None
    owner_id = owner.get("id") if isinstance(owner, Mapping) else None
    if not isinstance(owner_login, str) or not owner_login or not isinstance(owner_id, int):
        raise TransferCaptureError("repository metadata omitted its owner identity")

    raw_collaborators = client.list(f"/repos/{coordinate}/collaborators?affiliation=direct&per_page=100")
    raw_teams = client.list(f"/repos/{coordinate}/teams?per_page=100")
    raw_invitations = client.list(f"/repos/{coordinate}/invitations?per_page=100")
    if any(not isinstance(row, Mapping) for row in (*raw_collaborators, *raw_teams, *raw_invitations)):
        raise TransferCaptureError("repository access census contains a non-object row")

    collaborators = [_collaborator_access_record(row) for row in raw_collaborators]
    direct_grants = [
        row
        for row in collaborators
        if not (
            row.get("id") == owner_id
            and isinstance(row.get("login"), str)
            and row["login"].casefold() == owner_login.casefold()
        )
    ]
    teams = [_team_access_record(row) for row in raw_teams]
    invitations = [_invitation_access_record(row) for row in raw_invitations]

    def exact_sorted(rows: list[dict[str, Any]], identity_key: str, label: str) -> list[dict[str, Any]]:
        identities = [row.get(identity_key) for row in rows]
        if any(value is None for value in identities) or len(identities) != len(set(identities)):
            raise TransferCaptureError(f"repository access census contains invalid or duplicate {label} identities")
        return sorted(rows, key=lambda row: (str(row.get(identity_key)).casefold(), str(row.get("id") or "")))

    direct_grants = exact_sorted(direct_grants, "login", "collaborator")
    teams = exact_sorted(teams, "id", "team")
    invitations = exact_sorted(invitations, "id", "invitation")
    unexpected_count = len(direct_grants) + len(teams) + len(invitations)
    census = {
        "schema_version": "limen.repository_access_census.v1",
        "policy": {
            "source": "institutio/github/access.yaml",
            "mode": "never_grant",
            "canonical_coordinate": identity.canonical_coordinate,
            "satisfied": unexpected_count == 0,
        },
        "repository_owner": {"id": owner_id, "login": owner_login},
        "direct_grants": direct_grants,
        "team_grants": teams,
        "pending_invitations": invitations,
        "denominators": {
            "direct_grants": len(direct_grants),
            "team_grants": len(teams),
            "pending_invitations": len(invitations),
            "unexpected_access": unexpected_count,
        },
    }
    if unexpected_count:
        raise TransferCaptureError(
            f"repository violates never-grant access policy with {unexpected_count} unexpected access record(s)"
        )
    return census


def _required_connection(result: dict[str, Any], key: str, label: str) -> dict[str, Any]:
    if not result.get("available"):
        raise TransferCaptureError(f"{label} census is unavailable")
    payload = result.get("value")
    if not isinstance(payload, dict) or not isinstance(payload.get(key), list):
        raise TransferCaptureError(f"{label} census is malformed")
    total_count = payload.get("total_count")
    if not isinstance(total_count, int) or total_count != len(payload[key]):
        raise TransferCaptureError(f"{label} census denominator is incomplete")
    return payload


def _required_ruleset_census(client: GhClient, coordinate: str) -> dict[str, Any]:
    result = client.optional_list(f"/repos/{coordinate}/rulesets?per_page=100")
    if not result.get("available"):
        raise TransferCaptureError("repository rulesets census is unavailable")
    summaries = result.get("value")
    if not isinstance(summaries, list):
        raise TransferCaptureError("repository rulesets census is malformed")

    ruleset_ids: list[int] = []
    for summary in summaries:
        if not isinstance(summary, Mapping):
            raise TransferCaptureError("repository rulesets census contains a non-object row")
        ruleset_id = summary.get("id")
        if not isinstance(ruleset_id, int) or ruleset_id <= 0:
            raise TransferCaptureError("repository rulesets census contains an invalid identity")
        ruleset_ids.append(ruleset_id)
    if len(ruleset_ids) != len(set(ruleset_ids)):
        raise TransferCaptureError("repository rulesets census contains duplicate identities")

    rulesets: list[dict[str, Any]] = []
    for ruleset_id in sorted(ruleset_ids):
        detail = client.optional_object(f"/repos/{coordinate}/rulesets/{ruleset_id}")
        if not detail.get("available"):
            raise TransferCaptureError(f"repository ruleset {ruleset_id} detail census is unavailable")
        payload = detail.get("value")
        if not isinstance(payload, Mapping) or payload.get("id") != ruleset_id:
            raise TransferCaptureError(f"repository ruleset {ruleset_id} detail census is malformed")
        rulesets.append({"available": True, "value": _without_github_links(dict(payload))})
    return {"available": True, "value": rulesets}


def _names_only(result: dict[str, Any], key: str) -> dict[str, Any]:
    payload = _required_connection(result, key, key)
    values = payload[key]
    if any(not isinstance(value, Mapping) or not isinstance(value.get("name"), str) for value in values):
        raise TransferCaptureError(f"{key} census contains a nameless or non-object row")
    names = sorted(value["name"] for value in values)
    total_count = payload.get("total_count")
    if not isinstance(total_count, int) or total_count != len(names) or len(names) != len(set(names)):
        raise TransferCaptureError(f"{key} census denominator or identity is invalid")
    return {"available": True, "names": names, "total_count": total_count}


def _review_comments(client: GhClient, thread_id: str, first_page: Mapping[str, Any]) -> list[dict[str, Any]]:
    connection = dict(first_page)
    comments: list[dict[str, Any]] = []
    query = """
      query($thread: ID!, $after: String) {
        node(id: $thread) {
          ... on PullRequestReviewThread {
            comments(first: 100, after: $after) {
              nodes { id databaseId body author { login } createdAt updatedAt }
              pageInfo { hasNextPage endCursor }
            }
          }
        }
      }
    """
    while True:
        for raw in connection.get("nodes") or []:
            comments.append(
                {
                    "id": raw.get("id"),
                    "database_id": raw.get("databaseId"),
                    "author": (raw.get("author") or {}).get("login"),
                    "body_sha256": hashlib.sha256(str(raw.get("body") or "").encode()).hexdigest(),
                    "created_at": raw.get("createdAt"),
                    "updated_at": raw.get("updatedAt"),
                }
            )
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return comments
        cursor = page.get("endCursor")
        if not cursor:
            raise TransferCaptureError("review comment pagination omitted end cursor")
        data = client.graphql(query, {"thread": thread_id, "after": cursor})
        node = data.get("node") or {}
        connection = node.get("comments") or {}


def collect_review_threads(client: GhClient, owner: str, repo: str, number: int) -> list[dict[str, Any]]:
    query = """
      query($owner: String!, $repo: String!, $number: Int!, $after: String) {
        repository(owner: $owner, name: $repo) {
          pullRequest(number: $number) {
            reviewThreads(first: 100, after: $after) {
              nodes {
                id isResolved isOutdated path line startLine originalLine originalStartLine diffSide
                comments(first: 100) {
                  nodes { id databaseId body author { login } createdAt updatedAt }
                  pageInfo { hasNextPage endCursor }
                }
              }
              pageInfo { hasNextPage endCursor }
            }
          }
        }
      }
    """
    cursor: str | None = None
    threads: list[dict[str, Any]] = []
    while True:
        data = client.graphql(
            query,
            {"owner": owner, "repo": repo, "number": number, "after": cursor},
        )
        repository = data.get("repository") or {}
        pull_request = repository.get("pullRequest") or {}
        connection = pull_request.get("reviewThreads") or {}
        for raw in connection.get("nodes") or []:
            thread_id = str(raw.get("id") or "")
            if not thread_id:
                raise TransferCaptureError(f"PR #{number} review thread omitted node ID")
            threads.append(
                {
                    "id": thread_id,
                    "is_resolved": bool(raw.get("isResolved")),
                    "is_outdated": bool(raw.get("isOutdated")),
                    "path": raw.get("path"),
                    "line": raw.get("line"),
                    "start_line": raw.get("startLine"),
                    "original_line": raw.get("originalLine"),
                    "original_start_line": raw.get("originalStartLine"),
                    "diff_side": raw.get("diffSide"),
                    "comments": _review_comments(client, thread_id, raw.get("comments") or {}),
                }
            )
        page = connection.get("pageInfo") or {}
        if not page.get("hasNextPage"):
            return sorted(threads, key=lambda item: item["id"])
        cursor = page.get("endCursor")
        if not cursor:
            raise TransferCaptureError(f"PR #{number} review pagination omitted end cursor")


def _issue_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    issue_type = raw.get("type")
    return {
        "number": raw.get("number"),
        "id": raw.get("id"),
        "node_id": raw.get("node_id"),
        "state": raw.get("state"),
        "state_reason": raw.get("state_reason"),
        "issue_type": (_select(issue_type, ("id", "node_id", "name")) if isinstance(issue_type, dict) else issue_type),
        "assignees": sorted(
            str(value.get("login"))
            for value in raw.get("assignees") or []
            if isinstance(value, dict) and value.get("login")
        ),
        "labels": sorted(
            str(value.get("name")) for value in raw.get("labels") or [] if isinstance(value, dict) and value.get("name")
        ),
    }


def _release_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "node_id": raw.get("node_id"),
        "tag_name": raw.get("tag_name"),
        "target_commitish": raw.get("target_commitish"),
        "name": raw.get("name"),
        "draft": raw.get("draft"),
        "prerelease": raw.get("prerelease"),
        "created_at": raw.get("created_at"),
        "published_at": raw.get("published_at"),
        "body_sha256": hashlib.sha256(str(raw.get("body") or "").encode()).hexdigest(),
        "assets": sorted(
            (
                {
                    "id": asset.get("id"),
                    "name": asset.get("name"),
                    "size": asset.get("size"),
                    "digest": asset.get("digest"),
                }
                for asset in raw.get("assets") or []
                if isinstance(asset, dict)
            ),
            key=lambda asset: (str(asset.get("name")), int(asset.get("id") or 0)),
        ),
    }


def _ref_record(raw: Mapping[str, Any]) -> dict[str, Any]:
    obj = raw.get("object") or {}
    return {"ref": raw.get("ref"), "object_type": obj.get("type"), "tip": obj.get("sha")}


def _protected_checkout(path: Path) -> dict[str, Any]:
    def git(*args: str) -> bytes:
        result = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise TransferCaptureError(f"protected checkout inspection failed for {path.name}")
        return result.stdout

    status = git("status", "--porcelain=v2", "-z", "--untracked-files=all")
    unstaged = git("diff", "--binary", "--no-ext-diff")
    staged = git("diff", "--cached", "--binary", "--no-ext-diff")
    remotes = git("remote", "-v")
    untracked = git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0")
    untracked_records: list[dict[str, Any]] = []
    for relative_raw in sorted(value for value in untracked if value):
        relative = os.fsdecode(relative_raw)
        target = path / relative
        metadata = target.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            content_digest = hashlib.sha256(os.readlink(target).encode()).hexdigest()
        elif stat.S_ISREG(metadata.st_mode):
            content_digest = file_sha256(target)
        else:
            content_digest = hashlib.sha256(f"special:{metadata.st_mode}".encode()).hexdigest()
        untracked_records.append({"path": relative, "mode": stat.S_IMODE(metadata.st_mode), "sha256": content_digest})
    state = {
        "status_sha256": hashlib.sha256(status).hexdigest(),
        "unstaged_diff_sha256": hashlib.sha256(unstaged).hexdigest(),
        "staged_diff_sha256": hashlib.sha256(staged).hexdigest(),
        "remotes_sha256": hashlib.sha256(remotes).hexdigest(),
        "untracked": untracked_records,
    }
    return {
        "head": git("rev-parse", "HEAD").decode().strip(),
        "branch": git("symbolic-ref", "--short", "-q", "HEAD").decode().strip() or None,
        "state_digest": canonical_sha256(state),
        "state": state,
    }


def protected_path_digest(path: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        return {"exists": False, "tree_sha256": canonical_sha256([]), "file_count": 0}
    for target in sorted(path.rglob("*"), key=lambda value: os.fsencode(str(value.relative_to(path)))):
        relative = str(target.relative_to(path))
        metadata = target.lstat()
        if stat.S_ISDIR(metadata.st_mode):
            kind = "directory"
            digest = None
        elif stat.S_ISLNK(metadata.st_mode):
            kind = "symlink"
            digest = hashlib.sha256(os.readlink(target).encode()).hexdigest()
        elif stat.S_ISREG(metadata.st_mode):
            kind = "file"
            digest = file_sha256(target)
        else:
            kind = "special"
            digest = hashlib.sha256(f"special:{metadata.st_mode}".encode()).hexdigest()
        records.append(
            {
                "path": relative,
                "kind": kind,
                "mode": stat.S_IMODE(metadata.st_mode),
                "size": metadata.st_size,
                "sha256": digest,
            }
        )
    return {"exists": True, "tree_sha256": canonical_sha256(records), "file_count": len(records)}


def _installation_records(client: GhClient, repository_id: int) -> dict[str, Any]:
    installations = client.optional_connection("/user/installations?per_page=100", "installations")
    if not installations.get("available"):
        return installations
    matches: list[dict[str, Any]] = []
    for installation in (installations.get("value") or {}).get("installations") or []:
        if not isinstance(installation, dict) or not installation.get("id"):
            continue
        repos = client.optional_connection(
            f"/user/installations/{installation['id']}/repositories?per_page=100",
            "repositories",
        )
        if not repos.get("available"):
            matches.append(
                {
                    "installation_id": installation.get("id"),
                    "app_slug": installation.get("app_slug"),
                    "repository_membership_available": False,
                    "error_digest": repos.get("error_digest"),
                }
            )
            continue
        repositories = (repos.get("value") or {}).get("repositories") or []
        if any(isinstance(value, dict) and value.get("id") == repository_id for value in repositories):
            account = installation.get("account") or {}
            matches.append(
                {
                    "installation_id": installation.get("id"),
                    "app_id": installation.get("app_id"),
                    "app_slug": installation.get("app_slug"),
                    "target_type": installation.get("target_type"),
                    "account_id": account.get("id"),
                    "account_login": account.get("login"),
                    "repository_membership_available": True,
                }
            )
    return {"available": True, "installations": sorted(matches, key=lambda item: int(item["installation_id"]))}


def capture_github_manifest(
    client: GhClient,
    identity: RepositoryIdentityV1,
    coordinate: str,
) -> dict[str, Any]:
    owner, repo = coordinate.split("/", 1)
    metadata = client.object(f"/repos/{coordinate}")
    if metadata.get("id") != identity.repository_id:
        raise TransferCaptureError("repository numeric ID does not match RepositoryIdentityV1")
    observed_coordinate = str(metadata.get("full_name") or "")
    if not identity.accepts(observed_coordinate):
        raise TransferCaptureError("repository coordinate is not a registered identity alias")
    default_branch = str(metadata.get("default_branch") or "")
    default_sha = client.object(f"/repos/{coordinate}/commits/{default_branch}").get("sha")
    if not default_sha:
        raise TransferCaptureError("default branch tip could not be resolved")

    branches_raw = client.list(f"/repos/{coordinate}/git/matching-refs/heads/")
    tags_raw = client.list(f"/repos/{coordinate}/git/matching-refs/tags/")
    branches = sorted((_ref_record(value) for value in branches_raw), key=lambda item: str(item["ref"]))
    tags = sorted((_ref_record(value) for value in tags_raw), key=lambda item: str(item["ref"]))

    pulls_raw = client.list(f"/repos/{coordinate}/pulls?state=open&per_page=100")
    pulls: list[dict[str, Any]] = []
    for raw in sorted(pulls_raw, key=lambda item: int(item["number"])):
        number = int(raw["number"])
        head = raw.get("head") or {}
        head_repo = head.get("repo") or {}
        pulls.append(
            {
                "number": number,
                "id": raw.get("id"),
                "node_id": raw.get("node_id"),
                "head_sha": head.get("sha"),
                "head_ref": head.get("ref"),
                "head_repository": head_repo.get("full_name"),
                "base_sha": (raw.get("base") or {}).get("sha"),
                "review_threads": collect_review_threads(client, owner, repo, number),
            }
        )

    all_issues_raw = client.list(f"/repos/{coordinate}/issues?state=all&per_page=100")
    issues = sorted(
        (_issue_record(value) for value in all_issues_raw if not value.get("pull_request")),
        key=lambda item: int(item["number"]),
    )
    issue_types = client.optional_list(f"/orgs/{owner}/issue-types?per_page=100")

    branch_rows = client.list(f"/repos/{coordinate}/branches?per_page=100")
    branch_protection = _required_branch_protection_census(client, coordinate, branch_rows)

    workflows = client.connection(f"/repos/{coordinate}/actions/workflows?per_page=100", "workflows")
    workflow_states = sorted(
        (
            {
                "id": value.get("id"),
                "node_id": value.get("node_id"),
                "name": value.get("name"),
                "path": value.get("path"),
                "state": value.get("state"),
            }
            for value in workflows.get("workflows") or []
        ),
        key=lambda value: (str(value.get("path")), int(value.get("id") or 0)),
    )

    environments_result = client.optional_connection(
        f"/repos/{coordinate}/environments?per_page=100",
        "environments",
    )
    environment_payload = _required_connection(environments_result, "environments", "repository environments")
    environments: list[dict[str, Any]] = []
    for environment in environment_payload["environments"]:
        if not isinstance(environment, Mapping) or not isinstance(environment.get("name"), str):
            raise TransferCaptureError("repository environments census contains a nameless or non-object row")
        name = str(environment.get("name"))
        environments.append(
            {
                "name": name,
                "id": environment.get("id"),
                "node_id": environment.get("node_id"),
                "protection_rules": environment.get("protection_rules"),
                "deployment_branch_policy": environment.get("deployment_branch_policy"),
                "secret_names": _names_only(
                    client.optional_connection(
                        f"/repos/{coordinate}/environments/{name}/secrets?per_page=100",
                        "secrets",
                    ),
                    "secrets",
                ),
                "variable_names": _names_only(
                    client.optional_connection(
                        f"/repos/{coordinate}/environments/{name}/variables?per_page=100",
                        "variables",
                    ),
                    "variables",
                ),
            }
        )

    labels = sorted(
        (
            _select(value, ("id", "node_id", "name", "color", "description", "default"))
            for value in client.list(f"/repos/{coordinate}/labels?per_page=100")
        ),
        key=lambda item: str(item.get("name")),
    )
    releases = sorted(
        (_release_record(value) for value in client.list(f"/repos/{coordinate}/releases?per_page=100")),
        key=lambda item: int(item.get("id") or 0),
    )
    webhooks = _required_webhook_census(client, coordinate)
    deploy_keys = _required_deploy_key_census(client, coordinate)
    actions_settings = _required_actions_settings(client, coordinate)
    rulesets = _required_ruleset_census(client, coordinate)
    access = _repository_access_census(client, identity, coordinate, metadata)

    return {
        "identity": identity.model_dump(mode="json"),
        "observed_coordinate": observed_coordinate,
        "repository_settings": _select(metadata, _REPOSITORY_SETTING_KEYS),
        "default_sha": default_sha,
        "refs": {"branches": branches, "tags": tags},
        "releases": releases,
        "open_pull_requests": pulls,
        "issues": {
            "count": len(issues),
            "numbers": [value["number"] for value in issues],
            "records": issues,
            "types": issue_types,
        },
        "labels": labels,
        "rulesets": rulesets,
        "branch_protection": branch_protection,
        "actions": {
            "workflow_states": workflow_states,
            **actions_settings,
            "secret_names": _names_only(
                client.optional_connection(
                    f"/repos/{coordinate}/actions/secrets?per_page=100",
                    "secrets",
                ),
                "secrets",
            ),
            "variable_names": _names_only(
                client.optional_connection(
                    f"/repos/{coordinate}/actions/variables?per_page=100",
                    "variables",
                ),
                "variables",
            ),
        },
        "environments": sorted(environments, key=lambda value: value["name"]),
        "apps": _installation_records(client, identity.repository_id),
        "access": access,
        "webhooks": webhooks,
        "deploy_keys": deploy_keys,
    }


def capture_protected_state(
    checkouts: Mapping[str, Path],
    paths: Mapping[str, Path],
) -> dict[str, Any]:
    process_result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if process_result.returncode != 0:
        raise TransferCaptureError("process snapshot failed")
    agent_tokens = {
        "agy": ("antigravity", " agy "),
        "opencode": ("opencode",),
    }
    lane_names = sorted(set(checkouts) | set(paths), key=str.casefold)
    folded_names = [name.casefold() for name in lane_names]
    if len(folded_names) != len(set(folded_names)):
        raise TransferCaptureError("protected lane names collide case-insensitively")
    lane_needles = {
        name: tuple(
            str(path)
            for path in (
                *((checkouts[name],) if name in checkouts else ()),
                *((paths[name],) if name in paths else ()),
            )
        )
        for name in lane_names
    }
    process_rows: list[dict[str, Any]] = []
    ignored_pids = {os.getpid(), os.getppid()}
    for line in process_result.stdout.splitlines():
        parts = line.strip().split(maxsplit=2)
        if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
            continue
        pid, parent, command = int(parts[0]), int(parts[1]), parts[2]
        if pid in ignored_pids or parent == os.getpid():
            continue
        process_rows.append({"pid": pid, "ppid": parent, "command": command})

    protected_processes: dict[str, dict[str, Any]] = {}
    for name in lane_names:
        needles = lane_needles[name]
        tokens = agent_tokens.get(name.casefold(), ())
        matching_processes = [
            row
            for row in process_rows
            if any(needle in row["command"] for needle in needles)
            or any(token in row["command"].casefold() for token in tokens)
        ]
        matching_processes.sort(key=lambda value: (value["pid"], value["command"]))
        protected_processes[name] = {
            "snapshot_sha256": canonical_sha256(matching_processes),
            "count": len(matching_processes),
            "processes": matching_processes,
        }
    return {
        "checkouts": {name: _protected_checkout(path) for name, path in sorted(checkouts.items())},
        "paths": {name: protected_path_digest(path) for name, path in sorted(paths.items())},
        "processes": protected_processes,
    }


def create_verified_bundle(
    coordinate: str,
    bundle_path: Path,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{bundle_path.name}.",
        dir=bundle_path.parent,
    ) as raw_candidate_parent:
        candidate = Path(raw_candidate_parent) / "replacement.bundle"
        with tempfile.TemporaryDirectory(prefix="limen-transfer-bundle-") as raw_temp:
            temp = Path(raw_temp)
            mirror = temp / "source.git"
            restore = temp / "restore.git"

            commands = (
                ["git", "clone", "--mirror", f"https://github.com/{coordinate}.git", str(mirror)],
                ["git", "-C", str(mirror), "fetch", "origin", "+refs/pull/*/head:refs/pull/*/head"],
                ["git", "-C", str(mirror), "bundle", "create", str(candidate), "--all"],
                ["git", "-C", str(mirror), "bundle", "verify", str(candidate)],
                ["git", "clone", "--mirror", str(candidate), str(restore)],
            )
            for command in commands:
                result = runner(command, capture_output=True, text=True, check=False)
                if result.returncode != 0:
                    raise TransferCaptureError(f"Git bundle command failed: {command[1]}")

            def refs(root: Path) -> list[str]:
                result = runner(
                    ["git", "-C", str(root), "for-each-ref", "--format=%(refname) %(objectname)"],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                if result.returncode != 0:
                    raise TransferCaptureError("Git bundle ref enumeration failed")
                return sorted(line for line in result.stdout.splitlines() if line)

            source_refs = refs(mirror)
            restored_refs = refs(restore)
            if source_refs != restored_refs:
                raise TransferCaptureError("restored Git bundle refs differ from source mirror")

        receipt = {
            "sha256": file_sha256(candidate),
            "size_bytes": candidate.stat().st_size,
            "ref_count": len(source_refs),
            "refs_sha256": canonical_sha256(source_refs),
            "restore_verified": True,
            "_refs": source_refs,
        }
        try:
            os.replace(candidate, bundle_path)
        except OSError as exc:
            raise TransferCaptureError("verified Git bundle replacement failed") from exc
        return receipt


def verify_existing_bundle(
    bundle_path: Path,
    *,
    runner: Runner = subprocess.run,
) -> dict[str, Any]:
    verify = runner(
        ["git", "bundle", "verify", str(bundle_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode != 0:
        raise TransferCaptureError("existing Git bundle verification failed")
    heads = runner(
        ["git", "bundle", "list-heads", str(bundle_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if heads.returncode != 0:
        raise TransferCaptureError("existing Git bundle head enumeration failed")
    refs: list[str] = []
    for line in heads.stdout.splitlines():
        fields = line.split(maxsplit=1)
        if len(fields) == 2 and fields[1].startswith("refs/"):
            refs.append(f"{fields[1]} {fields[0]}")
    refs.sort()
    with tempfile.TemporaryDirectory(prefix="limen-transfer-bundle-restore-") as raw_temp:
        restore = Path(raw_temp) / "restore.git"
        clone = runner(
            ["git", "clone", "--mirror", str(bundle_path), str(restore)],
            capture_output=True,
            text=True,
            check=False,
        )
        if clone.returncode != 0:
            raise TransferCaptureError("existing Git bundle restore clone failed")
        restored = runner(
            ["git", "-C", str(restore), "for-each-ref", "--format=%(refname) %(objectname)"],
            capture_output=True,
            text=True,
            check=False,
        )
        if restored.returncode != 0:
            raise TransferCaptureError("existing Git bundle restored ref enumeration failed")
        restored_refs = sorted(line for line in restored.stdout.splitlines() if line)
        if restored_refs != refs:
            raise TransferCaptureError("existing Git bundle restored refs differ from bundle heads")
    return {
        "sha256": file_sha256(bundle_path),
        "size_bytes": bundle_path.stat().st_size,
        "ref_count": len(refs),
        "refs_sha256": canonical_sha256(refs),
        "restore_verified": True,
        "_refs": refs,
    }


def bind_bundle_to_github_manifest(
    github: Mapping[str, Any],
    bundle: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Require the restored bundle to contain every captured branch, tag, and open-PR tip."""

    if bundle is None:
        return None
    raw_refs = bundle.get("_refs")
    if not isinstance(raw_refs, list) or any(not isinstance(value, str) for value in raw_refs):
        raise TransferCaptureError("verified Git bundle omitted its private ref binding census")
    bundle_refs: dict[str, str] = {}
    for value in raw_refs:
        fields = value.split(maxsplit=1)
        if len(fields) != 2 or not fields[0].startswith("refs/"):
            raise TransferCaptureError("verified Git bundle contains a malformed ref binding")
        ref, tip = fields
        if ref in bundle_refs or not re.fullmatch(r"[0-9a-f]{40}", tip):
            raise TransferCaptureError("verified Git bundle contains duplicate or invalid ref bindings")
        bundle_refs[ref] = tip

    expected: dict[str, str] = {}
    for section in ("branches", "tags"):
        for row in (github.get("refs") or {}).get(section) or []:
            if isinstance(row, Mapping) and isinstance(row.get("ref"), str) and isinstance(row.get("tip"), str):
                expected[row["ref"]] = row["tip"]
    for pull_request in github.get("open_pull_requests") or []:
        if isinstance(pull_request, Mapping):
            number = pull_request.get("number")
            head_sha = pull_request.get("head_sha")
            if isinstance(number, int) and isinstance(head_sha, str):
                expected[f"refs/pull/{number}/head"] = head_sha
    default_branch = str((github.get("repository_settings") or {}).get("default_branch") or "")
    if expected.get(f"refs/heads/{default_branch}") != github.get("default_sha"):
        raise TransferCaptureError("GitHub default SHA differs from its captured branch ref")
    mismatches = sorted(ref for ref, tip in expected.items() if bundle_refs.get(ref) != tip)
    if mismatches:
        raise TransferCaptureError("verified Git bundle differs from captured GitHub refs")
    return {key: value for key, value in bundle.items() if key != "_refs"}


def invariant_projection(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return the owner-transfer-stable portion used for pre/post comparison."""

    identity = RepositoryIdentityV1.model_validate(manifest["identity"])
    github = dict(manifest["github"])
    github.pop("observed_coordinate", None)
    github.pop("apps", None)
    access = github.get("access")
    if isinstance(access, dict):
        access = dict(access)
        access.pop("repository_owner", None)
        github["access"] = access
    settings = dict(github["repository_settings"])
    settings.pop("full_name", None)
    settings.pop("name", None)
    github["repository_settings"] = settings

    def normalize(value: Any) -> Any:
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        if isinstance(value, str) and identity.accepts(value):
            return f"github-repository:{identity.repository_id}"
        return value

    protected = manifest["protected_state"]
    protected_stable = {
        "checkouts": {
            name: {
                "branch": row.get("branch"),
                "remotes_sha256": (row.get("state") or {}).get("remotes_sha256"),
            }
            for name, row in (protected.get("checkouts") or {}).items()
        },
        "paths": {name: {"exists": row.get("exists")} for name, row in (protected.get("paths") or {}).items()},
    }
    return {
        "identity": manifest["identity"],
        "github": normalize(github),
        "protected_state": protected_stable,
        "git_bundle": manifest.get("git_bundle"),
    }


_TRANSFER_TYPE_LABEL_PREFIX = "transfer-type/"
_DISABLED_DISMISSAL_RESTRICTION = {"enabled": False, "allowed_actors": []}
_SELECTED_ACTIONS_NOT_APPLICABLE = {
    "available": True,
    "applicable": False,
    "reason": "allowed_actions_policy_is_not_selected",
    "value": None,
}


def transfer_type_label(type_name: str) -> str:
    """Return the deterministic compensation label for a native issue type."""

    normalized = re.sub(r"[^a-z0-9]+", "-", type_name.strip().casefold()).strip("-")
    if not normalized:
        raise ValueError("issue type name does not contain a label-safe atom")
    return f"{_TRANSFER_TYPE_LABEL_PREFIX}{normalized}"


def _native_issue_type_semantics(value: Any) -> str | None:
    if not isinstance(value, Mapping) or not isinstance(value.get("name"), str):
        return None
    try:
        return transfer_type_label(value["name"])
    except ValueError:
        return None


def _native_type_catalog(value: Any) -> list[str] | None:
    if not isinstance(value, Mapping) or value.get("available") is not True:
        return None
    rows = value.get("value")
    if not isinstance(rows, list):
        return None
    names = [_native_issue_type_semantics(row) for row in rows]
    if any(name is None for name in names) or len(set(names)) != len(names):
        return None
    return sorted(name for name in names if name is not None)


def _label_names(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    names: list[str] = []
    for row in value:
        if not isinstance(row, Mapping) or not isinstance(row.get("name"), str):
            return None
        names.append(row["name"])
    return names


def _remove_exact_labels(value: Any, names: set[str]) -> Any:
    if not isinstance(value, list):
        return value
    return [
        row
        for row in value
        if not (isinstance(row, Mapping) and isinstance(row.get("name"), str) and row["name"] in names)
    ]


def _normalize_pull_request_restrictions(value: Any) -> Any:
    if isinstance(value, list):
        return [_normalize_pull_request_restrictions(item) for item in value]
    if not isinstance(value, dict):
        return value
    normalized = {key: _normalize_pull_request_restrictions(item) for key, item in value.items()}
    if normalized.get("type") != "pull_request":
        return normalized
    if normalized.get("dismissal_restriction") == _DISABLED_DISMISSAL_RESTRICTION:
        normalized.pop("dismissal_restriction")
    parameters = normalized.get("parameters")
    if isinstance(parameters, dict) and parameters.get("dismissal_restriction") == _DISABLED_DISMISSAL_RESTRICTION:
        parameters.pop("dismissal_restriction")
    return normalized


def _normalize_inapplicable_selected_actions(github: dict[str, Any]) -> None:
    actions = github.get("actions")
    if not isinstance(actions, dict):
        return
    permissions = actions.get("permissions")
    if not isinstance(permissions, Mapping) or permissions.get("available") is not True:
        return
    policy = permissions.get("value")
    if not isinstance(policy, Mapping) or policy.get("allowed_actions") not in {"all", "local_only"}:
        return
    actions["selected_actions"] = dict(_SELECTED_ACTIONS_NOT_APPLICABLE)


def _normalize_post_transfer_projection_pair(expected: dict[str, Any], observed: dict[str, Any]) -> None:
    expected_github = expected.get("github")
    observed_github = observed.get("github")
    if not isinstance(expected_github, dict) or not isinstance(observed_github, dict):
        return

    before_settings = expected_github.get("repository_settings")
    after_settings = observed_github.get("repository_settings")
    if (
        isinstance(before_settings, dict)
        and isinstance(after_settings, dict)
        and before_settings.get("custom_properties") == {}
        and after_settings.get("custom_properties") is None
    ):
        after_settings["custom_properties"] = {}

    expected_github["rulesets"] = _normalize_pull_request_restrictions(expected_github.get("rulesets"))
    observed_github["rulesets"] = _normalize_pull_request_restrictions(observed_github.get("rulesets"))
    _normalize_inapplicable_selected_actions(expected_github)
    _normalize_inapplicable_selected_actions(observed_github)

    before_issues = expected_github.get("issues")
    after_issues = observed_github.get("issues")
    if not isinstance(before_issues, dict) or not isinstance(after_issues, dict):
        return

    compensation_labels: set[str] = set()
    before_catalog = _native_type_catalog(before_issues.get("types"))
    after_catalog = _native_type_catalog(after_issues.get("types"))
    if before_catalog is not None:
        if after_catalog is not None and (after_catalog or not before_catalog):
            before_issues["types"] = {"semantic_types": before_catalog}
            after_issues["types"] = {"semantic_types": after_catalog}
        else:
            after_label_names = _label_names(observed_github.get("labels"))
            if after_label_names is not None and all(after_label_names.count(name) == 1 for name in before_catalog):
                compensation_labels.update(before_catalog)
                semantic_types = {"semantic_types": before_catalog}
                before_issues["types"] = semantic_types
                after_issues["types"] = dict(semantic_types)

    before_records = before_issues.get("records")
    after_records = after_issues.get("records")
    if isinstance(before_records, list) and isinstance(after_records, list):
        after_by_number = {
            row.get("number"): row
            for row in after_records
            if isinstance(row, dict) and isinstance(row.get("number"), int)
        }
        for before_row in before_records:
            if not isinstance(before_row, dict):
                continue
            after_row = after_by_number.get(before_row.get("number"))
            if not isinstance(after_row, dict):
                continue
            before_type = _native_issue_type_semantics(before_row.get("issue_type"))
            after_type = _native_issue_type_semantics(after_row.get("issue_type"))
            if before_type is None:
                continue
            before_row["issue_type"] = {"semantic_type": before_type}
            if after_type is not None:
                after_row["issue_type"] = {"semantic_type": after_type}
                continue
            after_labels = after_row.get("labels")
            if (
                after_row.get("issue_type") is None
                and isinstance(after_labels, list)
                and after_labels.count(before_type) == 1
            ):
                after_row["issue_type"] = {"semantic_type": before_type}
                compensation_labels.add(before_type)
                before_labels = before_row.get("labels")
                if isinstance(before_labels, list):
                    before_row["labels"] = [name for name in before_labels if name != before_type]
                after_row["labels"] = [name for name in after_labels if name != before_type]

    if compensation_labels:
        expected_github["labels"] = _remove_exact_labels(expected_github.get("labels"), compensation_labels)
        observed_github["labels"] = _remove_exact_labels(observed_github.get("labels"), compensation_labels)


def protected_state_deltas(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
) -> dict[str, dict[str, str]]:
    """Digest volatile/self-owned protected state without publishing its contents."""

    left = before.get("protected_state") or {}
    right = after.get("protected_state") or {}
    deltas: dict[str, dict[str, str]] = {}
    for section in ("checkouts", "paths", "processes"):
        left_rows = left.get(section) or {}
        right_rows = right.get(section) or {}
        for name in sorted(set(left_rows) | set(right_rows)):
            before_digest = canonical_sha256(left_rows.get(name))
            after_digest = canonical_sha256(right_rows.get(name))
            if before_digest != after_digest:
                deltas[f"{section}/{name}"] = {
                    "before_sha256": before_digest,
                    "after_sha256": after_digest,
                }
    return deltas


def _attribution_failures(
    deltas: Mapping[str, Mapping[str, str]],
    attribution: Mapping[str, Any] | None,
    *,
    before_manifest_sha256: str,
    after_manifest_sha256: str,
) -> list[str]:
    if not deltas:
        return []
    if attribution is None:
        return ["protected self-owned state changed without a private attribution receipt"]
    if attribution.get("schema_version") != "limen.protected_state_attribution.v1":
        return ["protected state attribution schema is invalid"]
    if (
        attribution.get("before_manifest_sha256") != before_manifest_sha256
        or attribution.get("after_manifest_sha256") != after_manifest_sha256
    ):
        return ["protected state attribution is not bound to the exact manifest pair"]
    rows = attribution.get("changes")
    if not isinstance(rows, Mapping) or set(rows) != set(deltas):
        return ["protected state attribution does not cover the exact delta denominator"]
    for name, expected in deltas.items():
        row = rows.get(name)
        if not isinstance(row, Mapping):
            return [f"protected state attribution is malformed: {name}"]
        actor = row.get("actor")
        proof = row.get("evidence")
        evidence = row.get("evidence_sha256")
        section, separator, expected_actor = name.partition("/")
        expected_cause = "protected_lane_process_churn" if section == "processes" else "protected_lane_self_write"
        if (
            row.get("before_sha256") != expected["before_sha256"]
            or row.get("after_sha256") != expected["after_sha256"]
            or not isinstance(actor, str)
            or not actor.strip()
            or not separator
            or actor != expected_actor
            or not isinstance(proof, Mapping)
            or evidence != canonical_sha256(proof)
            or proof.get("schema_version") != "limen.protected_state_delta_evidence.v1"
            or proof.get("delta") != name
            or proof.get("actor") != actor
            or proof.get("before_sha256") != expected["before_sha256"]
            or proof.get("after_sha256") != expected["after_sha256"]
            or proof.get("transfer_actor_touched") is not False
            or proof.get("cause_class") != expected_cause
            or not isinstance(proof.get("observed_at"), str)
        ):
            return [f"protected state attribution does not bind the exact private delta: {name}"]
        try:
            observed_at = datetime.fromisoformat(proof["observed_at"].replace("Z", "+00:00"))
        except ValueError:
            return [f"protected state attribution timestamp is invalid: {name}"]
        if observed_at.tzinfo is None:
            return [f"protected state attribution timestamp lacks timezone: {name}"]
    return []


def compare_manifests(
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    *,
    protected_attribution: Mapping[str, Any] | None = None,
) -> list[str]:
    expected = invariant_projection(before)
    observed = invariant_projection(after)
    _normalize_post_transfer_projection_pair(expected, observed)
    failures: list[str] = []
    if expected != observed:
        for key in sorted(set(expected) | set(observed)):
            if canonical_sha256(expected.get(key)) != canonical_sha256(observed.get(key)):
                failures.append(f"transfer invariant changed: {key}")
    failures.extend(
        _attribution_failures(
            protected_state_deltas(before, after),
            protected_attribution,
            before_manifest_sha256=canonical_sha256(before),
            after_manifest_sha256=canonical_sha256(after),
        )
    )
    return failures


def build_manifest(
    *,
    client: GhClient,
    identity: RepositoryIdentityV1,
    coordinate: str,
    checkouts: Mapping[str, Path],
    protected_paths: Mapping[str, Path],
    bundle: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if bundle is None:
        raise TransferCaptureError("transfer manifest requires a complete verified Git bundle")
    github = capture_github_manifest(client, identity, coordinate)
    protected_state = capture_protected_state(checkouts, protected_paths)
    bound_bundle = bind_bundle_to_github_manifest(github, bundle)
    return {
        "schema_version": "limen.repository_transfer_manifest.v3",
        "captured_at": datetime.now(UTC).isoformat(),
        "identity": identity.model_dump(mode="json"),
        "github": github,
        "protected_state": protected_state,
        "git_bundle": bound_bundle,
    }


def public_receipt(manifest: Mapping[str, Any], manifest_sha256: str) -> dict[str, Any]:
    github = manifest["github"]
    threads = [thread for pull_request in github["open_pull_requests"] for thread in pull_request["review_threads"]]
    workflow_states = github["actions"]["workflow_states"]
    disabled_workflows = sum(value.get("state") == "disabled_manually" for value in workflow_states)
    apps = github.get("apps") or {}
    return {
        "schema_version": "limen.repository_transfer_capture_receipt.v3",
        "receipt_role": "pre_transfer_preflight_snapshot",
        "final_private_recapture_required_after_ref_or_review_change": True,
        "captured_at": manifest["captured_at"],
        "repository_identity": manifest["identity"],
        "preferred_destination": manifest["identity"]["canonical_coordinate"],
        "fallback_destination": LIMEN_TRANSFER_FALLBACK_COORDINATE,
        "observed_coordinate": github["observed_coordinate"],
        "default_sha": github["default_sha"],
        "manifest_sha256": manifest_sha256,
        "git_bundle": manifest.get("git_bundle"),
        "denominators": {
            "branches": len(github["refs"]["branches"]),
            "tags": len(github["refs"]["tags"]),
            "releases": len(github["releases"]),
            "issues": github["issues"]["count"],
            "open_pull_requests": len(github["open_pull_requests"]),
            "review_threads": len(threads),
            "unresolved_current_review_threads": sum(
                not value["is_resolved"] and not value["is_outdated"] for value in threads
            ),
            "unresolved_outdated_review_threads": sum(
                not value["is_resolved"] and value["is_outdated"] for value in threads
            ),
            "workflows": len(github["actions"]["workflow_states"]),
            "environments": len(github["environments"]),
            "direct_access_grants": github["access"]["denominators"]["direct_grants"],
            "team_access_grants": github["access"]["denominators"]["team_grants"],
            "pending_access_invitations": github["access"]["denominators"]["pending_invitations"],
        },
        "workflow_freeze": {
            "disabled": disabled_workflows,
            "intentionally_active": len(workflow_states) - disabled_workflows,
            "policy": "institutio/github/workflow-transfer-policy.json",
        },
        "app_access_census": "available" if apps.get("available") else "unavailable_fail_closed",
        "private_custody_included": True,
        "private_paths_and_protected_lane_digests_published": False,
    }
