"""Repository-qualified, exact-tip remote branch reap effect machinery."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
import fcntl
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

from limen.universe_recovery import (
    CustodyProofV1,
    RefDispositionV2,
    ReapCapabilityV1,
    ReapJournalState,
    ReapJournalV1,
    ReapPlanV1,
    ReviewLineageClosureV2,
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


@contextmanager
def locked_redemptions(path: Path) -> Iterator[dict[str, Any]]:
    """Lock the keeper-owned capability-spend registry across one effect."""

    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if path.exists():
                value = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(value, dict):
                    raise RuntimeError("remote-reap redemption registry is malformed")
            else:
                value = {}
            yield value
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


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


def _gh_json(arguments: list[str], *, runner: Runner = subprocess.run) -> dict[str, Any]:
    process = runner(
        ["gh", "api", *arguments],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError("GitHub evidence query failed")
    value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("GitHub evidence response is malformed")
    return value


def validate_disposition_evidence(
    *,
    repository_root: Path,
    disposition: RefDispositionV2,
    review: ReviewLineageClosureV2,
    custody: CustodyProofV1,
    runner: Runner = subprocess.run,
) -> None:
    """Recompute every live fact that can authorize capability issuance."""

    slug = github_repository_slug(repository_root, runner=runner)
    if not disposition.repository_identity.accepts(slug) or not disposition.repository_identity.accepts(
        disposition.repository
    ):
        raise ValueError("repository identity does not match the disposition")
    metadata = _gh_json([f"repos/{slug}"], runner=runner)
    canonical_slug = str(metadata.get("full_name") or slug)
    if metadata.get(
        "id"
    ) != disposition.repository_identity.repository_id or not disposition.repository_identity.accepts(canonical_slug):
        raise ValueError("stable repository identity does not match the disposition")
    default_branch = str(metadata.get("default_branch") or "")
    default_ref = f"refs/heads/{default_branch}"
    default_tip = remote_tip(repository_root, default_ref, runner=runner)
    archived = bool(metadata.get("archived"))
    generation = canonical_digest(
        {
            "repository_id": disposition.repository_identity.repository_id,
            "default_ref": default_branch,
            "default_sha": default_tip,
            "archived": archived,
        }
    )
    if (disposition.default_ref, disposition.default_tip, disposition.default_generation) != (
        default_ref,
        default_tip,
        generation,
    ):
        raise ValueError("live default generation does not match the disposition")
    if remote_tip(repository_root, disposition.ref, runner=runner) != disposition.tip:
        raise ValueError("live remote ref does not match the disposition")
    commit_digest = canonical_digest(
        {
            "repository_id": disposition.repository_identity.repository_id,
            "ref": disposition.ref,
            "tip": disposition.tip,
        }
    )
    if disposition.commit_digest != commit_digest:
        raise ValueError("commit digest does not match the live repository/ref/tip")
    if disposition.delivery_disposition != "exact_landed":
        raise ValueError("equivalent landing is not yet eligible for automated deletion")
    comparison = _gh_json(
        [f"repos/{slug}/compare/{disposition.tip}...{disposition.default_tip}"],
        runner=runner,
    )
    if (comparison.get("merge_base_commit") or {}).get("sha") != disposition.tip:
        raise ValueError("live default ancestry does not prove exact landing")
    if (
        not review.terminal
        or review.repository_identity != disposition.repository_identity
        or not review.repository_identity.accepts(review.repository)
        or review.pull_request not in disposition.pull_requests
    ):
        raise ValueError("review closure is nonterminal or not named by the disposition")
    if review.lifecycle_stage not in {"main_verified", "runtime_verified", "terminal"}:
        raise ValueError("review lineage has not reached main verification")
    pull = _gh_json([f"repos/{slug}/pulls/{review.pull_request}"], runner=runner)
    if not pull.get("merged") or (pull.get("head") or {}).get("sha") != disposition.tip:
        raise ValueError("live pull request does not prove the exact tip merged")
    if canonical_digest(custody) != disposition.custody_proof_digest:
        raise ValueError("custody proof digest does not match the disposition")
    if (custody.repository, custody.ref, custody.tip, custody.disposition) != (
        disposition.repository,
        disposition.ref,
        disposition.tip,
        disposition.custody_disposition,
    ):
        raise ValueError("custody proof does not bind the disposition")
    if custody.source_digest != commit_digest:
        raise ValueError("custody proof source digest does not match the live ref")


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
    redemption_path: Path,
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
    if remote_url_digest(repository_root, runner=runner) != capability.remote_url_digest:
        raise RuntimeError("repository origin does not match the capability")
    with locked_redemptions(redemption_path) as redemptions:
        spent = redemptions.get(capability.capability_id)
        if spent is not None:
            if (spent.get("repository"), spent.get("ref"), spent.get("tip")) != (
                capability.repository,
                capability.ref,
                capability.live_tip,
            ):
                raise RuntimeError("reap capability redemption record does not match authority")
            if (
                spent.get("state") == "completed"
                and current.state == "completed"
                and remote_tip(repository_root, capability.ref, runner=runner) is None
            ):
                return current
            raise RuntimeError("reap capability has already been redeemed")
        if current.state != "verified":
            raise RuntimeError(f"reap journal requires reconciliation before apply: {current.state}")
        live_tip = remote_tip(repository_root, capability.ref, runner=runner)
        if live_tip != capability.live_tip:
            raise RuntimeError("live ref tip does not match the capability")

        redemptions[capability.capability_id] = {
            "repository": capability.repository,
            "ref": capability.ref,
            "tip": capability.live_tip,
            # ``apply_capability`` has verified the HMAC and its exact plan before
            # this keeper-owned record is written.  Persist the authenticated
            # capability/origin binding so a later crash reconciler never has to
            # trust fields supplied by an unverified capability document.
            "capability_digest": canonical_digest(capability),
            "remote_url_digest": capability.remote_url_digest,
            "state": "applying",
        }
        atomic_json(redemption_path, redemptions)
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
            redemptions[capability.capability_id]["state"] = "crashed"
            atomic_json(redemption_path, redemptions)
            crashed = journal(
                capability=capability,
                state="crashed",
                detail=str(exc),
                observed_at=utc_now(),
            )
            atomic_json(journal_path, crashed.model_dump(mode="json"))
            raise
        redemptions[capability.capability_id]["state"] = "completed"
        atomic_json(redemption_path, redemptions)
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
    capability: ReapCapabilityV1,
    redemption_path: Path,
    observed_at: datetime | None = None,
    runner: Runner = subprocess.run,
) -> ReapJournalV1:
    """Classify an interrupted effect from its authenticated redemption binding.

    Reconciliation deliberately does not mint or consume authority.  The
    capability is instead matched byte-for-byte (minus its signature field, as
    defined by :func:`canonical_digest`) to the binding persisted only after the
    original HMAC/plan verification succeeded.  Old or incomplete redemption
    rows fail closed and require a fresh owner-reviewed plan.
    """

    _journal_matches(current, capability)
    if current.state not in {"applying", "crashed"}:
        return current
    observed_at = (observed_at or utc_now()).astimezone(UTC)
    with locked_redemptions(redemption_path) as redemptions:
        spent = redemptions.get(capability.capability_id)
        if spent is None:
            raise RuntimeError("reap capability redemption record is missing")
        if (spent.get("repository"), spent.get("ref"), spent.get("tip")) != (
            capability.repository,
            capability.ref,
            capability.live_tip,
        ):
            raise RuntimeError("reap capability redemption record does not match authority")
        authenticated_digest = spent.get("capability_digest")
        authenticated_origin = spent.get("remote_url_digest")
        if not isinstance(authenticated_digest, str) or not isinstance(authenticated_origin, str):
            raise RuntimeError("reap capability redemption record lacks authenticated origin binding")
        if authenticated_digest != canonical_digest(capability):
            raise RuntimeError("reap capability does not match its authenticated redemption binding")
        if remote_url_digest(repository_root, runner=runner) != authenticated_origin:
            raise RuntimeError("repository origin does not match the authenticated redemption binding")
        tip = remote_tip(repository_root, current.ref, runner=runner)
        if tip is None:
            result = current.model_copy(
                update={
                    "state": "completed",
                    "updated_at": observed_at,
                    "detail": "reconciled: remote ref is absent",
                }
            )
        elif tip == current.expected_tip:
            result = current.model_copy(
                update={
                    "state": "crashed",
                    "updated_at": observed_at,
                    "detail": "reconciled: expected ref still exists; same capability requires owner review",
                }
            )
        else:
            result = current.model_copy(
                update={
                    "state": "crashed",
                    "updated_at": observed_at,
                    "detail": "reconciled: ref advanced; deletion denied and successor owner required",
                }
            )
        spent["state"] = result.state
        atomic_json(redemption_path, redemptions)
    return result
