#!/usr/bin/env python3
"""Prepare a fresh rollback candidate; never changes the current destination."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            h.update(chunk)
    return h.hexdigest()

def manifest(root):
    result = {}
    def visit(path, relative):
        info = path.lstat()
        row = {"mode":stat.S_IMODE(info.st_mode)}
        if path.is_symlink():
            row.update(kind="symlink",target=os.readlink(path))
        elif stat.S_ISREG(info.st_mode):
            row.update(kind="file",bytes=info.st_size,sha256=digest(path))
        elif stat.S_ISDIR(info.st_mode):
            row.update(kind="directory")
        else:
            raise ValueError("special file requires native recovery owner: " + relative)
        if hasattr(os, "listxattr"):
            row["xattrs"] = {key:hashlib.sha256(os.getxattr(path,key,follow_symlinks=False)).hexdigest() for key in os.listxattr(path,follow_symlinks=False)}
        result[relative] = row
        if row["kind"] == "directory":
            for child in sorted(path.iterdir()):
                visit(child,relative + "/" + child.name)
    visit(root,".")
    return result

def prepare(backup, current, stage, apply):
    backup = backup.absolute()
    current = current.absolute()
    stage = stage.absolute()
    if backup.is_symlink() or not backup.is_dir():
        raise ValueError("backup must be a physical directory")
    if stage.exists() or stage.is_symlink():
        raise ValueError("stage already exists; preserve it and choose a fresh path")
    if not stage.parent.is_dir() or stage.parent.is_symlink():
        raise ValueError("stage parent must be an existing physical directory")
    b, c, s = backup.resolve(), current.resolve(), stage.resolve()
    if any(x == y or x in y.parents or y in x.parents for x,y in ((b,s),(c,s),(b,c))):
        raise ValueError("backup, current, and stage must be disjoint")
    before = manifest(backup)
    current_before = manifest(current) if current.is_dir() and not current.is_symlink() else None
    required = sum(row.get("bytes",0) for row in before.values())
    if shutil.disk_usage(stage.parent).free < required + 64*1024*1024:
        raise ValueError("insufficient full-copy headroom")
    plan = {"schema":"limen.rollback_stage.v1","action":"stage-only","backup":str(backup),"current":str(current),"stage":str(stage),"logical_file_bytes":required,"activation_authorized":False,"database_consistency":"not established by file copy","independent_custody":"not established by staging"}
    if not apply:
        print(json.dumps(plan,indent=2))
        return 0
    stage.mkdir(mode=0o700)
    candidate = stage / "candidate"
    candidate.mkdir()
    try:
        subprocess.run(["/usr/bin/ditto","--rsrc","--extattr","--acl",str(backup),str(candidate)],check=True,timeout=300)
        after = manifest(backup)
        restored = manifest(candidate)
        if before != after or before != restored:
            raise ValueError("backup changed or staged contents/metadata differ")
        if current_before is not None and manifest(current) != current_before:
            raise ValueError("current destination changed during staging; retained, no activation")
        plan.update(verification="byte-mode-xattr-symlink comparison passed",current_preserved=True)
        (stage / "stage-receipt.json").write_text(json.dumps(plan,indent=2)+"\n")
        print(json.dumps(plan,indent=2))
        return 0
    except BaseException:
        (stage / "FAILED-PRESERVED").touch(exist_ok=True)
        raise

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup",type=Path,required=True)
    parser.add_argument("--current",type=Path,required=True)
    parser.add_argument("--stage",type=Path,required=True)
    parser.add_argument("--apply",action="store_true",help="create fresh candidate only; no activation or deletion")
    args = parser.parse_args()
    try:
        return prepare(args.backup,args.current,args.stage,args.apply)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print("rollback-stage: " + str(exc),file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
