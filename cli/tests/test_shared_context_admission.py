"""Adversarial tests for the bounded shared-context capability."""

import json
import os
import subprocess
import time
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
from click.testing import CliRunner
from limen import shared_context_admission as context
from limen.action_admission import classify_bash
from limen.action_admission_runtime import admit_pre_tool_action

REAL_VALIDATE_SOURCE = context.validate_source
REAL_COMMAND = context.command
REAL_GIT = context.git


class Controller:
    def __init__(self):
        self.calls = []
        self.released = []
        self.allowed = True

    def acquire(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"allowed": self.allowed, "lease": {"lease_id": "fixture-lease"}}

    def release(self, **kwargs):
        self.released.append(kwargs)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    home = tmp_path / "home"
    executable = home / ".local/bin/domus-shared-context"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"producer")
    executable.chmod(0o755)
    installed_auth = home / ".local/share/domus/host_mutation.py"
    installed_auth.parent.mkdir(parents=True)
    installed_auth.write_bytes(b"authorization")
    installed_auth.chmod(0o644)
    source = tmp_path / "source"
    source.mkdir()
    monkeypatch.setattr(context, "account_home", lambda: home)
    monkeypatch.setattr(context, "PRODUCER_SHA", context.digest(b"producer"))
    monkeypatch.setattr(context, "AUTH_SHA", context.digest(b"authorization"))
    monkeypatch.setattr(context, "validate_source", lambda path: None)
    monkeypatch.setattr(context, "git", lambda *args: "a" * 40)
    monkeypatch.setattr(
        context, "worktree_scope", lambda path: SimpleNamespace(linked=True, lease_kind="execution:fixture")
    )
    plan = {
        "schema": "domus.shared_context_plan.v1",
        "source": str(source),
        "revision": "a" * 40,
        "home": str(home),
        "attempt_id": "fixture-attempt-1",
        "packet": "fixture",
        "targets": [{"path": str(home / ".config/context"), "before": {"sha256": "old"}, "sha256": "new"}],
        "mirror": {"path": str(home / "AGENTS.md"), "before": None, "sha256": "new"},
    }

    def state(path, _home):
        before = (
            {"sha256": context.digest(path.read_bytes()), "mode": path.stat().st_mode & 0o777}
            if path.exists()
            else None
        )
        return {"path": str(path), "resolved": str(path), "parent_links": [], "before": before}

    p = SimpleNamespace(
        build_plan=lambda *_: deepcopy(plan), request=lambda value: {"plan": value}, destination_state=state
    )
    monkeypatch.setattr(context, "producer", lambda path: p)
    validations = []

    def authorize(receipt, signature, signers, expected):
        validations.append((receipt, signature, signers, expected))
        if signature.name != "valid.sig":
            raise context.ContextAdmissionError("signature rejected")
        return {"receipt_sha256": "a" * 64}

    auth = SimpleNamespace(validate_authorization=authorize, _assert_authorization_inputs_unchanged=lambda *_: None)
    monkeypatch.setattr(context, "authorizer", lambda path: auth)
    controller = Controller()
    monkeypatch.setattr(context, "AdmissionController", lambda: controller)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan))
    return SimpleNamespace(
        home=home,
        executable=executable,
        installed_auth=installed_auth,
        source=source,
        plan=plan,
        path=path,
        producer=p,
        auth=auth,
        validations=validations,
        controller=controller,
    )


def invoke(f, arguments, *, owner="fixture-owner"):
    context.admit_command(
        f"{f.executable} {arguments}",
        controller=f.controller,
        owner=owner,
        pid=os.getpid(),
        surface="fixture",
        ttl_seconds=60,
    )


def test_plan_is_zero_write_and_acquires_no_lease(fixture):
    f = fixture
    before = sorted(str(p) for p in f.home.rglob("*"))
    invoke(f, f"plan --source {f.source} --attempt-id fixture-attempt-1")
    assert sorted(str(p) for p in f.home.rglob("*")) == before
    assert not f.controller.calls


@pytest.mark.parametrize(
    "arguments",
    [
        "apply",
        "plan --source x",
        "verify --plan x --destination y",
        "apply --plan x --authorization y --signature z --force yes",
        "verify --plan x --plan y",
        "plan --source x --attempt-id --force",
        "verify --plan",
    ],
)
def test_rejects_expanded_or_malformed_arguments(fixture, arguments):
    with pytest.raises(context.ContextAdmissionError):
        invoke(fixture, arguments)
    assert not fixture.controller.calls


@pytest.mark.parametrize(
    "change", ["bytes", "write-permission", "execute-permission", "alias", "module-bytes", "module-alias"]
)
def test_installed_identity_is_not_a_basename_allowlist(fixture, change):
    f = fixture
    if change == "bytes":
        f.executable.write_bytes(b"lookalike")
    elif change == "write-permission":
        f.executable.chmod(0o777)
    elif change == "execute-permission":
        f.executable.chmod(0o644)
    elif change == "alias":
        original = f.home / "other"
        original.write_bytes(f.executable.read_bytes())
        f.executable.unlink()
        f.executable.symlink_to(original)
    elif change == "module-bytes":
        f.installed_auth.write_bytes(b"modified")
    else:
        original = f.home / "other-auth"
        original.write_bytes(f.installed_auth.read_bytes())
        f.installed_auth.unlink()
        f.installed_auth.symlink_to(original)
    with pytest.raises((OSError, context.ContextAdmissionError)):
        invoke(f, f"plan --source {f.source} --attempt-id fixture-attempt-1")


def test_apply_requires_exact_signature_then_scoped_writer(fixture):
    f = fixture
    invoke(f, f"apply --plan {f.path} --authorization receipt.json --signature valid.sig")
    assert f.validations[0][3] == {"plan": f.plan}
    assert len(f.controller.calls) == 1
    assert f.controller.calls[0][0] == ("execution:fixture",)


@pytest.mark.parametrize("reason", ["forged", "expired", "wrong-plan", "wrong-signers"])
def test_authorization_failure_never_acquires_writer(fixture, reason, monkeypatch):
    def refuse(*_):
        raise context.ContextAdmissionError(reason)

    monkeypatch.setattr(fixture.auth, "validate_authorization", refuse)
    with pytest.raises(context.ContextAdmissionError):
        invoke(fixture, f"apply --plan {fixture.path} --authorization receipt.json --signature valid.sig")
    assert not fixture.controller.calls


@pytest.mark.parametrize("change", ["extra-target", "before-image", "source-hash", "mirror"])
def test_changed_plan_is_rejected_before_signature_or_writer(fixture, change):
    f = fixture
    altered = deepcopy(f.plan)
    if change == "extra-target":
        altered["targets"].append({"path": str(f.home / "unrelated"), "sha256": "new", "before": None})
    elif change == "before-image":
        altered["targets"][0]["before"] = None
    elif change == "source-hash":
        altered["targets"][0]["sha256"] = "different"
    else:
        altered["mirror"]["path"] = str(f.home / "unrelated")
    f.path.write_text(json.dumps(altered))
    with pytest.raises(context.ContextAdmissionError):
        invoke(f, f"apply --plan {f.path} --authorization receipt.json --signature valid.sig")
    assert not f.validations and not f.controller.calls


def test_verify_accepts_new_before_images_but_no_destination_expansion(fixture):
    f = fixture
    f.plan["targets"][0]["before"] = {"sha256": "new"}
    invoke(f, f"verify --plan {f.path}")
    assert not f.controller.calls
    f.plan["targets"][0]["path"] = str(f.home / "different")
    with pytest.raises(context.ContextAdmissionError):
        invoke(f, f"verify --plan {f.path}")


def test_source_validation_failure_is_closed(fixture, monkeypatch):
    def reject(_):
        raise context.ContextAdmissionError("unapproved source")

    monkeypatch.setattr(context, "validate_source", reject)
    with pytest.raises(context.ContextAdmissionError):
        invoke(fixture, f"plan --source {fixture.source} --attempt-id fixture-attempt-1")


def test_apply_preserves_foreign_writer(fixture):
    fixture.controller.allowed = False
    with pytest.raises(context.ContextAdmissionError):
        invoke(fixture, f"apply --plan {fixture.path} --authorization receipt.json --signature valid.sig")
    assert not fixture.controller.released


def test_bootstrap_plan_has_only_two_fixed_targets_and_no_writes(fixture):
    f = fixture
    before = sorted(str(p) for p in f.home.rglob("*"))
    plan = context.bootstrap_plan(f.source, "bootstrap-fixture")
    assert {t["path"] for t in plan["targets"]} == {str(f.executable), str(f.installed_auth)}
    assert sorted(str(p) for p in f.home.rglob("*")) == before
    assert context.request(plan)["plan_sha256"] == context.digest(context.canonical(plan))


@pytest.fixture
def bootstrap_fixture(fixture, monkeypatch):
    import limen.dispatch
    import limen.inventory_admission

    monkeypatch.setattr(limen.dispatch, "_load_limen_env", lambda: None)
    monkeypatch.setattr(
        limen.inventory_admission,
        "require_approved_priority",
        lambda _: {"outcome_id": "shared-context-integration-20261016"},
    )
    return fixture


def test_bootstrap_preserves_before_images_and_reads_back(bootstrap_fixture, monkeypatch):
    f = bootstrap_fixture
    plan = context.bootstrap_plan(f.source, "bootstrap-fixture")
    monkeypatch.setattr(context, "command", lambda *_args, **_kwargs: b"")
    result = context.bootstrap(plan, Path("receipt.json"), Path("valid.sig"), "approved-key")
    journal_path = Path(result["receipt"])
    journal = json.loads(journal_path.read_text())
    assert journal["status"] == "verified"
    assert len(journal["before_images"]) == 2
    assert journal["before_images"][0]["content_base64"]
    assert journal_path.stat().st_mode & 0o777 == 0o600
    assert f.controller.released


def test_bootstrap_ambiguous_attempt_never_overwrites_history(bootstrap_fixture, monkeypatch):
    f = bootstrap_fixture
    plan = context.bootstrap_plan(f.source, "bootstrap-fixture")
    root = f.home / ".local/state/domus/shared-context-bootstrap"
    attempt = root / "bootstrap-fixture"
    attempt.mkdir(parents=True, mode=0o700)
    root.chmod(0o700)
    original = attempt / "receipt.json"
    original.write_bytes(b"original interrupted evidence")
    with pytest.raises(FileExistsError):
        context.bootstrap(plan, Path("receipt.json"), Path("valid.sig"), "approved-key")
    assert original.read_bytes() == b"original interrupted evidence"
    assert f.controller.released


def test_bootstrap_failure_keeps_partial_evidence_and_originals(bootstrap_fixture, monkeypatch):
    f = bootstrap_fixture
    plan = context.bootstrap_plan(f.source, "bootstrap-fixture")
    unrelated = f.home / "unrelated"
    unrelated.write_bytes(b"keep")

    def fail(*_args, **_kwargs):
        raise context.ContextAdmissionError("apply failed")

    monkeypatch.setattr(context, "command", fail)
    with pytest.raises(context.ContextAdmissionError):
        context.bootstrap(plan, Path("receipt.json"), Path("valid.sig"), "approved-key")
    receipt = f.home / ".local/state/domus/shared-context-bootstrap/bootstrap-fixture/receipt.json"
    assert json.loads(receipt.read_text())["status"] == "failed"
    assert unrelated.read_bytes() == b"keep"
    assert f.executable.read_bytes() == b"producer"
    assert f.controller.released


def test_cli_capabilities_reject_overrides():
    runner = CliRunner()
    assert runner.invoke(context.shared_context_group, ["capabilities"]).exit_code == 0
    assert runner.invoke(context.shared_context_group, ["capabilities", "--source", "/tmp"]).exit_code == 3


@pytest.mark.parametrize("name", ["domus-shared-context", "executable_domus-shared-context"])
def test_classifier_routes_reserved_names_to_exact_validator(name):
    assert classify_bash(f"/tmp/{name} apply --plan x --authorization y --signature z").category == "shared_context"
    assert classify_bash(f"python3 /tmp/{name} apply --plan x").category == "shared_context"


def test_runtime_denies_unexpected_validator_error(monkeypatch):
    def crash(*_args, **_kwargs):
        raise RuntimeError("unexpected source failure")

    monkeypatch.setattr(context, "admit_command", crash)
    result = admit_pre_tool_action(
        {"tool_name": "Bash", "tool_input": {"command": "domus-shared-context plan --source x --attempt-id example"}},
        controller=Controller(),
        owner="fixture",
        pid=os.getpid(),
        surface="fixture",
        ttl_seconds=60,
    )
    assert not result.allowed
    assert "RuntimeError" in result.reason


@pytest.fixture
def source_owner(fixture, monkeypatch):
    f = fixture
    for name, raw in ((context.PRODUCER_SOURCE, b"producer"), (context.AUTH_SOURCE, b"authorization")):
        path = f.source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)

    def git_run(*args):
        return (
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(f.source),
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "-c",
                    "commit.gpgSign=false",
                    *args,
                ],
                check=True,
                capture_output=True,
                timeout=10,
            )
            .stdout.decode()
            .strip()
        )

    git_run("init")
    git_run("add", ".")
    git_run("commit", "-m", "approved fixture")
    monkeypatch.setattr(context, "APPROVED_SOURCE", git_run("rev-parse", "HEAD"))
    monkeypatch.setattr(context, "git", REAL_GIT)

    def owner_command(args, **kwargs):
        if args == ["chezmoi", "source-path"]:
            return str(f.source).encode()
        return REAL_COMMAND(args, **kwargs)

    monkeypatch.setattr(context, "command", owner_command)
    f.git_run = git_run
    return f


def test_real_source_guard_accepts_only_approved_inputs(source_owner):
    REAL_VALIDATE_SOURCE(source_owner.source)


def test_real_source_guard_allows_receipt_only_successor(source_owner):
    f = source_owner
    (f.source / "docs").mkdir()
    (f.source / "docs/receipt.json").write_text("{}\n")
    f.git_run("add", ".")
    f.git_run("commit", "-m", "receipt")
    REAL_VALIDATE_SOURCE(f.source)


def test_real_source_guard_rejects_committed_template_change(source_owner):
    f = source_owner
    (f.source / "dot_config").mkdir()
    (f.source / "dot_config/AGENTS.md.tmpl").write_text("changed template\n")
    f.git_run("add", ".")
    f.git_run("commit", "-m", "unapproved template")
    with pytest.raises(context.ContextAdmissionError, match="approved deployment inputs"):
        REAL_VALIDATE_SOURCE(f.source)


def test_real_source_guard_rejects_dirty_and_untracked_inputs(source_owner):
    f = source_owner
    (f.source / "untracked").write_text("unexpected\n")
    with pytest.raises(context.ContextAdmissionError, match="committed and clean"):
        REAL_VALIDATE_SOURCE(f.source)


def test_real_source_guard_rejects_other_git_store(source_owner, tmp_path):
    foreign = tmp_path / "foreign"
    foreign.mkdir()
    subprocess.run(["git", "init", str(foreign)], check=True, capture_output=True, timeout=10)
    with pytest.raises(context.ContextAdmissionError, match="configured owner Git store"):
        REAL_VALIDATE_SOURCE(foreign)


def test_real_source_guard_rejects_unsafe_source_permissions(source_owner):
    (source_owner.source / context.AUTH_SOURCE).chmod(0o666)
    with pytest.raises(context.ContextAdmissionError, match="secure regular file"):
        REAL_VALIDATE_SOURCE(source_owner.source)


def test_pinned_module_loader_rejects_changed_bytes(tmp_path):
    path = tmp_path / "module.py"
    path.write_bytes(b"VALUE = 7\n")
    expected = context.digest(path.read_bytes())
    assert context.load_module(path, expected, "fixture").VALUE == 7
    path.write_bytes(b"VALUE = 9\n")
    with pytest.raises(context.ContextAdmissionError, match="identity differs"):
        context.load_module(path, expected, "fixture")


def test_bootstrap_deadline_covers_admission_before_any_write(bootstrap_fixture, monkeypatch):
    import limen.inventory_admission

    f = bootstrap_fixture
    plan = context.bootstrap_plan(f.source, "deadline-fixture")
    monkeypatch.setattr(context, "MAX_SECONDS", 0.01)
    monkeypatch.setattr(limen.inventory_admission, "require_approved_priority", lambda _: time.sleep(0.1))
    with pytest.raises(context.ContextAdmissionError, match="deadline"):
        context.bootstrap(plan, Path("receipt.json"), Path("valid.sig"), "approved-key")
    assert not f.controller.calls
    assert not (f.home / ".local/state").exists()


def test_bootstrap_lock_alias_never_changes_target(bootstrap_fixture):
    f = bootstrap_fixture
    plan = context.bootstrap_plan(f.source, "alias-fixture")
    root = f.home / ".local/state/domus/shared-context-bootstrap"
    root.mkdir(parents=True, mode=0o700)
    victim = f.home / "unrelated"
    victim.write_bytes(b"original")
    victim.chmod(0o644)
    (root / "writer.lock").symlink_to(victim)
    with pytest.raises(OSError):
        context.bootstrap(plan, Path("receipt.json"), Path("valid.sig"), "approved-key")
    assert victim.read_bytes() == b"original"
    assert victim.stat().st_mode & 0o777 == 0o644
    assert f.controller.released


def test_bootstrap_expired_after_apply_remains_failed(bootstrap_fixture, monkeypatch):
    f = bootstrap_fixture
    plan = context.bootstrap_plan(f.source, "expired-fixture")
    calls = []

    def recheck(*_args):
        calls.append(True)
        if len(calls) > 1:
            raise context.ContextAdmissionError("expired")

    monkeypatch.setattr(f.auth, "_assert_authorization_inputs_unchanged", recheck)
    monkeypatch.setattr(context, "command", lambda *_args, **_kwargs: b"")
    with pytest.raises(context.ContextAdmissionError, match="expired"):
        context.bootstrap(plan, Path("receipt.json"), Path("valid.sig"), "approved-key")
    path = f.home / ".local/state/domus/shared-context-bootstrap/expired-fixture/receipt.json"
    assert json.loads(path.read_text())["status"] == "failed"
    assert f.controller.released
