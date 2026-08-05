#!/usr/bin/env python3
"""nomenclator.py — NOMENCLATOR, the enforcer of INDEX·NOMINVM (the roll of names).

In Rome the *nomenclator* was the official who knew and announced every name — the keeper of the
album of names. This is its analogue: it validates names against the naming canon and marks any that
break it. (Its sibling magistrate, the **Censor**, governs conduct — the *regimen morum* — and is a
distinct organ; see scripts/censor.py. The Index Nominum's first ruling was to keep the two apart:
Nomenclator for names, Censor for conduct.)

The canon is DERIVED from spec/index-nominum/canon.yaml (never pinned here) per derive-never-pin:
retune a substitution there and the Nomenclator follows. Two charters sit above the machine form —
NAMING.md (orthography, prose) and spec/index-nominum/README.md (the institution).

What it enforces (v1): ORTHOGRAPHIA (Tier-1 letter substitutions — U→V, J→I, W→VV, QU→QV) and the
FORBIDDEN set (ASCII-only; no shell/URL/DNS-breaking characters). Morphologia is advisory in --check.

Usage:
  python3 scripts/nomenclator.py                 # validate the roll; exit 1 if any nota (CI gate)
  python3 scripts/nomenclator.py --apply         # also write logs/nomenclator.json (organ-health probe)
  python3 scripts/nomenclator.py --check "<name>" # derive a candidate's canon form (mint helper)
  python3 scripts/nomenclator.py --census         # take the roll's own census from the living estate
"""
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SPEC = ROOT / "spec" / "index-nominum"
CANON = SPEC / "canon.yaml"
ROLL = SPEC / "roll.yaml"
DOMAINS = SPEC / "domains.yaml"
OUT = ROOT / "logs" / "nomenclator.json"

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


def morphology_notae(name, canon):
    """Advisory structural checks (Morphologia + Identitas id-schemes). Never a hard gate."""
    out = []
    m = canon.get("morphologia") or {}
    idt = canon.get("identitas") or {}
    # ID schemes (DOC-/ATM-/IRF-): if it looks like one, it must match the grammar.
    for key, pat in (idt.get("id_schemes") or {}).items():
        if name.upper().startswith(key + "-") and not re.match(pat, name):
            out.append(f"id-scheme {key}: {name!r} ✗ {pat}")
    up = idt.get("uid_pattern")
    if up and re.match(r"^(ent|rel|evt|met|ses|rec)_", name) and not re.match(up, name):
        out.append(f"uid: {name!r} ✗ {up}")
    # anti-pattern: cadence used as a prefix (it is a suffix)
    for cad in (m.get("cadence_suffixes") or []):
        if name.lower().startswith(cad + "-"):
            out.append(f"cadence {cad!r} as prefix — cadence is a suffix, not a prefix")
    # essence--function: the function head should be a known token
    sep = m.get("separator", "--")
    if sep in name:
        head = name.split(sep, 1)[1].split("-")[0].lower()
        vocab = m.get("token_vocabulary") or {}
        if head and head not in vocab:
            out.append(f"function head {head!r} not in token_vocabulary")
    return out


def validate_domains(canon):
    """Hard-check CANDIDATE domain labels against the canon (orthography). CI-gated.

    Registered domains are facts (already owned, may be English brands that predate or sit outside the
    classical register) — they cannot be retroactively renamed, so they are not a hard gate. The canon
    governs names we are about to mint, i.e. the `candidate` bucket.
    """
    if not DOMAINS.exists():
        return []
    data = _load(DOMAINS)
    register = (canon.get("orthographia") or {}).get("register_default", "classical")
    out = []
    for e in data.get("candidate") or []:
        label = (e.get("label") or "").strip()
        if not label:
            continue
        marks, _, _ = notae(label, canon, register)
        out += [(f"domain:{label}", mk) for mk in marks]
    return out


def fail(message):
    print(f"nomenclator: {message}", file=sys.stderr)
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
    morph = morphology_notae(name, canon)
    if morph:
        print("  morphology (advisory):")
        for m in morph:
            print(f"    · {m}")
    return 1 if hard else 0


def validate_roll(canon):
    """Default + --apply: validate every name on the roll. Returns (violations, checked_count)."""
    if not ROLL.exists():
        print("nomenclator: no roll (spec/index-nominum/roll.yaml absent) — nothing to validate")
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


def _estate_names():
    """Discover names in the LIVING estate — the institutions under spec/, the heartbeat organs, and
    the pillar organs (organs/ dirs + organ-ladder pillars). This is the metabolize limb: the roll
    seeds, the estate is the source of truth. The institution crawls itself rather than waiting to be
    hand-fed (the autopoiesis 'past' tense). Widened 2026-07-09 to the organ estate so the roll can
    become the complete census instead of seeing only spec/ + beat voices."""
    names = set()
    spec_root = ROOT / "spec"
    if spec_root.exists():
        for d in spec_root.iterdir():
            if d.is_dir():
                names.add(d.name)
    hb = ROOT / "scripts" / "heartbeat-loop.sh"
    if hb.exists():
        for m in re.finditer(r"^C_([A-Z][A-Z_]*)=", hb.read_text(), re.M):
            names.add(m.group(1).lower())
    # the pillar organs — each authored organ dir is a name the surfaces display
    organs_root = ROOT / "organs"
    if organs_root.exists():
        for d in organs_root.iterdir():
            if d.is_dir():
                names.add(d.name)
    # organ-ladder pillars (the declarative organ census)
    ladder = ROOT / "organ-ladder.json"
    if ladder.exists():
        try:
            for o in (json.loads(ladder.read_text()).get("organs") or []):
                p = (o.get("pillar") or "").strip().lower()
                if p:
                    names.add(p)
        except (ValueError, OSError):
            pass
    return sorted(names)


def census(canon):
    """--census: take the roll's own census. Crawl the estate, derive each name's canon form, and
    report drift against the roll — so the roll metabolizes the living estate instead of being
    hand-fed. Plain-english identifiers needing U→V are PROPOSED for enrollment (not failures);
    only a genuinely broken name (non-ASCII / shell- or DNS-unsafe) is a hard nota → exit 1."""
    register = (canon.get("orthographia") or {}).get("register_default", "classical")
    roll_domains = set()
    if ROLL.exists():
        for e in (_load(ROLL).get("names") or []):
            dom = (e.get("domain") or "").lower()
            if dom:
                roll_domains.add(dom)
    names = _estate_names()
    enrolled, propose, broken = 0, [], []
    for nm in names:
        marks, _ortho, dom = notae(nm, canon, register)
        hard = [m for m in marks if m.startswith(("non-ASCII", "unsafe"))]
        if hard:
            broken.append((nm, hard))
        elif dom in roll_domains:
            enrolled += 1
        else:
            propose.append((nm, dom))
    print(f"nomenclator census: {len(names)} names in the living estate "
          f"(spec/ institutions + heartbeat organs)")
    print(f"  on the roll: {enrolled} · propose to enroll: {len(propose)} · broken: {len(broken)}")
    for nm, dom in propose:
        print(f"  + {nm} → {dom}  (estate name; derive canon form and add to roll.yaml)")
    for nm, hard in broken:
        print(f"  ✗ {nm}: {'; '.join(hard)}")
    return 1 if broken else 0


def main():
    if not yaml:
        print("nomenclator: pyyaml unavailable")
        return 2
    if not CANON.exists():
        fail(f"canon missing: {CANON}")
    canon = _load(CANON)

    if "--check" in sys.argv:
        i = sys.argv.index("--check")
        if i + 1 >= len(sys.argv):
            fail("--check needs a name, e.g. --check \"Studium IV\"")
        return check_one(canon, sys.argv[i + 1])

    if "--census" in sys.argv:
        return census(canon)

    violations, n = validate_roll(canon)
    violations += validate_domains(canon)

    if "--apply" in sys.argv:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "checked": n,
            "notae": len(violations),
            "status": "clean" if not violations else "nota",
        }, indent=2))

    if violations:
        print(f"\n{len(violations)} nota on the roll:")
        for name, m in violations:
            print(f"  ✗ {name}: {m}")
        return 1
    print(f"\n✓ {n} roll names + all domain labels satisfy the canon (orthographia + forbidden)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
