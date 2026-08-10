#!/usr/bin/env python3
"""Validate the PSP-P02-W04/W05 public flagship evidence packets.

The static mode proves packet shape, public-only custody boundaries, metric declarations, and the
W03 -> W04 -> W05 completion order. ``--verify-live`` additionally checks the public workflow
receipts, endpoint status, JSON observations, and visible corroborating terms.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/positioning/evidence/flagship-evidence.yaml"
MATRIX = ROOT / "docs/positioning/flagship-proof-set.yaml"
CLAIMS_LEDGER = ROOT / "docs/positioning/claims-ledger.md"
SCHEMA = "limen.positioning_flagship_evidence.v1"
EXPECTED_IDS = {"limen", "public_records", "ai_chat_exporter"}
EXPECTED_W08_SOURCE_HEAD = "96d0ac9e8755c1b7ed9ecf49a82b54b501f7a4aa"
EXPECTED_W08_CLAIM_IDS = {
    "lavrea-top-01-throughput",
    "lavrea-top-1-python-full-stack",
    "profile-contributions-last-year",
    "profile-daily-regeneration",
    "profile-federation-coverage",
    "profile-has-no-proof",
    "profile-limen-operating-proof",
    "profile-one-creator-authorship",
    "profile-portfolio-link",
    "profile-production-systems-headline",
    "profile-public-repository-counts",
    "profile-universal-production-claim",
    "profile-zero-manual-upkeep",
}
W08_LAYER_KEYS = {"measurement", "inference", "implication", "prominence"}
ALLOWED_PUBLIC_HOSTS = frozenset(
    {
        "api.github.com",
        "github.com",
        "limen-dashboard.pages.dev",
        "organvm-iii-ergon.github.io",
    }
)
MAX_RESPONSE_BYTES = 2_000_000


class EvidenceError(RuntimeError):
    """Raised for invalid public evidence or an unavailable public anchor."""


def validate_public_fetch_url(value: object) -> str:
    if not isinstance(value, str) or value != value.strip():
        raise EvidenceError("public anchor must be a normalized HTTPS URL")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise EvidenceError("public anchor URL is malformed") from exc
    if (
        parsed.scheme != "https"
        or parsed.hostname not in ALLOWED_PUBLIC_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
    ):
        raise EvidenceError("public anchor must use a credential-free selected public host")
    return value


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201
        validate_public_fetch_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


SAFE_OPENER = urllib.request.build_opener(_SafeRedirectHandler())


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise EvidenceError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{path} must contain a mapping")
    return value


def nested_value(value: object, path: str) -> object:
    current = value
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            raise EvidenceError(f"JSON observation path is absent: {path}")
        current = current[key]
    return current


def fetch(url: str) -> tuple[int, bytes]:
    url = validate_public_fetch_url(url)
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "limen-evidence-verifier"})
    try:
        with SAFE_OPENER.open(request, timeout=20) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise EvidenceError(f"public anchor exceeds {MAX_RESPONSE_BYTES} bytes")
            return response.status, payload
    except urllib.error.HTTPError as exc:
        payload = exc.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise EvidenceError(f"public anchor error body exceeds {MAX_RESPONSE_BYTES} bytes") from exc
        return exc.code, payload
    except urllib.error.URLError as exc:
        raise EvidenceError(f"public anchor unavailable: {url}: {exc.reason}") from exc


def selected_repositories(matrix: dict[str, Any]) -> dict[str, str]:
    selected: dict[str, str] = {}
    for row in matrix.get("candidates", []):
        if not isinstance(row, dict) or row.get("status") != "selected":
            continue
        identifier = row.get("id")
        repository = row.get("repository")
        if isinstance(identifier, str) and isinstance(repository, str):
            selected[identifier] = repository
    return selected


def validate_w08_import(index: dict[str, Any], ledger_text: str) -> list[str]:
    errors: list[str] = []
    imported = index.get("w08_research_import")
    if not isinstance(imported, dict):
        return ["w08_research_import must be a mapping"]
    if imported.get("source_head") != EXPECTED_W08_SOURCE_HEAD:
        errors.append("W08 import must bind the reviewed immutable source head")
    if imported.get("claim_count") != len(EXPECTED_W08_CLAIM_IDS):
        errors.append("W08 import claim_count must equal the 13-claim denominator")
    claims = imported.get("claims")
    if not isinstance(claims, list):
        return errors + ["W08 import claims must be a list"]
    identifiers = [claim.get("id") for claim in claims if isinstance(claim, dict)]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != EXPECTED_W08_CLAIM_IDS:
        errors.append("W08 import must classify each ratified claim exactly once")
    for claim in claims:
        if not isinstance(claim, dict):
            errors.append("every W08 import claim must be a mapping")
            continue
        identifier = str(claim.get("id") or "claim")
        layers = claim.get("layers")
        if not isinstance(layers, dict) or set(layers) != W08_LAYER_KEYS:
            errors.append(f"{identifier}: W08 import must preserve all four adjudication layers")
            continue
        if any(not isinstance(value, str) or not value for value in layers.values()):
            errors.append(f"{identifier}: every adjudication layer needs a disposition")
        if not isinstance(claim.get("publishable_status"), str) or not claim["publishable_status"]:
            errors.append(f"{identifier}: publishable_status is required")
        if not isinstance(claim.get("public_wording"), str) or not claim["public_wording"].strip():
            errors.append(f"{identifier}: bounded public wording is required")
        if not isinstance(claim.get("required_receipts"), list) or not claim["required_receipts"]:
            errors.append(f"{identifier}: required receipts must remain explicit")
        expected_row = (
            f"| `{identifier}` | `{layers['measurement']}` | `{layers['inference']}` | "
            f"`{layers['implication']}` | `{layers['prominence']}` | "
            f"`{claim.get('publishable_status')}` |"
        )
        if expected_row not in ledger_text:
            errors.append(f"{identifier}: claims ledger projection is missing or drifted")
    if EXPECTED_W08_SOURCE_HEAD not in ledger_text:
        errors.append("claims ledger must cite the immutable W08 source head")
    return errors


def validate_index(index: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    if index.get("schema_version") != SCHEMA:
        errors.append(f"schema_version must be {SCHEMA}")
    if index.get("work_ids") != ["PSP-P02-W04", "PSP-P02-W05"]:
        errors.append("work_ids must preserve the W04 then W05 cohort")

    gate = index.get("dependency_gate")
    if not isinstance(gate, dict):
        errors.append("dependency_gate must be a mapping")
    elif gate.get("w03_state") != "open" or gate.get("w04_state") != "open" or gate.get("w05_state") != "open":
        errors.append("preflight must keep W03, W04, and W05 formally open")

    privacy = index.get("privacy")
    if not isinstance(privacy, dict):
        errors.append("privacy must be a mapping")
    else:
        if privacy.get("public_packets_only") is not True:
            errors.append("packets must be public-only")
        if privacy.get("private_repository_names_in_artifact") != 0:
            errors.append("public evidence index must declare zero private repository names")
        if privacy.get("private_evidence_required_for_selected_claims") is not False:
            errors.append("selected claims must not require private evidence")
        addendum = privacy.get("encrypted_addendum")
        if not isinstance(addendum, dict) or addendum.get("status") != "not_created":
            errors.append("encrypted addendum must remain not_created without a sanctioned custody receipt")

    try:
        ledger_text = (root / "docs/positioning/claims-ledger.md").read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot load claims ledger: {exc}")
    else:
        errors.extend(validate_w08_import(index, ledger_text))

    packets = index.get("packets")
    if not isinstance(packets, list) or len(packets) != 3:
        return errors + ["packets must contain exactly three flagships"]
    packet_ids = {row.get("id") for row in packets if isinstance(row, dict)}
    if packet_ids != EXPECTED_IDS:
        errors.append(f"packet ids must be {sorted(EXPECTED_IDS)}")
    selected: dict[str, str] = {}
    try:
        selected = selected_repositories(load_yaml(root / "docs/positioning/flagship-proof-set.yaml"))
        if set(selected) != packet_ids:
            errors.append("packets must match the W03 selected flagship set exactly")
    except EvidenceError as exc:
        errors.append(str(exc))

    for packet in packets:
        if not isinstance(packet, dict):
            errors.append("every packet must be a mapping")
            continue
        label = str(packet.get("id") or "packet")
        path = packet.get("path")
        packet_path = Path(path) if isinstance(path, str) else None
        if (
            packet_path is None
            or packet_path.is_absolute()
            or ".." in packet_path.parts
            or not (root / packet_path).is_file()
        ):
            errors.append(f"{label}: packet path must exist")
        if packet.get("public_repository") != selected.get(label):
            errors.append(f"{label}: public_repository must match the W03-selected public repository")
        if not isinstance(packet.get("limitations"), list) or not packet["limitations"]:
            errors.append(f"{label}: limitations must be nonempty")
        if not isinstance(packet.get("authorship"), str) or not packet["authorship"].strip():
            errors.append(f"{label}: authorship treatment is required")
        sources = packet.get("sources")
        if (
            not isinstance(sources, list)
            or len(sources) != 2
            or [source.get("kind") for source in sources if isinstance(source, dict)].count("workflow_run") != 1
            or [source.get("kind") for source in sources if isinstance(source, dict)].count("public_endpoint") != 1
        ):
            errors.append(f"{label}: exactly one workflow and public endpoint source are required")
        else:
            for source in sources:
                url = source.get("url")
                try:
                    validate_public_fetch_url(url)
                except EvidenceError as exc:
                    errors.append(f"{label}: {exc}")
                if source.get("kind") == "workflow_run":
                    api_url = source.get("api_url")
                    try:
                        validate_public_fetch_url(api_url)
                    except EvidenceError:
                        errors.append(f"{label}: workflow API URL must use the public GitHub endpoint")
                    if not isinstance(api_url, str) or not api_url.startswith("https://api.github.com/repos/"):
                        errors.append(f"{label}: workflow API URL must use the public GitHub endpoint")
        metrics = packet.get("metrics")
        if not isinstance(metrics, list) or not metrics:
            errors.append(f"{label}: at least one material metric is required")
            continue
        for metric in metrics:
            if not isinstance(metric, dict):
                errors.append(f"{label}: metric must be a mapping")
                continue
            for field in ("id", "public_safe_claim", "status", "source_url", "observed_value", "comparison"):
                if field not in metric:
                    errors.append(f"{label}: metric missing {field}")
            if metric.get("comparison") != "exact":
                errors.append(f"{label}: metrics must use an exact, dated comparison")
            if metric.get("status") not in {"verified", "repository_asserted_with_public_anchor"}:
                errors.append(f"{label}: invalid metric status")
            if isinstance(metric.get("observed_value"), bool) or not isinstance(metric.get("observed_value"), (int, float)):
                errors.append(f"{label}: observed metric values must be numeric")
            try:
                validate_public_fetch_url(metric.get("source_url"))
            except EvidenceError as exc:
                errors.append(f"{label}: metric source {exc}")
    return errors


def verify_live(index: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for packet in index["packets"]:
        label = packet["id"]
        endpoint_text = ""
        for source in packet["sources"]:
            if source["kind"] == "workflow_run":
                status, payload = fetch(source["api_url"])
                if status != 200:
                    errors.append(f"{label}: workflow API returned HTTP {status}")
                    continue
                try:
                    run = json.loads(payload)
                except json.JSONDecodeError as exc:
                    errors.append(f"{label}: workflow API returned invalid JSON: {exc}")
                    continue
                if run.get("conclusion") != source["expected_conclusion"]:
                    errors.append(f"{label}: workflow conclusion is {run.get('conclusion')!r}")
                if run.get("head_sha") != source["observed_head"]:
                    errors.append(f"{label}: workflow head no longer matches the packet snapshot")
            elif source["kind"] == "public_endpoint":
                status, payload = fetch(source["url"])
                if status != source["expected_http_status"]:
                    errors.append(f"{label}: public endpoint returned HTTP {status}")
                endpoint_text = payload.decode("utf-8", errors="replace")
        for metric in packet["metrics"]:
            if metric.get("observation_path"):
                try:
                    value = nested_value(json.loads(endpoint_text), metric["observation_path"])
                except (json.JSONDecodeError, EvidenceError) as exc:
                    errors.append(f"{label}/{metric['id']}: {exc}")
                    continue
                if value != metric["observed_value"]:
                    errors.append(f"{label}/{metric['id']}: observed {value!r}, expected {metric['observed_value']!r}")
            evidence_text = endpoint_text
            if metric.get("corroborating_terms") and metric["source_url"] != next(
                source["url"] for source in packet["sources"] if source["kind"] == "public_endpoint"
            ):
                status, payload = fetch(metric["source_url"])
                if status != 200:
                    errors.append(f"{label}/{metric['id']}: metric source returned HTTP {status}")
                    continue
                evidence_text = payload.decode("utf-8", errors="replace")
            for term in metric.get("corroborating_terms", []):
                if term not in evidence_text:
                    errors.append(f"{label}/{metric['id']}: public evidence is missing {term!r}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-live", action="store_true", help="verify public network anchors")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()
    try:
        index = load_yaml(INDEX)
        errors = validate_index(index)
        if not errors and args.verify_live:
            errors.extend(verify_live(index))
    except EvidenceError as exc:
        errors = [str(exc)]
    result = {"status": "pass" if not errors else "fail", "errors": errors}
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif errors:
        print("FAIL")
        print("\n".join(f"- {error}" for error in errors))
    else:
        print("PASS")
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
