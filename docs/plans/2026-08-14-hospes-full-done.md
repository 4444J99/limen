# HOSPES full completion campaign

Issue: #2401
PR: #2419

## Context

The operator's directive: **"i want to get hospes fully done and complete."** HOSPES
(`organvm/hospes`, private Guest Operations OS for Podcasts) carried 11 open build issues, one
regression, a board row (`GH-organvm-hospes-9`) frozen mid-pilot, and a constellation chain
(`CONST-HOSPES-DOSSIER` / `CONST-CORPUS-REFRESH`) stalled at the broker. "Fully done" per estate
doctrine: every machine-doable lane driven to a verified end by executable predicates, every human
atom filed in its git-tracked owner, board truthful, idempotent fixed point.

## Resolved design decisions

- **D1 — Serial land queue, renumber-at-land.** Twelve PRs all allocated migration numbers at build
  time against a moving `main`; the land queue is the true allocator. Each lander rebases, renumbers
  its migration to the next free slot, and greps for duplicate `def _migration_` names (Python
  last-def-wins silently shadows a duplicate; git merges it cleanly — hit live on PRs #63, #64).
  Beat: parallel landing was rejected because every PR contends on `hospes/migrations.py`.
- **D2 — Conductor/lander division of labor.** Landers are mechanical (rebase → renumber → predicate
  → push → CI → merge attempt) and STOP with a JSON inventory when the `main-pr-only` ruleset refuses
  a merge on unresolved review threads. The conductor alone dispositions threads on the Bash rail:
  one consolidated hardening issue quoting every finding with priority + permalink, pointer replies
  ("resolution here means owned, not dismissed"), `resolveReviewThread` in ≤6-mutation GraphQL
  documents, then the squash merge. Landers never resolve/reply/dismiss, never `--admin`, never push
  fix-commits in response to review comments (estate precedent
  `PREC-2026-08-12-advisory-review-loop-has-no-fixed-point`: an automated reviewer is a generator,
  not a gate).
- **D3 — Residual findings become issues, not pre-merge obligations.** All 118 review-thread findings
  across the queue were preserved verbatim in 12 consolidated hardening issues (hospes#70–#73,
  #76–#78, #80–#83) rather than chased through fix-on-review divergence.

## Steps (as executed)

1. **Track A — board truth.** limen main mirrors the hospes rows; `GH-organvm-hospes-9`'s software
   gate completed (hospes #24, #26, #27, #34 all closed by merged PRs); its `needs_human` transition
   ticket authored into the broker inbox. Landing is blocked by the keeper defect below; the ticket
   was later terminally rejected at relay (see the runtime correction below).
2. **Track B — the 12-PR land queue**, in order, each `done.sh`-green and CI-green before merge:
   #61 (i26, 8b0e18ea) · #62 (i25, 3a261fc3) · #66 (i30, 83c7c6a8) · #63 (i24, b0f3463e) ·
   #64 (i27, efca71ff) · #65 (regression #59, 07162ce9) · #67 (i31, fbfdc669) · #68 (i29, 3ff12066) ·
   #69 (i34, f4f44703, migration 19) · #75 (i33, 673bca24, migration 20) ·
   #74 (i28, 6fd60e59, migration 21) · #79 (i32, b787d58a, migration 22). All 12 source issues
   auto-closed. Final whole-repo `done.sh` re-run on merged main as the fixed-point check.
3. **Track C — eviction closure** (transcript→ARCA): retired as vacuously satisfied, limen PR #2411.
4. **Track D — levers + stale registry surfaces**: completed pre-closeout (registry-owned).
5. **Track E — constellation chain.** Dossier artifact merged (hospes#60, 73f68f8); register dossier
   field + Rule-#4 pointer shipped (limen PR #2419 — the stamped implementing PR). The six broker
   chain tickets were rejected on a claim-agent mismatch, re-authored with `logical_agent: claude`
   (the broker resolves claim agent from `log.logical_agent` → `log.agent` → transport identity, and
   the tasks target claude while the beat relay authenticates as codex), and re-inboxed — later
   terminally rejected again on the same claim-agent 409 (see the runtime correction below: the
   worker binds claims to the authenticated identity, so the re-authoring could not have worked).
6. **Track F — branch disposition**: all session branches merged or retired; landers' worktrees
   removed after each merge.
7. **Track G — this closeout.**

## Premortem

- **What most plausibly makes this wrong or unwelcome?** The board projection lags the truth: the
  keeper's compatibility rail 409s every ticket ("canonical board has no top-level tasks sequence"),
  so `GH-organvm-hospes-9` and the CONST rows will not show their transitions until the keeper is
  repaired. That defect is precisely diagnosed and filed — limen#2374 (comment 5300519810: private
  DO board healthy at 3,111 tasks; the GitHub-text path parses the projection branch's public-shaped
  `tasks: []`, which its block-style regex cannot match), with the fix fork owned by lever #2408
  (`L-BOARD-PARTITION-DECISION`). GitHub itself — the issues and merged PRs above — is the truth the
  board projects; nothing in the campaign's substance is pending on the projection.

## Verification

- Per-PR: `bash done.sh` bare exit 0 in the lander worktree + full CI green (including
  `hospes-done` and `dashboard-quality`) before every merge; merge state verified via
  `gh pr view --json state,mergeCommit`; source issues verified auto-closed.
- Whole-repo: `done.sh` re-run on merged main (`b787d58a`) after the queue drained.
- Session closeout gates: `scripts/no-tasks-on-me.sh` + `scripts/credential-wall.py --check` +
  `bash scripts/verify-scoped.sh` on the shipping branch.

## Residual owners (each item lives in its owner, none on the operator)

- Hardening backlog: hospes#70–#73, #76–#78, #80–#83 (118 findings; the portal issue #81 carries 11
  P1s and is the security-first entry point; the CodeQL stack-trace class spans #82+#83 as one fix).
- Pilot-1 human residue: `GH-organvm-hospes-9` → hospes#9 (Ari review, real slate, human-authorized
  sends, real receipts) — needs_human ticket queued.
- Keeper repair: limen#2374 + lever #2408; release-stale defect limen#2413/#2063; DO quota limen#2054.
- Broker chain: 7 tickets — see the runtime correction below (terminally rejected, not queued).

## Runtime-verification correction (2026-08-15, post-closeout `/verify`)

The closeout's broker-ticket mechanism claim was verified **false** at runtime; everything else
stands. Corrections (full evidence: limen#2374 comment 5302327163):

- The 7 tickets do **not** ride a retry queue: the relay treats keeper 409s as terminal and moved
  all 7 to `logs/tickets/rejected/` with `.reason.txt` receipts. After the keeper repair they must
  be **re-submitted**, not waited on.
- GH-9's rejection (`"canonical board has no top-level tasks sequence"`) freshly corroborates the
  #2374 board-shape diagnosis.
- The six claude-targeted chain tickets hit a second, independent 409: the worker's
  `canonicalClaimAgent` binds the claim agent to the **authenticated transport identity**
  (`event.agent` = the relay's codex token) and never reads the ticket's declared identity — so
  `logical_agent: claude` could never work, and the local CLI check (`tabularius.py:792`, which
  honors the declared identity) was the wrong rail to validate against. The resolution is an
  authorization-design fork filed on #2374, adjacent to lever #2408.
