#!/usr/bin/env python3

import os
import sys
import yaml
from datetime import datetime, timezone, timedelta
from pathlib import Path


def get_tasks_path() -> Path:
    p = os.environ.get("LIMEN_TASKS")
    if p:
        return Path(p)
    default_path = Path.home() / "Workspace" / "limen" / "tasks.yaml"
    if default_path.exists():
        return default_path
    return Path("tasks.yaml")


def main():
    agent = "agy"
    tasks_path = get_tasks_path()

    if not tasks_path.exists():
        print(f"Error: Could not find tasks.yaml at {tasks_path}")
        sys.exit(1)

    try:
        with open(tasks_path, "r") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        print(f"Error reading {tasks_path}: {e}")
        sys.exit(1)

    try:
        portal = data.get("portal", {})
        budget = portal.get("budget", {})
        track = budget.get("track", {})

        per_agent_caps = budget.get("per_agent", {})
        per_agent_spent = track.get("per_agent", {})
        per_agent_reset = track.get("per_agent_reset", {})

        cap = per_agent_caps.get(agent, 0)
        spent = per_agent_spent.get(agent, 0)
        last_reset_str = per_agent_reset.get(agent)

        remaining = max(0, cap - spent)

        now = datetime.now(timezone.utc)

        print("==================================================")
        print("             AGY INTERNAL CLOCK                   ")
        print("==================================================")
        print(f" Agent:           {agent}")
        print(f" Daily Cap:       {cap} runs")
        print(f" Usage Spent:     {spent} runs")
        print(f" Remaining:       {remaining} runs")
        print("--------------------------------------------------")

        if last_reset_str:
            try:
                last_reset = datetime.fromisoformat(last_reset_str)
                if last_reset.tzinfo is None:
                    last_reset = last_reset.replace(tzinfo=timezone.utc)

                # Agy is on a 24h reset window by default
                window_hours = 24.0
                next_reset = last_reset + timedelta(hours=window_hours)

                print(f" Last Reset:      {last_reset.strftime('%Y-%m-%d %H:%M:%S UTC')}")
                print(f" Next Reset:      {next_reset.strftime('%Y-%m-%d %H:%M:%S UTC')}")

                time_until = int((next_reset - now).total_seconds())
                if time_until <= 0:
                    overdue_hours, overdue_rem = divmod(abs(time_until), 3600)
                    overdue_minutes = overdue_rem // 60
                    print(f" Refresh Status:  [OVERDUE] Window expired {overdue_hours}h {overdue_minutes}m ago.")
                    print("                  Budget will reset on next dispatch.")
                else:
                    pending_hours, pending_rem = divmod(time_until, 3600)
                    pending_minutes = pending_rem // 60
                    print(f" Refresh Status:  [PENDING] {pending_hours}h {pending_minutes}m until next refresh.")
            except Exception as e:
                print(f" Reset info:      Unparseable timestamp ({e})")
        else:
            print(" Reset info:      No previous reset found")

        print("==================================================")

    except Exception as e:
        print(f"Error parsing budget data: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
