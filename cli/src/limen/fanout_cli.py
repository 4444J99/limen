"""Public ``limen fanout`` command surface."""

from __future__ import annotations

import json
import os
from pathlib import Path

import click

from limen.conduct.broker import ConductError
from limen.conduct.client import client_from_env
from limen.fanout import (
    FanoutError,
    harvest_root,
    load_manifest,
    plan_manifest,
    start_manifest,
    status_root,
)


def _emit(payload: dict) -> None:
    click.echo(json.dumps(payload, indent=2, sort_keys=True))


def _failure(exc: Exception) -> click.ClickException:
    return click.ClickException(str(exc))


@click.group("fanout")
def fanout_group() -> None:
    """Plan, start, resume, and harvest board-independent remote work."""


@fanout_group.command("plan")
@click.option("--manifest", "manifest_file", required=True, type=click.Path(path_type=Path, exists=True))
def plan(manifest_file: Path) -> None:
    """Validate and render a canonical route without launching."""

    try:
        manifest = load_manifest(manifest_file)
        configured = os.environ.get("LIMEN_CONDUCT_URL") or os.environ.get("LIMEN_CONDUCT_STATE")
        capabilities = client_from_env().capabilities() if configured else None
        _emit(plan_manifest(manifest, capabilities=capabilities))
    except (ConductError, FanoutError, ValueError) as exc:
        raise _failure(exc) from exc


@fanout_group.command("start")
@click.option("--manifest", "manifest_file", required=True, type=click.Path(path_type=Path, exists=True))
@click.option("--remote-first/--no-remote-first", default=True, show_default=True)
@click.option("--local-max", type=click.IntRange(0, 1), default=1, show_default=True)
def start(manifest_file: Path, remote_first: bool, local_max: int) -> None:
    """Atomically reserve the graph and immediately return its root run ID."""

    try:
        manifest = load_manifest(manifest_file)
        _emit(
            start_manifest(
                manifest,
                client=client_from_env(),
                remote_first=remote_first,
                local_max=local_max,
            )
        )
    except (ConductError, FanoutError, ValueError) as exc:
        raise _failure(exc) from exc


@fanout_group.command("status")
@click.argument("root_run")
@click.option("--json", "json_output", is_flag=True, help="Emit the keeper response as JSON.")
def status(root_run: str, json_output: bool) -> None:
    """Resume campaign status directly from the remote keeper."""

    del json_output
    try:
        _emit(status_root(root_run, client=client_from_env()))
    except (ConductError, FanoutError, ValueError) as exc:
        raise _failure(exc) from exc


@fanout_group.command("harvest")
@click.argument("root_run")
@click.option("--merge", is_flag=True, help="Land exact PR receipts through the merge queue.")
def harvest(root_run: str, merge: bool) -> None:
    """Validate exact receipts and land each code leaf independently."""

    try:
        _emit(harvest_root(root_run, client=client_from_env(), merge=merge))
    except (ConductError, FanoutError, ValueError) as exc:
        raise _failure(exc) from exc
