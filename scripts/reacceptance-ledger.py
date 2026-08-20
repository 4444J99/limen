#!/usr/bin/env python3
"""Build, migrate, or validate the redacted recovery ledger v2."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import reacceptance_cli as _cli  # noqa: E402
from limen import reacceptance_contract as _contract  # noqa: E402
from limen import reacceptance_github as _github  # noqa: E402
from limen import reacceptance_policy as _policy  # noqa: E402
from limen import reacceptance_workflow as _workflow  # noqa: E402


REVIEW_DIR = ROOT / "docs" / "reviews" / "claude-reacceptance-2026-07-16"
SCOPE_PATH = REVIEW_DIR / "scope.json"
LEDGER_PATH = REVIEW_DIR / "ledger.json"

# Compatibility exports for existing callers and tests. The implementation and
# LedgerError identity remain owned by the layered modules under cli/src/limen.
SCHEMA = _contract.SCHEMA
V1_SCHEMA = _contract.V1_SCHEMA
SCOPE_SCHEMA = _contract.SCOPE_SCHEMA
REVIEW_GATE_SCHEMA = _contract.REVIEW_GATE_SCHEMA
REVIEW_GATE_CONTEXT = _contract.REVIEW_GATE_CONTEXT
SOURCE_LINEAGE_SCHEMA = _contract.SOURCE_LINEAGE_SCHEMA
TRAJECTORY_SCHEMA = _contract.TRAJECTORY_SCHEMA
SIDE_EFFECT_SCHEMA = _contract.SIDE_EFFECT_SCHEMA
SIDE_EFFECT_OUTCOME_SCHEMA = _contract.SIDE_EFFECT_OUTCOME_SCHEMA
REFRESH_RECEIPT_SCHEMA = _contract.REFRESH_RECEIPT_SCHEMA
PRIVACY_COPY_SCHEMA = _contract.PRIVACY_COPY_SCHEMA
CUTOFF_SCHEMA = _contract.CUTOFF_SCHEMA
OWNER_EVIDENCE_SCHEMAS = _contract.OWNER_EVIDENCE_SCHEMAS
LedgerError = _contract.LedgerError

load_json = _contract.load_json
load_json_snapshot = _contract.load_json_snapshot
normalized_evidence_digest = _contract.normalized_evidence_digest
_parse_timestamp = _contract._parse_timestamp
_scope_cutoff_digest = _contract._scope_cutoff_digest
_event_offsets_digest = _contract._event_offsets_digest
_base_row = _contract._base_row
_default_owner_evidence = _contract._default_owner_evidence
_document_scope = _contract._document_scope
_lineage_digest = _contract._lineage_digest
_effect_digest = _contract._effect_digest
_output_digest = _contract._output_digest
_finding_manifest_digest = _contract._finding_manifest_digest
_source_reference_manifest_digest = _contract._source_reference_manifest_digest
_legacy_v1_rows_digest = _contract._legacy_v1_rows_digest
_summary_for = _contract._summary_for

validate_document = _policy.validate_document
_derive_completion_gates = _policy._derive_completion_gates
_evidence_identity = _policy._evidence_identity
_owner_binding_digest = _policy._owner_binding_digest

migrate_v1_document = _workflow.migrate_v1_document
build_document = _workflow.build_document
_finalize_document = _workflow._finalize_document
normalize_edited_prior = _workflow.normalize_edited_prior
_finding_id = _workflow._finding_id
_refresh_findings = _workflow._refresh_findings

_write_atomic = _cli._write_atomic

# Keep the historical monkeypatch seam: tests and callers may replace this
# facade binding before invoking _refresh_remedy.
_gh_graphql = _github._gh_graphql


def load_scope(path: Path = SCOPE_PATH) -> dict[str, Any]:
    return _contract.load_scope(path)


def _refresh_remedy(remedy: dict[str, Any]) -> dict[str, Any]:
    return _github._refresh_remedy(remedy, fetch_pr=_gh_graphql)


def main(argv: list[str] | None = None) -> int:
    return _cli.main(argv, scope_path=SCOPE_PATH, ledger_path=LEDGER_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
