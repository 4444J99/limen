#!/usr/bin/env python3
"""Unbounded-depth metadata census. Never opens file contents or follows directory links."""
import argparse
import collections
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import signal
import subprocess
import time

def emit(handle, value):
    handle.write(json.dumps(value, ensure_ascii=True, sort_keys=True) + "\n")

def operation_timeout(signum, frame):
    raise TimeoutError("metadata operation exceeded 2 seconds")

def scan(roots, output, seconds):
    signal.signal(signal.SIGALRM, operation_timeout)
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    started = dt.datetime.now(dt.timezone.utc).isoformat()
    deadline = time.monotonic() + seconds
    mounts = subprocess.run(["/sbin/mount"], capture_output=True, text=True, check=True).stdout
    (output / "mounts.txt").write_text(mounts)
    excluded_mounts = {}
    for line in mounts.splitlines():
        match = re.match(r"^(.+) on (.+) \((.+)\)$", line)
        if match:
            where, flags = match[2], set(match[3].split(", "))
            if "local" not in flags or "devfs" in flags:
                excluded_mounts[where] = "non-local or virtual mount: " + match[3]
    seen = set()
    matched = set()
    errors = 0
    aliases = 0
    directories = 0
    rows = []
    with (output / "directories.jsonl").open("x") as found, (output / "aliases.jsonl").open("x") as links, (output / "errors.jsonl").open("x") as failures, (output / "coverage.jsonl").open("x") as coverage:
        for root in roots:
            counts = collections.Counter()
            stack = [str(Path(root).absolute())]
            root_errors = 0
            while stack and time.monotonic() < deadline:
                path = stack.pop()
                if path in excluded_mounts:
                    emit(coverage, {"path":path,"status":"excluded-mount","reason":excluded_mounts[path]})
                    counts["excluded_mounts"] += 1
                    continue
                try:
                    signal.setitimer(signal.ITIMER_REAL, 2)
                    info = os.lstat(path)
                    if stat.S_ISLNK(info.st_mode):
                        target = os.readlink(path)
                        if "codex" in path.lower() or "codex" in target.lower():
                            try:
                                real = os.path.realpath(path, strict=True)
                                target_info = os.stat(path)
                                target_id = [target_info.st_dev, target_info.st_ino]
                                kind = "directory" if stat.S_ISDIR(target_info.st_mode) else "file"
                            except OSError as exc:
                                real, target_id, kind = None, None, "unresolved"
                                emit(failures, {"path":path,"operation":"resolve-alias","errno":exc.errno})
                                errors += 1
                                root_errors += 1
                            emit(links, {"path":path,"target":target,"realpath":real,"physical_id":target_id,"kind":kind})
                            aliases += 1
                        continue
                    if not stat.S_ISDIR(info.st_mode):
                        continue
                    key = (info.st_dev, info.st_ino)
                    if key in seen:
                        counts["duplicate_physical_paths"] += 1
                        continue
                    seen.add(key)
                    directories += 1
                    counts["physical_directories"] += 1
                    if "codex" in os.path.basename(path).lower():
                        matched.add(key)
                        emit(found, {"path":path,"realpath":os.path.realpath(path),"physical_id":list(key),"basename":os.path.basename(path),"directory_entry_bytes":info.st_size,"mode":stat.S_IMODE(info.st_mode)})
                        counts["codex_named_physical_directories"] += 1
                    if getattr(info, "st_flags", 0) & getattr(stat, "SF_DATALESS", 0):
                        raise OSError("dataless cloud directory; not hydrated by census")
                    with os.scandir(path) as it:
                        children = []
                        for entry in it:
                            if entry.is_dir(follow_symlinks=False) or entry.is_symlink():
                                children.append(entry.path)
                        stack.extend(sorted(children, reverse=True))
                except OSError as exc:
                    emit(failures, {"path":path,"operation":"lstat-or-scandir","errno":exc.errno,"error_type":type(exc).__name__})
                    root_errors += 1
                    errors += 1
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 0)
            pending = len(stack)
            for path in stack:
                emit(coverage, {"path":path,"status":"pending-deadline"})
            row = {"root":root,"status":"deadline" if pending else ("traversed-with-errors" if root_errors else "traversed"),"counts":dict(counts),"errors":root_errors,"pending_directories":pending}
            rows.append(row)
            emit(coverage, row)
    hashes = {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    summary = {"schema":"limen.agent_surface_census.v1","started_at":started,"finished_at":dt.datetime.now(dt.timezone.utc).isoformat(),"roots":rows,"method":"iterative scandir; lstat; no symlink traversal; physical identity=(st_dev,st_ino)","name_predicate":"case-insensitive basename contains codex","depth_limit":None,"prune_patterns":[],"metadata_timeout_seconds":2,"dataless_policy":"record coverage error; do not hydrate cloud directories","excluded_mounts":excluded_mounts,"directory_bytes_semantics":"directory entry st_size only, not recursive storage or reclaimable bytes","physical_directories_scanned":directories,"codex_named_physical_directories":len(matched),"codex_related_aliases":aliases,"errors":errors,"complete":errors == 0 and not any(row["pending_directories"] for row in rows),"consistency":"live metadata observation, not an atomic filesystem snapshot","files":hashes}
    (output / "summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print(json.dumps({k:v for k,v in summary.items() if k not in ("files","excluded_mounts","roots")},indent=2))
    return 0 if summary["complete"] else 2

def verify(output):
    summary = json.loads((output / "summary.json").read_text())
    for name, expected in summary["files"].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != expected:
            raise ValueError("changed evidence: " + name)
    dirs = [json.loads(line) for line in (output / "directories.jsonl").read_text().splitlines()]
    ids = [tuple(row["physical_id"]) for row in dirs]
    if len(ids) != len(set(ids)) or len(ids) != summary["codex_named_physical_directories"]:
        raise ValueError("physical count mismatch")
    print(json.dumps({"integrity":"pass","complete":summary["complete"],"physical_codex_directories":len(ids),"errors":summary["errors"]}))
    return 0 if summary["complete"] else 2

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode",choices=("scan","verify"))
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--root",action="append")
    parser.add_argument("--seconds",type=int,default=600)
    args=parser.parse_args()
    if args.seconds <= 0:
        parser.error("seconds must be positive")
    if args.mode == "verify":
        return verify(args.output)
    roots = args.root or ["/Applications", "/Library", "/opt", "/usr/local", str(Path.home() / "Workspace"), str(Path.home()), "/private", "/System", "/Volumes", "/Users", "/"]
    return scan(roots,args.output,args.seconds)

if __name__ == "__main__":
    raise SystemExit(main())
