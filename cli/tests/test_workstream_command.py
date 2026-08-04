from __future__ import annotations

import hashlib
import json
import os
import pty
import shlex
import shutil
import stat
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path

import pytest
from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

import limen.census as census  # noqa: E402
from limen.cli import main  # noqa: E402
from limen.workstream_contract import RECEIPT_MODULES, new_contract  # noqa: E402


ADMITTED_PROVIDER_INSTRUCTION = (
    "This session is already admitted; read the modules and continue. Do not execute the operator launch command."
)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stdout}\n{result.stderr}")
    return result


def _write_committed_predecessor(repo: Path) -> tuple[Path, bytes, dict[str, object]]:
    remote = repo.parent / "origin.git"
    remote.mkdir()
    _git("init", "--bare", "-q", cwd=remote)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    _git("push", "-u", "origin", "main", cwd=repo)
    predecessor_worktree = repo.parent / "predecessor-worktree"
    _git("worktree", "add", "-b", "work/predecessor", str(predecessor_worktree), "main", cwd=repo)
    contract = new_contract("16d")
    runway = contract["runway"]
    runway.update(
        {
            "started_at": "2026-08-01T19:22:22+00:00",
            "started_epoch": 1_785_612_142,
            "deadline_at": "2026-08-17T19:22:22+00:00",
            "deadline_epoch": 1_786_994_542,
        }
    )
    receipt_value = {
        "schema": "limen.workstream.receipt.v1",
        "slug": "predecessor",
        "branch": "work/predecessor",
        "workstream": "alpha-omega",
        "contract": contract,
        "private_capsule": {
            "content": "redacted",
            "modules": list(RECEIPT_MODULES),
        },
    }
    receipt = predecessor_worktree / "docs" / "continuations" / "predecessor" / "workstream.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(json.dumps(receipt_value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _git("add", "docs/continuations/predecessor/workstream.json", cwd=predecessor_worktree)
    _git("commit", "-qm", "docs: preserve admitted predecessor", cwd=predecessor_worktree)
    _git("push", "-u", "origin", "work/predecessor", cwd=predecessor_worktree)
    return receipt, receipt.read_bytes(), contract


def _fixture_limen_root(tmp_path: Path) -> Path:
    fixture_root = tmp_path / "fixture-limen"
    (fixture_root / "scripts" / "lib").mkdir(parents=True)
    (fixture_root / "spec").mkdir()
    shutil.copy2(ROOT / "scripts" / "start-worktree-session.sh", fixture_root / "scripts")
    for name in ("workstream-capsule.sh", "campaign-relay-capsule.sh"):
        shutil.copy2(ROOT / "scripts" / "lib" / name, fixture_root / "scripts" / "lib")
    shutil.copytree(ROOT / "spec" / "continuation-capsule", fixture_root / "spec" / "continuation-capsule")
    shutil.copytree(ROOT / "cli" / "src", fixture_root / "cli" / "src")
    return fixture_root


def _fixture_limen_root_with_renamed_provider(
    tmp_path: Path,
    source: census.Vendor,
    renamed: census.Vendor,
) -> Path:
    """Copy the launcher with a test registry whose selected provider has an arbitrary ID."""

    fixture_root = _fixture_limen_root(tmp_path)
    census_path = fixture_root / "cli" / "src" / "limen" / "census.py"
    registry_source = census_path.read_text(encoding="utf-8")
    original_name = f'name="{source.name}"'
    original_binary = f'binary="{source.binary}"'
    record_start = registry_source.index(f"    Vendor(\n        {original_name},")
    record_end = registry_source.find("\n    Vendor(", record_start + 1)
    if record_end == -1:
        record_end = len(registry_source)
    source_record = registry_source[record_start:record_end]
    assert source_record.count(original_name) == 1
    assert source_record.count(original_binary) == 1
    alias_line = next(line for line in source_record.splitlines() if line.strip().startswith("aliases="))
    renamed_record = source_record.replace(original_name, f'name="{renamed.name}"', 1)
    renamed_record = renamed_record.replace(original_binary, f'binary="{renamed.binary}"', 1)
    renamed_record = renamed_record.replace(alias_line, "        aliases=(),", 1)
    registry_source = registry_source[:record_start] + renamed_record + registry_source[record_end:]
    census_path.write_text(registry_source, encoding="utf-8")
    return fixture_root


def test_registry_fixture_can_rename_a_provider_in_the_last_catalog_position(tmp_path: Path) -> None:
    source = census.VENDORS[-1]
    renamed = replace(
        source,
        name="fixture-final-provider",
        aliases=(),
        binary="fixture-final-provider-cli",
    )

    fixture_root = _fixture_limen_root_with_renamed_provider(tmp_path, source, renamed)

    fixture_registry = (fixture_root / "cli" / "src" / "limen" / "census.py").read_text(encoding="utf-8")
    assert f'name="{renamed.name}"' in fixture_registry
    assert f'binary="{renamed.binary}"' in fixture_registry


def test_workstream_command_writes_private_kickstart_packet(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = fake_bin / "opencode"
    fake_opencode.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_opencode.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "opencode")
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--prompt",
            "Ship a bounded packet.",
            str(repo),
            "Demo Packet",
        ],
    )

    assert result.exit_code == 0, result.output
    wt = repo / ".worktrees" / "demo-packet"
    readme = wt / ".limen-workstream" / "README.md"
    intent = wt / ".limen-workstream" / "intent.md"
    kickstart = wt / ".limen-workstream" / "kickstart.sh"
    receipt = wt / "docs" / "continuations" / "demo-packet" / "workstream.json"
    assert readme.exists()
    assert intent.exists()
    assert kickstart.exists()
    assert receipt.exists()
    kickstart_text = kickstart.read_text(encoding="utf-8")
    assert "workstream_launch_native_agent" in kickstart_text
    assert "agent=opencode" in kickstart_text
    assert "exec codex --ask-for-approval never --sandbox workspace-write" not in kickstart_text
    assert (
        json.loads((wt / ".limen-workstream" / "workstream.json").read_text(encoding="utf-8"))["runway"][
            "duration_seconds"
        ]
        == 86_400
    )
    assert "Ship a bounded packet." in intent.read_text(encoding="utf-8")
    assert "Ship a bounded packet." not in readme.read_text(encoding="utf-8")
    assert "bash " in result.output and "kickstart.sh" in result.output
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout

    capsule = wt / ".limen-workstream"
    helper = capsule / "workstream-contract.py"
    for child in capsule.iterdir():
        if child != helper:
            child.unlink()
    receipt.unlink()
    partial = CliRunner().invoke(
        main,
        [
            "workstream",
            "--prompt",
            "Ship a bounded packet.",
            str(repo),
            "Demo Packet",
        ],
    )
    assert partial.exit_code != 0
    assert "workstream contract is missing" in partial.output


def test_workstream_command_creates_inherited_and_renewed_successors_without_mutating_predecessor(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    predecessor, predecessor_bytes, predecessor_contract = _write_committed_predecessor(repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = fake_bin / "opencode"
    fake_opencode.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_opencode.chmod(0o755)
    fake_jules = fake_bin / "jules"
    fake_jules.write_text('#!/usr/bin/env bash\n: > "$PROVIDER_MARKER"\n', encoding="utf-8")
    fake_jules.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "opencode")
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    predecessor_head = _git("rev-parse", "HEAD", cwd=predecessor.parents[3]).stdout.strip()
    inherited_args = [
        "workstream",
        "--prompt",
        "Continue from the committed predecessor.",
        "--predecessor-receipt",
        str(predecessor),
        str(repo),
        "Inherited Successor",
    ]

    _git("branch", "work/uncapsuled-successor", "main", cwd=repo)
    unrelated_reuse = CliRunner().invoke(
        main,
        [
            "workstream",
            "--predecessor-receipt",
            str(predecessor),
            str(repo),
            "Uncapsuled Successor",
        ],
    )
    assert unrelated_reuse.exit_code == 2
    assert "existing uncapsuled successor target does not match" in unrelated_reuse.output
    assert not (repo / ".worktrees" / "uncapsuled-successor").exists()

    inherited = CliRunner().invoke(main, inherited_args)

    assert inherited.exit_code == 0, inherited.output
    inherited_wt = repo / ".worktrees" / "inherited-successor"
    inherited_contract = json.loads(
        (inherited_wt / ".limen-workstream" / "workstream.json").read_text(encoding="utf-8")
    )
    inherited_receipt_path = inherited_wt / "docs" / "continuations" / "inherited-successor" / "workstream.json"
    inherited_receipt_text = inherited_receipt_path.read_text(encoding="utf-8")
    inherited_receipt = json.loads(inherited_receipt_text)
    expected_lineage = {
        "slug": "predecessor",
        "branch": "work/predecessor",
        "receipt_sha256": hashlib.sha256(predecessor_bytes).hexdigest(),
    }
    assert inherited_contract["runway"] == predecessor_contract["runway"]
    assert inherited_contract["schema"] == "limen.workstream.contract.v1"
    assert inherited_contract["authorization"]["sandbox"] == "workspace-write"
    assert inherited_contract["conductor"]["provider_and_model"] == "provider_neutral"
    assert inherited_contract["runway"]["deadline_at"] == "2026-08-17T19:22:22+00:00"
    assert inherited_receipt["predecessor"] == expected_lineage
    assert _git("rev-parse", "HEAD", cwd=inherited_wt).stdout.strip() == predecessor_head
    assert f"Base ref: `{predecessor_head}`" in (inherited_wt / ".limen-workstream" / "manifest.md").read_text(
        encoding="utf-8"
    )
    assert str(predecessor) not in inherited_receipt_text
    for generated in (inherited_wt / ".limen-workstream").iterdir():
        if not generated.is_file():
            continue
        assert str(predecessor).encode() not in generated.read_bytes()
    assert predecessor.read_bytes() == predecessor_bytes

    rerender_paths = [
        path
        for path in (inherited_wt / ".limen-workstream").iterdir()
        if path.is_file() and path.name != ".capsule.lock"
    ] + [inherited_receipt_path]
    before_rerender = {path: path.read_bytes() for path in rerender_paths}
    repeated = CliRunner().invoke(main, inherited_args)
    assert repeated.exit_code == 0, repeated.output
    assert "capsule index:" in repeated.output and "(unchanged)" in repeated.output
    assert {path: path.read_bytes() for path in rerender_paths} == before_rerender

    renewed = CliRunner().invoke(
        main,
        [
            "workstream",
            "--prompt",
            "Create a distinct renewed successor.",
            "--predecessor-receipt",
            str(predecessor),
            "--runway-mode",
            "renew",
            "--runway",
            "2d",
            str(repo),
            "Renewed Successor",
        ],
    )

    assert renewed.exit_code == 0, renewed.output
    renewed_wt = repo / ".worktrees" / "renewed-successor"
    renewed_contract = json.loads((renewed_wt / ".limen-workstream" / "workstream.json").read_text(encoding="utf-8"))
    renewed_receipt = json.loads(
        (renewed_wt / "docs" / "continuations" / "renewed-successor" / "workstream.json").read_text(encoding="utf-8")
    )
    assert renewed_contract["runway"]["requested"] == "2d"
    assert renewed_contract["runway"]["started_epoch"] is None
    assert renewed_contract["runway"]["deadline_epoch"] is None
    assert renewed_contract["authorization"]["sandbox"] == "workspace-write"
    assert renewed_contract["conductor"]["provider_and_model"] == "provider_neutral"
    assert renewed_receipt["predecessor"] == expected_lineage
    assert _git("rev-parse", "HEAD", cwd=renewed_wt).stdout.strip() == predecessor_head
    assert predecessor.read_bytes() == predecessor_bytes

    # A successor is deliberately based on the predecessor's exact branch head, which need not
    # be the repository's live default HEAD. Jules cannot consume that base. The generated
    # kickstart must reject it before admission mutates the fresh runway or receipt.
    _git("symbolic-ref", "HEAD", "refs/heads/main", cwd=repo.parent / "origin.git")
    monkeypatch.setenv("LIMEN_AGENT", "jules")
    jules_successor = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--prompt",
            "Reject a successor base that Jules cannot consume.",
            "--predecessor-receipt",
            str(predecessor),
            "--runway-mode",
            "renew",
            "--runway",
            "2d",
            str(repo),
            "Jules Incompatible Successor",
        ],
    )
    assert jules_successor.exit_code == 0, jules_successor.output
    monkeypatch.setenv("LIMEN_AGENT", "opencode")
    jules_wt = repo / ".worktrees" / "jules-incompatible-successor"
    jules_contract = jules_wt / ".limen-workstream" / "workstream.json"
    jules_receipt = jules_wt / "docs" / "continuations" / "jules-incompatible-successor" / "workstream.json"
    protected = (jules_contract, jules_receipt)
    protected_bytes = {path: path.read_bytes() for path in protected}
    provider_marker = tmp_path / "jules-provider-started"

    rejected_jules = subprocess.run(
        ["bash", str(jules_wt / ".limen-workstream" / "kickstart.sh")],
        cwd=jules_wt,
        env={**os.environ, "PROVIDER_MARKER": str(provider_marker)},
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert rejected_jules.returncode == 2
    assert "requires current HEAD to equal the live remote default HEAD" in rejected_jules.stderr
    assert {path: path.read_bytes() for path in protected} == protected_bytes
    assert json.loads(jules_contract.read_text(encoding="utf-8"))["runway"]["started_epoch"] is None
    assert not provider_marker.exists()

    invalid = CliRunner().invoke(
        main,
        [
            "workstream",
            "--predecessor-receipt",
            str(predecessor),
            "--runway",
            "1d",
            str(repo),
            "Invalid Inherited Successor",
        ],
    )
    assert invalid.exit_code == 2
    assert "cannot accept --runway" in invalid.output
    assert not (repo / ".worktrees" / "invalid-inherited-successor").exists()

    wrong_base = CliRunner().invoke(
        main,
        [
            "workstream",
            "--predecessor-receipt",
            str(predecessor),
            "--from",
            "main",
            str(repo),
            "Wrong Base Successor",
        ],
    )
    assert wrong_base.exit_code == 2
    assert "--from must resolve to the exact predecessor HEAD" in wrong_base.output
    assert not (repo / ".worktrees" / "wrong-base-successor").exists()

    no_capsule = CliRunner().invoke(
        main,
        [
            "workstream",
            "--predecessor-receipt",
            str(predecessor),
            "--no-readme",
            str(repo),
            "Missing Successor Capsule",
        ],
    )
    assert no_capsule.exit_code == 2
    assert "successor custody requires a capsule" in no_capsule.output
    assert not (repo / ".worktrees" / "missing-successor-capsule").exists()

    missing_predecessor = CliRunner().invoke(
        main,
        ["workstream", "--runway-mode", "inherit", str(repo), "Missing Predecessor"],
    )
    assert missing_predecessor.exit_code == 2
    assert "--runway-mode requires --predecessor-receipt" in missing_predecessor.output


def test_successor_custody_failure_precedes_module_writes_and_allows_exact_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    predecessor, _predecessor_bytes, _predecessor_contract = _write_committed_predecessor(repo)
    fixture_root = _fixture_limen_root(tmp_path)
    helper = fixture_root / "cli" / "src" / "limen" / "workstream_contract.py"
    helper_source = helper.read_text(encoding="utf-8")
    parse_marker = "    args = parser.parse_args(argv)\n    try:\n"
    assert parse_marker in helper_source
    helper.write_text(
        helper_source.replace(
            parse_marker,
            (
                "    args = parser.parse_args(argv)\n"
                "    if args.command == 'configure-successor' and "
                "os.environ.get('FAIL_SUCCESSOR_CONFIGURE') == '1':\n"
                "        raise SystemExit('injected successor custody race')\n"
                "    try:\n"
            ),
            1,
        ),
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_opencode = fake_bin / "opencode"
    fake_opencode.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_opencode.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(fixture_root))
    monkeypatch.setenv("LIMEN_AGENT", "opencode")
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("FAIL_SUCCESSOR_CONFIGURE", "1")
    argv = [
        "workstream",
        "--predecessor-receipt",
        str(predecessor),
        str(repo),
        "Retryable Successor",
    ]

    failed = CliRunner().invoke(main, argv)

    assert failed.exit_code != 0
    wt = repo / ".worktrees" / "retryable-successor"
    capsule = wt / ".limen-workstream"
    assert capsule.is_dir()
    assert sorted(path.name for path in capsule.iterdir()) == [".capsule.lock"]
    assert not (wt / "docs" / "continuations" / "retryable-successor" / "workstream.json").exists()

    monkeypatch.delenv("FAIL_SUCCESSOR_CONFIGURE")
    retried = CliRunner().invoke(main, argv)

    assert retried.exit_code == 0, retried.output
    assert (capsule / "workstream.json").is_file()
    assert (capsule / "manifest.md").is_file()
    assert (wt / "docs" / "continuations" / "retryable-successor" / "workstream.json").is_file()


NON_NATIVE_WORKSTREAM_PROVIDERS = tuple(
    provider
    for provider in census.VENDORS
    if provider.issue_assignment
    or (
        provider.execution.transport != "native-cli"
        and not provider.execution.transport.startswith("ianva-")
        and provider.execution.workstream_adapter != "jules"
    )
)


@pytest.mark.parametrize("provider", NON_NATIVE_WORKSTREAM_PROVIDERS, ids=lambda provider: provider.name)
def test_non_native_lane_is_rejected_before_workstream_creation(
    tmp_path: Path,
    monkeypatch,
    capfd,
    provider: census.Vendor,
) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))

    result = CliRunner().invoke(
        main,
        ["workstream", "--agent", provider.name, str(repo), f"No Native {provider.name}"],
    )

    assert result.exit_code != 0
    assert "has no verified native workstream adapter" in capfd.readouterr().err
    assert not (repo / ".worktrees" / f"no-native-{provider.name}").exists()


def test_non_autonomous_jules_is_rejected_before_workstream_creation(tmp_path: Path, monkeypatch, capfd) -> None:
    source = next(provider for provider in census.VENDORS if provider.execution.workstream_adapter == "jules")
    renamed = replace(
        source,
        name="fixture-jules-interactive-renamed",
        aliases=(),
        binary="fixture-jules-interactive-cli",
    )
    fixture_root = _fixture_limen_root_with_renamed_provider(tmp_path, source, renamed)
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_jules = fake_bin / renamed.binary
    fake_jules.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_jules.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(fixture_root))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    result = CliRunner().invoke(
        main,
        ["workstream", "--agent", renamed.name, str(repo), "Interactive Renamed Jules"],
    )

    assert result.exit_code != 0
    assert "requires --autonomous" in capfd.readouterr().err
    assert not (repo / ".worktrees" / "interactive-renamed-jules").exists()


def test_autonomous_jules_workstream_uses_remote_cloud_transport(tmp_path: Path, monkeypatch, capfd) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    _git("remote", "add", "origin", "https://github.com/organvm/demo-repo.git/", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_jules = fake_bin / "jules"
    fake_jules.write_text(
        (
            "#!/usr/bin/env bash\n"
            'printf "jules\\n" >> "$EVENTS_CAPTURE"\n'
            'printf "%s\\n" "$@" > "$SESSION_ARGS_CAPTURE"\n'
            'if [[ "${JULES_SLEEP:-0}" == "1" ]]; then exec sleep 5; fi\n'
            'printf "Session is created.\\nID: 12345678901234567890\\nTask: test\\n\\n'
            'URL: https://jules.google.com/session/12345678901234567890\\n"\n'
            'if [[ "${JULES_FAIL_AFTER_OUTPUT:-0}" == "1" ]]; then exit 42; fi\n'
        ),
        encoding="utf-8",
    )
    fake_jules.chmod(0o755)
    real_git = shutil.which("git")
    assert real_git is not None
    fake_git = fake_bin / "git"
    # Fake userinfo proves repository selection never forwards credentials to Jules.
    fake_git.write_text(
        (
            "#!/usr/bin/env bash\n"
            'if [[ "$*" == *"remote get-url origin"* ]]; then\n'
            '  printf "%s\\n" "${FAKE_ORIGIN:-https://x-access-token:redacted@github.com/organvm/demo-repo.git/}"\n'
            "  exit 0\n"
            "fi\n"
            'if [[ "$*" == *"fetch --prune"* ]]; then exit 0; fi\n'
            'if [[ "$*" == *"ls-remote origin HEAD"* ]]; then\n'
            '  resolved_head="$REMOTE_HEAD"\n'
            '  if [[ "${ADVANCE_REMOTE_AFTER_FIRST_CHECK:-0}" == "1" ]]; then\n'
            '    check_count="$(cat "$REMOTE_HEAD_CHECK_COUNT" 2>/dev/null || printf 0)"\n'
            "    check_count=$((check_count + 1))\n"
            '    printf "%s" "$check_count" > "$REMOTE_HEAD_CHECK_COUNT"\n'
            '    if [[ "$check_count" -gt "${ADVANCE_REMOTE_AFTER_CHECKS:-1}" ]]; then '
            'resolved_head="$ADVANCED_REMOTE_HEAD"; fi\n'
            "  fi\n"
            '  printf "%s\\tHEAD\\n" "$resolved_head"\n'
            "  exit 0\n"
            "fi\n"
            'if [[ "$*" == *"ls-remote origin refs/heads/"* ]]; then\n'
            '  printf "%s\\t%s\\n" "$("$REAL_GIT" rev-parse HEAD)" "${!#}"\n'
            "  exit 0\n"
            "fi\n"
            'if [[ "$*" == *"status --porcelain --untracked-files=all"* && "${REPORT_DIRTY:-0}" == "1" ]]; then\n'
            '  printf " M local-only.txt\\n"\n'
            "  exit 0\n"
            "fi\n"
            'if [[ "$*" == *"commit -qm chore: preserve Jules session"* && "${FAIL_RECEIPT_COMMIT:-0}" == "1" ]]; then\n'
            "  exit 42\n"
            "fi\n"
            'if [[ "$*" == *"push --set-upstream origin"* ]]; then\n'
            '  printf "%s\\n" "$*" >> "$PUSH_CAPTURE"\n'
            '  printf "push\\n" >> "$EVENTS_CAPTURE"\n'
            "  exit 0\n"
            "fi\n"
            'exec "$REAL_GIT" "$@"\n'
        ),
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    args_capture = tmp_path / "jules-args.txt"
    push_capture = tmp_path / "jules-push.txt"
    events_capture = tmp_path / "jules-events.txt"
    remote_head = _git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    remote_head_check_count = tmp_path / "remote-head-check-count.txt"
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("REAL_GIT", real_git)
    monkeypatch.setenv("REMOTE_HEAD", remote_head)
    monkeypatch.setenv("REMOTE_HEAD_CHECK_COUNT", str(remote_head_check_count))
    monkeypatch.setenv("ADVANCED_REMOTE_HEAD", "1" * 40)
    monkeypatch.setenv("PUSH_CAPTURE", str(push_capture))
    monkeypatch.setenv("EVENTS_CAPTURE", str(events_capture))
    monkeypatch.setenv("SESSION_ARGS_CAPTURE", str(args_capture))

    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--agent",
            "jules",
            "--prompt",
            "Ship the exact bounded packet.",
            str(repo),
            "Jules Cloud",
        ],
    )

    assert result.exit_code == 0, result.output
    args = args_capture.read_text(encoding="utf-8").splitlines()
    assert args[:4] == ["remote", "new", "--repo", "organvm/demo-repo"]
    assert all("redacted" not in arg for arg in args)
    assert args[4] == "--session"
    assert args[5] == ADMITTED_PROVIDER_INSTRUCTION
    assert "Do NOT ask for feedback or approval." in args[7]
    assert "Ship the exact bounded packet." in "\n".join(args[5:])
    assert "# Continuation capsule:" not in args[5]
    wt = repo / ".worktrees" / "jules-cloud"
    receipt_path = wt / "docs" / "continuations" / "jules-cloud" / "workstream.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["provider_run"] == {
        "provider": "jules",
        "id": "12345678901234567890",
        "url": "https://jules.google.com/session/12345678901234567890",
    }
    reserved_receipt = json.loads(
        _git(
            "show",
            "HEAD^:docs/continuations/jules-cloud/workstream.json",
            cwd=wt,
        ).stdout
    )
    assert reserved_receipt["schema"] == "limen.workstream.receipt.v1"
    assert "provider_run" not in reserved_receipt
    assert _git("status", "--short", cwd=wt).stdout == ""
    assert (
        _git("log", "-1", "--format=%s", cwd=wt).stdout.strip()
        == "chore: preserve Jules session 12345678901234567890 receipt"
    )
    pushes = push_capture.read_text(encoding="utf-8").splitlines()
    assert len(pushes) == 2
    assert all("HEAD:" not in push for push in pushes)
    assert all(":refs/heads/work/jules-cloud" in push for push in pushes)
    assert events_capture.read_text(encoding="utf-8").splitlines() == ["push", "jules", "push"]
    kickstart = wt / ".limen-workstream" / "kickstart.sh"
    kickstart_text = kickstart.read_text(encoding="utf-8")
    assert (
        'if [[ "$launch_adapter" != "jules" ]]; then\n'
        '  workstream_publish_admitted_receipt "$receipt" "$expected_branch" "$expected_slug"\n'
        "  exec 9>&-\n"
        "fi"
    ) in kickstart_text

    original_receipt = receipt_path.read_text(encoding="utf-8")
    args_capture.unlink()
    events_before = events_capture.read_text(encoding="utf-8")
    relaunch = subprocess.run(
        ["bash", str(kickstart)],
        cwd=wt,
        env={**os.environ},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert relaunch.returncode == 0, relaunch.stdout + relaunch.stderr
    assert "receipt republished" in relaunch.stdout
    assert receipt_path.read_text(encoding="utf-8") == original_receipt
    assert events_capture.read_text(encoding="utf-8") == events_before + "push\n"
    assert not args_capture.exists()

    (wt / "unrelated.txt").write_text("must not ride the receipt push\n", encoding="utf-8")
    _git("add", "unrelated.txt", cwd=wt)
    _git("commit", "-qm", "unrelated local work", cwd=wt)
    unrelated_events = events_capture.read_text(encoding="utf-8")
    unrelated_republish = subprocess.run(
        ["bash", str(kickstart)],
        cwd=wt,
        env={**os.environ},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert unrelated_republish.returncode != 0
    assert "exact receipt-only commit" in unrelated_republish.stderr
    assert events_capture.read_text(encoding="utf-8") == unrelated_events
    assert not args_capture.exists()

    monkeypatch.setenv("REPORT_DIRTY", "1")
    dirty = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--agent",
            "jules",
            "--prompt",
            "Local-only state must fail closed.",
            str(repo),
            "Jules Dirty",
        ],
    )
    assert dirty.exit_code != 0
    assert "requires a clean worktree" in capfd.readouterr().err
    assert not args_capture.exists()
    monkeypatch.delenv("REPORT_DIRTY")

    args_capture.unlink(missing_ok=True)
    remote_head_check_count.unlink(missing_ok=True)
    race_event_count = len(events_capture.read_text(encoding="utf-8").splitlines())
    monkeypatch.setenv("ADVANCE_REMOTE_AFTER_FIRST_CHECK", "1")
    # Launch-environment and pre-admission Jules validation are both read-only. Advance only
    # after the later provider-side validation so this fixture still exercises the reservation
    # race rather than the earlier fail-closed base check.
    monkeypatch.setenv("ADVANCE_REMOTE_AFTER_CHECKS", "3")
    moving_default = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--agent",
            "jules",
            "--prompt",
            "Do not launch if the default branch moves after reservation.",
            str(repo),
            "Jules Moving Default",
        ],
    )
    assert moving_default.exit_code != 0
    race_events = events_capture.read_text(encoding="utf-8").splitlines()[race_event_count:]
    assert race_events == ["push"]
    assert not args_capture.exists()
    monkeypatch.delenv("ADVANCE_REMOTE_AFTER_FIRST_CHECK")
    monkeypatch.delenv("ADVANCE_REMOTE_AFTER_CHECKS")

    timeout_events_before = events_capture.read_text(encoding="utf-8")
    monkeypatch.setenv("JULES_SLEEP", "1")
    monkeypatch.setenv("LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS", "1")
    monkeypatch.setenv("LIMEN_AGENT", "jules")
    rendered_timeout = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--prompt",
            "The provider call must be bounded.",
            str(repo),
            "Jules Timeout",
        ],
    )
    assert rendered_timeout.exit_code == 0, rendered_timeout.output
    monkeypatch.delenv("LIMEN_AGENT")
    timeout_wt = repo / ".worktrees" / "jules-timeout"
    started = time.monotonic()
    timed_out = subprocess.run(
        ["bash", str(timeout_wt / ".limen-workstream" / "kickstart.sh")],
        cwd=timeout_wt,
        env={**os.environ},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert timed_out.returncode != 0
    assert time.monotonic() - started < 4
    monkeypatch.delenv("JULES_SLEEP")
    monkeypatch.delenv("LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS")

    args_capture.unlink(missing_ok=True)
    retried = subprocess.run(
        ["bash", str(timeout_wt / ".limen-workstream" / "kickstart.sh")],
        cwd=timeout_wt,
        env={**os.environ},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert retried.returncode != 0
    assert "unbound Jules launch reservation requires recovery" in retried.stderr
    retry_events = events_capture.read_text(encoding="utf-8")[len(timeout_events_before) :].splitlines()
    assert retry_events == ["push", "jules"]
    assert not args_capture.exists()
    timeout_receipt = json.loads(
        (timeout_wt / "docs/continuations/jules-timeout/workstream.json").read_text(encoding="utf-8")
    )
    assert "provider_run" not in timeout_receipt
    assert _git("log", "-1", "--format=%s", cwd=timeout_wt).stdout.strip().startswith("chore: reserve Jules launch ")

    args_capture.unlink(missing_ok=True)
    monkeypatch.setenv("JULES_FAIL_AFTER_OUTPUT", "1")
    failed_after_output = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--agent",
            "jules",
            "--prompt",
            "Preserve a receipt even when the provider returns nonzero.",
            str(repo),
            "Jules Nonzero Receipt",
        ],
    )
    assert failed_after_output.exit_code != 0
    assert "durable session receipt" in capfd.readouterr().err
    monkeypatch.delenv("JULES_FAIL_AFTER_OUTPUT")
    nonzero_wt = repo / ".worktrees" / "jules-nonzero-receipt"
    nonzero_receipt = json.loads(
        (nonzero_wt / "docs/continuations/jules-nonzero-receipt/workstream.json").read_text(encoding="utf-8")
    )
    assert nonzero_receipt["provider_run"]["id"] == "12345678901234567890"
    assert (
        _git("log", "-1", "--format=%s", cwd=nonzero_wt).stdout.strip()
        == "chore: preserve Jules session 12345678901234567890 receipt"
    )

    args_capture.unlink(missing_ok=True)
    monkeypatch.setenv("FAIL_RECEIPT_COMMIT", "1")
    commit_failed = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--agent",
            "jules",
            "--prompt",
            "A failed receipt commit must fail closed.",
            str(repo),
            "Jules Commit Failure",
        ],
    )
    assert commit_failed.exit_code != 0
    assert "could not publish its receipt" in capfd.readouterr().err
    monkeypatch.delenv("FAIL_RECEIPT_COMMIT")

    commit_wt = repo / ".worktrees" / "jules-commit-failure"
    commit_receipt = commit_wt / "docs" / "continuations" / "jules-commit-failure" / "workstream.json"
    recovered_receipt = json.loads(commit_receipt.read_text(encoding="utf-8"))
    assert recovered_receipt["provider_run"]["id"] == "12345678901234567890"
    args_capture.unlink()
    recovery_events = events_capture.read_text(encoding="utf-8")
    recovered = subprocess.run(
        ["bash", str(commit_wt / ".limen-workstream" / "kickstart.sh")],
        cwd=commit_wt,
        env={**os.environ},
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert recovered.returncode == 0, recovered.stdout + recovered.stderr
    assert "receipt republished" in recovered.stdout
    assert events_capture.read_text(encoding="utf-8") == recovery_events + "push\n"
    assert not args_capture.exists()
    assert _git("status", "--short", cwd=commit_wt).stdout == ""

    monkeypatch.setenv("REMOTE_HEAD", "0" * 40)
    stale = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--agent",
            "jules",
            "--prompt",
            "This stale base must not launch.",
            str(repo),
            "Jules Stale Base",
        ],
    )
    assert stale.exit_code != 0
    assert "current HEAD to equal the live remote default HEAD" in capfd.readouterr().err
    assert not args_capture.exists()


def test_shell_launcher_hands_off_to_generated_kickstart_without_a_tty(tmp_path: Path) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        (
            "#!/usr/bin/env bash\n"
            'printf "%s\\n" "$1" "$2" "$3" "$4" "$5" > "$SESSION_ARGS_CAPTURE"\n'
            'last="${!#}"\n'
            'printf "%s" "$last" > "$SESSION_PROMPT_CAPTURE"\n'
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    args_capture = tmp_path / "args.txt"
    prompt_capture = tmp_path / "prompt.txt"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SESSION_ARGS_CAPTURE": str(args_capture),
        "SESSION_PROMPT_CAPTURE": str(prompt_capture),
    }
    launched = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts" / "start-worktree-session.sh"),
            "--autonomous",
            "--agent",
            "codex",
            "--prompt",
            "Continue from the bounded capsule.",
            str(repo),
            "Agent Launch",
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )

    assert launched.returncode == 0, launched.stdout + launched.stderr
    assert args_capture.read_text(encoding="utf-8").splitlines() == [
        "--ask-for-approval",
        "never",
        "--sandbox",
        "workspace-write",
        "exec",
    ]
    assert "# Continuation capsule: agent-launch" in prompt_capture.read_text(encoding="utf-8")


def test_registry_provider_workstream_publishes_admitted_receipt_before_provider(tmp_path: Path) -> None:
    source_provider = next(provider for provider in census.VENDORS if provider.execution.workstream_adapter == "codex")
    provider = replace(
        source_provider,
        name="fixture-provider-renamed-arbitrarily",
        aliases=(),
        binary="fixture-provider-cli",
    )
    fixture_limen = _fixture_limen_root_with_renamed_provider(tmp_path, source_provider, provider)
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    remote = tmp_path / "origin.git"
    remote.mkdir()
    _git("init", "--bare", "-q", cwd=remote)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    _git("push", "-u", "origin", "main", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    real_git = shutil.which("git")
    assert real_git is not None
    fake_git = fake_bin / "git"
    fake_git.write_text(
        (
            "#!/usr/bin/env bash\n"
            'case "${1:-}" in\n'
            '  fetch) printf "fetch\\n" >> "$GIT_EVENTS_CAPTURE" ;;\n'
            '  push) printf "push\\n" >> "$GIT_EVENTS_CAPTURE" ;;\n'
            '  ls-remote) printf "ls-remote\\n" >> "$GIT_EVENTS_CAPTURE" ;;\n'
            "esac\n"
            'exec "$REAL_GIT" "$@"\n'
        ),
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    fake_provider = fake_bin / provider.binary
    fake_provider.write_text(
        (
            "#!/usr/bin/env bash\n"
            'if [[ "${1:-}" == "debug" && "${2:-}" == "models" ]]; then\n'
            "  printf '%s\\n' "
            '\'{"models":[{"slug":"fixture-sol","supported_reasoning_levels":'
            '[{"effort":"high"}]}]}\'\n'
            "  exit 0\n"
            "fi\n"
            'printf "provider\\n" >> "$EVENTS_CAPTURE"\n'
            'printf "%s\\n%s\\n%s\\n%s\\n%s\\n%s\\n%s\\n" '
            '"${LIMEN_WORKSTREAM_PROVIDER_ACTIVE:-}" '
            '"${LIMEN_WORKSTREAM_PROVIDER_CAPSULE_ID:-}" '
            '"${LIMEN_WORKSTREAM_PROVIDER_WORKTREE:-}" '
            '"${LIMEN_WORKSTREAM_PROVIDER_SESSION_ID:-}" '
            '"${LIMEN_CAPSULE_ID:-}" "${LIMEN_WORKTREE:-}" "${LIMEN_SESSION_ID:-}" '
            '> "$PROVIDER_BINDINGS_CAPTURE"\n'
            'last="${!#}"\n'
            'printf "%s" "$last" > "$SESSION_PROMPT_CAPTURE"\n'
            'receipt="$LIMEN_WORKTREE/docs/continuations/$LIMEN_CAPSULE_ID/workstream.json"\n'
            'before="$(python3 -c \'import os, sys; print(os.stat(sys.argv[1]).st_mtime_ns)\' "$receipt")"\n'
            'bash "$LIMEN_CAPSULE_DIR/kickstart.sh" > "$RECURSION_CAPTURE"\n'
            'after="$(python3 -c \'import os, sys; print(os.stat(sys.argv[1]).st_mtime_ns)\' "$receipt")"\n'
            '[[ "$before" == "$after" ]] || exit 44\n'
            'printf "provider-return\\n" >> "$EVENTS_CAPTURE"\n'
        ),
        encoding="utf-8",
    )
    fake_provider.chmod(0o755)
    stale_id_provider = fake_bin / provider.name
    stale_id_provider.write_text('#!/usr/bin/env bash\n: > "$STALE_PROVIDER_MARKER"\nexit 91\n', encoding="utf-8")
    stale_id_provider.chmod(0o755)
    events = tmp_path / "events.txt"
    git_events = tmp_path / "git-events.txt"
    bindings = tmp_path / "provider-bindings.txt"
    prompt_capture = tmp_path / "prompt.txt"
    recursion_capture = tmp_path / "recursion.txt"
    stale_provider_marker = tmp_path / "stale-provider.txt"
    env = {
        **os.environ,
        "LIMEN_ROOT": str(fixture_limen),
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "EVENTS_CAPTURE": str(events),
        "GIT_EVENTS_CAPTURE": str(git_events),
        "PROVIDER_BINDINGS_CAPTURE": str(bindings),
        "SESSION_PROMPT_CAPTURE": str(prompt_capture),
        "RECURSION_CAPTURE": str(recursion_capture),
        "STALE_PROVIDER_MARKER": str(stale_provider_marker),
        "REAL_GIT": real_git,
    }
    command = [
        "bash",
        str(fixture_limen / "scripts" / "start-worktree-session.sh"),
        "--autonomous",
        "--agent",
        provider.name,
        "--model",
        "fixture-sol",
        "--reasoning-effort",
        "high",
        "--sandbox",
        "workspace-write",
        "--prompt",
        "Publish the admitted receipt before provider launch.",
        str(repo),
        "Registry Admission Publication",
    ]

    launched = subprocess.run(command, env=env, text=True, capture_output=True, timeout=15, check=False)
    assert launched.returncode == 0, launched.stdout + launched.stderr
    wt = repo / ".worktrees" / "registry-admission-publication"
    branch = "work/registry-admission-publication"
    receipt_rel = "docs/continuations/registry-admission-publication/workstream.json"
    first_head = _git("rev-parse", "HEAD", cwd=wt).stdout.strip()
    remote_head = _git("ls-remote", "origin", f"refs/heads/{branch}", cwd=wt).stdout.split()[0]
    assert first_head == remote_head
    assert _git("status", "--short", "--untracked-files=all", cwd=wt).stdout == ""
    assert (
        _git("log", "-1", "--format=%s", cwd=wt).stdout.strip()
        == "docs: publish admitted registry-admission-publication runway"
    )
    assert _git("diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD", cwd=wt).stdout.strip() == receipt_rel
    assert events.read_text(encoding="utf-8").splitlines() == ["provider", "provider-return"]
    assert not stale_provider_marker.exists()
    assert git_events.read_text(encoding="utf-8").splitlines().count("fetch") == 1
    assert git_events.read_text(encoding="utf-8").splitlines().count("push") == 1
    assert git_events.read_text(encoding="utf-8").splitlines().count("ls-remote") == 2
    provider_bindings = bindings.read_text(encoding="utf-8").splitlines()
    assert provider_bindings[0] == "1"
    assert provider_bindings[1] == provider_bindings[4] == "registry-admission-publication"
    assert provider_bindings[2] == provider_bindings[5] == str(wt)
    assert provider_bindings[3] == provider_bindings[6]
    assert provider_bindings[3]
    assert prompt_capture.read_text(encoding="utf-8").startswith(f"{ADMITTED_PROVIDER_INSTRUCTION}\n\n")
    assert recursion_capture.read_text(encoding="utf-8") == (
        "This session is already admitted; continue directly without launching another provider.\n"
    )
    kickstart_text = (wt / ".limen-workstream" / "kickstart.sh").read_text(encoding="utf-8")
    assert f"agent={provider.name}" in kickstart_text
    assert f"agent={source_provider.name}" not in kickstart_text
    assert "launch_adapter=codex" in kickstart_text
    contract = json.loads((wt / ".limen-workstream" / "workstream.json").read_text(encoding="utf-8"))
    assert contract["primary_launch"]["agent"] == "codex"


def test_workstream_rejects_unwritable_linked_git_metadata_before_admission(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text('#!/usr/bin/env bash\n: > "$PROVIDER_MARKER"\n', encoding="utf-8")
    fake_codex.chmod(0o755)
    provider_marker = tmp_path / "provider-started"
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    monkeypatch.setenv("PROVIDER_MARKER", str(provider_marker))

    rendered = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--prompt",
            "Reject unwritable linked Git metadata before admission.",
            str(repo),
            "Git Metadata Preflight",
        ],
    )
    assert rendered.exit_code == 0, rendered.output
    wt = repo / ".worktrees" / "git-metadata-preflight"
    capsule = wt / ".limen-workstream"
    contract = capsule / "workstream.json"
    receipt = wt / "docs/continuations/git-metadata-preflight/workstream.json"
    protected = (contract, receipt)
    original_bytes = {path: path.read_bytes() for path in protected}
    git_dir, common_git_dir = (
        Path(raw)
        for raw in _git(
            "rev-parse",
            "--path-format=absolute",
            "--git-dir",
            "--git-common-dir",
            cwd=wt,
        ).stdout.splitlines()
    )

    for target, diagnostic in (
        (git_dir, "linked worktree Git directory is not writable"),
        (common_git_dir, "common Git directory is not writable"),
    ):
        original_mode = stat.S_IMODE(target.stat().st_mode)
        target.chmod(0o500)
        try:
            rejected = subprocess.run(
                ["bash", str(capsule / "kickstart.sh")],
                cwd=wt,
                env=os.environ.copy(),
                text=True,
                capture_output=True,
                check=False,
            )
        finally:
            target.chmod(original_mode)
        assert rejected.returncode == 2
        assert f"launch-environment error: {diagnostic}" in rejected.stderr
        assert {path: path.read_bytes() for path in protected} == original_bytes
        assert json.loads(contract.read_text(encoding="utf-8"))["runway"]["started_epoch"] is None
        assert not provider_marker.exists()


def test_workstream_rejects_unavailable_github_before_admission(tmp_path: Path) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    remote = tmp_path / "origin.git"
    remote.mkdir()
    _git("init", "--bare", "-q", cwd=remote)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    _git("push", "-u", "origin", "main", cwd=repo)
    _git("remote", "set-url", "origin", "https://github.com/organvm/unavailable-fixture.git", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    real_git = shutil.which("git")
    assert real_git is not None
    fake_git = fake_bin / "git"
    fake_git.write_text(
        (
            "#!/usr/bin/env bash\n"
            'if [[ "${1:-}" == "ls-remote" && "${2:-}" == "origin" ]]; then '
            'printf "remote-output-must-not-escape\\n" >&2; exit 69; fi\n'
            'exec "$REAL_GIT" "$@"\n'
        ),
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    fake_codex = fake_bin / "codex"
    fake_codex.write_text('#!/usr/bin/env bash\n: > "$PROVIDER_MARKER"\n', encoding="utf-8")
    fake_codex.chmod(0o755)
    provider_marker = tmp_path / "provider-started"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "REAL_GIT": real_git,
        "PROVIDER_MARKER": str(provider_marker),
    }

    rejected = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts/start-worktree-session.sh"),
            "--autonomous",
            "--agent",
            "codex",
            "--prompt",
            "Reject an unavailable GitHub remote before admission.",
            str(repo),
            "Unavailable GitHub",
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert rejected.returncode == 2
    assert "launch-environment error: configured remote origin is unavailable" in rejected.stderr
    assert "remote-output-must-not-escape" not in rejected.stdout + rejected.stderr
    wt = repo / ".worktrees" / "unavailable-github"
    contract = wt / ".limen-workstream/workstream.json"
    assert "git ls-remote origin HEAD > /dev/null 2>&1" in (wt / ".limen-workstream/kickstart.sh").read_text(
        encoding="utf-8"
    )
    assert json.loads(contract.read_text(encoding="utf-8"))["runway"]["started_epoch"] is None
    assert not provider_marker.exists()


@pytest.mark.parametrize(
    ("failed_preflight", "diagnostic"),
    [
        ("fetch", "bounded fetch from origin failed"),
        ("status", "bounded Git status failed"),
    ],
)
def test_fetch_and_status_fail_before_admission_without_mutating_contract_or_receipt(
    tmp_path: Path,
    failed_preflight: str,
    diagnostic: str,
) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    remote = tmp_path / "origin.git"
    remote.mkdir()
    _git("init", "--bare", "-q", cwd=remote)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    _git("push", "-u", "origin", "main", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    real_git = shutil.which("git")
    assert real_git is not None
    fake_git = fake_bin / "git"
    fake_git.write_text(
        (
            "#!/usr/bin/env bash\n"
            'if [[ "${FAIL_WORKSTREAM_PREFLIGHT:-}" == "fetch" && "${1:-}" == "fetch" ]]; then '
            'printf "fetch-output-must-not-escape\\n"; exit 71; fi\n'
            'if [[ "${FAIL_WORKSTREAM_PREFLIGHT:-}" == "status" && "$*" == "status --short --branch" ]]; then '
            'printf "status-output-must-not-escape\\n" >&2; exit 72; fi\n'
            'exec "$REAL_GIT" "$@"\n'
        ),
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    fake_codex = fake_bin / "codex"
    fake_codex.write_text('#!/usr/bin/env bash\n: > "$PROVIDER_MARKER"\n', encoding="utf-8")
    fake_codex.chmod(0o755)
    provider_marker = tmp_path / "provider-started"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "REAL_GIT": real_git,
        "LIMEN_AGENT": "codex",
        "PROVIDER_MARKER": str(provider_marker),
    }
    slug = f"preflight-{failed_preflight}-failure"
    rendered = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts" / "start-worktree-session.sh"),
            "--prompt",
            "Preflights must finish before admission.",
            str(repo),
            slug,
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert rendered.returncode == 0, rendered.stdout + rendered.stderr
    wt = repo / ".worktrees" / slug
    capsule = wt / ".limen-workstream"
    contract = capsule / "workstream.json"
    receipt = wt / "docs" / "continuations" / slug / "workstream.json"
    kickstart = capsule / "kickstart.sh"
    protected = (contract, receipt)
    original_bytes = {path: path.read_bytes() for path in protected}
    kickstart_text = kickstart.read_text(encoding="utf-8")
    admission_call = kickstart_text.index("\nrefresh_workstream_runway\n")
    assert (
        kickstart_text.index("git fetch --prune", kickstart_text.index("refresh_workstream_runway()")) < admission_call
    )
    assert kickstart_text.index("git status --short --branch") < admission_call
    assert "git fetch --prune >/dev/null 2>&1" in kickstart_text
    assert "git status --short --branch >/dev/null 2>&1" in kickstart_text

    rejected = subprocess.run(
        ["bash", str(kickstart)],
        cwd=wt,
        env={**env, "FAIL_WORKSTREAM_PREFLIGHT": failed_preflight},
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert rejected.returncode == 2
    assert f"launch-environment error: {diagnostic}" in rejected.stderr
    assert "output-must-not-escape" not in rejected.stdout + rejected.stderr
    assert {path: path.read_bytes() for path in protected} == original_bytes
    assert json.loads(contract.read_text(encoding="utf-8"))["runway"]["started_epoch"] is None
    assert not provider_marker.exists()


def test_codex_workstream_denies_provider_when_admitted_receipt_push_fails(tmp_path: Path) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    remote = tmp_path / "origin.git"
    remote.mkdir()
    _git("init", "--bare", "-q", cwd=remote)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    _git("push", "-u", "origin", "main", cwd=repo)
    pre_receive = remote / "hooks" / "pre-receive"
    pre_receive.write_text(
        (
            "#!/usr/bin/env bash\n"
            "while read -r _old _new ref; do\n"
            '  [[ "$ref" == "refs/heads/work/codex-publication-rejected" ]] && exit 1\n'
            "done\n"
        ),
        encoding="utf-8",
    )
    pre_receive.chmod(0o755)
    _git("config", "core.hooksPath", "hooks", cwd=remote)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        '#!/usr/bin/env bash\nprintf "provider\\n" > "$PROVIDER_MARKER"\n',
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    provider_marker = tmp_path / "provider-started"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "PROVIDER_MARKER": str(provider_marker),
    }

    rejected = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts" / "start-worktree-session.sh"),
            "--autonomous",
            "--agent",
            "codex",
            "--prompt",
            "Fail closed when publication is rejected.",
            str(repo),
            "Codex Publication Rejected",
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert rejected.returncode != 0
    assert "publication was confirmed absent or mismatched" in rejected.stdout + rejected.stderr
    assert not provider_marker.exists()

    pre_receive.unlink()
    wt = repo / ".worktrees" / "codex-publication-rejected"
    retried = subprocess.run(
        ["bash", str(wt / ".limen-workstream" / "kickstart.sh")],
        cwd=wt,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert retried.returncode == 0, retried.stdout + retried.stderr
    assert provider_marker.read_text(encoding="utf-8") == "provider\n"
    local_head = _git("rev-parse", "HEAD", cwd=wt).stdout.strip()
    remote_head = _git(
        "ls-remote",
        "origin",
        "refs/heads/work/codex-publication-rejected",
        cwd=wt,
    ).stdout.split()[0]
    assert local_head == remote_head


def test_explicit_codex_profile_validates_live_catalog_and_launches_exact_argv(tmp_path: Path) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        (
            "#!/usr/bin/env bash\n"
            'if [[ "${1:-}" == "debug" && "${2:-}" == "models" ]]; then\n'
            '  printf "catalog\\n" >> "$CATALOG_CAPTURE"\n'
            "  printf '%s\\n' "
            '\'{"models":[{"slug":"fixture-sol","supported_reasoning_levels":'
            '[{"effort":"high"},{"effort":"ultra-fixture"}]}]}\'\n'
            "  exit 0\n"
            "fi\n"
            'printf "%s\\n" "$1" "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" '
            '> "$SESSION_ARGS_CAPTURE"\n'
            'last="${!#}"\n'
            'printf "%s" "$last" > "$SESSION_PROMPT_CAPTURE"\n'
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    args_capture = tmp_path / "args.txt"
    prompt_capture = tmp_path / "prompt.txt"
    catalog_capture = tmp_path / "catalog.txt"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SESSION_ARGS_CAPTURE": str(args_capture),
        "SESSION_PROMPT_CAPTURE": str(prompt_capture),
        "CATALOG_CAPTURE": str(catalog_capture),
    }
    launched = subprocess.run(
        [
            "bash",
            str(ROOT / "scripts" / "start-worktree-session.sh"),
            "--autonomous",
            "--agent",
            "codex",
            "--model",
            "fixture-sol",
            "--reasoning-effort",
            "ultra-fixture",
            "--sandbox",
            "danger-full-access",
            "--prompt",
            "Continue through the explicit primary profile.",
            str(repo),
            "Explicit Agent Launch",
        ],
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )

    assert launched.returncode == 0, launched.stdout + launched.stderr
    assert catalog_capture.read_text(encoding="utf-8").splitlines() == ["catalog", "catalog"]
    assert args_capture.read_text(encoding="utf-8").splitlines() == [
        "--model",
        "fixture-sol",
        "--config",
        'model_reasoning_effort="ultra-fixture"',
        "--ask-for-approval",
        "never",
        "--sandbox",
        "danger-full-access",
        "exec",
    ]
    assert "# Continuation capsule: explicit-agent-launch" in prompt_capture.read_text(encoding="utf-8")
    contract = json.loads(
        (repo / ".worktrees" / "explicit-agent-launch" / ".limen-workstream" / "workstream.json").read_text(
            encoding="utf-8"
        )
    )
    assert contract["schema"] == "limen.workstream.contract.v2"
    assert contract["primary_launch"] == {
        "agent": "codex",
        "model": "fixture-sol",
        "reasoning_effort": "ultra-fixture",
        "selection": "human_explicit",
    }
    assert contract["authorization"]["sandbox"] == "danger-full-access"
    assert contract["authorization"]["approval_mode"] == "never"

    invalid_profiles = [
        ("Missing Model", "fixture-missing", "ultra-fixture", "danger-full-access", "not present"),
        ("Missing Effort", "fixture-sol", "missing-effort", "danger-full-access", "does not support"),
        ("Invalid Sandbox", "fixture-sol", "ultra-fixture", "host-everything", "sandbox"),
    ]
    for slug, model, effort, sandbox, message in invalid_profiles:
        rejected = subprocess.run(
            [
                "bash",
                str(ROOT / "scripts" / "start-worktree-session.sh"),
                "--model",
                model,
                "--reasoning-effort",
                effort,
                "--sandbox",
                sandbox,
                "--prompt",
                "This invalid profile must fail before render.",
                str(repo),
                slug,
            ],
            env=env,
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
        assert rejected.returncode == 2
        assert message in rejected.stderr
        assert not (repo / ".worktrees" / slug.lower().replace(" ", "-")).exists()


def test_autonomous_workstream_requires_prompt_and_launches_with_dynamic_readme(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        '#!/usr/bin/env bash\nprintf "%s" "$1" > "$SESSION_PROMPT_CAPTURE"\n',
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")
    missing = CliRunner().invoke(main, ["workstream", "--autonomous", str(repo), "No Prompt"])
    assert missing.exit_code == 2
    assert "requires --prompt or --prompt-file" in missing.output
    assert not (repo / ".worktrees" / "no-prompt").exists()

    unbounded = CliRunner().invoke(
        main,
        [
            "workstream",
            "--runway",
            "forever",
            "--prompt",
            "This must fail before worktree creation.",
            str(repo),
            "Unbounded",
        ],
    )
    assert unbounded.exit_code == 2
    assert "invalid workstream contract" in unbounded.output
    assert not (repo / ".worktrees" / "unbounded").exists()

    no_readme = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--no-readme",
            "--prompt",
            "This cannot be durable.",
            str(repo),
            "No Readme",
        ],
    )
    assert no_readme.exit_code == 2
    assert "cannot be combined with --no-readme" in no_readme.output
    assert not (repo / ".worktrees" / "no-readme").exists()

    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--runway",
            "2d",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )

    assert result.exit_code == 0, result.output
    wt = repo / ".worktrees" / "next-epoch"
    capsule = wt / ".limen-workstream"
    readme = capsule / "README.md"
    manifest = capsule / "manifest.md"
    contract = capsule / "workstream.json"
    contract_helper = capsule / "workstream-contract.py"
    intent = capsule / "intent.md"
    runtime = capsule / "runtime.md"
    closeout = capsule / "closeout.md"
    kickstart = capsule / "kickstart.sh"
    identity = capsule / "capsule.identity"
    receipt = wt / "docs" / "continuations" / "next-epoch" / "workstream.json"
    readme_text = readme.read_text(encoding="utf-8")
    manifest_text = manifest.read_text(encoding="utf-8")
    contract_data = json.loads(contract.read_text(encoding="utf-8"))
    intent_text = intent.read_text(encoding="utf-8")
    runtime_text = runtime.read_text(encoding="utf-8")
    kickstart_text = kickstart.read_text(encoding="utf-8")
    receipt_text = receipt.read_text(encoding="utf-8")
    receipt_data = json.loads(receipt_text)
    assert "Derive the next safe leaf from live receipts." in intent_text
    assert "Derive the next safe leaf from live receipts." not in readme_text
    assert "Autonomous: `yes`" in manifest_text
    assert "Agent: `codex`" in manifest_text
    assert "Conduct: `no`" in manifest_text
    assert "Runtime decision contract" in runtime_text
    assert "Reality determines the state" in runtime_text
    assert "Workstream: `substrate`" in manifest_text
    assert contract_data["runway"]["duration_seconds"] == 172_800
    assert contract_data["runway"]["started_epoch"] is None
    assert contract_data["authorization"]["mode"] == "full_non_destructive"
    assert contract_data["authorization"]["approval_mode"] == "never"
    assert contract_data["authorization"]["sandbox"] == "workspace-write"
    assert contract_data["conductor"]["mode"] == "route_bounded_packets"
    for module in (manifest, contract, intent, runtime, closeout):
        assert module.exists()
        assert module.name in readme_text
    assert "workstream_export_context" in kickstart_text
    assert "workstream_launch_native_agent" in kickstart_text
    assert "if [[ -t 0 && -t 1 ]]; then" in kickstart_text
    # The generic lane exec now carries the lane tier pin expansion (s9-lane-tier-pin). With no pin
    # the array is empty and bash expands it to NOTHING, so an unpinned launch is argv-identical to
    # what it was before the pin existed.
    assert 'exec "$binary" "${lane_args[@]+"${lane_args[@]}"}" "$capsule_prompt"' in kickstart_text
    assert "launch_lane_model=" in kickstart_text
    assert "IFS= read -r -d '' capsule_prompt" in kickstart_text
    assert '"$agent" "$registry_binary" "1" "$readme" "$allow_shell_fallback"' in kickstart_text
    assert "run-bounded" in kickstart_text
    assert kickstart_text.count("refresh_workstream_runway") == 3
    assert "workstream-contract.py" in kickstart_text
    assert "## Host-shell-only launch command" in readme_text
    assert "Run this command exactly once from the host shell." in readme_text
    assert ADMITTED_PROVIDER_INSTRUCTION in kickstart_text
    assert "LIMEN_WORKSTREAM_PROVIDER_ACTIVE=1" in kickstart_text
    assert "LIMEN_WORKSTREAM_PROVIDER_CAPSULE_ID" in kickstart_text
    assert "LIMEN_WORKSTREAM_PROVIDER_WORKTREE" in kickstart_text
    assert "LIMEN_WORKSTREAM_PROVIDER_SESSION_ID" in kickstart_text
    assert kickstart_text.index('if [[ "${LIMEN_WORKSTREAM_PROVIDER_ACTIVE:-}" == "1"') < kickstart_text.index(
        'exec 9>> "$capsule_lock"'
    )
    assert "--add-dir" not in kickstart_text
    readme_assignment = next(line for line in kickstart_text.splitlines() if line.startswith("readme="))
    assert shlex.split(readme_assignment) == [f"readme={readme}"]
    identity_data = json.loads(identity.read_text(encoding="utf-8"))
    assert identity_data["schema"] == "limen.workstream.capsule-identity.v2"
    assert len(identity_data["invocation_sha256"]) == 64
    assert set(identity_data["modules"]) == {
        "README.md",
        "manifest.md",
        "workstream.json",
        "workstream-contract.py",
        "intent.md",
        "runtime.md",
        "closeout.md",
        "kickstart.sh",
    }
    assert ".capsule.lock" in kickstart_text
    assert "validate_capsule_receipt" in kickstart_text
    assert receipt_data["schema"] == "limen.workstream.receipt.v1"
    assert receipt_data["slug"] == "next-epoch"
    assert receipt_data["branch"] == "work/next-epoch"
    assert receipt_data["workstream"] == "substrate"
    assert receipt_data["contract"] == contract_data
    private_modules = {
        "README.md": readme,
        "manifest.md": manifest,
        "workstream.json": contract,
        "workstream-contract.py": contract_helper,
        "intent.md": intent,
        "runtime.md": runtime,
        "closeout.md": closeout,
        "kickstart.sh": kickstart,
        "capsule.identity": identity,
    }
    assert receipt_data["private_capsule"] == {
        "content": "redacted",
        "modules": list(private_modules),
    }
    assert "Derive the next safe leaf from live receipts." not in receipt_text
    assert str(repo) not in receipt_text
    assert str(wt) not in receipt_text
    status = _git("status", "--short", "--untracked-files=all", cwd=wt).stdout
    assert ".limen-workstream" not in status
    assert "?? docs/continuations/next-epoch/workstream.json" in status
    ignored_receipt = subprocess.run(
        ["git", "check-ignore", "-q", "--", "docs/continuations/next-epoch/workstream.json"],
        cwd=wt,
        check=False,
    )
    assert ignored_receipt.returncode != 0

    capsule_files = (
        readme,
        manifest,
        contract,
        contract_helper,
        intent,
        runtime,
        closeout,
        kickstart,
        identity,
        receipt,
    )
    bytes_before = {path: path.read_bytes() for path in capsule_files}
    mtimes_before = {path: path.stat().st_mtime_ns for path in capsule_files}
    repeated = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )
    assert repeated.exit_code == 0, repeated.output
    assert "capsule index:" in repeated.output and "(unchanged)" in repeated.output
    assert {path: path.read_bytes() for path in capsule_files} == bytes_before
    assert {path: path.stat().st_mtime_ns for path in capsule_files} == mtimes_before

    _git("branch", "alternate-base", "main", cwd=repo)
    changed_invocations = [
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Changed prompt must become a successor.",
            str(repo),
            "Next Epoch",
        ],
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "different-lane",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
        [
            "workstream",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--from",
            "alternate-base",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--runway",
            "3d",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    ]
    for changed_args in changed_invocations:
        changed = CliRunner().invoke(main, changed_args)
        assert changed.exit_code != 0
        assert "launch identity changed" in changed.output
        assert {path: path.read_bytes() for path in capsule_files} == bytes_before
        assert {path: path.stat().st_mtime_ns for path in capsule_files} == mtimes_before

    render_command = """
source "$1"
render_workstream_capsule \
  "$2" "$3" "$4" "$5" "$6" "$7" "$8" "$9" "${10}" "${11}" "${12}"
"""
    render_args = [
        "bash",
        "-c",
        render_command,
        "capsule-identity-test",
        str(ROOT / "scripts" / "lib" / "workstream-capsule.sh"),
        str(wt),
        str(repo),
        "different-slug",
        "work/next-epoch",
        "substrate",
        "main",
        "1",
        "Derive the next safe leaf from live receipts.",
        str(ROOT / "spec" / "continuation-capsule"),
        "2d",
        str(ROOT / "cli" / "src" / "limen" / "workstream_contract.py"),
    ]
    changed_slug = subprocess.run(render_args, text=True, capture_output=True)
    assert changed_slug.returncode != 0
    assert "launch identity changed" in changed_slug.stderr
    assert {path: path.read_bytes() for path in capsule_files} == bytes_before
    assert {path: path.stat().st_mtime_ns for path in capsule_files} == mtimes_before

    render_args[8] = "work/different-branch"
    render_args[7] = "next-epoch"
    changed_branch = subprocess.run(render_args, text=True, capture_output=True)
    assert changed_branch.returncode != 0
    assert "branch identity changed" in changed_branch.stderr
    assert {path: path.read_bytes() for path in capsule_files} == bytes_before
    assert {path: path.stat().st_mtime_ns for path in capsule_files} == mtimes_before

    render_args[8] = "work/next-epoch"
    changed_contract_source = tmp_path / "changed-workstream-contract.py"
    changed_contract_source.write_bytes(
        (ROOT / "cli" / "src" / "limen" / "workstream_contract.py").read_bytes() + b"\n# changed source\n"
    )
    render_args[15] = str(changed_contract_source)
    changed_source = subprocess.run(render_args, text=True, capture_output=True)
    assert changed_source.returncode != 0
    assert "launch identity changed" in changed_source.stderr
    assert {path: path.read_bytes() for path in capsule_files} == bytes_before
    assert {path: path.stat().st_mtime_ns for path in capsule_files} == mtimes_before
    render_args[15] = str(ROOT / "cli" / "src" / "limen" / "workstream_contract.py")

    changed_spec = tmp_path / "changed-spec"
    shutil.copytree(ROOT / "spec" / "continuation-capsule", changed_spec)
    for source_name in ("runtime-autonomous.md", "closeout.md"):
        source_path = changed_spec / source_name
        original_source = source_path.read_bytes()
        source_path.write_bytes(original_source + b"\nchanged source\n")
        render_args[13] = str(changed_spec)
        changed_source = subprocess.run(render_args, text=True, capture_output=True)
        assert changed_source.returncode != 0
        assert "launch identity changed" in changed_source.stderr
        assert {path: path.read_bytes() for path in capsule_files} == bytes_before
        assert {path: path.stat().st_mtime_ns for path in capsule_files} == mtimes_before
        source_path.write_bytes(original_source)
    render_args[13] = str(ROOT / "spec" / "continuation-capsule")

    _git("add", "docs/continuations/next-epoch/workstream.json", cwd=wt)
    _git("commit", "-qm", "track continuation receipt", cwd=wt)
    tracked_receipt_bytes = receipt.read_bytes()
    tracked_receipt_mtime = receipt.stat().st_mtime_ns
    post_commit_rerender = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )
    assert post_commit_rerender.exit_code == 0, post_commit_rerender.output
    assert "capsule index:" in post_commit_rerender.output and "(unchanged)" in post_commit_rerender.output
    assert receipt.read_bytes() == tracked_receipt_bytes
    assert receipt.stat().st_mtime_ns == tracked_receipt_mtime
    assert _git("status", "--short", cwd=wt).stdout == ""

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        (
            "#!/usr/bin/env bash\n"
            'for ((i = 1; i < $#; i++)); do printf "%s\\n" "${!i}"; done '
            '> "$SESSION_ARGS_CAPTURE"\n'
            'printf "%s:%s:%s:%s:%s" "$LIMEN_WORKSTREAM_REQUESTED" '
            '"$LIMEN_WORKSTREAM_RUNWAY_SECONDS" "$LIMEN_WORKSTREAM_STARTED_EPOCH" '
            '"$LIMEN_WORKSTREAM_DEADLINE_EPOCH" "$LIMEN_WORKSTREAM_REMAINING_SECONDS" '
            '> "$SESSION_RUNWAY_CAPTURE"\n'
            'last="${!#}"\n'
            'printf "%s" "$last" > "$SESSION_PROMPT_CAPTURE"\n'
        ),
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    prompt_capture = tmp_path / "prompt.txt"
    args_capture = tmp_path / "args.txt"
    runway_capture = tmp_path / "runway.txt"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "SESSION_PROMPT_CAPTURE": str(prompt_capture),
        "SESSION_ARGS_CAPTURE": str(args_capture),
        "SESSION_RUNWAY_CAPTURE": str(runway_capture),
    }
    intent.write_text("drifted intent must not launch\n", encoding="utf-8")
    drifted_launch = subprocess.run(["bash", str(kickstart)], cwd=wt, env=env, text=True, capture_output=True)
    assert drifted_launch.returncode != 0
    assert "module bytes changed" in drifted_launch.stderr
    assert not prompt_capture.exists()
    intent.write_bytes(bytes_before[intent])

    fake_python = fake_bin / "python3"
    race_marker = tmp_path / "admission-race.txt"
    fake_python.write_text(
        (
            "#!/usr/bin/env bash\n"
            'if [[ "${2:-}" == "admit-identity" && ! -e "$RACE_MARKER" ]]; then\n'
            '  printf "drifted between verification and admission\\n" > "$RACE_INTENT"\n'
            '  : > "$RACE_MARKER"\n'
            "fi\n"
            'exec "$REAL_PYTHON" "$@"\n'
        ),
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    raced_env = {
        **env,
        "REAL_PYTHON": sys.executable,
        "RACE_MARKER": str(race_marker),
        "RACE_INTENT": str(intent),
    }
    raced_launch = subprocess.run(["bash", str(kickstart)], cwd=wt, env=raced_env, text=True, capture_output=True)
    assert raced_launch.returncode != 0
    assert race_marker.exists()
    assert "module bytes changed" in raced_launch.stderr
    assert contract.read_bytes() == bytes_before[contract]
    assert not prompt_capture.exists()
    intent.write_bytes(bytes_before[intent])
    fake_python.unlink()

    launched = subprocess.run(["bash", str(kickstart)], cwd=wt, env=env, text=True, capture_output=True)
    assert launched.returncode == 0, launched.stderr
    launched_prompt = prompt_capture.read_text(encoding="utf-8")
    assert launched_prompt == f"{ADMITTED_PROVIDER_INSTRUCTION}\n\n{readme_text}"
    assert "intent.md" in launched_prompt
    assert args_capture.read_text(encoding="utf-8").splitlines() == [
        "--ask-for-approval",
        "never",
        "--sandbox",
        "workspace-write",
        "exec",
    ]

    master_fd, slave_fd = pty.openpty()
    try:
        tty_launch = subprocess.run(
            ["bash", str(kickstart)],
            cwd=wt,
            env=env,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
        )
    finally:
        os.close(slave_fd)
        os.close(master_fd)
    assert tty_launch.returncode == 0, tty_launch.stderr
    assert prompt_capture.read_text(encoding="utf-8") == f"{ADMITTED_PROVIDER_INSTRUCTION}\n\n{readme_text}"
    assert args_capture.read_text(encoding="utf-8").splitlines() == [
        "--ask-for-approval",
        "never",
        "--sandbox",
        "workspace-write",
    ]
    admitted = json.loads(contract.read_text(encoding="utf-8"))
    admitted_receipt = json.loads(receipt.read_text(encoding="utf-8"))
    assert admitted["runway"]["started_epoch"] is not None
    assert admitted["runway"]["deadline_epoch"] == admitted["runway"]["started_epoch"] + 172_800
    assert admitted_receipt["contract"] == admitted
    requested, duration_raw, started_raw, deadline_raw, remaining_raw = runway_capture.read_text(
        encoding="utf-8"
    ).split(":")
    duration, started, deadline, remaining = (
        int(duration_raw),
        int(started_raw),
        int(deadline_raw),
        int(remaining_raw),
    )
    assert requested == "2d"
    assert duration == 172_800
    assert started == admitted["runway"]["started_epoch"]
    assert deadline == admitted["runway"]["deadline_epoch"]
    assert 0 < remaining <= duration

    admitted_bytes = contract.read_bytes()
    admitted_mtime = contract.stat().st_mtime_ns
    admitted_receipt_bytes = receipt.read_bytes()
    admitted_receipt_mtime = receipt.stat().st_mtime_ns
    inherited = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )
    assert inherited.exit_code == 0, inherited.output
    assert contract.read_bytes() == admitted_bytes
    assert contract.stat().st_mtime_ns == admitted_mtime
    assert receipt.read_bytes() == admitted_receipt_bytes
    assert receipt.stat().st_mtime_ns == admitted_receipt_mtime

    fake_python.write_text(
        (
            "#!/usr/bin/env bash\n"
            'if [[ "${2:-}" == "admit-identity" ]]; then\n'
            '  count="$(cat "$ADMIT_COUNTER" 2>/dev/null || printf 0)"\n'
            "  count=$((count + 1))\n"
            '  printf "%s" "$count" > "$ADMIT_COUNTER"\n'
            '  if [[ "$count" -le 1 ]]; then now=$((WORKSTREAM_DEADLINE - 1)); else now="$WORKSTREAM_DEADLINE"; fi\n'
            '  exec "$REAL_PYTHON" "$@" --now-epoch "$now"\n'
            "fi\n"
            'exec "$REAL_PYTHON" "$@"\n'
        ),
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    prompt_capture.unlink()
    expiry_env = {
        **env,
        "REAL_PYTHON": sys.executable,
        "ADMIT_COUNTER": str(tmp_path / "admit-count.txt"),
        "WORKSTREAM_DEADLINE": str(admitted["runway"]["deadline_epoch"]),
    }
    expired_at_final_boundary = subprocess.run(
        ["bash", str(kickstart)],
        cwd=wt,
        env=expiry_env,
        text=True,
        capture_output=True,
    )
    assert expired_at_final_boundary.returncode == 3
    assert "workstream contract expired" in expired_at_final_boundary.stderr
    assert not prompt_capture.exists()
    assert (tmp_path / "admit-count.txt").read_text(encoding="utf-8") == "2"
    fake_python.unlink()

    contract.unlink()
    missing_contract = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--workstream",
            "substrate",
            "--prompt",
            "Derive the next safe leaf from live receipts.",
            str(repo),
            "Next Epoch",
        ],
    )
    assert missing_contract.exit_code != 0
    assert "workstream contract is missing" in missing_contract.output
    assert not contract.exists()

    runtime.unlink()
    invalid = subprocess.run(["bash", str(kickstart)], cwd=wt, env=env, text=True, capture_output=True)
    assert invalid.returncode == 2
    assert "invalid capsule: missing or empty module" in invalid.stderr


def test_conduct_registration_precedes_runway_admission(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    events = tmp_path / "events.txt"
    fake_limen = fake_bin / "limen"
    fake_limen.write_text(
        "#!/usr/bin/env bash\n"
        'printf "register\\n" >> "$EVENTS_CAPTURE"\n'
        'if [[ "${REGISTER_CONFLICT:-}" == "1" ]]; then\n'
        '  printf "worktree is already owned by healthy session fixture-session\\n" >&2\n'
        "  exit 75\n"
        "fi\n"
        'exit "${REGISTER_RC:-0}"\n',
        encoding="utf-8",
    )
    fake_limen.chmod(0o755)
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        '#!/usr/bin/env bash\nprintf "provider\\n" >> "$EVENTS_CAPTURE"\nsleep 1\n',
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    fake_ps = fake_bin / "ps"
    fake_ps.write_text('#!/usr/bin/env bash\nprintf "Sat Aug  2 00:00:00 2026\\n"\n', encoding="utf-8")
    fake_ps.chmod(0o755)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CONDUCT_ENV_FILE", str(tmp_path / "missing-limen.env"))
    monkeypatch.delenv("LIMEN_CONDUCT_URL", raising=False)
    monkeypatch.delenv("LIMEN_CONDUCT_TOKEN", raising=False)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    rendered = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--conduct",
            "--prompt",
            "Prove conduct before admission.",
            str(repo),
            "Conduct Ordering",
        ],
    )
    assert rendered.exit_code == 0, rendered.output

    wt = repo / ".worktrees" / "conduct-ordering"
    capsule = wt / ".limen-workstream"
    kickstart = capsule / "kickstart.sh"
    contract = capsule / "workstream.json"
    identity = capsule / "capsule.identity"
    receipt = wt / "docs" / "continuations" / "conduct-ordering" / "workstream.json"
    protected = (contract, identity, receipt)
    bytes_before = {path: path.read_bytes() for path in protected}
    mtimes_before = {path: path.stat().st_mtime_ns for path in protected}

    real_python = shutil.which("python3")
    assert real_python is not None
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "${2:-}" == "admit-identity" ]]; then\n'
        '  printf "admit\\n" >> "$EVENTS_CAPTURE"\n'
        "fi\n"
        'exec "$REAL_PYTHON" "$@"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    launch_env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "EVENTS_CAPTURE": str(events),
        "REAL_PYTHON": real_python,
        "REGISTER_RC": "42",
    }

    rejected = subprocess.run(
        ["bash", str(kickstart)],
        cwd=wt,
        env=launch_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert rejected.returncode == 42
    assert events.read_text(encoding="utf-8").splitlines() == ["register"]
    assert {path: path.read_bytes() for path in protected} == bytes_before
    assert {path: path.stat().st_mtime_ns for path in protected} == mtimes_before
    assert json.loads(contract.read_text(encoding="utf-8"))["runway"]["started_epoch"] is None

    events.write_text("", encoding="utf-8")
    launch_env["REGISTER_RC"] = "0"
    launch_env["REGISTER_CONFLICT"] = "1"
    already_running = subprocess.run(
        ["bash", str(kickstart)],
        cwd=wt,
        env=launch_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert already_running.returncode == 0, already_running.stderr
    assert "This workstream is already running." in already_running.stdout
    assert events.read_text(encoding="utf-8").splitlines() == ["register"]
    assert {path: path.read_bytes() for path in protected} == bytes_before

    events.write_text("", encoding="utf-8")
    launch_env.pop("REGISTER_CONFLICT")
    launched = subprocess.run(
        ["bash", str(kickstart)],
        cwd=wt,
        env=launch_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert launched.returncode == 0, launched.stderr
    assert events.read_text(encoding="utf-8").splitlines() == [
        "register",
        "admit",
        "admit",
        "provider",
    ]
    assert json.loads(contract.read_text(encoding="utf-8"))["runway"]["started_epoch"] is not None


def test_conduct_keepalive_refreshes_without_exposing_credential_to_provider(
    tmp_path: Path,
    monkeypatch,
) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    events = tmp_path / "events.txt"
    registration_attempts = tmp_path / "registration-attempts.txt"
    provider_env = tmp_path / "provider-env.txt"
    fake_limen = fake_bin / "limen"
    fake_limen.write_text(
        "#!/usr/bin/env bash\n"
        'if [[ -z "${LIMEN_CONDUCT_URL:-}" || -z "${LIMEN_CONDUCT_TOKEN:-}" ]]; then exit 41; fi\n'
        'attempts="$(cat "$REGISTRATION_ATTEMPTS_CAPTURE" 2>/dev/null || printf 0)"\n'
        "attempts=$((attempts + 1))\n"
        'printf "%s\\n" "$attempts" > "$REGISTRATION_ATTEMPTS_CAPTURE"\n'
        'printf "register\\n" >> "$EVENTS_CAPTURE"\n'
        'if [[ "$attempts" -eq 2 ]]; then exit 42; fi\n',
        encoding="utf-8",
    )
    fake_limen.chmod(0o755)
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        "#!/usr/bin/env bash\n"
        'printf "provider\\n" >> "$EVENTS_CAPTURE"\n'
        'printf "credential=%s\\nkeepalive=%s\\nunrelated=%s\\n" '
        '"${LIMEN_CONDUCT_TOKEN-unset}" "${LIMEN_CONDUCT_KEEPALIVE_PID:-}" '
        '"${UNRELATED_PRIVATE_VALUE-unset}" > "$PROVIDER_ENV_CAPTURE"\n'
        "sleep 5\n",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    private_cache = tmp_path / "limen.env"
    private_cache.write_text(
        "export LIMEN_CONDUCT_URL=https://broker.example.invalid\n"
        "export LIMEN_CONDUCT_TOKEN=fixture-only\n"
        "export UNRELATED_PRIVATE_VALUE=must-not-be-imported\n",
        encoding="utf-8",
    )
    private_cache.chmod(0o600)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    monkeypatch.setenv("LIMEN_AGENT", "codex")
    monkeypatch.setenv("LIMEN_CONDUCT_ENV_FILE", str(private_cache))
    monkeypatch.delenv("LIMEN_CONDUCT_URL", raising=False)
    monkeypatch.delenv("LIMEN_CONDUCT_TOKEN", raising=False)
    monkeypatch.delenv("UNRELATED_PRIVATE_VALUE", raising=False)
    monkeypatch.setenv("PATH", f"{fake_bin}:{os.environ['PATH']}")

    rendered = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--conduct",
            "--prompt",
            "Keep the protected conductor live for the provider epoch.",
            str(repo),
            "Conduct Keepalive",
        ],
    )
    assert rendered.exit_code == 0, rendered.output

    wt = repo / ".worktrees" / "conduct-keepalive"
    capsule = wt / ".limen-workstream"
    launch_env = {
        **os.environ,
        "EVENTS_CAPTURE": str(events),
        "REGISTRATION_ATTEMPTS_CAPTURE": str(registration_attempts),
        "PROVIDER_ENV_CAPTURE": str(provider_env),
        "LIMEN_CONDUCT_KEEPALIVE_SECONDS": "1",
        "LIMEN_CONDUCT_KEEPALIVE_RETRY_SECONDS": "1",
        "LIMEN_CONDUCT_KEEPALIVE_POLL_SECONDS": "1",
    }
    launched = subprocess.run(
        ["bash", str(capsule / "kickstart.sh")],
        cwd=wt,
        env=launch_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert launched.returncode == 0, launched.stderr
    observed_events = events.read_text(encoding="utf-8").splitlines()
    assert observed_events[0] == "register"
    assert observed_events.count("provider") == 1
    assert observed_events.count("register") >= 4
    assert int(registration_attempts.read_text(encoding="utf-8")) >= 4
    provider_values = dict(line.split("=", 1) for line in provider_env.read_text(encoding="utf-8").splitlines())
    assert provider_values["credential"] == "unset"
    assert provider_values["keepalive"].isdigit()
    assert provider_values["unrelated"] == "unset"

    status_path = capsule / "conduct-keepalive.json"
    deadline = time.monotonic() + 5
    status = {}
    while time.monotonic() < deadline:
        if status_path.exists():
            status = json.loads(status_path.read_text(encoding="utf-8"))
            if status.get("state") == "stopped":
                break
        time.sleep(0.1)
    assert status["schema"] == "limen.workstream.conduct-keepalive.v1"
    assert status["state"] == "stopped"
    assert status["refresh_count"] >= 3
    assert status["last_failure_epoch"] is not None
    assert status["last_success_epoch"] >= status["last_failure_epoch"]
    assert status["detail"] == "provider process exited or changed identity"
    assert status_path.stat().st_mode & 0o777 == 0o600
    assert ".limen-workstream" not in _git("status", "--short", cwd=wt).stdout

    status_path.unlink()
    outside_status = tmp_path / "outside-status.json"
    status_path.symlink_to(outside_status)
    denied = subprocess.run(
        ["bash", str(capsule / "kickstart.sh")],
        cwd=wt,
        env=launch_env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert denied.returncode != 0
    assert "keepalive did not acknowledge" in denied.stderr
    assert events.read_text(encoding="utf-8").splitlines().count("provider") == 1
    assert not outside_status.exists()


def test_kickstart_wrapper_imports_only_the_broker_pair(tmp_path: Path) -> None:
    cache = tmp_path / "limen.env"
    cache.write_text(
        "export LIMEN_CONDUCT_URL=https://broker.example.invalid\n"
        "export LIMEN_CONDUCT_TOKEN=fixture-only\n"  # allow-secret: inert regression fixture
        "export UNRELATED_PRIVATE_VALUE=must-not-be-imported\n",
        encoding="utf-8",
    )
    cache.chmod(0o600)
    capture = tmp_path / "capture.txt"
    kickstart = tmp_path / "kickstart.sh"
    kickstart.write_text(
        "#!/usr/bin/env bash\n"
        'printf "url=%s\\ntoken=%s\\nunrelated=%s\\n" '
        '"${LIMEN_CONDUCT_URL-unset}" "${LIMEN_CONDUCT_TOKEN-unset}" '
        '"${UNRELATED_PRIVATE_VALUE-unset}" > "$CAPTURE"\n',
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "CAPTURE": str(capture),
        "LIMEN_CONDUCT_ENV_FILE": str(cache),
    }
    env.pop("LIMEN_CONDUCT_URL", None)
    env.pop("LIMEN_CONDUCT_TOKEN", None)
    env.pop("UNRELATED_PRIVATE_VALUE", None)

    launched = subprocess.run(
        ["bash", str(ROOT / "scripts" / "run-workstream-kickstart.sh"), str(kickstart)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert launched.returncode == 0, launched.stderr
    assert capture.read_text(encoding="utf-8").splitlines() == [
        "url=https://broker.example.invalid",
        "token=fixture-only",  # allow-secret: inert regression fixture
        "unrelated=unset",
    ]


def test_kickstart_wrapper_noops_for_a_fresh_live_capsule_session(tmp_path: Path) -> None:
    capsule = tmp_path / ".limen-workstream"
    capsule.mkdir()
    capture = tmp_path / "provider-started"
    now = int(time.time())
    holder = subprocess.Popen(["sleep", "30"])
    try:
        (capsule / "conduct-keepalive.json").write_text(
            json.dumps(
                {
                    "schema": "limen.workstream.conduct-keepalive.v1",
                    "session_id": "fixture-active-session",
                    "state": "active",
                    "target_pid": holder.pid,
                    "keepalive_pid": holder.pid,
                    "deadline_epoch": now + 600,
                    "observed_epoch": now,
                }
            ),
            encoding="utf-8",
        )
        kickstart = capsule / "kickstart.sh"
        kickstart.write_text('#!/usr/bin/env bash\n: > "$CAPTURE"\n', encoding="utf-8")

        launched = subprocess.run(
            ["bash", str(ROOT / "scripts" / "run-workstream-kickstart.sh"), str(kickstart)],
            env={**os.environ, "CAPTURE": str(capture)},
            text=True,
            capture_output=True,
            check=False,
        )

        assert launched.returncode == 0, launched.stderr
        assert launched.stdout.strip() == (
            "This workstream is already running. Continue in its existing session; no second process was started."
        )
        assert not capture.exists()
    finally:
        holder.terminate()
        holder.wait(timeout=2)


def test_kickstart_wrapper_does_not_mask_a_stale_keepalive_receipt(tmp_path: Path) -> None:
    capsule = tmp_path / ".limen-workstream"
    capsule.mkdir()
    capture = tmp_path / "provider-started"
    now = int(time.time())
    (capsule / "conduct-keepalive.json").write_text(
        json.dumps(
            {
                "schema": "limen.workstream.conduct-keepalive.v1",
                "session_id": "fixture-stale-session",
                "state": "active",
                "target_pid": os.getpid(),
                "keepalive_pid": os.getppid(),
                "deadline_epoch": now + 600,
                "observed_epoch": now - 361,
            }
        ),
        encoding="utf-8",
    )
    kickstart = capsule / "kickstart.sh"
    kickstart.write_text('#!/usr/bin/env bash\n: > "$CAPTURE"\n', encoding="utf-8")

    launched = subprocess.run(
        ["bash", str(ROOT / "scripts" / "run-workstream-kickstart.sh"), str(kickstart)],
        env={**os.environ, "CAPTURE": str(capture)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert launched.returncode == 0, launched.stderr
    assert launched.stdout == ""
    assert capture.exists()


def test_workstream_refuses_an_ignored_tracked_receipt_path(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    (repo / ".gitignore").write_text("docs/continuations/\n", encoding="utf-8")
    _git("add", "README.md", ".gitignore", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))
    result = CliRunner().invoke(
        main,
        [
            "workstream",
            "--prompt",
            "Keep the receipt durable.",
            str(repo),
            "Ignored Receipt",
        ],
    )

    assert result.exit_code != 0
    assert "capsule receipt path is ignored: docs/continuations/ignored-receipt/workstream.json" in result.output


def test_workstream_rejects_symlinked_private_root_before_writing_prompt(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)
    monkeypatch.setenv("LIMEN_ROOT", str(ROOT))

    created = CliRunner().invoke(main, ["workstream", "--no-readme", str(repo), "Symlink Root"])
    assert created.exit_code == 0, created.output
    wt = repo / ".worktrees" / "symlink-root"
    tracked_target = wt / "tracked-capsule-leak"
    tracked_target.mkdir()
    (wt / ".limen-workstream").symlink_to(tracked_target, target_is_directory=True)

    rejected = CliRunner().invoke(
        main,
        [
            "workstream",
            "--prompt",
            "private prompt must never cross the symlink",
            str(repo),
            "Symlink Root",
        ],
    )

    assert rejected.exit_code != 0
    assert "capsule root must be a real directory" in rejected.output
    assert list(tracked_target.iterdir()) == []


def test_capsule_advisory_lock_releases_when_its_shell_owner_is_killed(tmp_path: Path) -> None:
    lock_path = tmp_path / ".capsule.lock"
    ready_path = tmp_path / "ready"
    holder = subprocess.Popen(
        [
            "/bin/bash",
            "-c",
            (
                'exec 9>> "$1"; '
                "python3 -c 'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)' 9>&9; "
                ': > "$2"; '
                "sleep 30 9>&-"
            ),
            "capsule-lock-owner",
            str(lock_path),
            str(ready_path),
        ]
    )
    try:
        deadline = time.monotonic() + 5
        while not ready_path.exists() and holder.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready_path.exists()
        holder.kill()
        holder.wait(timeout=2)

        probe = subprocess.run(
            [
                "/bin/bash",
                "-c",
                ("exec 9>> \"$1\"; python3 -c 'import fcntl; fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)' 9>&9"),
                "capsule-lock-probe",
                str(lock_path),
            ],
            check=False,
        )
        assert probe.returncode == 0
    finally:
        if holder.poll() is None:
            holder.kill()
            holder.wait(timeout=2)


def test_concurrent_capsule_render_keeps_partial_kickstart_unlaunchable(tmp_path: Path) -> None:
    repo = tmp_path / "demo-repo"
    repo.mkdir()
    _git("init", "-q", "-b", "main", cwd=repo)
    _git("config", "user.email", "test@example.invalid", cwd=repo)
    _git("config", "user.name", "Test User", cwd=repo)
    (repo / "README.md").write_text("demo\n", encoding="utf-8")
    _git("add", "README.md", cwd=repo)
    _git("commit", "-qm", "init", cwd=repo)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_python = fake_bin / "python3"
    fake_python.write_text(
        (
            "#!/usr/bin/env bash\n"
            'if [[ "${2:-}" == "sync-receipt" && ! -e "$SYNC_ENTERED" ]]; then\n'
            '  : > "$SYNC_ENTERED"\n'
            '  while [[ ! -e "$SYNC_RELEASE" ]]; do sleep 0.01; done\n'
            "fi\n"
            'if [[ "${2:-}" == "admit-identity" && -n "${ADMIT_ENTERED:-}" && ! -e "$ADMIT_ENTERED" ]]; then\n'
            '  : > "$ADMIT_ENTERED"\n'
            '  while [[ ! -e "$ADMIT_RELEASE" ]]; do sleep 0.01; done\n'
            "fi\n"
            'exec "$REAL_PYTHON" "$@"\n'
        ),
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    sync_entered = tmp_path / "sync-entered"
    sync_release = tmp_path / "sync-release"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "REAL_PYTHON": sys.executable,
        "SYNC_ENTERED": str(sync_entered),
        "SYNC_RELEASE": str(sync_release),
    }
    command = [
        "bash",
        str(ROOT / "scripts" / "start-worktree-session.sh"),
        "--autonomous",
        "--prompt",
        "Render one coherent capsule.",
        str(repo),
        "Race Capsule",
    ]
    rendering = subprocess.Popen(command, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    render_stdout = ""
    render_stderr = ""
    try:
        deadline = time.monotonic() + 5
        while not sync_entered.exists() and rendering.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert sync_entered.exists(), rendering.stderr.read() if rendering.stderr else ""

        wt = repo / ".worktrees" / "race-capsule"
        capsule = wt / ".limen-workstream"
        kickstart = capsule / "kickstart.sh"
        identity = capsule / "capsule.identity"
        receipt = wt / "docs" / "continuations" / "race-capsule" / "workstream.json"
        assert kickstart.exists()
        assert (capsule / ".capsule.lock").is_file()
        assert identity.exists()
        assert not receipt.exists()

        blocked_launch = subprocess.run(
            ["bash", str(kickstart)],
            cwd=wt,
            env=env,
            text=True,
            capture_output=True,
        )
        assert blocked_launch.returncode == 2
        assert "holds the capsule lock" in blocked_launch.stderr

        concurrent_changed = subprocess.run(
            [
                "bash",
                str(ROOT / "scripts" / "start-worktree-session.sh"),
                "--autonomous",
                "--prompt",
                "A different identity must not interleave.",
                str(repo),
                "Race Capsule",
            ],
            env=env,
            text=True,
            capture_output=True,
        )
        assert concurrent_changed.returncode != 0
        assert "capsule is busy" in concurrent_changed.stderr
        assert identity.exists()
        assert not receipt.exists()
    finally:
        sync_release.write_text("release\n", encoding="utf-8")
        try:
            render_stdout, render_stderr = rendering.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            rendering.kill()
            render_stdout, render_stderr = rendering.communicate()

    assert rendering.returncode == 0, render_stdout + render_stderr
    wt = repo / ".worktrees" / "race-capsule"
    capsule = wt / ".limen-workstream"
    kickstart = capsule / "kickstart.sh"
    assert (capsule / "capsule.identity").exists()
    assert (wt / "docs" / "continuations" / "race-capsule" / "workstream.json").exists()
    assert (capsule / ".capsule.lock").is_file()

    launched_capture = tmp_path / "launched"
    fake_codex = fake_bin / "codex"
    fake_codex.write_text(
        '#!/usr/bin/env bash\n: > "$LAUNCHED_CAPTURE"\n',
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    admit_entered = tmp_path / "admit-entered"
    admit_release = tmp_path / "admit-release"
    launch_env = {
        **env,
        "LAUNCHED_CAPTURE": str(launched_capture),
        "ADMIT_ENTERED": str(admit_entered),
        "ADMIT_RELEASE": str(admit_release),
    }
    launching = subprocess.Popen(
        ["bash", str(kickstart)],
        cwd=wt,
        env=launch_env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    launch_stdout = ""
    launch_stderr = ""
    try:
        deadline = time.monotonic() + 5
        while not admit_entered.exists() and launching.poll() is None and time.monotonic() < deadline:
            time.sleep(0.01)
        assert admit_entered.exists(), launching.stderr.read() if launching.stderr else ""
        assert (capsule / ".capsule.lock").is_file()

        render_during_launch = subprocess.run(
            [
                "bash",
                str(ROOT / "scripts" / "start-worktree-session.sh"),
                "--autonomous",
                "--prompt",
                "A launch must exclude a concurrent rerender.",
                str(repo),
                "Race Capsule",
            ],
            env=env,
            text=True,
            capture_output=True,
        )
        assert render_during_launch.returncode != 0
        assert "capsule is busy" in render_during_launch.stderr
        assert not launched_capture.exists()
    finally:
        admit_release.write_text("release\n", encoding="utf-8")
        try:
            launch_stdout, launch_stderr = launching.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            launching.kill()
            launch_stdout, launch_stderr = launching.communicate()

    assert launching.returncode == 0, launch_stdout + launch_stderr
    assert launched_capture.exists()
    assert (capsule / ".capsule.lock").is_file()
