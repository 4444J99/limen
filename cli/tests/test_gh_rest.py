"""Tests for scripts/_gh_rest.py — the REST read path used when GitHub GraphQL is unavailable.

Claude Code cloud sessions answer every GraphQL call with HTTP 403, so `gh pr view` / `gh issue view`
cannot read anything there (gap G4). The module must derive the SAME facts over REST, in the SAME shape
`gh pr view --json ...` reports, and must fail toward caution (raise ReadError) on anything it cannot
read in full. gh is fully faked; no network.
"""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "_gh_rest.py"
SHA = "a" * 40


def _load():
    spec = importlib.util.spec_from_file_location("gh_rest_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ok(*pages):
    """gh api --paginate prints one JSON document per page, back to back."""
    return SimpleNamespace(returncode=0, stdout="".join(json.dumps(p) for p in pages), stderr="")


def _fail(stderr="gh: Not Found (HTTP 404)", returncode=1):
    return SimpleNamespace(returncode=returncode, stdout="", stderr=stderr)


def _pull(**over):
    pull = {
        "number": 7,
        "title": "t",
        "html_url": "https://github.com/o/r/pull/7",
        "state": "open",
        "merged": False,
        "draft": False,
        "mergeable": True,
        "mergeable_state": "clean",
        "changed_files": 2,
        "base": {"ref": "main"},
        "head": {"ref": "feature", "sha": SHA},
    }
    pull.update(over)
    return pull


def _router(routes):
    """Fake gh: the endpoint (last arg) selects the canned result; a list is consumed call by call."""
    calls = []

    def fake(args, timeout=60):
        endpoint = args[-1]
        calls.append(endpoint)
        for needle, result in routes.items():
            if endpoint.startswith(needle):
                if isinstance(result, list):
                    return result.pop(0) if len(result) > 1 else result[0]
                return result
        raise AssertionError(f"unexpected gh call: {args!r}")

    fake.calls = calls
    return fake


def _routes(pull=None, files=None, runs=None, statuses=None):
    return {
        "repos/o/r/pulls/7/files": files if files is not None else _ok([{"filename": "a.py"}], [{"filename": "b.md"}]),
        "repos/o/r/pulls/7": pull if pull is not None else _ok(_pull()),
        f"repos/o/r/commits/{SHA}/check-runs": runs if runs is not None else _ok({"check_runs": []}),
        f"repos/o/r/commits/{SHA}/status": statuses
        if statuses is not None
        else _ok({"state": "success", "statuses": []}),
    }


def test_snapshot_has_the_gh_pr_view_shape_and_normalizes_the_rollup():
    m = _load()
    runs = _ok(
        {
            "check_runs": [
                {
                    "name": "python",
                    "status": "completed",
                    "conclusion": "success",
                    "started_at": "2026-10-24T01:00:00Z",
                    "completed_at": "2026-10-24T01:05:00Z",
                }
            ]
        },
        {"check_runs": [{"name": "web", "status": "in_progress", "conclusion": None, "started_at": "t1"}]},
    )
    statuses = _ok(
        {"state": "success", "statuses": [{"context": "CodeRabbit", "state": "success", "created_at": "t2"}]}
    )
    snap = m.snapshot("o/r", 7, gh=_router(_routes(runs=runs, statuses=statuses)))

    assert snap["number"] == 7
    assert snap["url"] == "https://github.com/o/r/pull/7"
    assert snap["state"] == "OPEN"
    assert snap["isDraft"] is False
    assert snap["mergeStateStatus"] == "CLEAN"
    assert snap["baseRefName"] == "main"
    assert snap["headRefName"] == "feature"
    assert snap["headRefOid"] == SHA
    assert snap["files"] == [{"path": "a.py"}, {"path": "b.md"}]  # two pages flattened
    assert snap["statusCheckRollup"] == [
        {
            "__typename": "CheckRun",
            "name": "python",
            "status": "COMPLETED",
            "conclusion": "SUCCESS",
            "startedAt": "2026-10-24T01:00:00Z",
            "completedAt": "2026-10-24T01:05:00Z",
        },
        {
            "__typename": "CheckRun",
            "name": "web",
            "status": "IN_PROGRESS",
            "conclusion": None,
            "startedAt": "t1",
            "completedAt": None,
        },
        {"__typename": "StatusContext", "context": "CodeRabbit", "state": "SUCCESS", "createdAt": "t2"},
    ]


@pytest.mark.parametrize(
    ("rest_state", "expected"),
    [
        ("clean", "CLEAN"),
        ("dirty", "DIRTY"),
        ("behind", "BEHIND"),
        ("blocked", "BLOCKED"),
        ("unstable", "UNSTABLE"),
        ("has_hooks", "HAS_HOOKS"),
        ("draft", "DRAFT"),
        ("something-new", "UNKNOWN"),  # an unrecognized state must never read as mergeable
        (None, "UNKNOWN"),
    ],
)
def test_mergeable_state_maps_to_merge_state_status(rest_state, expected):
    m = _load()
    gh = _router(_routes(pull=_ok(_pull(mergeable_state=rest_state))))
    assert m.snapshot("o/r", 7, gh=gh)["mergeStateStatus"] == expected


def test_null_mergeable_is_unknown_even_if_state_looks_clean():
    m = _load()
    gh = _router(_routes(pull=_ok(_pull(mergeable=None, mergeable_state="clean"))))
    assert m.snapshot("o/r", 7, gh=gh, tries=1, delay=0)["mergeStateStatus"] == "UNKNOWN"


def test_null_mergeable_is_retried_until_github_has_computed_it():
    m = _load()
    sleeps = []
    pulls = [_ok(_pull(mergeable=None, mergeable_state="unknown")), _ok(_pull())]
    gh = _router(_routes(pull=pulls))
    snap = m.snapshot("o/r", 7, gh=gh, tries=3, delay=2.5, sleep=sleeps.append)
    assert snap["mergeStateStatus"] == "CLEAN"
    assert sleeps == [2.5]


def test_null_mergeable_exhausts_retries_to_unknown():
    m = _load()
    sleeps = []
    gh = _router(_routes(pull=_ok(_pull(mergeable=None, mergeable_state="unknown"))))
    snap = m.snapshot("o/r", 7, gh=gh, tries=3, delay=1, sleep=sleeps.append)
    assert snap["mergeStateStatus"] == "UNKNOWN"
    assert sleeps == [1, 1]  # tries-1 waits, never a wait after the last read


def test_closed_and_merged_prs_are_not_retried_or_called_open():
    m = _load()
    sleeps = []
    merged = _ok(_pull(state="closed", merged=True, mergeable=None, mergeable_state="unknown"))
    assert m.snapshot("o/r", 7, gh=_router(_routes(pull=merged)), sleep=sleeps.append)["state"] == "MERGED"
    closed = _ok(_pull(state="closed", merged=False, mergeable=None, mergeable_state="unknown"))
    assert m.snapshot("o/r", 7, gh=_router(_routes(pull=closed)), sleep=sleeps.append)["state"] == "CLOSED"
    assert sleeps == []


def test_draft_flag_is_carried():
    m = _load()
    gh = _router(_routes(pull=_ok(_pull(draft=True, mergeable_state="draft"))))
    snap = m.snapshot("o/r", 7, gh=gh)
    assert snap["isDraft"] is True
    assert snap["mergeStateStatus"] == "DRAFT"


def test_truncated_file_list_is_unreadable_not_empty_of_deploy_paths():
    m = _load()
    gh = _router(_routes(pull=_ok(_pull(changed_files=3000)), files=_ok([{"filename": "a.py"}])))
    with pytest.raises(m.ReadError, match="truncated"):
        m.snapshot("o/r", 7, gh=gh)


def test_a_failing_endpoint_raises_with_the_gh_diagnostic():
    m = _load()
    with pytest.raises(m.ReadError, match=r"Not Found \(HTTP 404\)"):
        m.snapshot("o/r", 7, gh=_router(_routes(pull=_fail())))
    with pytest.raises(m.ReadError, match="HTTP 502"):
        m.snapshot("o/r", 7, gh=_router(_routes(runs=_fail("gh: Bad Gateway (HTTP 502)"))))


def test_a_timeout_reads_as_timed_out_so_the_predicate_holds_not_blocks():
    m = _load()

    def hung(args, timeout=60):
        raise subprocess.TimeoutExpired(args, timeout)

    with pytest.raises(m.ReadError, match="timed out"):
        m.snapshot("o/r", 7, gh=hung)


@pytest.mark.parametrize(
    "routes",
    [
        {"pull": _ok({"number": 7})},  # no head/base
        {"pull": _ok([1, 2])},  # not an object
        {"runs": _ok({"check_runs": [{"status": "completed"}]})},  # run without a name
        {"runs": _ok({"oops": []})},  # no check_runs list
        {"statuses": _ok({"statuses": [{"state": "success"}]})},  # status without a context
        {"files": _ok({"not": "a list"})},
    ],
)
def test_malformed_payloads_raise(routes):
    m = _load()
    with pytest.raises(m.ReadError):
        m.snapshot("o/r", 7, gh=_router(_routes(**routes)), tries=1, delay=0)


def test_without_a_repo_the_endpoint_carries_gh_placeholders():
    m = _load()
    seen = []

    def fake(args, timeout=60):
        seen.append(args[-1])
        return _ok(_pull())

    assert m.head_sha(None, 7, gh=fake) == SHA
    assert seen == ["repos/{owner}/{repo}/pulls/7"]


def test_current_pr_finds_the_open_pr_for_a_branch():
    m = _load()
    seen = []

    def fake(args, timeout=60):
        seen.append(args[-1])
        return _ok([{"number": 41}])

    assert m.current_pr("o/r", "fix/some-branch", gh=fake) == 41
    assert seen == ["repos/o/r/pulls?head=o:fix/some-branch&state=open&per_page=2"]
    assert m.current_pr(None, "b", gh=fake) == 41
    assert seen[-1] == "repos/{owner}/{repo}/pulls?head={owner}:b&state=open&per_page=2"


def test_current_pr_reports_none_when_nothing_is_open_and_raises_on_failure(monkeypatch):
    m = _load()
    assert m.current_pr("o/r", "b", gh=lambda a, timeout=60: _ok([])) is None
    with pytest.raises(m.ReadError):
        m.current_pr("o/r", "b", gh=lambda a, timeout=60: _fail())
    monkeypatch.setattr(m, "current_branch", lambda: "")  # detached HEAD
    with pytest.raises(m.ReadError, match="no branch"):
        m.current_pr("o/r", None, gh=lambda a, timeout=60: _ok([]))


def test_unresolved_threads_counts_only_resolved_false():
    m = _load()
    threads = [
        {"resolved": True, "outdated": False},
        {"resolved": False, "outdated": True},  # outdated-but-unresolved still blocks, as GraphQL isResolved does
        {"resolved": False, "outdated": False},
        {"outdated": False},  # no verdict is not evidence of an unresolved thread
    ]
    assert m.unresolved_threads("o/r", 7, gh=lambda a, timeout=60: _ok(threads)) == 2
    with pytest.raises(m.ReadError):
        m.unresolved_threads("o/r", 7, gh=lambda a, timeout=60: _ok({"not": "a list"}))
    with pytest.raises(m.ReadError):
        m.unresolved_threads("o/r", 7, gh=lambda a, timeout=60: _fail("gh: Not Found (HTTP 404)"))


def test_issue_state_reports_open_or_closed_uppercase():
    m = _load()
    assert m.issue_state("o/r", 3, gh=lambda a, timeout=60: _ok({"state": "closed"})) == "CLOSED"
    assert m.issue_state("o/r", 3, gh=lambda a, timeout=60: _ok({"state": "open"})) == "OPEN"
    with pytest.raises(m.ReadError):
        m.issue_state("o/r", 3, gh=lambda a, timeout=60: _ok({"state": "weird"}))


def test_cli_prints_json_and_maps_failure_to_exit_1(monkeypatch, capsys):
    m = _load()
    monkeypatch.setattr(m, "_gh", _router(_routes()))
    assert m.main(["snapshot", "--pr", "7", "--repo", "o/r"]) == 0
    assert json.loads(capsys.readouterr().out)["headRefOid"] == SHA

    monkeypatch.setattr(m, "_gh", _router(_routes(pull=_fail("gh: HTTP 403 forbidden"))))
    assert m.main(["snapshot", "--pr", "7", "--repo", "o/r"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "HTTP 403 forbidden" in captured.err


def test_module_is_read_only_by_construction():
    """No mutating flag may be passed to gh: the effect paths get no REST twin (queue-free merge contract)."""
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ('"-X"', '"--method"', '"--input"', '"-f"', '"-F"', '"--field"', '"--raw-field"'):
        assert forbidden not in source, forbidden
