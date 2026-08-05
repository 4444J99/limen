#!/usr/bin/env python3
"""host-relief — SHED has hands: relieve what the fleet owns (IF-HOST-PRESSURE form 4).

2026-07-16 host-thrash: a root `bztransmit` stats pass held 8.6 GiB, the launchd
service com.limen.overnight-watch bloated to 3.1 GiB, swap hit 17.3/18 GiB — and
every relief step was performed BY HAND. This effector automates exactly that relief,
each beat, when the VITALS gate says SHED:

  * census the RSS of every running ``com.limen.*`` launchd agent (one ps pass);
    any label over VITALS_RSS_CEILING_MB is restarted via ``launchctl kickstart -k``
    (the launch-agent-liveness.py heal pattern) — the 3.1 GiB→105 MB overnight-watch
    restart, mechanized;
  * detect root-owned hogs the fleet CANNOT touch (RSS > VITALS_ROOT_HOG_MB) and
    escalate them loudly (onset-deduped macOS notification via scripts/_notify.py)
    carrying the pre-formed one-liner (``sudo kill <pid>``) — the one irreducible
    human atom, pushed to the operator instead of discovered by him;
  * notify once on SHED onset naming what was done; clear conditions when the gate
    returns to ok so the next onset re-fires.

Never touches bzserv/bztransmit/system processes itself (the storage-roles.yaml
Backblaze anti-role stands: observation only — escalation, not action). Bounded,
idempotent, fail-open. ``--check`` reports; ``--apply`` (the sensors.yaml armed
valve LIMEN_HOST_RELIEF_APPLY) executes the kickstarts. Fixture flags exist for
hermetic tests and force plan-only behavior — fixtures never cause side effects.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / "cli" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import _notify  # noqa: E402
from limen.vigilia import params, vitals  # noqa: E402

AGENT_PREFIX = "com.limen."
SHED_ONSET_KEY = "shed-onset"


def _root() -> Path:
    env = os.environ.get("LIMEN_ROOT")
    return Path(env).expanduser() if env else SOURCE_ROOT


def parse_ps(text: str) -> list[dict]:
    """Rows of ``ps -axo pid=,user=,rss=,command=`` → [{pid, user, rss_mb, command}]."""
    rows = []
    for line in text.splitlines():
        parts = line.split(None, 3)
        if len(parts) < 4 or not parts[0].isdigit() or not parts[2].isdigit():
            continue
        rows.append(
            {
                "pid": int(parts[0]),
                "user": parts[1],
                "rss_mb": round(int(parts[2]) / 1024, 1),  # ps rss is KiB
                "command": parts[3][:200],
            }
        )
    return rows


def parse_launchctl(text: str) -> dict[str, int]:
    """``launchctl list`` → {label: pid} for running com.limen.* agents."""
    agents: dict[str, int] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit() and parts[2].startswith(AGENT_PREFIX):
            agents[parts[2]] = int(parts[0])
    return agents


def plan_relief(
    gate_action: str,
    procs: list[dict],
    agents: dict[str, int],
    ceiling_mb: float,
    root_hog_mb: float,
) -> dict:
    """Pure decision: which owned agents to restart, which foreign hogs to escalate."""
    by_pid = {p["pid"]: p for p in procs}
    over_ceiling = []
    for label, pid in sorted(agents.items()):
        proc = by_pid.get(pid)
        if proc and proc["rss_mb"] > ceiling_mb:
            over_ceiling.append({"label": label, "pid": pid, "rss_mb": proc["rss_mb"]})
    agent_pids = set(agents.values())
    root_hogs = [
        {
            "pid": p["pid"],
            "user": p["user"],
            "rss_mb": p["rss_mb"],
            "command": p["command"],
            "one_liner": f"sudo kill {p['pid']}",
        }
        for p in procs
        if p["user"] == "root" and p["rss_mb"] > root_hog_mb and p["pid"] not in agent_pids and p["pid"] > 1
    ]
    return {
        "gate_action": gate_action,
        "relieve": gate_action == vitals.SHED,
        "over_ceiling": over_ceiling,
        "root_hogs": root_hogs if gate_action != vitals.OK else [],
    }


def _kickstart(label: str, uid: int) -> dict:
    target = f"gui/{uid}/{label}"
    try:
        proc = subprocess.run(["launchctl", "kickstart", "-k", target], capture_output=True, text=True, timeout=20)
        return {"label": label, "target": target, "ok": proc.returncode == 0, "rc": proc.returncode}
    except Exception as exc:
        return {"label": label, "target": target, "ok": False, "error": str(exc)[:120]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only (default action)")
    parser.add_argument("--apply", action="store_true", help="execute kickstarts for over-ceiling com.limen agents")
    parser.add_argument("--json", action="store_true", help="emit the full JSON report")
    parser.add_argument("--no-notify", action="store_true", help="dedup bookkeeping only, no osascript")
    parser.add_argument("--notify-test", action="store_true", help="fire one test notification and exit")
    parser.add_argument("--gate-action", default=None, help="override for tests (ok|throttle|shed)")
    parser.add_argument("--ps-fixture", default=None, help="ps output file — override for tests (forces plan-only)")
    parser.add_argument("--launchctl-fixture", default=None, help="launchctl list output file — override for tests")
    args = parser.parse_args(argv)

    root = _root()
    enabled = False if args.no_notify else None

    if args.notify_test:
        fired = _notify.notify_once(root, f"notify-test-{os.getpid()}", "host-relief notification path live", enabled=enabled)
        print(f"host-relief: notify-test fired={fired}")
        return 0

    hermetic = bool(args.ps_fixture or args.launchctl_fixture)
    if args.gate_action:
        gate_action = args.gate_action
    else:
        try:
            gate_action = vitals.beat_gate(shed=False).get("action", vitals.OK)
        except Exception:
            gate_action = vitals.OK  # fail-open: relief never invents pressure

    try:
        ps_text = (
            Path(args.ps_fixture).read_text()
            if args.ps_fixture
            else subprocess.run(
                ["ps", "-axo", "pid=,user=,rss=,command="], capture_output=True, text=True, timeout=15
            ).stdout
        )
        lc_text = (
            Path(args.launchctl_fixture).read_text()
            if args.launchctl_fixture
            else subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=15).stdout
        )
    except Exception as exc:
        print(f"host-relief: unknown — census failed ({str(exc)[:120]}); fail-open")
        return 0

    ceiling_mb = params.get("VITALS_RSS_CEILING_MB", 1024, cast=float)
    root_hog_mb = params.get("VITALS_ROOT_HOG_MB", 4096, cast=float)
    report = plan_relief(gate_action, parse_ps(ps_text), parse_launchctl(lc_text), ceiling_mb, root_hog_mb)
    report["ceiling_mb"] = ceiling_mb
    report["root_hog_mb"] = root_hog_mb

    kicked: list[dict] = []
    if report["relieve"] and report["over_ceiling"]:
        if args.apply and not hermetic:
            kicked = [_kickstart(item["label"], os.getuid()) for item in report["over_ceiling"]]
        else:
            kicked = [
                {"label": item["label"], "target": f"gui/{os.getuid()}/{item['label']}", "planned": True}
                for item in report["over_ceiling"]
            ]
    report["kickstarts"] = kicked

    notified: list[str] = []
    if report["relieve"]:
        did = ", ".join(f"{k['label']} restarted" for k in kicked if k.get("ok")) or "fleet load shed by the gate"
        if _notify.notify_once(root, SHED_ONSET_KEY, f"Host pressure critical — {did}. Details: logs/vigilia/", enabled=enabled):
            notified.append(SHED_ONSET_KEY)
    else:
        _notify.clear_condition(root, SHED_ONSET_KEY)
    current_hog_keys = set()
    for hog in report["root_hogs"]:
        key = f"root-hog-{hog['pid']}"
        current_hog_keys.add(key)
        msg = f"Root process holds {hog['rss_mb'] / 1024:.1f} GiB ({hog['command'][:60]}) — run: {hog['one_liner']}"
        if _notify.notify_once(root, key, msg, enabled=enabled):
            notified.append(key)
    for key in _notify.active_conditions(root):
        if key.startswith("root-hog-") and key not in current_hog_keys:
            _notify.clear_condition(root, key)  # hog gone — next onset re-fires
    report["notified"] = notified

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"host-relief: gate={gate_action} over-ceiling={len(report['over_ceiling'])} "
            f"root-hogs={len(report['root_hogs'])} kickstarts={len(kicked)} notified={len(notified)}"
        )
        for item in report["over_ceiling"]:
            print(f"  - {item['label']} pid {item['pid']} rss {item['rss_mb']:.0f} MB (ceiling {ceiling_mb:.0f})")
        for hog in report["root_hogs"]:
            print(f"  ! {hog['command'][:80]} pid {hog['pid']} rss {hog['rss_mb']:.0f} MB → {hog['one_liner']}")

    failed = [k for k in kicked if k.get("ok") is False]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
