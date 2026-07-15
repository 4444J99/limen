#!/usr/bin/env python3
"""HORREVM — the granary's doctor: every storage rail matches its DECLARED role.

Reads institutio/governance/storage-roles.yaml (the roles registry — the strategy the 2026-06-15
Archive4T endgame prose declared but never wired) and derives actual-vs-declared per rail each
scheduled beat, writing logs/cloud-storage-health.json (counts + masked identifiers only, no PII).

Pure sensor: zero mutations, lockless, fail-open — modeled on cvstos-organ.py. Every probe is a
bounded read-only subprocess (the library-preserve.py shape); a probe that errors or times out
degrades to `unknown` (advisory), never a false red and never a wedge. Drift — a rail whose actual
state contradicts its declaration (a 4th churned iCloud provider domain, a desktop File Provider
app reappearing on a headless-custody rail, the Archive4T SSOT unmounted) — exits 1 so the beat's
advisory escalation surfaces it.

Verbs:
  --check     (default) evaluate every rail; write the health log; exit 0 iff no drift
  --doctor    repo-deterministic self-check (registry schema/enums/paths) — no host probes
  --baseline  PRINT (never write) an accepted_remnants YAML block from the live census, masked
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "institutio" / "governance" / "storage-roles.yaml"
OUT = ROOT / "logs" / "cloud-storage-health.json"
CLOUDSTORAGE = Path.home() / "Library" / "CloudStorage"
GROUP_CONTAINERS = Path.home() / "Library" / "Group Containers"

DECLARED_STATES = {"adopted", "dormant-by-design", "pending-trust-gates"}
KNOWN_PROBES = {
    "brctl_container",
    "payload_band_gib",
    "fileprovider_error_scan",
    "processes",
    "bzvol_marker",
    "tmutil_latestbackup",
}
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
ACCOUNT_RE = re.compile(r"[\w.+-]+@[\w.-]+")
LAST_SYNC_RE = re.compile(r"last-sync:(\d{4}-\d{2}-\d{2} [\d:.]+)")


def _mask(value):
    """Recursively mask account tokens in anything that gets printed or serialized (PII firewall)."""
    if isinstance(value, str):
        return ACCOUNT_RE.sub("<account>", value)
    if isinstance(value, list):
        return [_mask(v) for v in value]
    if isinstance(value, dict):
        return {_mask(k): _mask(v) for k, v in value.items()}
    return value


def _run(cmd: list[str], timeout: int) -> tuple[int | None, str]:
    """Bounded read-only subprocess; (None, "") on timeout/absence — fail-open, never raises."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None, ""


def parse_brctl(rc: int | None, out: str) -> dict:
    """Three-way verdict on undocumented, ANSI-laden brctl output: token -> match,
    ran-without-token -> drift (that IS the signal), rc None/nonzero -> unknown."""
    if rc is None or rc != 0:
        return {"verdict": "unknown", "caught_up": None, "last_sync": None}
    text = ANSI_RE.sub("", out)
    caught_up = "caught-up" in text
    sync = LAST_SYNC_RE.search(text)
    return {
        "verdict": "match" if caught_up else "drift",
        "caught_up": caught_up,
        "last_sync": sync.group(1) if sync else None,
    }


def _payload_gib(path: str, timeout: int = 45) -> float | None:
    rc, out = _run(["du", "-sk", os.path.expanduser(path)], timeout)
    if rc is None or not out.strip():
        return None
    try:
        return int(out.split()[0]) / (1024 * 1024)
    except (ValueError, IndexError):
        return None


def _glob_count(pattern: str) -> list[str]:
    return sorted(os.path.basename(p) for p in glob.glob(os.path.expanduser(pattern)))


def remnant_check(accepted: list[dict]) -> tuple[list[str], list[str]]:
    """Per-pattern census vs the recorded baseline. Returns (notes, drifts)."""
    notes, drifts = [], []
    for entry in accepted or []:
        matches = _glob_count(str(entry.get("pattern", "")))
        cap = int(entry.get("max_count", 0))
        if len(matches) > cap:
            drifts.append(f"remnant pattern over baseline ({len(matches)}>{cap}): {entry.get('pattern')}")
        else:
            notes.append(f"remnants at baseline ({len(matches)}/{cap}): {entry.get('pattern')}")
    return notes, drifts


def cloudstorage_census(rails: dict) -> list[str]:
    """Entries under ~/Library/CloudStorage matched by NO rail's patterns/mount globs = unrecognized."""
    patterns: list[str] = []
    for rail in rails.values():
        for entry in rail.get("accepted_remnants") or []:
            pat = str(entry.get("pattern", ""))
            if "CloudStorage" in pat:
                patterns.append(os.path.basename(os.path.expanduser(pat)))
        for g in rail.get("mount_globs") or []:
            patterns.append(os.path.basename(os.path.expanduser(str(g))))
    unrecognized = []
    try:
        entries = sorted(e for e in os.listdir(CLOUDSTORAGE) if not e.startswith("."))
    except OSError:
        return []  # fail-open: census unreadable is unknown, not drift
    import fnmatch

    for name in entries:
        if not any(fnmatch.fnmatch(name, pat) for pat in patterns):
            unrecognized.append(name)
    return unrecognized


def dormant_check(expect: dict, pluginkit_out: str) -> tuple[list[str], list[str]]:
    """The desktop File Provider layer must be ABSENT (required even after headless adoption)."""
    notes, drifts = [], []
    for app in expect.get("apps") or []:
        if Path(app).exists():
            drifts.append(f"desktop app present (declared absent): {app}")
        else:
            notes.append(f"desktop app absent as declared: {os.path.basename(app)}")
    tokens = [t.lower() for t in expect.get("fileprovider_tokens") or []]
    if pluginkit_out and tokens:
        low = pluginkit_out.lower()
        hits = [t for t in tokens if t in low]
        if hits:
            drifts.append(f"File Provider registered (declared absent): {','.join(hits)}")
    return notes, drifts


def gates_summary(rail: dict, auto_results: dict) -> dict:
    """Fold probe results into the rail's declared trust gates."""
    passed = failed = manual = 0
    for gate in rail.get("trust_gates") or []:
        if not gate.get("automatable"):
            if gate.get("proven") is None:
                manual += 1
            continue
        res = auto_results.get(str(gate.get("id")))
        if res is True:
            passed += 1
        elif res is False:
            failed += 1
        # None = unresolved this pass (e.g. custody signal absent) — neither pass nor fail
    return {"automatable_pass": passed, "automatable_fail": failed, "manual_outstanding": manual}


def evaluate_rail(rail_id: str, rail: dict, host: dict) -> dict:
    declared = str(rail.get("declared_state", ""))
    notes: list[str] = []
    drifts: list[str] = []
    unknowns: list[str] = []
    auto: dict[str, bool | None] = {}
    probes = rail.get("probes") or {}

    if "brctl_container" in probes:
        rc, out = _run(["brctl", "status", str(probes["brctl_container"])], 20)
        parsed = parse_brctl(rc, out)
        auto["brctl-caught-up"] = {"match": True, "drift": False}.get(parsed["verdict"])
        if parsed["verdict"] == "drift":
            drifts.append("brctl ran without a caught-up token")
        elif parsed["verdict"] == "unknown":
            unknowns.append("brctl unavailable/timeout")
        else:
            notes.append(f"brctl caught-up (last-sync {parsed['last_sync']})")

    if "payload_band_gib" in probes:
        band = probes["payload_band_gib"] or {}
        gib = _payload_gib(str(rail.get("mount", "")))
        if gib is None:
            unknowns.append("payload size unknown (du timeout)")
        elif gib > float(band.get("max", float("inf"))) or gib < float(band.get("min", 0)):
            drifts.append(f"local payload {gib:.1f} GiB outside band {band.get('min')}-{band.get('max')}")
        else:
            notes.append(f"local payload {gib:.1f} GiB within band")

    if "fileprovider_error_scan" in probes:
        cfg = probes["fileprovider_error_scan"] or {}
        rc, out = _run(["fileproviderctl", "dump"], 30)
        if rc is None:
            unknowns.append("fileproviderctl unavailable/timeout")
        else:
            counts = {t: out.count(t) for t in cfg.get("tokens") or []}
            total = sum(counts.values())
            cap = cfg.get("max")
            if cap is not None and total > int(cap):
                drifts.append(f"file-provider error tokens over cap ({total}>{cap})")
            else:
                notes.append(f"file-provider error tokens: {total} (report-only)")

    if "processes" in probes:
        wanted = [str(p) for p in probes["processes"]]
        comm = host.get("ps", "")
        live = [p for p in wanted if p in comm]
        auto["client-running"] = bool(live)
        if live:
            notes.append(f"client processes live: {','.join(live)}")
        else:
            drifts.append(f"no client process visible ({','.join(wanted)})")

    if "bzvol_marker" in probes:
        present = Path(str(probes["bzvol_marker"])).exists()
        auto["volume-selected"] = present
        (notes if present else drifts).append(
            "bzvol marker present" if present else f"bzvol marker missing: {probes['bzvol_marker']}"
        )

    if "tmutil_latestbackup" in probes:
        rc, out = _run(["tmutil", "latestbackup"], 20)
        if rc == 0 and out.strip():
            auto["latest-backup"] = True
            notes.append("tmutil reports a latest backup")
        else:
            unknowns.append("tmutil latestbackup unavailable (rc!=0 -> unknown, never drift)")

    if rail.get("mount") and "payload_band_gib" not in probes:
        mounted = os.path.ismount(os.path.expanduser(str(rail["mount"])))
        auto["mounted"] = mounted
        if mounted:
            notes.append("mounted")
        elif rail.get("required_mounted"):
            drifts.append(f"required volume not mounted: {rail['mount']}")
        else:
            notes.append("not mounted (optional; report-only)")

    if rail.get("dormant_expectations"):
        d_notes, d_drifts = dormant_check(rail["dormant_expectations"], host.get("pluginkit", ""))
        notes += d_notes
        drifts += d_drifts

    r_notes, r_drifts = remnant_check(rail.get("accepted_remnants") or [])
    notes += r_notes
    drifts += r_drifts

    if rail.get("custody_signal"):
        signal = ROOT / str(rail["custody_signal"])
        if signal.exists():
            try:
                custody = json.loads(signal.read_text(encoding="utf-8")).get("rails", {}).get(rail_id, {})
                for gate_id, key in (
                    ("token", "token_ok"),
                    ("roundtrip", "probe_roundtrip_ok"),
                    ("integrity", "verify_ok"),
                    ("restore", "restore_ok"),
                ):
                    if key in custody:
                        auto[gate_id] = bool(custody[key])
                notes.append("custody signal read")
            except (OSError, ValueError):
                unknowns.append("custody signal unreadable")
        else:
            notes.append("custody PARKED on L-CLOUD-EGRESS-CONSENT (no custody signal yet — by design)")

    # pending-trust-gates: unmet gates are advisory, never drift (adoption in progress by
    # declaration). The dormant desktop layer and the remnant baseline still drift above — those
    # append their own lines. Adopted rails' probe failures also append their own drift lines; the
    # custody-signal gates are the one auto-only source, folded in here.
    if declared == "pending-trust-gates":
        failed_gates = sorted(k for k, v in auto.items() if v is False)
        if failed_gates:
            notes.append(f"trust gates not yet green (advisory while pending): {','.join(failed_gates)}")
    elif declared == "adopted":
        for gate_id in ("token", "roundtrip", "integrity", "restore"):
            if auto.get(gate_id) is False:
                drifts.append(f"custody trust gate failing: {gate_id}")

    verdict = "drift" if drifts else ("unknown" if unknowns and not notes else "match")
    return {
        "declared": declared,
        "verdict": verdict,
        "notes": notes + [f"unknown: {u}" for u in unknowns],
        "drift": drifts,
        "gates": gates_summary(rail, auto),
    }


def load_registry() -> dict | None:
    try:
        import yaml

        return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 — registry unreadable IS the finding, reported by caller
        print(f"storage-roles registry unreadable: {exc}")
        return None


def check() -> int:
    reg = load_registry()
    if not reg or not isinstance(reg.get("rails"), dict):
        return 1
    rails = reg["rails"]
    # one process-table scan + one pluginkit scan shared by every rail (no per-rail forks)
    _, ps_out = _run(["ps", "-axo", "comm="], 15)
    _, pk_out = _run(["pluginkit", "-m"], 15)
    host = {"ps": ps_out, "pluginkit": pk_out}
    report_rails = {rid: evaluate_rail(rid, rail, host) for rid, rail in rails.items()}
    unrecognized = cloudstorage_census(rails)
    counts = {"match": 0, "drift": 0, "unknown": 0}
    for res in report_rails.values():
        counts[res["verdict"]] += 1
    if unrecognized:
        counts["drift"] += 1
    exit_code = 1 if counts["drift"] else 0
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "schema_version": "0.1",
        "rails": report_rails,
        "census": {"unrecognized": unrecognized},
        "counts": counts,
        "exit": exit_code,
    }
    report = _mask(report)
    try:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"health log unwritable ({exc}) — report to stdout only")
    for rid, res in report["rails"].items():
        marker = {"match": "ok", "drift": "DRIFT", "unknown": "unknown"}[res["verdict"]]
        line = f"  {rid}: {marker} [{res['declared']}]"
        if res["drift"]:
            line += " — " + "; ".join(res["drift"])
        print(line)
    if unrecognized:
        print(f"  census: DRIFT — unrecognized CloudStorage entries: {', '.join(_mask(unrecognized))}")
    print(
        f"HORREVM: {counts['match']} match / {counts['drift']} drift / {counts['unknown']} unknown -> exit {exit_code}"
    )
    return exit_code


def doctor() -> int:
    """Repo-deterministic self-check — no host probes (the omega det rung)."""
    problems: list[str] = []
    reg = load_registry()
    if reg is None:
        problems.append("registry missing or unparseable")
    else:
        rails = reg.get("rails")
        if not isinstance(rails, dict) or not rails:
            problems.append("rails: missing or empty")
        else:
            for rid, rail in rails.items():
                for key in ("service", "declared_state", "role", "never", "trust_gates"):
                    if key not in rail:
                        problems.append(f"{rid}: missing {key}")
                if rail.get("declared_state") not in DECLARED_STATES:
                    problems.append(f"{rid}: declared_state not in {sorted(DECLARED_STATES)}")
                for probe in rail.get("probes") or {}:
                    if probe not in KNOWN_PROBES:
                        problems.append(f"{rid}: unknown probe {probe}")
                for gate in rail.get("trust_gates") or []:
                    if not isinstance(gate.get("automatable"), bool) or not gate.get("id"):
                        problems.append(f"{rid}: malformed trust gate {gate}")
                for entry in rail.get("accepted_remnants") or []:
                    if not entry.get("pattern") or not isinstance(entry.get("max_count"), int):
                        problems.append(f"{rid}: malformed accepted_remnants entry {entry}")
    if not os.access(OUT.parent, os.W_OK):
        problems.append(f"logs dir not writable: {OUT.parent}")
    for p in problems:
        print(f"  DOCTOR: {p}")
    print(f"HORREVM --doctor: {'OK' if not problems else f'{len(problems)} problem(s)'}")
    return 1 if problems else 0


def baseline() -> int:
    """PRINT an accepted_remnants block from the live census (masked); operator pastes it in."""
    print("# accepted_remnants candidates (masked; account-bearing names become globs) — paste per rail:")
    roots = [CLOUDSTORAGE, GROUP_CONTAINERS]
    for root in roots:
        try:
            entries = sorted(e for e in os.listdir(root) if not e.startswith("."))
        except OSError:
            continue
        for name in entries:
            pat = re.sub(r"-[\w.+-]+@[\w.-]+", "-*", name)
            print(
                f'  - {{pattern: "~/{root.relative_to(Path.home())}/{pat}", max_count: 1, note: "baselined '
                f'{datetime.now(timezone.utc).date()}"}}'
            )
    return 0


def main() -> int:
    os.environ.setdefault("OS_ACTIVITY_MODE", "disable")  # fork/os_log SIGSEGV mitigation (#831)
    parser = argparse.ArgumentParser(description="HORREVM storage-rails doctor")
    parser.add_argument("--check", action="store_true", help="evaluate rails vs declarations (default)")
    parser.add_argument("--doctor", action="store_true", help="registry schema self-check (no host probes)")
    parser.add_argument("--baseline", action="store_true", help="print an accepted_remnants block (never writes)")
    args = parser.parse_args()
    if args.doctor:
        return doctor()
    if args.baseline:
        return baseline()
    return check()


if __name__ == "__main__":
    sys.exit(main())
