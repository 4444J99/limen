"""Tests for scripts/_required_checks.py — the ONE required-check failure policy.

Covers the issue #2764 acceptance matrix: required-fail, optional-fail,
no-required-checks (proven absent), and policy-read-error (unmeasured, fail-closed).
gh is fully mocked; no network.
"""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "_required_checks.py"


def _load():
    spec = importlib.util.spec_from_file_location("required_checks_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _R(stdout="", returncode=0, stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


def _gh_for(checks_result, branch_meta=None, rules=None):
    """Fake gh answering `pr checks --required` and the branch-policy probes."""

    def fake_gh(args, timeout=60):
        if args[:2] == ["pr", "checks"]:
            return checks_result
        if args[0] == "api" and "/rules/branches/" in args[1]:
            return _R(json.dumps([] if rules is None else rules))
        if args[0] == "api" and "/branches/" in args[1]:
            return _R(json.dumps({"name": "main", "protected": False} if branch_meta is None else branch_meta))
        raise AssertionError(f"unexpected gh call: {args!r}")

    return fake_gh


def test_required_fail_names_returned():
    mod = _load()
    gh = _gh_for(
        _R(
            json.dumps(
                [
                    {"name": "pr-gate", "bucket": "fail", "state": "FAILURE"},
                    {"name": "advisory", "bucket": "pass", "state": "SUCCESS"},
                ]
            )
        )
    )
    assert mod.failing_required_checks(gh, "organvm/repo", 7, "main") == ("pr-gate",)


def test_nonzero_exit_with_valid_payload_is_authoritative():
    # `gh pr checks` returns non-zero when a required check is red; the JSON
    # payload remains authoritative and must still drive classification.
    mod = _load()
    gh = _gh_for(
        _R(
            json.dumps([{"name": "pr-gate", "bucket": "fail", "state": "FAILURE"}]),
            returncode=1,
        )
    )
    assert mod.failing_required_checks(gh, "organvm/repo", 7, "main") == ("pr-gate",)


def test_optional_only_failure_returns_empty_tuple():
    # An optional diagnostic failing in the rollup never appears in
    # `gh pr checks --required` output, so the required rail reads green.
    mod = _load()
    gh = _gh_for(_R(json.dumps([{"name": "pr-gate", "bucket": "pass", "state": "SUCCESS"}])))
    assert mod.failing_required_checks(gh, "organvm/repo", 7, "main") == ()


def test_no_required_checks_proven_absent_returns_empty_tuple():
    mod = _load()
    gh = _gh_for(
        _R("", returncode=1, stderr="no required checks reported on the main branch"),
        branch_meta={"name": "main", "protected": False},
        rules=[],
    )
    assert mod.failing_required_checks(gh, "organvm/repo", 7, "main") == ()


def test_no_required_checks_proven_absent_via_empty_protection():
    mod = _load()
    gh = _gh_for(
        _R("", returncode=1, stderr="no required checks reported on the main branch"),
        branch_meta={
            "name": "main",
            "protected": True,
            "protection": {"required_status_checks": {"contexts": [], "checks": []}},
        },
        rules=[{"type": "pull_request"}],
    )
    assert mod.failing_required_checks(gh, "organvm/repo", 7, "main") == ()


def test_no_required_checks_unproven_when_branch_has_required_checks():
    mod = _load()
    gh = _gh_for(
        _R("", returncode=1, stderr="no required checks reported on the main branch"),
        branch_meta={
            "name": "main",
            "protected": True,
            "protection": {"required_status_checks": {"contexts": ["pr-gate"], "checks": []}},
        },
        rules=[{"type": "pull_request"}],
    )
    # The absence claim is contradicted by branch protection → unmeasured, not green.
    assert mod.failing_required_checks(gh, "organvm/repo", 7, "main") is None


def test_no_required_checks_unproven_on_unknown_rule_type():
    mod = _load()
    gh = _gh_for(
        _R("", returncode=1, stderr="no required checks reported on the main branch"),
        branch_meta={"name": "main", "protected": False},
        rules=[{"type": "mysterious_future_rule"}],
    )
    assert mod.failing_required_checks(gh, "organvm/repo", 7, "main") is None


def test_no_required_checks_unproven_on_branch_api_error():
    mod = _load()
    gh = _gh_for(
        _R("", returncode=1, stderr="no required checks reported on the main branch"),
        branch_meta={"name": "main", "protected": False},
        rules=None,
    )

    def failing_rules(args, timeout=60):
        if args[0] == "api" and "/rules/branches/" in args[1]:
            return _R("", returncode=1, stderr="forbidden")
        return gh(args, timeout=timeout)

    assert mod.failing_required_checks(failing_rules, "organvm/repo", 7, "main") is None


def test_unmeasured_on_malformed_payload():
    mod = _load()
    for bad in (
        _R("not-json", returncode=1, stderr="boom"),
        _R(json.dumps({"unexpected": True})),
        _R(json.dumps([None])),
        _R(json.dumps([{"name": "pr-gate"}])),  # no bucket/state
        _R(json.dumps([{"bucket": "fail", "state": "FAILURE"}])),  # no name
        _R(json.dumps([{"name": "pr-gate", "bucket": "weird", "state": "WEIRD"}])),
    ):
        gh = _gh_for(bad)
        assert mod.failing_required_checks(gh, "organvm/repo", 7, "main") is None


def test_pending_required_checks():
    mod = _load()
    gh = _gh_for(
        _R(
            json.dumps(
                [
                    {"name": "pr-gate", "bucket": "pending", "state": "PENDING"},
                    {"name": "advisory", "bucket": "pass", "state": "SUCCESS"},
                ]
            )
        )
    )
    assert mod.pending_required_checks(gh, "organvm/repo", 7, "main") == ("pr-gate",)


def test_classify_required_failure():
    mod = _load()
    assert mod.classify_required_failure(None) == "REQUIRED-CHECKS-UNMEASURED"
    assert mod.classify_required_failure(("pr-gate",)) == "CI-RED"
    assert mod.classify_required_failure(()) == "OPTIONAL-ONLY"
    # The verdict constants are the literal strings the organs compare against.
    assert (mod.CI_RED, mod.UNMEASURED, mod.OPTIONAL_ONLY) == (
        "CI-RED",
        "REQUIRED-CHECKS-UNMEASURED",
        "OPTIONAL-ONLY",
    )


def test_rollup_constants_match_the_organ_literals():
    mod = _load()
    assert mod.ROLLUP_FAIL_STATES == {
        "FAILURE",
        "ERROR",
        "CANCELLED",
        "TIMED_OUT",
        "ACTION_REQUIRED",
    }
    assert mod.ROLLUP_PENDING_STATES == {
        "PENDING",
        "IN_PROGRESS",
        "QUEUED",
        "EXPECTED",
        "",
    }


# ── required_contexts(): the REST twin of `gh pr checks --required` ─────────────────────────────
# `gh pr checks --required` is GraphQL, which Claude Code cloud sessions cannot reach. required_contexts
# names the required contexts from branch protection AND rulesets; None means UNMEASURED and the caller
# must keep its conservative all-checks policy.


def _policy_gh(branch_meta, rules, *, meta_rc=0, rules_rc=0):
    def fake_gh(args, timeout=60):
        if args[0] == "api" and "/rules/branches/" in args[1]:
            return _R(json.dumps(rules), returncode=rules_rc)
        if args[0] == "api" and "/branches/" in args[1]:
            return _R(json.dumps(branch_meta), returncode=meta_rc)
        raise AssertionError(f"unexpected gh call: {args!r}")

    return fake_gh


def _protected(contexts=(), checks=()):
    return {
        "name": "main",
        "protected": True,
        "protection": {
            "enabled": True,
            "required_status_checks": {
                "contexts": list(contexts),
                "checks": list(checks),
                "enforcement_level": "everyone",
            },
        },
    }


def test_required_contexts_is_empty_when_nothing_is_required():
    m = _load()
    assert m.required_contexts(_policy_gh({"name": "main", "protected": False}, []), "o/r", "main") == ()
    assert m.required_contexts(_policy_gh(_protected(), []), "o/r", "main") == ()


def test_required_contexts_unions_classic_contexts_checks_and_rulesets():
    m = _load()
    meta = _protected(contexts=["pr-gate"], checks=[{"context": "python", "app_id": 15368}])
    rules = [
        {"type": "pull_request"},
        {
            "type": "required_status_checks",
            "parameters": {"required_status_checks": [{"context": "web", "integration_id": 1}, {"context": "pr-gate"}]},
        },
    ]
    assert m.required_contexts(_policy_gh(meta, rules), "o/r", "main") == ("pr-gate", "python", "web")


def test_required_contexts_ruleset_only_with_unprotected_branch():
    m = _load()
    rules = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": "ci"}]}}]
    assert m.required_contexts(_policy_gh({"name": "main", "protected": False}, rules), "o/r", "main") == ("ci",)


def test_required_contexts_merge_queue_rule_does_not_make_policy_unmeasured():
    m = _load()
    assert m.required_contexts(_policy_gh(_protected(contexts=["ci"]), [{"type": "merge_queue"}]), "o/r", "main") == (
        "ci",
    )


def test_required_contexts_unknown_rule_type_is_unmeasured():
    # A `workflows` rule can require checks this module cannot enumerate: never infer "nothing else required".
    m = _load()
    assert m.required_contexts(_policy_gh(_protected(contexts=["ci"]), [{"type": "workflows"}]), "o/r", "main") is None


def test_required_contexts_malformed_or_unreadable_policy_is_unmeasured():
    m = _load()
    ok_meta = _protected(contexts=["ci"])
    assert m.required_contexts(_policy_gh(ok_meta, [], meta_rc=1), "o/r", "main") is None
    assert m.required_contexts(_policy_gh(ok_meta, [], rules_rc=1), "o/r", "main") is None
    assert m.required_contexts(_policy_gh(ok_meta, {"not": "a list"}), "o/r", "main") is None
    # required_status_checks rule with no parameters
    assert m.required_contexts(_policy_gh(ok_meta, [{"type": "required_status_checks"}]), "o/r", "main") is None
    # protected branch with no protection object
    assert m.required_contexts(_policy_gh({"name": "main", "protected": True}, []), "o/r", "main") is None
    # wrong branch echoed back
    assert m.required_contexts(_policy_gh({"name": "other", "protected": False}, []), "o/r", "main") is None
    # non-string context
    assert m.required_contexts(_policy_gh(_protected(contexts=[7]), []), "o/r", "main") is None
    assert m.required_contexts(_policy_gh(ok_meta, []), "o/r", "") is None


def test_required_contexts_cli_prints_json_and_keeps_prove_no_required_mode(tmp_path):
    """Both CLI modes parse, and the unmeasured path exits 2 (the shell adapter's fail-toward-caution signal)."""
    import os
    import subprocess
    import sys

    stub = tmp_path / "gh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        'case "$*" in\n'
        '  *"rules/branches/main"*) echo \'[{"type":"required_status_checks","parameters":'
        '{"required_status_checks":[{"context":"pr-gate"}]}}]\' ;;\n'
        '  *"branches/main"*) echo \'{"name":"main","protected":false}\' ;;\n'
        "  *) exit 1 ;;\n"
        "esac\n"
    )
    stub.chmod(0o755)
    env = {**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"}

    got = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--contexts", "o/r", "--branch", "main"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert (got.returncode, json.loads(got.stdout)) == (0, ["pr-gate"])

    # a required context exists, so absence cannot be proven: exit 2 / UNMEASURED
    got = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--prove-no-required", "o/r", "--branch", "main"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert (got.returncode, got.stdout.strip()) == (2, "REQUIRED-CHECKS-UNMEASURED")

    broken = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--contexts", "o/r", "--branch", "nope"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert (broken.returncode, broken.stdout.strip()) == (2, "REQUIRED-CHECKS-UNMEASURED")
