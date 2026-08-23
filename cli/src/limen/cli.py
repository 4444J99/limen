import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

import click
import yaml

from limen.conduct.client import BrokerQuotaExhausted, client_from_env
from limen.conduct.cli import conduct_group
from limen.dispatch import dispatch_tasks, release_stale_tasks
from limen.doctor import (
    print_qa_report,
    print_readiness,
    qa_report,
    readiness_report,
    write_report,
)
from limen.fanout_cli import fanout_group
from limen.harvest import harvest_results
from limen.host_admission import AdmissionController, AdmissionStateError, process_identity, worktree_scope
from limen.io import load_limen_file, load_limen_text, save_derived_limen_projection
from limen.private_board import (
    PrivateCustodyUnavailable,
    default_private_custody_path,
    operational_board_path,
    path_is_public_aggregate,
    private_board_path,
)
from limen.opencode_smoke import run_opencode_smoke
from limen.progress import build_progress_snapshot, render_progress
from limen.progress_source_registry import build_source_registry
from limen.status import print_status

# The live owner of a quota-exhausted keeper. NOT a human lever: L-CLOUDFLARE-DO-QUOTA was
# RETIRED 2026-08-10 because the recurrence proved the defect is ours — unbounded heartbeat
# persistence and full-state write amplification (every mutation rewrites the whole broker
# state). Issue #2054 says in terms that no Cloudflare support case, billing change, plan
# change or operator action is required, so pointing a reader at a lever sends them to a
# human action the owner explicitly ruled out. Cite the engineering owner instead.
QUOTA_OWNER = "organvm/limen#2054 (conduct persistence write amplification)"
EX_TEMPFAIL = 75  # sysexits(3): the request is valid, the service is temporarily unable to honour it


def resolve_root() -> Path:
    """The board root: $LIMEN_ROOT, else the first candidate that actually holds tasks.yaml.

    Discovery mirrors resolve_limen_repo_root() below, so a board-reading verb works from
    any directory the way `limen workstream` already does. Without the fallbacks, `limen
    dispatch` refused to run outside a checkout while the package could locate its own repo
    two other ways ($LIMEN_TASKS' parent, and the __file__-relative root).
    """
    root = os.environ.get("LIMEN_ROOT")
    if root:
        return Path(root).expanduser().resolve()
    candidates = [Path.cwd()]
    tasks_env = os.environ.get("LIMEN_TASKS")
    if tasks_env:
        # Same derivation _root_for_dispatch() applies: a projection names its own root.
        candidates.append(Path(tasks_env).expanduser().parent)
    private_env = os.environ.get("LIMEN_PRIVATE_TASKS")
    if private_env:
        private_path = Path(private_env).expanduser()
        if private_path.is_file():
            return private_path.parent.resolve()
        candidates.append(private_path.parent)
    candidates.append(Path(__file__).resolve().parents[3])
    candidates.append(Path.home() / "Workspace" / "limen")
    for candidate in candidates:
        if (candidate / "tasks.yaml").exists():
            return candidate.resolve()
    click.echo(
        "LIMEN_ROOT not set and no tasks.yaml found in: " + ", ".join(str(candidate) for candidate in candidates),
        err=True,
    )
    sys.exit(2)


def resolve_tasks_path(root: Path) -> Path:
    private_env = os.environ.get("LIMEN_PRIVATE_TASKS")
    if private_env:
        return private_board_path(root / "tasks.yaml") or (root / "tasks.yaml")
    env_path = os.environ.get("LIMEN_TASKS")
    if env_path:
        configured = Path(env_path).expanduser().resolve()
        # An explicit LIMEN_TASKS can itself name the public aggregate (the live
        # checkout after cutover); derive custody from its SHAPE, not from the name.
        return operational_board_path(configured)
    return operational_board_path(root / "tasks.yaml")


def resolve_limen_repo_root() -> Path:
    env_root = os.environ.get("LIMEN_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root).expanduser().resolve())
    candidates.append(Path(__file__).resolve().parents[3])
    candidates.append(Path.cwd())
    for candidate in candidates:
        if (candidate / "scripts" / "start-worktree-session.sh").exists():
            return candidate
    click.echo("Could not find scripts/start-worktree-session.sh; set LIMEN_ROOT", err=True)
    sys.exit(2)


@click.group()
def main():
    pass


main.add_command(conduct_group)
main.add_command(fanout_group)


@main.command("observe")
@click.option("--once", "once", is_flag=True, required=True, help="Run one bounded observation pass")
@click.option("--scope", type=click.Choice(["host", "remote", "all"]), default="all", show_default=True)
@click.option("--json-output", is_flag=True)
def observe(once: bool, scope: str, json_output: bool) -> None:
    """Observe declared host and remote predicates without dispatch, healing, or sync."""
    del once
    from limen.observer import observe_once

    receipt = observe_once(resolve_limen_repo_root(), scope)
    if json_output:
        click.echo(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        counts = receipt["counts"]
        click.echo(
            f"observe {scope}: {counts['passed']} passed, {counts['failed']} failed, {counts['timed_out']} timed out"
        )
        for name, failure in receipt.get("failures", {}).items():
            detail = failure.get("failure_kind") or failure.get("returncode")
            click.echo(f"  - {name}: {failure['status']} ({detail})")
    if receipt["counts"]["failed"] or receipt["counts"]["timed_out"]:
        raise click.exceptions.Exit(1)


@main.command("heartbeat")
@click.option("--once", "once", is_flag=True, required=True, help="Run one resource-bounded scheduled tick")
@click.option("--json-output", is_flag=True)
def heartbeat(once: bool, json_output: bool) -> None:
    """Run at most one due read-only probe, then exit without resident children."""
    del once
    from limen.heartbeat import heartbeat_once, is_system_failure

    receipt = heartbeat_once(resolve_limen_repo_root())
    if json_output:
        click.echo(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        probe = receipt.get("probe") or "none"
        click.echo(f"heartbeat: {receipt['status']} probe={probe}")
    if is_system_failure(receipt):
        raise click.exceptions.Exit(1)


def _host_owner() -> tuple[str, int]:
    pid = os.getppid()
    label = os.environ.get("LIMEN_HOST_ADMISSION_OWNER") or os.environ.get("LIMEN_SESSION_ID")
    if not label:
        identity = process_identity(pid) or str(pid)
        label = f"limen-cli-{hashlib.sha256(identity.encode()).hexdigest()[:24]}"
    return label, pid


def _emit_host_decision(decision: dict, *, json_output: bool) -> None:
    if json_output:
        click.echo(json.dumps(decision, indent=2, sort_keys=True))
        return
    state = "allowed" if decision.get("allowed") else "denied"
    reasons = ",".join(decision.get("reasons") or [])
    suffix = f" ({reasons})" if reasons else ""
    click.echo(f"host-admission {decision.get('operation')}: {state}{suffix}")


@click.group("host-admission")
def host_admission_group():
    """Inspect or mutate the machine-wide writer/heavy lease store."""


@host_admission_group.command("acquire")
@click.argument("kind", type=click.Choice(["execution", "heavy"]))
@click.option("--cwd", type=click.Path(path_type=Path), default=None)
@click.option("--json", "json_output", is_flag=True)
def host_admission_acquire(kind: str, cwd: Path | None, json_output: bool) -> None:
    owner, pid = _host_owner()
    controller = AdmissionController()
    try:
        if kind == "execution":
            scope = worktree_scope(cwd or Path.cwd())
            if not scope.linked:
                decision = {
                    "schema": "limen.host_admission_decision.v1",
                    "operation": "acquire",
                    "allowed": False,
                    "reasons": ["shared-checkout-write"],
                    "lease": None,
                    "leases": controller.status(probe=False).get("leases") or [],
                }
            else:
                decision = controller.acquire(
                    scope.lease_kind,
                    owner=owner,
                    surface="limen-host-admission-cli",
                    pid=pid,
                )
        else:
            decision = controller.acquire(kind, owner=owner, surface="limen-host-admission-cli", pid=pid)
    except (AdmissionStateError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    _emit_host_decision(decision, json_output=json_output)
    if not decision.get("allowed"):
        raise click.exceptions.Exit(3)


@host_admission_group.command("status")
@click.option("--cwd", type=click.Path(path_type=Path), default=None)
@click.option("--json", "json_output", is_flag=True)
def host_admission_status(cwd: Path | None, json_output: bool) -> None:
    controller = AdmissionController()
    try:
        decision = controller.status(probe=True)
        if cwd is not None:
            scope = worktree_scope(cwd)
            decision["scope"] = {
                "scope_hash": scope.scope_hash,
                "linked": scope.linked,
                "writer_held": any(lease.get("kind") == scope.lease_kind for lease in decision.get("leases") or []),
            }
    except (AdmissionStateError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    _emit_host_decision(decision, json_output=json_output)


@host_admission_group.command("release")
@click.argument("kind", type=click.Choice(["execution", "heavy"]))
@click.option("--cwd", type=click.Path(path_type=Path), default=None)
@click.option("--json", "json_output", is_flag=True)
def host_admission_release(kind: str, cwd: Path | None, json_output: bool) -> None:
    owner, pid = _host_owner()
    controller = AdmissionController()
    try:
        lease_kind = worktree_scope(cwd or Path.cwd()).lease_kind if kind == "execution" else kind
        decision = controller.release_owned(lease_kind, owner=owner, pid=pid)
    except (AdmissionStateError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    _emit_host_decision(decision, json_output=json_output)
    if not decision.get("allowed"):
        raise click.exceptions.Exit(3)


main.add_command(host_admission_group)


def _yaml_json_default(value: object) -> str:
    """Encode YAML scalar types that JSON does not natively represent."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"unsupported YAML value for JSON transport: {type(value).__name__}")


@click.group("board")
def board_group():
    """Hydrate or bootstrap the authenticated private board custody."""


@board_group.command("hydrate")
@click.option("--output", required=True, type=click.Path(path_type=Path), help="Private off-disk YAML custody path")
def board_hydrate(output: Path) -> None:
    """Fetch the full board from the keeper without touching public tasks.yaml."""
    target = output.expanduser().resolve()
    if target.name == "tasks.yaml":
        raise click.ClickException("private hydration must use a distinct custody filename, not public tasks.yaml")
    board = client_from_env().private_board()
    target.parent.mkdir(parents=True, exist_ok=True)
    from limen.io import atomic_write_text

    atomic_write_text(target, yaml.safe_dump(board, sort_keys=False))
    click.echo(f"hydrated private board custody: {target}")


@board_group.command("custody-path")
@click.option("--public", type=click.Path(path_type=Path), default=None, help="Public projection to resolve against")
def board_custody_path(public: Path | None) -> None:
    """Print the custody path local operation resolves to — the beat's single source of truth.

    Exits 0 with the path when the public projection is still a full board (custody
    is that same file), 0 with the private custody path once it is the aggregate, and
    3 when the aggregate has no hydrated custody yet — the state that must never be
    read as "the board is empty".
    """
    root = resolve_root() if public is None else Path(public).expanduser().parent
    public_path = Path(public).expanduser() if public else root / "tasks.yaml"
    try:
        resolved = operational_board_path(public_path)
    except PrivateCustodyUnavailable as exc:
        click.echo(str(exc), err=True)
        click.echo(str(default_private_custody_path(public_path)))
        raise SystemExit(3) from exc
    click.echo(str(resolved))
    if path_is_public_aggregate(public_path):
        click.echo(f"# derived: {public_path} is the public aggregate; operating on private custody", err=True)


@board_group.command("initialize")
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def board_initialize(source: Path) -> None:
    """Seed the keeper once from an existing private board source."""
    source_path = source.expanduser().resolve()
    board = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(board, dict) or not isinstance(board.get("tasks"), list):
        raise click.ClickException("source must be a YAML board object with a tasks list")
    # PyYAML resolves ISO dates to native objects.  The remote protocol is JSON, so normalize
    # those values at this boundary while preserving the source's canonical ISO representation.
    board = json.loads(json.dumps(board, default=_yaml_json_default))
    result = client_from_env().initialize_private_board(board)
    click.echo(json.dumps({key: value for key, value in result.items() if key != "board"}, indent=2, sort_keys=True))


main.add_command(board_group)


@main.command("opencode-smoke")
@click.option(
    "--require-reentry",
    is_flag=True,
    help="Refuse a healthy model; smoke only a post-cooldown model awaiting re-entry proof.",
)
def opencode_smoke(require_reentry: bool) -> None:
    """Run one bounded read-only OpenCode tool smoke and append its health outcome."""

    result = run_opencode_smoke(allow_healthy=not require_reentry)
    click.echo(json.dumps(result.as_dict(), indent=2, sort_keys=True))
    if result.status == "blocked":
        raise click.exceptions.Exit(3)
    if not result.succeeded:
        raise click.exceptions.Exit(1)


@main.command()
@click.option("--root", default=None, help="Where to create the portal")
@click.option("--budget", default=100, type=int, help="Daily run budget")
def init(root, budget):
    """Report the remote-owner bootstrap required for a new portal."""
    target = Path(root).expanduser().resolve() if root else resolve_root()
    tasks_file = target / "tasks.yaml"

    if tasks_file.exists():
        click.echo(f"tasks.yaml already exists at {tasks_file}")
        return

    del budget
    raise click.ClickException(
        "local tasks.yaml bootstrap is retired: initialize the GitHub-backed "
        "board through the authenticated conduct owner, then hydrate this cache"
    )


@main.command()
@click.option("--agent", default=None, help="Filter by target agent")
@click.option("--budget", default=None, type=int, help="Max runs to spend")
@click.option("--dry-run/--live", default=True, help="Default: dry-run (no actual dispatch)")
@click.option("--task", default=None, help="Dispatch a single task ID")
@click.option("--limit", default=None, type=int, help="Maximum tasks to dispatch")
def dispatch(agent, budget, dry_run, task, limit):
    """Read tasks.yaml and dispatch open tasks to agents."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    dispatch_tasks(
        limen,
        tasks_path,
        agent=agent,
        budget=budget,
        dry_run=dry_run,
        task_id=task,
        limit=limit,
    )


@main.command("release-stale")
@click.option("--hours", default=24, type=int, help="Age threshold for stale active claims")
@click.option("--agent", default=None, help="Filter by target agent")
@click.option("--dry-run/--apply", default=True, help="Default: dry-run (no task mutation)")
@click.option("--json-output", "json_output", is_flag=True, help="Print machine-readable JSON")
@click.option("--report-file", default=None, help="Write machine-readable JSON to this path")
def release_stale(hours, agent, dry_run, json_output, report_file):
    """Route stale claims; Jules claims reopen only after confirmed remote absence."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    try:
        report = release_stale_tasks(limen, tasks_path, hours=hours, dry_run=dry_run, agent=agent)
    except BrokerQuotaExhausted as exc:
        # A spent keeper storage plan is not a release-stale defect and not a bug — it is an
        # owner decision this rung cannot make. Report one legible line naming its registry
        # owner and exit EX_TEMPFAIL, the idiom heal-board.py and self-heal.py already use:
        # non-zero, so the beat ledger still records a real outcome, but distinguishable from
        # the exit 1 that means "this rung is broken". Before this, a quota wall read as a
        # release-stale failure and sent readers hunting a defect that did not exist.
        click.echo(f"release-stale: BLOCKED — keeper storage quota exhausted, release deferred ({exc})"[:400], err=True)
        click.echo(
            f"release-stale: the write path is spent, not broken — owner: {QUOTA_OWNER}",
            err=True,
        )
        raise SystemExit(EX_TEMPFAIL) from exc
    if report_file:
        report_path = Path(report_file).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    if json_output:
        click.echo(json.dumps(report, indent=2))


@main.command()
@click.option("--agent", default="jules", help="Agent readiness to check")
@click.option("--json-output", "json_output", is_flag=True, help="Print machine-readable JSON")
@click.option("--report-file", default=None, help="Write machine-readable JSON to this path")
def doctor(agent, json_output, report_file):
    """Report local readiness for dispatch and stale-claim recovery."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    report = readiness_report(limen, tasks_path, agent=agent)
    write_report(report, Path(report_file).expanduser() if report_file else None)
    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        print_readiness(report)


@main.command()
@click.option("--agent", default="jules", help="Agent queue used for mechanism commands")
@click.option("--json-output", "json_output", is_flag=True, help="Print machine-readable JSON")
@click.option("--report-file", default=None, help="Write machine-readable JSON to this path")
def qa(agent, json_output, report_file):
    """Report QA lifecycle gates and steering queues without mutating tasks."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    report = qa_report(limen, tasks_path, agent=agent)
    write_report(report, Path(report_file).expanduser() if report_file else None)
    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        print_qa_report(report)


@main.command("apply")
@click.option("--fire", is_flag=True, help="Include the submit phase — SUBMITS to real ATS portals")
@click.option("--json", "json_output", is_flag=True, help="Emit the raw driver summary")
def apply_cmd(fire, json_output):
    """Run the outbound job-application funnel (stage only unless --fire).

    The CLI twin of the ``application_funnel`` MCP tool and the beat's
    ``application-funnel`` sensor — one effector, three front doors, so an agent
    without MCP still drives the same funnel instead of writing its own submitter.

    Disarmed this is reversible: source, score, build materials, stage packages,
    prepare follow-ups. Nothing leaves the machine. ``--fire`` adds the submit
    phase, which sends real applications and cannot be undone.
    """
    root = Path(__file__).resolve().parents[3]
    driver = root / "scripts" / "application-funnel.py"
    if not driver.exists():
        click.echo(f"funnel driver not found: {driver}", err=True)
        sys.exit(1)

    env = dict(os.environ)
    if fire:
        env["LIMEN_APPLY_FIRE"] = "1"

    proc = subprocess.run(
        [sys.executable, str(driver), "--json"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(root),
    )
    if json_output:
        click.echo(proc.stdout.strip() or proc.stderr.strip())
        sys.exit(proc.returncode)

    try:
        summary = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        click.echo(proc.stderr.strip() or "funnel produced no summary", err=True)
        sys.exit(proc.returncode or 1)

    click.echo(
        f"sourced {summary.get('sourced', 0)} · qualified {summary.get('qualified', 0)} · "
        f"staged {summary.get('staged', 0)} · submitted {summary.get('submitted', 0)}"
    )
    for note in summary.get("notes", []):
        click.echo(f"  - {note}")
    sys.exit(proc.returncode)


@main.command("daily-execute")
@click.option("--fire", is_flag=True, help="Arm routine professional applications and follow-ups for this invocation")
@click.option("--json", "json_output", is_flag=True, help="Emit the bounded PII-clean execution receipt")
@click.option("--timeout", default=1800, type=click.IntRange(min=1, max=1800), show_default=True)
@click.option("--receipt", type=click.Path(path_type=Path), default=None, help="Write the private receipt here")
def daily_execute(fire: bool, json_output: bool, timeout: int, receipt: Path | None) -> None:
    """Run the shared daily communications and application loop.

    This is the same implementation exposed through MCP ``daily_execution`` and
    the existing heartbeat. ``--fire`` is invocation-local; generated templates,
    staged forms, and unconfirmed submissions never count as delivered.
    """
    from limen.daily_execution import run_daily_execution

    prior = os.environ.get("LIMEN_DAILY_EXECUTION_RECEIPT")
    if receipt is not None:
        os.environ["LIMEN_DAILY_EXECUTION_RECEIPT"] = str(receipt.expanduser())
    try:
        result = run_daily_execution(fire=fire, root=resolve_limen_repo_root(), timeout_seconds=timeout)
    finally:
        if prior is None:
            os.environ.pop("LIMEN_DAILY_EXECUTION_RECEIPT", None)
        else:
            os.environ["LIMEN_DAILY_EXECUTION_RECEIPT"] = prior

    if json_output:
        click.echo(json.dumps(result, indent=2, sort_keys=True))
    else:
        click.echo(
            f"daily-execute: {result['status']} · applications "
            f"{result['applications']['confirmed']}/{result['applications']['target']} confirmed · "
            f"follow-ups {result['follow_ups']['confirmed']} confirmed"
        )
        for blocker in result["blockers"]:
            click.echo(f"  - {blocker}")
    if result["status"] == "blocked":
        raise click.exceptions.Exit(3)


@main.command()
@click.option("--agent", default=None, help="Filter by agent")
@click.option("--status", default=None, help="Filter by status")
def status(agent, status):
    """Show the task board."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    if not tasks_path.exists():
        click.echo("tasks.yaml not found", err=True)
        sys.exit(1)
    limen = load_limen_file(tasks_path)
    print_status(limen, agent_filter=agent, status_filter=status)


@main.command()
@click.option(
    "--view",
    type=click.Choice(["workstream", "source_lineage", "origin", "horizon", "agent", "repo", "status"]),
    default="workstream",
    show_default=True,
    help="Macro grouping and micro drill-down dimension.",
)
@click.option(
    "--scope",
    default=None,
    help="Show one value from --view (for example financial or past).",
)
@click.option(
    "--level",
    type=click.Choice(["macro", "micro", "all"]),
    default="all",
    show_default=True,
    help="Zoom level.",
)
@click.option(
    "--limit",
    default=50,
    type=click.IntRange(min=0),
    show_default=True,
    help="Micro rows to print.",
)
@click.option("--all", "show_all", is_flag=True, help="Print every matching active debt leaf.")
@click.option("--ascii", "ascii_only", is_flag=True, help="Use ASCII progress bars.")
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Print the bounded machine-readable board and source-coverage lens.",
)
@click.option(
    "--report-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the bounded board and source-coverage lens to a JSON receipt.",
)
def progress(view, scope, level, limit, show_all, ascii_only, json_output, report_file):
    """Filter the partial task-board projection and source-coverage lens.

    Dark, stale, partial, capped, unavailable, failed, or incomplete source
    contracts remain visible as coverage debt.  Source-owned leaves are not
    imported.  Origin and horizon are explicit metadata only; Limen never
    guesses whether a task is a human prompt, obligation, recommendation, or
    past/present/future work from title resemblance.
    """

    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    if not tasks_path.exists():
        click.echo("tasks.yaml not found", err=True)
        raise click.ClickException("cannot build board-progress lens")
    limen = load_limen_file(tasks_path)
    snapshot = build_progress_snapshot(limen, root)
    if report_file:
        output = Path(report_file).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    if json_output:
        click.echo(json.dumps(snapshot, indent=2))
        return
    click.echo(
        render_progress(
            snapshot,
            view=view,
            scope=scope,
            level=level,
            limit=None if show_all else limit,
            ascii_only=ascii_only,
        ),
        nl=False,
    )


@main.command("progress-sources")
@click.option(
    "--registry-dir",
    "registry_dirs",
    multiple=True,
    type=click.Path(path_type=Path),
    help="Use an explicit registration root; repeat to combine roots.",
)
@click.option("--json-output", is_flag=True, help="Print the normalized source registry as JSON.")
@click.option(
    "--report-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the normalized registry to an explicit receipt path.",
)
def progress_sources(registry_dirs, json_output, report_file):
    """Discover and validate work-universe source owner reports."""

    root = resolve_root()
    registry = build_source_registry(
        root,
        registration_dirs=[Path(path).expanduser() for path in registry_dirs] or None,
    )
    if report_file:
        output = Path(report_file).expanduser()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    if json_output:
        click.echo(json.dumps(registry, indent=2))
        return
    summary = registry["summary"]
    discovery = registry["discovery"]
    click.echo(
        "WORK-UNIVERSE SOURCES "
        f"status={registry['semantic_status']} "
        f"sources={summary['source_count']} "
        f"ready={summary['ready_required_source_count']}/{summary['required_source_count']} "
        f"coverage_debt={summary['coverage_debt']} "
        f"unknown_counts={summary['unknown_leaf_count_sources']} "
        f"discovery_exhaustive={str(discovery['exhaustive']).lower()}"
    )
    for source in registry["sources"]:
        count = source["normalized_leaf_count"]
        click.echo(
            f"{source['source_id']}\t{source['semantic_status']}\t"
            f"owner={source['owner']['id']}:{source['owner']['surface']}\t"
            f"exhaustive={str(source['exhaustive']).lower()}\tleaves={count if count is not None else 'unknown'}"
        )


def _open_prs_via_gh(limit: int = 200):
    """Enumerate open PRs in the current repo via `gh pr list` → list[workstream.PullRequest].

    Kept in the CLI (IO) layer so `limen.workstream` stays pure. Fail-open: any gh error (not
    installed, unauthenticated, not a GitHub repo) yields an empty list with a note on stderr,
    never a traceback — the projection just shows zero PRs.
    """
    from limen import workstream as ws

    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "open",
                "--limit",
                str(limit),
                "--json",
                "number,title,headRefName,url,isDraft",
            ],
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        click.echo("gh not found — cannot enumerate PRs (install GitHub CLI)", err=True)
        return []
    if result.returncode != 0:
        click.echo(f"gh pr list failed: {result.stderr.strip()}", err=True)
        return []
    try:
        rows = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return [
        ws.PullRequest(
            number=int(r.get("number", 0)),
            title=str(r.get("title", "")),
            branch=str(r.get("headRefName", "")),
            url=str(r.get("url", "")),
            draft=bool(r.get("isDraft", False)),
        )
        for r in rows
    ]


@main.command()
@click.option(
    "--scope",
    default=None,
    help="Show only one channel (accepts an alias, e.g. 'revenue').",
)
@click.option(
    "--emit",
    default=None,
    type=click.Path(),
    help="Write a board filtered to --scope's tasks to this path (feeds `cell conduct --workstream`).",
)
@click.option(
    "--prs",
    "prs_mode",
    is_flag=True,
    help="Project OPEN PRs (via gh) by channel instead of the task board — makes PR sprawl legible.",
)
@click.option(
    "--json-output",
    "json_output",
    is_flag=True,
    help="Machine-readable roster + per-channel counts.",
)
def channels(scope, emit, prs_mode, json_output):
    """Project the board by workstream channel — the purpose partition above vendor lanes.

    The roster DERIVES from organ-ladder.json (one channel per institutional organ) plus the
    operational lanes (conductor / contributions / correspondence / prompt-parity). `--emit` writes a
    single channel's board so a scoped `cell conduct --workstream <handle>` sees only its own lane —
    the one-worker-one-channel invariant that cures mixed-purpose PR pileup. `--prs` reuses the same
    channel taxonomy to bucket the open-PR pile, so session/PR sprawl reads on the purpose axis too.
    """
    from limen import workstream as ws

    root = resolve_root()

    if prs_mode:
        if emit:
            click.echo(
                "--emit projects the task board, not PRs; drop --prs or --emit",
                err=True,
            )
            sys.exit(2)
        prs = _open_prs_via_gh()
        if json_output:
            click.echo(json.dumps(ws.pr_roster_summary(prs, root), indent=2))
        else:
            ws.print_pr_channels(prs, root, scope=scope)
        return

    tasks_path = resolve_tasks_path(root)
    if not tasks_path.exists():
        click.echo("tasks.yaml not found", err=True)
        sys.exit(1)
    limen = load_limen_file(tasks_path)

    if emit:
        if not scope:
            click.echo("--emit requires --scope <handle>", err=True)
            sys.exit(2)
        filtered = ws.filter_board(limen, scope, root)
        out = Path(emit).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        save_derived_limen_projection(
            out,
            filtered,
            canonical_path=tasks_path,
        )  # a single channel is an explicitly noncanonical read-only projection
        click.echo(f"wrote {len(filtered.tasks)} tasks for channel '{ws.canonical_handle(scope, root)}' to {out}")
        return

    if json_output:
        click.echo(json.dumps(ws.roster_summary(limen, root), indent=2))
        return
    ws.print_channels(limen, root, scope=scope)


@main.command()
@click.option("--agent", default=None, help="Filter by agent")
def harvest(agent):
    """Check for completed dispatches and update task states."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    harvest_results(limen, tasks_path, agent=agent)


@main.command("workstream")
@click.option(
    "--autonomous",
    is_flag=True,
    help="Require a prompt and pass the modular live contract to the selected native agent.",
)
@click.option(
    "--agent",
    "agent_name",
    default=None,
    metavar="auto|LANE",
    help="Select and launch a canonical native lane; auto derives an available installed CLI.",
)
@click.option(
    "--conduct",
    is_flag=True,
    help="Register the launched direct session with the conduct broker as human-protected.",
)
@click.option(
    "--model",
    "launch_model",
    default=None,
    help="With --reasoning-effort and --sandbox: the exact human-selected Codex model. Alone: a lane tier pin for a registry profile that declares model-flag support; requires --agent.",
)
@click.option(
    "--reasoning-effort",
    "launch_reasoning_effort",
    default=None,
    help="Exact reasoning effort supported by the selected live Codex model.",
)
@click.option(
    "--sandbox",
    "launch_sandbox",
    default=None,
    help="Codex sandbox for the explicit primary launch profile.",
)
@click.option(
    "--shell",
    "launch_shell",
    is_flag=True,
    help="Open a login shell in the worktree after creating the packet.",
)
@click.option(
    "--from",
    "from_ref",
    default=None,
    help="Branch or ref to create the worktree branch from.",
)
@click.option(
    "--prompt",
    "prompt_text",
    default=None,
    help="Inline prompt packet for .limen-workstream/intent.md.",
)
@click.option(
    "--prompt-file",
    default=None,
    type=click.Path(exists=True),
    help="Prompt packet file to copy into intent.md.",
)
@click.option(
    "--predecessor-receipt",
    type=click.Path(exists=True, dir_okay=False),
    default=None,
    help="Create a validated successor from one committed tracked workstream receipt.",
)
@click.option(
    "--runway-mode",
    type=click.Choice(["inherit", "renew"]),
    default=None,
    help="Inherit the predecessor deadline exactly, or renew with an explicit --runway.",
)
@click.option(
    "--runway",
    default=None,
    help="Finite workstream runway (for example 90m, 8h, or 7d); defaults to 1d.",
)
@click.option(
    "--no-readme",
    is_flag=True,
    help="Create/reuse the worktree without writing the private kickoff packet.",
)
@click.option("--workstream", "workstream_handle", default=None, help="Pin the capsule to one purpose channel.")
@click.argument("repo")
@click.argument("slug")
def workstream(
    autonomous,
    agent_name,
    conduct,
    launch_model,
    launch_reasoning_effort,
    launch_sandbox,
    launch_shell,
    from_ref,
    prompt_text,
    prompt_file,
    predecessor_receipt,
    runway_mode,
    runway,
    workstream_handle,
    no_readme,
    repo,
    slug,
):
    """Create/reuse a repo worktree plus a modular kickoff capsule and command."""
    if predecessor_receipt is None and runway_mode is not None:
        raise click.UsageError("--runway-mode requires --predecessor-receipt")
    effective_runway_mode = runway_mode or "inherit"
    root = resolve_limen_repo_root()
    script = root / "scripts" / "start-worktree-session.sh"
    args = ["bash", str(script)]
    if autonomous:
        args.append("--autonomous")
    if agent_name:
        args.extend(["--agent", agent_name])
    if conduct:
        args.append("--conduct")
    if launch_model:
        args.extend(["--model", launch_model])
    if launch_reasoning_effort:
        args.extend(["--reasoning-effort", launch_reasoning_effort])
    if launch_sandbox:
        args.extend(["--sandbox", launch_sandbox])
    if launch_shell:
        args.append("--shell")
    if from_ref:
        args.extend(["--from", from_ref])
    if prompt_text:
        args.extend(["--prompt", prompt_text])
    if prompt_file:
        args.extend(["--prompt-file", prompt_file])
    if predecessor_receipt:
        args.extend(["--predecessor-receipt", predecessor_receipt, "--runway-mode", effective_runway_mode])
    if runway:
        args.extend(["--runway", runway])
    if workstream_handle:
        args.extend(["--workstream", workstream_handle])
    if no_readme:
        args.append("--no-readme")
    args.extend([repo, slug])
    if agent_name or launch_shell:
        result = subprocess.run(args, text=True)
    else:
        result = subprocess.run(args, text=True, capture_output=True)
        if result.stdout:
            click.echo(result.stdout, nl=False)
        if result.stderr:
            click.echo(result.stderr, err=True, nl=False)
    raise SystemExit(result.returncode)


@main.command("streams")
@click.option(
    "--status",
    "show_status",
    is_flag=True,
    help="One line per stream with its derived state (live/dormant/ready/blocked/stale/settled); touches nothing.",
)
@click.option(
    "--family",
    default=None,
    type=click.Choice(["domain", "constellation", "governance", "all"]),
    help="Which rows to open. Default domain — the operator's life/work domains (correspondence, "
    "financial, representation, …); constellation (the consulting domain's collaborator interior) "
    "and governance rows are named as elided and opened deliberately.",
)
@click.option("--lane", default=None, metavar="LANE", help="Native lane to open on (claude|codex|agy|opencode|…).")
@click.option("--dry-run", "dry_run", is_flag=True, help="Print exactly what would open; touch nothing.")
@click.option("--max-parallel", "max_parallel", default=None, type=int, help="Override the RAM-derived bound.")
@click.option("--unbounded", is_flag=True, help="Waive the RAM-derived bound (you accept the jetsam risk).")
@click.option("--session", "tmux_session", default=None, help="tmux session name (default limen-streams).")
def streams(show_status, family, lane, dry_run, max_parallel, unbounded, tmux_session):
    """Open (and REOPEN) the session streams, each in its own tmux window.

    The advertised form of scripts/open-streams.sh — a pure delegate, so the CLI can never tell a
    different story than the script. The round trip: open → work → exit the agent (the tmux window
    is kept) → `limen streams` again reopens the dormant stream; `limen streams --status` shows
    every lane's derived state at a glance.
    """
    root = resolve_limen_repo_root()
    args = ["bash", str(root / "scripts" / "open-streams.sh")]
    if show_status:
        args.append("--status")
    if family:
        args.extend(["--family", family])
    if lane:
        args.extend(["--lane", lane])
    if dry_run:
        args.append("--dry-run")
    if max_parallel is not None:
        args.extend(["--max-parallel", str(max_parallel)])
    if unbounded:
        args.append("--all")
    if tmux_session:
        args.extend(["--session", tmux_session])
    raise SystemExit(subprocess.run(args).returncode)


@main.command()
@click.option(
    "--verify",
    is_flag=True,
    help="Prove the fold reproduces the board byte-for-byte (exit 1 if not).",
)
@click.option(
    "--emit-events",
    "emit_events",
    default=None,
    help="Write the board's seed event stream (fold input) to this JSONL path.",
)
def materialize(verify, emit_events):
    """Derive the board from its event stream — step 1 of the event-sourced board.

    The board (tasks.yaml) is a *materialized view*: board = fold(events). --verify seeds events
    from the current board, folds them, re-serializes through the canonical writer, and asserts the
    bytes are identical — the executable proof that the projection reproduces reality exactly. This
    commits nothing (it does not write tasks.yaml); it only proves the ideal form is faithful.
    """
    import yaml

    from limen.materialize import fold, seed_events_from_board

    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    if not tasks_path.exists():
        click.echo("tasks.yaml not found", err=True)
        sys.exit(1)

    # Read the board bytes exactly ONCE: seed events from, and compare against, the same buffer.
    # The live board is rewritten every beat, so a second read_text() could observe a different file
    # than the one we folded — a TOCTOU false-negative. load_limen_text parses that single snapshot.
    on_disk = tasks_path.read_text()
    board = load_limen_text(on_disk, name=tasks_path.name)
    events = seed_events_from_board(board)

    if emit_events:
        out = Path(emit_events).expanduser()
        out.write_text("".join(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n" for e in events))
        click.echo(f"wrote {len(events)} events to {out}")

    if verify or not emit_events:
        rebuilt = fold(events)
        # canonical serialization = exactly what save_limen_file writes (mode=json, exclude_none,
        # sort_keys=False). Compare against the snapshot we loaded from — not a fresh read.
        rebuilt_bytes = yaml.dump(
            rebuilt.model_dump(mode="json", exclude_none=True),
            sort_keys=False,
            default_flow_style=False,
        )
        identical = rebuilt_bytes == on_disk
        click.echo(
            f"materialize: {len(board.tasks)} tasks, {len(events)} events; "
            f"fold(events) == tasks.yaml bytes: {identical}"
        )
        if not identical:
            click.echo(
                "  NON-IDENTICAL — the board on disk is not canonical, or the fold lost a field. "
                "Re-run `limen doctor`; do not migrate writers until this exits 0.",
                err=True,
            )
            sys.exit(1)


@main.command()
@click.option("--once", is_flag=True, help="One frame then exit")
@click.option("--compact", is_flag=True, help="One-line compact mode")
@click.option("-n", "--interval", default=2.0, type=float, help="Refresh interval in seconds")
def watch(once, compact, interval):
    """Show the real-time fleet dashboard."""
    from limen.watch import run

    run(once=once, compact=compact, interval=interval)


@main.group("research")
def research():
    """Prepare attended research and verify exported evidence."""


@research.command("prepare")
@click.argument("request_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--catalog",
    "catalog_source",
    default=lambda: os.environ.get("LIMEN_RESEARCH_CATALOG"),
    help="Studium profile registry path or URL (defaults to its canonical remote).",
)
@click.option("--work-dir", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option("--profile", default=None, help="Explicit owner profile; no fallback if unavailable.")
@click.option("--launch", is_flag=True, help="Open the attended research surface after writing the handoff.")
def research_prepare(request_file, catalog_source, work_dir, profile, launch):
    """Render a typed ManualHandoff or fail-closed BlockedReceipt."""
    from limen.research import (
        DEFAULT_CATALOG_URL,
        BlockedReceipt,
        ResearchRequest,
        launch_attended_research,
        load_document,
        prepare_research,
        write_json,
    )

    request = ResearchRequest.from_mapping(load_document(request_file))
    if profile:
        request = request.with_profile(profile)
    catalog = load_document(catalog_source or DEFAULT_CATALOG_URL)
    work_dir = work_dir.expanduser().resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = work_dir / f"{request.request_id}.prompt.md"
    outcome_path = work_dir / f"{request.request_id}.outcome.json"
    receipt_path = work_dir / f"{request.request_id}.receipt.json"
    outcome, receipt = prepare_research(request, catalog, prompt_ref=prompt_path.name)
    if hasattr(outcome, "rendered_prompt"):
        prompt_path.write_text(outcome.rendered_prompt, encoding="utf-8")
    write_json(outcome_path, outcome.public_dict())
    write_json(receipt_path, receipt.public_dict())
    if launch and not isinstance(outcome, BlockedReceipt):
        launch_attended_research(outcome)
    click.echo(
        json.dumps(
            {
                "outcome": outcome.outcome_type,
                "outcome_ref": str(outcome_path),
                "prompt_ref": str(prompt_path) if prompt_path.exists() else None,
                "receipt_ref": str(receipt_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    if isinstance(outcome, BlockedReceipt):
        raise click.exceptions.Exit(1)


@research.command("ingest")
@click.argument("export_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("request_file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--catalog",
    "catalog_source",
    default=lambda: os.environ.get("LIMEN_RESEARCH_CATALOG"),
    help="Studium profile registry path or URL (defaults to its canonical remote).",
)
@click.option("--owner-root", required=True, type=click.Path(file_okay=False, path_type=Path))
@click.option(
    "--handoff-receipt",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Manual-pending receipt emitted by research prepare.",
)
@click.option(
    "--verification-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Studium Source Verifier attestation for every claim and source.",
)
@click.option(
    "--sanitization-file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Studium Output Sanitization attestation bound to the exact Markdown export.",
)
@click.option(
    "--raw-owner-root",
    default=None,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    help="Designated root named by a private-owner:// raw_export_ref.",
)
@click.option("--observed-provider", default=None, help="Record only when the export exposes it.")
@click.option("--observed-model", default=None, help="Record only when the export exposes it.")
@click.option(
    "--operator-handling-seconds",
    required=True,
    type=click.IntRange(min=0),
    help="Measured attended handling time for the durable usage receipt.",
)
def research_ingest(
    export_file,
    request_file,
    catalog_source,
    owner_root,
    handoff_receipt,
    verification_file,
    sanitization_file,
    raw_owner_root,
    observed_provider,
    observed_model,
    operator_handling_seconds,
):
    """Normalize a Markdown export and write verified owner-repo outputs."""
    from limen.research import (
        DEFAULT_CATALOG_URL,
        BlockedReceipt,
        ResearchRequest,
        ingest_markdown_export,
        load_document,
        owner_path,
        render_evidence_markdown,
        stable_hash,
        verify_owner_root,
        verify_raw_export_custody,
        write_json,
    )

    request = ResearchRequest.from_mapping(load_document(request_file))
    catalog = load_document(catalog_source or DEFAULT_CATALOG_URL)
    handoff = load_document(handoff_receipt)
    verification = load_document(verification_file)
    sanitization = load_document(sanitization_file)
    owner_root = verify_owner_root(owner_root, request)
    verify_raw_export_custody(
        export_file,
        owner_root,
        request,
        raw_owner_root=raw_owner_root,
    )
    markdown = export_file.read_text(encoding="utf-8")
    outcome, receipt = ingest_markdown_export(
        markdown,
        request,
        catalog,
        handoff_receipt=handoff,
        verification_attestation=verification,
        sanitization_attestation=sanitization,
        observed_provider=observed_provider,
        observed_model=observed_model,
        operator_handling_seconds=operator_handling_seconds,
    )
    receipt_path = owner_path(owner_root, request.receipt_ref)
    if isinstance(outcome, BlockedReceipt):
        blocked_path = receipt_path.with_suffix(".blocked.json")
        write_json(blocked_path, outcome.public_dict())
        if not blocked_path.is_file() or not blocked_path.read_bytes():
            raise click.ClickException("blocked outcome write did not produce a durable owner artifact")
        write_json(receipt_path, receipt.public_dict())
        click.echo(json.dumps({"outcome": outcome.outcome_type, "blocked_ref": str(blocked_path)}, indent=2))
        raise click.exceptions.Exit(1)

    report_path = owner_path(owner_root, request.report_ref)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if request.output_format == "json":
        write_json(report_path, outcome)
    else:
        report_path.write_text(render_evidence_markdown(outcome), encoding="utf-8")
    if not report_path.is_file() or not report_path.read_bytes():
        raise click.ClickException("report write did not produce a durable owner artifact")
    report_hash = stable_hash(report_path.read_text(encoding="utf-8"))
    write_json(receipt_path, receipt.public_dict())
    click.echo(
        json.dumps(
            {
                "outcome": outcome["outcome_type"],
                "report_ref": str(report_path),
                "report_hash": report_hash,
                "receipt_ref": str(receipt_path),
            },
            indent=2,
            sort_keys=True,
        )
    )


@main.group("observatory")
def observatory():
    """OBSERVATORY — read-only daily GitHub success analysis (GITVS's legibility twin)."""


@observatory.command("doctor")
@click.option("--offline", is_flag=True, help="Skip the live gh probe")
def observatory_doctor(offline):
    """Self-verifying predicate: exit 0 ⟺ the organ is wired and safe."""
    from limen.observatory import doctor as obs_doctor

    report = obs_doctor.run(offline=offline)
    click.echo(json.dumps(report, indent=2, sort_keys=True))
    if not report.get("ok"):
        sys.exit(1)


@observatory.command("run")
@click.option(
    "--apply/--dry-run",
    default=False,
    help="Default: dry-run (proposes; writes no lever/task)",
)
def observatory_run(apply):
    """Run the whole loop (collect → analyze → reconcile → brief) for one beat."""
    from limen.observatory import executive as obs_exec

    status = obs_exec.run_beat(apply=apply)
    click.echo(obs_exec.summary_line(status))


def _load_vltima_validator(root: Path):
    path = root / "scripts" / "validate-vltima-kernel.py"
    if not path.exists():
        click.echo(f"VLTIMA validator missing at {path}", err=True)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("limen_vltima_validator_cli", path)
    if spec is None or spec.loader is None:
        click.echo(f"Could not load VLTIMA validator at {path}", err=True)
        sys.exit(2)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _display_path(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _vltima_json_text(payload: object) -> str:
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def _norm_selector(value: str) -> str:
    return value.strip().strip("/").lower()


def _select_vltima_projection(
    projection: dict[str, object],
    *,
    primitive: str | None,
    organ: str | None,
    layer: str | None,
    projection_name: str | None,
) -> object | None:
    selectors = [value for value in (primitive, organ, layer, projection_name) if value]
    if len(selectors) > 1:
        click.echo("vltima-kernel: choose only one of --primitive, --organ, --layer, or --projection", err=True)
        sys.exit(2)

    if primitive:
        needle = _norm_selector(primitive)
        primitives = projection.get("primitives")
        if isinstance(primitives, list):
            for item in primitives:
                if not isinstance(item, dict):
                    continue
                identifiers = {str(item.get("id") or "").lower(), str(item.get("label") or "").lower()}
                if needle in identifiers:
                    return item
        click.echo(f"vltima-kernel: primitive not found: {primitive}", err=True)
        sys.exit(1)

    if organ:
        needle = _norm_selector(organ)
        organs = projection.get("organs")
        if isinstance(organs, list):
            for item in organs:
                if not isinstance(item, dict):
                    continue
                home = _norm_selector(str(item.get("home") or ""))
                identifiers = {str(item.get("pillar") or "").lower(), home, home.removeprefix("organs/")}
                if needle in identifiers:
                    return item
        click.echo(f"vltima-kernel: organ not found: {organ}", err=True)
        sys.exit(1)

    if layer:
        layers = projection.get("layers") or {}
        if not isinstance(layers, dict):
            click.echo("vltima-kernel: layer map missing", err=True)
            sys.exit(1)
        needle = _norm_selector(layer)
        for layer_name, primitives in layers.items():
            if needle == str(layer_name).lower():
                return primitives
        click.echo(f"vltima-kernel: layer not found: {layer}", err=True)
        sys.exit(1)

    if projection_name:
        projections = projection.get("projections") or {}
        if not isinstance(projections, dict):
            click.echo("vltima-kernel: projection map missing", err=True)
            sys.exit(1)
        if projection_name not in projections:
            click.echo(f"vltima-kernel: projection not found: {projection_name}", err=True)
            sys.exit(1)
        return projections[projection_name]

    return None


@main.command("vltima-kernel")
@click.option("--root", type=click.Path(path_type=Path), default=None, help="Repo root to inspect.")
@click.option("--json-output", is_flag=True, help="Emit the derived VLTIMA kernel projection as JSON.")
@click.option("--write-projection", is_flag=True, help="Write organs/vltima/projection.json from the registry.")
@click.option("--check-projection", is_flag=True, help="Fail if organs/vltima/projection.json is missing or stale.")
@click.option("--projection-path", type=click.Path(path_type=Path), default=None, help="Override projection path.")
@click.option("--primitive", default=None, help="Emit one primitive by id or label.")
@click.option("--organ", default=None, help="Emit one organ projection by pillar or home path.")
@click.option("--layer", default=None, help="Emit one primitive layer by name.")
@click.option("--projection", "projection_name", default=None, help="Emit one named projection group.")
def vltima_kernel(
    root,
    json_output,
    write_projection,
    check_projection,
    projection_path,
    primitive,
    organ,
    layer,
    projection_name,
):
    """Validate and emit the VLTIMA universal kernel substrate."""
    repo_root = root.expanduser().resolve() if root else resolve_limen_repo_root()
    validator = _load_vltima_validator(repo_root)
    errors = validator.validate(repo_root)
    if errors:
        click.echo(f"vltima-kernel: blocked with {len(errors)} issue(s)", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(1)

    selector_requested = bool(primitive or organ or layer or projection_name)
    if json_output or write_projection or check_projection or selector_requested:
        projection, projection_errors = validator.build_projection(repo_root)
        if projection_errors:
            click.echo(f"vltima-kernel: blocked with {len(projection_errors)} issue(s)", err=True)
            for error in projection_errors:
                click.echo(f"  - {error}", err=True)
            sys.exit(1)
        expected = validator.projection_json_text(projection)
        target = validator._projection_path(repo_root, projection_path)
        if write_projection:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(expected)
            if not json_output:
                click.echo(f"vltima-kernel: wrote projection to {_display_path(repo_root, target)}")
        if check_projection:
            if not target.exists():
                click.echo(f"vltima-kernel: projection missing: {_display_path(repo_root, target)}", err=True)
                sys.exit(1)
            if target.read_text() != expected:
                click.echo(f"vltima-kernel: projection stale: {_display_path(repo_root, target)}", err=True)
                sys.exit(1)
            if not json_output and not write_projection and not selector_requested:
                click.echo(f"vltima-kernel: projection current at {_display_path(repo_root, target)}")
        selected = _select_vltima_projection(
            projection,
            primitive=primitive,
            organ=organ,
            layer=layer,
            projection_name=projection_name,
        )
        if selected is not None:
            click.echo(_vltima_json_text(selected), nl=False)
            return
        if json_output:
            click.echo(expected, nl=False)
        return

    click.echo("vltima-kernel: universal kernel and organ projections valid")


if __name__ == "__main__":
    main()
