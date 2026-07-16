# Whole-Estate AI-Agent Insights Review

Generated: `2026-07-16` · Window: 30 days (`2026-06-16` → `2026-07-16`)

## Scope

This is the estate-wide friction/insights synthesis — the companion to
`docs/agent-session-audit-rollup.md` (which covers prompt/session *structure*). This
report covers *friction* across **every** agent surface, not Claude alone: Claude Code,
Codex, OpenCode, Antigravity (the `agy` CLI), Cline, and Jules.

Inputs (all read-only, this session):

- Per-vendor friction packets — tonight's bounded 30-day extraction, counts/patterns only:
  `logs/insight-cross-vendor/{claude,codex,opencode,antigravity,cline,jules}.json` +
  `run-manifest.json` (produced by `scripts/insight-cross-vendor-ingest.py`, PR #1124).
- Claude-side lineage already in-repo: `logs/insights-drift.json` (10 rolling snapshots),
  `censor/insights-suggestions.jsonl` (disposition ledger), `censor/precedents.jsonl`,
  `EVERY-ASK-LEDGER.md`.
- Tonight's Claude-only `/insights` report (Anthropic analyzer, 97–109 sessions).

**PII firewall.** Counts, patterns, percentages, and script/vendor-store-root names only. No
message text, no names, no private file paths, no health/legal/personal content. Each adapter
already derives its signals from session_id/ts/structure, not from prompt bodies.

## Estate Shape (this window)

| Vendor | Sessions | Est. share | Role in the estate | Data quality |
|---|---:|---:|---|---|
| OpenCode | 1,766 | 72.9% | High-volume free-tier bulk lane (board/control-plane churn) | Native SQLite — strong |
| Claude Code | 500* | 20.6% | Governance / orchestration / closeout operator | JSONL substring scan — approximate; cap-limited |
| Codex | 151 | 6.2% | Secondary code lane | History JSONL, id/ts only |
| Antigravity (`agy`) | 4 | 0.2% | Occasional power-user CLI (high slash ratio) | Thin — per-conversation blobs opaque |
| Cline | 1 | <0.1% | Effectively unused | Thin — workspace-count proxy only |
| Jules | 0 | 0% | Dormant (oauth cache only, no session data) | None — estate acknowledged |

*Claude count is capped at 500 by the adapter's scan limit; true count is higher (the Claude
lineage's own `sessions_total` was 1,772 for the overlapping window). Treat Claude 500 as a
**capped sample**, not a census — every Claude *rate* below is a floor.

Estate total (window): **2,422 sessions**. Three-quarters of all agent sessions run on OpenCode's
free tier; Claude is one-fifth by count but carries the governance/closeout load.

## Per-Vendor Profiles

### Claude Code — the operator (capped sample of 500)

- **1,793 tool_result errors** across 500 sessions ≈ **3.6 tool errors/session**; >30% of sessions
  have at least one error (flagged HIGH by the adapter). avg 120.9 turns/session — the long-horizon
  orchestration profile.
- 71 user-correction turns; 24 stall-sessions (few turns relative to transcript size).
- **Friction classes** (from the Claude lineage + tonight's `/insights`): (a) stalling at reversible
  decision points / guessing at already-decided choices; (b) shallow, non-durable first passes needing
  redirection; (c) CI/environment waits blocking closeouts. The **only persisting** friction across the
  last 4 snapshots is *closeout stall loops* (`logs/insights-drift.json` → `recurring`).
- **What works** (positive signal, unchanged 3+ snapshots): closeout discipline, multi-PR cross-repo
  shipping, orchestrated agent fleets, parallel structured-packet fan-out.

### Codex — the secondary code lane

- 151 sessions, avg 8.0 history entries/session (1,205 entries total in window).
- **25 single-entry sessions (16.6%)** — opened and effectively abandoned after one turn. This is the
  Codex analogue of Claude's stall signal, but it manifests as *whole-session abandonment*, not
  mid-session decision-stalling.

### OpenCode — the free-tier bulk lane

- **1,766 sessions, 100% zero-cost** — all on `deepseek-v4-flash-free` (1,445 of them). `total_cost_usd
  = $0.00`. 171.2M input tokens / 3.77M output tokens (input:output ≈ 45:1 — a read/scan-heavy,
  low-generation profile consistent with board/control-plane churn, corroborated by the prior
  `docs/agent-opencode-review.md` finding that `tasks.yaml` is OpenCode's top changed target by a wide
  margin).
- **971 rapid-abandon sessions (55%)** updated within 30s of creation; **6,035 message parts contain an
  `error` substring** (≈3.4/session). The adapter flags "MAJORITY zero-cost — check provider
  connectivity." The most likely reading: a large share of these are **empty/errored/no-op sessions on a
  flaky free provider**, not real work. Volume here is a poor proxy for output.

### Antigravity (`agy`) — occasional power-user CLI

- 4 conversation DBs, 32 history entries, **17 slash-commands (53% slash ratio)** — a deliberate,
  power-user usage pattern, but far too little data for friction inference.

### Cline / Jules — thin / dormant

- Cline: 1 workspace, 20 log lines — a low-ROI adapter by design (Cline keeps session state inside
  VS Code, not in structured files). No friction inference possible.
- Jules: dormant — oauth cache only, no session data. Estate acknowledged; nothing to ingest.

## Cross-Cutting Findings

1. **Session-abandonment is systemic, not Claude-specific — but it wears a different face per vendor.**
   Claude *stalls mid-session* at decision/closeout points (24 stall-sessions; the persisting closeout
   loop). Codex *abandons whole sessions* after one entry (16.6%). OpenCode *rapid-abandons* half its
   sessions inside 30s (55%). The shared root is **starting work without a bound (predicate + scope) that
   lets it finish** — the exact friction the Claude charter already addresses for Claude only. The fix
   generalizes; see disposition D1.

2. **The estate is redundant at the bulk lane, complementary at the top.** OpenCode + Codex overlap
   heavily as code/board lanes (both mutate `tasks.yaml` and dispatch code); OpenCode's 73% volume is
   mostly cheap churn, not distinct capability. Claude is *complementary* — it uniquely carries
   governance, closeout, and cross-repo orchestration. Antigravity/Cline/Jules add negligible marginal
   coverage. **Consolidation opportunity**, not a gap.

3. **OpenCode's 100%-zero-cost fact is the economically important signal.** The tiering policy
   (`cli/src/limen/model_selection.py`, "Haiku-first / never default subagents") already pushes cheap
   work down — OpenCode's free `deepseek-v4-flash-free` lane is that principle taken to its limit: 171M
   input tokens at $0. The caveat is that **free-tier reliability is the hidden cost** — 55% rapid-abandon
   + 6,035 error parts suggest the free provider is dropping a large fraction of sessions. The economics
   win only holds if those abandons are empty/no-op (cheap to lose), not real work (expensive to lose).
   This is a **DATA-GAP** (D-gap-1): the adapter can't yet distinguish "empty errored session" from
   "real work lost to a flaky provider" because it pattern-matches the JSON blob rather than parsing it.

4. **Claude's 3.6 tool-errors/session is the highest-signal follow-up.** 1,793 errors across a *capped*
   500-session sample is a floor, and >30% session-incidence is high. Root-cause hypotheses worth a
   dedicated sensor (D-gap-2): (a) permission/allowlist denials mid-session (the recurring
   root-to-leaf-permission friction — already charter-addressed but not measured as a tool-error rate);
   (b) file-state races in the live checkout (Read-before-Edit misses, daemon-contended runtime files);
   (c) transient network/MCP-bridge failures; (d) speculative tool calls that fail cheaply by design.
   The current adapter counts errors but does not *classify* them — so we can't yet tell a real
   regression from cheap-speculative noise.

5. **The Claude-lineage corrections are already the estate's playbook — they just aren't enforced
   estate-wide yet.** Every standing correction in `censor/insights-suggestions.jsonl` (closeout
   terminality, done-as-predicate, never-over-claim, registry-owns-answer, scoped-verification,
   worktree-commit-enforcement) was authored against Claude sessions and is enforced only on the Claude
   surface. PR #1122 (Session Discipline shared layer + check M) is the vehicle that lifts four of these
   disciplines to a predicate enforced across **all 10 agent surfaces** — which is exactly what findings
   1 and 2 call for.

## Fix Disposition Per Finding

Legend: **ALREADY-OWNED** (shipped owner cited) · **NEW-PROPOSAL** (proposal-only, never auto-armed) ·
**DATA-GAP** (missing adapter/sensor).

### Already-owned (Claude surface) — 6

| # | Finding | Owner (shipped) |
|---|---|---|
| A1 | Closeout stall / premature-done | `scripts/no-tasks-on-me.sh`, `scripts/credential-wall.py`, `.claude/skills/closeout/SKILL.md`, PREC `closeout-terminal` |
| A2 | Shallow first pass | CLAUDE.md §Engage the Real Problem First, PREC `friction-shallow-first` |
| A3 | Stalling at reversible decisions / guessing already-decided | `scripts/ask-gate.py`, PREC `friction-registry-owns-answer` / `ask-already-decided` |
| A4 | CI/env waits blocking closeout | `scripts/merge-policy.sh`, `scripts/merge-drain.py`, `scripts/await-pr.sh` |
| A5 | Scoped verification (not full-suite tax) | `scripts/verify-scoped.sh` + pytest-scope-guard, PREC `scoped-gates` |
| A6 | Passive-blocker vs active-remediation | CLAUDE.md §Standing Autonomy (BLOCKED-once + bridge bootstrap), PREC `friction-blocked-once` |

Tonight's Claude `/insights` proposed four fixes; **all four were found already shipped in limen** for the
Claude surface (rows A3, A5, A1, A4). The gap those disciplines don't yet cover is *cross-vendor* reach —
addressed by the new proposals below via PR #1122.

### New proposals (proposal-only, NOT auto-armed) — 3

These are homed in `censor/whole-estate-insights-proposals.json` alongside this report (see
"Where proposals landed"), shaped like `censor/insights-suggestions.jsonl` entries but kept out of that
ledger because its rows are keyed by Claude-snapshot stamps and are read by `insight-cadence.py`'s
coverage check — cross-vendor proposals would break that join.

- **P1 — Lift the four Claude disciplines to an estate-wide predicate.** Session-abandonment (finding 1)
  is systemic; the disciplines that fix it exist only for Claude. **Delivery vehicle: PR #1122** (Session
  Discipline shared layer + check M, discipline parity across all 10 agent surfaces). Disposition:
  *in-flight* — cite #1122 as owner, do not re-author.
- **P2 — OpenCode/Codex bound-at-start guard.** Require an owner-scope + predicate + expected-receipt
  handshake before an OpenCode/Codex session mutates `tasks.yaml` or code (mirrors the
  `docs/agent-opencode-review.md` "Improvements #1" recommendation and the ask-gate discipline). Reduces
  the 16.6% Codex single-entry and 55% OpenCode rapid-abandon rates by refusing to start unbounded work.
  Proposal-only.
- **P3 — Estate-wide friction sensor in the beat.** Promote `scripts/insight-cross-vendor-ingest.py`
  (PR #1124) to a registered beat sensor in `institutio/governance/sensors.yaml` so the per-vendor
  friction counts refresh every cadence and feed the censor cascade the way `insights-drift.json` already
  does for Claude. Proposal-only — arming is a lever, not an auto-enable.

### Data gaps (missing adapter/sensor) — 2

- **D-gap-1 — OpenCode session classification.** The adapter pattern-matches the SQLite JSON blob and
  cannot distinguish an *empty/errored* zero-cost session from *real work lost to a flaky free provider*.
  Without that, the 55% rapid-abandon / 100% zero-cost numbers can't be read as either "cheap, ignore" or
  "expensive, alarm." Needs a blob-parsing pass (bounded, PII-safe: structure only) that classifies each
  zero-cost session as empty / errored / completed-free.
- **D-gap-2 — Claude tool-error classification.** The adapter counts 1,793 tool errors but does not
  classify them (permission-denial vs file-race vs network/MCP vs speculative-cheap). A follow-up sensor
  should bucket them so a real regression is separable from expected speculative noise — and so the
  charter's root-to-leaf-permission discipline can be *measured*, not just asserted.

## Where Proposals Landed

`censor/insights-suggestions.jsonl` is a **curated** ledger (no organ writes it; `insight-cadence.py` only
*reads* it for coverage-gap detection, joining on Claude-snapshot `reports` stamps). Appending
cross-vendor rows would corrupt that join. Per convention ("never fight a single-writer organ"), the three
new proposals are homed in **`censor/whole-estate-insights-proposals.json`** — a clearly-marked,
proposal-only sidecar shaped like the ledger's entries, not armed, not consumed by any organ. When PR #1122
lands, P1's disposition moves to `implemented` there; P2/P3 stay `proposed` until a lever arms them.

## Residuals (owner-named, not hung on the session)

- **P1** → PR #1122 (in-flight). Owner: that PR + the beat's merge rung (`scripts/merge-drain.py`).
- **P2, P3** → `censor/whole-estate-insights-proposals.json` (proposal-only; arming is a future lever).
- **D-gap-1, D-gap-2** → recorded as data gaps in this report + the proposals sidecar; owner is a future
  adapter revision to `scripts/insight-cross-vendor-ingest.py`.
- Packets (`logs/insight-cross-vendor/*.json`) are **gitignored runtime artifacts** by design (PR #1124);
  their durable summary lives in this tracked report.

## Commands

- Refresh packets: `python3 scripts/insight-cross-vendor-ingest.py` (writes `logs/insight-cross-vendor/`).
- Claude lineage refresh: `python3 scripts/insight-cadence.py --once`.
- Whole-system predicate: `scripts/verify-whole.sh`.

---

## Addendum — 2026-07-16: D-gap-1 and D-gap-2 Classified

*This addendum closes the two data gaps named as residuals in the report above. The ingest script
(`scripts/insight-cross-vendor-ingest.py`) was extended in PR #1126 with bounded, PII-safe
classification passes for both. The packets in `logs/insight-cross-vendor/` were re-run and now
carry the `classification` sub-field on the affected signals.*

### D-gap-1 — OpenCode abandon classification

The 971 rapid-abandon (<30s) sessions break down by structure — no text read, token/message
presence only:

| Class | Count | % of abandons | Interpretation |
|---|---:|---:|---|
| `aborted_after_content` | 518 | 53% | Messages written, no model response — provider dropped the call |
| `completed_fast` | 451 | 46% | Tokens present (avg 32.5K input / 580 output) — model ran, returned quickly |
| `empty_shell` | 2 | <1% | No messages at all — session opened and closed immediately |

**What this changes about the economics conclusion:**

The original report hypothesized that the 55% rapid-abandon rate was mostly empty/errored no-ops
("cheap to lose"). The classification refutes that: **99% of rapid-abandons had user content** (only
2 of 971 were empty shells), and **46% actually reached the model** (451 completed_fast sessions with
non-trivial token counts). The remaining 53% (518 sessions) show the pattern of a provider that
accepted the prompt but dropped the response — the user sent input, the model was not called.

**Revised economics verdict:** The free-tier win is partially valid but materially overstated. The
451 completed-fast sessions are genuine low-cost model calls. The 518 aborted-after-content sessions
represent dropped provider calls where the user paid time but got no output — those are friction
events, not no-ops. The 6,035 error-parts (~3.4/session) likely reflect these same provider drops
surfaced as in-session error messages. "Free tier is a win" holds for cost, not for reliability —
roughly half of rapid-abandon sessions were dropped requests on a flaky provider, not empty throwaways.
The consolidation opportunity (finding 2) is reinforced: if OpenCode's bulk lane drops ~500 sessions/month
to provider flakiness, the marginal value of that lane falls.

**Limits of this classification:** The 30s cutoff is a heuristic; a fast model call could also show
as <30s. The `completed_fast` count may include model invocations that returned errors (not completions).
Token presence is a sufficient proxy for "model was reached," not a sufficient proxy for "model
delivered useful output."

### D-gap-2 — Claude tool-error classification

1,793 `is_error:true` events across 500 sessions, classified by context-window substring scan
(3-line window; counts only):

| Class | Count | % of errors |
|---|---:|---:|
| `network_timeout_mcp` | 495 | 27.6% |
| `other` (unclassified) | 437 | 24.4% |
| `parse_decode` | 256 | 14.3% |
| `bash_exit_nonzero` | 190 | 10.6% |
| `file_not_found_race` | 161 | 9.0% |
| `interrupt_cancel` | 122 | 6.8% |
| `permission_denied` | 132 | 7.4% |

**What this changes about the Claude tool-error follow-up:**

The original report listed four root-cause hypotheses (permission/allowlist, file-state races,
network/MCP, speculative-cheap). The classification resolves the ordering: **network/MCP is the
dominant class (28%)**, not permissions (7.4%). The charter's root-to-leaf-permission discipline
addresses only the 7.4% permission class — valid and shipping, but not the largest driver. The
top-two classes together (network_timeout_mcp + unclassified, 52%) suggest the real floor is
environmental instability, not behavior choices.

The `parse_decode` class (14.3%) is unexpectedly large — these likely reflect MCP tool responses
that don't parse, which would be a second form of the same network/MCP instability.

**Follow-up shape:** The actionable sensor is a MCP-bridge stability signal, not (primarily) a
permission-allowlist audit. The permission rate (132 events, 7.4%) is low enough that the existing
charter allowlist discipline is proportionate to it. The 437 unclassified errors remain a residual
data gap — a one-time manual spot-check of 10–20 representative events would close that class.

**Limits:** Context-window substring scan is approximate. A keyword on a nearby line for an
unrelated reason will misclassify. The 3-line window may miss error text that appears further from
the `is_error` flag. Counts are a floor from the 500-session sample cap.
