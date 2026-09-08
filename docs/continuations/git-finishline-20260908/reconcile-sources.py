#!/usr/bin/env python3
"""Reconcile the frozen recovery extraction without publishing source bodies.

Reads canonical board and native GitHub snapshots supplied by the caller. It
does not access the network, replay historical tasks, or establish delivery.
"""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess

import yaml


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
INTENT_FIELDS = (
    "title",
    "description",
    "context",
    "repo",
    "type",
    "depends_on",
    "verification",
    "predicate",
    "acceptance_criteria",
    "receipt_target",
    "execution_requirements",
    "workstream_contract",
    "provider_eligibility",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def opaque(kind: str, value: str) -> str:
    material = f"{kind}:{value}" if kind else value
    return "recovery-" + hashlib.sha256(material.encode()).hexdigest()[:20]


def object_digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load(path: Path):
    return json.loads(path.read_text())


def unique(rows: list[dict], key: str) -> dict:
    if not isinstance(rows, list) or any(not isinstance(r, dict) or not r.get(key) for r in rows):
        raise ValueError(f"malformed {key} inventory")
    result = {r[key]: r for r in rows}
    if len(result) != len(rows):
        raise ValueError(f"duplicate {key}")
    return result


def task_assessment(candidate: dict, source_rows: list[tuple[int, dict]], board: dict) -> dict:
    """Compare intent fields, separately from mutable lifecycle observations."""
    current = board.get(candidate["id"])
    alternatives = []
    for index, source in source_rows:
        intent = {k: source.get(k) for k in INTENT_FIELDS}
        differences = [k for k in INTENT_FIELDS if current and source.get(k) != current.get(k)]
        alternatives.append(
            {
                "source_id": f"stash:{index}",
                "source_intent_sha256": object_digest(intent),
                "different_intent_fields": differences,
            }
        )
    if not alternatives:
        raise ValueError("candidate has no source task object")
    row = {
        "candidate_id": opaque("task", candidate["id"]),
        "source_ids": [f"stash:{i}" for i in candidate["source_indices"]],
        "source_delta_types": sorted(set(candidate["source_delta_types"])),
        "source_comparisons": alternatives,
        "canonical_status_observation": current.get("status") if current else None,
        "delivery_assessment": "unverified",
    }
    if current:
        row["canonical_intent_sha256"] = object_digest({k: current.get(k) for k in INTENT_FIELDS})
        diffs = [x["different_intent_fields"] for x in alternatives]
        if all(not d for d in diffs):
            row["lineage_assessment"] = "exact_source_intent_retained"
        elif any(not d for d in diffs):
            row["lineage_assessment"] = "source_variant_retained_other_variants_differ"
        elif (
            all(set(d).issubset({"predicate", "receipt_target"}) for d in diffs)
            and all(source.get(k) is None for _, source in source_rows for k in {"predicate", "receipt_target"})
            and current.get("predicate")
        ):
            row["lineage_assessment"] = "source_intent_retained_with_added_acceptance"
        else:
            row["lineage_assessment"] = "changed_intent_requires_reconciliation"
    else:
        original = candidate.get("original_id_candidate")
        row["lineage_assessment"] = "original_identity_present" if original in board else "source_identity_missing"
        if original:
            row["original_candidate_id"] = opaque("task", original)
            row["original_status_observation"] = board.get(original, {}).get("status")
        # A RECOVER record is a request to examine an unmerged predecessor,
        # never proof that the original marked done actually shipped.
    return row


def review_lineage(frozen: list[dict], native: list[dict]) -> list[dict]:
    original = unique(frozen, "id")
    observed = unique(native, "id")
    rows = []
    for rid, source in original.items():
        live = observed.get(rid)
        if not live or live.get("html_url") != source["html_url"]:
            raise ValueError("missing or mismatched native review identity")
        # A later edit needs reassessment; identity alone must not silently
        # bind a different request to the frozen candidate.
        if live.get("body") != source["body"]:
            raise ValueError("review body changed since extraction")
        parent = live.get("in_reply_to_id")
        if parent is not None and parent not in original:
            raise ValueError("review parent outside frozen extraction")
        root, seen = rid, set()
        while observed[root].get("in_reply_to_id") is not None:
            if root in seen:
                raise ValueError("cyclic review lineage")
            seen.add(root)
            root = observed[root]["in_reply_to_id"]
            if root not in original:
                raise ValueError("review ancestor outside frozen extraction")
        rows.append(
            {
                "review_id": str(rid),
                "review_ref": source["html_url"],
                "source_pr": source["source_pr"],
                "path": source["path"],
                "source_body_sha256": hashlib.sha256(source["body"].encode()).hexdigest(),
                "in_reply_to_id": str(parent) if parent is not None else None,
                "root_review_id": str(root),
                "record_kind": "reply" if parent is not None else "root_finding",
                "delivery_assessment": "unverified",
            }
        )
    return rows


def reconcile(
    extraction: dict,
    custody: dict,
    board: dict,
    snapshots: dict,
    frozen_reviews: list[dict],
    native_reviews: list[dict],
) -> dict:
    tasks = unique(board["tasks"], "id")
    candidates = unique(extraction["task_intent_candidates"], "id")
    task_rows = []
    for candidate in candidates.values():
        source_rows = [
            (i, snapshots[i][candidate["id"]]) for i in candidate["source_indices"] if candidate["id"] in snapshots[i]
        ]
        if len(source_rows) != len(candidate["source_indices"]):
            raise ValueError("candidate source occurrence is missing")
        task_rows.append(task_assessment(candidate, source_rows, tasks))
    reviews = review_lineage(frozen_reviews, native_reviews)
    historical = []
    for stash in custody["stashes"]:
        if not stash["delivery_disposition"].startswith("historical"):
            continue
        sid = f"stash:{stash['index']}"
        historical.append(
            {
                "source_id": sid,
                "source_object": stash["commit"],
                "prior_label": stash["delivery_disposition"],
                "reassessment": "historical_label_does_not_discharge_intent",
                "task_candidate_ids": [r["candidate_id"] for r in task_rows if sid in r["source_ids"]],
                "source_intent_ids": [
                    opaque("", c["id"])
                    for c in extraction["non_task_intent_candidates"]
                    if stash["index"] in c["source_indices"]
                ],
                "delivery_assessment": "unverified",
            }
        )
    return {
        "schema": "limen.recovery_source_reconciliation.v1",
        "owner": "https://github.com/4444J99/limen/pull/2576",
        "scope": "source and review lineage; delivery requires completion predicate",
        "counts": {
            "task_candidates": len(task_rows),
            "task_lineage": dict(sorted(Counter(r["lineage_assessment"] for r in task_rows).items())),
            "review_records": len(reviews),
            "root_review_findings": sum(r["record_kind"] == "root_finding" for r in reviews),
            "review_replies": sum(r["record_kind"] == "reply" for r in reviews),
            "historical_stash_labels_reassessed": len(historical),
        },
        "tasks": task_rows,
        "reviews": reviews,
        "historical_stash_labels": historical,
    }


def bind_manifest(manifest: dict, reconciliation: dict, decisions: dict, evidence: dict) -> dict:
    """Fold only explicitly assessed replies, retaining every frozen candidate."""
    result = deepcopy(manifest)
    before = [cid for atom in result["atoms"] for cid in atom["candidate_ids"]]
    if len(before) != len(set(before)):
        raise ValueError("duplicate candidate assignment")
    assigned = {cid: atom for atom in result["atoms"] for cid in atom["candidate_ids"]}
    reviews = unique(reconciliation["reviews"], "review_id")
    approved = unique(decisions["replies"], "review_id")
    replies = {rid: row for rid, row in reviews.items() if row["record_kind"] == "reply"}
    if set(approved) != set(replies):
        raise ValueError("every folded reply needs an explicit assessment")
    for rid, record in replies.items():
        decision = approved[rid]
        if (
            decision["root_review_id"] != record["root_review_id"]
            or decision["source_body_sha256"] != record["source_body_sha256"]
            or decision["disposition"] != "same_finding_evidence"
        ):
            raise ValueError("reply assessment is stale or has different scope")
        root_id = opaque("review", record["root_review_id"])
        reply_id = opaque("review", rid)
        parent, reply = assigned[root_id], assigned[reply_id]
        if parent is reply:  # Re-entry after a previous identical reconciliation.
            continue
        parent["candidate_ids"] = sorted(set(parent["candidate_ids"] + reply["candidate_ids"]))
        parent["source_ids"] = sorted(set(parent["source_ids"] + reply["source_ids"]))
        for cid in reply["candidate_ids"]:
            assigned[cid] = parent
        result["atoms"].remove(reply)
    for record in reviews.values():
        parent = assigned[opaque("review", record["review_id"])]
        root_id = record["root_review_id"]
        parent["review_record_ids"] = sorted(rid for rid, row in reviews.items() if row["root_review_id"] == root_id)
        parent["review_lineage_assessment"] = "native root finding; assessed replies retained as evidence"
    for row in reconciliation["tasks"]:
        atom = assigned[row["candidate_id"]]
        atom["lineage_assessment"] = row["lineage_assessment"]
        atom["source_reconciliation"] = evidence
        atom["canonical_status_observation"] = row["canonical_status_observation"]
    for source in result["sources"]:
        source["atom_ids"] = [a["atom_id"] for a in result["atoms"] if source["source_id"] in a["source_ids"]]
    after = [cid for atom in result["atoms"] for cid in atom["candidate_ids"]]
    if len(after) != len(before) or set(after) != set(before):
        raise ValueError("reconciliation changed the frozen candidate denominator")
    result["source_reconciliation"] = evidence
    result["count_status"] = "provisional: review replies reconciled; source variants and delivery unresolved"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-dir", type=Path, required=True)
    parser.add_argument("--canonical-board", type=Path, required=True)
    parser.add_argument("--native-review-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bind-manifest", type=Path)
    args = parser.parse_args()
    extraction = load(args.extraction_dir / "source-findings.json")
    custody = load(HERE / "stash-custody.json")
    frozen_reviews = load(args.extraction_dir / "review-findings.json")["reviews"]
    native_paths = [args.native_review_dir / f"{pr}.json" for pr in sorted({r["source_pr"] for r in frozen_reviews})]
    native_reviews = [r for p in native_paths for r in load(p)]
    expected = load(HERE / "candidate-inventory.json")["private_extraction_sha256"]
    actual = {name: sha(args.extraction_dir / f"{name}.json") for name in expected}
    if actual != expected:
        raise ValueError("private extraction does not match frozen inventory")
    snapshots = {}
    for i in sorted({i for c in extraction["task_intent_candidates"] for i in c["source_indices"]}):
        value = subprocess.run(
            ["git", "-C", str(ROOT), "show", custody["stashes"][i]["commit"] + ":tasks.yaml"],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        ).stdout
        snapshots[i] = unique(yaml.load(value, Loader=yaml.CSafeLoader)["tasks"], "id")
    result = reconcile(extraction, custody, load(args.canonical_board), snapshots, frozen_reviews, native_reviews)
    result["inputs"] = {
        "private_extraction_sha256": actual,
        "canonical_board_sha256": sha(args.canonical_board),
        "native_review_sha256": {p.stem: sha(p) for p in native_paths},
        "source_head": subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip(),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.bind_manifest:
        evidence = {"ref": str(args.output.resolve().relative_to(ROOT)), "sha256": sha(args.output)}
        manifest = bind_manifest(
            load(args.bind_manifest), result, load(HERE / "review-reply-assessments.json"), evidence
        )
        args.bind_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(result["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
