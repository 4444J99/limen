#!/usr/bin/env python3
"""Validate the PSP-P02-W04/W05 public flagship evidence packets.

The static mode proves packet shape, public-only custody boundaries, metric declarations, and the
W03 -> W04 -> W05 completion order. ``--verify-live`` additionally checks the public workflow
receipts, endpoint status, JSON observations, and visible corroborating terms.
"""

from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit

import yaml


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "docs/positioning/evidence/flagship-evidence.yaml"
MATRIX = ROOT / "docs/positioning/flagship-proof-set.yaml"
CLAIMS_LEDGER = ROOT / "docs/positioning/claims-ledger.md"
CENSUS = ROOT / "docs/github-estate-census.json"
SCHEMA = "limen.positioning_flagship_evidence.v1"
EXPECTED_IDS = {"limen", "public_records", "ai_chat_exporter"}
EXPECTED_W08_SOURCE_HEAD = "96d0ac9e8755c1b7ed9ecf49a82b54b501f7a4aa"
EXPECTED_W08_SOURCE_PATH = "docs/positioning/program/research-adjudication.json"
EXPECTED_W08_SOURCE_BLOB = "f0db657dde5cc27bb2db67e495fa410f6483646f"
EXPECTED_W08_SOURCE_SHA256 = "26a2342bf043c25906ebd985fa619249e3210f6f5409832f19e05cf770f8fca6"
EXPECTED_W08_PROJECTION_SHA256 = "698e317695c1ebd63f82e7456a04f1c55087754de0ef358bbd77c4fc8d4d39fc"
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
FULL_SHA1_RE = re.compile(r"[0-9a-f]{40}")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
REPOSITORY_TOKEN_RE = re.compile(
    r"(?=(?<![A-Za-z0-9_.-])([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?![A-Za-z0-9_.-]))"
)
PREDECESSOR_RECEIPTS = {"w03": "PSP-P02-W03", "w04": "PSP-P02-W04"}


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


def load_public_census_repositories(path: Path = CENSUS) -> set[str]:
    """Load only source-safe public identities from the redacted W01 census projection."""

    try:
        census = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvidenceError("cannot load the tracked W01 public census projection") from exc
    leaves = census.get("leaves") if isinstance(census, dict) else None
    if not isinstance(leaves, list):
        raise EvidenceError("tracked W01 public census projection has no leaf list")
    repositories = {
        str(leaf.get("repository"))
        for leaf in leaves
        if isinstance(leaf, dict)
        and leaf.get("private") is False
        and isinstance(leaf.get("repository"), str)
        and REPOSITORY_RE.fullmatch(str(leaf.get("repository")))
    }
    summary = census.get("summary") or {}
    repository_count = summary.get("repository_count")
    private_count = summary.get("private_repository_count")
    if (
        isinstance(repository_count, bool)
        or not isinstance(repository_count, int)
        or isinstance(private_count, bool)
        or not isinstance(private_count, int)
        or len(repositories) != repository_count - private_count
    ):
        raise EvidenceError("tracked W01 public census projection does not cover its public denominator")
    return repositories


def repository_identities_in_text(text: str, controlled_owners: set[str]) -> set[str]:
    """Extract controlled owner/repository tokens without needing any private-name inventory."""

    return {
        match.group(1)
        for match in REPOSITORY_TOKEN_RE.finditer(text)
        if match.group(1).split("/", 1)[0].casefold() in controlled_owners
    }


def public_artifact_identity_errors(index: dict[str, Any], *, root: Path = ROOT) -> list[str]:
    """Reject controlled repository identities absent from W01's redacted public allowlist."""

    try:
        public_repositories = load_public_census_repositories(root / "docs/github-estate-census.json")
    except EvidenceError as exc:
        return [str(exc)]
    canonical = {repository.casefold(): repository for repository in public_repositories}
    controlled_owners = {repository.split("/", 1)[0].casefold() for repository in public_repositories}
    texts = [json.dumps(index, ensure_ascii=False, sort_keys=True)]
    evidence_root = root / "docs/positioning/evidence"
    try:
        texts.extend(
            path.read_text(encoding="utf-8")
            for path in sorted(evidence_root.rglob("*"))
            if path.is_file()
        )
        texts.append((root / "docs/positioning/claims-ledger.md").read_text(encoding="utf-8"))
    except (OSError, UnicodeError) as exc:
        return [f"cannot inspect public evidence identity surfaces: {exc}"]
    unregistered = {
        identity.casefold()
        for text in texts
        for identity in repository_identities_in_text(text, controlled_owners)
        if canonical.get(identity.casefold()) != identity
    }
    if unregistered:
        return [
            "public evidence contains "
            f"{len(unregistered)} controlled repository identity token(s) absent from the tracked public census"
        ]
    return []


def nested_value(value: object, path: str) -> object:
    current = value
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            raise EvidenceError(f"JSON observation path is absent: {path}")
        current = current[key]
    return current


def read_bounded_body(response: Any, *, error_body: bool = False) -> bytes:
    """Read one bounded response body and normalize transport interruptions."""

    label = "public anchor error body" if error_body else "public anchor body"
    try:
        payload = response.read(MAX_RESPONSE_BYTES + 1)
    except (OSError, ValueError, http.client.HTTPException, urllib.error.URLError) as exc:
        raise EvidenceError(f"{label} could not be read completely") from exc
    if not isinstance(payload, bytes):
        raise EvidenceError(f"{label} did not return bytes")
    if len(payload) > MAX_RESPONSE_BYTES:
        raise EvidenceError(f"{label} exceeds {MAX_RESPONSE_BYTES} bytes")
    return payload


def fetch(url: str) -> tuple[int, bytes]:
    url = validate_public_fetch_url(url)
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "limen-evidence-verifier"})
    try:
        with SAFE_OPENER.open(request, timeout=20) as response:
            payload = read_bounded_body(response)
            return response.status, payload
    except urllib.error.HTTPError as exc:
        payload = read_bounded_body(exc, error_body=True)
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


def normalized_packet_text(value: str) -> str:
    """Collapse Markdown wrapping without erasing visible packet content."""

    return " ".join(value.split())


def validate_packet_markdown(packet: dict[str, Any], packet_text: str) -> list[str]:
    """Prove that public prose contains every material machine-index projection."""

    label = str(packet.get("id") or "packet")
    normalized = normalized_packet_text(packet_text)
    required: list[tuple[str, object]] = [
        ("bounded claim", packet.get("bounded_claim")),
        ("authorship", packet.get("authorship")),
    ]
    limitations = packet.get("limitations")
    if isinstance(limitations, list):
        required.extend(("limitation", value) for value in limitations)
    sources = packet.get("sources")
    for source in sources if isinstance(sources, list) else []:
        if not isinstance(source, dict):
            continue
        required.append(("source URL", source.get("url")))
        if source.get("kind") == "workflow_run":
            required.append(("workflow head", source.get("observed_head")))
    metrics = packet.get("metrics")
    for metric in metrics if isinstance(metrics, list) else []:
        if isinstance(metric, dict):
            required.append((f"{metric.get('id', 'metric')} claim", metric.get("public_safe_claim")))

    errors: list[str] = []
    for field, value in required:
        if not isinstance(value, str) or not value.strip():
            errors.append(f"{label}: {field} must be a nonempty packet projection")
        elif normalized_packet_text(value) not in normalized:
            errors.append(f"{label}: packet Markdown is missing indexed {field}")
    return errors


def w08_projection_sha256(claims: list[object]) -> str:
    """Hash every publication disposition imported from the immutable W08 artifact."""

    projection = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        projection.append(
            {
                "id": claim.get("id"),
                "layers": claim.get("layers"),
                "publishable_status": claim.get("publishable_status"),
                "public_wording": claim.get("public_wording"),
                "required_receipts": claim.get("required_receipts"),
            }
        )
    projection.sort(key=lambda row: str(row["id"]))
    encoded = json.dumps(projection, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def workflow_binding_errors(packet: dict[str, Any], source: dict[str, Any]) -> list[str]:
    """Bind both workflow URLs to the selected public repository and one run ID."""

    label = str(packet.get("id") or "packet")
    repository = packet.get("public_repository")
    if not isinstance(repository, str) or not repository:
        return [f"{label}: public_repository is required before workflow binding"]
    api_url = source.get("api_url")
    human_url = source.get("url")
    api_pattern = rf"https://api\.github\.com/repos/{re.escape(repository)}/actions/runs/([0-9]+)"
    human_pattern = rf"https://github\.com/{re.escape(repository)}/actions/runs/([0-9]+)"
    api_match = re.fullmatch(api_pattern, api_url) if isinstance(api_url, str) else None
    human_match = re.fullmatch(human_pattern, human_url) if isinstance(human_url, str) else None
    if api_match is None or human_match is None or api_match.group(1) != human_match.group(1):
        return [f"{label}: workflow API and human URLs must bind one run in public_repository"]
    return []


def dependency_issue_api_url(value: object) -> str:
    """Return the API URL for one repository-owned dependency issue."""

    url = validate_public_fetch_url(value)
    match = re.fullmatch(r"https://github\.com/organvm/limen/issues/([0-9]+)", url)
    if match is None:
        raise EvidenceError("dependency issue must be an organvm/limen issue URL")
    return f"https://api.github.com/repos/organvm/limen/issues/{match.group(1)}"


def verify_positioning_work_receipt(work_id: str) -> None:
    """Run the canonical latest-marked-receipt predicate for a closed predecessor."""

    try:
        result = subprocess.run(
            [sys.executable, "scripts/positioning-program.py", "--verify-work", work_id],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"{work_id} latest marked receipt predicate was unavailable") from exc
    if result.returncode != 0:
        raise EvidenceError(f"{work_id} latest marked receipt predicate did not pass")
    try:
        receipt = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"{work_id} latest marked receipt predicate returned invalid JSON") from exc
    if not isinstance(receipt, dict) or receipt.get("status") != "pass" or receipt.get("work_id") != work_id:
        raise EvidenceError(f"{work_id} latest marked receipt predicate returned an invalid result")


def verify_dependency_states(
    index: dict[str, Any],
    fetcher: Callable[[str], tuple[int, bytes]],
    receipt_verifier: Callable[[str], None] = verify_positioning_work_receipt,
) -> list[str]:
    """Compare live issue state and require canonical receipts for closed predecessors."""

    gate = index.get("dependency_gate")
    if not isinstance(gate, dict):
        return ["dependency_gate must be a mapping"]
    errors: list[str] = []
    for work in ("w03", "w04", "w05"):
        try:
            api_url = dependency_issue_api_url(gate.get(f"{work}_issue"))
        except EvidenceError as exc:
            errors.append(f"{work}: {exc}")
            continue
        status, payload = fetcher(api_url)
        if status != 200:
            errors.append(f"{work}: dependency issue API returned HTTP {status}")
            continue
        try:
            issue = json.loads(payload)
        except json.JSONDecodeError as exc:
            errors.append(f"{work}: dependency issue API returned invalid JSON: {exc}")
            continue
        if not isinstance(issue, dict):
            errors.append(f"{work}: dependency issue API response must be a mapping")
            continue
        observed_state = issue.get("state")
        declared_state = gate.get(f"{work}_state")
        if observed_state != declared_state:
            errors.append(
                f"{work}: declared dependency state {declared_state!r} "
                f"does not match live issue state {observed_state!r}"
            )
            continue
        predecessor_id = PREDECESSOR_RECEIPTS.get(work)
        if declared_state == "closed" and predecessor_id is not None:
            try:
                receipt_verifier(predecessor_id)
            except EvidenceError as exc:
                errors.append(f"{work}: {exc}")
    return errors


def validate_workflow_run_response(
    packet: dict[str, Any], source: dict[str, Any], run: object
) -> list[str]:
    """Validate the live workflow response against the selected public repository."""

    label = str(packet.get("id") or "packet")
    if not isinstance(run, dict):
        return [f"{label}: workflow API response must be a mapping"]
    errors: list[str] = []
    repository = run.get("repository")
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    if full_name != packet.get("public_repository"):
        errors.append(f"{label}: workflow response repository does not match public_repository")
    if run.get("html_url") != source.get("url"):
        errors.append(f"{label}: workflow response html_url does not match the human receipt URL")
    if run.get("url") != source.get("api_url"):
        errors.append(f"{label}: workflow response API URL does not match the indexed receipt")
    return errors


def derive_tree_path_count(observation: dict[str, Any], payload: bytes) -> int:
    """Derive an exact file count from a complete, head-pinned Git tree response."""

    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise EvidenceError(f"count source returned invalid JSON: {exc}") from exc
    if not isinstance(document, dict) or not isinstance(document.get("tree"), list):
        raise EvidenceError("count source must return a Git tree mapping")
    if document.get("truncated") is True:
        raise EvidenceError("count source Git tree is truncated")
    pattern = observation.get("path_regex")
    if not isinstance(pattern, str):
        raise EvidenceError("count observation path_regex is required")
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise EvidenceError(f"count observation path_regex is invalid: {exc}") from exc
    return sum(
        1
        for entry in document["tree"]
        if isinstance(entry, dict)
        and entry.get("type") == "blob"
        and isinstance(entry.get("path"), str)
        and compiled.fullmatch(entry["path"])
    )


def exact_count_errors(label: str, metric: dict[str, Any], payload: bytes) -> list[str]:
    """Compare a term metric's derived denominator with its indexed exact value."""

    observation = metric.get("count_observation")
    if not isinstance(observation, dict):
        return [f"{label}/{metric.get('id', 'metric')}: term metric needs an exact count observation"]
    try:
        derived = derive_tree_path_count(observation, payload)
    except EvidenceError as exc:
        return [f"{label}/{metric.get('id', 'metric')}: {exc}"]
    expected = metric.get("observed_value")
    if derived != expected:
        return [f"{label}/{metric.get('id', 'metric')}: derived {derived!r}, expected {expected!r}"]
    return []


def validate_metric_ledger(packets: list[object], ledger_text: str) -> list[str]:
    """Keep the managed section-8 metric rows equal to the packet index."""

    section_match = re.search(
        r"^## 8\. PSP-P02 selected-flagship packet claims\s*$\n(.*?)(?=^## 9\.)",
        ledger_text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if section_match is None:
        return ["claims ledger must contain the managed PSP-P02 section 8"]
    expected: dict[str, tuple[object, object, object]] = {}
    errors: list[str] = []
    for packet in packets:
        if not isinstance(packet, dict):
            continue
        packet_id = packet.get("id")
        metrics = packet.get("metrics")
        if not isinstance(packet_id, str) or not isinstance(metrics, list):
            continue
        for metric in metrics:
            if not isinstance(metric, dict) or not isinstance(metric.get("id"), str):
                continue
            identifier = f"{packet_id}/{metric['id']}"
            if identifier in expected:
                errors.append(f"{identifier}: duplicate packet metric identifier")
                continue
            expected[identifier] = (
                metric.get("status"),
                metric.get("observed_value"),
                metric.get("public_safe_claim"),
            )

    observed: dict[str, tuple[str, str, str]] = {}
    for line in section_match.group(1).splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if not cells or not re.fullmatch(r"`[^`]+/[^`]+`", cells[0]):
            continue
        if len(cells) != 5:
            errors.append("claims ledger section 8 contains a malformed managed metric row")
            continue
        identifier = cells[0][1:-1]
        if identifier in observed:
            errors.append(f"{identifier}: duplicate claims ledger metric row")
            continue
        status = cells[1][1:-1] if re.fullmatch(r"`[^`]+`", cells[1]) else cells[1]
        value = cells[2][1:-1] if re.fullmatch(r"`[^`]+`", cells[2]) else cells[2]
        observed[identifier] = (status, value, cells[3])

    if set(observed) != set(expected):
        errors.append("claims ledger section 8 metric denominator must match the packet index")
    for identifier in sorted(set(observed) & set(expected)):
        status, value, wording = expected[identifier]
        if observed[identifier] != (str(status), str(value), str(wording)):
            errors.append(f"{identifier}: claims ledger metric projection is missing or drifted")
    return errors


def validate_w08_import(index: dict[str, Any], ledger_text: str) -> list[str]:
    errors: list[str] = []
    imported = index.get("w08_research_import")
    if not isinstance(imported, dict):
        return ["w08_research_import must be a mapping"]
    if imported.get("source_head") != EXPECTED_W08_SOURCE_HEAD:
        errors.append("W08 import must bind the reviewed immutable source head")
    if imported.get("source_path") != EXPECTED_W08_SOURCE_PATH:
        errors.append("W08 import must bind the immutable source artifact path")
    if imported.get("source_blob") != EXPECTED_W08_SOURCE_BLOB:
        errors.append("W08 import must bind the immutable source artifact blob")
    if imported.get("source_sha256") != EXPECTED_W08_SOURCE_SHA256:
        errors.append("W08 import must bind the immutable source artifact SHA-256")
    if imported.get("projection_sha256") != EXPECTED_W08_PROJECTION_SHA256:
        errors.append("W08 import must declare the immutable adjudication projection SHA-256")
    if imported.get("claim_count") != len(EXPECTED_W08_CLAIM_IDS):
        errors.append("W08 import claim_count must equal the 13-claim denominator")
    claims = imported.get("claims")
    if not isinstance(claims, list):
        return errors + ["W08 import claims must be a list"]
    identifiers = [claim.get("id") for claim in claims if isinstance(claim, dict)]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != EXPECTED_W08_CLAIM_IDS:
        errors.append("W08 import must classify each ratified claim exactly once")
    if w08_projection_sha256(claims) != EXPECTED_W08_PROJECTION_SHA256:
        errors.append("W08 adjudication dispositions, wording, and receipts must match the immutable source artifact")
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
    else:
        for work in ("w03", "w04", "w05"):
            try:
                dependency_issue_api_url(gate.get(f"{work}_issue"))
            except EvidenceError as exc:
                errors.append(f"{work}: {exc}")
            if gate.get(f"{work}_state") not in {"open", "closed"}:
                errors.append(f"{work}: dependency state must be open or closed")
        if gate.get("w04_state") == "closed" and gate.get("w03_state") != "closed":
            errors.append("W04 may close only after W03")
        if gate.get("w05_state") == "closed" and (
            gate.get("w03_state") != "closed" or gate.get("w04_state") != "closed"
        ):
            errors.append("W05 may close only after W03 and W04")

    privacy = index.get("privacy")
    if not isinstance(privacy, dict):
        errors.append("privacy must be a mapping")
    else:
        if privacy.get("public_packets_only") is not True:
            errors.append("packets must be public-only")
        identity_guard = privacy.get("repository_identity_guard")
        if not isinstance(identity_guard, dict) or identity_guard != {
            "source": "docs/github-estate-census.json",
            "mode": "tracked_public_census_allowlist",
        }:
            errors.append("privacy must bind repository identities to the tracked W01 public census")
        if privacy.get("private_evidence_required_for_selected_claims") is not False:
            errors.append("selected claims must not require private evidence")
        addendum = privacy.get("encrypted_addendum")
        if not isinstance(addendum, dict) or addendum.get("status") != "not_created":
            errors.append("encrypted addendum must remain not_created without a sanctioned custody receipt")

    ledger_text: str | None = None
    try:
        ledger_text = (root / "docs/positioning/claims-ledger.md").read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"cannot load claims ledger: {exc}")
    else:
        errors.extend(validate_w08_import(index, ledger_text))

    errors.extend(public_artifact_identity_errors(index, root=root))

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
        packet_text: str | None = None
        if (
            packet_path is None
            or packet_path.is_absolute()
            or ".." in packet_path.parts
            or not (root / packet_path).is_file()
        ):
            errors.append(f"{label}: packet path must exist")
        else:
            try:
                packet_text = (root / packet_path).read_text(encoding="utf-8")
            except OSError as exc:
                errors.append(f"{label}: cannot load packet Markdown: {exc}")
        if packet.get("public_repository") != selected.get(label):
            errors.append(f"{label}: public_repository must match the W03-selected public repository")
        if not isinstance(packet.get("bounded_claim"), str) or not packet["bounded_claim"].strip():
            errors.append(f"{label}: bounded_claim must be nonempty")
        if not isinstance(packet.get("limitations"), list) or not packet["limitations"]:
            errors.append(f"{label}: limitations must be nonempty")
        if not isinstance(packet.get("authorship"), str) or not packet["authorship"].strip():
            errors.append(f"{label}: authorship treatment is required")
        sources = packet.get("sources")
        safe_sources = sources if isinstance(sources, list) else []
        public_endpoint_url: object = None
        if (
            not isinstance(sources, list)
            or len(sources) != 2
            or [source.get("kind") for source in sources if isinstance(source, dict)].count("workflow_run") != 1
            or [source.get("kind") for source in sources if isinstance(source, dict)].count("public_endpoint") != 1
        ):
            errors.append(f"{label}: exactly one workflow and public endpoint source are required")
        else:
            public_endpoint_url = next(
                source.get("url") for source in sources if source.get("kind") == "public_endpoint"
            )
            for source in sources:
                if not isinstance(source, dict):
                    errors.append(f"{label}: every source must be a mapping")
                    continue
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
                    errors.extend(workflow_binding_errors(packet, source))
                    observed_head = source.get("observed_head")
                    if not isinstance(observed_head, str) or FULL_SHA1_RE.fullmatch(observed_head) is None:
                        errors.append(f"{label}: workflow observed_head must be a full lowercase SHA-1")
                    if source.get("expected_conclusion") != "success":
                        errors.append(f"{label}: workflow expected_conclusion must be success")
                elif source.get("kind") == "public_endpoint":
                    expected_status = source.get("expected_http_status")
                    if isinstance(expected_status, bool) or not isinstance(expected_status, int):
                        errors.append(f"{label}: public endpoint expected_http_status must be an integer")
                    elif expected_status != 200:
                        errors.append(f"{label}: public endpoint expected_http_status must be 200")
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
            observation_path = metric.get("observation_path")
            count_observation = metric.get("count_observation")
            if observation_path is not None:
                if not isinstance(observation_path, str) or not observation_path.strip():
                    errors.append(f"{label}: observation_path must be a nonempty string")
                if metric.get("source_url") != public_endpoint_url:
                    errors.append(f"{label}: JSON observation source must equal the packet public endpoint")
                if count_observation is not None:
                    errors.append(f"{label}: metric may not mix JSON and term-count observations")
            else:
                if not isinstance(count_observation, dict):
                    errors.append(f"{label}: term-based metric must declare an exact count observation")
                else:
                    if count_observation.get("kind") != "github_tree_path_regex":
                        errors.append(f"{label}: count observation kind must be github_tree_path_regex")
                    count_url = count_observation.get("api_url")
                    try:
                        validate_public_fetch_url(count_url)
                    except EvidenceError as exc:
                        errors.append(f"{label}: count source {exc}")
                    workflow = next(
                        (
                            source
                            for source in safe_sources
                            if isinstance(source, dict) and source.get("kind") == "workflow_run"
                        ),
                        {},
                    )
                    expected_count_url = (
                        f"https://api.github.com/repos/{packet.get('public_repository')}/git/trees/"
                        f"{workflow.get('observed_head')}?recursive=1"
                    )
                    if count_url != expected_count_url:
                        errors.append(f"{label}: count source must bind public_repository and workflow head")
                    path_regex = count_observation.get("path_regex")
                    if not isinstance(path_regex, str) or not path_regex:
                        errors.append(f"{label}: count observation path_regex is required")
                    else:
                        try:
                            re.compile(path_regex)
                        except re.error as exc:
                            errors.append(f"{label}: count observation path_regex is invalid: {exc}")
                    if isinstance(metric.get("observed_value"), bool) or not isinstance(metric.get("observed_value"), int):
                        errors.append(f"{label}: term-count observed_value must be an integer")
            terms = metric.get("corroborating_terms")
            if count_observation is not None and (
                not isinstance(terms, list)
                or not terms
                or any(not isinstance(term, str) or not term for term in terms)
            ):
                errors.append(f"{label}: term-count metric needs nonempty corroborating_terms")
        if packet_text is not None:
            errors.extend(validate_packet_markdown(packet, packet_text))
    if ledger_text is not None:
        errors.extend(validate_metric_ledger(packets, ledger_text))
    return errors


def verify_live(index: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fetch_cache: dict[str, tuple[int, bytes]] = {}

    def cached_fetch(url: str) -> tuple[int, bytes]:
        if url not in fetch_cache:
            fetch_cache[url] = fetch(url)
        return fetch_cache[url]

    errors.extend(verify_dependency_states(index, cached_fetch))

    packets = index.get("packets")
    if not isinstance(packets, list):
        return ["packets must contain exactly three flagships"]
    for packet in packets:
        if not isinstance(packet, dict):
            errors.append("every packet must be a mapping")
            continue
        label = str(packet.get("id") or "packet")
        endpoint_text = ""
        sources = packet.get("sources")
        if not isinstance(sources, list):
            errors.append(f"{label}: sources must be a list")
            continue
        for source in sources:
            if not isinstance(source, dict):
                errors.append(f"{label}: every source must be a mapping")
                continue
            if source.get("kind") == "workflow_run":
                api_url = source.get("api_url")
                if not isinstance(api_url, str):
                    errors.append(f"{label}: workflow API URL is required")
                    continue
                status, payload = cached_fetch(api_url)
                if status != 200:
                    errors.append(f"{label}: workflow API returned HTTP {status}")
                    continue
                try:
                    run = json.loads(payload)
                except json.JSONDecodeError as exc:
                    errors.append(f"{label}: workflow API returned invalid JSON: {exc}")
                    continue
                errors.extend(validate_workflow_run_response(packet, source, run))
                if run.get("conclusion") != source.get("expected_conclusion"):
                    errors.append(f"{label}: workflow conclusion is {run.get('conclusion')!r}")
                if run.get("head_sha") != source.get("observed_head"):
                    errors.append(f"{label}: workflow head no longer matches the packet snapshot")
            elif source.get("kind") == "public_endpoint":
                endpoint_url = source.get("url")
                if not isinstance(endpoint_url, str):
                    errors.append(f"{label}: public endpoint URL is required")
                    continue
                status, payload = cached_fetch(endpoint_url)
                if status != source.get("expected_http_status"):
                    errors.append(f"{label}: public endpoint returned HTTP {status}")
                endpoint_text = payload.decode("utf-8", errors="replace")
        metrics = packet.get("metrics")
        if not isinstance(metrics, list):
            errors.append(f"{label}: metrics must be a list")
            continue
        public_endpoint_url = next(
            (
                source.get("url")
                for source in sources
                if isinstance(source, dict) and source.get("kind") == "public_endpoint"
            ),
            None,
        )
        for metric in metrics:
            if not isinstance(metric, dict):
                errors.append(f"{label}: metric must be a mapping")
                continue
            if metric.get("observation_path"):
                try:
                    value = nested_value(json.loads(endpoint_text), metric["observation_path"])
                except (json.JSONDecodeError, EvidenceError) as exc:
                    errors.append(f"{label}/{metric.get('id', 'metric')}: {exc}")
                    continue
                if value != metric.get("observed_value"):
                    errors.append(
                        f"{label}/{metric.get('id', 'metric')}: observed {value!r}, "
                        f"expected {metric.get('observed_value')!r}"
                    )
            elif isinstance(metric.get("count_observation"), dict):
                count_url = metric["count_observation"].get("api_url")
                if not isinstance(count_url, str):
                    errors.append(f"{label}/{metric.get('id', 'metric')}: count source URL is required")
                else:
                    status, payload = cached_fetch(count_url)
                    if status != 200:
                        errors.append(f"{label}/{metric.get('id', 'metric')}: count source returned HTTP {status}")
                    else:
                        errors.extend(exact_count_errors(label, metric, payload))
            evidence_text = endpoint_text
            source_url = metric.get("source_url")
            if metric.get("corroborating_terms") and source_url != public_endpoint_url:
                if not isinstance(source_url, str):
                    errors.append(f"{label}/{metric.get('id', 'metric')}: metric source URL is required")
                    continue
                status, payload = cached_fetch(source_url)
                if status != 200:
                    errors.append(f"{label}/{metric.get('id', 'metric')}: metric source returned HTTP {status}")
                    continue
                evidence_text = payload.decode("utf-8", errors="replace")
            for term in metric.get("corroborating_terms", []):
                if term not in evidence_text:
                    errors.append(f"{label}/{metric.get('id', 'metric')}: public evidence is missing {term!r}")
    return errors


def verify_evidence(index: dict[str, Any], *, live: bool = False) -> list[str]:
    """Run static validation first so malformed live fields fail as data, never exceptions."""

    errors = validate_index(index)
    if not errors and live:
        errors.extend(verify_live(index))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-live", action="store_true", help="verify public network anchors")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()
    try:
        index = load_yaml(INDEX)
        errors = verify_evidence(index, live=args.verify_live)
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
