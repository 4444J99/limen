#!/usr/bin/env python3
"""Run the isolated, resource-bounded prompt-atom activation canary.

The canary deliberately has no useful implicit paths. A caller must declare one
isolated sandbox containing HOME, every private/public output, and the receipt.
It runs the exact all-history scanner command twice with a hard five-work-unit
ceiling, then proves that the second run did not append, reclassify, or change any
canonical byte.

The receipt is redacted by construction: it contains a caller-safe label,
numeric counts/timings, and content hashes, never prompt text or filesystem paths.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts" / "prompt-atom-ledger.py"
MAX_WORK_UNITS = 5
DEFAULT_TIMEOUT_SECONDS = 180
MAX_CAPTURE_BYTES = 1024 * 1024
MAX_ARTIFACT_FILES = 100_000
MAX_ARTIFACT_ENTRIES = 200_000
SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SCANNER_SUMMARY = re.compile(
    r"appended\s+(?P<occurrences>\d+)/(?P<atoms>\d+)/(?P<outcomes>\d+);\s+"
    r"changed=(?P<changed>true|false)"
)


class CanaryFailure(RuntimeError):
    """A bounded canary predicate did not hold."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stream_file_digest(path: Path) -> tuple[int, str]:
    hasher = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            total += len(chunk)
            hasher.update(chunk)
    return total, hasher.hexdigest()


def file_metric(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "bytes": 0, "sha256": sha256_bytes(b"")}
    size, file_hash = stream_file_digest(path)
    return {"exists": True, "bytes": size, "sha256": file_hash}


def tree_metric(root: Path) -> dict[str, Any]:
    """Hash a private object tree without putting its paths in the receipt."""

    rows: list[tuple[str, int, str]] = []
    total = 0
    if root.exists():
        paths: list[Path] = []
        for entry_count, candidate in enumerate(root.rglob("*"), start=1):
            if entry_count > MAX_ARTIFACT_ENTRIES:
                raise CanaryFailure("private_raw_object_tree_exceeds_entry_bound")
            if not candidate.is_file():
                continue
            if len(paths) >= MAX_ARTIFACT_FILES:
                raise CanaryFailure("private_raw_object_count_exceeds_bound")
            resolved = candidate.resolve()
            resolved_root = root.resolve()
            if resolved_root not in resolved.parents:
                raise CanaryFailure("private_raw_object_symlink_escape")
            paths.append(candidate)
        for path in sorted(paths):
            size, file_hash = stream_file_digest(path)
            relative = str(path.relative_to(root))
            rows.append((relative, size, file_hash))
            total += size
    material = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
    return {"exists": root.exists(), "files": len(rows), "bytes": total, "sha256": sha256_bytes(material)}


def artifact_metrics(
    private_root: Path,
    public_snapshot: Path,
    public_markdown: Path,
) -> dict[str, dict[str, Any]]:
    private = private_root / "prompt-atoms"
    return {
        "event_journal": file_metric(private / "prompt-events.jsonl"),
        "outcome_journal": file_metric(private / "prompt-atom-outcomes.jsonl"),
        "source_cursor": file_metric(private / "source-cursor.json"),
        "private_checkpoint": file_metric(private / "prompt-atom-ledger.json"),
        "private_raw_objects": tree_metric(private / "raw-objects"),
        "public_snapshot": file_metric(public_snapshot),
        "public_markdown": file_metric(public_markdown),
    }


def load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise CanaryFailure(f"{label}_missing_or_malformed") from exc
    if not isinstance(value, dict):
        raise CanaryFailure(f"{label}_not_an_object")
    return value


def journal_counts(path: Path) -> dict[str, int]:
    counts = {"rows": 0, "reclassifications": 0, "atoms": 0}
    if not path.exists():
        return counts
    try:
        with path.open(encoding="utf-8", errors="strict") as handle:
            for line in handle:
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("non-object journal row")
                counts["rows"] += 1
                counts["reclassifications"] += int(bool(value.get("revision_of")))
                atoms = value.get("atoms")
                counts["atoms"] += len(atoms) if isinstance(atoms, list) else 0
    except (OSError, UnicodeError, ValueError) as exc:
        raise CanaryFailure("event_journal_missing_or_malformed") from exc
    return counts


def outcome_count(path: Path) -> int:
    if not path.exists():
        return 0
    count = 0
    try:
        with path.open(encoding="utf-8", errors="strict") as handle:
            for line in handle:
                if not line.strip():
                    continue
                if not isinstance(json.loads(line), dict):
                    raise ValueError("non-object outcome row")
                count += 1
    except (OSError, UnicodeError, ValueError) as exc:
        raise CanaryFailure("outcome_journal_missing_or_malformed") from exc
    return count


def run_bounded(command: list[str], env: dict[str, str], timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            start_new_session=True,
        )
    except OSError as exc:
        return {
            "returncode": 127,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "stdout": "",
            "stderr": str(exc),
        }

    stdout = bytearray()
    stderr = bytearray()
    overflow: list[str] = []
    overflow_lock = threading.Lock()

    def terminate() -> None:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            with contextlib.suppress(ProcessLookupError):
                process.kill()

    def reader(stream: Any, target: bytearray, label: str) -> None:
        try:
            while True:
                chunk = stream.read(64 * 1024)
                if not chunk:
                    return
                if len(target) + len(chunk) > MAX_CAPTURE_BYTES:
                    with overflow_lock:
                        if not overflow:
                            overflow.append(label)
                            terminate()
                    return
                target.extend(chunk)
        except (OSError, ValueError):
            return
        finally:
            with contextlib.suppress(OSError, ValueError):
                stream.close()

    if process.stdout is None or process.stderr is None:
        terminate()
        return {
            "returncode": 125,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "stdout": "",
            "stderr": "subprocess pipes unavailable",
        }
    threads = [
        threading.Thread(target=reader, args=(process.stdout, stdout, "stdout"), daemon=True),
        threading.Thread(target=reader, args=(process.stderr, stderr, "stderr"), daemon=True),
    ]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout
    timed_out = False
    while process.poll() is None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            terminate()
            break
        try:
            process.wait(timeout=min(0.05, remaining))
        except subprocess.TimeoutExpired:
            continue
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(timeout=1.0)
    for thread in threads:
        thread.join(timeout=1.0)
    returncode = 124 if timed_out else (125 if overflow else process.returncode)
    return {
        "returncode": returncode,
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "stdout": bytes(stdout).decode("utf-8", errors="replace"),
        "stderr": (
            f"{overflow[0]} exceeded {MAX_CAPTURE_BYTES} byte capture bound"
            if overflow
            else bytes(stderr).decode("utf-8", errors="replace")
        ),
    }


def scanner_summary(output: str) -> dict[str, Any]:
    match = SCANNER_SUMMARY.search(output)
    if match is None:
        return {"occurrences": None, "atoms": None, "outcomes": None, "changed": None}
    return {
        "occurrences": int(match.group("occurrences")),
        "atoms": int(match.group("atoms")),
        "outcomes": int(match.group("outcomes")),
        "changed": match.group("changed") == "true",
    }


def fixed_failures(cursor: dict[str, Any], public: dict[str, Any], cap: int) -> list[str]:
    failures: list[str] = []
    if int(cursor.get("work_units_used") or 0) != cap:
        failures.append("first_pass_did_not_use_exact_cap")
    if cursor.get("scope") != "all" or cursor.get("target_scope") != "all":
        failures.append("first_pass_scope_not_all")
    if int(cursor.get("pending_files") or 0):
        failures.append("first_pass_has_pending_units")
    if cursor.get("source_errors"):
        failures.append("first_pass_has_source_errors")
    if int(cursor.get("unsupported_source_count") or 0):
        failures.append("first_pass_has_unsupported_sources")
    if cursor.get("adapter_gaps") or cursor.get("adapter_gap_routes"):
        failures.append("first_pass_has_adapter_gaps")
    if cursor.get("all_baseline_complete") is not True:
        failures.append("first_pass_baseline_incomplete")
    source_scope = public.get("source_scope") if isinstance(public.get("source_scope"), dict) else {}
    if source_scope.get("scope") != "all" or source_scope.get("target_scope") != "all":
        failures.append("public_projection_scope_not_all")
    validation = public.get("validation") if isinstance(public.get("validation"), dict) else {}
    if validation.get("ok") is not True or validation.get("errors"):
        failures.append("public_projection_validation_failed")
    return failures


def safe_label(value: str) -> str:
    if not SAFE_LABEL.fullmatch(value):
        raise CanaryFailure("unsafe_canary_label")
    return value


def require_isolated_paths(
    sandbox_root: Path,
    home: Path,
    private_root: Path,
    public_snapshot: Path,
    public_markdown: Path,
    receipt: Path,
) -> None:
    if sandbox_root.is_symlink():
        raise CanaryFailure("sandbox_root_must_not_be_a_symlink")
    try:
        sandbox = sandbox_root.resolve(strict=True)
    except OSError as exc:
        raise CanaryFailure("sandbox_root_missing") from exc
    if not sandbox.is_dir():
        raise CanaryFailure("sandbox_root_not_a_directory")
    actual_home = Path.home().resolve()
    repo = ROOT.resolve()

    def overlaps(left: Path, right: Path) -> bool:
        return left == right or left in right.parents or right in left.parents

    if overlaps(sandbox, repo):
        raise CanaryFailure("sandbox_overlaps_live_repository")
    if overlaps(sandbox, actual_home):
        raise CanaryFailure("sandbox_overlaps_real_home")

    named_paths = {
        "source_home": home,
        "private_root": private_root,
        "public_snapshot": public_snapshot,
        "public_markdown": public_markdown,
        "receipt": receipt,
    }
    resolved = {name: path.resolve(strict=False) for name, path in named_paths.items()}
    for name, path in resolved.items():
        if path == sandbox or sandbox not in path.parents:
            raise CanaryFailure(f"{name}_escapes_sandbox")
        if overlaps(path, repo):
            raise CanaryFailure(f"{name}_overlaps_live_repository")
        if overlaps(path, actual_home):
            raise CanaryFailure(f"{name}_overlaps_real_home")
    if len(set(resolved.values())) != len(resolved):
        raise CanaryFailure("output_paths_are_not_distinct")
    if not resolved["source_home"].is_dir():
        raise CanaryFailure("isolated_home_missing")


def atomic_receipt(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode()
    with tempfile.NamedTemporaryFile(prefix=f".{path.name}.", dir=path.parent, delete=False) as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sandbox-root",
        type=Path,
        required=True,
        help="existing isolated root containing every source, output, and receipt path",
    )
    parser.add_argument("--home", type=Path, required=True, help="isolated fixture HOME")
    parser.add_argument("--private-root", type=Path, required=True, help="isolated private corpus root")
    parser.add_argument("--public-snapshot", type=Path, required=True, help="isolated redacted JSON output")
    parser.add_argument("--public-markdown", type=Path, required=True, help="isolated redacted Markdown output")
    parser.add_argument("--receipt", type=Path, required=True, help="redacted canary JSON receipt")
    parser.add_argument("--label", default="prompt-atom-v2-canary", help="safe receipt label")
    parser.add_argument("--cap", type=int, default=MAX_WORK_UNITS, help="work-unit cap; maximum 5")
    parser.add_argument("--nice", type=int, default=10, help="non-negative nice adjustment")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="seconds per subprocess")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures: list[str] = []
    try:
        label = safe_label(args.label)
        if not 1 <= args.cap <= MAX_WORK_UNITS:
            raise CanaryFailure("cap_outside_hard_ceiling")
        if not 0 <= args.nice <= 19:
            raise CanaryFailure("nice_outside_safe_range")
        if not 1 <= args.timeout <= 3600:
            raise CanaryFailure("timeout_outside_safe_range")
        sandbox_root = args.sandbox_root
        home = args.home.resolve()
        private_root = args.private_root.resolve()
        public_snapshot = args.public_snapshot.resolve()
        public_markdown = args.public_markdown.resolve()
        receipt_path = args.receipt.resolve()
        require_isolated_paths(
            sandbox_root,
            home,
            private_root,
            public_snapshot,
            public_markdown,
            receipt_path,
        )
        nice_binary = shutil.which("nice")
        if nice_binary is None:
            raise CanaryFailure("nice_binary_missing")
    except CanaryFailure as exc:
        print(f"prompt-atom-canary: FAIL — {exc}", file=sys.stderr)
        return 2

    env = os.environ.copy()
    env["LIMEN_ROOT"] = str(ROOT)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [
        nice_binary,
        "-n",
        str(args.nice),
        sys.executable,
        str(SCANNER),
        "--root",
        str(ROOT),
        "--source-home",
        str(home),
        "--private-root",
        str(private_root),
        "--public-snapshot",
        str(public_snapshot),
        "--public-markdown",
        str(public_markdown),
        "--scan",
        "--all",
        "--max-files",
        str(args.cap),
        "--write",
    ]
    private_dir = private_root / "prompt-atoms"
    event_journal = private_dir / "prompt-events.jsonl"
    outcome_journal = private_dir / "prompt-atom-outcomes.jsonl"
    cursor_path = private_dir / "source-cursor.json"

    receipt: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "label": label,
        "status": "fail",
        "scanner": "scripts/prompt-atom-ledger.py",
        "scanner_version": 2,
        "work_unit_cap": args.cap,
        "hard_max_work_units": MAX_WORK_UNITS,
        "nice_priority_requested": args.nice,
        "timeout_seconds_per_process": args.timeout,
        "passes": [],
        "failures": failures,
    }

    first = run_bounded(command, env, args.timeout)
    first_summary = scanner_summary(str(first["stdout"]))
    receipt["passes"].append(
        {
            "name": "first",
            "returncode": first["returncode"],
            "elapsed_ms": first["elapsed_ms"],
            "scanner_summary": first_summary,
        }
    )
    if first["returncode"] != 0:
        failures.append("first_scanner_failed")
    try:
        first_cursor = load_object(cursor_path, "source_cursor")
        first_public = load_object(public_snapshot, "public_snapshot")
        failures.extend(fixed_failures(first_cursor, first_public, args.cap))
        first_metrics = artifact_metrics(private_root, public_snapshot, public_markdown)
        first_journal = journal_counts(event_journal)
        first_outcomes = outcome_count(outcome_journal)
        receipt["first_pass"] = {
            "work_units_used": int(first_cursor.get("work_units_used") or 0),
            "scope": first_cursor.get("scope"),
            "target_scope": first_cursor.get("target_scope"),
            "pending_units": int(first_cursor.get("pending_files") or 0),
            "source_errors": len(first_cursor.get("source_errors") or []),
            "adapter_gaps": len(first_cursor.get("adapter_gaps") or []),
            "occurrences": int((first_public.get("coverage") or {}).get("occurrences") or 0),
            "atoms": int((first_public.get("coverage") or {}).get("atoms") or 0),
            "event_rows": first_journal["rows"],
            "outcome_rows": first_outcomes,
        }
        receipt["artifacts_after_first"] = first_metrics
    except CanaryFailure as exc:
        failures.append(str(exc))

    if failures:
        receipt["failures"] = list(dict.fromkeys(failures))
        atomic_receipt(receipt_path, receipt)
        print(f"prompt-atom-canary: FAIL — {', '.join(receipt['failures'])}", file=sys.stderr)
        return 1

    second = run_bounded(command, env, args.timeout)
    second_summary = scanner_summary(str(second["stdout"]))
    receipt["passes"].append(
        {
            "name": "second",
            "returncode": second["returncode"],
            "elapsed_ms": second["elapsed_ms"],
            "scanner_summary": second_summary,
        }
    )
    if second["returncode"] != 0:
        failures.append("second_scanner_failed")

    try:
        second_metrics = artifact_metrics(private_root, public_snapshot, public_markdown)
        second_journal = journal_counts(event_journal)
        second_outcomes = outcome_count(outcome_journal)
        journal_delta = {
            "event_rows": second_journal["rows"] - first_journal["rows"],
            "atoms": second_journal["atoms"] - first_journal["atoms"],
            "reclassifications": second_journal["reclassifications"] - first_journal["reclassifications"],
            "outcomes": second_outcomes - first_outcomes,
        }
        receipt["second_pass"] = {
            "event_row_delta": journal_delta["event_rows"],
            "atom_delta": journal_delta["atoms"],
            "outcome_delta": journal_delta["outcomes"],
            "reclassification_delta": journal_delta["reclassifications"],
        }
        receipt["artifacts_after_second"] = second_metrics
        if any(journal_delta.values()):
            failures.append("second_pass_journal_growth")
        if second_summary["occurrences"] not in {0, None}:
            failures.append("second_pass_appended_occurrences")
        if second_summary["atoms"] not in {0, None}:
            failures.append("second_pass_appended_atoms")
        if second_summary["outcomes"] not in {0, None}:
            failures.append("second_pass_appended_outcomes")
        if second_summary["changed"] is not False:
            failures.append("second_pass_reported_change")
        if first_metrics != second_metrics:
            failures.append("second_pass_bytes_changed")
    except CanaryFailure as exc:
        failures.append(str(exc))

    check_command = [
        nice_binary,
        "-n",
        str(args.nice),
        sys.executable,
        str(SCANNER),
        "--root",
        str(ROOT),
        "--private-root",
        str(private_root),
        "--public-snapshot",
        str(public_snapshot),
        "--public-markdown",
        str(public_markdown),
        "--check",
        "--require-scope",
        "all",
    ]
    checked = run_bounded(check_command, env, args.timeout)
    receipt["verification"] = {
        "returncode": checked["returncode"],
        "elapsed_ms": checked["elapsed_ms"],
    }
    if checked["returncode"] != 0:
        failures.append("authoritative_check_failed")

    receipt["failures"] = list(dict.fromkeys(failures))
    receipt["status"] = "pass" if not failures else "fail"
    atomic_receipt(receipt_path, receipt)
    if failures:
        print(f"prompt-atom-canary: FAIL — {', '.join(receipt['failures'])}", file=sys.stderr)
        return 1
    print(
        "prompt-atom-canary: PASS — five bounded work units; "
        "second pass appended/reclassified zero and changed no canonical bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
