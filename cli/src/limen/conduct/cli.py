"""Click command surface for the shared conduct protocol."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Literal

import click

from limen.conduct.broker import ConductError
from limen.conduct.canary import run_full_mesh_canary
from limen.conduct.canary_executor import (
    executor_client_from_environ,
    execute_native_canary_edge,
    read_native_canary_request,
)
from limen.conduct.campaign_relay import CampaignRelayError
from limen.conduct.client import client_from_env
from limen.conduct.liveness import foreign_worktree_occupant
from limen.conduct.models import AgentIdentityV1, ConductorSessionV1, RunReceiptV1, WorkPacketV1
from limen.conduct.supervisor import RESULT_SCHEMA, CampaignSupervisorError, run_campaign


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise click.ClickException(f"cannot read JSON packet {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise click.ClickException(f"JSON packet must contain an object: {path}")
    return payload


def _emit(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, indent=2, sort_keys=True))


def _bounded_canary_error(exc: ConductError | ValueError | OSError) -> str:
    detail = " ".join(str(exc).split()) or "conduct canary failed"
    limit = 1024
    return detail if len(detail) <= limit else f"{detail[: limit - 3]}..."


def _session_id(explicit: str | None) -> str:
    value = explicit or os.environ.get("LIMEN_SESSION_ID") or os.environ.get("LIMEN_RUN_ID")
    if not value:
        raise click.ClickException("session identity is required via --session-id or LIMEN_SESSION_ID")
    return value


def _lease_token(env_name: str) -> str:
    token = os.environ.get(env_name, "")
    if not token:
        raise click.ClickException(f"lease capability token is required in {env_name}")
    return token


def _profile_defaults(agent: str) -> dict[str, Any]:
    try:
        from limen.census import execution_profiles

        profile = execution_profiles().get(agent)
    except (ImportError, KeyError, TypeError):
        profile = None
    if profile is None:
        return {}
    return {
        "capabilities": profile.capabilities,
        "transport": profile.transport,
        "native_fanout": profile.native_fanout,
        "harvest_method": profile.harvest_method,
        "meter": profile.meter_ref,
    }


@click.group("conduct")
def conduct_group() -> None:
    """Submit, split, observe, and harvest bounded peer work."""


@conduct_group.command("capabilities")
def capabilities() -> None:
    _emit(client_from_env().capabilities())


@conduct_group.group("canary")
def canary_group() -> None:
    """Run bounded authenticated conduct canaries."""


@canary_group.command("full-mesh")
@click.option("--receipt", "receipt_path", required=True, type=click.Path(path_type=Path))
def canary_full_mesh(receipt_path: Path) -> None:
    """Exercise every ordered edge in the live native conduct mesh."""

    try:
        result = run_full_mesh_canary(
            client=client_from_env(),
            receipt_path=receipt_path,
        )
    except (ConductError, ValueError, OSError) as exc:
        raise click.ClickException(_bounded_canary_error(exc)) from exc
    _emit(result)


@canary_group.command("executor-edge", hidden=True)
def canary_executor_edge() -> None:
    """Execute one canary edge inside its already-running native session."""

    try:
        request = read_native_canary_request(sys.stdin.buffer)
        acknowledgement = execute_native_canary_edge(
            request,
            client=executor_client_from_environ(request, os.environ),
            environ=os.environ,
        )
    except (ConductError, ValueError, OSError) as exc:
        raise click.ClickException(_bounded_canary_error(exc)) from exc
    _emit(acknowledgement.to_payload())


@conduct_group.group("campaign")
def campaign_group() -> None:
    """Evaluate and route one finite institutional campaign epoch."""


@campaign_group.command("run")
@click.option("--capsule", type=click.Path(path_type=Path, exists=True))
@click.option("--capsule-commit", default=None)
@click.option("--capsule-base", default=None)
@click.option("--capsule-path", default=None)
@click.option("--capsule-branch", default=None)
@click.option("--terminal-predicate", type=click.Choice(["omega"]), default="omega", show_default=True)
@click.option("--session-id", default=None)
@click.option("--agent", default=lambda: os.environ.get("LIMEN_AGENT"))
@click.option("--evaluation-timeout", type=click.IntRange(300, 7200), default=1800, show_default=True)
@click.option("--wake-deadline-monotonic-ns", type=click.IntRange(min=1), default=None, hidden=True)
def campaign_run(
    capsule: Path | None,
    capsule_commit: str | None,
    capsule_base: str | None,
    capsule_path: str | None,
    capsule_branch: str | None,
    terminal_predicate: str,
    session_id: str | None,
    agent: str | None,
    evaluation_timeout: int,
    wake_deadline_monotonic_ns: int | None,
) -> None:
    if not agent:
        raise click.ClickException("agent identity is required via --agent or LIMEN_AGENT")
    identity = AgentIdentityV1(
        agent=agent,
        surface=os.environ.get("LIMEN_SURFACE", "workstream"),
        session_id=_session_id(session_id),
        native_run_id=os.environ.get("LIMEN_NATIVE_RUN_ID"),
        provider_identity=os.environ.get("LIMEN_PROVIDER_IDENTITY"),
    )
    try:
        result = run_campaign(
            client=client_from_env(),
            root=Path.cwd(),
            capsule=capsule,
            capsule_commit=capsule_commit,
            capsule_base=capsule_base,
            capsule_path=capsule_path,
            capsule_branch=capsule_branch,
            identity=identity,
            terminal_predicate=terminal_predicate,
            evaluation_timeout_seconds=evaluation_timeout,
            wake_deadline_monotonic_ns=wake_deadline_monotonic_ns,
        )
    except CampaignRelayError as exc:
        _emit(
            {
                "schema": RESULT_SCHEMA,
                "boundary": "invalid",
                "reason": exc.public_reason,
                "successor_required": True,
                "terminal_predicate": terminal_predicate,
            }
        )
        raise click.exceptions.Exit(1) from exc
    except (CampaignSupervisorError, ConductError) as exc:
        _emit(
            {
                "schema": RESULT_SCHEMA,
                "boundary": "invalid",
                "reason": str(exc)[:2000],
                "successor_required": False,
                "terminal_predicate": terminal_predicate,
            }
        )
        raise click.exceptions.Exit(1) from exc
    _emit(result)


@conduct_group.command("register")
@click.option("--session", "session_file", type=click.Path(path_type=Path, exists=True))
@click.option("--agent", default=lambda: os.environ.get("LIMEN_AGENT"))
@click.option("--surface", default=lambda: os.environ.get("LIMEN_SURFACE", "cli"))
@click.option("--session-id", default=None)
@click.option("--origin", type=click.Choice(["direct", "dispatched", "relay"]), default="direct")
@click.option("--capability", "capabilities_", multiple=True)
@click.option("--worktree", type=click.Path(path_type=Path), default=None)
@click.option("--human-protected", is_flag=True)
@click.option("--concurrency", type=click.IntRange(1, 1024), default=1)
@click.option("--transport", default=None)
@click.option("--native-fanout/--no-native-fanout", default=None)
@click.option("--harvest-method", default=None)
@click.option("--meter", default=None)
@click.option("--quota-remaining", type=click.FloatRange(min=0), default=None)
@click.option("--cost-per-run", type=click.FloatRange(min=0), default=None)
@click.option("--receipt-quality", type=click.FloatRange(0, 1), default=0, show_default=True)
@click.option("--native-session-id", default=None)
@click.option("--native-run-id", default=None)
@click.option("--provider-identity", default=None)
@click.option("--accepting-work/--not-accepting-work", default=True)
def register(
    session_file: Path | None,
    agent: str | None,
    surface: str,
    session_id: str | None,
    origin: Literal["direct", "dispatched", "relay"],
    capabilities_: tuple[str, ...],
    worktree: Path | None,
    human_protected: bool,
    concurrency: int,
    transport: str | None,
    native_fanout: bool | None,
    harvest_method: str | None,
    meter: str | None,
    quota_remaining: float | None,
    cost_per_run: float | None,
    receipt_quality: float,
    native_session_id: str | None,
    native_run_id: str | None,
    provider_identity: str | None,
    accepting_work: bool,
) -> None:
    if session_file:
        session = ConductorSessionV1.model_validate(_read_json(session_file))
    else:
        if not agent:
            raise click.ClickException("agent identity is required via --agent or LIMEN_AGENT")
        resolved_session = _session_id(session_id)
        defaults = _profile_defaults(agent)
        resolved_capabilities = frozenset(capabilities_) or defaults.get("capabilities", frozenset())
        resolved_native_run = native_run_id or os.environ.get("LIMEN_NATIVE_RUN_ID")
        identity = AgentIdentityV1(
            agent=agent,
            surface=surface,
            session_id=resolved_session,
            native_run_id=resolved_native_run,
            provider_identity=provider_identity,
        )
        session = ConductorSessionV1(
            session_id=resolved_session,
            identity=identity,
            origin=origin,
            native_session_id=native_session_id or os.environ.get("LIMEN_NATIVE_SESSION_ID"),
            native_run_id=resolved_native_run,
            capabilities=resolved_capabilities,
            worktree=str(worktree.resolve()) if worktree else os.environ.get("LIMEN_WORKTREE"),
            human_protected=human_protected,
            concurrency=concurrency,
            transport=transport or defaults.get("transport", "native"),
            native_fanout=(native_fanout if native_fanout is not None else bool(defaults.get("native_fanout", False))),
            harvest_method=harvest_method or defaults.get("harvest_method", "receipt"),
            meter=meter or defaults.get("meter"),
            quota_remaining=quota_remaining,
            cost_per_run=cost_per_run,
            receipt_quality=receipt_quality,
            accepting_work=accepting_work,
        )
    client = client_from_env()
    try:
        _emit(client.register(session))
    except ConductError as exc:
        owner_id = _dead_owner_to_supersede(str(exc), session)
        if owner_id is None:
            raise
        _emit(client.register(session.model_copy(update={"supersedes": owner_id})))


_OWNED_BY = re.compile(r"worktree is already owned by healthy session ([A-Za-z0-9._:-]+)")


def _dead_owner_to_supersede(detail: str, session: ConductorSessionV1) -> str | None:
    """The 409's named owner, but only when succession is provably safe: the broker's heartbeat
    TTL cannot see a crash/exec exit, so the claimant — the only party on the worktree's host —
    must prove no foreign process is still live there. Fail-closed: an unavailable probe reads
    as occupied and the original conflict is re-raised."""
    if not session.worktree:
        return None
    match = _OWNED_BY.search(detail)
    if not match:
        return None
    if foreign_worktree_occupant(Path(session.worktree)) is not None:
        return None
    return match.group(1)


@conduct_group.command("submit")
@click.option("--packet", "packet_file", required=True, type=click.Path(path_type=Path, exists=True))
def submit(packet_file: Path) -> None:
    _emit(client_from_env().submit(WorkPacketV1.model_validate(_read_json(packet_file))))


@conduct_group.command("split")
@click.argument("parent_run")
@click.option("--packet", "packet_file", required=True, type=click.Path(path_type=Path, exists=True))
def split(parent_run: str, packet_file: Path) -> None:
    packet = WorkPacketV1.model_validate(_read_json(packet_file))
    _emit(client_from_env().split(parent_run, packet))


@conduct_group.command("graph")
@click.argument("root_run")
def graph(root_run: str) -> None:
    _emit(client_from_env().graph(root_run))


@conduct_group.command("heartbeat")
@click.argument("lease")
@click.option("--generation", type=click.IntRange(1), required=True)
@click.option("--token-env", default="LIMEN_LEASE_TOKEN", show_default=True)
@click.option("--observed-heads", type=click.Path(path_type=Path, exists=True))
def heartbeat(lease: str, generation: int, token_env: str, observed_heads: Path | None) -> None:
    heads = _read_json(observed_heads) if observed_heads else {}
    _emit(
        client_from_env().heartbeat(
            lease,
            _lease_token(token_env),
            generation=generation,
            observed_heads=heads,
        )
    )


@conduct_group.command("report")
@click.argument("lease")
@click.option("--receipt", "receipt_file", required=True, type=click.Path(path_type=Path, exists=True))
@click.option("--token-env", default="LIMEN_LEASE_TOKEN", show_default=True)
def report(lease: str, receipt_file: Path, token_env: str) -> None:
    receipt = RunReceiptV1.model_validate(_read_json(receipt_file))
    _emit(
        client_from_env().report(
            lease,
            _lease_token(token_env),
            receipt,
            generation=receipt.lease_generation,
        )
    )


@conduct_group.command("harvest")
@click.argument("root_run")
def harvest(root_run: str) -> None:
    _emit(client_from_env().harvest(root_run))


@conduct_group.command("adopt")
@click.argument("run")
@click.option("--session-id", default=None)
def adopt(run: str, session_id: str | None) -> None:
    _emit(client_from_env().adopt(run, _session_id(session_id)))


@conduct_group.command("cancel")
@click.argument("run")
@click.option("--session-id", default=None)
def cancel(run: str, session_id: str | None) -> None:
    _emit(client_from_env().cancel(run, _session_id(session_id)))


@conduct_group.command("request-stop")
@click.argument("run")
@click.option("--session-id", default=None)
def request_stop(run: str, session_id: str | None) -> None:
    _emit(client_from_env().request_stop(run, _session_id(session_id)))
