# Stop governor: the operator's recurring follow-ups fire without typing (Claude + Codex)

Issue: #3128
PR: (pending)

## Context

Operator, 2026-10-19: the point of the command-line studies was to show that however a session starts, what has to
be asked of every session, and repeated, is redundant, and the operator wants slash commands and prompts to just
work without input. The predecessor, `docs/plans/2026-10-18-prompt-control-vocabulary.md` (#3056), ends with the
operator still typing a shorter slash command. This plan is the stronger end state: the follow-up fires itself.

Evidence (`docs/prompt-control-vocabulary-study.md`, section 3, Claude transcripts only): of 1,503 post-opener
turns, 540 are recurring argument-free asks (CONT 129, CLOSE 127, VERIFY 105, EXPLAIN 56, NEXT 49, STATUS 40, MERGE
30, REPORT 4), each typed at the instant an agent stops. 697 cannot be removed by a hook (HARNESS 422, SHELL 157,
NEWTASK 73, CONVO 45). 266 are only partly addressable (PASTE 108, CORRECT 140, TIER 12, CODIFY 6). The 22
system-named commands shipped 2026-10-16 have zero invocations across the 179 transcripts; the operator's own
words (`/verify`, `/closeout`) have hundreds. Hooks cannot type a slash command (Claude hooks docs), so the
mechanism fires the prompt body the command would carry, in the operator's lexicon.

Method: a read-only workflow (7 grounding scouts, 3 independent designs, 3 judges, 1 synthesis; 14 agents), then
the synthesis was checked against the repo and bent where the evidence said so (decisions below).

## Resolved design decisions

- **D1 - one governor at the turn-end boundary.** `scripts/stop-governor.py` is a pure `decide()` over the Stop
  payload, cheap read-only git state and a file ledger, shared by Claude and Codex. It emits at most one
  `{decision: block, reason}` per stop. Beat the alternatives: a typed-command set (22 unused), an injected
  end-of-turn contract on every prompt (latency, Codex shows hook context as visible developer messages, recursion
  unverified), a registry with no hook (removes nothing).
- **D2 - shadow first, evidence-gated promotion, and an operator decision is evidence.** Every rule ships
  `mode: shadow` (logs `would_block`, changes nothing). `live` needs a promotion block: replay or shadow evidence
  (n >= 30, precision >= 0.80, MERGE >= 0.90) or an explicit operator decision reference. This resolves "without my
  input" against "unmeasured live behavior": the operator can go live with one line and a reference, an agent can
  promote on data, and the predicate refuses a live rule with neither.
- **D3 - the registry is JSON.** The hook runs on whatever python3 the user hook finds; PyYAML may be absent and a
  YAML registry would then silently no-op. `institutio/governance` already holds 17 JSON registries.
- **D4 - project-scope arming, one paste for both vendors.** The synthesis proposed user-scope
  `~/.claude/settings.json`. The governor is limen-scoped, every other hook is project-scope, and tracked files make
  arming checkable in CI and revertible by PR, so the staged snippet targets `.claude/settings.json` and
  `.codex/hooks.json`. Arming stays the harness self-modification boundary: lever `L-STOP-GOVERNOR-ARM`, two
  armed-valve rows, `check-stop-governor.py --armed` (reported, never in the exit code).
- **D5 - the Codex Stop fix is its own commit.** `codex-host-admission.py::_stop` emitted
  `{continue: false, stopReason}`, which halts the turn per the openai/codex source (`stop.rs`, `turn.rs`); the
  "one bounded closeout pass" never continued. Now `{decision: block, reason}`; the validator tolerates the legacy
  shape through version skew and rejects `hookSpecificOutput` on Stop. Live only after the installed immutable
  runtime refreshes.
- **D6 - deviations from the judged synthesis, each from a test or a read of the code.**
  1. The send/delete/spend/leak deny-list gates CONT only. VERIFY, CLOSE, NEXT and STATUS verify or report and carry
     the gate clause; gating them would silence the completion stops this exists for.
  2. An absent `stop_hook_active` counts as not continuing; `true` or a non-boolean yields. Requiring an explicit
     `false` would make a harness that omits the field a silent, undetectable no-op; loops stay bounded by per-rule
     caps (CONT 2, others 1), the session cap (4), the daily cap (40) and the harness's own eight-block cap.
  3. A question outranks a completion word: an agent asking to continue is not finishing. Found by writing the
     fixtures (the synthetic CONT message contained "fixed").
  4. The fingerprint is vendor-free so one stop yields byte-identical text on both vendors; the claim key is
     per-vendor.
  5. No SessionStart standing-text mode, no per-intent demotion file, no measure script in this PR (below).
  6. The shadow log creates its own directory. The first test run found that nothing did, so no shadow evidence
     would ever have accrued.
- **D7 - what stays the operator's.** NEWTASK and CONVO/INFO (content only they have), the PASTE payload, harness
  built-ins with no hook path, and every effect that sends, deletes, spends or leaks (`BLOCKED: <atom>` once).

## Steps

1. Done: Codex Stop shape fix, with an A/B against the parent commit (`8089973`).
2. Done: `post-opener-intents.json`, `stop-governor.py`, `hooks/stop-governor.sh`, the `codex-hook-runner.sh` arm,
   `check-stop-governor.py`, the 57-case fixture matrix, `test_stop_governor.py`, two gates, three parameters, the
   staged snippet, the lever and the two armed-valve rows.
3. Operator: paste the snippet (lever `L-STOP-GOVERNOR-ARM`); the agent commits, opens the PR and merges.
4. Follow-up (filed on #3128, not done here): `scripts/stop-governor-measure.py` (offline replay over transcripts,
   `effect`, `promote-check`, the misfire breaker and its sensor), because the Claude and Codex transcript layouts
   it parses cannot be read in this container. Until it exists no rule can go live on replay evidence; the
   operator-decision route needs nothing.
5. Follow-up: widen scope beyond limen checkouts (399 studied turns were home/root sessions); paste-label and
   standing-context injection (SessionStart / prompt-submit); the unwired `claude-workflow-guard.py`.

## Premortem

- **What most plausibly makes this wrong or unwelcome?** The detectors are lexical and the study is Claude-only with
  +-5% heuristic coding. A completion word in a mid-work message would fire VERIFY/CLOSE early. Mitigation: shadow
  first, per-rule caps of 1-2, the gate clause on every text, the file and env kill switches, the CORRECT rate as the
  misfire signal after arming.
- Arming does nothing visible until promotion; the operator may read the quiet as "not working". The lever and
  snippet say so; `--armed` and `events.jsonl` are the proof of life. If `events.jsonl` stays empty after arming,
  check whether the harness sends `stop_hook_active` and `permission_mode` as read.
- The Claude Stop contract was read through a summarizing fetcher; Codex behavior from main-branch source and search
  relays (developers.openai.com was unreachable). The installed Codex build, Codex `permission_mode` values for
  interactive versus exec lanes, how two Codex Stop handlers aggregate, and whether editing the runner invalidates
  persisted hook trust are unverified. Codex coverage may be zero until checked; the governor fails quiet.
- The Codex half of "the studies in Codex and Claude" is not in this repo: the study is Claude-only. Codex gets a
  trend claim only, after measurement on the operator machine.
- The shared `_memory` project (packet 2026-10-16-v1.1) was not accessible from this session (access denied);
  nothing here relies on it.
- Child agents were not broker-reserved (`limen conduct split` cannot run here: missing dependency, no run to split
  from). Every worker was read-only and explicitly tiered; recorded as a deviation, the same as
  `docs/research/agent-ecosystem-unity/report.md`.

## Verification

- `python3 scripts/check-stop-governor.py` exits 0 (bare), twice; `--armed` reports PARKED until the lever is done.
- `bash scripts/run-pytest-hermetic.sh scripts/tests/test_stop_governor.py cli/tests/test_codex_host_admission_hook.py -q`.
- `bash scripts/verify-scoped.sh` on the exact tree.
- Mutation evidence, each run only after a clean baseline: 23 mutants of `stop-governor.py` (22 caught by the
  fixture matrix, 1 by the Claude/Codex byte-identity check), and the predicate's red paths for a wrong study count,
  a live rule without evidence, an invented lexicon phrase, an uppercase token, a slash command as mechanism, a
  dropped deny-gate, a raised cap, plan or dontAsk mode allowed, a bad snippet and a missing fixture
  (`test_predicate_goes_red_*`).
- Status words are separate claims: "merged" = on origin/main; "live" = the paste is in the tracked files and the
  immutable runtime carries the Codex fix; "observed" = a non-shadow decision row from a real session plus a
  promotion PR.
