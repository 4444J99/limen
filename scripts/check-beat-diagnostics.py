#!/usr/bin/env python3
"""BEAT DIAGNOSTICS gate — a beat rung may not hide the reason it failed.

The idiom this forbids is ``<cmd> 2>&1 | tail -1``, and it is not a style preference. It
destroys three different things at once:

  1. **The exit status.** ``$?`` of a pipeline is the LAST stage's status, so it reports
     *tail's* result — essentially always 0. Any trailing ``|| true`` is therefore
     decorative, and no caller can distinguish a hard failure from a clean run.
  2. **The diagnostic.** ``tail -1`` of a Python traceback is the closing line of the
     exception's own repr. When the exception carries a JSON body that is a bare ``}``.
  3. **The record.** Nothing is written down, so a rung can fail on every beat forever
     while the beat log, the enactment audit, and the organ-health face all stay green.

Measured 2026-08-07, and the reason this gate exists: the ``heal-board.py --canonical``
rung (#2014) failed on EVERY beat with ``conduct broker rejected request (500): Exceeded
allowed rows written in Durable Objects free tier``. It emitted 61 diagnostic lines. The
beat log received ``}``. Neither "Durable Objects" nor "rejected request" appeared in ANY
log file estate-wide. That is the "signal with no effector" class one level up: the
failure had no reader, so twelve regressed board atoms stayed regressed behind a rung that
looked like it was working.

``scripts/heartbeat-loop.sh`` now routes every rung through its ``beat_run`` helper, which
keeps the happy path to one line, prints a real tail on failure, and records the outcome to
``logs/beat-rungs.jsonl`` so ``scripts/enactment-audit.py`` can see a failing streak.

Two rungs:

  A. **RATCHET (shrink-only).** Per-file counts of the blinding idiom may only go DOWN
     versus ``institutio/governance/beat-diagnostics-baseline.txt``. A new one is a red
     check. The sibling beat scripts are baselined at their current counts rather than
     rewritten here: ``beat_run`` is deliberately INLINE in heartbeat-loop.sh so the
     daemon gains no new file dependency, and giving the siblings a shared helper is its
     own change. The ratchet is what makes that a position rather than a leak.
  B. **HELPER INTEGRITY.** ``beat_run`` must still exist, must still print more than the
     last line on failure, and must still record the outcome. A well-meaning
     "simplification" back to ``tail -1`` inside the helper would restore the blindness
     while every count stayed at zero.

Usage:
  scripts/check-beat-diagnostics.py           # report
  scripts/check-beat-diagnostics.py --check   # gate: exit 1 on any violation
  scripts/check-beat-diagnostics.py --update  # rewrite the baseline (shrink-only; refuses growth)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "institutio" / "governance" / "beat-diagnostics-baseline.txt"
LOOP = ROOT / "scripts" / "heartbeat-loop.sh"

# Anchors for lifting the rung runner out of the shipped loop, so the integrity rung can RUN it.
ANCHOR_START = 'BEAT_RUNG_LOG="${LIMEN_BEAT_RUNG_LOG:-'
ANCHOR_END = "# BOUNDED WAKE"

# The beat's own shell surface. Every file here is executed by, or as, a heartbeat rung.
COVERED = [
    "scripts/heartbeat-loop.sh",
    "scripts/heartbeat.sh",
    "scripts/mail-beat.sh",
    "scripts/publish-board-pr.sh",
    "scripts/saturate.sh",
    "scripts/deploy-corpus-organs.sh",
]

# `2>&1 | tail -1` (or -n 1): merge stderr into stdout, then throw all but one line away.
BLIND = re.compile(r"2>&1\s*\|\s*tail\s+(?:-1\b|-n\s*1\b)")


def scan(path: Path) -> list[tuple[int, str]]:
    """Every blinding-idiom site in ``path``, as (1-indexed line number, text)."""
    if not path.exists():
        return []
    hits = []
    for n, line in enumerate(path.read_text().splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):  # the prohibition is quoted in prose; that is not a site
            continue
        if BLIND.search(line):
            hits.append((n, line.strip()))
    return hits


def read_baseline() -> dict[str, int]:
    """Declared ceiling per file. Missing file or missing entry both mean zero allowed."""
    allowed: dict[str, int] = {}
    if not BASELINE.exists():
        return allowed
    for raw in BASELINE.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        path, _, count = line.rpartition(" ")
        if not path or not count.isdigit():
            continue
        allowed[path.strip()] = int(count)
    return allowed


def helper_integrity() -> list[str]:
    """Rung B: the helper that replaced the idiom must still do all three jobs."""
    problems = []
    if not LOOP.exists():
        return [f"{LOOP} is missing — the beat has no loop body"]
    text = LOOP.read_text()
    if "\nbeat_run() {" not in text:
        problems.append("scripts/heartbeat-loop.sh defines no beat_run() — every rung is blind again")
        return problems
    # Behaviour, not text. A grep is exactly as blind as the idiom it polices: removing the
    # opening banner leaves "RUNG FAIL" intact in the CLOSING one, so a string check passes on a
    # helper that has already been gutted. So EXECUTE the shipped helper against a fabricated
    # failing rung and observe what it actually does — the same reason the loop's own tests run
    # the real bytes instead of asserting on source.
    start = text.find(ANCHOR_START)
    end = text.find(ANCHOR_END, start) if start != -1 else -1
    if start == -1 or end == -1:
        return [f"cannot locate the rung runner in {LOOP} (anchors {ANCHOR_START!r} / {ANCHOR_END!r})"]
    helper = text[start:end]

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "logs").mkdir()
        # Three lines; the LAST is the useless one. This is the measured shape: `tail -1` of the
        # real failure yielded `}` while the cause sat on the line above it.
        rung = "sh -c 'echo CAUSE-IS-HERE; echo middle; echo }; exit 9'"
        script = f'LIMEN_ROOT="{root}"\n{helper}\nbeat_run probe-rung {rung}\necho "BEAT_RUN_RC=$?"\n'
        try:
            res = subprocess.run(
                ["bash", "-c", script],
                capture_output=True,
                text=True,
                timeout=30,
                env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LIMEN_ROOT": str(root)},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return [f"could not execute the rung runner: {exc}"]

        if "CAUSE-IS-HERE" not in res.stdout:
            problems.append(
                "beat_run drops a failing rung's real output — only the last line survives, "
                "which is the exact blindness this gate exists to prevent"
            )
        if "probe-rung" not in res.stdout:
            problems.append("beat_run no longer names the failing rung — a failure cannot be attributed")
        if "BEAT_RUN_RC=0" not in res.stdout:
            # The helper's stated contract. `|| true` at the call sites is what actually keeps the
            # beat alive today, so this is belt-and-braces — but a helper that silently starts
            # propagating status is exactly the kind of drift nobody notices until a `stamp` is
            # skipped and a voice goes stale for a week.
            problems.append(
                "beat_run is no longer fail-open — it propagates the rung's exit status instead of absorbing it"
            )

        ledger = root / "logs" / "beat-rungs.jsonl"
        if not ledger.exists() or not ledger.read_text().strip():
            problems.append("beat_run records no outcome — enactment-audit cannot see a failing streak")
        else:
            try:
                row = json.loads(ledger.read_text().splitlines()[-1])
            except (ValueError, IndexError):
                problems.append("beat_run's outcome ledger is not one JSON object per line")
            else:
                if row.get("exit") != 9:
                    problems.append(
                        f"beat_run recorded exit={row.get('exit')!r} for a rung that exited 9 — "
                        "it is reporting the pipeline's status, not the rung's"
                    )
                if row.get("rung") != "probe-rung":
                    problems.append("beat_run's ledger does not carry a stable rung label (the streak bucket)")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on any violation")
    ap.add_argument("--update", action="store_true", help="rewrite the baseline (shrink-only)")
    args = ap.parse_args(argv)

    allowed = read_baseline()
    current = {rel: scan(ROOT / rel) for rel in COVERED}
    violations: list[str] = []
    grew: dict[str, tuple[int, int]] = {}

    for rel in COVERED:
        hits = current[rel]
        ceiling = allowed.get(rel, 0)
        if len(hits) > ceiling:
            grew[rel] = (ceiling, len(hits))
            violations.append(f"{rel}: {len(hits)} blinding rung(s), baseline allows {ceiling}")
            for n, text in hits[ceiling:] if ceiling else hits:
                violations.append(f"    {rel}:{n}  {text[:120]}")

    problems = helper_integrity()

    if args.update:
        if grew:
            print("FAIL beat-diagnostics: --update would GROW the baseline. The ratchet is shrink-only.")
            for rel, (was, now) in sorted(grew.items()):
                print(f"  {rel}: {was} -> {now}")
            print("Route each new rung through beat_run instead, or state why the baseline must move.")
            return 1
        lines = [
            "# BEAT DIAGNOSTICS baseline — per-file ceiling for `2>&1 | tail -1` rungs.",
            "# Shrink-only: scripts/check-beat-diagnostics.py refuses an --update that grows any count.",
            "# heartbeat-loop.sh is at 0 — every rung goes through beat_run. The siblings are held here",
            "# because beat_run is inline in the loop by design (the daemon takes on no new file",
            "# dependency); giving them a shared helper is its own change, and this ceiling is what",
            "# keeps that a position rather than a leak.",
        ]
        for rel in COVERED:
            lines.append(f"{rel} {len(current[rel])}")
        BASELINE.write_text("\n".join(lines) + "\n")
        print(
            f"beat-diagnostics: baseline written — {sum(len(v) for v in current.values())} site(s) across {len(COVERED)} file(s)"
        )
        return 0

    total = sum(len(v) for v in current.values())
    loop_count = len(current["scripts/heartbeat-loop.sh"])
    print(
        f"beat-diagnostics: {total} blinding rung(s) across {len(COVERED)} beat script(s); heartbeat-loop.sh at {loop_count}"
    )
    for rel in COVERED:
        ceiling = allowed.get(rel, 0)
        mark = "✅" if len(current[rel]) <= ceiling else "❌"
        print(f"  {mark} {rel}: {len(current[rel])} (ceiling {ceiling})")

    if problems:
        print("HELPER INTEGRITY:")
        for p in problems:
            print(f"  ❌ {p}")
    else:
        print("  ✅ beat_run intact — captures its own status, prints a real tail, records the outcome")

    if violations or problems:
        if args.check:
            print("\nFAIL beat-diagnostics:", file=sys.stderr)
            for v in violations + problems:
                print(f"  {v}", file=sys.stderr)
            return 1
        return 0
    print("OK beat-diagnostics — no rung hides the reason it failed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
