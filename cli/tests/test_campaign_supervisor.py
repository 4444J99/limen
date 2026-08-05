"""Tests for the finite, keeper-backed institutional campaign supervisor."""

from __future__ import annotations

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest
from limen.conduct.campaign_relay import RelayLaunch
from limen.conduct.campaign_relay_protocol import _read_relay
from limen.conduct.models import AgentIdentityV1, AuthorityEnvelopeV1
from limen.conduct.supervisor import (
    CampaignSupervisorError,
    compile_omega_packets,
    load_capsule_receipt,
    load_capsule_receipt_ref,
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
    contract = new_contract("8h")
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
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")
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
            ],
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


def _publish_immutable_capsule(
    root: Path,
    source_receipt: Path,
    *,
    extra_path: bool = False,
    merge_commit: bool = False,
) -> tuple[str, str, str, str]:
    base = _git(root, "rev-parse", "HEAD")
    slug = "immutable-fixture"
    branch = f"work/{slug}"
    relative = f"docs/continuations/{slug}/workstream.json"
    payload = json.loads(source_receipt.read_text(encoding="utf-8"))
    payload.update({"branch": branch, "slug": slug})
    destination = root / relative
    destination.parent.mkdir(parents=True)
    destination.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    if extra_path:
        (root / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "publish immutable capsule")
    commit = _git(root, "rev-parse", "HEAD")
    if merge_commit:
        second_parent = _git(
            root,
            "commit-tree",
            f"{base}^{{tree}}",
            "-p",
            base,
            "-m",
            "second parent",
        )
        commit = _git(
            root,
            "commit-tree",
            f"{commit}^{{tree}}",
            "-p",
            base,
            "-p",
            second_parent,
            "-m",
            "merge-shaped capsule",
        )
    _git(root, "push", "origin", f"{commit}:refs/heads/{branch}")
    _git(
        root,
        "push",
        "origin",
        f"{commit}:refs/heads/limen-relay/capsule/{commit}",
    )
    return commit, base, relative, branch


def test_campaign_accepts_an_admitted_provider_neutral_v1_contract(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    loaded, remaining = load_capsule_receipt(receipt, root=root, now_epoch=now)
    assert loaded["contract"]["schema"] == "limen.workstream.contract.v1"
    assert remaining == 28_200


def test_immutable_capsule_ref_is_one_receipt_only_commit_on_its_expected_base(
    campaign_repo,
) -> None:
    root, source, now, _deadline = campaign_repo
    commit, base, path, branch = _publish_immutable_capsule(root, source)

    loaded, remaining = load_capsule_receipt_ref(
        root=root,
        commit=commit,
        base=base,
        path=path,
        branch=branch,
        now_epoch=now,
    )

    assert loaded["slug"] == "immutable-fixture"
    assert remaining == 28_200


def test_immutable_capsule_ref_rejects_a_mismatched_expected_base(
    campaign_repo,
) -> None:
    root, source, now, _deadline = campaign_repo
    commit, _base, path, branch = _publish_immutable_capsule(root, source)

    with pytest.raises(CampaignSupervisorError, match="expected base"):
        load_capsule_receipt_ref(
            root=root,
            commit=commit,
            base=commit,
            path=path,
            branch=branch,
            now_epoch=now,
        )


def test_immutable_capsule_ref_rejects_a_multifile_publication(
    campaign_repo,
) -> None:
    root, source, now, _deadline = campaign_repo
    commit, base, path, branch = _publish_immutable_capsule(
        root,
        source,
        extra_path=True,
    )

    with pytest.raises(CampaignSupervisorError, match="receipt-only"):
        load_capsule_receipt_ref(
            root=root,
            commit=commit,
            base=base,
            path=path,
            branch=branch,
            now_epoch=now,
        )


def test_immutable_capsule_ref_rejects_a_multiparent_publication(
    campaign_repo,
) -> None:
    root, source, now, _deadline = campaign_repo
    commit, base, path, branch = _publish_immutable_capsule(
        root,
        source,
        merge_commit=True,
    )

    with pytest.raises(CampaignSupervisorError, match="single-parent"):
        load_capsule_receipt_ref(
            root=root,
            commit=commit,
            base=base,
            path=path,
            branch=branch,
            now_epoch=now,
        )


def test_campaign_accepts_a_human_explicit_v2_contract(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    explicit = new_contract_v2(
        "8h",
        agent="codex",
        model="fixture-model",
        reasoning_effort="fixture-effort",
        sandbox="danger-full-access",
    )
    explicit["runway"] = payload["contract"]["runway"]
    payload["contract"] = explicit
    receipt.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    loaded, remaining = load_capsule_receipt(receipt, root=root, now_epoch=now)
    assert loaded["contract"]["schema"] == "limen.workstream.contract.v2"
    assert loaded["contract"]["primary_launch"]["selection"] == "human_explicit"
    assert remaining == 28_200


def test_campaign_rejects_an_unadmitted_provider_neutral_v1_contract(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["contract"] = new_contract("8h")
    receipt.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(CampaignSupervisorError, match="has not been admitted"):
        load_capsule_receipt(receipt, root=root, now_epoch=now)


def test_campaign_rejects_a_tampered_provider_neutral_v1_contract(campaign_repo) -> None:
    root, receipt, now, _deadline = campaign_repo
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["contract"]["conductor"]["provider_and_model"] = "pinned"
    receipt.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(CampaignSupervisorError, match="workstream conductor contract is invalid"):
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
        relay_launcher=lambda root, relay_id, **_kwargs: RelayLaunch(
            receipt=_read_relay(root, relay_id),
            launched=False,
        ),
    )
    assert result["boundary"] == "wait_relay"
    assert result["successor_required"] is True
    assert result["relay"]["schema"] == "limen.campaign_relay_boundary.v1"
    assert result["relay"]["state"] == "reserved"
    assert result["relay"]["attempts"] == 0
    assert "path" not in json.dumps(result["relay"])
    assert client.submissions == []


def test_t_minus_relay_budget_includes_elapsed_wake_preflight(campaign_repo) -> None:
    root, receipt, _now, deadline = campaign_repo
    observed: dict[str, float] = {}

    def launch(root, relay_id, *, timeout_seconds):
        observed["timeout_seconds"] = timeout_seconds
        return RelayLaunch(
            receipt=_read_relay(root, relay_id),
            launched=False,
        )

    result = run_campaign(
        client=FakeClient(),
        root=root,
        capsule=receipt,
        identity=_identity(),
        now_epoch=deadline - 1700,
        evaluator=lambda _root, _timeout: pytest.fail("evaluator must not run after T-30"),
        relay_launcher=launch,
        evaluation_timeout_seconds=300,
        wake_deadline_monotonic_ns=300_000_000_000,
        monotonic_ns=lambda: 50_000_000_000,
    )

    assert result["boundary"] == "wait_relay"
    assert observed["timeout_seconds"] == pytest.approx(70)


def test_concurrent_t_minus_beats_reserve_one_byte_stable_relay(campaign_repo) -> None:
    root, receipt, _now, deadline = campaign_repo

    def beat(_index: int) -> dict:
        return run_campaign(
            client=FakeClient(),
            root=root,
            capsule=receipt,
            identity=_identity(),
            now_epoch=deadline - 1700,
            evaluator=lambda _root, _timeout: pytest.fail("evaluator must not run after T-30"),
            relay_launcher=lambda root, relay_id, **_kwargs: RelayLaunch(
                receipt=_read_relay(root, relay_id),
                launched=False,
            ),
        )

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(beat, range(10)))

    projections = [json.dumps(result["relay"], sort_keys=True) for result in results]
    assert len(set(projections)) == 1
    assert all(result["boundary"] == "wait_relay" for result in results)
    store = Path(_git(root, "rev-parse", "--path-format=absolute", "--git-common-dir")) / "limen" / "campaign-relays"
    assert len(list(store.glob("*.json"))) == 1


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
