# FLAME activation — keeping the flame lit for a month away

The test: **Anthony leaves for a month; VLTIMA runs with or without him, and the
flame never goes out — even when the substrate isn't Claude.** This is the owned
record of what was built for that, what is already autonomous, and the few
irreducible human atoms that arm it. Surfaced once; not a nag.

## What is already substrate-independent (no tokens, no human)

The autonomic **body** needs no model at all. `route` / `feed` / `merge` / `heal` /
`sync-release` / `library-preserve` / `organ-health` are pure Python — they keep
breathing, healing, merging, and surfacing on **zero** vendor tokens. The only
thing that needs a model is *forward code generation*, and that already cascades
across 9 lanes with derived model tiers and self-healing lane gates. So most of
"the flame never goes out" already holds.

## What this change added (staged on this branch — deploy is his gate)

1. **The Continuity Kernel — `FLAME.md`.** The portable *self*: identity +
   prime-directive invariants + state-resume pointers. `dispatch._build_prompt`
   now prepends it to **every** lane's prompt, so whichever model runs the beat
   (codex, claude, opencode, gemini, jules, **ollama**, whatever comes next) acts
   AS VLTIMA, not as a generic coder. The model is the substrate; the kernel is
   the flame. Gated `LIMEN_FLAME_KERNEL` (default on), fail-open.
2. **The local floor — the `ollama` lane.** The last, unmetered cascade lane.
   When every metered/cloud vendor is spent (the "didn't pace tokens perfectly
   between refreshes" case), the beat still has a lane that can produce. Self-
   activating: it auto-joins the instant a model is pulled.
3. **The dead-man's switch — `com.limen.watchdog.plist`.** launchd re-fires
   `watchdog.py --heal` every 5 min no matter what, and it `kickstart`s the
   heartbeat whenever it is down / not-beating / wedged. heartbeat + watchdog =
   the flame relights itself.

## The irreducible human atoms (one-time, then walk away)

| # | Atom | Cheapest path | Unblocks |
|---|------|---------------|----------|
| 1 | **Arm self-resurrection** | `launchctl bootstrap gui/$(id -u) "$LIMEN_ROOT/container/launchd/com.limen.watchdog.plist"` (verify: `launchctl list \| grep limen`) | daemon relights itself after any crash/wedge — the core of "runs without me" |
| 2 | **Light the local floor** | `ollama pull qwen2.5-coder:7b` (then optionally add `ollama` to `LIMEN_LANES` in `com.limen.heartbeat.plist` for proactive use, not just failover) | a free, always-up coding lane when all metered vendors exhaust |
| 3 | **Cloudflare deploy token** | `wrangler login`, or set `CLOUDFLARE_API_TOKEN` in `~/.limen.env` | 16 revenue tasks / 6 products can go live unattended |
| 4 | **Durable mail credential** | use an **app-password** (no expiry) not the 7-day OAuth: land `GMAIL_APP_PASSWORD` in `~/.limen.env` (cred exists at `op://Private/gmail-app-pw-2026-06-06`) | mail lane survives past day 7 (OAuth testing-mode expires) |
| 5 | **Open the merge gate** | say "open the merge gate" (or grant `Bash(gh pr merge:*)`) | the 20 clean PRs land — see `docs/MERGE-READY.md` |

Atoms 1–2 are what make a *month* unattended real. Atoms 3–5 are the revenue/mail
gates already tracked in the live `needs_human` digest; they're repeated here so
the whole "month away" picture is one page.

## Optional throughput accelerator (not an atom — a knob)

The HEAL/MERGE organs now scan the **full** open-PR backlog (306 PRs as of this
writing) via a rotating window instead of only the first 30, so every CI-red PR is
seen and gets a heal task over successive beats. Healing then *runs* on whatever lane
the router picks; repos without a local checkout already ride **Jules** (async, non-
blocking). To let the daemon launch more local repairs per beat without a blocking
beat, set `LIMEN_DISPATCH_ASYNC=1` (and optionally override the host-derived
`LIMEN_ASYNC_MAX`) in `container/launchd/com.limen.heartbeat.plist`. Reversible; purely a
speed dial on draining the red pile — the coverage fix above works without it.

## Verify the flame after arming

- `launchctl list | grep com.limen` → both `heartbeat` and `watchdog` present.
- `python3 scripts/watchdog.py --dry-run` → assess without healing.
- `logs/organ-health.json` (or `organ-health.html`) → organs green.
- Kill the heartbeat (`launchctl kill TERM gui/$(id -u)/com.limen.heartbeat`) and
  confirm the watchdog relights it within ~5 min — the dead-man's switch, proven.
