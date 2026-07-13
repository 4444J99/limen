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
import importlib.util
import json
import math
import os
import re
import secrets
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
    source_scan_receipts: Path
    cursor: Path
    lock: Path
    private_snapshot: Path
    public_snapshot: Path
    public_markdown: Path
    public_seal: Path
    policy: Path

    @classmethod
    def for_root(
        cls,
        root: Path,
        *,
        private_root: Path | None = None,
        public_markdown: Path | None = None,
        public_snapshot: Path | None = None,
        public_seal: Path | None = None,
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
            source_scan_receipts=private_dir / "source-scan-receipts",
            cursor=private_dir / "source-cursor.json",
            lock=private_dir / "writer.lock",
            private_snapshot=private_dir / "prompt-atom-ledger.json",
            public_snapshot=public_snapshot or root / "docs" / "prompt-atom-ledger.json",
            public_markdown=public_markdown or root / "docs" / "prompt-atom-ledger.md",
            public_seal=public_seal or root / "docs" / "prompt-authority-seal.json",
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


def raw_object_reference(prompt_hash: str) -> str:
    return str(Path(prompt_hash[:2]) / f"{prompt_hash}.txt.gz")


def preserve_raw_object(paths: LedgerPaths, prompt_hash: str, text: str) -> str:
    """Content-address the exact private body once; journals keep only this opaque reference."""

    relative = Path(raw_object_reference(prompt_hash))
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
    if isinstance(value, bool):
        return None
    if not value:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
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


def _event_position(event: dict[str, Any], field: str) -> int:
    value = event.get(field, 0)
    if value is None:
        value = 0
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


def occurrence_from_event(event: dict[str, Any]) -> dict[str, Any]:
    text = str(event.get("text") or "")
    source = str(event.get("source") or "unknown")
    session_ref = str(event.get("session_ref") or "unknown")
    event_index = _event_position(event, "event_index")
    text_index = _event_position(event, "text_index")
    event_ref = str(event.get("event_ref") or event_index or "0")
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
        "event_index": event_index,
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


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _nonnegative_exact_int(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, int) and value >= 0


_LEGACY_FILE_SIGNATURE_FIELDS = {"size", "mtime_ns"}
_STRONG_FILE_SIGNATURE_FIELDS = {"size", "mtime_ns", "ctime_ns", "inode", "device"}
_OPENCODE_UNIT_SIGNATURE_FIELDS = {
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
}
_AGY_CONVERSATION_UNIT_SIGNATURE_FIELDS = _OPENCODE_UNIT_SIGNATURE_FIELDS - {
    "time_created",
    "time_updated",
}


def _file_signature_valid(value: Any, *, strong: bool = False) -> bool:
    if not isinstance(value, dict):
        return False
    fields = set(value)
    if fields != _STRONG_FILE_SIGNATURE_FIELDS and (strong or fields != _LEGACY_FILE_SIGNATURE_FIELDS):
        return False
    return all(_nonnegative_exact_int(value.get(field)) for field in fields)


def _cursor_unit_key_valid(value: Any) -> bool:
    return bool(isinstance(value, str) and re.fullmatch(r"scan-v[1-9][0-9]*:[A-Za-z0-9_.-]+:.+", value) is not None)


def _cursor_unit_signature_valid(key: Any, value: Any, *, strong_file: bool = False) -> bool:
    if not _cursor_unit_key_valid(key) or not isinstance(value, dict):
        return False
    parts = key.split(":", 2)
    source = parts[1] if len(parts) == 3 and parts[0].startswith("scan-v") else ""
    if source == "opencode-db":
        fields = set(value)
        valid_fields = fields == _OPENCODE_UNIT_SIGNATURE_FIELDS or (
            not strong_file and fields == {"time_created", "time_updated"}
        )
        return bool(
            valid_fields
            and (
                fields == {"time_created", "time_updated"}
                or (
                    isinstance(value.get("content_sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", value["content_sha256"]) is not None
                    and all(_nonnegative_exact_int(value.get(field)) for field in fields - {"content_sha256"})
                )
            )
        )
    if source == "agy-cli-conversations":
        fields = set(value)
        valid_fields = fields == _AGY_CONVERSATION_UNIT_SIGNATURE_FIELDS or (
            not strong_file and fields == _STRONG_FILE_SIGNATURE_FIELDS
        )
        return bool(
            valid_fields
            and (
                fields == _STRONG_FILE_SIGNATURE_FIELDS
                or (
                    isinstance(value.get("content_sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", value["content_sha256"]) is not None
                    and all(_nonnegative_exact_int(value.get(field)) for field in fields - {"content_sha256"})
                )
            )
        )
    return _file_signature_valid(value, strong=strong_file)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [str(item) for item in value]


def _semantic_count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _int_or_zero(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}


def _safe_digest(value: Any) -> str | None:
    try:
        return digest(value)
    except (TypeError, ValueError):
        return None


def _semantic_source_families(value: Any) -> dict[str, dict[str, int]]:
    if not isinstance(value, dict):
        return {}
    stable_fields = ("discovered", "converged", "adapted", "excluded", "pending", "errors", "unsupported")
    return {
        str(source): {field: _int_or_zero(counts.get(field)) for field in stable_fields}
        for source, counts in sorted(value.items(), key=lambda pair: str(pair[0]))
        if isinstance(counts, dict)
    }


def _semantic_source_adapter_contract(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    adapter_ids = value.get("adapter_ids")
    exclusion_ids = value.get("exclusion_ids")
    adapter_sources = value.get("adapter_sources")
    exclusion_sources = value.get("exclusion_sources")

    def source_map(candidate: Any) -> dict[str, str]:
        if not isinstance(candidate, dict):
            return {}
        return {
            str(contract_id): str(source)
            for contract_id, source in sorted(candidate.items(), key=lambda pair: str(pair[0]))
            if isinstance(contract_id, str) and isinstance(source, str)
        }

    semantic = {
        "version": _int_or_zero(value.get("version")),
        "scanner_version": _int_or_zero(value.get("scanner_version")),
        "digest": str(value.get("digest") or ""),
        "adapter_ids": sorted(_string_list(adapter_ids)),
        "exclusion_ids": sorted(_string_list(exclusion_ids)),
        "adapter_sources": source_map(adapter_sources),
        "exclusion_sources": source_map(exclusion_sources),
    }
    if "alias_blocker_reasons" in value:
        semantic["alias_blocker_reasons"] = sorted(_string_list(value.get("alias_blocker_reasons")))
    return semantic


def _unit_receipts_digest(cursor: dict[str, Any], receipts_field: str, digest_field: str) -> str | None:
    receipts = cursor.get(receipts_field)
    if isinstance(receipts, dict):
        return _safe_digest(receipts)
    value = cursor.get(digest_field)
    return str(value) if value else None


def _unit_key_list_digest(cursor: dict[str, Any], units_field: str, digest_field: str) -> str | None:
    units = cursor.get(units_field)
    if isinstance(units, list):
        return _safe_digest(units)
    value = cursor.get(digest_field)
    return str(value) if value else None


def _load_source_contract_module() -> Any:
    path = Path(__file__).with_name("prompt_sources.py")
    spec = importlib.util.spec_from_file_location("_limen_prompt_sources_for_corpus", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load current prompt source adapter contract")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def current_source_adapter_contract() -> dict[str, Any]:
    return _load_source_contract_module().source_adapter_contract()


def cursor_semantic(cursor: dict[str, Any]) -> dict[str, Any]:
    semantic = {
        "version": cursor.get("version", 1),
        "scanner_version": _int_or_zero(cursor.get("scanner_version")),
        "scope": cursor.get("scope", "fixture"),
        "target_scope": cursor.get("target_scope", cursor.get("scope", "fixture")),
        "horizon_days": cursor.get("horizon_days"),
        "all_baseline_complete": cursor.get("all_baseline_complete") is True,
        "all_source_manifest_digest": (
            str(cursor.get("all_source_manifest_digest"))
            if cursor.get("all_source_manifest_digest") is not None
            else None
        ),
        "pending_files": _int_or_zero(cursor.get("pending_files")),
        "source_errors": _string_list(cursor.get("source_errors")),
        "source_manifest_digest": cursor.get("source_manifest_digest"),
        "source_discovery_spec_digest": _safe_digest(cursor.get("source_discovery_spec")),
        "source_container_signatures_digest": _safe_digest(cursor.get("source_container_signatures")),
        "source_families": _semantic_source_families(cursor.get("source_families")),
        "source_unit_count": _int_or_zero(cursor.get("source_unit_count")),
        "source_units_digest": _unit_key_list_digest(
            cursor,
            "source_units",
            "source_units_digest",
        ),
        "unsupported_source_count": _int_or_zero(cursor.get("unsupported_source_count")),
        "unsupported_units_digest": _unit_receipts_digest(
            cursor,
            "unsupported_units",
            "unsupported_units_digest",
        ),
        "unresolved_unit_count": _int_or_zero(cursor.get("unresolved_unit_count")),
        "unresolved_units_digest": _unit_key_list_digest(
            cursor,
            "unresolved_units",
            "unresolved_units_digest",
        ),
        "source_adapter_contract": _semantic_source_adapter_contract(cursor.get("source_adapter_contract")),
        "excluded_source_count": _int_or_zero(cursor.get("excluded_source_count")),
        "source_exclusion_counts": _semantic_count_map(cursor.get("source_exclusion_counts")),
        "excluded_unit_receipts_digest": _unit_receipts_digest(
            cursor,
            "excluded_unit_receipts",
            "excluded_unit_receipts_digest",
        ),
        "adapted_source_count": _int_or_zero(cursor.get("adapted_source_count")),
        "source_adapter_counts": _semantic_count_map(cursor.get("source_adapter_counts")),
        "adapted_unit_receipts_digest": _unit_receipts_digest(
            cursor,
            "adapted_unit_receipts",
            "adapted_unit_receipts_digest",
        ),
        "adapter_gaps": _string_list(cursor.get("adapter_gaps")),
        "adapter_gap_routes": [value for value in (cursor.get("adapter_gap_routes") or []) if isinstance(value, dict)]
        if isinstance(cursor.get("adapter_gap_routes"), (list, tuple))
        else [],
        "source_scan_receipt": {
            "schema": str(cursor.get("source_scan_receipt_schema") or ""),
            "ref": str(cursor.get("source_scan_receipt_ref") or ""),
            "sha256": str(cursor.get("source_scan_receipt_sha256") or ""),
            "scanner_code_digest": str(cursor.get("source_scan_code_digest") or ""),
            "scan_payload_digest": str(cursor.get("source_scan_payload_digest") or ""),
            "base_revision": _int_or_zero(cursor.get("source_scan_base_revision")),
            "base_cursor_digest": str(cursor.get("source_scan_base_cursor_digest") or ""),
        },
        "files": cursor.get("files") if isinstance(cursor.get("files"), dict) else {},
    }
    if "source_alias_blocker_counts" in cursor:
        semantic["source_alias_blocker_counts"] = _semantic_count_map(cursor.get("source_alias_blocker_counts"))
    return semantic


def cursor_digest(cursor: dict[str, Any]) -> str:
    return digest(cursor_semantic(cursor))


_SOURCE_SCAN_SCHEMA = "limen.prompt-source-scan.v1"
_SOURCE_SCAN_FIELDS = {
    "source_scan_attestation",
    "source_scan_receipt_schema",
    "source_scan_receipt_ref",
    "source_scan_receipt_sha256",
    "source_scan_code_digest",
    "source_scan_payload_digest",
    "source_scan_base_revision",
    "source_scan_base_cursor_digest",
}
_PENDING_SOURCE_SCANS: dict[str, dict[str, Any]] = {}
_PENDING_SOURCE_SCANS_LOCK = threading.Lock()


def _source_scan_payload(cursor: dict[str, Any]) -> dict[str, Any]:
    clean = {key: value for key, value in cursor.items() if key not in _SOURCE_SCAN_FIELDS}
    return {
        "base_revision": _int_or_zero(cursor.get("source_scan_base_revision", cursor.get("base_revision"))),
        "base_cursor_digest": str(cursor.get("source_scan_base_cursor_digest", cursor.get("base_cursor_digest")) or ""),
        "cursor": cursor_semantic(clean),
    }


def source_scan_payload_digest(cursor: dict[str, Any]) -> str:
    return digest(_source_scan_payload(cursor))


def current_source_scanner_code_digest() -> str:
    root = Path(__file__).resolve().parents[3]
    files = (
        root / "scripts" / "prompt-atom-ledger.py",
        root / "cli" / "src" / "limen" / "prompt_corpus.py",
        root / "cli" / "src" / "limen" / "prompt_sources.py",
    )
    return digest({str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files})


def attest_source_scan(cursor: dict[str, Any], *, scanner_code_digest: str) -> str:
    """Bind an exact scanner result to this process until the writer seals it."""

    if re.fullmatch(r"[0-9a-f]{64}", scanner_code_digest) is None:
        raise ValueError("source scanner code digest must be lowercase sha256")
    if scanner_code_digest != current_source_scanner_code_digest():
        raise ValueError("source scanner code digest does not match the running implementation")
    cursor["source_scan_code_digest"] = scanner_code_digest
    cursor["source_scan_base_revision"] = _int_or_zero(cursor.get("base_revision"))
    cursor["source_scan_base_cursor_digest"] = str(cursor.get("base_cursor_digest") or "")
    cursor["source_scan_payload_digest"] = source_scan_payload_digest(cursor)
    token = secrets.token_hex(32)
    cursor["source_scan_attestation"] = token
    with _PENDING_SOURCE_SCANS_LOCK:
        if len(_PENDING_SOURCE_SCANS) >= 1024:
            _PENDING_SOURCE_SCANS.clear()
        _PENDING_SOURCE_SCANS[token] = {
            "payload_digest": cursor["source_scan_payload_digest"],
            "scanner_code_digest": scanner_code_digest,
        }
    return token


def _pending_source_scan_valid(cursor: dict[str, Any], *, consume: bool = False) -> bool:
    token = cursor.get("source_scan_attestation")
    if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{64}", token) is None:
        return False
    with _PENDING_SOURCE_SCANS_LOCK:
        pending = _PENDING_SOURCE_SCANS.pop(token, None) if consume else _PENDING_SOURCE_SCANS.get(token)
    return bool(
        isinstance(pending, dict)
        and pending.get("payload_digest") == cursor.get("source_scan_payload_digest")
        and pending.get("scanner_code_digest") == cursor.get("source_scan_code_digest")
        and cursor.get("source_scan_payload_digest") == source_scan_payload_digest(cursor)
    )


def _source_scan_receipt_payload(cursor: dict[str, Any]) -> dict[str, Any]:
    contract = _semantic_source_adapter_contract(cursor.get("source_adapter_contract"))
    return {
        "schema": _SOURCE_SCAN_SCHEMA,
        "scanner_code_digest": str(cursor.get("source_scan_code_digest") or ""),
        "source_adapter_contract_digest": str(contract.get("digest") or ""),
        "scan_payload_digest": str(cursor.get("source_scan_payload_digest") or ""),
        "base_revision": _int_or_zero(cursor.get("source_scan_base_revision")),
        "base_cursor_digest": str(cursor.get("source_scan_base_cursor_digest") or ""),
        "scope": str(cursor.get("scope") or ""),
        "target_scope": str(cursor.get("target_scope") or ""),
        "all_baseline_complete": cursor.get("all_baseline_complete") is True,
        "source_unit_count": _int_or_zero(cursor.get("source_unit_count")),
        "source_units_digest": str(cursor.get("source_units_digest") or ""),
        "files_digest": digest(cursor.get("files") if isinstance(cursor.get("files"), dict) else {}),
        "excluded_unit_receipts_digest": str(cursor.get("excluded_unit_receipts_digest") or ""),
        "adapted_unit_receipts_digest": str(cursor.get("adapted_unit_receipts_digest") or ""),
        "unsupported_units_digest": str(cursor.get("unsupported_units_digest") or ""),
        "unresolved_units_digest": str(cursor.get("unresolved_units_digest") or ""),
    }


def _source_scan_receipt_errors(cursor: dict[str, Any], receipt_root: Path | None) -> list[str]:
    if str(cursor.get("scope") or "") != "all" or str(cursor.get("target_scope") or "") != "all":
        return []
    if _pending_source_scan_valid(cursor):
        return []
    errors: list[str] = []
    receipt_ref = cursor.get("source_scan_receipt_ref")
    receipt_sha = cursor.get("source_scan_receipt_sha256")
    if cursor.get("source_scan_receipt_schema") != _SOURCE_SCAN_SCHEMA:
        errors.append("exact all/all scope requires a typed source scan receipt")
    if (
        not isinstance(receipt_ref, str)
        or re.fullmatch(r"source-scan-receipts/[0-9a-f]{64}\.json", receipt_ref) is None
    ):
        errors.append("source scan receipt reference is missing or malformed")
    if not isinstance(receipt_sha, str) or re.fullmatch(r"[0-9a-f]{64}", receipt_sha) is None:
        errors.append("source scan receipt hash is missing or malformed")
    for field in ("source_scan_code_digest", "source_scan_payload_digest", "source_scan_base_cursor_digest"):
        value = cursor.get(field)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            errors.append(f"{field} is missing or malformed")
    if cursor.get("source_scan_code_digest") != current_source_scanner_code_digest():
        errors.append("source scan receipt code identity is stale")
    if cursor.get("source_scan_payload_digest") != source_scan_payload_digest(cursor):
        errors.append("source scan payload digest is stale")
    if errors or receipt_root is None:
        return errors
    root = receipt_root.resolve()
    artifact = (root / str(receipt_ref)).resolve()
    if root not in artifact.parents or not artifact.is_file():
        return ["source scan receipt artifact is missing"]
    try:
        payload = artifact.read_bytes()
        mode = artifact.stat().st_mode & 0o777
    except OSError:
        return ["source scan receipt artifact is unreadable"]
    if mode != 0o400:
        errors.append("source scan receipt artifact is not immutable")
    if hashlib.sha256(payload).hexdigest() != receipt_sha:
        errors.append("source scan receipt artifact hash is stale")
    try:
        receipt = json.loads(payload.decode("utf-8", errors="strict"))
    except (UnicodeError, ValueError):
        receipt = None
    if receipt != _source_scan_receipt_payload(cursor):
        errors.append("source scan receipt artifact does not match cursor custody")
    return errors


def _seal_attested_source_scan(cursor: dict[str, Any]) -> tuple[dict[str, Any], str, bytes]:
    if not _pending_source_scan_valid(cursor, consume=True):
        raise ValueError("exact all/all cursor lacks a live scanner attestation")
    sealed = dict(cursor)
    sealed.pop("source_scan_attestation", None)
    sealed["source_scan_receipt_schema"] = _SOURCE_SCAN_SCHEMA
    receipt = _source_scan_receipt_payload(sealed)
    receipt_bytes = (canonical_json(receipt) + "\n").encode("utf-8")
    receipt_sha = hashlib.sha256(receipt_bytes).hexdigest()
    receipt_ref = f"source-scan-receipts/{receipt_sha}.json"
    sealed["source_scan_receipt_ref"] = receipt_ref
    sealed["source_scan_receipt_sha256"] = receipt_sha
    return sealed, receipt_ref, receipt_bytes


def _validate_source_scan_receipt_destination(paths: LedgerPaths, receipt_path: Path) -> None:
    root = paths.private_dir.resolve()
    parent = receipt_path.parent
    if os.path.lexists(parent):
        if parent.is_symlink() or not parent.is_dir() or parent.resolve().parent != root:
            raise ValueError("source scan receipt directory escapes private custody")
    elif parent.parent.resolve() != root:
        raise ValueError("source scan receipt directory escapes private custody")
    if os.path.lexists(receipt_path) and receipt_path.is_symlink():
        raise ValueError("source scan receipt path is a symlink")


def _clear_source_scan_authority(cursor: dict[str, Any]) -> dict[str, Any]:
    cleared = dict(cursor)
    token = cleared.get("source_scan_attestation")
    if isinstance(token, str):
        with _PENDING_SOURCE_SCANS_LOCK:
            _PENDING_SOURCE_SCANS.pop(token, None)
    for field in _SOURCE_SCAN_FIELDS:
        cleared.pop(field, None)
    return cleared


def source_scan_state_digest(cursor: dict[str, Any]) -> str:
    clean = {key: value for key, value in cursor.items() if key not in _SOURCE_SCAN_FIELDS}
    return digest(cursor_semantic(clean))


def _source_discovery_spec_valid(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {
        "version",
        "regular",
        "gemini_root",
        "opencode_db",
        "agy_conversations_root",
    }:
        return False
    if value.get("version") != 1 or not isinstance(value.get("regular"), list):
        return False
    for item in value["regular"]:
        if not isinstance(item, dict) or set(item) != {"source", "root", "patterns"}:
            return False
        if not isinstance(item.get("source"), str) or not item["source"]:
            return False
        if not isinstance(item.get("root"), str) or not Path(item["root"]).is_absolute():
            return False
        patterns = item.get("patterns")
        if (
            not isinstance(patterns, list)
            or not patterns
            or any(
                not isinstance(pattern, str)
                or not pattern
                or Path(pattern).is_absolute()
                or ".." in Path(pattern).parts
                for pattern in patterns
            )
        ):
            return False
    gemini_root = value.get("gemini_root")
    if gemini_root is not None and (not isinstance(gemini_root, str) or not Path(gemini_root).is_absolute()):
        return False
    return all(
        isinstance(value.get(field), str) and Path(value[field]).is_absolute()
        for field in ("opencode_db", "agy_conversations_root")
    )


def _source_container_signatures_valid(value: Any) -> bool:
    if not isinstance(value, dict) or set(value) != {"opencode-db"}:
        return False
    signature = value.get("opencode-db")
    if signature is None:
        return True
    expected_fields = {f"{prefix}_{field}" for prefix in ("db", "wal") for field in _STRONG_FILE_SIGNATURE_FIELDS}
    return bool(
        isinstance(signature, dict)
        and set(signature) == expected_fields
        and all(_nonnegative_exact_int(item) for item in signature.values())
    )


def _strong_source_path_signature(path: Path) -> dict[str, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return {
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "ctime_ns": stat.st_ctime_ns,
        "inode": stat.st_ino,
        "device": stat.st_dev,
    }


def _sqlite_storage_signature(path: Path) -> dict[str, int] | None:
    database = _strong_source_path_signature(path)
    if database is None:
        return None
    wal_path = Path(f"{path}-wal")
    if wal_path.is_symlink():
        return None
    wal = _strong_source_path_signature(wal_path) if wal_path.exists() else None
    if wal is None:
        wal = {field: 0 for field in _STRONG_FILE_SIGNATURE_FIELDS}
    return {
        **{f"db_{field}": int(database[field]) for field in _STRONG_FILE_SIGNATURE_FIELDS},
        **{f"wal_{field}": int(wal[field]) for field in _STRONG_FILE_SIGNATURE_FIELDS},
    }


def validate_live_source_custody(cursor: dict[str, Any]) -> list[str]:
    """Re-discover exact-all paths and re-stat their typed custody without reading prompt bodies."""

    if cursor.get("scope") != "all" or cursor.get("target_scope") != "all":
        return []
    spec = cursor.get("source_discovery_spec")
    if not _source_discovery_spec_valid(spec):
        return ["exact all/all source discovery specification is missing or malformed"]
    assert isinstance(spec, dict)
    container_signatures = cursor.get("source_container_signatures")
    if not _source_container_signatures_valid(container_signatures):
        return ["exact all/all source container signatures are missing or malformed"]
    assert isinstance(container_signatures, dict)
    source_units = set(cursor.get("source_units") or [])
    scanner_version = _int_or_zero(cursor.get("scanner_version"))
    ceiling = _int_or_zero((cursor.get("resource_limits") or {}).get("max_discovery_units"))
    ceiling = ceiling if ceiling > 0 else 100_000
    discovered: set[str] = set()
    seen_paths: set[str] = set()
    discovery_count = 0
    errors: list[str] = []
    source_contract_module = _load_source_contract_module()
    roots_by_source: dict[str, Path] = {}
    custody_by_locator: dict[str, Any] = {}

    def consider(source: str, path: Path, root: Path) -> bool:
        nonlocal discovery_count
        try:
            custody = source_contract_module.inspect_source_path_custody(source, path, root)
            if custody.error is not None:
                raise ValueError(custody.error)
            if custody.alias_contract_id is None and not path.is_file():
                return True
            discovery_count += 1
            if discovery_count > ceiling:
                errors.append("live source discovery exceeds the sealed resource ceiling")
                return False
        except (OSError, ValueError):
            errors.append(f"{source}: live source containment changed after the sealed scan")
            return True
        path_key = str(path)
        custody_by_locator[path_key] = custody
        if path_key not in seen_paths:
            seen_paths.add(path_key)
            discovered.add(f"scan-v{scanner_version}:{source}:{path}")
        return True

    for item in spec["regular"]:
        source = item["source"]
        root = Path(item["root"])
        roots_by_source[source] = root
        if not root.exists():
            continue
        candidates = (
            (root,) if root.is_file() else (path for pattern in item["patterns"] for path in root.rglob(pattern))
        )
        for path in candidates:
            if not consider(source, path, root):
                break
        if errors and errors[-1] == "live source discovery exceeds the sealed resource ceiling":
            break
    gemini_root = spec.get("gemini_root")
    if gemini_root and discovery_count <= ceiling:
        root = Path(gemini_root)
        roots_by_source["gemini-tmp"] = root
        if root.exists():
            for path in root.rglob("chats/*.jsonl"):
                if not consider("gemini-tmp", path, root):
                    break
    agy_root = Path(spec["agy_conversations_root"])
    if agy_root.exists() and discovery_count <= ceiling:
        roots_by_source["agy-cli-conversations"] = agy_root
        for path in agy_root.rglob("*.db"):
            if not consider("agy-cli-conversations", path, agy_root):
                break

    current_opencode_container = _sqlite_storage_signature(Path(spec["opencode_db"]))
    if current_opencode_container != container_signatures.get("opencode-db"):
        errors.append("opencode-db: live container generation changed after the sealed scan")

    expected_discovered = {key for key in source_units if isinstance(key, str) and ":opencode-db:" not in key}
    if discovered != expected_discovered:
        errors.append("live source unit manifest changed after the sealed scan")

    raw_files = cursor.get("files")
    raw_excluded = cursor.get("excluded_unit_receipts")
    raw_adapted = cursor.get("adapted_unit_receipts")
    files: dict[str, Any] = raw_files if isinstance(raw_files, dict) else {}
    excluded: dict[str, Any] = raw_excluded if isinstance(raw_excluded, dict) else {}
    adapted: dict[str, Any] = raw_adapted if isinstance(raw_adapted, dict) else {}
    for key in sorted(value for value in source_units if isinstance(value, str)):
        if not _cursor_unit_key_valid(key):
            continue
        _, source, locator = key.split(":", 2)
        receipt = excluded.get(key) or adapted.get(key)
        expected = files.get(key) or (receipt.get("signature") if isinstance(receipt, dict) else None)
        if not isinstance(expected, dict):
            errors.append(f"{source}: sealed unit lacks typed live custody")
            continue
        if source == "opencode-db":
            database_path = Path(locator.rsplit("#session:", 1)[0])
            storage = _sqlite_storage_signature(database_path)
            if storage is None or any(expected.get(field) != value for field, value in storage.items()):
                errors.append("opencode-db: live database generation changed after the sealed scan")
        elif source == "agy-cli-conversations":
            storage = _sqlite_storage_signature(Path(locator))
            if storage is None or any(expected.get(field) != value for field, value in storage.items()):
                errors.append("agy-cli-conversations: live database generation changed after the sealed scan")
        else:
            custody = custody_by_locator.get(locator)
            if custody is None and source in roots_by_source:
                custody = source_contract_module.inspect_source_path_custody(
                    source,
                    Path(locator),
                    roots_by_source[source],
                )
            current_signature = (
                custody.unit_signature
                if custody is not None and custody.error is None
                else _strong_source_path_signature(Path(locator))
            )
            if current_signature != expected:
                errors.append(f"{source}: live source signature changed after the sealed scan")
        if isinstance(receipt, dict) and receipt.get("contract_id") == "claude-project-memory-mirror-v1":
            sibling = Path(locator).parent / "memory" / Path(locator).name
            related = receipt.get("related_signatures") or {}
            if _strong_source_path_signature(sibling) != related.get("memory_sibling"):
                errors.append("claude-projects: live memory mirror sibling changed after the sealed scan")
        if isinstance(receipt, dict) and receipt.get("contract_id") == getattr(
            source_contract_module, "CLAUDE_PROJECT_MEMORY_ALIAS_ID", ""
        ):
            custody = custody_by_locator.get(locator)
            related = receipt.get("related_signatures") or {}
            evidence = receipt.get("related_evidence") or {}
            if (
                custody is None
                or custody.error is not None
                or custody.alias_contract_id != receipt.get("contract_id")
                or custody.related_signatures != related
                or custody.related_evidence != evidence
            ):
                errors.append("claude-projects: live project-memory alias changed after the sealed scan")
            else:
                target_key = f"scan-v{scanner_version}:{source}:{custody.alias_target}"
                target_receipt = excluded.get(target_key)
                if (
                    target_key not in source_units
                    or not isinstance(target_receipt, dict)
                    or target_receipt.get("contract_id") != "claude-project-memory-v1"
                    or target_receipt.get("signature") != related.get("memory_target")
                ):
                    errors.append("claude-projects: project-memory alias target lacks independent custody")
        if isinstance(receipt, dict) and receipt.get("contract_id") == "codex-pasted-text-attachment-v1":
            related = receipt.get("related_signatures") or {}
            evidence = receipt.get("related_evidence") or {}
            parent = evidence.get("parent_event") if isinstance(evidence, dict) else None
            parent_locator = parent.get("parent_locator") if isinstance(parent, dict) else None
            if not isinstance(parent_locator, str) or _strong_source_path_signature(
                Path(parent_locator)
            ) != related.get("parent_session"):
                errors.append("codex-attachments: live parent session changed after the sealed scan")
    return list(dict.fromkeys(errors))


def validate_source_adapter_cursor(
    cursor: dict[str, Any],
    *,
    receipt_root: Path | None = None,
) -> list[str]:
    """Validate private exclusion receipts and the current adapter contract."""

    target_scope = str(cursor.get("target_scope") or cursor.get("scope") or "")
    scope = str(cursor.get("scope") or "")
    raw_excluded = cursor.get("excluded_unit_receipts")
    raw_adapted = cursor.get("adapted_unit_receipts")
    raw_unsupported = cursor.get("unsupported_units")
    raw_unresolved = cursor.get("unresolved_units")
    raw_source_units = cursor.get("source_units")
    excluded = raw_excluded if isinstance(raw_excluded, dict) else {}
    adapted = raw_adapted if isinstance(raw_adapted, dict) else {}
    unsupported = raw_unsupported if isinstance(raw_unsupported, dict) else {}
    unresolved = raw_unresolved if isinstance(raw_unresolved, list) else []
    source_units = raw_source_units if isinstance(raw_source_units, list) else []
    needs_contract = bool(
        target_scope in {"all", "partial:all"}
        or cursor.get("scanner_version") is not None
        or cursor.get("source_adapter_contract") is not None
        or raw_excluded is not None
        or raw_adapted is not None
        or raw_unsupported is not None
        or raw_unresolved is not None
        or raw_source_units is not None
    )
    if not needs_contract:
        return []

    errors: list[str] = []
    errors.extend(_source_scan_receipt_errors(cursor, receipt_root))
    source_contract_module = _load_source_contract_module()
    expected = source_contract_module.source_adapter_contract()
    if cursor.get("scanner_version") != expected["scanner_version"]:
        errors.append("source scanner version is missing or stale")
    baseline_complete = cursor.get("all_baseline_complete")
    all_manifest_digest = cursor.get("all_source_manifest_digest")
    if not isinstance(baseline_complete, bool):
        errors.append("all_baseline_complete must be boolean")
    if baseline_complete is True:
        if scope != "all" or target_scope != "all":
            errors.append("all_baseline_complete requires exact all/all scope")
        if not isinstance(all_manifest_digest, str) or re.fullmatch(r"[0-9a-f]{64}", all_manifest_digest) is None:
            errors.append("all_source_manifest_digest is missing or malformed")
    elif scope == "all" and target_scope == "all":
        errors.append("exact all/all scope requires a complete all-history baseline")
    if (
        scope == "all"
        and target_scope == "all"
        and not _source_discovery_spec_valid(cursor.get("source_discovery_spec"))
    ):
        errors.append("exact all/all source discovery specification is missing or malformed")
    if (
        scope == "all"
        and target_scope == "all"
        and not _source_container_signatures_valid(cursor.get("source_container_signatures"))
    ):
        errors.append("exact all/all source container signatures are missing or malformed")
    contract = _semantic_source_adapter_contract(cursor.get("source_adapter_contract"))
    if contract != expected:
        errors.append("source adapter contract is missing or stale")
    if not isinstance(raw_excluded, dict):
        errors.append("excluded unit receipts must be an object")
    if not isinstance(raw_adapted, dict):
        errors.append("adapted unit receipts must be an object")
    if not isinstance(raw_unsupported, dict):
        errors.append("unsupported unit cache must be an object")
    if not isinstance(raw_unresolved, list):
        errors.append("unresolved unit obligations must be a list")
    if not isinstance(raw_source_units, list):
        errors.append("source unit manifest must be a list")
    if cursor.get("excluded_unit_receipts_digest") != _safe_digest(excluded):
        errors.append("excluded unit receipt digest is missing or stale")
    if cursor.get("adapted_unit_receipts_digest") != _safe_digest(adapted):
        errors.append("adapted unit receipt digest is missing or stale")
    if cursor.get("unsupported_units_digest") != _safe_digest(unsupported):
        errors.append("unsupported unit cache digest is missing or stale")
    if cursor.get("unresolved_units_digest") != _safe_digest(unresolved):
        errors.append("unresolved unit obligation digest is missing or stale")
    if cursor.get("source_units_digest") != _safe_digest(source_units):
        errors.append("source unit manifest digest is missing or stale")

    def count_field(name: str, expected_count: int) -> int:
        value = cursor.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{name} must be a non-negative integer")
            return 0
        if value != expected_count:
            errors.append(f"{name} does not match unit receipts")
        return value

    count_field("excluded_source_count", len(excluded))
    count_field("adapted_source_count", len(adapted))
    unsupported_count = count_field("unsupported_source_count", len(unsupported))
    unresolved_count = count_field("unresolved_unit_count", len(unresolved))
    source_unit_count = count_field("source_unit_count", len(source_units))

    def count_map(name: str, expected_counts: dict[str, int]) -> None:
        value = cursor.get(name)
        if not isinstance(value, dict):
            errors.append(f"{name} must be an object")
            return
        if any(not isinstance(key, str) for key in value):
            errors.append(f"{name} keys must be strings")
            return
        if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in value.values()):
            errors.append(f"{name} values must be non-negative integers")
            return
        if value != expected_counts:
            errors.append(f"{name} does not match unit receipts")

    def receipt_counts(receipts: dict[str, Any]) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for receipt in receipts.values():
            if isinstance(receipt, dict) and isinstance(receipt.get("contract_id"), str):
                counts[receipt["contract_id"]] += 1
        return dict(sorted(counts.items()))

    count_map("source_exclusion_counts", receipt_counts(excluded))
    count_map("source_adapter_counts", receipt_counts(adapted))
    raw_alias_blockers = cursor.get("source_alias_blocker_counts", {})
    alias_blockers = _semantic_count_map(raw_alias_blockers)
    valid_alias_reasons = set(getattr(source_contract_module, "SOURCE_ALIAS_BLOCKER_REASONS", ()))
    if not isinstance(raw_alias_blockers, dict):
        errors.append("source_alias_blocker_counts must be an object")
    elif alias_blockers != raw_alias_blockers or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0 for value in raw_alias_blockers.values()
    ):
        errors.append("source_alias_blocker_counts must contain non-negative integer counts")
    elif set(alias_blockers) - valid_alias_reasons:
        errors.append("source_alias_blocker_counts contains an unknown reason")

    def signature_valid(value: Any) -> bool:
        return _file_signature_valid(value, strong=True)

    def validate_group(
        receipts: dict[str, Any],
        *,
        disposition: str,
        valid_ids: set[str],
    ) -> None:
        for key, receipt in receipts.items():
            if not _cursor_unit_key_valid(key) or not isinstance(receipt, dict):
                errors.append(f"{disposition} unit receipt is malformed")
                continue
            _, source, locator = key.split(":", 2)
            related = receipt.get("related_signatures", {})
            related_ok = isinstance(related, dict) and all(
                isinstance(label, str) and signature_valid(signature) for label, signature in related.items()
            )
            related_evidence = receipt.get("related_evidence", {})
            contract_id = receipt.get("contract_id")
            if (
                receipt.get("version") != expected["version"]
                or receipt.get("disposition") != disposition
                or not isinstance(contract_id, str)
                or contract_id not in valid_ids
                or receipt.get("contract_digest") != expected["digest"]
                or not signature_valid(receipt.get("signature"))
                or not related_ok
                or not isinstance(related_evidence, dict)
                or not source_contract_module.source_contract_receipt_applies(
                    contract_id,
                    source,
                    locator,
                    signature=receipt.get("signature"),
                    related_signatures=related if isinstance(related, dict) else None,
                    related_evidence=related_evidence if isinstance(related_evidence, dict) else None,
                )
            ):
                errors.append(f"{key}: {disposition} unit receipt is malformed or stale")

    validate_group(excluded, disposition="excluded", valid_ids=set(expected["exclusion_ids"]))
    validate_group(adapted, disposition="adapted", valid_ids=set(expected["adapter_ids"]))
    alias_contract_id = getattr(source_contract_module, "CLAUDE_PROJECT_MEMORY_ALIAS_ID", "")
    scanner_version = _int_or_zero(cursor.get("scanner_version"))
    source_unit_set = set(source_units)
    for key, receipt in excluded.items():
        if not isinstance(receipt, dict) or receipt.get("contract_id") != alias_contract_id:
            continue
        parts = key.split(":", 2)
        if len(parts) != 3:
            continue
        source, locator = parts[1], parts[2]
        target = Path(locator).parent / "memory" / Path(locator).name
        target_key = f"scan-v{scanner_version}:{source}:{target}"
        target_receipt = excluded.get(target_key)
        related = receipt.get("related_signatures") or {}
        target_is_pending = target_key in set(unresolved)
        if target_key not in source_unit_set or (
            not target_is_pending
            and (
                not isinstance(target_receipt, dict)
                or target_receipt.get("contract_id") != "claude-project-memory-v1"
                or target_receipt.get("signature") != related.get("memory_target")
            )
        ):
            errors.append(f"{key}: project-memory alias target lacks independent custody")

    files = cursor.get("files")
    if not isinstance(files, dict):
        errors.append("parsed file cache must be an object")
    files = files if isinstance(files, dict) else {}
    if any(not _cursor_unit_signature_valid(key, signature, strong_file=True) for key, signature in files.items()):
        errors.append("parsed file cache contains a malformed unit signature")
    if any(
        not _cursor_unit_signature_valid(key, signature, strong_file=True) for key, signature in unsupported.items()
    ):
        errors.append("unsupported unit cache contains a malformed unit signature")
    if (
        any(not _cursor_unit_key_valid(key) for key in unresolved)
        or len(set(unresolved)) != len(unresolved)
        or unresolved != sorted(unresolved)
    ):
        errors.append("unresolved unit obligations are malformed")
    if (
        any(not _cursor_unit_key_valid(key) for key in source_units)
        or len(set(source_units)) != len(source_units)
        or source_units != sorted(source_units)
    ):
        errors.append("source unit manifest is malformed")
    if set(unsupported) - set(unresolved):
        errors.append("unsupported units are missing from unresolved obligations")
    raw_families = cursor.get("source_families")
    family_fields = ("discovered", "converged", "adapted", "excluded", "pending", "errors", "unsupported")
    family_totals = {field: 0 for field in family_fields}
    if isinstance(raw_families, dict):
        family_counts_valid = True
        for source, counts in raw_families.items():
            if not isinstance(source, str) or not isinstance(counts, dict):
                family_counts_valid = False
                break
            for field in family_fields:
                value = counts.get(field, 0)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    family_counts_valid = False
                    break
                family_totals[field] += value
            if not family_counts_valid:
                break
    else:
        family_counts_valid = False
    claude_family = raw_families.get("claude-projects") if isinstance(raw_families, dict) else None
    claude_errors = int(claude_family.get("errors") or 0) if isinstance(claude_family, dict) else 0
    if not family_counts_valid:
        errors.append("source family unresolved counts are malformed")
    elif family_totals["unsupported"] != unsupported_count:
        errors.append("source family unsupported counts do not match unsupported_source_count")
    if family_counts_valid and sum(alias_blockers.values()) > claude_errors:
        errors.append("source alias blocker counts exceed claude-projects errors")
    pending_files = cursor.get("pending_files", 0)
    if isinstance(pending_files, bool) or not isinstance(pending_files, int) or pending_files < 0:
        errors.append("pending_files must be a non-negative integer")
        pending_files = 0
    source_errors = cursor.get("source_errors", [])
    if not isinstance(source_errors, list) or any(not isinstance(value, str) for value in source_errors):
        errors.append("source_errors must be a list of strings")
        source_errors = []
    if family_counts_valid and family_totals["pending"] != pending_files:
        errors.append("source family pending counts do not match pending_files")
    if family_counts_valid and family_totals["errors"] != len(source_errors):
        errors.append("source family error counts do not match source_errors")
    if family_counts_valid and family_totals["discovered"] != source_unit_count:
        errors.append("source family discovered counts do not match source_unit_count")
    if family_counts_valid and family_totals["excluded"] != int(cursor.get("excluded_source_count") or 0):
        errors.append("source family excluded counts do not match excluded_source_count")
    if family_counts_valid and family_totals["adapted"] != int(cursor.get("adapted_source_count") or 0):
        errors.append("source family adapted counts do not match adapted_source_count")
    overlap = set(excluded) & set(files)
    if overlap:
        errors.append("excluded units remain in the parsed file cache")
    for key, receipt in adapted.items():
        if isinstance(receipt, dict) and files.get(key) != receipt.get("signature"):
            errors.append(f"{key}: adapted unit receipt does not match the parsed file cache")
    if set(excluded) & set(adapted):
        errors.append("source units cannot be both adapted and excluded")
    if scope == "all" and target_scope == "all":
        if pending_files:
            errors.append("exact all/all scope cannot have pending source files")
        if source_errors:
            errors.append("exact all/all scope cannot have source errors")
        if unsupported_count or unsupported or family_totals["unsupported"]:
            errors.append("exact all/all scope cannot have unsupported source units")
        if unresolved_count or unresolved:
            errors.append("exact all/all scope cannot have unresolved source obligations")
        if cursor.get("adapter_gaps") or cursor.get("adapter_gap_routes"):
            errors.append("exact all/all scope cannot have adapter gaps or routes")
        if cursor.get("all_source_manifest_digest") != cursor.get("source_manifest_digest"):
            errors.append("exact all/all scope requires matching source and all-history manifest digests")
        if set(source_units) != set(files) | set(excluded):
            errors.append("exact all/all source units do not match parsed and excluded unit custody")
        if family_counts_valid:

            def grouped_source(key: Any) -> str:
                parts = key.split(":", 2) if isinstance(key, str) else []
                return parts[1] if len(parts) == 3 else "__malformed__"

            grouped = {
                "discovered": Counter(grouped_source(key) for key in source_units),
                "converged": Counter(grouped_source(key) for key in files),
                "adapted": Counter(grouped_source(key) for key in adapted),
                "excluded": Counter(grouped_source(key) for key in excluded),
                "unsupported": Counter(grouped_source(key) for key in unsupported),
            }
            typed_families = raw_families if isinstance(raw_families, dict) else {}
            sources = set(typed_families) | {source for counts in grouped.values() for source in counts}
            for source in sorted(sources):
                counts = typed_families.get(source, {})
                if counts.get("discovered", 0) != counts.get("converged", 0) + counts.get("excluded", 0):
                    errors.append(f"{source}: exact all source family coverage is incomplete")
                if counts.get("adapted", 0) > counts.get("converged", 0):
                    errors.append(f"{source}: adapted source count exceeds converged coverage")
                for field, grouped_counts in grouped.items():
                    if counts.get(field, 0) != grouped_counts.get(source, 0):
                        errors.append(f"{source}: source family {field} count does not match unit custody")
    return errors


def _target_scope(cursor: dict[str, Any]) -> str:
    value = str(cursor.get("target_scope") or cursor.get("scope") or "fixture")
    return value.removeprefix("partial:")


def validate_cursor_shape(cursor: Any, *, role: str) -> list[str]:
    """Validate fields consumed before semantic ledger validation."""

    if not isinstance(cursor, dict):
        return [f"{role} cursor must be an object"]
    errors: list[str] = []
    for field in (
        "version",
        "scanner_version",
        "revision",
        "base_revision",
        "pending_files",
        "source_unit_count",
        "unsupported_source_count",
        "unresolved_unit_count",
        "excluded_source_count",
        "adapted_source_count",
        "work_units_used",
    ):
        if field not in cursor:
            continue
        value = cursor.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"{role} cursor {field} must be a non-negative integer")
    for field in ("horizon_days", "effective_horizon_days"):
        value = cursor.get(field)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            errors.append(f"{role} cursor {field} must be null or a non-negative integer")
    for field in (
        "files",
        "unsupported_units",
        "excluded_unit_receipts",
        "adapted_unit_receipts",
        "source_exclusion_counts",
        "source_adapter_counts",
        "source_alias_blocker_counts",
        "source_families",
        "source_coverage",
        "source_adapter_contract",
    ):
        if field in cursor and not isinstance(cursor.get(field), dict):
            errors.append(f"{role} cursor {field} must be an object")
    for field in ("files", "unsupported_units"):
        value = cursor.get(field)
        if isinstance(value, dict) and any(
            not _cursor_unit_signature_valid(key, signature) for key, signature in value.items()
        ):
            errors.append(f"{role} cursor {field} contains a malformed unit signature")
    for field in (
        "source_errors",
        "excluded_file_keys",
        "adapter_gaps",
        "adapter_gap_routes",
        "source_units",
        "unresolved_units",
    ):
        if field in cursor and not isinstance(cursor.get(field), list):
            errors.append(f"{role} cursor {field} must be a list")
    if isinstance(cursor.get("source_errors"), list) and any(
        not isinstance(value, str) for value in cursor["source_errors"]
    ):
        errors.append(f"{role} cursor source_errors values must be strings")
    if isinstance(cursor.get("excluded_file_keys"), list) and any(
        not isinstance(value, str) for value in cursor["excluded_file_keys"]
    ):
        errors.append(f"{role} cursor excluded_file_keys values must be strings")
    if isinstance(cursor.get("unresolved_units"), list) and any(
        not _cursor_unit_key_valid(value) for value in cursor["unresolved_units"]
    ):
        errors.append(f"{role} cursor unresolved_units contains a malformed unit key")
    if isinstance(cursor.get("source_units"), list) and any(
        not _cursor_unit_key_valid(value) for value in cursor["source_units"]
    ):
        errors.append(f"{role} cursor source_units contains a malformed unit key")
    for field in ("all_baseline_complete", "replace_files", "work_units_unbounded"):
        if field in cursor and not isinstance(cursor.get(field), bool):
            errors.append(f"{role} cursor {field} must be boolean")
    for field in (
        "base_cursor_digest",
        "source_manifest_digest",
        "all_source_manifest_digest",
        "unsupported_units_digest",
        "unresolved_units_digest",
        "source_units_digest",
    ):
        if field in cursor and cursor.get(field) is not None and not isinstance(cursor.get(field), str):
            errors.append(f"{role} cursor {field} must be text or null")
    return errors


def merge_cursor(current: dict[str, Any], proposed: dict[str, Any] | None) -> dict[str, Any]:
    """Monotonically merge a scan result produced before the writer lock was acquired."""

    current_errors = validate_cursor_shape(current, role="current")
    if current_errors:
        raise ValueError("invalid current cursor: " + "; ".join(current_errors))
    if proposed is None:
        return dict(current)
    proposed_errors = validate_cursor_shape(proposed, role="proposed")
    if proposed_errors:
        raise ValueError("invalid proposed cursor: " + "; ".join(proposed_errors))
    current_revision = int(current.get("revision") or 0)
    has_base_revision = "base_revision" in proposed
    has_base_digest = "base_cursor_digest" in proposed
    if has_base_revision != has_base_digest or (current and not (has_base_revision and has_base_digest)):
        raise ValueError("invalid proposed cursor: non-initial proposals require exact CAS revision and digest")
    if has_base_revision and has_base_digest:
        proposed_base_revision = int(proposed["base_revision"])
        proposed_base_digest = str(proposed["base_cursor_digest"])
        stale = bool(proposed_base_revision != current_revision or proposed_base_digest != cursor_digest(current))
    else:
        proposed_base_revision = 0
        stale = False
    if stale:
        raise ValueError("stale cursor proposal requires a fresh scan")
    current_unresolved = set(current.get("unresolved_units") or [])
    proposed_unresolved = set(proposed.get("unresolved_units") or [])
    cleared_unresolved = current_unresolved - proposed_unresolved
    proposed_source_units = set(proposed.get("source_units") or [])
    proposed_resolved = proposed_source_units & (
        set(proposed.get("files") or {}) | set(proposed.get("excluded_unit_receipts") or {})
    )
    if cleared_unresolved - proposed_resolved:
        raise ValueError("invalid proposed cursor: unresolved obligations lack parsed or excluded resolution proof")
    merged = dict(current)
    merged.update(
        {
            key: value
            for key, value in proposed.items()
            if key
            not in {
                "files",
                "excluded_file_keys",
                "replace_files",
                "base_cursor_digest",
                "base_revision",
            }
        }
    )
    files = {} if proposed.get("replace_files") is True else dict(current.get("files") or {})
    for key, signature in (proposed.get("files") or {}).items():
        # Exact cursor CAS makes this proposal the only admissible scan of the
        # current state. Source files may legitimately be replaced or rolled
        # back, so metadata ordering must not override fresh observed truth.
        files[str(key)] = signature
    for key in proposed.get("excluded_file_keys") or []:
        files.pop(str(key), None)
    merged.pop("excluded_file_keys", None)
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
        proposed_has_gap = bool(
            int(proposed.get("pending_files") or 0)
            or proposed.get("source_errors")
            or int(proposed.get("unsupported_source_count") or 0)
            or int(proposed.get("unresolved_unit_count") or 0)
            or proposed.get("adapter_gaps")
            or proposed.get("adapter_gap_routes")
        )
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
    if (
        pending
        or errors
        or int(merged.get("unsupported_source_count") or 0)
        or int(merged.get("unresolved_unit_count") or 0)
        or merged.get("adapter_gaps")
        or merged.get("adapter_gap_routes")
    ):
        scope = f"partial:{target}" if not scope.startswith("partial:") else scope
    merged["target_scope"] = target
    merged["scope"] = scope
    merged["pending_files"] = pending
    merged["source_errors"] = errors
    merged["revision"] = current_revision + 1
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

    occurrence_rows = [dict(row) for row in occurrences]
    occurrences_by_id = _index_by_id(occurrence_rows, "occurrence_id")
    projected_atoms_by_id = _index_by_id(projected_atoms, "atom_id")
    successor_edges = {
        predecessor_id
        for atom in projected_atoms
        if lineage_edge_valid(atom, policy=policy)
        for predecessor in (atom.get("predecessor_ids") or [])
        if (predecessor_id := str(predecessor)) in projected_atoms_by_id
        and lineage_edge_chronology_valid(
            atom,
            projected_atoms_by_id[predecessor_id],
            occurrences_by_id,
        )
    }
    for atom in projected_atoms:
        atom["is_current_intent"] = str(atom["atom_id"]) not in successor_edges
    projected_atoms.sort(key=lambda atom: (-float(atom["priority_score"]), str(atom["atom_id"])))

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
        *validate_source_adapter_cursor(cursor),
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
            if occurrence.get("excluded_reason") not in {
                "source_contract_excluded",
                "transport_duplicate",
                "transport_echo",
            }:
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
            for predecessor_id in predecessor_ids:
                predecessor = atoms_by_id.get(predecessor_id)
                if predecessor is not None and not lineage_edge_chronology_valid(
                    atom,
                    predecessor,
                    occurrences_by_id,
                ):
                    errors.append(f"{atom_id}: predecessor edge is not strictly chronological")
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


PROMPT_AUTHORITY_SEAL_SCHEMA = "limen.prompt-authority-seal.v1"
PROMPT_AUTHORITY_SEAL_SCHEMA_VERSION = 1
PROMPT_AUTHORITY_SEAL_MAX_BYTES = 64 * 1024
PROMPT_AUTHORITY_SEAL_MAX_SOURCE_FAMILIES = 128
_PROMPT_AUTHORITY_FAMILY_FIELDS = (
    "discovered",
    "converged",
    "adapted",
    "excluded",
    "pending",
    "errors",
    "unsupported",
)
_PROMPT_AUTHORITY_COVERAGE_FIELDS = (
    "occurrences",
    "operator_occurrences",
    "derived_occurrences",
    "excluded_occurrences",
    "atoms",
    "current_intents",
    "current_unresolved_atoms",
    "lineages",
    "assessed_atoms",
)
_PROMPT_AUTHORITY_ERROR_REASONS = (
    "adapter_missing",
    "bounded_ceiling_exceeded",
    "containment_violation",
    "malformed_source",
    "prompt_grounding_failed",
    "source_changed",
    "source_unavailable",
    "other",
)
_PROMPT_AUTHORITY_HASH_FIELDS = (
    "semantic",
    "policy",
    "source_cursor",
    "source_families",
    "source_manifest",
    "all_source_manifest",
    "source_units",
    "unsupported_units",
    "unresolved_units",
    "excluded_unit_receipts",
    "adapted_unit_receipts",
    "source_adapter_contract",
    "source_scan_receipt",
    "source_scanner_code",
    "source_scan_payload",
)
_PROMPT_AUTHORITY_REQUIRED_HASH_FIELDS = _PROMPT_AUTHORITY_HASH_FIELDS
_PUBLIC_SCOPE_LABEL = re.compile(r"(?:all|fixture|unknown|partial:all|(?:partial:)?recent:[0-9]+)")
_PUBLIC_SCOPE_ALIAS = re.compile(r"scope-[0-9a-f]{16}")
_PUBLIC_SOURCE_ALIAS = re.compile(r"source-[0-9a-f]{16}")
_PUBLIC_SOURCE_FAMILY_LABELS: frozenset[str] | None = None
_PROMPT_AUTHORITY_ALIAS_BLOCKER_REASONS: tuple[str, ...] | None = None


def _public_scope_label(value: Any) -> str:
    """Return a controlled scope token without copying an unexpected value."""

    candidate = str(value or "unknown")
    if _PUBLIC_SCOPE_LABEL.fullmatch(candidate):
        return candidate
    return f"scope-{digest(candidate)[:16]}"


def _public_scope_label_valid(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and (_PUBLIC_SCOPE_LABEL.fullmatch(value) is not None or _PUBLIC_SCOPE_ALIAS.fullmatch(value) is not None)
    )


def _public_source_family_labels() -> frozenset[str]:
    """Derive publishable family IDs from the versioned source contract."""

    global _PUBLIC_SOURCE_FAMILY_LABELS
    if _PUBLIC_SOURCE_FAMILY_LABELS is not None:
        return _PUBLIC_SOURCE_FAMILY_LABELS
    module = _load_source_contract_module()
    labels: set[str] = set()
    for field in ("SOURCE_ADAPTER_RULES", "SOURCE_EXCLUSION_RULES", "SOURCE_RECORD_SCHEMAS"):
        rules = getattr(module, field, {})
        if not isinstance(rules, dict):
            continue
        for rule in rules.values():
            if not isinstance(rule, dict):
                continue
            source = rule.get("source")
            if isinstance(source, str):
                labels.add(source)
            sources = rule.get("sources")
            if isinstance(sources, (list, tuple)):
                labels.update(value for value in sources if isinstance(value, str))
    _PUBLIC_SOURCE_FAMILY_LABELS = frozenset(labels)
    return _PUBLIC_SOURCE_FAMILY_LABELS


def _public_source_family_label(value: Any) -> str:
    """Keep contract-owned IDs readable and make every other family opaque."""

    candidate = str(value or "unknown")
    if candidate in _public_source_family_labels():
        return candidate
    return f"source-{digest(candidate)[:16]}"


def _public_source_family_label_valid(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and (
            value == "other-source-families"
            or value in _public_source_family_labels()
            or _PUBLIC_SOURCE_ALIAS.fullmatch(value) is not None
        )
    )


def _prompt_authority_alias_blocker_reasons() -> tuple[str, ...]:
    """Return a fixed, contract-owned public reason taxonomy plus a safe overflow row."""

    global _PROMPT_AUTHORITY_ALIAS_BLOCKER_REASONS
    if _PROMPT_AUTHORITY_ALIAS_BLOCKER_REASONS is None:
        contract = current_source_adapter_contract()
        reasons = tuple(
            sorted(value for value in (contract.get("alias_blocker_reasons") or []) if isinstance(value, str))
        )
        _PROMPT_AUTHORITY_ALIAS_BLOCKER_REASONS = (*reasons, "other")
    return _PROMPT_AUTHORITY_ALIAS_BLOCKER_REASONS


def _prompt_authority_alias_blocker_counts(value: Any) -> dict[str, int]:
    """Collapse alias blockers into the fixed public taxonomy without leaking labels."""

    reasons = _prompt_authority_alias_blocker_reasons()
    known = set(reasons) - {"other"}
    counts = {reason: 0 for reason in reasons}
    if not isinstance(value, dict):
        return counts
    for raw_reason, raw_count in value.items():
        reason = str(raw_reason)
        count = _int_or_zero(raw_count)
        counts[reason if reason in known else "other"] += count
    return counts


def _public_digest(value: Any) -> str | None:
    candidate = str(value or "")
    return candidate if re.fullmatch(r"[0-9a-f]{64}", candidate) is not None else None


def _prompt_authority_source_families(
    value: Any,
) -> tuple[dict[str, dict[str, int]], dict[str, Any]]:
    """Bound family cardinality while preserving exact aggregate totals."""

    aggregated: dict[str, dict[str, int]] = {}
    for raw_source, raw_counts in _semantic_source_families(value).items():
        source = _public_source_family_label(raw_source)
        counts = aggregated.setdefault(source, {field: 0 for field in _PROMPT_AUTHORITY_FAMILY_FIELDS})
        for field in _PROMPT_AUTHORITY_FAMILY_FIELDS:
            counts[field] += _int_or_zero(raw_counts.get(field))

    ranked = sorted(
        aggregated.items(),
        key=lambda item: (-sum(item[1].values()), item[0]),
    )
    overflow_rows: list[tuple[str, dict[str, int]]] = []
    if len(ranked) > PROMPT_AUTHORITY_SEAL_MAX_SOURCE_FAMILIES:
        keep = PROMPT_AUTHORITY_SEAL_MAX_SOURCE_FAMILIES - 1
        overflow_rows = ranked[keep:]
        ranked = ranked[:keep]
        overflow_counts = {field: 0 for field in _PROMPT_AUTHORITY_FAMILY_FIELDS}
        for _source, counts in overflow_rows:
            for field in _PROMPT_AUTHORITY_FAMILY_FIELDS:
                overflow_counts[field] += counts[field]
        ranked.append(("other-source-families", overflow_counts))

    families = {source: counts for source, counts in sorted(ranked)}
    overflow = {
        "count": len(overflow_rows),
        "labels_digest": digest(sorted(source for source, _counts in overflow_rows)),
    }
    return families, overflow


def _prompt_authority_error_reason(value: Any) -> str:
    """Collapse a private error into a fixed, locator-free reason taxonomy."""

    error = str(value or "").lower()
    if "bounded ceiling" in error or "exceeds bounded" in error:
        return "bounded_ceiling_exceeded"
    if "changed during" in error or "database or wal changed" in error:
        return "source_changed"
    if "cannot be stat'ed" in error or "source disappeared" in error or "obligations are unavailable" in error:
        return "source_unavailable"
    if any(
        marker in error
        for marker in (
            "symlink",
            "outside the canonical",
            "outside its containment",
            "escapes its declared",
            "escapes isolated",
            "cannot be resolved",
        )
    ):
        return "containment_violation"
    if "could not be grounded" in error:
        return "prompt_grounding_failed"
    if "requires an explicit prompt adapter" in error or "unknown opencode user-bearing" in error:
        return "adapter_missing"
    if any(
        marker in error
        for marker in (
            "malformed",
            "non-object",
            "unreadable json",
            "does not match the bounded adapter schema",
            "identity is ambiguous",
            "too many session identities",
        )
    ):
        return "malformed_source"
    return "other"


def _prompt_authority_ready(
    *,
    validation_ok: bool,
    scope: Any,
    totals: Any,
    hashes: Any,
    source_alias_blocker_counts: Any,
    public_projection_digest: Any,
) -> bool:
    """Derive the authority verdict from complete, public-safe evidence."""

    if (
        not isinstance(scope, dict)
        or not isinstance(totals, dict)
        or not isinstance(hashes, dict)
        or not isinstance(source_alias_blocker_counts, dict)
    ):
        return False
    zero_fields = ("pending", "errors", "unsupported", "unresolved", "adapter_gaps", "validation_errors")
    numeric_fields = (*zero_fields, "source_units", "converged", "excluded", "adapted")
    if any(not _nonnegative_exact_int(totals.get(field)) for field in numeric_fields):
        return False
    current_contract = _semantic_source_adapter_contract(current_source_adapter_contract())
    return bool(
        validation_ok
        and scope.get("scope") == "all"
        and scope.get("target_scope") == "all"
        and scope.get("all_baseline_complete") is True
        and scope.get("scanner_version") == current_contract.get("scanner_version")
        and not any(totals.get(field) for field in zero_fields)
        and not any(source_alias_blocker_counts.values())
        and _public_digest(public_projection_digest) is not None
        and all(_public_digest(hashes.get(field)) is not None for field in _PROMPT_AUTHORITY_REQUIRED_HASH_FIELDS)
        and hashes.get("source_adapter_contract") == current_contract.get("digest")
        and hashes.get("source_manifest") == hashes.get("all_source_manifest")
        and totals.get("source_units") == totals.get("converged", 0) + totals.get("excluded", 0)
        and totals.get("adapted", 0) <= totals.get("converged", 0)
    )


def prompt_authority_seal(
    snapshot: dict[str, Any],
    *,
    public: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic counts/hash-only public authority receipt."""

    raw_scope = snapshot.get("source_scope")
    scope = raw_scope if isinstance(raw_scope, dict) else {}
    raw_validation = snapshot.get("validation")
    validation = raw_validation if isinstance(raw_validation, dict) else {}
    raw_errors = scope.get("source_errors")
    source_errors = [value for value in raw_errors if isinstance(value, str)] if isinstance(raw_errors, list) else []
    source_error_reasons = {reason: 0 for reason in _PROMPT_AUTHORITY_ERROR_REASONS}
    for error in source_errors:
        source_error_reasons[_prompt_authority_error_reason(error)] += 1

    source_families, family_overflow = _prompt_authority_source_families(scope.get("source_families"))
    source_family_totals = {
        field: sum(counts[field] for counts in source_families.values()) for field in _PROMPT_AUTHORITY_FAMILY_FIELDS
    }
    source_alias_blocker_counts = _prompt_authority_alias_blocker_counts(scope.get("source_alias_blocker_counts"))
    raw_gaps = scope.get("adapter_gaps")
    adapter_gaps = (
        sorted({_public_source_family_label(value) for value in raw_gaps})
        if isinstance(raw_gaps, (list, tuple))
        else []
    )
    coverage_source = snapshot.get("coverage")
    coverage_source = coverage_source if isinstance(coverage_source, dict) else {}
    coverage = {field: _int_or_zero(coverage_source.get(field)) for field in _PROMPT_AUTHORITY_COVERAGE_FIELDS}
    source_scan = scope.get("source_scan_receipt")
    source_scan = source_scan if isinstance(source_scan, dict) else {}
    adapter_contract = scope.get("source_adapter_contract")
    adapter_contract = adapter_contract if isinstance(adapter_contract, dict) else {}
    scope_label = _public_scope_label(scope.get("scope"))
    target_scope = _public_scope_label(scope.get("target_scope"))
    totals = {
        "source_units": _int_or_zero(scope.get("source_unit_count")),
        "converged": source_family_totals["converged"],
        "pending": _int_or_zero(scope.get("pending_files")),
        "errors": len(source_errors),
        "unsupported": _int_or_zero(scope.get("unsupported_source_count")),
        "unresolved": _int_or_zero(scope.get("unresolved_unit_count")),
        "excluded": _int_or_zero(scope.get("excluded_source_count")),
        "adapted": _int_or_zero(scope.get("adapted_source_count")),
        "adapter_gaps": len(adapter_gaps),
        "validation_errors": len(validation.get("errors") or []) if isinstance(validation.get("errors"), list) else 0,
    }
    hashes = {
        "semantic": _public_digest(snapshot.get("semantic_digest")),
        "policy": _public_digest(snapshot.get("policy_digest")),
        "source_cursor": _public_digest(snapshot.get("source_cursor_digest")),
        "source_families": digest(
            {
                "families": source_families,
                "overflow": family_overflow,
            }
        ),
        "source_manifest": _public_digest(scope.get("source_manifest_digest")),
        "all_source_manifest": _public_digest(scope.get("all_source_manifest_digest")),
        "source_units": _public_digest(scope.get("source_units_digest")),
        "unsupported_units": _public_digest(scope.get("unsupported_units_digest")),
        "unresolved_units": _public_digest(scope.get("unresolved_units_digest")),
        "excluded_unit_receipts": _public_digest(scope.get("excluded_unit_receipts_digest")),
        "adapted_unit_receipts": _public_digest(scope.get("adapted_unit_receipts_digest")),
        "source_adapter_contract": _public_digest(adapter_contract.get("digest")),
        "source_scan_receipt": _public_digest(source_scan.get("sha256")),
        "source_scanner_code": _public_digest(source_scan.get("scanner_code_digest")),
        "source_scan_payload": _public_digest(source_scan.get("scan_payload_digest")),
    }
    validation_ok = validation.get("ok") is True
    seal_scope = {
        "scope": scope_label,
        "target_scope": target_scope,
        "all_baseline_complete": scope.get("all_baseline_complete") is True,
        "scanner_version": _int_or_zero(scope.get("scanner_version")),
        "horizon_days": (
            scope.get("horizon_days")
            if isinstance(scope.get("horizon_days"), int) and not isinstance(scope.get("horizon_days"), bool)
            else None
        ),
    }
    public_projection_digest = _public_digest(
        (public if isinstance(public, dict) else public_projection(snapshot)).get("projection_digest")
    )
    authority_ready = _prompt_authority_ready(
        validation_ok=validation_ok,
        scope=seal_scope,
        totals=totals,
        hashes=hashes,
        source_alias_blocker_counts=source_alias_blocker_counts,
        public_projection_digest=public_projection_digest,
    )
    material: dict[str, Any] = {
        "schema": PROMPT_AUTHORITY_SEAL_SCHEMA,
        "schema_version": PROMPT_AUTHORITY_SEAL_SCHEMA_VERSION,
        "authority_ready": authority_ready,
        "validation_ok": validation_ok,
        "scope": seal_scope,
        "totals": totals,
        "coverage": coverage,
        "source_families": source_families,
        "source_family_overflow": family_overflow,
        "source_error_reason_counts": source_error_reasons,
        "source_alias_blocker_counts": source_alias_blocker_counts,
        "adapter_gaps_digest": digest(adapter_gaps),
        "public_projection_digest": public_projection_digest,
        "hashes": hashes,
    }
    material["content_hash"] = digest(material)
    return material


def prompt_authority_seal_bytes(snapshot: dict[str, Any]) -> bytes:
    payload = _json_bytes(prompt_authority_seal(snapshot))
    if len(payload) > PROMPT_AUTHORITY_SEAL_MAX_BYTES:
        raise ValueError("public prompt authority seal exceeds its hard byte ceiling")
    return payload


def _prompt_authority_seal_digest_valid(seal: dict[str, Any]) -> bool:
    claimed = str(seal.get("content_hash") or "")
    material = {key: value for key, value in seal.items() if key != "content_hash"}
    return bool(
        not _prompt_authority_seal_schema_errors(seal)
        and claimed
        and claimed == digest(material)
        and len(_json_bytes(seal)) <= PROMPT_AUTHORITY_SEAL_MAX_BYTES
    )


def _prompt_authority_seal_schema_errors(seal: Any) -> list[str]:
    """Reject extra/free-text fields before a public-only seal can be trusted."""

    if not isinstance(seal, dict):
        return ["seal must be an object"]
    errors: list[str] = []
    expected_top = {
        "schema",
        "schema_version",
        "authority_ready",
        "validation_ok",
        "scope",
        "totals",
        "coverage",
        "source_families",
        "source_family_overflow",
        "source_error_reason_counts",
        "source_alias_blocker_counts",
        "adapter_gaps_digest",
        "public_projection_digest",
        "hashes",
        "content_hash",
    }
    if set(seal) != expected_top:
        errors.append("seal fields do not match the fixed schema")
    if seal.get("schema") != PROMPT_AUTHORITY_SEAL_SCHEMA:
        errors.append("seal schema is stale")
    if (
        not _nonnegative_exact_int(seal.get("schema_version"))
        or seal.get("schema_version") != PROMPT_AUTHORITY_SEAL_SCHEMA_VERSION
    ):
        errors.append("seal schema version is stale")
    if not isinstance(seal.get("authority_ready"), bool):
        errors.append("seal authority verdict must be boolean")
    if not isinstance(seal.get("validation_ok"), bool):
        errors.append("seal validation verdict must be boolean")

    scope = seal.get("scope")
    expected_scope = {"scope", "target_scope", "all_baseline_complete", "scanner_version", "horizon_days"}
    if not isinstance(scope, dict) or set(scope) != expected_scope:
        errors.append("seal scope is malformed")
    else:
        if any(not _public_scope_label_valid(scope.get(field)) for field in ("scope", "target_scope")):
            errors.append("seal scope labels are unsafe")
        if not isinstance(scope.get("all_baseline_complete"), bool):
            errors.append("seal baseline verdict must be boolean")
        if not _nonnegative_exact_int(scope.get("scanner_version")):
            errors.append("seal scanner version must be a non-negative integer")
        horizon = scope.get("horizon_days")
        if horizon is not None and (isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 0):
            errors.append("seal horizon must be a non-negative integer or null")

    totals = seal.get("totals")
    expected_totals = {
        "source_units",
        "converged",
        "pending",
        "errors",
        "unsupported",
        "unresolved",
        "excluded",
        "adapted",
        "adapter_gaps",
        "validation_errors",
    }
    if not isinstance(totals, dict) or set(totals) != expected_totals:
        errors.append("seal totals are malformed")
    elif any(not _nonnegative_exact_int(value) for value in totals.values()):
        errors.append("seal totals must be non-negative integers")

    coverage = seal.get("coverage")
    if not isinstance(coverage, dict) or set(coverage) != set(_PROMPT_AUTHORITY_COVERAGE_FIELDS):
        errors.append("seal coverage is malformed")
    elif any(not _nonnegative_exact_int(value) for value in coverage.values()):
        errors.append("seal coverage must contain non-negative integers")

    families = seal.get("source_families")
    if (
        not isinstance(families, dict)
        or len(families) > PROMPT_AUTHORITY_SEAL_MAX_SOURCE_FAMILIES
        or any(
            not _public_source_family_label_valid(source)
            or not isinstance(counts, dict)
            or set(counts) != set(_PROMPT_AUTHORITY_FAMILY_FIELDS)
            or any(not _nonnegative_exact_int(count) for count in counts.values())
            for source, counts in families.items()
        )
    ):
        errors.append("seal source family aggregates are malformed")

    overflow = seal.get("source_family_overflow")
    if (
        not isinstance(overflow, dict)
        or set(overflow) != {"count", "labels_digest"}
        or not _nonnegative_exact_int(overflow.get("count"))
        or _public_digest(overflow.get("labels_digest")) is None
    ):
        errors.append("seal source family overflow receipt is malformed")
    elif isinstance(families, dict):
        overflow_count = overflow.get("count")
        has_overflow_row = "other-source-families" in families
        if (bool(overflow_count) and not has_overflow_row) or (not overflow_count and has_overflow_row):
            errors.append("seal source family overflow row does not match its count")
        if overflow_count == 0 and overflow.get("labels_digest") != digest([]):
            errors.append("seal empty source family overflow digest is malformed")

    reasons = seal.get("source_error_reason_counts")
    if (
        not isinstance(reasons, dict)
        or set(reasons) != set(_PROMPT_AUTHORITY_ERROR_REASONS)
        or any(not _nonnegative_exact_int(value) for value in reasons.values())
    ):
        errors.append("seal source error reasons are malformed")
    elif isinstance(totals, dict) and _nonnegative_exact_int(totals.get("errors")):
        if sum(reasons.values()) != totals.get("errors"):
            errors.append("seal source error reasons do not match the error total")

    alias_blockers = seal.get("source_alias_blocker_counts")
    if (
        not isinstance(alias_blockers, dict)
        or set(alias_blockers) != set(_prompt_authority_alias_blocker_reasons())
        or any(not _nonnegative_exact_int(value) for value in alias_blockers.values())
    ):
        errors.append("seal source alias blocker counts are malformed")

    if isinstance(families, dict) and isinstance(totals, dict):
        family_total_fields = {
            "discovered": "source_units",
            "converged": "converged",
            "adapted": "adapted",
            "excluded": "excluded",
            "pending": "pending",
            "errors": "errors",
            "unsupported": "unsupported",
        }
        for family_field, total_field in family_total_fields.items():
            if all(isinstance(counts, dict) for counts in families.values()) and _nonnegative_exact_int(
                totals.get(total_field)
            ):
                if sum(_int_or_zero(counts.get(family_field)) for counts in families.values()) != totals.get(
                    total_field
                ):
                    errors.append(f"seal source family {family_field} counts do not match {total_field}")
        if (
            isinstance(scope, dict)
            and scope.get("scope") == "all"
            and scope.get("target_scope") == "all"
            and all(
                _nonnegative_exact_int(totals.get(field))
                for field in ("source_units", "converged", "excluded", "adapted")
            )
        ):
            if totals["source_units"] != totals["converged"] + totals["excluded"]:
                errors.append("seal exact-all source family coverage is incomplete")
            if totals["adapted"] > totals["converged"]:
                errors.append("seal exact-all adapted count exceeds converged coverage")

    hashes = seal.get("hashes")
    if not isinstance(hashes, dict) or set(hashes) != set(_PROMPT_AUTHORITY_HASH_FIELDS):
        errors.append("seal hash bindings are malformed")
    elif any(value is not None and _public_digest(value) is None for value in hashes.values()):
        errors.append("seal hash bindings must be lowercase SHA-256 values or null")
    elif isinstance(families, dict) and isinstance(overflow, dict):
        expected_family_digest = digest({"families": families, "overflow": overflow})
        if hashes.get("source_families") != expected_family_digest:
            errors.append("seal source family aggregate digest is stale")
    if _public_digest(seal.get("adapter_gaps_digest")) is None:
        errors.append("seal adapter gap digest is malformed")
    if _public_digest(seal.get("public_projection_digest")) is None:
        errors.append("seal public projection digest is malformed")
    if _public_digest(seal.get("content_hash")) is None:
        errors.append("seal content hash is malformed")
    expected_authority_ready = _prompt_authority_ready(
        validation_ok=seal.get("validation_ok") is True,
        scope=scope,
        totals=totals,
        hashes=hashes,
        source_alias_blocker_counts=alias_blockers,
        public_projection_digest=seal.get("public_projection_digest"),
    )
    if seal.get("authority_ready") != expected_authority_ready:
        errors.append("seal authority verdict does not match its evidence")
    return errors


def _prompt_authority_seal_matches_public(seal: dict[str, Any], public: dict[str, Any]) -> bool:
    def object_field(container: dict[str, Any], field: str) -> dict[str, Any]:
        value = container.get(field)
        return value if isinstance(value, dict) else {}

    hashes = object_field(seal, "hashes")
    seal_scope = object_field(seal, "scope")
    public_scope = object_field(public, "source_scope")
    totals = object_field(seal, "totals")
    coverage = object_field(seal, "coverage")
    public_coverage = object_field(public, "coverage")
    validation = object_field(public, "validation")
    public_adapter_contract = object_field(public_scope, "source_adapter_contract")
    current_adapter_contract = _semantic_source_adapter_contract(current_source_adapter_contract())
    public_source_scan = object_field(public_scope, "source_scan_receipt")
    public_adapter_gaps = public_scope.get("adapter_gaps")
    sanitized_public_adapter_gaps = (
        sorted({_public_source_family_label(value) for value in public_adapter_gaps})
        if isinstance(public_adapter_gaps, list)
        else []
    )
    raw_public_alias_blockers = public_scope.get("source_alias_blocker_counts")
    public_alias_blockers = _prompt_authority_alias_blocker_counts(raw_public_alias_blockers)
    current_alias_reasons = set(current_adapter_contract.get("alias_blocker_reasons") or [])
    public_alias_blockers_valid = bool(
        isinstance(raw_public_alias_blockers, dict)
        and set(raw_public_alias_blockers) <= current_alias_reasons
        and all(
            isinstance(reason, str) and _nonnegative_exact_int(count)
            for reason, count in raw_public_alias_blockers.items()
        )
    )
    contract_required = bool(
        public_scope.get("target_scope") == "all"
        or _int_or_zero(public_scope.get("scanner_version"))
        or _public_digest(public_adapter_contract.get("digest")) is not None
    )
    current_contract_matches = bool(
        not contract_required
        or (
            _semantic_source_adapter_contract(public_adapter_contract) == current_adapter_contract
            and public_scope.get("scanner_version") == current_adapter_contract.get("scanner_version")
        )
    )
    return bool(
        current_contract_matches
        and public_alias_blockers_valid
        and seal.get("public_projection_digest") == _public_digest(public.get("projection_digest"))
        and hashes.get("semantic") == _public_digest(public.get("semantic_digest"))
        and hashes.get("policy") == _public_digest(public.get("policy_digest"))
        and hashes.get("source_cursor") == _public_digest(public.get("source_cursor_digest"))
        and hashes.get("source_families") == _public_digest(public_scope.get("source_families_digest"))
        and hashes.get("source_manifest") == _public_digest(public_scope.get("source_manifest_digest"))
        and hashes.get("all_source_manifest") == _public_digest(public_scope.get("all_source_manifest_digest"))
        and hashes.get("source_units") == _public_digest(public_scope.get("source_units_digest"))
        and hashes.get("unsupported_units") == _public_digest(public_scope.get("unsupported_units_digest"))
        and hashes.get("unresolved_units") == _public_digest(public_scope.get("unresolved_units_digest"))
        and hashes.get("excluded_unit_receipts") == _public_digest(public_scope.get("excluded_unit_receipts_digest"))
        and hashes.get("adapted_unit_receipts") == _public_digest(public_scope.get("adapted_unit_receipts_digest"))
        and hashes.get("source_adapter_contract") == _public_digest(public_adapter_contract.get("digest"))
        and hashes.get("source_scan_receipt") == _public_digest(public_source_scan.get("sha256"))
        and hashes.get("source_scanner_code") == _public_digest(public_source_scan.get("scanner_code_digest"))
        and hashes.get("source_scan_payload") == _public_digest(public_source_scan.get("scan_payload_digest"))
        and seal.get("validation_ok") == (validation.get("ok") is True)
        and seal_scope.get("scope") == _public_scope_label(public_scope.get("scope"))
        and seal_scope.get("target_scope") == _public_scope_label(public_scope.get("target_scope"))
        and seal_scope.get("all_baseline_complete") == (public_scope.get("all_baseline_complete") is True)
        and seal_scope.get("scanner_version") == _int_or_zero(public_scope.get("scanner_version"))
        and seal_scope.get("horizon_days") == public_scope.get("horizon_days")
        and totals.get("source_units") == _int_or_zero(public_scope.get("source_unit_count"))
        and totals.get("converged") == _int_or_zero(public_scope.get("source_converged_count"))
        and totals.get("pending") == _int_or_zero(public_scope.get("pending_files"))
        and totals.get("errors") == _int_or_zero(public_scope.get("source_error_count"))
        and totals.get("unsupported") == _int_or_zero(public_scope.get("unsupported_source_count"))
        and totals.get("unresolved") == _int_or_zero(public_scope.get("unresolved_unit_count"))
        and totals.get("excluded") == _int_or_zero(public_scope.get("excluded_source_count"))
        and totals.get("adapted") == _int_or_zero(public_scope.get("adapted_source_count"))
        and totals.get("adapter_gaps") == len(sanitized_public_adapter_gaps)
        and seal.get("adapter_gaps_digest") == digest(sanitized_public_adapter_gaps)
        and seal.get("source_alias_blocker_counts") == public_alias_blockers
        and totals.get("validation_errors")
        == (len(validation.get("errors") or []) if isinstance(validation.get("errors"), list) else 0)
        and all(coverage.get(field) == _int_or_zero(public_coverage.get(field)) for field in coverage)
    )


def public_projection(snapshot: dict[str, Any], *, limit: int | None = None) -> dict[str, Any]:
    raw_source_scope = snapshot.get("source_scope")
    source_scope = raw_source_scope if isinstance(raw_source_scope, dict) else {}
    raw_source_scan = source_scope.get("source_scan_receipt")
    source_scan = raw_source_scan if isinstance(raw_source_scan, dict) else {}
    source_families, source_family_overflow = _prompt_authority_source_families(source_scope.get("source_families"))
    source_family_digest = digest(
        {
            "families": source_families,
            "overflow": source_family_overflow,
        }
    )
    source_converged_count = sum(counts["converged"] for counts in source_families.values())
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
            "scanner_version": _int_or_zero((snapshot.get("source_scope") or {}).get("scanner_version")),
            "target_scope": (snapshot.get("source_scope") or {}).get("target_scope"),
            "horizon_days": (snapshot.get("source_scope") or {}).get("horizon_days"),
            "all_baseline_complete": (snapshot.get("source_scope") or {}).get("all_baseline_complete") is True,
            "all_source_manifest_digest": (snapshot.get("source_scope") or {}).get("all_source_manifest_digest"),
            "pending_files": (snapshot.get("source_scope") or {}).get("pending_files", 0),
            "source_error_count": len((snapshot.get("source_scope") or {}).get("source_errors") or []),
            "source_unit_count": _int_or_zero((snapshot.get("source_scope") or {}).get("source_unit_count")),
            "source_converged_count": source_converged_count,
            "source_families_digest": source_family_digest,
            "source_units_digest": (snapshot.get("source_scope") or {}).get("source_units_digest"),
            "unsupported_source_count": _int_or_zero(
                (snapshot.get("source_scope") or {}).get("unsupported_source_count")
            ),
            "unsupported_units_digest": (snapshot.get("source_scope") or {}).get("unsupported_units_digest"),
            "unresolved_unit_count": _int_or_zero((snapshot.get("source_scope") or {}).get("unresolved_unit_count")),
            "unresolved_units_digest": (snapshot.get("source_scope") or {}).get("unresolved_units_digest"),
            "source_manifest_digest": (snapshot.get("source_scope") or {}).get("source_manifest_digest"),
            "source_adapter_contract": _semantic_source_adapter_contract(
                (snapshot.get("source_scope") or {}).get("source_adapter_contract")
            ),
            "source_scan_receipt": {
                "sha256": _public_digest(source_scan.get("sha256")),
                "scanner_code_digest": _public_digest(source_scan.get("scanner_code_digest")),
                "scan_payload_digest": _public_digest(source_scan.get("scan_payload_digest")),
            },
            "excluded_source_count": _int_or_zero((snapshot.get("source_scope") or {}).get("excluded_source_count")),
            "source_exclusion_counts": _semantic_count_map(
                (snapshot.get("source_scope") or {}).get("source_exclusion_counts")
            ),
            "excluded_unit_receipts_digest": (snapshot.get("source_scope") or {}).get("excluded_unit_receipts_digest"),
            "adapted_source_count": _int_or_zero((snapshot.get("source_scope") or {}).get("adapted_source_count")),
            "source_adapter_counts": _semantic_count_map(
                (snapshot.get("source_scope") or {}).get("source_adapter_counts")
            ),
            "source_alias_blocker_counts": _semantic_count_map(
                (snapshot.get("source_scope") or {}).get("source_alias_blocker_counts")
            ),
            "adapted_unit_receipts_digest": (snapshot.get("source_scope") or {}).get("adapted_unit_receipts_digest"),
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
        f"- Source scope: `{scope.get('scope') or 'unknown'}`; target: `{scope.get('target_scope') or 'unknown'}`; horizon days: `{scope.get('horizon_days')}`; pending files: `{scope.get('pending_files', 0)}`; source errors: `{scope.get('source_error_count', 0)}`; unsupported: `{scope.get('unsupported_source_count', 0)}`; unresolved units: `{scope.get('unresolved_unit_count', 0)}`.",
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
    raw_scope = snapshot.get("source_scope")
    scope = raw_scope if isinstance(raw_scope, dict) else {}
    return {
        "scope": scope.get("scope"),
        "scanner_version": _int_or_zero(scope.get("scanner_version")),
        "target_scope": scope.get("target_scope"),
        "horizon_days": scope.get("horizon_days"),
        "all_baseline_complete": scope.get("all_baseline_complete") is True,
        "all_source_manifest_digest": scope.get("all_source_manifest_digest"),
        "pending_files": _int_or_zero(scope.get("pending_files")),
        "source_errors": _string_list(scope.get("source_errors")),
        "source_unit_count": _int_or_zero(scope.get("source_unit_count")),
        "source_units_digest": scope.get("source_units_digest"),
        "unsupported_source_count": _int_or_zero(scope.get("unsupported_source_count")),
        "unsupported_units_digest": scope.get("unsupported_units_digest"),
        "unresolved_unit_count": _int_or_zero(scope.get("unresolved_unit_count")),
        "unresolved_units_digest": scope.get("unresolved_units_digest"),
        "source_manifest_digest": scope.get("source_manifest_digest"),
        "source_families": _semantic_source_families(scope.get("source_families")),
        "source_adapter_contract": _semantic_source_adapter_contract(scope.get("source_adapter_contract")),
        "source_scan_receipt": {
            "sha256": _public_digest((scope.get("source_scan_receipt") or {}).get("sha256"))
            if isinstance(scope.get("source_scan_receipt"), dict)
            else None,
            "scanner_code_digest": _public_digest((scope.get("source_scan_receipt") or {}).get("scanner_code_digest"))
            if isinstance(scope.get("source_scan_receipt"), dict)
            else None,
            "scan_payload_digest": _public_digest((scope.get("source_scan_receipt") or {}).get("scan_payload_digest"))
            if isinstance(scope.get("source_scan_receipt"), dict)
            else None,
        },
        "excluded_source_count": _int_or_zero(scope.get("excluded_source_count")),
        "source_exclusion_counts": _semantic_count_map(scope.get("source_exclusion_counts")),
        "excluded_unit_receipts_digest": scope.get("excluded_unit_receipts_digest"),
        "adapted_source_count": _int_or_zero(scope.get("adapted_source_count")),
        "source_adapter_counts": _semantic_count_map(scope.get("source_adapter_counts")),
        "source_alias_blocker_counts": _semantic_count_map(scope.get("source_alias_blocker_counts")),
        "adapted_unit_receipts_digest": scope.get("adapted_unit_receipts_digest"),
        "adapter_gaps": _string_list(scope.get("adapter_gaps")),
        "adapter_gap_routes": [value for value in (scope.get("adapter_gap_routes") or []) if isinstance(value, dict)]
        if isinstance(scope.get("adapter_gap_routes"), (list, tuple))
        else [],
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


def private_marker(
    snapshot: dict[str, Any],
    public: dict[str, Any],
    seal: dict[str, Any],
    *,
    paths: LedgerPaths,
) -> dict[str, Any]:
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
        "public_authority_seal_hash": seal.get("content_hash"),
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


def _prompt_authority_fast_path_valid(
    *,
    marker: dict[str, Any],
    public: dict[str, Any],
    seal: dict[str, Any],
    current_cursor: dict[str, Any],
) -> bool:
    """Re-derive every seal input from the private checkpoint and current cursor."""

    current_scope = cursor_semantic(current_cursor)
    expected_marker_scope = _compact_source_scope({"source_scope": current_scope})
    if marker.get("source_scope") != expected_marker_scope:
        return False
    expected_snapshot = {
        "version": marker.get("version"),
        "updated_through": marker.get("updated_through"),
        "semantic_digest": marker.get("semantic_digest"),
        "policy_digest": marker.get("policy_digest"),
        "source_cursor_digest": marker.get("source_cursor_digest"),
        "source_scope": current_scope,
        "coverage": marker.get("coverage") or {},
        "counts": marker.get("counts") or {},
        "validation": marker.get("validation") or {},
    }
    expected_public_scope = public_projection(expected_snapshot)["source_scope"]
    if public.get("source_scope") != expected_public_scope:
        return False
    for field in (
        "version",
        "updated_through",
        "semantic_digest",
        "policy_digest",
        "source_cursor_digest",
        "coverage",
        "counts",
        "validation",
    ):
        if public.get(field) != expected_snapshot.get(field):
            return False
    public_rows = public.get("unresolved_atoms")
    public_truncated = public.get("unresolved_atoms_truncated")
    current_unresolved = (expected_snapshot.get("coverage") or {}).get("current_unresolved_atoms")
    if (
        not isinstance(public_rows, list)
        or not _nonnegative_exact_int(public_truncated)
        or not _nonnegative_exact_int(current_unresolved)
        or len(public_rows) + _int_or_zero(public_truncated) != _int_or_zero(current_unresolved)
    ):
        return False
    expected_seal = prompt_authority_seal(expected_snapshot, public=public)
    return bool(
        seal == expected_seal
        and _prompt_authority_seal_digest_valid(seal)
        and _prompt_authority_seal_matches_public(seal, public)
    )


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


def _occurrence_order_key(occurrence: dict[str, Any]) -> tuple[dt.datetime, int, int] | None:
    parsed = _parse_time(occurrence.get("timestamp"))
    event_index = occurrence.get("event_index")
    text_index = occurrence.get("text_index")
    if (
        parsed is None
        or isinstance(event_index, bool)
        or not isinstance(event_index, int)
        or event_index < 0
        or isinstance(text_index, bool)
        or not isinstance(text_index, int)
        or text_index < 0
    ):
        return None
    return parsed, event_index, text_index


def lineage_edge_chronology_valid(
    successor_atom: dict[str, Any],
    predecessor_atom: dict[str, Any],
    occurrences_by_id: dict[str, dict[str, Any]],
) -> bool:
    """Return whether a semantic successor is provably later than its predecessor."""

    successor_occurrence_id = str(successor_atom.get("occurrence_id") or "")
    predecessor_occurrence_id = str(predecessor_atom.get("occurrence_id") or "")
    if not successor_occurrence_id or successor_occurrence_id == predecessor_occurrence_id:
        return False
    successor = occurrences_by_id.get(successor_occurrence_id)
    predecessor = occurrences_by_id.get(predecessor_occurrence_id)
    if successor is None or predecessor is None:
        return False
    successor_key = _occurrence_order_key(successor)
    predecessor_key = _occurrence_order_key(predecessor)
    if successor_key is None or predecessor_key is None:
        return False

    successor_time = successor_key[0]
    predecessor_time = predecessor_key[0]
    if successor_time != predecessor_time:
        return successor_time > predecessor_time

    # Equal timestamps are orderable only within the same session, where the
    # normalized event/text indexes form an explicit source order.
    if str(successor.get("session_ref_hash") or "") != str(predecessor.get("session_ref_hash") or ""):
        return False
    return successor_key[1:] > predecessor_key[1:]


def _adjacent_operator_predecessor(
    occurrence: dict[str, Any],
    occurrences: Sequence[dict[str, Any]],
    atoms_by_occurrence: dict[str, list[str]],
) -> str | None:
    current_key = _occurrence_order_key(occurrence)
    if current_key is None:
        return None
    session_hash = str(occurrence.get("session_ref_hash") or "")
    candidates: list[tuple[tuple[dt.datetime, int, int], dict[str, Any]]] = []
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
    try:
        event_index = _event_position(event, "event_index")
        text_index = _event_position(event, "text_index")
        position_invalid = False
    except ValueError:
        event_index = 0
        text_index = 0
        position_invalid = True
    return (
        str(event.get("source") or "unknown"),
        str(event.get("session_ref") or event.get("existing_occurrence_id") or "unknown"),
        parsed is None,
        parsed or dt.datetime.max.replace(tzinfo=dt.timezone.utc),
        position_invalid,
        event_index,
        text_index,
        original_index,
    )


SOURCE_REVISION_FIELDS = (
    "body_kind",
    "provenance",
    "authority",
    "source_locator",
    "timestamp",
    "duplicate_of",
    "excluded_reason",
)


def _source_revision_material(proposed: dict[str, Any]) -> dict[str, Any]:
    return {field: proposed.get(field) for field in SOURCE_REVISION_FIELDS}


def _source_revision_changed(current: dict[str, Any], proposed: dict[str, Any]) -> bool:
    return any(current.get(field) != proposed.get(field) for field in SOURCE_REVISION_FIELDS)


def _excluded_source_units(cursor: dict[str, Any]) -> set[tuple[str, str]]:
    units: set[tuple[str, str]] = set()
    receipts = cursor.get("excluded_unit_receipts")
    if not isinstance(receipts, dict):
        return units
    for key in receipts:
        if not isinstance(key, str):
            continue
        parts = key.split(":", 2)
        if len(parts) == 3 and parts[0].startswith("scan-v"):
            units.add((parts[1], parts[2]))
    return units


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
        replacement_attested = bool(cursor is not None and _pending_source_scan_valid(cursor))
        current_source_cursor_errors = validate_source_adapter_cursor(
            current_cursor,
            receipt_root=paths.private_dir,
        )
        if current_source_cursor_errors and not replacement_attested:
            raise ValueError("invalid stored source adapter cursor: " + "; ".join(current_source_cursor_errors))
        effective_cursor = merge_cursor(current_cursor, cursor)
        exact_all = bool(effective_cursor.get("scope") == "all" and effective_cursor.get("target_scope") == "all")
        cursor_changed = cursor_digest(effective_cursor) != cursor_digest(current_cursor)
        pending_scan_receipt: tuple[Path, bytes] | None = None
        if exact_all and replacement_attested:
            preseal_live_errors = validate_live_source_custody(effective_cursor)
            if preseal_live_errors:
                raise ValueError("live source custody changed: " + "; ".join(preseal_live_errors))
        if exact_all and cursor is not None and cursor_changed:
            if (
                not current_source_cursor_errors
                and current_cursor.get("scope") == "all"
                and current_cursor.get("target_scope") == "all"
                and source_scan_state_digest(effective_cursor) == source_scan_state_digest(current_cursor)
            ):
                _clear_source_scan_authority(effective_cursor)
                effective_cursor = current_cursor
            else:
                effective_cursor, receipt_ref, receipt_bytes = _seal_attested_source_scan(effective_cursor)
                receipt_path = paths.private_dir / receipt_ref
                _validate_source_scan_receipt_destination(paths, receipt_path)
                if receipt_path.exists() and receipt_path.read_bytes() != receipt_bytes:
                    raise ValueError("source scan receipt hash path contains different bytes")
                if receipt_path.exists() and receipt_path.stat().st_mode & 0o777 != 0o400:
                    raise ValueError("source scan receipt artifact is not immutable")
                pending_scan_receipt = (receipt_path, receipt_bytes)
        elif not exact_all:
            effective_cursor = _clear_source_scan_authority(effective_cursor)
        source_cursor_errors = validate_source_adapter_cursor(
            effective_cursor,
            receipt_root=None if pending_scan_receipt else paths.private_dir,
        )
        if source_cursor_errors:
            raise ValueError("invalid source adapter cursor: " + "; ".join(source_cursor_errors))
        live_source_errors = validate_live_source_custody(effective_cursor)
        if live_source_errors:
            raise ValueError("live source custody changed: " + "; ".join(live_source_errors))
        if cursor_digest(effective_cursor) == cursor_digest(current_cursor):
            effective_cursor = current_cursor

        marker = load_json(paths.private_snapshot)
        existing_public = load_json(paths.public_snapshot)
        existing_seal = load_json(paths.public_seal)
        fast_public_ok = bool(
            marker
            and existing_public
            and existing_seal
            and not events
            and not outcomes
            and cursor_digest(effective_cursor) == cursor_digest(current_cursor)
            and marker.get("policy_digest") == digest(policy)
            and marker.get("source_cursor_digest") == cursor_digest(current_cursor)
            and marker.get("public_projection_digest") == existing_public.get("projection_digest")
            and marker.get("public_authority_seal_hash") == existing_seal.get("content_hash")
            and marker.get("semantic_digest") == existing_public.get("semantic_digest")
            and marker.get("journal_signatures")
            == {
                "events": _path_signature(paths.event_journal),
                "outcomes": _path_signature(paths.outcome_journal),
                "cursor": _path_signature(paths.cursor),
                "raw_store": _raw_store_signature(paths),
            }
            and _public_digest_valid(existing_public)
            and _prompt_authority_fast_path_valid(
                marker=marker,
                public=existing_public,
                seal=existing_seal,
                current_cursor=current_cursor,
            )
            and paths.public_snapshot.exists()
            and paths.public_snapshot.read_bytes() == _json_bytes(existing_public)
            and paths.public_seal.exists()
            and paths.public_seal.read_bytes() == _json_bytes(existing_seal)
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
        pending_raw_objects: dict[str, str] = {}
        replacements: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}
        excluded_units = _excluded_source_units(effective_cursor)
        if excluded_units:
            contract = _semantic_source_adapter_contract(effective_cursor.get("source_adapter_contract"))
            exclusion_digest = digest(
                {
                    "kind": "source_contract_excluded",
                    "contract_digest": contract.get("digest"),
                }
            )
            for stored_occurrence in occurrence_rows:
                occurrence_id = str(stored_occurrence.get("occurrence_id") or "")
                source_locator = str(stored_occurrence.get("source_locator") or "")
                source_path = source_locator.rsplit("#", 1)[0] if "#" in source_locator else source_locator
                if (
                    not occurrence_id
                    or (str(stored_occurrence.get("source") or ""), source_path) not in excluded_units
                    or stored_occurrence.get("excluded_reason") == "source_contract_excluded"
                ):
                    continue
                old_atom_ids = set(atoms_by_occurrence.get(occurrence_id, []))
                assessed_removed = {
                    atom_id
                    for atom_id in old_atom_ids
                    if str((outcomes_by_atom.get(atom_id) or {}).get("disposition") or "unassessed") != "unassessed"
                }
                if assessed_removed:
                    raise ValueError(
                        "source contract exclusion would orphan assessed atoms: " + ", ".join(sorted(assessed_removed))
                    )
                revised = dict(stored_occurrence)
                revised["atom_ids"] = []
                revised["coverage_segment_hashes"] = []
                revised["excluded_reason"] = "source_contract_excluded"
                revised["classification_revision"] = int(stored_occurrence.get("classification_revision") or 0) + 1
                revised["classification_digest"] = exclusion_digest
                replacements[occurrence_id] = (revised, [])
                new_event_rows.append(
                    {
                        "occurrence": revised,
                        "atoms": [],
                        "revision_of": occurrence_id,
                    }
                )
                occurrence_by_id[occurrence_id] = revised
                atoms_by_occurrence[occurrence_id] = []
                for atom_id in old_atom_ids:
                    atom_by_id.pop(atom_id, None)
        ordered_events = sorted(
            ((index, event) for index, event in enumerate(events) if isinstance(event, dict)),
            key=_event_ingest_order,
        )
        for _input_index, event in ordered_events:
            if not isinstance(event, dict):
                continue
            event_locator = str(event.get("source_locator") or "")
            event_path = event_locator.rsplit("#", 1)[0] if "#" in event_locator else event_locator
            if (str(event.get("source") or ""), event_path) in excluded_units:
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
                for field in SOURCE_REVISION_FIELDS:
                    occurrence[field] = proposed_occurrence.get(field)
                occurrence_id = requested_existing_id
            else:
                occurrence = proposed_occurrence
                occurrence_id = str(occurrence["occurrence_id"])
                existing_occurrence = occurrence_by_id.get(occurrence_id)
            resolved_locator = str(occurrence.get("source_locator") or "")
            resolved_path = resolved_locator.rsplit("#", 1)[0] if "#" in resolved_locator else resolved_locator
            if (str(occurrence.get("source") or ""), resolved_path) in excluded_units:
                continue
            explicit_revision = bool(existing_occurrence and isinstance(event.get("atoms"), list))
            source_revision = bool(
                existing_occurrence is not None and _source_revision_changed(existing_occurrence, occurrence)
            )
            is_revision = bool(explicit_revision or source_revision)
            if existing_occurrence and not is_revision:
                continue
            classification_digest = (
                digest(
                    {
                        "kind": "occurrence_classification_revision",
                        "atoms": event.get("atoms") if explicit_revision else None,
                        "source_fields": _source_revision_material(occurrence),
                    }
                )
                if is_revision
                else None
            )
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
                prompt_hash = str(occurrence["prompt_hash"])
                occurrence["raw_object"] = raw_object_reference(prompt_hash)
                pending_raw_objects[prompt_hash] = raw_text
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
        final_live_source_errors = validate_live_source_custody(effective_cursor)
        if final_live_source_errors:
            raise ValueError("live source custody changed: " + "; ".join(final_live_source_errors))
        created_raw_objects: list[Path] = []
        for prompt_hash, raw_text in pending_raw_objects.items():
            destination = paths.raw_objects / raw_object_reference(prompt_hash)
            existed = destination.exists()
            preserve_raw_object(paths, prompt_hash, raw_text)
            if not existed:
                created_raw_objects.append(destination)
        post_raw_live_errors = validate_live_source_custody(effective_cursor)
        if post_raw_live_errors:
            for destination in created_raw_objects:
                with contextlib.suppress(OSError):
                    destination.unlink()
                with contextlib.suppress(OSError):
                    destination.parent.rmdir()
            with contextlib.suppress(OSError):
                paths.raw_objects.rmdir()
            raise ValueError("live source custody changed: " + "; ".join(post_raw_live_errors))
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
            if pending_scan_receipt is not None:
                receipt_path, receipt_bytes = pending_scan_receipt
                _validate_source_scan_receipt_destination(paths, receipt_path)
                receipt_existed = receipt_path.exists()
                if not receipt_path.exists():
                    atomic_write_bytes(receipt_path, receipt_bytes, mode=0o400)
                receipt_errors = _source_scan_receipt_errors(effective_cursor, paths.private_dir)
                if receipt_errors:
                    if not receipt_existed:
                        with contextlib.suppress(OSError):
                            receipt_path.unlink()
                    raise ValueError("invalid materialized source scan receipt: " + "; ".join(receipt_errors))
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
        seal = prompt_authority_seal(snapshot, public=public)
        markdown = render_markdown(public, policy)
        next_marker = private_marker(snapshot, public, seal, paths=paths)
        public_bytes = _json_bytes(public)
        seal_bytes = _json_bytes(seal)
        if len(seal_bytes) > PROMPT_AUTHORITY_SEAL_MAX_BYTES:
            raise ValueError("public prompt authority seal exceeds its hard byte ceiling")
        markdown_bytes = markdown.encode("utf-8")
        marker_bytes = _json_bytes(next_marker)
        changed = False
        if not paths.public_snapshot.exists() or paths.public_snapshot.read_bytes() != public_bytes:
            atomic_write_bytes(paths.public_snapshot, public_bytes, mode=0o644)
            changed = True
        if not paths.public_seal.exists() or paths.public_seal.read_bytes() != seal_bytes:
            atomic_write_bytes(paths.public_seal, seal_bytes, mode=0o644)
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
    seal = load_json(paths.public_seal)
    errors: list[str] = []
    if paths.private_snapshot.exists() and not private:
        errors.append("private prompt checkpoint is malformed")
    if paths.public_snapshot.exists() and not public:
        errors.append("public prompt projection is malformed")
    if paths.public_seal.exists() and not seal:
        errors.append("public prompt authority seal is malformed")
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
    if not seal:
        errors.append("public prompt authority seal is missing")
    elif not _prompt_authority_seal_digest_valid(seal):
        errors.append("public prompt authority seal digest or schema is invalid")
    elif public and not _prompt_authority_seal_matches_public(seal, public):
        errors.append("public prompt authority seal does not match the public projection")
    validation = source.get("validation") or {}
    if not validation.get("ok"):
        errors.extend(str(value) for value in (validation.get("errors") or ["validation failed"]))
    scope = str((source.get("source_scope") or {}).get("scope") or "unknown")
    if require_scope and scope != require_scope:
        errors.append(f"source scope is {scope}; require {require_scope}")
    if require_scope == "all" and (not seal or seal.get("authority_ready") is not True):
        errors.append("public prompt authority seal is not authority-ready for required all scope")
    if private:
        live_cursor, cursor_errors = load_json_strict(paths.cursor)
        errors.extend(cursor_errors)
        errors.extend(validate_cursor_shape(live_cursor, role="live"))
        errors.extend(validate_source_adapter_cursor(live_cursor, receipt_root=paths.private_dir))
        errors.extend(validate_live_source_custody(live_cursor))
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
        rebuilt_seal = prompt_authority_seal(rebuilt, public=rebuilt_public)
        rebuilt_marker = private_marker(rebuilt, rebuilt_public, rebuilt_seal, paths=paths)
        if private != rebuilt_marker:
            errors.append("private journals do not match the compact checkpoint")
        if not public:
            errors.append("public prompt projection is missing")
        elif paths.public_snapshot.read_bytes() != _json_bytes(rebuilt_public):
            errors.append("public prompt projection does not match the private journals")
        if seal and paths.public_seal.read_bytes() != _json_bytes(rebuilt_seal):
            errors.append("public prompt authority seal does not match the private journals")
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
        if seal and paths.public_seal.read_bytes() != _json_bytes(seal):
            errors.append("public prompt authority seal is not canonical")
        expected_markdown = render_markdown(public, load_policy(paths.policy))
        if not paths.public_markdown.exists():
            errors.append("public prompt Markdown is missing")
        elif paths.public_markdown.read_text(encoding="utf-8", errors="replace") != expected_markdown:
            errors.append("public prompt Markdown does not match its projection")
    return errors
