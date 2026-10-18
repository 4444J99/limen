# Ingest the Claude session corpus into the prompt-atom ledger; derive the post-opener vocabulary from the registry

Harness plan file. Written at the worktree path (`.claude/worktrees/plan-prompt-control-vocabulary/docs/plans/…`)
because the shared-checkout path is refused in a background session; the approval dialog may read the
shared path (`memory/project-plan-mode-worktree-shadow.md`). Step 1 re-homes this as a dated,
issue-chained plan via `scripts/session-plan.py`.

## Context

Goal (operator, 2026-10-18): reduce every prompt after a session's opener to a slash command, because
the words differ while the intention and outcome repeat. A three-corpus study of 178 Claude CLI
transcripts (1,503 post-opener turns) found: ~84% of typed post-opener turns collapse into ~12 intents;
the largest typed class, corrections (~140), restates rules already written in `CLAUDE.md`/`AGENTS.md`
(9 of 15 families); a 22-command agent-neutral set shipped 2026-10-16 (`~/.agents/skills/s-*`, `g-*`,
`m-*`, `v-*`, `tldr`) has **zero** invocations in 179 transcripts while `/verify` and `/closeout` have
hundreds; `/closeout` complaints come 26% of the time when the terminal line is withheld vs 5% when
printed, and in 6 of 8 withheld cases the fix was one turn away.

Operator decision: derive the command set from the registry, not from the hand taxonomy. The registry is
limen's prompt-atom ledger (`.limen-private/session-corpus/prompt-atoms/`, doctrine
`docs/architecture/prompt-corpus-control.md`), whose recurrence tool is `scripts/prompt-recurring-forms.py`.
Blocking fact: the ledger holds **zero** `claude-projects` sessions (cursor `source_families.claude-projects.discovered = 0`,
last native scan `2026-08-21T13:23:49Z`, scope `partial:recent:2`, `all_baseline_complete: false`).
Measured today (read-only): both declared roots are correct (`scripts/prompt-lifecycle-ledger.py:84-85`),
`inspect_source_path_custody` passes for all **181** depth-two session JSONL under the live root
(1,242 MiB; 6 files exceed the 32 MiB `max_source_bytes_per_unit` default, largest 110.8 MiB; hard max 512 MiB),
`--check-cursor` → PASS. So the gap is operational: no scan has run against this checkout since August.

Why no scan: the `prompt-corpus-control` sensor (`sensors.yaml:604`, cadence 4, `--days 2 --max-files 80 --write`)
runs on the heartbeat, which is now a launchd `limen heartbeat --once` every 180 s from the pinned runtime
(`~/.local/share/limen/runtimes/80efee81…/source`, 279 runs, last exit 0). Its latest receipt is
`status: deferred, passed: 0` under host `vitals_action: shed` (swap 0.505, +379 MB/min). That runtime
checkout has **no** `.limen-private/session-corpus/prompt-atoms` root. Hypothesis (medium): when the
sensor does run it resolves `--root` to the runtime source, finds no private root, and fails open
(`severity: silent`). Verified in step 4, not assumed.

## Steps

### 1. Home the study (first, before anything else)
- `scripts/session-plan.py open prompt-control-vocabulary --title "Prompt control vocabulary: ingest Claude corpus, derive post-opener commands"` → prints the exact `gh issue create`; run it on the Bash rail, re-run `open … --issue <N>`. Produces `docs/plans/2026-10-18-prompt-control-vocabulary.md` with `Issue:`/`PR: (pending)` (gate `session-phase`).
- Write the study as `docs/prompt-control-vocabulary-study.md`: the five sections already produced in-session (sequence grammar + totals, intent→phrasing table, same-outcome test, correction→rule families with `file:line`, paste-label taxonomy, closeout-failed loop, registry review incl. the 22-command zero-use finding and the three custody debts). Counts stated with denominators; quotes ≤120 chars, names redacted, no personal-thread quotes. Register one row in `institutio/governance/docs-manifest.yaml`.
- Commit on this worktree branch; push; PR body = plan summary. Merge only after step 6's scoped gate.

### 2. Admission gate (hard precondition for 3–5)
- `python3 scripts/host-work-admission.py status --no-probe` must report `allowed: true`. Today it is `false` (`swap-fraction`, `vitals-shed`). **BLOCKED: host admission** — stated once here; do not poll. The ingest is run by a Sonnet child or a staged script when admission clears, never from this Fable session.

### 3. Byte cap for the 6 oversized sessions
- Edit `docs/prompt-corpus-policy.json` → `resource_limits.max_source_bytes_per_unit: 134217728` (128 MiB; under the 512 MiB hard max). This changes the policy digest recorded in later seals, which is the documented path for a policy edit. Alternative rejected: leaving 6 sessions (`1ecb794a`, `e3ef1593`, `c4ea999a`, `87d23735`, `097f5a46`, `021beb60`; 5–26 turns each) as unsupported gaps would drop ~6% of the corpus silently.

### 4. First Claude baseline scan (from the live checkout, under admission)
```bash
LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/prompt-atom-ledger.py --scan --all --write          # pass 1 (80 units)
LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/prompt-atom-ledger.py --scan --all --write          # pass 2
LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/prompt-atom-ledger.py --scan --all --write          # pass 3 (181 ≤ 240)
python3 scripts/prompt-atom-ledger.py --check-cursor
python3 scripts/prompt-atom-ledger.py --check
```
- `--days 2` reaches nothing from July–October; `--all` is required and is the first baseline. Three bounded passes at the default 80 work units (or one `--unbounded` run only in a quiet window, wrapped by `DomusAgentHost run --` if a `StableAgentHostError` appears, per the verify skill).
- Each pass: read the predicate's own exit code; expect `source_families.claude-projects.converged` to rise and `claude-projects.errors` to stay 0. Codex (27 envelope errors) and agy (26 WAL stalls) are pre-existing adapter gaps, already owner-routed in the cursor; not fixed here.
- Then confirm the sensor mechanism: run the exact sensor command from `~/.local/share/limen/runtimes/<current>/source` with `LIMEN_ROOT` unset and read where it resolves `--private-root`. If it resolves to the runtime source (no private root), file one issue: "prompt-corpus-control sensor resolves private root to the pinned runtime; scans never reach the live ledger". Do not patch the heartbeat in this plan.

### 5. Recurring forms over the Claude corpus
```bash
python3 scripts/prompt-recurring-forms.py --write
python3 scripts/prompt-recurring-forms.py --verify            # exit 0; four invariants
```
- Do **not** use `--candidates`: it requires `MINIMUM_CANDIDATE_PROVIDERS = 2`, so every Claude-only form is excluded by definition. Read `index-all-patterns.jsonl` filtered to `provider == "claude"` (private; identifiers and counts only), rank forms by member count, and compare the top forms to the study's verbatim recurrences (`whats next ostensibly…` ×16, `safe to archive session?` ×16, `status update--what's merged and what's left?`, `percentage complete and status report`, `address all findings:'`, the `salve` sentence).
- Stated limit: `lineage_id` is `stable_id("pl", normalized_text)` (`prompt_corpus.py:889`) — a hash of normalized text. Without `LIMEN_PROMPT_CLASSIFIER_CMD` the registry confirms **verbatim** recurrences; it cannot reproduce semantic families such as CONT (`continue`/`proceed`/`go`/`option 1`). The study's families remain the hypothesis for those; a classifier command is a follow-up, not this plan.
- Output: append a "Registry confirmation" section to the study doc: per verbatim form, registry member count vs study count, with the provider filter stated.

### 6. Verify and land
- `bash scripts/verify-scoped.sh` on the branch (docs + `docs-manifest.yaml` + policy JSON → implicated gates incl. `session-phase`, `check-knowledge-alive` if the policy path is declared). Bare command, own exit code.
- `scripts/merge-policy.sh <PR#>` → 0 CLEARED → `gh pr merge … --squash --match-head-commit <SHA>`; non-deploy paths, no website guardrail.
- `scripts/session-plan.py close prompt-control-vocabulary --pr <N>`.

## Out of scope (filed, not done here)
- Naming the new commands (`/go /status /next /address /explain /codify`) and aliasing/retiring the unused 22 — next plan, after step 5 shows what the registry confirms.
- `/closeout` inherited-red exception clause (8 of 20 complaint cases) — separate fix on the closeout skill (copy A in `4444J99/a-i--skills`, per `docs/plans/2026-10-18-closeout-repo-agnostic.md`).
- Custody debts: `prompt-registry-archive` is the sole copy of `prompt-atoms.json`; its README names a path that no longer holds it — one issue on `4444J99/prompt-registry-archive`.
- Four unwritten rules (Mail.app over Gmail/browser for sends; already-sent dedupe; docs live in their owning repo; deliverables match operator voice) — one `AGENTS.md` correction PR via the `agent-docs` gate.

## Verification (done ⟺ all exit 0)
1. `scripts/check-session-phase.py` passes with the new dated plan.
2. `python3 scripts/prompt-atom-ledger.py --check-cursor` → PASS and `--check` → 0 after the scans; cursor shows `claude-projects.converged ≥ 175` (181 minus any residual byte-cap refusals, each named).
3. `python3 scripts/prompt-recurring-forms.py --verify` → 0; `report-all-patterns.json` `forms` count rises from 33,833 and a provider-`claude` filter of the index is non-empty.
4. Study doc exists at `docs/prompt-control-vocabulary-study.md`, listed in `docs-manifest.yaml`, merged on `origin/main`.
5. Two runs of `bash scripts/verify-scoped.sh` on the final tree, both bare exit 0.
