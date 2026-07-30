"""Exact-head external custody for generated estate-audit checkout failures."""

from __future__ import annotations

import hashlib
import json
import os
import plistlib
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import tempfile
import time
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from limen.agent_state.custody import _device_identity
from limen.agent_state.models import ReceiptError
from limen.agent_state.pipeline import PipelineError, require_mounted_external
from limen.worktree_roots import WorktreeTarget, iter_worktree_targets

PLAN_SCHEMA = "limen.estate_audit_custody_plan.v1"
RECEIPT_SCHEMA = "limen.estate_audit_custody_receipt.v1"
GENERATED_ROOT_RE = re.compile(r"^estate-audit-.+-[0-9]{14}$")
GITHUB_REMOTE_RE = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
    r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$"
)
OBJECT_ID_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
GIT = shutil.which("git", path=os.defpath) or "/usr/bin/git"
_GH = shutil.which("gh")
GH = str(Path(_GH).resolve()) if _GH else None
DEFAULT_CUSTODY_ROOT = Path("/Volumes/Archive4T/limen-private/estate-audit-git-custody")
MAX_ROOTS = 1000
MAX_SECONDS = 900
MAX_PAYLOAD_FILES = 10000
MAX_PAYLOAD_FILE_BYTES = 512 * 1024 * 1024
MAX_PAYLOAD_TOTAL_BYTES = 4 * 1024 * 1024 * 1024
PAYLOAD_CHUNK_BYTES = 1024 * 1024
MAX_CUSTODY_RECEIPT_BYTES = 32 * 1024 * 1024
VOLUME_UUID_RE = re.compile(r"^[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}$")
PHYSICAL_IDENTITY_RE = re.compile(r"^device_[0-9a-f]{32}$")
IdentityGuard = Callable[[Path], None]


class EstateAuditCustodyError(RuntimeError):
    """A custody predicate failed closed with a bounded public error code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class GeneratedRootRecord:
    path: str
    path_sha256: str
    source: str
    repository: str
    head: str
    tree: str
    tree_entry_count: int
    index_entry_count: int
    index_sha256: str
    device: int
    inode: int
    mtime_ns: int


@dataclass(frozen=True)
class CustodyPlan:
    roots: tuple[GeneratedRootRecord, ...]
    plan_sha256: str

    @property
    def repository_count(self) -> int:
        return len({root.repository for root in self.roots})

    @property
    def head_count(self) -> int:
        return len({(root.repository, root.head) for root in self.roots})

    @property
    def empty_index_root_count(self) -> int:
        return sum(root.index_entry_count == 0 for root in self.roots)

    @property
    def indexed_root_count(self) -> int:
        return len(self.roots) - self.empty_index_root_count

    def private_payload(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA,
            "roots": [asdict(root) for root in self.roots],
        }

    def public_payload(self) -> dict[str, Any]:
        return {
            "schema": PLAN_SCHEMA,
            "status": "ready",
            "root_count": len(self.roots),
            "repository_count": self.repository_count,
            "head_count": self.head_count,
            "empty_index_root_count": self.empty_index_root_count,
            "indexed_root_count": self.indexed_root_count,
            "plan_sha256": self.plan_sha256,
        }


@dataclass(frozen=True)
class CheckoutContentProof:
    path_sha256: str
    head: str
    tree: str
    file_count: int
    content_sha256: str
    exact: bool
    reason: str


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _path_sha256(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8", errors="surrogateescape")).hexdigest()


def _git_environment(*, github_auth: bool = False) -> dict[str, str]:
    """Use Git without ambient signers, credential prompts, hooks, or user configuration."""

    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "HOME": str(Path.home()),
        "LC_ALL": "C",
        "PATH": os.defpath,
    }
    if github_auth:
        if not GH or not Path(GH).is_file() or not os.access(GH, os.X_OK):
            raise EstateAuditCustodyError("github-credential-helper-unavailable")
        environment.update(
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "credential.https://github.com.helper",
                "GIT_CONFIG_VALUE_0": f"!{shlex.quote(GH)} auth git-credential",
            }
        )
    return environment


def _run_git(
    cwd: Path,
    arguments: Iterable[str],
    *,
    timeout: float = 120,
    input_bytes: bytes | None = None,
    stdin: Any = None,
    github_auth: bool = False,
) -> subprocess.CompletedProcess[bytes]:
    if timeout <= 0:
        raise EstateAuditCustodyError("campaign-time-limit-exceeded")
    try:
        return subprocess.run(
            [GIT, "-c", "protocol.file.allow=always", *arguments],
            cwd=str(cwd),
            env=_git_environment(github_auth=github_auth),
            input=input_bytes,
            stdin=stdin,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EstateAuditCustodyError("git-execution-failed", type(exc).__name__) from exc


def _git_bytes(cwd: Path, *arguments: str, timeout: float = 120, github_auth: bool = False) -> bytes:
    result = _run_git(cwd, arguments, timeout=timeout, github_auth=github_auth)
    if result.returncode:
        detail = result.stderr.decode("utf-8", errors="replace").strip()[:300]
        raise EstateAuditCustodyError("git-command-failed", detail or f"exit-{result.returncode}")
    return result.stdout


def _git_text(cwd: Path, *arguments: str, timeout: float = 120, github_auth: bool = False) -> str:
    return (
        _git_bytes(cwd, *arguments, timeout=timeout, github_auth=github_auth).decode("utf-8", errors="strict").strip()
    )


def _github_repository(remote: str) -> str:
    match = GITHUB_REMOTE_RE.fullmatch(remote.strip())
    if not match:
        raise EstateAuditCustodyError("non-github-origin")
    return f"{match.group('owner').lower()}/{match.group('repo').lower()}"


def _object_id(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if not OBJECT_ID_RE.fullmatch(normalized):
        raise EstateAuditCustodyError(f"invalid-{label}")
    return normalized


def _scan_timeout(deadline: float | None) -> float:
    if deadline is None:
        return 120
    remaining = _remaining(deadline)
    if remaining < 1:
        raise EstateAuditCustodyError("campaign-time-limit-exceeded")
    return min(120, remaining)


def _root_record(
    target: WorktreeTarget,
    *,
    deadline: float | None = None,
) -> GeneratedRootRecord:
    try:
        path = target.path.expanduser().resolve(strict=True)
        before = path.lstat()
    except OSError as exc:
        raise EstateAuditCustodyError("root-unavailable", type(exc).__name__) from exc
    if path.is_symlink() or not stat.S_ISDIR(before.st_mode):
        raise EstateAuditCustodyError("root-not-directory")
    if _git_text(path, "rev-parse", "--is-inside-work-tree", timeout=_scan_timeout(deadline)) != "true":
        raise EstateAuditCustodyError("root-not-git-checkout")
    index = _git_bytes(path, "ls-files", "-s", "-z", timeout=_scan_timeout(deadline))
    index_entries = [value for value in index.split(b"\0") if value]
    repository = _github_repository(_git_text(path, "remote", "get-url", "origin", timeout=_scan_timeout(deadline)))
    head = _object_id(
        _git_text(path, "rev-parse", "HEAD", timeout=_scan_timeout(deadline)),
        label="head",
    )
    tree = _object_id(
        _git_text(path, "rev-parse", "HEAD^{tree}", timeout=_scan_timeout(deadline)),
        label="tree",
    )
    tree_entries = [
        value
        for value in _git_bytes(
            path,
            "ls-tree",
            "-r",
            "--name-only",
            "-z",
            "HEAD",
            timeout=_scan_timeout(deadline),
        ).split(b"\0")
        if value
    ]
    try:
        after = path.lstat()
    except OSError as exc:
        raise EstateAuditCustodyError("root-changed-during-scan", type(exc).__name__) from exc
    if (before.st_dev, before.st_ino, before.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_mtime_ns):
        raise EstateAuditCustodyError("root-changed-during-scan")
    return GeneratedRootRecord(
        path=str(path),
        path_sha256=_path_sha256(path),
        source=target.source,
        repository=repository,
        head=head,
        tree=tree,
        tree_entry_count=len(tree_entries),
        index_entry_count=len(index_entries),
        index_sha256=hashlib.sha256(index).hexdigest(),
        device=int(after.st_dev),
        inode=int(after.st_ino),
        mtime_ns=int(after.st_mtime_ns),
    )


def discover_plan(
    limen_root: Path,
    *,
    targets: Iterable[WorktreeTarget] | None = None,
    max_roots: int = 1000,
    deadline: float | None = None,
) -> CustodyPlan:
    if max_roots <= 0 or max_roots > MAX_ROOTS:
        raise EstateAuditCustodyError("invalid-root-limit")
    if deadline is not None:
        _remaining(deadline)
    candidates = list(targets) if targets is not None else iter_worktree_targets(limen_root, strict=True)
    if deadline is not None:
        _remaining(deadline)
    selected = [target for target in candidates if GENERATED_ROOT_RE.fullmatch(target.path.name)]
    if len(selected) > max_roots:
        raise EstateAuditCustodyError("root-limit-exceeded")
    if not selected:
        raise EstateAuditCustodyError("no-generated-roots")
    records: list[GeneratedRootRecord] = []
    seen: set[str] = set()
    for target in sorted(selected, key=lambda value: str(value.path)):
        if deadline is not None:
            _remaining(deadline)
        record = _root_record(target, deadline=deadline)
        if record.path in seen:
            continue
        seen.add(record.path)
        records.append(record)
    payload = {"schema": PLAN_SCHEMA, "roots": [asdict(record) for record in records]}
    return CustodyPlan(roots=tuple(records), plan_sha256=_canonical_sha256(payload))


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise EstateAuditCustodyError("campaign-time-limit-exceeded")
    return remaining


def _repository_groups(plan: CustodyPlan) -> dict[str, dict[str, str]]:
    groups: dict[str, dict[str, str]] = {}
    for root in plan.roots:
        heads = groups.setdefault(root.repository, {})
        previous = heads.setdefault(root.head, root.tree)
        if previous != root.tree:
            raise EstateAuditCustodyError("head-tree-conflict")
    return groups


def _ref_for_head(head: str) -> str:
    return f"refs/limen-custody/{head}"


def _repository_store(custody_root: Path, repository: str) -> tuple[str, Path]:
    repository_sha256 = hashlib.sha256(repository.encode("utf-8")).hexdigest()
    return repository_sha256, custody_root / "repositories" / f"{repository_sha256}.git"


def _has_exact_ref(store: Path, head: str, tree: str, *, timeout: float) -> bool:
    if not store.is_dir():
        return False
    ref = _ref_for_head(head)
    result = _run_git(store, ["rev-parse", "--verify", ref], timeout=timeout)
    if result.returncode or result.stdout.decode().strip() != head:
        return False
    result = _run_git(store, ["rev-parse", f"{ref}^{{tree}}"], timeout=timeout)
    return result.returncode == 0 and result.stdout.decode().strip() == tree


def _restore_repository(store: Path, heads: dict[str, str], custody_root: Path, *, deadline: float) -> None:
    with tempfile.TemporaryDirectory(prefix=".restore-", dir=custody_root) as temporary:
        restore = Path(temporary) / "restore.git"
        _git_bytes(custody_root, "init", "--bare", "--quiet", str(restore), timeout=_remaining(deadline))
        source = store.resolve().as_uri()
        for head, tree in sorted(heads.items()):
            ref = _ref_for_head(head)
            restore_ref = f"refs/restore/{head}"
            _git_bytes(
                restore,
                "fetch",
                "--quiet",
                "--no-tags",
                source,
                f"{ref}:{restore_ref}",
                timeout=_remaining(deadline),
            )
            if _git_text(restore, "rev-parse", restore_ref, timeout=_remaining(deadline)) != head:
                raise EstateAuditCustodyError("restored-head-mismatch")
            if _git_text(restore, "rev-parse", f"{restore_ref}^{{tree}}", timeout=_remaining(deadline)) != tree:
                raise EstateAuditCustodyError("restored-tree-mismatch")
        _git_bytes(restore, "fsck", "--full", "--strict", "--no-progress", timeout=_remaining(deadline))


def _ensure_repository(
    custody_root: Path,
    repository: str,
    heads: dict[str, str],
    *,
    deadline: float,
    remote_url: str,
) -> tuple[dict[str, Any], bool]:
    repository_sha256, store = _repository_store(custody_root, repository)
    changed = False
    store.parent.mkdir(parents=True, exist_ok=True)
    if not store.exists():
        _git_bytes(custody_root, "init", "--bare", "--quiet", str(store), timeout=_remaining(deadline))
        changed = True
    if _git_text(store, "rev-parse", "--is-bare-repository", timeout=_remaining(deadline)) != "true":
        raise EstateAuditCustodyError("custody-store-not-bare")

    missing = {
        head: tree
        for head, tree in heads.items()
        if not _has_exact_ref(store, head, tree, timeout=_remaining(deadline))
    }
    if missing:
        github_auth = remote_url.startswith("https://github.com/")
        with tempfile.TemporaryDirectory(prefix=".source-", dir=custody_root) as temporary:
            source = Path(temporary) / "source.git"
            _git_bytes(
                custody_root,
                "clone",
                "--mirror",
                "--quiet",
                remote_url,
                str(source),
                timeout=_remaining(deadline),
                github_auth=github_auth,
            )
            for head, tree in sorted(missing.items()):
                exists = _run_git(source, ["cat-file", "-e", f"{head}^{{commit}}"], timeout=_remaining(deadline))
                if exists.returncode:
                    _git_bytes(
                        source,
                        "fetch",
                        "--quiet",
                        "--no-tags",
                        "origin",
                        head,
                        timeout=_remaining(deadline),
                        github_auth=github_auth,
                    )
                if _git_text(source, "rev-parse", f"{head}^{{tree}}", timeout=_remaining(deadline)) != tree:
                    raise EstateAuditCustodyError("remote-tree-mismatch")
                ref = _ref_for_head(head)
                current = _run_git(store, ["rev-parse", "--verify", ref], timeout=_remaining(deadline))
                if current.returncode == 0 and current.stdout.decode().strip() != head:
                    raise EstateAuditCustodyError("immutable-custody-ref-conflict")
                if current.returncode:
                    _git_bytes(
                        source,
                        "push",
                        "--quiet",
                        store.resolve().as_uri(),
                        f"{head}:{ref}",
                        timeout=_remaining(deadline),
                    )
                    changed = True

    for head, tree in heads.items():
        if not _has_exact_ref(store, head, tree, timeout=_remaining(deadline)):
            raise EstateAuditCustodyError("custody-ref-verification-failed")
    _git_bytes(store, "fsck", "--full", "--strict", "--no-progress", timeout=_remaining(deadline))
    _restore_repository(store, heads, custody_root, deadline=deadline)
    return (
        {
            "repository": repository,
            "repository_sha256": repository_sha256,
            "store": store.relative_to(custody_root).as_posix(),
            "heads": [{"head": head, "tree": tree} for head, tree in sorted(heads.items())],
            "restoration_passed": True,
        },
        changed,
    )


def _atomic_private_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{secrets.token_hex(4)}.tmp")
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def _receipt_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"


def _read_receipt_entry(directory: int, filename: str) -> bytes | None:
    try:
        descriptor = os.open(
            filename,
            os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=directory,
        )
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise EstateAuditCustodyError("custody-receipt-version-unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise EstateAuditCustodyError("custody-receipt-version-not-regular")
        if stat.S_IMODE(info.st_mode) != 0o600:
            raise EstateAuditCustodyError("custody-receipt-version-mode-invalid")
        if info.st_size > MAX_CUSTODY_RECEIPT_BYTES:
            raise EstateAuditCustodyError("custody-receipt-version-size-limit")
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            encoded = handle.read(MAX_CUSTODY_RECEIPT_BYTES + 1)
        if len(encoded) > MAX_CUSTODY_RECEIPT_BYTES:
            raise EstateAuditCustodyError("custody-receipt-version-size-limit")
        return encoded
    except EstateAuditCustodyError:
        raise
    except OSError as exc:
        raise EstateAuditCustodyError("custody-receipt-version-unavailable") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _preserve_canonical_receipt(
    custody_root: Path,
    plan_sha256: str,
    receipt: dict[str, Any],
    *,
    deadline: float,
) -> bool:
    _remaining(deadline)
    content_sha256 = str(receipt.get("content_sha256") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", content_sha256):
        raise EstateAuditCustodyError("custody-receipt-content-mismatch")
    canonical_name = f"{plan_sha256}.json"
    version_name = f"{plan_sha256}.{content_sha256}.json"
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory = os.open(custody_root / "receipts", flags)
    except OSError as exc:
        raise EstateAuditCustodyError("custody-receipt-version-unavailable") from exc
    temporary: str | None = None
    try:
        _remaining(deadline)
        canonical = _read_receipt_entry(directory, canonical_name)
        if canonical is None or canonical != _receipt_json_bytes(receipt):
            raise EstateAuditCustodyError("custody-receipt-changed-before-rotation")
        _remaining(deadline)
        version = _read_receipt_entry(directory, version_name)
        if version is not None:
            if version != canonical:
                raise EstateAuditCustodyError("custody-receipt-version-conflict")
            return False

        _remaining(deadline)
        temporary = f".{version_name}.{os.getpid()}.{secrets.token_hex(4)}.tmp"
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
            dir_fd=directory,
        )
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o600)
            handle.write(canonical)
            handle.flush()
            os.fsync(handle.fileno())
        _remaining(deadline)
        try:
            os.link(
                temporary,
                version_name,
                src_dir_fd=directory,
                dst_dir_fd=directory,
                follow_symlinks=False,
            )
        except FileExistsError:
            version = _read_receipt_entry(directory, version_name)
            if version != canonical:
                raise EstateAuditCustodyError("custody-receipt-version-conflict")
            return False
        _remaining(deadline)
        version = _read_receipt_entry(directory, version_name)
        if version != canonical:
            raise EstateAuditCustodyError("custody-receipt-version-conflict")
        os.fsync(directory)
        return True
    except EstateAuditCustodyError:
        raise
    except OSError as exc:
        raise EstateAuditCustodyError("custody-receipt-version-write-failed") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
            except OSError:
                pass
        os.close(directory)


def _receipt_path(custody_root: Path, plan_sha256: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", plan_sha256):
        raise EstateAuditCustodyError("invalid-plan-sha")
    return custody_root / "receipts" / f"{plan_sha256}.json"


def _resolved_custody_root(custody_root: Path) -> Path:
    expanded = Path(os.path.expanduser(custody_root))
    if ".." in expanded.parts:
        raise EstateAuditCustodyError("custody-target-path-indirection")
    candidate = Path(os.path.abspath(expanded))
    current = Path(candidate.anchor)
    for part in candidate.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            break
        except OSError as exc:
            raise EstateAuditCustodyError("custody-target-identity-unavailable") from exc
        if stat.S_ISLNK(info.st_mode):
            raise EstateAuditCustodyError("custody-target-path-indirection")
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise EstateAuditCustodyError("custody-target-identity-unavailable") from exc
    if resolved != candidate:
        raise EstateAuditCustodyError("custody-target-path-indirection")
    return resolved


def _external_custody_root(custody_root: Path) -> Path:
    candidate = _resolved_custody_root(custody_root)
    try:
        resolved = require_mounted_external(candidate)
    except PipelineError as exc:
        raise EstateAuditCustodyError("external-custody-unavailable") from exc
    if resolved != candidate:
        raise EstateAuditCustodyError("custody-target-path-indirection")
    return resolved


def _load_receipt(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise EstateAuditCustodyError("custody-receipt-unavailable", type(exc).__name__) from exc
    if not stat.S_ISREG(info.st_mode) or path.is_symlink():
        raise EstateAuditCustodyError("custody-receipt-not-regular")
    if stat.S_IMODE(info.st_mode) != 0o600:
        raise EstateAuditCustodyError("custody-receipt-mode-invalid")
    if info.st_size > MAX_CUSTODY_RECEIPT_BYTES:
        raise EstateAuditCustodyError("custody-receipt-size-limit")
    try:
        with path.open("rb") as handle:
            encoded = handle.read(MAX_CUSTODY_RECEIPT_BYTES + 1)
        if len(encoded) > MAX_CUSTODY_RECEIPT_BYTES:
            raise EstateAuditCustodyError("custody-receipt-size-limit")
        payload = json.loads(encoded)
    except EstateAuditCustodyError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EstateAuditCustodyError("custody-receipt-unavailable", type(exc).__name__) from exc
    if not isinstance(payload, dict) or payload.get("schema") != RECEIPT_SCHEMA:
        raise EstateAuditCustodyError("custody-receipt-schema-mismatch")
    content = {key: value for key, value in payload.items() if key != "content_sha256"}
    if payload.get("content_sha256") != _canonical_sha256(content):
        raise EstateAuditCustodyError("custody-receipt-content-mismatch")
    return payload


def assert_custody_target_identity(
    custody_root: Path,
    *,
    expected_volume_uuid: str,
    expected_physical_identity: str,
) -> None:
    """Fail closed unless one target remains on the exact registered physical medium."""

    expected_uuid = expected_volume_uuid.upper()
    if not VOLUME_UUID_RE.fullmatch(expected_uuid):
        raise EstateAuditCustodyError("expected-volume-uuid-invalid")
    if not PHYSICAL_IDENTITY_RE.fullmatch(expected_physical_identity):
        raise EstateAuditCustodyError("expected-physical-identity-invalid")
    candidate = _resolved_custody_root(custody_root)
    probe = candidate
    while not probe.exists() and probe != probe.parent:
        probe = probe.parent
    try:
        result = subprocess.run(
            ["/usr/sbin/diskutil", "info", "-plist", str(probe)],
            capture_output=True,
            check=False,
            timeout=20,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode:
            raise EstateAuditCustodyError("custody-target-identity-unavailable")
        payload = plistlib.loads(result.stdout)
        observed_mount = Path(os.path.abspath(str(payload["MountPoint"])))
        observed_uuid = str(payload["VolumeUUID"]).upper()
        try:
            candidate.relative_to(observed_mount)
        except ValueError as exc:
            raise EstateAuditCustodyError("custody-target-identity-mismatch") from exc
        physical_identity = _device_identity(observed_mount)
    except EstateAuditCustodyError:
        raise
    except (
        KeyError,
        OSError,
        ReceiptError,
        TypeError,
        subprocess.SubprocessError,
        plistlib.InvalidFileException,
    ) as exc:
        raise EstateAuditCustodyError("custody-target-identity-unavailable") from exc
    if observed_uuid != expected_uuid or physical_identity != expected_physical_identity:
        raise EstateAuditCustodyError("custody-target-identity-mismatch")


def _assert_identity(identity_guard: IdentityGuard | None, custody_root: Path) -> None:
    if identity_guard is not None:
        identity_guard(custody_root)


def _payload_relative(payload_sha256: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", payload_sha256):
        raise EstateAuditCustodyError("invalid-payload-sha")
    return Path("payloads") / payload_sha256[:2] / payload_sha256


def _stream_working_payload(
    root: Path,
    relative: str,
    expected_mode: str,
    *,
    destination: Path | None,
    deadline: float,
) -> tuple[str, int]:
    candidate = root / relative
    try:
        before = candidate.lstat()
    except OSError as exc:
        raise EstateAuditCustodyError("working-file-unavailable", type(exc).__name__) from exc
    if expected_mode == "120000":
        if not stat.S_ISLNK(before.st_mode):
            raise EstateAuditCustodyError("working-mode-mismatch")
        payload = os.readlink(candidate).encode("utf-8", errors="surrogateescape")
        if len(payload) > MAX_PAYLOAD_FILE_BYTES:
            raise EstateAuditCustodyError("payload-file-limit-exceeded")
        digest = hashlib.sha256(payload).hexdigest()
        if destination is not None:
            destination.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "wb") as output:
                output.write(payload)
                output.flush()
                os.fsync(output.fileno())
        total = len(payload)
    elif expected_mode in {"100644", "100755"}:
        if not stat.S_ISREG(before.st_mode):
            raise EstateAuditCustodyError("working-mode-mismatch")
        executable = bool(before.st_mode & stat.S_IXUSR)
        if executable != (expected_mode == "100755"):
            raise EstateAuditCustodyError("working-mode-mismatch")
        digest_state = hashlib.sha256()
        total = 0
        output = None
        try:
            if destination is not None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                output = os.fdopen(descriptor, "wb")
            with candidate.open("rb") as source:
                while chunk := source.read(PAYLOAD_CHUNK_BYTES):
                    _remaining(deadline)
                    total += len(chunk)
                    if total > MAX_PAYLOAD_FILE_BYTES:
                        raise EstateAuditCustodyError("payload-file-limit-exceeded")
                    digest_state.update(chunk)
                    if output is not None:
                        output.write(chunk)
            if output is not None:
                output.flush()
                os.fsync(output.fileno())
            digest = digest_state.hexdigest()
        except OSError as exc:
            raise EstateAuditCustodyError("working-file-unavailable", type(exc).__name__) from exc
        finally:
            if output is not None:
                output.close()
    else:
        raise EstateAuditCustodyError("unsupported-tree-mode")
    try:
        after = candidate.lstat()
    except OSError as exc:
        raise EstateAuditCustodyError("working-file-changed", type(exc).__name__) from exc
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise EstateAuditCustodyError("working-file-changed")
    return digest, total


def _stored_payload_digest(path: Path, *, deadline: float) -> tuple[str, int]:
    try:
        info = path.lstat()
    except OSError as exc:
        raise EstateAuditCustodyError("payload-store-unavailable", type(exc).__name__) from exc
    if not stat.S_ISREG(info.st_mode) or path.is_symlink() or stat.S_IMODE(info.st_mode) != 0o600:
        raise EstateAuditCustodyError("payload-store-invalid")
    digest = hashlib.sha256()
    total = 0
    try:
        with path.open("rb") as source:
            while chunk := source.read(PAYLOAD_CHUNK_BYTES):
                _remaining(deadline)
                digest.update(chunk)
                total += len(chunk)
    except OSError as exc:
        raise EstateAuditCustodyError("payload-store-unavailable", type(exc).__name__) from exc
    return digest.hexdigest(), total


def _ensure_payload(
    custody_root: Path,
    source_root: Path,
    relative: str,
    mode: str,
    *,
    deadline: float,
) -> tuple[str, int, str, bool]:
    incoming = custody_root / "payloads" / f".incoming-{os.getpid()}-{secrets.token_hex(8)}"
    try:
        payload_sha256, payload_bytes = _stream_working_payload(
            source_root,
            relative,
            mode,
            destination=incoming,
            deadline=deadline,
        )
        relative_store = _payload_relative(payload_sha256)
        store = custody_root / relative_store
        if store.exists():
            stored_sha256, stored_bytes = _stored_payload_digest(store, deadline=deadline)
            if (stored_sha256, stored_bytes) != (payload_sha256, payload_bytes):
                raise EstateAuditCustodyError("payload-store-content-mismatch")
            return payload_sha256, payload_bytes, relative_store.as_posix(), False
        store.parent.mkdir(parents=True, exist_ok=True)
        os.replace(incoming, store)
        os.chmod(store, 0o600)
        directory = os.open(store.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        return payload_sha256, payload_bytes, relative_store.as_posix(), True
    finally:
        incoming.unlink(missing_ok=True)


def _failed_checkout_state(
    root_record: GeneratedRootRecord,
    custody_root: Path,
    *,
    deadline: float,
    capture: bool,
) -> tuple[dict[str, Any], bool]:
    root = Path(root_record.path).resolve(strict=True)
    info = root.lstat()
    if (info.st_dev, info.st_ino, info.st_mtime_ns) != (
        root_record.device,
        root_record.inode,
        root_record.mtime_ns,
    ):
        raise EstateAuditCustodyError("root-changed-before-payload-capture")
    index = _git_bytes(root, "ls-files", "-s", "-z", timeout=_remaining(deadline))
    if index or hashlib.sha256(index).hexdigest() != root_record.index_sha256:
        raise EstateAuditCustodyError("failed-checkout-index-changed")
    if _git_text(root, "rev-parse", "HEAD", timeout=_remaining(deadline)) != root_record.head:
        raise EstateAuditCustodyError("failed-checkout-head-changed")
    if _git_text(root, "rev-parse", "HEAD^{tree}", timeout=_remaining(deadline)) != root_record.tree:
        raise EstateAuditCustodyError("failed-checkout-tree-changed")
    records = _tree_records(root, root_record.head)
    if any(kind != "blob" for _mode, kind, _object_id_value in records.values()):
        raise EstateAuditCustodyError("unsupported-tree-entry")
    working = _working_paths(root)
    if not set(working).issubset(records):
        raise EstateAuditCustodyError("failed-checkout-path-outside-head")

    exact_entries: list[tuple[str, str, str]] = []
    payloads: list[dict[str, Any]] = []
    changed = False
    for relative in sorted(working):
        mode, _kind, expected_object = records[relative]
        actual_object = _hash_working_path(root, relative, mode)
        if actual_object == expected_object:
            exact_entries.append((relative, mode, expected_object))
            continue
        if capture:
            payload_sha256, payload_bytes, store, payload_changed = _ensure_payload(
                custody_root,
                root,
                relative,
                mode,
                deadline=deadline,
            )
            changed = changed or payload_changed
        else:
            payload_sha256, payload_bytes = _stream_working_payload(
                root,
                relative,
                mode,
                destination=None,
                deadline=deadline,
            )
            store = _payload_relative(payload_sha256).as_posix()
        payloads.append(
            {
                "path": relative,
                "mode": mode,
                "head_blob": expected_object,
                "payload_sha256": payload_sha256,
                "payload_bytes": payload_bytes,
                "store": store,
            }
        )
    if set(_working_paths(root)) != set(working):
        raise EstateAuditCustodyError("failed-checkout-path-set-changed")
    content: dict[str, Any] = {
        "path_sha256": root_record.path_sha256,
        "head": root_record.head,
        "tree": root_record.tree,
        "working_file_count": len(working),
        "exact_head_file_count": len(exact_entries),
        "exact_head_entries_sha256": _canonical_sha256(exact_entries),
        "payload_count": len(payloads),
        "payload_bytes": sum(int(value["payload_bytes"]) for value in payloads),
        "payloads": payloads,
    }
    return {**content, "content_sha256": _canonical_sha256(content)}, changed


def _capture_failed_checkout_states(
    plan: CustodyPlan,
    custody_root: Path,
    *,
    deadline: float,
) -> tuple[list[dict[str, Any]], bool]:
    roots = [root for root in plan.roots if root.index_entry_count == 0]
    preliminary = [_failed_checkout_state(root, custody_root, deadline=deadline, capture=False)[0] for root in roots]
    payload_count = sum(int(state["payload_count"]) for state in preliminary)
    payload_bytes = sum(int(state["payload_bytes"]) for state in preliminary)
    if payload_count > MAX_PAYLOAD_FILES:
        raise EstateAuditCustodyError("payload-file-count-limit-exceeded")
    if payload_bytes > MAX_PAYLOAD_TOTAL_BYTES:
        raise EstateAuditCustodyError("payload-total-limit-exceeded")
    captured: list[dict[str, Any]] = []
    changed = False
    for root, expected in zip(roots, preliminary, strict=True):
        state, state_changed = _failed_checkout_state(root, custody_root, deadline=deadline, capture=True)
        if state != expected:
            raise EstateAuditCustodyError("failed-checkout-content-changed-during-capture")
        captured.append(state)
        changed = changed or state_changed
    return captured, changed


def _verify_failed_checkout_state(
    root_record: dict[str, Any],
    expected_state: dict[str, Any],
    *,
    deadline: float,
) -> str:
    try:
        record = GeneratedRootRecord(**root_record)
    except TypeError as exc:
        raise EstateAuditCustodyError("custody-root-record-invalid") from exc
    current, _changed = _failed_checkout_state(
        record,
        Path("."),
        deadline=deadline,
        capture=False,
    )
    if current != expected_state:
        raise EstateAuditCustodyError("failed-checkout-content-drift")
    return str(current["content_sha256"])


def verify_failed_checkout_state(
    root_record: dict[str, Any],
    expected_state: dict[str, Any],
    *,
    max_seconds: int = 900,
) -> str:
    """Immediately rehash one live failed checkout against its custody state."""

    if max_seconds <= 0 or max_seconds > MAX_SECONDS:
        raise EstateAuditCustodyError("invalid-time-limit")
    return _verify_failed_checkout_state(
        root_record,
        expected_state,
        deadline=time.monotonic() + max_seconds,
    )


def _verify_live_failed_checkout_states(
    receipt: dict[str, Any],
    *,
    deadline: float,
) -> None:
    roots = receipt.get("roots")
    states = receipt.get("failed_checkout_states")
    if not isinstance(roots, list) or not isinstance(states, list):
        raise EstateAuditCustodyError("custody-receipt-shape-invalid")
    empty_roots = {
        str(value.get("path_sha256") or ""): value
        for value in roots
        if isinstance(value, dict) and int(value.get("index_entry_count", -1)) == 0
    }
    if len(states) != len(empty_roots):
        raise EstateAuditCustodyError("failed-checkout-state-count-mismatch")
    for expected_state in states:
        if not isinstance(expected_state, dict):
            raise EstateAuditCustodyError("failed-checkout-state-invalid")
        root_record = empty_roots.get(str(expected_state.get("path_sha256") or ""))
        if root_record is None:
            raise EstateAuditCustodyError("failed-checkout-state-coverage-mismatch")
        _verify_failed_checkout_state(
            root_record,
            expected_state,
            deadline=deadline,
        )


def _payload_stats(states: list[dict[str, Any]]) -> dict[str, int]:
    payloads = [payload for state in states for payload in state["payloads"] if isinstance(payload, dict)]
    unique = {str(payload["payload_sha256"]): int(payload["payload_bytes"]) for payload in payloads}
    return {
        "failed_checkout_root_count": len(states),
        "working_payload_count": len(payloads),
        "working_payload_bytes": sum(int(payload["payload_bytes"]) for payload in payloads),
        "working_payload_unique_count": len(unique),
        "working_payload_unique_bytes": sum(unique.values()),
    }


def _receipt_for_plan(
    plan: CustodyPlan,
    repositories: list[dict[str, Any]],
    failed_checkout_states: list[dict[str, Any]],
) -> dict[str, Any]:
    content: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "plan_sha256": plan.plan_sha256,
        "root_count": len(plan.roots),
        "repository_count": plan.repository_count,
        "head_count": plan.head_count,
        "empty_index_root_count": plan.empty_index_root_count,
        "indexed_root_count": plan.indexed_root_count,
        **_payload_stats(failed_checkout_states),
        "roots": [asdict(root_record) for root_record in plan.roots],
        "repositories": repositories,
        "failed_checkout_states": failed_checkout_states,
        "restoration_passed": True,
    }
    return {**content, "content_sha256": _canonical_sha256(content)}


def preflight_plan(
    plan: CustodyPlan,
    *,
    max_seconds: int = MAX_SECONDS,
    deadline: float | None = None,
) -> dict[str, Any]:
    if max_seconds <= 0 or max_seconds > MAX_SECONDS:
        raise EstateAuditCustodyError("invalid-time-limit")
    effective_deadline = deadline or time.monotonic() + max_seconds
    _remaining(effective_deadline)
    states = [
        _failed_checkout_state(root, Path("."), deadline=effective_deadline, capture=False)[0]
        for root in plan.roots
        if root.index_entry_count == 0
    ]
    stats = _payload_stats(states)
    if stats["working_payload_count"] > MAX_PAYLOAD_FILES:
        raise EstateAuditCustodyError("payload-file-count-limit-exceeded")
    if stats["working_payload_bytes"] > MAX_PAYLOAD_TOTAL_BYTES:
        raise EstateAuditCustodyError("payload-total-limit-exceeded")
    return {"content_preflight_ok": True, **stats}


def _validated_receipt_repositories(
    root: Path,
    receipt: dict[str, Any],
) -> list[tuple[Path, dict[str, str]]]:
    if receipt.get("restoration_passed") is not True:
        raise EstateAuditCustodyError("custody-restoration-not-passed")
    roots = receipt.get("roots")
    repositories = receipt.get("repositories")
    if not isinstance(roots, list) or not isinstance(repositories, list):
        raise EstateAuditCustodyError("custody-receipt-shape-invalid")
    if int(receipt.get("root_count", -1)) != len(roots):
        raise EstateAuditCustodyError("custody-receipt-root-count-mismatch")
    if int(receipt.get("repository_count", -1)) != len(repositories):
        raise EstateAuditCustodyError("custody-receipt-repository-count-mismatch")

    root_pairs: set[tuple[str, str]] = set()
    root_repositories: set[str] = set()
    empty_index_roots = 0
    for value in roots:
        if not isinstance(value, dict):
            raise EstateAuditCustodyError("custody-receipt-root-invalid")
        repository = str(value.get("repository") or "")
        head = _object_id(str(value.get("head") or ""), label="head")
        tree = _object_id(str(value.get("tree") or ""), label="tree")
        try:
            index_entry_count = int(str(value.get("index_entry_count")))
        except (TypeError, ValueError) as exc:
            raise EstateAuditCustodyError("custody-receipt-index-invalid") from exc
        if index_entry_count < 0 or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("index_sha256") or "")):
            raise EstateAuditCustodyError("custody-receipt-index-invalid")
        empty_index_roots += index_entry_count == 0
        if _github_repository(f"https://github.com/{repository}.git") != repository:
            raise EstateAuditCustodyError("custody-receipt-repository-invalid")
        root_repositories.add(repository)
        root_pairs.add((head, tree))
    if int(receipt.get("head_count", -1)) != len(
        {(str(value.get("repository") or ""), str(value.get("head") or "")) for value in roots}
    ):
        raise EstateAuditCustodyError("custody-receipt-head-count-mismatch")
    if int(receipt.get("empty_index_root_count", -1)) != empty_index_roots:
        raise EstateAuditCustodyError("custody-receipt-index-count-mismatch")
    if int(receipt.get("indexed_root_count", -1)) != len(roots) - empty_index_roots:
        raise EstateAuditCustodyError("custody-receipt-index-count-mismatch")

    validated: list[tuple[Path, dict[str, str]]] = []
    receipt_repositories: set[str] = set()
    receipt_pairs: set[tuple[str, str]] = set()
    for repository in repositories:
        if not isinstance(repository, dict):
            raise EstateAuditCustodyError("custody-receipt-repository-invalid")
        name = str(repository.get("repository") or "")
        if _github_repository(f"https://github.com/{name}.git") != name or name in receipt_repositories:
            raise EstateAuditCustodyError("custody-receipt-repository-invalid")
        receipt_repositories.add(name)
        repository_sha256, expected_store = _repository_store(root, name)
        if repository.get("repository_sha256") != repository_sha256:
            raise EstateAuditCustodyError("custody-repository-digest-mismatch")
        relative = Path(str(repository.get("store") or ""))
        if relative.is_absolute() or ".." in relative.parts:
            raise EstateAuditCustodyError("custody-store-path-invalid")
        store = root / relative
        if store != expected_store or store.is_symlink():
            raise EstateAuditCustodyError("custody-store-path-invalid")
        heads: dict[str, str] = {}
        for value in repository.get("heads") or []:
            if not isinstance(value, dict):
                raise EstateAuditCustodyError("custody-receipt-head-invalid")
            head = _object_id(str(value.get("head") or ""), label="head")
            tree = _object_id(str(value.get("tree") or ""), label="tree")
            previous = heads.setdefault(head, tree)
            if previous != tree:
                raise EstateAuditCustodyError("head-tree-conflict")
            receipt_pairs.add((head, tree))
        if not heads:
            raise EstateAuditCustodyError("custody-receipt-heads-missing")
        validated.append((store, heads))
    if root_repositories != receipt_repositories or root_pairs != receipt_pairs:
        raise EstateAuditCustodyError("custody-receipt-coverage-mismatch")
    return validated


def _validate_failed_checkout_payloads(
    root: Path,
    receipt: dict[str, Any],
    *,
    deadline: float,
    full_restore: bool,
) -> None:
    roots = receipt.get("roots") or []
    empty_roots = {
        str(value.get("path_sha256") or ""): value
        for value in roots
        if isinstance(value, dict) and int(value.get("index_entry_count", -1)) == 0
    }
    states = receipt.get("failed_checkout_states")
    if not isinstance(states, list) or len(states) != len(empty_roots):
        raise EstateAuditCustodyError("failed-checkout-state-count-mismatch")
    state_paths: set[str] = set()
    payload_count = 0
    payload_bytes = 0
    unique_payloads: dict[str, tuple[Path, int]] = {}
    for state_value in states:
        if not isinstance(state_value, dict):
            raise EstateAuditCustodyError("failed-checkout-state-invalid")
        state = dict(state_value)
        content_sha256 = str(state.pop("content_sha256", ""))
        if content_sha256 != _canonical_sha256(state):
            raise EstateAuditCustodyError("failed-checkout-state-content-mismatch")
        path_sha256 = str(state.get("path_sha256") or "")
        root_record = empty_roots.get(path_sha256)
        if root_record is None or path_sha256 in state_paths:
            raise EstateAuditCustodyError("failed-checkout-state-coverage-mismatch")
        state_paths.add(path_sha256)
        if state.get("head") != root_record.get("head") or state.get("tree") != root_record.get("tree"):
            raise EstateAuditCustodyError("failed-checkout-state-head-mismatch")
        payloads = state.get("payloads")
        if not isinstance(payloads, list):
            raise EstateAuditCustodyError("failed-checkout-payload-shape-invalid")
        try:
            working_count = int(state.get("working_file_count", -1))
            exact_count = int(state.get("exact_head_file_count", -1))
            state_payload_count = int(state.get("payload_count", -1))
            state_payload_bytes = int(state.get("payload_bytes", -1))
        except (TypeError, ValueError) as exc:
            raise EstateAuditCustodyError("failed-checkout-state-count-invalid") from exc
        if (
            min(working_count, exact_count, state_payload_count, state_payload_bytes) < 0
            or working_count != exact_count + state_payload_count
            or state_payload_count != len(payloads)
            or not re.fullmatch(r"[0-9a-f]{64}", str(state.get("exact_head_entries_sha256") or ""))
        ):
            raise EstateAuditCustodyError("failed-checkout-state-count-invalid")
        calculated_bytes = 0
        for payload in payloads:
            if not isinstance(payload, dict):
                raise EstateAuditCustodyError("failed-checkout-payload-invalid")
            payload_sha256 = str(payload.get("payload_sha256") or "")
            try:
                size = int(payload.get("payload_bytes", -1))
            except (TypeError, ValueError) as exc:
                raise EstateAuditCustodyError("failed-checkout-payload-invalid") from exc
            relative = Path(str(payload.get("store") or ""))
            if (
                size < 0
                or relative != _payload_relative(payload_sha256)
                or relative.is_absolute()
                or ".." in relative.parts
                or str(payload.get("mode") or "") not in {"100644", "100755", "120000"}
                or not OBJECT_ID_RE.fullmatch(str(payload.get("head_blob") or ""))
            ):
                raise EstateAuditCustodyError("failed-checkout-payload-invalid")
            calculated_bytes += size
            previous = unique_payloads.setdefault(payload_sha256, (root / relative, size))
            if previous != (root / relative, size):
                raise EstateAuditCustodyError("payload-store-content-conflict")
        if calculated_bytes != state_payload_bytes:
            raise EstateAuditCustodyError("failed-checkout-state-count-invalid")
        payload_count += state_payload_count
        payload_bytes += state_payload_bytes
    if state_paths != set(empty_roots):
        raise EstateAuditCustodyError("failed-checkout-state-coverage-mismatch")
    if int(receipt.get("failed_checkout_root_count", -1)) != len(states):
        raise EstateAuditCustodyError("failed-checkout-state-count-mismatch")
    if int(receipt.get("working_payload_count", -1)) != payload_count:
        raise EstateAuditCustodyError("failed-checkout-state-count-mismatch")
    if int(receipt.get("working_payload_bytes", -1)) != payload_bytes:
        raise EstateAuditCustodyError("failed-checkout-state-count-mismatch")
    if int(receipt.get("working_payload_unique_count", -1)) != len(unique_payloads):
        raise EstateAuditCustodyError("failed-checkout-state-count-mismatch")
    unique_bytes = sum(size for _path, size in unique_payloads.values())
    if int(receipt.get("working_payload_unique_bytes", -1)) != unique_bytes:
        raise EstateAuditCustodyError("failed-checkout-state-count-mismatch")

    for payload_sha256, (store, size) in unique_payloads.items():
        stored_sha256, stored_bytes = _stored_payload_digest(store, deadline=deadline)
        if (stored_sha256, stored_bytes) != (payload_sha256, size):
            raise EstateAuditCustodyError("payload-store-content-mismatch")
    if full_restore and unique_payloads:
        with tempfile.TemporaryDirectory(prefix=".payload-restore-", dir=root) as temporary:
            restore_root = Path(temporary)
            for payload_sha256, (store, size) in unique_payloads.items():
                restored = restore_root / payload_sha256
                try:
                    shutil.copyfile(store, restored)
                    restored.chmod(0o600)
                except OSError as exc:
                    raise EstateAuditCustodyError("payload-restoration-failed", type(exc).__name__) from exc
                restored_sha256, restored_bytes = _stored_payload_digest(restored, deadline=deadline)
                if (restored_sha256, restored_bytes) != (payload_sha256, size):
                    raise EstateAuditCustodyError("payload-restoration-mismatch")


def verify_receipt(
    custody_root: Path,
    plan_sha256: str,
    *,
    full_restore: bool = True,
    max_seconds: int = 900,
    require_volume: bool = True,
    identity_guard: IdentityGuard | None = None,
    deadline: float | None = None,
) -> dict[str, Any]:
    if max_seconds <= 0 or max_seconds > MAX_SECONDS:
        raise EstateAuditCustodyError("invalid-time-limit")
    candidate = _resolved_custody_root(custody_root)
    _assert_identity(identity_guard, candidate)
    root = _external_custody_root(candidate) if require_volume else candidate
    _assert_identity(identity_guard, root)
    receipt = _load_receipt(_receipt_path(root, plan_sha256))
    if receipt.get("plan_sha256") != plan_sha256:
        raise EstateAuditCustodyError("custody-receipt-plan-mismatch")
    effective_deadline = deadline or time.monotonic() + max_seconds
    _remaining(effective_deadline)
    for store, heads in _validated_receipt_repositories(root, receipt):
        for head, tree in heads.items():
            if not _has_exact_ref(store, head, tree, timeout=_remaining(effective_deadline)):
                raise EstateAuditCustodyError("custody-ref-verification-failed")
        _git_bytes(
            store,
            "fsck",
            "--full",
            "--strict",
            "--no-progress",
            timeout=_remaining(effective_deadline),
        )
        if full_restore:
            _assert_identity(identity_guard, root)
            _restore_repository(store, heads, root, deadline=effective_deadline)
            _assert_identity(identity_guard, root)
    if full_restore:
        _assert_identity(identity_guard, root)
    _validate_failed_checkout_payloads(
        root,
        receipt,
        deadline=effective_deadline,
        full_restore=full_restore,
    )
    if full_restore:
        _assert_identity(identity_guard, root)
    return receipt


def apply_plan(
    plan: CustodyPlan,
    custody_root: Path,
    *,
    expected_plan_sha256: str,
    revalidate: Callable[[], CustodyPlan],
    remote_url_for: Callable[[str], str] | None = None,
    max_seconds: int = 900,
    require_volume: bool = True,
    identity_guard: IdentityGuard | None = None,
    deadline: float | None = None,
) -> tuple[dict[str, Any], bool]:
    if expected_plan_sha256 != plan.plan_sha256:
        raise EstateAuditCustodyError("plan-sha-mismatch")
    if max_seconds <= 0 or max_seconds > MAX_SECONDS:
        raise EstateAuditCustodyError("invalid-time-limit")
    candidate = _resolved_custody_root(custody_root)
    _assert_identity(identity_guard, candidate)
    root = _external_custody_root(candidate) if require_volume else candidate
    _assert_identity(identity_guard, root)
    root.mkdir(parents=True, exist_ok=True)
    _assert_identity(identity_guard, root)
    existing = _receipt_path(root, plan.plan_sha256)
    effective_deadline = deadline or time.monotonic() + max_seconds
    _remaining(effective_deadline)
    if existing.exists():
        verified = verify_receipt(
            root,
            plan.plan_sha256,
            full_restore=True,
            max_seconds=max(1, int(_remaining(effective_deadline))),
            require_volume=False,
            identity_guard=identity_guard,
            deadline=effective_deadline,
        )
        _assert_identity(identity_guard, root)
        try:
            _verify_live_failed_checkout_states(verified, deadline=effective_deadline)
        except EstateAuditCustodyError as exc:
            if exc.code != "failed-checkout-content-drift":
                raise
            _remaining(effective_deadline)
            _assert_identity(identity_guard, root)
            _preserve_canonical_receipt(
                root,
                plan.plan_sha256,
                verified,
                deadline=effective_deadline,
            )
            _remaining(effective_deadline)
            _assert_identity(identity_guard, root)
            failed_checkout_states, _payload_changed = _capture_failed_checkout_states(
                plan,
                root,
                deadline=effective_deadline,
            )
            _assert_identity(identity_guard, root)
            current = revalidate()
            _remaining(effective_deadline)
            if current.plan_sha256 != plan.plan_sha256:
                raise EstateAuditCustodyError("plan-changed-before-receipt")
            receipt = _receipt_for_plan(
                plan,
                list(verified["repositories"]),
                failed_checkout_states,
            )
            _remaining(effective_deadline)
            _assert_identity(identity_guard, root)
            _atomic_private_json(existing, receipt)
            _assert_identity(identity_guard, root)
            rotated = verify_receipt(
                root,
                plan.plan_sha256,
                full_restore=True,
                max_seconds=max(1, int(_remaining(effective_deadline))),
                require_volume=False,
                identity_guard=identity_guard,
                deadline=effective_deadline,
            )
            return rotated, True
        _assert_identity(identity_guard, root)
        return verified, False

    resolver = remote_url_for or (lambda repository: f"https://github.com/{repository}.git")
    repositories: list[dict[str, Any]] = []
    changed = False
    for repository, heads in sorted(_repository_groups(plan).items()):
        _assert_identity(identity_guard, root)
        result, repository_changed = _ensure_repository(
            root,
            repository,
            heads,
            deadline=effective_deadline,
            remote_url=resolver(repository),
        )
        _assert_identity(identity_guard, root)
        repositories.append(result)
        changed = changed or repository_changed

    _assert_identity(identity_guard, root)
    failed_checkout_states, payload_changed = _capture_failed_checkout_states(
        plan,
        root,
        deadline=effective_deadline,
    )
    _assert_identity(identity_guard, root)
    changed = changed or payload_changed

    current = revalidate()
    _remaining(effective_deadline)
    if current.plan_sha256 != plan.plan_sha256:
        raise EstateAuditCustodyError("plan-changed-before-receipt")
    receipt = _receipt_for_plan(plan, repositories, failed_checkout_states)
    _assert_identity(identity_guard, root)
    _atomic_private_json(existing, receipt)
    _assert_identity(identity_guard, root)
    verified = verify_receipt(
        root,
        plan.plan_sha256,
        full_restore=True,
        max_seconds=max(1, int(_remaining(effective_deadline))),
        require_volume=False,
        identity_guard=identity_guard,
        deadline=effective_deadline,
    )
    return verified, True


def public_receipt(receipt: dict[str, Any], *, changed: bool | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "status": "restored" if receipt.get("restoration_passed") is True else "blocked",
        "plan_sha256": receipt.get("plan_sha256"),
        "content_sha256": receipt.get("content_sha256"),
        "root_count": int(receipt.get("root_count") or 0),
        "repository_count": int(receipt.get("repository_count") or 0),
        "head_count": int(receipt.get("head_count") or 0),
        "empty_index_root_count": int(receipt.get("empty_index_root_count") or 0),
        "indexed_root_count": int(receipt.get("indexed_root_count") or 0),
        "failed_checkout_root_count": int(receipt.get("failed_checkout_root_count") or 0),
        "working_payload_count": int(receipt.get("working_payload_count") or 0),
        "working_payload_bytes": int(receipt.get("working_payload_bytes") or 0),
        "working_payload_unique_count": int(receipt.get("working_payload_unique_count") or 0),
        "working_payload_unique_bytes": int(receipt.get("working_payload_unique_bytes") or 0),
        "working_payload_manifest_sha256": _canonical_sha256(receipt.get("failed_checkout_states") or []),
        "restoration_passed": receipt.get("restoration_passed") is True,
    }
    if changed is not None:
        payload["changed"] = changed
    return payload


def receipt_coverage(receipt: dict[str, Any]) -> dict[str, tuple[str, str, str]]:
    content_sha256 = str(receipt.get("content_sha256") or "")
    coverage: dict[str, tuple[str, str, str]] = {}
    for root in receipt.get("roots") or []:
        if not isinstance(root, dict):
            continue
        path = str(root.get("path") or "")
        head = str(root.get("head") or "")
        tree = str(root.get("tree") or "")
        if path and OBJECT_ID_RE.fullmatch(head) and OBJECT_ID_RE.fullmatch(tree):
            coverage[path] = (head, tree, content_sha256)
    return coverage


def _tree_records(path: Path, head: str) -> dict[str, tuple[str, str, str]]:
    output = _git_bytes(path, "ls-tree", "-r", "-z", "--full-tree", head)
    records: dict[str, tuple[str, str, str]] = {}
    for raw in (value for value in output.split(b"\0") if value):
        try:
            metadata, encoded_path = raw.split(b"\t", 1)
            mode, kind, object_id = metadata.decode("ascii").split(" ", 2)
            relative = encoded_path.decode("utf-8", errors="surrogateescape")
        except ValueError as exc:
            raise EstateAuditCustodyError("tree-record-invalid") from exc
        records[relative] = (mode, kind, _object_id(object_id, label="blob"))
    return records


def _working_paths(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError as exc:
            raise EstateAuditCustodyError("working-tree-unreadable", type(exc).__name__) from exc
        for entry in entries:
            if directory == root and entry.name == ".git":
                continue
            candidate = Path(entry.path)
            relative = candidate.relative_to(root).as_posix()
            try:
                if entry.is_symlink():
                    found[relative] = candidate
                elif entry.is_dir(follow_symlinks=False):
                    pending.append(candidate)
                elif entry.is_file(follow_symlinks=False):
                    found[relative] = candidate
                else:
                    raise EstateAuditCustodyError("working-tree-special-file")
            except OSError as exc:
                raise EstateAuditCustodyError("working-tree-unreadable", type(exc).__name__) from exc
    return found


def _hash_working_path(root: Path, relative: str, expected_mode: str) -> str:
    candidate = root / relative
    try:
        before = candidate.lstat()
    except OSError as exc:
        raise EstateAuditCustodyError("working-file-unavailable", type(exc).__name__) from exc
    if expected_mode == "120000":
        if not stat.S_ISLNK(before.st_mode):
            raise EstateAuditCustodyError("working-mode-mismatch")
        payload = os.readlink(candidate).encode("utf-8", errors="surrogateescape")
        result = _run_git(root, ["hash-object", f"--path={relative}", "--stdin"], input_bytes=payload)
    elif expected_mode in {"100644", "100755"}:
        if not stat.S_ISREG(before.st_mode):
            raise EstateAuditCustodyError("working-mode-mismatch")
        executable = bool(before.st_mode & stat.S_IXUSR)
        if executable != (expected_mode == "100755"):
            raise EstateAuditCustodyError("working-mode-mismatch")
        try:
            with candidate.open("rb") as handle:
                result = _run_git(root, ["hash-object", f"--path={relative}", "--stdin"], stdin=handle)
        except OSError as exc:
            raise EstateAuditCustodyError("working-file-unavailable", type(exc).__name__) from exc
    else:
        raise EstateAuditCustodyError("unsupported-tree-mode")
    if result.returncode:
        raise EstateAuditCustodyError("working-file-hash-failed")
    try:
        after = candidate.lstat()
    except OSError as exc:
        raise EstateAuditCustodyError("working-file-changed", type(exc).__name__) from exc
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise EstateAuditCustodyError("working-file-changed")
    return _object_id(result.stdout.decode().strip(), label="blob")


def verify_failed_checkout_content(path: Path, *, expected_head: str, expected_tree: str) -> CheckoutContentProof:
    root = path.expanduser().resolve(strict=True)
    path_sha256 = _path_sha256(root)
    try:
        if _git_bytes(root, "ls-files", "-s", "-z"):
            return CheckoutContentProof(path_sha256, expected_head, expected_tree, 0, "", False, "index-not-empty")
        head = _object_id(_git_text(root, "rev-parse", "HEAD"), label="head")
        tree = _object_id(_git_text(root, "rev-parse", "HEAD^{tree}"), label="tree")
        if head != expected_head or tree != expected_tree:
            return CheckoutContentProof(path_sha256, head, tree, 0, "", False, "head-or-tree-drift")
        records = _tree_records(root, head)
        if any(kind != "blob" for _mode, kind, _object_id_value in records.values()):
            return CheckoutContentProof(path_sha256, head, tree, 0, "", False, "unsupported-tree-entry")
        working = _working_paths(root)
        if not set(working).issubset(records):
            return CheckoutContentProof(path_sha256, head, tree, len(working), "", False, "path-outside-head")
        verified: list[tuple[str, str, str]] = []
        for relative in sorted(working):
            mode, _kind, expected_object = records[relative]
            actual_object = _hash_working_path(root, relative, mode)
            if actual_object != expected_object:
                return CheckoutContentProof(path_sha256, head, tree, len(working), "", False, "blob-mismatch")
            verified.append((relative, mode, actual_object))
        if set(_working_paths(root)) != set(working):
            return CheckoutContentProof(path_sha256, head, tree, len(working), "", False, "path-set-changed")
        return CheckoutContentProof(
            path_sha256,
            head,
            tree,
            len(verified),
            _canonical_sha256(verified),
            True,
            "exact-head-content" if len(working) == len(records) else "exact-head-content-subset",
        )
    except (EstateAuditCustodyError, OSError):
        return CheckoutContentProof(path_sha256, expected_head, expected_tree, 0, "", False, "verification-failed")


__all__ = [
    "DEFAULT_CUSTODY_ROOT",
    "GENERATED_ROOT_RE",
    "MAX_CUSTODY_RECEIPT_BYTES",
    "MAX_ROOTS",
    "MAX_SECONDS",
    "CheckoutContentProof",
    "CustodyPlan",
    "EstateAuditCustodyError",
    "GeneratedRootRecord",
    "apply_plan",
    "assert_custody_target_identity",
    "discover_plan",
    "preflight_plan",
    "public_receipt",
    "receipt_coverage",
    "verify_failed_checkout_content",
    "verify_receipt",
]
