# START HERE — fresh-session bootstrap (Limen conductor)

> You are resuming as conductor of the Limen autonomous agent fleet. The previous session
> (`9750bef7`) got noisy — you inherit its **learnings** (memory), not its thrash. Begin clean.
> Read this file + `EVERY-ASK-LEDGER.md`, then act.

## 1. Orient (read-only)
```bash
cd ~/Workspace/limen && export LIMEN_ROOT="$PWD" LIMEN_TASKS="$PWD/tasks.yaml" \
  LIMEN_WORKDIR="$HOME/Workspace" PYTHONPATH="$PWD/cli/src"
python3 scripts/watch.py --once      # live per-agent board (omit --once to stream)
cat EVERY-ASK-LEDGER.md              # every ask present→past + the "Pick up here" checklist
```
Then read `MEMORY.md` + the memory dir — those mandates are binding.

## 2. Live state (as of session 9750bef7 close)
- Fleet is **LIVE & autonomous**: daemon `com.limen.heartbeat` (was pid 25199) dispatches
  across all 6 vendors. Do NOT restart it — observe and steer.
- Board ~ done 300+ / open ~255 / dispatched ~115. Budget refills per-vendor window.
- **Exporter revenue chain FULLY MERGED** (#26,39,40,41,42,43 + #27 foundation) — monetize it.
- Merge gate: 38 PRs merged this session with **zero bypass**.

## 3. Binding mandates (from memory — do not violate)
- **No downtime ever** — queue never hits 0; generate work when it drains.
- **Use ALL 6 vendors** (codex/opencode/agy/claude/gemini/jules); never serialize through one Claude.
- **Ideal-form wins over old** — deduce to certainty; don't punt decisions back to the user.
- **Never admin-bypass a merge gate** — FIX the gate instead (see #5).
- **Derive, never pin.** Archive4T = frozen backup, never delete/dedup. Secrets via `~/.limen.env`.

## 4. Settled decision — GitHub structure (EXECUTE on go, don't re-litigate)
287 repos across 11 owners is the bug. Target: **ONE org `organvm`** (already yours, empty).
Kill Enterprise forever. Collapse all 11 owners → `organvm` (source "spheres" become repo TOPICS).
One repo per product. A GitHub App `limen[bot]` becomes the fleet identity (decouples CI from
personal billing). Dry-run tool ready: `scripts/consolidate-github.py` (executes nothing without
`--apply`, gated on the user).

## 5. THE bottleneck + the decisive fix
Repos have **zero branch protection** → can't arm auto-merge → hand-merging races the fleet's
continuous PR output (a treadmill). **Fix:** `scripts/setup-rulesets.py` — add required-CI branch
protection + enable auto-merge across repos → PRs self-merge on green, gate drains itself, no
bypass. Dry-run first, reversible, **gated on user go-ahead.** This is the highest-leverage move.

## 6. Pick up here (highest-leverage first)
1. Get user go-ahead → run `setup-rulesets.py` (self-draining merge gate).
2. Commit+push the dirty `heal/conductor-restart-2026-06-16` branch.
3. Keep all 6 vendors saturated; drive `EVERY-ASK-LEDGER.md` items to done.
4. Write `docs/PLAN-LONG-AND-WIDE.md` (the multi-horizon plan to ratify).
5. One-container cutover (`container/migrate.sh` S4–S13) under external backup.
6. Surface the 5 `needs_human` atoms as a decision list.

## Only these need the human
card-0186 Santander call · Nelnet recert · `consolidate-github --apply` & `setup-rulesets --apply`
triggers · monetization signups.
