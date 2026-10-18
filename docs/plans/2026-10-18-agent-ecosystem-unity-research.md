# Plan: agent ecosystem unity — deep research, tiered, landing through the owners (2026-10-18)

Issue: #2848
PR: (pending)
Status: executed 2026-10-18 — see the Execution record at the end. Written in plan mode on Fable and approved
by the operator; executed after `/model sonnet`.

## Context

Everything this session did — the `.grokbot` doorway, the skills census, the location ledger, the
OpenCode live-database fix — rests on one architecture: a provider-agnostic runtime root
(`$LIMEN_AGENT_RUNTIME_ROOT`) with `$HOME` doorways. Three of its premises turned out wrong once
measured (disjoint skills roots, an owned `vm_bundles`, readers pointed at a frozen database). The
remaining risk is of the same kind: the design assumes each vendor *tolerates* relocation, and that
assumption has never been checked against what vendors document. `/deep-research` was invoked with no
question; the operator's answer to "what should it answer?" was **"agent ecosystem unity"**.

Refined question (what the workers research):

> As of October 2026, what do the coding-agent vendors in this estate (Anthropic Claude Code, OpenAI
> Codex CLI, Google Gemini CLI / Antigravity / Jules, OpenCode, GitHub Copilot CLI, Cursor, Block Goose,
> xAI Grok) **officially support** for relocating or sharing their home directory, instruction files,
> skills, MCP configuration and session state — and which **cross-vendor standards** (AGENTS.md, Agent
> Skills / SKILL.md, MCP, XDG base directories, the Linux Foundation's agentic-AI foundation) are
> converging — so a single runtime root can stand on supported mechanisms instead of symlink
> workarounds? Where a vendor documents nothing, say so; where the estate's observed layout
> contradicts a vendor's documented one, name the contradiction.

## Constraints found during planning (all verified read-only this session)

1. **This session is on Fable with no acceptance receipt.** `LIMEN_FABLE_ACCEPTANCE` is unset and
   `logs/fable-allotment.json` reads `over_cap: true` (stale week stamp, but the only reading there is).
   `docs/fable-allotment.md`: Fable is **plan-only**; building on Fable is a guard violation
   (`scripts/claude-workflow-guard.py` counts Edit/Write and `git add|commit|push`/`gh pr create|merge`
   on a Fable turn as "building on Fable"); subagents never inherit Fable; the guard caps a workflow at
   **1 Opus agent and 0 Fable agents** by default and caps build-from-plan at **sonnet**.
   → This plan is the Fable deliverable. Execution starts with `/model sonnet`.
2. **The stock `deep-research` workflow inherits the session model for every agent.** Workflow
   `agent()` calls inherit the main-loop model unless `model` is passed; the built-in script cannot be
   edited before its first run. → Author an equivalent script inline with an explicit tier on **every**
   agent (the other audiovisual session hit exactly this: "typed agent definitions ran on Fable").
3. **Limen's canonical research surface cannot ingest an in-harness run today.** `limen research
   prepare` selects a profile from the Studium catalog (`organvm/praxis-perpetua`,
   `governance/research-backend-profiles.yaml`, fetched from its canonical remote — no local checkout
   exists); every admissible profile is `manual_handoff` and the code says live automation is
   "deliberately unimplemented". `ingest` additionally requires a `prepare` handoff receipt, a
   source-verifier attestation and a sanitization attestation (shapes: `cli/tests/test_research.py`
   `valid_attestation()` / `valid_sanitization()`; export format: `valid_export()` in the same file —
   the `tests/research-backend/fixtures/valid-export.md` one test names is **not on disk** in this
   checkout, so the helper is the only local authority). → Produce an **ingest-ready bundle** and run
   `prepare` for real; track whatever receipt it emits; never hand-write a `ResearchReceipt`.
4. **Routing rule.** The question is owned by issue #2848 and the v3 plan
   (`docs/plans/2026-10-18-agent-surface-reconciliation-v3.md`, merged `d7723c8db`). Verified
   conclusions land there (append-only, dated); the full report lands in `docs/research/` only through
   `ingest`. No parallel receipt schema, no second plan for the same question.

## Approach

### Step 0 — drop the tier (operator, one keystroke)
`/model sonnet`. Nothing below runs on Fable. (CLAUDE.md: "After plan approval, drop back.")
Approval and the model switch are **two separate operator actions**. After approval, do nothing until
the harness's model line reads Sonnet; if "go" arrives first, refuse Step 1 and say why — one more
Fable turn with a mutation tool is one more guard finding.

### Step 1 — run the tiered research workflow (Sonnet turn)
Invoke `Workflow` with an **inline script** (ultracode is on; `workflow-authoring` already loaded).
Shape, with tiers that satisfy the guard:

| Phase | Agents | Tier / effort | Output schema |
|---|---|---|---|
| Search | 6 angle agents, `pipeline()` into Fetch | `sonnet` / `low` | `{results:[{url,title,why,primary_source}]}` |
| Fetch | one per angle: dedupe its URLs, read top 4–5 sources, extract **falsifiable** claims with a quote | `sonnet` / `medium` | `{claims:[{text,url,source_type,primary_source,quote}]}` |
| Dedupe | plain JS across all claims (genuine cross-item barrier) | — | — |
| Verify | 3 independent skeptics per claim; each **must fetch the cited URL** (and may search for a newer or contradicting source) before voting; verdict ∈ `supported` (quote located at the source), `contradicted` (the source, or a newer one, says otherwise — named), `unverified` (fetch failed or claim not locatable); a claim dies only on **≥2 `contradicted`**; `unverified` goes to `## Unknowns`, never the kill list | `sonnet` / `medium` | `{verdict, reason, quote?, counter_url?, fetched:boolean}` |

Why the three-valued vote: the question is about October-2026 vendor state, past every worker's
training. A refute-by-default skeptic that has not read the page is "uncertain" about anything recent
and true, so it would kill precisely the findings this plan needs. Fetch-before-vote also makes the
Studium attestation honest: `resolvable` and `verification_status` then come from an actual fetch,
which is what that schema asserts.
| Synthesize | **one** writer: export in the Studium format + the two attestations + sources manifest | `opus` / `high` | files written to the bundle dir |

The six angles: (a) per-vendor relocation mechanisms (`CLAUDE_CONFIG_DIR`, `CODEX_HOME`,
`GEMINI_CLI_HOME`, OpenCode/XDG, Copilot, Cursor, Goose, Grok) with doc URLs and version/date;
(b) instruction-file standards and precedence (AGENTS.md spec and adopter list, CLAUDE.md, GEMINI.md,
closest-wins); (c) the Agent Skills spec (SKILL.md), each agent's skills roots, Antigravity
`skills.json`; (d) MCP config surfaces per agent and any shared-location standard; (e) standards
governance and interop (AAIF under the Linux Foundation — MCP, AGENTS.md, goose; ACP; vendor roadmaps
on config unification); (f) XDG and `$HOME` hygiene (which agents honor `XDG_*`; open issues about
dotfile sprawl; macOS Application Support and TCC caveats for symlinked app state).

Hybrid input to Synthesize only: the merged ledger
(`domus-genoma:docs/receipts/2026-10-18-agent-location-ledger.json`) and the v3 plan's cross-provider
matrix, so each vendor finding carries a **documented vs observed** column. Primary source =
vendor docs, vendor repos, the spec's own site. `log()` every drop (sources not fetched, claims killed).
Script rules: plain JS, no `Date.now()`; pass `as_of` via `args`.

### Step 2 — preserve the bundle, run `prepare` for real, file the Studium gap
- Bundle dir: `$LIMEN_CUSTODY_STAGING_ROOT/research-agent-ecosystem-unity-20261018/` (mode 0700):
  `export.md` in the exact Studium shape `valid_export()` encodes — `# Research result`, then
  `## Material Claims` as `- [C<n>][material][evidence][supported|contradicted|unknown] <claim> [S<n>]`,
  `## Contradictions`, `## Unknowns`, `## Negative Searches` (`Query | Surface | Searched: <UTC> |
  Result count | Disposition`, one line per angle that found nothing), `## Novel Actionable Findings`,
  `## Source Manifest` — with `~`-relative paths, no usernames, no prompt bodies; a killed claim is
  recorded under Contradictions with the refuting source, never dropped silently;
  `verification.json`, `sanitization.json` (`export_hash` = sha256 of the exact export), `sources.json`,
  `request.yaml`, and a receipt of what the workflow dropped.
- `request.yaml`: question above; `required_capabilities` as the pilot's; `verification_strength:
  primary_source` (the contract's ratio floor is 0.8 — the Verify stage must reach it or the export
  says so); `preservation_tier: operational_internal`; `external_transmission: public_only`;
  `spend_ceiling.variable_cost: 0`; `output_contract` → `docs/research/agent-ecosystem-unity/report.md`
  + `.receipt.json`, `raw_export_ref: private-owner://limen/research-exports/agent-ecosystem-unity.md`.
- Run `limen research prepare request.yaml --work-dir <bundle>` against the canonical remote catalog
  (no `--profile`: let selection run and record what it rejects; never `--launch`).
  **Expected today: `BlockedReceipt` (no in-harness profile).** Commit that receipt beside the pilot's
  (`docs/research/agent-ecosystem-unity/…receipt.blocked.json`) — the same honest shape the pilot used.
  If it unexpectedly yields a `ManualHandoff`, run `ingest` with the bundle's two attestations and
  `--operator-handling-seconds 0`, and commit the report + receipt it writes.
- File one issue in `4444J99/praxis-perpetua` (the live slug; `organvm/praxis-perpetua` in
  `docs/research-backend.md` is a redirect — private repo, issues enabled, verified 2026-10-18) via
  `gh issue create` on the Bash rail: add an
  `in_harness_agent_workflow` profile so agent-run research with a bound verifier attestation can be
  ingested. Owner: Studium. Not a limen change.

### Step 3 — land the conclusions where the question lives
Append a dated section **"Research findings (2026-10-18): vendor mechanisms and standards"** to the v3
plan: a table — vendor / mechanism documented (URL, date) / observed here / consequence for the ring
model — plus a standards table and the kill list (claims refuted, why). Each row cites its source. Then
re-derive the plan's open items: any vendor-supported relocation that replaces a symlink doorway, any
standard that makes a per-provider skills fan-out unnecessary, and any contradiction that needs a lever.
Ship from a **fresh worktree off `origin/main`** — this worktree's branch merged as #3026, and a commit
stacked on a squash-merged branch conflicts on identical content (e.g.
`git worktree add -b docs/agent-ecosystem-unity-research-20261018 /Users/4jp/Workspace/.limen-worktrees/<slug> origin/main`,
after the writer-lease read; the standing override covers it). Before **any** gate runs in **any**
tree, delete `docs/plans/all-directories-on-flickering-eagle.md`: it is untracked, `verify-scoped.sh`
lists untracked work as changed paths, and `check-session-phase` judges `docs/plans/**`. Its content
lives on as the chain-named plan. Then the normal cadence: `scripts/verify-scoped.sh` → push →
`scripts/merge-policy.sh` → one `merge-drain.py` submission.

## Files

| File | Change |
|---|---|
| `docs/plans/2026-10-18-agent-ecosystem-unity-research.md` | this plan, chain-named (new) |
| `docs/plans/all-directories-on-flickering-eagle.md` | **deleted** before any gate runs (harness plan-mode artifact, untracked) |
| `docs/plans/2026-10-18-agent-surface-reconciliation-v3.md` | append the findings section (never rewrite) |
| `docs/research/agent-ecosystem-unity/*.receipt*.json` (+ `report.md` only via `ingest`) | whatever `prepare`/`ingest` emits |
| `$LIMEN_CUSTODY_STAGING_ROOT/research-agent-ecosystem-unity-20261018/` | untracked bundle, mode 0700, private |
| `organvm/praxis-perpetua` issue | the in-harness profile gap (Studium-owned) |

Reused, not reinvented: `limen research prepare/ingest` (`cli/src/limen/research/`), the attestation
shapes in `cli/tests/test_research.py`, the export fixture, the ledger from domus #509, `ship-docs.sh`
or the worktree PR rail, `merge-policy.sh`, `merge-drain.py`.

## Verification

- Guard: `python3 scripts/claude-workflow-guard.py audit-transcript` (or the beat's audit) shows
  ≤1 Opus agent and 0 Fable agents. It **will** also show this plan file's Write/Edit calls on Fable
  turns — plan mode wrote it, and the guard does not exempt plan mode; that finding is already incurred
  and expected. The criterion is **zero further** mutation tools on any Fable turn after approval.
- Workflow: the journal (`<transcriptDir>/journal.jsonl`) shows every agent's `model` ∈ {sonnet, opus};
  the drop log is non-empty or explicitly "0 dropped".
- Bundle: `shasum -a 256 export.md` equals `sanitization.json.export_hash`; every `claims[].source_ids`
  resolves in `sources.json`; the primary-source ratio is computed and stated.
- `limen research prepare` exit code read bare; its receipt JSON validates against the contract (the
  CLI refuses otherwise).
- `bash scripts/verify-scoped.sh` on the docs tree: cheap wave PASS (`session-phase`,
  `check-plan-decisions`, `check-note-links`, `check-docs-exports`).
- Landing: `git log origin/main -- docs/plans/2026-10-18-agent-surface-reconciliation-v3.md` shows the
  findings commit; `merge-drain` receipt says MERGED; no `result:` before that.

## Not in scope
Changing any vendor's config on this host from the findings (that is the next plan, with its own
levers); editing the Studium catalog (owner: Studium); running the attended Perplexity route (the
operator asked for the in-harness tool).

## Execution record (2026-10-18)

Results and evidence: `docs/research/agent-ecosystem-unity/report.md` and its `evidence/` and `method/`
directories. Where the run departed from the approved text:

| The plan said | What happened |
|---|---|
| One inline workflow | A two-agent pilot first (tiering, read-only agent type, web tools, schema output), then round 1 (6 angles, 103 agents), then a gap-closing round 2 (6 angles, 85 agents). Together about 62 agent-minutes against the 120 doctrine cap |
| Skeptics vote refute-by-default; kill on 2 refutes | Changed on the advisor's review to three-valued fetch-before-vote (`supported` / `contradicted` / `unverified`), kill only on 2 fetched contradictions. All 163 votes recorded `fetched: true`; 0 claims refuted |
| Expected `BlockedReceipt` from `prepare` | `prepare` first crashed with a raw `HTTPError` 404 because the canonical catalog is a private repo (limen#3078); with the catalog fetched via authenticated `gh` and passed as `--catalog`, it returned the expected `BlockedReceipt`. The missing in-harness profile is praxis-perpetua#57 |
| Guard criterion: at most 1 Opus and 0 Fable agents | Met for agents. But the round-2 Opus synthesizer called the `advisor` tool once, which ran one `claude-fable-5-1` iteration (44,911 in / 4,223 out tokens); and the plan-mode writes on Fable were already incurred. Filed as limen#3079 |
| (not in the plan) broker reservation of children | Not satisfiable for read-only in-harness subagents on a direct session; not done; limen#3079 |
| Land the conclusions where the question lives | Findings are in the research report; a digest section is appended to the v3 plan. The synthesis made seven errors, corrected from disk, code and primary sources and listed in the report |

Fable was used for planning only. No host configuration was changed by this plan.
