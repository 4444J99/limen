# Prompt control vocabulary — study of the operator's post-opener prompts

Date: 2026-10-18. Plan: `docs/plans/2026-10-18-prompt-control-vocabulary.md`.
Goal under study: reduce every prompt after a session's opener to a slash command, on the premise that the
words vary while the intention and the agent's outcome repeat.

All figures are from read-only passes over the Claude CLI transcripts under the shared runtime root
(`.agent-runtime/claude/projects/*/*.jsonl`, top level only; subagent transcripts excluded). Human turn =
`type: user`, not sidechain, not meta, not a tool result, not a harness wrapper (system-reminder,
task-notification, local-command echo), and not an injected relay (another session's message, continuation
capsule, compaction summary). Quotes are verbatim, at most 120 characters, with private individuals and
clients redacted to `[name]`. Personal-thread turns are counted, never quoted.

## 1. Corpus and denominators

| Quantity | Value |
|---|---|
| Project slugs | 85 |
| Top-level session transcripts | 179 (1 `.orphaned` recovery file; 178 sessions; this study's own session excluded) |
| Sessions with ≥1 human turn | 158 |
| Sessions with ≥2 human turns (sequence study) | 129 — limen 81, home/`/`/Workspace 43, other repos 5 |
| Post-opener human turns | 1,503 — limen 1,063, home/root 399, other 41 |
| Slugs with a `MEMORY.md` | 5 of 85 |

Three corpora were coded independently by slug group; a theme recurring in all three is a habit, one in a single
slug is local. Coding was heuristic plus a manual read of truncated turns: treat each cell as ±5%. Four pairs of
limen sessions are resume forks with identical turns and inflate counts slightly. The home/root corpus is a
three-day sprint (2026-10-16 → 10-18); the limen corpus spans July–October.

## 2. The session grammar

With the harness toggles (`/compact`, `/model`, `/effort`) removed, every multi-turn session has the shape

```
OPEN → ( CONT | PASTE | CORRECT | NEXT | STATUS | EXPLAIN )* → VERIFY+ → CLOSE
```

Evidence: `VERIFY>CLOSE` is the most common transition (50 in limen alone, harness removed); `OPEN>VERIFY>CLOSE`
is the most common three-turn session; 45 of 96 limen sessions end on a bare `/closeout`. The failure branch is
`CLOSE>CORRECT` (a closeout that left items hanging) and `CLOSE>CONT` (a closeout that surfaced leftovers; 11
occurrences in the home corpus).

Representative sequences (one line per complete session):

```
limen  6ffc6427  OPEN>VERIFY>VERIFY>CLOSE>VERIFY>CLOSE
limen  1607c1d2  OPEN>PASTE>VERIFY>PASTE>VERIFY>CORRECT>VERIFY>CLOSE
limen  c04eb60f  OPEN>CONT>MERGE×3>CLOSE
limen  cd4ddafd  OPEN>NEXT>STATUS>CONT>CORRECT>CONT>STATUS>CONT×2>STATUS>STATUS>STALL>CORRECT×2>SHELL>STALL>SHELL
home   62527e84  OPEN>VERIFY>NEXT>CONT>MERGE>CONT>EXPLAIN>CONT>MERGE>EXPLAIN>CLOSE
other  8d9c1055  OPEN>NEWTASK>NEXT×3>MERGE>VERIFY>CLOSE>CORRECT>CLOSE>CORRECT>CLOSE
```

## 3. Intent classes and the operator's phrasings

Post-opener turns across all three corpora (n = 1,503).

| Intent | n | Phrasings observed |
|---|---|---|
| HARNESS (already slash) | 422 | `/compact` ×265 · `/model` · `/effort` · `/voice` · `/loop` · `/goal` |
| SHELL (`!` prefix) | 157 | `!gh pr merge … --match-head-commit` · `!chezmoi apply …` · `!git -C …` |
| CORRECT | 140 | `no--…` · `once again, i ask:` · `you do not overwrite plans` · `closeout means closeout, nothing hanging` · `i never said to pause it` · `subagents need to be haiku or sonnet` |
| CONT | 129 | `continue` · `cont` · `proceed` · `go` · `keep going` · `yes full set` · `option 1` · `proceed w ur suggestion` · `you do it` · `fix all` · `get it there` · `full go` |
| CLOSE | 127 | `/closeout` · `safe to archive session?` ×16 · `safe to archive?` · `are we done here?` · `anything left?` · `what remains?` |
| PASTE (label + pasted material) | 108 | `address all findings:'` · `solve for the following:` · `this needs to all be addressed:'` · `heal:` · `debug -` · `from codex for folding in` · `agy` |
| VERIFY | 105 | `/verify` · `were all of the findings healed and addressed?` · `has everything that's been found been patched and repaired?` · `anything strange?` · `check` |
| NEWTASK (new content) | 73 | a genuinely new directive |
| EXPLAIN | 56 | `tldr and eli5` · `tldr/eli5` · `what do i need to do` ×8 · `how do i proceed?` |
| NEXT | 49 | `whats next ostensibly and extensibly alpha to omega/root to leaf re:this-workstream?` ×16 · `what does ideal form logic suggest?` · `what is the salve to heal, expand, evolve towards ideal forms?` · `so where do we go from here?` |
| CONVO/INFO | 45 | personal and interpersonal turns; injected facts (`i cant fix billing for awhile so`) |
| STATUS + STALL | 40 | `whats going on` · `percentage complete and status report` ×5 · `status update--what's merged and what's left?` ×4 · `are all PRs merged?` · `why does it appear as tho nothing is happening?` · `why is this taking so long?` |
| MERGE | 30 | `/ship` · `merge it` · `merge them` · `merge it once checks are green` · `merge it if the baseline passes` · `merge the stack in order` |
| TIER | 12 | `spawn teammates to run the full pass` · `assign all tasks to haiku/sonnet/opus logically--watch token usage` |
| CODIFY | 6 | `every process requires codifying` · `how do we fix it from ever happening again` · `let's make this a hook` |
| REPORT | 4 | `provide a report of all work done in this session` · `full report` |

Of the ~750 typed natural-language post-opener turns: ~314 (42%) are argument-free control, ~322 (43%) need an
argument (the paste, the rule, the question), ~118 (16%) carry new content and cannot be reduced.

Style markers across all corpora: lowercase, dropped apostrophes, `--` as the clause break, a trailing `;`,
`:'` (colon, apostrophe) as the paste delimiter (~20 labels), "bro"/"homie" as address, profanity in about a
quarter of typed turns tied to repetition or slowness.

## 4. Same words, same outcome — the premise tested

For each phrasing variant the agent's next action was read (samples of 1–6 per variant).

| Family | Verdict | What diverged |
|---|---|---|
| NEXT | mostly same | magnitude 0–296 tool calls; 10 of 14 heavy replies were followed by `/compact`; report-only vs act-and-merge in about a third |
| STATUS | same | `percentage` returns a number and table; `what's merged` returns merged/open lists — one question, two facets |
| STALL | mostly same | in every inspected case the cause was the agent's own waiting or granularity |
| CLOSE (typed) | mostly same | `safe/done` → verdict + evidence, then the human leaves (6 of 7); `is any work to be done` → backlog list, then more direction |
| CONT | same in kind | magnitude only; depends on what the prior turn left open |
| VERIFY (typed) | same | `were all findings healed` → honest "No" plus remediation; `anything strange?`/`check` → read-only report and a question back |

Within a family the agent always grounds on live `git`/`gh` state first and answers the same question. The
divergences are size and whether it stops at a report or acts. One hard number: a bare `/closeout` whose reply
ended in `CLOSEOUT COMPLETE` drew a complaint 3 times in 58 (5%); one that withheld the line drew a complaint 6
times in 23 (26%).

## 5. Corrections restate written rules

About 122 correction turns in 43 sessions cluster into 15 rule families. Nine restate a rule already written.

| Family | Sessions | Written rule | Gap |
|---|---|---|---|
| closeout left hanging | 18 | `limen/AGENTS.md:266` N-b, `:355`; `CLAUDE.md:178` | enforcement |
| ungrounded claims / data unread | 11 | `CLAUDE.md:216` data-grounding; `~/AGENTS.md:124` | enforcement |
| handed work back / asked permission | 11 | `~/AGENTS.md:96`; `limen/AGENTS.md:173`; `CLAUDE.md:197`, `:299` | enforcement |
| didn't check the registry | 9 | `CLAUDE.md:197`; `~/AGENTS.md:96` | enforcement (cross-repo partly) |
| "I already told you" | 9 | `limen/AGENTS.md:326` | enforcement |
| waiting / polling / all day | 8 | `CLAUDE.md:380`; `~/AGENTS.md:97`; no-hand-poll hook | enforcement |
| invented constraint / "blocked" | 8 | `CLAUDE.md:309`, `:356` | partial |
| reduce scope | 3 | `~/AGENTS.md:122` | enforcement |
| plan overwritten / dropped | 3 | `CLAUDE.md:139`; `~/AGENTS.md:64` | enforcement; "dropped" uncovered |
| model tier | 3 | `CLAUDE.md:254`; `~/AGENTS.md:138` | enforcement |
| plan-mode edits before plan | 1 | config only (`defaultMode: plan`) | vocabulary |
| wrong tool (Mail.app vs Gmail/browser) | 2 | not written | vocabulary |
| duplicate send / already sent | 3 | guard exists, unarmed | both |
| docs in the wrong repo | 2 | `~/AGENTS.md:98` covers tracking, not ownership | vocabulary |
| voice / deliverable spec | 4 | not written (`voice-enforcement` skill unreferenced) | vocabulary |

A `/correct <rule>` command would only shorten re-quoting the charter; for the nine enforcement families the
reduction is the predicate holding.

## 6. The closeout-failed loop

105 CLOSE turns; 20 followed within two turns by a complaint or "continue".

| Agent behaviour before the complaint | Cases |
|---|---|
| Withheld `CLOSEOUT COMPLETE` because an inherited predicate was red (branch-reap debt, `no-tasks-on-me`, fleet gate), said "owned by X", stopped | 8 |
| Printed `CLOSEOUT COMPLETE` while a visible symptom or open ask remained, or buried it | 6 |
| Listed leftovers, deferred or asked, no action | 4 |
| Interrupted at a permission prompt mid-closeout | 2 (one forked pair) |

In 6 of the 8 withheld cases the agent did the missing fix on the very next turn and then printed the line.
Three complaints are the identical sentence ("This isn't a closeout if you're leaving shit hanging on my head").

## 7. Paste labels

About 106 pastes: 48 labelled, 46 unlabelled, 12 images. Labelled verbs: address 14 · plan/heal 8 ·
from-agent 6 · solve/verify/review/debug 9 · descriptive 8 · image+complaint 8. Unlabelled: ~28 terminal dumps,
~16 other agents' reports. In practice an unlabelled agent report behaves as `address all`; a terminal dump as
`explain`.

## 8. Registry review — `4444J99/prompt-registry-archive` and the live ledger

- The archive is a 4-commit private snapshot of `prompt-atoms.json` (73.8 MB, 24,599 atoms, 2026-05-24). Its
  README names `~/Code/organvm/organvm-corpvs-testamentvm/data/prompt-registry/` as source of truth; that path and
  every other local clone hold no `prompt-atoms.json`. The snapshot is the only copy.
- `BACKLOG-AT-A-GLANCE-2026-05-01.md` reached the same conclusion at larger scale five months earlier: 66.7% of
  14,898 OPEN atoms were pasted repetitions of ~10 canonical asks already promoted to Universal Rules;
  `ATM-003195` "proceed w all suggestions, logic dictates order" ×44 was identified as the literal `/batch`.
- The live successor is limen's ledger (`.limen-private/session-corpus/prompt-atoms/`, 242,692 atoms). Its
  `claude-projects` family shows `discovered 0`: last native scan 2026-08-21, scope `partial:recent:2`,
  `all_baseline_complete: false`. Measured 2026-10-18: both declared roots are correct, custody passes for all 181
  depth-two session files (1,242 MiB; 6 files over the 32 MiB per-unit default), `--check-cursor` PASS. The
  heartbeat (`limen heartbeat --once`, 180 s, launchd) reports `status: deferred` under host shed, and the pinned
  runtime checkout has no private prompt-atoms root.
- A 22-command agent-neutral set shipped 2026-10-16 (domus-genoma #431: `s-00`…`s-09`, `g-*`, `m-*`, `v-*`,
  `tldr`). Invocations across all 179 transcripts: **0**. Control on the same wrapper: `/verify` and `/closeout`
  in the hundreds. `tldr and eli5` was typed 13 times with `/tldr` installed; `whats next…` 16 times with
  `s-00-phase` ("detect current phase and suggest the next command") installed.

## 9. What follows

- Names come from the operator's lexicon: the two commands in his own words are used hundreds of times; the
  22 system-named commands never.
- The command set is derived from `scripts/prompt-recurring-forms.py` once the Claude corpus is in the ledger
  (the plan); the hand taxonomy above is the hypothesis the registry checks. Limit: `lineage_id` is a hash of
  normalized text, so the registry confirms verbatim recurrences, not semantic families.
- Corrections get `closed_via_rule`, not a verb; the `/closeout` inherited-red clause is the single largest
  source and is a predicate fix.
- Four rules need writing for the first time: Mail.app over Gmail/browser for sends; already-sent dedupe; docs
  live in their owning repo; deliverables match operator voice.

## Registry confirmation

_(appended after the Claude baseline scan and `prompt-recurring-forms.py --write`; per verbatim form, registry
member count vs study count, provider filter `claude` stated.)_
