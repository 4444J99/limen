"""Shared infrastructure never erases surviving native jobs or unknown children."""

import json
import os

import pytest
from limen import process_ownership as ownership


@pytest.fixture
def cohort(tmp_path):
    root = tmp_path / "caller"
    root.mkdir()
    host = ownership.Process(100, 1, os.getuid(), "start-host", ("/codex", "app-server"), cwd=tmp_path)
    service = ownership.Process(101, 100, os.getuid(), "start-service", ("/server", "stdio"), cwd=root)
    helper = ownership.Process(102, 101, os.getuid(), "start-helper", ("/helper",), cwd=root)
    foreign = ownership.Process(
        103,
        100,
        os.getuid(),
        "start-foreign",
        ("/shell",),
        {"CODEX_THREAD_ID": "peer", "CODEX_SESSION_ID": "peer"},
        root,
    )
    own = ownership.Process(
        104,
        100,
        os.getuid(),
        "start-own",
        ("/shell",),
        {"CODEX_THREAD_ID": "subject", "CODEX_SESSION_ID": "subject"},
        root / "subdirectory",
    )
    unknown = ownership.Process(105, 101, os.getuid(), "start-unknown", ("/unknown",), cwd=root)
    processes = {row.pid: row for row in (host, service, helper, foreign, own, unknown)}
    contracts = [
        {
            "service_id": "provider",
            "argv": ["/server", "stdio"],
            "parent_service": None,
            "host_argv": list(host.argv),
            "contract_sha256": "contract",
        },
        {
            "service_id": "provider",
            "argv": ["/helper"],
            "parent_service": "provider",
            "host_argv": list(host.argv),
            "contract_sha256": "helper-contract",
        },
    ]
    witnesses = {key: {"thread_id": key, "session_id": key, "parent_thread_id": None} for key in ("subject", "peer")}

    def evaluate(**changes):
        return ownership.assess(
            processes,
            changes.pop("excluded", set()),
            root,
            "subject",
            contracts=changes.pop("contracts", contracts),
            witnesses=changes.pop("witnesses", witnesses),
            identity=changes.pop("identity", lambda pid: processes[pid].started),
            **changes,
        )

    return processes, contracts, witnesses, evaluate


def test_mixed_native_host_census_retains_peers_and_services_but_blocks_jobs(cohort):
    _, _, _, evaluate = cohort
    result = evaluate()
    assert result["complete"]
    assert result["counts"]["shared_service"] == 2
    assert result["counts"]["foreign_session"] == 1
    assert result["counts"]["owned_survivor"] == 1
    assert result["counts"]["unknown"] == 1
    assert result["process_count"] == 2


def test_command_normalization_is_bounded_to_each_census(cohort, monkeypatch):
    _, _, _, evaluate = cohort
    calls = []
    original = ownership.canonical_argv

    def normalize(argv):
        calls.append(tuple(argv))
        return original(argv)

    monkeypatch.setattr(ownership, "canonical_argv", normalize)
    first = evaluate()
    assert len(calls) == len(set(calls))
    before = len(calls)
    assert evaluate() == first
    assert len(calls) == before * 2  # No cached authority survives a new observation.


def test_shared_services_alone_allow_release_without_stopping_them(cohort):
    processes, _, _, evaluate = cohort
    del processes[104], processes[105]
    before = dict(processes)
    assert evaluate()["process_count"] == 0
    assert processes == before


def test_arbitrary_service_child_does_not_inherit_exemption(cohort):
    _, _, _, evaluate = cohort
    assert next(row for row in evaluate()["processes"] if row["pid"] == 105)["category"] == "unknown"


def test_root_membership_without_exact_thread_never_owns_or_exempts_a_job(cohort):
    processes, _, _, evaluate = cohort
    processes[104].env = {"CODEX_SESSION_ID": "subject"}
    assert next(row for row in evaluate()["processes"] if row["pid"] == 104)["category"] == "unknown"


def test_exact_native_job_looks_like_service_but_still_blocks(cohort):
    processes, _, _, evaluate = cohort
    processes[101].env = {"CODEX_THREAD_ID": "subject", "CODEX_SESSION_ID": "subject"}
    assert next(row for row in evaluate()["processes"] if row["pid"] == 101)["category"] == "owned_survivor"


def test_child_execution_remains_subject_responsibility(cohort):
    processes, _, witnesses, evaluate = cohort
    processes[104].env = {"CODEX_THREAD_ID": "child", "CODEX_SESSION_ID": "subject"}
    witnesses["child"] = {"thread_id": "child", "session_id": "subject", "parent_thread_id": "subject"}
    assert next(row for row in evaluate()["processes"] if row["pid"] == 104)["category"] == "owned_survivor"


@pytest.mark.parametrize("case", ["pid_reuse", "unreadable", "missing_header", "wrong_root", "conflicting_contract"])
def test_missing_or_conflicting_observation_is_unmeasured(cohort, case):
    processes, contracts, witnesses, evaluate = cohort
    args = {}
    if case == "pid_reuse":
        args["identity"] = lambda pid: "reused" if pid == 101 else processes[pid].started
    elif case == "unreadable":
        processes[101].readable = False
    elif case == "missing_header":
        del witnesses["subject"]
    elif case == "wrong_root":
        processes[104].env["CODEX_SESSION_ID"] = "another-root"
    else:
        contracts.append({**contracts[0], "service_id": "other-provider"})
    assert not evaluate(**args)["complete"]


@pytest.mark.parametrize(
    "field", ["process_identity", "argv_sha256", "contract_sha256", "host_identity", "host_pid", "service_id"]
)
def test_legacy_adoption_revalidates_each_evidence_field(cohort, field):
    _, _, _, evaluate = cohort
    row = next(row for row in evaluate()["processes"] if row["pid"] == 101)
    row[field] = "invalid"
    assert not evaluate(evidence=[row])["complete"]


def test_valid_adoption_is_read_only_and_unknown_rows_stay_blocked(cohort):
    _, _, _, evaluate = cohort
    row = next(row for row in evaluate()["processes"] if row["pid"] == 101)
    assert evaluate(evidence=[row])["counts"]["shared_service"] == 2
    assert evaluate(evidence=[row])["process_count"] == 2


def test_checker_observation_children_are_excluded(cohort):
    _, _, _, evaluate = cohort
    result = evaluate(excluded={104, 105})
    assert result["process_count"] == 0
    assert result["counts"]["checker"] == 2


def test_native_witness_reads_header_only_and_checks_child_lineage(tmp_path):
    path = tmp_path / "transcript"
    header = {
        "type": "session_meta",
        "payload": {
            "id": "child",
            "session_id": "root",
            "forked_from_id": "root",
            "source": {"subagent": {"thread_spawn": {"parent_thread_id": "root"}}},
        },
    }
    path.write_text(json.dumps(header) + "\nPRIVATE BODY IS NOT JSON")
    assert ownership.transcript_witness(path)["parent_thread_id"] == "root"
    header["payload"]["forked_from_id"] = "another"
    path.write_text(json.dumps(header))
    with pytest.raises(ownership.ObservationUnavailable):
        ownership.transcript_witness(path)


def test_snapshot_rejects_permission_limited_census(monkeypatch, tmp_path):
    from unittest.mock import MagicMock

    monkeypatch.setattr(
        ownership.subprocess,
        "run",
        lambda *args, **kwargs: type("Result", (), {"stdout": f"{os.getpid()} 1 {os.getuid()} checker"})(),
    )
    child = MagicMock()
    child.pid = 999999
    child.returncode = 1
    child.communicate.return_value = (b"partial", b"private diagnostic")
    context = MagicMock()
    context.__enter__.return_value = child
    monkeypatch.setattr(ownership.subprocess, "Popen", lambda *args, **kwargs: context)
    with pytest.raises(ownership.ObservationUnavailable, match="incomplete"):
        ownership.snapshot(tmp_path)


def test_native_details_return_no_secrets():
    if not sys_platform_supported():
        pytest.skip("native identity available on Darwin/Linux")
    argv, env = ownership.native_details(os.getpid())
    assert argv
    assert set(env) <= ownership.ENV_KEYS


def sys_platform_supported():
    import sys

    return sys.platform == "darwin" or sys.platform.startswith("linux")


def test_multi_scope_anchor_is_exact_and_native_lineage_is_global(cohort):
    processes, _, _, evaluate = cohort
    root = processes[101].cwd
    declared = root / "declared"
    processes[105].cwd = root / "undeclared"
    processes[104].cwd = root.parent / "outside"
    processes[102].cwd = declared
    result = evaluate(scope_roots=(declared,))
    rows = {row["pid"]: row for row in result["processes"]}
    assert 105 not in rows
    assert rows[101]["category"] == "shared_service"
    assert rows[102]["category"] == "shared_service"
    assert rows[104]["category"] == "owned_survivor"
    assert result["process_count"] == 1


def test_multi_scope_unknown_anchor_and_unreadable_root_fail(cohort):
    processes, _, _, evaluate = cohort
    root = processes[101].cwd
    processes[104].env = {}
    processes[104].readable = False
    result = evaluate(scope_roots=(root / "subdirectory",))
    assert not result["complete"]
    assert result["counts"]["unknown"] == 1


def test_multi_scope_observer_uses_one_snapshot(cohort, monkeypatch):
    from limen import process_services

    processes, contracts, witnesses, _ = cohort
    root = processes[101].cwd
    calls = []
    monkeypatch.setattr(ownership, "snapshot", lambda path: (calls.append(path) or processes, set()))
    monkeypatch.setattr(ownership, "read_native_witnesses", lambda *args: witnesses)
    monkeypatch.setattr(process_services, "service_contracts", lambda *args: contracts)
    monkeypatch.setattr(ownership, "process_identity", lambda pid: processes[pid].started)
    monkeypatch.setattr(ownership, "assess", lambda *args, **kwargs: {"complete": True})
    assert ownership.observe_many((root, root / "nested"), "subject", anchor=root)["complete"]
    assert calls == [root]
