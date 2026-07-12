#!/usr/bin/env bash
# omega.test.sh — regression test for scripts/omega.sh (the autonomic fixed-point predicate).
#
# omega.sh is the CONJUNCTION of every gate's --check; its own contract is the tally logic:
#   • a rung that cannot be checked here is SKIP, never a silent PASS (the curl-000 lesson);
#   • exit 0 ⟺ zero FAIL rungs (SKIPs allowed);
#   • --strict exits non-zero on either FAIL or SKIP;
#   • it stamps a versioned, content-addressed logs/omega.json with one row per rung.
# Deterministic: omega.sh derives ROOT from its own path and calls children by "$ROOT/scripts/X",
# so we run a COPY in a temp ROOT stubbed with fake predicates — no live board, handoff, or network.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
real_omega="$here/../omega.sh"
real_watch="$here/../overnight-watch.py"
[ -f "$real_omega" ] || { echo "FAIL: cannot find omega.sh at $real_omega" >&2; exit 1; }
[ -f "$real_watch" ] || { echo "FAIL: cannot find overnight-watch.py at $real_watch" >&2; exit 1; }

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# A stub ROOT: omega.sh + a scripts/ dir of fake predicates whose exit codes we control per case.
mkdir -p "$work/scripts" "$work/cli/src" "$work/logs"
cp "$real_omega" "$work/scripts/omega.sh"

# write_stubs <ask_gate_rc> — all det children exit 0 except ask-gate.py, whose rc is the argument.
# (In --offline the live children are SKIPped without running. Registry-owned checks are discovered
# through a generic stub whose sensor id is intentionally unrelated to its command/label.)
write_stubs() {
  local ask_rc="$1"
  for py in enactment-audit armed-valve-audit handoff-relay; do
    printf '#!/usr/bin/env python3\nimport sys; sys.exit(0)\n' > "$work/scripts/$py.py"
    chmod +x "$work/scripts/$py.py"
  done
  printf '#!/usr/bin/env python3\nimport sys; sys.exit(%s)\n' "$ask_rc" > "$work/scripts/ask-gate.py"
  chmod +x "$work/scripts/ask-gate.py"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$work/scripts/no-tasks-on-me.sh"
  chmod +x "$work/scripts/no-tasks-on-me.sh"
  cat > "$work/scripts/beat-sensors.py" <<'PY'
#!/usr/bin/env python3
import sys
import os
if "--list-omega" in sys.argv:
    rows = [
        "arbitrary.future.id\t0\tdet\tarbitrary registry parity\tpython3 scripts/future.py --check\t30",
        "arbitrary.future.id\t1\tlive\tarbitrary registry posture\tpython3 scripts/future.py --live\t45",
    ]
    mode = os.environ.get("OMEGA_TEST_SENSOR_MODE")
    if mode == "reverse":
        rows.reverse()
    elif mode == "added":
        rows.append("new.sensor.id\t0\tdet\tnew registry contract\tpython3 scripts/new.py\t60")
    elif mode == "command":
        rows[0] = "arbitrary.future.id\t0\tdet\tarbitrary registry parity\tpython3 scripts/renamed.py --check\t30"
    print("\n".join(rows))
    raise SystemExit(0)
if "--run-omega" in sys.argv:
    raise SystemExit(0)
raise SystemExit(2)
PY
  chmod +x "$work/scripts/beat-sensors.py"
}

pass=0; fail=0
check() { if [ "$1" = "$2" ]; then pass=$((pass+1)); else echo "  MISMATCH ($3): want '$2' got '$1'"; fail=$((fail+1)); fi; }

# ── Case 1: every det child green → OMEGA HOLDS, exit 0 ──────────────────────────
write_stubs 0
set +e
out="$(bash "$work/scripts/omega.sh" --offline --quiet 2>&1)"; rc=$?
set -e
check "$rc" "0" "case1 exit"
echo "$out" | grep -q "OMEGA HOLDS" && check "holds" "holds" "case1 verdict" || check "missing" "holds" "case1 verdict"
python3 - "$work/logs/omega.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["schema_version"] == 1, d
assert d["generated_at"] == d["generated"], d
assert len(d["contract_hash"]) == 64, d
assert d["verdict"] == "HOLDS", d["verdict"]
assert d["strict"] is False, d
assert d["fail"] == 0, d
assert all({"rung", "tier", "status"} <= set(r) for r in d["rungs"]), "rung shape"
# every live rung must be SKIP in offline mode (never a silent PASS)
live = [r for r in d["rungs"] if r["tier"] == "live"]
assert live and all(r["status"] == "SKIP" for r in live), [r["status"] for r in live]
rows = {r["rung"]: r for r in d["rungs"]}
assert rows["ask-lineage convergence"]["status"] == "SKIP", rows
assert rows["arbitrary registry parity"]["status"] == "PASS", rows
assert rows["arbitrary registry posture"]["status"] == "SKIP", rows
print("  case1 stamp OK")
PY
base_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_hash"])' "$work/logs/omega.json")"

# ── Case 1b: normalized contract identity ignores row order, but changes on a new rung ────────────
OMEGA_TEST_SENSOR_MODE=reverse bash "$work/scripts/omega.sh" --offline --quiet >/dev/null
reverse_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_hash"])' "$work/logs/omega.json")"
check "$reverse_hash" "$base_hash" "case1b normalized sensor order"
OMEGA_TEST_SENSOR_MODE=added bash "$work/scripts/omega.sh" --offline --quiet >/dev/null
added_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_hash"])' "$work/logs/omega.json")"
if [ "$added_hash" != "$base_hash" ]; then
  check "changed" "changed" "case1b added sensor changes hash"
else
  check "unchanged" "changed" "case1b added sensor changes hash"
fi
OMEGA_TEST_SENSOR_MODE=command bash "$work/scripts/omega.sh" --offline --quiet >/dev/null
command_hash="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["contract_hash"])' "$work/logs/omega.json")"
if [ "$command_hash" != "$base_hash" ]; then
  check "changed" "changed" "case1b command changes hash"
else
  check "unchanged" "changed" "case1b command changes hash"
fi

# ── Case 1c: strict rejects the same otherwise-green offline run because live rungs SKIP ──────────
set +e
out="$(bash "$work/scripts/omega.sh" --offline --strict --quiet 2>&1)"; rc=$?
set -e
check "$rc" "1" "case1c strict exit"
echo "$out" | grep -q "OMEGA INCOMPLETE" && check "incomplete" "incomplete" "case1c verdict" || check "missing" "incomplete" "case1c verdict"
python3 - "$work/logs/omega.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["strict"] is True and d["verdict"] == "INCOMPLETE" and d["skip"] > 0, d
print("  case1c strict stamp OK")
PY

# ── Case 2: one det child red → OMEGA BROKEN, exit 1 ─────────────────────────────
write_stubs 1
set +e
out="$(bash "$work/scripts/omega.sh" --offline --quiet 2>&1)"; rc=$?
set -e
check "$rc" "1" "case2 exit"
echo "$out" | grep -q "OMEGA BROKEN" && check "broken" "broken" "case2 verdict" || check "missing" "broken" "case2 verdict"
python3 - "$work/logs/omega.json" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["verdict"] == "BROKEN" and d["fail"] >= 1, d
print("  case2 stamp OK")
PY

# ── Case 3: overnight-trial receipt is content-addressed, not a bare pass boolean ────────────────
cp "$real_watch" "$work/scripts/overnight-watch.py"
LIMEN_ROOT="$work" python3 - "$work/scripts/overnight-watch.py" <<'PY'
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

script = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("omega_watch_fixture", script)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
start = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
clock = [start]
module.utc_now = lambda: clock[0]
module.time.monotonic_ns = lambda: 10_000_000_000_000 + int((clock[0] - start).total_seconds() * 1_000_000_000)
module._anchor_created_ns = lambda _path: int(start.timestamp() * 1_000_000_000)
module._observation_custody_created_ns = lambda path: int(
    module.parse_iso(json.loads(path.read_text())["observed_at"]).timestamp() * 1_000_000_000
)
module.evaluator_hash = lambda: "e" * 64
module._cursor_digest = lambda cursor: module.canonical_hash(cursor)
module._cursor_semantic = lambda cursor: cursor
module.handoff_relay_snapshot = lambda **_kwargs: {"ok": True, "check_returncode": 0}
module._prove_terminal_event = lambda entry: {
    "event_id": entry["event_id"], "proof_hash": module.canonical_hash(entry)
}
module._prove_session_event = lambda entry, **_kwargs: {
    "event_id": entry["event_id"], "provider": "jules", "proof_hash": module.canonical_hash(entry)
}
module.TASKS_PATH.write_text(json.dumps({"version": 1, "tasks": []}))
(module.LOGS / "async-runs").mkdir(parents=True, exist_ok=True)
(module.LOGS / "handoff.json").write_text('{"fresh":true}\n')

def signature(path):
    stat = path.stat()
    return {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns, "mode": stat.st_mode & 0o777}

def write_prompt(at):
    source = module.PROMPT_ATOM_SNAPSHOT
    source.parent.mkdir(parents=True, exist_ok=True)
    events = source.parent / "prompt-events.jsonl"
    outcomes = source.parent / "prompt-atom-outcomes.jsonl"
    events.touch(exist_ok=True)
    outcomes.touch(exist_ok=True)
    cursor = {
        "scope": "all", "target_scope": "all", "all_baseline_complete": True,
        "pending_files": 0, "source_errors": [], "unsupported_source_count": 0,
        "unresolved_unit_count": 0, "adapter_gaps": [],
        "source_families": {"fixture": {"discovered": 1, "converged": 1, "pending": 0,
                                                   "errors": 0, "unsupported": 0}},
        "last_scan_at": at.isoformat(timespec="seconds"),
    }
    cursor_path = source.parent / "source-cursor.json"
    cursor_path.write_text(json.dumps(cursor, sort_keys=True))
    snapshot = {
        "source_cursor_digest": module._cursor_digest(cursor), "source_scope": cursor,
        "coverage": {"operator_occurrences": 0}, "validation": {"ok": True},
        "journal_signatures": {"events": signature(events), "outcomes": signature(outcomes),
                               "cursor": signature(cursor_path)},
    }
    source.write_text(json.dumps(snapshot, sort_keys=True))

def append_task(at, index, status, agent="codex", session_id=None):
    board = json.loads(module.TASKS_PATH.read_text())
    board["tasks"].append({
        "id": f"TRIAL-{index}", "status": status, "target_agent": agent,
        "predicate": "python3 -c 'raise SystemExit(0)'",
        "receipt_target": f"git:organvm/limen:docs/r-{index}.json",
        "dispatch_log": [{"timestamp": at.isoformat(timespec="seconds"), "agent": agent,
                          "session_id": session_id or f"s-{index}", "status": status,
                          "output": "verified durable receipt"}],
    })
    module.TASKS_PATH.write_text(json.dumps(board, sort_keys=True))

def sample(at):
    clock[0] = at
    write_prompt(at)
    snapshot = {
        "timestamp": at.isoformat(timespec="seconds"),
        "launchd": {"ok": True, "state": "running", "env": {}}, "log_age_sec": 0,
        "heartbeat": {"latest_tick": {"timestamp": at.isoformat(timespec="seconds")}},
        "worker_count": 0, "heartbeat_child_count": 0, "stale_tick_count": 0,
        "handoff_relay": {"ok": True, "check_returncode": 0},
        "value_gate": {"returncode": 0}, "dispatch_control": {"allow_dispatch": True},
        "plist_drift": [], "throughput": {"below_floor": False},
    }
    module.write_jsonl(snapshot)
    module.append_trial_observation(snapshot)

write_prompt(start)
active, _ = module.start_trial()
for minute in range(5, 481, 5):
    at = start + dt.timedelta(minutes=minute)
    if minute in (60, 150, 240, 330, 420):
        append_task(at, minute, "done")
    if minute == 30:
        append_task(at, 999, "in_progress", "jules", "12345678901234567890")
    sample(at)
clock[0] = start + dt.timedelta(hours=8)
result = module.maybe_finalize_trial()
assert result["receipt"]["pass"] is True, result
PY
set +e
LIMEN_ROOT="$work" python3 - "$work/scripts/overnight-watch.py" >/dev/null 2>&1 <<'PY'
import datetime as dt, importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("omega_watch_check", Path(sys.argv[1]))
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
terminal = json.loads(module.TRIAL_WINDOW_PATH.read_text()); active = terminal["active_marker"]
start = module.parse_iso(active["window_start"]); end = module.parse_iso(active["window_end"])
module.utc_now = lambda: end
module.time.monotonic_ns = lambda: active["monotonic_start_ns"] + module.TRIAL_DURATION_SEC * 1_000_000_000
module._anchor_created_ns = lambda _path: int(start.timestamp() * 1_000_000_000)
module._observation_custody_created_ns = lambda path: int(
    module.parse_iso(json.loads(path.read_text())["observed_at"]).timestamp() * 1_000_000_000
)
module.evaluator_hash = lambda: "e" * 64
module._prove_terminal_event = lambda entry: {
    "event_id": entry["event_id"], "proof_hash": module.canonical_hash(entry)
}
raise SystemExit(0 if module.check_trial_receipt()[0] else 1)
PY
rc=$?
set -e
check "$rc" "0" "case3 content-addressed trial"
python3 - "$work/logs/overnight-trial.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p))
d["input_hash"] = "f" * 64
json.dump(d, open(p, "w"), indent=2, sort_keys=True)
PY
set +e
LIMEN_ROOT="$work" python3 - "$work/scripts/overnight-watch.py" >/dev/null 2>&1 <<'PY'
import importlib.util, json, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("omega_watch_tamper", Path(sys.argv[1]))
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
terminal = json.loads(module.TRIAL_WINDOW_PATH.read_text()); active = terminal["active_marker"]
start = module.parse_iso(active["window_start"]); end = module.parse_iso(active["window_end"])
module.utc_now = lambda: end
module.time.monotonic_ns = lambda: active["monotonic_start_ns"] + module.TRIAL_DURATION_SEC * 1_000_000_000
module._anchor_created_ns = lambda _path: int(start.timestamp() * 1_000_000_000)
module._observation_custody_created_ns = lambda path: int(
    module.parse_iso(json.loads(path.read_text())["observed_at"]).timestamp() * 1_000_000_000
)
module.evaluator_hash = lambda: "e" * 64
module._prove_terminal_event = lambda entry: {
    "event_id": entry["event_id"], "proof_hash": module.canonical_hash(entry)
}
raise SystemExit(0 if module.check_trial_receipt()[0] else 1)
PY
rc=$?
set -e
check "$rc" "1" "case3 tamper rejected"

echo
if [ "$fail" -eq 0 ]; then
  echo "omega.test.sh: PASS ($pass checks)"
else
  echo "omega.test.sh: FAIL ($fail mismatches, $pass ok)"; exit 1
fi
