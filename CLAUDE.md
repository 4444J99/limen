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
- Directory-scoped `AGENTS.md` files, where present, are closest-wins for their
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

**Components:** each component directory (layout: `AGENTS.md` → Working in This Repo) owns its remaining work (see [Closeout Definition](#closeout-definition)) and its README/manifest is the build reference. Gotchas the tree cannot tell you:

- `limen init` is retired and fails closed; the live verb/flag table is `README.md`.
- **MONETA** unconfigured *pools* demand as `reserved` orders (the valve) and auto-opens them the moment a receive address is set.
- The dashboard deploys to Cloudflare Pages; the Firebase Hosting step is dormant (its GCP credential exists nowhere). `web/worker/` is the live runtime but deploys on-demand via wrangler, not on merge.

**Storage modes** (`io.py`): local files are development projections; the authenticated Worker
plus GitHub Contents projection is the durable hosted keeper. Agents never treat a local
`LIMEN_TASKS` file as an independent writer. Persona tokens: `LIMEN_OWNER_TOKEN`/
`LIMEN_API_TOKEN`, `LIMEN_CLIENT_TOKEN`; absent → local owner-scoped dev mode.

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
Sonnet (the `"model": "sonnet"` pin, human-armed via lever `L-FABLE-GUARD-ARM` — an agent never
arms settings); `/model opus` is the deliberate escalation for ratifying a genuinely hard plan,
and Fable is never a session default — only an explicit `/model` escalation under a live
`docs/fable-allotment.md` acceptance receipt. The pin is a default, not a lock: `/model` persists
outside `settings.json` and can silently invert it, so never describe it as enforcement —
detection (`scripts/fable-session-guard.py` at SessionStart, the `claude-workflow-guard.py
audit-transcript` beat audit) is what holds the line. Full rationale:
[detail doc](docs/architecture/merge-and-branch-protocol-detail.md#session-model-cadence-and-the-opening-pin).

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

Follow `AGENTS.md` → Full Lifecycle Closure and `.agents/skills/closeout/SKILL.md`.
Session release, task completion, estate health and deletion eligibility are distinct
claims. Use the session-id/worktree-bound predicate and remotely durable owner receipt;
unknown ownership and owned unpublished work fail closed. A filed atom is homed, not
implemented. Reuse unchanged scoped verification; a read-only recheck must mutate nothing.
A completed session creates no successor capsule. Handoffs retain existing task states.
Use the established exact-head merge rail, or one `merge-drain` submission where applicable.
The first closeout is the real one: before the session predicate, inventory hanging work
(unmerged session PRs, landed-unreaped branches, live-checkout and installed-runtime
currency, unfiled follow-ups) and resolve or home each item. Status words are
evidence-bound and reported separately: "merged" (on origin/main), "live" (the live
checkout/runtime contains it), "observed" (runtime evidence); no "verified end-to-end"
without observed. Idempotence is two runs of the predicate, both bare exit 0. Procedure:
`.agents/skills/closeout/SKILL.md` steps 4-7.
After a successful session predicate, end with:
CLOSEOUT COMPLETE — idempotent fixed point, zero dangling items
Nothing follows the terminal statement.

## Definition of Done

When asked to define "done" or a "goal", deliver an **executable predicate** — a script or test that *verifies* the condition — never hand-maintained prose.

- **Write the predicate first.** Before doing the work, author a `done.sh` (or a test) that checks every concrete completion criterion: tests pass, build green, no dangling items, each owner records its own remaining work. Commit it (durable predicates only — not one-off throwaways; see [Edits Policy](#edits-policy)).
- **It must be self-verifying, runnable, and idempotent.** Exit `0` ⟺ done.
- **Do not claim completion — or write any closeout — until it exits 0.** Run it and summarize the output as proof. If it fails, make a bounded correction after inputs change; otherwise preserve the precise owner and evidence. If a higher-priority harness rule prevents running it, report the blocker rather than claiming verified completion.
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
- **Read the predicate's OWN exit code, never a pipeline's.** `predicate | tail` reports *tail's* status, so a gate that printed `FAIL` reads as green. Run the predicate bare and filter a saved copy, or use `${PIPESTATUS[0]}`. This is a standing behavioral rule, not a lint — the defect enters through ad-hoc verification shell, where a false green has no second reader (`AGENTS.md` → Session Discipline rule 6 is the source of truth).
- **Confirm the loop/driver actually runs** — that the entrypoint executes, not merely that files compile.
- **Check for regressions introduced by merges**: dropped imports, dumped/abandoned lanes, silently overwritten files. After any branch reconcile, diff against the prior green state.
- **Reconcile divergent branches against authoritative data** — GitHub redirect/PR state via `gh`, or `scripts/verify-dispatch.py` — never against heuristics or guesses.
- **A/B a change against its own parent commit, never against a branch name.** Once the PR merges, `origin/main` *contains* the change, so `git show origin/main:<file>` hands back the fixed file as the "before" and the A/B passes against itself. Extract the baseline from `<sha>^` and assert a marker is absent from it before trusting any before/after. Detail: [detail doc](docs/architecture/merge-and-branch-protocol-detail.md#ab-a-change-against-its-own-parent-commit).
- Report status terse and factual: if tests fail, say so with the output; if a step was skipped, say so; call something done only when the predicate proves it.

## Data Grounding

Before drawing any conclusion from a dataset (a message export, a mail archive, `chat.db`, a review window, a log
trawl), load the `data-grounding` skill (`.claude/skills/data-grounding/SKILL.md`): enumerate every channel before
analyzing one, state scope and denominators in the output, verify corpus retrieval reached a real store, and treat
conversation text as speech acts, never events. Case histories: [`docs/data-grounding-precedents.md`](docs/data-grounding-precedents.md).

## Edits Policy

- **Prefer minimal in-place edits**, especially during closeouts and cleanups. **Do not create new files unless asked** or genuinely required by the task.
- **Case-insensitive filesystem (macOS):** never let near-identical filenames (`Foo.md` vs `foo.md`) silently overwrite each other or drop a file from a commit — check before writing.
- **Confine edits to your worktree + branch.** Stage explicitly with `git add <path>` — **never `git add -A`** in a live checkout. Do not hand-merge contended `main` or edit daemon-contended runtime files.
- **Merge is a standing grant — Claude merges its own locally verified PRs into `main` without asking** (the routine-merge human-gate is lifted; see [Merge & Branch Protocol](#merge--branch-protocol)). Deploy is *automatic* on merge to `main` for deploy-trigger paths, so the **one guardrail** is the live website: never merge a change that breaks the deployed site/API — a website-sensitive PR requires its implicated local build/deploy predicate first. Mass cross-org/fleet merges, sends, wipes, and large spends stay human-gated levers.

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
- **Tier every fan-out agent by job — never let it inherit.** In-harness subagents (the Task tool *and* Workflow `agent()`) default to **the session model**, so trivial workers silently ride the session's Opus. Choose an `agentType` from `.claude/agents/` (`verify`/`scan` → haiku, `synth` → opus) or pass an explicit `model` + `effort`; the frontmatter pin is a **floor, not a cap**. The class→tier authority is `cli/src/limen/model_selection.py` plus `dispatch._claude_tier_for` (do **not** restate the ladder here); `scripts/claude-workflow-guard.py` surfaces untiered expensive fan-out every session. Incident: [detail doc](docs/architecture/merge-and-branch-protocol-detail.md#tier-every-fan-out-agent-by-job).
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

**The beat sensor estate is declared data too.** The heartbeat's sensors live in [`institutio/governance/sensors.yaml`](institutio/governance/sensors.yaml) (the SENSORS registry, beside GATES and PARAMETERS); `scripts/metabolize.sh` **derives** its whole sensor pass from it via `scripts/beat-sensors.py --run --source metabolize` (`--list` prints the matrix), and `scripts/check-sensors.py` (pr-gate) holds the registry in parity. **Adding a beat sensor = adding one `sensors.yaml` entry** — never a hand-wired shell block, and consumers read sensor capabilities, never sensor ids. Detail: [detail doc](docs/architecture/merge-and-branch-protocol-detail.md#the-beat-sensor-estate-is-declared-data-too).

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

**Chunking.** A branch is **one concern, not one session**: cut a fresh branch per concern off `origin/main` — finish → push → PR → next — and keep the **live checkout resting on `main`**, since a parked work branch pins the running fleet to stale code. `scripts/sync-release.sh` auto-unparks a fully-pushed, clean park each beat; do session work in a worktree. Incident: [detail doc](docs/architecture/merge-and-branch-protocol-detail.md#chunking--the-jules-capfill-park).

**Settling a session stream.** A PR that completes a domain declared in
[`institutio/governance/session-streams.yaml`](institutio/governance/session-streams.yaml) claims it
with an anchored `Settles: <stream-id>` trailer at **column 0** of the merge commit message. That
claim is the *only* thing that marks a domain settled, and the claiming commit must change something
outside the registry and `docs/{plans,continuations}/`. `scripts/check-session-streams.py` is the predicate.

**No side doors — docs included.** The branch cadence applies to *every* tracked change, including
one-file docs appends. Ship those with **`scripts/ship-docs.sh <slug> "<msg>" <file…>`**: it stages
only the named files onto a fresh branch from `origin/main` in an isolated worktree, opens the PR,
and self-merges once `merge-policy.sh` clears. System findings are githubbed the same way by
`scripts/sync-censor-issues.py` (dry-run until `LIMEN_CENSOR_ISSUES_APPLY=1`). TABVLARIVS is the only
logical board-projection writer and publishes only through the stable `tabularius/board-projection`
branch, whose exact head enters the normal PR rail; agent sessions never push `tasks.yaml`, and the
remote no-bypass `pull_request` rule rejects every direct default-branch push, automation and admins
included. Detail: [detail doc](docs/architecture/merge-and-branch-protocol-detail.md#no-side-doors--docs-included).

**Merge authority (standing grant).** Claude merges its own PRs into `main` *without asking*, the moment their exact tree is locally verified and GitHub reports them mergeable. Do not defer routine merges to the human operator. The grant has exactly one guardrail.

**The website guardrail.** A merge to `main` **auto-deploys** the live public site/API — but *only* when the diff touches a deploy-trigger path. The trigger paths are **declared once** in the `deploy_triggers` block of [`institutio/governance/gates.yaml`](institutio/governance/gates.yaml) (dashboard → `deploy.yml` → Cloudflare Pages, Firebase step dormant; API → `deploy-api.yml` → Cloud Run / Worker); `merge-policy.sh` derives its classification from that registry, and `check-gates.py` holds the registry in exact parity with the workflows on every PR — do not restate the path list here or anywhere else.

Classification is **path match AND rail armed**: a rail whose every effect-bearing step is conditioned on a secret that does not exist deploys nothing. The **api rail is dormant** on those grounds (`GCP_SA_KEY` exists nowhere; the live API is the Worker), so `web/api/**` and `cli/**` are non-deploy. Dormancy is declared in each trigger's `arming` block and *proven* by check-gates **K**; absent an `arming` block a trigger is armed (the default over-protects). Detail: [detail doc](docs/architecture/merge-and-branch-protocol-detail.md#the-website-guardrail--path-match-and-rail-armed).

For a **website-sensitive** PR, merging *is* the deploy — so its one exact-tree `scripts/verify-scoped.sh` batch must include the implicated local build/deploy predicate (including the local `web/app` build for dashboard changes). Never blind-merge a live deploy. On the registry-declared single-owner fast lane, remote CI remains useful telemetry but is advisory and cannot make unrelated live-state drift an admission failure. For every **other** PR (docs, corpus, mcp, ianva, memory, `web/worker`, most of `scripts/**`), merge freely once the scoped local predicate passes. (`web/worker` is the live runtime but deploys on-demand via wrangler, not on merge — so its merges don't auto-deploy.)

**The registry and predicate decide — not your memory.** For a registry-declared **single-owner fast lane**, run `scripts/verify-scoped.sh` once on the final clean exact tree, push it once, and immediately run `gh pr merge <PR#> --repo OWNER/NAME --squash --match-head-commit <SHA>`. Remote checks and automated reviews are advisory fix-forward inputs; do not arm auto-merge, wait, poll, or retry. For every other repository, run `scripts/merge-policy.sh <PR#>` (or no arg for the current branch):

- exit **0 CLEARED** → the predicate prints `MERGE-MODE: queue|direct` and an exact `MERGE-HEAD`.
  Submit that head once with
  `scripts/merge-drain.py --repo OWNER/NAME --pr <PR#> --expected-head <MERGE-HEAD>`, then return
  control. `QUEUED` is durable GitHub ownership, not `MERGED`; only a later repository-qualified
  merge receipt proves landing. Branch cleanup is receipt-backed and separate from the merge.
- exit **2 HOLD** → on a non-fast-lane repository, website-sensitive CI not yet green+complete, a draft, or **required** checks still running/failing. Non-deploy verdicts count only the checks branch protection actually requires (derived live via `gh pr checks --required`; fail-toward-caution falls back to all-checks when underivable) — an advisory check never holds a non-deploy merge (2026-07-24 insights lineage: deliverables held hostage behind non-required checks). Return control; do not wait in the agent/provider session.
- exit **3 BLOCKED** → GitHub itself refuses the merge: conflicts (DIRTY), a stale base without a
  proven queue rail, or an unsatisfied protection gate. Repair a real conflict or missing check.
  Do not turn `BEHIND` into a repeated branch-rewrite/full-CI loop; queue-capable stale heads are
  exit 0, while a missing/unknown queue is one exact owner-routed infrastructure blocker. Do not
  wait or re-run the predicate from the current agent/provider session.

The script **derives** its deploy classification from the GATES registry at run time and fails *toward caution*: if derivation is impossible (broken python/PyYAML/registry), it forces website-sensitive, so a broken environment can only HOLD, never blind-deploy. There is no path list to keep in lockstep — `check-gates.py` enforces registry↔workflow parity on every PR.

**Waiting on a gate.** Agent/provider sessions never wait on PR state: no polling loop, no sleep/recheck sequence, and no synchronous waiter. **`scripts/await-pr.sh` is retired and fails closed.** Queue mode never rewrites the PR head when `main` moves: GitHub creates a synthetic latest-base merge group for that shared-writer rail. Before submitting or merging, read `logs/AUTONOMY_PAUSED`: its `prohibitions:` bind interactive sessions too — a marker that prohibits merges means no submission and no merge until the operator releases it.

**Revising against a gate — an automated reviewer is a GENERATOR, not a gate.** A bot that re-reviews **each new head** has no fixed point: every fix *adds* lines for the next round to review (PR #2122 ran 4 days and ~180 commits while `merge-policy.sh` had returned **CLEARED** throughout). So **the merge decision belongs to `scripts/merge-policy.sh` alone**: on `0 CLEARED`, merge, and residual reviewer findings become follow-up issues, never a pre-merge obligation. Bound any fix-on-review cycle at **two rounds**, then stop with a loud verdict naming what you did not address. Precedent: `PREC-2026-08-12-advisory-review-loop-has-no-fixed-point`; full case: [detail doc](docs/architecture/merge-and-branch-protocol-detail.md#revising-against-a-gate--an-automated-reviewer-is-a-generator-not-a-gate).

**Still human-gated levers** (unchanged): mass cross-org/fleet merges, anything that **sends** (email) or **wipes/deletes**, and **large spends**. Those stay human-gated; routine code merges do not.
