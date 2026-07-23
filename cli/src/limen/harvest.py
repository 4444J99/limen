import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from limen.models import DispatchLogEntry, LimenFile, Task, dispatch_agent, dispatch_session_id
from limen.provider_selection import execution_profile_for
from limen.remote_execution import (
    ReceiptStore,
    RemoteExecutionError,
    RemoteLifecycle,
    RemoteReceipt,
    RemoteRun,
    RemoteState,
    discover_adapters,
    load_receipt,
    remote_request_from_task,
    verification_context_for_task,
)
from limen.tabularius import apply_limen_file_sync


def _get_jules_sessions(harvest_dir: Path) -> dict[str, str]:
    mapping = {}
    if harvest_dir.exists():
        for list_file in harvest_dir.glob(".list-*.txt"):
            try:
                for line in list_file.read_text().splitlines():
                    parts = line.split()
                    if not parts:
                        continue
                    session_id = parts[0]
                    if not session_id.isdigit():
                        continue
                    match = re.search(r"((?:LIMEN-\d+)|(?:GH-[A-Za-z0-9._-]+))", line)
                    if match:
                        mapping[match.group(1)] = session_id
            except Exception:
                pass
    try:
        result = subprocess.run(
            ["jules", "remote", "list", "--session"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                parts = line.split()
                if not parts:
                    continue
                session_id = parts[0]
                if not session_id.isdigit():
                    continue
                match = re.search(r"((?:LIMEN-\d+)|(?:GH-[A-Za-z0-9._-]+))", line)
                if match:
                    mapping[match.group(1)] = session_id
    except Exception:
        pass
    return mapping


def _diff_is_real(diff_text: str) -> bool:
    """True only if a harvested diff represents actual work.

    A jules result counts as 'done' only when a hand actually moved: a non-empty
    unified diff with real content changes. Rejects the empty placeholder (e.g. a
    ``patch.diff`` of ``index 0000000..e69de29`` with no hunks) and whitespace-only
    output. Exposed by the 2026-06-25 VIGILIA dispatch, where harvest marked tasks
    'done' the instant a ``.diff`` file existed — 'done' must mean done.
    """
    text = (diff_text or "").strip()
    if not text:
        return False
    if "diff --git" not in text and not text.lstrip().startswith("--- "):
        return False
    for line in text.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line[:1] in ("+", "-") and line[1:].strip():
            return True
        if line.startswith("Binary files") and line.rstrip().endswith("differ"):
            return True
    return False


def check_jules_harvest(limen: LimenFile, harvest_dir: Path) -> list[str]:
    updated: list[str] = []
    if not harvest_dir.exists():
        return updated

    session_mapping = _get_jules_sessions(harvest_dir)

    for task in limen.tasks:
        if task.status not in ("dispatched", "in_progress") or task.target_agent != "jules":
            continue
        # New submissions carry provider-neutral lifecycle metadata and are harvested below.  The
        # legacy Jules path may not mark those done from a bare diff.
        if any(entry.provider_run_id for entry in task.dispatch_log):
            continue

        session_id = session_mapping.get(task.id)
        if not session_id and task.dispatch_log:
            session_id = dispatch_session_id(task.dispatch_log[-1])

        if session_id:
            diff_file = harvest_dir / f"{session_id}.diff"
            if diff_file.exists():
                now = datetime.now(UTC)
                result = diff_file.read_text().strip()
                if not _diff_is_real(result):
                    # jules finished but produced nothing usable (empty/garbage
                    # diff). Do NOT mark done, and do NOT archive/cancel it:
                    # preserve the prompt-started work in the recovery lifecycle.
                    task.status = "failed"
                    if "noop" not in task.labels:
                        task.labels.append("noop")
                    task.updated = now
                    task.dispatch_log.append(
                        DispatchLogEntry(
                            timestamp=now,
                            agent="jules",
                            session_id=session_id,
                            status="failed",
                            output=result[:500],
                        )
                    )
                    print(f"  rejected {task.id}: jules diff empty/garbage — not 'done'")
                    continue
                task.status = "done"
                task.updated = now
                task.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now,
                        agent="jules",
                        session_id=session_id,
                        status="done",
                        output=result[:500],
                    )
                )
                updated.append(task.id)
                continue

        task_dir = harvest_dir / task.id
        if task_dir.exists() and (task_dir / "result.txt").exists():
            now = datetime.now(UTC)
            result = (task_dir / "result.txt").read_text().strip()
            if not result:
                # empty result file is not completion — don't false-done it.
                continue
            task.status = "done"
            task.updated = now
            task.dispatch_log.append(
                DispatchLogEntry(
                    timestamp=now,
                    agent="jules",
                    session_id=dispatch_session_id(task.dispatch_log[-1]) if task.dispatch_log else "harvest",
                    status="done",
                    output=result[:500],
                )
            )
            updated.append(task.id)
    return updated


def _remote_submission_entry(task: object) -> DispatchLogEntry | None:
    entries = getattr(task, "dispatch_log", None) or []
    if not entries:
        return None
    entry = entries[-1]
    if (
        entry.provider_run_id
        and entry.provider_url
        and entry.base_sha
        and entry.control_repo
        and entry.control_ref
        and entry.control_ref_kind
        and entry.control_sha
        and entry.workflow_id
        and entry.workflow_path
        and entry.workflow_event
        and entry.verification_context_digest
        and entry.remote_request_id
    ):
        return entry
    return None


def _remote_attempt_age(task: Task, request_id: str) -> float:
    timestamps = [
        entry.timestamp
        for entry in task.dispatch_log
        if entry.remote_request_id == request_id and entry.provider_run_id
    ]
    if not timestamps:
        return 0.0
    return max(0.0, (datetime.now(UTC) - min(timestamps)).total_seconds())


def _with_remote_state(run: RemoteRun, state: RemoteState, detail: str) -> RemoteRun:
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
        observed_at=datetime.now(UTC).isoformat(),
        detail=detail,
    )


def _remote_receipt_path(
    tasks_path: Path,
    store: ReceiptStore,
    task_id: str,
    value: str | None,
) -> Path | None:
    if not value:
        return None
    path = Path(value).expanduser()
    candidate = (path if path.is_absolute() else tasks_path.parent / path).resolve()
    expected_root = store.task_root(task_id).resolve()
    try:
        candidate.relative_to(expected_root)
    except ValueError as exc:
        raise RemoteExecutionError("remote receipt path escaped task-specific receipt custody") from exc
    if candidate.suffix != ".json":
        raise RemoteExecutionError("remote receipt path is not JSON")
    return candidate


def _adopt_orphan_remote_entry(
    task: Task,
    tasks_path: Path,
    store: ReceiptStore,
    tasks_by_id: dict[str, Task],
) -> DispatchLogEntry | None:
    """Adopt an intent persisted before a worker crashed prior to its board write."""

    for manifest, path in store.manifests_for_task(task.id):
        provider = str(manifest.get("provider") or "")
        base_sha = str(manifest.get("base_sha") or "")
        if provider != task.target_agent:
            continue
        try:
            raw_workflow_id = manifest.get("workflow_id")
            if isinstance(raw_workflow_id, bool) or not isinstance(raw_workflow_id, str | int):
                raise ValueError("stored workflow identity is invalid")
            verification_context = verification_context_for_task(task, tasks_by_id)
            request = remote_request_from_task(
                task,
                provider,
                base_sha=base_sha,
                control_repo=str(manifest.get("control_repo") or ""),
                control_ref=str(manifest.get("control_ref") or ""),
                control_ref_kind=str(manifest.get("control_ref_kind") or ""),
                control_sha=str(manifest.get("control_sha") or ""),
                workflow_id=int(raw_workflow_id),
                workflow_path=str(manifest.get("workflow_path") or ""),
                verification_context=verification_context,
                instruction=f"Verify completed implementation for task {task.id}; do not modify code: {task.title}",
                repo=str(task.repo or ""),
                execution_profile=execution_profile_for(task).as_dict(),
            )
            receipt = load_receipt(path, request)
        except (RemoteExecutionError, ValueError):
            # A changed task contract creates a new attempt and may never adopt an older packet.
            continue
        try:
            board_path = str(path.relative_to(tasks_path.parent))
        except ValueError:
            board_path = str(path)
        return DispatchLogEntry(
            timestamp=datetime.fromisoformat(receipt.run.observed_at),
            agent=provider,
            session_id=receipt.run.provider_run_id,
            status="dispatched",
            provider_run_id=receipt.run.provider_run_id,
            provider_url=receipt.run.url,
            base_sha=receipt.run.base_sha,
            control_repo=receipt.run.control_repo,
            control_ref=receipt.run.control_ref,
            control_ref_kind=receipt.run.control_ref_kind,
            control_sha=receipt.run.control_sha,
            workflow_id=receipt.run.workflow_id,
            workflow_path=receipt.run.workflow_path,
            workflow_event=receipt.run.workflow_event,
            verification_context_digest=receipt.run.verification_context_digest,
            remote_state=receipt.run.state.value,
            remote_request_id=receipt.run.request_id,
            remote_receipt=board_path,
            output="adopted content-addressed attempt after crash-before-board-write",
        )
    return None


def _record_remote_observation(
    task: Task,
    *,
    provider: str,
    status: str,
    run: RemoteRun,
    remote_state: str,
    receipt_path: str | None,
    output: str,
) -> bool:
    latest = (getattr(task, "dispatch_log", None) or [None])[-1]
    if (
        getattr(task, "status", None) == status
        and latest is not None
        and latest.status == status
        and latest.provider_run_id == run.provider_run_id
        and latest.provider_url == run.url
        and latest.base_sha == run.base_sha
        and latest.control_repo == run.control_repo
        and latest.control_ref == run.control_ref
        and latest.control_ref_kind == run.control_ref_kind
        and latest.control_sha == run.control_sha
        and latest.workflow_id == run.workflow_id
        and latest.workflow_path == run.workflow_path
        and latest.workflow_event == run.workflow_event
        and latest.verification_context_digest == run.verification_context_digest
        and latest.remote_state == remote_state
        and latest.remote_request_id == run.request_id
        and latest.remote_receipt == receipt_path
        and latest.output == output
    ):
        return False
    now = datetime.now(UTC)
    task.status = status
    task.updated = now
    task.dispatch_log.append(
        DispatchLogEntry(
            timestamp=now,
            agent=provider,
            session_id=run.provider_run_id,
            status=status,
            provider_run_id=run.provider_run_id,
            provider_url=run.url,
            base_sha=run.base_sha,
            control_repo=run.control_repo,
            control_ref=run.control_ref,
            control_ref_kind=run.control_ref_kind,
            control_sha=run.control_sha,
            workflow_id=run.workflow_id,
            workflow_path=run.workflow_path,
            workflow_event=run.workflow_event,
            verification_context_digest=run.verification_context_digest,
            remote_state=remote_state,
            remote_request_id=run.request_id,
            remote_receipt=receipt_path,
            output=output,
        )
    )
    return True


def check_remote_harvest(
    limen: LimenFile,
    tasks_path: Path,
    *,
    agent: str | None = None,
) -> list[str]:
    """Harvest provider-neutral remote runs without treating acknowledgements as completion."""

    adapters, _capabilities = discover_adapters()
    receipt_root = Path(
        os.environ.get("LIMEN_REMOTE_RECEIPT_ROOT", str(tasks_path.parent / "logs" / "remote-execution"))
    ).expanduser()
    store = ReceiptStore(receipt_root)
    updated: list[str] = []
    tasks_by_id = {item.id: item for item in limen.tasks}
    for task in limen.tasks:
        if task.status not in {"dispatched", "in_progress"}:
            continue
        entry = _remote_submission_entry(task)
        if entry is None:
            if any(item.remote_request_id for item in task.dispatch_log):
                # A newer head supersedes every historical remote attempt. Never search backward
                # and let an old successful run close a later dispatch.
                continue
            try:
                entry = _adopt_orphan_remote_entry(task, tasks_path, store, tasks_by_id)
            except RemoteExecutionError as exc:
                now = datetime.now(UTC)
                task.status = "failed_blocked"
                task.updated = now
                task.dispatch_log.append(
                    DispatchLogEntry(
                        timestamp=now,
                        agent=task.target_agent,
                        session_id="remote-receipt-custody-blocked",
                        status="failed_blocked",
                        output=f"remote receipt custody blocked: {str(exc)[:240]}",
                    )
                )
                updated.append(task.id)
                continue
            if entry is None:
                continue
        provider = dispatch_agent(entry)
        if agent and provider != agent:
            continue
        adapter = adapters.get(provider)
        if adapter is None:
            run = RemoteRun(
                provider=provider,
                provider_run_id=str(entry.provider_run_id),
                url=str(entry.provider_url),
                base_sha=str(entry.base_sha),
                control_repo=str(entry.control_repo),
                control_ref=str(entry.control_ref),
                control_ref_kind=str(entry.control_ref_kind),
                control_sha=str(entry.control_sha),
                workflow_id=int(entry.workflow_id or 0),
                workflow_path=str(entry.workflow_path),
                workflow_event=str(entry.workflow_event),
                verification_context_digest=str(entry.verification_context_digest),
                state=RemoteState.BLOCKED,
                request_id=str(entry.remote_request_id),
                observed_at=entry.timestamp.isoformat(),
                detail="live adapter unavailable during harvest",
            )
            if _record_remote_observation(
                task,
                provider=provider,
                status="failed_blocked",
                run=run,
                remote_state=RemoteState.BLOCKED.value,
                receipt_path=entry.remote_receipt,
                output="remote lifecycle blocked: live authenticated adapter/workflow unavailable",
            ):
                updated.append(task.id)
            continue
        try:
            verification_context = verification_context_for_task(task, tasks_by_id)
            request = remote_request_from_task(
                task,
                provider,
                base_sha=str(entry.base_sha),
                control_repo=str(entry.control_repo),
                control_ref=str(entry.control_ref),
                control_ref_kind=str(entry.control_ref_kind),
                control_sha=str(entry.control_sha),
                workflow_id=int(entry.workflow_id or 0),
                workflow_path=str(entry.workflow_path),
                verification_context=verification_context,
                instruction=f"Verify completed implementation for task {task.id}; do not modify code: {task.title}",
                repo=str(task.repo or ""),
                execution_profile=execution_profile_for(task).as_dict(),
            )
            stored = _remote_receipt_path(tasks_path, store, task.id, entry.remote_receipt)
            stored_receipt = None
            if stored is not None:
                if not stored.exists():
                    raise RemoteExecutionError("board-named remote receipt is missing")
                stored_receipt = load_receipt(stored, request)
            if stored_receipt is not None:
                run = stored_receipt.run
                if (
                    run.provider_run_id != entry.provider_run_id
                    or run.url != entry.provider_url
                    or run.control_repo != entry.control_repo
                    or run.control_ref != entry.control_ref
                    or run.control_ref_kind != entry.control_ref_kind
                    or run.control_sha != entry.control_sha
                    or run.workflow_id != entry.workflow_id
                    or run.workflow_path != entry.workflow_path
                    or run.workflow_event != entry.workflow_event
                    or run.verification_context_digest != entry.verification_context_digest
                    or run.request_id != entry.remote_request_id
                ):
                    raise RemoteExecutionError("board attempt identity does not match its stored receipt")
            else:
                run = RemoteRun(
                    provider=provider,
                    provider_run_id=str(entry.provider_run_id),
                    url=str(entry.provider_url),
                    base_sha=str(entry.base_sha),
                    control_repo=str(entry.control_repo),
                    control_ref=str(entry.control_ref),
                    control_ref_kind=str(entry.control_ref_kind),
                    control_sha=str(entry.control_sha),
                    workflow_id=int(entry.workflow_id or 0),
                    workflow_path=str(entry.workflow_path),
                    workflow_event=str(entry.workflow_event),
                    verification_context_digest=str(entry.verification_context_digest),
                    state=RemoteState(str(entry.remote_state or "submitted")),
                    request_id=str(entry.remote_request_id),
                    observed_at=entry.timestamp.isoformat(),
                )
            lifecycle = RemoteLifecycle(adapter, store)
            observed, receipt_path = lifecycle.probe(request, run)
            attempt_age = _remote_attempt_age(task, observed.request_id)
            if observed.pending_identity and observed.state is RemoteState.SUBMITTED and attempt_age >= 900:
                observed = _with_remote_state(
                    observed,
                    RemoteState.ABSENT,
                    "exhaustive catalog confirms no run after 15-minute materialization bound",
                )
                receipt_path = store.write(
                    RemoteReceipt(
                        request,
                        observed,
                        observed.state,
                        observed_at=observed.observed_at,
                        detail=observed.detail,
                    )
                )
            elif observed.state is RemoteState.UNKNOWN and attempt_age >= 900:
                observed = _with_remote_state(
                    observed,
                    RemoteState.BLOCKED,
                    "provider status remained unreachable for 15 minutes",
                )
                receipt_path = store.write(
                    RemoteReceipt(
                        request,
                        observed,
                        observed.state,
                        observed_at=observed.observed_at,
                        detail=observed.detail,
                    )
                )
            elif observed.state in {RemoteState.UNKNOWN, RemoteState.ABSENT} or (
                observed.pending_identity and observed.state is RemoteState.SUBMITTED
            ):
                observed, receipt_path = lifecycle.recover(request, observed)
            if observed.state is RemoteState.SUCCEEDED:
                receipt, receipt_path = lifecycle.harvest(request, observed)
            else:
                receipt = RemoteReceipt(
                    request,
                    observed,
                    observed.state,
                    observed_at=observed.observed_at,
                    detail=observed.detail,
                )
                receipt_path = store.write(receipt)
        except (RemoteExecutionError, ValueError, OSError) as exc:
            detail = f"remote harvest contract blocked: {str(exc)[:240]}"
            blocked = RemoteRun(
                provider=provider,
                provider_run_id=str(entry.provider_run_id),
                url=str(entry.provider_url),
                base_sha=str(entry.base_sha),
                control_repo=str(entry.control_repo),
                control_ref=str(entry.control_ref),
                control_ref_kind=str(entry.control_ref_kind),
                control_sha=str(entry.control_sha),
                workflow_id=int(entry.workflow_id or 0),
                workflow_path=str(entry.workflow_path),
                workflow_event=str(entry.workflow_event),
                verification_context_digest=str(entry.verification_context_digest),
                state=RemoteState.BLOCKED,
                request_id=str(entry.remote_request_id),
                observed_at=entry.timestamp.isoformat(),
                detail=detail,
            )
            if _record_remote_observation(
                task,
                provider=provider,
                status="failed_blocked",
                run=blocked,
                remote_state=RemoteState.BLOCKED.value,
                receipt_path=entry.remote_receipt,
                output=detail,
            ):
                updated.append(task.id)
            print(f"  remote harvest blocked {task.id}: {str(exc)[:240]}")
            continue

        if receipt.done:
            status = "done"
        elif receipt.state in {RemoteState.FAILED, RemoteState.ABSENT}:
            status = "failed"
        elif receipt.state is RemoteState.BLOCKED or receipt.state is RemoteState.SUCCEEDED:
            status = "failed_blocked"
        else:
            status = "in_progress"
        try:
            board_receipt = str(receipt_path.relative_to(tasks_path.parent))
        except ValueError:
            board_receipt = str(receipt_path)
        output = (
            f"remote lifecycle: {receipt.detail}; predicate="
            f"{'pass' if receipt.predicate and receipt.predicate.passed else 'not-proven'}; "
            f"outputs={len(receipt.outputs)}; done={str(receipt.done).lower()}"
        )
        if _record_remote_observation(
            task,
            provider=provider,
            status=status,
            run=receipt.run,
            remote_state=receipt.state.value,
            receipt_path=board_receipt,
            output=output,
        ):
            updated.append(task.id)
    return updated


def harvest_results(
    limen: LimenFile,
    tasks_path: Path,
    agent: str | None = None,
) -> None:
    scheduler_root = Path.home() / "Workspace" / "session-meta" / "scheduler"
    harvest_dir = scheduler_root / "jules" / "harvest"

    updated = []

    if not agent or agent == "jules":
        updated.extend(check_jules_harvest(limen, harvest_dir))
    updated.extend(check_remote_harvest(limen, tasks_path, agent=agent))

    if updated:
        apply_limen_file_sync(tasks_path, limen, agent=agent or "harvest", session_id="harvest")
        print(f"Harvested {len(updated)} task(s): {', '.join(updated)}")
    else:
        print("No completed tasks to harvest")
