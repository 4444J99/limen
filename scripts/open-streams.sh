#!/usr/bin/env bash
# open-streams.sh — open every READY session stream, each in its own TTY. One command.
#
# THE DEFECT THIS CLOSES
#   `check-session-streams.py --ready` DERIVES the openable set, but it is a printer: its output is
#   formatted for human eyes, and its only registered consumer (gates.yaml) runs the checker bare as
#   a validator. So the operator's round trip was: exit the session, run --ready, read four blocks,
#   open four terminal tabs, retype four commands. That is precisely the hand-loop the registry
#   exists to abolish, displaced one level up — and worse, until this change the printed command
#   omitted --agent and so opened no agent at all.
#
# WHY tmux AND NOT `cmd &`
#   `limen workstream --agent ...` ENDS IN exec (start-worktree-session.sh:479): it replaces its own
#   process with the agent's kickstart. An interactive agent needs a controlling TTY, so backgrounding
#   it in one shell does not give you N sessions — it gives you N headless jobs with nowhere to type.
#   tmux is the cheapest thing that hands each stream a real TTY, survives the operator closing the
#   laptop, needs no AppleScript/GUI, and is already installed.
#
# CONCURRENCY IS BOUNDED ON PURPOSE
#   Interactive agent sessions are heavy and this estate runs on a 16GB machine with LOGGED jetsam
#   kills; CLAUDE.md caps concurrent heavy processes for exactly that reason. Opening every ready
#   stream at once is the shape that gets killed, and a killed session loses its context silently.
#   The bound is DERIVED from physical RAM (see the helper) rather than being a magic number, is
#   overridable with --max-parallel / $LIMEN_STREAMS_MAX_PARALLEL, and every deferred stream is
#   NAMED with its exact command — a silent cap would read as "all four opened" when it did not.
#
# IDEMPOTENT
#   Re-running opens only what is not already open, on ONE authority: the liveness probe. A stream
#   with a session attached reads `live` and never reaches this script; a dormant stream reaches it
#   and is REOPENED — respawned into its kept tmux window when one survives, a fresh window
#   otherwise. Window presence is NOT the test (a kept window is the closeout display, not a
#   running stream — treating it as one froze every exited lane on SKIP, first live proof
#   2026-07-29).
#
# WHICH LANE OPENS THEM IS THE OPERATOR'S CHOICE, NOT THE REGISTRY'S
#   The registry emits `--agent auto` and may never pin a provider — the capsule contract declares
#   `lane_selection: derive_from_live_capabilities`. `auto` resolves through the live census ordered
#   by $LIMEN_AGENT, so on a stock host census ORDER picks the lane (codex, not claude). `--lane`
#   puts that choice where it belongs: in the environment, for this run only. Vendor-neutrality
#   stays in declared data; the operator still gets to say who opens the work.
#
# THE DEFAULT FAMILY IS THE OPERATOR'S LIFE/WORK DOMAINS
#   Rows carry `family: domain` (derived from the workstream channel roster — the operator's
#   life/work domains: correspondence, financial, representation, …, the streams he actually
#   means; 2026-07-30 correction), `family: constellation` (the collaborator person-streams —
#   the consulting domain's interior), or `family: governance` (hand-authored estate work).
#   "Open my streams" must never answer with plumbing or with one domain's interior, so the
#   default opens domain only; the other families are counted, named as skipped, and reachable
#   via --family constellation / --family governance (or everything via --family all).
#
# THE ROUND TRIP (open → exit → reopen)
#   Exiting the agent (/exit, or however the lane ends) KEEPS the tmux window — it prints
#   `── stream X exited — window kept ──` and drops to a shell so the closeout stays readable.
#   `Ctrl-b d` detaches from tmux without stopping anything. An exited stream's worktree remains
#   and the registry classifies it `dormant`: the next run of this script REOPENS it (labelled
#   REOPEN), re-entering the same worktree and branch. `--status` shows the whole cycle at a
#   glance: live (pid) / dormant / ready / blocked / stale / settled.
#
# Usage:
#   scripts/open-streams.sh                  # open + reopen the life/work domains, up to the bound
#   scripts/open-streams.sh --status         # one line per stream with its derived state
#   scripts/open-streams.sh --family all     # ...plus the constellation + governance rows
#   scripts/open-streams.sh --lane claude    # ...on a chosen lane (claude|codex|agy|opencode|…)
#   scripts/open-streams.sh --dry-run        # print exactly what would open, touch nothing
#   scripts/open-streams.sh --max-parallel 1 # open one, name the rest
#   scripts/open-streams.sh --all            # ignore the bound (you accept the jetsam risk)

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/.." && pwd)"

session="${LIMEN_STREAMS_TMUX_SESSION:-limen-streams}"
max_parallel="${LIMEN_STREAMS_MAX_PARALLEL:-}"
dry_run=0
unbounded=0
lane_choice=""
list_lanes_only=0
family="domain"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) dry_run=1; shift ;;
    --all) unbounded=1; shift ;;
    --max-parallel)
      [[ $# -ge 2 ]] || { echo "missing value for --max-parallel" >&2; exit 2; }
      max_parallel="$2"; shift 2 ;;
    --session)
      [[ $# -ge 2 ]] || { echo "missing value for --session" >&2; exit 2; }
      session="$2"; shift 2 ;;
    --family)
      # Which row family to open. Default `domain`: "open my streams" means the operator's
      # life/work domains (correspondence, financial, representation, …) — never one domain's
      # collaborator interior, never the estate's internal governance rows. Those are opened
      # deliberately, by name.
      [[ $# -ge 2 ]] || { echo "missing value for --family" >&2; exit 2; }
      case "$2" in
        domain|constellation|governance|all) family="$2" ;;
        *) echo "open-streams: unknown family '$2' (domain|constellation|governance|all)" >&2; exit 2 ;;
      esac
      shift 2 ;;
    --list-lanes)
      # Print the lanes this script will accept, one per line, then exit. Exists so nothing has to
      # re-derive the rule: tests and callers ask the script instead of keeping a second copy.
      lane_choice="--list"; list_lanes_only=1; shift ;;
    --status)
      # The registry owns state derivation — this is a pure delegate, so the launcher and the
      # checker can never tell the operator two different stories about the same stream.
      exec python3 "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/check-session-streams.py" --status ;;
    --lane)
      # Choose which native lane opens the domains. The REGISTRY stays vendor-neutral — it emits
      # `--agent auto` because the capsule contract declares `lane_selection:
      # derive_from_live_capabilities` and may never pin a provider. `auto` then resolves through
      # the live census, ordered by $LIMEN_AGENT. So the correct place for the operator's choice is
      # the environment, not declared data, and this flag is exactly that: it sets LIMEN_AGENT for
      # this run. Without it, census ORDER decides — which on a stock host is codex, not claude.
      [[ $# -ge 2 ]] || { echo "missing value for --lane" >&2; exit 2; }
      lane_choice="$2"; shift 2 ;;
    -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

# Validate the requested lane against the LIVE census before anything opens. A lane that is not
# live, or whose binary is not on PATH, must be refused here with the real alternatives named —
# discovering it inside a tmux window means N panes each printing an error nobody is watching.
# Checked even under --dry-run: a dry run whose lane is invalid would print a plan that cannot run.
if [[ -n "$lane_choice" ]]; then
  if ! lane_ok="$(
    PYTHONPATH="$repo_root/cli/src${PYTHONPATH:+:$PYTHONPATH}" python3 - "$lane_choice" <<'PY'
import os
import shutil
import sys

from limen.census import VENDORS, canonical
from limen.workstream_provider import workstream_binary_candidates, workstream_launchable


live = [
    v
    for v in VENDORS
    if v.status.available
    and v.status.state == "live"
    and workstream_launchable(v, autonomous=False)
    and any(shutil.which(candidate) for candidate in workstream_binary_candidates(v, os.environ))
]
want = canonical(sys.argv[1].strip().lower()) or sys.argv[1].strip().lower()
if want == "--list":
    # The set this script will accept, printed by the script itself. Anything that needs to know
    # which lanes are selectable asks HERE rather than re-deriving it — a second copy of this rule
    # is what let `--lane copilot` be accepted and then silently resolve to codex.
    for v in live:
        print(v.name)
    raise SystemExit(0)
if any(v.name == want for v in live):
    print(want)
    raise SystemExit(0)
names = ", ".join(v.name for v in live) or "(none)"
print(f"lane {sys.argv[1]!r} is not a live native lane on this host; live lanes: {names}", file=sys.stderr)
raise SystemExit(2)
PY
  )"; then
    echo "open-streams: refusing to open — see above" >&2
    exit 2
  fi
  if [[ "$list_lanes_only" -eq 1 ]]; then
    printf '%s\n' "$lane_ok"
    exit 0
  fi
  # `auto` reads this: the registry stays neutral, the operator's choice rides the environment.
  export LIMEN_AGENT="$lane_ok"
fi

if [[ "$dry_run" -eq 0 ]] && ! command -v tmux >/dev/null 2>&1; then
  echo "open-streams: tmux not found — install it (brew install tmux) or use --dry-run" >&2
  exit 127
fi

# `limen` must resolve BEFORE any window is opened. Discovering it is missing inside a tmux window
# means N windows each printing 'command not found' into a pane nobody is looking at.
if ! command -v limen >/dev/null 2>&1; then
  echo "open-streams: 'limen' not on PATH — pip install -e '$repo_root/cli'" >&2
  exit 127
fi

# The ready set, its bound, and each row's shell-quoted command — derived in one place. The checker
# exits non-zero on registry drift, and `set -e` makes that fatal here: we never open a set derived
# from an incoherent graph.
plan=$(
  python3 - "$repo_root" "${max_parallel:-}" "$unbounded" "$family" <<'PY'
import json
import os
import shlex
import subprocess
import sys

root, requested_cap, unbounded, family = sys.argv[1], sys.argv[2].strip(), sys.argv[3] == "1", sys.argv[4]

rows = json.loads(
    subprocess.run(
        [sys.executable, os.path.join(root, "scripts", "check-session-streams.py"), "--ready", "--json"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
)

# Family selection happens HERE, after the registry derives the full ready set, so the launcher
# can name what it is not opening — a filtered-out domain the operator cannot see reads as one
# that does not exist.
elided = [r for r in rows if family != "all" and r["family"] != family]
rows = [r for r in rows if family == "all" or r["family"] == family]

# Derived, not magic. An interactive agent session plus its tooling sits around GB_PER_STREAM; the
# reserve is the OS, the browser, and the heartbeat daemon, which are running regardless. Stated as
# constants so the arithmetic is auditable and the number moves when the machine does.
GB_PER_STREAM = 3.0
GB_RESERVED = 6.0
try:
    total_gb = int(subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True).stdout) / 1024**3
except (ValueError, OSError):
    total_gb = 0.0
derived = max(1, int((total_gb - GB_RESERVED) // GB_PER_STREAM)) if total_gb else 1

if unbounded:
    cap, why = len(rows), "--all (bound waived)"
elif requested_cap:
    cap, why = max(1, int(requested_cap)), "--max-parallel"
else:
    cap, why = derived, f"derived from {total_gb:.0f}GB RAM ({GB_RESERVED:.0f} reserved, {GB_PER_STREAM:.0f}/stream)"

# Resolve what `--agent auto` will actually pick, ONCE, and report it — using the same census rule
# start-worktree-session.sh:283-306 applies. `auto` is vendor-neutral by contract (the registry may
# never pin a provider), which means the lane is chosen by census ORDER unless $LIMEN_AGENT says
# otherwise: on a stock environment that is codex, not claude. An operator who asked for N claude
# sessions and silently got another vendor has been surprised by a contract detail, so the choice is
# printed before anything opens rather than discovered inside a pane.
lane = "unresolved"
try:
    sys.path.insert(0, os.path.join(root, "cli", "src"))
    import shutil

    from limen.census import VENDORS, by_name, canonical
    from limen.workstream_provider import workstream_binary_candidates, workstream_launchable

    preferred = canonical(os.environ.get("LIMEN_AGENT"))
    ordered = list(VENDORS)
    if preferred and by_name(preferred):
        ordered.sort(key=lambda v: v.name != preferred)
    eligible = [
        v
        for v in ordered
        if v.status.available
        and v.status.state == "live"
        and workstream_launchable(v, autonomous=False)
    ]
    picked = next(
        (
            (v, b)
            for v in eligible
            for b in workstream_binary_candidates(v, os.environ)
            if shutil.which(b)
        ),
        None,
    )
    if picked:
        lane = picked[0].name + ("" if preferred else "  (census default — set LIMEN_AGENT to steer)")
except Exception:  # noqa: BLE001 — reporting only; the launcher must not fail on a census hiccup
    pass

elided_note = ""
if elided:
    fams = sorted({r["family"] for r in elided})
    reach = " / ".join(f"--family {f}" for f in fams)
    elided_note = f"{len(elided)} row(s) in other families ({', '.join(fams)}) — open with {reach} or --family all"
print(f"CAP\t{cap}\t{why}\t{len(rows)}\t{lane}\t{elided_note}")
for i, row in enumerate(rows):
    # REOPEN vs OPEN is the registry's word (`reopen`: the worktree exists, the session exited) —
    # rendered here so the operator can tell resumption from a first open at a glance.
    kind = ("REOPEN" if row.get("reopen") else "OPEN") if i < cap else "DEFER"
    print(f"{kind}\t{row['id']}\t{row['job_class']}\t{shlex.join(row['argv'])}\t{row['title']}")
PY
)

cap_line="$(printf '%s\n' "$plan" | awk -F'\t' '$1=="CAP"')"
cap="$(printf '%s' "$cap_line" | cut -f2)"
cap_why="$(printf '%s' "$cap_line" | cut -f3)"
ready_n="$(printf '%s' "$cap_line" | cut -f4)"
lane="$(printf '%s' "$cap_line" | cut -f5)"
elided_note="$(printf '%s' "$cap_line" | cut -f6)"

if [[ "$ready_n" -eq 0 ]]; then
  echo "open-streams: NONE READY in family '$family' — nothing to open"
  [[ -n "$elided_note" ]] && echo "  note: $elided_note"
  python3 "$repo_root/scripts/check-session-streams.py" --ready
  exit 0
fi

echo "open-streams: $ready_n ready (family: $family), opening up to $cap  [$cap_why]"
[[ -n "$elided_note" ]] && echo "  elided:       $elided_note"
echo "  lane:         $lane"
echo "  tmux session: $session"
echo

opened=0

while IFS=$'\t' read -r kind sid job_class cmd title; do
  [[ "$kind" == "CAP" ]] && continue

  if [[ "$kind" == "DEFER" ]]; then
    # Named, never silent: a dropped stream the operator cannot see reads as one that opened.
    echo "  DEFER  $sid — over the bound; open later with:"
    echo "           $cmd"
    continue
  fi

  if [[ "$dry_run" -eq 1 ]]; then
    # Keep the OPEN/REOPEN distinction visible in the preview too.
    [[ "$kind" == "REOPEN" ]] && would="WOULD REOPEN" || would="WOULD"
    echo "  $would  $sid ($job_class) — $title"
    echo "           $cmd"
    opened=$((opened + 1))
    continue
  fi

  # Hydrate the credential organ's env sink FIRST: `limen workstream --conduct` needs the conduct
  # broker identity (LIMEN_CONDUCT_URL/TOKEN), and a fresh tmux pane inherits none of it — the
  # first live launch (2026-07-29) died at birth on BrokerUnavailable. Values are sourced, never
  # printed. Then keep the window after the agent exits: the operator needs to read the closeout,
  # and a window that vanishes on exit destroys exactly the output worth seeing.
  hydrate='[ -f "$HOME/.limen.env" ] && { set -a; . "$HOME/.limen.env"; set +a; };'
  window_cmd="$hydrate $cmd; printf '\n── stream %s exited — window kept ──\n' $(printf '%q' "$sid"); exec ${SHELL:-/bin/zsh} -l"

  if tmux has-session -t "$session" 2>/dev/null &&
     tmux list-windows -t "$session" -F '#W' 2>/dev/null | grep -qx "$sid"; then
    # The window survives exit BY DESIGN (the closeout stays readable) — but a kept window is not
    # a running stream, and skipping on window presence made the advertised round trip a lie:
    # exit → rerun hit SKIP forever until someone killed the window by hand (first live proof,
    # 2026-07-29). This row only reached the plan because liveness read the stream as openable,
    # so whatever occupies the window is a leftover shell, never the agent — respawn the stream
    # into it. The probe protects the one dangerous case for free: a human working inside the
    # worktree makes the stream `live`, and a live stream never enters the plan.
    tmux respawn-window -k -c "$repo_root" -t "$session:$sid" "$window_cmd"
  elif tmux has-session -t "$session" 2>/dev/null; then
    tmux new-window -t "$session" -n "$sid" -c "$repo_root" "$window_cmd"
  else
    tmux new-session -d -s "$session" -n "$sid" -c "$repo_root" "$window_cmd"
  fi
  echo "  $kind   $sid ($job_class) — $title"
  opened=$((opened + 1))
done < <(printf '%s\n' "$plan")

echo
if [[ "$dry_run" -eq 1 ]]; then
  echo "open-streams: DRY RUN — $opened would open, nothing was touched"
  exit 0
fi

echo "open-streams: $opened opened"
[[ "$opened" -gt 0 ]] && echo "  attach: tmux attach -t $session"
exit 0
