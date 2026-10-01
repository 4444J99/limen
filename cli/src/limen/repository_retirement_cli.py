"""Human-facing batch entrypoint; previews do not create journals or reserve actors."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import click

from limen.conduct.broker import ConductError
from limen.repository_retirement import (
    Campaign,
    RetirementError,
    Runner,
    Runtime,
    load_manifest,
    public_publish,
    timestamp,
)
from limen.repository_retirement_keeper import Keeper


def state_root() -> Path:
    return (
        Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))) / "limen" / "repository-retirement"
    )


@click.group("repos")
def repos_group():
    """Synchronize, preserve, and retire an exact admitted repository batch."""


def _campaign(batch: Path | None, resume: str | None) -> Campaign:
    if bool(batch) == bool(resume):
        raise click.UsageError("Specify exactly one of --batch or --resume.")
    if resume:
        from limen.repository_retirement import IDENTIFIER

        if not IDENTIFIER.fullmatch(resume):
            raise click.UsageError("Invalid campaign ID.")
        value = json.loads((state_root() / resume / "state.json").read_text())["manifest"]
    else:
        assert batch is not None
        value = load_manifest(batch)
    return Campaign(value, state_root())


@repos_group.command("retire")
@click.option("--batch", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--resume")
@click.option("--apply", is_flag=True, help="Execute already-authorized work; otherwise preview only.")
@click.option("--json-output", is_flag=True)
def retire(batch, resume, apply, json_output):
    """Run one bounded batch pass and retain exact progress for resumption."""
    try:
        if not apply and batch:
            # Preview does not instantiate Campaign (which owns private journals).
            manifest = load_manifest(batch)
            shell = object.__new__(Campaign)
            shell.manifest = manifest
            shell.hash = ""
            result = Runner(shell, runtime=Runtime(min(timestamp(manifest["deadline"]), time.time() + 600))).preview()
        else:
            campaign = _campaign(batch, resume)
            if not apply:
                result = Runner(campaign).preview()
            else:
                # Exactly one authenticated graph read. No fallback to a previous
                # campaign's exhaustion receipt or to caller-supplied accounting.
                keeper = Keeper(campaign.manifest)
                runtime = Runtime(min(keeper.deadline, time.time() + 1800))
                runner = Runner(
                    campaign,
                    keeper=keeper,
                    runtime=runtime,
                    progress=None
                    if json_output
                    else lambda row: click.echo(
                        f"{row['candidate']}: {row['status']} ({row.get('reason') or 'verified'})"
                    ),
                )
                result = runner.apply()
                public_publish(runtime, campaign)
                result = campaign.summary()
                if not result.get("retained") and not campaign.state.get("root_report"):
                    proofs = {
                        key: row["proof_sha256"]
                        for key, row in campaign.state["candidates"].items()
                        if row["status"] == "removed"
                    }
                    campaign.state["root_report"] = keeper.report(proofs)
                    campaign.save()
        click.echo(json.dumps(result, sort_keys=True, indent=2))
        if apply and result.get("retained"):
            raise click.exceptions.Exit(1)
    except ConductError as exc:
        raise click.ClickException(f"keeper-rejected-{type(exc).__name__}: status={exc.status}") from exc
    except (RetirementError, OSError, ValueError, KeyError) as exc:
        if isinstance(exc, RetirementError):
            detail = str(exc)
        else:
            detail = "batch-input-or-state-unavailable"
        raise click.ClickException(detail) from exc


@repos_group.command("accept")
@click.option("--resume", required=True)
def accept(resume):
    """Review current custody proofs as the separately reserved native reviewer."""
    try:
        campaign = _campaign(None, resume)
        keeper = Keeper(campaign.manifest)
        result = Runner(campaign, keeper=keeper, runtime=Runtime(min(keeper.deadline, time.time() + 600))).accept()
        click.echo(json.dumps(result, sort_keys=True))
    except ConductError as exc:
        raise click.ClickException(f"keeper-rejected-{type(exc).__name__}: status={exc.status}") from exc
    except (RetirementError, OSError, ValueError, KeyError) as exc:
        raise click.ClickException(str(exc) if isinstance(exc, RetirementError) else "acceptance-unavailable") from exc


@repos_group.command("status")
@click.argument("campaign_id")
@click.option("--private", is_flag=True, help="Include private candidate paths; never publish this output.")
def status(campaign_id, private):
    """Read measured changes without inspecting repositories or reserving capacity."""
    try:
        campaign = _campaign(None, campaign_id)
        value = campaign.state if private else campaign.summary()
        click.echo(json.dumps(value, sort_keys=True, indent=2))
    except (RetirementError, OSError, ValueError, KeyError) as exc:
        raise click.ClickException("campaign-state-unavailable") from exc
