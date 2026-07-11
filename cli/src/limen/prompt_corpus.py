"""Private prompt-occurrence and ask-atom control plane.

The raw journal is private.  Public projections contain stable opaque IDs,
counts, lineage, priority dimensions, and evidence dispositions only.  Model or
provider catalogs are deliberately outside this module: callers may supply
provider-neutral atom candidates and dimension overrides, while the structural
fallback guarantees lossless coverage without credentials.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import gzip
import hashlib
import json
import math
import os
import re
import tempfile
import threading
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence
from urllib.parse import urlsplit


DISPOSITIONS = {
    "unassessed",
    "not_done",
    "partial",
    "done",
    "blocked",
    "superseded",
}

ATOM_KINDS = {
    "ask",
    "correction",
    "constraint",
    "acceptance_criterion",
    "human_gate",
}

PROVENANCE_KINDS = {
    "operator_typed",
    "delegated_task_frame",
    "continuation_summary",
    "transport_echo",
    "unknown_user_input",
}

DIMENSIONS = (
    "operator_emphasis",
    "system_leverage",
    "magnitude",
    "recurrence",
    "dependency_impact",
    "preservation_risk",
    "recency",
    "cost_of_delay",
)

EVIDENCE_KINDS = {
    "github_pr",
    "github_commit",
    "github_issue",
    "github_run",
    "task_receipt",
    "predicate_receipt",
}

DEFAULT_POLICY: dict[str, Any] = {
    "version": 1,
    "weights": {name: 1.0 for name in DIMENSIONS},
    "authority_bands": {
        "operator": {"floor": 0.67, "ceiling": 1.0},
        "unknown": {"floor": 0.34, "ceiling": 0.66},
        "derived": {"floor": 0.0, "ceiling": 0.33},
    },
    "confidence_thresholds": {
        "semantic_atom": 0.5,
        "lineage_edge": 0.5,
        "structural_fallback": 0.25,
        "command_timeout_seconds": 30.0,
    },
    "owner_routing": {
        "default_owner": "unassigned",
        "default_route": "unrouted",
        "default_next_command": "python3 scripts/prompt-atom-ledger.py --scan --all --write",
    },
    "reclassification": {"max_occurrences_per_run": 5},
    "recency_half_life_days": 30.0,
    "unconverged_repeat_limit": 15,
}

_SAFE_ROUTE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@#-]{0,159}$")

_THREAD_LOCK = threading.RLock()
_CORRECTION_RE = re.compile(
    r"^(?:no\b|not\b|do not\b|don't\b|stop\b|instead\b|rather\b|"
    r"what i(?:'m| am) saying\b|once again\b|like i said\b|correction\b)",
    re.IGNORECASE,
)
_ACCEPTANCE_RE = re.compile(
    r"\b(?:acceptance|done when|finish line|predicate|must pass|verify that|proof required)\b",
    re.IGNORECASE,
)
_CONSTRAINT_RE = re.compile(
    r"\b(?:must|never|only|do not|don't|should not|cannot|can't|required)\b",
    re.IGNORECASE,
)
_HUMAN_GATE_RE = re.compile(
    r"\b(?:needs human|human gate|manual approval|human decision)\b",
    re.IGNORECASE,
)
_ACTION_AFTER_AND_RE = re.compile(
    r"\s+and\s+(?=(?:add|answer|build|check|continue|create|derive|explain|find|fix|give|"
    r"implement|inspect|keep|land|make|merge|preserve|record|remove|review|route|run|show|"
    r"stop|tell|test|update|use|verify|write)\b)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class LedgerPaths:
    root: Path
    private_dir: Path
    event_journal: Path
    outcome_journal: Path
    raw_objects: Path
    cursor: Path
    lock: Path
    private_snapshot: Path
    public_snapshot: Path
    public_markdown: Path
    policy: Path

    @classmethod
    def for_root(
        cls,
        root: Path,
        *,
        private_root: Path | None = None,
        public_markdown: Path | None = None,
        public_snapshot: Path | None = None,
        policy: Path | None = None,
    ) -> "LedgerPaths":
        configured_private_root = os.environ.get("LIMEN_PRIVATE_SESSION_CORPUS")
        private_base = private_root
        if private_base is None and configured_private_root:
            private_base = Path(configured_private_root).expanduser()
        private_dir = (private_base or root / ".limen-private" / "session-corpus") / "prompt-atoms"
        return cls(
            root=root,
            private_dir=private_dir,
            event_journal=private_dir / "prompt-events.jsonl",
            outcome_journal=private_dir / "prompt-atom-outcomes.jsonl",
            raw_objects=private_dir / "raw-objects",
            cursor=private_dir / "source-cursor.json",
            lock=private_dir / "writer.lock",
            private_snapshot=private_dir / "prompt-atom-ledger.json",
            public_snapshot=public_snapshot or root / "docs" / "prompt-atom-ledger.json",
            public_markdown=public_markdown or root / "docs" / "prompt-atom-ledger.md",
            policy=policy or root / "docs" / "prompt-corpus-policy.json",
        )


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8", errors="replace")).hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 20) -> str:
    material = "\0".join(str(part) for part in parts)
    return f"{prefix}-{hashlib.sha256(material.encode('utf-8', errors='replace')).hexdigest()[:length]}"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def load_json_strict(path: Path) -> tuple[dict[str, Any], list[str]]:
    if not path.exists():
        return {}, []
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, [f"{path.name}: malformed or unreadable JSON: {exc}"]
    if not isinstance(value, dict):
        return {}, [f"{path.name}: JSON value is not an object"]
    return value, []


def load_jsonl_strict(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except ValueError as exc:
                    errors.append(f"{path.name}:{line_number}: malformed JSON: {exc}")
                    continue
                if isinstance(row, dict):
                    rows.append(row)
                else:
                    errors.append(f"{path.name}:{line_number}: row is not an object")
    except OSError as exc:
        if path.exists() or not isinstance(exc, FileNotFoundError):
            errors.append(f"{path.name}: cannot read journal: {exc}")
    return rows, errors


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Compatibility reader for caller-provided JSONL; journal checks use the strict form."""

    return load_jsonl_strict(path)[0]


def atomic_write_bytes(path: Path, content: bytes, *, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
        os.chmod(path, mode)
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)


def atomic_write_text(path: Path, text: str, *, mode: int = 0o600) -> None:
    atomic_write_bytes(path, text.encode("utf-8"), mode=mode)


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    material = [canonical_json(row) + "\n" for row in rows]
    if not material:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(fd, "a", encoding="utf-8") as handle:
        handle.writelines(material)
        handle.flush()
        os.fsync(handle.fileno())
    return len(material)


def preserve_raw_object(paths: LedgerPaths, prompt_hash: str, text: str) -> str:
    """Content-address the exact private body once; journals keep only this opaque reference."""

    relative = Path(prompt_hash[:2]) / f"{prompt_hash}.txt.gz"
    destination = paths.raw_objects / relative
    if not destination.exists():
        atomic_write_bytes(
            destination,
            gzip.compress(text.encode("utf-8", errors="replace"), compresslevel=6),
            mode=0o400,
        )
        os.chmod(destination.parent, 0o700)
    paths.raw_objects.mkdir(parents=True, exist_ok=True)
    os.chmod(paths.raw_objects, 0o700)
    return str(relative)


def read_raw_object(paths: LedgerPaths, relative: str) -> str:
    """Read one private raw object while rejecting path traversal."""

    candidate = (paths.raw_objects / relative).resolve()
    root = paths.raw_objects.resolve()
    if root not in candidate.parents:
        raise ValueError("raw object path escapes private store")
    return gzip.decompress(candidate.read_bytes()).decode("utf-8", errors="replace")


def load_event_journal(
    path: Path,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Load transactional occurrence+atom rows from the append-only journal."""

    rows, errors = load_jsonl_strict(path)
    occurrence_order: list[str] = []
    occurrences_by_id: dict[str, dict[str, Any]] = {}
    atoms_by_occurrence: dict[str, list[dict[str, Any]]] = {}
    for line_number, row in enumerate(rows, start=1):
        occurrence = row.get("occurrence")
        event_atoms = row.get("atoms")
        if not isinstance(occurrence, dict) or not isinstance(event_atoms, list):
            errors.append(f"{path.name}:{line_number}: event row lacks occurrence/atoms")
            continue
        if not all(isinstance(atom, dict) for atom in event_atoms):
            errors.append(f"{path.name}:{line_number}: event atoms must be objects")
            continue
        occurrence_id = str(occurrence.get("occurrence_id") or "")
        if not occurrence_id:
            errors.append(f"{path.name}:{line_number}: occurrence id is missing")
            continue
        revision_of = str(row.get("revision_of") or "")
        if occurrence_id in occurrences_by_id and revision_of != occurrence_id:
            errors.append(f"{path.name}:{line_number}: duplicate base occurrence")
            continue
        if revision_of and revision_of not in occurrences_by_id:
            errors.append(f"{path.name}:{line_number}: classification revision lacks a base event")
            continue
        if occurrence_id not in occurrences_by_id:
            occurrence_order.append(occurrence_id)
        occurrences_by_id[occurrence_id] = occurrence
        atoms_by_occurrence[occurrence_id] = list(event_atoms)
    occurrences = [occurrences_by_id[value] for value in occurrence_order]
    atoms = [atom for value in occurrence_order for atom in atoms_by_occurrence[value]]
    return occurrences, atoms, errors


@contextlib.contextmanager
def exclusive_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    with _THREAD_LOCK, path.open("a+") as handle:
        os.chmod(path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_policy(path: Path) -> dict[str, Any]:
    raw = load_json(path)
    policy = dict(DEFAULT_POLICY)
    policy.update({key: value for key, value in raw.items() if key != "weights"})
    weights = dict(DEFAULT_POLICY["weights"])
    if isinstance(raw.get("weights"), dict):
        for name in DIMENSIONS:
            try:
                weights[name] = max(0.0, float(raw["weights"].get(name, weights[name])))
            except (TypeError, ValueError):
                pass
    if not any(weights.values()):
        weights = dict(DEFAULT_POLICY["weights"])
    policy["weights"] = weights
    authority_bands = {name: dict(values) for name, values in DEFAULT_POLICY["authority_bands"].items()}
    if isinstance(raw.get("authority_bands"), dict):
        for name in authority_bands:
            candidate = raw["authority_bands"].get(name)
            if not isinstance(candidate, dict):
                continue
            floor = _clamp(candidate.get("floor"), authority_bands[name]["floor"])
            ceiling = _clamp(candidate.get("ceiling"), authority_bands[name]["ceiling"])
            if floor <= ceiling:
                authority_bands[name] = {"floor": floor, "ceiling": ceiling}
    if not (
        authority_bands["derived"]["ceiling"] < authority_bands["unknown"]["floor"]
        and authority_bands["unknown"]["ceiling"] < authority_bands["operator"]["floor"]
    ):
        authority_bands = {name: dict(values) for name, values in DEFAULT_POLICY["authority_bands"].items()}
    policy["authority_bands"] = authority_bands
    thresholds = dict(DEFAULT_POLICY["confidence_thresholds"])
    if isinstance(raw.get("confidence_thresholds"), dict):
        for name in ("semantic_atom", "lineage_edge", "structural_fallback"):
            thresholds[name] = _clamp(raw["confidence_thresholds"].get(name), thresholds[name])
        try:
            thresholds["command_timeout_seconds"] = min(
                300.0,
                max(
                    0.1,
                    float(
                        raw["confidence_thresholds"].get(
                            "command_timeout_seconds",
                            thresholds["command_timeout_seconds"],
                        )
                    ),
                ),
            )
        except (TypeError, ValueError):
            pass
    policy["confidence_thresholds"] = thresholds
    routing = dict(DEFAULT_POLICY["owner_routing"])
    if isinstance(raw.get("owner_routing"), dict):
        for field in ("default_owner", "default_route"):
            candidate = str(raw["owner_routing"].get(field) or "").strip()
            if _SAFE_ROUTE_LABEL.fullmatch(candidate):
                routing[field] = candidate
        next_command = str(raw["owner_routing"].get("default_next_command") or "").strip()
        if next_command:
            routing["default_next_command"] = next_command
        for field in ("sources", "adapters", "by_source"):
            candidate = raw["owner_routing"].get(field)
            if isinstance(candidate, dict):
                routing[field] = candidate
    policy["owner_routing"] = routing
    reclassification = dict(DEFAULT_POLICY["reclassification"])
    if isinstance(raw.get("reclassification"), dict):
        try:
            reclassification["max_occurrences_per_run"] = min(
                1000,
                max(
                    1,
                    int(
                        raw["reclassification"].get(
                            "max_occurrences_per_run",
                            reclassification["max_occurrences_per_run"],
                        )
                    ),
                ),
            )
        except (TypeError, ValueError):
            pass
    policy["reclassification"] = reclassification
    try:
        policy["recency_half_life_days"] = max(0.001, float(policy["recency_half_life_days"]))
    except (TypeError, ValueError):
        policy["recency_half_life_days"] = DEFAULT_POLICY["recency_half_life_days"]
    try:
        policy["unconverged_repeat_limit"] = max(1, int(policy["unconverged_repeat_limit"]))
    except (TypeError, ValueError):
        policy["unconverged_repeat_limit"] = DEFAULT_POLICY["unconverged_repeat_limit"]
    return policy


def normalize_intent(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|\[[ xX]\]\s+)", "", text)
    text = re.sub(r"\s+", " ", text).strip().strip("-–—;,. ")
    return text.casefold()


def _structural_blocks(text: str) -> list[str]:
    """Preserve fenced spans as candidates instead of discarding private input."""

    parts = re.split(r"(```[^\n]*\n.*?```)", text, flags=re.DOTALL)
    blocks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("```"):
            fenced = re.sub(r"^```[^\n]*\n?|```$", "", part, flags=re.DOTALL).strip()
            if fenced:
                blocks.append(fenced)
            continue
        for paragraph in re.split(r"\n\s*\n", part):
            paragraph = paragraph.strip()
            if not paragraph:
                continue
            list_lines = [line.strip() for line in paragraph.splitlines() if line.strip()]
            if len(list_lines) > 1 and any(
                re.match(r"^(?:[-*+]\s+|\d+[.)]\s+|\[[ xX]\]\s+)", line) for line in list_lines
            ):
                blocks.extend(list_lines)
            else:
                blocks.append(" ".join(list_lines))
    return blocks


def structural_segments(text: str) -> list[str]:
    """Conservatively split prose/list structure; never require a model."""

    clean = text.strip()
    if not clean:
        return []

    segments: list[str] = []
    for block in _structural_blocks(clean):
        for sentence in re.split(r"(?<=[?!.])\s+(?=[A-Za-z0-9])|\s*;\s+", block):
            for piece in _ACTION_AFTER_AND_RE.split(sentence):
                piece = piece.strip()
                if len(re.sub(r"\W", "", piece)) < 2:
                    continue
                segments.append(piece)
    return segments or [clean]


def speech_act_kind(text: str) -> str:
    stripped = text.strip()
    if _CORRECTION_RE.search(stripped):
        return "correction"
    if _HUMAN_GATE_RE.search(stripped):
        return "human_gate"
    if _ACCEPTANCE_RE.search(stripped):
        return "acceptance_criterion"
    if _CONSTRAINT_RE.search(stripped):
        return "constraint"
    return "ask"


def _clamp(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return round(min(1.0, max(0.0, number)), 6)


def _parse_time(value: Any) -> dt.datetime | None:
    if not value:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        try:
            return dt.datetime.fromtimestamp(number, tz=dt.timezone.utc)
        except (OSError, OverflowError, ValueError):
            return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def occurrence_from_event(event: dict[str, Any]) -> dict[str, Any]:
    text = str(event.get("text") or "")
    source = str(event.get("source") or "unknown")
    session_ref = str(event.get("session_ref") or "unknown")
    event_ref = str(event.get("event_ref") or event.get("event_index") or "0")
    text_index = int(event.get("text_index") or 0)
    prompt_hash = hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()
    occurrence_id = stable_id("po", source, session_ref, event_ref, text_index, prompt_hash, length=24)
    provenance = str(event.get("provenance") or "unknown_user_input")
    if provenance not in PROVENANCE_KINDS:
        provenance = "unknown_user_input"
    # Authority is derived from provenance; a normalized event cannot upgrade itself.
    authority = (
        "operator"
        if provenance == "operator_typed"
        else ("unknown" if provenance == "unknown_user_input" else "derived")
    )
    return {
        "occurrence_id": occurrence_id,
        "source": source,
        "session_ref_hash": digest(session_ref)[:24],
        "event_ref_hash": digest(event_ref)[:24],
        "event_index": int(event.get("event_index") or 0),
        "text_index": text_index,
        "source_locator": event.get("source_locator"),
        "timestamp": event.get("timestamp"),
        "prompt_hash": prompt_hash,
        "body_kind": str(event.get("body_kind") or "direct"),
        "provenance": provenance,
        "authority": authority,
        "raw_text": text,
        "atom_ids": [],
        "excluded_reason": None,
        "duplicate_of": event.get("duplicate_of"),
    }


def atoms_from_event(
    occurrence: dict[str, Any],
    event: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    if occurrence.get("provenance") == "transport_echo":
        occurrence["excluded_reason"] = "transport_echo"
        return []
    task_body = str(event.get("task_body") or "")
    body_kind = str(occurrence.get("body_kind") or "direct")
    atom_text = task_body if task_body.strip() else str(occurrence.get("raw_text") or "")
    if body_kind in {"flame_scaffold", "session_context"} and not task_body.strip():
        occurrence["excluded_reason"] = "derived_context_without_actionable_body"
        return []
    if not atom_text.strip():
        occurrence["excluded_reason"] = "empty_prompt_body"
        return []

    baseline_segments = structural_segments(atom_text) or [atom_text.strip()]
    baseline: list[tuple[str, str, str]] = []
    for segment_index, segment in enumerate(baseline_segments):
        normalized = normalize_intent(segment)
        if normalized:
            baseline.append((segment, normalized, digest({"index": segment_index, "intent": normalized})))
    occurrence["coverage_segment_hashes"] = [segment_hash for _text, _normalized, segment_hash in baseline]

    supplied = event.get("atoms")
    candidates: list[dict[str, Any]] = []
    covered: set[str] = set()
    thresholds = policy["confidence_thresholds"]
    if isinstance(supplied, list):
        for candidate in supplied:
            if not isinstance(candidate, dict):
                continue
            classifier_label = str(candidate.get("text") or "").strip()
            normalized_label = normalize_intent(classifier_label)
            if not normalized_label:
                continue
            confidence = _clamp(candidate.get("classification_confidence"), 0.75)
            if confidence < float(thresholds["semantic_atom"]):
                continue
            row = dict(candidate)
            row["atomization_mode"] = "semantic_adapter"
            row["classification_confidence"] = confidence
            candidate_coverage: list[str] = []
            exact = next(
                (
                    segment_hash
                    for _segment, baseline_normalized, segment_hash in baseline
                    if baseline_normalized == normalized_label and segment_hash not in covered
                ),
                None,
            )
            if exact:
                candidate_coverage.append(exact)
            indexes = candidate.get("coverage_segment_indexes") or []
            source_segments = candidate.get("source_segments") or []
            if isinstance(indexes, list) and isinstance(source_segments, list):
                for source_index, source_segment in zip(indexes, source_segments, strict=False):
                    try:
                        baseline_index = int(source_index)
                        _text, baseline_normalized, segment_hash = baseline[baseline_index]
                    except (IndexError, TypeError, ValueError):
                        continue
                    if (
                        normalize_intent(str(source_segment)) == baseline_normalized
                        and segment_hash not in covered
                        and segment_hash not in candidate_coverage
                    ):
                        candidate_coverage.append(segment_hash)
            row["coverage_hashes"] = list(dict.fromkeys(candidate_coverage))
            if not row["coverage_hashes"]:
                continue
            covered_source = [
                segment
                for segment, _baseline_normalized, segment_hash in baseline
                if segment_hash in row["coverage_hashes"]
            ]
            if not covered_source:
                continue
            # The classifier may label or categorize an atom, but it may not
            # author the intent.  Canonical intent is always the exact source
            # span(s) whose positional hashes it claimed.
            row["text"] = " ".join(covered_source)
            row["classifier_label_hash"] = digest(normalized_label)
            covered.update(row["coverage_hashes"])
            candidates.append(row)
    for segment, _normalized, segment_hash in baseline:
        if segment_hash in covered:
            continue
        candidates.append(
            {
                "text": segment,
                "kind": speech_act_kind(segment),
                "atomization_mode": "structural_fallback",
                "classification_confidence": float(thresholds["structural_fallback"]),
                "coverage_hashes": [segment_hash],
            }
        )

    atoms: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        intent = str(candidate.get("text") or "").strip()
        if not intent:
            continue
        normalized = normalize_intent(intent)
        if not normalized:
            continue
        kind = str(candidate.get("kind") or speech_act_kind(intent))
        if kind not in ATOM_KINDS:
            kind = speech_act_kind(intent)
        coverage_identity = ",".join(sorted(str(value) for value in (candidate.get("coverage_hashes") or [])))
        atom_id = stable_id("pa", occurrence["occurrence_id"], coverage_identity, normalized, length=24)
        lineage_id = str(candidate.get("lineage_id") or stable_id("pl", normalized, length=24))
        predecessors = [str(value) for value in (candidate.get("predecessor_ids") or []) if str(value)]
        dependencies = [str(value) for value in (candidate.get("dependency_ids") or []) if str(value)]
        mode = str(candidate.get("atomization_mode") or "structural_fallback")
        if mode not in {"semantic_adapter", "structural_fallback"}:
            mode = "structural_fallback"
        dimensions = candidate.get("dimensions") if mode == "semantic_adapter" else {}
        routing = policy["owner_routing"]
        owner = str(candidate.get("owner") or routing["default_owner"]).strip()
        owner_route = str(candidate.get("owner_route") or candidate.get("route") or routing["default_route"]).strip()
        if not _SAFE_ROUTE_LABEL.fullmatch(owner):
            owner = str(routing["default_owner"])
        if not _SAFE_ROUTE_LABEL.fullmatch(owner_route):
            owner_route = str(routing["default_route"])
        atoms.append(
            {
                "atom_id": atom_id,
                "occurrence_id": occurrence["occurrence_id"],
                "source": occurrence["source"],
                "session_ref_hash": occurrence["session_ref_hash"],
                "timestamp": occurrence.get("timestamp"),
                "index": index,
                "kind": kind,
                "authority": occurrence["authority"],
                "intent": intent,
                "normalized_intent_hash": digest(normalized),
                "lineage_id": lineage_id,
                "relation": str(candidate.get("relation") or "origin"),
                "predecessor_ids": predecessors,
                "candidate_predecessor_ids": [],
                "dependency_ids": dependencies,
                "dimension_overrides": dimensions if isinstance(dimensions, dict) else {},
                "atomization_mode": mode,
                "classification_confidence": _clamp(
                    candidate.get("classification_confidence"),
                    0.75 if mode == "semantic_adapter" else 0.25,
                ),
                "classifier_provenance": (
                    str(candidate.get("classifier_provenance") or "runtime_adapter")
                    if mode == "semantic_adapter"
                    else "native_structural_fallback"
                ),
                "classifier_label_hash": (
                    str(candidate.get("classifier_label_hash") or "") if mode == "semantic_adapter" else None
                ),
                "coverage_hashes": [str(value) for value in (candidate.get("coverage_hashes") or []) if str(value)],
                "owner": owner,
                "owner_route": owner_route,
                "lineage_evidence": candidate.get("lineage_evidence"),
            }
        )
    if not atoms:
        occurrence["excluded_reason"] = "no_actionable_atom_after_normalization"
    occurrence["atom_ids"] = [atom["atom_id"] for atom in atoms]
    return atoms


def _emphasis_score(atom: dict[str, Any]) -> float:
    text = str(atom.get("intent") or "")
    score = 0.25
    if atom.get("kind") == "correction":
        score += 0.3
    if atom.get("kind") in {"constraint", "acceptance_criterion"}:
        score += 0.15
    score += min(0.15, 0.05 * (text.count("!") + max(0, text.count("?") - 1)))
    letters = [char for char in text if char.isalpha()]
    if letters:
        upper_ratio = sum(char.isupper() for char in letters) / len(letters)
        score += min(0.15, upper_ratio * 0.3)
    return _clamp(score)


def _magnitude_score(atom: dict[str, Any]) -> float:
    words = max(1, len(re.findall(r"\b\w+\b", str(atom.get("intent") or ""))))
    return _clamp(math.log1p(words) / math.log(101))


def _recency_score(timestamp: Any, reference: dt.datetime, half_life_days: float) -> float:
    parsed = _parse_time(timestamp)
    if parsed is None:
        return 0.25
    age_days = max(0.0, (reference - parsed).total_seconds() / 86400.0)
    return _clamp(math.pow(0.5, age_days / half_life_days))


def _outcome_for_atom(atom_id: str, outcomes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    row = outcomes.get(atom_id) or {}
    disposition = str(row.get("disposition") or "unassessed")
    return {
        "disposition": disposition,
        "owner": row.get("owner"),
        "gate": row.get("gate"),
        "next_command": row.get("next_command"),
        "residual_atom_ids": [str(value) for value in (row.get("residual_atom_ids") or [])],
        "successor_atom_id": row.get("successor_atom_id"),
        "evidence": [item for item in (row.get("evidence") or []) if isinstance(item, dict)],
        "assessed_at": row.get("assessed_at"),
    }


_GITHUB_EVIDENCE_PATTERNS = {
    "github_pr": re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/[1-9][0-9]*$"),
    "github_issue": re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/issues/[1-9][0-9]*$"),
    "github_commit": re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/commit/[0-9a-fA-F]{40}$"),
    "github_run": re.compile(r"^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/actions/runs/[1-9][0-9]*$"),
}
_REPO_EVIDENCE_RE = re.compile(r"^(?:docs|logs)/[A-Za-z0-9_.@/+:-]+$")


def canonical_evidence_ref(kind: str, value: Any) -> str | None:
    ref = str(value or "").strip()
    if not ref or any(ord(char) < 32 or char in "`|\\" for char in ref):
        return None
    if kind in _GITHUB_EVIDENCE_PATTERNS:
        parts = urlsplit(ref)
        if parts.query or parts.fragment or parts.username or parts.password:
            return None
        return ref if _GITHUB_EVIDENCE_PATTERNS[kind].fullmatch(ref) else None
    if kind in {"task_receipt", "predicate_receipt"}:
        if "?" in ref or "#" in ref or ".." in Path(ref).parts:
            return None
        return ref if _REPO_EVIDENCE_RE.fullmatch(ref) else None
    return None


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _verified_artifact(
    *,
    evidence_root: Path | None,
    ref: Any,
    expected_sha256: Any,
) -> Path | None:
    if evidence_root is None:
        return None
    canonical_ref = canonical_evidence_ref("predicate_receipt", ref)
    expected = str(expected_sha256 or "")
    if canonical_ref is None or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
        return None
    root = evidence_root.resolve()
    artifact = (root / canonical_ref).resolve()
    if root not in artifact.parents or not artifact.is_file():
        return None
    try:
        return artifact if _file_sha256(artifact) == expected else None
    except OSError:
        return None


def _github_verification_receipt(item: dict[str, Any], evidence_root: Path | None) -> bool:
    artifact = _verified_artifact(
        evidence_root=evidence_root,
        ref=item.get("verification_receipt_ref"),
        expected_sha256=item.get("verification_receipt_sha256"),
    )
    if artifact is None:
        return False
    try:
        receipt = json.loads(artifact.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError):
        return False
    if not isinstance(receipt, dict):
        return False
    common_fields = (
        "kind",
        "ref",
        "predicate",
        "result",
        "verified_at",
        "owner",
        "subject_atom_ids",
        "verifier",
    )
    kind_fields = {
        "github_pr": ("state", "head_sha", "merge_commit_sha", "reachable_from_default"),
        "github_commit": ("commit_sha", "reachable_from_default"),
        "github_run": ("conclusion", "head_sha", "reachable_from_default"),
    }
    kind = str(item.get("kind") or "")
    expected = {field: item.get(field) for field in (*common_fields, *kind_fields.get(kind, ()))}
    return bool(
        receipt.get("schema") == "limen.github-verification.v1"
        and receipt.get("exit_code") == 0
        and receipt.get("evidence") == expected
    )


def _passing_evidence(
    item: Any,
    *,
    atom_id: str,
    owner: str,
    evidence_root: Path | None,
) -> bool:
    if not isinstance(item, dict):
        return False
    kind = str(item.get("kind") or "")
    base_valid = bool(
        kind in EVIDENCE_KINDS
        and canonical_evidence_ref(kind, item.get("ref"))
        and str(item.get("predicate") or "").strip()
        and not re.search(r"[\x00-\x1f`]", str(item.get("predicate") or ""))
        and str(item.get("result") or "").strip().lower() == "pass"
        and _parse_time(item.get("verified_at")) is not None
        and atom_id in [str(value) for value in (item.get("subject_atom_ids") or [])]
        and bool(owner)
        and str(item.get("owner") or "").strip() == owner
    )
    if not base_valid:
        return False
    sha_re = re.compile(r"^[0-9a-f]{40}$")
    if kind == "github_pr":
        return bool(
            _github_verification_receipt(item, evidence_root)
            and item.get("verifier") == "github_api"
            and item.get("state") == "merged"
            and sha_re.fullmatch(str(item.get("head_sha") or ""))
            and sha_re.fullmatch(str(item.get("merge_commit_sha") or ""))
            and item.get("reachable_from_default") is True
        )
    if kind == "github_commit":
        ref_sha = str(item.get("ref") or "").rsplit("/", 1)[-1].lower()
        return bool(
            _github_verification_receipt(item, evidence_root)
            and item.get("verifier") == "github_api"
            and ref_sha == str(item.get("commit_sha") or "").lower()
            and item.get("reachable_from_default") is True
        )
    if kind == "github_run":
        return bool(
            _github_verification_receipt(item, evidence_root)
            and item.get("verifier") == "github_api"
            and item.get("conclusion") == "success"
            and sha_re.fullmatch(str(item.get("head_sha") or ""))
            and item.get("reachable_from_default") is True
        )
    if kind == "github_issue":
        return False
    if item.get("verifier") != "local_predicate":
        return False
    try:
        return bool(
            int(str(item.get("exit_code"))) == 0
            and _verified_artifact(
                evidence_root=evidence_root,
                ref=item.get("ref"),
                expected_sha256=item.get("artifact_sha256"),
            )
            is not None
        )
    except (TypeError, ValueError):
        return False


def validate_outcome(
    atom: dict[str, Any],
    atoms_by_id: dict[str, dict[str, Any]],
    *,
    evidence_root: Path | None,
) -> list[str]:
    atom_id = str(atom["atom_id"])
    outcome = atom.get("outcome") or {}
    disposition = str(outcome.get("disposition") or "unassessed")
    errors: list[str] = []
    if disposition not in DISPOSITIONS:
        errors.append(f"{atom_id}: invalid disposition {disposition!r}")
        return errors
    evidence = outcome.get("evidence") or []
    owner = str(outcome.get("owner") or "").strip()
    passing = [
        item
        for item in evidence
        if _passing_evidence(
            item,
            atom_id=atom_id,
            owner=owner,
            evidence_root=evidence_root,
        )
    ]
    if disposition != "unassessed" and _parse_time(outcome.get("assessed_at")) is None:
        errors.append(f"{atom_id}: assessed disposition requires assessed_at")
    for item in evidence:
        if not _passing_evidence(
            item,
            atom_id=atom_id,
            owner=owner,
            evidence_root=evidence_root,
        ):
            errors.append(f"{atom_id}: evidence is not a typed, canonical, verified passing predicate")
    if disposition == "done" and not passing:
        errors.append(f"{atom_id}: done requires a referenced passing predicate")
    if disposition in {"done", "partial", "superseded"} and not str(outcome.get("owner") or "").strip():
        errors.append(f"{atom_id}: closure disposition requires an owner")
    if disposition == "partial":
        residual = [str(value) for value in (outcome.get("residual_atom_ids") or [])]
        residual_valid = bool(residual) and all(value in atoms_by_id and value != atom_id for value in residual)
        if not passing or not residual_valid:
            errors.append(f"{atom_id}: partial requires passing evidence and residual atom ids")
    if disposition == "blocked":
        if not all(str(outcome.get(field) or "").strip() for field in ("owner", "gate", "next_command")):
            errors.append(f"{atom_id}: blocked requires owner, gate, and next_command")
    if disposition == "superseded":
        successor = str(outcome.get("successor_atom_id") or "")
        successor_atom = atoms_by_id.get(successor)
        predecessor_edge = atom_id in ([str(value) for value in (successor_atom or {}).get("predecessor_ids") or []])
        predecessor_time = _parse_time(atom.get("timestamp"))
        successor_time = _parse_time((successor_atom or {}).get("timestamp"))
        successor_is_newer = bool(
            successor_atom
            and successor != atom_id
            and predecessor_time is not None
            and successor_time is not None
            and successor_time > predecessor_time
        )
        if not passing or not predecessor_edge or not successor_is_newer:
            errors.append(
                f"{atom_id}: superseded requires a distinct newer successor with a predecessor edge and passing proof"
            )
    return errors


_OUTCOME_TRANSITIONS = {
    "unassessed": {"not_done", "partial", "blocked", "done", "superseded"},
    "not_done": {"not_done", "partial", "blocked", "done", "superseded"},
    "partial": {"partial", "blocked", "done", "superseded"},
    "blocked": {"blocked", "partial", "done", "superseded"},
    "done": set(),
    "superseded": set(),
}


def validate_outcome_history(
    rows: Sequence[dict[str, Any]],
    atoms_by_id: dict[str, dict[str, Any]],
    *,
    evidence_root: Path | None,
) -> list[str]:
    """Validate append-only, revision-linked outcome state before it can govern."""

    errors: list[str] = []
    effective: dict[str, dict[str, Any]] = {}
    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"outcome row {row_number}: journal row is not an object")
            continue
        atom_id = str(row.get("atom_id") or "")
        source_atom = atoms_by_id.get(atom_id)
        if not atom_id or source_atom is None:
            errors.append(f"{atom_id or 'unknown'}: outcome references an unknown atom")
            continue

        atom = dict(source_atom)
        atom["outcome"] = _outcome_for_atom(atom_id, {atom_id: row})
        errors.extend(validate_outcome(atom, atoms_by_id, evidence_root=evidence_root))

        previous = effective.get(atom_id)
        revision_of = str(row.get("revision_of") or "")
        if previous is None:
            if revision_of:
                errors.append(f"{atom_id}: first outcome must not claim revision_of")
            effective[atom_id] = row
            continue

        expected_revision = digest(previous)
        if revision_of != expected_revision:
            errors.append(f"{atom_id}: outcome revision_of does not match the prior immutable row")

        previous_disposition = str(previous.get("disposition") or "unassessed")
        disposition = str(row.get("disposition") or "unassessed")
        if previous_disposition in {"done", "superseded"}:
            errors.append(f"{atom_id}: terminal {previous_disposition} outcome is immutable")
        elif disposition not in _OUTCOME_TRANSITIONS.get(previous_disposition, set()):
            errors.append(f"{atom_id}: outcome transition {previous_disposition!r} -> {disposition!r} is a rollback")

        previous_time = _parse_time(previous.get("assessed_at"))
        assessed_time = _parse_time(row.get("assessed_at"))
        if disposition == "unassessed":
            errors.append(f"{atom_id}: assessed outcome cannot return to unassessed")
        if previous_time is not None and (assessed_time is None or assessed_time <= previous_time):
            errors.append(f"{atom_id}: outcome revision assessed_at must increase monotonically")
        effective[atom_id] = row
    return errors


def _semantic_source_families(value: Any) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        return {}
    stable_fields = ("discovered", "converged", "pending", "errors", "unsupported")
    return {
        str(source): {field: int(counts.get(field) or 0) for field in stable_fields}
        for source, counts in sorted(value.items())
        if isinstance(counts, dict)
    }


def cursor_semantic(cursor: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": cursor.get("version", 1),
        "scope": cursor.get("scope", "fixture"),
        "target_scope": cursor.get("target_scope", cursor.get("scope", "fixture")),
        "horizon_days": cursor.get("horizon_days"),
        "pending_files": int(cursor.get("pending_files") or 0),
        "source_errors": [str(value) for value in (cursor.get("source_errors") or [])],
        "source_manifest_digest": cursor.get("source_manifest_digest"),
        "source_families": _semantic_source_families(cursor.get("source_families")),
        "adapter_gaps": [str(value) for value in (cursor.get("adapter_gaps") or [])],
        "adapter_gap_routes": [value for value in (cursor.get("adapter_gap_routes") or []) if isinstance(value, dict)],
        "files": cursor.get("files") or {},
    }


def cursor_digest(cursor: dict[str, Any]) -> str:
    return digest(cursor_semantic(cursor))


def _newer_signature(current: Any, proposed: Any) -> Any:
    if not isinstance(current, dict):
        return proposed
    if not isinstance(proposed, dict):
        return current
    current_mtime = int(current.get("mtime_ns") or 0)
    proposed_mtime = int(proposed.get("mtime_ns") or 0)
    if proposed_mtime > current_mtime:
        return proposed
    if proposed_mtime < current_mtime:
        return current
    return proposed if canonical_json(proposed) >= canonical_json(current) else current


def _target_scope(cursor: dict[str, Any]) -> str:
    value = str(cursor.get("target_scope") or cursor.get("scope") or "fixture")
    return value.removeprefix("partial:")


def merge_cursor(current: dict[str, Any], proposed: dict[str, Any] | None) -> dict[str, Any]:
    """Monotonically merge a scan result produced before the writer lock was acquired."""

    if proposed is None:
        return dict(current)
    current_revision = int(current.get("revision") or 0)
    raw_base_revision = proposed.get("base_revision")
    if raw_base_revision is None:
        raw_base_revision = proposed.get("revision") or 0
    proposed_base_revision = int(str(raw_base_revision))
    proposed_base_digest = str(proposed.get("base_cursor_digest") or "")
    stale = bool(
        (proposed_base_digest and proposed_base_digest != cursor_digest(current))
        or (current_revision and proposed_base_revision < current_revision)
    )
    if stale:
        # A scan based on an older cursor may contribute only monotonic file
        # signatures.  It may not replace manifest, family, gap, or scope
        # assertions made by the current writer.
        merged = dict(current)
        files = dict(current.get("files") or {})
        for key, signature in (proposed.get("files") or {}).items():
            files[str(key)] = _newer_signature(files.get(str(key)), signature)
        target = "all" if "all" in {_target_scope(current), _target_scope(proposed)} else _target_scope(current)
        stale_error = "stale cursor proposal requires a fresh scan"
        merged["files"] = files
        merged["target_scope"] = target
        merged["scope"] = f"partial:{target}"
        merged["pending_files"] = max(
            1,
            int(current.get("pending_files") or 0),
            int(proposed.get("pending_files") or 0),
        )
        merged["source_errors"] = list(dict.fromkeys([*(current.get("source_errors") or []), stale_error]))
        merged["revision"] = max(current_revision, int(proposed.get("revision") or 0)) + 1
        return merged
    merged = dict(current)
    merged.update(
        {key: value for key, value in proposed.items() if key not in {"files", "base_cursor_digest", "base_revision"}}
    )
    files = dict(current.get("files") or {})
    for key, signature in (proposed.get("files") or {}).items():
        files[str(key)] = _newer_signature(files.get(str(key)), signature)
    merged["files"] = files
    current_target = _target_scope(current)
    proposed_target = _target_scope(proposed)
    if proposed_target == "all":
        target = "all"
        scope = str(proposed.get("scope") or "partial:all")
        pending = int(proposed.get("pending_files") or 0)
        errors = [str(value) for value in (proposed.get("source_errors") or [])]
    elif current_target == "all":
        target = "all"
        proposed_has_gap = bool(int(proposed.get("pending_files") or 0) or proposed.get("source_errors"))
        current_was_complete = str(current.get("scope") or "") == "all"
        scope = "all" if current_was_complete and not proposed_has_gap else "partial:all"
        pending = (
            int(proposed.get("pending_files") or 0)
            if current_was_complete
            else max(
                int(current.get("pending_files") or 0),
                int(proposed.get("pending_files") or 0),
            )
        )
        errors = [str(value) for value in (proposed.get("source_errors") or [])]
        if not current_was_complete:
            errors = list(dict.fromkeys([*(current.get("source_errors") or []), *errors]))
        merged["source_manifest_digest"] = current.get("source_manifest_digest")
        merged["horizon_days"] = None
    else:
        target = proposed_target
        scope = str(proposed.get("scope") or target)
        pending = int(proposed.get("pending_files") or 0)
        errors = [str(value) for value in (proposed.get("source_errors") or [])]
    if pending or errors:
        scope = f"partial:{target}" if not scope.startswith("partial:") else scope
    merged["target_scope"] = target
    merged["scope"] = scope
    merged["pending_files"] = pending
    merged["source_errors"] = errors
    merged["revision"] = max(current_revision, int(proposed.get("revision") or 0)) + 1
    return merged


def build_snapshot(
    occurrences: Sequence[dict[str, Any]],
    atoms: Sequence[dict[str, Any]],
    outcome_rows: Sequence[dict[str, Any]],
    policy: dict[str, Any],
    cursor: dict[str, Any],
    *,
    journal_errors: Sequence[str] = (),
    evidence_root: Path | None = None,
) -> dict[str, Any]:
    outcomes = {str(row.get("atom_id")): row for row in outcome_rows if isinstance(row, dict) and row.get("atom_id")}
    recurrence = Counter(str(atom.get("lineage_id") or "") for atom in atoms)
    dependents: Counter[str] = Counter()
    for atom in atoms:
        for dependency in atom.get("dependency_ids") or []:
            dependents[str(dependency)] += 1
    parsed_times = [
        parsed
        for parsed in (_parse_time(occurrence.get("timestamp")) for occurrence in occurrences)
        if parsed is not None
    ]
    reference = max(parsed_times, default=dt.datetime(1970, 1, 1, tzinfo=dt.timezone.utc))
    max_recurrence = max(recurrence.values(), default=1)
    max_dependents = max(dependents.values(), default=1)
    weights = policy["weights"]
    weight_total = sum(float(weights[name]) for name in DIMENSIONS) or 1.0

    projected_atoms: list[dict[str, Any]] = []
    for source_atom in atoms:
        atom = dict(source_atom)
        lineage_id = str(atom.get("lineage_id") or "")
        dependency_count = len(atom.get("dependency_ids") or []) + dependents.get(str(atom["atom_id"]), 0)
        dimensions = {
            "operator_emphasis": _emphasis_score(atom),
            "system_leverage": _clamp(dependents.get(str(atom["atom_id"]), 0) / max_dependents),
            "magnitude": _magnitude_score(atom),
            "recurrence": _clamp(recurrence.get(lineage_id, 1) / max_recurrence),
            "dependency_impact": _clamp(dependency_count / max(1, max_dependents)),
            "preservation_risk": 0.0,
            "recency": _recency_score(atom.get("timestamp"), reference, float(policy["recency_half_life_days"])),
            "cost_of_delay": _clamp(dependency_count / max(1, max_dependents)),
        }
        for name, value in (atom.get("dimension_overrides") or {}).items():
            if name in DIMENSIONS:
                dimensions[name] = _clamp(value, dimensions[name])
        base_score = sum(dimensions[name] * float(weights[name]) for name in DIMENSIONS) / weight_total
        authority = str(atom.get("authority") or "unknown")
        band = (policy.get("authority_bands") or {}).get(authority, DEFAULT_POLICY["authority_bands"]["unknown"])
        band_floor = float(band["floor"])
        band_ceiling = float(band["ceiling"])
        score = band_floor + base_score * (band_ceiling - band_floor)
        atom["dimensions"] = dimensions
        atom["authority_band"] = {
            "floor": round(band_floor, 6),
            "ceiling": round(band_ceiling, 6),
        }
        atom["priority_score"] = round(score * 100.0, 3)
        atom["priority_reasons"] = [
            name for name, _value in sorted(dimensions.items(), key=lambda item: (-item[1], item[0]))[:3]
        ]
        atom["outcome"] = _outcome_for_atom(str(atom["atom_id"]), outcomes)
        projected_atoms.append(atom)

    successor_edges = {
        predecessor
        for atom in projected_atoms
        if lineage_edge_valid(atom, policy=policy)
        for predecessor in (atom.get("predecessor_ids") or [])
    }
    for atom in projected_atoms:
        atom["is_current_intent"] = str(atom["atom_id"]) not in successor_edges
    projected_atoms.sort(key=lambda atom: (-float(atom["priority_score"]), str(atom["atom_id"])))

    occurrence_rows = [dict(row) for row in occurrences]
    source_counts = Counter(str(row.get("source") or "unknown") for row in occurrence_rows)
    provenance_counts = Counter(str(row.get("provenance") or "unknown") for row in occurrence_rows)
    kind_counts = Counter(str(atom.get("kind") or "unknown") for atom in projected_atoms)
    disposition_counts = Counter(
        str((atom.get("outcome") or {}).get("disposition") or "unassessed") for atom in projected_atoms
    )
    authority_counts = Counter(str(atom.get("authority") or "unknown") for atom in projected_atoms)

    snapshot: dict[str, Any] = {
        "version": 1,
        "updated_through": reference.isoformat(timespec="seconds") if parsed_times else None,
        "policy_digest": digest(policy),
        "source_cursor_digest": cursor_digest(cursor),
        "source_scope": cursor_semantic(cursor),
        "coverage": {
            "occurrences": len(occurrence_rows),
            "operator_occurrences": sum(1 for row in occurrence_rows if row.get("authority") == "operator"),
            "derived_occurrences": sum(1 for row in occurrence_rows if row.get("authority") == "derived"),
            "excluded_occurrences": sum(1 for row in occurrence_rows if row.get("excluded_reason")),
            "atoms": len(projected_atoms),
            "current_intents": sum(1 for atom in projected_atoms if atom.get("is_current_intent")),
            "current_unresolved_atoms": sum(
                1
                for atom in projected_atoms
                if atom.get("is_current_intent")
                and str((atom.get("outcome") or {}).get("disposition") or "unassessed") not in {"done", "superseded"}
            ),
            "lineages": len({str(atom.get("lineage_id")) for atom in projected_atoms}),
            "assessed_atoms": len(projected_atoms) - int(disposition_counts.get("unassessed", 0)),
        },
        "counts": {
            "sources": dict(source_counts.most_common()),
            "provenance": dict(provenance_counts.most_common()),
            "kinds": dict(kind_counts.most_common()),
            "authority": dict(authority_counts.most_common()),
            "dispositions": dict(disposition_counts.most_common()),
        },
        "occurrences": occurrence_rows,
        "atoms": projected_atoms,
    }
    validation_errors = [
        *journal_errors,
        *validate_snapshot(
            snapshot,
            outcome_rows=outcome_rows,
            evidence_root=evidence_root,
            policy=policy,
        ),
    ]
    operator_lineages: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for atom in projected_atoms:
        if atom.get("authority") == "operator":
            operator_lineages[str(atom.get("lineage_id") or "")].append(atom)
    repeat_limit = int(policy["unconverged_repeat_limit"])
    for lineage_id, rows in operator_lineages.items():
        if len(rows) <= repeat_limit:
            continue
        dispositions = {str((row.get("outcome") or {}).get("disposition") or "unassessed") for row in rows}
        if dispositions <= {"unassessed"}:
            validation_errors.append(
                f"{rows[0].get('atom_id')}: {len(rows)} operator repeats exceed {repeat_limit} without assessment"
            )
    snapshot["validation"] = {"ok": not validation_errors, "errors": validation_errors}
    semantic = {key: value for key, value in snapshot.items() if key != "semantic_digest"}
    snapshot["semantic_digest"] = digest(semantic)
    return snapshot


def validate_snapshot(
    snapshot: dict[str, Any],
    *,
    outcome_rows: Sequence[dict[str, Any]] = (),
    evidence_root: Path | None = None,
    policy: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    atoms = [row for row in (snapshot.get("atoms") or []) if isinstance(row, dict)]
    atoms_by_id = {str(atom.get("atom_id")): atom for atom in atoms if atom.get("atom_id")}
    if len(atoms_by_id) != len(atoms):
        errors.append("atom journal contains duplicate or missing atom ids")
    occurrences = [row for row in (snapshot.get("occurrences") or []) if isinstance(row, dict)]
    occurrences_by_id = {str(row.get("occurrence_id")): row for row in occurrences if row.get("occurrence_id")}
    if len(occurrences_by_id) != len(occurrences):
        errors.append("event journal contains duplicate or missing occurrence ids")
    for occurrence in snapshot.get("occurrences") or []:
        if not isinstance(occurrence, dict):
            errors.append("non-object occurrence row")
            continue
        occurrence_id = str(occurrence.get("occurrence_id") or "unknown")
        linked_ids = [str(value) for value in (occurrence.get("atom_ids") or [])]
        if not linked_ids and not occurrence.get("excluded_reason"):
            errors.append(f"{occurrence.get('occurrence_id')}: occurrence lacks atoms or exclusion")
        if any(value not in atoms_by_id for value in linked_ids):
            errors.append(f"{occurrence_id}: occurrence references missing atoms")
        if occurrence.get("authority") == "operator" and not linked_ids:
            if occurrence.get("excluded_reason") not in {"transport_duplicate", "transport_echo"}:
                errors.append(f"{occurrence.get('occurrence_id')}: operator occurrence lacks atom coverage")
        if not str(occurrence.get("raw_object") or "").strip():
            errors.append(f"{occurrence_id}: occurrence lacks a private raw object reference")
        expected_coverage = set(str(value) for value in (occurrence.get("coverage_segment_hashes") or []))
        actual_coverage = {
            str(value)
            for atom_id in linked_ids
            for value in (atoms_by_id.get(atom_id) or {}).get("coverage_hashes") or []
        }
        if expected_coverage - actual_coverage:
            errors.append(f"{occurrence_id}: structural atom coverage is incomplete")
    for atom in atoms:
        atom_id = str(atom.get("atom_id") or "unknown")
        if str(atom.get("occurrence_id") or "") not in occurrences_by_id:
            errors.append(f"{atom_id}: atom references a missing occurrence")
        if str(atom.get("kind") or "") not in ATOM_KINDS:
            errors.append(f"{atom_id}: invalid atom kind")
        if str(atom.get("atomization_mode") or "") not in {
            "semantic_adapter",
            "structural_fallback",
        }:
            errors.append(f"{atom_id}: invalid atomization mode")
        dimensions = atom.get("dimensions") or {}
        if set(dimensions) != set(DIMENSIONS):
            errors.append(f"{atom_id}: priority dimensions incomplete")
        for relation_id in [
            *(atom.get("predecessor_ids") or []),
            *(atom.get("dependency_ids") or []),
        ]:
            if str(relation_id) not in atoms_by_id or str(relation_id) == atom_id:
                errors.append(f"{atom_id}: lineage/dependency edge does not resolve")
        predecessor_ids = [str(value) for value in (atom.get("predecessor_ids") or [])]
        if predecessor_ids:
            unrelated = [
                predecessor_id
                for predecessor_id in predecessor_ids
                if str((atoms_by_id.get(predecessor_id) or {}).get("lineage_id") or "")
                != str(atom.get("lineage_id") or "")
            ]
            if unrelated:
                errors.append(f"{atom_id}: predecessor edge crosses unrelated lineages")
            if not lineage_edge_valid(atom, policy=policy):
                errors.append(f"{atom_id}: predecessor edge lacks valid correction/refinement evidence")
        errors.extend(validate_outcome(atom, atoms_by_id, evidence_root=evidence_root))
    errors.extend(
        validate_outcome_history(
            outcome_rows,
            atoms_by_id,
            evidence_root=evidence_root,
        )
    )
    return errors


def _safe_evidence_refs(atom: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for item in (atom.get("outcome") or {}).get("evidence") or []:
        kind = str(item.get("kind") or "")
        ref = canonical_evidence_ref(kind, item.get("ref"))
        if ref:
            refs.append(ref)
    return refs


def public_projection(snapshot: dict[str, Any], *, limit: int | None = None) -> dict[str, Any]:
    unresolved = [
        atom
        for atom in snapshot.get("atoms") or []
        if (atom.get("outcome") or {}).get("disposition") not in {"done", "superseded"}
        and atom.get("is_current_intent")
    ]
    rows = []
    selected = unresolved if limit is None else unresolved[:limit]
    for atom in selected:
        outcome = atom.get("outcome") or {}
        rows.append(
            {
                "atom_id": atom.get("atom_id"),
                "kind": atom.get("kind"),
                "authority": atom.get("authority"),
                "atomization_mode": atom.get("atomization_mode"),
                "classification_confidence": atom.get("classification_confidence"),
                "priority_score": atom.get("priority_score"),
                "priority_reasons": atom.get("priority_reasons") or [],
                "dimensions": atom.get("dimensions") or {},
                "disposition": outcome.get("disposition"),
                "owner": outcome.get("owner") or atom.get("owner") or "unassigned",
                "owner_route": atom.get("owner_route") or "unrouted",
                "residual_atom_ids": outcome.get("residual_atom_ids") or [],
                "evidence_refs": _safe_evidence_refs(atom),
            }
        )
    public = {
        "version": snapshot.get("version"),
        "updated_through": snapshot.get("updated_through"),
        "semantic_digest": snapshot.get("semantic_digest"),
        "policy_digest": snapshot.get("policy_digest"),
        "source_cursor_digest": snapshot.get("source_cursor_digest"),
        "source_scope": {
            "scope": (snapshot.get("source_scope") or {}).get("scope"),
            "target_scope": (snapshot.get("source_scope") or {}).get("target_scope"),
            "horizon_days": (snapshot.get("source_scope") or {}).get("horizon_days"),
            "pending_files": (snapshot.get("source_scope") or {}).get("pending_files", 0),
            "source_error_count": len((snapshot.get("source_scope") or {}).get("source_errors") or []),
            "source_manifest_digest": (snapshot.get("source_scope") or {}).get("source_manifest_digest"),
            "adapter_gaps": (snapshot.get("source_scope") or {}).get("adapter_gaps") or [],
            "adapter_gap_routes": (snapshot.get("source_scope") or {}).get("adapter_gap_routes") or [],
        },
        "coverage": snapshot.get("coverage") or {},
        "counts": snapshot.get("counts") or {},
        "validation": snapshot.get("validation") or {},
        "unresolved_atoms": rows,
        "unresolved_atoms_truncated": max(0, len(unresolved) - len(rows)),
    }
    public["projection_digest"] = digest(public)
    return public


def _render_counts(values: dict[str, int]) -> str:
    return ", ".join(f"`{key}` {value}" for key, value in values.items()) or "none"


def render_markdown(public: dict[str, Any], policy: dict[str, Any]) -> str:
    coverage = public.get("coverage") or {}
    counts = public.get("counts") or {}
    rows = public.get("unresolved_atoms") or []
    scope = public.get("source_scope") or {}
    lines = [
        "# Prompt Atom Ledger",
        "",
        "## Canonical Decision",
        "",
        "- The individual ask, correction, constraint, acceptance criterion, or human gate is the unit of intent.",
        "- Sessions and batches are compatibility containers; they never prove that their child asks are complete.",
        "- Raw prompt bodies and source coordinates stay in the ignored private journal. This projection is redacted.",
        "- External classifiers may supply provider-neutral atom candidates and dimension overrides. No model or catalog name is pinned here; structural fallback preserves coverage when no classifier is reachable.",
        "- `done` requires a referenced passing predicate. Candidate similarity, git proximity, and recorded custody are not completion proof.",
        "",
        "## Coverage",
        "",
        f"- Source scope: `{scope.get('scope') or 'unknown'}`; target: `{scope.get('target_scope') or 'unknown'}`; horizon days: `{scope.get('horizon_days')}`; pending files: `{scope.get('pending_files', 0)}`; source errors: `{scope.get('source_error_count', 0)}`.",
        f"- Prompt occurrences: `{coverage.get('occurrences', 0)}`; operator: `{coverage.get('operator_occurrences', 0)}`; derived: `{coverage.get('derived_occurrences', 0)}`.",
        f"- Ask atoms: `{coverage.get('atoms', 0)}` across `{coverage.get('lineages', 0)}` lineages; current intents: `{coverage.get('current_intents', 0)}`.",
        f"- Assessed atoms: `{coverage.get('assessed_atoms', 0)}`; excluded occurrences: `{coverage.get('excluded_occurrences', 0)}`.",
        f"- Dispositions: {_render_counts(counts.get('dispositions') or {})}.",
        f"- Speech acts: {_render_counts(counts.get('kinds') or {})}.",
        f"- Validation: `{'PASS' if (public.get('validation') or {}).get('ok') else 'FAIL'}`.",
        "",
        "## Dynamic Priority Contract",
        "",
        "Priority is recomputed from evidence and lineage on every projection. The runtime policy is data, not a model catalog:",
        "",
    ]
    for name in DIMENSIONS:
        lines.append(f"- `{name}` weight: `{policy['weights'][name]}`.")
    lines += [
        "",
        "## Highest-Ranked Current Unresolved Atoms",
        "",
        "| Rank | Atom | Kind | Authority | Score | Reasons | Disposition | Evidence |",
        "|---:|---|---|---|---:|---|---|---|",
    ]
    for rank, row in enumerate(rows[:50], start=1):
        evidence = ", ".join(f"`{ref}`" for ref in row.get("evidence_refs") or []) or "none"
        reasons = ", ".join(f"`{reason}`" for reason in row.get("priority_reasons") or []) or "none"
        lines.append(
            f"| {rank} | `{row['atom_id']}` | `{row['kind']}` | `{row['authority']}` | "
            f"{row['priority_score']} | {reasons} | `{row['disposition']}` | {evidence} |"
        )
    if not rows:
        lines.append("| 0 | none | n/a | n/a | 0 | none | n/a | none |")
    if int(public.get("unresolved_atoms_truncated") or 0):
        lines += [
            "",
            f"_{public['unresolved_atoms_truncated']} additional current unresolved atoms remain in the private projection._",
        ]
    lines += [
        "",
        "## Commands",
        "",
        "- Incremental native scan: `python3 scripts/prompt-atom-ledger.py --scan --write`",
        "- Full source convergence: `python3 scripts/prompt-atom-ledger.py --scan --all --write`",
        "- Verify private/public projection: `python3 scripts/prompt-atom-ledger.py --check`",
        "",
    ]
    return "\n".join(lines)


def _compact_source_scope(snapshot: dict[str, Any]) -> dict[str, Any]:
    scope = snapshot.get("source_scope") or {}
    return {
        "scope": scope.get("scope"),
        "target_scope": scope.get("target_scope"),
        "horizon_days": scope.get("horizon_days"),
        "pending_files": int(scope.get("pending_files") or 0),
        "source_errors": [str(value) for value in (scope.get("source_errors") or [])],
        "source_manifest_digest": scope.get("source_manifest_digest"),
        "source_families": _semantic_source_families(scope.get("source_families")),
        "adapter_gaps": [str(value) for value in (scope.get("adapter_gaps") or [])],
        "adapter_gap_routes": [value for value in (scope.get("adapter_gap_routes") or []) if isinstance(value, dict)],
    }


def _path_signature(path: Path) -> dict[str, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "mode": stat.st_mode & 0o777}


def _raw_store_signature(paths: LedgerPaths) -> str:
    rows: list[tuple[str, int, int, int]] = []
    if paths.raw_objects.exists():
        for path in sorted(paths.raw_objects.rglob("*.txt.gz")):
            try:
                stat = path.stat()
            except OSError:
                rows.append((str(path.relative_to(paths.raw_objects)), -1, -1, -1))
                continue
            rows.append(
                (
                    str(path.relative_to(paths.raw_objects)),
                    stat.st_size,
                    stat.st_mtime_ns,
                    stat.st_mode & 0o777,
                )
            )
    return digest(rows)


def private_marker(snapshot: dict[str, Any], public: dict[str, Any], *, paths: LedgerPaths) -> dict[str, Any]:
    """Return a compact checkpoint; journals and raw objects remain canonical."""

    return {
        "version": snapshot.get("version"),
        "updated_through": snapshot.get("updated_through"),
        "semantic_digest": snapshot.get("semantic_digest"),
        "policy_digest": snapshot.get("policy_digest"),
        "source_cursor_digest": snapshot.get("source_cursor_digest"),
        "source_scope": _compact_source_scope(snapshot),
        "coverage": snapshot.get("coverage") or {},
        "counts": snapshot.get("counts") or {},
        "validation": snapshot.get("validation") or {},
        "public_projection_digest": public.get("projection_digest"),
        "journal_signatures": {
            "events": _path_signature(paths.event_journal),
            "outcomes": _path_signature(paths.outcome_journal),
            "cursor": _path_signature(paths.cursor),
            "raw_store": _raw_store_signature(paths),
        },
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")


def _public_digest_valid(public: dict[str, Any]) -> bool:
    claimed = str(public.get("projection_digest") or "")
    material = {key: value for key, value in public.items() if key != "projection_digest"}
    return bool(claimed and claimed == digest(material))


def validate_raw_references(
    paths: LedgerPaths,
    occurrences: Sequence[dict[str, Any]],
    *,
    verify_content: bool = False,
) -> list[str]:
    errors: list[str] = []
    verified: set[str] = set()
    for occurrence in occurrences:
        occurrence_id = str(occurrence.get("occurrence_id") or "unknown")
        relative = str(occurrence.get("raw_object") or "")
        prompt_hash = str(occurrence.get("prompt_hash") or "")
        if not relative:
            continue
        expected = str(Path(prompt_hash[:2]) / f"{prompt_hash}.txt.gz")
        if relative != expected:
            errors.append(f"{occurrence_id}: raw object reference does not match prompt hash")
            continue
        candidate = (paths.raw_objects / relative).resolve()
        if paths.raw_objects.resolve() not in candidate.parents or not candidate.is_file():
            errors.append(f"{occurrence_id}: private raw object is missing")
            continue
        try:
            mode = candidate.stat().st_mode & 0o777
        except OSError as exc:
            errors.append(f"{occurrence_id}: private raw object cannot be stat'ed: {exc}")
            continue
        if mode & 0o222:
            errors.append(f"{occurrence_id}: private raw object is not read-only")
        if verify_content and relative not in verified:
            try:
                raw = read_raw_object(paths, relative)
            except (OSError, EOFError, ValueError, gzip.BadGzipFile) as exc:
                errors.append(f"{occurrence_id}: private raw object is unreadable: {exc}")
            else:
                actual_hash = hashlib.sha256(raw.encode("utf-8", errors="replace")).hexdigest()
                if actual_hash != prompt_hash:
                    errors.append(f"{occurrence_id}: private raw object digest mismatch")
            verified.add(relative)
    return errors


def _index_by_id(rows: Sequence[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(row[key]): row for row in rows if isinstance(row, dict) and row.get(key)}


def _dedupe_key(occurrence: dict[str, Any]) -> tuple[str, str, str]:
    parsed = _parse_time(occurrence.get("timestamp"))
    timestamp = parsed.isoformat(timespec="seconds") if parsed else str(occurrence.get("timestamp") or "")[:19]
    return (
        str(occurrence.get("session_ref_hash") or ""),
        str(occurrence.get("prompt_hash") or ""),
        timestamp,
    )


def _occurrence_order_key(occurrence: dict[str, Any]) -> tuple[dt.datetime, int] | None:
    parsed = _parse_time(occurrence.get("timestamp"))
    if parsed is None:
        return None
    return parsed, int(occurrence.get("event_index") or 0)


def _adjacent_operator_predecessor(
    occurrence: dict[str, Any],
    occurrences: Sequence[dict[str, Any]],
    atoms_by_occurrence: dict[str, list[str]],
) -> str | None:
    current_key = _occurrence_order_key(occurrence)
    if current_key is None:
        return None
    session_hash = str(occurrence.get("session_ref_hash") or "")
    candidates: list[tuple[tuple[dt.datetime, int], dict[str, Any]]] = []
    for row in occurrences:
        if str(row.get("session_ref_hash") or "") != session_hash:
            continue
        if row.get("authority") != "operator" or row.get("provenance") == "transport_echo":
            continue
        row_key = _occurrence_order_key(row)
        if row_key is None or row_key >= current_key:
            continue
        candidates.append((row_key, row))
    if not candidates:
        return None
    _key, predecessor = max(candidates, key=lambda item: item[0])
    atom_ids = atoms_by_occurrence.get(str(predecessor.get("occurrence_id") or ""), [])
    return atom_ids[-1] if atom_ids else None


def lineage_edge_valid(atom: dict[str, Any], *, policy: dict[str, Any] | None = None) -> bool:
    if not atom.get("predecessor_ids"):
        return True
    evidence = atom.get("lineage_evidence")
    if atom.get("atomization_mode") != "semantic_adapter" or not isinstance(evidence, dict):
        return False
    active_policy = policy or DEFAULT_POLICY
    threshold = float((active_policy.get("confidence_thresholds") or {}).get("lineage_edge", 0.5))
    return bool(
        atom.get("relation") in {"corrects", "refines", "supersedes"}
        and evidence.get("kind") == "semantic_adapter"
        and str(evidence.get("classifier_provenance") or "") == str(atom.get("classifier_provenance") or "")
        and _clamp(evidence.get("confidence")) >= threshold
    )


def _event_ingest_order(item: tuple[int, dict[str, Any]]) -> tuple[Any, ...]:
    original_index, event = item
    parsed = _parse_time(event.get("timestamp"))
    return (
        str(event.get("source") or "unknown"),
        str(event.get("session_ref") or event.get("existing_occurrence_id") or "unknown"),
        parsed is None,
        parsed or dt.datetime.max.replace(tzinfo=dt.timezone.utc),
        int(event.get("event_index") or 0),
        int(event.get("text_index") or 0),
        original_index,
    )


def update_ledger(
    paths: LedgerPaths,
    *,
    events: Sequence[dict[str, Any]] = (),
    outcomes: Sequence[dict[str, Any]] = (),
    cursor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Idempotently append new input and atomically refresh both projections."""

    paths.private_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(paths.private_dir, 0o700)
    with exclusive_lock(paths.lock):
        policy = load_policy(paths.policy)
        current_cursor, cursor_errors = load_json_strict(paths.cursor)
        if cursor_errors:
            raise ValueError("; ".join(cursor_errors))
        effective_cursor = merge_cursor(current_cursor, cursor)
        if cursor_digest(effective_cursor) == cursor_digest(current_cursor):
            effective_cursor = current_cursor

        marker = load_json(paths.private_snapshot)
        existing_public = load_json(paths.public_snapshot)
        fast_public_ok = bool(
            marker
            and existing_public
            and not events
            and not outcomes
            and cursor_digest(effective_cursor) == cursor_digest(current_cursor)
            and marker.get("policy_digest") == digest(policy)
            and marker.get("source_cursor_digest") == cursor_digest(current_cursor)
            and marker.get("public_projection_digest") == existing_public.get("projection_digest")
            and marker.get("semantic_digest") == existing_public.get("semantic_digest")
            and marker.get("journal_signatures")
            == {
                "events": _path_signature(paths.event_journal),
                "outcomes": _path_signature(paths.outcome_journal),
                "cursor": _path_signature(paths.cursor),
                "raw_store": _raw_store_signature(paths),
            }
            and _public_digest_valid(existing_public)
            and paths.public_snapshot.exists()
            and paths.public_snapshot.read_bytes() == _json_bytes(existing_public)
            and paths.public_markdown.exists()
            and paths.public_markdown.read_text(encoding="utf-8", errors="replace")
            == render_markdown(existing_public, policy)
        )
        if fast_public_ok:
            result = dict(marker)
            result["write_changed"] = False
            result["appended"] = {
                "occurrences": 0,
                "atoms": 0,
                "outcomes": 0,
                "reclassified": 0,
            }
            return result

        occurrence_rows, atom_rows, event_errors = load_event_journal(paths.event_journal)
        outcome_rows, outcome_errors = load_jsonl_strict(paths.outcome_journal)
        journal_errors = [*event_errors, *outcome_errors]
        if journal_errors:
            raise ValueError("; ".join(journal_errors))
        occurrence_by_id = _index_by_id(occurrence_rows, "occurrence_id")
        atom_by_id = _index_by_id(atom_rows, "atom_id")
        atoms_by_occurrence = {
            str(row.get("occurrence_id") or ""): [str(value) for value in (row.get("atom_ids") or [])]
            for row in occurrence_rows
        }
        outcomes_by_atom = {
            str(row.get("atom_id")): row for row in outcome_rows if isinstance(row, dict) and row.get("atom_id")
        }

        new_occurrences: list[dict[str, Any]] = []
        new_atoms: list[dict[str, Any]] = []
        new_event_rows: list[dict[str, Any]] = []
        replacements: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
        ordered_events = sorted(
            ((index, event) for index, event in enumerate(events) if isinstance(event, dict)),
            key=_event_ingest_order,
        )
        for _input_index, event in ordered_events:
            if not isinstance(event, dict):
                continue
            proposed_occurrence = occurrence_from_event(event)
            requested_existing_id = str(event.get("existing_occurrence_id") or "")
            if requested_existing_id:
                existing_occurrence = occurrence_by_id.get(requested_existing_id)
                if existing_occurrence is None:
                    raise ValueError(f"classification revision references unknown occurrence: {requested_existing_id}")
                if proposed_occurrence.get("prompt_hash") != existing_occurrence.get("prompt_hash"):
                    raise ValueError(f"classification revision body does not match occurrence: {requested_existing_id}")
                occurrence = dict(existing_occurrence)
                occurrence["raw_text"] = proposed_occurrence["raw_text"]
                occurrence["atom_ids"] = []
                occurrence["excluded_reason"] = None
                occurrence_id = requested_existing_id
            else:
                occurrence = proposed_occurrence
                occurrence_id = str(occurrence["occurrence_id"])
                existing_occurrence = occurrence_by_id.get(occurrence_id)
            is_revision = bool(existing_occurrence and isinstance(event.get("atoms"), list))
            if existing_occurrence and not is_revision:
                continue
            classification_digest = digest(event.get("atoms") or []) if is_revision else None
            if (
                is_revision
                and existing_occurrence is not None
                and existing_occurrence.get("classification_digest") == classification_digest
            ):
                continue
            atoms = atoms_from_event(occurrence, event, policy)
            preceding_operator_atoms: list[str] = []
            for atom in atoms:
                if atom["kind"] == "correction" and not atom["predecessor_ids"]:
                    adjacent = (
                        preceding_operator_atoms[-1]
                        if preceding_operator_atoms
                        else _adjacent_operator_predecessor(
                            occurrence,
                            [*occurrence_rows, *new_occurrences],
                            atoms_by_occurrence,
                        )
                    )
                    if adjacent:
                        # Position is a useful review hint, not semantic proof.
                        # Only a grounded classifier edge may retire an older
                        # current intent.
                        atom["candidate_predecessor_ids"] = [adjacent]
                if occurrence.get("authority") == "operator":
                    preceding_operator_atoms.append(str(atom["atom_id"]))
            raw_text = str(occurrence.pop("raw_text", ""))
            if existing_occurrence:
                occurrence["raw_object"] = existing_occurrence.get("raw_object")
                occurrence["classification_revision"] = int(existing_occurrence.get("classification_revision") or 0) + 1
                occurrence["classification_digest"] = classification_digest
                old_atom_ids = set(atoms_by_occurrence.get(occurrence_id, []))
                new_atom_ids = {str(atom["atom_id"]) for atom in atoms}
                assessed_removed = {
                    atom_id
                    for atom_id in old_atom_ids - new_atom_ids
                    if str((outcomes_by_atom.get(atom_id) or {}).get("disposition") or "unassessed") != "unassessed"
                }
                if assessed_removed:
                    raise ValueError(
                        "classification revision would orphan assessed atoms: " + ", ".join(sorted(assessed_removed))
                    )
                replacements[occurrence_id] = (occurrence, atoms)
                new_event_rows.append(
                    {
                        "occurrence": occurrence,
                        "atoms": atoms,
                        "revision_of": occurrence_id,
                    }
                )
                for old_atom_id in old_atom_ids:
                    atom_by_id.pop(old_atom_id, None)
            else:
                occurrence["raw_object"] = preserve_raw_object(paths, str(occurrence["prompt_hash"]), raw_text)
                occurrence["classification_revision"] = 0
                occurrence["classification_digest"] = (
                    digest(event.get("atoms") or []) if isinstance(event.get("atoms"), list) else None
                )
                new_occurrences.append(occurrence)
                new_event_rows.append({"occurrence": occurrence, "atoms": atoms})
            occurrence_by_id[occurrence_id] = occurrence
            atoms_by_occurrence[occurrence_id] = [str(atom["atom_id"]) for atom in atoms]
            for atom in atoms:
                atom_by_id[str(atom["atom_id"])] = atom
                new_atoms.append(atom)

        malformed_outcomes = [
            index
            for index, row in enumerate(outcomes)
            if not isinstance(row, dict) or not str(row.get("atom_id") or "")
        ]
        if malformed_outcomes:
            raise ValueError(
                "outcomes must be objects with atom_id: " + ", ".join(str(index) for index in malformed_outcomes)
            )
        known_outcome_rows = {canonical_json(row) for row in outcome_rows}
        new_outcomes = [
            row
            for row in outcomes
            if isinstance(row, dict) and row.get("atom_id") and canonical_json(row) not in known_outcome_rows
        ]
        unknown_outcomes = [
            str(row.get("atom_id")) for row in new_outcomes if str(row.get("atom_id")) not in atom_by_id
        ]
        if unknown_outcomes:
            raise ValueError(f"outcomes reference unknown atoms: {', '.join(unknown_outcomes)}")
        outcome_validation_errors = validate_outcome_history(
            [*outcome_rows, *new_outcomes],
            atom_by_id,
            evidence_root=paths.root,
        )
        if outcome_validation_errors:
            raise ValueError("invalid outcome history: " + "; ".join(outcome_validation_errors))
        append_jsonl(paths.event_journal, new_event_rows)
        append_jsonl(paths.outcome_journal, new_outcomes)

        if replacements:
            occurrence_rows = [
                replacements.get(str(row.get("occurrence_id") or ""), (row, []))[0] for row in occurrence_rows
            ]
            atom_rows = [atom for atom in atom_rows if str(atom.get("occurrence_id") or "") not in replacements]
            atom_rows.extend(
                atom for _occurrence, replacement_atoms in replacements.values() for atom in replacement_atoms
            )
        occurrence_rows.extend(new_occurrences)
        atom_rows.extend(atom for atom in new_atoms if str(atom.get("occurrence_id") or "") not in replacements)
        outcome_rows.extend(new_outcomes)
        if cursor is not None and cursor_digest(effective_cursor) != cursor_digest(current_cursor):
            atomic_write_bytes(paths.cursor, _json_bytes(effective_cursor), mode=0o600)

        raw_errors = validate_raw_references(paths, occurrence_rows, verify_content=True)
        snapshot = build_snapshot(
            occurrence_rows,
            atom_rows,
            outcome_rows,
            policy,
            effective_cursor,
            journal_errors=raw_errors,
            evidence_root=paths.root,
        )
        public = public_projection(snapshot)
        markdown = render_markdown(public, policy)
        next_marker = private_marker(snapshot, public, paths=paths)
        public_bytes = _json_bytes(public)
        markdown_bytes = markdown.encode("utf-8")
        marker_bytes = _json_bytes(next_marker)
        changed = False
        if not paths.public_snapshot.exists() or paths.public_snapshot.read_bytes() != public_bytes:
            atomic_write_bytes(paths.public_snapshot, public_bytes, mode=0o644)
            changed = True
        if not paths.public_markdown.exists() or paths.public_markdown.read_bytes() != markdown_bytes:
            atomic_write_bytes(paths.public_markdown, markdown_bytes, mode=0o644)
            changed = True
        # The checkpoint is last: a crash before this line leaves check_ledger red.
        if not paths.private_snapshot.exists() or paths.private_snapshot.read_bytes() != marker_bytes:
            atomic_write_bytes(paths.private_snapshot, marker_bytes, mode=0o600)
            changed = True
        snapshot["write_changed"] = changed
        snapshot["appended"] = {
            "occurrences": len(new_occurrences),
            "atoms": len(new_atoms),
            "outcomes": len(new_outcomes),
            "reclassified": len(replacements),
        }
        return snapshot


def check_ledger(paths: LedgerPaths, *, require_scope: str | None = None) -> list[str]:
    private = load_json(paths.private_snapshot)
    public = load_json(paths.public_snapshot)
    errors: list[str] = []
    if paths.private_snapshot.exists() and not private:
        errors.append("private prompt checkpoint is malformed")
    if paths.public_snapshot.exists() and not public:
        errors.append("public prompt projection is malformed")
    private_artifacts_exist = any(
        path.exists()
        for path in (
            paths.event_journal,
            paths.outcome_journal,
            paths.cursor,
            paths.raw_objects,
        )
    )
    if private_artifacts_exist and not private:
        errors.append("private prompt checkpoint is missing while private journals remain")
    source = private or public
    if not source:
        return ["prompt atom ledger is missing"]
    validation = source.get("validation") or {}
    if not validation.get("ok"):
        errors.extend(str(value) for value in (validation.get("errors") or ["validation failed"]))
    scope = str((source.get("source_scope") or {}).get("scope") or "unknown")
    if require_scope and scope != require_scope:
        errors.append(f"source scope is {scope}; require {require_scope}")
    if private:
        live_cursor, cursor_errors = load_json_strict(paths.cursor)
        errors.extend(cursor_errors)
        if private.get("source_cursor_digest") != cursor_digest(live_cursor):
            errors.append("source cursor changed after the private projection")
        occurrence_rows, atom_rows, event_errors = load_event_journal(paths.event_journal)
        outcome_rows, outcome_errors = load_jsonl_strict(paths.outcome_journal)
        raw_errors = validate_raw_references(paths, occurrence_rows, verify_content=True)
        rebuilt = build_snapshot(
            occurrence_rows,
            atom_rows,
            outcome_rows,
            load_policy(paths.policy),
            live_cursor,
            journal_errors=[*event_errors, *outcome_errors, *raw_errors],
            evidence_root=paths.root,
        )
        if not (rebuilt.get("validation") or {}).get("ok"):
            errors.extend(str(value) for value in (rebuilt.get("validation") or {}).get("errors") or [])
        rebuilt_public = public_projection(rebuilt)
        rebuilt_marker = private_marker(rebuilt, rebuilt_public, paths=paths)
        if private != rebuilt_marker:
            errors.append("private journals do not match the compact checkpoint")
        if not public:
            errors.append("public prompt projection is missing")
        elif paths.public_snapshot.read_bytes() != _json_bytes(rebuilt_public):
            errors.append("public prompt projection does not match the private journals")
        expected_markdown = render_markdown(rebuilt_public, load_policy(paths.policy))
        if not paths.public_markdown.exists():
            errors.append("public prompt Markdown is missing")
        elif paths.public_markdown.read_text(encoding="utf-8", errors="replace") != expected_markdown:
            errors.append("public prompt Markdown does not match the private journals")
    elif public:
        if not _public_digest_valid(public):
            errors.append("public prompt projection digest is invalid")
        if public.get("policy_digest") != digest(load_policy(paths.policy)):
            errors.append("public prompt projection policy digest is stale")
        if paths.public_snapshot.read_bytes() != _json_bytes(public):
            errors.append("public prompt projection is not canonical")
        expected_markdown = render_markdown(public, load_policy(paths.policy))
        if not paths.public_markdown.exists():
            errors.append("public prompt Markdown is missing")
        elif paths.public_markdown.read_text(encoding="utf-8", errors="replace") != expected_markdown:
            errors.append("public prompt Markdown does not match its projection")
    return errors
