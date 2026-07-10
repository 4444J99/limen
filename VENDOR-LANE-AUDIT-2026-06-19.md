# Vendor Lane Audit — 2026-06-19 (read-only)

> **Correction 2026-07-10 (opencode):** the "opencode = free-model lane / free model fallback"
> characterization below is superseded. opencode is multi-model — a free floor **and** the opencode
> Zen subscription. Under dynamic provider routing (#921) its model is selected LIVE from
> `opencode models --verbose` with **no free fallback and no name heuristic**; an unauthed /
> capability-poor catalog yields `failed_blocked`, not a silent downgrade. The subscription becomes
> reachable via `opencode auth login` (lever **L-OPENCODE-SUB-AUTH #928**). Live truth is the census
> record + provider routing, not this dated snapshot.

Mandate: use ALL 6 vendors, never serialize. Audit found the fleet is effectively
serialized onto **codex** (now exhausted), with agy/gemini/claude/jules idle.

## Per-vendor health

| vendor | CLI | auth | health | idle reason |
|---|---|---|---|---|
| codex | /opt/homebrew/bin/codex 0.141.0 | ~/.codex/auth.json (chatgpt) OK | EXHAUSTED | router dumps 209 tasks here; usage.json health=exhausted, 0 tok remaining in 5h window |
| claude | ~/.local/bin/claude | ~/.claude.json OK | HEALTHY but idle | router routes 0 tasks to claude; open_queue=0; 40% token headroom unused |
| opencode | /opt/homebrew/bin/opencode 1.17.5 | NO auth.json -> free model fallback | HEALTHY (degraded) | only 10 tasks routed (deploy-only); no API key, runs free `opencode/north-mini-code-free` |
| agy | /opt/homebrew/bin/agy 1.0.10 | local CLI, scratch bridge healed | HEALTHY but idle | 0 tasks routed; was on lanes-down.txt earlier (now gone); scratch-bridge makes it produce |
| gemini | /opt/homebrew/bin/gemini 0.46.0 | GEMINI_API_KEY set but NOT exported | DOWN | key is shell var, not exported -> Python os.environ can't see it; free-tier key also rate-limits instantly |
| jules | /opt/homebrew/bin/jules | ~/.jules OK | HEALTHY but idle | router reserves jules only for repos w/ no local checkout; everything has a checkout -> 0 routed; 8 stale claims |

## Root causes (verified)

1. **Router serialization (the big one).** `python3 scripts/route.py` routes
   `{codex: 209, opencode: 10}` and ZERO to claude/agy/gemini/jules. The
   "prefer local codex, save Jules quota" heuristic in `scripts/route.py`
   funnels the whole backlog into codex. codex `usage.json` -> `health: exhausted`,
   `remaining: 0` tokens (5h window). This is the literal opposite of the
   round-robin mandate.

2. **gemini key not exported.** `typeset -p GEMINI_API_KEY` shows the value is set
   but NOT exported (not in `export -p`). `python3 -c "os.environ.get('GEMINI_API_KEY')"`
   returns None, so `route.py:_vendor_health()` marks gemini down and dispatch never
   passes the key to the subprocess. When the key IS exported, `_vendor_health()`
   flips gemini to True (verified). Secondary: even with the key, the FREE-tier key
   rate-limits instantly — heartbeat log shows 16 `RATE-LIMIT gemini` in one beat.

3. **agy/jules/claude idle = starvation, not breakage.** All three pass health
   checks. They have 0 open tasks routed to them (`open_queue=0`). `logs/lanes-down.txt`
   does NOT currently exist, so `_down_lanes()` returns `set()` — the heartbeat's
   historical `skipping down lanes: ['agy','gemini']` lines are from older beats.

4. **doctor `agent_cli: FAIL agent-dispatch not found` is a false alarm** for local
   lanes. `dispatch.py:138` references a legacy `agent-dispatch` binary, but real
   local dispatch uses the per-vendor argv in `_AGENT_ARGV` (codex/claude/opencode/
   agy/gemini all have correct write flags). Ignore that FAIL for local lanes.

## Write-flags per lane (all correct in dispatch.py `_AGENT_ARGV`)

- codex: `exec --skip-git-repo-check --sandbox workspace-write` (writes)
- claude: `-p --permission-mode acceptEdits` (writes)
- opencode: `run` + model injected lazily from `opencode models` (writes; no -m = no-op)
- agy: `--dangerously-skip-permissions -p` + `_bridge_agy_scratch` carries scratch->worktree (writes)
- gemini: `--approval-mode auto_edit -p` (writes)
- jules: `jules new --repo <r> <prompt>` (async cloud)

## Concrete unblock actions

1. **De-serialize the router** (highest leverage). Spread the 209 codex tasks across
   all healthy lanes round-robin (codex/claude/agy + opencode for deploy + jules for
   no-checkout repos). Either patch `scripts/route.py` to round-robin among up lanes
   instead of defaulting all-local -> codex, or run `python3 scripts/route.py --apply`
   only after the heuristic is balanced. (Do NOT --apply the current single-lane plan.)
2. **codex exhausted**: stop feeding it; it refills on the ~5h rolling window. Move its
   queued work to claude/agy now.
3. **gemini**: `export GEMINI_API_KEY` (add `export` so subprocesses inherit it), and/or
   do the one-time Google sign-in to create `~/.gemini/oauth_creds.json` then set
   `LIMEN_GEMINI_OAUTH=1` (dispatch.py:477 drops the API key for gemini's subprocess to
   use the higher-limit OAuth/Code-Assist tier). Free-tier key alone rate-limits.
4. **opencode**: run `opencode auth login` to write `~/.local/share/opencode/auth.json`
   so it uses a real model instead of the free fallback.
5. **agy / claude / jules**: no fix needed — route work to them (fixing #1 unblocks all
   three). jules also has 8 stale claims: `limen release-stale --agent jules --hours 24 --apply`.
