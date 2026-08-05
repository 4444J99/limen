"""Finite orchestration of one campaign-relay launch and successor handoff."""

from __future__ import annotations

import os
import selectors
import subprocess
import threading
import time
from collections.abc import Callable
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from limen.conduct.campaign_relay import (
    _CONTROL_LINE_CEILING,
    _CONTROL_TOTAL_CEILING,
    _EXEC_HANDOFF_BUDGET_SECONDS,
    _STARTUP_TIMEOUT_SECONDS,
    _TERMINAL_STATES,
    CampaignRelayError,
    ReadyRelayCapsule,
    RelayLaunch,
    _capsule_remote_ref,
    _deadline_timeout,
    _git,
    _latest_remote_ref,
    _open_store,
    _primary_checkout,
    _read_receipt,
    _ready_remote_ref,
    _relay_names,
    _relay_worktree,
)
from limen.conduct.campaign_relay_process import (
    _acknowledge_relay,
    _activation_registration_lock,
    _bounded_registration,
    _BoundedStreamDigest,
    _clear_activation_marker,
    _finish_drains,
    _live_relay_lanes,
    _process_start_identity,
    _reap_relay_process,
    _spawn_relay_process,
    _startup_evidence,
    _terminalize_relay,
    _validate_control_event,
    _write_activation_marker,
)
from limen.conduct.campaign_relay_publication import (
    _capsule_receipt_path,
    _load_remote_attempt,
    _load_remote_ready,
    _publication_payload,
    _publish_ready_receipt,
    _publish_remote_attempt,
    _recover_remote_ready,
)
from limen.conduct.campaign_relay_state import (
    _adopt_remote_base,
    _adopt_remote_relay,
    _claim_relay_attempt,
    _read_relay,
    _replace_relay,
    _same_relay_identity,
    _same_relay_lineage,
)
from limen.conduct.models import CampaignRelayReceiptV1


def _reconcile_consumed_attempt(
    root: Path,
    receipt: CampaignRelayReceiptV1,
    *,
    process_identity: Callable[[int], str],
    registration: Callable[..., tuple[str, int]],
    deadline_monotonic: float | None = None,
) -> RelayLaunch:
    if receipt.state == "ready":
        return RelayLaunch(receipt=receipt, launched=False)
    recovered = _recover_remote_ready(
        root,
        receipt,
        deadline_monotonic=deadline_monotonic,
    )
    if recovered is not None:
        updates = recovered.model_dump(mode="json")
        ready = _replace_relay(
            root,
            receipt.relay_id,
            expected_states=frozenset({"launching", "registered", "published", "failed", "indeterminate"}),
            updates=updates,
            deadline_monotonic=deadline_monotonic,
        )
        return RelayLaunch(receipt=ready, launched=False)
    if receipt.state == "indeterminate" and receipt.terminal_code == "relay_ready_publication_uncertain":
        provider_alive = False
        if receipt.launch_pid is not None and receipt.launch_process_started is not None:
            try:
                provider_alive = process_identity(receipt.launch_pid) == receipt.launch_process_started
            except CampaignRelayError:
                provider_alive = False
        failure_code = "relay_ready_provider_absent"
        if provider_alive:
            prospective = CampaignRelayReceiptV1.model_validate(
                {
                    **receipt.model_dump(mode="json"),
                    "state": "ready",
                    "terminal_code": None,
                }
            )
            try:
                _publish_ready_receipt(
                    root,
                    prospective,
                    deadline_monotonic=deadline_monotonic,
                )
            except CampaignRelayError as exc:
                if exc.code == "relay_ready_publication_uncertain":
                    return RelayLaunch(receipt=receipt, launched=False)
                failure_code = exc.code
            else:
                ready = _replace_relay(
                    root,
                    receipt.relay_id,
                    expected_states=frozenset({"indeterminate"}),
                    updates=prospective.model_dump(mode="json"),
                    deadline_monotonic=deadline_monotonic,
                )
                return RelayLaunch(receipt=ready, launched=False)

        rollback_ok = receipt.selected_agent is not None and bool(receipt.selected_capabilities)
        if rollback_ok:
            worktree = _relay_worktree(
                root,
                receipt.successor_slug,
                deadline_monotonic=deadline_monotonic,
            )
            env = dict(os.environ)
            for key in (
                "LIMEN_HUMAN_PROTECTED",
                "LIMEN_NATIVE_RUN_ID",
                "LIMEN_NATIVE_SESSION_ID",
                "LIMEN_PROVIDER_IDENTITY",
                "LIMEN_RUN_ID",
            ):
                env.pop(key, None)
            try:
                with _activation_registration_lock(
                    worktree,
                    deadline_monotonic=deadline_monotonic,
                ):
                    _clear_activation_marker(worktree, receipt.relay_id)
                    registration(
                        root=root,
                        env=env,
                        agent=receipt.selected_agent,
                        capabilities=receipt.selected_capabilities,
                        session_id=receipt.successor_session_id,
                        worktree=worktree,
                        accepting_work=False,
                        deadline_monotonic=deadline_monotonic,
                    )
            except CampaignRelayError:
                rollback_ok = False
        terminal_code = failure_code if rollback_ok else "relay_activation_rollback_failed"
        terminal = _replace_relay(
            root,
            receipt.relay_id,
            expected_states=frozenset({"indeterminate"}),
            updates={
                "activation_response_sha256": (None if rollback_ok else receipt.activation_response_sha256),
                "terminal_code": terminal_code,
            },
            deadline_monotonic=deadline_monotonic,
        )
        return RelayLaunch(receipt=terminal, launched=False)
    if receipt.state in _TERMINAL_STATES:
        return RelayLaunch(receipt=receipt, launched=False)
    controller_alive = False
    if receipt.controller_pid is not None and receipt.controller_process_started is not None:
        try:
            controller_alive = process_identity(receipt.controller_pid) == receipt.controller_process_started
        except CampaignRelayError:
            controller_alive = False
    if controller_alive:
        return RelayLaunch(receipt=receipt, launched=False)
    empty_stdout = _BoundedStreamDigest()
    empty_stderr = _BoundedStreamDigest()
    terminal = _terminalize_relay(
        root,
        receipt.relay_id,
        state="indeterminate",
        code="relay_controller_interrupted",
        stdout=empty_stdout,
        stderr=empty_stderr,
        deadline_monotonic=deadline_monotonic,
    )
    return RelayLaunch(receipt=terminal, launched=False)


def launch_reserved_relay(
    root: Path,
    relay_id: str,
    *,
    timeout_seconds: float = _STARTUP_TIMEOUT_SECONDS,
    process_factory: Callable[..., subprocess.Popen[bytes]] = _spawn_relay_process,
    process_identity: Callable[[int], str] = _process_start_identity,
    lane_selector: Callable[[Path], tuple[str, ...]] = _live_relay_lanes,
    registration: Callable[..., tuple[str, int]] = _bounded_registration,
) -> RelayLaunch:
    """Consume the sole relay attempt and prove the provider's final exec boundary."""

    startup_started = time.monotonic()
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not 1 <= timeout_seconds <= 900
    ):
        raise CampaignRelayError(
            "relay_timeout_invalid",
            "campaign relay startup timeout must be between 1 and 900 seconds",
        )
    deadline = startup_started + float(timeout_seconds)
    root = root.resolve()
    primary_root = _primary_checkout(
        root,
        deadline_monotonic=deadline,
    )
    existing = _read_relay(
        root,
        relay_id,
        deadline_monotonic=deadline,
    )
    if existing.state != "reserved":
        return _reconcile_consumed_attempt(
            root,
            existing,
            process_identity=process_identity,
            registration=registration,
            deadline_monotonic=deadline,
        )
    recovered_ready = _recover_remote_ready(
        root,
        existing,
        allow_base_adoption=True,
        deadline_monotonic=deadline,
    )
    if recovered_ready is not None:
        ready = _adopt_remote_relay(
            root,
            relay_id,
            expected_states=frozenset({"reserved"}),
            remote=recovered_ready,
            deadline_monotonic=deadline,
        )
        return RelayLaunch(receipt=ready, launched=False)
    remote_attempt = _load_remote_attempt(
        root,
        existing,
        allow_base_adoption=True,
        deadline_monotonic=deadline,
    )
    if remote_attempt is not None:
        if remote_attempt.exact_remote_main != existing.exact_remote_main:
            existing = _adopt_remote_base(
                root,
                relay_id,
                exact_remote_main=remote_attempt.exact_remote_main,
                deadline_monotonic=deadline,
            )
        claim = _claim_relay_attempt(
            root,
            relay_id,
            controller_pid=remote_attempt.controller_pid,
            controller_process_started=remote_attempt.controller_process_started,
            remote_attempt_commit=remote_attempt.commit,
            remote_attempt_token=remote_attempt.token,
            deadline_monotonic=deadline,
        )
        if not claim.launched:
            return _reconcile_consumed_attempt(
                root,
                claim.receipt,
                process_identity=process_identity,
                registration=registration,
                deadline_monotonic=deadline,
            )
        return _reconcile_consumed_attempt(
            root,
            claim.receipt,
            process_identity=process_identity,
            registration=registration,
            deadline_monotonic=deadline,
        )
    _deadline_timeout(deadline, float(timeout_seconds))
    live_lanes = lane_selector(root)
    _deadline_timeout(deadline, float(timeout_seconds))
    if (
        not live_lanes
        or len(live_lanes) != len(set(live_lanes))
        or any(not isinstance(lane, str) or not lane for lane in live_lanes)
    ):
        raise CampaignRelayError(
            "relay_capacity_unavailable",
            "live provider capacity returned no unique eligible lanes",
        )
    controller_started = process_identity(os.getpid())
    _deadline_timeout(deadline, float(timeout_seconds))
    claim = _claim_relay_attempt(
        root,
        relay_id,
        controller_pid=os.getpid(),
        controller_process_started=controller_started,
        deadline_monotonic=deadline,
    )
    if not claim.launched:
        return _reconcile_consumed_attempt(
            root,
            claim.receipt,
            process_identity=process_identity,
            registration=registration,
            deadline_monotonic=deadline,
        )
    try:
        published_attempt = _publish_remote_attempt(
            root,
            claim.receipt,
            controller_pid=os.getpid(),
            controller_process_started=controller_started,
            deadline_monotonic=deadline,
        )
        receipt = _replace_relay(
            root,
            relay_id,
            expected_states=frozenset({"launching"}),
            updates={
                "controller_pid": published_attempt.controller_pid,
                "controller_process_started": published_attempt.controller_process_started,
                "remote_attempt_commit": published_attempt.commit,
                "remote_attempt_token": published_attempt.token,
            },
            deadline_monotonic=deadline,
        )
    except CampaignRelayError as exc:
        terminal = _terminalize_relay(
            root,
            relay_id,
            state="indeterminate",
            code=exc.code,
            stdout=_BoundedStreamDigest(),
            stderr=_BoundedStreamDigest(),
            deadline_monotonic=deadline,
        )
        return RelayLaunch(receipt=terminal, launched=False)
    if not published_attempt.won:
        return _reconcile_consumed_attempt(
            root,
            receipt,
            process_identity=process_identity,
            registration=registration,
            deadline_monotonic=deadline,
        )
    try:
        _deadline_timeout(deadline, float(timeout_seconds))
    except CampaignRelayError as exc:
        terminal = _terminalize_relay(
            root,
            relay_id,
            state="indeterminate",
            code=exc.code,
            stdout=_BoundedStreamDigest(),
            stderr=_BoundedStreamDigest(),
            deadline_monotonic=deadline,
        )
        return RelayLaunch(receipt=terminal, launched=False)
    control_reader, control_writer = os.pipe()
    exec_reader, exec_writer = os.pipe()
    ack_reader, ack_writer = os.pipe()
    os.set_inheritable(control_writer, True)
    os.set_inheritable(exec_writer, True)
    os.set_inheritable(ack_reader, True)
    ack_writer_open = True
    env = dict(os.environ)
    for key in (
        "LIMEN_HUMAN_PROTECTED",
        "LIMEN_NATIVE_RUN_ID",
        "LIMEN_NATIVE_SESSION_ID",
        "LIMEN_PROVIDER_IDENTITY",
        "LIMEN_RUN_ID",
    ):
        env.pop(key, None)
    env.update(
        {
            "LIMEN_CAMPAIGN_RELAY_BASE": receipt.exact_remote_main,
            "LIMEN_CAMPAIGN_RELAY_ACK_FD": str(ack_reader),
            "LIMEN_CAMPAIGN_RELAY_CONTROL_FD": str(control_writer),
            "LIMEN_CAMPAIGN_RELAY_ELIGIBLE_LANES": ",".join(live_lanes),
            "LIMEN_CAMPAIGN_RELAY_EXEC_FD": str(exec_writer),
            "LIMEN_CAMPAIGN_RELAY_ID": receipt.relay_id,
            "LIMEN_WORKSTREAM_SESSION_ID": receipt.successor_session_id,
        }
    )
    command = [
        str(primary_root / "scripts" / "start-worktree-session.sh"),
        "--campaign-relay",
        receipt.relay_id,
        "--autonomous",
        "--agent",
        "auto",
        "--conduct",
        "--from",
        receipt.exact_remote_main,
        "--runway",
        "8h",
        "--workstream",
        receipt.workstream,
        str(primary_root),
        receipt.successor_slug,
    ]
    stdout_evidence = _BoundedStreamDigest()
    stderr_evidence = _BoundedStreamDigest()
    try:
        process = process_factory(
            command,
            root=primary_root,
            env=env,
            ack_descriptor=ack_reader,
            control_descriptor=control_writer,
            exec_descriptor=exec_writer,
        )
    except OSError:
        os.close(control_reader)
        os.close(control_writer)
        os.close(exec_reader)
        os.close(exec_writer)
        os.close(ack_reader)
        os.close(ack_writer)
        ack_writer_open = False
        terminal = _terminalize_relay(
            root,
            relay_id,
            state="failed",
            code="relay_spawn_failed",
            stdout=stdout_evidence,
            stderr=stderr_evidence,
            deadline_monotonic=deadline,
        )
        return RelayLaunch(receipt=terminal, launched=True)
    finally:
        if "process" in locals():
            os.close(ack_reader)
            os.close(control_writer)
            os.close(exec_writer)
    if process.stdout is None or process.stderr is None:
        os.close(control_reader)
        os.close(exec_reader)
        if ack_writer_open:
            os.close(ack_writer)
            ack_writer_open = False
        terminal = _terminalize_relay(
            root,
            relay_id,
            state="indeterminate",
            code="relay_startup_streams_missing",
            stdout=stdout_evidence,
            stderr=stderr_evidence,
            deadline_monotonic=deadline,
        )
        _reap_relay_process(process)
        return RelayLaunch(receipt=terminal, launched=True)
    try:
        started = process_identity(process.pid)
    except CampaignRelayError:
        os.close(control_reader)
        os.close(exec_reader)
        if ack_writer_open:
            os.close(ack_writer)
            ack_writer_open = False
        terminal = _terminalize_relay(
            root,
            relay_id,
            state="indeterminate",
            code="relay_process_identity_unavailable",
            stdout=stdout_evidence,
            stderr=stderr_evidence,
            deadline_monotonic=deadline,
        )
        _reap_relay_process(process)
        return RelayLaunch(receipt=terminal, launched=True)
    try:
        _replace_relay(
            root,
            relay_id,
            expected_states=frozenset({"launching"}),
            updates={
                "launch_pid": process.pid,
                "launch_process_started": started,
            },
            deadline_monotonic=deadline,
        )
    except CampaignRelayError as exc:
        os.close(control_reader)
        os.close(exec_reader)
        if ack_writer_open:
            os.close(ack_writer)
            ack_writer_open = False
        terminal = _terminalize_relay(
            root,
            relay_id,
            state="indeterminate",
            code=exc.code,
            stdout=stdout_evidence,
            stderr=stderr_evidence,
            deadline_monotonic=deadline,
        )
        _reap_relay_process(process)
        return RelayLaunch(receipt=terminal, launched=True)
    stdout_thread = threading.Thread(
        target=stdout_evidence.consume,
        args=(process.stdout,),
        daemon=True,
    )
    stderr_thread = threading.Thread(
        target=stderr_evidence.consume,
        args=(process.stderr,),
        daemon=True,
    )
    stdout_thread.start()
    stderr_thread.start()
    os.set_blocking(control_reader, False)
    os.set_blocking(exec_reader, False)
    selector = selectors.DefaultSelector()
    selector.register(control_reader, selectors.EVENT_READ, data="control")
    selector.register(exec_reader, selectors.EVENT_READ, data="exec")
    control_buffer = bytearray()
    control_total = 0
    exec_buffer = bytearray()
    expected_stage = "selected"
    exec_pending = False
    terminal_code: str | None = None
    terminal_state = "indeterminate"
    control_eof = False
    exec_eof = False
    selected_capabilities: tuple[str, ...] = ()
    worktree: Path | None = None
    activation_registration_guard = ExitStack()
    activation_registration_guard_held = False

    def startup_output_ceiling_crossed() -> bool:
        return stdout_evidence.output_ceiling_crossed() or stderr_evidence.output_ceiling_crossed()

    try:
        while not (control_eof and exec_eof):
            if startup_output_ceiling_crossed():
                terminal_code = "relay_startup_output_oversized"
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                if terminal_code is None:
                    terminal_code = "relay_startup_timeout"
                break
            events = selector.select(min(0.25, remaining))
            if not events:
                if process.poll() is not None:
                    terminal_code = "relay_process_exited_before_ready"
                    terminal_state = "failed"
                    break
                continue
            descriptor = events[0][0].fd
            channel = events[0][0].data
            try:
                chunk = os.read(descriptor, _CONTROL_LINE_CEILING)
            except BlockingIOError:
                continue
            if not chunk:
                if channel == "control":
                    control_eof = True
                    selector.unregister(control_reader)
                else:
                    exec_eof = True
                    selector.unregister(exec_reader)
                continue
            if channel == "exec":
                exec_buffer.extend(chunk)
                if len(exec_buffer) > _CONTROL_LINE_CEILING:
                    terminal_code = "relay_exec_status_oversized"
                    break
                if b"\n" in exec_buffer:
                    terminal_code = "relay_exec_failed"
                    terminal_state = "failed"
                    break
                continue
            control_total += len(chunk)
            if control_total > _CONTROL_TOTAL_CEILING:
                terminal_code = "relay_control_oversized"
                break
            control_buffer.extend(chunk)
            if len(control_buffer) > _CONTROL_LINE_CEILING and b"\n" not in control_buffer:
                terminal_code = "relay_control_oversized"
                break
            while b"\n" in control_buffer:
                line, _, remainder = control_buffer.partition(b"\n")
                control_buffer = bytearray(remainder)
                if terminal_code is not None:
                    continue
                try:
                    event = _validate_control_event(bytes(line), relay_id)
                    stage = event["stage"]
                    if stage != expected_stage:
                        raise CampaignRelayError(
                            "relay_control_order_invalid",
                            "campaign relay control events are out of order",
                        )
                    if stage == "selected":
                        if set(event) != {
                            "agent",
                            "capabilities",
                            "relay_id",
                            "schema",
                            "session_id",
                            "stage",
                        }:
                            raise CampaignRelayError(
                                "relay_registration_invalid",
                                "campaign relay registration proof is invalid",
                            )
                        capabilities = event.get("capabilities")
                        if (
                            event.get("session_id") != receipt.successor_session_id
                            or not isinstance(event.get("agent"), str)
                            or event["agent"] not in live_lanes
                            or not isinstance(capabilities, list)
                            or not capabilities
                            or any(not isinstance(capability, str) or not capability for capability in capabilities)
                            or capabilities != sorted(set(capabilities))
                        ):
                            raise CampaignRelayError(
                                "relay_registration_invalid",
                                "campaign relay registration proof is invalid",
                            )
                        selected_capabilities = tuple(capabilities)
                        worktree = _relay_worktree(
                            root,
                            receipt.successor_slug,
                            deadline_monotonic=deadline,
                        )
                        response_sha, _response_bytes = registration(
                            root=root,
                            env=env,
                            agent=event["agent"],
                            capabilities=selected_capabilities,
                            session_id=receipt.successor_session_id,
                            worktree=worktree,
                            accepting_work=False,
                            deadline_monotonic=deadline,
                        )
                        _replace_relay(
                            root,
                            relay_id,
                            expected_states=frozenset({"launching"}),
                            updates={
                                "state": "registered",
                                "selected_agent": event["agent"],
                                "selected_capabilities": selected_capabilities,
                                "registration_response_sha256": response_sha,
                            },
                            deadline_monotonic=deadline,
                        )
                        if startup_output_ceiling_crossed():
                            terminal_code = "relay_startup_output_oversized"
                        elif time.monotonic() >= deadline:
                            terminal_code = "relay_startup_timeout"
                        else:
                            _acknowledge_relay(ack_writer, b"registered\n")
                            expected_stage = "published"
                    elif stage == "published":
                        if set(event) != {
                            "branch",
                            "commit",
                            "parent",
                            "receipt_blob",
                            "receipt_path",
                            "receipt_ref",
                            "relay_id",
                            "schema",
                            "stage",
                        }:
                            raise CampaignRelayError(
                                "relay_publication_invalid",
                                "campaign relay publication proof is invalid",
                            )
                        if (
                            event.get("branch") != receipt.successor_branch
                            or event.get("receipt_path") != _capsule_receipt_path(receipt)
                            or event.get("receipt_ref") != _capsule_remote_ref(str(event.get("commit") or ""))
                        ):
                            raise CampaignRelayError(
                                "relay_publication_invalid",
                                "campaign relay publication proof is invalid",
                            )
                        publication_commit = str(event.get("commit") or "")
                        publication_parent = str(event.get("parent") or "")
                        publication_receipt_blob = str(event.get("receipt_blob") or "")
                        _publication_payload(
                            root,
                            receipt,
                            publication_commit=publication_commit,
                            publication_parent=publication_parent,
                            publication_receipt_blob=publication_receipt_blob,
                            deadline_monotonic=deadline,
                        )
                        _replace_relay(
                            root,
                            relay_id,
                            expected_states=frozenset({"registered"}),
                            updates={
                                "state": "published",
                                "publication_commit": publication_commit,
                                "publication_parent": publication_parent,
                                "publication_receipt_blob": publication_receipt_blob,
                            },
                            deadline_monotonic=deadline,
                        )
                        if startup_output_ceiling_crossed():
                            terminal_code = "relay_startup_output_oversized"
                        elif deadline - time.monotonic() < _EXEC_HANDOFF_BUDGET_SECONDS:
                            terminal_code = "relay_startup_timeout"
                        else:
                            if worktree is None:
                                raise CampaignRelayError(
                                    "relay_registration_invalid",
                                    "campaign relay worktree is unavailable before provider handoff",
                                )
                            activation_registration_guard.enter_context(
                                _activation_registration_lock(
                                    worktree,
                                    deadline_monotonic=deadline,
                                )
                            )
                            activation_registration_guard_held = True
                            _acknowledge_relay(ack_writer, b"launch\n")
                            os.close(ack_writer)
                            ack_writer_open = False
                            expected_stage = "exec_pending"
                    else:
                        if set(event) != {
                            "agent",
                            "pid",
                            "process_started",
                            "relay_id",
                            "schema",
                            "session_id",
                            "stage",
                        }:
                            raise CampaignRelayError(
                                "relay_exec_proof_invalid",
                                "campaign relay provider exec proof is invalid",
                            )
                        current = _read_relay(
                            root,
                            relay_id,
                            deadline_monotonic=deadline,
                        )
                        if (
                            current.state != "published"
                            or event.get("agent") != current.selected_agent
                            or event.get("session_id") != current.successor_session_id
                            or event.get("pid") != process.pid
                            or event.get("process_started") != started
                        ):
                            raise CampaignRelayError(
                                "relay_exec_proof_invalid",
                                "campaign relay provider exec proof is invalid",
                            )
                        exec_pending = True
                        expected_stage = "closed"
                except CampaignRelayError as exc:
                    terminal_code = exc.code
            if terminal_code is not None:
                break
        if terminal_code is not None and ack_writer_open:
            os.close(ack_writer)
            ack_writer_open = False
        if control_buffer and terminal_code is None:
            terminal_code = "relay_control_incomplete"
        if exec_buffer and terminal_code is None:
            terminal_code = "relay_exec_failed"
            terminal_state = "failed"
        drains_finished = (
            _finish_drains(
                (stdout_thread, stderr_thread),
                deadline=deadline,
            )
            if terminal_code is None
            else False
        )
        evidence = _startup_evidence(stdout_evidence, stderr_evidence)
        output_truncated = bool(evidence["startup_stdout_truncated"] or evidence["startup_stderr_truncated"])
        output_read_failed = stdout_evidence.read_failed() or stderr_evidence.read_failed()
        if terminal_code is None and startup_output_ceiling_crossed():
            terminal_code = "relay_startup_output_oversized"
        if (
            control_eof
            and exec_eof
            and exec_pending
            and terminal_code is None
            and not output_truncated
            and not output_read_failed
            and drains_finished
            and process.poll() is None
        ):
            try:
                observed_started = process_identity(process.pid)
            except CampaignRelayError:
                observed_started = ""
            if observed_started == started:
                current = _read_relay(
                    root,
                    relay_id,
                    deadline_monotonic=deadline,
                )
                if current.selected_agent is None or not selected_capabilities or worktree is None:
                    terminal_code = "relay_registration_invalid"
                else:
                    activation_applied = False
                    ready_published = False
                    try:
                        if not activation_registration_guard_held:
                            raise CampaignRelayError(
                                "relay_activation_lock_failed",
                                "campaign relay activation lock was not held across provider handoff",
                            )
                        activation_applied = True
                        _write_activation_marker(worktree, relay_id)
                        activation_sha, _activation_bytes = registration(
                            root=root,
                            env=env,
                            agent=current.selected_agent,
                            capabilities=selected_capabilities,
                            session_id=current.successor_session_id,
                            worktree=worktree,
                            accepting_work=True,
                            deadline_monotonic=deadline,
                        )
                        activated = _replace_relay(
                            root,
                            relay_id,
                            expected_states=frozenset({"published"}),
                            updates={
                                "activation_response_sha256": activation_sha,
                            },
                            deadline_monotonic=deadline,
                        )
                        if process.poll() is not None:
                            raise CampaignRelayError(
                                "relay_exec_identity_changed",
                                "campaign relay provider exited during activation",
                            )
                        try:
                            activated_started = process_identity(process.pid)
                        except CampaignRelayError as exc:
                            raise CampaignRelayError(
                                "relay_exec_identity_changed",
                                "campaign relay provider identity changed during activation",
                            ) from exc
                        if activated_started != started:
                            raise CampaignRelayError(
                                "relay_exec_identity_changed",
                                "campaign relay provider identity changed during activation",
                            )
                        activation_registration_guard.close()
                        activation_registration_guard_held = False
                        prospective = CampaignRelayReceiptV1.model_validate(
                            {
                                **activated.model_dump(mode="json"),
                                "state": "ready",
                                **evidence,
                            }
                        )
                        _publish_ready_receipt(
                            root,
                            prospective,
                            deadline_monotonic=deadline,
                        )
                        ready_published = True
                        ready = _replace_relay(
                            root,
                            relay_id,
                            expected_states=frozenset({"published"}),
                            updates={
                                "state": "ready",
                                **evidence,
                            },
                            deadline_monotonic=deadline,
                        )
                        return RelayLaunch(receipt=ready, launched=True)
                    except CampaignRelayError as exc:
                        terminal_code = exc.code
                        if (
                            activation_applied
                            and not ready_published
                            and terminal_code != "relay_ready_publication_uncertain"
                        ):
                            rollback_ok = True
                            try:
                                if activation_registration_guard_held:
                                    _clear_activation_marker(worktree, relay_id)
                                    registration(
                                        root=root,
                                        env=env,
                                        agent=current.selected_agent,
                                        capabilities=selected_capabilities,
                                        session_id=current.successor_session_id,
                                        worktree=worktree,
                                        accepting_work=False,
                                        deadline_monotonic=deadline,
                                    )
                                else:
                                    with _activation_registration_lock(
                                        worktree,
                                        deadline_monotonic=deadline,
                                    ):
                                        _clear_activation_marker(worktree, relay_id)
                                        registration(
                                            root=root,
                                            env=env,
                                            agent=current.selected_agent,
                                            capabilities=selected_capabilities,
                                            session_id=current.successor_session_id,
                                            worktree=worktree,
                                            accepting_work=False,
                                            deadline_monotonic=deadline,
                                        )
                            except CampaignRelayError:
                                rollback_ok = False
                            finally:
                                if activation_registration_guard_held:
                                    activation_registration_guard.close()
                                    activation_registration_guard_held = False
                            if rollback_ok:
                                try:
                                    _replace_relay(
                                        root,
                                        relay_id,
                                        expected_states=frozenset({"published"}),
                                        updates={"activation_response_sha256": None},
                                        deadline_monotonic=deadline,
                                    )
                                except CampaignRelayError:
                                    rollback_ok = False
                            if not rollback_ok:
                                terminal_code = "relay_activation_rollback_failed"
            else:
                terminal_code = "relay_exec_identity_changed"
        if activation_registration_guard_held:
            activation_registration_guard.close()
            activation_registration_guard_held = False
        if terminal_code is None:
            terminal_code = (
                "relay_startup_output_oversized"
                if output_truncated
                else (
                    "relay_startup_output_read_failed"
                    if output_read_failed
                    else ("relay_startup_output_incomplete" if not drains_finished else "relay_exec_not_proven")
                )
            )
        if process.poll() is not None and not exec_pending:
            terminal_state = "failed"
        terminal = _terminalize_relay(
            root,
            relay_id,
            state=terminal_state,
            code=terminal_code,
            stdout=stdout_evidence,
            stderr=stderr_evidence,
            deadline_monotonic=deadline,
        )
        return RelayLaunch(receipt=terminal, launched=True)
    finally:
        activation_registration_guard.close()
        selector.close()
        os.close(control_reader)
        os.close(exec_reader)
        if ack_writer_open:
            os.close(ack_writer)
        _reap_relay_process(process)


def discover_ready_relay(
    root: Path,
    *,
    workstream: str = "institutional-omega",
    now_epoch: int | None = None,
    deadline_monotonic: float | None = None,
) -> ReadyRelayCapsule:
    """Load the latest active ready successor without checking out its topic branch."""

    now = int(time.time()) if now_epoch is None else now_epoch
    latest_ref = _latest_remote_ref(workstream)
    rows = _git(
        root,
        "ls-remote",
        "origin",
        latest_ref,
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    if not rows:
        raise CampaignRelayError(
            "relay_successor_unavailable",
            "no active ready campaign successor has reached its handoff boundary",
        )
    fields = rows[0].split("\t") if len(rows) == 1 else []
    if len(fields) != 2 or fields[1] != latest_ref:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay latest-ready ref is malformed or ambiguous",
        )
    latest_commit = fields[0]
    receipt = _load_remote_ready(
        root,
        commit=latest_commit,
        relay_id=None,
        validate_publication=False,
        deadline_monotonic=deadline_monotonic,
    )
    ready_ref = _ready_remote_ref(receipt.relay_id)
    ready_rows = _git(
        root,
        "ls-remote",
        "origin",
        ready_ref,
        deadline_monotonic=deadline_monotonic,
    ).splitlines()
    ready_fields = ready_rows[0].split("\t") if len(ready_rows) == 1 else []
    if ready_fields != [latest_commit, ready_ref]:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay latest-ready ref is not held by its dedicated relay ref",
        )
    if receipt.workstream != workstream:
        raise CampaignRelayError(
            "relay_ready_invalid",
            "campaign relay latest-ready ref names a different workstream",
        )
    receipt_name, _lock_name = _relay_names(receipt.relay_id)
    with _open_store(root) as store:
        local_receipt = _read_receipt(store, receipt_name)
    if local_receipt is not None:
        if not _same_relay_identity(local_receipt, receipt) and not (
            local_receipt.state == "reserved" and _same_relay_lineage(local_receipt, receipt)
        ):
            raise CampaignRelayError(
                "relay_ready_invalid",
                "local and remote campaign relay identities disagree",
            )
        if local_receipt.state == "ready" and local_receipt != receipt:
            raise CampaignRelayError(
                "relay_ready_invalid",
                "local and remote campaign relay readiness receipts disagree",
            )
    if (
        receipt.predecessor_deadline_epoch > now
        or receipt.publication_commit is None
        or receipt.publication_parent is None
        or receipt.publication_receipt_blob is None
    ):
        raise CampaignRelayError(
            "relay_successor_unavailable",
            "no active ready campaign successor has reached its handoff boundary",
        )
    payload = _publication_payload(
        root,
        receipt,
        publication_commit=receipt.publication_commit,
        publication_parent=receipt.publication_parent,
        publication_receipt_blob=receipt.publication_receipt_blob,
        deadline_monotonic=deadline_monotonic,
    )
    deadline = int(payload["contract"]["runway"]["deadline_epoch"])
    if deadline <= now:
        raise CampaignRelayError(
            "relay_successor_unavailable",
            "no active ready campaign successor has reached its handoff boundary",
        )
    return ReadyRelayCapsule(
        receipt=receipt,
        capsule_path=_capsule_receipt_path(receipt),
        payload=payload,
        remaining_seconds=deadline - now,
    )


def relay_boundary_projection(receipt: CampaignRelayReceiptV1) -> dict[str, Any]:
    """Return the path-free lifecycle atom safe for heartbeat and owner receipts."""

    terminal = receipt.state in _TERMINAL_STATES
    return {
        "schema": "limen.campaign_relay_boundary.v1",
        "relay_id": receipt.relay_id,
        "state": receipt.state,
        "attempts": receipt.attempts,
        "terminal_code": receipt.terminal_code,
        "successor_session_id": receipt.successor_session_id,
        "workstream": receipt.workstream,
        "next_lifecycle_predicate": (
            "the admitted receipt commit remains held by its dedicated ref and reachable from the "
            "successor topic branch until the predecessor deadline"
            if receipt.state == "ready"
            else (
                "the consumed relay is terminal and cannot be retried; an owner must admit a new successor identity"
                if terminal
                else "one finite launch proves dormant broker registration, exact receipt "
                "publication, provider exec continuity, and post-exec activation without a "
                "duplicate spawn"
            )
        ),
    }
