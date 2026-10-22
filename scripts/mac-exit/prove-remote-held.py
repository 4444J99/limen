#!/usr/bin/env python3
"""Decide, per repository, whether every piece of local git work is already held by a remote.

WHY: the earlier local-only sweep was wrong three ways. It looked only at a remote named `origin`; it counted
squash-merged branches as unpushed; and it repeated repo-wide counts on every worktree row. Deleting a Mac's copy
needs POSITIVE evidence against FRESH remote state, so this tool asks every remote what it holds right now
(`git ls-remote`, never `fetch`) and proves each local tip one of three ways:

  PROVEN-EXACT      the tip equals the SHA of a freshly listed remote ref (any ref name, any remote).
  PROVEN-ANCESTOR   the tip is an ancestor of a freshly listed SHA of a GitHub remote whose object exists locally
                    (GitHub is known to hold the whole history behind what it advertises; any other host could be a
                    shallow repository, so off GitHub only an exact match proves). When the local tracking refs have
                    fallen behind a remote that moved forward, GitHub's compare endpoint answers the same question
                    for the exact tip against the remote branch (evidence `github-compare: ...`); a rewound or
                    force-pushed remote answers `behind`/`diverged` and proves nothing.
  PROVEN-MERGED-PR  a pull request in the remote's own GitHub repository, merged, whose head SHA equals the tip and
                    whose merge commit is on the default branch (how squash-merged work is proven).
  Both GitHub proofs run in the helper gh-merged-pr-proof.sh; the tool never builds gh arguments. An annotated tag
  is held only when the remote has the tag OBJECT: its commit being on a branch does not hold the tag message.

Anything else is UNPROVEN with a reason. A repository is PROVEN-ALL only if
  - every ref tip (branches, tags, other refs such as notes and replace refs, detached-HEAD worktrees) is proven;
  - no commit is reachable only from a reflog (any worktree's) or a remote-tracking ref unless GitHub holds it too
    (UNPROVEN-REFLOG-ONLY: a deleted branch's work, an abandoned detached commit, a stale `origin/x`);
  - every worktree is clean: no tracked changes, no untracked non-ignored files, and no file edited behind
    skip-worktree / assume-unchanged (UNPROVEN-HIDDEN-EDITS);
  - there is no stash entry (refs/stash counts even without its reflog, and in a bare repository);
  - at least one NETWORK remote answered a fresh listing (GitHub lookups alone never stand in for it);
  - every submodule repository under <git dir>/modules and every objects/info/alternates lender is itself
    PROVEN-ALL (UNPROVEN-SUBMODULE / UNPROVEN-ALTERNATES), and the local git-lfs store is empty (UNPROVEN-LFS).
Remotes whose URL is a filesystem path, or an address on this machine or its LAN (loopback, RFC1918, link-local,
.local names), never count; a single-label host may be an ssh-config alias and is unsupported. A failed or
unauthenticated listing is UNPROVEN-NETWORK, never PROVEN. Every git listing that fails (refs, worktrees, remotes,
stashes, status, the reflog walk) is UNPROVEN-ERROR, never an empty listing.

Not covered, by design: unreferenced objects no reflog names (never reachable, `git fsck` territory) and objects behind
an advertised SHA on a non-GitHub remote (recorded in the `notes` column). `head_held` in entries.tsv is about one
checkout's own HEAD; the checkout that holds .git is `no` unless the whole repository is PROVEN-ALL.

Read-only by construction: every git call runs as `GIT_OPTIONAL_LOCKS=0 git -c core.fsmonitor=false ...` with
GIT_NO_LAZY_FETCH, GIT_NO_REPLACE_OBJECTS and an empty graft file set; the network is `ls-remote` and the helper's
GETs only. Every result file ends with a `#END rows=N` row; a file without it was cut short.

  python3 -I prove-remote-held.py --tsv git.tsv --out-dir OUT [--compare real.tsv] [--deadline 1380]
  python3 -I prove-remote-held.py --self-test

Exit codes: 0 = a complete run and every repository PROVEN-ALL with an empty `gaps` column; 1 = a complete run, some
repository not PROVEN-ALL, or PROVEN-ALL but carrying a documented gap (so a --trust-remote-under run never exits 0);
64 = usage error (nothing is created); 70 = internal error or an incomplete run (--limit dropped entries, a deadline
left repositories unexamined, an exception): the result files of such a run are not to be used as a full proof.
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import dataclasses
import io
import ipaddress
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
from collections import Counter
from collections.abc import Callable, Mapping
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NoReturn

# SHA_RE: the 40-hex SHA-1 id the GitHub helper speaks (GitHub has no SHA-256 repositories).
# OID_RE: a git object id, SHA-1 (40 hex) or SHA-256 (64 hex).
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
OID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9._-]+$")
BRANCH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")
SCP_RE = re.compile(r"^(?:[^/@:\s]+@)?[^/@:\s]+:(?!//)")
TRANSPORT_HELPER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*::")
USERINFO_RE = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.-]*)://(?P<info>[^/@\s]*)@")
SECRET_QS_RE = re.compile(r"(?i)([?&](?:token|access_token|private_token|password|passwd|key|secret)=)[^&\s]+")
EMBEDDED_IPV4_RE = re.compile(r"(?<![0-9])([0-9]{1,3})[.-]([0-9]{1,3})[.-]([0-9]{1,3})[.-]([0-9]{1,3})(?![0-9])")
NETWORK_SCHEMES = {"http", "https", "ssh", "git", "git+ssh", "ssh+git"}
LOCAL_HOST_SUFFIXES = (".local", ".localdomain", ".localhost", ".lan", ".home", ".internal", ".home.arpa")

GIT_TIMEOUT = 60
STATUS_TIMEOUT = 180
NET_TIMEOUT = 30
HELPER_TIMEOUT = 90

EXACT, ANCESTOR, MERGED_PR = "PROVEN-EXACT", "PROVEN-ANCESTOR", "PROVEN-MERGED-PR"
R_NO_REMOTE, R_LOCAL, R_UNSUPPORTED = "UNPROVEN-NO-REMOTE", "UNPROVEN-LOCAL-REMOTE", "UNPROVEN-UNSUPPORTED-REMOTE"
R_NETWORK, R_NOT_HELD, R_DIRTY = "UNPROVEN-NETWORK", "UNPROVEN-TIP-NOT-HELD", "UNPROVEN-DIRTY"
R_STASH, R_ERROR, R_TIMEOUT = "UNPROVEN-STASH", "UNPROVEN-ERROR", "UNPROVEN-TIMEOUT"
R_VANISHED, R_ORPHAN = "UNPROVEN-VANISHED", "UNPROVEN-NO-GIT-METADATA"
R_REFLOG, R_SUBMODULE, R_ALTERNATES = "UNPROVEN-REFLOG-ONLY", "UNPROVEN-SUBMODULE", "UNPROVEN-ALTERNATES"
R_LFS, R_HIDDEN = "UNPROVEN-LFS", "UNPROVEN-HIDDEN-EDITS"
R_ANNEX = "UNPROVEN-ANNEX"  # git-annex content under <git dir>/annex/objects: large local files no ref or remote lists
# Documented gaps in a proof (contract 4): the verdict can be PROVEN-ALL and still rest on an assumption. The column
# `gaps` of remote-held.tsv carries these codes; a consumer trusts a PROVEN-ALL row only when it is empty.
GAP_NONGITHUB = "NONGITHUB-HISTORY-ASSUMED"  # a SHA held by a non-GitHub remote, the history behind it assumed complete
GAP_NO_REFLOG = "NO-REFLOG"  # a non-bare repository whose reflogs cannot enumerate its abandoned commits
GAP_BARE = "BARE-NO-REFLOG"  # a bare repository keeps no reflog: its dangling commits cannot be enumerated
GAP_TRUST = "TRUST-REMOTE-UNDER"  # a remote counted as offsite only because --trust-remote-under said so (test only)
R_PER_WORKTREE = "UNPROVEN-PER-WORKTREE"  # a refs/worktree|bisect|rewritten tip of some worktree that no remote holds
R_UNREPRESENTABLE = "UNPROVEN-UNREPRESENTABLE"  # a join key that cannot be written losslessly (contract 1)
SUPERSEDED = "SUPERSEDED-BOT-BRANCH"  # reported on its own; never blocks a verdict
BRANCHES_PROVEN = (
    "BRANCHES-PROVEN"  # second, weaker verdict: branches + clean trees + no stash (tags/other refs ignored)
)
BOT_BRANCH_RE = re.compile(r"^(?:dependabot|renovate)/")
BOT_AUTHOR_RE = re.compile(r"dependabot|renovate", re.IGNORECASE)
GITHUB_COMMITTER = "GitHub <noreply@github.com>"  # committer of every commit a bot makes through the GitHub API
REASON_ORDER = [
    R_VANISHED,
    R_ORPHAN,
    R_UNREPRESENTABLE,
    R_NO_REMOTE,
    R_LOCAL,
    R_UNSUPPORTED,
    R_NETWORK,
    R_NOT_HELD,
    R_PER_WORKTREE,
    R_REFLOG,
    R_SUBMODULE,
    R_ALTERNATES,
    R_LFS,
    R_ANNEX,
    R_DIRTY,
    R_HIDDEN,
    R_STASH,
    R_ERROR,
    R_TIMEOUT,
]
MAX_SWEEP_LOOKUPS = 20  # GitHub lookups spent on reflog-only / tracking-ref-only commits per repository
MAX_BOT_COMMITS = 200  # a bot branch carrying more commits of its own than this is not treated as a stale copy
MAX_MODULE_DEPTH = 4  # submodule / alternates repositories analysed below a repository

# Test-only overlay on the child environment (value None deletes the variable). Empty in production.
ENV_OVERRIDES: dict[str, str | None] = {}
# Set by make_ctx when --trust-remote-under names a directory: only then may git speak the `file` protocol.
ALLOW_FILE_PROTOCOL = False


# ---------------------------------------------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------------------------------------------


def redact(text: str) -> str:
    """Strip credentials from anything that is written out: URL userinfo (except a bare ssh user) and secret params."""

    def _userinfo(match: re.Match[str]) -> str:
        scheme, info = match.group("scheme"), match.group("info")
        if scheme.lower() in {"ssh", "git+ssh", "ssh+git"} and ":" not in info:
            return match.group(0)
        return f"{scheme}://***@"

    return SECRET_QS_RE.sub(r"\1***", USERINFO_RE.sub(_userinfo, text))


FFFD = "\N{REPLACEMENT CHARACTER}"
LONE_SURROGATE_RE = re.compile("[\\udc80-\\udcff]")
# Characters that break a row for a TSV reader: TAB, CR and LF, plus every other boundary `str.splitlines()` honours, plus
# the lone surrogates `surrogateescape` leaves for bytes that are not UTF-8 (they cannot be encoded into the file).
KEY_UNSAFE_RE = re.compile(
    "[\\t\\r\\n\\x0b\\x0c\\x1c\\x1d\\x1e\\x85\N{LINE SEPARATOR}\N{PARAGRAPH SEPARATOR}\\udc80-\\udcff]"
)


def flat(text: str, limit: int = 160) -> str:
    """One TSV-safe line: redacted, no tabs or newlines, bounded. Free text only: never a join key (see key_cell)."""
    return LONE_SURROGATE_RE.sub(FFFD, redact(" ".join(text.split())))[:limit]


def key_cell(value: str) -> str:
    """A join-key cell (contract 1): byte-identical to the live value, never collapsed, redacted or truncated. A character
    that would break the row becomes U+FFFD, so the cell can no longer equal any live path (fail closed); the repository
    is then UNPROVEN-UNREPRESENTABLE (see unrepresentable_keys). Never mangled into a different valid path."""
    return KEY_UNSAFE_RE.sub(FFFD, value)


def paths_cell(paths: list[str]) -> str:
    """The `paths` list: `;` separates elements, so a `;` inside one becomes U+FFFD too."""
    return ";".join(key_cell(p).replace(";", FFFD) for p in paths)


def base_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_GRAFT_FILE=os.devnull,  # finding 3d: info/grafts would rewrite ancestry just like refs/replace
        GIT_NO_LAZY_FETCH="1",
        GIT_PAGER="cat",
        GIT_ALLOW_PROTOCOL="file:https:http:ssh:git" if ALLOW_FILE_PROTOCOL else "https:http:ssh:git",
    )
    for key, value in ENV_OVERRIDES.items():
        if value is None:
            env.pop(key, None)
        else:
            env[key] = value
    return env


def run(
    cmd: list[str], *, timeout: float, env: dict[str, str], cwd: str | None = None, stdin: str | None = None
) -> tuple[int, str, str]:
    """Run in its own session so a timeout can kill the whole group (an ssh grandchild would hold the pipes open)."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="surrogateescape",  # a path that is not UTF-8 must stay a distinct path, never a U+FFFD lookalike
            start_new_session=True,
        )
    except OSError as exc:
        return 127, "", f"cannot start {cmd[0]}: {exc}"
    try:
        out, err = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            out, err = "", ""
        return 124, out or "", f"timeout after {timeout:.0f}s"
    return proc.returncode, out, err


def git(
    path: str, *args: str, timeout: float = GIT_TIMEOUT, stdin: str | None = None, env: dict[str, str] | None = None
) -> tuple[int, str, str]:
    cmd = ["git", "-c", "core.fsmonitor=false", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "-C", path, *args]
    return run(cmd, timeout=timeout, env=env or base_env(), stdin=stdin)


class Throttle:
    """Minimum spacing between outward calls, so a few hundred lookups stay polite."""

    def __init__(self, interval: float) -> None:
        self.interval = interval
        self.last = 0.0
        self.lock = threading.Lock()

    def wait(self) -> None:
        """Reserve the next start slot (thread-safe), then sleep until it."""
        with self.lock:
            now = time.monotonic()
            start = max(now, self.last + self.interval)
            self.last = start
        if start > now:
            time.sleep(start - now)


# ---------------------------------------------------------------------------------------------------------------
# remote URL handling
# ---------------------------------------------------------------------------------------------------------------


def local_path_of(url: str) -> str | None:
    """The filesystem path a remote URL names, or None when it is a network/other URL."""
    if url.startswith("file://"):
        return urllib.parse.unquote(urllib.parse.urlparse(url).path)
    if "://" in url or SCP_RE.match(url):
        return None
    return url


def classify_remote(url: str, trusted: list[str]) -> str:
    """network | local | unsupported. A path is local (same machine) unless a test explicitly trusts its directory."""
    if not url or TRANSPORT_HELPER_RE.match(url):  # `ext::sh -c ...` and friends run a program, not a network fetch
        return "unsupported"
    path = local_path_of(url)
    if path is not None:
        real = os.path.realpath(path)
        if any(real == t or real.startswith(t + os.sep) for t in trusted):
            return "network"
        return "local"
    scheme = url.split("://", 1)[0].lower() if "://" in url else "ssh"
    parts = split_url(url)
    if scheme not in NETWORK_SCHEMES or parts is None:
        return "unsupported"
    return host_kind(parts[0])


def host_kind(host: str) -> str:
    """network | local | unsupported for a URL host. Finding 4a: an address on this machine or its LAN is not offsite.

    Loopback, RFC1918, link-local, CGNAT and other non-global address literals, `localhost`, and mDNS/LAN suffixes are
    local; a single-label name is probably an ssh-config alias (it may point anywhere, even at this Mac): unknown."""
    host = host.strip("[]").lower().rstrip(".")
    if not host:
        return "unsupported"
    try:
        ip: ipaddress.IPv4Address | ipaddress.IPv6Address | None = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        ip = legacy_ipv4(host)
    if ip is not None:
        return "network" if ip.is_global else "local"
    if host == "localhost" or host.endswith(LOCAL_HOST_SUFFIXES):
        return "local"
    embedded = embedded_ipv4(host)
    if embedded is not None:
        return "network" if embedded.is_global else "local"
    return "network" if "." in host else "unsupported"


def legacy_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """The address a resolver reads from a legacy IPv4 spelling (127.1, 0x7f.0.0.1, 0177.0.0.1, 2130706433), or None."""
    try:
        return ipaddress.IPv4Address(socket.inet_aton(host))
    except (OSError, ValueError):
        return None


def embedded_ipv4(host: str) -> ipaddress.IPv4Address | None:
    """An IPv4 address spelled inside a name (wildcard DNS such as 127.0.0.1.nip.io or 10-0-0-5.sslip.io), or None.
    Such a name resolves to that address, so it is only offsite when the address is."""
    match = EMBEDDED_IPV4_RE.search(host)
    if match is None:
        return None
    try:
        return ipaddress.IPv4Address(".".join(str(int(octet)) for octet in match.groups()))
    except ValueError:
        return None


def split_url(url: str) -> tuple[str, str] | None:
    """(host, path) of a network URL with scheme, userinfo, port and a trailing .git removed."""
    if "://" in url:
        rest = url.split("://", 1)[1]
        hostpart, _, path = rest.partition("/")
        host = re.sub(r":\d+$", "", hostpart.rsplit("@", 1)[-1])
    elif SCP_RE.match(url):
        hostpart, _, path = url.partition(":")
        host = hostpart.rsplit("@", 1)[-1]
    else:
        return None
    return host.lower(), path.strip("/").removesuffix(".git")


def github_slug(*urls: str) -> str | None:
    for url in urls:
        parts = split_url(url)
        if parts and parts[0] == "github.com" and SLUG_RE.match(parts[1]):
            return parts[1]
    return None


def norm_key(url: str) -> str:
    """Identity of a listing: scheme, user, host, port and path all matter (finding 4b). Only the case of a github.com
    path is folded; a second repository's listing must never answer for the first.

    The path keeps what it means: `ssh://host/x` is the ABSOLUTE path /x, while the scp-style `host:x` is relative to the
    login home (/~/x) and `host:/x` is absolute (/x). Folding them into one key let one repository's listing prove another's
    tips."""
    if "://" in url:
        scheme, rest = url.split("://", 1)
        hostpart, _, path = rest.partition("/")
        path = "/" + path
        user, _, hostport = hostpart.rpartition("@")
        port = re.search(r":(\d+)$", hostport)
        host = hostport[: port.start()] if port else hostport
        port_text = port.group(1) if port else ""
    elif SCP_RE.match(url):
        scheme, port_text = "ssh", ""
        hostpart, _, path = url.partition(":")
        path = path if path.startswith("/") else "/~/" + path
        user, _, host = hostpart.rpartition("@")
    else:
        return url
    host, path = host.lower(), path.rstrip("/").removesuffix(".git")
    if host == "github.com":
        path = path.lower()
    return f"{scheme.lower()}://{user}@{host}:{port_text}{path}"


# ---------------------------------------------------------------------------------------------------------------
# data model
# ---------------------------------------------------------------------------------------------------------------


@dataclasses.dataclass
class Fresh:
    """What a remote advertised right now (heads and tags, annotated tags also as their peeled `^{}` line)."""

    refs: dict[str, str]
    by_sha: dict[str, str]

    @property
    def shas(self) -> set[str]:
        return set(self.by_sha)


@dataclasses.dataclass
class Remote:
    name: str
    raw_url: str
    resolved_url: str
    kind: str  # network | local | unsupported
    slug: str | None
    fresh: Fresh | None = None
    error: str = ""
    trusted: bool = False  # offsite only because --trust-remote-under named the directory it lives in

    def flag(self) -> str:
        if self.kind != "network":
            return self.kind
        return "ok" if self.fresh is not None else f"net-fail: {self.error}"


@dataclasses.dataclass
class Tip:
    ref: str
    kind: str  # branch | tag | other | detached | per-worktree
    sha: str
    commit: str | None
    status: str = ""
    evidence: str = ""
    otype: str = "commit"  # commit | tag (an annotated tag object, whose sha is not its commit) | other
    via: str = ""  # the remote whose listing proved it EXACT

    @property
    def annotated(self) -> bool:
        """An annotated tag object carries a message and signature of its own: its commit being held is not enough."""
        return self.otype == "tag"

    @property
    def proven(self) -> bool:
        return self.status.startswith("PROVEN-")

    @property
    def blocking(self) -> bool:
        """Unproven and not a superseded bot branch: the tips that make a repository UNPROVEN."""
        return not self.proven and self.status != SUPERSEDED

    @property
    def name(self) -> str:
        return self.ref.removeprefix("refs/heads/") if self.kind == "branch" else self.ref


@dataclasses.dataclass
class Worktree:
    path: str
    head: str | None = None
    branch: str | None = None
    detached: bool = False
    bare: bool = False
    missing: bool = False
    dirty: int = 0
    hidden: int = 0  # files edited behind skip-worktree / assume-unchanged (invisible to `git status`)
    unborn: bool = False  # on a branch that has no commit yet
    note: str = ""


@dataclasses.dataclass
class Row:
    path: str
    kind: str
    sweep: dict[str, str]


@dataclasses.dataclass
class Group:
    key: str  # absolute common dir, or MISSING:<path> / NOMETA:<path> / ERROR:<path>
    rows: list[Row]
    error: str = ""


@dataclasses.dataclass
class RowFacts:
    row: Row
    head: str = ""
    head_status: str = ""
    dirty: int = -1
    held: str = ""  # yes | no | vanished


@dataclasses.dataclass
class RepoResult:
    repo: str
    common_dir: str
    rows: list[Row]
    remotes: list[Remote] = dataclasses.field(default_factory=list)
    tips: list[Tip] = dataclasses.field(default_factory=list)
    worktrees: list[Worktree] = dataclasses.field(default_factory=list)
    stashes: int = 0
    verdict: str = "UNPROVEN"
    branches_verdict: str = "UNPROVEN"
    reasons: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)  # limits of the proof that do not change the verdict
    gaps: set[str] = dataclasses.field(default_factory=set)  # the same limits as machine codes (GAP_*)
    scope: str = ""
    seconds: float = 0.0
    row_facts: list[RowFacts] = dataclasses.field(default_factory=list)

    @property
    def dirty_entries(self) -> int:
        return sum(max(w.dirty, 0) for w in self.worktrees)

    @property
    def first_reason(self) -> str:
        return f"{self.reasons[0][0]}: {self.reasons[0][1]}" if self.reasons else ""

    @property
    def all_reasons(self) -> str:
        return " | ".join(f"{code}: {detail}" for code, detail in self.reasons)

    @property
    def all_notes(self) -> str:
        return " | ".join(self.notes)

    @property
    def gaps_cell(self) -> str:
        return ";".join(sorted(self.gaps))

    def count(self, kind: str, status: str | None = None) -> int:
        tips = [t for t in self.tips if t.kind == kind]
        if status is None:
            return len(tips)
        if status == "UNPROVEN":
            return sum(1 for t in tips if t.blocking)
        return sum(1 for t in tips if t.status == status)


@dataclasses.dataclass
class Ctx:
    helper: str | None
    trusted: list[str]
    deadline: float
    net: Throttle
    helper_throttle: Throttle
    fresh_ok: dict[str, Fresh] = dataclasses.field(default_factory=dict)
    fresh_fail: dict[str, str] = dataclasses.field(default_factory=dict)
    pr_cache: dict[tuple[str, str], tuple[str, str]] = dataclasses.field(default_factory=dict)
    default_branch: dict[str, str] = dataclasses.field(default_factory=dict)
    log: Callable[[str], None] = lambda _msg: None
    calls: Counter[str] = dataclasses.field(default_factory=Counter)
    workers: int = 1  # concurrent GitHub lookups (the spacing between their starts is still enforced)
    lock: threading.Lock = dataclasses.field(default_factory=threading.Lock)
    visiting: set[str] = dataclasses.field(default_factory=set)  # common dirs being analysed (cycle guard)


# ---------------------------------------------------------------------------------------------------------------
# grouping by git common dir
# ---------------------------------------------------------------------------------------------------------------


def diagnose_gitfile(path: str) -> str | None:
    """Why git cannot open `path` when its `.git` is a file that does not lead to a repository (text only, read-only)."""
    dot_git = os.path.join(path, ".git")
    if not os.path.isfile(dot_git):
        return None
    try:
        text = Path(dot_git).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not text:
        return "empty .git file: not a git repository"
    first = text.splitlines()[0]
    if first.startswith("gitdir:"):
        target = first.removeprefix("gitdir:").strip()
        if not os.path.exists(target):
            return (
                f"orphaned worktree: .git points to {flat(target, 140)} which no longer exists "
                "(admin entry pruned or parent repository gone); the files here are under no git repository"
            )
    return None


def group_rows(rows: list[Row]) -> list[Group]:
    groups: dict[str, Group] = {}
    for row in rows:
        if not os.path.isdir(row.path):
            key, error = f"MISSING:{os.path.realpath(row.path)}", "path no longer exists"
        else:
            rc, out, err = git(row.path, "rev-parse", "--path-format=absolute", "--git-common-dir")
            if rc == 0 and out.strip():
                key, error = os.path.realpath(out.rstrip("\n")), ""
            elif diagnosis := diagnose_gitfile(row.path):
                key, error = (
                    f"NOMETA:{os.path.realpath(row.path)}",
                    f"{diagnosis}; git said: {flat(err or f'rev-parse rc={rc}', 100)}",
                )
            else:
                key, error = f"ERROR:{os.path.realpath(row.path)}", flat(err or f"rev-parse rc={rc}")
        groups.setdefault(key, Group(key, [], error)).rows.append(row)
    return list(groups.values())


# ---------------------------------------------------------------------------------------------------------------
# per-repository collection
# ---------------------------------------------------------------------------------------------------------------


def parse_ls_remote(out: str) -> Fresh:
    """What a remote advertised. A line that is not `<object id> TAB <refname>` (SHA-1 or SHA-256 id) raises
    ValueError: dropping it would make a remote that holds work look like one that holds nothing, or the other way
    round. An unreadable answer is no answer."""
    refs: dict[str, str] = {}
    by_sha: dict[str, str] = {}
    for line in out.split("\n"):
        if not line:
            continue
        sha, _, ref = line.partition("\t")
        if not (OID_RE.match(sha) and ref):
            raise ValueError(f"unparseable ls-remote line: {flat(line, 60)}")
        refs[ref] = sha
        by_sha.setdefault(sha, ref)
    return Fresh(refs, by_sha)


def fetch_fresh(ctx: Ctx, anchor: str, remote: Remote) -> None:
    """Fill remote.fresh from `git ls-remote --heads --tags`, or remote.error. Cached per normalized remote."""
    key = norm_key(remote.resolved_url)
    if key in ctx.fresh_ok:
        remote.fresh = ctx.fresh_ok[key]
        return
    if remote.resolved_url in ctx.fresh_fail:
        remote.error = ctx.fresh_fail[remote.resolved_url]
        return
    rc, cfg, _ = git(anchor, "config", "--get", "core.sshCommand")
    ssh = cfg.strip() if rc == 0 and cfg.strip() else os.environ.get("GIT_SSH_COMMAND", "ssh")
    env = base_env()
    env["GIT_SSH_COMMAND"] = f"{ssh} -o BatchMode=yes -o ConnectTimeout=15"
    err = ""
    for attempt in (1, 2):
        ctx.net.wait()
        ctx.calls["ls-remote"] += 1
        rc, out, err = git(anchor, "ls-remote", "--heads", "--tags", remote.name, timeout=NET_TIMEOUT, env=env)
        if rc == 0:
            try:
                remote.fresh = ctx.fresh_ok[key] = parse_ls_remote(out)
            except ValueError as exc:
                rc, err = 1, str(exc)
                break
            return
        if attempt == 1 and ("timeout" in err or "Could not resolve" in err or "Connection reset" in err):
            time.sleep(1.5)
            continue
        break
    remote.error = ctx.fresh_fail[remote.resolved_url] = flat(
        err.strip().splitlines()[-1] if err.strip() else f"rc={rc}", 90
    )


def collect_remotes(ctx: Ctx, anchor: str) -> tuple[list[Remote], str]:
    """(remotes, error). A failing `git remote` is an error, never 'repository has no remote'."""
    rc, out, err = git(anchor, "remote")
    if rc != 0:
        return [], f"remote listing failed: {flat(err or f'rc={rc}', 90)}"
    remotes = []
    for name in out.split():
        _, raw, _ = git(anchor, "config", "--get", f"remote.{name}.url")
        _, resolved, _ = git(anchor, "ls-remote", "--get-url", name)
        raw, resolved = raw.rstrip("\n"), resolved.rstrip("\n") or raw.rstrip("\n")
        kind = classify_remote(resolved, ctx.trusted)
        trusted = kind == "network" and local_path_of(resolved) is not None
        remotes.append(Remote(name, raw, resolved, kind, github_slug(resolved), trusted=trusted))
    return remotes, ""


REF_FORMAT = "%(refname)%09%(objectname)%09%(objecttype)%09%(*objectname)%09%(*objecttype)"
# Refs that belong to ONE worktree (git's per-worktree ref namespaces). A listing made from one worktree shows only that
# worktree's; the others sit in <common>/worktrees/<id>/refs/. They are collected per worktree and never as bare names.
PER_WORKTREE_PREFIXES = ("refs/worktree/", "refs/bisect/", "refs/rewritten/")


def tips_from_listing(
    anchor: str, out: str, git_dir: str | None = None, worktree: str | None = None
) -> list[Tip] | str:
    """Tips from `for-each-ref --format=REF_FORMAT` output, or the first unparseable line (never silently skipped).

    worktree=None: the shared and current-worktree refs, `refs/remotes/` and `refs/stash` left out (evidence / stash logic)
    and the per-worktree namespaces left out (collect_per_worktree_tips owns them). worktree=<realpath>: a per-worktree
    listing; every ref is then named `<full refname>@<worktree>`, so it can never collide with another worktree's."""
    prefix = [f"--git-dir={git_dir}"] if git_dir else []
    tips = []
    for line in out.split("\n"):
        if not line:
            continue
        ref, sha, otype, peeled, ptype = (line.split("\t") + [""] * 5)[:5]
        if worktree is None and ref.startswith(("refs/remotes/", "refs/stash", *PER_WORKTREE_PREFIXES)):
            continue
        if not OID_RE.match(sha) or not ref:
            return f"unparseable ref listing line: {flat(line, 100)}"
        kind = (
            "per-worktree"
            if worktree is not None
            else "branch"
            if ref.startswith("refs/heads/")
            else "tag"
            if ref.startswith("refs/tags/")
            else "other"
        )
        commit: str | None = sha if otype == "commit" else peeled if (otype == "tag" and ptype == "commit") else None
        if commit is None and otype == "tag":
            rc2, out2, _ = git(anchor, *prefix, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
            commit = out2.strip() if rc2 == 0 and OID_RE.match(out2.strip()) else None
        name = ref if worktree is None else f"{ref}@{worktree}"
        tips.append(Tip(name, kind, sha, commit, otype=otype if otype in {"commit", "tag"} else "other"))
    return tips


def collect_tips(anchor: str) -> list[Tip] | str:
    rc, out, err = git(anchor, "for-each-ref", f"--format={REF_FORMAT}")
    if rc != 0:
        return f"for-each-ref failed: {flat(err)}"
    return tips_from_listing(anchor, out)


def per_worktree_sources(common_dir: str, main_label: str) -> tuple[list[tuple[str, str]], list[str]]:
    """[(git dir, worktree realpath)] for the main worktree and every linked worktree's admin dir, plus errors.

    A linked worktree's admin dir is <common>/worktrees/<id>; its `gitdir` file names <worktree>/.git. This works for a
    worktree whose directory is gone too, which `git -C <worktree>` cannot reach."""
    sources = [(common_dir, main_label)]
    errors: list[str] = []
    root = os.path.join(common_dir, "worktrees")
    try:
        names = sorted(os.listdir(root))
    except FileNotFoundError:
        return sources, errors
    except OSError as exc:
        return sources, [f"cannot list {root}: {exc.strerror}"]
    for name in names:
        admin = os.path.join(root, name)
        if not os.path.isdir(admin):
            continue
        try:
            target = Path(admin, "gitdir").read_text(encoding="utf-8", errors="surrogateescape").rstrip("\n")
        except OSError as exc:
            errors.append(f"worktree admin dir {flat(name, 60)}: cannot read its gitdir file ({exc.strerror})")
            continue
        if not os.path.isabs(target):  # worktree.useRelativePaths
            target = os.path.join(admin, target)
        sources.append((admin, os.path.realpath(os.path.dirname(target))))
    return sources, errors


def collect_per_worktree_tips(anchor: str, common_dir: str, main_label: str) -> tuple[list[Tip], list[str]]:
    """The per-worktree refs (refs/worktree/*, refs/bisect/*, refs/rewritten/*) of EVERY worktree, the main one included.

    A for-each-ref from the anchor sees only its own worktree's, and `rev-list --all` / `--reflog` reach none of them
    (no reflog by default), so a commit that only such a ref names would otherwise read as nothing."""
    sources, errors = per_worktree_sources(common_dir, main_label)
    tips: list[Tip] = []
    for git_dir, label in sources:
        rc, out, err = git(
            anchor,
            f"--git-dir={git_dir}",
            "for-each-ref",
            f"--format={REF_FORMAT}",
            *(prefix.rstrip("/") for prefix in PER_WORKTREE_PREFIXES),
        )
        if rc != 0:
            errors.append(f"per-worktree ref listing failed for {flat(label, 80)}: {flat(err or f'rc={rc}', 90)}")
            continue
        found = tips_from_listing(anchor, out, git_dir=git_dir, worktree=label)
        if isinstance(found, str):
            errors.append(found)
        else:
            tips += found
    return tips, errors


def collect_stashes(anchor: str) -> tuple[int, list[str], list[str]]:
    """(stash entries, stash commit shas, errors). Works in a bare repository (`git stash list` does not: rc 128).

    refs/stash existing counts as a stash even when its reflog is gone and `log -g` lists nothing."""
    rc, out, err = git(anchor, "for-each-ref", "--format=%(objectname)", "refs/stash")
    if rc != 0:
        return 0, [], [f"stash ref listing failed: {flat(err or f'rc={rc}', 90)}"]
    if not out.split():
        return 0, [], []
    errors = []
    if not all(OID_RE.match(s) for s in out.split()):  # something is there; what, we cannot read: never 'no stash'
        errors.append(f"stash ref listing unparseable: {flat(out, 60)}")
    top = [s for s in out.split() if OID_RE.match(s)]
    rc, out, err = git(anchor, "log", "-g", "--format=%H", "refs/stash")
    listed = [s for s in out.split() if OID_RE.match(s)] if rc == 0 else []
    if rc == 0 and not all(OID_RE.match(s) for s in out.split()):
        errors.append(f"stash reflog listing unparseable: {flat(out, 60)}")
    if rc != 0:
        errors.append(f"stash reflog listing failed: {flat(err or f'rc={rc}', 90)}")
    return max(len(listed), 1), sorted(set(listed) | set(top)), errors


def collect_worktrees(anchor: str) -> tuple[list[Worktree], str]:
    """(worktrees, error). A failing listing is an error, never 'no worktrees': detached tips and dirt would vanish."""
    # -z: NUL-terminated fields, paths unquoted, so a path holding a newline is one path (not two garbage records)
    rc, out, err = git(anchor, "worktree", "list", "--porcelain", "-z")
    worktrees: list[Worktree] = []
    cur: Worktree | None = None
    if rc != 0:
        return [], f"worktree listing failed: {flat(err or f'rc={rc}', 90)}"
    for line in out.split("\0"):
        key, _, value = line.partition(" ")
        if key == "worktree":
            cur = Worktree(path=value)
            worktrees.append(cur)
        elif cur is None:
            continue
        elif key == "HEAD":
            cur.head = None if set(value) <= {"0"} else value  # the all-zero id of an unborn branch, any hash length
            cur.unborn = cur.head is None
        elif key == "branch":
            cur.branch = value
        elif key == "detached":
            cur.detached = True
        elif key == "bare":
            cur.bare = True
        elif key == "prunable":
            cur.missing = True
    for wt in worktrees:
        if not wt.bare and not os.path.isdir(wt.path):
            wt.missing = True
        elif not wt.bare and looks_like_gitdir(wt.path):
            # `git worktree list` of a submodule names <super>/.git/modules/<name> itself as the worktree. The real
            # checkout is where core.worktree points; status, hidden edits and the HEAD all belong to that directory.
            rc, top, _ = git(wt.path, "rev-parse", "--show-toplevel")
            if rc == 0 and top.strip():
                wt.path = top.rstrip("\n")
    return worktrees, ""


def looks_like_gitdir(path: str) -> bool:
    return os.path.isfile(os.path.join(path, "HEAD")) and os.path.isdir(os.path.join(path, "objects"))


def probe_worktree(path: str) -> Worktree:
    """A swept path that `git worktree list` does not name: read its HEAD from git instead of guessing. Unborn only when
    git says it is on a branch with no commit; a HEAD that cannot be read is neither held nor unborn."""
    wt = Worktree(path=path, note="swept path not in worktree list")
    rc, ref, _ = git(path, "symbolic-ref", "-q", "HEAD")
    wt.branch = ref.strip() if rc == 0 and ref.strip() else None
    rc, sha, _ = git(path, "rev-parse", "--verify", "-q", "HEAD^{commit}")
    wt.head = sha.strip() if rc == 0 and OID_RE.match(sha.strip()) else None
    wt.detached = wt.branch is None and wt.head is not None
    wt.unborn = wt.branch is not None and wt.head is None
    return wt


def present_objects(anchor: str, shas: set[str]) -> set[str]:
    """Subset of shas that exist locally as commits (cat-file --batch-check; never fetches). An annotated tag's
    commit arrives as its own peeled `^{}` line, so tag objects themselves are not needed here."""
    if not shas:
        return set()
    rc, out, _ = git(
        anchor, "cat-file", "--batch-check=%(objectname) %(objecttype)", stdin="\n".join(sorted(shas)) + "\n"
    )
    if rc != 0:
        return set()
    present = set()
    for line in out.splitlines():
        sha, _, otype = line.partition(" ")
        if otype == "commit":
            present.add(sha)
    return present


def unheld_commits(anchor: str, commits: set[str], held: set[str]) -> set[str] | None:
    """Of `commits`, those NOT reachable from any `held` sha: `rev-list C... ^H...` lists exactly them."""
    if not commits or not held:
        return set(commits)
    stdin = "\n".join(sorted(commits)) + "\n" + "".join(f"^{sha}\n" for sha in sorted(held))
    rc, out, _ = git(anchor, "rev-list", "--stdin", stdin=stdin, timeout=GIT_TIMEOUT * 4)
    if rc != 0:
        return None
    listed = set(out.split())
    return {c for c in commits if c in listed}


# ---------------------------------------------------------------------------------------------------------------
# proving tips
# ---------------------------------------------------------------------------------------------------------------


def run_helper(ctx: Ctx, slug: str, sha: str, get_candidates: Callable[[], list[str]]) -> tuple[str, str]:
    """(PROVEN|ANCESTOR|NONE|ERROR, detail) from the gh helper, validated; cached per (repo, sha).

    ANCESTOR = GitHub's compare endpoint says the tip is an ancestor of a remote branch (the tracking refs here were
    behind the remote); PROVEN = a merged pull request in that repository had exactly this tip as its head."""
    key = (slug.lower(), sha)
    if key in ctx.pr_cache:
        return ctx.pr_cache[key]
    if ctx.helper is None:
        return "ERROR", "GitHub proof disabled"
    if not SLUG_RE.match(slug) or not SHA_RE.match(sha):
        return "ERROR", "invalid slug or sha (the GitHub helper speaks 40-hex SHA-1 ids only)"
    candidates = get_candidates()
    result = ("ERROR", "unreachable")
    for attempt in (1, 2):
        ctx.helper_throttle.wait()
        with ctx.lock:
            ctx.calls["helper"] += 1
        argv = [ctx.helper, slug, sha, ctx.default_branch.get(slug.lower(), "-"), *candidates]
        rc, out, err = run(argv, timeout=HELPER_TIMEOUT, env=dict(os.environ))
        fields = out.strip().splitlines()[0].split("\t") if out.strip() else []
        status = fields[0] if fields else "ERROR"
        asked = len(fields) > 2 and fields[1].lower() == slug.lower() and fields[2] == sha
        default = fields[-1] if len(fields) >= 5 and BRANCH_RE.match(fields[-1]) else ""
        if status in {"PROVEN", "ANCESTOR", "NONE"} and not asked:
            result = ("ERROR", "helper output does not match the question asked")
        elif status == "PROVEN" and rc == 0 and len(fields) == 6:
            number, merge = fields[3], fields[4]
            if number.isdigit() and SHA_RE.match(merge):
                ctx.default_branch[slug.lower()] = default or ctx.default_branch.get(slug.lower(), "")
                result = ("PROVEN", f"merged-PR: {slug}#{number} merge {merge[:12]} on {default}")
                break
            result = ("ERROR", "helper output does not match the question asked")
        elif status == "ANCESTOR" and rc == 0 and len(fields) >= 4:
            branch = fields[3]
            default = fields[4] if len(fields) > 4 and BRANCH_RE.match(fields[4]) else ""
            if default:
                ctx.default_branch[slug.lower()] = default
            if BRANCH_RE.match(branch) and (branch in candidates or branch == default):
                result = ("ANCESTOR", f"github-compare: {slug}:{branch}")
                break
            result = ("ERROR", "helper output does not match the question asked")
        elif status == "NONE" and rc == 1:
            if default:
                ctx.default_branch[slug.lower()] = default
            result = ("NONE", flat(fields[3] if len(fields) > 3 else "no proof", 80))
            break
        else:
            result = ("ERROR", flat(fields[3] if len(fields) > 3 else (err or f"rc={rc}"), 90))
        if attempt == 1 and "gh:" in result[1]:
            time.sleep(2.0)
            continue
        break
    ctx.pr_cache[key] = result
    return result


def candidate_branches(anchor: str, tip: Tip, remote: Remote | None) -> list[str]:
    """Remote heads (as the remote advertises them now) whose local tracking ref contains the tip: where to look."""
    if remote is None or remote.fresh is None or not tip.commit:
        return []
    prefix = f"refs/remotes/{remote.name}/"
    rc, out, _ = git(anchor, "for-each-ref", "--contains", tip.commit, "--format=%(refname)", prefix)
    names = []
    for ref in out.split() if rc == 0 else []:
        name = ref.removeprefix(prefix)
        if name != "HEAD" and BRANCH_RE.match(name) and f"refs/heads/{name}" in remote.fresh.refs:
            names.append(name)
    return sorted(set(names), key=lambda n: (n != tip.name, n))[:3]


def superseded_bot(anchor: str, tip: Tip, live: list[Remote]) -> str | None:
    """Evidence that a local dependabot/* or renovate/* branch is a stale, regenerable copy.

    Requires the same-named head to exist on a freshly listed remote at a DIFFERENT tip (the bot rewrote it) and EVERY
    commit the local branch holds beyond what the fresh remotes advertise to be bot-authored AND bot-committed (finding
    3b: a human `git commit --amend` keeps the bot as author). A bot commit made through the GitHub API is committed
    by `GitHub <noreply@github.com>`; that identity is accepted as committer, never as author. A human commit on top
    of a bot branch is real work and stays unproven."""
    if tip.kind != "branch" or not tip.commit or not BOT_BRANCH_RE.match(tip.name):
        return None
    ref = f"refs/heads/{tip.name}"
    for remote in live:
        assert remote.fresh is not None
        remote_sha = remote.fresh.refs.get(ref)
        if not remote_sha or remote_sha == tip.sha:
            continue
        advertised: set[str] = set()
        for other in live:
            assert other.fresh is not None
            advertised |= present_objects(anchor, other.fresh.shas)
        own = commits_beyond(anchor, tip.commit, advertised)
        if not own or len(own) > MAX_BOT_COMMITS:
            continue
        rc, out, _ = git(
            anchor,
            "log",
            "--no-walk=unsorted",
            "--stdin",
            "--format=%an <%ae>%x09%cn <%ce>",
            stdin="\n".join(own) + "\n",
        )
        lines = out.splitlines()
        if rc != 0 or len(lines) != len(own):
            continue
        if all(bot_commit(line) for line in lines):
            return f"{remote.name}:{ref} is now at {remote_sha[:12]}; local tip {tip.sha[:12]} is a bot-authored stale copy"
    return None


def bot_commit(line: str) -> bool:
    """`author<TAB>committer` of one commit: a bot wrote it and a bot (or GitHub on its behalf) committed it."""
    author, _, committer = line.partition("\t")
    return bool(BOT_AUTHOR_RE.search(author)) and (
        bool(BOT_AUTHOR_RE.search(committer)) or committer.strip() == GITHUB_COMMITTER
    )


def commits_beyond(anchor: str, tip: str, held: set[str]) -> list[str] | None:
    """Commits reachable from `tip` but from none of `held`, or None when git could not say."""
    stdin = tip + "\n" + "".join(f"^{sha}\n" for sha in sorted(held))
    rc, out, _ = git(anchor, "rev-list", "--stdin", stdin=stdin)
    return out.split() if rc == 0 else None


def prove_tips(ctx: Ctx, anchor: str, tips: list[Tip], remotes: list[Remote]) -> None:
    live = [r for r in remotes if r.kind == "network" and r.fresh is not None]
    failed = [r for r in remotes if r.kind == "network" and r.fresh is None]
    # 1. exact: the tip's own object is the SHA of a freshly listed remote ref. An annotated tag is held only when the
    #    remote has the tag OBJECT (finding 3a): its peeled commit being on a branch says nothing about the tag message.
    for tip in tips:
        for remote in sorted(live, key=lambda r: (not r.slug, r.name)):  # GitHub first: it holds the history too
            assert remote.fresh is not None
            ref = remote.fresh.by_sha.get(tip.sha)
            if ref:
                tip.status, tip.evidence, tip.via = EXACT, f"{remote.name}:{ref}", remote.name
                break
    # 2. ancestor: an ancestor of a fresh remote SHA that exists locally. Only a GitHub remote is known to hold the
    #    full history behind what it advertises; any other host could be a shallow repository (finding 3e), so there
    #    only an exact match proves. Annotated tag objects are never ancestors of anything.
    pending = [t for t in tips if not t.status and t.commit and not t.annotated]
    for remote in live:
        if not pending:
            break
        if not remote.slug:
            continue
        assert remote.fresh is not None
        present = present_objects(anchor, remote.fresh.shas)
        unheld = unheld_commits(anchor, {t.commit for t in pending if t.commit}, present)
        if unheld is None:
            continue
        for tip in pending:
            if tip.commit not in unheld:
                tip.status, tip.evidence = ANCESTOR, f"{remote.name} ({len(present)} fresh remote shas present locally)"
        pending = [t for t in pending if not t.status]
    # 2b. a stale dependabot/renovate branch the bot has since rewritten on the remote: regenerable, counted on its own
    for tip in tips:
        if not tip.status and (note := superseded_bot(anchor, tip, live)):
            tip.status, tip.evidence = SUPERSEDED, note
    # 3. GitHub, asked about the exact tip in the exact repository: ancestry of a remote branch the local tracking
    #    refs have fallen behind, or a merged pull request whose head was this tip (squash/rebase merges)
    slug_remotes = github_remotes(remotes)
    stale_note = stale_tracking(anchor, [t for t in tips if not t.status and t.commit], live)
    lookups: dict[tuple[str, str], tuple[str, str, list[str]]] = {}
    if slug_remotes and ctx.helper is not None:
        for tip in tips:
            if tip.status or not tip.commit or tip.kind == "other" or tip.annotated:
                continue
            for slug, remote in slug_remotes.items():
                key = (slug.lower(), tip.commit)
                if key not in ctx.pr_cache and key not in lookups:
                    lookups[key] = (slug, tip.commit, candidate_branches(anchor, tip, remote))
    if lookups:  # a repository with hundreds of branches would otherwise spend minutes in single-file lookups
        with ThreadPoolExecutor(max_workers=max(ctx.workers, 1)) as pool:
            list(pool.map(lambda job: run_helper(ctx, job[0], job[1], lambda c=job[2]: c), lookups.values()))
    for tip in tips:
        if tip.status:
            continue
        pr_state, pr_detail = "SKIPPED", ""
        if tip.commit and tip.kind != "other" and not tip.annotated and slug_remotes and ctx.helper is not None:
            for slug, remote in slug_remotes.items():
                state, detail = run_helper(
                    ctx, slug, tip.commit, lambda r=remote, t=tip: candidate_branches(anchor, t, r)
                )
                if state in {"PROVEN", "ANCESTOR"}:
                    tip.status, tip.evidence = (MERGED_PR if state == "PROVEN" else ANCESTOR), detail
                    break
                if state == "ERROR":
                    pr_state, pr_detail = "ERROR", detail
                elif pr_state != "ERROR":
                    pr_state, pr_detail = "NONE", detail
        if tip.status:
            continue
        if failed:
            tip.status, tip.evidence = R_NETWORK, "; ".join(f"{r.name}: {r.error}" for r in failed)
        elif pr_state == "ERROR":
            tip.status, tip.evidence = R_NETWORK, f"GitHub lookup inconclusive: {pr_detail}"
        else:
            why = stale_note.get(tip.ref) or "no fresh remote ref contains it"
            if tip.commit is None:
                why = "not a commit and not a remote ref"
            elif tip.annotated:
                why = "annotated tag object is not on any fresh remote ref (its commit alone does not hold the tag)"
            suffix = {"NONE": f"GitHub: {pr_detail}", "SKIPPED": "GitHub: not checked"}.get(pr_state, "")
            unheld = R_PER_WORKTREE if tip.kind == "per-worktree" else R_NOT_HELD
            tip.status, tip.evidence = unheld, f"{why}; {suffix}" if suffix else why


def github_remotes(remotes: list[Remote]) -> dict[str, Remote]:
    """slug -> the remote to ask about it (an answering one first): where the GitHub helper may be consulted."""
    found: dict[str, Remote] = {}
    for remote in sorted(remotes, key=lambda r: (r.fresh is None, r.name)):
        if remote.kind == "network" and remote.slug:
            found.setdefault(remote.slug, remote)
    return found


def failed_listings(remotes: list[Remote]) -> str:
    return "; ".join(f"{r.name}: {r.error or 'no answer'}" for r in remotes if r.fresh is None) or "none listed"


def sweep_beyond_tips(
    ctx: Ctx,
    anchor: str,
    common_dir: str,
    tips: list[Tip],
    remotes: list[Remote],
    stash_shas: list[str],
    gaps: set[str],
) -> list[tuple[str, str]]:
    """Finding 1: commits no ref tip names but a reflog or a remote-tracking ref still does (a deleted branch's work, an
    abandoned detached commit, a branch pushed and then deleted on both sides, a stale origin/x). They are local data too.

    Excluded as already accounted for: every tip commit (an unproven tip blocks the verdict by itself), every stash entry
    (blocks by itself), and every SHA a freshly listed remote advertises that exists locally (the remote holds it and, being
    a complete repository, what is behind it). What remains is walked down to its maximal commits; each is asked of GitHub
    (at most MAX_SWEEP_LOOKUPS per repository, the rest count as unheld) and anything still unheld blocks the verdict."""
    live = [r for r in remotes if r.kind == "network" and r.fresh is not None]
    held = {t.commit for t in tips if t.commit} | set(stash_shas)
    for remote in sorted(live, key=lambda r: (not r.slug, r.name)):  # GitHub first, so only what it lacks counts
        assert remote.fresh is not None
        present = present_objects(anchor, remote.fresh.shas)
        if not remote.slug and present - held:
            gaps.add(GAP_NONGITHUB)  # commits excluded on a non-GitHub remote's word that its history is complete
        held |= present
    exclude = "".join(f"^{sha}\n" for sha in sorted(held))
    # Walked from the common dir: git then reads the shared refs' reflogs and the HEAD reflog of the main checkout and of
    # every linked worktree, including one whose directory is already gone.
    walk = ["rev-list", "--reflog", "--remotes", "--stdin"]
    rc, out, err = git(anchor, f"--git-dir={common_dir}", *walk, stdin=exclude, timeout=GIT_TIMEOUT * 4)
    if rc != 0:
        return [(R_ERROR, f"reflog / tracking-ref reachability failed: {flat(err or f'rc={rc}', 90)}")]
    rest = set(out.split())
    if not rest:
        return []
    rc, parents, err = git(
        anchor, "rev-list", "--no-walk", "--parents", "--stdin", stdin="\n".join(sorted(rest)) + "\n"
    )
    if rc != 0:
        return [(R_ERROR, f"reflog / tracking-ref ancestry failed: {flat(err or f'rc={rc}', 90)}")]
    inner = {p for line in parents.splitlines() for p in line.split()[1:] if p in rest}
    sources = github_remotes(remotes)
    unheld = []
    for index, sha in enumerate(sorted(rest - inner)):
        proven = False
        if index < MAX_SWEEP_LOOKUPS and ctx.helper is not None:
            probe = Tip("(reflog)", "other", sha, sha)
            for slug, remote in sources.items():
                state, _detail = run_helper(ctx, slug, sha, lambda r=remote, t=probe: candidate_branches(anchor, t, r))
                if state in {"PROVEN", "ANCESTOR"}:
                    proven = True
                    break
        if not proven:
            unheld.append(sha)
    if not unheld:
        return []
    return [
        (
            R_REFLOG,
            f"{len(rest)} commit(s) reachable only from reflogs or remote-tracking refs, "
            f"{len(unheld)} head(s) not held remotely; first {unheld[0][:12]}",
        )
    ]


def stale_tracking(anchor: str, tips: list[Tip], live: list[Remote]) -> dict[str, str]:
    """Tips contained only in tracking refs the remote no longer advertises (force-push / deleted branch)."""
    notes: dict[str, str] = {}
    if not tips or not live:
        return notes
    rc, out, _ = git(anchor, "for-each-ref", "--format=%(refname)%09%(objectname)", "refs/remotes/")
    if rc != 0:
        return notes
    for remote in live:
        assert remote.fresh is not None
        fresh = remote.fresh.shas
        prefix = f"refs/remotes/{remote.name}/"
        stale = {
            line.split("\t")[1]
            for line in out.splitlines()
            if line.startswith(prefix) and "\t" in line and line.split("\t")[1] not in fresh
        }
        unheld = unheld_commits(anchor, {t.commit for t in tips if t.commit}, stale)
        if unheld is None:
            continue
        for tip in tips:
            if tip.commit and tip.commit not in unheld:
                notes[tip.ref] = (
                    f"only a stale tracking ref of {remote.name} holds it (the remote no longer has that sha)"
                )
    return notes


# ---------------------------------------------------------------------------------------------------------------
# per-repository analysis
# ---------------------------------------------------------------------------------------------------------------


def repo_label(group: Group, worktrees: list[Worktree]) -> str:
    for wt in worktrees:
        if not wt.bare:
            return os.path.realpath(wt.path)
    for row in group.rows:
        if row.kind == "repo":
            return os.path.realpath(row.path)
    return group.key.removesuffix("/.git")


def worktree_status(path: str) -> tuple[int, str]:
    rc, out, err = git(
        path, "status", "--porcelain=v1", "--untracked-files=normal", "--ignore-submodules=none", timeout=STATUS_TIMEOUT
    )
    if rc != 0:
        return -1, flat(err or f"status rc={rc}", 90)
    return len([ln for ln in out.splitlines() if ln.strip()]), ""


def hidden_edits(path: str) -> tuple[int, int, str]:
    """(entries hidden from status, of those edited on disk, error) for one worktree (finding 5).

    skip-worktree (sparse checkout) and assume-unchanged entries are not inspected by `git status`; a file edited behind
    such a bit is local work no commit holds. Each flagged file that exists is hashed and compared with its index entry."""
    rc, top, err = git(path, "rev-parse", "--show-toplevel")
    if (
        rc != 0 or not top.strip()
    ):  # the path given may be a git dir (a submodule's): names are relative to the checkout
        return 0, 0, f"cannot locate the work tree of {path}: {flat(err or f'rc={rc}', 90)}"
    top = top.rstrip("\n")
    rc, out, err = git(top, "ls-files", "-v", "-z")
    if rc != 0:
        return 0, 0, f"ls-files failed in {path}: {flat(err or f'rc={rc}', 90)}"
    flagged = [e[2:] for e in out.split("\0") if len(e) > 2 and (e[0] == "S" or e[0].islower())]
    if not flagged:
        return 0, 0, ""
    rc, staged, err = git(top, "ls-files", "-s", "-z")
    if rc != 0:
        return len(flagged), 0, f"ls-files -s failed in {path}: {flat(err or f'rc={rc}', 90)}"
    index_sha = {}
    for entry in staged.split("\0"):
        meta, _, name = entry.partition("\t")
        fields = meta.split()
        if len(fields) == 3 and fields[2] == "0":
            index_sha[name] = (fields[0], fields[1])
    present = [name for name in flagged if os.path.lexists(os.path.join(top, name))]
    edited = [n for n in present if "\n" in n or os.path.islink(os.path.join(top, n)) or n not in index_sha]
    hashable = [n for n in present if n not in edited]
    if hashable:
        rc, hashes, err = git(top, "hash-object", "--stdin-paths", stdin="\n".join(hashable) + "\n")
        listed = hashes.split()
        if rc != 0 or len(listed) != len(hashable):
            return len(flagged), 0, f"hash-object failed in {path}: {flat(err or f'rc={rc}', 90)}"
        edited += [n for n, sha in zip(hashable, listed, strict=True) if sha != index_sha[n][1]]
    return len(flagged), len(edited), ""


def has_content_files(top: str) -> bool:
    """Any file under `top`, symlinks to content included. A store that cannot be read is assumed to hold content."""
    unreadable: list[OSError] = []
    for _dirpath, _dirs, files in os.walk(top, onerror=unreadable.append):
        if files:
            return True
    return any(not isinstance(e, FileNotFoundError) for e in unreadable)


def has_lfs_objects(common_dir: str) -> bool:
    """git-lfs content lives outside the object database and every ref listing: under <git dir>/lfs/objects, or under
    `lfs.storage` when that relocates the store (a relative path is relative to the git dir, `~/` is the home)."""
    tops = [os.path.join(common_dir, "lfs", "objects")]
    rc, out, _err = git(common_dir, "config", "--get", "lfs.storage")
    if rc == 0 and out.strip():
        storage = os.path.expanduser(out.rstrip("\n"))
        tops.append(os.path.join(common_dir, storage, "objects"))
    elif rc != 1:  # 1 = the key is not set; anything else means we cannot tell where the store is
        return True
    return any(has_content_files(top) for top in tops)


def has_annex_objects(common_dir: str) -> bool:
    """git-annex content lives under <git dir>/annex/objects, as files git never stores in its object database."""
    return has_content_files(os.path.join(common_dir, "annex", "objects"))


def has_reflogs(common_dir: str) -> bool:
    """True when the repository keeps any reflog file. A bare repository keeps none unless core.logAllRefUpdates was set
    before the work, so a branch deleted there leaves a dangling commit nothing can enumerate."""
    return any(files for _dirpath, _dirs, files in os.walk(os.path.join(common_dir, "logs")))


def reflog_disabled(common_dir: str) -> bool:
    """A NON-bare repository whose reflogs cannot enumerate abandoned commits: core.logAllRefUpdates is explicitly false
    (new ref updates are not logged, so a deleted branch's commit leaves no trace `rev-list --reflog` can find), or it keeps
    no reflog file at all. A setting that cannot be read counts as disabled."""
    rc, out, _err = git(common_dir, "config", "--get", "core.logAllRefUpdates")
    if rc == 0 and out.strip().lower() in {"false", "no", "off", "0"}:
        return True
    if rc not in (0, 1):  # 1 = not set (git's default logs branches and HEAD)
        return True
    return not has_reflogs(common_dir)


def module_gitdirs(common_dir: str) -> tuple[list[str], str]:
    """(submodule git dirs under <common>/modules, error). A name may contain `/`; nested modules are found when the
    module itself is analysed."""
    found: list[str] = []
    failures: list[str] = []
    top = os.path.join(common_dir, "modules")
    if not os.path.isdir(top):
        return [], ""
    for dirpath, dirs, _files in os.walk(top, onerror=lambda e: failures.append(e.strerror or str(e))):
        if os.path.isfile(os.path.join(dirpath, "HEAD")) and os.path.isdir(os.path.join(dirpath, "objects")):
            found.append(dirpath)
            dirs[:] = []
    return sorted(found), "; ".join(failures)


def alternate_gitdirs(common_dir: str) -> tuple[list[str], str]:
    """(git dirs lending objects to this repository via objects/info/alternates, error)."""
    path = os.path.join(common_dir, "objects", "info", "alternates")
    if not os.path.exists(path):
        return [], ""
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        return [], f"cannot read objects/info/alternates: {exc.strerror}"
    lenders = []
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        objects = os.path.realpath(os.path.join(common_dir, "objects", line))
        if os.path.basename(objects) != "objects" or not os.path.isfile(os.path.join(os.path.dirname(objects), "HEAD")):
            return [], f"alternates entry {flat(line, 80)} is not the objects dir of a git repository"
        lenders.append(os.path.dirname(objects))
    return lenders, ""


def module_worktree(gitdir: str) -> str:
    """The checkout of a submodule git dir (core.worktree), or the git dir itself when it has none (a bare lender)."""
    rc, top, _ = git(gitdir, "rev-parse", "--show-toplevel")
    return top.rstrip("\n") if rc == 0 and top.strip() else gitdir


def analyze_nested(ctx: Ctx, gitdir: str, kind: str, depth: int) -> RepoResult:
    """A submodule's or an alternates lender's repository, analysed exactly like a swept one (its own remote, tips,
    reflogs, stash). Its worktree comes from `.git` being a directory named `.git` (a normal lender) or from core.worktree
    (a submodule); the sweep entry's status is the parent's `status --ignore-submodules=none`."""
    real = os.path.realpath(gitdir)
    anchor = os.path.dirname(real) if os.path.basename(real) == ".git" else module_worktree(real)
    return analyze_group(ctx, Group(real, [Row(anchor, kind, {})]), depth + 1)


def nested_reasons(ctx: Ctx, common_dir: str, depth: int, gaps: set[str]) -> tuple[list[tuple[str, str]], list[str]]:
    """Reasons and notes from everything this repository depends on or carries: submodules, alternates lenders, LFS."""
    reasons: list[tuple[str, str]] = []
    notes: list[str] = []
    if has_lfs_objects(common_dir):
        reasons.append((R_LFS, "git-lfs objects are stored locally and cannot be checked against a remote"))
    if has_annex_objects(common_dir):
        reasons.append((R_ANNEX, "git-annex content is stored locally and cannot be checked against a remote"))
    for kind, code, (dirs, error) in (
        ("submodule", R_SUBMODULE, module_gitdirs(common_dir)),
        ("alternates lender", R_ALTERNATES, alternate_gitdirs(common_dir)),
    ):
        if error:
            reasons.append((R_ERROR, f"{kind} discovery failed: {flat(error, 120)}"))
        bad = []
        for gitdir in dirs:
            if depth >= MAX_MODULE_DEPTH:
                bad.append(f"{os.path.basename(gitdir)}: nested more than {MAX_MODULE_DEPTH} deep")
                continue
            sub = analyze_nested(ctx, gitdir, kind, depth)
            gaps |= sub.gaps  # a submodule's assumptions are the superproject's
            if sub.verdict != "PROVEN-ALL":
                bad.append(f"{os.path.basename(gitdir)}: {sub.first_reason}")
        if dirs:
            notes.append(f"{kind}s analysed: {len(dirs)}")
        if bad:
            reasons.append((code, f"{len(bad)} of {len(dirs)} {kind}(s) not PROVEN-ALL; first {flat(bad[0], 200)}"))
    return reasons, notes


def analyze_group(ctx: Ctx, group: Group, depth: int = 0) -> RepoResult:
    """analyze_repo, refusing a repository that is already being analysed higher up (an alternates or submodule cycle)."""
    if group.key in ctx.visiting:
        res = RepoResult(
            repo=os.path.realpath(group.rows[0].path), common_dir=group.key, rows=group.rows, scope="whole-repo"
        )
        res.reasons = [(R_ERROR, "repository depends on itself (alternates / submodule cycle)")]
        res.row_facts = [RowFacts(r, held="no") for r in group.rows]
        return res
    ctx.visiting.add(group.key)
    try:
        return refuse_unrepresentable(analyze_repo(ctx, group, depth))
    finally:
        ctx.visiting.discard(group.key)


def unrepresentable_keys(res: RepoResult) -> list[str]:
    """The join keys of this repository that cannot be written losslessly (contract 1): a TAB, CR, LF (or any other line
    boundary) in a path or ref name, or a `;` inside one element of the `paths` list."""
    bad: list[str] = []
    for label, value in (("repo", res.repo), ("common_dir", res.common_dir)):
        if KEY_UNSAFE_RE.search(value):
            bad.append(label)
    row_paths = [os.path.realpath(r.path) for r in res.rows]
    if any(KEY_UNSAFE_RE.search(p) or ";" in p for p in row_paths):
        bad.append("paths")
    if any(KEY_UNSAFE_RE.search(os.path.realpath(w.path)) for w in res.worktrees):
        bad.append("worktree")
    if any(KEY_UNSAFE_RE.search(t.ref) for t in res.tips):
        bad.append("ref")
    return bad


def refuse_unrepresentable(res: RepoResult) -> RepoResult:
    """A repository whose join keys cannot be written byte-identical is UNPROVEN: the consumer would otherwise look up a
    mangled path, find nothing, and read 'not named' as 'nothing to protect'. The cells carry U+FFFD instead."""
    bad = unrepresentable_keys(res)
    if not bad:
        return res
    res.reasons = sorted(
        [*res.reasons, (R_UNREPRESENTABLE, f"join key(s) {', '.join(bad)} contain a character the TSV cannot carry")],
        key=lambda reason: REASON_ORDER.index(reason[0]) if reason[0] in REASON_ORDER else 99,
    )
    res.verdict, res.branches_verdict = "UNPROVEN", "UNPROVEN"
    if res.scope in {"", "nothing-to-preserve", "partial"}:
        res.scope = "whole-repo"  # the keys are unusable, so nothing can be scoped down to part of the repository
    for fact in res.row_facts:
        if fact.held == "yes":
            fact.held = "no"
    return res


def analyze_repo(ctx: Ctx, group: Group, depth: int) -> RepoResult:
    started = time.monotonic()
    res = RepoResult(repo=os.path.realpath(group.rows[0].path), common_dir=group.key, rows=group.rows)
    if group.error:
        # A path that vanished after the sweep is never PROVEN; it is also nothing local to preserve (scope=vanished).
        # A directory git cannot open (orphaned worktree, empty .git file) has files but no git metadata: whole-repo.
        vanished = group.key.startswith("MISSING:")
        code = R_VANISHED if vanished else R_ORPHAN if group.key.startswith("NOMETA:") else R_ERROR
        res.reasons = [(code, group.error)]
        res.scope = "vanished" if vanished else "whole-repo"
        res.row_facts = [RowFacts(r, held="vanished" if vanished else "no") for r in group.rows]
        return res
    anchor = group.rows[0].path
    common: list[tuple[str, str]] = []  # reasons that block both verdicts (remote, tree, stash, errors)
    res.worktrees, listing_error = collect_worktrees(anchor)
    if listing_error:
        common.append((R_ERROR, listing_error))
    listed = {os.path.realpath(w.path) for w in res.worktrees}
    for row in group.rows:
        if os.path.realpath(row.path) not in listed and os.path.isdir(row.path):
            res.worktrees.append(probe_worktree(row.path))
            listed.add(os.path.realpath(row.path))
    res.repo = repo_label(group, res.worktrees)
    res.remotes, listing_error = collect_remotes(ctx, anchor)
    if listing_error:
        common.append((R_ERROR, listing_error))
    if any(r.trusted for r in res.remotes):
        res.gaps.add(GAP_TRUST)
    if any(w.bare for w in res.worktrees) and not has_reflogs(group.key):
        res.gaps.add(GAP_BARE)
    if not any(w.bare for w in res.worktrees) and reflog_disabled(group.key):
        res.gaps.add(GAP_NO_REFLOG)
    tips_or_err = collect_tips(anchor)
    if isinstance(tips_or_err, str):
        common.append((R_ERROR, tips_or_err))
        tips: list[Tip] = []
    else:
        tips = tips_or_err
    main_label = os.path.realpath(res.worktrees[0].path) if res.worktrees else os.path.realpath(group.key)
    per_worktree, per_errors = collect_per_worktree_tips(anchor, group.key, main_label)
    common += [(R_ERROR, e) for e in per_errors]
    tips += per_worktree
    for wt in res.worktrees:
        if wt.detached and wt.head and not wt.bare:
            tips.append(Tip(f"HEAD@{os.path.realpath(wt.path)}", "detached", wt.head, wt.head))
    res.tips = tips

    res.stashes, stash_shas, stash_errors = collect_stashes(anchor)
    common += [(R_ERROR, e) for e in stash_errors]
    if res.stashes:
        common.append((R_STASH, f"{res.stashes} stash entries (never on a remote)"))

    usable = [r for r in res.remotes if r.kind == "network"]
    for remote in usable:
        fetch_fresh(ctx, anchor, remote)
    answered = [r for r in usable if r.fresh is not None]
    if not usable:
        if listing_error:
            code, detail = R_ERROR, listing_error  # already a reason above; the tips just need a blocking status
        elif not res.remotes:
            code, detail = R_NO_REMOTE, "repository has no remote"
        elif any(r.kind == "local" for r in res.remotes):
            code = R_LOCAL
            detail = "only filesystem-path remotes: " + ", ".join(
                f"{r.name}={flat(r.raw_url, 60)}" for r in res.remotes
            )
        else:
            code, detail = R_UNSUPPORTED, ", ".join(f"{r.name}={flat(r.raw_url, 60)}" for r in res.remotes)
        if (code, detail) not in common:
            common.append((code, detail))
        for tip in tips:
            tip.status, tip.evidence = code, detail
    else:
        prove_tips(ctx, anchor, tips, res.remotes)
        by_name = {r.name: r for r in res.remotes}
        if any(t.status == EXACT and t.via in by_name and not by_name[t.via].slug for t in tips):
            res.gaps.add(GAP_NONGITHUB)
        if not answered:  # finding 4c: GitHub lookups alone never stand in for a fresh listing
            common.append((R_NETWORK, "no network remote answered a fresh listing: " + failed_listings(usable)))
        common += sweep_beyond_tips(ctx, anchor, group.key, tips, res.remotes, stash_shas, res.gaps)
        nested, nested_notes = nested_reasons(ctx, group.key, depth, res.gaps)
        common += nested
        res.notes += nested_notes
        if any(not r.slug for r in answered):
            res.notes.append(
                "non-GitHub remote: exact tips are proven by SHA, but history behind them is assumed complete there "
                "(ls-remote cannot show a shallow remote)"
            )
    res.scope = "partial" if answered else "whole-repo"
    tip_reasons = unproven_tip_reasons(tips) if tips and usable else []
    branch_tip_reasons = unproven_tip_reasons([t for t in tips if t.kind in {"branch", "detached"}]) if usable else []

    # working trees: every worktree git knows plus every swept path, de-duplicated by real path
    seen: dict[str, Worktree] = {}
    for wt in res.worktrees:
        seen[os.path.realpath(wt.path)] = wt
    for row in group.rows:
        real = os.path.realpath(row.path)
        if real not in seen:
            seen[real] = Worktree(path=row.path, note="swept path not in worktree list")
            res.worktrees.append(seen[real])
    status_errors: list[str] = []
    hidden_wts: list[str] = []
    for wt in res.worktrees:
        if wt.bare:
            continue
        if wt.missing or not os.path.isdir(wt.path):
            wt.missing, wt.dirty, wt.note = True, 0, wt.note or "worktree directory missing (nothing to lose)"
            continue
        wt.dirty, err = worktree_status(wt.path)
        if wt.dirty < 0:
            wt.note = err
            status_errors.append(f"{wt.path}: {err}")
            continue
        flagged, edited, err = hidden_edits(wt.path)
        if err:
            status_errors.append(err)
        elif flagged:
            res.notes.append(f"{flagged} skip-worktree / assume-unchanged entries in {wt.path} are hidden from status")
        wt.hidden = max(edited, 1) if err else edited  # an unreadable index is not 'nothing hidden'
        if edited:
            hidden_wts.append(f"{wt.path}: {edited}")
    dirty_wts = [w for w in res.worktrees if w.dirty > 0]
    if dirty_wts:
        common.append((R_DIRTY, f"{res.dirty_entries} entries in {len(dirty_wts)} worktree(s)"))
    if hidden_wts:
        common.append(
            (R_HIDDEN, "files edited behind skip-worktree / assume-unchanged: " + "; ".join(hidden_wts)[:200])
        )
    if status_errors:
        common.append((R_ERROR, "status failed: " + "; ".join(status_errors)[:200]))

    def order(reasons: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return sorted(reasons, key=lambda reason: REASON_ORDER.index(reason[0]) if reason[0] in REASON_ORDER else 99)

    res.reasons = order(common + tip_reasons)
    res.verdict = "UNPROVEN" if res.reasons else "PROVEN-ALL"
    res.branches_verdict = BRANCHES_PROVEN if not common and not branch_tip_reasons else "UNPROVEN"
    if not os.path.isdir(anchor):
        # the repository was deleted while it was being examined (a live Mac): what was read is not evidence
        res.reasons = [(R_VANISHED, "path vanished while it was being examined")]
        res.verdict, res.branches_verdict, res.scope = "UNPROVEN", "UNPROVEN", "vanished"
    elif res.verdict == "PROVEN-ALL":
        res.scope = "nothing-to-preserve"  # `partial` here would read as "part of it is unproven"
    res.row_facts = row_facts(res, seen)
    res.seconds = time.monotonic() - started
    return res


def unproven_tip_reasons(tips: list[Tip]) -> list[tuple[str, str]]:
    """One reason per code (network / not held) for the tips that block a verdict; superseded bot branches do not."""
    by_code: dict[str, list[Tip]] = {}
    for tip in tips:
        if tip.blocking and tip.status in {R_NETWORK, R_NOT_HELD, R_PER_WORKTREE}:
            by_code.setdefault(tip.status, []).append(tip)
    reasons = []
    for code in (R_NETWORK, R_NOT_HELD, R_PER_WORKTREE):
        if code in by_code:
            first = by_code[code][0]
            reasons.append((code, f"{len(by_code[code])} tip(s); first {first.name}: {first.evidence}"))
    return reasons


def row_facts(res: RepoResult, seen: dict[str, Worktree]) -> list[RowFacts]:
    by_ref = {t.ref: t for t in res.tips}
    facts = []
    for row in res.rows:
        wt = seen.get(os.path.realpath(row.path))
        fact = RowFacts(row)
        if wt is None or wt.missing:
            fact.held = "vanished"
        elif wt.bare:
            fact.head, fact.held = "(bare)", "yes" if res.verdict == "PROVEN-ALL" else "no"
        else:
            fact.dirty = wt.dirty
            tip = None
            if wt.detached:
                fact.head = f"(detached) {wt.head or ''}"[:60]
                tip = by_ref.get(f"HEAD@{os.path.realpath(wt.path)}")
            elif wt.branch:
                fact.head = wt.branch
                tip = by_ref.get(wt.branch)
            if tip is not None:
                fact.head_status = tip.status
            elif wt.unborn:
                fact.head, fact.head_status = fact.head or "(unborn)", "UNBORN"
            clean = fact.dirty == 0 and wt.hidden == 0
            head_ok = fact.head_status == "UNBORN" or (tip is not None and not tip.blocking)
            fact.held = "yes" if clean and head_ok else "no"
            # Finding 2: the path that holds the git common dir takes every ref, reflog and stash with it when it is
            # deleted, so its own HEAD being held says nothing unless the whole repository is.
            if fact.held == "yes" and holds_common_dir(wt.path, res.common_dir) and res.verdict != "PROVEN-ALL":
                fact.held = "no"
        facts.append(fact)
    return facts


def holds_common_dir(path: str, common_dir: str) -> bool:
    """True when `path` is the checkout whose `.git` directory IS the repository (not a linked worktree)."""
    return os.path.realpath(os.path.join(path, ".git")) == os.path.realpath(common_dir)


def timeout_result(group: Group) -> RepoResult:
    res = RepoResult(
        repo=os.path.realpath(group.rows[0].path), common_dir=group.key, rows=group.rows, scope="whole-repo"
    )
    res.reasons = [(R_TIMEOUT, "not examined before the deadline")]
    res.row_facts = [RowFacts(r, held="no") for r in group.rows]
    return res


# ---------------------------------------------------------------------------------------------------------------
# outputs
# ---------------------------------------------------------------------------------------------------------------

EXIT_CODES = (
    "exit codes: 0 = complete run, every repository PROVEN-ALL with an empty `gaps` column; 1 = complete run, some\n"
    "repository not PROVEN-ALL or PROVEN-ALL with a documented gap (a --trust-remote-under run never exits 0);\n"
    "64 = usage error (nothing is created); 70 = internal error or an incomplete run (--limit dropped entries,\n"
    "the deadline left repositories unexamined, an exception). --self-test: 0 all checks pass, 1 otherwise."
)
REMOTE_HELD_COLS = [
    "repo",
    "common_dir",
    "remotes",
    "branches_total",
    "exact",
    "ancestor",
    "merged_pr",
    "unproven",
    "dirty_entries",
    "stashes",
    "verdict",
    "first_reason",
    "tags_total",
    "tags_unproven",
    "other_unproven",
    "detached_total",
    "detached_unproven",
    "worktrees",
    "dirty_worktrees",
    "rows",
    "scope",
    "seconds",
    "paths",
    "branches_verdict",
    "superseded_bot",
    "all_reasons",
    "notes",
    "gaps",
]
UNPROVEN_COLS = ["repo", "branch", "tip", "reason", "kind"]
SUPERSEDED_COLS = ["repo", "branch", "tip", "evidence"]
VANISHED_COLS = [
    "path",
    "kind",
    "reason",
    "sweep_remote",
    "sweep_dirty",
    "sweep_unpushed",
    "sweep_stashes",
    "had_exposure_in_sweep",
]
PRESERVE_COLS = [
    "repo",
    "common_dir",
    "scope",
    "unproven_refs",
    "unproven_ref_names",
    "dirty_worktrees",
    "dirty_entries",
    "stashes",
    "reason_codes",
    "first_reason",
]
TIPS_COLS = ["repo", "ref", "kind", "tip", "status", "evidence"]
WORKTREE_COLS = ["repo", "worktree", "head", "dirty_entries", "note"]
ENTRY_COLS = [
    "path",
    "kind",
    "common_dir",
    "repo_verdict",
    "repo_first_reason",
    "row_head",
    "row_head_status",
    "row_dirty_entries",
    "head_held",  # this checkout's own HEAD is held and it is clean; NOT "safe to delete" unless repo_verdict says so
    "sweep_dirty",
    "sweep_unpushed",
    "sweep_stashes",
    "repo_branches_verdict",
]
OUT_SPECS = {
    "remote-held": REMOTE_HELD_COLS,
    "unproven-branches": UNPROVEN_COLS,
    "superseded-bot-branches": SUPERSEDED_COLS,
    "preserve-set": PRESERVE_COLS,
    "tips": TIPS_COLS,
    "worktrees": WORKTREE_COLS,
    "entries": ENTRY_COLS,
    "vanished": VANISHED_COLS,
}
# Join keys (contract 1): written byte-identical through key_cell, never flattened, collapsed, redacted or truncated.
# Every path in them is an os.path.realpath(); the predicate realpaths its side too before it compares.
LOSSLESS_COLS: dict[str, frozenset[str]] = {
    "remote-held": frozenset({"repo", "common_dir", "paths"}),
    "tips": frozenset({"repo", "ref", "tip"}),
    "entries": frozenset({"path", "common_dir"}),
    "worktrees": frozenset({"repo", "worktree"}),
    "preserve-set": frozenset({"repo", "common_dir"}),
    "unproven-branches": frozenset({"repo"}),
    "superseded-bot-branches": frozenset({"repo"}),
    "vanished": frozenset({"path"}),
    "real-compare": frozenset({"path"}),
}


def cell(value: object) -> str:
    """A free-text cell: whitespace collapsed. Join keys never come through here (see TsvOut.lossless)."""
    return LONE_SURROGATE_RE.sub(FFFD, " ".join(value.split())) if isinstance(value, str) else str(value)


END_MARK = "#END"


class TsvOut:
    """A TSV that ends with a full-width completion row `#END rows=N` (finding 4g): a file cut short by a crash lacks
    it, and a consumer that reads every row by column index (as check-exit-ready.py does) still finds the columns.

    `lossless` names the join-key columns (contract 1): they are written byte-identical through key_cell, every other
    column is free text and collapses whitespace."""

    def __init__(self, path: Path, cols: list[str], lossless: frozenset[str] = frozenset()) -> None:
        self.fh = path.open("x", encoding="utf-8", newline="")
        self.cols = cols
        self.lossless = lossless
        self.rows = 0
        self.fh.write("\t".join(cols) + "\n")
        self.fh.flush()

    def write(self, **values: object) -> None:
        self.fh.write("\t".join(self.render(c, values.get(c, "")) for c in self.cols) + "\n")
        self.fh.flush()
        self.rows += 1

    def render(self, col: str, value: object) -> str:
        return key_cell(str(value)) if col in self.lossless else cell(value)

    def close(self, *, complete: bool = True) -> None:
        """Write the completion row and close. complete=False (an aborted run) closes WITHOUT it: the file must read as cut
        short, never as a finished one."""
        if not self.fh.closed:
            if complete:
                self.fh.write("\t".join([f"{END_MARK} rows={self.rows}"] + [END_MARK] * (len(self.cols) - 1)) + "\n")
            self.fh.close()


def open_outs(out_dir: Path) -> dict[str, TsvOut]:
    return {
        name: TsvOut(out_dir / f"{name}.tsv", cols, LOSSLESS_COLS.get(name, frozenset()))
        for name, cols in OUT_SPECS.items()
    }


def remotes_cell(res: RepoResult) -> str:
    return "; ".join(f"{r.name}={flat(r.raw_url or r.resolved_url, 100)} [{r.flag()}]" for r in res.remotes) or "NONE"


def write_repo(outs: dict[str, TsvOut], res: RepoResult) -> None:
    branches = [t for t in res.tips if t.kind == "branch"]
    dirty_wts = [w for w in res.worktrees if w.dirty > 0]
    repo = res.repo
    outs["remote-held"].write(
        repo=repo,
        common_dir=res.common_dir,
        remotes=remotes_cell(res),
        branches_total=len(branches),
        exact=res.count("branch", EXACT),
        ancestor=res.count("branch", ANCESTOR),
        merged_pr=res.count("branch", MERGED_PR),
        unproven=res.count("branch", "UNPROVEN"),
        dirty_entries=res.dirty_entries,
        stashes=res.stashes,
        verdict=res.verdict,
        first_reason=flat(res.first_reason, 300),
        tags_total=res.count("tag"),
        tags_unproven=res.count("tag", "UNPROVEN"),
        other_unproven=res.count("other", "UNPROVEN") + res.count("per-worktree", "UNPROVEN"),
        detached_total=res.count("detached"),
        detached_unproven=res.count("detached", "UNPROVEN"),
        worktrees=len(res.worktrees),
        dirty_worktrees=len(dirty_wts),
        rows=len(res.rows),
        scope=res.scope,
        seconds=f"{res.seconds:.1f}",
        paths=paths_cell([os.path.realpath(r.path) for r in res.rows]),
        branches_verdict=res.branches_verdict,
        superseded_bot=sum(1 for t in res.tips if t.status == SUPERSEDED),
        all_reasons=flat(res.all_reasons, 1500),
        notes=flat(res.all_notes, 600),
        gaps=res.gaps_cell,
    )
    for tip in res.tips:
        outs["tips"].write(
            repo=repo,
            ref=tip.ref,
            kind=tip.kind,
            tip=tip.sha,
            status=tip.status,
            evidence=flat(tip.evidence, 300),
        )
        if tip.status == SUPERSEDED:
            outs["superseded-bot-branches"].write(
                repo=repo, branch=flat(tip.name, 300), tip=tip.sha, evidence=flat(tip.evidence, 300)
            )
        elif tip.blocking:
            outs["unproven-branches"].write(
                repo=repo,
                branch=flat(tip.name, 300),
                tip=tip.sha,
                kind=tip.kind,
                reason=flat(f"{tip.status}: {tip.evidence}", 400),
            )
    for wt in res.worktrees:
        head = "(bare)" if wt.bare else wt.branch or (f"(detached) {wt.head}" if wt.detached else "(unborn)")
        outs["worktrees"].write(
            repo=repo,
            worktree=os.path.realpath(wt.path),
            head=flat(head, 120),
            dirty_entries=wt.dirty,
            note=flat(wt.note, 160),
        )
    if res.verdict == "UNPROVEN" and res.scope != "vanished":  # a vanished path leaves nothing local to preserve
        refs = [t.name for t in res.tips if t.blocking]
        outs["preserve-set"].write(
            repo=repo,
            common_dir=res.common_dir,
            scope=res.scope,
            unproven_refs=len(refs),
            unproven_ref_names=flat(";".join(refs[:40]) + (f";...(+{len(refs) - 40})" if len(refs) > 40 else ""), 600),
            dirty_worktrees=flat(";".join(f"{w.path}={w.dirty}" for w in dirty_wts), 600),
            dirty_entries=res.dirty_entries,
            stashes=res.stashes,
            reason_codes=",".join(code for code, _ in res.reasons),
            first_reason=flat(res.first_reason, 300),
        )
    for fact in res.row_facts:
        sweep = fact.row.sweep
        outs["entries"].write(
            path=os.path.realpath(fact.row.path),
            kind=fact.row.kind,
            common_dir=res.common_dir,
            repo_verdict=res.verdict,
            repo_first_reason=flat(res.first_reason, 200),
            row_head=flat(fact.head, 120),
            row_head_status=fact.head_status,
            row_dirty_entries=fact.dirty if fact.dirty >= 0 else "",
            head_held=fact.held,
            sweep_dirty=sweep.get("dirty", ""),
            sweep_unpushed=sweep.get("unpushed", ""),
            sweep_stashes=sweep.get("stashes", ""),
            repo_branches_verdict=res.branches_verdict,
        )
        if fact.held == "vanished":
            exposed = any(sweep.get(k, "0") not in {"0", ""} for k in ("dirty", "unpushed", "stashes")) or (
                sweep.get("remote", "") == "NONE"
            )
            outs["vanished"].write(
                path=os.path.realpath(fact.row.path),
                kind=fact.row.kind,
                reason=flat(res.first_reason, 200) if res.scope == "vanished" else "worktree directory missing",
                sweep_remote=flat(sweep.get("remote", ""), 200),
                sweep_dirty=sweep.get("dirty", ""),
                sweep_unpushed=sweep.get("unpushed", ""),
                sweep_stashes=sweep.get("stashes", ""),
                had_exposure_in_sweep="yes" if exposed else "no",
            )


def code_of(reason: str) -> str:
    return reason.split(":", 1)[0]


def write_summary(
    path: Path,
    results: list[RepoResult],
    ctx: Ctx,
    started: float,
    args_note: str,
    compare: list[Row] | None,
    incomplete: list[str] | None = None,
) -> None:
    lines = [f"prove-remote-held summary ({time.strftime('%Y-%m-%d %H:%M:%S')})", args_note, ""]
    lines += [f"INCOMPLETE RUN: {reason}" for reason in incomplete or []]
    lines += [""] if incomplete else []
    if ctx.trusted:
        relying = sum(1 for r in results if GAP_TRUST in r.gaps)
        lines += [
            f"WARNING: --trust-remote-under ({', '.join(ctx.trusted)}) is TEST ONLY: filesystem remotes under it were counted as "
            f"offsite. {relying} of {len(results)} repositories rely on it and carry the gap {GAP_TRUST}; "
            "none of them proves anything for an erase.",
            "",
        ]
    entries = sum(len(r.rows) for r in results)
    verdicts = Counter(r.verdict for r in results)
    vanished = sum(1 for r in results if r.scope == "vanished")
    lines += [
        f"repositories examined (distinct git common dirs): {len(results)}   (from {entries} sweep entries)",
        f"  PROVEN-ALL: {verdicts['PROVEN-ALL']}",
        f"  UNPROVEN:   {verdicts['UNPROVEN']}",
        f"    of which UNPROVEN-VANISHED (path gone since the sweep, nothing local to preserve): {vanished}",
        "",
        f"PROVEN-ALL with no documented gap (all a consumer can trust): "
        f"{sum(1 for r in results if r.verdict == 'PROVEN-ALL' and not r.gaps)}",
        "documented gaps (a PROVEN-ALL row that carries one is NOT to be trusted; the `gaps` column of remote-held.tsv):",
        *(
            [f"  {n:4d}  {code}" for code, n in Counter(c for r in results for c in r.gaps).most_common()]
            or ["        (none)"]
        ),
        "",
        "second, weaker verdict (PROVEN-ALL above is NOT loosened): BRANCHES-PROVEN = every branch and detached-HEAD tip",
        "proven, every worktree clean, no stash; tags and other refs are not required",
        (
            f"  BRANCHES-PROVEN: {sum(1 for r in results if r.branches_verdict == BRANCHES_PROVEN)}"
            f"   (PROVEN-ALL ones among them: {sum(1 for r in results if r.verdict == 'PROVEN-ALL')};"
            f" BRANCHES-PROVEN but not PROVEN-ALL, i.e. held up only by tags / other refs:"
            f" {sum(1 for r in results if r.branches_verdict == BRANCHES_PROVEN and r.verdict != 'PROVEN-ALL')})"
        ),
        "",
        "UNPROVEN repositories by first reason:",
    ]
    first = Counter(code_of(r.first_reason) for r in results if r.verdict == "UNPROVEN")
    lines += [f"  {n:4d}  {code}" for code, n in first.most_common()]
    lines += ["", "UNPROVEN repositories by any reason (a repository can carry several):"]
    anyc = Counter(code for r in results if r.verdict == "UNPROVEN" for code in {c for c, _ in r.reasons})
    lines += [f"  {n:4d}  {code}" for code, n in anyc.most_common()]
    tips = [t for r in results for t in r.tips]
    lines += ["", f"ref tips examined: {len(tips)}"]
    for kind in ("branch", "tag", "other", "detached", "per-worktree"):
        kt = [t for t in tips if t.kind == kind]
        st = Counter(t.status if t.proven else code_of(t.status) for t in kt)
        lines.append(f"  {kind}: {len(kt)}  " + "  ".join(f"{k}={v}" for k, v in sorted(st.items())))
    via_compare = sum(1 for t in tips if t.status == ANCESTOR and t.evidence.startswith("github-compare"))
    lines.append(f"  (PROVEN-ANCESTOR via GitHub compare rather than local objects: {via_compare})")
    bots = [t for t in tips if t.status == SUPERSEDED]
    lines.append(
        f"  SUPERSEDED-BOT-BRANCH (stale dependabot/renovate copies; regenerable; never block a verdict, listed in"
        f" superseded-bot-branches.tsv): {len(bots)} tips in {sum(1 for r in results if any(t.status == SUPERSEDED for t in r.tips))} repos"
    )
    lines += [
        "",
        (
            f"working trees: {sum(len(r.worktrees) for r in results)}; dirty: {sum(1 for r in results for w in r.worktrees if w.dirty > 0)};"
            f" dirty entries: {sum(r.dirty_entries for r in results)}; stash entries: {sum(r.stashes for r in results)}"
        ),
        (
            f"scope of UNPROVEN repositories: whole-repo={sum(1 for r in results if r.verdict == 'UNPROVEN' and r.scope == 'whole-repo')}"
            f" partial={sum(1 for r in results if r.verdict == 'UNPROVEN' and r.scope == 'partial')}"
        ),
        "",
        (
            f"network calls: ls-remote={ctx.calls['ls-remote']} (cached listings: {len(ctx.fresh_ok)}),"
            f" merged-PR helper={ctx.calls['helper']}; elapsed {time.monotonic() - started:.0f}s"
        ),
    ]
    if compare is not None:
        by_path = {os.path.realpath(f.row.path): (r, f) for r in results for f in r.row_facts}
        lines += ["", f"real.tsv comparison ({len(compare)} entries):"]
        repo_states: Counter[str] = Counter()
        branch_states: Counter[str] = Counter()
        row_states: Counter[str] = Counter()
        repos_all: dict[str, RepoResult] = {}
        for row in compare:
            hit = by_path.get(os.path.realpath(row.path))
            if hit is None:
                repo_states["not-in-sweep"] += 1
                branch_states["not-in-sweep"] += 1
                row_states["not-in-sweep"] += 1
                continue
            res, fact = hit
            repo_states[R_VANISHED if res.scope == "vanished" else res.verdict] += 1
            branch_states[R_VANISHED if res.scope == "vanished" else res.branches_verdict] += 1
            row_states[fact.held] += 1
            repos_all[res.common_dir] = res
        lines += [
            "  by REPOSITORY verdict (an entry is PROVEN-ALL when its whole repository is; strict):",
            *[f"    {n:4d}  {state}" for state, n in sorted(repo_states.items())],
            (
                f"    distinct repositories behind these entries: {len(repos_all)}"
                f" ({sum(1 for r in repos_all.values() if r.verdict == 'PROVEN-ALL')} PROVEN-ALL,"
                f" {sum(1 for r in repos_all.values() if r.branches_verdict == BRANCHES_PROVEN)} BRANCHES-PROVEN)"
            ),
            "  by REPOSITORY branches verdict (BRANCHES-PROVEN includes every PROVEN-ALL repository):",
            *[f"    {n:4d}  {state}" for state, n in sorted(branch_states.items())],
            "  by ENTRY head_held (this checkout's own HEAD tip is proven AND it is clean; for the checkout that holds",
            "  the repository's .git it is forced to no unless the whole repository is PROVEN-ALL; NOT a deletion verdict):",
            *[f"    {n:4d}  head_held={state}" for state, n in sorted(row_states.items())],
        ]
    lines += ["", "files: " + " ".join(f"{name}.tsv" for name in OUT_SPECS) + " real-compare.tsv (with --compare)"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_compare(path: Path, results: list[RepoResult], compare: list[Row]) -> None:
    by_path = {os.path.realpath(f.row.path): (r, f) for r in results for f in r.row_facts}
    cols = [
        "path",
        "kind",
        "reasons_in_real_tsv",
        "repo_verdict",
        "repo_branches_verdict",
        "repo_first_reason",
        "head_held",
        "row_dirty_entries",
    ]
    out = TsvOut(path, cols, LOSSLESS_COLS["real-compare"])
    for row in compare:
        hit = by_path.get(os.path.realpath(row.path))
        res, fact = hit if hit else (None, None)
        out.write(
            path=os.path.realpath(row.path),
            kind=row.kind,
            reasons_in_real_tsv=row.sweep.get("reasons", ""),
            repo_verdict=res.verdict if res else "NOT-IN-SWEEP",
            repo_branches_verdict=res.branches_verdict if res else "NOT-IN-SWEEP",
            repo_first_reason=flat(res.first_reason, 200) if res else "",
            head_held=fact.held if fact else "",
            row_dirty_entries=fact.dirty if fact and fact.dirty >= 0 else "",
        )
    out.close()


# ---------------------------------------------------------------------------------------------------------------
# driver
# ---------------------------------------------------------------------------------------------------------------


def read_rows(path: Path) -> list[Row]:
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        return [Row(r["path"], r.get("kind", ""), dict(r)) for r in reader if r.get("path")]


def analyze_all(ctx: Ctx, rows: list[Row], outs: dict[str, TsvOut] | None) -> list[RepoResult]:
    groups = group_rows(rows)
    ctx.log(f"{len(rows)} entries -> {len(groups)} distinct git common dirs")
    results = []
    for i, group in enumerate(groups, 1):
        res = timeout_result(group) if time.monotonic() > ctx.deadline else analyze_group(ctx, group)
        results.append(res)
        if outs is not None:
            write_repo(outs, res)
        if i % 10 == 0 or i == len(groups):
            ctx.log(
                f"{i}/{len(groups)} repositories; PROVEN-ALL so far {sum(r.verdict == 'PROVEN-ALL' for r in results)}"
            )
    return results


def make_ctx(args: argparse.Namespace, helper: str | None, trusted: list[str]) -> Ctx:
    def log(msg: str) -> None:
        print(f"{time.strftime('%H:%M:%S')} {msg}", file=sys.stderr, flush=True)

    global ALLOW_FILE_PROTOCOL
    ALLOW_FILE_PROTOCOL = bool(trusted)  # finding 5: a trusted directory is only reachable over git's `file` protocol
    return Ctx(
        helper=helper,
        trusted=[os.path.realpath(t) for t in trusted],
        deadline=time.monotonic() + args.deadline,
        net=Throttle(args.net_interval),
        helper_throttle=Throttle(args.helper_interval),
        log=log,
        workers=getattr(args, "helper_workers", 1),
    )


EXIT_PROVEN, EXIT_NOT_PROVEN, EXIT_USAGE, EXIT_INTERNAL = 0, 1, 64, 70
INTERNAL_ERROR_MESSAGE = "prove-remote-held: internal error; the result files are incomplete and must not be used"


class UsageParser(argparse.ArgumentParser):
    """argparse with the family's exit code for a usage error (64, like check-exit-ready), not argparse's 2."""

    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def usage_problems(args: argparse.Namespace) -> list[str]:
    """Everything wrong with the arguments, found BEFORE anything is created: a bad invocation leaves no output directory."""
    problems = []
    if args.out_dir.exists() and (not args.out_dir.is_dir() or any(args.out_dir.iterdir())):
        problems.append(f"refusing to write into non-empty or non-directory {args.out_dir}")
    for flag, path in (("--tsv", args.tsv), ("--compare", args.compare)):
        if path is None:
            continue
        try:
            has_rows = bool(read_rows(path))
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            problems.append(f"cannot read {flag} {path}: {exc}")
            continue
        if not has_rows:
            problems.append(
                f"{flag} {path} has no entries (it needs a header with a `path` column and at least one row)"
            )
    if not args.no_pr_proof and not os.access(args.helper, os.X_OK):
        problems.append(f"helper not executable: {args.helper}")
    if args.limit < 0:
        problems.append("--limit must not be negative")
    return problems


def incomplete_reasons(args: argparse.Namespace, total: int, results: list[RepoResult]) -> list[str]:
    """Why this run did not cover everything it was given. An incomplete run is never a green one."""
    reasons = []
    if args.limit and total > args.limit:
        reasons.append(f"--limit {args.limit} examined only {args.limit} of {total} sweep entries")
    timed_out = sum(1 for r in results if any(code == R_TIMEOUT for code, _ in r.reasons))
    if timed_out:
        reasons.append(f"{timed_out} repositories were not examined before the {args.deadline:.0f}s deadline")
    return reasons


def cmd_run(args: argparse.Namespace) -> int:
    out_dir = args.out_dir
    problems = usage_problems(args)
    if problems:
        for problem in problems:
            print(f"prove-remote-held: {problem}", file=sys.stderr)
        return EXIT_USAGE
    out_dir.mkdir(parents=True, exist_ok=True)
    helper = None if args.no_pr_proof else str(args.helper)
    all_rows = read_rows(args.tsv)
    compare = read_rows(args.compare) if args.compare else None
    rows = all_rows[: args.limit] if args.limit else all_rows
    started = time.monotonic()
    ctx = make_ctx(args, helper, args.trust_remote_under)
    if args.trust_remote_under:
        print(
            f"prove-remote-held: WARNING: --trust-remote-under is TEST ONLY: filesystem remotes under "
            f"{', '.join(ctx.trusted)} count as offsite, so every repository relying on one carries the gap {GAP_TRUST}",
            file=sys.stderr,
        )
    outs = open_outs(out_dir)
    try:
        results = analyze_all(ctx, rows, outs)
    except BaseException:
        for out in outs.values():  # an aborted run must read as cut short: close WITHOUT the completion row
            out.close(complete=False)
        raise
    for out in outs.values():
        out.close()
    if compare is not None:
        write_compare(out_dir / "real-compare.tsv", results, compare)
    note = f"input {args.tsv}; helper {'disabled' if helper is None else helper}; deadline {args.deadline:.0f}s"
    if args.trust_remote_under:
        note += f"; TEST-ONLY --trust-remote-under {', '.join(args.trust_remote_under)}"
    incomplete = incomplete_reasons(args, len(all_rows), results)
    write_summary(out_dir / "summary.txt", results, ctx, started, note, compare, incomplete)  # last: marks completion
    print((out_dir / "summary.txt").read_text(encoding="utf-8"))
    for reason in incomplete:
        print(f"prove-remote-held: INCOMPLETE RUN: {reason}", file=sys.stderr)
    if incomplete:
        return EXIT_INTERNAL
    if with_gaps := [r for r in results if r.verdict == "PROVEN-ALL" and r.gaps]:
        print(
            f"prove-remote-held: {len(with_gaps)} repositories are PROVEN-ALL but carry documented gaps (the `gaps` column): "
            "exit 1, only a gap-free PROVEN-ALL is a green",
            file=sys.stderr,
        )
    return EXIT_PROVEN if all(r.verdict == "PROVEN-ALL" and not r.gaps for r in results) else EXIT_NOT_PROVEN


# ---------------------------------------------------------------------------------------------------------------
# self-test: throwaway fixture repositories, one scenario per verdict
# ---------------------------------------------------------------------------------------------------------------


FAKE_SSH = r"""#!/usr/bin/env bash
# Fake ssh for the self-test: NO network. It serves the bare repositories that live under __ROOT__ over git's real ssh
# transport (upload-pack and receive-pack), so a remote can be spelled exactly like a production one:
#   github.com  /OWNER/NAME.git  -> __ROOT__/r_NAME.git
#   HOST        /abs/path        -> __ROOT__/ssh/HOST/abs/abs/path        (ssh://HOST/abs/path and HOST:/abs/path)
#   HOST        rel/path         -> __ROOT__/ssh/HOST/home/rel/path       (HOST:rel/path, relative to the login home)
root='__ROOT__'
args=()
while [ $# -gt 0 ]; do
  case "$1" in
    -G) exit 0 ;;
    -o|-p|-i|-l|-F|-E) shift 2 ;;
    -4|-6|-T|-q|-v) shift ;;
    *) args+=("$1"); shift ;;
  esac
done
n=${#args[@]}
host="${args[$((n-2))]}"
host="${host##*@}"
cmd="${args[$((n-1))]}"
service="${cmd%% *}"
service="${service#git-}"
path="${cmd#* }"
path="${path#\'}"
path="${path%\'}"
case "$host" in
  github.com) real="$root/r_$(basename "$path")" ;;
  *)
    case "$path" in
      /*) real="$root/ssh/$host/abs$path" ;;
      "~/"*) real="$root/ssh/$host/home/${path#\~/}" ;;
      *) real="$root/ssh/$host/home/$path" ;;
    esac
    ;;
esac
echo "$host $path" >> "$root/fake-ssh.log"
exec git "$service" "$real"
"""


class Checks:
    def __init__(self) -> None:
        self.failed = 0
        self.total = 0

    def expect(self, label: str, actual: object, expected: object) -> None:
        self.total += 1
        ok = actual == expected
        self.failed += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f"  expected={expected!r} actual={actual!r}"))

    def expect_in(self, label: str, needle: str, haystack: str) -> None:
        self.total += 1
        ok = needle in haystack
        self.failed += 0 if ok else 1
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f"  {needle!r} not in {haystack[:200]!r}"))


def self_test(keep: bool) -> int:
    global ALLOW_FILE_PROTOCOL
    root = Path(os.path.realpath(tempfile.mkdtemp(prefix="selftest-")))  # realpath: macOS /var is a symlink
    print(f"fixtures under {root}")
    ENV_OVERRIDES.update(
        GIT_CONFIG_GLOBAL="/dev/null",
        GIT_CONFIG_NOSYSTEM="1",
        GIT_ALLOW_PROTOCOL="file:https:http:ssh:git",
        GIT_SSH_VARIANT="ssh",
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.invalid",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.invalid",
        https_proxy=None,
        HTTPS_PROXY=None,
        http_proxy=None,
        HTTP_PROXY=None,
        all_proxy=None,
        ALL_PROXY=None,
        NO_PROXY="127.0.0.1",
    )
    chk = Checks()
    try:
        _self_test_body(root, chk)
    except Exception as exc:  # a crash is a red self-test, reported as one (the traceback stays on stderr)
        traceback.print_exc()
        chk.expect("self-test ran to the end", f"{type(exc).__name__}: {exc}"[:150], "no exception")
    finally:
        ENV_OVERRIDES.clear()
        ALLOW_FILE_PROTOCOL = False
        if not keep:
            shutil.rmtree(root, ignore_errors=True)
    print(f"self-test: {chk.total - chk.failed}/{chk.total} checks passed")
    return 0 if chk.failed == 0 and chk.total > 0 else 1


def tsv_rows(path: Path) -> tuple[list[list[str]], str]:
    """(data rows, completion row) of one result file; the completion row is the last line, `#END rows=N` first."""
    lines = path.read_text(encoding="utf-8").split("\n")  # not splitlines(): it also splits on \x85,   and friends
    if lines and lines[-1] == "":
        lines.pop()
    marker = lines[-1] if lines and lines[-1].startswith(END_MARK) else ""
    body = lines[1:-1] if marker else lines[1:]
    return [line.split("\t") for line in body], marker.split("\t")[0]


COPY_ENV = "PROVE_SELFTEST_MUTANT_COPY"  # set by prove-mutation-check.py for the self-tests of its copies


def mutation_check_state(here: Path, environ: Mapping[str, str]) -> str:
    """`present` (the script sits next to the tool), `copy` (this run is one of its mutant copies, which carry only the
    tool and its helper), or `missing`. Only a copy may skip the sub-checks that need the script; anywhere else its
    absence is a failure, never a silent skip (PS-14)."""
    if environ.get(COPY_ENV) == "1":
        return "copy"
    return "present" if (here / "prove-mutation-check.py").exists() else "missing"


def ends_properly(path: Path, cols: list[str]) -> bool:
    """Exactly one `#END rows=N` line, the last one, full width, N the number of data rows (contract 3)."""
    lines = path.read_text(encoding="utf-8").split("\n")
    if lines.pop() != "":
        return False
    ends = [i for i, ln in enumerate(lines) if ln.startswith(END_MARK)]
    if ends != [len(lines) - 1] or len(lines) < 2:
        return False
    cells = lines[-1].split("\t")
    return cells[0] == f"{END_MARK} rows={len(lines) - 2}" and len(cells) == len(cols) and set(cells[1:]) <= {END_MARK}


def tsv_header(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").split("\n", 1)[0].split("\t")


def tsv_dicts(path: Path) -> list[dict[str, str]]:
    """Data rows of a result file as {column: cell}; a row with a different cell count than the header is a failure of the
    writer (a TAB leaked out of a cell), so it is reported as a row with a single `_bad` key."""
    header = path.read_text(encoding="utf-8").split("\n", 1)[0].split("\t")
    rows, _marker = tsv_rows(path)
    return [dict(zip(header, r, strict=True)) if len(r) == len(header) else {"_bad": "\t".join(r)} for r in rows]


def live_ref_keys(repo: Path) -> dict[str, str]:
    """{key: tip} for a repository, derived from live git the way contract 2 says the predicate derives it, and written
    independently of the code under test: a full refname for every ref outside refs/remotes/ and refs/stash, `HEAD@<wt>`
    for every detached worktree, `<refname>@<wt>` for each worktree's refs/worktree|bisect|rewritten refs."""

    def lines(cwd: str, *argv: str) -> list[str]:
        rc, out, err = run(["git", *argv], timeout=60, env=base_env(), cwd=cwd)
        if rc != 0:
            raise RuntimeError(f"git {' '.join(argv)} failed in {cwd}: {err}")
        return [ln for ln in out.split("\n") if ln]

    per_worktree = ("refs/worktree/", "refs/bisect/", "refs/rewritten/")
    keys: dict[str, str] = {}
    for line in lines(str(repo), "for-each-ref", "--format=%(refname)%09%(objectname)"):
        ref, oid = line.split("\t")
        if not ref.startswith(("refs/remotes/", "refs/stash", *per_worktree)):
            keys[ref] = oid
    listing = run(["git", "worktree", "list", "--porcelain", "-z"], timeout=60, env=base_env(), cwd=str(repo))[1]
    for record in listing.split("\0\0"):
        fields = record.split("\0")
        wt = next((f.removeprefix("worktree ") for f in fields if f.startswith("worktree ")), None)
        if wt is None:
            continue
        real_wt = os.path.realpath(wt)
        head = next((f.removeprefix("HEAD ") for f in fields if f.startswith("HEAD ")), "")
        if "detached" in fields:
            keys[f"HEAD@{real_wt}"] = head
        for line in lines(
            wt, "for-each-ref", "--format=%(refname)%09%(objectname)", "refs/worktree", "refs/bisect", "refs/rewritten"
        ):
            ref, oid = line.split("\t")
            keys[f"{ref}@{real_wt}"] = oid
    return keys


def _self_test_body(root: Path, chk: Checks) -> None:
    def sh(cwd: Path, *argv: str) -> str:
        rc, out, err = run(["git", *argv], timeout=60, env=base_env(), cwd=str(cwd))
        if rc != 0:
            raise RuntimeError(f"fixture command failed in {cwd}: git {' '.join(argv)}: {err}")
        return out.strip()

    def commit(repo: Path, name: str, author: str | None = None, committer: tuple[str, str] | None = None) -> str:
        (repo / name).write_text(name + "\n", encoding="utf-8")
        sh(repo, "add", name)
        saved = {k: ENV_OVERRIDES[k] for k in ("GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")}
        if committer:
            ENV_OVERRIDES.update(GIT_COMMITTER_NAME=committer[0], GIT_COMMITTER_EMAIL=committer[1])
        try:
            sh(repo, "commit", "-q", "-m", name, *(["--author", author] if author else []))
        finally:
            ENV_OVERRIDES.update(saved)
        return sh(repo, "rev-parse", "HEAD")

    bot_author = "dependabot[bot] <49699333+dependabot[bot]@users.noreply.github.com>"
    github_committer = ("GitHub", "noreply@github.com")  # who commits a bot's work made through the GitHub API

    def make_bot(
        name: str,
        branch: str,
        author: str | None,
        remote_rewritten: bool,
        human_amend: bool = False,
        human_on_top: bool = False,
        committer: tuple[str, str] | None = None,
    ) -> tuple[Path, str]:
        """a clone whose local `branch` was pushed, then (optionally) force-pushed to another tip by a second clone,
        then (optionally) amended by a human, which keeps the bot as author, or continued by a human commit."""
        bare, work = make(name)
        sh(work, "checkout", "-q", "-b", branch)
        tip = commit(work, "b1", author, committer or (github_committer if author else None))
        if remote_rewritten:
            sh(work, "push", "-q", "origin", branch)
            second = root / f"o_{name}"
            sh(root, "clone", "-q", str(bare), str(second))
            sh(second, "checkout", "-q", branch)
            sh(second, "commit", "-q", "--amend", "-m", "rewritten by the bot")
            sh(second, "push", "-q", "--force", "origin", branch)
        if human_amend:
            (work / "b1").write_text("b1\nhuman fix that exists nowhere else\n", encoding="utf-8")
            sh(work, "commit", "-q", "-a", "--amend", "--no-edit")
            tip = sh(work, "rev-parse", "HEAD")
        if human_on_top:
            tip = commit(work, "human-follow-up")
        sh(work, "checkout", "-q", "main")
        return work, tip

    fakessh = root / "fake-ssh.sh"
    fakessh.write_text(FAKE_SSH.replace("__ROOT__", str(root)), encoding="utf-8")
    fakessh.chmod(0o755)
    ssh_command = f"'{fakessh}'"

    def make(name: str, slug: str | None = None) -> tuple[Path, Path]:
        """bare remote + a clone with main pushed. With a slug the origin becomes the real github.com ssh URL, served
        from the bare remote by the fake ssh (never an insteadOf rewrite: the slug is derived from the URL git uses)."""
        bare, work = root / f"r_{name}.git", root / f"w_{name}"
        sh(root, "init", "-q", "--bare", "-b", "main", str(bare))
        sh(root, "clone", "-q", str(bare), str(work))
        sh(work, "symbolic-ref", "HEAD", "refs/heads/main")
        commit(work, "c1")
        commit(work, "c2")
        sh(work, "push", "-q", "origin", "main")
        if slug:
            sh(work, "config", "core.sshCommand", ssh_command)
            sh(work, "remote", "set-url", "origin", f"ssh://git@github.com/{slug}.git")
        return bare, work

    # 1 allheld: exact branch, ancestor-only branch, lightweight + annotated tag, all pushed. A GitHub-style URL, because
    #   an ancestor-only branch is provable only against a remote known to hold full history (finding 3e).
    _bare, work = make("allheld", slug="fixture/allheld")
    sh(work, "checkout", "-q", "-b", "exactbr")
    commit(work, "e1")
    sh(work, "push", "-q", "origin", "exactbr")
    sh(work, "checkout", "-q", "main")
    sh(work, "branch", "anc", "main~1")
    sh(work, "tag", "v1")
    sh(work, "tag", "-a", "-m", "v2", "v2")
    sh(work, "push", "-q", "origin", "v1", "v2")
    # 2 unpushed branch
    _, w2 = make("unpushed")
    sh(w2, "checkout", "-q", "-b", "wip")
    wip_tip = commit(w2, "u1")
    # 3 squash-merged: branch feat pushed, squashed into remote main by another clone, remote branch deleted + pruned
    bare3, w3 = make("squash", slug="fixture/squash")
    sh(w3, "checkout", "-q", "-b", "feat")
    commit(w3, "s1")
    squash_tip = commit(w3, "s2")
    sh(w3, "push", "-q", "origin", "feat")
    other = root / "o_squash"
    sh(root, "clone", "-q", str(bare3), str(other))
    sh(other, "merge", "-q", "--squash", "origin/feat")
    sh(other, "commit", "-q", "-m", "squash feat")
    sh(other, "push", "-q", "origin", "main")
    sh(other, "push", "-q", "origin", ":feat")
    sh(w3, "fetch", "-q", "--prune", "origin")
    # 4 dirty: tracked modification + untracked file, everything pushed
    _, w4 = make("dirty")
    (w4 / "c1").write_text("changed\n", encoding="utf-8")
    (w4 / "untracked.txt").write_text("x\n", encoding="utf-8")
    # 5 stash
    _, w5 = make("stash")
    (w5 / "c1").write_text("stashed\n", encoding="utf-8")
    sh(w5, "stash", "push", "-q", "-m", "fixture")
    # 6 no remote
    w6 = root / "w_noremote"
    sh(root, "init", "-q", "-b", "main", str(w6))
    commit(w6, "n1")
    # 7 two remotes: topic pushed only to `backup`
    _, w7 = make("multi")
    backup = root / "r_multi_backup.git"
    sh(root, "init", "-q", "--bare", "-b", "main", str(backup))
    sh(w7, "remote", "add", "backup", str(backup))
    sh(w7, "push", "-q", "backup", "main")
    sh(w7, "checkout", "-q", "-b", "topic")
    commit(w7, "t1")
    sh(w7, "push", "-q", "backup", "topic")
    # 8 network failure + credential in the URL: tracking ref says "held", fresh listing cannot confirm. The ssh command
    #   is `false`, so the listing fails at once and offline; the host is a reserved name that is not on this machine.
    _, w8 = make("netfail")
    sh(w8, "config", "core.sshCommand", "false")
    sh(w8, "remote", "set-url", "origin", "ssh://user:SECRETTOKEN@git.example.invalid/x.git")  # allow-secret: dummy
    # 9 stale tracking ref: the remote was rewound after the clone pushed c2 (GitHub says `behind`: not an ancestor)
    bare9, w9 = make("stale", slug="fixture/stale")
    stale_tip = sh(w9, "rev-parse", "HEAD")
    sh(bare9, "update-ref", "refs/heads/main", "main~1")
    # 13 remote moved forward: dev pushed as d1, then another clone pushed d2 on top; local tracking ref is behind
    bare13, w13 = make("ff", slug="fixture/ff")
    sh(w13, "checkout", "-q", "-b", "dev")
    ff_tip = commit(w13, "d1")
    sh(w13, "push", "-q", "origin", "dev")
    other13 = root / "o_ff"
    sh(root, "clone", "-q", str(bare13), str(other13))
    sh(other13, "checkout", "-q", "dev")
    commit(other13, "d2")
    sh(other13, "push", "-q", "origin", "dev")
    # 14-16 bot-named branches: a stale bot copy the remote has since rewritten (bot author, GitHub committer, as the
    #       real ones are); a human commit on a bot-named branch that the remote also rewrote; a bot-named branch the
    #       remote has never heard of
    _w_bot, bot_tip = make_bot("bot", "dependabot/npm/foo", bot_author, remote_rewritten=True)
    make_bot("bothuman", "renovate/lock", None, remote_rewritten=True)
    make_bot("botnoref", "dependabot/pip/bar", bot_author, remote_rewritten=False)
    # 17 orphaned worktree (its admin entry pruned from the parent) and 18 a directory with an empty .git file
    wt_orphan = root / "wt_orphan"
    sh(w2, "worktree", "add", "-q", "--detach", str(wt_orphan), "main")
    shutil.rmtree(w2 / ".git" / "worktrees" / "wt_orphan")
    nogit_empty = root / "nogit_empty"
    nogit_empty.mkdir()
    (nogit_empty / ".git").write_text("", encoding="utf-8")
    # 10 detached HEAD worktree holding an unpushed commit (branch deleted afterwards)
    _, w10 = make("detunpushed")
    sh(w10, "checkout", "-q", "-b", "tmp")
    det_tip = commit(w10, "d1")
    wt10 = root / "wt_detunpushed"
    sh(w10, "worktree", "add", "-q", "--detach", str(wt10), det_tip)
    sh(w10, "checkout", "-q", "main")
    sh(w10, "branch", "-q", "-D", "tmp")
    # 11 dirty detached worktree on a pushed commit; the main checkout stays clean
    _, w11 = make("detdirty")
    wt11 = root / "wt_detdirty"
    sh(w11, "worktree", "add", "-q", "--detach", str(wt11), "main")
    (wt11 / "c1").write_text("dirty detached\n", encoding="utf-8")
    # 12 unpushed local tag on a unique commit
    _, w12 = make("tagonly")
    sh(w12, "checkout", "-q", "-b", "scratch")
    commit(w12, "g1")
    sh(w12, "tag", "local-only")
    sh(w12, "checkout", "-q", "main")
    sh(w12, "branch", "-q", "-D", "scratch")
    # 19 commits only a reflog names (finding 1): a deleted unmerged branch and a detached commit abandoned by checkout
    _, w19 = make("reflog")
    sh(w19, "checkout", "-q", "-b", "exp")
    commit(w19, "x1")
    sh(w19, "checkout", "-q", "main")
    sh(w19, "branch", "-q", "-D", "exp")
    sh(w19, "checkout", "-q", "--detach")
    commit(w19, "x2")
    sh(w19, "checkout", "-q", "main")
    # 20 work only a stale remote-tracking ref holds: pushed, local branch and remote branch deleted, never pruned, all
    #    reflogs expired so that nothing else names it
    bare20, w20 = make("trackonly")
    sh(w20, "checkout", "-q", "-b", "feat")
    track_tip = commit(w20, "f1")
    sh(w20, "push", "-q", "origin", "feat")
    sh(w20, "checkout", "-q", "main")
    sh(w20, "branch", "-q", "-D", "feat")
    sh(bare20, "update-ref", "-d", "refs/heads/feat")
    sh(w20, "reflog", "expire", "--expire=all", "--all")
    # 21 positive control for 19/20: the same shape, but the remote still has the branch (and moved on), so GitHub can
    #    say the abandoned commit is an ancestor of it
    bare21, w21 = make("rfheld", slug="fixture/rfheld")
    sh(w21, "checkout", "-q", "-b", "kept")
    rf_tip = commit(w21, "k1")
    sh(w21, "push", "-q", "origin", "kept")
    other21 = root / "o_rfheld"
    sh(root, "clone", "-q", str(bare21), str(other21))
    sh(other21, "checkout", "-q", "kept")
    commit(other21, "k2")
    sh(other21, "push", "-q", "origin", "kept")
    sh(w21, "checkout", "-q", "main")
    sh(w21, "branch", "-q", "-D", "kept")
    # 22 refs/stash whose reflog is gone: `stash list` shows nothing, the stash commit is still local-only work
    _, w22 = make("stashnolog")
    (w22 / "c1").write_text("change\n", encoding="utf-8")
    sh(w22, "stash", "push", "-q", "-m", "s")
    os.remove(w22 / ".git" / "logs" / "refs" / "stash")
    # 23 bare mirrors: one carrying refs/stash (`git stash list` fails in any bare repository), one plain
    _, w23 = make("barestashsrc")
    (w23 / "c1").write_text("change\n", encoding="utf-8")
    sh(w23, "stash", "push", "-q", "-m", "s")
    sh(root, "clone", "-q", "--mirror", str(w23), str(root / "m_barestash.git"))
    sh(root / "m_barestash.git", "remote", "set-url", "origin", str(root / "r_barestashsrc.git"))
    _, w23b = make("baremirrorsrc")
    sh(root, "clone", "-q", "--mirror", str(w23b), str(root / "m_bareplain.git"))
    sh(root / "m_bareplain.git", "remote", "set-url", "origin", str(root / "r_baremirrorsrc.git"))
    # 24 info/grafts gives a remote tip a fake extra parent (finding 3d): a local-only commit then looks "held"
    _, w24 = make("grafts", slug="fixture/grafts")
    head24, parent24 = sh(w24, "rev-parse", "main"), sh(w24, "rev-parse", "main~1")
    sh(w24, "checkout", "-q", "-b", "loc", "main~1")
    graft_tip = commit(w24, "graft-only")
    sh(w24, "checkout", "-q", "main")
    (w24 / ".git" / "info").mkdir(exist_ok=True)
    (w24 / ".git" / "info" / "grafts").write_text(f"{head24} {parent24} {graft_tip}\n", encoding="utf-8")
    # 25 the same lie through a refs/replace object (GIT_NO_REPLACE_OBJECTS)
    _, w25 = make("replace", slug="fixture/replace")
    sh(w25, "checkout", "-q", "-b", "loc", "main~1")
    replace_tip = commit(w25, "replace-only")
    sh(w25, "checkout", "-q", "main")
    sh(w25, "replace", "--graft", "main", "main~1", replace_tip)
    # 26 an annotated tag that exists only here, on a commit the remote holds (finding 3a)
    _, w26 = make("annot", slug="fixture/annot")
    sh(w26, "tag", "-a", "-m", "release notes written only here", "v9")
    # 27 a human amended a stale bot branch: the author stays the bot, the committer does not (finding 3b)
    _, botamend_tip = make_bot(
        "botamend", "dependabot/npm/amended", bot_author, remote_rewritten=True, human_amend=True
    )
    #    a stale copy of a branch that is NOT bot-named, whatever its author
    _, botname_tip = make_bot("botname", "feature/bumps", bot_author, remote_rewritten=True)
    # 28 the remote is a shallow repository: it advertises main but not the history behind it (finding 3e)
    w28 = root / "w_shallowsrc"
    sh(root, "init", "-q", "-b", "main", str(w28))
    commit(w28, "c1")
    sh(w28, "branch", "old")
    commit(w28, "c2")
    commit(w28, "c3")
    sh(root, "clone", "-q", "--bare", "--depth", "1", f"file://{w28}", str(root / "r_shallowsrc.git"))
    sh(w28, "remote", "add", "origin", str(root / "r_shallowsrc.git"))
    # 29 a GitHub ssh URL whose listing fails (offline: the ssh command is `false`): the GitHub helper alone never
    #    proves (finding 4c)
    _, w29 = make("ghonly")
    sh(w29, "config", "core.sshCommand", "false")
    sh(w29, "remote", "set-url", "origin", "ssh://git@github.com/fixture/ghonly.git")
    # 30 refs/notes that exist only here
    _, w30 = make("notes")
    sh(w30, "notes", "add", "-m", "review notes only here", "HEAD")
    # 31 a linked worktree detached on a local-only commit whose directory was then deleted (git still lists it)
    _, w31 = make("prunable")
    wt31 = root / "wt_prunable"
    sh(w31, "worktree", "add", "-q", "--detach", str(wt31), "main")
    prunable_tip = commit(wt31, "p1")
    shutil.rmtree(wt31)
    # 32 a clean, held linked worktree in a repository that is UNPROVEN (unpushed branch): its own HEAD is held, the
    #    main checkout (which holds .git) is not deletable (finding 2)
    _, w32 = make("linkclean")
    sh(w32, "checkout", "-q", "-b", "wip")
    commit(w32, "k1")
    sh(w32, "checkout", "-q", "main")
    wt32 = root / "wt_linkclean"
    sh(w32, "worktree", "add", "-q", "--detach", str(wt32), "main")
    # 33 submodules (finding 3c): the superproject is pushed in both; the submodule's recorded commit is pushed in one
    bare_sub = root / "r_sub.git"
    sh(root, "init", "-q", "--bare", "-b", "main", str(bare_sub))
    sub_seed = root / "o_sub_seed"
    sh(root, "clone", "-q", str(bare_sub), str(sub_seed))
    sh(sub_seed, "symbolic-ref", "HEAD", "refs/heads/main")
    commit(sub_seed, "s1")
    sh(sub_seed, "push", "-q", "origin", "main")
    for name in ("subheld", "sublocal"):
        _, w33 = make(name)
        sh(w33, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(bare_sub), "sub")
        sh(w33, "commit", "-q", "-m", "add sub")
        if name == "sublocal":
            commit(w33 / "sub", "s2-local-only")
            sh(w33, "add", "sub")
            sh(w33, "commit", "-q", "-m", "bump sub to a commit only this machine has")
        sh(w33, "push", "-q", "origin", "main")
    # 34 alternates (finding 4e): a borrower whose lender holds unpushed work, and one whose lender holds nothing
    for name in ("bad", "ok"):
        lender_bare, lender = make(f"lend{name}")
        if name == "bad":
            sh(lender, "checkout", "-q", "-b", "wip")
            commit(lender, "lender-only")
            sh(lender, "checkout", "-q", "main")
        borrower = root / f"w_borrow{name}"
        sh(root, "clone", "-q", "--shared", str(lender), str(borrower))
        sh(borrower, "remote", "set-url", "origin", str(lender_bare))
        sh(borrower, "fetch", "-q", "--prune", "origin")
    # 35 git-lfs content in the repository's own lfs store (finding 4e)
    _, w35 = make("lfs")
    (w35 / ".git" / "lfs" / "objects" / "ab" / "cd").mkdir(parents=True)
    (w35 / ".git" / "lfs" / "objects" / "ab" / "cd" / ("0" * 64)).write_text("pointer target\n", encoding="utf-8")
    # 36 files edited behind skip-worktree / assume-unchanged, which `git status` never shows (finding 5), and the same
    #    bits on files that were not edited (a sparse checkout)
    _, w36 = make("hidden")
    sh(w36, "update-index", "--skip-worktree", "c1")
    sh(w36, "update-index", "--assume-unchanged", "c2")
    (w36 / "c1").write_text("c1\nedited behind skip-worktree\n", encoding="utf-8")
    (w36 / "c2").write_text("c2\nedited behind assume-unchanged\n", encoding="utf-8")
    _, w36b = make("sparse")
    sh(w36b, "update-index", "--skip-worktree", "c1")
    sh(w36b, "update-index", "--assume-unchanged", "c2")
    # 37 a human commit on top of a bot commit on a stale bot branch; a human commit made through the GitHub web UI
    #    (author a person, committer GitHub) on a bot-named branch
    make_bot("botmixed", "dependabot/npm/mixed", bot_author, remote_rewritten=True, human_on_top=True)
    make_bot("botweb", "renovate/web", None, remote_rewritten=True, committer=github_committer)
    # 38 a remote-only branch fetched here with no local branch: its tracking ref is the remote's own advertised SHA
    bare38, w38 = make("trackheld")
    other38 = root / "o_trackheld"
    sh(root, "clone", "-q", str(bare38), str(other38))
    sh(other38, "checkout", "-q", "-b", "side")
    commit(other38, "side1")
    sh(other38, "push", "-q", "origin", "side")
    sh(w38, "fetch", "-q", "origin")
    # 39 abandoned work on a GitHub-style remote that never had it: the helper is consulted and says no
    _, w39 = make("rfnone", slug="fixture/rfnone")
    sh(w39, "checkout", "-q", "-b", "gone")
    rfnone_tip = commit(w39, "g1")
    sh(w39, "checkout", "-q", "main")
    sh(w39, "branch", "-q", "-D", "gone")
    # 40 / 41 abandoned work the remote's branches have since moved past: a chain of two commits behind one head, and
    #        two independent heads (the lookup cap is lowered to 1 where these are analysed)
    for name, branches in (("rfchain", ("chain",)), ("rfpair", ("p", "q"))):
        bare40, w40 = make(name, slug=f"fixture/{name}")
        for branch in branches:
            sh(w40, "checkout", "-q", "-b", branch, "main")
            commit(w40, f"{branch}1")
            if name == "rfchain":
                commit(w40, f"{branch}2")
            sh(w40, "push", "-q", "origin", branch)
            other40 = root / f"o_{name}_{branch}"
            sh(root, "clone", "-q", str(bare40), str(other40))
            sh(other40, "checkout", "-q", branch)
            commit(other40, f"{branch}-on-top")
            sh(other40, "push", "-q", "origin", branch)
            sh(w40, "checkout", "-q", "main")
            sh(w40, "branch", "-q", "-D", branch)
    # 42 HEAD-reflog-only work in two linked worktrees, one of them since deleted from disk
    _, w42 = make("wtlog")
    for wt_name in ("wt_wtlive", "wt_wtgone"):
        wt_path = root / wt_name
        sh(w42, "worktree", "add", "-q", "--detach", str(wt_path), "main")
        commit(wt_path, f"{wt_name}-only")
        sh(wt_path, "checkout", "-q", "--detach", "main")
    shutil.rmtree(root / "wt_wtgone")
    # 43 join keys (contract 1): a path with consecutive spaces (pushed, and holding a local-only annotated tag), and paths
    #    the TSV cannot carry (`;` is the list separator, TAB / LF break the row), and a checkout reached by a symlink
    make("spaced  ok")
    _, w43 = make("spaced  tag")
    sh(w43, "tag", "-a", "-m", "only here", "local-note")
    make("semi;colon")
    make("tab\tin-name")
    make("lf\nin-name")
    _, w_real = make("symreal")
    shutil.move(str(w_real), str(root / "real_sym"))
    os.symlink(root / "real_sym", root / "w_symlinked")

    def orphan(repo: Path, msg: str) -> str:
        """a commit nothing points at yet: no branch, no HEAD, no reflog entry, only what the caller pins it with"""
        return sh(repo, "commit-tree", sh(repo, "write-tree"), "-p", sh(repo, "rev-parse", "HEAD"), "-m", msg)

    # 44 per-worktree refs (P3): a ref under refs/worktree/ or refs/bisect/ is private to ONE worktree, has no reflog by
    #    default, and a listing from another worktree (or `rev-list --all`) never shows it
    _, w44 = make("wtref")
    wt44 = root / "wt_wtref"
    sh(w44, "worktree", "add", "-q", "--detach", str(wt44), "main")
    wtref_tip = orphan(wt44, "only under refs/worktree/keep of the linked worktree")
    sh(wt44, "update-ref", "refs/worktree/keep", wtref_tip)
    _, w44b = make("wtref2")
    wt44b = root / "wt_wtref2"
    sh(w44b, "worktree", "add", "-q", "--detach", str(wt44b), "main")
    wtref2_tip = orphan(w44b, "only under refs/worktree/keep of the MAIN worktree")
    sh(w44b, "update-ref", "refs/worktree/keep", wtref2_tip)
    _, w44c = make("bisect")
    wt44c = root / "wt_bisect"
    sh(w44c, "worktree", "add", "-q", "--detach", str(wt44c), "main")
    bisect_tip = orphan(wt44c, "marked bad in a bisect running in a side worktree")
    sh(wt44c, "update-ref", "refs/bisect/bad", bisect_tip)
    #    positive control: per-worktree refs that point at pushed work are proven like any other tip
    _, w44d = make("wtheld")
    wt44d = root / "wt_wtheld"
    sh(w44d, "worktree", "add", "-q", "--detach", str(wt44d), "main")
    sh(w44d, "update-ref", "refs/worktree/pin", "main")
    sh(wt44d, "update-ref", "refs/bisect/good", "main")

    # 45 two remotes that differ only in how the path is spelled (P1): `host:data.git` is ~/data.git, relative to the login
    #    home; `ssh://host/data.git` is /data.git. They are two repositories and one listing must never answer for the other.
    srv = root / "ssh" / "srv.example.com"
    home_bare, abs_bare = srv / "home" / "data.git", srv / "abs" / "data.git"
    for bare45 in (home_bare, abs_bare):
        bare45.parent.mkdir(parents=True)
        sh(root, "init", "-q", "--bare", "-b", "main", str(bare45))
    w45a = root / "w_collideA"
    sh(root, "clone", "-q", str(home_bare), str(w45a))
    sh(w45a, "symbolic-ref", "HEAD", "refs/heads/main")
    commit(w45a, "d1")
    sh(w45a, "push", "-q", "origin", "main")
    sh(w45a, "push", "-q", str(abs_bare), "main")  # /data.git gets d1 only
    collide_tip = commit(w45a, "d2-held-only-in-the-home-copy")
    sh(w45a, "push", "-q", "origin", "main")  # ~/data.git gets d2 too
    sh(w45a, "remote", "set-url", "origin", "srv.example.com:data.git")
    sh(w45a, "config", "core.sshCommand", ssh_command)
    w45b = root / "w_collideB"
    sh(root, "clone", "-q", str(w45a), str(w45b))  # B has d2 locally, and its remote is /data.git, which lacks it
    sh(w45b, "remote", "remove", "origin")
    sh(w45b, "remote", "add", "origin", "ssh://srv.example.com/data.git")
    sh(w45b, "config", "core.sshCommand", ssh_command)
    # 46 insteadOf rewrites a github.com URL to a NON-GitHub mirror that is a shallow repository (P2): the full-history
    #    ancestor rule is only valid for GitHub itself, so the slug must come from the URL git actually uses
    src46 = root / "o_mirror_src"
    sh(root, "init", "-q", "-b", "main", str(src46))
    old46 = commit(src46, "m1")
    commit(src46, "m2")
    commit(src46, "m3")
    mirror = root / "ssh" / "mirror.example.com" / "abs" / "srv" / "mirror.git"
    mirror.parent.mkdir(parents=True)
    sh(root, "clone", "-q", "--bare", "--depth", "1", f"file://{src46}", str(mirror))
    w46 = root / "w_mirror"
    sh(root, "clone", "-q", str(src46), str(w46))
    sh(w46, "branch", "old", old46)
    sh(w46, "remote", "set-url", "origin", "https://github.com/fixture/mirror.git")
    sh(w46, "config", "url.ssh://git@mirror.example.com/srv/.insteadOf", "https://github.com/fixture/")
    sh(w46, "config", "core.sshCommand", ssh_command)
    # 47 a github.com URL that insteadOf points at a LOCAL bare: not a GitHub remote, never reaches the helper
    bare47, w47 = make("insteadlocal")
    sh(w47, "config", f"url.{bare47}.insteadOf", "https://github.com/fixture/insteadlocal.git")
    sh(w47, "remote", "set-url", "origin", "https://github.com/fixture/insteadlocal.git")

    # 48 SHA-256 repositories (P5): every object id is 64 hex. A bare mirror holding a local-only branch, a pushed clone, and
    #    a clone with a stash
    bare48 = root / "r_sha256.git"
    sh(root, "init", "-q", "--bare", "--object-format=sha256", "-b", "main", str(bare48))
    w48 = root / "w_sha256"
    sh(root, "clone", "-q", str(bare48), str(w48))
    sh(w48, "symbolic-ref", "HEAD", "refs/heads/main")
    commit(w48, "z1")
    sh(w48, "tag", "-a", "-m", "sha256 tag", "z-tag")
    sh(w48, "push", "-q", "origin", "main", "z-tag")
    mirror48 = root / "m_sha256.git"
    sh(root, "clone", "-q", "--mirror", str(bare48), str(mirror48))
    only48 = sh(
        mirror48, "commit-tree", sh(mirror48, "rev-parse", "main^{tree}"), "-p", "main", "-m", "only in the mirror"
    )
    sh(mirror48, "update-ref", "refs/heads/unpushed", only48)
    w48s = root / "w_sha256stash"
    sh(root, "clone", "-q", str(bare48), str(w48s))
    (w48s / "z1").write_text("stashed change\n", encoding="utf-8")
    sh(w48s, "stash", "push", "-q", "-m", "s")

    # 49 documented gaps (contract 4). A GitHub origin proves every tip, while a second NON-GitHub remote advertises a commit
    #    that exists here only as a tracking ref: the sweep excludes it on that remote's word that its history is complete
    _, w49 = make("sweepgap", slug="fixture/sweepgap")
    backup49 = root / "ssh" / "backup.example.com" / "home" / "data.git"
    backup49.parent.mkdir(parents=True)
    sh(root, "init", "-q", "--bare", "-b", "main", str(backup49))
    sh(w49, "push", "-q", str(backup49), "main")
    other49 = root / "o_sweepgap"
    sh(root, "clone", "-q", str(backup49), str(other49))
    sh(other49, "checkout", "-q", "-b", "extra")
    commit(other49, "x1")
    sh(other49, "push", "-q", "origin", "extra")
    sh(w49, "remote", "add", "backup", "backup.example.com:data.git")
    sh(w49, "fetch", "-q", "backup")
    #    control: the same non-GitHub backup holds nothing the GitHub remote does not, and the tips are proven by GitHub first
    _, w49b = make("dualhold", slug="fixture/dualhold")
    backup49b = root / "ssh" / "dual.example.com" / "home" / "data.git"
    backup49b.parent.mkdir(parents=True)
    sh(root, "init", "-q", "--bare", "-b", "main", str(backup49b))
    sh(w49b, "push", "-q", str(backup49b), "main")
    sh(w49b, "remote", "add", "backup", "dual.example.com:data.git")
    # 50 a submodule whose own remote is a trusted local path under a superproject that GitHub proves by itself (the gap
    #    belongs to the superproject), and a shallow NON-GitHub remote while this machine holds the history behind its tip
    _, w50 = make("subgap", slug="fixture/subgap")
    sh(w50, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(bare_sub), "sub")
    sh(w50, "commit", "-q", "-m", "add sub")
    sh(w50, "push", "-q", "origin", "main")
    src50 = root / "o_shtip_src"
    sh(root, "init", "-q", "-b", "main", str(src50))
    for n in ("s1", "s2", "s3"):
        commit(src50, n)
    shallow = root / "ssh" / "shallow.example.com" / "abs" / "srv" / "shtip.git"
    shallow.parent.mkdir(parents=True)
    sh(root, "clone", "-q", "--bare", "--depth", "1", f"file://{src50}", str(shallow))
    w50b = root / "w_shtip"
    sh(root, "clone", "-q", str(src50), str(w50b))
    sh(w50b, "remote", "set-url", "origin", "ssh://shallow.example.com/srv/shtip.git")
    sh(w50b, "config", "core.sshCommand", ssh_command)
    # 51 a bare repository that DOES keep reflogs (the control for BARE-NO-REFLOG)
    _, w51 = make("barelogsrc")
    sh(root, "clone", "-q", "--mirror", str(w51), str(root / "m_barelog.git"))
    sh(root / "m_barelog.git", "remote", "set-url", "origin", str(root / "r_barelogsrc.git"))
    sh(root / "m_barelog.git", "config", "core.logAllRefUpdates", "true")
    sh(root / "m_barelog.git", "update-ref", "refs/heads/touched", "main")

    # 52 a file edited behind skip-worktree INSIDE a submodule (P4): the superproject's `git status` shows nothing, so the
    #    probe of the submodule must look in the submodule's checkout, not in its git dir
    _, w52 = make("subskip")
    sh(w52, "-c", "protocol.file.allow=always", "submodule", "add", "-q", str(bare_sub), "sub")
    sh(w52, "commit", "-q", "-m", "add sub")
    sh(w52, "push", "-q", "origin", "main")
    sh(w52 / "sub", "update-index", "--skip-worktree", "s1")
    (w52 / "sub" / "s1").write_text("s1\nedited behind skip-worktree inside the submodule\n", encoding="utf-8")
    # 53 the same edit in a LINKED worktree (P8): its HEAD is held and `git status` is clean, but deleting it loses the edit
    _, w53 = make("wthidden")
    wt53 = root / "wt_wthidden"
    sh(w53, "worktree", "add", "-q", "--detach", str(wt53), "main")
    sh(wt53, "update-index", "--skip-worktree", "c1")
    (wt53 / "c1").write_text("c1\nedited behind skip-worktree in the linked worktree\n", encoding="utf-8")
    sh(root, "init", "-q", "-b", "main", str(root / "u_unborn"))

    # 54 large-file stores outside <git dir>/lfs/objects (P9): lfs.storage relocated (absolute, and relative to the git
    #    dir), a relocated store that is empty (the control), and git-annex content
    _, w54 = make("lfsstore")
    store = root / "lfs-elsewhere"
    (store / "objects" / "ab" / "cd").mkdir(parents=True)
    (store / "objects" / "ab" / "cd" / ("abcd" + "0" * 60)).write_text("large local-only content\n", encoding="utf-8")
    sh(w54, "config", "lfs.storage", str(store))
    _, w54b = make("lfsrel")
    (w54b / ".git" / "custom-lfs" / "objects" / "ab" / "cd").mkdir(parents=True)
    (w54b / ".git" / "custom-lfs" / "objects" / "ab" / "cd" / ("abcd" + "0" * 60)).write_text("x\n", encoding="utf-8")
    sh(w54b, "config", "lfs.storage", "custom-lfs")
    _, w54c = make("lfsempty")
    (root / "lfs-empty" / "objects").mkdir(parents=True)
    sh(w54c, "config", "lfs.storage", str(root / "lfs-empty"))
    _, w54d = make("annex")
    annex_dir = w54d / ".git" / "annex" / "objects" / "Xx" / "Yy" / "SHA256E-s6--feed.txt"
    annex_dir.mkdir(parents=True)
    (annex_dir / "SHA256E-s6--feed.txt").write_text("annex\n", encoding="utf-8")

    # 55 reflogs that cannot enumerate abandoned commits in a NON-bare repository (G1). The abandoned commit is made with
    #    plumbing and never checked out, so no HEAD reflog names it either: core.logAllRefUpdates=false, and a repository
    #    whose reflog files were removed. The control keeps reflogs for every ref.
    dangling55 = {}
    for name, how in (("nolog", "config"), ("nologdir", "dir"), ("logalways", "always")):
        _, w55 = make(name)
        if how == "config":
            sh(w55, "config", "core.logAllRefUpdates", "false")
        elif how == "dir":
            shutil.rmtree(w55 / ".git" / "logs")
        else:
            sh(w55, "config", "core.logAllRefUpdates", "always")
        dangling55[name] = sh(w55, "commit-tree", sh(w55, "rev-parse", "main^{tree}"), "-p", "main", "-m", "abandoned")
        sh(w55, "update-ref", "refs/heads/gone", dangling55[name])
        sh(w55, "update-ref", "-d", "refs/heads/gone")

    def stub(name: str, body: str) -> str:
        path = root / name
        path.write_text(f"#!/usr/bin/env bash\necho \"$1 $2\" >> '{root}/helper.log'\n{body}\n", encoding="utf-8")
        path.chmod(0o755)
        return str(path)

    # An oracle that answers like GitHub would, from the local bare remotes: ancestry of the candidate branches / main,
    # then a merged-PR list. It is the ground truth the Python is held to (so a rewound remote answers NONE).
    (root / "merged-prs.txt").write_text(f"fixture/squash {squash_tip}\n", encoding="utf-8")
    oracle = root / "stub-oracle.sh"
    oracle.write_text(
        "#!/usr/bin/env bash\n"
        f"root='{root}'\n"
        'echo "$*" >> "$root/helper.log"\n'
        'slug="$1"; sha="$2"; shift 3\n'
        'bare="$root/r_${slug#fixture/}.git"\n'
        'for b in "$@" main; do\n'
        '  if git -C "$bare" merge-base --is-ancestor "$sha" "refs/heads/$b" 2>/dev/null; then\n'
        '    printf "ANCESTOR\\t%s\\t%s\\t%s\\tmain\\n" "$slug" "$sha" "$b"; exit 0\n'
        "  fi\n"
        "done\n"
        'if grep -qx "$slug $sha" "$root/merged-prs.txt" 2>/dev/null; then\n'
        '  printf "PROVEN\\t%s\\t%s\\t7\\t%s\\tmain\\n" "$slug" "$sha" "$(git -C "$bare" rev-parse refs/heads/main)"; exit 0\n'
        "fi\n"
        'printf "NONE\\t%s\\t%s\\tno-proof\\tmain\\n" "$slug" "$sha"; exit 1\n',
        encoding="utf-8",
    )
    oracle.chmod(0o755)
    s_oracle = str(oracle)

    s_proven = stub("stub-proven.sh", 'printf "PROVEN\\t%s\\t%s\\t7\\t%s\\tmain\\n" "$1" "$2" "' + "b" * 40 + '"')
    s_proven_rc = stub(
        "stub-proven-rc.sh", 'printf "PROVEN\\t%s\\t%s\\t7\\t%s\\tmain\\n" "$1" "$2" "' + "b" * 40 + '"; exit 2'
    )
    s_none = stub("stub-none.sh", 'printf "NONE\\t%s\\t%s\\tno-merged-pr\\n" "$1" "$2"; exit 1')
    s_error = stub("stub-error.sh", 'printf "ERROR\\t%s\\t%s\\tgh: rate limited\\n" "$1" "$2"; exit 2')
    s_wrong = stub("stub-wrongsha.sh", 'printf "PROVEN\\t%s\\t' + "a" * 40 + "\\t7\\t" + "b" * 40 + '\\tmain\\n" "$1"')

    s_badbranch = stub("stub-badbranch.sh", 'printf "ANCESTOR\\t%s\\t%s\\tevil\\tmain\\n" "$1" "$2"')

    rows = [Row(str(p), "repo", {}) for p in sorted(root.glob("w_*"))]
    rows += [Row(str(p), "repo", {}) for p in sorted(root.glob("m_*.git"))]
    # linked worktrees swept as rows of a repository that is already listed above
    linked = [wt10, wt11, wt32, wt44, wt44c, wt44d, wt53]
    rows += [Row(str(wt), "worktree", {}) for wt in linked]
    rows.append(Row(str(wt_orphan), "worktree", {}))
    rows.append(Row(str(nogit_empty), "repo", {}))
    rows.append(Row(str(root / "vanished"), "repo", {"dirty": "3", "unpushed": "0", "stashes": "0", "remote": "NONE"}))
    args = argparse.Namespace(deadline=300.0, net_interval=0.0, helper_interval=0.0, helper_workers=3)

    def analyze_list(helper: str | None, trusted: list[str], chosen: list[Row]) -> dict[str, RepoResult]:
        log = root / "helper.log"
        log.write_text("", encoding="utf-8")
        ctx = make_ctx(args, helper, trusted)
        ctx.log = lambda _m: None
        results = analyze_all(ctx, chosen, None)
        return {Path(r.repo).name if not r.common_dir.startswith("MISSING") else "vanished": r for r in results}

    def analyze(helper: str | None, trusted: list[str], only: tuple[str, ...] | None = None) -> dict[str, RepoResult]:
        return analyze_list(helper, trusted, [r for r in rows if only is None or Path(r.path).name in only])

    def faulted(
        where: str,
        fails: Callable[[tuple[str, ...]], bool],
        only: tuple[str, ...],
        reply: tuple[int, str, str] = (128, "", "fatal: injected fault"),
    ) -> dict[str, RepoResult]:
        """Analyze `only` with every git call whose repository path contains `where` and whose arguments `fails` accepts
        answering `reply` (default rc 128): the tool must read an unreadable listing as UNPROVEN, never as an empty one."""
        real = globals()["git"]

        def failing(path: str, *git_args: str, **kw: object) -> tuple[int, str, str]:
            if where in path and fails(git_args):
                return reply
            return real(path, *git_args, **kw)

        globals()["git"] = failing
        try:
            return analyze(s_oracle, [str(root)], only)
        finally:
            globals()["git"] = real

    print("pass 1: trusted fixture remotes; the GitHub oracle answers from the bare remotes")
    res = analyze(s_oracle, [str(root)])
    chk.expect(
        "entries -> repositories (every linked worktree row shares its repository's common dir)",
        len(res),
        len(rows) - len(linked),
    )
    chk.expect("allheld verdict", res["w_allheld"].verdict, "PROVEN-ALL")
    a = res["w_allheld"]
    chk.expect(
        "allheld branches exact/ancestor",
        (a.count("branch"), a.count("branch", EXACT), a.count("branch", ANCESTOR)),
        (3, 2, 1),
    )
    chk.expect("allheld tags (lightweight + annotated) all exact", (a.count("tag"), a.count("tag", EXACT)), (2, 2))
    chk.expect(
        "allheld: nothing to preserve is not scope=partial (finding 5)",
        (a.scope, a.reasons),
        ("nothing-to-preserve", []),
    )
    chk.expect(
        "unpushed is UNPROVEN-TIP-NOT-HELD",
        (res["w_unpushed"].verdict, res["w_unpushed"].reasons[0][0]),
        ("UNPROVEN", R_NOT_HELD),
    )
    unpushed_tip = next(t for t in res["w_unpushed"].tips if t.name == "wip")
    chk.expect(
        "unpushed tip is the wip commit and is not proven",
        (unpushed_tip.sha == wip_tip, unpushed_tip.proven),
        (True, False),
    )
    s = res["w_squash"]
    st = next(t for t in s.tips if t.name == "feat")
    chk.expect(
        "squash-merged branch proven by merged PR (oracle)", (st.status, st.sha == squash_tip), (MERGED_PR, True)
    )
    chk.expect("squash fixture verdict PROVEN-ALL", s.verdict, "PROVEN-ALL")
    ff = res["w_ff"]
    dev = next(t for t in ff.tips if t.name == "dev")
    chk.expect(
        "tracking ref behind a remote that moved forward: ancestor of the remote branch via GitHub compare",
        (dev.sha == ff_tip, dev.status, dev.evidence, ff.verdict),
        (True, ANCESTOR, "github-compare: fixture/ff:dev", "PROVEN-ALL"),
    )
    stale_tip_ref = next(t for t in res["w_stale"].tips if t.name == "main")
    chk.expect(
        "rewound remote: GitHub says the tip is not an ancestor, so a stale tracking ref still proves nothing",
        (stale_tip_ref.sha == stale_tip, stale_tip_ref.status),
        (True, R_NOT_HELD),
    )
    helper_log = sorted(
        line
        for line in (root / "helper.log").read_text(encoding="utf-8").splitlines()
        if line.strip() and line.split()[0] in {"fixture/ff", "fixture/squash", "fixture/stale"}
    )
    chk.expect(
        "helper asked only about unproven tips, with slug, exact tip, default placeholder and candidate branches",
        helper_log,
        sorted([f"fixture/ff {ff_tip} - dev", f"fixture/squash {squash_tip} -", f"fixture/stale {stale_tip} - main"]),
    )
    d = res["w_dirty"]
    chk.expect(
        "dirty: 2 entries, all refs proven, verdict UNPROVEN-DIRTY",
        (d.dirty_entries, d.count("branch", "UNPROVEN"), d.reasons[0][0]),
        (2, 0, R_DIRTY),
    )
    chk.expect(
        "stash: UNPROVEN-STASH only", (res["w_stash"].stashes, [c for c, _ in res["w_stash"].reasons]), (1, [R_STASH])
    )
    chk.expect("no remote: UNPROVEN-NO-REMOTE", res["w_noremote"].reasons[0][0], R_NO_REMOTE)
    m = res["w_multi"]
    topic = next(t for t in m.tips if t.name == "topic")
    chk.expect(
        "multi-remote: topic pushed only to backup is EXACT via backup",
        (m.verdict, topic.status, topic.evidence.startswith("backup:")),
        ("PROVEN-ALL", EXACT, True),
    )
    nf = res["w_netfail"]
    chk.expect(
        "network failure is UNPROVEN-NETWORK even though a tracking ref exists",
        (nf.verdict, nf.reasons[0][0]),
        ("UNPROVEN", R_NETWORK),
    )
    chk.expect(
        "network failure marks the branch tips UNPROVEN-NETWORK",
        {t.status for t in nf.tips if t.kind == "branch"},
        {R_NETWORK},
    )
    sl = res["w_stale"]
    chk.expect(
        "stale tracking ref does not prove (remote was rewound)",
        (sl.verdict, sl.reasons[0][0]),
        ("UNPROVEN", R_NOT_HELD),
    )
    chk.expect_in("stale tracking ref is named as the reason", "stale tracking ref", sl.first_reason)
    du = res["w_detunpushed"]
    dtip = next(t for t in du.tips if t.kind == "detached")
    chk.expect("detached HEAD worktree commit is a tip and unproven", (dtip.sha == det_tip, dtip.proven), (True, False))
    dd = res["w_detdirty"]
    dirty_by_wt = {Path(w.path).name: w.dirty for w in dd.worktrees}
    chk.expect(
        "dirty detached worktree: per-worktree dirt kept separate", dirty_by_wt, {"w_detdirty": 0, "wt_detdirty": 1}
    )
    chk.expect(
        "dirty detached worktree: refs proven, verdict UNPROVEN-DIRTY",
        (dd.count("detached", "UNPROVEN"), dd.reasons[0][0]),
        (0, R_DIRTY),
    )
    held = {Path(f.row.path).name: f.held for f in dd.row_facts}
    chk.expect(
        "row-level held: the dirty worktree is no, and so is the clean main checkout of an UNPROVEN repository",
        held,
        {"w_detdirty": "no", "wt_detdirty": "no"},  # was yes for w_detdirty before finding 2
    )
    lk = {Path(f.row.path).name: f.held for f in res["w_linkclean"].row_facts}
    chk.expect(
        "head_held: in an UNPROVEN repository the main checkout is no but a clean held linked worktree stays yes",
        (res["w_linkclean"].verdict, lk),
        ("UNPROVEN", {"w_linkclean": "no", "wt_linkclean": "yes"}),
    )
    chk.expect(
        "head_held: the main checkout of a PROVEN-ALL repository is yes",
        {Path(f.row.path).name: f.held for f in res["w_allheld"].row_facts},
        {"w_allheld": "yes"},
    )
    tg = res["w_tagonly"]
    tag = next(t for t in tg.tips if t.kind == "tag")
    chk.expect(
        "unpushed local tag is unproven and blocks PROVEN-ALL",
        (tag.name, tag.proven, tg.verdict),
        ("refs/tags/local-only", False, "UNPROVEN"),
    )
    chk.expect(
        "vanished path is UNPROVEN-VANISHED, never PROVEN",
        (res["vanished"].verdict, res["vanished"].reasons[0][0], res["vanished"].row_facts[0].held),
        ("UNPROVEN", R_VANISHED, "vanished"),
    )
    bot = res["w_bot"]
    bot_ref = next(t for t in bot.tips if t.name == "dependabot/npm/foo")
    chk.expect(
        "stale bot branch (remote rewrote it; bot author, GitHub committer): SUPERSEDED, repo stays PROVEN-ALL",
        (bot_ref.sha == bot_tip, bot_ref.status, bot.verdict, bot.branches_verdict, bot.count("branch", "UNPROVEN")),
        (True, SUPERSEDED, "PROVEN-ALL", BRANCHES_PROVEN, 0),
    )
    bh = res["w_bothuman"]
    chk.expect(
        "human commit on a renovate/* branch the remote also rewrote is real work: still UNPROVEN",
        (bh.verdict, bh.branches_verdict, [t.status for t in bh.tips if t.name == "renovate/lock"]),
        ("UNPROVEN", "UNPROVEN", [R_NOT_HELD]),
    )
    bn = res["w_botnoref"]
    chk.expect(
        "bot-named branch the remote never had is not superseded: UNPROVEN",
        (bn.verdict, [t.status for t in bn.tips if t.name == "dependabot/pip/bar"]),
        ("UNPROVEN", [R_NOT_HELD]),
    )
    ba = res["w_botamend"]
    amended = next(t for t in ba.tips if t.name == "dependabot/npm/amended")
    chk.expect(
        "finding 3b: a human `commit --amend` of a bot commit keeps the bot as author but is not a stale copy",
        (amended.sha == botamend_tip, amended.status, ba.verdict),
        (True, R_NOT_HELD, "UNPROVEN"),
    )
    bnm = res["w_botname"]
    renamed = next(t for t in bnm.tips if t.name == "feature/bumps")
    chk.expect(
        "a bot-authored stale copy on a branch that is not bot-named is not superseded",
        (renamed.sha == botname_tip, renamed.status, bnm.verdict),
        (True, R_NOT_HELD, "UNPROVEN"),
    )
    chk.expect(
        "branches verdict: held up only by a local-only tag is BRANCHES-PROVEN while PROVEN-ALL stays UNPROVEN",
        (res["w_tagonly"].verdict, res["w_tagonly"].branches_verdict),
        ("UNPROVEN", BRANCHES_PROVEN),
    )
    chk.expect(
        "branches verdict: PROVEN-ALL repositories are BRANCHES-PROVEN too",
        (res["w_allheld"].branches_verdict, res["w_squash"].branches_verdict, res["w_ff"].branches_verdict),
        (BRANCHES_PROVEN, BRANCHES_PROVEN, BRANCHES_PROVEN),
    )
    chk.expect(
        "branches verdict is not loosened for unpushed / dirty / stash / dirty worktree / detached / network / no remote",
        {
            name: res[name].branches_verdict
            for name in (
                "w_unpushed", "w_dirty", "w_stash", "w_detdirty", "w_detunpushed", "w_netfail", "w_noremote", "w_stale",
            )
        },
        {
            name: "UNPROVEN"
            for name in (
                "w_unpushed", "w_dirty", "w_stash", "w_detdirty", "w_detunpushed", "w_netfail", "w_noremote", "w_stale",
            )
        },
    )  # fmt: skip
    orphan, empty = res["wt_orphan"], res["nogit_empty"]
    chk.expect(
        "orphaned worktree (admin entry pruned) is UNPROVEN-NO-GIT-METADATA, whole-repo, with the cause named",
        (orphan.verdict, orphan.reasons[0][0], orphan.scope, "no longer exists" in orphan.first_reason),
        ("UNPROVEN", R_ORPHAN, "whole-repo", True),
    )
    chk.expect(
        "empty .git file is UNPROVEN-NO-GIT-METADATA",
        (empty.verdict, empty.reasons[0][0], "empty .git file" in empty.first_reason),
        ("UNPROVEN", R_ORPHAN, True),
    )

    print("finding 1: commits only reflogs / remote-tracking refs / refs/stash name")
    rl = res["w_reflog"]
    chk.expect(
        "reflog-only work (deleted unmerged branch, abandoned detached commit) is UNPROVEN-REFLOG-ONLY",
        (rl.verdict, [c for c, _ in rl.reasons], [t.status for t in rl.tips if t.kind == "branch"]),
        ("UNPROVEN", [R_REFLOG], [EXACT]),
    )
    chk.expect_in("reflog-only reason counts both abandoned heads", "2 head(s) not held remotely", rl.first_reason)
    tr = res["w_trackonly"]
    chk.expect(
        "work only an unpruned remote-tracking ref holds (remote and local branch deleted) is UNPROVEN-REFLOG-ONLY",
        (tr.verdict, [c for c, _ in tr.reasons]),
        ("UNPROVEN", [R_REFLOG]),
    )
    chk.expect_in("tracking-only reason names the abandoned commit", track_tip[:12], tr.first_reason)
    rh = res["w_rfheld"]
    chk.expect(
        "positive control: the abandoned commit is an ancestor of a branch the remote still has: PROVEN-ALL",
        (rh.verdict, rh.reasons, f"fixture/rfheld {rf_tip} - kept" in (root / "helper.log").read_text("utf-8")),
        ("PROVEN-ALL", [], True),
    )
    chk.expect(
        "tags / other refs stay out of the sweep: a local-only tag is BRANCHES-PROVEN, not REFLOG-ONLY",
        [c for c, _ in res["w_tagonly"].reasons],
        [R_NOT_HELD],
    )
    sn = res["w_stashnolog"]
    chk.expect(
        "refs/stash whose reflog is gone still counts as a stash",
        (sn.stashes, sn.verdict, [c for c, _ in sn.reasons]),
        (1, "UNPROVEN", [R_STASH]),
    )
    bs, bp = res["m_barestash.git"], res["m_bareplain.git"]
    chk.expect(
        "bare mirror carrying refs/stash is UNPROVEN-STASH (`git stash list` would have failed and read as none)",
        (bs.stashes, bs.verdict, [c for c, _ in bs.reasons]),
        (1, "UNPROVEN", [R_STASH]),
    )
    chk.expect(
        "positive control: a plain bare mirror is PROVEN-ALL (no false error from the stash probe)",
        (bp.stashes, bp.verdict, bp.reasons),
        (0, "PROVEN-ALL", []),
    )

    print("findings 3a-3e")
    gr = next(t for t in res["w_grafts"].tips if t.name == "loc")
    chk.expect(
        "3d: a local-only commit grafted under a remote tip via info/grafts is not held",
        (gr.sha == graft_tip, gr.status, res["w_grafts"].verdict),
        (True, R_NOT_HELD, "UNPROVEN"),
    )
    rp = next(t for t in res["w_replace"].tips if t.name == "loc")
    chk.expect(
        "refs/replace grafting a local-only commit under a remote tip does not make it held",
        (rp.sha == replace_tip, rp.status, res["w_replace"].verdict),
        (True, R_NOT_HELD, "UNPROVEN"),
    )
    an = next(t for t in res["w_annot"].tips if t.name == "refs/tags/v9")
    chk.expect(
        "3a: an annotated tag whose commit the remote holds is still unheld when the tag object is local-only",
        (an.annotated, an.status, res["w_annot"].verdict),
        (True, R_NOT_HELD, "UNPROVEN"),
    )
    chk.expect_in("3a: the reason says the tag object is the problem", "annotated tag object", an.evidence)
    ss = res["w_shallowsrc"]
    old = next(t for t in ss.tips if t.name == "old")
    chk.expect(
        "3e: off GitHub an ancestor-only branch is not provable (the remote may be shallow); the exact tip is",
        (old.status, next(t.status for t in ss.tips if t.name == "main"), ss.verdict),
        (R_NOT_HELD, EXACT, "UNPROVEN"),
    )
    anc = next(t for t in res["w_allheld"].tips if t.name == "anc")
    chk.expect("3e control: on a GitHub remote the same ancestor-only branch is PROVEN-ANCESTOR", anc.status, ANCESTOR)

    print("finding 4: fail closed, no false offsite, no cache collisions, GitHub alone never proves")
    gh = res["w_ghonly"]
    chk.expect(
        "4c: no network remote answered, yet GitHub proved the tip: still UNPROVEN-NETWORK",
        (
            next(t.status for t in gh.tips if t.name == "main"),
            gh.verdict,
            any(c == R_NETWORK and "no network remote answered" in d for c, d in gh.reasons),
        ),
        (ANCESTOR, "UNPROVEN", True),
    )
    pr = res["w_prunable"]
    pdt = [t for t in pr.tips if t.kind == "detached"]
    chk.expect(
        "a deleted (prunable) linked worktree detached on a local-only commit still contributes its tip",
        ([(t.sha == prunable_tip, t.status) for t in pdt], pr.verdict),
        ([(True, R_NOT_HELD)], "UNPROVEN"),
    )
    for label, want, url in (
        ("github over https", "network", "https://github.com/o/r.git"),
        ("github over scp-style ssh", "network", "git@github.com:o/r.git"),
        ("a public address literal", "network", "ssh://git@8.8.8.8/o/r.git"),
        ("172.32.x is public", "network", "https://172.32.0.1/o/r.git"),
        ("localhost", "local", "ssh://git@localhost/srv/r.git"),
        ("loopback literal", "local", "git@127.0.0.1:o/r.git"),
        ("RFC1918 192.168", "local", "https://192.168.1.10/o/r.git"),
        ("RFC1918 10/8", "local", "ssh://10.0.0.5/o/r.git"),
        ("RFC1918 172.16/12", "local", "ssh://172.16.4.2/o/r.git"),
        ("link-local", "local", "https://169.254.1.1/o/r.git"),
        ("CGNAT literal", "local", "https://100.64.0.1/o/r.git"),
        ("IPv6 loopback", "local", "ssh://git@[::1]/o/r.git"),
        ("IPv6 link-local", "local", "https://[fe80::1]/o/r.git"),
        ("mDNS .local name", "local", "http://nas.local/r.git"),
        ("single-label ssh alias is unknown", "unsupported", "nas:o/r.git"),
        ("single-label host in a URL is unknown", "unsupported", "ssh://backup/o/r.git"),
        ("unknown scheme", "unsupported", "ext::sh -c x"),
        ("a dotted remote-helper transport is not an scp-style host", "unsupported", "git.helper::addr"),
        ("IPv4 shorthand 127.1", "local", "https://127.1/o/r.git"),
        ("IPv4 shorthand in an scp-style address", "local", "git@127.1:o/r.git"),
        ("hex loopback 0x7f.0.0.1", "local", "https://0x7f.0.0.1/o/r.git"),
        ("octal loopback 0177.0.0.1", "local", "ssh://0177.0.0.1/o/r.git"),
        ("decimal loopback 2130706433", "local", "https://2130706433/o/r.git"),
        ("shorthand private 10.1", "local", "https://10.1/o/r.git"),
        ("wildcard DNS for loopback", "local", "https://127.0.0.1.nip.io/o/r.git"),
        ("dashed wildcard DNS for RFC1918", "local", "ssh://git@192-168-1-5.sslip.io/o/r.git"),
        ("wildcard DNS for a public address stays offsite", "network", "https://8.8.8.8.nip.io/o/r.git"),
        ("a public shorthand-free name stays offsite", "network", "https://git.example.org/o/r.git"),
    ):
        chk.expect(f"4a classify_remote: {label}", classify_remote(url, []), want)
    chk.expect(
        "4b norm_key: user, port and non-GitHub path case all keep two listings apart",
        (
            norm_key("alice@host.example:repo.git") != norm_key("bob@host.example:repo.git"),
            norm_key("ssh://git@host.example:2222/srv/r.git") != norm_key("ssh://git@host.example/srv/r.git"),
            norm_key("ssh://host.example/srv/Repo.git") != norm_key("ssh://host.example/srv/repo.git"),
        ),
        (True, True, True),
    )
    chk.expect(
        "P1 norm_key: scp `host:x` (relative to the login home) and `ssh://host/x` (absolute) are different repositories",
        (
            norm_key("host.example:data.git") != norm_key("ssh://host.example/data.git"),
            norm_key("host.example:/srv/r.git") == norm_key("ssh://host.example/srv/r.git"),
            norm_key("host.example:x.git") == norm_key("ssh://host.example/~/x.git"),
        ),
        (True, True, True),
    )
    ca, cb = res["w_collideA"], res["w_collideB"]
    chk.expect(
        "P1: a listing of ~/data.git (scp-style) never proves the tips of /data.git (ssh://): A is proven, B is not held",
        (
            ca.verdict,
            [t.sha == collide_tip for t in ca.tips if t.name == "main"],
            cb.verdict,
            [(t.sha == collide_tip, t.status) for t in cb.tips if t.name == "main"],
        ),
        ("PROVEN-ALL", [True], "UNPROVEN", [(True, R_NOT_HELD)]),
    )
    served = (root / "fake-ssh.log").read_text(encoding="utf-8").split("\n")
    chk.expect(
        "P1: ... because each spelling was listed on its own, two ls-remote calls",
        ("srv.example.com data.git" in served, "srv.example.com /data.git" in served),
        (True, True),
    )
    chk.expect(
        "P2 control: the same shape over the real github.com URL (fake ssh transport) still proves an ancestor",
        ([r.slug for r in res["w_allheld"].remotes], res["w_allheld"].verdict),
        (["fixture/allheld"], "PROVEN-ALL"),
    )
    chk.expect(
        "4b norm_key control: the same GitHub repository spelled differently shares one listing",
        norm_key("https://github.com/Fixture/Repo.git") == norm_key("https://github.com/fixture/repo"),
        True,
    )

    print("findings 3c, 4e, 5 and the sweep's edges")
    sh_ok, sh_bad = res["w_subheld"], res["w_sublocal"]
    chk.expect(
        "3c control: a submodule whose recorded commit its remote holds leaves the superproject PROVEN-ALL",
        (sh_ok.verdict, sh_ok.reasons, any("submodules analysed: 1" in n for n in sh_ok.notes)),
        ("PROVEN-ALL", [], True),
    )
    chk.expect(
        "3c: a submodule at a commit only this machine has makes the (fully pushed) superproject UNPROVEN-SUBMODULE",
        (sh_bad.verdict, [c for c, _ in sh_bad.reasons]),
        ("UNPROVEN", [R_SUBMODULE]),
    )
    chk.expect_in("3c: the reason names the submodule's own cause", "UNPROVEN-TIP-NOT-HELD", sh_bad.first_reason)
    lb, lo = res["w_borrowbad"], res["w_borrowok"]
    chk.expect(
        "4e: a borrower whose alternates lender holds unpushed work is UNPROVEN-ALTERNATES (its own refs are all held)",
        (lb.verdict, [c for c, _ in lb.reasons], lb.count("branch", "UNPROVEN")),
        ("UNPROVEN", [R_ALTERNATES], 0),
    )
    chk.expect(
        "4e control: a borrower whose lender is fully pushed is PROVEN-ALL",
        (lo.verdict, lo.reasons, any("alternates lenders analysed: 1" in n for n in lo.notes)),
        ("PROVEN-ALL", [], True),
    )
    chk.expect(
        "4e: git-lfs content in the local lfs store is UNPROVEN-LFS (it cannot be checked against a remote)",
        (res["w_lfs"].verdict, [c for c, _ in res["w_lfs"].reasons]),
        ("UNPROVEN", [R_LFS]),
    )
    chk.expect(
        "P9: git-lfs content in a store relocated by lfs.storage (absolute, or relative to the git dir) is UNPROVEN-LFS",
        [(res[n].verdict, [c for c, _ in res[n].reasons]) for n in ("w_lfsstore", "w_lfsrel")],
        [("UNPROVEN", [R_LFS])] * 2,
    )
    chk.expect(
        "P9 control: lfs.storage pointing at an empty store changes nothing",
        (res["w_lfsempty"].verdict, res["w_lfsempty"].reasons),
        ("PROVEN-ALL", []),
    )
    chk.expect(
        "P9: git-annex content under .git/annex/objects is UNPROVEN-ANNEX",
        (res["w_annex"].verdict, [c for c, _ in res["w_annex"].reasons]),
        ("UNPROVEN", [R_ANNEX]),
    )
    hd = res["w_hidden"]
    chk.expect(
        "5: files edited behind skip-worktree and assume-unchanged are UNPROVEN-HIDDEN-EDITS naming both",
        (hd.verdict, [c for c, _ in hd.reasons], hd.dirty_entries),
        ("UNPROVEN", [R_HIDDEN], 0),
    )
    chk.expect_in("5: ... both edited files are counted", "w_hidden: 2", hd.first_reason)
    spr = res["w_sparse"]
    chk.expect(
        "5 control: skip-worktree / assume-unchanged entries that were not edited stay PROVEN-ALL, recorded as a note",
        (spr.verdict, spr.reasons, any("2 skip-worktree / assume-unchanged entries" in n for n in spr.notes)),
        ("PROVEN-ALL", [], True),
    )
    chk.expect(
        "4e/5: a non-GitHub remote leaves an explicit note that history behind exact tips is assumed complete",
        any("non-GitHub remote" in n for n in res["w_multi"].notes),
        True,
    )
    chk.expect(
        "3b: a human commit on top of a bot commit is not a stale bot copy (every commit must be the bot's)",
        [t.status for t in res["w_botmixed"].tips if t.name == "dependabot/npm/mixed"],
        [R_NOT_HELD],
    )
    chk.expect(
        "3b: a person's commit made through the GitHub web UI (committer GitHub) is not a bot's stale copy",
        [t.status for t in res["w_botweb"].tips if t.name == "renovate/web"],
        [R_NOT_HELD],
    )
    th = res["w_trackheld"]
    chk.expect(
        "sweep control: a remote-only branch fetched here (no local branch) is held by the remote's own listing",
        (th.verdict, th.reasons),
        ("PROVEN-ALL", []),
    )
    rn = res["w_rfnone"]
    chk.expect(
        "sweep: abandoned work GitHub does not have is UNPROVEN-REFLOG-ONLY after the helper was consulted and said no",
        (
            rn.verdict,
            [c for c, _ in rn.reasons],
            f"fixture/rfnone {rfnone_tip} -" in (root / "helper.log").read_text("utf-8"),
        ),
        ("UNPROVEN", [R_REFLOG], True),
    )
    wl = res["w_wtlog"]
    chk.expect(
        "sweep: commits only a linked worktree's HEAD reflog names (one worktree deleted since) are REFLOG-ONLY",
        (wl.verdict, [c for c, _ in wl.reasons]),
        ("UNPROVEN", [R_REFLOG]),
    )
    chk.expect_in(
        "sweep: ... both worktrees' abandoned commits are counted", "2 head(s) not held remotely", wl.first_reason
    )
    nt = next((t for t in res["w_notes"].tips if t.ref == "refs/notes/commits"), None)
    chk.expect(
        "a local-only refs/notes/commits is a blocking `other` tip",
        (nt.kind, nt.status, res["w_notes"].verdict) if nt else None,
        ("other", R_NOT_HELD, "UNPROVEN"),
    )
    capped = globals()["MAX_SWEEP_LOOKUPS"]
    globals()["MAX_SWEEP_LOOKUPS"] = 1
    try:
        capres = analyze(s_oracle, [str(root)], only=("w_rfchain", "w_rfpair"))
    finally:
        globals()["MAX_SWEEP_LOOKUPS"] = capped
    chk.expect(
        "sweep: a chain of abandoned commits is one head, so a lookup cap of 1 still proves it",
        (capres["w_rfchain"].verdict, capres["w_rfchain"].reasons),
        ("PROVEN-ALL", []),
    )
    chk.expect(
        "sweep: with a lookup cap of 1 the second of two independent heads is unheld, never assumed held",
        (capres["w_rfpair"].verdict, [c for c, _ in capres["w_rfpair"].reasons]),
        ("UNPROVEN", [R_REFLOG]),
    )
    chk.expect_in("sweep: ... exactly one head is left", "1 head(s) not held remotely", capres["w_rfpair"].first_reason)
    ctl2 = analyze(s_oracle, [str(root)], only=("w_rfpair",))["w_rfpair"]
    chk.expect("sweep control: with the normal cap both independent heads are proven", ctl2.verdict, "PROVEN-ALL")

    mirror_only = analyze(s_oracle, [str(root)], only=("w_mirror",))["w_mirror"]
    mirror_old = next(t for t in mirror_only.tips if t.name == "old")
    chk.expect(
        "P2: a github.com URL that insteadOf rewrites to a shallow non-GitHub mirror is not a GitHub remote: "
        "no full-history ancestor proof, the helper is never asked",
        (
            [r.slug for r in mirror_only.remotes],
            mirror_old.status,
            mirror_only.verdict,
            (root / "helper.log").read_text(encoding="utf-8"),
        ),
        ([None], R_NOT_HELD, "UNPROVEN", ""),
    )

    print("finding 4f: a 404 from GitHub reads as 'not found or no access', never as an answer about the work")
    fake_bin = root / "fakebin"
    fake_bin.mkdir()
    helper_path = Path(__file__).resolve().parent / "gh-merged-pr-proof.sh"
    for label, body, want_status, want_rc in (
        ("404", 'echo "gh: Not Found (HTTP 404)" >&2; exit 1', "NONE", 1),
        ("502 (control: not a definite negative)", 'echo "gh: bad gateway (HTTP 502)" >&2; exit 1', "ERROR", 2),
    ):
        fake_gh = fake_bin / "gh"
        fake_gh.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
        fake_gh.chmod(0o755)
        rc, out, _err = run(
            [str(helper_path), "fixture/x", "a" * 40, "main"],
            timeout=60,
            env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        )
        fields = out.strip().split("\t")
        chk.expect(f"helper with gh answering {label}: status and exit code", (fields[0], rc), (want_status, want_rc))
        if want_status == "NONE":
            chk.expect_in("helper 404 reason says 'or no access'", "or-no-access", out)

    for flag in ("--help", "-h"):
        rc, out, _err = run([str(helper_path), flag], timeout=60, env=dict(os.environ))
        chk.expect(
            f"PS-14: the helper answers {flag} with its usage: exit 0 and no status line",
            (rc, out.startswith("usage: gh-merged-pr-proof.sh"), out.startswith("ERROR")),
            (0, True, False),
        )
    rc, out, err = run([str(helper_path)], timeout=60, env=dict(os.environ))
    chk.expect(
        "PS-14: no arguments: the usage on stderr, the protocol's ERROR line on stdout, exit 2",
        (rc, err.startswith("usage: gh-merged-pr-proof.sh"), out.split("\t")[:3]),
        (2, True, ["ERROR", "?", "?"]),
    )

    print("faults: an unreadable listing is UNPROVEN, never an empty one")
    for label, fails, only, want in (
        ("status", lambda a: a[0] == "status", ("w_allheld",), "status failed"),
        ("ref listing", lambda a: a[0] == "for-each-ref" and "%(objecttype)" in a[1], ("w_allheld",), "for-each-ref"),
        ("worktree listing", lambda a: a[:2] == ("worktree", "list"), ("w_allheld",), "worktree listing failed"),
        ("remote listing", lambda a: a == ("remote",), ("w_allheld",), "remote listing failed"),
        ("stash ref listing", lambda a: a[0] == "for-each-ref" and a[-1] == "refs/stash", ("w_allheld",), "stash ref"),
        ("stash reflog listing", lambda a: a[0] == "log" and "-g" in a, ("w_stash",), "stash reflog"),
        ("reflog sweep", lambda a: "rev-list" in a and "--reflog" in a, ("w_allheld",), "reachability failed"),
        ("reflog ancestry", lambda a: "rev-list" in a and "--no-walk" in a, ("w_trackonly",), "ancestry failed"),
    ):
        fr = faulted(only[0], fails, only)[only[0]]
        chk.expect(
            f"fault in {label}: UNPROVEN with UNPROVEN-ERROR naming it",
            (fr.verdict, any(c == R_ERROR and want in d for c, d in fr.reasons)),
            ("UNPROVEN", True),
        )
    fr = faulted("w_stale", lambda a: a[:2] == ("rev-list", "--stdin"), ("w_stale",))["w_stale"]
    chk.expect(
        "fault in the ancestry probe: the tip stays NOT-HELD (a failed rev-list proves nothing)",
        next(t.status for t in fr.tips if t.name == "main"),
        R_NOT_HELD,
    )
    for label, hits, reply, only, want in (
        (
            "an ls-remote line that is not `<object id> TAB <ref>`",
            lambda a: a[:2] == ("ls-remote", "--heads"),
            (0, "this is not a ref listing\n", ""),
            "w_allheld",
            R_NETWORK,
        ),
        (
            "a for-each-ref line whose object id is not hex",
            lambda a: a[0] == "for-each-ref" and "%(objecttype)" in a[1],
            (0, "refs/heads/main\tnot-an-object-id\tcommit\t\t\n", ""),
            "w_allheld",
            "unparseable ref listing line",
        ),
        (
            "an unreadable refs/stash listing",
            lambda a: a[0] == "for-each-ref" and a[-1] == "refs/stash",
            (0, "not-an-object-id\n", ""),
            "w_unpushed",
            "stash ref listing unparseable",
        ),
    ):
        fr = faulted(only, hits, (only,), reply)[only]
        chk.expect(
            f"P5: {label} makes the repository UNPROVEN (an unreadable line is never skipped)",
            (fr.verdict, any(want in code or want in detail for code, detail in fr.reasons)),
            ("UNPROVEN", True),
        )
    ctl = faulted("w_allheld", lambda a: False, ("w_allheld",))["w_allheld"]
    chk.expect("fault control: the same repository with no fault injected is PROVEN-ALL", ctl.verdict, "PROVEN-ALL")

    bad256, ok256, stash256 = res["m_sha256.git"], res["w_sha256"], res["w_sha256stash"]
    chk.expect(
        "P5: a SHA-256 bare mirror holding a local-only branch is UNPROVEN: 64-hex ids are tips, not noise",
        (
            bad256.verdict,
            sorted((t.name, len(t.sha), t.status) for t in bad256.tips),
        ),
        (
            "UNPROVEN",
            sorted([("main", 64, EXACT), ("refs/tags/z-tag", 64, EXACT), ("unpushed", 64, R_NOT_HELD)]),
        ),
    )
    chk.expect(
        "P5 control: a fully pushed SHA-256 clone is PROVEN-ALL with 64-hex tips for the branch and the annotated tag",
        (ok256.verdict, sorted((t.name, len(t.sha), t.status) for t in ok256.tips)),
        ("PROVEN-ALL", sorted([("main", 64, EXACT), ("refs/tags/z-tag", 64, EXACT)])),
    )
    chk.expect(
        "P5: a stash in a SHA-256 repository is counted (its 64-hex id is not dropped)",
        (stash256.stashes, [c for c, _ in stash256.reasons]),
        (1, [R_STASH]),
    )
    chk.expect(
        "P5: the all-zero id of an unborn branch is recognised for any hash length",
        [set(v) <= {"0"} for v in ("0" * 40, "0" * 64)],
        [True, True],
    )

    print("pass 2: same repositories WITHOUT trusting local remotes (they live on this machine)")
    res2 = analyze(s_proven, [], only=("w_trackheld", "w_insteadlocal", "w_unpushed"))
    chk.expect(
        "local-path remote never proves anything, nor does a github.com URL that insteadOf points at a local path",
        [(res2[n].verdict, res2[n].reasons[0][0]) for n in ("w_trackheld", "w_insteadlocal")],
        [("UNPROVEN", R_LOCAL)] * 2,
    )
    chk.expect("local-path remote: helper never reached", (root / "helper.log").read_text(encoding="utf-8"), "")

    print("pass 3: helper answers NONE / ERROR / lies about the sha / is disabled")
    for label, helper, want in (
        ("NONE", s_none, R_NOT_HELD),
        ("ERROR", s_error, R_NETWORK),
        ("wrong sha", s_wrong, R_NETWORK),
        ("ancestor of a branch nobody asked about", s_badbranch, R_NETWORK),
        ("PROVEN line but a failing exit status", s_proven_rc, R_NETWORK),
        ("disabled", None, R_NOT_HELD),
    ):
        r3 = analyze(helper, [str(root)], only=("w_squash",))["w_squash"]
        tip = next(t for t in r3.tips if t.name == "feat")
        chk.expect(f"squash tip with helper {label}: {want}", (r3.verdict, tip.status), ("UNPROVEN", want))

    print("finding 5: the CLI flag works, and the environment follows it")
    saved_protocol = ENV_OVERRIDES.pop("GIT_ALLOW_PROTOCOL")
    try:
        make_ctx(args, None, [])
        no_file = base_env()["GIT_ALLOW_PROTOCOL"]
        make_ctx(args, None, [str(root)])
        with_file = base_env()["GIT_ALLOW_PROTOCOL"]
    finally:
        ENV_OVERRIDES["GIT_ALLOW_PROTOCOL"] = saved_protocol
    chk.expect(
        "git may speak `file` only when --trust-remote-under names a directory",
        ("file" in no_file.split(":"), "file" in with_file.split(":")),
        (False, True),
    )
    sweep = root / "cli-sweep.tsv"
    sweep.write_text(f"path\tkind\n{root / 'w_trackheld'}\trepo\n", encoding="utf-8")
    quiet_home = root / "home"
    quiet_home.mkdir()
    cli_env = {**os.environ, "HOME": str(quiet_home), "XDG_CONFIG_HOME": str(quiet_home)}

    def cli(*argv: str) -> tuple[int, str, str]:
        return run([sys.executable, "-I", str(Path(__file__).resolve()), *argv], timeout=300, env=cli_env)

    def cli_run(label: str, *extra: str, tsv: Path = sweep) -> tuple[int, Path, str]:
        out_path = root / f"cli-out-{label}"
        rc, _out, err = cli(
            "--tsv", str(tsv), "--out-dir", str(out_path), "--no-pr-proof", "--net-interval", "0", *extra
        )
        return rc, out_path, err

    for label, extra, want, want_rc in (
        ("with --trust-remote-under", ["--trust-remote-under", str(root)], "PROVEN-ALL", 1),
        ("without it", [], R_LOCAL, 1),
    ):
        rc, cli_out, err = cli_run(label.split()[0], *extra)
        cli_rows, _marker = (
            tsv_rows(cli_out / "remote-held.tsv") if (cli_out / "remote-held.tsv").exists() else ([], "")
        )
        cli_fact = dict(zip(REMOTE_HELD_COLS, cli_rows[0], strict=False)) if cli_rows else {}
        field = "verdict" if want == "PROVEN-ALL" else "first_reason"
        chk.expect(
            f"CLI {label}: w_trackheld is {want}", cli_fact.get(field, f"rc={rc} {err[-120:]}").split(":")[0], want
        )
        chk.expect(f"PS-9: CLI {label}: exit code {want_rc}", rc, want_rc)
        chk.expect(
            f"G2: CLI {label}: stderr names PROVEN-ALL rows that carry gaps only when there are some",
            "PROVEN-ALL but carry documented gaps" in err,
            want == "PROVEN-ALL",
        )
        chk.expect(
            f"PS-5: CLI {label}: the flag leaves its trace in the row, the summary and stderr, and only then",
            (
                GAP_TRUST in cli_fact.get("gaps", ""),
                "TEST-ONLY --trust-remote-under" in (cli_out / "summary.txt").read_text(encoding="utf-8"),
                "--trust-remote-under is TEST ONLY" in err,
            ),
            (want == "PROVEN-ALL",) * 3,
        )

    clean_sweep = root / "cli-sweep-clean.tsv"
    clean_sweep.write_text(f"path\tkind\n{root / 'w_allheld'}\trepo\n", encoding="utf-8")
    rc, clean_out, err = cli_run("gapfree", tsv=clean_sweep)
    clean_rows, _marker = (
        tsv_rows(clean_out / "remote-held.tsv") if (clean_out / "remote-held.tsv").exists() else ([], "")
    )
    clean_fact = dict(zip(REMOTE_HELD_COLS, clean_rows[0], strict=False)) if clean_rows else {}
    chk.expect(
        "G2: a PROVEN-ALL repository with an empty `gaps` column (GitHub alone proves it) is the only exit 0",
        (rc, clean_fact.get("verdict", f"rc={rc} {err[-120:]}"), clean_fact.get("gaps", "?")),
        (0, "PROVEN-ALL", ""),
    )
    rc, cmp_out, _err = cli_run("compare", "--trust-remote-under", str(root), "--compare", str(sweep))
    cmp_rows, cmp_marker = tsv_rows(cmp_out / "real-compare.tsv")
    chk.expect(
        "contract 3: real-compare.tsv (--compare) ends with its completion row too, and its path is the realpath",
        (rc, cmp_marker, [r[0] for r in cmp_rows], ends_properly(cmp_out / "real-compare.tsv", ["path"] * 8)),
        (1, f"{END_MARK} rows=1", [os.path.realpath(root / "w_trackheld")], True),  # exit 1: a trusted-remote gap
    )
    print("PS-9: exit codes (0 proven, 1 not proven, 64 usage, 70 internal error or incomplete run)")
    rc, out, _err = cli("--help")
    chk.expect("PS-9: --help documents the exit codes", (rc, "70 = internal error" in out), (0, True))
    rc, _out, _err = cli()
    chk.expect("PS-9: no arguments is a usage error: exit 64", rc, 64)
    rc, _out, _err = cli("--no-such-flag")
    chk.expect("PS-9: an unknown flag is a usage error: exit 64, not argparse's 2", rc, 64)
    missing_out = root / "cli-out-missing-tsv"
    rc, _out, _err = cli("--tsv", str(root / "no-such-sweep.tsv"), "--out-dir", str(missing_out))
    chk.expect("PS-9: a missing --tsv is exit 64 and creates nothing", (rc, missing_out.exists()), (64, False))
    header_only = root / "cli-header-only.tsv"
    header_only.write_text("path\tkind\n", encoding="utf-8")
    rc, empty_out, _err = cli_run("empty", tsv=header_only)
    chk.expect(
        "PS-9: a sweep with no entries is exit 64 (no vacuous green) and creates nothing",
        (rc, empty_out.exists()),
        (64, False),
    )
    busy_out = root / "cli-out-busy"
    busy_out.mkdir()
    (busy_out / "keep").write_text("x\n", encoding="utf-8")
    rc, _out, _err = cli("--tsv", str(sweep), "--out-dir", str(busy_out))
    chk.expect(
        "PS-9: a non-empty --out-dir is exit 64 and untouched",
        (rc, [p.name for p in busy_out.iterdir()]),
        (64, ["keep"]),
    )
    rc, late_out, _err = cli_run("deadline", "--trust-remote-under", str(root), "--deadline=-1")
    late_rows, late_marker = tsv_rows(late_out / "remote-held.tsv")
    chk.expect(
        "PS-9: a deadline that leaves repositories unexamined is exit 70, says so, and the file still ends with its row",
        (
            rc,
            late_marker,
            R_TIMEOUT in (late_rows[0][REMOTE_HELD_COLS.index("first_reason")] if late_rows else ""),
            "INCOMPLETE RUN" in (late_out / "summary.txt").read_text(encoding="utf-8"),
        ),
        (70, f"{END_MARK} rows=1", True, True),
    )
    two_rows = root / "cli-two-rows.tsv"
    two_rows.write_text(f"path\tkind\n{root / 'w_trackheld'}\trepo\n{root / 'w_dirty'}\trepo\n", encoding="utf-8")
    rc, _lim_out, _err = cli_run("limit", "--trust-remote-under", str(root), "--limit", "1", tsv=two_rows)
    chk.expect("PS-9: --limit that drops entries is an incomplete run: exit 70", rc, 70)
    real_analyze = globals()["analyze_all"]

    def exploding(ctx_: Ctx, rows_: list[Row], outs_: dict[str, TsvOut] | None) -> list[RepoResult]:
        real_analyze(ctx_, rows_[:1], outs_)  # the first repository's rows reach the files, then the run dies
        raise RuntimeError("injected failure")

    boom_out = root / "cli-out-boom"
    globals()["analyze_all"] = exploding
    stderr_text = io.StringIO()
    try:
        with contextlib.redirect_stderr(stderr_text):
            boom_rc = main(
                ["--tsv", str(sweep), "--out-dir", str(boom_out), "--no-pr-proof", "--net-interval", "0"]
                + ["--trust-remote-under", str(root)]
            )
    finally:
        globals()["analyze_all"] = real_analyze
    boom_tails = [(boom_out / f"{name}.tsv").read_text(encoding="utf-8").split("\n")[-2] for name in OUT_SPECS]
    chk.expect(
        "PS-9: an exception is exit 70 with a traceback; no result file gets a completion row and there is no summary.txt",
        (
            boom_rc,
            "injected failure" in stderr_text.getvalue(),
            any(t.startswith(END_MARK) for t in boom_tails),
            (boom_out / "summary.txt").exists(),
        ),
        (70, True, False, False),
    )

    print("redaction")
    chk.expect(
        "userinfo with password is masked", redact("https://user:SECRETTOKEN@host/x.git"), "https://***@host/x.git"
    )
    chk.expect("bare ssh user is kept", redact("ssh://git@github.com/o/r.git"), "ssh://git@github.com/o/r.git")
    chk.expect(
        "secret query parameter is masked",
        redact("https://h/x?token=abc&y=1"),  # allow-secret: dummy fixture value proving redact() masks it
        "https://h/x?token=***&y=1",  # allow-secret: expected masked output of the dummy
    )
    out_dir = root / "out"
    out_dir.mkdir()
    outs = open_outs(out_dir)
    ctx = make_ctx(args, s_oracle, [str(root)])
    ctx.log = lambda _m: None
    results = analyze_all(ctx, rows, outs)
    for out in outs.values():
        out.close()
    write_summary(out_dir / "summary.txt", results, ctx, time.monotonic(), "self-test", rows)
    written = "".join(p.read_text(encoding="utf-8") for p in sorted(out_dir.iterdir()))
    chk.expect("credential never reaches any output file", "SECRETTOKEN" in written, False)
    chk.expect_in("remote-held.tsv carries the redacted URL", "ssh://***@git.example.invalid/x.git", written)
    preserve, _ = tsv_rows(out_dir / "preserve-set.tsv")
    chk.expect(
        "preserve-set lists the UNPROVEN repositories that still exist (not the vanished one)",
        len(preserve),
        sum(r.verdict == "UNPROVEN" and r.scope != "vanished" for r in results),
    )
    unproven_text = (out_dir / "unproven-branches.tsv").read_text(encoding="utf-8")
    superseded_text = (out_dir / "superseded-bot-branches.tsv").read_text(encoding="utf-8")
    chk.expect(
        "superseded bot branch is listed on its own and never in unproven-branches.tsv",
        ("dependabot/npm/foo" in superseded_text, "dependabot/npm/foo" in unproven_text),
        (True, False),
    )
    vanished_rows, _ = tsv_rows(out_dir / "vanished.tsv")
    chk.expect(
        "vanished.tsv names the vanished path and flags it as exposed in the sweep (dirty=3, no remote)",
        (len(vanished_rows), vanished_rows[0][0].endswith("/vanished"), vanished_rows[0][-1]),
        (1, True, "yes"),
    )
    remote_held, marker = tsv_rows(out_dir / "remote-held.tsv")
    header = (out_dir / "remote-held.tsv").read_text(encoding="utf-8").splitlines()[0].split("\t")
    by_name = {Path(r[0]).name: dict(zip(header, r, strict=False)) for r in remote_held}
    chk.expect(
        "remote-held.tsv columns: verdict and branches_verdict side by side, superseded_bot counted",
        (by_name["w_tagonly"]["verdict"], by_name["w_tagonly"]["branches_verdict"], by_name["w_bot"]["superseded_bot"]),
        ("UNPROVEN", BRANCHES_PROVEN, "1"),
    )
    last_row = (out_dir / "remote-held.tsv").read_text(encoding="utf-8").splitlines()[-1].split("\t")
    chk.expect(
        "finding 4g: a result file ends with a full-width completion row carrying its row count",
        (last_row[0], len(last_row) == len(REMOTE_HELD_COLS), marker),
        (f"{END_MARK} rows={len(results)}", True, f"{END_MARK} rows={len(results)}"),
    )
    cut = out_dir / "cut.tsv"
    cut.write_text("\n".join(["a\tb", "1\t2"]) + "\n", encoding="utf-8")
    chk.expect("finding 4g control: a file without the row reads as incomplete", tsv_rows(cut)[1], "")
    entries, _ = tsv_rows(out_dir / "entries.tsv")
    entry_header = (out_dir / "entries.tsv").read_text(encoding="utf-8").splitlines()[0].split("\t")
    chk.expect(
        "finding 2: entries.tsv names the column head_held, not row_held",
        ("head_held" in entry_header, "row_held" in entry_header),
        (True, False),
    )
    chk.expect("entries.tsv has one row per sweep entry", len(entries), len(rows))

    print("contract 1: join keys are lossless, realpath'd, and byte-identical to the path git and the OS report")
    leaked = [r["_bad"] for name in OUT_SPECS for r in tsv_dicts(out_dir / f"{name}.tsv") if "_bad" in r]
    chk.expect("no result file has a row whose cell count differs from its header (no TAB / LF leaks out)", leaked, [])
    chk.expect(
        "contract 3: every result file ends with exactly one full-width `#END rows=N` row, N = its data rows",
        [name for name, cols in OUT_SPECS.items() if not ends_properly(out_dir / f"{name}.tsv", cols)],
        [],
    )
    held_by_repo = {r.get("repo", ""): r for r in tsv_dicts(out_dir / "remote-held.tsv")}
    entry_rows = [r for r in tsv_dicts(out_dir / "entries.tsv") if "path" in r]
    tip_rows = [r for r in tsv_dicts(out_dir / "tips.tsv") if "repo" in r]

    def real(name: str) -> str:
        return os.path.realpath(root / name)

    ok_row = held_by_repo.get(real("w_spaced  ok"), {})
    chk.expect(
        "INT-3: a checkout path with consecutive spaces is a join key byte-identical to its realpath (repo, paths, common_dir)",
        (ok_row.get("paths"), ok_row.get("common_dir"), ok_row.get("verdict")),
        (real("w_spaced  ok"), real("w_spaced  ok/.git"), "PROVEN-ALL"),
    )
    tag_row = held_by_repo.get(real("w_spaced  tag"), {})
    chk.expect(
        "INT-3: ... and the UNPROVEN repository with that path keeps its verdict AND its key, so the join finds it",
        (tag_row.get("paths"), tag_row.get("verdict")),
        (real("w_spaced  tag"), "UNPROVEN"),
    )
    chk.expect(
        "INT-3: ... entries.tsv and tips.tsv carry the same unflattened path",
        (
            [e["path"] for e in entry_rows if "spaced  tag" in e["path"]],
            {t["repo"] for t in tip_rows if "spaced" in t["repo"] and "tag" in t["repo"]},
        ),
        ([real("w_spaced  tag")], {real("w_spaced  tag")}),
    )
    semi = held_by_repo.get(real("w_semi;colon"), {})
    chk.expect(
        "contract 1: a `;` in a checkout path (the list separator) is UNPROVEN-UNREPRESENTABLE, written with U+FFFD",
        (semi.get("verdict"), semi.get("paths"), R_UNREPRESENTABLE in semi.get("all_reasons", "")),
        ("UNPROVEN", real("w_semi;colon").replace(";", FFFD), True),
    )
    tab_key, lf_key = real("w_tab\tin-name").replace("\t", FFFD), real("w_lf\nin-name").replace("\n", FFFD)
    chk.expect(
        "contract 1: a TAB / LF in a checkout path is UNPROVEN-UNREPRESENTABLE, U+FFFD in place, the row stays whole",
        [
            (held_by_repo.get(k, {}).get("verdict"), held_by_repo.get(k, {}).get("paths"), R_UNREPRESENTABLE)
            for k in (tab_key, lf_key)
        ],
        [("UNPROVEN", tab_key, R_UNREPRESENTABLE), ("UNPROVEN", lf_key, R_UNREPRESENTABLE)],
    )
    chk.expect(
        "contract 1: the unrepresentable repositories carry the reason code and are not PROVEN-ALL in memory either",
        [(res[n].verdict, res[n].reasons[0][0]) for n in ("w_tab\tin-name", "w_lf\nin-name")],
        [("UNPROVEN", R_UNREPRESENTABLE)] * 2,
    )
    via_link = held_by_repo.get(real("real_sym"), {})
    chk.expect(
        "contract 1: a checkout reached through a symlink is keyed by its realpath",
        (via_link.get("paths"), via_link.get("repo")),
        (real("real_sym"), real("real_sym")),
    )
    chk.expect(
        "contract 1: key_cell keeps what git printed and only replaces what would break the row",
        (key_cell("a  b ;c"), key_cell("a\tb\rc\nd"), key_cell("x\N{LINE SEPARATOR}y"), paths_cell(["a;b", "c"])),
        ("a  b ;c", f"a{FFFD}b{FFFD}c{FFFD}d", f"x{FFFD}y", f"a{FFFD}b;c"),
    )

    print(
        "contract 2: tips.tsv holds, for every live ref, the row the predicate looks up (full refnames, HEAD@, @worktree)"
    )
    by_repo_ref = {(r["repo"], r["ref"]): r for r in tip_rows}

    def binding(name: str) -> list[str]:
        """Problems a consumer deriving its keys from live git would meet in the REAL tips.tsv for one repository."""
        repo_path = root / name
        label, problems = os.path.realpath(repo_path), []
        for key, oid in sorted(live_ref_keys(repo_path).items()):
            row = by_repo_ref.get((label, key))
            if row is None:
                problems.append(f"{key}: no row")
            elif row["tip"] != oid:
                problems.append(f"{key}: tip {row['tip'][:8]} != live {oid[:8]}")
            elif not row["status"].startswith("PROVEN-"):
                problems.append(f"{key}: {row['status']}")
        return problems

    chk.expect(
        "INT-5: every live ref of a fully pushed repository has its full-refname row, same tip, proven (the F1 binding)",
        (binding("w_allheld"), sorted(r["ref"] for r in tip_rows if r["repo"] == real("w_allheld"))),
        (
            [],
            [f"refs/heads/{b}" for b in ("anc", "exactbr", "main")] + ["refs/tags/v1", "refs/tags/v2"],
        ),
    )
    chk.expect(
        "INT-5: no branch, tag or other row of any repository is a short name",
        [r["ref"] for r in tip_rows if r["kind"] in {"branch", "tag", "other"} and not r["ref"].startswith("refs/")],
        [],
    )
    chk.expect(
        "INT-5: a detached worktree is keyed HEAD@<realpath of the worktree>, one row per such worktree",
        sorted(r["ref"] for r in tip_rows if r["kind"] == "detached" and r["repo"] == real("w_detunpushed")),
        [f"HEAD@{real('wt_detunpushed')}"],
    )
    chk.expect(
        "INT-5: refs/notes and the other full refnames are keyed exactly as `for-each-ref` prints them",
        [r["ref"] for r in tip_rows if r["repo"] == real("w_notes") and r["kind"] == "other"],
        ["refs/notes/commits"],
    )
    chk.expect(
        "INT-5: the unpushed work is bound to an UNPROVEN row (never absent, never proven)",
        binding("w_unpushed"),
        ["refs/heads/wip: UNPROVEN-TIP-NOT-HELD"],
    )
    chk.expect(
        "P3: a per-worktree ref of a LINKED worktree is listed as <refname>@<worktree> and blocks: UNPROVEN-PER-WORKTREE",
        (
            res["w_wtref"].verdict,
            [c for c, _ in res["w_wtref"].reasons],
            [(t.ref, t.sha == wtref_tip, t.status) for t in res["w_wtref"].tips if t.kind == "per-worktree"],
            binding("w_wtref"),
        ),
        (
            "UNPROVEN",
            [R_PER_WORKTREE],
            [(f"refs/worktree/keep@{real('wt_wtref')}", True, R_PER_WORKTREE)],
            [f"refs/worktree/keep@{real('wt_wtref')}: {R_PER_WORKTREE}"],
        ),
    )
    anchored = analyze_list(s_oracle, [str(root)], [Row(str(wt44b), "worktree", {}), Row(str(w44b), "repo", {})])[
        "w_wtref2"
    ]
    chk.expect(
        "P3: a per-worktree ref of the MAIN worktree is found when the sweep lists a linked worktree first",
        (
            anchored.verdict,
            [c for c, _ in anchored.reasons],
            [(t.ref, t.sha == wtref2_tip) for t in anchored.tips if t.kind == "per-worktree"],
            [t.ref for t in anchored.tips if t.kind == "other"],
        ),
        ("UNPROVEN", [R_PER_WORKTREE], [(f"refs/worktree/keep@{real('w_wtref2')}", True)], []),
    )
    chk.expect(
        "P3: the anchor's own per-worktree refs are listed once, qualified, never also as a bare `other` name",
        (
            [t.ref for t in res["w_wtref2"].tips if t.kind == "other"],
            [t.ref for t in res["w_wtref2"].tips if t.kind == "per-worktree"],
        ),
        ([], [f"refs/worktree/keep@{real('w_wtref2')}"]),
    )
    chk.expect(
        "P3: refs/bisect/bad of a side worktree blocks too",
        (
            res["w_bisect"].verdict,
            [(t.ref, t.sha == bisect_tip) for t in res["w_bisect"].tips if t.kind == "per-worktree"],
        ),
        ("UNPROVEN", [(f"refs/bisect/bad@{real('wt_bisect')}", True)]),
    )
    chk.expect(
        "P3 control: per-worktree refs on pushed work are proven, qualified by their worktree, and the repository is PROVEN-ALL",
        (
            res["w_wtheld"].verdict,
            sorted((t.ref, t.status) for t in res["w_wtheld"].tips if t.kind == "per-worktree"),
            binding("w_wtheld"),
        ),
        (
            "PROVEN-ALL",
            sorted(
                [
                    (f"refs/bisect/good@{real('wt_wtheld')}", EXACT),
                    (f"refs/worktree/pin@{real('w_wtheld')}", EXACT),
                ]
            ),
            [],
        ),
    )

    print("P4 / P8: submodule checkouts and hidden edits are read where the files are")
    sk = res["w_subskip"]
    chk.expect(
        "P4: a file edited behind skip-worktree inside a SUBMODULE makes the superproject UNPROVEN-SUBMODULE",
        (sk.verdict, [c for c, _ in sk.reasons], R_HIDDEN in sk.first_reason, sk.dirty_entries),
        ("UNPROVEN", [R_SUBMODULE], True, 0),
    )
    nested_ctx = make_ctx(args, s_oracle, [str(root)])
    nested_ctx.log = lambda _m: None
    sub_res = analyze_nested(nested_ctx, str(root / "w_subskip" / ".git" / "modules" / "sub"), "submodule", 0)
    chk.expect(
        "P4: the nested analysis is anchored at the submodule's checkout, once, never also at its git dir",
        ([os.path.realpath(w.path) for w in sub_res.worktrees], sub_res.repo, sub_res.verdict),
        ([real("w_subskip/sub")], real("w_subskip/sub"), "UNPROVEN"),
    )
    chk.expect(
        "P4: the hidden-edit probe finds the edit even when it is handed the submodule's git dir (it was (1, 0, ''))",
        hidden_edits(str(root / "w_subskip" / ".git" / "modules" / "sub")),
        (1, 1, ""),
    )
    swept_sub = next(
        iter(analyze_list(s_oracle, [str(root)], [Row(str(root / "w_sublocal" / "sub"), "worktree", {})]).values())
    )
    sub_fact = swept_sub.row_facts[0]
    chk.expect(
        "P8: a swept submodule checkout with an unpushed commit on its branch is not held (it was '(unborn)' and held)",
        (sub_fact.head, sub_fact.head_status, sub_fact.held),
        ("refs/heads/main", R_NOT_HELD, "no"),
    )
    held_sub = next(
        iter(analyze_list(s_oracle, [str(root)], [Row(str(root / "w_subheld" / "sub"), "worktree", {})]).values())
    )
    chk.expect(
        "P8 control: a swept submodule checkout on a pushed commit is held",
        (held_sub.row_facts[0].head, held_sub.row_facts[0].held),
        ("refs/heads/main", "yes"),
    )
    wh = res["w_wthidden"]
    chk.expect(
        "P8: a linked worktree with a file edited behind skip-worktree is not head_held, though its HEAD is held and status is clean",
        (wh.verdict, {Path(f.row.path).name: f.held for f in wh.row_facts}, [w.dirty for w in wh.worktrees]),
        ("UNPROVEN", {"w_wthidden": "no", "wt_wthidden": "no"}, [0, 0]),
    )
    probes = [probe_worktree(str(root / p_)) for p_ in ("wt_detunpushed", "w_sublocal/sub", "u_unborn", "nogit_empty")]
    chk.expect(
        "P8: probe_worktree reads a swept path's HEAD from git: detached on a commit, unborn only on a commit-less branch, else unknown",
        [(w.detached, w.unborn, w.head is not None, w.branch) for w in probes],
        [
            (True, False, True, None),
            (False, False, True, "refs/heads/main"),
            (False, True, False, "refs/heads/main"),
            (False, False, False, None),
        ],
    )

    print("contract 4: the gaps column names every documented limit of a proof")
    gap_cells = {Path(r["repo"]).name: r["gaps"] for r in tsv_dicts(out_dir / "remote-held.tsv") if "repo" in r}
    chk.expect(
        "contract 4: `gaps` is the last column of remote-held.tsv, after the existing ones",
        (REMOTE_HELD_COLS[-1], "gaps" in tsv_header(out_dir / "remote-held.tsv")),
        ("gaps", True),
    )
    chk.expect(
        "contract 4 control: a PROVEN-ALL repository proven by GitHub alone has an empty `gaps`",
        (res["w_allheld"].verdict, gap_cells["w_allheld"]),
        ("PROVEN-ALL", ""),
    )
    chk.expect(
        "contract 4 control: a non-GitHub backup that holds nothing GitHub lacks adds no gap (GitHub proves first)",
        (res["w_dualhold"].verdict, gap_cells["w_dualhold"]),
        ("PROVEN-ALL", ""),
    )
    chk.expect(
        "contract 4 / P10: a tip held by SHA on a non-GitHub remote leaves NONGITHUB-HISTORY-ASSUMED on a PROVEN-ALL row",
        [(res[n].verdict, gap_cells[n]) for n in ("w_collideA", "w_shtip")],
        [("PROVEN-ALL", GAP_NONGITHUB)] * 2,
    )
    chk.expect(
        "contract 4 / P10: a commit excluded from the sweep on a non-GitHub remote's word leaves the same gap",
        (res["w_sweepgap"].verdict, gap_cells["w_sweepgap"]),
        ("PROVEN-ALL", GAP_NONGITHUB),
    )
    chk.expect(
        "contract 4 / PS-5: a remote counted as offsite only because of --trust-remote-under leaves TRUST-REMOTE-UNDER",
        (res["w_trackheld"].verdict, sorted(res["w_trackheld"].gaps), gap_cells["w_trackheld"]),
        ("PROVEN-ALL", [GAP_NONGITHUB, GAP_TRUST], f"{GAP_NONGITHUB};{GAP_TRUST}"),
    )
    chk.expect(
        "contract 4: a submodule's gap is the superproject's (the superproject itself is proven by GitHub alone)",
        (res["w_subgap"].verdict, GAP_TRUST in res["w_subgap"].gaps),
        ("PROVEN-ALL", True),
    )
    chk.expect(
        "contract 4 / P10: a bare repository without reflogs leaves BARE-NO-REFLOG; one that keeps reflogs does not",
        (GAP_BARE in res["m_bareplain.git"].gaps, GAP_BARE in res["m_barelog.git"].gaps),
        (True, False),
    )
    unlogged = {n: res[n] for n in ("w_nolog", "w_nologdir")}
    chk.expect(
        "G1: a NON-bare repository whose reflogs cannot enumerate abandoned commits "
        "(core.logAllRefUpdates=false, or no reflog file at all) leaves NO-REFLOG on its PROVEN-ALL row",
        (
            [r.verdict for r in unlogged.values()],
            [GAP_NO_REFLOG in r.gaps for r in unlogged.values()],
            [GAP_BARE in r.gaps for r in unlogged.values()],
            [
                run(["git", "cat-file", "-e", dangling55[n]], timeout=30, env=base_env(), cwd=str(root / f"w_{n}"))[0]
                for n in ("nolog", "nologdir")
            ],
        ),
        (["PROVEN-ALL"] * 2, [True, True], [False, False], [0, 0]),
    )
    chk.expect(
        "G1 control: reflogs for every ref, or a bare repository (BARE-NO-REFLOG instead), do not get NO-REFLOG",
        [GAP_NO_REFLOG in res[n].gaps for n in ("w_allheld", "w_logalways", "m_bareplain.git", "m_barelog.git")],
        [False] * 4,
    )
    summary_text = (out_dir / "summary.txt").read_text(encoding="utf-8")
    chk.expect(
        "PS-5: summary.txt carries a loud TEST ONLY line naming --trust-remote-under and the gap, and counts gap-free rows",
        (
            "WARNING: --trust-remote-under" in summary_text,
            GAP_TRUST in summary_text,
            "PROVEN-ALL with no documented gap" in summary_text,
        ),
        (True, True, True),
    )

    print("scratch hygiene: fixtures and mutants stay out of the checkout")
    here = Path(__file__).resolve().parent
    tmp_root = Path(os.path.realpath(tempfile.gettempdir()))
    chk.expect(
        "the self-test builds its fixtures under the system temp dir (realpath), never next to the script",
        (root.is_relative_to(tmp_root), root.is_relative_to(here), str(root) == os.path.realpath(root)),
        (True, False, True),
    )
    mutation_check = here / "prove-mutation-check.py"
    state = mutation_check_state(here, os.environ)
    chk.expect(
        "PS-14: prove-mutation-check.py sits next to the tool (or this run is one of its mutant copies); never skipped silently",
        state in {"present", "copy"},
        True,
    )
    if state == "copy":
        print("  [SKIP] mutation check sub-checks: this is a mutant copy (it carries only the tool and its helper)")
    with tempfile.TemporaryDirectory(prefix="gate-") as gate_dir:
        (Path(gate_dir) / "with").mkdir()
        (Path(gate_dir) / "with" / "prove-mutation-check.py").write_text("", encoding="utf-8")
        (Path(gate_dir) / "without").mkdir()
        gate = [
            mutation_check_state(Path(gate_dir) / "with", {}),
            mutation_check_state(Path(gate_dir) / "without", {}),
            mutation_check_state(Path(gate_dir) / "without", {COPY_ENV: "1"}),
        ]
    chk.expect(
        "PS-14: a checkout without prove-mutation-check.py is `missing` (a failure), only a marked copy may skip",
        gate,
        ["present", "missing", "copy"],
    )
    if state == "present":
        mc = [sys.executable, "-I", str(mutation_check)]
        listing = sorted(p.name for p in here.iterdir())
        rc, out, _err = run([*mc, "--help"], timeout=60, env=dict(os.environ))
        chk.expect("mutation check: --help works and names the optional OUT_DIR", (rc, "OUT_DIR" in out), (0, True))
        rc, out, _err = run([*mc, "--check-anchors"], timeout=120, env=dict(os.environ))
        chk.expect(
            "mutation check: the default run leaves nothing next to the script and cleans its temp dir",
            (rc, sorted(p.name for p in here.iterdir()) == listing, "kept " in out),
            (0, True, False),
        )
        for label, extra, want_kept in (("without --keep", [], False), ("with --keep", ["--keep"], True)):
            target = root / f"mutants-{label.split()[-1]}"
            rc, out, _err = run([*mc, "--check-anchors", str(target), *extra], timeout=120, env=dict(os.environ))
            chk.expect(
                f"mutation check: a named OUT_DIR {label} is {'kept and printed' if want_kept else 'removed'}",
                (rc, target.is_dir(), f"kept {target}" in out),
                (0, want_kept, want_kept),
            )
        busy = root / "mutants-busy"
        busy.mkdir()
        (busy / "x").write_text("x\n", encoding="utf-8")
        rc, _out, _err = run([*mc, "--check-anchors", str(busy)], timeout=60, env=dict(os.environ))
        chk.expect(
            "mutation check: a non-empty OUT_DIR is refused (usage error 64), untouched",
            (rc, (busy / "x").exists()),
            (64, True),
        )
        rc, _out, err = run([*mc, "--only", "no-such-mutant"], timeout=60, env=dict(os.environ))
        chk.expect(
            "PS-10: --only with an unknown mutant name is exit 64 naming it, never 'all killed' over zero mutants",
            (rc, "no-such-mutant" in err),
            (64, True),
        )
        rc, _out, _err = run([*mc, "--check-anchors", "--only", "no-such-mutant"], timeout=60, env=dict(os.environ))
        chk.expect("PS-10: ... and with --check-anchors too (it reported '0 valid, 0 invalid', exit 0)", rc, 64)


def main(argv: list[str] | None = None) -> int:
    here = Path(__file__).resolve().parent
    parser = UsageParser(
        description=__doc__.splitlines()[0], epilog=EXIT_CODES, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--tsv", type=Path, help="sweep TSV (path, kind, branch, remote, dirty, unpushed, stashes, ...)"
    )
    parser.add_argument("--out-dir", type=Path, help="new or empty directory for the result files")
    parser.add_argument("--compare", type=Path, help="second sweep TSV (e.g. real.tsv) to compare against the verdicts")
    parser.add_argument("--helper", type=Path, default=here / "gh-merged-pr-proof.sh", help="merged-PR proof helper")
    parser.add_argument("--no-pr-proof", action="store_true", help="skip the merged-PR proof entirely")
    parser.add_argument("--helper-workers", type=int, default=3, help="concurrent GitHub lookups (default 3)")
    parser.add_argument(
        "--deadline", type=float, default=1380.0, help="seconds before remaining repos are UNPROVEN-TIMEOUT"
    )
    parser.add_argument("--net-interval", type=float, default=0.25, help="min seconds between ls-remote calls")
    parser.add_argument("--helper-interval", type=float, default=0.6, help="min seconds between GitHub lookup starts")
    parser.add_argument(
        "--trust-remote-under", action="append", default=[], help="TEST ONLY: treat path remotes under DIR as network"
    )
    parser.add_argument("--limit", type=int, default=0, help="examine only the first N sweep entries")
    parser.add_argument("--self-test", action="store_true", help="build fixture repositories and assert each verdict")
    parser.add_argument(
        "--keep-fixtures", action="store_true", help="with --self-test: do not delete the fixture directory"
    )
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test(args.keep_fixtures)
    if not args.tsv or not args.out_dir:
        parser.error("--tsv and --out-dir are required (or --self-test)")
    try:
        return cmd_run(args)
    except Exception:  # an internal error is exit 70 with a traceback, never a result that looks finished
        traceback.print_exc()
        print(INTERNAL_ERROR_MESSAGE, file=sys.stderr)
        return EXIT_INTERNAL


if __name__ == "__main__":
    sys.exit(main())
