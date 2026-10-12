"""Shared OS observations routed through the existing insight cadence.

One bounded probe per run; stable owner/signal IDs deduplicate repeat failures.
After three unchanged observations automatic repair is held for owner review.
Native visual evidence is supplied by the supported computer-use harness only.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from limen.runtime_pool import RuntimePool


def probe(argv):
    try:
        result = subprocess.run(argv, capture_output=True, timeout=10, check=False)
        return result.returncode == 0 and not result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return False


def observations(root, home):
    pool = RuntimePool().observe(home)
    result = []
    if not pool.get("allowed"):
        result.append(
            (
                "shared_pool_pressure",
                "4444J99/limen",
                True,
                ",".join(pool.get("denial_reasons", [])) or "pool_observation_unavailable",
            )
        )
    targets = [str(home / ".claude/CLAUDE.md"), str(home / ".claude/hooks/chezmoi-add-after-edit.sh")]
    if not probe(["chezmoi", "diff", "--include", "files", *targets]):
        result.append(("managed_configuration_drift", "4444J99/domus-genoma", True, "reviewed_source_render_mismatch"))
    host = home / "Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost"
    # verify-lifetime is read-only; it does not request or change TCC permissions.
    try:
        ready = (
            subprocess.run([str(host), "verify-lifetime"], capture_output=True, timeout=10, check=False).returncode == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        ready = False
    if not ready:
        result.append(("native_host_routing", "4444J99/domus-genoma", True, "stable_host_unavailable"))
    try:
        visual = json.loads((root / "docs/reviews/native-visual-20261012.json").read_text())
        age = (datetime.now(UTC) - datetime.fromisoformat(visual["observed_at"])).total_seconds()
        if visual.get("native_capture") is not True or not 0 <= age <= 7 * 86400:
            raise ValueError()
        for cause in sorted(set(visual.get("external_gates", []))):
            result.append(("native_visual_" + cause, "4444J99/domus-genoma", False, cause))
    except (OSError, ValueError, KeyError, TypeError):
        result.append(("native_visual_evidence", "4444J99/domus-genoma", False, "fresh_native_evidence_required"))
    return result


def packets(findings, previous, now):
    state = {}
    grouped = {}
    for signal, owner, healable, reason in sorted(set(findings)):
        old = previous.get(signal, {})
        count = min(4, old.get("observations", 0) + 1) if old.get("reason") == reason else 1
        state[signal] = {"reason": reason, "observations": count}
        packet = grouped.setdefault(
            owner,
            {
                "vendor": "operating-system-" + owner.rsplit("/", 1)[-1],
                "owner": owner,
                "run_at_iso": now,
                "sessions_seen": 0,
                "friction_signals": [],
            },
        )
        packet["friction_signals"].append(
            {
                "signal": signal,
                "owner": owner,
                "severity": "warning",
                "count": 1,
                "description": reason,
                "healable": healable and count <= 3,
                "suggested_action": "Reconcile owning source and regression predicate; unchanged repairs stop after three observations"
                if healable
                else "Resolve the recorded external acceptance gate; preserve platform safeguards",
            }
        )
    # Empty packets clear resolved findings in the existing consumer.
    for name in ("limen", "domus-genoma"):
        owner = "4444J99/" + name
        grouped.setdefault(
            owner,
            {
                "vendor": "operating-system-" + name,
                "owner": owner,
                "run_at_iso": now,
                "sessions_seen": 0,
                "friction_signals": [],
            },
        )
    return grouped, state


def write_health(root: Path, home: Path):
    from limen.io import atomic_write_text

    out = root / "logs/insight-cross-vendor"
    path = out / "state/operating-system.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(path.read_text())
    except (OSError, ValueError):
        previous = {}
    grouped, state = packets(observations(root, home), previous, datetime.now(UTC).isoformat())
    for packet in grouped.values():
        atomic_write_text(out / (packet["vendor"] + ".json"), json.dumps(packet) + "\n")
    atomic_write_text(path, json.dumps(state) + "\n")
