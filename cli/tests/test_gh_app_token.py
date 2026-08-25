from __future__ import annotations

import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gh-app-token.sh"


def _executable(path: Path, source: str) -> None:
    path.write_text(source, encoding="utf-8")
    path.chmod(0o755)


def _app_environment(tmp_path: Path, **overrides: str) -> tuple[dict[str, str], Path]:
    binaries = tmp_path / "bin"
    binaries.mkdir()
    log = tmp_path / "curl.log"
    _executable(
        binaries / "openssl",
        """#!/usr/bin/env bash
if [ "${1:-}" = "base64" ]; then
  printf 'eA=='
else
  printf 'signature'
fi
""",
    )
    _executable(
        binaries / "curl",
        """#!/usr/bin/env bash
printf 'CALL\\n' >> "$MOCK_CURL_LOG"
for arg in "$@"; do
  printf '%s\\n' "$arg" >> "$MOCK_CURL_LOG"
done
case " $* " in
  *"/app/installations/77/access_tokens"*)
    [ "${MOCK_TOKEN_FAILURE:-0}" = "0" ] || exit 22
    case " $* " in
      *'{"repositories":["project"]}'*)
        printf '{"token":"bootstrap-token"}'
        ;;
      *'{"repository_ids":[125]}'*)
        [ "${MOCK_FINAL_TOKEN_FAILURE:-0}" = "0" ] || exit 22
        printf '{"token":"app-token"}'
        ;;
      *) exit 25 ;;
    esac
    ;;
  *"/repos/acme/project/installation"*)
    printf '{"id":%s}' "${MOCK_INSTALLATION_ID:-77}"
    ;;
  *"/repos/acme/project"*)
    case " $* " in
      *"Authorization: Bearer bootstrap-token"*) ;;
      *) exit 24 ;;
    esac
    printf '{"id":%s,"full_name":"%s"}' "${MOCK_REPOSITORY_ID:-125}" "${MOCK_FULL_NAME:-acme/project}"
    ;;
  *)
    exit 23
    ;;
esac
""",
    )
    env = os.environ.copy()
    for name in (
        "GITHUB_APP_ID",
        "GITHUB_APP_PRIVATE_KEY",
        "GITHUB_APP_INSTALLATION_ID",
        "GITHUB_TOKEN",
        "LIMEN_GITHUB_TARGET_REPO",
    ):
        env.pop(name, None)
    env.update(
        {
            "PATH": f"{binaries}{os.pathsep}{env['PATH']}",
            "LIMEN_ENV": str(tmp_path / "absent.env"),
            "GITHUB_API": "https://api.fixture.invalid",
            "GITHUB_APP_ID": "1234",
            "GITHUB_APP_PRIVATE_KEY": "-----BEGIN PRIVATE KEY----- fixture -----END PRIVATE KEY-----",  # allow-secret: inert malformed fixture
            "MOCK_CURL_LOG": str(log),
        }
    )
    env.update(overrides)
    return env, log


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_app_token_resolves_exact_installation_and_scopes_one_numeric_repository(tmp_path: Path) -> None:
    env, log = _app_environment(tmp_path, GITHUB_TOKEN="must-not-fallback")

    result = _run(env, "--repo", "acme/project")

    assert result.returncode == 0
    assert result.stdout == "app-token\n"
    calls = log.read_text(encoding="utf-8")
    assert "https://api.fixture.invalid/repos/acme/project/installation" in calls
    assert "https://api.fixture.invalid/repos/acme/project" in calls
    assert "https://api.fixture.invalid/app/installations/77/access_tokens" in calls
    assert '{"repositories":["project"]}' in calls
    assert '{"repository_ids":[125]}' in calls
    assert "Authorization: Bearer bootstrap-token" in calls
    assert calls.count("/app/installations/77/access_tokens") == 2
    assert calls.index("/app/installations/77/access_tokens") < calls.rindex("/repos/acme/project")
    assert calls.rindex("/app/installations/77/access_tokens") > calls.rindex("/repos/acme/project")
    assert "must-not-fallback" not in result.stdout + result.stderr + calls


def test_app_credentials_without_exact_repo_fail_without_pat_or_gh_fallback(tmp_path: Path) -> None:
    env, log = _app_environment(tmp_path, GITHUB_TOKEN="must-not-fallback")

    result = _run(env)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "exact target required" in result.stderr
    assert not log.exists()


def test_pinned_installation_must_equal_exact_repository_installation(tmp_path: Path) -> None:
    env, log = _app_environment(
        tmp_path,
        GITHUB_APP_INSTALLATION_ID="88",
        GITHUB_TOKEN="must-not-fallback",
    )

    result = _run(env, "--repo", "acme/project")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "pinned installation id does not match" in result.stderr
    assert "/repos/acme/project/installation" in log.read_text(encoding="utf-8")
    assert "/access_tokens" not in log.read_text(encoding="utf-8")


def test_repository_identity_mismatch_fails_closed_before_token_mint(tmp_path: Path) -> None:
    env, log = _app_environment(
        tmp_path,
        MOCK_FULL_NAME="acme/other",
        GITHUB_TOKEN="must-not-fallback",
    )

    result = _run(env, "--repo", "acme/project")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "repository identity mismatch" in result.stderr
    assert "/access_tokens" in log.read_text(encoding="utf-8")


def test_app_token_request_failure_never_broadens_to_pat(tmp_path: Path) -> None:
    env, _log = _app_environment(
        tmp_path,
        MOCK_TOKEN_FAILURE="1",
        GITHUB_TOKEN="must-not-fallback",
    )

    result = _run(env, "--repo", "acme/project")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "refusing PAT/gh" in result.stderr


def test_numeric_repository_token_failure_never_emits_bootstrap_token_or_broadens_to_pat(tmp_path: Path) -> None:
    env, log = _app_environment(
        tmp_path,
        MOCK_FINAL_TOKEN_FAILURE="1",
        GITHUB_TOKEN="must-not-fallback",
    )

    result = _run(env, "--repo", "acme/project")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "numeric-repository-scoped installation token request rejected" in result.stderr
    assert "refusing PAT/gh" in result.stderr
    calls = log.read_text(encoding="utf-8")
    assert "Authorization: Bearer bootstrap-token" in calls
    assert "must-not-fallback" not in result.stdout + result.stderr + calls


def test_pat_fallback_remains_available_only_when_app_credentials_are_absent(tmp_path: Path) -> None:
    env, _log = _app_environment(tmp_path)
    env.pop("GITHUB_APP_ID")
    env.pop("GITHUB_APP_PRIVATE_KEY")
    env["GITHUB_TOKEN"] = "pat-token"

    result = _run(env, "--repo", "acme/project")

    assert result.returncode == 0
    assert result.stdout == "pat-token\n"


def test_pat_fallback_without_exact_repository_is_refused(tmp_path: Path) -> None:
    env, _log = _app_environment(tmp_path)
    env.pop("GITHUB_APP_ID")
    env.pop("GITHUB_APP_PRIVATE_KEY")
    env["GITHUB_TOKEN"] = "must-not-emit"

    result = _run(env)

    assert result.returncode == 1
    assert result.stdout == ""
    assert "exact target required" in result.stderr


def test_app_only_never_uses_pat_when_app_credentials_are_absent(tmp_path: Path) -> None:
    env, log = _app_environment(tmp_path)
    env.pop("GITHUB_APP_ID")
    env.pop("GITHUB_APP_PRIVATE_KEY")
    env["GITHUB_TOKEN"] = "must-not-fallback"

    result = _run(env, "--repo", "acme/project", "--app-only")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "App-only mode requires" in result.stderr
    assert not log.exists()


def test_which_proves_exact_installation_instead_of_only_inspecting_environment(tmp_path: Path) -> None:
    env, log = _app_environment(tmp_path)

    result = _run(env, "--repo", "acme/project", "--which")

    assert result.returncode == 0
    assert result.stdout.startswith("app ")
    calls = log.read_text(encoding="utf-8")
    assert "/repos/acme/project/installation" in calls
    assert "/app/installations/77/access_tokens" in calls


def test_partial_app_configuration_fails_closed_instead_of_using_pat(tmp_path: Path) -> None:
    env, _log = _app_environment(tmp_path, GITHUB_TOKEN="must-not-fallback")
    env.pop("GITHUB_APP_PRIVATE_KEY")

    result = _run(env, "--repo", "acme/project")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "credentials are incomplete" in result.stderr


def test_repository_target_rejects_path_traversal_segments(tmp_path: Path) -> None:
    env, log = _app_environment(tmp_path, GITHUB_TOKEN="must-not-fallback")

    result = _run(env, "--repo", "../project")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "exact target required" in result.stderr
    assert not log.exists()
