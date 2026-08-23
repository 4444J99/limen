"""Repository-qualified, exact-tip remote branch reap effect machinery."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from limen.universe_recovery import (
    ReapCapabilityV1,
    ReapJournalState,
    ReapJournalV1,
    ReapPlanV1,
    canonical_digest,
    cas_delete_command,
    verify_reap_capability,
)


Runner = Callable[..., subprocess.CompletedProcess[str]]


def utc_now() -> datetime:
    return datetime.now(UTC)


def atomic_json(path: Path, value: Any) -> None:
    """Atomically fsync one bounded effect receipt."""

    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(value, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def load_model(path: Path, model):
    return model.model_validate(json.loads(path.read_text(encoding="utf-8")))


def remote_url(repository_root: Path, *, runner: Runner = subprocess.run) -> str:
    process = runner(
        ["git", "-C", str(repository_root), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if process.returncode != 0 or not process.stdout.strip():
        raise RuntimeError("cannot resolve repository origin")
    return process.stdout.strip()


def remote_url_digest(repository_root: Path, *, runner: Runner = subprocess.run) -> str:
    return canonical_digest({"origin": remote_url(repository_root, runner=runner)})


def github_repository_slug(repository_root: Path, *, runner: Runner = subprocess.run) -> str:
    """Resolve an owner/repository slug without exposing credentials or query data."""

    value = remote_url(repository_root, runner=runner)
    if value.startswith("git@github.com:"):
        path = value.removeprefix("git@github.com:")
    else:
        parsed = urlparse(value)
        if parsed.hostname != "github.com":
            raise RuntimeError("repository origin is not a canonical GitHub remote")
        path = parsed.path.lstrip("/")
    slug = path.removesuffix(".git").strip("/")
    if slug.count("/") != 1 or any(part in {"", ".", ".."} for part in slug.split("/")):
        raise RuntimeError("repository origin has no unambiguous owner/repository identity")
    return slug


def remote_tip(
    repository_root: Path,
    ref: str,
    *,
    runner: Runner = subprocess.run,
) -> str | None:
    process = runner(
        ["git", "-C", str(repository_root), "ls-remote", "--refs", "origin", ref],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if process.returncode not in {0, 2}:
        raise RuntimeError("remote ref observation failed")
    rows = [line.split() for line in process.stdout.splitlines() if line.strip()]
    matches = [row[0] for row in rows if len(row) == 2 and row[1] == ref]
    if len(matches) > 1:
        raise RuntimeError("remote ref observation is ambiguous")
    return matches[0] if matches else None


def journal(
    *,
    capability: ReapCapabilityV1,
    state: ReapJournalState,
    detail: str,
    observed_at: datetime,
) -> ReapJournalV1:
    return ReapJournalV1(
        effect_id=f"effect-{capability.capability_id}",
        capability_id=capability.capability_id,
        repository=capability.repository,
        ref=capability.ref,
        expected_tip=capability.live_tip,
        state=state,
        updated_at=observed_at,
        detail=detail,
    )


def _journal_matches(current: ReapJournalV1, capability: ReapCapabilityV1) -> None:
    expected = (
        capability.capability_id,
        capability.repository,
        capability.ref,
        capability.live_tip,
    )
    actual = (current.capability_id, current.repository, current.ref, current.expected_tip)
    if actual != expected:
        raise RuntimeError("reap journal does not bind the supplied capability")


def apply_capability(
    *,
    repository_root: Path,
    plan: ReapPlanV1,
    capability: ReapCapabilityV1,
    journal_path: Path,
    signing_material: bytes,
    observed_at: datetime | None = None,
    runner: Runner = subprocess.run,
) -> ReapJournalV1:
    """Redeem one verified capability and prove the exact ref is absent."""

    observed_at = (observed_at or utc_now()).astimezone(UTC)
    verify_reap_capability(
        capability,
        plan=plan,
        signing_material=signing_material,
        observed_at=observed_at,
    )
    current = load_model(journal_path, ReapJournalV1)
    _journal_matches(current, capability)
    if current.state == "completed":
        if remote_tip(repository_root, capability.ref, runner=runner) is None:
            return current
        raise RuntimeError("completed reap journal conflicts with a live ref")
    if current.state != "verified":
        raise RuntimeError(f"reap journal requires reconciliation before apply: {current.state}")
    if remote_url_digest(repository_root, runner=runner) != capability.remote_url_digest:
        raise RuntimeError("repository origin does not match the capability")
    live_tip = remote_tip(repository_root, capability.ref, runner=runner)
    if live_tip != capability.live_tip:
        raise RuntimeError("live ref tip does not match the capability")

    applying = journal(
        capability=capability,
        state="applying",
        detail="exact-tip CAS deletion admitted",
        observed_at=observed_at,
    )
    atomic_json(journal_path, applying.model_dump(mode="json"))
    try:
        command = cas_delete_command(capability)
        process = runner(
            [command[0], "-C", str(repository_root), *command[1:]],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError("exact-tip CAS deletion was rejected")
        if remote_tip(repository_root, capability.ref, runner=runner) is not None:
            raise RuntimeError("remote ref remains after deletion")
    except Exception as exc:
        crashed = journal(
            capability=capability,
            state="crashed",
            detail=str(exc),
            observed_at=utc_now(),
        )
        atomic_json(journal_path, crashed.model_dump(mode="json"))
        raise
    completed = journal(
        capability=capability,
        state="completed",
        detail="exact-tip CAS deletion and post-effect absence verified",
        observed_at=utc_now(),
    )
    atomic_json(journal_path, completed.model_dump(mode="json"))
    return completed


def reconcile_effect(
    *,
    repository_root: Path,
    current: ReapJournalV1,
    observed_at: datetime | None = None,
    runner: Runner = subprocess.run,
) -> ReapJournalV1:
    """Classify an interrupted effect without issuing or consuming new authority."""

    if current.state not in {"applying", "crashed"}:
        return current
    observed_at = (observed_at or utc_now()).astimezone(UTC)
    tip = remote_tip(repository_root, current.ref, runner=runner)
    if tip is None:
        return current.model_copy(
            update={
                "state": "completed",
                "updated_at": observed_at,
                "detail": "reconciled: remote ref is absent",
            }
        )
    if tip == current.expected_tip:
        return current.model_copy(
            update={
                "state": "crashed",
                "updated_at": observed_at,
                "detail": "reconciled: expected ref still exists; same capability requires owner review",
            }
        )
    return current.model_copy(
        update={
            "state": "crashed",
            "updated_at": observed_at,
            "detail": "reconciled: ref advanced; deletion denied and successor owner required",
        }
    )
