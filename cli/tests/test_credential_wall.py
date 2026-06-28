"""credential-wall — the secret/credential Wall generator (pinned issue #320).

The Wall claims to be machine-generated from `DEFAULT_MAP`; these pin that the generator actually
exists, indexes EVERY secret atom (hydration lanes + CI/runtime secrets), leaks no values, and
that `--check` is a real predicate — exit 0 ⟺ every credential in use has a registered home.
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _wall():
    return _mod("credential_wall", "scripts/credential-wall.py")


def test_body_indexes_every_hydration_lane():
    m = _wall()
    body = m.wall_body()
    # every env var that creds-hydrate manages must appear on the Wall
    for entry in m._load_default_map():
        for env in entry.get("env", []):
            assert env in body, f"{env} missing from the credential Wall"


def test_body_indexes_every_ci_secret():
    m = _wall()
    body = m.wall_body()
    for s in m.CI_SECRETS:
        assert s["name"] in body, f"{s['name']} missing from the credential Wall"
    # the four that were previously absent are the whole point of this generator
    for name in ("LIMEN_API_TOKEN", "LIMEN_CLIENT_TOKEN", "GCP_SA_KEY", "WARP_API_KEY", "OP_SERVICE_ACCOUNT_TOKEN"):
        assert name in body


def test_body_carries_marker_and_no_values():
    m = _wall()
    body = m.wall_body()
    assert m.WALL_MARKER in body
    # values never touch the repo — no 1Password service-account token prefix may appear
    assert "ops_" not in body


def test_check_passes_when_everything_homed():
    assert _wall().check() == 0


def test_check_flags_a_homeless_ci_secret(monkeypatch):
    m = _wall()
    monkeypatch.setattr(
        m, "CI_SECRETS", m.CI_SECRETS + [{"name": "ORPHAN", "home": "", "used": "", "hand": "", "issue": "—"}]
    )
    assert m.check() == 1
