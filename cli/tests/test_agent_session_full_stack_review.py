from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "agent-session-full-stack-review.py"


def load_review_module():
    spec = importlib.util.spec_from_file_location("agent_session_full_stack_review", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_changed_files_from_patch_extracts_add_update_delete_and_move() -> None:
    review = load_review_module()
    patch = """*** Begin Patch
*** Add File: docs/new.md
+text
*** Update File: scripts/old.py
@@
-old
+new
*** Update File: old/name.py
*** Move to: new/name.py
*** Delete File: stale.txt
*** End Patch
"""

    assert review.changed_files_from_patch(patch) == [
        "docs/new.md",
        "new/name.py",
        "old/name.py",
        "scripts/old.py",
        "stale.txt",
    ]


def test_changed_files_from_codex_custom_apply_patch_payload() -> None:
    review = load_review_module()
    payload = {
        "type": "custom_tool_call",
        "name": "apply_patch",
        "input": """*** Begin Patch
*** Update File: cli/src/limen/dispatch.py
@@
-old
+new
*** End Patch
""",
    }

    assert review.changed_files_from_tool_payload(payload) == ["cli/src/limen/dispatch.py"]


def test_changed_files_from_claude_mutating_tool_payload() -> None:
    review = load_review_module()
    payload = {
        "role": "assistant",
        "content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "README.md"}},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "scripts/route.py"}},
            {"type": "tool_use", "name": "Write", "input": {"file_path": "docs/report.md"}},
        ],
    }

    assert review.changed_files_from_tool_payload(payload) == ["docs/report.md", "scripts/route.py"]


def test_changed_files_from_agy_spans_extracts_mutating_target_files() -> None:
    review = load_review_module()
    spans = [
        '{"toolAction":"Viewing file","TargetFile":"docs/read-only.md"}',
        'x{"toolAction":"Editing file","TargetFile":"/Users/4jp/Workspace/limen/scripts/route.py","ReplacementChunks":[]}',
        '{"toolAction":"Creating file","TargetFile":"docs/new.md","CodeContent":"text"}',
        '{"TargetFile":"docs/implicit-edit.md","ReplacementContent":"new"}',
    ]

    assert review.changed_files_from_agy_spans(spans) == [
        "/Users/4jp/Workspace/limen/scripts/route.py",
        "docs/implicit-edit.md",
        "docs/new.md",
    ]


class _Recorder:
    def __init__(self) -> None:
        self.prompts: list[dict] = []
        self.outcomes: list[dict] = []
        self.sessions: list[dict] = []

    def add_prompt(self, **kwargs):
        self.prompts.append(kwargs)
        return {}

    def add_outcome_text(self, **kwargs) -> None:
        self.outcomes.append(kwargs)

    def add_session_metadata(self, **kwargs) -> None:
        self.sessions.append(kwargs)


class _Sink:
    def write(self, _text: str) -> None:
        pass


def _extract(store: Path) -> _Recorder:
    review = load_review_module()
    review.OPENCODE_DB = store
    recorder = _Recorder()
    review.extract_opencode(recorder, _Sink())
    return recorder


def test_opencode_review_keeps_legacy_turns_and_adds_the_v2_tail(opencode_migrated_store: Path) -> None:
    recorder = _extract(opencode_migrated_store)
    frozen = [p for p in recorder.prompts if p["session_id"] == "frozen"]
    answers = [o for o in recorder.outcomes if o["session_id"] == "frozen"]

    assert [p["text"] for p in frozen] == ["Frozen ask\n\nInjected note", "Tail ask"]
    assert [p["ordinal"] for p in frozen] == [0, 2], "tail turns continue the legacy numbering"
    assert len(answers) == 1 and "Frozen answer" in answers[0]["text"], "legacy assistant text survives the v2 store"
    assert answers[0]["changed_files"] == ["a.py"], "patch parts exist only in the legacy rows"


def test_opencode_review_reads_a_session_that_exists_only_in_v2(opencode_migrated_store: Path) -> None:
    recorder = _extract(opencode_migrated_store)

    assert {s["session_id"] for s in recorder.sessions} == {"frozen", "v2-only"}
    assert [p["text"] for p in recorder.prompts if p["session_id"] == "v2-only"] == ["V2 ask"]
    assert [o["text"] for o in recorder.outcomes if o["session_id"] == "v2-only"] == ["V2 answer"]
