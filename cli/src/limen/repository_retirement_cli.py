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


@repos_group.command("custody")
@click.option("--allowlist", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--apply", is_flag=True, help="Preserve exact listed roots; never remove sources.")
@click.option("--verify", type=click.Path(path_type=Path, exists=True, dir_okay=False))
@click.option("--candidate", multiple=True, help="Opaque candidate IDs within the unchanged allowlist.")
@click.option("--max-seconds", type=click.IntRange(1, 900), default=600)
def custody(allowlist, apply, verify, candidate, max_seconds):
    """Encrypted archives and two-device restoration for an exact source allowlist."""
    from limen.agent_state.crypto import CryptoError
    from limen.host_admission import AdmissionDenied, hold_lease
    from limen.repository_archive_custody import ArchiveCustody, default_config
    from limen.repository_archive_custody import allowlist as read_allowlist
    from limen.repository_retirement import atomic_json, digest

    if bool(allowlist) == bool(verify) or (verify and (apply or candidate)):
        raise click.UsageError("Use --allowlist [--apply] or --verify RECEIPT.")
    data = state_root().parent / "repository-archives"
    runtime = Runtime(time.time() + max_seconds)
    engine = ArchiveCustody(runtime, data / "scratch")
    try:
        config = default_config(Path(__file__).resolve().parents[3])
        if verify:
            with (
                hold_lease(
                    "heavy",
                    owner=os.environ.get("CODEX_THREAD_ID", f"archive-{os.getpid()}"),
                    surface="repository-archive-verify",
                ),
                runtime.verification(),
            ):
                result = engine.verify(json.loads(verify.read_text()), config)
        else:
            binding, entries = read_allowlist(allowlist)
            if candidate:
                selected = set(candidate)
                if not selected.issubset({digest(e["path"])[:16] for e in entries}):
                    raise click.UsageError("Candidate is outside the exact allowlist.")
                entries = [e for e in entries if digest(e["path"])[:16] in selected]
            if not apply:
                result = {
                    "preview": True,
                    "allowlist_sha256": binding,
                    "candidates": engine.preview(entries),
                    "retirement_authorized": False,
                }
            else:
                rows = []
                with hold_lease(
                    "heavy",
                    owner=os.environ.get("CODEX_THREAD_ID", f"archive-{os.getpid()}"),
                    surface="repository-archive-capture",
                ):
                    for entry in entries:
                        try:
                            row = engine.capture(entry, binding, config, data / binding)
                        except (RetirementError, OSError, ValueError, CryptoError) as exc:
                            row = {
                                "candidate": digest(entry["path"])[:16],
                                "status": "retained",
                                "reason": str(exc)
                                if isinstance(exc, RetirementError)
                                else "archive-capture-unavailable",
                            }
                        rows.append(row)
                        atomic_json(data / binding / "progress.json", {"candidates": rows})
                result = {"allowlist_sha256": binding, "candidates": rows, "retirement_authorized": False}
        click.echo(json.dumps(result, sort_keys=True))
        if any(row.get("status") == "retained" for row in result.get("candidates", [])):
            raise click.exceptions.Exit(1)
    except (RetirementError, OSError, ValueError, CryptoError, AdmissionDenied) as exc:
        if isinstance(exc, AdmissionDenied):
            raise click.ClickException(
                "archive-host-admission-denied: " + ", ".join(exc.decision.get("reasons", []))
            ) from exc
        raise click.ClickException(
            str(exc) if isinstance(exc, RetirementError) else "archive-prerequisite-unavailable"
        ) from exc
    finally:
        if (apply or verify) and engine.diagnostics:
            # Internal FileVault storage, mode 0600. Never print raw private diagnostics.
            engine.scratch_ready()
            atomic_json(data / "diagnostics.json", {"failures": engine.diagnostics})


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
