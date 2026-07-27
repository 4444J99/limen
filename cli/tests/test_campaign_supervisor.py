"""Tests for the finite, keeper-backed institutional campaign supervisor."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from limen.conduct.models import AgentIdentityV1, AuthorityEnvelopeV1
from limen.conduct.supervisor import (
    CampaignSupervisorError,
    compile_omega_packets,
    load_capsule_receipt,
    run_campaign,
    validate_omega_evaluation,
)
from limen.omega_remediation import OmegaRemediationV1, remediation_payload
from limen.work_loan import WorkLoanV1, packet_work_loan_missing
from limen.workstream_contract import RECEIPT_MODULES, new_contract, new_contract_v2


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def campaign_repo(tmp_path: Path) -> tuple[Path, Path, int, int]:
    root = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "campaign@example.invalid")
    _git(root, "config", "user.name", "Campaign Test")
    now = 2_000_000_000
    started = now - 600
    deadline = started + 8 * 60 * 60
    contract = new_contract_v2(
        "8h",
        agent="codex",
        model="fixture-model",
        reasoning_effort="fixture-effort",
        sandbox="danger-full-access",
    )
    contract["runway"].update(
        {
            "started_epoch": started,
            "deadline_epoch": deadline,
            "started_at": datetime.fromtimestamp(started, UTC).isoformat(timespec="seconds"),
            "deadline_at": datetime.fromtimestamp(deadline, UTC).isoformat(timespec="seconds"),
        }
    )
    receipt = root / "docs" / "continuations" / "campaign-fixture" / "workstream.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "branch": "work/campaign-fixture",
                "contract": contract,
                "private_capsule": {
                    "content": "redacted",
                    "modules": list(RECEIPT_MODULES),
                },
                "schema": "limen.workstream.receipt.v1",
                "slug": "campaign-fixture",
                "workstream": "institutional-omega",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (root / "README.md").write_text("fixture\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "fixture")
    _git(tmp_path, "init", "--bare", str(remote))
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "-u", "origin", "main")
    return root, receipt, now, deadline


def _remediation(rung_id: str, owner: str = "fixture-owner") -> dict:
    return remediation_payload(
        OmegaRemediationV1(
            id=rung_id,
            owner=owner,
            next_action=f"Run and owner-route {rung_id}.",
            predicate=f"python3 scripts/check.py --rung {rung_id}",
            required_capabilities=frozenset({"shell"}),
            authority=AuthorityEnvelopeV1(
                actions=frozenset({"read"}),
                repositories=frozenset({"organvm/limen"}),
                path_prefixes=frozenset({"."}),
                may_delegate=False,
            ),
            effect="read",
            output_ceiling_bytes=4096,
            receipt_target="github:organvm/limen:issue:1571",
            work_loan=WorkLoanV1(
                source_origin="system_debt",
                horizon="present",
                value_case=f"Close {rung_id}.",
                budget_cost=1,
                owner_surface=owner,
            ),
        )
    )


def _omega(*statuses: tuple[str, str]) -> dict:
    rows = [
        {
            "id": rung_id,
            "remediation": _remediation(rung_id),
            "rung": rung_id,
            "status": status,
            "tier": "det",
        }
        for rung_id, status in statuses
    ]
    counts = {status: sum(row["status"] == status for row in rows) for status in ("PASS", "FAIL", "SKIP")}
    return {
        "schema_version": 3,
        "contract_hash": "a" * 64,
        "fail": counts["FAIL"],
        "offline": False,
        "pass": counts["PASS"],
        "rungs": rows,
        "skip": counts["SKIP"],
        "strict": True,
        "verdict": "HOLDS" if not counts["FAIL"] and not counts["SKIP"] else "BROKEN",
    }


class FakeClient:
    def __init__(self) -> None:
        self.submissions = []
        self.capability_calls = 0

    def capabilities(self):
        self.capability_calls += 1
        return {
            "schema_version": "limen.conduct_capabilities.v1",
            "sessions": [
                {
                    "session_id": "heavy-local",
                    "capabilities": ["conduct", "shell", "local_heavy"],
                    "healthy": True,
                    "accepting_work": True,
                    "active_leases": 0,
                    "concurrency": 1,
                },
                {
                    "session_id": "remote-a",
                    "capabilities": ["shell"],
                    "healthy": True,
                    "accepting_work": True,
                    "active_leases": 0,
                    "concurrency": 2,
                },
                {
                    "session_id": "remote-b",
                    "capabilities": ["shell"],
                    "healthy": True,
                    "accepting_work": True,
                    "active_leases": 0,
                    "concurrency": 2,
                },
            ]
        }

    def submit_graph(self, packets):
        self.submissions.append(packets)
        return {
            "status": "reserved",
            "root_run_id": packets[1].root_run_id,
            "runs": [{"work_id": packet.work_id} for packet in packets],
        }

    def harvest(self, root_run_id):
        packets = self.submissions[-1]
        return {
            "root_run_id": root_run_id,
            "run_count": len(packets),
            "unharvested": [packet.work_id for packet in packets[1:]],
        }


def _identity() -> AgentIdentityV1:
    return AgentIdentityV1(
        agent="codex",
        surface="workstream",
        session_id="campaign-session",
    )


def test_campaign_rejects_a_legacy_launch_contract(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    legacy = new_contract("8h")
    legacy["runway"] = payload["contract"]["runway"]
    payload["contract"] = legacy
    receipt.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(CampaignSupervisorError, match="requires a v2 launch contract"):
        load_capsule_receipt(receipt, root=root, now_epoch=now)


def test_failed_rungs_submit_one_atomic_typed_graph(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    client = FakeClient()
    result = run_campaign(
        client=client,
        root=root,
        capsule=receipt,
        identity=_identity(),
        now_epoch=now,
        evaluator=lambda _root, _timeout: (
            1,
            _omega(("core.one", "FAIL"), ("core.two", "PASS")),
        ),
        settler=lambda _root, _timeout: pytest.fail("settler must not run"),
    )
    assert result["boundary"] == "continue"
    assert result["failed_rung_count"] == 1
    assert result["packet_count"] == 2
    assert client.capability_calls == 1
    assert len(client.submissions) == 1
    root_packet, leaf = client.submissions[0]
    assert leaf.root_run_id == leaf.parent_run_id == result["root_run_id"]
    assert root_packet.campaign.campaign_id == leaf.campaign.campaign_id
    assert leaf.campaign.owner == "fixture-owner"
    assert leaf.authority.may_delegate is False
    assert leaf.effect == "read"
    assert root_packet.preferred_agent is None
    assert leaf.preferred_agent is None
    assert packet_work_loan_missing(root_packet) == ()
    assert packet_work_loan_missing(leaf) == ()
    serialized = json.dumps([packet.model_dump(mode="json") for packet in client.submissions[0]])
    assert "fixture-model" not in serialized
    assert "provider:" not in serialized


def test_keeper_acknowledgement_must_match_the_exact_graph(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo

    class WrongRootClient(FakeClient):
        def submit_graph(self, packets):
            result = super().submit_graph(packets)
            result["root_run_id"] = "run-" + ("0" * 32)
            return result

    with pytest.raises(CampaignSupervisorError, match="exact typed remediation graph"):
        run_campaign(
            client=WrongRootClient(),
            root=root,
            capsule=receipt,
            identity=_identity(),
            now_epoch=now,
            evaluator=lambda _root, _timeout: (1, _omega(("core.one", "FAIL"))),
        )


def test_unavailable_required_capability_selects_switch_without_submission(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    client = FakeClient()

    def unavailable():
        client.capability_calls += 1
        return {
            "schema_version": "limen.conduct_capabilities.v1",
            "sessions": [
                {
                    "session_id": "full-local",
                    "capabilities": ["conduct", "shell"],
                    "healthy": True,
                    "accepting_work": True,
                    "active_leases": 1,
                    "concurrency": 1,
                }
            ],
        }

    client.capabilities = unavailable
    result = run_campaign(
        client=client,
        root=root,
        capsule=receipt,
        identity=_identity(),
        now_epoch=now,
        evaluator=lambda _root, _timeout: (1, _omega(("core.one", "FAIL"))),
    )
    assert result["boundary"] == "switch"
    assert result["missing_capabilities"] == [["conduct"], ["shell"]]
    assert client.submissions == []


def test_t_minus_boundary_admits_no_work(campaign_repo) -> None:
    root, receipt, _now, deadline = campaign_repo
    client = FakeClient()
    result = run_campaign(
        client=client,
        root=root,
        capsule=receipt,
        identity=_identity(),
        now_epoch=deadline - 1700,
        evaluator=lambda _root, _timeout: pytest.fail("evaluator must not run after T-30"),
    )
    assert result["boundary"] == "wait_relay"
    assert result["successor_required"] is True
    assert client.submissions == []


def test_settled_requires_green_strict_omega_and_three_two_pass_receipts(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    client = FakeClient()
    settlement = [
        {"mode": "--run", "changed": True},
        {"mode": "--check", "changed": False},
        {"mode": "--check", "changed": False},
    ]
    result = run_campaign(
        client=client,
        root=root,
        capsule=receipt,
        identity=_identity(),
        now_epoch=now,
        evaluator=lambda _root, _timeout: (0, _omega(("core.one", "PASS"))),
        settler=lambda _root, _timeout: settlement,
    )
    assert result["boundary"] == "settled"
    assert result["settlement"] == settlement
    assert client.capability_calls == 0
    assert client.submissions == []


def test_settled_rejects_incomplete_or_changed_two_pass_receipts(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    for settlement in (
        [{"mode": "--run", "changed": False}],
        [
            {"mode": "--run", "changed": False},
            {"mode": "--check", "changed": False},
            {"mode": "--check", "changed": True},
        ],
    ):
        with pytest.raises(CampaignSupervisorError, match="settlement|two-pass"):
            run_campaign(
                client=FakeClient(),
                root=root,
                capsule=receipt,
                identity=_identity(),
                now_epoch=now,
                evaluator=lambda _root, _timeout: (0, _omega(("core.one", "PASS"))),
                settler=lambda _root, _timeout, receipts=settlement: receipts,
            )


def test_untyped_or_mismatched_omega_rung_fails_before_submission(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    client = FakeClient()
    payload = _omega(("core.one", "FAIL"))
    payload["rungs"][0].pop("remediation")
    with pytest.raises(CampaignSupervisorError, match="typed remediation metadata is invalid"):
        run_campaign(
            client=client,
            root=root,
            capsule=receipt,
            identity=_identity(),
            now_epoch=now,
            evaluator=lambda _root, _timeout: (1, payload),
        )
    assert client.submissions == []


def test_dirty_or_moved_main_fails_before_evaluation(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    (root / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(CampaignSupervisorError, match="not clean"):
        run_campaign(
            client=FakeClient(),
            root=root,
            capsule=receipt,
            identity=_identity(),
            now_epoch=now,
            evaluator=lambda _root, _timeout: pytest.fail("evaluator must not run"),
        )


def test_clean_local_head_that_moved_past_remote_default_fails(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    (root / "README.md").write_text("moved\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-qm", "move local head")
    with pytest.raises(CampaignSupervisorError, match="not exact remote default"):
        run_campaign(
            client=FakeClient(),
            root=root,
            capsule=receipt,
            identity=_identity(),
            now_epoch=now,
            evaluator=lambda _root, _timeout: pytest.fail("evaluator must not run"),
        )


def test_capsule_receipt_symlink_fails_before_evaluation(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    linked = root / "capsule-link.json"
    linked.symlink_to(receipt)
    with pytest.raises(CampaignSupervisorError, match="must not be a symlink"):
        load_capsule_receipt(linked, root=root, now_epoch=now)


def test_expired_capsule_fails_before_evaluation(campaign_repo) -> None:
    root, receipt, _now, deadline = campaign_repo
    with pytest.raises(CampaignSupervisorError, match="runway has expired"):
        load_capsule_receipt(receipt, root=root, now_epoch=deadline)


def test_compile_rejects_unclaimed_write_metadata(campaign_repo) -> None:
    root, receipt_path, _now, _deadline = campaign_repo
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    git_state = {
        "head": _git(root, "rev-parse", "HEAD"),
        "remote_main": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
    }
    payload = _omega(("core.one", "FAIL"))
    failed, contract_hash = validate_omega_evaluation(1, payload)
    remediation = failed[0]["remediation"]
    failed[0]["remediation"] = remediation.model_copy(
        update={
            "effect": "write",
            "authority": remediation.authority.model_copy(update={"actions": frozenset({"read", "write"})}),
        }
    )
    with pytest.raises(CampaignSupervisorError, match="explicit resource claims"):
        compile_omega_packets(
            receipt=receipt,
            identity=_identity(),
            git_state=git_state,
            omega_payload=payload,
            failed_rows=failed,
            omega_contract_hash=contract_hash,
        )


def test_packet_identity_deduplicates_one_state_but_changes_with_omega_state(campaign_repo) -> None:
    root, receipt_path, _now, _deadline = campaign_repo
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    git_state = {
        "head": _git(root, "rev-parse", "HEAD"),
        "remote_main": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
    }
    first_payload = _omega(("core.one", "FAIL"))
    first_failed, contract_hash = validate_omega_evaluation(1, first_payload)
    first = compile_omega_packets(
        receipt=receipt,
        identity=_identity(),
        git_state=git_state,
        omega_payload=first_payload,
        failed_rows=first_failed,
        omega_contract_hash=contract_hash,
    )
    duplicate = compile_omega_packets(
        receipt=receipt,
        identity=_identity(),
        git_state=git_state,
        omega_payload=first_payload,
        failed_rows=first_failed,
        omega_contract_hash=contract_hash,
    )
    changed_payload = _omega(("core.one", "SKIP"))
    changed_failed, changed_contract_hash = validate_omega_evaluation(1, changed_payload)
    changed = compile_omega_packets(
        receipt=receipt,
        identity=_identity(),
        git_state=git_state,
        omega_payload=changed_payload,
        failed_rows=changed_failed,
        omega_contract_hash=changed_contract_hash,
    )
    assert [packet.work_key for packet in first] == [packet.work_key for packet in duplicate]
    assert [packet.work_id for packet in first] == [packet.work_id for packet in duplicate]
    assert {packet.work_key for packet in first}.isdisjoint(packet.work_key for packet in changed)
