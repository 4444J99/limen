#!/usr/bin/env python3
"""ATOM-HOMING drift predicate — holds the registry to its own rules (the check-gates.py shape).

Exit 0 iff institutio/governance/atom-homing.yaml is internally coherent:
  A  schema      — every canonical atom kind has a row carrying the required fields with
                   valid enums (home_class / unit / verify). A kind without a home is the
                   exact vacuum this registry exists to abolish.
  B  reachable   — every declared home resolves: an in-repo path, a local path, an
                   `org/repo` in the estate census, or (home_class: broker) a real CLI
                   verb. Host-aware by the same rule as check-corpora / check-convergence:
                   'missing' is only claimable where the evidence to prove absence exists.
  C  completeness— registry kinds, census kinds, and the canonical eight agree exactly,
                   and the census's per-kind counts sum to its declared total. Runs
                   STORE-FREE: it reads the committed census, never the corpus, because
                   the corpus lives in a `remote: none` store CI can never reach — and is
                   presently cold-archived off the operator host as well.
  D  leak        — no atom statement may appear in the public tree. Enforced structurally
                   and store-free: no file outside the declared producer/parser set may
                   carry the extract signature, and no tracked file may carry a literal
                   atom id. This is the executable form of `redacted: false ⇒ never
                   leaves its store`.
  E  ratchet     — residue may only ever shrink: each kind's residue_baseline must not
                   exceed the census count for that kind, nor the committed ceiling in
                   atom-residue-baseline.txt. Lowering residue takes a two-file edit;
                   raising it back is a visible diff, not a silent regression.
  F  derive      — scripts/brainstorm-harvest.py must READ the kind list from this
                   registry rather than keep a second literal copy of it.
  G  anti-fake   — a deferral must name a count, an owner, and a release condition, and
                   must be strictly smaller than the kind's residue. A kind that defers
                   its entire population has not been homed; it has been hidden.

Run directly, via pr-gate, or verify-whole. Fails toward caution: a broken registry is RED.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
REGISTRY = ROOT / "institutio" / "governance" / "atom-homing.yaml"
CENSUS = ROOT / "institutio" / "governance" / "atom-census.yaml"
CEILING = ROOT / "institutio" / "governance" / "atom-residue-baseline.txt"
HARVEST = SCRIPTS / "brainstorm-harvest.py"
CONDUCT_CLI = ROOT / "cli" / "src" / "limen" / "conduct" / "cli.py"

sys.path.insert(0, str(SCRIPTS))
import reference_state
from reference_state import ReferenceResolver

# The eight-kind schema is fixed by the semantic pass itself; a ninth kind is a schema
# change, not a registry edit, and must fail loudly here first.
CANONICAL_KINDS = {
    "projects-to-start",
    "decisions",
    "tasks",
    "vacuums",
    "questions-unresolved",
    "client-offerings",
    "schema-proposals",
    "functionality-to-repeat",
}

VALID_HOME_CLASS = {"public", "private", "broker"}
VALID_UNIT = {"cluster", "stream", "atom"}
VALID_VERIFY = {
    "irf_row_exists",
    "ledger_entry_exists",
    "spec_file_exists",
    "precedent_row_exists",
    "registry_row_exists",
    "lever_row_exists",
    "broker_receipt",
    "funnel_entry_exists",
}
REQUIRED_FIELDS = (
    "home",
    "home_class",
    "unit",
    "admits",
    "verify",
    "consumers",
    "residue_baseline",
    "owner_of_record",
    "note",
)

# Files permitted to name the extract signature: the producer, the parser, and this
# predicate. Anything else carrying it is a drained extract that escaped its store.
SIGNATURE_PRODUCERS = {
    "scripts/brainstorm-harvest.py",
    "organs/consulting/constellation/constellation-streams.py",
    "scripts/check-atom-homing.py",
}

failures: list[str] = []
advisories: list[str] = []


def fail(check: str, msg: str) -> None:
    failures.append(f"  ✗ [{check}] {msg}")


def advise(check: str, msg: str) -> None:
    advisories.append(f"  ↑ {check}: {msg}")


def _load_convergence_module():
    """Reuse check-convergence.py's owner resolver — the one resolver, no second copy.

    Returns None if it cannot be loaded; check B then degrades to path-only resolution
    rather than inventing a competing reachability rule.
    """
    path = SCRIPTS / "check-convergence.py"
    if not path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("_check_convergence", path)
        if spec is None or spec.loader is None:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 — a broken sibling must not mask this registry's own drift
        return None


def _home_reachable(home: str, home_class: str, conv) -> str:
    """'ok' | 'archived' | 'missing' | 'unverifiable-here' | 'prose'.

    Resolution is keyed off home_class, because the three classes carry different burdens
    of proof:

      public  — an in-repo path. It binds EVERYWHERE, CI included, so a public home that
                does not exist is drift, full stop. Deliberately NOT delegated to
                check-convergence's resolver, which downgrades an absent path to the
                advisory 'prose' — correct for a registry that tolerates prose owners,
                wrong for one whose entire purpose is that every kind has a real home.
      broker  — a CLI verb, not a path: prove the subcommand exists in-tree.
      private — out-of-tree by definition (a private repo, an evacuated store). Here the
                host-aware resolver IS right: absence is only claimable where the evidence
                to prove it exists.
    """
    if home_class == "broker":
        if not home.startswith("limen "):
            return "prose"
        parts = home.split()
        if len(parts) < 3:
            return "prose"
        group, verb = parts[1], parts[2]
        if group == "conduct" and CONDUCT_CLI.is_file():
            src = CONDUCT_CLI.read_text(encoding="utf-8")
            return "ok" if f'command("{verb}")' in src else "missing"
        return "unverifiable-here"

    if home_class == "public":
        return "ok" if (ROOT / home).exists() else "missing"

    # private: an in-repo path still counts if it happens to exist; otherwise ask the CUSTODY
    # axis first (it can prove an evacuated store is archived rather than lost), and fall back
    # to the convergence resolver for the org/repo census case it owns.
    if (ROOT / home).exists():
        return "ok"
    res = ReferenceResolver().resolve(home)
    if res.state in (reference_state.OK, reference_state.ARCHIVED):
        return "ok" if res.state == reference_state.OK else "archived"
    if conv is not None:
        return conv._owner_reachable(home, conv._census_repos())
    return "unverifiable-here"


def _git_grep(pattern: str, fixed: bool = False) -> list[str]:
    """Tracked files matching `pattern`. Empty list means genuinely no match.

    A leak check that fails OPEN is worse than none at all, so an unexpected git exit is
    escalated as a check-D failure rather than quietly returning nothing. (This is not
    hypothetical: passing a Python-escaped literal to `-E` makes git exit 2, which an
    earlier version of this function silently read as 'clean'.)
    """
    proc = subprocess.run(
        ["git", "grep", "-l", "-F" if fixed else "-E", pattern],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode not in (0, 1):
        fail("D", f"leak scan could not run (git grep exit {proc.returncode}): {proc.stderr.strip()[:200]}")
        return []
    return [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]


def check_leak() -> None:
    """D — the public tree may hold generalizations, counts, and ids, never statements."""
    # Built from parts so this predicate's own source is not itself a match. Matched as a
    # FIXED string: the literal contains regex-significant characters.
    signature = "## " + "SEMANTIC" + " ATOMS"
    for path in _git_grep(signature, fixed=True):
        if path not in SIGNATURE_PRODUCERS:
            fail("D", f"{path}: carries the extract signature — a drained extract in the public tree")

    # An atom id is `<thread_uid>--<kind>--NNN`; a literal one in the public tree means a
    # statement almost certainly travelled with it.
    kinds_alt = "|".join(sorted(CANONICAL_KINDS))
    id_pattern = r"[a-z0-9][a-z0-9_-]*--(" + kinds_alt + r")--[0-9]{3}"
    for path in _git_grep(id_pattern):
        if path != "scripts/check-atom-homing.py":
            fail("D", f"{path}: carries a literal atom id — atom ids are private-store data")


def _read_ceiling() -> dict[str, int]:
    """`<kind> <count>` per line; blank lines and # comments ignored."""
    ceiling: dict[str, int] = {}
    if not CEILING.is_file():
        fail("E", f"missing residue ceiling file: {CEILING.relative_to(ROOT)}")
        return ceiling
    for lineno, raw in enumerate(CEILING.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 2 or not parts[1].isdigit():
            fail("E", f"{CEILING.name}:{lineno}: expected `<kind> <count>`, got {raw!r}")
            continue
        ceiling[parts[0]] = int(parts[1])
    return ceiling


def main() -> int:
    if not REGISTRY.is_file():
        print(f"atom-homing registry: MISSING ({REGISTRY})")
        return 1
    doc = yaml.safe_load(REGISTRY.read_text(encoding="utf-8")) or {}
    kinds = doc.get("kinds") or {}
    if not kinds:
        fail("A", "registry has no `kinds` block")

    conv = _load_convergence_module()
    if conv is None:
        advise("B", "check-convergence.py resolver unavailable — home resolution is path-only")

    # ── A: schema ────────────────────────────────────────────────────────────────
    for kid, row in kinds.items():
        if not isinstance(row, dict):
            fail("A", f"{kid}: row must be a mapping")
            continue
        for field in REQUIRED_FIELDS:
            if field not in row:
                fail("A", f"{kid}: missing `{field}`")
        if row.get("home_class") not in VALID_HOME_CLASS:
            fail("A", f"{kid}: home_class {row.get('home_class')!r} not in {sorted(VALID_HOME_CLASS)}")
        if row.get("unit") not in VALID_UNIT:
            fail("A", f"{kid}: unit {row.get('unit')!r} not in {sorted(VALID_UNIT)}")
        if row.get("verify") not in VALID_VERIFY:
            fail("A", f"{kid}: verify {row.get('verify')!r} not in {sorted(VALID_VERIFY)}")
        if not isinstance(row.get("residue_baseline"), int):
            fail("A", f"{kid}: residue_baseline must be an integer (atoms)")
        if not isinstance(row.get("consumers"), list) or not row.get("consumers"):
            fail("A", f"{kid}: consumers must be a non-empty list")

        # consumer files must exist (check-personal-facts D)
        for consumer in row.get("consumers") or []:
            if not (SCRIPTS / consumer).is_file():
                fail("A", f"{kid}: consumer scripts/{consumer} not found")

        # ── B: the home resolves ─────────────────────────────────────────────────
        home = row.get("home") or ""
        verdict = _home_reachable(home, row.get("home_class", ""), conv)
        if verdict == "missing":
            fail("B", f"{kid}: home {home!r} does not resolve")
        elif verdict == "archived":
            # Accounted for by the CUSTODY axis: absent here, but receipts prove two verified
            # copies on independent devices. Distinct from 'ok' (you cannot write to it right
            # now) and from 'missing' (it is not lost) — which is the whole point of the state.
            advise("B", f"{kid}: home {home!r} is archived off-host with verified custody — accounted for, not lost")
        elif verdict == "prose":
            advise("B", f"{kid}: home {home!r} is prose, not a resolvable reference")
        elif verdict == "unverifiable-here":
            advise("B", f"{kid}: home {home!r} unverifiable on this host (evacuated store or CI runner)")
        elif verdict != "ok":
            # No silent fall-through: an unrecognised verdict is drift in the resolver contract,
            # not an implicit pass. Adding a state upstream must never read as 'fine' down here.
            fail("B", f"{kid}: home {home!r} returned unknown reachability verdict {verdict!r}")

        # ── G: anti-fake deferral ────────────────────────────────────────────────
        deferred = row.get("deferred")
        if deferred is not None:
            if not isinstance(deferred, dict):
                fail("G", f"{kid}: deferred must be a mapping")
            else:
                count = deferred.get("count")
                if not isinstance(count, int) or count <= 0:
                    fail("G", f"{kid}: deferred.count must be a positive integer")
                for field in ("owner", "until"):
                    if not str(deferred.get(field) or "").strip():
                        fail("G", f"{kid}: deferred must name `{field}` — an unowned deferral is a vacuum")
                residue = row.get("residue_baseline")
                if isinstance(count, int) and isinstance(residue, int) and count >= residue:
                    fail(
                        "G",
                        f"{kid}: defers {count} of {residue} residual atoms — a wholly-deferred "
                        "kind is not homed, it is hidden",
                    )

    # ── C: completeness (store-free, against the committed census) ───────────────
    registry_kinds = set(kinds)
    if registry_kinds != CANONICAL_KINDS:
        for missing in sorted(CANONICAL_KINDS - registry_kinds):
            fail("C", f"canonical kind {missing!r} has no registry row — an un-homed kind is a vacuum")
        for extra in sorted(registry_kinds - CANONICAL_KINDS):
            fail("C", f"registry declares unknown kind {extra!r} (the schema is eight kinds)")

    census: dict = {}
    if not CENSUS.is_file():
        fail("C", f"missing census projection: {CENSUS.relative_to(ROOT)} — run brainstorm-harvest.py --census")
    else:
        census = yaml.safe_load(CENSUS.read_text(encoding="utf-8")) or {}
        by_kind = census.get("by_kind") or {}
        totals = census.get("totals") or {}
        if set(by_kind) != CANONICAL_KINDS:
            fail("C", f"census by_kind covers {sorted(set(by_kind))}, expected the canonical eight")
        summed = sum(v for v in by_kind.values() if isinstance(v, int))
        declared = totals.get("atoms")
        if isinstance(declared, int) and summed != declared:
            fail("C", f"census by_kind sums to {summed} but totals.atoms is {declared}")

    # ── E: ratchet ───────────────────────────────────────────────────────────────
    ceiling = _read_ceiling()
    by_kind = (census.get("by_kind") or {}) if census else {}
    for kid, row in kinds.items():
        residue = row.get("residue_baseline")
        if not isinstance(residue, int):
            continue
        total = by_kind.get(kid)
        if isinstance(total, int) and residue > total:
            fail("E", f"{kid}: residue_baseline {residue} exceeds census count {total}")
        cap = ceiling.get(kid)
        if cap is None:
            if ceiling:
                fail("E", f"{kid}: no ceiling row in {CEILING.name}")
        elif residue > cap:
            fail("E", f"{kid}: residue_baseline {residue} exceeds ceiling {cap} — residue may only shrink")

    # ── F: consumers derive ──────────────────────────────────────────────────────
    if not HARVEST.is_file():
        fail("F", f"missing consumer: {HARVEST.relative_to(ROOT)}")
    else:
        src = HARVEST.read_text(encoding="utf-8")
        if re.search(r"^ATOM_KINDS\s*=\s*\[", src, re.MULTILINE):
            fail("F", "brainstorm-harvest.py keeps a literal ATOM_KINDS list — it must derive from this registry")
        if "atom-homing.yaml" not in src:
            fail("F", "brainstorm-harvest.py does not reference atom-homing.yaml — the kind list is not derived")

    # ── D: leak ──────────────────────────────────────────────────────────────────
    check_leak()

    for line in advisories:
        print(line)
    if failures:
        print("atom-homing registry: DRIFT")
        print("\n".join(failures))
        return 1

    residue_total = sum(r.get("residue_baseline", 0) for r in kinds.values() if isinstance(r, dict))
    atoms = ((census.get("totals") or {}).get("atoms")) if census else None
    scope = f" of {atoms}" if isinstance(atoms, int) else ""
    print(
        f"atom-homing registry: OK ({len(kinds)} kinds homed, {residue_total}{scope} atoms residual, checks A-G clean)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
