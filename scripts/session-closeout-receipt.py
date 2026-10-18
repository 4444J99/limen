#!/usr/bin/env python3
"""Session closeout receipt producer: derive, never guess, a `limen.session_closeout.v2` receipt.

WHY: `limen.session_closeout` (cli/src/limen/session_closeout.py) is the only authority on whether a
session is released, and it only CHECKS a hand-built receipt (limen issue 2977). This tool is the missing
producer. It imports the checker's own helpers (path_digest, safe_path, matches, dirty_paths,
github_repository_slug, repository_readback, owner_readback, published, evaluate_scoped) so producer and
checker cannot drift, derives every value from a named source, and fails closed -- with an actionable
`gap: <code>: <message>` -- whenever ownership, base, owner, disposition or session membership is not
provable. It never invents owned_paths, retained_work, owner_url, disposition, base_head or scopes.

VERBS (a closed set)
  plan    --manifest M [--json]
          Read-only. Gathers every live fact (git, gh, broker audit and registration, process census),
          prints a redacted fact table and EVERY gap. Candidate ownership paths are printed under
          "unattributed, NOT written"; they never reach the receipt.
  attest  --manifest M --scope ID --label NAME (--gate ID | -- CMD...) [--purpose completion] [--owner-url U]
          Runs ONE registry-declared gate (institutio/governance/gates.yaml, or the verify-scoped wrapper) in the
          scope root with its own bounded process group, a scrubbed environment and check=False, then
          records the real exit code, head and output digest in a create-only attestation file.
  build   --manifest M [--json]
          Re-derives everything, refuses on any gap, writes evidence then the receipt (create-only), runs the
          REAL evaluate_scoped as a labelled dry run, and rolls back the files it created if that fails.
  check   --manifest M [--expect-unpublished] [--recheck-heads] [--json]
          Runs the real checker in-process. `--expect-unpublished` is a non-evidence dry run for the window
          between the receipt commit and its push. Only a bare `check` after the push is evidence.

NEVER: registers or mutates a broker session, stages, commits, pushes, merges, creates a continuation, or
deletes. After `build` the operator stages exactly the printed `git add -- <paths>` list.

MANIFEST (private, mode 0600, outside every scope root): schema limen.session_closeout_manifest.v1 with
session_id, anchor, owner_url, [disposition], receipt{root_id, continuation, [name]}, scopes[], verification[],
custody{mode: evidence|absence, bundle}, external_effects[], external_effects_enumerated. See
docs/session-closeout.md "Producer".

EXIT CODES (mirror the checker): 0 success or an identical re-run that wrote nothing; 1 measured refusal
(one or more gaps); 2 unmeasured (gh, broker, git or the census unavailable, or malformed input); 3 only
`check --expect-unpublished`: the dry run found no obstacle, which is explicitly NOT a pass.

Run it under an interpreter that can import limen's dependencies (pydantic, PyYAML), e.g. the cli venv:
`cli/.venv/bin/python -I scripts/session-closeout-receipt.py plan --manifest PRIVATE_MANIFEST`.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import shlex
import signal
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "cli/src"))

from limen import session_closeout as closeout

MANIFEST_SCHEMA = "limen.session_closeout_manifest.v1"
ATTESTATION_SCHEMA = "limen.session_check_attestation.v1"
ABSENCE_SCHEMA = "limen.custody_absence.v1"
EFFECT_SCHEMA = "limen.external_effect_readback.v1"
SEALED_TRACKED_SCHEMA = "limen.sealed_custody_receipt.tracked.v1"
CUSTODY_CONTRACT = "limen.custody_receipt.v2"
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
RECEIPT_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}\.json")
SLUG_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}")
EVIDENCE_DIRNAME = "closeout-evidence"
DEFAULT_RECEIPT_NAME = "session-closeout.json"
SUCCESS_STATUSES = {"done", "succeeded", "archived"}
TERMINAL_STATUSES = {
    "done",
    "failed",
    "failed_blocked",
    "needs_human",
    "archived",
    "succeeded",
    "blocked",
    "cancelled",
    "partial",
}
NATIVE_EFFECT_KINDS = {"pull_request", "issue", "git_ref"}
DEFAULT_TIMEOUT_SECONDS = 600
MAX_TIMEOUT_SECONDS = 600
CHILD_ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "TMPDIR",
    "LANG",
    "TERM",
    "USER",
    "LOGNAME",
    "SHELL",
    "PYTHONPATH",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "XDG_CONFIG_HOME",
)
CHILD_ENV_PREFIXES = ("LC_",)

# A14: one scanner runs over every committed byte (receipt, attestations, absence and effect evidence, custody).
SECRET_PATTERNS = (
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"op://"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"xox[abprs]-[A-Za-z0-9-]{10,}"),
)
ASSIGNMENT_PATTERN = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|authorization)[\"']?\s*[=:]\s*[\"']?[^\s\"',;]{3,}"
)
FLAG_PATTERN = re.compile(r"(?i)--(?:token|password|passwd|secret|api-key|auth)(?:=|\s+)\S+")
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![\w/.:-])/(?:Users|home|Volumes|private|tmp|var|opt|etc|usr|root|mnt|srv|System|Library|Applications)/"
)
FILE_URL_PATTERN = re.compile(r"file://")

# A6: a gate may never rewrite the repository or the broker. Registry commands are scanned verbatim. This static
# scan is a first line only (shell indirection can always hide a verb); the authoritative guard is the observed
# before/after state in `attest` (HEAD, tree and every ref), which also catches a `git push` that updates a
# remote-tracking ref. A remote-only mutation (for example `gh` against the API) is not observable locally.
GIT_MUTATING_VERBS = (
    r"push|commit|add|reset|checkout|switch|merge|rebase|stash|clean|restore|rm|mv|tag|"
    r"cherry-pick|revert|worktree|am|apply|update-ref|gc|prune"
)
MUTATING_COMMANDS = (
    re.compile(rf"\bgit\b[^\n;&|]*\b(?:{GIT_MUTATING_VERBS})\b"),
    # A variable expanded in command position followed by a mutating verb (`G=git; $G push`).
    re.compile(rf"\$\{{?[A-Za-z_][A-Za-z0-9_]*\}}?\s+(?:{GIT_MUTATING_VERBS})\b"),
    re.compile(r"\beval\b"),
    re.compile(r"\bgh\b[^\n;&|]*\b(?:merge|create|close|edit|delete|reopen|comment|review|ready)\b"),
    re.compile(r"\blimen\s+conduct\b"),
)
DEFAULT_GATES_REGISTRY = "institutio/governance/gates.yaml"
VERIFY_SCOPED_WRAPPER = "bash scripts/verify-scoped.sh"
VERIFY_SCOPED_SCRIPT = "scripts/verify-scoped.sh"
HEX64 = re.compile(r"[0-9a-f]{64}")


class ProducerError(RuntimeError):
    """Unmeasured: the message is fixed prose and carries no private path, argv or credential."""


class Refusal(Exception):  # noqa: N818 - a refusal is a measured outcome, not an error
    """One measured refusal (exit 1) raised from a verb that has no report to accumulate gaps in."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


# --------------------------------------------------------------------------- seams


@dataclass
class Seams:
    """Every external observation, injectable so the contract tests never touch a network or a broker."""

    audit: Callable[[str], dict]
    sessions: Callable[[], list[dict]]
    read_owner: Callable[[str], dict]
    read_repository: Callable[[str], dict]
    observe: Callable[..., Any]
    read_effect: Callable[[dict], dict]
    now: Callable[[], datetime] = lambda: datetime.now(UTC)


def gh_effect_readback(spec: dict) -> dict:
    """Read one native external effect through gh and project only the fields a verdict needs."""
    kind = spec["kind"]
    if kind in {"pull_request", "issue"}:
        match = closeout.OWNER.fullmatch(str(spec.get("url", "")))
        if not match:
            raise closeout.Unmeasured("effect url must be an exact GitHub issue or PR URL")
        repo, url_kind, number = match.groups()
        if (url_kind == "pull") != (kind == "pull_request"):
            raise closeout.Unmeasured("effect kind does not match its URL")
        endpoint = "pulls" if kind == "pull_request" else "issues"
        value = json.loads(closeout.run(["gh", "api", "--method", "GET", f"repos/{repo}/{endpoint}/{number}"]))
        if value.get("html_url") != spec["url"]:
            raise closeout.Unmeasured("effect readback identity mismatch")
        projected = {"state": value.get("state"), "html_url": value.get("html_url"), "number": value.get("number")}
        if kind == "pull_request":
            projected.update(
                merged=value.get("merged"),
                merge_commit_sha=value.get("merge_commit_sha"),
                head={"sha": (value.get("head") or {}).get("sha")},
                base={"ref": (value.get("base") or {}).get("ref")},
            )
        return projected
    slug, branch = str(spec.get("repository", "")), str(spec.get("branch", ""))
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", slug) or not branch or branch.startswith("-"):
        raise closeout.Unmeasured("git_ref effect needs repository and branch")
    value = json.loads(
        closeout.run(["gh", "api", "--method", "GET", f"repos/{slug}/git/ref/heads/{quote(branch, safe='')}"])
    )
    obj = value.get("object") or {}
    return {"ref": value.get("ref"), "object": {"type": obj.get("type"), "sha": obj.get("sha")}}


def live_seams() -> Seams:
    """The production seams. The broker client is built lazily so `plan` fails closed, never at import."""
    holder: dict[str, Any] = {}

    def client() -> Any:
        if "client" not in holder:
            from limen.conduct.client import client_from_env

            holder["client"] = client_from_env()
        return holder["client"]

    def observe(*args: Any, **kwargs: Any) -> Any:
        from limen.process_ownership import observe_many

        return observe_many(*args, **kwargs)

    return Seams(
        audit=lambda session_id: client().session_audit(session_id),
        sessions=lambda: list(client().capabilities().get("sessions", [])),
        read_owner=lambda url: closeout.owner_readback(url),
        read_repository=lambda slug: closeout.repository_readback(slug),
        observe=observe,
        read_effect=gh_effect_readback,
    )


# --------------------------------------------------------------------------- reports


class Report:
    def __init__(self) -> None:
        self.gaps: list[tuple[str, str]] = []
        self.notes: list[str] = []
        self.facts: list[dict] = []
        self.candidates: dict[str, dict] = {}
        self.receipt: dict | None = None
        self.receipt_bytes: bytes | None = None
        self.receipt_exists_identical = False
        self.new_files: dict[str, bytes] = {}
        self.cited: list[str] = []
        self.overlay: set[str] = set()
        self.disposition: str | None = None
        self.census: dict | None = None
        self.audit: dict = {}
        self.binding: dict | None = None

    def gap(self, code: str, message: str) -> None:
        item = (code, message)
        if item not in self.gaps:
            self.gaps.append(item)

    def note(self, message: str) -> None:
        if message not in self.notes:
            self.notes.append(message)

    def cite(self, relative: str) -> None:
        if relative not in self.cited:
            self.cited.append(relative)
        self.overlay.add(relative)


@dataclass
class Scope:
    id: str
    kind: str
    path: Path
    spec: dict
    absent: bool = False
    parent: str | None = None
    head: str | None = None
    owned: list[str] = field(default_factory=list)
    retained_work: list[dict] = field(default_factory=list)
    repository: str | None = None
    repository_id: int | None = None
    branch: str | None = None
    row: dict | None = None


@dataclass
class Context:
    manifest_path: Path
    manifest: dict
    allow_local_remote: bool
    gaps: list[tuple[str, str]] = field(default_factory=list)
    session_id: str = ""
    slug: str | None = None
    anchor: Path = Path("/")
    scopes: dict[str, Scope] = field(default_factory=dict)
    receipt_id: str = ""
    receipt_root: Path | None = None
    continuation: str = ""
    receipt_rel: str = ""
    evidence_dir_rel: str = ""
    private_literals: list[str] = field(default_factory=list)
    allowed_literals: list[str] = field(default_factory=list)

    def gap(self, code: str, message: str) -> None:
        item = (code, message)
        if item not in self.gaps:
            self.gaps.append(item)


# --------------------------------------------------------------------------- safe file IO (A13)


def _chain_parts(relative: str) -> tuple[str, ...]:
    return PurePosixPath(closeout.safe_path(relative)).parts


def chain_problem(root: Path, relative: str, *, tolerate_missing_from: int | None = None) -> str | None:
    """A13: walk every component below the repository root; a symlink anywhere in the chain is refused."""
    parts = _chain_parts(relative)
    current = root
    for index, name in enumerate(parts):
        current = current / name
        try:
            state = os.lstat(current)
        except FileNotFoundError:
            if tolerate_missing_from is not None and index >= tolerate_missing_from:
                return None
            return "missing"
        if stat.S_ISLNK(state.st_mode):
            return "symlink"
        if index < len(parts) - 1 and not stat.S_ISDIR(state.st_mode):
            return "not_directory"
    return None


def _open_directory_chain(
    root: Path, parts: tuple[str, ...], *, create_from: int | None = None
) -> tuple[int, list[tuple[int, str]]]:
    """Open `root/parts` one component at a time with O_NOFOLLOW; optionally create dirs from an index on."""
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    created: list[tuple[int, str]] = []
    try:
        for index, name in enumerate(parts):
            try:
                child = os.open(name, flags, dir_fd=descriptor)
            except FileNotFoundError:
                if create_from is None or index < create_from:
                    raise
                os.mkdir(name, 0o755, dir_fd=descriptor)
                created.append((index, name))
                child = os.open(name, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, created
    except BaseException:
        os.close(descriptor)
        raise


def read_receipt_file(root: Path, relative: str) -> bytes:
    parts = _chain_parts(relative)
    directory, _ = _open_directory_chain(root, parts[:-1])
    try:
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, "rb") as handle:
        return handle.read()


def create_only(root: Path, relative: str, data: bytes, *, create_from: int) -> list[str]:
    """Create `relative` exclusively (O_EXCL|O_NOFOLLOW), mode 0644, creating only directories below `create_from`."""
    parts = _chain_parts(relative)
    directory, created = _open_directory_chain(root, parts[:-1], create_from=create_from)
    try:
        descriptor = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=directory)
        with os.fdopen(descriptor, "wb") as handle:
            os.fchmod(handle.fileno(), 0o644)
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(directory)
    return ["/".join(parts[: index + 1]) for index, _ in created]


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- scrub (A14)


def scrub_problems(data: bytes, *, literals: list[str], allowed: list[str], strict: bool) -> list[str]:
    """Return problem codes only (never the matched text) for secrets or private paths in committed bytes."""
    text = data.decode("utf-8", errors="replace") if strict else data.decode("latin-1")
    for item in allowed:
        text = text.replace(item, "")
    problems: list[str] = []
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        problems.append("secret_shape")
    if strict and (ASSIGNMENT_PATTERN.search(text) or FLAG_PATTERN.search(text)):
        problems.append("credential_assignment")
    if ABSOLUTE_PATH_PATTERN.search(text) or FILE_URL_PATTERN.search(text):
        problems.append("absolute_path")
    if any(literal and literal in text for literal in literals):
        problems.append("declared_private_path")
    return problems


def origin_credential_problem(origin: str) -> bool:
    """A14: a remote carrying a password, a token username or a non-`git` ssh user is never echoed."""
    if origin.startswith("git@") or "://" not in origin:
        return False
    parts = urlsplit(origin)
    if parts.password:
        return True
    if parts.username and parts.scheme in {"http", "https"}:
        return True
    return bool(parts.username and parts.username != "git")


# --------------------------------------------------------------------------- manifest and context


def load_manifest(path: Path) -> tuple[dict, int]:
    state = os.lstat(path)
    if stat.S_ISLNK(state.st_mode) or not stat.S_ISREG(state.st_mode):
        raise ProducerError("manifest must be a regular file, not a link")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict) or value.get("schema") != MANIFEST_SCHEMA:
        raise ProducerError("manifest schema mismatch")
    return value, state.st_mode


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def prepare(manifest_path: Path, *, allow_local_remote: bool = False) -> Context:
    """Local-only resolution: no network, no broker, no git. Anything unprovable becomes a gap."""
    manifest, mode = load_manifest(manifest_path)
    ctx = Context(manifest_path=manifest_path.resolve(), manifest=manifest, allow_local_remote=allow_local_remote)
    if mode & 0o077:
        ctx.gap(
            "manifest_mode_too_open", "the manifest names absolute private paths; chmod it to 0600 in a 0700 directory"
        )
    session_id = manifest.get("session_id")
    if not isinstance(session_id, str) or not ID_RE.fullmatch(session_id):
        ctx.gap("session_id_invalid", "session_id must match [A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
    else:
        ctx.session_id = session_id
        # A13: the evidence directory name is a constrained slug of the session id, or the build stops.
        if SLUG_RE.fullmatch(session_id):
            ctx.slug = session_id
        else:
            ctx.gap("session_slug_invalid", "session_id is too long to name an evidence directory (96 characters max)")
    anchor_value = manifest.get("anchor")
    if not isinstance(anchor_value, str) or not Path(anchor_value).is_absolute():
        raise ProducerError("manifest anchor must be an absolute path")
    try:
        ctx.anchor = Path(anchor_value).resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProducerError("session anchor does not exist") from exc
    if Path(anchor_value) != ctx.anchor:
        ctx.gap("anchor_not_canonical", "the anchor must already equal its resolved path (no symlinks or `..`)")
    for key in ("scope_lineage", "scope_retirement", "broker_scope_root_id"):
        if key in manifest:
            ctx.gap(
                "unsupported_in_producer_v1" if key != "broker_scope_root_id" else "broker_scope_unsupported",
                f"`{key}` needs evidence this producer cannot derive (native transcript or retirement graph)",
            )
    _prepare_scopes(ctx, manifest)
    _prepare_receipt(ctx, manifest)
    ctx.private_literals = sorted(
        {str(ctx.anchor), str(Path.home()), str(ctx.manifest_path.parent), *(str(s.path) for s in ctx.scopes.values())}
    )
    return ctx


def _prepare_scopes(ctx: Context, manifest: dict) -> None:
    rows = manifest.get("scopes")
    if not isinstance(rows, list) or not rows:
        ctx.gap("scopes_required", "declare every scope root explicitly; the producer never scans for repositories")
        return
    seen_paths: dict[Path, str] = {}
    for spec in rows:
        if not isinstance(spec, dict):
            ctx.gap("scope_malformed", "every scope must be an object")
            continue
        identifier, kind, path_value = spec.get("id"), spec.get("kind"), spec.get("path")
        if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier) or identifier in ctx.scopes:
            ctx.gap("scope_id_invalid", "scope ids must match [A-Za-z0-9][A-Za-z0-9_.-]{0,127} and be unique")
            continue
        if kind not in {"git", "retained"}:
            ctx.gap(
                "scope_kind_unsupported", f"scope {identifier}: kind must be git or retained (retired is unsupported)"
            )
            continue
        if not isinstance(path_value, str) or not Path(path_value).is_absolute():
            ctx.gap("scope_path_invalid", f"scope {identifier}: path must be absolute")
            continue
        declared = Path(path_value)
        try:
            resolved = declared.resolve(strict=True)
            absent = False
        except FileNotFoundError:
            resolved, absent = declared.resolve(strict=False), True
            # An absent root is never silently marked retired (the design's gap scope_absent).
            ctx.gap("scope_absent", f"scope {identifier}: the path is absent; retirement needs a custody graph")
        if declared != resolved:
            ctx.gap("scope_path_not_canonical", f"scope {identifier}: the path must equal its resolved form")
        if resolved in seen_paths:
            ctx.gap(
                "scope_duplicate_root", f"scope {identifier} duplicates the canonical root of {seen_paths[resolved]}"
            )
        seen_paths[resolved] = identifier
        ctx.scopes[identifier] = Scope(id=identifier, kind=kind, path=resolved, spec=spec, absent=absent)
    for scope in ctx.scopes.values():
        parents = [
            other for other in ctx.scopes.values() if other.id != scope.id and scope.path.is_relative_to(other.path)
        ]
        if parents:
            scope.parent = max(parents, key=lambda other: len(other.path.parts)).id
    # A19: the private manifest must not become an unattributed dirty path inside a declared scope.
    for scope in ctx.scopes.values():
        if ctx.manifest_path.is_relative_to(scope.path):
            ctx.gap(
                "manifest_inside_scope",
                f"the manifest sits inside scope {scope.id}; keep it under a staging root outside every declared scope "
                "(the default LIMEN_CUSTODY_STAGING_ROOT lies inside the live limen checkout)",
            )


def _prepare_receipt(ctx: Context, manifest: dict) -> None:
    block = manifest.get("receipt")
    if not isinstance(block, dict):
        ctx.gap("receipt_required", "receipt{root_id, continuation} is required")
        return
    root_id = block.get("root_id")
    scope = ctx.scopes.get(root_id) if isinstance(root_id, str) else None
    if scope is None or scope.kind != "git":
        ctx.gap("receipt_root_invalid", "receipt.root_id must name a declared git scope")
        return
    ctx.receipt_id, ctx.receipt_root = scope.id, scope.path
    name = block.get("name", DEFAULT_RECEIPT_NAME)
    if not isinstance(name, str) or not RECEIPT_NAME_RE.fullmatch(name):
        ctx.gap("receipt_name_invalid", "receipt.name must be a plain *.json file name")
        return
    try:
        continuation = closeout.safe_path(block.get("continuation"))
    except closeout.Unmeasured:
        ctx.gap("continuation_invalid", "receipt.continuation must be a repository-relative directory")
        return
    ctx.continuation = continuation
    problem = None if scope.absent else chain_problem(scope.path, continuation)
    if problem is not None or scope.absent:
        # A13: a symlinked or missing continuation never receives a write; a new owner is never created here.
        ctx.gap(
            "continuation_unsafe" if problem in {"symlink", "not_directory"} else "continuation_missing",
            "receipt.continuation must be an existing real directory inside the receipt repository "
            f"(found: {problem or 'absent scope'}); the producer never creates a continuation owner",
        )
        return
    if not scope.absent and not (scope.path / continuation).is_dir():
        ctx.gap("continuation_missing", "receipt.continuation must be an existing directory")
        return
    ctx.receipt_rel = f"{continuation}/{name}"
    if ctx.slug is not None:
        ctx.evidence_dir_rel = f"{continuation}/{EVIDENCE_DIRNAME}/{ctx.slug}"
        problem = chain_problem(scope.path, ctx.evidence_dir_rel, tolerate_missing_from=len(_chain_parts(continuation)))
        if problem is not None:
            ctx.gap("evidence_dir_unsafe", f"the evidence directory chain contains a {problem} component")
            ctx.evidence_dir_rel = ""


def evidence_create_from(ctx: Context) -> int:
    return len(_chain_parts(ctx.continuation))


# --------------------------------------------------------------------------- derivation


def _git(root: Path, *args: str, raw: bool = False) -> Any:
    return closeout.git(root, *args, raw=raw)


def _git_ok(root: Path, *args: str) -> bool:
    try:
        _git(root, *args)
    except subprocess.CalledProcessError:
        return False
    return True


def _owner_value(
    rep: Report, seams: Seams, cache: dict[str, dict | None], url: Any, code: str, subject: str
) -> dict | None:
    """The live readback of an owner, or None with one gap when it is malformed or unverifiable."""
    if not isinstance(url, str) or not closeout.OWNER.fullmatch(url):
        rep.gap(code, f"{subject}: an exact https://github.com/OWNER/REPO/(issues|pull)/N owner URL is required")
        return None
    if url not in cache:
        try:
            cache[url] = seams.read_owner(url)
        except closeout.Unmeasured:
            cache[url] = None
    if cache[url] is None:
        rep.gap(code, f"{subject}: the owner could not be verified by a live readback")
    return cache[url]


def _owner_state(rep: Report, seams: Seams, cache: dict[str, dict | None], url: Any, code: str, subject: str) -> bool:
    """True only for a live-read, open GitHub owner; every other outcome is one gap."""
    value = _owner_value(rep, seams, cache, url, code, subject)
    if value is None:
        return False
    if value.get("state") != "open":
        rep.gap(code, f"{subject}: the owner is not open")
        return False
    return True


def derive(ctx: Context, seams: Seams) -> Report:
    """Gather every fact once, collect every gap, and (when none block) assemble the receipt bytes."""
    rep = Report()
    for code, message in ctx.gaps:
        rep.gap(code, message)
    if not ctx.session_id or ctx.receipt_root is None or not ctx.scopes:
        return rep
    owners: dict[str, dict | None] = {}
    manifest = ctx.manifest
    _derive_broker(ctx, seams, rep)
    _derive_owner(ctx, seams, rep, owners)
    attestations = _derive_verification(ctx, rep)
    custody = _derive_custody(ctx, seams, rep)
    effects, effect_state = _derive_effects(ctx, seams, rep, owners)
    process_evidence = _derive_process_sidecar(ctx, rep)
    cited = set(rep.cited)
    rows: list[dict] = []
    for scope in ctx.scopes.values():
        if scope.kind == "git":
            row = _derive_git_scope(ctx, seams, rep, scope, owners, attestations, cited)
        else:
            row = _derive_retained_scope(ctx, seams, rep, scope, owners)
        if row is not None:
            scope.row = row
            rows.append(row)
    _derive_nested(ctx, rep)
    _derive_unattributed_evidence(ctx, rep)
    _derive_census(ctx, seams, rep, process_evidence)
    _derive_effect_attribution(ctx, rep)
    _derive_disposition(ctx, rep, attestations, effect_state, owners, seams)
    if rep.gaps or custody is None or len(rows) != len(ctx.scopes):
        return rep
    receipt: dict[str, Any] = {
        "schema": closeout.SCHEMA_V2,
        "session_id": ctx.session_id,
        "session_root_path_sha256": closeout.path_digest(ctx.anchor),
        "receipt_root_id": ctx.receipt_id,
        "owner_url": manifest.get("owner_url"),
        "disposition": rep.disposition,
        "scope_roots": rows,
        "verification": [item["entry"] for item in attestations],
        "custody": custody,
        # An explicit empty list is the committed form of the `external_effects_enumerated` attestation (A10).
        "external_effects": effects,
    }
    if manifest.get("process_ownership"):
        receipt["process_ownership"] = manifest["process_ownership"]
    rep.receipt = receipt
    rep.receipt_bytes = json_bytes(receipt)
    _finalize_files(ctx, rep)
    return rep


def _derive_broker(ctx: Context, seams: Seams, rep: Report) -> None:
    sid = ctx.session_id
    audit = seams.audit(sid)
    if not isinstance(audit, dict):
        raise ProducerError("broker audit is malformed")
    rep.audit = audit
    coverage = audit.get("coverage")
    if (
        audit.get("session_id") != sid
        or not isinstance(coverage, dict)
        or coverage.get("retained_state_complete") is not True
    ):
        rep.gap("audit_incomplete", "the broker session audit is missing or its retained state coverage is incomplete")
    runs = audit.get("runs")
    if not isinstance(runs, list) or audit.get("retained_run_count") != len(runs):
        rep.gap("retained_runs_incomplete", "the broker audit does not account for every retained run")
        runs = []
    # A8: leases and runs are reported, never released, by the producer; the checker rejects them otherwise.
    if type(audit.get("active_lease_count")) is not int or audit["active_lease_count"] != 0:
        rep.gap(
            "active_lease",
            "the session still holds (or has unmeasured) leases; release or report them through the broker "
            "(`limen conduct report` / `harvest`) before building -- the producer never mutates the broker",
        )
    nonterminal = sorted(
        {str(row.get("status")) for row in runs if isinstance(row, dict) and row.get("status") not in TERMINAL_STATUSES}
    )
    if nonterminal:
        rep.gap(
            "nonterminal_runs",
            f"runs are not terminal (statuses: {', '.join(nonterminal)}); report or harvest them first",
        )
    # A20: name the exact binding mismatch class so the operator files one precise blocker.
    rows = [row for row in seams.sessions() if isinstance(row, dict) and row.get("session_id") == sid]
    binding = rows[0] if rows else None
    rep.binding = binding
    if binding is None:
        rep.gap(
            "binding_no_row",
            "no broker registration row exists for this session; the checker then demands a Codex-format native "
            "transcript this producer cannot supply. BLOCKED: re-register the session at the anchor through its owner "
            "(a human-protected registration is never overridden by this tool); file it once and do not re-poll",
        )
        return
    bound = Path(str(binding.get("worktree") or ""))
    if not bound.is_absolute():
        rep.gap("binding_worktree_not_absolute", "the broker row's worktree is not an absolute path")
    elif bound != bound.resolve():
        rep.gap("binding_worktree_not_canonical", "the broker row's worktree is not a canonical resolved path")
    elif bound != ctx.anchor:
        rep.gap(
            "binding_worktree_mismatch",
            "the broker row's worktree differs from the declared anchor; BLOCKED: re-anchor the registration "
            "through its owner, file it once and do not re-poll",
        )


def _derive_owner(ctx: Context, seams: Seams, rep: Report, owners: dict[str, dict | None]) -> None:
    url = ctx.manifest.get("owner_url")
    if not isinstance(url, str) or not closeout.OWNER.fullmatch(url):
        rep.gap("owner_url_missing", "owner_url must be an exact GitHub issue or PR URL; there is no fallback")
        return
    # A closed owner is acceptable for `complete`; the derived disposition decides whether it must be open.
    _owner_value(rep, seams, owners, url, "owner_url_unverified", "session owner")


def _read_json_file(ctx: Context, rep: Report, relative: str, code: str) -> tuple[bytes, Any] | None:
    try:
        raw = read_receipt_file(ctx.receipt_root, relative)  # type: ignore[arg-type]
        return raw, json.loads(raw)
    except closeout.Unmeasured:
        rep.gap(code, "evidence path must be repository-relative")
    except (FileNotFoundError, NotADirectoryError):
        rep.gap(code, f"evidence file {relative} does not exist in the receipt repository")
    except OSError:
        rep.gap(code, f"evidence file {relative} is unreadable or reached through a symlink")
    except ValueError:
        rep.gap(code, f"evidence file {relative} is not valid JSON")
    return None


def _revalidate_gate(ctx: Context, scope: Scope, head: str, value: dict) -> str | None:
    """A6: an attestation file is evidence only if its gate re-resolves, today, from the registry the scope COMMITS at
    the attested head: same gate id, same command, same definition digest, and a command `attest` would still run.
    A hand-written file naming an unknown gate or a made-up digest is refused (the reason string, or None if sound)."""
    gate_id, registry_rel = value.get("gate_id"), value.get("gate_registry")
    command, digest = value.get("command"), value.get("gate_definition_sha256")
    if not all(isinstance(item, str) and item for item in (gate_id, registry_rel, command, digest)):
        return "does not bind a registry-declared gate (gate id, registry, command and digest are required)"
    if HEX64.fullmatch(digest) is None or HEX64.fullmatch(str(value.get("output_sha256", ""))) is None:
        return "carries a malformed gate or output digest"
    if value.get("tree_clean_at_start") is not True or value.get("tree_and_head_unchanged_at_end") is not True:
        return "does not record a clean tree and an unchanged head around the run"
    try:
        registry = load_committed_registry(scope.path, head, registry_rel)
        resolved_id, resolved_command, resolved_digest = resolve_gate(
            registry, lambda relative: read_committed_blob(scope.path, head, relative), gate_id, []
        )
    except (Refusal, ProducerError, subprocess.SubprocessError):
        return "names a gate the scope does not declare in a registry committed at the attested head"
    if resolved_id != gate_id or resolved_command != command or resolved_digest != digest:
        return "does not match the gate definition committed at the attested head"
    if command_problem(command, ctx.private_literals) is not None:
        return "records a command that attest would refuse"
    return None


def _derive_verification(ctx: Context, rep: Report) -> list[dict]:
    """Read attestations written by `attest`; head and exit_code come from the file, never from the manifest."""
    entries: list[dict] = []
    declared = ctx.manifest.get("verification")
    if not isinstance(declared, list) or not declared:
        # A8: an empty verification list is unmeasured at the checker, so the producer refuses to emit one.
        rep.gap("verification_required", "at least one attested verification entry is required (run `attest`)")
        return entries
    for item in declared:
        if not isinstance(item, dict) or item.get("scope") not in ctx.scopes:
            rep.gap("verification_scope_unknown", "every verification entry needs a declared scope id")
            continue
        scope = ctx.scopes[item["scope"]]
        if scope.kind != "git":
            rep.gap("verification_scope_not_git", f"verification of {scope.id}: only git scopes carry attested checks")
            continue
        try:
            relative = closeout.safe_path(item.get("evidence"))
        except closeout.Unmeasured:
            rep.gap(
                "verification_evidence_invalid", f"verification of {scope.id}: evidence must be repository-relative"
            )
            continue
        loaded = _read_json_file(ctx, rep, relative, "verification_evidence_unreadable")
        if loaded is None:
            continue
        raw, value = loaded
        if not isinstance(value, dict) or value.get("schema") != ATTESTATION_SCHEMA:
            rep.gap("verification_not_attested", f"{relative} is not a {ATTESTATION_SCHEMA} file written by `attest`")
            continue
        if value.get("session_id") != ctx.session_id or value.get("root_id") != scope.id:
            rep.gap("verification_binding_mismatch", f"{relative} does not bind this session and scope {scope.id}")
            continue
        head, code = value.get("head"), value.get("exit_code")
        if not isinstance(head, str) or not closeout.SHA.fullmatch(head) or type(code) is not int:
            rep.gap("verification_malformed", f"{relative} lacks an exact head or an integer exit code")
            continue
        gate_problem = _revalidate_gate(ctx, scope, head, value)
        if gate_problem is not None:
            rep.gap("verification_not_a_gate", f"{relative} {gate_problem}")
            continue
        entry: dict[str, Any] = {
            "root_id": scope.id,
            "head": head,
            "exit_code": code,
            "evidence": relative,
            "sha256": sha256_hex(raw),
        }
        if value.get("purpose") == "completion":
            entry["purpose"] = "completion"
            entry["owner_url"] = value.get("owner_url")
        rep.cite(relative)
        entries.append({"entry": entry, "scope": scope.id})
    return entries


def _derive_process_sidecar(ctx: Context, rep: Report) -> list[dict]:
    packet = ctx.manifest.get("process_ownership")
    if not packet:
        return []
    if not isinstance(packet, dict):
        rep.gap("process_sidecar_malformed", "process_ownership must be {evidence, sha256}")
        return []
    try:
        relative = closeout.safe_path(packet.get("evidence"))
    except closeout.Unmeasured:
        rep.gap("process_sidecar_malformed", "process_ownership.evidence must be repository-relative")
        return []
    loaded = _read_json_file(ctx, rep, relative, "process_sidecar_unreadable")
    if loaded is None:
        return []
    raw, value = loaded
    if (
        not isinstance(value, dict)
        or value.get("schema") != "limen.process_ownership.v1"
        or not isinstance(value.get("processes"), list)
        or packet.get("sha256") != sha256_hex(raw)
    ):
        rep.gap("process_sidecar_malformed", "the sidecar must be limen.process_ownership.v1 with a matching sha256")
        return []
    rep.cite(relative)
    return value["processes"]


def _derive_census(ctx: Context, seams: Seams, rep: Report, evidence: list[dict]) -> None:
    """A2: report the census as counts by category (no pids, no paths); a shared anchor cannot reach zero."""
    roots = tuple(scope.path for scope in ctx.scopes.values())
    observation = seams.observe(roots, ctx.session_id, anchor=ctx.anchor, evidence=evidence)
    if (
        not isinstance(observation, dict)
        or observation.get("complete") is not True
        or type(observation.get("process_count")) is not int
    ):
        raise ProducerError("process census is unavailable or incomplete")
    counts = observation.get("counts") if isinstance(observation.get("counts"), dict) else {}
    rep.census = {
        "complete": True,
        "process_count": observation["process_count"],
        "counts": {str(key): value for key, value in sorted(counts.items()) if isinstance(value, int) and value},
    }
    home = Path.home().resolve()
    shared = ctx.anchor == home or ctx.anchor in home.parents or ctx.anchor.parent == ctx.anchor
    if shared:
        rep.note(
            "the anchor is a shared directory (HOME or an ancestor): any other agent whose cwd is exactly the anchor is "
            "counted by the census, so a zero count cannot be relied on while other agents run"
        )
    if observation["process_count"]:
        message = (
            f"{observation['process_count']} process(es) with their working directory at the anchor or under a declared "
            f"scope are surviving or unattributed (by category: {rep.census['counts'] or 'unreported'}); quiesce or "
            "finish those lanes, or anchor the session at a dedicated quiet directory"
        )
        if shared:
            message += (
                ". The anchor is a shared directory (HOME or an ancestor): every other agent whose cwd is exactly the "
                "anchor is counted, so this session cannot reach zero while other agents run"
            )
        rep.gap("process_census_nonzero", message)


# ---- custody (A3, A4)


def _derive_custody(ctx: Context, seams: Seams, rep: Report) -> dict | None:
    block = ctx.manifest.get("custody")
    if not isinstance(block, dict) or block.get("mode") not in {"evidence", "absence"}:
        rep.gap("custody_required", "custody.mode must be `evidence` (portable custody v2 bundle) or `absence`")
        return None
    root_ids = sorted(ctx.scopes)
    if block["mode"] == "evidence":
        return _custody_evidence(ctx, rep, block, root_ids)
    return _custody_absence(ctx, seams, rep, root_ids)


def _custody_evidence(ctx: Context, rep: Report, block: dict, root_ids: list[str]) -> dict | None:
    try:
        relative = closeout.safe_path(block.get("bundle"))
    except closeout.Unmeasured:
        rep.gap("custody_evidence_unrecognized", "custody.bundle must name a committed portable custody bundle path")
        return None
    loaded = _read_json_file(ctx, rep, relative, "custody_evidence_unrecognized")
    if loaded is None:
        return None
    raw, value = loaded
    if isinstance(value, dict) and value.get("schema") == SEALED_TRACKED_SCHEMA:
        # A3: the redacted sealed-custody receipt binds neither the session nor any scope id or path hash.
        rep.gap(
            "custody_unbound_to_scope",
            "a sealed-custody tracked receipt carries no session id, scope ids or path hashes, so it cannot prove "
            "custody for these scopes; supply a limen.custody_receipt.v2 bundle that validate_bundle binds to them",
        )
        return None
    consumed: list[str] = []

    def read_evidence(packet: dict) -> bytes:
        path = closeout.safe_path(packet.get("evidence"))
        payload = read_receipt_file(ctx.receipt_root, path)  # type: ignore[arg-type]
        if sha256_hex(payload) != packet.get("sha256"):
            raise ValueError("supporting evidence digest mismatch")
        consumed.append(path)
        return payload

    try:
        from limen.portable_custody import validate_bundle

        validate_bundle(
            raw,
            session_id=ctx.session_id,
            scope_paths={scope.id: closeout.path_digest(scope.path) for scope in ctx.scopes.values()},
            read_evidence=read_evidence,
        )
    except ImportError as exc:
        raise ProducerError("portable custody validation dependencies are unavailable") from exc
    except (ValueError, TypeError, KeyError, OSError) as exc:
        rep.gap("custody_bundle_invalid", f"validate_bundle rejected the bundle ({type(exc).__name__})")
        return None
    rep.cite(relative)
    for path in consumed:
        rep.cite(path)
        problems = scrub_problems(
            read_receipt_file(ctx.receipt_root, path), literals=ctx.private_literals, allowed=[], strict=False
        )  # type: ignore[arg-type]
        if problems:
            rep.gap("committed_bytes_unsafe", f"custody evidence {path} contains {', '.join(problems)}")
    return {
        "verified": True,
        "root_ids": root_ids,
        "contract": CUSTODY_CONTRACT,
        "evidence": relative,
        "sha256": sha256_hex(raw),
    }


def _custody_absence(ctx: Context, seams: Seams, rep: Report, root_ids: list[str]) -> dict | None:
    problem = False
    if any(scope.kind != "git" for scope in ctx.scopes.values()):
        rep.gap(
            "custody_absence_not_measurable_for_retained_scope",
            "a retained scope holds artifacts outside git; absence cannot be measured, supply a portable custody bundle",
        )
        problem = True
    anchor_scope = next(
        (scope for scope in ctx.scopes.values() if scope.path == ctx.anchor and scope.kind == "git"), None
    )
    if anchor_scope is None:
        # A4: a clean git tree says nothing about untracked private artifacts in a non-git anchor.
        rep.gap(
            "custody_absence_anchor_not_git_scope",
            "the anchor is not itself a declared git scope, so private artifacts outside git cannot be excluded; "
            "supply a portable custody bundle",
        )
        problem = True
    if not ctx.evidence_dir_rel or problem:
        return None
    scopes_out: list[dict] = []
    for scope in ctx.scopes.values():
        if scope.absent:
            return None
        excluded: list[str] = []
        status = _git(scope.path, "status", "--porcelain=v1", "--ignored", "-z", "--untracked-files=all", raw=True)
        residual = sorted(closeout.dirty_paths(status))
        if scope.id == ctx.receipt_id:
            prefix = ctx.evidence_dir_rel + "/"
            excluded = [prefix, ctx.receipt_rel]
            residual = [path for path in residual if not path.startswith(prefix) and path != ctx.receipt_rel]
        if residual:
            rep.gap(
                "custody_absence_unproven",
                f"scope {scope.id} holds {len(residual)} untracked, ignored or modified path(s) "
                "(for example build caches); absence is not provable, supply a portable custody bundle",
            )
        stash = _git(scope.path, "stash", "list")
        if stash:
            rep.gap("custody_absence_unproven", f"scope {scope.id} has stashed local-only changes")
        row = {"root_id": scope.id, "head": _git(scope.path, "rev-parse", "HEAD"), "residual_path_count": len(residual)}
        row["stash_count"] = len(stash.splitlines()) if stash else 0
        if excluded:
            row["excluded"] = excluded
        else:
            # A4: publication is recorded only for scopes that are not the receipt root (their heads are final).
            row["published"] = _published_flag(scope)
            if row["published"] is not True:
                rep.gap("custody_absence_unproven", f"scope {scope.id} head is not remotely published; push it first")
        scopes_out.append(row)
    relative = f"{ctx.evidence_dir_rel}/custody-absence.json"
    reused = _reuse_evidence(ctx, rep, relative, ABSENCE_SCHEMA)
    evidence = {
        "schema": ABSENCE_SCHEMA,
        "session_id": ctx.session_id,
        "claim": "no untracked, ignored or stashed local-only payload in the declared git scopes",
        "scopes": scopes_out,
        "limits": [
            "self-measured by the producer; this is not an independent restore copy",
            "git scopes only; artifacts outside git are not measured",
        ],
    }
    if reused is None:
        data = json_bytes(evidence)
        rep.new_files[relative] = data
    else:
        data, existing = reused
        # A3/A16: an existing absence file is cited only if it IS the live measurement. The receipt-root head moves
        # when the receipt is committed, so an excluded row is compared without its head.
        if _absence_comparable(existing) != _absence_comparable(evidence):
            rep.gap(
                "custody_evidence_stale",
                "the existing absence evidence is not the live measurement of the declared scopes; "
                "remove it (it is untracked output of `build`) and rebuild",
            )
    rep.cite(relative)
    return {"verified": True, "root_ids": root_ids, "evidence": relative, "sha256": sha256_hex(data)}


def _absence_comparable(evidence: dict) -> dict:
    rows = evidence.get("scopes")
    normalized = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict):
            row = dict(row)
            if row.get("excluded"):
                row.pop("head", None)
            normalized.append(row)
    normalized.sort(key=lambda row: str(row.get("root_id", "")))
    return {
        "claim": evidence.get("claim"),
        "limits": evidence.get("limits"),
        "scopes": normalized,
    }


def _published_flag(scope: Scope) -> bool:
    branch = _derive_branch(scope)[0]
    if branch is None:
        return False
    try:
        return bool(closeout.published(scope.path, _git(scope.path, "rev-parse", "HEAD"), branch))
    except subprocess.CalledProcessError:
        return False


def _reuse_evidence(ctx: Context, rep: Report, relative: str, schema: str) -> tuple[bytes, dict] | None:
    """A16: an evidence file that already exists is validated and reused, never regenerated or overwritten."""
    try:
        raw = read_receipt_file(ctx.receipt_root, relative)  # type: ignore[arg-type]
    except FileNotFoundError:
        return None
    except OSError:
        rep.gap("evidence_unreadable", f"existing evidence {relative} is unreadable or reached through a symlink")
        return None
    try:
        value = json.loads(raw)
    except ValueError:
        value = None
    if not isinstance(value, dict) or value.get("schema") != schema or value.get("session_id") != ctx.session_id:
        rep.gap("evidence_exists_unrecognized", f"existing {relative} is not a valid {schema} file for this session")
        return None
    return raw, value


# ---- effects (A10, A17)


def _lookup(value: Any, dotted: str) -> Any:
    for part in dotted.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def _derive_effects(ctx: Context, seams: Seams, rep: Report, owners: dict) -> tuple[list[dict], dict]:
    declared = ctx.manifest.get("external_effects", [])
    state = {"unverified": 0}
    out: list[dict] = []
    if not isinstance(declared, list):
        rep.gap("external_effects_malformed", "external_effects must be a list")
        return out, state
    if not declared and ctx.manifest.get("external_effects_enumerated") is not True:
        # A10: an empty list is never emitted without an explicit enumeration attestation.
        rep.gap(
            "external_effects_not_enumerated",
            "list every PR, issue, pushed ref and export this session produced, or attest "
            "`external_effects_enumerated: true` when there are none",
        )
    for spec in declared:
        if not isinstance(spec, dict) or not isinstance(spec.get("id"), str) or not ID_RE.fullmatch(spec["id"]):
            rep.gap("external_effect_malformed", "every effect needs an id matching [A-Za-z0-9][A-Za-z0-9_.-]*")
            continue
        kind = spec.get("kind")
        if not isinstance(kind, str) or not kind:
            rep.gap("external_effect_malformed", f"effect {spec['id']}: kind is required")
            continue
        if "verified" in spec:
            # A10: a manifest-asserted verified flag is an overstatement the checker cannot catch.
            rep.gap(
                "external_effect_assertion",
                f"effect {spec['id']}: `verified` is derived from a readback, never asserted",
            )
            continue
        relative = f"{ctx.evidence_dir_rel}/effect-{spec['id']}.json" if ctx.evidence_dir_rel else ""
        if not relative:
            continue
        if kind in NATIVE_EFFECT_KINDS:
            entry = _native_effect(ctx, seams, rep, spec, relative)
        else:
            entry = _caller_effect(ctx, rep, spec)
        if entry is None:
            continue
        if entry["verified"] is not True:
            state["unverified"] += 1
            entry["owner_url"] = spec.get("owner_url", ctx.manifest.get("owner_url"))
            _owner_state(
                rep, seams, owners, entry["owner_url"], "external_effect_owner_unavailable", f"effect {spec['id']}"
            )
        out.append(entry)
    return out, state


def _native_effect(ctx: Context, seams: Seams, rep: Report, spec: dict, relative: str) -> dict | None:
    expect = spec.get("expect")
    if not isinstance(expect, dict) or not expect:
        # A10: an empty `expect` would be vacuously satisfied.
        rep.gap("external_effect_expect_required", f"effect {spec['id']}: a non-empty `expect` object is required")
        return None
    before = len(rep.gaps)
    reused = _reuse_evidence_effect(ctx, rep, relative, spec)
    if len(rep.gaps) > before:
        return None
    if reused is not None:
        raw, matches_ = reused
        rep.cite(relative)
        return {
            "id": spec["id"],
            "kind": spec["kind"],
            "verified": matches_,
            "evidence": relative,
            "sha256": sha256_hex(raw),
        }
    try:
        readback = seams.read_effect(spec)
    except closeout.Unmeasured:
        rep.gap("external_effect_unreadable", f"effect {spec['id']}: the live readback is unavailable or malformed")
        return None
    matched = _expect_matches(readback, expect)
    evidence = {
        "schema": EFFECT_SCHEMA,
        "session_id": ctx.session_id,
        "id": spec["id"],
        "kind": spec["kind"],
        "observed_at": seams.now().isoformat(),
        "readback": readback,
        "expect": expect,
        "matches": matched,
    }
    data = json_bytes(evidence)
    rep.new_files[relative] = data
    rep.cite(relative)
    return {
        "id": spec["id"],
        "kind": spec["kind"],
        "verified": matched,
        "evidence": relative,
        "sha256": sha256_hex(data),
    }


def _expect_matches(readback: Any, expect: dict) -> bool:
    return all(_lookup(readback, key) == value for key, value in expect.items())


def _reuse_evidence_effect(ctx: Context, rep: Report, relative: str, spec: dict) -> tuple[bytes, bool] | None:
    """A10: `verified` is recomputed from the stored readback against the manifest's CURRENT `expect`; the file's own
    `matches` flag is never trusted. Evidence recorded for a different expectation, or whose flag disagrees with its
    own readback, is refused rather than silently re-judged (it is create-only: use a new effect id)."""
    reused = _reuse_evidence(ctx, rep, relative, EFFECT_SCHEMA)
    if reused is None:
        return None
    raw, value = reused
    readback, stored_expect = value.get("readback"), value.get("expect")
    if (
        value.get("id") != spec["id"]
        or value.get("kind") != spec["kind"]
        or type(value.get("matches")) is not bool
        or not isinstance(readback, dict)
        or not isinstance(stored_expect, dict)
        or not stored_expect
    ):
        rep.gap("evidence_exists_unrecognized", f"existing {relative} does not describe effect {spec['id']}")
        return None
    if stored_expect != spec["expect"]:
        rep.gap(
            "external_effect_evidence_stale",
            f"effect {spec['id']}: {relative} was recorded for a different `expect`; use a new effect id",
        )
        return None
    recomputed = _expect_matches(readback, spec["expect"])
    if recomputed is not value["matches"]:
        rep.gap(
            "external_effect_evidence_inconsistent",
            f"effect {spec['id']}: {relative} claims a verdict its own readback does not support",
        )
        return None
    return raw, recomputed


def _caller_effect(ctx: Context, rep: Report, spec: dict) -> dict | None:
    try:
        relative = closeout.safe_path(spec.get("evidence"))
    except closeout.Unmeasured:
        rep.gap(
            "external_effect_evidence_required",
            f"effect {spec['id']}: caller-supplied kinds need a committed evidence file",
        )
        return None
    loaded = _read_json_file(ctx, rep, relative, "external_effect_evidence_unreadable")
    if loaded is None:
        return None
    raw, _ = loaded
    rep.cite(relative)
    # A10: a caller-supplied kind is never measured here, so it is never recorded as verified.
    return {"id": spec["id"], "kind": spec["kind"], "verified": False, "evidence": relative, "sha256": sha256_hex(raw)}


def _derive_effect_attribution(ctx: Context, rep: Report) -> None:
    receipt_scope = ctx.scopes.get(ctx.receipt_id)
    for spec in (
        ctx.manifest.get("external_effects", []) if isinstance(ctx.manifest.get("external_effects"), list) else []
    ):
        if not isinstance(spec, dict) or spec.get("kind") != "git_ref" or receipt_scope is None:
            continue
        if (
            receipt_scope.repository
            and spec.get("repository") == receipt_scope.repository
            and spec.get("branch") == receipt_scope.branch
        ):
            # A17: a readback of the receipt's own branch can never contain the commit that carries it.
            rep.gap(
                "effect_is_receipt_branch",
                f"effect {spec.get('id')}: the receipt branch is proven by its scope row, not by an effect entry",
            )


# ---- git scopes


def _derive_branch(scope: Scope) -> tuple[str | None, str]:
    """A15: derive the publication branch from the upstream configuration, never from a name guess."""
    root = scope.path
    try:
        current = _git(root, "symbolic-ref", "-q", "--short", "HEAD")
    except subprocess.CalledProcessError:
        current = None
    declared = scope.spec.get("publication_branch")
    if current is None:
        if isinstance(declared, str) and declared and not declared.startswith("-"):
            return declared, "detached"
        return None, "detached_unbound"
    try:
        remote = _git(root, "config", "--get", f"branch.{current}.remote")
        merge = _git(root, "config", "--get", f"branch.{current}.merge")
    except subprocess.CalledProcessError:
        return None, "unbound"
    if remote != "origin" or not merge.startswith("refs/heads/"):
        return None, "unbound"
    derived = merge.removeprefix("refs/heads/")
    if isinstance(declared, str) and declared and declared != derived:
        return derived, "mismatch"
    return derived, "upstream"


def _derive_git_scope(
    ctx: Context, seams: Seams, rep: Report, scope: Scope, owners: dict, attestations: list[dict], cited: set[str]
) -> dict | None:
    sid, root = scope.id, scope.path
    is_receipt = sid == ctx.receipt_id
    if scope.absent:
        return None
    try:
        top = Path(_git(root, "rev-parse", "--show-toplevel")).resolve()
    except subprocess.CalledProcessError:
        rep.gap("scope_not_git_root", f"scope {sid} is not a git checkout")
        return None
    if top != root:
        rep.gap("scope_not_git_root", f"scope {sid} is not an exact git top level")
        return None
    head = _git(root, "rev-parse", "HEAD")
    scope.head = head
    row: dict[str, Any] = {"id": sid, "kind": "git", "path_sha256": closeout.path_digest(root)}
    fact: dict[str, Any] = {"id": sid, "kind": "git", "head": head, "receipt_root": is_receipt}
    # origin, repository identity (A14: never echo an origin that carries credentials)
    try:
        origin = _git(root, "remote", "get-url", "origin")
    except subprocess.CalledProcessError:
        rep.gap("origin_missing", f"scope {sid} has no `origin` remote")
        return None
    if origin_credential_problem(origin):
        rep.gap("origin_has_embedded_credentials", f"scope {sid}: the origin remote embeds credentials; fix the remote")
        return None
    try:
        github_slug = closeout.github_repository_slug(origin)
    except closeout.Unmeasured:
        rep.gap("origin_invalid", f"scope {sid}: the origin remote is not a valid GitHub remote")
        return None
    default_branch: str | None = None
    if github_slug is not None:
        repo = seams.read_repository(github_slug)
        repository_id = repo.get("id")
        if type(repository_id) is not int or not isinstance(repo.get("full_name"), str):
            rep.gap("repository_identity_unavailable", f"scope {sid}: GitHub did not return a numeric id and full_name")
            return None
        row["repository"], row["repository_id"] = repo["full_name"], repository_id
        default_branch = repo.get("default_branch") if isinstance(repo.get("default_branch"), str) else None
        scope.repository = repo["full_name"]
    else:
        repository = origin.removesuffix(".git")
        private = repository.startswith("/") or "file://" in repository or str(Path.home()) in repository
        if private and not ctx.allow_local_remote:
            rep.gap(
                "repository_string_is_private_path",
                f"scope {sid}: a non-GitHub origin is committed verbatim and here it is a private path",
            )
            return None
        row["repository"] = repository
        scope.repository = repository
        if ctx.allow_local_remote:
            ctx.allowed_literals.append(repository)
    fact["repository"] = row["repository"]
    # ownership is derived first so a later gap on this scope never leaves a parent's coverage looking empty
    owned = _validated_paths(rep, scope.spec.get("owned_paths"), "owned_paths_invalid", f"scope {sid} owned_paths")
    retained = _validated_retained(rep, seams, owners, ctx, scope.spec.get("retained_work"), sid)
    if owned is None or retained is None:
        return None
    scope.owned, scope.retained_work = owned, retained
    row["owned_paths"], row["retained_work"] = owned, retained
    if scope.parent:
        row["nested_in"] = scope.parent
    siblings = [path for item in retained for path in item["paths"]]
    # publication branch (A15)
    branch, how = _derive_branch(scope)
    if branch is None:
        rep.gap(
            "publication_branch_unbound",
            f"scope {sid}: the checkout has no `origin` upstream (branch.<b>.remote/merge) and is not an explicit "
            "detached publication; set the upstream with `git push -u origin <branch>`",
        )
        return None
    if how == "mismatch":
        rep.gap(
            "publication_branch_mismatch",
            f"scope {sid}: the manifest publication_branch differs from the derived upstream",
        )
        return None
    scope.branch = branch
    row["publication_branch"] = branch
    fact["publication_branch"], fact["publication_branch_source"] = branch, how
    if is_receipt:
        rep.note(
            f"scope {sid}: the receipt root's final head is the receipt commit; push it, then run `check` (publication "
            "is proven on the topic branch, not on main; merged is reported separately)"
        )
    else:
        # A1: a branch that was never pushed makes published() RAISE; that is a gap here, never exit 2.
        try:
            if not closeout.published(root, head, branch):
                rep.gap("not_remotely_durable", f"scope {sid}: HEAD is not on the live remote branch; push it")
        except subprocess.CalledProcessError:
            rep.gap(
                "ref_absent_on_remote",
                f"scope {sid}: the publication branch is absent on the remote (never pushed or deleted after a merge)",
            )
        subject = head
        row["subject_head"] = subject
    # shared publication branch across checkouts of one repository (A21)
    for other in ctx.scopes.values():
        if other.id != sid and other.kind == "git" and other.repository == scope.repository and other.branch == branch:
            pair = " and ".join(sorted([other.id, sid]))
            rep.gap(
                "shared_publication_branch",
                f"scopes {pair} are two checkouts of one repository on the same publication branch",
            )
    # base_head (A7)
    base = _derive_base(rep, scope, head, default_branch, github_slug is not None, bool(owned or retained))
    if base is None:
        return None
    row["base_head"] = base
    fact["base_head"] = base
    # attribution preflight (mirrors the checker; the real dry run in `build` remains the authority)
    evidence_set = set(cited) | {ctx.receipt_rel}
    dirty = closeout.dirty_paths(_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all", raw=True))
    committed = [
        os.fsdecode(raw) for raw in _git(root, "diff", "--name-only", "-z", base, head, raw=True).split(b"\0") if raw
    ]
    unattributed_dirty, unattributed_committed = [], []
    for path in sorted(dirty):
        if is_receipt and path in evidence_set:
            continue
        if closeout.matches(path, owned):
            rep.gap("owned_uncommitted_path", f"scope {sid}: owned path {path} is not committed")
        elif not closeout.matches(path, siblings):
            unattributed_dirty.append(path)
    for path in committed:
        if is_receipt and path in evidence_set:
            continue
        if not closeout.matches(path, owned + siblings):
            unattributed_committed.append(path)
    if unattributed_dirty:
        rep.gap(
            "unattributed_dirty_path", f"scope {sid}: {len(unattributed_dirty)} dirty path(s) have no declared owner"
        )
    if unattributed_committed:
        rep.gap(
            "unattributed_committed_path",
            f"scope {sid}: {len(unattributed_committed)} committed path(s) have no declared owner",
        )
    if unattributed_dirty or unattributed_committed:
        rep.candidates[sid] = {
            "unattributed_dirty": unattributed_dirty,
            "unattributed_committed": unattributed_committed,
        }
    changed = set(dirty) | set(committed)
    for path in owned:  # A18: ownership must not be broader than what actually changed
        if not any(closeout.matches(item, [path]) for item in changed):
            rep.gap("owned_path_matches_nothing", f"scope {sid}: owned path {path} matches no committed or dirty path")
    for path in siblings:
        if not any(closeout.matches(item, [path]) for item in changed):
            rep.gap(
                "retained_path_matches_nothing", f"scope {sid}: retained path {path} matches no committed or dirty path"
            )
    # verification freshness
    mine = [item for item in attestations if item["scope"] == sid]
    for item in mine:
        revision = item["entry"]["head"]
        if not _git_ok(root, "merge-base", "--is-ancestor", revision, head):
            rep.gap("verification_head_not_ancestor", f"scope {sid}: attested head is not an ancestor of HEAD")
        elif owned and _git(root, "diff", "--name-only", revision, head, "--", *owned):
            rep.gap("verification_stale", f"scope {sid}: owned paths changed since the attested head; re-run `attest`")
    if owned and not mine:
        rep.gap("owned_scope_unverified", f"scope {sid} owns paths but has no attested verification")
    fact.update(
        dirty_count=len(dirty),
        committed_count=len(committed),
        owned_paths=len(owned),
        retained_paths=len(siblings),
    )
    rep.facts.append(fact)
    return row


def _derive_base(
    rep: Report, scope: Scope, head: str, default_branch: str | None, github: bool, claims_paths: bool
) -> str | None:
    sid, root = scope.id, scope.path
    spec = scope.spec.get("base_head")
    default_ref = f"refs/remotes/origin/{default_branch}" if github and default_branch else None
    fork_point: str | None = None
    if default_ref is not None:
        try:
            fork_point = _git(root, "merge-base", head, default_ref)
        except subprocess.CalledProcessError:
            fork_point = None
    if spec == "fork-point":
        if not github:
            rep.gap(
                "fork_point_needs_github_default_branch",
                f"scope {sid}: fork-point is derivable only from a GitHub default branch; give an explicit base_head",
            )
            return None
        if fork_point is None:
            rep.gap(
                "default_branch_ref_unavailable",
                f"scope {sid}: refs/remotes/origin/{default_branch} is absent; fetch the default branch",
            )
            return None
        if fork_point == head or _git_ok(root, "merge-base", "--is-ancestor", head, default_ref):  # type: ignore[arg-type]
            # A7: the attribution window would be empty, which passes the unattributed-commit check vacuously.
            rep.gap(
                "fork_point_equals_head",
                f"scope {sid}: the fork point equals HEAD (already contained in the default branch); the attribution window is empty",
            )
            return None
        return fork_point
    if not isinstance(spec, str) or not closeout.SHA.fullmatch(spec):
        rep.gap("base_head_required", f"scope {sid}: base_head must be `fork-point` or an exact 40-hex revision")
        return None
    if not _git_ok(root, "merge-base", "--is-ancestor", spec, head):
        rep.gap("base_not_ancestor", f"scope {sid}: base_head is not an ancestor of HEAD")
        return None
    if spec == head and claims_paths:
        rep.gap(
            "base_equals_head",
            f"scope {sid}: base_head equals HEAD but the scope claims paths; the attribution window is empty",
        )
        return None
    if fork_point is not None and not _git_ok(root, "merge-base", "--is-ancestor", spec, fork_point):
        # A7: an explicit base later than the fork point hides session commits from attribution.
        rep.gap(
            "base_after_fork_point",
            f"scope {sid}: base_head is later than the fork point and would hide commits from attribution",
        )
        return None
    return spec


def _validated_paths(rep: Report, value: Any, code: str, subject: str) -> list[str] | None:
    if value is None:
        value = []
    if not _strings(value):
        rep.gap(code, f"{subject} must be a list of repository-relative paths")
        return None
    out = []
    for path in value:
        try:
            out.append(closeout.safe_path(path))
        except closeout.Unmeasured:
            rep.gap(code, f"{subject}: an entry is not a repository-relative path")
            return None
    return out


def _validated_retained(
    rep: Report, seams: Seams, owners: dict, ctx: Context, value: Any, sid: str
) -> list[dict] | None:
    if value is None:
        value = []
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        rep.gap("retained_work_malformed", f"scope {sid}: retained_work must be a list of {{paths, owner_url}}")
        return None
    out = []
    for item in value:
        paths = _validated_paths(rep, item.get("paths"), "retained_work_malformed", f"scope {sid} retained_work.paths")
        if paths is None or not paths:
            rep.gap("retained_work_malformed", f"scope {sid}: each retained_work item needs non-empty paths")
            return None
        url = item.get("owner_url")
        if url == ctx.manifest.get("owner_url"):
            # A18: the session's own owner cannot launder unknown ownership into `retained`.
            rep.gap(
                "retained_owner_is_receipt_owner",
                f"scope {sid}: retained work needs the foreign owner's own open issue or PR",
            )
            return None
        if not _owner_state(rep, seams, owners, url, "retained_owner_unavailable", f"scope {sid} retained work"):
            return None
        out.append({"paths": paths, "owner_url": url})
    return out


def _derive_retained_scope(ctx: Context, seams: Seams, rep: Report, scope: Scope, owners: dict) -> dict | None:
    if scope.absent:
        return None
    row: dict[str, Any] = {"id": scope.id, "kind": "retained", "path_sha256": closeout.path_digest(scope.path)}
    url = scope.spec.get("owner_url")
    if not _owner_state(rep, seams, owners, url, "retained_scope_owner_unavailable", f"retained scope {scope.id}"):
        return None
    row["owner_url"] = url
    retained = _validated_retained(rep, seams, owners, ctx, scope.spec.get("retained_work"), scope.id)
    if retained is None:
        return None
    scope.retained_work = retained
    if retained:
        row["retained_work"] = retained  # A9: the checker reads retained_work from every row, whatever its kind
    if scope.parent:
        row["nested_in"] = scope.parent  # A9: a retained row nested in another scope needs nested_in too
    rep.facts.append({"id": scope.id, "kind": "retained", "owner_url_open": True})
    return row


def _derive_nested(ctx: Context, rep: Report) -> None:
    for scope in ctx.scopes.values():
        if scope.parent is None:
            continue
        parent = ctx.scopes[scope.parent]
        prefix = scope.path.relative_to(parent.path).as_posix()
        if not any(closeout.matches(prefix, item["paths"]) for item in parent.retained_work):
            rep.gap(
                "nested_scope_unowned",
                f"scope {scope.id} is nested in {parent.id}, whose retained_work must explicitly cover its prefix; "
                "the producer never edits a parent's retained work to make it fit",
            )


def _derive_unattributed_evidence(ctx: Context, rep: Report) -> None:
    """A12: attestation files this run does not cite would surface as unattributed paths; name them."""
    if not ctx.evidence_dir_rel or ctx.receipt_root is None:
        return
    try:
        directory, _ = _open_directory_chain(ctx.receipt_root, _chain_parts(ctx.evidence_dir_rel))
    except FileNotFoundError:
        return
    except OSError:
        rep.gap("evidence_dir_unsafe", "the evidence directory is unreadable or a symlink")
        return
    try:
        names = sorted(os.listdir(directory))
    finally:
        os.close(directory)
    cited = set(rep.cited) | set(rep.new_files)
    for name in names:
        relative = f"{ctx.evidence_dir_rel}/{name}"
        if relative not in cited:
            rep.gap(
                "uncited_evidence_file",
                f"{relative} is not cited by this manifest and would be an unattributed path; cite it or remove it "
                "(the producer never deletes)",
            )


def _derive_disposition(
    ctx: Context, rep: Report, attestations: list[dict], effect_state: dict, owners: dict, seams: Seams
) -> None:
    """A23: derive the disposition; `complete` is refused whenever anything is retained, unverified or failing."""
    runs = rep.audit.get("runs") if isinstance(rep.audit.get("runs"), list) else []
    has_retained = any(scope.kind == "retained" or scope.retained_work for scope in ctx.scopes.values())
    failing = [item for item in attestations if item["entry"]["exit_code"] != 0]
    all_success = all(isinstance(row, dict) and row.get("status") in SUCCESS_STATUSES for row in runs)
    derived = (
        "complete" if all_success and not has_retained and not failing and not effect_state["unverified"] else "handoff"
    )
    claimed = ctx.manifest.get("disposition")
    owned_any = any(scope.owned for scope in ctx.scopes.values())
    if claimed is None:
        rep.disposition = derived
    elif claimed == "complete" and derived != "complete":
        rep.gap(
            "disposition_overstated",
            "`complete` is refused: the session retains work, has unverified effects, failing checks or non-successful runs",
        )
    elif claimed == "read_only":
        rep.disposition = "read_only"
        if owned_any:
            rep.gap("read_only_with_owned_paths", "a session that owns paths cannot be read_only")
    elif claimed in {"complete", "handoff"}:
        rep.disposition = claimed
    else:
        rep.gap("disposition_invalid", "disposition must be omitted or one of complete, handoff, read_only")
    if failing:
        for item in failing:
            entry = item["entry"]
            if rep.disposition != "handoff" or entry.get("purpose") != "completion":
                rep.gap(
                    "required_predicate_failed",
                    f"{entry['root_id']}: a failing check is allowed only as a `completion` check under handoff",
                )
            else:
                _owner_state(
                    rep,
                    seams,
                    owners,
                    entry.get("owner_url"),
                    "failing_check_owner_unavailable",
                    f"failing check of {entry['root_id']}",
                )
    owner_url = ctx.manifest.get("owner_url")
    if rep.disposition == "handoff" and isinstance(owner_url, str):
        value = owners.get(owner_url)
        if value is not None and value.get("state") != "open":
            rep.gap("handoff_owner_not_open", "a handoff requires an open session owner")


def _finalize_files(ctx: Context, rep: Report) -> None:
    assert rep.receipt_bytes is not None and ctx.receipt_root is not None
    for relative, data in rep.new_files.items():
        problems = scrub_problems(data, literals=ctx.private_literals, allowed=ctx.allowed_literals, strict=True)
        if problems:
            rep.gap("committed_bytes_unsafe", f"{relative} would contain {', '.join(problems)}")
    problems = scrub_problems(
        rep.receipt_bytes, literals=ctx.private_literals, allowed=ctx.allowed_literals, strict=True
    )
    if problems:
        rep.gap("committed_bytes_unsafe", f"the receipt would contain {', '.join(problems)}")
    for relative in rep.cited:
        if relative in rep.new_files:
            continue
        try:
            data = read_receipt_file(ctx.receipt_root, relative)
        except OSError:
            continue
        # Every cited byte gets the strict scan (assignment and flag shapes included), wherever the file lives:
        # caller-supplied effect and custody evidence is committed and cited exactly like producer-authored files.
        problems = scrub_problems(data, literals=ctx.private_literals, allowed=ctx.allowed_literals, strict=True)
        if problems:
            rep.gap("committed_bytes_unsafe", f"cited evidence {relative} contains {', '.join(problems)}")
    receipt_path = ctx.receipt_root / ctx.receipt_rel
    if os.path.lexists(receipt_path):
        existing = read_receipt_file(ctx.receipt_root, ctx.receipt_rel)
        if existing == rep.receipt_bytes:
            rep.receipt_exists_identical = True
        else:
            rep.gap(
                "receipt_exists_use_distinct_name",
                "a different receipt already exists at this path; use receipt.name for a new one",
            )
            return
    rep.cite(ctx.receipt_rel)
    if not rep.receipt_exists_identical:
        rep.new_files[ctx.receipt_rel] = rep.receipt_bytes


# --------------------------------------------------------------------------- dry run (A11)


def filter_porcelain(payload: bytes, hidden: set[str]) -> bytes:
    tokens = iter(payload.split(b"\0"))
    kept: list[bytes] = []
    for row in tokens:
        if not row:
            continue
        if len(row) < 4 or row[2:3] != b" ":
            raise closeout.Unmeasured("invalid Git porcelain")
        path = os.fsdecode(row[3:])
        extra = [next(tokens, b"")] if (b"R" in row[:2] or b"C" in row[:2]) else []
        if path not in hidden:
            kept.extend([row, *extra])
    return b"".join(row + b"\0" for row in kept)


@contextlib.contextmanager
def dry_run_overlay(receipt_root: Path, overlay: set[str], *, shim_publication: bool = True) -> Iterator[None]:
    """A11: let the REAL checker see working-tree bytes for uncommitted receipt files, and pretend only the
    receipt root is published. Everything else is delegated, so producer and checker cannot drift."""
    original_git, original_published = closeout.git, closeout.published
    resolved = receipt_root.resolve()

    def git_shim(root: Path, *args: str, raw: bool = False) -> Any:
        if Path(root).resolve() == resolved and args:
            if args[0] == "show" and len(args) == 2 and ":" in args[1]:
                relative = args[1].partition(":")[2]
                if relative in overlay:
                    data = read_receipt_file(resolved, relative)
                    return data if raw else data.decode("utf-8").rstrip("\n")
            if args[0] == "status" and raw:
                return filter_porcelain(original_git(root, *args, raw=True), overlay)
        return original_git(root, *args, raw=raw)

    def published_shim(root: Path, revision: str, branch: str) -> bool:
        if Path(root).resolve() == resolved:
            return True
        return original_published(root, revision, branch)

    closeout.git = git_shim  # type: ignore[assignment]
    if shim_publication:
        closeout.published = published_shim  # type: ignore[assignment]
    try:
        yield
    finally:
        closeout.git, closeout.published = original_git, original_published  # type: ignore[assignment]


def dry_run(ctx: Context, rep: Report, seams: Seams) -> dict:
    roots = {scope.id: scope.path for scope in ctx.scopes.values()}
    receipt_path = ctx.receipt_root / ctx.receipt_rel  # type: ignore[operator]
    with dry_run_overlay(ctx.receipt_root, set(rep.overlay)):  # type: ignore[arg-type]
        return closeout.evaluate_scoped(
            ctx.anchor,
            ctx.session_id,
            receipt_path,
            roots,
            audit=rep.audit,
            binding=rep.binding,
            native_transcript=None,
            read_owner=seams.read_owner,
            read_repository=seams.read_repository,
            observe_processes=seams.observe,
        )


# --------------------------------------------------------------------------- output


def checker_identity(canonical: Path | None) -> dict:
    """A24: name the checker module judging this run and flag skew against the canonical copy."""
    path = Path(closeout.__file__).resolve()
    info: dict[str, Any] = {"module": "limen/session_closeout.py", "module_sha256": sha256_hex(path.read_bytes())}
    if canonical is None and os.environ.get("LIMEN_ROOT"):
        canonical = Path(os.environ["LIMEN_ROOT"]) / "cli/src/limen/session_closeout.py"
    if canonical is not None and canonical.is_file():
        info["canonical_sha256"] = sha256_hex(canonical.read_bytes())
        info["skew"] = info["canonical_sha256"] != info["module_sha256"]
    return info


def emit(args: argparse.Namespace, payload: dict) -> None:
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    print(f"session-closeout-receipt {payload.get('verb')}: {payload.get('status')}")
    for gap in payload.get("gaps", []):
        print(f"gap: {gap['code']}: {gap['message']}")
    for note in payload.get("notes", []):
        print(f"note: {note}")
    for key in ("reason", "error_type"):
        if key in payload:
            print(f"{key}: {payload[key]}")
    for key in ("write", "git_add"):
        for item in payload.get(key, []) if isinstance(payload.get(key), list) else []:
            print(f"{key}: {item}")
    for key in ("census", "checker", "dry_run", "disposition", "recheck"):
        if key in payload:
            print(f"{key}: {json.dumps(payload[key], sort_keys=True)}")


def gaps_payload(rep_gaps: list[tuple[str, str]]) -> list[dict]:
    return [{"code": code, "message": message} for code, message in sorted(rep_gaps)]


def base_payload(verb: str, rep: Report, ctx: Context, args: argparse.Namespace) -> dict:
    return {
        "schema": "limen.session_closeout_producer.v1",
        "verb": verb,
        "status": "gaps" if rep.gaps else "ready",
        "session_id": ctx.session_id,
        "gaps": gaps_payload(rep.gaps),
        "notes": rep.notes,
        "census": rep.census,
        "disposition": rep.disposition,
        "scopes": rep.facts,
        "unattributed_NOT_written": rep.candidates,
        "checker": checker_identity(getattr(args, "canonical_checker", None)),
        "residual_risk": (
            "path_sha256 and session_root_path_sha256 of well-known private paths are brute-forceable; the checker "
            "mandates them, so only opaque ids appear anywhere else"
        ),
    }


def git_add_list(rep: Report) -> list[str]:
    paths = sorted(set(rep.cited))
    return [f"git add -- {' '.join(shlex.quote(path) for path in paths)}"] if paths else []


# --------------------------------------------------------------------------- verbs


def cmd_plan(args: argparse.Namespace, seams: Seams) -> int:
    ctx = prepare(args.manifest, allow_local_remote=args.allow_local_remote)
    rep = derive(ctx, seams)
    payload = base_payload("plan", rep, ctx, args)
    payload["write"] = sorted(rep.new_files)
    payload["git_add"] = git_add_list(rep)
    payload["dry_run"] = "skipped: plan is read-only; `build` runs the real checker as a labelled dry run"
    emit(args, payload)
    return 1 if rep.gaps else 0


def _rollback(ctx: Context, created: list[str], created_dirs: list[str]) -> None:
    for relative in reversed(created):
        with contextlib.suppress(OSError):
            os.unlink(ctx.receipt_root / relative)  # type: ignore[operator]
    for relative in reversed(created_dirs):
        with contextlib.suppress(OSError):
            os.rmdir(ctx.receipt_root / relative)  # type: ignore[operator]


def cmd_build(args: argparse.Namespace, seams: Seams) -> int:
    ctx = prepare(args.manifest, allow_local_remote=args.allow_local_remote)
    rep = derive(ctx, seams)
    payload = base_payload("build", rep, ctx, args)
    if rep.gaps or rep.receipt is None:
        emit(args, payload)
        return 1
    created: list[str] = []
    created_dirs: list[str] = []
    try:
        for relative, data in rep.new_files.items():  # evidence first, the receipt last
            created_dirs.extend(create_only(ctx.receipt_root, relative, data, create_from=evidence_create_from(ctx)))  # type: ignore[arg-type]
            created.append(relative)
        try:
            result = dry_run(ctx, rep, seams)
        except closeout.Unmeasured as exc:
            rep.gap("checker_unmeasured", f"the real checker could not measure the receipt: {exc}")
            result = None
    except BaseException:
        _rollback(ctx, created, created_dirs)
        raise
    if result is not None and result.get("findings"):
        for finding in result["findings"]:
            rep.gap("checker_finding", str(finding))
    if rep.gaps:
        _rollback(ctx, created, created_dirs)
        payload = base_payload("build", rep, ctx, args)
        payload["status"] = "refused_rolled_back"
        emit(args, payload)
        return 1
    payload["status"] = "unchanged" if rep.receipt_exists_identical and not created else "built"
    payload["write"] = created
    payload["git_add"] = git_add_list(rep)
    payload["dry_run"] = {
        "non_evidence": True,
        "note": "receipt-root publication and uncommitted bytes were simulated; run `check` bare after the push",
        "findings": [],
    }
    emit(args, payload)
    return 0


def _argv(ctx: Context, receipt_path: Path) -> list[str]:
    out = ["--session-id", ctx.session_id, "--worktree", str(ctx.anchor), "--receipt", str(receipt_path)]
    for scope in ctx.scopes.values():
        out.extend(["--scope-root", f"{scope.id}={scope.path}"])
    return [*out, "--json"]


def _receipt_branch(ctx: Context, receipt_path: Path) -> str | None:
    try:
        receipt = json.loads(receipt_path.read_bytes())
    except (OSError, ValueError):
        return None
    for row in receipt.get("scope_roots", []) if isinstance(receipt, dict) else []:
        if isinstance(row, dict) and row.get("id") == ctx.receipt_id:
            branch = row.get("publication_branch")
            return branch if isinstance(branch, str) else None
    return None


def _recheck_heads(ctx: Context, receipt_path: Path) -> dict:
    """A22: report which scope's head moved since the (create-only) receipt bound subject_head."""
    receipt = json.loads(receipt_path.read_bytes())
    moved, held = [], []
    for row in receipt.get("scope_roots", []):
        scope = ctx.scopes.get(row.get("id"))
        if scope is None or row.get("kind") != "git" or row["id"] == ctx.receipt_id:
            continue
        (held if _git(scope.path, "rev-parse", "HEAD") == row.get("subject_head") else moved).append(row["id"])
    return {"moved": sorted(moved), "held": sorted(held)}


def cmd_check(args: argparse.Namespace, seams: Seams) -> int:
    ctx = prepare(args.manifest, allow_local_remote=args.allow_local_remote)
    if ctx.receipt_root is None or not ctx.receipt_rel or not ctx.scopes:
        raise ProducerError("the manifest does not locate a receipt")
    receipt_path = ctx.receipt_root / ctx.receipt_rel
    if not receipt_path.is_file():
        raise ProducerError("the receipt does not exist; run `build` first")
    payload: dict[str, Any] = {
        "schema": "limen.session_closeout_producer.v1",
        "verb": "check",
        "checker": checker_identity(args.canonical_checker),
        "manifest_gaps": gaps_payload(ctx.gaps),
    }
    if args.recheck_heads:
        payload["recheck"] = _recheck_heads(ctx, receipt_path)
        payload["status"] = "heads_moved" if payload["recheck"]["moved"] else "heads_held"
        emit(args, payload)
        return 1 if payload["recheck"]["moved"] else 0
    argv = _argv(ctx, receipt_path)
    dry = False
    if args.expect_unpublished:
        branch = _receipt_branch(ctx, receipt_path)
        head = _git(ctx.receipt_root, "rev-parse", "HEAD")
        publication = "published"
        try:
            if not closeout.published(ctx.receipt_root, head, branch or ""):
                publication = "not_remotely_durable"
        except subprocess.CalledProcessError:
            publication = "ref_absent_on_remote"  # A1: never exit 2 for a first push
        payload["receipt_root_publication"] = publication
        dry = publication != "published"
    buffer = io.StringIO()
    context = dry_run_overlay(ctx.receipt_root, set(), shim_publication=True) if dry else contextlib.nullcontext()
    with context, contextlib.redirect_stdout(buffer):
        code = closeout.main(argv)
    try:
        result = json.loads(buffer.getvalue())
    except ValueError as exc:
        raise ProducerError("the checker produced no JSON") from exc
    if dry:
        # A1/A11: a labelled non-evidence dry run; its result is never emitted as a pass.
        payload.update(status="dry_run_clean_not_evidence" if code == 0 else "dry_run_findings", non_evidence=True)
        payload["checker_exit"] = code
        payload["findings"] = result.get("findings", []) if isinstance(result, dict) else []
        if code != 0 and isinstance(result, dict) and result.get("reason"):
            payload["reason"] = result["reason"]
        emit(args, payload)
        return 3 if code == 0 else code
    payload["status"] = "released" if code == 0 else "findings" if code == 1 else "unmeasured"
    payload["checker_exit"] = code
    payload["checker_result"] = result
    emit(args, payload)
    return code


# ---- attest (A5, A6)


def read_committed_blob(root: Path, head: str, relative: str) -> bytes | None:
    """The bytes of `relative` as committed at `head`, or None when that commit has no such file.

    The gate registry and the verify-scoped wrapper are read from the scope's own git object database, never from
    the working tree or from an operator-supplied path: a gate is "declared" only by a file the repository commits.
    """
    if not closeout.SHA.fullmatch(head):
        raise ProducerError("a gate is resolved only at an exact 40-hex head")
    try:
        return _git(root, "show", f"{head}:{relative}", raw=True)
    except subprocess.CalledProcessError:
        return None


def parse_registry(data: bytes) -> dict[str, dict]:
    try:
        import yaml
    except ImportError as exc:
        raise ProducerError("PyYAML is required to read the gate registry") from exc
    try:
        value = yaml.safe_load(data)
    except yaml.YAMLError as exc:
        raise ProducerError("the gate registry is not valid YAML") from exc
    gates = value.get("gates") if isinstance(value, dict) else None
    if not isinstance(gates, dict):
        raise ProducerError("the gate registry has no gates mapping")
    return gates


def load_committed_registry(root: Path, head: str, relative: str) -> dict[str, dict]:
    """A6: the registry is the scope's own committed file at `head`; an operator-supplied file declares nothing."""
    try:
        safe = closeout.safe_path(relative)
    except closeout.Unmeasured:
        safe = None
    data = read_committed_blob(root, head, safe) if safe else None
    if data is None:
        raise Refusal(
            "gates_registry_not_committed",
            "the gate registry must be a repository-relative file committed at the scope head",
        )
    return parse_registry(data)


def resolve_gate(
    registry: dict[str, dict],
    read_blob: Callable[[str], bytes | None],
    gate_id: str | None,
    argv: list[str],
) -> tuple[str, str, str]:
    """A6: only a registry-declared gate (or the verify-scoped wrapper for the exact tree) may be attested.

    `read_blob` returns the committed bytes of a repository-relative path at the attested head.
    """
    command_text = shlex.join(argv) if argv else None
    if gate_id is None and command_text is not None:
        gate_id = next(
            (name for name, row in registry.items() if isinstance(row, dict) and row.get("command") == command_text),
            None,
        )
        if gate_id is None and command_text == VERIFY_SCOPED_WRAPPER:
            gate_id = "verify-scoped"
    if gate_id is None:
        raise Refusal("argv_not_registry_gate", "attest runs only a gate declared in the registry (use --gate ID)")
    if command_text is not None:
        expected = VERIFY_SCOPED_WRAPPER if gate_id == "verify-scoped" else (registry.get(gate_id) or {}).get("command")
        if command_text != expected:
            raise Refusal("argv_not_registry_gate", "the supplied command is not the declared command of that gate")
    if gate_id == "verify-scoped":
        script = read_blob(VERIFY_SCOPED_SCRIPT)
        if script is None:
            raise Refusal("gate_not_declared", "the scope head commits no scripts/verify-scoped.sh")
        return gate_id, VERIFY_SCOPED_WRAPPER, sha256_hex(script)
    row = registry.get(gate_id)
    if not isinstance(row, dict) or not isinstance(row.get("command"), str):
        raise Refusal("gate_not_declared", "the gate is not declared in the registry")
    definition = json_bytes({"command": row["command"], "paths": row.get("paths", [])})
    return gate_id, row["command"], sha256_hex(definition)


def command_problem(command: str, literals: list[str]) -> Refusal | None:
    """The refusal (if any) for a gate command that mutates the repository or would commit unsafe bytes."""
    if any(pattern.search(command) for pattern in MUTATING_COMMANDS):
        return Refusal(
            "command_mutates_repository_or_broker",
            "an attested gate may not stage, commit, push, merge or touch the broker",
        )
    problems = scrub_problems(command.encode(), literals=literals, allowed=[], strict=True)
    if problems:
        return Refusal(
            "committed_bytes_unsafe", f"the gate command would put {', '.join(problems)} in a committed file"
        )
    return None


def child_environment(root: Path) -> dict[str, str]:
    """A5: an allowlisted environment; no token, broker or credential variable reaches test code."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key in CHILD_ENV_ALLOWLIST or key.startswith(CHILD_ENV_PREFIXES)
    }
    env["LIMEN_ROOT"] = str(root)
    env["LIMEN_NOTIFY"] = "0"
    return env


def run_bounded(command: str, root: Path, timeout: int) -> tuple[int, str, int]:
    """Run one shell command in its own process group; kill the group at the deadline; never check=True."""
    with tempfile.TemporaryFile() as sink:
        process = subprocess.Popen(  # noqa: S603 - a registry-declared gate, run through bash -c
            ["bash", "-c", command],
            cwd=root,
            env=child_environment(root),
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        group = process.pid
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(group, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(group, signal.SIGKILL)
                process.wait()
            raise ProducerError(
                "the gate exceeded its deadline; its process group was killed and nothing was attested"
            ) from exc
        finally:
            # Reap stray children: survivors with a cwd in the scope would become census `unknown` processes.
            # macOS answers EPERM (not ESRCH) for a group whose members are all already-exited zombies.
            with contextlib.suppress(ProcessLookupError, PermissionError):
                os.killpg(group, signal.SIGKILL)
        sink.seek(0)
        digest, size = hashlib.sha256(), 0
        for block in iter(lambda: sink.read(1 << 20), b""):
            digest.update(block)
            size += len(block)
    return code, digest.hexdigest(), size


def cmd_attest(args: argparse.Namespace, seams: Seams) -> int:
    ctx = prepare(args.manifest, allow_local_remote=args.allow_local_remote)
    blocking = [gap for gap in ctx.gaps if gap[0] not in {"manifest_mode_too_open"}]
    if blocking or ctx.receipt_root is None or not ctx.evidence_dir_rel:
        raise Refusal(
            blocking[0][0] if blocking else "manifest_unresolved",
            blocking[0][1] if blocking else "the manifest does not resolve a receipt location",
        )
    scope = ctx.scopes.get(args.scope)
    if scope is None or scope.kind != "git" or scope.absent:
        raise Refusal("attest_scope_invalid", "--scope must name a declared, present git scope")
    if not LABEL_RE.fullmatch(args.label):
        raise Refusal("label_invalid", "--label must match [A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
    if args.purpose not in {None, "completion"}:
        raise Refusal("purpose_invalid", "--purpose may only be `completion`")
    if args.timeout < 1 or args.timeout > MAX_TIMEOUT_SECONDS:
        raise Refusal(
            "timeout_invalid",
            f"--timeout must be 1..{MAX_TIMEOUT_SECONDS} seconds (the finite-work verification bound)",
        )
    prefix = ctx.evidence_dir_rel + "/"

    def tree_state() -> tuple[str, bytes, str]:
        status = _git(scope.path, "status", "--porcelain=v1", "-z", "--untracked-files=all", raw=True)
        if scope.id == ctx.receipt_id:
            status = filter_porcelain(status, {p for p in closeout.dirty_paths(status) if p.startswith(prefix)})
        # Every ref (branches, tags, remote-tracking refs, stash): a gate that pushes updates a remote-tracking ref.
        refs = _git(scope.path, "for-each-ref", "--format=%(refname) %(objectname)")
        return _git(scope.path, "rev-parse", "HEAD"), status, refs

    head, status, refs = tree_state()
    if status:
        raise Refusal(
            "tree_dirty_at_start", f"scope {scope.id} has uncommitted changes; attest only an exact clean head"
        )
    # A6: the gate is resolved from the registry COMMITTED at this exact head, never from an operator-supplied file.
    registry_rel = args.gates_registry or DEFAULT_GATES_REGISTRY
    registry = load_committed_registry(scope.path, head, registry_rel)
    gate_id, command, definition_digest = resolve_gate(
        registry, lambda relative: read_committed_blob(scope.path, head, relative), args.gate, list(args.command)
    )
    refusal = command_problem(command, ctx.private_literals)
    if refusal is not None:
        raise refusal
    target = f"{ctx.evidence_dir_rel}/{args.label}.json"
    if os.path.lexists(ctx.receipt_root / target):
        raise Refusal("attestation_exists", f"{target} already exists; attestations are create-only, pick a new label")
    owner_url = args.owner_url or (ctx.manifest.get("owner_url") if args.purpose else None)
    code, output_sha, output_bytes = run_bounded(command, scope.path, args.timeout)
    after_head, after_status, after_refs = tree_state()
    if after_head != head or after_status != status or after_refs != refs:
        raise Refusal(
            "tree_or_head_changed_during_run",
            "the gate changed HEAD, the working tree or a ref; nothing was attested",
        )
    record: dict[str, Any] = {
        "schema": ATTESTATION_SCHEMA,
        "session_id": ctx.session_id,
        "root_id": scope.id,
        "head": head,
        "label": args.label,
        "gate_id": gate_id,
        "gate_registry": registry_rel,
        "gate_definition_sha256": definition_digest,
        "command": command,
        "environment": "scrubbed allowlist",
        "exit_code": code,
        "output_sha256": output_sha,
        "output_bytes": output_bytes,
        "tree_clean_at_start": True,
        "tree_and_head_unchanged_at_end": True,
    }
    if args.purpose:
        record["purpose"] = args.purpose
        record["owner_url"] = owner_url
    data = json_bytes(record)
    problems = scrub_problems(data, literals=ctx.private_literals, allowed=[], strict=True)
    if problems:
        raise Refusal("committed_bytes_unsafe", f"the attestation would contain {', '.join(problems)}")
    create_only(ctx.receipt_root, target, data, create_from=evidence_create_from(ctx))
    payload = {
        "schema": "limen.session_closeout_producer.v1",
        "verb": "attest",
        "status": "attested",
        "gaps": [],
        "write": [target],
        "recorded": {"root_id": scope.id, "gate_id": gate_id, "exit_code": code, "head": head},
    }
    emit(args, payload)
    return 0


# --------------------------------------------------------------------------- entry point


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else None)
    verbs = parser.add_subparsers(dest="verb", required=True)

    def common(sub: argparse.ArgumentParser) -> None:
        sub.add_argument("--manifest", required=True, type=Path)
        sub.add_argument("--json", action="store_true")
        sub.add_argument(
            "--allow-local-remote", action="store_true", help="tests only: permit a non-GitHub origin string"
        )
        sub.add_argument("--canonical-checker", type=Path, help="compare the checker module with this canonical copy")

    plan = verbs.add_parser("plan", help="read-only: every fact and every gap")
    common(plan)
    plan.set_defaults(func=cmd_plan)

    attest = verbs.add_parser("attest", help="run one registry-declared gate and record the result")
    common(attest)
    attest.add_argument("--scope", required=True)
    attest.add_argument("--label", required=True)
    attest.add_argument("--gate")
    attest.add_argument(
        "--gates-registry",
        help="repository-relative path of a gate registry COMMITTED at the scope head "
        f"(default {DEFAULT_GATES_REGISTRY}); an operator-supplied file outside the repository declares no gate",
    )
    attest.add_argument("--purpose")
    attest.add_argument("--owner-url")
    attest.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    attest.add_argument("command", nargs="*")
    attest.set_defaults(func=cmd_attest)

    build = verbs.add_parser("build", help="write evidence and the receipt, then dry-run the real checker")
    common(build)
    build.set_defaults(func=cmd_build)

    check = verbs.add_parser("check", help="run the real checker in-process")
    common(check)
    check.add_argument("--expect-unpublished", action="store_true")
    check.add_argument("--recheck-heads", action="store_true")
    check.set_defaults(func=cmd_check)
    return parser


def main(argv: list[str] | None = None, *, seams: Seams | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args, seams or live_seams()))
    except Refusal as refusal:
        emit(
            args,
            {"verb": args.verb, "status": "refused", "gaps": [{"code": refusal.code, "message": refusal.message}]},
        )
        return 1
    except (ProducerError, closeout.Unmeasured) as exc:
        emit(args, {"verb": args.verb, "status": "unmeasured", "gaps": [], "reason": str(exc)})
        return 2
    except (
        ValueError,
        TypeError,
        KeyError,
        OSError,
        subprocess.SubprocessError,
        RuntimeError,
        AttributeError,  # the checker leaks these as tracebacks with exit 1; the producer never does
        IndexError,
    ) as exc:
        # No stderr, no argv, no path: only the exception class.
        emit(args, {"verb": args.verb, "status": "unmeasured", "gaps": [], "error_type": type(exc).__name__})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
