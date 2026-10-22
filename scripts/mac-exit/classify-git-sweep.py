#!/usr/bin/env python3
"""Classify a scripts/mac-exit/git-sweep.sh TSV by whether each entry's work is provably elsewhere.

Repo-level facts (a remote, unpushed commits, stashes) come from kind=repo and kind=bare rows only: in a worktree
row `rev-list --branches` and `stash list` report the shared repository, so counting them per worktree repeats
one repo's exposure on every row. A bare repository is a repository of its own with no working tree, so it carries
the repo-level facts and nothing per-worktree. Every row contributes what is truly per-HEAD: uncommitted entries
and a detached HEAD that no remote branch contains (a main checkout can sit on a detached HEAD holding commits
no ref names, so the rule applies to every kind).

Entries under cache, probe, fixture and already-preserved-copy paths are split off as disposable.

The sweep columns are a local view and say nothing about what a remote holds. With --remote-held (the prover's
remote-held.tsv) two more facts are judged for every PRESENT row, so work the sweep calls safe still reaches the producer:
  remote-not-proven  the row's realpath is not named in any repository's `paths`, or the repository's verdict is not
                     exactly PROVEN-ALL, or its `gaps` are not empty (a proof the predicate would not trust);
  filtered-content   a non-bare checkout has a tracked path with a `filter` attribute (clean/smudge filter, filter=lfs)
                     whose working-tree bytes differ from the index blob: git stores the filter's output, so no
                     remote and no status shows those bytes. A file missing from the work tree is not a difference; a
                     git read that fails counts as a difference. Same rule as the predicate: `git ls-files -s -z`,
                     `git check-attr --stdin -z filter`, `git hash-object --no-filters --stdin-paths`.
The file must end in one full-width `#END rows=N` row (N = its data rows) and carry the columns repo, common_dir, verdict,
paths and gaps; otherwise nothing is written and the exit code is 65. A ref that moved after the proof needs a fresh proof
before this runs: the predicate fails such a row closed. Without --remote-held the output is exactly the sweep-only view.

  python3 scripts/mac-exit/classify-git-sweep.py git.tsv --out real.tsv     # exit 0; the TSV is the finding
  python3 scripts/mac-exit/classify-git-sweep.py git.tsv --out real.tsv --remote-held PROVE_OUT/remote-held.tsv
"""

from __future__ import annotations

import argparse
import csv
import os
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path

DISPOSABLE_MARKERS = (
    "/_agents/cache/",
    "/.tmp/plugins",
    "/.staging/",
    "/custody-staging/",
    "/pytest-fixtures",
    "/legacy-home/preserved-repos/",
    "/.agent-runtime/codex/.tmp/",
)
FIELDS = ("path", "kind", "branch", "remote", "dirty", "unpushed", "stashes", "reasons")
REPO_LEVEL_KINDS = ("repo", "bare")


def reasons_for(row: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    if row["kind"] in REPO_LEVEL_KINDS:
        if row["remote"] == "NONE":
            reasons.append("no-origin")
        if row["unpushed"] not in ("0", ""):
            reasons.append("unpushed")
        if row["stashes"] not in ("0", ""):
            reasons.append("stash")
    if row["dirty"] not in ("0", ""):
        reasons.append("dirty")
    if row["branch"] == "(detached)" and row["head_remote_branches"] == "0":
        reasons.append("detached-head-on-no-remote-branch")
    return reasons


END_MARK = "#END"
HELD_COLS = ("repo", "common_dir", "verdict", "paths", "gaps")
EX_DATAERR = 65
GIT_TIMEOUT_SEC = 600
FILTER_UNSET = (b"unspecified", b"unset")


class HeldError(Exception):
    pass


def load_remote_held(path: Path) -> dict[str, list[tuple[str, str]]]:
    """{realpath of a checkout: [(verdict, gaps) of every repository row naming it]} from the prover's remote-held.tsv.
    Raises HeldError unless the file is newline-terminated, has the needed columns, whole rows, and exactly one full-width
    `#END rows=N` row, last, with N the number of data rows."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise HeldError(f"cannot read {path}: {exc}") from exc
    lines = text.split("\n")  # not splitlines(): it would also split inside a cell on \x85,   and friends
    if lines.pop() != "" or not lines:
        raise HeldError(f"{path} does not end in a newline or is empty: cut short")
    header = lines[0].split("\t")
    missing = [c for c in HELD_COLS if c not in header]
    if missing:
        raise HeldError(f"{path} lacks the column(s) {', '.join(missing)}")
    ends = [i for i, ln in enumerate(lines) if ln.startswith(END_MARK)]
    if ends != [len(lines) - 1] or len(lines) < 2:
        raise HeldError(f"{path} needs exactly one `#END rows=N` row, as its last line")
    cells = lines[-1].split("\t")
    data = lines[1:-1]
    if cells[0] != f"{END_MARK} rows={len(data)}" or len(cells) != len(header) or any(c != END_MARK for c in cells[1:]):
        raise HeldError(f"{path}: completion row does not say rows={len(data)} at full width")
    held: dict[str, list[tuple[str, str]]] = {}
    for n, line in enumerate(data, start=2):
        row = line.split("\t")
        if len(row) != len(header):
            raise HeldError(f"{path} line {n} has {len(row)} cells, the header {len(header)}")
        fact = dict(zip(header, row, strict=True))
        for element in fact["paths"].split(";"):
            if element:
                held.setdefault(os.path.realpath(element), []).append((fact["verdict"], fact["gaps"]))
    return held


def remote_not_proven(path: str, held: dict[str, list[tuple[str, str]]]) -> bool:
    named = held.get(os.path.realpath(path))
    return not named or any(verdict != "PROVEN-ALL" or gaps.strip() for verdict, gaps in named)


def git(path: str, *args: str, data: bytes = b"") -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_NO_LAZY_FETCH": "1", "LC_ALL": "C"}
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", path, *args],
        input=data,
        capture_output=True,
        env=env,
        timeout=GIT_TIMEOUT_SEC,
        check=False,
    )


def filtered_content(path: str) -> bool:
    """True when a tracked path with a filter attribute holds working-tree bytes the index blob does not (or git cannot say)."""
    try:
        staged = git(path, "ls-files", "-s", "-z")
        if staged.returncode != 0:
            return True
        index: dict[bytes, tuple[bytes, bytes, bytes]] = {}  # name -> (mode, blob id, stage)
        for entry in (e for e in staged.stdout.split(b"\0") if e):
            head, _, name = entry.partition(b"\t")
            mode, blob, stage = head.split(b" ")
            if stage != b"0" or name not in index:
                index[name] = (mode, blob, stage)
        if not index:
            return False
        attrs = git(path, "check-attr", "--stdin", "-z", "filter", data=b"\0".join(index) + b"\0")
        toks = [t for t in attrs.stdout.split(b"\0") if t]
        if attrs.returncode != 0 or len(toks) % 3:
            return True
        names = [toks[i] for i in range(0, len(toks), 3) if toks[i + 2] not in FILTER_UNSET]
        check: list[bytes] = []
        for name in names:
            mode, _blob, stage = index[name]
            if stage != b"0":
                return True  # an unmerged path: what the work tree holds is not any one stored blob
            if mode not in (b"100644", b"100755"):
                continue  # a symlink or a gitlink has no file bytes to compare
            try:
                st = os.lstat(os.path.join(os.fsencode(path), name))
            except OSError:
                continue  # missing from the work tree: not a difference
            if not stat.S_ISREG(st.st_mode):
                continue
            if b"\n" in name:
                return True  # --stdin-paths is line based; refuse to guess
            check.append(name)
        if not check:
            return False
        hashed = git(path, "hash-object", "--no-filters", "--stdin-paths", data=b"\n".join(check) + b"\n")
        ids = hashed.stdout.split()
        if hashed.returncode != 0 or len(ids) != len(check):
            return True
        return any(got != index[name][1] for name, got in zip(check, ids, strict=True))
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tsv", type=Path, help="git.tsv written by git-sweep.sh")
    parser.add_argument("--out", type=Path, required=True, help="where to write the real-exposure TSV")
    parser.add_argument(
        "--remote-held",
        type=Path,
        default=None,
        help="the prover's remote-held.tsv: also list every present row it does not prove PROVEN-ALL with no gaps "
        "(remote-not-proven) and every checkout holding filter-attribute bytes the index lacks (filtered-content)",
    )
    args = parser.parse_args()

    held = None
    if args.remote_held is not None:
        try:
            held = load_remote_held(args.remote_held)
        except HeldError as exc:
            print(f"classify-git-sweep: refusing, nothing written: {exc}", file=sys.stderr)
            return EX_DATAERR

    with args.tsv.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh, delimiter="\t"))

    tally: Counter[str] = Counter()
    safe: Counter[str] = Counter()
    disposable = 0
    real: list[dict[str, str]] = []
    for row in rows:
        reasons = reasons_for(row)
        if held is not None and os.path.isdir(row["path"]):
            if remote_not_proven(row["path"], held):
                reasons.append("remote-not-proven")
            if row["kind"] != "bare" and filtered_content(row["path"]):
                reasons.append("filtered-content")
        if not reasons:
            safe[row["kind"]] += 1
            continue
        if any(marker in row["path"] for marker in DISPOSABLE_MARKERS):
            disposable += 1
            continue
        for reason in reasons:
            tally[f"{row['kind']}:{reason}"] += 1
        real.append({**row, "reasons": ",".join(reasons)})

    with args.out.open("w", encoding="utf-8") as out:
        out.write("\t".join(FIELDS) + "\n")
        for row in sorted(real, key=lambda r: r["path"]):
            out.write("\t".join(row[f] for f in FIELDS) + "\n")

    kinds = Counter(r["kind"] for r in rows)
    print(f"entries={len(rows)} repos={kinds['repo']} worktrees={kinds['worktree']} bare={kinds['bare']}")
    print(
        f"safe repos={safe['repo']} safe worktrees={safe['worktree']} safe bare={safe['bare']} "
        f"disposable={disposable} real={len(real)}"
    )
    for key, val in sorted(tally.items()):
        print(f"  {key}: {val}")
    print(f"real-exposure TSV: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
