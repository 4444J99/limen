#!/usr/bin/env python3
"""Independently verify a reap plan and issue a short-lived capability."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.remote_reap import (  # noqa: E402
    atomic_json,
    journal,
    load_model,
    remote_url_digest,
    validate_disposition_evidence,
)
from limen.universe_recovery import (  # noqa: E402
    CustodyProofV1,
    RefDispositionV2,
    ReapPlanV1,
    ReviewLineageClosureV2,
    canonical_digest,
    issue_reap_capability,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a repository-qualified remote-reap plan")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--disposition", type=Path, required=True)
    parser.add_argument("--review-closure", type=Path, required=True)
    parser.add_argument("--custody-receipt", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--capability-output", type=Path, required=True)
    parser.add_argument("--journal-output", type=Path, required=True)
    args = parser.parse_args()
    signing_material = os.environ.get(
        "LIMEN_REMOTE_REAP_CAPABILITY_KEY", ""
    )  # allow-secret: runtime env reference only
    if not signing_material:
        print("remote-reap-verify: keeper capability key is unavailable", file=sys.stderr)
        return 2
    now = datetime.now(UTC)
    try:
        disposition = load_model(args.disposition, RefDispositionV2)
        review = load_model(args.review_closure, ReviewLineageClosureV2)
        custody = load_model(args.custody_receipt, CustodyProofV1)
        plan = load_model(args.plan, ReapPlanV1)
        if not disposition.reap_eligible:
            raise ValueError("ref disposition is not reap eligible")
        validate_disposition_evidence(
            repository_root=args.repository_root,
            disposition=disposition,
            review=review,
            custody=custody,
        )
        if disposition.grace_satisfied_at is None or now < disposition.grace_satisfied_at:
            raise ValueError("remote reap grace has not elapsed")
        if disposition.expires_at is not None and now >= disposition.expires_at:
            raise ValueError("ref disposition has expired")
        expected = {
            "repository": disposition.repository,
            "repository_id": disposition.repository_id,
            "remote_url_digest": remote_url_digest(args.repository_root),
            "ref": disposition.ref,
            "live_tip": disposition.tip,
            "disposition_digest": canonical_digest(disposition),
            "custody_receipt_digest": canonical_digest(custody),
            "review_closure_digest": canonical_digest(review),
        }
        for field, value in expected.items():
            if getattr(plan, field) != value:
                raise ValueError(f"reap plan {field} does not match live evidence")
        if now >= plan.expires_at:
            raise ValueError("reap plan has expired")
        if plan.planned_at > now or now - plan.planned_at > timedelta(minutes=5):
            raise ValueError("reap plan is future-dated or too old to verify")
        if plan.expires_at - now > timedelta(minutes=60):
            raise ValueError("reap plan exceeds the capability lifetime ceiling")
        if plan.grace_satisfied_at != disposition.grace_satisfied_at:
            raise ValueError("reap plan grace does not match the disposition")
        capability_id = f"cap-{canonical_digest(plan)[:32]}"
        planned = journal(
            capability=issue_reap_capability(
                plan,
                capability_id=capability_id,
                issued_by="tabularius-keeper",
                signing_material=signing_material.encode(),
                issued_at=now,
            ),
            state="planned",
            detail="repository-qualified reap plan recorded before capability issuance",
            observed_at=now,
        )
        atomic_json(args.journal_output, planned.model_dump(mode="json"))
        capability = issue_reap_capability(
            plan,
            capability_id=capability_id,
            issued_by="tabularius-keeper",
            signing_material=signing_material.encode(),
            issued_at=now,
        )
        atomic_json(args.capability_output, capability.model_dump(mode="json"))
        verified = journal(
            capability=capability,
            state="verified",
            detail="live repository, exact tip, custody, review closure, grace, and capability binding verified",
            observed_at=now,
        )
        atomic_json(args.journal_output, verified.model_dump(mode="json"))
    except Exception as exc:
        print(f"remote-reap-verify: denied: {exc}", file=sys.stderr)
        return 1
    print(f"remote-reap-verify: verified {disposition.repository} {disposition.ref}@{disposition.tip}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
