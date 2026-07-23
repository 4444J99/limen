from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "corpus-command-center.py"


def _load():
    spec = importlib.util.spec_from_file_location("corpus_command_center", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _wire_paths(ccc, tmp_path: Path):
    ccc.ROOT = tmp_path
    ccc.HOME = tmp_path
    ccc.PRIVATE_ROOT = tmp_path / ".limen-private" / "session-corpus"
    ccc.LIFECYCLE_INDEX = ccc.PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
    ccc.PRIORITY_INDEX = ccc.PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
    ccc.ATTACK_INDEX = ccc.PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
    ccc.PRIVATE_INDEX = ccc.PRIVATE_ROOT / "lifecycle" / "corpus-command-center.private.json"
    ccc.PUBLIC_INDEX = ccc.PRIVATE_ROOT / "lifecycle" / "corpus-command-center.public.json"
    ccc.PRIVATE_HTML = ccc.PRIVATE_ROOT / "lifecycle" / "corpus-command-center.private.html"
    ccc.BODY_OBJECT_ROOT = ccc.PRIVATE_ROOT / "corpus-command-center" / "objects"
    ccc.DOC_PATH = tmp_path / "docs" / "corpus-command-center.md"
    ccc.TASKS_PATH = tmp_path / "tasks.yaml"
    ccc.AUG1_VIEW_PATH = tmp_path / "logs" / "aug1-view.json"
    ccc.VALUE_REPOS_PATH = tmp_path / "value-repos.json"
    ccc.POSITIONING_SEEDS_PATH = tmp_path / "positioning-seeds.json"
    ccc.POSITIONING_DIR = tmp_path / "docs" / "positioning"


def test_corpus_command_center_indexes_all_unit_shapes_and_redacts_public(tmp_path: Path):
    ccc = _load()
    _wire_paths(ccc, tmp_path)
    ccc.LIFECYCLE_INDEX.parent.mkdir(parents=True)

    session_a = tmp_path / "codex-a.jsonl"
    session_b = tmp_path / "claude-b.jsonl"
    session_a.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "timestamp": "2026-06-29T00:00:00Z",
                        "payload": {
                            "type": "user_message",
                            "message": "RAW_PRIVATE_PROMPT build the ledger",
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-29T00:01:00Z",
                        "payload": {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"text": "RAW_ASSISTANT_REPLY here is the plan"}],
                        },
                    }
                ),
                json.dumps(
                    {
                        "timestamp": "2026-06-29T00:02:00Z",
                        "payload": {
                            "type": "function_call",
                            "name": "read_file",
                            "arguments": '{"path":"SECRET_TOOL_ARG"}',
                        },
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    session_b.write_text(
        json.dumps(
            {
                "type": "user",
                "timestamp": "2026-06-29T01:00:00Z",
                "message": {"role": "user", "content": "RAW_PRIVATE_PROMPT build the ledger"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "type": "attachment",
                "timestamp": "2026-06-29T01:01:00Z",
                "attachment": {"text": "RAW_ATTACHMENT_ARTIFACT"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    prompt_hash = ccc.full_hash("RAW_PRIVATE_PROMPT build the ledger")
    ccc.LIFECYCLE_INDEX.write_text(
        json.dumps(
            {
                "sessions": [
                    {
                        "session_key": "session-a",
                        "session_id_hash": "sid-a",
                        "source": "codex-sessions",
                        "path": str(session_a),
                        "display_path": "~/codex-a.jsonl",
                        "mtime": "2026-06-29T00:02:00Z",
                    },
                    {
                        "session_key": "session-b",
                        "session_id_hash": "sid-b",
                        "source": "claude-projects",
                        "path": str(session_b),
                        "display_path": "~/claude-b.jsonl",
                        "mtime": "2026-06-29T01:01:00Z",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    ccc.PRIORITY_INDEX.write_text(
        json.dumps(
            {
                "session_items": [
                    {"session_key": "session-a", "lane": "work-lane", "worktree_slug": "wt-a"},
                    {"session_key": "session-b", "lane": "work-lane", "worktree_slug": "wt-b"},
                ],
                "prompt_units": [{"prompt_hash": prompt_hash}],
            }
        ),
        encoding="utf-8",
    )
    ccc.ATTACK_INDEX.write_text(json.dumps({"ranked_paths": [{"id": "work-lane"}]}), encoding="utf-8")
    ccc.TASKS_PATH.write_text(
        """
tasks:
  - id: TASK-1
    title: RAW_TASK_TITLE
    context: RAW_TASK_CONTEXT
    status: open
    priority: high
    repo: owner/private-repo
""",
        encoding="utf-8",
    )
    (tmp_path / "docs" / "positioning").mkdir(parents=True)
    (tmp_path / "docs" / "inbound-magnet-system.md").write_text("RAW_INBOUND_DOC", encoding="utf-8")
    (tmp_path / "docs" / "AUG1-10K-GATE.md").write_text("RAW_AUG_DOC", encoding="utf-8")
    (tmp_path / "docs" / "positioning" / "public-record-data-scrapper.md").write_text("scraper model", encoding="utf-8")
    (tmp_path / "logs").mkdir()
    ccc.AUG1_VIEW_PATH.write_text(
        json.dumps(
            {
                "generated_at": "2026-06-29T00:00:00",
                "deadline": "2026-08-01",
                "days_left": 33,
                "gate": {"pass": False, "legs": [{"ok": True}, {"ok": False}]},
                "next_act": "open a rail",
                "ledger": {"received_total_cents": 0},
            }
        ),
        encoding="utf-8",
    )
    ccc.VALUE_REPOS_PATH.write_text(json.dumps({"repos": ["organvm/public-record-data-scrapper"]}), encoding="utf-8")
    ccc.POSITIONING_SEEDS_PATH.write_text(
        json.dumps({"frontdoor": {"contact": ""}, "repos": {"organvm/public-record-data-scrapper": {}}}),
        encoding="utf-8",
    )

    private, public, markdown = ccc.build_snapshots(write_objects=True)
    ccc.write_outputs(private, public, markdown)

    kinds = {unit["kind"] for unit in private["units"]}
    assert {"prompt", "response", "tool", "artifact", "task"}.issubset(kinds)
    assert private["coverage"]["units"] == len(private["units"])
    assert private["coverage"]["body_objects"] > 0
    assert any(unit["body_object"] for unit in private["units"] if unit["kind"] == "prompt")
    assert all("body_preview" not in unit for unit in private["units"])
    assert private["comparison_previews"]
    assert any(cluster["unit_count"] >= 2 for cluster in private["clusters"])
    assert private["comparisons"], "duplicate prompt should create a side-by-side comparison"
    assert any(row["absent_adjacent_atoms"] for row in private["allusions"])
    assert public["aug1"]["legs_met"] == 1
    assert public["inbound"]["scraper_model_present"] is True

    public_text = json.dumps(public)
    for forbidden in [
        "RAW_PRIVATE_PROMPT",
        "RAW_ASSISTANT_REPLY",
        "RAW_ATTACHMENT_ARTIFACT",
        "RAW_TASK_CONTEXT",
        "SECRET_TOOL_ARG",
        str(tmp_path),
        '"body_preview"',
        '"body_object"',
        '"private_source_path"',
    ]:
        assert forbidden not in public_text

    assert ccc.PRIVATE_INDEX.exists()
    assert ccc.PUBLIC_INDEX.exists()
    assert ccc.PRIVATE_HTML.exists()
    assert "RAW_PRIVATE_PROMPT" in ccc.PRIVATE_HTML.read_text(encoding="utf-8")
    assert ccc.DOC_PATH.exists()
    assert "Corpus Command Center" in ccc.DOC_PATH.read_text(encoding="utf-8")


def test_doc_candidates_include_control_plane_receipts(tmp_path: Path):
    ccc = _load()
    _wire_paths(ccc, tmp_path)
    (tmp_path / "docs").mkdir(parents=True)
    for name in (
        "session-corpus-ledger.md",
        "antigravity-scratch-bridge.md",
        "storage-creep-2026-07-05.md",
        "avtopoiesis.md",
        "agent-codex-review.md",
    ):
        (tmp_path / "docs" / name).write_text(f"# {name}\n", encoding="utf-8")

    candidates = {path.name for path in ccc.doc_candidates()}

    assert {
        "session-corpus-ledger.md",
        "antigravity-scratch-bridge.md",
        "storage-creep-2026-07-05.md",
        "avtopoiesis.md",
        "agent-codex-review.md",
    } <= candidates
