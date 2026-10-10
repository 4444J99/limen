#!/usr/bin/env python3
"""Prepare the existing fanout manifest. This command reserves or launches nothing."""

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli/src"))
from limen.conduct.models import AgentIdentityV1, canonical_hash
from limen.fanout import FanoutLeafV1, FanoutManifestV1


def build_manifest(session_id, deadline):
    identity = AgentIdentityV1(agent="codex", surface="native", session_id=session_id, provider_identity="codex")
    owner = "https://github.com/4444J99/ops/issues/6"
    loan = dict(
        source_origin="human_prompt",
        horizon="present",
        value_case="Resolve authorized ops#6 recovery with serialized custody",
        budget_cost=1,
        owner_surface="4444J99/ops",
    )
    roles = (
        (
            "A",
            "4444J99/ops",
            "08d493caf5cf6fe7a64cbb67f6ed7e6b07ea119e",
            "After 2026-10-10T00:00:00Z, A alone acquires deployment custody and runs pinned owner preflight/apply for runtime 62469ec5b402460a5610145e67901fcdd0ca00b9; retain authoritative receipt and release before B.",
            "python3 cloudflare/scripts/recover_d1.py --help",
        ),
        (
            "B",
            "4444J99/ops",
            "08d493caf5cf6fe7a64cbb67f6ed7e6b07ea119e",
            "After A authoritative receipt and release, verify source/version/index/activation and six capabilities. Hosted ALREADY_DEPLOYED is independently gated; broker admission is not hosted idempotency.",
            "python3 cloudflare/scripts/recover_d1.py --help",
        ),
        (
            "C",
            "4444J99/limen",
            "a1b26e57aae9472aed5e7943de4a9ff12319d192",
            "Evaluate activation-bound witness only when its eligible complete UTC day is available. Otherwise checkpoint ACTION_REQUIRED without sleeping, renewing deadlines or adding a scheduler.",
            "python3 -m py_compile .github/scripts/cloudflare-kv/monitor.py",
        ),
    )
    leaves = []
    for index, (role, repo, base, effect, predicate) in enumerate(roles):
        key = f"ops6-coordinate-20261009-{role}"
        leaves.append(
            FanoutLeafV1(
                work_id=key,
                idempotency_key=key,
                owner_repository=repo,
                exact_base=base,
                topic_branch="main",
                allowed_paths=("cloudflare",) if index < 2 else (".github/scripts/cloudflare-kv",),
                resource_claims=(),
                dependencies=() if index == 0 else (leaves[-1].work_id,),
                intended_effect=effect,
                effect="read",
                predicate=predicate,
                receipt_target=owner,
                work_loan={**loan, "owner_surface": repo},
                deadline=deadline,
                retry={"max_attempts": 1},
                spend={"limit": 1},
                prompt_hash=canonical_hash({"owner": owner}),
                plan_hash=canonical_hash({"role": role, "effect": effect}),
            )
        )
    return FanoutManifestV1(
        root_work_id="ops6-coordinate-20261009",
        idempotency_key="ops6-coordinate-20261009",
        initiator=identity,
        conductor=identity,
        predicate="python3 cloudflare/scripts/recover_d1.py --help",
        receipt_target=owner,
        work_loan={**loan, "budget_cost": 3},
        deadline=deadline,
        leaves=tuple(leaves),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--original-deadline", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            build_manifest(
                args.session_id, datetime.fromisoformat(args.original_deadline.replace("Z", "+00:00"))
            ).model_dump(mode="json"),
            indent=2,
        )
    )
