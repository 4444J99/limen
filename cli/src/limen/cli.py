import os
import sys
from pathlib import Path

import click

from limen.dispatch import dispatch_tasks
from limen.harvest import harvest_results
from limen.io import load_limen_file, save_limen_file
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
def dispatch(agent, budget, dry_run, task):
    """Read tasks.yaml and dispatch open tasks to agents."""
    root = resolve_root()
    tasks_path = resolve_tasks_path(root)
    limen = load_limen_file(tasks_path)
    dispatch_tasks(
        limen, tasks_path, agent=agent, budget=budget, dry_run=dry_run, task_id=task
    )


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
