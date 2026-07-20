"""Click command surface for the shared conduct protocol."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

import click

from limen.conduct.client import client_from_env
from limen.conduct.models import AgentIdentityV1, ConductorSessionV1, RunReceiptV1, WorkPacketV1


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
    _emit(client_from_env().register(session))


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
