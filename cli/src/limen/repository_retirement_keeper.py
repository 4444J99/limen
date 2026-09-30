"""Broker-derived admission and independently reserved acceptance; no local grants."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

from limen.conduct.client import client_from_env
from limen.conduct.models import AgentIdentityV1, PredicateEvidenceV1, RunReceiptV1
from limen.repository_retirement import RetirementError, digest, manifest_binding, timestamp


class Keeper:
    def __init__(self, manifest: dict, *, client=None):
        self.manifest = manifest
        self.client = client or client_from_env()
        self.graph = self.client.graph(manifest["run_id"])
        self.nodes = {node["run_id"]: node for node in self.graph["nodes"]}
        self.root = self.nodes[manifest["run_id"]]
        self.reviewer = self.nodes.get(manifest.get("review_run_id"))
        if self.reviewer is None or self.reviewer["run_id"] == self.root["run_id"]:
            raise RetirementError("independent-review-capacity-not-reserved")
        actors = [self.root.get("executor_session_id"), self.reviewer.get("executor_session_id")]
        if not all(actors) or actors[0] == actors[1]:
            raise RetirementError("executor-cannot-accept-own-removal")
        packet = self.root["packet"]
        binding = packet.get("execution", {}).get("repository_retirement", {})
        if (
            binding.get("manifest_sha256") != manifest_binding(manifest)
            or binding.get("campaign_id") != manifest["campaign_id"]
        ):
            raise RetirementError("keeper-campaign-binding-mismatch")
        # Manifest hashes cannot include their own containing packet; the manifest
        # references run IDs, while the keeper's execution envelope binds its hash.
        if packet["spend"]["unit"] != "agent_minutes" or not 0 < packet["spend"]["limit"] <= 120:
            raise RetirementError("keeper-agent-minute-envelope-required")
        if (
            self.reviewer["packet"]["spend"]["unit"] != "agent_minutes"
            or self.reviewer["packet"]["spend"]["limit"] > 10
        ):
            raise RetirementError("independent-review-allowance-invalid")
        self.limit = packet["spend"]["limit"]
        self.deadline = min(timestamp(manifest["deadline"]), timestamp(packet["deadline"]))
        self.claimed = None
        if self.reviewer.get("parent_run_id") != self.root["run_id"]:
            raise RetirementError("reviewer-not-reserved-under-this-campaign")
        review_binding = self.reviewer["packet"].get("execution", {}).get("repository_retirement", {})
        if review_binding != binding:
            raise RetirementError("reviewer-campaign-binding-mismatch")

    def accounting(self) -> tuple[float, float]:
        total = 0.0
        for node in self.nodes.values():
            accepted = [row for row in node.get("receipts", []) if row.get("mutation_authorized") is True]
            if accepted:
                # Keeper receipt IDs are idempotent. Count the accepted run once.
                total += float(accepted[-1].get("spend", {}).get("agent_minutes", 0))
            elif node.get("lease", {}).get("state") in {"active", "reserved"}:
                total += max(0, (time.time() - timestamp(node["lease"]["acquired_at"])) / 60)
        return total, max(0, self.limit - total)

    def authorize(self, key: str, paths: list[str], *, review: bool = False) -> float:
        node = self.reviewer if review else self.root
        lease = node.get("lease", {})
        packet = node["packet"]
        if lease.get("state") not in {"reserved", "active"}:
            raise RetirementError("keeper-lease-not-live")
        required = {"repository-accept"} if review else {"repository-retire", "repository-sync", "repository-custody"}
        if not required.issubset(packet["authority"]["actions"]):
            raise RetirementError("keeper-action-not-authorized")
        prefixes = packet["authority"]["path_prefixes"]
        if any(
            not any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)
            for path in paths
        ):
            raise RetirementError("keeper-path-scope-mismatch")
        if not review and not any(claim["key"] == key and claim["mode"] == "exclusive" for claim in lease["resources"]):
            raise RetirementError("common-git-ownership-not-reserved")
        _consumed, remaining = self.accounting()
        if remaining <= 0:
            raise RetirementError("campaign-budget-exhausted")
        attempt_deadline = timestamp(lease["acquired_at"]) + (10 if review else 30) * 60
        deadline = min(self.deadline, timestamp(lease["hard_deadline"]), attempt_deadline, time.time() + remaining * 60)
        if time.time() >= deadline:
            raise RetirementError("campaign-deadline-exhausted")
        actor = os.environ.get("LIMEN_SESSION_ID")
        if not actor or actor != node["executor_session_id"]:
            raise RetirementError("native-session-identity-mismatch")
        if self.claimed is None:
            self.claimed = self.client.claim(lease["lease_id"], lease["generation"])
        return deadline

    def heartbeat(self, *, review: bool = False) -> None:
        node = self.reviewer if review else self.root
        if self.claimed:
            self.client.heartbeat(
                node["lease"]["lease_id"], self.claimed["capability_token"], generation=node["lease"]["generation"]
            )

    def accepted(self, proof_hash: str) -> bool:
        for receipt in self.reviewer.get("receipts", []):
            if (
                receipt.get("mutation_authorized") is True
                and receipt.get("outcome") == "succeeded"
                and receipt.get("executor", {}).get("session_id") == self.reviewer["executor_session_id"]
                and receipt.get("predicate", {}).get("exit_code") == 0
                and proof_hash in receipt.get("observed_heads_after", {}).values()
            ):
                return True
        return False

    def report(self, proofs: dict[str, str], *, review: bool = False, succeeded: bool = True) -> dict:
        node = self.reviewer if review else self.root
        lease = node["lease"]
        packet = node["packet"]
        elapsed = max(0, (time.time() - timestamp(lease["acquired_at"])) / 60)
        receipt = RunReceiptV1(
            receipt_id="repo-retirement-" + digest({"run": node["run_id"], "proofs": proofs})[:40],
            run_id=node["run_id"],
            lease_id=lease["lease_id"],
            lease_generation=lease["generation"],
            executor=AgentIdentityV1.model_validate(lease["executor"]),
            predicate=PredicateEvidenceV1(command=packet["predicate"], exit_code=0 if succeeded else 1),
            observed_heads_before={**lease.get("observed_heads", {}), **(proofs if review else {})},
            observed_heads_after={**lease.get("observed_heads", {}), **proofs},
            spend={"agent_minutes": elapsed},
            child_runs=tuple(node.get("children", [])),
            outcome="succeeded" if succeeded else "blocked",
            completed_at=datetime.now(UTC),
        )
        return self.client.report(
            lease["lease_id"], self.claimed["capability_token"], receipt, generation=lease["generation"]
        )
