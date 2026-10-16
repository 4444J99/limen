"""Exact, signed admission for the versioned Domus shared-context producer."""

from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import pwd
import re
import shlex
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Any

import click

from limen.host_admission import AdmissionController, worktree_scope

APPROVED_SOURCE = "deb28a564ae76e5da1fa7446686a573125d75525"
PRODUCER_SOURCE = "dot_local/bin/executable_domus-shared-context"
AUTH_SOURCE = "dot_local/share/domus/host_mutation.py"
PRODUCER_SHA = "9b21eaecef4f4dd5696889719cc86793d48aad847da284c0ac8b571f79fa5e77"
AUTH_SHA = "e19900fa51226e4c3ddf9c6fa6ebd509b83f51f6cb40f11f35dbe9f2cd6e36be"
MAX_BYTES = 4 * 1024 * 1024
MAX_SECONDS = 90
BOOT_SCHEMA = "limen.shared_context_bootstrap_plan.v1"


class ContextAdmissionError(ValueError):
    """A context action does not satisfy its exact capability."""


def account_home() -> Path:
    return Path(pwd.getpwuid(os.getuid()).pw_dir).resolve()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def secure_read(path: Path) -> bytes:
    """Read one owned regular snapshot, rejecting aliases and writable peers."""
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_uid != os.getuid() or before.st_mode & 0o022:
            raise ContextAdmissionError("context input is not an owned secure regular file")
        if before.st_size > MAX_BYTES:
            raise ContextAdmissionError("context input exceeds its byte bound")
        with os.fdopen(os.dup(fd), "rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_mode", "st_uid")
        if len(raw) > MAX_BYTES or any(getattr(before, k) != getattr(after, k) for k in fields):
            raise ContextAdmissionError("context input changed during inspection")
        return raw
    finally:
        os.close(fd)


def command(args: list[str], *, cwd: Path | None = None, data: bytes | None = None) -> bytes:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    result = subprocess.run(args, cwd=cwd, input=data, capture_output=True, timeout=20, env=env, check=False)
    if result.returncode:
        raise ContextAdmissionError("bounded context subprocess failed")
    return result.stdout


def git(source: Path, *args: str) -> str:
    return command(["git", "-C", str(source), *args]).decode().strip()


def validate_source(source: Path) -> None:
    """Trust the configured Git store and approved source, never an origin label alone."""
    configured = Path(command(["chezmoi", "source-path"]).decode().strip()).resolve(strict=True)
    source = source.resolve(strict=True)
    if Path(git(source, "rev-parse", "--show-toplevel")).resolve() != source:
        raise ContextAdmissionError("context source is not a Git root")
    common = ("rev-parse", "--path-format=absolute", "--git-common-dir")
    if Path(git(source, *common)).resolve() != Path(git(configured, *common)).resolve():
        raise ContextAdmissionError("context source is outside the configured owner Git store")
    if git(source, "status", "--porcelain", "--untracked-files=normal"):
        raise ContextAdmissionError("context source is not committed and clean")
    # Dated receipts and plans may advance; executable/template inputs may not.
    if git(
        source,
        "diff",
        "--name-only",
        APPROVED_SOURCE,
        "HEAD",
        "--",
        ".",
        ":(exclude)docs/**",
        ":(exclude).codex/plans/**",
    ):
        raise ContextAdmissionError("context source differs from its approved deployment inputs")
    for name, expected in ((PRODUCER_SOURCE, PRODUCER_SHA), (AUTH_SOURCE, AUTH_SHA)):
        if digest(secure_read(source / name)) != expected:
            raise ContextAdmissionError("context producer source identity differs")


def load_module(path: Path, expected: str, name: str) -> ModuleType:
    raw = secure_read(path)
    if digest(raw) != expected:
        raise ContextAdmissionError("context executable or authorization module identity differs")
    module = ModuleType(name)
    module.__file__ = str(path)
    # Reuse the owner implementation only after verifying its pinned complete bytes.
    exec(compile(raw, str(path), "exec"), module.__dict__)  # noqa: S102
    return module


def producer(source: Path) -> ModuleType:
    return load_module(source / PRODUCER_SOURCE, PRODUCER_SHA, "limen_context_producer")


def authorizer(source: Path) -> ModuleType:
    return load_module(source / AUTH_SOURCE, AUTH_SHA, "limen_context_authorizer")


def request(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema": "domus.host_mutation_authorization.v2",
        "action": "shared_context.bootstrap",
        "attempt_id": plan["attempt_id"],
        "signature_namespace": "domus-host-mutation",
        "plan": plan,
        "plan_sha256": digest(canonical(plan)),
    }


def bootstrap_plan(source: Path, attempt_id: str) -> dict[str, Any]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{5,127}", attempt_id):
        raise ContextAdmissionError("invalid context attempt identity")
    validate_source(source)
    p = producer(source)
    home = account_home()
    targets = []
    for name, path, expected, mode in (
        (PRODUCER_SOURCE, home / ".local/bin/domus-shared-context", PRODUCER_SHA, 0o755),
        (AUTH_SOURCE, home / ".local/share/domus/host_mutation.py", AUTH_SHA, 0o644),
    ):
        targets.append({**p.destination_state(path, home), "source_path": name, "sha256": expected, "mode": mode})
    return {
        "schema": BOOT_SCHEMA,
        "source": str(source.resolve()),
        "revision": git(source, "rev-parse", "HEAD"),
        "home": str(home),
        "attempt_id": attempt_id,
        "deadline_seconds": MAX_SECONDS,
        "targets": targets,
    }


def read_plan(path: Path) -> dict[str, Any]:
    value = json.loads(secure_read(path))
    plan = value.get("plan", value)
    if not isinstance(plan, dict):
        raise ContextAdmissionError("context plan is not an object")
    return plan


def write_journal(path: Path, value: dict[str, Any]) -> None:
    fd, temporary = tempfile.mkstemp(prefix=".context-receipt-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(canonical(value) + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise ContextAdmissionError("context journal became an alias")
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def bounded_bootstrap(function):
    @wraps(function)
    def run(*args, **kwargs):
        def expired(*_args):
            raise ContextAdmissionError("context bootstrap deadline reached")

        started = time.monotonic()
        previous_handler = signal.signal(signal.SIGALRM, expired)
        previous_timer = signal.setitimer(signal.ITIMER_REAL, MAX_SECONDS)
        try:
            return function(*args, **kwargs)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_timer[0]:
                signal.setitimer(
                    signal.ITIMER_REAL, max(0.001, previous_timer[0] - (time.monotonic() - started)), previous_timer[1]
                )

    return run


@bounded_bootstrap
def bootstrap(plan: dict[str, Any], receipt: Path, signature: Path, work_key: str) -> dict[str, Any]:
    from limen.dispatch import _load_limen_env
    from limen.inventory_admission import require_approved_priority

    _load_limen_env()
    priority = require_approved_priority(work_key)
    if priority.get("outcome_id") != "shared-context-integration-20261016":
        raise ContextAdmissionError("context bootstrap requires its admitted outcome")
    source = Path(plan["source"])
    if plan.get("schema") != BOOT_SCHEMA or bootstrap_plan(source, plan["attempt_id"]) != plan:
        raise ContextAdmissionError("context bootstrap plan or before-images changed")
    auth = authorizer(source)
    signers = account_home() / ".config/git/allowed_signers"
    authority = auth.validate_authorization(receipt, signature, signers, request(plan))
    scope = worktree_scope(source)
    if not scope.linked:
        raise ContextAdmissionError("context bootstrap requires an isolated source checkout")
    controller = AdmissionController()
    owner = "context-bootstrap-" + plan["attempt_id"]
    lease = controller.acquire(scope.lease_kind, owner=owner, surface="shared-context-bootstrap", pid=os.getpid())
    if not lease.get("allowed"):
        raise ContextAdmissionError("context bootstrap source writer is unavailable")
    root = account_home() / ".local/state/domus/shared-context-bootstrap"
    p = producer(source)
    journal: dict[str, Any] = {
        "schema": "limen.shared_context_bootstrap_receipt.v1",
        "plan": plan,
        "authorization": authority,
        "status": "started",
        "before_images": [],
    }
    attempt: Path | None = None
    attempt_created = False
    try:
        p.destination_state(root / "receipt.json", account_home())
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or stat.S_IMODE(root.stat().st_mode) != 0o700:
            raise ContextAdmissionError("context bootstrap receipt root is not private")
        lock_fd = os.open(root / "writer.lock", os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
        with os.fdopen(lock_fd, "a+") as lock:
            lock_stat = os.fstat(lock.fileno())
            if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_uid != os.getuid() or lock_stat.st_mode & 0o077:
                raise ContextAdmissionError("context bootstrap lock is not private")
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            attempt = root / plan["attempt_id"]
            attempt.mkdir(mode=0o700)  # Never replay an ambiguous attempt.
            attempt_created = True
            for target in plan["targets"]:
                path = Path(target["path"])
                journal["before_images"].append(
                    {
                        "path": target["path"],
                        "before": target["before"],
                        "content_base64": base64.b64encode(secure_read(path)).decode() if path.exists() else None,
                    }
                )
            output = attempt / "receipt.json"
            write_journal(output, journal)

            auth._assert_authorization_inputs_unchanged(receipt, signature, signers, authority)
            if bootstrap_plan(source, plan["attempt_id"]) != plan:
                raise ContextAdmissionError("context bootstrap inputs changed before apply")
            command(
                [
                    "chezmoi",
                    "--source",
                    str(source),
                    "--destination",
                    str(account_home()),
                    "--no-tty",
                    "--refresh-externals=never",
                    "apply",
                    "--force",
                    "--exclude=scripts",
                    *[t["path"] for t in plan["targets"]],
                ],
                cwd=source,
            )
            auth._assert_authorization_inputs_unchanged(receipt, signature, signers, authority)
            for target in plan["targets"]:
                path = Path(target["path"])
                if digest(secure_read(path)) != target["sha256"] or stat.S_IMODE(path.stat().st_mode) != target["mode"]:
                    raise ContextAdmissionError("context bootstrap readback differs")
            journal["status"] = "verified"
            write_journal(output, journal)
            return {"status": "verified", "receipt": str(output), "targets": len(plan["targets"])}
    except Exception as exc:
        if attempt_created and attempt is not None:
            journal.update(status="failed", error_type=type(exc).__name__)
            write_journal(attempt / "receipt.json", journal)
        raise
    finally:
        controller.release(lease_id=lease["lease"]["lease_id"], owner=owner, pid=os.getpid())


def admit_command(
    command_text: str, *, controller: AdmissionController, owner: str | None, pid: int, surface: str, ttl_seconds: int
) -> None:
    """Validate the exact producer command before admitting any external write."""
    home = account_home()
    tokens = shlex.split(command_text)
    executable = home / ".local/bin/domus-shared-context"
    selected = (
        shutil.which(tokens[0]) if tokens and tokens[0] == "domus-shared-context" else tokens[0] if tokens else ""
    )
    if selected != str(executable) or executable.resolve() != executable:
        raise ContextAdmissionError("only the canonical installed context executable is permitted")
    if digest(secure_read(executable)) != PRODUCER_SHA or not executable.stat().st_mode & 0o100:
        raise ContextAdmissionError("installed context executable identity or mode differs")
    installed_auth = home / ".local/share/domus/host_mutation.py"
    if installed_auth.resolve() != installed_auth or digest(secure_read(installed_auth)) != AUTH_SHA:
        raise ContextAdmissionError("installed authorization module identity differs")
    options: dict[str, str] = {}
    if len(tokens) < 2 or (len(tokens) - 2) % 2:
        raise ContextAdmissionError("invalid context command arguments")
    for index in range(2, len(tokens), 2):
        key, value = tokens[index : index + 2]
        if key in options or not key.startswith("--") or value.startswith("--"):
            raise ContextAdmissionError("duplicate or malformed context argument")
        options[key] = value
    operation = tokens[1]
    expected = {
        "plan": {"--source", "--attempt-id"},
        "verify": {"--plan"},
        "apply": {"--plan", "--authorization", "--signature"},
    }
    if operation not in expected or set(options) != expected[operation]:
        raise ContextAdmissionError("expanded context command arguments are forbidden")
    if operation == "plan":
        validate_source(Path(options["--source"]))
        return
    plan = read_plan(Path(options["--plan"]))
    source = Path(plan["source"])
    validate_source(source)
    p = producer(source)
    actual = p.build_plan(source, plan["attempt_id"])
    if operation == "verify":
        # Post-apply before-images differ, but all destinations, source hashes,
        # aliases, modes and the synchronization script must remain identical.
        for value in (actual, plan):
            for target in [*value["targets"], value["mirror"]]:
                target.pop("before", None)
        if actual != plan:
            raise ContextAdmissionError("context verification plan expands or changes its source")
        return
    if owner is None or actual != plan:
        raise ContextAdmissionError("context apply writer, source or before-images changed")
    auth = authorizer(source)
    auth.validate_authorization(
        Path(options["--authorization"]),
        Path(options["--signature"]),
        home / ".config/git/allowed_signers",
        p.request(plan),
    )
    scope = worktree_scope(source)
    if not scope.linked:
        raise ContextAdmissionError("context apply requires an isolated source checkout")
    decision = controller.acquire(scope.lease_kind, owner=owner, surface=surface, pid=pid, ttl_seconds=ttl_seconds)
    if not decision.get("allowed"):
        raise ContextAdmissionError("context apply source writer is unavailable")


@click.command("shared-context")
@click.argument("operation", type=click.Choice(["bootstrap-plan", "bootstrap", "capabilities"]))
@click.option("--source", type=click.Path(path_type=Path))
@click.option("--attempt-id")
@click.option("--plan", type=click.Path(path_type=Path))
@click.option("--authorization", type=click.Path(path_type=Path))
@click.option("--signature", type=click.Path(path_type=Path))
@click.option("--work-key")
def shared_context_group(
    operation: str,
    source: Path | None,
    attempt_id: str | None,
    plan: Path | None,
    authorization: Path | None,
    signature: Path | None,
    work_key: str | None,
) -> None:
    """Inspect or bootstrap the exact signed shared-context producer."""
    try:
        if operation == "capabilities":
            if any((source, attempt_id, plan, authorization, signature, work_key)):
                raise ContextAdmissionError("capabilities accepts no overrides")
            result = {
                "schema": "limen.shared_context_capabilities.v1",
                "producer_sha256": PRODUCER_SHA,
                "authorization_module_sha256": AUTH_SHA,
                "approved_source": APPROVED_SOURCE,
                "external_writes": "exact-signed-plan-only",
                "bootstrap_targets": 2,
            }
        elif operation == "bootstrap-plan":
            if source is None or attempt_id is None or any((plan, authorization, signature, work_key)):
                raise ContextAdmissionError("bootstrap-plan requires only source and attempt-id")
            value = bootstrap_plan(source.resolve(), attempt_id)
            result = {"plan": value, "authorization_request": request(value)}
        else:
            if (
                any((source, attempt_id))
                or plan is None
                or authorization is None
                or signature is None
                or work_key is None
            ):
                raise ContextAdmissionError("bootstrap requires plan, authorization, signature and work-key")
            result = bootstrap(read_plan(plan), authorization, signature, work_key)
        click.echo(json.dumps(result, sort_keys=True))
    except Exception as exc:
        click.echo(json.dumps({"status": "failed", "error_type": type(exc).__name__}), err=True)
        raise click.exceptions.Exit(3) from exc
