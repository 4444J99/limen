import os
import json
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
from limen.io import load_limen_file
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
        ag.write_text(
            "# Limen Agent Protocol\n\nSee https://github.com/4444J99/limen\n"
        )
        click.echo(f"Created {ag}")


@main.command()
@click.option("--agent", default=None, help="Filter by target agent")
@click.option("--budget", default=None, type=int, help="Max runs to spend")
@click.option(
    "--dry-run/--live", default=True, help="Default: dry-run (no actual dispatch)"
)
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
@click.option(
    "--hours", default=24, type=int, help="Age threshold for stale active claims"
)
@click.option("--agent", default=None, help="Filter by target agent")
@click.option(
    "--dry-run/--apply", default=True, help="Default: dry-run (no task mutation)"
)
@click.option(
    "--json-output", "json_output", is_flag=True, help="Print machine-readable JSON"
)
@click.option(
    "--report-file", default=None, help="Write machine-readable JSON to this path"
)
def release_stale(hours, agent, dry_run, json_output, report_file):
    """Reopen dispatched/in-progress tasks whose latest event is stale."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    report = release_stale_tasks(
        limen, tasks_path, hours=hours, dry_run=dry_run, agent=agent
    )
    if report_file:
        report_path = Path(report_file).expanduser()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    if json_output:
        click.echo(json.dumps(report, indent=2))


@main.command()
@click.option("--agent", default="jules", help="Agent readiness to check")
@click.option(
    "--json-output", "json_output", is_flag=True, help="Print machine-readable JSON"
)
@click.option(
    "--report-file", default=None, help="Write machine-readable JSON to this path"
)
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
@click.option(
    "--agent", default="jules", help="Agent queue used for mechanism commands"
)
@click.option(
    "--json-output", "json_output", is_flag=True, help="Print machine-readable JSON"
)
@click.option(
    "--report-file", default=None, help="Write machine-readable JSON to this path"
)
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
@click.option("--agent", default=None, help="Filter by agent")
def harvest(agent):
    """Check for completed dispatches and update task states."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    harvest_results(limen, tasks_path, agent=agent)


if __name__ == "__main__":
    main()
