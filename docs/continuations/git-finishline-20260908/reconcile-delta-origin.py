#!/usr/bin/env python3
"""Separate recovered asks from task state carried by archived projections.

This is a source-delta predicate, not a task completion predicate. No board or
Git refs are mutated. Private task content is represented only by digests.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location("source_reconciliation", HERE / "reconcile-sources.py")
source = importlib.util.module_from_spec(spec)
spec.loader.exec_module(source)
OBSERVATIONS = {"unchanged_request_fields", "carried_from_contemporaneous_default"}


def intent(row: dict | None) -> dict | None:
    return {k: row.get(k) for k in source.INTENT_FIELDS} if row is not None else None


def classify(base: dict | None, index: dict | None, work: dict, prior: dict | None) -> str:
    b, i, w, p = map(intent, [base, index, work, prior])
    if b == i == w:
        return "unchanged_request_fields"
    # A staged request differing from both base and worktree is its own source
    # variant. A matching worktree must not erase it.
    if p == w and i in (b, w):
        return "carried_from_contemporaneous_default"
    return "added_or_changed_request"


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True, timeout=30
    ).stdout.strip()


def board(ref: str) -> dict:
    value = yaml.load(git("show", ref + ":tasks.yaml"), Loader=yaml.CSafeLoader)
    return source.unique(value["tasks"], "id")


def scan(extraction: dict, custody: dict, canonical: dict, generation: str) -> dict:
    candidates = source.unique(extraction["task_intent_candidates"], "id")
    current = source.unique(canonical["tasks"], "id")
    stashes = {r["index"]: r for r in custody["stashes"]}
    if len(stashes) != 26:
        raise ValueError("stash denominator changed")
    by_candidate = defaultdict(list)
    source_bindings = []
    for index in sorted({i for c in candidates.values() for i in c["source_indices"]}):
        stash = stashes[index]
        stamp = git("show", "-s", "--format=%cI", stash["commit"])
        prior_head = git("rev-list", "-1", "--before=" + stamp, generation)
        if not prior_head:
            raise ValueError("no contemporaneous default ancestor")
        parents = git("show", "-s", "--format=%P", stash["commit"]).split()
        if parents != stash["parents"]:
            raise ValueError("stash parent lineage changed")
        refs = {"base": parents[0], "index": parents[1], "worktree": stash["commit"], "prior_default": prior_head}
        versions = {key: board(ref) for key, ref in refs.items()}
        source_bindings.append(
            {
                "source_id": f"stash:{index}",
                "source_time": stamp,
                "objects": refs,
                "task_blobs": {key: git("rev-parse", ref + ":tasks.yaml") for key, ref in refs.items()},
            }
        )
        for cid, candidate in candidates.items():
            if index not in candidate["source_indices"]:
                continue
            rows = {key: rows.get(cid) for key, rows in versions.items()}
            if rows["worktree"] is None:
                raise ValueError("source candidate vanished")
            classification = classify(rows["base"], rows["index"], rows["worktree"], rows["prior_default"])
            by_candidate[cid].append(
                {
                    "source_id": f"stash:{index}",
                    "classification": classification,
                    "request_digests": {
                        key: source.object_digest(intent(row)) if row is not None else None for key, row in rows.items()
                    },
                }
            )
    rows = []
    for cid, candidate in candidates.items():
        occurrences = by_candidate[cid]
        observed_only = all(r["classification"] in OBSERVATIONS for r in occurrences)
        canonical_owner = cid in current
        rows.append(
            {
                "candidate_id": source.opaque("task", cid),
                "source_ids": [f"stash:{i}" for i in candidate["source_indices"]],
                "classification": "preserved_projection_observation"
                if observed_only and canonical_owner
                else "recovered_request",
                "canonical_identity_present": canonical_owner,
                "canonical_request_digest": source.object_digest(intent(current[cid])) if canonical_owner else None,
                "occurrences": occurrences,
                "underlying_task_delivery": "not_asserted",
            }
        )
    return {
        "schema": "limen.recovery_delta_origin.v1",
        "repository": "4444J99/limen",
        "default_generation": generation,
        "request_fields": list(source.INTENT_FIELDS),
        "source_bindings": source_bindings,
        "candidates": rows,
        "counts": dict(sorted(Counter(r["classification"] for r in rows).items())),
        "scope": "origin of stash request deltas; carried state is preserved without claiming underlying tasks complete",
    }


def bind(manifest: dict, origin: dict, evidence: dict) -> dict:
    result = deepcopy(manifest)
    original_candidates = [cid for a in result["atoms"] for cid in a["candidate_ids"]]
    if len(original_candidates) != len(set(original_candidates)):
        raise ValueError("duplicate manifest candidate")
    preserving = source.opaque("", "recovery-dated-report-observations")
    owner = next(a for a in result["atoms"] if a["atom_id"] == preserving)
    assigned = {cid: a for a in result["atoms"] for cid in a["candidate_ids"]}
    roles = owner.setdefault("candidate_roles", {})
    for row in origin["candidates"]:
        if row["classification"] != "preserved_projection_observation":
            continue
        if not row["canonical_identity_present"] or not row["occurrences"]:
            raise ValueError("observation lacks canonical owner or source delta")
        for occurrence in row["occurrences"]:
            d = occurrence["request_digests"]
            if occurrence["classification"] == "unchanged_request_fields":
                valid = d["base"] == d["index"] == d["worktree"] and d["worktree"] is not None
            elif occurrence["classification"] == "carried_from_contemporaneous_default":
                valid = (
                    d["worktree"] == d["prior_default"]
                    and d["index"] in (d["base"], d["worktree"])
                    and d["worktree"] is not None
                )
            else:
                valid = False
            if not valid:
                raise ValueError("changed request cannot become a projection observation")
        atom = assigned[row["candidate_id"]]
        roles[row["candidate_id"]] = {
            "role": "preserved_projection_observation",
            "underlying_task_delivery": "not_asserted",
        }
        if atom is owner:
            continue
        if atom["candidate_ids"] != [row["candidate_id"]] or atom["outcome"]["disposition"] != "unassessed":
            raise ValueError("cannot overwrite an assessed or grouped source intent")
        owner["candidate_ids"] += atom["candidate_ids"]
        owner["source_ids"] = sorted(set(owner["source_ids"] + atom["source_ids"]))
        result["atoms"].remove(atom)
    owner["candidate_ids"] = sorted(owner["candidate_ids"])
    owner["description"] = (
        "Preserve dated reports and unchanged task projection observations with source ancestry; do not replay authority or assert the underlying tasks delivered."
    )
    owner["delta_origin_evidence"] = evidence
    owner["evidence_gap"] = (
        "Archive restoration and delta-origin checks passed; the preserving source and receipts still require final integration landing."
    )
    for row in result["sources"]:
        row["atom_ids"] = [a["atom_id"] for a in result["atoms"] if row["source_id"] in a["source_ids"]]
    final_candidates = [cid for a in result["atoms"] for cid in a["candidate_ids"]]
    if len(final_candidates) != len(original_candidates) or set(final_candidates) != set(original_candidates):
        raise ValueError("candidate coverage changed")
    result["delta_origin"] = evidence
    result["count_status"] = (
        "provisional: source-delta observations and review replies reconciled; remaining recovered requests and delivery unresolved"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extraction-dir", type=Path, required=True)
    parser.add_argument("--canonical-board", type=Path, required=True)
    parser.add_argument("--generation", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--bind-manifest", type=Path)
    args = parser.parse_args()
    expected = source.load(HERE / "candidate-inventory.json")["private_extraction_sha256"]
    if {key: source.sha(args.extraction_dir / f"{key}.json") for key in expected} != expected:
        raise ValueError("extraction digest mismatch")
    result = scan(
        source.load(args.extraction_dir / "source-findings.json"),
        source.load(HERE / "stash-custody.json"),
        source.load(args.canonical_board),
        args.generation,
    )
    result["inputs"] = {
        "private_extraction_sha256": expected,
        "canonical_board_sha256": source.sha(args.canonical_board),
        "predicate_sha256": source.sha(Path(__file__)),
        "source_head": git("rev-parse", "HEAD"),
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if args.bind_manifest:
        evidence = {"ref": str(args.output.resolve().relative_to(ROOT)), "sha256": source.sha(args.output)}
        result_manifest = bind(source.load(args.bind_manifest), result, evidence)
        args.bind_manifest.write_text(json.dumps(result_manifest, indent=2) + "\n")
    print(json.dumps(result["counts"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
