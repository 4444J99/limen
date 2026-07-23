"""Strict, shell-free predicates and packet attestation for remote workers.

This module is pure stdlib so a GitHub runner can execute it directly from the Limen control
checkout before installing project dependencies.  User text is never evaluated by a shell.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import selectors
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

SCHEMA_VERSION = "limen.remote-execution.v3"
SHA_RE = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,127}$")
PROVIDER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
WORKFLOW_PATH_RE = re.compile(r"^\.github/workflows/[A-Za-z0-9_.-]+\.ya?ml$")
CONTROL_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
VERIFIER_SCRIPT_RE = re.compile(r"^(?:scripts|tools)/(?:check|verify)[A-Za-z0-9_.-]*\.py$")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+1[ .-]?)?(?:\(\d{3}\)|\d{3}-)\s*\d{3}[ .-]\d{4}(?!\d)")
SSN_RE = re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)")
SENSITIVE_RE = re.compile(
    r"(?i)(?:(?:api[_-]?key|access[_-]?token|client[_-]?secret|private[_-]?key|password)\s*[:=]\s*\S+"
    r"|github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9_]+|sk-[A-Za-z0-9_-]{12,})"
)
PRIVATE_RE = re.compile(r"(?i)(?:/Volumes/|/Users/|/home/|\.limen-private(?:/|\b)|~/|keychain)")
SHELL_META_RE = re.compile(r"(?:&&|\|\||[;|`<>\n\r]|\$\(|\$\{|\*|\?)")

# The untrusted repository never executes on the Actions host.  The image is an exact immutable
# multi-arch manifest from Docker's official Python image.  Updating it is a reviewed control-plane
# change and changes every sandbox receipt through ``SANDBOX_PROFILE_DIGEST``.
SANDBOX_IMAGE = "python@sha256:eb43ff125d8d58d7449dcba7d336c23bcac412f526d861db493b9994d8010280"
SANDBOX_OK = b"limen-sandbox-boundary-v1\n"
SANDBOX_OUTPUT_LIMIT = 1_048_576
SANDBOX_ENV = {
    "HOME": "/tmp",
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONCOERCECLOCALE": "0",
    "PYTHONHASHSEED": "0",
    "PYTHONIOENCODING": "UTF-8",
    "PYTHONUTF8": "1",
    "TMPDIR": "/tmp",
}


class PredicateContractError(ValueError):
    pass


def digest_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def digest_text(value: str) -> str:
    return digest_bytes(value.encode())


def validate_control_ref(value: str, kind: str) -> str:
    """Validate a short GitHub branch/tag name accepted by workflow dispatch."""

    if kind not in {"branch", "tag"}:
        raise PredicateContractError("control ref kind must be branch or tag")
    if (
        not CONTROL_REF_RE.fullmatch(value)
        or value.upper() == "HEAD"
        or SHA_RE.fullmatch(value.lower())
        or value.lower().startswith("refs/")
        or value.endswith(("/", "."))
        or ".." in value
        or "//" in value
        or any(part.endswith(".lock") or part.startswith(".") for part in value.split("/"))
    ):
        raise PredicateContractError("control ref must be an explicit safe branch or tag name")
    return value


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def assert_public_text(value: str, *, field: str) -> None:
    if PRIVATE_RE.search(value):
        raise PredicateContractError(f"{field} references private/local custody")
    if SENSITIVE_RE.search(value):
        raise PredicateContractError(f"{field} appears to contain a plaintext credential")
    if EMAIL_RE.search(value) or PHONE_RE.search(value) or SSN_RE.search(value):
        raise PredicateContractError(f"{field} appears to contain personal contact data")


def _safe_relative_path(token: str) -> bool:
    if token.startswith(("/", "~")):
        return False
    path = PurePosixPath(token.split("::", 1)[0])
    return ".." not in path.parts and all(not part.startswith(".limen-private") for part in path.parts)


@dataclass(frozen=True)
class TrustedPredicate:
    source: str
    argv: tuple[str, ...]

    @property
    def digest(self) -> str:
        return digest_text(self.source)


def parse_trusted_predicate(value: str) -> TrustedPredicate:
    source = value.strip()
    if not source:
        raise PredicateContractError("predicate is empty")
    assert_public_text(source, field="predicate")
    if SHELL_META_RE.search(source):
        raise PredicateContractError("predicate contains shell composition or expansion")
    try:
        argv = tuple(shlex.split(source, posix=True))
    except ValueError as exc:
        raise PredicateContractError(f"predicate quoting is invalid: {exc}") from exc
    # Parsing is only an input-language gate; the security boundary is the locked-down container
    # below.  Keeping this grammar to one repository-owned stdlib verifier prevents a task from
    # quietly turning the verification-only lane into a build/test/package executor.
    if len(argv) != 2 or argv[0] != "python3" or not VERIFIER_SCRIPT_RE.fullmatch(argv[1]):
        raise PredicateContractError(
            "remote predicate must be exactly: python3 scripts/check*.py or python3 scripts/verify*.py"
        )
    if not _safe_relative_path(argv[1]):
        raise PredicateContractError("predicate verifier path is unsafe")
    return TrustedPredicate(source=source, argv=argv)


@dataclass(frozen=True)
class ReceiptTarget:
    scheme: str
    repo: str
    kind: str
    identifier: str
    path: str = ""

    @classmethod
    def parse(cls, value: str) -> ReceiptTarget:
        parts = value.split(":", 4)
        if len(parts) < 4:
            raise PredicateContractError("receipt_target is not a supported exact target")
        scheme, repo, kind, identifier = parts[:4]
        path = parts[4] if len(parts) == 5 else ""
        if scheme not in {"github", "artifact"} or not REPO_RE.fullmatch(repo):
            raise PredicateContractError("receipt_target has an unsupported scheme or repo")
        if scheme == "artifact":
            if kind != "task" or not SAFE_ID_RE.fullmatch(identifier) or path:
                raise PredicateContractError("artifact target must be artifact:<repo>:task:<task-id>")
            return cls(scheme, repo, "artifact", identifier)
        if kind in {"pull-request", "issue", "actions-run"}:
            if not identifier.isdigit() or path:
                raise PredicateContractError(f"github {kind} target requires an exact numeric identity")
        elif kind in {"commit", "tree"}:
            if not SHA_RE.fullmatch(identifier) or path:
                raise PredicateContractError(f"github {kind} target requires an exact SHA")
        elif kind == "blob":
            if not SHA_RE.fullmatch(identifier) or not path or not _safe_relative_path(path):
                raise PredicateContractError("github blob target requires exact SHA and safe path")
        else:
            raise PredicateContractError("receipt_target kind is unsupported")
        return cls(scheme, repo, kind.replace("-", "_"), identifier, path)

    def matches(self, output: Mapping[str, object]) -> bool:
        if str(output.get("kind") or "") != self.kind:
            return False
        if str(output.get("repo") or "") != self.repo:
            return False
        if str(output.get("identifier") or "") != self.identifier:
            return False
        if str(output.get("path") or "") != self.path:
            return False
        uri = str(output.get("uri") or "")
        if self.kind == "artifact":
            match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/actions/runs/(\d+)", uri)
            return bool(match and match.group(1) == self.repo)
        suffix_kind = {
            "pull_request": "pull",
            "issue": "issues",
            "commit": "commit",
            "blob": "blob",
            "tree": "tree",
            "actions_run": "actions/runs",
        }[self.kind]
        parsed = urlparse(uri)
        if parsed.scheme != "https" or parsed.netloc != "github.com":
            return False
        expected = f"/{self.repo}/{suffix_kind}/{self.identifier}"
        if self.kind == "blob":
            expected += f"/{self.path}"
        return parsed.path.rstrip("/") == expected.rstrip("/")


def validate_content_references(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise PredicateContractError("inputs_json must be a list")
    if len(value) > 64:
        raise PredicateContractError("too many remote input references")
    rows: list[dict[str, object]] = []
    for item in value:
        if not isinstance(item, dict):
            raise PredicateContractError("input reference must be an object")
        digest = str(item.get("digest") or "")
        uri = str(item.get("uri") or "")
        redacted = item.get("redacted") is True
        media_type = str(item.get("media_type") or "application/octet-stream")
        if not DIGEST_RE.fullmatch(digest) or not redacted:
            raise PredicateContractError("input must be redacted and content-addressed")
        if not uri.startswith(("https://github.com/", "artifact:")):
            raise PredicateContractError("input URI lacks approved remote custody")
        assert_public_text(uri, field="input URI")
        assert_public_text(media_type, field="input media type")
        rows.append({"digest": digest, "uri": uri, "media_type": media_type, "redacted": True})
    if len(canonical_json(rows)) > 32_768:
        raise PredicateContractError("remote input manifest is too large")
    return rows


def _validate_json_value(value: object, *, depth: int = 0) -> None:
    if depth > 12:
        raise PredicateContractError("execution profile is nested too deeply")
    if value is None or isinstance(value, bool | str | int):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise PredicateContractError("execution profile contains a non-finite number")
    if isinstance(value, list):
        for item in value:
            _validate_json_value(item, depth=depth + 1)
        return
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise PredicateContractError("execution profile keys must be strings")
        for item in value.values():
            _validate_json_value(item, depth=depth + 1)
        return
    raise PredicateContractError("execution profile contains a non-JSON value")


def validate_execution_profile(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise PredicateContractError("execution_profile_json must be an object")
    _validate_json_value(value)
    encoded = canonical_json(value)
    if len(encoded) > 16_384:
        raise PredicateContractError("execution profile is too large")
    text = encoded.decode()
    assert_public_text(text, field="execution profile")
    if re.search(r'(?i)"(?:model|model_id|tier)"\s*:', text):
        raise PredicateContractError("execution profile may not pin a model or tier")
    return value


def packet_payload(
    *,
    provider: str,
    task_id: str,
    repo: str,
    base_sha: str,
    control_repo: str,
    control_ref: str,
    control_ref_kind: str,
    control_sha: str,
    workflow_id: int,
    workflow_path: str,
    workflow_event: str,
    verification_context_digest: str,
    predicate_digest: str,
    instruction_digest: str,
    receipt_target: str,
    custody_mode: str,
    inputs: list[dict[str, object]],
    execution_profile: dict[str, object],
) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "task_id": task_id,
        "repo": repo,
        "base_sha": base_sha,
        "control_repo": control_repo,
        "control_ref": control_ref,
        "control_ref_kind": control_ref_kind,
        "control_sha": control_sha,
        "workflow_id": workflow_id,
        "workflow_path": workflow_path,
        "workflow_event": workflow_event,
        "verification_context_digest": verification_context_digest,
        "predicate_digest": predicate_digest,
        "instruction_digest": instruction_digest,
        "receipt_target": receipt_target,
        "custody_mode": custody_mode,
        "inputs": inputs,
        "execution_profile": execution_profile,
    }


def packet_digest(
    *,
    provider: str,
    task_id: str,
    repo: str,
    base_sha: str,
    control_repo: str,
    control_ref: str,
    control_ref_kind: str,
    control_sha: str,
    workflow_id: int,
    workflow_path: str,
    workflow_event: str,
    verification_context_digest: str,
    predicate_digest: str,
    instruction_digest: str,
    receipt_target: str,
    custody_mode: str,
    inputs: list[dict[str, object]],
    execution_profile: dict[str, object],
) -> str:
    return digest_bytes(
        canonical_json(
            packet_payload(
                provider=provider,
                task_id=task_id,
                repo=repo,
                base_sha=base_sha,
                control_repo=control_repo,
                control_ref=control_ref,
                control_ref_kind=control_ref_kind,
                control_sha=control_sha,
                workflow_id=workflow_id,
                workflow_path=workflow_path,
                workflow_event=workflow_event,
                verification_context_digest=verification_context_digest,
                predicate_digest=predicate_digest,
                instruction_digest=instruction_digest,
                receipt_target=receipt_target,
                custody_mode=custody_mode,
                inputs=inputs,
                execution_profile=execution_profile,
            )
        )
    )


def _run(argv: Sequence[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        list(argv),
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


SandboxRunner = Callable[[Sequence[str], int], subprocess.CompletedProcess[bytes]]


def _sandbox_profile() -> dict[str, object]:
    return {
        "version": "limen.verifier-sandbox.v1",
        "image": SANDBOX_IMAGE,
        "network": "none",
        "rootfs": "read-only",
        "target_mount": "read-only:/workspace",
        "writable": ["tmpfs:/tmp:64MiB:noexec,nosuid,nodev"],
        "capabilities": "none",
        "no_new_privileges": True,
        "uid_gid": "65534:65534",
        "cpus": "1.0",
        "memory": "512m",
        "pids": 64,
        "container_logs": "local:max-size=1m,max-file=1,compress=false",
        "environment": dict(sorted(SANDBOX_ENV.items())),
    }


SANDBOX_PROFILE_DIGEST = digest_bytes(canonical_json(_sandbox_profile()))


def sandbox_command(cwd: Path, script: str, *, docker_binary: str = "docker") -> tuple[str, ...]:
    """Build the fixed OS isolation boundary for one untrusted repository verifier.

    The only variable container inputs are a resolved target directory and a prevalidated script
    path inside that read-only mount.  No host environment, workspace sibling, Docker socket,
    credential file, or control checkout is mounted.
    """

    target = cwd.resolve(strict=True)
    if not target.is_dir() or "," in str(target) or "\n" in str(target):
        raise PredicateContractError("sandbox target path is unavailable or unsupported")
    if not VERIFIER_SCRIPT_RE.fullmatch(script):
        raise PredicateContractError("sandbox script is not a verification-only entrypoint")
    return (
        docker_binary,
        "run",
        "--rm",
        "--log-driver=local",
        "--log-opt=max-size=1m",
        "--log-opt=max-file=1",
        "--log-opt=compress=false",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--ipc=none",
        "--pids-limit=64",
        "--memory=512m",
        "--memory-swap=512m",
        "--cpus=1.0",
        "--ulimit=nofile=256:256",
        "--user=65534:65534",
        "--hostname=limen-verifier",
        "--workdir=/workspace",
        "--mount",
        f"type=bind,src={target},dst=/workspace,readonly",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,nodev,size=67108864,mode=1777",
        "--entrypoint=/usr/bin/env",
        SANDBOX_IMAGE,
        "-i",
        *(f"{key}={value}" for key, value in sorted(SANDBOX_ENV.items())),
        "python3",
        f"/workspace/{script}",
    )


def _default_sandbox_runner(argv: Sequence[str], timeout: int) -> subprocess.CompletedProcess[bytes]:
    process = subprocess.Popen(
        list(argv),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    if process.stdout is None:  # pragma: no cover - Popen invariant for stdout=PIPE
        raise PredicateContractError("sandbox output pipe is unavailable")
    chunks: list[bytes] = []
    size = 0
    deadline = time.monotonic() + timeout
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    exceeded = False
    timed_out = False
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            events = selector.select(timeout=min(remaining, 0.25))
            if not events:
                if process.poll() is not None:
                    break
                continue
            chunk = os.read(process.stdout.fileno(), 65_536)
            if not chunk:
                break
            size += len(chunk)
            if size > SANDBOX_OUTPUT_LIMIT:
                exceeded = True
                break
            chunks.append(chunk)
    finally:
        selector.close()
    if exceeded or timed_out:
        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=2)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
        message = b"sandbox output limit exceeded\n" if exceeded else b"sandbox timeout exceeded\n"
        return subprocess.CompletedProcess(list(argv), 124 if timed_out else 125, message)
    try:
        returncode = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        return subprocess.CompletedProcess(list(argv), 124, b"sandbox timeout exceeded\n")
    return subprocess.CompletedProcess(list(argv), returncode, b"".join(chunks))


def _attest_sandbox_runtime(runner: SandboxRunner, *, docker_binary: str) -> None:
    version = runner((docker_binary, "version", "--format", "{{.Server.Version}}"), 30)
    if version.returncode != 0 or not (version.stdout or b"").strip():
        raise PredicateContractError("Docker daemon unavailable for verification sandbox")
    image = runner(
        (docker_binary, "image", "inspect", SANDBOX_IMAGE, "--format", "{{json .RepoDigests}}"),
        30,
    )
    if image.returncode != 0:
        raise PredicateContractError("pinned verification sandbox image is unavailable")
    try:
        digests = json.loads((image.stdout or b"").decode())
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PredicateContractError("sandbox image identity inspection is invalid") from exc
    if not isinstance(digests, list) or SANDBOX_IMAGE not in digests:
        raise PredicateContractError("sandbox image does not match the allowlisted official digest")


def _sandbox_probe_source() -> str:
    expected = repr(dict(sorted(SANDBOX_ENV.items())))
    return f"""from pathlib import Path
import os
import socket

EXPECTED = {expected}
if dict(os.environ) != EXPECTED:
    raise SystemExit("environment inheritance detected")
if "GITHUB_STEP_SUMMARY" in os.environ or any(key.startswith("GITHUB_") for key in os.environ):
    raise SystemExit("GitHub command/runtime environment exposed")
if any("host-secret-must-not-cross" in value for value in os.environ.values()):
    raise SystemExit("host secret sentinel exposed")
if Path("/workspace/../.limen-control").exists() or Path("/github/workspace/.limen-control").exists():
    raise SystemExit("control checkout sibling exposed")

for candidate in (
    Path("/workspace/limen-outside-write"),
    Path("/outside-write"),
    Path("/root/outside-write"),
    Path("/github/workspace/outside-write"),
):
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("unsafe")
    except OSError:
        pass
    else:
        raise SystemExit(f"outside write succeeded: {{candidate}}")

temporary = Path("/tmp/limen-sandbox-probe")
temporary.write_text("ephemeral")
if temporary.read_text() != "ephemeral":
    raise SystemExit("controlled temporary output unavailable")
if any(name != "lo" for _index, name in socket.if_nameindex()):
    raise SystemExit("non-loopback network interface exposed")
sock = socket.socket()
sock.settimeout(0.25)
try:
    connected = sock.connect_ex(("198.51.100.1", 9)) == 0
finally:
    sock.close()
if connected:
    raise SystemExit("outbound network unexpectedly reachable")
print("limen-sandbox-boundary-v1")
"""


def _attest_sandbox(runner: SandboxRunner, *, docker_binary: str, timeout: int) -> str:
    with tempfile.TemporaryDirectory(prefix="limen-sandbox-probe-") as directory:
        root = Path(directory)
        script = root / "scripts" / "check-limen-sandbox.py"
        script.parent.mkdir()
        script.write_text(_sandbox_probe_source())
        script.chmod(0o644)
        result = runner(sandbox_command(root, "scripts/check-limen-sandbox.py", docker_binary=docker_binary), timeout)
    if result.returncode != 0 or result.stdout != SANDBOX_OK or len(result.stdout or b"") > SANDBOX_OUTPUT_LIMIT:
        detail = (result.stdout or b"").decode(errors="replace").strip()[:240]
        raise PredicateContractError(f"verification sandbox boundary self-test failed: {detail or result.returncode}")
    return digest_bytes(result.stdout)


def _run_sandbox(
    predicate: TrustedPredicate,
    *,
    cwd: Path,
    timeout: int,
    runner: SandboxRunner,
    docker_binary: str,
) -> subprocess.CompletedProcess[bytes]:
    result = runner(sandbox_command(cwd, predicate.argv[1], docker_binary=docker_binary), timeout)
    if len(result.stdout or b"") <= SANDBOX_OUTPUT_LIMIT:
        return result
    return subprocess.CompletedProcess(result.args, 125, b"sandbox output limit exceeded\n")


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return _run(("git", *args), cwd=cwd, timeout=60)


def _validate_repo_paths(predicate: TrustedPredicate, cwd: Path) -> None:
    """Reject verifier paths that escape the exact checkout through a symlink or flag value."""

    symlink_rows = _git(cwd, "ls-files", "-s")
    if symlink_rows.returncode != 0:
        raise PredicateContractError("unable to attest tracked verifier paths")
    if any(row.startswith(b"120000 ") for row in symlink_rows.stdout.splitlines()):
        raise PredicateContractError("remote verifier checkout may not contain tracked symlinks")

    relative = predicate.argv[1]
    tracked = _git(cwd, "ls-files", "--error-unmatch", "--", relative)
    if tracked.returncode != 0 or tracked.stdout.decode(errors="replace").strip() != relative:
        raise PredicateContractError(f"predicate verifier is not tracked at the exact checkout: {relative}")
    candidate = cwd / relative
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(cwd)
    except (FileNotFoundError, ValueError):
        raise PredicateContractError(f"predicate target is absent or escapes checkout: {relative}") from None
    if candidate.is_symlink() or not candidate.is_file():
        raise PredicateContractError(f"predicate target must be a regular non-symlink file: {relative}")


def _scan_delta(cwd: Path) -> tuple[bool, str, int]:
    diff = _git(cwd, "diff", "HEAD", "--binary", "--no-ext-diff")
    status = _git(cwd, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    payload = bytearray(diff.stdout or b"")
    unsafe = diff.returncode != 0 or status.returncode != 0
    for raw_row in (status.stdout or b"").split(b"\0"):
        if not raw_row.startswith(b"?? "):
            continue
        relative = raw_row[3:].decode(errors="replace")
        if not _safe_relative_path(relative):
            unsafe = True
            continue
        candidate = (cwd / relative).resolve()
        try:
            candidate.relative_to(cwd)
        except ValueError:
            unsafe = True
            continue
        payload.extend(b"\nUNTRACKED\0" + relative.encode(errors="replace") + b"\0")
        if not candidate.is_file() or candidate.is_symlink() or candidate.stat().st_size > 10_000_000:
            unsafe = True
            continue
        payload.extend(candidate.read_bytes())
        if len(payload) > 20_000_000:
            unsafe = True
            break
    blob = bytes(payload)
    text = blob.decode(errors="replace")
    unsafe = unsafe or bool(
        SENSITIVE_RE.search(text)
        or EMAIL_RE.search(text)
        or PHONE_RE.search(text)
        or SSN_RE.search(text)
        or PRIVATE_RE.search(text)
    )
    return not unsafe, digest_bytes(blob), len(blob)


def execute_attested(
    args: argparse.Namespace,
    *,
    sandbox_runner: SandboxRunner | None = None,
) -> dict[str, object]:
    predicate = parse_trusted_predicate(args.predicate)
    target = ReceiptTarget.parse(args.receipt_target)
    if not PROVIDER_RE.fullmatch(args.provider):
        raise PredicateContractError("provider identifier is invalid")
    if args.custody_mode != "artifact":
        raise PredicateContractError("central deterministic worker requires artifact custody")
    if target != ReceiptTarget("artifact", args.control_repo, "artifact", args.task_id):
        raise PredicateContractError("central worker receipt target must bind control repo and task ID")
    if not re.fullmatch(r"[0-9a-f]{32}", args.request_id):
        raise PredicateContractError("request ID is invalid")
    if not REPO_RE.fullmatch(args.repo) or not REPO_RE.fullmatch(args.control_repo):
        raise PredicateContractError("repo is invalid")
    validate_control_ref(args.control_ref, args.control_ref_kind)
    if (
        not SAFE_ID_RE.fullmatch(args.task_id)
        or not SHA_RE.fullmatch(args.base_sha)
        or not SHA_RE.fullmatch(args.control_sha)
    ):
        raise PredicateContractError("task ID, target SHA, or control SHA is invalid")
    if (
        isinstance(args.workflow_id, bool)
        or not isinstance(args.workflow_id, int)
        or args.workflow_id <= 0
        or not WORKFLOW_PATH_RE.fullmatch(args.workflow_path)
        or args.workflow_event != "workflow_dispatch"
    ):
        raise PredicateContractError("workflow identity is invalid")
    if not DIGEST_RE.fullmatch(args.verification_context_digest):
        raise PredicateContractError("verification context digest is invalid")
    if args.observed_control_repo != args.control_repo or args.observed_workflow_event != args.workflow_event:
        raise PredicateContractError("observed repository/event does not match workflow packet")
    if args.observed_control_ref != args.control_ref or args.observed_control_ref_kind != args.control_ref_kind:
        raise PredicateContractError("observed workflow branch/tag does not match control ref")
    if args.observed_workflow_sha.lower() != args.control_sha:
        raise PredicateContractError("observed workflow SHA does not match exact control commit")
    control_namespace = "heads" if args.control_ref_kind == "branch" else "tags"
    expected_workflow_ref = f"{args.control_repo}/{args.workflow_path}@refs/{control_namespace}/{args.control_ref}"
    if args.observed_workflow_ref != expected_workflow_ref:
        raise PredicateContractError("observed workflow ref does not match exact workflow path and control ref")
    inputs = validate_content_references(json.loads(args.inputs_json))
    profile = validate_execution_profile(json.loads(args.execution_profile_json))
    expected_packet = packet_digest(
        provider=args.provider,
        task_id=args.task_id,
        repo=args.repo,
        base_sha=args.base_sha,
        control_repo=args.control_repo,
        control_ref=args.control_ref,
        control_ref_kind=args.control_ref_kind,
        control_sha=args.control_sha,
        workflow_id=args.workflow_id,
        workflow_path=args.workflow_path,
        workflow_event=args.workflow_event,
        verification_context_digest=args.verification_context_digest,
        predicate_digest=predicate.digest,
        instruction_digest=args.instruction_digest,
        receipt_target=args.receipt_target,
        custody_mode=args.custody_mode,
        inputs=inputs,
        execution_profile=profile,
    )
    if args.packet_digest != expected_packet:
        raise PredicateContractError("packet digest mismatch")
    if args.request_id != expected_packet.removeprefix("sha256:")[:32]:
        raise PredicateContractError("request ID does not match recomputed packet digest")
    cwd = Path(args.cwd).resolve()
    observed = _git(cwd, "rev-parse", "HEAD")
    observed_sha = observed.stdout.decode().strip().lower() if observed.returncode == 0 else ""
    if observed_sha != args.base_sha:
        raise PredicateContractError("observed checkout SHA does not match packet base SHA")
    control_cwd = Path(args.control_cwd).resolve()
    observed_control = _git(control_cwd, "rev-parse", "HEAD")
    observed_control_sha = observed_control.stdout.decode().strip().lower() if observed_control.returncode == 0 else ""
    if observed_control_sha != args.control_sha:
        raise PredicateContractError("observed control checkout SHA does not match packet control SHA")
    if not DIGEST_RE.fullmatch(args.instruction_digest):
        raise PredicateContractError("instruction digest is invalid")
    _validate_repo_paths(predicate, cwd)

    runner = sandbox_runner or _default_sandbox_runner
    _attest_sandbox_runtime(runner, docker_binary=args.docker_binary)
    sandbox_attestation_digest = _attest_sandbox(
        runner,
        docker_binary=args.docker_binary,
        timeout=min(60, args.timeout),
    )
    result = _run_sandbox(
        predicate,
        cwd=cwd,
        timeout=args.timeout,
        runner=runner,
        docker_binary=args.docker_binary,
    )
    output_digest = digest_bytes(result.stdout or b"")
    delta_safe, delta_digest, delta_bytes = _scan_delta(cwd)
    clean = _git(cwd, "status", "--porcelain").stdout.strip() == b""
    exit_code = result.returncode if result.returncode != 0 else (0 if clean and delta_safe else 125)
    run_url = args.run_url.rstrip("/")
    if not re.fullmatch(rf"https://github\.com/{re.escape(args.control_repo)}/actions/runs/\d+", run_url):
        raise PredicateContractError("run URL does not bind the control repository and numeric run ID")
    outputs: list[dict[str, object]] = []
    if exit_code == 0:
        outputs.append(
            {
                "kind": "artifact",
                "uri": run_url,
                "repo": args.control_repo,
                "identifier": args.task_id,
                "path": "",
            }
        )
    receipt: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "request_id": args.request_id,
        "provider": args.provider,
        "task_id": args.task_id,
        "repo": args.repo,
        "base_sha": args.base_sha,
        "observed_sha": observed_sha,
        "control_repo": args.control_repo,
        "control_ref": args.control_ref,
        "control_ref_kind": args.control_ref_kind,
        "control_sha": args.control_sha,
        "observed_control_sha": observed_control_sha,
        "observed_control_ref": args.observed_control_ref,
        "observed_control_ref_kind": args.observed_control_ref_kind,
        "workflow_id": args.workflow_id,
        "workflow_path": args.workflow_path,
        "observed_workflow_path": args.workflow_path,
        "workflow_event": args.workflow_event,
        "observed_workflow_event": args.observed_workflow_event,
        "observed_workflow_sha": args.observed_workflow_sha.lower(),
        "verification_context_digest": args.verification_context_digest,
        "predicate_digest": predicate.digest,
        "instruction_digest": args.instruction_digest,
        "predicate_exit_code": exit_code,
        "predicate_output_digest": output_digest,
        "packet_digest": expected_packet,
        "receipt_target": args.receipt_target,
        "custody_mode": args.custody_mode,
        "inputs_digest": digest_bytes(canonical_json(inputs)),
        "execution_profile_digest": digest_bytes(canonical_json(profile)),
        "delta_safe": delta_safe,
        "delta_digest": delta_digest,
        "delta_bytes": delta_bytes,
        "workspace_clean": clean,
        "sandbox_image": SANDBOX_IMAGE,
        "sandbox_profile_digest": SANDBOX_PROFILE_DIGEST,
        "sandbox_attestation_digest": sandbox_attestation_digest,
        "outputs": outputs,
    }
    receipt["receipt_digest"] = digest_bytes(canonical_json(receipt))
    return receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--provider", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--control-repo", required=True)
    parser.add_argument("--control-ref", required=True)
    parser.add_argument("--control-ref-kind", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--control-sha", required=True)
    parser.add_argument("--workflow-id", required=True, type=int)
    parser.add_argument("--workflow-path", required=True)
    parser.add_argument("--workflow-event", required=True)
    parser.add_argument("--observed-control-repo", required=True)
    parser.add_argument("--observed-control-ref", required=True)
    parser.add_argument("--observed-control-ref-kind", required=True)
    parser.add_argument("--observed-workflow-event", required=True)
    parser.add_argument("--observed-workflow-ref", required=True)
    parser.add_argument("--observed-workflow-sha", required=True)
    parser.add_argument("--verification-context-digest", required=True)
    parser.add_argument("--predicate", required=True)
    parser.add_argument("--instruction-digest", required=True)
    parser.add_argument("--receipt-target", required=True)
    parser.add_argument("--custody-mode", required=True)
    parser.add_argument("--inputs-json", required=True)
    parser.add_argument("--execution-profile-json", required=True)
    parser.add_argument("--packet-digest", required=True)
    parser.add_argument("--run-url", required=True)
    parser.add_argument("--cwd", required=True)
    parser.add_argument("--control-cwd", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--timeout", type=int, default=2700)
    parser.add_argument("--docker-binary", default="docker")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        receipt = execute_attested(args)
    except (PredicateContractError, json.JSONDecodeError, OSError, subprocess.SubprocessError) as exc:
        print(f"remote predicate blocked: {exc}", file=sys.stderr)
        return 2
    output = Path(args.output)
    output.write_bytes(json.dumps(receipt, indent=2, sort_keys=True).encode() + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
