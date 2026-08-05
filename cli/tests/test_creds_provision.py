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
