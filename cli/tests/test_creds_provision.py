"""CLAVIS (creds-provision.py) — the credential-provisioning organ.

Locks the forever-predicate (`check`) and the one-time seed (`bootstrap`):
- a REQUIRED op-sourced secret in a non-SA-readable vault is a HARD fail (exit 1) — the loud signal
  that the estate is not yet SA-homed;
- a secret already in the automation vault is green;
- a `derive`-backed lane (keyring source) is exempt from the vault check;
- `bootstrap` is dry-run by default, emits the exact op command sequence, de-dupes per item, and
  NEVER prints a secret/token value.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

PROVISION = Path(__file__).resolve().parents[2] / "scripts" / "creds-provision.py"
# Point the policy at a nonexistent file so load_policy() fails-open to its defaults
# (automation_vault = Limen-Automation) — hermetic, independent of the repo's credentials.yaml.
_NO_POLICY = {"LIMEN_CREDS_POLICY": "/tmp/does-not-exist-clavis-policy.yaml"}


def _run(cred_map_json, command="check", extra_args=None):
    env = {**os.environ, **_NO_POLICY, "LIMEN_CREDS_MAP": cred_map_json}
    return subprocess.run(
        [sys.executable, str(PROVISION), command, *(extra_args or [])],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )


def test_check_hard_fails_on_required_outlier():
    """A required secret in a non-SA-readable vault → exit 1 + a loud ✗."""
    r = _run('[{"lane":"req","ref":"op://Private/item/password","env":["X"],"enabled":true,"required":true}]')
    assert r.returncode == 1
    assert "✗" in r.stdout and "REQUIRED" in r.stdout


def test_check_green_when_secret_in_automation_vault():
    """A secret already homed in the automation vault → exit 0 + ✓."""
    r = _run('[{"lane":"ok","ref":"op://Limen-Automation/item/password","env":["X"],"enabled":true,"required":true}]')
    assert r.returncode == 0
    assert "✓" in r.stdout


def test_derive_backed_lane_is_exempt():
    """A `derive` lane (keyring source) in a non-readable vault is NOT a hard fail — op isn't needed."""
    r = _run(
        '[{"lane":"gh","ref":"op://GitHub-Tokens/t/password","derive":["gh","auth","token"],'
        '"env":["GH_TOKEN"],"enabled":true,"required":true}]'
    )
    assert r.returncode == 0
    assert "derive-exempt" in r.stdout


def test_parked_lane_ignored():
    """enabled:false → parked, never flagged, exit 0."""
    r = _run('[{"lane":"parked","ref":"op://Private/x/password","enabled":false,"required":true}]')
    assert r.returncode == 0


def test_bootstrap_dryrun_emits_commands_dedupes_and_hides_token():
    """bootstrap dry-run: emits create-vault + create-SA + one move PER ITEM (deduped across refs),
    executes nothing, and never prints a token value."""
    m = (
        '[{"lane":"a","ref":"op://Private/gmail-app-pw/password","env":["P"],"enabled":true,"required":true},'
        '{"lane":"b","ref":"op://Private/gmail-app-pw/username","env":["U"],"enabled":true,"required":true},'
        '{"lane":"c","ref":"op://Personal/CF Token/credential","env":["CF"],"enabled":true}]'
    )
    r = _run(m, command="bootstrap")
    assert r.returncode == 0
    assert "op service-account create" in r.stdout
    assert "op vault create Limen-Automation" in r.stdout
    # gmail-app-pw appears in two refs but must migrate exactly once; CF Token once.
    assert r.stdout.count("op item move gmail-app-pw") == 1
    assert r.stdout.count("op item move") == 2
    assert "[dry-run]" in r.stdout and "[ok]" not in r.stdout  # nothing executed
    # no obvious secret/token material leaked
    assert "ops_" not in r.stdout and "eyJ" not in r.stdout


def _module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("provision_test", PROVISION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _bootstrap_fixture(tmp_path, monkeypatch):
    import copy
    import json

    module = _module()
    policy = copy.deepcopy(module._POLICY_DEFAULTS)
    target = tmp_path / "service-account-token"
    policy["service_account"]["token_file"] = str(target)
    token = "ops_" + "synthetic_test_" * 4  # allow-secret: constructed nonfunctional test fixture
    state = {"items": [], "created": 0, "calls": [], "failure": None}

    def op(args, env, *, payload=None):
        state["calls"].append(args)
        operation = " ".join(args[:2])
        if operation == state["failure"]:
            raise module.ProvisionError("injected provider failure")
        if args[:2] == ["vault", "list"]:
            return json.dumps([{"id": "vault-id", "name": "Limen-Automation"}])
        if args[:2] == ["item", "list"]:
            return json.dumps(state["items"])
        if args[:2] == ["service-account", "create"]:
            assert "OP_SERVICE_ACCOUNT_TOKEN" not in env
            state["created"] += 1
            return token
        if args[:2] == ["item", "create"]:
            assert token not in str(args)
            assert json.loads(payload)["fields"][0]["value"] == token
            state["items"] = [{"id": "item-id", "title": "limen-fleet service account"}]
            return json.dumps(state["items"][0])
        if args[0] == "read":
            return token
        raise AssertionError(args)

    monkeypatch.setattr(module, "_op", op)
    return module, policy, target, token, state


def test_bootstrap_custody_readback_restart_and_previous_preservation(tmp_path, monkeypatch, capsys):
    module, policy, target, token, state = _bootstrap_fixture(tmp_path, monkeypatch)
    target.write_text("old-account")
    target.chmod(0o600)
    assert module.cmd_bootstrap(policy, [], True) == 0
    assert target.read_text().strip() == token
    assert target.stat().st_mode & 0o777 == 0o600
    assert target.with_name(target.name + ".previous").read_text().strip() == "old-account"
    assert module.cmd_bootstrap(policy, [], True) == 0
    assert state["created"] == 1
    assert not any(call[:2] == ["item", "move"] for call in state["calls"])
    assert token not in capsys.readouterr().out


def test_ambiguous_creation_preserves_intent_and_cannot_remint(tmp_path, monkeypatch):
    module, policy, target, token, state = _bootstrap_fixture(tmp_path, monkeypatch)
    state["failure"] = "service-account create"
    assert module.cmd_bootstrap(policy, [], True) == 2
    assert target.with_name(target.name + ".creation-intent").exists()
    state["failure"] = None
    assert module.cmd_bootstrap(policy, [], True) == 2
    assert state["created"] == 0
    assert not target.exists()


def test_custody_failure_preserves_pending_without_replacing_current(tmp_path, monkeypatch):
    module, policy, target, token, state = _bootstrap_fixture(tmp_path, monkeypatch)
    target.write_text("old-account")
    target.chmod(0o600)
    state["failure"] = "item create"
    assert module.cmd_bootstrap(policy, [], True) == 2
    assert target.read_text() == "old-account"
    pending = target.with_name(target.name + ".pending")
    assert pending.read_text().strip() == token
    assert pending.stat().st_mode & 0o777 == 0o600
    state["failure"] = None
    assert module.cmd_bootstrap(policy, [], True) == 0
    assert state["created"] == 1


def test_bootstrap_denied_read_stops_before_creation(tmp_path, monkeypatch):
    module, policy, target, token, state = _bootstrap_fixture(tmp_path, monkeypatch)
    state["failure"] = "vault list"
    assert module.cmd_bootstrap(policy, [], True) == 2
    assert state["created"] == 0
    assert not target.exists()


def test_owner_environment_preserves_native_session_without_service_override(monkeypatch):
    module = _module()
    monkeypatch.setenv("OP_SERVICE_ACCOUNT_TOKEN", "restricted-fixture")
    monkeypatch.setenv("OP_BIOMETRIC_UNLOCK_ENABLED", "false")
    monkeypatch.setenv("OP_SESSION_test", "owner-fixture")
    env = module._owner_environment()
    assert "OP_SERVICE_ACCOUNT_TOKEN" not in env
    assert "OP_BIOMETRIC_UNLOCK_ENABLED" not in env
    assert env["OP_SESSION_test"] == "owner-fixture"


@pytest.mark.parametrize("document", ["", "null", "[]", "false", "{}", "automation_vault: Limen-Automation"])
def test_mutating_bootstrap_rejects_missing_policy_without_provider_call(tmp_path, monkeypatch, document):
    module = _module()
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(document)
    monkeypatch.setattr(module, "POLICY_PATH", policy_path)
    monkeypatch.setattr(module, "_op", lambda *a, **kw: pytest.fail("provider reached without policy"))
    assert module.main(["bootstrap", "--apply"]) == 2


@pytest.mark.parametrize("defect", ["relative_target", "extra_vault", "missing_name", "extra_grant", "string_boolean"])
def test_policy_rejects_ambiguous_mutation_scope(tmp_path, monkeypatch, defect):
    import copy
    import yaml

    module = _module()
    policy = copy.deepcopy(module._POLICY_DEFAULTS)
    if defect == "relative_target":
        policy["service_account"]["token_file"] = "relative-token"
    elif defect == "extra_vault":
        policy["sa_readable_vaults"].append("another-vault")
    elif defect == "missing_name":
        del policy["service_account"]["name"]
    elif defect == "extra_grant":
        policy["service_account"]["create_flags"] += " --vault another-vault:read_items"
    else:
        policy["policy"]["derive_exempt"] = "false"
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(yaml.safe_dump(policy))
    monkeypatch.setattr(module, "POLICY_PATH", policy_path)
    with pytest.raises(ValueError):
        module.load_policy(strict=True)


@pytest.mark.parametrize("failure", ["timeout", "unavailable", "rejected"])
def test_op_failure_diagnostics_disclose_only_closed_stage_and_reason(monkeypatch, failure):
    module = _module()
    private = "private-provider-output-and-command-argument"

    def run(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired([private], 60, output=private, stderr=private)
        if failure == "unavailable":
            raise OSError(private)
        return subprocess.CompletedProcess([private], 1, private, private)

    monkeypatch.setattr(module.subprocess, "run", run)
    with pytest.raises(module.ProvisionError) as caught:
        module._op(["service-account", "create", private], {})
    assert caught.value.stage == "service-account-create"
    assert caught.value.reason == failure
    assert private not in str(caught.value)


def test_live_policy_is_explicit_and_valid():
    module = _module()
    assert module.load_policy(strict=True)["automation_vault"] == "Limen-Automation"
