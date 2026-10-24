"""Replay the bound affected sources into create-only private correction artifacts."""

import argparse
from compression import zstd
import hashlib
import importlib.util
import json
from pathlib import Path
import time

BASE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("repaired_native_projection", BASE / "capture-native-projection.py")
DECODER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DECODER)


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(131072), b""):
            digest.update(block)
    return digest.hexdigest()


def capture(session):
    path = Path(session["path"])
    before = path.stat()
    start = time.monotonic()
    digest = hashlib.sha256()
    size = 0
    count = 0
    opener = zstd.open if path.suffix == ".zst" else open

    def records():
        nonlocal size, count
        with opener(path, "rb") as source:
            for number in range(1, 200001):
                if time.monotonic() - start > 20:
                    raise TimeoutError("source_deadline")
                line = source.readline(4 * 1024 * 1024 + 1)
                if not line:
                    return
                size += len(line)
                if len(line) > 4 * 1024 * 1024 or size > 128 * 1024 * 1024:
                    raise ValueError("source_limit")
                digest.update(line)
                count = number
                yield number, json.loads(line)
        raise ValueError("source_record_limit")

    projected = DECODER.project_rollout_records(records())
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("source_changed_during_read")
    if digest.hexdigest() != session["decompressed_sha256"]:
        raise ValueError("source_snapshot_mismatch")
    return {**session, **projected, "decompressed_bytes": size, "records": count}


def backward_pairs(session):
    return {
        (prompt["source_ref"]["rollout_ordinal"], reply["source_ref"]["rollout_ordinal"])
        for prompt in session["prompts"]
        for reply in prompt["finals"]
        if reply["source_ref"]["rollout_ordinal"] <= prompt["source_ref"]["rollout_ordinal"]
    }


def write_new(path, value):
    with path.open("x") as output:
        json.dump(value, output, indent=2)
        output.write("\n")
    path.chmod(0o600)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    if not args.output_root.is_dir() or args.output_root.is_symlink():
        raise ValueError("output_root_must_be_an_existing_private_directory")
    snapshot = args.private_root / "native-stream-v3-0000.json"
    original_catalog = args.private_root / "native-catalog.html"
    original_hashes = {path.name: file_digest(path) for path in (snapshot, original_catalog)}
    stream = json.loads(snapshot.read_text())
    findings = json.loads((BASE / "reply-order-findings-v1.json").read_text())
    wanted = {row["column"] for row in findings["sources"]}
    selected = {hashlib.sha256(s["path"].encode()).hexdigest()[:12]: s for s in stream["sessions"]}
    if not wanted <= selected.keys():
        raise ValueError("affected_source_binding_unavailable")
    start = time.monotonic()
    corrected = {}
    rows = []
    for column in sorted(wanted):
        if time.monotonic() - start > 220:
            raise TimeoutError("reconciliation_deadline")
        old = selected[column]
        new = capture(old)
        old_inputs = [(p["source_ref"], p["text"], p["extra_parts"]) for p in old["prompts"]]
        new_inputs = [(p["source_ref"], p["text"], p["extra_parts"]) for p in new["prompts"]]
        if old_inputs != new_inputs:
            raise ValueError("source_input_projection_changed")
        before = backward_pairs(old)
        after = backward_pairs(new)
        if after:
            raise ValueError("backward_association_survived")
        changed = sum(a["finals"] != b["finals"] for a, b in zip(old["prompts"], new["prompts"], strict=True))
        corrected[old["path"]] = new
        rows.append(
            {
                "column": column,
                "snapshot_sha256": old["decompressed_sha256"],
                "decoded_bytes": new["decompressed_bytes"],
                "prompt_rows": len(new["prompts"]),
                "backward_pairs_before": len(before),
                "backward_pairs_after": len(after),
                "changed_response_positions": changed,
                "source_input_projection_unchanged": True,
            }
        )
        print(json.dumps(rows[-1]), flush=True)
    stream["sessions"] = [corrected.get(s["path"], s) for s in stream["sessions"]]
    stream["reply_order_correction"] = {
        "source_columns": len(rows),
        "original_snapshot_sha256": original_hashes[snapshot.name],
    }
    destination = args.output_root / "native-stream-reply-order-20261023.json"
    write_new(destination, stream)
    if any(file_digest(args.private_root / name) != digest for name, digest in original_hashes.items()):
        raise ValueError("original_artifact_changed")
    report = {
        "owner": "https://github.com/4444J99/limen/issues/3056",
        "date": "2026-10-23",
        "original_artifacts_unchanged": True,
        "original_artifact_sha256": original_hashes,
        "corrected_snapshot_sha256": file_digest(destination),
        "source_columns": rows,
        "backward_pairs_before": sum(r["backward_pairs_before"] for r in rows),
        "backward_pairs_after": sum(r["backward_pairs_after"] for r in rows),
        "changed_response_positions": sum(r["changed_response_positions"] for r in rows),
        "elapsed_seconds": round(time.monotonic() - start, 3),
        "limits": "Only the 19 affected columns were replayed. Shared-turn causal uncertainty and all original source/retention gaps remain.",
    }
    write_new(args.output_root / "reply-order-reconciliation-20261023.json", report)
    print(json.dumps({k: v for k, v in report.items() if k != "source_columns"}), flush=True)


if __name__ == "__main__":
    main()
