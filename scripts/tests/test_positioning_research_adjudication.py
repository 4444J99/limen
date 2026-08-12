from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
import importlib.machinery
import importlib.util
import json
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "positioning-research-adjudication.py"


def _load_module():
    loader = importlib.machinery.SourceFileLoader("positioning_research_adjudication", str(SCRIPT))
    spec = importlib.util.spec_from_loader("positioning_research_adjudication", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


MODULE = _load_module()


def _accepted_receipt(work_id: str):
    if work_id == "PSP-P02-W01":
        return {
            "schema_version": "limen.positioning_work_receipt.v1",
            "work_id": work_id,
            "acceptance_sha256": "9a77e91e51ab8f76149dacd5011f4fd725523b6d74c1db622df2929730d42ec5",
            "outcome": "succeeded",
            "authority": {
                "kind": "direct_human_session",
                "session_id": "019fed0d-52c4-7a83-b493-88a80035b42c",
                "executor": "Codex",
                "human_protected": True,
            },
            "changed_paths": [
                "docs/github-estate-census.json",
                "docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json",
                "institutio/governance/gates.yaml",
                "scripts/github-estate-census.py",
                "scripts/tests/test_github_estate_census_custody.py",
                "scripts/tests/verify-resolver.test.sh",
            ],
            "predicate": {
                "command": "python3 scripts/github-estate-census.py --check-repositories --json",
                "exit_code": 0,
                "output_sha256": "af2c9d21d9eb26f952e3cf4afbab98a9ec595fecc7bca751e6067561ddeb71d4",
                "observed_at": "2026-08-10T22:13:19Z",
            },
            "evidence_urls": [
                "https://github.com/organvm/limen/issues/2173",
                "https://github.com/organvm/limen/pull/2305",
            ],
            "rollback": {"invoked": False, "state": "not needed"},
            "observed_heads": {
                "organvm/limen": "10cf8476d5e88309c71d5fac25167ec7b7af59c4"
            },
        }
    return {
        "schema_version": "limen.positioning_work_receipt.v1",
        "work_id": work_id,
        "acceptance_sha256": "02709f01d310679d8e631d9a7b3a8c71c8759af99097fed9ed6467dd2b9c7a5a",
        "outcome": "succeeded",
        "authority": {
            "kind": "direct_human_session",
            "session_id": "019fed0d-52c4-7a83-b493-88a80035b42c",
            "executor": "Codex",
            "human_protected": True,
        },
        "changed_paths": [
            "docs/positioning/claims-ledger.md",
            "docs/positioning/evidence/README.md",
            "docs/positioning/evidence/flagship-evidence.yaml",
            "docs/receipts/positioning/relays/2026-08-10-psp-p02-w04-w05-evidence-preflight.md",
            "scripts/tests/flagship-evidence.test.py",
        ],
        "predicate": {
            "command": "python3 scripts/flagship-evidence.py --verify-live --json",
            "exit_code": 0,
            "output_sha256": "9054a16a40cad92475d959529bd515e967092bfc29d312d3cad3d2c7058c909c",
            "observed_at": "2026-08-12T11:05:25Z",
        },
        "evidence_urls": [
            "https://github.com/organvm/limen/issues/2177",
            "https://github.com/organvm/limen/pull/2328",
        ],
        "rollback": {"invoked": False, "state": "not needed"},
        "observed_heads": {
            "organvm/limen": "d8b44e60e404b044436addf8108732cc28c06371"
        },
    }


def _accepted_comment(work_id: str):
    receipt = _accepted_receipt(work_id)
    expected = MODULE.ACCEPTED_DEPENDENCIES[work_id]
    assert MODULE._canonical_sha256(receipt) == expected["canonical_receipt_sha256"]
    return {
        "id": int(expected["marked_receipt"].rsplit("-", 1)[1]),
        "html_url": expected["marked_receipt"],
        "body": (
            f"<!-- positioning-receipt:{work_id} -->\n"
            f"```json\n{json.dumps(receipt, indent=2)}\n```"
        ),
    }


def _bundle():
    return {
        "artifact": MODULE._load_json(MODULE.ARTIFACT_PATH),
        "receipt": MODULE._load_json(MODULE.RECEIPT_PATH),
        "program": MODULE._load_yaml(MODULE.PROGRAM_PATH),
        "issue_map": MODULE._load_json(MODULE.ISSUE_MAP_PATH),
        "issue_index": MODULE.ISSUE_INDEX_PATH.read_text(encoding="utf-8"),
        "research_doc": MODULE.RESEARCH_DOC_PATH.read_text(encoding="utf-8"),
        "flagship_evidence": MODULE._load_yaml(MODULE.FLAGSHIP_EVIDENCE_PATH),
        "flagship_evidence_text": MODULE.FLAGSHIP_EVIDENCE_PATH.read_text(encoding="utf-8"),
        "claims_ledger": MODULE.CLAIMS_LEDGER_PATH.read_text(encoding="utf-8"),
    }


def _errors(bundle):
    return MODULE.validate_bundle(
        bundle["artifact"],
        bundle["receipt"],
        bundle["program"],
        bundle["issue_map"],
        bundle["issue_index"],
        bundle["research_doc"],
        bundle["flagship_evidence"],
        bundle["flagship_evidence_text"],
        bundle["claims_ledger"],
    )


def _sync_projected_issue_receipt(bundle) -> None:
    work_ids = bundle["artifact"]["repository_drift_relay"]["affected_work_ids"]
    bundle["receipt"]["portfolio_repository_identity"][
        "live_issue_bodies_requiring_refresh"
    ] = [
        {
            "work_id": work_id,
            "issue": bundle["issue_map"]["issues"][work_id]["number"],
        }
        for work_id in work_ids
    ]


def _rfc3339(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _live_profile_fixture():
    now = datetime(2026, 8, 12, 13, 0, tzinfo=timezone.utc)
    latest_trigger = "2" * 40
    current_head = "3" * 40
    accepted_head = _bundle()["receipt"]["public_profile"]["head"]
    run_start = now.replace(hour=7, minute=0, second=0, microsecond=0)
    runs = []
    for offset in range(8):
        created_at = run_start - timedelta(days=offset)
        run_id = 9000 + offset
        trigger_head = latest_trigger if offset == 0 else f"{offset + 3:040x}"
        runs.append(
            {
                "id": run_id,
                "event": "schedule",
                "status": "completed",
                "conclusion": "success",
                "created_at": _rfc3339(created_at),
                "updated_at": _rfc3339(created_at + timedelta(minutes=5)),
                "head_sha": trigger_head,
                "html_url": (
                    f"https://github.com/{MODULE.PROFILE_REPOSITORY}/actions/runs/{run_id}"
                ),
            }
        )

    stats = {}
    for name, value in {
        "personal_public_repos": 8,
        "followers": 41,
        "member_since": "2016",
        "ecosystem_public_repos": 227,
        "ecosystem_original_repos": 198,
        "contributions_last_year": 33203,
    }.items():
        stats[name] = {
            "value": value,
            "basis": "live-public-gh-api",
            "source_query": f"gh api public/{name}",
            "attest": "api",
        }

    contribution_days = []
    first_day = now.date() - timedelta(days=365)
    for offset in range(366):
        contribution_days.append(
            {
                "contributionCount": 91 if offset < 365 else 2,
                "date": (first_day + timedelta(days=offset)).isoformat(),
            }
        )
    contribution_total = sum(day["contributionCount"] for day in contribution_days)
    weeks = [
        {"contributionDays": contribution_days[index : index + 7]}
        for index in range(0, len(contribution_days), 7)
    ]

    compare_url = (
        f"https://api.github.com/repos/{MODULE.PROFILE_REPOSITORY}/compare/"
        f"{accepted_head}...{current_head}"
    )
    trigger_compare_url = (
        f"https://api.github.com/repos/{MODULE.PROFILE_REPOSITORY}/compare/"
        f"{latest_trigger}...{current_head}"
    )
    public_payloads = {
        MODULE.PROFILE_USER_API_URL: {
            **MODULE.EXPECTED_PROFILE_METADATA_RESULT,
            "updated_at": "2026-08-12T08:00:00Z",
        },
        MODULE.PROFILE_MANIFEST_RAW_URL: {
            "login": "4444J99",
            "generated": "2026-08-12T07:05:00Z",
            "stats": stats,
        },
        MODULE.PROFILE_RUNS_API_URL: {"workflow_runs": runs},
        MODULE.PROFILE_MAIN_COMMIT_API_URL: {
            "sha": current_head,
            "html_url": (
                f"https://github.com/{MODULE.PROFILE_REPOSITORY}/commit/{current_head}"
            ),
            "commit": {"committer": {"date": "2026-08-12T07:10:00Z"}},
            "parents": [{"sha": "9" * 40}],
        },
        trigger_compare_url: {
            "url": trigger_compare_url,
            "status": "ahead",
            "ahead_by": 2,
            "base_commit": {"sha": latest_trigger},
            "merge_base_commit": {"sha": latest_trigger},
            "commits": [{"sha": "8" * 40}],
        },
        compare_url: {
            "url": compare_url,
            "status": "ahead",
            "ahead_by": 2,
            "base_commit": {"sha": accepted_head},
            "merge_base_commit": {"sha": accepted_head},
            "commits": [{"sha": "4" * 40}],
        },
    }
    contribution_payload = {
        "data": {
            "user": {
                "contributionsCollection": {
                    "contributionCalendar": {
                        "totalContributions": contribution_total,
                        "weeks": weeks,
                    }
                }
            }
        }
    }
    return now, public_payloads, contribution_payload


def test_tracked_adjudication_bundle_passes_static_contract() -> None:
    assert _errors(_bundle()) == []


def test_formalization_is_ready_but_projection_remains_pending() -> None:
    bundle = _bundle()

    assert bundle["artifact"]["status"] == MODULE.FORMAL_STATUS
    assert bundle["artifact"]["formalization"]["projection_status"] == MODULE.PROJECTION_STATUS
    assert bundle["receipt"]["formal_completion"]["allowed"] is False
    assert bundle["receipt"]["formal_completion"]["projection_status"] == MODULE.PROJECTION_STATUS


def test_malformed_formalization_and_accepted_blocks_fail_as_validation_errors() -> None:
    malformed = _bundle()
    malformed["artifact"] = copy.deepcopy(malformed["artifact"])
    malformed["artifact"]["formalization"] = "not-a-mapping"
    assert "artifact.formalization must be a mapping" in _errors(malformed)

    malformed = _bundle()
    malformed["receipt"] = copy.deepcopy(malformed["receipt"])
    malformed["receipt"]["formal_completion"] = ["not-a-mapping"]
    assert "receipt.formal_completion must be a mapping" in _errors(malformed)

    malformed = _bundle()
    malformed["artifact"] = copy.deepcopy(malformed["artifact"])
    malformed["artifact"]["formalization"]["accepted_dependencies"] = "not-a-list"
    assert "artifact.formalization.accepted_dependencies must be a list" in _errors(malformed)

    malformed = _bundle()
    malformed["receipt"] = copy.deepcopy(malformed["receipt"])
    malformed["receipt"]["formal_completion"]["dependencies"][0] = "not-a-mapping"
    assert "receipt.formal_completion.dependencies[0] must be a mapping" in _errors(malformed)

    malformed = _bundle()
    malformed["flagship_evidence"] = copy.deepcopy(malformed["flagship_evidence"])
    malformed["flagship_evidence"]["w08_research_import"] = "not-a-mapping"
    assert "flagship_evidence.w08_research_import must be a mapping" in _errors(malformed)

    malformed = _bundle()
    malformed["flagship_evidence"] = copy.deepcopy(malformed["flagship_evidence"])
    malformed["flagship_evidence"]["w08_research_import"]["claims"][0] = "not-a-mapping"
    assert (
        "flagship_evidence.w08_research_import.claims[0] must be a mapping" in _errors(malformed)
    )

    malformed = _bundle()
    malformed["artifact"] = copy.deepcopy(malformed["artifact"])
    malformed["artifact"]["w05_import_contract"] = "not-a-mapping"
    assert "artifact.w05_import_contract must be a mapping" in _errors(malformed)

    malformed = _bundle()
    malformed["receipt"] = copy.deepcopy(malformed["receipt"])
    malformed["receipt"]["claims_ledger_integration"] = "not-a-mapping"
    assert "receipt.claims_ledger_integration must be a mapping" in _errors(malformed)


def test_all_imported_claim_fields_must_exactly_match_accepted_w05_projection() -> None:
    bundle = _bundle()
    bundle["flagship_evidence"] = copy.deepcopy(bundle["flagship_evidence"])
    imported = bundle["flagship_evidence"]["w08_research_import"]["claims"][0]
    imported["public_wording"] = "broadened after acceptance"

    assert (
        "all 13 artifact claims must exactly match the accepted W05 four-layer and publishable projection"
        in _errors(bundle)
    )


def test_w05_import_cannot_replace_the_accepted_flagship_evidence_blob() -> None:
    bundle = _bundle()
    bundle["artifact"] = copy.deepcopy(bundle["artifact"])
    bundle["flagship_evidence"] = copy.deepcopy(bundle["flagship_evidence"])
    wording = "jointly mutated after accepted W05"
    bundle["artifact"]["claims"][0]["w05_integration"]["public_wording"] = wording
    bundle["flagship_evidence"]["w08_research_import"]["claims"][0]["public_wording"] = wording
    bundle["flagship_evidence_text"] = yaml.safe_dump(
        bundle["flagship_evidence"],
        sort_keys=False,
    )

    errors = _errors(bundle)
    assert "flagship-evidence blob differs from the accepted W05 binding" in errors
    assert (
        "all 13 artifact claims must exactly match the accepted W05 four-layer and publishable projection"
        not in errors
    )


def test_claims_ledger_table_must_match_all_four_dispositions() -> None:
    bundle = _bundle()
    bundle["claims_ledger"] = bundle["claims_ledger"].replace(
        "| `profile-production-systems-headline` | `verified` |",
        "| `profile-production-systems-headline` | `contradicted` |",
        1,
    )

    assert (
        "accepted claims-ledger table must exactly match all 13 formalized claim dispositions"
        in _errors(bundle)
    )


def test_claim_denominator_is_fixed_and_not_self_declared() -> None:
    bundle = _bundle()
    bundle["artifact"] = copy.deepcopy(bundle["artifact"])
    bundle["artifact"]["claims"].pop()
    bundle["artifact"]["coverage"]["denominator"] = 12
    bundle["artifact"]["coverage"]["adjudicated"] = 12
    bundle["artifact"]["w05_import_contract"]["source_claim_ids"].pop()

    assert "claims must contain exactly 13 adjudicated rows" in _errors(bundle)


def test_disposition_vocabulary_cannot_authorize_its_own_new_value() -> None:
    bundle = _bundle()
    bundle["artifact"] = copy.deepcopy(bundle["artifact"])
    bundle["artifact"]["disposition_vocabularies"]["measurement"].append("invented")
    bundle["artifact"]["claims"][0]["measurement"]["disposition"] = "invented"

    errors = _errors(bundle)
    assert "measurement disposition vocabulary must match the canonical ordered vocabulary" in errors


def test_tokenized_disposition_and_citation_sinks_fail_neutrally() -> None:
    for malformed_vocabulary in ("verified", [{"unhashable": True}]):
        bundle = _bundle()
        bundle["artifact"] = copy.deepcopy(bundle["artifact"])
        bundle["artifact"]["disposition_vocabularies"]["measurement"] = malformed_vocabulary
        assert (
            "measurement disposition vocabulary must match the canonical ordered vocabulary"
            in _errors(bundle)
        )

    disposition = _bundle()
    disposition["artifact"] = copy.deepcopy(disposition["artifact"])
    disposition["artifact"]["claims"][0]["measurement"]["disposition"] = {"unhashable": True}
    assert any("measurement uses an unknown disposition" in error for error in _errors(disposition))

    citations = _bundle()
    citations["artifact"] = copy.deepcopy(citations["artifact"])
    citations["artifact"]["claims"][0]["measurement"]["citations"] = [["PROFILE_README"]]
    assert any(
        "measurement citations must be nonempty string source IDs" in error
        for error in _errors(citations)
    )


def test_tokenized_lavrea_and_http_receipt_sinks_fail_neutrally() -> None:
    axis = _bundle()
    axis["artifact"] = copy.deepcopy(axis["artifact"])
    axis["artifact"]["lavrea_axis_audit"][0]["axis"] = ["contributions_year"]
    assert "lavrea_axis_audit[0].axis must be a nonempty string token" in _errors(axis)

    citations = _bundle()
    citations["artifact"] = copy.deepcopy(citations["artifact"])
    citations["artifact"]["lavrea_axis_audit"][0]["citations"] = [{"source": "PROFILE_README"}]
    assert any("needs valid citations" in error for error in _errors(citations))

    http = _bundle()
    http["receipt"] = copy.deepcopy(http["receipt"])
    http["receipt"]["http_receipts"][0]["id"] = ["current_profile_blog_field"]
    assert "receipt.http_receipts[0] needs a nonempty string id" in _errors(http)


def test_public_sources_reject_embedded_credentials() -> None:
    bundle = _bundle()
    bundle["artifact"] = copy.deepcopy(bundle["artifact"])
    bundle["artifact"]["sources"]["PROFILE_README"]["url"] = (
        "https://token@example.test/public-source"
    )

    assert any("credential-free HTTPS public URL" in error for error in _errors(bundle))


def test_public_sources_reject_query_and_fragment_credentials() -> None:
    for unsafe_url in (
        "https://example.test/public-source?access_token=SECRET",
        "https://example.test/public-source#access_token=SECRET",
    ):
        bundle = _bundle()
        bundle["artifact"] = copy.deepcopy(bundle["artifact"])
        bundle["artifact"]["sources"]["PROFILE_README"]["url"] = unsafe_url

        assert any("credential-free HTTPS public URL" in error for error in _errors(bundle))

    assert MODULE._credential_free_https_url(
        "https://docs.github.com/en/graphql/reference/users#contributioncalendar"
    )


def test_public_sources_bind_exact_expected_repository_path_and_url() -> None:
    unexpected_repository = _bundle()
    unexpected_repository["artifact"] = copy.deepcopy(unexpected_repository["artifact"])
    source = unexpected_repository["artifact"]["sources"]["PROFILE_README"]
    source["repository"] = "unexpected-owner/private-profile"
    source["url"] = (
        "https://github.com/unexpected-owner/private-profile/blob/"
        f"{source['head']}/README.md"
    )
    errors = _errors(unexpected_repository)
    assert "source PROFILE_README must bind its exact public repository" in errors
    assert "source PROFILE_README must bind its exact public url" in errors

    wrong_path = _bundle()
    wrong_path["artifact"] = copy.deepcopy(wrong_path["artifact"])
    source = wrong_path["artifact"]["sources"]["PROFILE_README"]
    source["path"] = "PRIVATE.md"
    source["url"] = (
        "https://github.com/4444J99/4444J99/blob/"
        f"{source['head']}/PRIVATE.md"
    )
    errors = _errors(wrong_path)
    assert "source PROFILE_README must bind its exact public path" in errors
    assert "source PROFILE_README must bind its exact public url" in errors


def test_public_sources_reject_unexpected_and_credential_bearing_fields() -> None:
    unexpected = _bundle()
    unexpected["artifact"] = copy.deepcopy(unexpected["artifact"])
    unexpected["artifact"]["sources"]["PROFILE_API_RECEIPT"]["authorization"] = (
        "Bearer SECRET"
    )
    assert (
        "source PROFILE_API_RECEIPT must match its exact typed public contract"
        in _errors(unexpected)
    )

    changed = _bundle()
    changed["artifact"] = copy.deepcopy(changed["artifact"])
    changed["artifact"]["sources"]["PROFILE_API_RECEIPT"]["receipt_path"] = (
        "unexpected/private-metadata"
    )
    errors = _errors(changed)
    assert "source PROFILE_API_RECEIPT must match its exact typed public contract" in errors
    assert "source PROFILE_API_RECEIPT must bind its exact public receipt_path" in errors


def test_live_public_sources_require_public_repositories_and_exact_paths() -> None:
    artifact = _bundle()["artifact"]

    def valid_fetch(args):
        endpoint = args[-1]
        for source_id, expected in MODULE.EXPECTED_PUBLIC_SOURCES.items():
            repository = expected.get("repository")
            path = expected.get("path")
            head = expected.get("head")
            if all(isinstance(value, str) for value in (repository, path, head)):
                content_endpoint = (
                    f"repos/{repository}/contents/{MODULE.quote(path, safe='/')}?ref={head}"
                )
                if endpoint == content_endpoint:
                    return {
                        "type": "file",
                        "path": path,
                        "html_url": expected["url"],
                        "sha": expected.get("blob"),
                    }
        repository = endpoint.removeprefix("repos/")
        return {"full_name": repository, "private": False, "visibility": "public"}

    assert MODULE.validate_live_sources(artifact, valid_fetch) == []

    def private_fetch(args):
        endpoint = args[-1]
        if endpoint == "repos/4444J99/4444J99":
            return {"full_name": "4444J99/4444J99", "private": True, "visibility": "private"}
        return valid_fetch(args)

    assert (
        "public source repository 4444J99/4444J99 must resolve as that exact public repository"
        in MODULE.validate_live_sources(artifact, private_fetch)
    )

    def wrong_path_fetch(args):
        value = valid_fetch(args)
        if args[-1].endswith("/contents/README.md?ref=f198b37e3161121e7c198e21bd18b87e29b6bc4f"):
            value = {**value, "path": "PRIVATE.md"}
        return value

    assert (
        "public source PROFILE_README must resolve its exact accepted repository path"
        in MODULE.validate_live_sources(artifact, wrong_path_fetch)
    )


def test_claim_ids_reject_non_public_tokens() -> None:
    bundle = _bundle()
    bundle["artifact"] = copy.deepcopy(bundle["artifact"])
    bundle["artifact"]["claims"][0]["id"] = "PRIVATE/Claim"
    bundle["artifact"]["w05_import_contract"]["source_claim_ids"][0] = "PRIVATE/Claim"

    assert any("public-safe lowercase token format" in error for error in _errors(bundle))


def test_live_identity_resolves_only_the_immutable_repository_id() -> None:
    bundle = _bundle()
    calls = []

    def fetch(args):
        calls.append(args)
        return {
            "id": MODULE.PORTFOLIO_REPOSITORY_ID,
            "full_name": MODULE.PORTFOLIO_CANONICAL_SLUG,
            "visibility": "public",
            "private": False,
            "default_branch": "main",
            "archived": False,
        }

    assert MODULE.validate_live_identity(bundle["program"], fetch) == []
    assert calls == [["api", f"repositories/{MODULE.PORTFOLIO_REPOSITORY_ID}"]]


def test_live_identity_rejects_non_mapping_transport_payloads_neutrally() -> None:
    program = _bundle()["program"]

    for payload in ([], "not-an-object", 42):
        assert MODULE.validate_live_identity(program, lambda _args, value=payload: value) == [
            "stable repository identity response must be a mapping"
        ]

    actions_token_payload = {
        "id": MODULE.PORTFOLIO_REPOSITORY_ID,
        "full_name": MODULE.PORTFOLIO_CANONICAL_SLUG,
        "visibility": "public",
        "private": False,
        "default_branch": "main",
        "archived": False,
    }
    assert MODULE.validate_live_identity(program, lambda _args: actions_token_payload) == []


def test_live_identity_keeps_public_immutable_metadata_fail_closed_for_actions_tokens() -> None:
    program = _bundle()["program"]
    moved_private = {
        "id": MODULE.PORTFOLIO_REPOSITORY_ID,
        "full_name": "future-owner/portfolio",
        "visibility": "private",
        "private": True,
        "default_branch": "trunk",
        "archived": True,
        "permissions": {"admin": False},
    }

    errors = MODULE.validate_live_identity(program, lambda _args: moved_private)

    assert any("full_name='future-owner/portfolio'" in error for error in errors)
    assert any("visibility='private'" in error for error in errors)
    assert any("default_branch='trunk'" in error for error in errors)
    assert any("archived=True" in error for error in errors)
    assert "stable portfolio repository must remain public" in errors
    assert not any("admin" in error or "permissions" in error for error in errors)


def test_live_reference_binds_exact_open_issue_and_rejects_substitutes() -> None:
    static = _bundle()
    static["receipt"] = copy.deepcopy(static["receipt"])
    static["receipt"]["formal_completion"]["live_reference"]["issue"] = (
        "https://github.com/other/repo/issues/1245"
    )
    assert (
        "the profile-engine live reference must bind the exact open organvm/limen#1245 contract"
        in _errors(static)
    )

    expected = {
        "number": MODULE.LIVE_REFERENCE_ISSUE_NUMBER,
        "html_url": MODULE.LIVE_REFERENCE_URL,
        "url": MODULE.LIVE_REFERENCE_API_URL,
        "repository_url": "https://api.github.com/repos/organvm/limen",
        "state": "open",
    }
    calls = []

    def fetch(args):
        calls.append(args)
        return expected

    assert MODULE.validate_live_reference(fetch) == []
    assert calls == [["api", "repos/organvm/limen/issues/1245"]]
    assert MODULE.validate_live_reference(lambda _args: []) == [
        "profile-engine live reference response must be a mapping"
    ]

    closed = {**expected, "state": "closed"}
    assert any("state must remain 'open'" in error for error in MODULE.validate_live_reference(lambda _args: closed))

    wrong = {**expected, "number": 1246, "html_url": "https://github.com/other/repo/issues/1246"}
    errors = MODULE.validate_live_reference(lambda _args: wrong)
    assert any("number must remain 1245" in error for error in errors)
    assert any("html_url must remain" in error for error in errors)

    pull_request = {**expected, "pull_request": {"url": "https://api.github.com/example"}}
    assert (
        "profile-engine live reference must remain an issue, not a pull request"
        in MODULE.validate_live_reference(lambda _args: pull_request)
    )


def test_gh_json_normalizes_timeout_and_spawn_errors(monkeypatch) -> None:
    def time_out(*_args, **_kwargs):
        raise MODULE.subprocess.TimeoutExpired(cmd=["gh", "api"], timeout=60)

    monkeypatch.setattr(MODULE.subprocess, "run", time_out)
    with pytest.raises(MODULE.AdjudicationError, match="GitHub query timed out after 60 seconds"):
        MODULE._gh_json(["api", "rate_limit"])

    def spawn_error(*_args, **_kwargs):
        raise OSError("gh unavailable")

    monkeypatch.setattr(MODULE.subprocess, "run", spawn_error)
    with pytest.raises(MODULE.AdjudicationError, match="cannot start GitHub query: gh unavailable"):
        MODULE._gh_json(["api", "rate_limit"])


def test_live_formalization_binds_latest_marked_receipts_and_observed_heads() -> None:
    calls = []

    def fetch(args):
        calls.append(args)
        endpoint = args[-1]
        issue_number = 2173 if "/2173" in endpoint else 2177
        work_id = "PSP-P02-W01" if issue_number == 2173 else "PSP-P02-W05"
        if "comments" not in endpoint:
            return {"state": "closed"}
        return [[_accepted_comment(work_id)]]

    assert MODULE.validate_live_dependencies(fetch) == []
    assert calls == [
        ["api", "repos/organvm/limen/issues/2173"],
        [
            "api",
            "--paginate",
            "--slurp",
            "repos/organvm/limen/issues/2173/comments?per_page=100",
        ],
        ["api", "repos/organvm/limen/issues/2177"],
        [
            "api",
            "--paginate",
            "--slurp",
            "repos/organvm/limen/issues/2177/comments?per_page=100",
        ],
    ]


def test_live_receipt_selection_includes_later_paginated_comments() -> None:
    def fetch(args):
        endpoint = args[-1]
        issue_number = 2173 if "/2173" in endpoint else 2177
        work_id = "PSP-P02-W01" if issue_number == 2173 else "PSP-P02-W05"
        if "comments" not in endpoint:
            return {"state": "closed"}
        accepted = _accepted_comment(work_id)
        marker = f"<!-- positioning-receipt:{work_id} -->"
        first_page = [
            {"id": index + 1, "html_url": f"https://example.test/{index + 1}", "body": "ordinary"}
            for index in range(99)
        ]
        first_page.append(
            {
                "id": accepted["id"] - 1,
                "html_url": "https://example.test/superseded",
                "body": f"{marker}\n```json\n{{}}\n```",
            }
        )
        return [first_page, [accepted]]

    assert MODULE.validate_live_dependencies(fetch) == []


def test_live_receipt_pagination_payloads_fail_neutrally() -> None:
    cases = (
        ("not-pages", "comment pagination must be a list of pages"),
        ([{"not": "a-page"}], "comment page[0] must be a list"),
        ([["not-a-comment"]], "comment page[0][0] must be a mapping"),
        ([[{"id": [], "body": "marked"}]], "comment page[0][0] needs a positive integer id"),
    )
    for payload, expected_error in cases:
        def fetch(args, value=payload):
            return value if "comments" in args[-1] else {"state": "closed"}

        assert any(expected_error in error for error in MODULE.validate_live_dependencies(fetch))


def test_contribution_observation_is_typed_and_bound_to_both_recorded_values() -> None:
    missing = _bundle()
    missing["receipt"] = copy.deepcopy(missing["receipt"])
    result = next(
        row
        for row in missing["receipt"]["api_query_receipts"]
        if row["id"] == "contribution_calendar_fresh_observation"
    )["result"]
    del result["total_contributions"]
    del result["sum_of_daily_counts"]
    assert "fresh contribution total and daily-count sum must be non-negative integers" in _errors(missing)

    arbitrary = _bundle()
    arbitrary["receipt"] = copy.deepcopy(arbitrary["receipt"])
    result = next(
        row
        for row in arbitrary["receipt"]["api_query_receipts"]
        if row["id"] == "contribution_calendar_fresh_observation"
    )["result"]
    result["total_contributions"] = 42
    result["sum_of_daily_counts"] = 42
    assert "fresh contribution total must preserve the recorded 33168 observation" in _errors(arbitrary)


def test_profile_metadata_result_is_exact_typed_and_reconciled() -> None:
    missing = _bundle()
    missing["receipt"] = copy.deepcopy(missing["receipt"])
    profile = next(
        row for row in missing["receipt"]["api_query_receipts"] if row["id"] == "profile_metadata"
    )
    profile.pop("result")
    assert "profile metadata result must match the exact typed public observation" in _errors(missing)

    arbitrary = _bundle()
    arbitrary["receipt"] = copy.deepcopy(arbitrary["receipt"])
    profile = next(
        row for row in arbitrary["receipt"]["api_query_receipts"] if row["id"] == "profile_metadata"
    )
    profile["result"]["public_repos"] = True
    errors = _errors(arbitrary)
    assert "profile metadata result must match the exact typed public observation" in errors
    assert (
        "profile metadata result must reconcile identity, repository count, blog claim, and tenure inputs"
        in errors
    )


def test_lavrea_axis_conclusions_match_the_accepted_exact_contract() -> None:
    bundle = _bundle()
    bundle["artifact"] = copy.deepcopy(bundle["artifact"])
    axis = bundle["artifact"]["lavrea_axis_audit"][0]
    axis["measurement_disposition"] = "arbitrary_but_nonempty"
    axis["inference_disposition"] = "arbitrary_but_nonempty"
    axis["primary_source_result"] = "Arbitrary but nonempty text."

    assert (
        "LAVREA axis contributions_year must match its accepted exact conclusion contract"
        in _errors(bundle)
    )


def test_public_profile_head_and_blobs_bind_cited_sources_and_latest_run() -> None:
    mismatched_head = _bundle()
    mismatched_head["receipt"] = copy.deepcopy(mismatched_head["receipt"])
    mismatched_head["receipt"]["public_profile"]["head"] = "a" * 40
    assert (
        "public-profile head must exactly match the cited README and manifest heads"
        in _errors(mismatched_head)
    )

    mismatched_blobs = _bundle()
    mismatched_blobs["receipt"] = copy.deepcopy(mismatched_blobs["receipt"])
    mismatched_blobs["receipt"]["public_profile"]["readme"]["blob"] = "a" * 40
    mismatched_blobs["receipt"]["public_profile"]["stats_manifest"]["blob"] = "b" * 40
    blob_errors = _errors(mismatched_blobs)
    assert "public-profile README blob must exactly match its cited source blob" in blob_errors
    assert "public-profile manifest blob must exactly match its cited source blob" in blob_errors

    mismatched_run = _bundle()
    mismatched_run["receipt"] = copy.deepcopy(mismatched_run["receipt"])
    mismatched_run["receipt"]["daily_generation_receipt"]["runs"][0]["resulting_head"] = "a" * 40
    assert (
        "public-profile head must exactly match the latest scheduled run resulting_head"
        in _errors(mismatched_run)
    )


def test_public_profile_and_nested_mappings_match_complete_typed_contract() -> None:
    assert MODULE._exact_typed_mapping(
        _bundle()["receipt"]["public_profile"],
        MODULE.EXPECTED_PUBLIC_PROFILE,
    )

    mutations = (
        (("repository",), "other-owner/profile"),
        (("readme", "url"), "https://example.test/readme"),
        (("readme", "authorization"), "Bearer SECRET"),
        (("stats_manifest", "rendered_values", "personal_public_repositories"), True),
        (("workflow", "url"), "https://example.test/workflow"),
    )
    for path, replacement in mutations:
        bundle = _bundle()
        bundle["receipt"] = copy.deepcopy(bundle["receipt"])
        target = bundle["receipt"]["public_profile"]
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = replacement

        assert (
            "public-profile receipt must match its complete exact typed contract"
            in _errors(bundle)
        )


def test_privacy_review_matches_complete_typed_public_safe_contract() -> None:
    assert MODULE._exact_typed_mapping(
        _bundle()["receipt"]["privacy_review"],
        MODULE.EXPECTED_PRIVACY_REVIEW,
    )

    mutations = (
        ("authorization", "Bearer SECRET"),
        ("accessToken", "opaque"),
        ("apiKey", "opaque"),
        ("clientSecret", "opaque"),
        ("privateKey", "opaque"),
        ("rule", "Only selected fields are inspected."),
        ("private_repository_names", False),
    )
    for key, replacement in mutations:
        bundle = _bundle()
        bundle["receipt"] = copy.deepcopy(bundle["receipt"])
        bundle["receipt"]["privacy_review"][key] = replacement

        assert (
            "privacy review must match its complete exact typed public-safe contract"
            in _errors(bundle)
        )


def test_entire_public_artifact_and_receipt_reject_credential_fields_recursively() -> None:
    baseline = _bundle()
    assert MODULE._credential_free_public_tree(baseline["artifact"])
    assert MODULE._credential_free_public_tree(baseline["receipt"])

    def mapping_paths(value, path=()):
        if isinstance(value, dict):
            yield path
            for key, child in value.items():
                yield from mapping_paths(child, path + (key,))
        elif isinstance(value, list):
            for index, child in enumerate(value):
                yield from mapping_paths(child, path + (index,))

    credential_keys = (
        "authorization",
        "accessToken",
        "apiKey",
        "clientSecret",
        "privateKey",
    )
    for root_name in ("artifact", "receipt"):
        for path in mapping_paths(baseline[root_name]):
            for credential_key in credential_keys:
                public_tree = copy.deepcopy(baseline[root_name])
                target = public_tree
                for key in path:
                    target = target[key]
                target[credential_key] = "opaque"

                assert not MODULE._credential_free_public_tree(public_tree)

    credentialed_value = _bundle()
    credentialed_value["artifact"] = copy.deepcopy(credentialed_value["artifact"])
    credentialed_value["artifact"]["reviewer_verdict"]["note"] = "api_key=SECRET"  # allow-secret
    assert "artifact must be recursively credential-free" in _errors(credentialed_value)


def test_organization_observations_are_exact_typed_ten_key_censuses() -> None:
    malformed = _bundle()
    malformed["receipt"] = copy.deepcopy(malformed["receipt"])
    original = next(
        row
        for row in malformed["receipt"]["api_query_receipts"]
        if row["id"] == "public_original_organization_repository_counts"
    )
    original["organization_count"] = 9
    original["counts"].pop("a-organvm")
    original["counts"]["organvm"] = True
    errors = _errors(malformed)

    assert (
        "API query receipt public_original_organization_repository_counts must contain the exact ten organization keys"
        in errors
    )
    assert (
        "API query receipt public_original_organization_repository_counts counts must be non-negative integers"
        in errors
    )
    assert (
        "API query receipt public_original_organization_repository_counts organization_count must be 10"
        in errors
    )


def test_api_receipts_require_exact_ids_public_metadata_and_no_credentials() -> None:
    malformed_set = _bundle()
    malformed_set["receipt"] = copy.deepcopy(malformed_set["receipt"])
    duplicate = copy.deepcopy(malformed_set["receipt"]["api_query_receipts"][0])
    extra = copy.deepcopy(duplicate)
    extra["id"] = "unexpected_public_query"
    malformed_set["receipt"]["api_query_receipts"].extend([duplicate, extra, "not-a-mapping"])
    errors = _errors(malformed_set)
    assert "API query receipt id profile_metadata is duplicated" in errors
    assert "receipt.api_query_receipts[7] must be a mapping" in errors
    assert "API query receipts must contain the exact unique expected ID set" in errors

    credentialed = _bundle()
    credentialed["receipt"] = copy.deepcopy(credentialed["receipt"])
    profile = credentialed["receipt"]["api_query_receipts"][0]
    profile["source"] = "https://api.github.com/users/4444J99?access_token=SECRET"
    profile["reproduction"] = "gh api users/4444J99 -H 'Authorization: Bearer SECRET'"
    profile["observed_at"] = "not-a-date"
    errors = _errors(credentialed)
    assert "API query receipt profile_metadata needs a credential-free HTTPS source" in errors
    assert "API query receipt profile_metadata needs an RFC3339 observation time" in errors
    assert (
        "API query receipt profile_metadata needs safe nonempty reproduction or query metadata"
        in errors
    )


def test_api_receipt_ids_bind_their_exact_expected_source_endpoints() -> None:
    assert set(MODULE.EXPECTED_API_RECEIPT_SOURCES) == MODULE.EXPECTED_API_RECEIPT_IDS
    for receipt_id in MODULE.EXPECTED_API_RECEIPT_SOURCES:
        bundle = _bundle()
        bundle["receipt"] = copy.deepcopy(bundle["receipt"])
        row = next(
            row
            for row in bundle["receipt"]["api_query_receipts"]
            if row["id"] == receipt_id
        )
        row["source"] = f"https://example.test/unrelated/{receipt_id}"

        assert (
            f"API query receipt {receipt_id} must bind its exact expected source endpoint"
            in _errors(bundle)
        )


def test_public_receipt_schemas_reject_credential_bearing_extra_fields() -> None:
    for receipt_id in MODULE.EXPECTED_API_RECEIPT_IDS:
        bundle = _bundle()
        bundle["receipt"] = copy.deepcopy(bundle["receipt"])
        row = next(
            row
            for row in bundle["receipt"]["api_query_receipts"]
            if row["id"] == receipt_id
        )
        row["authorization"] = "Bearer SECRET"

        assert any(
            f"API query receipt {receipt_id} must contain exactly" in error
            for error in _errors(bundle)
        )

    for receipt_id in MODULE.EXPECTED_HTTP_RECEIPTS:
        bundle = _bundle()
        bundle["receipt"] = copy.deepcopy(bundle["receipt"])
        row = next(
            row
            for row in bundle["receipt"]["http_receipts"]
            if row["id"] == receipt_id
        )
        row["authorization"] = "Bearer SECRET"

        assert any(
            f"HTTP receipt {receipt_id} must contain exactly" in error
            for error in _errors(bundle)
        )

    daily = _bundle()
    daily["receipt"] = copy.deepcopy(daily["receipt"])
    daily["receipt"]["daily_generation_receipt"]["authorization"] = "Bearer SECRET"
    assert (
        "daily generation receipt must contain its exact public field set"
        in _errors(daily)
    )

    run = _bundle()
    run["receipt"] = copy.deepcopy(run["receipt"])
    run["receipt"]["daily_generation_receipt"]["runs"][0]["authorization"] = (
        "Bearer SECRET"
    )
    assert (
        "every daily generation run must contain its exact public field set"
        in _errors(run)
    )


def test_projected_issue_numbers_are_positive_non_boolean_and_distinct() -> None:
    for invalid_number in (True, 0, -1):
        bundle = _bundle()
        bundle["issue_map"] = copy.deepcopy(bundle["issue_map"])
        bundle["receipt"] = copy.deepcopy(bundle["receipt"])
        work_ids = bundle["artifact"]["repository_drift_relay"]["affected_work_ids"]
        assert len(work_ids) == 18
        work_id = work_ids[0]
        bundle["issue_map"]["issues"][work_id]["number"] = invalid_number
        _sync_projected_issue_receipt(bundle)

        assert (
            f"{work_id} issue number must be a positive non-boolean integer"
            in _errors(bundle)
        )

    duplicate = _bundle()
    duplicate["issue_map"] = copy.deepcopy(duplicate["issue_map"])
    duplicate["receipt"] = copy.deepcopy(duplicate["receipt"])
    work_ids = duplicate["artifact"]["repository_drift_relay"]["affected_work_ids"]
    first_work_id, second_work_id = work_ids[:2]
    issue_number = duplicate["issue_map"]["issues"][first_work_id]["number"]
    duplicate["issue_map"]["issues"][second_work_id]["number"] = issue_number
    _sync_projected_issue_receipt(duplicate)

    assert (
        f"issue number {issue_number} is duplicated by {first_work_id} and {second_work_id}"
        in _errors(duplicate)
    )


def test_http_receipts_bind_url_time_status_and_reproduction() -> None:
    bundle = _bundle()
    bundle["receipt"] = copy.deepcopy(bundle["receipt"])
    row = bundle["receipt"]["http_receipts"][0]
    row["url"] = "https://example.test/"
    row["observed_at"] = "not-a-date"
    row["reproduction"] = "curl https://example.test/"

    errors = _errors(bundle)
    assert any("must bind the exact credential-free endpoint URL" in error for error in errors)
    assert any("needs an RFC3339 observation time" in error for error in errors)
    assert any("must safely reproduce the exact endpoint URL without credentials" in error for error in errors)

    for receipt_id, (expected_url, _status) in MODULE.EXPECTED_HTTP_RECEIPTS.items():
        credentialed_commands = (
            f"curl {expected_url} -H 'Authorization: Bearer SECRET'",
            f"curl --user alice:hunter2 {expected_url}",
            f"curl -ualice:hunter2 {expected_url}",
            f"curl --oauth2-bearer SECRET {expected_url}",
            f"curl --proxy-user alice:hunter2 {expected_url}",
            f"curl --proxy-header 'Proxy-Authorization: Basic SECRET' {expected_url}",
            f"curl --cert client.pem --key client.key {expected_url}",
        )
        for reproduction in credentialed_commands:
            credentialed = _bundle()
            credentialed["receipt"] = copy.deepcopy(credentialed["receipt"])
            row = next(
                row
                for row in credentialed["receipt"]["http_receipts"]
                if row["id"] == receipt_id
            )
            row["reproduction"] = reproduction

            assert (
                f"HTTP receipt {receipt_id} must safely reproduce the exact endpoint URL without credentials"
                in _errors(credentialed)
            )


def test_live_profile_observations_reproduce_all_moving_public_claim_inputs() -> None:
    now, public_payloads, contribution_payload = _live_profile_fixture()
    public_calls = []
    graphql_calls = []
    http_calls = []

    def public_fetch(url):
        public_calls.append(url)
        return copy.deepcopy(public_payloads[url])

    def gh_fetch(args):
        graphql_calls.append(args)
        return copy.deepcopy(contribution_payload)

    def http_fetch(url):
        http_calls.append(url)
        status = MODULE.EXPECTED_HTTP_RECEIPTS[
            next(
                receipt_id
                for receipt_id, (expected_url, _status) in MODULE.EXPECTED_HTTP_RECEIPTS.items()
                if expected_url == url
            )
        ][1]
        return {"status": status, "url": url}

    errors = MODULE.validate_live_profile_observations(
        _bundle()["receipt"],
        gh_fetch=gh_fetch,
        public_fetch=public_fetch,
        http_fetch=http_fetch,
        now=now,
    )

    assert errors == []
    assert set(public_calls) == set(public_payloads)
    assert graphql_calls == [
        ["api", "graphql", "-f", f"query={MODULE.PROFILE_CONTRIBUTION_QUERY}"]
    ]
    assert set(http_calls) == {
        url for url, _status in MODULE.EXPECTED_HTTP_RECEIPTS.values()
    }


def test_live_profile_window_ignores_older_failures_and_truncated_compare_commits() -> None:
    now, public_payloads, contribution_payload = _live_profile_fixture()
    runs = public_payloads[MODULE.PROFILE_RUNS_API_URL]["workflow_runs"]
    oldest_created = datetime.fromisoformat(runs[-1]["created_at"].replace("Z", "+00:00"))
    for offset in range(2):
        run_id = 8000 + offset
        created_at = oldest_created - timedelta(days=offset + 1)
        runs.append(
            {
                "id": run_id,
                "event": "schedule",
                "status": "completed",
                "conclusion": "failure",
                "created_at": _rfc3339(created_at),
                "updated_at": _rfc3339(created_at + timedelta(minutes=5)),
                "head_sha": f"{offset + 20:040x}",
                "html_url": (
                    f"https://github.com/{MODULE.PROFILE_REPOSITORY}/actions/runs/{run_id}"
                ),
            }
        )
    compare_url = next(url for url in public_payloads if "/compare/" in url)
    public_payloads[compare_url]["ahead_by"] = 500
    public_payloads[compare_url]["commits"] = [{"sha": "f" * 40}]

    errors = MODULE.validate_live_profile_observations(
        _bundle()["receipt"],
        gh_fetch=lambda _args: copy.deepcopy(contribution_payload),
        public_fetch=lambda url: copy.deepcopy(public_payloads[url]),
        http_fetch=lambda url: {
            "status": next(
                status
                for expected_url, status in MODULE.EXPECTED_HTTP_RECEIPTS.values()
                if expected_url == url
            ),
            "url": url,
        },
        now=now,
    )

    assert errors == []


def test_live_profile_accepts_transitive_scheduled_trigger_ancestry() -> None:
    now, public_payloads, contribution_payload = _live_profile_fixture()
    latest_trigger = public_payloads[MODULE.PROFILE_RUNS_API_URL]["workflow_runs"][0]["head_sha"]
    current_head = public_payloads[MODULE.PROFILE_MAIN_COMMIT_API_URL]["sha"]
    trigger_compare_url = (
        f"https://api.github.com/repos/{MODULE.PROFILE_REPOSITORY}/compare/"
        f"{latest_trigger}...{current_head}"
    )
    assert public_payloads[MODULE.PROFILE_MAIN_COMMIT_API_URL]["parents"] == [
        {"sha": "9" * 40}
    ]
    assert public_payloads[trigger_compare_url]["status"] == "ahead"
    assert public_payloads[trigger_compare_url]["ahead_by"] == 2

    errors = MODULE.validate_live_profile_observations(
        _bundle()["receipt"],
        gh_fetch=lambda _args: copy.deepcopy(contribution_payload),
        public_fetch=lambda url: copy.deepcopy(public_payloads[url]),
        http_fetch=lambda url: {
            "status": next(
                status
                for expected_url, status in MODULE.EXPECTED_HTTP_RECEIPTS.values()
                if expected_url == url
            ),
            "url": url,
        },
        now=now,
    )

    assert errors == []


def test_live_profile_observations_fail_neutrally_on_drift_and_malformed_payloads() -> None:
    now, public_payloads, contribution_payload = _live_profile_fixture()

    def validate(payloads, contribution=contribution_payload, http_statuses=None):
        statuses = http_statuses or {
            url: status for url, status in MODULE.EXPECTED_HTTP_RECEIPTS.values()
        }
        return MODULE.validate_live_profile_observations(
            _bundle()["receipt"],
            gh_fetch=lambda _args: copy.deepcopy(contribution),
            public_fetch=lambda url: copy.deepcopy(payloads[url]),
            http_fetch=lambda url: {"status": statuses[url], "url": url},
            now=now,
        )

    changed_profile = copy.deepcopy(public_payloads)
    changed_profile[MODULE.PROFILE_USER_API_URL]["public_repos"] = 9
    assert any(
        "live profile metadata public_repos must remain 8" in error
        for error in validate(changed_profile)
    )

    missing_runs = copy.deepcopy(public_payloads)
    missing_runs[MODULE.PROFILE_RUNS_API_URL] = {"workflow_runs": []}
    assert (
        "live profile workflow must expose eight recent successful scheduled runs"
        in validate(missing_runs)
    )

    changed_contribution = copy.deepcopy(contribution_payload)
    calendar = changed_contribution["data"]["user"]["contributionsCollection"][
        "contributionCalendar"
    ]
    calendar["totalContributions"] -= 1
    assert (
        "live contribution total must equal the sum of daily counts"
        in validate(public_payloads, changed_contribution)
    )

    changed_http = {
        url: 500 if index == 0 else status
        for index, (url, status) in enumerate(MODULE.EXPECTED_HTTP_RECEIPTS.values())
    }
    assert any(
        "live HTTP receipt" in error and "must remain" in error
        for error in validate(public_payloads, http_statuses=changed_http)
    )

    malformed = copy.deepcopy(public_payloads)
    malformed[MODULE.PROFILE_USER_API_URL] = []
    malformed[MODULE.PROFILE_MANIFEST_RAW_URL] = "not-a-mapping"
    malformed[MODULE.PROFILE_RUNS_API_URL] = None
    malformed[MODULE.PROFILE_MAIN_COMMIT_API_URL] = []
    compare_url = next(url for url in malformed if "/compare/" in url)
    malformed[compare_url] = "not-a-mapping"
    malformed_errors = validate(malformed, contribution=[])
    assert "live profile metadata response must be a mapping" in malformed_errors
    assert "live profile stats manifest response must be a mapping" in malformed_errors
    assert "live scheduled workflow response must be a mapping" in malformed_errors
    assert "live profile main-head response must be a mapping" in malformed_errors
    assert (
        "live contribution calendar response must contain the expected mapping"
        in malformed_errors
    )


def test_daily_runs_are_distinct_scheduled_and_window_bound() -> None:
    duplicate = _bundle()
    duplicate["receipt"] = copy.deepcopy(duplicate["receipt"])
    runs = duplicate["receipt"]["daily_generation_receipt"]["runs"]
    runs[1] = copy.deepcopy(runs[0])
    assert "daily generation runs must use distinct run IDs and URLs" in _errors(duplicate)

    wrong_event = _bundle()
    wrong_event["receipt"] = copy.deepcopy(wrong_event["receipt"])
    wrong_event["receipt"]["daily_generation_receipt"]["runs"][0]["event"] = "workflow_dispatch"
    assert any("must record event=schedule" in error for error in _errors(wrong_event))

    outside_window = _bundle()
    outside_window["receipt"] = copy.deepcopy(outside_window["receipt"])
    outside_window["receipt"]["daily_generation_receipt"]["runs"][0]["created_at"] = (
        "2026-08-11T08:05:20Z"
    )
    assert "daily generation run times must fall inside the observation window" in _errors(outside_window)


def test_issue_map_change_selects_the_bounded_live_research_adjudication_gate() -> None:
    gates = MODULE._load_yaml(ROOT / "institutio" / "governance" / "gates.yaml")
    gate = gates["gates"]["research-adjudication-test"]
    workflow = MODULE._load_yaml(ROOT / ".github" / "workflows" / "pr-gate.yml")

    assert ".github/workflows/pr-gate.yml" in gate["paths"]
    assert "institutio/positioning/github-map.json" in gate["paths"]
    assert "docs/positioning/claims-ledger.md" in gate["paths"]
    assert "docs/positioning/evidence/flagship-evidence.yaml" in gate["paths"]
    assert "docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json" in gate["paths"]
    assert gate["command"] == (
        "bash scripts/run-pytest-hermetic.sh cli/tests/test_positioning_program.py "
        "scripts/tests/test_positioning_research_adjudication.py -q && "
        "python3 scripts/positioning-research-adjudication.py --verify-live"
    )
    assert gate["command"].endswith(
        "python3 scripts/positioning-research-adjudication.py --verify-live"
    )
    assert gate["timeout_seconds"] == 300
    assert workflow["permissions"] == {"contents": "read", "issues": "read"}
    verification_steps = {
        step["name"]: step
        for step in workflow["jobs"]["pr-gate"]["steps"]
        if isinstance(step, dict) and "name" in step
    }
    for step_name in (
        "Verify implicated PR gates (scoped, CI mirrors deferred)",
        "Verify merge-group integration gates (scoped, fail-closed)",
        "Verify manual run (scoped)",
    ):
        assert verification_steps[step_name]["env"]["GH_TOKEN"] == "${{ github.token }}"
    fallback = verification_steps[
        "Full literal matrix (LIMEN_PRGATE_SCOPED=0 escape hatch)"
    ]
    assert fallback["env"]["GH_TOKEN"] == "${{ github.token }}"
    assert (
        "python3 scripts/positioning-research-adjudication.py --verify-live"
        in fallback["run"].splitlines()
    )
    assert (
        "bash scripts/run-pytest-hermetic.sh "
        "scripts/tests/test_positioning_research_adjudication.py -q"
        in fallback["run"].splitlines()
    )
    assert "GH_TOKEN" not in workflow["jobs"]["pr-gate"]["env"]
