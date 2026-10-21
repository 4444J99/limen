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


KEEPAWAKE = ("/usr/bin/caffeinate", "-i", "-t", "300")


def _row(result, pid):
    return next((row for row in result["processes"] if row["pid"] == pid), None)


def test_harness_keepawake_child_of_checker_ancestry_is_checker_owned(cohort):
    # The harness wraps each tool call in `caffeinate -i -t 300`, a child of the shell the checker runs under; it
    # inherits the worktree cwd. Counting it as a survivor made every in-session closeout fail (measured 2026-10-19).
    processes, _, _, evaluate = cohort
    baseline = evaluate(excluded={104})
    processes[106] = ownership.Process(106, 104, os.getuid(), "start-keepawake", KEEPAWAKE, cwd=processes[101].cwd)
    result = evaluate(excluded={104})
    assert _row(result, 106) == {"pid": 106, "category": "checker", "reason": "checker_keepawake"}
    assert result["process_count"] == baseline["process_count"]
    assert result["counts"]["checker"] == baseline["counts"]["checker"] + 1


@pytest.mark.parametrize(
    ("argv", "parent"),
    [
        pytest.param(KEEPAWAKE, 100, id="parent-not-in-checker-ancestry"),
        pytest.param(("/usr/bin/caffeinate", "-s", "-t", "300"), 104, id="other-flag"),
        pytest.param(("/usr/bin/caffeinate", "-i", "-t", "99999"), 104, id="unbounded-timeout"),
        pytest.param(("/usr/bin/caffeinate", "-i", "-t", "0"), 104, id="zero-timeout"),
        pytest.param(("/usr/bin/caffeinate", "-i", "-t", "300", "sleep", "1"), 104, id="wraps-a-command"),
        pytest.param(("/usr/bin/caffeinate", "-i"), 104, id="no-timeout"),
        pytest.param(("/usr/bin/sleep", "-i", "-t", "300"), 104, id="not-caffeinate"),
    ],
)
def test_keepawake_lookalikes_stay_unknown_and_block(cohort, argv, parent):
    # The rule must not hide a real survivor: anything that is not the exact wrapper under the checker stays blocking.
    processes, _, _, evaluate = cohort
    baseline = evaluate(excluded={104})
    processes[106] = ownership.Process(106, parent, os.getuid(), "start-lookalike", argv, cwd=processes[101].cwd)
    result = evaluate(excluded={104})
    row = _row(result, 106)
    assert (row["category"], row["reason"]) == ("unknown", "ownership_unresolved")
    assert result["process_count"] == baseline["process_count"] + 1


def test_keepawake_outside_the_scope_root_is_not_counted_at_all(cohort):
    processes, _, _, evaluate = cohort
    baseline = evaluate(excluded={104})
    processes[106] = ownership.Process(106, 104, os.getuid(), "start-away", KEEPAWAKE, cwd=processes[100].cwd)
    result = evaluate(excluded={104})
    assert _row(result, 106) is None
    assert result["process_count"] == baseline["process_count"]


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


def test_native_witness_accepts_thread_spawn_parent_without_forked_from(tmp_path):
    sessions = tmp_path / "sessions" / "2026" / "10" / "17"
    sessions.mkdir(parents=True)
    child = {
        "type": "session_meta",
        "payload": {
            "id": "child",
            "session_id": "root",
            "source": {"subagent": {"thread_spawn": {"parent_thread_id": "root"}}},
        },
    }
    root = {"type": "session_meta", "payload": {"id": "root", "session_id": "root"}}
    (sessions / "rollout-child.jsonl").write_text(json.dumps(child) + "\n")
    (sessions / "rollout-root.jsonl").write_text(json.dumps(root) + "\n")

    witnesses = ownership.read_native_witnesses(tmp_path, {"child"})

    assert witnesses["child"]["parent_thread_id"] == "root"
    assert witnesses["child"]["session_id"] == witnesses["root"]["session_id"]


@pytest.mark.parametrize(
    "root_header",
    [
        None,
        {"type": "session_meta", "payload": {"id": "root", "session_id": "another-session"}},
    ],
    ids=["missing-parent", "cross-session-parent"],
)
def test_native_witness_rejects_missing_or_cross_session_parent(tmp_path, root_header):
    sessions = tmp_path / "sessions" / "2026" / "10" / "17"
    sessions.mkdir(parents=True)
    child = {
        "type": "session_meta",
        "payload": {
            "id": "child",
            "session_id": "root",
            "forked_from_id": "root",
            "source": {"subagent": {"thread_spawn": {"parent_thread_id": "root"}}},
        },
    }
    (sessions / "rollout-child.jsonl").write_text(json.dumps(child) + "\n")
    if root_header:
        (sessions / "rollout-root.jsonl").write_text(json.dumps(root_header) + "\n")

    with pytest.raises(ownership.ObservationUnavailable, match="native_ancestry_invalid"):
        ownership.read_native_witnesses(tmp_path, {"child"})


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


def test_subject_tagged_child_without_witness_stays_unmeasured(cohort):
    processes, _, witnesses, evaluate = cohort
    root = processes[101].cwd
    processes[104].cwd = root.parent / "undeclared"
    del witnesses["subject"]
    result = evaluate(scope_roots=(root / "declared",))
    rows = {row["pid"]: row for row in result["processes"]}
    assert rows[104]["category"] == "unmeasured"
    assert not result["complete"]


def test_command_file_digests_binds_every_named_file_and_the_helper(tmp_path):
    import hashlib

    from limen import process_services

    binary, script, helper = (tmp_path / name for name in ("server", "tool.py", "node_repl"))
    for path, body in ((binary, b"one"), (script, b"two"), (helper, b"three")):
        path.write_bytes(body)
    hashes: dict[str, str] = {}
    digests = process_services._command_file_digests([str(binary), "--flag", str(script)], str(helper), hashes)
    assert digests == {
        str(path.resolve()): hashlib.sha256(body).hexdigest()
        for path, body in ((binary, b"one"), (script, b"two"), (helper, b"three"))
    }
    assert hashes == digests  # the cross-command memo is populated


def test_canonical_argv_keeps_an_unresolvable_word_literally_and_still_resolves_the_rest(tmp_path, monkeypatch):
    # Observed 2026-10-18: EACCES on /usr/local/bin/1password-mcp, an argv word of an unrelated host
    # process, escaped from here and made every session-release check "unmeasured".
    from pathlib import Path

    target = tmp_path / "real-binary"
    target.write_bytes(b"x")
    link = tmp_path / "link-to-binary"
    link.symlink_to(target)
    locked = tmp_path / "locked"
    locked.write_bytes(b"y")
    real_resolve = Path.resolve

    def resolve(self, *args, **kwargs):
        if self.name == "locked":
            raise PermissionError(13, "Permission denied", str(self))
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    assert ownership.canonical_argv([str(locked), "--flag"]) == (str(locked), "--flag")  # argv[0], unresolvable
    assert ownership.canonical_argv(["server", str(locked)])[1] == str(locked)  # a later word, unresolvable
    # Resolvable words keep their normalization: a symlink still collapses to its target.
    assert ownership.canonical_argv([str(link)]) == (str(target.resolve()),)


def test_command_file_digests_ignores_non_files_and_relative_words(tmp_path):
    from limen import process_services

    assert process_services._command_file_digests(["server", "--flag", str(tmp_path / "missing")], None, {}) == {}


def test_command_file_digests_unresolvable_path_yields_no_contract_not_a_crash(tmp_path, monkeypatch):
    # An unreadable absolute argv path (observed: /usr/local/bin/1password-mcp) used to escape as
    # PermissionError and turn every session-release check into "unmeasured".
    from pathlib import Path

    from limen import process_services

    readable, locked = tmp_path / "readable", tmp_path / "locked"
    readable.write_bytes(b"ok")
    locked.write_bytes(b"sealed")
    real_resolve = Path.resolve

    def resolve(self, *args, **kwargs):
        if self.name == "locked":
            raise PermissionError(13, "Permission denied", str(self))
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    hashes: dict[str, str] = {}
    assert process_services._command_file_digests([str(readable), str(locked)], None, hashes) is None


def test_command_file_digests_unreadable_bytes_yield_no_contract_and_never_a_partial_one(tmp_path, monkeypatch):
    from pathlib import Path

    from limen import process_services

    readable, sealed = tmp_path / "readable", tmp_path / "sealed"
    readable.write_bytes(b"ok")
    sealed.write_bytes(b"sealed")
    real_open = Path.open

    def opener(self, *args, **kwargs):
        if self.name == "sealed":
            raise PermissionError(13, "Permission denied", str(self))
        return real_open(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opener)
    # The readable file is hashed first, yet the result is None: a contract that silently omits the
    # unreadable file's bytes would be weaker provenance, not a fail-closed one.
    assert process_services._command_file_digests([str(readable), str(sealed)], None, {}) is None
