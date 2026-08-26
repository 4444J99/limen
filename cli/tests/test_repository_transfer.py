from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

import limen.repository_transfer as transfer
from limen.repository_identity import LIMEN_REPOSITORY_IDENTITY
from limen.repository_transfer import (
    GhClient,
    TransferCaptureError,
    bind_bundle_to_github_manifest,
    canonical_sha256,
    capture_protected_state,
    compare_manifests,
    file_sha256,
    invariant_projection,
    protected_state_deltas,
    public_receipt,
    transfer_type_label,
    verify_existing_bundle,
)


def test_gh_client_fails_closed_on_incomplete_pagination_shape() -> None:
    def runner(*_args, **_kwargs):
        return subprocess.CompletedProcess([], 0, json.dumps([{"not": "a page"}]), "")

    with pytest.raises(TransferCaptureError, match="expected list page"):
        GhClient(runner=runner).list("/repos/example/repo/issues")


@pytest.mark.parametrize(
    "result",
    [
        {"available": False, "error_class": "github_api_unavailable"},
        {"available": True, "value": {}},
        {"available": True, "value": {"total_count": 1, "environments": []}},
    ],
)
def test_required_environment_census_rejects_unavailable_or_incomplete_results(result: dict[str, Any]) -> None:
    with pytest.raises(TransferCaptureError, match="repository environments census"):
        transfer._required_connection(result, "environments", "repository environments")


def test_secret_and_variable_name_censuses_reject_unavailable_results() -> None:
    with pytest.raises(TransferCaptureError, match="secrets census is unavailable"):
        transfer._names_only({"available": False}, "secrets")
    with pytest.raises(TransferCaptureError, match="variables census is unavailable"):
        transfer._names_only({"available": False}, "variables")


def test_required_ruleset_census_rejects_unavailable_summary() -> None:
    class Client:
        def optional_list(self, _endpoint: str) -> dict[str, Any]:
            return {"available": False, "error_class": "github_api_unavailable"}

    with pytest.raises(TransferCaptureError, match="repository rulesets census is unavailable"):
        transfer._required_ruleset_census(Client(), "4444J99/limen")


def test_required_ruleset_census_rejects_unavailable_detail() -> None:
    class Client:
        def optional_list(self, _endpoint: str) -> dict[str, Any]:
            return {"available": True, "value": [{"id": 7}]}

        def optional_object(self, _endpoint: str) -> dict[str, Any]:
            return {"available": False, "error_class": "github_api_unavailable"}

    with pytest.raises(TransferCaptureError, match="ruleset 7 detail census is unavailable"):
        transfer._required_ruleset_census(Client(), "4444J99/limen")


def test_required_ruleset_census_reads_every_detail() -> None:
    class Client:
        def optional_list(self, _endpoint: str) -> dict[str, Any]:
            return {"available": True, "value": [{"id": 9}, {"id": 7}]}

        def optional_object(self, endpoint: str) -> dict[str, Any]:
            ruleset_id = int(endpoint.rsplit("/", 1)[-1])
            return {
                "available": True,
                "value": {"id": ruleset_id, "name": f"ruleset-{ruleset_id}", "_links": {"html": {}}},
            }

    census = transfer._required_ruleset_census(Client(), "4444J99/limen")

    assert [row["value"]["id"] for row in census["value"]] == [7, 9]
    assert all("_links" not in row["value"] for row in census["value"])


def test_protected_branch_census_fails_closed_when_details_are_unreadable() -> None:
    class Client:
        def optional_object(self, _endpoint: str) -> dict[str, Any]:
            return {"available": False, "error_class": "github_api_unavailable"}

    with pytest.raises(TransferCaptureError, match="protected branch main census is unavailable"):
        transfer._required_branch_protection_census(
            Client(),
            "4444J99/limen",
            [{"name": "main", "protected": True}],
        )


def test_protected_branch_census_reads_details_and_encodes_branch_identity() -> None:
    class Client:
        def __init__(self) -> None:
            self.endpoint = ""

        def optional_object(self, endpoint: str) -> dict[str, Any]:
            self.endpoint = endpoint
            return {
                "available": True,
                "value": {"required_pull_request_reviews": {"required_approving_review_count": 1}, "_links": {}},
            }

    client = Client()
    census = transfer._required_branch_protection_census(
        client,
        "4444J99/limen",
        [{"name": "release/next", "protected": True}],
    )

    assert client.endpoint.endswith("/branches/release%2Fnext/protection")
    assert census == {
        "release/next": {
            "available": True,
            "value": {"required_pull_request_reviews": {"required_approving_review_count": 1}},
        }
    }


@pytest.mark.parametrize(
    ("surface", "label"),
    [
        ("hooks", "repository webhooks"),
        ("keys", "repository deploy keys"),
    ],
)
def test_hook_and_deploy_key_censuses_fail_closed_when_unreadable(surface: str, label: str) -> None:
    class Client:
        def optional_list(self, endpoint: str) -> dict[str, Any]:
            assert f"/{surface}?" in endpoint
            return {"available": False, "error_class": "github_api_unavailable"}

    capture = transfer._required_webhook_census if surface == "hooks" else transfer._required_deploy_key_census
    with pytest.raises(TransferCaptureError, match=f"{label} census is unavailable"):
        capture(Client(), "4444J99/limen")


def _actions_settings_responses(*, allowed_actions: str = "all") -> dict[str, dict[str, Any]]:
    prefix = "/repos/4444J99/limen/actions/permissions"
    return {
        prefix: {
            "available": True,
            "value": {"enabled": True, "allowed_actions": allowed_actions, "sha_pinning_required": False},
        },
        f"{prefix}/workflow": {
            "available": True,
            "value": {"default_workflow_permissions": "read", "can_approve_pull_request_reviews": True},
        },
        f"{prefix}/selected-actions": {
            "available": True,
            "value": {
                "github_owned_allowed": True,
                "verified_allowed": False,
                "patterns_allowed": ["actions/*"],
            },
        },
        f"{prefix}/fork-pr-contributor-approval": {
            "available": True,
            "value": {"approval_policy": "first_time_contributors"},
        },
        f"{prefix}/artifact-and-log-retention": {
            "available": True,
            "value": {"days": 90, "maximum_allowed_days": 90},
        },
    }


def test_actions_census_derives_selected_actions_inapplicability_from_readable_policy() -> None:
    class Client:
        def __init__(self) -> None:
            self.responses = _actions_settings_responses()
            self.requested: list[str] = []

        def optional_object(self, endpoint: str) -> dict[str, Any]:
            self.requested.append(endpoint)
            return self.responses[endpoint]

    client = Client()
    settings = transfer._required_actions_settings(client, "4444J99/limen")

    assert settings["selected_actions"] == {
        "available": True,
        "applicable": False,
        "reason": "allowed_actions_policy_is_not_selected",
        "value": None,
    }
    assert all(not endpoint.endswith("/selected-actions") for endpoint in client.requested)


def test_actions_census_preserves_v3_readable_envelope_when_selected_actions_apply() -> None:
    class Client:
        def __init__(self) -> None:
            self.responses = _actions_settings_responses(allowed_actions="selected")

        def optional_object(self, endpoint: str) -> dict[str, Any]:
            return self.responses[endpoint]

    settings = transfer._required_actions_settings(Client(), "4444J99/limen")

    assert settings["selected_actions"] == {
        "available": True,
        "value": {
            "github_owned_allowed": True,
            "verified_allowed": False,
            "patterns_allowed": ["actions/*"],
        },
    }


@pytest.mark.parametrize(
    "suffix",
    ["", "/workflow", "/selected-actions", "/fork-pr-contributor-approval", "/artifact-and-log-retention"],
)
def test_actions_census_fails_closed_when_an_applicable_setting_is_unreadable(suffix: str) -> None:
    prefix = "/repos/4444J99/limen/actions/permissions"

    class Client:
        def __init__(self) -> None:
            self.responses = _actions_settings_responses(allowed_actions="selected")
            self.responses[f"{prefix}{suffix}"] = {
                "available": False,
                "error_class": "github_api_unavailable",
            }

        def optional_object(self, endpoint: str) -> dict[str, Any]:
            return self.responses[endpoint]

    with pytest.raises(TransferCaptureError, match="census is unavailable"):
        transfer._required_actions_settings(Client(), "4444J99/limen")


def test_repository_access_census_excludes_only_the_personal_owner() -> None:
    class Client:
        def list(self, endpoint: str) -> list[dict[str, Any]]:
            if "/collaborators?" in endpoint:
                return [
                    {
                        "id": 24_796_448,
                        "node_id": "OWNER",
                        "login": "4444J99",
                        "type": "User",
                        "role_name": "admin",
                        "permissions": {"admin": True, "push": True, "pull": True},
                    }
                ]
            return []

    census = transfer._repository_access_census(
        Client(),
        LIMEN_REPOSITORY_IDENTITY,
        "4444J99/limen",
        {"owner": {"id": 24_796_448, "login": "4444J99"}},
    )

    assert census["policy"]["satisfied"] is True
    assert census["direct_grants"] == []
    assert census["team_grants"] == []
    assert census["pending_invitations"] == []
    assert census["denominators"]["unexpected_access"] == 0


@pytest.mark.parametrize("surface", ["collaborator", "team", "invitation"])
def test_repository_access_census_fails_closed_on_every_grant_surface(surface: str) -> None:
    class Client:
        def list(self, endpoint: str) -> list[dict[str, Any]]:
            if surface == "collaborator" and "/collaborators?" in endpoint:
                return [
                    {
                        "id": 99,
                        "node_id": "USER_99",
                        "login": "unexpected-writer",
                        "type": "User",
                        "role_name": "write",
                        "permissions": {"push": True, "pull": True},
                    }
                ]
            if surface == "team" and "/teams?" in endpoint:
                return [
                    {
                        "id": 88,
                        "node_id": "TEAM_88",
                        "slug": "unexpected-team",
                        "permission": "push",
                        "permissions": {"push": True, "pull": True},
                        "organization": {"id": 1, "login": "organvm"},
                    }
                ]
            if surface == "invitation" and "/invitations?" in endpoint:
                return [
                    {
                        "id": 77,
                        "node_id": "INVITE_77",
                        "invitee": {"id": 66, "login": "pending-writer"},
                        "role_name": "write",
                        "permissions": "write",
                    }
                ]
            return []

    with pytest.raises(TransferCaptureError, match="never-grant access policy"):
        transfer._repository_access_census(
            Client(),
            LIMEN_REPOSITORY_IDENTITY,
            "4444J99/limen",
            {"owner": {"id": 24_796_448, "login": "4444J99"}},
        )


def test_transfer_comparison_ignores_only_coordinate_and_observation_time() -> None:
    manifest = {
        "captured_at": "before",
        "identity": LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json"),
        "github": {
            "observed_coordinate": "organvm/limen",
            "repository_settings": {
                "id": 1_255_213_941,
                "name": "limen",
                "full_name": "organvm/limen",
                "default_branch": "main",
            },
            "default_sha": "a" * 40,
            "refs": {"branches": [], "tags": []},
        },
        "protected_state": {"checkouts": {}, "paths": {}},
        "git_bundle": {"sha256": "b" * 64},
    }
    after = json.loads(json.dumps(manifest))
    after["captured_at"] = "after"
    after["github"]["observed_coordinate"] = "4444J99/limen"
    after["github"]["repository_settings"]["full_name"] = "4444J99/limen"

    assert invariant_projection(manifest) == invariant_projection(after)
    assert compare_manifests(manifest, after) == []

    after["github"]["default_sha"] = "c" * 40
    assert compare_manifests(manifest, after) == ["transfer invariant changed: github"]


def _org_transfer_manifest() -> dict[str, Any]:
    return {
        "captured_at": "before",
        "identity": LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json"),
        "github": {
            "observed_coordinate": "organvm/limen",
            "repository_settings": {
                "id": 1_255_213_941,
                "name": "limen",
                "full_name": "organvm/limen",
                "custom_properties": {},
            },
            "rulesets": {
                "available": True,
                "value": [
                    {
                        "available": True,
                        "value": {
                            "id": 7,
                            "rules": [
                                {
                                    "type": "pull_request",
                                    "parameters": {
                                        "required_review_thread_resolution": True,
                                        "dismissal_restriction": {
                                            "enabled": False,
                                            "allowed_actors": [],
                                        },
                                    },
                                }
                            ],
                        },
                    }
                ],
            },
            "issues": {
                "count": 1,
                "numbers": [11],
                "records": [
                    {
                        "number": 11,
                        "issue_type": {"id": 3, "node_id": "IT_3", "name": "Bug Report"},
                        "labels": ["existing"],
                    }
                ],
                "types": {
                    "available": True,
                    "value": [{"id": 3, "node_id": "IT_3", "name": "Bug Report"}],
                },
            },
            "labels": [{"id": 1, "name": "existing", "color": "ffffff"}],
        },
        "protected_state": {"checkouts": {}, "paths": {}},
        "git_bundle": {"sha256": "b" * 64},
    }


def test_v3_readable_surface_envelopes_remain_comparison_compatible() -> None:
    hook = {
        "id": 11,
        "type": "Repository",
        "name": "web",
        "active": True,
        "events": ["push"],
        "config": {"content_type": "json", "url": "https://example.invalid/hook"},
        "created_at": "2026-08-25T00:00:00Z",
        "updated_at": "2026-08-25T00:00:00Z",
    }
    deploy_key = {
        "id": 12,
        "title": "read-only mirror",
        "key": "ssh-ed25519 public-material",
        "read_only": True,
        "created_at": "2026-08-25T00:00:00Z",
        "verified": True,
    }
    branch_detail = {"required_pull_request_reviews": {"required_approving_review_count": 1}}
    action_responses = _actions_settings_responses()

    class Client:
        def optional_list(self, endpoint: str) -> dict[str, Any]:
            if "/hooks?" in endpoint:
                return {"available": True, "value": [hook]}
            if "/keys?" in endpoint:
                return {"available": True, "value": [deploy_key]}
            raise AssertionError(f"unexpected list endpoint: {endpoint}")

        def optional_object(self, endpoint: str) -> dict[str, Any]:
            if "/branches/main/protection" in endpoint:
                return {"available": True, "value": branch_detail}
            return action_responses[endpoint]

    client = Client()
    before = _org_transfer_manifest()
    before_github = before["github"]
    before_github["webhooks"] = {"available": True, "value": [transfer._webhook_record(hook)]}
    before_github["deploy_keys"] = {"available": True, "value": [transfer._deploy_key_record(deploy_key)]}
    before_github["branch_protection"] = {
        "main": {"available": True, "value": branch_detail},
    }
    before_github["actions"] = transfer._required_actions_settings(client, "4444J99/limen")
    before_github["actions"]["selected_actions"] = {
        "available": False,
        "error_class": "github_api_unavailable",
        "error_digest": "legacy-409-digest",
    }

    after = json.loads(json.dumps(before))
    after_github = after["github"]
    after_github["webhooks"] = transfer._required_webhook_census(client, "4444J99/limen")
    after_github["deploy_keys"] = transfer._required_deploy_key_census(client, "4444J99/limen")
    after_github["branch_protection"] = transfer._required_branch_protection_census(
        client,
        "4444J99/limen",
        [{"name": "main", "protected": True}],
    )
    after_github["actions"] = transfer._required_actions_settings(client, "4444J99/limen")

    assert isinstance(after_github["webhooks"], dict)
    assert isinstance(after_github["deploy_keys"], dict)
    assert after_github["actions"]["permissions"]["available"] is True
    assert compare_manifests(before, after) == []


@pytest.mark.parametrize(
    "post_types",
    [
        {"available": False, "error_class": "github_api_unavailable"},
        {"available": True, "value": []},
    ],
)
def test_org_to_personal_postflight_accepts_only_exact_semantic_normalizations(
    post_types: dict[str, Any],
) -> None:
    before = _org_transfer_manifest()
    after = json.loads(json.dumps(before))
    after["captured_at"] = "after"
    github = after["github"]
    github["repository_settings"]["custom_properties"] = None
    del github["rulesets"]["value"][0]["value"]["rules"][0]["parameters"]["dismissal_restriction"]
    github["issues"]["types"] = post_types
    github["issues"]["records"][0]["issue_type"] = None
    github["issues"]["records"][0]["labels"].append("transfer-type/bug-report")
    github["labels"].append({"id": 2, "name": "transfer-type/bug-report", "color": "ffffff"})

    assert transfer_type_label("  Bug / Report  ") == "transfer-type/bug-report"
    assert compare_manifests(before, after) == []


@pytest.mark.parametrize(
    "restriction",
    [
        {"enabled": True, "allowed_actors": []},
        {"enabled": False, "allowed_actors": [{"actor_id": 1}]},
        {"enabled": False, "allowed_actors": [], "unexpected": True},
    ],
)
def test_postflight_rejects_nonempty_or_enabled_dismissal_restriction(
    restriction: dict[str, object],
) -> None:
    before = _org_transfer_manifest()
    after = json.loads(json.dumps(before))
    parameters = after["github"]["rulesets"]["value"][0]["value"]["rules"][0]["parameters"]
    parameters["dismissal_restriction"] = restriction

    assert compare_manifests(before, after) == ["transfer invariant changed: github"]


@pytest.mark.parametrize("compensation", [None, "transfer-type/bug", "transfer-type/Bug-Report"])
def test_postflight_rejects_absent_or_wrong_issue_type_compensation(compensation: str | None) -> None:
    before = _org_transfer_manifest()
    after = json.loads(json.dumps(before))
    github = after["github"]
    github["issues"]["types"] = {"available": False}
    github["issues"]["records"][0]["issue_type"] = None
    if compensation is not None:
        github["issues"]["records"][0]["labels"].append(compensation)
        github["labels"].append({"id": 2, "name": compensation, "color": "ffffff"})

    assert compare_manifests(before, after) == ["transfer invariant changed: github"]


def test_postflight_rejects_changed_native_issue_type_semantics() -> None:
    before = _org_transfer_manifest()
    after = json.loads(json.dumps(before))
    after["github"]["issues"]["records"][0]["issue_type"] = {
        "id": 9,
        "node_id": "IT_9",
        "name": "Feature Request",
    }

    assert compare_manifests(before, after) == ["transfer invariant changed: github"]


def test_postflight_rejects_loss_of_nonempty_custom_properties() -> None:
    before = _org_transfer_manifest()
    after = json.loads(json.dumps(before))
    before["github"]["repository_settings"]["custom_properties"] = {"control-plane": "limen"}
    after["github"]["repository_settings"]["custom_properties"] = None

    assert compare_manifests(before, after) == ["transfer invariant changed: github"]


def test_public_receipt_contains_digests_and_denominators_not_private_state(tmp_path: Path) -> None:
    manifest = {
        "captured_at": "2026-08-25T00:00:00+00:00",
        "identity": LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json"),
        "github": {
            "observed_coordinate": "organvm/limen",
            "default_sha": "a" * 40,
            "refs": {"branches": [{"ref": "refs/heads/main"}], "tags": []},
            "releases": [],
            "issues": {"count": 2},
            "open_pull_requests": [
                {
                    "review_threads": [
                        {"is_resolved": False, "is_outdated": False},
                        {"is_resolved": False, "is_outdated": True},
                    ]
                }
            ],
            "actions": {"workflow_states": []},
            "apps": {"available": False},
            "access": {
                "denominators": {
                    "direct_grants": 0,
                    "team_grants": 0,
                    "pending_invitations": 0,
                }
            },
            "environments": [],
        },
        "protected_state": {
            "checkouts": {"agy": {"state_digest": "secret"}},
            "paths": {"opencode": {"tree_sha256": "private"}},
        },
        "git_bundle": {"sha256": "b" * 64, "restore_verified": True},
    }

    receipt = public_receipt(manifest, canonical_sha256(manifest))

    rendered = json.dumps(receipt)
    assert receipt["denominators"]["review_threads"] == 2
    assert receipt["denominators"]["unresolved_current_review_threads"] == 1
    assert receipt["denominators"]["unresolved_outdated_review_threads"] == 1
    assert receipt["denominators"]["direct_access_grants"] == 0
    assert receipt["denominators"]["team_access_grants"] == 0
    assert receipt["denominators"]["pending_access_invitations"] == 0
    assert "secret" not in rendered
    assert "state_digest" not in rendered
    assert "tree_sha256" not in rendered
    assert "agy" not in rendered
    assert "opencode" not in rendered


def test_existing_bundle_is_restored_before_it_is_accepted(tmp_path: Path) -> None:
    repository = tmp_path / "source"
    bundle = tmp_path / "source.bundle"
    subprocess.run(["git", "init", str(repository)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "test@example.invalid"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repository), "config", "user.name", "Test"], check=True)
    (repository / "proof.txt").write_text("bundle restore proof\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repository), "add", "proof.txt"], check=True)
    subprocess.run(["git", "-C", str(repository), "commit", "-m", "proof"], check=True)
    subprocess.run(
        ["git", "-C", str(repository), "bundle", "create", str(bundle), "--all"],
        check=True,
    )

    receipt = verify_existing_bundle(bundle)

    assert receipt["restore_verified"] is True
    assert receipt["ref_count"] >= 1
    assert receipt["sha256"] == file_sha256(bundle)


def _bundle_refresh_runner(
    *,
    fail_stage: str | None = None,
    mismatch_restored_refs: bool = False,
):
    def runner(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        stage: str
        stdout = ""
        if command[:3] == ["git", "clone", "--mirror"]:
            stage = "clone_source" if str(command[3]).startswith("https://") else "clone_restore"
        elif "fetch" in command:
            stage = "fetch_pull_refs"
        elif "bundle" in command and "create" in command:
            stage = "bundle_create"
        elif "bundle" in command and "verify" in command:
            stage = "bundle_verify"
        elif "for-each-ref" in command:
            stage = "source_refs" if Path(command[2]).name == "source.git" else "restored_refs"
            tip = "b" * 40 if stage == "restored_refs" and mismatch_restored_refs else "a" * 40
            stdout = f"refs/heads/main {tip}\n"
        else:  # pragma: no cover - protects this test double from silent command growth
            raise AssertionError(f"unexpected bundle command: {command}")

        if stage == fail_stage:
            return subprocess.CompletedProcess(command, 1, "", f"failed at {stage}")
        if stage == "bundle_create":
            Path(command[-2]).write_bytes(b"new verified bundle")
        return subprocess.CompletedProcess(command, 0, stdout, "")

    return runner


@pytest.mark.parametrize(
    "fail_stage",
    [
        "clone_source",
        "fetch_pull_refs",
        "bundle_create",
        "bundle_verify",
        "clone_restore",
        "source_refs",
        "restored_refs",
        "restored_ref_mismatch",
    ],
)
def test_bundle_refresh_failure_preserves_the_previous_verified_bundle(tmp_path: Path, fail_stage: str) -> None:
    bundle = tmp_path / "source.bundle"
    bundle.write_bytes(b"previous verified bundle")
    runner = _bundle_refresh_runner(
        fail_stage=None if fail_stage == "restored_ref_mismatch" else fail_stage,
        mismatch_restored_refs=fail_stage == "restored_ref_mismatch",
    )

    with pytest.raises(TransferCaptureError):
        transfer.create_verified_bundle("4444J99/limen", bundle, runner=runner)

    assert bundle.read_bytes() == b"previous verified bundle"
    assert list(tmp_path.iterdir()) == [bundle]


def test_bundle_refresh_replaces_only_after_the_candidate_is_restored_and_verified(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = tmp_path / "source.bundle"
    bundle.write_bytes(b"previous verified bundle")
    real_replace = transfer.os.replace
    replacement_observations: list[tuple[Path, Path]] = []

    def checked_replace(source: str | Path, destination: str | Path) -> None:
        source_path = Path(source)
        destination_path = Path(destination)
        assert source_path.read_bytes() == b"new verified bundle"
        assert destination_path.read_bytes() == b"previous verified bundle"
        replacement_observations.append((source_path, destination_path))
        real_replace(source, destination)

    monkeypatch.setattr(transfer.os, "replace", checked_replace)

    receipt = transfer.create_verified_bundle(
        "4444J99/limen",
        bundle,
        runner=_bundle_refresh_runner(),
    )

    assert replacement_observations
    assert bundle.read_bytes() == b"new verified bundle"
    assert receipt["sha256"] == file_sha256(bundle)
    assert receipt["restore_verified"] is True


def test_bundle_refresh_replace_interruption_preserves_the_previous_verified_bundle(
    tmp_path: Path,
    monkeypatch,
) -> None:
    bundle = tmp_path / "source.bundle"
    bundle.write_bytes(b"previous verified bundle")

    def interrupted_replace(_source: str | Path, _destination: str | Path) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr(transfer.os, "replace", interrupted_replace)

    with pytest.raises(TransferCaptureError, match="replacement failed"):
        transfer.create_verified_bundle(
            "4444J99/limen",
            bundle,
            runner=_bundle_refresh_runner(),
        )

    assert bundle.read_bytes() == b"previous verified bundle"
    assert list(tmp_path.iterdir()) == [bundle]


def test_verified_bundle_is_bound_to_every_github_ref_and_open_pr_head() -> None:
    github = {
        "repository_settings": {"default_branch": "main"},
        "default_sha": "a" * 40,
        "refs": {
            "branches": [{"ref": "refs/heads/main", "tip": "a" * 40}],
            "tags": [{"ref": "refs/tags/v1", "tip": "b" * 40}],
        },
        "open_pull_requests": [{"number": 7, "head_sha": "c" * 40}],
    }
    bundle = {
        "sha256": "d" * 64,
        "restore_verified": True,
        "_refs": [
            f"refs/heads/main {'a' * 40}",
            f"refs/pull/7/head {'c' * 40}",
            f"refs/tags/v1 {'b' * 40}",
        ],
    }

    bound = bind_bundle_to_github_manifest(github, bundle)

    assert bound == {"sha256": "d" * 64, "restore_verified": True}
    bad = json.loads(json.dumps(bundle))
    bad["_refs"][1] = f"refs/pull/7/head {'e' * 40}"
    with pytest.raises(TransferCaptureError, match="differs from captured GitHub refs"):
        bind_bundle_to_github_manifest(github, bad)


def test_protected_state_attribution_binds_exact_manifests_actor_and_evidence() -> None:
    before = {
        "captured_at": "before",
        "identity": LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json"),
        "github": {
            "observed_coordinate": "organvm/limen",
            "repository_settings": {"name": "limen", "full_name": "organvm/limen"},
        },
        "protected_state": {
            "checkouts": {},
            "paths": {"opencode": {"exists": True, "tree_sha256": "a" * 64}},
        },
        "git_bundle": {"sha256": "b" * 64},
    }
    after = json.loads(json.dumps(before))
    after["captured_at"] = "after"
    after["protected_state"]["paths"]["opencode"]["tree_sha256"] = "c" * 64
    assert compare_manifests(before, after) == [
        "protected self-owned state changed without a private attribution receipt"
    ]

    before_delta = canonical_sha256(before["protected_state"]["paths"]["opencode"])
    after_delta = canonical_sha256(after["protected_state"]["paths"]["opencode"])
    evidence = {
        "schema_version": "limen.protected_state_delta_evidence.v1",
        "delta": "paths/opencode",
        "actor": "opencode",
        "before_sha256": before_delta,
        "after_sha256": after_delta,
        "transfer_actor_touched": False,
        "cause_class": "protected_lane_self_write",
        "observed_at": "2026-08-25T12:00:00+00:00",
    }
    attribution = {
        "schema_version": "limen.protected_state_attribution.v1",
        "before_manifest_sha256": canonical_sha256(before),
        "after_manifest_sha256": canonical_sha256(after),
        "changes": {
            "paths/opencode": {
                "actor": "opencode",
                "before_sha256": before_delta,
                "after_sha256": after_delta,
                "evidence": evidence,
                "evidence_sha256": canonical_sha256(evidence),
            }
        },
    }

    assert compare_manifests(before, after, protected_attribution=attribution) == []
    attribution["changes"]["paths/opencode"]["actor"] = "codex"
    assert compare_manifests(before, after, protected_attribution=attribution) == [
        "protected state attribution does not bind the exact private delta: paths/opencode"
    ]


def test_protected_processes_are_captured_and_diffed_per_lane(tmp_path: Path, monkeypatch) -> None:
    agy_checkout = tmp_path / "agy-checkout"
    opencode_path = tmp_path / "opencode-runtime"
    agy_checkout.mkdir()
    opencode_path.mkdir()
    process_table = "\n".join(
        (
            f"101 1 /Applications/Antigravity.app/agy --workspace {agy_checkout}",
            f"202 1 opencode serve --state {opencode_path}",
            "303 1 unrelated-daemon",
        )
    )

    monkeypatch.setattr(
        transfer.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 0, process_table, ""),
    )
    monkeypatch.setattr(transfer, "_protected_checkout", lambda _path: {"head": "a" * 40})
    monkeypatch.setattr(transfer, "protected_path_digest", lambda _path: {"tree_sha256": "b" * 64})

    before = capture_protected_state({"agy": agy_checkout}, {"opencode": opencode_path})

    assert set(before["processes"]) == {"agy", "opencode"}
    assert before["processes"]["agy"]["count"] == 1
    assert before["processes"]["agy"]["processes"][0]["pid"] == 101
    assert before["processes"]["opencode"]["count"] == 1
    assert before["processes"]["opencode"]["processes"][0]["pid"] == 202

    after = json.loads(json.dumps(before))
    after["processes"]["agy"]["count"] = 0
    after["processes"]["agy"]["processes"] = []
    after["processes"]["agy"]["snapshot_sha256"] = canonical_sha256([])
    deltas = protected_state_deltas(
        {"protected_state": before},
        {"protected_state": after},
    )
    assert set(deltas) == {"processes/agy"}


def test_process_delta_requires_exact_lane_actor_and_process_cause() -> None:
    before = {
        "captured_at": "before",
        "identity": LIMEN_REPOSITORY_IDENTITY.model_dump(mode="json"),
        "github": {
            "observed_coordinate": "organvm/limen",
            "repository_settings": {"name": "limen", "full_name": "organvm/limen"},
        },
        "protected_state": {
            "checkouts": {},
            "paths": {},
            "processes": {"agy": {"snapshot_sha256": "a" * 64, "count": 1}},
        },
        "git_bundle": {"sha256": "b" * 64},
    }
    after = json.loads(json.dumps(before))
    after["captured_at"] = "after"
    after["protected_state"]["processes"]["agy"] = {
        "snapshot_sha256": "c" * 64,
        "count": 0,
    }
    delta = protected_state_deltas(before, after)["processes/agy"]

    def attribution(actor: str | None, cause: str) -> dict[str, object]:
        evidence = {
            "schema_version": "limen.protected_state_delta_evidence.v1",
            "delta": "processes/agy",
            "actor": actor,
            "before_sha256": delta["before_sha256"],
            "after_sha256": delta["after_sha256"],
            "transfer_actor_touched": False,
            "cause_class": cause,
            "observed_at": "2026-08-25T12:00:00+00:00",
        }
        return {
            "schema_version": "limen.protected_state_attribution.v1",
            "before_manifest_sha256": canonical_sha256(before),
            "after_manifest_sha256": canonical_sha256(after),
            "changes": {
                "processes/agy": {
                    "actor": actor,
                    "before_sha256": delta["before_sha256"],
                    "after_sha256": delta["after_sha256"],
                    "evidence": evidence,
                    "evidence_sha256": canonical_sha256(evidence),
                }
            },
        }

    assert (
        compare_manifests(
            before,
            after,
            protected_attribution=attribution("agy", "protected_lane_process_churn"),
        )
        == []
    )
    for fabricated_actor in (None, "Agy", "codex", "opencode"):
        assert compare_manifests(
            before,
            after,
            protected_attribution=attribution(fabricated_actor, "protected_lane_process_churn"),
        ) == ["protected state attribution does not bind the exact private delta: processes/agy"]
    assert compare_manifests(
        before,
        after,
        protected_attribution=attribution("agy", "protected_lane_self_write"),
    ) == ["protected state attribution does not bind the exact private delta: processes/agy"]


def test_manifest_cli_rejects_colliding_frozen_artifact_paths_before_network(tmp_path: Path) -> None:
    private = tmp_path / ".limen-private"
    private.mkdir()
    output = private / "manifest.json"

    result = subprocess.run(
        [
            "python3",
            "scripts/repository-transfer-manifest.py",
            "--output",
            str(output),
            "--existing-bundle",
            str(private / "bundle"),
            "--verify-against",
            str(output),
        ],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "pairwise distinct" in result.stderr
