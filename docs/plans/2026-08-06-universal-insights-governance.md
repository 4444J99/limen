# Universal insights → universal governance: implement all /insights suggestions across every actor

Issue: #1876
PR: (pending)

## Context

Three bodies of insight from one session: the built-in `/insights` Opus report (28 interactive
Claude sessions; 5 rule additions + 3 features + 4 usage patterns — enumeration closed), the audit
of that report (facts confirmed; discrepancies found — 268 vs 32 commits, closeout dominance
22/30, wrong_approach 10 not 8; structural blindness proven: interactive Claude transcripts are
~10–15% of estate activity), and a fresh census of every other lane and desktop store on the host.

The real problem this plan engages: **rules that live only in CLAUDE.md bind one lane of seven+.**
Concretely: codex natively reads AGENTS.md truncated at byte 32,768 of 44,253 (losing the Session
Rituals and its own Agent-Specific Notes); the cross-vendor ingest has been frozen since
2026-07-22 with nothing detecting it; `scripts/vendor-insights.py` implicates no test gate; the
antigravity index samples 15 of ~638 conversations order-biased; and the busiest suggestions from
the Opus report (closeout-means-closeout, no-hand-polling, pipeline-exit-code) exist as Claude
prose, not as covenant + predicate every actor inherits.

## Resolved design decisions

- **D1 — Suggestions land agent-neutrally or mechanically, never as more CLAUDE.md prose.**
  AGENTS.md carries the covenant (rules 6/7 + closure predicate cites + terminal phrase), held by
  new `check-agent-docs.py` phrase-checks Q/R; CLAUDE.md gains pointer clauses only. Beat this
  because a rule stated where only Claude reads it is obedience, not governance.
- **D2 — The codex truncation is fixed on both sides**: raise `project_doc_max_bytes` to 65536 in
  the chezmoi *source* (domus-genoma sibling repo — editing the deployed file is futile), AND make
  the budget mechanical: a declared `instruction_surfaces:` block in gates.yaml with ratcheting
  check S, then pay the debt by stratifying ~15.1KB of doctrine sections to `docs/architecture/`.
  A host cap alone is invisible to CI and other machines; a budget alone leaves this host truncated
  meanwhile.
- **D3 — Antigravity is a three-source union** (summaries ∪ conversation blobs ∪ history,
  keyed by conversation_id; overlap measured at 5/129) — the ledger's original "summaries as
  spine" would silently drop 124 live conversations. PII firewall: structural columns only,
  mechanically tested.
- **D4 — Ingest health rides the existing insight lineage** (packets → insight-cadence →
  insight-route → censor → public issues) as a third ordered step on the *existing*
  `insight-cross-vendor` sensor — no parallel loop, no second sensor. One backward-compatible
  base fix (honor packet-declared owner/severity) is required or findings strand below the
  issue-opening threshold.
- **D5 — Desktop stores are registered honestly, not parsed greedily**: claude.ai LevelDB cache =
  server-side mirror, never opened; ChatGPT `.data` = opaque, counts/sizes/mtimes only; both
  enforced by sentinel tests. The estate must not be silent about a store it cannot read — and
  must not read what it cannot read safely.
- **D6 — Closeout blocking stays asynchronous** (`reconcile-closeouts.py` beat organ; the
  Stop-hook alternative is Claude-only and fights the constant-time SessionEnd design). The
  `LIMEN_SESSION_CLOSEOUT=1` observe-flip is filed as a board task, not flipped here.
- **D7 — Anti-poll ban becomes a mechanical deny on BOTH rails** (`.claude/settings.json` +
  `.codex/hooks.json`): three co-occurring tokens (loop + gh probe + sleep) in one command string;
  fail-open on parse doubt; `await-pr.sh` passes by construction.

## Steps

1. **Branch A `fix/vendor-insights-index-honesty`** — IndexResult + shared `_rank()`, per-adapter
   timestamp fallbacks, opencode window fix, antigravity union, codex `capsule_churn`, `index.json`
   meta block (`total_in_window`, capped, order_key), renderer cap lines, SKILL.md denominator
   doctrine, new `vendor-insights-test` gate row, ~12 tests.
2. **Run-3 waves 1–2** — opencode 90d, copilot 30d, gemini 60d (responses-not-captured framing),
   claude 14d parity, codex re-index; then antigravity 30d/cap 60. Reports delivered as files.
3. **Branch B `feat/vendor-registry-desktop-lanes`** — claude-desktop / chatgpt-desktop /
   vscode-copilot-chat ×2 + cline lane + 3 dormant acknowledgments + dormant-targeting bug fix +
   sentinel PII tests. Wave 3 delivery.
4. **Branch C `feat/cross-vendor-health-sensor`** — `--health` (packet_stale / store_reset /
   retention_horizon / capsule_churn / narrative_lag), `index --all`, insight-cadence
   owner/severity honor, sensor 3 ordered steps + timeout 900 (parity), 6 params, ~12 tests.
   Closeout: terminal-state receipt comment on campaign issue #1571.
5. **Branch D `docs/agents-universal-covenant`** — AGENTS.md +~1.8KB covenant, checks Q/R, loud
   skip for the 8 dead domus-genoma-guarded checks, copilot profile + FLAME.md pointers,
   CLAUDE.md pointer clauses, `PREC-2026-08-06-menu-instead-of-action-is-lane-neutral` appended.
6. **Branch E `chore/agents-byte-budget`** — `instruction_surfaces:` block + check S (ratchet).
7. **Branch F `feat/no-hand-poll-guard`** — hook + deny-matrix test + gate row + param + dual-rail
   wiring (staged handoff if the settings edit is refused).
8. **Branch G `docs/agents-stratify-tier1`** — relocate the nine doctrine sections, pointer stubs,
   ceiling drops toward 32768, check S4 retires the debt.
9. **domus-genoma** (sibling repo, explicit adds): codex cap commit + shell-rule scope commit;
   `chezmoi apply`; empirical codex read check.
10. **Filed items + closeout** — board tasks (LIMEN_SESSION_CLOSEOUT observe-flip; nested-clone
    question), A4 GITVS debt check, R2 harvest, memory codification, final predicates.

## Premortem

- **What most plausibly makes this wrong or unwelcome?** (a) The AGENTS.md stratification (step 8)
  is a whole-file reflow — if inbound references break subtly, the covenant ships but the file
  fractures; mitigation: grep every relocated section name, and the ratchet+board-task fallback is
  pre-declared. (b) The health rung's thresholds are estimates — a noisy first week would train
  the operator to ignore it; mitigation: advisory severity, one aggregate signal, env-tunable.
  (c) `index --all` on the beat widens the standing local PII footprint (gitignored, disarmable
  via the existing gate) — flagged, not hidden. (d) 900s sensor timeout is an estimate; if the
  rung SIGKILLs, shrink the window, don't grow the timeout.

## Verification

- Per branch: `bash scripts/verify-scoped.sh` + the implicated gates run bare (own exit codes):
  `scripts/run-pytest-hermetic.sh cli/tests/test_vendor_insights.py -q`,
  `python3 scripts/check-agent-docs.py`, `python3 scripts/check-sensors.py`,
  `python3 scripts/check-params.py`, `bash scripts/tests/no-hand-poll-guard.test.sh`.
- Whole-system: `scripts/verify-whole.sh` at the fixed point (or pr-gate CI as the sanctioned
  carrier when the heavy lease is held).
- Live proof: `python3 scripts/insight-cross-vendor-ingest.py --health` reports fresh packets
  (the frozen-since-Jul-22 ingest actually cured, not merely detectable);
  `python3 scripts/reconcile-closeouts.py --doctor` green.
- Deliverables: 5 lane reports + 1 newly-registered-lanes summary sent as files; every PR merged
  via `merge-policy.sh` → `await-pr.sh --merge`.

## R2 harvest — run-3 per-lane suggestions, folded at build closeout (2026-08-06)

Each row: what the lane's narrative suggested → its disposition. Nothing here is parked; every
row names a shipped mechanism, a registry owner, or a recorded observation.

| Row | Lane suggestion (run 3) | Disposition |
|-----|------------------------|-------------|
| R2-a | opencode: the 1-second fleet capsule-admission probe and the ~Aug-3 store reset went unnoticed | Branch C `store_reset` check (ring-buffer, 50% drop at base≥20) + `packet_stale` watch it structurally |
| R2-b | copilot: 25h mission self-diagnosed a GitHub secondary-rate-limit and serialized; 11 stubs left unclosed | Serialization already self-applied by the lane; stub-closure discipline is the covenant (AGENTS.md → Full Lifecycle Closure, check Q) — lane-neutral, landed in Branch D |
| R2-c | gemini: dispatch families dark 21 days, zero replies captured | `packet_stale` (3d) + `index_ahead_of_narrative` (7d) checks make a dark lane a beat finding, not a manual-sweep discovery (Branch C); the store's replies-not-captured limit stays a coverage note (R5 doctrine, Branch A) |
| R2-d | claude parity: built-in /insights read 28 sessions where 60 existed in-window; worktree-lockout friction ×3 sessions | Denominator honesty shipped estate-wide as `meta.total_in_window` (Branch A); worktree-lockout friction recorded — owner is the harness (session-scoped worktree binding), not a limen surface |
| R2-e | antigravity: stamp `workspace_uri` at conversation-write time; treat the ~10-day blob horizon as an export deadline; recency views skew toward unsummarized sessions | Vendor-side write-path is not ours to fix — recorded as observation; the horizon became the `retention_horizon` check (14d, Branch C); the skew caveat landed in SKILL.md coverage-note doctrine (Branch A) |
| R2-f | cline: fold the lane into the health sensor and stop hand-reviewing it | Done as designed: state-only indexer with honest zeros (Branch B) + health-sensor standing watch (Branch C) |

A4 disposition check (2026-08-06): `GITVS-UNCAPPED-PR-DEBT-0715` — zero hits in the debt
ledger, censor residuals, and open/closed issues; not recurring, nothing to file.
