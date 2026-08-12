from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
import json
from pathlib import Path


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


def _bundle():
    return {
        "artifact": MODULE._load_json(MODULE.ARTIFACT_PATH),
        "receipt": MODULE._load_json(MODULE.RECEIPT_PATH),
        "program": MODULE._load_yaml(MODULE.PROGRAM_PATH),
        "issue_map": MODULE._load_json(MODULE.ISSUE_MAP_PATH),
        "issue_index": MODULE.ISSUE_INDEX_PATH.read_text(encoding="utf-8"),
        "research_doc": MODULE.RESEARCH_DOC_PATH.read_text(encoding="utf-8"),
        "flagship_evidence": MODULE._load_yaml(MODULE.FLAGSHIP_EVIDENCE_PATH),
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
        bundle["claims_ledger"],
    )


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
            "permissions": {"admin": True},
        }

    assert MODULE.validate_live_identity(bundle["program"], fetch) == []
    assert calls == [["api", f"repositories/{MODULE.PORTFOLIO_REPOSITORY_ID}"]]


def test_live_identity_rejects_non_mapping_transport_payloads_neutrally() -> None:
    program = _bundle()["program"]

    for payload in ([], "not-an-object", 42):
        assert MODULE.validate_live_identity(program, lambda _args, value=payload: value) == [
            "stable repository identity response must be a mapping"
        ]

    malformed_permissions = {
        "id": MODULE.PORTFOLIO_REPOSITORY_ID,
        "full_name": MODULE.PORTFOLIO_CANONICAL_SLUG,
        "visibility": "public",
        "private": False,
        "default_branch": "main",
        "archived": False,
        "permissions": [],
    }
    assert MODULE.validate_live_identity(program, lambda _args: malformed_permissions) == [
        "stable repository identity permissions must be a mapping"
    ]


def test_live_formalization_binds_latest_marked_receipts_and_observed_heads() -> None:
    calls = []

    def fetch(args):
        calls.append(args)
        issue_number = 2173 if "/2173" in args[1] else 2177
        work_id = "PSP-P02-W01" if issue_number == 2173 else "PSP-P02-W05"
        if "comments" not in args[1]:
            return {"state": "closed"}
        receipt = _accepted_receipt(work_id)
        expected = MODULE.ACCEPTED_DEPENDENCIES[work_id]
        assert MODULE._canonical_sha256(receipt) == expected["canonical_receipt_sha256"]
        return [
            {
                "id": int(expected["marked_receipt"].rsplit("-", 1)[1]),
                "html_url": expected["marked_receipt"],
                "body": (
                    f"<!-- positioning-receipt:{work_id} -->\n"
                    f"```json\n{json.dumps(receipt, indent=2)}\n```"
                ),
            }
        ]

    assert MODULE.validate_live_dependencies(fetch) == []
    assert calls == [
        ["api", "repos/organvm/limen/issues/2173"],
        ["api", "repos/organvm/limen/issues/2173/comments?per_page=100"],
        ["api", "repos/organvm/limen/issues/2177"],
        ["api", "repos/organvm/limen/issues/2177/comments?per_page=100"],
    ]


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
    assert any("must reproduce the exact endpoint URL" in error for error in errors)


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


def test_issue_map_change_selects_the_research_adjudication_gate() -> None:
    gates = MODULE._load_yaml(ROOT / "institutio" / "governance" / "gates.yaml")
    gate = gates["gates"]["research-adjudication-test"]

    assert "institutio/positioning/github-map.json" in gate["paths"]
    assert "docs/positioning/claims-ledger.md" in gate["paths"]
    assert "docs/positioning/evidence/flagship-evidence.yaml" in gate["paths"]
    assert "docs/receipts/psp-p02-w01-estate-census-preflight-20260810.json" in gate["paths"]
