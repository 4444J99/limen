"""Local preparation refusals cannot consume a provider reservation."""

from types import SimpleNamespace

import pytest

import limen.dispatch as dispatch
import limen.tabularius as tabularius
from limen.conduct.client import BrokerUnavailable
from limen.io import save_limen_file
from test_serial_claim_custody import _open_board


@pytest.fixture(autouse=True)
def _hermetic_dispatch(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "hermetic-root"))
    monkeypatch.setenv("LIMEN_WORKTREE_DEBT_GATE", "0")
    monkeypatch.setenv("LIMEN_DISPATCH_ADMISSION", "0")
    for name in ("LIMEN_VALUE_REPOS", "LIMEN_VALUE_REPOS_FILE", "LIMEN_VALUE_GATE_STRICT"):
        monkeypatch.delenv(name, raising=False)


def _journal(monkeypatch):
    actuals = []
    store = SimpleNamespace(
        record_reservation=lambda *a, **kw: None,
        record_actual=lambda *a, **kw: actuals.append(kw),
    )
    monkeypatch.setattr(dispatch, "default_work_loan_journal_store", lambda *a: store)
    return actuals


@pytest.mark.parametrize(
    "case",
    [
        "agent_gate",
        "selection",
        "claude_contract",
        "workstream_contract",
        "no_model",
        "inplace_repo",
        "inplace_packet",
        "inplace_host",
        "isolated_repo",
        "isolated_clone",
        "isolated_initialize",
        "isolated_workspace",
        "isolated_host",
        "isolated_packet",
    ],
)
def test_local_presubmit_rejections_record_zero_provider_runs(tmp_path, monkeypatch, capsys, case):
    task = _open_board(tmp_path / "tasks.yaml").tasks[0]
    agent = "opencode" if case == "no_model" else "codex"
    task.target_agent = agent
    actuals = _journal(monkeypatch)
    monkeypatch.setattr(dispatch, "agent_can_run_task", lambda *a: case != "agent_gate")
    monkeypatch.setattr(dispatch, "_agent_argv", lambda *a: ["exec"])
    monkeypatch.setattr(dispatch, "_worktree_isolation_enabled", lambda: case.startswith("isolated_"))
    monkeypatch.setattr(dispatch, "_resolve_agent_binary", lambda *a: "synthetic-provider")
    monkeypatch.setattr(dispatch, "_resolve_repo_dir", lambda *a: tmp_path)
    monkeypatch.setattr(dispatch, "_workstream_packet_for", lambda *a: None)
    monkeypatch.setattr(dispatch, "_build_prompt", lambda *a: "synthetic prompt")
    monkeypatch.setattr(dispatch, "_stable_agent_host_command", lambda command, *a: command)
    monkeypatch.setattr(dispatch, "_run_cmd", lambda *a, **kw: pytest.fail("provider must not start"))
    monkeypatch.setattr(dispatch, "_run_capture", lambda *a, **kw: pytest.fail("provider must not start"))
    if case in {"selection", "claude_contract", "workstream_contract"}:
        error = {
            "selection": dispatch.ProviderSelectionError,
            "claude_contract": dispatch.ClaudeLaunchContractError,
            "workstream_contract": dispatch.WorkstreamLaunchContractError,
        }[case]
        monkeypatch.setattr(dispatch, "_agent_argv", lambda *a: (_ for _ in ()).throw(error("private-error-token")))
    if case in {"inplace_repo", "isolated_repo", "isolated_clone"}:
        monkeypatch.setattr(dispatch, "_resolve_repo_dir", lambda *a: None)
        monkeypatch.setattr(
            dispatch,
            "_repo_unavailable_reason",
            lambda *a: "repo unavailable: private-error-token" if case == "isolated_repo" else None,
        )
        monkeypatch.setattr(dispatch, "_clone_repo", lambda *a: None)
    if case == "inplace_packet":
        monkeypatch.setattr(dispatch, "_workstream_packet_for", lambda *a: {"schema_version": "fixture"})
    if case in {"inplace_host", "isolated_host"}:
        monkeypatch.setattr(
            dispatch,
            "_stable_agent_host_command",
            lambda *a, **kw: (_ for _ in ()).throw(dispatch.StableAgentHostError("private-error-token")),
        )
    if case in {"isolated_initialize", "isolated_workspace"}:
        monkeypatch.setattr(dispatch, "_default_branch", lambda *a: "main")
        monkeypatch.setattr(dispatch, "_same_repo_pr_head_for_task", lambda *a: None)
        monkeypatch.setattr(dispatch, "_isolation_root", lambda: tmp_path / "isolation")
        monkeypatch.setattr(dispatch, "_git_plumbing", lambda *a, **kw: None)
        monkeypatch.setattr(
            dispatch,
            "initialize_worktree",
            lambda *a, **kw: (_ for _ in ()).throw(
                dispatch.WorktreeInitializationError(
                    "private-error-token", journal_path=tmp_path / "journal.json", receipt={}
                )
            ),
        )
        if case == "isolated_workspace":
            monkeypatch.setattr(dispatch, "initialize_worktree", lambda *a, **kw: None)
            monkeypatch.setattr(dispatch, "_record_worktree_birth", lambda *a, **kw: None)
            monkeypatch.setattr(dispatch, "_mark_machine_admission_born", lambda *a, **kw: None)
            monkeypatch.setattr(dispatch, "_cleanup_isolated_worktree", lambda *a, **kw: None)
            monkeypatch.setattr(
                dispatch,
                "_workspace_agent_args",
                lambda *a: (_ for _ in ()).throw(dispatch.WorkstreamLaunchContractError("private-error-token")),
            )
    if case in {"isolated_host", "isolated_packet"}:
        monkeypatch.setattr(dispatch, "_lane_run_env", lambda *a: {})
        monkeypatch.setattr(dispatch, "_assert_final_workstream_launch", lambda *a: None)
        if case == "isolated_packet":
            monkeypatch.setattr(
                dispatch,
                "_assert_final_workstream_launch",
                lambda *a: (_ for _ in ()).throw(dispatch.WorkstreamLaunchContractError("private-error-token")),
            )

        def call():
            return dispatch._run_isolated_agent(agent, task, tmp_path, ["synthetic-provider"], 1)
    else:

        def call():
            return dispatch._call_local_agent(agent, task, False)

    monkeypatch.setattr(dispatch, "call_agent_dispatch", lambda *a, **kw: call())
    result = dispatch._journaled_agent_dispatch(agent, task, False, "a" * 64)
    assert dispatch._is_prelaunch_result(result)
    assert actuals[0]["metrics"] == {"runs": 0}
    assert "private-error-token" not in str(result) + capsys.readouterr().out
    if case in {"workstream_contract", "inplace_packet", "isolated_workspace", "isolated_packet"}:
        assert dispatch._is_workstream_successor_result(result)


@pytest.mark.parametrize("refund_ack", [True, False])
def test_local_prelaunch_refund_restores_remainder_only_after_canonical_acceptance(tmp_path, monkeypatch, refund_ack):
    path = tmp_path / "tasks.yaml"
    board = _open_board(path)
    first = board.tasks[0].id
    board.tasks[0].priority = "critical"
    board.tasks.append(board.tasks[0].model_copy(update={"id": "NEXT", "priority": "high"}, deep=True))
    board.portal.budget.daily = 1
    board.portal.budget.per_agent["codex"] = 1
    save_limen_file(path, board)
    actuals = _journal(monkeypatch)
    launched = []
    events = []
    monkeypatch.setattr(
        dispatch,
        "_agent_argv",
        lambda *a: (_ for _ in ()).throw(dispatch.ProviderSelectionError("private-error-token")),
    )

    def provider(_agent, task, **kwargs):
        if task.id == first:
            return dispatch._call_local_agent("codex", task, False)
        events.append("provider-start")
        launched.append(task.id)
        return True

    sync = dispatch.apply_limen_file_sync

    def commit(*args, **kwargs):
        refund = kwargs.get("session_id") == "serial-results" and args[1].tasks[-1].id == first
        if refund and not refund_ack:
            raise BrokerUnavailable("refund not acknowledged")
        result = sync(*args, **kwargs)
        if refund:
            events.append("canonical-refund-accepted")
        return result

    monkeypatch.setattr(dispatch, "call_agent_dispatch", provider)
    monkeypatch.setattr(dispatch, "apply_limen_file_sync", commit)
    monkeypatch.setattr(dispatch, "_down_lanes", lambda: set())
    monkeypatch.setattr(dispatch, "run_always_working_before_dispatch", lambda *a, **kw: True)
    dispatch.dispatch_tasks(board, path, agent="codex", budget=1, limit=2, dry_run=False)
    assert launched == (["NEXT"] if refund_ack else [])
    assert actuals[0]["metrics"] == {"runs": 0}
    assert events == (["canonical-refund-accepted", "provider-start"] if refund_ack else [])
    accepted = dispatch.load_limen_file(path)
    assert accepted.portal.budget.track.spent == 1
    if not refund_ack:
        assert next(row for row in accepted.tasks if row.id == first).status == "dispatched"
        [pending] = list((tabularius.tickets_root(path) / "inbox").glob("*.json"))
        assert tabularius.Ticket.model_validate_json(pending.read_bytes()).log["execution_started"] is False


@pytest.mark.parametrize("outcome", [False, dispatch._TIMEOUT, dispatch._blocked_result("provider attempted")])
def test_result_after_local_run_attempt_keeps_debit_classification(tmp_path, monkeypatch, outcome):
    task = _open_board(tmp_path / "tasks.yaml").tasks[0]
    actuals = _journal(monkeypatch)
    monkeypatch.setattr(dispatch, "_agent_argv", lambda *a: ["exec"])
    monkeypatch.setattr(dispatch, "_worktree_isolation_enabled", lambda: True)
    monkeypatch.setattr(dispatch, "_isolated_local_run", lambda *a: outcome)
    monkeypatch.setattr(
        dispatch, "call_agent_dispatch", lambda *a, **kw: dispatch._call_local_agent("codex", task, False)
    )
    assert dispatch._journaled_agent_dispatch("codex", task, False, "a" * 64) == outcome
    assert actuals[0]["metrics"] == {"runs": 1}


@pytest.mark.parametrize("case", ["host", "workstream"])
def test_retry_preparation_refusal_preserves_prior_provider_attempt(tmp_path, monkeypatch, capsys, case):
    task = _open_board(tmp_path / "tasks.yaml").tasks[0]
    actuals = _journal(monkeypatch)
    monkeypatch.setattr(dispatch, "_lane_run_env", lambda *a: {})
    monkeypatch.setattr(dispatch, "_assert_final_workstream_launch", lambda *a: None)
    monkeypatch.setattr(dispatch, "_stable_agent_host_command", lambda command, *a: command)
    name, error = (
        ("_stable_agent_host_command", dispatch.StableAgentHostError)
        if case == "host"
        else ("_assert_final_workstream_launch", dispatch.WorkstreamLaunchContractError)
    )
    monkeypatch.setattr(dispatch, name, lambda *a, **kw: (_ for _ in ()).throw(error("private-error-token")))
    monkeypatch.setattr(dispatch, "_run_capture", lambda *a, **kw: pytest.fail("retry must not start"))
    monkeypatch.setattr(
        dispatch,
        "call_agent_dispatch",
        lambda *a, **kw: dispatch._run_isolated_agent(
            "opencode", task, tmp_path, ["synthetic-provider"], 1, retry_count=1
        ),
    )
    result = dispatch._journaled_agent_dispatch("opencode", task, False, "a" * 64)
    assert not dispatch._is_prelaunch_result(result)
    assert actuals[0]["metrics"] == {"runs": 1}
    assert "private-error-token" not in str(result) + capsys.readouterr().out


@pytest.mark.parametrize("raises", [True, False])
def test_clone_failure_is_redacted_before_prelaunch_result(tmp_path, monkeypatch, capsys, raises):
    task = _open_board(tmp_path / "tasks.yaml").tasks[0]
    task.repo = "test-owner/test-repo"
    monkeypatch.setattr(dispatch, "_clone_cache_root", lambda: tmp_path)
    monkeypatch.setattr(
        dispatch,
        "_run_capture",
        lambda *a, **kw: (
            (_ for _ in ()).throw(OSError("private-error-token"))
            if raises
            else SimpleNamespace(returncode=1, stdout="", stderr="private-error-token")
        ),
    )
    assert dispatch._clone_repo(task) is None
    assert "private-error-token" not in capsys.readouterr().out


@pytest.mark.parametrize("guard", ["host", "workstream"])
def test_auth_retry_guard_refusal_keeps_first_provider_attempt(tmp_path, monkeypatch, capsys, guard):
    task = _open_board(tmp_path / "tasks.yaml").tasks[0]
    actuals = _journal(monkeypatch)
    calls = []
    monkeypatch.setattr(dispatch, "_lane_run_env", lambda *a: {})
    monkeypatch.setattr(dispatch, "_assert_final_workstream_launch", lambda *a: None)
    monkeypatch.setattr(dispatch, "_stable_agent_host_command", lambda command, *a: command)
    name, error = (
        ("_stable_agent_host_command", dispatch.StableAgentHostError)
        if guard == "host"
        else ("_assert_final_workstream_launch", dispatch.WorkstreamLaunchContractError)
    )

    def guarded(*args):
        if calls:
            raise error("private-error-token")
        return args[0] if guard == "host" else None

    def attempted(*args, **kwargs):
        calls.append("provider")
        return SimpleNamespace(returncode=1, stdout="", stderr="not logged in")

    monkeypatch.setattr(dispatch, name, guarded)
    monkeypatch.setattr(dispatch, "_run_capture", attempted)
    monkeypatch.setattr(
        dispatch,
        "call_agent_dispatch",
        lambda *a, **kw: dispatch._run_isolated_agent("claude", task, tmp_path, ["synthetic-provider"], 1),
    )
    result = dispatch._journaled_agent_dispatch("claude", task, False, "a" * 64)
    assert calls == ["provider"]
    assert not dispatch._is_prelaunch_result(result)
    assert actuals[0]["metrics"] == {"runs": 1}
    assert "private-error-token" not in str(result) + capsys.readouterr().out
    assert dispatch._is_workstream_successor_result(result) == (guard == "workstream")


def test_exception_after_run_boundary_does_not_become_no_launch(tmp_path, monkeypatch, capsys):
    task = _open_board(tmp_path / "tasks.yaml").tasks[0]
    actuals = _journal(monkeypatch)
    monkeypatch.setattr(dispatch, "_lane_run_env", lambda *a: {})
    monkeypatch.setattr(dispatch, "_assert_final_workstream_launch", lambda *a: None)
    monkeypatch.setattr(dispatch, "_stable_agent_host_command", lambda command, *a: command)
    monkeypatch.setattr(
        dispatch,
        "_run_capture",
        lambda *a, **kw: (_ for _ in ()).throw(dispatch.StableAgentHostError("private-error-token")),
    )
    monkeypatch.setattr(
        dispatch,
        "call_agent_dispatch",
        lambda *a, **kw: dispatch._run_isolated_agent("codex", task, tmp_path, ["synthetic-provider"], 1),
    )
    result = dispatch._journaled_agent_dispatch("codex", task, False, "a" * 64)
    assert not dispatch._is_prelaunch_result(result)
    assert actuals[0]["metrics"] == {"runs": 1}
    assert "private-error-token" not in str(result) + capsys.readouterr().out


def test_repository_unavailable_diagnostic_does_not_copy_remote_stderr(monkeypatch):
    monkeypatch.setattr(
        dispatch,
        "_run_capture",
        lambda *a, **kw: SimpleNamespace(returncode=1, stdout="", stderr="repository not found private-error-token"),
    )
    assert dispatch._repo_unavailable_reason("test-owner/test-repo") == "repo unavailable: test-owner/test-repo"
