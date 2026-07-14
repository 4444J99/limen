import os
import json
import subprocess
import sys
from pathlib import Path

import click

from limen.doctor import (
    print_qa_report,
    print_readiness,
    qa_report,
    readiness_report,
    write_report,
)
from limen.dispatch import dispatch_tasks, release_stale_tasks
from limen.harvest import harvest_results
from limen.io import load_limen_file, load_limen_text
from limen.progress import build_progress_snapshot, render_progress
from limen.status import print_status


def resolve_root() -> Path:
    root = os.environ.get("LIMEN_ROOT")
    if root:
        return Path(root).expanduser().resolve()
    cwd = Path.cwd()
    if (cwd / "tasks.yaml").exists():
        return cwd
    click.echo("LIMEN_ROOT not set and no tasks.yaml in current directory", err=True)
    sys.exit(2)


def resolve_tasks_path(root: Path) -> Path:
    env_path = os.environ.get("LIMEN_TASKS")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return root / "tasks.yaml"


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


@main.command()
@click.option("--root", default=None, help="Where to create the portal")
@click.option("--budget", default=100, type=int, help="Daily run budget")
def init(root, budget):
    """Scaffold a new tasks.yaml in LIMEN_ROOT or current directory."""
    target = Path(root).expanduser().resolve() if root else resolve_root()
    tasks_file = target / "tasks.yaml"

    if tasks_file.exists():
        click.echo(f"tasks.yaml already exists at {tasks_file}")
        return

    target.mkdir(parents=True, exist_ok=True)
    content = f"""version: "1.0"
portal:
  name: "Universal Task Intake"
  description: "One file to aim every agent you have"
  budget:
    daily: {budget}
    unit: "runs"
    per_agent: {{}}
    track:
      date: ""
      spent: 0
      per_agent: {{}}
tasks: []
"""
    tasks_file.write_text(content)
    click.echo(f"Created {tasks_file} with daily budget of {budget}")
    ag = target / "AGENTS.md"
    if not ag.exists():
        ag.write_text("# Limen Agent Protocol\n\nSee https://github.com/4444J99/limen\n")
        click.echo(f"Created {ag}")


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
    report = release_stale_tasks(limen, tasks_path, hours=hours, dry_run=dry_run, agent=agent)
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
    type=click.Choice(["workstream", "origin", "horizon", "agent", "repo", "status"]),
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
    from limen.io import save_limen_file

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
        save_limen_file(out, filtered, allow_shrink=True)  # a single channel is legitimately small
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
    help="Require a prompt, embed the live derive-not-force contract, and start Codex with the README.",
)
@click.option(
    "--codex",
    "launch_codex",
    is_flag=True,
    help="Open Codex in the worktree after creating the packet.",
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
    help="Inline prompt packet for .limen-workstream/README.md.",
)
@click.option(
    "--prompt-file",
    default=None,
    type=click.Path(exists=True),
    help="Prompt packet file to embed in README.md.",
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
    launch_codex,
    launch_shell,
    from_ref,
    prompt_text,
    prompt_file,
    workstream_handle,
    no_readme,
    repo,
    slug,
):
    """Create/reuse a repo worktree plus a private kickoff README and kickstart command."""
    root = resolve_limen_repo_root()
    script = root / "scripts" / "start-worktree-session.sh"
    args = ["bash", str(script)]
    if autonomous:
        args.append("--autonomous")
    if launch_codex:
        args.append("--codex")
    if launch_shell:
        args.append("--shell")
    if from_ref:
        args.extend(["--from", from_ref])
    if prompt_text:
        args.extend(["--prompt", prompt_text])
    if prompt_file:
        args.extend(["--prompt-file", prompt_file])
    if workstream_handle:
        args.extend(["--workstream", workstream_handle])
    if no_readme:
        args.append("--no-readme")
    args.extend([repo, slug])
    if launch_codex or launch_shell:
        result = subprocess.run(args)
    else:
        result = subprocess.run(args, text=True, capture_output=True)
        if result.stdout:
            click.echo(result.stdout, nl=False)
        if result.stderr:
            click.echo(result.stderr, err=True, nl=False)
    raise SystemExit(result.returncode)


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


if __name__ == "__main__":
    main()
