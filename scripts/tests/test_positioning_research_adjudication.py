from __future__ import annotations

import copy
import importlib.machinery
import importlib.util
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


def _bundle():
    return {
        "artifact": MODULE._load_json(MODULE.ARTIFACT_PATH),
        "receipt": MODULE._load_json(MODULE.RECEIPT_PATH),
        "program": MODULE._load_yaml(MODULE.PROGRAM_PATH),
        "issue_map": MODULE._load_json(MODULE.ISSUE_MAP_PATH),
        "issue_index": MODULE.ISSUE_INDEX_PATH.read_text(encoding="utf-8"),
        "research_doc": MODULE.RESEARCH_DOC_PATH.read_text(encoding="utf-8"),
    }


def _errors(bundle):
    return MODULE.validate_bundle(
        bundle["artifact"],
        bundle["receipt"],
        bundle["program"],
        bundle["issue_map"],
        bundle["issue_index"],
        bundle["research_doc"],
    )


def test_tracked_adjudication_bundle_passes_static_contract() -> None:
    assert _errors(_bundle()) == []


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
