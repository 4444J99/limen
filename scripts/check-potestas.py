#!/usr/bin/env python3
"""check-potestas — the Omega predicate for the POTESTAS track (organvm/limen#2091).

WHAT IT CLOSES: a corpus about influence is only worth having if it is honest about which of its
own mechanisms survived replication. Every popular treatment of this material cites findings that
collapsed -- ego depletion, power posing, social priming, nudge, Cambridge Analytica -- and a reader
who absorbs the canon uncritically walks away CONFIDENTLY WRONG, which is worse than ignorant
because it feels like competence.

So this predicate makes the evidence grade STRUCTURAL rather than editorial:

  1. definition present
  2. evidence present and in the declared grade set        (REQUIRED, no default)
  3. sign present            -- how it is DETECTED in the wild (the inoculation payload)
  4. counter present         -- what is actually done about it
  5. instance present        -- opaque ids only, or the literal string `none-observed`
  6. evidence: robust        -- requires a real citation (author + year + venue)
  7. HYGIENE GATE            -- no `debunked` mechanism is load-bearing anywhere: no drill,
                                protocol, or rubric may cite one. replication.md is exempt --
                                cataloguing the dead is its entire job.

Plus the PII rules that keep this track publishable (organvm/limen#2113): the registry is a PUBLIC
file describing MECHANISMS, never people. Instance ids are opaque; the resolution map lives only in
the private overlay.

Usage:
  python3 scripts/check-potestas.py          # human-readable; exit 0 iff every rule holds
  python3 scripts/check-potestas.py --json   # machine-readable summary

Run it BARE and read its own exit code. `check-potestas.py | tail` reports *tail's* status, which is
essentially always 0, and turns a printed FAIL into a false green.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - environment, not code
    sys.stderr.write(
        "check-potestas: PyYAML is not importable in this interpreter.\n"
        "  This is an ENVIRONMENT failure, not a registry failure.\n"
        "  Fix:  pip install -e 'cli[test]'\n"
    )
    raise SystemExit(2) from None

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "studium" / "potestas" / "mechanisms.yaml"
TRACK = REPO / "studium" / "potestas"
RUBRICS = REPO / "studium" / "rubric"

# replication.md exists precisely to catalogue the dead, so it may name them freely.
RULE7_EXEMPT = {"replication.md", "mechanisms.yaml", "PLAN.md"}

INSTANCE_RE = re.compile(r"^inst-\d{4}$")
NONE_OBSERVED = "none-observed"

# PII patterns. Deliberately blunt: a public track about one person's corpus has exactly one
# catastrophic failure mode, and a public repo's history keeps what a later commit removes.
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# Deliberately SHAPE-matched, not digit-counted. An earlier digit-counting version flagged six
# academic citations ("APSR 112(1):148-166 (2018)", "Science 185:1124-1131") as phone numbers --
# a check that cries wolf on its own bibliography gets disabled, which is worse than no check.
PHONE_RE = re.compile(
    r"(?<![\w.])(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?![\w.])"  # NANP
    r"|(?<![\w.])\+\d{10,15}(?![\w.])"  # E.164
)
PRIVATE_PATH_RE = re.compile(r"_people-private|/Users/[A-Za-z0-9_]+/")


class Findings:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.notes: list[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_registry(f: Findings) -> tuple[dict, list[dict]]:
    if not REGISTRY.exists():
        f.error(f"registry absent: {REGISTRY.relative_to(REPO)}")
        return {}, []
    try:
        doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        f.error(f"registry does not parse: {exc}")
        return {}, []
    meta = doc.get("meta") or {}
    mechs = doc.get("mechanisms") or []
    if not isinstance(mechs, list):
        f.error("registry `mechanisms` is not a list")
        return meta, []
    if not mechs:
        f.error("registry has zero mechanisms -- a registry with no entries is a stub")
    return meta, mechs


def check_schema(meta: dict, mechs: list[dict], f: Findings) -> dict[str, str]:
    """Rules 1-6. Returns {mechanism_id: evidence_grade}."""
    grades = set(meta.get("evidence_grades") or [])
    families = set(meta.get("families") or [])
    if not grades:
        f.error("meta.evidence_grades is missing -- the grade set must be declared, not implied")
        return {}

    seen: dict[str, str] = {}
    for i, m in enumerate(mechs):
        if not isinstance(m, dict):
            f.error(f"mechanism #{i} is not a mapping")
            continue
        mid = m.get("id") or f"<unnamed #{i}>"

        if mid in seen:
            f.error(f"{mid}: duplicate id")
        if not m.get("definition"):
            f.error(f"{mid}: rule 1 -- `definition` missing or empty")

        # Rule 2 -- the field this whole registry exists for.
        ev = m.get("evidence")
        if not ev:
            f.error(f"{mid}: rule 2 -- `evidence` is REQUIRED and has no default")
        elif ev not in grades:
            f.error(f"{mid}: rule 2 -- evidence '{ev}' is not one of {sorted(grades)}")

        if not m.get("sign"):
            f.error(f"{mid}: rule 3 -- `sign` missing (a mechanism you cannot spot is not knowledge)")
        if not m.get("counter"):
            f.error(f"{mid}: rule 4 -- `counter` missing")

        # Rule 5 -- opaque ids only. This is what keeps the public track publishable.
        inst = m.get("instance")
        if inst is None:
            f.error(f"{mid}: rule 5 -- `instance` missing (use `none-observed` if there is none)")
        elif inst == NONE_OBSERVED:
            pass
        elif isinstance(inst, list):
            if not inst:
                f.error(f"{mid}: rule 5 -- empty instance list; use `none-observed`")
            for val in inst:
                if not isinstance(val, str) or not INSTANCE_RE.match(val):
                    f.error(f"{mid}: rule 5 -- instance '{val}' is not an opaque id (inst-NNNN)")
        else:
            f.error(f"{mid}: rule 5 -- `instance` must be a list of opaque ids or '{NONE_OBSERVED}'")

        # Rule 6 -- a robust claim without a source is an assertion.
        if ev == "robust" and not m.get("citation"):
            f.error(f"{mid}: rule 6 -- evidence: robust requires a citation (author + year + venue)")

        fam = m.get("family")
        if families and fam not in families:
            f.error(f"{mid}: family '{fam}' is not one of {sorted(families)}")

        if not isinstance(m.get("inward", False), bool):
            f.error(f"{mid}: `inward` must be a boolean (it derives the Phi-5 forbidden set)")

        if isinstance(ev, str):
            seen[str(mid)] = ev
    return seen


def consumer_files() -> list[Path]:
    """Drills, protocols, rubrics -- everything that could make a mechanism load-bearing."""
    out: list[Path] = []
    if TRACK.exists():
        out.extend(p for p in TRACK.rglob("*.md") if p.name not in RULE7_EXEMPT)
    if RUBRICS.exists():
        out.extend(sorted(RUBRICS.glob("*.md")))
    return out


def check_rule7(grades: dict[str, str], f: Findings) -> int:
    """Rule 7 -- the hygiene gate. A dead mechanism may not carry weight."""
    dead = {mid for mid, ev in grades.items() if ev == "debunked"}
    soft = {mid for mid, ev in grades.items() if ev == "overstated"}
    checked = 0
    for path in consumer_files():
        checked += 1
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(REPO)
        for mid in dead:
            if re.search(rf"\b{re.escape(mid)}\b", text):
                f.error(
                    f"rule 7 -- {rel} cites `{mid}`, which is graded `debunked`. "
                    "A debunked mechanism may not be load-bearing; teaching it would teach a superstition."
                )
        for mid in soft:
            if re.search(rf"\b{re.escape(mid)}\b", text):
                f.note(f"{rel} cites `{mid}` (graded `overstated`) -- verify it is being cited AS overstated")
    return checked


def check_pii(f: Findings) -> None:
    """The boundary that makes this track publishable. Structural, not careful.

    Scans EVERY track file plus the rubrics -- deliberately NOT reusing consumer_files(), whose
    RULE7_EXEMPT set exists only so replication.md may name the dead. Routing the PII scan through
    that same exemption would have left the catalogue of debunked findings, the track index, and
    the registry's own siblings unscanned. Rule 7 and the PII rules exempt different things.
    """
    targets: list[Path] = [REGISTRY]
    if TRACK.exists():
        targets.extend(TRACK.rglob("*.md"))
        targets.extend(TRACK.rglob("*.yaml"))
    if RUBRICS.exists():
        targets.extend(RUBRICS.glob("*.md"))
    for path in {p for p in targets if p.exists()}:
        rel = path.relative_to(REPO)
        text = path.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            if EMAIL_RE.search(line):
                f.error(f"PII -- {rel}:{line_no} contains an email address")
            if PHONE_RE.search(line):
                f.error(f"PII -- {rel}:{line_no} contains a phone-number-shaped string")
            if PRIVATE_PATH_RE.search(line) and "never in this repo" not in line:
                f.error(f"PII -- {rel}:{line_no} leaks a private-overlay or home path")


def main() -> int:
    ap = argparse.ArgumentParser(description="Omega predicate for the POTESTAS track")
    ap.add_argument("--json", action="store_true", help="machine-readable summary")
    args = ap.parse_args()

    f = Findings()
    meta, mechs = load_registry(f)
    grades = check_schema(meta, mechs, f) if mechs else {}
    consumers = check_rule7(grades, f) if grades else 0
    check_pii(f)

    by_grade: dict[str, int] = {}
    for ev in grades.values():
        by_grade[ev] = by_grade.get(ev, 0) + 1
    inward = sum(1 for m in mechs if isinstance(m, dict) and m.get("inward"))

    if args.json:
        print(
            json.dumps(
                {
                    "ok": f.ok,
                    "mechanisms": len(grades),
                    "by_evidence": by_grade,
                    "inward": inward,
                    "consumers_scanned": consumers,
                    "errors": f.errors,
                    "notes": f.notes,
                },
                indent=2,
            )
        )
        return 0 if f.ok else 1

    print(f"POTESTAS registry: {len(grades)} mechanisms, {consumers} consumer file(s) scanned")
    if by_grade:
        spread = "  ".join(f"{k}={v}" for k, v in sorted(by_grade.items()))
        print(f"  evidence: {spread}")
        print(f"  inward (Phi-5 forbidden set): {inward}")
    for note in f.notes:
        print(f"  note: {note}")
    if f.ok:
        print("check-potestas: OK -- every mechanism graded, signed, countered; no dead mechanism load-bearing")
        return 0
    print(f"\ncheck-potestas: FAIL -- {len(f.errors)} finding(s)")
    for err in f.errors:
        print(f"  - {err}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
