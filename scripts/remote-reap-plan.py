#!/usr/bin/env python3
"""Read-only planner for one repository-qualified remote branch reap.

The planner emits a candidate plan to stdout.  It never writes a file, issues
authority, or mutates local/remote Git state.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.remote_reap import (  # noqa: E402
    github_repository_slug,
    load_model,
    remote_tip,
    remote_url_digest,
)
from limen.universe_recovery import (  # noqa: E402
    RefDispositionV2,
    ReapPlanV1,
    ReviewLineageClosureV2,
    canonical_digest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan one exact-tip remote branch reap")
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--disposition", type=Path, required=True)
    parser.add_argument("--review-closure", type=Path, required=True)
    parser.add_argument("--expires-min", type=int, default=15)
    args = parser.parse_args()
    now = datetime.now(UTC)
    try:
        disposition = load_model(args.disposition, RefDispositionV2)
        review = load_model(args.review_closure, ReviewLineageClosureV2)
        if not disposition.reap_eligible:
            raise ValueError("ref disposition is not reap eligible")
        if github_repository_slug(args.repository_root) != disposition.repository:
            raise ValueError("repository identity does not match the disposition")
        if not review.terminal or review.repository != disposition.repository:
            raise ValueError("review closure is nonterminal or belongs to another repository")
        if review.pull_request not in disposition.pull_requests:
            raise ValueError("review closure is not named by the ref disposition")
        if disposition.grace_satisfied_at is None or now < disposition.grace_satisfied_at:
            raise ValueError("remote reap grace has not elapsed")
        if disposition.expires_at is not None and now >= disposition.expires_at:
            raise ValueError("ref disposition has expired")
        if remote_tip(args.repository_root, disposition.ref) != disposition.tip:
            raise ValueError("live remote ref does not match the disposition")
        plan = ReapPlanV1(
            plan_id=f"plan-{canonical_digest(disposition)[:32]}",
            repository=disposition.repository,
            repository_id=disposition.repository_id,
            remote_url_digest=remote_url_digest(args.repository_root),
            ref=disposition.ref,
            live_tip=disposition.tip,
            disposition_digest=canonical_digest(disposition),
            custody_receipt_digest=disposition.custody_proof_digest,
            review_closure_digest=canonical_digest(review),
            grace_satisfied_at=disposition.grace_satisfied_at,
            planned_at=now,
            expires_at=now + timedelta(minutes=max(1, min(args.expires_min, 60))),
        )
    except Exception as exc:
        print(f"remote-reap-plan: denied: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(plan.model_dump(mode="json"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
