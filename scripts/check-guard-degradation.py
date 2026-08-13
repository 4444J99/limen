#!/usr/bin/env python3
"""check-guard-degradation.py — the declared-population ratchet for "a guard that cannot see must WARN".

F7 of the 2026-08-07 cadence-guard arc. The arc fixed FOUR instances of one defect by hand; this
is what stops the fifth from being found by an incident instead of by a predicate.

Two halves, and the second is the point:

  POPULATION   Every parameters.yaml row carrying a `guard_state:` block declares a guard subject
               to the invariant. The population is RATCHETED against
               institutio/governance/guard-state-baseline.txt: it may grow, never shrink. Deleting
               a guard's declaration is exactly how a class-wide invariant quietly stops covering
               the thing it was written for, so removing a line is a RED, not a cleanup.

  PROOF        Each declared guard is EXECUTED against its degenerate inputs — not inspected. This
               distinction is the whole lesson: `verify-fable-gate.sh` was GREEN throughout the
               incident, all five blocks passing, because the question it asked was answered
               correctly by a meter that was itself lying. Inspection cannot catch a guard whose
               code looks right and whose input is wrong; execution against a degenerate input can.

A finding is any declared guard that, handed an input it cannot resolve, returns TRUSTED — or
returns something this contract cannot read, or raises. (A guard that crashes is not failing safe:
a SessionStart hook's command ends `|| true`, so at the surface that matters a crash and a silence
are the same event.)

Fixture tokens usable in a case's `env` map, materialized fresh in a tmpdir each run so the proof
is hermetic and idempotent:

  @missing    a path that does not exist
  @garbage    a file that is not JSON
  @notdict    valid JSON of the wrong shape
  @staleweek  a well-formed meter for a PRIOR ISO week
  @frozen     a well-formed CURRENT-week meter whose mtime is days old (the writer stopped)

Exit 0 ⟺ every declared guard degrades toward the warning AND the population has not shrunk.
"""

from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PARAMS = ROOT / "institutio" / "governance" / "parameters.yaml"
BASELINE = ROOT / "institutio" / "governance" / "guard-state-baseline.txt"

sys.path.insert(0, str(ROOT / "cli" / "src"))


def _monday() -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return (now - dt.timedelta(days=now.weekday())).date().isoformat()


def _meter(week: str) -> str:
    return json.dumps({"week": week, "spent_pct": 5.0, "deliberate_cap": 40, "hard_cap": 50, "over_cap": False})


def materialize(tmp: Path) -> dict[str, str]:
    """Build every fixture token once. Hermetic: nothing outside `tmp` is touched or read."""
    missing = tmp / "does-not-exist.json"

    garbage = tmp / "garbage.json"
    garbage.write_text("{ this is not json")

    notdict = tmp / "notdict.json"
    notdict.write_text("[1, 2, 3]")

    staleweek = tmp / "staleweek.json"
    staleweek.write_text(_meter("2020-01-06"))

    frozen = tmp / "frozen.json"
    frozen.write_text(_meter(_monday()))
    old = frozen.stat().st_mtime - 60 * 60 * 24 * 5
    os.utime(frozen, (old, old))

    return {
        "@missing": str(missing),
        "@garbage": str(garbage),
        "@notdict": str(notdict),
        "@staleweek": str(staleweek),
        "@frozen": str(frozen),
    }


def declared_guards() -> dict[str, dict]:
    """{param name: guard_state block} for every parameters.yaml row declaring one."""
    import yaml

    doc = yaml.safe_load(PARAMS.read_text(encoding="utf-8")) or {}
    found: dict[str, dict] = {}

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if isinstance(value, dict) and isinstance(value.get("guard_state"), dict):
                    found[str(key)] = value["guard_state"]
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(doc)
    return found


def _resolve(reader_ref: str):
    module_name, _, attr = str(reader_ref).partition(":")
    module = importlib.import_module(module_name)
    return getattr(module, attr)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update-baseline", action="store_true", help="record the CURRENT population (growth only)")
    args = ap.parse_args(argv)

    from limen import guard_contract  # noqa: PLC0415 — sys.path is set above

    guards = declared_guards()
    if not guards:
        print("check-guard-degradation: RED — no guard_state rows declared at all", file=sys.stderr)
        return 1

    prior = set()
    if BASELINE.exists():
        prior = {ln.strip() for ln in BASELINE.read_text().splitlines() if ln.strip() and not ln.startswith("#")}

    findings: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        tokens = materialize(Path(td))
        for name, block in sorted(guards.items()):
            try:
                reader = _resolve(block.get("reader", ""))
            except Exception as exc:  # noqa: BLE001 — an unresolvable reader is a finding
                findings.append(f"{name}: reader {block.get('reader')!r} unresolvable ({type(exc).__name__}: {exc})")
                continue
            cases = []
            for case in block.get("degenerate") or []:
                env = {k: tokens.get(str(v), str(v)) for k, v in (case.get("env") or {}).items()}
                cases.append({"name": case.get("name", "unnamed"), "env": env, "args": case.get("args") or []})
            if not cases:
                findings.append(f"{name}: declares a guard but NO degenerate cases — an unproven claim")
                continue
            for f in guard_contract.check_degrades(reader, cases):
                findings.append(f"{name} / {f['case']}: {f['why']}")
            print(f"  ok   {name}: {len(cases)} degenerate case(s) all degrade toward the warning")

    shrunk = sorted(prior - set(guards))
    if shrunk:
        findings.append(
            "POPULATION SHRANK — these guards lost their guard_state declaration: "
            + ", ".join(shrunk)
            + ". Removing a declaration is how a class-wide invariant quietly stops covering its subject."
        )

    if args.update_baseline and not findings:
        BASELINE.write_text(
            "# Declared population for check-guard-degradation.py — GROW-ONLY.\n"
            "# Each line is a parameters.yaml row carrying a `guard_state:` block.\n"
            + "".join(f"{n}\n" for n in sorted(guards))
        )
        print(f"check-guard-degradation: baseline updated — {len(guards)} declared guard(s)")
        return 0

    # Machine line (parsed by scripts/check-ideal-forms.py via the ideal-forms registry's
    # `extract`). Printed on BOTH paths: a measurement that only appears when green is a
    # measurement that disappears exactly when it matters.
    print(f"guard-degradation: declared={len(guards)} findings={len(findings)}")

    if findings:
        for f in findings:
            print(f"  FAIL {f}", file=sys.stderr)
        print(f"check-guard-degradation: RED — {len(findings)} finding(s)", file=sys.stderr)
        return 1

    print(f"check-guard-degradation: OK — {len(guards)} declared guard(s), every degenerate input degrades")
    return 0


if __name__ == "__main__":
    sys.exit(main())
