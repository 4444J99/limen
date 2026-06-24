#!/usr/bin/env python3
"""censor.py — CENSOR, the enforcer of INDEX·NOMINVM (the roll of names).

In Rome the *censor* kept the census — the album of names — and enforced the *regimen morum*,
marking any violation with the **nota censoria**. This is its analogue: it validates names against
the naming canon and issues a nota against any that break it.

The canon is DERIVED from spec/index-nominum/canon.yaml (never pinned here) per derive-never-pin:
retune a substitution there and CENSOR follows. Two charters sit above the machine form —
NAMING.md (orthography, prose) and spec/index-nominum/README.md (the institution).

What it enforces (v1): ORTHOGRAPHIA (Tier-1 letter substitutions — U→V, J→I, W→VV, QU→QV) and the
FORBIDDEN set (ASCII-only; no shell/URL/DNS-breaking characters). Morphologia is advisory in --check.

Usage:
  python3 scripts/censor.py                 # validate the roll; exit 1 if any nota (CI gate)
  python3 scripts/censor.py --apply         # also write logs/censor.json (organ-health probe)
  python3 scripts/censor.py --check "<name>" # derive a candidate's canon form (mint helper)
"""
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
CANON = ROOT / "spec" / "index-nominum" / "canon.yaml"
ROLL = ROOT / "spec" / "index-nominum" / "roll.yaml"
OUT = ROOT / "logs" / "censor.json"

try:
    import yaml
except ImportError:
    yaml = None


def _load(path):
    return yaml.safe_load(path.read_text()) or {}


def _subs(canon, register="classical"):
    """The ordered substitution list for a register. archaic = classical + archaic_extra."""
    table = (canon.get("orthographia") or {}).get("substitutions") or {}
    rules = list(table.get("classical") or [])
    if register == "archaic":
        rules += list(table.get("archaic_extra") or [])
    return rules


def orthographic_form(s, subs):
    """Apply Tier-1 letter substitutions to the lowercased name → its canon orthographic form."""
    out = s.lower()
    for r in subs:
        out = out.replace(r["from"], r["to"])
    return out


def domain_form(s, canon, subs):
    """Derive the domain-safe label: whitespace→hyphen, orthographic substitution, keep DNS charset."""
    f = canon.get("forbidden") or {}
    ws = f.get("whitespace_to", "-")
    charset = set(f.get("domain_charset", "abcdefghijklmnopqrstuvwxyz0123456789-."))
    s = "".join(ws if ch.isspace() else ch for ch in s)
    s = orthographic_form(s, subs)
    return "".join(ch for ch in s if ch in charset)


def notae(name, canon, register="classical", domain=None):
    """Return the list of violations (notae) for a name, plus the derived canon forms."""
    subs = _subs(canon, register)
    f = canon.get("forbidden") or {}
    out = []

    # FORBIDDEN — anything that breaks terminal / Finder / DNS
    if f.get("ascii_only", True):
        for ch in name:
            if ord(ch) > 0x7F:
                use = (f.get("replacements") or {}).get(ch)
                hint = f" → write {use!r}" if use else ""
                out.append(f"non-ASCII {ch!r}{hint} (breaks terminal/Finder/DNS)")
    for spec in f.get("chars") or []:
        if spec["char"] in name:
            use = (f.get("replacements") or {}).get(spec["char"])
            hint = f" → write {use!r}" if use else ""
            out.append(f"unsafe {spec['char']!r}{hint} ({spec.get('why', '')})")

    # ORTHOGRAPHIA — the display must already be in canon (a fixed point of the substitution)
    canon_ortho = orthographic_form(name, subs)
    if canon_ortho != name.lower():
        out.append(f"orthography: {name!r} → canon {canon_ortho.upper()!r}")

    # DOMAIN — if a label was declared, it must equal the derived one
    derived_domain = domain_form(name, canon, subs)
    if domain is not None and domain != derived_domain:
        out.append(f"domain: {domain!r} → {derived_domain!r}")

    return out, canon_ortho, derived_domain


def fail(message):
    print(f"censor: {message}", file=sys.stderr)
    raise SystemExit(2)


def check_one(canon, name):
    """--check: derive and print a candidate's canon form; exit 1 only on a hard (forbidden) nota."""
    register = (canon.get("orthographia") or {}).get("register_default", "classical")
    marks, ortho, domain = notae(name, canon, register)
    print(f"  candidate : {name}")
    print(f"  wordmark  : {ortho.upper()}")
    print(f"  domain    : {domain}")
    hard = [m for m in marks if m.startswith(("non-ASCII", "unsafe"))]
    if marks:
        print("  notae:")
        for m in marks:
            print(f"    ✗ {m}")
    else:
        print("  ✓ in canon")
    return 1 if hard else 0


def validate_roll(canon):
    """Default + --apply: validate every name on the roll. Returns (violations, checked_count)."""
    if not ROLL.exists():
        print("censor: no roll (spec/index-nominum/roll.yaml absent) — nothing to validate")
        return [], 0
    roll = _load(ROLL)
    default_reg = (canon.get("orthographia") or {}).get("register_default", "classical")
    violations = []
    names = roll.get("names") or []
    for e in names:
        display = (e.get("display") or "").strip()
        if not display:
            violations.append(("(blank)", "roll entry missing 'display'"))
            continue
        marks, _, _ = notae(display, canon, e.get("register", default_reg), e.get("domain"))
        for m in marks:
            violations.append((display, m))
    return violations, len(names)


def main():
    if not yaml:
        print("censor: pyyaml unavailable")
        return 2
    if not CANON.exists():
        fail(f"canon missing: {CANON}")
    canon = _load(CANON)

    if "--check" in sys.argv:
        i = sys.argv.index("--check")
        if i + 1 >= len(sys.argv):
            fail("--check needs a name, e.g. --check \"Studium IV\"")
        return check_one(canon, sys.argv[i + 1])

    violations, n = validate_roll(canon)

    if "--apply" in sys.argv:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "checked": n,
            "notae": len(violations),
            "status": "clean" if not violations else "nota",
        }, indent=2))

    if violations:
        print(f"\n{len(violations)} nota censoria on the roll:")
        for name, m in violations:
            print(f"  ✗ {name}: {m}")
        return 1
    print(f"\n✓ all {n} names on the roll satisfy the canon (orthographia + forbidden)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
