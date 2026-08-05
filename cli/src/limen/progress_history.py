"""Content-addressed work-universe snapshots and arbitrary-window deltas."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ADAPTER_SCHEMA = "limen.progress-history-adapter.v1"
SNAPSHOT_SCHEMA = "limen.progress-history-snapshot.v1"
DELTA_SCHEMA = "limen.progress-history-delta.v1"


class ProgressHistoryError(RuntimeError):
    """Historical input, custody, or comparison is not trustworthy."""


def canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(payload).hexdigest()


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ProgressHistoryError(f"{path.name}:unreadable-or-invalid") from exc
    if not isinstance(value, dict):
        raise ProgressHistoryError(f"{path.name}:root-not-object")
    return value


def _text_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item for item in value):
        raise ProgressHistoryError(f"{field}:nonempty-string-list-required")
    return list(value)


def normalize_adapter(value: dict[str, Any]) -> dict[str, Any]:
    if value.get("schema") != ADAPTER_SCHEMA:
        raise ProgressHistoryError("unsupported-adapter-schema")
    source_id = value.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        raise ProgressHistoryError("adapter-source-id-required")
    terminal_values = value.get("terminal_values", [])
    reopened_values = value.get("reopened_values", [])
    ask_kind_values = value.get("ask_kind_values", [])
    for field, raw in (
        ("terminal_values", terminal_values),
        ("reopened_values", reopened_values),
        ("ask_kind_values", ask_kind_values),
    ):
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise ProgressHistoryError(f"{field}:string-list-required")
    optional_fields = ("verified_field", "actual_field", "kind_field")
    for field in optional_fields:
        if value.get(field) is not None and not isinstance(value.get(field), str):
            raise ProgressHistoryError(f"{field}:string-required")
    return {
        "source_id": source_id,
        "document_paths": _text_list(value.get("document_paths"), "document_paths"),
        "leaf_field": str(value.get("leaf_field") or "leaves"),
        "identity_fields": _text_list(value.get("identity_fields"), "identity_fields"),
        "state_fields": _text_list(value.get("state_fields"), "state_fields"),
        "terminal_values": sorted({str(item).lower() for item in terminal_values}),
        "reopened_values": sorted({str(item).lower() for item in reopened_values}),
        "verified_field": value.get("verified_field"),
        "actual_field": value.get("actual_field"),
        "kind_field": value.get("kind_field"),
        "ask_kind_values": sorted({str(item).lower() for item in ask_kind_values}),
        "timestamp_fields": _text_list(value.get("timestamp_fields", ["created_at"]), "timestamp_fields"),
        "evidence_fields": _text_list(value["evidence_fields"], "evidence_fields")
        if value.get("evidence_fields")
        else [],
    }


def default_adapter_dirs(root: Path) -> list[Path]:
    roots = [root / "config" / "progress-history-sources"]
    extra = os.environ.get("LIMEN_PROGRESS_HISTORY_ADAPTER_DIRS", "")
    roots.extend(Path(item).expanduser() for item in extra.split(os.pathsep) if item.strip())
    return roots


def load_history_adapters(
    root: Path,
    *,
    adapter_dirs: Iterable[Path] | None = None,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    adapters: dict[str, dict[str, Any]] = {}
    failures: list[str] = []
    directories = list(adapter_dirs) if adapter_dirs is not None else default_adapter_dirs(root)
    for directory in directories:
        if not directory.is_dir():
            failures.append("history-adapter-root-unavailable")
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                adapter = normalize_adapter(_read_object(path))
            except ProgressHistoryError as exc:
                failures.append(f"adapter-{sha256(path.name.encode()).hexdigest()[:12]}:{exc}")
                continue
            source_id = str(adapter["source_id"])
            if source_id in adapters:
                failures.append(f"{source_id}:duplicate-history-adapter")
                continue
            adapters[source_id] = adapter
    return adapters, sorted(set(failures))


def _field(row: Mapping[str, Any], candidates: Sequence[str]) -> Any:
    for field in candidates:
        value = row.get(field)
        if value is not None and value != "":
            return value
    return None


def _nested(row: Mapping[str, Any], field: str) -> Any:
    value: Any = row
    for part in field.split("."):
        if not isinstance(value, Mapping) or part not in value:
            return None
        value = value[part]
    return value


def _evidence(row: Mapping[str, Any], fields: Sequence[str]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for field in fields:
        value = _nested(row, field)
        values = value if isinstance(value, list) else [value]
        for item in values:
            if item is None or item == "" or isinstance(item, (dict, list)):
                continue
            rendered = " ".join(str(item).split())[:4096]
            if rendered:
                evidence.append({"field": field, "value": rendered})
    unique = {(item["field"], item["value"]): item for item in evidence}
    return [unique[key] for key in sorted(unique)]


def _timestamp(value: Any) -> str | None:
    if value in {None, ""}:
        return None
    try:
        observed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if observed.tzinfo is None:
        return None
    return observed.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _nonnegative_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return value


def _actual_usage(row: Mapping[str, Any], field: str | None) -> dict[str, int | float | None]:
    raw = row.get(field) if field else None
    source = raw if isinstance(raw, Mapping) else {}
    return {
        "runs": _nonnegative_number(source.get("runs")),
        "input_tokens": _nonnegative_number(source.get("input_tokens")),
        "output_tokens": _nonnegative_number(source.get("output_tokens")),
        "cache_tokens": _nonnegative_number(source.get("cache_tokens")),
        "dollars_usd": _nonnegative_number(source.get("dollars_usd")),
        "elapsed_seconds": _nonnegative_number(source.get("elapsed_seconds")),
        "host_local_seconds": _nonnegative_number(source.get("host_local_seconds")),
    }


def _normalize_leaf(source_id: str, raw: dict[str, Any], adapter: dict[str, Any]) -> dict[str, Any]:
    identity = _field(raw, adapter["identity_fields"])
    if identity is None:
        raise ProgressHistoryError("leaf-identity-missing")
    state = str(_field(raw, adapter["state_fields"]) or "unknown").lower()
    kind_field = adapter.get("kind_field")
    kind = str(raw.get(kind_field) or "unknown").lower() if kind_field else "unknown"
    verified_field = adapter.get("verified_field")
    verified = bool(raw.get(verified_field) is True) if verified_field else False
    opened_at = _field(raw, adapter["timestamp_fields"])
    return {
        "leaf_key": sha256(f"{source_id}\0{identity}".encode()).hexdigest(),
        "source_id": source_id,
        "kind": kind,
        "state": state,
        "terminal": state in adapter["terminal_values"],
        "reopened": state in adapter["reopened_values"],
        "verified_outcome": verified,
        "verified_value_units": 1 if verified else 0,
        "is_ask": kind in adapter["ask_kind_values"],
        "opened_at": _timestamp(opened_at),
        "actual": _actual_usage(raw, adapter.get("actual_field")),
        "evidence": _evidence(raw, adapter["evidence_fields"]),
        "content_sha256": canonical_sha256(raw),
    }


def _tracked_truncation(document: Mapping[str, Any]) -> int:
    total = 0
    for key, value in document.items():
        if key.endswith("_truncated_count") and isinstance(value, int) and not isinstance(value, bool):
            total += max(0, value)
    return total


def _document(root: Path, adapter: dict[str, Any]) -> tuple[dict[str, Any], str] | None:
    for raw in adapter["document_paths"]:
        path = Path(raw).expanduser()
        candidate = path if path.is_absolute() else root / path
        if candidate.is_file():
            return _read_object(candidate), str(raw)
    return None


def collect_history_sources(
    root: Path,
    registry: dict[str, Any],
    adapters: Mapping[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Normalize registered owner documents without a coded source catalog."""

    contributions: list[dict[str, Any]] = []
    failures: list[str] = []
    rows = registry.get("sources") if isinstance(registry, dict) else None
    if not isinstance(rows, list):
        return [], ["source-registry-rows-unavailable"]
    registered = {str(row.get("source_id")): row for row in rows if isinstance(row, dict)}
    for source_id, row in sorted(registered.items()):
        adapter = adapters.get(source_id)
        if adapter is None:
            failures.append(f"{source_id}:history-adapter-missing")
            continue
        resolved = _document(root, adapter)
        if resolved is None:
            failures.append(f"{source_id}:history-document-unavailable")
            continue
        document, document_path = resolved
        report = document.get("source_report")
        if not isinstance(report, dict) or report.get("source_id") != source_id:
            failures.append(f"{source_id}:history-document-report-invalid")
            continue
        registry_hash = row.get("content_sha256")
        if registry_hash is not None and report.get("content_sha256") != registry_hash:
            failures.append(f"{source_id}:history-document-source-hash-mismatch")
            continue
        leaves_raw = document.get(adapter["leaf_field"])
        if not isinstance(leaves_raw, list):
            failures.append(f"{source_id}:history-leaf-field-invalid")
            continue
        leaves: list[dict[str, Any]] = []
        leaf_failures = 0
        for raw in leaves_raw:
            if not isinstance(raw, dict):
                leaf_failures += 1
                continue
            try:
                leaves.append(_normalize_leaf(source_id, raw, adapter))
            except ProgressHistoryError:
                leaf_failures += 1
        leaves.sort(key=lambda item: str(item["leaf_key"]))
        declared = report.get("normalized_leaf_count")
        truncation = _tracked_truncation(document)
        count_exact = isinstance(declared, int) and declared == len(leaves) + truncation
        exhaustive = bool(
            row.get("semantic_status") == "ready"
            and row.get("exhaustive") is True
            and report.get("exhaustive") is True
            and count_exact
            and truncation == 0
            and leaf_failures == 0
        )
        if not exhaustive:
            failures.append(f"{source_id}:history-contribution-partial")
        contributions.append(
            {
                "source_id": source_id,
                "owner": row.get("owner"),
                "cursor": row.get("cursor"),
                "source_content_sha256": row.get("content_sha256"),
                "document_path_hash": sha256(document_path.encode()).hexdigest(),
                "document_content_sha256": canonical_sha256(document),
                "exhaustive": exhaustive,
                "declared_leaf_count": declared,
                "known_leaf_count": len(leaves),
                "truncated_leaf_count": truncation,
                "leaf_failure_count": leaf_failures,
                "leaves": leaves,
            }
        )
    for source_id in sorted(set(adapters) - set(registered)):
        failures.append(f"{source_id}:history-adapter-source-unregistered")
    return contributions, sorted(set(failures))


def _usage_totals(leaves: Sequence[dict[str, Any]]) -> dict[str, int | float]:
    fields = (
        "runs",
        "input_tokens",
        "output_tokens",
        "cache_tokens",
        "dollars_usd",
        "elapsed_seconds",
        "host_local_seconds",
    )
    return {
        field: round(sum(float((leaf.get("actual") or {}).get(field) or 0) for leaf in leaves), 8) for field in fields
    }


def build_progress_snapshot(
    registry: dict[str, Any],
    contributions: Sequence[dict[str, Any]],
    selection: dict[str, Any],
    *,
    generated_at: datetime | None = None,
    failures: Sequence[str] = (),
) -> dict[str, Any]:
    observed = (generated_at or datetime.now(UTC)).astimezone(UTC)
    leaves = sorted(
        [dict(leaf) for source in contributions for leaf in source.get("leaves") or []],
        key=lambda row: str(row["leaf_key"]),
    )
    leaf_keys = [str(leaf["leaf_key"]) for leaf in leaves]
    source_rows = [
        {key: value for key, value in source.items() if key != "leaves"}
        for source in sorted(contributions, key=lambda row: str(row["source_id"]))
    ]
    all_failures = sorted(set(failures))
    if len(set(leaf_keys)) != len(leaf_keys):
        all_failures.append("duplicate-history-leaf-key")
    registry_ready = registry.get("semantic_status") == "ready"
    exhaustive = bool(
        registry_ready and source_rows and all(row["exhaustive"] for row in source_rows) and not all_failures
    )
    summary = {
        "source_count": len(source_rows),
        "leaf_count": len(leaves),
        "active_count": sum(not bool(leaf["terminal"]) for leaf in leaves),
        "terminal_count": sum(bool(leaf["terminal"]) for leaf in leaves),
        "reopened_count": sum(bool(leaf["reopened"]) for leaf in leaves),
        "verified_value_units": sum(int(leaf["verified_value_units"]) for leaf in leaves),
        "ask_count": sum(bool(leaf["is_ask"]) for leaf in leaves),
        "verified_ask_outcome_count": sum(
            bool(leaf["is_ask"] and leaf["verified_outcome"] and leaf["terminal"]) for leaf in leaves
        ),
        "actual": _usage_totals(leaves),
        "coverage_debt": int((registry.get("summary") or {}).get("coverage_debt") or 0)
        + sum(not bool(row["exhaustive"]) for row in source_rows)
        + len(all_failures),
    }
    material = {
        "schema": SNAPSHOT_SCHEMA,
        "generated_at": observed.isoformat().replace("+00:00", "Z"),
        "exhaustive": exhaustive,
        "registry_content_sha256": registry.get("content_sha256"),
        "sources": source_rows,
        "summary": summary,
        "selection": selection,
        "failures": all_failures,
        "leaves": leaves,
    }
    return {**material, "snapshot_id": canonical_sha256(material)}


def persist_snapshot(snapshot: dict[str, Any], directory: Path) -> Path:
    snapshot_id = str(snapshot.get("snapshot_id") or "")
    material = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
    if snapshot.get("schema") != SNAPSHOT_SCHEMA or snapshot_id != canonical_sha256(material):
        raise ProgressHistoryError("snapshot-content-address-invalid")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / f"{snapshot_id}.json"
    payload = (json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()
    if target.exists():
        if target.read_bytes() != payload:
            raise ProgressHistoryError("snapshot-address-collision")
        return target
    descriptor, temporary = tempfile.mkstemp(dir=directory, prefix=".snapshot-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != payload:
                raise ProgressHistoryError("snapshot-address-collision")
        directory_fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        try:
            Path(temporary).unlink()
        except FileNotFoundError:
            pass
    return target


def load_snapshots(directory: Path) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    if not directory.is_dir():
        return snapshots
    for path in sorted(directory.glob("*.json")):
        snapshot = _read_object(path)
        snapshot_id = str(snapshot.get("snapshot_id") or "")
        material = {key: value for key, value in snapshot.items() if key != "snapshot_id"}
        if path.stem != snapshot_id or snapshot_id != canonical_sha256(material):
            raise ProgressHistoryError(f"{path.name}:snapshot-content-address-invalid")
        snapshots.append(snapshot)
    return sorted(snapshots, key=lambda row: (str(row.get("generated_at")), str(row.get("snapshot_id"))))


def snapshot_at_or_before(snapshots: Sequence[dict[str, Any]], at: datetime) -> dict[str, Any] | None:
    boundary = at.astimezone(UTC)
    eligible = []
    for snapshot in snapshots:
        observed = _timestamp(snapshot.get("generated_at"))
        if observed and datetime.fromisoformat(observed.replace("Z", "+00:00")) <= boundary:
            eligible.append(snapshot)
    return eligible[-1] if eligible else None


def compare_snapshots(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    if baseline.get("schema") != SNAPSHOT_SCHEMA or current.get("schema") != SNAPSHOT_SCHEMA:
        raise ProgressHistoryError("snapshot-schema-mismatch")
    start = datetime.fromisoformat(str(baseline["generated_at"]).replace("Z", "+00:00"))
    end = datetime.fromisoformat(str(current["generated_at"]).replace("Z", "+00:00"))
    if end < start:
        raise ProgressHistoryError("historical-window-reversed")
    before = {str(row["leaf_key"]): row for row in baseline.get("leaves") or []}
    after = {str(row["leaf_key"]): row for row in current.get("leaves") or []}
    arrivals = sorted(set(after) - set(before))
    disappeared = sorted(set(before) - set(after))
    shared = sorted(set(before) & set(after))
    closures = [key for key in shared if not before[key]["terminal"] and after[key]["terminal"]]
    reopened = [
        key
        for key in shared
        if (before[key]["terminal"] and not after[key]["terminal"]) or bool(after[key]["reopened"])
    ]
    aged = [key for key in shared if not before[key]["terminal"] and not after[key]["terminal"]]
    elapsed = max(0.0, (end - start).total_seconds())
    before_summary = baseline.get("summary") or {}
    after_summary = current.get("summary") or {}
    before_actual = before_summary.get("actual") or {}
    after_actual = after_summary.get("actual") or {}
    actual_delta = {
        field: round(float(after_actual.get(field) or 0) - float(before_actual.get(field) or 0), 8)
        for field in set(before_actual) | set(after_actual)
    }
    value_delta = int(after_summary.get("verified_value_units") or 0) - int(
        before_summary.get("verified_value_units") or 0
    )
    ask_delta = int(after_summary.get("ask_count") or 0) - int(before_summary.get("ask_count") or 0)
    outcome_delta = int(after_summary.get("verified_ask_outcome_count") or 0) - int(
        before_summary.get("verified_ask_outcome_count") or 0
    )
    material = {
        "schema": DELTA_SCHEMA,
        "from_snapshot_id": baseline.get("snapshot_id"),
        "to_snapshot_id": current.get("snapshot_id"),
        "window_seconds": elapsed,
        "arrivals": len(arrivals),
        "closures": len(closures),
        "reopened_debt": len(set(reopened)),
        "disappeared_without_terminal_receipt": len(disappeared),
        "aged_active_leaves": len(aged),
        "aging_seconds_added": round(elapsed * len(aged), 3),
        "actual_spend_delta": actual_delta,
        "actual_spend_regression": any(value < 0 for value in actual_delta.values()),
        "verified_value_delta": value_delta,
        "ask_arrival_delta": ask_delta,
        "verified_ask_outcome_delta": outcome_delta,
        "ask_vs_outcome_gap_delta": ask_delta - outcome_delta,
        "coverage_debt_delta": int(after_summary.get("coverage_debt") or 0)
        - int(before_summary.get("coverage_debt") or 0),
    }
    return {**material, "delta_id": canonical_sha256(material)}
