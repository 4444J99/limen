#!/usr/bin/env python3
"""background-items-census.py — every background item on the host maps to a declared owner.

The gap this closes. On 2026-08-15 the operator's Login Items & Extensions pane showed
"DomusAgentHost" four times (all "Item from unidentified developer") plus bare rows named
``bash``, ``python3``, ``node``, ``cloudflared`` — and the estate had no surface that could say
what any of them were. The answer (four legitimate LaunchAgents sharing one TCC-principal
binary; macOS names a legacy BTM row by its executable BASENAME, not the plist Label, and files
adhoc-signed binaries under a synthetic "Unknown Developer") had to be derived by hand with
``sfltool dumpbtm``. This organ makes that answer standing: a declared registry
(``spec/background-items.json``) × the live LaunchAgents directory × (when available) the BTM
database, classified every beat.

Classes (dialogs-silenced vocabulary — classify and name the owner, mutate nothing):
  ESTATE       label declared in the registry's ``estate_agents``
  THIRD-PARTY  label/identifier matches a ``third_party_prefixes`` entry (Rule 55a §4 exempt)
  TOMBSTONE    plist parses but declares no Program/ProgramArguments (e.g. Keystone stubs)
  UNDECLARED   anything else — the drift class this predicate exists to catch

``--check`` exits 1 iff any UNDECLARED plist exists in the LaunchAgents directory. Declared
estate agents with no installed plist are reported (``missing_estate``) but do not gate — the
liveness organ (scripts/launch-agent-liveness.py) owns aliveness; this organ owns declaration
parity. BTM rows are corroboration only (``sfltool dumpbtm`` works unprivileged on this host,
measured 2026-08-15): unmatched BTM identifiers are surfaced as advisory, never gate, because
BTM also carries app/SMAppService registrations the plist directory does not own.

This organ NEVER writes a plist, toggles a row, or touches launchd state — Rule 55/55a's
hard-block hook is the authority; classification and reporting only.

Off-darwin (CI) the LaunchAgents directory is absent and sfltool does not exist: both fail OPEN
(empty census, exit 0), same contract as launch-agent-liveness.

PII-clean: labels, basenames, classes, counts, ISO times only — never argv tails, tokens, paths
outside the estate.

Usage:
  python3 scripts/background-items-census.py            # report + receipt, exit 0
  python3 scripts/background-items-census.py --check    # gate mode: exit 1 on UNDECLARED
  python3 scripts/background-items-census.py --registry F   # override registry (tests)
"""

import argparse
import datetime
import json
import os
import plistlib
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))
DEFAULT_REGISTRY = ROOT / "spec" / "background-items.json"
LAUNCHAGENTS_DIR = Path(os.environ.get("LIMEN_LAUNCHAGENTS_DIR", Path.home() / "Library" / "LaunchAgents"))
RECEIPT = ROOT / "logs" / "background-items-census.json"
IS_DARWIN = sys.platform == "darwin"

BTM_IDENTIFIER_RE = re.compile(r"^\s*Identifier:\s+(?:\d+\.)?(\S+)\s*$", re.MULTILINE)


def load_registry(path):
    """Registry as {estate: {label: entry}, prefixes: [..]}. Missing/unreadable -> empty (fail open)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"estate": {}, "prefixes": []}
    estate = data.get("estate_agents", {}) if isinstance(data, dict) else {}
    prefixes = data.get("third_party_prefixes", []) if isinstance(data, dict) else []
    return {
        "estate": {k: v for k, v in estate.items() if isinstance(v, dict)},
        "prefixes": [p for p in prefixes if isinstance(p, str) and p],
    }


# ── injectable side-effect boundaries (monkeypatched in tests) ─────────────────────────────────
def _sfltool_dumpbtm(timeout=30):
    """Raw `sfltool dumpbtm` text, or None when unavailable (non-darwin, missing, or refused)."""
    if not IS_DARWIN:
        return None
    try:
        proc = subprocess.run(["sfltool", "dumpbtm"], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 and proc.stdout else None


def classify_label(label, registry):
    if label in registry["estate"]:
        return "estate"
    if any(label.startswith(p) for p in registry["prefixes"]):
        return "third-party"
    return None


def program_basename(plist):
    args = plist.get("ProgramArguments")
    program = plist.get("Program") or (args[0] if isinstance(args, list) and args else None)
    return Path(program).name if isinstance(program, str) and program else None


def census_plists(directory, registry):
    """Classify every .plist in the LaunchAgents directory. Missing dir -> empty census."""
    rows = []
    try:
        paths = sorted(Path(directory).glob("*.plist"))
    except OSError:
        paths = []
    for path in paths:
        label = path.name[: -len(".plist")]
        try:
            with open(path, "rb") as fp:
                plist = plistlib.load(fp)
        except (OSError, ValueError, plistlib.InvalidFileException):
            rows.append({"label": label, "class": "undeclared", "rendered_as": None, "note": "unparseable"})
            continue
        rendered = program_basename(plist)
        cls = classify_label(label, registry)
        if cls is None and rendered is None:
            cls = "tombstone"
        rows.append({"label": label, "class": cls or "undeclared", "rendered_as": rendered})
    return rows


def census_btm(dump_text, registry):
    """Classify BTM identifiers from a dumpbtm capture. None/empty -> skipped."""
    if not dump_text:
        return {"available": False, "unmatched": [], "total": 0}
    identifiers = sorted({m for m in BTM_IDENTIFIER_RE.findall(dump_text) if "." in m})
    unmatched = [i for i in identifiers if classify_label(i, registry) is None]
    return {"available": True, "unmatched": unmatched, "total": len(identifiers)}


def missing_estate(rows, registry):
    installed = {r["label"] for r in rows}
    return sorted(label for label in registry["estate"] if label not in installed)


def build_report(registry):
    rows = census_plists(LAUNCHAGENTS_DIR, registry)
    btm = census_btm(_sfltool_dumpbtm(), registry)
    undeclared = [r["label"] for r in rows if r["class"] == "undeclared"]
    return {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "launchagents_dir_present": Path(LAUNCHAGENTS_DIR).is_dir(),
        "counts": {
            "estate": sum(1 for r in rows if r["class"] == "estate"),
            "third_party": sum(1 for r in rows if r["class"] == "third-party"),
            "tombstone": sum(1 for r in rows if r["class"] == "tombstone"),
            "undeclared": len(undeclared),
        },
        "rows": rows,
        "undeclared": undeclared,
        "missing_estate": missing_estate(rows, registry),
        "btm": btm,
    }


def write_receipt(report):
    try:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        RECEIPT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass  # a receipt failure must never break the beat


def print_report(report):
    c = report["counts"]
    print(
        f"background-items census: {c['estate']} estate, {c['third_party']} third-party, "
        f"{c['tombstone']} tombstone, {c['undeclared']} UNDECLARED"
    )
    for row in report["rows"]:
        if row["class"] == "estate" and row["rendered_as"] and row["rendered_as"] != row["label"]:
            print(f"  estate      {row['label']}  (renders as '{row['rendered_as']}' in Login Items)")
    for label in report["undeclared"]:
        print(f"  UNDECLARED  {label} — no registry owner and no third-party exemption (spec/background-items.json)")
    for label in report["missing_estate"]:
        print(f"  note        declared estate agent not installed: {label} (liveness organ owns aliveness)")
    if report["btm"]["available"]:
        extra = report["btm"]["unmatched"]
        print(f"  btm         {report['btm']['total']} identifiers; {len(extra)} unmatched (advisory)")
        for ident in extra[:10]:
            print(f"  btm-extra   {ident}")
    else:
        print("  btm         skipped (sfltool unavailable)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="exit 1 if any UNDECLARED plist exists")
    parser.add_argument("--no-receipt", action="store_true", help="report only; write no receipt")
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY), help="registry override (tests)")
    args = parser.parse_args()

    registry = load_registry(args.registry)
    report = build_report(registry)
    print_report(report)
    if not args.no_receipt:
        write_receipt(report)

    if args.check and report["undeclared"]:
        print(
            f"FAIL — {len(report['undeclared'])} undeclared background item(s); declare or exempt each in spec/background-items.json"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
