#!/usr/bin/env python3
"""One-command reversible intake and receipt-candidate workflow for PSP-P03-W07."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
PROGRAM = ROOT / "docs/positioning/program"
VALIDATOR_PATH = PROGRAM / "validate_p03_w07_blinded_reader.py"
IMPORT_SCHEMA_VERSION = "psp-p03-w07-reader-import.v1"
DIRECT_HUMAN_SESSION_ID = "019fed0e-7216-7422-8398-f83354946f54"
EXECUTOR = "Codex"

SPEC = importlib.util.spec_from_file_location("validate_p03_w07_blinded_reader", VALIDATOR_PATH)
if not SPEC or not SPEC.loader:
    raise RuntimeError(f"cannot load {VALIDATOR_PATH}")
V = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = V
SPEC.loader.exec_module(V)


class WorkflowError(ValueError):
    """Raised when the reversible W07 workflow cannot proceed safely."""


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WorkflowError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_object)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot read JSON from {path}: {exc}") from exc


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def pretty_json(payload: Any) -> str:
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def response_sha256(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def initialization_payload() -> dict[str, Any]:
    tracked = V.load_payload(V.DEFAULT_RESPONSES)
    return {
        "schema_version": IMPORT_SCHEMA_VERSION,
        "collected_at": None,
        "readers": json.loads(json.dumps(tracked["readers"])),
    }


def _exact_keys(value: Any, expected: set[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WorkflowError(f"{label} must be an object")
    actual = set(value)
    if actual != expected:
        raise WorkflowError(
            f"{label} keys differ: missing={sorted(expected - actual)} extra={sorted(actual - expected)}"
        )
    return value


def import_response_set(raw: Any) -> tuple[dict[str, Any], V.Verdict]:
    source = _exact_keys(raw, {"schema_version", "collected_at", "readers"}, "import set")
    if source["schema_version"] != IMPORT_SCHEMA_VERSION:
        raise WorkflowError(f"schema_version must be {IMPORT_SCHEMA_VERSION}")
    if source["collected_at"] is None:
        raise WorkflowError("collected_at is still pending; five reader records were not collected")
    payload = {
        "schema_version": V.SCHEMA_VERSION,
        "work_id": V.WORK_ID,
        "stimulus": dict(V.STIMULUS),
        "status": "complete",
        "collected_at": source["collected_at"],
        "readers": source["readers"],
    }
    verdict = V.validate(payload)
    return payload, verdict


def score_totals(payload: dict[str, Any]) -> Counter[str]:
    totals: Counter[str] = Counter({field: 0 for field in V.SCORE_FIELDS})
    for reader in payload["readers"]:
        for field in V.SCORE_FIELDS:
            totals[field] += int(reader["element_scores"][field])
    return totals


def objection_summary(payload: dict[str, Any]) -> tuple[Counter[str], int]:
    categories: Counter[str] = Counter()
    authority_unresolved = 0
    for reader in payload["readers"]:
        seen: set[str] = set()
        for objection in reader["trust_objections"]:
            seen.add(objection["category"])
            if objection["category"] == "authority_takeover_concern" and objection["unresolved"]:
                authority_unresolved += 1
        categories.update(seen)
    return categories, authority_unresolved


def revision_decision(
    verdict: V.Verdict,
    totals: Counter[str],
    categories: Counter[str],
    authority_unresolved: int,
) -> str:
    repeated = sorted(category for category, count in categories.items() if count >= 3)
    if verdict.state == "pass":
        return "PASS: no narrative revision is required by the declared W07 thresholds."
    if authority_unresolved or repeated:
        return "REVISE W03-W06: resolve authority or structural trust language, then collect a fresh set."
    if totals["role"] < 4 or totals["buyer"] < 4:
        return "REVISE W03-W06: clarify role or buyer, then collect a fresh set."
    if totals["cta"] < 4:
        return "REVISE CTA: clarify the two-door next action, then collect a fresh set."
    return "REVISE W03-W06: the aggregate comprehension threshold failed; collect a fresh set after revision."


def decision_memo(payload: dict[str, Any], verdict: V.Verdict) -> str:
    totals = score_totals(payload)
    categories, authority_unresolved = objection_summary(payload)
    repeated = sorted(f"{category}={count}" for category, count in categories.items() if count >= 3)
    category_rows = [
        f"- {category}: {categories.get(category, 0)}/5 readers" for category in sorted(V.OBJECTION_CATEGORIES)
    ]
    lines = [
        "# PSP-P03-W07 blinded-reader decision memo",
        "",
        "This memo contains aggregate classifications only. It does not reproduce reader",
        "answers, names, companies, contacts, or private project details.",
        "",
        "## Evidence binding",
        "",
        f"- Stimulus head: {V.STIMULUS['head']}",
        f"- Reader-block SHA-256: {V.STIMULUS['reader_block_sha256']}",
        f"- Protocol: {V.STIMULUS['issue_comment']}",
        f"- Response-set SHA-256: {response_sha256(payload)}",
        f"- Collected at: {payload['collected_at']}",
        "",
        "## Comprehension scores",
        "",
        f"- Total: {sum(totals.values())}/25",
        *[f"- {field}: {totals[field]}/5" for field in V.SCORE_FIELDS],
        "",
        "## Trust classifications",
        "",
        *category_rows,
        f"- Unresolved authority/takeover records: {authority_unresolved}",
        "- Repeated structural categories: " + (", ".join(repeated) if repeated else "none"),
        "",
        "## Decision",
        "",
        f"- Validator state: {verdict.state.upper()}",
        f"- Validator reason: {verdict.message}",
        f"- Revision verdict: {revision_decision(verdict, totals, categories, authority_unresolved)}",
        "",
        "## Return path",
        "",
        "Keep the accepted W03-W06 narrative live. A failed set returns only the",
        "implicated inference or trust category for revision; no response is edited,",
        "rescored after coaching, or reused in the fresh set.",
        "",
    ]
    return "\n".join(lines)


def _write_exact(path: Path, content: str) -> None:
    if not path.parent.exists():
        raise WorkflowError(f"output parent does not exist: {path.parent}")
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current != content:
            raise WorkflowError(f"refusing to overwrite different existing output: {path}")
        return
    path.write_text(content, encoding="utf-8")


def _preflight_output(path: Path, content: str) -> None:
    if not path.parent.exists():
        raise WorkflowError(f"output parent does not exist: {path.parent}")
    if path.exists() and path.read_text(encoding="utf-8") != content:
        raise WorkflowError(f"refusing to overwrite different existing output: {path}")


def _git(*args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise WorkflowError(f"git {' '.join(args)} failed: {detail.strip()}") from exc
    return completed.stdout.strip()


def _tracked_clean(path: Path) -> str:
    try:
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise WorkflowError(f"evidence path must remain inside the repository: {path}") from exc
    _git("ls-files", "--error-unmatch", "--", relative)
    _git("diff", "--quiet", "HEAD", "--", relative)
    _git("diff", "--cached", "--quiet", "--", relative)
    return relative


def _acceptance_sha256() -> str:
    command = [
        sys.executable,
        str(ROOT / "scripts/positioning-program.py"),
        "--receipt-template",
        V.WORK_ID,
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        receipt = json.loads(completed.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"cannot derive live W07 receipt template: {exc}") from exc
    digest = receipt.get("acceptance_sha256")
    if not isinstance(digest, str) or not re_full_digest(digest):
        raise WorkflowError("live W07 receipt template returned an invalid acceptance digest")
    return digest


def re_full_digest(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def build_receipt_comment(
    payload: dict[str, Any],
    verdict: V.Verdict,
    *,
    observed_head: str,
    observed_at: str,
    acceptance_sha256: str,
    changed_paths: list[str],
    response_path: str,
    memo_path: str,
) -> str:
    if verdict.state != "pass":
        raise WorkflowError("receipt candidate requires a passing five-reader verdict")
    if len(observed_head) != 40 or not all(character in "0123456789abcdef" for character in observed_head):
        raise WorkflowError("observed head must be an exact lowercase 40-character Git SHA")
    V._rfc3339(observed_at)
    if not re_full_digest(acceptance_sha256):
        raise WorkflowError("acceptance_sha256 must be a lowercase SHA-256 digest")
    predicate_command = "python3 docs/positioning/program/validate_p03_w07_blinded_reader.py " + response_path
    predicate_output = V.render_verdict(verdict) + "\n"
    base_url = f"https://github.com/organvm/limen/blob/{observed_head}/"
    receipt = {
        "schema_version": "limen.positioning_work_receipt.v1",
        "work_id": V.WORK_ID,
        "acceptance_sha256": acceptance_sha256,
        "authority": {
            "kind": "direct_human_session",
            "session_id": DIRECT_HUMAN_SESSION_ID,
            "executor": EXECUTOR,
            "human_protected": True,
        },
        "changed_paths": sorted(changed_paths),
        "evidence_urls": [
            "https://github.com/organvm/limen/issues/2188",
            V.STIMULUS["issue_comment"],
            base_url + response_path,
            base_url + memo_path,
        ],
        "observed_heads": {"organvm/limen": observed_head},
        "outcome": "succeeded",
        "predicate": {
            "command": predicate_command,
            "exit_code": 0,
            "observed_at": observed_at,
            "output_sha256": hashlib.sha256(predicate_output.encode("utf-8")).hexdigest(),
        },
        "rollback": {
            "invoked": False,
            "state": "not needed; accepted W03-W06 remains the return path",
        },
    }
    fence = chr(96) * 3
    return (
        f"<!-- positioning-receipt:{V.WORK_ID} -->\n"
        f"{fence}json\n{json.dumps(receipt, indent=2, sort_keys=True)}\n{fence}\n"
    )


def receipt_candidate(
    responses: Path,
    memo: Path,
    *,
    observed_at: str | None = None,
) -> str:
    payload = V.load_payload(responses)
    verdict = V.validate(payload)
    if verdict.state != "pass":
        raise WorkflowError("receipt candidate requires a passing five-reader verdict")
    expected_memo = decision_memo(payload, verdict)
    response_relative = _tracked_clean(responses)
    memo_relative = _tracked_clean(memo)
    if memo.read_text(encoding="utf-8") != expected_memo:
        raise WorkflowError("tracked decision memo is stale or does not match the response set")
    if _git("status", "--porcelain"):
        raise WorkflowError("receipt candidate requires a globally clean exact worktree")
    observed_head = _git("rev-parse", "HEAD")
    changed = _git(
        "diff",
        "--name-only",
        f"{V.STIMULUS['head']}..{observed_head}",
        "--",
        "docs/positioning",
        "docs/receipts",
    ).splitlines()
    timestamp = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    return build_receipt_comment(
        payload,
        verdict,
        observed_head=observed_head,
        observed_at=timestamp,
        acceptance_sha256=_acceptance_sha256(),
        changed_paths=changed,
        response_path=response_relative,
        memo_path=memo_relative,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    initialize = subparsers.add_parser("init", help="create a deterministic anonymous import file")
    initialize.add_argument("output", type=Path)

    importer = subparsers.add_parser("import", help="validate and canonicalize five collected records")
    importer.add_argument("source", type=Path)
    importer.add_argument("--responses", required=True, type=Path)
    importer.add_argument("--memo", required=True, type=Path)

    validate = subparsers.add_parser("validate", help="validate a canonical response set")
    validate.add_argument("responses", nargs="?", type=Path, default=V.DEFAULT_RESPONSES)

    receipt = subparsers.add_parser("receipt", help="generate a marked exact-head receipt candidate")
    receipt.add_argument("responses", type=Path)
    receipt.add_argument("memo", type=Path)
    receipt.add_argument("--output", required=True, type=Path)
    receipt.add_argument("--observed-at")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            content = pretty_json(initialization_payload())
            _write_exact(args.output, content)
            print(f"INITIALIZED: {args.output}")
            return 0

        if args.command == "import":
            payload, verdict = import_response_set(load_json(args.source))
            responses_content = pretty_json(payload)
            memo_content = decision_memo(payload, verdict)
            _preflight_output(args.responses, responses_content)
            _preflight_output(args.memo, memo_content)
            _write_exact(args.responses, responses_content)
            _write_exact(args.memo, memo_content)
            print(V.render_verdict(verdict))
            print(f"RESPONSES: {args.responses}")
            print(f"DECISION_MEMO: {args.memo}")
            return 2 if verdict.state == "blocked" else 0

        if args.command == "validate":
            verdict = V.validate(V.load_payload(args.responses))
            print(V.render_verdict(verdict))
            return 2 if verdict.state == "blocked" else 0

        try:
            args.output.resolve().relative_to(ROOT.resolve())
        except ValueError:
            pass
        else:
            raise WorkflowError("receipt candidate output must stay outside the repository to preserve the clean head")
        candidate = receipt_candidate(
            args.responses,
            args.memo,
            observed_at=args.observed_at,
        )
        _write_exact(args.output, candidate)
        print(f"PASS: {V.WORK_ID} receipt candidate is bound to the clean exact head")
        print(f"RECEIPT_CANDIDATE: {args.output}")
        return 0
    except (OSError, UnicodeError, WorkflowError, V.EvidenceError) as exc:
        print(f"FAIL: {V.WORK_ID} workflow: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
