#!/usr/bin/env python3
"""Check recovery intent delivery, separately from archive custody.

No network calls or mutations: the input is a fixed, reviewable integration
generation. Evidence files are digest-bound and must be tracked by Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "cli/src"))
from limen.prompt_corpus import validate_outcome  # noqa: E402


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(root: Path, item: dict) -> dict:
    ref = item["ref"]
    path = root / ref
    if path.is_symlink() or root.resolve() not in path.resolve().parents:
        raise ValueError("unsafe evidence path")
    if digest(path) != item["sha256"]:
        raise ValueError("stale evidence digest")
    subprocess.run(
        ["git", "-C", str(root), "ls-files", "--error-unmatch", "--", ref],
        check=True, capture_output=True, timeout=10,
    )
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError("evidence must be an object")
    return value


def expected_sources(here: Path) -> dict[str, str]:
    stashes = json.loads((here / "stash-custody.json").read_text())["stashes"]
    branches = json.loads((here / "branch-custody.json").read_text())["branches"]
    prs = json.loads((here / "pr-custody.json").read_text())["pull_requests"]
    if (len(stashes), len(branches), len(prs)) != (26, 9, 9):
        raise ValueError("custody denominator differs from 26/9/9")
    result = {f"stash:{x['index']}": x["commit"] for x in stashes}
    result.update({f"branch:{i}": x["tip"] for i, x in enumerate(branches)})
    result.update({f"pr:{i}": x["original_head"] for i, x in enumerate(prs)})
    if len(result) != 44:
        raise ValueError("duplicate custody source identity")
    return result


def check(data: dict, expected: dict[str, str], root: Path = ROOT) -> dict:
    errors: list[str] = []
    sources = data.get("sources", [])
    atoms = data.get("atoms", [])
    by_id = {a["atom_id"]: a for a in atoms}
    source_ids = [s["source_id"] for s in sources]
    if len(source_ids) != len(set(source_ids)) or set(source_ids) != set(expected):
        errors.append("source coverage differs from frozen 44-source cohort")
    if len(by_id) != len(atoms):
        errors.append("duplicate atom identity")
    covered = set()
    for source in sources:
        sid = source["source_id"]
        if source.get("object") != expected.get(sid):
            errors.append(f"{sid}: wrong source object")
        required = {"tracked", "index", "untracked", "requests", "reviews"}
        inspected = source.get("inspection", {})
        if any(inspected.get(k) != "assessed" for k in required):
            errors.append(f"{sid}: incomplete source inspection")
        ids = source.get("atom_ids", [])
        if not ids and not source.get("no_action_explanation"):
            errors.append(f"{sid}: neither intent nor explicit no-action explanation")
        if not ids:
            try:
                proof = artifact(root, source["no_action_evidence"])
                if proof.get("source_id") != sid or proof.get("object") != expected.get(sid):
                    raise ValueError("observation evidence subject mismatch")
                if proof.get("actionable_intents") != [] or not proof.get("analysis"):
                    raise ValueError("observation has no supported no-action analysis")
            except (KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
                errors.append(f"{sid}: invalid no-action evidence: {exc}")
        for aid in ids:
            if aid not in by_id or sid not in by_id[aid].get("source_ids", []):
                errors.append(f"{sid}: missing reciprocal atom {aid}")
            covered.add(aid)
    if set(by_id) != covered:
        errors.append("orphan or unknown intent in source mapping")
    finished = set()
    for aid, atom in by_id.items():
        for sid in atom.get("source_ids", []):
            if sid not in source_ids:
                errors.append(f"{aid}: source outside cohort")
        outcome = atom.get("outcome", {})
        errors.extend(validate_outcome(atom, by_id, evidence_root=root))
        disposition = outcome.get("disposition", "unassessed")
        if disposition not in {"done", "superseded"}:
            errors.append(f"{aid}: unfinished ({disposition})")
            continue
        if atom.get("unresolved_findings") != []:
            errors.append(f"{aid}: unresolved or unassessed substantive findings")
        if disposition == "superseded":
            successor = by_id.get(outcome.get("successor_atom_id"), {})
            if successor.get("outcome", {}).get("disposition") != "done":
                errors.append(f"{aid}: successor is not delivered")
            continue
        try:
            delivery = artifact(root, atom["delivery"])
            repo = delivery["repository"]
            generation = data["integration_generations"][repo]
            if delivery.get("default_generation") != generation:
                raise ValueError("stale integration generation")
            if delivery.get("atom_id") != aid or delivery.get("status") != "delivered":
                raise ValueError("delivery subject/status mismatch")
            if delivery.get("landing_kind") not in {"merged_pr", "verified_successor"}:
                raise ValueError("archive, owner, draft or unmerged PR is not delivery")
            if delivery.get("reachable_from_default") is not True:
                raise ValueError("missing positive landing proof")
            head = delivery["implemented_head"]
            if not isinstance(head, str) or len(head) != 40 or any(c not in "0123456789abcdef" for c in head):
                raise ValueError("invalid implementing head")
            landing = [e for e in outcome.get("evidence", [])
                       if e.get("kind") in {"github_pr", "github_commit"}
                       and e.get("ref", "").startswith(f"https://github.com/{repo}/")
                       and head in {e.get("head_sha"), e.get("commit_sha")}
                       and e.get("reachable_from_default") is True]
            if not landing:
                raise ValueError("missing verified repository-qualified landing receipt")
            required = atom.get("required_predicates", [])
            predicates = delivery.get("predicates", [])
            if not required or set(required) != {p["id"] for p in predicates}:
                raise ValueError("required delivery predicates missing")
            for predicate in predicates:
                receipt = artifact(root, predicate["receipt"])
                if (receipt.get("exit_code") != 0 or receipt.get("head") != head
                        or receipt.get("predicate_id") != predicate["id"]
                        or receipt.get("repository") != repo
                        or receipt.get("executed") is not True):
                    raise ValueError("predicate not executed successfully at implementing head")
            finished.add(aid)
        except (KeyError, ValueError, OSError, subprocess.SubprocessError) as exc:
            errors.append(f"{aid}: invalid delivery evidence: {exc}")
    for aid, atom in by_id.items():
        outcome = atom.get("outcome", {})
        if outcome.get("disposition") == "superseded":
            if outcome.get("successor_atom_id") in finished:
                finished.add(aid)
            else:
                errors.append(f"{aid}: successor failed delivery verification")
    return {"schema": "limen.recovery_completion_result.v1",
            "status": "FAIL" if errors else "PASS", "source_count": len(sources),
            "intent_count": len(atoms), "delivered_intent_count": len(finished),
            "errors": sorted(set(errors))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).with_name("completion.json"))
    args = parser.parse_args()
    try:
        result = check(json.loads(args.manifest.read_text()), expected_sources(Path(__file__).parent))
    except (KeyError, TypeError, ValueError, OSError) as exc:
        result = {"status": "FAIL", "errors": [f"invalid completion input: {exc}"]}
    result["error_count"] = len(result.get("errors", []))
    result["errors"] = result.get("errors", [])[:30]
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
