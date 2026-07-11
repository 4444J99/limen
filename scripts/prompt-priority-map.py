#!/usr/bin/env python3
"""Build the operational atom queue plus a legacy compatibility map.

The validated, all-scope ask-atom projection is the only control input.  This
script does not read raw app session files or prompt text.  Historical session
receipts and prompt hashes are retained as a clearly non-authoritative custody
view; they can never replace, reorder, or route the atom queue.

* tracked docs/prompt-priority-map.md: public-safe atom queue preview and compatibility context;
* ignored .limen-private/.../prompt-priority-map.json: complete atom queue and compatibility map.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
HOME = Path.home()
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS", ROOT / ".limen-private" / "session-corpus"))
PROMPT_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-lifecycle-index.json"
ATOM_INDEX = ROOT / "docs" / "prompt-atom-ledger.json"
CODEX_INDEX = PRIVATE_ROOT / "lifecycle" / "codex-session-lifecycle.json"
ATTACK_INDEX = PRIVATE_ROOT / "lifecycle" / "session-attack-paths.json"
BLOCKER_INDEX = PRIVATE_ROOT / "lifecycle" / "session-lifecycle-blockers.json"
CAPABILITY_INDEX = PRIVATE_ROOT / "lifecycle" / "capability-substrate-index.json"
DOC_PATH = ROOT / "docs" / "prompt-priority-map.md"
PRIVATE_INDEX = PRIVATE_ROOT / "lifecycle" / "prompt-priority-map.json"
ATOM_CHECK_RECEIPT = PRIVATE_ROOT / "prompt-atoms" / "prompt-atom-check-receipt.json"

SOURCE_WEIGHTS = {
    "codex-sessions": 8,
    "codex-history": 3,
    "claude-projects": 5,
    "claude-tasks": 4,
    "claude-plans": 2,
    "claude-file-history": 0,
    "codex-attachments": 0,
}

STATE_WEIGHTS = {
    "ALIVE": 18,
    "STALLED": 26,
    "PARKED": -22,
    "CLOSED": -8,
}

PARKED_SECRET_FAMILIES = {"auth_credentials"}
ATOM_DISPOSITIONS = {"unassessed", "not_done", "partial", "blocked", "done", "superseded"}
UNRESOLVED_DISPOSITIONS = ATOM_DISPOSITIONS - {"done", "superseded"}
ATOM_KINDS = {"ask", "correction", "constraint", "acceptance_criterion", "human_gate"}
ATOM_AUTHORITIES = {"operator", "derived", "unknown"}
SAFE_ROUTE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@#-]{0,159}$")
SAFE_ATOM_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SAFE_EVIDENCE_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class AtomProjectionError(RuntimeError):
    """The atom projection is not safe or complete enough to govern work."""


def _digest_like(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", str(value or "")))


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8", errors="replace")
    return hashlib.sha256(encoded).hexdigest()


def projection_digest_valid(atom_index: dict[str, Any]) -> bool:
    claimed = str(atom_index.get("projection_digest") or "")
    material = {key: value for key, value in atom_index.items() if key != "projection_digest"}
    return bool(_digest_like(claimed) and claimed == canonical_digest(material))


def _private_core_check(atom_index: dict[str, Any]) -> dict[str, Any] | None:
    """Use the canonical checker when its private journals are present."""

    private_dir = PRIVATE_ROOT / "prompt-atoms"
    if not any(
        (private_dir / name).exists()
        for name in ("prompt-events.jsonl", "prompt-atom-ledger.json", "source-cursor.json")
    ):
        return None
    cli_src = Path(__file__).resolve().parents[1] / "cli" / "src"
    if str(cli_src) not in sys.path:
        sys.path.insert(0, str(cli_src))
    corpus = importlib.import_module("limen.prompt_corpus")
    paths = corpus.LedgerPaths.for_root(
        ROOT,
        private_root=PRIVATE_ROOT,
        public_snapshot=ATOM_INDEX,
    )
    errors = corpus.check_ledger(paths, require_scope="all")
    if errors:
        raise AtomProjectionError("private atom checker failed: " + "; ".join(errors))
    marker = corpus.load_json(paths.private_snapshot)
    if marker.get("public_projection_digest") != atom_index.get("projection_digest"):
        raise AtomProjectionError("private atom checkpoint does not match projection_digest")
    return {
        "kind": "live_core_check",
        "checker": "limen.prompt_corpus.check_ledger",
        "result": "pass",
        "projection_digest": atom_index.get("projection_digest"),
    }


def verify_private_check_receipt(
    atom_index: dict[str, Any],
    *,
    projection_path: Path | None = None,
    receipt_path: Path | None = None,
    allow_live: bool = True,
) -> dict[str, Any]:
    """Require a private, hash-matched receipt for the exact public projection."""

    if allow_live:
        live = _private_core_check(atom_index)
        if live is not None:
            return live
    projection_path = projection_path or ATOM_INDEX
    receipt_path = receipt_path or ATOM_CHECK_RECEIPT
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8", errors="strict"))
        receipt_stat = receipt_path.stat()
        mode = receipt_stat.st_mode & 0o777
    except FileNotFoundError as exc:
        raise AtomProjectionError("missing trusted private atom check receipt") from exc
    except (OSError, UnicodeError, ValueError) as exc:
        raise AtomProjectionError(f"malformed private atom check receipt: {exc}") from exc
    if not isinstance(receipt, dict):
        raise AtomProjectionError("private atom check receipt must be a JSON object")
    if receipt_path.is_symlink() or receipt_stat.st_uid != os.getuid() or mode & 0o077:
        raise AtomProjectionError("private atom check receipt permissions are not private")
    required = {
        "version": 1,
        "kind": "prompt_atom_projection_check",
        "checker": "limen.prompt_corpus.check_ledger",
        "result": "pass",
        "projection_digest": atom_index.get("projection_digest"),
        "projection_file_sha256": hashlib.sha256(projection_path.read_bytes()).hexdigest(),
        "semantic_digest": atom_index.get("semantic_digest"),
        "policy_digest": atom_index.get("policy_digest"),
        "source_cursor_digest": atom_index.get("source_cursor_digest"),
    }
    mismatched = [key for key, expected in required.items() if receipt.get(key) != expected]
    if mismatched:
        raise AtomProjectionError("private atom check receipt does not match projection: " + ", ".join(mismatched))
    return {key: receipt[key] for key in required if key != "projection_file_sha256"}


def load_atom_projection(path: Path) -> dict[str, Any]:
    """Load the required atom projection strictly; optional indexes stay best-effort."""

    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AtomProjectionError(f"missing authoritative atom projection: {path}") from exc
    except OSError as exc:
        raise AtomProjectionError(f"cannot read authoritative atom projection {path}: {exc}") from exc
    except (UnicodeError, ValueError) as exc:
        raise AtomProjectionError(f"malformed authoritative atom projection {path}: {exc}") from exc
    if not isinstance(obj, dict):
        raise AtomProjectionError(f"authoritative atom projection must be a JSON object: {path}")
    return obj


def _nonnegative_int(value: Any, field: str, errors: list[str]) -> int:
    if isinstance(value, bool):
        errors.append(f"{field} must be a non-negative integer")
        return 0
    try:
        result = int(value)
    except (TypeError, ValueError):
        errors.append(f"{field} must be a non-negative integer")
        return 0
    if result < 0:
        errors.append(f"{field} must be a non-negative integer")
        return 0
    return result


def _validated_count_map(
    value: Any,
    field: str,
    errors: list[str],
) -> dict[str, int]:
    if not isinstance(value, dict):
        errors.append(f"{field} must be an object")
        return {}
    return {str(key): _nonnegative_int(count, f"{field}.{key}", errors) for key, count in value.items()}


def _reconcile_projection_counts(
    atom_index: dict[str, Any],
    rows: list[dict[str, Any]],
    form: str,
    errors: list[str],
) -> None:
    coverage = atom_index.get("coverage") if isinstance(atom_index.get("coverage"), dict) else {}
    total_atoms = _nonnegative_int(coverage.get("atoms"), "coverage.atoms", errors)
    current_intents = _nonnegative_int(
        coverage.get("current_intents"),
        "coverage.current_intents",
        errors,
    )
    current_unresolved = _nonnegative_int(
        coverage.get("current_unresolved_atoms"),
        "coverage.current_unresolved_atoms",
        errors,
    )
    counts = atom_index.get("counts")
    if not isinstance(counts, dict):
        errors.append("counts is missing")
        return
    dispositions = _validated_count_map(counts.get("dispositions"), "counts.dispositions", errors)
    kinds = _validated_count_map(counts.get("kinds"), "counts.kinds", errors)
    if set(dispositions) - ATOM_DISPOSITIONS:
        errors.append("counts.dispositions contains an invalid disposition")
    if set(kinds) - ATOM_KINDS:
        errors.append("counts.kinds contains an invalid kind")
    if sum(dispositions.values()) != total_atoms:
        errors.append("counts.dispositions does not reconcile with coverage.atoms")
    if sum(kinds.values()) != total_atoms:
        errors.append("counts.kinds does not reconcile with coverage.atoms")
    if current_intents > total_atoms:
        errors.append("coverage.current_intents exceeds coverage.atoms")
    if current_unresolved > current_intents:
        errors.append("coverage.current_unresolved_atoms exceeds coverage.current_intents")
    if len(rows) != current_unresolved:
        errors.append("unresolved atom rows do not match coverage.current_unresolved_atoms")

    row_dispositions = Counter(
        str(row.get("disposition") or (row.get("outcome") or {}).get("disposition") or "unassessed") for row in rows
    )
    if any(row_dispositions[key] > dispositions.get(key, 0) for key in row_dispositions):
        errors.append("unresolved atom disposition rows exceed projection counts")
    row_kinds = Counter(str(row.get("kind") or "") for row in rows)
    if any(row_kinds[key] > kinds.get(key, 0) for key in row_kinds):
        errors.append("unresolved atom kind rows exceed projection counts")
    if form == "full":
        raw_rows = [row for row in (atom_index.get("atoms") or []) if isinstance(row, dict)]
        actual_dispositions = Counter(
            str((row.get("outcome") or {}).get("disposition") or row.get("disposition") or "unassessed")
            for row in raw_rows
        )
        actual_kinds = Counter(str(row.get("kind") or "") for row in raw_rows)
        if dict(actual_dispositions) != dispositions:
            errors.append("full atom rows do not match counts.dispositions")
        if dict(actual_kinds) != kinds:
            errors.append("full atom rows do not match counts.kinds")
        actual_current = [row for row in raw_rows if row.get("is_current_intent") is True]
        actual_current_unresolved = [
            row
            for row in actual_current
            if str((row.get("outcome") or {}).get("disposition") or row.get("disposition") or "unassessed")
            in UNRESOLVED_DISPOSITIONS
        ]
        if len(actual_current) != current_intents:
            errors.append("full atom rows do not match coverage.current_intents")
        if len(actual_current_unresolved) != current_unresolved:
            errors.append("full atom rows do not match coverage.current_unresolved_atoms")


def _atom_rows(atom_index: dict[str, Any], errors: list[str]) -> tuple[list[dict[str, Any]], str]:
    """Return complete unresolved rows from either full or redacted projection form."""

    if "atoms" in atom_index:
        raw_rows = atom_index.get("atoms")
        if not isinstance(raw_rows, list):
            errors.append("atoms must be a list")
            return [], "full"
        rows = [row for row in raw_rows if isinstance(row, dict)]
        if len(rows) != len(raw_rows):
            errors.append("atoms contains a non-object row")
        coverage = atom_index.get("coverage") or {}
        expected = _nonnegative_int(coverage.get("atoms"), "coverage.atoms", errors)
        if expected != len(raw_rows):
            errors.append(f"coverage.atoms={expected} does not match {len(raw_rows)} atom rows")
        return [
            row
            for row in rows
            if row.get("is_current_intent", True)
            and str((row.get("outcome") or {}).get("disposition") or "unassessed") in UNRESOLVED_DISPOSITIONS
        ], "full"

    raw_rows = atom_index.get("unresolved_atoms")
    if not isinstance(raw_rows, list):
        errors.append("projection lacks atoms or unresolved_atoms")
        return [], "redacted"
    rows = [row for row in raw_rows if isinstance(row, dict)]
    if len(rows) != len(raw_rows):
        errors.append("unresolved_atoms contains a non-object row")
    if "unresolved_atoms_truncated" not in atom_index:
        errors.append("redacted projection lacks unresolved_atoms_truncated completeness proof")
    truncated = _nonnegative_int(
        atom_index.get("unresolved_atoms_truncated", 0),
        "unresolved_atoms_truncated",
        errors,
    )
    if truncated:
        errors.append(f"unresolved atom projection is truncated by {truncated} row(s)")
    return rows, "redacted"


def validate_atom_projection(atom_index: dict[str, Any]) -> tuple[list[dict[str, Any]], str]:
    """Require verified, exact all-scope atom truth before any prioritization."""

    errors: list[str] = []
    if atom_index.get("version") != 1:
        errors.append("unsupported or missing atom projection version")
    declared_authority = atom_index.get("authority")
    if declared_authority not in (None, "prompt_atom_projection") or "legacy_compatibility" in atom_index:
        errors.append("legacy or foreign projection authority is not accepted")
    if not projection_digest_valid(atom_index):
        errors.append("projection_digest is missing or does not match projection content")
    for field in ("semantic_digest", "policy_digest", "source_cursor_digest"):
        if not _digest_like(atom_index.get(field)):
            errors.append(f"{field} must be a 64-character lowercase hex digest")

    validation = atom_index.get("validation")
    if not isinstance(validation, dict) or validation.get("ok") is not True:
        errors.append("atom projection validation is not PASS")
    if isinstance(validation, dict) and validation.get("errors"):
        errors.append("atom projection reports validation errors")

    scope = atom_index.get("source_scope")
    if not isinstance(scope, dict):
        errors.append("source_scope is missing")
        scope = {}
    if scope.get("scope") != "all" or scope.get("target_scope") != "all":
        errors.append("atom projection scope must be exact all/all")
    if _nonnegative_int(scope.get("pending_files", 0), "source_scope.pending_files", errors):
        errors.append("atom projection still has pending source files")
    source_error_count = _nonnegative_int(
        scope.get("source_error_count", len(scope.get("source_errors") or [])),
        "source_scope.source_error_count",
        errors,
    )
    if source_error_count or scope.get("source_errors"):
        errors.append("atom projection has source errors")
    adapter_gaps = scope.get("adapter_gaps")
    adapter_gap_routes = scope.get("adapter_gap_routes")
    if not isinstance(adapter_gaps, list) or not isinstance(adapter_gap_routes, list):
        errors.append("atom projection adapter gap fields must be lists")
    if adapter_gaps or adapter_gap_routes:
        errors.append("atom projection has unresolved adapter gaps or routes")
    if not _digest_like(scope.get("source_manifest_digest")):
        errors.append("source_scope.source_manifest_digest is missing or malformed")

    coverage = atom_index.get("coverage")
    if not isinstance(coverage, dict):
        errors.append("coverage is missing")
    else:
        _nonnegative_int(coverage.get("atoms"), "coverage.atoms", errors)

    rows, form = _atom_rows(atom_index, errors)
    _reconcile_projection_counts(atom_index, rows, form, errors)
    seen: set[str] = set()
    for index, row in enumerate(rows):
        atom_id = str(row.get("atom_id") or "")
        if not atom_id:
            errors.append(f"unresolved atom row {index} lacks atom_id")
        elif not SAFE_ATOM_ID.fullmatch(atom_id):
            errors.append(f"unresolved atom row {index} has an unsafe atom_id")
        elif atom_id in seen:
            errors.append(f"duplicate unresolved atom_id: {atom_id}")
        seen.add(atom_id)
        disposition = str(row.get("disposition") or (row.get("outcome") or {}).get("disposition") or "unassessed")
        if disposition not in UNRESOLVED_DISPOSITIONS:
            errors.append(f"{atom_id or index}: unresolved row has terminal/invalid disposition {disposition}")
        if str(row.get("kind") or "") not in ATOM_KINDS:
            errors.append(f"{atom_id or index}: kind is missing or invalid")
        if str(row.get("authority") or "") not in ATOM_AUTHORITIES:
            errors.append(f"{atom_id or index}: authority is missing or invalid")
        score = row.get("priority_score")
        if (
            isinstance(score, bool)
            or not isinstance(score, (int, float))
            or not math.isfinite(float(score))
            or not 0.0 <= float(score) <= 100.0
        ):
            errors.append(f"{atom_id or index}: priority_score must be finite numeric evidence")
        reasons = row.get("priority_reasons")
        if not isinstance(reasons, list):
            errors.append(f"{atom_id or index}: priority_reasons must be a list")
        elif any(not SAFE_EVIDENCE_KEY.fullmatch(str(value)) for value in reasons):
            errors.append(f"{atom_id or index}: priority_reasons contains an unsafe key")
        dimensions = row.get("dimensions")
        if not isinstance(dimensions, dict):
            errors.append(f"{atom_id or index}: dimensions must be an object")
        else:
            for key, value in dimensions.items():
                if not SAFE_EVIDENCE_KEY.fullmatch(str(key)):
                    errors.append(f"{atom_id or index}: dimensions contains an unsafe key")
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                    or not 0.0 <= float(value) <= 1.0
                ):
                    errors.append(f"{atom_id or index}: dimension {key} must be finite in [0,1]")

    if errors:
        raise AtomProjectionError("; ".join(dict.fromkeys(errors)))
    return rows, form


def _safe_route_label(value: Any, fallback: str) -> str:
    label = str(value or "").strip()
    return label if SAFE_ROUTE_LABEL.fullmatch(label) else fallback


def _route_metadata(atom: dict[str, Any]) -> tuple[str, str]:
    outcome = atom.get("outcome") if isinstance(atom.get("outcome"), dict) else {}
    owner = _safe_route_label(atom.get("owner") or outcome.get("owner"), "unassigned")
    route = _safe_route_label(
        atom.get("owner_route")
        or atom.get("route_to")
        or atom.get("route")
        or outcome.get("owner_route")
        or outcome.get("route_to")
        or outcome.get("route"),
        "unrouted",
    )
    return owner, route


def build_atom_items(atom_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build the complete control queue without copying private prompt bodies."""

    items: list[dict[str, Any]] = []
    for atom in atom_rows:
        outcome = atom.get("outcome") if isinstance(atom.get("outcome"), dict) else {}
        disposition = str(atom.get("disposition") or outcome.get("disposition") or "unassessed")
        owner, route = _route_metadata(atom)
        items.append(
            {
                "atom_id": str(atom["atom_id"]),
                "kind": str(atom.get("kind") or "ask"),
                "authority": str(atom.get("authority") or "unknown"),
                "priority_score": float(atom["priority_score"]),
                "priority_reasons": [str(value) for value in atom.get("priority_reasons") or []],
                "dimensions": {str(key): float(value) for key, value in (atom.get("dimensions") or {}).items()},
                "disposition": disposition,
                "owner": owner,
                "route": route,
                "routed": owner != "unassigned" or route != "unrouted",
                "candidate_predecessor_count": len(atom.get("candidate_predecessor_ids") or []),
                "dependency_count": len(atom.get("dependency_ids") or []),
            }
        )
    return sorted(items, key=lambda item: (-item["priority_score"], item["atom_id"]))


def build_atom_owner_queues(atom_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group unresolved work by explicit atom metadata, never by legacy sessions."""

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for atom in atom_items:
        grouped[(str(atom["owner"]), str(atom["route"]))].append(atom)
    queues: list[dict[str, Any]] = []
    for (owner, route), rows in grouped.items():
        rows.sort(key=lambda row: (-float(row["priority_score"]), str(row["atom_id"])))
        queue_hash = hashlib.sha256(f"{owner}\0{route}".encode()).hexdigest()[:16]
        queues.append(
            {
                "queue_id": f"atom-owner-{queue_hash}",
                "owner": owner,
                "route": route,
                "routed": any(bool(row["routed"]) for row in rows),
                "atom_count": len(rows),
                "atom_ids": [str(row["atom_id"]) for row in rows],
                "top_priority_score": float(rows[0]["priority_score"]),
                "dispositions": dict(Counter(str(row["disposition"]) for row in rows).most_common()),
            }
        )
    return sorted(
        queues,
        key=lambda row: (
            -float(row["top_priority_score"]),
            not bool(row["routed"]),
            str(row["owner"]),
            str(row["route"]),
        ),
    )


def load_json(path: Path) -> dict[str, Any]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return obj if isinstance(obj, dict) else {}


def relpath(path: Path) -> str:
    try:
        return "~/" + str(path.expanduser().resolve().relative_to(HOME))
    except (OSError, ValueError):
        return str(path)


def parse_ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def recency_score(value: Any, now: dt.datetime) -> tuple[int, str]:
    parsed = parse_ts(value)
    if parsed is None:
        return 0, "unknown"
    age = now - parsed
    if age.total_seconds() < 0:
        return 18, "future/clock-skew"
    days = age.total_seconds() / 86400
    if days <= 1:
        return 20, "<=1d"
    if days <= 7:
        return 14, "<=7d"
    if days <= 30:
        return 8, "<=30d"
    if days <= 120:
        return 3, "<=120d"
    return 1, ">120d"


def priority_band(score: int) -> str:
    if score >= 90:
        return "critical"
    if score >= 70:
        return "high"
    if score >= 50:
        return "medium"
    if score >= 30:
        return "low"
    return "parked"


def band_rank(band: str) -> int:
    return {"critical": 0, "high": 1, "medium": 2, "low": 3, "parked": 4}.get(band, 5)


def compact_counts(counter: Counter[str], *, limit: int = 5) -> dict[str, int]:
    return dict(counter.most_common(limit))


def public_counts(counter: Counter[str], *, limit: int = 3) -> str:
    bits = [f"`{key}` {value}" for key, value in counter.most_common(limit)]
    return ", ".join(bits) if bits else "none"


def codex_lookups(
    codex: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_key = {}
    by_session_hash = {}
    by_path = {}
    for session in codex.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        key = session.get("session_key")
        if key:
            by_key[str(key)] = session
        session_id_hash = session.get("session_id_hash")
        if session_id_hash:
            by_session_hash[str(session_id_hash)] = session
        path = session.get("path")
        if path:
            by_path[str(path)] = session
    return by_key, by_session_hash, by_path


def codex_meta_for_session(
    session: dict[str, Any],
    by_key: dict[str, dict[str, Any]],
    by_session_hash: dict[str, dict[str, Any]],
    by_path: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    session_key = str(session.get("session_key") or "")
    if session_key in by_key:
        return by_key[session_key]
    session_id_hash = str(session.get("session_id_hash") or "")
    if session_id_hash:
        for codex_hash, meta in by_session_hash.items():
            if codex_hash.startswith(session_id_hash) or session_id_hash.startswith(codex_hash):
                return meta
    path = str(session.get("path") or "")
    return by_path.get(path, {})


def attack_lookups(attack: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    worktrees = {}
    families = {}
    for path in attack.get("ranked_paths") or []:
        if not isinstance(path, dict):
            continue
        kind = path.get("kind")
        path_id = path.get("id")
        if not path_id:
            continue
        if kind == "worktree":
            worktrees[str(path_id)] = path
        elif kind == "family":
            families[str(path_id)] = path
    return worktrees, families


def lane_for_session(
    session: dict[str, Any],
    codex_meta: dict[str, Any],
    worktree_path: dict[str, Any] | None,
    family_path: dict[str, Any] | None,
) -> str:
    family = str(codex_meta.get("family") or "uncategorized")
    state = str(codex_meta.get("state") or "")
    if family in PARKED_SECRET_FAMILIES:
        return "parked-secret"
    if worktree_path:
        return str(worktree_path.get("lane") or "worktree-review")
    if family == "uncategorized" and session.get("worktree_slug"):
        return "historical-worktree-review"
    if state == "STALLED":
        return "stalled-review"
    if family_path:
        return str(family_path.get("lane") or "family-review")
    if str(session.get("source") or "").startswith("claude"):
        return "legacy-session-review"
    return "hash-review"


def next_action_for_session(
    session: dict[str, Any],
    codex_meta: dict[str, Any],
    worktree_path: dict[str, Any] | None,
    family_path: dict[str, Any] | None,
    lane: str,
) -> str:
    family = str(codex_meta.get("family") or "uncategorized")
    if family in PARKED_SECRET_FAMILIES:
        return "Keep parked unless a scoped account/setup task directly requires non-secret prep."
    if worktree_path and worktree_path.get("next_action"):
        return str(worktree_path["next_action"])
    if family_path and family_path.get("next_action"):
        return str(family_path["next_action"])
    if lane == "stalled-review":
        return "Privately inspect the session receipt, then promote a task packet or write a blocker receipt."
    if lane == "historical-worktree-review":
        return "Privately inspect the historical worktree session, then route it to preservation, supersession, or archive proof."
    if lane == "legacy-session-review":
        return "Sample the private source file, extract durable atoms, then route to an owner ledger."
    source = str(session.get("source") or "unknown")
    return f"Review the redacted `{source}` receipt privately and assign an owner route before delegation."


def score_session(
    session: dict[str, Any],
    codex_meta: dict[str, Any],
    worktree_path: dict[str, Any] | None,
    family_path: dict[str, Any] | None,
    now: dt.datetime,
) -> tuple[int, str]:
    prompt_hashes = [str(value) for value in session.get("prompt_hashes") or [] if value]
    prompt_events = int(session.get("prompt_event_count") or len(prompt_hashes))
    unique_prompts = len(set(prompt_hashes))
    duplicate_events = max(0, prompt_events - unique_prompts)
    source = str(session.get("source") or "unknown")
    family = str(codex_meta.get("family") or "uncategorized")
    state = str(codex_meta.get("state") or "")
    score = 10
    score += SOURCE_WEIGHTS.get(source, 1)
    score += min(20, prompt_events // 5)
    score += min(14, unique_prompts // 5)
    score += min(10, int(session.get("prompt_bytes") or 0) // 50000)
    score += min(10, duplicate_events // 3)
    recent_score, recent_label = recency_score(
        session.get("last_event") or session.get("mtime") or codex_meta.get("mtime"),
        now,
    )
    score += recent_score
    score += STATE_WEIGHTS.get(state, 0)
    if worktree_path:
        score += int(int(worktree_path.get("score") or 0) * 0.45)
        lane = str(worktree_path.get("lane") or "")
        if lane == "documented-residue":
            score -= 35
        elif lane == "observe":
            score -= 18
        elif lane == "owner-blocker":
            score += 8
    elif family_path:
        score += int(int(family_path.get("score") or 0) * 0.40)
    if session.get("worktree_slug"):
        score += 10
    if state == "STALLED":
        score += 8
    if family == "uncategorized":
        score += 12
    if family in PARKED_SECRET_FAMILIES:
        score -= 45
    return score, recent_label


def build_session_items(
    prompt: dict[str, Any],
    codex: dict[str, Any],
    attack: dict[str, Any],
    now: dt.datetime,
) -> list[dict[str, Any]]:
    codex_by_key, codex_by_session_hash, codex_by_path = codex_lookups(codex)
    worktree_paths, family_paths = attack_lookups(attack)
    items = []
    for session in prompt.get("sessions") or []:
        if not isinstance(session, dict):
            continue
        prompt_hashes = [str(value) for value in session.get("prompt_hashes") or [] if value]
        prompt_events = int(session.get("prompt_event_count") or len(prompt_hashes))
        if prompt_events <= 0:
            continue
        session_key = str(session.get("session_key") or "")
        codex_meta = codex_meta_for_session(session, codex_by_key, codex_by_session_hash, codex_by_path)
        worktree_slug = str(session.get("worktree_slug") or "")
        family = str(codex_meta.get("family") or "uncategorized")
        worktree_path = worktree_paths.get(worktree_slug) if worktree_slug else None
        family_path = family_paths.get(family) if family != "uncategorized" else None
        score, recency = score_session(session, codex_meta, worktree_path, family_path, now)
        lane = lane_for_session(session, codex_meta, worktree_path, family_path)
        if lane == "parked-secret":
            score = min(score, 29)
        item = {
            "session_key": session_key,
            "session_id_hash": session.get("session_id_hash"),
            "source": session.get("source") or "unknown",
            "family": family,
            "state": codex_meta.get("state") or "unclassified",
            "owner": codex_meta.get("owner") or "unassigned",
            "route": codex_meta.get("route") or "",
            "worktree_slug": worktree_slug or None,
            "cwd_hash": session.get("cwd_hash") or codex_meta.get("cwd_hash"),
            "score": score,
            "band": priority_band(score),
            "lane": lane,
            "recency": recency,
            "prompt_events": prompt_events,
            "unique_prompt_hashes": len(set(prompt_hashes)),
            "duplicate_prompt_events": max(0, prompt_events - len(set(prompt_hashes))),
            "event_count": int(session.get("event_count") or 0),
            "prompt_bytes": int(session.get("prompt_bytes") or 0),
            "first_event": session.get("first_event") or codex_meta.get("first_event"),
            "last_event": session.get("last_event") or codex_meta.get("last_event") or session.get("mtime"),
            "first_prompt_hash": session.get("first_prompt_hash"),
            "last_prompt_hash": session.get("last_prompt_hash"),
            "prompt_hashes": prompt_hashes,
            "next_action": next_action_for_session(session, codex_meta, worktree_path, family_path, lane),
            "attack_path": {
                "kind": (worktree_path or family_path or {}).get("kind"),
                "id": (worktree_path or family_path or {}).get("id"),
                "score": (worktree_path or family_path or {}).get("score"),
            },
            "private_source_path": session.get("path"),
            "private_display_path": session.get("display_path"),
        }
        items.append(item)
    return sorted(
        items,
        key=lambda item: (
            band_rank(str(item["band"])),
            -int(item["score"]),
            str(item["lane"]),
            str(item["session_key"]),
        ),
    )


def build_prompt_units(session_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    units: dict[str, dict[str, Any]] = {}
    for session in session_items:
        seen_in_session = set()
        for prompt_hash in session["prompt_hashes"]:
            item = units.setdefault(
                prompt_hash,
                {
                    "prompt_hash": prompt_hash,
                    "occurrences": 0,
                    "session_keys": set(),
                    "sources": Counter(),
                    "families": Counter(),
                    "lanes": Counter(),
                    "bands": Counter(),
                    "worktrees": Counter(),
                    "max_score": int(session["score"]),
                    "representative_session_key": session["session_key"],
                    "latest_event": session.get("last_event"),
                },
            )
            item["occurrences"] += 1
            item["session_keys"].add(session["session_key"])
            item["sources"][str(session["source"])] += 1
            item["families"][str(session["family"])] += 1
            item["lanes"][str(session["lane"])] += 1
            item["bands"][str(session["band"])] += 1
            if session.get("worktree_slug"):
                item["worktrees"][str(session["worktree_slug"])] += 1
            if int(session["score"]) > int(item["max_score"]):
                item["max_score"] = int(session["score"])
                item["representative_session_key"] = session["session_key"]
            if session.get("last_event") and (
                not item.get("latest_event") or str(session["last_event"]) > str(item["latest_event"])
            ):
                item["latest_event"] = session["last_event"]
            seen_in_session.add(prompt_hash)
        for prompt_hash in seen_in_session:
            units[prompt_hash]["session_count"] = len(units[prompt_hash]["session_keys"])
    rows = []
    for item in units.values():
        rows.append(
            {
                "prompt_hash": item["prompt_hash"],
                "occurrences": item["occurrences"],
                "session_count": len(item["session_keys"]),
                "session_keys": sorted(item["session_keys"]),
                "sources": dict(item["sources"].most_common()),
                "families": dict(item["families"].most_common()),
                "lanes": dict(item["lanes"].most_common()),
                "bands": dict(item["bands"].most_common()),
                "worktrees": dict(item["worktrees"].most_common()),
                "max_score": item["max_score"],
                "representative_session_key": item["representative_session_key"],
                "latest_event": item.get("latest_event"),
            }
        )
    return sorted(rows, key=lambda row: (-int(row["max_score"]), -int(row["occurrences"]), row["prompt_hash"]))


def build_review_batches(session_items: list[dict[str, Any]], *, batch_size: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in session_items:
        grouped[(str(item["band"]), str(item["lane"]))].append(item)

    batches = []
    for (band, lane), rows in grouped.items():
        rows = sorted(rows, key=lambda item: (-int(item["score"]), str(item["session_key"])))
        for index in range(0, len(rows), batch_size):
            chunk = rows[index : index + batch_size]
            prompt_hashes = {h for item in chunk for h in item["prompt_hashes"]}
            source_counts = Counter(str(item["source"]) for item in chunk)
            family_counts = Counter(str(item["family"]) for item in chunk)
            worktree_counts = Counter(str(item["worktree_slug"]) for item in chunk if item.get("worktree_slug"))
            batch_number = index // batch_size + 1
            scores = [int(item["score"]) for item in chunk]
            top = chunk[0]
            batches.append(
                {
                    "id": f"prompt-batch-{band}-{lane}-{batch_number:03d}",
                    "band": band,
                    "lane": lane,
                    "session_count": len(chunk),
                    "prompt_events": sum(int(item["prompt_events"]) for item in chunk),
                    "unique_prompt_hashes": len(prompt_hashes),
                    "max_score": max(scores),
                    "avg_score": round(sum(scores) / len(scores), 1),
                    "sources": compact_counts(source_counts),
                    "families": compact_counts(family_counts),
                    "worktrees": dict(worktree_counts.most_common()),
                    "top_session_key": top["session_key"],
                    "next_action": top["next_action"],
                    "session_keys": [item["session_key"] for item in chunk],
                    "prompt_hashes": sorted(prompt_hashes),
                }
            )
    return sorted(
        batches,
        key=lambda item: (
            band_rank(str(item["band"])),
            -int(item["max_score"]),
            -int(item["prompt_events"]),
            str(item["lane"]),
            str(item["id"]),
        ),
    )


def lane_task_map(session_items: list[dict[str, Any]], batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_lane: dict[str, list[dict[str, Any]]] = defaultdict(list)
    batch_counts = Counter(str(batch["lane"]) for batch in batches)
    for item in session_items:
        by_lane[str(item["lane"])].append(item)
    rows = []
    for lane, items in by_lane.items():
        sorted_items = sorted(items, key=lambda item: (-int(item["score"]), str(item["session_key"])))
        top = sorted_items[0]
        rows.append(
            {
                "lane": lane,
                "sessions": len(items),
                "prompt_events": sum(int(item["prompt_events"]) for item in items),
                "batches": int(batch_counts.get(lane, 0)),
                "top_band": top["band"],
                "top_score": int(top["score"]),
                "dominant_family": Counter(str(item["family"]) for item in items).most_common(1)[0][0],
                "dominant_source": Counter(str(item["source"]) for item in items).most_common(1)[0][0],
                "route": top["next_action"],
            }
        )
    return sorted(rows, key=lambda item: (band_rank(str(item["top_band"])), -int(item["top_score"]), item["lane"]))


def build_snapshot(batch_size: int) -> dict[str, Any]:
    atom_index = load_atom_projection(ATOM_INDEX)
    atom_rows, atom_projection_form = validate_atom_projection(atom_index)
    private_check = verify_private_check_receipt(atom_index)
    atom_items = build_atom_items(atom_rows)
    atom_owner_queues = build_atom_owner_queues(atom_items)

    # Everything below is legacy custody context.  It is deliberately computed
    # only after atom truth passes and is never an input to either atom queue.
    prompt = load_json(PROMPT_INDEX)
    codex = load_json(CODEX_INDEX)
    attack = load_json(ATTACK_INDEX)
    blockers = load_json(BLOCKER_INDEX)
    capability = load_json(CAPABILITY_INDEX)
    now = dt.datetime.now(dt.timezone.utc)
    session_items = build_session_items(prompt, codex, attack, now)
    prompt_units = build_prompt_units(session_items)
    batches = build_review_batches(session_items, batch_size=max(1, batch_size))
    for row in batches:
        row["authority"] = "legacy_compatibility_only"
        row["governs_execution"] = False
    for row in session_items:
        row["authority"] = "legacy_compatibility_only"
        row["governs_execution"] = False
    lane_map = lane_task_map(session_items, batches)
    for row in lane_map:
        row["authority"] = "legacy_compatibility_only"
        row["governs_execution"] = False
    source_counts = Counter(str(item["source"]) for item in session_items)
    family_counts = Counter(str(item["family"]) for item in session_items)
    lane_counts = Counter(str(item["lane"]) for item in session_items)
    band_counts = Counter(str(item["band"]) for item in session_items)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "control": {
            "authority": "prompt_atom_projection",
            "healthy": True,
            "scope": "all",
            "governing_unit": "atom_id",
            "semantic_digest": atom_index["semantic_digest"],
            "policy_digest": atom_index["policy_digest"],
            "source_cursor_digest": atom_index["source_cursor_digest"],
            "projection_form": atom_projection_form,
            "projection_digest": atom_index["projection_digest"],
            "private_check": private_check,
            "legacy_can_override": False,
        },
        "inputs": {
            "prompt_lifecycle_index": {"path": str(PROMPT_INDEX), "present": bool(prompt)},
            "prompt_atom_ledger": {"path": str(ATOM_INDEX), "present": bool(atom_index)},
            "codex_session_lifecycle": {"path": str(CODEX_INDEX), "present": bool(codex)},
            "session_attack_paths": {"path": str(ATTACK_INDEX), "present": bool(attack)},
            "session_lifecycle_blockers": {"path": str(BLOCKER_INDEX), "present": bool(blockers)},
            "capability_substrate": {"path": str(CAPABILITY_INDEX), "present": bool(capability)},
        },
        "coverage": {
            "prompt_index_files": sum(int(s.get("files", 0)) for s in prompt.get("sources", []) if isinstance(s, dict)),
            "prompt_index_events": sum(
                int(s.get("prompt_events", 0)) for s in prompt.get("sources", []) if isinstance(s, dict)
            ),
            "prioritized_sessions": len(session_items),
            "prioritized_prompt_events": sum(int(item["prompt_events"]) for item in session_items),
            "unique_prompt_hashes": len(prompt_units),
            "prompt_atoms": int((atom_index.get("coverage") or {}).get("atoms") or 0),
            "current_unresolved_prompt_atoms": len(atom_items),
            "prompt_atom_scope": "all",
            "atom_owner_queues": len(atom_owner_queues),
            "unrouted_prompt_atoms": sum(1 for item in atom_items if not item["routed"]),
            "legacy_review_batches": len(batches),
            "legacy_codex_classified_sessions": codex.get("session_count", 0),
            "legacy_attack_paths": len(attack.get("ranked_paths") or []),
            "legacy_blockers": len(blockers.get("blockers") or []),
            "legacy_capability_activation_items": len(capability.get("activation_queue") or []),
        },
        "counts": {
            "sources": dict(source_counts.most_common()),
            "families": dict(family_counts.most_common()),
            "lanes": dict(lane_counts.most_common()),
            "bands": dict(band_counts.most_common()),
            "atom_dispositions": (atom_index.get("counts") or {}).get("dispositions") or {},
            "atom_kinds": (atom_index.get("counts") or {}).get("kinds") or {},
        },
        "atom_control_queue": atom_items,
        "atom_owner_queues": atom_owner_queues,
        "legacy_compatibility": {
            "authoritative": False,
            "governs_execution": False,
            "reason": "sessions, hashes, batches, and lanes are custody containers, not ask truth",
            "lane_task_map": lane_map,
            "review_batches": batches,
            "session_items": session_items,
            "prompt_units": prompt_units,
        },
        "private_index": str(PRIVATE_INDEX),
    }


def render_markdown(snapshot: dict[str, Any], *, limit: int) -> str:
    control = snapshot.get("control") or {}
    if control.get("healthy") is not True or control.get("authority") != "prompt_atom_projection":
        raise AtomProjectionError("refusing to render without a healthy authoritative atom projection")
    coverage = snapshot["coverage"]
    counts = snapshot["counts"]
    compatibility = snapshot.get("legacy_compatibility") or {}
    if compatibility.get("authoritative") is not False or compatibility.get("governs_execution") is not False:
        raise AtomProjectionError("legacy compatibility data is missing its non-authority boundary")
    batches = (compatibility.get("review_batches") or [])[:limit]
    sessions = (compatibility.get("session_items") or [])[:limit]
    atoms = snapshot.get("atom_control_queue", [])[:limit]
    owner_queues = snapshot.get("atom_owner_queues", [])
    lines = [
        "# Prompt Priority Map",
        "",
        f"Generated: `{snapshot['generated_at']}`",
        "",
        "## Canonical Decision",
        "",
        "- The governing unit is an individual ask atom identified by `atom_id`. Only the validated, exact all-scope atom projection controls ranking and routing.",
        "- Every prompt occurrence is covered by atoms or an explicit exclusion in the private ledger; tracked docs show opaque IDs and numeric evidence, never prompt text.",
        "- Atom priority comes from the live prompt-corpus policy and current lineage/evidence, not a fixed topic, provider, or model table.",
        "- Sessions, hashes, review batches, and legacy lanes are compatibility/custody views only. They do not rank, route, close, or override atoms.",
        "- Unassigned atom IDs stay visibly `unrouted`; owner routing must be recorded on the atom projection before delegation.",
        "",
        "## Coverage",
        "",
        f"- Prompt lifecycle source files: `{coverage.get('prompt_index_files', 0)}`.",
        f"- Prompt-like events from source ledger: `{coverage.get('prompt_index_events', 0)}`.",
        f"- Prioritized session receipts: `{coverage.get('prioritized_sessions', 0)}`.",
        f"- Prioritized prompt events: `{coverage.get('prioritized_prompt_events', 0)}`.",
        f"- Unique prompt hashes: `{coverage.get('unique_prompt_hashes', 0)}`.",
        f"- Prompt atoms: `{coverage.get('prompt_atoms', 0)}`; current unresolved atoms: `{coverage.get('current_unresolved_prompt_atoms', 0)}`; source scope: `{coverage.get('prompt_atom_scope', 'missing')}`.",
        f"- Atom owner queues: `{coverage.get('atom_owner_queues', 0)}`; unresolved atom IDs without an explicit owner/route: `{coverage.get('unrouted_prompt_atoms', 0)}`.",
        f"- Legacy compatibility batches / Codex sessions: `{coverage.get('legacy_review_batches', 0)}` / `{coverage.get('legacy_codex_classified_sessions', 0)}`.",
        f"- Legacy attack paths / blockers / capability items: `{coverage.get('legacy_attack_paths', 0)}` / `{coverage.get('legacy_blockers', 0)}` / `{coverage.get('legacy_capability_activation_items', 0)}`.",
        f"- Source mix: {public_counts(Counter(counts.get('sources') or {}))}.",
        f"- Band mix: {public_counts(Counter(counts.get('bands') or {}), limit=5)}.",
        f"- Lane mix: {public_counts(Counter(counts.get('lanes') or {}), limit=6)}.",
        "",
        "## Atom Control Queue (authoritative; bounded display)",
        "",
        "| Rank | Atom | Kind | Authority | Score | Reasons | Disposition |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for rank, atom in enumerate(atoms, start=1):
        reasons = ", ".join(f"`{value}`" for value in atom["priority_reasons"]) or "none"
        lines.append(
            f"| {rank} | `{atom['atom_id']}` | `{atom['kind']}` | `{atom['authority']}` | "
            f"{atom['priority_score']} | {reasons} | `{atom['disposition']}` |"
        )
    if not atoms:
        lines.append("| 0 | none | n/a | n/a | 0 | none | n/a |")

    lines += [
        "",
        "## Atom Owner Queues (authoritative)",
        "",
        "| Queue | Owner | Route | Atoms | Highest Score | Ordered Atom IDs |",
        "|---|---|---|---:|---:|---|",
    ]
    for queue in owner_queues:
        displayed_ids = queue["atom_ids"][:limit]
        atom_ids = ", ".join(f"`{atom_id}`" for atom_id in displayed_ids)
        hidden = int(queue["atom_count"]) - len(displayed_ids)
        if hidden:
            atom_ids += f"; _{hidden} more in private control queue_"
        lines.append(
            f"| `{queue['queue_id']}` | `{queue['owner']}` | `{queue['route']}` | "
            f"{queue['atom_count']} | {queue['top_priority_score']} | {atom_ids} |"
        )
    if not owner_queues:
        lines.append("| none | n/a | n/a | 0 | 0 | none |")

    lines += [
        "",
        "## Legacy Compatibility Model (non-authoritative)",
        "",
        "- The tables below are custody aids for historical receipts that have not yet been atom-linked. They are not dispatch queues.",
        "- Their heuristic scores cannot add, remove, reorder, assign, supersede, or close any atom ID.",
        "- The private JSON keeps the complete compatibility map alongside, but structurally separate from, the complete atom control queue.",
        "",
        "## Legacy Review Batches (compatibility only)",
        "",
        "| Rank | Batch | Band | Lane | Sessions | Prompt Events | Unique Prompts | Dominant Mix | Route |",
        "|---:|---|---|---|---:|---:|---:|---|---|",
    ]
    for rank, batch in enumerate(batches, start=1):
        source_bits = ", ".join(f"{key} {value}" for key, value in batch["sources"].items()) or "none"
        family_bits = ", ".join(f"{key} {value}" for key, value in batch["families"].items()) or "none"
        lines.append(
            f"| {rank} | `{batch['id']}` | `{batch['band']}` | `{batch['lane']}` | "
            f"{batch['session_count']} | {batch['prompt_events']} | {batch['unique_prompt_hashes']} | "
            f"sources {source_bits}; families {family_bits} | {batch['next_action']} |"
        )
    if not batches:
        lines.append("| 0 | none | n/a | n/a | 0 | 0 | 0 | none | n/a |")

    lines += [
        "",
        "## Legacy Session Receipts (compatibility only)",
        "",
        "| Rank | Session Key | Band | Lane | Score | Source | Family / State | Worktree | Prompt Events | Next Action |",
        "|---:|---|---|---|---:|---|---|---|---:|---|",
    ]
    for rank, session in enumerate(sessions, start=1):
        worktree = session.get("worktree_slug") or "none"
        lines.append(
            f"| {rank} | `{session['session_key']}` | `{session['band']}` | `{session['lane']}` | "
            f"{session['score']} | `{session['source']}` | `{session['family']}` / `{session['state']}` | "
            f"`{worktree}` | {session['prompt_events']} | {session['next_action']} |"
        )
    if not sessions:
        lines.append("| 0 | none | n/a | n/a | 0 | n/a | n/a | n/a | 0 | n/a |")

    lines += [
        "",
        "## Legacy Lane Map (compatibility only)",
        "",
        "| Lane | Top Band | Sessions | Prompt Events | Batches | Dominant Source | Dominant Family | Route |",
        "|---|---|---:|---:|---:|---|---|---|",
    ]
    for lane in compatibility.get("lane_task_map") or []:
        lines.append(
            f"| `{lane['lane']}` | `{lane['top_band']}` | {lane['sessions']} | {lane['prompt_events']} | "
            f"{lane['batches']} | `{lane['dominant_source']}` | `{lane['dominant_family']}` | {lane['route']} |"
        )
    if not (compatibility.get("lane_task_map") or []):
        lines.append("| none | n/a | 0 | 0 | 0 | n/a | n/a | n/a |")

    lines += [
        "",
        "## Private Output",
        "",
        f"- Prompt priority private map: `{relpath(PRIVATE_INDEX)}`.",
        "- The private map contains the complete atom-ID control and owner queues plus explicitly non-authoritative legacy prompt hashes, session keys, source paths, lanes, scores, and batch membership; it contains no prompt text.",
        "",
        "## Commands",
        "",
        "- Refresh authoritative ask atoms first: `python3 scripts/prompt-atom-ledger.py --scan --all --write && python3 scripts/prompt-atom-ledger.py --check --require-scope all`",
        "- Refresh this priority map: `python3 scripts/prompt-priority-map.py --write`",
        "- Refresh legacy compatibility prerequisites (custody only): `python3 scripts/prompt-lifecycle-ledger.py --write --all && python3 scripts/session-attack-paths.py --write`",
        "- Show a wider tracked atom preview: `python3 scripts/prompt-priority-map.py --write --limit 60`",
        "",
    ]
    return "\n".join(lines)


def write_outputs(snapshot: dict[str, Any], markdown: str) -> None:
    DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    DOC_PATH.write_text(markdown, encoding="utf-8")
    PRIVATE_INDEX.parent.mkdir(parents=True, exist_ok=True)
    PRIVATE_INDEX.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a redacted prompt priority/task map.")
    parser.add_argument("--write", action="store_true", help="write docs and ignored private index")
    parser.add_argument("--limit", type=int, default=30, help="batches and sessions to show in tracked docs")
    parser.add_argument("--batch-size", type=int, default=25, help="session receipts per review batch")
    args = parser.parse_args()

    try:
        snapshot = build_snapshot(batch_size=max(1, args.batch_size))
        markdown = render_markdown(snapshot, limit=max(1, args.limit))
    except AtomProjectionError as exc:
        print(f"prompt-priority-map: BLOCKED — {exc}", file=sys.stderr)
        return 2
    if args.write:
        write_outputs(snapshot, markdown)
    else:
        print(markdown)
    msg = (
        "prompt-priority-map: "
        f"{snapshot['coverage']['current_unresolved_prompt_atoms']} authoritative unresolved atoms, "
        f"{snapshot['coverage']['atom_owner_queues']} owner queues; "
        f"{snapshot['coverage']['legacy_review_batches']} legacy compatibility batches"
    )
    if args.write:
        msg += f"; wrote {DOC_PATH}"
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
