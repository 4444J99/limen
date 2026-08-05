from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"fixture Git command failed: {result.stderr}")
    return result.stdout.strip()


def _generated_emit_function(tmp_path: Path, relay_id: str) -> str:
    kickstart = tmp_path / "kickstart.sh"
    kickstart.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

cd "$PWD"

publish_receipt() {
  workstream_publish_admitted_receipt "$receipt" "$expected_branch" "$expected_slug"
  exec 9>&-
}

agent=codex
registry_binary=/bin/true
workstream_launch_native_agent   "$agent" "$registry_binary"
""",
        encoding="utf-8",
    )
    transformed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "lib" / "campaign-relay-control.py"),
            str(kickstart),
            relay_id,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert transformed.returncode == 0, transformed.stderr
    source = kickstart.read_text(encoding="utf-8")
    start = source.index("workstream_campaign_relay_emit_published() {")
    end_marker = "\n}\n\nworkstream_register_conduct_session() {"
    end = source.index(end_marker, start) + 3
    return source[start:end]


@pytest.mark.parametrize("push_mode", ["accepted", "mismatch"])
def test_ambiguous_capsule_push_reconciles_only_the_intended_commit(
    tmp_path: Path,
    push_mode: str,
) -> None:
    real_git = shutil.which("git")
    assert real_git is not None
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    binary_dir = tmp_path / "bin"
    capsule_dir = tmp_path / "capsule"
    repo.mkdir()
    binary_dir.mkdir()
    capsule_dir.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "relay-refs@example.invalid")
    _git(repo, "config", "user.name", "Relay Ref Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "base")
    receipt = repo / "docs" / "continuations" / "successor" / "workstream.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}\n", encoding="utf-8")
    _git(repo, "add", str(receipt.relative_to(repo)))
    _git(repo, "commit", "-qm", "publish successor receipt")
    intended_commit = _git(repo, "rev-parse", "HEAD")
    wrong_commit = _git(repo, "rev-parse", "HEAD^")
    receipt_ref = f"refs/heads/limen-relay/capsule/{intended_commit}"
    _git(remote.parent, "init", "--bare", "-q", str(remote))
    _git(repo, "remote", "add", "origin", str(remote))

    git_wrapper = binary_dir / "git"
    git_wrapper.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "push" && "${2:-}" == "origin" \
  && "${3:-}" == *":refs/heads/limen-relay/capsule/"* ]]; then
  refspec="$3"
  intended="${refspec%%:*}"
  remote_ref="${refspec#*:}"
  if [[ "$CAPSULE_PUSH_MODE" == "accepted" ]]; then
    "$REAL_GIT" push origin "$intended:$remote_ref" >/dev/null 2>&1
  else
    wrong="$("$REAL_GIT" rev-parse "$intended^")"
    "$REAL_GIT" push origin "$wrong:$remote_ref" >/dev/null 2>&1
  fi
  exit 1
fi
exec "$REAL_GIT" "$@"
""",
        encoding="utf-8",
    )
    git_wrapper.chmod(0o755)
    contract_helper = capsule_dir / "workstream-contract.py"
    contract_helper.write_text(
        """#!/usr/bin/env python3
import subprocess
import sys

separator = sys.argv.index("--")
raise SystemExit(subprocess.run(sys.argv[separator + 1 :], check=False).returncode)
""",
        encoding="utf-8",
    )
    control_path = tmp_path / "control.jsonl"
    ack_path = tmp_path / "ack"
    ack_path.write_bytes(b"launch\n")
    relay_id = "a" * 64
    emit_function = _generated_emit_function(tmp_path, relay_id)
    harness = tmp_path / "harness.sh"
    harness.write_text(
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"{emit_function}\n"
            'expected_branch="work/successor"\n'
            f"export LIMEN_WORKTREE={shlex.quote(str(repo))}\n"
            f"export LIMEN_CAPSULE_DIR={shlex.quote(str(capsule_dir))}\n"
            "export LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS=5\n"
            "export LIMEN_CAMPAIGN_RELAY_CONTROL_FD=3\n"
            "export LIMEN_CAMPAIGN_RELAY_ACK_FD=4\n"
            f"exec 3>{shlex.quote(str(control_path))}\n"
            f"exec 4<{shlex.quote(str(ack_path))}\n"
            f"cd {shlex.quote(str(repo))}\n"
            f"workstream_campaign_relay_emit_published {shlex.quote(str(receipt))}\n"
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    env = {
        **os.environ,
        "CAPSULE_PUSH_MODE": push_mode,
        "PATH": f"{binary_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "REAL_GIT": real_git,
    }

    completed = subprocess.run(
        [str(harness)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    remote_head = _git(repo, "ls-remote", "origin", receipt_ref, env=env).split("\t", 1)[0]

    if push_mode == "accepted":
        assert completed.returncode == 0, completed.stderr
        assert remote_head == intended_commit
        event = json.loads(control_path.read_text(encoding="utf-8"))
        assert event["stage"] == "published"
        assert event["commit"] == intended_commit
        assert event["receipt_ref"] == receipt_ref
    else:
        assert completed.returncode == 2
        assert "immutable receipt-ref publication failed" in completed.stderr
        assert remote_head == wrong_commit
        assert control_path.read_bytes() == b""


@pytest.mark.parametrize("push_mode", ["accepted", "mismatch", "unavailable"])
def test_ambiguous_topic_push_reconciles_the_exact_branch_ref(
    tmp_path: Path,
    push_mode: str,
) -> None:
    real_git = shutil.which("git")
    assert real_git is not None
    repo = tmp_path / "repo"
    remote = tmp_path / "origin.git"
    binary_dir = tmp_path / "bin"
    capsule_dir = tmp_path / "capsule"
    push_seen = tmp_path / "push-seen"
    repo.mkdir()
    binary_dir.mkdir()
    capsule_dir.mkdir()
    _git(repo, "init", "-q", "-b", "work/successor")
    _git(repo, "config", "user.email", "relay-topic@example.invalid")
    _git(repo, "config", "user.name", "Relay Topic Test")
    _git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "-qm", "base")
    base_commit = _git(repo, "rev-parse", "HEAD")
    _git(remote.parent, "init", "--bare", "-q", str(remote))
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "work/successor")
    receipt = repo / "docs" / "continuations" / "successor" / "workstream.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text("{}\n", encoding="utf-8")

    git_wrapper = binary_dir / "git"
    git_wrapper.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "push" ]]; then
  refspec=""
  for argument in "$@"; do
    case "$argument" in
      *:refs/heads/work/successor) refspec="$argument" ;;
    esac
  done
  if [[ -n "$refspec" ]]; then
    intended="${refspec%%:*}"
    remote_ref="${refspec#*:}"
    : > "$PUSH_SEEN"
    if [[ "$TOPIC_PUSH_MODE" == "accepted" ]]; then
      "$REAL_GIT" push origin "$intended:$remote_ref" >/dev/null 2>&1
    elif [[ "$TOPIC_PUSH_MODE" == "mismatch" ]]; then
      wrong="$("$REAL_GIT" rev-parse "$intended^")"
      "$REAL_GIT" push origin "$wrong:$remote_ref" >/dev/null 2>&1
    fi
    exit 1
  fi
fi
if [[ "${1:-}" == "ls-remote" && "$TOPIC_PUSH_MODE" == "unavailable" && -f "$PUSH_SEEN" ]]; then
  exit 1
fi
exec "$REAL_GIT" "$@"
""",
        encoding="utf-8",
    )
    git_wrapper.chmod(0o755)
    contract_helper = capsule_dir / "workstream-contract.py"
    contract_helper.write_text(
        """#!/usr/bin/env python3
import subprocess
import sys

separator = sys.argv.index("--")
raise SystemExit(subprocess.run(sys.argv[separator + 1 :], check=False).returncode)
""",
        encoding="utf-8",
    )
    harness = tmp_path / "topic-harness.sh"
    harness.write_text(
        (
            "#!/usr/bin/env bash\n"
            "set -euo pipefail\n"
            f"source {shlex.quote(str(ROOT / 'scripts' / 'lib' / 'workstream-capsule.sh'))}\n"
            f"export LIMEN_WORKTREE={shlex.quote(str(repo))}\n"
            f"export LIMEN_CAPSULE_DIR={shlex.quote(str(capsule_dir))}\n"
            "export LIMEN_WORKSTREAM_PREFLIGHT_TIMEOUT_SECONDS=5\n"
            f"cd {shlex.quote(str(repo))}\n"
            "workstream_publish_admitted_receipt "
            f"{shlex.quote(str(receipt))} work/successor successor\n"
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{binary_dir}{os.pathsep}{os.environ.get('PATH', '')}",
        "PUSH_SEEN": str(push_seen),
        "REAL_GIT": real_git,
        "TOPIC_PUSH_MODE": push_mode,
    }

    completed = subprocess.run(
        [str(harness)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=15,
    )
    publication_commit = _git(repo, "rev-parse", "HEAD")
    remote_row = _git(repo, "ls-remote", "origin", "refs/heads/work/successor")
    remote_head = remote_row.split("\t", 1)[0]

    if push_mode == "accepted":
        assert completed.returncode == 0, completed.stderr
        assert remote_head == publication_commit
        assert "admitted workstream receipt published" in completed.stdout
    elif push_mode == "mismatch":
        assert completed.returncode == 2
        assert remote_head == base_commit
        assert "confirmed absent or mismatched" in completed.stderr
    else:
        assert completed.returncode == 2
        assert remote_head == base_commit
        assert "outcome is uncertain" in completed.stderr
