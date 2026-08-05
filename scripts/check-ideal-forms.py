#!/usr/bin/env python3
"""IDEAL-FORMS drift predicate — holds the ledger of ideals to a DERIVED distance.

Exit 0 iff institutio/governance/ideal-forms.yaml is internally coherent AND no ledger prose
contradicts a live measurement:

  A  schema      — required fields present; NO row carries a hand-written distance or status
                   (the session-streams check-F rule: there is no field to lie in).
  B  parity      — every `### IF-*` heading in docs/IDEAL-FORMS-LEDGER.md has a registry row
                   and every row has a heading. Both directions, exact.
  C  probe shape — environment in enum; EXACTLY one of at_ideal_when / (extract + ideal_value);
                   any script the command names exists; the extract compiles; and the cycle
                   guard holds (only the `self` environment may name this predicate).
  D  the loop    — for every probe actually run, the ledger's prose **Status:** must agree with
                   the derived verdict. A heading that says DONE while its probe reports
                   distance (or OPEN while its probe is at ideal) is DRIFT, not a stale note.
                   This is the check that would have caught IF-LIVE-TREE-COHERENCE's "behind
                   24" sitting in the doc while the real number was 120.
  E  vacuums     — `probe: null` REQUIRES `probe_absent_reason`, and the unmeasured rows are
                   counted loudly (Rule #1: a vacuum is never a resting state).
  F  no hand-written distance — a row WITH a probe may not carry a hand-written `**Distance:**`
                   in the ledger prose; it must point at the command. Check A forbids the field
                   in the REGISTRY and never looked at the doc, so the doc is where the field
                   survived: IF-AMALGAMATION's Distance read "75 open PRs, 157 unmerged branches
                   (2026-06-25)" for 38 days while the real figure passed 1,100 — off by 15x, in
                   a registry whose header says there is no field to lie in. There was one.
                   Narrative is not the problem and keeps its place on an `**Evidence:**` line;
                   only the NUMBER has to be derived.

Only `environment: repo` probes run inside this check — they are the ones that bind anywhere.
`host` / `network` probes cannot be proven here (the check-corpora/check-convergence rule:
absence of evidence on a CI runner is a host fact, not drift), and `self` is never executed.

    python3 scripts/check-ideal-forms.py            # the gate
    python3 scripts/check-ideal-forms.py --measure  # run EVERY runnable probe, print distances

`--measure` is how a distance gets updated: by command, never by memory.

Run directly, via pr-gate, or verify-whole. Fails toward caution: a broken registry is RED.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "institutio" / "governance" / "ideal-forms.yaml"
LEDGER = ROOT / "docs" / "IDEAL-FORMS-LEDGER.md"
SELF_NAME = "check-ideal-forms.py"

VALID_ENVIRONMENT = {"repo", "host", "network", "self"}
REQUIRED_FIELDS = ("ideal", "owner")
# The whole point of the registry: a distance may not be written down anywhere in it.
FORBIDDEN_FIELDS = ("status", "distance", "distance_pinned", "state", "measured_at", "done")

HEADING_RE = re.compile(r"^### (IF-[A-Z0-9-]+)\b", re.MULTILINE)
STATUS_RE = re.compile(r"^- \*\*Status:\*\*\s*(.+)$", re.MULTILINE)
DISTANCE_RE = re.compile(r"^- \*\*Distance[^:]*:\*\*\s*(.+)$", re.MULTILINE)
# The one phrase a probed row's Distance line is allowed to be. Not a format preference: any
# other content is a number a human typed, and a number a human typed is the thing check F exists
# to make impossible. `--measure` is how the real one is obtained.
DERIVED_MARK = "DERIVED"

failures: list[str] = []
notes: list[str] = []


def fail(check: str, msg: str) -> None:
    failures.append(f"  ✗ [{check}] {msg}")


def note(msg: str) -> None:
    notes.append(f"  ↑ {msg}")


def _script_in(command: str) -> Path | None:
    """The repo-relative script a probe command invokes, if it names one."""
    for token in command.split():
        if token.endswith((".py", ".sh")) and "/" in token:
            return ROOT / token
    return None


def run_probe(probe: dict) -> tuple[str, str]:
    """Return (verdict, detail). verdict ∈ at-ideal | distance-remains | unmeasured."""
    command = probe["command"]
    proc = subprocess.run(command, shell=True, cwd=ROOT, capture_output=True, text=True, check=False, timeout=300)
    output = (proc.stdout or "") + (proc.stderr or "")

    if probe.get("at_ideal_when") == "exit_zero":
        if proc.returncode == 0:
            return "at-ideal", "exit 0"
        return "distance-remains", f"exit {proc.returncode}"

    pattern = probe.get("extract", "")
    match = re.search(pattern, output)
    if not match:
        # A probe whose output no longer matches its extract is drift in the PROBE, not a pass.
        return "unmeasured", f"extract {pattern!r} matched nothing in the probe's output"
    measured = int(match.group(1))
    ideal = probe.get("ideal_value")
    verdict = "at-ideal" if measured == ideal else "distance-remains"
    return verdict, f"{measured} (ideal {ideal})"


def ledger_sections() -> dict[str, str]:
    """Map IF-id -> the prose Status line the ledger currently claims."""
    text = LEDGER.read_text(encoding="utf-8")
    ids = HEADING_RE.findall(text)
    spans = [m.start() for m in HEADING_RE.finditer(text)] + [len(text)]
    out = {}
    for i, ident in enumerate(ids):
        body = text[spans[i] : spans[i + 1]]
        status = STATUS_RE.search(body)
        out[ident] = status.group(1).strip() if status else ""
    return out


def ledger_distances() -> dict[str, list[str]]:
    """Map IF-id -> every `**Distance:**` line its ledger entry writes down.

    A list, not a single value: two Distance lines in one entry is the same defect twice, and
    reading only the first is how the compound-claim bug in check D happened.
    """
    text = LEDGER.read_text(encoding="utf-8")
    ids = HEADING_RE.findall(text)
    spans = [m.start() for m in HEADING_RE.finditer(text)] + [len(text)]
    return {ident: DISTANCE_RE.findall(text[spans[i] : spans[i + 1]]) for i, ident in enumerate(ids)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--measure", action="store_true", help="run every runnable probe and print derived distances")
    args = ap.parse_args()

    if not REGISTRY.is_file():
        print(f"FAILED: check-ideal-forms — registry missing at {REGISTRY}")
        return 1
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    ideals = doc.get("ideals") or {}
    vocab = doc.get("prose_status_vocabulary") or {}
    at_ideal_words = set(vocab.get("at_ideal") or [])
    remains_words = set(vocab.get("distance_remains") or [])
    if not ideals:
        fail("A", "registry has no `ideals` block")

    prose = ledger_sections()
    distances = ledger_distances()

    # B: parity, both directions.
    for ident in sorted(set(ideals) - set(prose)):
        fail("B", f"{ident}: registry row has no `### {ident}` heading in {LEDGER.relative_to(ROOT)}")
    for ident in sorted(set(prose) - set(ideals)):
        fail("B", f"{ident}: ledger heading has no registry row — every ideal is a tracked param")

    unmeasured, measured_rows = [], []

    for ident, row in sorted(ideals.items()):
        if not isinstance(row, dict):
            fail("A", f"{ident}: row must be a mapping")
            continue

        # A: required fields + the no-hand-state rule.
        for field in REQUIRED_FIELDS:
            if not str(row.get(field) or "").strip():
                fail("A", f"{ident}: missing `{field}`")
        for field in FORBIDDEN_FIELDS:
            if field in row:
                fail(
                    "A",
                    f"{ident}: carries `{field}` — a distance/status is DERIVED, never written. "
                    "Delete the field; `--measure` is how the number is obtained.",
                )

        probe = row.get("probe")

        # F: a probed row's distance is a COMMAND's output, never a sentence someone wrote.
        #
        # Deliberately scoped to probed rows. A `probe: null` row has no derivation, so prose is
        # all it has — check E already counts those loudly, and forbidding their Distance too
        # would delete information without replacing it. This forbids the number exactly where a
        # command can supply it, which is the only place a written one can silently go stale.
        if probe is not None:
            for line in distances.get(ident, []):
                if DERIVED_MARK not in line:
                    fail(
                        "F",
                        f"{ident}: ledger writes a Distance by hand — {line[:60]!r}… — while the row "
                        f"HAS a probe. Replace with `- **Distance:** {DERIVED_MARK} — "
                        "`python3 scripts/check-ideal-forms.py --measure`.` and move the narrative "
                        "to an `**Evidence:**` line.",
                    )
            if not distances.get(ident):
                fail(
                    "F",
                    f"{ident}: probed row has no `**Distance:**` line — a reader cannot tell where the number comes from",
                )

        # E: an absent probe is legal but must name why, and is counted.
        if probe is None:
            if not str(row.get("probe_absent_reason") or "").strip():
                fail("E", f"{ident}: probe is null without `probe_absent_reason` — an unnamed vacuum")
            unmeasured.append(ident)
            continue
        if not isinstance(probe, dict):
            fail("C", f"{ident}: probe must be a mapping or null")
            continue

        # C: probe shape.
        command = str(probe.get("command") or "").strip()
        if not command:
            fail("C", f"{ident}: probe has no `command`")
            continue
        if not str(probe.get("derives") or "").strip():
            fail("C", f"{ident}: probe has no `derives` — an unexplained number is not a measurement")
        env = probe.get("environment")
        if env not in VALID_ENVIRONMENT:
            fail("C", f"{ident}: environment {env!r} not in {sorted(VALID_ENVIRONMENT)}")

        has_exit = probe.get("at_ideal_when") == "exit_zero"
        has_extract = "extract" in probe or "ideal_value" in probe
        if has_exit and has_extract:
            fail("C", f"{ident}: declare EXACTLY one of at_ideal_when / (extract + ideal_value)")
        elif not has_exit and not has_extract:
            fail("C", f"{ident}: probe declares no verdict rule")
        elif has_extract:
            if "extract" not in probe or "ideal_value" not in probe:
                fail("C", f"{ident}: extract and ideal_value must be declared together")
            else:
                try:
                    re.compile(probe["extract"])
                except re.error as exc:
                    fail("C", f"{ident}: extract is not a valid regex — {exc}")

        script = _script_in(command)
        if script is not None and not script.is_file():
            fail("C", f"{ident}: probe command references missing {script.relative_to(ROOT)}")

        # C: cycle guard — only the declared self-row may name this predicate, and it never runs.
        # C: cycle guard — only the declared self-row may name this predicate, and it NEVER runs.
        #
        # This must SKIP, not merely report. The first draft only appended the failure and then
        # fell through to run_probe(), so a row naming this script with environment:repo made the
        # predicate invoke itself forever — the check hung instead of failing. Found by negative
        # test C4; a guard that reports a violation while still performing it is not a guard.
        if SELF_NAME in command:
            if env != "self":
                fail(
                    "C", f"{ident}: names {SELF_NAME} with environment {env!r} — only `self` may, and it never executes"
                )
            unmeasured.append(ident)
            continue

        runnable = env == "repo" or (args.measure and env in ("repo", "host", "network"))
        if not runnable or env == "self":
            unmeasured.append(ident)
            continue

        verdict, detail = run_probe(probe)
        measured_rows.append((ident, verdict, detail, env))

        # D: the loop closes — prose must not contradict the measurement.
        #
        # A compound claim ("SHIPPED (engine) / OPEN (enactment)") is read by its WEAKEST word:
        # any distance-remains token means the prose already admits distance, so it can never be
        # "overstating". Reading only the first word mis-flagged exactly that entry.
        claim = prose.get(ident, "")
        words = {w.strip(".,—-()") for w in claim.replace("/", " ").split()}
        claims_distance = bool(words & remains_words)
        claims_ideal = bool(words & at_ideal_words) and not claims_distance

        if verdict == "unmeasured":
            fail("C", f"{ident}: {detail}")
        elif verdict == "distance-remains" and claims_ideal:
            fail(
                "D",
                f"{ident}: ledger claims {sorted(words & at_ideal_words)} but its probe reports "
                f"distance ({detail}) — prose overstates",
            )
        elif verdict == "at-ideal" and claims_distance and not probe.get("instantaneous"):
            fail(
                "D",
                f"{ident}: ledger claims {sorted(words & remains_words)} but its probe reports "
                f"AT IDEAL ({detail}) — prose lags the system",
            )

    if args.measure:
        print("IDEAL-FORMS — derived distances\n")
        for ident, verdict, detail, env in measured_rows:
            mark = "✓" if verdict == "at-ideal" else "·"
            print(f"  {mark} {ident:26} {verdict:17} {detail}   [{env}]")
        for ident in unmeasured:
            print(f"  ? {ident:26} unmeasured")
        print()

    for n in notes:
        print(n)
    if failures:
        print("ideal-forms registry: DRIFT")
        print("\n".join(failures))
        return 1
    at_ideal = sum(1 for _, v, _, _ in measured_rows if v == "at-ideal")
    print(
        f"ideal-forms registry: OK ({len(ideals)} ideals; {len(measured_rows)} measured, "
        f"{at_ideal} at ideal, {len(unmeasured)} unmeasured vacuum(s), checks A-F clean)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
