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
