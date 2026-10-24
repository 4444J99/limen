#!/usr/bin/env python3
"""ICLOUD DEDUPE — archive-never-rm engine for numbered-duplicate folders in iCloud Drive.

iCloud Drive (and Desktop & Documents re-enables / client resets) mint ` N`-suffixed sibling
folders ("03_Legal 2", "Documents - host") under CloudDocs/Desktop and CloudDocs/Documents. In the
2026-10-23 census every unsuffixed folder was empty and exactly one numbered variant held the
content, so deleting by name pattern would destroy data. This engine classifies each variant
(KEEPER / EMPTY / SUBSET / DIVERGENT, keyed on (relpath, size)), proves SUBSET variants by sha256
against the keeper, archives them to an external volume, and renames the keeper to the plain name.
Stdlib only; run with `python3 -I`.

Verbs (exactly one; default is --dry-run):
  --dry-run   (default) recompute the census from the live tree (lstat only), diff against
              census.json, classify variants, write plan.live.json + PREVIEW.md. Reads NO file
              content and mutates nothing in iCloud. --replan also rewrites plan.json (the
              reviewed plan the apply gate compares against).
  --census    lstat-only census of Desktop/ and Documents/ written to census.json in the state dir
              (the baseline --dry-run diffs against). Read-only against iCloud.
  --status    read-only: per-group state (applied? from `after` manifests in the archive manifests
              dir), UNION_COPY progress (files in the union dir vs plan), and whether the writer
              lock is held. Touches neither iCloud nor the archive.
  --apply --group G   execute one group (single writer via flock). Copy-verify-then-remove to the
              external archive volume. iCloud originals of UNION_COPY groups are never removed.
  --verify    compare BEFORE manifests vs (iCloud canonical U archive); print LOST=<n>; exit
              non-zero if n>0.

Paths: --state-dir (plan.json, plan.live.json, PREVIEW.md, census.json, .lock; default
$LIMEN_CUSTODY_STAGING_ROOT/icloud-dedupe, falling back to
~/Workspace/limen/.limen-private/custody-staging/icloud-dedupe; created 0700) and --archive-root
(default /Volumes/Archive4T/icloud-dedupe-2026-10-23, so the existing run's manifests stay valid).

Progress: every long phase (scan, copy/union, hashing, brctl settle waits, verify) prints a flushed
line at least every 60 s (files done/total, bytes done/total, current relpath; brctl elapsed + last
state). A silent multi-hour run is a defect: the 2026-10-24 operator killed a 5 h run for it.

Safety contract (do not weaken):
  * --apply refuses unless a live re-plan of the group equals plan.json (exit 5 = plan drift).
  * brctl must report caught-up before any mutation, after archiving, and after the rename;
    otherwise the run stops (exit 4 = iCloud did not settle / name space changed under us).
  * Refuses when FXICloudDriveDesktop/FXICloudDriveDocuments read 1, or are unreadable without
    --allow-fx-unknown; refuses when the archive volume is unmounted or free space is short.
  * Copy = /usr/bin/ditto, then sha256 + xattr verify, F_FULLFSYNC, from-disk re-hash; the source
    is re-hashed immediately before each unlink; only the recorded set is unlinked and directories
    are removed with rmdir only (a non-recorded entry makes rmdir raise and the variant stays).
  * UNION_COPY groups (99_System_Backups) copy a deduplicated union to the archive with a sha256
    manifest and NEVER remove the iCloud originals.

PENDING OWNER RULING (issue #3195): in-iCloud removal of EMPTY and hash-proven SUBSET variants is
terminal deletion inside ~/Library/Mobile Documents, which the `icloud` rail in
institutio/governance/storage-roles.yaml lists under `never:`. Every removed byte has a verified
archive copy, but the clause is unamended: until the owner rules, treat --apply as requiring that
ruling and do not extend it to new groups or to UNION_COPY originals.
"""
import argparse
import collections
import datetime
import fcntl
import glob
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import threading
import time

CD = os.path.expanduser("~/Library/Mobile Documents/com~apple~CloudDocs")
PARENTS = (("Desktop", CD + "/Desktop"), ("Documents", CD + "/Documents"))
DEFAULT_ARCHIVE_ROOT = "/Volumes/Archive4T/icloud-dedupe-2026-10-23"
_FALLBACK_STAGING = "~/Workspace/limen/.limen-private/custody-staging"
# Resolved by configure(); module-level so tests can point them at a synthetic tree.
STATE_DIR = ""
CENSUS_JSON = ""
PLAN_JSON = ""
PLAN_LIVE_JSON = ""
PREVIEW_MD = ""
LOCK_PATH = ""
ARCH_VOL = ""
ARCH = ""
MANIFESTS = ""
UNION_GROUPS = {"99_System_Backups"}
SF_DATALESS = 0x40000000
NUM = re.compile(r'(?<!-) (\d+)$')
IGNORABLE = {".DS_Store", "Icon\r"}
VER_SUFFIX = re.compile(r'\.v\d\d(?=(\.[^./]*)?$)')
BRCTL_WAIT = 3600
BRCTL_POLL = 10          # seconds between brctl polls
PROGRESS_INTERVAL = 60.0  # max seconds between flushed progress lines in any long phase
SPACE_FACTOR = 1.5
EXIT_SETTLE = 4          # iCloud (brctl) did not settle / group changed under us
EXIT_PLAN_DRIFT = 5      # live re-plan differs from plan.json
ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


def default_state_dir():
    root = os.environ.get("LIMEN_CUSTODY_STAGING_ROOT") or os.path.expanduser(_FALLBACK_STAGING)
    return os.path.join(root, "icloud-dedupe")


def mount_point(path):
    """Volume that must be mounted for `path`: /Volumes/<name> for external roots, else the
    nearest enclosing mount point. An unmounted /Volumes/X must never resolve to '/'."""
    path = os.path.abspath(path)
    parts = path.split(os.sep)
    if len(parts) > 2 and parts[1] == "Volumes":
        return os.sep.join(parts[:3])
    while path != os.sep and not os.path.ismount(path):
        path = os.path.dirname(path)
    return path


def configure(state_dir=None, archive_root=None, census_json=None):
    """Point the module at a state dir and archive root (defaults above)."""
    global STATE_DIR, CENSUS_JSON, PLAN_JSON, PLAN_LIVE_JSON, PREVIEW_MD, LOCK_PATH
    global ARCH_VOL, ARCH, MANIFESTS
    STATE_DIR = os.path.abspath(os.path.expanduser(state_dir or default_state_dir()))
    CENSUS_JSON = os.path.abspath(os.path.expanduser(census_json)) if census_json else STATE_DIR + "/census.json"
    PLAN_JSON = STATE_DIR + "/plan.json"
    PLAN_LIVE_JSON = STATE_DIR + "/plan.live.json"
    PREVIEW_MD = STATE_DIR + "/PREVIEW.md"
    LOCK_PATH = STATE_DIR + "/.lock"
    ARCH = os.path.abspath(os.path.expanduser(archive_root or DEFAULT_ARCHIVE_ROOT))
    ARCH_VOL = mount_point(ARCH)
    MANIFESTS = ARCH + "/manifests"


def ensure_state_dir():
    os.makedirs(STATE_DIR, mode=0o700, exist_ok=True)
    os.chmod(STATE_DIR, 0o700)


configure()


# ---------------------------------------------------------------- progress
class Progress:
    """Flushed progress lines for a long phase: files done/total, bytes done/total, current relpath.

    note() emits when PROGRESS_INTERVAL has elapsed since the last line; a watchdog thread covers
    blocking calls (a single huge ditto, a slow hash, a dataless download) so the output is never
    silent longer than the interval. Use as a context manager."""

    def __init__(self, phase, total_files=0, total_bytes=0, interval=None):
        self.phase = phase
        self.total_files = total_files
        self.total_bytes = total_bytes
        self.interval = PROGRESS_INTERVAL if interval is None else interval
        self.files = 0
        self.bytes = 0
        self.current = ""
        self.t0 = time.monotonic()
        self.last = self.t0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def line(self, tail=""):
        files = "%d/%d" % (self.files, self.total_files) if self.total_files else "%d" % self.files
        byts = ("%s/%s" % (hb(self.bytes), hb(self.total_bytes))) if self.total_bytes else hb(self.bytes)
        return "progress [%s] files %s bytes %s elapsed %ds current: %s%s" % (
            self.phase, files, byts, int(time.monotonic() - self.t0), self.current or "-", tail)

    def emit(self, tail=""):
        with self._lock:
            print(self.line(tail), flush=True)
            self.last = time.monotonic()

    def note(self, current=None, files=0, nbytes=0):
        if current is not None:
            self.current = current
        self.files += files
        self.bytes += nbytes
        if time.monotonic() - self.last >= self.interval:
            self.emit()

    def _watch(self):
        tick = min(max(self.interval / 4.0, 0.01), 1.0)
        while not self._stop.wait(tick):
            if time.monotonic() - self.last >= self.interval:
                self.emit()

    def __enter__(self):
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, et, ev, tb):
        self._stop.set()
        self._thread.join(timeout=2)
        self.emit(" (done)" if et is None else " (ended with %s)" % et.__name__)
        return False


# ---------------------------------------------------------------- scanning
def split_name(n, isdir):
    if isdir:
        stem, ext = n, ''
    else:
        stem, ext = os.path.splitext(n)
    m = NUM.search(stem)
    if m:
        return stem[:m.start()] + ext, int(m.group(1))
    return n, 0


def norm_name(name):
    """Map an iCloud placeholder '.foo.icloud' to 'foo'."""
    if name.startswith('.') and name.endswith('.icloud') and len(name) > 8:
        return name[1:-7]
    return name


def walk(root):
    """lstat-only walk -> list of (rel, size, mtime, dataless, kind)."""
    out = []
    stack = [""]
    while stack:
        rel = stack.pop()
        full = os.path.join(root, rel) if rel else root
        try:
            it = list(os.scandir(full))
        except OSError:
            out.append((rel + "/<ERR>", 0, 0, False, 'err'))
            continue
        for e in it:
            r = os.path.join(rel, e.name) if rel else e.name
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                out.append((r, 0, 0, False, 'err'))
                continue
            dl = bool(getattr(st, 'st_flags', 0) & SF_DATALESS)
            if stat.S_ISDIR(st.st_mode):
                stack.append(r)
                out.append((r, 0, int(st.st_mtime), dl, 'dir'))
            elif stat.S_ISLNK(st.st_mode):
                out.append((r, st.st_size, int(st.st_mtime), dl, 'link'))
            else:
                out.append((r, st.st_size, int(st.st_mtime), dl, 'file'))
    return out


def is_ignorable(rel):
    return os.path.basename(rel) in IGNORABLE


def scan_variant(parent, name, isdir, st):
    p = os.path.join(parent, name)
    if isdir:
        ents = walk(p)
    else:
        ents = [("", st.st_size, int(st.st_mtime), bool(getattr(st, 'st_flags', 0) & SF_DATALESS), 'file')]
    files = [e for e in ents if e[4] in ('file', 'link')]
    dirs = [e for e in ents if e[4] == 'dir']
    errs = [e for e in ents if e[4] == 'err']
    keys = {}   # (normrel,size) -> (actual rel, dataless, mtime)
    for rel, size, mt, dl, kind in files:
        if is_ignorable(rel):
            continue
        d, b = os.path.split(rel)
        nrel = os.path.join(d, norm_name(b)) if d else norm_name(b)
        keys[(nrel, size)] = (rel, dl, mt)
    return {
        "name": name, "path": p, "isdir": isdir,
        "files": len(files), "dirs": len(dirs), "bytes": sum(e[1] for e in files),
        "dataless_files": sum(1 for e in files if e[3]),
        "dataless_bytes": sum(e[1] for e in files if e[3]),
        "icloud_placeholders": sum(1 for e in files if e[0].endswith('.icloud')),
        "errs": len(errs),
        "_ents": ents, "_keys": keys,
    }


def scan_parent(label, parent):
    groups = collections.defaultdict(list)
    for n in sorted(os.listdir(parent)):
        st = os.lstat(os.path.join(parent, n))
        isdir = stat.S_ISDIR(st.st_mode)
        base, num = split_name(n, isdir)
        v = scan_variant(parent, n, isdir, st)
        v["num"] = num
        groups[base].append(v)
    for base in groups:
        groups[base].sort(key=lambda v: v["num"])
    return groups


# ---------------------------------------------------------------- classification
def pick_keeper(variants):
    best = max(len(v["_keys"]) for v in variants)
    if best == 0:
        return None
    tied = [v for v in variants if len(v["_keys"]) == best]
    for v in tied:
        if v["num"] == 0:
            return v
    return sorted(tied, key=lambda v: v["num"])[0]


def plan_group(label, base, variants):
    g = {"parent": label, "group": base, "variants": [], "keeper": None,
         "keeper_rename": None}
    notdir = [v for v in variants if not v["isdir"]]
    if notdir or len(variants) < 2:
        g["status"] = "SKIPPED"
        g["reason"] = "non-directory group" if notdir else "single variant"
        for v in variants:
            g["variants"].append(_vsummary(v, "UNTOUCHED", None, None))
        return g
    keeper = pick_keeper(variants)
    kkeys = set(keeper["_keys"]) if keeper else set()
    union_mode = base in UNION_GROUPS
    dest_root = ARCH + "/" + base
    dl_bytes = 0
    copy_bytes = 0
    compared = {}
    has_div = False
    for v in variants:
        if keeper is not None and v is keeper:
            cls = "KEEPER"
        elif not v["_keys"]:
            cls = "EMPTY"
        else:
            cls = "SUBSET" if set(v["_keys"]) <= kkeys else "DIVERGENT"
        if cls == "DIVERGENT":
            has_div = True
        g["variants"].append(_vsummary(v, cls, dest_root + "/" + v["name"] + "/", None))
        v["_cls"] = cls
    if keeper:
        g["keeper"] = keeper["name"]
    if union_mode:
        g["status"] = "UNION_COPY"
        g["mode"] = "UNION_COPY"
        g["union_dest"] = dest_root + "/union/"
        for v in variants:
            dl_bytes += v["dataless_bytes"]
            copy_bytes += v["bytes"]
            _vs(g, v)["action"] = "UNION_COPY"
    elif has_div:
        g["status"] = "NEEDS_UNION"
        g["mode"] = "NONE"
        for v in variants:
            _vs(g, v)["action"] = "NONE"
    else:
        g["status"] = "PLANNED"
        g["mode"] = "ARCHIVE"
        for v in variants:
            if v["_cls"] in ("EMPTY", "SUBSET"):
                _vs(g, v)["action"] = "ARCHIVE"
                dl_bytes += v["dataless_bytes"]
                copy_bytes += v["bytes"]
                if v["_cls"] == "SUBSET":
                    for k in v["_keys"]:
                        compared[k] = keeper["_keys"][k][1] and k[1] or 0
            else:
                _vs(g, v)["action"] = "KEEP"
        dl_bytes += sum(compared.values())
        if keeper is not None and keeper["num"] != 0:
            g["keeper_rename"] = {"from": keeper["path"], "to": os.path.join(os.path.dirname(keeper["path"]), base)}
    g["bytes_to_download"] = dl_bytes
    g["bytes_to_copy"] = copy_bytes
    return g


def _vsummary(v, cls, dest, action):
    return {"name": v["name"], "num": v["num"], "class": cls, "action": action,
            "files": v["files"], "dirs": v["dirs"], "keys": len(v["_keys"]),
            "bytes": v["bytes"], "dataless_files": v["dataless_files"],
            "dataless_bytes": v["dataless_bytes"],
            "icloud_placeholders": v["icloud_placeholders"], "errs": v["errs"],
            "dest": dest}


def _vs(g, v):
    for s in g["variants"]:
        if s["name"] == v["name"]:
            return s
    raise KeyError(v["name"])


# ---------------------------------------------------------------- census drift
def drift(scans):
    rep = []
    try:
        census = json.load(open(CENSUS_JSON, encoding="utf-8"))
    except Exception as e:
        return ["census.json unreadable: %r" % (e,)]
    fields = ("files", "dirs", "bytes", "dataless_files", "dataless_bytes", "icloud_placeholders", "errs")
    for label, groups in scans.items():
        cg = census.get(label, {})
        for base in sorted(set(cg) | set(groups)):
            if base not in groups:
                rep.append("%s/%s: group in census, absent live" % (label, base)); continue
            if base not in cg:
                rep.append("%s/%s: group live, absent from census" % (label, base)); continue
            cv = {v["name"]: v for v in cg[base]["variants"]}
            lv = {v["name"]: v for v in groups[base]}
            for n in sorted(set(cv) | set(lv)):
                if n not in lv:
                    rep.append("%s/%s: variant '%s' in census, absent live" % (label, base, n)); continue
                if n not in cv:
                    rep.append("%s/%s: variant '%s' live, absent from census" % (label, base, n)); continue
                diffs = ["%s %s->%s" % (f, cv[n].get(f), lv[n][f]) for f in fields
                         if cv[n].get(f) != lv[n][f]]
                if diffs:
                    rep.append("%s/%s: variant '%s': %s" % (label, base, n, "; ".join(diffs)))
    return rep


# ---------------------------------------------------------------- reporting
def hb(n):
    n = float(n)
    for u in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or u == "TiB":
            return "%d B" % n if u == "B" else "%.2f %s" % (n, u)
        n /= 1024


def totals_of(plans):
    t = {"groups": 0, "variants_total": 0, "variants_to_archive": 0, "keeper_renames": 0,
         "bytes_to_download": 0, "bytes_to_copy": 0, "needs_union_groups": 0,
         "union_copy_groups": 0, "union_copy_variants": 0, "skipped_groups": 0,
         "bytes_to_download_archive_mode": 0}
    for g in plans:
        if g["status"] == "SKIPPED":
            t["skipped_groups"] += 1
            continue
        t["groups"] += 1
        t["variants_total"] += len(g["variants"])
        t["bytes_to_download"] += g["bytes_to_download"]
        t["bytes_to_copy"] += g["bytes_to_copy"]
        if g["status"] == "NEEDS_UNION":
            t["needs_union_groups"] += 1
        elif g["status"] == "UNION_COPY":
            t["union_copy_groups"] += 1
            t["union_copy_variants"] += len(g["variants"])
        else:
            t["variants_to_archive"] += sum(1 for v in g["variants"] if v["action"] == "ARCHIVE")
            t["keeper_renames"] += 1 if g["keeper_rename"] else 0
            t["bytes_to_download_archive_mode"] += g["bytes_to_download"]
    return t


def write_outputs(plans, tot, drep, plan_path):
    ensure_state_dir()
    doc = {"generated": datetime.datetime.now().isoformat(timespec="seconds"),
           "archive_root": ARCH, "archive_volume_mounted": os.path.ismount(ARCH_VOL),
           "totals": tot, "drift_vs_census": drep, "groups": plans}
    tmp = plan_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    os.replace(tmp, plan_path)
    L = ["# iCloud dedupe PREVIEW (dry-run)", "",
         "Generated %s. Nothing in iCloud was modified; no file content was read." % doc["generated"],
         "Archive root: `%s` (volume mounted: %s)" % (ARCH, doc["archive_volume_mounted"]), "",
         "## Totals", "", "| metric | value |", "|---|---|"]
    rows = [("groups (multi-variant dir groups)", tot["groups"]),
            ("variants total", tot["variants_total"]),
            ("variants to archive (EMPTY+SUBSET)", tot["variants_to_archive"]),
            ("keeper renames", tot["keeper_renames"]),
            ("UNION_COPY groups", tot["union_copy_groups"]),
            ("UNION_COPY variants", tot["union_copy_variants"]),
            ("NEEDS_UNION groups", tot["needs_union_groups"]),
            ("bytes to download (all groups)", "%d (%s)" % (tot["bytes_to_download"], hb(tot["bytes_to_download"]))),
            ("bytes to download (archive-mode groups)", "%d (%s)" % (tot["bytes_to_download_archive_mode"], hb(tot["bytes_to_download_archive_mode"]))),
            ("bytes to copy to archive", "%d (%s)" % (tot["bytes_to_copy"], hb(tot["bytes_to_copy"]))),
            ("skipped groups (non-dir / single)", tot["skipped_groups"])]
    for k, v in rows:
        L.append("| %s | %s |" % (k, v))
    L += ["", "## Drift vs census.json", ""]
    L += ["- " + d for d in drep] if drep else ["No drift: live tree matches census.json for all compared fields."]
    L += ["", "## Groups", ""]
    for g in plans:
        if g["status"] == "SKIPPED":
            continue
        L.append("### %s / %s  [%s]" % (g["parent"], g["group"], g["status"]))
        L.append("")
        L.append("keeper: `%s`; mode: %s; bytes to download: %d (%s); bytes to copy: %s" % (
            g["keeper"], g["mode"], g["bytes_to_download"], hb(g["bytes_to_download"]), hb(g["bytes_to_copy"])))
        if g.get("union_dest"):
            L.append("union destination: `%s` (+ sha256 manifest); iCloud originals are NOT removed" % g["union_dest"])
        if g["keeper_rename"]:
            L.append("keeper rename: `%s` -> `%s`" % (os.path.basename(g["keeper_rename"]["from"]), os.path.basename(g["keeper_rename"]["to"])))
        L += ["", "| variant | class | action | files | keys | bytes | dataless files | dataless bytes | destination |",
              "|---|---|---|---|---|---|---|---|---|"]
        for v in g["variants"]:
            L.append("| %s | %s | %s | %d | %d | %d | %d | %d | %s |" % (
                v["name"], v["class"], v["action"], v["files"], v["keys"], v["bytes"],
                v["dataless_files"], v["dataless_bytes"],
                ("`%s`" % v["dest"]) if v["action"] in ("ARCHIVE",) else (("`%s`" % g["union_dest"]) if v["action"] == "UNION_COPY" else "")))
        L.append("")
    sk = [g for g in plans if g["status"] == "SKIPPED"]
    if sk:
        L += ["## Skipped (not dir-variant groups)", ""]
        L += ["- %s/%s: %s (%d entries)" % (g["parent"], g["group"], g["reason"], len(g["variants"])) for g in sk]
    with open(PREVIEW_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


# ---------------------------------------------------------------- apply helpers
def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256_disk(p):
    """Hash from disk through a fresh O_RDONLY descriptor, page cache bypassed where possible."""
    fd = os.open(p, os.O_RDONLY)
    try:
        nc = getattr(fcntl, "F_NOCACHE", None)
        if nc is not None:
            try:
                fcntl.fcntl(fd, nc, 1)
            except OSError:
                pass
        h = hashlib.sha256()
        while True:
            b = os.read(fd, 1 << 20)
            if not b:
                break
            h.update(b)
        return h.hexdigest()
    finally:
        os.close(fd)


def entry_hash(p, disk=False):
    """sha256 of a file; for a symlink, sha256 of b'link:'+target."""
    if os.path.islink(p):
        return hashlib.sha256(b"link:" + os.fsencode(os.readlink(p))).hexdigest()
    return sha256_disk(p) if disk else sha256_file(p)


def fullsync_path(p):
    """Flush a written file to stable storage (F_FULLFSYNC on macOS) before it is trusted."""
    if os.path.islink(p):
        return
    fd = os.open(p, os.O_RDONLY)
    try:
        ff = getattr(fcntl, "F_FULLFSYNC", None)
        try:
            if ff is not None:
                fcntl.fcntl(fd, ff)
            else:
                os.fsync(fd)
        except OSError:
            os.fsync(fd)
    finally:
        os.close(fd)


def nrel_of(rel):
    d, b = os.path.split(rel)
    return os.path.join(d, norm_name(b)) if d else norm_name(b)


def finder_flag(key):
    """Return 1, 0, or None (unknown: missing key, error, or unparseable)."""
    try:
        r = subprocess.run(["defaults", "read", "com.apple.finder", key],
                           capture_output=True, text=True, timeout=30)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    v = r.stdout.strip()
    if v == "1":
        return 1
    if v == "0":
        return 0
    return None


# ---- brctl settle detection
CLOUDDOCS_FULL = "com.apple.CloudDocs"
CLOUDDOCS_ABBR = re.compile(r'c\{1\}m\.a\{3\}e\.C\{7\}s')   # brctl abbreviates the container id
NOT_CAUGHT = re.compile(r'not[\s_-]*caught[\s_-]*up', re.I)
BUSY_WORD = re.compile(
    r'\b(uploading|downloading|pending[\w-]*|needs?[-_ ]?(?:upload|download|sync)\w*)\b(?:\s*[:=]\s*(\d+))?',
    re.I)


def brctl_settled(out):
    """Parse `brctl status`. Returns (settled, reason). Fails closed on anything unexpected."""
    text = ANSI.sub("", out)
    blocks = []
    cur = None
    for line in text.splitlines():
        if line.startswith("<"):
            cur = [line]
            blocks.append(cur)
        elif cur is not None:
            cur.append(line)
    cd = [b for b in blocks if CLOUDDOCS_FULL in b[0] or CLOUDDOCS_ABBR.search(b[0])]
    if not cd:
        return False, "no com.apple.CloudDocs container block in brctl output"
    for b in cd:
        blk = "\n".join(b)
        if NOT_CAUGHT.search(blk):
            return False, "container reports 'not caught up'"
        if "caught-up" not in blk.lower():
            return False, "container block lacks 'caught-up'"
        for m in BUSY_WORD.finditer(blk):
            if m.group(2) is None:
                return False, "container reports '%s'" % m.group(1)
            if int(m.group(2)) > 0:
                return False, "container reports %s=%s" % (m.group(1), m.group(2))
    return True, "caught-up"


def wait_settled(limit=BRCTL_WAIT, what=""):
    """True only when CloudDocs is caught up and idle; False on timeout or brctl failure."""
    t0 = time.time()
    last = "never polled"
    last_print = time.monotonic()
    tag = " [" + what + "]" if what else ""
    while True:
        try:
            r = subprocess.run(["brctl", "status"], capture_output=True, text=True, timeout=60)
        except Exception as e:
            print("brctl unavailable (%r)%s" % (e, tag), flush=True)
            return False
        ok, last = brctl_settled(r.stdout + r.stderr)
        if ok:
            print("brctl: settled (%s)%s" % (last, tag), flush=True)
            return True
        if time.time() - t0 >= limit:
            break
        if time.monotonic() - last_print >= PROGRESS_INTERVAL:
            print("brctl: waiting to settle, elapsed %ds of %ds, last state: %s%s" % (
                int(time.time() - t0), limit, last, tag), flush=True)
            last_print = time.monotonic()
        time.sleep(BRCTL_POLL)
    print("brctl: NOT settled after %ds: %s%s" % (limit, last, tag), flush=True)
    return False


def abort_settle(msg):
    sys.stderr.write("ABORT (exit %d): %s\n" % (EXIT_SETTLE, msg))
    sys.exit(EXIT_SETTLE)


def manifest_of(root_entries):
    return [{"relpath": r, "size": s, "mtime": m} for r, s, m in root_entries]


def icloud_manifest(parent, base):
    out = []
    for n in sorted(os.listdir(parent)):
        b, _ = split_name(n, os.path.isdir(os.path.join(parent, n)) and not os.path.islink(os.path.join(parent, n)))
        if b != base:
            continue
        for rel, size, mt, dl, kind in walk(os.path.join(parent, n)):
            if kind in ('file', 'link'):
                out.append({"variant": n, "relpath": rel, "size": size, "mtime": mt, "kind": kind})
    return out


def archive_manifest(base):
    out = []
    root = ARCH + "/" + base
    if not os.path.isdir(root):
        return out
    for rel, size, mt, dl, kind in walk(root):
        if kind in ('file', 'link'):
            out.append({"archive_relpath": rel, "size": size, "mtime": mt})
    return out


def safe(n):
    return re.sub(r'[^A-Za-z0-9._-]+', '_', n)


def write_manifest(tag, label, base):
    os.makedirs(MANIFESTS, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%dT%H%M%S%f") + "-p%d" % os.getpid()
    p = "%s/%s.%s.%s.json" % (MANIFESTS, safe(base), tag, ts)
    doc = {"group": base, "parent": label, "tag": tag, "time": ts,
           "icloud": icloud_manifest(dict(PARENTS)[label], base)}
    if tag == "after":
        doc["archive"] = archive_manifest(base)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=1, ensure_ascii=False)
    print("manifest:", p)
    return p


# ---- per-group sha256 manifests: sha256 TAB size TAB json(normrel) TAB json(variant) TAB json(actual relpath)
def hash_manifest_path(base, kind):
    return "%s/%s.%s.sha256" % (MANIFESTS, safe(base), kind)


def load_hash_manifest(path):
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line:
                continue
            sha, size, nrel, var, act = line.split("\t", 4)
            out[(json.loads(var), json.loads(nrel), int(size))] = (sha, json.loads(act))
    return out


def save_hash_manifest(path, d):
    os.makedirs(MANIFESTS, exist_ok=True)
    tmp = "%s.tmp.%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as f:
        for (var, nrel, size), (sha, act) in sorted(d.items()):
            f.write("%s\t%d\t%s\t%s\t%s\n" % (
                sha, size, json.dumps(nrel, ensure_ascii=False),
                json.dumps(var, ensure_ascii=False), json.dumps(act, ensure_ascii=False)))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    print("hash manifest:", path, "(%d entries)" % len(d))


_XATTR_IGNORE = ("com.apple.provenance", "com.apple.quarantine", "com.apple.lastuseddate#PS")


def xattr_sig(path):
    """Extended attributes (name -> hex value) excluding volatile system ones."""
    r = subprocess.run(["/usr/bin/xattr", path], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("xattr list failed: %s: %s" % (path, r.stderr.strip()))
    sig = {}
    for name in r.stdout.splitlines():
        if not name or name in _XATTR_IGNORE:
            continue
        v = subprocess.run(["/usr/bin/xattr", "-px", name, path], capture_output=True, text=True)
        if v.returncode != 0:
            raise RuntimeError("xattr read failed: %s %s: %s" % (path, name, v.stderr.strip()))
        sig[name] = v.stdout
    return sig

def _raise(e):
    raise e


def copy_tree_verified(src, dst, progress=None):
    """Copy src dir -> dst with per-file sha256 verify, fsync and a from-disk re-hash.
    Any unlistable directory raises. Returns (files, bytes, recorded) where recorded maps
    relpath -> (size, sha256) hashed from the SOURCE before it was copied."""
    nfiles = nbytes = 0
    recorded = {}
    os.makedirs(dst, exist_ok=True)
    for dp, dns, fns in os.walk(src, followlinks=False, onerror=_raise):
        rel = os.path.relpath(dp, src)
        ddir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(ddir, exist_ok=True)
        # os.walk reports symlinks-to-directories under dirnames; they must be copied as links too
        names = list(fns) + [n for n in dns if os.path.islink(os.path.join(dp, n))]
        for fn in names:
            s = os.path.join(dp, fn)
            d = os.path.join(ddir, fn)
            relf = fn if rel == "." else os.path.join(rel, fn)
            if os.path.islink(s):
                tgt = os.readlink(s)
                if os.path.lexists(d):
                    if not os.path.islink(d) or os.readlink(d) != tgt:
                        raise RuntimeError("symlink mismatch at " + d)
                else:
                    os.symlink(tgt, d)
                recorded[relf] = (os.lstat(s).st_size, entry_hash(s))
                nfiles += 1
                if progress is not None:
                    progress.note(current=relf, files=1)
                continue
            if progress is not None:
                progress.note(current=relf)
            sh = sha256_file(s)
            recorded[relf] = (os.lstat(s).st_size, sh)
            if os.path.lexists(d):
                if os.path.islink(d) or sha256_file(d) != sh:
                    raise RuntimeError("destination exists with different content: " + d)
            else:
                # ditto preserves xattrs, resource forks, ACLs and flags; shutil.copy2 drops them on darwin
                subprocess.run(["/usr/bin/ditto", s, d], check=True)
                if sha256_file(d) != sh:
                    raise RuntimeError("post-copy hash mismatch: " + d)
                if xattr_sig(s) != xattr_sig(d):
                    raise RuntimeError("post-copy xattr mismatch: " + d)
            fullsync_path(d)
            nfiles += 1
            nbytes += os.path.getsize(d)
            if progress is not None:
                progress.note(files=1, nbytes=os.path.getsize(d))
    os.sync()
    # re-hash every destination file from disk (fresh O_RDONLY fd) against the pre-copy source hash
    if progress is not None:
        progress.phase = progress.phase.replace("copy", "rehash", 1)
        progress.files = progress.bytes = 0
    for relf, (size, sh) in recorded.items():
        d = os.path.join(dst, relf)
        if progress is not None:
            progress.note(current=relf, files=1, nbytes=size)
        if entry_hash(d, disk=True) != sh:
            raise RuntimeError("from-disk re-hash mismatch: " + d)
    return nfiles, nbytes, recorded


def archive_variant(v, dest, store, store_path):
    tf = tb = 0
    for r, sz, m, dl, k in walk(v["path"]):
        if k in ('file', 'link'):
            tf += 1
            tb += sz
    with Progress("copy %s" % v["name"], tf, tb) as prog:
        return _archive_variant(v, dest, store, store_path, prog)


def _archive_variant(v, dest, store, store_path, prog):
    n, b, rec = copy_tree_verified(v["path"], dest, prog)
    # safety re-walk: unlistable entries on either side, or a structure not fully present at the
    # destination, refuse removal. Structure = file + link + dir keys.
    s_ents = walk(v["path"])
    d_ents = walk(dest)
    errs = [e[0] for e in s_ents + d_ents if e[4] == 'err']
    if errs:
        raise RuntimeError("unlistable entries for %s (%d, first %r); refusing removal" % (v["name"], len(errs), errs[0]))
    srckeys = {(r, s, k) for r, s, m, dl, k in s_ents}
    dstkeys = {(r, s, k) for r, s, m, dl, k in d_ents}
    if not srckeys <= dstkeys:
        raise RuntimeError("archive incomplete for %s: %d source entries missing/different at destination"
                           % (v["name"], len(srckeys - dstkeys)))
    src_files = {r: s for r, s, m, dl, k in s_ents if k in ('file', 'link')}
    for r, s in src_files.items():
        if r not in rec or rec[r][0] != s:
            raise RuntimeError("source changed during copy: %s" % r)
    # durable sha256 manifest BEFORE the source is removed
    for r, (size, sh) in rec.items():
        if is_ignorable(r):
            continue
        store[(v["name"], nrel_of(r), size)] = (sh, r)
    save_hash_manifest(store_path, store)
    # remove ONLY the recorded set, re-hashing each source immediately before unlinking;
    # anything not recorded (created after the copy) is left in place and the variant is not removed
    prog.phase = "unlink %s" % v["name"]
    prog.files = prog.bytes = 0
    for r, (size, sh) in rec.items():
        s = os.path.join(v["path"], r)
        prog.note(current=r, files=1, nbytes=size)
        if entry_hash(s) != sh:
            raise RuntimeError("source changed after archive (left in place): %s" % s)
        os.unlink(s)
    for dp, dns, fns in os.walk(v["path"], topdown=False, onerror=_raise):
        for dn in dns:
            q = os.path.join(dp, dn)
            if not os.path.islink(q):
                os.rmdir(q)  # raises if a non-recorded entry remains
    os.rmdir(v["path"])
    print("archived %s -> %s (%d files, %s)" % (v["name"], dest, n, hb(b)))


def preflight(g, plan_g, allow_fx_unknown=False):
    for k in ("FXICloudDriveDesktop", "FXICloudDriveDocuments"):
        val = finder_flag(k)
        if val == 1:
            raise SystemExit("REFUSE: %s reads 1 (Desktop & Documents sync on)" % k)
        if val is None and not allow_fx_unknown:
            raise SystemExit("REFUSE: %s is unknown (missing key or read error); pass --allow-fx-unknown to override" % k)
        if val is None:
            print("WARN: %s unknown; continuing under --allow-fx-unknown" % k)
    if not os.path.ismount(ARCH_VOL):
        raise SystemExit("REFUSE: %s is not mounted" % ARCH_VOL)
    os.makedirs(ARCH, exist_ok=True)
    dl = plan_g["bytes_to_download"]
    cp = plan_g["bytes_to_copy"]
    f_root = shutil.disk_usage("/").free
    f_arch = shutil.disk_usage(ARCH).free
    need_root = dl * SPACE_FACTOR
    need_arch = max(dl, cp) * SPACE_FACTOR
    print("space: / free %s need %s; archive free %s need %s" % (hb(f_root), hb(need_root), hb(f_arch), hb(need_arch)))
    if f_root < need_root:
        raise SystemExit("REFUSE: insufficient free space on /")
    if f_arch < need_arch:
        raise SystemExit("REFUSE: insufficient free space on archive volume")


def live_group(label, base):
    parent = dict(PARENTS)[label]
    groups = scan_parent(label, parent)
    if base not in groups:
        raise SystemExit("group not found: %s/%s" % (label, base))
    return groups[base]


def group_names_now(label, base):
    parent = dict(PARENTS)[label]
    out = set()
    for n in os.listdir(parent):
        p = os.path.join(parent, n)
        isd = os.path.isdir(p) and not os.path.islink(p)
        if split_name(n, isd)[0] == base:
            out.add(n)
    return out


# ---------------------------------------------------------------- plan.json comparison
SIG_GROUP = ("parent", "group", "status", "mode", "keeper", "bytes_to_copy", "union_dest")
SIG_VAR = ("num", "class", "action", "files", "dirs", "keys", "bytes", "errs", "dest")


def plan_sig(g):
    j = json.loads(json.dumps(g))
    sig = {k: j.get(k) for k in SIG_GROUP}
    kr = j.get("keeper_rename")
    sig["keeper_rename"] = None if not kr else {"from": os.path.basename(kr["from"]),
                                                 "to": os.path.basename(kr["to"])}
    sig["variants"] = {v["name"]: {f: v.get(f) for f in SIG_VAR} for v in j["variants"]}
    return sig


def diff_sig(a, b, prefix=""):
    lines = []
    for k in sorted(set(a) | set(b), key=str):
        x, y = a.get(k), b.get(k)
        if isinstance(x, dict) and isinstance(y, dict):
            lines += diff_sig(x, y, prefix + str(k) + ".")
        elif x != y:
            lines.append("%s%s: plan=%r live=%r" % (prefix, k, x, y))
    return lines


def load_plan_group(label, base):
    try:
        with open(PLAN_JSON, encoding="utf-8") as f:
            doc = json.load(f)
    except Exception as e:
        raise SystemExit("REFUSE: cannot load %s (%r); generate it deliberately with --replan" % (PLAN_JSON, e))
    for g in doc.get("groups", []):
        if g.get("parent") == label and g.get("group") == base:
            return g
    raise SystemExit("REFUSE: group %s/%s absent from %s; use --replan to regenerate deliberately" % (label, base, PLAN_JSON))


def apply_group(label, base, variants, g, allow_fx_unknown=False):
    print("group %s/%s status=%s" % (label, base, g["status"]))
    if g["status"] in ("SKIPPED", "NEEDS_UNION"):
        raise SystemExit("REFUSE: group is %s" % g["status"])
    preflight(g, g, allow_fx_unknown)
    if not wait_settled(what="before any mutation"):
        abort_settle("iCloud not settled before any mutation of %s/%s; nothing changed" % (label, base))
    write_manifest("before", label, base)
    byname = {v["name"]: v for v in variants}
    if g["mode"] == "UNION_COPY":
        union_copy(base, variants)
    else:
        keeper = byname[g["keeper"]] if g["keeper"] else None
        # 1. hash-compare SUBSET vs keeper (all before any move); record keeper hashes
        keep_path = hash_manifest_path(base, "keeper")
        keep_store = load_hash_manifest(keep_path)
        cmp_files = sum(len(byname[sv["name"]]["_keys"]) for sv in g["variants"] if sv["class"] == "SUBSET")
        with Progress("hash-compare %s/%s" % (label, base), cmp_files) as prog:
            for sv in g["variants"]:
                if sv["class"] != "SUBSET":
                    continue
                v = byname[sv["name"]]
                for k, (arel, dl, mt) in v["_keys"].items():
                    krel = keeper["_keys"][k][0]
                    sp = os.path.join(v["path"], arel)
                    kp = os.path.join(keeper["path"], krel)
                    if os.path.islink(sp) != os.path.islink(kp):
                        raise SystemExit("ABORT group: link/file mismatch %s vs %s" % (sp, kp))
                    try:
                        kh = entry_hash(kp)
                        sh = entry_hash(sp)
                    except OSError as e:
                        raise SystemExit("ABORT group: unreadable %s (%r)" % (sp, e))
                    if sh != kh:
                        raise SystemExit("ABORT group: hash mismatch %s vs %s" % (sp, kp))
                    keep_store[(keeper["name"], k[0], k[1])] = (kh, krel)
                    prog.note(arel, files=1, nbytes=k[1])
                print("hash-verified SUBSET %s against keeper" % v["name"])
        if keep_store:
            save_hash_manifest(keep_path, keep_store)
        # 2. archive EMPTY first, then SUBSET
        arch_path = hash_manifest_path(base, "archive")
        arch_store = load_hash_manifest(arch_path)
        order = [sv for sv in g["variants"] if sv["action"] == "ARCHIVE"]
        order.sort(key=lambda sv: (sv["class"] != "EMPTY", sv["num"]))
        try:
            for sv in order:
                archive_variant(byname[sv["name"]], sv["dest"], arch_store, arch_path)
        except (RuntimeError, OSError) as e:
            raise SystemExit("ABORT group (exit 1): %s" % e)
        # 3. settle after archiving, re-check the name space, then rename the keeper
        if not wait_settled(what="after archiving siblings"):
            abort_settle("iCloud not settled after archiving siblings of %s/%s; keeper rename NOT done" % (label, base))
        expected = {sv["name"] for sv in g["variants"] if sv["action"] != "ARCHIVE"}
        now = group_names_now(label, base)
        if now != expected:
            abort_settle("name space of %s/%s changed vs plan: unexpected=%s missing=%s; keeper rename NOT done"
                         % (label, base, sorted(now - expected), sorted(expected - now)))
        if g["keeper_rename"]:
            src, dst = g["keeper_rename"]["from"], g["keeper_rename"]["to"]
            if os.path.lexists(dst):
                abort_settle("rename target now exists %s; keeper rename NOT done" % dst)
            os.rename(src, dst)
            print("renamed keeper %s -> %s" % (os.path.basename(src), os.path.basename(dst)))
    write_manifest("after", label, base)
    if not wait_settled(what="after rename"):
        abort_settle("iCloud not settled after changes to %s/%s; filesystem state is consistent and complete, re-run --verify later" % (label, base))


def union_copy(base, variants):
    dest_root = ARCH + "/" + base + "/union"
    os.makedirs(dest_root, exist_ok=True)
    seen = {}      # rel -> {hash: destrel}
    manifest = []
    tf = tb = 0
    for v in variants:
        for r, sz, m, dl, k in walk(v["path"]):
            if k == 'file' and os.path.basename(r) not in IGNORABLE:
                tf += 1
                tb += sz
    with Progress("union %s" % base, tf, tb) as prog:
        for v in sorted(variants, key=lambda v: v["num"]):
            for dp, dns, fns in os.walk(v["path"], followlinks=False):
                rel = os.path.relpath(dp, v["path"])
                ddir = dest_root if rel == "." else os.path.join(dest_root, rel)
                os.makedirs(ddir, exist_ok=True)
                for fn in fns:
                    s = os.path.join(dp, fn)
                    if fn in IGNORABLE or os.path.islink(s):
                        continue
                    relf = fn if rel == "." else os.path.join(rel, fn)
                    prog.note("%s/%s" % (v["name"], relf), files=1, nbytes=os.lstat(s).st_size)
                    sh = sha256_file(s)
                    entries = seen.setdefault(relf, {})
                    if not entries:
                        d0 = os.path.join(dest_root, relf)
                        if os.path.exists(d0):           # resume: hash what is already there
                            entries[sha256_file(d0)] = relf
                    if sh in entries:
                        manifest.append((sh, entries[sh], v["name"]))
                        continue
                    if not entries:
                        drel = relf
                    else:
                        stem, ext = os.path.splitext(relf)
                        drel = "%s.v%02d%s" % (stem, v["num"], ext)
                    d = os.path.join(dest_root, drel)
                    if os.path.exists(d) and sha256_file(d) != sh:
                        raise RuntimeError("union collision at " + d)
                    if not os.path.exists(d):
                        shutil.copy2(s, d)
                    if sha256_file(d) != sh:
                        raise RuntimeError("union post-copy hash mismatch " + d)
                    entries[sh] = drel
                    manifest.append((sh, drel, v["name"]))
            print("union: variant %s done" % v["name"])
    with open(ARCH + "/" + base + "/union.sha256", "w", encoding="utf-8") as f:
        for sh, drel, vn in sorted(manifest, key=lambda x: x[1]):
            f.write("%s  union/%s  (from %s)\n" % (sh, drel, vn))
    print("union manifest written; iCloud originals untouched")


# ---------------------------------------------------------------- verify
def verify():
    """Every BEFORE file key (variant, relpath, size) must resolve to an archive entry or a keeper
    entry whose sha256 matches what is on disk now. LOST counts misses and mismatches."""
    lost = 0
    checked = 0
    unhashed = 0
    for label, parent in PARENTS:
        groups = scan_parent(label, parent)
        before = collections.defaultdict(set)
        for p in glob.glob(MANIFESTS + "/*.before.*.json"):
            try:
                d = json.load(open(p, encoding="utf-8"))
            except Exception:
                continue
            if d.get("parent") != label:
                continue
            for e in d["icloud"]:
                if not is_ignorable(e["relpath"]):
                    before[d["group"]].add((e.get("variant", ""), nrel_of(e["relpath"]), e["size"]))
        for base, want in sorted(before.items()):
            arch_m = load_hash_manifest(hash_manifest_path(base, "archive"))
            keep_m = load_hash_manifest(hash_manifest_path(base, "keeper"))
            keep_by = {(nr, sz): (sh, act) for (var, nr, sz), (sh, act) in keep_m.items()}
            live = {}
            for v in groups.get(base, []):
                for k, (rel, dl, mt) in v["_keys"].items():
                    live.setdefault(k, os.path.join(v["path"], rel))
            union_have = set()
            arch = ARCH + "/" + base
            if base in UNION_GROUPS and os.path.isdir(arch):
                for r, s, m, dl, k in walk(arch):
                    if k in ('file', 'link'):
                        parts = r.split(os.sep, 1)
                        if len(parts) == 2:
                            union_have.add((nrel_of(parts[1]), s))
                            union_have.add((nrel_of(VER_SUFFIX.sub("", parts[1])), s))
            with Progress("verify %s/%s" % (label, base), len(want)) as prog:
                for var, nrel, size in sorted(want):
                    checked += 1
                    ak = (var, nrel, size)
                    why = None
                    if ak in arch_m:
                        sha, act = arch_m[ak]
                        ap = os.path.join(ARCH, base, var, act)
                        try:
                            if entry_hash(ap, disk=True) != sha:
                                why = "archive hash mismatch"
                        except OSError:
                            why = "archive file missing/unreadable"
                    elif (nrel, size) in keep_by:
                        sha, act = keep_by[(nrel, size)]
                        lp = live.get((nrel, size))
                        if lp is None:
                            why = "keeper file missing"
                        else:
                            try:
                                if entry_hash(lp, disk=True) != sha:
                                    why = "keeper hash mismatch"
                            except OSError:
                                why = "keeper file unreadable"
                    elif (nrel, size) in live:
                        unhashed += 1          # untouched keeper file, never hashed: size-level resolution only
                    elif (nrel, size) in union_have:
                        pass
                    else:
                        why = "no keeper/archive entry"
                    if why:
                        lost += 1
                        print("LOST: %s/%s %s %s (%d): %s" % (label, base, var, nrel, size, why))
                    prog.note(nrel, files=1, nbytes=size)
    print("checked=%d" % checked)
    print("resolved_by_size_only=%d" % unhashed)
    print("LOST=%d" % lost)
    return 1 if lost > 0 else 0


# ---------------------------------------------------------------- main
def run_dry(replan):
    scans = {}
    plans = []
    with Progress("scan") as prog:
        for label, parent in PARENTS:
            prog.current = parent
            scans[label] = scan_parent(label, parent)
            for base in sorted(scans[label]):
                prog.note("%s/%s" % (label, base), files=1)
                plans.append(plan_group(label, base, scans[label][base]))
    drep = drift(scans)
    tot = totals_of(plans)
    write_outputs(plans, tot, drep, PLAN_LIVE_JSON)
    if replan:
        write_outputs(plans, tot, drep, PLAN_JSON)
        print("REPLAN: %s regenerated deliberately" % PLAN_JSON)
    print(json.dumps(tot, indent=1))
    print("drift entries: %d" % len(drep))
    for d in drep:
        print("  DRIFT " + d)
    # informational: compare the live plan with the approved plan.json
    try:
        with open(PLAN_JSON, encoding="utf-8") as f:
            approved = {(g["parent"], g["group"]): g for g in json.load(f).get("groups", [])}
        live = {(g["parent"], g["group"]): g for g in plans}
        ndiff = 0
        for k in sorted(set(approved) | set(live)):
            if k not in approved or k not in live:
                ndiff += 1
                print("  PLAN-DIFF %s/%s: present only in %s" % (k[0], k[1], "live" if k in live else "plan.json"))
                continue
            dd = diff_sig(plan_sig(approved[k]), plan_sig(live[k]))
            if dd:
                ndiff += 1
                print("  PLAN-DIFF %s/%s: %s" % (k[0], k[1], "; ".join(dd)))
        print("plan.json groups differing from live: %d" % ndiff)
    except Exception as e:
        print("plan.json not comparable (%r); use --replan to create it deliberately" % (e,))
    print("plan.json:", PLAN_JSON)
    print("live plan:", PLAN_LIVE_JSON)
    print("preview:", PREVIEW_MD)


CENSUS_FIELDS = ("name", "num", "isdir", "files", "dirs", "bytes", "dataless_files", "dataless_bytes",
                 "icloud_placeholders", "errs")


def run_census():
    """lstat-only census of Desktop/ and Documents/ -> CENSUS_JSON (the baseline --dry-run diffs)."""
    ensure_state_dir()
    out = {}
    ngroups = nvariants = 0
    with Progress("census") as prog:
        for label, parent in PARENTS:
            prog.current = parent
            groups = scan_parent(label, parent)
            out[label] = {}
            for base, vs in sorted(groups.items()):
                prog.note("%s/%s" % (label, base), files=1)
                out[label][base] = {"variants": [{k: v[k] for k in CENSUS_FIELDS} for v in vs],
                                    "total_files": sum(v["files"] for v in vs)}
                ngroups += 1
                nvariants += len(vs)
    tmp = CENSUS_JSON + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=1, ensure_ascii=False)
    os.replace(tmp, CENSUS_JSON)
    print("census: %s (%d groups, %d variants)" % (CENSUS_JSON, ngroups, nvariants))
    return 0


def lock_state():
    """Read-only probe of the writer lock; never creates the lock file."""
    if not os.path.exists(LOCK_PATH):
        return "free (no lock file)"
    try:
        fd = os.open(LOCK_PATH, os.O_RDONLY)
    except OSError as e:
        return "unknown (%r)" % (e,)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            return "HELD by another writer"
        fcntl.flock(fd, fcntl.LOCK_UN)
        return "free"
    finally:
        os.close(fd)


def _manifest_count(base, tag):
    return len(glob.glob("%s/%s.%s.*.json" % (glob.escape(MANIFESTS), glob.escape(safe(base)), tag)))


def status():
    """Read-only progress report. Reads plan.json and the archive manifests dir; never lists iCloud."""
    print("state dir:    %s" % STATE_DIR)
    print("archive root: %s (volume %s mounted: %s)" % (ARCH, ARCH_VOL, os.path.ismount(ARCH_VOL)))
    print("writer lock:  %s" % lock_state())
    try:
        with open(PLAN_JSON, encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as e:
        print("plan.json:    unreadable (%r); run --dry-run --replan" % (e,))
        return 0
    print("plan.json:    %s (generated %s)" % (PLAN_JSON, plan.get("generated")))
    counts = collections.Counter()
    for g in plan.get("groups", []):
        if g["status"] == "SKIPPED":
            counts["skipped"] += 1
            continue
        n_after = _manifest_count(g["group"], "after")
        n_before = _manifest_count(g["group"], "before")
        if g["status"] == "NEEDS_UNION":
            state = "blocked (NEEDS_UNION: divergent content, not applyable)"
        elif n_after:
            state = "applied (after-manifests: %d)" % n_after
        elif n_before:
            state = "STARTED, not finished (before-manifests: %d, no after-manifest)" % n_before
        else:
            state = "pending"
        counts[state.split(" ")[0].rstrip(",")] += 1
        print("  %s/%s [%s/%s] %s" % (g["parent"], g["group"], g["status"], g["mode"], state))
        if g.get("mode") == "UNION_COPY":
            udir = ARCH + "/" + g["group"] + "/union"
            uf = ub = 0
            if os.path.isdir(udir):
                for r, sz, m, dl, k in walk(udir):
                    if k == 'file':
                        uf += 1
                        ub += sz
            want_files = sum(v["files"] for v in g["variants"])
            done = os.path.exists(ARCH + "/" + g["group"] + "/union.sha256")
            print("    union: %d files / %s in %s (plan upper bound %d files / %s; hash-dedup lowers it); "
                  "manifest %s" % (uf, hb(ub), udir, want_files, hb(g["bytes_to_copy"]),
                                   "written (complete)" if done else "absent (incomplete)"))
    print("summary: " + ", ".join("%s=%d" % kv for kv in sorted(counts.items())))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(allow_abbrev=False)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--status", action="store_true",
                    help="read-only: per-group applied state, union progress, lock held?")
    ap.add_argument("--census", action="store_true",
                    help="lstat-only census of Desktop/ and Documents/ written to census.json")
    ap.add_argument("--replan", action="store_true",
                    help="deliberately regenerate plan.json from the live tree (dry-run, no mutation)")
    ap.add_argument("--allow-fx-unknown", action="store_true",
                    help="proceed when the Finder FXICloudDrive* flags cannot be read (value 1 always refuses)")
    ap.add_argument("--group")
    ap.add_argument("--state-dir", help="plan.json/PREVIEW.md/lock/census dir (default: %s)" % default_state_dir())
    ap.add_argument("--archive-root", help="archive root (default: %s)" % DEFAULT_ARCHIVE_ROOT)
    ap.add_argument("--census-json", help="census.json path (default: <state-dir>/census.json)")
    a = ap.parse_args(argv)
    if sum(1 for x in (a.apply, a.verify, a.status, a.census) if x) > 1:
        ap.error("--apply, --verify, --status and --census are mutually exclusive")
    if a.state_dir or a.archive_root or a.census_json:
        keep_census = CENSUS_JSON if a.state_dir is None else None
        configure(a.state_dir or STATE_DIR, a.archive_root or ARCH, a.census_json or keep_census)
    if a.status:
        sys.exit(status())
    if a.census:
        sys.exit(run_census())
    if a.verify:
        sys.exit(verify())
    if a.apply:
        if not a.group:
            sys.exit("--apply requires --group <name>")
        ensure_state_dir()
        lf = open(LOCK_PATH, "w")
        try:
            fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            sys.exit("REFUSE: another writer holds " + LOCK_PATH)
        label = None
        variants = None
        for l, p in PARENTS:
            sc = scan_parent(l, p)
            if a.group in sc:
                label, variants = l, sc[a.group]
                break
        if label is None:
            sys.exit("group not found: " + a.group)
        g = plan_group(label, a.group, variants)
        approved = load_plan_group(label, a.group)
        dd = diff_sig(plan_sig(approved), plan_sig(g))
        if dd:
            sys.stderr.write("ABORT (exit %d): live re-plan of %s/%s differs from %s:\n" % (EXIT_PLAN_DRIFT, label, a.group, PLAN_JSON))
            for line in dd:
                sys.stderr.write("  " + line + "\n")
            sys.stderr.write("Review, then regenerate deliberately with --replan.\n")
            sys.exit(EXIT_PLAN_DRIFT)
        print("plan.json matches live re-plan for %s/%s" % (label, a.group))
        apply_group(label, a.group, variants, g, a.allow_fx_unknown)
        return
    # dry-run (default); --replan additionally rewrites plan.json
    run_dry(a.replan)


if __name__ == "__main__":
    main()
