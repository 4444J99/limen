"""Proof-bearing remote execution lifecycle.

The only production adapter enabled here is the central deterministic GitHub Actions worker. Native
AI-provider lanes retain their existing guarded dispatch paths until they can independently prove an
exact observed SHA, terminal predicate, and exact receipt identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import fcntl
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Callable, Iterable, Iterator, Mapping, Protocol, Sequence
from urllib.parse import quote

from limen import census
from limen.remote_predicate import (
    DIGEST_RE,
    REPO_RE,
    SAFE_ID_RE,
    SCHEMA_VERSION,
    SHA_RE,
    SANDBOX_IMAGE,
    SANDBOX_PROFILE_DIGEST,
    WORKFLOW_PATH_RE,
    PredicateContractError,
    PROVIDER_RE,
    ReceiptTarget,
    assert_public_text,
    canonical_json,
    digest_bytes,
    digest_text,
    packet_digest,
    parse_trusted_predicate,
    validate_content_references,
    validate_control_ref,
    validate_execution_profile,
)


VERIFICATION_CONTEXT_VERSION = "limen.verification-context.v1"
VERIFICATION_ONLY_LABEL = "mode:verification-only"
IMPLEMENTATION_TASK_TYPES = frozenset({"build", "code", "implementation"})


class RemoteExecutionError(RuntimeError):
    pass


class RemoteState(StrEnum):
    SUBMITTED = "submitted"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    ABSENT = "absent"
    UNKNOWN = "unknown"

    @property
    def terminal(self) -> bool:
        return self in {self.SUCCEEDED, self.FAILED, self.BLOCKED, self.ABSENT}


def verification_context_for_task(task: object, tasks_by_id: Mapping[str, object]) -> dict[str, object]:
    """Return a stable verifier-child contract or fail closed.

    GitHub Actions is not a generic coding agent.  A child may use it only after one or more
    implementation parents have terminal, exact GitHub custody.  The dispatch adapter rechecks
    those immutable PR/commit identities remotely before submission; harvest recomputes this
    context so changing the child into a build task can never turn a green check into false done.
    """

    task_id = str(getattr(task, "id", "") or "")
    task_type = str(getattr(task, "type", "") or "").strip().lower()
    task_repo = str(getattr(task, "repo", "") or "")
    labels = [str(label) for label in (getattr(task, "labels", None) or [])]
    dependencies = [str(dep) for dep in (getattr(task, "depends_on", None) or [])]
    if task_type != "verification":
        raise RemoteExecutionError(
            "GitHub Actions lane is verification-only; implementation/build/code tasks are rejected"
        )
    if not REPO_RE.fullmatch(task_repo):
        raise RemoteExecutionError("verification child requires an exact GitHub owner/repo")
    if VERIFICATION_ONLY_LABEL not in labels:
        raise RemoteExecutionError(f"verification child requires label {VERIFICATION_ONLY_LABEL}")
    if not dependencies or len(dependencies) != len(set(dependencies)) or task_id in dependencies:
        raise RemoteExecutionError("verification child requires unique implementation parent dependencies")

    parents: list[dict[str, object]] = []
    for parent_id in dependencies:
        parent = tasks_by_id.get(parent_id)
        if parent is None:
            raise RemoteExecutionError(f"verification parent is absent: {parent_id}")
        parent_type = str(getattr(parent, "type", "") or "").strip().lower()
        parent_status = str(getattr(parent, "status", "") or "").strip().lower()
        parent_repo = str(getattr(parent, "repo", "") or "")
        raw_target = str(getattr(parent, "receipt_target", "") or "")
        if parent_type not in IMPLEMENTATION_TASK_TYPES or parent_status not in {"done", "archived"}:
            raise RemoteExecutionError(f"verification parent lacks terminal implementation custody: {parent_id}")
        try:
            target = ReceiptTarget.parse(raw_target)
        except PredicateContractError as exc:
            raise RemoteExecutionError(f"verification parent receipt is invalid: {parent_id}: {exc}") from exc
        if target.scheme != "github" or target.kind not in {"pull_request", "commit"}:
            raise RemoteExecutionError(f"verification parent needs exact merged PR or commit custody: {parent_id}")
        if parent_repo != target.repo or not REPO_RE.fullmatch(parent_repo):
            raise RemoteExecutionError(f"verification parent repository does not match its receipt: {parent_id}")
        if parent_repo != task_repo:
            raise RemoteExecutionError(
                f"verification parent does not have custody in the child target repo: {parent_id}"
            )

        expected_url = (
            f"https://github.com/{target.repo}/pull/{target.identifier}"
            if target.kind == "pull_request"
            else f"https://github.com/{target.repo}/commit/{target.identifier}"
        )
        custody_event: object | None = None
        for entry in reversed(list(getattr(parent, "dispatch_log", None) or [])):
            status = str(getattr(entry, "status", "") or "").lower()
            text = " ".join(
                str(getattr(entry, name, "") or "") for name in ("session_id", "output", "provider_url")
            ).lower()
            if status not in {"done", "archived"}:
                continue
            if target.kind == "pull_request" and ("merged" not in text or expected_url.lower() not in text):
                continue
            if target.kind == "commit" and target.identifier.lower() not in text:
                continue
            custody_event = {
                "timestamp": str(getattr(entry, "timestamp", "") or ""),
                "agent": str(getattr(entry, "agent", "") or ""),
                "status": status,
                "event_digest": digest_text(text),
            }
            break
        if custody_event is None:
            raise RemoteExecutionError(f"verification parent lacks an exact terminal custody event: {parent_id}")
        parents.append(
            {
                "task_id": parent_id,
                "type": parent_type,
                "repo": parent_repo,
                "receipt_target": raw_target,
                "custody_event": custody_event,
            }
        )
    return {
        "schema_version": VERIFICATION_CONTEXT_VERSION,
        "child_task_id": task_id,
        "child_type": "verification",
        "mode": "verification-only",
        "depends_on": dependencies,
        "implementation_custody": parents,
    }


def _validate_verification_context(value: Mapping[str, object], task_id: str, repo: str) -> None:
    try:
        encoded = canonical_json(dict(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("verification context is not canonical JSON") from exc
    if len(encoded) > 16_384:
        raise ValueError("verification context is too large")
    dependencies = value.get("depends_on")
    custody = value.get("implementation_custody")
    if (
        value.get("schema_version") != VERIFICATION_CONTEXT_VERSION
        or value.get("child_task_id") != task_id
        or value.get("child_type") != "verification"
        or value.get("mode") != "verification-only"
        or not isinstance(dependencies, list)
        or not dependencies
        or any(not isinstance(item, str) or not SAFE_ID_RE.fullmatch(item) for item in dependencies)
        or len(dependencies) != len(set(dependencies))
        or not isinstance(custody, list)
        or len(custody) != len(dependencies)
    ):
        raise ValueError("verification context is malformed")
    for dependency, row in zip(dependencies, custody, strict=True):
        if not isinstance(row, dict):
            raise ValueError("verification context custody row is malformed")
        receipt = str(row.get("receipt_target") or "")
        try:
            target = ReceiptTarget.parse(receipt)
        except PredicateContractError as exc:
            raise ValueError("verification context custody receipt is malformed") from exc
        event = row.get("custody_event")
        if (
            row.get("task_id") != dependency
            or row.get("type") not in IMPLEMENTATION_TASK_TYPES
            or row.get("repo") != repo
            or target.scheme != "github"
            or target.repo != repo
            or target.kind not in {"pull_request", "commit"}
            or not isinstance(event, dict)
            or event.get("status") not in {"done", "archived"}
            or not DIGEST_RE.fullmatch(str(event.get("event_digest") or ""))
        ):
            raise ValueError("verification context lacks exact implementation custody")


@dataclass(frozen=True)
class ContentReference:
    digest: str
    uri: str
    media_type: str = "application/octet-stream"
    redacted: bool = True

    def __post_init__(self) -> None:
        validate_content_references([asdict(self)])


@dataclass(frozen=True)
class RemoteRequest:
    provider: str
    task_id: str
    repo: str
    base_sha: str
    control_repo: str
    control_ref: str
    control_ref_kind: str
    control_sha: str
    workflow_id: int
    workflow_path: str
    verification_context: Mapping[str, object]
    predicate: str
    receipt_target: str
    instruction: str = ""
    inputs: tuple[ContentReference, ...] = ()
    execution_profile: Mapping[str, object] = field(default_factory=dict)
    custody_mode: str = "artifact"
    _verification_context_json: bytes = field(init=False, repr=False, compare=False)
    _execution_profile_json: bytes = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.provider or not SAFE_ID_RE.fullmatch(self.task_id):
            raise ValueError("provider and task_id are required")
        if not PROVIDER_RE.fullmatch(self.provider):
            raise ValueError("provider identity is invalid")
        if (
            not REPO_RE.fullmatch(self.repo)
            or not SHA_RE.fullmatch(self.base_sha)
            or not REPO_RE.fullmatch(self.control_repo)
            or not SHA_RE.fullmatch(self.control_sha)
        ):
            raise ValueError("remote request requires exact target and control repository SHAs")
        try:
            validate_control_ref(self.control_ref, self.control_ref_kind)
        except PredicateContractError as exc:
            raise ValueError(str(exc)) from exc
        if (
            isinstance(self.workflow_id, bool)
            or not isinstance(self.workflow_id, int)
            or self.workflow_id <= 0
            or not WORKFLOW_PATH_RE.fullmatch(self.workflow_path)
        ):
            raise ValueError("remote request workflow identity is invalid")
        _validate_verification_context(self.verification_context, self.task_id, self.repo)
        if not isinstance(self.inputs, tuple) or any(not isinstance(item, ContentReference) for item in self.inputs):
            raise ValueError("remote inputs must be typed content references")
        try:
            parse_trusted_predicate(self.predicate)
            ReceiptTarget.parse(self.receipt_target)
            validate_content_references([asdict(item) for item in self.inputs])
            validate_execution_profile(dict(self.execution_profile))
            assert_public_text(self.instruction, field="instruction")
        except PredicateContractError as exc:
            raise ValueError(str(exc)) from exc
        if self.custody_mode not in {"artifact", "git"}:
            raise ValueError("unsupported custody_mode")
        object.__setattr__(self, "_verification_context_json", canonical_json(dict(self.verification_context)))
        object.__setattr__(self, "_execution_profile_json", canonical_json(dict(self.execution_profile)))

    @property
    def predicate_digest(self) -> str:
        return digest_text(self.predicate.strip())

    @property
    def verification_context_digest(self) -> str:
        return digest_bytes(self._verification_context_json)

    def verification_context_payload(self) -> dict[str, object]:
        payload = json.loads(self._verification_context_json)
        if not isinstance(payload, dict):  # pragma: no cover - canonicalized in __post_init__
            raise ValueError("verification context is not an object")
        return payload

    def execution_profile_payload(self) -> dict[str, object]:
        payload = json.loads(self._execution_profile_json)
        if not isinstance(payload, dict):  # pragma: no cover - canonicalized in __post_init__
            raise ValueError("execution profile is not an object")
        return payload

    @property
    def workflow_event(self) -> str:
        return "workflow_dispatch"

    @property
    def packet_digest(self) -> str:
        return packet_digest(
            provider=self.provider,
            task_id=self.task_id,
            repo=self.repo,
            base_sha=self.base_sha,
            control_repo=self.control_repo,
            control_ref=self.control_ref,
            control_ref_kind=self.control_ref_kind,
            control_sha=self.control_sha,
            workflow_id=self.workflow_id,
            workflow_path=self.workflow_path,
            workflow_event=self.workflow_event,
            verification_context_digest=self.verification_context_digest,
            predicate_digest=self.predicate_digest,
            instruction_digest=digest_text(self.instruction),
            receipt_target=self.receipt_target,
            custody_mode=self.custody_mode,
            inputs=[asdict(item) for item in self.inputs],
            execution_profile=self.execution_profile_payload(),
        )

    def public_manifest(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "task_id": self.task_id,
            "repo": self.repo,
            "base_sha": self.base_sha,
            "control_repo": self.control_repo,
            "control_ref": self.control_ref,
            "control_ref_kind": self.control_ref_kind,
            "control_sha": self.control_sha,
            "workflow_id": self.workflow_id,
            "workflow_path": self.workflow_path,
            "workflow_event": self.workflow_event,
            "verification_context_digest": self.verification_context_digest,
            "predicate_digest": self.predicate_digest,
            "instruction_digest": digest_text(self.instruction),
            "receipt_target": self.receipt_target,
            "custody_mode": self.custody_mode,
            "inputs": [asdict(item) for item in self.inputs],
            "execution_profile_digest": digest_bytes(self._execution_profile_json),
            "packet_digest": self.packet_digest,
        }

    @property
    def request_id(self) -> str:
        """Stable attempt identity persisted before the provider mutation.

        A changed SHA, predicate, target, input, profile, or instruction produces a new attempt;
        retrying the same packet adopts the existing attempt instead of creating another run.
        """

        return self.packet_digest.removeprefix("sha256:")[:32]


@dataclass(frozen=True)
class RemoteRun:
    provider: str
    provider_run_id: str
    url: str
    base_sha: str
    control_repo: str
    control_ref: str
    control_ref_kind: str
    control_sha: str
    workflow_id: int
    workflow_path: str
    workflow_event: str
    verification_context_digest: str
    state: RemoteState
    request_id: str
    observed_at: str
    detail: str = ""

    def __post_init__(self) -> None:
        if not self.provider_run_id or not self.request_id:
            raise ValueError("remote run identity is required")
        if (
            not self.url.startswith("https://")
            or not SHA_RE.fullmatch(self.base_sha)
            or not REPO_RE.fullmatch(self.control_repo)
            or not SHA_RE.fullmatch(self.control_sha)
            or isinstance(self.workflow_id, bool)
            or not isinstance(self.workflow_id, int)
            or self.workflow_id <= 0
            or not WORKFLOW_PATH_RE.fullmatch(self.workflow_path)
            or self.workflow_event != "workflow_dispatch"
            or not DIGEST_RE.fullmatch(self.verification_context_digest)
        ):
            raise ValueError("remote run URL or exact base SHA is invalid")
        try:
            validate_control_ref(self.control_ref, self.control_ref_kind)
        except PredicateContractError as exc:
            raise ValueError(str(exc)) from exc
        try:
            observed = datetime.fromisoformat(self.observed_at)
        except ValueError as exc:
            raise ValueError("remote run observation timestamp is invalid") from exc
        if observed.tzinfo is None:
            raise ValueError("remote run observation timestamp must be timezone-aware")

    @property
    def pending_identity(self) -> bool:
        return self.provider_run_id == f"pending:{self.request_id}"


@dataclass(frozen=True)
class PredicateReceipt:
    command_digest: str
    passed: bool
    exit_code: int
    output_digest: str

    def __post_init__(self) -> None:
        if not DIGEST_RE.fullmatch(self.command_digest) or not DIGEST_RE.fullmatch(self.output_digest):
            raise ValueError("predicate receipt digests are invalid")


@dataclass(frozen=True)
class DurableOutput:
    kind: str
    uri: str
    repo: str
    identifier: str
    path: str = ""
    digest: str | None = None

    def __post_init__(self) -> None:
        if not self.uri.startswith("https://github.com/") or not REPO_RE.fullmatch(self.repo):
            raise ValueError("durable output lacks GitHub custody")
        if self.digest is not None and not DIGEST_RE.fullmatch(self.digest):
            raise ValueError("durable output digest is invalid")

    def identity(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "uri": self.uri,
            "repo": self.repo,
            "identifier": self.identifier,
            "path": self.path,
            "digest": self.digest,
        }


@dataclass(frozen=True)
class RemoteReceipt:
    request: RemoteRequest
    run: RemoteRun
    state: RemoteState
    predicate: PredicateReceipt | None = None
    outputs: tuple[DurableOutput, ...] = ()
    observed_sha: str | None = None
    observed_at: str = field(default_factory=lambda: _now())
    detail: str = ""
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported remote receipt schema")
        if (
            self.run.provider != self.request.provider
            or self.run.base_sha != self.request.base_sha
            or self.run.control_repo != self.request.control_repo
            or self.run.control_ref != self.request.control_ref
            or self.run.control_ref_kind != self.request.control_ref_kind
            or self.run.control_sha != self.request.control_sha
            or self.run.workflow_id != self.request.workflow_id
            or self.run.workflow_path != self.request.workflow_path
            or self.run.workflow_event != self.request.workflow_event
            or self.run.verification_context_digest != self.request.verification_context_digest
            or self.run.request_id != self.request.request_id
        ):
            raise ValueError("receipt provider/request/target/control/workflow identity does not match submission")
        if self.state is not self.run.state:
            raise ValueError("receipt state does not match embedded run state")
        if self.predicate and self.predicate.command_digest != self.request.predicate_digest:
            raise ValueError("predicate receipt does not match requested predicate")

    @property
    def done(self) -> bool:
        if (
            self.state is not RemoteState.SUCCEEDED
            or self.observed_sha != self.request.base_sha
            or self.predicate is None
            or not self.predicate.passed
            or self.predicate.exit_code != 0
        ):
            return False
        target = ReceiptTarget.parse(self.request.receipt_target)
        for output in self.outputs:
            if not target.matches(output.identity()):
                continue
            if target.kind == "artifact":
                if output.uri != self.run.url or output.identifier != self.request.task_id:
                    continue
                if not self.run.provider_run_id.isdigit() or not output.uri.endswith(
                    f"/actions/runs/{self.run.provider_run_id}"
                ):
                    continue
            return True
        return False

    @property
    def terminal(self) -> bool:
        return self.state.terminal

    def as_dict(self) -> dict[str, object]:
        run = asdict(self.run)
        run["state"] = self.run.state.value
        return {
            "schema_version": self.schema_version,
            "request": self.request.public_manifest(),
            "run": run,
            "state": self.state.value,
            "predicate": asdict(self.predicate) if self.predicate else None,
            "outputs": [output.identity() for output in self.outputs],
            "observed_sha": self.observed_sha,
            "observed_at": self.observed_at,
            "detail": self.detail,
            "done": self.done,
        }


class RemoteExecutionAdapter(Protocol):
    provider: str

    def preflight(self, request: RemoteRequest) -> None: ...

    def intent(self, request: RemoteRequest) -> RemoteRun: ...

    def submit(self, request: RemoteRequest) -> RemoteRun: ...

    def probe(self, request: RemoteRequest, run: RemoteRun) -> RemoteRun: ...

    def harvest(self, request: RemoteRequest, run: RemoteRun) -> RemoteReceipt: ...

    def recover(self, request: RemoteRequest, run: RemoteRun) -> RemoteRun: ...


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


CommandRunner = Callable[[Sequence[str], int], CommandResult]


def run_command(argv: Sequence[str], timeout: int = 90) -> CommandResult:
    try:
        result = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return CommandResult(tuple(argv), 127, "", str(exc))
    return CommandResult(tuple(argv), result.returncode, result.stdout or "", result.stderr or "")


def resolve_control_ref(
    repo: str,
    ref: str,
    *,
    kind: str | None = None,
    runner: CommandRunner = run_command,
    gh: str = "gh",
) -> tuple[str, str]:
    """Resolve one exact short branch/tag name to its peeled commit SHA and kind."""

    if not REPO_RE.fullmatch(repo):
        raise RemoteExecutionError("control repository must be owner/name")
    kinds = (kind,) if kind is not None else ("branch", "tag")
    matches: list[tuple[str, Mapping[str, object]]] = []
    for candidate in kinds:
        try:
            validate_control_ref(ref, candidate)
        except PredicateContractError as exc:
            raise RemoteExecutionError(str(exc)) from exc
        namespace = "heads" if candidate == "branch" else "tags"
        result = runner(
            [gh, "api", f"repos/{repo}/git/ref/{namespace}/{quote(ref, safe='')}"],
            30,
        )
        if result.returncode != 0:
            continue
        try:
            row = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise RemoteExecutionError("control ref probe returned invalid JSON") from exc
        expected = f"refs/{namespace}/{ref}"
        obj = row.get("object") if isinstance(row, dict) else None
        if (
            not isinstance(row, dict)
            or row.get("ref") != expected
            or not isinstance(obj, dict)
            or obj.get("type") not in ({"commit"} if candidate == "branch" else {"commit", "tag"})
            or not SHA_RE.fullmatch(str(obj.get("sha") or "").lower())
        ):
            raise RemoteExecutionError("control ref probe returned contradictory identity")
        matches.append((candidate, obj))
    if len(matches) != 1:
        reason = "ambiguous branch/tag name" if matches else "branch/tag not found"
        raise RemoteExecutionError(f"control ref {reason}: {ref}")
    resolved_kind, ref_object = matches[0]
    commit = runner(
        [gh, "api", f"repos/{repo}/commits/{quote(ref, safe='')}", "--jq", ".sha"],
        30,
    )
    _require_success(commit, "control ref commit resolution")
    sha = commit.stdout.strip().lower()
    if not SHA_RE.fullmatch(sha):
        raise RemoteExecutionError("control ref did not resolve to an exact commit SHA")
    if resolved_kind == "branch" and str(ref_object.get("sha") or "").lower() != sha:
        raise RemoteExecutionError("control branch ref and peeled commit SHA disagree")
    if resolved_kind == "branch":
        branch = runner([gh, "api", f"repos/{repo}/branches/{quote(ref, safe='')}"], 30)
        _require_success(branch, "control branch protection probe")
        try:
            branch_row = json.loads(branch.stdout)
        except json.JSONDecodeError as exc:
            raise RemoteExecutionError("control branch protection probe returned invalid JSON") from exc
        commit_row = branch_row.get("commit") if isinstance(branch_row, dict) else None
        if (
            not isinstance(branch_row, dict)
            or branch_row.get("name") != ref
            or branch_row.get("protected") is not True
            or not isinstance(commit_row, dict)
            or str(commit_row.get("sha") or "").lower() != sha
        ):
            raise RemoteExecutionError("control branch is unprotected or does not match its exact commit SHA")
    return resolved_kind, sha


class ReceiptStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def task_root(self, task_id: str) -> Path:
        return self.root / _safe_component(task_id)

    @contextmanager
    def submission_lock(self, task_id: str) -> Iterator[None]:
        task_root = self.task_root(task_id)
        task_root.mkdir(parents=True, exist_ok=True)
        with (task_root / ".submission.lock").open("a+") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def write(self, receipt: RemoteReceipt) -> Path:
        payload = canonical_json(receipt.as_dict())
        digest = hashlib.sha256(payload).hexdigest()
        path = self.task_root(receipt.request.task_id) / f"{digest}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            descriptor, temporary_name = tempfile.mkstemp(prefix=f".{digest}.", dir=path.parent)
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload + b"\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return path

    def latest_for(self, request: RemoteRequest) -> tuple[RemoteReceipt, Path] | None:
        task_root = self.task_root(request.task_id)
        if not task_root.is_dir():
            return None
        candidates = sorted(task_root.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True)
        for path in candidates:
            try:
                payload = json.loads(path.read_bytes())
            except (OSError, json.JSONDecodeError) as exc:
                raise RemoteExecutionError(f"corrupt receipt in active task custody: {path.name}: {exc}") from exc
            if not isinstance(payload, dict):
                raise RemoteExecutionError(f"non-object receipt in active task custody: {path.name}")
            if payload.get("request") != request.public_manifest():
                continue
            receipt = load_receipt(path, request)
            if receipt.run.request_id == request.request_id:
                return receipt, path
        return None

    def manifests_for_task(self, task_id: str) -> list[tuple[dict[str, object], Path]]:
        """Return hash-verified receipt manifests for crash-before-board adoption."""

        task_root = self.task_root(task_id)
        if not task_root.is_dir():
            return []
        rows: list[tuple[dict[str, object], Path]] = []
        for path in sorted(task_root.glob("*.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True):
            try:
                payload = json.loads(path.read_bytes())
            except (OSError, json.JSONDecodeError) as exc:
                raise RemoteExecutionError(f"corrupt receipt in active task custody: {path.name}: {exc}") from exc
            if not isinstance(payload, dict):
                raise RemoteExecutionError(f"non-object receipt in active task custody: {path.name}")
            if path.stem != hashlib.sha256(canonical_json(payload)).hexdigest():
                raise RemoteExecutionError(f"receipt filename/content hash mismatch: {path.name}")
            manifest = payload.get("request")
            if not isinstance(manifest, dict):
                raise RemoteExecutionError(f"receipt request manifest is malformed: {path.name}")
            rows.append((manifest, path))
        return rows


_REMOTE_SUBMISSION_STRING_FIELDS = frozenset(
    {
        "provider",
        "task_id",
        "repo",
        "provider_run_id",
        "provider_url",
        "base_sha",
        "control_repo",
        "control_ref",
        "control_ref_kind",
        "control_sha",
        "workflow_path",
        "workflow_event",
        "verification_context_digest",
        "remote_state",
        "remote_request_id",
        "packet_digest",
        "remote_receipt",
    }
)
_REMOTE_REQUEST_FIELDS = frozenset(
    {
        "provider",
        "task_id",
        "repo",
        "base_sha",
        "control_repo",
        "control_ref",
        "control_ref_kind",
        "control_sha",
        "workflow_id",
        "workflow_path",
        "workflow_event",
        "verification_context_digest",
        "predicate_digest",
        "instruction_digest",
        "receipt_target",
        "custody_mode",
        "inputs",
        "execution_profile_digest",
        "packet_digest",
    }
)
_REMOTE_RUN_FIELDS = frozenset(
    {
        "provider",
        "provider_run_id",
        "url",
        "base_sha",
        "control_repo",
        "control_ref",
        "control_ref_kind",
        "control_sha",
        "workflow_id",
        "workflow_path",
        "workflow_event",
        "verification_context_digest",
        "state",
        "request_id",
        "observed_at",
        "detail",
    }
)
_REMOTE_RECEIPT_FIELDS = frozenset(
    {
        "schema_version",
        "request",
        "run",
        "state",
        "predicate",
        "outputs",
        "observed_sha",
        "observed_at",
        "detail",
        "done",
    }
)


def validate_remote_submission_harvest(
    submission: object,
    *,
    result: object,
    agent: object,
    expected_agent: str | None,
    expected_request_contract: Mapping[str, object],
    task_id: str,
    task_repo: str | None,
    root: Path,
    receipt_root: Path,
) -> dict[str, object]:
    """Authenticate an async result against its complete, hash-addressed remote receipt.

    The detached worker is not board authority.  Its compact result is accepted only when every
    request/run identity agrees with the receipt written synchronously around provider submission.
    """

    if not isinstance(submission, Mapping):
        raise RemoteExecutionError("remote submission metadata is missing")
    metadata = dict(submission)
    missing = (_REMOTE_SUBMISSION_STRING_FIELDS | {"workflow_id"}) - metadata.keys()
    if missing:
        raise RemoteExecutionError(f"remote submission metadata is incomplete: {sorted(missing)}")
    if any(not isinstance(metadata[field], str) or not metadata[field] for field in _REMOTE_SUBMISSION_STRING_FIELDS):
        raise RemoteExecutionError("remote submission metadata contains an empty or non-string identity")
    workflow_id = metadata["workflow_id"]
    if isinstance(workflow_id, bool) or not isinstance(workflow_id, int) or workflow_id <= 0:
        raise RemoteExecutionError("remote submission workflow ID is invalid")
    if not isinstance(result, str) or result != metadata["provider_run_id"]:
        raise RemoteExecutionError("async result run ID does not match remote submission run ID")
    if not isinstance(agent, str) or agent != metadata["provider"]:
        raise RemoteExecutionError("async result agent does not match remote submission provider")
    if expected_agent is not None and agent != expected_agent:
        raise RemoteExecutionError("async result agent does not match reserved remote lane")
    if task_repo is None or metadata["task_id"] != task_id or metadata["repo"] != task_repo:
        raise RemoteExecutionError("remote submission task/repository does not match the authoritative board")

    configured_root = receipt_root.expanduser().resolve()
    task_root = ReceiptStore(configured_root).task_root(task_id)
    if task_root.is_symlink() or not task_root.is_dir():
        raise RemoteExecutionError("remote receipt task custody is absent or symlinked")
    expected_task_root = task_root.resolve(strict=True)
    raw_path = Path(str(metadata["remote_receipt"])).expanduser()
    candidate = raw_path if raw_path.is_absolute() else root / raw_path
    if candidate.is_symlink():
        raise RemoteExecutionError("remote receipt custody file is symlinked")
    try:
        receipt_path = candidate.resolve(strict=True)
        receipt_path.relative_to(expected_task_root)
    except (OSError, ValueError) as exc:
        raise RemoteExecutionError("remote receipt escapes or is absent from configured custody") from exc
    if receipt_path.parent != expected_task_root or not receipt_path.is_file() or receipt_path.suffix != ".json":
        raise RemoteExecutionError("remote receipt custody path is not a JSON file")
    try:
        payload = json.loads(receipt_path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise RemoteExecutionError("remote receipt is unreadable") from exc
    if not isinstance(payload, dict):
        raise RemoteExecutionError("remote receipt is not an object")
    if receipt_path.stem != hashlib.sha256(canonical_json(payload)).hexdigest():
        raise RemoteExecutionError("remote receipt filename/content hash mismatch")
    missing_receipt = _REMOTE_RECEIPT_FIELDS - payload.keys()
    if missing_receipt or payload.get("schema_version") != SCHEMA_VERSION:
        raise RemoteExecutionError("remote receipt schema is incomplete or unsupported")
    request = payload.get("request")
    run = payload.get("run")
    if not isinstance(request, dict) or not isinstance(run, dict):
        raise RemoteExecutionError("remote receipt request/run metadata is malformed")
    if _REMOTE_REQUEST_FIELDS - request.keys() or _REMOTE_RUN_FIELDS - run.keys():
        raise RemoteExecutionError("remote receipt request/run metadata is incomplete")
    required_current_contract_fields = {
        "predicate_digest",
        "instruction_digest",
        "receipt_target",
        "custody_mode",
        "inputs",
        "execution_profile",
        "execution_profile_digest",
        "verification_context_digest",
    }
    current_contract_fields = required_current_contract_fields - {"execution_profile"}
    if required_current_contract_fields - expected_request_contract.keys() or any(
        request[field] != expected_request_contract[field] for field in current_contract_fields
    ):
        raise RemoteExecutionError("remote receipt request no longer matches the current task contract")
    try:
        current_execution_profile = validate_execution_profile(expected_request_contract["execution_profile"])
    except PredicateContractError as exc:
        raise RemoteExecutionError("current remote execution profile is invalid") from exc
    if request["execution_profile_digest"] != digest_bytes(canonical_json(current_execution_profile)):
        raise RemoteExecutionError("remote receipt execution profile digest does not match the current task contract")
    if (
        not isinstance(request.get("inputs"), list)
        or isinstance(request.get("workflow_id"), bool)
        or not isinstance(request.get("workflow_id"), int)
        or isinstance(run.get("workflow_id"), bool)
        or not isinstance(run.get("workflow_id"), int)
        or not isinstance(payload.get("outputs"), list)
        or not isinstance(payload.get("done"), bool)
        or not isinstance(payload.get("observed_at"), str)
        or not isinstance(run.get("observed_at"), str)
    ):
        raise RemoteExecutionError("remote receipt contains malformed complete metadata")

    request_identity = {
        "provider": "provider",
        "task_id": "task_id",
        "repo": "repo",
        "base_sha": "base_sha",
        "control_repo": "control_repo",
        "control_ref": "control_ref",
        "control_ref_kind": "control_ref_kind",
        "control_sha": "control_sha",
        "workflow_id": "workflow_id",
        "workflow_path": "workflow_path",
        "workflow_event": "workflow_event",
        "verification_context_digest": "verification_context_digest",
        "packet_digest": "packet_digest",
    }
    run_identity = {
        "provider": "provider",
        "provider_run_id": "provider_run_id",
        "provider_url": "url",
        "base_sha": "base_sha",
        "control_repo": "control_repo",
        "control_ref": "control_ref",
        "control_ref_kind": "control_ref_kind",
        "control_sha": "control_sha",
        "workflow_id": "workflow_id",
        "workflow_path": "workflow_path",
        "workflow_event": "workflow_event",
        "verification_context_digest": "verification_context_digest",
        "remote_state": "state",
        "remote_request_id": "request_id",
    }
    if any(metadata[source] != request[target] for source, target in request_identity.items()):
        raise RemoteExecutionError("remote submission metadata contradicts its request receipt")
    if any(metadata[source] != run[target] for source, target in run_identity.items()):
        raise RemoteExecutionError("remote submission metadata contradicts its provider run receipt")
    if payload.get("state") != run.get("state") or metadata["remote_state"] != payload.get("state"):
        raise RemoteExecutionError("remote submission and receipt states disagree")
    packet = str(request["packet_digest"])
    try:
        expected_packet = packet_digest(
            provider=str(request["provider"]),
            task_id=str(request["task_id"]),
            repo=str(request["repo"]),
            base_sha=str(request["base_sha"]),
            control_repo=str(request["control_repo"]),
            control_ref=str(request["control_ref"]),
            control_ref_kind=str(request["control_ref_kind"]),
            control_sha=str(request["control_sha"]),
            workflow_id=request["workflow_id"],
            workflow_path=str(request["workflow_path"]),
            workflow_event=str(request["workflow_event"]),
            verification_context_digest=str(request["verification_context_digest"]),
            predicate_digest=str(request["predicate_digest"]),
            instruction_digest=str(request["instruction_digest"]),
            receipt_target=str(request["receipt_target"]),
            custody_mode=str(request["custody_mode"]),
            inputs=validate_content_references(request["inputs"]),
            execution_profile=current_execution_profile,
        )
    except (PredicateContractError, TypeError, ValueError) as exc:
        raise RemoteExecutionError("remote receipt packet manifest is invalid") from exc
    if packet != expected_packet:
        raise RemoteExecutionError("remote receipt packet digest does not bind its request manifest")
    if not DIGEST_RE.fullmatch(packet) or metadata["remote_request_id"] != packet.removeprefix("sha256:")[:32]:
        raise RemoteExecutionError("remote request ID is not derived from the attested packet digest")
    return metadata


def load_receipt(path: Path, request: RemoteRequest) -> RemoteReceipt:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise RemoteExecutionError(f"remote receipt unavailable: {exc}") from exc
    if not isinstance(payload, dict):
        raise RemoteExecutionError("remote receipt is not an object")
    canonical = canonical_json(payload)
    if path.stem != hashlib.sha256(canonical).hexdigest():
        raise RemoteExecutionError("local receipt filename/content hash mismatch")
    manifest = payload.get("request")
    if not isinstance(manifest, dict) or manifest != request.public_manifest():
        raise RemoteExecutionError("stored request manifest does not match live task contract")
    run_row = payload.get("run")
    if not isinstance(run_row, dict):
        raise RemoteExecutionError("stored run is malformed")
    try:
        run = RemoteRun(
            provider=str(run_row["provider"]),
            provider_run_id=str(run_row["provider_run_id"]),
            url=str(run_row["url"]),
            base_sha=str(run_row["base_sha"]),
            control_repo=str(run_row["control_repo"]),
            control_ref=str(run_row["control_ref"]),
            control_ref_kind=str(run_row["control_ref_kind"]),
            control_sha=str(run_row["control_sha"]),
            workflow_id=int(run_row["workflow_id"]),
            workflow_path=str(run_row["workflow_path"]),
            workflow_event=str(run_row["workflow_event"]),
            verification_context_digest=str(run_row["verification_context_digest"]),
            state=RemoteState(str(run_row["state"])),
            request_id=str(run_row["request_id"]),
            observed_at=str(run_row["observed_at"]),
            detail=str(run_row.get("detail") or ""),
        )
        predicate_row = payload.get("predicate")
        predicate = PredicateReceipt(**predicate_row) if isinstance(predicate_row, dict) else None
        output_rows = payload.get("outputs", [])
        if not isinstance(output_rows, list) or any(not isinstance(item, dict) for item in output_rows):
            raise RemoteExecutionError("stored receipt outputs are malformed")
        outputs = tuple(DurableOutput(**item) for item in output_rows)
        receipt = RemoteReceipt(
            request=request,
            run=run,
            state=RemoteState(str(payload["state"])),
            predicate=predicate,
            outputs=outputs,
            observed_sha=str(payload["observed_sha"]) if payload.get("observed_sha") else None,
            observed_at=str(payload.get("observed_at") or _now()),
            detail=str(payload.get("detail") or ""),
            schema_version=str(payload.get("schema_version") or ""),
        )
        if receipt.as_dict() != payload:
            raise RemoteExecutionError("stored receipt contains non-canonical or inconsistent fields")
        return receipt
    except (KeyError, TypeError, ValueError) as exc:
        raise RemoteExecutionError(f"stored receipt validation failed: {exc}") from exc


class RemoteLifecycle:
    def __init__(self, adapter: RemoteExecutionAdapter, store: ReceiptStore) -> None:
        self.adapter = adapter
        self.store = store

    def submit(self, request: RemoteRequest) -> tuple[RemoteRun, Path]:
        with self.store.submission_lock(request.task_id):
            self.adapter.preflight(request)
            existing = self.store.latest_for(request)
            if existing is not None:
                previous, _path = existing
                if previous.terminal:
                    if previous.done:
                        return previous.run, self.store.write(previous)
                    raise RemoteExecutionError(
                        "exact remote attempt is already terminal without completion; a changed packet is required"
                    )
                recovered = self.adapter.recover(request, previous.run)
                self._check_transition(request, previous.run, recovered)
                if _same_run_observation(previous.run, recovered):
                    return previous.run, _path
                receipt = RemoteReceipt(
                    request,
                    recovered,
                    recovered.state,
                    observed_at=recovered.observed_at,
                    detail=recovered.detail,
                )
                return recovered, self.store.write(receipt)

            intent = self.adapter.intent(request)
            self._check_identity(request, intent)
            self.store.write(
                RemoteReceipt(
                    request,
                    intent,
                    intent.state,
                    observed_at=intent.observed_at,
                    detail="submission intent persisted before provider mutation",
                )
            )
            run = self.adapter.submit(request)
            self._check_transition(request, intent, run)
            receipt = RemoteReceipt(
                request,
                run,
                run.state,
                observed_at=run.observed_at,
                detail="submission observed; not completion",
            )
            return run, self.store.write(receipt)

    def probe(self, request: RemoteRequest, run: RemoteRun) -> tuple[RemoteRun, Path]:
        observed = self.adapter.probe(request, run)
        self._check_transition(request, run, observed)
        if _same_run_observation(run, observed):
            observed = run
        receipt = RemoteReceipt(
            request,
            observed,
            observed.state,
            observed_at=observed.observed_at,
            detail=observed.detail,
        )
        return observed, self.store.write(receipt)

    def harvest(self, request: RemoteRequest, run: RemoteRun) -> tuple[RemoteReceipt, Path]:
        receipt = self.adapter.harvest(request, run)
        self._check_transition(request, run, receipt.run)
        return receipt, self.store.write(receipt)

    def recover(self, request: RemoteRequest, run: RemoteRun) -> tuple[RemoteRun, Path]:
        recovered = self.adapter.recover(request, run)
        self._check_transition(request, run, recovered)
        if _same_run_observation(run, recovered):
            recovered = run
        receipt = RemoteReceipt(
            request,
            recovered,
            recovered.state,
            observed_at=recovered.observed_at,
            detail=recovered.detail,
        )
        return recovered, self.store.write(receipt)

    @staticmethod
    def _check_identity(request: RemoteRequest, run: RemoteRun) -> None:
        if (
            run.provider != request.provider
            or run.base_sha != request.base_sha
            or run.control_repo != request.control_repo
            or run.control_ref != request.control_ref
            or run.control_ref_kind != request.control_ref_kind
            or run.control_sha != request.control_sha
            or run.workflow_id != request.workflow_id
            or run.workflow_path != request.workflow_path
            or run.workflow_event != request.workflow_event
            or run.verification_context_digest != request.verification_context_digest
            or run.request_id != request.request_id
        ):
            raise RemoteExecutionError(
                "adapter changed provider, request, target SHA, control SHA, or workflow identity"
            )

    @classmethod
    def _check_transition(cls, request: RemoteRequest, before: RemoteRun, after: RemoteRun) -> None:
        cls._check_identity(request, after)
        if before.pending_identity:
            if not (after.pending_identity or after.provider_run_id.isdigit()):
                raise RemoteExecutionError("adapter replaced pending identity with an invalid run ID")
        elif after.provider_run_id != before.provider_run_id or after.url != before.url:
            raise RemoteExecutionError("adapter changed provider run identity or URL")


class GitHubWorkflowAdapter:
    def __init__(
        self,
        *,
        provider: str,
        control_repo: str,
        control_sha: str,
        control_ref: str,
        control_ref_kind: str,
        workflow_id: int,
        workflow_path: str,
        runner: CommandRunner = run_command,
        gh_binary: str = "gh",
    ) -> None:
        if (
            not PROVIDER_RE.fullmatch(provider)
            or not REPO_RE.fullmatch(control_repo)
            or not SHA_RE.fullmatch(control_sha)
            or isinstance(workflow_id, bool)
            or not isinstance(workflow_id, int)
            or workflow_id <= 0
            or not WORKFLOW_PATH_RE.fullmatch(workflow_path)
        ):
            raise ValueError("GitHub workflow adapter requires exact control repo/SHA/workflow identity")
        try:
            validate_control_ref(control_ref, control_ref_kind)
        except PredicateContractError as exc:
            raise ValueError(str(exc)) from exc
        self.provider = provider
        self.control_repo = control_repo
        self.control_sha = control_sha
        self.control_ref = control_ref
        self.control_ref_kind = control_ref_kind
        self.workflow_id = workflow_id
        self.workflow_path = workflow_path
        self.runner = runner
        self.gh_binary = gh_binary

    def _validate_request(self, request: RemoteRequest, *, submitting: bool) -> None:
        target = ReceiptTarget.parse(request.receipt_target)
        expected = ReceiptTarget("artifact", self.control_repo, "artifact", request.task_id)
        if (
            request.provider != self.provider
            or request.control_repo != self.control_repo
            or request.control_ref != self.control_ref
            or request.control_ref_kind != self.control_ref_kind
            or request.workflow_id != self.workflow_id
            or request.workflow_path != self.workflow_path
            or request.custody_mode != "artifact"
            or target != expected
        ):
            raise RemoteExecutionError(
                f"central workflow requires artifact:{self.control_repo}:task:{request.task_id} custody"
            )
        if submitting and request.control_sha != self.control_sha:
            raise RemoteExecutionError("control repository advanced before submission; rebuild the exact packet")

    def _verify_implementation_custody(self, request: RemoteRequest) -> None:
        rows = request.verification_context_payload().get("implementation_custody")
        if not isinstance(rows, list):
            raise RemoteExecutionError("verification context omitted implementation custody")
        for row in rows:
            if not isinstance(row, dict):
                raise RemoteExecutionError("verification context parent is malformed")
            target = ReceiptTarget.parse(str(row.get("receipt_target") or ""))
            if row.get("repo") != request.repo or target.repo != request.repo:
                raise RemoteExecutionError("implementation parent custody does not match the verification target")
            if target.kind == "pull_request":
                result = self.runner(
                    [
                        self.gh_binary,
                        "api",
                        f"repos/{target.repo}/pulls/{target.identifier}",
                        "--jq",
                        ".merged_at",
                    ],
                    30,
                )
                _require_success(result, f"implementation parent PR {target.repo}#{target.identifier} probe")
                if result.stdout.strip().lower() in {"", "null"}:
                    raise RemoteExecutionError(
                        f"implementation parent PR is not merged: {target.repo}#{target.identifier}"
                    )
            elif target.kind == "commit":
                result = self.runner(
                    [
                        self.gh_binary,
                        "api",
                        f"repos/{target.repo}/commits/{target.identifier}",
                        "--jq",
                        ".sha",
                    ],
                    30,
                )
                _require_success(result, f"implementation parent commit {target.repo}@{target.identifier} probe")
                if result.stdout.strip().lower() != target.identifier:
                    raise RemoteExecutionError("implementation parent exact commit custody is unavailable")
            else:  # pragma: no cover - request construction validates the typed context first
                raise RemoteExecutionError("implementation parent custody is not an exact merged PR or commit")

    def preflight(self, request: RemoteRequest) -> None:
        self._validate_request(request, submitting=True)
        resolved_kind, resolved_sha = resolve_control_ref(
            self.control_repo,
            request.control_ref,
            runner=self.runner,
            gh=self.gh_binary,
        )
        if resolved_kind != request.control_ref_kind or resolved_sha != request.control_sha:
            raise RemoteExecutionError("control repository advanced before workflow mutation")
        workflow = self.runner(
            [self.gh_binary, "api", f"repos/{self.control_repo}/actions/workflows/{request.workflow_id}"],
            30,
        )
        _require_success(workflow, "control workflow identity probe")
        try:
            workflow_row = json.loads(workflow.stdout)
        except json.JSONDecodeError as exc:
            raise RemoteExecutionError("control workflow identity returned invalid JSON") from exc
        if (
            not isinstance(workflow_row, dict)
            or workflow_row.get("id") != request.workflow_id
            or workflow_row.get("path") != request.workflow_path
            or workflow_row.get("state") != "active"
        ):
            raise RemoteExecutionError("control workflow identity changed before submission")
        visibility = self.runner(
            [self.gh_binary, "api", f"repos/{request.repo}", "--jq", ".private"],
            30,
        )
        _require_success(visibility, "target visibility probe")
        value = visibility.stdout.strip().lower()
        if value != "false":
            if value == "true":
                raise RemoteExecutionError(
                    "private target blocked: org Actions allowance/budget and private runner capacity are unavailable"
                )
            raise RemoteExecutionError("target visibility probe returned an invalid value")
        self._verify_implementation_custody(request)

    def intent(self, request: RemoteRequest) -> RemoteRun:
        self._validate_request(request, submitting=True)
        return RemoteRun(
            provider=request.provider,
            provider_run_id=f"pending:{request.request_id}",
            url=f"https://github.com/{self.control_repo}/actions/workflows/{self.workflow_id}",
            base_sha=request.base_sha,
            control_repo=request.control_repo,
            control_ref=request.control_ref,
            control_ref_kind=request.control_ref_kind,
            control_sha=request.control_sha,
            workflow_id=request.workflow_id,
            workflow_path=request.workflow_path,
            workflow_event=request.workflow_event,
            verification_context_digest=request.verification_context_digest,
            state=RemoteState.SUBMITTED,
            request_id=request.request_id,
            observed_at=_now(),
            detail="durable submission intent; provider mutation not yet confirmed",
        )

    def submit(self, request: RemoteRequest) -> RemoteRun:
        self.preflight(request)
        request_id = request.request_id
        existing = self._find_run(request, request_id)
        if existing is not None:
            return _run_from_actions(request, request_id, existing, self.control_repo)
        # Narrow the discovery-to-mutation race. GitHub requires a branch/tag for --ref, while the
        # independently resolved exact SHA remains authoritative and must still match after I/O.
        self.preflight(request)
        inputs_json = json.dumps([asdict(item) for item in request.inputs], sort_keys=True, separators=(",", ":"))
        profile_json = request._execution_profile_json.decode()
        result = self.runner(
            [
                self.gh_binary,
                "workflow",
                "run",
                str(request.workflow_id),
                "--repo",
                self.control_repo,
                "--ref",
                request.control_ref,
                "-f",
                f"request_id={request_id}",
                "-f",
                f"provider={request.provider}",
                "-f",
                f"task_id={request.task_id}",
                "-f",
                f"target_repo={request.repo}",
                "-f",
                f"base_sha={request.base_sha}",
                "-f",
                f"control_repo={request.control_repo}",
                "-f",
                f"control_ref={request.control_ref}",
                "-f",
                f"control_ref_kind={request.control_ref_kind}",
                "-f",
                f"control_sha={request.control_sha}",
                "-f",
                f"workflow_id={request.workflow_id}",
                "-f",
                f"workflow_path={request.workflow_path}",
                "-f",
                f"verification_context_digest={request.verification_context_digest}",
                "-f",
                f"predicate={request.predicate}",
                "-f",
                f"instruction_digest={digest_text(request.instruction)}",
                "-f",
                f"receipt_target={request.receipt_target}",
                "-f",
                f"custody_mode={request.custody_mode}",
                "-f",
                f"inputs_json={inputs_json}",
                "-f",
                f"execution_profile_json={profile_json}",
                "-f",
                f"packet_digest={request.packet_digest}",
            ],
            90,
        )
        _require_success(result, "workflow submission")
        try:
            resolved = self._find_run(request, request_id)
        except RemoteExecutionError:
            resolved = None
        if resolved is not None:
            return _run_from_actions(request, request_id, resolved, self.control_repo)
        return replace_run(
            self.intent(request),
            RemoteState.SUBMITTED,
            "workflow accepted; durable request ID awaiting provider run materialization",
        )

    def _find_run(self, request: RemoteRequest, request_id: str) -> dict[str, object] | None:
        result = self.runner(
            [
                self.gh_binary,
                "api",
                "--method",
                "GET",
                "--paginate",
                "--slurp",
                f"repos/{self.control_repo}/actions/workflows/{request.workflow_id}/runs",
                "-f",
                "event=workflow_dispatch",
                "-f",
                "per_page=100",
            ],
            120,
        )
        _require_success(result, "workflow run discovery")
        try:
            pages = json.loads(result.stdout or "[]")
        except json.JSONDecodeError as exc:
            raise RemoteExecutionError("workflow run discovery returned invalid JSON") from exc
        if isinstance(pages, dict):
            pages = [pages]
        if not isinstance(pages, list):
            raise RemoteExecutionError("workflow run discovery returned an invalid catalog")
        matches: list[dict[str, object]] = []
        for page in pages:
            if not isinstance(page, dict):
                continue
            runs = page.get("workflow_runs")
            if not isinstance(runs, list):
                continue
            for row in runs:
                if not isinstance(row, dict):
                    continue
                title = str(row.get("display_title") or row.get("name") or "")
                if title != f"remote:{request_id}:{request.task_id}":
                    continue
                try:
                    _validate_actions_row_identity(request, request_id, row)
                except RemoteExecutionError as exc:
                    raise RemoteExecutionError(
                        "workflow run request identity collision with contradictory control metadata"
                    ) from exc
                matches.append(row)
        if len(matches) > 1:
            raise RemoteExecutionError("multiple workflow runs share one supposedly idempotent request ID")
        return matches[0] if matches else None

    def probe(self, request: RemoteRequest, run: RemoteRun) -> RemoteRun:
        if run.pending_identity:
            resolved = self._find_run(request, run.request_id)
            return (
                _run_from_actions(request, run.request_id, resolved, self.control_repo)
                if resolved
                else replace_run(
                    run, RemoteState.SUBMITTED, "provider run not materialized yet; request remains recoverable"
                )
            )
        result = self.runner(
            [
                self.gh_binary,
                "api",
                f"repos/{request.control_repo}/actions/runs/{run.provider_run_id}",
            ],
            60,
        )
        if result.returncode != 0:
            return replace_run(run, RemoteState.UNKNOWN, _short(result.stderr or result.stdout))
        try:
            row = json.loads(result.stdout)
        except json.JSONDecodeError:
            return replace_run(run, RemoteState.UNKNOWN, "provider status JSON invalid")
        if not isinstance(row, dict):
            return replace_run(run, RemoteState.UNKNOWN, "provider status is not an object")
        return _run_from_actions(request, run.request_id, row, self.control_repo)

    def harvest(self, request: RemoteRequest, run: RemoteRun) -> RemoteReceipt:
        observed = self.probe(request, run)
        if observed.state is RemoteState.FAILED:
            return RemoteReceipt(request, observed, RemoteState.FAILED, detail="workflow failed; no artifact required")
        if observed.state is not RemoteState.SUCCEEDED:
            return RemoteReceipt(request, observed, observed.state, detail=observed.detail)
        with tempfile.TemporaryDirectory(prefix="limen-remote-receipt-") as directory:
            result = self.runner(
                [
                    self.gh_binary,
                    "run",
                    "download",
                    observed.provider_run_id,
                    "--repo",
                    self.control_repo,
                    "--name",
                    "remote-execution-receipt",
                    "--dir",
                    directory,
                ],
                120,
            )
            if result.returncode != 0:
                blocked = replace_run(observed, RemoteState.BLOCKED, "successful workflow omitted terminal artifact")
                return RemoteReceipt(request, blocked, RemoteState.BLOCKED, detail=blocked.detail)
            receipt_path = Path(directory) / "receipt.json"
            if not receipt_path.exists():
                blocked = replace_run(observed, RemoteState.BLOCKED, "workflow artifact omitted receipt.json")
                return RemoteReceipt(request, blocked, RemoteState.BLOCKED, detail=blocked.detail)
            try:
                payload = json.loads(receipt_path.read_text())
            except (OSError, json.JSONDecodeError) as exc:
                raise RemoteExecutionError(f"workflow receipt is unreadable: {exc}") from exc
        receipt = _receipt_from_workflow_payload(payload, request, observed, self.control_repo)
        if receipt.done:
            return receipt
        blocked = replace_run(observed, RemoteState.BLOCKED, "terminal receipt lacks exact target custody")
        return RemoteReceipt(request, blocked, RemoteState.BLOCKED, detail=blocked.detail)

    def recover(self, request: RemoteRequest, run: RemoteRun) -> RemoteRun:
        observed = self.probe(request, run)
        if observed.state is RemoteState.UNKNOWN:
            return replace_run(observed, RemoteState.UNKNOWN, "provider query uncertain; stable request ID retained")
        return observed


@dataclass(frozen=True)
class RemoteCapability:
    provider: str
    reachable: bool
    driver: str
    detail: str


def discover_adapters(
    *,
    environ: Mapping[str, str] | None = None,
    runner: CommandRunner = run_command,
    vendors: Iterable[census.Vendor] | None = None,
    binary_finder: Callable[[str], str | None] = shutil.which,
) -> tuple[dict[str, RemoteExecutionAdapter], list[RemoteCapability]]:
    """Discover only live, authenticated central-workflow adapters.

    ``vendors=[]`` deliberately means an empty live catalog; it never resurrects the static census.
    """

    env = dict(os.environ if environ is None else environ)
    catalog = tuple(census.VENDORS if vendors is None else vendors)
    adapters: dict[str, RemoteExecutionAdapter] = {}
    capabilities: list[RemoteCapability] = []
    for vendor in catalog:
        if vendor.kind != "github-actions":
            continue
        provider = vendor.name
        gh = env.get("LIMEN_GITHUB_ACTIONS_BIN", vendor.binary)
        repo = env.get("LIMEN_GITHUB_ACTIONS_REPO", "organvm/limen")
        workflow = env.get("LIMEN_GITHUB_ACTIONS_WORKFLOW", "limen-agent.yml")
        configured_ref = env.get("LIMEN_GITHUB_ACTIONS_CONTROL_REF")
        if binary_finder(gh) is None:
            capabilities.append(RemoteCapability(provider, False, "github-workflow", f"{gh} not found"))
            continue
        auth = runner([gh, "auth", "status", "--hostname", "github.com"], 30)
        if auth.returncode != 0:
            capabilities.append(RemoteCapability(provider, False, "github-workflow", "GitHub auth unavailable"))
            continue
        if configured_ref is None:
            default_branch = runner([gh, "api", f"repos/{repo}", "--jq", ".default_branch"], 30)
            control_ref = default_branch.stdout.strip() if default_branch.returncode == 0 else ""
            expected_kind: str | None = "branch"
        else:
            control_ref = configured_ref
            expected_kind = None
        try:
            control_ref_kind, control_sha = resolve_control_ref(
                repo,
                control_ref,
                runner=runner,
                gh=gh,
            )
            if expected_kind is not None and control_ref_kind != expected_kind:
                raise RemoteExecutionError("remote default ref did not resolve as a branch")
        except RemoteExecutionError as exc:
            capabilities.append(RemoteCapability(provider, False, "github-workflow", str(exc)))
            continue
        workflow_probe = runner(
            [gh, "api", f"repos/{repo}/actions/workflows/{quote(workflow, safe='')}"],
            30,
        )
        if workflow_probe.returncode != 0:
            capabilities.append(RemoteCapability(provider, False, "github-workflow", "workflow unavailable"))
            continue
        try:
            workflow_row = json.loads(workflow_probe.stdout)
            workflow_id = workflow_row.get("id") if isinstance(workflow_row, dict) else None
            workflow_path = workflow_row.get("path") if isinstance(workflow_row, dict) else None
            workflow_state = workflow_row.get("state") if isinstance(workflow_row, dict) else None
        except json.JSONDecodeError:
            workflow_id = workflow_path = workflow_state = None
        if (
            isinstance(workflow_id, bool)
            or not isinstance(workflow_id, int)
            or workflow_id <= 0
            or not isinstance(workflow_path, str)
            or not WORKFLOW_PATH_RE.fullmatch(workflow_path)
            or workflow_state != "active"
        ):
            capabilities.append(RemoteCapability(provider, False, "github-workflow", "workflow identity invalid"))
            continue
        adapter = GitHubWorkflowAdapter(
            provider=provider,
            control_repo=repo,
            control_sha=control_sha,
            control_ref=control_ref,
            control_ref_kind=control_ref_kind,
            workflow_id=workflow_id,
            workflow_path=workflow_path,
            runner=runner,
            gh_binary=gh,
        )
        adapters[provider] = adapter
        capabilities.append(
            RemoteCapability(
                provider,
                True,
                "github-workflow",
                f"live auth and exact {repo}:{control_ref_kind}:{control_ref}@{adapter.control_sha} "
                f"workflow {workflow_id} verified",
            )
        )
    return adapters, capabilities


def resolve_pushed_sha(repo: str, *, ref: str = "HEAD", runner: CommandRunner = run_command, gh: str = "gh") -> str:
    if not REPO_RE.fullmatch(repo):
        raise RemoteExecutionError("remote repo must be owner/name")
    result = runner([gh, "api", f"repos/{repo}/commits/{quote(ref, safe='')}", "--jq", ".sha"], 30)
    _require_success(result, "remote SHA resolution")
    sha = result.stdout.strip().lower()
    if not SHA_RE.fullmatch(sha):
        raise RemoteExecutionError("remote owner did not return an exact pushed SHA")
    return sha


def remote_request_from_task(
    task: object,
    provider: str,
    *,
    base_sha: str,
    control_repo: str,
    control_ref: str,
    control_ref_kind: str,
    control_sha: str,
    workflow_id: int,
    workflow_path: str,
    verification_context: Mapping[str, object],
    instruction: str = "",
    repo: str | None = None,
    execution_profile: Mapping[str, object] | None = None,
) -> RemoteRequest:
    return RemoteRequest(
        provider=provider,
        task_id=str(getattr(task, "id", "") or ""),
        repo=repo or str(getattr(task, "repo", "") or ""),
        base_sha=base_sha,
        control_repo=control_repo,
        control_ref=control_ref,
        control_ref_kind=control_ref_kind,
        control_sha=control_sha,
        workflow_id=workflow_id,
        workflow_path=workflow_path,
        verification_context=verification_context,
        predicate=str(getattr(task, "predicate", "") or ""),
        receipt_target=str(getattr(task, "receipt_target", "") or ""),
        instruction=instruction,
        execution_profile=execution_profile or {},
        custody_mode="artifact",
    )


def _receipt_from_workflow_payload(
    payload: object,
    request: RemoteRequest,
    run: RemoteRun,
    control_repo: str,
) -> RemoteReceipt:
    if not isinstance(payload, dict):
        raise RemoteExecutionError("workflow receipt is not an object")
    receipt_digest = str(payload.get("receipt_digest") or "")
    unsigned = dict(payload)
    unsigned.pop("receipt_digest", None)
    if receipt_digest != digest_bytes(canonical_json(unsigned)):
        raise RemoteExecutionError("workflow receipt digest mismatch")
    expected: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "request_id": run.request_id,
        "provider": request.provider,
        "task_id": request.task_id,
        "repo": request.repo,
        "base_sha": request.base_sha,
        "observed_sha": request.base_sha,
        "control_repo": request.control_repo,
        "control_ref": request.control_ref,
        "control_ref_kind": request.control_ref_kind,
        "control_sha": request.control_sha,
        "observed_control_sha": request.control_sha,
        "observed_control_ref": request.control_ref,
        "observed_control_ref_kind": request.control_ref_kind,
        "workflow_id": request.workflow_id,
        "workflow_path": request.workflow_path,
        "observed_workflow_path": request.workflow_path,
        "workflow_event": request.workflow_event,
        "observed_workflow_event": request.workflow_event,
        "observed_workflow_sha": request.control_sha,
        "verification_context_digest": request.verification_context_digest,
        "predicate_digest": request.predicate_digest,
        "instruction_digest": digest_text(request.instruction),
        "packet_digest": request.packet_digest,
        "receipt_target": request.receipt_target,
        "custody_mode": request.custody_mode,
        "inputs_digest": digest_bytes(canonical_json([asdict(item) for item in request.inputs])),
        "execution_profile_digest": digest_bytes(request._execution_profile_json),
        "delta_safe": True,
        "delta_digest": digest_bytes(b""),
        "delta_bytes": 0,
        "workspace_clean": True,
        "sandbox_image": SANDBOX_IMAGE,
        "sandbox_profile_digest": SANDBOX_PROFILE_DIGEST,
        "sandbox_attestation_digest": digest_text("limen-sandbox-boundary-v1\n"),
    }
    for key, value in expected.items():
        if payload.get(key) != value:
            raise RemoteExecutionError(f"workflow receipt mismatch for {key}")
    try:
        exit_code = int(str(payload["predicate_exit_code"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise RemoteExecutionError("workflow receipt lacks predicate exit code") from exc
    output_digest = str(payload.get("predicate_output_digest") or "")
    if not DIGEST_RE.fullmatch(output_digest):
        raise RemoteExecutionError("workflow receipt lacks predicate output digest")
    if exit_code != 0:
        raise RemoteExecutionError("successful workflow carried a failing predicate receipt")
    raw_outputs = payload.get("outputs")
    if not isinstance(raw_outputs, list):
        raise RemoteExecutionError("workflow receipt outputs are malformed")
    try:
        outputs = tuple(DurableOutput(**item) for item in raw_outputs if isinstance(item, dict))
    except (TypeError, ValueError) as exc:
        raise RemoteExecutionError(f"workflow output invalid: {exc}") from exc
    if any(output.repo != control_repo for output in outputs):
        raise RemoteExecutionError("workflow output escaped the control repository")
    target = ReceiptTarget.parse(request.receipt_target)
    if (
        len(outputs) != 1
        or not target.matches(outputs[0].identity())
        or outputs[0].uri != run.url
        or outputs[0].identifier != request.task_id
        or outputs[0].digest is not None
    ):
        raise RemoteExecutionError("workflow output does not bind the exact current Actions run")
    state = RemoteState.SUCCEEDED
    observed = replace_run(run, state, "terminal attested workflow receipt")
    return RemoteReceipt(
        request=request,
        run=observed,
        state=state,
        predicate=PredicateReceipt(request.predicate_digest, exit_code == 0, exit_code, output_digest),
        outputs=outputs,
        observed_sha=request.base_sha,
        detail="terminal attested workflow receipt",
    )


def _validate_actions_row_identity(
    request: RemoteRequest,
    request_id: str,
    row: Mapping[str, object],
) -> None:
    run_id = str(row.get("id") or "")
    url = str(row.get("html_url") or "")
    title = str(row.get("display_title") or "")
    repository = row.get("repository")
    repository_name = str(repository.get("full_name") or "") if isinstance(repository, Mapping) else ""
    head_branch = str(row.get("head_branch") or "")
    raw_workflow_id = row.get("workflow_id")
    try:
        workflow_id = (
            int(raw_workflow_id)
            if isinstance(raw_workflow_id, str | int) and not isinstance(raw_workflow_id, bool)
            else 0
        )
    except ValueError:
        workflow_id = 0
    expected_url = f"https://github.com/{request.control_repo}/actions/runs/{run_id}"
    if (
        not run_id.isdigit()
        or url.rstrip("/") != expected_url
        or title != f"remote:{request_id}:{request.task_id}"
        or str(row.get("head_sha") or "").lower() != request.control_sha
        or head_branch != request.control_ref
        or str(row.get("event") or "") != request.workflow_event
        or repository_name != request.control_repo
        or workflow_id != request.workflow_id
        or str(row.get("path") or "") != request.workflow_path
    ):
        raise RemoteExecutionError(
            "Actions row does not bind exact request, control ref/SHA, event, repository, workflow ID/path, and run"
        )


def _run_from_actions(
    request: RemoteRequest,
    request_id: str,
    row: Mapping[str, object],
    control_repo: str,
) -> RemoteRun:
    if control_repo != request.control_repo:
        raise RemoteExecutionError("adapter control repository does not match request")
    _validate_actions_row_identity(request, request_id, row)
    run_id = str(row["id"])
    url = str(row["html_url"])
    status = str(row.get("status") or "").lower()
    conclusion = str(row.get("conclusion") or "").lower()
    if status == "completed":
        state = RemoteState.SUCCEEDED if conclusion == "success" else RemoteState.FAILED
    elif status in {"queued", "waiting", "pending", "requested"}:
        state = RemoteState.QUEUED
    else:
        state = RemoteState.RUNNING
    return RemoteRun(
        provider=request.provider,
        provider_run_id=run_id,
        url=url,
        base_sha=request.base_sha,
        control_repo=request.control_repo,
        control_ref=request.control_ref,
        control_ref_kind=request.control_ref_kind,
        control_sha=request.control_sha,
        workflow_id=request.workflow_id,
        workflow_path=request.workflow_path,
        workflow_event=request.workflow_event,
        verification_context_digest=request.verification_context_digest,
        state=state,
        request_id=request_id,
        observed_at=_now(),
        detail=conclusion or status,
    )


def replace_run(run: RemoteRun, state: RemoteState, detail: str) -> RemoteRun:
    return RemoteRun(
        provider=run.provider,
        provider_run_id=run.provider_run_id,
        url=run.url,
        base_sha=run.base_sha,
        control_repo=run.control_repo,
        control_ref=run.control_ref,
        control_ref_kind=run.control_ref_kind,
        control_sha=run.control_sha,
        workflow_id=run.workflow_id,
        workflow_path=run.workflow_path,
        workflow_event=run.workflow_event,
        verification_context_digest=run.verification_context_digest,
        state=state,
        request_id=run.request_id,
        observed_at=_now(),
        detail=detail,
    )


def _same_run_observation(left: RemoteRun, right: RemoteRun) -> bool:
    return (
        left.provider == right.provider
        and left.provider_run_id == right.provider_run_id
        and left.url == right.url
        and left.base_sha == right.base_sha
        and left.control_repo == right.control_repo
        and left.control_ref == right.control_ref
        and left.control_ref_kind == right.control_ref_kind
        and left.control_sha == right.control_sha
        and left.workflow_id == right.workflow_id
        and left.workflow_path == right.workflow_path
        and left.workflow_event == right.workflow_event
        and left.verification_context_digest == right.verification_context_digest
        and left.state is right.state
        and left.request_id == right.request_id
        and left.detail == right.detail
    )


def _require_success(result: CommandResult, action: str) -> None:
    if result.returncode:
        raise RemoteExecutionError(f"{action} failed: {_short(result.stderr or result.stdout)}")


def _short(value: str, limit: int = 240) -> str:
    return " ".join(value.split())[:limit]


def _safe_component(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-") or "remote"
    if safe == value and value not in {".", ".."}:
        return safe
    return f"{safe[:80]}--{hashlib.sha256(value.encode()).hexdigest()[:12]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
