#!/usr/bin/env python3
"""censor.py — THE CENSOR: limen's insights→actions institution.

The Roman censor periodically audited the institution itself and adjusted standing
on a fixed cadence (the lustrum). This is that office for the fleet: on calendar
cadences it reads the system's own signals — fleet performance, organ health,
behavioural drift — and acts to make the system change and grow. It CONVERGES
organs that already exist (self-improve, organ-health, the insights-* tools); it
does not rebuild them ([[pillars-platform-convergence]], [[excavate-before-redoing-solved-work]]).

CONSTITUTION — separation of powers, because branches exist "for a reason at scale":
  • LEGISLATIVE  censor/protocols.yaml — defines what may be done and by which branch.
  • EXECUTIVE    the actuators below — they ONLY do what the cascade authorised.
  • JUDICIAL     the verifier — authorises irreversible actions and writes case law
                 (precedents.jsonl) from outcomes. Applying is never the branch that judged.

DECISION CASCADE (logic prevails — autonomy is derived, never a dial):
  1. PROTOCOL dictates  → action determined; disposition from reversibility + signing branch.
  2. else PRECEDENT     → a prior like-case with a good outcome suggests the action.
  3. else EXPLORATION   → emit a study, never dead-stop ([[no-never-happens-again]]).
  4. until IDEAL-FORM   → derived certainty acts AND proposes the rule back as law.

CALENDAR CADENCE over a beat-counting heartbeat: the heartbeat fires censor.py on a
beat; the Censor itself gates each tier (hourly/daily/weekly) on WALL-CLOCK elapsed
since that tier last ran (logs/censor-state.json). That is the missing calendar layer.

Anti-waste + never-"NO": read-mostly; every actuator is wrapped + timeout-bounded +
fail-open. Writes only its own state/ledger and delegates contended writes to the
organs that own them. Default is DRY (report only); --apply lets the executive act.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
CENSOR_DIR = ROOT / "censor"
PROTOCOLS = Path(os.environ.get("LIMEN_CENSOR_PROTOCOLS", CENSOR_DIR / "protocols.yaml"))
STATE_PATH = LOGS / "censor-state.json"
LEDGER_PATH = LOGS / "censor-decisions.jsonl"      # high-volume audit trail → runtime (gitignored)
PRECEDENTS_PATH = CENSOR_DIR / "precedents.jsonl"  # judicial case law → durable, committed
LAST_PATH = LOGS / "censor-last.json"   # compact summary the view reads
RESIDUAL_PATH = LOGS / "censor-residual.json"

TIER_SECONDS = {"hourly": 3600, "daily": 86400, "weekly": 604800, "monthly": 2592000}


def _positive_int_env(name, default):
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


ACTUATOR_TIMEOUT = _positive_int_env("LIMEN_CENSOR_TIMEOUT", 300)


# ─── primitives ──────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _iso(dt=None):
    return (dt or _now()).isoformat(timespec="seconds")


def _parse_ts(v):
    if not isinstance(v, str):
        return None
    try:
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _load_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def _load_yaml(path):
    try:
        import yaml
        return yaml.safe_load(Path(path).read_text()) or {}
    except Exception:
        return {}


def _load_jsonl(path):
    out = []
    try:
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    except OSError:
        pass
    return out


def _atomic_write(path, text):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, p)


def _append_jsonl(path, record):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a") as f:
        f.write(json.dumps(record) + "\n")


def _run(cmd, env_extra=None):
    """Run an actuator fail-open. Returns (ok, tail)."""
    env = dict(os.environ)
    if env_extra:
        env.update(env_extra)
    try:
        r = subprocess.run(cmd, cwd=str(ROOT), env=env, capture_output=True,
                           text=True, timeout=ACTUATOR_TIMEOUT)
        tail = (r.stdout or r.stderr or "").strip().splitlines()[-1:] or [""]
        return r.returncode == 0, tail[0][:200]
    except (subprocess.TimeoutExpired, OSError, ValueError) as e:
        return False, f"{type(e).__name__}: {e}"[:200]


# ─── cadence gating: beat-time → calendar-time ───────────────────────

def due_tiers(state, now, force=None):
    if force:
        return [force] if force in TIER_SECONDS else []
    last = (state or {}).get("last_run", {})
    due = []
    for tier, span in TIER_SECONDS.items():
        prev = _parse_ts(last.get(tier))
        if prev is None or (now - prev).total_seconds() >= span:
            due.append(tier)
    return due


# ─── signal gathering (read-only) ────────────────────────────────────

def _self_improve_proposal(refresh):
    if refresh:
        _run([sys.executable, "scripts/self-improve.py"])
    return _load_json(LOGS / "self-improve-proposal.json", {})


def gather_signals(tier, refresh=True):
    """Read the system's own signals for this tier. Each signal is a dict with a
    `type` and a short `subject`. Pure-ish: only refreshes organs when asked."""
    sigs = []
    if tier == "hourly":
        sigs.append({"type": "cadence_tick", "tier": "hourly", "subject": "hourly capture + proprioception"})
        health = _load_json(LOGS / "organ-health.json", {})
        for o in health.get("organs", []):
            if o.get("status") in ("stale", "down"):
                sigs.append({"type": "organ_health", "status": o["status"],
                             "subject": o.get("key", "?"), "age_h": o.get("age_h"),
                             "expected_h": o.get("expected_h")})
    elif tier == "daily":
        prop = _self_improve_proposal(refresh)
        for la in prop.get("lane_adjustments", []):
            if la.get("verdict"):
                sigs.append({"type": "lane_adjustment", "verdict": la["verdict"],
                             "subject": la.get("lane", "?"),
                             "target_weight": la.get("target_weight"),
                             "reason": la.get("reason", "")})
        for rk in prop.get("rerank", []):
            if rk.get("move") not in ("boost", "deprioritise"):
                continue   # 'hold' = self-improve chose no change → not a signal, not a study
            sigs.append({"type": "rerank", "move": rk.get("move"),
                         "subject": rk.get("pattern", "?"), "reason": rk.get("reason", "")})
        for rp in prop.get("retire_patterns", []):
            sigs.append({"type": "retire_pattern", "subject": rp.get("pattern", "?"),
                         "action_hint": rp.get("action"), "reason": (rp.get("evidence") or [""])[0]})
    elif tier == "weekly":
        # behavioural drift — recurring frictions become candidate standing corrections.
        # Read whatever drift signal exists; degrade gracefully if the tooling is absent.
        # A friction whose correction is already ADJUDICATED (a precedent with a good
        # outcome records where the standing correction lives) is annotated codified=yes:
        # the behavioural-rule lever was already blessed once — re-surfacing it every week
        # is the parked-blocker anti-pattern, so the cascade resolves it via precedent.
        # The friction still leaves the drift only empirically (a future report without it).
        settled = {pc.get("subject") for pc in _load_jsonl(PRECEDENTS_PATH)
                   if pc.get("type") == "recurring_friction"
                   and pc.get("outcome") in ("good", "applied-ok")}
        for src in (LOGS / "friction-federation.json", LOGS / "insights-drift.json"):
            d = _load_json(src, {})
            for fr in (d.get("recurring") or d.get("frictions") or [])[:8]:
                label = fr if isinstance(fr, str) else fr.get("pattern") or fr.get("label", "?")
                sigs.append({"type": "recurring_friction", "subject": label,
                             "codified": "yes" if label in settled else "no",
                             "reason": "recurring across the window"})
    return sigs


# ─── LEGISLATIVE: protocol matching ──────────────────────────────────

def match_protocol(signal, protocols):
    for p in protocols:
        when = p.get("when", {})
        if when.get("signal") != signal.get("type"):
            continue
        ok = True
        for k, v in when.items():
            if k == "signal":
                continue
            if k.endswith("_in"):
                if signal.get(k[:-3]) not in v:
                    ok = False
                    break
            elif signal.get(k) != v:
                ok = False
                break
        if ok:
            return p
    return None


# ─── JUDICIAL: precedent + outcome review ────────────────────────────

def match_precedent(signal, precedents):
    """A prior like-case (same type+subject) whose recorded outcome was good."""
    for pc in reversed(precedents):
        if pc.get("type") == signal.get("type") and pc.get("subject") == signal.get("subject"):
            if pc.get("outcome") in ("good", "applied-ok"):
                return pc
    return None


def disposition_for(protocol):
    """Autonomy DERIVED from reversibility + signing branch (never a dial)."""
    if protocol.get("his_lever"):
        return "surface"
    rev = protocol.get("reversible")
    branch = protocol.get("branch")
    if rev == "reversible" and branch == "executive":
        return "auto"
    if rev == "irreversible":
        return "surface" if protocol.get("his_lever") else "propose"
    return "propose"   # gated / judicial


# ─── THE CASCADE ─────────────────────────────────────────────────────

def cascade(signal, protocols, precedents):
    """protocol → precedent → exploration → (ideal-form, out of band). Returns a verdict."""
    p = match_protocol(signal, protocols)
    if p:
        return {"branch": "protocol", "protocol": p.get("id"),
                "action": p.get("action"), "mechanism": p.get("mechanism"),
                "reversible": p.get("reversible"), "his_lever": p.get("his_lever"),
                "disposition": disposition_for(p),
                "rationale": f"protocol {p.get('id')} dictates"}
    pc = match_precedent(signal, precedents)
    if pc:
        disp = "auto" if pc.get("reversible") == "reversible" else "propose"
        return {"branch": "precedent", "action": pc.get("action"),
                "reversible": pc.get("reversible"), "disposition": disp,
                "rationale": f"precedent {pc.get('id', '?')} (outcome {pc.get('outcome')})"}
    # no protocol, no precedent → explore, never stop
    return {"branch": "exploration", "action": "study this signal",
            "reversible": "reversible", "disposition": "explore",
            "rationale": "no protocol or precedent — exploration required (ideal-form pending)"}


# ─── EXECUTIVE: actuators (only run for 'auto' dispositions, only with --apply) ──

def execute(tier, verdict, signal, apply, retire_authorised):
    """Carry out an authorised, reversible action. Returns an outcome string."""
    if not apply:
        return "dry-run"
    if verdict["disposition"] != "auto":
        return "not-authorised-for-auto"
    sig_t = signal["type"]
    if sig_t == "cadence_tick":
        # hourly: capture the insights snapshot (fix the dormant hook) + refresh proprioception
        ok1, t1 = _run(["insights-snapshot", "--only-if-newer", "--quiet"])
        ok2, t2 = _run([sys.executable, "scripts/organ-health.py"])
        return f"capture={'ok' if ok1 else t1}; proprioception={'ok' if ok2 else t2}"
    if sig_t in ("lane_adjustment", "rerank"):
        # reversible loop closure: self-improve --apply feeds route.py / sets idempotent priority.
        # retire stays OFF unless the judicial branch authorised it (it never does in v1).
        env = {"LIMEN_SI_APPLY": "1", "LIMEN_SI_RETIRE": "1" if retire_authorised else "0"}
        ok, t = _run([sys.executable, "scripts/self-improve.py", "--apply"], env)
        return f"self-improve --apply: {'ok' if ok else t}"
    return "no-actuator"


# ─── main ────────────────────────────────────────────────────────────

def run_tier(tier, protocols, precedents, apply):
    signals = gather_signals(tier, refresh=apply)
    decisions = []
    # self-improve --apply covers ALL reversible lane/rerank signals in one idempotent call;
    # fire it at most once per tier to avoid redundant runs.
    si_fired = False
    for s in signals:
        v = cascade(s, protocols, precedents)
        outcome = "pending"
        if v["disposition"] == "auto" and s["type"] in ("lane_adjustment", "rerank"):
            if not si_fired:
                outcome = execute(tier, v, s, apply, retire_authorised=False)
                si_fired = True
            else:
                outcome = "covered by single self-improve --apply"
        else:
            outcome = execute(tier, v, s, apply, retire_authorised=False)
        rec = {"ts": _iso(), "tier": tier, "signal": s, "verdict": v, "outcome": outcome}
        decisions.append(rec)
        # the ledger is the durable audit trail of REAL runs — appended only when the
        # executive is armed, so a dry/observing Censor (every beat) never spams it.
        if apply:
            _append_jsonl(LEDGER_PATH, rec)
    return decisions


def census() -> dict:
    """Counts-only public census; no signal subjects, protocol ids, residual titles, or decisions."""
    protocols = (_load_yaml(PROTOCOLS) or {}).get("protocols", [])
    precedents = _load_jsonl(PRECEDENTS_PATH)
    state = _load_json(STATE_PATH, {"last_run": {}})
    last = _load_json(LAST_PATH, {"decisions": []})
    residuals = _load_json(RESIDUAL_PATH, [])
    return {
        "tiers": len(TIER_SECONDS),
        "protocols": len(protocols) if isinstance(protocols, list) else 0,
        "precedents": len(precedents),
        "state_tiers": len((state or {}).get("last_run") or {}) if isinstance(state, dict) else 0,
        "last_decisions": len(last.get("decisions") or []) if isinstance(last, dict) else 0,
        "residuals": len(residuals) if isinstance(residuals, list) else 0,
        "actuator_timeout_s": ACTUATOR_TIMEOUT,
    }


def main():
    ap = argparse.ArgumentParser(description="The Censor — insights→actions on cadences.")
    ap.add_argument("--apply", action="store_true", help="let the executive act (default: dry report)")
    ap.add_argument("--tier", choices=list(TIER_SECONDS), help="force one tier regardless of cadence")
    ap.add_argument("--all", action="store_true", help="run every tier regardless of cadence")
    ap.add_argument("--census", action="store_true", help="print counts-only public census JSON")
    args = ap.parse_args()
    if args.census:
        print(json.dumps(census(), indent=2, sort_keys=True))
        return 0

    protocols = (_load_yaml(PROTOCOLS) or {}).get("protocols", [])
    precedents = _load_jsonl(PRECEDENTS_PATH)
    state = _load_json(STATE_PATH, {"last_run": {}})
    now = _now()

    tiers = list(TIER_SECONDS) if args.all else due_tiers(state, now, args.tier)
    summary = {"generated": _iso(now), "applied": bool(args.apply), "tiers_run": tiers, "decisions": []}

    for tier in tiers:
        decisions = run_tier(tier, protocols, precedents, args.apply)
        summary["decisions"].extend(decisions)
        if args.apply or args.tier or args.all:
            state.setdefault("last_run", {})[tier] = _iso(now)

    if args.apply:
        _atomic_write(STATE_PATH, json.dumps(state, indent=2))
    _atomic_write(LAST_PATH, json.dumps(summary, indent=2))

    by_disp = {}
    for d in summary["decisions"]:
        by_disp[d["verdict"]["disposition"]] = by_disp.get(d["verdict"]["disposition"], 0) + 1
    disp_str = ", ".join(f"{n} {k}" for k, n in sorted(by_disp.items())) or "no signals"
    print(f"censor: tiers={tiers or 'none-due'} · {len(summary['decisions'])} decisions ({disp_str})"
          f" · {'APPLIED' if args.apply else 'dry-run'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
