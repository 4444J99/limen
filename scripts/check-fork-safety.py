#!/usr/bin/env python3
"""check-fork-safety.py — self-verifying predicate for the macOS 26.6 fork/os_log crash.

The gap this closes. A real macOS 26.6 crash ("python keeps crashing") was root-caused to
Apple's Network.framework ``pthread_atfork`` child handler segfaulting in ``os_log``
(``nw_settings_child_has_forked`` → ``_os_log_preferences_refresh``) on the child side of
``fork()+exec()``. The fix — ``export OS_ACTIVITY_MODE=disable`` before any python launches —
is shipped to scripts/metabolize.sh + scripts/heartbeat-loop.sh (limen #831) and
domus-genoma/dot_zshenv.tmpl (#229). But the crash is a *timing race*: it killed a fraction
of forks and could not be force-reproduced. So the fix was "verified" only by absence of
recurrence — a hope, not a predicate. That violates two charter laws (Definition of Done =
executable predicate; sensor-without-effector = defect). This script makes the fix
self-verifying and beat-wired: green ⟺ mitigation present AND no matching crash newer than the
mitigation boundary; on a recurrence it exits non-zero so the beat surfaces the escalation.

Corrected mechanism note (empirically confirmed, python 3.14.6, this box): on macOS
``subprocess._HAVE_POSIX_SPAWN_CLOSEFROM`` is False, so the default ``close_fds=True`` sends
*essentially every* subprocess call through ``fork()`` — not just ``cwd=``/``preexec_fn`` ones.
A posix_spawn "cure" is therefore invasive AND partial (can never cover ``start_new_session``
group-kill callers), while OS_ACTIVITY_MODE fixes the os_log layer for ALL fork paths. The
posix_spawn arm (LIMEN_FORK_SAFE) stays dark, armed only if THIS predicate ever fires.

Two clauses, both must be green:
  1. MITIGATION PRESENT — ``OS_ACTIVITY_MODE`` is exported in the beat scripts (committed files).
  2. NO POST-MITIGATION CRASH — no .ips crash report matching the signature has an mtime newer
     than the mitigation boundary (git author-date of the OS_ACTIVITY_MODE commit).

Boundary is DERIVED, never hardcoded: git author-date of the commit that added OS_ACTIVITY_MODE
to scripts/metabolize.sh; fallback to a committed marker (scripts/.fork-safety-since); if
neither is available the crash clause fails OPEN (reports matches, does not gate the beat).

PII-clean: only basenames, matched frame keyword, and ISO times are printed — never report bodies.

Exit codes: 0 = green; 1 = mitigation missing OR a post-boundary crash recurred (with --check).

Usage:
  python3 scripts/check-fork-safety.py                 # report + stamp, exit 0
  python3 scripts/check-fork-safety.py --check         # gate mode: exit 1 on failure
  python3 scripts/check-fork-safety.py --reports-dir D  # scan D/*.ips + D/Retired/*.ips (tests)
  python3 scripts/check-fork-safety.py --since EPOCH|ISO # override the boundary (tests)
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))

# The atfork/os_log crash signature. Any one frame is sufficient — the child-side atfork handler
# and its os_log victim are both diagnostic of THIS bug and appear in no benign python crash.
SIGNATURE_RE = re.compile(
    r"nw_settings_child_has_forked|_os_log_preferences_refresh|child side of fork",
    re.IGNORECASE,
)

# Beat scripts that must carry the mitigation for clause 1 to be green.
MITIGATION_SCRIPTS = ("scripts/metabolize.sh", "scripts/heartbeat-loop.sh")
MITIGATION_TOKEN = "OS_ACTIVITY_MODE"

DEFAULT_REPORTS_DIR = Path.home() / "Library" / "Logs" / "DiagnosticReports"
MARKER = SCRIPT_ROOT / "scripts" / ".fork-safety-since"


def _parse_since(raw):
    """Accept an epoch-seconds string or an ISO-8601 timestamp; return epoch float or None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        pass
    try:
        # tolerate a trailing Z
        return datetime.datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def mitigation_boundary(override=None):
    """Epoch seconds separating pre-fix crashes from a true recurrence, and how it was found.

    Order: explicit override → git author-date of the OS_ACTIVITY_MODE commit → committed marker.
    Returns (epoch_or_None, source_str).
    """
    ov = _parse_since(override)
    if ov is not None:
        return ov, "override"
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(ROOT),
                "log",
                "-1",
                "--format=%at",
                "-S",
                MITIGATION_TOKEN,
                "--",
                "scripts/metabolize.sh",
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        val = out.stdout.strip()
        if out.returncode == 0 and val:
            return float(val), "git"
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    if MARKER.exists():
        mv = _parse_since(MARKER.read_text(encoding="utf-8", errors="ignore"))
        if mv is not None:
            return mv, "marker"
    return None, "none"


def mitigation_present():
    """Clause 1: OS_ACTIVITY_MODE exported in every beat script. Returns (ok, missing_list)."""
    missing = []
    for rel in MITIGATION_SCRIPTS:
        p = ROOT / rel
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            missing.append(rel)
            continue
        if MITIGATION_TOKEN not in text:
            missing.append(rel)
    return (not missing), missing


def _ips_files(reports_dir):
    """Every .ips under reports_dir and its Retired/ rotation subdir."""
    for base in (reports_dir, reports_dir / "Retired"):
        if not base.is_dir():
            continue
        for p in sorted(base.glob("*.ips")):
            yield p


def scan_crashes(reports_dir, boundary):
    """Clause 2: crash reports matching the signature. Returns (all_matches, recurrences).

    Each entry: {name, mtime_iso, mtime, frame}. A recurrence is a match with mtime > boundary
    (when a boundary is known). mtime (epoch) is tz-free and set at write == crash time.
    """
    all_matches, recurrences = [], []
    for p in _ips_files(reports_dir):
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        m = SIGNATURE_RE.search(text)
        if not m:
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        entry = {
            "name": p.name,
            "mtime": mtime,
            "mtime_iso": datetime.datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
            "frame": m.group(0),
        }
        all_matches.append(entry)
        if boundary is not None and mtime > boundary:
            recurrences.append(entry)
    return all_matches, recurrences


def _stamp(payload):
    """Best-effort log stamp; never fatal (fail-open on unwritable paths)."""
    try:
        logs = ROOT / "logs"
        logs.mkdir(exist_ok=True)
        (logs / "fork-safety.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="macOS fork/os_log crash predicate")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on failure")
    ap.add_argument(
        "--reports-dir",
        default=os.environ.get("LIMEN_CRASH_REPORTS_DIR"),
        help="crash-report root (default ~/Library/Logs/DiagnosticReports)",
    )
    ap.add_argument("--since", default=None, help="override boundary (epoch or ISO-8601)")
    args = ap.parse_args(argv)

    reports_dir = Path(args.reports_dir) if args.reports_dir else DEFAULT_REPORTS_DIR
    boundary, source = mitigation_boundary(args.since)
    mit_ok, missing = mitigation_present()
    matches, recurrences = scan_crashes(reports_dir, boundary)

    boundary_iso = (
        datetime.datetime.fromtimestamp(boundary).isoformat(timespec="seconds") if boundary is not None else None
    )
    failed = (not mit_ok) or bool(recurrences)

    payload = {
        "mitigation_present": mit_ok,
        "mitigation_missing": missing,
        "boundary_epoch": boundary,
        "boundary_iso": boundary_iso,
        "boundary_source": source,
        "reports_dir": str(reports_dir),
        "matches_total": len(matches),
        "recurrences": recurrences,
        "green": not failed,
    }
    _stamp(payload)

    # Human-readable report (PII-clean: basenames + frame keyword + ISO only).
    print("── fork-safety predicate (macOS 26.6 atfork/os_log crash) ──")
    if mit_ok:
        print(f"  ✓ mitigation OS_ACTIVITY_MODE present in {len(MITIGATION_SCRIPTS)} beat script(s)")
    else:
        print(f"  ✗ mitigation MISSING from: {', '.join(missing)}")
    if boundary is None:
        print("  ⚠ mitigation boundary UNDERIVABLE (no git, no marker) — crash clause fails OPEN")
    else:
        print(
            f"  • boundary {boundary_iso} (via {source}); "
            f"{len(matches)} known crash(es), {len(recurrences)} after boundary"
        )
    for e in recurrences:
        print(f"    ↳ RECURRENCE {e['name']} @ {e['mtime_iso']} [{e['frame']}]")

    if failed:
        if not mit_ok:
            print("  RESULT: RED — mitigation removed; restore OS_ACTIVITY_MODE=disable in the beat scripts")
        if recurrences:
            print(
                "  RESULT: RED — crash recurred DESPITE mitigation; arm the posix_spawn escalation "
                "(LIMEN_FORK_SAFE=1) — see scripts/check-fork-safety.py docstring"
            )
    else:
        print("  RESULT: GREEN")

    return 1 if (failed and args.check) else 0


if __name__ == "__main__":
    sys.exit(main())
