# Stop governor: the operator's recurring follow-ups fire without typing (Claude + Codex)

Issue: #3128
PR: #3134

## Context

Operator, 2026-10-19: the point of the command-line studies was to show that however a session starts, what has to
be asked of every session, and repeated, is redundant, and the operator wants slash commands and prompts to just
work without input. The predecessor, `docs/plans/2026-10-18-prompt-control-vocabulary.md` (#3056), ends with the
operator still typing a shorter slash command. This plan is the stronger end state: the follow-up fires itself.

Evidence (`docs/prompt-control-vocabulary-study.md`, section 3, Claude transcripts only): of 1,503 post-opener
turns, the classes CONT 129, CLOSE 127, VERIFY 105, EXPLAIN 56, NEXT 49, STATUS 40, MERGE 30 and REPORT 4 sum to
540 (this plan's own sum of the table; the study's separate figure is ~314 of ~750 typed natural-language turns
being argument-free control, a different denominator). The study does not say these are all typed at the instant
an agent stops; that is the premise this governor tests in shadow. 697 cannot be removed by a hook (HARNESS 422,
SHELL 157, NEWTASK 73, CONVO 45). 266 are only partly addressable (PASTE 108, CORRECT 140, TIER 12, CODIFY 6). SHELL
and STALL are hypotheses here, not coded findings. The system-named commands shipped 2026-10-16 show no invocations
in the study's corpus (the plan #3056 count of 22 is not re-derived here); the operator's own words (`/verify`,
`/closeout`) have hundreds. Hooks cannot type a slash command (Claude hooks docs), so the mechanism fires the
prompt body the command would carry, in the operator's lexicon. The study's table has known soft spots (127 vs 105
and 140 vs 122 count discrepancies between sections) that this plan inherits and does not resolve.

Method: a read-only workflow (7 grounding scouts, 3 independent designs, 3 judges, 1 synthesis; 14 agents), then
the synthesis was checked against the repo and bent where the evidence said so (decisions below).

## Resolved design decisions

- **D1 - one governor at the turn-end boundary.** `scripts/stop-governor.py` is a pure `decide()` over the Stop
  payload, cheap read-only git state and a file ledger, shared by Claude and Codex. It emits at most one
  `{decision: block, reason}` per stop. Beat the alternatives: a typed-command set (the 2026-10-16 names show no use in the corpus), an injected
  end-of-turn contract on every prompt (latency, Codex shows hook context as visible developer messages, recursion
  unverified), a registry with no hook (removes nothing).
- **D2 - shadow first, declared-evidence promotion, and an operator decision is evidence.** Every rule ships
  `mode: shadow` (logs `would_block`, changes nothing). `live` needs a promotion block: declared replay or shadow
  evidence (an ISO date, n >= 30, precision >= 0.80, MERGE >= 0.90, and an existing tracked receipt file) or an
  explicit operator decision citing a GitHub issue or PR URL. The numbers are self-attested: nothing in this repo
  measures them until the follow-up measure tool exists, so the predicate holds the form of the evidence, not its
  truth. This resolves "without my input" against "unmeasured live behavior": the operator can go live with one
  line and a reference, an agent can promote on data, and the predicate refuses a live rule with neither.
- **D3 - the registry is JSON.** The hook runs on whatever python3 the user hook finds; PyYAML may be absent and a
  YAML registry would then silently no-op. `institutio/governance` already holds 17 JSON registries.
- **D4 - project-scope arming, one paste for both vendors.** The synthesis proposed user-scope
  `~/.claude/settings.json`. The governor is limen-scoped, most of this repo's hooks are project-scope (a few, such
  as the Fable guard and the trust hook, are user-scope), and tracked files make arming checkable in CI and
  revertible by PR, so the staged snippet targets `.claude/settings.json` and `.codex/hooks.json`. Arming stays the harness self-modification boundary: lever `L-STOP-GOVERNOR-ARM`, two
  armed-valve rows, `check-stop-governor.py --armed` (reported, never in the exit code).
- **D5 - the Codex Stop fix is its own commit.** `codex-host-admission.py::_stop` emitted
  `{continue: false, stopReason}`, which halts the turn per the openai/codex source (`stop.rs`, `turn.rs`); the
  "one bounded closeout pass" never continued. Now `{decision: block, reason}`; the validator tolerates the legacy
  shape through version skew and rejects `hookSpecificOutput` on Stop. Live only after the installed immutable
  runtime refreshes.
- **D6 - deviations from the judged synthesis, each from a test or a read of the code.**
  1. The send/delete/spend/leak deny filter (66 regex roots) gates CONT only and is best-effort, a lexical filter
     and not a safety boundary. VERIFY, CLOSE and STATUS verify or report and carry the gate clause; NEXT and MERGE
     can act, and rely on that clause plus `merge-policy.sh` (MERGE needs a clean, pushed, non-main branch and a PR
     reference with no hold phrase). Gating the others would silence the completion stops this exists for.
  2. An absent `stop_hook_active` counts as not continuing; `true` or a non-boolean yields. Requiring an explicit
     `false` would make a harness that omits the field a silent, undetectable no-op; loops stay bounded by per-rule
     caps (CONT 2, others 1), the session cap (4) and the daily cap (40). Claude Code documents its own
     continuation ceiling, read through a summarizing fetcher and not observed; Codex documents none, so only the
     repo's caps are proven.
  3. A question outranks a completion word: an agent asking to continue is not finishing. Found by writing the
     fixtures (the synthetic CONT message contained "fixed"). Completion claims are negation-aware.
  4. The fingerprint is vendor-free so one stop yields identical text on both vendors; the claim key is
     per-vendor.
  5. No SessionStart standing-text mode, no per-intent demotion file, no measure script in this PR (below).
  6. The shadow log creates its own directory. The first test run found that nothing did, so no shadow evidence
     would ever have accrued.
  7. One git probe per stop (porcelain v2, 2-3 git calls, `core.fsmonitor=false`, `GIT_*` stripped) after every
     no-I/O check, so a stop that no rule could match pays for no git. The ledger reservation (per-rule, session
     and daily caps plus the claim) is one atomic step under `flock`, fail-open after a one-second wait.
  8. The governor yields on `CLAUDE_CODE_SESSION_ATTENDED=0` (observed on Claude Code 2.1.303 `-p`, undocumented,
     used only to yield) and on the dispatch fleet markers, so headless `claude -p` callers that are not dispatch
     lanes stay quiet. There is deliberately no Codex yield rule: Codex joins multiple Stop handlers' block
     reasons, and its `permission_mode` values are read from source only.
- **D7 - what stays the operator's.** NEWTASK and CONVO/INFO (content only they have), the PASTE payload, harness
  built-ins with no hook path, and every effect that sends, deletes, spends or leaks (`BLOCKED: <atom>` once).

## Steps

1. Done: Codex Stop shape fix, with an A/B against the parent commit (`8089973`).
2. Done: `post-opener-intents.json`, `stop-governor.py`, `hooks/stop-governor.sh`, the `codex-hook-runner.sh` arm,
   `check-stop-governor.py` (letters A-J), the 108-case fixture matrix, `test_stop_governor.py` (302 tests), two
   gates, three parameters, the staged snippet, the lever and the two armed-valve rows. Round-1 adversarial review
   fixes (single probe, atomic reserve, lexicon rebuild, attended variable, deny roots, hermetic arming tests) are
   folded in.
3. Operator: paste the snippet (lever `L-STOP-GOVERNOR-ARM`); the agent commits, opens the PR and merges.
4. Follow-ups (filed on #3128, not done here): `scripts/stop-governor-measure.py` (offline replay over
   transcripts, `effect`, `promote-check`, the misfire breaker and its sensor), because the Claude and Codex
   transcript layouts it parses cannot be read in this container; until it exists the declared-evidence numbers
   are self-attested and the operator-decision route needs nothing. A state-dir GC/prune sensor for the shared
   ledger. An interactive-mode Claude Code run. A live Codex check (two Stop handlers, `permission_mode` values,
   hook trust) before the Codex entry is armed. Widen scope beyond limen checkouts (399 studied turns were
   home/root sessions). Paste-label and standing-context injection (SessionStart / prompt-submit). The unwired
   `claude-workflow-guard.py`. Worktree/registry skew when `CLAUDE_PROJECT_DIR` is a worktree on an older commit.

## Premortem

- **What most plausibly makes this wrong or unwelcome?** The detectors are lexical and the study is Claude-only with
  +-5% heuristic coding. A completion word in a mid-work message would fire VERIFY/CLOSE early. Mitigation: shadow
  first, per-rule caps of 1-2, the gate clause on every text, the file and env kill switches, the CORRECT rate as the
  misfire signal after arming.
- Arming does nothing visible until promotion; the operator may read the quiet as "not working". The lever and
  snippet say so; `--armed` and `events.jsonl` are the proof of life. If `events.jsonl` stays empty after arming,
  check whether the harness sends `stop_hook_active` and `permission_mode` as read.
- One real Claude Code 2.1.303 `-p` run in a throwaway repo (2026-10-19) observed the hook contract: the payload
  fields, `decision: block` continuing the turn as "Stop hook feedback:", and a "Stop hook error occurred" banner
  after a block. That run is `-p` only; interactive Claude Code, `/loop` and background-job behavior are unobserved,
  and the guards for them rest on payload fields and env vars the plan assumes.
- Codex behavior is read from openai/codex main-branch source (developers.openai.com was unreachable): block
  continues, `continue: false` halts, the `permission_mode` enum is {default, acceptEdits, plan, dontAsk,
  bypassPermissions}, and several Stop handlers' block reasons are joined (so the host-admission pass and this
  governor can both speak on one stop; there is no yield rule). The installed Codex build, whether editing the
  runner invalidates persisted hook trust, and live aggregation are unverified. Codex coverage may be zero until
  checked; the governor fails quiet.
- The hook runs on whatever python3 the machine has; the governor parses as Python 3.9 syntax and imports no 3.11
  name (predicate J). A failing interpreter leaves a breadcrumb in `logs/stop-governor/wrapper-errors.log`.
- Other headless `claude -p` callers (for example `scripts/quicken.py`) are not dispatch lanes; they are covered only
  by the `CLAUDE_CODE_SESSION_ATTENDED=0` yield, which is observed on one version and undocumented.
- The Codex half of "the studies in Codex and Claude" is not in this repo: the study is Claude-only. Codex gets a
  trend claim only, after measurement on the operator machine.
- The shared `_memory` project (packet 2026-10-16-v1.1) was not accessible from this session (access denied);
  nothing here relies on it.
- Child agents were not broker-reserved (`limen conduct split` cannot run here: missing dependency, no run to split
  from). Every worker was read-only and explicitly tiered; recorded as a deviation, the same as
  `docs/research/agent-ecosystem-unity/report.md`.

## Verification

- `python3 scripts/check-stop-governor.py` exits 0 (bare), twice; `--armed` reports PARKED until the lever is done;
  `--require-armed` is the lever's acceptance predicate and exits 1 until both vendors are armed and the governor
  runs under this machine's python3.
- `bash scripts/run-pytest-hermetic.sh scripts/tests/test_stop_governor.py cli/tests/test_codex_host_admission_hook.py -q`.
- `bash scripts/verify-scoped.sh` on the exact tree, with failures classified against a pristine `origin/main`
  worktree.
- Observed once, 2026-10-19, Claude Code 2.1.303, `-p` mode, throwaway repo: the Stop payload fields, a block
  continuing the turn, and the error banner above. Not observed: interactive Claude Code, any Codex build.
- Mutation testing of `stop-governor.py` is re-run against the rewritten governor after a clean baseline; the earlier
  count (23 mutants of the first cut) is not carried forward as evidence for this version.
- Status words are separate claims: "merged" = on origin/main; "live" = the paste is in the tracked files and the
  immutable runtime carries the Codex fix; "observed" = a non-shadow decision row from a real session plus a
  promotion PR.
