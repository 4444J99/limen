from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load_script(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_ruleset_registry_and_limen_guards_are_case_insensitive() -> None:
    setup_rulesets = _load_script("setup_rulesets_coordinate_test", "scripts/setup-rulesets.py")

    assert (
        setup_rulesets.checks_for_repo(
            "4444j99/LIMEN",
            facts={"archived": False, "fork": False, "private": False},
        )
        == []
    )
    assert setup_rulesets._is_limen_repo("4444j99/LIMEN") is True


def test_ruleset_repo_overrides_are_case_insensitive() -> None:
    setup_rulesets = _load_script("setup_rulesets_override_test", "scripts/setup-rulesets.py")
    document = {
        "classes": {
            "special": {"match": []},
            "fallback": {"match": ["**"]},
        },
        "repo_overrides": {"Owner/Repo": {"class": "special"}},
    }

    name, _row = setup_rulesets._class_for_repo(document, "owner/REPO", facts={})

    assert name == "special"


@pytest.mark.parametrize(
    "candidate",
    [None, "4444j99/LIMEN", "organvm/limen", "ORGANVM/LIMEN"],
)
def test_bootstrap_resolves_limen_aliases_to_canonical_repository(candidate: str | None) -> None:
    bootstrap = _load_script("bootstrap_github_app_target_test", "scripts/bootstrap-github-app.py")

    assert bootstrap.canonical_verification_target(candidate) == "4444J99/limen"


def test_bootstrap_rejects_non_repository_installation_target() -> None:
    bootstrap = _load_script("bootstrap_github_app_invalid_target_test", "scripts/bootstrap-github-app.py")

    with pytest.raises(ValueError, match="exact OWNER/REPO"):
        bootstrap.canonical_verification_target("4444J99")


def test_bootstrap_wait_probes_only_the_exact_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap = _load_script("bootstrap_github_app_wait_test", "scripts/bootstrap-github-app.py")
    probes: list[tuple[str, bool]] = []

    def verify(repo: str, *, quiet: bool = False) -> bool:
        probes.append((repo, quiet))
        return True

    monkeypatch.setattr(bootstrap, "verify_app_token", verify)

    assert bootstrap.wait_for_repository_installation("4444J99/limen", 0) is True
    assert probes == [("4444J99/limen", True)]


def test_bootstrap_personal_owner_action_and_manifest_match_exact_target() -> None:
    bootstrap = _load_script("bootstrap_github_app_personal_owner_test", "scripts/bootstrap-github-app.py")

    with bootstrap.BootstrapServer(
        ("127.0.0.1", 0),
        bootstrap.BootstrapHandler,
        app_owner="4444J99",
        app_owner_type="User",
        app_name="limen-bot-test",
        install_repo="4444J99/limen",
    ) as server:
        assert server.manifest_action.startswith(f"{bootstrap.GITHUB_WEB}/settings/apps/new?state=")
        assert "/organizations/" not in server.manifest_action
        assert server.manifest["public"] is False
        assert server.manifest["url"] == f"{bootstrap.GITHUB_WEB}/4444J99/limen"
        assert server.manifest["hook_attributes"]["url"] == f"{bootstrap.GITHUB_WEB}/4444J99/limen"


def test_bootstrap_resolves_account_type_for_exact_target_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    bootstrap = _load_script("bootstrap_github_app_account_type_test", "scripts/bootstrap-github-app.py")
    calls: list[list[str]] = []

    def run(argv: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="User\n", stderr="")

    monkeypatch.setattr(bootstrap.subprocess, "run", run)

    assert bootstrap.github_account_type("4444J99") == "User"
    assert calls == [["gh", "api", "/users/4444J99", "--jq", ".type"]]


def test_bootstrap_organization_owner_uses_organization_manifest_action() -> None:
    bootstrap = _load_script("bootstrap_github_app_org_owner_test", "scripts/bootstrap-github-app.py")

    action = bootstrap.manifest_settings_url("organvm", "Organization", "fixed-state")

    assert action == f"{bootstrap.GITHUB_WEB}/organizations/organvm/settings/apps/new?state=fixed-state"


def test_bootstrap_private_app_rejects_cross_owner_target() -> None:
    bootstrap = _load_script("bootstrap_github_app_owner_mismatch_test", "scripts/bootstrap-github-app.py")

    with pytest.raises(ValueError, match="private App owner must match"):
        bootstrap.BootstrapServer(
            ("127.0.0.1", 0),
            bootstrap.BootstrapHandler,
            app_owner="organvm",
            app_owner_type="Organization",
            app_name="limen-bot-test",
            install_repo="4444J99/limen",
        )
