#!/usr/bin/env python3
"""launch-agent-liveness.py — the liveness invariant for critical launchd organs.

The gap this closes. On 2026-07-09 a mass launchd-quiesce (macOS 26.6 fork/os_log crash
mitigation) disabled 11 agents at once and only ``com.limen.heartbeat`` was restored — the
MONETA mint (the first-dollar revenue rail), its Cloudflare tunnel, the credential organ, and
the ianva gateway sat dark for days. The armed-valve audit SAW the mint down every beat
(``MONETA_MINT_LIVE SILENT-OFF``) but nothing restored it: a sensor with no effector, which the
charter names a defect. This organ is that missing effector.

The form. A declared invariant — ``spec/critical-launch-agents.json`` — names the launchd agents
that MUST stay alive. Every beat this asserts each one; when armed (``LIMEN_LAUNCHAGENT_HEAL=1``)
it re-bootstraps + kickstarts any that are down, restoring a plist from
``~/Library/LaunchAgents.disabled/`` if a quiesce quarantined it there. The REGISTRY (not chat)
owns WHICH organs are load-bearing; the DAEMON (not an ephemeral session) owns keeping them
alive. So the human residue collapses to ONE durable grant: arm the valve once, and the beat
keeps the rail alive across quiesce + reboot forever — never a per-incident approval.

Down = the launchd label is not loaded, OR its declared health probe fails. Restore = (if the
active plist is missing, copy the newest quarantined backup back) -> ``bootstrap`` ->
``kickstart -k`` -> re-probe. An agent whose plist exists NOWHERE is genuinely unrecoverable: it
is surfaced RED (never silent) with the exact remediation, never quietly dropped.

Off-darwin the signal is inapplicable, so it fails OPEN (reports, never gates).

PII-clean: only labels, roles, probe kinds, and ISO times are printed — never secrets/addresses.

Exit codes (with --check): 0 = every critical agent alive; 1 = one or more down (after any
--apply restore). Default (no flag): report + stamp, exit 0.

Usage:
  python3 scripts/launch-agent-liveness.py             # report + stamp, exit 0
  python3 scripts/launch-agent-liveness.py --check     # gate mode: exit 1 if any down
  python3 scripts/launch-agent-liveness.py --apply      # restore down agents (the effector)
  python3 scripts/launch-agent-liveness.py --apply --dry-run   # preview restores, no mutation
  python3 scripts/launch-agent-liveness.py --agents-file F      # override manifest (tests)
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))
DEFAULT_MANIFEST = ROOT / "spec" / "critical-launch-agents.json"
LAUNCHAGENTS_DIR = Path(os.environ.get("LIMEN_LAUNCHAGENTS_DIR", Path.home() / "Library" / "LaunchAgents"))
DISABLED_DIR = Path(
    os.environ.get("LIMEN_LAUNCHAGENTS_DISABLED_DIR", Path.home() / "Library" / "LaunchAgents.disabled")
)
DOMAIN_UID = os.environ.get("LIMEN_LAUNCHCTL_UID") or str(os.getuid())
IS_DARWIN = sys.platform == "darwin"


def load_manifest(path):
    """The critical-agent list from the invariant file. Missing/unreadable -> empty (fail open)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    agents = data.get("agents", []) if isinstance(data, dict) else []
    return [a for a in agents if isinstance(a, dict) and a.get("label")]


# ── injectable side-effect boundaries (monkeypatched in tests) ─────────────────────────────────
def _launchctl(args, timeout=15):
    """Run launchctl; return CompletedProcess. Never raises."""
    try:
        return subprocess.run(["launchctl", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:  # pragma: no cover - defensive
        return subprocess.CompletedProcess(args, 1, "", str(e))


def _probe_http(url, expect_status, timeout=6):
    """True iff GET url returns expect_status. Uses curl (already a fleet dependency)."""
    try:
        out = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "--max-time", str(timeout), url],
            capture_output=True,
            text=True,
            timeout=timeout + 4,
        )
        return out.stdout.strip() == str(expect_status)
    except (OSError, subprocess.SubprocessError):
        return False


# ── assessment ─────────────────────────────────────────────────────────────────────────────────
def is_loaded(label):
    """True iff launchd has the label bootstrapped in the gui domain."""
    return _launchctl(["print", f"gui/{DOMAIN_UID}/{label}"]).returncode == 0


def probe_ok(agent):
    """Liveness per the agent's declared probe. 'http' hits a URL; otherwise loaded-ness is life."""
    p = agent.get("probe") or {}
    if p.get("kind") == "http":
        return _probe_http(p["url"], p.get("expect_status", 200))
    return is_loaded(agent["label"])


def find_plist(label):
    """(path, state): active plist if present, else newest quarantined backup, else (None,'missing')."""
    active = LAUNCHAGENTS_DIR / f"{label}.plist"
    if active.exists():
        return active, "active"
    if DISABLED_DIR.is_dir():
        backups = sorted(DISABLED_DIR.glob(f"{label}.plist.*"))
        if backups:
            return backups[-1], "quarantined"
    return None, "missing"


def assess(agent):
    """{label, role, alive, down, plist_state, recoverable}."""
    label = agent["label"]
    plist, plist_state = find_plist(label)
    alive = probe_ok(agent)
    return {
        "label": label,
        "role": agent.get("role", ""),
        "alive": alive,
        "down": not alive,
        "plist_state": plist_state,
        "recoverable": plist is not None,
    }


# ── effector ─────────────────────────────────────────────────────────────────────────────────
def restore(agent, dry_run=False, settle_tries=3, settle_s=2.0):
    """Bring a down agent back: (re-place quarantined plist) -> bootstrap -> kickstart -> re-probe."""
    label = agent["label"]
    plist, state = find_plist(label)
    if plist is None:
        return {
            "label": label,
            "action": "unrecoverable",
            "ok": False,
            "steps": [],
            "detail": (
                f"no plist for {label} in {LAUNCHAGENTS_DIR} or {DISABLED_DIR} — "
                "regenerate it (scripts/gen-launchd-plist.sh) then re-run"
            ),
        }
    active = LAUNCHAGENTS_DIR / f"{label}.plist"
    steps = []
    if state == "quarantined":
        steps.append(f"restore plist {plist.name} -> {active}")
        if not dry_run:
            LAUNCHAGENTS_DIR.mkdir(parents=True, exist_ok=True)
            shutil.copy2(plist, active)
    steps.append(f"bootstrap gui/{DOMAIN_UID} {active.name}")
    steps.append(f"kickstart -k gui/{DOMAIN_UID}/{label}")
    if dry_run:
        return {"label": label, "action": "restore", "ok": True, "steps": steps, "detail": "would restore"}
    _launchctl(["bootstrap", f"gui/{DOMAIN_UID}", str(active)])  # no-op if already loaded
    _launchctl(["kickstart", "-k", f"gui/{DOMAIN_UID}/{label}"])
    ok = False
    for _ in range(max(1, settle_tries)):
        if probe_ok(agent):
            ok = True
            break
        time.sleep(settle_s)
    return {
        "label": label,
        "action": "restore",
        "ok": ok,
        "steps": steps,
        "detail": "restored" if ok else "restart issued; probe still down (next beat re-checks)",
    }


def _stamp(payload):
    """Best-effort log stamp; never fatal."""
    try:
        logs = ROOT / "logs"
        logs.mkdir(exist_ok=True)
        (logs / "launch-agent-liveness.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:  # pragma: no cover - defensive
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="critical launchd-agent liveness invariant + effector")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 if any critical agent down")
    ap.add_argument("--apply", action="store_true", help="restore down agents (the effector)")
    ap.add_argument("--dry-run", action="store_true", help="with --apply: preview restores, no mutation")
    ap.add_argument(
        "--agents-file", default=os.environ.get("LIMEN_CRITICAL_AGENTS_FILE"), help="manifest path override"
    )
    args = ap.parse_args(argv)

    manifest = args.agents_file or DEFAULT_MANIFEST
    agents = load_manifest(manifest)

    statuses = [assess(a) for a in agents]
    by_label = {a["label"]: a for a in agents}
    down = [s for s in statuses if s["down"]]

    restored = []
    if args.apply and down and (IS_DARWIN or args.dry_run):
        for s in down:
            restored.append(restore(by_label[s["label"]], dry_run=args.dry_run))
        # re-assess after the effector so the exit code reflects the final state
        statuses = [assess(a) for a in agents]
        down = [s for s in statuses if s["down"]]

    payload = {
        "manifest": str(manifest),
        "darwin": IS_DARWIN,
        "total": len(statuses),
        "down": [s["label"] for s in down],
        "unrecoverable": [s["label"] for s in down if not s["recoverable"]],
        "restored": restored,
        "green": not down,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _stamp(payload)

    print("── launch-agent liveness (critical organs must stay alive) ──")
    if not agents:
        print(f"  ⚠ no critical agents declared in {manifest} — nothing to assert")
    for s in statuses:
        mark = "✓" if s["alive"] else "✗"
        note = "" if s["alive"] else f"  [plist:{s['plist_state']}{'' if s['recoverable'] else ' UNRECOVERABLE'}]"
        print(f"  {mark} {s['label']} — {s['role']}{note}")
    for r in restored:
        icon = "↻" if r["ok"] else "⚠"
        print(f"    {icon} {r['label']}: {r['detail']}")
    if not IS_DARWIN:
        print("  • non-darwin host — liveness inapplicable, failing OPEN")
    print(f"  RESULT: {'GREEN' if not down else 'RED'}")
    if down:
        unrec = [s["label"] for s in down if not s["recoverable"]]
        if unrec:
            print(f"  ✗ UNRECOVERABLE (regenerate plist): {', '.join(unrec)}")
        recov = [s["label"] for s in down if s["recoverable"]]
        if recov and not args.apply:
            print(f"  ✗ DOWN (recoverable): {', '.join(recov)} — arm LIMEN_LAUNCHAGENT_HEAL=1 to auto-restore")

    # fail OPEN off-darwin (signal inapplicable); gate only on a real down set otherwise
    failed = bool(down) and IS_DARWIN
    return 1 if (failed and args.check) else 0


if __name__ == "__main__":
    sys.exit(main())
