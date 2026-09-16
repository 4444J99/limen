"""Packet compilation must preserve broker underwriting and immutable replay."""

from datetime import datetime, timedelta, timezone
import hashlib

import pytest

from limen.conduct import ConductBroker, ConductConflict, ConductorSessionV1, MemoryStateStore
from limen.conduct.assessment_packet import AssessmentPacketError, compile_assessment_packet
from limen.conduct.assessor_source import AssessorSnapshot
from limen.conduct.models import AgentIdentityV1, ConductPrincipalV1
from limen.work_loan import WorkLoanV1, packet_work_loan_missing

NOW = datetime(2026, 9, 16, tzinfo=timezone.utc)
IDENTITY = AgentIdentityV1(agent="codex", surface="test", session_id="completion-conductor")
HINT = dict(
    key="1154799938:123:2",
    repository_id=1154799938,
    run_id=123,
    run_attempt=2,
    head_sha="a" * 40,
    coordinate="organvm/.github",
    automatic_acceptance=False,
)


def compile_packet(**overrides):
    data = b"fixture-only source"
    values = dict(
        hint=HINT,
        source=AssessorSnapshot("c" * 40, hashlib.sha256(data).hexdigest(), data),
        identity=IDENTITY,
        executor_session_id="completion-executor",
        deadline=NOW + timedelta(minutes=5),
        now=NOW,
        predicate="python3 scripts/reviewed-assessor.py",
        receipt_target="git:organvm/.github:docs/receipts/assessment.json",
        work_loan=WorkLoanV1(
            source_origin="system_debt",
            horizon="present",
            value_case="Reassess one completed dependency run",
            budget_cost=1,
            owner_surface="github:organvm/.github:pull-request:26",
        ),
    )
    values.update(overrides)
    return compile_assessment_packet(**values)


def test_packet_is_underwritten_read_only_and_reproducible():
    packet = compile_packet()
    assert packet_work_loan_missing(packet) == ()
    assert packet.model_dump() == compile_packet().model_dump()
    assert packet.effect == "read"
    assert not packet.authority.may_delegate
    assert not packet.authority.external_effects
    assert not packet.authority.path_prefixes
    assert packet.authority.repositories == frozenset({"organvm/.github"})
    assert packet.spend.reserve == packet.spend.limit == 1
    assert packet.retry.max_attempts == 1
    assert packet.fanout.max_children == packet.fanout.max_depth == 0
    assert packet.execution["assessor_source"]["commit"] == "c" * 40
    assert packet.execution["executor_session_id"] == "completion-executor"
    assert packet.execution["observed_heads"] == {"dependency_head": "a" * 40}


@pytest.mark.parametrize(
    "overrides",
    [
        {"hint": {**HINT, "run_attempt": True}},
        {"hint": {**HINT, "key": "wrong"}},
        {"hint": {**HINT, "automatic_acceptance": True}},
        {"hint": {**HINT, "head_sha": None}},
        {"source": AssessorSnapshot("c" * 40, "0" * 64, b"changed")},
        {"work_loan": None},
        {"predicate": "done"},
        {"receipt_target": "/tmp/receipt.json"},
        {"deadline": NOW + timedelta(seconds=95)},
        {"deadline": NOW + timedelta(seconds=901)},
        {"deadline": datetime(2026, 9, 16)},
        {"executor_session_id": ""},
    ],
)
def test_incomplete_contract_never_produces_packet(overrides):
    with pytest.raises(AssessmentPacketError):
        compile_packet(**overrides)


def test_real_broker_reuses_packet_and_rejects_changed_source():
    broker = ConductBroker(MemoryStateStore())
    principal = ConductPrincipalV1(
        principal_id="fixture-assessor",
        agent="codex",
        surface="test",
        roles=frozenset({"observer", "conductor", "executor"}),
    )
    for identity, capabilities in [
        (IDENTITY, {"conduct"}),
        (AgentIdentityV1(agent="codex", surface="test", session_id="completion-executor"), {"dependency-assessment"}),
    ]:
        broker.register(
            ConductorSessionV1(
                session_id=identity.session_id,
                identity=identity,
                origin="dispatched",
                capabilities=frozenset(capabilities),
                heartbeat_at=NOW,
            ),
            principal=principal,
            now=NOW,
        )
    packet = compile_packet()
    first = broker.submit(packet, principal=principal, now=NOW)
    duplicate = broker.submit(packet, principal=principal, now=NOW)
    assert duplicate["run_id"] == first["run_id"]
    assert duplicate["status"] == "duplicate"
    changed = b"different reviewed source"
    replacement = compile_packet(source=AssessorSnapshot("d" * 40, hashlib.sha256(changed).hexdigest(), changed))
    with pytest.raises(ConductConflict, match="immutable hashes"):
        broker.submit(replacement, principal=principal, now=NOW)


def test_cli_compiles_without_broker_or_execution(tmp_path, monkeypatch):
    import json
    from click.testing import CliRunner
    from limen.conduct.cli import conduct_group
    from limen.conduct.models import WorkPacketV1

    packet = compile_packet()
    source = b"fixture-only source"
    contract = dict(
        identity=IDENTITY.model_dump(mode="json"),
        executor_session_id="completion-executor",
        deadline=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        predicate=packet.predicate,
        receipt_target=packet.receipt_target,
        work_loan=packet.work_loan.model_dump(mode="json"),
        source_commit="c" * 40,
        script_sha256=hashlib.sha256(source).hexdigest(),
    )
    hint_path = tmp_path / "hint.json"
    contract_path = tmp_path / "contract.json"
    hint_path.write_text(json.dumps(HINT))
    contract_path.write_text(json.dumps(contract))
    monkeypatch.setattr(
        "limen.conduct.assessor_source.capture_assessor",
        lambda *a: AssessorSnapshot("c" * 40, hashlib.sha256(source).hexdigest(), source),
    )

    def forbidden(*args, **kwargs):
        pytest.fail("read-only compilation must not contact or execute")

    monkeypatch.setattr("limen.conduct.cli.client_from_env", forbidden)
    monkeypatch.setattr("limen.conduct.assessor_execution.execute_assessor", forbidden)
    arguments = [
        "compile-dependency-assessment",
        "--hint",
        str(hint_path),
        "--contract",
        str(contract_path),
        "--source-repository",
        str(tmp_path),
    ]
    result = CliRunner().invoke(conduct_group, arguments)
    assert result.exit_code == 0, result.output
    compiled = WorkPacketV1.model_validate_json(result.output)
    assert compiled.work_key == packet.work_key
    contract["credential"] = "must-not-be-copied"
    contract_path.write_text(json.dumps(contract))
    invalid = CliRunner().invoke(conduct_group, arguments)
    assert invalid.exit_code == 1
    assert "must-not-be-copied" not in invalid.output
