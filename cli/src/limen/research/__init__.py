"""Studium-owned, provider-neutral research runtime boundary."""

from .catalog import ResearchProfile, select_profile
from .contracts import (
    DEFAULT_CATALOG_URL,
    PERPLEXITY_RESEARCH_URL,
    ResearchContractError,
    ResearchRequest,
    load_document,
    owner_path,
    stable_hash,
    write_json,
)
from .custody import verify_owner_root, verify_raw_export_custody
from .evidence import ingest_markdown_export, render_evidence_markdown
from .handoff import (
    BlockedReceipt,
    ManualHandoff,
    ResearchReceipt,
    launch_attended_research,
    prepare_research,
    render_research_prompt,
)
from .sanitization import OutputSanitizationAttestation
from .verification import SourceVerifierAttestation

__all__ = [
    "DEFAULT_CATALOG_URL",
    "PERPLEXITY_RESEARCH_URL",
    "BlockedReceipt",
    "ManualHandoff",
    "OutputSanitizationAttestation",
    "ResearchContractError",
    "ResearchProfile",
    "ResearchReceipt",
    "ResearchRequest",
    "SourceVerifierAttestation",
    "ingest_markdown_export",
    "launch_attended_research",
    "load_document",
    "owner_path",
    "prepare_research",
    "render_evidence_markdown",
    "render_research_prompt",
    "select_profile",
    "stable_hash",
    "verify_owner_root",
    "verify_raw_export_custody",
    "write_json",
]
