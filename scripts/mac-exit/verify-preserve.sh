#!/usr/bin/env bash
# verify-preserve.sh <real.tsv> <run-dir> [supplementary-run-dir ...]
#
# Independent verification of a preserve-git.sh run. It does NOT trust the producer's bookkeeping:
#   - recomputes every row's git common dir and slug from real.tsv itself (own slug implementation),
#   - re-runs `git bundle verify` on every bundle (full bundles inside an EMPTY scratch bare repo, so they must be
#     self-contained; head bundles against their source repo, which holds their prerequisites),
#   - streams every bundle's pack through `git unpack-objects -n` (checksums + zlib of every object, writes nothing),
#   - runs `tar -tf` on every tar and compares the entry count with the count recorded at creation time; raw git-dir tars
#     must also contain HEAD,
#   - recomputes from live git, for every common dir, what a bundle drops (commits reachable only from a reflog, per-worktree
#     refs, LFS or git-annex objects, submodule git dirs, an LFS store moved outside the git dir by lfs.storage) and checks the
#     run holds it: the raw git-dir copy must contain every such commit's object, ref file and object, LFS/annex file and
#     modules/ entry; the lfs-storage-tar every file of the relocated store; and for every checkout, the filtered-tar exactly
#     the working-tree files of the tracked paths that have a `filter` attribute (credential-pattern and >2 GiB files excepted),
#   - recomputes the sha256 of every file against MANIFEST.tsv (reads with F_NOCACHE),
#   - checks consistency: unique common dirs == full bundles (ok+empty) + raw git-dir tars + items covered by a
#     supplementary run; every dirty row has its snapshots; every detached row has a head bundle; every unresolved row has
#     its raw tar; extra stash entries have patches; no file in the run directory is missing from the manifest,
#   - UNBORN-HEAD rows (no commits): every row with staged index entries must be covered by a staged-tar + git-dir tar of
#     this run, or by a `covered-by:<path under the destination root>` annotation whose copy is independently checked
#     (git repo present, same number of staged entries); otherwise the run FAILS,
#   - a failed item counts as covered only by a raw git-dir tar in the same run, or by an ok item for the same source in a
#     supplementary run whose own RESULT.txt starts with PASS.
#   - a raw git-dir copy must not hold a `config` / `config.worktree` carrying a user:password@ URL (preserve-git.sh leaves them
#     out, listed in dirty/credential-skipped.txt), and the verifier does not demand those members,
# Writes <run-dir>/RESULT.txt (first line PASS only when everything is consistent with zero failures, else FAIL; the second
# line names the run, a later `manifest_sha256=` line pins the MANIFEST.tsv the verdict is about).
# Read-only toward every repository and never uses the network; scratch files live under PRESERVE_SCRATCH
# (default ${TMPDIR:-/tmp}/preserve-git-scratch).
# Exit 0 on PASS, 1 on FAIL.

set -u
export GIT_OPTIONAL_LOCKS=0
export GIT_NO_LAZY_FETCH=1
export LC_ALL=C

[ $# -ge 2 ] || { echo "usage: $0 <real.tsv> <run-dir> [supplementary-run-dir ...]" >&2; exit 64; }
TSV=$1
RUN=$2
shift 2
[ -f "$TSV" ] || { echo "no such tsv: $TSV" >&2; exit 66; }
[ -f "$RUN/MANIFEST.tsv" ] || { echo "no MANIFEST.tsv in $RUN" >&2; exit 66; }

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
SCR="${PRESERVE_SCRATCH:-${TMPDIR:-/tmp}/preserve-git-scratch}/verify-$STAMP"
mkdir -p "$SCR" || exit 73
command git init --bare -q "$SCR/verify.git" || exit 73

python3 -I - "$TSV" "$RUN" "$SCR" "$@" <<'PY'
import collections
import csv
import fnmatch
import hashlib
import os
import re
import stat
import struct
import subprocess
import sys
import tarfile
import time

tsv, run, scr = sys.argv[1:4]
supp_dirs = sys.argv[4:]
HOME = os.environ["HOME"]
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", LC_ALL="C")
EMPTY_GITDIR = os.path.join(scr, "verify.git")
ROOT = os.path.dirname(os.path.abspath(run))
F_NOCACHE = 48
MANIFEST_COLS = ["item_kind", "status", "slug", "source", "file", "bytes", "sha256", "entries", "note"]
EXEMPT = {"MANIFEST.tsv", "RESULT.txt", "run.log", "verify-preserve.sh"}

failures = []
notes = []
started = time.time()


def fail(msg):
    failures.append(msg)


def note(msg):
    notes.append(msg)


def slugify(p):
    rel = p[len(HOME) + 1:] if p.startswith(HOME + "/") else p.lstrip("/")
    rel = rel.replace("/", "__")[:150]
    return rel + "-" + hashlib.sha256(p.encode()).hexdigest()[:8]


def git(*args, cwd=None, gitdir=None, stdin=subprocess.DEVNULL):
    cmd = ["git", "-c", "core.fsmonitor=false", "-c", "color.ui=false", "-c", "core.pager=cat"]
    if gitdir:
        cmd.append("--git-dir=" + gitdir)
    if cwd:
        cmd += ["-C", cwd]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, env=ENV, stdin=stdin)


def sha256_file(path):
    h = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY)
    try:
        try:
            import fcntl
            fcntl.fcntl(fd, F_NOCACHE, 1)
        except Exception:
            pass
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                break
            h.update(block)
    finally:
        os.close(fd)
    return h.hexdigest()


def pack_check(path):
    """Stream the pack inside a bundle through `git unpack-objects -n` (verifies checksum + every object)."""
    with open(path, "rb") as f:
        sig = f.readline()
        if not sig.startswith((b"# v2 git bundle", b"# v3 git bundle")):
            return False, "bad bundle signature"
        while True:
            line = f.readline()
            if line in (b"\n", b""):
                break
        offset = f.tell()
    with open(path, "rb") as f:
        f.seek(offset)
        r = git("unpack-objects", "-n", "-q", gitdir=EMPTY_GITDIR, stdin=f)
    return r.returncode == 0, (r.stderr.decode("utf-8", "replace").strip().splitlines() or [""])[-1]


def tar_list(path, keep_names=False):
    p = subprocess.Popen(["tar", "-tf", path], stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, env=ENV)
    n = 0
    names = []
    for line in p.stdout:
        n += 1
        if keep_names:
            names.append(line.rstrip(b"\n").decode("utf-8", "replace"))
    err = p.stderr.read().decode("utf-8", "replace").strip()
    rc = p.wait()
    return rc, n, err, names


def count_nul(cmd_out):
    return len([x for x in cmd_out.split(b"\0") if x])


# Credential-pattern files are never copied (preserve-git.sh leaves them out of every file tar); an independent copy of
# its rule, so the expected content of a filtered-tar is derived here and not read back from the producer's skip list.
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
CRED_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx",
    "*.keychain", "*.keychain-db", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    ".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".pgpass",
    "credentials", "credentials.json", "service-account*.json", "*.token", ".token", "token",
    "tokens.json", "secrets.json", "secrets.yaml", "secrets.yml", "*.secret",
]
CRED_DIRS = {".ssh", ".gnupg", ".aws", ".1password", "1password", "keychains", "private_keys"}
SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".pub")


def is_cred(rel):
    parts = [p for p in rel.lower().split("/") if p]
    if not parts:
        return False
    for d in parts[:-1]:
        if d in CRED_DIRS:
            return True
    base = parts[-1]
    if base.endswith(SAFE_SUFFIXES):
        return False
    return any(fnmatch.fnmatchcase(base, pat) for pat in CRED_PATTERNS)


def idx_has(data, sha):
    """Is `sha` in a pack .idx (version 2)? Binary search on the sorted object-name table."""
    if data[:4] != b"\xfftOc" or struct.unpack(">I", data[4:8])[0] != 2:
        return False
    want = bytes.fromhex(sha)
    width = len(want)
    fanout = struct.unpack(">256I", data[8:8 + 1024])
    lo, hi = (fanout[want[0] - 1] if want[0] else 0), fanout[want[0]]
    table = 8 + 1024
    while lo < hi:
        mid = (lo + hi) // 2
        entry = data[table + mid * width:table + (mid + 1) * width]
        if entry == want:
            return True
        if entry < want:
            lo = mid + 1
        else:
            hi = mid
    return False


def inside(path, directory):
    return path == directory or path.startswith(directory + os.sep)


def walk_files(root):
    """Regular files below root (symlinks are not followed and not files)."""
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            p = os.path.join(dirpath, fn)
            if stat.S_ISREG(os.lstat(p).st_mode):
                yield p


def gitdirs_of(common):
    """The common dir, then every linked worktree's admin dir: read with --git-dir so a worktree whose checkout is gone counts."""
    out = [common]
    wt = os.path.join(common, "worktrees")
    if os.path.isdir(wt):
        out += [os.path.join(wt, n) for n in sorted(os.listdir(wt)) if os.path.isfile(os.path.join(wt, n, "HEAD"))]
    return out


CRED_URL = re.compile(rb"://[^/ @]+:[^/ @]+@")
_cred_configs = {}


def credential_configs(common):
    """Paths (relative to the git dir) of every `config` / `config.worktree` below it whose content carries a
    user:password@ URL: preserve-git.sh leaves these out of the raw git-dir copy, so the copy must not hold them and the
    verifier must not demand them. Independent of the producer's own scan; cached per git dir."""
    if common in _cred_configs:
        return _cred_configs[common]
    found = []
    for dirpath, _dirs, files in os.walk(common):
        for fn in files:
            if fn not in ("config", "config.worktree"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                if not stat.S_ISREG(os.lstat(p).st_mode):
                    continue
                with open(p, "rb") as fh:
                    data = fh.read()
            except OSError:
                continue
            if any(CRED_URL.search(line) for line in data.split(b"\n")):
                found.append(os.path.relpath(p, common))
    _cred_configs[common] = found
    return found


def lfs_dir(common):
    """(realpath of the directory git-lfs keeps its store in for this repository, whether lfs.storage names one)."""
    r = git("config", "--type=path", "--get", "lfs.storage", gitdir=common)
    v = r.stdout.decode("utf-8", "replace").strip() if r.returncode == 0 else ""
    configured = r.returncode == 0
    if not v:
        v = os.path.join(common, "lfs")
    elif not os.path.isabs(v):
        v = os.path.join(common, v)  # git-lfs reads a relative lfs.storage relative to the git dir
    return os.path.realpath(v), configured


def requirement(common):
    """What a bundle drops for this common dir, derived from live git: the reasons a raw git-dir copy is required, and the
    things such a copy must then hold. A rule that cannot be evaluated counts as required."""
    req = {"reasons": [], "reflog_commits": [], "wt_refs": [], "lfs_files": [], "modules_paths": []}

    def add(reason):
        if reason not in req["reasons"]:
            req["reasons"].append(reason)

    commits = {}
    for gd in gitdirs_of(common):
        r = git("rev-list", "--reflog", "--not", "--all", gitdir=gd)
        if r.returncode != 0:
            add("reflog-check-failed")
        else:
            for sha in r.stdout.decode().split():
                commits[sha] = True
        r = git("for-each-ref", "--format=%(objectname) %(refname)", "refs/worktree", "refs/bisect", "refs/rewritten", gitdir=gd)
        if r.returncode != 0:
            add("per-worktree-refs-check-failed")
        else:
            for ln in r.stdout.decode("utf-8", "replace").splitlines():
                if ln.strip():
                    sha, _, ref = ln.partition(" ")
                    req["wt_refs"].append((gd, ref, sha))
                    add("per-worktree-refs")
    req["reflog_commits"] = list(commits)
    if commits:
        add("reflog-only")
    lfs, _configured = lfs_dir(common)
    for tag, objects in (("lfs-objects", os.path.join(lfs, "objects") if inside(lfs, common) else None),
                         ("annex-objects", os.path.join(common, "annex", "objects"))):
        if objects and os.path.isdir(objects):
            for p in walk_files(objects):
                req["lfs_files"].append((os.path.relpath(p, common), os.lstat(p).st_size))
                add(tag)
    modules = os.path.join(common, "modules")
    if os.path.isdir(modules):
        left_out = set(credential_configs(common))
        for dirpath, dirs, files in os.walk(modules):
            for n in dirs + files:
                rel = os.path.relpath(os.path.join(dirpath, n), common)
                if not n.startswith("tmp_pack_") and rel not in left_out:
                    req["modules_paths"].append(rel)
        if req["modules_paths"] or os.listdir(modules):
            add("submodule-gitdirs")
    return req


def check_gitdir_content(common, tar_path, req):
    """Everything that made the raw git-dir copy required must be inside it: a list of problems, empty when it is."""
    base = os.path.basename(common)
    try:
        tf = tarfile.open(tar_path, "r:", encoding="utf-8", errors="surrogateescape")
        members = {m.name: m for m in tf}
    except (OSError, tarfile.TarError) as exc:
        return ["the raw git-dir copy is unreadable: %s" % exc]
    problems = []
    with tf:
        def blob(name):
            fh = tf.extractfile(members[name])
            return fh.read() if fh else b""

        idx_blobs = []
        idx_loaded = False

        def has_object(sha):
            nonlocal idx_blobs, idx_loaded
            if "%s/objects/%s/%s" % (base, sha[:2], sha[2:]) in members:
                return True
            if not idx_loaded:
                idx_blobs = [blob(n) for n in members if n.startswith(base + "/objects/pack/") and n.endswith(".idx")]
                idx_loaded = True
            return any(idx_has(d, sha) for d in idx_blobs)

        missing = [sha for sha in req["reflog_commits"] if not has_object(sha)]
        if missing:
            problems.append("%d reflog-only commit(s) are not in the raw git-dir copy, e.g. %s" % (len(missing), missing[0][:12]))
        for gd, ref, sha in req["wt_refs"]:
            rel = os.path.relpath(gd, common)
            name = "%s/%s" % (base, ref) if rel == "." else "%s/%s/%s" % (base, rel, ref)
            m = members.get(name)
            held = m is not None and m.isreg() and blob(name).decode("utf-8", "replace").strip() == sha
            if not held and rel == "." and (base + "/packed-refs") in members:
                held = any(ln.startswith(sha + " ") and ln[len(sha) + 1:].strip() == ref
                           for ln in blob(base + "/packed-refs").decode("utf-8", "replace").splitlines())
            if not held:
                problems.append("per-worktree ref %s of %s is not in the raw git-dir copy with value %s" % (ref, rel, sha[:12]))
            elif not has_object(sha):
                problems.append("the object %s of per-worktree ref %s is not in the raw git-dir copy" % (sha[:12], ref))
        gone = [rel for rel, size in req["lfs_files"]
                if not ((m := members.get("%s/%s" % (base, rel))) is not None and m.isreg() and m.size == size)]
        if gone:
            problems.append("%d LFS/annex object file(s) are not in the raw git-dir copy, e.g. %s" % (len(gone), gone[0]))
        gone = [rel for rel in req["modules_paths"] if ("%s/%s" % (base, rel)) not in members]
        if gone:
            problems.append("%d entr(ies) of modules/ are not in the raw git-dir copy, e.g. %s" % (len(gone), gone[0]))
    return problems


def check_store_content(store, tar_path):
    """Every file of a relocated LFS store must be in its tar (objects with the same size)."""
    base = os.path.basename(store)
    try:
        with tarfile.open(tar_path, "r:", encoding="utf-8", errors="surrogateescape") as tf:
            members = {m.name: m for m in tf}
    except (OSError, tarfile.TarError) as exc:
        return ["the LFS store copy is unreadable: %s" % exc]
    gone = []
    for p in walk_files(store):
        rel = os.path.relpath(p, store)
        m = members.get("%s/%s" % (base, rel))
        if m is None or not m.isreg() or (rel.startswith("objects" + os.sep) and m.size != os.lstat(p).st_size):
            gone.append(rel)
    return ["%d file(s) of the LFS store %s are not in its copy, e.g. %s" % (len(gone), store, gone[0])] if gone else []


def filter_paths(path):
    """Tracked paths of a checkout that have a `filter` attribute (not unspecified, not unset), or None when git cannot say."""
    ls = git("ls-files", "-z", cwd=path)
    if ls.returncode != 0:
        return None
    if not ls.stdout:
        return []
    r = subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-C", path, "check-attr", "--stdin", "-z", "filter"],
        capture_output=True, env=ENV, input=ls.stdout,
    )
    toks = [t for t in r.stdout.split(b"\0") if t]
    if r.returncode != 0 or len(toks) % 3:
        return None
    return [toks[i].decode("utf-8", "surrogateescape") for i in range(0, len(toks), 3) if toks[i + 2] not in (b"unspecified", b"unset")]


def expected_filtered(path, names):
    """{name: size or None for a symlink} of the filter-attribute paths a filtered-tar must hold: present in the working tree
    as a regular file (<= 2 GiB) or a symlink, and not a credential pattern."""
    want = {}
    for n in names:
        try:
            st = os.lstat(os.path.join(path, n))
        except OSError:
            continue
        if is_cred(n):
            continue
        if stat.S_ISLNK(st.st_mode):
            want[n] = None
        elif stat.S_ISREG(st.st_mode) and st.st_size <= MAX_FILE_BYTES:
            want[n] = st.st_size
    return want


waivers = []  # (source, reason, evidence path)


def check_waiver(note_text):
    """`waived-by-conductor: <reason> evidence=<existing absolute file>`: never accepted without both parts."""
    after = note_text.split("waived-by-conductor:", 1)[1]
    m = re.search(r"\bevidence=(\S+)", after)
    reason = re.split(r"\s+evidence=", after, maxsplit=1)[0].strip(" |")
    if len(reason) < 20:
        return False, "waiver has no real reason text"
    if not m:
        return False, "waiver has no evidence=<path> token"
    ev = m.group(1)
    if not os.path.isabs(ev) or not os.path.isfile(ev):
        return False, "waiver evidence file does not exist: %s" % ev
    return True, (reason, ev)


def resolve_covered(note_text):
    """`covered-by:<path>` in a manifest note: a path under the mac-exit root (the destination root's parent)."""
    m = re.search(r"covered-by:(\S+)", note_text or "")
    if not m:
        return None, "no covered-by annotation"
    allowed = os.path.dirname(ROOT)
    copy = os.path.normpath(os.path.join(ROOT, m.group(1)))
    if not copy.startswith(allowed + os.sep):
        return None, "covered-by path escapes %s" % allowed
    if not os.path.isdir(copy):
        return None, "covered-by copy %s does not exist" % copy
    if git("rev-parse", "--git-dir", cwd=copy).returncode != 0:
        return None, "covered-by copy %s is not a git repository" % copy
    return copy, ""


def load_manifest(rundir):
    with open(os.path.join(rundir, "MANIFEST.tsv"), newline="") as f:
        lines = f.read().split("\n")
    out = []
    bad = []
    if lines[0].split("\t") != MANIFEST_COLS:
        bad.append("header is not the expected 9 columns")
    for i, ln in enumerate(lines[1:], start=2):
        if not ln:
            continue
        parts = ln.split("\t")
        if len(parts) != 9:
            bad.append("line %d has %d columns, expected 9" % (i, len(parts)))
            continue
        out.append(dict(zip(MANIFEST_COLS, parts)))
    return out, bad


# ---------------------------------------------------------------- inputs
with open(tsv, newline="") as f:
    rd = csv.reader(f, delimiter="\t")
    header = next(rd)
    rows = [dict(zip(header, r)) for r in rd if r]

items, bad = load_manifest(run)
for b in bad:
    fail("MANIFEST.tsv " + b)
by = collections.defaultdict(list)
for it in items:
    by[(it["item_kind"], it["slug"])].append(it)


def one(kind, slug):
    lst = by.get((kind, slug), [])
    if len(lst) > 1:
        fail("duplicate manifest items for %s %s" % (kind, slug))
    return lst[0] if lst else None


# supplementary runs: ok items there can cover failed items here, but only if that run itself verified PASS
supp_ok = set()
supp_names = []
for sd in supp_dirs:
    try:
        with open(os.path.join(sd, "RESULT.txt")) as f:
            first = f.readline().strip()
    except OSError:
        first = "(no RESULT.txt)"
    if first != "PASS":
        fail("supplementary run %s is not verified PASS (RESULT first line: %s)" % (sd, first))
        continue
    sitems, sbad = load_manifest(sd)
    for b in sbad:
        fail("supplementary MANIFEST.tsv " + b)
    supp_names.append(os.path.basename(sd.rstrip("/")))
    for it in sitems:
        if it["status"] == "ok":
            supp_ok.add((it["item_kind"], it["source"]))

# ---------------------------------------------------------------- recompute row classes from live state
vanished_rows, orphan_rows, resolved_rows = [], [], []
commons = collections.OrderedDict()
for r in rows:
    p = r["path"]
    r["slug"] = slugify(p)
    r["dirty_n"] = int(r["dirty"]) if r["dirty"].isdigit() else 0
    if not os.path.isdir(p):
        vanished_rows.append(r)
        continue
    res = git("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=p)
    out = res.stdout.decode("utf-8", "replace").strip()
    if res.returncode != 0 or not out:
        orphan_rows.append(r)
        continue
    r["common"] = os.path.realpath(out)
    resolved_rows.append(r)
    commons.setdefault(r["common"], []).append(r)

U = set(commons)
if len(rows) != len(vanished_rows) + len(orphan_rows) + len(resolved_rows):
    fail("row accounting broken")

explained = set()  # id() of failed items that are legitimately covered

# ---------------------------------------------------------------- file-level checks (hash, size, existence)
files_checked = 0
bytes_checked = 0
manifest_files = set()
for it in items:
    rel = it["file"]
    if not rel:
        continue
    manifest_files.add(rel)
    path = os.path.join(run, rel)
    if not os.path.isfile(path):
        fail("manifest file missing on disk: %s" % rel)
        continue
    size = os.path.getsize(path)
    if str(size) != it["bytes"]:
        fail("size mismatch %s: manifest %s, disk %d" % (rel, it["bytes"], size))
    digest = sha256_file(path)
    if digest != it["sha256"]:
        fail("sha256 mismatch %s" % rel)
    files_checked += 1
    bytes_checked += size

for dirpath, dirnames, filenames in os.walk(run):
    for fn in filenames:
        rel = os.path.relpath(os.path.join(dirpath, fn), run)
        if rel in EXEMPT:
            continue
        if rel not in manifest_files:
            fail("file in run dir not recorded in MANIFEST.tsv: %s" % rel)

# ---------------------------------------------------------------- integrity of EVERY ok item, driven by the manifest
# (never by live source state: these files may be the only copies left once a source has been deleted)
packs_checked = 0
gitdir_tars = 0
tar_entry_total = 0
TAR_KINDS = ("untracked-tar", "staged-tar", "orphan-tree-tar", "gitdir-tar", "filtered-tar", "lfs-storage-tar")
for it in items:
    if it["status"] != "ok" or not it["file"]:
        continue
    k = it["item_kind"]
    path = os.path.join(run, it["file"])
    if not os.path.isfile(path):
        continue
    if k in TAR_KINDS:
        rc, n, err, names = tar_list(path, keep_names=(k == "gitdir-tar"))
        if rc != 0:
            fail("tar -tf failed for %s: %s" % (it["file"], err[-200:]))
        if str(n) != it["entries"]:
            fail("tar %s lists %d entries, recorded at creation %s" % (it["file"], n, it["entries"]))
        if k == "untracked-tar":
            tar_entry_total += n
        if k == "gitdir-tar":
            gitdir_tars += 1
            base = os.path.basename(it["source"])
            if (base + "/HEAD") not in names:
                fail("git-dir tar %s has no %s/HEAD" % (it["file"], base))
            if any("/tmp_pack_" in x for x in names):
                fail("git-dir tar %s contains aborted tmp_pack files" % it["file"])
            if os.path.isdir(it["source"]):
                held = set(names)
                for rel in credential_configs(it["source"]):
                    if ("%s/%s" % (base, rel)) in held:
                        fail("git-dir tar %s holds %s, which carries a user:password@ URL and must be left out" % (it["file"], rel))
    elif k == "bundle":
        v = git("bundle", "verify", path, gitdir=EMPTY_GITDIR)  # full bundles are self-contained: verify in an empty repo
        if v.returncode != 0:
            fail("bundle verify (empty repo) failed for %s: %s" % (it["file"], v.stderr.decode("utf-8", "replace").strip()[-200:]))
        lh = git("bundle", "list-heads", path, gitdir=EMPTY_GITDIR)
        nref = len([ln for ln in lh.stdout.decode("utf-8", "replace").splitlines() if ln.strip()])
        if str(nref) != it["entries"]:
            fail("bundle %s lists %d refs, manifest says %s" % (it["file"], nref, it["entries"]))
        ok, msg = pack_check(path)
        packs_checked += 1
        if not ok:
            fail("pack stream check failed for %s: %s" % (it["file"], msg))
    elif k == "head-bundle":
        ok, msg = pack_check(path)
        packs_checked += 1
        if not ok:
            fail("pack stream check failed for %s: %s" % (it["file"], msg))
        src = it["source"]
        if os.path.isdir(src) and git("rev-parse", "--git-dir", cwd=src).returncode == 0:
            v = git("bundle", "verify", path, cwd=src)  # thin bundle: prerequisites live in its source repo
            if v.returncode != 0:
                fail("head bundle verify failed for %s: %s" % (it["file"], v.stderr.decode("utf-8", "replace").strip()[-200:]))
        else:
            note("head bundle %s: prerequisites unverifiable because the source %s is gone (pack stream check still ran)" % (it["file"], src))

# ---------------------------------------------------------------- waivers (a failed item the conductor accepted, with evidence)
# Validated over ALL failed manifest items, because the waived source may already be gone and so absent from U.
waived_items = {}
for it in items:
    if it["item_kind"] != "row" and it["status"] == "failed" and "waived-by-conductor:" in it["note"]:
        ok, res = check_waiver(it["note"])
        if not ok:
            fail("failed %s %s carries a waiver that is not valid: %s" % (it["item_kind"], it["source"], res))
            continue
        waivers.append((it["source"], res[0], res[1]))
        waived_items[id(it)] = True
        explained.add(id(it))

# ---------------------------------------------------------------- every common dir is accounted for
state_counts = collections.Counter()
common_state = {}
for common in sorted(U):
    slug = slugify(common)
    b = one("bundle", slug)
    g = one("gitdir-tar", slug)
    state = None
    if b is not None and b["status"] in ("ok", "empty"):
        state = "bundle-" + b["status"]
    elif g is not None and g["status"] == "ok":
        state = "gitdir-tar"
        if b is not None and b["status"] == "failed":
            explained.add(id(b))
    elif ("bundle", common) in supp_ok or ("gitdir-tar", common) in supp_ok:
        state = "supplementary-run"
        for it in (b, g):
            if it is not None and it["status"] == "failed":
                explained.add(id(it))
    elif (b is not None and id(b) in waived_items) or (g is not None and id(g) in waived_items):
        state = "waived"
    else:
        for it in (b, g):
            if it is not None and it["status"] == "failed" and "covered-by:" in it["note"]:
                copy, why = resolve_covered(it["note"])
                if copy is None:
                    fail("failed %s for %s annotated covered-by but: %s" % (it["item_kind"], common, why))
                    continue
                if os.path.isdir(common):
                    # source still exists: the copy must hold every ref tip of the source
                    src_refs = {ln.split()[0] for ln in git("for-each-ref", "--format=%(objectname)", gitdir=common).stdout.decode().splitlines() if ln.strip()}
                    missing = [x for x in src_refs if git("cat-file", "-e", x + "^{commit}", cwd=copy).returncode != 0 and git("cat-file", "-e", x, cwd=copy).returncode != 0]
                    if missing:
                        fail("covered-by copy %s lacks %d ref tip(s) of %s" % (copy, len(missing), common))
                        continue
                state = "covered-by-copy"
                explained.add(id(it))
                note("%s covered by copy %s" % (common, copy))
                break
    if state is None:
        fail("common dir not preserved: %s (bundle=%s gitdir-tar=%s)" % (common, b["status"] if b else None, g["status"] if g else None))
        state_counts["uncovered"] += 1
        continue
    state_counts[state] += 1
    common_state[common] = state
    if state == "bundle-empty":
        refs = git("show-ref", gitdir=common)
        if refs.stdout.strip():
            fail("bundle for %s is recorded empty but the repo has refs" % common)

bundle_sources = {it["source"] for it in items if it["item_kind"] in ("bundle", "gitdir-tar")}
extra = sorted(bundle_sources - U)
if extra:
    note("%d bundle/gitdir-tar item(s) for a common dir no longer derived from real.tsv, e.g. %s" % (len(extra), extra[0]))
eq_parts = sum(state_counts[k] for k in ("bundle-ok", "bundle-empty", "gitdir-tar", "supplementary-run", "covered-by-copy", "waived", "uncovered"))
if len(U) != eq_parts:
    fail("unique common dirs (%d) != preserved states (%s)" % (len(U), dict(state_counts)))

# ---------------------------------------------------------------- what a bundle drops (recomputed from live git, not read from the producer)
# A bundle carries refs and their history. A raw git-dir copy is required for reflog-only commits, per-worktree refs, LFS or
# annex objects and submodule git dirs, and a relocated LFS store needs its own tar. Items covered some other way (a
# supplementary run, a covered-by copy, a waiver) are that route's business.
raw_required = raw_verified = lfs_stores = lfs_stores_verified = 0
for common in sorted(U):
    state = common_state.get(common)
    if state is None or state in ("covered-by-copy", "waived"):
        continue
    cslug = slugify(common)
    req = requirement(common)
    if req["reasons"]:
        raw_required += 1
        why = ",".join(req["reasons"])
        if state == "supplementary-run":
            if ("gitdir-tar", common) not in supp_ok:
                fail("common dir %s needs a raw git-dir copy (%s) and no supplementary run holds one" % (common, why))
        else:
            g = one("gitdir-tar", cslug)
            if g is None or g["status"] != "ok":
                fail("common dir %s needs a raw git-dir copy (%s) but the run has no usable gitdir-tar item (%s)" % (common, why, g["status"] if g else "none"))
            elif os.path.isfile(os.path.join(run, g["file"])):
                bad_content = check_gitdir_content(common, os.path.join(run, g["file"]), req)
                for msg in bad_content:
                    fail("raw git-dir copy %s (required for %s): %s" % (g["file"], why, msg))
                if not bad_content:
                    raw_verified += 1
    store, configured = lfs_dir(common)
    if configured and not inside(store, common):
        lfs_stores += 1
        if state == "supplementary-run":
            if ("lfs-storage-tar", store) not in supp_ok:
                fail("common dir %s keeps its LFS store outside the git dir (%s) and no supplementary run holds a copy" % (common, store))
            continue
        it = one("lfs-storage-tar", cslug)
        live = os.path.isdir(store) and any(True for _ in os.scandir(store))
        if it is None:
            fail("common dir %s keeps its LFS store outside the git dir (%s) but the run has no lfs-storage-tar item" % (common, store))
        elif it["source"] != store:
            fail("lfs-storage-tar item for %s names %s, live lfs.storage is %s" % (common, it["source"], store))
        elif it["status"] == "empty":
            if live:
                fail("lfs-storage-tar for %s is recorded empty but %s holds files" % (common, store))
            else:
                lfs_stores_verified += 1
        elif it["status"] == "ok" and os.path.isfile(os.path.join(run, it["file"])):
            bad_content = check_store_content(store, os.path.join(run, it["file"]))
            for msg in bad_content:
                fail("lfs-storage-tar %s: %s" % (it["file"], msg))
            if not bad_content:
                lfs_stores_verified += 1

# ---------------------------------------------------------------- head bundles (detached rows)
head_ok = head_empty = 0
for r in resolved_rows:
    if r["branch"] != "(detached)":
        continue
    it = one("head-bundle", r["slug"])
    if it is None:
        fail("detached row has no head-bundle item: %s" % r["path"])
        continue
    if it["status"] == "ok":
        head_ok += 1  # integrity is checked by the manifest-driven pass above
    elif it["status"] == "empty":
        head_empty += 1
        rl = git("rev-list", "-n", "1", "HEAD", "--not", "--remotes", cwd=r["path"])
        if rl.stdout.strip():
            fail("head bundle for %s is recorded empty but HEAD has commits outside every remote" % r["path"])


# ---------------------------------------------------------------- dirty snapshots
def covered_by_check(pt_note, r, staged):
    copy, why = resolve_covered(pt_note)
    if copy is None:
        return False, why
    cs = git("ls-files", "--cached", "-z", cwd=copy)
    n = count_nul(cs.stdout)
    if n != staged:
        return False, "covered-by copy has %d staged entries, the source has %d" % (n, staged)
    return True, copy


dirty_rows = [r for r in resolved_rows if r["dirty_n"] > 0]
snap_rows = 0
snap_bytes = 0
both_empty = []
unborn_rows = []
for r in dirty_rows:
    pt = one("tracked-patch", r["slug"])
    ut = one("untracked-tar", r["slug"])
    unborn = git("rev-parse", "-q", "--verify", "HEAD", cwd=r["path"]).returncode != 0
    if unborn:
        staged = count_nul(git("ls-files", "--cached", "-z", cwd=r["path"]).stdout)
        unborn_rows.append((r["path"], staged))
        if pt is not None:
            explained.add(id(pt))  # nothing to diff against: failed or empty alike
        if staged > 0:
            st = one("staged-tar", r["slug"])
            gt = one("gitdir-tar", slugify(r["common"]))
            if st is not None and st["status"] == "ok" and gt is not None and gt["status"] == "ok":
                pass
            else:
                ok, why = covered_by_check(pt["note"] if pt else "", r, staged)
                if not ok:
                    fail("unborn-HEAD row with %d staged entries is not covered (%s): %s" % (staged, why, r["path"]))
                else:
                    note("unborn-HEAD row %s covered by %s (%d staged entries match)" % (r["path"], why, staged))
    else:
        if pt is None or pt["status"] not in ("ok", "empty"):
            fail("dirty row has no usable tracked patch: %s" % r["path"])
            continue
    if ut is None or ut["status"] not in ("ok", "empty"):
        fail("dirty row has no usable untracked tar: %s" % r["path"])
        continue
    made = False
    if pt is not None and pt["status"] == "ok":
        made = True
        path = os.path.join(run, pt["file"])
        if os.path.isfile(path):
            with open(path, "rb") as f:
                head = f.read(10)
            if not head.startswith(b"diff --git"):
                fail("tracked patch does not start with a git diff header: %s" % pt["file"])
            snap_bytes += os.path.getsize(path)
    if ut["status"] == "ok":
        made = True  # tar entry counts are checked by the manifest-driven pass above
        path = os.path.join(run, ut["file"])
        if os.path.isfile(path):
            snap_bytes += os.path.getsize(path)
    if made:
        snap_rows += 1
    else:
        both_empty.append(r["path"])
if both_empty:
    note("%d dirty row(s) produced no snapshot content (dirty>0 in the sweep but nothing tracked or untracked to save): %s" % (len(both_empty), "; ".join(both_empty[:6])))

# ---------------------------------------------------------------- filter-attribute paths (filtered-tar)
# Git stores what a clean filter (or git-lfs) outputs, not the working-tree bytes: status and diff stay clean while the
# only copy of those bytes is the file. Every resolved checkout with such a tracked path needs a filtered-tar holding
# exactly the files that exist now (credential-pattern and > 2 GiB files excepted), sizes included.
filtered_rows = filtered_verified = 0
for r in resolved_rows:
    path = r["path"]
    if git("rev-parse", "--is-bare-repository", cwd=path).stdout.strip() == b"true":
        continue  # no working tree
    names = filter_paths(path)
    if names is None:
        fail("cannot list the filter-attribute paths of %s" % path)
        continue
    want = expected_filtered(path, names)
    if not want:
        continue
    filtered_rows += 1
    it = one("filtered-tar", r["slug"])
    if it is None:
        if ("filtered-tar", path) in supp_ok:
            filtered_verified += 1
        else:
            fail("checkout %s has %d tracked path(s) with a filter attribute present in the working tree but the run has no filtered-tar item" % (path, len(want)))
        continue
    if it["status"] != "ok":
        if it["status"] == "empty":
            fail("filtered-tar for %s is recorded empty but %d filter-attribute file(s) exist in the working tree" % (path, len(want)))
        continue  # failed or skipped: reported by the generic status check
    tpath = os.path.join(run, it["file"])
    if not os.path.isfile(tpath):
        continue
    try:
        with tarfile.open(tpath, "r:", encoding="utf-8", errors="surrogateescape") as tf:
            held = {m.name: m for m in tf}
    except (OSError, tarfile.TarError) as exc:
        fail("filtered-tar %s is unreadable: %s" % (it["file"], exc))
        continue
    missing = sorted(set(want) - set(held))
    extra = sorted(set(held) - set(want))
    wrong = sorted(n for n, size in want.items() if size is not None and n in held and held[n].size != size)
    if missing:
        fail("filtered-tar %s lacks %d of the %d filter-attribute file(s) of %s, e.g. %s" % (it["file"], len(missing), len(want), path, missing[0]))
    if extra:
        fail("filtered-tar %s holds %d file(s) that live git does not list as filter-attribute files, or that a credential rule excludes, e.g. %s" % (it["file"], len(extra), extra[0]))
    if wrong:
        fail("filtered-tar %s holds %d file(s) whose size differs from the working tree, e.g. %s" % (it["file"], len(wrong), wrong[0]))
    if not (missing or extra or wrong):
        filtered_verified += 1

# rows whose source vanished AFTER the apply run: their live state cannot be re-derived, so coverage is read from the
# manifest (a dirty row needs both snapshot items; a detached row needs its head-bundle item); their integrity was
# already checked by the manifest-driven pass above
gone_since_apply = 0
for r in vanished_rows:
    ri = one("row", r["slug"])
    if ri is not None and ri["status"] == "vanished":
        continue  # already missing at apply time and recorded as such
    gone_since_apply += 1
    if r["dirty_n"] > 0:
        pt, ut = one("tracked-patch", r["slug"]), one("untracked-tar", r["slug"])
        opt = one("orphan-tree-tar", r["slug"])
        if not (pt is not None and ut is not None and pt["status"] in ("ok", "empty", "failed") and ut["status"] in ("ok", "empty")) and opt is None:
            fail("row vanished after the apply run and the manifest holds no snapshot for it: %s" % r["path"])
    if r["branch"] == "(detached)" and one("head-bundle", r["slug"]) is None and one("orphan-tree-tar", r["slug"]) is None:
        fail("detached row vanished after the apply run and the manifest holds no head bundle for it: %s" % r["path"])

# ---------------------------------------------------------------- unresolved rows (raw working-tree tar)
orphan_made = 0
for r in orphan_rows:
    it = one("orphan-tree-tar", r["slug"])
    row_item = one("row", r["slug"])
    if row_item is None:
        note("unresolved row not recorded as a row item: %s" % r["path"])
    if it is None or it["status"] not in ("ok", "empty"):
        fail("unresolved row has no usable orphan-tree-tar: %s" % r["path"])
        continue
    if it["status"] == "ok":
        orphan_made += 1

# ---------------------------------------------------------------- vanished rows
recovered_annotated = 0
for r in vanished_rows:
    it = one("row", r["slug"])
    if it is None or it["status"] != "vanished":
        note("row vanished since the apply run (no vanished item): %s" % r["path"])
    else:
        m = re.search(r"recovered-from-tm-\d{8}T\d{6}", it["note"])
        if m:
            recovered_annotated += 1
            if not os.path.isdir(os.path.join(os.path.dirname(ROOT), m.group(0))):
                note("vanished row annotated %s but that directory is not present beside the destination root" % m.group(0))
for it in items:
    if it["item_kind"] == "row" and it["status"] == "vanished" and os.path.isdir(it["source"]):
        note("row recorded vanished at apply time has reappeared: %s" % it["source"])

# ---------------------------------------------------------------- extra stash entries
stash_checked = 0
for common in U:
    lg = git("log", "-g", "--format=%H", "refs/stash", gitdir=common)
    n = len([ln for ln in lg.stdout.decode().splitlines() if ln.strip()]) if lg.returncode == 0 else 0
    if n <= 1:
        continue
    cslug = slugify(common)
    if common_state.get(common) == "supplementary-run":
        continue  # this repo is the supplementary run's business, and that run is verified on its own
    rl = one("stash-reflog", cslug)
    if rl is None or rl["status"] != "ok":
        fail("repo with %d stash entries has no stash reflog item: %s" % (n, common))
    for i in range(1, n):
        found = [it for it in by.get(("stash-patch", cslug), []) if ("stash@{%d}" % i) in it["note"]]
        if not found or found[0]["status"] != "ok":
            fail("stash@{%d} of %s has no usable patch" % (i, common))
        else:
            stash_checked += 1

# ---------------------------------------------------------------- skip lists
skip_reasons = collections.Counter()
skipped_path = os.path.join(run, "dirty", "skipped.txt")
cred_path = os.path.join(run, "dirty", "credential-skipped.txt")
big_files = []
if os.path.isfile(skipped_path):
    with open(skipped_path, "rb") as f:
        for ln in f.read().split(b"\n"):
            if ln:
                parts = ln.split(b"\t")
                skip_reasons[parts[0].decode()] += 1
                if parts[0] == b"over-2GiB":
                    big_files.append(ln.decode("utf-8", "replace"))
else:
    fail("dirty/skipped.txt missing")
cred_n = cred_bytes = 0
if os.path.isfile(cred_path):
    with open(cred_path, "rb") as f:
        for ln in f.read().split(b"\n"):
            if ln:
                cred_n += 1
                try:
                    cred_bytes += int(ln.split(b"\t")[-1])
                except ValueError:
                    pass
else:
    fail("dirty/credential-skipped.txt missing")

# ---------------------------------------------------------------- generic status check (after coverage is known)
for it in items:
    k, s = it["item_kind"], it["status"]
    if k == "row":
        continue  # a failed row is explained by its orphan-tree-tar (checked above)
    if s in ("failed", "skipped") and id(it) not in explained:
        fail("%s %s is %s: %s" % (k, it["slug"], s, it["note"]))

# ---------------------------------------------------------------- totals and RESULT.txt
kind_bytes = collections.Counter()
kind_status = collections.Counter()
for it in items:
    kind_status[(it["item_kind"], it["status"])] += 1
    try:
        kind_bytes[it["item_kind"]] += int(it["bytes"])
    except ValueError:
        pass
total_bytes = sum(kind_bytes.values())
n_ok = state_counts["bundle-ok"]
n_empty = state_counts["bundle-empty"]

verdict = "PASS" if not failures else "FAIL"
out = [verdict]
out.append("WAIVERS: %d%s" % (len(waivers), " (a PASS above means PASS-with-waivers: each waived item is listed below with its evidence)" if waivers else ""))
for src, reason, ev in waivers:
    out.append("WAIVER: source=%s reason=%s evidence=%s" % (src, reason, ev))
out.append("run=%s verified_at=%s elapsed=%ds" % (run, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), time.time() - started))
# pins the manifest this verdict is about: a manifest edited after the verifier passed it no longer matches
out.append("manifest_sha256=%s" % sha256_file(os.path.join(run, "MANIFEST.tsv")))
out.append("rows=%d resolved=%d unresolved_orphans=%d vanished=%d (annotated recovered-from-tm: %d)" % (len(rows), len(resolved_rows), len(orphan_rows), len(vanished_rows), recovered_annotated))
out.append("unique_common_dirs=%d states=%s" % (len(U), dict(state_counts)))
out.append("equation: %d unique common dirs == bundle-ok %d + bundle-empty %d + gitdir-tar %d + covered-by-supplementary-run %d + covered-by-copy %d + waived %d + uncovered %d (vanished rows have no common dir and are counted at row level)" % (len(U), n_ok, n_empty, state_counts["gitdir-tar"], state_counts["supplementary-run"], state_counts["covered-by-copy"], state_counts["waived"], state_counts["uncovered"]))
out.append("supplementary_runs_used=%s" % (supp_names or "none"))
out.append("head_bundles ok=%d empty=%d (detached resolved rows=%d)" % (head_ok, head_empty, len([r for r in resolved_rows if r["branch"] == "(detached)"])))
out.append("dirty_rows=%d with_snapshot_content=%d snapshot_bytes=%d tar_entries=%d" % (len(dirty_rows), snap_rows, snap_bytes, tar_entry_total))
out.append("unborn_head_rows=%s" % (unborn_rows or "none"))
out.append("orphan_tree_tars_made=%d of %d unresolved rows; rows vanished since the apply run (coverage read from the manifest)=%d" % (orphan_made, len(orphan_rows), gone_since_apply))
out.append("stash_patches_verified=%d" % stash_checked)
out.append("raw_git_dir_copies_required=%d verified=%d; lfs_stores_outside_git_dir=%d verified=%d; checkouts_with_filtered_paths=%d verified=%d" % (raw_required, raw_verified, lfs_stores, lfs_stores_verified, filtered_rows, filtered_verified))
out.append("files_hashed=%d bytes_hashed=%d bundle_packs_stream_checked=%d gitdir_tars_checked=%d" % (files_checked, bytes_checked, packs_checked, gitdir_tars))
out.append("skipped_files: %s; over_2GiB=%d; credential_pattern_files=%d (%d bytes, paths+sizes only)" % (dict(skip_reasons) or "none", len(big_files), cred_n, cred_bytes))
out.append("manifest_bytes_total=%d by_kind=%s" % (total_bytes, dict(kind_bytes)))
out.append("status_counts=%s" % {"%s:%s" % k: v for k, v in sorted(kind_status.items())})
if failures:
    out.append("FAILURES (%d):" % len(failures))
    out += ["  - " + m for m in failures[:200]]
if notes:
    out.append("NOTES (%d):" % len(notes))
    out += ["  - " + m for m in notes[:200]]
text = "\n".join(out) + "\n"
with open(os.path.join(run, "RESULT.txt"), "w") as f:
    f.write(text)
sys.stdout.write(text)
sys.exit(0 if not failures else 1)
PY
exit $?
