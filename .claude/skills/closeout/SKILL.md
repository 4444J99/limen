---
name: closeout
description: Drive a task to a true closeout — ZERO open or dangling items. Verify ground truth read-only across all owners, close every gap so each owner records its own residual work, reach an idempotent fixed point (re-run = no changes), commit all loose work, and produce a relay handoff. Use when asked to close out, finalize, wrap up, archive, or hand off.
---

# Closeout

A closeout means **ZERO open or dangling items** — no caveats, no "still open" list. Canonical definition: `CLAUDE.md` → Closeout Definition.

## Steps

1. **Verify ground truth (read-only) across all owners.** Fan out parallel read-only explorers — one per repo / component / ledger — each returning a structured packet `{ found, not_found, confidence }`. Merge into one report and flag conflicts. Never guess a location or timeframe; verify each explicitly.
2. **Close every gap.** For each open item, either resolve it now or record it in *its own owner's* record (the repo/ledger that owns it) with the cheapest path to resolution. Nothing parked in a throwaway list.
3. **Reach an idempotent fixed point.** Run the done-predicate (`scripts/verify-whole.sh` or the task's `done.sh`). Re-run until it produces **no changes** and exits 0. If a re-run still mutates state, you are not done — return to step 2.
4. **Commit loose work across all repos.** `git add <path>` explicitly (**never `-A`**); commit; confirm `git status` is clean everywhere you touched. Push staged branches — but leave merges/deploys to Anthony.
5. **Produce a relay handoff.** A concise RELAY/closeout note: what changed, the proof (predicate output), and only the genuinely human-gated remainder — each already recorded in its owner.

## Gate

Do **not** declare closeout until: every owner records its own remaining work, the verification re-runs to a zero-change fixed point, and all loose work is committed. Closeout means ZERO open items.
