#!/usr/bin/env python3
"""Executable exit-readiness predicate: may the Mac be erased now?

The definition of done for the Mac exit is this script, not prose. It prints one line per check

    PASS <id> <detail>        the evidence was recomputed from live state and holds
    FAIL <id> <detail>        the evidence is missing, stale, or contradicts the claim
    UNPROVEN <id> <detail>    needs a human attestation, or evidence that cannot be derived

and then a final line, READY or NOT-READY.

Exit codes
    0   READY and nothing else: every check is PASS except human-erase, which only the owner at the machine can settle.
    1   NOT-READY: at least one check is FAIL.
    2   NOT-READY: no FAIL, but a check could not establish its answer (UNPROVEN). --no-deep ends here at best.
    64  usage error, including -h/--help (unknown flag, abbreviated flag, bad value, a bound above its hard ceiling, a
        missing required argument): no check ran.
    70  internal error: a check crashed (it prints as FAIL), so the verdict is not an answer.
`human-erase` is UNPROVEN by construction, so it is the one UNPROVEN check READY tolerates. A caller must read the exit
code, never the final line alone: only exit 0 is READY, 1 and 2 are NOT-READY, and 64 and 70 print no verdict at all.

Checks
    sweep-fresh            the git sweep is newer than --max-sweep-age-min (hard ceiling 120; a larger value is a
                           usage error, exit 64), parses, has rows, and its find.err (when present beside it) is
                           empty. The roots file beside it (git.tsv -> git.roots: the roots the sweep walked, then
                           `#END rows=N`) must exist and must cover every default root (each directory directly under
                           $HOME except Library .Trash .cache .npm .cargo .rustup, and $HOME/.local/share): a fresh scan
                           of those roots, plus --discovery-root and the strays under $HOME, must find no checkout or
                           bare repository the sweep lacks (universe-miss).
                           Evidence goes stale on a live Mac.
    git-preserved          every sweep entry not proven remote-held is covered by the UNION of the producer's
                           run-* directories and manual-* copies under --preserve-root (see "Preserve contract"),
                           judged against LIVE git state (see "Live exposure"). --remote-held is required.
    ignored-payload        UNPROVEN while a present checkout holds git-ignored files that no tracked manifest regenerates
                           (a node_modules, .venv, __pycache__ ... beside the manifest that rebuilds it; nothing else is
                           exempt for its name) and the owner has not listed it (--ignored-payload-attestation: path,
                           signer on --waiver-signers, ISO timestamp not before the newest ignored file (a bare date
                           counts from 00:00:00 UTC), sha256 of the checkout's sorted ignored-path list); a bare
                           repository has no work tree and is skipped;
                           PASS when there are none. No run copies ignored files, so this is never a silent pass.
    no-external-dependency nothing on a scanned volume depends on a disk that is not a scanned volume. Every .git
                           entry (file, symlink or directory, any case), every objects/info/alternates (bare stores
                           included) and every worktrees/*/commondir is read, with no depth bound (a --gitfile-depth
                           bound FAILs as scan-truncated if anything lies below it). A target is resolved through
                           every symlink; if it exists on a device that is none of the scanned volumes it is a LIVE
                           dependency (a spelling like /users, the firmlink alias or a link on the volume cannot hide
                           it); if it names the Mac but is already gone it is an orphan: one INFO line, not a failure.
                           By default (--externals auto) every mounted non-boot volume under --volumes-root is
                           scanned, whatever it is called; a mounted volume missing from an explicit list, an unmounted
                           volume and a scan of no volume are FAIL, never skipped.
    t7-unique-consolidated every file in the t7-unique MANIFEST.sha256 re-hashes equal on the external (off the Mac's
                           device, no symlinks) and the original is still on the T7 source volume (existence + size;
                           --hash-t7-originals re-hashes it too).
    nongit-homed           every non-git homing set named by --nongit-run (required, repeatable) has a newest run-* with a passing RESULT.txt (every RESULT:
                           tag PASS, no FAIL/PARTIAL line anywhere, no problem= line) whose manifest entries all
                           re-hash equal, off the Mac's device, AND match the LIVE source: --nongit-items names the
                           homing tool's items TSV; a source file that changed since the run (size, or modified after
                           the run's UTC stamp) or that was never homed (in neither the manifest nor EXCLUDED.tsv)
                           FAILs. Without a matching items file the check FAILs: a copy is not compared with itself.
    credential-registry-complete
                           credential-wall.py --check exits 0 (absent script: UNPROVEN). This proves the registry
                           is complete, not that the Mac's credential-route items are held.
    credential-route-items-homed
                           UNPROVEN unless --credential-attestation is an owner-written, names-only list, one line
                           per item: '<name> held-by: <organ|1Password|released> <ISO date>'. No value is read.
    backblaze-offsite      UNPROVEN unless --backblaze-attestation holds "upload-complete: yes <ISO date>"
                           dated no earlier than the newest preserve/non-git run. Not automatable.
    human-erase            always UNPROVEN.

Preserve contract (mirrors preserve-git.sh; the self-test runs the real producer, so drift fails the test)
    Entries needing preservation are the sweep rows flagged by the classify rules (kind=repo or bare: no origin,
    unpushed, stash; any kind: dirty, and a detached HEAD on no remote branch), plus every row the --remote-held file
    does not name PROVEN-ALL, a row it does not name at all included (absent is unproven, never trusted). PROVEN-ALL
    waives the unpushed/detached reasons only when the row has a remote and the verdict is bound to live git (see "Live
    exposure"); it never waives dirty work, a stash, or content a clean filter keeps out of every blob.
    --remote-held is read in the prove lane's shapes: one row per checkout (`path` + `repo_verdict`/`verdict`, which
    can bind nothing) or one row per repository (`repo`, `common_dir`, `paths` `;`-joined, `verdict`, `gaps`). Its last
    row, and tips.tsv's, must be `#END rows=N` with N the data rows; a file without it was cut short and is unusable.
    Every key is a realpath and is compared exactly: a spelling that differs matches nothing.
    A needed entry is covered when, against the CURRENT repository state:
      - its common dir has a bundle item with status ok, the artifact exists with the manifest size and a
        recomputed sha256 equal to the manifest, `git bundle verify` passes with a complete history, and the
        bundle heads include every current refs/heads/* and refs/stash tip at the same sha;
        where a bundle cannot work (partial clone, failed bundle, unborn HEAD) a gitdir-tar item stands in: the raw
        git dir copy is hash-verified, read without extracting, and must carry every current refs/heads/* and
        refs/stash tip at the same sha with the tip commits present in its objects;
      - a repository that needs preservation and shows, in live git, reflog-only commits (`rev-list --reflog --not
        --all`, in every worktree), a ref under refs/worktree, refs/bisect or refs/rewritten, git-lfs or git-annex object
        files, or submodule git dirs under modules/, ALSO has a gitdir-tar that holds what made it necessary: every
        reflog-only commit's object, every per-worktree ref file at its live tip with its object, the large-file objects
        by listing and size, the modules/ files by listing. The copy is in addition to the bundle, not instead of it.
        A raw copy stands in for a bundle only for a partial clone or an unborn HEAD; anywhere else a missing, failed
        or wrong bundle is a FAIL whatever raw copies exist. An
        lfs.storage inside the git dir counts as the lfs store; one outside it needs an lfs-storage-tar of that
        directory (status `empty` when it holds nothing);
      - a checkout whose tracked files carry a `filter` attribute (git-lfs, a notebook stripper) and whose working-tree
        bytes differ from the blob git stores has a filtered-tar of those files, matching the live files, and needs
        preservation even when it is otherwise clean and pushed. Credential-pattern names are left out of the tar and
        counted in the detail, as for every other snapshot; a file over 2 GiB is unsnapshotable (FAIL);
      - extra stash entries have a stash-reflog item and one verified stash-patch each;
      - an unborn-HEAD dirty row (nothing to diff) has an empty tracked-patch, a staged-tar matching `git ls-files
        --cached`, and a gitdir-tar holding the staged blobs and the current index;
      - a dirty row has a tracked-patch whose sha256 equals the sha256 of the current
        `git diff --binary --no-ext-diff --no-textconv --default-prefix --no-relative HEAD` (credential paths
        excluded as the producer does) and an untracked-tar whose members match the current untracked file
        list (name, size, mtime; --deep also compares content);
      - a detached row has a head bundle carrying the current HEAD, or HEAD is on a remote branch now;
      - an unresolvable row has an orphan-tree-tar matching the current file list;
      - an entry that vanished from the Mac (os.lstat says FileNotFoundError; an unreadable path is never "vanished")
        is accepted only if the recovery directory (newest recovered-from-* beside --preserve-root, or --recovery-root)
        holds a copy at the same $HOME-relative path that re-hashes against the RESCUE-MANIFEST.sha256 beside it and
        holds no file it does not list, whose current branch, unpushed count, stash count, dirty count and origin
        match the sweep's record, whose branch tips resolve, which is not shallow (unless the sweep row carries
        shallow=1) and which borrows no objects through alternates; otherwise FAIL;
      - the source is complete (a run has skipped-list and credential-list rows; incomplete runs are set aside)
        and no repository has a commit, or a dirty file, newer than the run start time taken from the
        run-<UTC stamp> directory name (a manual copy: its manifest's mtime).
    Coverage is a UNION over components, judged per source: a repository's bundle, a checkout's dirty snapshot,
    detached HEAD and orphan tree may each be covered by a different run or manual copy, and staleness applies to
    the covering source. `--verbose` lists, per row, which source covers each component. Each run's own RESULT.txt
    verdict and WAIVERS count are surfaced in the detail but never trusted: every artifact is re-hashed here.
    A manual copy (`<manual-dir>/<name>/` with `<manual-dir>/<name>.MANIFEST.sha256`) covers a kind=repo row of the
    same basename and origin when every manifest entry re-hashes, every current cached and untracked file
    (credential patterns excepted) has the manifest's sha256, an unborn row's staged blobs exist in the copy's
    object database, and (for a bundle component) the copy carries the current branch tips and every live stash
    entry. A copy that borrows objects through alternates, links its git dir or objects elsewhere by symlink, or
    has an empty manifest never covers.
    Files the producer cannot snapshot (over 2 GiB, special files) make the entry FAIL: they are not preserved.
    Credential-pattern files are left out by the producer by design; they are counted in the detail.

Live exposure (the plan is built from live git, never from the sweep alone)
    Every sweep row whose checkout exists is recomputed with git-sweep.sh's columns. These each FAIL and can be
    neither waived nor covered by a run: exposure that grew since the sweep (exposure-drift), a kind git disagrees
    with (`bare` when git says so; else `repo` when the git dir is the common dir, which covers a submodule or
    separate-git-dir checkout; else `worktree`), a checkout git no longer resolves that the sweep recorded clean, a
    skip-worktree/assume-unchanged file that differs from the index (hidden-edit), a git read that fails (git-error:
    never read as zero) and a path that cannot be stat-ed (exposure-unreadable). A fresh `find` over the sweep's roots
    file (no depth bound, no prune, `.git` in any case, bare repositories too), --discovery-root and the strays under
    $HOME must find no checkout the sweep lacks (universe-miss), including the repository behind a swept worktree, and
    must not error (discovery-incomplete); sweep-fresh applies the same test.
    PROVEN-ALL is believed for a checkout only while the --remote-held file is younger than --max-remote-held-age-min
    (default 720), names that checkout with the repository's common dir as git reports it and an empty `gaps`, the
    repository holds no large-file store a remote listing cannot prove, one of its remotes resolves (after insteadOf)
    somewhere other than this Mac, and every live ref of the repository is a proven row of the tips.tsv beside it, under
    the keys the prove lane writes: the full refname for every ref outside refs/remotes and refs/stash, `HEAD@<worktree>`
    for each detached worktree HEAD, `<refname>@<worktree>` for every ref under refs/worktree, refs/bisect and
    refs/rewritten, in EVERY worktree of the repository. This is checked for every present checkout, whatever exposure its
    columns show; otherwise the row is treated as unproven and needs coverage like any other.
    A path under a disposable marker earns no exemption: the row needs coverage like any other, or an owner-signed
    --disposals record (columns path, reason, signer, evidence_path, evidence_sha256; the evidence is a regular file
    whose sha256 is recomputed). Disposed rows are reported as waivers.
    Compared refs are every ref but refs/remotes/* (branches, tags, stash, notes, refs/limen/...), in bundles and in
    raw git-dir copies. Deep verification is the default (--no-deep opts out, and a run that did is never READY):
    content compare of untracked files, a pack stream check of bundles, `git fsck` of every raw git-dir copy. A thin
    head bundle needs its prerequisites in the verified repository bundle, and an `empty` head bundle is accepted only
    if HEAD is reachable from that bundle's tips. Not covered: the sweep's head_remote_branches still counts local
    remote-tracking refs (which is why a clean row is believed only on a bound PROVEN-ALL, never on those counts).

Waivers (--waivers <tsv> with --waiver-signers <allow-list>; columns path, reason, evidence_path, evidence_sha256,
signer, kind, and optionally signed_at)
    A sweep row whose checkout has vanished from the Mac and is not matched in the recovery copy is a FAIL (a
    PROVEN-ALL verdict does not spare it: a proof binds the refs a checkout holds, and a gone one holds none). A
    signer on the allow-list file (one name per line, # comments) may waive it. A waiver is honoured only with a
    non-empty reason, a signer on that list, a kind (remote-held | copy-elsewhere | loss-accepted), an evidence file
    that is a regular file (not a directory, link or the waivers file itself), whose sha256 is re-verified against
    evidence_sha256 and which names the waived path (absolute or ~/-relative), and a path that is a row of the sweep
    and provably gone: os.lstat raises FileNotFoundError, nothing else (an unreadable parent, a TCC-protected
    folder, a file squatting on the path are not "gone"). A signed_at, a waivers file or an evidence file dated in the
    future is invalid. Without --waiver-signers every waiver is invalid: no signer can be verified. A waiver is printed as
    `WAIVED <check> <path> <reason> [signer=.. kind=.. evidence=..]`, and a waiver over a row that had unpreserved data
    (the sweep's own dirty/unpushed/stash/no-origin) is also listed on its own `EXPOSED` line naming what it gives up;
    the final line carries the count, e.g. `READY (1 waiver)`. A waiver that fails any condition, names a surviving
    checkout, or duplicates another is itself a FAIL (waiver-invalid) and waives nothing it covers.
    Waivers cover only `row-vanished`: a surviving but uncovered repository can never be waived.

Custody and time
    Every preserve run, manual copy, recovered tree, non-git run and t7 copy must live on another device than $HOME
    (after realpath), and no artifact may be reached through a symlink. --max-sweep-age-min and
    --max-remote-held-age-min have hard ceilings (120 and 4320 minutes). An attestation, waiver or evidence file dated
    in the future is rejected.

Limits stated plainly: a clean repository is covered by its bundle plus the ref comparison; edits that keep a
file's size and mtime are only caught in the default deep mode. The script never writes to the Mac or to an external; its
only scratch is one empty temporary directory that it removes. It makes no network call. No path that names a
real volume or a dated directory is built in: --preserve-root, --remote-held, --nongit-run (repeatable), --t7-unique, --t7-source,
--credential-wall, --credential-attestation and --backblaze-attestation are REQUIRED arguments, and omitting one is
a usage error (exit 64), never a silent default. Only --volumes-root (/Volumes) and the volume list (every mounted
non-boot volume) have defaults, and neither names a disk.

Self-test: `check-exit-ready.py --self-test` builds fixture repositories, runs the real preserve-git.sh on
them, and asserts every verdict, positive and negative.
"""

from __future__ import annotations

import argparse
import bisect
import collections
import contextlib
import dataclasses
import errno
import fcntl
import fnmatch
import functools
import hashlib
import io
import ipaddress
import mmap
import os
import plistlib
import re
import shutil
import socket
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import traceback
import types
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, NoReturn

PASS, FAIL, UNPROVEN = "PASS", "FAIL", "UNPROVEN"
EXIT_USAGE = 64  # H1: argparse's own 2 would read as "only UNPROVEN checks remain"; also -h/--help (E1)
EXIT_INTERNAL = 70  # a check crashed: the verdict is not an answer

# Generic defaults only: every layout path (preserve root, t7 dirs, attestations, non-git runs) is a required argument.
DEFAULTS = {
    "volumes_root": "/Volumes",
    "externals": "auto",  # F4: every mounted non-boot volume under volumes_root, never a hand-kept list
    "max_sweep_age_min": 30.0,
    "gitfile_depth": 0,  # F4: 0 = unbounded; a positive bound FAILs when anything lies below it
    "max_remote_held_age_min": 720.0,  # merged: the tighter of the two fix branches' defaults (12 h)
}
# H6: hard ceilings, enforced at the command line (exit 64) and again inside the check for a directly built Ctx
MAX_SWEEP_AGE_CEILING_MIN = 120.0
MAX_REMOTE_HELD_AGE_CEILING_MIN = 4320.0
FUTURE_SKEW_SEC = 300  # H6: tolerated clock skew before a dated artifact counts as future-dated

F_NOCACHE = getattr(fcntl, "F_NOCACHE", 48)
MAX_FILE_BYTES = 2 * 1024 * 1024 * 1024
SCRATCH_HEADROOM = 256 * 1024 * 1024  # free space to leave after extracting a raw git-dir copy for verification
MANIFEST_COLS = ["item_kind", "status", "slug", "source", "file", "bytes", "sha256", "entries", "note"]
SWEEP_COLS = ["path", "kind", "branch", "remote", "dirty", "unpushed", "stashes", "head_remote_branches"]
RUN_RE = re.compile(r"^run-(\d{8}T\d{6}Z)(?:-\d+)?$")  # run-<UTC stamp>, or run-<UTC stamp>-<pid> (non-git homing)
SHASUM_RE = re.compile(r"^([0-9a-fA-F]{64}) [ *](.+)$")
VERDICT_COLUMNS = ("verdict", "repo_verdict", "status", "result", "proof", "state")
MAC_PREFIXES = ("/Users", "/System/Volumes/Data/Users", "/Volumes/Macintosh HD/Users")
PRUNE_NAMES = (
    ".Spotlight-V100",
    ".fseventsd",
    ".Trashes",
    ".DocumentRevisions-V100",
    ".TemporaryItems",
    "*.sparsebundle",
)
HUMAN_ONLY = {"human-erase"}

# Ported verbatim from scripts/mac-exit/classify-git-sweep.py (the producer's input rules).
DISPOSABLE_MARKERS = (
    "/_agents/cache/",
    "/.tmp/plugins",
    "/.staging/",
    "/custody-staging/",
    "/pytest-fixtures",
    "/legacy-home/preserved-repos/",
    "/.agent-runtime/codex/.tmp/",
)

# Ported verbatim from preserve-git.sh (credential-pattern filter).
CRED_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.jks", "*.keystore", "*.kdbx",
    "*.keychain", "*.keychain-db", "id_rsa*", "id_dsa*", "id_ecdsa*", "id_ed25519*",
    ".netrc", "_netrc", ".npmrc", ".pypirc", ".git-credentials", ".pgpass",
    "credentials", "credentials.json", "service-account*.json", "*.token", ".token", "token",
    "tokens.json", "secrets.json", "secrets.yaml", "secrets.yml", "*.secret",
]  # fmt: skip
CRED_DIRS = {".ssh", ".gnupg", ".aws", ".1password", "1password", "keychains", "private_keys"}
SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".pub")

GIT_BASE = ["git", "-c", "core.fsmonitor=false", "-c", "color.ui=false", "-c", "core.pager=cat"]
DIFF_FLAGS = ["diff", "--binary", "--no-ext-diff", "--no-textconv", "--default-prefix", "--no-relative"]


def default_device_of(path: str) -> int:
    """The device a path really lives on (symlinks resolved first); raises OSError when it does not exist."""
    return os.stat(os.path.realpath(path)).st_dev


@dataclasses.dataclass(frozen=True)
class Media:
    """What a path's storage physically is (H2a). `external` only when its bytes sit on a disk that leaves with the
    externals; `why` is the evidence, or the reason it could not be established."""

    external: bool
    mount: str
    why: str


MEDIA_IMAGE_DEPTH = 4  # an image inside an image inside ...: past this the backing chain is not followed (fail closed)


def run_plist(argv: list[str]) -> dict[str, object]:
    proc = subprocess.run(argv, check=False, capture_output=True, stdin=subprocess.DEVNULL, timeout=120)
    if proc.returncode != 0:
        raise OSError(f"{argv[0]} exit {proc.returncode}: {one_line(proc.stderr.decode('utf-8', 'replace'), 120)}")
    loaded = plistlib.loads(proc.stdout)
    if not isinstance(loaded, dict):
        raise ValueError(f"{argv[0]} returned a {type(loaded).__name__}, not a dictionary")
    return loaded


def default_media_of(path: str, depth: int = 0) -> Media:
    """H2a: whether a path's bytes live on an external physical disk. A device that differs from $HOME's proves
    nothing (an internal APFS volume, or a disk image whose file is on the Mac, has a device of its own), so this reads
    `diskutil info` for the disk under the path's mount. A disk image reports itself as external, removable media, so
    it is judged by the media its backing file lives on instead. Anything that cannot be established is not external."""
    real = os.path.realpath(path) if path else ""
    if not real:
        return Media(False, "", "no path to place")
    try:
        proc = subprocess.run(
            ["df", "-P", real], check=False, capture_output=True, stdin=subprocess.DEVNULL, timeout=60
        )
        lines = proc.stdout.decode("utf-8", "surrogateescape").splitlines()
        if proc.returncode != 0 or len(lines) < 2:
            return Media(False, "", f"df cannot place {real}")
        fields = lines[-1].split(None, 5)
        node, mount = fields[0], (fields[5] if len(fields) > 5 else "")
        if not node.startswith("/dev/disk"):
            return Media(False, mount, f"{mount or real} is not on a local disk ({node})")
        info = run_plist(["diskutil", "info", "-plist", node])
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError) as exc:
        return Media(False, "", f"cannot read the disk under {real}: {exc}")
    bus = str(info.get("BusProtocol", ""))
    ident = str(info.get("DeviceIdentifier", ""))
    if bus == "Disk Image":
        if depth >= MEDIA_IMAGE_DEPTH:
            return Media(False, mount, f"{mount}: disk images nested deeper than {MEDIA_IMAGE_DEPTH} are not followed")
        whole = "/dev/" + str(info.get("ParentWholeDisk", ""))
        try:
            images = run_plist(["hdiutil", "info", "-plist"]).get("images", [])
        except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError) as exc:
            return Media(False, mount, f"{mount} is a disk image whose backing file cannot be found: {exc}")
        for image in images if isinstance(images, list) else []:
            entities = image.get("system-entities", []) if isinstance(image, dict) else []
            devs = {str(e.get("dev-entry", "")) for e in entities if isinstance(e, dict)}
            if whole in devs or node in devs:
                backing_path = str(image.get("image-path", ""))
                backing = default_media_of(backing_path, depth + 1)
                return Media(backing.external, mount, f"{mount} is a disk image backed by {backing_path}: {backing.why}")
        return Media(False, mount, f"{mount} is a disk image ({ident}) that hdiutil does not list")
    if info.get("Internal") is False and info.get("RemovableMediaOrExternalDevice") is True:
        return Media(True, mount, f"{mount} is on an external {bus or 'disk'} ({ident})")
    return Media(False, mount, f"{mount} is on the Mac's internal {bus or 'disk'} ({ident})")


# ----------------------------------------------------------------------------------------------------
# data types
# ----------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class Problem:
    code: str
    subject: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {tilde(self.subject)}: {self.message}"


@dataclasses.dataclass
class Waiver:
    """A signed, evidenced exception for one sweep row that vanished from the Mac."""

    path: str
    reason: str
    evidence: str
    signer: str
    kind: str = ""
    exposure: str = ""  # the sweep's own reasons for the row (dirty=.., unpushed=..): what the waiver gives up
    signed_at: str = ""


@dataclasses.dataclass
class Result:
    check_id: str
    status: str
    detail: str
    problems: list[Problem] = dataclasses.field(default_factory=list)
    extra: list[str] = dataclasses.field(default_factory=list)
    waived: list[Waiver] = dataclasses.field(default_factory=list)
    info: list[str] = dataclasses.field(default_factory=list)
    crashed: bool = False  # the check itself raised: its FAIL is an internal error (exit 70), not a finding


@dataclasses.dataclass
class Ctx:
    sweep: Path
    max_sweep_age_min: float
    preserve_root: Path
    remote_held: Path | None
    externals: list[str]
    nongit_runs: list[Path]
    backblaze_attestation: Path | None
    t7_unique: Path
    t7_source: Path
    volumes_root: Path
    credential_wall: Path
    recovery_root: Path | None = None
    preserve_runs: list[Path] | None = None
    credential_attestation: Path | None = None
    waivers: Path | None = None
    hash_t7_originals: bool = False
    deep: bool = True  # H4: object-level verification is the default; --no-deep is the opt-out
    verbose: bool = False
    scratch: Path | None = None
    gitfile_depth: int = 0  # F4: unbounded by default
    # the fresh scan walks the roots in the sweep's roots file (scan_universe) PLUS these, and the $HOME strays when
    # discovery_strays; only a Ctx built in code can switch the sweep's roots off (make_ctx always scans them)
    discovery_roots: list[Path] = dataclasses.field(default_factory=list)
    discovery_strays: bool = False
    ignored_payload_attestation: Path | None = None
    disposals: Path | None = None
    universe_cache: dict[str, object] = dataclasses.field(default_factory=dict, init=False, repr=False, compare=False)
    repo_cache: dict[str, object] = dataclasses.field(default_factory=dict, init=False, repr=False, compare=False)
    home: str = dataclasses.field(default_factory=lambda: os.environ.get("HOME", "/"))
    now: float = dataclasses.field(default_factory=time.time)
    is_mount: Callable[[str], bool] = os.path.ismount
    waiver_signers: Path | None = None
    nongit_items: list[Path] = dataclasses.field(default_factory=list)
    max_remote_held_age_min: float = DEFAULTS["max_remote_held_age_min"]
    device_of: Callable[[str], int] = default_device_of  # injected so a fixture tree can stand in for two disks
    media_of: Callable[[str], Media] = default_media_of  # H2a: physical media, injected like device_of
    scan_universe: bool = True  # walk the roots named by the sweep's roots file; False only for a hand-built sweep


@dataclasses.dataclass
class Need:
    row: dict[str, str]
    reasons: list[str]
    dirty: bool = False
    bundle: bool = False
    head: bool = False
    common: str | None = None
    orphan: bool = False
    marker: bool = False  # the path carries a disposable marker; that earns no exemption (F3)
    filtered: bool = False  # §7: a clean/smudge filter keeps bytes in the working tree that git never stores
    gitdir: list[str] = dataclasses.field(default_factory=list)  # §6: why a raw git-dir copy is required (live git)
    lfs_storage: str = ""  # §6: an lfs.storage directory outside the git dir that needs its own tar
    git_error: str = ""  # a live git read for the §6/§7 requirements failed; reported, never read as "none"


# ----------------------------------------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------------------------------------
def tilde(path: str) -> str:
    home = os.environ.get("HOME", "")
    return "~" + path[len(home) :] if home and path.startswith(home + "/") else path


def one_line(text: str, limit: int = 900) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    fd = os.open(path, os.O_RDONLY)
    try:
        with contextlib.suppress(Exception):
            fcntl.fcntl(fd, F_NOCACHE, 1)
        while True:
            block = os.read(fd, 1 << 20)
            if not block:
                break
            digest.update(block)
    finally:
        os.close(fd)
    return digest.hexdigest()


def is_cred(rel: str) -> bool:
    parts = [p for p in rel.lower().split("/") if p]
    if not parts:
        return False
    if any(d in CRED_DIRS for d in parts[:-1]):
        return True
    base = parts[-1]
    if base.endswith(SAFE_SUFFIXES):
        return False
    return any(fnmatch.fnmatchcase(base, pat) for pat in CRED_PATTERNS)


def slugify(path: str, home: str) -> str:
    """Mirror preserve-git.sh slugify: $HOME-relative, / -> __, 150 bytes (LC_ALL=C), -<8 hex of sha256(path)>."""
    if path.startswith(home + "/"):
        rel = path[len(home) + 1 :]
    else:
        rel = path.removeprefix("/")
    rel_b = rel.replace("/", "__").encode("utf-8", "surrogateescape")[:150]
    digest = hashlib.sha256(path.encode("utf-8", "surrogateescape")).hexdigest()
    return rel_b.decode("utf-8", "surrogateescape") + "-" + digest[:8]


def git_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    # No lazy fetch from a promisor remote, no prompt: a missing object is a git error, never a network call.
    env.update(GIT_OPTIONAL_LOCKS="0", LC_ALL="C", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    return env


def run_git(
    args: list[str | bytes],
    *,
    cwd: str | None = None,
    gitdir: str | None = None,
    timeout: float = 600,
    data: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    """Run git read-only (`data` is fed to its stdin). Returns rc 124 on timeout and rc 127 if git is missing, never
    raises."""
    cmd: list[str | bytes] = list(GIT_BASE)
    if gitdir:
        cmd.append("--git-dir=" + gitdir)
    if cwd:
        cmd += ["-C", cwd]
    cmd += args
    try:
        return subprocess.run(
            [os.fsencode(a) for a in cmd],
            check=False,
            capture_output=True,
            env=git_env(),
            stdin=subprocess.DEVNULL if data is None else None,
            input=data,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, b"", b"timeout")
    except OSError as exc:
        return subprocess.CompletedProcess(cmd, 127, b"", str(exc).encode())


def err_tail(proc: subprocess.CompletedProcess[bytes]) -> str:
    text = (proc.stderr or b"").decode("utf-8", "replace").strip()
    return one_line(text.splitlines()[-1] if text else f"rc={proc.returncode}", 200)


class GitReadError(Exception):
    """A git read whose answer decides a verdict failed (H3): never to be read as an empty or zero result."""


def must(proc: subprocess.CompletedProcess[bytes], what: str) -> subprocess.CompletedProcess[bytes]:
    if proc.returncode != 0:
        raise GitReadError(f"{what} failed: {err_tail(proc)}")
    return proc


def stream_digest(cmd: list[bytes]) -> tuple[str, int, int, str]:
    """sha256 + byte count of a command's stdout without buffering it. Returns (sha, nbytes, rc, stderr tail)."""
    digest = hashlib.sha256()
    total = 0
    with tempfile.TemporaryFile() as errf:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf, stdin=subprocess.DEVNULL, env=git_env())
        assert proc.stdout is not None
        while True:
            block = proc.stdout.read(1 << 20)
            if not block:
                break
            digest.update(block)
            total += len(block)
        rc = proc.wait()
        errf.seek(0)
        tail = errf.read().decode("utf-8", "replace").strip()
    return digest.hexdigest(), total, rc, one_line(tail.splitlines()[-1] if tail else "", 200)


def parse_shasum_manifest(path: Path) -> tuple[list[tuple[str, str]], list[str]]:
    """Parse `<sha256>  <relpath>` lines. Returns (entries, malformed line descriptions)."""
    entries: list[tuple[str, str]] = []
    bad: list[str] = []
    text = path.read_bytes().decode("utf-8", "surrogateescape")
    for lineno, line in enumerate(text.split("\n"), start=1):
        if not line:
            continue
        match = SHASUM_RE.match(line)
        if not match:
            bad.append(f"line {lineno}")
            continue
        entries.append((match.group(1).lower(), match.group(2)))
    return entries, bad


def safe_rel(rel: str) -> bool:
    return bool(rel) and not rel.startswith("/") and ".." not in rel.split("/")


def media_for(ctx: Ctx, path: str) -> Media:
    """The physical media under a path, probed once per device: a device is one mounted filesystem, so every path on
    it sits on the same disk. The cache lives on the Ctx, so a replaced Ctx (another probe) starts empty."""
    try:
        key = f"media:{ctx.device_of(path)}"
    except OSError:
        key = ""
    hit = ctx.universe_cache.get(key) if key else None
    if isinstance(hit, Media):
        return hit
    try:
        media = ctx.media_of(path)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        media = Media(False, "", f"the disk under {path} could not be probed: {exc}")
    if key:
        ctx.universe_cache[key] = media
    return media


def custody_problem(ctx: Ctx, path: str | os.PathLike[str]) -> str:
    """H2/H2a: '' when the path's bytes sit on an external physical disk (so they survive erasing the Mac), else why
    not. A device that differs from $HOME's proves nothing: an internal APFS volume and a disk image kept on the Mac
    have devices of their own, so the verdict is the media's (an image is judged by its backing file's disk)."""
    media = media_for(ctx, str(path))
    if media.external:
        return ""
    try:
        if ctx.device_of(str(path)) == ctx.device_of(ctx.home):
            return f"{tilde(str(path))} is on the same device as $HOME, i.e. on the Mac's own disk"
    except OSError:
        pass
    return f"{tilde(str(path))} is not on an external disk, so it goes with the Mac ({media.why})"


def within_real(root: str | os.PathLike[str], rel: str) -> bool:
    """H2/F8: root/rel resolves to itself, i.e. no symlink on the way leads out of (or around) the copy."""
    return os.path.realpath(os.path.join(root, rel)) == os.path.join(os.path.realpath(root), os.path.normpath(rel))


def verify_hash_entries(
    root: Path, entries: list[tuple[str, str]], ctx: Ctx | None = None
) -> tuple[list[str], int, int]:
    """Re-hash every entry under root. Returns (problems, files hashed, bytes hashed).

    An entry reached through a symlink is rejected (a link can lead back onto the Mac); with a ctx, an entry on the
    Mac's own device is rejected too."""
    problems: list[str] = []
    files = nbytes = 0
    for sha, rel in entries:
        if not safe_rel(rel):
            problems.append(f"unsafe path in manifest: {rel}")
            continue
        path = root / rel
        if not within_real(root, rel):
            problems.append(f"symlinked or escapes the copy: {rel}")
            continue
        if not path.is_file():
            problems.append(f"missing: {rel}")
            continue
        if ctx is not None and (why := custody_problem(ctx, path)):
            problems.append(f"not off the Mac: {rel} ({why})")
            continue
        try:
            got = sha256_file(path)
        except OSError as exc:
            problems.append(f"unreadable: {rel} ({exc.strerror})")
            continue
        files += 1
        nbytes += path.stat().st_size
        if got != sha:
            problems.append(f"sha256 mismatch: {rel}")
    return problems, files, nbytes


# ----------------------------------------------------------------------------------------------------
# sweep + classification (the producer's input rules)
# ----------------------------------------------------------------------------------------------------
class SweepError(Exception):
    pass


def load_sweep(path: Path) -> list[dict[str, str]]:
    try:
        text = path.read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise SweepError(f"cannot read sweep {path}: {exc.strerror}") from exc
    lines = text.split("\n")
    header = lines[0].split("\t")
    missing = [c for c in SWEEP_COLS if c not in header]
    if missing:
        raise SweepError(f"sweep header lacks columns {missing}")
    rows = []
    for lineno, line in enumerate(lines[1:], start=2):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < len(header):
            raise SweepError(f"sweep line {lineno} has {len(parts)} columns, expected {len(header)}")
        rows.append(dict(zip(header, parts, strict=False)))
    return rows


def reasons_for(row: dict[str, str]) -> list[str]:
    reasons: list[str] = []
    if row["kind"] in ("repo", "bare"):
        if row["remote"] == "NONE":
            reasons.append("no-origin")
        if row["unpushed"] not in ("0", ""):
            reasons.append("unpushed")
        if row["stashes"] not in ("0", ""):
            reasons.append("stash")
    if row["dirty"] not in ("0", ""):
        reasons.append("dirty")
    # FP-DETACHED-REPO: a main checkout on a detached HEAD holds local commits just as a linked worktree does
    if row["branch"] == "(detached)" and row["head_remote_branches"] == "0":
        reasons.append("detached-head-on-no-remote-branch")
    return reasons


class Held(dict[str, set[str]]):
    """The remote-held verdicts by checkout path, as written, plus what the same rows say about each checkout (§4):
    the repository `labels` that tips.tsv is keyed by, the `commons` (git common dirs) the proof was made for and the
    documented `gaps` of the proof. A dict, so the per-checkout shapes and unit tests keep passing plain mappings."""

    def __init__(self, data: dict[str, set[str]] | None = None) -> None:
        super().__init__(data or {})
        self.labels: dict[str, str] = {}
        self.commons: dict[str, str] = {}
        self.gaps: dict[str, set[str]] = {}


def split_end_row(text: str, what: str) -> list[str]:
    """§3 (P6): the rows of a prover TSV without its completion row. The file must end in exactly one full-width
    `#END rows=N` row, N equal to the number of data rows; a file cut short by a crash, or one that was edited,
    lacks it. The completion row is never data. Raises SweepError otherwise."""
    rows = [ln for ln in text.split("\n") if ln.strip()]
    if not rows:
        raise SweepError(f"{what} is empty")
    marks = [i for i, ln in enumerate(rows) if ln.split("\t", 1)[0].startswith("#END")]
    if not marks:
        raise SweepError(f"{what} has no '#END rows=N' completion row, so it was cut short or never finished")
    if len(marks) > 1:
        raise SweepError(f"{what} has {len(marks)} '#END' rows; exactly one, at the end, is allowed")
    if marks[0] != len(rows) - 1:
        raise SweepError(f"{what} has rows after its '#END' row")
    cells = rows[-1].split("\t")
    header = rows[0].split("\t")
    found = re.fullmatch(r"#END rows=(\d+)", cells[0])
    if found is None or len(cells) != len(header) or any(c != "#END" for c in cells[1:]):
        raise SweepError(f"{what} ends in a malformed completion row: {one_line(rows[-1], 80)}")
    if int(found.group(1)) != len(rows) - 2:
        raise SweepError(f"{what}: its '#END' row says rows={found.group(1)} but the file holds {len(rows) - 2} data rows")
    return rows[:-1]


def load_remote_held(path: Path) -> Held:
    """checkout path -> set of upper-cased verdicts. Raises SweepError on an unrecognised header or a file without
    its `#END rows=N` row (fail closed).

    Two shapes are read, both written by the prove lane: one row per checkout (a `path` column, as in its
    entries.tsv with `repo_verdict`), or one row per repository (a `paths` column of `;`-joined checkouts, as in
    its remote-held.tsv with `verdict`, which must also carry `repo`, `common_dir` and `gaps`). A checkout listed
    under several rows is held only if every row says so. The keys are the file's own spelling: they are realpaths
    (§1), and a lookup uses the realpath of the swept path, so a spelling that differs matches nothing.
    """
    try:
        text = path.read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise SweepError(f"cannot read remote-held file {path}: {exc.strerror}") from exc
    lines = split_end_row(text, "remote-held file")
    header = [c.strip().lower() for c in lines[0].split("\t")]
    pcol = next((c for c in ("path", "paths") if c in header), None)
    if pcol is None:
        raise SweepError(f"remote-held header has no 'path' or 'paths' column: {header}")
    vcol = next((c for c in VERDICT_COLUMNS if c in header), None)
    if vcol is None:
        raise SweepError(f"remote-held header has no verdict column among {list(VERDICT_COLUMNS)}: {header}")
    per_repo = pcol == "paths"
    if per_repo and (missing := [c for c in ("repo", "common_dir", "gaps") if c not in header]):
        raise SweepError(f"remote-held header lacks the column(s) {missing} the per-repository shape carries")
    pi, vi = header.index(pcol), header.index(vcol)
    held = Held()
    verdicts: dict[str, set[str]] = collections.defaultdict(set)
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            raise SweepError(f"remote-held row has too few columns: {one_line(line, 80)}")
        if not per_repo:
            verdicts[parts[pi]].add(parts[vi].strip().upper())
            continue
        label, common = parts[header.index("repo")], parts[header.index("common_dir")]
        gaps = {g.strip() for g in parts[header.index("gaps")].split(";") if g.strip()}
        for checkout in (c for c in parts[pi].split(";") if c):
            verdicts[checkout].add(parts[vi].strip().upper())
            if checkout in held.labels and (held.labels[checkout], held.commons[checkout]) != (label, common):
                gaps.add("AMBIGUOUS-ROWS")  # two repositories claim this checkout: neither proof is believed
            held.labels.setdefault(checkout, label)
            held.commons.setdefault(checkout, common)
            held.gaps.setdefault(checkout, set()).update(gaps)
    held.update(verdicts)
    return held


@dataclasses.dataclass
class Plan:
    needs: list[Need]
    entries: int = 0
    safe: int = 0
    disposable: int = 0
    waived: int = 0


REF_REASONS = {"no-origin", "unpushed", "stash", "remote-not-proven"}
UNSTORED = "filtered-content"  # §7: working-tree bytes a clean filter keeps out of every blob; never waived


def build_plan(
    rows: list[dict[str, str]], held: dict[str, set[str]] | None, extra: dict[str, list[str]] | None = None
) -> Plan:
    """What needs preservation. With a remote-held mapping, a row is safe only when it is PROVEN-ALL there: a row the
    file does not name is unproven like any other (§5, FP-REMOTE-TRUST), never trusted for being absent. `extra` holds
    the reasons live git adds per row (UNSTORED)."""
    plan = Plan(needs=[], entries=len(rows))
    for row in rows:
        reasons = reasons_for(row) + list((extra or {}).get(row["path"], []))
        verdicts = held.get(os.path.realpath(row["path"]), set()) if held is not None else None
        proven = verdicts == {"PROVEN-ALL"}
        if verdicts is not None and not proven:
            reasons.append("remote-not-proven")
        if not reasons:
            plan.safe += 1
            continue
        waivable = {"unpushed", "detached-head-on-no-remote-branch"}
        remaining = list(reasons)
        if proven and row["remote"] != "NONE":
            remaining = [r for r in reasons if r not in waivable]
        # F3: a path marker is not evidence about the repository. A marked row is counted, then judged like any other.
        marker = any(m in row["path"] for m in DISPOSABLE_MARKERS)
        plan.disposable += marker
        need = Need(
            row=row,
            reasons=reasons,
            dirty="dirty" in remaining,
            bundle=bool(REF_REASONS & set(remaining)),
            head="detached-head-on-no-remote-branch" in remaining,
            marker=marker,
            filtered=UNSTORED in remaining,
        )
        if not (need.dirty or need.bundle or need.head or need.filtered):
            plan.waived += 1
            continue
        plan.needs.append(need)
    return plan


# ----------------------------------------------------------------------------------------------------
# live exposure: what the sweep, a proof file or a run says about a checkout is not trusted until git agrees
# ----------------------------------------------------------------------------------------------------
# §12: the fresh scan is never narrower than the sweep. It walks exactly the roots the sweep says it walked (its roots
# file), plus whatever --discovery-root adds, plus the strays directly under $HOME. These names are the only ones the
# sweep leaves out of $HOME (git-sweep.sh: every other directory under $HOME is a root, ~/.local/share included).
STRAY_PRUNE = ("Library", ".Trash", ".cache", ".npm", ".cargo", ".rustup")
END_ROW = re.compile(r"#END rows=(\d+)")


def roots_path(sweep: Path) -> Path:
    """§12: the sweep's roots file is the sweep path with its last suffix replaced by `.roots`."""
    return sweep.with_suffix(".roots")


def load_roots(path: Path) -> list[str]:
    """The roots a sweep walked: one absolute path per line and a closing `#END rows=N`. Raises SweepError when the
    file is missing, unreadable, or does not end in a completion row that counts its roots."""
    try:
        lines = [ln for ln in path.read_bytes().decode("utf-8", "surrogateescape").split("\n") if ln.strip()]
    except OSError as exc:
        raise SweepError(f"cannot read the sweep's roots file {path}: {exc.strerror}") from exc
    found = END_ROW.fullmatch(lines[-1].strip()) if lines else None
    if found is None:
        raise SweepError(f"the sweep's roots file {path.name} has no '#END rows=N' row, so it is cut short or not one")
    roots = lines[:-1]
    if int(found.group(1)) != len(roots) or any(not r.startswith("/") for r in roots):
        raise SweepError(f"the sweep's roots file {path.name} does not hold {found.group(1)} absolute root paths")
    return roots


def default_roots(home: str) -> list[str]:
    """git-sweep.sh's default roots, as they exist now (§12): the realpath of every directory directly under $HOME except
    the names the sweep leaves out, plus $HOME/.local/share. A sweep taken with explicit ROOT arguments may have walked
    fewer, and a directory created after the sweep is in none of its roots."""
    try:
        names = sorted(os.listdir(home))
    except OSError:
        return []
    found = [os.path.realpath(os.path.join(home, n)) for n in names if n not in STRAY_PRUNE and os.path.isdir(os.path.join(home, n))]
    share = os.path.join(home, ".local", "share")
    if os.path.isdir(share):
        found.append(os.path.realpath(share))
    return list(dict.fromkeys(found))


def scan_expression() -> list[str]:
    """What the fresh scan looks for under a root: a `.git` entry in any case (not descended into), and any directory
    named objects, whose parent is a bare repository when it also holds HEAD and refs/."""
    return ["(", "-iname", ".git", "-print0", "-prune", ")", "-o", "(", "-type", "d", "-iname", "objects", "-print0", ")"]


def discovery_scans(ctx: Ctx) -> tuple[list[tuple[str, list[str]]], list[Problem]]:
    """The find invocations: (label, argv) for each root that applies, and the problems reading the roots file raised.
    No depth bound and no prune below a root: the sweep's own bounds and prunes are blind spots, not rules."""
    problems: list[Problem] = []
    roots: list[str] = []
    if ctx.scan_universe:
        try:
            walked = load_roots(roots_path(ctx.sweep))
        except SweepError as exc:
            problems.append(Problem("input-unusable", str(roots_path(ctx.sweep)), str(exc)))
        else:
            roots += walked
            if ctx.discovery_strays:  # PS-2: a sweep taken with narrow explicit ROOT arguments does not narrow this check
                problems += [
                    Problem("universe-miss", root, "the sweep did not walk this default root (see its roots file)")
                    for root in default_roots(ctx.home)
                    if not any(root == w or root.startswith(w + "/") for w in walked)
                ]
    roots += [str(r) for r in ctx.discovery_roots]
    scans = [(r, ["find", r, "-xdev", *scan_expression()]) for r in dict.fromkeys(roots)]
    if ctx.discovery_strays:
        skip: list[str] = ["("]
        for index, name in enumerate(STRAY_PRUNE):
            skip += (["-o"] if index else []) + ["-path", os.path.join(ctx.home, name)]
        skip += [")", "-prune", "-o"]
        scans.append((ctx.home, ["find", ctx.home, "-xdev", "-maxdepth", "3", *skip, *scan_expression()]))
    return scans, problems


def checkouts_in(listing: bytes) -> set[str]:
    """The checkouts and bare repositories in one find's NUL-separated output (see scan_expression)."""
    found: set[str] = set()
    bare: list[str] = []
    for raw in listing.split(b"\0"):
        entry = os.fsdecode(raw)
        if not entry:
            continue
        parent, name = os.path.dirname(entry), os.path.basename(entry).lower()
        if "/.git/" in parent.lower() + "/":
            continue
        if name == ".git":
            found.add(parent)
        elif name == "objects" and os.path.basename(parent).lower() != ".git":
            if os.path.isfile(os.path.join(parent, "HEAD")) and os.path.isdir(os.path.join(parent, "refs")):
                bare.append(parent)
    # the sweep's rule: git itself calls the directory a bare repository and it is its own git dir. A separate-git-dir
    # gitdir (core.worktree set) is not bare, and a candidate inside an accepted bare directory is part of it
    for candidate in sorted(bare):
        if any(candidate.startswith(accepted + "/") for accepted in found if accepted in bare):
            continue
        ids = run_git(["rev-parse", "--path-format=absolute", "--is-bare-repository", "--absolute-git-dir"], cwd=candidate)
        lines = ids.stdout.decode("utf-8", "surrogateescape").splitlines()
        if ids.returncode == 0 and len(lines) == 2 and lines[0] == "true" and os.path.realpath(lines[1]) == os.path.realpath(candidate):
            found.add(candidate)
    return found


def discover_repos(ctx: Ctx) -> tuple[list[str], list[Problem]]:
    """Every checkout and bare repository a scan made NOW finds. A find that errors is a discovery-incomplete problem,
    never a short list; a missing or unusable roots file is input-unusable."""
    scans, problems = discovery_scans(ctx)
    key = repr(([label for label, _ in scans], ctx.scan_universe))
    cached = ctx.universe_cache.get(key)
    if isinstance(cached, tuple):
        return cached
    found: set[str] = set()
    for label, cmd in scans:
        try:
            proc = subprocess.run(cmd, check=False, capture_output=True, stdin=subprocess.DEVNULL, timeout=3600)
        except (subprocess.TimeoutExpired, OSError) as exc:
            problems.append(Problem("discovery-incomplete", label, f"the scan could not finish: {exc}"))
            continue
        if proc.returncode != 0 or proc.stderr.strip():
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[:1]
            problems.append(
                Problem(
                    "discovery-incomplete",
                    label,
                    "find reported errors, so the list of checkouts is incomplete: "
                    + (tail[0] if tail else f"rc={proc.returncode}"),
                )
            )
        found |= checkouts_in(proc.stdout)
    result = (sorted(found), problems)
    ctx.universe_cache[key] = result
    return result


def universe_problems(ctx: Ctx, rows: list[dict[str, str]]) -> list[Problem]:
    """F2: the sweep is the universe only if a fresh scan finds nothing it does not list."""
    if not ctx.scan_universe and not ctx.discovery_roots and not ctx.discovery_strays:
        return []  # only a Ctx built in code can say so: make_ctx always scans the sweep's roots
    found, problems = discover_repos(ctx)
    swept = {os.path.realpath(r["path"]) for r in rows}
    missing = [repo for repo in found if os.path.realpath(repo) not in swept]
    return [
        *problems,
        *(Problem("universe-miss", repo, "a git checkout on disk that the sweep does not list") for repo in missing),
    ]


def path_state(path: str) -> str:
    """`present`, `gone` (FileNotFoundError only) or `unknown` (any other stat failure, or not a directory)."""
    try:
        info = os.stat(path)
    except (FileNotFoundError, NotADirectoryError):
        return "gone"
    except OSError:
        return "unknown"
    return "present" if stat.S_ISDIR(info.st_mode) else "unknown"


def blob_id(path: str, rel: bytes) -> str:
    """What `git add` would store for this file (a symlink: its target), so it can be compared with the index."""
    full = os.path.join(os.fsencode(path), rel)
    if os.path.islink(full):
        proc = subprocess.run(
            [*GIT_BASE, "-C", path, "hash-object", "-t", "blob", "--stdin"],
            input=os.readlink(full),
            capture_output=True,
            check=False,
            env=git_env(),
        )
    else:
        proc = run_git(["hash-object", "--", rel], cwd=path)
    return must(proc, "hash-object").stdout.decode().strip()


def hidden_edits(path: str) -> tuple[int, int]:
    """F6: (skip-worktree / assume-unchanged entries present on disk, those whose content differs from the index).

    git status, git diff and the producer's tracked patch all skip such entries, so an edit to one is invisible to
    every other check. Entries absent from disk are legitimate sparse-checkout paths and are not counted.
    """
    listing = must(run_git(["ls-files", "-v", "-z"], cwd=path), "ls-files -v").stdout.split(b"\0")
    flagged = [e[2:] for e in listing if len(e) > 2 and (e[:1] == b"S" or e[:1].islower())]
    if not flagged:
        return 0, 0
    staged = must(run_git(["ls-files", "--stage", "-z"], cwd=path), "ls-files --stage").stdout.split(b"\0")
    index = {e.split(b"\t", 1)[1]: e.split(b"\t", 1)[0].split()[1].decode() for e in staged if b"\t" in e}
    present = differ = 0
    for rel in flagged:
        if not os.path.lexists(os.path.join(os.fsencode(path), rel)):
            continue
        present += 1
        if blob_id(path, rel) != index.get(rel):
            differ += 1
    return present, differ


def live_row(path: str) -> tuple[dict[str, str], int, str] | None:
    """git-sweep.sh's columns recomputed from live git, plus the hidden-edit count and the git common dir (realpath).
    None: git cannot resolve the path.

    `kind` is derived from git exactly as the sweep does (§12): `bare` when git says the repository is bare; else `repo`
    when the git dir is the common dir (a main checkout, including a submodule or a separate-git-dir checkout whose
    `.git` is a file); else `worktree`. A failing read raises GitReadError instead of reading as 0 (F2, H3).
    """
    ids = run_git(
        ["rev-parse", "--path-format=absolute", "--is-bare-repository", "--absolute-git-dir", "--git-common-dir"],
        cwd=path,
    )
    lines = ids.stdout.decode("utf-8", "surrogateescape").splitlines()
    if ids.returncode != 0 or len(lines) != 3 or lines[0] not in ("true", "false"):
        return None
    bare = lines[0] == "true"
    gitdir, common = os.path.realpath(lines[1]), os.path.realpath(lines[2])
    if bare:
        if gitdir != os.path.realpath(path):
            return None  # a directory inside a bare repository is not the repository
    else:
        top = run_git(["rev-parse", "--path-format=absolute", "--show-toplevel"], cwd=path)
        if top.returncode != 0 or os.path.realpath(top.stdout.decode("utf-8", "surrogateescape").strip()) != (
            os.path.realpath(path)
        ):
            return None  # git found an enclosing repository, not one of its own
    sym = run_git(["symbolic-ref", "--short", "-q", "HEAD"], cwd=path)
    if sym.returncode == 0 and sym.stdout.strip():
        branch = sym.stdout.decode("utf-8", "surrogateescape").strip()
    elif sym.returncode == 1:
        branch = "(detached)"
    else:
        must(sym, "symbolic-ref HEAD")
        branch = "(detached)"
    cfg = run_git(["config", "--get", "remote.origin.url"], cwd=path)
    if cfg.returncode != 1:
        must(cfg, "config remote.origin.url")
    probe = run_git(["rev-parse", "-q", "--verify", "HEAD"], cwd=path)
    if probe.returncode not in (0, 1):
        must(probe, "rev-parse HEAD")
    # a bare repository has no working tree: nothing is dirty and `git status` would refuse to run
    dirty = (
        0
        if bare
        else len(
            must(run_git(["status", "--porcelain=v1", "--untracked-files=normal"], cwd=path), "status").stdout.splitlines()
        )
    )
    unpushed = must(run_git(["rev-list", "--count", "--branches", "--not", "--remotes"], cwd=path), "rev-list")
    containing = (
        must(run_git(["branch", "-r", "--contains", "HEAD"], cwd=path), "branch -r --contains").stdout.splitlines()
        if probe.returncode == 0
        else []
    )
    row = {
        "kind": "bare" if bare else "repo" if gitdir == common else "worktree",
        "branch": branch,
        "remote": cfg.stdout.decode("utf-8", "surrogateescape").strip() or "NONE",
        "dirty": str(dirty),
        "unpushed": unpushed.stdout.decode().strip(),
        "stashes": str(stash_count(common)),
        "head_remote_branches": str(len(containing)),
    }
    return row, 0 if bare else hidden_edits(path)[1], common


@dataclasses.dataclass
class Trust:
    """Whether a remote-held PROVEN-ALL verdict may be believed at all, and the per-ref tips it must be bound to."""

    tips: dict[str, dict[str, tuple[str, str, str]]] | None = None
    labels: dict[str, str] = dataclasses.field(default_factory=dict)
    commons: dict[str, str] = dataclasses.field(default_factory=dict)
    gaps: dict[str, set[str]] = dataclasses.field(default_factory=dict)
    why: str = ""


def load_tips(path: Path) -> dict[str, dict[str, tuple[str, str, str]]] | None:
    """repo label -> ref key -> (tip, status, kind) from the prove lane's tips.tsv (§2). None when the file is absent.
    A file without its `#END rows=N` row raises SweepError (§3); the same key twice with different content is kept as
    UNPROVEN-CONFLICT, never resolved in the proof's favour."""
    if not path.is_file():
        return None
    lines = split_end_row(path.read_bytes().decode("utf-8", "surrogateescape"), "tips.tsv")
    header = lines[0].split("\t")
    wanted = ("repo", "ref", "kind", "tip", "status")
    if any(c not in header for c in wanted):
        raise SweepError(f"tips header lacks columns among {list(wanted)}: {header}")
    at = {c: header.index(c) for c in wanted}
    tips: dict[str, dict[str, tuple[str, str, str]]] = collections.defaultdict(dict)
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) < len(header):
            raise SweepError(f"tips row has too few columns: {one_line(line, 80)}")
        row = (parts[at["tip"]], parts[at["status"]], parts[at["kind"]])
        known = tips[parts[at["repo"]]].get(parts[at["ref"]])
        tips[parts[at["repo"]]][parts[at["ref"]]] = row if known in (None, row) else (known[0], "UNPROVEN-CONFLICT", known[2])
    return dict(tips)


def proof_trust(ctx: Ctx, held: dict[str, set[str]] | None) -> tuple[Trust, list[Problem]]:
    """F1: a PROVEN-ALL verdict is believed only while its file is recent and bound to ref tips (tips.tsv beside it)."""
    trust, problems = Trust(), []
    if ctx.remote_held is None or held is None:
        return trust, problems
    try:
        age_min = (ctx.now - ctx.remote_held.stat().st_mtime) / 60
    except OSError as exc:
        trust.why = f"the remote-held file cannot be dated ({exc.strerror})"
    else:
        if age_min < -1:
            trust.why = "the remote-held file is dated in the future"
        elif age_min > ctx.max_remote_held_age_min:
            trust.why = f"the remote-held file is {age_min:.0f}m old, over the {ctx.max_remote_held_age_min:g}m bound"
    try:
        trust.tips = load_tips(ctx.remote_held.parent / "tips.tsv")
    except SweepError as exc:
        problems.append(Problem("input-unusable", str(ctx.remote_held.parent / "tips.tsv"), str(exc)))
    if isinstance(held, Held):
        trust.labels, trust.commons, trust.gaps = held.labels, held.commons, held.gaps
    return trust, problems


def proof_ok(status: str) -> bool:
    return status.startswith("PROVEN-") or status == "SUPERSEDED-BOT-BRANCH"


# ----------------------------------------------------------------------------------------------------
# a repository as live git shows it, keyed the way the prove lane's tips.tsv is (§2)
# ----------------------------------------------------------------------------------------------------
PER_WORKTREE_PREFIXES = ("refs/worktree/", "refs/bisect/", "refs/rewritten/")
NOT_A_ROW = ("refs/remotes/", "refs/stash")  # the prove lane's evidence / the stash logic, never tip rows


@dataclasses.dataclass
class Worktree:
    path: str  # realpath of the worktree; for a bare repository's main worktree, the bare directory
    names: list[str]  # every spelling accepted as the `@<worktree>` suffix of a key
    admin: str  # the git dir holding this worktree's HEAD and per-worktree refs
    main: bool = False
    detached: bool = False
    head: str = ""


def is_local_url(url: str) -> bool:
    """§5: does a remote URL (after insteadOf) name this machine? A filesystem path, file://, or a loopback host
    (127.0.0.0/8 in any spelling inet_aton reads, ::1, localhost) is not a remote that survives erasing the Mac."""
    url = url.strip()
    if not url or url.startswith(("/", ".", "~", "file:")):
        return True
    if "://" in url:
        host = url.split("://", 1)[1].split("/", 1)[0].rsplit("@", 1)[-1]
        host = host[1 : host.index("]")] if host.startswith("[") and "]" in host else host.rsplit(":", 1)[0]
    elif ":" in url.split("/", 1)[0]:
        host = url.split(":", 1)[0].rsplit("@", 1)[-1]  # scp-style host:path
    else:
        return True  # a bare relative path
    host = host.strip().rstrip(".").lower()
    if host in ("", "localhost", "ip6-localhost") or host.endswith(".localhost"):
        return True
    try:  # inet_aton reads the shorthand spellings (127.1, 0x7f.0.0.1, 0177.0.0.1, 2130706433) a lookup would resolve
        addr = ipaddress.ip_address(host if ":" in host else socket.inet_ntoa(socket.inet_aton(host)))
    except (OSError, ValueError):
        return False
    mapped = getattr(addr, "ipv4_mapped", None)
    return (mapped or addr).is_loopback or addr.is_unspecified


class RepoState:
    """One repository (git common dir) as live git shows it: every worktree, every ref, and the facts §6 turns into a
    raw git-dir copy. Reads that decide a verdict raise GitReadError; nothing is guessed."""

    def __init__(self, common: str):
        self.common = common
        self.worktrees: list[Worktree] = []
        self.refs: dict[str, str] = {}
        self.per_worktree: list[tuple[str, str, Worktree]] = []
        self.bare = False
        self._memo: dict[str, object] = {}

    def keyed_refs(self) -> list[tuple[list[str], str]]:
        """(acceptable tips.tsv keys, tip) for every row the proof must hold (§2): full refnames outside refs/remotes
        and refs/stash, `HEAD@<worktree>` for each detached worktree, `<refname>@<worktree>` for per-worktree refs."""
        out: list[tuple[list[str], str]] = [([name], sha) for name, sha in sorted(self.refs.items())]
        out += [([f"HEAD@{n}" for n in wt.names], wt.head) for wt in self.worktrees if wt.detached]
        out += [([f"{ref}@{n}" for n in wt.names], sha) for ref, sha, wt in self.per_worktree]
        return out

    def _git(self, args: list[str], what: str, admin: str = "") -> bytes:
        return must(run_git(args, gitdir=admin or self.common), what).stdout

    def reflog_only(self) -> list[str]:
        """§6.1: commits only a reflog reaches, in any worktree (`rev-list --reflog --not --all`, per worktree)."""
        if "reflog" not in self._memo:
            found: dict[str, None] = {}
            for wt in self.worktrees:
                out = self._git(["rev-list", "--reflog", "--not", "--all"], "rev-list --reflog", wt.admin)
                found.update(dict.fromkeys(out.decode("ascii", "replace").split()))
            self._memo["reflog"] = list(found)
        return self._memo["reflog"]  # type: ignore[return-value]

    def files_under(self, rel: str) -> list[str]:
        """Regular files under <common>/<rel> (§6.3), as paths relative to the git dir; [] when there is no such dir."""
        if (key := f"files:{rel}") not in self._memo:
            found: list[str] = []
            for current, _dirs, names in os.walk(os.path.join(self.common, rel)):
                found += [os.path.relpath(os.path.join(current, n), self.common) for n in names]
            self._memo[key] = sorted(found)
        return self._memo[key]  # type: ignore[return-value]

    def has_modules(self) -> bool:
        """§6.4: <common>/modules/ holds any entry (submodule git dirs)."""
        try:
            return bool(os.listdir(os.path.join(self.common, "modules")))
        except FileNotFoundError:
            return False
        except OSError as exc:
            raise GitReadError(f"cannot list {self.common}/modules: {exc.strerror}") from exc

    def lfs_dir(self) -> str:
        """Where git-lfs keeps its store: `lfs.storage` (a leading ~ expanded, a relative path relative to the git dir),
        else <common>/lfs. A realpath."""
        if "lfs-dir" not in self._memo:
            proc = run_git(["config", "--get", "lfs.storage"], gitdir=self.common)
            value = "" if proc.returncode == 1 else must(proc, "config lfs.storage").stdout.decode("utf-8", "surrogateescape").strip()
            value = os.path.expanduser(value) if value else os.path.join(self.common, "lfs")
            self._memo["lfs-dir"] = os.path.realpath(value if os.path.isabs(value) else os.path.join(self.common, value))
        return self._memo["lfs-dir"]  # type: ignore[return-value]

    def lfs_storage(self) -> str:
        """§6 (P9): git-lfs storage kept OUTSIDE the git dir (lfs.storage), as a realpath; '' when it is not."""
        target = self.lfs_dir()
        return "" if target == self.common or target.startswith(self.common + os.sep) else target

    def lfs_objects(self) -> list[str]:
        """The git-lfs object files inside the git dir (§6.3), relative to it. A store outside it has its own tar."""
        target = self.lfs_dir()
        if self.lfs_storage():
            return []
        return self.files_under(os.path.join(os.path.relpath(target, self.common), "objects"))

    def gitdir_reasons(self) -> list[str]:
        """§6: why a raw git-dir copy (gitdir-tar) is required for this repository, from live git alone."""
        why: list[str] = []
        if self.reflog_only():
            why.append("reflog-only commits")
        if self.per_worktree:
            why.append("per-worktree refs")
        if self.lfs_objects():
            why.append("git-lfs objects")
        if self.files_under("annex/objects"):
            why.append("git-annex objects")
        if self.has_modules():
            why.append("submodule git dirs")
        return why

    def large_file_stores(self) -> list[str]:
        """Content no ref carries and no remote listing proves held: git-lfs, git-annex, a relocated lfs.storage."""
        stores = []
        if self.lfs_objects():
            stores.append("git-lfs objects")
        if self.files_under("annex/objects"):
            stores.append("git-annex objects")
        if self.lfs_storage():
            stores.append("an lfs.storage directory outside the git dir")
        return stores

    def offsite_remote(self) -> bool:
        """§5: is any remote's push URL (after insteadOf) somewhere other than this Mac?"""
        names = must(run_git(["remote"], gitdir=self.common), "remote").stdout.decode("utf-8", "replace").split()
        for name in names:
            proc = run_git(["remote", "get-url", "--push", name], gitdir=self.common)
            if proc.returncode == 0 and not is_local_url(proc.stdout.decode("utf-8", "surrogateescape")):
                return True
        return False


def repo_state(ctx: Ctx, anchor: str, common: str, main_checkout: bool = False) -> RepoState:
    """The RepoState of the repository `anchor` belongs to, built once per run. `main_checkout`: the anchor is the
    repository's own checkout, which is then an accepted spelling of the main worktree (a separate-git-dir checkout is
    listed by git under its git dir)."""
    cached = ctx.repo_cache.get(common)
    state = cached if isinstance(cached, RepoState) else None
    if state is None:
        state = RepoState(common)
        listing = must(run_git(["worktree", "list", "--porcelain"], cwd=anchor), "worktree list")
        first = listing.stdout.decode("utf-8", "surrogateescape").split("\n\n", 1)[0].splitlines()
        shown = next((ln[len("worktree ") :] for ln in first if ln.startswith("worktree ")), "")
        if not shown:
            raise GitReadError("worktree list names no main worktree")
        state.bare = "bare" in first
        state.worktrees.append(Worktree(os.path.realpath(shown), [os.path.realpath(shown)], common, main=True))
        admin_root = os.path.join(common, "worktrees")
        try:
            ids = sorted(os.listdir(admin_root))
        except FileNotFoundError:
            ids = []
        except OSError as exc:
            raise GitReadError(f"cannot list {admin_root}: {exc.strerror}") from exc
        for ident in ids:
            admin = os.path.join(admin_root, ident)
            try:
                with open(os.path.join(admin, "gitdir"), encoding="utf-8", errors="surrogateescape") as handle:
                    where = os.path.realpath(os.path.dirname(handle.read().strip()))
            except OSError as exc:
                raise GitReadError(f"cannot read {admin}/gitdir: {exc.strerror}") from exc
            state.worktrees.append(Worktree(where, [where], admin))
        for wt in state.worktrees:
            sym = run_git(["symbolic-ref", "-q", "HEAD"], gitdir=wt.admin)
            if sym.returncode not in (0, 1):
                must(sym, "symbolic-ref HEAD")
            wt.detached = sym.returncode == 1
            probe = run_git(["rev-parse", "-q", "--verify", "HEAD"], gitdir=wt.admin)
            if probe.returncode not in (0, 1):
                must(probe, "rev-parse HEAD")
            wt.head = probe.stdout.decode().strip() if probe.returncode == 0 else ""
            if wt.detached and not wt.head:
                raise GitReadError(f"the detached HEAD of {tilde(wt.path)} does not resolve")
            out = must(
                run_git(
                    ["for-each-ref", "--format=%(refname)%09%(objectname)", "refs/worktree", "refs/bisect", "refs/rewritten"],
                    gitdir=wt.admin,
                ),
                "for-each-ref (per-worktree refs)",
            ).stdout
            for line in out.decode("utf-8", "surrogateescape").splitlines():
                ref, _, sha = line.partition("\t")
                state.per_worktree.append((ref, sha, wt))
        out = must(
            run_git(["for-each-ref", "--format=%(refname)%09%(objectname)%09%(symref)"], gitdir=common), "for-each-ref"
        ).stdout
        for line in out.decode("utf-8", "surrogateescape").splitlines():
            name, sha, symref = (line.split("\t") + ["", ""])[:3]
            if name and not symref and not name.startswith((*NOT_A_ROW, *PER_WORKTREE_PREFIXES)):
                state.refs[name] = sha
        ctx.repo_cache[common] = state
    if main_checkout and os.path.realpath(anchor) not in state.worktrees[0].names:
        state.worktrees[0].names.append(os.path.realpath(anchor))
    return state


def proof_unbound(trust: Trust, path: str, state: RepoState) -> str:
    """'' when the PROVEN-ALL verdict of this checkout's repository is bound to live git; otherwise why not (§2, §4, §5).

    Bound means: the proof is recent, made for this common dir, free of documented gaps, covers no content a remote
    listing cannot see (large-file stores), and holds every live ref tip, detached worktree HEAD and per-worktree ref of
    the repository, in every worktree, as a proven tip under the exact keys of §2."""
    if trust.why:
        return trust.why
    if trust.tips is None:
        return "there is no tips.tsv beside the remote-held file, so the verdict is not bound to any ref tip"
    real = os.path.realpath(path)
    label = trust.labels.get(real)
    if label is None:
        return "the remote-held row for this checkout names no repository, so tips.tsv cannot be joined to it"
    if trust.commons.get(real) != state.common:
        return f"the proof was made for {tilde(trust.commons.get(real, ''))}, but git says this checkout belongs to {tilde(state.common)}"
    if gaps := trust.gaps.get(real):
        return "the proof has documented gaps: " + ", ".join(sorted(gaps))
    if stores := state.large_file_stores():
        return f"the repository holds {' and '.join(stores)}, which no remote listing proves held"
    # work the ref keys cannot see: a commit made after the proof on a branch that was then deleted lives only in a
    # reflog, and a submodule-only commit (after `submodule deinit`) only under modules/. §6 answers both with a raw copy
    if hidden := [what for what, found in (("reflog-only commits", state.reflog_only()), ("submodule git dirs", state.has_modules())) if found]:
        return f"the repository holds {' and '.join(hidden)} that no ref proof covers"
    tips = trust.tips.get(label)
    if tips is None:
        return f"tips.tsv has no entry for this repository ({tilde(label)})"
    for keys, sha in state.keyed_refs():
        known = next((tips[k] for k in keys if k in tips), None)
        shown = f"the detached HEAD {keys[0]}" if keys[0].startswith("HEAD@") else keys[0]
        if known is None:
            return f"{shown} is not in the proof"
        if known[0] != sha:
            return f"{shown} moved since the proof ({known[0][:10]} -> {sha[:10]})"
        if not proof_ok(known[1]):
            return f"{shown} is {known[1]} in the proof"
    if not state.offsite_remote():
        return "no remote of this repository resolves to anywhere but this Mac (a path, file:// or loopback URL is not a remote)"
    return ""


@dataclasses.dataclass
class Live:
    """The sweep rows with every present checkout's columns recomputed from git, and what that turned up."""

    rows: list[dict[str, str]]
    held: dict[str, set[str]] | None
    problems: list[Problem] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)
    extra: dict[str, list[str]] = dataclasses.field(default_factory=dict)  # path -> reasons only live git can add
    commons: dict[str, str] = dataclasses.field(default_factory=dict)  # path -> git common dir (realpath)


LIVE_WORKERS = 4  # git reads only, a few at a time: the Mac is memory-constrained


def raw_blob_ids(path: str, names: list[bytes]) -> dict[bytes, str]:
    """What the working-tree bytes of each file would be stored as with NO filter applied (`hash-object --no-filters`)."""
    clean = [n for n in names if b"\n" not in n]
    ids: dict[bytes, str] = {}
    if clean:
        proc = must(
            run_git(["hash-object", "--no-filters", "--stdin-paths"], cwd=path, data=b"\n".join(clean) + b"\n"),
            "hash-object --no-filters",
        )
        out = proc.stdout.decode("ascii", "replace").split()
        if len(out) != len(clean):
            raise GitReadError(f"hash-object --no-filters answered {len(out)} ids for {len(clean)} files")
        ids.update(zip(clean, out, strict=True))
    for name in (n for n in names if b"\n" in n):
        ids[name] = must(run_git(["hash-object", "--no-filters", "--", name], cwd=path), "hash-object").stdout.decode().strip()
    return ids


def filtered_files(path: str) -> tuple[dict[bytes, os.stat_result], dict[bytes, str]]:
    """(the tracked regular files that exist in the working tree and carry a `filter` attribute, with their lstat; the blob
    id git stores for every tracked path). `git ls-files -z | git check-attr --stdin -z filter`, value neither
    `unspecified` nor `unset`: this includes filter=lfs."""
    staged = must(run_git(["ls-files", "--stage", "-z"], cwd=path), "ls-files --stage").stdout.split(b"\0")
    stored: dict[bytes, str] = {}
    for entry in staged:
        meta, _, name = entry.partition(b"\t")
        fields = meta.split()
        if name and len(fields) == 3 and fields[2] == b"0" and fields[0] != b"160000":
            stored[name] = fields[1].decode()
    if not stored:
        return {}, stored
    attrs = must(
        run_git(["check-attr", "--stdin", "-z", "filter"], cwd=path, data=b"\0".join(stored) + b"\0"), "check-attr filter"
    ).stdout.split(b"\0")
    filtered = [attrs[i] for i in range(0, len(attrs) - 2, 3) if attrs[i + 2] not in (b"unspecified", b"unset")]
    root, present = os.fsencode(path), {}
    for name in filtered:
        try:
            info = os.lstat(os.path.join(root, name))
        except OSError:
            continue  # absent from the working tree (a sparse checkout, or deleted): there are no bytes to lose
        if stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode):  # the producer's tar holds links too
            present[name] = info
    return present, stored


def unstored_of(
    path: str, present: dict[bytes, os.stat_result], stored: dict[bytes, str]
) -> dict[bytes, os.stat_result]:
    """The filtered regular files whose working-tree bytes are not what git stores (hashed with NO filter applied; a
    symlink stores its target, which no filter touches)."""
    regular = {name: info for name, info in present.items() if stat.S_ISREG(info.st_mode)}
    raw = raw_blob_ids(path, list(regular)) if regular else {}
    return {name: info for name, info in regular.items() if raw[name] != stored[name]}


def unstored_content(path: str) -> dict[bytes, os.stat_result]:
    """§7 (FP-UNSTORED-CONTENT): a clean filter (nbstripout and friends) or git-lfs keeps working-tree bytes out of every
    blob, so status, diff, bundles and the remote all agree while the Mac holds the only copy."""
    present, stored = filtered_files(path)
    return unstored_of(path, present, stored)


def probe_row(row: dict[str, str]) -> tuple[str, tuple[dict[str, str], int, str] | GitReadError | None]:
    """The per-row git work of derive_live, safe to run on a worker thread: (path state, live_row result or error)."""
    state = path_state(row["path"])
    if state != "present":
        return state, None
    try:
        return state, live_row(row["path"])
    except GitReadError as exc:
        return state, exc


def derive_live(ctx: Ctx, rows: list[dict[str, str]], held: dict[str, set[str]] | None) -> Live:
    """F1 F2 F6 H3: recompute every present row's exposure from live git, bind PROVEN-ALL to ref tips, find the
    checkouts the sweep never listed. Rows whose path is gone keep the sweep's record for the recovery/waiver logic."""
    live = Live(rows=[], held=dict(held) if held is not None else None)
    live.problems += universe_problems(ctx, rows)
    trust, trust_problems = proof_trust(ctx, held)
    live.problems += trust_problems
    unbound: list[str] = []
    with ThreadPoolExecutor(max_workers=LIVE_WORKERS) as pool:
        probes = list(pool.map(probe_row, rows))
    for row, (state, fresh) in zip(rows, probes, strict=True):
        path = row["path"]
        if state != "present":
            live.rows.append(row)
            if state == "unknown":
                live.problems.append(
                    Problem("exposure-unreadable", path, "cannot tell whether this checkout still exists (stat failed)")
                )
            real = os.path.realpath(path)
            if live.held is not None and live.held.get(real) == {"PROVEN-ALL"}:
                # A14: a proof is about the refs a checkout holds now; one that is gone has none to bind. It may have
                # been moved somewhere no scan reaches, with commits made since, so only a recovery copy or an
                # owner-signed waiver (kind remote-held) settles it, whatever the old record says
                live.held[real] = {"PROVEN-ALL-UNBOUND"}
                unbound.append(f"{tilde(path)}: the checkout is gone, so no tip of it can be bound to the proof")
            continue
        try:
            if isinstance(fresh, GitReadError):
                raise fresh
            if fresh is None:
                live.rows.append(row)
                if not reasons_for(row):
                    live.problems.append(
                        Problem(
                            "exposure-drift",
                            path,
                            "git can no longer resolve this checkout, which the sweep recorded clean",
                        )
                    )
                continue
            cols, hidden, common = fresh
            now = {**row, **cols}
            live.commons[path] = common
            if hidden:
                live.problems.append(
                    Problem(
                        "hidden-edit",
                        path,
                        f"{hidden} skip-worktree/assume-unchanged file(s) differ from the index; git status, git diff and "
                        "the preserved patch cannot see them",
                    )
                )
            grew = sorted(set(reasons_for(now)) - set(reasons_for(row)))
            if cols["kind"] != row["kind"] or grew:
                what = f"kind {row['kind']} -> {cols['kind']}" if cols["kind"] != row["kind"] else ""
                live.problems.append(
                    Problem(
                        "exposure-drift",
                        path,
                        "live git disagrees with the sweep: "
                        + "; ".join(x for x in (what, f"new exposure {grew}" if grew else "") if x),
                    )
                )
            live.rows.append(now)
            real = os.path.realpath(path)
            if live.held is not None and live.held.get(real) == {"PROVEN-ALL"}:
                # FP-SAFE-ROW-REFS: bound for EVERY present checkout, whatever exposure the columns show, because the
                # columns see branches only and the proof is believed only for what it holds tip by tip
                why = proof_unbound(trust, path, repo_state(ctx, path, common, cols["kind"] == "repo"))
                if why:
                    live.held[real] = {"PROVEN-ALL-UNBOUND"}
                    unbound.append(f"{tilde(path)}: {why}")
            if cols["kind"] != "bare" and unstored_content(path):
                live.extra[path] = [UNSTORED]  # §7: only this Mac holds those bytes, whatever the proof says
        except GitReadError as exc:
            live.rows.append(row)
            live.problems.append(Problem("git-error", path, str(exc)))
    live.problems += unowned_common_problems(live)
    if unbound:
        live.notes.append(
            f"{len(unbound)} PROVEN-ALL verdict(s) not trusted and treated as unproven, e.g. {unbound[0]}"
        )
    return live


def unowned_common_problems(live: Live) -> list[Problem]:
    """FP-WORKTREE-OF-UNSWEPT-COMMON: a swept worktree whose repository no swept repo/bare row owns has its refs, stash
    and remotes judged nowhere. The repository joins the universe the sweep lacks."""
    owners = {live.commons[r["path"]] for r in live.rows if r["kind"] in ("repo", "bare") and r["path"] in live.commons}
    orphaned = sorted(
        {c for r in live.rows if r["kind"] == "worktree" and (c := live.commons.get(r["path"])) and c not in owners}
    )
    return [
        Problem("universe-miss", common, "the repository behind a swept worktree is not itself in the sweep")
        for common in orphaned
    ]


DISPOSAL_COLS = ("path", "reason", "signer", "evidence_path", "evidence_sha256")


def vet_disposals(ctx: Ctx, rows: list[dict[str, str]], plan: Plan) -> tuple[list[Waiver], list[Problem]]:
    """F3: a row under a disposable path marker is still exposure. It leaves the plan only through an owner-signed
    record: its path, a reason, a signer and an evidence FILE whose sha256 is re-verified here. Honoured records
    remove the row from plan.needs and are reported as waivers; anything else is a disposal-invalid problem."""
    if ctx.disposals is None:
        return [], []
    try:
        text = ctx.disposals.read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        return [], [Problem("disposal-invalid", str(ctx.disposals), f"cannot read the disposals file: {exc.strerror}")]
    lines = [ln for ln in text.split("\n") if ln.strip()]
    header = [c.strip().lower() for c in lines[0].split("\t")] if lines else []
    if any(col not in header for col in DISPOSAL_COLS):
        return [], [
            Problem("disposal-invalid", str(ctx.disposals), f"header must carry the columns {list(DISPOSAL_COLS)}")
        ]
    try:
        mtime = ctx.disposals.stat().st_mtime
    except OSError as exc:
        return [], [Problem("disposal-invalid", str(ctx.disposals), f"cannot read the disposals file: {exc.strerror}")]
    if mtime > ctx.now + FUTURE_SKEW_SEC:
        return [], [Problem("disposal-invalid", str(ctx.disposals), "the disposals file is dated in the future")]
    col = {name: header.index(name) for name in (*DISPOSAL_COLS, "signed_at") if name in header}
    signers, signers_error = load_signers(ctx.waiver_signers)
    swept = {r["path"] for r in rows}
    marked = {p for p in swept if has_disposable_marker(p)}
    needing = {n.row["path"]: n for n in plan.needs if n.marker}
    honoured: dict[str, Waiver] = {}
    problems: list[Problem] = []
    seen: set[str] = set()
    for lineno, line in enumerate(lines[1:], start=2):
        parts = line.split("\t") + [""] * len(header)
        path, reason, signer, evidence, digest = (parts[col[name]].strip() for name in DISPOSAL_COLS)
        signed_at = parts[col["signed_at"]].strip() if "signed_at" in col else ""
        subject = path or f"{ctx.disposals}:{lineno}"
        why = ""
        resolved = evidence
        if not path:
            why = "record names no path"
        elif path not in swept:
            continue  # a record for a checkout this sweep does not list weakens nothing
        elif path in seen:
            why = "more than one record for this path"
        elif path not in marked:
            why = "not a disposable-marker row of the sweep; only those can be disposed"
        elif not reason or not signer:
            why = "record needs a reason and a signer"
        elif signers_error:  # D1: a disposal waives unpreserved work exactly as a waiver does, so it is signed alike
            why = signers_error
        elif signer not in signers:
            why = f"signer {signer!r} is not on the allow-list"
        elif signed_at and (parse_attest_date(signed_at) is None or is_future(signed_at, ctx.now)):
            why = f"signed_at {signed_at!r} is not an ISO date in the past"
        elif not evidence:
            why = "evidence is not a regular file: (none)"
        else:
            resolved, why = evidence_problem(ctx, evidence, digest, path, ctx.disposals.parent)
        seen.add(path)
        if why:
            problems.append(Problem("disposal-invalid", subject, why))
        elif path in needing:
            need = needing[path]
            exposure = exposure_of(need.row, need.reasons)
            honoured[path] = Waiver(path, f"disposal: {reason}", resolved, signer, "disposal", exposure, signed_at)
    plan.needs = [n for n in plan.needs if n.row["path"] not in honoured]
    return list(honoured.values()), problems


def has_disposable_marker(path: str) -> bool:
    """D1: does the path carry a disposable marker as whole path components? '/custody-staging/' needs that directory
    above the checkout; '/pytest-fixtures' is that exact name, so 'pytest-fixtures-formatted' is not a marker."""
    parts = [p for p in path.split("/") if p]
    for marker in DISPOSABLE_MARKERS:
        want = [p for p in marker.split("/") if p]
        span = len(want)
        limit = len(parts) - (1 if marker.endswith("/") else 0)  # a trailing slash: something must sit inside it
        if any(parts[i : i + span] == want for i in range(max(limit - span + 1, 0))):
            return True
    return False


# FP-IGNORED-NAME-EXEMPT: no directory is exempt for what it is called. A build/, coverage/ or .cache/ directory is where
# a local database or a result set sits as often as anything regenerable. What a toolchain really regenerates are its
# dependency stores and byte-code caches, and only while the manifest that rebuilds them is tracked beside them.
JS_MANIFESTS = ("package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb")
PY_MANIFESTS = ("requirements*.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "Pipfile.lock", "poetry.lock")
DEPENDENCY_STORES: dict[str, tuple[str, ...]] = {
    "node_modules": JS_MANIFESTS,
    **dict.fromkeys((".venv", "venv", "site-packages", ".tox", ".nox", "*.egg-info"), (*PY_MANIFESTS, "uv.lock")),
    **dict.fromkeys(("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"), ("*.py",)),
}
REGENERABLE_FILES = ("*.pyc", "*.pyo", ".DS_Store")  # byte-code and Finder metadata: nothing in them is anyone's work


def regenerable(rel: str, tracked_names: dict[str, set[str]]) -> bool:
    """Is this ignored path a dependency store (or a file of one) that a tracked manifest beside it rebuilds?"""
    parts = rel.split("/")
    if any(fnmatch.fnmatchcase(parts[-1], p) for p in REGENERABLE_FILES):
        return True
    for index, part in enumerate(parts):
        for pattern, manifests in DEPENDENCY_STORES.items():
            if fnmatch.fnmatchcase(part, pattern):
                beside = tracked_names.get("/".join(parts[:index]), set())
                return any(fnmatch.fnmatchcase(name, m) for name in beside for m in manifests)
    return False


def ignored_payload(path: str) -> list[str]:
    """Ignored paths of one checkout that no tracked manifest regenerates (a collapsed directory is one)."""
    proc = must(
        run_git(["ls-files", "-o", "-i", "--exclude-standard", "--directory", "-z"], cwd=path), "ls-files -o -i"
    )
    ignored = [raw.decode("utf-8", "replace").rstrip("/") for raw in proc.stdout.split(b"\0") if raw]
    tracked_names: dict[str, set[str]] = collections.defaultdict(set)
    if ignored:
        listing = must(run_git(["ls-files", "-z"], cwd=path), "ls-files").stdout.split(b"\0")
        for raw in listing:
            directory, _, name = raw.decode("utf-8", "replace").rpartition("/")
            tracked_names[directory].add(name)
    return sorted(rel for rel in ignored if rel and not regenerable(rel, tracked_names))


def payload_digest(items: list[str]) -> str:
    """The sha256 of an ignored-path list as `printf '%s\\n' <sorted paths> | shasum -a 256` computes it (H-IGNORED-ATTESTATION)."""
    return hashlib.sha256("".join(f"{rel}\n" for rel in sorted(items)).encode("utf-8", "surrogateescape")).hexdigest()


def check_ignored_payload(ctx: Ctx) -> Result:
    """F6: git ignores local databases, .env-style state and build output alike, and no run copies ignored files.
    Whatever is not obviously regenerable needs the owner's word, so it is UNPROVEN until the owner lists the checkout."""
    cid = "ignored-payload"
    try:
        rows = load_sweep(ctx.sweep)
    except SweepError as exc:
        return Result(cid, FAIL, str(exc))
    found: dict[str, list[str]] = {}
    problems: list[Problem] = []
    scanned = 0
    for row in rows:
        path = row["path"]
        if path_state(path) != "present" or resolve_common(path) is None or is_bare_repo(path):
            continue  # gone: the recovery logic owns it; unresolvable: its orphan-tree-tar copies every file; bare: no work tree
        scanned += 1
        try:
            if items := ignored_payload(path):
                found[path] = items
        except GitReadError as exc:
            problems.append(Problem("git-error", path, str(exc)))
    if problems:
        return Result(cid, FAIL, f"{len(problems)} checkout(s) could not be scanned: {problems[0]}", problems)
    if not found:
        return Result(
            cid, PASS, f"{scanned} present checkout(s): no ignored file outside regenerable build/cache directories"
        )
    attested, refused = attested_payloads(ctx, found)
    open_ = sorted(set(found) - attested)
    total = sum(len(v) for v in found.values())
    if not open_:
        return Result(
            cid, PASS, f"owner attestation covers all {len(found)} checkout(s) holding {total} ignored path(s)"
        )
    example = f"{tilde(open_[0])}: {found[open_[0]][0]}"
    why = f" ({len(refused)} attestation(s) refused, e.g. {next(iter(refused.values()))})" if refused else ""
    return Result(
        cid,
        UNPROVEN,
        f"{len(open_)} of {len(found)} checkout(s) hold git-ignored files no preserve run copies ({total} paths), e.g. "
        f"{example}; the owner must list each in --ignored-payload-attestation as "
        f"'<path><TAB><signer><TAB><ISO date><TAB><sha256 of its sorted ignored-path list>'{why}",
        extra=[f"{tilde(p)} sha256={payload_digest(found[p])}: {', '.join(found[p][:5])}" for p in open_],
    )


def attested_payloads(ctx: Ctx, found: dict[str, list[str]]) -> tuple[set[str], dict[str, str]]:
    """H-IGNORED-ATTESTATION: which checkouts the owner's attestation really covers, and why the others were refused.
    A line covers a checkout only with a signer on --waiver-signers, an ISO date that is not in the future and not
    older than the newest of the files it covers, and the sha256 of the checkout's CURRENT ignored-path list, so a
    payload added later reopens the check."""
    attested: set[str] = set()
    refused: dict[str, str] = {}
    if ctx.ignored_payload_attestation is None or not ctx.ignored_payload_attestation.is_file():
        return attested, refused
    signers, signers_error = load_signers(ctx.waiver_signers)
    text = ctx.ignored_payload_attestation.read_bytes().decode("utf-8", "replace")
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if line.startswith("#") or len(parts) < 3 or parts[0] not in found:
            continue
        path, signer, when = parts[:3]
        window = attest_window(when)
        newest = 0.0
        for rel in found[path]:
            with contextlib.suppress(OSError):  # a path that vanished since the scan changes nothing about the date test
                newest = max(newest, os.lstat(os.path.join(path, rel)).st_mtime)
        if not signer:
            why = "no signer"
        elif signers_error:
            why = signers_error
        elif signer not in signers:
            why = f"signer {signer!r} is not on the allow-list"
        elif window is None:
            why = f"{when!r} is not an ISO date"
        elif is_future(when, ctx.now):
            why = f"dated {when} in the future"
        elif window[0] < newest:  # a bare date counts from 00:00:00 UTC: it cannot vouch for files made later that day
            why = f"dated {when}, before the newest ignored file changed (a bare date counts from 00:00:00 UTC; give a timestamp)"
        elif len(parts) < 4 or parts[3].lower() != payload_digest(found[path]):
            why = "its sha256 does not match the current ignored-path list (or is missing): the payload changed or was never listed"
        else:
            attested.add(path)
            continue
        refused[path] = f"{tilde(path)}: {why}"
    return attested, refused


# ----------------------------------------------------------------------------------------------------
# live repository state (every call read-only, same flags as the producer)
# ----------------------------------------------------------------------------------------------------
def is_bare_repo(path: str) -> bool:
    """Does git call the repository at this path bare? It has no work tree: nothing is ignored, untracked, filtered or
    dirty in it, and the commands that look for those refuse to run there."""
    proc = run_git(["rev-parse", "--is-bare-repository"], cwd=path)
    return proc.returncode == 0 and proc.stdout.decode().strip() == "true"


def resolve_common(path: str) -> str | None:
    proc = run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=path)
    out = proc.stdout.decode("utf-8", "surrogateescape").strip()
    if proc.returncode != 0 or not out:
        return None
    return os.path.realpath(out)


def current_refs(common: str) -> dict[str, str]:
    """Every ref the repository holds that carries data of its own (F5): branches, tags, stash, notes, refs/limen/...

    Remote-tracking refs (refs/remotes/) are copies of what a remote already holds and move on every fetch, so they
    are not compared; symbolic refs add no data. A failing read raises GitReadError rather than reading as no refs.
    """
    proc = must(
        run_git(["for-each-ref", "--format=%(objectname)%09%(symref)%09%(refname)"], gitdir=common), "for-each-ref"
    )
    refs: dict[str, str] = {}
    for line in proc.stdout.decode("utf-8", "surrogateescape").splitlines():
        sha, symref, name = (line.split("\t") + ["", ""])[:3]
        if name and not symref and not name.startswith("refs/remotes/"):
            refs[name] = sha
    return refs


def stash_shas(common: str) -> list[str]:
    """Every stash entry (the whole reflog of refs/stash, newest first); [] only when refs/stash does not exist.

    Any other git failure raises GitReadError (H3: a read error is never "no stashes")."""
    probe = run_git(["rev-parse", "-q", "--verify", "refs/stash"], gitdir=common)
    if probe.returncode == 1 and not probe.stdout.strip():
        return []  # `rev-parse -q --verify` exits 1, silently, for a ref that does not exist
    must(probe, "rev-parse refs/stash")
    proc = must(run_git(["log", "-g", "--format=%H", "refs/stash"], gitdir=common), "stash reflog")
    return [ln.decode().strip() for ln in proc.stdout.splitlines() if ln.strip()]


def stash_count(common: str) -> int:
    return len(stash_shas(common))


def newest_commit_ts(common: str, head_path: str | None = None) -> int:
    proc = must(
        run_git(
            [
                "for-each-ref",
                "--sort=-committerdate",
                "--count=1",
                "--format=%(committerdate:unix)",
                "refs/heads",
                "refs/stash",
            ],
            gitdir=common,
        ),
        "for-each-ref (newest commit)",
    )
    best = int(proc.stdout.strip()) if proc.stdout.strip().isdigit() else 0
    if head_path:
        probe = run_git(["rev-parse", "-q", "--verify", "HEAD"], cwd=head_path)
        if probe.returncode == 0:  # rc 1 is an unborn HEAD: no commit to date
            head = must(run_git(["log", "-1", "--format=%ct", "HEAD"], cwd=head_path), "log HEAD")
            if head.stdout.strip().isdigit():
                best = max(best, int(head.stdout.strip()))
        elif probe.returncode != 1:
            must(probe, "rev-parse HEAD")
    return best


def filter_untracked(repo: str, names: list[bytes]) -> tuple[dict[bytes, os.stat_result], collections.Counter[str]]:
    """Port of the producer's filter-untracked: what its untracked tar is expected to hold."""
    keep: dict[bytes, os.stat_result] = {}
    stats: collections.Counter[str] = collections.Counter()
    root = os.fsencode(repo)
    for name in names:
        if name.endswith(b"/"):
            stats["nested"] += 1
            continue
        try:
            st = os.lstat(os.path.join(root, name))
        except OSError:
            stats["gone"] += 1
            continue
        if is_cred(name.decode("utf-8", "replace")):
            stats["cred"] += 1
            continue
        if stat.S_ISREG(st.st_mode):
            if st.st_size > MAX_FILE_BYTES:
                stats["big"] += 1
                continue
        elif not stat.S_ISLNK(st.st_mode):
            stats["special"] += 1
            continue
        keep[name] = st
    return keep, stats


def current_untracked(path: str) -> tuple[dict[bytes, os.stat_result], collections.Counter[str], str]:
    proc = run_git(["ls-files", "-o", "--exclude-standard", "-z"], cwd=path)
    if proc.returncode != 0:
        return {}, collections.Counter(), "ls-files -o failed: " + err_tail(proc)
    names = [n for n in proc.stdout.split(b"\0") if n]
    keep, stats = filter_untracked(path, names)
    return keep, stats, ""


def current_patch(path: str) -> tuple[str, int, int, str]:
    """(sha256, bytes, credential paths excluded, error) of the current tracked diff, built like the producer's."""
    names = run_git(["diff", "--name-only", "-z", "--no-ext-diff", "--no-relative", "HEAD"], cwd=path)
    if names.returncode != 0:
        return "", 0, 0, "diff --name-only failed: " + err_tail(names)
    excl = [
        b":(top,exclude,literal)" + n for n in names.stdout.split(b"\0") if n and is_cred(n.decode("utf-8", "replace"))
    ]
    args: list[str | bytes] = [*DIFF_FLAGS, "HEAD"]
    if excl:
        args += ["--", ":(top)", *excl]
    cmd = [os.fsencode(a) for a in [*GIT_BASE, "-C", path, *args]]
    sha, total, rc, tail = stream_digest(cmd)
    if rc != 0:
        return "", 0, len(excl), f"git diff exit {rc}: {tail}"
    return sha, total, len(excl), ""


def dirty_file_mtimes(path: str, untracked: dict[bytes, os.stat_result], unborn: bool = False) -> int:
    newest = max((st.st_mtime_ns // 1_000_000_000 for st in untracked.values()), default=0)
    if unborn:
        return newest  # no HEAD to diff against: the staged paths are dated by check_unborn
    names = must(
        run_git(["diff", "--name-only", "-z", "--no-ext-diff", "--no-relative", "HEAD"], cwd=path), "diff --name-only"
    )
    root = os.fsencode(path)
    for n in names.stdout.split(b"\0"):
        if not n:
            continue
        try:
            newest = max(newest, os.lstat(os.path.join(root, n)).st_mtime_ns // 1_000_000_000)
        except OSError:
            continue
    return newest


def walk_files(path: str) -> list[bytes]:
    """Port of `find . -xdev ( -type f -o -type l )`, names relative to path."""
    root = os.fsencode(path)
    dev = os.lstat(root).st_dev
    found: list[bytes] = []
    for dirpath, dirnames, filenames in os.walk(root):
        keep = []
        for d in dirnames:
            full = os.path.join(dirpath, d)
            try:
                st = os.lstat(full)
            except OSError:
                continue
            if stat.S_ISLNK(st.st_mode):
                found.append(os.path.relpath(full, root))
            elif st.st_dev == dev:
                keep.append(d)
        dirnames[:] = keep
        for f in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, f), root))
    return found


def fmt_name(name: bytes) -> str:
    return name.decode("utf-8", "replace")


def normalize_member(name: str) -> bytes:
    raw = name.encode("utf-8", "surrogateescape")
    while raw.startswith(b"./"):
        raw = raw[2:]
    return raw


def compare_tar(tar_path: str, expected: dict[bytes, os.stat_result], root: str, deep: bool) -> list[str]:
    """Compare a tar against the current file set. Returns human-readable differences (empty = match)."""
    want = {normalize_member(fmt_name(k)): (k, v) for k, v in expected.items()}
    try:
        with tarfile.open(tar_path, "r:", encoding="utf-8", errors="surrogateescape") as tf:
            return tar_differences(tf, want, os.fsencode(root), deep)
    except (OSError, tarfile.TarError) as exc:
        return [f"tar unreadable: {exc}"]


def tar_differences(
    tf: tarfile.TarFile, want: dict[bytes, tuple[bytes, os.stat_result]], rootb: bytes, deep: bool
) -> list[str]:
    notes: list[str] = []
    members: dict[bytes, tarfile.TarInfo] = {}
    dupes = 0
    for m in tf:
        key = normalize_member(m.name)
        dupes += key in members
        members[key] = m
    missing = sorted(set(want) - set(members))
    extra = sorted(set(members) - set(want))
    if dupes:
        notes.append(f"{dupes} duplicate member name(s)")
    if missing:
        notes.append(f"{len(missing)} current file(s) not in the tar, e.g. {fmt_name(missing[0])}")
    if extra:
        notes.append(f"{len(extra)} tar member(s) not in the current file list, e.g. {fmt_name(extra[0])}")
    changed: list[bytes] = []
    for key, (orig, st) in want.items():
        member = members.get(key)
        if member is None:
            continue
        full = os.path.join(rootb, orig)
        if stat.S_ISLNK(st.st_mode):
            try:
                same = member.issym() and member.linkname.encode("utf-8", "surrogateescape") == os.readlink(full)
            except OSError:
                same = False
            if not same:
                changed.append(key)
        elif not member.isreg() or member.size != st.st_size or abs(float(member.mtime) - st.st_mtime_ns / 1e9) >= 1.0:
            changed.append(key)
        elif deep:
            handle = tf.extractfile(member)
            digest = hashlib.sha256()
            while handle is not None:
                block = handle.read(1 << 20)
                if not block:
                    break
                digest.update(block)
            if digest.hexdigest() != sha256_file(full):
                changed.append(key)
    if changed:
        notes.append(f"{len(changed)} file(s) changed since the snapshot, e.g. {fmt_name(changed[0])}")
    return notes


# ----------------------------------------------------------------------------------------------------
# check: sweep-fresh
# ----------------------------------------------------------------------------------------------------
def check_sweep_fresh(ctx: Ctx) -> Result:
    path = ctx.sweep
    if not path.is_file():
        return Result("sweep-fresh", FAIL, f"no sweep file at {tilde(str(path))}; run scripts/mac-exit/git-sweep.sh")
    if not 0 < ctx.max_sweep_age_min <= MAX_SWEEP_AGE_CEILING_MIN:  # H6: the bound itself has a hard ceiling
        return Result(
            "sweep-fresh",
            FAIL,
            f"the {ctx.max_sweep_age_min:g}m age bound is outside (0, {MAX_SWEEP_AGE_CEILING_MIN:g}]; "
            "a bound that can be raised without limit is no bound",
        )
    age_min = (ctx.now - path.stat().st_mtime) / 60
    try:
        rows = load_sweep(path)
    except SweepError as exc:
        return Result("sweep-fresh", FAIL, str(exc))
    problems = []
    if age_min < -1:
        problems.append(f"sweep mtime is {-age_min:.1f}m in the future")
    elif age_min > ctx.max_sweep_age_min:
        problems.append(
            f"age {age_min:.1f}m exceeds the {ctx.max_sweep_age_min:g}m bound (evidence is stale; re-sweep)"
        )
    if not rows:
        problems.append("sweep has 0 entries (a silent find error gives an empty sweep)")
    find_err = path.parent / "find.err"
    if find_err.is_file() and find_err.stat().st_size > 0:
        problems.append(f"{find_err.name} is not empty ({find_err.stat().st_size} bytes): the scan was incomplete")
    if gaps := universe_problems(ctx, rows):  # F2: the sweep must list every checkout a fresh scan finds
        examples = " | ".join(str(p) for p in gaps[:3])
        problems.append(f"{len(gaps)} problem(s) against a fresh scan of the sweep's roots: {examples}")
    if problems:
        return Result("sweep-fresh", FAIL, "; ".join(problems))
    return Result(
        "sweep-fresh", PASS, f"{path.name} age {age_min:.1f}m <= {ctx.max_sweep_age_min:g}m, {len(rows)} entries"
    )


# ----------------------------------------------------------------------------------------------------
# check: git-preserved
# ----------------------------------------------------------------------------------------------------
@dataclasses.dataclass
class BundleInfo:
    usable: bool = False
    heads: dict[str, str] = dataclasses.field(default_factory=dict)
    problems: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    reported: bool = False


class RunView:
    """The newest preserve run: parsed MANIFEST.tsv plus a cache of recomputed artifact hashes."""

    def __init__(self, run: Path, ctx: Ctx | None = None):
        self.run = run
        self.ctx = ctx  # H2: with a ctx, every artifact must live off the Mac's device
        self.items: list[dict[str, str]] = []
        self.by: dict[tuple[str, str], list[dict[str, str]]] = collections.defaultdict(list)
        self.errors: list[str] = []
        self._hashed: dict[str, tuple[str, str] | None] = {}
        self.files_hashed = 0
        self.bytes_hashed = 0
        match = RUN_RE.match(run.name)
        self.start_ts = 0
        if match:
            parsed = datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
            self.start_ts = int(parsed.timestamp())
        self._load()

    def _load(self) -> None:
        manifest = self.run / "MANIFEST.tsv"
        if not manifest.is_file():
            self.errors.append("no MANIFEST.tsv in the run")
            return
        lines = manifest.read_bytes().decode("utf-8", "surrogateescape").split("\n")
        if lines[0].split("\t") != MANIFEST_COLS:
            self.errors.append("MANIFEST.tsv header is not the producer's 9 columns")
            return
        for lineno, line in enumerate(lines[1:], start=2):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) != len(MANIFEST_COLS):
                self.errors.append(f"MANIFEST.tsv line {lineno} has {len(parts)} columns (run cut short?)")
                continue
            item = dict(zip(MANIFEST_COLS, parts, strict=True))
            self.items.append(item)
            self.by[(item["item_kind"], item["slug"])].append(item)

    def complete(self) -> bool:
        kinds = {i["item_kind"] for i in self.items if i["status"] == "ok"}
        return {"skipped-list", "credential-list"} <= kinds

    def one(self, kind: str, slug: str) -> dict[str, str] | None:
        found = self.by.get((kind, slug), [])
        return found[0] if found else None

    def verify_artifact(self, item: dict[str, str]) -> tuple[str, str] | None:
        """Recompute size and sha256 against the manifest. Returns (code, message) on failure, else None."""
        rel = item["file"]
        if not safe_rel(rel):
            return ("artifact-missing", f"{item['item_kind']} item records no usable file ({rel!r})")
        if rel in self._hashed:
            return self._hashed[rel]
        path = self.run / rel
        verdict: tuple[str, str] | None
        if not within_real(self.run, rel):  # H2: a link in the run can lead back onto the Mac
            verdict = ("artifact-symlink", f"{rel} is reached through a symlink, so it is not custody")
        elif not path.is_file():
            verdict = ("artifact-missing", f"{rel} is not in the run")
        elif self.ctx is not None and (why := custody_problem(self.ctx, path)):
            verdict = ("custody-on-mac", f"{rel}: {why}")
        elif str(path.stat().st_size) != item["bytes"]:
            verdict = ("hash-mismatch", f"{rel} is {path.stat().st_size} bytes, manifest says {item['bytes']}")
        else:
            self.files_hashed += 1
            self.bytes_hashed += path.stat().st_size
            verdict = (
                None
                if sha256_file(path) == item["sha256"]
                else ("hash-mismatch", f"{rel} sha256 differs from manifest")
            )
        self._hashed[rel] = verdict
        return verdict


def newest_run(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    runs = sorted(p for p in root.iterdir() if p.is_dir() and RUN_RE.match(p.name))
    return runs[-1] if runs else None


def discover_recovery(preserve_root: Path) -> Path | None:
    """The newest recovered-from-* directory beside the preserve root (rescued copies of vanished repositories)."""
    parent = preserve_root.parent
    if not parent.is_dir():
        return None
    found = sorted(p for p in parent.iterdir() if p.is_dir() and p.name.startswith("recovered-from-"))
    return found[-1] if found else None


def idx_has(data: bytes, sha: str) -> bool:
    """Is `sha` in a pack .idx (version 2)? Binary search on the sorted object-name table."""
    if data[:4] != b"\xfftOc" or struct.unpack(">I", data[4:8])[0] != 2:
        return False
    want = bytes.fromhex(sha)
    width = len(want)
    fanout = struct.unpack(">256I", data[8 : 8 + 1024])
    lo, hi = (fanout[want[0] - 1] if want[0] else 0), fanout[want[0]]
    table = 8 + 1024
    while lo < hi:
        mid = (lo + hi) // 2
        entry = data[table + mid * width : table + (mid + 1) * width]
        if entry == want:
            return True
        if entry < want:
            lo = mid + 1
        else:
            hi = mid
    return False


def inspect_gitdir_tar(
    path: str, base: str, tips: list[str]
) -> tuple[dict[str, str], list[str], tarfile.TarInfo | None, str]:
    """Read a raw git-dir tar without extracting it: (refs, tip shas it lacks, index member, error).

    Refs come from packed-refs and every loose file under refs/ (remote-tracking refs excepted, see current_refs); a
    tip is present when it is a loose object or listed in one of the pack indexes. Reftable repositories are reported
    as unsupported, never as covered.
    """
    sha_re = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    try:
        with tarfile.open(path, "r:", encoding="utf-8", errors="surrogateescape") as tf:
            members = {m.name: m for m in tf}
            if any(n.startswith(f"{base}/reftable/") for n in members):
                return {}, [], None, "raw git dir copy uses the reftable format, which this check cannot read"

            def blob(member: tarfile.TarInfo) -> bytes:
                handle = tf.extractfile(member)
                return handle.read() if handle else b""

            def text(member: tarfile.TarInfo) -> str:
                return blob(member).decode("utf-8", "replace")

            refs: dict[str, str] = {}
            if f"{base}/packed-refs" in members:
                for line in text(members[f"{base}/packed-refs"]).splitlines():
                    sha, _, name = line.partition(" ")
                    if sha_re.match(sha) and name.startswith("refs/") and not name.startswith("refs/remotes/"):
                        refs[name] = sha
            for name, member in members.items():
                rel = name[len(base) + 1 :]
                if member.isreg() and rel.startswith("refs/") and not rel.startswith("refs/remotes/"):
                    value = text(member).strip()
                    if sha_re.match(value):
                        refs[rel] = value
            return refs, tar_missing_objects(tf, members, base, tips), members.get(f"{base}/index"), ""
    except (OSError, tarfile.TarError) as exc:
        return {}, [], None, f"raw git dir copy unreadable: {exc}"


def tar_missing_objects(tf: tarfile.TarFile, members: dict[str, tarfile.TarInfo], base: str, shas: list[str]) -> list[str]:
    """Which of these objects a raw git-dir tar lacks: not a loose object, and in none of its pack indexes."""
    indexes: list[bytes] | None = None
    missing = []
    for sha in shas:
        if f"{base}/objects/{sha[:2]}/{sha[2:]}" in members:
            continue
        if indexes is None:
            indexes = []
            for name, member in members.items():
                if name.startswith(f"{base}/objects/pack/") and name.endswith(".idx"):
                    handle = tf.extractfile(member)
                    indexes.append(handle.read() if handle else b"")
        if not any(idx_has(data, sha) for data in indexes):
            missing.append(sha)
    return missing


def gitdir_tar_problems(tar_path: str, base: str, state: RepoState) -> list[str]:
    """§6: does a raw git-dir copy hold what made it required? Every reflog-only commit's object, every per-worktree ref
    file (with the right tip) and its object, the git-lfs and git-annex object files (by listing, sizes equal) and the
    submodule git dirs under modules/ (by listing). Reads live git for the expectation; returns what is missing."""
    problems: list[str] = []
    try:
        with tarfile.open(tar_path, "r:", encoding="utf-8", errors="surrogateescape") as tf:
            members = {m.name: m for m in tf}
            if any(n.startswith(f"{base}/reftable/") for n in members):
                return ["the raw git dir copy uses the reftable format, which this check cannot read"]
            reflog = state.reflog_only()
            lost = tar_missing_objects(tf, members, base, reflog)
            if lost:
                problems.append(f"{len(lost)} of {len(reflog)} reflog-only commit(s) are not in the copy, e.g. {lost[0][:10]}")
            sha_re = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
            for ref, sha, wt in state.per_worktree:
                where = ref if wt.main else f"worktrees/{os.path.basename(wt.admin)}/{ref}"
                member = members.get(f"{base}/{where}")
                handle = tf.extractfile(member) if member is not None and member.isreg() else None
                value = handle.read().decode("ascii", "replace").strip() if handle else ""
                if not sha_re.match(value) or value != sha:
                    problems.append(f"per-worktree ref {ref} of {tilde(wt.path)} is not in the copy at its live tip")
                elif tar_missing_objects(tf, members, base, [sha]):
                    problems.append(f"the object of per-worktree ref {ref} of {tilde(wt.path)} is not in the copy")
            for rel in (*state.lfs_objects(), *state.files_under("annex/objects")):
                member = members.get(f"{base}/{rel}")
                if member is None or member.size != os.path.getsize(os.path.join(state.common, rel)):
                    problems.append(f"large-file object {rel} is missing from the copy or differs in size")
                    break
            gone = [
                rel
                for rel in state.files_under("modules")
                if not (os.path.basename(rel).startswith("tmp_pack_") or os.path.basename(rel) == "config")
                and f"{base}/{rel}" not in members
            ]
            if gone:
                problems.append(f"{len(gone)} file(s) under modules/ are not in the copy, e.g. {gone[0]}")
    except (OSError, tarfile.TarError) as exc:
        return [f"the raw git dir copy is unreadable: {exc}"]
    return problems


#   ("bundle" | "gitdir" | "lfs-storage", common dir) | ("dirty" | "head" | "orphan" | "filtered", checkout path)
ComponentKey = tuple[str, str]


def is_partial_clone(common: str) -> bool:
    """preserve-git.sh's test: a promisor remote or extensions.partialclone, so blobs may live only on the remote."""
    promisor = run_git(["config", "--get-regexp", r"^remote\..*\.promisor$"], gitdir=common).stdout.decode()
    if any(line.split()[-1:] == ["true"] for line in promisor.splitlines()):
        return True
    return run_git(["config", "--get", "extensions.partialclone"], gitdir=common).returncode == 0


def is_unborn(common: str) -> bool:
    """HEAD names a branch that has no commit yet (`rev-parse --verify HEAD` exits 1)."""
    return run_git(["rev-parse", "-q", "--verify", "HEAD"], gitdir=common).returncode == 1


class GitPreserved:
    """Evaluate one producer run against the live repositories, component by component.

    A need row has up to four independent components (its repository's bundle, its dirty snapshot, its detached
    HEAD, its orphan tree). Each is judged on its own so that complementary runs can cover different components.
    """

    def __init__(self, ctx: Ctx, needs: list[Need], view: RunView, scratch: str):
        self.ctx = ctx
        self.needs = needs
        self.view = view
        self.scratch = scratch
        self.empty = os.path.join(scratch, "empty.git")
        self.components: dict[ComponentKey, list[Problem]] = {}
        self.current: list[Problem] = []
        self.bundles: dict[str, BundleInfo] = {}
        self.gitdir_verdicts: dict[str, str] = {}
        self.stats: collections.Counter[str] = collections.Counter()

    def begin(self, key: ComponentKey) -> None:
        self.current = self.components.setdefault(key, [])

    def add(self, code: str, subject: str, message: str) -> None:
        self.current.append(Problem(code, subject, message))

    @contextlib.contextmanager
    def guarded(self, subject: str) -> Iterator[None]:
        """A git read that fails inside a component is that component's `git-error`, never a silent zero (H3)."""
        try:
            yield
        except GitReadError as exc:
            self.add("git-error", subject, str(exc))

    def slug(self, path: str) -> str:
        return slugify(path, self.ctx.home)

    def stale(self, subject: str, what: str, ts: int) -> None:
        if self.view.start_ts and ts > self.view.start_ts:
            self.add("stale", subject, f"{what} at {iso(ts)} is newer than the run start {iso(self.view.start_ts)}")

    # ---- full bundles, or the raw git-dir copy the producer makes where a bundle cannot work ----------
    def bundle_info(self, common: str) -> BundleInfo:
        if common in self.bundles:
            return self.bundles[common]
        info = self.bundle_only(common)
        if not info.usable:
            # partial clones and bundles the producer reported as failed are covered by a gitdir-tar item instead. A
            # bundle that exists and does NOT verify is a defect, never replaced: the raw copy is in addition (§6)
            bundle_problems, info.problems = info.problems, []
            if self.tar_stands_in(common) and self.view.one("gitdir-tar", self.slug(common)) is not None:
                # a partial clone has no bundle item by design; only a bundle that failed is worth reporting
                bundle_problems = [p for p in bundle_problems if p[0] != "manifest-missing"]
                if self.gitdir_route(common, info):
                    self.bundles[common] = info
                    return info
            info.problems = bundle_problems + info.problems
        self.bundles[common] = info
        return info

    def tar_stands_in(self, common: str) -> bool:
        """May a raw git-dir copy replace the bundle? Only where live git shows a bundle cannot carry the repository: a
        partial clone (no bundle item by design) or an unborn HEAD. Anywhere else the bundle is required whatever
        raw copies exist (§6: the copy is in addition), and a bundle that failed or is wrong is a FAIL, fail closed."""
        item = self.view.one("bundle", self.slug(common))
        return (is_partial_clone(common) or is_unborn(common)) and (item is None or item["status"] == "failed")

    def gitdir_route(self, common: str, info: BundleInfo) -> bool:
        item = self.view.one("gitdir-tar", self.slug(common))
        if item is None:
            return False
        if item["status"] != "ok":
            info.problems.append(("item-status", f"gitdir-tar item is {item['status']}: {item['note'][:120]}"))
            return False
        bad = self.view.verify_artifact(item)
        if bad:
            info.problems.append(bad)
            return False
        current = current_refs(common)
        refs, missing, _index, err = inspect_gitdir_tar(
            str(self.view.run / item["file"]), os.path.basename(common), sorted(set(current.values()))
        )
        if err:
            info.problems.append(("bundle-verify", err))
            return False
        info.heads = refs
        if missing:
            info.problems.append(
                (
                    "tip-missing",
                    f"{len(missing)} current tip commit(s) are not in the raw git dir copy, e.g. {missing[0][:10]}",
                )
            )
            return False
        if self.ctx.deep and (problem := self.gitdir_fsck(str(self.view.run / item["file"]), os.path.basename(common))):
            info.problems.append(("bundle-verify", problem))
            return False
        info.usable = True
        self.stats["gitdir_tars_checked"] += 1
        return True

    def gitdir_fsck(self, tar_path: str, base: str) -> str:
        """H4: extract a raw git-dir copy into scratch and let git check that its objects are readable and connected.
        Returns '' when it is sound, else why not. One verdict per artifact."""
        if tar_path in self.gitdir_verdicts:
            return self.gitdir_verdicts[tar_path]
        need, free = os.path.getsize(tar_path), shutil.disk_usage(self.scratch).free
        if free < 2 * need + SCRATCH_HEADROOM:
            # the internal disk of the Mac being emptied is the usual scratch: never fill it, never skip the check
            verdict = (
                f"no room to extract this {need}-byte raw git dir copy for verification ({free} bytes free in "
                "scratch); give --scratch a volume with space"
            )
            self.gitdir_verdicts[tar_path] = verdict
            return verdict
        dest = tempfile.mkdtemp(prefix="gitdir-", dir=self.scratch)
        try:
            with tarfile.open(tar_path, "r:") as tf:
                kw = {"filter": "data"} if hasattr(tarfile, "data_filter") else {}
                tf.extractall(dest, members=[m for m in tf if m.isreg() or m.isdir()], **kw)  # noqa: S202
            proc = run_git(
                ["fsck", "--connectivity-only", "--no-dangling"], gitdir=os.path.join(dest, base), timeout=1800
            )
            verdict = (
                ""
                if proc.returncode == 0
                else "raw git dir copy failed git fsck --connectivity-only: " + err_tail(proc)
            )
        except (OSError, tarfile.TarError) as exc:
            verdict = f"raw git dir copy could not be extracted for verification: {exc}"
        finally:
            shutil.rmtree(dest, ignore_errors=True)
        self.gitdir_verdicts[tar_path] = verdict
        return verdict

    def bundle_only(self, common: str) -> BundleInfo:
        info = BundleInfo()
        item = self.view.one("bundle", self.slug(common))
        if item is None:
            info.problems.append(("manifest-missing", "no bundle item for this repository in MANIFEST.tsv"))
            return info
        if item["status"] == "empty":
            refs = run_git(["show-ref"], gitdir=common)
            if refs.returncode != 1:  # show-ref exits 1 when there is no ref at all
                must(refs, "show-ref")
            if refs.stdout.strip():
                info.problems.append(("item-status", "bundle recorded empty but the repository has refs now"))
            else:
                info.usable = True
            return info
        if item["status"] != "ok":
            info.problems.append(("item-status", f"bundle item is {item['status']}: {item['note'][:120]}"))
            return info
        bad = self.view.verify_artifact(item)
        if bad:
            info.problems.append(bad)
            return info
        path = str(self.view.run / item["file"])
        # An empty repository: a full bundle must verify there, i.e. its history is self-contained.
        verify = run_git(["bundle", "verify", path], gitdir=self.empty)
        out = verify.stdout.decode("utf-8", "replace")
        if verify.returncode != 0 or "complete history" not in out:
            why = err_tail(verify) if verify.returncode != 0 else "bundle has prerequisites (not self-contained)"
            info.problems.append(("bundle-verify", "git bundle verify in an empty repository failed: " + why))
            return info
        heads = must(run_git(["bundle", "list-heads", path], gitdir=self.empty), "bundle list-heads")
        for line in heads.stdout.decode("utf-8", "surrogateescape").splitlines():
            sha, _, name = line.partition(" ")
            if name:
                info.heads[name] = sha
        if self.ctx.deep:
            problem = pack_check(path, self.empty)
            if problem:
                info.problems.append(("bundle-verify", problem))
                return info
        info.usable = True
        self.stats["bundles_verified"] += 1
        return info

    def check_refs(self, common: str, info: BundleInfo) -> list[tuple[str, str]]:
        """Problems of the bundle against the CURRENT refs of the repository."""
        problems = list(info.problems)
        if not info.usable and not problems:
            problems.append(("bundle-verify", "bundle unusable"))
        if info.usable and info.heads is not None:
            missing = [
                f"{name}@{sha[:10]}"
                for name, sha in sorted(current_refs(common).items())
                if info.heads.get(name) != sha
            ]
            if missing:
                more = f" (+{len(missing) - 3} more)" if len(missing) > 3 else ""
                problems.append(("tip-missing", "bundle lacks the current tip of " + ", ".join(missing[:3]) + more))
            problems += self.stash_problems(common)
        return problems

    def stash_problems(self, common: str) -> list[tuple[str, str]]:
        count = stash_count(common)
        if count <= 1:
            return []
        slug = self.slug(common)
        out: list[tuple[str, str]] = []
        reflog = self.view.one("stash-reflog", slug)
        if reflog is None or reflog["status"] != "ok":
            out.append(("stash-missing", f"{count} stash entries but no usable stash-reflog item"))
        else:
            bad = self.view.verify_artifact(reflog)
            if bad:
                out.append(bad)
        patches = self.view.by.get(("stash-patch", slug), [])
        for index in range(1, count):
            hit = [p for p in patches if f"stash@{{{index}}}" in p["note"]]
            if not hit or hit[0]["status"] != "ok":
                out.append(("stash-missing", f"stash@{{{index}}} has no usable stash-patch"))
                continue
            bad = self.view.verify_artifact(hit[0])
            if bad:
                out.append(bad)
        return out

    # ---- dirty snapshots -----------------------------------------------------------------------
    def check_dirty(self, need: Need) -> None:
        path = need.row["path"]
        slug = self.slug(path)
        patch = self.view.one("tracked-patch", slug)
        tar_item = self.view.one("untracked-tar", slug)
        for label, item in (("tracked-patch", patch), ("untracked-tar", tar_item)):
            if item is None:
                self.add("manifest-missing", path, f"no {label} item in MANIFEST.tsv")
            elif item["status"] not in ("ok", "empty"):
                self.add("item-status", path, f"{label} item is {item['status']}: {item['note'][:120]}")
        unborn = run_git(["rev-parse", "-q", "--verify", "HEAD"], cwd=path).returncode != 0
        staged_newest = 0
        if unborn:
            staged_newest = self.check_unborn(need, patch)
        elif patch is not None and patch["status"] in ("ok", "empty"):
            sha, nbytes, _ncred, perr = current_patch(path)
            if perr:
                self.add("git-error", path, perr)
                return
            if patch["file"] or patch["status"] == "ok":  # H8: an `ok` patch with no file is a gap, not a skip
                bad = self.view.verify_artifact(patch)
                if bad:
                    self.add(bad[0], path, bad[1])
            if patch["status"] == "empty" and nbytes != 0:
                self.add("patch-mismatch", path, f"patch recorded empty but the current tracked diff is {nbytes} bytes")
            elif patch["status"] == "ok" and sha != patch["sha256"]:
                self.add(
                    "patch-mismatch", path, "the current `git diff --binary HEAD` no longer equals the preserved patch"
                )
            self.stats["patches_compared"] += 1
        untracked, stats, uerr = current_untracked(path)
        if uerr:
            self.add("git-error", path, uerr)
            return
        self.stats["credential_files_left_out"] += stats["cred"]
        if stats["big"] or stats["special"]:
            self.add(
                "unsnapshotable",
                path,
                f"{stats['big']} file(s) over 2 GiB and {stats['special']} special file(s) cannot be in the snapshot",
            )
        if tar_item is not None and tar_item["status"] == "empty" and untracked:
            self.add("untracked-mismatch", path, f"tar recorded empty but {len(untracked)} untracked file(s) exist now")
        elif tar_item is not None and tar_item["status"] == "ok":
            bad = self.view.verify_artifact(tar_item)
            if bad:
                self.add(bad[0], path, bad[1])
            else:
                for note in compare_tar(str(self.view.run / tar_item["file"]), untracked, path, self.ctx.deep):
                    self.add("untracked-mismatch", path, note)
                self.stats["tars_compared"] += 1
        self.stale(path, "newest dirty file", max(dirty_file_mtimes(path, untracked, unborn), staged_newest))

    def check_unborn(self, need: Need, patch: dict[str, str] | None) -> int:
        """No commits yet, so nothing to diff: staged paths live in a staged-tar, the index and blobs in a gitdir-tar.

        Returns the newest mtime (seconds) among the staged files, for the staleness test.
        """
        path = need.row["path"]
        slug = self.slug(path)
        if patch is not None and patch["status"] == "ok":
            self.add("patch-mismatch", path, "a tracked patch is recorded but the repository has no commits")
        listed = must(run_git(["ls-files", "--cached", "-z"], cwd=path), "ls-files --cached")
        keep, _stats = filter_untracked(path, [n for n in listed.stdout.split(b"\0") if n])
        staged = self.view.one("staged-tar", slug)
        if staged is None:
            self.add("manifest-missing", path, "unborn HEAD: no staged-tar item in MANIFEST.tsv")
        elif staged["status"] == "empty":
            if keep:
                self.add("staged-mismatch", path, f"staged-tar recorded empty but {len(keep)} path(s) are staged now")
        elif staged["status"] != "ok":
            self.add("item-status", path, f"staged-tar item is {staged['status']}: {staged['note'][:120]}")
        else:
            bad = self.view.verify_artifact(staged)
            if bad:
                self.add(bad[0], path, bad[1])
            else:
                for note in compare_tar(str(self.view.run / staged["file"]), keep, path, self.ctx.deep):
                    self.add("staged-mismatch", path, note)
                self.stats["tars_compared"] += 1
        self.check_gitdir_copy(need)
        return max((st.st_mtime_ns // 1_000_000_000 for st in keep.values()), default=0)

    def check_gitdir_copy(self, need: Need) -> None:
        """The raw git-dir copy must hold the staged blobs and the current index."""
        path, common = need.row["path"], need.common or ""
        item = self.view.one("gitdir-tar", self.slug(common))
        if item is None:
            self.add("manifest-missing", path, "unborn HEAD: no gitdir-tar item (the index and blobs live only there)")
            return
        if item["status"] != "ok":
            self.add("item-status", path, f"gitdir-tar item is {item['status']}: {item['note'][:120]}")
            return
        bad = self.view.verify_artifact(item)
        if bad:
            self.add(bad[0], path, bad[1])
            return
        staged = must(run_git(["ls-files", "--stage", "-z"], cwd=path), "ls-files --stage").stdout.split(b"\0")
        blobs = sorted({e.split(b"\t", 1)[0].split()[1].decode() for e in staged if b"\t" in e})
        _refs, missing, index_member, err = inspect_gitdir_tar(
            str(self.view.run / item["file"]), os.path.basename(common), blobs
        )
        if err:
            self.add("bundle-verify", path, err)
            return
        if missing:
            self.add("gitdir-stale", path, f"{len(missing)} staged blob(s) are not in the raw git dir copy")
        try:
            current = os.stat(os.path.join(common, "index"))
        except OSError:
            current = None
        if current is not None and (
            index_member is None
            or index_member.size != current.st_size
            or abs(float(index_member.mtime) - current.st_mtime_ns / 1e9) >= 1.0
        ):
            self.add("gitdir-stale", path, "the index changed after the raw git dir copy was made")
        if self.ctx.deep and (problem := self.gitdir_fsck(str(self.view.run / item["file"]), os.path.basename(common))):
            self.add("bundle-verify", path, problem)
        self.stats["gitdir_tars_checked"] += 1

    # ---- detached heads --------------------------------------------------------------------------
    def check_head(self, need: Need) -> None:
        path = need.row["path"]
        head = run_git(["rev-parse", "HEAD"], cwd=path)
        sha = head.stdout.decode().strip()
        if head.returncode != 0 or not sha:
            self.add("git-error", path, "rev-parse HEAD failed: " + err_tail(head))
            return
        info = self.bundle_info(need.common) if need.common else BundleInfo()
        if info.usable and sha in info.heads.values():
            return
        item = self.view.one("head-bundle", self.slug(path))
        if item is None:
            self.add("head-uncovered", path, "detached HEAD is on no remote branch and no head-bundle item exists")
            return
        if item["status"] == "empty":
            # H7: `empty` only ever meant "reachable from a local remote-tracking ref", and those move and lie. HEAD
            # must be reachable from a tip the verified repository bundle carries.
            if not (need.common and self.reachable_from_bundle(need.common, path, [sha], info)):
                self.add(
                    "head-uncovered",
                    path,
                    "head bundle recorded empty, which rests on local remote-tracking refs, "
                    "and the repository bundle does not carry HEAD",
                )
            return
        if item["status"] != "ok":
            self.add("item-status", path, f"head-bundle item is {item['status']}: {item['note'][:120]}")
            return
        bad = self.view.verify_artifact(item)
        if bad:
            self.add(bad[0], path, bad[1])
            return
        bundle = str(self.view.run / item["file"])
        verify = run_git(["bundle", "verify", bundle], cwd=path)
        if verify.returncode != 0:
            self.add("bundle-verify", path, "head bundle failed git bundle verify: " + err_tail(verify))
            return
        heads = must(run_git(["bundle", "list-heads", bundle], cwd=path), "bundle list-heads").stdout.decode().split()
        if sha not in heads:
            self.add("head-uncovered", path, f"head bundle does not carry the current HEAD {sha[:10]}")
            return
        if self.ctx.deep and (problem := pack_check(bundle, need.common or path)):
            self.add("bundle-verify", path, problem)
            return
        prerequisites = bundle_prerequisites(bundle)
        if prerequisites and not (need.common and self.reachable_from_bundle(need.common, path, prerequisites, info)):
            # H7: a thin bundle verified in the live repository borrows its prerequisites from it; they must be
            # carried by the verified repository bundle instead, or the copy is not restorable on its own.
            self.add(
                "head-uncovered",
                path,
                f"head bundle is thin: {len(prerequisites)} prerequisite commit(s) are not carried by the repository bundle",
            )

    def reachable_from_bundle(self, common: str, path: str, commits: list[str], info: BundleInfo) -> bool:
        """Are all `commits` ancestors of (or equal to) a tip of the verified repository bundle? Asked of the live
        object graph, never of the remote-tracking refs, which are not evidence."""
        if not info.usable or not commits:
            return False
        tips = sorted(set(info.heads.values()))
        lost = set(missing_objects(common, tips))
        present = [t for t in tips if t not in lost]
        if not present:
            return False
        left = run_git(["rev-list", "-n", "1", *commits, "--not", *present], cwd=path)
        return left.returncode == 0 and not left.stdout.strip()

    # ---- unresolvable rows -------------------------------------------------------------------------
    def check_orphan(self, need: Need) -> None:
        path = need.row["path"]
        item = self.view.one("orphan-tree-tar", self.slug(path))
        if item is None:
            self.add("orphan-uncovered", path, "git cannot resolve this checkout and no orphan-tree-tar item exists")
            return
        if item["status"] not in ("ok", "empty"):
            self.add("item-status", path, f"orphan-tree-tar item is {item['status']}: {item['note'][:120]}")
            return
        current, _stats = filter_untracked(path, [n for n in walk_files(path) if n])
        if item["status"] == "empty":
            if current:
                self.add("orphan-uncovered", path, f"orphan tar recorded empty but {len(current)} file(s) exist now")
            return
        bad = self.view.verify_artifact(item)
        if bad:
            self.add(bad[0], path, bad[1])
            return
        for note in compare_tar(str(self.view.run / item["file"]), current, path, self.ctx.deep):
            self.add("orphan-uncovered", path, note)
        self.stats["orphan_tars_compared"] += 1

    # ---- what bundles, patches and tars of tracked content cannot carry (§6, §7) ----------------------
    def check_gitdir_required(self, need: Need) -> None:
        """§6: this repository needs a raw git-dir copy, and that copy must hold what made it necessary. The bundle stays
        required where the other components ask for it: the copy is in addition to the bundle, never instead of it."""
        path, common = need.row["path"], need.common or ""
        why = ", ".join(need.gitdir)
        item = self.view.one("gitdir-tar", self.slug(common))
        if item is None:
            self.add("manifest-missing", path, f"a raw git dir copy is required ({why}) and the run has no gitdir-tar item")
            return
        if item["status"] != "ok":
            self.add("item-status", path, f"gitdir-tar item is {item['status']}: {item['note'][:120]}")
            return
        bad = self.view.verify_artifact(item)
        if bad:
            self.add(bad[0], path, bad[1])
            return
        tar_path = str(self.view.run / item["file"])
        for note in gitdir_tar_problems(tar_path, os.path.basename(common), repo_state(self.ctx, path, common)):
            self.add("gitdir-incomplete", path, f"the raw git dir copy was required for {why}, but {note}")
        if self.ctx.deep and (problem := self.gitdir_fsck(tar_path, os.path.basename(common))):
            self.add("bundle-verify", path, problem)
        self.stats["gitdir_tars_checked"] += 1

    def check_lfs_storage(self, need: Need) -> None:
        """§6 (P9): git-lfs storage outside the git dir is not in the raw git-dir copy; it needs a tar of its own."""
        path, common = need.row["path"], need.common or ""
        item = self.view.one("lfs-storage-tar", self.slug(common))
        if item is None:
            self.add("manifest-missing", path, f"lfs.storage {tilde(need.lfs_storage)} is outside the git dir and the run has no lfs-storage-tar item")
            return
        if item["status"] not in ("ok", "empty"):
            self.add("item-status", path, f"lfs-storage-tar item is {item['status']}: {item['note'][:120]}")
            return
        live: dict[bytes, os.stat_result] = {}
        for current, _dirs, names in os.walk(need.lfs_storage):
            for name in names:
                full = os.path.join(current, name)
                live[os.fsencode(os.path.relpath(full, need.lfs_storage))] = os.lstat(full)
        if item["status"] == "empty":  # the producer's word for a storage directory that is missing or holds nothing
            if live:
                self.add("gitdir-incomplete", path, f"lfs-storage-tar recorded empty but lfs.storage holds {len(live)} file(s) now")
            return
        bad = self.view.verify_artifact(item)
        if bad:
            self.add(bad[0], path, bad[1])
            return
        prefix = os.path.basename(need.lfs_storage)
        try:
            with tarfile.open(str(self.view.run / item["file"]), "r:", encoding="utf-8", errors="surrogateescape") as tf:
                sizes = {normalize_member(m.name): m.size for m in tf if m.isreg()}
        except (OSError, tarfile.TarError) as exc:
            self.add("bundle-verify", path, f"lfs-storage-tar unreadable: {exc}")
            return
        wrong = [
            n
            for n, info in live.items()
            if sizes.get(n, sizes.get(os.fsencode(prefix) + b"/" + n)) != info.st_size
        ]
        if wrong:
            self.add("gitdir-incomplete", path, f"{len(wrong)} file(s) of lfs.storage are not in the tar at their live size, e.g. {fmt_name(wrong[0])}")

    def check_filtered(self, need: Need) -> None:
        """§7: bytes a clean filter or git-lfs keeps out of every blob live only in the working tree; the filtered-tar
        must hold each of them, and what it holds must still be what the working tree holds."""
        path = need.row["path"]
        item = self.view.one("filtered-tar", self.slug(path))
        present, stored = filtered_files(path)
        lost = unstored_of(path, present, stored)
        # the producer leaves out credential-pattern names (reported, never copied) and files over 2 GiB (they cannot be
        # snapshotted, which is a FAIL as it is for every other tar); neither can be expected in the filtered-tar
        credential = {n for n in lost if is_cred(fmt_name(n))}
        oversize = {n for n in lost if n not in credential and lost[n].st_size > MAX_FILE_BYTES}
        self.stats["credential_files_left_out"] += len(credential)
        if oversize:
            self.add("unsnapshotable", path, f"{len(oversize)} filtered file(s) over 2 GiB cannot be in the filtered-tar")
        lost = {n: info for n, info in lost.items() if n not in credential and n not in oversize}
        if not lost:
            return  # nothing the filter hides is left to lose that a tar could hold
        if item is None:
            self.add("manifest-missing", path, f"{len(lost)} tracked file(s) hold bytes git never stores (e.g. {fmt_name(next(iter(lost)))}) and the run has no filtered-tar item")
            return
        if item["status"] not in ("ok", "empty"):
            self.add("item-status", path, f"filtered-tar item is {item['status']}: {item['note'][:120]}")
            return
        if item["status"] == "empty":
            self.add("filtered-uncovered", path, f"filtered-tar recorded empty but {len(lost)} file(s) hold unstored bytes now")
            return
        bad = self.view.verify_artifact(item)
        if bad:
            self.add(bad[0], path, bad[1])
            return
        try:
            with tarfile.open(str(self.view.run / item["file"]), "r:", encoding="utf-8", errors="surrogateescape") as tf:
                members = {normalize_member(m.name) for m in tf}
                absent = sorted(n for n in lost if normalize_member(fmt_name(n)) not in members)
                if absent:
                    self.add("filtered-uncovered", path, f"{len(absent)} file(s) with unstored bytes are not in the filtered-tar, e.g. {fmt_name(absent[0])}")
                kept = {n: info for n, info in present.items() if normalize_member(fmt_name(n)) in members}
                extra = sorted(members - {normalize_member(fmt_name(n)) for n in present})
                if extra:
                    self.add("filtered-uncovered", path, f"{len(extra)} tar member(s) are no filter-attributed working-tree file, e.g. {fmt_name(extra[0])}")
                want = {normalize_member(fmt_name(k)): (k, v) for k, v in kept.items()}
                for note in tar_differences(tf, want, os.fsencode(path), self.ctx.deep):
                    self.add("filtered-uncovered", path, note)
        except (OSError, tarfile.TarError) as exc:
            self.add("bundle-verify", path, f"filtered-tar unreadable: {exc}")
        self.stats["tars_compared"] += 1

    # ---- driver ---------------------------------------------------------------------------------
    def run(self) -> None:
        """Judge every prepared need (see prepare_needs) against this run, one component at a time."""
        init = run_git(["init", "--bare", "-q", self.empty])
        if init.returncode != 0:
            self.begin(("scratch", self.scratch))
            self.add("git-error", self.scratch, "cannot create the scratch repository: " + err_tail(init))
            return
        by_common: dict[str, list[Need]] = collections.defaultdict(list)
        for need in self.needs:
            if need.orphan:
                self.begin(("orphan", need.row["path"]))
                with self.guarded(need.row["path"]):
                    self.check_orphan(need)
            elif need.bundle and need.common:
                by_common[need.common].append(need)
        for common, needs in by_common.items():
            subject = needs[0].row["path"]
            self.begin(("bundle", common))
            with self.guarded(subject):
                for code, message in self.check_refs(common, self.bundle_info(common)):
                    self.add(code, subject, message)
                self.stale(subject, "newest commit", newest_commit_ts(common, subject))
        for key, need in need_keys([n for n in self.needs if not n.orphan and n.common]):
            if key[0] in ("gitdir", "lfs-storage", "filtered"):
                self.begin(key)
                with self.guarded(need.row["path"]):
                    {"gitdir": self.check_gitdir_required, "lfs-storage": self.check_lfs_storage}.get(
                        key[0], self.check_filtered
                    )(need)
        for need in self.needs:
            if need.orphan or need.common is None:
                continue
            path = need.row["path"]
            if need.dirty:
                self.begin(("dirty", path))
                with self.guarded(path):
                    self.check_dirty(need)
            if need.head:
                self.begin(("head", path))
                with self.guarded(path):
                    self.check_head(need)
                    self.stale(path, "newest commit", newest_commit_ts(need.common, path))


def prepare_needs(needs: list[Need], ctx: Ctx | None = None) -> tuple[list[Need], list[Need]]:
    """Resolve each need against the live Mac once: (present checkouts, vanished ones). Marks unresolvable orphans, and
    (with a ctx) what live git says a raw git-dir copy must hold (§6)."""
    present: list[Need] = []
    vanished: list[Need] = []
    for need in needs:
        path = need.row["path"]
        if not os.path.isdir(path):
            vanished.append(need)
            continue
        need.common = resolve_common(path)
        need.orphan = need.common is None
        if ctx is not None and need.common is not None:
            try:
                state = repo_state(ctx, path, need.common, need.row["kind"] == "repo")
                need.gitdir, need.lfs_storage = state.gitdir_reasons(), state.lfs_storage()
            except GitReadError as exc:
                need.git_error = str(exc)
        present.append(need)
    return present, vanished


@functools.lru_cache(maxsize=2)
def rescue_index(manifest: str, _mtime_ns: int, _size: int) -> tuple[list[str], list[str], list[str]]:
    """A RESCUE-MANIFEST.sha256 parsed once (many vanished rows share one manifest) and sorted by path, so one
    row's slice is found by bisection: (paths, shas, malformed lines). The mtime and size key the cache."""
    entries, bad = parse_shasum_manifest(Path(manifest))
    pairs = sorted((e.removeprefix("./"), sha) for sha, e in entries)
    return [path for path, _sha in pairs], [sha for _path, sha in pairs], bad


BORROW_NAMES = ("alternates", "http-alternates")  # objects/info files that make a repository borrow objects (any case)
CUSTODY_FINDING_LIMIT = 25  # a git dir full of links reports its first few, not tens of thousands


def custody_git_findings(git: Path) -> list[tuple[str, str, str]]:
    """C1-C5: why a copy's git dir is not self-contained, from a recursive lstat walk of the WHOLE git dir.
    Returns (kind, path relative to the git dir's parent, detail) for each of:
      symlink      a link at any depth (loose objects, packs, refs, objects/ itself) whose target leaves the copy (the
                   git dir's parent) or is not there to resolve: it can lead back onto the Mac. A link that resolves
                   inside the copy, such as a hook pointing at a script in the work tree, holds nothing of the Mac's.
      alternates   an objects/info/alternates or http-alternates file, in any case: the objects are borrowed
      commondir    a commondir file at the top (a standalone git dir has none) or one that resolves outside the git dir
      unreadable   a directory the walk could not list: what is in it is unknown, so it is never read as clean
    The first CUSTODY_FINDING_LIMIT findings are returned. The work tree is not walked: its symlinks are tracked
    content (git stores the link text), compared elsewhere."""
    found: list[tuple[str, str, str]] = []
    real_git = os.path.realpath(git)
    real_copy = os.path.dirname(real_git)

    def add(kind: str, full: str, detail: str = "") -> None:
        if len(found) < CUSTODY_FINDING_LIMIT:
            found.append((kind, f"{git.name}/{os.path.relpath(full, git)}", detail))

    def unreadable(exc: OSError) -> None:
        add("unreadable", str(exc.filename or git), exc.strerror or "")

    for current, dirs, names in os.walk(git, onerror=unreadable):  # followlinks stays off: a link is reported, not read
        for name in (*dirs, *names):
            full = os.path.join(current, name)
            if os.path.islink(full):
                target = os.path.realpath(full)
                if target != real_copy and not target.startswith(real_copy + os.sep):
                    add("symlink", full, target)
        for name in names:
            full = os.path.join(current, name)
            if os.path.islink(full):
                continue
            low = name.casefold()
            if (
                low in BORROW_NAMES
                and os.path.basename(current).casefold() == "info"
                and os.path.basename(os.path.dirname(current)).casefold() == "objects"
            ):
                add("alternates", full)
            elif low == "commondir":
                try:
                    with open(full, "rb") as handle:
                        target = handle.read(4096).decode("utf-8", "replace").strip()
                except OSError as exc:
                    add("unreadable", full, exc.strerror or "")
                    continue
                resolved = os.path.realpath(os.path.join(current, target))
                inside = resolved == real_git or resolved.startswith(real_git + os.sep)
                if current == str(git) or not inside:
                    add("commondir", full, target)
    return found


def git_dir_links(git: Path) -> list[str]:
    """Every symlink anywhere under a git dir whose target leaves the copy, as '<git dir>/<relative path>': a copy whose
    objects, packs or refs are links can lead straight back onto the Mac, whatever its manifest says (the walk is
    recursive, not one level)."""
    return [rel for kind, rel, _detail in custody_git_findings(git) if kind == "symlink"]


def custody_git_identity(copy: str) -> str:
    """C2/C4: '' when git, run inside the copy, reads its own `.git` for the git dir, the common dir and the object
    store; otherwise why not. A commondir file, a gitfile or a link would make git answer from somewhere else."""
    own = os.path.realpath(os.path.join(copy, ".git"))
    proc = run_git(["rev-parse", "--absolute-git-dir", "--git-common-dir", "--git-path", "objects"], cwd=copy)
    lines = proc.stdout.decode("utf-8", "surrogateescape").splitlines()
    if proc.returncode != 0 or len(lines) < 3:
        return f"git cannot open the copy's repository ({err_tail(proc)})"
    git_dir, common, objects = (os.path.realpath(os.path.join(copy, line)) for line in lines[:3])
    if git_dir != own or common != own:
        return f"git reads this copy's repository from {tilde(common)}, not from its own .git"
    if not objects.startswith(own + os.sep):
        return f"git reads this copy's objects from {tilde(objects)}, outside its own .git"
    return ""


def rescue_problems(ctx: Ctx, root: Path, rel: str) -> list[str]:
    """F8: a recovered tree must re-hash against the RESCUE-MANIFEST.sha256 the rescue wrote beside it, and hold no
    regular file that manifest does not list. A tree nobody can re-hash is a copy of unknown content."""
    manifest = root / "RESCUE-MANIFEST.sha256"
    if not manifest.is_file():
        return [f"{root.name} has no RESCUE-MANIFEST.sha256, so the recovered tree cannot be re-hashed"]
    stat_result = manifest.stat()
    paths, shas, bad = rescue_index(str(manifest), stat_result.st_mtime_ns, stat_result.st_size)
    first, last = bisect.bisect_left(paths, rel + "/"), bisect.bisect_left(paths, rel + "0")  # "0" follows "/"
    mine = list(zip(shas[first:last], paths[first:last], strict=True))
    if not mine:
        return [f"RESCUE-MANIFEST.sha256 lists no file under {rel}"]
    found, _files, _nbytes = verify_hash_entries(root, mine, ctx)
    problems = [f"malformed RESCUE-MANIFEST.sha256 {b}" for b in bad] + [f"rescue manifest: {p}" for p in found[:3]]
    if len(found) > 3:
        problems.append(f"rescue manifest: +{len(found) - 3} more entries failed")
    listed = {e for _sha, e in mine}
    unlisted = [
        os.path.relpath(os.path.join(cur, name), root)
        for cur, _dirs, names in os.walk(root / rel)
        for name in names
        if not os.path.islink(os.path.join(cur, name)) and os.path.relpath(os.path.join(cur, name), root) not in listed
    ]
    if unlisted:
        problems.append(
            f"{len(unlisted)} file(s) in the recovered tree are not in the rescue manifest, e.g. {unlisted[0]}"
        )
    git = root / rel / ".git"
    if git.is_dir() and not git.is_symlink():  # a missing, linked or gitfile .git is check_vanished's to report
        pointers = []
        findings = custody_git_findings(git)
        for kind, where, detail in findings:
            if kind == "commondir":
                pointers.append(f"{where} names another git dir ({detail or 'empty'}), so the copy is not standalone")
            elif kind == "alternates" and not where.endswith("objects/info/alternates"):
                pointers.append(f"{where} borrows objects (a spelling objects/info/alternates misses)")
            elif kind == "unreadable":
                pointers.append(f"{where} cannot be read ({detail}), so what it holds is unknown")
        problems += pointers
        if not findings and (why := custody_git_identity(str(root / rel))):  # a link is check_vanished's to report
            problems.append(why)
    return problems


def check_vanished(ctx: Ctx, need: Need, stats: collections.Counter[str]) -> list[Problem]:
    """Accept a vanished entry only if the recovery directory holds a copy that matches the sweep's record."""
    path, row = need.row["path"], need.row
    try:
        os.lstat(path)
    except FileNotFoundError:
        pass  # F7: the only proof of absence; any other error means the data may still be on the Mac
    except OSError as exc:
        why = f"cannot confirm the checkout is gone ({type(exc).__name__}: {exc.strerror}); no copy can stand in for it"
        return [Problem("row-unverifiable", path, why)]
    else:
        return [Problem("row-vanished", path, "the path still exists but is not a usable checkout directory")]
    root = ctx.recovery_root
    if root is None or not root.is_dir():
        return [Problem("row-vanished", path, "no longer on disk and no recovery directory is available")]
    home = ctx.home
    if not path.startswith(home + "/"):
        return [Problem("row-vanished", path, "no longer on disk and outside $HOME, so it has no recovery location")]
    rel = path[len(home) + 1 :]
    copy = str(root / rel)
    if not os.path.isdir(copy):
        return [Problem("row-vanished", path, f"no longer on disk and absent from the recovery directory {root.name}")]
    if why := custody_problem(ctx, root):  # H2: a recovery copy on the Mac's own disk dies with the erase
        return [Problem("row-vanished", path, f"recovery copy is not custody: {why}")]
    if not within_real(root, rel):
        return [Problem("row-vanished", path, "recovery copy is reached through a symlink")]
    top = run_git(["rev-parse", "--show-toplevel"], cwd=copy).stdout.decode("utf-8", "surrogateescape").strip()
    if not top or os.path.realpath(top) != os.path.realpath(copy):
        return [Problem("row-vanished", path, "recovery copy is not a repository root")]
    problems = rescue_problems(ctx, root, rel)
    git_entry = os.path.join(copy, ".git")
    if os.path.islink(git_entry) or not os.path.isdir(git_entry):
        problems.append("recovery copy's .git is not a real directory (a gitfile or link can lead back to the Mac)")
    else:
        problems += [f"recovery copy: {link} is a symlink" for link in git_dir_links(Path(git_entry))]
    if os.path.lexists(os.path.join(copy, ".git", "shallow")) and row.get("shallow", "") not in ("1", "yes", "true"):
        problems.append("recovery copy is shallow (truncated history) but the sweep row was not")
    sym = run_git(["symbolic-ref", "--short", "-q", "HEAD"], cwd=copy)
    branch = sym.stdout.decode("utf-8", "surrogateescape").strip() if sym.returncode == 0 else "(detached)"
    if branch != row["branch"]:
        problems.append(f"HEAD is {branch}, sweep recorded {row['branch']}")
    counts = {
        "unpushed": run_git(["rev-list", "--count", "--branches", "--not", "--remotes"], cwd=copy).stdout,
        "stashes": b"%d" % stash_count(os.path.join(copy, ".git"))
        if os.path.isdir(os.path.join(copy, ".git"))
        else b"?",
        "dirty": b"%d"
        % len(run_git(["status", "--porcelain=v1", "--untracked-files=normal"], cwd=copy).stdout.splitlines()),
    }
    for key, raw in counts.items():
        if raw.decode().strip() != row[key]:
            problems.append(f"{key} is {raw.decode().strip() or '?'}, sweep recorded {row[key]}")
    remote = run_git(["config", "--get", "remote.origin.url"], cwd=copy).stdout.decode("utf-8", "replace").strip()
    if (remote or "NONE") != row["remote"]:
        problems.append("origin url differs from the sweep")
    unreadable = [
        f"{name}@{sha[:10]}"
        for name, sha in current_refs(os.path.join(copy, ".git")).items()
        if run_git(["rev-parse", "--verify", "-q", sha + "^{commit}"], cwd=copy).returncode != 0
    ]
    if unreadable:
        problems.append("branch tip commit(s) unreadable: " + ", ".join(unreadable[:3]))
    if os.path.lexists(os.path.join(copy, ".git", "objects", "info", "alternates")):
        problems.append("recovery copy borrows objects through objects/info/alternates")
    if ctx.deep and not problems:
        fsck = run_git(["fsck", "--connectivity-only", "--no-dangling"], cwd=copy, timeout=1800)
        if fsck.returncode != 0:
            problems.append("git fsck --connectivity-only failed: " + err_tail(fsck))
    if problems:
        return [
            Problem(
                "row-vanished", path, f"recovery copy in {root.name} does not match the sweep: " + "; ".join(problems)
            )
        ]
    stats["recovered_accepted"] += 1
    return []


def vanished_problems(ctx: Ctx, need: Need, stats: collections.Counter[str]) -> list[Problem]:
    """check_vanished with a failing git read (H3) turned into a row-vanished problem instead of an exception."""
    try:
        return check_vanished(ctx, need, stats)
    except GitReadError as exc:
        path = need.row["path"]
        return [Problem("row-vanished", path, f"the recovery copy could not be read: {exc}")]


def bundle_prerequisites(bundle: str) -> list[str]:
    """The commits a bundle's header says the importing repository must already have (its `-<sha>` lines)."""
    found: list[str] = []
    with open(bundle, "rb") as handle:
        if not handle.readline().startswith(b"# v"):
            return found
        for line in handle:
            if line in (b"\n", b""):
                break
            if line.startswith(b"-") and line[1:].split():
                found.append(line[1:].split()[0].decode("ascii", "replace"))
    return found


def pack_check(bundle: str, empty_gitdir: str) -> str:
    """Stream the pack through `git unpack-objects -n` (checksum and zlib of every object, writes nothing)."""
    with open(bundle, "rb") as probe:
        if not probe.readline().startswith((b"# v2 git bundle", b"# v3 git bundle")):
            return "bad bundle signature"
        while probe.readline() not in (b"\n", b""):
            pass
        offset = probe.tell()
    # A fresh handle seeked to the pack: the probe's read-ahead would have moved the shared file offset.
    with open(bundle, "rb") as handle:
        handle.seek(offset)
        try:
            proc = subprocess.run(
                [*GIT_BASE, "--git-dir=" + empty_gitdir, "unpack-objects", "-n", "-q"],
                check=False,
                stdin=handle,
                capture_output=True,
                env=git_env(),
                timeout=1800,
            )
        except subprocess.TimeoutExpired:
            return "pack stream check timed out"
    return "" if proc.returncode == 0 else "pack stream check failed: " + err_tail(proc)


WAIVER_COLS = ("path", "reason", "evidence_path", "evidence_sha256", "signer", "kind")  # F7; signed_at is optional
# F7: the closed set of claims a signer can make. All three give up the Mac copy; the output says which one was made.
WAIVER_KINDS = ("remote-held", "copy-elsewhere", "loss-accepted")


def load_signers(path: Path | None) -> tuple[set[str], str]:
    """The waiver signer allow-list: (names, error). One name per line, # comments; an unreadable list names nobody."""
    if path is None:
        return set(), "no --waiver-signers allow-list was given, so no signer can be verified"
    try:
        text = path.read_bytes().decode("utf-8", "replace")
    except OSError as exc:
        return set(), f"cannot read the signer allow-list: {exc.strerror}"
    names = {ln.strip() for ln in text.splitlines() if ln.strip() and not ln.strip().startswith("#")}
    return names, "" if names else "the signer allow-list names nobody"


def attest_window(text: str) -> tuple[float, float] | None:
    """The instants an ISO date or datetime stands for: (first, last). A date-only value is its whole UTC day, a
    datetime one instant. None when it is neither."""
    try:
        if len(text) == 10:
            first = datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp()
            return first, first + 86399
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    instant = (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()
    return instant, instant


def is_future(text: str, now: float) -> bool:
    """H6: is an ISO date or datetime later than now (plus clock skew)? A date-only value counts from its first second."""
    window = attest_window(text)
    return window is not None and window[0] > now + FUTURE_SKEW_SEC


PATH_CHARS = r"A-Za-z0-9/_~+@%\-"  # characters that continue a path: a longer path is not the path it contains


def path_token(needle: bytes) -> re.Pattern[bytes]:
    """W1: the path as a whole token. Nothing that continues a path may precede or follow it, so the evidence for
    `<path>-v2`, `<path>/sub` or `/mnt/old<path>` is not evidence for `<path>`; a closing '.' is punctuation."""
    before = f"(?<![{PATH_CHARS}.])".encode()
    after = f"(?![{PATH_CHARS}]|\\.[{PATH_CHARS}])".encode()
    return re.compile(before + re.escape(needle) + after)


def hash_and_find(path: str, needles: list[bytes]) -> tuple[str, bool]:
    """sha256 of a file and whether any needle occurs in it as a whole path token (see path_token)."""
    with open(path, "rb") as handle:
        try:
            view = mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ)
        except ValueError:  # an empty file cannot be mapped, and names nothing
            return hashlib.sha256().hexdigest(), False
        with view:
            return hashlib.sha256(view).hexdigest(), any(path_token(n).search(view) for n in needles)


def exposure_of(row: dict[str, str], reasons: list[str] | None = None) -> str:
    """What is unpreserved for a row: the data a waiver or disposal gives up. `reasons` are the plan's own (they
    include remote-not-proven); without them the sweep's columns say it."""
    counts = {"dirty": row["dirty"], "unpushed": row["unpushed"], "stash": row["stashes"]}
    return ",".join(f"{r}={counts[r]}" if r in counts else r for r in (reasons_for(row) if reasons is None else reasons))


def judged_artifacts(ctx: Ctx) -> set[str]:
    """Files under judgment: evidence that merely lists a path (the sweep, a proof file) or is the signed record itself
    proves nothing about where the work is."""
    judged: list[Path | None] = [
        ctx.waivers,
        ctx.disposals,
        ctx.sweep,
        ctx.remote_held,
        ctx.remote_held.parent / "tips.tsv" if ctx.remote_held else None,
        ctx.waiver_signers,
        ctx.ignored_payload_attestation,
        ctx.backblaze_attestation,
        ctx.credential_attestation,
        *ctx.nongit_items,
    ]
    return {os.path.realpath(j) for j in judged if j is not None}


def evidence_problem(ctx: Ctx, evidence: str, claimed: str, path: str, base: Path) -> tuple[str, str]:
    """(resolved path, why not): the evidence must be a regular file (a relative one resolves beside `base`, the
    record's own directory), not an artifact under judgment, hash to the claimed sha256, and name the waived path as
    a whole token (absolute or ~/-relative). Free text is never evidence by itself."""
    resolved = evidence if os.path.isabs(evidence) else str(base / evidence)
    try:
        st = os.lstat(resolved)
    except OSError as exc:
        return resolved, f"evidence path is unreadable: {exc.strerror} ({evidence})"
    if not stat.S_ISREG(st.st_mode):
        return resolved, f"evidence must be a regular file, not a directory, link or device: {evidence}"
    if os.path.realpath(resolved) in judged_artifacts(ctx):
        # a file that merely lists the path (the sweep) or is the signed record itself proves nothing about where the
        # work is
        return (
            resolved,
            "the evidence is the waivers file itself or another artifact under judgment "
            "(sweep, remote-held, disposals, signers)",
        )
    if st.st_mtime > ctx.now + FUTURE_SKEW_SEC:
        return resolved, "the evidence file is dated in the future"
    if not re.fullmatch(r"[0-9a-fA-F]{64}", claimed):
        return resolved, "evidence_sha256 is not a 64-hex sha256"
    needles = [os.fsencode(path)]
    if path.startswith(ctx.home + "/"):
        needles.append(os.fsencode("~/" + path[len(ctx.home) + 1 :]))
    try:
        got, mentions = hash_and_find(resolved, needles)
    except OSError as exc:
        return resolved, f"evidence file is unreadable: {exc.strerror}"
    if got != claimed.lower():
        return resolved, "the evidence file's sha256 differs from evidence_sha256"
    if not mentions:
        return resolved, "the evidence file never mentions the waived path"
    return resolved, ""


def vet_waivers(ctx: Ctx, rows: list[dict[str, str]]) -> tuple[dict[str, Waiver], list[Problem]]:
    """Validate the waivers file. A waiver is honoured only for a sweep row whose path has vanished from the Mac
    (os.lstat raises FileNotFoundError, nothing else), signed by an allow-listed signer, typed by a known kind, with
    a re-hashed evidence file that names the path; anything else is itself a FAIL (waiver-invalid)."""
    if ctx.waivers is None:
        return {}, []
    problems: list[Problem] = []
    try:
        text = ctx.waivers.read_bytes().decode("utf-8", "surrogateescape")
        mtime = ctx.waivers.stat().st_mtime
    except OSError as exc:
        return {}, [Problem("waiver-invalid", str(ctx.waivers), f"cannot read the waivers file: {exc.strerror}")]
    lines = [ln for ln in text.split("\n") if ln.strip()]
    header = [c.strip().lower() for c in lines[0].split("\t")] if lines else []
    if any(col not in header for col in WAIVER_COLS):
        return {}, [Problem("waiver-invalid", str(ctx.waivers), f"header must carry the columns {list(WAIVER_COLS)}")]
    if mtime > ctx.now + FUTURE_SKEW_SEC:
        return {}, [Problem("waiver-invalid", str(ctx.waivers), "the waivers file is dated in the future")]
    signers, signers_error = load_signers(ctx.waiver_signers)
    col = {name: header.index(name) for name in (*WAIVER_COLS, "signed_at") if name in header}
    by_path = {r["path"]: r for r in rows}
    valid: dict[str, Waiver] = {}
    seen: set[str] = set()
    for lineno, line in enumerate(lines[1:], start=2):
        parts = line.split("\t") + [""] * len(header)
        path, reason, evidence, claimed, signer, kind = (parts[col[name]].strip() for name in WAIVER_COLS)
        signed_at = parts[col["signed_at"]].strip() if "signed_at" in col else ""
        subject = path or f"{ctx.waivers}:{lineno}"
        why = ""
        resolved = evidence
        if not path:
            why = "waiver names no path"
        elif path in seen:
            why = "more than one waiver for this path"
        elif path not in by_path:
            why = "path is not a row of the sweep"
        elif not reason:
            why = "waiver has no reason"
        elif not signer:
            why = "waiver has no signer"
        elif signers_error:
            why = signers_error
        elif signer not in signers:
            why = f"signer {signer!r} is not on the allow-list"
        elif kind not in WAIVER_KINDS:
            why = f"kind {kind!r} is not one of {list(WAIVER_KINDS)}"
        elif signed_at and (parse_attest_date(signed_at) is None or is_future(signed_at, ctx.now)):
            why = f"signed_at {signed_at!r} is not an ISO date in the past"
        elif not evidence:
            why = "waiver has no evidence_path"
        else:
            resolved, why = evidence_problem(ctx, evidence, claimed, path, ctx.waivers.parent)
        if not why and path:
            try:
                os.lstat(path)
            except FileNotFoundError:
                pass  # the only proof of absence; EPERM, ENOTDIR and friends mean "cannot tell", never "gone"
            except OSError as exc:
                why = f"cannot confirm the path is gone ({type(exc).__name__}: {exc.strerror}), so it cannot be waived"
            else:
                why = "the path still exists on disk, so it cannot be waived"
        if not why and path:
            why = waiver_moved_problem(ctx, path, by_path[path])
        if why:
            problems.append(Problem("waiver-invalid", subject, why))
        else:
            valid[path] = Waiver(path, reason, resolved, signer, kind, exposure_of(by_path[path]), signed_at)
        seen.add(path)
    return valid, problems


def plan_exposure(waiver: Waiver, plan: Plan) -> Waiver:
    """W3: the exposure a waiver gives up is the PLAN's reasons for that row (they include remote-not-proven), not only
    the sweep's own columns, so an applied waiver over a proof-less row still prints its EXPOSED line."""
    need = next((n for n in plan.needs if n.row["path"] == waiver.path), None)
    return waiver if need is None else dataclasses.replace(waiver, exposure=exposure_of(need.row, need.reasons))


def waiver_moved_problem(ctx: Ctx, path: str, row: dict[str, str]) -> str:
    """W2: a path that is gone may only have MOVED. The fresh scan prunes ~/.Trash, so a checkout dragged there leaves
    the sweep's universe with its data still on this disk. '' when the Trash holds no checkout of the waived name
    and origin, else why the waiver is refused. Only where the stray scan is on, i.e. where $HOME is the Mac's."""
    trash = os.path.join(ctx.home, ".Trash")
    if not ctx.discovery_strays or not os.path.lexists(trash):
        return ""
    try:
        proc = subprocess.run(
            ["find", trash, "-xdev", "-maxdepth", "8", "-iname", ".git", "-print0", "-prune"],
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=600,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return f"cannot search {tilde(trash)} for the moved checkout ({exc}), so it cannot be waived"
    if proc.returncode != 0 or proc.stderr.strip():
        return f"cannot search {tilde(trash)} for the moved checkout (find reported errors), so it cannot be waived"
    name = os.path.basename(path).casefold()
    for raw in proc.stdout.split(b"\0"):
        repo = os.path.dirname(os.fsdecode(raw)) if raw else ""
        found = os.path.basename(repo).casefold()
        if not repo or not (found == name or found.startswith(name + " ")):  # Finder suffixes a colliding name
            continue
        origin = run_git(["config", "--get", "remote.origin.url"], cwd=repo)
        if origin.returncode not in (0, 1):  # unreadable: cannot rule it out
            return f"{tilde(repo)} in the Trash cannot be read, so a moved checkout cannot be ruled out"
        url = origin.stdout.decode("utf-8", "replace").strip() or "NONE"
        if url == row["remote"]:
            return f"the checkout was moved, not removed: {tilde(repo)} has the same name and origin, data still on disk"
    return ""


def remote_held_age_problem(ctx: Ctx) -> str:
    """H6: PROVEN-ALL is a statement about one moment; an old or future-dated remote-held file proves nothing now."""
    if ctx.remote_held is None:
        return ""
    if not 0 < ctx.max_remote_held_age_min <= MAX_REMOTE_HELD_AGE_CEILING_MIN:
        return f"the {ctx.max_remote_held_age_min:g}m remote-held age bound is outside (0, {MAX_REMOTE_HELD_AGE_CEILING_MIN:g}]"
    try:
        age_min = (ctx.now - ctx.remote_held.stat().st_mtime) / 60
    except OSError as exc:
        return f"cannot read the remote-held file: {exc.strerror}"
    if age_min < -FUTURE_SKEW_SEC / 60:
        return f"the remote-held file is dated {-age_min:.0f}m in the future"
    if age_min > ctx.max_remote_held_age_min:
        return (
            f"the remote-held proof is {age_min:.0f}m old, over the {ctx.max_remote_held_age_min:g}m bound "
            "(its PROVEN-ALL verdicts are stale; re-run the prove lane)"
        )
    return ""


def check_git_preserved(ctx: Ctx) -> Result:
    try:
        rows = load_sweep(ctx.sweep)
        if why := remote_held_age_problem(ctx):
            raise SweepError(why)
        held = load_remote_held(ctx.remote_held) if ctx.remote_held else None
    except SweepError as exc:
        return Result("git-preserved", FAIL, str(exc), [Problem("input-unusable", str(ctx.sweep), str(exc))])
    waivers, waiver_problems = vet_waivers(ctx, rows)
    result = evaluate_git_preserved(ctx, rows, held, waivers)
    if waiver_problems:
        shown = " | ".join(str(p) for p in waiver_problems[:3])
        result.status = FAIL
        result.problems += waiver_problems
        result.extra += [str(p) for p in waiver_problems]
        result.detail += f"; {len(waiver_problems)} invalid waiver(s): {shown}"
    return result


def evaluate_git_preserved(
    ctx: Ctx, rows: list[dict[str, str]], held: dict[str, set[str]] | None, waivers: dict[str, Waiver]
) -> Result:
    live = derive_live(ctx, rows, held)  # F1 F2 F6: the plan is built from live git, never from the sweep alone
    plan = build_plan(live.rows, live.held, live.extra)
    disposed, disposal_problems = vet_disposals(ctx, live.rows, plan)
    return fold_exposure(evaluate_plan(ctx, plan, waivers), live, disposed, disposal_problems)


def fold_exposure(res: Result, live: Live, disposed: list[Waiver], disposal_problems: list[Problem]) -> Result:
    """Add what live git, the proof binding and the disposal records found. None of it can be waived or covered."""
    res.waived += disposed
    lead = []  # leads the detail: a verdict line is cut short, and the cause must not be what gets cut
    found = live.problems + disposal_problems
    if found:
        codes = ", ".join(f"{c}={n}" for c, n in sorted(collections.Counter(p.code for p in found).items()))
        more = f" (+{len(found) - 3} more)" if len(found) > 3 else ""
        res.status = FAIL
        res.problems += found
        res.extra += [str(p) for p in found]
        lead.append(
            f"{len(found)} live-exposure problem(s) no preserve run can cover [{codes}]: "
            + " | ".join(str(p) for p in found[:3])
            + more
        )
    lead += live.notes
    if disposed:
        lead.append(f"{len(disposed)} disposable-marker row(s) DISPOSED by signed record")
    res.detail = "; ".join([*lead, res.detail])
    return res


def evaluate_plan(ctx: Ctx, plan: Plan, waivers: dict[str, Waiver]) -> Result:
    scope = (
        f"{plan.entries} sweep entries: {len(plan.needs)} need preservation, {plan.safe} safe, "
        f"{plan.disposable} under a disposable marker (still judged), {plan.waived} proven remote-held"
    )
    if not plan.needs:
        return Result("git-preserved", PASS, scope + "; nothing to preserve")
    views, manuals, skipped = open_sources(ctx)
    if not views and not manuals:
        if skipped:
            problems = [Problem("run-incomplete", name, reason) for name, reasons in skipped for reason in reasons]
            return Result(
                "git-preserved",
                FAIL,
                f"{scope}; no usable source: " + "; ".join(f"{n}: {'; '.join(r)}" for n, r in skipped),
                problems,
            )
        where = tilde(str(ctx.preserve_root))
        return Result(
            "git-preserved",
            FAIL,
            f"{scope}; no run-* or manual-* source under {where}",
            [Problem("run-missing", str(ctx.preserve_root), "no preserve run exists")],
        )
    present, vanished = prepare_needs(plan.needs, ctx)
    stats: collections.Counter[str] = collections.Counter()
    problems_all: list[Problem] = [p for need in vanished for p in vanished_problems(ctx, need, stats)]
    problems_all += [Problem("git-error", n.row["path"], n.git_error) for n in present if n.git_error]
    sources: list[Source] = []
    scratch = tempfile.mkdtemp(prefix="exit-ready-", dir=str(ctx.scratch) if ctx.scratch else None)
    try:
        for view in sorted(views, key=lambda v: v.run.name, reverse=True):
            evaluator = GitPreserved(ctx, present, view, scratch)
            evaluator.run()
            stats.update(evaluator.stats)
            stats["artifacts_hashed"] += view.files_hashed
            stats["bytes_hashed"] += view.bytes_hashed
            sources.append(Source(view.run.name, evaluator.components, verifier_note(view.run)))
        for manual in sorted(manuals, key=lambda m: m.name, reverse=True):
            copies = ManualSource(ctx, manual)
            sources.append(Source(manual.name, copies.evaluate(present), "manual copy"))
            stats["manual_files_hashed"] += copies.hashed
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    coverage, uncovered = settle_coverage(present, sources)
    problems_all += uncovered + [
        p for s in sources for key, ps in s.components.items() if key[0] == "scratch" for p in ps
    ]
    applied: dict[str, Waiver] = {}
    unwaived: list[Problem] = []
    for problem in problems_all:
        if problem.code == "row-vanished" and problem.subject in waivers:
            applied[problem.subject] = plan_exposure(waivers[problem.subject], plan)
        else:
            unwaived.append(problem)
    problems_all = unwaived
    kinds = collections.Counter(
        "orphan" if n.orphan else k for n in plan.needs for k in ("dirty", "bundle", "head") if getattr(n, k)
    )
    counts = f"dirty={kinds['dirty']} bundle={kinds['bundle']} head={kinds['head']} orphan={kinds['orphan']}"
    by_source = collections.Counter(coverage.values())
    if stats["recovered_accepted"]:
        by_source["recovery"] = stats["recovered_accepted"]
    used = ", ".join(f"{name}={n}" for name, n in sorted(by_source.items())) or "none"
    proof = (
        f"sources: {'; '.join(f'{s.name} ({s.note})' for s in sources)}; components covered by source: {used}; "
        f"hashed {stats['artifacts_hashed']} artifacts ({stats['bytes_hashed']} bytes), "
        f"{stats['bundles_verified']} bundles verified, {stats['gitdir_tars_checked']} raw git-dir copies read, "
        f"{stats['patches_compared']} patches and {stats['tars_compared']} tars compared to live state"
    )
    left_out = stats["credential_files_left_out"]
    note = f"; {left_out} credential-pattern file(s) deliberately left out of snapshots" if left_out else ""
    if skipped:
        note += "; ignored incomplete source(s): " + ", ".join(f"{n} ({'; '.join(r)[:80]})" for n, r in skipped)
    if applied:
        note += f"; {len(applied)} vanished row(s) WAIVED"
    if unused := sorted(set(waivers) - set(applied)):
        note += f"; {len(unused)} valid waiver(s) unused (nothing to waive), e.g. {tilde(unused[0])}"
    covered_lines = coverage_lines(present, coverage)
    if problems_all:
        codes = ", ".join(f"{c}={n}" for c, n in sorted(collections.Counter(p.code for p in problems_all).items()))
        examples = " | ".join(str(p) for p in problems_all[:3])
        more = f" (+{len(problems_all) - 3} more)" if len(problems_all) > 3 else ""
        found = f"{len(problems_all)} problem(s) [{codes}]: {examples}{more}"
        return Result(
            "git-preserved",
            FAIL,
            f"{scope}; need {counts}; {found}; {proof}{note}",
            problems_all,
            [str(p) for p in problems_all] + covered_lines,
            list(applied.values()),
        )
    return Result(
        "git-preserved",
        PASS,
        f"{scope}; need {counts} all covered; {proof}{note}",
        extra=covered_lines,
        waived=list(applied.values()),
    )


@dataclasses.dataclass
class Source:
    """One preservation source (a producer run or a manual copy) judged component by component."""

    name: str
    components: dict[ComponentKey, list[Problem]]
    note: str


def verifier_note(run: Path) -> str:
    """The producer's own verdict (first line of its RESULT.txt) and waiver count, surfaced but never trusted."""
    result = run / "RESULT.txt"
    if not result.is_file():
        return "no verifier RESULT.txt"
    lines = result.read_bytes().decode("utf-8", "replace").splitlines()
    verdict = lines[0].strip() if lines else "empty"
    waivers = next((ln.split(":", 1)[1].strip() for ln in lines if ln.startswith("WAIVERS:")), "")
    return f"verifier {verdict}" + (f", {waivers} producer waiver(s)" if waivers else "")


VERIFIED_RE = re.compile(r"^run=(?P<run>.+) verified_at=(?P<at>\S+)")  # verify-preserve.sh's second RESULT.txt line


def verifier_problem(ctx: Ctx, run: Path, start_ts: int) -> str:
    """INT-7: '' when the independent verifier (verify-preserve.sh) passed THIS run, else why the run does not count.
    RESULT.txt must be a regular file whose first line is exactly PASS and whose `run=<dir> verified_at=<UTC>` line
    names this run's directory and a time between the run's start and now. A `manifest_sha256=` line, when the
    verifier writes one, must equal the sha256 of the run's MANIFEST.tsv. Every artifact is still re-hashed here:
    the verdict gates a run, it never replaces the predicate's own checks."""
    result = run / "RESULT.txt"
    try:
        info = os.lstat(result)
    except FileNotFoundError:
        return "no verify-preserve RESULT.txt: a run counts only after the independent verifier has passed it"
    except OSError as exc:
        return f"the verifier's RESULT.txt cannot be read ({exc.strerror})"
    if not stat.S_ISREG(info.st_mode):
        return "the verifier's RESULT.txt is not a regular file"
    lines = result.read_bytes().decode("utf-8", "replace").splitlines()
    first = lines[0].strip() if lines else ""
    if first != "PASS":
        return f"the independent verifier's verdict is {one_line(first or 'empty', 40)!r}, not PASS"
    bound = next((m for ln in lines if (m := VERIFIED_RE.match(ln.strip()))), None)
    if bound is None:
        return "RESULT.txt has no `run=<dir> verified_at=<time>` line, so its PASS is not bound to any run"
    if os.path.basename(bound["run"].rstrip("/")) != run.name:
        return f"RESULT.txt verified {tilde(bound['run'])}, not this run ({run.name})"
    when = parse_attest_date(bound["at"])
    if when is None:
        return f"RESULT.txt verified_at {bound['at']!r} is not an ISO time"
    if when > ctx.now + FUTURE_SKEW_SEC:
        return f"RESULT.txt verified_at {bound['at']} is in the future"
    if start_ts and when < start_ts - FUTURE_SKEW_SEC:
        return f"RESULT.txt verified_at {bound['at']} is before the run began ({iso(start_ts)})"
    pinned = next((ln.split("=", 1)[1].strip().lower() for ln in lines if ln.startswith("manifest_sha256=")), "")
    if pinned and pinned != sha256_file(run / "MANIFEST.tsv"):
        return "the MANIFEST.tsv changed after the verifier passed it (manifest_sha256 differs)"
    return ""


def open_sources(ctx: Ctx) -> tuple[list[RunView], list[Path], list[tuple[str, list[str]]]]:
    """Discover producer runs and manual copies. Incomplete runs are set aside with their reasons, not trusted."""
    if ctx.preserve_runs:
        paths = list(ctx.preserve_runs)
    elif ctx.preserve_root.is_dir():
        paths = sorted(
            p
            for p in ctx.preserve_root.iterdir()
            if p.is_dir() and (RUN_RE.match(p.name) or p.name.startswith("manual-"))
        )
    else:
        paths = []
    views: list[RunView] = []
    manuals: list[Path] = []
    skipped: list[tuple[str, list[str]]] = []
    for path in paths:
        if (path / "MANIFEST.tsv").is_file() or RUN_RE.match(path.name):
            view = RunView(path, ctx)
            reasons = list(view.errors)
            if why := custody_problem(ctx, path):  # H2: a run on the Mac's own disk is not a backup
                reasons.append(why)
            if not view.errors and not view.complete():
                reasons.append("no skipped-list/credential-list rows (still running or cut short)")
            if not view.start_ts:
                reasons.append("directory name carries no UTC stamp")
            elif view.start_ts > ctx.now + FUTURE_SKEW_SEC:  # N3: a stamp ahead of now would silence every stale check
                reasons.append(f"directory name carries a UTC stamp in the future ({iso(view.start_ts)})")
            if not view.errors and (why := verifier_problem(ctx, path, view.start_ts)):  # INT-7
                reasons.append(why)
            if reasons:
                skipped.append((path.name, reasons))
            else:
                views.append(view)
        elif any(path.glob("*.MANIFEST.sha256")):
            manuals.append(path)
        else:
            skipped.append((path.name, ["neither a producer run nor a manual copy"]))
    return views, manuals, skipped


def need_keys(present: list[Need]) -> list[tuple[ComponentKey, Need]]:
    keys: dict[ComponentKey, Need] = {}
    for need in present:
        path = need.row["path"]
        if need.orphan:
            keys.setdefault(("orphan", path), need)
            continue
        if need.bundle and need.common:
            keys.setdefault(("bundle", need.common), need)
        if need.gitdir and need.common:
            keys.setdefault(("gitdir", need.common), need)
        if need.lfs_storage and need.common:
            keys.setdefault(("lfs-storage", need.common), need)
        if need.dirty:
            keys.setdefault(("dirty", path), need)
        if need.head:
            keys.setdefault(("head", path), need)
        if need.filtered:
            keys.setdefault(("filtered", path), need)
    return list(keys.items())


def settle_coverage(present: list[Need], sources: list[Source]) -> tuple[dict[ComponentKey, str], list[Problem]]:
    """A component is covered when ANY source covers it with no problem (staleness is judged per source).
    An uncovered component reports the problems of the source that came closest."""
    coverage: dict[ComponentKey, str] = {}
    uncovered: list[Problem] = []
    for key, need in need_keys(present):
        candidates = [(s, s.components[key]) for s in sources if key in s.components]
        hit = next((s for s, found in candidates if not found), None)
        if hit is not None:
            coverage[key] = hit.name
        elif not candidates:
            uncovered.append(
                Problem("manifest-missing", need.row["path"], f"no source evaluates the {key[0]} component")
            )
        else:
            # a source that merely lacks the item says less than one that evaluated it and found a defect (F8: the
            # operator must read why a manual copy was refused, not only that a run has no bundle item)
            best, found = min(candidates, key=lambda c: (all(p.code == "manifest-missing" for p in c[1]), len(c[1])))
            tag = f" [closest source: {best.name}]" if len(sources) > 1 else ""
            uncovered += [Problem(p.code, p.subject, p.message + tag) for p in found]
    return coverage, uncovered


def coverage_lines(present: list[Need], coverage: dict[ComponentKey, str]) -> list[str]:
    lines = []
    for need in present:
        path = need.row["path"]
        parts = [
            f"{kind}={coverage[key]}"
            for kind, ident in (
                ("orphan", path),
                ("bundle", need.common or ""),
                ("gitdir", need.common or ""),
                ("lfs-storage", need.common or ""),
                ("dirty", path),
                ("head", path),
                ("filtered", path),
            )
            if (key := (kind, ident)) in coverage
        ]
        if parts:
            lines.append(f"covered {tilde(path)}: " + " ".join(parts))
    return lines


def missing_objects(gitdir: str, shas: list[str]) -> list[str]:
    """Which of these objects are absent from a repository (git cat-file --batch-check; never fetches)."""
    if not shas:
        return []
    proc = subprocess.run(
        [*GIT_BASE, "--git-dir=" + gitdir, "cat-file", "--batch-check"],
        input=("\n".join(shas) + "\n").encode(),
        check=False,
        capture_output=True,
        env=git_env(),
        timeout=600,
    )
    must(proc, "cat-file --batch-check")  # H3: a git that cannot answer is not an answer of "nothing is missing"
    return [ln.split()[0] for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.endswith(" missing")]


class ManualSource:
    """A hand-made copy of repositories: `<dir>/<name>/` (working tree plus .git) and `<dir>/<name>.MANIFEST.sha256`."""

    def __init__(self, ctx: Ctx, directory: Path):
        self.ctx = ctx
        self.dir = directory
        self.hashed = 0
        self._manifests: dict[str, tuple[dict[str, str], list[str]]] = {}
        self._standalone: dict[str, list[str]] = {}

    def manifest(self, name: str) -> tuple[dict[str, str], list[str]]:
        """(relative path -> sha256, problems): the copy re-hashed against its manifest, once per copy."""
        if name not in self._manifests:
            raw, bad = parse_shasum_manifest(self.dir / f"{name}.MANIFEST.sha256")
            entries = [(sha, rel.removeprefix("./")) for sha, rel in raw]
            found, files, _nbytes = verify_hash_entries(self.dir / name, entries, self.ctx)
            self.hashed += files
            problems = [f"malformed manifest {b}" for b in bad] + found
            if not entries:
                problems.append("manifest has 0 entries")
            self._manifests[name] = ({rel: sha for sha, rel in entries}, problems)
        return self._manifests[name]

    def evaluate(self, present: list[Need]) -> dict[ComponentKey, list[Problem]]:
        components: dict[ComponentKey, list[Problem]] = {}
        for need in present:
            path = need.row["path"]
            name = os.path.basename(path)
            copy = self.dir / name
            manifest_file = self.dir / f"{name}.MANIFEST.sha256"
            if need.row["kind"] != "repo" or need.orphan or not manifest_file.is_file() or not (copy / ".git").is_dir():
                continue
            origin = run_git(["config", "--get", "remote.origin.url"], cwd=str(copy)).stdout.decode().strip()
            if (origin or "NONE") != need.row["remote"]:
                continue  # a same-named copy of some other repository
            taken = int(manifest_file.stat().st_mtime)
            entries, base = self.manifest(name)
            shared = [Problem("hash-mismatch", path, f"{self.dir.name}/{name}: {m}") for m in base]
            shared += self.borrow_problems(path, copy)
            try:
                if need.dirty:
                    components[("dirty", path)] = shared + self.dirty_problems(need, copy, entries, taken)
            except GitReadError as exc:
                components[("dirty", path)] = [Problem("git-error", path, str(exc))]
            try:
                if need.bundle and need.common:
                    components.setdefault(("bundle", need.common), shared + self.ref_problems(need, copy, taken))
            except GitReadError as exc:
                components.setdefault(("bundle", need.common or ""), [Problem("git-error", path, str(exc))])
        return components

    def borrow_problems(self, path: str, copy: Path) -> list[Problem]:
        """F8/C1-C3/H2a: a copy that is not standalone does not cover, however well its manifest re-hashes: one that
        borrows objects (alternates, any case), links its git dir, objects, packs or refs elsewhere (a recursive lstat
        walk, so a link at any depth counts), names another git dir (commondir), or sits on the Mac's own disk. Once
        the Mac is gone whatever it borrowed is gone with it. The verdict is read once per copy."""
        label = f"{self.dir.name}/{copy.name}"
        if copy.name not in self._standalone:
            self._standalone[copy.name] = self.standalone_problems(copy, label)
        return [Problem("manual-mismatch", path, why) for why in self._standalone[copy.name]]

    def standalone_problems(self, copy: Path, label: str) -> list[str]:
        out: list[str] = []
        if why := custody_problem(self.ctx, self.dir):
            out.append(f"{label}: not off the Mac: {why}")
        git = copy / ".git"
        try:
            kind = os.lstat(git).st_mode
        except OSError as exc:
            return [*out, f"{label}: .git cannot be read ({exc.strerror})"]
        if not stat.S_ISDIR(kind):  # C1: a link (or a gitfile) is read through, so the git data may be on the Mac
            what = "a symlink" if stat.S_ISLNK(kind) else "not a real directory"
            return [*out, f"{label}: .git is {what}, so the copy's git data can sit on the Mac"]
        findings = custody_git_findings(git)
        links = [where for found_kind, where, _detail in findings if found_kind == "symlink"]
        if links:  # one line however many links: a copy made of links is one defect
            more = f" (and {len(links) - 1} more)" if len(links) > 1 else ""
            out.append(f"{label}: {links[0]} is a symlink{more}")
        for found_kind, where, detail in findings:
            if found_kind == "alternates":
                out.append(f"{label} borrows objects via alternates ({where})")
            elif found_kind == "commondir":
                out.append(f"{label}: {where} names another git dir ({detail or 'empty'})")
            elif found_kind == "unreadable":
                out.append(f"{label}: {where} cannot be read ({detail}), so what it holds is unknown")
        if not findings and (why := custody_git_identity(str(copy))):
            out.append(f"{label}: {why}")
        return out

    def dirty_problems(self, need: Need, copy: Path, entries: dict[str, str], taken: int) -> list[Problem]:
        path = need.row["path"]
        cached = [
            n
            for n in must(run_git(["ls-files", "--cached", "-z"], cwd=path), "ls-files --cached").stdout.split(b"\0")
            if n
        ]
        untracked, _stats, err = current_untracked(path)
        if err:
            return [Problem("git-error", path, err)]
        live_root, copy_root = os.fsencode(path), os.fsencode(str(copy))
        absent: list[bytes] = []
        differ: list[bytes] = []
        newest = 0
        for name in sorted(set(cached) | set(untracked)):
            try:
                st = os.lstat(os.path.join(live_root, name))
            except OSError:
                continue
            if is_cred(name.decode("utf-8", "replace")):
                continue
            newest = max(newest, st.st_mtime_ns // 1_000_000_000)
            if stat.S_ISLNK(st.st_mode):
                twin = os.path.join(copy_root, name)
                if not os.path.islink(twin) or os.readlink(twin) != os.readlink(os.path.join(live_root, name)):
                    differ.append(name)
            elif stat.S_ISREG(st.st_mode):
                want = entries.get(name.decode("utf-8", "surrogateescape"))
                if want is None:
                    absent.append(name)
                elif sha256_file(os.path.join(live_root, name)) != want:
                    differ.append(name)
        problems: list[Problem] = []
        if absent:
            problems.append(
                Problem(
                    "manual-mismatch",
                    path,
                    f"{len(absent)} current file(s) not in the copy, e.g. {fmt_name(absent[0])}",
                )
            )
        if differ:
            problems.append(
                Problem("manual-mismatch", path, f"{len(differ)} file(s) differ, e.g. {fmt_name(differ[0])}")
            )
        if run_git(["rev-parse", "-q", "--verify", "HEAD"], cwd=path).returncode != 0:
            staged = must(run_git(["ls-files", "--stage", "-z"], cwd=path), "ls-files --stage").stdout.split(b"\0")
            shas = sorted({e.split(b"\t", 1)[0].split()[1].decode() for e in staged if b"\t" in e})
            if lost := missing_objects(str(copy / ".git"), shas):
                problems.append(
                    Problem("manual-mismatch", path, f"{len(lost)} staged blob(s) are not in the copy's git dir")
                )
        if newest > taken:
            problems.append(
                Problem(
                    "stale", path, f"newest dirty file at {iso(newest)} is newer than the copy's manifest {iso(taken)}"
                )
            )
        return problems

    def ref_problems(self, need: Need, copy: Path, taken: int) -> list[Problem]:
        path, common = need.row["path"], need.common or ""
        current = current_refs(common)
        theirs = current_refs(str(copy / ".git"))
        problems: list[Problem] = []
        lacking = [f"{n}@{s[:10]}" for n, s in sorted(current.items()) if theirs.get(n) != s]
        if lacking:
            problems.append(Problem("tip-missing", path, "the copy lacks the current tip of " + ", ".join(lacking[:3])))
        elif lost := missing_objects(str(copy / ".git"), sorted(set(current.values()))):
            problems.append(Problem("tip-missing", path, f"{len(lost)} tip commit(s) are not in the copy's git dir"))
        try:  # the COPY's reflog: unreadable is a defect of the copy, reported beside the others, never a pass
            kept: set[str] | None = set(stash_shas(str(copy / ".git")))
        except GitReadError as exc:
            problems.append(Problem("stash-unreadable", path, f"the copy's stash reflog cannot be read: {exc}"))
            kept = None
        # the LIVE repository's stash list stays fail-closed (H3): a GitReadError here propagates
        if kept is not None and (dropped := [sha for sha in stash_shas(common) if sha not in kept]):  # F8
            problems.append(
                Problem(
                    "stash-missing", path, f"{len(dropped)} live stash entr(ies) are not in the copy's stash reflog"
                )
            )
        if (newest := newest_commit_ts(common, path)) > taken:
            problems.append(Problem("stale", path, f"newest commit at {iso(newest)} is newer than the copy's manifest"))
        return problems


# ----------------------------------------------------------------------------------------------------
# check: no-external-dependency
# ----------------------------------------------------------------------------------------------------
def points_into_mac(target: str, roots: list[str]) -> bool:
    """Does a path NAME the Mac's home area (spelling only: case-folded, firmlink alias stripped)? Used for gitfiles
    whose target is gone, so they can be counted as orphans; a target that exists is judged by its device instead."""
    norm = os.path.normpath(target).casefold()
    if any(norm == r.casefold() or norm.startswith(r.rstrip("/").casefold() + "/") for r in roots):
        return False
    firm = "/system/volumes/data"
    if norm.startswith(firm + "/"):
        norm = norm[len(firm) :]
    prefixes = [p.casefold() for p in MAC_PREFIXES]
    return any(norm == p or norm.startswith(p + "/") for p in prefixes)


def dependency_state(ctx: Ctx, target: str, volume_devices: set[int], roots: list[str]) -> str:
    """F4: 'live' when the target exists on a device that is none of the scanned external volumes (the Mac's disk, or
    any other disk that will not be there), 'orphan' when it names the Mac but is already gone, '' otherwise.
    The target is resolved through every symlink first, and judged by device, so spelling (/users, the firmlink
    alias, 'Macintosh HD') cannot hide it. A target that cannot be examined is treated as live: fail closed."""
    real = os.path.realpath(target)
    try:
        device = ctx.device_of(real)
    except FileNotFoundError:
        return "orphan" if points_into_mac(real, roots) or points_into_mac(target, roots) else ""
    except OSError:
        return "live"
    return "" if device in volume_devices else "live"


def git_pointers(entry: str, kind: str) -> list[tuple[str, str]]:
    """The paths a .git entry, an alternates file or a commondir file points at: [(kind, absolute target)].
    Raises OSError when the entry cannot be read (the caller reports it as scan-incomplete)."""
    here = os.path.dirname(entry)
    if kind == "git":
        if os.path.islink(entry):
            return [("symlink", os.path.join(here, os.readlink(entry)))]
        if not os.path.isfile(entry):
            return []
        with open(entry, "rb") as handle:
            first = handle.read(4096).split(b"\n", 1)[0].decode("utf-8", "replace").strip()
        if not first.startswith("gitdir:"):
            return []
        target = first[len("gitdir:") :].strip()
        return [("gitfile", target if os.path.isabs(target) else os.path.join(here, target))]
    if kind in ("config", "config.worktree"):  # X3: core.worktree names the work tree whose uncommitted edits git reads
        proc = run_git(["config", "--file", entry, "--get-all", "core.worktree"])
        if proc.returncode == 1:
            return []  # the key is absent
        if proc.returncode != 0:
            raise OSError(errno.EIO, f"git config cannot read it ({err_tail(proc)})")
        values = [v.strip() for v in proc.stdout.decode("utf-8", "surrogateescape").splitlines() if v.strip()]
        return [("worktree", v if os.path.isabs(v) else os.path.join(here, v)) for v in values]
    with open(entry, "rb") as handle:
        lines = [ln.strip() for ln in handle.read().decode("utf-8", "replace").splitlines()]
    base = os.path.dirname(here) if kind == "alternates" else here  # alternates entries are relative to objects/
    return [
        (kind, ln if os.path.isabs(ln) else os.path.join(base, ln)) for ln in lines if ln and not ln.startswith("#")
    ]


def in_git_dir(entry: str) -> bool:
    """Is this regular file a member of a git dir (a .git directory, a bare repository or a worktrees/* admin dir)? A
    git dir has a HEAD, and an object store or a commondir; a worktrees/* admin dir and a .git directory are git dirs
    by position alone (their HEAD may be missing, which git does not forgive but a copy can show). A file that only
    shares the name has none of these."""
    here = os.path.dirname(entry)
    if not os.path.isfile(entry):
        return False
    if os.path.basename(entry).casefold() == "commondir" and (
        os.path.basename(here).casefold() == ".git" or os.path.basename(os.path.dirname(here)).casefold() == "worktrees"
    ):
        return True
    return os.path.lexists(os.path.join(here, "HEAD")) and (
        os.path.isdir(os.path.join(here, "objects")) or os.path.lexists(os.path.join(here, "commondir"))
    )


def find_git_entries(root: str, depth: int) -> tuple[list[str], str]:
    """Every .git entry (file, symlink or directory; case-insensitive), objects/info/alternates and
    worktrees/*/commondir under a volume, without descending into object stores. Returns (paths, error)."""
    prune: list[str] = ["("]
    for index, name in enumerate(PRUNE_NAMES):
        prune += (["-o"] if index else []) + ["-name", name]
    prune += [")", "-prune", "-o"]
    stores = ["(", "-path", "*/.git/objects/??", "-o", "-path", "*.git/objects/??", "-o"]
    stores += ["-path", "*/.git/objects/pack", "-o", "-path", "*.git/objects/pack", ")", "-prune", "-o"]
    # X1-X3: every spelling (-ipath/-iname) of alternates, of commondir at ANY depth (a .git or bare directory's own
    # commondir, not only a worktrees/*/ one) and of the config files that can carry core.worktree; the caller keeps
    # only those whose parent really is a git dir
    wanted = ["(", "-iname", ".git", "-o", "-ipath", "*/objects/info/alternates", "-o", "-iname", "commondir", "-o"]
    wanted += ["-iname", "config", "-o", "-iname", "config.worktree", ")", "-print0"]
    bound = ["-maxdepth", str(depth)] if depth > 0 else []
    try:
        proc = subprocess.run(
            ["find", root, "-xdev", *bound, *prune, *stores, *wanted],
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=1800,
        )
        if proc.returncode != 0 or proc.stderr.strip():
            tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[:1]
            return [], "find reported errors: " + (tail[0] if tail else f"rc={proc.returncode}")
        if depth > 0:  # a bound is honest only if nothing lies below it
            below = subprocess.run(
                ["find", root, "-xdev", "-mindepth", str(depth + 1), "-maxdepth", str(depth + 1), "-print", "-quit"],
                check=False,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                timeout=1800,
            )
            if below.returncode != 0 or below.stderr.strip():
                return [], "find reported errors while probing below the depth bound"
            if below.stdout.strip():
                return [], f"scan-truncated: entries exist below the depth bound {depth}, which the scan never read"
    except subprocess.TimeoutExpired:
        return [], "find timed out; the scan is incomplete"
    return [os.fsdecode(p) for p in proc.stdout.split(b"\0") if p], ""


def check_no_external_dependency(ctx: Ctx) -> Result:
    problems: list[Problem] = []
    roots = [str(ctx.volumes_root / name) for name in ctx.externals]
    scanned = gitfiles = pointers = orphaned = worktrees = 0
    volume_devices: set[int] = set()
    media_ok: dict[str, bool] = {}
    for root in roots:  # every scanned EXTERNAL volume counts as "not the Mac", whichever one a pointer is found on
        if os.path.isdir(root) and ctx.is_mount(root):
            media_ok[root] = media_for(ctx, root).external  # H2a: an internal volume or an image on the Mac is the Mac
            if media_ok[root]:
                with contextlib.suppress(OSError):
                    volume_devices.add(ctx.device_of(root))
    for name, root in zip(ctx.externals, roots, strict=True):
        if not os.path.isdir(root) or not ctx.is_mount(root):
            problems.append(
                Problem("not-mounted", root, f"volume {name} is not mounted; cannot prove it is independent")
            )
            continue
        if not media_ok[root]:
            problems.append(
                Problem(
                    "not-external",
                    root,
                    f"volume {name} is not on an external disk ({media_for(ctx, root).why}), so it goes with the Mac",
                )
            )
            continue
        found, error = find_git_entries(root, ctx.gitfile_depth)
        if error:
            code = "scan-truncated" if error.startswith("scan-truncated") else "scan-incomplete"
            problems.append(Problem(code, root, error.removeprefix("scan-truncated: ")))
            continue
        scanned += 1
        for entry in found:
            base = os.path.basename(entry).lower()
            kind = "git" if base == ".git" else base  # alternates | commondir | config | config.worktree
            if kind in ("commondir", "config", "config.worktree") and not in_git_dir(entry):
                continue  # a file that merely has that name, outside any git dir
            try:
                targets = git_pointers(entry, kind)
            except OSError as exc:
                problems.append(Problem("scan-incomplete", entry, f"unreadable: {exc.strerror}"))
                continue
            gitfiles += sum(1 for k, _t in targets if k == "gitfile")
            pointers += sum(1 for k, _t in targets if k in ("alternates", "commondir"))
            worktrees += sum(1 for k, _t in targets if k == "worktree")
            for what, target in targets:
                state = dependency_state(ctx, target, volume_devices, roots)
                if state == "live":
                    # the Mac-side object store or admin dir exists: this works today and breaks on the erase
                    problems.append(
                        Problem(
                            "mac-dependency",
                            entry,
                            f"LIVE: {what} points at {os.path.realpath(target)}, which exists outside the volumes",
                        )
                    )
                elif state == "orphan":
                    orphaned += 1  # the target is already gone: nothing can be converted, nothing will break
    for name in discover_externals(ctx.volumes_root, ctx.is_mount, ctx.device_of, ctx.home, ctx.media_of):
        if name not in ctx.externals:
            problems.append(
                Problem("volume-unscanned", str(ctx.volumes_root / name), f"volume {name} is mounted but not scanned")
            )
    if scanned == 0 and not problems:
        problems.append(Problem("no-volumes", str(ctx.volumes_root), "no external volume was scanned"))
    info = (
        [
            f"{orphaned} gitfile(s) already point at a Mac admin directory that no longer exists "
            "(orphaned: nothing to convert, not a dependency)"
        ]
        if orphaned
        else []
    )
    live = len([p for p in problems if p.code == "mac-dependency"])
    if problems:
        examples = " | ".join(str(p) for p in problems[:3])
        more = f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""
        return Result(
            "no-external-dependency",
            FAIL,
            f"{live} LIVE worktree(s) depend on the Mac ({len(problems) - live} other problem(s)), {orphaned} orphaned "
            f"(INFO), {gitfiles} gitfiles and {pointers} alternates/commondir files read over "
            f"{len(ctx.externals)} volume(s): {examples}{more}",
            problems,
            [str(p) for p in problems],
            info=info,
        )
    return Result(
        "no-external-dependency",
        PASS,
        f"{gitfiles} gitfile(s) and {pointers} alternates/commondir file(s) on {scanned} mounted volume(s) "
        f"({', '.join(ctx.externals)}): none depends on a live Mac admin directory, object store or work tree "
        f"({orphaned} orphaned, {worktrees} core.worktree setting(s) read)",
        info=info,
    )


# ----------------------------------------------------------------------------------------------------
# check: t7-unique-consolidated
# ----------------------------------------------------------------------------------------------------
def check_t7_unique(ctx: Ctx) -> Result:
    manifest = ctx.t7_unique / "MANIFEST.sha256"
    if not manifest.is_file():
        return Result("t7-unique-consolidated", FAIL, f"no MANIFEST.sha256 in {tilde(str(ctx.t7_unique))}")
    entries, bad = parse_shasum_manifest(manifest)
    problems = [f"malformed manifest {b}" for b in bad]
    if not entries:
        problems.append("manifest has 0 entries")
    if not ctx.is_mount(str(ctx.t7_source)):
        problems.append(f"{ctx.t7_source.name} is not mounted: cannot prove the originals are still there")
    if why := custody_problem(ctx, ctx.t7_unique):  # H2a: the copy itself, even when its manifest lists nothing
        problems.append(f"copy root not off the Mac: {why}")
    copy_problems, files, nbytes = verify_hash_entries(ctx.t7_unique, entries, ctx)
    problems += [f"copy {p}" for p in copy_problems]
    originals = 0
    if ctx.is_mount(str(ctx.t7_source)):
        for sha, rel in entries:
            if not safe_rel(rel):
                continue
            src, dst = ctx.t7_source / rel, ctx.t7_unique / rel
            if not src.is_file():
                problems.append(f"original missing on {ctx.t7_source.name}: {rel}")
            elif dst.is_file() and src.stat().st_size != dst.stat().st_size:
                problems.append(f"original size differs: {rel}")
            elif ctx.hash_t7_originals and sha256_file(src) != sha:
                problems.append(f"original sha256 differs: {rel}")
            else:
                originals += 1
    if problems:
        more = f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""
        return Result(
            "t7-unique-consolidated",
            FAIL,
            f"{len(problems)} problem(s): " + " | ".join(problems[:3]) + more,
            extra=problems,
        )
    how = (
        "re-hashed equal to the manifest"
        if ctx.hash_t7_originals
        else "checked by existence and size only, NOT re-hashed (--hash-t7-originals to hash them)"
    )
    return Result(
        "t7-unique-consolidated",
        PASS,
        f"{files} files ({nbytes} bytes) re-hashed equal on the external; "
        f"{originals} originals present on {ctx.t7_source.name}, {how}",
    )


# ----------------------------------------------------------------------------------------------------
# check: nongit-homed
# ----------------------------------------------------------------------------------------------------
def resolve_run_dir(path: Path) -> Path | None:
    if not path.is_dir():
        return None
    if (path / "RESULT.txt").is_file():
        return path
    return newest_run(path) or path


def check_nongit_homed(ctx: Ctx) -> Result:
    """Every configured homing set (a run dir, or the parent of run-* dirs) must have a PASS run that re-hashes."""
    results = [check_nongit_set(base, ctx) for base in ctx.nongit_runs]
    if not results:
        return Result("nongit-homed", FAIL, "no non-git run directory is configured")
    status = FAIL if any(r.status == FAIL for r in results) else PASS
    extra = [line for r in results for line in r.extra]
    return Result("nongit-homed", status, " || ".join(r.detail for r in results), extra=extra)


SQLITE_MAGIC = b"SQLite format 3\x00"
SQLITE_SIDECARS = ("-wal", "-shm", "-journal")
NONGIT_SF_DATALESS = 0x40000000  # the flag the homing tool lists a File Provider / iCloud placeholder by


def is_sqlite_copy(path: Path) -> bool:
    """Does this file start with the SQLite header? The homing tool snapshots such files with .backup, which rewrites
    them (journal mode, page layout), so their size need not equal the live file's."""
    try:
        with open(path, "rb") as handle:
            return handle.read(16) == SQLITE_MAGIC
    except OSError:
        return False


@dataclasses.dataclass
class HomingItem:
    """One row of the homing tool's items TSV: what was copied (source), where it landed (dest_rel) and what it skips."""

    name: str
    source: str
    dest_rel: str
    globs: tuple[str, ...]
    carve: frozenset[str]


def parse_homing_items(path: Path, home: str) -> tuple[list[HomingItem], str]:
    """The items file a non-git homing run was made from: (items, error). Same format as the tool reads."""
    try:
        text = path.read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        return [], f"cannot read the items file {path.name}: {exc.strerror}"
    items: list[HomingItem] = []
    for lineno, raw in enumerate(text.split("\n"), start=1):
        line = raw.rstrip("\r")
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if not 3 <= len(parts) <= 4 or not all(parts[:3]):
            return [], f"{path.name} line {lineno} is not 'name, source_dir, dest_rel[, exclude_globs]'"
        source = parts[1]
        if source.startswith("$HOME/"):
            source = home + source[len("$HOME") :]
        elif source.startswith("~/"):
            source = home + source[1:]
        globs = [g for g in (parts[3].split(";") if len(parts) == 4 else []) if g]
        items.append(
            HomingItem(
                parts[0],
                os.path.normpath(source),
                os.path.normpath(parts[2]),
                tuple(g for g in globs if not g.startswith("=")),
                frozenset(g[1:] for g in globs if g.startswith("=")),
            )
        )
    return items, "" if items else f"{path.name} lists no item"


def bind_items(ctx: Ctx, entries: list[str]) -> tuple[list[HomingItem], str]:
    """The items file a run was made from: every manifest entry maps to an item and every item has an entry."""
    why: list[str] = []
    for file in ctx.nongit_items:
        items, error = parse_homing_items(file, ctx.home)
        if error:
            why.append(error)
            continue
        hit: dict[str, int] = {i.name: 0 for i in items}
        unmapped = 0
        for rel in entries:
            owner = max(
                (i for i in items if rel == i.dest_rel or rel.startswith(i.dest_rel + "/")),
                key=lambda i: len(i.dest_rel),
                default=None,
            )
            if owner is None:
                unmapped += 1
            else:
                hit[owner.name] += 1
        empty = [n for n, c in hit.items() if not c]
        if not unmapped and not empty:
            return items, ""
        why.append(f"{file.name}: {unmapped} manifest entr(ies) map to no item, {len(empty)} item(s) have no entry")
    return [], "no --nongit-items file matches this run (" + ("; ".join(why) or "none was given") + ")"


def live_source_problems(ctx: Ctx, run: Path, entries: list[str]) -> list[str]:
    """H5: the homed copy is compared with the LIVE source, not with its own manifest. A source file that exists and
    changed since the run (size, or a newer mtime than the run's UTC stamp) is not homed in its current form, and a
    live file that is in neither the manifest nor EXCLUDED.tsv was never homed at all."""
    items, error = bind_items(ctx, entries)
    if error:
        return [error]
    match = RUN_RE.match(run.name)
    stamp = (
        datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).timestamp()
        if match
        else (run / "RESULT.txt").stat().st_mtime
    )
    if match and stamp > ctx.now + FUTURE_SKEW_SEC:  # N3: a run stamped ahead of now would switch the mtime compare off
        return [f"the run's UTC stamp {iso(stamp)} is in the future, so no source file can be compared with it"]
    excluded = excluded_rows(run)
    bad_exclusions: list[str] = []
    unreadable: list[str] = []

    def unreadable_dir(exc: OSError) -> None:  # N1: a directory that cannot be listed is not a directory with nothing in it
        if not isinstance(exc, FileNotFoundError):
            unreadable.append(f"{exc.filename or '?'} ({exc.strerror})")

    def honoured(full: str, rel: str, item: HomingItem) -> bool:
        """N2: an EXCLUDED.tsv row spares a live path from the compare only when the row is true of that path NOW."""
        kind = excluded.get(full)
        if kind is None:
            return False
        if why := excluded_row_problem(kind, full, rel, item):
            bad_exclusions.append(f"{tilde(full)} listed as {kind}: {why}")
            return False
        return True

    homed = set(entries)
    changed: list[str] = []
    added: list[str] = []
    for item in items:
        single = os.path.isfile(item.source) and not os.path.islink(item.source)
        for rel in entries:
            if rel != item.dest_rel and not rel.startswith(item.dest_rel + "/"):
                continue
            live = item.source if single else os.path.join(item.source, rel[len(item.dest_rel) + 1 :])
            try:
                st = os.lstat(live)
            except FileNotFoundError:
                continue  # gone from the Mac after the run: the copy holds it, nothing is lost
            except OSError as exc:  # N1: unreadable is not gone
                unreadable.append(f"{live} ({exc.strerror})")
                continue
            try:
                copy = (run / rel).stat()
            except OSError:
                continue  # the copy's own defect is reported by its hash check
            resized = st.st_size != copy.st_size and not is_sqlite_copy(run / rel)
            if resized or st.st_mtime > stamp + 1:
                changed.append(live)
        if single:
            continue
        for current, dirs, names in os.walk(item.source, onerror=unreadable_dir):
            relative = os.path.relpath(current, item.source)
            dirs[:] = [
                d
                for d in dirs
                if not any(
                    fnmatch.fnmatchcase(d, g) or fnmatch.fnmatchcase(os.path.normpath(os.path.join(relative, d)), g)
                    for g in item.globs
                )
                and not (relative == "." and d in item.carve)
                and not honoured(os.path.join(current, d), os.path.normpath(os.path.join(relative, d)), item)
            ]
            for name in names:
                full = os.path.join(current, name)
                sub = os.path.normpath(os.path.join(relative, name))
                if (
                    honoured(full, sub, item)
                    or os.path.islink(full)
                    or not os.path.isfile(full)
                    or is_cred(sub)
                    or any(fnmatch.fnmatchcase(name, g) or fnmatch.fnmatchcase(sub, g) for g in item.globs)
                    or (relative == "." and name in item.carve)
                ):
                    continue
                if name.endswith(SQLITE_SIDECARS) and posixpath_join(item.dest_rel, sub.rsplit("-", 1)[0]) in homed:
                    # the tool never copies the sidecars of a database it snapshotted; a sidecar written after
                    # the run means the database changed after it
                    if os.lstat(full).st_mtime > stamp + 1:
                        changed.append(full)
                    continue
                if posixpath_join(item.dest_rel, sub) not in homed:
                    added.append(full)
    out = []
    if unreadable:
        out.append(
            f"{len(unreadable)} source path(s) cannot be read, so what they hold was not compared, "
            f"e.g. {unreadable[0] if '/' not in unreadable[0] else tilde(unreadable[0])}"
        )
    if bad_exclusions:
        out.append(
            f"{len(bad_exclusions)} EXCLUDED.tsv row(s) are not true of the live source (the list is the run's own and "
            f"unhashed, so a row spares a path only when it holds now), e.g. {bad_exclusions[0]}"
        )
    if changed:
        out.append(f"{len(changed)} source file(s) changed since the run, e.g. {tilde(changed[0])}")
    if added:
        out.append(
            f"{len(added)} source file(s) were never homed (not in the manifest or EXCLUDED.tsv), e.g. {tilde(added[0])}"
        )
    return out


def tsv_unescape(cell: str) -> str:
    """Undo the homing tool's tsv_cell escaping of backslash, tab, newline and carriage return."""
    return re.sub(r"\\(.)", lambda m: {"t": "\t", "n": "\n", "r": "\r", "\\": "\\"}.get(m.group(1), m.group(0)), cell)


def excluded_rows(run: Path) -> dict[str, str]:
    """EXCLUDED.tsv of a non-git run: source path -> the kind the tool wrote (kind, source_path, bytes, reason)."""
    listing = run / "EXCLUDED.tsv"
    rows: dict[str, str] = {}
    if listing.is_file():
        for raw in listing.read_bytes().decode("utf-8", "surrogateescape").split("\n")[1:]:
            parts = raw.split("\t")
            if len(parts) > 1:
                rows[tsv_unescape(parts[1])] = parts[0].strip()
    return rows


# Ported verbatim from nongit_homing.py (the homing tool's credential names): an EXCLUDED.tsv row that claims a
# credential is true only when the name really matches one of these, or the predicate's own credential patterns.
NONGIT_CRED_FILE_GLOBS = (
    ".env .env.* *.env .netrc _netrc .npmrc .pypirc .git-credentials id_rsa* id_dsa* id_ecdsa* id_ed25519* *.pem "
    "*.p12 *.pfx *.key *.keychain *.keychain-db *.kdbx *.jks *.ppk secring.* pubring.kbx trustdb.gpg credentials "
    "credentials.json client_secret*.json service-account*.json auth.json token token.json tokens.json *-tokens.json "
    "*_tokens.json *.token *token_cache*.json session.json cookies cookies-journal cookies.sqlite login?data* "
    "web?data* logins.json key3.db key4.db *.secret *.secrets secrets.* secret.* .claude.json legacy-home.json "
    "mcp.json .mcp.json config.toml config.toml.bak-* claude_desktop_config.json* .credentials.json "
    "*.credentials.json installation_id ant-did"
).split()
NONGIT_CRED_DIR_GLOBS = (
    ".ssh .gnupg .aws .azure .kube .docker .electrum .secrets keychains *1password* private-keys-v1.d .config/gh "
    ".gcloud .moneta"
).split()


def excluded_row_problem(kind: str, full: str, rel: str, item: HomingItem) -> str:
    """N2: why an EXCLUDED.tsv row is not true of the live path (''), judged by the kind the homing tool writes:
    dataless-placeholder (the dataless flag is set NOW), special-file (a socket, fifo or device), credential-file /
    credential-dir (the name matches a credential pattern) and item-excluded (the item's own exclude globs)."""
    try:
        st = os.lstat(full)
    except FileNotFoundError:
        return ""  # nothing is there to compare
    except OSError as exc:
        return f"cannot be examined ({exc.strerror})"
    return excluded_stat_problem(kind, st, os.path.basename(full).lower(), rel, item)


def excluded_stat_problem(kind: str, st: os.stat_result, name: str, rel: str, item: HomingItem) -> str:
    """excluded_row_problem for a stat already in hand (st_mode and st_flags are all it reads)."""
    family = kind.split("-")[0].lower()
    mode = st.st_mode
    if family == "dataless":
        flagged = stat.S_ISREG(mode) and getattr(st, "st_flags", 0) & NONGIT_SF_DATALESS
        return "" if flagged else "it is not a dataless placeholder now: its bytes are readable and were never homed"
    if family == "special":
        return "" if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode) or stat.S_ISLNK(mode)) else "it is not special"
    if family == "credential":
        low = rel.lower()
        if stat.S_ISDIR(mode):
            hit = any(d in CRED_DIRS for d in low.split("/")) or any(
                fnmatch.fnmatchcase(name, g)
                or fnmatch.fnmatchcase(low, g)
                or ("/" in g and ("/" + low).endswith("/" + g))
                for g in NONGIT_CRED_DIR_GLOBS
            )
        else:
            hit = is_cred(rel) or any(fnmatch.fnmatchcase(name, g) for g in NONGIT_CRED_FILE_GLOBS)
        return "" if hit else "its name matches no credential pattern"
    if family == "item":
        base = os.path.basename(rel)
        hit = any(
            g and (fnmatch.fnmatchcase(rel, g) or fnmatch.fnmatchcase(base, g) or rel.startswith(g.rstrip("/") + "/"))
            for g in item.globs
        )
        return "" if hit else "it matches none of the item's exclude globs"
    return f"{kind!r} is not a kind the homing tool writes"


def posixpath_join(base: str, rel: str) -> str:
    return os.path.normpath(os.path.join(base, rel))


RESULT_DATA_PREFIXES = ("excluded[", "excluded_overflow=", "item[", "sqlite_store=", "run_dir=")  # paths and names
RESULT_COUNTERS = ("errors", "drift", "missing", "mismatch")  # the homing tool's own failure counters
RESULT_FAILING_WORD = re.compile(r"(?i)(fail\w*|error\w*|partial\w*)\b")
RESULT_KEYED = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)\s*[:=]\s*(.*)$")


def result_verdict_problem(lines: list[str]) -> str:
    """H5/N4: RESULT.txt is a PASS only if nothing in it says otherwise, in any spelling. 'PASS' on line 1 does not
    outvote a later verdict: every `RESULT:` tag must be exactly 'RESULT: PASS'; a result/verdict/status line in another
    case or key must say PASS; a line that opens with fail/error/partial, a problem(s)= line and a non-zero failure
    counter (errors= drift= missing= mismatch=) are failures wherever they sit. Lines that merely carry paths and names
    (excluded[..], item[..], sqlite_store=, run_dir=) are data, not verdicts."""
    stripped = [ln.strip() for ln in lines if ln.strip()]
    first = stripped[0] if stripped else ""
    tags = [ln for ln in stripped if ln.startswith("RESULT:")]
    for ln in stripped:
        if ln.startswith(RESULT_DATA_PREFIXES) or ln.startswith("RESULT:"):
            continue
        keyed = RESULT_KEYED.match(ln)
        key, value = (keyed.group(1).lower(), keyed.group(2).strip()) if keyed else ("", "")
        if key in RESULT_COUNTERS and value.isdigit():
            if int(value) != 0:
                return f"RESULT.txt carries a failure counter: {ln!r}"
        elif key.startswith("problem") or RESULT_FAILING_WORD.match(ln):
            return f"RESULT.txt carries a failing line: {one_line(ln, 80)!r}"
        elif key in ("result", "verdict", "status") and value != "PASS":
            return f"RESULT.txt carries a verdict that is not exactly PASS: {one_line(ln, 80)!r}"
    if any(t != "RESULT: PASS" for t in tags):
        return f"RESULT.txt carries a non-PASS tag: {next(t for t in tags if t != 'RESULT: PASS')!r}"
    if first != "PASS" and not tags:
        return f"RESULT.txt verdict is not PASS (first line {first!r}, no RESULT: tag)"
    return ""


def check_nongit_set(base: Path, ctx: Ctx | None = None) -> Result:
    run = resolve_run_dir(base)
    if run is None:
        return Result("nongit-homed", FAIL, f"non-git run directory {tilde(str(base))} does not exist")
    label = base.name if run == base else f"{base.name}/{run.name}"
    result_file = run / "RESULT.txt"
    if not result_file.is_file():
        where = f"{label} has" if run != base else f"no run-* directory under {tilde(str(run))} has"
        return Result("nongit-homed", FAIL, f"{where} a RESULT.txt")
    lines = result_file.read_bytes().decode("utf-8", "replace").splitlines()
    problems: list[str] = []
    if verdict := result_verdict_problem(lines):
        problems.append(verdict)
    reported = [ln.strip() for ln in lines if ln.strip().startswith("problem=")]
    if reported:
        problems.append(f"RESULT.txt lists {len(reported)} problem= line(s), e.g. {one_line(reported[0], 120)}")
    if ctx is not None and (why := custody_problem(ctx, run)):
        problems.append(f"not off the Mac: {why}")
    entries: list[tuple[str, str]] = []
    sha_manifest, tsv_manifest = run / "MANIFEST.sha256", run / "MANIFEST.tsv"
    if sha_manifest.is_file():
        entries, bad = parse_shasum_manifest(sha_manifest)
        problems += [f"malformed manifest {b}" for b in bad]
    elif tsv_manifest.is_file():
        rows = tsv_manifest.read_bytes().decode("utf-8", "surrogateescape").split("\n")
        header = rows[0].split("\t")
        if "sha256" not in header or not ({"rel_path", "file", "path"} & set(header)):
            problems.append("MANIFEST.tsv has no sha256/path columns")
        else:
            si = header.index("sha256")
            pi = header.index(next(c for c in ("rel_path", "file", "path") if c in header))
            entries = [(r.split("\t")[si].lower(), r.split("\t")[pi]) for r in rows[1:] if r]
    else:
        problems.append("no MANIFEST.sha256 or MANIFEST.tsv")
    if not entries and not any("manifest" in p.lower() for p in problems):
        problems.append("manifest has 0 entries")
    hash_problems, files, nbytes = verify_hash_entries(run, entries, ctx)
    problems += hash_problems
    if ctx is not None and entries:
        problems += live_source_problems(ctx, run, [rel.removeprefix("./") for _sha, rel in entries])
    if problems:
        more = f" (+{len(problems) - 3} more)" if len(problems) > 3 else ""
        return Result(
            "nongit-homed",
            FAIL,
            f"{label}: {len(problems)} problem(s): " + " | ".join(problems[:3]) + more,
            extra=problems,
        )
    excluded = run / "EXCLUDED.tsv"
    left_out = max(len(excluded.read_bytes().splitlines()) - 1, 0) if excluded.is_file() else 0
    note = (
        f"; {left_out} credential/dataless/special entr(ies) listed in EXCLUDED.tsv were not copied" if left_out else ""
    )
    return Result(
        "nongit-homed",
        PASS,
        f"{label}: RESULT PASS, {files} manifest entries ({nbytes} bytes) re-hashed equal and matching the live "
        f"source{note}",
    )


# ----------------------------------------------------------------------------------------------------
# check: credentials-routed, backblaze-offsite, human-erase
# ----------------------------------------------------------------------------------------------------
def check_credential_registry(ctx: Ctx) -> Result:
    """The registry is complete (credential-wall.py --check). This proves every credential kind has a home in code,
    NOT that the Mac's own credential-route items are held there: that is credential-route-items-homed."""
    cid = "credential-registry-complete"
    script = ctx.credential_wall
    if not script.is_file():
        return Result(cid, UNPROVEN, f"{script.name} not found at {tilde(str(script))}; cannot prove the registry")
    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--check"],
            check=False,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return Result(cid, FAIL, f"{script.name} --check timed out after 180s")
    out = proc.stdout.decode("utf-8", "replace").strip().splitlines()
    err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
    last = out[-1] if out else (err[-1] if err else f"rc={proc.returncode}")
    if proc.returncode == 0:
        return Result(cid, PASS, f"{script.name} --check exit 0 (registry only): {one_line(last, 160)}")
    note = (
        " (interpreter import failure, not a registry verdict)"
        if any("Error" in e and "import" in e.lower() for e in err)
        else ""
    )
    return Result(cid, FAIL, f"{script.name} --check exit {proc.returncode}{note}: {one_line(last, 160)}")


ITEM_RE = re.compile(r"^(?P<name>\S.*?)\s+held-by:\s*(?P<holder>organ|1Password|released)\s+(?P<date>\S+)\s*$")


def credential_leftovers(ctx: Ctx) -> int:
    """How many credential-pattern files the preserve runs and the non-git homing deliberately left out (names only)."""
    left = 0
    runs = ctx.preserve_runs or (sorted(ctx.preserve_root.glob("run-*")) if ctx.preserve_root.is_dir() else [])
    for path in runs:
        listing = path / "dirty" / "credential-skipped.txt"
        if listing.is_file():
            left += len([ln for ln in listing.read_bytes().splitlines() if ln.strip()])
    for base in ctx.nongit_runs:  # N2: a credential the non-git homing left out is just as unhomed (names only)
        if (run := resolve_run_dir(base)) is not None:
            left += sum(1 for kind in excluded_rows(run).values() if kind.startswith("credential"))
    return left


def check_credential_route_items(ctx: Ctx) -> Result:
    """Credential-route items (keys, tokens, .env originals, wallets, keychain exports) are never read by this
    predicate and cannot be derived: they stay UNPROVEN until the owner lists where each one is held (names only)."""
    cid = "credential-route-items-homed"
    path = ctx.credential_attestation
    left = credential_leftovers(ctx)
    cover = (
        f"; {left} credential-pattern file(s) were left out of git snapshots or non-git homing and must be named"
        if left
        else ""
    )
    need = "the owner must list each item as '<name> held-by: <organ|1Password|released> <ISO date>' (names only)"
    if path is None or not path.is_file():
        return Result(cid, UNPROVEN, f"no credential attestation file ({need}){cover}")
    items = 0
    for lineno, raw in enumerate(path.read_bytes().decode("utf-8", "replace").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = ITEM_RE.match(line)
        if match is None:
            return Result(
                cid, UNPROVEN, f"{path.name} line {lineno} is not '<name> held-by: <holder> <ISO date>'{cover}"
            )
        if parse_attest_date(match.group("date")) is None:
            return Result(cid, UNPROVEN, f"{path.name} line {lineno} has a non-ISO date {match.group('date')!r}{cover}")
        if is_future(match.group("date"), ctx.now):
            return Result(cid, UNPROVEN, f"{path.name} line {lineno} is dated in the future{cover}")
        items += 1
    if items == 0:
        return Result(cid, UNPROVEN, f"{path.name} names no item ({need}){cover}")
    return Result(
        cid,
        PASS,
        f"owner attestation names {items} item(s), each held by the credential organ, 1Password or released "
        f"({path.name}); completeness of the list is the owner's claim, no value was read{cover}",
    )


ATTEST_RE = re.compile(r"^upload-complete:\s*yes\s+(\S+)\s*$")


def parse_attest_date(text: str) -> float | None:
    try:
        if len(text) == 10:
            return datetime.fromisoformat(text).replace(tzinfo=UTC).timestamp() + 86399
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()


def check_backblaze(ctx: Ctx) -> Result:
    path = ctx.backblaze_attestation
    why = "the owner must attest it; not automatable"
    if path is None or not path.is_file():
        return Result("backblaze-offsite", UNPROVEN, f"no attestation file ({why})")
    lines = path.read_bytes().decode("utf-8", "replace").splitlines()
    match = next((m for m in (ATTEST_RE.match(ln.strip()) for ln in lines) if m), None)
    if match is None:
        return Result(
            "backblaze-offsite", UNPROVEN, f"{path.name} has no 'upload-complete: yes <ISO date>' line ({why})"
        )
    stamp = parse_attest_date(match.group(1))
    if stamp is None:
        return Result("backblaze-offsite", UNPROVEN, f"attestation date {match.group(1)!r} is not ISO")
    if is_future(match.group(1), ctx.now):  # H6: an attestation dated ahead of now outranks every run by construction
        return Result("backblaze-offsite", UNPROVEN, f"attestation date {match.group(1)!r} is in the future")
    newest = 0.0
    newest_name = ""
    evidence = [("preserve", newest_run(ctx.preserve_root))] + [
        ("non-git", resolve_run_dir(p)) for p in ctx.nongit_runs
    ]
    for label, run in evidence:
        if run is None:
            continue
        m = RUN_RE.match(run.name)
        ts = (
            datetime.strptime(m.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).timestamp()
            if m
            else (run / "RESULT.txt").stat().st_mtime
            if (run / "RESULT.txt").is_file()
            else 0.0
        )
        if ts > newest:
            newest, newest_name = ts, f"{label} run {run.name}"
    # T1: a bare date covers from its first second, not its last, so it can never vouch for a run made later that day
    covers = stamp - 86399 if len(match.group(1)) == 10 else stamp
    if covers < newest:
        hint = "; a bare date counts from 00:00:00 UTC, write a full ISO time" if len(match.group(1)) == 10 else ""
        return Result(
            "backblaze-offsite",
            UNPROVEN,
            f"attestation {match.group(1)} predates the newest evidence ({newest_name}); it does not cover it{hint}",
        )
    with contextlib.suppress(OSError):
        if path.stat().st_mtime + FUTURE_SKEW_SEC < newest:  # a file written before the run cannot attest it
            return Result(
                "backblaze-offsite",
                UNPROVEN,
                f"{path.name} was last written before the newest evidence ({newest_name}), so it cannot attest it",
            )
    return Result("backblaze-offsite", PASS, f"owner attestation upload-complete: yes {match.group(1)} ({path.name})")


def check_human_erase(_ctx: Ctx) -> Result:
    return Result(
        "human-erase",
        UNPROVEN,
        "the erase needs the owner at the machine with the Apple ID; "
        "this predicate can only say everything before it holds",
    )


CHECKS: list[tuple[str, Callable[[Ctx], Result]]] = [
    ("sweep-fresh", check_sweep_fresh),
    ("git-preserved", check_git_preserved),
    ("ignored-payload", check_ignored_payload),
    ("no-external-dependency", check_no_external_dependency),
    ("t7-unique-consolidated", check_t7_unique),
    ("nongit-homed", check_nongit_homed),
    ("credential-registry-complete", check_credential_registry),
    ("credential-route-items-homed", check_credential_route_items),
    ("backblaze-offsite", check_backblaze),
    ("human-erase", check_human_erase),
]


def run_one(check_id: str, fn: Callable[[Ctx], Result], ctx: Ctx) -> Result:
    try:
        return fn(ctx)
    except Exception as exc:  # noqa: BLE001  a crashed check must read as FAIL, never as silence
        return Result(check_id, FAIL, f"internal error {type(exc).__name__}: {one_line(str(exc), 300)}", crashed=True)


def decide(results: list[Result]) -> tuple[str, int]:
    """(verdict line, exit code), §8: 0 READY (every check PASS but the one only the owner at the machine can settle),
    1 NOT-READY with a FAIL, 2 NOT-READY because a check could not establish its answer."""
    if any(r.status == FAIL for r in results):
        return "NOT-READY", 1
    unproven = {r.check_id for r in results if r.status == UNPROVEN}
    return ("READY", 0) if unproven <= HUMAN_ONLY else ("NOT-READY", 2)


# ----------------------------------------------------------------------------------------------------
# command line
# ----------------------------------------------------------------------------------------------------
class UsageParser(argparse.ArgumentParser):
    """argparse exits 2 on a usage error; here 2 means "nothing failed, only UNPROVEN checks remain" (H1)."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


class HelpAction(argparse.Action):
    """-h/--help prints the usage and exits 64: asking for help is not a verdict, and an exit 0 would read as READY (E1)."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> NoReturn:
        parser.print_help()
        parser.exit(EXIT_USAGE)


EXIT_CODES_HELP = f"""\
exit codes (a caller must read the exit code; the final READY / NOT-READY line alone is not enough):
  0   READY: every check is PASS except human-erase, which only the owner at the machine can settle
  1   NOT-READY: at least one check is FAIL
  2   NOT-READY: no FAIL, but a check could not establish its answer (UNPROVEN); --no-deep always ends here at best
  {EXIT_USAGE}  usage error, including -h/--help: no check ran
  {EXIT_INTERNAL}  internal error: a check crashed, so the verdict is not an answer
"""


def build_parser() -> argparse.ArgumentParser:
    here = Path(__file__).resolve().parent
    default_sweep = os.path.join(os.environ.get("TMPDIR", "/tmp"), "mac-exit-git-sweep", "git.tsv")
    p = UsageParser(
        description=__doc__.splitlines()[0],
        epilog=EXIT_CODES_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        allow_abbrev=False,
        add_help=False,
    )
    p.add_argument("-h", "--help", action=HelpAction, nargs=0, help=f"show this help and exit {EXIT_USAGE}")
    p.add_argument(
        "--sweep",
        default=default_sweep,
        help="git.tsv from scripts/mac-exit/git-sweep.sh (default: its default out dir)",
    )
    p.add_argument(
        "--max-sweep-age-min",
        type=float,
        default=DEFAULTS["max_sweep_age_min"],
        help=f"sweep age bound in minutes (hard ceiling {MAX_SWEEP_AGE_CEILING_MIN:g})",
    )
    p.add_argument("--preserve-root", default=None, help="REQUIRED: parent of the run-* preserve directories")
    p.add_argument(
        "--remote-held",
        default=None,
        help="REQUIRED: remote-held.tsv from the prove lane (its tips.tsv must sit beside it). A checkout it does not "
        "name is unproven, not trusted",
    )
    p.add_argument(
        "--max-remote-held-age-min",
        type=float,
        default=DEFAULTS["max_remote_held_age_min"],
        help=f"--remote-held age bound in minutes (hard ceiling {MAX_REMOTE_HELD_AGE_CEILING_MIN:g})",
    )
    p.add_argument(
        "--externals",
        default=DEFAULTS["externals"],
        help="comma-separated external volume names; 'auto' (default) = every mounted non-boot volume under "
        "--volumes-root. A mounted volume missing from an explicit list FAILs",
    )
    p.add_argument(
        "--nongit-items",
        action="append",
        default=None,
        help="the items TSV (name, source_dir, dest_rel, exclude_globs) a non-git homing run was made from; "
        "repeatable. The homed copy is compared to the LIVE source, so nongit-homed FAILs without it",
    )
    p.add_argument(
        "--waiver-signers",
        default=None,
        help="allow-list file (one signer per line, # comments) naming who may sign a waiver; "
        "--waivers without it FAILs",
    )
    p.add_argument(
        "--nongit-run",
        action="append",
        default=None,
        help="REQUIRED, repeatable: a non-git homing set, i.e. a run dir with RESULT.txt + manifest, or its parent "
        "(newest run-*)",
    )
    p.add_argument("--backblaze-attestation", default=None, help='REQUIRED: file holding "upload-complete: yes <date>"')
    p.add_argument("--t7-unique", default=None, help="REQUIRED: the consolidated t7-unique directory")
    p.add_argument("--t7-source", default=None, help="REQUIRED: the T7 volume that must still hold the originals")
    p.add_argument("--volumes-root", default=DEFAULTS["volumes_root"])
    p.add_argument("--credential-wall", default=None, help="REQUIRED: path of credential-wall.py")
    p.add_argument(
        "--credential-attestation",
        default=None,
        help="REQUIRED: owner-written names-only list, one line per credential-route item: "
        "'<name> held-by: <organ|1Password|released> <date>'",
    )
    p.add_argument(
        "--preserve-run",
        action="append",
        default=None,
        help="a producer run-* directory or a manual-* copy directory; repeatable (default: every run-* and manual-* "
        "directory under --preserve-root, used as a union)",
    )
    p.add_argument(
        "--waivers",
        default=None,
        help="TSV (path, reason, evidence_path, evidence_sha256, signer, kind[, signed_at]): signed exceptions for "
        "sweep rows that vanished from the Mac",
    )
    p.add_argument(
        "--recovery-root",
        default=None,
        help="rescued copies of vanished repositories (default: newest recovered-from-* beside --preserve-root)",
    )
    p.add_argument(
        "--gitfile-depth",
        type=int,
        default=DEFAULTS["gitfile_depth"],
        help="0 (default) scans without a depth bound; a positive bound FAILs when anything lies below it",
    )
    p.add_argument(
        "--hash-t7-originals", action="store_true", help="re-hash the T7 originals too (default: existence+size)"
    )
    p.add_argument(
        "--deep", action="store_true", help="object-level verification (the default; accepted for compatibility)"
    )
    p.add_argument(
        "--no-deep",
        action="store_true",
        help="skip the content compare and the pack / git-dir object verification (quick looks only: such a run is "
        "UNPROVEN at best, never READY)",
    )
    p.add_argument(
        "--discovery-root",
        action="append",
        default=None,
        help="ADD a root to the fresh scan that must find nothing the sweep lacks; repeatable. The scan always "
        "walks the roots in the sweep's .roots file and the strays under $HOME as well",
    )
    p.add_argument(
        "--disposals",
        default=None,
        help="TSV (path, reason, signer, evidence_path, evidence_sha256): owner-signed disposal of a row under a "
        "disposable path marker",
    )
    p.add_argument(
        "--ignored-payload-attestation",
        default=None,
        help="TSV (path, signer, ISO timestamp, sha256 of the checkout's sorted ignored-path list): the owner has "
        "reviewed that checkout's git-ignored files. The signer must be on --waiver-signers, the time not before the "
        "newest ignored file (a bare date counts from 00:00:00 UTC); a payload added later reopens it",
    )
    p.add_argument("--verbose", action="store_true", help="print every problem under its check line")
    p.add_argument("--scratch", default=None, help="parent for the one temporary directory")
    p.add_argument("--self-test", action="store_true", help="run the fixture-based self-test and exit")
    p.add_argument("--preserve-script", default=str(here / "preserve-git.sh"), help="self-test: the real producer")
    p.add_argument("--classify-script", default=str(here / "classify-git-sweep.py"), help="self-test: sweep classifier")
    p.add_argument("--keep-fixtures", action="store_true", help="self-test: keep the temporary fixture tree")
    return p


def discover_externals(
    volumes_root: Path,
    is_mount: Callable[[str], bool],
    device_of: Callable[[str], int],
    home: str,
    media_of: Callable[[str], Media] | None = None,
) -> list[str]:
    """F4/H2a: every mounted volume under volumes_root that is external physical media. The boot volume (its alias
    resolves to / or shares $HOME's device) is left out, and so is any volume the media probe places on the Mac's own
    disk (an internal APFS volume, a disk image kept on the Mac, a network share): none of them leaves with the
    externals. A volume the probe cannot place at all stays in the list so the scan reports it. Nothing is hardcoded,
    so a volume named like a blank or fresh disk is scanned like any other."""
    probe = media_of or default_media_of
    try:
        names = sorted(os.listdir(volumes_root))
    except OSError:
        return []
    found = []
    for name in names:
        path = str(volumes_root / name)
        if os.path.realpath(path) == "/" or not is_mount(path):
            continue
        try:
            if device_of(path) == device_of(home):
                continue
        except OSError:
            pass  # unreadable device: keep the volume in the list so the scan reports it
        media = probe(path)
        if not media.external and media.mount:
            continue  # placed, and not external
        found.append(name)
    return found


def make_ctx(
    args: argparse.Namespace,
    is_mount: Callable[[str], bool],
    device_of: Callable[[str], int] = default_device_of,
    media_of: Callable[[str], Media] = default_media_of,
) -> Ctx:
    preserve_root = Path(args.preserve_root)
    home = os.environ.get("HOME", "/")
    if args.externals.strip() in ("", "auto"):
        externals = discover_externals(Path(args.volumes_root), is_mount, device_of, home, media_of)
    else:
        externals = [e.strip() for e in args.externals.split(",") if e.strip()]
    return Ctx(
        sweep=Path(args.sweep),
        max_sweep_age_min=args.max_sweep_age_min,
        preserve_root=preserve_root,
        recovery_root=Path(args.recovery_root) if args.recovery_root else discover_recovery(preserve_root),
        preserve_runs=[Path(p) for p in args.preserve_run] if args.preserve_run else None,
        credential_attestation=Path(args.credential_attestation) if args.credential_attestation else None,
        waivers=Path(args.waivers) if args.waivers else None,
        remote_held=Path(args.remote_held) if args.remote_held else None,
        externals=externals,
        nongit_runs=[Path(p) for p in args.nongit_run],
        nongit_items=[Path(p) for p in (args.nongit_items or [])],
        waiver_signers=Path(args.waiver_signers) if args.waiver_signers else None,
        max_remote_held_age_min=args.max_remote_held_age_min,
        device_of=device_of,
        media_of=media_of,
        home=home,
        backblaze_attestation=Path(args.backblaze_attestation) if args.backblaze_attestation else None,
        t7_unique=Path(args.t7_unique),
        t7_source=Path(args.t7_source),
        volumes_root=Path(args.volumes_root),
        credential_wall=Path(args.credential_wall),
        hash_t7_originals=args.hash_t7_originals,
        deep=not args.no_deep,
        discovery_roots=[Path(os.path.realpath(p)) for p in args.discovery_root or []],
        discovery_strays=True,
        scan_universe=True,
        disposals=Path(args.disposals) if args.disposals else None,
        ignored_payload_attestation=Path(args.ignored_payload_attestation)
        if args.ignored_payload_attestation
        else None,
        verbose=args.verbose,
        scratch=Path(args.scratch) if args.scratch else None,
        gitfile_depth=args.gitfile_depth,
        is_mount=is_mount,
    )


def main(
    argv: list[str] | None = None,
    *,
    is_mount: Callable[[str], bool] = os.path.ismount,
    device_of: Callable[[str], int] = default_device_of,
    media_of: Callable[[str], Media] = default_media_of,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.self_test:
        return run_self_test(args)
    for flag, given in (
        ("--preserve-root", args.preserve_root),
        ("--remote-held", args.remote_held),
        ("--nongit-run", args.nongit_run),
        ("--t7-unique", args.t7_unique),
        ("--t7-source", args.t7_source),
        ("--credential-wall", args.credential_wall),
        ("--credential-attestation", args.credential_attestation),
        ("--backblaze-attestation", args.backblaze_attestation),
    ):
        if not given:  # no layout path has a built-in default: a public tool does not know the owner's disks
            parser.error(f"{flag} is required (there is no default path)")
    for flag, value, ceiling in (
        ("--max-sweep-age-min", args.max_sweep_age_min, MAX_SWEEP_AGE_CEILING_MIN),
        ("--max-remote-held-age-min", args.max_remote_held_age_min, MAX_REMOTE_HELD_AGE_CEILING_MIN),
    ):
        if not 0 < value <= ceiling:  # H6: a bound that can be raised without limit is no bound
            parser.error(
                f"{flag} {value:g} is outside (0, {ceiling:g}]: evidence older than that is stale by definition"
            )
    if args.gitfile_depth < 0:
        parser.error("--gitfile-depth must be >= 0 (0 = unbounded)")
    ctx = make_ctx(args, is_mount, device_of, media_of)
    results: list[Result] = []
    for check_id, fn in CHECKS:
        result = run_one(check_id, fn, ctx)
        results.append(result)
        print(f"{result.status} {result.check_id} {one_line(result.detail, 4000 if ctx.verbose else 900)}", flush=True)
        for line in result.info:
            print(f"INFO {result.check_id} {one_line(line, 400)}", flush=True)
        for waiver in result.waived:
            print(
                f"WAIVED {result.check_id} {waiver.path} {one_line(waiver.reason, 300)} "
                f"[signer={waiver.signer} kind={waiver.kind} evidence={waiver.evidence}]",
                flush=True,
            )
        for waiver in result.waived:
            if waiver.exposure:  # F7: a waiver over a row that had unpreserved data is listed on its own line
                print(
                    f"EXPOSED {result.check_id} {waiver.path} waived with data exposure [{waiver.exposure}] "
                    f"by {waiver.signer} as {waiver.kind}",
                    flush=True,
                )
        if ctx.verbose:
            for line in result.extra:
                print(f"  - {one_line(line, 400)}", flush=True)
    if not ctx.deep or ctx.remote_held is None:
        # H-NO-DEEP-READY: what was skipped (the content compare, the pack and git-dir object checks) is exactly what a
        # truncated bundle with a re-hashed manifest slips past, so such a run can never say READY
        skipped = Result(
            "deep-verification",
            UNPROVEN,
            "--no-deep skips the content compare and the pack / git-dir object verification" if not ctx.deep
            else "no --remote-held file was given, so no PROVEN-ALL verdict was checked",
        )
        results.append(skipped)
        print(f"{skipped.status} {skipped.check_id} {skipped.detail}", flush=True)
    verdict, code = decide(results)
    waived = sum(len(r.waived) for r in results)
    print(f"{verdict} ({waived} waiver{'' if waived == 1 else 's'})" if waived else verdict, flush=True)
    return EXIT_INTERNAL if any(r.crashed for r in results) else code


# ----------------------------------------------------------------------------------------------------
# self-test: fixtures from real git, the real producer, every verdict asserted (positive and negative)
# ----------------------------------------------------------------------------------------------------
class Suite:
    def __init__(self, verbose: bool):
        self.verbose = verbose
        self.total = 0
        self.failed: list[str] = []

    def group(self, title: str) -> None:
        print(f"[{title}]", flush=True)

    def expect(self, name: str, cond: bool, detail: str = "") -> None:
        self.total += 1
        if cond:
            if self.verbose:
                print(f"  ok   {name}")
        else:
            self.failed.append(name)
            print(f"  FAIL {name} {one_line(detail, 700)}", flush=True)


FX_ENV = {
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def fx(cwd: str | os.PathLike[str] | None, *args: str) -> str:
    """Fixture git: isolated config, no hooks, no signing, so a host setting cannot change or hang a fixture."""
    cmd = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "-c", "protocol.file.allow=always"]
    cmd += ["-c", "gc.auto=0", "-c", "maintenance.auto=false"]  # no detached maintenance writing lock files mid-test
    if cwd is not None:
        cmd += ["-C", str(cwd)]
    proc = subprocess.run(
        [*cmd, *args],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, **FX_ENV},
        stdin=subprocess.DEVNULL,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"fixture git {' '.join(args[:3])} failed: {proc.stderr.strip()}")
    return proc.stdout


def put(path: Path, data: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)


def commit_file(repo: Path, name: str, text: str, message: str) -> None:
    put(repo / name, text)
    fx(repo, "add", name)
    fx(repo, "commit", "-q", "-m", message)


def origin_store(repo: Path) -> Path:
    """Where the bare repository standing behind a fixture's origin lives: beside the fixture tree, never inside it, so
    the fresh scan (which now finds bare repositories) does not take a remote for a checkout the sweep lacks."""
    for ancestor in repo.parents:
        if ancestor.name == "work":
            return ancestor.parent / "remotes" / (str(repo.relative_to(ancestor)).replace("/", "__") + ".origin.git")
    return repo.parent.parent / "remotes" / repo.parent.name / f"{repo.name}.origin.git"


def add_origin(repo: Path) -> Path:
    """Give a fixture repository an origin the predicate may call a remote (§5): an https URL that is no path on this
    machine, plus the remote-tracking ref a push would leave. The commits really are pushed, to a bare store standing
    behind it, so `git submodule add` and clones from it still work."""
    store = origin_store(repo)
    store.parent.mkdir(parents=True, exist_ok=True)
    fx(None, "init", "-q", "--bare", "--template=", str(store))
    fx(repo, "push", "-q", str(store), "main")
    fx(repo, "remote", "add", "origin", f"https://git.example.invalid/{store.name}")
    fx(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return store


def make_repo(root: Path, name: str, *, remote: bool = True) -> Path:
    repo = root / name
    fx(None, "init", "-q", "--template=", "-b", "main", str(repo))
    put(repo / "bin.dat", bytes(range(256)))
    fx(repo, "add", "bin.dat")
    commit_file(repo, "tracked.txt", "one\n", "one")
    commit_file(repo, "second.txt", "two\n", "two")
    if remote:
        add_origin(repo)
    return repo


def make_dirty(root: Path, name: str) -> Path:
    repo = make_repo(root, name)
    put(repo / "tracked.txt", "one\nmodified\n")
    put(repo / "bin.dat", bytes(reversed(range(256))))
    put(repo / "new.txt", "untracked\n")
    put(repo / "credentials.json", "{}\n")  # credential pattern: left out of snapshots by design
    nested = repo / "nested"
    fx(None, "init", "-q", "--template=", "-b", "main", str(nested))
    commit_file(nested, "n.txt", "n\n", "nested")
    # a nested repository is a checkout of its own that a scan finds (F2), so it is swept; this one is fully pushed
    add_origin(nested)
    os.symlink("tracked.txt", repo / "link")
    return repo


def make_plain(root: Path) -> Path:
    repo = make_repo(root, "plain", remote=False)
    fx(repo, "branch", "feature")
    for n in (1, 2):
        put(repo / "tracked.txt", f"stash {n}\n")
        fx(repo, "stash", "push", "-q", "-m", f"s{n}")
    return repo


def make_unpushed(root: Path, name: str) -> Path:
    repo = make_repo(root, name)
    fx(repo, "checkout", "-q", "-b", "topic")
    commit_file(repo, "topic.txt", "t\n", "topic")
    return repo


def sweep_row(path: str) -> list[str]:
    """The git-sweep.sh columns, computed the same way, for a fixture checkout."""
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}

    def g(*a: str) -> tuple[int, str]:
        p = subprocess.run(
            ["git", "-C", path, *a], check=False, capture_output=True, text=True, env=env, stdin=subprocess.DEVNULL
        )
        return p.returncode, p.stdout

    # §12: kind comes from git, the way git-sweep.sh and the predicate derive it (a checkout git cannot resolve keeps
    # the old rule: a `.git` directory is a repository, a `.git` file a worktree)
    rc, ids = g("rev-parse", "--path-format=absolute", "--is-bare-repository", "--absolute-git-dir", "--git-common-dir")
    lines = ids.splitlines()
    if rc == 0 and len(lines) == 3:
        kind = "bare" if lines[0] == "true" else "repo" if os.path.realpath(lines[1]) == os.path.realpath(lines[2]) else "worktree"
    else:
        kind = "repo" if os.path.isdir(os.path.join(path, ".git")) else "worktree"
    rc, out = g("symbolic-ref", "--short", "-q", "HEAD")
    branch = out.strip() if rc == 0 and out.strip() else "(detached)"
    remote = g("config", "--get", "remote.origin.url")[1].strip() or "NONE"
    dirty = str(len(g("status", "--porcelain=v1", "--untracked-files=normal")[1].splitlines()))
    rc, out = g("rev-list", "--count", "--branches", "--not", "--remotes")
    unpushed = out.strip() if rc == 0 else "?"
    if kind == "bare":  # `git stash list` refuses to run without a work tree; the stash entries are refs/stash's reflog
        rc, out = g("log", "-g", "--format=%H", "refs/stash")
        stashes = str(len(out.splitlines()) if rc == 0 else 0)
    else:
        stashes = str(len(g("stash", "list")[1].splitlines()))
    headrem = str(len(g("branch", "-r", "--contains", "HEAD")[1].splitlines()))
    return [path, kind, branch, remote, dirty, unpushed, stashes, headrem]


def write_roots(sweep: Path, roots: list[str]) -> None:
    """§12: the roots file beside a fixture sweep: the roots it walked, one realpath per line, then `#END rows=N`."""
    real = [os.path.realpath(r) for r in roots]
    roots_path(sweep).write_text("".join(f"{r}\n" for r in real) + f"#END rows={len(real)}\n")


def write_sweep(path: Path, repo_paths: list[str], roots: list[str] | None = None) -> None:
    """A fixture sweep and its roots file. By default the root is the `work` directory the checkouts live in."""
    lines = ["\t".join(SWEEP_COLS)] + ["\t".join(sweep_row(p)) for p in repo_paths]
    path.write_text("\n".join(lines) + "\n")
    if roots is None:
        roots = sorted({p.split("/work/")[0] + "/work" for p in repo_paths if "/work/" in p})
    write_roots(path, roots)


def copy_sweep(src: Path, dest: Path) -> None:
    """Copy a fixture sweep together with its roots file (the roots file is the sweep path with `.roots` for its suffix)."""
    shutil.copy(src, dest)
    if roots_path(src).is_file():
        shutil.copy(roots_path(src), roots_path(dest))


HELD_FIXTURE_COLS = ("repo", "common_dir", "remotes", "verdict", "first_reason", "paths", "all_reasons", "notes", "gaps")


def write_held(path: Path, entries: list[dict[str, str]]) -> None:
    """A per-repository remote-held.tsv in the prove lane's shape (§1, §3, §4): a `gaps` column and the closing row."""
    rows = ["\t".join(HELD_FIXTURE_COLS)] + ["\t".join(e.get(c, "") for c in HELD_FIXTURE_COLS) for e in entries]
    rows.append("\t".join([f"#END rows={len(entries)}"] + ["#END"] * (len(HELD_FIXTURE_COLS) - 1)))
    path.write_text("\n".join(rows) + "\n")


def held_entry(repo: str, verdict: str, paths: list[str] | None = None, gaps: str = "") -> dict[str, str]:
    """One repository's remote-held row: the label is the main checkout's realpath, the keys are realpaths (§1)."""
    top = os.path.realpath(repo)
    common = os.path.realpath(fx(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    return {
        "repo": top,
        "common_dir": common,
        "verdict": verdict,
        "paths": ";".join(os.path.realpath(p) for p in (paths or [top])),
        "gaps": gaps,
    }


def contract_tip_rows(label: str, repo: str, status: str = "PROVEN-EXACT") -> list[list[str]]:
    """The tips.tsv rows of §2 for one fixture repository, written from raw git alone (never through the predicate's own
    reading of a repository, so a key it derives wrongly cannot be mirrored here): full refnames outside refs/remotes and
    refs/stash, `HEAD@<worktree>` for every detached worktree, `<refname>@<worktree>` for every per-worktree ref."""
    rows: list[list[str]] = []
    per_worktree = ("refs/worktree/", "refs/bisect/", "refs/rewritten/")
    for entry in fx(repo, "for-each-ref", "--format=%(refname)%09%(objectname)%09%(symref)").splitlines():
        ref, sha, symref = (entry.split("\t") + ["", ""])[:3]
        if symref or ref.startswith(("refs/remotes/", "refs/stash", *per_worktree)):
            continue
        kind = "branch" if ref.startswith("refs/heads/") else "tag" if ref.startswith("refs/tags/") else "other"
        rows.append([label, ref, kind, sha, status, "fixture"])
    for block in fx(repo, "worktree", "list", "--porcelain").strip().split("\n\n"):
        fields = dict(ln.partition(" ")[::2] for ln in block.splitlines())
        where = os.path.realpath(fields["worktree"])
        if "detached" in fields:
            rows.append([label, f"HEAD@{where}", "detached", fields["HEAD"], status, "fixture"])
        listed = fx(where, "for-each-ref", "--format=%(refname)%09%(objectname)", "refs/worktree", "refs/bisect", "refs/rewritten")
        for entry in listed.splitlines():
            ref, _, sha = entry.partition("\t")
            rows.append([label, f"{ref}@{where}", "per-worktree", sha, status, "fixture"])
    return rows


def write_contract_tips(
    path: Path,
    repos: dict[str, str],
    status: str = "PROVEN-EXACT",
    drop: Callable[[list[str]], bool] = lambda _row: False,
    rewrite: Callable[[list[str]], list[str]] = lambda row: row,
) -> None:
    """tips.tsv (§2, §3) for fixture repositories given as label -> checkout path; `drop` removes rows a test withholds
    and `rewrite` changes the ones it keeps (a wrong key, a short name)."""
    rows = [["repo", "ref", "kind", "tip", "status", "evidence"]]
    for label, repo in repos.items():
        rows += [rewrite(r) for r in contract_tip_rows(label, repo, status) if not drop(r)]
    rows.append([f"#END rows={len(rows) - 1}"] + ["#END"] * 5)
    path.write_text("".join("\t".join(r) + "\n" for r in rows))


WORLD_PROVEN = ("held", "safe", "dirtyA", "dirtyB", "dirtyC", "dirtyD", "nestedA", "nestedB", "nestedC", "nestedD")


def world_held_entries(
    repos: dict[str, str], omit: tuple[str, ...] = (), extra: tuple[dict[str, str], ...] = ()
) -> list[dict[str, str]]:
    """The fixture world's remote-held rows: the PROVEN-ALL repositories (less `omit`), the two the proof cannot vouch for
    (`notheld`; `wtbase` with its linked worktree's detached commit no remote has), and any `extra` rows."""
    entries = [held_entry(repos[n], "PROVEN-ALL") for n in WORLD_PROVEN if n not in omit]
    entries.append(held_entry(repos["notheld"], "UNPROVEN"))
    entries.append(held_entry(repos["wtbase"], "UNPROVEN", [repos["wtbase"], repos["wtdet"]]))
    return [*entries, *extra]


def refresh_tips(w: World, extra: dict[str, str] | None = None, **kw: Any) -> None:
    """The proof re-made for the fixture world's PROVEN-ALL repositories (and any `extra` label -> path) as they are now."""
    repos = {os.path.realpath(w.repos[n]): w.repos[n] for n in WORLD_PROVEN}
    write_contract_tips(w.root / "tips.tsv", {**repos, **(extra or {})}, **kw)


def repin(run: Path) -> None:
    """Keep the verifier's `manifest_sha256=` pin in RESULT.txt in step with a MANIFEST.tsv the self-test edited on
    purpose. A test that edits the manifest simulates a CONSISTENT change (an item dropped, a field set, a re-hash),
    so the defence it targets is the artifact check, not INT-7's pin; INT-7 tests write an inconsistent pin themselves."""
    result = run / "RESULT.txt"
    if not result.is_file():
        return
    text = result.read_text()
    if "manifest_sha256=" in text:
        result.write_text(re.sub(r"manifest_sha256=\S+", f"manifest_sha256={sha256_file(run / 'MANIFEST.tsv')}", text))


def add_manifest_item(run: Path, kind: str, slug: str, source: str, artifact: Path, entries: int, note: str) -> None:
    """Append one item to a run's MANIFEST.tsv exactly as the producer's manifest() does (size and sha256 of the file)."""
    row = [kind, "ok", slug, source, artifact.relative_to(run).as_posix(), str(artifact.stat().st_size)]
    row += [sha256_file(artifact), str(entries), note]
    with (run / "MANIFEST.tsv").open("a", encoding="utf-8") as handle:
        handle.write("\t".join(row) + "\n")
    repin(run)


def add_empty_item(run: Path, kind: str, slug: str, source: str, note: str) -> None:
    """An `empty` item as the producer writes it: no artifact file, zero bytes, zero entries."""
    with (run / "MANIFEST.tsv").open("a", encoding="utf-8") as handle:
        handle.write("\t".join([kind, "empty", slug, source, "", "0", "", "0", note]) + "\n")
    repin(run)


def make_gitdir_tar(run: Path, common: str, home: str, why: str) -> None:
    """The producer's gitdir_tar() for one repository: `tar -C <parent> --exclude 'tmp_pack_*' -cf <run>/bundles/<slug>.gitdir.tar
    <base>`, with its manifest row. The self-test uses it only where the producer under test does not make the item yet."""
    slug = slugify(common, home)
    artifact = run / "bundles" / f"{slug}.gitdir.tar"
    artifact.parent.mkdir(exist_ok=True)
    env = {**os.environ, "COPYFILE_DISABLE": "1"}  # as the producer exports it: no AppleDouble `._` members in a git dir
    subprocess.run(
        ["tar", "-C", os.path.dirname(common), "--exclude", "tmp_pack_*", "-cf", str(artifact), os.path.basename(common)],
        check=True,
        capture_output=True,
        env=env,
    )
    entries = len(subprocess.run(["tar", "-tf", str(artifact)], check=True, capture_output=True, env=env).stdout.splitlines())
    add_manifest_item(run, "gitdir-tar", slug, common, artifact, entries, f"raw copy of the git dir: {why}")


@dataclasses.dataclass
class World:
    root: Path
    home: str
    repos: dict[str, str]
    sweep: Path
    real: Path
    held: Path
    preserve_root: Path
    run: Path
    start_ts: int


def build_world(root: Path, args: argparse.Namespace) -> World:
    work = root / "work"
    work.mkdir()
    repos: dict[str, str] = {"plain": str(make_plain(work))}
    for tag in "ABCD":
        repos[f"dirty{tag}"] = str(make_dirty(work, f"dirty{tag}"))
    base = make_repo(work, "wtbase")
    wt = work / "wtdet"
    fx(base, "worktree", "add", "-q", "--detach", str(wt), "HEAD")
    commit_file(wt, "d.txt", "d\n", "detached")
    repos["wtbase"], repos["wtdet"] = str(base), str(wt)
    repos["held"] = str(make_unpushed(work, "held"))
    repos["notheld"] = str(make_unpushed(work, "notheld"))
    orphan = work / "orphan"
    put(orphan / ".git", f"gitdir: {work}/gone/gitdir\n")
    put(orphan / "a.txt", "a\n")
    put(orphan / "sub" / "b.txt", "b\n")
    os.symlink("a.txt", orphan / "lnk")
    repos["orphan"] = str(orphan)
    disposable = work / "custody-staging"
    disposable.mkdir()
    repos["disp"] = str(make_repo(disposable, "disp", remote=False))
    repos["safe"] = str(make_repo(work, "safe"))
    unborn = work / "unborn"  # no commits: the producer takes a staged-tar and a raw git-dir copy
    fx(None, "init", "-q", "--template=", "-b", "main", str(unborn))
    put(unborn / "staged.txt", "staged\n")
    fx(unborn, "add", "staged.txt")
    put(unborn / "loose.txt", "loose\n")
    repos["unborn"] = str(unborn)
    partial = make_unpushed(work, "partial")  # a promisor remote: the producer takes a raw git-dir copy, no bundle
    fx(partial, "config", "remote.origin.promisor", "true")
    fx(partial, "config", "remote.origin.partialclonefilter", "blob:none")
    repos["partial"] = str(partial)
    for tag in "ABCD":  # F2: a nested repository is a checkout of its own that a scan finds, so it is swept
        repos[f"nested{tag}"] = f"{repos[f'dirty{tag}']}/nested"
    sweep = root / "git.tsv"
    write_sweep(sweep, list(repos.values()))
    held = root / "remote-held.tsv"
    write_held(held, world_held_entries(repos))
    # F1: PROVEN-ALL is bound to the repository's tips, in the contract's own keys (§2), written from raw git
    write_contract_tips(root / "tips.tsv", {os.path.realpath(repos[n]): repos[n] for n in WORLD_PROVEN})
    evidence = root / "disposal-evidence.md"
    evidence.write_text(
        f"fixture scratch repository {repos['disp']} under a disposable marker; the owner signs it away\n"
    )
    (root / "disposals.tsv").write_text(
        "path\treason\tsigner\tevidence_path\tevidence_sha256\n"
        f"{repos['disp']}\tfixture scratch repository\tconductor\t{evidence.name}\t{sha256_file(evidence)}\n"
    )
    real = root / "real.tsv"
    classify = Path(args.classify_script)
    if classify.is_file():
        subprocess.run([sys.executable, str(classify), str(sweep), "--out", str(real)], check=True, capture_output=True)
    else:
        rows = load_sweep(sweep)
        keep = [r for r in rows if reasons_for(r) and not any(m in r["path"] for m in DISPOSABLE_MARKERS)]
        real.write_text(
            "path\tkind\tbranch\tremote\tdirty\tunpushed\tstashes\treasons"
            + "\n"
            + "".join(
                "\t".join([r["path"], r["kind"], r["branch"], r["remote"], r["dirty"], r["unpushed"], r["stashes"]])
                + "\t"
                + ",".join(reasons_for(r))
                + "\n"
                for r in keep
            )
        )
    # F3: the classifier drops rows under a disposable marker, but a marker earns no exemption here, so the
    # fixture feeds them to the producer too (the covered path; the signed-disposal path is tested on its own)
    marked = [r for r in load_sweep(sweep) if reasons_for(r) and any(m in r["path"] for m in DISPOSABLE_MARKERS)]
    with real.open("a", encoding="utf-8") as handle:
        for r in marked:
            cols = [r["path"], r["kind"], r["branch"], r["remote"], r["dirty"], r["unpushed"], r["stashes"]]
            handle.write("\t".join([*cols, ",".join(reasons_for(r))]) + "\n")
    preserve_root = root / "preserve-root"
    proc = subprocess.run(
        ["bash", args.preserve_script, str(real), str(preserve_root), "apply"],
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=900,
        # fixtures live under TMPDIR on the boot disk: opt out of the producer's same-device refusal for the test only
        env={
            **os.environ,
            "PRESERVE_MIN_FREE_GIB": "0",
            "PRESERVE_SCRATCH": str(root / "pscratch"),
            "PRESERVE_ALLOW_SAME_DEVICE": "1",
        },
    )
    if proc.returncode != 0:
        raise RuntimeError(f"producer exited {proc.returncode}: {proc.stderr.strip()[-400:]}")
    run = newest_run(preserve_root)
    if run is None:
        raise RuntimeError("producer wrote no run directory")
    # §6 parity: the predicate's rule and the REAL producer must agree on which repositories get a raw git-dir copy; a
    # fixture never writes one on the producer's behalf (that is how a fabricated format hid INT-5 in round 1)
    if unmade := missing_gitdir_tars(sweep, held, run, os.environ.get("HOME", "/")):
        raise RuntimeError(f"the producer wrote no gitdir-tar where the predicate's §6 rule requires one: {unmade}")
    # INT-7: a run counts only after the independent verifier has passed it, so the fixture run is verified by the REAL
    # verify-preserve.sh (never a RESULT.txt written here): its PASS names this run and is what the predicate binds
    verified = subprocess.run(
        ["bash", str(Path(args.preserve_script).with_name("verify-preserve.sh")), str(real), str(run)],
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=900,
        env={**os.environ, "PRESERVE_SCRATCH": str(root / "pscratch")},
    )
    if verified.returncode != 0:
        raise RuntimeError(f"verify-preserve exited {verified.returncode}: {verified.stdout.strip()[:400]}")
    (root / "tmp").mkdir()
    start = int(datetime.strptime(run.name[4:], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).timestamp())
    return World(root, os.environ.get("HOME", "/"), repos, sweep, real, held, preserve_root, run, start)


def missing_gitdir_tars(sweep: Path, held: Path, run: Path, home: str) -> list[str]:
    """§6 asks the producer for a raw git-dir copy wherever live git shows reflog-only commits, per-worktree refs, git-lfs
    or git-annex objects, or submodule git dirs. The repositories (with the predicate's reasons) where the predicate's
    rule fires but the producer's run has no gitdir-tar item: the parity check between the two halves of the contract."""
    stub, view = mk_ctx_stub(), RunView(run)
    present, _gone = prepare_needs(build_plan(load_sweep(sweep), load_remote_held(held)).needs)
    missing = []
    for need in present:
        if need.orphan or need.common is None or view.one("gitdir-tar", slugify(need.common, home)) is not None:
            continue
        why = repo_state(stub, need.row["path"], need.common, need.row["kind"] == "repo").gitdir_reasons()
        if why:
            missing.append(f"{need.common} ({', '.join(why)})")
    return missing


SELFTEST_DEVICES: Callable[[str], int] | None = None  # set by run_self_test; cli() hands it to main()
SELFTEST_MEDIA: Callable[[str], Media] | None = None  # likewise, for the physical-media probe
SELFTEST_HOME: Path | None = None  # likewise: the empty stand-in $HOME main() runs under


def fixture_media(w: World, mac: tuple[str, ...] = ()) -> Callable[[str], Media]:
    """The physical-media stand-in for fixture_devices (H2a): device 1 (the Mac's zones, plus any `mac` extras) is the
    internal disk, every other fixture device an external one. A path that does not exist is not external."""
    device_of = fixture_devices(w, mac)

    def media_of(path: str) -> Media:
        try:
            device = device_of(path)
        except OSError as exc:
            return Media(False, "", f"fixture: cannot place {path}: {exc.strerror}")
        return Media(device != 1, f"fixture-device-{device}", f"fixture device {device}")

    return media_of


def fixture_devices(w: World, mac: tuple[str, ...] = ()) -> Callable[[str], int]:
    """Fake device ids so one fixture tree can stand in for the Mac's disk and the externals (F4, H2).

    The Mac is device 1: $HOME, anything outside the fixture root, and the root's work/, fakehome/, mac-source/ and
    nongit-src/ subtrees (plus any `mac` extras). VolA is 3, VolB is 4 and every other path under the root is a
    generic external, 2. A path that does not exist raises FileNotFoundError, as os.stat does."""
    root = os.path.realpath(w.root)
    zones = [(os.path.join(root, "vols", "VolA"), 3), (os.path.join(root, "vols", "VolB"), 4)]
    zones += [(os.path.join(root, name), 1) for name in ("work", "fakehome", "mac-source", "nongit-src", *mac)]

    def device_of(path: str) -> int:
        real = os.path.realpath(path)
        os.stat(real)
        for prefix, device in zones:
            if real == prefix or real.startswith(prefix + "/"):
                return device
        return 2 if real == root or real.startswith(root + "/") else 1

    return device_of


def mk_ctx(world: World, **over: object) -> Ctx:
    signers = world.root / "waiver-signers.txt"
    if not signers.exists():
        signers.write_text("# fixture allow-list\nconductor\n")
    base: dict[str, object] = {
        "device_of": fixture_devices(world),
        "media_of": fixture_media(world),
        "waiver_signers": signers,
        "sweep": world.sweep,
        "max_sweep_age_min": 30.0,
        "preserve_root": world.preserve_root,
        "remote_held": world.held,
        "externals": [],
        "nongit_runs": [world.root / "absent-nongit"],
        "backblaze_attestation": None,
        "credential_attestation": None,
        "t7_unique": world.root / "absent-t7",
        "t7_source": world.root / "absent-t7-source",
        "volumes_root": world.root / "vols",
        "credential_wall": world.root / "absent-wall.py",
        "scratch": world.root / "tmp",
        "home": world.home,
        "is_mount": os.path.isdir,
    }
    base.update(over)
    if "scan_universe" not in over:
        # F2: the fresh scan covers the roots in the sweep's roots file. A synthetic sweep of vanished paths (the recovery
        # and waiver groups) has none and is no claim about the disk
        base["scan_universe"] = roots_path(Path(str(base["sweep"]))).is_file()
    return Ctx(**base)  # type: ignore[arg-type]


def blame(res: Result) -> dict[str, set[str]]:
    out: dict[str, set[str]] = collections.defaultdict(set)
    for p in res.problems:
        out[p.subject].add(p.code)
    return dict(out)


def rewrite_manifest(run: Path, fn: Callable[[dict[str, str]], dict[str, str] | None]) -> None:
    path = run / "MANIFEST.tsv"
    lines = path.read_text().split("\n")
    out = [lines[0]]
    for line in lines[1:]:
        if not line:
            continue
        item = fn(dict(zip(MANIFEST_COLS, line.split("\t"), strict=True)))
        if item is not None:
            out.append("\t".join(item[c] for c in MANIFEST_COLS))
    path.write_text("\n".join(out) + "\n")
    repin(run)


def clone_run(world: World, name: str) -> tuple[Path, Path]:
    dest = world.root / f"tamper-{name}"
    shutil.copytree(world.run, dest / world.run.name, symlinks=True)
    return dest, dest / world.run.name


def drop_item(run: Path, kind: str, slug: str) -> None:
    rewrite_manifest(run, lambda i: None if (i["item_kind"], i["slug"]) == (kind, slug) else i)


def set_field(run: Path, kind: str, slug: str, **fields: str) -> None:
    rewrite_manifest(run, lambda i: {**i, **fields} if (i["item_kind"], i["slug"]) == (kind, slug) else i)


# ----------------------------------------------------------------------------------------------------
# self-test groups for the exposure-derivation findings. Each builds its own spare world, so a test may damage
# repositories freely and the shared world stays pristine for every group after it.
# ----------------------------------------------------------------------------------------------------
def spare_world(w: World, name: str, args: argparse.Namespace) -> World:
    """A second disposable fixture world (own repositories, own producer run)."""
    root = w.root / name
    root.mkdir()
    return build_world(root, args)


def tar_edit(
    path: Path,
    drop: Callable[[str], bool] = lambda _n: False,
    dup: str | None = None,
    replace: dict[str, bytes] | None = None,
    add: dict[str, bytes] | None = None,
) -> None:
    """Rewrite a tar in place: without the members `drop` selects, repeating member `dup`, with new content for
    `replace`, or with extra regular members `add`."""
    members: list[tuple[tarfile.TarInfo, bytes | None]] = []
    with tarfile.open(path, "r:") as tf:
        for m in tf:
            handle = tf.extractfile(m) if m.isreg() else None
            members.append((m, handle.read() if handle else None))
    with tarfile.open(path, "w:", format=tarfile.PAX_FORMAT) as out:
        for m, data in members:
            if drop(m.name):
                continue
            if replace and m.name in replace:
                data = replace[m.name]
                m = m.replace(deep=True)
                m.size = len(data)
            out.addfile(m, io.BytesIO(data) if data is not None else None)
            if dup == m.name:
                out.addfile(m, io.BytesIO(data) if data is not None else None)
        for name, data in (add or {}).items():
            info = tarfile.TarInfo(name)
            info.size, info.mtime, info.mode = len(data), int(time.time()), 0o644
            out.addfile(info, io.BytesIO(data))


def rehash(run: Path, kind: str, slug: str) -> None:
    """Make the manifest agree with a tampered artifact, so only the content check can catch the tampering."""
    item = RunView(run).one(kind, slug)
    assert item is not None, (kind, slug)
    artifact = run / item["file"]
    set_field(run, kind, slug, bytes=str(artifact.stat().st_size), sha256=sha256_file(artifact))


def raises_git_error(fn: Callable[..., object], *args: object) -> bool:
    try:
        fn(*args)
    except GitReadError:
        return True
    return False


def st_group_ready_a_artifacts(s: Suite, w: World, args: argparse.Namespace) -> None:
    s.group("exposure: tampered artifacts, all refs, unreadable git state (F5 H3 H8; M03 M04 M06 M10 M12 M14 M16 M18)")
    sw = spare_world(w, "spare-artifacts", args)
    partial, unborn, dirty_a = sw.repos["partial"], sw.repos["unborn"], sw.repos["dirtyA"]
    dirty_b, dirty_c, notheld = sw.repos["dirtyB"], sw.repos["dirtyC"], sw.repos["notheld"]
    wtdet, wtbase = sw.repos["wtdet"], sw.repos["wtbase"]
    partial_slug = slugify(os.path.realpath(partial + "/.git"), sw.home)
    unborn_slug = slugify(os.path.realpath(unborn + "/.git"), sw.home)

    def run_check(**over: object) -> Result:
        return check_git_preserved(mk_ctx(sw, **over))

    def codes(res: Result, repo: str) -> set[str]:
        return blame(res).get(repo, set())

    s.expect("the spare world itself PASSes before any damage (negative control)", run_check().status == PASS)

    # M03: a raw git-dir copy in the reftable format cannot be read, so it never counts as covered
    dest, run = clone_run(sw, "reftable")
    item = RunView(run).one("gitdir-tar", partial_slug)
    with tarfile.open(run / item["file"], "a") as tf:
        info = tarfile.TarInfo(".git/reftable/tables.list")
        info.size = 2
        tf.addfile(info, io.BytesIO(b"0\n"))
    rehash(run, "gitdir-tar", partial_slug)
    res = run_check(preserve_root=dest)
    s.expect(
        "a gitdir-tar holding reftable data is bundle-verify, never covered (M03)",
        codes(res, partial) == {"bundle-verify"} and "reftable" in str(res.problems),
        str(blame(res)),
    )

    # M16: a tar that repeats a member name is not the snapshot it claims to be
    dest, run = clone_run(sw, "dupes")
    item = RunView(run).one("untracked-tar", slugify(dirty_a, sw.home))
    tar_edit(run / item["file"], dup="new.txt")
    rehash(run, "untracked-tar", slugify(dirty_a, sw.home))
    res = run_check(preserve_root=dest)
    s.expect(
        "an untracked-tar with a repeated member name is untracked-mismatch (M16)",
        codes(res, dirty_a) == {"untracked-mismatch"} and "duplicate member" in str(res.problems),
        str(blame(res)),
    )

    # M18: the unborn repository's raw git-dir copy must hold every staged blob
    blob = fx(unborn, "rev-parse", ":staged.txt").strip()
    dest, run = clone_run(sw, "no-blob")
    item = RunView(run).one("gitdir-tar", unborn_slug)
    tar_edit(run / item["file"], drop=lambda n: n == f".git/objects/{blob[:2]}/{blob[2:]}")
    rehash(run, "gitdir-tar", unborn_slug)
    res = run_check(preserve_root=dest)
    s.expect(
        "a gitdir-tar missing a staged blob is gitdir-stale and names the blob (M18)",
        any(p.code == "gitdir-stale" and "staged blob" in p.message for p in res.problems if p.subject == unborn),
        str(blame(res)),
    )

    # M14: an index rewritten after the raw git-dir copy was taken
    index = Path(unborn) / ".git" / "index"
    before = index.stat()
    try:
        os.utime(index, ns=(before.st_atime_ns, before.st_mtime_ns + 5_000_000_000))
        res = run_check()
        s.expect(
            "an index newer than the raw git-dir copy's is gitdir-stale (M14)",
            any(p.code == "gitdir-stale" and "index changed" in p.message for p in res.problems if p.subject == unborn),
            str(blame(res)),
        )
    finally:
        os.utime(index, ns=(before.st_atime_ns, before.st_mtime_ns))
    s.expect("the restored index PASSes again (negative control)", run_check().status == PASS)

    # M04: files the producer cannot snapshot make the entry FAIL (git never lists a FIFO or socket, so size is the case)
    huge = Path(dirty_b) / "huge.bin"
    with huge.open("wb") as handle:
        handle.truncate(MAX_FILE_BYTES + 1)
    try:
        s.expect("a file over 2 GiB is unsnapshotable (M04)", codes(run_check(), dirty_b) == {"unsnapshotable"})
    finally:
        huge.unlink()
    s.expect("without them the repository PASSes again (negative control)", run_check().status == PASS)

    # M10: an untracked file whose mtime moved while its size did not
    target = Path(dirty_c) / "new.txt"
    before = target.stat()
    try:
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns - 3_600_000_000_000))
        s.expect(
            "a same-size untracked file with another mtime is untracked-mismatch (M10)",
            codes(run_check(), dirty_c) == {"untracked-mismatch"},
        )
    finally:
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))

    # M12: a find that reports an error is an incomplete scan, never a clean one
    vols = sw.root / "ra-vols"
    locked = vols / "VolA" / "locked"
    locked.mkdir(parents=True)
    ctx = mk_ctx(sw, externals=["VolA"], volumes_root=vols)
    try:
        locked.chmod(0)
        res = check_no_external_dependency(ctx)
        s.expect(
            "find stderr (an unreadable directory) FAILs as scan-incomplete (M12)",
            res.status == FAIL and "scan-incomplete" in str(res.problems),
            res.detail,
        )
    finally:
        locked.chmod(0o755)
    s.expect(
        "the same volume PASSes once readable (negative control)", check_no_external_dependency(ctx).status == PASS
    )

    # M06: a head bundle whose prerequisite the repository lacks fails `git bundle verify`
    dest, run = clone_run(sw, "head-bundle")
    drop_item(run, "bundle", slugify(os.path.realpath(wtbase + "/.git"), sw.home))  # else the full bundle covers HEAD
    head_slug = slugify(wtdet, sw.home)
    bundle_file = run / RunView(run).one("head-bundle", head_slug)["file"]
    raw = bundle_file.read_bytes()
    at = raw.index(b"\n-") + 2
    bundle_file.write_bytes(raw[:at] + b"1" * 40 + raw[at + 40 :])
    rehash(run, "head-bundle", head_slug)
    s.expect(
        "a head bundle that fails git bundle verify is bundle-verify (M06)",
        codes(run_check(preserve_root=dest), wtdet) == {"bundle-verify"},
    )

    # F5: refs outside heads and stash. The full bundle and the raw git-dir copy must carry them too.
    tree = fx(notheld, "rev-parse", "HEAD^{tree}").strip()
    c1 = fx(notheld, "commit-tree", tree, "-p", "HEAD", "-m", "reachable only from refs/limen").strip()
    c2 = fx(notheld, "commit-tree", tree, "-p", "HEAD", "-m", "reachable only from a tag").strip()
    fx(notheld, "update-ref", "refs/limen/artifact-x", c1)
    fx(notheld, "tag", "-a", "-m", "annotated local tag", "v-local", c2)
    try:
        res = run_check()
        lacking = [p.message for p in res.problems if p.subject == notheld and p.code == "tip-missing"]
        s.expect(
            "a ref under refs/limen and an annotated tag created after the run are tip-missing (F5)",
            len(lacking) == 1 and "refs/limen/artifact-x" in lacking[0] and "refs/tags/v-local" in lacking[0],
            str(lacking),
        )
    finally:
        fx(notheld, "update-ref", "-d", "refs/limen/artifact-x")
        fx(notheld, "tag", "-d", "v-local")
    s.expect("with those refs removed the repository PASSes again (negative control)", run_check().status == PASS)
    c3 = fx(partial, "commit-tree", fx(partial, "rev-parse", "HEAD^{tree}").strip(), "-p", "HEAD", "-m", "x").strip()
    fx(partial, "update-ref", "refs/limen/extra", c3)
    try:
        s.expect(
            "a new ref the raw git-dir copy lacks is tip-missing (F5, gitdir-tar)",
            codes(run_check(), partial) == {"tip-missing"},
        )
    finally:
        fx(partial, "update-ref", "-d", "refs/limen/extra")
    # the same namespaces are read out of the raw git-dir copy, loose and packed, when it does carry them
    topic = fx(partial, "rev-parse", "refs/heads/topic").strip()
    fx(partial, "update-ref", "refs/limen/loose", topic)
    fx(partial, "update-ref", "refs/limen/packed", topic)
    dest, run = clone_run(sw, "carried-refs")
    try:
        s.expect(
            "two new refs the raw git-dir copy lacks are tip-missing (F5, negative control)",
            codes(run_check(preserve_root=dest), partial) == {"tip-missing"},
        )
        tar_edit(
            run / RunView(run).one("gitdir-tar", partial_slug)["file"],
            add={
                ".git/refs/limen/loose": f"{topic}\n".encode(),
                ".git/packed-refs": f"# pack-refs with: peeled fully-peeled sorted\n{topic} refs/limen/packed\n".encode(),
            },
        )
        rehash(run, "gitdir-tar", partial_slug)
        s.expect(
            "refs outside heads and stash that the raw git-dir copy carries, loose or packed, cover (F5)",
            codes(run_check(preserve_root=dest), partial) == set(),
            str(blame(run_check(preserve_root=dest))),
        )
    finally:
        fx(partial, "update-ref", "-d", "refs/limen/loose")
        fx(partial, "update-ref", "-d", "refs/limen/packed")

    # H3: an unreadable ref store is a git-error, never an empty answer that hides a missing tip
    old_tip = fx(notheld, "rev-parse", "refs/heads/topic").strip()
    env = {
        **os.environ,
        **FX_ENV,
        "GIT_COMMITTER_DATE": "2001-01-01T00:00:00Z",
        "GIT_AUTHOR_DATE": "2001-01-01T00:00:00Z",
    }
    late = subprocess.run(
        ["git", "-C", notheld, "commit-tree", tree, "-p", "HEAD", "-m", "late, backdated"],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    ).stdout.strip()
    packed = Path(os.path.realpath(notheld + "/.git")) / "packed-refs"
    fx(notheld, "update-ref", "refs/heads/topic", late)
    try:
        s.expect(
            "a backdated commit made after the run is tip-missing (precondition for H3)",
            "tip-missing" in codes(run_check(), notheld),
        )
        packed.write_text("this line is not a ref\n")
        res = run_check()
        s.expect(
            "the same repository with an unreadable ref store is git-error, not a pass (H3)",
            res.status == FAIL and "git-error" in codes(res, notheld),
            str(blame(res)),
        )
    finally:
        packed.unlink(missing_ok=True)
        fx(notheld, "update-ref", "refs/heads/topic", old_tip)
        # the backdated commit is reflog-only now, which §6 answers with a raw git-dir copy; "repaired" means the reflog
        # that remembers it is gone too
        fx(notheld, "reflog", "expire", "--expire=now", "--all")
    s.expect("the repaired repository PASSes again (negative control)", run_check().status == PASS)
    empty_dir = sw.root / "not-a-git-dir"
    empty_dir.mkdir()
    s.expect(
        "current_refs, stash_count and newest_commit_ts raise on a git dir they cannot read (H3)",
        all(raises_git_error(fn, str(empty_dir)) for fn in (current_refs, stash_count, newest_commit_ts)),
    )
    s.expect(
        "missing_objects raises when git cannot answer, instead of reporting nothing missing (H3)",
        raises_git_error(missing_objects, str(empty_dir), ["a" * 40]),
    )

    # H8: an `ok` tracked-patch that records no file must still be verified (and fails as artifact-missing)
    dest, run = clone_run(sw, "empty-ok-patch")
    set_field(run, "tracked-patch", slugify(dirty_b, sw.home), file="")
    s.expect(
        "an ok tracked-patch item with an empty file field is artifact-missing (H8)",
        "artifact-missing" in codes(run_check(preserve_root=dest), dirty_b),
    )


def prepare_e2e(sw: World) -> Path:
    """What the shared world's earlier groups leave behind for st_group_e2e, built for a spare world. Returns the
    Backblaze attestation path."""
    make_vols(sw)
    st_group_t7_restore(sw)
    (sw.root / "wall-ok.py").write_text("import sys\nsys.exit(0)\n")
    (sw.root / "e2e-credential-items.txt").write_text("deploy-key held-by: 1Password 2026-10-21\n")
    attestation = sw.root / "e2e-attest.txt"
    # merged with H6: a future-dated attestation is now rejected; T1: a bare date counts from 00:00:00 and would
    # predate today's run, so the positive control carries a full time
    attestation.write_text(f"upload-complete: yes {datetime.now(UTC).isoformat()}\n")
    return attestation


def swept_checkouts(sw: World) -> list[str]:
    """Every checkout a scan of the spare world finds, in the order build_world sweeps them."""
    return list(sw.repos.values())


def st_group_ready_a_exposure(s: Suite, w: World, args: argparse.Namespace) -> None:
    s.group("exposure: live re-derivation, proof binding, universe, hidden state, disposal, deep (F1 F2 F3 F6 H4 H7)")
    sb = spare_world(w, "spare-exposure-b", args)
    attestation = prepare_e2e(sb)
    code, lines = cli(e2e_argv(sb, attestation), os.path.isdir)
    s.expect(
        "a fully covered spare world is READY, exit 0 (positive control for everything below)",
        code == 0 and lines[-1] == "READY",
        f"{code} {lines}",
    )

    # F1 (r1): a repository the sweep recorded clean gains a local commit, a stash, an edit and an untracked file
    safe = Path(sb.repos["safe"])
    commit_file(safe, "local-only.txt", "work that exists only on this Mac\n", "local only")
    put(safe / "tracked.txt", "stashed edit\n")
    fx(safe, "stash", "push", "-q", "-m", "only copy")
    put(safe / "tracked.txt", "one\nuncommitted edit\n")
    put(safe / "notes.txt", "untracked notes\n")
    os.utime(sb.sweep, None)
    res = check_git_preserved(mk_ctx(sb))
    s.expect(
        "exposure that appeared after the sweep is exposure-drift and FAILs git-preserved (F1)",
        res.status == FAIL and "exposure-drift" in blame(res).get(str(safe), set()),
        str(blame(res)),
    )
    s.expect(
        "the drifted repository also needs coverage now: its bundle, stash and dirty snapshot are missing (F1)",
        {"manifest-missing"} <= blame(res).get(str(safe), set()),
        str(blame(res)),
    )
    code, lines = cli(e2e_argv(sb, attestation), os.path.isdir)
    s.expect(
        "end to end the drifted world is NOT-READY with exit 1, where the baseline printed READY (r1)",
        code == 1 and lines[-1] == "NOT-READY" and any(ln.startswith("FAIL git-preserved") for ln in lines),
        f"{code} {lines[-1]}",
    )

    sa = spare_world(w, "spare-exposure-a", args)
    work = sa.root / "work"

    def run_check(**over: object) -> Result:
        return check_git_preserved(mk_ctx(sa, **over))

    def scan(**over: object) -> Ctx:
        return mk_ctx(sa, discovery_roots=[work], **over)

    def codes(res: Result, repo: str) -> set[str]:
        return blame(res).get(repo, set())

    s.expect("the other spare world PASSes before any damage (negative control)", run_check().status == PASS)

    # F1 (r1b): PROVEN-ALL is bound to the ref tips the prove lane saw, and to the age of its file
    held = Path(sa.repos["held"])
    old_tip = fx(held, "rev-parse", "refs/heads/topic").strip()
    commit_file(held, "after-proof.txt", "a commit made after the remote proof\n", "after proof")
    write_sweep(sa.sweep, swept_checkouts(sa))  # a fresh sweep: held is plainly "unpushed", PROVEN-ALL in the file
    res = run_check()
    s.expect(
        "a commit made after the proof voids PROVEN-ALL: held needs its bundle and the bundle lacks the tip (F1)",
        res.status == FAIL and "tip-missing" in codes(res, str(held)) and "not trusted" in res.detail,
        res.detail,
    )
    refresh_tips(sa)
    s.expect(
        "with the proof re-bound to the new tip the same state PASSes (negative control)", run_check().status == PASS
    )
    aged = time.time() - 721 * 60
    os.utime(sa.held, (aged, aged))
    res = run_check()
    s.expect(
        "a remote-held file older than the age bound is not believed (F1)",
        res.status == FAIL and "over the 720m bound" in res.detail,
        res.detail,
    )
    s.expect(
        "the age bound is a parameter",
        # merged with H6: the bound must stay under the hard ceiling, so use 24 h (the file is 721 m old)
        run_check(max_remote_held_age_min=60 * 24).status == PASS,
    )
    os.utime(sa.held, None)
    (sa.root / "tips.tsv").rename(sa.root / "tips.off")
    res = run_check()
    s.expect(
        "a remote-held file with no tips.tsv beside it is not bound to any tip and is not believed (F1)",
        res.status == FAIL and "no tips.tsv" in res.detail,
        res.detail,
    )
    (sa.root / "tips.off").rename(sa.root / "tips.tsv")
    s.expect("restoring tips.tsv PASSes again (negative control)", run_check().status == PASS)
    fx(held, "reset", "-q", "--hard", old_tip)
    fx(held, "reflog", "expire", "--expire=now", "--all")  # else the undone commit stays reflog-only, which no proof covers
    write_sweep(sa.sweep, swept_checkouts(sa))
    refresh_tips(sa)
    s.expect("the repaired world PASSes (negative control)", run_check().status == PASS)

    # F1: the per-repository remote-held shape joins tips.tsv by its `repo` label, and a detached HEAD needs its own tip
    wtbase, wtdet = Path(sa.repos["wtbase"]), Path(sa.repos["wtdet"])
    lab = sa.root / "labels"
    lab.mkdir()
    write_held(lab / "remote-held.tsv", [held_entry(str(wtbase), "PROVEN-ALL", [str(wtbase), str(wtdet)])])
    write_contract_tips(lab / "tips.tsv", {os.path.realpath(wtbase): str(wtbase)})  # carries HEAD@<wtdet> (§2)
    res = run_check(remote_held=lab / "remote-held.tsv")
    s.expect(
        "a proof keyed by the repo label, with the detached HEAD's tip, binds both checkouts (F1, positive control)",
        "not trusted" not in res.detail,
        res.detail,
    )
    write_contract_tips(lab / "tips.tsv", {os.path.realpath(wtbase): str(wtbase)}, drop=lambda r: r[2] == "detached")
    res = run_check(remote_held=lab / "remote-held.tsv")
    s.expect(
        "the same proof without a tip for the detached HEAD is not believed for that checkout (F1)",
        "not trusted" in res.detail and "detached HEAD" in res.detail,
        res.detail,
    )
    write_contract_tips(lab / "tips.tsv", {"elsewhere": str(wtbase)})
    res = run_check(remote_held=lab / "remote-held.tsv")
    s.expect(
        "a proof filed under another repository label binds nothing (F1)",
        "not trusted" in res.detail and "no entry for this repository" in res.detail,
        res.detail,
    )

    # F2 (r2): a checkout the sweep does not list, a one-row sweep, a scan that errors
    s.expect(
        "a fresh scan that finds nothing the sweep lacks PASSes (negative control)",
        check_git_preserved(scan()).status == PASS and check_sweep_fresh(scan()).status == PASS,
    )
    late = work / "late"
    fx(None, "init", "-q", "--template=", "-b", "main", str(late))
    commit_file(late, "only-copy.txt", "never pushed anywhere\n", "only copy")
    res, fresh = check_git_preserved(scan()), check_sweep_fresh(scan())
    s.expect(
        "a repository created after the sweep FAILs git-preserved as universe-miss (F2)",
        res.status == FAIL and codes(res, str(late)) == {"universe-miss"},
        str(blame(res)),
    )
    s.expect(
        "and FAILs sweep-fresh, which names the scan (F2)",
        fresh.status == FAIL and "fresh scan" in fresh.detail,
        fresh.detail,
    )
    shutil.rmtree(late)
    tiny = sa.root / "tiny.tsv"
    tiny.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(sweep_row(sa.repos["safe"])) + "\n")
    os.utime(tiny, None)
    res = check_git_preserved(scan(sweep=tiny, remote_held=None))
    s.expect(
        "a one-row sweep on a disk full of repositories is not 'nothing to preserve' (F2, r2)",
        res.status == FAIL and sum(p.code == "universe-miss" for p in res.problems) >= 10,
        res.detail,
    )
    res = check_sweep_fresh(mk_ctx(sa, discovery_roots=[sa.root / "no-such-root"]))
    s.expect(
        "a scan whose find errors is discovery-incomplete, never an empty universe (F2)",
        res.status == FAIL and "find reported errors" in res.detail,
        res.detail,
    )

    # F2/H3: a git status that fails is a FAIL, where the sweep's `2>/dev/null | wc -l` turned it into dirty=0
    index = Path(sa.repos["safe"]) / ".git" / "index"
    before, saved = index.stat(), index.read_bytes()
    try:
        index.write_bytes(b"this is not an index")
        res = run_check()
        s.expect(
            "a repository whose git status fails is git-error, not clean (F2, H3)",
            res.status == FAIL and "git-error" in codes(res, sa.repos["safe"]),
            str(blame(res)),
        )
    finally:
        index.write_bytes(saved)
        os.utime(index, ns=(before.st_atime_ns, before.st_mtime_ns))
    s.expect("the restored index PASSes again (negative control)", run_check().status == PASS)

    # F7-adjacent: a checkout that cannot be stat-ed is not "vanished"; it FAILs as exposure-unreadable
    locked = sa.root / "locked"
    hidden_repo = make_dirty(locked, "dirtyX")
    unreadable = sa.root / "unreadable.tsv"
    unreadable.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(sweep_row(str(hidden_repo))) + "\n")
    os.utime(unreadable, None)
    try:
        locked.chmod(0)
        res = run_check(sweep=unreadable, remote_held=None)
        s.expect(
            "a checkout under an unreadable parent is exposure-unreadable (F1)",
            res.status == FAIL and "exposure-unreadable" in codes(res, str(hidden_repo)),
            str(blame(res)),
        )
    finally:
        locked.chmod(0o755)

    # F1: a checkout the sweep recorded clean that git can no longer resolve has lost its history, not its exposure
    safe_git = Path(sa.repos["safe"]) / ".git"
    safe_git.rename(safe_git.with_name(".git.off"))
    try:
        res = run_check()
        s.expect(
            "a swept-clean checkout whose .git is gone is exposure-drift, not skipped (F1)",
            res.status == FAIL and "can no longer resolve" in str(res.problems),
            str(blame(res)),
        )
    finally:
        safe_git.with_name(".git.off").rename(safe_git)
    s.expect("with its .git back the world PASSes (negative control)", run_check().status == PASS)

    # F6 (r3): a submodule is a repository of its own
    subs = sa.root / "subs"
    subs.mkdir()
    make_repo(subs, "subseed")
    sup = make_repo(subs, "super")
    fx(sup, "submodule", "add", "-f", "-q", "-b", "main", str(origin_store(subs / "subseed")), "lib")
    fx(sup, "commit", "-q", "-m", "add submodule")
    fx(sup, "push", "-q", str(origin_store(sup)), "main")
    fx(sup, "update-ref", "refs/remotes/origin/main", "HEAD")
    sub = sup / "lib"
    fx(sub, "checkout", "-q", "-b", "feature")
    commit_file(sub, "feature.txt", "exists only in the submodule\n", "submodule-only commit")
    sub_sweep = sa.root / "subs.tsv"
    sub_rows = [sweep_row(str(sup)), sweep_row(str(sub))]
    sub_rows[1][1] = "worktree"  # what git-sweep.sh recorded when it took `.git` being a file for "a linked worktree"
    sub_sweep.write_text("\t".join(SWEEP_COLS) + "\n" + "\n".join("\t".join(r) for r in sub_rows) + "\n")
    os.utime(sub_sweep, None)
    res = run_check(sweep=sub_sweep, remote_held=None)
    s.expect(
        "a submodule swept as a worktree is exposure-drift: git says it owns its git dir (F6, r3)",
        res.status == FAIL
        and "exposure-drift" in codes(res, str(sub))
        and "kind worktree -> repo" in str(res.problems),
        str(blame(res)),
    )
    fixed = sweep_row(str(sub))
    fixed[1] = "repo"
    sub_sweep.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(fixed) + "\n")
    os.utime(sub_sweep, None)
    res = run_check(sweep=sub_sweep, remote_held=None)
    s.expect(
        "swept as a repository, its unpushed commit needs a bundle the run does not have (F6, r3)",
        "exposure-drift" not in codes(res, str(sub)) and "manifest-missing" in codes(res, str(sub)),
        str(blame(res)),
    )

    # F6 (r5): skip-worktree and assume-unchanged hide edits from git status, git diff and the preserved patch
    dirty_b, plain_clean = Path(sa.repos["dirtyB"]), Path(sa.repos["safe"])
    fx(dirty_b, "update-index", "--skip-worktree", "second.txt")
    s.expect(
        "a skip-worktree file that still matches the index is not an exposure (negative control)",
        run_check().status == PASS,
    )
    put(dirty_b / "second.txt", "two\nedited after the run; diff and status hide it\n")
    res = run_check()
    s.expect(
        "an edit to a skip-worktree file is hidden-edit (F6, r5)",
        res.status == FAIL and "hidden-edit" in codes(res, str(dirty_b)),
        str(blame(res)),
    )
    put(dirty_b / "second.txt", "two\n")
    fx(dirty_b, "update-index", "--no-skip-worktree", "second.txt")
    fx(plain_clean, "update-index", "--assume-unchanged", "second.txt")
    put(plain_clean / "second.txt", "two\nedited under assume-unchanged\n")
    res = run_check()
    s.expect(
        "an edit to an assume-unchanged file is hidden-edit (F6)",
        res.status == FAIL and "hidden-edit" in codes(res, str(plain_clean)),
        str(blame(res)),
    )
    put(plain_clean / "second.txt", "two\n")
    fx(plain_clean, "update-index", "--no-assume-unchanged", "second.txt")
    s.expect("with both restored the world PASSes (negative control)", run_check().status == PASS)

    # F6 (r5): ignored files no run copies are a separate UNPROVEN check, never a silent pass
    dirty_a = Path(sa.repos["dirtyA"])
    s.expect("no ignored payload PASSes (negative control)", check_ignored_payload(mk_ctx(sa)).status == PASS)
    (dirty_a / ".git" / "info").mkdir(exist_ok=True)
    (dirty_a / ".git" / "info" / "exclude").write_text("local.db\nnode_modules/\n")
    put(dirty_a / "local.db", "irreplaceable local database\n")
    put(dirty_a / "package.json", "{}\n")  # node_modules is regenerable only beside a tracked manifest (FP-IGNORED-NAME-EXEMPT)
    fx(dirty_a, "add", "package.json")
    put(dirty_a / "node_modules" / "pkg" / "index.js", "regenerable\n")
    res = check_ignored_payload(mk_ctx(sa))
    s.expect(
        "an ignored local database is UNPROVEN and named, a regenerable node_modules is not (F6, r5)",
        res.status == UNPROVEN and "dirtyA: local.db" in res.detail and "node_modules" not in " ".join(res.extra),
        res.detail,
    )
    owner = sa.root / "payload-attest.tsv"
    today = later_stamp()  # F4: a timestamp (a bare date counts from 00:00:00 UTC and cannot vouch for today's files)
    digest = payload_digest(ignored_payload(str(dirty_a)))  # H-IGNORED-ATTESTATION: bound to the list it reviewed
    owner.write_text(f"{dirty_a}\tconductor\t{today}\t{digest}\n")
    s.expect(
        "the owner's attestation naming the checkout settles it",
        check_ignored_payload(mk_ctx(sa, ignored_payload_attestation=owner)).status == PASS,
    )
    owner.write_text(f"{dirty_a}\t\t{today}\t{digest}\n")
    s.expect(
        "an attestation with no signer settles nothing",
        check_ignored_payload(mk_ctx(sa, ignored_payload_attestation=owner)).status == UNPROVEN,
    )
    (dirty_a / "local.db").unlink()
    s.expect(
        "with the database gone the check PASSes again (negative control)",
        check_ignored_payload(mk_ctx(sa)).status == PASS,
    )
    fx(dirty_a, "rm", "-q", "-f", "--cached", "package.json")  # back to the producer's snapshot for the groups below
    (dirty_a / "package.json").unlink()
    shutil.rmtree(dirty_a / "node_modules")  # with its manifest gone it would be ignored payload again
    code, lines = cli(e2e_argv(sa, prepare_e2e(sa)), os.path.isdir)
    s.expect(
        "the new check is part of the end-to-end verdict list",
        any(ln.startswith("PASS ignored-payload") for ln in lines),
    )

    # F3: a disposable path marker is not evidence
    disp = sa.repos["disp"]
    disp_slug = slugify(os.path.realpath(disp + "/.git"), sa.home)
    dest, run = clone_run(sa, "no-disp")
    drop_item(run, "bundle", disp_slug)
    res = run_check(preserve_root=dest)
    s.expect(
        "a row under a disposable marker that no run covers FAILs: the path earns no exemption (F3)",
        res.status == FAIL and codes(res, disp) == {"manifest-missing"},
        str(blame(res)),
    )
    disposals = sa.root / "disposals.tsv"
    res = run_check(preserve_root=dest, disposals=disposals)
    s.expect(
        "an owner-signed disposal record with hashed evidence discharges it and is reported as a waiver (F3)",
        res.status == PASS and [x.path for x in res.waived] == [disp] and "DISPOSED" in res.detail,
        res.detail,
    )
    good = disposals.read_text().splitlines()[1].split("\t")
    for label, row in {
        "a wrong evidence hash": [*good[:4], "0" * 64],
        "no signer": [good[0], good[1], "", *good[3:]],
        "evidence that is a directory": [*good[:3], str(sa.root), good[4]],
        "no evidence": [*good[:3], "", good[4]],
        "a row that is real exposure, not a marker row": [sa.repos["plain"], *good[1:]],
    }.items():
        bad = sa.root / "disposals-bad.tsv"
        bad.write_text("\t".join(DISPOSAL_COLS) + "\n" + "\t".join(row) + "\n")
        res = run_check(preserve_root=dest, disposals=bad)
        s.expect(
            f"a disposal record with {label} is disposal-invalid and discharges nothing (F3)",
            res.status == FAIL and not res.waived and "disposal-invalid" in {p.code for p in res.problems},
            res.detail,
        )
    bad.write_text("\t".join(DISPOSAL_COLS) + "\n" + "\t".join(good) + "\n" + "\t".join(good) + "\n")
    s.expect("two records for one path FAIL", run_check(preserve_root=dest, disposals=bad).status == FAIL)

    # H4: deep verification is the default; the opt-out exists but is not
    # merged with the required-argument change: a context needs the full layout argv, not an empty one
    full_argv = e2e_argv(sb, attestation)
    defaults = make_ctx(build_parser().parse_args(full_argv), os.path.isdir)
    s.expect(
        "deep verification is on by default and --no-deep turns it off (H4)",
        defaults.deep and not make_ctx(build_parser().parse_args([*full_argv, "--no-deep"]), os.path.isdir).deep,
    )
    notheld_slug = slugify(os.path.realpath(sa.repos["notheld"] + "/.git"), sa.home)
    dest, run = clone_run(sa, "truncated")
    bundle = run / "bundles" / f"{notheld_slug}.bundle"
    bundle.write_bytes(bundle.read_bytes()[:-40])
    rehash(run, "bundle", notheld_slug)
    res = check_git_preserved(dataclasses.replace(mk_ctx(sa, preserve_root=dest), deep=defaults.deep))
    s.expect(
        "a truncated bundle with a re-hashed manifest FAILs in the default mode (H4, r12)",
        codes(res, sa.repos["notheld"]) == {"bundle-verify"},
        str(blame(res)),
    )
    partial = sa.repos["partial"]
    tip = fx(partial, "rev-parse", "refs/heads/topic").strip()
    dest, run = clone_run(sa, "gitdir-corrupt")
    slug = slugify(os.path.realpath(partial + "/.git"), sa.home)
    tar_edit(
        run / RunView(run).one("gitdir-tar", slug)["file"], replace={f".git/objects/{tip[:2]}/{tip[2:]}": b"not zlib"}
    )
    rehash(run, "gitdir-tar", slug)
    res = check_git_preserved(dataclasses.replace(mk_ctx(sa, preserve_root=dest), deep=True))
    s.expect(
        "a raw git-dir copy with a corrupt tip object FAILs object verification (H4)",
        codes(res, partial) == {"bundle-verify"} and "fsck" in str(res.problems),
        str(blame(res)),
    )
    s.expect(
        "the pristine raw git-dir copy PASSes the same deep check (negative control)",
        check_git_preserved(dataclasses.replace(mk_ctx(sa), deep=True)).status == PASS,
    )
    saved_headroom = SCRATCH_HEADROOM
    globals()["SCRATCH_HEADROOM"] = 1 << 62
    try:
        res = check_git_preserved(dataclasses.replace(mk_ctx(sa), deep=True))
    finally:
        globals()["SCRATCH_HEADROOM"] = saved_headroom
    s.expect(
        "a raw git-dir copy that cannot be extracted for lack of scratch space FAILs rather than skipping (H4)",
        res.status == FAIL and "no room to extract" in str(res.problems),
        res.detail,
    )

    # H7: a head bundle is judged by the verified repository bundle, not by local remote-tracking refs
    wtdet, wtbase = sa.repos["wtdet"], sa.repos["wtbase"]
    dest, run = clone_run(sa, "thin")
    drop_item(run, "bundle", slugify(os.path.realpath(wtbase + "/.git"), sa.home))
    res = run_check(preserve_root=dest)
    s.expect(
        "a thin head bundle whose prerequisites the repository bundle does not carry is head-uncovered (H7)",
        codes(res, wtdet) == {"head-uncovered"} and "thin" in str(res.problems),
        str(blame(res)),
    )
    # git lists a linked worktree's HEAD among `bundle --all`'s heads; cut it out so the head bundle is what is judged
    dest, run = clone_run(sa, "thin-reachable")
    head_sha = fx(wtdet, "rev-parse", "HEAD").strip()
    repo_slug = slugify(os.path.realpath(wtbase + "/.git"), sa.home)
    repo_bundle = run / RunView(run).one("bundle", repo_slug)["file"]
    header, gap, pack = repo_bundle.read_bytes().partition(b"\n\n")
    kept = [ln for ln in header.split(b"\n") if not ln.startswith(head_sha.encode())]
    repo_bundle.write_bytes(b"\n".join(kept) + gap + pack)
    rehash(run, "bundle", repo_slug)
    s.expect(
        "a thin head bundle whose prerequisites the repository bundle reaches covers the detached HEAD (H7, positive)",
        codes(run_check(preserve_root=dest), wtdet) == set(),
        str(blame(run_check(preserve_root=dest))),
    )
    stray = fx(wtdet, "commit-tree", fx(wtdet, "rev-parse", "HEAD^{tree}").strip(), "-p", "HEAD", "-m", "stray").strip()
    head_slug = slugify(wtdet, sa.home)
    bundle_file = run / RunView(run).one("head-bundle", head_slug)["file"]
    raw = bundle_file.read_bytes()
    at = raw.index(b"\n-") + 2
    bundle_file.write_bytes(raw[:at] + stray.encode() + raw[at + len(stray) :])
    rehash(run, "head-bundle", head_slug)
    res = run_check(preserve_root=dest)
    s.expect(
        "a head bundle prerequisite that the usable repository bundle does not reach is head-uncovered (H7)",
        codes(res, wtdet) == {"head-uncovered"} and "thin" in str(res.problems),
        str(blame(res)),
    )
    dest, run = clone_run(sa, "empty-head")
    drop_item(run, "bundle", slugify(os.path.realpath(wtbase + "/.git"), sa.home))  # else the bundle carries HEAD
    set_field(run, "head-bundle", slugify(wtdet, sa.home), status="empty", file="", bytes="0", sha256="")
    res = run_check(preserve_root=dest)
    s.expect(
        "a head bundle recorded empty is not accepted on the strength of remote-tracking refs (H7)",
        codes(res, wtdet) == {"head-uncovered"} and "remote-tracking" in str(res.problems),
        str(blame(res)),
    )


def st_group_classification(s: Suite, w: World) -> None:
    s.group("classification and producer parity")
    rows = load_sweep(w.sweep)
    plan = build_plan(rows, load_remote_held(w.held))
    names = {Path(n.row["path"]).name: n for n in plan.needs}
    # F3: `disp` sits under a disposable marker and is no longer exempt by its path, so it needs coverage like the rest
    # §5: only a repository the prove lane's file names PROVEN-ALL (and tips.tsv binds) is safe. `wtbase` is not: its
    # linked worktree holds a detached commit no remote has, so the proof cannot be PROVEN-ALL for the repository
    want = {"plain", "dirtyA", "dirtyB", "dirtyC", "dirtyD", "wtbase", "wtdet", "notheld", "orphan", "unborn", "partial", "disp"}
    s.expect("plan: needing entries", set(names) == want, str(sorted(names)))
    s.expect(
        "plan: counts (F2: the four nested repositories are swept; 5 safe: safe and the four nested, each PROVEN-ALL)",
        (plan.entries, plan.safe, plan.disposable, plan.waived) == (18, 5, 1, 1),
        str((plan.entries, plan.safe, plan.disposable, plan.waived)),
    )
    s.expect("plan: PROVEN-ALL never exempts dirty work", names["dirtyA"].dirty)
    s.expect(
        "plan: plain needs a bundle (no origin, unpushed, stash)", names["plain"].bundle and not names["plain"].dirty
    )
    s.expect("plan: detached worktree needs head coverage", names["wtdet"].head)
    s.expect("plan: non-PROVEN-ALL repo is not waived", names["notheld"].bundle)
    no_remote = {"path": "/x", "kind": "repo", "branch": "main", "remote": "NONE", "dirty": "0", "unpushed": "2",
                 "stashes": "0", "head_remote_branches": "0"}  # fmt: skip
    plan_none = build_plan([no_remote], {"/x": {"PROVEN-ALL"}})
    s.expect("plan: PROVEN-ALL cannot waive a repo with no remote", len(plan_none.needs) == 1)
    stash_row = {**no_remote, "remote": "git@example.invalid:o/r.git", "unpushed": "0", "stashes": "1"}
    s.expect("plan: PROVEN-ALL cannot waive a stash", len(build_plan([stash_row], {"/x": {"PROVEN-ALL"}}).needs) == 1)
    clean_row = {**no_remote, "remote": "git@example.invalid:o/r.git", "unpushed": "0"}
    s.expect(
        "plan: clean row listed without PROVEN-ALL is added",
        len(build_plan([clean_row], {"/x": {"UNPROVEN"}}).needs) == 1,
    )
    # §5 (FP-REMOTE-TRUST): absent is not trusted. This used to read "a clean row absent from the file is safe"; the
    # contract reverses it, so a row the prove lane never named needs coverage like any unproven one
    s.expect("plan: clean row absent from the file is UNPROVEN and needs coverage", len(build_plan([clean_row], {}).needs) == 1)
    s.expect(
        "plan: with no remote-held file at all (a sub-check) the same row stays safe",
        len(build_plan([clean_row], None).needs) == 0,
    )
    per_repo = w.root / "held-per-repo.tsv"
    write_held(
        per_repo,
        [
            held_entry(w.repos["held"], "PROVEN-ALL"),
            held_entry(w.repos["notheld"], "UNPROVEN", [w.repos["notheld"], w.repos["wtdet"]]),
        ],
    )
    by_repo = build_plan(rows, load_remote_held(per_repo))
    s.expect(
        "remote-held per-repository shape (`paths` joined by ;) is read: held is waived, every row it does not name needs coverage",
        (by_repo.waived, len(by_repo.needs)) == (1, 17),  # 18 rows less `held`; absent rows are unproven (§5)
        str((by_repo.waived, len(by_repo.needs))),
    )
    loaded = load_remote_held(per_repo)
    s.expect(
        "the per-repository shape carries each checkout's repository label, common dir and gaps (§4)",
        isinstance(loaded, Held)
        and loaded.labels[os.path.realpath(w.repos["held"])] == os.path.realpath(w.repos["held"])
        and loaded.commons[os.path.realpath(w.repos["held"])] == os.path.realpath(w.repos["held"] + "/.git")
        and loaded.gaps[os.path.realpath(w.repos["held"])] == set(),
    )
    per_path = w.root / "held-entries.tsv"
    per_path.write_text(
        f"path\tkind\trepo_verdict\n{w.repos['held']}\trepo\tPROVEN-ALL\n{w.repos['notheld']}\trepo\tUNPROVEN\n"
        "#END rows=2\t#END\t#END\n"
    )
    s.expect(
        "remote-held per-checkout shape (`repo_verdict`) is read",
        build_plan(rows, load_remote_held(per_path)).waived == 1,
    )
    two = w.root / "held-two-rows.tsv"
    two.write_text(f"path\tverdict\n{w.repos['held']}\tPROVEN-ALL\n{w.repos['held']}\tUNPROVEN\n#END rows=2\t#END\n")
    s.expect(
        "a checkout under two rows is held only if every row says so",
        build_plan(rows, load_remote_held(two)).waived == 0,
    )
    real_paths = {ln.split("\t")[0] for ln in w.real.read_text().split("\n")[1:] if ln}
    flagged = {n.row["path"] for n in build_plan(rows, None).needs}
    s.expect(
        "parity: needing set equals the classifier's real.tsv",
        flagged == real_paths,
        f"{len(flagged)} vs {len(real_paths)}",
    )
    for label, text in (
        ("no path column", "x\tverdict\n#END rows=0\t#END\n"),
        ("no verdict column", "path\tnotes\n#END rows=0\t#END\n"),
        ("empty", ""),
    ):
        bad = w.root / "bad-held.tsv"
        bad.write_text(text)
        res = check_git_preserved(mk_ctx(w, remote_held=bad))
        s.expect(
            f"remote-held with {label} fails closed",
            res.status == FAIL and "input-unusable" in blame(res).get(str(w.sweep), set()),
        )


def st_group_git_preserved(s: Suite, w: World) -> None:
    s.group("git-preserved: pristine run")
    env = git_env()
    s.expect(
        "every git call forbids lazy fetch, prompts and index refresh",
        (env["GIT_NO_LAZY_FETCH"], env["GIT_TERMINAL_PROMPT"], env["GIT_OPTIONAL_LOCKS"]) == ("1", "0", "0"),
    )
    res = check_git_preserved(mk_ctx(w))
    s.expect("pristine run PASSes against live state", res.status == PASS, res.detail)
    # F3: bundle 4 -> 5, the marked row `disp` is preserved by the run like any other (no path exemption)
    # §5: wtbase and wtdet join the bundle count (their repository is unproven), and the orphan row counts once per
    # component it needs (head and bundle)
    s.expect("coverage kinds counted", "need dirty=5 bundle=7 head=1 orphan=2" in res.detail, res.detail)
    s.expect("credential-pattern files are reported, not hidden", "credential-pattern" in res.detail, res.detail)
    res = check_git_preserved(mk_ctx(w, remote_held=None))
    s.expect(
        "without remote-held every flagged entry needs a bundle (3), still PASS",
        res.status == PASS and "bundle=6" in res.detail,  # F3: 5 -> 6 with `disp`
        res.detail,
    )
    res = check_git_preserved(mk_ctx(w, deep=True))
    s.expect("deep mode (content compare, pack stream) PASSes", res.status == PASS, res.detail)
    s.expect("missing run root FAILs", check_git_preserved(mk_ctx(w, preserve_root=w.root / "nope")).status == FAIL)
    empty_root = w.root / "empty-root"
    empty_root.mkdir()
    res = check_git_preserved(mk_ctx(w, preserve_root=empty_root))
    s.expect(
        "no run-* directory FAILs as run-missing",
        res.status == FAIL and "run-missing" in blame(res).get(str(empty_root), set()),
    )
    s.expect("unreadable sweep FAILs", check_git_preserved(mk_ctx(w, sweep=w.root / "nope.tsv")).status == FAIL)

    s.group("git-preserved: tampered copies of the run")
    plain, notheld, held = w.repos["plain"], w.repos["notheld"], w.repos["held"]
    plain_common, notheld_common, held_common = (os.path.realpath(r + "/.git") for r in (plain, notheld, held))

    dest, run = clone_run(w, "hash")
    set_field(run, "bundle", slugify(plain_common, w.home), sha256="a" * 64)
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "wrong manifest sha256 FAILs as hash-mismatch",
        res.status == FAIL and blame(res).get(plain) == {"hash-mismatch"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "flip")
    patch = run / "dirty" / f"{slugify(w.repos['dirtyB'], w.home)}.tracked.patch"
    data = bytearray(patch.read_bytes())
    data[-2] ^= 0x01
    patch.write_bytes(bytes(data))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "a flipped byte in an artifact FAILs as hash-mismatch",
        blame(res).get(w.repos["dirtyB"]) == {"hash-mismatch"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "missing-bundle")
    drop_item(run, "bundle", slugify(notheld_common, w.home))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "missing bundle item FAILs as manifest-missing",
        blame(res).get(notheld) == {"manifest-missing"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "waived")
    drop_item(run, "bundle", slugify(held_common, w.home))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect("a PROVEN-ALL repo needs no bundle", res.status == PASS, res.detail)
    res = check_git_preserved(mk_ctx(w, preserve_root=dest, remote_held=None))
    s.expect(
        "the same run FAILs when remote-held is not supplied",
        blame(res).get(held) == {"manifest-missing"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "missing-tar")
    drop_item(run, "untracked-tar", slugify(w.repos["dirtyA"], w.home))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "missing untracked-tar item FAILs", blame(res).get(w.repos["dirtyA"]) == {"manifest-missing"}, str(blame(res))
    )

    dest, run = clone_run(w, "failed")
    set_field(run, "bundle", slugify(plain_common, w.home), status="failed")
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect("bundle item with status failed FAILs", blame(res).get(plain) == {"item-status"}, str(blame(res)))

    dest, run = clone_run(w, "stash")
    stash_patches = [i for i in RunView(run).items if i["item_kind"] == "stash-patch"]
    s.expect("producer wrote a stash-patch for the extra stash entry", len(stash_patches) == 1, str(len(stash_patches)))
    drop_item(run, "stash-patch", slugify(plain_common, w.home))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect("missing stash patch FAILs as stash-missing", blame(res).get(plain) == {"stash-missing"}, str(blame(res)))

    partial, unborn = w.repos["partial"], w.repos["unborn"]
    partial_slug = slugify(os.path.realpath(partial + "/.git"), w.home)
    unborn_slug = slugify(os.path.realpath(unborn + "/.git"), w.home)
    view = RunView(w.run)
    s.expect(
        "producer: a partial clone gets a gitdir-tar and no bundle",
        view.one("gitdir-tar", partial_slug) is not None and view.one("bundle", partial_slug) is None,
    )
    s.expect(
        "producer: an unborn HEAD gets a staged-tar, a gitdir-tar and an empty bundle",
        view.one("staged-tar", slugify(unborn, w.home)) is not None
        and view.one("gitdir-tar", unborn_slug) is not None
        and (view.one("bundle", unborn_slug) or {}).get("status") == "empty",
    )

    dest, run = clone_run(w, "gitdir-missing")
    drop_item(run, "gitdir-tar", partial_slug)
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "a partial clone with no gitdir-tar item FAILs as manifest-missing",
        blame(res).get(partial) == {"manifest-missing"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "gitdir-hash")
    set_field(run, "gitdir-tar", partial_slug, sha256="a" * 64)
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "a gitdir-tar whose manifest hash is wrong FAILs as hash-mismatch",
        blame(res).get(partial) == {"hash-mismatch"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "staged-missing")
    drop_item(run, "staged-tar", slugify(unborn, w.home))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "an unborn HEAD with no staged-tar item FAILs",
        blame(res).get(unborn) == {"manifest-missing"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "unborn-gitdir-missing")
    drop_item(run, "gitdir-tar", unborn_slug)
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "an unborn HEAD with no gitdir-tar item FAILs",
        blame(res).get(unborn) == {"manifest-missing"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "head")
    drop_item(run, "head-bundle", slugify(w.repos["wtdet"], w.home))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "a missing head bundle is covered when the repository bundle carries the worktree HEAD ref",
        res.status == PASS,
        res.detail,
    )
    drop_item(run, "bundle", slugify(os.path.realpath(w.repos["wtbase"] + "/.git"), w.home))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "a missing head bundle and no repository bundle FAILs as head-uncovered",
        blame(res).get(w.repos["wtdet"]) == {"head-uncovered"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "orphan")
    drop_item(run, "orphan-tree-tar", slugify(w.repos["orphan"], w.home))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "missing orphan-tree-tar FAILs as orphan-uncovered",
        blame(res).get(w.repos["orphan"]) == {"orphan-uncovered"},
        str(blame(res)),
    )

    dest, run = clone_run(w, "incomplete")
    drop_item(run, "credential-list", "credential-skipped.txt")
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "a run without its closing rows FAILs as incomplete",
        res.status == FAIL and "run-incomplete" in str(res.problems),
        res.detail,
    )

    dest, run = clone_run(w, "header")
    manifest = run / "MANIFEST.tsv"
    manifest.write_text(manifest.read_text().replace("item_kind", "kind", 1))
    s.expect(
        "a manifest with a foreign header FAILs", check_git_preserved(mk_ctx(w, preserve_root=dest)).status == FAIL
    )

    dest, run = clone_run(w, "verifier")
    honest = (run / "RESULT.txt").read_text()
    (run / "RESULT.txt").write_text(honest.replace("WAIVERS: 0", "WAIVERS: 2", 1))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "a verifier PASS carrying producer WAIVERS is surfaced with its count, while the independently re-verified "
        "coverage counts",
        res.status == PASS and "verifier PASS, 2 producer waiver(s)" in res.detail,
        res.detail,
    )
    (run / "RESULT.txt").write_text("FAIL\nWAIVERS: 2\nbundle x lists 3 refs, manifest says 4\n")
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(  # INT-7 flips the old assertion: a failed verifier no longer lets a re-hashed run count
        "a verifier verdict of FAIL sets the run aside, however well it re-hashes (INT-7)",
        res.status == FAIL and "no usable source" in res.detail and "not PASS" in res.detail,
        res.detail,
    )

    dest, run = clone_run(w, "truncated-bundle")
    bundle = run / "bundles" / f"{slugify(notheld_common, w.home)}.bundle"
    bundle.write_bytes(bundle.read_bytes()[:-40])
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect("a truncated bundle FAILs", blame(res).get(notheld) == {"hash-mismatch"}, str(blame(res)))
    rewrite_manifest(
        run,
        lambda i: (
            {**i, "bytes": str(bundle.stat().st_size), "sha256": sha256_file(bundle)}
            if i["file"] == f"bundles/{bundle.name}"
            else i
        ),
    )
    res = check_git_preserved(mk_ctx(w, preserve_root=dest, deep=True))
    s.expect(
        "a truncated bundle with a re-hashed manifest still FAILs git bundle verify",
        blame(res).get(notheld) == {"bundle-verify"},
        str(blame(res)),
    )


def copy_run_as(world: World, dest: Path) -> None:
    """A copy of the fixture run under another run-* name. The verifier's PASS names the directory it verified (INT-7),
    so the copy's RESULT.txt is re-pointed at its new name; the verdict itself is still the real verifier's."""
    shutil.copytree(world.run, dest, symlinks=True)
    result = dest / "RESULT.txt"
    result.write_text(result.read_text().replace(f"run={world.run} ", f"run={dest} ", 1))


def shifted_run_name(run: Path, seconds: int) -> str:
    stamp = datetime.strptime(run.name[4:], "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC) + timedelta(seconds=seconds)
    return "run-" + stamp.strftime("%Y%m%dT%H%M%SZ")


def make_manual(dest: Path, repo: str) -> Path:
    """A hand-made copy: <dest>/<name>/ (tree and .git) plus <dest>/<name>.MANIFEST.sha256 (./relative paths)."""
    name = os.path.basename(repo)
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(repo, dest / name, symlinks=True)
    lines = []
    for current, _dirs, files in os.walk(dest / name):
        for f in sorted(files):
            full = Path(current) / f
            if not full.is_symlink():
                lines.append(f"{sha256_file(full)}  ./{full.relative_to(dest / name)}\n")
    (dest / f"{name}.MANIFEST.sha256").write_text("".join(lines))
    return dest


def st_group_union(s: Suite, w: World) -> None:
    s.group("git-preserved: union of runs and manual copies")
    plain, dirty_b, unborn = w.repos["plain"], w.repos["dirtyB"], w.repos["unborn"]
    plain_bundle = slugify(os.path.realpath(plain + "/.git"), w.home)
    name_a, name_b = shifted_run_name(w.run, 1), shifted_run_name(w.run, 2)

    root = w.root / "union-complementary"
    for name, kind, slug in ((name_a, "bundle", plain_bundle), (name_b, "tracked-patch", slugify(dirty_b, w.home))):
        copy_run_as(w, root / name)
        drop_item(root / name, kind, slug)
    alone_a = check_git_preserved(mk_ctx(w, preserve_root=root, preserve_runs=[root / name_a]))
    alone_b = check_git_preserved(mk_ctx(w, preserve_root=root, preserve_runs=[root / name_b]))
    s.expect(
        "run A alone lacks plain's bundle and run B alone lacks dirtyB's patch: each FAILs",
        blame(alone_a).get(plain) == {"manifest-missing"} and blame(alone_b).get(dirty_b) == {"manifest-missing"},
        f"{blame(alone_a)} {blame(alone_b)}",
    )
    res = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect("complementary runs together cover everything: PASS", res.status == PASS, res.detail)
    s.expect(
        "the per-row coverage names the run that covers each component",
        any(ln.startswith("covered") and "plain" in ln and f"bundle={name_b}" in ln for ln in res.extra)
        and any(ln.startswith("covered") and "dirtyB" in ln and f"dirty={name_a}" in ln for ln in res.extra),
        "\n".join(res.extra[:4]),
    )

    root = w.root / "union-stale"
    shutil.copytree(w.run, root / w.run.name, symlinks=True)
    early = shifted_run_name(w.run, -86400 * 2)
    copy_run_as(w, root / early)
    old_alone = check_git_preserved(mk_ctx(w, preserve_root=root, preserve_runs=[root / early]))
    s.expect(
        "a run older than the repositories' newest commits is stale and FAILs alone",
        old_alone.status == FAIL and "stale" in {p.code for p in old_alone.problems},
        old_alone.detail,
    )
    res = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect(
        "staleness is judged per covering run: the fresh run covers what the stale run cannot",
        res.status == PASS and not any(early in ln for ln in res.extra if ln.startswith("covered")),
        res.detail,
    )

    root = w.root / "union-incomplete"
    shutil.copytree(w.run, root / w.run.name, symlinks=True)
    copy_run_as(w, root / name_b)
    drop_item(root / name_b, "credential-list", "credential-skipped.txt")
    res = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect(
        "an incomplete run is set aside and named, the complete one still covers",
        res.status == PASS and "ignored incomplete source(s)" in res.detail and name_b in res.detail,
        res.detail,
    )

    root = w.root / "union-manual"
    shutil.copytree(w.run, root / w.run.name, symlinks=True)
    for kind, slug in (
        ("staged-tar", slugify(unborn, w.home)),
        ("gitdir-tar", slugify(os.path.realpath(unborn + "/.git"), w.home)),
        ("bundle", plain_bundle),
    ):
        drop_item(root / w.run.name, kind, slug)
    without = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect(
        "without a manual copy the unborn repo and plain's bundle are uncovered",
        blame(without).get(unborn) == {"manifest-missing"} and blame(without).get(plain) == {"manifest-missing"},
        str(blame(without)),
    )
    manual = root / "manual-1"
    make_manual(manual, unborn)
    make_manual(manual, plain)
    res = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect(
        "manual copies cover the unborn repo's dirty component and plain's bundle component",
        res.status == PASS
        and any("unborn" in ln and "dirty=manual-1" in ln for ln in res.extra)
        and any(ln.endswith("plain: bundle=manual-1") or "plain: bundle=manual-1" in ln for ln in res.extra),
        res.detail + " | " + " ".join(res.extra[:3]),
    )
    staged = manual / "unborn" / "staged.txt"
    original = staged.read_text()
    staged.write_text("tampered\n")
    res = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect(
        "a manual copy that no longer matches its manifest does not cover",
        blame(res).get(unborn) == {"hash-mismatch"},
        str(blame(res)),
    )
    staged.write_text(original)
    manifest_file = manual / "unborn.MANIFEST.sha256"
    kept = manifest_file.read_text()
    manifest_file.write_text("".join(ln for ln in kept.splitlines(keepends=True) if "loose.txt" not in ln))
    res = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect(
        "a current file missing from the manual manifest does not cover",
        blame(res).get(unborn) == {"manual-mismatch"},
        str(blame(res)),
    )
    manifest_file.write_text(kept)
    os.utime(manifest_file, (w.start_ts - 86400, w.start_ts - 86400))
    res = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect(
        "a manual copy older than the repository's newest dirty file is stale",
        blame(res).get(unborn) == {"stale"},
        str(blame(res)),
    )
    os.utime(manifest_file, None)
    s.expect("restored manual copy covers again", check_git_preserved(mk_ctx(w, preserve_root=root)).status == PASS)
    other = root / "manual-2"
    make_manual(other, unborn)
    fx(other / "unborn", "remote", "add", "origin", "https://example.invalid/other.git")
    (other / "unborn.MANIFEST.sha256").write_text(
        "".join(
            f"{sha256_file(Path(c) / f)}  ./{(Path(c) / f).relative_to(other / 'unborn')}\n"
            for c, _d, fs in os.walk(other / "unborn")
            for f in sorted(fs)
        )
    )
    shutil.rmtree(manual)
    res = check_git_preserved(mk_ctx(w, preserve_root=root))
    s.expect(
        "a same-named copy with a different origin is a different repository and never covers",
        blame(res).get(unborn) == {"manifest-missing"},
        str(blame(res)),
    )


def write_rescue_manifest(recovery: Path, rel: str) -> None:
    """What tm-rescue-verify.sh leaves at the root of a recovery directory: sha256 of every file, paths from the root."""
    lines = []
    for current, _dirs, names in os.walk(recovery / rel):
        for name in sorted(names):
            full = Path(current) / name
            if not full.is_symlink():
                lines.append(f"{sha256_file(full)}  {full.relative_to(recovery)}\n")
    (recovery / "RESCUE-MANIFEST.sha256").write_text("".join(lines))


def st_group_vanished(s: Suite, w: World) -> None:
    s.group("git-preserved: vanished entries and the recovery copy")
    home = w.root / "fakehome"
    home.mkdir(exist_ok=True)  # H2 reads the device of $HOME, so the stand-in home must exist
    recovery = w.root / "recovered-from-test"
    gone = str(home / "Workspace" / "gone")
    copy = recovery / "Workspace" / "gone"
    copy.parent.mkdir(parents=True)
    repo = make_unpushed(copy.parent, "gone")
    write_rescue_manifest(recovery, "Workspace/gone")  # F8: a recovered tree is accepted only if it re-hashes
    row = sweep_row(str(repo))
    row[0] = gone
    sweep = w.root / "vanished.tsv"
    sweep.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(row) + "\n")
    ctx = mk_ctx(w, sweep=sweep, remote_held=None, home=str(home), recovery_root=recovery)
    res = check_git_preserved(ctx)
    s.expect(
        "vanished entry with a matching recovery copy is accepted",
        res.status == PASS and "recovery=1" in res.detail,
        res.detail,
    )
    res = check_git_preserved(dataclasses.replace(ctx, recovery_root=None))
    s.expect(
        "vanished entry with no recovery directory FAILs",
        res.status == FAIL and "row-vanished" in str(res.problems),
        res.detail,
    )
    res = check_git_preserved(dataclasses.replace(ctx, recovery_root=w.root / "recovered-empty"))
    s.expect("vanished entry absent from the recovery directory FAILs", res.status == FAIL, res.detail)
    other = str(home / "Workspace" / "other")
    sweep2 = w.root / "vanished2.tsv"
    sweep2.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join([other, *row[1:]]) + "\n")
    res = check_git_preserved(dataclasses.replace(ctx, sweep=sweep2))
    s.expect(
        "a vanished entry with no copy at its path FAILs",
        res.status == FAIL and "absent from the recovery" in res.detail,
        res.detail,
    )
    commit_file(repo, "extra.txt", "x\n", "extra local-only commit")
    write_rescue_manifest(recovery, "Workspace/gone")  # re-listed, so only the unpushed count can be at fault
    res = check_git_preserved(ctx)
    s.expect(
        "a recovery copy whose unpushed count differs FAILs",
        res.status == FAIL and "unpushed is 2" in res.detail,
        res.detail,
    )
    outside = w.root / "elsewhere" / "gone"
    sweep3 = w.root / "vanished3.tsv"
    sweep3.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join([str(outside), *row[1:]]) + "\n")
    res = check_git_preserved(dataclasses.replace(ctx, sweep=sweep3))
    s.expect("a vanished entry outside $HOME has no recovery location and FAILs", res.status == FAIL, res.detail)


WAIVER_HEADER = "path\treason\tevidence_path\tevidence_sha256\tsigner\tkind\n"  # F7: the contract grew two columns


def vanished_row(w: World) -> list[str]:
    """A flagged sweep row (4 unpushed commits) whose checkout no longer exists."""
    return [str(w.root / "work" / "reaped-clone"), "repo", "main", "git@example.invalid:o/r.git", "0", "4", "0", "6"]


def waiver_row(
    path: str, evidence: Path, *, reason: str = "owner-sanctioned reap; remote holds the work", **over: str
) -> tuple[str, ...]:
    """One well-formed waiver line; every negative control overrides exactly one field."""
    fields = {
        "path": path,
        "reason": reason,
        "evidence_path": str(evidence),
        "evidence_sha256": sha256_file(evidence),
        "signer": "conductor",
        "kind": "remote-held",
    }
    fields.update(over)
    return tuple(fields[c] for c in WAIVER_COLS)


def st_group_waivers(s: Suite, w: World) -> None:
    s.group("waivers for vanished rows")
    row = vanished_row(w)
    gone = row[0]
    sweep = w.root / "waiver-sweep.tsv"
    sweep.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(row) + "\n")
    evidence = w.root / "evidence.md"
    # F7: evidence must name the waived path (here the vanished clone, and `safe` for the still-existing case below)
    evidence.write_text(f"reaped by the sanctioned run: {gone}\nremote holds newer branches\n{w.repos['safe']}\n")
    wfile = w.root / "waivers.tsv"

    def write(*rows: tuple[str, ...], header: str = WAIVER_HEADER) -> None:
        wfile.write_text(header + "".join("\t".join(r) + "\n" for r in rows))

    ctx = mk_ctx(w, sweep=sweep, remote_held=None, waivers=wfile)
    good = waiver_row(gone, evidence)
    base = check_git_preserved(dataclasses.replace(ctx, waivers=None))
    s.expect(
        "without a waiver the vanished row FAILs",
        base.status == FAIL and blame(base).get(gone) == {"row-vanished"},
        str(blame(base)),
    )
    write(good)
    res = check_git_preserved(ctx)
    s.expect(
        "a vanished row with reason, allow-listed signer, kind and re-hashed evidence is WAIVED and the check PASSes",
        res.status == PASS and [x.path for x in res.waived] == [gone] and not res.problems,
        res.detail,
    )
    s.expect(
        "the waiver carries its signer, kind and the exposure it gives up",
        res.waived[0].signer == "conductor"
        and res.waived[0].kind == "remote-held"
        and "unpushed=4" in res.waived[0].exposure,
        str(res.waived[0]),
    )
    write(waiver_row(gone, evidence, evidence_path="evidence.md"))
    s.expect(
        "a relative evidence_path resolves beside the waivers file",
        check_git_preserved(ctx).status == PASS,
        check_git_preserved(ctx).detail,
    )
    other = w.root / "other-evidence.md"
    other.write_text("a log that names some other checkout entirely\n")
    link = w.root / "evidence-link.md"
    link.unlink(missing_ok=True)
    os.symlink(evidence, link)
    future = w.root / "evidence-future.md"
    future.write_text(f"{gone}\n")
    os.utime(future, (time.time() + 7200, time.time() + 7200))
    # each case differs from `good` by exactly one defect; the second element must appear in the failure
    cases = {
        "no reason": (waiver_row(gone, evidence, reason=""), "no reason"),
        "a nonexistent evidence path": (
            waiver_row(gone, evidence, evidence_path=str(w.root / "nope.md")),
            "unreadable",
        ),
        "no evidence path": (waiver_row(gone, evidence, evidence_path=""), "no evidence_path"),
        "no signer": (waiver_row(gone, evidence, signer=""), "no signer"),
        "a path that is not in the sweep": (waiver_row("/not/in/the/sweep", evidence), "not a row of the sweep"),
        "a directory as evidence": (
            waiver_row(gone, evidence, evidence_path=str(w.root), evidence_sha256="0" * 64),
            "regular file",
        ),
        "a symlink as evidence": (waiver_row(gone, evidence, evidence_path=str(link)), "regular file"),
        "the sweep itself as evidence (it lists every path)": (waiver_row(gone, sweep), "artifact under judgment"),
        "the waivers file itself as evidence": (
            waiver_row(gone, evidence, evidence_path=str(wfile)),
            "waivers file itself",
        ),
        "a wrong evidence_sha256": (waiver_row(gone, evidence, evidence_sha256="0" * 64), "sha256 differs"),
        "no evidence_sha256": (waiver_row(gone, evidence, evidence_sha256=""), "not a 64-hex"),
        "evidence that never names the path": (waiver_row(gone, other), "never mentions"),
        "evidence dated in the future": (waiver_row(gone, future), "future"),
        "a signer who is not on the allow-list": (waiver_row(gone, evidence, signer="anyone"), "allow-list"),
        "an unknown kind": (waiver_row(gone, evidence, kind="because-i-said-so"), "kind"),
    }
    for label, (bad, needle) in cases.items():
        write(bad)
        res = check_git_preserved(ctx)
        s.expect(
            f"a waiver with {label} FAILs and does not waive the row",
            res.status == FAIL
            and not res.waived
            and "waiver-invalid" in str(res.problems)
            and needle in str(res.problems),
            f"{needle!r} not in {res.problems}",
        )
    write(waiver_row(gone, evidence) + ("2999-01-01",), header=WAIVER_HEADER.rstrip("\n") + "\tsigned_at\n")
    res = check_git_preserved(ctx)
    s.expect(
        "a future-dated signed_at FAILs",
        res.status == FAIL and not res.waived and "signed_at" in str(res.problems),
        str(res.problems),
    )
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    write(waiver_row(gone, evidence) + (today,), header=WAIVER_HEADER.rstrip("\n") + "\tsigned_at\n")
    s.expect(
        "a signed_at of today PASSes (negative control for the future check)", check_git_preserved(ctx).status == PASS
    )
    write(good)
    res = check_git_preserved(dataclasses.replace(ctx, waiver_signers=None))
    s.expect(
        "waivers with no signer allow-list at all FAIL (no signer can be verified)",
        res.status == FAIL and not res.waived and "allow-list" in str(res.problems),
        str(res.problems),
    )
    os.utime(wfile, (time.time() + 7200, time.time() + 7200))
    res = check_git_preserved(ctx)
    s.expect(
        "a future-dated waivers file FAILs",
        res.status == FAIL and not res.waived and "future" in str(res.problems),
        str(res.problems),
    )
    os.utime(wfile, None)
    write(good, waiver_row("/not/in/the/sweep", evidence))
    res = check_git_preserved(ctx)
    s.expect(
        "a bogus waiver FAILs the check even beside a good one",
        res.status == FAIL and len(res.waived) == 1 and {p.code for p in res.problems} == {"waiver-invalid"},
        str(blame(res)),
    )
    write(good, good)
    s.expect("two waivers for one path FAIL", check_git_preserved(ctx).status == FAIL)
    wfile.write_text("path\treason\tevidence_path\tsigner\n" + f"{gone}\treaped\t{evidence}\tconductor\n")
    s.expect(
        "the old four-column header (no evidence_sha256, no kind) FAILs",
        check_git_preserved(ctx).status == FAIL and not check_git_preserved(ctx).waived,
    )
    s.expect(
        "an unreadable waivers file FAILs",
        check_git_preserved(dataclasses.replace(ctx, waivers=w.root / "no-such-waivers.tsv")).status == FAIL,
    )
    write(good, waiver_row(w.repos["safe"], evidence))
    res = check_git_preserved(mk_ctx(w, sweep=w.sweep, waivers=wfile))
    s.expect(
        "a still-existing checkout can never be waived",
        res.status == FAIL
        and blame(res).get(w.repos["safe"]) == {"waiver-invalid"}
        and "still exists" in str(res.problems),
        str(blame(res)),
    )

    dest, run = clone_run(w, "waive-live")
    drop_item(run, "bundle", slugify(os.path.realpath(w.repos["plain"] + "/.git"), w.home))
    plain_evidence = w.root / "plain-evidence.md"
    plain_evidence.write_text(f"{w.repos['plain']}\n")
    write(waiver_row(w.repos["plain"], plain_evidence))
    res = check_git_preserved(mk_ctx(w, preserve_root=dest, waivers=wfile))
    s.expect(
        "a still-existing UNCOVERED repo is not waivable: its gap stays and the waiver is invalid",
        res.status == FAIL and blame(res).get(w.repos["plain"]) == {"manifest-missing", "waiver-invalid"},
        str(blame(res)),
    )
    s.expect("the waiver for a surviving repo is never applied", not res.waived)

    # F7 / r9a: a checkout that is merely UNREADABLE (a chmod-000 parent: the TCC analogue) is not vanished
    locked = w.root / "locked"
    held_back = make_dirty(locked, "dirtyX")
    eperm_sweep = w.root / "eperm.tsv"
    eperm_sweep.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(sweep_row(str(held_back))) + "\n")
    eperm_evidence = w.root / "eperm-evidence.md"
    eperm_evidence.write_text(f"{held_back}\n")
    write(waiver_row(str(held_back), eperm_evidence))
    eperm_ctx = mk_ctx(w, sweep=eperm_sweep, remote_held=None, waivers=wfile)
    os.chmod(locked, 0)
    try:
        res = check_git_preserved(eperm_ctx)
    finally:
        os.chmod(locked, 0o755)
    s.expect(
        "a live repo under an unreadable parent is NOT waived: unreadable is not vanished",
        res.status == FAIL
        and not res.waived
        and "cannot confirm the path is gone" in str(res.problems)  # the waiver layer's own refusal
        and "cannot confirm the checkout is gone" in str(res.problems)  # the row layer's
        # merged: the live-exposure layer (ready-a) refuses the unreadable path too, so three layers name it
        and blame(res).get(str(held_back)) == {"waiver-invalid", "row-unverifiable", "exposure-unreadable"},
        str(res.problems),
    )
    shutil.rmtree(locked)
    s.expect(
        "the same waiver PASSes once the path is really gone (negative control for the unreadable case)",
        check_git_preserved(eperm_ctx).status == PASS and len(check_git_preserved(eperm_ctx).waived) == 1,
        check_git_preserved(eperm_ctx).detail,
    )

    # F7 / r9b: a repo moved to a Trash directory is gone from its path but its data is on disk; the waiver that
    # cites the waivers file as its own evidence is refused, so the move cannot be laundered into a waiver
    moved = Path(w.repos["dirtyA"])
    trash = w.root / "Trash"
    trash.mkdir(exist_ok=True)
    moved_sweep = w.root / "moved.tsv"
    moved_sweep.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(sweep_row(str(moved))) + "\n")
    shutil.move(str(moved), str(trash / "dirtyA"))
    try:
        write(waiver_row(str(moved), evidence, evidence_path=str(wfile)))
        res = check_git_preserved(mk_ctx(w, sweep=moved_sweep, remote_held=None, waivers=wfile))
        s.expect(
            "a repo moved to the Trash with the waivers file as its evidence is not waived",
            res.status == FAIL and not res.waived and "waivers file itself" in str(res.problems),
            str(res.problems),
        )
    finally:
        shutil.move(str(trash / "dirtyA"), str(moved))


def st_group_sweep(s: Suite, w: World) -> None:
    s.group("sweep-fresh")
    d = w.root / "sweepcase"
    d.mkdir()
    sweep = d / "git.tsv"
    copy_sweep(w.sweep, sweep)
    ctx = mk_ctx(w, sweep=sweep)
    s.expect("fresh sweep PASSes", check_sweep_fresh(ctx).status == PASS)
    old = time.time() - 3600
    os.utime(sweep, (old, old))
    res = check_sweep_fresh(ctx)
    s.expect("stale sweep FAILs", res.status == FAIL and "stale" in res.detail, res.detail)
    s.expect(
        "the age bound is a parameter",
        check_sweep_fresh(dataclasses.replace(ctx, max_sweep_age_min=120)).status == PASS,
    )
    s.expect("missing sweep FAILs", check_sweep_fresh(mk_ctx(w, sweep=d / "none.tsv")).status == FAIL)
    future = time.time() + 7200
    os.utime(sweep, (future, future))
    s.expect("a future-dated sweep FAILs", check_sweep_fresh(ctx).status == FAIL)
    os.utime(sweep, None)
    (d / "find.err").write_text("find: permission denied\n")
    res = check_sweep_fresh(ctx)
    s.expect("a non-empty find.err FAILs", res.status == FAIL and "find.err" in res.detail, res.detail)
    (d / "find.err").write_text("")
    sweep.write_text("\t".join(SWEEP_COLS) + "\n")
    s.expect("a sweep with zero entries FAILs", check_sweep_fresh(ctx).status == FAIL)
    sweep.write_text("path\tkind\n/x\trepo\n")
    s.expect("a sweep with a foreign header FAILs", check_sweep_fresh(ctx).status == FAIL)


def make_vols(w: World) -> Path:
    vols = w.root / "vols"
    main_repo = vols / "VolA" / "main"
    put(main_repo / ".git" / "HEAD", "ref: refs/heads/main\n")
    put(vols / "VolA" / "wt-rel" / ".git", "gitdir: ../main/.git/worktrees/wt\n")
    put(vols / "VolA" / "wt-abs" / ".git", f"gitdir: {main_repo}/.git/worktrees/wt2\n")
    put(vols / "VolA" / "notes" / ".git", "not a gitfile\n")
    (vols / "VolB").mkdir(parents=True, exist_ok=True)
    return vols


def st_group_externals(s: Suite, w: World) -> None:
    s.group("no-external-dependency")
    vols = make_vols(w)
    ctx = mk_ctx(w, externals=["VolA", "VolB"], volumes_root=vols)
    res = check_no_external_dependency(ctx)
    s.expect(
        "clean volumes PASS (relative and absolute in-volume gitfiles)",
        res.status == PASS and "2 gitfile(s)" in res.detail,
        res.detail,
    )
    live_admin = f"{w.repos['plain']}/.git"  # a Mac-side admin directory that exists
    put(vols / "VolB" / "gone" / ".git", f"gitdir: {MAC_PREFIXES[0]}/a/repo/.git/worktrees/gone\n")
    res = check_no_external_dependency(ctx)
    s.expect(
        "an ORPHANED gitfile (its Mac admin dir is already gone) is an INFO line, not a failure",
        res.status == PASS and len(res.info) == 1 and res.info[0].startswith("1 gitfile(s) already point"),
        f"{res.detail} {res.info}",
    )
    put(vols / "VolB" / "x" / ".git", f"gitdir: {live_admin}\n")
    res = check_no_external_dependency(ctx)
    s.expect(
        "a LIVE gitfile (its Mac admin dir exists) FAILs",
        res.status == FAIL and blame(res).get(str(vols / "VolB" / "x" / ".git")) == {"mac-dependency"},
        res.detail,
    )
    s.expect(
        "the orphans are still reported beside a live failure, with their count, and no count is hardcoded",
        "1 LIVE worktree(s)" in res.detail and res.info and res.info[0].startswith("1 gitfile(s)"),
        f"{res.detail} {res.info}",
    )
    (vols / "VolB" / "x" / ".git").unlink()
    (vols / "VolB" / "gone" / ".git").unlink()
    deep = vols / "VolA" / "a" / "b"
    put(deep / ".git", f"gitdir: {os.path.relpath(live_admin, deep)}\n")
    res = check_no_external_dependency(ctx)
    s.expect(
        "a relative gitfile that resolves to a live Mac admin dir FAILs",
        res.status == FAIL and blame(res).get(str(deep / ".git")) == {"mac-dependency"},
        res.detail,
    )
    (deep / ".git").unlink()
    put(
        vols / "VolB" / "fw" / ".git", f"gitdir: /System/Volumes/Data{os.path.realpath(live_admin)}\n"
    )  # the firmlink spelling
    s.expect(
        "the firmlinked /System/Volumes/Data/Users alias is recognised as the Mac",
        check_no_external_dependency(ctx).status == FAIL,
    )
    (vols / "VolB" / "fw" / ".git").unlink()
    res = check_no_external_dependency(dataclasses.replace(ctx, externals=["VolA", "VolMissing"]))
    s.expect(
        "a missing volume FAILs, it is never skipped",
        res.status == FAIL and "not-mounted" in str(res.problems),
        res.detail,
    )
    res = check_no_external_dependency(dataclasses.replace(ctx, is_mount=os.path.ismount))
    s.expect(
        "a directory that is not a mount point FAILs",
        res.status == FAIL and "not-mounted" in str(res.problems),
        res.detail,
    )
    put(vols / "VolB" / "q" / "q" / "q" / "q" / "q" / ".git", f"gitdir: {live_admin}\n")
    res = check_no_external_dependency(ctx)
    s.expect(
        "F4: the default scan has no depth bound, so a live gitfile six levels down is found",  # was: depth>5 PASSed
        res.status == FAIL
        and blame(res).get(str(vols / "VolB" / "q" / "q" / "q" / "q" / "q" / ".git")) == {"mac-dependency"},
        res.detail,
    )
    res = check_no_external_dependency(dataclasses.replace(ctx, gitfile_depth=5))
    s.expect(
        "F4: an explicit depth bound FAILs as scan-truncated when anything lies below it",
        res.status == FAIL and "scan-truncated" in {p.code for p in res.problems},
        res.detail,
    )
    s.expect(
        "depth bound is a parameter",
        check_no_external_dependency(dataclasses.replace(ctx, gitfile_depth=7)).status == FAIL,
    )
    shutil.rmtree(vols / "VolB" / "q")
    s.expect(
        "F4: a bound with nothing below it is honest and PASSes (negative control for scan-truncated)",
        check_no_external_dependency(dataclasses.replace(ctx, gitfile_depth=5)).status == PASS,
    )


def shasum_line(path: Path, rel: str, star: bool = False) -> str:
    return f"{sha256_file(path)} {'*' if star else ' '}{rel}\n"


def stamp_of(run: Path) -> float:
    """The UTC stamp in a run directory's name, as epoch seconds."""
    match = RUN_RE.match(run.name)
    assert match, run.name
    return datetime.strptime(match.group(1), "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC).timestamp()


def put_source(path: Path, data: str | bytes, run: Path) -> None:
    """A live source file last modified an hour BEFORE the homing run's stamp (H5 compares the two)."""
    put(path, data)
    before = stamp_of(run) - 3600
    os.utime(path, (before, before))


def st_group_t7(s: Suite, w: World) -> None:
    s.group("t7-unique-consolidated")
    src, copy = w.root / "t7src", w.root / "t7copy"
    for base in (src, copy):
        put(base / "a" / "b.bin", bytes(range(200)))
        put(base / "c.txt", "hello\n")
    (copy / "MANIFEST.sha256").write_text(
        shasum_line(copy / "a/b.bin", "a/b.bin") + shasum_line(copy / "c.txt", "c.txt", star=True)
    )
    ctx = mk_ctx(w, t7_unique=copy, t7_source=src)
    res = check_t7_unique(ctx)
    s.expect("consolidated copy PASSes", res.status == PASS and "2 files" in res.detail, res.detail)
    s.expect(
        "hashing the originals too PASSes",
        check_t7_unique(dataclasses.replace(ctx, hash_t7_originals=True)).status == PASS,
    )
    original = src / "c.txt"
    original.write_text("HELLO\n")
    s.expect(
        "an original that differs only in content passes by size (documented)", check_t7_unique(ctx).status == PASS
    )
    s.expect(
        "--hash-t7-originals catches it",
        check_t7_unique(dataclasses.replace(ctx, hash_t7_originals=True)).status == FAIL,
    )
    original.write_text("hello world\n")
    s.expect("an original whose size differs FAILs", check_t7_unique(ctx).status == FAIL)
    original.write_text("hello\n")
    (src / "a" / "b.bin").unlink()
    res = check_t7_unique(ctx)
    s.expect(
        "an original removed from the T7 FAILs", res.status == FAIL and "original missing" in res.detail, res.detail
    )
    put(src / "a" / "b.bin", bytes(range(200)))
    (copy / "c.txt").write_text("tampered\n")
    res = check_t7_unique(ctx)
    s.expect(
        "a copy that no longer matches its hash FAILs",
        res.status == FAIL and "sha256 mismatch" in res.detail,
        res.detail,
    )
    (copy / "c.txt").write_text("hello\n")
    (copy / "a" / "b.bin").unlink()
    s.expect("a copy missing from the external FAILs", check_t7_unique(ctx).status == FAIL)
    put(copy / "a" / "b.bin", bytes(range(200)))
    s.expect("restored fixture PASSes again", check_t7_unique(ctx).status == PASS)
    res = check_t7_unique(dataclasses.replace(ctx, is_mount=lambda p: not p.endswith("t7src")))
    s.expect("an unmounted T7 FAILs", res.status == FAIL and "not mounted" in res.detail, res.detail)
    manifest = copy / "MANIFEST.sha256"
    manifest.write_text(manifest.read_text() + f"{'0' * 64}  ../escape\n")
    s.expect("a path-traversal entry FAILs", check_t7_unique(ctx).status == FAIL)
    manifest.write_text("garbage\n")
    s.expect("a malformed manifest FAILs", check_t7_unique(ctx).status == FAIL)
    s.expect("a missing manifest FAILs", check_t7_unique(mk_ctx(w, t7_unique=w.root / "nope")).status == FAIL)


def st_group_nongit(s: Suite, w: World) -> None:
    s.group("nongit-homed")
    parent = w.root / "nongit"
    run = parent / "run-20261021T120000Z-4242"  # the homing helper's run-<UTC stamp>-<pid> naming
    put(run / "data" / "x.txt", "x\n")
    put(run / "data" / "y.bin", bytes(range(50)))
    sums = shasum_line(run / "data/x.txt", "data/x.txt") + shasum_line(run / "data/y.bin", "data/y.bin")
    (run / "MANIFEST.sha256").write_text(sums)
    (run / "RESULT.txt").write_text("PASS\nitems=2\n")
    # H5: the homed copy is compared with the live source it was made from, named by the homing tool's items file
    src = w.root / "nongit-src"
    put_source(src / "data" / "x.txt", "x\n", run)
    put_source(src / "data" / "y.bin", bytes(range(50)), run)
    items1 = w.root / "nongit-items.tsv"
    items1.write_text(f"# fixture items\ndata\t{src / 'data'}\tdata\n")
    ctx = mk_ctx(w, nongit_runs=[run], nongit_items=[items1])
    res = check_nongit_homed(ctx)
    s.expect(
        "PASS RESULT.txt with a matching manifest PASSes",
        res.status == PASS and "2 manifest entries" in res.detail,
        res.detail,
    )
    s.expect(
        "the parent directory resolves to the newest run-*",
        check_nongit_homed(mk_ctx(w, nongit_runs=[parent], nongit_items=[items1])).status == PASS,
    )
    second = w.root / "nongit-runtime"
    run2 = second / "run-20261021T130000Z-77"
    put(run2 / "home" / "state.db", bytes(range(30)))
    (run2 / "MANIFEST.sha256").write_text(shasum_line(run2 / "home/state.db", "home/state.db"))
    (run2 / "RESULT.txt").write_text("mode=apply\nRESULT: PASS\n")
    put_source(src / "home" / "state.db", bytes(range(30)), run2)
    items2 = w.root / "nongit-items-runtime.tsv"
    items2.write_text(f"state\t{src / 'home' / 'state.db'}\thome/state.db\n")
    both = mk_ctx(w, nongit_runs=[parent, second], nongit_items=[items1, items2])
    res = check_nongit_homed(both)
    s.expect(
        "two homing sets must both PASS",
        res.status == PASS and "run-20261021T130000Z-77" in res.detail and "run-20261021T120000Z-4242" in res.detail,
        res.detail,
    )
    (run2 / "RESULT.txt").write_text("mode=apply\nproblem=DRIFT home/state.db\nRESULT: FAIL\n")
    res = check_nongit_homed(both)
    s.expect(
        "one failing set (live agent state drifted) makes nongit-homed FAIL",
        res.status == FAIL and "nongit-runtime/run-20261021T130000Z-77" in res.detail,
        res.detail,
    )
    s.expect(
        "a missing second set FAILs",
        check_nongit_homed(mk_ctx(w, nongit_runs=[parent, w.root / "gone"])).status == FAIL,
    )
    s.expect("no configured set FAILs", check_nongit_homed(mk_ctx(w, nongit_runs=[])).status == FAIL)
    (run / "RESULT.txt").write_text("mode=apply\nitems=2\nRESULT: PASS\n")
    s.expect("the homing helper's trailing `RESULT: PASS` is accepted", check_nongit_homed(ctx).status == PASS)
    (run / "RESULT.txt").write_text("mode=apply\nRESULT: FAIL\n")
    s.expect("RESULT: FAIL FAILs", check_nongit_homed(ctx).status == FAIL)
    (run / "RESULT.txt").write_text("mode=apply\nRESULT: DRY-RUN (nothing written)\n")
    s.expect("a dry run is not a PASS", check_nongit_homed(ctx).status == FAIL)
    (run / "RESULT.txt").write_text("mode=apply\nproblem=mismatch home/x\nRESULT: PASS\n")
    res = check_nongit_homed(ctx)
    s.expect(
        "a PASS that still lists a problem= line FAILs", res.status == FAIL and "problem=" in res.detail, res.detail
    )
    (run / "RESULT.txt").write_text("PASS\n")
    (run / "EXCLUDED.tsv").write_text("kind\tsource_path\tbytes\treason\ncredential\t/x/.key\t3\tcredential name\n")
    res = check_nongit_homed(ctx)
    s.expect(
        "files left out of the homing are reported, not hidden",
        res.status == PASS and "1 credential" in res.detail,
        res.detail,
    )
    (run / "EXCLUDED.tsv").unlink()
    empty_parent = w.root / "nongit-empty"
    empty_parent.mkdir()
    res = check_nongit_homed(mk_ctx(w, nongit_runs=[empty_parent]))
    s.expect(
        "a parent with no run-* child FAILs", res.status == FAIL and "no run-* directory" in res.detail, res.detail
    )
    (run / "data" / "x.txt").write_text("changed\n")
    res = check_nongit_homed(ctx)
    s.expect(
        "a manifest entry that no longer re-hashes equal FAILs",
        res.status == FAIL and "sha256 mismatch" in res.detail,
        res.detail,
    )
    (run / "data" / "x.txt").write_text("x\n")
    (run / "data" / "y.bin").unlink()
    s.expect("a manifest entry whose file is gone FAILs", check_nongit_homed(ctx).status == FAIL)
    put(run / "data" / "y.bin", bytes(range(50)))
    (run / "MANIFEST.sha256").unlink()
    (run / "MANIFEST.tsv").write_text(
        "sha256\tbytes\trel_path\tkind\n"
        + "".join(f"{sha256_file(run / r)}\t0\t{r}\tfile\n" for r in ("data/x.txt", "data/y.bin"))
    )
    s.expect("the MANIFEST.tsv form is accepted", check_nongit_homed(ctx).status == PASS)
    (run / "MANIFEST.tsv").unlink()
    s.expect("no manifest FAILs", check_nongit_homed(ctx).status == FAIL)
    (run / "MANIFEST.sha256").write_text("")
    s.expect("an empty manifest FAILs", check_nongit_homed(ctx).status == FAIL)
    s.expect("a missing directory FAILs", check_nongit_homed(mk_ctx(w, nongit_runs=[w.root / "nope"])).status == FAIL)
    (run / "RESULT.txt").unlink()
    s.expect("a missing RESULT.txt FAILs", check_nongit_homed(ctx).status == FAIL)


def st_group_credentials_backblaze(s: Suite, w: World) -> None:
    s.group("credential checks, backblaze-offsite, human-erase")
    today = datetime.now(UTC).strftime("%Y-%m-%d")  # H6: an attestation may not be dated ahead of now
    ok, bad, imp = (w.root / n for n in ("wall-ok.py", "wall-bad.py", "wall-import.py"))
    ok.write_text("import sys\nassert sys.argv[1:] == ['--check']\nprint('registered')\n")
    bad.write_text("import sys\nprint('homeless atom')\nsys.exit(1)\n")
    imp.write_text(
        "import sys\nprint('ModuleNotFoundError: No module named yaml (import)', file=sys.stderr)\nsys.exit(1)\n"
    )
    res = check_credential_registry(mk_ctx(w, credential_wall=ok))
    s.expect(
        "credential-wall exit 0 PASSes the registry check and says it proves the registry only",
        res.status == PASS and res.check_id == "credential-registry-complete" and "registry only" in res.detail,
        res.detail,
    )
    s.expect("credential-wall exit 1 FAILs", check_credential_registry(mk_ctx(w, credential_wall=bad)).status == FAIL)
    res = check_credential_registry(mk_ctx(w, credential_wall=imp))
    s.expect(
        "an interpreter import failure FAILs and says so",
        res.status == FAIL and "import failure" in res.detail,
        res.detail,
    )
    s.expect("an absent credential-wall is UNPROVEN", check_credential_registry(mk_ctx(w)).status == UNPROVEN)

    items = w.root / "credential-items.txt"
    res = check_credential_route_items(mk_ctx(w))
    s.expect(
        "credential-route items are UNPROVEN with no attestation, even though the registry passed",
        res.status == UNPROVEN and res.check_id == "credential-route-items-homed",
        res.detail,
    )
    items.write_text(
        "# names only, never values\n"
        "github-deploy-key held-by: 1Password 2026-10-21\n"
        "~/Documents/wallet-export held-by: organ 2026-10-21T09:30:00Z\n"
        "old-vendor-token held-by: released 2026-10-20\n"
    )
    res = check_credential_route_items(mk_ctx(w, credential_attestation=items))
    s.expect(
        "an owner-written names-only list with a holder and date per item PASSes",
        res.status == PASS and "3 item(s)" in res.detail and "no value was read" in res.detail,
        res.detail,
    )
    for label, text in (
        ("a line without held-by", "github-deploy-key 2026-10-21\n"),
        ("an unknown holder", "github-deploy-key held-by: desk-drawer 2026-10-21\n"),
        ("a non-ISO date", "github-deploy-key held-by: organ yesterday\n"),
        ("no item at all", "# nothing here\n\n"),
        ("one good and one malformed line", "a held-by: organ 2026-10-21\nb held-by:\n"),
    ):
        items.write_text(text)
        res = check_credential_route_items(mk_ctx(w, credential_attestation=items))
        s.expect(f"an attestation with {label} stays UNPROVEN", res.status == UNPROVEN, res.detail)
    s.expect(
        "a missing attestation path stays UNPROVEN",
        check_credential_route_items(mk_ctx(w, credential_attestation=w.root / "nope.txt")).status == UNPROVEN,
    )
    run_with_left_out = w.root / "cred-runs" / "run-20261021T120000Z"
    put(run_with_left_out / "dirty" / "credential-skipped.txt", "untracked-tar\tslug\tpath/.key\t12\n")
    res = check_credential_route_items(mk_ctx(w, preserve_runs=[run_with_left_out]))
    s.expect(
        "credential-pattern files left out of the git snapshots are counted in the detail",
        res.status == UNPROVEN and "1 credential-pattern file(s) were left out" in res.detail,
        res.detail,
    )

    s.expect("no attestation is UNPROVEN", check_backblaze(mk_ctx(w)).status == UNPROVEN)
    att = w.root / "attest.txt"
    att.write_text(f"upload-complete: yes {datetime.now(UTC).isoformat()}\n")  # T1: a bare date no longer covers today
    s.expect(
        "a valid owner attestation dated after the evidence PASSes",
        check_backblaze(mk_ctx(w, backblaze_attestation=att)).status == PASS,
    )
    att.write_text(f"note\nupload-complete: yes {datetime.now(UTC).isoformat()}\n")
    s.expect("an ISO datetime attestation PASSes", check_backblaze(mk_ctx(w, backblaze_attestation=att)).status == PASS)
    att.write_text("upload-complete: yes 2999-01-01\n")  # H6: this used to PASS by outranking every run
    res = check_backblaze(mk_ctx(w, backblaze_attestation=att))
    s.expect(
        "an attestation dated in the future is UNPROVEN, not a PASS",
        res.status == UNPROVEN and "future" in res.detail,
        res.detail,
    )
    att.write_text("upload-complete: yes 2020-01-01\n")
    res = check_backblaze(mk_ctx(w, backblaze_attestation=att))
    s.expect(
        "an attestation older than the newest preserve run is UNPROVEN",
        res.status == UNPROVEN and "predates" in res.detail,
        res.detail,
    )
    att.write_text(f"upload-complete: no {today}\n")
    s.expect(
        "'upload-complete: no' is UNPROVEN", check_backblaze(mk_ctx(w, backblaze_attestation=att)).status == UNPROVEN
    )
    att.write_text("upload-complete: yes tomorrow\n")
    s.expect("a non-ISO date is UNPROVEN", check_backblaze(mk_ctx(w, backblaze_attestation=att)).status == UNPROVEN)
    att.write_text("")
    s.expect(
        "an empty attestation is UNPROVEN", check_backblaze(mk_ctx(w, backblaze_attestation=att)).status == UNPROVEN
    )
    s.expect("human-erase is always UNPROVEN", check_human_erase(mk_ctx(w)).status == UNPROVEN)


def st_group_decide(s: Suite) -> None:
    s.group("verdict and exit code")

    def rs(**over: str) -> list[Result]:
        status = {i: PASS for i, _ in CHECKS} | {"human-erase": UNPROVEN}
        status |= {k.replace("_", "-"): v for k, v in over.items()}
        return [Result(i, st, "") for i, st in status.items()]

    s.expect("all PASS is READY, exit 0", decide(rs(human_erase=PASS)) == ("READY", 0))
    s.expect("only human-erase outstanding is READY, exit 0 (§8: 0 is READY and nothing else)", decide(rs()) == ("READY", 0))
    s.expect("another UNPROVEN check is NOT-READY, exit 2", decide(rs(backblaze_offsite=UNPROVEN)) == ("NOT-READY", 2))
    s.expect("any FAIL is NOT-READY, exit 1", decide(rs(git_preserved=FAIL)) == ("NOT-READY", 1))
    s.expect("FAIL outranks UNPROVEN", decide(rs(git_preserved=FAIL, backblaze_offsite=UNPROVEN)) == ("NOT-READY", 1))
    ids = [i for i, _ in CHECKS]
    s.expect(
        "the credential registry and the credential-route items are two separate checks",
        len(set(ids)) == len(ids) and {"credential-registry-complete", "credential-route-items-homed"} <= set(ids),
        str(ids),
    )
    crashed = run_one("boom", lambda _c: 1 / 0, mk_ctx_stub())
    s.expect(
        "a crashing check reads as FAIL, never as silence",
        crashed.status == FAIL and "ZeroDivisionError" in crashed.detail,
    )


def mk_ctx_stub() -> Ctx:
    p = Path("/nonexistent")
    return Ctx(p, 30.0, p, None, [], [p], None, p, p, p, p)


def cli(argv: list[str], is_mount: Callable[[str], bool]) -> tuple[int, list[str]]:
    """main() with its stdout captured. $HOME is the self-test's empty stand-in home while it runs: the fresh scan always
    walks the strays under $HOME, and a self-test never scans the real one."""
    buf = io.StringIO()
    saved_home = os.environ.get("HOME")
    if SELFTEST_HOME is not None:
        os.environ["HOME"] = str(SELFTEST_HOME)
    try:
        with contextlib.redirect_stdout(buf):
            probes: dict[str, object] = {"device_of": SELFTEST_DEVICES} if SELFTEST_DEVICES else {}
            if SELFTEST_MEDIA:
                probes["media_of"] = SELFTEST_MEDIA
            code = main(argv, is_mount=is_mount, **probes)  # type: ignore[arg-type]
    finally:
        if saved_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved_home
    return code, buf.getvalue().splitlines()


def e2e_argv(w: World, attestation: Path, sweep: Path | None = None) -> list[str]:
    paths = {
        "--sweep": sweep or w.sweep,
        "--preserve-root": w.preserve_root,
        "--remote-held": w.held,
        "--volumes-root": w.root / "vols",
        "--nongit-run": w.root / "nongit",
        "--t7-unique": w.root / "t7copy",
        "--t7-source": w.root / "t7src",
        "--credential-wall": w.root / "wall-ok.py",
        "--credential-attestation": w.root / "e2e-credential-items.txt",
        "--nongit-items": w.root / "nongit-items.tsv",  # H5: nongit-homed compares with the live source
        "--waiver-signers": w.root / "waiver-signers.txt",  # F7: a waiver's signer must be on this list
        "--backblaze-attestation": attestation,
        "--scratch": w.root / "tmp",
    }  # the fresh scan walks the roots in the sweep's .roots file; the strays are under cli()'s empty stand-in $HOME
    return ["--externals", "VolA,VolB"] + [x for flag, path in paths.items() for x in (flag, str(path))]


def st_group_e2e(s: Suite, w: World) -> None:
    s.group("end to end through main()")
    att = w.root / "e2e-attest.txt"
    att.write_text(f"upload-complete: yes {datetime.now(UTC).isoformat()}\n")  # H6: not future-dated; T1: a full time
    (w.root / "e2e-credential-items.txt").write_text("deploy-key held-by: 1Password 2026-10-21\n")
    os.utime(w.sweep, None)
    argv = e2e_argv(w, att)
    code, lines = cli(argv, os.path.isdir)
    verdicts = [ln.split(" ", 2)[:2] for ln in lines[:-1]]
    s.expect("exit 0 when only human-erase is outstanding", code == 0, f"{code}\n" + "\n".join(lines))
    s.expect("one line per check plus the final line", len(lines) == len(CHECKS) + 1, str(len(lines)))
    s.expect(
        "every check is PASS except human-erase",
        verdicts == [[PASS, i] for i, _ in CHECKS[:-1]] + [[UNPROVEN, "human-erase"]],
        str(verdicts),
    )
    s.expect("final line is READY", lines[-1] == "READY", lines[-1])

    row = vanished_row(w)
    waived_sweep = w.root / "e2e-waived-sweep.tsv"
    waived_sweep.write_text(w.sweep.read_text() + "\t".join(row) + "\n")
    shutil.copy(roots_path(w.sweep), roots_path(waived_sweep))
    waivers = w.root / "e2e-waivers.tsv"
    # F7: a waiver now carries the evidence file's sha256 and a kind (waiver_row builds the full line)
    waivers.write_text(WAIVER_HEADER + "\t".join(waiver_row(row[0], w.root / "evidence.md")) + "\n")
    os.utime(waived_sweep, None)
    waived_argv = e2e_argv(w, att, sweep=waived_sweep)
    code, lines = cli(waived_argv, os.path.isdir)
    s.expect(
        "a vanished row without a waiver makes it NOT-READY with exit 1",
        code == 1 and lines[-1] == "NOT-READY" and any(ln.startswith("FAIL git-preserved") for ln in lines),
        f"{code} {lines[-1]}",
    )
    code, lines = cli([*waived_argv, "--waivers", str(waivers)], os.path.isdir)
    s.expect(
        "with its waiver the same sweep is READY (1 waiver), exit 0, with a WAIVED line",
        code == 0
        and lines[-1] == "READY (1 waiver)"
        and any(ln.startswith(f"WAIVED git-preserved {row[0]} owner-sanctioned reap") for ln in lines)
        and any(ln.startswith("PASS git-preserved") for ln in lines),
        f"{code} {lines[-1]}\n" + "\n".join(lines),
    )
    s.expect(
        "F7: the waiver over a row with unpushed commits is listed on its own EXPOSED line, with signer and kind",
        any(
            # §5: the waived row is not named in the proof, so it is remote-not-proven as well as unpushed
            ln.startswith(f"EXPOSED git-preserved {row[0]} waived with data exposure [unpushed=4,remote-not-proven]")
            and "by conductor as remote-held" in ln
            for ln in lines
        ),
        "\n".join(lines),
    )
    att.write_text("")
    code, lines = cli([*waived_argv, "--waivers", str(waivers)], os.path.isdir)
    s.expect(
        "the waiver count is reported on a NOT-READY verdict too",
        code == 2 and lines[-1] == "NOT-READY (1 waiver)",
        f"{code} {lines[-1]}",
    )
    code, lines = cli(argv, os.path.isdir)
    s.expect(
        "an unattested Backblaze makes it NOT-READY with exit 2",
        code == 2 and lines[-1] == "NOT-READY",
        f"{code} {lines[-1]}",
    )
    old = time.time() - 7200
    os.utime(w.sweep, (old, old))
    code, lines = cli(argv, os.path.isdir)
    s.expect(
        "a stale sweep makes it NOT-READY with exit 1",
        code == 1 and lines[-1] == "NOT-READY" and lines[0].startswith("FAIL sweep-fresh"),
        f"{code} {lines[0]}",
    )
    os.utime(w.sweep, None)
    code, lines = cli(argv + ["--externals", "VolA,VolGone"], os.path.isdir)
    s.expect(
        "an unmounted external makes it NOT-READY with exit 1",
        code == 1 and any(ln.startswith("FAIL no-external-dependency") for ln in lines),
        "\n".join(lines),
    )
    code, lines = cli([*argv, "--verbose"], os.path.isdir)
    s.expect(
        "--verbose keeps the same verdict and final line", code == 2 and lines[-1] == "NOT-READY", f"{code} {lines[-1]}"
    )


def st_group_mutations(s: Suite, w: World) -> None:
    s.group("git-preserved: the repositories change after the run")
    old = w.start_ts - 3600
    seen: dict[str, set[str]] = {}

    def run_check(**over: object) -> Result:
        # H4: deep is the default now. This group exercises the --no-deep comparison on purpose: dirtyD's same-size
        # edit below is visible only to the deep one and must not be blamed by the calls that follow it.
        return check_git_preserved(mk_ctx(w, **{"deep": False, **over}))

    def only(res: Result, repo: str, codes: set[str], name: str) -> None:
        got = blame(res)
        seen[w.repos[repo]] = codes
        s.expect(
            f"{name}: FAIL with exactly {sorted(codes)}",
            res.status == FAIL and got.get(w.repos[repo]) == codes,
            str(got),
        )
        s.expect(
            f"{name}: no other repository is blamed",
            {k: v for k, v in got.items() if k != w.repos[repo]}
            == {k: v for k, v in seen.items() if k != w.repos[repo]},
            str(got),
        )

    plain = Path(w.repos["plain"])
    fx(plain, "branch", "extra", "HEAD~1")
    only(run_check(), "plain", {"tip-missing"}, "new branch on an old commit (bundle lacks the current tip)")

    notheld = Path(w.repos["notheld"])
    commit_file(notheld, "later.txt", "later\n", "later")
    only(run_check(), "notheld", {"tip-missing", "stale"}, "new commit after the run (tip missing and stale)")

    dirty_b = Path(w.repos["dirtyB"])
    put(dirty_b / "tracked.txt", "one\nchanged after the run\n")
    os.utime(dirty_b / "tracked.txt", (old, old))
    only(run_check(), "dirtyB", {"patch-mismatch"}, "tracked file changed (patch no longer matches), mtime hidden")

    dirty_c = Path(w.repos["dirtyC"])
    os.utime(dirty_c / "tracked.txt", None)
    only(run_check(), "dirtyC", {"stale"}, "dirty file touched after the run")

    dirty_a = Path(w.repos["dirtyA"])
    put(dirty_a / "added.txt", "added\n")
    os.utime(dirty_a / "added.txt", (old, old))
    only(run_check(), "dirtyA", {"untracked-mismatch"}, "new untracked file (tar member list differs), mtime hidden")

    dirty_d = Path(w.repos["dirtyD"])
    same = (dirty_d / "new.txt").stat()
    put(dirty_d / "new.txt", "UNTRACKED\n")
    os.utime(dirty_d / "new.txt", ns=(same.st_atime_ns, same.st_mtime_ns))
    res = run_check(deep=True)
    got = blame(res)
    s.expect(
        "same-size untracked edit with mtime restored: --deep catches it",
        got.get(w.repos["dirtyD"]) == {"untracked-mismatch"},
        str(got),
    )
    # only the --deep run sees dirtyD's edit, so it is deliberately not in `seen` for the default-mode checks below

    partial = Path(w.repos["partial"])
    fx(partial, "branch", "extra", "HEAD~1")
    only(run_check(), "partial", {"tip-missing"}, "partial clone: new branch the raw git-dir copy lacks")

    unborn = Path(w.repos["unborn"])
    put(unborn / "staged2.txt", "later\n")
    os.utime(unborn / "staged2.txt", (old, old))
    fx(unborn, "add", "staged2.txt")
    only(
        run_check(),
        "unborn",
        {"staged-mismatch", "gitdir-stale"},
        "unborn HEAD: a path staged after the run (staged-tar and index copy differ)",
    )

    wtdet = Path(w.repos["wtdet"])
    commit_file(wtdet, "d2.txt", "d2\n", "another detached commit")
    res = run_check()
    got = blame(res)
    s.expect(
        "new commit on a detached worktree is not covered by its head bundle",
        got.get(w.repos["wtdet"]) == {"head-uncovered", "stale"},
        str(got),
    )

    orphan = Path(w.repos["orphan"])
    put(orphan / "late.txt", "late\n")
    res = run_check()
    s.expect(
        "a file added to an orphan tree breaks its tar match",
        blame(res).get(w.repos["orphan"]) == {"orphan-uncovered"},
        str(blame(res)),
    )

    s.expect("the mutated world as a whole is FAIL", run_check().status == FAIL)
    os.utime(w.sweep, None)
    code, lines = cli(e2e_argv(w, w.root / "e2e-attest.txt"), os.path.isdir)
    s.expect(
        "end to end the mutated world is NOT-READY with exit 1",
        code == 1 and lines[-1] == "NOT-READY" and any(ln.startswith("FAIL git-preserved") for ln in lines),
        f"{code} {lines[-1]}",
    )


def run_self_test(args: argparse.Namespace) -> int:
    global SELFTEST_DEVICES, SELFTEST_MEDIA, SELFTEST_HOME
    suite = Suite(args.verbose)
    # hermetic: fixtures are built and swept with an empty git config (FX_ENV, sweep_row), so the checks read the same
    os.environ.update(GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
    if not Path(args.preserve_script).is_file():
        print(f"self-test cannot run: producer script not found: {args.preserve_script}")
        return 1
    if not Path(args.classify_script).is_file():
        print(f"note: no classifier at {args.classify_script}; real.tsv is built from the ported rules (weaker parity)")
    parent = Path(args.scratch) if args.scratch else None
    # every fixture path is a realpath (§1): the prove lane's keys are, and the predicate compares realpaths
    root = Path(os.path.realpath(tempfile.mkdtemp(prefix="exit-ready-selftest-", dir=parent)))
    # git reads a host-wide ignore and attributes file from $XDG_CONFIG_HOME/git whatever GIT_CONFIG_GLOBAL says; a fixture
    # must not inherit the machine owner's (their `pkg` or `*.log` would change what the ignored-payload check sees)
    saved_xdg = os.environ.get("XDG_CONFIG_HOME")
    os.environ["XDG_CONFIG_HOME"] = str(root / "xdg-config")
    started = time.time()
    try:
        world = build_world(root, args)
        SELFTEST_DEVICES = fixture_devices(world)
        SELFTEST_MEDIA = fixture_media(world)
        (root / "fakehome").mkdir(exist_ok=True)
        SELFTEST_HOME = root / "fakehome"
        print(
            f"fixtures: {len(world.repos)} checkouts, producer run {world.run.name} ({time.time() - started:.0f}s)",
            flush=True,
        )
        st_group_ready_a_artifacts(suite, world, args)
        st_group_ready_a_exposure(suite, world, args)
        st_group_classification(suite, world)
        st_group_git_preserved(suite, world)
        st_group_union(suite, world)
        st_group_vanished(suite, world)
        st_group_waivers(suite, world)
        st_group_sweep(suite, world)
        st_group_externals(suite, world)
        st_group_t7(suite, world)
        st_group_nongit(suite, world)
        st_group_credentials_backblaze(suite, world)
        st_group_decide(suite)
        # the end-to-end groups need the fixtures the groups above leave behind, and a pristine world
        make_vols(world)
        st_group_t7_restore(world)
        st_group_e2e(suite, world)
        st_group_mutations(suite, world)
        # F4/F7/F8/H1/H2/H5/H6 groups: a world of their own, because the groups above leave the shared one mutated
        (world.root / "fresh").mkdir()
        fresh = build_world(world.root / "fresh", args)
        st_group_r2_binding(suite, fresh, args)
        st_group_r2_discovery(suite, fresh, args)
        st_group_r2_gitdir(suite, fresh, args)
        st_group_r2_payload(suite, fresh, args)
        st_group_usage_codes(suite)
        st_group_manual_copies(suite, fresh)
        st_group_recovery_copies(suite, fresh)
        st_group_custody(suite, fresh)
        st_group_external_scan(suite, fresh)
        st_group_nongit_live(suite, fresh)
        st_group_time_bounds(suite, fresh)
        st_group_object_primitives(suite, fresh)
        st_group_media(suite, fresh)
        st_group_custody_media(suite, fresh)
        st_group_custody_image(suite, fresh)
        st_group_custody_units(suite, fresh)
        st_group_custody_copies(suite, fresh)
        st_group_custody_external(suite, fresh)
        st_group_custody_waivers(suite, fresh)
        st_group_custody_nongit(suite, fresh)
        st_group_custody_time(suite, fresh)
        st_group_custody_e2e(suite, fresh, args)
    except Exception as exc:  # noqa: BLE001  a crashing fixture is a failed self-test, reported with its traceback
        traceback.print_exc()
        suite.failed.append(f"self-test crashed: {type(exc).__name__}: {exc}")
    finally:
        if saved_xdg is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = saved_xdg
        if args.keep_fixtures:
            print(f"fixtures kept at {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)
    print(f"self-test: {suite.total} assertions, {len(suite.failed)} failed ({time.time() - started:.0f}s)")
    for name in suite.failed:
        print(f"  failed: {name}")
    return 0 if not suite.failed else 1


def st_group_t7_restore(w: World) -> None:
    """Leave pristine t7 and non-git fixtures behind for the end-to-end group."""
    src, copy, run = w.root / "t7src", w.root / "t7copy", w.root / "nongit" / "run-20261021T120000Z-4242"
    for base in (src, copy):
        put(base / "a" / "b.bin", bytes(range(200)))
        put(base / "c.txt", "hello\n")
    (copy / "MANIFEST.sha256").write_text(
        shasum_line(copy / "a/b.bin", "a/b.bin") + shasum_line(copy / "c.txt", "c.txt")
    )
    put(run / "data" / "x.txt", "x\n")
    put(run / "data" / "y.bin", bytes(range(50)))
    (run / "MANIFEST.sha256").unlink(missing_ok=True)
    (run / "MANIFEST.sha256").write_text(
        shasum_line(run / "data/x.txt", "data/x.txt") + shasum_line(run / "data/y.bin", "data/y.bin")
    )
    (run / "RESULT.txt").write_text("PASS\n")
    (run / "MANIFEST.tsv").unlink(missing_ok=True)
    src = w.root / "nongit-src"  # H5: the live source the non-git run is compared with, and the items file naming it
    put_source(src / "data" / "x.txt", "x\n", run)
    put_source(src / "data" / "y.bin", bytes(range(50)), run)
    (w.root / "nongit-items.tsv").write_text(f"data\t{src / 'data'}\tdata\n")
    (w.root / "waiver-signers.txt").write_text("conductor\n")


# ----------------------------------------------------------------------------------------------------
# self-test groups for the waiver / external-dependency / copy-validation findings (F4 F7 F8 H1 H2 H5 H6).
# Each safety check gets a case that must FAIL and a negative control that must PASS, so none can rot into a no-op.
# They run last, on a world of their own, because the groups above leave the shared world mutated.
# ----------------------------------------------------------------------------------------------------
USAGE_REQUIRED = (
    "--preserve-root",
    "--remote-held",
    "--nongit-run",
    "--t7-unique",
    "--t7-source",
    "--credential-wall",
    "--credential-attestation",
    "--backblaze-attestation",
)


def usage_exit(argv: list[str], omit: str = "") -> object:
    """main()'s SystemExit code for a command line that argparse refuses (None when it did not exit).

    Every path flag points at a directory that does not exist, so a flag that WRONGLY parses runs inert checks
    (never the real Mac or its volumes) and merely reads as None here."""
    nowhere = str(Path(tempfile.gettempdir()) / "exit-ready-inert-nowhere")
    inert = ["--externals", "auto"]
    for flag in ("--sweep", "--volumes-root", *USAGE_REQUIRED):
        if flag != omit:
            inert += [flag, nowhere]
    sink = io.StringIO()
    try:
        with contextlib.redirect_stderr(sink), contextlib.redirect_stdout(sink):
            main([*inert, *argv])
    except SystemExit as exc:
        return exc.code
    return None


def later_stamp() -> str:
    """An ISO timestamp two seconds from now: not before any file made so far, well inside the future-dating skew."""
    return (datetime.now(UTC) + timedelta(seconds=2)).strftime("%Y-%m-%dT%H:%M:%S+00:00")


@contextlib.contextmanager
def dated(ts: float) -> Iterator[None]:
    """Commits made inside carry this date (before the run under test began), so staleness is not what a case tests."""
    stamp = f"{int(ts)} +0000"
    saved = {k: os.environ.get(k) for k in ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")}
    os.environ.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def codes_of(res: Result, repo: str) -> set[str]:
    return blame(res).get(repo, set())


def st_group_r2_binding(s: Suite, w: World, args: argparse.Namespace) -> None:
    s.group("round 2 (§2 §3 §4 §5): PROVEN-ALL is bound tip by tip, absent is unproven, a path is no remote")
    sb = spare_world(w, "r2-bind", args)
    work, past = sb.root / "work", sb.start_ts - 3600
    extra_rows: list[dict[str, str]] = []
    extra_tips: dict[str, str] = {}

    def run(**over: object) -> Result:
        return check_git_preserved(mk_ctx(sb, **over))

    def settle(**kw: Any) -> None:
        """What the operator's pipeline does after a change: an honest sweep, and a proof made from what git holds now."""
        write_sweep(sb.sweep, swept_checkouts(sb))
        write_held(sb.held, world_held_entries(sb.repos, extra=tuple(extra_rows)))
        refresh_tips(sb, extra_tips, **kw)
        os.utime(sb.held, None)

    res = run()
    s.expect("r2: the spare world PASSes before any change (positive control)", res.status == PASS, res.detail)

    # A14 (carried-forward rows): a PROVEN-ALL checkout that is gone has no refs left to bind; moved out of every scanned
    # root with commits made since, it would otherwise ride on its old record
    gone = Path(sb.repos["nestedD"])
    with dated(past):
        commit_file(gone, "after.txt", "new local work after the sweep\n", "new local work")
    moved = sb.root / "r2-moved" / "nestedD"
    moved.parent.mkdir()
    shutil.move(str(gone), str(moved))
    res = run()
    s.expect(
        "A14: a PROVEN-ALL row whose checkout vanished (moved out of every scanned root) is row-vanished, not safe",
        res.status == FAIL and "row-vanished" in codes_of(res, str(gone)) and "is gone" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    shutil.move(str(moved), str(gone))
    settle()
    s.expect("A14: moved back and re-proven, the row PASSes again (positive control)", run().status == PASS)

    # F1 / H-REFLOG-ONLY after the proof: work made once the proof was taken, on a branch deleted since, lives only in a
    # reflog (and a deinit'd submodule's commits only under modules/); the ref keys cannot see either
    ghost = Path(sb.repos["nestedC"])
    with dated(past):
        fx(ghost, "checkout", "-q", "-b", "throwaway")
        commit_file(ghost, "scratch.txt", "work that exists only in a reflog\n", "throwaway work")
        fx(ghost, "checkout", "-q", "main")
        fx(ghost, "branch", "-D", "throwaway")
    write_sweep(sb.sweep, swept_checkouts(sb))
    res = run()
    s.expect(
        "F1: a PROVEN-ALL row whose repository holds a commit only a reflog reaches is not bound, and needs coverage",
        res.status == FAIL
        and "reflog-only commits that no ref proof covers" in res.detail
        and "manifest-missing" in codes_of(res, str(ghost)),
        f"{blame(res)} {res.detail}",
    )
    ghost_common = os.path.realpath(f"{ghost}/.git")
    ghost_slug = slugify(ghost_common, sb.home)
    dest, run_dir = clone_run(sb, "reflog-post-proof")
    artifact = run_dir / "bundles" / f"{ghost_slug}.bundle"
    fx(ghost, "bundle", "create", "-q", str(artifact), "--all")
    add_manifest_item(run_dir, "bundle", ghost_slug, ghost_common, artifact, 1, "verify=ok")
    res = run(preserve_root=dest)
    s.expect("F1: with its bundle but no raw git-dir copy the row still FAILs", res.status == FAIL and "raw git dir copy is required" in str(res.problems), f"{blame(res)} {res.problems}")
    make_gitdir_tar(run_dir, ghost_common, sb.home, "reflog-only commits")
    res = run(preserve_root=dest)
    s.expect("F1: with its bundle and the raw git-dir copy that holds the reflog-only commit the row PASSes", res.status == PASS, f"{blame(res)} {res.problems}")
    fx(ghost, "reflog", "expire", "--expire=now", "--all")
    settle()
    s.expect("F1: with the reflog gone the row is bound again (positive control)", run().status == PASS)
    put(ghost / ".git" / "modules" / "lib" / "HEAD", "ref: refs/heads/main\n")  # c7b: a submodule git dir left by deinit
    res = run()
    s.expect(
        "F1: a PROVEN-ALL row whose repository holds submodule git dirs is not bound either",
        res.status == FAIL and "submodule git dirs that no ref proof covers" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    shutil.rmtree(ghost / ".git" / "modules")
    s.expect("F1: with modules/ gone the row is bound again (positive control)", run().status == PASS)

    # FP-DETACHED-REPO: the main checkout of a PROVEN-ALL repository detaches its HEAD and commits locally
    safe = Path(sb.repos["safe"])
    with dated(past):
        fx(safe, "checkout", "-q", "--detach")
        commit_file(safe, "detached-1.txt", "only on this Mac\n", "detached work 1")
        commit_file(safe, "detached-2.txt", "more\n", "detached work 2")
    write_sweep(sb.sweep, swept_checkouts(sb))  # an honest re-sweep; the proof was made before the commits
    res = run()
    s.expect(
        "FP-DETACHED-REPO: a kind=repo checkout on a detached HEAD with local-only commits is head-uncovered, not safe",
        res.status == FAIL and "head-uncovered" in codes_of(res, str(safe)) and "not trusted" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    settle()  # a proof made now carries the key HEAD@<safe> for that detached HEAD
    res = run()
    s.expect(
        "FP-DETACHED-REPO: the proof re-made with the detached HEAD's tip binds it (positive control)",
        res.status == PASS,
        res.detail,
    )
    fx(safe, "checkout", "-q", "main")
    fx(safe, "reflog", "expire", "--expire=now", "--all")  # the detached commits are reflog-only now (F1): forget them
    settle()

    # FP-SAFE-ROW-REFS: commits only a custom ref, an annotated tag and a note reach, on a row whose sweep columns are clean
    nested_a = Path(sb.repos["nestedA"])
    with dated(past):
        tree = fx(nested_a, "rev-parse", "HEAD^{tree}").strip()
        only_ref = fx(nested_a, "commit-tree", tree, "-p", "HEAD", "-m", "artifact reachable only from refs/limen").strip()
        fx(nested_a, "update-ref", "refs/limen/artifact-x", only_ref)
        only_tag = fx(nested_a, "commit-tree", tree, "-p", "HEAD", "-m", "release reachable only from a tag").strip()
        fx(nested_a, "tag", "-a", "-m", "annotated local tag", "v-local", only_tag)
        fx(nested_a, "notes", "add", "-m", "a note that exists only here", "HEAD")
    write_sweep(sb.sweep, swept_checkouts(sb))
    res = run()
    s.expect(
        "FP-SAFE-ROW-REFS: the sweep columns are blind to them (unpushed=0) ...",
        sweep_row(str(nested_a))[5] == "0",
        str(sweep_row(str(nested_a))),
    )
    s.expect(
        "FP-SAFE-ROW-REFS: ... yet a clean PROVEN-ALL row whose tag, custom ref and note are not in the proof needs coverage",
        res.status == FAIL
        and "manifest-missing" in codes_of(res, str(nested_a))
        and "refs/limen/artifact-x is not in the proof" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    settle()
    s.expect("FP-SAFE-ROW-REFS: the proof re-made with those refs binds them (positive control)", run().status == PASS)
    for ref in ("refs/limen/artifact-x", "refs/notes/commits"):
        fx(nested_a, "update-ref", "-d", ref)
    fx(nested_a, "tag", "-d", "v-local")
    settle()

    # FP-REMOTE-TRUST: a forged remote-tracking ref makes a local-only commit look pushed, and the row is not in the file
    nested_b = Path(sb.repos["nestedB"])
    with dated(past):
        fx(nested_b, "checkout", "-q", "-b", "feature")
        commit_file(nested_b, "feature.txt", "never pushed; the tracking ref is stale or forged\n", "feature")
    fx(nested_b, "update-ref", "refs/remotes/origin/feature", "HEAD")
    write_sweep(sb.sweep, swept_checkouts(sb))
    write_held(sb.held, world_held_entries(sb.repos, omit=("nestedB",)))
    refresh_tips(sb)
    res = run()
    s.expect(
        "FP-REMOTE-TRUST: the sweep calls the forged-tracking-ref row clean (unpushed=0) ...",
        sweep_row(str(nested_b))[5] == "0",
        str(sweep_row(str(nested_b))),
    )
    s.expect(
        "FP-REMOTE-TRUST: ... and a row the remote-held file does not name is unproven: it needs a bundle the run lacks",
        res.status == FAIL and "manifest-missing" in codes_of(res, str(nested_b)),
        str(blame(res)),
    )
    fx(nested_b, "checkout", "-q", "main")
    fx(nested_b, "branch", "-D", "feature")
    fx(nested_b, "update-ref", "-d", "refs/remotes/origin/feature")
    fx(nested_b, "reflog", "expire", "--expire=now", "--all")
    settle()
    s.expect("FP-REMOTE-TRUST: named PROVEN-ALL and bound again, the row PASSes (positive control)", run().status == PASS)

    # FP-REMOTE-TRUST: an origin that is a directory (or file:// URL, or an insteadOf rewrite to one) is not a remote
    nested_c = Path(sb.repos["nestedC"])
    store, https = origin_store(nested_c), f"https://git.example.invalid/{origin_store(nested_c).name}"
    for label, apply, undo in (
        ("a directory on this Mac", ("remote", "set-url", "origin", str(store)), ("remote", "set-url", "origin", https)),
        ("a file:// URL", ("remote", "set-url", "origin", f"file://{store}"), ("remote", "set-url", "origin", https)),
        (
            "an insteadOf rewrite of the https URL to a directory",
            ("config", f"url.{store.parent}/.insteadOf", "https://git.example.invalid/"),
            ("config", "--unset", f"url.{store.parent}/.insteadOf"),
        ),
    ):
        fx(nested_c, *apply)
        res = run()
        s.expect(
            f"FP-REMOTE-TRUST: a PROVEN-ALL repository whose only remote is {label} is not trusted",
            res.status == FAIL
            and "manifest-missing" in codes_of(res, str(nested_c))
            and "anywhere but this Mac" in res.detail,
            f"{blame(res)} {res.detail}",
        )
        fx(nested_c, *undo)
    s.expect("FP-REMOTE-TRUST: with the https origin back the row PASSes (positive control)", run().status == PASS)
    local = (
        "/srv/x.git",
        "./x.git",
        "~/x.git",
        "file:///srv/x.git",
        "ssh://localhost/x.git",
        "https://127.0.0.1/x.git",
        "https://127.1/x.git",
        "ssh://git@0x7f.0.0.1/x.git",
        "https://[::1]/x.git",
        "https://[::ffff:127.0.0.1]/x.git",
        "git@localhost:o/x.git",
        "",
    )
    offsite = ("https://github.com/o/x.git", "git@github.com:o/x.git", "ssh://git@example.invalid:2222/x.git", "https://10.1.2.3/x.git")
    s.expect(
        "§5: every spelling of this machine is a local URL, every other host is not",
        all(is_local_url(u) for u in local) and not any(is_local_url(u) for u in offsite),
        str([u for u in local if not is_local_url(u)] + [u for u in offsite if is_local_url(u)]),
    )
    s.expect(
        "§5: --remote-held is a required argument (exit 64 without it)",
        "--remote-held" in USAGE_REQUIRED and usage_exit([], omit="--remote-held") == EXIT_USAGE,
        str(usage_exit([], omit="--remote-held")),
    )

    # P6 (§3): a remote-held.tsv or tips.tsv without its closing row was cut short; none of it is believed
    for name, path in (("remote-held.tsv", sb.held), ("tips.tsv", sb.root / "tips.tsv")):
        text = path.read_text()
        rows = text.splitlines()
        variants = {
            "no completion row (cut short by a crash)": "\n".join(rows[:-1]) + "\n",
            "a completion row that miscounts": text.replace(f"#END rows={len(rows) - 2}", f"#END rows={len(rows) - 1}", 1),
            "two completion rows": text + rows[-1] + "\n",
            "a data row after the completion row": text + rows[1] + "\n",
        }
        for label, body in variants.items():
            path.write_text(body)
            res = run()
            s.expect(
                f"P6: a {name} with {label} is input-unusable",
                res.status == FAIL and "input-unusable" in str(res.problems) and "#END" in str(res.problems),
                f"{blame(res)} {res.detail}",
            )
        path.write_text(text)
    s.expect("P6: with both files whole again the world PASSes (positive control)", run().status == PASS)

    # INT-3 (§1): a key is compared exactly. The old prover collapsed runs of spaces in `paths`
    with dated(past):
        spaced = make_repo(work, "tag  repo")
    sb.repos["spaced"] = str(spaced)
    exact = held_entry(str(spaced), "PROVEN-ALL")
    collapsed = {**exact, "repo": " ".join(exact["repo"].split()), "paths": " ".join(exact["paths"].split())}
    extra_rows[:] = [collapsed]
    extra_tips[collapsed["repo"]] = str(spaced)
    settle()
    res = run()
    s.expect(
        "INT-3: a proof that names the checkout under a spelling that differs (two spaces collapsed) proves nothing for it",
        res.status == FAIL and "manifest-missing" in codes_of(res, str(spaced)),
        f"{blame(res)} {res.detail}",
    )
    extra_rows[:] = [exact]
    extra_tips.clear()
    extra_tips[exact["repo"]] = str(spaced)
    settle()
    s.expect("INT-3: under its exact realpath key the same checkout PASSes (positive control)", run().status == PASS)

    # INT-5 / PS-6 / H-PROVER-TIPS-NAMES (§2): the old prover's short branch names bind nothing
    settle(rewrite=lambda r: [r[0], r[1].removeprefix("refs/heads/"), *r[2:]])
    res = run()
    s.expect(
        "INT-5: a tips.tsv that names branches by their SHORT name (main, topic) does not bind a PROVEN-ALL verdict",
        res.status == FAIL and "is not in the proof" in res.detail and "refs/heads/main" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    settle()
    s.expect("INT-5: full refnames bind it (positive control)", run().status == PASS)

    # §4: any documented gap, and a proof made for another common dir, make the verdict untrusted
    nested_d = sb.repos["nestedD"]
    gapped = held_entry(nested_d, "PROVEN-ALL", gaps="NONGITHUB-HISTORY-ASSUMED;BARE-NO-REFLOG")
    write_held(sb.held, world_held_entries(sb.repos, omit=("nestedD",), extra=(gapped, *extra_rows)))
    res = run()
    s.expect(
        "§4: a non-empty `gaps` makes the PROVEN-ALL row untrusted, naming the codes",
        res.status == FAIL
        and "manifest-missing" in codes_of(res, nested_d)
        and "NONGITHUB-HISTORY-ASSUMED" in res.detail
        and "BARE-NO-REFLOG" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    foreign = {**held_entry(nested_d, "PROVEN-ALL"), "common_dir": os.path.realpath(sb.repos["nestedC"]) + "/.git"}
    write_held(sb.held, world_held_entries(sb.repos, omit=("nestedD",), extra=(foreign, *extra_rows)))
    res = run()
    s.expect(
        "§1: a proof whose common_dir is not the one git reports for the checkout is untrusted",
        res.status == FAIL and "was made for" in res.detail and "manifest-missing" in codes_of(res, nested_d),
        f"{blame(res)} {res.detail}",
    )
    settle()

    # §2 / P3: per-worktree refs and detached HEADs are keyed by worktree and listed for EVERY worktree
    with dated(past):
        proj = make_repo(work, "proj")
    linked = work / "proj-wt"
    fx(proj, "worktree", "add", "-q", "-b", "side", str(linked))
    with dated(past):
        commit_file(linked, "side.txt", "side\n", "side work")
        kept = fx(linked, "commit-tree", fx(linked, "rev-parse", "HEAD^{tree}").strip(), "-m", "kept by a per-worktree ref").strip()
        fx(linked, "update-ref", "refs/worktree/keep", kept)
        fx(linked, "update-ref", "refs/bisect/bad", kept)
    sb.repos["proj"], sb.repos["proj-wt"] = str(proj), str(linked)
    entry = held_entry(str(proj), "PROVEN-ALL", [str(proj), str(linked)])
    extra_rows.append(entry)
    extra_tips[entry["repo"]] = str(proj)
    settle()
    where = os.path.realpath(linked)
    tips_text = (sb.root / "tips.tsv").read_text()
    s.expect(
        "fixture sanity: the proof written from raw git carries a key per per-worktree ref and a branch row for each worktree",
        f"refs/worktree/keep@{where}" in tips_text and f"refs/bisect/bad@{where}" in tips_text and "refs/heads/side" in tips_text,
    )
    res = run()
    s.expect(
        "§2: a repository with a linked worktree is bound across both worktrees (positive control)",
        res.status == PASS,
        res.detail,
    )
    settle(drop=lambda r: r[2] == "per-worktree")
    res = run()
    s.expect(
        "P3: refs/worktree and refs/bisect of a LINKED worktree absent from the proof void it",
        res.status == FAIL and f"@{where} is not in the proof" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    settle(rewrite=lambda r: [r[0], r[1].replace(f"@{where}", f"@{os.path.realpath(proj)}"), *r[2:]])
    res = run()
    s.expect(
        "P3: the same refs filed under another worktree's key void it too",
        res.status == FAIL and f"@{where} is not in the proof" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    settle()
    fx(linked, "checkout", "-q", "--detach")
    write_sweep(sb.sweep, swept_checkouts(sb))  # the linked worktree detached after the proof was made
    res = run()
    s.expect(
        "§2: a linked worktree that detached its HEAD after the proof needs the HEAD@<worktree> row",
        res.status == FAIL and f"HEAD@{where} is not in the proof" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    settle()
    s.expect("§2: with that row proven the repository PASSes again", run().status == PASS)

    # a separate-git-dir (or submodule) checkout: git lists its main worktree under the git dir, the prove lane keys the
    # checkout's own realpath. Both spellings bind; a detached HEAD there is the everyday state of a submodule
    with dated(past):
        sepb = work / "sepb"
        fx(None, "init", "-q", "--template=", "-b", "main", "--separate-git-dir", str(work / "sepb.gitdir"), str(sepb))
        commit_file(sepb, "x.txt", "x\n", "x")
        fx(sepb, "remote", "add", "origin", "https://git.example.invalid/sepb.git")
        fx(sepb, "update-ref", "refs/remotes/origin/main", "HEAD")
        fx(sepb, "checkout", "-q", "--detach")
    sb.repos["sepb"] = str(sepb)
    entry = held_entry(str(sepb), "PROVEN-ALL")
    extra_rows.append(entry)
    extra_tips[entry["repo"]] = str(sepb)
    gitdir_path, checkout_path = os.path.realpath(work / "sepb.gitdir"), os.path.realpath(sepb)
    settle()  # the fixture writer reads `git worktree list`, which names the git dir
    s.expect("§2: a separate-git-dir checkout's detached HEAD binds under git's own spelling of its worktree", run().status == PASS, run().detail)
    settle(rewrite=lambda r: [r[0], r[1].replace(f"@{gitdir_path}", f"@{checkout_path}"), *r[2:]])
    s.expect("§2: and under the checkout's own realpath, the prove lane's spelling", run().status == PASS, run().detail)
    settle(rewrite=lambda r: [r[0], r[1].replace(f"@{gitdir_path}", f"@{work}/nowhere"), *r[2:]])
    res = run()
    s.expect(
        "§2: under any other spelling the detached HEAD is not in the proof",
        res.status == FAIL and f"HEAD@{gitdir_path}" in res.detail and "is not in the proof" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    settle()

    # FP-WORKTREE-OF-UNSWEPT-COMMON: a swept worktree of a bare repository that is itself not swept
    bare, topic = work / "proj2.git", work / "proj2-topic"
    fx(None, "clone", "-q", "--bare", str(origin_store(proj)), str(bare))
    fx(bare, "symbolic-ref", "HEAD", "refs/heads/main")  # the store's default branch is not main
    with dated(past):
        fx(bare, "worktree", "add", "-q", "-b", "topic", str(topic), "main")
        commit_file(topic, "topic.txt", "only in the bare repository's objects\n", "unpushed topic work")
        put(topic / "topic.txt", "stashed\n")
        fx(topic, "stash", "push", "-q", "-m", "only copy of this stash")
    sb.repos["proj2-topic"] = str(topic)
    settle()
    fresh_res, res = check_sweep_fresh(mk_ctx(sb)), run()
    s.expect(
        "FP-WORKTREE-OF-UNSWEPT-COMMON: the fresh scan finds the bare repository the sweep lacks (sweep-fresh FAILs)",
        fresh_res.status == FAIL and "universe-miss" in fresh_res.detail and "proj2.git" in fresh_res.detail,
        fresh_res.detail,
    )
    s.expect(
        "FP-WORKTREE-OF-UNSWEPT-COMMON: git-preserved FAILs on it, and the swept worktree (unpushed commit, stash) needs coverage",
        res.status == FAIL
        and codes_of(res, os.path.realpath(bare)) == {"universe-miss"}
        and "manifest-missing" in codes_of(res, str(topic)),
        str(blame(res)),
    )
    sb.repos["proj2.git"] = str(bare)  # the sweep lists the bare repository as kind=bare (§12)
    settle()
    s.expect("§12: the sweep helper derives kind=bare from git", sweep_row(str(bare))[1] == "bare", str(sweep_row(str(bare))))
    res = run()
    s.expect(
        "§12: a kind=bare row is accepted (no universe-miss, no exposure-drift) and, with no bundle, needs coverage",
        res.status == FAIL
        and "manifest-missing" in codes_of(res, str(bare)) | codes_of(res, str(topic))  # one bundle serves both rows
        and "universe-miss" not in {c for cs in blame(res).values() for c in cs}
        and "exposure-drift" not in {c for cs in blame(res).values() for c in cs},
        str(blame(res)),
    )
    slug = slugify(os.path.realpath(bare), sb.home)
    artifact = sb.run / "bundles" / f"{slug}.bundle"
    fx(bare, "bundle", "create", "-q", str(artifact), "--all")
    add_manifest_item(sb.run, "bundle", slug, os.path.realpath(bare), artifact, 3, "verify=ok")
    res = run()
    s.expect(
        "§12: a full bundle of the bare directory (common dir = the bare directory) covers the bare row and its worktree",
        res.status == PASS,
        f"{blame(res)} {res.detail}",
    )
    # F2: a bare repository has no work tree; the scans that need one (ignored files, filtered content, hidden edits)
    # are not run on its row, so its row is covered by its bundle alone and the world can be READY
    res = check_ignored_payload(mk_ctx(sb))
    s.expect("F2: the ignored-payload check PASSes with a bare row in the sweep", res.status == PASS, res.detail)
    os.utime(sb.sweep, None)
    os.utime(sb.held, None)
    code, lines = cli(e2e_argv(sb, prepare_e2e(sb)), os.path.isdir)
    s.expect(
        "F2: a world holding a bare row with a local-only commit, covered by its bundle, is READY (exit 0)",
        code == 0 and lines[-1] == "READY",
        f"{code} {lines}",
    )


def mk_lone_repo(path: Path) -> Path:
    """A repository with one commit and no remote, the shape of work that exists only on this Mac."""
    fx(None, "init", "-q", "--template=", "-b", "main", str(path))
    commit_file(path, "only.txt", "the only copy\n", "only copy")
    return path


def st_group_r2_discovery(s: Suite, w: World, args: argparse.Namespace) -> None:
    s.group("round 2 (§12 §8): the fresh scan is never narrower than the sweep, --discovery-root adds, exit codes")
    sd = spare_world(w, "r2-disc", args)
    attestation = prepare_e2e(sd)
    work, argv = sd.root / "work", e2e_argv(sd, attestation)
    elsewhere = sd.root / "r2-elsewhere"
    elsewhere.mkdir()

    def sweep_fresh(**over: object) -> Result:
        return check_sweep_fresh(mk_ctx(sd, **over))

    res = sweep_fresh()
    s.expect("r2: the spare world's fresh scan finds nothing the sweep lacks (positive control)", res.status == PASS, res.detail)
    s.expect(
        "PS-13: no personal directory name is built in; the roots come from the sweep's roots file",
        not {"SWEEP_ROOTS", "SWEEP_PRUNE", "default_discovery_roots"} & set(globals()),
        str({"SWEEP_ROOTS", "SWEEP_PRUNE", "default_discovery_roots"} & set(globals())),
    )
    code, lines = cli(argv, os.path.isdir)
    s.expect("§8: READY exits 0, and 0 means READY", code == 0 and lines[-1] == "READY", f"{code} {lines[-1]}")
    code, lines = cli([*argv, "--discovery-root", str(elsewhere)], os.path.isdir)
    s.expect("PS-8: an added root that holds nothing changes nothing (positive control)", code == 0, f"{code} {lines[-1]}")

    # FP-DISCOVERY-BLIND / FP-DISCOVERY-ROOT-DRIFT: everything the sweep's bounds and prunes could not see
    def case_git_upper() -> Path:
        repo = mk_lone_repo(work / "shouty")
        (repo / ".git").rename(repo / ".GIT")  # git on a case-insensitive volume reads it; `find -name .git` does not
        return repo

    blind = {
        "at depth 10 below its root (the sweep stops at 9)": lambda: mk_lone_repo(work / "a1/a2/a3/a4/a5/a6/a7/a8/deep"),
        "inside a node_modules": lambda: mk_lone_repo(work / "app/node_modules/my-fork"),
        "inside a .venv": lambda: mk_lone_repo(work / "tool/.venv/src/editable-dep"),
        "inside a site-packages": lambda: mk_lone_repo(work / "lib/site-packages/vendored"),
        "whose git directory is spelled .GIT": case_git_upper,
    }
    for label, build in blind.items():
        repo = build()
        res, gp = sweep_fresh(), check_git_preserved(mk_ctx(sd))
        s.expect(
            f"FP-DISCOVERY-BLIND: a repository {label} is a universe-miss in sweep-fresh and in git-preserved",
            res.status == FAIL
            and "universe-miss" in res.detail
            and gp.status == FAIL
            and codes_of(gp, str(repo)) == {"universe-miss"},
            f"{res.detail} {blame(gp)}",
        )
        shutil.rmtree(work / repo.relative_to(work).parts[0])
    lost = work / "lost.git"
    fx(None, "init", "-q", "--bare", "--template=", str(lost))
    res, gp = sweep_fresh(), check_git_preserved(mk_ctx(sd))
    s.expect(
        "FP-DISCOVERY-BLIND: a bare repository (a directory holding HEAD, objects/ and refs/) is a universe-miss",
        res.status == FAIL and "universe-miss" in res.detail and codes_of(gp, str(lost)) == {"universe-miss"},
        f"{res.detail} {blame(gp)}",
    )
    shutil.rmtree(lost)
    s.expect("FP-DISCOVERY-BLIND: with those gone the scan PASSes again (positive control)", sweep_fresh().status == PASS)

    # the sweep's bare rule: git calls it bare AND it is its own git dir; nothing nested inside a bare directory counts
    sep, outer = work / "sep", work / "outer.git"
    fx(None, "init", "-q", "--template=", "-b", "main", "--separate-git-dir", str(work / "sep.gitdir"), str(sep))
    commit_file(sep, "s.txt", "s\n", "s")
    fx(None, "init", "-q", "--bare", "--template=", str(outer))
    fx(None, "init", "-q", "--bare", "--template=", str(outer / "inner"))
    sd.repos["sep"], sd.repos["outer.git"] = str(sep), str(outer)
    write_sweep(sd.sweep, swept_checkouts(sd))
    res = sweep_fresh()
    s.expect(
        "§12: a separate-git-dir gitdir is not a bare repository, and a bare directory nested in a bare one is not a row of its own",
        res.status == PASS,
        res.detail,
    )
    del sd.repos["sep"], sd.repos["outer.git"]
    shutil.rmtree(sep)
    shutil.rmtree(work / "sep.gitdir")
    shutil.rmtree(outer)
    write_sweep(sd.sweep, swept_checkouts(sd))

    # PS-8 / H-DISCOVERY-ROOT-NARROWS: --discovery-root ADDS; it never replaces the sweep's roots or the $HOME strays
    mk_lone_repo(work / "late")
    code, lines = cli([*argv, "--discovery-root", str(elsewhere)], os.path.isdir)
    s.expect(
        "PS-8: with an unrelated --discovery-root a repository the sweep lacks under its own root is still a universe-miss",
        code == 1 and any(ln.startswith("FAIL sweep-fresh") and "universe-miss" in ln for ln in lines),
        f"{code} {lines}",
    )
    shutil.rmtree(work / "late")
    assert SELFTEST_HOME is not None
    stray = mk_lone_repo(SELFTEST_HOME / "stray")
    code, lines = cli([*argv, "--discovery-root", str(work)], os.path.isdir)
    s.expect(
        "PS-8: with --discovery-root given, the repository the sweep lacks directly under $HOME is still a universe-miss",
        code == 1 and any(ln.startswith("FAIL sweep-fresh") and "universe-miss" in ln for ln in lines),
        f"{code} {lines}",
    )
    shutil.rmtree(stray)

    # INT-4 / PS-2 / FP-DISCOVERY-ROOT-DRIFT: ~/.local/share is a root of the sweep, so it is one of the scan's
    home = sd.root / "r2-home"
    share = home / ".local" / "share"
    mk_lone_repo(share / "app" / "tool")  # past the strays' depth: only the sweep's roots file reaches it
    sweepdir = sd.root / "r2-sweep"
    sweepdir.mkdir()
    sweep = sweepdir / "git.tsv"
    copy_sweep(sd.sweep, sweep)
    write_roots(sweep, [str(work), str(share)])
    res = check_sweep_fresh(mk_ctx(sd, sweep=sweep, home=str(home)))
    s.expect(
        "INT-4: a repository under ~/.local/share created after the sweep is a universe-miss (its roots file lists the root)",
        res.status == FAIL and "universe-miss" in res.detail and "tool" in res.detail,
        res.detail,
    )
    shutil.rmtree(home)
    mk_lone_repo(home / ".local" / "share")  # the strays' own scan used to prune exactly this path
    mk_lone_repo(home / "Library" / "caches")  # the sweep leaves ~/Library out, so the scan does too
    found = universe_problems(mk_ctx(sd, home=str(home), discovery_strays=True), load_sweep(sd.sweep))
    s.expect(
        "PS-2: the strays scan under $HOME does not prune ~/.local/share, and prunes only what the sweep leaves out",
        any(p.subject == f"{home}/.local/share" and "a git checkout on disk" in p.message for p in found)
        and not any("Library" in p.subject for p in found),
        str([str(p) for p in found]),
    )

    # F3 / PS-2: the breadth comes from the sweep's roots file, but never narrower than the default roots, so a sweep
    # taken with explicit ROOT arguments (or a top-level directory created after it) does not narrow this check
    home3 = sd.root / "r2-home3"
    for name in ("Documents", ".local/share", "Library"):
        (home3 / name).mkdir(parents=True)
    narrow = sd.root / "r2-narrow" / "git.tsv"
    narrow.parent.mkdir()
    copy_sweep(sd.sweep, narrow)
    write_roots(narrow, [str(work)])  # the sweep was run as `git-sweep.sh OUT work`
    res = check_sweep_fresh(mk_ctx(sd, sweep=narrow, home=str(home3), discovery_strays=True))
    s.expect(
        "F3: a sweep that walked only the roots it was given, not the default roots under $HOME, FAILs sweep-fresh",
        res.status == FAIL
        and "the sweep did not walk this default root" in res.detail
        and f"{home3}/Documents" in res.detail
        and "Library" not in res.detail,
        res.detail,
    )
    write_roots(narrow, [str(work), str(home3 / "Documents"), str(home3 / ".local")])
    res = check_sweep_fresh(mk_ctx(sd, sweep=narrow, home=str(home3), discovery_strays=True))
    s.expect(
        "F3: with every default root walked (.local/share is under the walked .local) the same sweep PASSes",
        res.status == PASS,
        res.detail,
    )
    (home3 / "NewProjects").mkdir()
    res = check_sweep_fresh(mk_ctx(sd, sweep=narrow, home=str(home3), discovery_strays=True))
    s.expect(
        "F3: a top-level directory created under $HOME after the sweep is a default root it did not walk",
        res.status == FAIL and f"{home3}/NewProjects" in res.detail,
        res.detail,
    )
    mk_lone_repo(home3 / "NewProjects" / "idea")
    res = check_sweep_fresh(mk_ctx(sd, sweep=narrow, home=str(home3), discovery_strays=True, discovery_roots=[home3 / "NewProjects"]))
    s.expect(
        "F3: --discovery-root still adds: the repository under the added root is a universe-miss",
        res.status == FAIL and f"{home3}/NewProjects/idea" in res.detail,
        res.detail,
    )

    # §12: the roots file is mandatory evidence, like the sweep itself
    bad = sd.root / "r2-badroots"
    bad.mkdir()
    for label, body in {
        "is missing": None,
        "has no #END row": f"{work}\n",
        "miscounts its roots": f"{work}\n#END rows=2\n",
        "names a relative root": "work\n#END rows=1\n",
    }.items():
        broken = bad / "git.tsv"
        copy_sweep(sd.sweep, broken)
        roots_path(broken).unlink(missing_ok=True)
        if body is not None:
            roots_path(broken).write_text(body)
        res = check_sweep_fresh(mk_ctx(sd, sweep=broken, scan_universe=True))
        s.expect(
            f"§12: a sweep whose roots file {label} FAILs sweep-fresh as input-unusable",
            res.status == FAIL and "input-unusable" in res.detail and "roots file" in res.detail,
            res.detail,
        )

    # H-NO-DEEP-READY: --no-deep skips exactly what a truncated bundle with a re-hashed manifest slips past
    code, lines = cli([*argv, "--no-deep"], os.path.isdir)
    s.expect(
        "H-NO-DEEP-READY: --no-deep can never say READY: UNPROVEN deep-verification, NOT-READY, exit 2",
        code == 2
        and lines[-1] == "NOT-READY"
        and any(ln.startswith("UNPROVEN deep-verification") for ln in lines)
        and not any(ln == "READY" for ln in lines),
        f"{code} {lines}",
    )
    # §8: a crashed check is exit 70 and NOT-READY, never an answer
    saved = list(CHECKS)
    CHECKS.insert(0, ("boom", lambda _ctx: 1 // 0))
    try:
        code, lines = cli(argv, os.path.isdir)
    finally:
        CHECKS[:] = saved
    s.expect(
        "§8: a check that crashes exits 70, prints FAIL with the error, and the verdict is NOT-READY",
        code == EXIT_INTERNAL
        and lines[-1] == "NOT-READY"
        and any(ln.startswith("FAIL boom internal error ZeroDivisionError") for ln in lines),
        f"{code} {lines}",
    )
    helptext = build_parser().format_help()
    s.expect(
        "PS-7: --help documents every exit code",
        all(f"  {c}" in helptext for c in ("0   READY", "1   NOT-READY", f"{EXIT_USAGE}  usage", f"{EXIT_INTERNAL}  internal")),
        helptext[-600:],
    )


def make_filtered_tar(run: Path, repo: Path, names: list[str], home: str) -> None:
    """A run's `filtered-tar` for a checkout: the named working-tree files, as the producer's §7 item holds them."""
    slug = slugify(str(repo), home)
    artifact = run / "dirty" / f"{slug}.filtered.tar"
    artifact.parent.mkdir(exist_ok=True)
    with tarfile.open(artifact, "w") as tf:
        for name in names:
            tf.add(repo / name, arcname=name)
    add_manifest_item(run, "filtered-tar", slug, str(repo), artifact, len(names), "working-tree files a filter keeps out of git")


def st_group_r2_gitdir(s: Suite, w: World, args: argparse.Namespace) -> None:
    s.group("round 2 (§6 §7): a raw git-dir copy where a bundle cannot carry the work; content git never stores")
    sg = spare_world(w, "r2-gitdir", args)
    plain, past = Path(sg.repos["plain"]), sg.start_ts - 3600
    common = os.path.realpath(f"{plain}/.git")
    slug = slugify(common, sg.home)

    def run(**over: object) -> Result:
        return check_git_preserved(mk_ctx(sg, **over))

    res = run()
    s.expect("r2: the spare world PASSes before any change (positive control)", res.status == PASS, res.detail)
    state = repo_state(mk_ctx_stub(), str(plain), common, True)
    s.expect(
        "§6.1: live git shows reflog-only commits for plain (its older stash entry), so its raw git-dir copy is required",
        bool(state.reflog_only()) and "reflog-only commits" in state.gitdir_reasons(),
        str(state.gitdir_reasons()),
    )
    dest, run_dir = clone_run(sg, "no-tar")
    drop_item(run_dir, "gitdir-tar", slug)
    res = run(preserve_root=dest)
    s.expect(
        "INT-2 / P7: a repository with reflog-only commits and no gitdir-tar item is not covered by its bundle alone",
        res.status == FAIL
        and "manifest-missing" in codes_of(res, str(plain))
        and "raw git dir copy is required (reflog-only commits)" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    lost = state.reflog_only()[0]
    member = f".git/objects/{lost[:2]}/{lost[2:]}"
    dest, run_dir = clone_run(sg, "tar-without-reflog-commit")
    tar_edit(run_dir / RunView(run_dir).one("gitdir-tar", slug)["file"], drop=lambda n: n == member)
    rehash(run_dir, "gitdir-tar", slug)
    res = run(preserve_root=dest)
    s.expect(
        "H-REFLOG-ONLY: the raw git-dir copy must HOLD the reflog-only commit's object, not merely exist",
        "gitdir-incomplete" in codes_of(res, str(plain)) and "reflog-only commit" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    # §6: the copy is in addition to the bundle. A bundle that is there and wrong is never replaced by it
    dest, run_dir = clone_run(sg, "bundle-wrong")
    set_field(run_dir, "bundle", slug, sha256="a" * 64)
    res = run(preserve_root=dest)
    s.expect(
        "§6: a corrupt bundle is still hash-mismatch although the repository has a raw git-dir copy",
        codes_of(res, str(plain)) == {"hash-mismatch"},
        str(blame(res)),
    )
    dest, run_dir = clone_run(sg, "bundle-failed")
    set_field(run_dir, "bundle", slug, status="failed")
    res = run(preserve_root=dest)
    s.expect(
        "§6: a bundle reported as failed is still a FAIL when the repository has a raw git-dir copy (fail closed; the "
        "copy stands in only for a partial clone or an unborn HEAD)",
        res.status == FAIL and codes_of(res, str(plain)) == {"item-status"},
        f"{blame(res)} {res.detail}",
    )

    # per-worktree refs: a commit only refs/worktree of a linked worktree reaches (the bundle does not carry it)
    wtbase, wtdet = sg.repos["wtbase"], Path(sg.repos["wtdet"])
    wt_common = os.path.realpath(f"{wtbase}/.git")
    with dated(past):
        kept = fx(wtdet, "commit-tree", fx(wtdet, "rev-parse", "HEAD^{tree}").strip(), "-m", "kept by a per-worktree ref").strip()
        fx(wtdet, "update-ref", "refs/worktree/keep", kept)
    res = run()
    s.expect(
        "P7: a commit reachable only from a linked worktree's refs/worktree needs a raw git-dir copy the run lacks",
        res.status == FAIL and "raw git dir copy is required (per-worktree refs)" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    dest, run_dir = clone_run(sg, "pwt")
    make_gitdir_tar(run_dir, wt_common, sg.home, "per-worktree refs")
    res = run(preserve_root=dest)
    s.expect("P7: with that copy in the run the repository PASSes (positive control)", res.status == PASS, f"{blame(res)} {res.detail}")
    tar_edit(run_dir / RunView(run_dir).one("gitdir-tar", slugify(wt_common, sg.home))["file"], drop=lambda n: n.endswith("/refs/worktree/keep"))
    rehash(run_dir, "gitdir-tar", slugify(wt_common, sg.home))
    res = run(preserve_root=dest)
    s.expect(
        "P7: a copy without the per-worktree ref file is gitdir-incomplete",
        "gitdir-incomplete" in str(res.problems) and "refs/worktree/keep" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    fx(wtdet, "update-ref", "-d", "refs/worktree/keep")

    # git-lfs objects live only in .git/lfs, which a bundle never carries
    lfs_object = plain / ".git" / "lfs" / "objects" / "ab" / "cd" / ("ab" * 32)
    put(lfs_object, "the only copy of a large binary\n")
    res = run()
    s.expect(
        "INT-2: a git-lfs object the run's raw git-dir copy predates is gitdir-incomplete",
        "gitdir-incomplete" in codes_of(res, str(plain)) and "large-file object" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    dest, run_dir = clone_run(sg, "lfs")
    drop_item(run_dir, "gitdir-tar", slug)
    make_gitdir_tar(run_dir, common, sg.home, "git-lfs objects")
    res = run(preserve_root=dest)
    s.expect("INT-2: re-made after the object arrived, the copy holds it and the run PASSes", res.status == PASS, f"{blame(res)}")
    safe = Path(sg.repos["safe"])
    put(safe / ".git" / "lfs" / "objects" / "aa" / "bb" / ("aa" * 32), "the only copy of a large binary\n")
    res = run()
    s.expect(
        "a8 / FP-UNSTORED-CONTENT: a clean PROVEN-ALL row holding git-lfs objects is not trusted: a remote listing cannot see them",
        res.status == FAIL
        and "manifest-missing" in codes_of(res, str(safe))
        and "git-lfs objects" in res.detail,
        f"{blame(res)} {res.detail}",
    )
    shutil.rmtree(safe / ".git" / "lfs")
    shutil.rmtree(plain / ".git" / "lfs")

    # submodule git dirs under modules/
    put(plain / ".git" / "modules" / "lib" / "HEAD", "ref: refs/heads/main\n")
    res = run()
    s.expect(
        "§6.4: submodule git dirs under modules/ the run's raw git-dir copy predates are gitdir-incomplete",
        "gitdir-incomplete" in codes_of(res, str(plain)) and "modules/" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    shutil.rmtree(plain / ".git" / "modules")

    # P9: git-lfs storage relocated outside the git dir has a tar of its own
    storage = sg.root / "lfs-store"
    put(storage / "objects" / "aa" / "bb" / ("ab" * 32), "payload\n")
    fx(plain, "config", "lfs.storage", str(storage))
    res = run()
    s.expect(
        "P9: an lfs.storage outside the git dir with no lfs-storage-tar item is not covered",
        res.status == FAIL and "lfs-storage-tar" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    dest, run_dir = clone_run(sg, "lfs-storage")
    artifact = run_dir / "bundles" / f"{slug}.lfs-storage.tar"
    with tarfile.open(artifact, "w") as tf:
        tf.add(storage, arcname=storage.name)
    add_manifest_item(run_dir, "lfs-storage-tar", slug, str(storage), artifact, 3, "lfs.storage outside the git dir")
    res = run(preserve_root=dest)
    s.expect("P9: with its lfs-storage-tar the run PASSes (positive control)", res.status == PASS, f"{blame(res)} {res.problems}")
    put(storage / "objects" / "aa" / "bb" / ("ab" * 32), "payload changed after the tar\n")
    res = run(preserve_root=dest)
    s.expect(
        "P9: a file of lfs.storage that changed size since the tar is gitdir-incomplete",
        "gitdir-incomplete" in codes_of(res, str(plain)) and "lfs.storage" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    shutil.rmtree(storage)
    storage.mkdir()  # the producer records a storage directory that holds nothing as an `empty` item
    dest, run_dir = clone_run(sg, "lfs-storage-empty")
    add_empty_item(run_dir, "lfs-storage-tar", slug, str(storage), "nothing in lfs.storage")
    res = run(preserve_root=dest)
    s.expect("P9: an empty lfs.storage with an `empty` lfs-storage-tar item PASSes", res.status == PASS, f"{blame(res)} {res.problems}")
    put(storage / "late.bin", "arrived after the run\n")
    res = run(preserve_root=dest)
    s.expect(
        "P9: an `empty` lfs-storage-tar item is wrong once the directory holds a file",
        "gitdir-incomplete" in codes_of(res, str(plain)) and "recorded empty" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    fx(plain, "config", "--unset", "lfs.storage")
    # an lfs.storage INSIDE the git dir is the lfs store (a relative value is relative to the git dir)
    put(plain / ".git" / "custom-lfs" / "objects" / "ab" / "cd" / ("cd" * 32), "the only copy of a large binary\n")
    fx(plain, "config", "lfs.storage", "custom-lfs")
    res = run()
    s.expect(
        "§6.3: an lfs.storage inside the git dir counts: its objects the raw copy predates are gitdir-incomplete",
        "gitdir-incomplete" in codes_of(res, str(plain)) and "large-file object" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    fx(plain, "config", "--unset", "lfs.storage")
    shutil.rmtree(plain / ".git" / "custom-lfs")

    # §7 / FP-UNSTORED-CONTENT: a clean filter keeps working-tree bytes out of every blob
    nested_a = Path(sg.repos["nestedA"])
    put(nested_a / ".gitattributes", "*.txt filter=same\n")
    fx(nested_a, "config", "filter.same.clean", "cat")
    put(nested_a / "kept.txt", "a filter that changes nothing\n")
    fx(nested_a, "add", ".gitattributes", "kept.txt")
    with dated(past):
        fx(nested_a, "commit", "-q", "-m", "a no-op filter")
    fx(nested_a, "update-ref", "refs/remotes/origin/main", "HEAD")
    fx(safe, "config", "filter.strip.clean", "grep -v OUTPUT")
    fx(safe, "config", "filter.strip.smudge", "cat")
    put(safe / ".gitattributes", "*.ipynb filter=strip\n")
    put(safe / "analysis.ipynb", "cell 1\nOUTPUT: aaaaaaaaaaaaaaaaaaaaaaaa\n")
    fx(safe, "add", ".gitattributes", "analysis.ipynb")
    with dated(past):
        fx(safe, "commit", "-q", "-m", "notebook")
    fx(safe, "update-ref", "refs/remotes/origin/main", "HEAD")
    notebook = safe / "analysis.ipynb"
    put(notebook, "cell 1\nOUTPUT: three days of results!!!\n")  # same size, new bytes that no blob holds
    write_sweep(sg.sweep, swept_checkouts(sg))
    write_held(sg.held, world_held_entries(sg.repos))
    refresh_tips(sg)
    os.utime(sg.held, None)
    s.expect(
        "FP-UNSTORED-CONTENT: git itself sees nothing (status is empty) ...",
        fx(safe, "status", "--porcelain") == "",
        fx(safe, "status", "--porcelain"),
    )
    res = run()
    s.expect(
        "FP-UNSTORED-CONTENT: ... yet a clean PROVEN-ALL row whose working tree holds bytes a clean filter drops needs a filtered-tar",
        res.status == FAIL
        and "manifest-missing" in codes_of(res, str(safe))
        and "filtered-tar" in str(res.problems)
        and not codes_of(res, str(nested_a)),
        f"{blame(res)} {res.problems}",
    )
    dest, run_dir = clone_run(sg, "filtered")
    make_filtered_tar(run_dir, safe, ["analysis.ipynb"], sg.home)
    res = run(preserve_root=dest)
    s.expect(
        "FP-UNSTORED-CONTENT: with a filtered-tar holding the file, matching the live bytes, the row is covered",
        res.status == PASS,
        f"{blame(res)} {res.problems}",
    )
    stamp = notebook.stat()
    put(notebook, "cell 1\nOUTPUT: THREE DAYS OF RESULTS!!!\n")
    os.utime(notebook, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    res = run(preserve_root=dest)
    s.expect(
        "FP-UNSTORED-CONTENT: bytes edited after the snapshot, size and mtime restored, are caught by the content compare",
        "filtered-uncovered" in codes_of(res, str(safe)) and "changed since the snapshot" in str(res.problems),
        f"{blame(res)} {res.problems}",
    )
    # what the producer does and does not put in a filtered-tar: links are members, credential names are left out
    put(notebook, "cell 1\nOUTPUT: three days of results!!!\n")
    os.utime(notebook, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    put(safe / ".gitattributes", "*.ipynb filter=strip\n*.token filter=strip\n")
    put(safe / "api.token", "line\nOUTPUT: a credential the filter drops from every blob\n")
    os.symlink("analysis.ipynb", safe / "link.ipynb")
    fx(safe, "add", ".gitattributes", "api.token", "link.ipynb")
    with dated(past):
        fx(safe, "commit", "-q", "-m", "a credential-named file and a link under the filter")
    fx(safe, "update-ref", "refs/remotes/origin/main", "HEAD")
    write_sweep(sg.sweep, swept_checkouts(sg))
    refresh_tips(sg)
    os.utime(sg.held, None)
    dest, run_dir = clone_run(sg, "filtered-members")
    make_filtered_tar(run_dir, safe, ["analysis.ipynb", "link.ipynb"], sg.home)
    res = run(preserve_root=dest)
    s.expect(
        "§7: a filtered symlink is a member of the tar, not an extra, and a credential-pattern file (left out by the "
        "producer) is reported, not demanded",
        res.status == PASS and "credential-pattern" in res.detail,
        f"{blame(res)} {res.problems} {res.detail}",
    )
    saved_limit = MAX_FILE_BYTES
    globals()["MAX_FILE_BYTES"] = 8
    try:
        res = run(preserve_root=dest)
    finally:
        globals()["MAX_FILE_BYTES"] = saved_limit
    s.expect(
        "§7: a filtered file over the size limit cannot be in the tar: unsnapshotable, as for every other snapshot",
        "unsnapshotable" in codes_of(res, str(safe)),
        f"{blame(res)} {res.problems}",
    )


def st_group_r2_payload(s: Suite, w: World, args: argparse.Namespace) -> None:
    s.group("round 2: ignored payload is exempt only beside the manifest that regenerates it; the attestation is bound")
    sp = spare_world(w, "r2-payload", args)
    safe = Path(sp.repos["safe"])
    (safe / ".git" / "info").mkdir(exist_ok=True)
    (safe / ".git" / "info" / "exclude").write_text("*.db\nnode_modules/\n__pycache__/\n.DS_Store\n")

    def check(**over: object) -> Result:
        return check_ignored_payload(mk_ctx(sp, **over))

    s.expect("r2: no ignored file PASSes (positive control)", check().status == PASS)
    names = ("build/thesis.db", "coverage/lab-results.db", ".cache/notes.db", "dist/results.db", "target/run.db")
    for rel in names:
        put(safe / rel, "irreplaceable\n")
    res, listed = check(), ignored_payload(str(safe))
    s.expect(
        "FP-IGNORED-NAME-EXEMPT: ignored databases under build/, coverage/, .cache/, dist/ and target/ are payload, not 'regenerable'",
        res.status == UNPROVEN and {n.split("/")[0] for n in names} <= {p.split("/")[0] for p in listed},
        str(listed),
    )
    for rel in names:
        (safe / rel).unlink()
    for rel in ("build", "coverage", ".cache", "dist", "target"):
        shutil.rmtree(safe / rel)
    s.expect("FP-IGNORED-NAME-EXEMPT: with those gone the check PASSes (positive control)", check().status == PASS)

    put(safe / "node_modules" / "pkg" / "index.js", "regenerable only if a manifest says how\n")
    put(safe / "frontend" / "node_modules" / "pkg" / "index.js", "regenerable only beside its own manifest\n")
    put(safe / "pkg" / "m.py", "x = 1\n")
    fx(safe, "add", "pkg/m.py")
    put(safe / "pkg" / "__pycache__" / "m.cpython-313.pyc", "byte-code\n")
    put(safe / ".DS_Store", "finder\n")
    res = check()
    s.expect(
        "FP-IGNORED-NAME-EXEMPT: node_modules with no tracked manifest beside it is payload; byte-code and .DS_Store are not",
        res.status == UNPROVEN
        and "node_modules" in res.detail + " ".join(res.extra)
        and "__pycache__" not in res.detail + " ".join(res.extra)
        and ".DS_Store" not in res.detail + " ".join(res.extra),
        res.detail,
    )
    put(safe / "package.json", "{}\n")
    fx(safe, "add", "package.json")
    res = check()
    shown = res.detail + " ".join(res.extra)
    s.expect(
        "FP-IGNORED-NAME-EXEMPT: a tracked package.json exempts the node_modules beside it, and only that one",
        res.status == UNPROVEN and "frontend/node_modules" in shown and "frontend/node_modules" in " ".join(res.extra),
        shown,
    )
    put(safe / "frontend" / "package.json", "{}\n")
    fx(safe, "add", "frontend/package.json")
    s.expect("FP-IGNORED-NAME-EXEMPT: and with its own manifest the second one is exempt too", check().status == PASS, check().detail)

    # H-IGNORED-ATTESTATION: signer, date and the list it covers
    put(safe / "local.db", "irreplaceable local database\n")
    items = ignored_payload(str(safe))
    digest, today = payload_digest(items), later_stamp()
    owner = sp.root / "payload-attest.tsv"

    def attest(*cells: str) -> Result:
        owner.write_text("\t".join(cells) + "\n")
        return check(ignored_payload_attestation=owner)

    s.expect("r2: the unlisted payload is UNPROVEN, and the detail names the sha256 to sign", check().status == UNPROVEN)
    res = attest(str(safe), "conductor", today, digest)
    s.expect("H-IGNORED-ATTESTATION: signer on the allow-list, a timestamp after the files and the list's sha256 settle it (positive control)", res.status == PASS, res.detail)
    cases = {
        "a signer on no allow-list": ((str(safe), "anyone-at-all", today, digest), "allow-list"),
        "a date in 2999": ((str(safe), "conductor", "2999-01-01", digest), "future"),
        "a date before the files existed": ((str(safe), "conductor", "2000-01-01", digest), "before the newest"),
        "today's bare date, which counts from 00:00:00 UTC (F4 / PS-4)": (
            (str(safe), "conductor", datetime.now(UTC).strftime("%Y-%m-%d"), digest),
            "bare date",
        ),
        "no sha256 at all": ((str(safe), "conductor", today), "sha256"),
        "the sha256 of another list": ((str(safe), "conductor", today, "0" * 64), "sha256"),
        "a date that is not ISO": ((str(safe), "conductor", "last tuesday", digest), "ISO"),
    }
    for label, (cells, needle) in cases.items():
        res = attest(*cells)
        s.expect(
            f"H-IGNORED-ATTESTATION: an attestation with {label} settles nothing",
            res.status == UNPROVEN and needle in res.detail,
            res.detail,
        )
    owner.write_text("\t".join((str(safe), "conductor", today, digest)) + "\n")
    put(safe / "added-after.db", "never reviewed\n")
    res = check(ignored_payload_attestation=owner)
    s.expect(
        "H-IGNORED-ATTESTATION: a payload added after the attestation reopens the check",
        res.status == UNPROVEN and "sha256" in res.detail,
        res.detail,
    )
    (safe / "added-after.db").unlink()
    res = check(ignored_payload_attestation=owner, waiver_signers=None)
    s.expect(
        "H-IGNORED-ATTESTATION: with no --waiver-signers allow-list no signer can be verified",
        res.status == UNPROVEN and "allow-list" in res.detail,
        res.detail,
    )


def st_group_usage_codes(s: Suite) -> None:
    s.group("H1 exit codes: a usage error is 64, never 2")
    s.expect(
        "an unknown flag exits 64", usage_exit(["--no-such-flag"]) == EXIT_USAGE, str(usage_exit(["--no-such-flag"]))
    )
    s.expect(
        "an abbreviated flag is not accepted (allow_abbrev is off) and exits 64",
        usage_exit(["--max-sweep-age", "30"]) == EXIT_USAGE,
        str(usage_exit(["--max-sweep-age", "30"])),
    )
    s.expect("a non-numeric bound exits 64", usage_exit(["--max-sweep-age-min", "soon"]) == EXIT_USAGE)
    s.expect(
        "a sweep age bound above its hard ceiling exits 64", usage_exit(["--max-sweep-age-min", "100000"]) == EXIT_USAGE
    )
    s.expect("a zero sweep age bound exits 64", usage_exit(["--max-sweep-age-min", "0"]) == EXIT_USAGE)
    s.expect(
        "a remote-held age bound above its hard ceiling exits 64",
        usage_exit(["--max-remote-held-age-min", "100000"]) == EXIT_USAGE,
    )
    s.expect("a negative gitfile depth exits 64", usage_exit(["--gitfile-depth", "-1"]) == EXIT_USAGE)
    # E1 / §8: asking for help is not a verdict, so it exits 64; exit 0 is reserved for READY
    s.expect("--help exits 64, never 0", usage_exit(["--help"]) == EXIT_USAGE, str(usage_exit(["--help"])))
    s.expect("-h exits 64, never 0", usage_exit(["-h"]) == EXIT_USAGE, str(usage_exit(["-h"])))
    for flag in USAGE_REQUIRED:
        s.expect(
            f"omitting the required {flag} is a usage error (exit 64), not a silent default",
            usage_exit([], omit=flag) == EXIT_USAGE,
            str(usage_exit([], omit=flag)),
        )
    s.expect(
        "negative control: with every required path given the command line parses and runs inert checks",
        usage_exit([]) is None,
    )
    s.expect(
        "DEFAULTS names no volume, no dated directory and no home-relative workspace",
        not any(
            ("/Volumes/" in str(v) or "20" in str(v) and "/" in str(v) or "Workspace" in str(v))
            for v in DEFAULTS.values()
        )
        and DEFAULTS["volumes_root"] == "/Volumes",
        str(DEFAULTS),
    )
    s.expect("EXIT_USAGE and EXIT_INTERNAL differ from every verdict code", {EXIT_USAGE, EXIT_INTERNAL}.isdisjoint((0, 1, 2)))


def rehash_manual(manual: Path, name: str) -> None:
    """Rewrite a manual copy's manifest to describe the copy as it is now (so only the planted defect can be at fault)."""
    base = manual / name
    lines = [
        f"{sha256_file(Path(c) / f)}  ./{(Path(c) / f).relative_to(base)}\n"
        for c, _d, fs in os.walk(base)
        for f in sorted(fs)
        if not (Path(c) / f).is_symlink()
    ]
    (manual / f"{name}.MANIFEST.sha256").write_text("".join(lines))


def st_group_manual_copies(s: Suite, w: World) -> None:
    s.group("F8 manual copies: alternates, objects, stashes, empty manifest, custody")
    plain = w.repos["plain"]
    counter = iter(range(100))

    def scenario() -> tuple[Path, Path, Path]:
        root = w.root / f"pm-{next(counter)}"
        shutil.copytree(w.run, root / w.run.name, symlinks=True)
        drop_item(root / w.run.name, "bundle", slugify(os.path.realpath(plain + "/.git"), w.home))
        manual = root / "manual-1"
        make_manual(manual, plain)
        return root, manual, manual / "plain"

    def verdict(root: Path, **over: object) -> tuple[Result, set[str], str]:
        """The overall result, plus the problems the manual copy ITSELF reports for plain's bundle component
        (settle_coverage shows only the closest source's problems, which may be the run's)."""
        ctx = mk_ctx(w, preserve_root=root, **over)
        res = check_git_preserved(ctx)
        present, _gone = prepare_needs(build_plan(load_sweep(ctx.sweep), load_remote_held(w.held)).needs)
        found = ManualSource(ctx, root / "manual-1").evaluate(present)
        own = [p for (kind, _id), ps in found.items() if kind == "bundle" for p in ps]
        return res, {p.code for p in own}, " | ".join(p.message for p in own)

    root, manual, copy = scenario()
    res, codes, _text = verdict(root)
    s.expect(
        "baseline: an honest manual copy of plain covers its bundle component",
        res.status == PASS and any("plain: bundle=manual-1" in ln for ln in res.extra),
        res.detail,
    )

    root, manual, copy = scenario()  # r10: every object is borrowed from the live repository through alternates
    shutil.rmtree(copy / ".git" / "objects")
    (copy / ".git" / "objects" / "info").mkdir(parents=True)
    (copy / ".git" / "objects" / "pack").mkdir()
    (copy / ".git" / "objects" / "info" / "alternates").write_text(plain + "/.git/objects\n")
    rehash_manual(manual, "plain")
    res, codes, text = verdict(root)
    s.expect(
        "r10: a manual copy that borrows its objects via alternates does not cover",
        res.status == FAIL and "alternates" in text and codes == {"manual-mismatch"},
        text,
    )
    s.expect(
        "the verdict itself names the manual copy's defect, not only the run's missing bundle item",
        "borrows objects via alternates" in str(res.problems),
        str(res.problems),
    )

    root, manual, copy = scenario()  # the same refs, but the objects are simply not there (and nothing is borrowed)
    shutil.rmtree(copy / ".git" / "objects")
    (copy / ".git" / "objects" / "pack").mkdir(parents=True)
    rehash_manual(manual, "plain")
    res, codes, text = verdict(root)
    s.expect(
        "a manual copy whose tip commits are missing from its object store does not cover",
        res.status == FAIL and "tip commit(s) are not in the copy's git dir" in text,
        text,
    )

    root, manual, copy = scenario()  # r13: the stash reflog is gone, only the top refs/stash survives
    (copy / ".git" / "logs" / "refs" / "stash").unlink()
    rehash_manual(manual, "plain")
    res, codes, text = verdict(root)
    s.expect(
        "r13: a manual copy that kept only the top stash does not cover",
        res.status == FAIL and "stash" in text and "stash-missing" in codes,
        text,
    )

    root, manual, copy = scenario()
    (manual / "plain.MANIFEST.sha256").write_text("")
    res, codes, text = verdict(root)
    s.expect(
        "a manual copy with an empty manifest does not cover",
        res.status == FAIL and "manifest has 0 entries" in text,
        text,
    )

    root, manual, copy = scenario()
    live_objects = Path(plain) / ".git" / "objects"
    shutil.rmtree(copy / ".git" / "objects")
    os.symlink(live_objects, copy / ".git" / "objects")
    res, codes, text = verdict(root)
    s.expect(
        "a manual copy whose objects directory is a symlink back to the Mac does not cover",
        res.status == FAIL and "is a symlink" in text,
        text,
    )

    root, manual, copy = scenario()
    res, codes, text = verdict(
        root, device_of=fixture_devices(w, mac=(root.name,)), media_of=fixture_media(w, mac=(root.name,))
    )
    s.expect(
        "H2: a manual copy on the Mac's own device is no custody",
        res.status == FAIL and "not off the Mac" in text,
        text,
    )


def st_group_recovery_copies(s: Suite, w: World) -> None:
    s.group("F7/F8 vanished rows: recovery copy checks, RESCUE-MANIFEST, shallow, unreadable, custody")
    counter = iter(range(100))

    def scenario(**row_extra: str) -> tuple[Ctx, Path, Path, Path]:
        tag = f"r{next(counter)}"
        home = w.root / "fakehome" / tag
        recovery = w.root / f"recovered-from-{tag}"
        home.mkdir(parents=True)
        copy = recovery / "Workspace" / "gone"
        copy.parent.mkdir(parents=True)
        repo = make_unpushed(copy.parent, "gone")
        write_rescue_manifest(recovery, "Workspace/gone")
        row = sweep_row(str(repo))
        row[0] = str(home / "Workspace" / "gone")
        header, values = list(SWEEP_COLS), row
        for key, value in row_extra.items():
            header.append(key)
            values = [*values, value]
        sweep = w.root / f"vanished-{tag}.tsv"
        sweep.write_text("\t".join(header) + "\n" + "\t".join(values) + "\n")
        ctx = mk_ctx(w, sweep=sweep, remote_held=None, home=str(home), recovery_root=recovery)
        return ctx, home, recovery, copy

    def why(ctx: Ctx) -> tuple[Result, str]:
        res = check_git_preserved(ctx)
        return res, " | ".join(str(p) for p in res.problems)

    ctx, home, recovery, copy = scenario()
    res, text = why(ctx)
    s.expect("baseline: a matching, re-hashing recovery copy is accepted", res.status == PASS, res.detail)

    ctx, home, recovery, copy = scenario()  # M07
    fx(copy, "checkout", "-q", "main")
    write_rescue_manifest(recovery, "Workspace/gone")
    res, text = why(ctx)
    s.expect(
        "a recovery copy on a different branch than the sweep recorded FAILs",
        res.status == FAIL and "HEAD is main, sweep recorded topic" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()  # M08
    fx(copy, "remote", "set-url", "origin", "https://example.invalid/other.git")
    write_rescue_manifest(recovery, "Workspace/gone")
    res, text = why(ctx)
    s.expect(
        "a recovery copy with a different origin than the sweep recorded FAILs",
        res.status == FAIL and "origin url differs from the sweep" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()  # M09: a branch whose tip is not a commit
    blob_file = copy / "blob-source.txt"
    blob_file.write_text("a blob is not a commit\n")
    blob = fx(copy, "hash-object", "-w", str(blob_file)).strip()
    blob_file.unlink()
    (copy / ".git" / "refs" / "heads" / "blobby").write_text(blob + "\n")
    write_rescue_manifest(recovery, "Workspace/gone")
    res, text = why(ctx)
    s.expect(
        "a recovery copy with a branch tip that is not a readable commit FAILs",
        res.status == FAIL and "branch tip commit(s) unreadable: refs/heads/blobby@" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()  # M01
    (copy / ".git" / "objects" / "info").mkdir(parents=True, exist_ok=True)
    (copy / ".git" / "objects" / "info" / "alternates").write_text("/somewhere/else/objects\n")
    write_rescue_manifest(recovery, "Workspace/gone")
    res, text = why(ctx)
    s.expect(
        "a recovery copy that borrows objects through alternates FAILs",
        res.status == FAIL and "borrows objects through objects/info/alternates" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()
    (recovery / "RESCUE-MANIFEST.sha256").unlink()
    res, text = why(ctx)
    s.expect(
        "F8: a recovery copy with no RESCUE-MANIFEST.sha256 is not accepted",
        res.status == FAIL and "no RESCUE-MANIFEST.sha256" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()
    (copy / ".git" / "description").write_text("one\n")
    write_rescue_manifest(recovery, "Workspace/gone")
    (copy / ".git" / "description").write_text("two\n")
    res, text = why(ctx)
    s.expect(
        "F8: a recovered file that no longer re-hashes against RESCUE-MANIFEST.sha256 is not accepted",
        res.status == FAIL and "sha256 mismatch" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()
    moved_git = recovery / "git-elsewhere"
    shutil.move(str(copy / ".git"), str(moved_git))
    (copy / ".git").write_text(f"gitdir: {moved_git}\n")
    write_rescue_manifest(recovery, "Workspace/gone")
    res, text = why(ctx)
    s.expect(
        "F8: a recovery copy whose .git is a gitfile (it can point back at the Mac) is not accepted",
        res.status == FAIL and "not a real directory" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()
    shutil.move(str(copy / ".git" / "objects"), str(recovery / "objects-elsewhere"))
    os.symlink(recovery / "objects-elsewhere", copy / ".git" / "objects")
    write_rescue_manifest(recovery, "Workspace/gone")
    res, text = why(ctx)
    s.expect(
        "F8: a recovery copy whose objects directory is a symlink is not accepted",
        res.status == FAIL and ".git/objects is a symlink" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()
    (copy / ".git" / "unlisted-note").write_text("added after the rescue\n")
    res, text = why(ctx)
    s.expect(
        "F8: a file the rescue manifest does not list is not accepted",
        res.status == FAIL and "not in the rescue manifest" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()
    root_commit = fx(copy, "rev-list", "--max-parents=0", "HEAD").split()[0]
    (copy / ".git" / "shallow").write_text(root_commit + "\n")
    write_rescue_manifest(recovery, "Workspace/gone")
    res, text = why(ctx)
    s.expect(
        "F8: a shallow recovery copy is not accepted when the sweep row was not shallow",
        res.status == FAIL and "shallow" in text,
        text,
    )

    ctx, home, recovery, copy = scenario(shallow="1")
    (copy / ".git" / "shallow").write_text(root_commit + "\n")
    write_rescue_manifest(recovery, "Workspace/gone")
    res, text = why(ctx)
    s.expect(
        "F8: the same shallow copy IS accepted when the sweep row says it was shallow (negative control)",
        res.status == PASS,
        text,
    )

    ctx, home, recovery, copy = scenario()  # F7/r9a: the live path is unreadable, so a matching copy proves nothing
    live = home / "Workspace" / "gone"
    live.mkdir(parents=True)
    (live / "keep.txt").write_text("still on the Mac\n")
    os.chmod(home / "Workspace", 0)
    try:
        res, text = why(ctx)
    finally:
        os.chmod(home / "Workspace", 0o755)
    s.expect(
        "F7: an unreadable (not vanished) checkout is not excused by a matching recovery copy",
        res.status == FAIL and "row-unverifiable" in text and "cannot confirm" in text,
        text,
    )
    shutil.rmtree(live)
    s.expect("the same row is accepted once the checkout is really gone (negative control)", why(ctx)[0].status == PASS)

    ctx, home, recovery, copy = scenario()
    (home / "Workspace").mkdir()
    (home / "Workspace" / "gone").write_text("a file squatting on the checkout path\n")
    res, text = why(ctx)
    s.expect(
        "a path that still exists (as a file) is not vanished, whatever a recovery copy says",
        res.status == FAIL and "still exists" in text,
        text,
    )

    ctx, home, recovery, copy = scenario()
    res, text = why(
        dataclasses.replace(
            ctx,
            device_of=fixture_devices(w, mac=(recovery.name,)),
            media_of=fixture_media(w, mac=(recovery.name,)),
        )
    )
    s.expect(
        "H2: a recovery copy on the Mac's own device is no custody",
        res.status == FAIL and "not custody" in text,
        text,
    )


def st_group_custody(s: Suite, w: World) -> None:
    s.group("H2 custody: symlinked artifacts and the Mac's own device")
    nh = w.repos["notheld"]
    slug = slugify(os.path.realpath(nh + "/.git"), w.home)
    dest, run = clone_run(w, "symlinked-b")
    s.expect(
        "baseline: a pristine cloned run PASSes", check_git_preserved(mk_ctx(w, preserve_root=dest)).status == PASS
    )
    bundle = run / "bundles" / (slug + ".bundle")
    bundle.unlink()
    os.symlink(w.run / "bundles" / (slug + ".bundle"), bundle)
    res = check_git_preserved(mk_ctx(w, preserve_root=dest))
    s.expect(
        "r6: an artifact that is a symlink is not custody",
        res.status == FAIL and "artifact-symlink" in {p.code for p in res.problems},
        res.detail,
    )
    res = check_git_preserved(
        mk_ctx(
            w, device_of=fixture_devices(w, mac=("preserve-root",)), media_of=fixture_media(w, mac=("preserve-root",))
        )
    )
    s.expect(
        "H2: a preserve run on the same device as $HOME is set aside, so nothing covers",
        res.status == FAIL
        and "same device as $HOME" in res.detail
        and "no usable source" in res.detail,  # the run itself is set aside, not merely its artifacts
        res.detail,
    )
    t7src, t7copy = w.root / "t7src-b", w.root / "t7copy-b"
    for base in (t7src, t7copy):
        put(base / "c.txt", "hello\n")
    (t7copy / "MANIFEST.sha256").write_text(shasum_line(t7copy / "c.txt", "c.txt"))
    ctx = mk_ctx(w, t7_unique=t7copy, t7_source=t7src)
    s.expect("baseline: an off-Mac t7 copy PASSes", check_t7_unique(ctx).status == PASS)
    res = check_t7_unique(
        dataclasses.replace(
            ctx, device_of=fixture_devices(w, mac=("t7copy-b",)), media_of=fixture_media(w, mac=("t7copy-b",))
        )
    )
    s.expect(
        "H2: a t7 copy on the Mac's own device FAILs",
        res.status == FAIL and "not off the Mac" in res.detail,
        res.detail,
    )
    (t7copy / "c.txt").unlink()
    os.symlink(t7src / "c.txt", t7copy / "c.txt")
    res = check_t7_unique(ctx)
    s.expect(
        "a t7 'copy' that is a symlink to the original FAILs",
        res.status == FAIL and "symlinked" in res.detail,
        res.detail,
    )
    ng = w.root / "ng-custody" / "run-20261021T120000Z-9"
    put(ng / "data" / "x.txt", "x\n")
    (ng / "MANIFEST.sha256").write_text(shasum_line(ng / "data/x.txt", "data/x.txt"))
    (ng / "RESULT.txt").write_text("PASS\n")
    src = w.root / "nongit-src"
    put_source(src / "cust" / "x.txt", "x\n", ng)
    items = w.root / "ng-custody-items.tsv"
    items.write_text(f"d\t{src / 'cust'}\tdata\n")
    nctx = mk_ctx(w, nongit_runs=[ng], nongit_items=[items])
    s.expect(
        "baseline: an off-Mac non-git run PASSes",
        check_nongit_homed(nctx).status == PASS,
        check_nongit_homed(nctx).detail,
    )
    res = check_nongit_homed(
        dataclasses.replace(
            nctx, device_of=fixture_devices(w, mac=("ng-custody",)), media_of=fixture_media(w, mac=("ng-custody",))
        )
    )
    s.expect(
        "H2: a non-git run on the Mac's own device FAILs",
        res.status == FAIL and "not off the Mac" in res.detail,
        res.detail,
    )


def st_group_external_scan(s: Suite, w: World) -> None:
    s.group("F4 external scan: alternates, symlinks, case, links on the volume, default volumes")
    vols = make_vols(w)
    plain_git = w.repos["plain"] + "/.git"
    ctx = mk_ctx(w, externals=["VolA", "VolB"], volumes_root=vols)
    s.expect(
        "baseline: the clean volumes PASS",
        check_no_external_dependency(ctx).status == PASS,
        check_no_external_dependency(ctx).detail,
    )

    def only(res: Result, entry: Path) -> bool:
        return res.status == FAIL and blame(res).get(str(entry)) == {"mac-dependency"}

    alt = vols / "VolB" / "alt-clone"
    fx(None, "clone", "-q", "--shared", w.repos["plain"], str(alt))
    res = check_no_external_dependency(ctx)
    s.expect(
        "r11a: a clone whose objects live on the Mac (objects/info/alternates) FAILs",
        only(res, alt / ".git" / "objects" / "info" / "alternates"),
        res.detail,
    )
    shutil.rmtree(alt)
    store = vols / "VolB" / "store" / ".git" / "objects"
    store.mkdir(parents=True)
    (vols / "VolB" / "local-alt" / ".git" / "objects" / "info").mkdir(parents=True)
    (vols / "VolB" / "local-alt" / ".git" / "objects" / "info" / "alternates").write_text(
        "../../../store/.git/objects\n"
    )
    res = check_no_external_dependency(ctx)
    s.expect(
        "negative control: relative alternates that stay on the volume PASS",
        res.status == PASS and "1 alternates/commondir" in res.detail,
        res.detail,
    )
    bare = vols / "VolB" / "bare.git" / "objects" / "info"
    bare.mkdir(parents=True)
    (bare / "alternates").write_text(plain_git + "/objects\n")
    res = check_no_external_dependency(ctx)
    s.expect(
        "a bare store (no .git entry at all) that borrows Mac objects FAILs", only(res, bare / "alternates"), res.detail
    )
    shutil.rmtree(vols / "VolB" / "bare.git")
    wt = vols / "VolB" / "wtstore" / ".git" / "worktrees" / "w1"
    wt.mkdir(parents=True)
    (wt / "commondir").write_text(plain_git + "\n")
    res = check_no_external_dependency(ctx)
    s.expect("a worktree admin dir whose commondir is on the Mac FAILs", only(res, wt / "commondir"), res.detail)
    (wt / "commondir").write_text("../..\n")
    s.expect(
        "negative control: commondir '../..' stays inside the volume and PASSes",
        check_no_external_dependency(ctx).status == PASS,
        check_no_external_dependency(ctx).detail,
    )
    shutil.rmtree(vols / "VolB" / "wtstore")
    shutil.rmtree(vols / "VolB" / "local-alt")
    shutil.rmtree(vols / "VolB" / "store")
    link = vols / "VolB" / "symlinked"
    link.mkdir()
    os.symlink(plain_git, link / ".git")
    res = check_no_external_dependency(ctx)
    s.expect("r11b: a .git symlink into the Mac FAILs", only(res, link / ".git"), res.detail)
    (link / ".git").unlink()
    os.symlink(vols / "VolA" / "main" / ".git", link / ".git")
    s.expect(
        "negative control: a .git symlink to a directory on a scanned volume PASSes",
        check_no_external_dependency(ctx).status == PASS,
        check_no_external_dependency(ctx).detail,
    )
    (link / ".git").unlink()
    upper = os.path.realpath(plain_git).replace("/private/", "/PRIVATE/", 1)
    if os.path.isdir(upper):  # a case-insensitive volume (the macOS default): same directory, different spelling
        (link / ".git").write_text(f"gitdir: {upper}\n")
        res = check_no_external_dependency(ctx)
        s.expect("r11c: a gitfile spelled in another case still FAILs", only(res, link / ".git"), res.detail)
        (link / ".git").unlink()
    os.symlink(w.repos["plain"], vols / "VolB" / "mac-link")
    (vols / "VolB" / "via-link").mkdir()
    (vols / "VolB" / "via-link" / ".git").write_text(f"gitdir: {vols}/VolB/mac-link/.git\n")
    res = check_no_external_dependency(ctx)
    s.expect(
        "r11d: a gitfile that reaches the Mac through a symlink on the volume FAILs",
        only(res, vols / "VolB" / "via-link" / ".git"),
        res.detail,
    )
    (vols / "VolB" / "via-link" / ".git").unlink()
    (vols / "VolB" / "mac-link").unlink()
    s.expect("everything cleaned up PASSes again", check_no_external_dependency(ctx).status == PASS)

    (vols / "Blank").mkdir()
    (vols / "Fresh").mkdir()
    os.symlink("/", vols / "Macintosh HD")
    found = discover_externals(vols, os.path.isdir, fixture_devices(w), w.home, fixture_media(w))
    s.expect(
        "F4: default externals are every mounted non-boot volume, blank-looking ones included, boot alias excluded",
        found == ["Blank", "Fresh", "VolA", "VolB"],
        str(found),
    )
    res = check_no_external_dependency(ctx)
    s.expect(
        "F4: a mounted volume missing from an explicit --externals list FAILs as volume-unscanned",
        res.status == FAIL and "volume-unscanned" in {p.code for p in res.problems},
        res.detail,
    )
    full = dataclasses.replace(ctx, externals=found)
    s.expect(
        "negative control: listing every mounted volume PASSes",
        check_no_external_dependency(full).status == PASS,
        check_no_external_dependency(full).detail,
    )
    required = [x for flag in USAGE_REQUIRED for x in (flag, str(w.root / "unused"))]
    args = build_parser().parse_args(["--volumes-root", str(vols), "--externals", "auto", *required])
    s.expect(
        "make_ctx derives the volume list itself for --externals auto",
        make_ctx(args, os.path.isdir, fixture_devices(w), fixture_media(w)).externals == found,
    )
    empty = w.root / "empty-vols"
    empty.mkdir()
    res = check_no_external_dependency(dataclasses.replace(ctx, externals=[], volumes_root=empty))
    s.expect(
        "a scan of zero volumes cannot PASS",
        res.status == FAIL and "no-volumes" in {p.code for p in res.problems},
        res.detail,
    )
    s.expect(
        "points_into_mac: every Mac spelling is recognised (case, firmlink, 'Macintosh HD')",
        all(
            points_into_mac(t, [])
            for t in (
                f"{MAC_PREFIXES[0]}/a/.git",
                f"{MAC_PREFIXES[0].upper()}/a/.git",
                f"{MAC_PREFIXES[1]}/a/.git",
                f"{MAC_PREFIXES[2]}/a/.git",
                f"/System/Volumes/Data{MAC_PREFIXES[0]}/a/.git",
            )
        ),
    )
    s.expect(
        "points_into_mac: a path inside a scanned volume or elsewhere is not the Mac",
        not points_into_mac(f"{MAC_PREFIXES[0]}/vol/x", [f"{MAC_PREFIXES[0]}/vol"])
        and not points_into_mac("/opt/x/.git", []),
    )


def items_stub() -> HomingItem:
    return HomingItem("d", "/nowhere", "d", (), frozenset())


def st_group_nongit_live(s: Suite, w: World) -> None:
    s.group("H5 non-git homing: the live source, a strict RESULT.txt")
    base = w.root / "ngl"
    run = base / "run-20261021T120000Z-5"
    src = w.root / "nongit-src" / "live"
    put(run / "data" / "x.txt", "x\n")
    put(run / "data" / "y.bin", bytes(range(50)))
    (run / "MANIFEST.sha256").write_text(
        shasum_line(run / "data/x.txt", "data/x.txt") + shasum_line(run / "data/y.bin", "data/y.bin")
    )
    (run / "RESULT.txt").write_text("mode=apply\nRESULT: PASS\n")
    put_source(src / "x.txt", "x\n", run)
    put_source(src / "y.bin", bytes(range(50)), run)
    items = w.root / "ngl-items.tsv"
    items.write_text(f"d\t{src}\tdata\t*.tmp\n")
    ctx = mk_ctx(w, nongit_runs=[run], nongit_items=[items])

    def verdict() -> Result:
        return check_nongit_homed(ctx)

    s.expect("baseline: a run that matches its live source PASSes", verdict().status == PASS, verdict().detail)
    after = stamp_of(run) + 7200
    (src / "x.txt").write_text("v2 edited on the Mac after the homing run\n")
    os.utime(src / "x.txt", (after, after))
    res = verdict()
    s.expect(
        "r8: a source file edited after the run FAILs (size differs)",
        res.status == FAIL and "changed since the run" in res.detail,
        res.detail,
    )
    (src / "x.txt").write_text("y\n")  # same size, newer mtime
    os.utime(src / "x.txt", (after, after))
    res = verdict()
    s.expect(
        "r8: a same-size edit with a newer mtime FAILs too",
        res.status == FAIL and "changed since the run" in res.detail,
        res.detail,
    )
    put_source(src / "x.txt", "x\n", run)
    s.expect(
        "negative control: the source restored to its old state PASSes", verdict().status == PASS, verdict().detail
    )
    put(src / "b-new.txt", "created after the run\n")
    res = verdict()
    s.expect(
        "r8: a new file in the source that was never homed FAILs",
        res.status == FAIL and "never homed" in res.detail and "b-new.txt" in res.detail,
        res.detail,
    )
    (src / "b-new.txt").unlink()
    put(src / "scratch.tmp", "excluded by the item's glob\n")
    put(src / ".env", "excluded by the credential rule\n")  # allow-secret: fixture name only, no value
    s.expect(
        "negative control: files the item's globs or the credential rule skip do not count as un-homed",
        verdict().status == PASS,
        verdict().detail,
    )
    put(src / "listed.bin", "in EXCLUDED.tsv\n")
    (run / "EXCLUDED.tsv").write_text(
        f"kind\tsource_path\tbytes\treason\ndataless-placeholder\t{src / 'listed.bin'}\t3\tplaceholder\n"
    )
    res = verdict()
    s.expect(  # N2 flips the old assertion: the run's own unhashed list no longer spares a readable file
        "N2: a readable file listed in EXCLUDED.tsv as a dataless placeholder is still un-homed and FAILs",
        res.status == FAIL and "EXCLUDED.tsv row" in res.detail and "never homed" in res.detail,
        res.detail,
    )
    put(src / ".claude.json", "{}\n")  # a credential name the homing tool lists, outside the predicate's own patterns
    (run / "EXCLUDED.tsv").write_text(
        "kind\tsource_path\tbytes\treason\n"
        f"credential-file\t{src / '.claude.json'}\t3\t.claude.json\n"
        f"dataless-placeholder\t{src / 'gone-after-the-run.bin'}\t3\tplaceholder\n"
    )
    (src / "listed.bin").unlink()
    s.expect(
        "negative control: a credential-file row whose name matches a credential pattern is honoured, and a row for a "
        "path that is gone is never consulted",
        verdict().status == PASS,
        verdict().detail,
    )
    for flagged, label, kind in (
        (0x40000000, "dataless", "dataless-placeholder"),
        (0, "a hydrated (unflagged) file", "dataless-placeholder"),
    ):
        problem = excluded_stat_problem(
            kind, types.SimpleNamespace(st_mode=stat.S_IFREG, st_flags=flagged), "x.bin", "x.bin", items_stub()
        )
        s.expect(f"excluded_stat_problem: {label} file as a dataless placeholder", (problem == "") == bool(flagged))
    for label, mode, ok in (("a fifo", stat.S_IFIFO, True), ("a directory", stat.S_IFDIR, False)):
        problem = excluded_stat_problem(
            "special-file", types.SimpleNamespace(st_mode=mode, st_flags=0), "p", "p", items_stub()
        )
        s.expect(f"excluded_stat_problem: {label} as a special file", (problem == "") == ok, problem)
    (run / "EXCLUDED.tsv").unlink()
    (src / ".claude.json").unlink()
    (src / "y.bin").unlink()
    s.expect("negative control: a source file deleted after the run loses nothing and PASSes", verdict().status == PASS)
    put_source(src / "y.bin", bytes(range(50)), run)

    # the homing tool snapshots a SQLite database with .backup (journal mode and size change) and skips its sidecars
    import sqlite3

    live_db, copy_db = src / "notes.sqlite", run / "data" / "notes.sqlite"
    conn = sqlite3.connect(live_db)
    conn.execute("create table n (v text)")
    conn.executemany("insert into n values (?)", [("x" * 40,)] * 2000)
    conn.commit()
    conn.close()
    snap = sqlite3.connect(copy_db)
    sqlite3.connect(live_db).backup(snap)
    snap.execute("vacuum")
    snap.close()
    (src / "notes.sqlite-wal").write_bytes(b"w" * 64)
    (src / "notes.sqlite-shm").write_bytes(b"s" * 64)
    for name in ("notes.sqlite", "notes.sqlite-wal", "notes.sqlite-shm"):
        os.utime(src / name, (stamp_of(run) - 3600,) * 2)
    snap = sqlite3.connect(copy_db)
    snap.execute("delete from n where rowid > 25")
    snap.commit()
    snap.execute("vacuum")
    snap.close()
    (run / "RESULT.txt").write_text("mode=apply\nRESULT: PASS\n")
    (run / "MANIFEST.sha256").write_text(
        "".join(shasum_line(run / rel, rel) for rel in ("data/x.txt", "data/y.bin", "data/notes.sqlite"))
    )
    s.expect(
        "a snapshotted SQLite database may differ in size from the live file, and its un-copied sidecars are covered",
        live_db.stat().st_size != copy_db.stat().st_size and verdict().status == PASS,
        f"{live_db.stat().st_size} vs {copy_db.stat().st_size}: {verdict().detail}",
    )
    os.utime(src / "notes.sqlite-wal", (after, after))
    res = verdict()
    s.expect(
        "a sidecar written after the run means the database changed after it: FAIL",
        res.status == FAIL and "changed since the run" in res.detail and "notes.sqlite-wal" in res.detail,
        res.detail,
    )
    os.utime(src / "notes.sqlite-wal", (stamp_of(run) - 3600,) * 2)
    (src / "orphan.sqlite-wal").write_bytes(b"w")
    res = verdict()
    s.expect(
        "negative control: a sidecar whose database was never homed is un-homed data and FAILs",
        res.status == FAIL and "never homed" in res.detail,
        res.detail,
    )
    (src / "orphan.sqlite-wal").unlink()
    s.expect("the run PASSes again once the stray sidecar is gone", verdict().status == PASS, verdict().detail)

    other = w.root / "ngl-items-other.tsv"
    other.write_text(f"d\t{src}\telsewhere\n")
    res = check_nongit_homed(dataclasses.replace(ctx, nongit_items=[other]))
    s.expect(
        "an items file that does not describe this run's entries FAILs",
        res.status == FAIL and "no --nongit-items file matches" in res.detail,
        res.detail,
    )
    res = check_nongit_homed(dataclasses.replace(ctx, nongit_items=[]))
    s.expect(
        "with no items file the copy cannot be compared with the live source, so it FAILs",
        res.status == FAIL and "none was given" in res.detail,
        res.detail,
    )
    for label, text, ok in (
        ("PASS then a RESULT: FAIL tag", "PASS\nRESULT: FAIL\n", False),
        ("PASS then a bare FAIL line", "PASS\nFAIL: 3 files differ\n", False),
        ("PASS then a PARTIAL line", "PASS\nPARTIAL\n", False),
        ("two RESULT tags, the last one PASS", "RESULT: FAIL\nRESULT: PASS\n", False),
        ("a dry run", "RESULT: DRY-RUN (nothing written)\n", False),
        ("no verdict at all", "mode=apply\nitems=2\n", False),
        ("PASS alone", "PASS\n", True),
        ("PASS then a PASS tag", "PASS\nRESULT: PASS\n", True),
        ("mode line then a PASS tag", "mode=apply\nRESULT: PASS\n", True),
    ):
        (run / "RESULT.txt").write_text(text)
        res = verdict()
        s.expect(
            f"RESULT.txt strictness: {label} {'PASSes' if ok else 'FAILs'}",
            (res.status == PASS) == ok,
            res.detail,
        )


def st_group_time_bounds(s: Suite, w: World) -> None:
    s.group("H6 time: hard ceilings, remote-held age, future-dated evidence")
    d = w.root / "timecase"
    d.mkdir()
    sweep = d / "git.tsv"
    copy_sweep(w.sweep, sweep)
    ctx = mk_ctx(w, sweep=sweep)
    over = dataclasses.replace(ctx, max_sweep_age_min=MAX_SWEEP_AGE_CEILING_MIN * 10)
    old = time.time() - 3600 * 5
    os.utime(sweep, (old, old))
    res = check_sweep_fresh(over)
    s.expect(
        "a sweep age bound above its hard ceiling FAILs even when the sweep is 'fresh enough' for it",
        res.status == FAIL and "outside" in res.detail,
        res.detail,
    )
    os.utime(sweep, None)
    s.expect(
        "negative control: the ceiling itself is an allowed bound",
        check_sweep_fresh(dataclasses.replace(ctx, max_sweep_age_min=MAX_SWEEP_AGE_CEILING_MIN)).status == PASS,
    )

    held = d / "remote-held.tsv"
    shutil.copy(w.held, held)
    shutil.copy(w.held.parent / "tips.tsv", d / "tips.tsv")  # the proof is bound to the tips beside it
    hctx = mk_ctx(w, remote_held=held)
    s.expect(
        "baseline: a fresh remote-held file is usable",
        check_git_preserved(hctx).status == PASS,
        check_git_preserved(hctx).detail,
    )
    days_old = time.time() - 3 * 86400
    os.utime(held, (days_old, days_old))
    res = check_git_preserved(hctx)
    s.expect(
        "H6: a remote-held file older than its bound FAILs (its PROVEN-ALL verdicts are stale)",
        res.status == FAIL and "over the" in res.detail,
        res.detail,
    )
    s.expect(
        "negative control: the same old file passes under a bound that admits it",
        check_git_preserved(dataclasses.replace(hctx, max_remote_held_age_min=MAX_REMOTE_HELD_AGE_CEILING_MIN)).status
        == PASS,
    )
    s.expect(
        "a remote-held age bound above its hard ceiling FAILs",
        check_git_preserved(
            dataclasses.replace(hctx, max_remote_held_age_min=MAX_REMOTE_HELD_AGE_CEILING_MIN * 10)
        ).status
        == FAIL,
    )
    soon = time.time() + 7200
    os.utime(held, (soon, soon))
    res = check_git_preserved(hctx)
    s.expect("a future-dated remote-held file FAILs", res.status == FAIL and "future" in res.detail, res.detail)
    os.utime(held, None)

    items = d / "cred-items.txt"
    items.write_text("deploy-key held-by: 1Password 2999-01-01\n")
    res = check_credential_route_items(mk_ctx(w, credential_attestation=items))
    s.expect(
        "a future-dated credential attestation line stays UNPROVEN",
        res.status == UNPROVEN and "future" in res.detail,
        res.detail,
    )
    items.write_text(f"deploy-key held-by: 1Password {datetime.now(UTC).strftime('%Y-%m-%d')}\n")
    s.expect(
        "negative control: today's date is accepted",
        check_credential_route_items(mk_ctx(w, credential_attestation=items)).status == PASS,
    )
    s.expect(
        "is_future: a date-only value counts from its first second, a past datetime is not future",
        is_future("2999-01-01", time.time())
        and not is_future(datetime.now(UTC).strftime("%Y-%m-%d"), time.time())
        and not is_future("2020-01-01T00:00:00+00:00", time.time()),
    )


def st_group_object_primitives(s: Suite, w: World) -> None:
    s.group("pack index and raw git-dir reading")
    repo = make_repo(w.root / "unit", "packed")
    fx(repo, "gc", "-q")
    idx = next((repo / ".git" / "objects" / "pack").glob("pack-*.idx")).read_bytes()
    tip = fx(repo, "rev-parse", "HEAD").strip()
    s.expect("idx_has finds an object that is in the pack", idx_has(idx, tip))
    s.expect(
        "idx_has refuses objects that are not in the pack (including the fanout edges)",
        not idx_has(idx, "1" * 40) and not idx_has(idx, "00" + "0" * 38) and not idx_has(idx, "ff" * 20),
    )
    s.expect("idx_has refuses a file that is not a v2 index", not idx_has(b"not an index at all", tip))
    complete, hollow = w.root / "unit" / "complete.tar", w.root / "unit" / "hollow.tar"
    with tarfile.open(complete, "w") as tf:
        tf.add(repo / ".git", arcname=".git")
    with tarfile.open(hollow, "w") as tf:
        tf.add(repo / ".git", arcname=".git", filter=lambda ti: None if ti.name.startswith(".git/objects/") else ti)
    _refs, missing, _idx, err = inspect_gitdir_tar(str(complete), ".git", [tip])
    s.expect(
        "a raw git-dir tar that carries the tip (in its pack) reports nothing missing",
        not err and missing == [],
        str((err, missing)),
    )
    _refs, missing, _idx, err = inspect_gitdir_tar(str(hollow), ".git", [tip])
    s.expect(
        "a raw git-dir tar without the tip's object reports it missing",
        not err and missing == [tip],
        str((err, missing)),
    )


def st_group_media(s: Suite, w: World) -> None:
    s.group("H2a physical media: the real probe and its fixture stand-in")
    root = default_media_of("/")
    s.expect("the boot volume is not external media", not root.external, root.why)
    gone = default_media_of(str(w.root / "no-such-path"))
    s.expect("a path that does not exist is not external media", not gone.external, gone.why)
    s.expect("an empty path is not external media", not default_media_of("").external)
    # the review's H2a repro: an image file kept on the Mac, attached as its own volume, has a device of its own and
    # reports itself as external removable media; only the backing file's disk tells the truth
    image, mount = w.root / "media" / "looks-external.dmg", w.root / "media" / "mnt"
    mount.mkdir(parents=True)
    made = subprocess.run(
        ["hdiutil", "create", "-quiet", "-size", "8m", "-fs", "HFS+", "-volname", "LooksExternal", str(image)],
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    s.expect("fixture: hdiutil made the disk image", made.returncode == 0, made.stderr.decode("utf-8", "replace"))
    attached = subprocess.run(
        ["hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", str(mount), str(image)],
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    try:
        s.expect("fixture: hdiutil attached the image", attached.returncode == 0, attached.stderr.decode("utf-8", "replace"))
        seen = default_media_of(str(mount))
        s.expect(
            "a disk image whose file lives on the Mac is not external, though it has its own device (H2a)",
            not seen.external and "disk image backed by" in seen.why and os.stat(mount).st_dev != os.stat(w.root).st_dev,
            seen.why,
        )
    finally:
        if attached.returncode == 0:
            subprocess.run(["hdiutil", "detach", "-quiet", "-force", str(mount)], check=False, timeout=120)
    fake = fixture_media(w, mac=("media",))
    s.expect(
        "fixture stand-in: the Mac's zones are internal, the volumes external, a missing path neither",
        not fake(str(w.root / "work")).external
        and not fake(str(w.root / "media")).external
        and fake(str(w.root)).external
        and not fake(str(w.root / "no-such-path")).external,
    )


# ----------------------------------------------------------------------------------------------------
# round 2, custody lane (H2a C1-C5 X1-X3 D1 N1-N4 W1-W3 T1 INT-7). Each FALSE-PASS case builds the defect and judges it
# through the shipped entry points (check_* and main()), so the same assertion fails on the file before the fix.
# ----------------------------------------------------------------------------------------------------
def internal_media(_path: str) -> Media:
    """A media probe that puts every path on the Mac's own APFS volume: a device of its own, but not an external disk."""
    return Media(False, "internal-volume", "an internal APFS volume with a device of its own")


def st_group_custody_media(s: Suite, w: World) -> None:
    s.group("H2a custody is the physical media: a device that differs from $HOME's proves nothing")
    external, internal = mk_ctx(w), mk_ctx(w, media_of=internal_media)  # both see the fixture's external-looking device
    artifact = w.run / "MANIFEST.tsv"
    s.expect("baseline: an artifact on external media is custody", custody_problem(external, artifact) == "")
    why = custody_problem(internal, artifact)
    s.expect(
        "H2a: an artifact on an internal volume with its own device is not custody",
        bool(why) and "not on an external disk" in why,
        why,
    )
    res = check_git_preserved(internal)
    s.expect(
        "H2a: a preserve run on an internal volume is set aside, so nothing covers",
        res.status == FAIL and "no usable source" in res.detail and "not on an external disk" in res.detail,
        res.detail,
    )
    t7src, t7copy = w.root / "cmedia-t7src", w.root / "cmedia-t7copy"
    for base in (t7src, t7copy):
        put(base / "c.txt", "hello\n")
    (t7copy / "MANIFEST.sha256").write_text(shasum_line(t7copy / "c.txt", "c.txt"))
    t7 = mk_ctx(w, t7_unique=t7copy, t7_source=t7src)
    res = check_t7_unique(dataclasses.replace(t7, media_of=internal_media))
    s.expect(
        "H2a: a t7 copy on an internal volume FAILs",
        check_t7_unique(t7).status == PASS and res.status == FAIL and "not off the Mac" in res.detail,
        res.detail,
    )
    ng = w.root / "cmedia-ng" / "run-20261021T120000Z-9"
    put(ng / "data" / "x.txt", "x\n")
    (ng / "MANIFEST.sha256").write_text(shasum_line(ng / "data/x.txt", "data/x.txt"))
    (ng / "RESULT.txt").write_text("PASS\n")
    put_source(w.root / "nongit-src" / "cmedia" / "x.txt", "x\n", ng)
    items = w.root / "cmedia-items.tsv"
    items.write_text(f"d\t{w.root / 'nongit-src' / 'cmedia'}\tdata\n")
    nctx = mk_ctx(w, nongit_runs=[ng], nongit_items=[items])
    res = check_nongit_homed(dataclasses.replace(nctx, media_of=internal_media))
    s.expect(
        "H2a: a non-git run on an internal volume FAILs",
        check_nongit_homed(nctx).status == PASS and res.status == FAIL and "not off the Mac" in res.detail,
        res.detail,
    )
    counted: list[str] = []

    def counting(path: str) -> Media:
        counted.append(path)
        return fixture_media(w)(path)

    probing = mk_ctx(w, media_of=counting)
    for path in (w.run / "MANIFEST.tsv", w.run / "bundles", w.run / "run.log"):
        custody_problem(probing, path)
    s.expect("the media of a device is probed once, not once per artifact", len(counted) == 1, str(counted))
    vols = w.root / "cmedia-vols"
    (vols / "VolX").mkdir(parents=True)
    s.expect(
        "H2a: a mounted volume the probe places on the Mac's own disk is not auto-listed as an external",
        discover_externals(vols, os.path.isdir, fixture_devices(w), w.home, internal_media) == []
        and discover_externals(vols, os.path.isdir, fixture_devices(w), w.home, fixture_media(w)) == ["VolX"],
    )
    unplaced = discover_externals(
        vols, os.path.isdir, fixture_devices(w), w.home, lambda _p: Media(False, "", "the probe could not place it")
    )
    s.expect("a volume the probe cannot place at all stays listed, so the scan reports it", unplaced == ["VolX"])


def st_group_custody_image(s: Suite, w: World) -> None:
    s.group("H2a with the production probes: a disk image kept on the Mac is no custody and no external volume")
    base = w.root / "cimage"
    vols = base / "vols"
    mount = vols / "BackupImg"
    mount.mkdir(parents=True)
    image = base / "backup.dmg"
    made = subprocess.run(
        ["hdiutil", "create", "-quiet", "-size", "8m", "-fs", "HFS+", "-volname", "BackupImg", str(image)],
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    s.expect("fixture: hdiutil made the disk image", made.returncode == 0, made.stderr.decode("utf-8", "replace"))
    if made.returncode != 0:
        return
    attached = subprocess.run(
        ["hdiutil", "attach", "-quiet", "-nobrowse", "-mountpoint", str(mount), str(image)],
        check=False,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        timeout=120,
    )
    try:
        s.expect("fixture: hdiutil attached the image", attached.returncode == 0, attached.stderr.decode("utf-8", "replace"))
        if attached.returncode != 0:
            return
        artifact = mount / "preserve-root" / "run-20261021T120000Z" / "artifact.bin"
        put(artifact, b"x" * 100)
        real = mk_ctx(
            w,
            device_of=default_device_of,
            media_of=default_media_of,
            is_mount=os.path.ismount,
            volumes_root=vols,
            externals=["BackupImg"],
        )
        s.expect(
            "fixture: the mounted image has a device of its own, which is what the old test mistook for custody",
            default_device_of(str(mount)) != default_device_of(w.home),
        )
        why = custody_problem(real, artifact)
        s.expect(
            "H2a: an artifact inside a disk image stored on the Mac is no custody",
            bool(why) and "not on an external disk" in why,
            why,
        )
        res = check_no_external_dependency(real)
        s.expect(
            "H2a: an image on the Mac listed as an external volume is refused as not-external",
            res.status == FAIL and "not-external" in {p.code for p in res.problems},
            res.detail,
        )
        s.expect(
            "H2a: such an image is not auto-listed as an external volume",
            discover_externals(vols, os.path.ismount, default_device_of, w.home, default_media_of) == [],
        )
    finally:
        if attached.returncode == 0:
            subprocess.run(["hdiutil", "detach", "-quiet", "-force", str(mount)], check=False, timeout=120)


def st_group_custody_units(s: Suite, w: World) -> None:
    s.group("custody primitives: path tokens, markers, git-dir findings, unescaping")
    marked = "/h/work/custody-staging/disp"
    s.expect(
        "a disposable marker is a whole path component: the directory above a checkout counts, its look-alikes do not",
        has_disposable_marker(marked)
        and not has_disposable_marker("/h/work/custody-staging")
        and has_disposable_marker("/h/pytest-fixtures/x")
        and not has_disposable_marker("/h/pytest-fixtures-formatted/x")
        and has_disposable_marker("/h/a/.tmp/plugins/x")
        and not has_disposable_marker("/h/a/.tmp/pluginsx/y"),
    )
    probe = w.root / "cunits-evidence.txt"
    for text, ok in (
        ("see /a/b\n", True),
        ("see /a/b.\n", True),
        ('path: "/a/b",\n', True),
        ("(/a/b)\n", True),
        ("/a/b-v2\n", False),
        ("/a/b/sub\n", False),
        ("/a/b.bak\n", False),
        ("/mnt/old/a/b\n", False),
        ("", False),
    ):
        probe.write_text(text)
        s.expect(f"W1: evidence {text!r} {'names' if ok else 'does not name'} /a/b", hash_and_find(str(probe), [b"/a/b"])[1] == ok)
    s.expect(
        "tsv_unescape undoes the homing tool's escaping",
        tsv_unescape("a\\\\b\\tc\\nd") == "a\\b\tc\nd" and tsv_unescape("plain") == "plain",
    )
    repo = make_repo(w.root / "cunits", "findings", remote=False)
    s.expect("an honest git dir has no custody finding", custody_git_findings(repo / ".git") == [])
    cases: dict[str, tuple[str, Callable[[Path], None]]] = {
        "symlink": ("link", lambda g: os.symlink(g.parent.parent / "outside-target", g / "refs" / "heads" / "alias")),
        "commondir": ("top", lambda g: (g / "commondir").write_text("../elsewhere\n")),
        "alternates": ("case", lambda g: (g / "objects" / "info" / "ALTERNATES").write_text("/x/objects\n")),
    }
    for kind, (_label, plant) in cases.items():
        twin = w.root / "cunits" / f"findings-{kind}"
        shutil.copytree(repo, twin, symlinks=True)
        (twin / ".git" / "objects" / "info").mkdir(parents=True, exist_ok=True)
        plant(twin / ".git")
        found = {k for k, _r, _d in custody_git_findings(twin / ".git")}
        s.expect(f"custody_git_findings reports a planted {kind}", found == {kind}, str(found))
    hooked = w.root / "cunits" / "findings-hook"
    shutil.copytree(repo, hooked, symlinks=True)
    (hooked / ".git" / "hooks").mkdir(exist_ok=True)
    os.symlink("../../tracked.txt", hooked / ".git" / "hooks" / "pre-commit")
    s.expect(
        "a git-dir link that resolves inside the copy (a hook pointing at a work-tree script) is not a finding",
        custody_git_findings(hooked / ".git") == [],
        str(custody_git_findings(hooked / ".git")),
    )
    inside = w.root / "cunits" / "findings-inside"
    shutil.copytree(repo, inside, symlinks=True)
    (inside / ".git" / "worktrees" / "w1").mkdir(parents=True)
    (inside / ".git" / "worktrees" / "w1" / "commondir").write_text("../..\n")
    s.expect(
        "a worktrees/* commondir that stays inside the git dir is not a finding",
        custody_git_findings(inside / ".git") == [],
        str(custody_git_findings(inside / ".git")),
    )
    sealed = w.root / "cunits" / "findings-sealed"
    shutil.copytree(repo, sealed, symlinks=True)
    os.chmod(sealed / ".git" / "refs", 0)
    try:
        found = {k for k, _r, _d in custody_git_findings(sealed / ".git")}
    finally:
        os.chmod(sealed / ".git" / "refs", 0o755)
    s.expect("a directory the walk cannot list is a finding, never read as clean", found == {"unreadable"}, str(found))


def custody_manual_root(w: World, tag: str) -> tuple[Path, Path]:
    """A preserve root whose run lacks plain's bundle (only a manual copy can cover it), and an empty manual-1."""
    root = w.root / f"cc-{tag}"
    shutil.copytree(w.run, root / w.run.name, symlinks=True)
    drop_item(root / w.run.name, "bundle", slugify(os.path.realpath(w.repos["plain"] + "/.git"), w.home))
    manual = root / "manual-1"
    manual.mkdir(parents=True)
    return root, manual


def custody_manual_verdict(w: World, root: Path, **over: object) -> tuple[Result, str, set[str]]:
    res = check_git_preserved(mk_ctx(w, preserve_root=root, **over))
    return res, " | ".join(str(p) for p in res.problems), {p.code for p in res.problems if p.subject == w.repos["plain"]}


def custody_recovery_ctx(w: World, tag: str, build: Callable[[Path, Path], None], **over: object) -> Ctx:
    """A sweep row for a vanished checkout whose recovery copy is `build`'s doing. The Mac-side twin lives in the
    fixture's mac-source zone (device 1), outside every scanned root."""
    home = w.root / "fakehome" / f"cc-{tag}"
    home.mkdir(parents=True)
    recovery = w.root / f"recovered-from-cc-{tag}"
    twin = make_unpushed(w.root / "mac-source", f"twin-{tag}")
    copy = recovery / "Workspace" / "gone"
    copy.parent.mkdir(parents=True)
    shutil.copytree(twin, copy, symlinks=True)
    build(copy, twin)
    write_rescue_manifest(recovery, "Workspace/gone")
    row = sweep_row(str(twin))
    row[0] = str(home / "Workspace" / "gone")
    sweep = w.root / f"cc-vanished-{tag}.tsv"
    sweep.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(row) + "\n")
    return mk_ctx(w, sweep=sweep, remote_held=None, home=str(home), recovery_root=recovery, **over)


def st_group_custody_copies(s: Suite, w: World) -> None:
    s.group("C1-C5 copies must be standalone: no link, commondir or borrowed object may lead back to the Mac")
    plain = Path(w.repos["plain"])

    def tree_files(copy: Path) -> None:
        copy.mkdir()
        for name in ("tracked.txt", "second.txt", "bin.dat"):
            shutil.copy2(plain / name, copy / name)

    def manual_case(tag: str, build: Callable[[Path], None]) -> tuple[Result, str, set[str]]:
        root, manual = custody_manual_root(w, tag)
        build(manual / "plain")
        rehash_manual(manual, "plain")
        return custody_manual_verdict(w, root)

    res, text, _codes = manual_case("ok", lambda copy: shutil.copytree(plain, copy, symlinks=True))
    s.expect("baseline: an honest manual copy of plain covers its bundle component", res.status == PASS, text)

    def c1(copy: Path) -> None:
        tree_files(copy)
        os.symlink(plain / ".git", copy / ".git")

    res, text, codes = manual_case("c1", c1)
    s.expect(
        "C1: a manual copy whose .git is a symlink into the Mac does not cover",
        res.status == FAIL and codes == {"manual-mismatch"} and ".git is a symlink" in text,
        text,
    )

    def c2(copy: Path) -> None:
        tree_files(copy)
        (copy / ".git").mkdir()
        for name in ("HEAD", "index"):
            shutil.copy2(plain / ".git" / name, copy / ".git" / name)
        (copy / ".git" / "commondir").write_text(f"{plain / '.git'}\n")

    res, text, codes = manual_case("c2", c2)
    s.expect(
        "C2: a manual copy whose .git/commondir names the Mac repository does not cover",
        res.status == FAIL and "manual-mismatch" in codes and "commondir" in text,
        text,
    )

    def c3(copy: Path) -> None:
        shutil.copytree(plain, copy, symlinks=True)
        for obj in [p for p in (copy / ".git" / "objects").rglob("*") if p.is_file() and not p.is_symlink()]:
            target = plain / obj.relative_to(copy)
            obj.unlink()
            os.symlink(target, obj)

    res, text, codes = manual_case("c3", c3)
    s.expect(
        "C3: a manual copy whose loose objects and packs are symlinks into the Mac does not cover",
        res.status == FAIL and codes == {"manual-mismatch"} and "is a symlink" in text,
        text,
    )

    def alt(copy: Path) -> None:
        shutil.copytree(plain, copy, symlinks=True)
        (copy / ".git" / "objects" / "info").mkdir(parents=True, exist_ok=True)
        (copy / ".git" / "objects" / "info" / "ALTERNATES").write_text(f"{plain / '.git' / 'objects'}\n")

    res, text, codes = manual_case("alt", alt)
    s.expect(
        "a manual copy that borrows objects through a case-variant ALTERNATES does not cover",
        res.status == FAIL and "manual-mismatch" in codes and "borrows objects via alternates" in text,
        text,
    )
    root, manual = custody_manual_root(w, "med")
    shutil.copytree(plain, manual / "plain", symlinks=True)
    rehash_manual(manual, "plain")
    res, text, _codes = custody_manual_verdict(w, root, media_of=internal_media)
    s.expect(
        "H2a: an honest manual copy that sits on an internal volume does not cover",
        res.status == FAIL and "not off the Mac" in text,
        text,
    )

    res = check_git_preserved(custody_recovery_ctx(w, "ok", lambda copy, twin: None))
    s.expect("baseline: an honest recovered tree for a vanished row is accepted", res.status == PASS, res.detail)

    def c4(copy: Path, twin: Path) -> None:
        shutil.rmtree(copy / ".git")
        (copy / ".git").mkdir()
        for name in ("HEAD", "index"):
            shutil.copy2(twin / ".git" / name, copy / ".git" / name)
        (copy / ".git" / "commondir").write_text(f"{twin / '.git'}\n")

    res = check_git_preserved(custody_recovery_ctx(w, "c4", c4))
    s.expect(
        "C4: a recovered tree whose .git/commondir points at a live Mac repository is not accepted",
        res.status == FAIL and "row-vanished" in {p.code for p in res.problems} and "commondir" in str(res.problems),
        res.detail,
    )

    def c5(copy: Path, twin: Path) -> None:
        for obj in [p for p in (copy / ".git" / "objects").rglob("*") if p.is_file()]:
            target = twin / obj.relative_to(copy)
            obj.unlink()
            os.symlink(target, obj)

    res = check_git_preserved(custody_recovery_ctx(w, "c5", c5))
    s.expect(
        "C5: a recovered tree whose loose objects are symlinks into the Mac is not accepted",
        res.status == FAIL and "is a symlink" in str(res.problems),
        res.detail,
    )
    ctx = custody_recovery_ctx(w, "med", lambda copy, twin: None)
    recovery = os.path.realpath(str(ctx.recovery_root))
    plain_device, plain_media = fixture_devices(w), fixture_media(w)

    def own_device(path: str) -> int:  # the recovery root gets a device of its own, different from $HOME's
        return 5 if os.path.realpath(path).startswith(recovery) else plain_device(path)

    def own_media(path: str) -> Media:  # ... and sits on an internal volume
        return internal_media(path) if own_device(path) == 5 else plain_media(path)

    res = check_git_preserved(dataclasses.replace(ctx, device_of=own_device, media_of=own_media))
    s.expect(
        "H2a: a recovered tree on an internal volume is no custody",
        res.status == FAIL and "not custody" in str(res.problems),
        res.detail,
    )


def st_group_custody_external(s: Suite, w: World) -> None:
    s.group("X1-X3 external scan: commondir in any git dir, every spelling of alternates, core.worktree")
    vols = make_vols(w)
    found = [name for name in sorted(os.listdir(vols)) if not os.path.islink(vols / name)]  # every mounted volume
    ctx = mk_ctx(w, externals=found, volumes_root=vols)
    safe_git = Path(w.repos["safe"]) / ".git"
    s.expect(
        "baseline: the clean fixture volumes PASS",
        check_no_external_dependency(ctx).status == PASS,
        check_no_external_dependency(ctx).detail,
    )

    def only(res: Result, entry: Path) -> bool:
        return res.status == FAIL and blame(res).get(str(entry)) == {"mac-dependency"}

    wt = vols / "VolB" / "x1-wt"
    (wt / ".git").mkdir(parents=True)
    for name in ("HEAD", "index"):
        shutil.copy2(safe_git / name, wt / ".git" / name)
    (wt / ".git" / "commondir").write_text(f"{safe_git}\n")
    res = check_no_external_dependency(ctx)
    s.expect("X1: a .git directory whose commondir names the Mac repository FAILs", only(res, wt / ".git" / "commondir"), res.detail)
    (wt / ".git" / "commondir").write_text("..\n")
    s.expect(
        "negative control: a commondir that stays inside the volume PASSes",
        check_no_external_dependency(ctx).status == PASS,
        check_no_external_dependency(ctx).detail,
    )
    shutil.rmtree(wt)

    alt = vols / "VolB" / "x2-alt"
    fx(None, "clone", "-q", "--shared", w.repos["safe"], str(alt))
    info = alt / ".git" / "objects" / "info"
    (info / "alternates").rename(info / "ALTERNATES")
    res = check_no_external_dependency(ctx)
    spelled = next((p for p in info.iterdir() if p.name.lower() == "alternates"), info / "ALTERNATES")
    s.expect("X2: a case-variant objects/info/ALTERNATES that borrows from the Mac FAILs", only(res, spelled), res.detail)
    shutil.rmtree(alt)

    bare = vols / "VolB" / "x3-site.git"
    tree = w.root / "mac-source" / "x3-site"  # fixture device 1: the Mac, outside every scanned root
    tree.mkdir(parents=True)
    fx(None, "init", "-q", "--bare", "--template=", str(bare))
    fx(None, "--git-dir", str(bare), "config", "core.bare", "false")
    fx(None, "--git-dir", str(bare), "config", "core.worktree", str(tree))
    res = check_no_external_dependency(ctx)
    s.expect(
        "X3: a repository on the volume whose core.worktree is a Mac directory FAILs",
        only(res, bare / "config") and "worktree points at" in res.detail,
        res.detail,
    )
    inside = vols / "VolB" / "x3-tree"
    inside.mkdir()
    fx(None, "--git-dir", str(bare), "config", "core.worktree", str(inside))
    s.expect(
        "negative control: core.worktree inside the volume PASSes",
        check_no_external_dependency(ctx).status == PASS,
        check_no_external_dependency(ctx).detail,
    )
    shutil.rmtree(bare)
    shutil.rmtree(inside)
    stray = vols / "VolB" / "x-notes"
    put(stray / "config", f"worktree = {safe_git}\n")
    put(stray / "commondir", f"{safe_git}\n")
    s.expect(
        "negative control: files named config or commondir outside any git dir are not pointers",
        check_no_external_dependency(ctx).status == PASS,
        check_no_external_dependency(ctx).detail,
    )
    shutil.rmtree(stray)
    res = check_no_external_dependency(dataclasses.replace(ctx, media_of=internal_media))
    s.expect(
        "H2a: every explicitly listed volume that is internal media is refused as not-external",
        res.status == FAIL and {p.code for p in res.problems} == {"not-external"},
        res.detail,
    )


def st_group_custody_waivers(s: Suite, w: World) -> None:
    s.group("W1 W2 W3 waivers: evidence tokens, a checkout moved to the Trash, the exposure of a proof-less row")
    row = vanished_row(w)
    gone = row[0]
    sweep = w.root / "cw-sweep.tsv"
    sweep.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(row) + "\n")
    wfile = w.root / "cw-waivers.tsv"

    def verdict(evidence_text: str) -> Result:
        evidence = w.root / "cw-evidence.md"
        evidence.write_text(evidence_text)
        wfile.write_text(WAIVER_HEADER + "\t".join(waiver_row(gone, evidence)) + "\n")
        return check_git_preserved(mk_ctx(w, sweep=sweep, remote_held=None, waivers=wfile))

    s.expect(
        "baseline: evidence that names the path as a whole token waives it",
        verdict(f"remote holds the work of {gone}.\n").status == PASS,
    )
    for label, text in (
        ("only <path>-v2", f"remote verified for {gone}-v2 only\n"),
        ("only <path>/sub", f"{gone}/sub is held elsewhere\n"),
        ("a longer path that ends with it", f"/mnt/old{gone}\n"),
    ):
        res = verdict(text)
        s.expect(
            f"W1: evidence naming {label} does not bind a waiver for <path>",
            res.status == FAIL and not res.waived and "never mentions" in str(res.problems),
            str(res.problems),
        )

    home = w.root / "fakehome" / "cw2"
    trash_repo = make_repo(home / ".Trash", "proj", remote=False)
    moved = [str(home / "Workspace" / "proj"), "repo", "main", "NONE", "0", "1", "0", "0"]
    sweep2 = w.root / "cw2-sweep.tsv"
    sweep2.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(moved) + "\n")
    evidence2 = w.root / "cw2-evidence.md"
    evidence2.write_text(f"{moved[0]} copied elsewhere by the owner\n")
    wfile.write_text(WAIVER_HEADER + "\t".join(waiver_row(moved[0], evidence2, kind="copy-elsewhere")) + "\n")
    ctx2 = mk_ctx(
        w, sweep=sweep2, remote_held=None, waivers=wfile, home=str(home), discovery_roots=[], discovery_strays=True
    )
    res = check_git_preserved(ctx2)
    s.expect(
        "W2: a dirty-or-unpushed checkout moved into ~/.Trash is not 'vanished': its waiver is refused",
        res.status == FAIL and not res.waived and "moved, not removed" in str(res.problems) and trash_repo.exists(),
        str(res.problems),
    )
    shutil.rmtree(home / ".Trash")
    res = check_git_preserved(ctx2)
    s.expect(
        "negative control: with nothing of that name in the Trash the same waiver PASSes",
        res.status == PASS and len(res.waived) == 1,
        res.detail,
    )

    partial = [str(w.root / "work" / "partial-gone"), "repo", "main", "git@example.invalid:o/r.git", "0", "0", "0", "1"]
    sweep3 = w.root / "cw3-sweep.tsv"
    sweep3.write_text("\t".join(SWEEP_COLS) + "\n" + "\t".join(partial) + "\n")
    held = w.root / "cw3" / "remote-held.tsv"
    held.parent.mkdir(exist_ok=True)
    held.write_text(f"path\tverdict\n{partial[0]}\tPARTIAL\n#END rows=1\t#END\n")  # §3: a complete proof file
    evidence3 = w.root / "cw3-evidence.md"
    evidence3.write_text(f"{partial[0]}\n")
    wfile.write_text(WAIVER_HEADER + "\t".join(waiver_row(partial[0], evidence3)) + "\n")
    res = check_git_preserved(mk_ctx(w, sweep=sweep3, remote_held=held, waivers=wfile))
    s.expect(
        "W3: a waiver over a vanished remote-not-proven row carries that exposure (so main() prints its EXPOSED line)",
        res.status == PASS and len(res.waived) == 1 and "remote-not-proven" in res.waived[0].exposure,
        f"{res.detail} | {res.waived}",
    )


def custody_nongit_case(w: World, tag: str, stamp: str = "20261021T120000Z") -> tuple[Path, Path, Ctx]:
    """A non-git run, its live source (last modified an hour before the run) and the items file that names it."""
    run = w.root / f"cng-{tag}" / f"run-{stamp}-5"
    src = w.root / "nongit-src" / f"cng-{tag}"
    put(run / "data" / "x.txt", "x\n")
    (run / "MANIFEST.sha256").write_text(shasum_line(run / "data/x.txt", "data/x.txt"))
    (run / "RESULT.txt").write_text("mode=apply\nRESULT: PASS\n")
    put_source(src / "x.txt", "x\n", run)
    items = w.root / f"cng-{tag}-items.tsv"
    items.write_text(f"d\t{src}\tdata\n")
    return run, src, mk_ctx(w, nongit_runs=[run], nongit_items=[items])


def st_group_custody_nongit(s: Suite, w: World) -> None:
    s.group("N1-N4 nongit-homed: unreadable sources, EXCLUDED.tsv, a future run stamp, RESULT.txt spellings")
    run, src, ctx = custody_nongit_case(w, "base")
    s.expect("baseline: a run that matches its source PASSes", check_nongit_homed(ctx).status == PASS, check_nongit_homed(ctx).detail)

    put(src / "private" / "thesis.docx", "never homed\n")
    res = check_nongit_homed(ctx)
    s.expect("negative control: a readable un-homed file FAILs", res.status == FAIL and "never homed" in res.detail, res.detail)
    os.chmod(src / "private", 0)
    try:
        res = check_nongit_homed(ctx)
    finally:
        os.chmod(src / "private", 0o755)
    s.expect(
        "N1: the same file under a sub-directory that cannot be read is not skipped silently",
        res.status == FAIL and "cannot be read" in res.detail,
        res.detail,
    )
    shutil.rmtree(src / "private")

    put(src / "taxes-2025.pdf", "irreplaceable, never homed\n")
    put(src / "photos" / "img1.jpg", "never homed\n")
    (run / "EXCLUDED.tsv").write_text(
        "kind\tsource_path\tbytes\treason\n"
        f"dataless\t{src / 'taxes-2025.pdf'}\t27\tplaceholder\n"
        f"credential\t{src / 'photos'}\t0\tdir\n"
    )
    res = check_nongit_homed(ctx)
    s.expect(
        "N2: readable files listed in the run's own EXCLUDED.tsv as dataless / credential are still un-homed",
        res.status == FAIL and "EXCLUDED.tsv row" in res.detail and "never homed" in res.detail,
        res.detail,
    )
    (run / "EXCLUDED.tsv").unlink()
    (src / "taxes-2025.pdf").unlink()
    shutil.rmtree(src / "photos")
    s.expect("negative control: with them gone the run PASSes again", check_nongit_homed(ctx).status == PASS)

    frun, fsrc, fctx = custody_nongit_case(w, "future", stamp="29990101T000000Z")
    put(fsrc / "x.txt", "y\n")  # the same size, modified now: a future stamp used to switch the mtime compare off
    res = check_nongit_homed(fctx)
    s.expect(
        "N3: a run directory stamped in the future FAILs, so a same-size edit cannot hide behind it",
        res.status == FAIL and "in the future" in res.detail,
        res.detail,
    )
    for text in (
        "PASS\nresult: FAIL\n",
        "PASS\nResult: FAIL\n",
        "PASS\nERROR: 3 files not copied\n",
        "PASS\nverdict=FAIL\n",
        "PASS\nFAILURE: copy aborted\n",
        "PASS\nproblems=2\n",
        "mode=apply\nerrors=3\nRESULT: PASS\n",
        "mode=apply\nRESULT: PASS\nRESULT: pass\n",
    ):
        (run / "RESULT.txt").write_text(text)
        s.expect(f"N4: RESULT.txt {text!r} FAILs", check_nongit_homed(ctx).status == FAIL)
    (run / "RESULT.txt").write_text(
        "mode=apply\nfiles=1\nerrors=0\ndrift=0\nmissing=0\nmismatch=0\n"
        "excluded[credential-file]=/x/error.log bytes=3 failure.json\nitem[d]=files=1 errors=0\nRESULT: PASS\n"
    )
    s.expect(
        "negative control: zero failure counters and names that merely contain 'error' do not fail a PASS",
        check_nongit_homed(ctx).status == PASS,
        check_nongit_homed(ctx).detail,
    )

    # the same checks against the REAL homing tool's output, so the kinds and the RESULT.txt shape are its own
    tool = Path(__file__).with_name("nongit_homing.py")
    sqlite = shutil.which("sqlite3") or "/usr/bin/sqlite3"
    if not tool.is_file() or not os.path.exists(sqlite):
        s.expect("fixture: the real homing tool and sqlite3 are present", False, f"{tool} {sqlite}")
        return
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    real_run = w.root / "cng-real" / f"run-{stamp}-5"
    real_run.parent.mkdir()
    real_src = w.root / "nongit-src" / "cng-real"
    put_source(real_src / "a.txt", "a\n", real_run)
    put_source(real_src / "error.log", "not a failure\n", real_run)
    put_source(real_src / ".claude.json", "{}\n", real_run)
    put_source(real_src / ".ssh" / "id_rsa", "key\n", real_run)
    os.mkfifo(real_src / "pipe")
    real_items = w.root / "cng-real-items.tsv"
    real_items.write_text(f"real\t{real_src}\tdata\n")
    made = subprocess.run(
        [sys.executable, "-I", str(tool), "apply", str(real_run), str(real_items), "--home", w.home, "--sqlite", sqlite],
        check=False,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )
    s.expect("fixture: the real homing tool ran", made.returncode == 0, made.stdout[-300:] + made.stderr[-300:])
    kinds = set(excluded_rows(real_run).values())
    s.expect(
        "the real tool writes the EXCLUDED.tsv kinds the predicate verifies",
        {"credential-file", "credential-dir", "special-file"} <= kinds,
        str(kinds),
    )
    rctx = mk_ctx(w, nongit_runs=[real_run], nongit_items=[real_items])
    res = check_nongit_homed(rctx)
    s.expect("the real tool's own run PASSes (names with 'error', failure counters at zero, real kinds)", res.status == PASS, res.detail)
    with (real_run / "EXCLUDED.tsv").open("a") as handle:
        handle.write(f"credential-file\t{real_src / 'a.txt'}\t2\tclaimed\n")
    res = check_nongit_homed(rctx)
    s.expect(
        "a readable file added to the real run's EXCLUDED.tsv as a credential is still un-homed",
        res.status == FAIL and "EXCLUDED.tsv row" in res.detail,
        res.detail,
    )


def st_group_custody_time(s: Suite, w: World) -> None:
    s.group("T1 backblaze-offsite and INT-7 the verifier's verdict")
    now = datetime.now(UTC)
    run = w.root / "ctime" / f"run-{now.strftime('%Y%m%dT%H%M%SZ')}-1"
    run.mkdir(parents=True)
    (run / "RESULT.txt").write_text("RESULT: PASS\n")
    att = w.root / "ctime-attest.txt"
    ctx = mk_ctx(w, preserve_root=w.root / "ctime-none", nongit_runs=[run], backblaze_attestation=att)

    def verdict(text: str, written_ago: float = 0.0) -> Result:
        att.write_text(text)
        stamp = time.time() - written_ago
        os.utime(att, (stamp, stamp))
        return check_backblaze(ctx)

    res = verdict(f"upload-complete: yes {now.strftime('%Y-%m-%d')}\n", written_ago=6 * 3600)
    s.expect(
        "T1: a bare-date attestation written hours before a run made later the same day does not cover it",
        res.status == UNPROVEN and "predates" in res.detail,
        res.detail,
    )
    res = verdict(f"upload-complete: yes {now.strftime('%Y-%m-%d')}\n")
    s.expect(
        "T1: a bare date counts from 00:00:00 UTC, so even a freshly written one cannot vouch for today's run",
        res.status == UNPROVEN and "00:00:00" in res.detail,
        res.detail,
    )
    res = verdict(f"upload-complete: yes {(now - timedelta(minutes=1)).isoformat()}\n")
    s.expect("an attestation timed before the run is UNPROVEN", res.status == UNPROVEN and "predates" in res.detail)
    res = verdict(f"upload-complete: yes {datetime.now(UTC).isoformat()}\n", written_ago=6 * 3600)
    s.expect(
        "T1: an attestation file last written hours before the run cannot attest it",
        res.status == UNPROVEN and "last written before" in res.detail,
        res.detail,
    )
    res = verdict(f"upload-complete: yes {datetime.now(UTC).isoformat()}\n")
    s.expect("negative control: a full timestamp written after the run PASSes", res.status == PASS, res.detail)

    base, run0 = clone_run(w, "int7-base")
    s.expect(
        "baseline: the verifier-passed fixture run PASSes",
        check_git_preserved(mk_ctx(w, preserve_root=base)).status == PASS,
        check_git_preserved(mk_ctx(w, preserve_root=base)).detail,
    )
    honest = (run0 / "RESULT.txt").read_text()
    other = "run-20200101T000000Z"
    cases = {
        "no verifier RESULT.txt": (None, "no verify-preserve RESULT.txt"),
        "a verifier verdict of FAIL": (honest.replace("PASS", "FAIL", 1), "not PASS"),
        "an empty RESULT.txt": ("", "not PASS"),
        "a PASS copied from another run": (honest.replace(run0.name, other), "not this run"),
        "a PASS with no run= line": ("PASS\nWAIVERS: 0\n", "not bound to any run"),
        "a verified_at far in the future": (
            re.sub(r"verified_at=\S+", "verified_at=2999-01-01T00:00:00Z", honest),
            "in the future",
        ),
        "a verified_at before the run began": (
            re.sub(r"verified_at=\S+", "verified_at=2001-01-01T00:00:00Z", honest),
            "before the run began",
        ),
        # the verifier now writes the pin itself: replace it (a second, appended line would never be read)
        "a manifest_sha256 that no longer matches": (
            re.sub(r"manifest_sha256=\S+", "manifest_sha256=" + "0" * 64, honest)
            if "manifest_sha256=" in honest
            else honest + "manifest_sha256=" + "0" * 64 + "\n",
            "manifest_sha256",
        ),
    }
    for index, (label, (text, needle)) in enumerate(cases.items()):
        dest, bad = clone_run(w, f"int7-case-{index}")
        if text is None:
            (bad / "RESULT.txt").unlink(missing_ok=True)
        else:
            (bad / "RESULT.txt").write_text(text)
        res = check_git_preserved(mk_ctx(w, preserve_root=dest))
        s.expect(
            f"INT-7: a run with {label} does not count",
            res.status == FAIL and "no usable source" in res.detail and needle in res.detail,
            res.detail,
        )
    dest, bad = clone_run(w, "int7-pin")
    (bad / "RESULT.txt").write_text(honest + f"manifest_sha256={sha256_file(bad / 'MANIFEST.tsv')}\n")
    s.expect(
        "negative control: a manifest_sha256 that matches the MANIFEST.tsv is accepted",
        check_git_preserved(mk_ctx(w, preserve_root=dest)).status == PASS,
        check_git_preserved(mk_ctx(w, preserve_root=dest)).detail,
    )


def st_group_custody_e2e(s: Suite, w: World, args: argparse.Namespace) -> None:
    global SELFTEST_DEVICES, SELFTEST_MEDIA
    s.group("custody through main(): the cases that used to print READY")
    saved = SELFTEST_DEVICES, SELFTEST_MEDIA
    try:
        sa = spare_world(w, "ce2e-a", args)
        SELFTEST_DEVICES, SELFTEST_MEDIA = fixture_devices(sa), fixture_media(sa)
        att = prepare_e2e(sa)
        os.utime(sa.sweep, None)
        base_argv = e2e_argv(sa, att)

        def run_main(root: Path | None = None, *extra: str) -> tuple[int, list[str]]:
            argv = list(base_argv)
            if root is not None:
                argv[argv.index("--preserve-root") + 1] = str(root)
            os.utime(sa.sweep, None)
            return cli([*argv, *extra], os.path.isdir)

        code, lines = run_main()
        s.expect("baseline: the covered fixture is READY, exit 0", code == 0 and lines[-1] == "READY", f"{code} {lines[-1]}")

        plain = Path(sa.repos["plain"])
        root, manual = custody_manual_root(sa, "e2e-c1")
        copy = manual / "plain"
        copy.mkdir()
        for name in ("tracked.txt", "second.txt", "bin.dat"):
            shutil.copy2(plain / name, copy / name)
        os.symlink(plain / ".git", copy / ".git")
        rehash_manual(manual, "plain")
        code, lines = run_main(root)
        s.expect(
            "C1: main() with a manual copy whose .git links into the Mac is NOT-READY, exit 1",
            code == 1 and lines[-1] == "NOT-READY" and any(ln.startswith("FAIL git-preserved") for ln in lines),
            f"{code} {lines[-1]}",
        )
        (copy / ".git").unlink()
        shutil.rmtree(copy)
        shutil.copytree(plain, copy, symlinks=True)
        rehash_manual(manual, "plain")
        code, lines = run_main(root)
        s.expect(
            "negative control: an honest manual copy of the same repository is READY, exit 0",
            code == 0 and lines[-1] == "READY",
            f"{code} {lines[-1]}",
        )

        dest, bad = clone_run(sa, "no-verifier")
        (bad / "RESULT.txt").unlink(missing_ok=True)
        code, lines = run_main(dest)
        s.expect(
            "INT-7: main() over a run the verifier never passed is NOT-READY, exit 1",
            code == 1 and lines[-1] == "NOT-READY" and any(ln.startswith("FAIL git-preserved") for ln in lines),
            f"{code} {lines[-1]}",
        )

        sb = spare_world(w, "ce2e-b", args)
        SELFTEST_DEVICES, SELFTEST_MEDIA = fixture_devices(sb), fixture_media(sb)
        att_b = prepare_e2e(sb)
        disp = Path(sb.repos["disp"])
        commit_file(disp, "local.txt", "only copy\n", "local only")
        put(disp / "tracked.txt", "one\nedited\n")
        write_sweep(sb.sweep, swept_checkouts(sb))  # an honest sweep: the disposable row now has unpushed work
        dest, run = clone_run(sb, "nodisp")
        for kind, slug in (
            ("bundle", slugify(os.path.realpath(str(disp) + "/.git"), sb.home)),
            ("tracked-patch", slugify(str(disp), sb.home)),
            ("untracked-tar", slugify(str(disp), sb.home)),
        ):
            drop_item(run, kind, slug)
        dfile = sb.root / "my-disposals.tsv"
        named = sb.root / "disposal-named.md"
        named.write_text(f"{disp} is scratch; the owner signs it away\n")
        unnamed = sb.root / "disposal-unnamed.md"
        unnamed.write_text("a note that names no checkout at all\n")
        future = sb.root / "disposal-future.md"
        future.write_text(f"{disp}\n")
        os.utime(future, (time.time() + 7200, time.time() + 7200))

        def disposal(signer: str, evidence: Path) -> None:
            dfile.write_text(
                "\t".join(DISPOSAL_COLS)
                + f"\n{disp}\tscratch\t{signer}\t{evidence}\t{sha256_file(evidence)}\n"
            )

        b_argv = e2e_argv(sb, att_b)
        b_argv[b_argv.index("--preserve-root") + 1] = str(dest)

        def run_b() -> tuple[int, list[str]]:
            os.utime(sb.sweep, None)
            return cli([*b_argv, "--disposals", str(dfile)], os.path.isdir)

        disposal("anyone-at-all", named)
        code, lines = run_b()
        s.expect(
            "D1: main() with a disposal signed by a name on no allow-list is NOT-READY, exit 1, and waives nothing",
            code == 1 and lines[-1] == "NOT-READY" and not any(ln.startswith("WAIVED") for ln in lines),
            f"{code} {lines[-1]}",
        )
        for label, signer, evidence, needle in (
            ("a signer who is on no allow-list", "anyone-at-all", named, "allow-list"),
            ("the sweep itself as its evidence", "conductor", sb.sweep, "artifact under judgment"),
            ("evidence that never names the checkout", "conductor", unnamed, "never mentions"),
            ("evidence dated in the future", "conductor", future, "future"),
        ):
            disposal(signer, evidence)
            res = check_git_preserved(mk_ctx(sb, preserve_root=dest, disposals=dfile))
            s.expect(
                f"D1: a disposal signed with {label} is disposal-invalid and discharges nothing",
                res.status == FAIL and not res.waived and needle in str([p for p in res.problems if "disposal" in p.code]),
                str(res.problems),
            )
        disposal("conductor", named)
        code, lines = run_b()
        s.expect(
            "D1: a disposal with an allow-listed signer and evidence naming the checkout is READY (1 waiver), exit 0",
            code == 0 and lines[-1] == "READY (1 waiver)",
            f"{code} {lines[-1]}",
        )
        s.expect(
            "D1: the disposal is listed as a WAIVED line of kind disposal and on its own EXPOSED line",
            any(ln.startswith(f"WAIVED git-preserved {disp} disposal: scratch") and "kind=disposal" in ln for ln in lines)
            and any(
                ln.startswith(f"EXPOSED git-preserved {disp} waived with data exposure [")
                and ln.endswith("by conductor as disposal")
                for ln in lines
            ),
            "\n".join(lines),
        )
    finally:
        SELFTEST_DEVICES, SELFTEST_MEDIA = saved


if __name__ == "__main__":
    sys.exit(main())
