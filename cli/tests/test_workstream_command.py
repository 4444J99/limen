from __future__ import annotations

import json
import os
import pty
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from click.testing import CliRunner

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen.cli import main


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(["git", *args], cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed\n{result.stdout}\n{result.stderr}")
    return result


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
            'if [[ "${JULES_SLEEP:-0}" == "1" ]]; then sleep 5; fi\n'
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
            '    if [[ "$check_count" -gt 1 ]]; then resolved_head="$ADVANCED_REMOTE_HEAD"; fi\n'
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
    assert args[5].startswith("Do NOT ask for feedback or approval.")
    assert "Ship the exact bounded packet." in args[5]
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
    assert 'if [[ "$agent" != "jules" ]]; then\n  exec 9>&-\nfi' in kickstart_text

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

    timeout_events_before = events_capture.read_text(encoding="utf-8")
    monkeypatch.setenv("JULES_SLEEP", "1")
    monkeypatch.setenv("LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS", "1")
    started = time.monotonic()
    timed_out = CliRunner().invoke(
        main,
        [
            "workstream",
            "--autonomous",
            "--agent",
            "jules",
            "--prompt",
            "The provider call must be bounded.",
            str(repo),
            "Jules Timeout",
        ],
    )
    assert timed_out.exit_code != 0
    assert time.monotonic() - started < 4
    monkeypatch.delenv("JULES_SLEEP")
    monkeypatch.delenv("LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS")

    timeout_wt = repo / ".worktrees" / "jules-timeout"
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
    assert 'exec "$binary" "$capsule_prompt"' in kickstart_text
    assert "IFS= read -r -d '' capsule_prompt" in kickstart_text
    assert '"$agent" "$registry_binary" "1" "$readme" "$allow_shell_fallback"' in kickstart_text
    assert "run-bounded" in kickstart_text
    assert kickstart_text.count("refresh_workstream_runway") == 3
    assert "workstream-contract.py" in kickstart_text
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
    assert launched_prompt == readme_text
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
    assert prompt_capture.read_text(encoding="utf-8") == readme_text
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
