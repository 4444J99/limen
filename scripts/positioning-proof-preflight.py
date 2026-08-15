#!/usr/bin/env python3
"""Fail-closed integration harness for the dependency-gated PSP-C04/P05 proof package."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import html
import hashlib
import io
import importlib.util
import json
import os
import re
import ssl
import subprocess
import sys
import tempfile
import zipfile
from http.client import HTTPException
from urllib.parse import parse_qsl, unquote, urlsplit
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_CA_BUNDLE_CANDIDATES = (
    Path("/etc/ssl/cert.pem"),
    Path("/etc/ssl/certs/ca-certificates.crt"),
    Path("/etc/pki/tls/certs/ca-bundle.crt"),
    Path("/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"),
)
TRUSTED_EXECUTABLE_DIRECTORIES = (
    Path(sys.executable).resolve().parent,
    Path("/opt/homebrew/bin"),
    Path("/usr/local/bin"),
    Path("/usr/bin"),
    Path("/bin"),
)
DEFAULT_CONTRACT = ROOT / "docs/positioning/proof/psp-c04-proof-contract.json"
FULL_HEAD = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
W07_RECEIPT_URL = re.compile(r"^https://github\.com/organvm/limen/issues/2188#issuecomment-[0-9]+$")
W07_RECEIPT_BLOCK = re.compile(
    r"<!--\s*positioning-receipt:PSP-P03-W07\s*-->\s*```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
W07_BINDING_FIELDS = {"work_id", "issue_url", "url", "sha256", "receipt"}
W07_WORK_RECEIPT_FIELDS = {
    "schema_version",
    "work_id",
    "acceptance_sha256",
    "authority",
    "changed_paths",
    "evidence_urls",
    "observed_heads",
    "outcome",
    "predicate",
    "reader_evidence",
    "rollback",
}
W07_AUTHORITY_FIELDS = {"kind", "session_id", "executor", "human_protected"}
W07_PREDICATE_FIELDS = {"command", "exit_code", "observed_at", "output_sha256"}
W07_READER_EVIDENCE_FIELDS = {
    "reader_count",
    "independent_reader_count",
    "synthetic_or_model_reader_count",
    "unresolved_authority_objections",
    "total_score",
    "role_matches",
    "buyer_matches",
    "cta_matches",
    "response_set_path",
    "response_set_sha256",
    "decision_memo_path",
    "decision_memo_sha256",
}
W07_ROLLBACK_FIELDS = {"invoked", "state"}
EXTERNAL_VALIDATION_RECEIPT_URL = re.compile(r"^https://github\.com/organvm/limen/issues/2201#issuecomment-[0-9]+$")
EXTERNAL_VALIDATION_RECEIPT_SCHEMA = "limen.positioning_external_validation_receipt.v1"
EXTERNAL_VALIDATION_RECEIPT_BLOCK = re.compile(
    r"<!--\s*positioning-external-validation-receipt\s*-->\s*```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
EXTERNAL_VALIDATION_RECEIPT_FIELDS = {
    "schema_version",
    "evidence_kind",
    "subject_sha256",
    "actor_identity",
    "observed_at",
    "limitations",
}
EXTERNAL_VALIDATION_MINIMUM_FIELDS = (
    "validator identity class",
    "independence disclosure",
    "object URL or receipt",
    "receipt SHA-256",
    "date",
    "claim scope",
    "method",
    "limitations",
    "consent status",
    "withdrawal route",
)
PHASE_RECEIPT_URLS = {
    "PSP-P03": re.compile(r"^https://github\.com/organvm/limen/issues/2181#issuecomment-[0-9]+$"),
    "PSP-P04": re.compile(r"^https://github\.com/organvm/limen/issues/2189#issuecomment-[0-9]+$"),
}
PHASE_RECEIPT_AUTHORS = {"4444J99"}
PHASE_RECEIPT_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
PHASE_RECEIPT_BLOCK = re.compile(
    r"<!--\s*positioning-phase-receipt:(PSP-P\d{2})\s*-->\s*```json\s*(\{.*?\})\s*```",
    re.DOTALL,
)
PHASE_RECEIPT_FIELDS = {
    "schema_version",
    "phase_id",
    "status",
    "exit_gate_sha256",
    "observed_heads",
    "child_receipts_sha256",
    "remote_state_sha256",
    "parity_sha256",
    "predicate",
    "evidence_urls",
}
PHASE_RECEIPT_PREDICATE_FIELDS = {"command", "exit_code", "output_sha256", "observed_at"}
W07_VALIDATOR_PATH = "docs/positioning/program/validate_p03_w07_blinded_reader.py"
W07_WORKFLOW_PATH = "docs/positioning/program/w07_blinded_reader_workflow.py"
W07_SCHEMA_PATH = "docs/positioning/program/w07_blinded_reader_response_schema.json"
W07_PROTOCOL_PATH = "docs/positioning/w07-blinded-reader-protocol.md"
W07_REPLAY_PATHS = (W07_VALIDATOR_PATH, W07_WORKFLOW_PATH, W07_SCHEMA_PATH, W07_PROTOCOL_PATH)
W07_RESPONSE_PATH = re.compile(r"^docs/receipts/positioning/psp-p03-w07-reader-responses\.json$")
W07_MEMO_PATH = re.compile(r"^docs/receipts/positioning/psp-p03-w07-decision-memo\.md$")
ARCHITECTURE_DEMO_SCHEMA = "limen.positioning_architecture_demo_fixture.v1"
COST_REVIEW_SCHEMA = "limen.positioning_cost_failure_review.v1"
SURFACE_INSPECTION_SCHEMA = "limen.positioning_surface_inspection.v2"
SURFACE_SCANNER = "canonical_claim_drift"
SURFACE_SCANNER_VERSION = "4"
TRUSTED_PYYAML_DEPENDENCY = {
    "distribution": "PyYAML",
    "version": "6.0.3",
    "package": "yaml",
    "python_source_file_count": 17,
    "python_source_tree_sha256": "fca0d26205a35539a5e123116d2756f3ff33dc1fc4058686cef1268840815eb6",
}
W07_RPDS_COMPAT_SOURCE = """from collections.abc import Mapping, Sequence, Set as AbstractSet


class HashTrieMap(Mapping):
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, value=()):
        self._data = dict(value)

    @classmethod
    def convert(cls, value):
        return value if isinstance(value, cls) else cls(value)

    def __getitem__(self, key):
        return self._data[key]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def insert(self, key, value):
        updated = dict(self._data)
        updated[key] = value
        return type(self)(updated)

    def remove(self, key):
        updated = dict(self._data)
        del updated[key]
        return type(self)(updated)

    def update(self, *values):
        updated = dict(self._data)
        for value in values:
            updated.update(value)
        return type(self)(updated)


class HashTrieSet(AbstractSet):
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, value=()):
        self._data = frozenset(value)

    def __contains__(self, item):
        return item in self._data

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)

    def insert(self, item):
        return type(self)((*self._data, item))

    def discard(self, item):
        return type(self)(value for value in self._data if value != item)

    def remove(self, item):
        if item not in self._data:
            raise KeyError(item)
        return self.discard(item)

    def update(self, *values):
        updated = set(self._data)
        for value in values:
            updated.update(value)
        return type(self)(updated)


class List(Sequence):
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, value=()):
        self._data = tuple(value)

    def __getitem__(self, index):
        return self._data[index]

    def __len__(self):
        return len(self._data)

    def push_front(self, item):
        return type(self)((item, *self._data))
"""
TRUSTED_W07_JSONSCHEMA_DEPENDENCY = {
    "distributions": {
        "attrs": "26.1.0",
        "jsonschema": "4.26.0",
        "jsonschema-specifications": "2025.9.1",
        "referencing": "0.37.0",
        "typing-extensions": "4.15.0",
    },
    "package_roots": ["attr", "attrs", "jsonschema", "jsonschema_specifications", "referencing"],
    "single_files": ["typing_extensions.py"],
    "source_file_count": 75,
    "source_tree_sha256": "f94058ced7bc81593410dcf711e37320fc8f760420f01edb9acb5950c94077eb",
    "rpds_compat_sha256": "339c93ba3307278b36036fa61205fa7a9c2feb6fe440df999771655868216f8d",
}
EXTERNAL_RECEIPT_TIME_RULE = (
    "The structured review receipt is authored in the authenticated GitHub comment version and its "
    "observed_at must equal that comment version's updated_at exactly."
)
POSITIONING_PROGRAM_BOOTSTRAP = """
import hashlib
import pathlib
import runpy
import sys

dependency_root, dependency_sha256, dependency_file_count, program, *arguments = sys.argv[1:]
package_root = pathlib.Path(dependency_root, "yaml").resolve(strict=True)
source_files = sorted(package_root.rglob("*.py"))
if len(source_files) != int(dependency_file_count):
    raise SystemExit("trusted PyYAML dependency file count changed")
digest = hashlib.sha256()
for source_file in source_files:
    if source_file.is_symlink() or package_root not in source_file.resolve(strict=True).parents:
        raise SystemExit("trusted PyYAML dependency escaped its package root")
    data = source_file.read_bytes()
    relative = source_file.relative_to(package_root).as_posix().encode("utf-8")
    digest.update(relative)
    digest.update(b"\\0")
    digest.update(str(len(data)).encode("ascii"))
    digest.update(b"\\0")
    digest.update(data)
if digest.hexdigest() != dependency_sha256:
    raise SystemExit("trusted PyYAML dependency tree digest changed")
sys.path.insert(0, dependency_root)
sys.argv = [program, *arguments]
runpy.run_path(program, run_name="__main__")
"""
W07_REPLAY_BOOTSTRAP = """
import hashlib
import importlib.abc
import importlib.util
import io
import pathlib
import runpy
import sys
import zipfile

(
    dependency_sha256,
    dependency_file_count,
    rpds_sha256,
    archive_sha256,
    archive_size,
    uncompressed_size,
    mode,
    program,
    *arguments,
) = sys.argv[1:]
archive_size = int(archive_size)
if archive_size <= 0 or archive_size > 1_000_000:
    raise SystemExit("trusted W07 jsonschema dependency archive exceeds its bound")
raw_archive = sys.stdin.buffer.read(archive_size + 1)
if len(raw_archive) != archive_size:
    raise SystemExit("trusted W07 jsonschema dependency archive size changed")
if hashlib.sha256(raw_archive).hexdigest() != archive_sha256:
    raise SystemExit("trusted W07 jsonschema dependency archive digest changed")
archive_bytes = io.BytesIO(raw_archive)
try:
    archive = zipfile.ZipFile(archive_bytes)
except (OSError, zipfile.BadZipFile) as error:
    raise SystemExit("trusted W07 jsonschema dependency archive is invalid") from error
infos = archive.infolist()
if len(infos) != int(dependency_file_count) + 1:
    raise SystemExit("trusted W07 jsonschema dependency file count changed")
names = [info.filename for info in infos]
if len(names) != len(set(names)):
    raise SystemExit("trusted W07 jsonschema dependency contains duplicate paths")
allowed_top_levels = {
    "attr",
    "attrs",
    "jsonschema",
    "jsonschema_specifications",
    "referencing",
    "rpds",
    "typing_extensions.py",
}
sources = {}
total_uncompressed = 0
for info in infos:
    name = info.filename
    relative = pathlib.PurePosixPath(name)
    if (
        info.is_dir()
        or info.compress_type != zipfile.ZIP_STORED
        or info.flag_bits & 0x1
        or not name
        or "\\\\" in name
        or relative.is_absolute()
        or ".." in relative.parts
        or relative.parts[0] not in allowed_top_levels
    ):
        raise SystemExit("trusted W07 jsonschema dependency contains an unsafe path or entry")
    data = archive.read(info)
    if len(data) != info.file_size:
        raise SystemExit("trusted W07 jsonschema dependency entry size changed")
    sources[name] = data
    total_uncompressed += len(data)
if int(uncompressed_size) <= 0 or int(uncompressed_size) > 1_000_000:
    raise SystemExit("trusted W07 jsonschema dependency uncompressed size exceeds its bound")
if total_uncompressed != int(uncompressed_size):
    raise SystemExit("trusted W07 jsonschema dependency uncompressed size changed")
digest = hashlib.sha256()
for name in sorted(sources):
    data = sources[name]
    if name == "rpds/__init__.py":
        if hashlib.sha256(data).hexdigest() != rpds_sha256:
            raise SystemExit("trusted W07 rpds compatibility source changed")
        continue
    relative_bytes = name.encode("utf-8")
    digest.update(relative_bytes)
    digest.update(b"\\0")
    digest.update(str(len(data)).encode("ascii"))
    digest.update(b"\\0")
    digest.update(data)
if digest.hexdigest() != dependency_sha256:
    raise SystemExit("trusted W07 jsonschema dependency tree changed")

class MemoryResourceReader:
    def __init__(self, package_prefix):
        self.package_prefix = package_prefix

    def files(self):
        return zipfile.Path(archive, at=self.package_prefix)


class MemoryDependencyImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def __init__(self):
        self.packages = {
            name[:-12].replace("/", "."): name
            for name in sources
            if name.endswith("/__init__.py")
        }
        self.modules = {
            name[:-3].replace("/", "."): name
            for name in sources
            if name.endswith(".py") and not name.endswith("/__init__.py")
        }

    def find_spec(self, fullname, path=None, target=None):
        source_name = self.packages.get(fullname)
        is_package = source_name is not None
        if source_name is None:
            source_name = self.modules.get(fullname)
        if source_name is None:
            return None
        spec = importlib.util.spec_from_loader(fullname, self, is_package=is_package)
        if spec is None:
            raise ImportError(f"cannot create in-memory dependency spec for {fullname}")
        spec.origin = f"memory:///{source_name}"
        spec.has_location = True
        spec.loader_state = {"source_name": source_name, "is_package": is_package}
        if is_package:
            spec.submodule_search_locations = []
        return spec

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        state = module.__spec__.loader_state
        source_name = state["source_name"]
        origin = f"memory:///{source_name}"
        module.__file__ = origin
        if state["is_package"]:
            module.__path__ = []
        code = compile(sources[source_name], origin, "exec", dont_inherit=True)
        exec(code, module.__dict__)

    def get_resource_reader(self, fullname):
        source_name = self.packages.get(fullname)
        if source_name is None:
            return None
        return MemoryResourceReader(source_name.removesuffix("__init__.py"))


dependency_importer = MemoryDependencyImporter()
sys.meta_path.insert(0, dependency_importer)
program_path = pathlib.Path(program).resolve(strict=True)
if mode == "script":
    sys.argv = [str(program_path), *arguments]
    runpy.run_path(str(program_path), run_name="__main__")
    raise SystemExit(0)
elif mode != "memo" or len(arguments) != 1:
    raise SystemExit("unknown W07 replay mode")
response_path = pathlib.Path(arguments[0]).resolve(strict=True)
workflow_path = program_path
spec = importlib.util.spec_from_file_location("psp_c04_observed_w07_workflow", workflow_path)
if spec is None or spec.loader is None:
    raise SystemExit("observed W07 workflow is unavailable")
workflow = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = workflow
spec.loader.exec_module(workflow)
payload = workflow.V.load_payload(response_path)
verdict = workflow.V.validate(payload)
if verdict.state != "pass":
    raise SystemExit("observed W07 workflow did not accept the response set")
sys.stdout.write(workflow.decision_memo(payload, verdict))
"""
INDEPENDENT_REVIEWER_CLASSES = {"independent_human", "independent_model", "consented_collaborator"}
DEMO_ROOT_FIELDS = {"schema_version", "synthetic_only", "records"}
DEMO_RECORD_FIELDS = {
    "packet": {"type", "id", "synthetic", "authority"},
    "lease": {"type", "id", "synthetic", "packet_id"},
    "execution": {"type", "id", "synthetic", "lease_id"},
    "predicate": {"type", "id", "synthetic", "execution_id", "result"},
    "receipt": {"type", "id", "synthetic", "predicate_id"},
    "failure": {"type", "id", "synthetic", "predicate_id", "reason"},
    "recovery": {"type", "id", "synthetic", "failure_id", "action"},
    "harvest": {"type", "id", "synthetic", "receipt_id", "recovery_id", "outcome"},
}
DEMO_RELATIONSHIPS = {
    ("lease", "packet_id"): "packet",
    ("execution", "lease_id"): "lease",
    ("predicate", "execution_id"): "execution",
    ("receipt", "predicate_id"): "predicate",
    ("failure", "predicate_id"): "predicate",
    ("recovery", "failure_id"): "failure",
    ("harvest", "receipt_id"): "receipt",
    ("harvest", "recovery_id"): "recovery",
}
DEMO_ID_NAMESPACE = {
    "packet": "packet-demo",
    "lease": "lease-demo",
    "execution": "run-demo",
    "predicate": "predicate-demo",
    "receipt": "receipt-demo",
    "failure": "failure-demo",
    "recovery": "recovery-demo",
    "harvest": "harvest-demo",
}
DEMO_BOUNDED_VALUES = {
    "packet": {"authority": ["bounded"]},
    "predicate": {"result": ["pass", "fail", "blocked"]},
    "failure": {"reason": ["bounded synthetic failure"]},
    "recovery": {"action": ["narrow and rerun"]},
    "harvest": {"outcome": ["receipt retained"]},
}
P02_ACCEPTED_HEAD = "8faa5fb9899231ebf5f87e78bb171544c11b79d7"
C03_CURRENT_HEAD = "b6af8086c9050634313f519c29a6dfcb922c3721"
C03_MERGE_COMMIT = "8f89ad16ca1df84b00cb8227c88f368d0d64631a"
C03_ACCEPTED_P03_ANCESTOR = "c94bc3748fcf2d1dc802a4bae972df23d9a9fbec"
CANONICAL_PORTFOLIO = {"slug": "organvm-vii-kerygma/portfolio", "repository_id": 1155412125}
_W07_WORKFLOW: Any | None = None
EXPECTED_FLAGSHIPS = {
    "limen": {
        "claim_id": "C02-PROOF-LIMEN",
        "candidate_claim": "Limen demonstrates governed multi-agent delivery with public operating, failure, and verification receipts.",
        "evidence_wording": "Limen is a live orchestration and governance system, operating continuously in production in its owner's environment since May 2026.",
        "accepted_source_status": "verified",
    },
    "public_records": {
        "claim_id": "C02-PROOF-PUBLIC-RECORDS",
        "candidate_claim": "Four implemented state collectors (CA, TX, FL, and NY) sit on a broader architecture.",
        "evidence_wording": "Four implemented state collectors on a fifty-state architecture",
        "accepted_source_status": "repository_asserted_with_public_anchor",
    },
    "ai_chat_exporter": {
        "claim_id": "C02-PROOF-AI-CHAT-EXPORTER",
        "candidate_claim": "The public AI Chat Exporter surface presents five export formats without a server dependency.",
        "evidence_wording": "The public product surface presents five export formats: Markdown, HTML, JSON, PNG, and text.",
        "accepted_source_status": "verified",
    },
}
EXPECTED_FLAGSHIP_REPOSITORIES = {
    "limen": "organvm/limen",
    "public_records": "organvm-iii-ergon/public-record-data-scrapper",
    "ai_chat_exporter": "organvm-iii-ergon/a-i-chat--exporter",
}
EXPECTED_DEPENDENCY_BINDINGS = {
    "p02_live_registry": (
        P02_ACCEPTED_HEAD,
        "institutio/positioning/program.yaml",
        "de8c489667f2ad797dde60dfb84a9fa1fb4b0e16",
    ),
    "p02_flagship_selection": (
        P02_ACCEPTED_HEAD,
        "docs/positioning/flagship-proof-set.yaml",
        "5d4776efc7a811b0163cdfea5cf083409157feae",
    ),
    "p02_public_evidence": (
        P02_ACCEPTED_HEAD,
        "docs/positioning/evidence/flagship-evidence.yaml",
        "ce59d44794f44e0511436cbabbcd4fba1a938891",
    ),
    "p02_claim_policy": (
        P02_ACCEPTED_HEAD,
        "docs/positioning/program/CLAIM-CORRECTION-PROTOCOL.md",
        "57565f0d0dc72d2200b41be0e21fe6d323ec7f83",
    ),
    "p02_claims_ledger": (
        P02_ACCEPTED_HEAD,
        "docs/positioning/claims-ledger.md",
        "3e49114563075dcd6926e3b7f8fd24bf8b9c3fee",
    ),
    "c03_identity_offers": (
        C03_MERGE_COMMIT,
        "institutio/positioning/commercial-contract.yaml",
        "11ebfe5cb972c5b535059e5aa1f607ea64e90d17",
    ),
}
EXPECTED_OFFER_BINDINGS = {
    "agentic_delivery_audit": (
        "docs/positioning/offers/agentic-delivery-audit.md",
        "34bd10760afe6e8e8b778e0f6ad59c8aa1766097",
        ["L2", "L3"],
    ),
    "governance_install": (
        "docs/positioning/offers/governance-install.md",
        "2ddb46f8d2a4bc122720d4a2d890298ee1c5e380",
        ["L2", "L3"],
    ),
    "bounded_governance_retainer": (
        "docs/positioning/offers/bounded-delivery-governance-retainer.md",
        "1b46928d216fb2ed7299907a292ecc92511b0d60",
        ["L2", "L3"],
    ),
    "qualification_and_routing": (
        "docs/positioning/offers/qualification-and-routing.md",
        "1cf8bd4e42d96533973418f2de26e1aad313d205",
        ["L2", "L3"],
    ),
    "product_operating_partnership_review": (
        "docs/positioning/offers/product-operating-partnership-review.md",
        "9240e1fc1142eca6ca58d792f09581e1b514e046",
        ["L3"],
    ),
}
EXPECTED_SURFACE_LEVELS = {
    "portfolio_front_door": "L1",
    "portfolio_flagship": "L2",
    "resume": "L1",
    "personal_profile": "L1",
    "organization_profile": "L1",
    "flagship_repository": "L2",
}
FORBIDDEN_DEMO_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "credential",
    "customer",
    "email",
    "id_token",
    "passcode",
    "passphrase",
    "passwd",
    "password",
    "pwd",
    "private_path",
    "private_key",
    "private_repository",
    "recovery_code",
    "refresh_token",
    "secret",
    "session_cookie",
    "tasks_yaml_body",
    "token",
}
PUBLIC_FAILURE_CLASSES = {
    "dependency_failure",
    "external_gate",
    "human_gate",
    "policy_failure",
    "predicate_failure",
    "resource_limit",
    "verification_failure",
}
INDEPENDENCE_DISPOSITIONS = {
    "independent_peer_review",
    "independent_public_source",
    "independent_third_party",
}
FORBIDDEN_DEMO_VALUE_PATTERNS = (
    re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{8,}\b"),
    re.compile(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}\b"),
    re.compile(r"(?i)https?://[^\s/:@]+:[^\s/@]+@"),
    re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:password|secret|api[-_ ]?key|access[-_ ]?token|"
        r"refresh[-_ ]?token|id[-_ ]?token|authorization|session[-_ ]?cookie|"
        r"private[-_ ]?key|recovery[-_ ]?code)"
        r"(?:[ \t]*[:=][ \t]*|[ \t]+(?:is|was)[ \t]*[:=]?[ \t]*)"
        r"(?!(?:[\"'`][ \t]*)?(?:not|never|none|absent|redacted|withheld|unknown|unavailable|prohibited|required|unused)\b)\S+"
    ),
    re.compile(
        r"(?i)(?<![A-Za-z0-9])(?:customer|client|lead|contact|person|account|private)"
        r"(?:[-_:/]+(?:id[-_:/]+)?)(?=[A-Za-z0-9._:/-]*\d)[A-Za-z0-9][A-Za-z0-9._:/-]*"
    ),
)
SURFACE_PRIVATE_VALUE_PATTERNS = (
    *FORBIDDEN_DEMO_VALUE_PATTERNS,
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
)


def _reject_duplicate_json_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member: {key}")
        value[key] = child
    return value


def _loads_preflight_artifact(raw: str) -> object:
    return json.loads(raw, object_pairs_hook=_reject_duplicate_json_members)


def _contract_tls_context() -> ssl.SSLContext:
    """Use a fixed OS trust-bundle allowlist instead of ambient CA variables."""
    bundle = next((candidate for candidate in CONTRACT_CA_BUNDLE_CANDIDATES if candidate.is_file()), None)
    if bundle is None:
        raise OSError("contract-owned TLS trust bundle is unavailable")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(bundle))
    return context


def _contract_https_open(request: Request, *, timeout: int):
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=_contract_tls_context()))
    return opener.open(request, timeout=timeout)


def load_contract(path: Path) -> dict[str, Any]:
    data = _loads_preflight_artifact(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("contract root must be an object")
    return data


def _expected_leaf_ids() -> list[str]:
    return [f"PSP-P05-W0{index}" for index in range(1, 7)]


def validate(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    required_roots = {
        "schema_version",
        "chunk_id",
        "phase_id",
        "status",
        "counts_as_closure",
        "formalization_gate",
        "dependency_progress",
        "dependency_sources",
        "commercial_artifact_set",
        "program_binding",
        "claim_policy",
        "flagships",
        "sources",
        "surface_audit_model",
        "cost_failure_reproduction",
        "exact_head_receipt_plan",
        "synthetic_architecture_demo",
        "external_validation",
    }
    missing = sorted(required_roots - contract.keys())
    if missing:
        errors.append(f"missing root fields: {', '.join(missing)}")
    if contract.get("status") != "PREPARED/PREFLIGHT":
        errors.append("status must remain PREPARED/PREFLIGHT")
    if contract.get("counts_as_closure") is not False:
        errors.append("counts_as_closure must remain false")

    program_binding = contract.get("program_binding")
    if not isinstance(program_binding, dict):
        errors.append("program_binding must be an object")
    else:
        if program_binding.get("source_path") != "institutio/positioning/program.yaml":
            errors.append("program binding must name the canonical manifest")
        if program_binding.get("exact_head") != P02_ACCEPTED_HEAD:
            errors.append("program binding must use the accepted PSP-P02 head")
        if not FULL_HEAD.fullmatch(str(program_binding.get("expected_blob", ""))):
            errors.append("program binding requires the exact registry blob")
        if program_binding.get("canonical_portfolio") != CANONICAL_PORTFOLIO:
            errors.append("program binding must name the live canonical portfolio owner")
        audits = program_binding.get("leaf_audit")
        if not isinstance(audits, list):
            errors.append("program binding leaf audit must be a list")
        else:
            audited_ids = [row.get("work_id") for row in audits if isinstance(row, dict)]
            if audited_ids != _expected_leaf_ids():
                errors.append("program binding must audit PSP-P05-W01 through W06 in order")
            for row in audits:
                if not isinstance(row, dict):
                    continue
                work_id = row.get("work_id", "<unknown>")
                for field in ("outcome", "acceptance", "target_paths", "executable_artifacts", "residual_gates"):
                    if not row.get(field):
                        errors.append(f"{work_id} audit missing {field}")

    formalization = contract.get("formalization_gate")
    if not isinstance(formalization, dict):
        errors.append("formalization_gate must be an object")
    else:
        if formalization.get("required_chunks") != ["PSP-C03"]:
            errors.append("formalization must require only PSP-C03 after PSP-P02 closure")
        expected_dependencies = {
            "pyyaml": TRUSTED_PYYAML_DEPENDENCY,
            "w07_jsonschema": TRUSTED_W07_JSONSCHEMA_DEPENDENCY,
        }
        if formalization.get("trusted_python_dependencies") != expected_dependencies:
            errors.append("formalization must exact-bind the complete trusted Python dependency trees")

    progress = contract.get("dependency_progress")
    if not isinstance(progress, dict):
        errors.append("dependency_progress must be an object")
        c03: dict[str, Any] = {}
    else:
        p02 = progress.get("p02")
        if not isinstance(p02, dict) or p02.get("status") != "closed":
            errors.append("PSP-P02 must be recorded closed")
        elif p02.get("exact_head") != P02_ACCEPTED_HEAD:
            errors.append("PSP-P02 progress head mismatch")
        raw_c03 = progress.get("c03")
        if not isinstance(raw_c03, dict):
            errors.append("dependency_progress.c03 must be an object")
            c03 = {}
        else:
            c03 = raw_c03
    if c03:
        if c03.get("status") != "p03_w01_w06_closed_p04_merged_w07_open":
            errors.append("C03 progress status mismatch")
        if c03.get("exact_head") != C03_CURRENT_HEAD:
            errors.append("C03 current preflight head mismatch")
        if c03.get("merge_commit") != C03_MERGE_COMMIT:
            errors.append("C03 merged integration commit mismatch")
        if c03.get("accepted_p03_ancestor") != C03_ACCEPTED_P03_ANCESTOR:
            errors.append("C03 accepted P03 ancestor mismatch")
        if c03.get("closed_leaves") != [f"PSP-P03-W0{index}" for index in range(1, 7)]:
            errors.append("C03 closed leaves must be W01-W06")
        sole_unsatisfied = c03.get("sole_unsatisfied_leaf")
        if not isinstance(sole_unsatisfied, dict):
            errors.append("C03 sole_unsatisfied_leaf must be an object")
        else:
            if sole_unsatisfied.get("work_id") != "PSP-P03-W07":
                errors.append("C03 sole unsatisfied leaf must be PSP-P03-W07")
            if sole_unsatisfied.get("required_independent_readers") != 5:
                errors.append("C03 W07 must require five independent readers")
            if sole_unsatisfied.get("current_valid_readers") != 0:
                errors.append("C03 W07 valid-reader count must remain zero until genuine receipts exist")
            if sole_unsatisfied.get("synthetic_or_model_readers_allowed") is not False:
                errors.append("C03 W07 must reject synthetic or model readers")
            if sole_unsatisfied.get("outbound_from_c04") is not False:
                errors.append("C04 must not solicit W07 readers")
        receipt = c03.get("w06_receipt")
        if not isinstance(receipt, dict):
            errors.append("C03 w06_receipt must be an object")
        else:
            if receipt.get("url") != "https://github.com/organvm/limen/issues/2187#issuecomment-5271254820":
                errors.append("C03 W06 receipt URL mismatch")
            if receipt.get("sha256") != "260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617":
                errors.append("C03 W06 receipt SHA mismatch")

    dependencies = contract.get("dependency_sources", [])
    if not isinstance(dependencies, list):
        errors.append("dependency_sources must be a list")
        dependencies = []
    dependency_ids = {dependency.get("id") for dependency in dependencies if isinstance(dependency, dict)}
    if dependency_ids != set(EXPECTED_DEPENDENCY_BINDINGS):
        errors.append("dependency sources must bind the complete accepted P02 and current C03 artifact set")
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            errors.append("dependency source must be an object")
            continue
        dependency_id = dependency.get("id", "<unknown>")
        exact_head = dependency.get("exact_head")
        if not isinstance(exact_head, str) or not FULL_HEAD.fullmatch(exact_head):
            errors.append(f"dependency {dependency_id} requires a full exact head")
        expected_blob = dependency.get("expected_blob")
        if not isinstance(expected_blob, str) or not FULL_HEAD.fullmatch(expected_blob):
            errors.append(f"dependency {dependency_id} requires a full expected blob")
        if dependency.get("integration") != "exact_committed_head_only":
            errors.append(f"dependency {dependency_id} must integrate exact committed heads only")
        if not dependency.get("required_path"):
            errors.append(f"dependency {dependency_id} requires a source path")
    c03_dependency = next(
        (dependency for dependency in dependencies if dependency.get("id") == "c03_identity_offers"),
        {},
    )
    if c03_dependency.get("exact_head") != C03_MERGE_COMMIT:
        errors.append("C03 dependency source must use the reachable merged integration commit")
    if c03_dependency.get("branch") != "main":
        errors.append("C03 dependency source must use the authoritative merged main ref")
    if c03_dependency.get("merge_commit") != C03_MERGE_COMMIT:
        errors.append("C03 dependency source must bind its merged main commit")
    for dependency in dependencies:
        dependency_id = dependency.get("id", "<unknown>")
        expected_binding = EXPECTED_DEPENDENCY_BINDINGS.get(dependency_id)
        if (
            expected_binding
            and (
                dependency.get("exact_head"),
                dependency.get("required_path"),
                dependency.get("expected_blob"),
            )
            != expected_binding
        ):
            errors.append(f"dependency {dependency_id} is not pinned to its accepted upstream object")

    commercial_artifacts = contract.get("commercial_artifact_set")
    if not isinstance(commercial_artifacts, dict):
        errors.append("commercial_artifact_set must be an object")
    else:
        if commercial_artifacts.get("source_head") != C03_MERGE_COMMIT:
            errors.append("commercial artifact set must use the reachable C03 merged integration commit")
        artifacts = commercial_artifacts.get("artifacts")
        if not isinstance(artifacts, list):
            errors.append("commercial artifact set must contain an artifacts list")
        else:
            artifact_ids = {artifact.get("id") for artifact in artifacts if isinstance(artifact, dict)}
            if artifact_ids != set(EXPECTED_OFFER_BINDINGS):
                errors.append("commercial artifact set must bind the five generated offers")
            for artifact in artifacts:
                if not isinstance(artifact, dict):
                    errors.append("commercial artifact must be an object")
                    continue
                artifact_id = artifact.get("id", "<unknown>")
                if not artifact.get("path"):
                    errors.append(f"commercial artifact {artifact_id} requires a path")
                if not FULL_HEAD.fullmatch(str(artifact.get("expected_blob", ""))):
                    errors.append(f"commercial artifact {artifact_id} requires a full expected blob")
                if "L1" in artifact.get("levels", []):
                    errors.append(f"commercial artifact {artifact_id} must not expose an L1 offer payload")
                expected_offer = EXPECTED_OFFER_BINDINGS.get(artifact_id)
                if (
                    expected_offer
                    and (
                        artifact.get("path"),
                        artifact.get("expected_blob"),
                        artifact.get("levels"),
                    )
                    != expected_offer
                ):
                    errors.append(f"commercial artifact {artifact_id} is not pinned to the accepted C03 object")
            partnership = next(
                (artifact for artifact in artifacts if artifact.get("id") == "product_operating_partnership_review"),
                {},
            )
            if partnership.get("levels") != ["L3"] or partnership.get("public_front_door") is not False:
                errors.append("product operating partnership review must remain L3-only and off the public front door")

    sources = contract.get("sources", [])
    if not isinstance(sources, list):
        errors.append("sources must be a list")
        sources = []
    source_ids = {source.get("id") for source in sources if isinstance(source, dict)}
    for source in sources:
        if not isinstance(source, dict):
            errors.append("source must be an object")
            continue
        if not source.get("observed_at"):
            errors.append(f"source {source.get('id', '<unknown>')} has no observation date")
        if not source.get("max_age_days"):
            errors.append(f"source {source.get('id', '<unknown>')} has no freshness budget")

    flagships = contract.get("flagships", [])
    if not isinstance(flagships, list):
        errors.append("flagships must be a list")
        flagships = []
    flagship_ids: set[str] = set()
    for flagship in flagships:
        if not isinstance(flagship, dict):
            errors.append("flagship must be an object")
            continue
        flagship_id = flagship.get("id")
        if not flagship_id:
            errors.append("flagship missing id")
            continue
        if flagship_id in flagship_ids:
            errors.append(f"duplicate flagship id: {flagship_id}")
        flagship_ids.add(flagship_id)
        expected_flagship = EXPECTED_FLAGSHIPS.get(flagship_id)
        if expected_flagship:
            for field, expected_value in expected_flagship.items():
                if flagship.get(field) != expected_value:
                    errors.append(f"flagship {flagship_id} has stale {field}")
        if flagship.get("status") != "candidate":
            errors.append(f"flagship {flagship_id} must remain candidate in preflight")
        missing_sources = sorted(set(flagship.get("required_source_ids", [])) - source_ids)
        if missing_sources:
            errors.append(f"flagship {flagship_id} has unresolved sources: {', '.join(missing_sources)}")
        if not flagship.get("limitations"):
            errors.append(f"flagship {flagship_id} requires limitations")

    if flagship_ids != {"limen", "public_records", "ai_chat_exporter"}:
        errors.append("flagship set must be Limen, public_records, and ai_chat_exporter")

    withheld = " ".join(contract.get("claim_policy", {}).get("withheld_classes", [])).lower()
    for term in ("adoption", "revenue", "ranking", "percentile", "private"):
        if term not in withheld:
            errors.append(f"withheld classes must cover {term}")

    reproduction = contract.get("cost_failure_reproduction", {})
    if reproduction.get("status") != "executable_synthetic_fixture_only":
        errors.append("cost/failure reproduction must be executable with synthetic fixtures only")
    if not reproduction.get("runner") or not reproduction.get("fixture"):
        errors.append("cost/failure reproduction requires runner and fixture")
    if reproduction.get("review_schema") != COST_REVIEW_SCHEMA:
        errors.append("cost/failure reproduction must bind the independent review schema")
    reviewer_classes = reproduction.get("independent_reviewer_classes")
    if (
        not isinstance(reviewer_classes, list)
        or not all(isinstance(value, str) for value in reviewer_classes)
        or set(reviewer_classes) != INDEPENDENT_REVIEWER_CLASSES
    ):
        errors.append("cost/failure reproduction must bind the independent reviewer classes")
    public_failure_classes = reproduction.get("public_failure_classes")
    if (
        not isinstance(public_failure_classes, list)
        or not all(isinstance(value, str) for value in public_failure_classes)
        or set(public_failure_classes) != PUBLIC_FAILURE_CLASSES
    ):
        errors.append("cost/failure reproduction must declare the reviewed public failure vocabulary")

    receipt_plan = contract.get("exact_head_receipt_plan", {})
    if not receipt_plan.get("runner") or not receipt_plan.get("request_schema"):
        errors.append("exact-head receipt plan requires an executable runner and request schema")
    output_limit = receipt_plan.get("default_output_limit_bytes")
    if (
        not isinstance(output_limit, int)
        or isinstance(output_limit, bool)
        or not 1024 <= output_limit <= 10 * 1024 * 1024
    ):
        errors.append("exact-head receipt plan requires a bounded output budget")
    flagship_predicates = receipt_plan.get("flagship_predicates")
    if not isinstance(flagship_predicates, dict) or set(flagship_predicates) != set(EXPECTED_FLAGSHIPS):
        errors.append("exact-head receipt plan must bind every selected flagship predicate")
    else:
        for flagship_id, binding in flagship_predicates.items():
            if not isinstance(binding, dict) or set(binding) != {
                "repository",
                "default_branch",
                "predicate",
                "runtime_setup",
            }:
                errors.append(f"exact-head receipt predicate has an invalid schema: {flagship_id}")
                continue
            if binding.get("repository") != EXPECTED_FLAGSHIP_REPOSITORIES.get(flagship_id):
                errors.append(f"exact-head receipt predicate has the wrong repository: {flagship_id}")
            if not isinstance(binding.get("default_branch"), str) or not binding["default_branch"].strip():
                errors.append(f"exact-head receipt predicate requires a default branch: {flagship_id}")
            predicate = binding.get("predicate")
            if not isinstance(predicate, dict) or set(predicate) != {"argv", "timeout_seconds", "max_output_bytes"}:
                errors.append(f"exact-head receipt predicate command has an invalid schema: {flagship_id}")
                continue
            argv = predicate.get("argv")
            if (
                not isinstance(argv, list)
                or not argv
                or not all(isinstance(value, str) and value and "\0" not in value for value in argv)
            ):
                errors.append(f"exact-head receipt predicate command requires safe argv: {flagship_id}")
            timeout = predicate.get("timeout_seconds")
            if not isinstance(timeout, int) or isinstance(timeout, bool) or not 1 <= timeout <= 1800:
                errors.append(f"exact-head receipt predicate command requires a bounded timeout: {flagship_id}")
            bound_output = predicate.get("max_output_bytes")
            if (
                not isinstance(bound_output, int)
                or isinstance(bound_output, bool)
                or not 1024 <= bound_output <= 10 * 1024 * 1024
            ):
                errors.append(f"exact-head receipt predicate command requires bounded output: {flagship_id}")
            runtime_setup = binding.get("runtime_setup")
            if flagship_id == "limen":
                if runtime_setup != {"mode": "none"}:
                    errors.append("Limen exact-head receipt must use the no-dependency isolated runtime")
                continue
            expected_lockfile = {
                "public_records": "package-lock.json",
                "ai_chat_exporter": "pnpm-lock.yaml",
            }[flagship_id]
            expected_setup_argv = {
                "public_records": ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
                "ai_chat_exporter": ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"],
            }[flagship_id]
            if not isinstance(runtime_setup, dict) or set(runtime_setup) != {
                "mode",
                "lockfile",
                "argv",
                "timeout_seconds",
                "max_output_bytes",
            }:
                errors.append(f"exact-head receipt runtime setup has an invalid schema: {flagship_id}")
                continue
            if runtime_setup.get("mode") != "locked_install" or runtime_setup.get("lockfile") != expected_lockfile:
                errors.append(f"exact-head receipt runtime setup must bind the canonical lockfile: {flagship_id}")
            setup_argv = runtime_setup.get("argv")
            if setup_argv != expected_setup_argv:
                errors.append(
                    f"exact-head receipt runtime setup requires the contract-owned install argv: {flagship_id}"
                )
            setup_timeout = runtime_setup.get("timeout_seconds")
            if not isinstance(setup_timeout, int) or isinstance(setup_timeout, bool) or not 1 <= setup_timeout <= 1800:
                errors.append(f"exact-head receipt runtime setup requires a bounded timeout: {flagship_id}")
            setup_output = runtime_setup.get("max_output_bytes")
            if (
                not isinstance(setup_output, int)
                or isinstance(setup_output, bool)
                or not 1024 <= setup_output <= 10 * 1024 * 1024
            ):
                errors.append(f"exact-head receipt runtime setup requires bounded output: {flagship_id}")

    surface_model = contract.get("surface_audit_model", {})
    if surface_model.get("claim_inventory_source") != "p02_claims_ledger":
        errors.append("surface audit must discover material claims from the accepted claims ledger")
    if surface_model.get("surface_levels") != EXPECTED_SURFACE_LEVELS:
        errors.append("surface audit must bind every public surface to its canonical disclosure level")
    if surface_model.get("inspection_schema") != SURFACE_INSPECTION_SCHEMA:
        errors.append("surface audit must bind the canonical inspection schema")
    inspection_max_age_hours = surface_model.get("inspection_max_age_hours")
    if (
        not isinstance(inspection_max_age_hours, int)
        or isinstance(inspection_max_age_hours, bool)
        or not 1 <= inspection_max_age_hours <= 168
    ):
        errors.append("surface audit must declare a bounded inspection freshness budget")
    surfaces = surface_model.get("surfaces")
    surface_sources = surface_model.get("surface_sources")
    if surfaces != list(EXPECTED_SURFACE_LEVELS):
        errors.append("surface audit must bind the exact nonempty canonical surface denominator")
    if not isinstance(surfaces, list) or not isinstance(surface_sources, dict) or set(surface_sources) != set(surfaces):
        errors.append("surface audit must bind exactly one canonical source to every public surface")
    else:
        identities: set[str] = set()
        for surface in surfaces:
            binding = surface_sources.get(surface)
            if not isinstance(binding, dict) or set(binding) != {
                "source_kind",
                "source_locator",
                "receipt_path",
                "extractor",
            }:
                errors.append(f"surface source binding has an invalid exact schema: {surface}")
                continue
            identity = json.dumps(binding, sort_keys=True, separators=(",", ":"))
            if identity in identities:
                errors.append(f"surface source binding is reused across canonical surfaces: {surface}")
            identities.add(identity)
            if binding.get("source_kind") == "tracked_blob":
                if (
                    not _safe_relative_path(binding.get("source_locator"))
                    or binding.get("receipt_path") is not None
                    or binding.get("extractor") != "raw_text_v1"
                ):
                    errors.append(f"tracked surface source binding is invalid: {surface}")
            elif binding.get("source_kind") == "live_receipt":
                if (
                    not _credential_free_https_url(binding.get("source_locator"))
                    or not _safe_relative_path(binding.get("receipt_path"))
                    or binding.get("extractor") != "visible_text_v3"
                ):
                    errors.append(f"live surface source binding is invalid: {surface}")
            else:
                errors.append(f"surface source binding kind is unsupported: {surface}")

    demo = contract.get("synthetic_architecture_demo", {})
    if demo.get("status") != "contract_only_no_ui" or not demo.get("prohibited_inputs"):
        errors.append("architecture demo must remain contract-only with prohibited inputs")
    if not demo.get("fixture") or not demo.get("validator_mode"):
        errors.append("architecture demo requires a synthetic fixture and validator mode")
    if demo.get("id_namespace") != DEMO_ID_NAMESPACE:
        errors.append("architecture demo must bind the exact synthetic identifier namespace")
    if demo.get("bounded_values") != DEMO_BOUNDED_VALUES:
        errors.append("architecture demo must bind the exact bounded synthetic vocabulary")

    validation = contract.get("external_validation", {})
    if validation.get("status") != "rubric_only_no_outreach":
        errors.append("external validation must remain rubric-only/no-outreach")
    if validation.get("human_gate") != "HG-PUBLICATION-SEND":
        errors.append("external validation must retain HG-PUBLICATION-SEND")
    if validation.get("receipt_time_rule") != EXTERNAL_RECEIPT_TIME_RULE:
        errors.append("external validation must bind receipt time to the authenticated comment version")
    minimum_objects = validation.get("minimum_object_count")
    if not isinstance(minimum_objects, int) or isinstance(minimum_objects, bool) or minimum_objects < 2:
        errors.append("external validation must require at least two substantive objects")
    if validation.get("minimum_fields") != list(EXTERNAL_VALIDATION_MINIMUM_FIELDS):
        errors.append("external validation minimum fields must match the canonical exact schema")
    return errors


def _parse_date(value: str) -> date:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()


def source_freshness(contract: dict[str, Any], as_of: date) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source in contract.get("sources", []):
        observed = _parse_date(source["observed_at"])
        age_days = (as_of - observed).days
        declared = source.get("status")
        fresh_by_age = 0 <= age_days <= int(source["max_age_days"])
        current = declared == "current" and fresh_by_age
        rows.append(
            {
                "source_id": source["id"],
                "observed_at": source["observed_at"],
                "age_days": age_days,
                "max_age_days": source["max_age_days"],
                "declared_status": declared,
                "fresh_by_age": fresh_by_age,
                "current": current,
                "action": "eligible" if current else "refresh_or_withhold",
            }
        )
    return rows


def resolve_dependency_sources(contract: dict[str, Any], repository: Path = ROOT) -> list[dict[str, Any]]:
    """Resolve pinned dependency files directly from Git objects without merging branches."""
    rows: list[dict[str, Any]] = []
    for dependency in contract.get("dependency_sources", []):
        source_spec = f"{dependency['exact_head']}:{dependency['required_path']}"
        completed = subprocess.run(
            [str(_trusted_named_executable("git")), "show", source_spec],
            cwd=repository,
            env=_sanitized_git_environment(),
            check=False,
            capture_output=True,
            timeout=30,
        )
        if completed.returncode:
            rows.append(
                {
                    "source_id": dependency["id"],
                    "exact_head": dependency["exact_head"],
                    "path": dependency["required_path"],
                    "expected_blob": dependency["expected_blob"],
                    "resolved": False,
                    "reason": "missing_exact_head_object_or_path",
                }
            )
            continue
        blob = subprocess.run(
            [str(_trusted_named_executable("git")), "rev-parse", source_spec],
            cwd=repository,
            env=_sanitized_git_environment(),
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        actual_blob = blob.stdout.strip() if blob.returncode == 0 else None
        blob_match = actual_blob == dependency["expected_blob"]
        rows.append(
            {
                "source_id": dependency["id"],
                "exact_head": dependency["exact_head"],
                "path": dependency["required_path"],
                "expected_blob": dependency["expected_blob"],
                "resolved": blob_match,
                "reason": "resolved" if blob_match else "blob_mismatch",
                "blob": actual_blob,
                "blob_match": blob_match,
                "sha256": hashlib.sha256(completed.stdout).hexdigest(),
                "bytes": len(completed.stdout),
            }
        )
    return rows


def _read_git_object(repository: Path, head: str, path: str) -> tuple[str | None, str | None]:
    source_spec = f"{head}:{path}"
    content = subprocess.run(
        [str(_trusted_named_executable("git")), "show", source_spec],
        cwd=repository,
        env=_sanitized_git_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    blob = subprocess.run(
        [str(_trusted_named_executable("git")), "rev-parse", source_spec],
        cwd=repository,
        env=_sanitized_git_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if content.returncode or blob.returncode:
        return None, None
    return content.stdout, blob.stdout.strip()


def _read_git_object_bytes(repository: Path, head: str, path: str) -> tuple[bytes | None, str | None]:
    source_spec = f"{head}:{path}"
    content = subprocess.run(
        [str(_trusted_named_executable("git")), "show", source_spec],
        cwd=repository,
        env=_sanitized_git_environment(),
        check=False,
        capture_output=True,
        timeout=30,
    )
    blob = subprocess.run(
        [str(_trusted_named_executable("git")), "rev-parse", source_spec],
        cwd=repository,
        env=_sanitized_git_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if content.returncode or blob.returncode:
        return None, None
    return content.stdout, blob.stdout.strip()


def verify_upstream_bindings(contract: dict[str, Any], repository: Path = ROOT) -> dict[str, Any]:
    """Verify accepted registry, claim, commercial, and generated-offer objects without checkout mutation."""
    errors: list[str] = []
    checked: list[dict[str, Any]] = []
    binding = contract.get("program_binding", {})
    registry_content, registry_blob = _read_git_object(
        repository,
        str(binding.get("exact_head")),
        str(binding.get("source_path")),
    )
    if registry_blob != binding.get("expected_blob"):
        errors.append("accepted PSP-P02 registry blob mismatch")
    elif registry_content is None:
        errors.append("accepted PSP-P02 registry object is unavailable")
    else:
        required_registry_markers = (
            "canonical_slug: organvm-vii-kerygma/portfolio",
            "github_repository_id: 1155412125",
            "target_repo: organvm-vii-kerygma/portfolio",
        )
        missing_markers = [marker for marker in required_registry_markers if marker not in registry_content]
        if missing_markers:
            errors.append("accepted PSP-P02 registry does not bind the live portfolio owner")
    checked.append(
        {
            "id": "p02_live_registry",
            "head": binding.get("exact_head"),
            "path": binding.get("source_path"),
            "blob": registry_blob,
            "blob_match": registry_blob == binding.get("expected_blob"),
        }
    )

    dependencies = {row.get("id"): row for row in contract.get("dependency_sources", [])}
    claims_dependency = dependencies.get("p02_claims_ledger", {})
    ledger_content, ledger_blob = _read_git_object(
        repository,
        str(claims_dependency.get("exact_head")),
        str(claims_dependency.get("required_path")),
    )
    commercial_dependency = dependencies.get("c03_identity_offers", {})
    commercial_content, commercial_blob = _read_git_object(
        repository,
        str(commercial_dependency.get("exact_head")),
        str(commercial_dependency.get("required_path")),
    )
    checked.extend(
        [
            {
                "id": "p02_claims_ledger",
                "head": claims_dependency.get("exact_head"),
                "path": claims_dependency.get("required_path"),
                "blob": ledger_blob,
                "blob_match": ledger_blob == claims_dependency.get("expected_blob"),
            },
            {
                "id": "c03_identity_offers",
                "head": commercial_dependency.get("exact_head"),
                "path": commercial_dependency.get("required_path"),
                "blob": commercial_blob,
                "blob_match": commercial_blob == commercial_dependency.get("expected_blob"),
            },
        ]
    )
    if ledger_blob != claims_dependency.get("expected_blob") or ledger_content is None:
        errors.append("accepted PSP-P02 claims ledger binding failed")
    if commercial_blob != commercial_dependency.get("expected_blob") or commercial_content is None:
        errors.append("current C03 commercial contract binding failed")
    if ledger_content is not None and commercial_content is not None:
        for flagship in contract.get("flagships", []):
            claim_id = flagship.get("claim_id")
            if claim_id not in commercial_content:
                errors.append(f"claim {claim_id} is absent from the current C03 contract")
            if flagship.get("evidence_wording") not in ledger_content:
                errors.append(f"claim {claim_id} evidence wording is stale")
            if flagship.get("candidate_claim") not in commercial_content:
                errors.append(f"claim {claim_id} commercial wording is stale")

    artifact_set = contract.get("commercial_artifact_set", {})
    source_head = artifact_set.get("source_head")
    for artifact in artifact_set.get("artifacts", []):
        _content, actual_blob = _read_git_object(repository, str(source_head), str(artifact.get("path")))
        blob_match = actual_blob == artifact.get("expected_blob")
        checked.append(
            {
                "id": artifact.get("id"),
                "head": source_head,
                "path": artifact.get("path"),
                "blob": actual_blob,
                "blob_match": blob_match,
            }
        )
        if not blob_match:
            errors.append(f"commercial artifact {artifact.get('id')} blob mismatch")
    return {"status": "pass" if not errors else "fail", "errors": errors, "checked": checked}


def resolve_claims(
    contract: dict[str, Any],
    *,
    as_of: date | None = None,
    dependency_rows: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Resolve candidate claims to dated sources without promoting them."""
    as_of = as_of or datetime.now(timezone.utc).date()
    sources = {source["id"]: source for source in contract.get("sources", [])}
    freshness = {row["source_id"]: row for row in source_freshness(contract, as_of)}
    dependency_ok = all(row.get("resolved") for row in dependency_rows or [])
    publishable_statuses = set(contract.get("claim_policy", {}).get("publishable_statuses", []))
    resolved: list[dict[str, Any]] = []
    for flagship in contract.get("flagships", []):
        source_rows = [
            sources[source_id] for source_id in flagship.get("required_source_ids", []) if source_id in sources
        ]
        current_sources = bool(source_rows) and all(freshness[row["id"]]["current"] for row in source_rows)
        source_status = flagship.get("accepted_source_status")
        publishable = (
            source_status in publishable_statuses
            and current_sources
            and dependency_ok
            and contract.get("status") != "PREPARED/PREFLIGHT"
        )
        reasons: list[str] = []
        if contract.get("status") == "PREPARED/PREFLIGHT":
            reasons.append("c04_formalization_pending")
        if source_status not in publishable_statuses:
            reasons.append("source_status_not_publishable")
        if not current_sources:
            reasons.append("source_refresh_required")
        if dependency_rows is not None and not dependency_ok:
            reasons.append("dependency_source_unresolved")
        resolved.append(
            {
                "claim_id": flagship["claim_id"],
                "flagship_id": flagship["id"],
                "candidate_claim": flagship["candidate_claim"],
                "source_ids": [row["id"] for row in source_rows],
                "observation_dates": sorted({row["observed_at"] for row in source_rows}),
                "status": source_status,
                "max_disclosure": flagship["max_disclosure"],
                "limitations": flagship["limitations"],
                "publishable": publishable,
                "reason_codes": reasons,
                "action": "eligible_for_surface_audit" if publishable else "withhold_until_refresh_and_formalization",
            }
        )
    return resolved


def build_surface_audit_skeleton(contract: dict[str, Any]) -> list[dict[str, Any]]:
    """Create the complete surface-by-claim denominator without touching public copy."""
    rows: list[dict[str, Any]] = []
    claims = discover_material_claims(contract)
    for surface in contract.get("surface_audit_model", {}).get("surfaces", []):
        for claim in claims:
            rows.append(
                {
                    "surface": surface,
                    "claim_id": claim["claim_id"],
                    "claim_text": claim["candidate_claim"],
                    "presence": "not_audited",
                    "source_ids": claim["source_ids"],
                    "observed_at": claim["observation_dates"],
                    "status": claim["status"],
                    "disclosure_level": claim["max_disclosure"],
                    "canonical_or_drift": "not_audited",
                    "contains_private_material": None,
                    "action": claim["action"],
                }
            )
    return rows


def _markdown_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _ledger_action(*dispositions: str) -> str:
    boundary = " ".join(dispositions).lower()
    unsafe_markers = (
        "conflicted",
        "contradicted",
        "do not publish",
        "ignored",
        "never use",
        "not yet published",
        "not_established",
        "nowhere",
        "remove",
        "superseded",
        "unsupported",
        "unverified",
        "withhold",
        "withheld",
    )
    return "withhold_or_remove" if any(marker in boundary for marker in unsafe_markers) else "audit_canonical_wording"


def _is_markdown_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)


def _ledger_material_claims(
    content: str,
    source_id: str,
    *,
    formalization_pending: bool,
) -> list[dict[str, Any]]:
    reconciled = re.search(r"Reconciled (\d{4}-\d{2}-\d{2})", content)
    observed_at = [reconciled.group(1)] if reconciled else []
    in_claim_section = False
    claims: list[dict[str, Any]] = []
    seen_text: set[str] = set()
    lines = content.splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^## [1-9]\.", line):
            in_claim_section = True
            continue
        if line.startswith("## "):
            in_claim_section = False
        if not in_claim_section or not line.startswith("|"):
            continue
        cells = _markdown_cells(line)
        next_cells = (
            _markdown_cells(lines[index + 1]) if index + 1 < len(lines) and lines[index + 1].startswith("|") else []
        )
        if (
            len(cells) < 3
            or _is_markdown_separator(cells)
            or _is_markdown_separator(next_cells)
            or cells[1].lower() == "status"
        ):
            continue
        claim_text = cells[0]
        if not claim_text or claim_text in seen_text:
            continue
        seen_text.add(claim_text)
        status = cells[1]
        public_safe_wording = cells[-2] if len(cells) >= 5 else claim_text
        tier = cells[-1] if len(cells) >= 5 else "ledger_only"
        action = _ledger_action(*cells[1:])
        publishable = action == "audit_canonical_wording" and not formalization_pending
        reason_codes = ["accepted_claims_ledger_inventory"]
        if formalization_pending:
            reason_codes.append("c04_formalization_pending")
        claim_id = f"LEDGER-{hashlib.sha256(claim_text.encode()).hexdigest()[:16].upper()}"
        claims.append(
            {
                "claim_id": claim_id,
                "flagship_id": None,
                "candidate_claim": claim_text,
                "source_ids": [source_id],
                "observation_dates": observed_at,
                "status": status,
                "max_disclosure": tier,
                "limitations": [public_safe_wording],
                "publishable": publishable,
                "reason_codes": reason_codes,
                "action": action
                if publishable or action != "audit_canonical_wording"
                else "withhold_until_refresh_and_formalization",
            }
        )
    return claims


def discover_material_claims(contract: dict[str, Any], repository: Path = ROOT) -> list[dict[str, Any]]:
    """Discover the accepted ledger denominator, then retain the selected flagship proof cells."""
    dependencies = {row.get("id"): row for row in contract.get("dependency_sources", []) if isinstance(row, dict)}
    source_id = str(contract.get("surface_audit_model", {}).get("claim_inventory_source", ""))
    dependency = dependencies.get(source_id, {})
    content, blob = _read_git_object(
        repository,
        str(dependency.get("exact_head", "")),
        str(dependency.get("required_path", "")),
    )
    if content is None or blob != dependency.get("expected_blob"):
        raise ValueError("accepted claims-ledger inventory is unavailable or stale")
    claims = _ledger_material_claims(
        content,
        source_id,
        formalization_pending=contract.get("status") == "PREPARED/PREFLIGHT",
    )
    claims.extend(resolve_claims(contract))
    if not claims:
        raise ValueError("material public-claim inventory is empty")
    return sorted(claims, key=lambda row: str(row["claim_id"]))


def _disclosure_floor(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    levels = [int(match) for match in re.findall(r"\bL([123])\b", value.upper())]
    return min(levels) if levels else None


def _safe_relative_path(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or "\0" in value or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts and path.as_posix() == value


def _credential_free_https_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        return False
    parsed = urlsplit(value)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


_CLAIM_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "this",
    "to",
    "was",
    "with",
}


def _normalized_surface_text(value: str) -> str:
    without_markup = re.sub(r"<[^>]+>", " ", html.unescape(value))
    return " ".join(re.findall(r"[a-z0-9]+", without_markup.lower()))


class _VisibleSurfaceParser(HTMLParser):
    _HIDDEN_TAGS = {"head", "script", "style", "template", "title", "noscript", "svg"}
    _ACTIVE_CONTENT_TAGS = {"applet", "embed", "iframe", "object", "script"}
    _EXECUTABLE_URI_ATTRIBUTES = {"action", "formaction", "href", "src", "xlink:href"}
    _VOID_TAGS = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }
    _CLAUSE_BOUNDARY_TAGS = {
        "article",
        "aside",
        "blockquote",
        "br",
        "dd",
        "details",
        "div",
        "dialog",
        "dl",
        "dt",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }
    _TABLE_PARSING_TAGS = {
        "caption",
        "col",
        "colgroup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
    }
    _HIDDEN_STYLE = re.compile(
        r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*(?:hidden|collapse))"
        r"(?:\s*!important)?\s*(?:;|$)",
        re.IGNORECASE,
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_stack: list[str] = []
        self._element_stack: list[str] = []
        self._closed_details: list[dict[str, int | bool | None]] = []
        self._visible_fragments: list[str] = []
        self._stylesheet_text_seen = False

    def _closed_details_hide_current(self) -> bool:
        for frame in self._closed_details:
            summary_index = frame["summary_index"]
            if (
                not isinstance(summary_index, int)
                or len(self._element_stack) <= summary_index
                or self._element_stack[summary_index] != "summary"
            ):
                return True
        return False

    @classmethod
    def _attributes_hide_element(cls, attrs: list[tuple[str, str | None]]) -> bool:
        normalized: dict[str, str | None] = {}
        for name, value in attrs:
            key = name.casefold()
            if key.startswith("on") and len(key) > 2:
                raise ValueError("surface visibility requires executable event-handler evaluation")
            if (
                key in cls._EXECUTABLE_URI_ATTRIBUTES
                and isinstance(value, str)
                and value.lstrip().casefold().startswith("javascript:")
            ):
                raise ValueError("surface visibility requires executable URI evaluation")
            if key in {"hidden", "aria-hidden", "style", "rel", "open", "popover"} and key in normalized:
                raise ValueError("surface response duplicates a visibility or stylesheet-control attribute")
            normalized[key] = value
        if "hidden" in normalized:
            return True
        aria_hidden = normalized.get("aria-hidden")
        if isinstance(aria_hidden, str) and aria_hidden.strip().casefold() == "true":
            return True
        style = normalized.get("style")
        if not isinstance(style, str):
            return False
        if "/*" in style or "\\" in style:
            raise ValueError("surface response uses obfuscated inline visibility styling")
        if cls._HIDDEN_STYLE.search(style) is not None:
            return True
        if style.strip():
            raise ValueError("surface visibility requires unsupported inline style evaluation")
        return False

    def _reject_closed_details_table_ambiguity(self, tag: str) -> None:
        if self._closed_details and tag in self._TABLE_PARSING_TAGS:
            raise ValueError("surface response has table parsing ambiguity inside closed details")

    @staticmethod
    def _attributes_reference_stylesheet(attrs: list[tuple[str, str | None]]) -> bool:
        for name, value in attrs:
            if name.casefold() == "rel" and isinstance(value, str):
                return "stylesheet" in value.casefold().split()
        return False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        if normalized in self._ACTIVE_CONTENT_TAGS:
            raise ValueError("surface visibility requires executable active-content evaluation")
        self._reject_closed_details_table_ambiguity(normalized)
        attributes_hidden = self._attributes_hide_element(attrs)
        if normalized == "link" and self._attributes_reference_stylesheet(attrs):
            raise ValueError("surface visibility requires external stylesheet evaluation")
        attribute_names = {name.casefold() for name, _value in attrs}
        if normalized == "summary":
            for frame in reversed(self._closed_details):
                if frame["details_index"] == len(self._element_stack) - 1 and not frame["summary_seen"]:
                    frame["summary_seen"] = True
                    frame["summary_index"] = len(self._element_stack)
                    break
        if normalized not in self._VOID_TAGS:
            self._element_stack.append(normalized)
        user_agent_hidden = (
            (normalized == "dialog" and "open" not in attribute_names)
            or "popover" in attribute_names
            or self._closed_details_hide_current()
        )
        hidden = bool(self._hidden_stack) or normalized in self._HIDDEN_TAGS or attributes_hidden or user_agent_hidden
        if hidden and normalized not in self._VOID_TAGS:
            self._hidden_stack.append(normalized)
        elif not hidden:
            self._visible_fragments.append("\n" if normalized in self._CLAUSE_BOUNDARY_TAGS else " ")
        if normalized == "details" and "open" not in attribute_names:
            self._closed_details.append(
                {
                    "details_index": len(self._element_stack) - 1,
                    "summary_seen": False,
                    "summary_index": None,
                }
            )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized = tag.casefold()
        if normalized in self._ACTIVE_CONTENT_TAGS:
            raise ValueError("surface visibility requires executable active-content evaluation")
        self._reject_closed_details_table_ambiguity(normalized)
        if normalized not in self._VOID_TAGS:
            raise ValueError("surface response self-closes a non-void HTML element")
        attributes_hidden = self._attributes_hide_element(attrs)
        if normalized == "link" and self._attributes_reference_stylesheet(attrs):
            raise ValueError("surface visibility requires external stylesheet evaluation")
        hidden = bool(self._hidden_stack) or normalized in self._HIDDEN_TAGS or attributes_hidden
        if not hidden:
            self._visible_fragments.append("\n" if normalized in self._CLAUSE_BOUNDARY_TAGS else " ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.casefold()
        if self._hidden_stack:
            if self._hidden_stack[-1] != normalized:
                raise ValueError("surface response has malformed hidden HTML regions")
            self._hidden_stack.pop()
        elif normalized in self._HIDDEN_TAGS:
            raise ValueError("surface response has malformed hidden HTML regions")
        else:
            self._visible_fragments.append("\n" if normalized in self._CLAUSE_BOUNDARY_TAGS else " ")
        if normalized not in self._VOID_TAGS:
            if not self._element_stack or self._element_stack[-1] != normalized:
                if self._closed_details:
                    raise ValueError("surface response has malformed closed-details HTML")
            else:
                closing_index = len(self._element_stack) - 1
                self._element_stack.pop()
                if normalized == "details" and self._closed_details:
                    if self._closed_details[-1]["details_index"] != closing_index:
                        raise ValueError("surface response has malformed closed-details HTML")
                    self._closed_details.pop()

    def handle_data(self, data: str) -> None:
        if self._hidden_stack and self._hidden_stack[-1] == "style" and data.strip():
            self._stylesheet_text_seen = True
        if not self._hidden_stack and not self._closed_details_hide_current():
            self._visible_fragments.append(data)

    def visible_text(self) -> str:
        if self._hidden_stack or self._closed_details:
            raise ValueError("surface response has unterminated hidden HTML regions")
        if self._stylesheet_text_seen:
            raise ValueError("surface visibility requires stylesheet evaluation")
        return " ".join(self._visible_fragments)


def _canonical_surface_extraction(content: bytes, extractor: str) -> bytes:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("surface response is not UTF-8 text") from exc
    if extractor in {"visible_text_v2", "visible_text_v3"}:
        parser = _VisibleSurfaceParser()
        parser.feed(text)
        parser.close()
        text = parser.visible_text()
    elif extractor == "raw_text_v1":
        text = html.unescape(text)
    else:
        raise ValueError("surface source uses an unsupported canonical extractor")
    if extractor == "visible_text_v3":
        normalized = "\n".join(
            normalized_line for line in text.splitlines() if (normalized_line := " ".join(line.split()))
        )
    else:
        normalized = " ".join(text.split())
    return (normalized + "\n").encode("utf-8")


def _surface_claim_scan(
    inspected_text: str,
    expected_rows: dict[tuple[str, str], dict[str, Any]],
    surface: str,
) -> tuple[list[str], list[str]]:
    segments = [
        normalized
        for raw in re.split(r"[\n\r.!?;]+", html.unescape(inspected_text))
        if (normalized := _normalized_surface_text(raw))
    ]
    matched: list[str] = []
    drifted: list[str] = []
    for (row_surface, claim_id), row in expected_rows.items():
        if row_surface != surface or not isinstance(row.get("claim_text"), str):
            continue
        canonical = _normalized_surface_text(row["claim_text"])
        if not canonical:
            continue
        if any(f" {canonical} " in f" {segment} " for segment in segments):
            if _canonical_claim_is_negated(inspected_text, canonical):
                drifted.append(claim_id)
            else:
                matched.append(claim_id)
            continue
        canonical_tokens = {
            token
            for token in canonical.split()
            if token not in _CLAIM_STOPWORDS and (len(token) >= 3 or token.isdigit())
        }
        canonical_sequence = canonical.split()
        if len(canonical_tokens) < 2 or len(canonical_sequence) < 3:
            continue
        for segment in segments:
            segment_sequence = segment.split()
            segment_tokens = set(segment_sequence)
            overlap = canonical_tokens & segment_tokens
            coverage = len(overlap) / len(canonical_tokens)
            matcher = SequenceMatcher(
                None,
                canonical_sequence,
                segment_sequence,
                autojunk=False,
            )
            ordered_coverage = sum(block.size for block in matcher.get_matching_blocks()) / len(canonical_sequence)
            minimum_overlap = min(3, len(canonical_tokens))
            if len(overlap) >= minimum_overlap and coverage >= 0.5 and ordered_coverage >= 0.5:
                drifted.append(claim_id)
                break
    return sorted(matched), sorted(set(drifted))


def _canonical_claim_is_negated(inspected_text: str, canonical: str) -> bool:
    canonical_tokens = canonical.split()
    if not canonical_tokens:
        return False
    occurrence_results: list[bool] = []
    for raw_segment in re.split(r"[\n\r.!?;]+", html.unescape(inspected_text)):
        segment = _normalized_surface_text(raw_segment)
        segment_tokens = segment.split()
        width = len(canonical_tokens)
        for start in range(len(segment_tokens) - width + 1):
            if segment_tokens[start : start + width] != canonical_tokens:
                continue
            prefix = segment_tokens[:start]
            suffix = segment_tokens[start + width :]
            negated = bool(prefix[-1:] and prefix[-1] in {"cannot", "cant", "never", "no", "not", "without"})
            prefix_text = " ".join(prefix[-12:])
            if re.search(r"\b(?:no|without)\s+(?:credible\s+)?evidence\b(?:\s+[a-z0-9]+){0,8}$", prefix_text):
                negated = True
            if set(suffix[:4]).intersection(
                {
                    "contradicted",
                    "contradicts",
                    "denied",
                    "false",
                    "incorrect",
                    "rejected",
                    "untrue",
                    "wrong",
                }
            ):
                negated = True
            occurrence_results.append(negated)
    return bool(occurrence_results) and all(occurrence_results)


def _surface_contains_private_material(inspected_text: str) -> bool:
    return any(pattern.search(inspected_text) for pattern in SURFACE_PRIVATE_VALUE_PATTERNS)


def _fetch_bounded_public_surface(source_url: str) -> bytes:
    request = Request(
        source_url,
        headers={"Accept": "text/html,text/plain", "User-Agent": "limen-positioning-proof-preflight"},
    )
    with _contract_https_open(request, timeout=30) as response:
        if response.geturl() != source_url:
            raise ValueError("live surface redirected away from its contract-owned URL")
        content = response.read(1_048_577)
    if len(content) > 1_048_576:
        raise ValueError("live surface exceeds the bounded response size")
    return content


def _surface_inspection_errors(
    contract: dict[str, Any],
    inspections: object,
    expected_rows: dict[tuple[str, str], dict[str, Any]],
    repository: Path,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    errors: list[str] = []
    expected_surfaces = contract.get("surface_audit_model", {}).get("surfaces", [])
    if expected_surfaces != list(EXPECTED_SURFACE_LEVELS):
        return ["surface audit requires the exact nonempty canonical surface denominator"], {}
    if not isinstance(inspections, dict) or set(inspections) != set(expected_surfaces):
        return ["surface_inspections must bind exactly one inspection per canonical surface"], {}
    source_bindings = contract.get("surface_audit_model", {}).get("surface_sources")
    if not isinstance(source_bindings, dict) or set(source_bindings) != set(expected_surfaces):
        return ["surface source registry must bind exactly every canonical surface"], {}
    surface_model = contract.get("surface_audit_model", {})
    max_age_hours = surface_model.get("inspection_max_age_hours")
    if not isinstance(max_age_hours, int) or isinstance(max_age_hours, bool) or not 1 <= max_age_hours <= 168:
        errors.append("surface inspection freshness budget must be a bounded integer hour count")
        max_age_hours = 0
    try:
        default_branch, authoritative_head = _canonical_limen_remote_head()
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        errors.append(f"canonical surface inspection authority is unavailable: {exc}")
        default_branch = None
        authoritative_head = None
    binding_fields = {"source_kind", "source_locator", "receipt_path", "extractor"}
    binding_identities: set[str] = set()
    for surface in expected_surfaces:
        binding = source_bindings.get(surface)
        if not isinstance(binding, dict) or set(binding) != binding_fields:
            errors.append(f"surface source binding has an invalid exact schema: {surface}")
            continue
        identity = json.dumps(
            {field: binding.get(field) for field in sorted(binding_fields)},
            sort_keys=True,
            separators=(",", ":"),
        )
        if identity in binding_identities:
            errors.append(f"surface source binding is reused across canonical surfaces: {surface}")
        binding_identities.add(identity)
        if binding.get("source_kind") == "tracked_blob":
            if (
                not _safe_relative_path(binding.get("source_locator"))
                or binding.get("receipt_path") is not None
                or binding.get("extractor") != "raw_text_v1"
            ):
                errors.append(f"tracked surface source binding is invalid: {surface}")
        elif binding.get("source_kind") == "live_receipt":
            if (
                not _credential_free_https_url(binding.get("source_locator"))
                or not _safe_relative_path(binding.get("receipt_path"))
                or binding.get("extractor") != "visible_text_v3"
            ):
                errors.append(f"live surface source binding is invalid: {surface}")
        else:
            errors.append(f"surface source binding kind is unsupported: {surface}")
    canonical_objects: dict[str, tuple[bytes | None, str | None]] = {}
    if default_branch is not None and authoritative_head is not None:
        authority_paths = {
            str(binding.get("source_locator"))
            if binding.get("source_kind") == "tracked_blob"
            else str(binding.get("receipt_path"))
            for binding in source_bindings.values()
            if isinstance(binding, dict)
            and (
                (binding.get("source_kind") == "tracked_blob" and _safe_relative_path(binding.get("source_locator")))
                or (binding.get("source_kind") == "live_receipt" and _safe_relative_path(binding.get("receipt_path")))
            )
        }
        try:
            canonical_objects = _fetch_canonical_limen_objects(
                default_branch,
                authoritative_head,
                authority_paths,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            errors.append(f"canonical surface inspection objects are unavailable: {exc}")
    exact_fields = {
        "schema_version",
        "inspection_id",
        "surface",
        "source_kind",
        "source_locator",
        "receipt_path",
        "extractor",
        "observed_at",
        "exact_head",
        "blob_sha1",
        "extracted_text_sha256",
        "scanner",
        "scanner_version",
        "matched_claim_ids",
    }
    resolved: dict[str, dict[str, Any]] = {}
    seen_ids: set[str] = set()
    for surface in expected_surfaces:
        inspection = inspections.get(surface)
        if not isinstance(inspection, dict) or set(inspection) != exact_fields:
            errors.append(f"surface inspection has an invalid exact schema: {surface}")
            continue
        if inspection.get("schema_version") != SURFACE_INSPECTION_SCHEMA:
            errors.append(f"surface inspection has an unsupported schema: {surface}")
        inspection_id = inspection.get("inspection_id")
        if not isinstance(inspection_id, str) or not inspection_id.strip() or "\0" in inspection_id:
            errors.append(f"surface inspection requires a nonblank inspection_id: {surface}")
        elif inspection_id in seen_ids:
            errors.append(f"surface inspection_id is duplicated: {inspection_id}")
        else:
            seen_ids.add(inspection_id)
        if inspection.get("surface") != surface:
            errors.append(f"surface inspection identity differs from its canonical surface: {surface}")
        observed_at = inspection.get("observed_at")
        try:
            observed = datetime.fromisoformat(str(observed_at).replace("Z", "+00:00"))
            if not isinstance(observed_at, str) or observed.tzinfo is None:
                raise ValueError
        except ValueError:
            errors.append(f"surface inspection observed_at must be RFC3339 with a timezone: {surface}")
        else:
            now = datetime.now(timezone.utc)
            if observed > now:
                errors.append(f"surface inspection cannot be future-dated: {surface}")
            elif max_age_hours and observed < now - timedelta(hours=max_age_hours):
                errors.append(f"surface inspection is older than the contract-owned freshness budget: {surface}")
        if inspection.get("scanner") != SURFACE_SCANNER or inspection.get("scanner_version") != SURFACE_SCANNER_VERSION:
            errors.append(f"surface inspection requires the canonical scanner and version: {surface}")
        exact_head = inspection.get("exact_head")
        blob_sha1 = inspection.get("blob_sha1")
        if not isinstance(exact_head, str) or not FULL_HEAD.fullmatch(exact_head):
            errors.append(f"surface inspection requires a full exact head: {surface}")
        elif authoritative_head is not None and exact_head != authoritative_head:
            errors.append(f"surface inspection head is not the authoritative remote default head: {surface}")
        if not isinstance(blob_sha1, str) or not FULL_HEAD.fullmatch(blob_sha1):
            errors.append(f"surface inspection requires a full blob identity: {surface}")

        source_kind = inspection.get("source_kind")
        source_locator = inspection.get("source_locator")
        receipt_path = inspection.get("receipt_path")
        extractor = inspection.get("extractor")
        extracted_text_sha256 = inspection.get("extracted_text_sha256")
        binding = source_bindings.get(surface)
        if isinstance(binding, dict) and any(
            inspection.get(field) != binding.get(field)
            for field in ("source_kind", "source_locator", "receipt_path", "extractor")
        ):
            errors.append(f"surface inspection differs from the contract-owned source binding: {surface}")
        object_path: object = None
        if source_kind == "tracked_blob":
            if not _safe_relative_path(source_locator):
                errors.append(f"tracked surface inspection requires a safe repository path: {surface}")
            if receipt_path is not None or extractor != "raw_text_v1":
                errors.append(f"tracked surface inspection must not declare live-receipt fields: {surface}")
            if not isinstance(extracted_text_sha256, str) or not SHA256.fullmatch(extracted_text_sha256):
                errors.append(f"tracked surface inspection requires a canonical extraction SHA-256: {surface}")
            object_path = source_locator
        elif source_kind == "live_receipt":
            if not _credential_free_https_url(source_locator):
                errors.append(f"live surface inspection requires a credential-free HTTPS URL: {surface}")
            if not _safe_relative_path(receipt_path):
                errors.append(f"live surface inspection requires an immutable tracked receipt path: {surface}")
            if extractor != "visible_text_v3":
                errors.append(f"live surface inspection requires the contract-owned visible-text extractor: {surface}")
            if not isinstance(extracted_text_sha256, str) or not SHA256.fullmatch(extracted_text_sha256):
                errors.append(f"live surface inspection requires a canonical extraction SHA-256: {surface}")
            object_path = receipt_path
        else:
            errors.append(f"surface inspection source_kind is unsupported: {surface}")

        content: bytes | None = None
        actual_blob: str | None = None
        if (
            isinstance(exact_head, str)
            and FULL_HEAD.fullmatch(exact_head)
            and isinstance(object_path, str)
            and _safe_relative_path(object_path)
        ):
            content, actual_blob = canonical_objects.get(object_path, (None, None))
        if content is None or actual_blob != blob_sha1:
            errors.append(f"surface inspection source blob is unavailable or drifted: {surface}")
            content = b""
        if len(content) > 1_048_576:
            errors.append(f"surface inspection source exceeds the bounded response size: {surface}")
        inspected_content = b""
        if source_kind == "tracked_blob" and extractor == "raw_text_v1":
            try:
                inspected_content = _canonical_surface_extraction(content, extractor)
            except ValueError as exc:
                errors.append(f"tracked surface extraction failed: {surface}: {exc}")
            if (
                isinstance(extracted_text_sha256, str)
                and SHA256.fullmatch(extracted_text_sha256)
                and hashlib.sha256(inspected_content).hexdigest() != extracted_text_sha256
            ):
                errors.append(f"tracked surface canonical extraction digest differs from the bound source: {surface}")
        if source_kind == "live_receipt" and extractor == "visible_text_v3":
            inspected_content = content
            if (
                isinstance(extracted_text_sha256, str)
                and SHA256.fullmatch(extracted_text_sha256)
                and hashlib.sha256(content).hexdigest() != extracted_text_sha256
            ):
                errors.append(f"surface inspection extraction receipt digest is unavailable or drifted: {surface}")
            try:
                canonical_receipt = _canonical_surface_extraction(content, "raw_text_v1")
            except ValueError as exc:
                errors.append(f"surface inspection extraction receipt is invalid: {surface}: {exc}")
            else:
                if canonical_receipt != content:
                    errors.append(f"surface inspection extraction receipt is not canonical text: {surface}")
            if isinstance(source_locator, str) and _credential_free_https_url(source_locator):
                try:
                    live_content = _fetch_bounded_public_surface(source_locator)
                except (HTTPException, OSError, ValueError) as exc:
                    errors.append(f"live surface inspection could not reproduce the current response: {surface}: {exc}")
                else:
                    try:
                        raw_live_text = html.unescape(live_content.decode("utf-8"))
                    except UnicodeDecodeError:
                        errors.append(f"live surface raw response is not UTF-8 text: {surface}")
                    else:
                        if _surface_contains_private_material(raw_live_text):
                            errors.append(f"live surface raw response contains private material: {surface}")
                    try:
                        live_extraction = _canonical_surface_extraction(live_content, extractor)
                    except ValueError as exc:
                        errors.append(f"live surface canonical extraction failed: {surface}: {exc}")
                    else:
                        if (
                            isinstance(extracted_text_sha256, str)
                            and SHA256.fullmatch(extracted_text_sha256)
                            and hashlib.sha256(live_extraction).hexdigest() != extracted_text_sha256
                        ):
                            errors.append(f"live surface visible claims differ from the tracked extraction: {surface}")
                        inspected_content = live_extraction
        try:
            inspected_text = inspected_content.decode("utf-8")
        except UnicodeDecodeError:
            errors.append(f"surface inspection source is not UTF-8 text: {surface}")
            inspected_text = ""

        expected_claim_ids = {claim_id for row_surface, claim_id in expected_rows if row_surface == surface}
        matched_claim_ids = inspection.get("matched_claim_ids")
        valid_matches = (
            isinstance(matched_claim_ids, list)
            and all(isinstance(claim_id, str) and claim_id in expected_claim_ids for claim_id in matched_claim_ids)
            and len(matched_claim_ids) == len(set(matched_claim_ids))
        )
        if not valid_matches:
            errors.append(f"surface inspection matched_claim_ids are invalid: {surface}")
            matched_claim_ids = []
        recomputed_matches, drifted_claim_ids = _surface_claim_scan(inspected_text, expected_rows, surface)
        contains_private_material = _surface_contains_private_material(inspected_text)
        if contains_private_material:
            errors.append(f"surface inspection found private material in the bound source: {surface}")
        if drifted_claim_ids:
            errors.append(
                f"surface inspection found noncanonical material claim variants: {surface}: "
                + ", ".join(drifted_claim_ids)
            )
        if sorted(matched_claim_ids) != recomputed_matches:
            errors.append(f"surface inspection matched claims differ from the bound source: {surface}")
        if isinstance(inspection_id, str):
            resolved[surface] = {
                "inspection_id": inspection_id,
                "matched_claim_ids": set(matched_claim_ids),
                "contains_private_material": contains_private_material,
            }
    return errors, resolved


def audit_surface_manifest(
    contract: dict[str, Any],
    manifest: dict[str, Any],
    repository: Path = ROOT,
) -> dict[str, Any]:
    skeleton = build_surface_audit_skeleton(contract)
    expected_rows = {(row["surface"], row["claim_id"]): row for row in skeleton}
    expected = set(expected_rows)
    supplied_rows = manifest.get("rows") if isinstance(manifest, dict) else None
    errors: list[str] = []
    if not isinstance(manifest, dict) or set(manifest) != {"rows", "surface_inspections"}:
        errors.append("surface manifest must use exactly rows and surface_inspections")
    inspection_errors, resolved_inspections = _surface_inspection_errors(
        contract,
        manifest.get("surface_inspections") if isinstance(manifest, dict) else None,
        expected_rows,
        repository,
    )
    errors.extend(inspection_errors)
    if not isinstance(supplied_rows, list):
        return {"status": "fail", "errors": [*errors, "surface manifest rows must be a list"], "coverage": {}}
    supplied: set[tuple[str, str]] = set()
    present_by_surface: dict[str, set[str]] = {surface: set() for surface in resolved_inspections}
    surface_levels = contract.get("surface_audit_model", {}).get("surface_levels", {})
    for row in supplied_rows:
        if not isinstance(row, dict):
            errors.append("surface row must be an object")
            continue
        key = (str(row.get("surface")), str(row.get("claim_id")))
        if key in supplied:
            errors.append(f"duplicate surface cell: {key[0]} / {key[1]}")
        supplied.add(key)
        if row.get("contains_private_material") is not False:
            errors.append(f"private material not disproven: {key[0]} / {key[1]}")
        inspection = resolved_inspections.get(key[0], {})
        derived_private_material = inspection.get("contains_private_material")
        if (
            isinstance(derived_private_material, bool)
            and row.get("contains_private_material") is not derived_private_material
        ):
            errors.append(f"private-material disposition differs from the bound inspection: {key[0]} / {key[1]}")
        presence = row.get("presence")
        if not isinstance(presence, str) or presence not in {"present", "absent"}:
            errors.append(f"surface presence unresolved: {key[0]} / {key[1]}")
        if presence == "present":
            present_by_surface.setdefault(key[0], set()).add(key[1])
            canonical = expected_rows.get(key, {})
            required_cells = set(contract.get("surface_audit_model", {}).get("required_cells", []))
            missing_required = sorted(
                field
                for field in required_cells
                if field not in row or row.get(field) is None or row.get(field) == "" or row.get(field) == []
            )
            if missing_required:
                errors.append(
                    f"present claim missing required evidence fields: {key[0]} / {key[1]}: {', '.join(missing_required)}"
                )
            source_ids = row.get("source_ids")
            valid_source_ids = (
                isinstance(source_ids, list)
                and bool(source_ids)
                and all(isinstance(source_id, str) and source_id for source_id in source_ids)
            )
            if not valid_source_ids:
                errors.append(f"source_ids must be a non-empty string list: {key[0]} / {key[1]}")
            expected_source_ids = expected_rows.get(key, {}).get("source_ids", [])
            expected_sources = set(expected_source_ids)
            if valid_source_ids and len(source_ids) != len(set(source_ids)):
                errors.append(f"source_ids contain duplicates: {key[0]} / {key[1]}")
            if valid_source_ids and (
                len(source_ids) != len(expected_source_ids) or set(source_ids) != expected_sources
            ):
                errors.append(f"source ids differ from canonical inventory: {key[0]} / {key[1]}")
            if not isinstance(row.get("disclosure_level"), str) or not row.get("disclosure_level"):
                errors.append(f"disclosure level missing: {key[0]} / {key[1]}")
            if not isinstance(row.get("action"), str) or not row.get("action"):
                errors.append(f"claim action missing: {key[0]} / {key[1]}")
            if row.get("action") != canonical.get("action"):
                errors.append(f"claim action differs from canonical inventory: {key[0]} / {key[1]}")
            if row.get("disclosure_level") != canonical.get("disclosure_level"):
                errors.append(f"disclosure level differs from canonical inventory: {key[0]} / {key[1]}")
            claim_floor = _disclosure_floor(canonical.get("disclosure_level"))
            surface_floor = _disclosure_floor(surface_levels.get(key[0]) if isinstance(surface_levels, dict) else None)
            if claim_floor is None or surface_floor is None or claim_floor > surface_floor:
                errors.append(f"claim disclosure tier does not authorize this surface: {key[0]} / {key[1]}")
            if canonical.get("action") != "audit_canonical_wording":
                errors.append(f"canonical claim is not eligible for public presence: {key[0]} / {key[1]}")
            if row.get("claim_text") != canonical.get("claim_text"):
                errors.append(f"claim text differs from canonical inventory: {key[0]} / {key[1]}")
            if row.get("canonical_or_drift") != "canonical":
                errors.append(f"present claim differs from canonical wording: {key[0]} / {key[1]}")
            observed_at = row.get("observed_at")
            valid_observations = (
                isinstance(observed_at, list)
                and bool(observed_at)
                and all(isinstance(value, str) and bool(value) for value in observed_at)
            )
            if valid_observations:
                try:
                    for value in observed_at:
                        _parse_date(value)
                except ValueError:
                    valid_observations = False
            if not valid_observations or observed_at != canonical.get("observed_at"):
                errors.append(f"observation dates differ from canonical evidence: {key[0]} / {key[1]}")
            if row.get("status") != canonical.get("status"):
                errors.append(f"claim status differs from canonical inventory: {key[0]} / {key[1]}")
        inspection = resolved_inspections.get(key[0])
        if not isinstance(inspection, dict) or row.get("inspection_id") != inspection.get("inspection_id"):
            errors.append(f"surface row does not bind its canonical inspection: {key[0]} / {key[1]}")
    missing = sorted(expected - supplied)
    unexpected = sorted(supplied - expected)
    if missing:
        errors.append(f"missing surface cells: {len(missing)}")
    if unexpected:
        errors.append(f"unexpected surface cells: {len(unexpected)}")
    for surface, inspection in resolved_inspections.items():
        if present_by_surface.get(surface, set()) != inspection.get("matched_claim_ids"):
            errors.append(f"surface row presence differs from the bound inspection: {surface}")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "coverage": {
            "expected": len(expected),
            "supplied": len(supplied & expected),
            "missing": [f"{surface}:{claim}" for surface, claim in missing],
            "unexpected": [f"{surface}:{claim}" for surface, claim in unexpected],
        },
    }


def validate_demo_fixture(contract: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    missing_root_fields = sorted(DEMO_ROOT_FIELDS - set(fixture))
    unexpected_root_fields = sorted(set(fixture) - DEMO_ROOT_FIELDS)
    if missing_root_fields:
        errors.append(f"demo fixture missing root fields: {', '.join(missing_root_fields)}")
    if unexpected_root_fields:
        errors.append(f"demo fixture has unknown root fields: {', '.join(unexpected_root_fields)}")
    if fixture.get("schema_version") != ARCHITECTURE_DEMO_SCHEMA:
        errors.append(f"demo fixture schema_version must be {ARCHITECTURE_DEMO_SCHEMA}")
    if fixture.get("synthetic_only") is not True:
        errors.append("demo fixture must declare synthetic_only true")
    records = fixture.get("records")
    if not isinstance(records, list):
        return {"status": "fail", "errors": [*errors, "demo records must be a list"]}
    record_types: set[str] = set()
    record_type_counts: dict[str, int] = {}
    records_by_id: dict[str, dict[str, Any]] = {}
    demo_contract = contract.get("synthetic_architecture_demo", {})
    id_namespace = demo_contract.get("id_namespace") if isinstance(demo_contract, dict) else None
    bounded_values = demo_contract.get("bounded_values") if isinstance(demo_contract, dict) else None
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append(f"demo record {index} must be an object")
            continue
        record_type = record.get("type")
        if not isinstance(record_type, str) or not record_type.strip():
            errors.append(f"demo record {index} requires a nonblank text type")
        else:
            record_types.add(record_type)
            record_type_counts[record_type] = record_type_counts.get(record_type, 0) + 1
            expected_fields = DEMO_RECORD_FIELDS.get(record_type)
            if expected_fields is None:
                errors.append(f"demo record {index} has unsupported type: {record_type}")
            else:
                missing_fields = sorted(expected_fields - set(record))
                unexpected_fields = sorted(set(record) - expected_fields)
                if missing_fields:
                    errors.append(f"demo record {index} missing {record_type} fields: {', '.join(missing_fields)}")
                if unexpected_fields:
                    errors.append(
                        f"demo record {index} has unknown {record_type} fields: {', '.join(unexpected_fields)}"
                    )
                for field in sorted(expected_fields - {"type", "synthetic"}):
                    value = record.get(field)
                    if not isinstance(value, str) or not value.strip():
                        errors.append(f"demo record {index} field {field} must be nonblank text")
        record_id = record.get("id")
        if isinstance(record_id, str) and record_id.strip():
            if record_id in records_by_id:
                errors.append(f"duplicate demo record id: {record_id}")
            else:
                records_by_id[record_id] = record
        else:
            errors.append(f"demo record {index} requires a nonblank text id")
        expected_id = (
            id_namespace.get(record_type) if isinstance(id_namespace, dict) and isinstance(record_type, str) else None
        )
        if record_id != expected_id:
            errors.append(f"demo record {index} id must use the contract-owned synthetic namespace")
        allowed_fields = (
            bounded_values.get(record_type)
            if isinstance(bounded_values, dict) and isinstance(record_type, str)
            else None
        )
        if isinstance(allowed_fields, dict):
            for field, allowed in allowed_fields.items():
                value = record.get(field)
                if not isinstance(value, str) or not isinstance(allowed, list) or value not in allowed:
                    errors.append(f"demo record {index} field {field} is outside the bounded synthetic vocabulary")
        forbidden = sorted(_find_forbidden_demo_material(record))
        if forbidden:
            errors.append(f"demo record {index} contains forbidden material: {', '.join(forbidden)}")
        if record.get("synthetic") is not True:
            errors.append(f"demo record {index} must be marked synthetic")
    required = set(contract.get("synthetic_architecture_demo", {}).get("required_record_types", []))
    missing = sorted(required - record_types)
    if missing:
        errors.append(f"demo missing record types: {', '.join(missing)}")
    unexpected_types = sorted(record_types - set(DEMO_RECORD_FIELDS))
    if unexpected_types:
        errors.append(f"demo has unsupported record types: {', '.join(unexpected_types)}")
    for record_type in sorted(required):
        if record_type_counts.get(record_type) != 1:
            errors.append(f"demo requires exactly one {record_type} record")
    for record in records_by_id.values():
        record_type = record.get("type")
        if not isinstance(record_type, str):
            continue
        for (source_type, field), target_type in DEMO_RELATIONSHIPS.items():
            if record_type != source_type:
                continue
            reference = record.get(field)
            target = records_by_id.get(reference) if isinstance(reference, str) else None
            if target is None or target.get("type") != target_type:
                errors.append(f"demo {source_type} {record.get('id')} must link {field} to a {target_type} record")
    packet = next((record for record in records_by_id.values() if record.get("type") == "packet"), None)
    if packet is not None and packet.get("authority") != "bounded":
        errors.append("demo packet authority must be bounded")
    predicate = next((record for record in records_by_id.values() if record.get("type") == "predicate"), None)
    if predicate is not None and predicate.get("result") not in {"pass", "fail", "blocked"}:
        errors.append("demo predicate result must be pass, fail, or blocked")
    for failure in (record for record in records_by_id.values() if record.get("type") == "failure"):
        predicate_reference = failure.get("predicate_id")
        linked = records_by_id.get(predicate_reference) if isinstance(predicate_reference, str) else None
        if (
            isinstance(linked, dict)
            and linked.get("type") == "predicate"
            and linked.get("result")
            not in {
                "fail",
                "blocked",
            }
        ):
            errors.append(f"demo failure {failure.get('id')} must link to a failed or blocked predicate")
    return {"status": "pass" if not errors else "fail", "errors": errors, "record_count": len(records)}


def _normalized_demo_key(value: object) -> str:
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(value))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


DEMO_URL = re.compile(r"(?i)(?:https?:)?//[^\s<>\"']+")
DEMO_URL_NESTING_LIMIT = 4


def _demo_url_contains_forbidden_material(value: str, *, depth: int = 0) -> bool:
    candidates = [value]
    decoded = value
    for _attempt in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        candidates.append(next_value)
        decoded = next_value
    forbidden_compact = {key.replace("_", "") for key in FORBIDDEN_DEMO_KEYS}
    forbidden_segments = {
        "credential",
        "customer",
        "email",
        "passcode",
        "passphrase",
        "passwd",
        "password",
        "pwd",
        "secret",
        "token",
    }
    for candidate_text in candidates:
        for match in DEMO_URL.finditer(candidate_text):
            candidate = match.group(0).rstrip(".,);]")
            try:
                parsed = urlsplit(candidate if not candidate.startswith("//") else f"https:{candidate}")
            except ValueError:
                return True
            if parsed.username is not None or parsed.password is not None:
                return True
            for encoded in (parsed.query, parsed.fragment):
                for key, parameter_value in parse_qsl(encoded, keep_blank_values=True):
                    normalized = _normalized_demo_key(key)
                    compact = normalized.replace("_", "")
                    if (
                        normalized in FORBIDDEN_DEMO_KEYS
                        or compact in forbidden_compact
                        or forbidden_segments.intersection(normalized.split("_"))
                    ):
                        return True
                    if DEMO_URL.search(unquote(parameter_value)):
                        if depth >= DEMO_URL_NESTING_LIMIT:
                            return True
                        if _demo_url_contains_forbidden_material(parameter_value, depth=depth + 1):
                            return True
    return False


def _find_forbidden_demo_material(value: object, path: str = "$") -> set[str]:
    forbidden: set[str] = set()
    forbidden_compact = {key.replace("_", "") for key in FORBIDDEN_DEMO_KEYS}
    forbidden_segments = {
        "credential",
        "customer",
        "email",
        "passcode",
        "passphrase",
        "passwd",
        "password",
        "pwd",
        "secret",
        "token",
    }
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = _normalized_demo_key(key)
            compact = normalized.replace("_", "")
            if (
                normalized in FORBIDDEN_DEMO_KEYS
                or compact in forbidden_compact
                or forbidden_segments.intersection(normalized.split("_"))
            ):
                forbidden.add(f"{path}.{key}")
            forbidden.update(_find_forbidden_demo_material(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            forbidden.update(_find_forbidden_demo_material(child, f"{path}[{index}]"))
    elif isinstance(value, str):
        if _demo_url_contains_forbidden_material(value) or any(
            pattern.search(value) for pattern in FORBIDDEN_DEMO_VALUE_PATTERNS
        ):
            forbidden.add(path)
    return forbidden


def _canonical_external_validation_subject(row: dict[str, Any]) -> str:
    subject = {key: value for key, value in row.items() if key not in {"object URL or receipt", "receipt SHA-256"}}
    raw = json.dumps(subject, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _authenticate_external_validation_object(row: dict[str, Any]) -> str:
    receipt_url = row.get("object URL or receipt")
    if not isinstance(receipt_url, str) or not EXTERNAL_VALIDATION_RECEIPT_URL.fullmatch(receipt_url):
        raise ValueError("external validation receipt must be an immutable PSP-P05-W04 issue comment")
    comment = _fetch_github_issue_comment(receipt_url, "external validation")
    author = comment.get("user")
    login = author.get("login") if isinstance(author, dict) else None
    if not isinstance(login, str) or not login.strip():
        raise ValueError("external validation receipt has no authenticated actor")
    body = comment.get("body")
    matches = EXTERNAL_VALIDATION_RECEIPT_BLOCK.findall(body) if isinstance(body, str) else []
    if len(matches) != 1:
        raise ValueError("external validation comment must contain exactly one marked receipt")
    receipt = _loads_preflight_artifact(matches[0])
    if not isinstance(receipt, dict) or set(receipt) != EXTERNAL_VALIDATION_RECEIPT_FIELDS:
        raise ValueError("external validation receipt has an invalid exact schema")
    if receipt.get("schema_version") != EXTERNAL_VALIDATION_RECEIPT_SCHEMA:
        raise ValueError("external validation receipt has an unsupported schema")
    if receipt.get("evidence_kind") != "external_validation":
        raise ValueError("external validation receipt has the wrong evidence kind")
    canonical_receipt = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    receipt_sha256 = row.get("receipt SHA-256")
    if not isinstance(receipt_sha256, str) or not SHA256.fullmatch(receipt_sha256):
        raise ValueError("external validation object requires a lowercase receipt SHA-256")
    if hashlib.sha256(canonical_receipt).hexdigest() != receipt_sha256:
        raise ValueError("external validation receipt digest differs from the marked receipt")
    if receipt.get("subject_sha256") != _canonical_external_validation_subject(row):
        raise ValueError("external validation receipt does not bind the exact asserted review")
    if receipt.get("actor_identity") != login:
        raise ValueError("external validation receipt actor differs from the authenticated comment actor")
    observed_at = receipt.get("observed_at")
    try:
        observed = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError
    except (AttributeError, ValueError) as exc:
        raise ValueError("external validation receipt observed_at must be RFC3339 with a timezone") from exc
    if observed > datetime.now(timezone.utc):
        raise ValueError("external validation receipt cannot be future-dated")
    try:
        raw_created_at = comment.get("created_at")
        raw_updated_at = comment.get("updated_at")
        if not isinstance(raw_created_at, str) or not isinstance(raw_updated_at, str):
            raise ValueError
        created_at = datetime.fromisoformat(raw_created_at.replace("Z", "+00:00"))
        updated_at = datetime.fromisoformat(raw_updated_at.replace("Z", "+00:00"))
        if created_at.tzinfo is None or updated_at.tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ValueError("external validation comment timestamps must be authenticated RFC3339 values") from exc
    now = datetime.now(timezone.utc)
    if created_at > updated_at or updated_at > now:
        raise ValueError("external validation comment timestamps are not chronologically valid")
    if observed != updated_at:
        raise ValueError("external validation receipt time differs from the authenticated comment version")
    if observed.date().isoformat() != row.get("date"):
        raise ValueError("external validation receipt date differs from the asserted review date")
    limitations = receipt.get("limitations")
    if not (
        isinstance(limitations, list)
        and limitations
        and all(isinstance(value, str) and value.strip() and "\0" not in value for value in limitations)
    ):
        raise ValueError("external validation receipt limitations must be public-safe text")
    private_paths = sorted(_find_forbidden_demo_material(receipt, "authenticated external validation receipt"))
    if private_paths:
        raise ValueError(
            "external validation receipt contains private or credential material: " + ", ".join(private_paths)
        )
    if login.casefold() == "4444j99":
        raise ValueError("external validation actor must be independent from the subject owner")
    return login


def validate_external_objects(
    contract: dict[str, Any],
    payload: dict[str, Any],
    *,
    as_of: date | None = None,
) -> dict[str, Any]:
    as_of = as_of or datetime.now(timezone.utc).date()
    errors: list[str] = []
    if payload.get("outreach_performed") is not False:
        errors.append("preflight payload must prove no outreach")
    objects = payload.get("objects")
    if not isinstance(objects, list):
        return {"status": "fail", "errors": [*errors, "external validation objects must be a list"]}
    validation = contract.get("external_validation", {})
    configured_minimum_fields = validation.get("minimum_fields")
    contract_schema_valid = configured_minimum_fields == list(EXTERNAL_VALIDATION_MINIMUM_FIELDS)
    if not contract_schema_valid:
        errors.append("external validation minimum fields must match the canonical exact schema")
    required = set(EXTERNAL_VALIDATION_MINIMUM_FIELDS)
    expected_fields = required | {"object class"}
    acceptable_rows = validation.get("acceptable_objects")
    if (
        not isinstance(acceptable_rows, list)
        or not acceptable_rows
        or not all(isinstance(value, str) and value.strip() for value in acceptable_rows)
    ):
        errors.append("external validation must declare approved object classes")
        acceptable_objects: set[str] = set()
    else:
        acceptable_objects = set(acceptable_rows)
    minimum_count = int(validation.get("minimum_object_count", 0))
    provenance: set[str] = set()
    authenticated_actors: set[str] = set()
    substantive_public_count = 0
    for index, row in enumerate(objects):
        if not isinstance(row, dict):
            errors.append(f"validation object {index} must be an object")
            continue
        missing = sorted(field for field in required if field not in row)
        if missing:
            errors.append(f"validation object {index} missing: {', '.join(missing)}")
        unexpected = sorted((field for field in row if field not in expected_fields), key=str)
        if unexpected:
            errors.append(
                f"validation object {index} has unexpected fields: {', '.join(str(field) for field in unexpected)}"
            )
        exact_schema = contract_schema_valid and not missing and not unexpected and set(row) == expected_fields
        private_paths = sorted(_find_forbidden_demo_material(row, f"validation object {index}"))
        if private_paths:
            errors.append(f"validation object {index} contains private material: {', '.join(private_paths)}")
        invalid_text = sorted(
            field
            for field in required
            if field in row and (not isinstance(row.get(field), str) or not row.get(field).strip())
        )
        if invalid_text:
            errors.append(f"validation object {index} fields must be nonblank text: {', '.join(invalid_text)}")
        object_class = row.get("object class")
        if not isinstance(object_class, str) or object_class not in acceptable_objects:
            errors.append(f"validation object {index} requires an approved object class")
        independence = str(row.get("independence disclosure") or "").strip().lower()
        if independence not in INDEPENDENCE_DISPOSITIONS:
            errors.append(f"validation object {index} lacks an affirmative independence disposition")
        raw_object_receipt = row.get("object URL or receipt")
        object_receipt = raw_object_receipt.strip() if isinstance(raw_object_receipt, str) else raw_object_receipt
        duplicate_receipt = False
        if isinstance(object_receipt, str) and object_receipt:
            if object_receipt in provenance:
                errors.append(f"validation object {index} duplicates an existing object receipt")
                duplicate_receipt = True
            provenance.add(object_receipt)
        observed_at = row.get("date")
        valid_date = True
        try:
            if not isinstance(observed_at, str):
                raise ValueError
            parsed_date = _parse_date(observed_at)
            if parsed_date > as_of:
                errors.append(f"validation object {index} date cannot be in the future")
                valid_date = False
        except ValueError:
            errors.append(f"validation object {index} date must be ISO-8601")
            valid_date = False
        consent_status = row.get("consent status")
        if not isinstance(consent_status, str) or consent_status not in {"public_consented", "withdrawn"}:
            errors.append(f"validation object {index} has no public consent disposition")
        authenticated_actor: str | None = None
        if (
            consent_status == "public_consented"
            and exact_schema
            and not invalid_text
            and not private_paths
            and isinstance(object_receipt, str)
            and object_receipt
        ):
            try:
                authenticated_actor = _authenticate_external_validation_object(row)
            except (HTTPException, OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"validation object {index} authority failed closed: {exc}")
            else:
                normalized_actor = authenticated_actor.casefold()
                if normalized_actor in authenticated_actors:
                    errors.append(f"validation object {index} duplicates an authenticated validator actor")
                    authenticated_actor = None
                else:
                    authenticated_actors.add(normalized_actor)
        if (
            consent_status == "public_consented"
            and exact_schema
            and not invalid_text
            and not private_paths
            and object_class in acceptable_objects
            and independence in INDEPENDENCE_DISPOSITIONS
            and isinstance(object_receipt, str)
            and bool(object_receipt)
            and not duplicate_receipt
            and valid_date
            and authenticated_actor is not None
        ):
            substantive_public_count += 1
    if substantive_public_count < minimum_count:
        errors.append(f"external validation requires at least {minimum_count} substantive public-consented objects")
    return {
        "status": "pass" if not errors else "fail",
        "errors": errors,
        "object_count": len(objects),
        "substantive_public_count": substantive_public_count,
    }


def _live_w07_verification(repository: Path) -> dict[str, Any]:
    completed = _run_trusted_positioning_program(
        repository,
        "--verify-work",
        "PSP-P03-W07",
        timeout=90,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"live PSP-P03-W07 verifier did not pass: {detail}")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError("live PSP-P03-W07 verifier returned a non-object")
    receipt_url = value.get("receipt_url")
    if not isinstance(receipt_url, str) or not W07_RECEIPT_URL.fullmatch(receipt_url):
        raise ValueError("live PSP-P03-W07 receipt URL is not an immutable canonical issue comment")
    comment = _fetch_github_issue_comment(receipt_url, "PSP-P03-W07")
    if not _phase_comment_authorized(comment):
        raise ValueError("live PSP-P03-W07 receipt comment is not owned by an authorized repository actor")
    body = comment.get("body")
    matches = W07_RECEIPT_BLOCK.findall(body) if isinstance(body, str) else []
    if len(matches) != 1:
        raise ValueError("live PSP-P03-W07 comment must contain exactly one marked work receipt")
    authenticated_receipt = _loads_preflight_artifact(matches[0])
    if not isinstance(authenticated_receipt, dict):
        raise ValueError("live PSP-P03-W07 marked receipt must be a JSON object")
    private_paths = sorted(_find_forbidden_demo_material(authenticated_receipt))
    if private_paths:
        raise ValueError(
            "live PSP-P03-W07 marked receipt contains private or credential material: " + ", ".join(private_paths)
        )
    observed = dict(value)
    observed["authenticated_receipt"] = authenticated_receipt
    return observed


def _phase_comment_authorized(comment: object) -> bool:
    if not isinstance(comment, dict):
        return False
    author = comment.get("user")
    author_login = author.get("login") if isinstance(author, dict) else None
    return author_login in PHASE_RECEIPT_AUTHORS and comment.get("author_association") in PHASE_RECEIPT_ASSOCIATIONS


def _fetch_github_issue_comment(receipt_url: str, label: str) -> dict[str, Any]:
    comment_match = re.search(r"#issuecomment-([0-9]+)$", receipt_url)
    if comment_match is None:
        raise ValueError(f"live {label} receipt URL has no immutable comment identifier")
    request = Request(
        f"https://api.github.com/repos/organvm/limen/issues/comments/{comment_match.group(1)}",
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "limen-positioning-proof-preflight",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with _contract_https_open(request, timeout=30) as response:
        raw_comment = response.read(1_048_577)
    if len(raw_comment) > 1_048_576:
        raise ValueError(f"live {label} receipt comment exceeds the bounded response size")
    comment = json.loads(raw_comment)
    if not isinstance(comment, dict) or comment.get("html_url") != receipt_url:
        raise ValueError(f"live {label} receipt comment identity differs from the verifier result")
    return comment


def _live_phase_verification(repository: Path, phase_id: str) -> dict[str, Any]:
    phase_proof = _run_trusted_positioning_program(repository, "--phase-proof", phase_id, timeout=180)
    if phase_proof.returncode != 0:
        detail = (phase_proof.stderr or phase_proof.stdout).strip()
        raise ValueError(f"live {phase_id} manifest phase proof did not pass: {detail}")
    phase_proof_value = _loads_preflight_artifact(phase_proof.stdout)
    if (
        not isinstance(phase_proof_value, dict)
        or phase_proof_value.get("status") != "pass"
        or phase_proof_value.get("phase_id") != phase_id
    ):
        raise ValueError(f"live {phase_id} manifest phase proof returned an invalid result")
    phase_proof_sha256 = hashlib.sha256(phase_proof.stdout.encode("utf-8")).hexdigest()

    completed = _run_trusted_positioning_program(repository, "--verify-phase", phase_id, timeout=180)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"live {phase_id} verifier did not pass: {detail}")
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise ValueError(f"live {phase_id} verifier returned a non-object")
    receipt_url = value.get("receipt_url")
    if not isinstance(receipt_url, str) or not PHASE_RECEIPT_URLS[phase_id].fullmatch(receipt_url):
        raise ValueError(f"live {phase_id} receipt URL is not an immutable canonical issue comment")
    comment = _fetch_github_issue_comment(receipt_url, phase_id)
    if not _phase_comment_authorized(comment):
        raise ValueError(f"live {phase_id} receipt comment is not owned by an authorized repository actor")
    body = comment.get("body")
    matches = PHASE_RECEIPT_BLOCK.findall(body) if isinstance(body, str) else []
    matches = [receipt for candidate_phase, receipt in matches if candidate_phase == phase_id]
    if len(matches) != 1:
        raise ValueError(f"live {phase_id} comment must contain exactly one marked phase receipt")
    receipt = _loads_preflight_artifact(matches[0])
    if not isinstance(receipt, dict):
        raise ValueError(f"live {phase_id} marked receipt returned a non-object")
    if set(receipt) != PHASE_RECEIPT_FIELDS:
        raise ValueError(f"live {phase_id} marked receipt has an invalid exact schema")
    predicate = receipt.get("predicate")
    if not isinstance(predicate, dict) or set(predicate) != PHASE_RECEIPT_PREDICATE_FIELDS:
        raise ValueError(f"live {phase_id} marked receipt predicate has an invalid exact schema")
    private_paths = sorted(_find_forbidden_demo_material(receipt, f"live {phase_id} marked receipt"))
    if private_paths:
        raise ValueError(
            f"live {phase_id} marked receipt contains private or credential material: " + ", ".join(private_paths)
        )
    canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != value.get("receipt_sha256"):
        raise ValueError(f"live {phase_id} marked receipt digest differs from the verifier result")
    observed_heads = receipt.get("observed_heads")
    if not isinstance(observed_heads, dict):
        raise ValueError(f"live {phase_id} marked receipt has no observed_heads binding")
    expected_command = f"python3 scripts/positioning-program.py --phase-proof {phase_id}"
    if (
        not isinstance(predicate, dict)
        or predicate.get("command") != expected_command
        or predicate.get("exit_code") != 0
        or predicate.get("output_sha256") != phase_proof_sha256
    ):
        raise ValueError(f"live {phase_id} marked receipt does not bind the executed manifest phase proof")
    for field in ("exit_gate_sha256", "child_receipts_sha256", "remote_state_sha256", "parity_sha256"):
        if receipt.get(field) != phase_proof_value.get(field):
            raise ValueError(f"live {phase_id} marked receipt differs from the executed phase proof: {field}")
    value["observed_heads"] = observed_heads
    value["phase_proof"] = phase_proof_value
    value["phase_proof_output_sha256"] = phase_proof_sha256
    value["phase_proof_predicate"] = predicate
    return value


def _sanitized_git_environment() -> dict[str, str]:
    environment = dict(os.environ)
    for key in tuple(environment):
        if (
            key
            in {
                "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                "GIT_COMMON_DIR",
                "GIT_CONFIG",
                "GIT_CONFIG_COUNT",
                "GIT_CONFIG_PARAMETERS",
                "GIT_DIR",
                "GIT_EXEC_PATH",
                "GIT_INDEX_FILE",
                "GIT_NAMESPACE",
                "GIT_OBJECT_DIRECTORY",
                "GIT_SHALLOW_FILE",
                "GIT_SSL_CAINFO",
                "GIT_SSL_CAPATH",
                "GIT_SSL_NO_VERIFY",
                "GIT_SSL_VERSION",
                "GIT_WORK_TREE",
                "ALL_PROXY",
                "HTTP_PROXY",
                "HTTPS_PROXY",
                "NO_PROXY",
                "all_proxy",
                "http_proxy",
                "https_proxy",
                "no_proxy",
            }
            or key.startswith("GIT_CONFIG_KEY_")
            or key.startswith("GIT_CONFIG_VALUE_")
            or key.startswith("GIT_SSL_")
            or key.upper().startswith(("LD_", "DYLD_"))
            or key.lower() in {"all_proxy", "http_proxy", "https_proxy", "no_proxy"}
        ):
            environment.pop(key, None)
    environment.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_COUNT": "0",
            "GIT_GRAFT_FILE": os.devnull,
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "PATH": os.pathsep.join(str(path) for path in dict.fromkeys(TRUSTED_EXECUTABLE_DIRECTORIES)),
        }
    )
    return environment


def _trusted_named_executable(name: str) -> Path:
    if not name or Path(name).name != name or "/" in name or "\\" in name:
        raise ValueError("trusted executable name must be one path-free component")
    candidate = next(
        (
            directory / name
            for directory in dict.fromkeys(TRUSTED_EXECUTABLE_DIRECTORIES)
            if (directory / name).is_file() and os.access(directory / name, os.X_OK)
        ),
        None,
    )
    if candidate is None:
        raise OSError(f"trusted executable is unavailable: {name}")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise OSError(f"trusted executable is not executable: {resolved}")
    return resolved


def _python_source_tree(package_root: Path) -> tuple[str, list[tuple[PurePosixPath, bytes]]]:
    """Read one exact pure-Python package tree once and return its deterministic digest."""
    package_root = package_root.resolve(strict=True)
    sources: list[tuple[PurePosixPath, bytes]] = []
    digest = hashlib.sha256()
    for source_file in sorted(package_root.rglob("*.py")):
        if source_file.is_symlink():
            raise ValueError("trusted Python dependency must not contain source symlinks")
        resolved = source_file.resolve(strict=True)
        if package_root not in resolved.parents or not resolved.is_file():
            raise ValueError("trusted Python dependency escaped its package root")
        relative = PurePosixPath(source_file.relative_to(package_root).as_posix())
        data = source_file.read_bytes()
        relative_bytes = relative.as_posix().encode("utf-8")
        digest.update(relative_bytes)
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
        sources.append((relative, data))
    return digest.hexdigest(), sources


def _w07_jsonschema_source_tree(site_root: Path) -> tuple[str, list[tuple[PurePosixPath, bytes]]]:
    """Read the exact pure-Python jsonschema closure used by the isolated W07 replay."""
    site_root = site_root.resolve(strict=True)
    sources: list[tuple[PurePosixPath, bytes]] = []
    excluded_parts = {"__pycache__", "benchmarks", "tests"}
    for package in TRUSTED_W07_JSONSCHEMA_DEPENDENCY["package_roots"]:
        raw_package_root = site_root / package
        if raw_package_root.is_symlink():
            raise ValueError("trusted W07 dependency package root must not be a symlink")
        package_root = raw_package_root.resolve(strict=True)
        if package_root.parent != site_root or not package_root.is_dir():
            raise ValueError("trusted W07 dependency escaped the site-packages root")
        for source_file in sorted(package_root.rglob("*")):
            if not source_file.is_file() or excluded_parts.intersection(source_file.parts):
                continue
            if source_file.is_symlink():
                raise ValueError("trusted W07 dependency must not contain source symlinks")
            resolved = source_file.resolve(strict=True)
            if package_root not in resolved.parents:
                raise ValueError("trusted W07 dependency escaped its package root")
            sources.append((PurePosixPath(source_file.relative_to(site_root).as_posix()), source_file.read_bytes()))
    for filename in TRUSTED_W07_JSONSCHEMA_DEPENDENCY["single_files"]:
        source_file = site_root / filename
        resolved = source_file.resolve(strict=True)
        if not source_file.is_file() or not resolved.is_file():
            raise ValueError("trusted W07 dependency single file is unavailable")
        sources.append((PurePosixPath(filename), resolved.read_bytes()))
    sources.sort(key=lambda row: row[0].as_posix())
    digest = hashlib.sha256()
    for relative, data in sources:
        relative_bytes = relative.as_posix().encode("utf-8")
        digest.update(relative_bytes)
        digest.update(b"\0")
        digest.update(str(len(data)).encode("ascii"))
        digest.update(b"\0")
        digest.update(data)
    return digest.hexdigest(), sources


def _trusted_w07_jsonschema_sources() -> list[tuple[PurePosixPath, bytes]]:
    ambient_python_paths = {
        Path(raw_path).expanduser().resolve()
        for raw_path in os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if raw_path
    }
    for raw_path in sys.path:
        if not raw_path:
            continue
        try:
            candidate_root = Path(raw_path).expanduser().resolve(strict=True)
        except OSError:
            continue
        if (
            candidate_root in ambient_python_paths
            or candidate_root.name not in {"site-packages", "dist-packages"}
            or candidate_root == ROOT
            or ROOT in candidate_root.parents
        ):
            continue
        try:
            tree_sha256, sources = _w07_jsonschema_source_tree(candidate_root)
        except (OSError, ValueError):
            continue
        if (
            len(sources) == TRUSTED_W07_JSONSCHEMA_DEPENDENCY["source_file_count"]
            and tree_sha256 == TRUSTED_W07_JSONSCHEMA_DEPENDENCY["source_tree_sha256"]
        ):
            return sources
    raise OSError("complete contract-owned W07 jsonschema dependency tree is unavailable")


def _w07_jsonschema_dependency_archive(
    sources: list[tuple[PurePosixPath, bytes]],
) -> bytes:
    """Create one deterministic, stored, in-memory archive for the isolated W07 child."""
    rpds_source = W07_RPDS_COMPAT_SOURCE.encode("utf-8")
    if hashlib.sha256(rpds_source).hexdigest() != TRUSTED_W07_JSONSCHEMA_DEPENDENCY["rpds_compat_sha256"]:
        raise ValueError("contract-owned W07 rpds compatibility source digest changed")
    entries = [*sources, (PurePosixPath("rpds/__init__.py"), rpds_source)]
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for relative, data in entries:
            info = zipfile.ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return archive_buffer.getvalue()


def _w07_replay_arguments(archive: bytes, mode: str, program: Path, *arguments: Path) -> list[str]:
    with zipfile.ZipFile(io.BytesIO(archive)) as dependency_archive:
        uncompressed_size = sum(info.file_size for info in dependency_archive.infolist())
    return [
        TRUSTED_W07_JSONSCHEMA_DEPENDENCY["source_tree_sha256"],
        str(TRUSTED_W07_JSONSCHEMA_DEPENDENCY["source_file_count"]),
        TRUSTED_W07_JSONSCHEMA_DEPENDENCY["rpds_compat_sha256"],
        hashlib.sha256(archive).hexdigest(),
        str(len(archive)),
        str(uncompressed_size),
        mode,
        str(program),
        *(str(argument) for argument in arguments),
    ]


def _text_completed_process(completed: subprocess.CompletedProcess[bytes | str]) -> subprocess.CompletedProcess[str]:
    stdout = (
        completed.stdout.decode("utf-8", errors="replace") if isinstance(completed.stdout, bytes) else completed.stdout
    )
    stderr = (
        completed.stderr.decode("utf-8", errors="replace") if isinstance(completed.stderr, bytes) else completed.stderr
    )
    return subprocess.CompletedProcess(completed.args, completed.returncode, stdout or "", stderr or "")


def _w07_replay_environment(interpreter: Path) -> dict[str, str]:
    environment = _sanitized_git_environment()
    for key in tuple(environment):
        upper = key.upper()
        if key == "PATH" or upper.startswith(("PYTHON", "LD_", "DYLD_")):
            environment.pop(key, None)
    trusted_path = (
        interpreter.parent,
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/bin"),
    )
    environment.update(
        {
            "PATH": os.pathsep.join(str(path) for path in dict.fromkeys(trusted_path)),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
        }
    )
    return environment


def _run_trusted_positioning_program(
    repository: Path,
    *arguments: str,
    timeout: int,
) -> subprocess.CompletedProcess[str]:
    """Run the tracked program with the current trusted interpreter and no ambient runtime hooks."""
    repository = repository.resolve(strict=True)
    interpreter = Path(sys.executable).resolve(strict=True)
    program = (repository / "scripts/positioning-program.py").resolve(strict=True)
    expected_program = repository / "scripts/positioning-program.py"
    if program != expected_program or not program.is_file():
        raise ValueError("positioning program must be the tracked repository script")
    if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
        raise OSError(f"trusted Python interpreter is not executable: {interpreter}")
    ambient_python_paths = {
        Path(raw_path).expanduser().resolve()
        for raw_path in os.environ.get("PYTHONPATH", "").split(os.pathsep)
        if raw_path
    }
    dependency_sources: list[tuple[PurePosixPath, bytes]] | None = None
    for raw_path in sys.path:
        if not raw_path:
            continue
        try:
            candidate_root = Path(raw_path).expanduser().resolve(strict=True)
        except OSError:
            continue
        if (
            candidate_root in ambient_python_paths
            or candidate_root.name not in {"site-packages", "dist-packages"}
            or candidate_root == repository
            or repository in candidate_root.parents
        ):
            continue
        raw_package_root = candidate_root / TRUSTED_PYYAML_DEPENDENCY["package"]
        if raw_package_root.is_symlink():
            continue
        try:
            package_root = raw_package_root.resolve(strict=True)
            tree_sha256, candidate_sources = _python_source_tree(package_root)
        except (OSError, ValueError):
            continue
        if package_root.parent != candidate_root:
            continue
        if (
            len(candidate_sources) != TRUSTED_PYYAML_DEPENDENCY["python_source_file_count"]
            or tree_sha256 != TRUSTED_PYYAML_DEPENDENCY["python_source_tree_sha256"]
        ):
            continue
        dependency_sources = candidate_sources
        break
    if dependency_sources is None:
        raise OSError("complete contract-owned PyYAML source tree is unavailable outside ambient PYTHONPATH")
    environment = _sanitized_git_environment()
    for key in tuple(environment):
        upper = key.upper()
        if key == "PATH" or upper.startswith(("PYTHON", "LD_", "DYLD_")):
            environment.pop(key, None)
    trusted_path = (
        interpreter.parent,
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path("/bin"),
    )
    environment.update(
        {
            "PATH": os.pathsep.join(str(path) for path in dict.fromkeys(trusted_path)),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONSAFEPATH": "1",
        }
    )
    with tempfile.TemporaryDirectory(prefix="limen-pyyaml-") as directory:
        dependency_root = Path(directory)
        package_root = dependency_root / TRUSTED_PYYAML_DEPENDENCY["package"]
        package_root.mkdir()
        for relative, data in dependency_sources:
            destination = package_root.joinpath(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        return subprocess.run(
            [
                str(interpreter),
                "-I",
                "-S",
                "-B",
                "-c",
                POSITIONING_PROGRAM_BOOTSTRAP,
                str(dependency_root),
                TRUSTED_PYYAML_DEPENDENCY["python_source_tree_sha256"],
                str(TRUSTED_PYYAML_DEPENDENCY["python_source_file_count"]),
                str(program),
                *arguments,
            ],
            cwd=repository,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )


def _sanitized_ancestry(repository: Path, ancestor: str, descendant: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_trusted_named_executable("git")), "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=repository,
        env=_sanitized_git_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _canonical_limen_remote_head() -> tuple[str, str]:
    completed = subprocess.run(
        [
            str(_trusted_named_executable("git")),
            "ls-remote",
            "--symref",
            "https://github.com/organvm/limen.git",
            "HEAD",
        ],
        cwd=Path("/"),
        env=_sanitized_git_environment(),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"canonical organvm/limen remote inspection failed: {detail}")
    default_branch: str | None = None
    default_head: str | None = None
    for line in completed.stdout.splitlines():
        if line.startswith("ref: refs/heads/") and line.endswith("\tHEAD"):
            default_branch = line.removeprefix("ref: refs/heads/").removesuffix("\tHEAD")
        elif line.endswith("\tHEAD"):
            candidate = line.removesuffix("\tHEAD")
            if FULL_HEAD.fullmatch(candidate):
                default_head = candidate
    if not isinstance(default_branch, str) or not default_branch.strip() or default_head is None:
        raise ValueError("canonical organvm/limen remote returned no exact default-branch head")
    return default_branch, default_head


def _fetch_canonical_limen_objects(
    default_branch: str,
    default_head: str,
    object_paths: set[str],
) -> dict[str, tuple[bytes | None, str | None]]:
    """Fetch canonical main into an isolated store before resolving surface evidence blobs."""
    if (
        not isinstance(default_branch, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", default_branch)
        or any(token in default_branch for token in ("..", "//", "@{", "\\"))
        or not FULL_HEAD.fullmatch(default_head)
        or not isinstance(object_paths, set)
        or any(not _safe_relative_path(path) for path in object_paths)
    ):
        raise ValueError("canonical organvm/limen object request is invalid")
    trusted_git = str(_trusted_named_executable("git"))
    environment = _sanitized_git_environment()
    anchor = Path(Path.cwd().anchor or os.sep)
    with tempfile.TemporaryDirectory(prefix="limen-c04-surface-authority-") as temporary:
        object_store = Path(temporary) / "canonical.git"
        commands = (
            [trusted_git, "init", "--bare", "--quiet", str(object_store)],
            [
                trusted_git,
                "--git-dir",
                str(object_store),
                "remote",
                "add",
                "canonical",
                "https://github.com/organvm/limen.git",
            ],
            [
                trusted_git,
                "--git-dir",
                str(object_store),
                "config",
                "remote.canonical.promisor",
                "true",
            ],
            [
                trusted_git,
                "--git-dir",
                str(object_store),
                "config",
                "remote.canonical.partialclonefilter",
                "blob:none",
            ],
            [
                trusted_git,
                "--git-dir",
                str(object_store),
                "fetch",
                "--no-tags",
                "--depth=1",
                "--filter=blob:none",
                "--force",
                "canonical",
                f"{default_head}:refs/canonical/{default_branch}",
            ],
        )
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=anchor,
                env=environment,
                check=False,
                capture_output=True,
                timeout=120,
            )
            if completed.returncode != 0:
                raise ValueError("canonical organvm/limen surface head could not be fetched into the isolated store")
        canonical_ref = f"refs/canonical/{default_branch}"
        fetched = subprocess.run(
            [trusted_git, "--git-dir", str(object_store), "rev-parse", "--verify", canonical_ref],
            cwd=anchor,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if fetched.returncode != 0 or fetched.stdout.strip() != default_head:
            raise ValueError("fetched canonical organvm/limen surface head differs from the advertised head")
        objects: dict[str, tuple[bytes | None, str | None]] = {}
        for path in sorted(object_paths):
            source_spec = f"{canonical_ref}:{path}"
            content = subprocess.run(
                [trusted_git, "--git-dir", str(object_store), "show", source_spec],
                cwd=anchor,
                env=environment,
                check=False,
                capture_output=True,
                timeout=30,
            )
            blob = subprocess.run(
                [trusted_git, "--git-dir", str(object_store), "rev-parse", source_spec],
                cwd=anchor,
                env=environment,
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if content.returncode != 0 or blob.returncode != 0 or not FULL_HEAD.fullmatch(blob.stdout.strip()):
                objects[path] = (None, None)
            else:
                objects[path] = (content.stdout, blob.stdout.strip())
        return objects


def _canonical_limen_containment(
    default_branch: str,
    default_head: str,
    candidate_heads: set[str],
    descendant_head: str | None = None,
) -> dict[str, bool]:
    """Fetch canonical history once and prove every requested ancestry relation inside it."""
    if (
        not isinstance(default_branch, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", default_branch)
        or any(token in default_branch for token in ("..", "//", "@{", "\\"))
        or not FULL_HEAD.fullmatch(default_head)
        or not isinstance(candidate_heads, set)
        or not candidate_heads
        or any(not FULL_HEAD.fullmatch(head) for head in candidate_heads)
        or (descendant_head is not None and not FULL_HEAD.fullmatch(descendant_head))
    ):
        raise ValueError("canonical organvm/limen ancestry request is invalid")
    trusted_git = str(_trusted_named_executable("git"))
    environment = _sanitized_git_environment()
    anchor = Path(Path.cwd().anchor or os.sep)
    with tempfile.TemporaryDirectory(prefix="limen-c04-closure-authority-") as temporary:
        object_store = Path(temporary) / "canonical.git"
        commands = (
            [trusted_git, "init", "--bare", "--quiet", str(object_store)],
            [
                trusted_git,
                "--git-dir",
                str(object_store),
                "fetch",
                "--no-tags",
                "--filter=blob:none",
                "--force",
                "https://github.com/organvm/limen.git",
                f"{default_head}:refs/canonical/{default_branch}",
            ],
        )
        for command in commands:
            completed = subprocess.run(
                command,
                cwd=anchor,
                env=environment,
                check=False,
                capture_output=True,
                timeout=120,
            )
            if completed.returncode != 0:
                raise ValueError("canonical organvm/limen head could not be fetched into the isolated store")
        canonical_ref = f"refs/canonical/{default_branch}"
        fetched = subprocess.run(
            [trusted_git, "--git-dir", str(object_store), "rev-parse", "--verify", canonical_ref],
            cwd=anchor,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if fetched.returncode != 0 or fetched.stdout.strip() != default_head:
            raise ValueError("fetched canonical organvm/limen head differs from the advertised head")
        available: dict[str, bool] = {}
        for head in dict.fromkeys((*sorted(candidate_heads), descendant_head)):
            if head is None:
                continue
            candidate = subprocess.run(
                [trusted_git, "--git-dir", str(object_store), "cat-file", "-e", f"{head}^{{commit}}"],
                cwd=anchor,
                env=environment,
                check=False,
                capture_output=True,
                timeout=30,
            )
            available[head] = candidate.returncode == 0
        descendant = descendant_head or canonical_ref
        if descendant_head is not None and not available.get(descendant_head, False):
            return {head: False for head in candidate_heads}
        containment: dict[str, bool] = {}
        for candidate_head in sorted(candidate_heads):
            if not available.get(candidate_head, False):
                containment[candidate_head] = False
                continue
            ancestry = subprocess.run(
                [
                    trusted_git,
                    "--git-dir",
                    str(object_store),
                    "merge-base",
                    "--is-ancestor",
                    candidate_head,
                    descendant,
                ],
                cwd=anchor,
                env=environment,
                check=False,
                capture_output=True,
                timeout=30,
            )
            containment[candidate_head] = ancestry.returncode == 0
        return containment


def _canonical_limen_contains_head(
    default_branch: str,
    default_head: str,
    candidate_head: str,
    descendant_head: str | None = None,
) -> bool:
    return _canonical_limen_containment(
        default_branch,
        default_head,
        {candidate_head},
        descendant_head,
    ).get(candidate_head, False)


def _live_authoritative_closure_verification(repository: Path, closure_head: str) -> dict[str, Any]:
    if not FULL_HEAD.fullmatch(closure_head):
        raise ValueError("authoritative closure verification requires a full exact head")
    default_branch, default_head = _canonical_limen_remote_head()
    if not _canonical_limen_contains_head(default_branch, default_head, closure_head):
        raise ValueError("claimed C03 closure head is not contained by the authoritative default branch")
    value = {
        "status": "pass",
        "repository": "organvm/limen",
        "closure_head": closure_head,
        "default_branch": default_branch,
        "default_head": default_head,
        "contained": True,
    }
    errors = _validate_authoritative_closure_verification(value, closure_head)
    if errors:
        raise ValueError("; ".join(errors))
    return value


def _validate_authoritative_closure_verification(value: object, closure_head: str) -> list[str]:
    expected = {
        "status",
        "repository",
        "closure_head",
        "default_branch",
        "default_head",
        "contained",
    }
    if not isinstance(value, dict) or set(value) != expected:
        return ["authoritative closure verification has an invalid exact schema"]
    errors: list[str] = []
    if value.get("status") != "pass" or value.get("repository") != "organvm/limen":
        errors.append("authoritative closure verification did not pass for organvm/limen")
    if value.get("closure_head") != closure_head:
        errors.append("authoritative closure verification does not bind the claimed exact head")
    default_branch = value.get("default_branch")
    if not isinstance(default_branch, str) or not default_branch.strip():
        errors.append("authoritative closure verification has no default branch")
    if not FULL_HEAD.fullmatch(str(value.get("default_head") or "")):
        errors.append("authoritative closure verification has no full default-branch head")
    if value.get("contained") is not True:
        errors.append("claimed C03 closure head is not contained by the authoritative default branch")
    return errors


def _validate_phase_receipt_bindings(
    value: object,
    repository: Path,
    closure_head: str | None,
    live_verifications: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    phases = tuple(PHASE_RECEIPT_URLS)
    if not isinstance(value, dict) or set(value) != set(phases):
        return ["closure receipt must bind exactly the PSP-P03 and PSP-P04 marked phase receipts"]
    if live_verifications is None:
        try:
            live_verifications = {phase_id: _live_phase_verification(repository, phase_id) for phase_id in phases}
        except (HTTPException, json.JSONDecodeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
            return [str(exc)]
    errors: list[str] = []
    valid_closure_head = isinstance(closure_head, str) and bool(FULL_HEAD.fullmatch(closure_head))
    ancestry_candidates: dict[str, str] = {}
    if not valid_closure_head:
        errors.append("phase receipts require a full closure exact head")
    for phase_id in phases:
        binding = value.get(phase_id)
        observed = live_verifications.get(phase_id) if isinstance(live_verifications, dict) else None
        if not isinstance(binding, dict) or set(binding) != {"receipt_url", "receipt_sha256"}:
            errors.append(f"{phase_id} must bind exactly receipt_url and receipt_sha256")
            continue
        if not isinstance(observed, dict) or observed.get("status") != "pass" or observed.get("phase_id") != phase_id:
            errors.append(f"live {phase_id} verification did not return pass")
            continue
        phase_proof = observed.get("phase_proof")
        phase_proof_sha256 = observed.get("phase_proof_output_sha256")
        phase_proof_predicate = observed.get("phase_proof_predicate")
        expected_command = f"python3 scripts/positioning-program.py --phase-proof {phase_id}"
        if (
            not isinstance(phase_proof, dict)
            or phase_proof.get("status") != "pass"
            or phase_proof.get("phase_id") != phase_id
            or not isinstance(phase_proof_sha256, str)
            or not SHA256.fullmatch(phase_proof_sha256)
            or not isinstance(phase_proof_predicate, dict)
            or phase_proof_predicate.get("command") != expected_command
            or phase_proof_predicate.get("exit_code") != 0
            or phase_proof_predicate.get("output_sha256") != phase_proof_sha256
        ):
            errors.append(f"live {phase_id} verification does not bind an executed manifest phase proof")
            continue
        receipt_url = observed.get("receipt_url")
        receipt_sha256 = observed.get("receipt_sha256")
        if not isinstance(receipt_url, str) or not PHASE_RECEIPT_URLS[phase_id].fullmatch(receipt_url):
            errors.append(f"live {phase_id} receipt URL is not an immutable canonical issue comment")
        if not isinstance(receipt_sha256, str) or not SHA256.fullmatch(receipt_sha256):
            errors.append(f"live {phase_id} receipt digest is not a lowercase SHA-256")
        if binding.get("receipt_url") != receipt_url:
            errors.append(f"{phase_id} receipt URL differs from the latest marked live phase receipt")
        if binding.get("receipt_sha256") != receipt_sha256:
            errors.append(f"{phase_id} receipt digest differs from the latest marked live phase receipt")
        observed_heads = observed.get("observed_heads")
        if not isinstance(observed_heads, dict) or set(observed_heads) != {"organvm/limen"}:
            errors.append(f"live {phase_id} receipt must bind exactly the organvm/limen observed head")
            continue
        observed_head = observed_heads.get("organvm/limen")
        if not isinstance(observed_head, str) or not FULL_HEAD.fullmatch(observed_head):
            errors.append(f"live {phase_id} receipt observed head is not a full Git head")
            continue
        ancestry_candidates[phase_id] = observed_head
    if valid_closure_head and ancestry_candidates:
        try:
            default_branch, default_head = _canonical_limen_remote_head()
            containment = _canonical_limen_containment(
                default_branch,
                default_head,
                set(ancestry_candidates.values()),
                closure_head,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
            errors.append(f"canonical phase ancestry authority is unavailable: {exc}")
        else:
            for phase_id, observed_head in ancestry_candidates.items():
                if not containment.get(observed_head, False):
                    errors.append(f"live {phase_id} receipt observed head is not an ancestor of the closure head")
    return errors


def _git_blob(repository: Path, head: str, path: str) -> bytes:
    completed = subprocess.run(
        [str(_trusted_named_executable("git")), "show", f"{head}:{path}"],
        cwd=repository,
        env=_sanitized_git_environment(),
        check=False,
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise ValueError(f"W07 evidence blob is unavailable at {head}:{path}: {detail}")
    return completed.stdout


def _trusted_w07_workflow() -> Any:
    global _W07_WORKFLOW
    if _W07_WORKFLOW is None:
        path = ROOT / W07_WORKFLOW_PATH
        spec = importlib.util.spec_from_file_location("psp_c04_w07_workflow", path)
        if spec is None or spec.loader is None:
            raise ValueError(f"trusted W07 workflow is unavailable: {path}")
        workflow = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = workflow
        spec.loader.exec_module(workflow)
        _W07_WORKFLOW = workflow
    return _W07_WORKFLOW


def _canonical_w07_decision_memo(response_payload: dict[str, Any]) -> bytes:
    workflow = _trusted_w07_workflow()
    verdict = workflow.V.validate(response_payload)
    if verdict.state != "pass":
        raise ValueError("trusted W07 workflow did not accept the exact tracked response set")
    return workflow.decision_memo(response_payload, verdict).encode("utf-8")


def _run_trusted_w07_validator(response_path: Path) -> subprocess.CompletedProcess[str]:
    interpreter = Path(sys.executable).resolve(strict=True)
    validator = (ROOT / W07_VALIDATOR_PATH).resolve(strict=True)
    if validator != ROOT / W07_VALIDATOR_PATH or not validator.is_file():
        raise ValueError("trusted W07 validator must be the tracked repository script")
    sources = _trusted_w07_jsonschema_sources()
    archive = _w07_jsonschema_dependency_archive(sources)
    environment = _w07_replay_environment(interpreter)
    completed = subprocess.run(
        [
            str(interpreter),
            "-I",
            "-S",
            "-B",
            "-c",
            W07_REPLAY_BOOTSTRAP,
            *_w07_replay_arguments(archive, "script", validator, response_path),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        input=archive,
        text=False,
        timeout=90,
    )
    return _text_completed_process(completed)


def _run_observed_w07_replay(
    repository: Path,
    observed_head: str,
    response_blob: bytes,
) -> tuple[subprocess.CompletedProcess[str], bytes]:
    """Execute the W07 validator and memo workflow from the receipt's exact observed head."""
    interpreter = Path(sys.executable).resolve(strict=True)
    sources = _trusted_w07_jsonschema_sources()
    archive = _w07_jsonschema_dependency_archive(sources)
    environment = _w07_replay_environment(interpreter)
    with tempfile.TemporaryDirectory(prefix="limen-c04-w07-replay-") as directory:
        replay_root = Path(directory)
        for relative in W07_REPLAY_PATHS:
            target = replay_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_git_blob(repository, observed_head, relative))
        response_target = replay_root / "w07-reader-responses.json"
        response_target.write_bytes(response_blob)
        validator = replay_root / W07_VALIDATOR_PATH
        workflow = replay_root / W07_WORKFLOW_PATH
        completed = subprocess.run(
            [
                str(interpreter),
                "-I",
                "-S",
                "-B",
                "-c",
                W07_REPLAY_BOOTSTRAP,
                *_w07_replay_arguments(archive, "script", validator, response_target),
            ],
            cwd=replay_root,
            env=environment,
            check=False,
            capture_output=True,
            input=archive,
            text=False,
            timeout=90,
        )
        completed = _text_completed_process(completed)
        if completed.returncode != 0:
            return completed, b""
        memo = subprocess.run(
            [
                str(interpreter),
                "-I",
                "-S",
                "-B",
                "-c",
                W07_REPLAY_BOOTSTRAP,
                *_w07_replay_arguments(archive, "memo", workflow, response_target),
            ],
            cwd=replay_root,
            env=environment,
            check=False,
            capture_output=True,
            input=archive,
            text=False,
            timeout=90,
        )
        memo = _text_completed_process(memo)
        if memo.returncode != 0:
            detail = (memo.stderr or memo.stdout).strip()
            raise ValueError(f"observed-head W07 workflow did not reproduce the decision memo: {detail}")
        return completed, memo.stdout.encode("utf-8")


def _verify_w07_response_blob(
    repository: Path,
    observed_head: str,
    closure_head: str,
    response_path: str,
    response_sha256: str,
    decision_memo_path: str,
    decision_memo_sha256: str,
    evidence: dict[str, Any],
    predicate: dict[str, Any],
) -> None:
    ancestry = _sanitized_ancestry(repository, observed_head, closure_head)
    if ancestry.returncode != 0:
        raise ValueError("W07 observed head is not contained by the claimed C03 closure head")

    response_blob = _git_blob(repository, observed_head, response_path)
    try:
        response_payload = _loads_preflight_artifact(response_blob.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"W07 response-set blob is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(response_payload, dict):
        raise ValueError("W07 response-set blob root must be an object")
    canonical = json.dumps(response_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    if hashlib.sha256(canonical).hexdigest() != response_sha256:
        raise ValueError("W07 response-set digest does not bind the exact tracked response blob")

    decision_memo_blob = _git_blob(repository, observed_head, decision_memo_path)
    if hashlib.sha256(decision_memo_blob).hexdigest() != decision_memo_sha256:
        raise ValueError("W07 decision-memo digest does not bind the exact tracked memo blob")

    completed, canonical_memo = _run_observed_w07_replay(repository, observed_head, response_blob)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise ValueError(f"trusted W07 blinded-reader predicate did not pass: {detail}")
    if predicate.get("exit_code") != completed.returncode:
        raise ValueError("W07 receipt predicate exit_code differs from the exact-head validator result")
    predicate_output_sha256 = predicate.get("output_sha256")
    if hashlib.sha256(completed.stdout.encode("utf-8")).hexdigest() != predicate_output_sha256:
        raise ValueError("W07 receipt predicate output digest differs from the exact-head validator result")
    if decision_memo_blob != canonical_memo:
        raise ValueError("W07 decision memo differs from the observed-head aggregate of the exact response set")
    match = re.search(
        r"SCORE: total=(\d+)/25 role=(\d+)/5 buyer=(\d+)/5 cta=(\d+)/5",
        completed.stdout,
    )
    if match is None:
        raise ValueError("exact-head W07 blinded-reader predicate omitted its score receipt")
    measured = tuple(int(value) for value in match.groups())
    expected = tuple(evidence[field] for field in ("total_score", "role_matches", "buyer_matches", "cta_matches"))
    if measured != expected:
        raise ValueError("W07 reader evidence counts differ from the exact-head predicate output")


def _validate_w07_receipt_binding(
    value: object,
    repository: Path,
    live_verification: dict[str, Any] | None = None,
    closure_head: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["closure receipt requires a structured W07 receipt binding"]
    if set(value) != W07_BINDING_FIELDS:
        errors.append("W07 receipt binding must use the exact contract fields")
    private_paths = sorted(_find_forbidden_demo_material(value))
    if private_paths:
        errors.append("W07 receipt binding contains private or credential material: " + ", ".join(private_paths))
    if value.get("work_id") != "PSP-P03-W07":
        errors.append("W07 receipt work_id must be PSP-P03-W07")
    if value.get("issue_url") != "https://github.com/organvm/limen/issues/2188":
        errors.append("W07 receipt must bind the canonical issue")
    url = value.get("url")
    if not isinstance(url, str) or not W07_RECEIPT_URL.fullmatch(url):
        errors.append("W07 receipt URL must be an immutable #2188 issue comment")
    digest = value.get("sha256")
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append("W07 receipt digest must be a lowercase SHA-256")
    receipt = value.get("receipt")
    if not isinstance(receipt, dict):
        errors.append("W07 binding must embed the canonical marked receipt")
    elif isinstance(digest, str) and SHA256.fullmatch(digest):
        if set(receipt) != W07_WORK_RECEIPT_FIELDS:
            errors.append("embedded W07 receipt must use the exact work-receipt fields")
        canonical = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode()
        if hashlib.sha256(canonical).hexdigest() != digest:
            errors.append("W07 receipt digest does not bind the embedded canonical receipt")
        if receipt.get("work_id") != "PSP-P03-W07" or receipt.get("outcome") != "succeeded":
            errors.append("embedded W07 receipt must record a successful PSP-P03-W07 outcome")
        if receipt.get("schema_version") != "limen.positioning_work_receipt.v1":
            errors.append("embedded W07 receipt must use the canonical work-receipt schema")
        authority = receipt.get("authority")
        if not isinstance(authority, dict) or set(authority) != W07_AUTHORITY_FIELDS:
            errors.append("embedded W07 receipt authority must use the exact contract fields")
        rollback = receipt.get("rollback")
        if not isinstance(rollback, dict) or set(rollback) != W07_ROLLBACK_FIELDS:
            errors.append("embedded W07 receipt rollback must use the exact contract fields")
        evidence = receipt.get("reader_evidence")
        response_path: str | None = None
        memo_path: str | None = None
        observed_head: str | None = None
        if not isinstance(evidence, dict):
            errors.append("embedded W07 receipt must include the public-safe reader evidence summary")
        else:
            if set(evidence) != W07_READER_EVIDENCE_FIELDS:
                errors.append("W07 reader evidence must use the exact contract fields")
            exact_counts = {
                "reader_count": 5,
                "independent_reader_count": 5,
                "synthetic_or_model_reader_count": 0,
                "unresolved_authority_objections": 0,
            }
            for field, expected in exact_counts.items():
                if evidence.get(field) != expected:
                    errors.append(f"W07 reader evidence {field} must be {expected}")
            for field in ("total_score", "role_matches", "buyer_matches", "cta_matches"):
                measured = evidence.get(field)
                minimum = 20 if field == "total_score" else 4
                maximum = 25 if field == "total_score" else 5
                if not isinstance(measured, int) or isinstance(measured, bool) or not minimum <= measured <= maximum:
                    errors.append(f"W07 reader evidence {field} must be between {minimum} and {maximum}")
            for field in ("response_set_sha256", "decision_memo_sha256"):
                measured = evidence.get(field)
                if not isinstance(measured, str) or not SHA256.fullmatch(measured):
                    errors.append(f"W07 reader evidence {field} must be a lowercase SHA-256")
            candidate_path = evidence.get("response_set_path")
            if (
                not isinstance(candidate_path, str)
                or not W07_RESPONSE_PATH.fullmatch(candidate_path)
                or ".." in Path(candidate_path).parts
            ):
                errors.append("W07 reader evidence must bind a safe tracked response_set_path")
            else:
                response_path = candidate_path
            candidate_memo_path = evidence.get("decision_memo_path")
            if (
                not isinstance(candidate_memo_path, str)
                or not W07_MEMO_PATH.fullmatch(candidate_memo_path)
                or ".." in Path(candidate_memo_path).parts
            ):
                errors.append("W07 reader evidence must bind the canonical tracked decision_memo_path")
            else:
                memo_path = candidate_memo_path
            changed_paths = receipt.get("changed_paths")
            for label, path in (("response_set_path", response_path), ("decision_memo_path", memo_path)):
                if path is not None and (not isinstance(changed_paths, list) or path not in changed_paths):
                    errors.append(f"W07 {label} must be present in the receipt changed_paths")
            observed_heads = receipt.get("observed_heads")
            observed_head = observed_heads.get("organvm/limen") if isinstance(observed_heads, dict) else None
            evidence_urls = receipt.get("evidence_urls")
            if not FULL_HEAD.fullmatch(str(observed_head or "")):
                errors.append("W07 evidence must bind a full exact observed head")
            else:
                for label, path in (("response_set_path", response_path), ("decision_memo_path", memo_path)):
                    expected_url = f"https://github.com/organvm/limen/blob/{observed_head}/{path}"
                    if path is not None and (not isinstance(evidence_urls, list) or expected_url not in evidence_urls):
                        errors.append(f"W07 {label} must bind an immutable exact-head evidence URL")
        predicate = receipt.get("predicate")
        expected_command = f"python3 {W07_VALIDATOR_PATH} {response_path}" if response_path is not None else None
        if not isinstance(predicate, dict) or set(predicate) != W07_PREDICATE_FIELDS:
            errors.append("embedded W07 receipt predicate must use the exact contract fields")
        elif predicate.get("command") != expected_command:
            errors.append("embedded W07 receipt must bind the exact manifest-owned blinded-reader predicate command")
        elif predicate.get("exit_code") != 0:
            errors.append("embedded W07 receipt predicate must record exit_code 0")
        elif not isinstance(predicate.get("output_sha256"), str) or not SHA256.fullmatch(predicate["output_sha256"]):
            errors.append("embedded W07 receipt predicate must bind a lowercase output SHA-256")
    if errors:
        return errors
    assert isinstance(receipt, dict)
    assert isinstance(evidence, dict)
    assert isinstance(observed_head, str)
    assert isinstance(response_path, str)
    assert isinstance(memo_path, str)
    assert isinstance(predicate, dict)
    try:
        _verify_w07_response_blob(
            repository,
            observed_head,
            closure_head or "HEAD",
            response_path,
            evidence["response_set_sha256"],
            memo_path,
            evidence["decision_memo_sha256"],
            evidence,
            predicate,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return [str(exc)]
    try:
        observed = live_verification if live_verification is not None else _live_w07_verification(repository)
    except (HTTPException, json.JSONDecodeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
        return [str(exc)]
    if observed.get("status") != "pass" or observed.get("work_id") != "PSP-P03-W07":
        errors.append("live PSP-P03-W07 verification did not return pass")
    if observed.get("receipt_url") != url:
        errors.append("W07 receipt URL differs from the latest marked live receipt")
    if observed.get("receipt_sha256") != digest:
        errors.append("W07 receipt digest differs from the latest marked live receipt")
    authenticated_receipt = observed.get("authenticated_receipt")
    if authenticated_receipt != receipt:
        errors.append("embedded W07 receipt differs from the authenticated marked comment receipt")
    elif (
        hashlib.sha256(json.dumps(authenticated_receipt, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        != digest
    ):
        errors.append("authenticated W07 marked receipt digest differs from the canonical binding")
    return errors


def formalization_readiness(
    contract: dict[str, Any],
    closure_receipt: dict[str, Any] | None = None,
    repository: Path = ROOT,
    w07_verification: dict[str, Any] | None = None,
    phase_verifications: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    accepted_head = contract.get("dependency_progress", {}).get("c03", {}).get("merge_commit")
    residual = ["PSP-P03-W07 genuine five-reader receipt", "PSP-C03 formal closure predicates"]
    receipt_errors: list[str] = []
    final_head: str | None = None
    if closure_receipt is not None:
        if closure_receipt.get("chunk_id") != "PSP-C03":
            receipt_errors.append("closure receipt chunk must be PSP-C03")
        if closure_receipt.get("status") != "pass":
            receipt_errors.append("closure receipt status must be pass")
        final_head = closure_receipt.get("exact_head")
        if not isinstance(final_head, str) or not FULL_HEAD.fullmatch(final_head):
            receipt_errors.append("closure receipt requires a full exact head")
        else:
            authoritative: dict[str, Any] | None = None
            try:
                authoritative = _live_authoritative_closure_verification(repository, final_head)
                receipt_errors.extend(_validate_authoritative_closure_verification(authoritative, final_head))
            except (HTTPException, json.JSONDecodeError, OSError, subprocess.TimeoutExpired, ValueError) as exc:
                receipt_errors.append(str(exc))
            if not FULL_HEAD.fullmatch(str(accepted_head or "")):
                receipt_errors.append("accepted C03 ancestry floor must be a full exact head")
            elif isinstance(authoritative, dict) and not _canonical_limen_contains_head(
                str(authoritative.get("default_branch")),
                str(authoritative.get("default_head")),
                str(accepted_head),
                final_head,
            ):
                receipt_errors.append("final C03 head is not an isolated-canonical descendant of the accepted head")
        if "phase_predicates" in closure_receipt:
            receipt_errors.append("self-declared phase_predicates are not accepted as phase evidence")
        receipt_errors.extend(
            _validate_phase_receipt_bindings(
                closure_receipt.get("phase_receipts"),
                repository,
                closure_head=final_head,
                live_verifications=phase_verifications,
            )
        )
        receipt_errors.extend(
            _validate_w07_receipt_binding(
                closure_receipt.get("w07_receipt"),
                repository,
                live_verification=w07_verification,
                closure_head=final_head,
            )
        )
        if not receipt_errors:
            residual = []
    dependency_rows = resolve_dependency_sources(contract, repository)
    unresolved_sources = [row["source_id"] for row in dependency_rows if not row.get("resolved")]
    if unresolved_sources:
        receipt_errors.append(f"unresolved pinned sources: {', '.join(unresolved_sources)}")
    upstream_bindings = verify_upstream_bindings(contract, repository)
    receipt_errors.extend(upstream_bindings["errors"])
    if contract.get("counts_as_closure") is not False:
        receipt_errors.append("C04 preflight must not count as closure")
    ready = closure_receipt is not None and not receipt_errors and not residual
    return {
        "status": "ready_for_formal_c04_activation" if ready else "PREPARED/PREFLIGHT",
        "ready": ready,
        "accepted_c03_head": accepted_head,
        "residual_gates": residual,
        "errors": receipt_errors,
        "dependency_sources": dependency_rows,
        "upstream_bindings": upstream_bindings,
        "automatic_actions": contract.get("formalization_gate", {}).get("automatic_after_dependencies", [])
        if ready
        else [],
        "prohibited_actions": contract.get("formalization_gate", {}).get("never_automatic", []),
    }


def _load_optional_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = _loads_preflight_artifact(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--mode",
        choices=(
            "validate",
            "resolve",
            "surface-audit",
            "dependency-sources",
            "upstream-bindings",
            "freshness",
            "demo",
            "external-validation",
            "formalization",
        ),
        default="validate",
    )
    parser.add_argument("--input", type=Path)
    parser.add_argument("--as-of", type=date.fromisoformat)
    args = parser.parse_args()
    try:
        contract = load_contract(args.contract)
        errors = validate(contract)
        result: dict[str, Any] = {
            "contract": str(args.contract),
            "status": "pass" if not errors else "fail",
            "errors": errors,
        }
        if not errors:
            as_of = args.as_of or datetime.now(timezone.utc).date()
            if args.mode == "validate":
                result["sources"] = resolve_dependency_sources(contract)
                result["upstream_bindings"] = verify_upstream_bindings(contract)
                unresolved = [row["source_id"] for row in result["sources"] if not row["resolved"]]
                if unresolved:
                    result["errors"].append(f"unresolved pinned sources: {', '.join(unresolved)}")
                result["errors"].extend(result["upstream_bindings"]["errors"])
                if result["errors"]:
                    result["status"] = "fail"
            elif args.mode == "dependency-sources":
                result["sources"] = resolve_dependency_sources(contract)
                if not all(row["resolved"] for row in result["sources"]):
                    result["status"] = "fail"
            elif args.mode == "upstream-bindings":
                result["upstream_bindings"] = verify_upstream_bindings(contract)
                result["status"] = result["upstream_bindings"]["status"]
            elif args.mode == "freshness":
                result["sources"] = source_freshness(contract, as_of)
            elif args.mode == "resolve":
                dependency_rows = resolve_dependency_sources(contract)
                result["dependency_sources"] = dependency_rows
                result["claims"] = resolve_claims(contract, as_of=as_of, dependency_rows=dependency_rows)
            elif args.mode == "surface-audit":
                payload = _load_optional_json(args.input)
                if payload is None:
                    result["rows"] = build_surface_audit_skeleton(contract)
                else:
                    result["audit"] = audit_surface_manifest(contract, payload)
                    result["status"] = result["audit"]["status"]
            elif args.mode == "demo":
                payload = _load_optional_json(args.input)
                if payload is None:
                    raise ValueError("--mode demo requires --input")
                result["demo"] = validate_demo_fixture(contract, payload)
                result["status"] = result["demo"]["status"]
            elif args.mode == "external-validation":
                payload = _load_optional_json(args.input)
                if payload is None:
                    raise ValueError("--mode external-validation requires --input")
                result["validation"] = validate_external_objects(contract, payload, as_of=as_of)
                result["status"] = result["validation"]["status"]
            elif args.mode == "formalization":
                payload = _load_optional_json(args.input)
                result["formalization"] = formalization_readiness(contract, payload)
                result["status"] = "pass" if result["formalization"]["ready"] else "fail"
                result["errors"].extend(result["formalization"]["errors"])
    except (OSError, json.JSONDecodeError, subprocess.TimeoutExpired, ValueError) as exc:
        failure_label = args.mode.replace("-", " ")
        result = {
            "contract": str(args.contract),
            "status": "fail",
            "errors": [f"{failure_label} failed: {exc}"],
        }
    print(json.dumps(result, indent=2) if args.json else result["status"].upper())
    return 1 if result["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
