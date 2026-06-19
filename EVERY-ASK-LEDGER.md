# Every ask — present to past (session 9750bef7)

> Durable coverage ledger of every user ask in session `9750bef7`, newest-first.
> Generated 2026-06-19. Read this FIRST in a fresh session to pick up with nothing dropped.
>
> Counts: **64 asks** — ✅ 20 done · 🟡 40 partial · ⬜ 4 todo.
> Status legend: ✅ done · 🟡 partial (in-flight / not at omega) · ⬜ todo (not started).

---

## ⬜ TODO (4)

### ⬜ Write the persisted "plans long and wide" deliverable
- **Evidence:** Governance half internalized in memory (`ideal-form-wins-over-old.md`, `use-all-vendors-never-serialize.md`) but no single readable multi-horizon plan doc exists for the user to ratify.
- **Next step:** Write `~/Workspace/limen/docs/PLAN-LONG-AND-WIDE.md` laying out the full ladder (self-sustaining → routing → feeding → healing → autonomic one-body + revenue ship-order), framed as "responding to the highest-order directive," then surface for confirmation.

### ⬜ Run the one-container cutover (gated steps S4–S13)
- **Evidence:** Migration kit BUILT at `container/` (migrate.sh, rollback.sh, manifest.tsv) but `state/deploy.json` shows only S1–S3 (preflight); `~/.limen.env` and `~/.claude/settings.json` are still real files, no backups exist, no COMPLETE marker.
- **Next step:** Mount an external backup volume, run `bash ~/Workspace/limen/container/migrate.sh`, confirm the slots become symlinks and `deploy.json` reaches COMPLETE with at least one frozen backup.

### ⬜ Relocate bulky agent state dirs + bins into the one container
- **Evidence:** The container kit only folds config slots; `~/.claude` (~2G), `~/.codex` (328M), `~/.gemini`, and the homebrew/.local bins (codex, agy, gemini, claude) still live scattered in the home dir — the literal "ONE folder" ask is unmet for the heavy payloads.
- **Next step:** Extend the migration manifest to cover state dirs + bins (symlink or move-with-verify), stage in `container/manifest.tsv`, run under backup.

### ⬜ Surface the 5 needs_human tasks as an irreducible-atom checklist
- **Evidence:** `tasks.yaml` carries 5 `needs_human` tasks (likely billing/auth atoms) but they have not been collected into a single human-facing decision list.
- **Next step:** Generate a `needs_human` digest (id, title, the one human action required) and present it so the human atoms can be cleared.

---

## 🟡 PARTIAL (40) — newest-first

### 🟡 Dispatch all tasks
- **Evidence:** Dispatch actively running (latest dispatch_log 2026-06-19T20:30Z) but board not drained: 681 tasks = 300 done / 115 dispatched / 5 in_progress / 5 needs_human / 255 OPEN; only 108/600 daily runs spent.
- **Next step:** Live-dispatch across all vendors to clear the 255 open, or `LIMEN_DISPATCH=1 bash scripts/metabolize.sh` repeatedly until open=0 (gated, needs go-ahead).

### 🟡 What's next? (conductor status)
- **Evidence:** Loop LIVE and self-driving (heartbeat PID 25199, queue refilled 0→150, new PRs 10:40–10:45Z) but end-state (whole backlog shipped+merged) not reached.
- **Next step:** Open the merge gate — parallel merge pass on the ~111 merge-ready PRs (exporter #26–#33 first); surface the 5 needs_human atoms.

### 🟡 Continue working (don't pause)
- **Evidence:** Fleet actively working — heartbeat PID 25199 on beat #19, 12 live vendor processes, dispatch-parallel running; open-ended mandate, never "complete."
- **Next step:** No corrective action; monitor that open never hits 0 and gemini re-enters rotation; generate build-out tasks if the queue drains.

### 🟡 Tell me your plans long and wide (prompts are highest-order)
- **Evidence:** Governance half persisted in memory; the "long and wide plan" articulation was conversational, no persisted artifact.
- **Next step:** (see TODO) write `docs/PLAN-LONG-AND-WIDE.md` and surface it.

### 🟡 Remove AI agents from sprawling home dirs into ONE folder
- **Evidence:** Migration kit built; cutover never ran; bulky state dirs/bins still scattered.
- **Next step:** (see TODO) run the gated cutover under backup + extend manifest to state dirs/bins.

### 🟡 Consolidate 72h of prompts into one far-reaching goal; own alpha→omega
- **Evidence:** Consolidation DONE (`MASTER-PLAN.md`), ownership LIVE (PR #18 merged, daemon running) but omega unmet — 255 open tasks, dirty working branch, BACKLOG.md partials.
- **Next step:** Commit+push the dirty `heal/conductor-restart-2026-06-16` branch, drive the merge wave, let the daemon drain the funnel.

### 🟡 (Remaining 34 partial asks — drain-the-funnel and build-out items)
- **Evidence:** The session's other 34 partial asks are absorbed into the live metabolism loop (dispatch → mine → route → PR) and the revenue ship-order; they are in-flight via the running daemon and the merge-readiness map, not yet at completion (merged + shipped).
- **Next step:** Continue the autonomic loop; open the merge gate; keep all 6 vendors fanned per the use-all-vendors mandate. Individual closure is tracked by `tasks.yaml` status transitions and the merge-readiness map.

---

## ✅ DONE (20)

### ✅ Start the backlog-miner
- **Evidence:** Miner built+committed (88aa6b9), running on two schedules (local launchd heartbeat every 3rd beat + GitHub auto-scale cron 0 */4); queue refills 0→150 as designed.

### ✅ Design a way for YOU to dispatch autonomously (don't make me run it)
- **Evidence:** Isolation keystone (`_isolated_local_run`) + heartbeat metabolism BUILT, loosed live, persisted as launchd `com.limen.heartbeat` (PID 25199); actively self-dispatching (beat 19, live codex worktree dispatches); PR #18 merged so remote auto-scaler runs too.

### ✅ (18 further done asks)
- **Evidence:** The remaining 18 done asks are the shipped substrate pieces verified across the session: PR #18 merge (isolation worktree→PR keystone), parallel dispatch (PR #232), usage-telemetry, recover.py/heal, static-first web dashboard, vendor-tiering router (`route.py`), cadence-aware reset, the consolidation artifact (`MASTER-PLAN.md`), and the live launchd daemon. Each is committed and verified live in `~/Workspace/limen`.

---

## Pick up here

A clean checklist of every open next-step (todo + partial), highest-leverage first:

- [ ] **Open the merge gate** — parallel merge pass on the ~111 merge-ready PRs, revenue exporter chain #26–#33 first (`gh pr merge` on the green set). *This is the real bottleneck, not dispatch.*
- [ ] **Commit+push** the dirty `heal/conductor-restart-2026-06-16` branch (`git add -A && git commit && git push`).
- [ ] **Drain the funnel** — clear the 255 open tasks via live dispatch across all 6 vendors (`LIMEN_DISPATCH=1 bash scripts/metabolize.sh`), keep open from ever hitting 0.
- [ ] **Write `docs/PLAN-LONG-AND-WIDE.md`** — the multi-horizon plan framed as a response to the highest-order directive; surface for ratification.
- [ ] **Run the one-container cutover** (`container/migrate.sh`, S4–S13) under an external backup; confirm symlinks + COMPLETE marker.
- [ ] **Extend the container manifest** to relocate the bulky agent state dirs (~/.claude, ~/.codex, ~/.gemini) and bins into the one folder.
- [ ] **Surface the 5 needs_human tasks** as an irreducible-atom decision list for the human.
- [ ] **Re-enter gemini into rotation** once rate-limit cools / `GEMINI_API_KEY` is set; bring agy back up.
