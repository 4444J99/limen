#!/usr/bin/env python3
"""host-pressure-stale — watch the watcher (sensor 0o).

The VITALS gauge (memory + load axes) is the hand that throttles/sheds under host
pressure; if the gauge itself goes silent, the valve is flying blind and nothing else
notices — the exact failure mode the sensors registry warns about. This rung fails when
the ``sampled_at`` record in ``logs/vigilia/status.json`` (written by the heartbeat's
independent fast wave) misses VITALS_STALE_BEATS declared sample cadences
(x LIMEN_VITALS_SAMPLE_SECONDS), allowing one bounded sampler/write grace
(LIMEN_VITALS_SAMPLE_TIMEOUT + LIMEN_VITALS_SAMPLE_GRACE_SECONDS) at the cadence boundary, or is absent entirely while
VIGILIA is on (LIMEN_VIGILIA unset counts as on — the heartbeat's own default).

The alarm is the staleness, not the pressure: the effector for pressure itself remains
the existing THROTTLE/SHED path in heartbeat-loop.sh. Exit 0 = gauge alive (or VIGILIA
deliberately off). Exit 1 = gauge silent — and since 2026-07-16 (IF-HOST-PRESSURE
form 4) a silent gauge also fires ONE onset-deduped macOS notification via
scripts/_notify.py: a blind valve was exactly the 7/15 gap, and an advisory line in a
log no one is reading is not an alarm. Read-only otherwise; advisory in the registry.
"""

from __future__ import annotations

import argparse
import json
import os
import hashlib
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _notify  # noqa: E402

STALE_KEY = "vitals-stale"


def _boot_identity() -> str:
    try:
        result = subprocess.run(["sysctl", "-n", "kern.boottime"], capture_output=True, text=True, timeout=3)
        return hashlib.sha256(result.stdout.strip().encode()).hexdigest()[:20]
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def _active_monotonic() -> float:
    return time.clock_gettime(getattr(time, "CLOCK_UPTIME_RAW", time.CLOCK_MONOTONIC))


def _root() -> Path:
    env = os.environ.get("LIMEN_ROOT")
    if env:
        return Path(env).expanduser()
    return Path(__file__).resolve().parents[1]


def _env_value(raw: str) -> str:
    """Parse one shell-style assignment value without treating quoted ``#`` as a comment."""
    quote: str | None = None
    escaped = False
    for index, char in enumerate(raw):
        if escaped:
            escaped = False
            continue
        if char == "\\" and quote != "'":
            escaped = True
            continue
        if quote:
            if char == quote:
                quote = None
            continue
        if char in ("'", '"'):
            quote = char
        elif char == "#" and (index == 0 or raw[index - 1].isspace()):
            raw = raw[:index]
            break
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        value = value[1:-1]
    return value


def _configured_env(name: str, default: str) -> str:
    """Read launchd/interactive env first, then the shared ~/.limen.env declaration."""
    if name in os.environ:
        return os.environ[name]
    env_file = Path(os.environ.get("LIMEN_ENV_FILE", Path.home() / ".limen.env")).expanduser()
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("export "):
                line = line[7:].lstrip()
            if line.startswith(f"{name}="):
                return _env_value(line.split("=", 1)[1])
    except OSError:
        pass
    return default


def _positive_float(name: str, default: float) -> float:
    try:
        value = float(_configured_env(name, str(default)))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _sample_seconds() -> float:
    """Mirror heartbeat-loop.sh: accept positive integers, otherwise use 300."""
    raw = _configured_env("LIMEN_VITALS_SAMPLE_SECONDS", "300")
    return float(raw) if raw.isdigit() and int(raw) > 0 else 300.0


def _sample_timeout_seconds() -> float:
    """Mirror the heartbeat's positive-integer VIGILIA sampler timeout."""
    raw = _configured_env("LIMEN_VITALS_SAMPLE_TIMEOUT", "30")
    return float(min(int(raw), 3600)) if raw.isdigit() and int(raw) > 0 else 30.0


def _sample_grace_seconds(sample_seconds: float) -> float:
    """Cover the sampler runtime plus the small producer-write boundary."""
    write_grace = min(_positive_float("LIMEN_VITALS_SAMPLE_GRACE_SECONDS", 5.0), sample_seconds)
    return write_grace + _sample_timeout_seconds()


def _stale(message: str, *, read_only: bool) -> int:
    print(message)
    if not read_only:
        _notify.notify_once(_root(), STALE_KEY, message)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--read-only",
        action="store_true",
        help="evaluate freshness without notification or dedupe-state writes",
    )
    args = parser.parse_args(argv)
    if _configured_env("LIMEN_VIGILIA", "1") in ("0", "false", "False"):
        print("host-pressure-stale: VIGILIA off — nothing to watch")
        return 0
    if _configured_env("LIMEN_HOST_PRESSURE_STALE", "1") in ("0", "false", "False"):
        print("host-pressure-stale: watchdog off — nothing to evaluate")
        return 0

    stale_beats = _positive_float("LIMEN_VITALS_STALE_BEATS", 3)
    sample_seconds = _sample_seconds()
    budget_s = stale_beats * sample_seconds
    grace_s = _sample_grace_seconds(sample_seconds)
    stale_after_s = budget_s + grace_s

    status_path = _root() / "logs" / "vigilia" / "status.json"
    if not status_path.exists():
        return _stale(
            f"host-pressure-stale: STALE — {status_path} absent while VIGILIA on",
            read_only=args.read_only,
        )

    try:
        payload = json.loads(status_path.read_text())
        wake_state = str(payload.get("wake_state") or "legacy")
        if wake_state in {"Sleep", "MaintenanceDarkWake", "DarkWake"}:
            print(f"host-pressure-stale: grace — wake_state={wake_state} cannot page")
            return 0
        boot_identity = payload.get("boot_identity")
        sampled_monotonic = payload.get("sampled_monotonic_seconds")
        if boot_identity != _boot_identity() or not isinstance(sampled_monotonic, (int, float)):
            print("host-pressure-stale: STALE — reboot/legacy metadata requires one bounded sample-first refresh")
            if not args.read_only:
                try:
                    subprocess.run(
                        [sys.executable, "-m", "limen.vigilia", "sample"],
                        cwd=_root(),
                        timeout=30,
                        capture_output=True,
                        check=False,
                    )
                except (OSError, subprocess.SubprocessError):
                    pass
                return 0
            return 1
        sampled_raw = payload.get("sampled_at") or payload.get("completed_at") or payload.get("ts") or ""
        if not sampled_raw:
            return _stale(
                f"host-pressure-stale: STALE — no timestamp in {status_path}",
                read_only=args.read_only,
            )
        sampled_at = datetime.fromisoformat(sampled_raw.replace("Z", "+00:00"))
        if sampled_at.tzinfo is None:
            sampled_at = sampled_at.replace(tzinfo=timezone.utc)
    except Exception as exc:
        return _stale(
            f"host-pressure-stale: STALE — unreadable timestamp in {status_path} ({exc})",
            read_only=args.read_only,
        )

    age_s = max(0.0, _active_monotonic() - float(sampled_monotonic))
    if age_s >= stale_after_s:
        return _stale(
            f"host-pressure-stale: STALE — vitals record is {age_s / 60:.0f} min old "
            f"(budget {budget_s / 60:.0f} min = {stale_beats:g} x LIMEN_VITALS_SAMPLE_SECONDS "
            f"+ {grace_s:.0f}s sampler/write grace); the throttle/shed valve is flying blind",
            read_only=args.read_only,
        )

    if not args.read_only:
        _notify.clear_condition(_root(), STALE_KEY)
    print(f"host-pressure-stale: ok — vitals record {age_s / 60:.1f} min old (budget {budget_s / 60:.0f} min)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
