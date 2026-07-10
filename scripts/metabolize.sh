#!/usr/bin/env bash
# metabolize.sh — one full metabolism cycle of the conductor (the heartbeat).
#
#   drain (close completed) → mine (refill queue) → route (assign cheapest
#   vendor) → [dispatch] → board.
#
# This is the body the local cron AND the remote 4-hourly auto-scaler run to keep
# idle multi-vendor capacity producing. Idempotent + bounded.
#
# SAFE BY DEFAULT: without LIMEN_DISPATCH=1 it only drains/mines/routes/reports —
# all reversible local writes, nothing outward. With LIMEN_DISPATCH=1 it also:
#   - dispatches local lanes (codex/opencode/agy/claude) which, via worktree
#     isolation, only ever produce reviewable PRs — never touch a live tree;
#   - dispatches jules within its daily budget.
#
# Knobs: LIMEN_MINE_LIMIT (15)  LIMEN_LOCAL_LIMIT (3)  LIMEN_JULES_LIMIT (10)
set -uo pipefail
export LIMEN_ROOT="${LIMEN_ROOT:-$HOME/Workspace/limen}"
export LIMEN_TASKS="${LIMEN_TASKS:-$LIMEN_ROOT/tasks.yaml}"
export LIMEN_WORKDIR="${LIMEN_WORKDIR:-$HOME/Workspace}"
export LIMEN_ISOLATION="${LIMEN_ISOLATION:-worktree}"
export PYTHONPATH="$LIMEN_ROOT/cli/src"
# macOS 26.6 fork-safety mitigation. Apple's Network.framework (loaded at startup into
# EVERY python here — 3.14/3.13/3.9 alike) registers a pthread_atfork child handler
# (nw_settings_child_has_forked) that SIGSEGVs in os_log on the child side of a
# fork()+exec() — i.e. any subprocess call that passes cwd=/preexec_fn (~32 fleet files).
# It's a timing race, so it kills a fraction of the thousands of fork+exec/beat. Quieting
# os_activity defuses the os_log path the handler crashes in. Must be set BEFORE any python
# launches (the framework loads before user code runs), so it lives here, above the first
# python invocation. Mechanism-certain cure = keep subprocess on posix_spawn (no cwd=);
# this env var is the zero-blast-radius mitigation. See fork-oslog crash report 2026-07-09.
export OS_ACTIVITY_MODE="${OS_ACTIVITY_MODE:-disable}"
cd "$LIMEN_ROOT" || exit 1
if [ -z "${LIMEN_WORKTREES:-}" ]; then
  if [ -d /Volumes/Scratch ] && [ -w /Volumes/Scratch ]; then
    export LIMEN_WORKTREES="/Volumes/Scratch/limen-worktrees"
  else
    export LIMEN_WORKTREES="$LIMEN_WORKDIR/.limen-worktrees"
  fi
else
  export LIMEN_WORKTREES
fi
export LIMEN_WORKTREE_ROOT="${LIMEN_WORKTREE_ROOT:-$LIMEN_WORKTREES}"
mkdir -p "$LIMEN_WORKTREES" "$LIMEN_WORKTREE_ROOT" 2>/dev/null || true

echo "═══ metabolize $(date '+%F %T') — dispatch=${LIMEN_DISPATCH:-0} isolation=$LIMEN_ISOLATION ═══"

echo "── 0a. hydrate credentials (1Password → ~/.limen.env → every lane; never re-login) ──"
# Refresh fleet creds from the ONE source of truth so a one-time login never has to be repeated
# (lapsed tokens / fresh worktrees self-heal). Fail-open: skips silently if op is locked/absent.
if [ "${LIMEN_CREDS_HYDRATE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/creds-hydrate.py" --apply || echo "  (creds-hydrate skipped — op locked/absent)"
  # PRESENCE is not VALIDITY: a stale/revoked/suspended token sits in the floor looking ✓ while every
  # lane it feeds is dead. Probe each materialized cred against its service and surface the dead ones.
  # Non-fatal (never breaks the beat) and fail-open offline; a re-mint into op self-heals on next --apply.
  python3 "$LIMEN_ROOT/scripts/creds-hydrate.py" --verify || echo "  ↑ DEAD credential(s) above — re-mint into the op:// item, then they self-heal next beat"
fi
# Source the cred cache so THIS shell + every child (route.py, the agent CLIs) inherit the keys.
if [ -f "$HOME/.limen.env" ]; then set -a; . "$HOME/.limen.env"; set +a; fi

echo "── 0b. verify MCP connector consent (Lane B — surface lapsed claude.ai connectors in the log, never in chat) ──"
# The op:// lane (0a) has a validity probe; this is the missing one for the OTHER credential lane —
# the claude.ai hosted MCP connectors whose OAuth lives SERVER-SIDE (no local token to refresh). A
# lapsed connector surfaces HERE in the beat log with its one-lever cure (L-IANVA-CLOUD), not as a
# recurring /mcp chat nag. Non-fatal + fail-open offline (exit 0 unless a REQUIRED connector lapses).
if [ "${LIMEN_MCP_VERIFY:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/mcp-auth-verify.py" || echo "  ↑ REQUIRED MCP connector(s) unauthenticated — pull L-IANVA-CLOUD (#263) to end the class"
fi

echo "── 0c. verify the cartridge is plugged into the real source (host-is-factory invariant) ──"
# The factory/cartridge law (memory: host-is-factory-system-is-cartridge) needs one check
# nothing else performs: is chezmoi pointed at the REAL cartridge (organvm/domus-genoma), or at
# a scratch/dummy source? chezmoi verify/status/health only validate WHATEVER source is wired, so
# a disconnected cartridge returns a meaningless green. This runs regardless of chezmoi's state and
# surfaces an unplugged cartridge HERE in the beat log — not months later by accident. Fail-open:
# exit 0 when connected OR chezmoi absent; non-zero only on a genuine disconnection.
if [ "${LIMEN_CARTRIDGE_CHECK:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/cartridge-connected.py" || echo "  ↑ cartridge UNPLUGGED (above) — bring domus-genoma current, then re-point chezmoi at it"
fi

echo "── 0c'. verify config hydrates from the CURRENT cartridge (no wedge / no stale / no orphan) ──"
# cartridge-connected proves the right REMOTE is wired; it cannot see three states that still read
# green there but silently disable hydration: (1) a strict-missingkey template error aborts the whole
# `chezmoi status`/apply run (the wedge that let a subagent's ~/.claude statusline write become a
# durable-looking local orphan, 2026-07-09); (2) the source checkout parked on a stale branch serves
# old config so a master-fixed template is still broken locally; (3) a managed target edited on disk
# but never re-added (the auto-capture hook only fires on the Edit tool). Fail-open only for an absent
# chezmoi; a wedged pipeline / stale cartridge / .claude orphan is the actionable non-zero.
if [ "${LIMEN_CHEZMOI_DRIFT_CHECK:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/chezmoi-drift.py" || echo "  ↑ config is NOT hydrating from the current cartridge (above) — nothing is local; reconcile per the hint"
fi

echo "── 0d. verify enactment — every declared-ON fleet flag is actually LIVE (not just merged) ──"
# The gap this closes (memory: enacted-not-declared): a flag can be declared ON in parameters.yaml
# and merged, yet be dark in the RUNNING beat — either wired nowhere (TABVLARIVS #576 shipped its
# producers OFF while the note claimed the fleet enabled them) or wired-but-the-daemon-never-
# kickstarted (a `while true` loop never re-sources itself). verify-whole enforces the wiring
# contract; THIS surfaces the live-host liveness truth in the beat log — a stale daemon or an
# un-enacted switch shows up HERE, not by the operator asking five times. Fail-open, never fatal.
if [ "${LIMEN_ENACTMENT_CHECK:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/enactment-audit.py" --check || echo "  ↑ un-enacted fleet flag above — wire it in heartbeat-loop.sh, or kickstart the daemon (launchctl kickstart -k gui/\$(id -u)/com.limen.heartbeat)"
fi

echo "── 0e. refresh the weekly Fable balance meter + surface an over-cap / unaccepted Fable run ──"
# The Fable runtime backstop (docs/fable-allotment.md): Fable is PLAN-ONLY and ~111x Opus cost. The
# receipt organ gates INTENDED spend at accept-time; this refreshes the LIVE weekly meter
# (logs/fable-allotment.json, read by model_selection's cap gate) and surfaces an over-cap or
# unaccepted Fable session HERE in the beat log — like creds-hydrate --verify — instead of only on a
# manual audit. Fail-open, never fatal: a measurement hiccup can't break the beat.
if [ "${LIMEN_FABLE_BALANCE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/fable-allotment.py" balance >/dev/null 2>&1 || echo "  (fable balance meter skipped — see logs)"
  if [ -n "${LIMEN_LATEST_SESSION_JSONL:-}" ] && [ -f "${LIMEN_LATEST_SESSION_JSONL}" ]; then
    python3 "$LIMEN_ROOT/scripts/claude-workflow-guard.py" audit-transcript "${LIMEN_LATEST_SESSION_JSONL}" >/dev/null \
      || echo "  ↑ unaccepted / over-budget Fable run above — accept it (scripts/fable-allotment.py accept …) or drop off Fable (docs/fable-allotment.md)"
  fi
fi

echo "── 0e. armed-valve audit — parked levers vs silently-off valves ──"
# The gap this closes (retro 06-24→07-08 finding 8; PREC-2026-07-08-armed-valve-outcome):
# a deliverable-IS-the-behavior valve left disarmed (MONETA's empty checkout, the censor
# mirror's permanent dry-run, LIMEN_DISPATCH unset) satisfies every closeout predicate while
# drifting the OUTCOME. This separates ARMED / PARKED (lever cites it — owned, fine) /
# SILENT-OFF (the failure class) every beat. Fail-open, never fatal to the beat.
if [ "${LIMEN_VALVE_AUDIT:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/armed-valve-audit.py" --check || echo "  ↑ SILENTLY-OFF deliverable valve above — arm it, or file its lever in his-hand-levers.json"
fi

echo "── 0f. ship gate — product-facing done requires a reachable external artifact ──"
# The gap this closes (retro 06-24→07-08 findings 4 + gap-model): 101 creative asks produced
# merged PRs and receipts and nothing a user could reach; MONETA's URL returned curl-000 while
# every internal predicate read green. Probes each registered product artifact
# (spec/ship-surfaces.json) + every product-facing done-claim on the board. Fail-open.
if [ "${LIMEN_SHIP_GATE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/ship-gate.py" --check || echo "  ↑ product-facing done-claim with NO reachable artifact above — deploy it or reopen the task"
fi

echo "── 0g. heal convergence — the healer must converge, not re-spend capacity on a wall ──"
# The gap this closes (retro 06-24→07-08 findings 1–2): the healer opened PRs it could not
# merge (growth-auditor #16–#22, theoria #492…#500 — same check red every time) and nothing
# detected the stall; 59% of heal receipts produced no PR with no field separating
# "already green" from "gave up silently". Chronic = ≥3 open heal PRs failing the SAME
# check >48h. Receipts now carry a mechanically-derived outcome (async-run-one.py). Fail-open.
if [ "${LIMEN_HEAL_CONVERGENCE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/heal-convergence.py" --check || echo "  ↑ CHRONIC heal non-convergence above — fix the named check at its root or park the repo with a chronic receipt"
fi

echo "── 0g2. fork-safety — the macOS 26.6 atfork/os_log crash must stay fixed, provably ──"
# The gap this closes: "python keeps crashing" was root-caused to Apple's Network.framework
# pthread_atfork child handler segfaulting in os_log on the child side of fork()+exec(). The
# fix (OS_ACTIVITY_MODE=disable, set above) shipped, but the crash is a timing RACE — "no
# recurrence" was a hope, not a predicate (Definition of Done + sensor-without-effector laws).
# This asserts, every beat, that the mitigation is still present in the beat scripts AND that no
# .ips crash report matching the atfork/os_log signature is newer than the mitigation commit. A
# recurrence exits non-zero here (the effector) and is the documented trigger to arm the dark
# posix_spawn escalation (LIMEN_FORK_SAFE). macOS-only signal; fail-open on non-darwin / no git.
if [ "${LIMEN_FORK_SAFETY_CHECK:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/check-fork-safety.py" --check || echo "  ↑ fork/os_log crash RECURRED or mitigation removed above — restore OS_ACTIVITY_MODE=disable, or arm the posix_spawn escalation (LIMEN_FORK_SAFE=1; see scripts/check-fork-safety.py)"
fi

echo "── 0g3. trunk-green — main's required CI must stay green, or nothing can merge ──"
# The gap this closes (2026-07-10): main's REQUIRED pr-gate silently went red (non-hermetic tests)
# and NO sensor detected it — it blocked every PR until a human noticed and a reactive lane fixed it
# in parallel with a duplicate. pr-gate runs on pull_request only; ci.yml runs the SAME suite on
# push:[main], so the latest completed CI run on main is the trunk-health proxy. On RED this exits
# non-zero (the beat surfaces it) and — once armed (LIMEN_MAIN_GREEN_APPLY=1) — emits ONE idempotent
# HEAL-mainred task so lanes converge instead of duplicating. Detection ships armed; emission dark
# (observable-before-autonomous). Throttled gh + fail-open offline; never fatal to the beat.
if [ "${LIMEN_MAIN_GREEN_CHECK:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/check-main-green.py" || echo "  ↑ main trunk RED above — a heal PR is needed (arm LIMEN_MAIN_GREEN_APPLY=1 to auto-emit one canonical HEAL-mainred task); see scripts/check-main-green.py"
fi

echo "── 0h. dispatch continuity — detect a silent lane while queue + budget exist ──"
# The gap this closes (Jul 3–5 starvation precedent): Jules accepted zero tasks for 72h
# while ~40 open tasks sat in the queue and the budget showed headroom. Daemon alive,
# queue full, meter green — but the lane was dark. Nothing surfaced this until a human
# noticed. This check runs every beat and classifies each lane as flowing / idle-ok /
# starved. Two consecutive starved readings hang an idempotent ASK-lane-starved-<lane>
# needs_human atom. Fail-open — missing data → "unknown", never an alarm.
if [ "${LIMEN_CONTINUITY_CHECK:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/dispatch-continuity-check.py" || echo "  (continuity skipped)"
fi

echo "── 0i. ask gate — every intake-window ask carries one done-predicate, or gets split ──"
# The gap this closes (retro 06-24→07-08 gap model): asks converge iff they are
# predicate-shaped, bounded, and owned; the five most-escalated themes were exactly the
# narrative/multi-goal ones. Report-only for now (observable-before-autonomous — the
# LIMEN_CENSOR_APPLY constitutional pattern): counts land in logs/ask-gate.json; keeper-seam
# enforcement (--task-file --check on every incoming ticket) arms once the log proves the
# predicate. Fail-open, never fatal.
if [ "${LIMEN_ASK_GATE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/ask-gate.py" --audit --since 7 --top 8 || echo "  (ask-gate report failed — non-fatal)"
fi

echo "── 0i. omega — the autonomic fixed point (conjunction of every gate's --check) ──"
# The gap this closes (retro 06-24→07-08, omega definition): each gate proves its own slice, but
# nothing asserted the WHOLE — that the system runs unattended, products are reachable, healing
# converges, nothing hangs on the session. omega.sh composes them; a rung it cannot check is SKIP,
# never a silent PASS (the MONETA curl-000 lesson). --offline runs the det subset (no network in the
# cheap beat rungs); the verdict + PASS/FAIL/SKIP lands in logs/omega.json for session-orient.
# Fail-open, never fatal to the beat.
if [ "${LIMEN_OMEGA:-1}" = "1" ]; then
  bash "$LIMEN_ROOT/scripts/omega.sh" --offline --quiet || echo "  ↑ OMEGA not holding above — a gate rung failed; the system is off its fixed point (see logs/omega.json)"
fi

echo "── 0. refresh usage telemetry / lane health ──"
python3 "$LIMEN_ROOT/scripts/usage-telemetry.py" || echo "  (usage telemetry skipped)"

# DEAD-LINK HYGIENE: a 404 on a public identity surface is silent demand-loss — it repels the exact
# visitor the front door pulls, and nobody reports it. Probe the tracked surfaces (link-surfaces.json)
# for broken links; self-throttled to ~6h so the beat never floods the network. Fail-open, never fatal.
if [ "${LIMEN_LINK_HEALTH:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/link-health.py" --verify --throttle 21600 || echo "  ↑ DEAD link(s) on a public surface above — fix at the source or add a remap in link-surfaces.json"
  # SELF-HEAL: when a dead link has a verified-live replacement, the organ OPENS a reviewable
  # fix-PR (reversible — never a merge; publishing stays the human's hand). Idempotent +
  # self-limiting: one PR per distinct fix-set, skipped once a PR for it exists, so once merged
  # the link resolves and no PR re-opens. Reuses the throttled probe above (near-zero extra work).
  # Set LIMEN_LINK_HEAL=0 to keep detection but disable auto-opening PRs.
  if [ "${LIMEN_LINK_HEAL:-1}" = "1" ]; then
    python3 "$LIMEN_ROOT/scripts/link-health.py" --heal --apply --throttle 21600 || echo "  (link-health heal skipped/failed — non-fatal)"
  fi
fi

# CODEX SKILL BUDGET HYGIENE (memory: distillation-not-reduction). Codex shortens skill
# descriptions past its ~2% skills budget every session; the session-noise-containment doctrine
# (Rule 1) BANS the disable-to-silence "fix" (that reduces capability). Instead distill every
# plugin/skill description to a thin, meaning-preserving lead — keeping EVERY skill. The
# marketplace cache reverts on refresh, so re-running each beat self-heals it. Idempotent +
# reversible (--restore); silent when already thin, logs the re-heal when a refresh grew it
# back — surfaced HERE, never hidden. Set LIMEN_CODEX_SLIM=0 to disable.
if [ "${LIMEN_CODEX_SLIM:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/codex-skill-slim.py" --apply --quiet || echo "  (codex-skill-slim skipped — no codex config/cache)"
fi

echo "── 0i. routine freshness — detect cloud routines that fire but stop delivering ──"
# The gap this closes (atom-backlog-triage 25-day silence precedent): a cloud routine can FIRE
# (its scheduler triggers it in claude.ai) without DELIVERING (writing a comment to its rolling
# GitHub issue). This organ proves firing == delivering on every beat by querying rolling-issue
# comment timestamps via gh; any routine silent beyond 2x its max_silent_days gets a needs_human
# atom hung in the permanent queue. Self-throttled to ~6h so the beat never floods the network.
# Fail-open, never fatal.
if [ "${LIMEN_ROUTINE_FRESHNESS:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/routine-freshness-audit.py" --throttle 21600 || echo "  (routine freshness skipped)"
fi

echo "── 0j. session walk — full-horizon census of BOTH vendor session estates ──"
# QUICKEN breathes the recent stalled tail (3-day horizon); this organ answers the whole
# question "has EVERY session been walked from first prompt to implementation?" across
# ~/.claude/projects AND ~/.codex/sessions, all projects, all time. Unwalked user sessions
# land in logs/session-walk-residue.md with resume pointers, and --walk drains a bounded
# few per beat (journaled; 2-strike give-up). Fail-open, never fatal.
if [ "${LIMEN_SESSION_WALK:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/session-walk-census.py" --walk "${LIMEN_SESSION_WALK_CAP:-2}" || echo "  (session walk skipped)"
fi

echo "── 1. drain (close completed Jules) ──"
bash "$LIMEN_ROOT/scripts/drain.sh" || echo "  (drain skipped/failed — continuing)"

echo "── 2. mine (refill queue from GitHub backlog) ──"
python3 "$LIMEN_ROOT/scripts/mine-backlog.py" --limit "${LIMEN_MINE_LIMIT:-15}" --apply || echo "  (mine skipped)"

echo "── 2b. generate (self-feed build-out tasks if mining left the queue below floor) ──"
# the SELF-FEEDING guarantee: when the GitHub backlog is exhausted and mining returns nothing,
# this tops the queue to LIMEN_BACKLOG_FLOOR with useful per-product work so `open` never hits 0
# and the loop never idles. No-ops when the queue is already healthy.
python3 "$LIMEN_ROOT/scripts/generate-backlog.py" --apply || echo "  (generate skipped)"

echo "── 3. route (assign cheapest-capable vendor) ──"
python3 "$LIMEN_ROOT/scripts/route.py" --apply || echo "  (route skipped)"

if [ "${LIMEN_DISPATCH:-0}" = "1" ]; then
  echo "── 4a. dispatch local lanes → PRs (worktree-isolated, live tree untouched) ──"
  for v in codex opencode agy claude; do
    python3 -m limen dispatch --agent "$v" --live --limit "${LIMEN_LOCAL_LIMIT:-3}" || true
  done
  echo "── 4b. dispatch jules (within daily budget) ──"
  python3 -m limen dispatch --agent jules --live --limit "${LIMEN_JULES_LIMIT:-10}" || true
else
  echo "── 4. dispatch SKIPPED (set LIMEN_DISPATCH=1 to enable outward dispatch) ──"
fi

echo "── 5. board ──"
python3 -m limen doctor 2>&1 | head -12

echo "── 5b. insight-cadence (proposal-only auto-reporting) ──"
# Generates reports at 4 tiers (hourly/daily/weekly/monthly). Self-gates behind
# elapsed wall-clock time internally, but --once forces it to run if due.
if [ "${LIMEN_INSIGHT_CADENCE:-1}" = "1" ]; then
  python3 "$LIMEN_ROOT/scripts/insight-cadence.py" --once || echo "  (insight-cadence skipped)"
  # Route the latest report per tier to its durable owner (his-hand levers / keeper upsert
  # tickets / organ residual inboxes). Armed by the same default as the heartbeat
  # (LIMEN_INSIGHT_ROUTE_APPLY=1); board echoes are skipped, new tasks capped per pass.
  LIMEN_INSIGHT_ROUTE_APPLY="${LIMEN_INSIGHT_ROUTE_APPLY:-1}" \
    python3 "$LIMEN_ROOT/scripts/insight-route.py" | tail -3 || echo "  (insight-route skipped)"
  # Mirror live censor residuals → public `censor` GitHub issues (auto-open/auto-close, capped).
  # Observable before autonomous: dry-run until LIMEN_CENSOR_ISSUES_APPLY=1 arms it.
  python3 "$LIMEN_ROOT/scripts/sync-censor-issues.py" \
    $([ "${LIMEN_CENSOR_ISSUES_APPLY:-0}" = "1" ] && echo --apply) | tail -3 || echo "  (censor-issues skipped)"
fi

echo "── 5c. arca (encrypted private-estate vault) ──"
# ARCA — off-machine durability for the private estate: every ~/Workspace/_*-private store,
# AES-256-encrypted (key ONLY in the macOS Keychain, never in any repo or env file) and pushed
# as ciphertext to a private GitHub repo (organvm/arca). The containment inverse of the public
# lanes: GitHub never sees a plaintext byte. Change-detected + roundtrip-verified; no-ops in
# seconds when nothing changed. Fails soft (headless Keychain / offline). LIMEN_ARCA=0 disables.
if [ "${LIMEN_ARCA:-1}" = "1" ]; then
  bash "$LIMEN_ROOT/scripts/arca.sh" backup || echo "  (arca skipped — keychain locked, offline, or vault unconfigured)"
fi

# ── 6. self-improve (LOW cadence) — the last rung of the self-* ladder ──
# Reads the loop's own dispatch_log track record and emits a re-plan PROPOSAL to
# logs/self-improve-proposal.json (down-weight 0%-lanes, retire chronic-fail
# patterns, boost what ships). Proposal-only + read-only — never writes tasks.yaml.
# It's a slow-moving signal, so run it only every Nth beat, not per-beat.
# Wired live: low-cadence voice (every LIMEN_SI_CADENCE hours) — the last rung that closes the ladder.
N="${LIMEN_SI_CADENCE:-10}"
if [ "$(( $(date +%s) / 3600 % N ))" = "0" ]; then
  python3 "$LIMEN_ROOT/scripts/self-improve.py" || echo "  (self-improve skipped)"
fi

# ── 7. handoff-relay — write the seam-survival packet so the next session/vendor/beat
# resumes WARM (open lanes, in-flight claims, last blocker, budget, next action). Keystone of
# the walk-away loop (retro 2026-07-08). Read-only over the board; never writes tasks.yaml.
python3 "$LIMEN_ROOT/scripts/handoff-relay.py" || echo "  (handoff-relay skipped)"

echo "═══ metabolize done $(date '+%F %T') ═══"
