#!/usr/bin/env python3
"""Verify preservation of a substantively reviewed report, not facts through keyword checks.

The fixed document and comment digests bind the actual September 9 source audit and independent
verdict. Updating those pins requires a new source review. This offline predicate verifies that
the reviewed source/evidence is still present; it cannot authenticate a live GitHub response,
rerun historical executions, establish transitive task acceptance or authorize publication.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OBSERVATION = Path("docs/receipts/positioning/2026-09-09-limen-report-review-observation.json")
OBSERVATION_SHA256 = "4b65fefca4c4c78ec4c0aa04d3ffa886fb621eeab45c0fb9d8b38ff3ea40b583"
REPORT_HEAD = "cd875d2fd585113cbb12a3ffa2f16d01912ab5a0"
REPORT_TREE = "e0a1052d69511ec64aba94942969830e633d1473"
DOCUMENTS = {
    "limen-engineering-report.md": "34b7b755bb941f08fe7e81e4c2b796d7ca2a91ee",
    "limen-evidence-appendix.md": "d7729fd1cf84d59a9751a8c55cf2b996e01853a6",
    "limen-executive-summary.md": "94725e9b7a4a537ecb07d3daf77544bf481b97f8",
    "limen-limitations.md": "fb30d01abc75d8a302411ece388c3de712955694",
}
COMMENTS = {
    5602000514: "65ea984d28ddb399266b9432cbf6395312d32a259d701691d4a2896913730007",
    5602027664: "c6d96054312d102b80b658bca0c60bbbc265a8a3b7caf4f0e0a3c54d587afabf",
}
CLAIMS = [f"E{number:02d}" for number in range(1, 10)]
BOUNDARY = (
    "Preserved reviewed-source evidence only: no live revalidation, historical execution rerun, "
    "transitive dependency acceptance, task completion or external publication authority."
)


def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def verify(root: Path = ROOT) -> dict:
    errors: list[str] = []
    documents: dict[str, str] = {}
    for name, expected in DOCUMENTS.items():
        path = root / "docs/positioning/proof" / name
        try:
            content = path.read_bytes()
            if git_blob(content) != expected:
                errors.append(f"{name}: differs from the independently reviewed source; obtain a new review")
            documents[name] = content.decode("utf-8")
        except (OSError, UnicodeError):
            errors.append(f"{name}: reviewed document unavailable")
    appendix = documents.get("limen-evidence-appendix.md", "")
    evidence_rows = re.findall(r"^\| (E\d{2}) \|", appendix, re.MULTILINE)
    if evidence_rows != CLAIMS:
        errors.append("dated claim coverage must preserve E01 through E09 exactly once")
    references = set(re.findall(r"\bE\d{2}\b", "\n".join(documents.values())))
    if references != set(CLAIMS):
        errors.append("every referenced evidence ID must resolve to the reviewed appendix")
    try:
        record = json.loads((root / OBSERVATION).read_text())
        if not isinstance(record, dict):
            raise ValueError("observation must be an object")
        capture_digest = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if capture_digest != OBSERVATION_SHA256:
            errors.append("complete review observation differs from the actual captured record")
        expected = {
            "schema_version": "limen.report_source_review_observation.v1",
            "source": "authenticated_github_connector",
            "repository": "4444J99/limen",
            "repository_id": 1255213941,
            "report_head": REPORT_HEAD,
            "report_tree": REPORT_TREE,
        }
        for key, value in expected.items():
            if record.get(key) != value:
                errors.append(f"review observation {key} does not match the recorded source")
        observed = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("observation timestamp needs timezone")
        comments = record.get("comments")
        if not isinstance(comments, list) or [item.get("id") for item in comments] != list(COMMENTS):
            raise ValueError("source audit and independent verdict must both be preserved in order")
        for comment in comments:
            identifier = comment["id"]
            url = f"https://github.com/4444J99/limen/issues/2198#issuecomment-{identifier}"
            if comment.get("html_url") != url or comment.get("user_login") != "4444J99":
                errors.append(f"comment {identifier}: recorded origin differs")
            body = comment.get("body", "")
            if not isinstance(body, str) or hashlib.sha256(body.encode()).hexdigest() != COMMENTS[identifier]:
                errors.append(f"comment {identifier}: source audit or independent verdict changed")
            created = datetime.fromisoformat(comment["created_at"].replace("Z", "+00:00"))
            updated = datetime.fromisoformat(comment["updated_at"].replace("Z", "+00:00"))
            if created.tzinfo is None or updated.tzinfo is None or not created <= updated <= observed:
                errors.append(f"comment {identifier}: observation chronology invalid")
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        errors.append("review observation unavailable or malformed")
    return {
        "status": "pass" if not errors else "fail",
        "work_id": "PSP-P05-W01",
        "reviewed_report_head": REPORT_HEAD,
        "reviewed_report_tree": REPORT_TREE,
        "document_count": len(DOCUMENTS),
        "claim_ids": CLAIMS,
        "independent_verdict_url": "https://github.com/4444J99/limen/issues/2198#issuecomment-5602027664",
        "boundary": BOUNDARY,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify recorded reviewed-source preservation")
    parser.add_argument("--json", action="store_true", help="emit a deterministic evidence result")
    args = parser.parse_args()
    result = verify()
    print(json.dumps(result, indent=2) if args.json else f"Limen report source review: {result['status']}\n{BOUNDARY}")
    if not args.json:
        for error in result["errors"]:
            print(f"- {error}")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
