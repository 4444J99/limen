#!/usr/bin/env python3
"""Additive, hash-verified copy of chosen non-git directories to an external volume (stdlib only).

  nongit_homing.py MODE RUN_DIR ITEMS_TSV [--home DIR] [--sqlite BIN] [--deadline-sec N]
                   [--extra-cred-file-globs 'g1;g2'] [--extra-cred-dir-globs 'g1;g2']

    MODE       dry | apply
    RUN_DIR    new run directory. apply creates it and refuses one that already exists; dry never writes there.
    ITEMS_TSV  one item per line: name <TAB> source_dir <TAB> dest_rel <TAB> exclude_globs
               source_dir is absolute or starts with $HOME/ (or ~/); dest_rel is relative to RUN_DIR;
               exclude_globs is ';'-separated and relative to source_dir. '#' comments and blank lines are ignored.
               A glob written '=name' silently carves a top-level entry out of the item because another item copies it.

Per item: walk the source without following symlinks, copy every regular file by streaming it once (the SHA-256 of
the SOURCE bytes is taken from the very bytes written), recreate symlinks and directories, then re-read every
destination file (F_NOCACHE on macOS) and compare its SHA-256 with the source hash. A source whose size, mtime or
inode changed while it was being copied is reported as DRIFT (re-run that item), never as verified.

SQLite: any regular file whose first 16 bytes are 'SQLite format 3\\0' is a database and is snapshotted with
`sqlite3 -readonly SRC ".backup DEST"` (consistent even while an application holds it open in WAL or rollback-journal
mode), journal mode flipped to DELETE so the snapshot is self-contained, then checked with PRAGMA integrity_check and
hashed twice on read-back. The '-wal', '-shm' and '-journal' sidecars of a snapshotted database are not copied (the
snapshot already contains them). If a snapshot fails, the database and its sidecars are copied as a hash-verified
trio instead and flagged in RESULT.txt.

Never copied, only listed (name and size, never contents) in EXCLUDED.tsv: credential-looking names and directories
(CRED_FILE_GLOBS / CRED_DIR_GLOBS plus the operator's additive extras), dataless iCloud/File Provider placeholders
(reading one would trigger a download), and sockets/FIFOs/devices. Names containing a tab, newline, carriage return
or backslash cannot be written to a manifest that `shasum -a 256 -c` can verify; they are reported as ERROR_PATH and
not copied.

Nothing is ever deleted or overwritten: every destination path is created exclusively, and every destination
directory is checked to resolve inside RUN_DIR before anything is written. The only unlink is of the '-shm'/'-wal'
scratch sidecars that sqlite itself creates beside a snapshot THIS run just wrote, guarded to paths under RUN_DIR.

Preserved: file bytes, permission bits (without setuid/setgid/sticky) and mtime, symlink targets. Not preserved:
ownership, extended attributes, ACLs, resource forks, birth time, directory mtimes, hard-link identity.

A run PASSes only if there are no problems and at least one file was copied and verified. A run that hits the
deadline writes a FAIL result; MANIFEST.sha256 then lists only what had been verified by that point.
"""

from __future__ import annotations

import argparse
import fcntl
import fnmatch
import hashlib
import os
import posixpath
import re
import shutil
import stat
import subprocess
import sys
import time
import urllib.parse
from dataclasses import dataclass, field

CHUNK = 8 * 1024 * 1024
SQLITE_MAGIC = b"SQLite format 3\x00"
SF_DATALESS = 0x40000000
SIDECARS = ("-wal", "-shm", "-journal")
SQLITE_TIMEOUT = 3600  # per sqlite3 invocation; further capped by the remaining run deadline
BAD_NAME_CHARS = re.compile(r"[\t\n\r\\]")
EXIT_OK, EXIT_FAIL, EXIT_USAGE, EXIT_NO_SQLITE, EXIT_RUN_DIR_EXISTS = 0, 1, 64, 69, 73

# Tight, name-based. Matched case-insensitively against the basename (files) or basename / relative path / trailing
# path components (dirs). The defaults only ever grow: the operator's extras are additive and cannot remove one.
CRED_FILE_GLOBS = [
    ".env",
    ".env.*",
    "*.env",
    ".netrc",
    "_netrc",
    ".npmrc",
    ".pypirc",
    ".git-credentials",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.key",
    "*.keychain",
    "*.keychain-db",
    "*.kdbx",
    "*.jks",
    "*.ppk",
    "secring.*",
    "pubring.kbx",
    "trustdb.gpg",
    "credentials",
    "credentials.json",
    "client_secret*.json",
    "service-account*.json",
    "auth.json",
    "token",
    "token.json",
    "tokens.json",
    "*-tokens.json",
    "*_tokens.json",
    "*.token",
    "*token_cache*.json",
    "session.json",
    "cookies",
    "cookies-journal",
    "cookies.sqlite",
    "login data*",
    "web data*",
    "logins.json",
    "key3.db",
    "key4.db",
    "*.secret",
    "*.secrets",
    "secrets.*",
    "secret.*",
    # agent/MCP tool config files embed environment tokens and are re-rendered from their templates, so refusing
    # them loses nothing
    ".claude.json",
    "legacy-home.json",
    "mcp.json",
    ".mcp.json",
    "config.toml",
    "config.toml.bak-*",
    "claude_desktop_config.json*",
    ".credentials.json",
    "*.credentials.json",
    "installation_id",
    "ant-did",
]
CRED_DIR_GLOBS = [
    ".ssh",
    ".gnupg",
    ".aws",
    ".azure",
    ".kube",
    ".docker",
    ".electrum",
    ".secrets",
    "keychains",
    "*1password*",
    "private-keys-v1.d",
    ".config/gh",
    ".gcloud",
    ".moneta",
]


class HomingError(Exception):
    """Bad input or an unsafe configuration: nothing has been written."""

    def __init__(self, message: str, code: int = EXIT_USAGE):
        super().__init__(message)
        self.code = code


class RunDirExists(Exception):
    """apply refuses to reuse a run directory."""


class DeadlineExceeded(Exception):
    """The hard run deadline passed; nothing further is copied or verified."""


class DestEscapeError(OSError):
    """A destination path would resolve outside the run directory."""


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def tsv_cell(text: str) -> str:
    """Escape a value for a TSV cell or a one-line report: backslash, tab, newline and carriage return."""
    return text.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def ci_match(name: str, globs: list[str]) -> str | None:
    low = name.lower()
    for g in globs:
        if fnmatch.fnmatchcase(low, g.lower()):
            return g
    return None


def item_excluded(rel: str, globs) -> bool:
    base = os.path.basename(rel)
    return any(
        g and (fnmatch.fnmatchcase(rel, g) or fnmatch.fnmatchcase(base, g) or rel.startswith(g.rstrip("/") + "/"))
        for g in globs
    )


def credential_dir_hit(name: str, rel: str, path: str, globs: list[str]) -> str | None:
    """A credential directory glob matches the directory name, the path relative to the item, or (for a glob with
    several components such as '.config/gh') the trailing components of the absolute path, so it still bites when
    the item's root is below the glob's first component."""
    low_name, low_rel, low_path = name.lower(), rel.lower(), path.lower()
    for g in globs:
        gl = g.lower()
        if fnmatch.fnmatchcase(low_name, gl) or fnmatch.fnmatchcase(low_rel, gl):
            return g
        if "/" in gl and fnmatch.fnmatchcase(low_path, "*/" + gl):
            return g
    return None


def exclusion_for_file(name: str, st, cred_globs: list[str]) -> tuple[str, str] | None:
    """(kind, reason) when a regular file must be listed instead of copied, else None."""
    hit = ci_match(name, cred_globs)
    if hit:
        return "credential-file", hit
    if getattr(st, "st_flags", 0) & SF_DATALESS:
        return "dataless-placeholder", "remote-held; reading would download"
    return None


def tree_size(path: str) -> tuple[int, int]:
    """Apparent bytes and file count of a (credential) directory: stat only, nothing is opened."""
    total = count = 0
    stack = [path]
    while stack:
        p = stack.pop()
        try:
            with os.scandir(p) as it:
                for e in it:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(st.st_mode):
                        stack.append(e.path)
                    elif stat.S_ISREG(st.st_mode):
                        total += st.st_size
                        count += 1
        except OSError:
            continue
    return total, count


def is_sqlite(path: str, size: int) -> bool:
    if size < 512:
        return False
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        try:
            return os.read(fd, 16) == SQLITE_MAGIC
        finally:
            os.close(fd)
    except OSError:
        return False


def sha_file(path: str, nocache: bool = False, check=None) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        if nocache and sys.platform == "darwin":  # re-read from the device, not the page cache
            try:
                fcntl.fcntl(fh.fileno(), getattr(fcntl, "F_NOCACHE", 48), 1)  # 48 = F_NOCACHE on darwin
            except OSError:
                pass
        while True:
            b = fh.read(CHUNK)
            if not b:
                break
            h.update(b)
            if check:
                check()
    return h.hexdigest()


def copy_hash(src: str, dst: str, st, check=None) -> str:
    """Stream src->dst exclusively and return the sha256 of the bytes read from src.

    The source is opened with O_NOFOLLOW|O_NONBLOCK and must still be a regular file (a path swapped for a symlink
    or FIFO after the walk is refused, never followed or blocked on). The destination is created with O_EXCL."""
    h = hashlib.sha256()
    out_fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        in_fd = os.open(src, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
        try:
            if not stat.S_ISREG(os.fstat(in_fd).st_mode):
                raise OSError(f"{src} is no longer a regular file")
            with os.fdopen(in_fd, "rb", closefd=False) as fin, os.fdopen(out_fd, "wb", closefd=False) as fout:
                while True:
                    b = fin.read(CHUNK)
                    if not b:
                        break
                    h.update(b)
                    fout.write(b)
                    if check:
                        check()
                fout.flush()
            if st.st_size > CHUNK:  # small files ride the per-item os.sync()
                os.fsync(out_fd)
        finally:
            os.close(in_fd)
    finally:
        os.close(out_fd)
    os.chmod(dst, (stat.S_IMODE(st.st_mode) & 0o777) | 0o200)
    os.utime(dst, ns=(st.st_atime_ns, st.st_mtime_ns))
    return h.hexdigest()


def find_sqlite(explicit: str | None = None) -> str:
    """The sqlite3 CLI: --sqlite, then $NONGIT_HOMING_SQLITE (each strict), then /usr/bin/sqlite3, then PATH."""
    for pinned in (explicit, os.environ.get("NONGIT_HOMING_SQLITE")):
        if pinned:
            if os.access(pinned, os.X_OK):
                return pinned
            raise HomingError(f"sqlite3 binary is not executable: {pinned}", EXIT_NO_SQLITE)
    for cand in ("/usr/bin/sqlite3", shutil.which("sqlite3")):
        if cand and os.access(cand, os.X_OK):
            return cand
    raise HomingError("sqlite3 not found (install it, or pass --sqlite / set NONGIT_HOMING_SQLITE)", EXIT_NO_SQLITE)


@dataclass(frozen=True)
class Item:
    name: str
    source: str  # absolute, normalized
    dest_rel: str  # relative to the run dir, normalized, no '..'
    globs: tuple[str, ...] = ()
    carve: frozenset[str] = frozenset()
    line: int = 0


def expand_source(raw: str, home: str) -> str:
    for prefix in ("${HOME}", "$HOME", "~"):
        if raw == prefix or raw.startswith(prefix + "/"):
            raw = home + raw[len(prefix) :]
            break
    if "$" in raw:
        raise HomingError(f"unsupported variable in source '{raw}' (only a leading $HOME or ~ is expanded)")
    if not os.path.isabs(raw):
        raise HomingError(f"source must be absolute or start with $HOME/: '{raw}'")
    return os.path.normpath(raw)


def normalize_dest_rel(raw: str) -> str:
    norm = posixpath.normpath(raw) if raw else "."
    parts = norm.split("/")
    if norm == "." or norm.startswith("/") or ".." in parts:
        raise HomingError(f"dest_rel must be a relative path inside the run directory (no '..', not absolute): '{raw}'")
    if BAD_NAME_CHARS.search(norm):
        raise HomingError(f"dest_rel contains a tab, newline, carriage return or backslash: '{tsv_cell(raw)}'")
    if parts[0].startswith("-"):
        raise HomingError(f"dest_rel must not start with '-': '{raw}'")
    return norm


def parse_items(path: str, home: str) -> list[Item]:
    items: list[Item] = []
    names: dict[str, int] = {}
    dests: dict[str, int] = {}
    with open(path, encoding="utf-8", errors="surrogateescape") as fh:
        for lineno, raw in enumerate(fh, 1):
            line = raw.rstrip("\r\n")
            if not line.strip() or line.startswith("#"):
                continue
            where = f"{path}:{lineno}"
            parts = line.split("\t")
            if not 3 <= len(parts) <= 4:
                raise HomingError(
                    f"{where}: want name, source_dir, dest_rel[, exclude_globs] (tab-separated), got {len(parts)} field(s)"
                )
            name, source, dest_rel = parts[0], parts[1], parts[2]
            if not name or not source or not dest_rel:
                raise HomingError(f"{where}: name, source_dir and dest_rel must all be non-empty")
            try:
                src_abs = expand_source(source, home)
                dest_norm = normalize_dest_rel(dest_rel)
            except HomingError as e:
                raise HomingError(f"{where}: {e}") from None
            if name in names:
                raise HomingError(f"{where}: item name '{name}' already used on line {names[name]}")
            if dest_norm in dests:
                raise HomingError(f"{where}: dest_rel '{dest_norm}' already used on line {dests[dest_norm]}")
            names[name], dests[dest_norm] = lineno, lineno
            globs = [g for g in (parts[3].split(";") if len(parts) == 4 else []) if g]
            carve = frozenset(g[1:] for g in globs if g.startswith("="))
            if any(not c or "/" in c for c in carve):
                raise HomingError(f"{where}: '=name' carve-outs name one top-level entry (no '/')")
            items.append(
                Item(name, src_abs, dest_norm, tuple(g for g in globs if not g.startswith("=")), carve, lineno)
            )
    if not items:
        raise HomingError(f"{path}: no items")
    return items


def _inside(child: str, parent: str) -> bool:
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def check_items(items: list[Item], run_dir: str) -> None:
    """Refuse configurations that would copy bytes twice, copy into themselves, or rename a single file."""
    run_real = os.path.join(os.path.realpath(os.path.dirname(run_dir)), os.path.basename(run_dir))
    reals = [(it, os.path.realpath(it.source)) for it in items]
    for it, real in reals:
        if _inside(run_real, real):
            raise HomingError(f"run directory {run_dir} is inside the source of item '{it.name}': it would copy itself")
        if _inside(real, run_real):
            raise HomingError(f"the source of item '{it.name}' is inside the run directory {run_dir}")
        single = os.path.isfile(it.source) and not os.path.islink(it.source)
        if single and posixpath.basename(it.dest_rel) != os.path.basename(it.source):
            raise HomingError(
                f"item '{it.name}': a single-file source keeps its name, so dest_rel must end in "
                f"'{os.path.basename(it.source)}' (got '{it.dest_rel}')"
            )
    # No item may contain another (that would copy and count the same bytes twice) unless the outer item's exclude
    # list carves the inner one out (the "loose files of a directory" pattern).
    for a, a_real in reals:
        for b, b_real in reals:
            if a is b or not _inside(b_real, a_real):
                continue
            if a_real == b_real:
                raise HomingError(f"items '{a.name}' and '{b.name}' have the same source {a.source}")
            rel_b = b_real[len(a_real.rstrip(os.sep)) + 1 :]
            first = rel_b.split(os.sep)[0]
            if not (first in a.carve or item_excluded(rel_b, a.globs) or item_excluded(first, a.globs)):
                raise HomingError(
                    f"overlapping items: '{a.name}' ({a.source}) contains '{b.name}' ({b.source}); "
                    f"add '={first}' to the exclude list of '{a.name}'"
                )


@dataclass
class Homer:
    """One run: dry (read-only plan) or apply (copy + verify). Holds all counters; `run` does the work."""

    apply: bool
    run_dir: str
    sqlite_bin: str
    cred_file_globs: list[str] = field(default_factory=lambda: list(CRED_FILE_GLOBS))
    cred_dir_globs: list[str] = field(default_factory=lambda: list(CRED_DIR_GLOBS))
    deadline_sec: float = 0.0  # 0 = no deadline

    def __post_init__(self) -> None:
        self.run_dir = os.path.abspath(self.run_dir)
        self.started = time.time()
        self.deadline = time.monotonic() + self.deadline_sec if self.deadline_sec > 0 else None
        self.tot = dict(
            files=0,
            bytes=0,
            symlinks=0,
            dirs=0,
            snapshots=0,
            snapshot_bytes=0,
            trio_fallbacks=0,
            excluded_credential=0,
            excluded_credential_bytes=0,
            excluded_dataless=0,
            excluded_special=0,
            excluded_by_item_glob=0,
            verified=0,
            drift=0,
            missing=0,
            mismatch=0,
            errors=0,
        )
        self.problems: list[tuple[str, str, str]] = []  # (kind, path, detail)
        self.sqlite_stores: dict[str, str] = {}
        self.excluded_rows: list[tuple[str, str, int, str]] = []  # (kind, source path, bytes, reason)
        self.item_stats: list[tuple[str, dict[str, int]]] = []
        self.deadline_hit = False
        self.manifest_fh = self.tsv_fh = None
        self._run_real = ""
        self._dirs_ok: set[str] = set()

    # -- bookkeeping ------------------------------------------------------------------------------------------
    def note(self, kind: str, path: str, detail: str = "") -> None:
        self.problems.append((kind, path, detail))
        self.tot[{"DRIFT": "drift", "MISSING": "missing", "MISMATCH": "mismatch"}.get(kind, "errors")] += 1

    def check_deadline(self) -> None:
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise DeadlineExceeded()

    def _remaining(self, cap: float) -> float:
        if self.deadline is None:
            return cap
        left = self.deadline - time.monotonic()
        if left <= 0:
            raise DeadlineExceeded()
        return min(cap, left)

    def record(self, sha: str, size: int, rel_under_run: str, kind: str) -> None:
        self.manifest_fh.write(f"{sha}  {rel_under_run}\n")
        self.tsv_fh.write("\t".join([sha, str(size), tsv_cell(rel_under_run), tsv_cell(kind)]) + "\n")

    def ensure_dir(self, path: str) -> None:
        """makedirs, but only after proving the deepest existing ancestor resolves inside the run directory, so a
        symlink recreated by one item can never redirect a later item's writes out of it."""
        if path in self._dirs_ok:
            return
        probe = path
        while not os.path.lexists(probe):
            probe = os.path.dirname(probe)
        if not _inside(os.path.realpath(probe), self._run_real):
            raise DestEscapeError(f"destination {path} resolves outside the run directory")
        os.makedirs(path, exist_ok=True)
        self._dirs_ok.add(path)

    # -- source walk ------------------------------------------------------------------------------------------
    def walk(self, src: str, globs, carve=frozenset(), only: str | None = None):
        """Yield (rel, kind, st) for everything under src; kind in dir|file|link.
        `only` restricts the top level to one entry name (single-file items)."""
        stack = [""]
        while stack:
            rel_dir = stack.pop()
            full = os.path.join(src, rel_dir) if rel_dir else src
            try:
                entries = sorted(os.scandir(full), key=lambda e: e.name)
            except OSError as e:
                self.note("ERROR_LIST", full, repr(e))
                continue
            for ent in entries:
                if only is not None and not rel_dir and ent.name != only:
                    continue
                if not rel_dir and ent.name in carve:
                    continue  # '=name': carved out because another item copies it (silent, not an exclusion)
                rel = os.path.join(rel_dir, ent.name) if rel_dir else ent.name
                try:
                    st = ent.stat(follow_symlinks=False)
                except OSError as e:
                    self.note("ERROR_STAT", ent.path, repr(e))
                    continue
                if item_excluded(rel, globs):
                    self.tot["excluded_by_item_glob"] += 1
                    size = tree_size(ent.path)[0] if stat.S_ISDIR(st.st_mode) else st.st_size
                    self.excluded_rows.append(("item-excluded", ent.path, size, "item exclude list"))
                    continue
                if stat.S_ISDIR(st.st_mode):
                    hit = credential_dir_hit(ent.name, rel, ent.path, self.cred_dir_globs)
                    if hit:
                        size, count = tree_size(ent.path)
                        self.tot["excluded_credential"] += max(count, 1)
                        self.tot["excluded_credential_bytes"] += size
                        self.excluded_rows.append(("credential-dir", ent.path, size, f"{hit} ({count} files)"))
                        continue
                    if self._bad_name(ent):
                        continue
                    yield rel, "dir", st
                    stack.append(rel)
                elif stat.S_ISREG(st.st_mode):
                    ex = exclusion_for_file(ent.name, st, self.cred_file_globs)
                    if ex and ex[0] == "credential-file":
                        self.tot["excluded_credential"] += 1
                        self.tot["excluded_credential_bytes"] += st.st_size
                        self.excluded_rows.append((ex[0], ent.path, st.st_size, ex[1]))
                        continue
                    if ex:
                        self.tot["excluded_dataless"] += 1
                        self.excluded_rows.append((ex[0], ent.path, st.st_size, ex[1]))
                        continue
                    if self._bad_name(ent):
                        continue
                    yield rel, "file", st
                elif stat.S_ISLNK(st.st_mode):
                    if self._bad_name(ent):
                        continue
                    yield rel, "link", st
                else:
                    self.tot["excluded_special"] += 1
                    self.excluded_rows.append(("special-file", ent.path, 0, "socket/fifo/device"))

    def _bad_name(self, ent) -> bool:
        if BAD_NAME_CHARS.search(ent.name):
            self.note("ERROR_PATH", ent.path, "name contains a tab, newline, carriage return or backslash; not copied")
            return True
        return False

    # -- sqlite -----------------------------------------------------------------------------------------------
    def _sqlite(self, args: list[str]) -> subprocess.CompletedProcess:
        timeout = self._remaining(SQLITE_TIMEOUT)
        try:
            return subprocess.run(
                [self.sqlite_bin, *args], capture_output=True, text=True, errors="replace", timeout=timeout
            )
        except subprocess.TimeoutExpired:
            self.check_deadline()
            return subprocess.CompletedProcess(args, 124, "", f"sqlite3 timed out after {timeout:.0f}s")

    def _scrub_snapshot_sidecars(self, dst: str) -> None:
        """Remove -shm/-wal scratch that sqlite created beside the snapshot this run just wrote."""
        for side in (dst + "-shm", dst + "-wal"):
            if (
                os.path.exists(side)
                and _inside(os.path.realpath(side), self._run_real)
                and (side.endswith("-shm") or os.path.getsize(side) == 0)
            ):
                os.unlink(side)

    def dry_probe_sqlite(self, src: str) -> str:
        """Prove the database opens (TCC) without any lock or write: immutable read-only URI."""
        uri = "file:" + urllib.parse.quote(src) + "?mode=ro&immutable=1"
        r = self._sqlite([uri, "select count(*) from sqlite_master;"])
        return "opens-ok" if r.returncode == 0 else "OPEN-FAILED: " + (r.stderr or r.stdout).strip()[:120]

    def snapshot_sqlite(self, src: str, dst: str, rel_under_run: str) -> bool:
        """True when a snapshot file now exists at dst (verified or not); False sends the caller to the trio copy."""
        if os.path.lexists(dst):
            self.note("ERROR_EXISTS", dst)
            return False
        if re.search(r'["\\\n\r]', dst):  # the .backup dot-command takes a quoted argument
            self.sqlite_stores[src] = "SNAPSHOT-FAILED: destination path cannot be quoted for .backup"
            return False
        try:
            self.ensure_dir(os.path.dirname(dst))
        except OSError as e:
            self.note("ERROR_COPY", dst, repr(e))
            return False
        r = self._sqlite(["-readonly", src, f'.backup main "{dst}"'])
        if (r.returncode != 0 or not os.path.exists(dst)) and not (
            os.path.exists(src + "-wal") and os.path.getsize(src + "-wal") > 0
        ):
            # A quiescent WAL-mode db has no -shm to open read-only; with no pending WAL an immutable read is exact.
            if os.path.exists(dst):
                os.unlink(dst)  # our own half-written snapshot
            uri = "file:" + urllib.parse.quote(src) + "?mode=ro&immutable=1"
            r = self._sqlite([uri, f'.backup main "{dst}"'])
        if r.returncode != 0 or not os.path.exists(dst):
            if os.path.exists(dst):
                os.unlink(dst)  # our own half-written snapshot
            self.sqlite_stores[src] = "SNAPSHOT-FAILED: " + (r.stderr or r.stdout).strip()[:160]
            return False
        self._sqlite([dst, "PRAGMA journal_mode=DELETE;"])
        self._scrub_snapshot_sidecars(dst)
        chk = self._sqlite(["-readonly", dst, "PRAGMA integrity_check;"])
        self._scrub_snapshot_sidecars(dst)
        if chk.stdout.strip() != "ok":
            self.note("ERROR_INTEGRITY", src, chk.stdout.strip()[:300])
            self.sqlite_stores[src] = "INTEGRITY-FAIL (snapshot kept for inspection)"
            return True
        if any(os.path.exists(dst + s) for s in ("-wal", "-journal")):
            self.note(
                "ERROR_SIDECAR",
                dst,
                "snapshot still has a -wal/-journal sidecar; the main file alone is not self-contained",
            )
            self.sqlite_stores[src] = "SIDECAR-LEFT (snapshot kept for inspection)"
            return True
        os.sync()
        sha1 = sha_file(dst, nocache=True, check=self.check_deadline)
        sha2 = sha_file(dst, nocache=True, check=self.check_deadline)  # second read-back: catches a flaky write path
        if sha1 != sha2:
            self.note("MISMATCH", dst, "snapshot hash unstable on re-read")
            return True
        size = os.path.getsize(dst)
        self.record(sha1, size, rel_under_run, "sqlite-snapshot;src=" + src)
        self.tot["snapshots"] += 1
        self.tot["snapshot_bytes"] += size
        self.tot["verified"] += 1
        self.sqlite_stores[src] = "snapshot-ok"
        return True

    # -- one item ---------------------------------------------------------------------------------------------
    def run_item(self, item: Item) -> None:
        print(f"[{utc_now()}] item {item.name}: {item.source} -> {item.dest_rel}", flush=True)
        before = dict(self.tot)
        try:
            self._run_item(item)
        finally:
            keys = ("files", "bytes", "snapshots", "symlinks", "dirs", "verified")
            self.item_stats.append((item.name, {k: self.tot[k] - before[k] for k in keys}))

    def _regular(self, path: str):
        try:
            st = os.lstat(path)
        except OSError:
            return None
        return st if stat.S_ISREG(st.st_mode) else None

    def _run_item(self, item: Item) -> None:
        src_item = item.source
        single = os.path.isfile(src_item) and not os.path.islink(src_item)
        if not (single or os.path.isdir(src_item)):
            self.note("ERROR_SOURCE_MISSING", src_item, "source is not a directory or regular file")
            return
        # A single-file item is walked as its parent directory restricted to that one name.
        src = os.path.dirname(src_item) if single else src_item
        only = os.path.basename(src_item) if single else None
        dest_rel = posixpath.dirname(item.dest_rel) if single else item.dest_rel
        dest_root = os.path.normpath(os.path.join(self.run_dir, dest_rel))
        todo: list = []  # (rel, st) regular files to copy and verify
        entries = list(self.walk(src, item.globs, item.carve, only))
        names = {rel: st for rel, kind, st in entries if kind == "file"}
        dbs = {
            rel: st
            for rel, st in names.items()
            if not rel.endswith(SIDECARS) and is_sqlite(os.path.join(src, rel), st.st_size)
        }
        skip_sidecar = {b + s for b in dbs for s in SIDECARS}
        for rel, kind, st in entries:
            self.check_deadline()
            if kind == "dir":
                self.tot["dirs"] += 1
                if self.apply:
                    try:
                        self.ensure_dir(os.path.join(dest_root, rel))
                    except OSError as e:
                        self.note("ERROR_COPY", os.path.join(dest_root, rel), repr(e))
            elif kind == "link":
                self.tot["symlinks"] += 1
                if self.apply:
                    self._recreate_symlink(
                        os.path.join(src, rel), os.path.join(dest_root, rel), posixpath.join(dest_rel, rel)
                    )
            elif rel in skip_sidecar:
                continue
            elif rel in dbs:
                s = os.path.join(src, rel)
                if not self.apply:
                    self.sqlite_stores[s] = self.dry_probe_sqlite(s)
                    wal = self._regular(s + "-wal")
                    self.tot["snapshots"] += 1
                    self.tot["snapshot_bytes"] += st.st_size + (wal.st_size if wal else 0)
                elif not self.snapshot_sqlite(s, os.path.join(dest_root, rel), posixpath.join(dest_rel, rel)):
                    self.tot["trio_fallbacks"] += 1
                    todo.append((rel, st))
                    for sc in SIDECARS:
                        side = self._regular(s + sc)
                        if side:
                            todo.append((rel + sc, side))
            else:
                todo.append((rel, st))
        self.tot["files"] += len(todo)
        self.tot["bytes"] += sum(st.st_size for _, st in todo)
        if not self.apply:
            return
        copied = []
        for rel, st in todo:
            self.check_deadline()
            s, d = os.path.join(src, rel), os.path.join(dest_root, rel)
            try:
                self.ensure_dir(os.path.dirname(d))
                sha = copy_hash(s, d, st, self.check_deadline)
            except OSError as e:
                self.note("ERROR_COPY", s, repr(e))
                continue
            try:
                after = os.lstat(s)
                drift = (after.st_size, after.st_mtime_ns, after.st_ino) != (st.st_size, st.st_mtime_ns, st.st_ino)
            except OSError:
                drift = True  # the source vanished while it was being copied
            copied.append((rel, sha, st, drift))
        os.sync()
        for rel, sha, st, drift in copied:
            self.check_deadline()
            s, d = os.path.join(src, rel), os.path.join(dest_root, rel)
            rel_run = posixpath.join(dest_rel, rel)
            if drift:
                self.note(
                    "DRIFT",
                    s,
                    f"source changed while being copied; unverified copy left at {rel_run}; re-run this item",
                )
                continue
            try:
                dsha = sha_file(d, nocache=True, check=self.check_deadline)
            except OSError:
                self.note("MISSING", d)
                continue
            if dsha != sha or os.path.getsize(d) != st.st_size:
                self.note("MISMATCH", d, f"src={sha} dst={dsha}")
                continue
            self.record(sha, st.st_size, rel_run, "file")
            self.tot["verified"] += 1

    def _recreate_symlink(self, src: str, dst: str, rel_run: str) -> None:
        try:
            target = os.readlink(src)
            self.ensure_dir(os.path.dirname(dst))
            os.symlink(target, dst)
            if os.readlink(dst) != target:
                self.note("MISMATCH", dst, "symlink target differs after creation")
                return
        except OSError as e:
            self.note("ERROR_SYMLINK", dst, repr(e))
            return
        digest = hashlib.sha256(os.fsencode(target)).hexdigest()
        self.record_symlink(digest, len(os.fsencode(target)), rel_run, target)

    def record_symlink(self, digest: str, size: int, rel_run: str, target: str) -> None:
        # Symlinks are verified by readlink and listed in MANIFEST.tsv only: `shasum -c` cannot check a link.
        self.tsv_fh.write(
            "\t".join([digest, str(size), tsv_cell(rel_run), tsv_cell("symlink;target=" + target)]) + "\n"
        )

    # -- the run ----------------------------------------------------------------------------------------------
    def run(self, items: list[Item]) -> tuple[str, int]:
        """Execute every item; return (result text, exit code). apply also writes the run directory."""
        check_items(items, self.run_dir)
        if self.apply:
            parent = os.path.dirname(self.run_dir)
            if not os.path.isdir(parent):
                raise HomingError(f"the parent of the run directory does not exist: {parent}")
            try:
                os.mkdir(self.run_dir)  # fails if it exists: every run is a new directory
            except FileExistsError:
                raise RunDirExists(f"run directory already exists: {self.run_dir}") from None
            self._run_real = os.path.realpath(self.run_dir)
            # line-buffered, so a hard kill leaves a manifest of everything verified so far
            self.manifest_fh = open(
                os.path.join(self.run_dir, "MANIFEST.sha256"),
                "x",
                buffering=1,
                encoding="utf-8",
                errors="surrogateescape",
            )
            self.tsv_fh = open(
                os.path.join(self.run_dir, "MANIFEST.tsv"), "x", buffering=1, encoding="utf-8", errors="surrogateescape"
            )
            self.tsv_fh.write("sha256\tbytes\trel_path\tkind\n")
        try:
            for item in items:
                self.run_item(item)
        except DeadlineExceeded:
            self.deadline_hit = True
            self.note("DEADLINE", "", f"the {self.deadline_sec:.0f}s run deadline passed; remaining work was not done")
        finally:
            if self.apply:
                self.manifest_fh.close()
                self.tsv_fh.close()
        if self.apply:
            with open(
                os.path.join(self.run_dir, "EXCLUDED.tsv"), "x", encoding="utf-8", errors="surrogateescape"
            ) as fh:
                fh.write("kind\tsource_path\tbytes\treason\n")
                for kind, path, size, why in self.excluded_rows:
                    fh.write("\t".join([kind, tsv_cell(path), str(size), tsv_cell(why)]) + "\n")
            if not self.problems and self.tot["verified"] == 0:
                self.note(
                    "NOTHING_VERIFIED", "", "no file was copied and verified (empty sources, or everything excluded)"
                )
        ok = not self.problems and (not self.apply or self.tot["verified"] == self.tot["files"] + self.tot["snapshots"])
        text = self.result_text(len(items), ok)
        if self.apply:
            with open(os.path.join(self.run_dir, "RESULT.txt"), "x", encoding="utf-8", errors="surrogateescape") as fh:
                fh.write(text)
        return text, EXIT_OK if ok else EXIT_FAIL

    def result_text(self, n_items: int, ok: bool) -> str:
        mode = "apply" if self.apply else "dry"
        lines = [
            f"mode={mode}",
            f"run_dir={tsv_cell(self.run_dir)}",
            f"started={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(self.started))}",
            f"finished={utc_now()}",
            f"seconds={time.time() - self.started:.0f}",
            f"items={n_items}",
        ] + [f"{k}={v}" for k, v in self.tot.items()]
        lines.append(f"PLAN_TOTAL_BYTES={self.tot['bytes'] + self.tot['snapshot_bytes']}")
        for name, stats in self.item_stats:
            lines.append(f"item[{tsv_cell(name)}]=" + " ".join(f"{k}={v}" for k, v in stats.items()))
        lines += [f"sqlite_store={tsv_cell(src)} {state}" for src, state in self.sqlite_stores.items()]
        lines += [f"excluded[{k}]={tsv_cell(p)} bytes={b} {tsv_cell(why)}" for k, p, b, why in self.excluded_rows[:300]]
        if len(self.excluded_rows) > 300:
            lines.append(f"excluded_overflow={len(self.excluded_rows) - 300} (all rows are in EXCLUDED.tsv on apply)")
        lines += [f"problem={k} {tsv_cell(p)} {tsv_cell(d)}" for k, p, d in self.problems[:200]]
        if len(self.problems) > 200:
            lines.append(f"problem_overflow={len(self.problems) - 200}")
        if self.apply:
            lines.append("RESULT: " + ("PASS" if ok else "FAIL"))
        else:
            lines.append("RESULT: " + ("DRY-RUN (nothing written)" if ok else "DRY-RUN-PROBLEMS (apply would fail)"))
        return "\n".join(lines) + "\n"


def split_globs(text: str) -> list[str]:
    return [g for g in text.split(";") if g]


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("dry", "apply"))
    parser.add_argument("run_dir")
    parser.add_argument("items_tsv")
    parser.add_argument("--home", default=os.environ.get("HOME") or os.path.expanduser("~"))
    parser.add_argument(
        "--sqlite", default=None, help="sqlite3 CLI (default: $NONGIT_HOMING_SQLITE, /usr/bin/sqlite3, PATH)"
    )
    parser.add_argument("--deadline-sec", type=float, default=0.0, help="hard wall for the whole run (0 = none)")
    parser.add_argument(
        "--extra-cred-file-globs", default="", help="';'-separated credential file globs ADDED to the defaults"
    )
    parser.add_argument(
        "--extra-cred-dir-globs", default="", help="';'-separated credential directory globs ADDED to the defaults"
    )
    args = parser.parse_args(argv)
    try:
        sqlite_bin = find_sqlite(args.sqlite)
        items = parse_items(args.items_tsv, args.home)
        homer = Homer(
            apply=args.mode == "apply",
            run_dir=args.run_dir,
            sqlite_bin=sqlite_bin,
            cred_file_globs=CRED_FILE_GLOBS + split_globs(args.extra_cred_file_globs),
            cred_dir_globs=CRED_DIR_GLOBS + split_globs(args.extra_cred_dir_globs),
            deadline_sec=args.deadline_sec,
        )
        text, code = homer.run(items)
    except HomingError as e:
        print(f"nongit_homing: {e}", file=sys.stderr)
        return e.code
    except RunDirExists as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return EXIT_RUN_DIR_EXISTS
    sys.stdout.write(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
