#!/usr/bin/env python3
"""lever-classify.py — the sovereignty classifier + dissolution path for the his-hand registry.

The charter's `no-tasks-on-me.sh` proves every lever is HOMED (owned, traceable,
issue-pointed). It never proves a lever is IRREDUCIBLE. This is that missing arm.

A lever is legitimate ONLY if the action IS the operator — an irreducible
sovereignty boundary. Everything else is DESIGN DEBT owned by the beat: a place
where the system has not yet built (or has already built) the organ that
dissolves the human dependency, and it must not sit on his head wearing the
"human-gated" costume.

Every OPEN lever must resolve to exactly one of:

  sovereignty: {reason: <SOVEREIGN_REASONS>}
      The action is irreducibly his (bank, wallet custody, legal body,
      biometric, identity/his-name, a vendor mint no code can perform, or a
      governance CHOICE the script can execute but only he may decide). Stays a
      valve: homed, routed-around, surfaced once, never nags.

  design_debt: {organ: <path>, status: built|partial|absent, dissolves_when: "<cmd>"}
      The system owes this. `organ` names the code that dissolves it;
      `dissolves_when` is a shell predicate (exit 0 => dissolved). When it goes
      green the beat AUTO-DISCHARGES the lever, crediting the organ, not him.

Classification is DERIVED from each lever's own prose (its gate/label/note state
WHY the human is needed) unless an explicit field overrides it. Derivation fails
CLOSED: anything without a clear irreducible signal and without an explicit tag
lands UNCLASSIFIED (red), forcing a real decision rather than a silent pass.

Usage:
  lever-classify.py --check      exit 0 <=> every open lever is proven-sovereign or converted
  lever-classify.py --list       print each open lever's class + evidence + (design_debt) dissolvable state
  lever-classify.py --dissolve   report design_debt levers whose dissolves_when is GREEN (dry-run)
  lever-classify.py --dissolve --apply   discharge dissolved levers (requires LIMEN_LEVER_DISSOLVE_APPLY=1)

The registry PUBLISHES; this script adds only structural fields (never PII).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

REGISTRY = os.environ.get(
    "LIMEN_HIS_HAND_LEVERS",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "his-hand-levers.json"),
)

# The only reasons a lever may irreducibly need the human. Each is a sovereignty
# boundary: automating it would mean impersonating him, using his body, touching
# his hardware, or overriding a choice that is his to make.
SOVEREIGN_REASONS = {
    "identity",          # publishing/acting AS him — his name, his feed, his click, his account, his LMS/registrar data
    "bank",              # his financial institution (a fraud call, an account action)
    "wallet_custody",    # holding keys/custody — a self-custody receive address, a seed phrase, an escrowed key
    "legal_body",        # a legal signature, a notarization, an in-person act
    "biometric",         # Touch ID / Face ID / fingerprint — his body
    "vendor_mint",       # create an account / mint a first token / OAuth-consent a machine cannot self-issue
    "physical_act",      # his hands / his devices — mount a drive, tap an iPhone, plug in hardware
    "device_grant",      # a macOS/OS GUI security prompt only he can approve (TCC, FDA, Automation, driver install)
    "governance_choice", # the script CAN do it; only he may DECIDE/CONSENT (persistence-arm, self-mod, spend, protection)
}

# Conservative derivation signals, ordered most-concretely-irreducible first
# (first match wins). A signal fires only on explicit, unambiguous prose — when
# in doubt, no match => the lever falls through to UNCLASSIFIED rather than being
# waved through as his. Physical/device/vendor signals precede the softer
# identity/governance ones so a "mount"/"TCC"/"OAuth" lever is not mislabeled by
# an incidental "your ...".
SOVEREIGN_SIGNALS = [
    ("biometric",        r"touch id|face id|biometric|fingerprint"),
    ("bank",             r"phone call|your bank|fraud hold|santander"),
    ("wallet_custody",   r"self-custody|wallet you.{0,20}control|receive address|seed phrase|escrow the .{0,20}key|keychain access"),
    ("legal_body",       r"\bnotari|your signature|sign in person|wet signature"),
    ("physical_act",     r"\bmount\b|tap (an |the )?iphone|physical iphone|iphone in hand|personal.device install|ios shortcut|plug in|sit-down|\bin hand\b"),
    ("device_grant",     r"\btcc\b|full disk access|screen recording|gui approval|gui-only|automation (grant|permission)|driver install|preferences pane|settings pane|time machine"),
    # persistence / self-mod arming: the auto-mode classifier deliberately blocks
    # the agent from writing its own persistence/settings — consent is his alone.
    ("governance_choice",r"limen_[a-z_]*=1|settings\.json|classifier.den|classifier.block|persistence.arm|self.arming|paste.{0,30}(snippet|hook|env)|override.{0,20}(your|rule)|spending limit|org billing|\bpurchase\b|branch.protection|security.posture|delete the repo"),
    ("vendor_mint",      r"create.{0,20}(account|app|the developer)|developer app|mint.{0,20}token|re-mint|first.{0,12}token|register.{0,20}app|auth login|oauth|rclone authorize|credential mint|create \+ install"),
    ("identity",         r"under your (own )?name|your public feed|your identity|your click|your account|your cadence|publish.{0,30}your|\boutward\b|your name|\blms\b|registrar|set.{0,12}active|personal.fact|home address|_life-private"),
]


def load_registry(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def is_open(lever: dict) -> bool:
    """A lever is OPEN unless it carries a `discharged` stamp (obligations-view.py:54 semantics)."""
    return not str(lever.get("discharged", "")).strip()


def evidence_blob(lever: dict) -> str:
    parts = [str(lever.get(k, "")) for k in ("label", "gate", "note", "status", "cost")]
    return " ".join(parts).lower()


def classify(lever: dict) -> dict:
    """Return {kind, reason|organ, source, evidence}. kind in {sovereignty, design_debt, UNCLASSIFIED}."""
    # 1. Explicit field wins — the distinction is data.
    sov = lever.get("sovereignty")
    if isinstance(sov, dict) and sov.get("reason") in SOVEREIGN_REASONS:
        return {"kind": "sovereignty", "reason": sov["reason"], "source": "explicit"}
    dd = lever.get("design_debt")
    if isinstance(dd, dict) and str(dd.get("organ", "")).strip() and str(dd.get("dissolves_when", "")).strip():
        status = dd.get("status", "built")
        return {"kind": "design_debt", "organ": dd["organ"], "status": status,
                "dissolves_when": dd["dissolves_when"], "source": "explicit"}

    # 2. Derive sovereignty from prose — conservative, first strong signal wins.
    blob = evidence_blob(lever)
    for reason, pattern in SOVEREIGN_SIGNALS:
        m = re.search(pattern, blob)
        if m:
            return {"kind": "sovereignty", "reason": reason, "source": "derived",
                    "evidence": m.group(0)}

    # 3. Fail closed.
    return {"kind": "UNCLASSIFIED", "source": "none"}


def malformed_reasons(lever: dict) -> list[str]:
    """Structural problems in an explicit field (invalid reason, half-filled design_debt)."""
    problems = []
    sov = lever.get("sovereignty")
    if isinstance(sov, dict) and sov.get("reason") not in SOVEREIGN_REASONS:
        problems.append(f"sovereignty.reason '{sov.get('reason')}' not in {sorted(SOVEREIGN_REASONS)}")
    dd = lever.get("design_debt")
    if isinstance(dd, dict):
        if not str(dd.get("organ", "")).strip():
            problems.append("design_debt.organ empty")
        if not str(dd.get("dissolves_when", "")).strip():
            problems.append("design_debt.dissolves_when empty")
    return problems


def run_predicate(cmd: str, root: str) -> tuple[bool, str]:
    """Run a dissolves_when shell predicate. Returns (green, one-line note). Fails closed on error."""
    try:
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True, timeout=120)
        tail = (r.stdout or r.stderr or "").strip().splitlines()
        return r.returncode == 0, (tail[-1] if tail else f"exit {r.returncode}")
    except Exception as e:  # timeout / spawn failure => not dissolved
        return False, f"predicate error: {e}"


def cmd_list(levers: list[dict], root: str) -> int:
    open_levers = [l for l in levers if is_open(l)]
    sov = dd = unc = 0
    for lev in open_levers:
        c = classify(lev)
        lid = lev.get("id", "<no-id>")
        if c["kind"] == "sovereignty":
            sov += 1
            tag = "sovereignty" if c["source"] == "explicit" else "sovereignty~derived"
            ev = f"  «{c.get('evidence')}»" if c.get("evidence") else ""
            print(f"  {lid:32s} {tag:22s} reason={c['reason']}{ev}")
        elif c["kind"] == "design_debt":
            dd += 1
            green, note = run_predicate(c["dissolves_when"], root)
            state = "DISSOLVABLE→discharge" if green else "not-yet"
            print(f"  {lid:32s} design_debt            organ={c['organ']} [{c['status']}] {state} ({note})")
        else:
            unc += 1
            print(f"  {lid:32s} UNCLASSIFIED           << classify: add sovereignty{{reason}} or design_debt{{organ,dissolves_when}}")
    print(f"\n  {len(open_levers)} open: {sov} sovereignty · {dd} design_debt · {unc} UNCLASSIFIED")
    return unc


def cmd_check(levers: list[dict]) -> int:
    rc = 0
    for lev in (l for l in levers if is_open(l)):
        lid = lev.get("id", "<no-id>")
        for p in malformed_reasons(lev):
            print(f"FAIL  lever {lid}: {p}")
            rc = 1
        c = classify(lev)
        if c["kind"] == "UNCLASSIFIED":
            print(f"FAIL  lever {lid}: UNCLASSIFIED — automatable homework may be parked on his head. "
                  f"Tag sovereignty{{reason}} (irreducibly his) or design_debt{{organ,dissolves_when}} (the beat owes it).")
            rc = 1
    if rc == 0:
        n = sum(1 for l in levers if is_open(l))
        print(f"ok    every open lever ({n}) is proven-sovereign or converted to design_debt")
    return rc


def cmd_dissolve(levers: list[dict], root: str, apply: bool) -> int:
    armed = apply and os.environ.get("LIMEN_LEVER_DISSOLVE_APPLY") == "1"
    if apply and not armed:
        print("note  --apply given but LIMEN_LEVER_DISSOLVE_APPLY != 1 — dry-run (double-dark gate)")
    dissolved = []
    for lev in (l for l in levers if is_open(l)):
        c = classify(lev)
        if c["kind"] != "design_debt":
            continue
        green, note = run_predicate(c["dissolves_when"], root)
        if green:
            dissolved.append((lev, c, note))
            print(f"DISSOLVED  {lev.get('id')}: {c['organ']} satisfies dissolves_when ({note})")
    if not dissolved:
        print("ok    no design_debt lever is dissolvable this pass (nothing to auto-discharge)")
        return 0
    if not armed:
        print(f"\n{len(dissolved)} lever(s) DISSOLVABLE — re-run with --apply and LIMEN_LEVER_DISSOLVE_APPLY=1 to discharge.")
        return 0
    # Arm: stamp discharged crediting the organ, not the human.
    for lev, c, note in dissolved:
        lev["discharged"] = (f"dissolved by organ {c['organ']} — dissolves_when green ({note}); "
                             f"no human action taken. (lever-classify --dissolve)")
    with open(REGISTRY, "w") as fh:
        json.dump({k: v for k, v in load_registry(REGISTRY).items() if k != "levers"} | {"levers": levers}, fh, indent=2)
        fh.write("\n")
    print(f"\nDischarged {len(dissolved)} lever(s), crediting the organ. Run scripts/sync-hishand-issues.py --apply to close their issues.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="exit 0 iff every open lever is sovereign-or-converted")
    ap.add_argument("--list", action="store_true", help="print each open lever's classification + dissolvable state")
    ap.add_argument("--dissolve", action="store_true", help="report/discharge design_debt levers whose dissolves_when is green")
    ap.add_argument("--apply", action="store_true", help="with --dissolve: actually discharge (needs LIMEN_LEVER_DISSOLVE_APPLY=1)")
    args = ap.parse_args()

    root = os.path.dirname(os.path.dirname(os.path.abspath(REGISTRY)))
    d = load_registry(REGISTRY)
    levers = d.get("levers", [])
    if not isinstance(levers, list) or not levers:
        print("FAIL  registry has no 'levers' list")
        return 1

    if args.list:
        return cmd_list(levers, root)
    if args.dissolve:
        return cmd_dissolve(levers, root, args.apply)
    # default: --check
    return cmd_check(levers)


if __name__ == "__main__":
    sys.exit(main())
