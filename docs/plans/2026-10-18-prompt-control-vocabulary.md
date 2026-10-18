# Prompt control vocabulary: ingest Claude corpus, derive post-opener commands

Issue: #3056
PR: (pending)

## Context

The operator wants every prompt after a session's opener reduced to a slash command: the words differ while
the intention and the agent's outcome repeat. A read-only study of 178 Claude CLI transcripts (1,503
post-opener turns; `docs/prompt-control-vocabulary-study.md`) found ~84% of typed post-opener turns collapse
into ~12 intents; the largest typed class, corrections (~140), restates rules already written in
`CLAUDE.md`/`AGENTS.md` (9 of 15 families); the 22 agent-neutral commands shipped 2026-10-16 have zero
invocations across all 179 transcripts while `/verify` and `/closeout` have hundreds.

Operator decision: derive the command set from the registry, not from the hand taxonomy. The registry is the
prompt-atom ledger (`.limen-private/session-corpus/prompt-atoms/`; doctrine
`docs/architecture/prompt-corpus-control.md`; recurrence tool `scripts/prompt-recurring-forms.py`). The ledger
holds **zero** `claude-projects` sessions: last native scan `2026-08-21T13:23:49Z`, scope `partial:recent:2`,
`all_baseline_complete: false`. Measured 2026-10-18: both declared roots are correct
(`scripts/prompt-lifecycle-ledger.py:84-85`), `inspect_source_path_custody` passes for all 181 depth-two
session files under the live root (1,242 MiB; 6 files exceed the 32 MiB per-unit default, largest 110.8 MiB),
`--check-cursor` → PASS. The gap is operational: the `prompt-corpus-control` sensor runs on a launchd
`limen heartbeat --once` (180 s) whose latest receipt is `status: deferred` under host `vitals_action: shed`,
and the pinned runtime checkout it runs from has no private prompt-atoms root.

## Resolved design decisions

- **D1 — Registry derives, taxonomy checks.** The study's intent families are the hypothesis;
  `prompt-recurring-forms.py` over an ingested Claude corpus is the predicate. Beat the alternative (name
  commands from the taxonomy now) because the 22 taxonomy-named commands shipped two days earlier have zero
  uses — names that are not lifted from the operator's own turns do not get typed.
- **D2 — Raise the per-unit byte cap to 128 MiB** (`resource_limits.max_source_bytes_per_unit`, hard max 512)
  rather than leave 6 sessions (5–26 turns each) as unsupported gaps; a silent 6% hole is worse than a policy
  digest change on the documented `--write` path.
- **D3 — `--all` baseline in bounded passes**, not `--days 2`: the sensor horizon reaches nothing from
  July–October and no all-history baseline has ever completed.
- **D4 — Do not use `--candidates`**: it requires two providers, which excludes every Claude-only form by
  definition. Read `index-all-patterns.jsonl` filtered to `provider == claude`.
- **D5 — Heartbeat not patched here.** The sensor-root hypothesis is verified and filed as one issue; the
  beat's deferral is host pressure, which this plan does not own.

## Steps

1. Home the study: `docs/prompt-control-vocabulary-study.md` + one `institutio/governance/docs-manifest.yaml`
   row; this plan chained to #3056. Commit on `worktree-plan-prompt-control-vocabulary`, push, open the PR.
2. Admission gate: `python3 scripts/host-work-admission.py status --no-probe` → `allowed: true` before any
   scan. Today `false` (`swap-fraction`, `vitals-shed`). **BLOCKED: host admission** — stated once; the ingest
   runs in a Sonnet child or staged script when admission clears, never from the planning session.
3. `docs/prompt-corpus-policy.json`: add `resource_limits.max_source_bytes_per_unit: 134217728`.
4. From the live checkout, under admission:
   `LIMEN_ROOT=/Users/4jp/Workspace/limen python3 scripts/prompt-atom-ledger.py --scan --all --write` × 3
   (80 work units each; 181 files), then `--check-cursor` and `--check`. Read each exit code bare. Then run the
   exact sensor command from the pinned runtime's `source/` with `LIMEN_ROOT` unset and record where it resolves
   its private root; if it is the runtime source, file one issue.
5. `python3 scripts/prompt-recurring-forms.py --write` then `--verify`; filter the index to `provider == claude`;
   append the "Registry confirmation" section to the study (registry member count vs study count per verbatim
   form; stated limit: `lineage_id` hashes normalized text, so semantic families such as CONT are not
   reproducible without a classifier).
6. `bash scripts/verify-scoped.sh`; `scripts/merge-policy.sh <PR#>` → CLEARED → squash merge with
   `--match-head-commit`; `scripts/session-plan.py close prompt-control-vocabulary --pr <N>`.

Out of scope, each filed to its owner: naming the new commands and retiring the unused 22 (next plan);
the `/closeout` inherited-red clause (closeout skill copy A); `prompt-registry-archive` as sole copy of
`prompt-atoms.json`; the four unwritten rules (Mail.app for sends, already-sent dedupe, docs in their owning
repo, operator voice) as one `AGENTS.md` correction.

## Premortem

- **What most plausibly makes this wrong or unwelcome?** Host admission stays `false` for days and the scan
  never runs, so the "registry confirmation" section stays empty and the command set is named from the taxonomy
  after all — exactly the path that produced 22 unused commands. Mitigation: the study is homed and merged
  regardless (step 1 does not wait on step 4), and the empty section states the gate it is waiting on.
- The registry confirms verbatim repeats only; if the operator expects it to reproduce `continue/proceed/go`
  as one family, D4's stated limit must be read before the names are chosen.

## Verification

- `scripts/check-session-phase.py` → 0 with this plan.
- After scans: `python3 scripts/prompt-atom-ledger.py --check-cursor` → PASS, `--check` → 0, cursor
  `claude-projects.converged ≥ 175` with any byte-cap refusals named.
- `python3 scripts/prompt-recurring-forms.py --verify` → 0; a `provider == claude` filter of the index is
  non-empty.
- `bash scripts/verify-scoped.sh` twice on the final tree, both bare exit 0.
