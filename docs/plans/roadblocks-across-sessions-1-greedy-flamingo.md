# Roadblocks across sessions — one root-to-leaf unblock plan

Issue: #2966 (umbrella issue to be opened by `scripts/session-plan.py open` on plan exit; see Homing)
PR: #3019 (R4), #3020 (R3); R5, R1, R6 pending, R2 is #3011

## Context

The two pasted sessions (Claude "fewer-permission-prompts", Codex "Finish session closeout")
both ended with the session-release predicate unmeasured and `CLOSEOUT COMPLETE` correctly
withheld. They are three sessions' residue, not two: the Codex session was picking up the
closeout of Claude session `021beb60…` (reflexive-observation doctrine, worktree
`docs-reflexive-observation`, now absent) — the very session the hook probe mislabeled `codex`
(#3001). The stalls are independent seams stacked in one pipeline (`scripts/no-tasks-on-me.sh`
→ `cli/src/limen/session_closeout.py`) plus one environmental gate (disk). Verified live
2026-10-18; local `main` is 17 commits behind `origin/main`, so reads of changed files use
`origin/main`.

## Roadblock inventory (evidence → owner → disposition)

| # | Roadblock | Evidence | Owner | Disposition |
|---|-----------|----------|-------|-------------|
| R1 | Limen-launched worktrees denied: `storage-headroom-latched-until-200-gib-free` | `df`: 12 GiB free of 460. `storage_headroom.py`: block <50 GiB, re-enable only ≥200 GiB; latch file `blocked: true`. Gates `inventory_admission.reserve_growth("worktree")` and `repair-checkout`; the harness `EnterWorktree` created a worktree fine this session. | `cli/src/limen/storage_headroom.py`, `docs/substrate-storage-pressure.md` | Cache reclaim alone cannot reach 200 GiB (uv 17G + styx 3.6G + …; `~/Library` 82G and `~/Workspace` 115G unexamined, mostly protected custody). The latch is per-APFS-container, and `/Volumes/Scratch` (150 GiB) / `/Volumes/Archive4T` (1.1 TiB) are independent. **No launcher flag exists for an external destination** (`start-worktree-session.sh:748` hardcodes `$repo/.worktrees/$slug`); the 7 external worktrees were placed by hand. Fix: (a) reproduce which caller emitted the refusal, (b) add one named destination override that feeds the same `reserve_growth` identity, (c) meanwhile `limen repair-checkout --destination /Volumes/Scratch/…` already accepts an external path. Do **not** lower the constants (Green-is-additive). |
| R2 | #3011 census `PermissionError` fix unmerged | PR open; cheap gates + 69 tests green; heavy wave denied (`heavy-lease-held`, pid 36700) | PR #3011 | Run the exact-head `scripts/verify-scoped.sh` heavy wave when the single heavy lease frees; merge on `merge-policy.sh` CLEARED (standing grant, subject to `logs/AUTONOMY_PAUSED`). |
| R3 | `BrokerUnavailable` in isolated agent shell | #2966: broker env only in `~/.limen.env`; shell can't source it | #2966 | Extract the user-owned / mode-600 / not-symlink predicate from `workstream_hydrate_conduct_environment` (`scripts/lib/workstream-capsule.sh:944`) into one Python module that both that path and `client_from_env` import — no second copy. Missing/unsafe file → named blocker, not traceback; test both. |
| R4 | Squash-merged work can't be proven published | #2970: `published()` (`session_closeout.py:94`) proves only `refs/heads/<branch>`; branch auto-deleted on squash; verification heads must be ancestors (`:267`, `:727`) | #2970 | The receipt has no PR number, so choose one: derive via `gh pr list --head <branch> --state merged` (no schema change, preferred) or add a receipt field. Accept merge-commit ancestry of the default tip as proof; reuse the #2928 pattern (`953c0904a`). Also: `merge-base --is-ancestor` failures raise `CalledProcessError`, which `main()` (`:825`) swallows into `status: unmeasured` with **no `reason`** — convert to `Unmeasured` with a reason so the verdict is a named blocker. |
| R5 | No path to a measured verdict for a Claude session | (i) `native_witness` requires Codex `session_meta` rows; (ii) the registration hook (`scripts/hooks/conduct-register.sh`, f152cf758) is wired in `.claude/settings.json` on `origin/main`, but a session loads settings at start — this job started from the shared checkout 17 commits behind, so its loaded settings lack the hook; **live proof:** `$CLAUDE_JOB_DIR/tmp` is empty (no `conduct-register.log`/stamp) after entering a `.claude/worktrees/` cwd. (iii) `evaluate()`/`main()` take the binding only from live `capabilities()["sessions"]`. | #2966 (added scope) | Forward-looking bind path for a *running* session: drive the existing hook script with a synthetic `{session_id, cwd}` payload (it already refuses the default codex bearer) rather than hand-registering. Derive the id scheme from code — what `workstream_register_conduct_session` registers vs. what `no-tasks-on-me.sh --session-id` compares — and test on a throwaway id only. Add a SessionStart orientation warning when the checkout is behind and the hook is absent from loaded settings. |
| R6 | Broker record `021beb60…` pinned as `codex` | #3001: no deregister/relabel in conduct CLI or keeper (`web/worker/src/conduct/keeper.js:450` 409s; succession only by exact owner) | #3001 | Owner-role keeper release for a pinned, unhealthy session + test. Worker deploys on-demand via wrangler — that deploy is the one operator-gated step. |
| R7 | Codex session's attempts: reopen #2989, write scratch script | #2989 is CLOSED with doctrine shipped (#2990/#2993/#2994). `evaluate()` demands an *open* owner only for `disposition=handoff` (`:229`) or `retained_work` entries (`:236-237`); the `021beb60` receipt is `complete`, `retained_work: []`, owner PR #2990 (closed is fine). | — | Do not reopen shipped issues. Before choosing, identify which clause the Codex session actually hit: if `:237`, the fix is naming an open owner (#3001) for retained paths, not reopening; if `worktree_name` (`:166`), the absent `docs-reflexive-observation` needs the scoped (v2) retired-scope/preservation form. Guard-denied scratch-script writes follow the two-denial escalation protocol (one script, dry-run/apply commands). |

## Work order (≤2 implementation lanes, 1 heavy workload; one atomic commit per concern)

0. **Gate check, no mutation:** `scripts/host-work-admission.py status --no-probe` (writer lease
   showed 9 held, `capacity allowed=no (swap-fraction)`) and `logs/AUTONOMY_PAUSED`
   `prohibitions:` (binds interactive merges). Proceed only when both admit.
1. **R2 first** — already built; merging removes the `PermissionError` that masks measurement.
2. **R4, then R3** — separate PRs. R4: `published()` + ancestry + reasoned `Unmeasured`; tests
   in `cli/tests/test_session_closeout*.py` for a squash-merged subject with a deleted branch.
   R3: shared env-ownership module + `client_from_env`; tests for missing/loose-mode file.
3. **R5** — bind-running command/doc + test; hook change only if the id-scheme check shows a
   mismatch; orientation warning for stale-checkout sessions.
4. **R1** — destination override (small, with a test that an external destination is judged by
   its own volume identity).
5. **R6** — keeper release op + test; hand the operator the single wrangler deploy command.
6. **Re-measure — forward-looking, not retroactive.** The predicate binds only to a *live*
   broker record, and both pasted sessions have ended. Their closure form is the explicit-blocker
   receipt they already hold (AGENTS.md: valid closure). R3–R6 make the **next** session measure
   to exit 0; prove that on this session (it is a background job in a `.claude/worktrees/`
   cwd — exactly the hook's trigger) rather than promising to re-measure the dead ones.

## Operator-gated atoms (stated once, filed, not re-surfaced)

- Internal disk reclaim: `~/.cache/uv` (17G, regenerable, `uv cache prune`) and moving verified
  `.limen-private/custody-staging` (20G) to `$LIMEN_CUSTODY_STAGING_ROOT` on an external volume.
  Wipes/moves stay human-gated and custody-verified; file in the existing
  `substrate-storage-pressure` ledger, no new surface.
- Keeper deploy for R6.

## Verification

- Per PR: `scripts/verify-scoped.sh` once on the final tree; A/B against the parent commit
  (`<sha>^`), asserting the failing marker is absent from the baseline.
- R3/R4: real-host A/B (copy of `cli/src` differing only in the fix), as in #3011.
- End state: `scripts/no-tasks-on-me.sh --session-id <id> --receipt <path> --json` exits 0,
  run twice, each read bare (never through a pipe). Report merged / live / observed separately.

## Homing

Plan-phase chain: on exit, `scripts/session-plan.py open <slug> --title "…"` prints the
`gh issue create` for an umbrella issue (R1–R7; #2966 is too narrow), then re-home this file
as `docs/plans/2026-10-18-<slug>.md` on this worktree branch. `check-session-phase.py` currently
passes with the undated harness filename (verified), so no re-name is needed to keep the gate
green; the dated name is for convention and the `Issue:`/`PR:` chain.

## Not doing

Lowering the 50/200 GiB constants, hand-registering a live session with the default bearer,
deleting custody partials, editing `tasks.yaml`, reopening shipped issues, or recreating the
absent worktree.
