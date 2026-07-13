"""Versioned native prompt-source adapter and exclusion contract."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from pathlib import Path, PurePath
from typing import Any


SOURCE_ADAPTER_CONTRACT_VERSION = 1
PROMPT_SOURCE_SCANNER_VERSION = 3
SOURCE_FILE_SIGNATURE_FIELDS = ("ctime_ns", "device", "inode", "mtime_ns", "size")
CLAUDE_PROJECT_MEMORY_ALIAS_ID = "claude-project-memory-alias-v1"
SOURCE_ALIAS_BLOCKER_REASONS = (
    "alias_ancestor_symlink",
    "alias_changed",
    "alias_dangling_target",
    "alias_isolated_home_escape",
    "alias_link_chain",
    "alias_outside_root",
    "alias_target_mismatch",
    "alias_target_not_regular",
    "alias_wrong_role",
)


class SourcePathCustody:
    """Metadata-only custody for one path below a declared prompt-source root."""

    __slots__ = (
        "alias_contract_id",
        "alias_target",
        "blocker_reason",
        "error",
        "related_evidence",
        "related_signatures",
        "relative",
        "unit_signature",
    )

    def __init__(
        self,
        *,
        relative: Path | None,
        unit_signature: dict[str, int] | None,
        alias_contract_id: str | None = None,
        alias_target: Path | None = None,
        related_signatures: dict[str, dict[str, int]] | None = None,
        related_evidence: dict[str, dict[str, str]] | None = None,
        blocker_reason: str | None = None,
        error: str | None = None,
    ) -> None:
        self.relative = relative
        self.unit_signature = unit_signature
        self.alias_contract_id = alias_contract_id
        self.alias_target = alias_target
        self.related_signatures = related_signatures
        self.related_evidence = related_evidence
        self.blocker_reason = blocker_reason
        self.error = error


def _signature_from_stat(value: os.stat_result) -> dict[str, int]:
    values = {
        "size": value.st_size,
        "mtime_ns": value.st_mtime_ns,
        "ctime_ns": value.st_ctime_ns,
        "inode": value.st_ino,
        "device": value.st_dev,
    }
    return {field: int(values[field]) for field in SOURCE_FILE_SIGNATURE_FIELDS}


def _absolute_lexical(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path.expanduser())))


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root) if candidate != root else None
    except ValueError:
        return False
    return True


def _blocked_source_path(reason: str, message: str) -> SourcePathCustody:
    return SourcePathCustody(
        relative=None,
        unit_signature=None,
        blocker_reason=reason,
        error=message,
    )


def inspect_source_path_custody(
    source: str,
    path: Path,
    containment_root: Path,
    *,
    isolated_home: Path | None = None,
) -> SourcePathCustody:
    """Resolve direct files and one exact Claude memory alias without arbitrary link traversal.

    The declared root itself remains trusted and may be a configured symlink, matching
    the pre-existing scanner contract. Below that root, only a leaf
    ``claude-projects/<project>/<name>.md`` alias whose link text names the exact
    ``memory/<name>.md`` sibling is admissible. The target and every target ancestor
    below the root must be non-symlinks.
    """

    lexical_root = _absolute_lexical(containment_root)
    lexical_path = _absolute_lexical(path)
    try:
        relative = lexical_path.relative_to(lexical_root)
    except ValueError:
        return _blocked_source_path("alias_outside_root", "source path escapes its declared source root")

    try:
        resolved_root = lexical_root.resolve(strict=True)
        resolved_home = isolated_home.resolve(strict=True) if isolated_home is not None else None
    except OSError as exc:
        return _blocked_source_path("alias_outside_root", f"source path cannot be resolved: {exc}")
    if resolved_home is not None and not _within(resolved_root, resolved_home):
        return _blocked_source_path("alias_isolated_home_escape", "source path escapes isolated source home")

    path_is_declared_root = lexical_path == lexical_root
    current = lexical_root if path_is_declared_root else lexical_path.parent
    try:
        while current != lexical_root:
            current_stat = os.lstat(current)
            if stat.S_ISLNK(current_stat.st_mode):
                return _blocked_source_path(
                    "alias_ancestor_symlink",
                    "source path contains a symlink hop below its declared source root",
                )
            parent = current.parent
            if parent == current:
                return _blocked_source_path("alias_outside_root", "source path is outside its containment root")
            current = parent
        leaf_stat = os.lstat(lexical_path)
    except OSError as exc:
        return _blocked_source_path("alias_dangling_target", f"source path cannot be resolved: {exc}")

    if not stat.S_ISLNK(leaf_stat.st_mode) or path_is_declared_root:
        try:
            resolved_path = lexical_path.resolve(strict=True)
        except OSError as exc:
            return _blocked_source_path("alias_dangling_target", f"source path cannot be resolved: {exc}")
        if not _within(resolved_path, resolved_root):
            return _blocked_source_path("alias_outside_root", "source path escapes its declared source root")
        if resolved_home is not None and not _within(resolved_path, resolved_home):
            return _blocked_source_path("alias_isolated_home_escape", "source path escapes isolated source home")
        direct_stat = os.stat(lexical_path) if path_is_declared_root else leaf_stat
        return SourcePathCustody(relative=relative, unit_signature=_signature_from_stat(direct_stat))

    alias_error = "source path contains a symlink hop outside the approved Claude project-memory alias contract"
    if source != "claude-projects" or len(relative.parts) != 2 or lexical_path.suffix.lower() != ".md":
        return _blocked_source_path("alias_wrong_role", alias_error)

    expected_target = lexical_path.parent / "memory" / lexical_path.name
    try:
        link_text = os.readlink(lexical_path)
    except OSError as exc:
        return _blocked_source_path("alias_changed", f"source path contains a changed symlink hop: {exc}")
    link_path = Path(link_text)
    if not link_path.is_absolute() and ".." in link_path.parts:
        return _blocked_source_path("alias_target_mismatch", alias_error)
    claimed_target = _absolute_lexical(link_path if link_path.is_absolute() else lexical_path.parent / link_path)
    if claimed_target != expected_target:
        return _blocked_source_path("alias_target_mismatch", alias_error)

    try:
        current = expected_target
        target_stat: os.stat_result | None = None
        while current != lexical_root:
            current_stat = os.lstat(current)
            if stat.S_ISLNK(current_stat.st_mode):
                return _blocked_source_path(
                    "alias_link_chain",
                    "source path contains a symlink hop whose target is another symlink",
                )
            if current == expected_target:
                target_stat = current_stat
            current = current.parent
        if target_stat is None or not stat.S_ISREG(target_stat.st_mode):
            return _blocked_source_path(
                "alias_target_not_regular",
                "source path contains a symlink hop whose target is not a regular file",
            )
        resolved_target = expected_target.resolve(strict=True)
    except OSError as exc:
        return _blocked_source_path(
            "alias_dangling_target",
            f"source path contains a dangling symlink hop: {exc}",
        )
    if not _within(resolved_target, resolved_root):
        return _blocked_source_path("alias_outside_root", alias_error)
    if resolved_home is not None and not _within(resolved_target, resolved_home):
        return _blocked_source_path("alias_isolated_home_escape", "source path escapes isolated source home")

    target_signature = _signature_from_stat(target_stat)
    target_locator_sha256 = hashlib.sha256(str(expected_target).encode("utf-8", errors="replace")).hexdigest()
    link_target_sha256 = hashlib.sha256(os.fsencode(link_text)).hexdigest()
    return SourcePathCustody(
        relative=relative,
        unit_signature=_signature_from_stat(leaf_stat),
        alias_contract_id=CLAUDE_PROJECT_MEMORY_ALIAS_ID,
        alias_target=expected_target,
        related_signatures={"memory_target": target_signature},
        related_evidence={
            "memory_target": {
                "locator_sha256": target_locator_sha256,
                "link_target_sha256": link_target_sha256,
            }
        },
    )


SOURCE_ADAPTER_RULES: dict[str, dict[str, Any]] = {
    "codex-pasted-text-attachment-v1": {
        "source": "codex-attachments",
        "path": {
            "relative_depth": 2,
            "basename_regex": r"pasted-text-[1-9][0-9]*\.txt",
        },
        "parent": {
            "source": "codex-sessions",
            "record": "response_item:message:user",
            "content_block_type": "input_text",
            "reference_line": (
                "pasted text file: <canonical-absolute-attachment-path>. Read this file before continuing."
            ),
            "cardinality": "exactly-one-canonical-parent-event",
            "session_identity": "exactly-one-canonical-session-meta-identity",
            "inherits": ["session_ref", "timestamp", "provenance", "authority"],
        },
        "body_encoding": "utf-8-strict",
        "unparsed_parent_record_authority": "parent-completeness-unknown",
        "unknown_parent_completeness_with_attachment_candidate": "fail-closed",
        "parent_byte_accounting": "cumulative-actual-read",
        "max_probe_bytes": 1048576,
        "max_parent_probe_bytes": 536870912,
        "max_parent_record_bytes": 1048576,
        "max_parent_candidate_bytes": 16777216,
        "max_parent_records": 100000,
        "max_parent_session_ids": 16,
    },
    "claude-remote-task-command-v1": {
        "source": "claude-projects",
        "path": {"relative_depth": 4, "segment_2": "remote-agents", "suffix": ".json"},
        "object_keys": [
            "command",
            "remoteTaskType",
            "sessionId",
            "spawnedAt",
            "taskId",
            "title",
            "toolUseId",
        ],
        "field_types": {
            "command": "nonempty-string",
            "remoteTaskType": "nonempty-string",
            "sessionId": "nonempty-string",
            "spawnedAt": "nonnegative-integer",
            "taskId": "nonempty-string",
            "title": "nonempty-string",
            "toolUseId": "nonempty-string",
        },
        "text_field": "command",
        "event_type": "claude-remote-task-command",
        "event_id_fields": ["taskId", "toolUseId"],
        "session_field": "sessionId",
        "timestamp_field": "spawnedAt",
        "body_kind": "delegated_task_frame",
        "provenance": "delegated_task_frame",
        "authority": "derived",
        "max_probe_bytes": 65536,
    },
    "claude-subagent-metadata-v1": {
        "source": "claude-projects",
        "path": {"path_segment": "subagents", "suffix": ".json"},
        "schema": "claude-subagent-metadata-v1",
        "text_selectors": ["description"],
        "body_kind": "delegated_task_frame",
        "provenance": "delegated_task_frame",
        "authority": "derived",
    },
    "claude-workflow-metadata-v1": {
        "source": "claude-projects",
        "path": {"path_segment": "workflows", "suffix": ".json"},
        "schema": "claude-workflow-metadata-v1",
        "text_selectors": [
            "args",
            "phases[*].title",
            "phases[*].detail",
            "workflowProgress[*].promptPreview",
        ],
        "body_kind": "delegated_task_frame",
        "provenance": "delegated_task_frame",
        "authority": "derived",
    },
}
SOURCE_EXCLUSION_RULES: dict[str, dict[str, Any]] = {
    "claude-file-history-snapshot-v1": {
        "source": "claude-file-history",
        "path": {"minimum_relative_depth": 1, "basename_regex": "[0-9a-fA-F]+@v[0-9]+"},
    },
    "claude-generated-plan-v1": {
        "source": "claude-plans",
        "path": {"minimum_relative_depth": 1},
    },
    "claude-project-memory-v1": {
        "source": "claude-projects",
        "path": {"relative_depth": 3, "segment_1": "memory", "suffix": ".md"},
    },
    CLAUDE_PROJECT_MEMORY_ALIAS_ID: {
        "source": "claude-projects",
        "path": {"relative_depth": 2, "suffix": ".md"},
        "alias": {
            "kind": "leaf-symlink",
            "target": "memory/<same-basename>",
            "target_type": "regular-file",
            "ancestor_symlinks": "reject",
            "target_symlinks": "reject",
            "containment": "same-declared-source-root",
        },
    },
    "claude-project-memory-mirror-v1": {
        "source": "claude-projects",
        "path": {"relative_depth": 2, "suffix": ".md"},
        "sibling": "memory/<same-basename>",
        "content_predicate": "sha256-equal",
        "max_probe_bytes": 16777216,
    },
    "claude-project-tool-result-v1": {
        "source": "claude-projects",
        "path": {"minimum_relative_depth": 4, "segment_2": "tool-results"},
    },
    "claude-task-lock-v1": {
        "source": "claude-tasks",
        "path": {"relative_depth": 2, "basename": ".lock"},
        "size": 0,
    },
    "claude-task-watermark-v1": {
        "source": "claude-tasks",
        "path": {"relative_depth": 2, "basename": ".highwatermark"},
        "content_predicate": "bounded-ascii-decimal",
        "max_probe_bytes": 128,
    },
    "claude-workflow-script-v1": {
        "source": "claude-projects",
        "path": {
            "minimum_relative_depth": 5,
            "segments_2_3": ["workflows", "scripts"],
            "suffix": ".js",
        },
    },
    "claude-task-artifact-v1": {
        "source": "claude-tasks",
        "path": {"minimum_relative_depth": 2},
    },
    "claude-project-media-v1": {
        "source": "claude-projects",
        "path": {"minimum_relative_depth": 4},
    },
}
SOURCE_ADAPTER_IDS = tuple(sorted(SOURCE_ADAPTER_RULES))
SOURCE_EXCLUSION_IDS = tuple(sorted(SOURCE_EXCLUSION_RULES))
SOURCE_RECEIPT_EVIDENCE_RULES = {
    "codex-pasted-text-attachment-v1": {
        "related_label": "parent_session",
        "cardinality": "exactly-one",
        "parent_locator": "private-canonical-codex-session-path",
        "identity": [
            "parent_locator_sha256",
            "parent_event_ref_sha256",
            "parent_session_ref_sha256",
            "reference_sha256",
        ],
        "inherited": ["provenance", "authority", "timestamp"],
    },
    "claude-project-memory-mirror-v1": {
        "related_label": "memory_sibling",
        "related_locator": "<primary-parent>/memory/<primary-basename>",
        "content_predicate": "primary-and-related-sha256-equal",
    },
    CLAUDE_PROJECT_MEMORY_ALIAS_ID: {
        "related_label": "memory_target",
        "related_locator": "<primary-parent>/memory/<primary-basename>",
        "identity": ["locator_sha256", "link_target_sha256"],
        "target_type": "non-symlink-regular-file",
    },
}
SOURCE_AUTHORITY_RULES = {
    "claude-project-main-session-v1": {
        "source": "claude-projects",
        "path": {"relative_depth": 2, "suffix": ".jsonl"},
        "operator_eligible": True,
    },
    "claude-project-derived-subtrees-v1": {
        "source": "claude-projects",
        "path_segments_any": ["subagents", "workflows"],
        "provenance": "delegated_task_frame",
        "authority": "derived",
        "independent_of_record_flag": "isSidechain",
    },
    "claude-project-unclassified-jsonl-v1": {
        "source": "claude-projects",
        "path": {"suffix": ".jsonl", "excluding_relative_depth": 2},
        "provenance": "unknown_user_input",
        "authority": "unknown",
        "unless_path_segments_any": ["subagents", "workflows"],
    },
}
CODEX_USER_RECORD_KEYS = ("payload", "timestamp", "type")
CODEX_RESPONSE_USER_PAYLOAD_KEYSETS = (
    ("content", "role", "type"),
    ("content", "internal_chat_message_metadata_passthrough", "role", "type"),
)
CODEX_USER_CONTENT_BLOCK_KEYSETS = {
    "input_text": ("text", "type"),
    "input_image": ("detail", "image_url", "type"),
}
CODEX_EVENT_USER_PAYLOAD_KEYSETS = (
    ("images", "local_images", "message", "text_elements", "type"),
    ("local_images", "message", "text_elements", "type"),
)
CODEX_TEXT_ELEMENT_KEYS = ("byte_range", "placeholder")
CODEX_BYTE_RANGE_KEYS = ("end", "start")
CLAUDE_PROJECT_JSONL_TYPES = (
    "agent-name",
    "agent-setting",
    "ai-title",
    "assistant",
    "attachment",
    "file-history-snapshot",
    "fork-context-ref",
    "last-prompt",
    "mode",
    "permission-mode",
    "pr-link",
    "queue-operation",
    "result",
    "started",
    "system",
    "user",
    "worktree-state",
)
CLAUDE_USER_CONTENT_BLOCK_TYPES = ("document", "image", "text", "tool_result")
CLAUDE_USER_CONTENT_BLOCK_KEYSETS = {
    "text": (("text", "type"),),
    "tool_result": (
        ("content", "tool_use_id", "type"),
        ("content", "is_error", "tool_use_id", "type"),
    ),
    "image": (("source", "type"),),
    "document": (("source", "type"),),
}
CLAUDE_ASSISTANT_CONTENT_BLOCK_TYPES = ("fallback", "text", "thinking", "tool_use")
CLAUDE_ASSISTANT_PROMPT_FIELDS = {
    "*": ("prompt", "instructions"),
    "Agent": ("prompt", "description"),
    "SendMessage": ("prompt", "message", "content", "args"),
    "TaskCreate": ("prompt", "description", "content"),
    "TaskUpdate": ("prompt", "description"),
    "Workflow": ("prompt", "args", "description"),
}
CLAUDE_ATTACHMENT_PROMPT_FIELDS = {
    "goal_status": ("condition",),
    "hook_additional_context": ("content",),
    "queued_command": ("prompt",),
}
CLAUDE_UNEXPECTED_PROMPT_FIELDS = ("instructions", "prompt")
CLAUDE_ATTACHMENT_TYPES = (
    "agent_listing_delta",
    "budget_usd",
    "command_permissions",
    "compact_file_reference",
    "date_change",
    "deferred_tools_delta",
    "edited_text_file",
    "file",
    "goal_status",
    "hook_additional_context",
    "hook_cancelled",
    "hook_non_blocking_error",
    "hook_success",
    "invoked_skills",
    "mcp_instructions_delta",
    "nested_memory",
    "output_style",
    "plan_file_reference",
    "plan_mode",
    "plan_mode_exit",
    "plan_mode_reentry",
    "queued_command",
    "skill_listing",
    "task_reminder",
    "task_status",
    "ultra_effort_enter",
    "ultra_effort_exit",
    "workflow_keyword_request",
)
CLAUDE_QUEUE_OPERATIONS = ("dequeue", "enqueue", "popAll", "remove")
CLAUDE_GOAL_STATUS_KEYS = (
    "condition",
    "durationMs",
    "failed",
    "iterations",
    "met",
    "reason",
    "sentinel",
    "tokens",
    "type",
)
CLAUDE_SUBAGENT_METADATA_KEYS = (
    "agentType",
    "description",
    "isFork",
    "spawnDepth",
    "toolUseId",
    "worktreeBranch",
    "worktreePath",
)
CLAUDE_WORKFLOW_METADATA_KEYS = (
    "agentCount",
    "agentType",
    "args",
    "defaultModel",
    "durationMs",
    "error",
    "logs",
    "phases",
    "result",
    "runId",
    "script",
    "scriptPath",
    "spawnDepth",
    "startTime",
    "status",
    "summary",
    "taskId",
    "timestamp",
    "totalTokens",
    "totalToolCalls",
    "workflowName",
    "workflowProgress",
    "worktreePath",
)
CLAUDE_WORKFLOW_PHASE_KEYS = ("detail", "model", "title")
CLAUDE_WORKFLOW_PROGRESS_KEYS = (
    "agentId",
    "agentType",
    "attempt",
    "cached",
    "durationMs",
    "error",
    "index",
    "isolation",
    "label",
    "lastProgressAt",
    "lastToolName",
    "lastToolSummary",
    "model",
    "phaseIndex",
    "phaseTitle",
    "promptPreview",
    "queuedAt",
    "resultPreview",
    "startedAt",
    "state",
    "title",
    "tokens",
    "toolCalls",
    "type",
)
CLAUDE_TASK_KEYSETS = (
    ("activeForm", "blockedBy", "blocks", "description", "id", "status", "subject"),
    ("blockedBy", "blocks", "description", "id", "status", "subject"),
    ("activeForm", "blockedBy", "blocks", "description", "id", "owner", "status", "subject"),
)
CODEX_HISTORY_KEYSETS = (("session_id", "text", "ts"),)
AGY_HISTORY_KEYSETS = (
    ("display",),
    ("conversationId", "display", "timestamp", "workspace"),
    ("conversationId", "display", "timestamp", "type", "workspace"),
    ("display", "timestamp", "workspace"),
    ("display", "timestamp", "type", "workspace"),
)
AGY_CONVERSATION_UNIT_SIGNATURE_FIELDS = (
    "content_sha256",
    "db_ctime_ns",
    "db_device",
    "db_inode",
    "db_mtime_ns",
    "db_size",
    "wal_ctime_ns",
    "wal_device",
    "wal_inode",
    "wal_mtime_ns",
    "wal_size",
)
GEMINI_USER_RECORD_KEYSETS = (("content", "type"), ("content", "id", "timestamp", "type"))
GEMINI_CONTENT_BLOCK_KEYSETS = (("functionResponse",), ("text",))
GEMINI_SET_KEYSETS = (("lastUpdated",), ("lastUpdated", "messages"), ("memoryScratchpad",))
GEMINI_NONUSER_RECORD_KEYSETS = (
    ("kind", "lastUpdated", "projectHash", "sessionId", "startTime"),
    ("content", "id", "model", "thoughts", "timestamp", "tokens", "type"),
    ("content", "id", "model", "thoughts", "timestamp", "tokens", "toolCalls", "type"),
)
OPENCODE_USER_MESSAGE_KEYS = (
    "agent",
    "model",
    "prompt_provenance",
    "role",
    "summary",
    "time",
)
OPENCODE_UNIT_SIGNATURE_FIELDS = (
    "content_sha256",
    "db_ctime_ns",
    "db_device",
    "db_inode",
    "db_mtime_ns",
    "db_size",
    "time_created",
    "time_updated",
    "wal_ctime_ns",
    "wal_device",
    "wal_inode",
    "wal_mtime_ns",
    "wal_size",
)
OPENCODE_USER_PART_KEYSETS = {
    "text": (
        ("text", "type"),
        ("metadata", "synthetic", "text", "time", "type"),
        ("text", "time", "type"),
    ),
    "compaction": (
        ("auto", "overflow", "tail_start_id", "type"),
        ("auto", "tail_start_id", "type"),
        ("summary", "type"),
    ),
    "subtask": (
        ("description", "prompt", "type"),
        ("description", "type"),
        ("prompt", "type"),
    ),
}
SOURCE_RECORD_SCHEMAS = {
    "codex-user-message-v1": {
        "source": "codex-sessions",
        "record_keys": CODEX_USER_RECORD_KEYS,
        "unknown_recursive_user_marker": "unsupported",
        "response_item": {
            "record": "response_item:message:user",
            "payload_keysets": CODEX_RESPONSE_USER_PAYLOAD_KEYSETS,
            "content_block_keysets": CODEX_USER_CONTENT_BLOCK_KEYSETS,
            "supported_content_block_types": ["input_text"],
            "unsupported_content_block_types": ["input_image", "unknown"],
        },
        "event_msg": {
            "record": "event_msg:user_message",
            "payload_keysets": CODEX_EVENT_USER_PAYLOAD_KEYSETS,
            "text_element_keys": CODEX_TEXT_ELEMENT_KEYS,
            "byte_range_keys": CODEX_BYTE_RANGE_KEYS,
            "media_fields_require_adapter_when_nonempty": ["images", "local_images"],
        },
    },
    "claude-project-jsonl-v1": {
        "source": "claude-projects",
        "suffix": ".jsonl",
        "allowed_types": CLAUDE_PROJECT_JSONL_TYPES,
        "user_content_block_types": CLAUDE_USER_CONTENT_BLOCK_TYPES,
        "user_content_block_keysets": CLAUDE_USER_CONTENT_BLOCK_KEYSETS,
        "unsupported_user_content_without_adapter": ["document", "image"],
        "assistant_content_block_types": CLAUDE_ASSISTANT_CONTENT_BLOCK_TYPES,
        "assistant_prompt_fields": CLAUDE_ASSISTANT_PROMPT_FIELDS,
        "attachment_types": CLAUDE_ATTACHMENT_TYPES,
        "attachment_prompt_fields": CLAUDE_ATTACHMENT_PROMPT_FIELDS,
        "unexpected_attachment_prompt_fields": CLAUDE_UNEXPECTED_PROMPT_FIELDS,
        "queue_operations": CLAUDE_QUEUE_OPERATIONS,
        "queue_prompt_fields": ["content", "prompt"],
        "last_prompt_keysets": [
            ["lastPrompt", "leafUuid", "sessionId", "type"],
            ["leafUuid", "sessionId", "type"],
        ],
        "transport_candidates": [
            "last-prompt",
            "queue-operation",
            "attachment:goal_status.condition",
            "attachment:queued_command.prompt",
        ],
        "goal_status_keys": CLAUDE_GOAL_STATUS_KEYS,
        "transport_candidate_provenance": {
            "exact_same_file_operator_hash": "transport_echo",
            "unmatched": "unknown_user_input",
            "derived_path_unmatched": "delegated_task_frame",
        },
    },
    "claude-subagent-metadata-v1": {
        "source": "claude-projects",
        "path_segment": "subagents",
        "suffix": ".json",
        "allowed_keys": CLAUDE_SUBAGENT_METADATA_KEYS,
        "required_any": ["agentType", "toolUseId"],
        "prompt_field_types": {"description": "string"},
    },
    "claude-workflow-metadata-v1": {
        "source": "claude-projects",
        "path_segment": "workflows",
        "suffix": ".json",
        "allowed_keys": CLAUDE_WORKFLOW_METADATA_KEYS,
        "required_any": ["agentType", "runId"],
        "prompt_field_types": {
            "args": "string",
            "phases": "list[object]",
            "workflowProgress": "list[object]",
        },
        "phase_keys": CLAUDE_WORKFLOW_PHASE_KEYS,
        "workflow_progress_keys": CLAUDE_WORKFLOW_PROGRESS_KEYS,
    },
    "claude-task-json-v1": {
        "source": "claude-tasks",
        "suffix": ".json",
        "exact_keysets": CLAUDE_TASK_KEYSETS,
        "prompt_field_types": {"description": "string"},
    },
    "codex-history-v1": {
        "source": "codex-history",
        "exact_keysets": CODEX_HISTORY_KEYSETS,
        "prompt_field_types": {"text": "string"},
    },
    "agy-history-v1": {
        "source": "agy-cli-history",
        "exact_keysets": AGY_HISTORY_KEYSETS,
        "prompt_field_types": {"display": "string"},
    },
    "gemini-chat-v1": {
        "sources": ["gemini-tmp", "gemini-tmp-agy"],
        "user_record_keysets": GEMINI_USER_RECORD_KEYSETS,
        "content_block_keysets": GEMINI_CONTENT_BLOCK_KEYSETS,
        "set_keysets": GEMINI_SET_KEYSETS,
        "nonuser_record_keysets": GEMINI_NONUSER_RECORD_KEYSETS,
    },
    "opencode-user-v1": {
        "source": "opencode-db",
        "message_keys": OPENCODE_USER_MESSAGE_KEYS,
        "part_keysets": OPENCODE_USER_PART_KEYSETS,
        "unit_signature_fields": OPENCODE_UNIT_SIGNATURE_FIELDS,
    },
    "agy-conversation-v1": {
        "source": "agy-cli-conversations",
        "prompt_step_type": 14,
        "prompt_columns": [
            "step_payload",
            "metadata",
            "task_details",
            "error_details",
            "render_info",
        ],
        "unknown_prompt_markers": ["prompt", "instructions", "role:user", "type:user|human|prompt"],
        "unit_signature_fields": AGY_CONVERSATION_UNIT_SIGNATURE_FIELDS,
    },
}
SOURCE_ADAPTER_CONTRACT_SPEC = {
    "version": SOURCE_ADAPTER_CONTRACT_VERSION,
    "scanner_version": PROMPT_SOURCE_SCANNER_VERSION,
    "file_signature_fields": SOURCE_FILE_SIGNATURE_FIELDS,
    "alias_blocker_reasons": SOURCE_ALIAS_BLOCKER_REASONS,
    "adapters": SOURCE_ADAPTER_RULES,
    "exclusions": SOURCE_EXCLUSION_RULES,
    "receipt_evidence": SOURCE_RECEIPT_EVIDENCE_RULES,
    "authority_rules": SOURCE_AUTHORITY_RULES,
    "record_schemas": SOURCE_RECORD_SCHEMAS,
}


def _digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def source_adapter_contract() -> dict[str, Any]:
    """Return the public-safe current source adapter contract."""

    return {
        "version": SOURCE_ADAPTER_CONTRACT_VERSION,
        "scanner_version": PROMPT_SOURCE_SCANNER_VERSION,
        "digest": _digest(SOURCE_ADAPTER_CONTRACT_SPEC),
        "alias_blocker_reasons": sorted(SOURCE_ALIAS_BLOCKER_REASONS),
        "adapter_ids": sorted(SOURCE_ADAPTER_IDS),
        "exclusion_ids": sorted(SOURCE_EXCLUSION_IDS),
        "adapter_sources": {
            contract_id: str(rule["source"]) for contract_id, rule in sorted(SOURCE_ADAPTER_RULES.items())
        },
        "exclusion_sources": {
            contract_id: str(rule["source"]) for contract_id, rule in sorted(SOURCE_EXCLUSION_RULES.items())
        },
    }


def _relative_role_parts(source: str, locator: str) -> tuple[str, ...] | None:
    roots = {
        "codex-attachments": (".codex", "attachments"),
        "claude-file-history": (".claude", "file-history"),
        "claude-plans": (".claude", "plans"),
        "claude-projects": (".claude", "projects"),
        "claude-tasks": (".claude", "tasks"),
    }
    root = roots.get(source)
    if root is None:
        return None
    parts = PurePath(locator).parts
    for index in range(len(parts) - len(root) + 1):
        if tuple(parts[index : index + len(root)]) == root:
            return tuple(parts[index + len(root) :])
    return None


def source_contract_receipt_applies(
    contract_id: str,
    source: str,
    locator: str,
    signature: dict[str, Any] | None = None,
    related_signatures: dict[str, Any] | None = None,
    related_evidence: dict[str, Any] | None = None,
) -> bool:
    """Validate the source and structural path role claimed by a private receipt."""

    rule = SOURCE_ADAPTER_RULES.get(contract_id) or SOURCE_EXCLUSION_RULES.get(contract_id)
    if not isinstance(rule, dict) or rule.get("source") != source:
        return False
    relative = _relative_role_parts(source, locator)
    if relative is None:
        return False
    path = PurePath(locator)
    suffix = path.suffix.lower()
    related = related_signatures or {}
    evidence = related_evidence or {}

    def mirror_evidence_valid() -> bool:
        sibling = path.parent / "memory" / path.name
        detail = evidence.get("memory_sibling")
        primary_sha = detail.get("primary_content_sha256") if isinstance(detail, dict) else None
        related_sha = detail.get("related_content_sha256") if isinstance(detail, dict) else None
        expected_locator_sha = hashlib.sha256(str(sibling).encode("utf-8", errors="replace")).hexdigest()
        sibling_signature = related.get("memory_sibling")
        return bool(
            set(evidence) == {"memory_sibling"}
            and isinstance(detail, dict)
            and set(detail)
            == {
                "locator_sha256",
                "primary_content_sha256",
                "related_content_sha256",
            }
            and detail.get("locator_sha256") == expected_locator_sha
            and isinstance(primary_sha, str)
            and re.fullmatch(r"[0-9a-f]{64}", primary_sha) is not None
            and primary_sha == related_sha
            and isinstance(signature, dict)
            and isinstance(sibling_signature, dict)
            and signature.get("size") == sibling_signature.get("size")
        )

    def memory_alias_evidence_valid() -> bool:
        target = path.parent / "memory" / path.name
        detail = evidence.get("memory_target")
        target_signature = related.get("memory_target")
        expected_locator_sha = hashlib.sha256(str(target).encode("utf-8", errors="replace")).hexdigest()
        return bool(
            set(related) == {"memory_target"}
            and set(evidence) == {"memory_target"}
            and isinstance(target_signature, dict)
            and isinstance(detail, dict)
            and set(detail) == {"link_target_sha256", "locator_sha256"}
            and detail.get("locator_sha256") == expected_locator_sha
            and all(
                isinstance(detail.get(field), str) and re.fullmatch(r"[0-9a-f]{64}", str(detail[field])) is not None
                for field in ("link_target_sha256", "locator_sha256")
            )
        )

    def codex_attachment_evidence_valid() -> bool:
        detail = evidence.get("parent_event")
        parent_signature = related.get("parent_session")
        if not isinstance(detail, dict) or not isinstance(parent_signature, dict):
            return False
        expected_keys = {
            "authority",
            "parent_event_index",
            "parent_event_ref_sha256",
            "parent_locator",
            "parent_locator_sha256",
            "parent_session_ref_sha256",
            "parent_text_index",
            "provenance",
            "reference_sha256",
            "timestamp",
        }
        if set(evidence) != {"parent_event"} or set(detail) != expected_keys:
            return False
        parent_locator = detail.get("parent_locator")
        if not isinstance(parent_locator, str) or not parent_locator:
            return False
        parent_parts = PurePath(parent_locator).parts
        codex_sessions = (".codex", "sessions")
        parent_root_indexes = [
            index
            for index in range(len(parent_parts) - len(codex_sessions) + 1)
            if tuple(parent_parts[index : index + len(codex_sessions)]) == codex_sessions
        ]
        attachment_parts = path.parts
        attachment_root_indexes = [
            index
            for index in range(len(attachment_parts) - 1)
            if tuple(attachment_parts[index : index + 2]) == (".codex", "attachments")
        ]
        if (
            len(parent_root_indexes) != 1
            or len(attachment_root_indexes) != 1
            or parent_parts[: parent_root_indexes[0]] != attachment_parts[: attachment_root_indexes[0]]
            or PurePath(parent_locator).suffix.lower() != ".jsonl"
        ):
            return False
        if (
            detail.get("parent_locator_sha256")
            != hashlib.sha256(parent_locator.encode("utf-8", errors="replace")).hexdigest()
        ):
            return False
        reference = f"pasted text file: {locator}. Read this file before continuing."
        if detail.get("reference_sha256") != hashlib.sha256(reference.encode("utf-8", errors="replace")).hexdigest():
            return False
        for field in ("parent_event_ref_sha256", "parent_session_ref_sha256"):
            value = detail.get(field)
            if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
                return False
        for field in ("parent_event_index", "parent_text_index"):
            value = detail.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                return False
        provenance = detail.get("provenance")
        authority = detail.get("authority")
        expected_authority = (
            "operator"
            if provenance == "operator_typed"
            else ("unknown" if provenance == "unknown_user_input" else "derived")
        )
        return bool(
            provenance
            in {
                "operator_typed",
                "transport_echo",
                "continuation_summary",
                "delegated_task_frame",
                "unknown_user_input",
            }
            and authority == expected_authority
            and (
                detail.get("timestamp") is None
                or (
                    not isinstance(detail.get("timestamp"), bool)
                    and isinstance(detail.get("timestamp"), (str, int, float))
                )
            )
        )

    prompt_suffixes = {".json", ".jsonl", ".md"}

    predicates = {
        "codex-pasted-text-attachment-v1": lambda: (
            len(relative) == 2
            and re.fullmatch(r"pasted-text-[1-9][0-9]*\.txt", path.name) is not None
            and set(related) == {"parent_session"}
        ),
        "claude-file-history-snapshot-v1": lambda: (
            len(relative) >= 1 and re.fullmatch(r"[0-9a-fA-F]+@v[0-9]+", path.name) is not None
        ),
        "claude-generated-plan-v1": lambda: len(relative) >= 1,
        "claude-project-memory-v1": lambda: len(relative) == 3 and relative[1] == "memory" and suffix == ".md",
        CLAUDE_PROJECT_MEMORY_ALIAS_ID: lambda: (
            len(relative) == 2 and suffix == ".md" and set(related) == {"memory_target"}
        ),
        "claude-project-memory-mirror-v1": lambda: (
            len(relative) == 2 and suffix == ".md" and set(related) == {"memory_sibling"}
        ),
        "claude-project-tool-result-v1": lambda: len(relative) >= 4 and relative[2] == "tool-results",
        "claude-task-lock-v1": lambda: (
            len(relative) == 2 and path.name == ".lock" and isinstance(signature, dict) and signature.get("size") == 0
        ),
        "claude-task-watermark-v1": lambda: len(relative) == 2 and path.name == ".highwatermark",
        "claude-task-artifact-v1": lambda: len(relative) >= 2 and suffix not in prompt_suffixes,
        "claude-workflow-script-v1": lambda: (
            len(relative) >= 5 and relative[2:4] == ("workflows", "scripts") and suffix == ".js"
        ),
        "claude-remote-task-command-v1": lambda: (
            len(relative) == 4 and relative[2] == "remote-agents" and suffix == ".json"
        ),
        "claude-subagent-metadata-v1": lambda: "subagents" in relative[2:] and suffix == ".json",
        "claude-workflow-metadata-v1": lambda: "workflows" in relative[2:] and suffix == ".json",
        "claude-project-media-v1": lambda: len(relative) >= 4 and suffix not in prompt_suffixes,
    }
    predicate = predicates.get(contract_id)
    if not predicate or not predicate():
        return False
    if contract_id == "claude-project-memory-mirror-v1":
        return mirror_evidence_valid()
    if contract_id == CLAUDE_PROJECT_MEMORY_ALIAS_ID:
        return memory_alias_evidence_valid()
    if contract_id == "codex-pasted-text-attachment-v1":
        return codex_attachment_evidence_valid()
    return not evidence
