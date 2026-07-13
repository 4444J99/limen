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
CLI_SRC = ROOT / "cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from limen.prompt_sources import (  # noqa: E402
    PROMPT_SOURCE_SCANNER_VERSION,
    source_adapter_contract,
)


SCANNER = ROOT / "scripts" / "prompt-atom-ledger.py"
CANARY_CODE_PATHS = (
    Path(__file__).resolve(),
    SCANNER,
    ROOT / "scripts" / "prompt-lifecycle-ledger.py",
    ROOT / "cli" / "src" / "limen" / "prompt_corpus.py",
    ROOT / "cli" / "src" / "limen" / "prompt_sources.py",
    ROOT / "docs" / "prompt-corpus-policy.json",
)
REQUIRED_CANARY_FAMILIES = (
    "codex-sessions",
    "claude-projects",
    "gemini-tmp",
    "opencode-db",
    "agy-cli-conversations",
)
MAX_WORK_UNITS = 5
DEFAULT_TIMEOUT_SECONDS = 180
MAX_CAPTURE_BYTES = 1024 * 1024
MAX_ARTIFACT_FILES = 100_000
MAX_ARTIFACT_ENTRIES = 200_000
SAFE_LABEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
SCANNER_SUMMARY = re.compile(
    r"appended\s+(?P<occurrences>\d+)/(?P<atoms>\d+)/(?P<outcomes>\d+);\s+"
    r"changed=(?P<changed>true|false);\s+work_units=(?P<work_units>\d+)"
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


def exact_head_code_identity() -> dict[str, Any]:
    """Bind the canary receipt to the checked-out implementation bytes and Git HEAD."""

    relative_paths = [str(path.relative_to(ROOT)) for path in CANARY_CODE_PATHS]
    try:
        head = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CanaryFailure("git_head_identity_unavailable") from exc
    if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", head) is None:
        raise CanaryFailure("git_head_identity_malformed")
    rows = []
    matches_git_head = True
    for path, relative in zip(CANARY_CODE_PATHS, relative_paths, strict=True):
        if path.is_symlink():
            raise CanaryFailure("canary_code_file_must_not_be_a_symlink")
        metric = file_metric(path)
        if not metric["exists"]:
            raise CanaryFailure("canary_code_file_missing")
        try:
            head_result = subprocess.run(
                ["git", "rev-parse", f"{head}:{relative}"],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            head_blob = head_result.stdout.strip() if head_result.returncode == 0 else ""
            working_blob = subprocess.run(
                ["git", "hash-object", "--no-filters", "--", relative],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
        except (OSError, subprocess.SubprocessError) as exc:
            raise CanaryFailure("git_head_identity_unavailable") from exc
        if re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", working_blob) is None:
            raise CanaryFailure("git_blob_identity_malformed")
        if head_blob and re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", head_blob) is None:
            raise CanaryFailure("git_blob_identity_malformed")
        matches_git_head = matches_git_head and bool(head_blob) and working_blob == head_blob
        rows.append((relative, metric["bytes"], metric["sha256"]))
    return {
        "git_head": head,
        "code_sha256": sha256_bytes(json.dumps(rows, separators=(",", ":")).encode()),
        "matches_git_head": matches_git_head,
    }


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
    public_seal: Path,
) -> dict[str, dict[str, Any]]:
    private = private_root / "prompt-atoms"
    return {
        "event_journal": file_metric(private / "prompt-events.jsonl"),
        "outcome_journal": file_metric(private / "prompt-atom-outcomes.jsonl"),
        "source_cursor": file_metric(private / "source-cursor.json"),
        "private_checkpoint": file_metric(private / "prompt-atom-ledger.json"),
        "private_raw_objects": tree_metric(private / "raw-objects"),
        "private_source_scan_receipts": tree_metric(private / "source-scan-receipts"),
        "public_snapshot": file_metric(public_snapshot),
        "public_markdown": file_metric(public_markdown),
        "public_seal": file_metric(public_seal),
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
        return {
            "occurrences": None,
            "atoms": None,
            "outcomes": None,
            "changed": None,
            "work_units": None,
        }
    return {
        "occurrences": int(match.group("occurrences")),
        "atoms": int(match.group("atoms")),
        "outcomes": int(match.group("outcomes")),
        "changed": match.group("changed") == "true",
        "work_units": int(match.group("work_units")),
    }


def fixed_failures(
    cursor: dict[str, Any],
    public: dict[str, Any],
    cap: int,
    first_summary: dict[str, Any],
    expected_contract: dict[str, Any],
) -> list[str]:
    failures: list[str] = []
    if first_summary["work_units"] != cap:
        failures.append("first_pass_did_not_use_exact_cap")
    if first_summary["changed"] is not True:
        failures.append("first_pass_did_not_report_fresh_change")
    if not isinstance(first_summary["occurrences"], int) or first_summary["occurrences"] <= 0:
        failures.append("first_pass_appended_no_occurrences")
    if not isinstance(first_summary["atoms"], int) or first_summary["atoms"] <= 0:
        failures.append("first_pass_appended_no_atoms")
    if cursor.get("scope") != "all" or cursor.get("target_scope") != "all":
        failures.append("first_pass_scope_not_all")
    if cursor.get("scanner_version") != PROMPT_SOURCE_SCANNER_VERSION:
        failures.append("first_pass_scanner_version_mismatch")
    if cursor.get("source_adapter_contract") != expected_contract:
        failures.append("first_pass_source_contract_mismatch")
    if int(cursor.get("pending_files") or 0):
        failures.append("first_pass_has_pending_units")
    if cursor.get("source_errors"):
        failures.append("first_pass_has_source_errors")
    if int(cursor.get("unsupported_source_count") or 0):
        failures.append("first_pass_has_unsupported_sources")
    if int(cursor.get("unresolved_unit_count") or 0):
        failures.append("first_pass_has_unresolved_source_units")
    if cursor.get("adapter_gaps") or cursor.get("adapter_gap_routes"):
        failures.append("first_pass_has_adapter_gaps")
    if cursor.get("all_baseline_complete") is not True:
        failures.append("first_pass_baseline_incomplete")
    families = cursor.get("source_families")
    expected_family_row = {
        "discovered": 1,
        "converged": 1,
        "adapted": 0,
        "excluded": 0,
        "pending": 0,
        "errors": 0,
        "unsupported": 0,
    }
    active_families = {
        str(name): {key: int((counts or {}).get(key) or 0) for key in expected_family_row}
        for name, counts in (families or {}).items()
        if isinstance(name, str)
        and isinstance(counts, dict)
        and any(int(counts.get(key) or 0) for key in expected_family_row)
    }
    if active_families != {name: expected_family_row for name in REQUIRED_CANARY_FAMILIES}:
        failures.append("first_pass_required_family_coverage_mismatch")
    source_scope = public.get("source_scope") if isinstance(public.get("source_scope"), dict) else {}
    if source_scope.get("scope") != "all" or source_scope.get("target_scope") != "all":
        failures.append("public_projection_scope_not_all")
    if source_scope.get("scanner_version") != PROMPT_SOURCE_SCANNER_VERSION:
        failures.append("public_projection_scanner_version_mismatch")
    if source_scope.get("source_adapter_contract") != expected_contract:
        failures.append("public_projection_source_contract_mismatch")
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
    public_seal: Path,
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
        "public_seal": public_seal,
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
    parser.add_argument("--public-seal", type=Path, required=True, help="isolated counts/hash-only seal output")
    parser.add_argument("--receipt", type=Path, required=True, help="redacted canary JSON receipt")
    parser.add_argument("--label", default="prompt-atom-v2-canary", help="safe receipt label")
    parser.add_argument("--cap", type=int, default=MAX_WORK_UNITS, help="work-unit cap; maximum 5")
    parser.add_argument("--nice", type=int, default=10, help="non-negative nice adjustment")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="seconds per subprocess")
    parser.add_argument(
        "--allow-dirty-code",
        action="store_true",
        help="test-only escape hatch; receipt remains marked as not exact-head",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    failures: list[str] = []
    code_identity: dict[str, Any] = {}
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
        public_seal = args.public_seal.resolve()
        receipt_path = args.receipt.resolve()
        require_isolated_paths(
            sandbox_root,
            home,
            private_root,
            public_snapshot,
            public_markdown,
            public_seal,
            receipt_path,
        )
        nice_binary = shutil.which("nice")
        if nice_binary is None:
            raise CanaryFailure("nice_binary_missing")
        canonical_outputs = (
            private_root / "prompt-atoms",
            public_snapshot,
            public_markdown,
            public_seal,
            receipt_path,
        )
        if any(os.path.lexists(path) for path in canonical_outputs):
            raise CanaryFailure("canary_outputs_must_be_fresh")
        code_identity = exact_head_code_identity()
        if not code_identity["matches_git_head"] and not args.allow_dirty_code:
            raise CanaryFailure("canary_code_does_not_match_git_head")
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
        "--public-seal",
        str(public_seal),
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

    expected_contract = source_adapter_contract()
    receipt: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "label": label,
        "status": "fail",
        "scanner": "scripts/prompt-atom-ledger.py",
        "scanner_version": PROMPT_SOURCE_SCANNER_VERSION,
        "git_head": code_identity["git_head"],
        "code_sha256": code_identity["code_sha256"],
        "code_matches_git_head": code_identity["matches_git_head"],
        "source_adapter_contract": {
            "version": expected_contract["version"],
            "digest": expected_contract["digest"],
        },
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
        failures.extend(fixed_failures(first_cursor, first_public, args.cap, first_summary, expected_contract))
        first_metrics = artifact_metrics(private_root, public_snapshot, public_markdown, public_seal)
        first_journal = journal_counts(event_journal)
        first_outcomes = outcome_count(outcome_journal)
        receipt["first_pass"] = {
            "work_units_used": int(first_summary.get("work_units") or 0),
            "scope": first_cursor.get("scope"),
            "target_scope": first_cursor.get("target_scope"),
            "pending_units": int(first_cursor.get("pending_files") or 0),
            "source_errors": len(first_cursor.get("source_errors") or []),
            "adapter_gaps": len(first_cursor.get("adapter_gaps") or []),
            "occurrences": int((first_public.get("coverage") or {}).get("occurrences") or 0),
            "atoms": int((first_public.get("coverage") or {}).get("atoms") or 0),
            "event_rows": first_journal["rows"],
            "outcome_rows": first_outcomes,
            "source_families": {
                name: {
                    field: int(((first_cursor.get("source_families") or {}).get(name) or {}).get(field) or 0)
                    for field in ("discovered", "converged")
                }
                for name in REQUIRED_CANARY_FAMILIES
            },
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
        second_metrics = artifact_metrics(private_root, public_snapshot, public_markdown, public_seal)
        second_journal = journal_counts(event_journal)
        second_outcomes = outcome_count(outcome_journal)
        journal_delta = {
            "event_rows": second_journal["rows"] - first_journal["rows"],
            "atoms": second_journal["atoms"] - first_journal["atoms"],
            "reclassifications": second_journal["reclassifications"] - first_journal["reclassifications"],
            "outcomes": second_outcomes - first_outcomes,
        }
        receipt["second_pass"] = {
            "work_units_used": int(second_summary.get("work_units") or 0),
            "event_row_delta": journal_delta["event_rows"],
            "atom_delta": journal_delta["atoms"],
            "outcome_delta": journal_delta["outcomes"],
            "reclassification_delta": journal_delta["reclassifications"],
        }
        receipt["artifacts_after_second"] = second_metrics
        if any(journal_delta.values()):
            failures.append("second_pass_journal_growth")
        if second_summary["occurrences"] != 0:
            failures.append("second_pass_appended_occurrences")
        if second_summary["atoms"] != 0:
            failures.append("second_pass_appended_atoms")
        if second_summary["outcomes"] != 0:
            failures.append("second_pass_appended_outcomes")
        if second_summary["changed"] is not False:
            failures.append("second_pass_reported_change")
        if second_summary["work_units"] != 0:
            failures.append("second_pass_used_work_units")
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
        "--public-seal",
        str(public_seal),
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
    try:
        final_seal = load_object(public_seal, "public_authority_seal")
        authority_ready = final_seal.get("authority_ready") is True
        receipt["verification"]["authority_ready"] = authority_ready
        if not authority_ready:
            failures.append("public_authority_seal_not_ready")
    except CanaryFailure as exc:
        receipt["verification"]["authority_ready"] = False
        failures.append(str(exc))

    try:
        final_code_identity = exact_head_code_identity()
        identity_stable = bool(
            final_code_identity["git_head"] == code_identity["git_head"]
            and final_code_identity["code_sha256"] == code_identity["code_sha256"]
            and final_code_identity["matches_git_head"] == code_identity["matches_git_head"]
        )
        receipt["code_identity_reverified"] = identity_stable
        if not identity_stable:
            failures.append("canary_code_identity_changed_during_run")
        if not args.allow_dirty_code and not final_code_identity["matches_git_head"]:
            failures.append("canary_code_no_longer_matches_git_head")
    except CanaryFailure as exc:
        receipt["code_identity_reverified"] = False
        failures.append(str(exc))

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
