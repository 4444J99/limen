"""Regression tests for the zero-unauthorized-writer source predicate."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "task_writer_audit",
    ROOT / "scripts" / "task-writer-audit.py",
)
assert SPEC and SPEC.loader
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def test_python_audit_is_scope_aware_for_unrelated_path_writes():
    rows = audit.audit_python_source(
        """
from pathlib import Path
TASKS = Path("tasks.yaml")

def load_limits():
    path = Path("logs/usage-limits.json")
    path.write_text("{}")
""",
        "scripts/usage.py",
    )

    assert rows == []


def test_python_audit_rejects_direct_yaml_and_git_board_sync():
    rows = audit.audit_python_source(
        """
import subprocess
from limen.io import save_limen_file

def save_board_sync(board_path, board):
    subprocess.run(["git", "stash", "push"])
    save_limen_file(board_path, board)
""",
        "mcp/src/example.py",
    )

    assert {(row["kind"], row["call"]) for row in rows} == {
        ("board-git-sync", "subprocess.run"),
        ("direct-yaml-writer", "save_limen_file"),
    }


def test_python_audit_rejects_path_open_write_mode():
    rows = audit.audit_python_source(
        """
from pathlib import Path
import yaml

def save(board_path, payload):
    with board_path.open("w") as stream:
        yaml.safe_dump(payload, stream)
""",
        "scripts/claim-task.py",
    )

    assert [(row["kind"], row["call"]) for row in rows] == [
        ("direct-yaml-writer", "board_path.open"),
    ]


def test_shell_audit_rejects_board_copy_restore_and_allows_exact_sandbox_marker():
    rows = audit.audit_shell_source(
        """
cp tasks.yaml "$TMP"
git checkout -- tasks.yaml
cp "$TMP" tasks.yaml
cp tasks.yaml "$VERIFY_ROOT/tasks.yaml" # task-writer-audit: allow-derived-sandbox
git diff -- tasks.yaml
""",
        "scripts/sync-release.sh",
    )

    assert [row["line"] for row in rows] == [2, 3, 4]


def test_javascript_audit_rejects_legacy_save_board_definition_and_call():
    rows = audit.audit_javascript_source(
        """
async function saveBoard(env, data, sha) {
  return githubPut(env, data, sha);
}
await saveBoard(env, board, sha);
""",
        "web/worker/src/index.js",
    )

    assert [(row["line"], row["call"]) for row in rows] == [
        (2, "function saveBoard"),
        (5, "saveBoard"),
    ]


def test_instruction_audit_rejects_direct_write_and_git_guidance():
    rows = audit.audit_instruction_text(
        """
Workers may edit tasks.yaml directly.
Run git add tasks.yaml and push it after the task.
Inspection is read-only.
""",
        "AGENTS.md",
    )

    assert [row["kind"] for row in rows] == [
        "direct-board-write-guidance",
        "direct-board-git-guidance",
    ]


def test_generated_receipts_are_deterministic(tmp_path):
    payload = {
        "schema_version": "limen.task_writer_audit.v2",
        "authorized_projection_writers": [
            {"path": "cli/src/limen/io.py", "role": "byte primitive"},
        ],
        "unauthorized_writer_count": 0,
        "unauthorized_writers": [],
    }
    (tmp_path / "scripts").mkdir()
    (tmp_path / "docs").mkdir()

    audit.write_receipts(payload, tmp_path)
    first_json = (tmp_path / "logs" / "task-writer-audit.json").read_bytes()
    first_doc = (tmp_path / "docs" / "tabularius-writer-audit.md").read_bytes()
    audit.write_receipts(payload, tmp_path)

    assert (tmp_path / "logs" / "task-writer-audit.json").read_bytes() == first_json
    assert (tmp_path / "docs" / "tabularius-writer-audit.md").read_bytes() == first_doc


def test_tabularius_relay_has_no_projection_writer_exemption():
    assert "cli/src/limen/tabularius.py" not in audit.AUTHORIZED_PROJECTION_WRITERS

    payload = audit.audit_repo(ROOT)

    assert payload["unauthorized_writer_count"] == 0
    assert payload["unauthorized_writers"] == []
