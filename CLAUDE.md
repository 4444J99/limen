# CLAUDE.md — Claude Code Operating Charter

Operating discipline for every Claude Code session in this repo. Complements (does **not** duplicate):

- `AGENTS.md` — the dispatch/task contract, Peer Conductor Contract, and receipt rules.
- `GEMINI.md` — Gemini's native transport adapter.

When a rule below also lives in those files, **they are the source of truth** and this charter points to them.
If prose and executable predicates disagree, the executable predicate wins; update the prose to match
the script/schema/code rather than trusting memory.

## Instruction File Maintenance

- `AGENTS.md` owns operating modes, task states, the Peer Conductor Contract, budget semantics,
  safety, and receipt/projection rules.
- `CLAUDE.md` owns Claude-specific execution discipline: session phase entry, closeout, merge
  cadence, credential handling, output style, worktree isolation, and compliant gate reroutes.
- `GEMINI.md` owns only Gemini-specific conduct/MCP transport details.
- `CONTRIBUTING.md` owns human contributor guidance.
- `docs/agent-instruction-standard.md` owns the rationale and cross-surface standard.
- `.github/copilot-instructions.md` is a deliberate **pointer file** (Copilot reads that path
  natively) — it defers to `AGENTS.md` and must never grow into a second rulebook.
- Directory-scoped `AGENTS.md` files (today: `apps/danse/AGENTS.md`) are closest-wins for their
  subtree — more specific, never higher-ranked than the root contract.
- If you change task states, precedence, agent names, referenced scripts, or status examples, update
  `scripts/check-agent-docs.py` in the same change. Do not add a competing instruction file unless a
  new tool requires it; link it back to `AGENTS.md`.

How the agent-instruction files (this charter, `AGENTS.md`, `GEMINI.md`, and the ecosystem-wide `ORGANVM:AUTO` layer) fit together — and why there is no separate "agent-all" repo to build — is settled once in [`docs/agent-instruction-standard.md`](docs/agent-instruction-standard.md). Read it before re-proposing how these files should be standardized.

## Architecture & Orientation

Limen is a **cross-agent, cross-repo, budget-capped task intake system**. TABVLARIVS is the
deterministic state, lease, and budget authority; `tasks.yaml` at `$LIMEN_ROOT` (fallback
`./tasks.yaml`) is its local read-only projection. Every native lane submits bounded work and
receipts through the authenticated conduct broker under `AGENTS.md` → **Peer Conductor Contract**.
Around that kernel are a CLI, a published SaaS surface, and a fleet of self-keeping "organs."

In a direct human-request session, do not claim unrelated queue work. Submit any requested task
transition through the broker; never change the projection directly. `AGENTS.md` → **Operating
Modes** is the authoritative rule.

**The lifecycle and peer-conductor protocol are durable; providers are native adapters.** The
canonical states, transitions, authority attenuation, protected-session rules, and startup
checklist live in `AGENTS.md` and are enforced by `scripts/check-agent-docs.py`. Claude has no
special rank: conductor is a temporary capability. Surfaces are gated by persona (owner / client /
public) via bearer tokens. Firebase hosting serves only public-safe static shells + public
contracts; everything internal loads at runtime from a Cloudflare Worker (or the FastAPI adapter).
Keep the lifecycle + persona-sanction semantics intact and any of Firebase/Cloud
Run/Next.js/FastAPI can be swapped.

**Components** (each owns its remaining work — see [Closeout Definition](#closeout-definition)):

| Path | What it is | Build/run |
|------|-----------|-----------|
| `cli/` | The `limen` CLI (`limen.cli:main`, Click). Core verbs: `dispatch`, `release-stale`, `doctor`, `qa`, `status`, `harvest`, `streams`, plus the `conduct` group (`limen init` is retired — fails closed; the full verb/flag table lives in `README.md`). Logic in `dispatch.py`, `harvest.py`, `capacity.py`, `model_selection.py`, `converge.py`; data shapes in `models.py`; YAML I/O in `io.py`. The autonomic institution lives under `cli/src/limen/vigilia/`. | `pip install -e 'cli[test]'`; tests in `cli/tests/` |
| `web/api/` | FastAPI runtime adapter (`main.py`). Same HTTP contract as the Worker. | `uvicorn main:app` / Docker; tests in `web/api/tests/` |
| `web/worker/` | Cloudflare Worker — the **live** runtime, GitHub-Contents storage. Deploys on-demand via wrangler (not on merge). | `npm run dev` / `npm run deploy`; lint `npm run check` |
| `web/app/` | Next.js dashboard (static export → Cloudflare Pages `limen-dashboard.pages.dev`; the Firebase Hosting step is dormant — its GCP credential exists nowhere, road-not-taken). Surfaces `/` (owner), `/qa`, `/client`, `/public`. | `npm run dev`; `npm run build` (prebuild generates static data + validates surfaces) |
| `mcp/` | MCP adapter exposing the same authenticated conduct protocol and task-compatibility events (`mcp/src/limen_mcp/server.py`). | `pip install -e mcp/` |
| `ianva/` | MCP doorway/aggregator package. | `pip install -e ianva/` |
| `moneta/` | **MONETA** — sovereign Bitcoin licence mint, no processor in the path (see `moneta/README.md`). Gotcha: unconfigured it *pools* demand as `reserved` orders (the valve) and auto-opens them the moment a receive address is set. | `cd moneta && npm test` |
| `spec/contracts/` (incl. `spec/contracts/conduct/`) | Portable JSON Schemas the generated surface contracts must satisfy. | `node scripts/validate-contract-schemas.mjs` |
| `scripts/` (~420 files) | The operational fleet: `metabolize.sh`/`heartbeat-loop.sh` (the beat), `verify-whole.sh` (whole-system predicate), `merge-policy.sh` (merge decision), `organ-health.py` (liveness), `creds-hydrate.py` (credential organ), plus per-organ generators. | run directly |
| `organs/`, `organ-ladder.json`, `pillars.yaml`, `his-hand-levers.json` | Declarative registries: the self-* organ ladder, platform pillars, and the owned human-gated lever registry. | data files |
| `apps/` | Product applications (`danse/`, `vision-board-studio/`). `apps/danse/AGENTS.md` is the one directory-scoped instruction file — closest wins for files under it. | per-app |
| `studium/` | The study/publishing estate (essays, film, music, rubric, ledger) — the repo's largest component by file count; declarative + content, no build gate. | data/content files |
| `censor/` | Insight→correction lineage: `censor/precedents.jsonl` is the precedent registry "the registry owns the answer" queries; mirrored to `censor`-labelled issues by `scripts/sync-censor-issues.py`. | data files |

**Storage modes** (`io.py`): local files are development projections; the authenticated Worker
plus GitHub Contents projection is the durable hosted keeper. Agents never treat a local
`LIMEN_TASKS` file as an independent writer. Persona tokens: `LIMEN_OWNER_TOKEN`/
`LIMEN_API_TOKEN`, `LIMEN_CLIENT_TOKEN`; absent → local owner-scoped dev mode.

**Common commands** (beyond the [CI Gate Matrix](#worktree-isolation--ci-gate-matrix)):

```bash
python -m pytest web/api/tests cli/tests -q          # full test suite
python -m pytest cli/tests/test_dispatch.py -q       # one test file
python -m pytest cli/tests/test_dispatch.py::test_x  # one test
python3 scripts/check-ruff-pin.py && python3 -m ruff check cli/src cli/tests web/api mcp ianva  # lint (config: root .ruff.toml — py311, line-length 120; version pin: cli/pyproject.toml [test])
scripts/verify-whole.sh                              # whole-system predicate (exit 0 ⟺ green)
limen dispatch --agent jules         # dry-run preview; add --live to dispatch for real
```
## Session Phase Entry

**A session opens in the PLAN phase.** `.claude/settings.json` sets `permissions.defaultMode:
"plan"`, so every interactive session in this repo starts read-only, in stage SHAPE, and reaches
BUILD by deciding to — not by default. This is the *entry binding* for the canonical cross-agent
lifecycle declared in `~/.config/ai-context/session-phases.yaml` (`explore → plan → branch → code →
verify → push → wait → review → amend → merge → closeout`), which shipped advisory-only in its
Phase 1 and named this as its Phase-2 gate. Every other phase in that registry remains advisory;
advancing one joint is not a licence to hard-block the lifecycle.

**The fleet is unaffected, structurally.** Headless lanes launch with an explicit
`--permission-mode dontAsk` that `dispatch.py` *validates* before the provider process starts
(`ClaudeLaunchContractError`). A CLI flag outranks a settings default, so no beat rung, scheduled
agent, or dispatched build can be stalled by this. Do not add an exemption mechanism for them.

**"Unless it is illogical" is an exit, not a carve-out list.** A read-only session pays nothing —
it never needs to leave the phase. A genuinely trivial change leaves in one action (`shift+tab`, or
ExitPlanMode). Enumerating exempt session shapes would be hand-maintained prose that decays; the
transcript records every `permissionMode` transition instead, and `scripts/harness-root-probe.py`
already reads that field. The default binds, the exit is cheap, and the exit is observable.

**Session model cadence — open cheap, escalate deliberately.** Interactive sessions OPEN on
Sonnet (the `"model": "sonnet"` pin staged in `docs/keys/fable-guard-settings-snippet.json`,
human-armed via lever `L-FABLE-GUARD-ARM` — an agent never arms settings). The first message —
usually a chaotic brainstorm — is structured into the plan chain *in plan mode on Sonnet*;
`/model opus` is the deliberate escalation for ratifying a genuinely hard plan, and Fable is
never a session default — only an explicit `/model` escalation under a live
`docs/fable-allotment.md` acceptance receipt. After plan approval, drop back (`/model sonnet`)
and execute through the tiered fleet (`.claude/agents/` pins + the `model_selection.py` ladder —
do not restate it here). The harness routes models per *session*, never per message (verified
2026-08-07: hooks cannot switch models), so enforcement is the three real layers: the opening
pin (prevention), `scripts/fable-session-guard.py` at SessionStart (loud warning on Fable
over-cap/unaccepted), and the `claude-workflow-guard.py audit-transcript` beat audit (unaccepted
Fable burn is a violation).

**The opening pin is a default, not a lock — and `/model` overwrites it.** `/model` is manual,
but it is *not* session-scoped: it reports "saved as your default for new sessions" and persists
outside `settings.json` (absent from `~/.claude/settings.json`, `settings.local.json`, and every
plain key of `~/.claude.json` — the store is harness-internal, so no predicate can read it back).
Two consequences, and they run opposite ways. **Cheap:** setting the opening tier costs one
keystroke — `/model sonnet` arms the cadence's prevention layer with no settings paste at all;
the staged snippet's paste is then only needed for the SessionStart guard hook. **Leaky:** one
`/model opus` at any time silently re-arms an expensive default for *every* future session, and
it leaves no artifact a gate can inspect. So prevention is the weakest of the three layers by
construction — detection (SessionStart guard) and the after-the-fact beat audit are what actually
hold the line. Never describe the pin as an enforcement mechanism; it is a good default that a
single keystroke, made months earlier and long forgotten, can invert.
Do not replace plan-mode entry with an auto-mode entry plus a hand-built plan-first hook: plan
mode already *is* that enforcement, and the cost objection dissolves once the opening model is
cheap.

**A plan carries an issue and a PR — via one command.** The `plan` phase's product is not a file,
it is a *chain*: plan artifact → labelled GitHub issue → implementing PR. Open it with

```bash
scripts/session-plan.py open <slug> --title "..." --issue <N>   # plan file + branch + PR
scripts/session-plan.py close <slug> --pr <N>                   # stamp the implementing PR
scripts/session-plan.py audit                                    # chain state for every plan
```

The organ **never writes to GitHub in-process**: `open` without `--issue` prints the exact
`gh issue create` and exits 2, and `close` prints the `gh issue close`, so every outward write stays
on the Bash rail where `PreToolUse` hooks can reach it. That is not ceremony — `check-effectors.py`
Class C failed this organ's first cut for building `gh` argv inside Python, and its baseline is
shrink-only. Do not "fix" a future Class C finding by moving the call into a shell helper: the
scanner walks Python only, so that hides the finding without removing the blindness.

Plans live at `docs/plans/YYYY-MM-DD-<slug>.md` (this repo's home; the canonical registry names
`.claude/plans/`, and the divergence is deliberate — `docs/` is what publishes and what
`check-session-streams.py` reads). Never overwrite a plan; a same-day re-plan is `-v2`. `Issue:` is
the tracked issue; `PR:` is the PR that **implements** the plan — not the PR that ships the plan
document. `PR: (pending)` is a legitimate state between `open` and `close`; a *missing* `PR:` line
is not, because silence about implementation is what let 18 plans accumulate with no answer to
"was this built?".

**The predicate decides — not your memory.** `scripts/check-session-phase.py` (gate `session-phase`
in the GATES registry, so `verify-scoped.sh` runs it on any `docs/plans/**` change) exits `0` ⟺
every non-baselined dated plan declares `Issue: #N` and a `PR:` state. Plans predating the chain are
listed in `institutio/governance/session-plan-baseline.txt` — the same ratchet this registry already
uses six times over. A line leaves that baseline only by retro-fitting a real header, never to
silence a fresh violation.

## Closeout Definition

A *closeout* means **ZERO open or dangling items introduced by this task/session** — never end one with a "but here's what's still open" caveat for work you created or claimed. Before declaring closeout:

1. **Every owner records its own remaining work** — each repo, component, and ledger carries its residual items in its *own* record; nothing is parked in your head or in a single throwaway list.
2. **An idempotent fixed point is reached** — re-running the full verification produces **no changes** (see [Definition of Done](#definition-of-done)). If a re-run still mutates state, you are not done.
3. **All loose work you introduced or touched is committed across every affected repo** — no uncommitted diffs, no stranded branches; `git status` is clean wherever you touched.

If gaps remain, **close them first**, then archive and hand off. A genuinely human-gated item is **filed in its own git-tracked owner** — a lever in `his-hand-levers.json`, or (for any token/secret/login/env atom) the credential organ + Wall #320 — **never recited back to the operator in a closeout, and never appended as a "but also this" tail.** The relay cites the registry and the green predicate; it does **not** enumerate his atoms. He reads owed work in the registry on his own cadence — **a closeout that hands him a list has failed, even when every item is technically homed.** If an atom is *already* filed, that is DONE: do not re-surface it. Likewise a green-but-pending PR is a **homed** item, not a dangling one: its owner is the beat's merge rung (`scripts/merge-drain.py` via `scripts/drain.sh`) — cite that owner and end, or run the one bounded waiter (`scripts/await-pr.sh`); never babysit CI with a hand-rolled watcher shell. When the predicates are green at the fixed point, end with the terminal statement — **"CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items"** — and **stop**: nothing follows it. A closeout that keeps talking past the terminal statement — any caveat tail — has failed. Run `/closeout` to execute this discipline.

Point 1 has a shipped predicate — **`scripts/no-tasks-on-me.sh`** (exit `0` ⟺ nothing hangs on the ephemeral session). It proves every human-gated item lives in the git-tracked registry with a real owner (recall-only memory at `~/.claude/…` is **not** a durable home), that no preserved work is stranded on a local-only `*-staged-*` ref (each must be merged or cited by a lever), and that the registry stays PII-clean (it publishes). Since 2026-08-15 it also reads **working-tree state**, which no arm of it previously did: §11 the session's own worktree is clean and its branch pushed (the live checkout is skipped — `capture.sh` keeps it dirty by design), §12 no orphaned watcher outlives the session, §13 the session left ≥1 durable artifact beyond `logs/` and daemon runtime paths. Estate-wide worktree debt is **reported, never failed** — that is the reaper organ's ledger, and inheriting its backlog would red every closeout for work that is not this session's. Credential/secret atoms live in a **separate** git-tracked home (the credential organ), so the closeout gate is **both** `scripts/no-tasks-on-me.sh` **and** `scripts/credential-wall.py --check` (exit `0` ⟺ every secret in use is homed). Both green ⟺ nothing hangs, and the relay then names the registry, never the atoms. Run them instead of re-auditing ownership by hand each session; a chat audit you have to repeat next session — or a "here's what's still open" list handed to the operator — *is* leaving the discipline hanging on him. The lane-neutral form of this discipline is the closure covenant in `AGENTS.md` → **Full Lifecycle Closure** (check Q); this section is Claude's binding of it.

## Definition of Done

When asked to define "done" or a "goal", deliver an **executable predicate** — a script or test that *verifies* the condition — never hand-maintained prose.

- **Write the predicate first.** Before doing the work, author a `done.sh` (or a test) that checks every concrete completion criterion: tests pass, build green, no dangling items, each owner records its own remaining work. Commit it (durable predicates only — not one-off throwaways; see [Edits Policy](#edits-policy)).
- **It must be self-verifying, runnable, and idempotent.** Exit `0` ⟺ done.
- **Do not claim completion — or write any closeout — until it exits 0.** Run it and summarize the output as proof. If it fails, keep iterating until it passes. If a higher-priority harness rule prevents running it, report the blocker rather than claiming verified completion.
- For whole-system "done" in this repo, the predicate is already shipped: **`scripts/verify-whole.sh`** (lint → compile → contracts → `pytest web/api/tests cli/tests -q` → runtime/worker probes → dashboard build → `git diff --check`; prints `Whole-system verification passed`). A task-level `done.sh` should call it or a scoped subset — `scripts/verify-scoped.sh` is the shipped scoped subset; don't reinvent either.

## Engage the Real Problem First

The insights lineage's most-persistent friction (4 consecutive reports, 2026-05-21 → 2026-07-03):
fixating on trivial mechanics, or offering a menu of reporting options, instead of engaging the
actual design problem — forcing the requester to repeat or reframe until it converges. The standing
correction (censor precedent `PREC-2026-07-04-friction-shallow-first`):

- **Commit to the substantive problem on the first pass.** Name the real objective behind the
  request and work at that altitude; a seemingly trivial chore usually implies the engine behind it
  ("find X" = build the portal that finds X; "import this" = the auto-rebuild engine, not the one
  import; "define done" = the executable predicate, not prose).
- **Deliver executable, durable forms by default** — a predicate, an organ, a register — never
  hand-maintained prose where a runnable check belongs (see [Definition of Done](#definition-of-done)).
- **Options are a decision, not a deliverable.** Pick the reversible best by the cascade
  (protocol → precedent → exploration → ideal-form) and proceed; present alternatives only when a
  genuine human-gated lever forces the choice.
- **The registry owns the answer.** Never ask the operator — or guess — about a fact or framing a
  registry already owns (`his-hand-levers.json`, `organ-ladder.json`, `pillars.yaml`, `tasks.yaml`,
  `censor/precedents.jsonl`): query it and proceed. (Precedent: the "8 vs 10 organs" question was
  asked while `organ-ladder.json` held the count.)

## Never Over-Claim Completion

Do **not** declare work "done" or "fully done" until verified end-to-end:

- **Run the real gates locally**, never from memory: `python3 scripts/check-ruff-pin.py && python3 -m ruff check cli/src cli/tests web/api mcp ianva`, `python -m pytest web/api/tests cli/tests -q`, and `scripts/verify-whole.sh`. (The GATES registry is the command's source of truth — `scripts/verify.py --list`.)
- **Read the predicate's OWN exit code, never a pipeline's.** `predicate | tail` makes `$?` report *tail's* status — which is essentially always `0` — so a gate that printed `FAIL` is read as green. Run the predicate bare and filter a saved copy, or use `${PIPESTATUS[0]}`. (2026-08-05: a closeout reported `EXIT=0` from a `scripts/no-tasks-on-me.sh` run that had printed `FAIL` and truly exited `1`.) The committed scripts get this right; the defect enters through **ad-hoc verification shell**, which is precisely where a false green has no second reader to catch it — so this is a standing behavioral rule, not a lint. (Lane-neutral since 2026-08-06: `AGENTS.md` → Session Discipline rule 6.)
- **Confirm the loop/driver actually runs** — that the entrypoint executes, not merely that files compile.
- **Check for regressions introduced by merges**: dropped imports, dumped/abandoned lanes, silently overwritten files. After any branch reconcile, diff against the prior green state.
- **Reconcile divergent branches against authoritative data** — GitHub redirect/PR state via `gh`, or `scripts/verify-dispatch.py` — never against heuristics or guesses.
- **A/B a change against its own parent commit, never against a branch name.** Once the PR merges, `origin/main` *contains* the change, so `git show origin/main:<file>` silently hands back the fixed file as the "before" — and the A/B compares the fix to itself and passes. The three-dot `git diff origin/main...HEAD` keeps showing a correct diff throughout (it resolves the merge base), so nothing looks wrong. Extract the baseline from `<sha>^` and assert a marker is absent from it before trusting any before/after. (2026-08-07: a post-merge runtime verification's first "pre-fix" extraction was the fixed file.)
- Report status terse and factual: if tests fail, say so with the output; if a step was skipped, say so; call something done only when the predicate proves it.

## Data Grounding

Before drawing ANY conclusion from a dataset — a message export, a mail archive, a review window,
a log trawl — establish the ground truth of the *input* first (case histories behind every rule
here: [`docs/data-grounding-precedents.md`](docs/data-grounding-precedents.md)):

- **Enumerate the CHANNELS before analyzing any one of them.** A missing channel does not widen
  the error bars — it **inverts the conclusion's sign**. Before concluding anything about an
  interaction, a relationship, or a sequence of events, list every channel that could carry it
  (text messages, voice/video calls, a second messaging app, email, transfers, in-person) and
  state in the output which you queried and which you did not (precedent P1). **No scope,
  window, or count check catches this**, because every count *within* the queried channel was
  correct — which is why channel enumeration precedes all of them.
- **State the scope up front, in the output**: the exact date/window boundaries, the direction of
  the records (sent AND received? one side only?), any export filters, and the **total record
  count** — before the first conclusion, so a scope error surfaces immediately.
- **Window = the last human review point, never the last automated run.** An automation's
  timestamp is not evidence a human saw anything.
- **Suspicious-count self-check**: if a count looks too low or too high against the requester's
  stated expectation or the surrounding evidence, treat that as a data-scope bug in YOUR input
  until proven otherwise — re-derive it by a second independent method before presenting.
- **When a file could be a queue or a record, assume RECORD** — verify live sent-state/channel
  state before acting on a file's title or presence.
- **A conversation corpus records SPEECH ACTS, not EVENTS.** "I sent you $150" is evidence that a
  sentence was typed. Ideas floated, contracts drafted, plans proposed, dates agreed and amounts
  negotiated are *conversation* — most are never executed. A claim of the form "X happened"
  sourced only from message text is **asserted-in-conversation**, never **occurred**, unless a
  NON-conversational channel corroborates it: commits, transactions, calendar, filesystem
  artifacts, or the operator. Mark the distinction in the output (precedent P2).
- **A window is not the corpus — never state a sample's finding in the corpus's language.** Report
  the denominator you actually read, next to the denominator that exists, every time. The failure
  is silent and it scales (precedent P3). If the
  full extent is unknown, that is itself the first finding — establish it before analyzing.
- **Corpus retrieval fails silently and looks like absence.** Before concluding a corpus holds
  nothing about a subject, verify the resolver reached a real store: `python3
  scripts/corpus_resolve.py` must name a populated home. The estate has now twice reported "no
  populated corpus" with hundreds of MB on disk (registry header, and again 2026-07-31 from a
  relocated store) — "I found nothing" and "I read nothing" are indistinguishable in the output.
- **On a "since we last reviewed" ask, the PRIOR SESSIONS are one of the channels — and their
  findings live in the assistant's prose, not in their tool results.** Reconstructing the watermark
  from the earlier session's *user prompts* is under-reading it. (2026-08-07: a Charles review did
  exactly that, then reported "Instagram was never read — no export on disk." It had been read, live
  via the Chrome bridge, in that same prior session; the four-phase relationship arc, the lifetime
  money total, and a decisive verbatim exchange were all already established there and had to be
  recovered from the transcript after the operator said "a lot happened in the previous sessions.")
  Browser-read evidence leaves **no artifact on disk** — it survives as screenshots, so grep the
  assistant `text` blocks. Absence of a file is not absence of a reading. Locate the prior work
  (`grep -rli <subject> .agent-runtime/*/projects/*/*.jsonl`), inherit its findings **with
  provenance**, then state only what is new — and write the result to a durable artifact so the next
  session never pays this cost again.
- **A binary or attachment-backed event is invisible to a text dump, and reads as "it didn't
  happen."** Rendering a thread by its text column silently drops every non-text event. (2026-08-07,
  same review: two Apple Cash transfers rendered as `[media]` placeholders and were reported as "no
  money moved in this window" — they had moved, mid-call, six days after the operator said "dont ask
  me for money ever again," which was the single most load-bearing fact in the window.) In
  `chat.db`, payments are `message.balloon_bundle_id LIKE '%PeerPayment%'` with the amount inside
  `payload_data`; enumerate the distinct `balloon_bundle_id` values before trusting any dump, and
  never conclude "no X occurred" from a channel rendered in one modality.

## Edits Policy

- **Prefer minimal in-place edits**, especially during closeouts and cleanups. **Do not create new files unless asked** or genuinely required by the task.
- **Case-insensitive filesystem (macOS):** never let near-identical filenames (`Foo.md` vs `foo.md`) silently overwrite each other or drop a file from a commit — check before writing.
- **Confine edits to your worktree + branch.** Stage explicitly with `git add <path>` — **never `git add -A`** in a live checkout. Do not hand-merge contended `main` or edit daemon-contended runtime files.
- **Merge is a standing grant — Claude merges its own green PRs into `main` without asking** (the routine-merge human-gate is lifted; see [Merge & Branch Protocol](#merge--branch-protocol)). Deploy is *automatic* on merge to `main` for deploy-trigger paths, so the **one guardrail** is the live website: never merge a change that breaks the deployed site/API — a website-sensitive PR requires green CI first. Mass cross-org/fleet merges, sends, wipes, and large spends stay human-gated levers.

## Credentials Are Organ-Owned (Never Recited in Chat)

Tokens, secrets, API keys, logins, env vars are **system burden, not the human operator's** — never recited in a chat or parked as a fresh ad-hoc ask. They have **two registered homes, both on GitHub** (per the directive 2026-06-25 and the pinned Wall, `organvm/limen#320`):

- **The information** lives in code — `scripts/creds-hydrate.py`'s `DEFAULT_MAP` (a NAMED param; override via `LIMEN_CREDS_MAP`). Each entry routes one `op://` source to its sinks: `env` (→ `~/.limen.env`), `file` (tool-native), and/or `gh_secret` (`{repo, name}` → a GitHub Actions secret). Add a vendor = add **one entry**, never a login step; the organ hydrates it every beat + at login (launchd), idempotently, value never printed (behind `_scrub()`). **The `gh_secret` sink self-lands CI secrets the organ used to ask a human to paste** — e.g. `GMAIL_APP_PASSWORD`, which sat as an open lever long after it was already set on `organvm/domus`.
- **The actions** live as the `credential`-labelled issues indexed on the Wall (`#320`) — not invented anew in chat. When a credential need arises: add it to `DEFAULT_MAP` (the organ lands whatever it can) and, if a human atom genuinely remains, it belongs on the Wall, not recited at him.
- **Validity, not presence, is the predicate.** `creds-hydrate --verify` authenticates each cred against its service and exits 1 on a dead one (wired into `metabolize.sh`). A dead credential surfaces **there**, in the beat log — not as a chat task.
- **The only irreducible human residue is a vendor/account MINT the organ physically cannot perform** (for example, creating a replacement credential). Record only the current, evidenced real-world action; a provider error string does not prove a billing cause, and the discharged `L-CARD-FRAUD-HOLD` may never own a later incident by default. `op` stays opt-in: hydration must never trigger an unattended Touch-ID/GUI prompt.

## Output Discipline (Concise Mode)

- Return **summaries, not file dumps.** Report **paths and diffs** — never paste large file contents back.
- **Checkpoint progress every few steps** with short factual status lines; no promotional language.
- Sub-agents return concise structured results, not raw transcripts.

## Parallel Exploration & Fan-Out

For any search or recon whose scope spans multiple domains, **fan out parallel read-only workers — one per distinct domain** (each remote, each local floor, each repo), launched in a single batch.

- **Reserve every child before launch.** Call `limen conduct split` or `conduct_split` before
  invoking Task/Workflow subagents, teams, or any separate capacity. Pass the returned root,
  parent, run, lease generation, task, conductor, and execution-hash identities into the native
  child. Hidden fanout is rejected; native tooling does not broaden the parent's authority.
- Give each worker a **strict read-only scope** and require a **structured packet**: `{ found: [...], not_found: [...], confidence }`.
- **Wait for ALL workers**, then **merge into one ground-truth report that flags conflicts** between packets.
- **Never park the search early, and never guess a timeframe** — verify every location and timeframe explicitly before reporting. Default to ~3 parallel explorers for non-trivial recon.
- **Tier every fan-out agent by job — never let it inherit.** In-harness subagents (the Task tool *and* Workflow `agent()`) default to **the session model**, so a fan-out of trivial workers silently rides the session's Opus (the `verify-studio-launch` incident: six broken-link/typo checks on Opus 4.8). Pick each agent's tier by its job: choose an `agentType` from `.claude/agents/` (`verify`/`scan` → haiku, `synth` → opus) or pass an explicit `model` + `effort`. The frontmatter pin is a **floor, not a cap** — a per-call `model` still escalates a genuinely hard job upward. The class→tier authority is `cli/src/limen/model_selection.py` plus `dispatch._claude_tier_for` (do **not** restate the ladder here); an untiered expensive-tier fan-out is surfaced every session by the `scripts/claude-workflow-guard.py` audit wired into `SessionEnd`.
- **Fable is a reserved tier above Opus, not the new default.** Use it only under [`docs/fable-allotment.md`](docs/fable-allotment.md): a Fable run needs a written `scripts/fable-allotment.py accept ...` command/receipt before it starts, `LIMEN_FABLE_ACCEPTANCE=<receipt>` in the run environment, and a single bounded objective. Retry bumping caps at Opus unless `LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE=1` and that acceptance is present. Untiered Fable/Opus fan-out is blocked by `scripts/claude-workflow-guard.py`.

## Worktree Isolation & CI Gate Matrix

Isolate work in a **git worktree so the live fleet is untouched** (see `GEMINI.md` for the swarm protocol). Then verify before pushing — **scoped to the diff, never the whole world by default**:

**Session streams** (the operator's declared work domains) have their own launcher: `limen streams`
(→ `scripts/open-streams.sh`) opens and **reopens** every openable domain, one tmux window each;
`limen streams --status` shows each stream's derived state. The rows and cartridges are owned by
[`institutio/governance/session-streams.yaml`](institutio/governance/session-streams.yaml) — the
constellation lanes in it are DERIVED from the constellation register (check M holds parity; edit
the register and rerun `organs/consulting/constellation/derive-streams.py --write`, never the rows).

- **`scripts/verify-scoped.sh` is the default push gate.** It maps the changed paths (branch diff vs `origin/main` plus uncommitted/untracked work) to only the gates they implicate, runs those, and names every gate it skipped. A docs append must never pay for a Next.js build, a wrangler boot, and 1,200+ tests.
- **The full matrix below is a pre-merge event, not a per-session tax.** Run it — or let CI run it — only when the diff touches deploy-trigger paths (the website guardrail `merge-policy.sh` enforces at merge time), when scoping cannot attribute the change, or on explicit request.
- **`verify-whole.sh` is machine-serialized** via a lock file (`LIMEN_VERIFY_LOCK_FILE`; opt-out `LIMEN_VERIFY_NO_LOCK=1` for single-purpose CI runners): concurrent runs from parallel sessions wait instead of stampeding the host with simultaneous npm installs, workerd boots, and production builds.

**The gate estate is declared data, not a hand-maintained table.** Every gate — command, implicating paths, cost tier, machine-serialization — lives in [`institutio/governance/gates.yaml`](institutio/governance/gates.yaml) (the GATES registry, the parameter-panel pattern one domain over). `scripts/verify.py --list` prints the live matrix; `scripts/verify.py --changed` is what the scoped wrapper runs; `scripts/verify-whole.sh` remains the whole-system predicate and derives its file lists from the same registry. `scripts/check-gates.py` (wired into pr-gate on every PR) holds the registry to the workflows and consumers — adding a gate = adding **one registry entry**, and a drifted copy anywhere is a red check, not a memory chore.

**The beat sensor estate is declared data too.** The heartbeat's continuous-runtime sensors live in [`institutio/governance/sensors.yaml`](institutio/governance/sensors.yaml) (the SENSORS registry, VIGILIA's third axis beside GATES and PARAMETERS), and `scripts/metabolize.sh` **derives** its whole sensor pass from it via one `scripts/beat-sensors.py --run --source metabolize` call (`--list` prints the matrix; `LIMEN_BEAT_DERIVE=0` skips the pass — an escape hatch; the hand-wired `── 0x ──` blocks are gone). `scripts/check-sensors.py` (wired into pr-gate) holds it in parity with the scripts, the parameter panel, and the beat sources — its D-check accepts the derive-runner call in place of literal gate strings. **Adding a beat sensor = adding one `sensors.yaml` entry** — never a hand-wired shell block. Every consumer that reads a sensor fact derives it from the registry, not the shell: `check-params.py`'s `registry_referenced_tokens`, `armed-valve-audit.py`'s `discover_sensor_valves` (gate + `armed_valve_type`), and `omega.sh`, which derives its registry-declared fixed-point rungs (`omega_eligible`) via `beat-sensors.py --list-omega`/`--run-omega`. Sensor capabilities (`omega_eligible`, `armed_valve_type`, `args_when`, `cadence`/`timeout`) are read by capability, never by sensor id — consumers work unchanged if an id is renamed. See `docs/IDEAL-FORMS-LEDGER.md` → IF-SENSOR-REGISTRY.

- For each failure, **fix root-to-leaf and re-run the implicated gates** — loop until they pass end-to-end (the full matrix only when the diff implicates it). Do not chase one gate green while another regresses.
- **Surface masked failures from dependency bumps** — a green that only passes because a check was skipped or a dependency silently changed behavior.
- **Only after the implicated gates are green locally**, push and open the PR, pasting the green run as proof. **Then merge it yourself** the moment `scripts/merge-policy.sh <PR#>` exits `0` (CLEARED) — that predicate enforces the website guardrail; never merge on a HOLD/BLOCKED. See [Merge & Branch Protocol](#merge--branch-protocol).

## Standing Autonomy & Compliant Gate Reroute

The requesting human's explicit request is authorization to drive reversible work to a verified
end. Do not re-gate routine reversible actions behind "want me to...", "should I...", or "confirm
first" unless the harness or policy requires it. The litmus before any action is one question:
**am I destroying, sending, spending, or irreversibly leaking?** If no, proceed within the active
system / developer / runtime constraints. If yes, surface the irreducible human action with the
cheapest safe path to resolution.

Harness gates are safety controls. Do **not** bypass, disable, or evade them. When a gate blocks a
step, find a compliant alternative path and take it; only the truly irreducible atom gets surfaced.
Concretely, from precedent:

- **Force-push / delete-remote-ref blocked** → never ask the human to force-push or wipe a ref.
  Open a **new branch** and normal-push it as a superseding PR, close the stale one, or rebase onto
  current `main`.
- **`settings.json` / hook-arming blocked** (self-modification boundary) → stage the exact
  validated file, hand the human the one required copy-paste, and do the surrounding branch,
  commit, rebase, push, PR, and merge work yourself.
- **A permission prompt recurs** → broaden the allow rule to the whole class of command
  (root-to-leaf), never re-approve the same literal string one prompt at a time. (Insights
  lineage: a too-narrow allowlist caused 10+ repeat prompts in one session.)
- **A bridge / connectivity / auth check reports blocked** → attempt the documented bootstrap or
  reconnection path once before reporting; a passive re-report of a known-blocked status is a
  parked blocker, not a finding. The Chrome-bridge bootstrap, concretely: `tabs_context_mcp` → if
  no browser attaches, relaunch Chrome (`open -a "Google Chrome"`) and retry once; a background
  job that cannot pair with the extension does not fight it — fall back to headless Playwright
  (token/magic-link URLs carry their own identity), dry-run → screenshot → act, verify via the
  server's observed effect (never the acting session's optimistic DOM), and abort on any captcha.
- **A genuinely human-gated gate is hit** → state **`BLOCKED: <atom>`** exactly **once**, file the
  atom in its registry owner (a lever in `his-hand-levers.json`; credential atoms → the credential
  organ + Wall #320), then leave it — **never loop on, poll, or re-surface a filed gate** — and
  keep driving every other reversible lane to its verified end in the same session.

Never present a reroutable gate as human work. Reduce every blocker to its single irreducible atom
(if any), clear the rest through compliant mechanisms, and report what was done. The
[Merge & Branch Protocol](#merge--branch-protocol) below is the merge-specific instance of this
reflex.

## Merge & Branch Protocol

Authoritative and permanent. Claude **owns the branch cadence and the merge decision** — the requesting human does not have to think about either. This realizes the cascade *protocol → precedent → exploration → ideal-form*: the protocol is below; the executable predicate **`scripts/merge-policy.sh`** is the ideal-form that decides each case by logic, never by memory.

**Branch cadence.** Never commit to `main` directly. Every change is a topic branch, isolated in a worktree, named by intent:

| Prefix | For |
|--------|-----|
| `feat/` | new capability |
| `fix/` | bug / regression fix |
| `heal/` | reconcile a divergence or a self-healed regression |
| `chore/` | tooling, deps, config |
| `docs/` | docs / memory / charter only |
| `refactor/` | behavior-preserving restructure |
| `worktree-*` | auto-named isolation branches (fleet / bg jobs) |

One PR per branch → `main`. Squash-merge; branch cleanup is a separate receipt-backed reap, not an
automatic delete. `main` is the trunk **and** the live deploy source.

**Chunking.** A branch is **one concern, not one session.** When a session produces multiple concerns, cut a fresh branch per concern off `origin/main` — finish → push → PR → next branch — never accumulate heterogeneous commits on a single session branch. And the **live checkout rests on `main`**: parking it on a work branch pins the running fleet to stale code and entangles every autonomic capture into that branch (the 2026-06-29 jules-capfill park: 5 days, 65 behind, a feature slice + daemon receipts fused onto one ref). `scripts/sync-release.sh` auto-unparks a fully-pushed, clean park each beat and fails open loudly otherwise — do session work in a worktree, never in the live checkout.

**Settling a session stream.** If a PR completes a domain declared in
[`institutio/governance/session-streams.yaml`](institutio/governance/session-streams.yaml), claim it
with an anchored trailer at **column 0** of the merge commit message — `Settles: <stream-id>` (comma-separated
for several). That claim is the *only* thing that marks a domain settled, and the claiming commit must
change something outside the registry and `docs/{plans,continuations}/`: bookkeeping records an outcome,
it cannot produce one. A passing mention no longer counts — the old unanchored `git log --grep=<id>` rule
settled `s10-axis-coverage` off a docs commit whose whole subject was that s10 owns work a plan should
*not* do. `scripts/check-session-streams.py` is the predicate.

**No side doors — docs included.** The branch cadence applies to *every* tracked change, including
one-file docs appends (the `docs: review … run` class, which was landing as direct `main` commits —
35 of 40 at its worst). Ship those with **`scripts/ship-docs.sh <slug> "<msg>" <file…>`**: it stages
only the named files onto a fresh branch cut from `origin/main` in an isolated reclaim-tracked
worktree (your checkout is never touched), opens the PR, and self-merges the moment
`merge-policy.sh` clears while retaining the branch/root for later accepted cleanup — one command,
so the PR path is never harder than the side door. The system's own findings are
githubbed the same way: **`scripts/sync-censor-issues.py`** (beat-wired, dry-run until
`LIMEN_CENSOR_ISSUES_APPLY=1` arms it) mirrors live censor residuals to public `censor`-labelled
issues and auto-closes them when the lineage clears — so insight→correction work arrives as an
issue and leaves as a PR that cites it. TABVLARIVS is the only logical board-projection writer:
the keeper commits accepted events with SHA compare-and-swap and publishes only through the stable
`tabularius/board-projection` branch, whose exact head enters the normal merge queue. Agent sessions
never push `tasks.yaml`, and the keeper never pushes `main`; the remote no-bypass `pull_request`
rule rejects every direct default-branch push, including automation and admins.

**Merge authority (standing grant).** Claude merges its own PRs into `main` *without asking*, the moment they are green and mergeable. Do not defer routine merges to the human operator. The grant has exactly one guardrail.

**The website guardrail.** A merge to `main` **auto-deploys** the live public site/API — but *only* when the diff touches a deploy-trigger path. The trigger paths are **declared once** in the `deploy_triggers` block of [`institutio/governance/gates.yaml`](institutio/governance/gates.yaml) (dashboard → `deploy.yml` → Cloudflare Pages, Firebase step dormant; API → `deploy-api.yml` → Cloud Run / Worker); `merge-policy.sh` derives its classification from that registry, and `check-gates.py` holds the registry in exact parity with the workflows on every PR — do not restate the path list here or anywhere else.

Classification is **path match AND rail armed**, because the question was never "does this glob match" but "will merging change what is served". A rail whose every effect-bearing step is conditioned on a secret that does not exist deploys nothing — it runs, prints a skip notice, and goes green. The **api rail is dormant** on exactly those grounds (`GCP_SA_KEY` exists nowhere; the live API is the Worker), so `web/api/**` and `cli/**` are non-deploy. Dormancy is declared in each trigger's `arming` block and *proven* by check-gates **K** — offline from the workflow's own step gating, and corroborated against the latest run's step conclusions, which is what catches the secret landing while the registry still says dormant. Absent an `arming` block a trigger is armed: the default over-protects.

For a **website-sensitive** PR, merging *is* the deploy — so it requires **green CI first** (plus a local `web/app` build for dashboard changes). Never blind-merge a live deploy. For every **other** PR (docs, corpus, mcp, ianva, memory, `web/worker`, most of `scripts/**`), merge freely once CLEAN. (`web/worker` is the live runtime but deploys on-demand via wrangler, not on merge — so its merges don't auto-deploy.)

**The predicate decides — not your memory.** Run `scripts/merge-policy.sh <PR#>` (or no arg for the current branch):

- exit **0 CLEARED** → run `scripts/await-pr.sh <PR#> --merge`. The predicate prints
  `MERGE-MODE: queue|direct` and an exact `MERGE-HEAD`; the waiter binds the effect to both. When
  the queue is active it enqueues once and reports success only after GitHub reports `MERGED`.
  Branch cleanup is receipt-backed and separate from the merge.
- exit **2 HOLD** → website-sensitive with CI not yet green+complete, a draft, or **required** checks still running/failing. Non-deploy verdicts count only the checks branch protection actually requires (derived live via `gh pr checks --required`; fail-toward-caution falls back to all-checks when underivable) — an advisory check never holds a non-deploy merge (2026-07-24 insights lineage: deliverables held hostage behind non-required checks). Website-sensitive PRs still demand the FULL rollup green: merging is the deploy. Wait for green, then merge.
- exit **3 BLOCKED** → GitHub itself refuses the merge: conflicts (DIRTY), a stale base without a
  proven queue rail, or an unsatisfied protection gate. Repair a real conflict or missing check.
  Do not turn `BEHIND` into a repeated branch-rewrite/full-CI loop; queue-capable stale heads are
  exit 0, while a missing/unknown queue is one exact owner-routed infrastructure blocker.

The script **derives** its deploy classification from the GATES registry at run time and fails *toward caution*: if derivation is impossible (broken python/PyYAML/registry), it forces website-sensitive, so a broken environment can only HOLD, never blind-deploy. There is no path list to keep in lockstep — `check-gates.py` enforces registry↔workflow parity on every PR.

**Waiting on a gate.** Never hand-roll a background poll loop on a PR gate (`for … gh pr … sleep … done` is banned — the 2026-07-15 endless-watcher incident: bespoke pollers, silent on FAIL, outliving their sessions). The one sanctioned synchronous waiter is **`scripts/await-pr.sh <PR#> [--merge]`** — hard deadline, loud CLEARED/QUEUED/MERGED/FAILED/TIMEOUT verdicts, single instance per PR, and it refuses to start under a merge-prohibiting pause marker. Queue mode never rewrites the PR head when `main` moves: GitHub creates a synthetic latest-base merge group and the always-on `pr-gate` verifies only that integration composition. Anything longer than the deadline belongs to the beat's merge rung (`scripts/merge-drain.py` via `scripts/drain.sh`) — hand off and end. Before arming any watcher or merging, read `logs/AUTONOMY_PAUSED`: its `prohibitions:` bind interactive sessions too — a marker that prohibits merges means no watcher and no merge until the operator releases it.

**Revising against a gate — an automated reviewer is a GENERATOR, not a gate.** The twin of the watcher ban above, and it costs more. A bot that re-reviews **each new head** has no fixed point: handed a fresh diff it always emits something, and every fix *adds* lines, so the surface the next round reviews is larger than the last. Chasing it diverges. (2026-08-12: PR #2122 ran 4 days, ~180 commits, +5,838/−204 across 29 files and 167 inline comments — 119 from one bot — while `merge-policy.sh` had returned **CLEARED** the whole time; the degenerate tail is `style(test): restore terminal newline` three commits in a row. Sibling PRs that week drew 0, 6, and 0 comments.) So: **the merge decision belongs to `scripts/merge-policy.sh` alone** — when it exits `0 CLEARED`, merge, and residual reviewer findings become follow-up issues, never a pre-merge obligation (this is the same rule as "an advisory check never holds a non-deploy merge", applied to prose instead of checks). Bound any fix-on-review cycle at **two rounds**, then stop with a loud verdict naming what you did not address; a third round is evidence the reviewer is generating rather than converging. Precedent: `PREC-2026-08-12-advisory-review-loop-has-no-fixed-point`.

**Still human-gated levers** (unchanged): mass cross-org/fleet merges, anything that **sends** (email) or **wipes/deletes**, and **large spends**. Those stay human-gated; routine code merges do not.
