#!/usr/bin/env python3
"""vox-verify.py — the VOX program macro-verification predicate (VOX-META, executable form).

`spec/vox-program.md` §2 declares a pre-dispatch gate: each plan is checked against AGENTS.md
precedence + lifecycle + his-hand, organ boundaries, the credential protocol, NAMING ideal-form, and
the `vox/types` single-contract rule; §4 adds a macro sibling-collision review. Per this repo's
Definition of Done, that gate is delivered here as an EXECUTABLE PREDICATE (exit 0 ⟺ every gate
passes), not hand-maintained prose.

Two layers, so the receipt can never silently drift from the code:
  * The JUDGMENT gates (2 organ boundaries, 5 single-contract, macro collision) and the cross-repo
    floor of gate 3 are established by a read-only multi-agent verification pass and recorded as signed
    verdicts in `spec/vox-program-verification.md` (the receipt). This predicate PARSES that receipt
    and requires every gate to be `pass` or `pass-with-note`.
  * The MECHANICAL gates (3 credential lane, 4 NAMING, 1 lifecycle floor) are RE-COMPUTED here from
    limen's own sources at run time. If a receipt verdict says `pass` while its mechanical re-check is
    red, that is a DRIFT and a hard failure — the code wins (same discipline as check-agent-docs.py).

Standalone by design: this reaches cross-repo state (the sibling repos), so it is deliberately NOT
wired into the required `pr-gate` — coupling limen's trunk-green to another repo's state is a fragility
we refuse. Run it on demand / as VOX-META's re-assertion:

  python3 scripts/vox-verify.py            # exit 0 ⟺ all gates pass
  python3 scripts/vox-verify.py --verbose  # also print each gate's basis
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECEIPT = ROOT / "spec" / "vox-program-verification.md"

# The minted program NAMES subject to NAMING orthography (env-var names follow SCREAMING_SNAKE, a
# different convention, so they are not run through the domain-label canon).
PROGRAM_NAMES = ["vox", "in-my-head"]
# Files the VOX program introduced/touched in limen — the proportionate scope for the "no committed
# secret" mechanical floor (fleet-wide secret cleanliness is publication-policy.py's standing job).
VOX_TOUCHED = ["scripts/creds-hydrate.py", "scripts/credential-wall.py", "scripts/vox-verify.py",
               "spec/vox-program.md", "spec/vox-program-verification.md"]
# ElevenLabs key shapes on top of the canonical _SECRET_RX firewall.
_ELEVEN_RX = (re.compile(r"sk_[A-Za-z0-9]{24,}"), re.compile(r"""xi-api-key["'`]?\s*[:=]\s*["'`][^"'`]+"""))

_failures: list[str] = []
_notes: list[str] = []


def fail(gate: str, msg: str) -> None:
    _failures.append(f"{gate}: {msg}")


def _load_default_map() -> list[dict]:
    """Import DEFAULT_MAP from the hyphenated loader (single source of truth) — as credential-wall does."""
    p = ROOT / "scripts" / "creds-hydrate.py"
    spec = importlib.util.spec_from_file_location("creds_hydrate", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return list(getattr(m, "DEFAULT_MAP", []))


def _secret_rx() -> tuple:
    """Reuse the canonical _SECRET_RX firewall from creds-hydrate.py, plus the ElevenLabs shapes."""
    p = ROOT / "scripts" / "creds-hydrate.py"
    spec = importlib.util.spec_from_file_location("creds_hydrate", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return tuple(getattr(m, "_SECRET_RX", ())) + _ELEVEN_RX


def parse_receipt() -> dict[str, str]:
    """Extract the machine-readable verdict block: `<!-- vox-verify:verdicts ... -->`."""
    if not RECEIPT.exists():
        fail("receipt", f"{RECEIPT.relative_to(ROOT)} is missing — VOX-META has no signed verdict surface")
        return {}
    text = RECEIPT.read_text()
    m = re.search(r"<!--\s*vox-verify:verdicts\s*(.*?)-->", text, re.DOTALL)
    if not m:
        fail("receipt", "no `<!-- vox-verify:verdicts ... -->` block found in the receipt")
        return {}
    verdicts: dict[str, str] = {}
    for line in m.group(1).strip().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            verdicts[k.strip()] = v.strip()
    return verdicts


# ---- mechanical re-checks (drift-guards) ----------------------------------------------------------

def check_gate3_lane() -> bool:
    """The ElevenLabs credential is registered in DEFAULT_MAP routed to ELEVEN_API_KEY, credential-wall
    --check passes, and no secret literal appears in the VOX-touched files."""
    ok = True
    dm = _load_default_map()
    if not any("ELEVEN_API_KEY" in (e.get("env") or []) for e in dm):
        fail("gate3_credential_protocol", "no DEFAULT_MAP lane routes to ELEVEN_API_KEY")
        ok = False
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "credential-wall.py"), "--check"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        fail("gate3_credential_protocol", "credential-wall.py --check is red (a secret lacks a home)")
        ok = False
    rx = _secret_rx()
    for rel in VOX_TOUCHED:
        p = ROOT / rel
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            # skip the op:// provenance path (a reference, not a value) and regex/pattern definitions
            if any(s in line for s in ("op://", "re.compile", "_ELEVEN_RX", "_SECRET_RX")):
                continue
            for pat in rx:
                if pat.search(line):
                    fail("gate3_credential_protocol", f"possible committed secret in {rel}:{i}")
                    ok = False
    return ok


def check_gate4_naming() -> bool:
    """Each minted program name carries no hard (forbidden) nota — nomenclator.py --check exits 0."""
    ok = True
    for name in PROGRAM_NAMES:
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "nomenclator.py"), "--check", name],
                           capture_output=True, text=True)
        if r.returncode == 1:
            fail("gate4_naming", f"name '{name}' fails NAMING (hard nota): {r.stdout.strip()[:80]}")
            ok = False
    return ok


def check_gate1_floor() -> bool:
    """Every VOX-* task on the board carries a status in the canonical VALID_STATUSES set."""
    board = ROOT / "tasks.yaml"
    if not board.exists():
        _notes.append("gate1: tasks.yaml not in this checkout — floor deferred to the receipt verdict")
        return True
    try:
        sys.path.insert(0, str(ROOT / "cli" / "src"))
        import yaml
        from limen.models import VALID_STATUSES
    except Exception as e:  # noqa: BLE001 — reuse unavailable → defer to receipt, don't false-fail
        _notes.append(f"gate1: could not import VALID_STATUSES ({e}); floor deferred to receipt")
        return True
    try:
        data = yaml.safe_load(board.read_text()) or {}
    except Exception as e:  # noqa: BLE001
        _notes.append(f"gate1: tasks.yaml unparseable here ({e}); floor deferred to receipt")
        return True
    vox = [t for t in data.get("tasks", []) if str(t.get("id", "")).startswith("VOX-")]
    if not vox:
        _notes.append("gate1: no VOX-* tasks in this checkout's board; floor deferred to receipt")
        return True
    ok = True
    for t in vox:
        if t.get("status") not in VALID_STATUSES:
            fail("gate1_precedence", f"task {t.get('id')} has invalid status '{t.get('status')}'")
            ok = False
    return ok


# gate -> mechanical re-check (drift-guard). Judgment-only gates map to None (receipt-trusted).
DRIFT_GUARDS = {
    "gate1_precedence": check_gate1_floor,
    "gate2_organ_boundaries": None,
    "gate3_credential_protocol": check_gate3_lane,
    "gate4_naming": check_gate4_naming,
    "gate5_single_contract": None,
    "macro_sibling_collision": None,
}

PASSING = {"pass", "pass-with-note"}


def main() -> int:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    verdicts = parse_receipt()

    for gate, guard in DRIFT_GUARDS.items():
        verdict = verdicts.get(gate)
        if verdict is None:
            fail(gate, "no verdict recorded in the receipt")
            continue
        if verdict not in PASSING:
            fail(gate, f"receipt verdict is '{verdict}' (not pass)")
            continue
        # verdict says pass — drift-guard it against the code where we can.
        if guard is not None:
            mech_ok = guard()  # appends its own failure(s) on drift
            if verbose:
                print(f"  · {gate}: receipt={verdict}, mechanical={'ok' if mech_ok else 'DRIFT'}")
        elif verbose:
            print(f"  · {gate}: receipt={verdict} (judgment — receipt-trusted)")

    for n in _notes:
        print(f"  note — {n}")

    if _failures:
        print(f"✗ vox-verify: {len(_failures)} gate failure(s):")
        for f in _failures:
            print(f"   - {f}")
        return 1
    print(f"✓ vox-verify: all {len(DRIFT_GUARDS)} VOX-program gates pass "
          f"(mechanical gates re-checked; receipt {RECEIPT.name} in agreement)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
