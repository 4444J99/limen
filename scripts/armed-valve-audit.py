#!/usr/bin/env python3
"""armed-valve-audit.py — separate PARKED levers from SILENTLY-OFF valves.

The gap this closes (retro 2026-06-24→07-08, finding 8; censor precedent
PREC-2026-07-08-armed-valve-outcome): a safe-by-default valve left disarmed reads
as "dropped". sync-censor-issues.py ran every beat in permanent dry-run, MONETA's
deployed URL returned nothing, LIMEN_DISPATCH sat unset — each satisfied the
closeout predicate while drifting the OUTCOME. Filing the disarming lever is not
arming the behavior: when the deliverable IS the live effect, a beat-wired organ
in permanent dry-run is an UNMET ask.

Two-source model (liquid, never a hand-maintained list):
  • DERIVED — every ``${LIMEN_*:-default}`` gate in the beat sources
    (metabolize.sh, heartbeat-loop.sh). Default "1" = armed-by-default (GREEN
    unless explicitly zeroed). Default "0" = disarmed-by-default → must be
    classified in spec/armed-valves.json or it surfaces as UNCLASSIFIED.
  • REGISTRY — spec/armed-valves.json holds only what derivation cannot: the
    deliverable-vs-safety classification, and external probes (a URL that must
    serve, an artifact that must carry the rail).

Verdicts per valve:
  ARMED        armed (env arm active, or probe green)
  PARKED       disarmed deliverable, but a lever in his-hand-levers.json cites it
               — surfaced once, owned, never nagged. Not a failure.
  SILENT-OFF   disarmed deliverable with NO lever citation — the failure class.
  SAFE-OFF     disarmed safety-class valve — off-by-default is the design.
  UNCLASSIFIED disarmed-by-default gate not in the registry — a new valve that
               must be classified (warning, not failure).
  SKIP         probe skipped (--offline).

Exit codes: 0 = no SILENT-OFF; 1 = at least one SILENT-OFF (with --check).
Always stamps logs/armed-valve-audit.json (fail-open on unwritable paths).

Usage:
  python3 scripts/armed-valve-audit.py            # report + stamp
  python3 scripts/armed-valve-audit.py --check    # gate mode: exit 1 on SILENT-OFF
  python3 scripts/armed-valve-audit.py --offline  # skip url probes (CI-safe)
"""

import argparse
import datetime
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))

def gate_re(prefix):
    return re.compile(r"\$\{(" + re.escape(prefix) + r"[A-Z0-9_]+):-([^}]*)\}")

# beat gates that select cadence/limits/paths, not behavior valves — never audited
NON_VALVE_RE = re.compile(
    r"^LIMEN_(BEAT|MINE_LIMIT|LOCAL_LIMIT|BACKLOG_FLOOR|NET_HOST|ROOT|WORKSPACE_ROOT"
    r"|CREDS_MAP|OWNERS|TASKS|GITHUB|FABLE|CLAUDE_RETRY)"
)


def discover_gates(sources, prefix="LIMEN_"):
    """Every boolean gate (``${<prefix>NAME:-0|1}``) in the beat sources → {name: default}.

    Only defaults of exactly "0"/"1" are valves (arm/disarm semantics); numeric
    tunables, paths, and command substitutions are parameters, not behaviors.
    """
    gates = {}
    rx = gate_re(prefix)
    for src in sources:
        p = Path(src)
        if not p.exists():
            continue
        for name, default in rx.findall(p.read_text(errors="replace")):
            default = default.strip()
            if default in ("0", "1") and not NON_VALVE_RE.match(name):
                gates.setdefault(name, default)
    return gates


def env_view(env_file):
    """os.environ overlaid on ~/.limen.env (export KEY=VALUE lines)."""
    view = {}
    p = Path(env_file).expanduser()
    if p.exists():
        for line in p.read_text(errors="replace").splitlines():
            m = re.match(r"\s*(?:export\s+)?([A-Z0-9_]+)=(.*)$", line)
            if m:
                view[m.group(1)] = m.group(2).strip().strip("'\"")
    view.update(os.environ)
    return view


def lever_citations(levers_path):
    """Raw text of the his-hand registry — a valve id appearing there is PARKED."""
    p = Path(levers_path)
    return p.read_text(errors="replace") if p.exists() else ""


def probe_url(entry, timeout=10):
    """(ok, note) for url / url_contains probes. Never raises."""
    url = entry["url"]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "limen-armed-valve-audit"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            if entry["kind"] == "url_contains":
                body = resp.read(4_000_000).decode("utf-8", errors="replace")
                ok = entry["needle"] in body
                return ok, f"{status}, needle {'present' if ok else 'ABSENT'}"
            ok = status == entry.get("expect_status", 200)
            return ok, str(status)
    except Exception as exc:  # noqa: BLE001 — probe failure IS the finding
        return False, f"unreachable ({type(exc).__name__})"


def audit(registry, gates, env, levers_text, offline=False):
    rows = []
    classified = set()

    for entry in registry.get("deliverable", []):
        vid = entry["id"]
        classified.add(vid)
        lever = entry.get("lever")
        cited = bool(lever) and lever in levers_text or vid in levers_text
        if entry["kind"] == "env":
            armed = env.get(vid, gates.get(vid, "0")) == entry.get("expected", "1")
            note = f"env={env.get(vid, '<unset>')}"
        elif offline:
            rows.append(dict(id=vid, verdict="SKIP", note="offline", what=entry.get("what", "")))
            continue
        else:
            armed, note = probe_url(entry)
        verdict = "ARMED" if armed else ("PARKED" if cited else "SILENT-OFF")
        rows.append(dict(id=vid, verdict=verdict, note=note, what=entry.get("what", "")))

    safety = set(registry.get("safety", []))
    classified |= safety

    for name, default in sorted(gates.items()):
        if name in classified:
            if name in safety and env.get(name, default) != "1":
                rows.append(dict(id=name, verdict="SAFE-OFF", note=f"default={default}", what="safety-class; off is the design"))
            continue
        # classification derives from the CODE default only — env must never hide a
        # gate from the registry check, or --contract flaps between hosts and CI
        if default == "1":
            rows.append(dict(id=name, verdict="ARMED", note=f"default={default}", what=""))
        else:
            rows.append(dict(id=name, verdict="UNCLASSIFIED", note=f"default={default}", what="new disarmed-by-default gate — classify in spec/armed-valves.json"))
    return rows


def stamp(rows, path):
    counts = {}
    for r in rows:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    payload = dict(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        counts=counts,
        valves=rows,
    )
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=1) + "\n")
    except OSError as exc:
        print(f"  (stamp skipped: {exc})", file=sys.stderr)
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description="Separate parked levers from silently-off valves.")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on any SILENT-OFF")
    ap.add_argument("--offline", action="store_true", help="skip url probes (CI-safe, deterministic)")
    ap.add_argument("--contract", action="store_true",
                    help="registry-completeness rung only (repo-deterministic): exit 1 on any "
                         "UNCLASSIFIED gate; env/url liveness rungs are the beat's job")
    # code inputs pin to the script's own repo (a dev worktree audits ITS contract,
    # never the runtime root's — the prompt-lifecycle-ledger live-root lesson);
    # only the stamp lands in the runtime root's logs/.
    ap.add_argument("--registry", default=str(SCRIPT_ROOT / "spec" / "armed-valves.json"))
    ap.add_argument("--sources", nargs="*", default=[str(SCRIPT_ROOT / "scripts" / "metabolize.sh"), str(SCRIPT_ROOT / "scripts" / "heartbeat-loop.sh")])
    ap.add_argument("--gate-prefix", default="LIMEN_",
                    help="env-var namespace to derive gates from (tests use a fixture prefix "
                         "so the governed namespace never gains undeclared tokens)")
    ap.add_argument("--env-file", default=str(Path.home() / ".limen.env"))
    ap.add_argument("--levers", default=str(SCRIPT_ROOT / "his-hand-levers.json"))
    ap.add_argument("--stamp", default=str(ROOT / "logs" / "armed-valve-audit.json"))
    ap.add_argument("--json", action="store_true", help="print rows as JSON")
    args = ap.parse_args(argv)

    registry = json.loads(Path(args.registry).read_text())
    gates = discover_gates(args.sources, prefix=args.gate_prefix)
    env = env_view(args.env_file)
    levers_text = lever_citations(args.levers)

    rows = audit(registry, gates, env, levers_text, offline=args.offline)
    counts = stamp(rows, args.stamp)

    if args.json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            if r["verdict"] in ("ARMED",):
                continue  # green is silent; the beat log carries only what needs eyes
            print(f"  {r['verdict']:<12} {r['id']:<28} {r['note']}" + (f" — {r['what']}" if r["what"] else ""))
        summary = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        print(f"armed-valve-audit: {summary or 'no valves discovered'}")

    if args.contract:
        unclassified = [r for r in rows if r["verdict"] == "UNCLASSIFIED"]
        if args.check and unclassified:
            print(f"armed-valve-audit: RED — registry lags the code; {len(unclassified)} "
                  "unclassified gate(s): " + ", ".join(r["id"] for r in unclassified), file=sys.stderr)
            return 1
        return 0

    silent = [r for r in rows if r["verdict"] == "SILENT-OFF"]
    if args.check and silent:
        print(f"armed-valve-audit: RED — {len(silent)} deliverable valve(s) silently off: "
              + ", ".join(r["id"] for r in silent), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
