#!/usr/bin/env python3
"""Build ops#6 packets without effects; --submit uses one atomic keeper transaction."""

import argparse
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import shlex
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cli/src"))
from limen.conduct.client import client_from_env
from limen.conduct.models import (
    AgentIdentityV1,
    AuthorityEnvelopeV1,
    FanoutBoundsV1,
    ResourceClaimV1,
    SpendEnvelopeV1,
    WorkPacketV1,
)
from limen.dispatch import _load_limen_env
from limen.fanout import _run_id

WORK_KEY = "ops6-coordinate-20261009"
OWNER = "https://github.com/4444J99/ops/issues/6"
LAUNCHER = "08d493caf5cf6fe7a64cbb67f6ed7e6b07ea119e"
SOURCE = "62469ec5b402460a5610145e67901fcdd0ca00b9"
WITNESS = "a1b26e57aae9472aed5e7943de4a9ff12319d192"
DEPLOY = "cloudflare/ops-scheduler-production/deploy"
HOSTED = "github/4444J99/limen/ops-recovery/idempotent-apply"
PATHS = frozenset({"cloudflare", ".github/workflows/ops-owner-release.yml", ".github/scripts/cloudflare-kv"})


def build_packets(session_id, deadline, *, launcher_checkout, source_checkout):
    """Construction is deterministic and never reads credentials, reserves or launches."""
    if deadline.tzinfo is None:
        raise ValueError("original deadline must have a timezone")
    identity = AgentIdentityV1(agent="codex", surface="native", session_id=session_id, provider_identity="codex")
    loan = dict(
        source_origin="human_prompt",
        horizon="present",
        value_case="Resolve accepted ops#6 recovery under serial deployment custody",
        budget_cost=1,
        owner_surface="4444J99/ops",
    )
    root = WorkPacketV1(
        work_id=WORK_KEY,
        work_key=WORK_KEY,
        intent={"kind": "fanout-root", "leaf_count": 3, "owner": OWNER},
        execution={"adapter": "fanout-keeper", "launcher": LAUNCHER, "runtime_source": SOURCE},
        initiator=identity,
        conductor=identity,
        preferred_agent="codex",
        required_capabilities=frozenset({"conduct"}),
        predicate="limen conduct graph " + WORK_KEY,
        receipt_target=OWNER,
        work_loan={**loan, "budget_cost": 3},
        authority=AuthorityEnvelopeV1(
            actions=frozenset({"read", "deploy", "hosted-idempotency"}),
            repositories=frozenset({"4444J99/ops", "4444J99/limen"}),
            path_prefixes=PATHS,
            external_effects=frozenset({DEPLOY, HOSTED}),
        ),
        deadline=deadline,
        spend=SpendEnvelopeV1(limit=3),
        effect="read",
        fanout=FanoutBoundsV1(max_children=3, max_depth=1),
    )
    root_id = _run_id(root)
    root = root.model_copy(update={"predicate": f"limen conduct graph {root_id}"})
    recovery = f"python3 {shlex.quote(str(Path(launcher_checkout) / 'cloudflare/scripts/recover_d1.py'))} {shlex.quote(str(source_checkout))}"
    roles = (
        (
            "A",
            "4444J99/ops",
            LAUNCHER,
            {"cloudflare"},
            {"read", "deploy"},
            {DEPLOY},
            "Run fresh owner preflight, then accepted recover_d1.py against the pinned runtime source with --apply. "
            "Require authoritative source/version/index/activation receipt and lease release before B.",
            recovery + " --apply",
        ),
        (
            "B",
            "4444J99/ops",
            LAUNCHER,
            {"cloudflare", ".github/workflows/ops-owner-release.yml"},
            {"read", "hosted-idempotency"},
            {HOSTED},
            "After A's successful authoritative receipt and release independently verify source, Worker version, "
            "pending-order index, activation, topology and all six capabilities. Dispatch accepted owner/main hosted "
            "apply; require ALREADY_DEPLOYED and identical activation. Runner denial is a separate open gate.",
            recovery,
        ),
        (
            "C",
            "4444J99/limen",
            WITNESS,
            {".github/scripts/cloudflare-kv"},
            {"read"},
            set(),
            "After B's receipt and release check activation-bound witness, post-activation completions, repaired-query "
            "evidence and a complete eligible UTC day at existing thresholds. If unavailable record ACTION_REQUIRED; "
            "the existing witness collects later evidence. Do not sleep, renew deadlines or create a fifth run.",
            "python3 .github/scripts/cloudflare-kv/monitor.py",
        ),
    )
    packets = [root]
    for role, repo, base, paths, actions, effects, intended, predicate in roles:
        key = f"{WORK_KEY}-{role}"
        packets.append(
            WorkPacketV1(
                root_run_id=root_id,
                parent_run_id=root_id,
                depth=1,
                work_id=key,
                work_key=key,
                intent={"kind": "fanout-leaf", "role": role, "intended_effect": intended},
                execution={
                    "adapter": "fanout",
                    "owner_repository": repo,
                    "exact_base": base,
                    "runtime_source": SOURCE,
                    "topic_branch": "main",
                    "launcher_checkout": str(launcher_checkout),
                    "source_checkout": str(source_checkout),
                    "dependencies": [] if role == "A" else [packets[-1].work_id],
                    "executor_session_id": session_id if role == "A" else None,
                    "observed_heads": {repo: base},
                },
                initiator=identity,
                conductor=identity,
                preferred_agent="codex",
                required_capabilities=frozenset({"read-verifier", "predicate-receipt"}),
                resource_claims=tuple(ResourceClaimV1(key=f"external/{effect}") for effect in sorted(effects)),
                predicate=predicate,
                receipt_target=OWNER,
                work_loan={**loan, "owner_surface": repo},
                authority=AuthorityEnvelopeV1(
                    actions=frozenset(actions),
                    repositories=frozenset({repo, "4444J99/limen"} if role == "B" else {repo}),
                    path_prefixes=frozenset(paths),
                    external_effects=frozenset(effects),
                    may_delegate=False,
                ),
                deadline=deadline,
                effect="external" if effects else "read",
            )
        )
    return tuple(packets)


def require_allowance(allowance):
    """A lower bound or an active-only view cannot underwrite four fixed reservations."""
    if (
        allowance.get("schema_version") != "limen.execution_allowance.v1"
        or allowance.get("exhaustive") is not True
        or allowance.get("work_key") != WORK_KEY
        or allowance.get("limit_seconds") != 7200
        or allowance.get("reserved_seconds") != 0
        or allowance.get("matching_run_ids") != []
        or allowance.get("remaining_seconds") != 7200
    ):
        raise ValueError("ops6_four_reservations_not_proven_available")


def submit(client, session_id, *, launcher_checkout, source_checkout, now=None):
    # No deadline is assigned before the earlier rejection's zero debit is proven.
    require_allowance(client.execution_allowance(WORK_KEY))
    deadline = (now or datetime.now(UTC)) + timedelta(minutes=30)
    return client.submit_graph(
        build_packets(session_id, deadline, launcher_checkout=launcher_checkout, source_checkout=source_checkout)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--launcher-checkout", type=Path, required=True)
    parser.add_argument("--source-checkout", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--original-deadline")
    mode.add_argument("--submit", action="store_true")
    args = parser.parse_args()
    if args.submit:
        _load_limen_env()
        result = submit(
            client_from_env(),
            args.session_id,
            launcher_checkout=args.launcher_checkout,
            source_checkout=args.source_checkout,
        )
        # Submission may contain lease capabilities; publish identities/status only.
        print(json.dumps({"status": result["status"], "root_run_id": result.get("root_run_id")}))
    else:
        deadline = datetime.fromisoformat(args.original_deadline.replace("Z", "+00:00"))
        packets = build_packets(
            args.session_id, deadline, launcher_checkout=args.launcher_checkout, source_checkout=args.source_checkout
        )
        print(
            json.dumps(
                {
                    "schema_version": "limen.ops6_graph.v1",
                    "reservation_seconds": 7200,
                    "packets": [p.model_dump(mode="json") for p in packets],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
