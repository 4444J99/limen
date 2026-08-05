#!/usr/bin/env python3
"""organ-health.py — PROPRIOCEPTION: the organism feels whether its own organs are firing.

The self-* ladder is asserted from code ("all rungs wired and live") but, until now, nothing
SHOWED whether each rung actually fires on cadence. A liveness belief that the logs can quietly
contradict is not autonomic — it's faith. This organ closes that gap: for every rung
(SUSTAIN · ROUTE · FEED · MERGE · HEAL · IMPROVE · PRESERVE · CONVERGE · MAIL) it derives the
LAST time the organ fired and marks it green / stale / down / gated against its OWN cadence.

Two signal sources, in priority order:
  1. logs/.voice/<voice>   — a stamp the heartbeat writes the instant a voice plays (ground truth).
  2. an artifact the organ produces (mtime or embedded timestamp) — works TODAY, before stamping
     lands in the live loop.

Derive, never pin: the door-list itself, the cadences (C_*), and the adaptive tempo (LOOP_MIN/MAX)
are all PARSED out of heartbeat-loop.sh — membership is the heartbeat's, never a hand-roster, so a
beat added or removed upstream is FELT, not silently missed (the door-discovery CONTRACT is shared
with AVTOPOIESIS via spec/avtopoiesis/canon.yaml). _registry() only ENRICHES discovered beats with
their signal specifics. Gate flags are read from ~/.limen.env so a gated-OFF organ reads "gated"
(intentional), never a false "down".

Anti-waste + never-"NO": read-only on the fleet's data; writes only its own logs/organ-health.json
and the self-contained organ-health.html face. Every probe fails OPEN — a missing artifact yields
"unknown", never a crash, and never blocks the beat.
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
LOGS = ROOT / "logs"
VOICED = LOGS / ".voice"
LOOP_SH = ROOT / "scripts" / "heartbeat-loop.sh"
ENV_FILE = Path(os.environ.get("LIMEN_ENV_FILE", Path.home() / ".limen.env"))
OUT_DIRS = [ROOT / "web" / "app" / "out", ROOT / "web" / "app" / "public"]
CANON = ROOT / "spec" / "avtopoiesis" / "canon.yaml"  # the SINGLE door-discovery contract (shared with AVTOPOIESIS)
SENSORS = ROOT / "institutio" / "governance" / "sensors.yaml"
LEDGER = Path(os.environ.get("LIMEN_OBLIGATIONS_LEDGER", ROOT / "obligations-ledger.json"))  # mail capability signal

try:
    import yaml
except ImportError:  # fail-open: proprioception must never crash on a missing dep
    yaml = None

_TS_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})")


# ── derive cadences + tempo from the loop itself (never pin) ──────────────────────────────────
def _loop_text():
    try:
        return LOOP_SH.read_text()
    except OSError:
        return ""


def _parse_cadences(text):
    """C_NAME="${LIMEN_BEAT_NAME:-N}"  →  {"NAME": N}.  Env overrides the parsed default."""
    out = {}
    for name, default in re.findall(r'C_([A-Z_]+)="\$\{LIMEN_BEAT_[A-Z_]+:-(\d+)\}"', text):
        try:
            out[name] = int(os.environ.get(f"LIMEN_BEAT_{name}", default))
        except ValueError:
            continue
    return out


def _parse_tempo(text):
    def grab(var, fallback):
        m = re.search(rf"{var}:-(\d+)", text)
        val = m.group(1) if m else str(fallback)
        try:
            return int(os.environ.get(var, val))
        except ValueError:
            return fallback

    return grab("LIMEN_LOOP_MIN", 120), grab("LIMEN_LOOP_MAX", 1800)


# ── the living door-list: DISCOVERED from the heartbeat, never hand-rostered ───────────────────
# A degraded-mode mirror of spec/avtopoiesis/canon.yaml's discovery patterns. Kept in lockstep with
# the canon by a test — when canon/PyYAML is present the canon wins; this only keeps the organ alive
# if the spec is absent (an older checkout) so proprioception never crashes.
_BEAT_PATTERN_FALLBACK = r'C_([A-Z][A-Z_]*)="\$\{LIMEN_BEAT_\1:-([0-9]+)\}"(?:[^#\n]*#\s*([^\n]*))?'
_GATE_PATTERN_FALLBACK = r'\[\s*"\$\{LIMEN_%s:-0\}"\s*=\s*"1"\s*\]'


def _discovery_contract():
    """The (beat_pattern, gate_pattern) used to read the heartbeat — sourced from
    spec/avtopoiesis/canon.yaml so organ-health and AVTOPOIESIS share ONE contract (derive, never
    pin). Fail-open to the mirrored inline patterns above."""
    if yaml is not None:
        try:
            disc = (yaml.safe_load(CANON.read_text()) or {}).get("discovery") or {}
            return (
                disc.get("beat_pattern") or _BEAT_PATTERN_FALLBACK,
                disc.get("gate_pattern") or _GATE_PATTERN_FALLBACK,
            )
        except OSError:
            pass
    return _BEAT_PATTERN_FALLBACK, _GATE_PATTERN_FALLBACK


def _discover_doors(text):
    """Every C_<NAME> beat the heartbeat declares is a door. MEMBERSHIP lives here, in the loop —
    never in a hand-roster — so a beat can be neither silently missed (added upstream) nor silently
    kept (removed upstream). A beat the loop gates OFF by default reads dormant."""
    beat_pat, gate_pat = _discovery_contract()
    out, seen = [], set()
    for name, cadence, role in re.findall(beat_pat, text):
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        dormant = bool("%s" in gate_pat and re.search(gate_pat % name, text))
        out.append({"key": key, "name": name, "cadence": int(cadence), "role": role.strip(), "dormant": dormant})
    # Scheduled sensors are doors too. Membership remains derived from the live loop: registry
    # entries join only when the loop contains the generic scheduled runner. Sensor identity,
    # cadence, gate, and title all come from data, so renamed ids require no consumer edit.
    if re.search(r"beat-sensors\.py[^\n]*--source\s+heartbeat[^\n]*--scheduled-only", text):
        try:
            sensors = (yaml.safe_load(SENSORS.read_text()) or {}).get("sensors") or {}
        except (OSError, ValueError, AttributeError):
            sensors = {}
        derive_match = re.search(r"LIMEN_BEAT_DERIVE:-(\d+)", text)
        derive_default = derive_match.group(1) if derive_match else "0"
        derive_live = _env_flag("LIMEN_BEAT_DERIVE", derive_default) == "1"
        for sensor_id, sensor in sensors.items():
            if sensor_id in seen or "heartbeat" not in (sensor.get("source") or []):
                continue
            cadence_spec = sensor.get("cadence")
            if cadence_spec is None:
                continue
            if isinstance(cadence_spec, dict):
                cadence_value = os.environ.get(str(cadence_spec.get("env") or ""), str(cadence_spec.get("default", "")))
                cadence_default = cadence_spec.get("default")
            else:
                cadence_value = cadence_spec
                cadence_default = cadence_spec
            try:
                cadence = int(cadence_value)
            except (TypeError, ValueError):
                try:
                    cadence = int(cadence_default)
                except (TypeError, ValueError):
                    continue
            if cadence <= 0:
                continue
            gate = sensor.get("gate")
            gate_default = str(sensor.get("default", "1"))
            sensor_gate_dormant = bool(gate and gate_default == "0")
            seen.add(sensor_id)
            out.append(
                {
                    "key": sensor_id,
                    "name": sensor_id.upper().replace("-", "_").replace(".", "_"),
                    "cadence": cadence,
                    "role": str(sensor.get("title") or f"{sensor_id} sensor"),
                    "dormant": (not derive_live) or sensor_gate_dormant,
                    "registry_sensor": True,
                    "gate": gate,
                    "gate_default": gate_default,
                    "bound_lever": (
                        "LIMEN_BEAT_DERIVE=1" if not derive_live else (f"{gate}=1" if sensor_gate_dormant else None)
                    ),
                }
            )
    return out


def _env_flag(name, default=""):
    """Read a gate flag from the live env, falling back to ~/.limen.env, then default. Read-only."""
    if name in os.environ:
        return os.environ[name]
    try:
        for ln in ENV_FILE.read_text().splitlines():
            ln = ln.strip()
            if ln.startswith(f"{name}=") or ln.startswith(f"export {name}="):
                return ln.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def _mail_capability():
    """Is the Gmail WRITE/archive capability actually LIVE? An HONEST capability signal, not a dead
    env ref: the app-password credential is materialized (GMAIL_APP_PASSWORD present), OR the
    obligations ledger shows a real archive already fired (any account.archived > 0). Returns
    (live, bound_lever) — when not live, the bound human lever that opens it (the bulk archive stays
    a hand-pull, so an un-live capability reads 'gated' with its lever, never forced green)."""
    if _env_flag("GMAIL_APP_PASSWORD", "").strip():
        return True, None
    try:
        led = json.loads(LEDGER.read_text())
        accounts = led.get("accounts") if isinstance(led, dict) else None
        if isinstance(accounts, list) and any((a or {}).get("archived", 0) for a in accounts):
            return True, None
    except (OSError, ValueError):
        pass
    return False, "L-IMAP-APP-PW"


def _is_hold(o):
    """When a rung reads 'gated', is that an INTENDED hold (owner's off-by-design knob) or a
    RESIDUAL gap (a capability that should be live but a lever blocks it, or a default-ON safety
    organ that got dark-disabled)? True ⟺ intended hold — so a deliberate HOLD is never mistaken
    for a broken probe. Explicit `hold` wins; else derive: dormant/off-by-default = hold, while a
    gate whose default is ON ("1") that is nonetheless gated is a dark-disable, i.e. NOT a hold."""
    if "hold" in o:
        return bool(o["hold"])
    if o.get("_dormant"):
        return True
    return o.get("gate_default", "") != "1"


# ── signal probes ─────────────────────────────────────────────────────────────────────────────
def _mtime(path):
    try:
        return Path(path).stat().st_mtime
    except OSError:
        return None


def _voice_stamp(voice):
    """Ground-truth last-fire from logs/.voice/<voice> (mtime; content is the ISO ts but mtime
    is enough and avoids parse cost)."""
    return _mtime(VOICED / voice)


def _last_log_ts(path):
    """Newest 'YYYY-MM-DD HH:MM:SS' found in a log file → epoch (local). Fail-open to None."""
    try:
        text = Path(path).read_text()
    except OSError:
        return None
    best = None
    for m in _TS_RE.findall(text):
        try:
            when = datetime.strptime(m.replace("T", " "), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
        if best is None or when > best:
            best = when
    return best


def _json_field_ts(path, *fields):
    """Epoch from the first present ISO/'%Y-%m-%d %H:%M:%S' field in a json file."""
    try:
        obj = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(obj, dict):
        return None
    for f in fields:
        v = obj.get(f)
        if not isinstance(v, str):
            continue
        m = _TS_RE.search(v)
        if not m:
            continue
        try:
            return datetime.strptime(m.group(1).replace("T", " "), "%Y-%m-%d %H:%M:%S").timestamp()
        except ValueError:
            continue
    return None


# ── the enrichment table ──────────────────────────────────────────────────────────────────────
# NOT the door-list (that is DISCOVERED from the heartbeat — see _doors). This only ENRICHES a
# discovered beat with the signal specifics the loop can't express: which VOICE stamps it, which
# artifact probe proves a fire until stamping is live, how it's gated, and a one-line "what". The
# few rungs with NO cadence_key (sustain/merge/improve) are conceptual — they ride the base tick or
# a wall-clock producer rather than their own C_ beat — and are carried through as first-class rungs.
def _registry():
    return [
        dict(
            key="sustain",
            rung="SUSTAIN",
            voice="tick",
            cadence_beats=1,
            what="heartbeat daemon — the base tempo every voice rides on",
            probe=lambda: _mtime(LOGS / "ticks.jsonl"),
        ),
        dict(
            key="route",
            rung="ROUTE",
            voice="balance",
            cadence_key="BALANCE",
            what="capacity-aware routing across the lanes",
            probe=lambda: _mtime(LOGS / "route-health.json"),
        ),  # route.py stamps this every balance beat
        dict(
            key="feed",
            rung="FEED",
            voice="feed",
            cadence_key="FEED",
            what="mine + generate backlog (revenue-first)",
            probe=lambda: _mtime(LOGS / "feed-health.json"),
        ),  # generate-backlog.py stamps this every feed beat
        dict(
            key="merge",
            rung="MERGE",
            voice="merge",
            cadence_key="DRAIN",
            claim_cadence=False,
            gate_note="merge-drain runs inside the drain voice; merges remain policy-gated",
            what="merge-ready assessment; CLEAN PRs ship",
            probe=lambda: _last_log_ts(LOGS / "merge-drain.log"),
        ),
        dict(
            key="heal",
            rung="HEAL",
            voice="heal",
            cadence_key="HEAL",
            what="repair CI-red/conflict PRs; reconcile phantom dispatches",
            probe=lambda: _mtime(LOGS / "dispatch-verify.json"),
        ),
        dict(
            key="improve",
            rung="IMPROVE",
            voice="improve",
            interval_s=10 * 3600,
            what="learn lane productivity → routing weights (producer)",
            probe=lambda: (
                _json_field_ts(LOGS / "self-improve-proposal.json", "generated_at", "timestamp")
                or _mtime(LOGS / "self-improve-proposal.json")
            ),
        ),
        dict(
            key="preserve",
            rung="PRESERVE",
            voice="backup",
            cadence_key="BACKUP",
            what="copy irreplaceable → Archive4T; reclaim regenerable caches",
            probe=lambda: _mtime(LOGS / "library-levers.json") or _mtime(LOGS / "capture-log.jsonl"),
        ),
        dict(
            key="converge",
            rung="CONVERGE",
            voice="corpus",
            cadence_key="CORPUS",
            gate="LIMEN_CORPUS_CONVERGE",
            gate_default="0",
            hold=True,
            bound_lever="LIMEN_CORPUS_CONVERGE=1",
            what="distill his words toward THE ONE (the 'back again')",
            probe=lambda: _mtime(LOGS / "corpus-converge-state.json"),
        ),
        # MAIL: gate on a REAL capability signal (app-password materialized OR ledger shows a real
        # archive), NOT the superseded GMAIL_OAUTH_OP_REF env ref (nobody set it → could never go
        # green). The organ sweeps + rebuilds the ledger keylessly every beat, so with the capability
        # live it is judged on its (fresh) voice-stamp; without it, the bulk archive is a hand-lever,
        # so it reads 'gated' with that lever (residual, not an intended hold), never forced green.
        dict(
            key="mail",
            rung="MAIL",
            voice="mail",
            cadence_key="MAIL",
            capability=_mail_capability,
            hold=False,
            what="sweep inbound (flag/archive) + rebuild obligations ledger",
            probe=lambda: _mtime(LOGS / "obligations-view.json"),
        ),
        dict(
            key="vigilia",
            rung="VIGILIA",
            voice="vigilia",
            cadence_beats=1,
            gate="LIMEN_VIGILIA",
            gate_default="1",
            what="autonomic self-keeping: VITALS (don't crash) · CONTINUITY (don't forget) · INTEGRITY (don't corrupt)",
            probe=lambda: _json_field_ts(LOGS / "vigilia" / "status.json", "ts"),
        ),
        dict(
            key="nomenclator",
            rung="NOMENCLATOR",
            voice="nomenclator",
            cadence_key="NOMENCLATOR",
            gate="LIMEN_NOMENCLATOR",
            gate_default="0",
            hold=True,
            bound_lever="LIMEN_NOMENCLATOR=1",
            what="INDEX·NOMINVM — hold the roll of names to the canon (nota)",
            probe=lambda: _mtime(LOGS / "nomenclator.json"),
        ),
        dict(
            key="evocator",
            rung="EVOCATOR",
            voice="evocator",
            cadence_key="EVOCATOR",
            what="the summoner — keep canonical truths present in every channel (FLAME/corpus/memory)",
            probe=lambda: _mtime(LOGS / "evocator.json"),
        ),
        dict(
            key="positioning",
            rung="POSITIONING",
            voice="positioning",
            cadence_key="POSITIONING",
            gate="LIMEN_POSITIONING",
            gate_default="0",
            hold=True,
            bound_lever="L-POSITIONING-ACTIVATE",
            what="refresh inbound-magnet surfaces (form/operation pages + front door + discoverability)",
            probe=lambda: _mtime(ROOT / "docs" / "positioning" / "_frontdoor.md"),
        ),
        dict(
            key="health",
            rung="HEALTH",
            voice="health",
            cadence_key="HEALTH",
            what="personal health office — chart digest + visit-prep + chase open clinical loops (PII local)",
            probe=lambda: _mtime(LOGS / "health-organ-state.json"),
        ),
        dict(
            key="life",
            rung="LIFE",
            voice="life",
            cadence_key="LIFE",
            what="digital-life office — accounts/assets + subscription purge clock (PII local)",
            probe=lambda: _mtime(LOGS / "life-organ-state.json"),
        ),
        dict(
            key="governance",
            rung="GOVERNANCE",
            voice="governance",
            cadence_key="GOVERNANCE",
            gate="LIMEN_GOVERNANCE",
            gate_default="1",
            what="cursus honorum validator + governance standing; aerarium office",
            probe=lambda: _mtime(LOGS / "governance-organ-state.json"),
        ),
        dict(
            key="pubpolicy",
            rung="PUBPOLICY",
            voice="pubpolicy",
            cadence_key="PUBPOLICY",
            gate="LIMEN_PUBPOLICY",
            gate_default="1",
            what="content-disposition engine: (repo visibility x content class) -> one disposition; owner-scoped redactor",
            probe=lambda: _mtime(LOGS / "publication-policy-state.json"),
        ),
        dict(
            key="cvstos",
            rung="CVSTOS",
            voice="cvstos",
            cadence_key="CVSTOS",
            gate="LIMEN_CVSTOS",
            gate_default="1",
            what="keeper of the host — chat-app/local debt census + factory invariant (nothing truly on PATH/local) + reaper proprioception",
            probe=lambda: _mtime(LOGS / "cvstos-organ-state.json"),
        ),
        dict(
            key="vvltvs",
            rung="VVLTVS",
            voice="vvltvs",
            cadence_key="VVLTVS",
            gate="LIMEN_VVLTVS",
            gate_default="1",
            what="the countenance — verify the public face reflects the live SSOT (profile/portfolio drift) + the contribution-mix radar (the review-% tell)",
            probe=lambda: _mtime(LOGS / "vvltvs-organ-state.json"),
        ),
        # no cadence_key: an always-on pre-lock preflight (like heal-board), not a due_voice beat —
        # so it claims no cadence and never trips the absent-from-heartbeat drift check; green when
        # its per-beat state stamp is fresh.
        dict(
            key="tabularius",
            rung="TABVLARIVS",
            voice="tabularius",
            gate="LIMEN_TABVLARIVS",
            gate_default="1",
            what="the conduct relay — submit the lock-free ticket inbox to the authenticated remote keeper and archive only acknowledged projection receipts",
            probe=lambda: _mtime(LOGS / "tabularius-organ-state.json"),
        ),
        # no cadence_key: runs as a metabolize.sh pre-beat check (section 0h), not a
        # timed heartbeat voice — so it claims no cadence and never trips the absent-
        # from-heartbeat drift check; green when its per-beat artifact is fresh.
        dict(
            key="continuity",
            rung="CONTINUITY",
            voice="continuity",
            what="per-lane dispatch continuity (no silent lane while queue+budget exist)",
            probe=lambda: _json_field_ts(LOGS / "dispatch-continuity.json", "generated"),
        ),
        # no cadence_key: routine-freshness-audit runs inside metabolize.sh step 0e (not a standalone
        # heartbeat voice), so it claims no cadence and never trips the absent-from-heartbeat drift
        # check; green when its per-beat state stamp (logs/routine-freshness.json) is fresh.
        dict(
            key="routines",
            rung="ROUTINES",
            voice="routines",
            gate="LIMEN_ROUTINE_FRESHNESS",
            gate_default="1",
            what="cloud-routine delivery freshness (13 routines; firing must equal delivering)",
            probe=lambda: _json_field_ts(LOGS / "routine-freshness.json", "generated"),
        ),
        # no cadence_key: session-walk-census runs inside metabolize.sh step 0j; green when its
        # per-beat census stamp is fresh.
        dict(
            key="session-walk",
            rung="SESSION_WALK",
            voice="session-walk",
            gate="LIMEN_SESSION_WALK",
            gate_default="1",
            what="full-horizon walk census of BOTH vendor session estates (residue self-drains)",
            probe=lambda: _json_field_ts(LOGS / "session-walk-census.json", "generated"),
        ),
    ]


def _doors(text):
    """The fused door-list (no I/O). The curated self-* ladder rungs come FIRST — each cross-checked
    against the heartbeat so a beat it names but the loop no longer declares is flagged as drift, not
    silently kept. Then every OTHER beat the heartbeat declares is appended as a first-class door, so
    a beat added upstream is felt, never silently missed. Membership is the heartbeat's; _registry()
    only enriches it. (Synthetic rungs — sustain/merge/improve — carry no cadence_key and pass through
    untouched.)"""
    discovered = _discover_doors(text)
    by_key = {d["key"]: d for d in discovered}
    rungs, claimed = [], set()
    for o in _registry():
        spec = dict(o)
        bk = (o.get("cadence_key") or "").lower()
        if bk:
            if spec.get("claim_cadence", True):
                claimed.add(bk)
            if bk not in by_key:
                spec["_absent"] = True
                spec["gate_note"] = "beat absent from heartbeat — drift"
            elif by_key[bk].get("dormant"):
                spec["_dormant"] = True
        rungs.append(spec)
    for d in discovered:
        if d["key"] in claimed:
            continue
        rungs.append(
            dict(
                key=d["key"],
                rung=d["name"],
                voice=d["key"],
                cadence_key=None if d.get("registry_sensor") else d["name"],
                cadence_beats=d["cadence"] if d.get("registry_sensor") else None,
                what=d["role"] or f"{d['key']} beat",
                probe=lambda: None,
                _dormant=bool(d.get("dormant")),
                gate=d.get("gate"),
                gate_default=d.get("gate_default"),
                # a beat the heartbeat gates OFF by default (e.g. AVTOPOIESIS) is an INTENDED hold whose
                # bound lever is its own knob — surfaced so a deliberate HOLD never reads as a broken probe
                bound_lever=d.get("bound_lever") or (f"LIMEN_{d['name']}=1" if d.get("dormant") else None),
                hold=bool(d.get("dormant")),
                gate_note="gated OFF by default" if d.get("dormant") else "",
            )
        )
    return rungs


def build():
    text = _loop_text()
    cadences = _parse_cadences(text)
    loop_min, loop_max = _parse_tempo(text)

    organs = []
    drift = []
    for o in _doors(text):
        # cadence → expected seconds between fires, worst-case (idle beats run at LOOP_MAX).
        if "interval_s" in o:
            expected = o["interval_s"]
            cadence_desc = f"~{o['interval_s'] // 3600}h"
        else:
            beats = o.get("cadence_beats") or cadences.get(o.get("cadence_key", ""), 0) or 1
            expected = beats * loop_max
            cadence_desc = "every beat" if beats == 1 else f"every {beats} beats"

        # gate state — a real CAPABILITY probe, an explicit env-flag gate, or a beat the heartbeat
        # itself gates OFF by default. bound_lever + hold_vs_residual travel WITH the gate so a
        # deliberate HOLD is never read as a broken probe, and a residual names the lever that opens it.
        gated, bound_lever, hold_vs_residual = False, o.get("bound_lever"), None
        if o.get("capability"):
            live, lever = o["capability"]()
            gated = not live
            if gated:
                bound_lever = lever or bound_lever
        elif o.get("_dormant"):
            gated = True
        elif o.get("gate"):
            val = _env_flag(o["gate"], o.get("gate_default", ""))
            gated = (val == "") if o.get("gate_truthy_nonempty") else (val != "1")
        if gated:
            hold_vs_residual = _is_hold(o)
            if not bound_lever and o.get("gate"):  # default re-enable lever = flip the knob on
                bound_lever = f"{o['gate']}=1"

        # SELF-PROTECTING INVARIANT: a gate whose DEPLOYED value disagrees with its declared
        # gate_default is drift — and a default-ON safety organ flipped OFF is a dark-disable (exactly
        # how VIGILIA sat dark for 2.5 days). Flag every such organ; --strict makes a dark-disable fatal.
        gd = o.get("gate_default")
        if o.get("gate") and gd is not None:
            deployed = _env_flag(o["gate"], gd)
            if deployed != gd:
                drift.append(
                    {
                        "key": o["key"],
                        "rung": o["rung"],
                        "gate": o["gate"],
                        "gate_default": gd,
                        "deployed": deployed,
                        "dark_disabled": (gd == "1" and deployed != "1"),
                    }
                )

        # best signal: voice-stamp (ground truth) else artifact probe
        src = "voice-stamp"
        ts = _voice_stamp(o["voice"])
        if ts is None:
            ts = o["probe"]()
            src = "artifact"
        if ts is None:
            src = "none"

        now = time.time()
        age = (now - ts) if ts else None

        if gated:
            status = "gated"
        elif age is None:
            status = "unknown"
        elif age <= expected * 1.5:
            status = "green"
        elif age <= expected * 4:
            status = "stale"
        else:
            status = "down"
        if o.get("_absent"):  # ladder names a beat the heartbeat no longer declares → loud, not silent
            status = "down"

        note = o.get("gate_note", "")
        if gated:  # make the tick honest: name the KIND of gate + its bound lever
            kind = "intended HOLD" if hold_vs_residual else "residual (capability)"
            bits = [kind] + ([f"lever {bound_lever}"] if bound_lever else []) + ([note] if note else [])
            note = " · ".join(bits)

        organs.append(
            {
                "key": o["key"],
                "rung": o["rung"],
                "what": o["what"],
                "voice": o["voice"],
                "cadence": cadence_desc,
                "status": status,
                "source": src,
                "last_fired": datetime.fromtimestamp(ts).isoformat(timespec="seconds") if ts else None,
                "age_h": round(age / 3600, 1) if age is not None else None,
                "expected_h": round(expected / 3600, 1),
                "note": note,
                "bound_lever": bound_lever if gated else None,
                "hold_vs_residual": hold_vs_residual,
            }
        )

    counts = {}
    for o in organs:
        counts[o["status"]] = counts.get(o["status"], 0) + 1
    rungs_live = sum(1 for o in organs if o["status"] in ("green", "gated"))
    dark = [d for d in drift if d["dark_disabled"]]
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "tempo": {"min_s": loop_min, "max_s": loop_max},
        "summary": {"total": len(organs), "live": rungs_live, **counts},
        # self-protecting invariant: deployed gate values that diverge from their safe default
        "gate_integrity": {"drift": drift, "dark_disabled": dark, "ok": not dark},
        "organs": organs,
    }


_DOT = {"green": "#2ecc71", "stale": "#f1c40f", "down": "#e74c3c", "gated": "#8a93a6", "unknown": "#6e7681"}
_LABEL = {"green": "live", "stale": "stale", "down": "DOWN", "gated": "gated (intentional)", "unknown": "no signal yet"}


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_html(v):
    rows = []
    for o in v["organs"]:
        color = _DOT.get(o["status"], "#555")
        age = f"{o['age_h']}h ago" if o["age_h"] is not None else "—"
        last = o["last_fired"] or "never observed"
        src = "" if o["source"] == "voice-stamp" else f' <span class="src">({o["source"]})</span>'
        note = f' · <span class="note">{_esc(o["note"])}</span>' if o["note"] else ""
        rows.append(f"""
        <tr>
          <td><span class="dot" style="background:{color}"></span><b>{_esc(o["rung"])}</b>
              <div class="what">{_esc(o["what"])}</div></td>
          <td class="cad">{_esc(o["cadence"])}{note}</td>
          <td class="age">{_esc(age)}<div class="last">{_esc(last)}{src}</div></td>
          <td><span class="badge" style="background:{color}">{_esc(_LABEL.get(o["status"], o["status"]))}</span></td>
        </tr>""")

    s = v["summary"]
    headline = f"{s.get('live', 0)}/{s.get('total', 0)} rungs live"
    sub_bits = [f"{n}: {s[n]}" for n in ("green", "gated", "stale", "down", "unknown") if s.get(n)]
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="refresh" content="30"><title>LIMEN — organ health</title>
<style>
 :root{{color-scheme:dark}}
 body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}}
 .wrap{{max-width:820px;margin:0 auto;padding:18px}}
 h1{{font-size:20px;margin:0 0 2px}} .sub{{color:#8a93a6;font-size:13px;margin-bottom:14px}}
 .card{{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:6px 16px;margin:12px 0}}
 .big{{font-size:26px;font-weight:700;margin:6px 0}}
 table{{width:100%;border-collapse:collapse}} td{{padding:11px 6px;border-top:1px solid #21262d;vertical-align:top}}
 tr:first-child td{{border-top:none}}
 .dot{{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:7px;vertical-align:middle}}
 .what{{color:#8a93a6;font-size:12px;margin:2px 0 0 18px}}
 .cad{{color:#c9d1d9;font-size:13px}} .note{{color:#8a93a6;font-size:12px}}
 .age{{font-size:13px}} .last{{color:#6e7681;font-size:11px}} .src{{color:#8a93a6}}
 .badge{{color:#06140c;font-weight:700;border-radius:5px;padding:2px 8px;font-size:12px}}
</style></head><body><div class="wrap">
 <h1>LIMEN — organ health</h1>
 <div class="sub">proprioception · does each self-* rung actually fire? · updated {_esc(v["generated_at"])} · auto-refresh 30s</div>
 <div class="card"><div class="big">{_esc(headline)}</div>
   <div class="sub" style="margin:0 0 8px">{_esc(" · ".join(sub_bits))}</div></div>
 <div class="card"><table><tbody>{"".join(rows)}</tbody></table></div>
 <div class="sub">green/stale/down derived per-organ against its OWN cadence (worst-case beat = {v["tempo"]["max_s"]}s).
   Ground-truth source is logs/.voice/&lt;voice&gt; once heartbeat voice-stamping is live; until then,
   organs fall back to their output artifact's freshness (shown as "(artifact)").</div>
</div></body></html>"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--help" in argv or "-h" in argv:
        print("usage: organ-health.py [--strict] [--help]")
        print("  Writes logs/organ-health.json + organ-health.html.")
        print("  --strict  exit 1 when a default-ON safety organ is deployed OFF (dark-disabled)")
        return 0
    strict = "--strict" in argv
    view = build()
    LOGS.mkdir(parents=True, exist_ok=True)
    (LOGS / "organ-health.json").write_text(json.dumps(view, indent=2))
    html = render_html(view)
    wrote = []
    for d in OUT_DIRS:
        try:
            d.mkdir(parents=True, exist_ok=True)
            (d / "organ-health.html").write_text(html)
            (d / "organ-health.json").write_text(json.dumps(view, indent=2))
            wrote.append(str(d / "organ-health.html"))
        except OSError:
            continue
    s = view["summary"]
    detail = " ".join(f"{o['rung']}:{o['status']}" for o in view["organs"])
    print(
        f"organ-health: {s.get('live', 0)}/{s.get('total', 0)} live -> "
        f"{', '.join(wrote) or 'logs/organ-health.json only'}\n  {detail}"
    )
    dark = view["gate_integrity"]["dark_disabled"]
    if dark:  # a default-ON safety organ deployed OFF — never let it pass silently
        print(
            "  ⚠ GATE-DRIFT (dark-disabled safety organ): "
            + ", ".join(f"{d['rung']} {d['gate']}={d['deployed']} (default {d['gate_default']})" for d in dark)
        )
    return 1 if (strict and dark) else 0


if __name__ == "__main__":
    raise SystemExit(main())
