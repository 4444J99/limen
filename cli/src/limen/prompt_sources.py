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
PROMPT_SOURCE_SCANNER_VERSION = 4
SOURCE_FILE_SIGNATURE_FIELDS = ("ctime_ns", "device", "inode", "mtime_ns", "size")
AGY_CONVERSATION_ROOT_SEGMENTS = (".gemini", "antigravity-cli", "conversations")
AGY_SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm", "-journal")
CLAUDE_PROJECT_MEMORY_ALIAS_ID = "claude-project-memory-alias-v1"
CLAUDE_SUBAGENT_SESSION_ALIAS_ID = "claude-subagent-session-alias-v1"
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
    """Resolve direct files and exact Claude aliases without arbitrary link traversal.

    The declared root itself remains trusted and may be a configured symlink, matching
    the pre-existing scanner contract. Below that root, the only admissible aliases are
    the exact project-memory mirror and Claude's same-project, cross-session subagent
    mirror. The target and every target ancestor below the root must be non-symlinks.
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

    alias_error = "source path contains a symlink hop outside the approved Claude alias contracts"
    try:
        link_text = os.readlink(lexical_path)
    except OSError as exc:
        return _blocked_source_path("alias_changed", f"source path contains a changed symlink hop: {exc}")
    link_path = Path(link_text)
    claimed_target = _absolute_lexical(link_path if link_path.is_absolute() else lexical_path.parent / link_path)

    memory_alias = bool(
        source == "claude-projects" and len(relative.parts) == 2 and lexical_path.suffix.lower() == ".md"
    )
    subagent_alias = bool(
        source == "claude-projects"
        and len(relative.parts) in {4, 5}
        and relative.parts[2] == "subagents"
        and (
            (len(relative.parts) == 4 and lexical_path.suffix.lower() in {".json", ".jsonl"})
            or (len(relative.parts) == 5 and not lexical_path.suffix)
        )
    )
    if memory_alias:
        expected_target = lexical_path.parent / "memory" / lexical_path.name
        if not link_path.is_absolute() and ".." in link_path.parts:
            return _blocked_source_path("alias_target_mismatch", alias_error)
        if claimed_target != expected_target:
            return _blocked_source_path("alias_target_mismatch", alias_error)
        alias_contract_id = CLAUDE_PROJECT_MEMORY_ALIAS_ID
        related_label = "memory_target"
        target_must_be_directory = False
    elif subagent_alias:
        if not link_path.is_absolute():
            return _blocked_source_path("alias_target_mismatch", alias_error)
        try:
            target_relative = claimed_target.relative_to(lexical_root)
        except ValueError:
            return _blocked_source_path("alias_outside_root", alias_error)
        if not (
            len(target_relative.parts) == len(relative.parts)
            and target_relative.parts[0] == relative.parts[0]
            and target_relative.parts[1] != relative.parts[1]
            and target_relative.parts[2:] == relative.parts[2:]
        ):
            return _blocked_source_path("alias_target_mismatch", alias_error)
        expected_target = claimed_target
        alias_contract_id = CLAUDE_SUBAGENT_SESSION_ALIAS_ID
        related_label = "subagent_target"
        target_must_be_directory = len(relative.parts) == 5
    else:
        return _blocked_source_path("alias_wrong_role", alias_error)

    if not _within(expected_target, lexical_root):
        return _blocked_source_path("alias_outside_root", alias_error)
    if expected_target == lexical_path:
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
        target_type_ok = bool(
            target_stat is not None
            and (stat.S_ISDIR(target_stat.st_mode) if target_must_be_directory else stat.S_ISREG(target_stat.st_mode))
        )
        if not target_type_ok:
            return _blocked_source_path(
                "alias_target_not_regular",
                "source path contains a symlink hop whose target has the wrong filesystem type",
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

    assert target_stat is not None
    target_signature = _signature_from_stat(target_stat)
    target_locator_sha256 = hashlib.sha256(str(expected_target).encode("utf-8", errors="replace")).hexdigest()
    link_target_sha256 = hashlib.sha256(os.fsencode(link_text)).hexdigest()
    related_detail = {
        "locator_sha256": target_locator_sha256,
        "link_target_sha256": link_target_sha256,
    }
    if alias_contract_id == CLAUDE_SUBAGENT_SESSION_ALIAS_ID:
        related_detail["target_locator"] = str(expected_target)
    return SourcePathCustody(
        relative=relative,
        unit_signature=_signature_from_stat(leaf_stat),
        alias_contract_id=alias_contract_id,
        alias_target=expected_target,
        related_signatures={related_label: target_signature},
        related_evidence={related_label: related_detail},
    )


def agy_conversation_root_error(home: Path, root: Path) -> str | None:
    """Require the canonical Agy root and every fixed segment to remain direct."""

    lexical_home = _absolute_lexical(home)
    lexical_root = _absolute_lexical(root)
    expected_root = lexical_home.joinpath(*AGY_CONVERSATION_ROOT_SEGMENTS)
    if not os.path.lexists(lexical_home) and not os.path.lexists(lexical_root):
        return None
    if lexical_root != expected_root:
        return "configured conversation root does not match its canonical HOME-relative role"
    try:
        current = lexical_home
        for segment in AGY_CONVERSATION_ROOT_SEGMENTS:
            current /= segment
            if not os.path.lexists(current):
                return None
            current_stat = os.lstat(current)
            if stat.S_ISLNK(current_stat.st_mode):
                return "conversation root contains a symlink hop in its fixed path"
            if not stat.S_ISDIR(current_stat.st_mode):
                return "conversation root contains a non-directory fixed path segment"
        resolved_home = lexical_home.resolve(strict=True)
        resolved_root = lexical_root.resolve(strict=True)
    except OSError as exc:
        return f"conversation root cannot be resolved: {exc}"
    if not _within(resolved_root, resolved_home):
        return "conversation root escapes its configured HOME"
    return None


def agy_conversation_storage_error(path: Path) -> str | None:
    """Reject non-regular database or sidecar leaves before SQLite opens them."""

    try:
        database_mode = path.lstat().st_mode
    except OSError as exc:
        return f"cannot inspect conversation database leaf: {exc}"
    if not stat.S_ISREG(database_mode):
        return "conversation database leaf is not a regular file"
    for suffix in AGY_SQLITE_SIDECAR_SUFFIXES:
        sidecar = Path(f"{path}{suffix}")
        if not os.path.lexists(sidecar):
            continue
        custody = inspect_source_path_custody("agy-cli-conversations", sidecar, path.parent)
        if custody.error:
            return f"{sidecar.name}: {custody.error}"
        try:
            sidecar_mode = sidecar.lstat().st_mode
        except OSError as exc:
            return f"{sidecar.name}: cannot inspect SQLite sidecar: {exc}"
        if not stat.S_ISREG(sidecar_mode):
            return f"{sidecar.name}: SQLite sidecar is not a regular file"
    return None


SOURCE_ADAPTER_RULES: dict[str, dict[str, Any]] = {
    "agy-conversation-v1": {
        "source": "agy-cli-conversations",
        "path": {
            "root_segments": list(AGY_CONVERSATION_ROOT_SEGMENTS),
            "relative_depth": 1,
            "suffix": ".db",
        },
        "schema": "agy-conversation-v1",
        "prompt_discriminator": {"column": "step_type", "exact_integer": 14},
        "prompt_carrier": "exactly-one-grounded-source-segment",
        "provenance": "provider-neutral",
    },
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
        "max_parent_record_bytes": 16777216,
        "max_parent_candidate_bytes": 16777216,
        "max_parent_records": 100000,
        "max_parent_session_ids": 16,
    },
    "opencode-assistant-task-v1": {
        "source": "opencode-db",
        "storage": {
            "parent_table": "message",
            "child_table": "part",
            "relationship": [
                "message.id=part.message_id",
                "message.session_id=part.session_id",
            ],
        },
        "parent": {
            "role": "assistant",
            "message_keysets": [
                [
                    "agent",
                    "cost",
                    "mode",
                    "modelID",
                    "parentID",
                    "path",
                    "providerID",
                    "role",
                    "time",
                    "tokens",
                ],
                [
                    "agent",
                    "cost",
                    "finish",
                    "mode",
                    "modelID",
                    "parentID",
                    "path",
                    "providerID",
                    "role",
                    "time",
                    "tokens",
                ],
            ],
        },
        "part": {
            "type": "tool",
            "tool": "task",
            "keys": ["callID", "state", "tool", "type"],
            "identity_field": "callID",
        },
        "state": {
            "running_keys": ["input", "metadata", "status", "time", "title"],
            "completed_keys": ["input", "metadata", "output", "status", "time", "title"],
            "metadata_keysets": [
                ["model", "parentSessionId", "sessionId"],
                ["model", "parentSessionId", "sessionId", "truncated"],
                ["model", "outputPath", "parentSessionId", "sessionId", "truncated"],
            ],
            "time_keysets": {
                "running": ["start"],
                "completed": ["end", "start"],
            },
        },
        "input": {
            "keysets": [
                ["description", "prompt", "subagent_type"],
                ["command", "description", "prompt", "subagent_type"],
            ],
            "text_field": "prompt",
        },
        "child_session": {
            "id": "state.metadata.sessionId",
            "parent_id": "part.session_id",
            "agent": "state.input.subagent_type",
            "model": {
                "id": "state.metadata.model.modelID",
                "providerID": "state.metadata.model.providerID",
            },
        },
        "body_kind": "delegated_task_frame",
        "provenance": "delegated_task_frame",
        "authority": "derived",
    },
    "codex-session-jsonl-v2": {
        "source": "codex-sessions",
        "path": {
            "relative_depth": 4,
            "calendar_segments": ["YYYY", "MM", "DD"],
            "basename_regex": r"rollout-.+\.jsonl",
        },
        "schema": "codex-session-jsonl-v2",
        "canonical_identity": "one-id-or-one-filename-bound-id",
        "compacted_history_authority": "derived-continuation-context",
        "media": {
            "primary": "response_item:message:user:input_image",
            "transport": "event_msg:user_message:local_images",
            "binding": "nearest-preceding-exact-text-and-cardinality",
            "encoding": "data:image/png;base64",
            "occurrence": "digest-only-nontext-input",
        },
        "max_probe_bytes": 536870912,
        "max_record_bytes": 16777216,
        "max_records": 100000,
        "max_compacted_history_items": 256,
        "max_media_bytes": 16777216,
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
SOURCE_MISSING_EXCLUSION_ID = "source-missing-v1"

SOURCE_EXCLUSION_RULES: dict[str, dict[str, Any]] = {
    SOURCE_MISSING_EXCLUSION_ID: {
        # Wildcard: applies to any source whose tracked path has been reclaimed
        # from disk. The source_contract_receipt_applies function handles this
        # contract_id specially — it bypasses the source/path-role checks that
        # apply to on-disk exclusions and validates only the observed_missing_at
        # evidence field.
        "source": "*",
        "reason": "source path no longer exists on disk",
    },
    "agy-conversation-nonprompt-v1": {
        "source": "agy-cli-conversations",
        "path": {
            "root_segments": list(AGY_CONVERSATION_ROOT_SEGMENTS),
            "relative_depth": 1,
            "suffix": ".db",
        },
        "schema": "agy-conversation-v1",
        "predicate": "all rows have an exact non-prompt step discriminator and no prompt-bearing marker",
    },
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
    CLAUDE_SUBAGENT_SESSION_ALIAS_ID: {
        "source": "claude-projects",
        "path": {
            "relative_depth": 4,
            "segment_2": "subagents",
            "suffixes": [".json", ".jsonl"],
        },
        "alias": {
            "kind": "leaf-symlink",
            "target": "<same-project>/<different-session>/subagents/<same-basename>",
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
    CLAUDE_SUBAGENT_SESSION_ALIAS_ID: {
        "related_label": "subagent_target",
        "related_locator": "<same-project>/<different-session>/subagents/<same-basename>",
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
CODEX_COMPACTED_PAYLOAD_KEYSETS = (
    ("first_window_id", "message", "previous_window_id", "replacement_history", "window_id", "window_number"),
    ("message", "replacement_history", "window_id"),
    ("message", "replacement_history"),
)
CODEX_COMPACTED_MESSAGE_KEYSETS = CODEX_RESPONSE_USER_PAYLOAD_KEYSETS
CODEX_COMPACTION_ITEM_KEYSETS = (
    ("encrypted_content", "id", "internal_chat_message_metadata_passthrough", "type"),
    ("encrypted_content", "id", "type"),
    ("encrypted_content", "metadata", "type"),
    ("encrypted_content", "type"),
)
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
CLAUDE_DERIVED_TOOL_RESULT_PROMPT_KEYSETS = (
    (
        "agentId",
        "canReadOutputFile",
        "description",
        "isAsync",
        "outputFile",
        "prompt",
        "resolvedModel",
        "status",
    ),
    (
        "agentId",
        "agentType",
        "content",
        "prompt",
        "resolvedModel",
        "status",
        "toolStats",
        "totalDurationMs",
        "totalTokens",
        "totalToolUseCount",
        "usage",
    ),
    (
        "agentId",
        "agentType",
        "content",
        "prompt",
        "resolvedModel",
        "status",
        "totalDurationMs",
        "totalTokens",
        "totalToolUseCount",
        "usage",
    ),
    (
        "description",
        "outputFile",
        "prompt",
        "sessionUrl",
        "status",
        "taskId",
    ),
    (
        "agentId",
        "agentType",
        "content",
        "prompt",
        "resolvedModel",
        "status",
        "toolStats",
        "totalDurationMs",
        "totalTokens",
        "totalToolUseCount",
        "usage",
        "worktreeBranch",
        "worktreePath",
    ),
)
CLAUDE_DERIVED_TOOL_RESULT_TEXT_FIELDS = (
    "agentId",
    "agentType",
    "description",
    "outputFile",
    "prompt",
    "resolvedModel",
    "sessionUrl",
    "status",
    "taskId",
    "worktreeBranch",
    "worktreePath",
)
CLAUDE_DERIVED_TOOL_RESULT_INTEGER_FIELDS = (
    "totalDurationMs",
    "totalTokens",
    "totalToolUseCount",
)
CLAUDE_DERIVED_TOOL_RESULT_JOB_KEYS = (
    "cron",
    "durable",
    "humanSchedule",
    "id",
    "prompt",
    "recurring",
)
CLAUDE_EXIT_PLAN_ALLOWED_PROMPT_INPUT_KEYS = ("allowedPrompts", "plan", "planFilePath")
CLAUDE_EXIT_PLAN_ALLOWED_PROMPT_KEYS = ("prompt", "tool")
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
OPENCODE_ASSISTANT_MESSAGE_KEYSETS = (
    ("agent", "cost", "mode", "modelID", "parentID", "path", "providerID", "role", "time", "tokens"),
    (
        "agent",
        "cost",
        "finish",
        "mode",
        "modelID",
        "parentID",
        "path",
        "providerID",
        "role",
        "time",
        "tokens",
    ),
)
OPENCODE_TASK_TOOL_PART_KEYS = ("callID", "state", "tool", "type")
OPENCODE_TASK_TOOL_STATE_KEYSETS = {
    "running": ("input", "metadata", "status", "time", "title"),
    "completed": ("input", "metadata", "output", "status", "time", "title"),
}
OPENCODE_TASK_TOOL_INPUT_KEYSETS = (
    ("description", "prompt", "subagent_type"),
    ("command", "description", "prompt", "subagent_type"),
)
OPENCODE_TASK_TOOL_METADATA_KEYSETS = (
    ("model", "parentSessionId", "sessionId"),
    ("model", "parentSessionId", "sessionId", "truncated"),
    ("model", "outputPath", "parentSessionId", "sessionId", "truncated"),
)
OPENCODE_TASK_TOOL_TIME_KEYSETS = {
    "running": ("start",),
    "completed": ("end", "start"),
}
OPENCODE_USER_SUMMARY_KEYS = ("diffs",)
OPENCODE_USER_SUMMARY_DIFF_KEYS = ("additions", "deletions", "file", "patch", "status")
OPENCODE_USER_SUMMARY_MAX_BYTES = 512 * 1024 * 1024
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
    "codex-session-jsonl-v2": {
        "source": "codex-sessions",
        "record_keys": CODEX_USER_RECORD_KEYS,
        "canonical_identity": "one-id-or-one-filename-bound-id",
        "response_item": {
            "payload_keysets": CODEX_RESPONSE_USER_PAYLOAD_KEYSETS,
            "content_block_keysets": CODEX_USER_CONTENT_BLOCK_KEYSETS,
            "text_block": "input_text",
            "media_block": {
                "type": "input_image",
                "detail": "high",
                "encoding": "data:image/png;base64",
                "atomization": "nontext-occurrence-only",
            },
        },
        "event_msg": {
            "payload_keysets": CODEX_EVENT_USER_PAYLOAD_KEYSETS,
            "local_image_role": "transport-reference",
            "image_placeholder_regex": r"\[Image #[1-9][0-9]*\]",
            "binding": "nearest-preceding-exact-text-and-cardinality",
        },
        "compacted": {
            "payload_keysets": CODEX_COMPACTED_PAYLOAD_KEYSETS,
            "message": "exact-empty-string",
            "replacement_message_keysets": CODEX_COMPACTED_MESSAGE_KEYSETS,
            "compaction_item_keysets": CODEX_COMPACTION_ITEM_KEYSETS,
            "user_authority": "derived-continuation-context",
            "developer_role": "non-operator-context",
        },
    },
    "claude-project-jsonl-v1": {
        "source": "claude-projects",
        "suffix": ".jsonl",
        "max_probe_bytes": 67108864,
        "max_records": 100000,
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
        "derived_tool_result_prompt": {
            "record_marker": "sourceToolAssistantUUID",
            "object_field": "toolUseResult",
            "exact_keysets": CLAUDE_DERIVED_TOOL_RESULT_PROMPT_KEYSETS,
            "text_fields": CLAUDE_DERIVED_TOOL_RESULT_TEXT_FIELDS,
            "integer_fields": CLAUDE_DERIVED_TOOL_RESULT_INTEGER_FIELDS,
            "boolean_fields": ["canReadOutputFile", "isAsync"],
            "list_fields": ["content"],
            "object_fields": ["toolStats", "usage"],
            "prompt_field": "prompt",
            "provenance": "delegated_task_frame",
            "authority": "derived",
        },
        "derived_tool_result_jobs": {
            "record_marker": "sourceToolAssistantUUID",
            "object_field": "toolUseResult",
            "exact_object_keys": ["jobs"],
            "exact_job_keys": CLAUDE_DERIVED_TOOL_RESULT_JOB_KEYS,
            "prompt_field": "prompt",
            "provenance": "delegated_task_frame",
            "authority": "derived",
        },
        "exit_plan_allowed_prompts": {
            "tool_name": "ExitPlanMode",
            "exact_input_keys": CLAUDE_EXIT_PLAN_ALLOWED_PROMPT_INPUT_KEYS,
            "exact_item_keys": CLAUDE_EXIT_PLAN_ALLOWED_PROMPT_KEYS,
            "prompt_field": "prompt",
            "provenance": "delegated_task_frame",
            "authority": "derived",
        },
        "attachment_prompt_value_shapes": {
            "hook_additional_context": ["string", "list[string]"],
            "queued_command": ["string", "list[text-block]"],
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
        "excluded_summary": {
            "keys": OPENCODE_USER_SUMMARY_KEYS,
            "diff_keys": OPENCODE_USER_SUMMARY_DIFF_KEYS,
            "max_bytes": OPENCODE_USER_SUMMARY_MAX_BYTES,
            "diff_field_types": {
                "additions": "integer",
                "deletions": "integer",
                "file": "text",
                "patch": "text",
                "status": "text",
            },
            "disposition": "provider-generated-patch-context",
        },
        "unit_signature_fields": OPENCODE_UNIT_SIGNATURE_FIELDS,
    },
    "opencode-assistant-task-v1": SOURCE_ADAPTER_RULES["opencode-assistant-task-v1"],
    "agy-conversation-v1": {
        "source": "agy-cli-conversations",
        "table": "steps",
        "required_columns": [
            "idx",
            "step_type",
            "status",
            "step_payload",
            "metadata",
            "task_details",
            "error_details",
            "render_info",
        ],
        "admitted_columns": [
            "has_subtrajectory",
            "permissions",
            "step_format",
        ],
        "identity_columns": ["idx", "step_type", "status"],
        "identity_type": "exact-nonnegative-integer",
        "unique_index_column": "idx",
        "prompt_step_type": 14,
        "prompt_columns": [
            "step_payload",
            "metadata",
            "task_details",
            "error_details",
            "render_info",
        ],
        "prompt_carrier_cardinality": "exactly-one-grounded-source-segment",
        "binary_payload_envelope": {
            "envelope": "agy-step-payload-proto-v1",
            "encoding": "protobuf-wire-exact",
            "step_type_field": 1,
            "prompt_message_field": 19,
            "prompt_text_field": 2,
            "annotated_copy_message_field": 3,
            "annotated_copy_text_field": 1,
            "max_wire_depth": 8,
        },
        "nonprompt_exclusion_contract": "agy-conversation-nonprompt-v1",
        "max_prompt_candidates_per_record": 64,
        "max_json_nesting_depth": 128,
        "unknown_prompt_markers": [
            "prompt",
            "instructions",
            "role:user|human|operator",
            "type:user|human|operator|prompt",
        ],
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
        "agy-cli-conversations": (".gemini", "antigravity-cli", "conversations"),
        "codex-attachments": (".codex", "attachments"),
        "codex-sessions": (".codex", "sessions"),
        "claude-file-history": (".claude", "file-history"),
        "claude-plans": (".claude", "plans"),
        "claude-projects": (".claude", "projects"),
        "claude-tasks": (".claude", "tasks"),
        "opencode-db": (".local", "share", "opencode"),
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

    if contract_id == SOURCE_MISSING_EXCLUSION_ID:
        evidence = related_evidence or {}
        observed = evidence.get("observed_missing_at")
        return bool(
            isinstance(evidence, dict)
            and set(evidence) == {"observed_missing_at"}
            and isinstance(observed, str)
            and observed
        )

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

    def subagent_alias_evidence_valid() -> bool:
        detail = evidence.get("subagent_target")
        target_signature = related.get("subagent_target")
        if not isinstance(detail, dict) or not isinstance(target_signature, dict):
            return False
        target_locator = detail.get("target_locator")
        if not isinstance(target_locator, str) or not target_locator:
            return False
        source_parts = path.parts
        target_path = PurePath(target_locator)
        target_parts = target_path.parts
        marker = (".claude", "projects")
        source_indexes = [
            index
            for index in range(len(source_parts) - len(marker) + 1)
            if tuple(source_parts[index : index + len(marker)]) == marker
        ]
        target_indexes = [
            index
            for index in range(len(target_parts) - len(marker) + 1)
            if tuple(target_parts[index : index + len(marker)]) == marker
        ]
        if len(source_indexes) != 1 or len(target_indexes) != 1:
            return False
        source_relative = source_parts[source_indexes[0] + len(marker) :]
        target_relative = target_parts[target_indexes[0] + len(marker) :]
        if not (
            source_parts[: source_indexes[0]] == target_parts[: target_indexes[0]]
            and len(source_relative) == 4
            and len(target_relative) == 4
            and source_relative[0] == target_relative[0]
            and source_relative[1] != target_relative[1]
            and source_relative[2:] == target_relative[2:]
            and source_relative[2] == "subagents"
            and path.suffix.lower() in {".json", ".jsonl"}
            and target_path.suffix.lower() == path.suffix.lower()
        ):
            return False
        expected_locator_sha = hashlib.sha256(target_locator.encode("utf-8", errors="replace")).hexdigest()
        return bool(
            set(related) == {"subagent_target"}
            and set(evidence) == {"subagent_target"}
            and set(detail) == {"link_target_sha256", "locator_sha256", "target_locator"}
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
        "agy-conversation-v1": lambda: len(relative) == 1 and suffix == ".db",
        "agy-conversation-nonprompt-v1": lambda: len(relative) == 1 and suffix == ".db",
        "codex-pasted-text-attachment-v1": lambda: (
            len(relative) == 2
            and re.fullmatch(r"pasted-text-[1-9][0-9]*\.txt", path.name) is not None
            and set(related) == {"parent_session"}
        ),
        "opencode-assistant-task-v1": lambda: (
            len(relative) == 1
            and re.fullmatch(r"opencode\.db#session:[0-9a-f]{24}", relative[0]) is not None
            and set(related) == set()
        ),
        "codex-session-jsonl-v2": lambda: (
            len(relative) == 4
            and re.fullmatch(r"20[0-9]{2}", relative[0]) is not None
            and re.fullmatch(r"(?:0[1-9]|1[0-2])", relative[1]) is not None
            and re.fullmatch(r"(?:0[1-9]|[12][0-9]|3[01])", relative[2]) is not None
            and re.fullmatch(r"rollout-.+\.jsonl", relative[3]) is not None
        ),
        "claude-file-history-snapshot-v1": lambda: (
            len(relative) >= 1 and re.fullmatch(r"[0-9a-fA-F]+@v[0-9]+", path.name) is not None
        ),
        "claude-generated-plan-v1": lambda: len(relative) >= 1,
        "claude-project-memory-v1": lambda: len(relative) == 3 and relative[1] == "memory" and suffix == ".md",
        CLAUDE_PROJECT_MEMORY_ALIAS_ID: lambda: (
            len(relative) == 2 and suffix == ".md" and set(related) == {"memory_target"}
        ),
        CLAUDE_SUBAGENT_SESSION_ALIAS_ID: lambda: (
            len(relative) == 4
            and relative[2] == "subagents"
            and suffix in {".json", ".jsonl"}
            and set(related) == {"subagent_target"}
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
    if contract_id == CLAUDE_SUBAGENT_SESSION_ALIAS_ID:
        return subagent_alias_evidence_valid()
    if contract_id == "codex-pasted-text-attachment-v1":
        return codex_attachment_evidence_valid()
    return not evidence
