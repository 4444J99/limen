#!/usr/bin/env python3
"""Contain the pre-rewrite lineage without publishing what the rewrite removed.

On 2026-10-10 the public history was rewritten (manifest commit 66b2ee71a) to move personal and
third-party records into the private sibling 4444J99/limen--private.  Local checkouts still carry
the pre-rewrite ("old") lineage.  This predicate exits 0 only when:

  A. every old-lineage ref (branch, tag, hidden ref, stash, detached worktree HEAD) is recorded in
     the public ledger with its live tip and class, and the live classification still agrees;
  B. every blob the old lineage holds at a purged path has a hash match in a local clone of
     limen--private;
  C. no old-lineage branch has a push-capable upstream (quarantine form: branch.<b>.remote = "."
     and branch.<b>.pushRemote = ".", so implicit push/pull target the repository itself).

Commit classes (for every old-lineage commit not reachable from the new lineage):
  already-on-new-lineage  patch-id equal to a new-lineage commit, or a rewritten counterpart whose
                          change is byte-identical, or every path it changed already holds its
                          bytes on the new tip;
  purge-equivalent        its counterpart differs only by purged paths and the rewrite's text
                          scrub, or it changed only purged paths (dropped by the rewrite);
  unique-work             anything else; the owning ref needs an owner decision.

Privacy: the public ledger and stdout carry only ref names (40-hex components digested), salted
digests of commit ids, classes, and counts.  Paths, subjects, the learned scrub map, and full ids
stay in --private-dir (mode 0700), which also holds the limen--private bare clone.

Usage:
  python3 scripts/check-prerewrite-containment.py                  # check (exit 0 ⟺ contained)
  python3 scripts/check-prerewrite-containment.py --write-ledger   # reclassify and record
  python3 scripts/check-prerewrite-containment.py --quarantine     # print upstream quarantine cmds
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "receipts" / "privacy" / "prerewrite-containment-20261016.json"
SCHEMA = "limen.prerewrite_containment.v1"
BOUNDARY = "31664a78ba7459bf475416accf7c03d3555f54fc"  # last commit shared by both lineages
MANIFEST_COMMIT = "66b2ee71a1075d652a32a44186d01db258c8adce"  # .gitignore block naming purged paths
MANIFEST_MARKER = "4444J99/limen--private"
NEW_REF = "refs/remotes/origin/main"
QUARANTINE_REMOTE = "."
DIGEST_SALT = "limen-prerewrite-containment:"
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
HEX_TOKEN = re.compile(r"\b[0-9a-f]{7,40}\b")
OID_COMPONENT = re.compile(r"^[0-9a-f]{40}$")
# A hex run of 10+ chars holding both a letter and a digit (dates and plain numbers stay readable).
EMBEDDED_HEX = re.compile(r"(?<![0-9a-f:])(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{10,64}(?![0-9a-f])")
WS_SPLIT = re.compile(r"(\s+)")
CLASSES = ("already-on-new-lineage", "purge-equivalent", "unique-work")
# Agent working-tree snapshot namespaces: never pushed, never commits of record. A purged-path
# version that exists ONLY here was never published, so the rewrite did not purge it; each such
# version must still be recorded in the ledger (and is an owner custody decision in the plan).
CHECKPOINT_NAMESPACES = ("refs/cline/", "refs/codex/")


class ContainmentError(RuntimeError):
    """A redacted, operator-actionable predicate failure."""


def default_private_dir() -> Path:
    staging = os.environ.get("LIMEN_CUSTODY_STAGING_ROOT") or str(ROOT / ".limen-private" / "custody-staging")
    return Path(staging) / "prerewrite-containment-20261016"


def git(*args: str, cwd: Path | None = None, check: bool = True, data: bytes | None = None) -> str:
    proc = subprocess.run(["git", *args], cwd=cwd, input=data, capture_output=True, check=False)
    if check and proc.returncode != 0:
        raise ContainmentError(f"git {args[0]} failed (exit {proc.returncode})")
    return proc.stdout.decode("utf-8", "replace")


def git_ok(*args: str, cwd: Path | None = None) -> bool:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False).returncode == 0


def digest(oid: str) -> str:
    return hashlib.sha256((DIGEST_SALT + oid).encode()).hexdigest()[:24]


def public_ref_name(name: str) -> str:
    """Digest any object id — full or abbreviated — embedded in a ref name.

    Old commit ids must never reach the ledger: GitHub may keep serving them until #2537, so even a
    12-hex abbreviation inside a tag name (`…-detached-<abbrev>-<date>`) is a lookup key.
    """
    name = "/".join(f"oid:{digest(p)}" if OID_COMPONENT.match(p) else p for p in name.split("/"))
    return EMBEDDED_HEX.sub(lambda m: f"oid:{digest(m.group(0))[:12]}", name)


# ── purge manifest ──────────────────────────────────────────────────────────────────────────────


def manifest_patterns() -> list[str]:
    lines = git("show", f"{MANIFEST_COMMIT}:.gitignore").splitlines()
    start = next((i for i, line in enumerate(lines) if MANIFEST_MARKER in line), None)
    if start is None:
        raise ContainmentError("purge manifest block not found in the manifest commit's .gitignore")
    return [line.strip().strip("/") for line in lines[start + 1 :] if line.strip() and not line.startswith("#")]


def is_manifest_path(path: str, patterns: list[str]) -> bool:
    return any(path == p or path.startswith(p + "/") for p in patterns)


def manifest_pathspecs(patterns: list[str]) -> list[str]:
    return [f":(top,literal){p}" for p in patterns]


def excluded_pathspecs(patterns: list[str]) -> list[str]:
    return [".", *(f":(exclude,top,literal){p}" for p in patterns)]


# ── ref inventory and lineage ───────────────────────────────────────────────────────────────────


def inventory() -> list[dict[str, Any]]:
    """Every ref, the stash reflog, and every detached worktree HEAD, peeled to a commit."""
    refs: list[dict[str, Any]] = []
    for line in git("for-each-ref", "--format=%(refname)%00%(objectname)%00%(objecttype)").splitlines():
        name, oid, typ = line.split("\0")
        if typ == "tag":
            oid = git("rev-parse", f"{oid}^{{commit}}").strip()
        elif typ != "commit":
            continue
        kind = (
            "branch"
            if name.startswith("refs/heads/")
            else "remote"
            if name.startswith("refs/remotes/")
            else ("tag" if name.startswith("refs/tags/") else "hidden")
        )
        refs.append({"ref": name, "oid": oid, "kind": kind})
    for i, oid in enumerate(git("reflog", "show", "--format=%H", "refs/stash", "--", check=False).split()):
        refs.append({"ref": f"stash@{{{i}}}", "oid": oid, "kind": "stash"})
    checked_out: dict[str, str] = {}
    for block in git("worktree", "list", "--porcelain").strip().split("\n\n"):
        fields = dict(line.split(" ", 1) if " " in line else (line, "") for line in block.splitlines())
        path = fields.get("worktree", "")
        if "branch" in fields:
            checked_out[fields["branch"]] = path
        elif fields.get("HEAD"):
            refs.append({"ref": f"worktree-head:{path}", "oid": fields["HEAD"], "kind": "detached-worktree"})
    for item in refs:
        if item["ref"] in checked_out:
            item["worktree"] = checked_out[item["ref"]]
    return refs


def lineage(oid: str, cache: dict[str, str]) -> str:
    """contained | old | new | pre-boundary relative to the new lineage tip."""
    if oid in cache:
        return cache[oid]
    if git_ok("merge-base", "--is-ancestor", oid, NEW_REF):
        result = "contained"
    elif not git_ok("merge-base", "--is-ancestor", BOUNDARY, oid):
        result = "pre-boundary"
    else:
        out = git("rev-list", "--boundary", oid, f"^{NEW_REF}").splitlines()
        edges = [line[1:] for line in out if line.startswith("-")]
        result = "old" if any(git_ok("merge-base", "--is-ancestor", e, BOUNDARY) for e in edges) else "new"
    cache[oid] = result
    return result


# ── commit classification ───────────────────────────────────────────────────────────────────────


def patch_ids(revs: list[str]) -> dict[str, str]:
    log = subprocess.run(
        ["git", "log", "-p", "--no-merges", "--no-color", "--format=commit %H", *revs], capture_output=True, check=True
    ).stdout
    out = subprocess.run(["git", "patch-id", "--stable"], input=log, capture_output=True, check=True).stdout.decode()
    return {commit: pid for pid, commit in (line.split() for line in out.splitlines())}


def commit_meta(revs: list[str]) -> dict[str, dict[str, Any]]:
    meta: dict[str, dict[str, Any]] = {}
    out = git("log", "--format=%H%x00%P%x00%at%x00%s", *revs)
    for line in out.splitlines():
        oid, parents, at, subject = line.split("\0", 3)
        meta[oid] = {"parents": parents.split(), "key": (at, HEX_TOKEN.sub("<oid>", subject)), "subject": subject}
    return meta


def commit_diff(oid: str, parents: list[str], patterns: list[str]) -> list[str]:
    base = parents[0] if parents else EMPTY_TREE
    out = git("diff", "--no-color", "--no-renames", "--no-ext-diff", base, oid, "--", *excluded_pathspecs(patterns))
    return [line for line in out.splitlines() if not line.startswith("index ")]


def learn_scrub_map(pairs: list[tuple[str, str]], patterns: list[str]) -> dict[str, str]:
    """Token-level replacements the rewrite applied, learned from counterpart tree diffs."""
    learned: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for old, new in pairs:
        out = git(
            "diff",
            "--word-diff=porcelain",
            "--word-diff-regex=[^[:space:]]+",
            "-U0",
            old,
            new,
            "--",
            *excluded_pathspecs(patterns),
        ).splitlines()
        for a, b in zip(out, out[1:], strict=False):
            if a.startswith("-") and not a.startswith("---") and b.startswith("+") and not b.startswith("+++"):
                learned[a[1:]][b[1:]] += 1
    scrub: dict[str, str] = {}
    for old_tok, news in learned.items():
        if len(news) == 1:
            scrub[old_tok] = next(iter(news))
    return scrub


def core_replacements(scrub: dict[str, str]) -> list[tuple[str, str]]:
    """Reduce token pairs to their differing cores (shared prefix/suffix stripped), longest first."""
    cores: dict[str, str] = {}
    for old, new in scrub.items():
        p = 0
        while p < min(len(old), len(new)) and old[p] == new[p]:
            p += 1
        s = 0
        while s < min(len(old), len(new)) - p and old[-1 - s] == new[-1 - s]:
            s += 1
        core_old, core_new = old[p : len(old) - s], new[p : len(new) - s]
        if len(core_old) >= 3 and cores.get(core_old, core_new) == core_new:
            cores[core_old] = core_new
    return sorted(cores.items(), key=lambda kv: -len(kv[0]))


def apply_scrub(lines: list[str], scrub: dict[str, str], cores: list[tuple[str, str]]) -> list[str]:
    """Whole-token replacement, then in-token core replacement (scrubs glued to punctuation/`_`)."""
    result = []
    for line in lines:
        mapped = "".join(scrub.get(tok, tok) for tok in WS_SPLIT.split(line))
        for old, new in cores:
            if old in mapped:
                mapped = mapped.replace(old, new)
        result.append(mapped)
    return result


def _line_matches(line: str, target: str, cores: list[tuple[str, str]]) -> bool:
    """True when some subset of the in-line cores turns `line` into `target`.

    The rewrite replaced some casings of a scrubbed token and kept others (a lowercase repository
    slug survives beside an uppercase constant that was replaced), so a core is applied per line
    only where it is needed. Lines rarely hold more than three distinct cores; the cap bounds cost.
    """
    if line == target:
        return True
    present = [c for c in cores if c[0] in line][:6]
    for mask in range(1, 1 << len(present)):
        candidate = line
        for i, (old, new) in enumerate(present):
            if mask >> i & 1:
                candidate = candidate.replace(old, new)
        if candidate == target:
            return True
    return False


def scrub_equivalent(mine: list[str], theirs: list[str], scrub: dict[str, str], cores: list[tuple[str, str]]) -> bool:
    """Line-by-line equality after the whole-token scrub plus a per-line choice of core scrubs."""
    if len(mine) != len(theirs):
        return False
    tokens_only = apply_scrub(mine, scrub, [])
    return all(_line_matches(t, b, cores) for t, b in zip(tokens_only, theirs, strict=True))


def content_on_new_tip(oid: str, parents: list[str], patterns: list[str]) -> bool:
    base = parents[0] if parents else EMPTY_TREE
    changed = [
        p
        for p in git("diff", "--name-only", "--no-renames", base, oid, "--", *excluded_pathspecs(patterns)).split("\n")
        if p
    ]
    if not changed:
        return False
    mine = dict(_ls_blobs(oid, changed))
    theirs = dict(_ls_blobs(NEW_REF, changed))
    return all(mine.get(p) == theirs.get(p) for p in changed)


def _ls_blobs(rev: str, paths: list[str]) -> list[tuple[str, str]]:
    out = git("ls-tree", "-r", "-z", rev, "--", *(f":(top,literal){p}" for p in paths))
    rows = []
    for entry in out.split("\0"):
        if entry:
            info, path = entry.split("\t", 1)
            rows.append((path, info.split()[2]))
    return rows


def classify(old_refs: list[dict[str, Any]], patterns: list[str], private_dir: Path, learn: bool) -> dict[str, Any]:
    tips = sorted({r["oid"] for r in old_refs})
    old_only = commit_meta([*tips, f"^{NEW_REF}"]) if tips else {}
    new_side = commit_meta([NEW_REF, f"^{BOUNDARY}"])
    new_pids = set(patch_ids([NEW_REF, f"^{BOUNDARY}"]).values())
    old_pids = patch_ids([*tips, f"^{NEW_REF}"]) if tips else {}
    by_key: dict[tuple[str, str], list[str]] = collections.defaultdict(list)
    for oid, m in new_side.items():
        by_key[m["key"]].append(oid)

    map_path = private_dir / "replace-map.learned.json"
    pending = [oid for oid in old_only if old_pids.get(oid) not in new_pids]
    if learn:
        pairs = [(oid, by_key[old_only[oid]["key"]][0]) for oid in pending if by_key.get(old_only[oid]["key"])]
        scrub = learn_scrub_map(pairs, patterns)
        _write_private(map_path, {"scrub": scrub})
    else:
        try:
            scrub = json.loads(map_path.read_text())["scrub"]
        except (OSError, ValueError, KeyError) as exc:
            raise ContainmentError("private scrub map missing; run --write-ledger on the custody host") from exc
    cores = core_replacements(scrub)
    map_digest = hashlib.sha256(json.dumps(scrub, sort_keys=True).encode()).hexdigest()

    classes: dict[str, dict[str, str]] = {}
    for oid, m in old_only.items():
        if old_pids.get(oid) in new_pids:
            classes[oid] = {"class": "already-on-new-lineage", "evidence": "patch-id"}
            continue
        mine = commit_diff(oid, m["parents"], patterns)
        verdict = None
        for cand in by_key.get(m["key"], []):
            theirs = commit_diff(cand, new_side[cand]["parents"], patterns)
            if mine == theirs:
                verdict = {"class": "already-on-new-lineage", "evidence": "counterpart-identical-change"}
            elif scrub_equivalent(mine, theirs, scrub, cores):
                verdict = {"class": "purge-equivalent", "evidence": "counterpart-equal-after-scrub"}
            if verdict:
                verdict["counterpart"] = cand
                break
        if verdict is None and not mine:
            touched = git("diff", "--name-only", m["parents"][0] if m["parents"] else EMPTY_TREE, oid).split()
            if any(is_manifest_path(p, patterns) for p in touched):
                verdict = {"class": "purge-equivalent", "evidence": "only-purged-paths"}
            else:
                verdict = {"class": "already-on-new-lineage", "evidence": "empty-change"}
        if verdict is None and content_on_new_tip(oid, m["parents"], patterns):
            verdict = {"class": "already-on-new-lineage", "evidence": "content-on-new-tip"}
        classes[oid] = verdict or {"class": "unique-work", "evidence": "no-equivalent"}
    return {"commits": classes, "meta": old_only, "map_digest": map_digest}


# ── purged-blob custody ─────────────────────────────────────────────────────────────────────────


def is_checkpoint(ref: str) -> bool:
    return ref.startswith(CHECKPOINT_NAMESPACES)


def purged_blobs(old_refs: list[dict[str, Any]], patterns: list[str]) -> dict[str, set[str]]:
    tips = sorted({r["oid"] for r in old_refs})
    if not tips:
        return {}
    commits = git("log", "--format=%H", *tips, f"^{NEW_REF}", "--", *manifest_pathspecs(patterns)).split()
    blobs: dict[str, set[str]] = collections.defaultdict(set)
    for oid in commits:
        for path, blob in _ls_blobs_manifest(oid, patterns):
            blobs[path].add(blob)
    return blobs


def _ls_blobs_manifest(rev: str, patterns: list[str]) -> list[tuple[str, str]]:
    out = git("ls-tree", "-r", "-z", rev, "--", *manifest_pathspecs(patterns))
    rows = []
    for entry in out.split("\0"):
        if entry:
            info, path = entry.split("\t", 1)
            if info.split()[1] == "blob":
                rows.append((path, info.split()[2]))
    return rows


def private_has(oids: set[str], private_git: Path) -> set[str]:
    if not oids:
        return set()
    if not (private_git / "HEAD").exists():
        raise ContainmentError("limen--private clone missing from the private dir; clone it read-only first")
    data = ("\n".join(sorted(oids)) + "\n").encode()
    out = git("cat-file", "--batch-check=%(objectname) %(objecttype)", cwd=private_git, data=data)
    return {line.split()[0] for line in out.splitlines() if line.endswith(" blob") or line.endswith(" commit")}


def private_reaches(oid: str, private_git: Path) -> bool:
    return bool(git("for-each-ref", "--contains", oid, "--count=1", cwd=private_git, check=False).strip())


# ── upstream quarantine ─────────────────────────────────────────────────────────────────────────


def upstream_state(branch_ref: str) -> dict[str, Any]:
    name = branch_ref[len("refs/heads/") :]
    remotes = set(git("remote").split())

    def cfg(key: str) -> str:
        return git("config", "--get", key, check=False).strip()

    remote, push_remote, merge = (
        cfg(f"branch.{name}.remote"),
        cfg(f"branch.{name}.pushRemote"),
        cfg(f"branch.{name}.merge"),
    )
    effective_push = push_remote or cfg("remote.pushDefault") or remote or "origin"
    capable = [r for r in {remote, effective_push} if r and r != QUARANTINE_REMOTE and (r in remotes or ":" in r)]
    return {
        "branch": name,
        "remote": remote or None,
        "merge": merge or None,
        "push_remote": push_remote or None,
        "push_capable": bool(capable),
        "quarantined": remote == QUARANTINE_REMOTE and push_remote == QUARANTINE_REMOTE,
    }


# ── assembly ────────────────────────────────────────────────────────────────────────────────────


def _write_private(path: Path, obj: Any) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True)
    os.replace(tmp, path)


def evaluate(private_dir: Path, learn: bool) -> dict[str, Any]:
    if not git_ok("cat-file", "-e", f"{MANIFEST_COMMIT}^{{commit}}"):
        raise ContainmentError("manifest commit absent; fetch origin first")
    patterns = manifest_patterns()
    cache: dict[str, str] = {}
    refs = inventory()
    for r in refs:
        r["lineage"] = lineage(r["oid"], cache)
    old_refs = [r for r in refs if r["lineage"] == "old"]
    result = classify(old_refs, patterns, private_dir, learn)
    commits = result["commits"]
    private_git = private_dir / "limen--private.git"

    ref_rows = []
    for r in sorted(old_refs, key=lambda x: x["ref"]):
        reach = git("rev-list", r["oid"], f"^{NEW_REF}").split()
        counts = collections.Counter(commits[c]["class"] for c in reach)
        cls = next(c for c in reversed(CLASSES) if counts.get(c)) if counts else "already-on-new-lineage"
        row = {
            "ref": public_ref_name(r["ref"]),
            "kind": r["kind"],
            "tip": digest(r["oid"]),
            "class": cls,
            "commits": {c: counts.get(c, 0) for c in CLASSES},
            "private_custody": private_reaches(r["oid"], private_git) if (private_git / "HEAD").exists() else None,
        }
        if r.get("worktree"):
            row["worktree"] = r["worktree"]
        if r["kind"] == "branch":
            st = upstream_state(r["ref"])
            row["upstream"] = {k: st[k] for k in ("remote", "push_remote", "push_capable", "quarantined")}
            row["remote_counterpart"] = git_ok(
                "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{st['branch']}"
            )
        ref_rows.append(row)

    blobs = purged_blobs([r for r in old_refs if not is_checkpoint(r["ref"])], patterns)
    checkpoint = purged_blobs([r for r in old_refs if is_checkpoint(r["ref"])], patterns)
    published = set().union(*blobs.values()) if blobs else set()
    checkpoint_all = set().union(*checkpoint.values()) if checkpoint else set()
    present = private_has(published | checkpoint_all, private_git)
    paths = set(blobs) | set(checkpoint)
    unheld_paths = sorted(p for p in paths if not (blobs.get(p, set()) | checkpoint.get(p, set())) & present)
    unmatched = {oid: v for oid, v in commits.items() if v["evidence"] != "patch-id"}
    return {
        "patterns": patterns,
        "refs": ref_rows,
        "raw_refs": old_refs,
        "commits": commits,
        "unmatched": unmatched,
        "meta": result["meta"],
        "map_digest": result["map_digest"],
        "blobs": blobs,
        "blobs_missing": sorted(published - present),
        "checkpoint_only_missing": sorted(checkpoint_all - published - present),
        "paths": paths,
        "unheld_paths": unheld_paths,
        "lineage_counts": collections.Counter(r["lineage"] for r in refs),
    }


def public_ledger(ev: dict[str, Any]) -> dict[str, Any]:
    by_class = collections.Counter(v["class"] for v in ev["commits"].values())
    return {
        "schema": SCHEMA,
        "issue": "4444J99/limen#2537",
        "boundary": BOUNDARY,
        "manifest_commit": MANIFEST_COMMIT,
        "new_ref": NEW_REF,
        "private_repository": "4444J99/limen--private",
        "scrub_map_sha256": ev["map_digest"],
        "summary": {
            "old_lineage_refs": len(ev["refs"]),
            "old_only_commits": len(ev["commits"]),
            "commits_by_class": {c: by_class.get(c, 0) for c in CLASSES},
            "unmatched_commits": len(ev["unmatched"]),
            "purged_paths": len(ev["paths"]),
            "purged_paths_without_private_match": len(ev["unheld_paths"]),
            "purged_blobs": sum(len(b) for b in ev["blobs"].values()),
            "purged_blobs_missing_in_private": len(ev["blobs_missing"]),
            "checkpoint_only_blobs_missing_in_private": len(ev["checkpoint_only_missing"]),
        },
        "checkpoint_only_unpublished_blobs": [digest(b) for b in ev["checkpoint_only_missing"]],
        "refs": ev["refs"],
        "unmatched_commits": sorted(
            (
                {"commit": digest(oid), **{k: v for k, v in c.items() if k != "counterpart"}}
                for oid, c in ev["unmatched"].items()
            ),
            key=lambda x: x["commit"],
        ),
    }


def private_evidence(ev: dict[str, Any]) -> dict[str, Any]:
    return {
        "refs": [{"ref": r["ref"], "oid": r["oid"], "kind": r["kind"]} for r in ev["raw_refs"]],
        "unmatched": {
            oid: {**c, "subject": ev["meta"][oid]["subject"], "digest": digest(oid)}
            for oid, c in ev["unmatched"].items()
        },
        "purged_blobs": {p: sorted(b) for p, b in sorted(ev["blobs"].items())},
        "blobs_missing": ev["blobs_missing"],
        "checkpoint_only_missing": ev["checkpoint_only_missing"],
        "unheld_paths": ev["unheld_paths"],
    }


def check(ev: dict[str, Any], ledger: dict[str, Any]) -> list[str]:
    failures = []
    if ledger.get("schema") != SCHEMA:
        failures.append(f"A: ledger schema is not {SCHEMA}")
    recorded = {(r["ref"], r["tip"]): r for r in ledger.get("refs", [])}
    live = {(r["ref"], r["tip"]): r for r in ev["refs"]}
    for key, row in live.items():
        rec = recorded.get(key)
        if rec is None:
            failures.append(f"A: unclassified old-lineage ref {key[0]} (tip {key[1]})")
        elif rec.get("class") != row["class"]:
            failures.append(f"A: {key[0]} classified {rec.get('class')} but live evidence says {row['class']}")
    for key in recorded.keys() - live.keys():
        failures.append(f"A: ledger ref {key[0]} (tip {key[1]}) no longer live — re-record with --write-ledger")
    if ledger.get("scrub_map_sha256") != ev["map_digest"]:
        failures.append("A: private scrub map differs from the one the ledger was classified with")
    if ev["blobs_missing"]:
        failures.append(f"B: {len(ev['blobs_missing'])} purged blob(s) have no hash match in limen--private")
    if ev["unheld_paths"]:
        failures.append(f"B: {len(ev['unheld_paths'])} purged path(s) have no version held in limen--private")
    if not ev["blobs"]:
        failures.append("B: no purged blobs found in the old lineage — manifest or boundary is wrong")
    recorded_checkpoint = set(ledger.get("checkpoint_only_unpublished_blobs", []))
    for b in ev["checkpoint_only_missing"]:
        if digest(b) not in recorded_checkpoint:
            failures.append(f"B: unrecorded checkpoint-only purged-path version {digest(b)}")
    for row in ev["refs"]:
        up = row.get("upstream")
        if up and up["push_capable"]:
            failures.append(f"C: {row['ref']} has a push-capable upstream")
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--private-dir", type=Path, default=default_private_dir())
    ap.add_argument("--ledger", type=Path, default=LEDGER)
    ap.add_argument("--write-ledger", action="store_true", help="reclassify, write public ledger + private evidence")
    ap.add_argument("--quarantine", action="store_true", help="print the git config commands that quarantine upstreams")
    args = ap.parse_args(argv)
    try:
        ev = evaluate(args.private_dir, learn=args.write_ledger)
        if args.quarantine:
            for row in ev["refs"]:
                up = row.get("upstream")
                if up and not up["quarantined"]:
                    name = row["ref"][len("refs/heads/") :]
                    print(f"git config branch.{name}.remote {QUARANTINE_REMOTE}")
                    print(f"git config branch.{name}.merge refs/heads/{name}")
                    print(f"git config branch.{name}.pushRemote {QUARANTINE_REMOTE}")
            return 0
        if args.write_ledger:
            _write_private(args.private_dir / "evidence.json", private_evidence(ev))
            args.ledger.parent.mkdir(parents=True, exist_ok=True)
            args.ledger.write_text(json.dumps(public_ledger(ev), indent=1, sort_keys=True) + "\n")
        ledger = json.loads(args.ledger.read_text())
        failures = check(ev, ledger)
    except (ContainmentError, OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"prerewrite-containment: ERROR {exc}", file=sys.stderr)
        return 2
    summary = public_ledger(ev)["summary"]
    print(f"prerewrite-containment: refs by lineage {dict(ev['lineage_counts'])}")
    print(f"prerewrite-containment: {json.dumps(summary, sort_keys=True)}")
    for f in failures:
        print(f"FAIL {f}")
    print(
        "prerewrite-containment: CONTAINED" if not failures else f"prerewrite-containment: {len(failures)} failure(s)"
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
