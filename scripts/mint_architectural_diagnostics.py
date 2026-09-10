#!/usr/bin/env python3
"""Produce unverified architectural triage from an explicitly supplied PR inventory.

Title and branch heuristics do not establish custody, landing, isolation, or human gates.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECEIPTS_DIR = ROOT / "docs" / "receipts"


def analyze_pr_architecture(p: dict) -> dict | None:
    repo = p["repository"]
    num = p["number"]
    title = p["title"]
    branch = p["head_branch"]
    base = p.get("base_branch", "main")
    chamber = p.get("chamber", "organvm")
    author = p.get("author", "unknown")
    draft = p.get("is_draft", False)
    url = p.get("url", f"https://github.com/{repo}/pull/{num}")

    # 1. Protected Boundary Check (Strict zero-touch isolation)
    if "universal-mail--automation" in repo:
        return None
    if repo == "4444J99/limen" and num == 2543:
        return None
    if "private-document-review" in branch:
        return None
    if "conduct-role-hardening-and-permissions" in branch:
        return None

    title_lower = title.lower()
    branch_lower = branch.lower()
    full_text = f"{repo} {title} {branch}".lower()

    # Ignore pure automated dependabot bumps unless explicit security/sentinel architecture
    if author in ["dependabot", "app/dependabot"] and not any(
        k in title_lower for k in ["security", "sentinel", "conduct", "auth"]
    ):
        return None

    category = None
    blocker_type = None
    observed_divergence = None
    affected_subsystems = []
    breaking_impact = None
    recommendations = []

    # Category 1: Security & Sentinel Vulnerability Defense
    if any(
        k in full_text
        for k in [
            "sentinel",
            "security",
            "token refresh",
            "path traversal",
            "github-token",
            "token exposure",
            "injection",
            "fix-github-token",
            "deprecate insecure",
            "remove insecure token",
        ]
    ):
        category = "Security Matrices & Vulnerability Defense"
        if "token refresh" in full_text:
            blocker_type = "Session Token Invalidation & Suspended Principal Re-Authentication"
            observed_divergence = (
                f"PR #{num} ({branch}) enforces status checks during token refresh. "
                "Bypassing active token validation allows suspended user sessions to persist across token refresh cycles."
            )
            affected_subsystems = ["Authentication Engine", "JWT Refresh Pipeline", "Principal Session Store"]
            breaking_impact = (
                "Modifying token refresh validation contract could invalidate existing client session caches "
                "and requires atomic sync with auth middleware."
            )
            recommendations = [
                "Option A: Integrate token status check into core auth middleware with a 60-second cached status TTL to prevent database read amplification.",
                "Option B: Add deprecation header and grace period for legacy client refresh tokens.",
            ]
        elif "path traversal" in full_text:
            blocker_type = "Unsanitized Path Traversal in Archive Scanner"
            observed_divergence = f"PR #{num} ({branch}) remediates path traversal risks in archive extraction and directory scanning routines."
            affected_subsystems = [
                "ArchiveScanner Subsystem",
                "Filesystem Extraction Engine",
                "Security Ingestion Boundary",
            ]
            breaking_impact = (
                "Strict canonical path validation may block symlinked legacy test archives or multi-root repositories "
                "if base directory resolution is too narrow."
            )
            recommendations = [
                "Option A: Enforce strict realpath resolution against configured allowlist roots before opening archive entries.",
                "Option B: Quarantine unresolvable archive paths into a sandboxed staging directory with isolated read-only permissions.",
            ]
        elif "github-token" in full_text or "token exposure" in full_text:
            blocker_type = "CLI Argument Credential Exposure & Deprecation"
            observed_divergence = (
                f"PR #{num} ({branch}) deprecates and removes plain-text `--github-token` CLI flags in favor of "
                "environment variable or vault resolution."
            )
            affected_subsystems = ["CLI Entrypoint", "Credential Hydration Layer", "Subprocess Argument Sanitizer"]
            breaking_impact = "Immediate removal of CLI token argument breaks automated shell scripts and CI jobs relying on legacy argument passing."
            recommendations = [
                "Option A: Introduce a 2-stage deprecation: emit a security warning to stderr while reading from environment variable fallback.",
                "Option B: Enforce environment variable / credential-wall resolution exclusively and update all orchestrator invocation scripts.",
            ]
        elif "injection" in full_text:
            blocker_type = "GitHub Actions / Workflow Script Injection Vulnerability"
            observed_divergence = f"PR #{num} ({branch}) patches untrusted input interpolation in GitHub Actions workflow steps and issue notifications."
            affected_subsystems = [
                "GitHub Actions Workflows",
                "Issue Notification Effector",
                "Event Webhook Dispatcher",
            ]
            breaking_impact = "Altering workflow step argument passing requires updating action step environment mappings and verifying webhook payload parsing."
            recommendations = [
                "Option A: Move untrusted inputs into intermediate environment variables (`env: TITLE: ${{ github.event.issue.title }}`) instead of direct script template expansion.",
                "Option B: Adopt hardened third-party notification actions pinned to exact commit SHA.",
            ]
        elif "guard system paths" in full_text or "permissions" in full_text or "security hardening" in full_text:
            blocker_type = "System Path Boundary Guard & Package Security Hardening"
            observed_divergence = f"PR #{num} ({branch}) implements strict filesystem path guarding, CSP headers, and pinned dependencies."
            affected_subsystems = ["Path Resolution Subsystem", "HTTP Security Headers", "Build Package Manifest"]
            breaking_impact = "Guarding system paths prevents tool access to parent workspace roots unless explicitly declared in path sandbox manifests."
            recommendations = [
                "Option A: Align path boundaries with the project-wide workspace root schema and verify with scoped test gates.",
                "Option B: Pin high-risk dependencies in lockfiles with explicit hash validation.",
            ]
        else:
            blocker_type = "Security Policy Hardening & Vulnerability Remediation"
            observed_divergence = f"PR #{num} ({branch}) introduces security policy updates and dependency mitigations."
            affected_subsystems = ["Security Ingestion Subsystem", "Policy Engine"]
            breaking_impact = "Requires cross-subsystem review to confirm no breaking interface changes."
            recommendations = [
                "Option A: Audit security diff against established governance access matrices.",
                "Option B: Verify with hermetic test suite.",
            ]

    # Category 2: Conduct Principal RBAC & Authorization Authority
    elif any(
        k in full_text
        for k in [
            "conduct-role",
            "conduct principal",
            "rbac",
            "authority-qualified",
            "canonical-repository-authority",
            "submission boundaries",
            "domus-auth",
            "tab-bookmark-manager-auth",
        ]
    ):
        category = "Conduct Principal RBAC & Authorization Authority"
        if "authority-qualified" in full_text:
            blocker_type = "Authority-Qualified Governance Memory Schema Evolution"
            observed_divergence = f"PR #{num} ({branch}) adds authority qualification and self-image metadata to governance memory models."
            affected_subsystems = [
                "Ontologia Governance Engine",
                "Authority Resolution Ledger",
                "Self-Image Memory Store",
            ]
            breaking_impact = "Changes schema of persisted governance memory, requiring backward compatibility adapters for unsealed historical records."
            recommendations = [
                "Option A: Implement dual-read schema adapter with automatic forward-migration for legacy governance records.",
                "Option B: Require explicit operator cryptographic sign-off before ratifying memory self-image transitions.",
            ]
        elif "canonical-repository-authority" in full_text:
            blocker_type = "Canonical Repository Authority Matrix Modification"
            observed_divergence = f"PR #{num} ({branch}) redefines canonical authority boundaries for repository operations and upstream sync."
            affected_subsystems = [
                "Repository Custody Registry",
                "Estate Management Subsystem",
                "Authority Governance Plane",
            ]
            breaking_impact = (
                "Reassigning repository authority alters permissions for write and release actions across the estate."
            )
            recommendations = [
                "Option A: Validate repository authority claims against `institutio/github/estate.yaml` and audit logs.",
                "Option B: Enforce single-authority rule with operator custody confirmation.",
            ]
        elif "submission boundaries" in full_text:
            blocker_type = "Application Submission Boundary Enforcement"
            observed_divergence = (
                f"PR #{num} ({branch}) enforces remote-only precision submission boundaries in application pipeline."
            )
            affected_subsystems = ["Application Pipeline", "Submission Effector", "Boundary Filter"]
            breaking_impact = "Restricts candidate intake routes and alters submission payload filtering behavior."
            recommendations = [
                "Option A: Validate submission schema and verify zero rejection of valid candidate submissions.",
                "Option B: Add telemetry logging for filtered submissions.",
            ]
        else:
            blocker_type = "Authentication & Role-Based Access Control Reconfiguration"
            observed_divergence = (
                f"PR #{num} ({branch}) modifies authorization contracts or authentication session handling."
            )
            affected_subsystems = ["Auth Middleware", "Access Control List", "Session Manager"]
            breaking_impact = "Modifies role resolution and endpoint authorization checks."
            recommendations = [
                "Option A: Verify role permission matrices against `institutio/governance/gates.yaml`.",
                "Option B: Test role fallback handlers with isolated unit tests.",
            ]

    # Category 3: Payment Rails, Revenue Engines & Ledger Substrates
    elif any(
        k in full_text
        for k in [
            "billing",
            "payment",
            "revenue",
            "monetiz",
            "ledger",
            "buyable",
            "subscription",
            "open-weight api rail",
            "premium-tier",
            "next-rev",
            "candidate weights acquisition ledger",
        ]
    ):
        category = "Payment Rails, Revenue Engines & Ledger Substrates"
        if "the-invisible-ledger" in repo and (
            "persist billing fields" in title_lower or "revenue" in title_lower or "postgres" in title_lower
        ):
            blocker_type = "Database Schema & State Persistence Drift for Billing Subsystem"
            observed_divergence = f"PR #{num} ({branch}) modifies Postgres organization adapter to persist customer billing fields across daemon reloads."
            affected_subsystems = [
                "Postgres Organization Adapter",
                "Billing State Machine",
                "Customer Entitlement Ledger",
            ]
            breaking_impact = (
                "Alters database migration requirements and SQL schema for organization records; unapplied migrations "
                "cause runtime connection/column lookup failures."
            )
            recommendations = [
                "Option A: Execute idempotent migration script and verify column presence before loading organization adapter.",
                "Option B: Wrap billing field extraction with safe dictionary `.get()` fallbacks defaulting to unpaid/trial tier if column is absent.",
            ]
        elif "manumissio" in repo and "open-weight api rail" in title_lower:
            blocker_type = "API Routing & Open-Weight Provider Key Architecture"
            observed_divergence = f"PR #{num} ({branch}) introduces open-weight API routing rails (OpenRouter / DeepSeek keys + dispatch routing)."
            affected_subsystems = ["Model Routing Engine", "API Key Vault Integration", "Provider Rate-Limiting Mesh"]
            breaking_impact = "Changes inference egress architecture and credential injection pipeline for external AI model providers."
            recommendations = [
                "Option A: Require credential-wall verification (`credential-wall.py --check`) for newly introduced API key variables before enabling routing.",
                "Option B: Implement circuit breaker fallback to sovereign local inference if external provider endpoints fail.",
            ]
        elif "sovereign-systems" in repo and ("subscription" in title_lower or "payment collection" in title_lower):
            blocker_type = "Subscription Boundary & Payment Collection Rail Implementation"
            observed_divergence = f"PR #{num} ({branch}) establishes subscription boundaries, gated content access, and payment collection interfaces."
            affected_subsystems = ["Subscription Gatekeeper", "Stripe Payment Processor", "Content Access Controller"]
            breaking_impact = "Enforces gating on previously public or ungated endpoints; misconfigured subscription validation blocks valid clients."
            recommendations = [
                "Option A: Deploy in permissive shadow mode (`SUB_ENFORCE=0`) to log billing evaluations before activating blocking enforcement.",
                "Option B: Validate webhook signing secrets against test suite fixtures.",
            ]
        elif "victoroff-os" in repo and ("buyable" in title_lower or "monetization" in title_lower):
            blocker_type = "Commercial Transaction & Monetized Contract Infrastructure"
            observed_divergence = f"PR #{num} ({branch}) adds monetized V-Contract infrastructure and commercial readiness checkout flows."
            affected_subsystems = [
                "V-Contract Billing Engine",
                "Checkout Transaction Rail",
                "Commercial Licensing Plane",
            ]
            breaking_impact = "Modifies contract pricing models, digital signature flows, and monetary ledger records."
            recommendations = [
                "Option A: Perform end-to-end sandbox purchase simulation and verify idempotent webhook processing.",
                "Option B: Ensure all transaction records are signed and homed in immutable audit logs.",
            ]
        else:
            blocker_type = "Revenue Engine Increment & Product Path Alignment"
            observed_divergence = f"PR #{num} ({branch}) implements next-phase revenue increments and billing hooks."
            affected_subsystems = ["Revenue Pipeline", "Monetization Module", "Billing Webhooks"]
            breaking_impact = "Alters pricing tier evaluation and monetization reporting."
            recommendations = [
                "Option A: Audit revenue path against product specification and operator goals.",
                "Option B: Test payment processor webhooks against hermetic mock servers.",
            ]

    # Category 4: Breaking Protocol Redesigns & Governance Charters
    elif any(
        k in full_text
        for k in [
            "governance",
            "protocol",
            "ontologia",
            "charter",
            "system-governance-framework",
            "agent-governance-layer",
            "telos-beacon-protocol",
            "blockchain",
            "truth-first governance organ",
            "peer-audited--behavioral-blockchain",
        ]
    ):
        category = "Breaking Protocol Redesigns & Governance Charters"
        if "organvm-corpvs-testamentvm" in repo and (
            "governance organ" in title_lower or "telos" in title_lower or "logos" in title_lower
        ):
            blocker_type = "Ecosystem Governance Organ Ratification & Beacon Protocol Redesign"
            observed_divergence = f"PR #{num} ({branch}) proposes ratification of Truth-First Governance Organ and introduces AX-7 Tetradic Self-Knowledge beacon protocols."
            affected_subsystems = [
                "Governance Ratification Spine",
                "Telos Beacon Protocol",
                "Corpus Philosophical Schema",
            ]
            breaking_impact = "Fundamentally alters foundational constitutional rules, peer organ definitions, and teleological protocol standards across the entire ecosystem."
            recommendations = [
                "Option A: Convene operator review session to ratify or adjust constitutional governance organ definitions.",
                "Option B: Stage protocol schemas into experimental draft namespaces (`docs/specs/draft-spec-001/`) before promoting to CANON.",
            ]
        elif "system-governance-framework" in repo:
            blocker_type = "System Governance Taxonomy & Authority Tier Restructuring"
            observed_divergence = f"PR #{num} ({branch}) updates test suites, coverage, and ranked tier definitions for system governance frameworks."
            affected_subsystems = ["Governance Taxonomy Engine", "Framework Classification Matrix", "System Tier Index"]
            breaking_impact = "Reclassifying repository tiers impacts automated audit priorities and gate requirements across Taxis chamber."
            recommendations = [
                "Option A: Rebase against current default branch, resolve test assertions, and verify alignment with `institutio/registry/organs.yaml`.",
                "Option B: Review taxonomy schema diff with operator.",
            ]
        elif "victoroff-os" in repo and "agent-governance-layer" in full_text:
            blocker_type = "AI Model & Agent Governance Substrate Architecture"
            observed_divergence = f"PR #{num} ({branch}) establishes AI model governance layers, safety guardrails, and agent authority boundaries."
            affected_subsystems = ["Agent Runtime Governance", "Model Safety Policy", "Subagent Intercept Layer"]
            breaking_impact = "Directly constrains autonomous subagent invocation and message dispatch paths."
            recommendations = [
                "Option A: Validate agent governance layer with multi-agent orchestration test scenarios.",
                "Option B: Audit model safety constraints against operational dispatch latency requirements.",
            ]
        else:
            blocker_type = "Protocol Specification & Governance Boundary Modification"
            observed_divergence = (
                f"PR #{num} ({branch}) introduces protocol schema modifications and governance updates."
            )
            affected_subsystems = ["Protocol Layer", "Governance Manifests"]
            breaking_impact = "May cause downstream client incompatibility if protocol schemas diverge."
            recommendations = [
                "Option A: Review protocol diff with system architects.",
                "Option B: Provide schema migration compatibility layer.",
            ]

    # Category 5: Operator-Gated Decisions & Recovery Runtimes
    elif any(
        k in full_text
        for k in [
            "recovery",
            "preview-valves",
            "custody review debt",
            "acceptance gates",
            "control plane",
            "blackbaud-gate-5-proof",
        ]
    ):
        category = "Operator-Gated Decisions & Recovery Runtimes"
        if "domus-genoma" in repo and "preview valves" in title_lower:
            blocker_type = "Limen Heartbeat Preview Valve Ownership Reassignment"
            observed_divergence = (
                f"PR #{num} ({branch}) alters heartbeat preview valve ownership and dispatch telemetry controls."
            )
            affected_subsystems = ["Heartbeat Sensor Mesh", "Preview Telemetry Valves", "Operator Control Intercept"]
            breaking_impact = "Modifying valve ownership could disrupt live telemetry feeds to operator dashboards during autonomic recovery cycles."
            recommendations = [
                "Option A: Retain backward-compatible telemetry dispatch while enabling shadow valve feeds.",
                "Option B: Conduct operator-in-the-loop manual validation of preview telemetry streams.",
            ]
        elif "daily-engine" in repo and "acceptance gates" in title_lower:
            blocker_type = "Daily Engine Recovery Acceptance Gate Calibration"
            observed_divergence = (
                f"PR #{num} ({branch}) introduces new strict acceptance gates for Daily Engine CI workflows."
            )
            affected_subsystems = ["Daily Execution Engine", "Recovery CI Gates", "Autonomic Scheduler"]
            breaking_impact = "Stricter acceptance gates may fail existing background daily execution cycles if gate thresholds are set too conservatively."
            recommendations = [
                "Option A: Calibrate gate thresholds against historical execution telemetry before enforcing hard failure.",
                "Option B: Allow configurable advisory warnings during initial rollout phase.",
            ]
        elif repo == "4444J99/limen" and num == 2542:
            blocker_type = "Recovery Liveness & Custody Review Debt Reconciliation"
            observed_divergence = f"PR #{num} ({branch}) reconciles recovery liveness and custody review debt following PR #2539 / #2540 merges."
            affected_subsystems = ["Custody Review Ledger", "Recovery Liveness Subsystem", "Estate Audit Trail"]
            breaking_impact = (
                "Resolves outstanding audit debt across recovery sessions without mutating protected runtime lanes."
            )
            recommendations = [
                "Option A: Review custody reconciliation diff against `docs/estate-closeout-audit.md`.",
                "Option B: Rebase onto latest main and verify zero dangling tasks with `scripts/no-tasks-on-me.sh`.",
            ]
        elif "victoroff-os" in repo and "blackbaud" in full_text:
            blocker_type = "Enterprise Integration Buyer-Facing Proof Validation"
            observed_divergence = f"PR #{num} ({branch}) provides buyer-facing proof artifacts and Gate 5 qualification for Blackbaud integration."
            affected_subsystems = ["Enterprise Integration Bridge", "Blackbaud API Connector", "Buyer Proof Ledger"]
            breaking_impact = "Operator-gated commercial milestone requiring external stakeholder sign-off."
            recommendations = [
                "Option A: Archive buyer-facing proof artifacts into commercial documentation repository.",
                "Option B: Await operator sign-off before merging into commercial production branch.",
            ]
        else:
            blocker_type = "Operator-Gated Recovery Workflow Calibration"
            observed_divergence = (
                f"PR #{num} ({branch}) contains operator-gated recovery logic and runtime configurations."
            )
            affected_subsystems = ["Recovery Engine", "Operator Gate Subsystem"]
            breaking_impact = "Requires explicit human confirmation before executing state transitions."
            recommendations = [
                "Option A: Inspect recovery plan diff with operator.",
                "Option B: Validate with hermetic local test gates.",
            ]

    if not category:
        return None

    return as_unverified_assessment(
        {
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "target": {
                "chamber": chamber,
                "repository": repo,
                "pull_request": num,
                "head_branch": branch,
                "base_branch": base,
                "author": author,
                "is_draft": draft,
                "url": url,
                "title": title,
            },
            "diagnostic_assessment": {
                "category": category,
                "blocker_type": blocker_type,
                "observed_divergence": observed_divergence,
                "affected_subsystems": affected_subsystems,
                "breaking_impact_analysis": breaking_impact,
                "operator_recommendations": recommendations,
            },
        }
    )


def as_unverified_assessment(record: dict) -> dict:
    """Recast legacy heuristics without inventing validation or remote-state evidence."""
    record = json.loads(json.dumps(record))
    record["schema"] = "limen.architectural_assessment.v1"
    record["receipt_type"] = "architectural_assessment"
    record["verification_status"] = "unverified"
    record["evidence_basis"] = "inventory metadata heuristics; source diff and runtime uninspected"
    record["establishes_custody"] = False
    record["establishes_landing"] = False
    assessment = record["diagnostic_assessment"]
    assessment["classification"] = "Unverified architectural triage"
    assessment["disposition"] = "UNVERIFIED_ASSESSMENT"
    for key in ("blocker_type", "observed_divergence", "breaking_impact_analysis"):
        text = assessment.get(key, "")
        if not text.startswith("Unverified hypothesis: "):
            assessment[key] = f"Unverified hypothesis: {text}"
    assessment["operator_recommendations"] = [
        value if value.startswith("Candidate for review: ") else f"Candidate for review: {value}"
        for value in assessment.get("operator_recommendations", [])
    ]
    record.pop("protected_boundary_verification", None)
    record["protected_boundary_assessment"] = {
        "status": "unverified",
        "zero_touch_verified": False,
        "quarantined_from_auto_merge": False,
    }
    target = record["target"]
    record["diagnostic_comment_body"] = (
        f"### Unverified architectural triage\n\n"
        f"{target['repository']} PR #{target['pull_request']}\n\n"
        f"Metadata suggests the category: {assessment['category']}.\n\n"
        "This is a title and branch heuristic for review. The source diff, remote PR state, "
        "custody, landing, protected boundaries, and merge quarantine have not been verified. "
        "No human approval requirement is established by this assessment."
    )
    record["integrity_note"] = (
        "Unverified metadata assessment only; no custody, landing, isolation, or lifecycle proof."
    )
    return record


def assessment_manifest(records: list[dict]) -> dict:
    return {
        "schema": "limen.architectural_assessment_manifest.v1",
        "receipt_type": "architectural_assessment_manifest",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "verification_status": "unverified",
        "establishes_custody": False,
        "establishes_landing": False,
        "total_assessments": len(records),
        "diagnostics": [
            {
                "repository": r["target"]["repository"],
                "pull_request": r["target"]["pull_request"],
                "category": r["diagnostic_assessment"]["category"],
                "blocker_type": r["diagnostic_assessment"]["blocker_type"],
                "disposition": "UNVERIFIED_ASSESSMENT",
            }
            for r in records
        ],
        "integrity_note": "Metadata triage index only; no PR state, custody, quarantine, or landing verified.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True, help="Explicit JSON PR inventory input")
    parser.add_argument("--output-dir", type=Path, default=RECEIPTS_DIR)
    args = parser.parse_args(argv)
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    records = [record for p in inventory.get("pull_requests", []) if (record := analyze_pr_architecture(p))]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        target = record["target"]
        repo = target["repository"].replace("/", "_")
        path = args.output_dir / f"architectural_diagnostic_{repo}_{target['pull_request']}.json"
        path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    manifest = assessment_manifest(records)
    (args.output_dir / "architectural_diagnostics_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {len(records)} unverified architectural assessments in {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
