#!/usr/bin/env python3
"""Validate and live-check the public-safe PSP-C11 foundry preflight.

The live path inspects every repository owned by the authenticated user and
their organizations. Private repository facts stay in memory. Output contains
only aggregate private counts and opaque, per-snapshot private candidate IDs.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "docs/positioning/foundry/psp-c11/foundry-preflight-contract.json"
SNAPSHOT = ROOT / "docs/positioning/foundry/psp-c11/product-candidate-snapshot.json"
PUBLIC_PACKAGE = ROOT / "docs/positioning/foundry/psp-c11"
RELAY = ROOT / "docs/receipts/positioning/relays/2026-08-10-psp-c11-governed-foundry-preflight.md"
ESTATE = ROOT / "institutio/github/estate.yaml"

EXPECTED_ASSIGNMENTS = {
    "PSP-P13-W01": {"model": "gpt-5.4-mini", "effort": "low", "effect": "read"},
    "PSP-P13-W02": {"model": "gpt-5.6-terra", "effort": "high", "effect": "write"},
    "PSP-P13-W03": {"model": "gpt-5.6-sol", "effort": "xhigh", "effect": "write"},
    "PSP-P13-W04": {"model": "gpt-5.6-terra", "effort": "high", "effect": "write"},
    "PSP-P13-W05": {"model": "gpt-5.6-terra", "effort": "high", "effect": "write"},
    "PSP-P13-W06": {"model": "gpt-5.6-sol", "effort": "max", "effect": "write"},
    "PSP-P13-W07": {"model": "gpt-5.6-sol", "effort": "xhigh", "effect": "write"},
    "PSP-P13-W08": {"model": "gpt-5.6-sol", "effort": "max", "effect": "external"},
    "PSP-P13-W09": {"model": "gpt-5.6-terra", "effort": "high", "effect": "write"},
}
EXPECTED_CONDUCTOR = {"model": "gpt-5.6-sol", "effort": "max"}
EXPECTED_P02_CLOSURE = {
    "url": "https://github.com/organvm/limen/issues/2172",
    "accepted_main_head": "8faa5fb9899231ebf5f87e78bb171544c11b79d7",
    "marked_receipt": "https://github.com/organvm/limen/issues/2172#issuecomment-5270095170",
    "canonical_receipt_sha256": "f312ae3536ced23aa782701b4a437866707c2eec4b6b194ba05a735e2d8bb434",
}
EXPECTED_C02_SOURCES = {
    "c02_estate_census": {
        "url": "https://github.com/organvm/limen/pull/2305",
        "merge_commit": "10cf8476d5e88309c71d5fac25167ec7b7af59c4",
    },
    "c02_estate_classification": {
        "url": "https://github.com/organvm/limen/pull/2307",
        "merge_commit": "35134b95650a26185a58eb3b3a82632e5b80b5b2",
    },
}
EXPECTED_C03_CHECKPOINT = {
    "status": "accepted_through_w06",
    "accepted_head": "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec",
    "integration_pull_request": "https://github.com/organvm/limen/pull/2312",
    "current_offer_head": "b6af8086c9050634313f519c29a6dfcb922c3721",
    "closed_leaves": [f"PSP-P03-W{index:02d}" for index in range(1, 7)],
    "reader_gate": {
        "work_id": "PSP-P03-W07",
        "issue": "https://github.com/organvm/limen/issues/2188",
        "state": "open",
        "assignment": {"model": "gpt-5.4-mini", "effort": "low", "effect": "read"},
    },
}
EXPECTED_C10_SOURCE_BINDINGS = [
    {
        "id": "c05_delivery_relay",
        "target": "limen",
        "pull_request": 2315,
        "head": "bcb69fa25dc93fa15b5ec4d985d845067a58c307",
        "role": "delivery operating-system relay and public-safe acceptance boundary",
        "counts_as_closure": False,
    },
    {
        "id": "c05_private_templates",
        "target": "private_custody",
        "pull_request": 135,
        "head": "432c31ea6bcaf2c175b0fde08b6e1733fe4c2926",
        "role": "proposal, SOW, commercial-decision, and acceptance-closeout templates",
        "counts_as_closure": False,
    },
    {
        "id": "c09_qualification_relay",
        "target": "limen",
        "pull_request": 2322,
        "head": "03d5e8fcefd73249f8c7edf61ace31e98b6d73e0",
        "role": "qualification, CTA-routing, and conversion source lock",
        "counts_as_closure": False,
    },
    {
        "id": "c09_private_package",
        "target": "private_custody",
        "pull_request": 136,
        "head": "7e5715d813a20d7c7b7b68c2d2c2f808cc3909f9",
        "role": "private discovery, proposal, follow-up, and no-outcome controls",
        "counts_as_closure": False,
    },
    {
        "id": "c09_portfolio_package",
        "target": "portfolio",
        "pull_request": 222,
        "head": "da79fb63b9756b5cce0d42ed2a7722668854a228",
        "role": "public audit and conversion-path contract without publication",
        "counts_as_closure": False,
    },
]
EXPECTED_C10_INTEGRATION = {
    "pull_request": "https://github.com/organvm/limen/pull/2321",
    "head": "98e10060a31a69c3d6cfe54375c68fe298c6c53a",
    "receipt_sha256": "bcb248826040197de8ef143da48ff61234d2cb2f6d73962fbc424eb2848856e6",
    "source_bindings": EXPECTED_C10_SOURCE_BINDINGS,
    "counts_as_closure": False,
}
EXPECTED_PREPARED_CHUNKS = {
    "PSP-C04": {"closed": False, "limen_pr": 2313, "limen_head": "23712398c6586e005c303eff632604985cd0a25c"},
    "PSP-C05": {
        "closed": False,
        "limen_pr": 2315,
        "limen_head": "bcb69fa25dc93fa15b5ec4d985d845067a58c307",
        "private_pr": 135,
        "private_head": "432c31ea6bcaf2c175b0fde08b6e1733fe4c2926",
    },
    "PSP-C06": {
        "closed": False,
        "limen_pr": 2317,
        "limen_head": "b3c8dcb8ee461fad7be971efc0fc60ca27726668",
        "portfolio_pr": 221,
        "portfolio_head": "6cb7f291ef758d26d136620398c6e9c09f74d0ea",
        "visual_direction_state": "three_unselected",
    },
    "PSP-C07": {"closed": False, "limen_pr": 2318, "limen_head": "6ee6bd7d546a56474cf3bd38e06fad794ab7bc45"},
    "PSP-C08": {"closed": False, "limen_pr": 2316, "limen_head": "a7937bb1e122574edc5d9e9cb74e18538d2b86c5"},
    "PSP-C09": {
        "closed": False,
        "limen_pr": 2322,
        "limen_head": "03d5e8fcefd73249f8c7edf61ace31e98b6d73e0",
        "private_pr": 136,
        "private_head": "7e5715d813a20d7c7b7b68c2d2c2f808cc3909f9",
        "portfolio_pr": 222,
        "portfolio_head": "da79fb63b9756b5cce0d42ed2a7722668854a228",
    },
    "PSP-C10": {"closed": False, "limen_pr": 2321, "limen_head": EXPECTED_C10_INTEGRATION["head"]},
}

REQUIRED_STRUCTURES = {
    "revocable_operating_license",
    "performance_revenue_share",
    "performance_vesting_venture",
    "custody_preserving_management_mandate",
    "time_boxed_option_trial",
}
REQUIRED_GATES = {"HG-PUBLICATION-SEND", "HG-OPERATOR-TERMS", "HG-CONTRACT"}
HARD_DECLINE_FLAGS = {
    "requests_credentials_before_terms",
    "rejects_return_obligations",
    "concealed_material_conflict",
    "unlawful_operating_capacity",
}
HUMAN_REVIEW_FLAGS = {
    "unresolved_conflict",
    "unresolved_legal_capacity",
    "score_reference_conflict",
    "policy_exception_requested",
}
SAFE_ACCESS = {
    ("source", "public_metadata"),
    ("synthetic_trial", "invented_data_isolated_sandbox"),
}
FORBIDDEN_ACCESS = {
    "production_credentials",
    "customer_data",
    "production_data",
    "private_source",
    "repository_administration",
    "domain_control",
    "ip_license",
    "product_transfer_rights",
}


class PreflightError(RuntimeError):
    """Raised when the preflight would become incomplete, unsafe, or false."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PreflightError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"{path} must contain an object")
    return value


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise PreflightError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PreflightError(f"{path} must contain a mapping")
    return value


def _run_json(args: list[str], timeout: int = 180) -> Any:
    result = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "command failed").strip()
        raise PreflightError(message[:500])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise PreflightError("GitHub query returned invalid JSON") from exc


def _paginated_array(endpoint: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["gh", "api", "--paginate", endpoint],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=240,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "GitHub pagination failed").strip()
        raise PreflightError(message[:500])
    rows: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    payload = result.stdout
    position = 0
    while position < len(payload):
        while position < len(payload) and payload[position].isspace():
            position += 1
        if position >= len(payload):
            break
        try:
            page, position = decoder.raw_decode(payload, position)
        except json.JSONDecodeError as exc:
            raise PreflightError("GitHub pagination returned invalid JSON") from exc
        if not isinstance(page, list):
            raise PreflightError("GitHub pagination returned a non-list page")
        rows.extend(row for row in page if isinstance(row, dict))
    return rows


def collect_live_repositories() -> tuple[list[str], list[dict[str, Any]]]:
    organizations = _paginated_array("/user/orgs?per_page=100")
    organization_names = sorted(
        {str(row.get("login") or "").strip() for row in organizations if str(row.get("login") or "").strip()}
    )
    pages = [_paginated_array("/user/repos?affiliation=owner&per_page=100")]
    pages.extend(_paginated_array(f"/orgs/{owner}/repos?type=all&per_page=100") for owner in organization_names)
    repositories: dict[str, dict[str, Any]] = {}
    for page in pages:
        for row in page:
            full_name = str(row.get("full_name") or "").strip()
            if not full_name:
                raise PreflightError("live census returned a repository without full_name")
            if full_name in repositories:
                raise PreflightError("live census returned a duplicate repository identity")
            repositories[full_name] = row
    return organization_names, [repositories[key] for key in sorted(repositories)]


def _threshold_points(value: int, rules: list[dict[str, Any]]) -> int:
    points = 0
    for rule in rules:
        if value >= int(rule["minimum"]):
            points = max(points, int(rule["points"]))
    return points


def score_demand(row: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    if bool(row.get("private")):
        return {
            "score": 0,
            "tier": "E0",
            "evidence": ["no_approved_public_demand_evidence"],
            "next_experiment": "Owner-approved, consented problem interview or instrumented private test; no send from this preflight.",
            "stop_condition": "Park after two bounded experiments produce no approved E3-or-stronger evidence.",
        }
    points = model["metadata_points"]
    stars = int(row.get("stargazers_count") or 0)
    forks = int(row.get("forks_count") or 0)
    watchers = int(row.get("subscribers_count") or 0)
    score = min(
        int(model["metadata_cap"]),
        _threshold_points(stars, points["stars"])
        + _threshold_points(forks, points["forks"])
        + _threshold_points(watchers, points["watchers"]),
    )
    evidence: list[str] = []
    if stars:
        evidence.append(f"public_stars:{stars}")
    if forks:
        evidence.append(f"public_forks:{forks}")
    if watchers:
        evidence.append(f"public_watchers:{watchers}")
    if forks >= 1:
        tier = "E2"
        next_experiment = "Instrument activation and retention, then obtain consented user evidence."
    elif stars or watchers:
        tier = "E1"
        next_experiment = "Identify the problem behind public attention through consented interviews."
    else:
        tier = "E0"
        next_experiment = "Run a bounded problem interview or instrumented landing-page experiment after the send gate."
    return {
        "score": score,
        "tier": tier,
        "evidence": evidence or ["zero_observed_public_demand_signal"],
        "next_experiment": next_experiment,
        "stop_condition": "Park after two bounded experiments produce no approved E3-or-stronger evidence.",
    }


def _parse_timestamp(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)
    except ValueError:
        return None


def score_readiness(row: dict[str, Any], model: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    score = 5
    evidence = ["resolved_in_live_owned_estate"]
    if not bool(row.get("archived")):
        score += 5
        evidence.append("not_archived")
    if row.get("default_branch"):
        score += 5
        evidence.append("default_branch_present")
    pushed = _parse_timestamp(row.get("pushed_at"))
    if pushed:
        age_days = max(0, (now - pushed).days)
        if age_days <= 90:
            score += 5
            evidence.append("pushed_within_90_days")
        elif age_days <= 365:
            score += 3
            evidence.append("pushed_within_365_days")
    if not bool(row.get("private")) and isinstance(row.get("license"), dict) and row["license"].get("spdx_id"):
        score += 5
        evidence.append("public_license_metadata_present")
    if row.get("homepage"):
        score += 5
        evidence.append("homepage_present_deploy_intent_only")
    score = min(score, int(model["metadata_screen_cap"]))
    if bool(row.get("archived")):
        band = "park_archived"
    elif score >= 20:
        band = "diligence_required"
    else:
        band = "discovery_only"
    return {
        "metadata_screen_score": score,
        "band": band,
        "evidence": evidence,
        "unverified_dimensions": [
            "exact_head_build_test",
            "runtime_liveness",
            "security",
            "data_privacy",
            "ip_contributor_custody",
            "observability_return",
            "maintenance_owner_and_estimate",
        ],
        "custody_risk": "restricted_review_required" if bool(row.get("private")) else "medium_until_ip_data_review",
    }


def _opaque_private_rows(rows: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    keyed = sorted(
        ((hashlib.sha256(str(row["full_name"]).encode("utf-8")).hexdigest(), row) for row in rows),
        key=lambda item: item[0],
    )
    width = max(3, len(str(len(keyed))))
    return [(f"private-candidate-{index:0{width}d}", row) for index, (_, row) in enumerate(keyed, 1)]


def build_snapshot(
    contract: dict[str, Any],
    organizations: list[str],
    repositories: list[dict[str, Any]],
    observed_at: dt.datetime,
) -> dict[str, Any]:
    estate = load_yaml(ESTATE)
    product_names = [str(value) for value in ((estate.get("product_ledger") or {}).get("repos") or [])]
    if len(product_names) != len(set(product_names)):
        raise PreflightError("product ledger contains duplicate candidate keys")
    by_name: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for row in repositories:
        by_name[str(row.get("name") or "")].append(row)
    missing = [name for name in product_names if len(by_name.get(name, [])) == 0]
    ambiguous = [name for name in product_names if len(by_name.get(name, [])) > 1]
    if missing or ambiguous:
        raise PreflightError(
            f"candidate resolution failed: missing={len(missing)} ambiguous={len(ambiguous)}"
        )
    candidates = [by_name[name][0] for name in product_names]
    candidate_names = sorted(str(row["full_name"]) for row in candidates)
    identity_digest = hashlib.sha256("\n".join(candidate_names).encode("utf-8")).hexdigest()
    repository_digest = hashlib.sha256(
        "\n".join(sorted(str(row["full_name"]) for row in repositories)).encode("utf-8")
    ).hexdigest()
    public_rows = sorted((row for row in candidates if not bool(row.get("private"))), key=lambda row: str(row["full_name"]))
    private_rows = [row for row in candidates if bool(row.get("private"))]
    demand_model = contract["demand_model"]
    readiness_model = contract["readiness_model"]

    def render(candidate_id: str, row: dict[str, Any], public: bool) -> dict[str, Any]:
        demand = score_demand(row, demand_model)
        readiness = score_readiness(row, readiness_model, observed_at)
        disposition = "park"
        if not bool(row.get("archived")) and demand["score"] >= 20 and readiness["metadata_screen_score"] >= 15:
            disposition = "experiment"
        return {
            "candidate_id": candidate_id,
            "repository": str(row["full_name"]) if public else None,
            "visibility": "public" if public else "private",
            "current_state": "archived" if bool(row.get("archived")) else "active_repository",
            "demand": demand,
            "readiness": readiness,
            "preflight_disposition": disposition,
            "economics": {
                "status": "unpriced_public_preflight",
                "hypothesis": "Value, cost, and incentive units must be sourced privately before transfer consideration.",
                "runway": "not_approved",
                "transfer_trigger": "Demand, readiness, operator, custody, economics, terms, and return floors all pass.",
                "stop_condition": demand["stop_condition"],
            },
            "transfer_eligible": False,
            "blocking_evidence": [
                "no_E3_or_stronger_primary_demand_receipt",
                "no_full_technical_readiness_receipt",
                "no_operator_selected_or_scored",
                "human_terms_and_contract_gates_unpulled",
                "no_observed_pilot",
            ],
        }

    rendered = [render(str(row["full_name"]), row, True) for row in public_rows]
    rendered.extend(render(candidate_id, row, False) for candidate_id, row in _opaque_private_rows(private_rows))
    counts = collections.Counter(row["visibility"] for row in rendered)
    dispositions = collections.Counter(row["preflight_disposition"] for row in rendered)
    demand_tiers = collections.Counter(row["demand"]["tier"] for row in rendered)
    readiness_bands = collections.Counter(row["readiness"]["band"] for row in rendered)
    repository_owner_counts = collections.Counter(str(row["owner"]["login"]) for row in repositories)
    for organization in organizations:
        repository_owner_counts.setdefault(organization, 0)
    source_rows = {
        str(source.get("id")): source
        for source in contract["live_sources"]
        if isinstance(source, dict)
    }
    source_ids = contract["candidate_inventory"]["source_ids"]
    return {
        "schema_version": "limen.psp_c11_product_candidate_snapshot.v1",
        "status": "PREPARED/PREFLIGHT",
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "sources": [source_rows[source_id]["url"] for source_id in source_ids],
        "census": {
            "organization_count": len(organizations),
            "organization_roster": organizations,
            "repository_count": len(repositories),
            "repository_owner_counts": dict(sorted(repository_owner_counts.items())),
            "repository_identity_sha256": repository_digest,
        },
        "candidate_denominator": {
            "count": len(rendered),
            "visibility": dict(sorted(counts.items())),
            "identity_sha256": identity_digest,
            "private_identity_rule": "Opaque per-snapshot IDs; private names and owner-specific row identities are not persisted.",
        },
        "score_distribution": {
            "demand_tiers": dict(sorted(demand_tiers.items())),
            "readiness_bands": dict(sorted(readiness_bands.items())),
            "preflight_dispositions": dict(sorted(dispositions.items())),
            "transfer_eligible": 0,
        },
        "candidates": rendered,
    }


def _operator_score(case: dict[str, Any], profile: dict[str, Any]) -> tuple[int, str]:
    scores = case.get("scores") or {}
    dimensions = profile["dimensions"]
    expected = {str(row["id"]) for row in dimensions}
    if set(scores) != expected:
        raise PreflightError(f"{case.get('id')}: operator score dimensions do not match the contract")
    for name, value in scores.items():
        if not isinstance(value, int) or value < 0 or value > 5:
            raise PreflightError(f"{case.get('id')}: {name} must be an integer from 0 through 5")
    flags = set(case.get("flags") or [])
    if flags & HARD_DECLINE_FLAGS:
        return 0, "decline"
    if flags & HUMAN_REVIEW_FLAGS:
        weighted = round(sum(int(row["weight"]) * int(scores[row["id"]]) / 5 for row in dimensions))
        return weighted, "human_review"
    weighted = round(sum(int(row["weight"]) * int(scores[row["id"]]) / 5 for row in dimensions))
    for route in profile["routes"]:
        if weighted >= int(route["minimum"]):
            return weighted, str(route["route"])
    raise PreflightError("operator route table has no fallback")


def _access_decision(drill: dict[str, Any]) -> str:
    requested = str(drill.get("requested") or "")
    if requested in FORBIDDEN_ACCESS:
        return "deny"
    if (str(drill.get("stage") or ""), requested) in SAFE_ACCESS:
        return "allow"
    return "deny"


def run_synthetic_drills(contract: dict[str, Any]) -> dict[str, Any]:
    operator_results = []
    for case in contract["synthetic_cases"]:
        score, route = _operator_score(case, contract["operator_profile"])
        operator_results.append(
            {
                "case_id": case["id"],
                "score": score,
                "route": route,
                "expected_route": case["expected_route"],
                "pass": route == case["expected_route"],
            }
        )
    access_results = []
    for drill in contract["synthetic_access_drills"]:
        decision = _access_decision(drill)
        access_results.append(
            {
                "drill_id": drill["id"],
                "decision": decision,
                "expected": drill["expected"],
                "pass": decision == drill["expected"],
            }
        )
    lifecycle = [
        {"step": "inventory", "artifact": "invented_product", "external_effect": False},
        {"step": "score", "artifact": "invented_evidence", "external_effect": False},
        {"step": "diligence", "artifact": "invented_operator", "external_effect": False},
        {"step": "synthetic_trial", "artifact": "invented_data_isolated_sandbox", "external_effect": False},
        {"step": "return_rehearsal", "artifact": "sandbox_destroyed_no_live_access", "external_effect": False},
        {"step": "governance_review", "artifact": "synthetic_decision_receipt", "external_effect": False},
    ]
    passed = all(row["pass"] for row in operator_results + access_results)
    predecessor = contract["dependency_boundary"]["formal_predecessor"]
    return {
        "schema_version": "limen.psp_c11_synthetic_drill_receipt.v2",
        "status": "pass" if passed else "fail",
        "synthetic_only": True,
        "human_acceptance_simulated": False,
        "external_effects": [],
        "operator_cases": operator_results,
        "access_drills": access_results,
        "lifecycle_replay": lifecycle,
        "final_custody": "owner_unchanged",
        "observed_pilot": False,
        "source_lock": {
            "chunk_id": predecessor["chunk_id"],
            "head": predecessor["exact_head"],
            "receipt_sha256": predecessor["receipt_sha256"],
            "source_bindings": predecessor["source_bindings"],
            "counts_as_closure": predecessor["counts_as_closure"],
        },
    }


def validate_contract(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("status") != "PREPARED/PREFLIGHT":
        errors.append("contract status must remain PREPARED/PREFLIGHT")
    if contract.get("chunk_id") != "PSP-C11" or contract.get("phase_id") != "PSP-P13":
        errors.append("contract must remain bound to PSP-C11 / PSP-P13")
    if contract.get("schema_version") != "limen.psp_c11_foundry_preflight.v2":
        errors.append("contract schema must remain at reconciled v2")
    if contract.get("reconciled_at") != "2026-08-12":
        errors.append("contract reconciliation date drift")
    if contract.get("conductor") != EXPECTED_CONDUCTOR:
        errors.append("C11 conductor assignment drift")
    if contract.get("leaf_assignments") != EXPECTED_ASSIGNMENTS:
        errors.append("leaf model, effort, or effect assignment drift")
    live_sources = {row.get("id"): row for row in contract.get("live_sources", []) if isinstance(row, dict)}
    if set(live_sources) != {"p02_closure", *EXPECTED_C02_SOURCES}:
        errors.append("live source set must contain only P02 closure and the two accepted C02 inputs")
    p02 = live_sources.get("p02_closure") or {}
    if (
        p02.get("state") != "closed"
        or any(p02.get(key) != value for key, value in EXPECTED_P02_CLOSURE.items())
    ):
        errors.append("P02 closure must remain bound to its accepted main head and marked receipt")
    for source_id, expected in EXPECTED_C02_SOURCES.items():
        source = live_sources.get(source_id) or {}
        if (
            source.get("state") != "merged"
            or source.get("url") != expected["url"]
            or source.get("merge_commit") != expected["merge_commit"]
        ):
            errors.append(f"{source_id} must remain bound to its accepted merged commit")
    dependency_value = contract.get("dependency_boundary")
    if not isinstance(dependency_value, dict):
        errors.append("dependency boundary must be an object")
        dependency: dict[str, Any] = {}
    else:
        dependency = dependency_value
    predecessor = dependency.get("formal_predecessor") or {}
    if not isinstance(predecessor, dict) or predecessor.get("chunk_id") != "PSP-C10":
        errors.append("C10 predecessor checkpoint is malformed")
    elif predecessor.get("prepared") is not True or predecessor.get("closed") is not False:
        errors.append("C10 must remain prepared but not closed")
    elif (
        predecessor.get("pull_request") != "https://github.com/organvm/limen/pull/2321"
        or predecessor.get("exact_head") != EXPECTED_PREPARED_CHUNKS["PSP-C10"]["limen_head"]
    ):
        errors.append("C10 predecessor checkpoint head drift")
    integration = {
        "pull_request": predecessor.get("pull_request"),
        "head": predecessor.get("exact_head"),
        "receipt_sha256": predecessor.get("receipt_sha256"),
        "source_bindings": predecessor.get("source_bindings"),
        "counts_as_closure": predecessor.get("counts_as_closure"),
    }
    if integration != EXPECTED_C10_INTEGRATION:
        errors.append("C10 integrated readiness source-lock drift")
    if dependency.get("ready_work_observation") != "no_psp_c11_leaf_ready":
        errors.append("C11 ready-work observation drift")
    if dependency.get("c03_checkpoint") != EXPECTED_C03_CHECKPOINT:
        errors.append("C03 accepted checkpoint or reader gate drift")
    phase_value = dependency.get("phase_dependencies")
    phase_dependencies = phase_value if isinstance(phase_value, dict) else {}
    if not isinstance(phase_value, dict):
        errors.append("phase dependency checkpoints must be an object")
    p02_phase = phase_dependencies.get("PSP-P02") or {}
    if (
        not isinstance(p02_phase, dict)
        or p02_phase.get("closed") is not True
        or p02_phase.get("issue") != EXPECTED_P02_CLOSURE["url"]
        or p02_phase.get("accepted_main_head") != EXPECTED_P02_CLOSURE["accepted_main_head"]
    ):
        errors.append("P02 closure checkpoint is missing")
    for phase_id in ("PSP-P04", "PSP-P11", "PSP-P12"):
        phase = phase_dependencies.get(phase_id) or {}
        if not isinstance(phase, dict) or phase.get("closed") is not False:
            errors.append(f"{phase_id} must remain unsatisfied in C11 preflight")
    if dependency.get("prepared_chunks") != EXPECTED_PREPARED_CHUNKS:
        errors.append("C04-C10 prepared checkpoint heads drift")
    inventory = contract.get("candidate_inventory") or {}
    if inventory.get("source_ids") != list(EXPECTED_C02_SOURCES):
        errors.append("candidate inventory sources must be the two accepted C02 inputs only")
    estate = load_yaml(ESTATE)
    product_count = len(((estate.get("product_ledger") or {}).get("repos") or []))
    if inventory.get("expected_candidate_count") != product_count:
        errors.append("candidate denominator does not match the canonical product ledger")
    profile = contract.get("operator_profile") or {}
    dimensions = profile.get("dimensions") or []
    if sum(int(row.get("weight") or 0) for row in dimensions) != 100:
        errors.append("operator profile weights must sum to 100")
    structures = {row.get("id") for row in contract.get("structure_options", []) if isinstance(row, dict)}
    if structures != REQUIRED_STRUCTURES:
        errors.append("structure option set is incomplete")
    for structure in contract.get("structure_options", []):
        if not structure.get("mandatory_boundaries") or not structure.get("return"):
            errors.append(f"structure {structure.get('id', '<unknown>')} lacks boundaries or return path")
    gates = {row.get("id"): row for row in contract.get("human_gates", []) if isinstance(row, dict)}
    if set(gates) != REQUIRED_GATES:
        errors.append("human gate set is incomplete or duplicated")
    if any(row.get("state") != "unpulled" for row in gates.values()):
        errors.append("all human gates must remain unpulled in preflight")
    pilot = contract.get("bounded_pilot") or {}
    false_fields = {
        "product_selected",
        "operator_selected",
        "operator_recruited",
        "terms_selected",
        "terms_signed",
        "rights_transferred",
        "credentials_granted",
        "production_access_granted",
        "observed_pilot",
    }
    for field in sorted(false_fields):
        if pilot.get(field) is not False:
            errors.append(f"bounded_pilot.{field} must remain false")
    if pilot.get("status") != "DESIGN_ONLY/UNOBSERVED":
        errors.append("pilot status must remain DESIGN_ONLY/UNOBSERVED")
    try:
        drills = run_synthetic_drills(contract)
        if drills["status"] != "pass":
            errors.append("synthetic drill expectations do not match the contract")
    except PreflightError as exc:
        errors.append(str(exc))
    return errors


def validate_snapshot(snapshot: dict[str, Any], contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if snapshot.get("status") != "PREPARED/PREFLIGHT":
        errors.append("snapshot status must remain PREPARED/PREFLIGHT")
    source_rows = {
        str(row.get("id")): row
        for row in contract.get("live_sources", [])
        if isinstance(row, dict)
    }
    expected_sources = [
        source_rows[source_id].get("url")
        for source_id in contract.get("candidate_inventory", {}).get("source_ids", [])
        if source_id in source_rows
    ]
    if snapshot.get("sources") != expected_sources:
        errors.append("snapshot sources must contain only the accepted inventory inputs")
    candidates = snapshot.get("candidates") or []
    expected = int(contract["candidate_inventory"]["expected_candidate_count"])
    if len(candidates) != expected or snapshot.get("candidate_denominator", {}).get("count") != expected:
        errors.append("snapshot candidate denominator is incomplete")
    ids = [row.get("candidate_id") for row in candidates if isinstance(row, dict)]
    if len(ids) != len(set(ids)):
        errors.append("snapshot candidate IDs are not unique")
    for row in candidates:
        candidate_id = str(row.get("candidate_id") or "<unknown>")
        visibility = row.get("visibility")
        repository = row.get("repository")
        if visibility == "private":
            if repository is not None or not candidate_id.startswith("private-candidate-"):
                errors.append(f"{candidate_id}: private row exposes an identity")
        elif visibility == "public":
            if not isinstance(repository, str) or "/" not in repository:
                errors.append(f"{candidate_id}: public row lacks a repository")
        else:
            errors.append(f"{candidate_id}: invalid visibility")
        demand = row.get("demand") or {}
        readiness = row.get("readiness") or {}
        economics = row.get("economics") or {}
        if not demand.get("evidence") or not demand.get("next_experiment") or not demand.get("stop_condition"):
            errors.append(f"{candidate_id}: demand evidence contract is incomplete")
        if not readiness.get("unverified_dimensions") or not readiness.get("custody_risk"):
            errors.append(f"{candidate_id}: readiness/custody contract is incomplete")
        if not economics.get("hypothesis") or not economics.get("transfer_trigger") or not economics.get("stop_condition"):
            errors.append(f"{candidate_id}: economics contract is incomplete")
        if row.get("transfer_eligible") is not False:
            errors.append(f"{candidate_id}: preflight cannot mark a candidate transfer-eligible")
    return errors


def private_name_leaks(private_names: set[str]) -> list[str]:
    paths = sorted(PUBLIC_PACKAGE.rglob("*")) if PUBLIC_PACKAGE.exists() else []
    if RELAY.is_file():
        paths.append(RELAY)
    leaks: set[str] = set()
    repository_character = r"A-Za-z0-9_.-"
    for path in paths:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for name in private_names:
            if re.search(rf"(?<![{repository_character}]){re.escape(name)}(?![{repository_character}])", text):
                leaks.add(str(path.relative_to(ROOT)))
    return sorted(leaks)


def compare_live_snapshot(snapshot: dict[str, Any], live: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for path in (
        ("census", "organization_count"),
        ("census", "organization_roster"),
        ("census", "repository_count"),
        ("census", "repository_owner_counts"),
        ("census", "repository_identity_sha256"),
        ("candidate_denominator", "count"),
        ("candidate_denominator", "visibility"),
        ("candidate_denominator", "identity_sha256"),
        ("score_distribution",),
        ("candidates",),
    ):
        old: Any = snapshot
        new: Any = live
        for key in path:
            old = old.get(key) if isinstance(old, dict) else None
            new = new.get(key) if isinstance(new, dict) else None
        if old != new:
            errors.append(f"live snapshot drift at {'.'.join(path)}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=CONTRACT)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--live", action="store_true", help="run two complete owner-wide censuses and emit a public-safe snapshot")
    parser.add_argument("--verify-live-snapshot", action="store_true", help="compare the tracked identity/visibility denominator to two live passes")
    parser.add_argument("--drills", action="store_true", help="emit synthetic operator, access, return, and governance drill results")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        contract = load_json(args.contract)
        errors = validate_contract(contract)
        snapshot = load_json(args.snapshot) if args.snapshot.is_file() else None
        if snapshot is not None:
            errors.extend(validate_snapshot(snapshot, contract))
        if args.drills:
            result = run_synthetic_drills(contract)
            if errors:
                result["status"] = "fail"
                result["errors"] = errors
            print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"].upper())
            return 1 if errors or result["status"] != "pass" else 0
        if args.live or args.verify_live_snapshot:
            organizations_1, repositories_1 = collect_live_repositories()
            organizations_2, repositories_2 = collect_live_repositories()
            identities_1 = {str(row["full_name"]) for row in repositories_1}
            identities_2 = {str(row["full_name"]) for row in repositories_2}
            if organizations_1 != organizations_2 or identities_1 != identities_2:
                raise PreflightError("two live owner-wide census passes produced different identity sets")
            observed_at = dt.datetime.now(dt.UTC)
            live = build_snapshot(contract, organizations_2, repositories_2, observed_at)
            live["two_pass_receipt"] = {
                "pass_1_repository_identity_sha256": hashlib.sha256(
                    "\n".join(sorted(identities_1)).encode("utf-8")
                ).hexdigest(),
                "pass_2_repository_identity_sha256": hashlib.sha256(
                    "\n".join(sorted(identities_2)).encode("utf-8")
                ).hexdigest(),
                "new_organization_keys": 0,
                "new_repository_keys": 0,
                "new_candidate_keys": 0,
            }
            private_names = {str(row["full_name"]) for row in repositories_2 if bool(row.get("private"))}
            public_bare_names = {
                str(row.get("name") or "") for row in repositories_2 if not bool(row.get("private"))
            }
            private_unique_bare_names = {
                str(row.get("name") or "")
                for row in repositories_2
                if bool(row.get("private")) and str(row.get("name") or "") not in public_bare_names
            }
            leaks = private_name_leaks(private_names | private_unique_bare_names)
            if leaks:
                errors.append(f"private repository identity leaked into public C11 path(s): {', '.join(leaks)}")
            if args.verify_live_snapshot:
                if snapshot is None:
                    errors.append("tracked snapshot is missing")
                else:
                    errors.extend(compare_live_snapshot(snapshot, live))
            if errors:
                live["status"] = "fail"
                live["errors"] = errors
            output = live
            if args.verify_live_snapshot:
                output = {
                    "schema_version": "limen.psp_c11_live_snapshot_verification.v1",
                    "status": "fail" if errors else "pass",
                    "observed_at": live["observed_at"],
                    "census": live["census"],
                    "candidate_denominator": live["candidate_denominator"],
                    "score_distribution": live["score_distribution"],
                    "two_pass_receipt": live["two_pass_receipt"],
                    "tracked_snapshot_match": not any(error.startswith("live snapshot drift") for error in errors),
                    "privacy_scan": {
                        "private_repository_count": len(private_names),
                        "scanned_paths": [
                            str(PUBLIC_PACKAGE.relative_to(ROOT)),
                            str(RELAY.relative_to(ROOT)),
                        ],
                        "leak_count": len(leaks),
                    },
                    "errors": errors,
                }
            print(json.dumps(output, indent=2, sort_keys=True) if args.json else output["status"])
            return 1 if errors else 0
        result = {
            "schema_version": "limen.psp_c11_foundry_preflight_validation.v1",
            "status": "pass" if not errors else "fail",
            "contract": str(args.contract.relative_to(ROOT)),
            "snapshot": str(args.snapshot.relative_to(ROOT)) if snapshot is not None else None,
            "errors": errors,
            "synthetic_drills": run_synthetic_drills(contract),
        }
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else result["status"].upper())
        return 1 if errors else 0
    except (PreflightError, OSError, KeyError, TypeError, ValueError) as exc:
        result = {"status": "fail", "errors": [str(exc)]}
        print(json.dumps(result, indent=2, sort_keys=True) if args.json else f"FAIL: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
