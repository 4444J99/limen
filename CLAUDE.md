# CLAUDE.md — Claude Code Operating Charter

Operating discipline for every Claude Code session in this repo. Complements (does **not** duplicate):

- `AGENTS.md` — the dispatch/task contract and `dispatch_log` done-recording.
- `GEMINI.md` — the swarm worktree-isolation and PR-babysitting lifecycle.

When a rule below also lives in those files, **they are the source of truth** and this charter points to them.
If prose and executable predicates disagree, the executable predicate wins; update the prose to match
the script/schema/code rather than trusting memory.

## Instruction File Maintenance

- `AGENTS.md` owns operating modes, task states, dispatch protocol, budget semantics, safety, and
  `dispatch_log` shape.
- `CLAUDE.md` owns Claude-specific execution discipline: closeout, merge cadence, credential
  handling, output style, worktree isolation, and compliant gate reroutes.
- `GEMINI.md` owns conductor/MCP workflow details and PR babysitting mechanics.
- `CONTRIBUTING.md` owns human contributor guidance.
- `docs/agent-instruction-standard.md` owns the rationale and cross-surface standard.
- If you change task states, precedence, agent names, referenced scripts, or status examples, update
  `scripts/check-agent-docs.py` in the same change. Do not add a competing instruction file unless a
  new tool requires it; link it back to `AGENTS.md`.

How the agent-instruction files (this charter, `AGENTS.md`, `GEMINI.md`, and the ecosystem-wide `ORGANVM:AUTO` layer) fit together — and why there is no separate "agent-all" repo to build — is settled once in [`docs/agent-instruction-standard.md`](docs/agent-instruction-standard.md). Read it before re-proposing how these files should be standardized.

## Architecture & Orientation

Limen is a **cross-agent, cross-repo, budget-capped task intake system**. The single source of truth is `tasks.yaml` at `$LIMEN_ROOT` (fallback `./tasks.yaml`); every AI agent reads it at session start, claims a task, executes, and writes results back via a `dispatch_log` (the contract is `AGENTS.md`). Around that core file are a CLI, a published SaaS surface, and a fleet of self-keeping "organs."

In a direct human-request session, do not claim unrelated queue work or mutate `tasks.yaml` unless
the request explicitly asks for Limen queue execution. `AGENTS.md` → **Operating Modes** is the
authoritative rule.

**The lifecycle is the durable contract — providers are replaceable adapters.** A task moves `open → dispatched → in_progress → done → archived`; from `in_progress` it may instead go `failed`, `failed_blocked`, or `needs_human`, and a stale claim is released back to `open`. The canonical state set, the cross-agent precedence ladder, and the startup checklist live in `AGENTS.md` (**Task States** / **Precedence** / **Startup Checklist**) and are enforced by `scripts/check-agent-docs.py`. Surfaces are gated by persona (owner / client / public) via bearer tokens. Firebase hosting serves only public-safe static shells + public contracts; everything internal loads at runtime from a Cloudflare Worker (or the FastAPI adapter). Keep the lifecycle + persona-sanction semantics intact and any of Firebase/Cloud Run/Next.js/FastAPI can be swapped.

**Components** (each owns its remaining work — see [Closeout Definition](#closeout-definition)):

| Path | What it is | Build/run |
|------|-----------|-----------|
| `cli/` | The `limen` CLI (`limen.cli:main`, Click). Core verbs: `init`, `dispatch`, `release-stale`, `doctor`, `qa`, `status`, `harvest`. Logic in `dispatch.py`, `harvest.py`, `capacity.py`, `model_selection.py`, `converge.py`; data shapes in `models.py`; YAML I/O in `io.py`. The autonomic institution lives under `cli/src/limen/vigilia/`. | `pip install -e 'cli[test]'`; tests in `cli/tests/` |
| `web/api/` | FastAPI runtime adapter (`main.py`). Same HTTP contract as the Worker. | `uvicorn main:app` / Docker; tests in `web/api/tests/` |
| `web/worker/` | Cloudflare Worker — the **live** runtime, GitHub-Contents storage. Deploys on-demand via wrangler (not on merge). | `npm run dev` / `npm run deploy`; lint `npm run check` |
| `web/app/` | Next.js dashboard (static export → Firebase Hosting). Surfaces `/` (owner), `/qa`, `/client`, `/public`. | `npm run dev`; `npm run build` (prebuild generates static data + validates surfaces) |
| `mcp/` | MCP server exposing limen over the Model Context Protocol (`mcp/src/limen_mcp/server.py`). | `pip install -e mcp/` |
| `ianva/` | MCP doorway/aggregator package. | `pip install -e ianva/` |
| `moneta/` | **MONETA** — the sovereign cash organ (sibling of `quaestor`: quaestor *finds* money, MONETA *intakes* it). Self-hosted Bitcoin licence mint: takes BTC to an owner-controlled address, confirms against a **keyless** public explorer (mempool.space/Esplora), and signs each product's own offline ECDSA-P256 Pro licence — **no processor in the path**. Unconfigured, it *pools* demand as `reserved` orders (the valve) and auto-opens them the moment a receive address is set. `Dockerfile`-ready for a $0 deploy. | `cd moneta && npm test` (vitest + `tsc`); tests in `moneta/src/__tests__/` |
| `spec/contracts/` + `spec/*.schema.json` | Portable JSON Schemas the generated surface contracts must satisfy. | `node scripts/validate-contract-schemas.mjs` |
| `scripts/` (~120 files) | The operational fleet: `metabolize.sh`/`heartbeat-loop.sh` (the beat), `verify-whole.sh` (whole-system predicate), `merge-policy.sh` (merge decision), `organ-health.py` (liveness), `creds-hydrate.py` (credential organ), plus per-organ generators. | run directly |
| `organs/`, `organ-ladder.json`, `pillars.yaml`, `his-hand-levers.json` | Declarative registries: the self-* organ ladder, platform pillars, and the owned human-gated lever registry. | data files |

**Storage modes** (`io.py`): local file (`LIMEN_TASKS=/path`) for dev; GitHub Contents (`LIMEN_GITHUB_REPO`, `LIMEN_GITHUB_TOKEN`, optional `_BRANCH`/`_PATH`) for the hosted runtime. Persona tokens: `LIMEN_OWNER_TOKEN`/`LIMEN_API_TOKEN`, `LIMEN_CLIENT_TOKEN`; absent → local owner-scoped dev mode.

**Common commands** (beyond the [CI Gate Matrix](#worktree-isolation--ci-gate-matrix)):

```bash
python -m pytest web/api/tests cli/tests -q          # full test suite
python -m pytest cli/tests/test_dispatch.py -q       # one test file
python -m pytest cli/tests/test_dispatch.py::test_x  # one test
python -m ruff check cli/src cli/tests web/api mcp   # lint (py311, line-length 120)
scripts/verify-whole.sh                              # whole-system predicate (exit 0 ⟺ green)
limen dispatch --agent jules         # dry-run preview; add --live to dispatch for real
```

## Closeout Definition

A *closeout* means **ZERO open or dangling items introduced by this task/session** — never end one with a "but here's what's still open" caveat for work you created or claimed. Before declaring closeout:

1. **Every owner records its own remaining work** — each repo, component, and ledger carries its residual items in its *own* record; nothing is parked in your head or in a single throwaway list.
2. **An idempotent fixed point is reached** — re-running the full verification produces **no changes** (see [Definition of Done](#definition-of-done)). If a re-run still mutates state, you are not done.
3. **All loose work you introduced or touched is committed across every affected repo** — no uncommitted diffs, no stranded branches; `git status` is clean wherever you touched.

If gaps remain, **close them first**, then archive and hand off. A genuinely human-gated item is **filed in its own git-tracked owner** — a lever in `his-hand-levers.json`, or (for any token/secret/login/env atom) the credential organ + Wall #320 — **never recited back to the operator in a closeout, and never appended as a "but also this" tail.** The relay cites the registry and the green predicate; it does **not** enumerate his atoms. He reads owed work in the registry on his own cadence — **a closeout that hands him a list has failed, even when every item is technically homed.** If an atom is *already* filed, that is DONE: do not re-surface it. Run `/closeout` to execute this discipline.

Point 1 has a shipped predicate — **`scripts/no-tasks-on-me.sh`** (exit `0` ⟺ nothing hangs on the ephemeral session). It proves every human-gated item lives in the git-tracked registry with a real owner (recall-only memory at `~/.claude/…` is **not** a durable home), that no preserved work is stranded on a local-only `*-staged-*` ref (each must be merged or cited by a lever), and that the registry stays PII-clean (it publishes). Credential/secret atoms live in a **separate** git-tracked home (the credential organ), so the closeout gate is **both** `scripts/no-tasks-on-me.sh` **and** `scripts/credential-wall.py --check` (exit `0` ⟺ every secret in use is homed). Both green ⟺ nothing hangs, and the relay then names the registry, never the atoms. Run them instead of re-auditing ownership by hand each session; a chat audit you have to repeat next session — or a "here's what's still open" list handed to the operator — *is* leaving the discipline hanging on him.

## Definition of Done

When asked to define "done" or a "goal", deliver an **executable predicate** — a script or test that *verifies* the condition — never hand-maintained prose.

- **Write the predicate first.** Before doing the work, author a `done.sh` (or a test) that checks every concrete completion criterion: tests pass, build green, no dangling items, each owner records its own remaining work. Commit it (durable predicates only — not one-off throwaways; see [Edits Policy](#edits-policy)).
- **It must be self-verifying, runnable, and idempotent.** Exit `0` ⟺ done.
- **Do not claim completion — or write any closeout — until it exits 0.** Run it and summarize the output as proof. If it fails, keep iterating until it passes. If a higher-priority harness rule prevents running it, report the blocker rather than claiming verified completion.
- For whole-system "done" in this repo, the predicate is already shipped: **`scripts/verify-whole.sh`** (lint → compile → contracts → `pytest web/api/tests cli/tests -q` → runtime/worker probes → dashboard build → `git diff --check`; prints `Whole-system verification passed`). A task-level `done.sh` should call it or a scoped subset — don't reinvent it.

## Never Over-Claim Completion

Do **not** declare work "done" or "fully done" until verified end-to-end:

- **Run the real gates locally**, never from memory: `python -m ruff check cli/src cli/tests web/api mcp`, `python -m pytest web/api/tests cli/tests -q`, and `scripts/verify-whole.sh`.
- **Confirm the loop/driver actually runs** — that the entrypoint executes, not merely that files compile.
- **Check for regressions introduced by merges**: dropped imports, dumped/abandoned lanes, silently overwritten files. After any branch reconcile, diff against the prior green state.
- **Reconcile divergent branches against authoritative data** — GitHub redirect/PR state via `gh`, or `scripts/verify-dispatch.py` — never against heuristics or guesses.
- Report status terse and factual: if tests fail, say so with the output; if a step was skipped, say so; call something done only when the predicate proves it.

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
- **The only irreducible human residue is a vendor/billing MINT the organ physically cannot perform** (a suspended project, a revoked token behind a billing hold). Record it as its **real-world action** (e.g. the bank call `L-CARD-FRAUD-HOLD` that un-suspends the gemini project), never as a "re-mint this token" chore. `op` stays opt-in: hydration must never trigger an unattended Touch-ID/GUI prompt.

## Output Discipline (Concise Mode)

- Return **summaries, not file dumps.** Report **paths and diffs** — never paste large file contents back.
- **Checkpoint progress every few steps** with short factual status lines; no promotional language.
- Sub-agents return concise structured results, not raw transcripts.

## Parallel Exploration & Fan-Out

For any search or recon whose scope spans multiple domains, **fan out parallel read-only workers — one per distinct domain** (each remote, each local floor, each repo), launched in a single batch.

- Give each worker a **strict read-only scope** and require a **structured packet**: `{ found: [...], not_found: [...], confidence }`.
- **Wait for ALL workers**, then **merge into one ground-truth report that flags conflicts** between packets.
- **Never park the search early, and never guess a timeframe** — verify every location and timeframe explicitly before reporting. Default to ~3 parallel explorers for non-trivial recon.
- **Tier every fan-out agent by job — never let it inherit.** In-harness subagents (the Task tool *and* Workflow `agent()`) default to **the session model**, so a fan-out of trivial workers silently rides the session's Opus (the `verify-studio-launch` incident: six broken-link/typo checks on Opus 4.8). Pick each agent's tier by its job: choose an `agentType` from `.claude/agents/` (`verify`/`scan` → haiku, `synth` → opus) or pass an explicit `model` + `effort`. The frontmatter pin is a **floor, not a cap** — a per-call `model` still escalates a genuinely hard job upward. The class→tier authority is `cli/src/limen/model_selection.py` plus `dispatch._claude_tier_for` (do **not** restate the ladder here); an untiered expensive-tier fan-out is surfaced every session by the `scripts/claude-workflow-guard.py` audit wired into `SessionEnd`.
- **Fable is a reserved tier above Opus, not the new default.** Use it only under [`docs/fable-allotment.md`](docs/fable-allotment.md): a Fable run needs a written `scripts/fable-allotment.py accept ...` command/receipt before it starts, `LIMEN_FABLE_ACCEPTANCE=<receipt>` in the run environment, and a single bounded objective. Retry bumping caps at Opus unless `LIMEN_CLAUDE_RETRY_BUMP_TO_FABLE=1` and that acceptance is present. Untiered Fable/Opus fan-out is blocked by `scripts/claude-workflow-guard.py`.

## Worktree Isolation & CI Gate Matrix

Isolate work in a **git worktree so the live fleet is untouched** (see `GEMINI.md` for the swarm protocol). Then run the **full local gate matrix** before pushing:

| Gate | Command |
|------|---------|
| Lint | `python -m ruff check cli/src cli/tests web/api mcp ianva` |
| Format | `python -m ruff format --check cli/src cli/tests web/api mcp ianva` |
| Type-check | `python -m mypy src/limen/` (from `cli/`) and `python -m mypy --ignore-missing-imports mcp/src/limen_mcp/ ianva/src/ianva/` |
| Compile | `python -m py_compile web/api/main.py cli/src/limen/*.py mcp/src/limen_mcp/server.py ianva/src/ianva/*.py` |
| Tests | `python -m pytest web/api/tests cli/tests -q` |
| Contracts / surfaces | `node scripts/validate-contract-schemas.mjs` |
| Worker | `npm run check` (in `web/worker`) |
| Build | `npm run build` (in `web/app`) |
| Whole-system | `scripts/verify-whole.sh` |

- For each failure, **fix root-to-leaf and re-run the full matrix** — loop until every gate passes end-to-end. Do not chase one gate green while another regresses.
- **Surface masked failures from dependency bumps** — a green that only passes because a check was skipped or a dependency silently changed behavior.
- **Only after every gate is green locally**, push and open the PR, pasting the full green run as proof. **Then merge it yourself** the moment `scripts/merge-policy.sh <PR#>` exits `0` (CLEARED) — that predicate enforces the website guardrail; never merge on a HOLD/BLOCKED. See [Merge & Branch Protocol](#merge--branch-protocol).

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

One PR per branch → `main`. Squash-merge, delete the branch. `main` is the trunk **and** the live deploy source.

**Merge authority (standing grant).** Claude merges its own PRs into `main` *without asking*, the moment they are green and mergeable. Do not defer routine merges to the human operator. The grant has exactly one guardrail.

**The website guardrail.** A merge to `main` **auto-deploys** the live public site/API — but *only* when the diff touches a deploy-trigger path:

- **Dashboard** (`deploy.yml` → Firebase Hosting): `web/app/**`, `firebase.json`, `tasks.yaml`, `.github/workflows/deploy.yml`
- **API** (`deploy-api.yml` → Cloud Run / Worker): `web/api/**`, `cli/**`, `scripts/preflight-cloud-run.sh`, `.github/workflows/deploy-api.yml`

For a **website-sensitive** PR, merging *is* the deploy — so it requires **green CI first** (plus a local `web/app` build for dashboard changes). Never blind-merge a live deploy. For every **other** PR (docs, corpus, mcp, ianva, memory, `web/worker`, most of `scripts/**`), merge freely once CLEAN. (`web/worker` is the live runtime but deploys on-demand via wrangler, not on merge — so its merges don't auto-deploy.)

**The predicate decides — not your memory.** Run `scripts/merge-policy.sh <PR#>` (or no arg for the current branch):

- exit **0 CLEARED** → `gh pr merge <PR#> --squash --delete-branch`. Do it; don't ask.
- exit **2 HOLD** → website-sensitive with CI not yet green+complete, a draft, or non-deploy checks still running. Wait for green, then merge.
- exit **3 BLOCKED** → GitHub itself refuses the merge: conflicts (DIRTY), stale base (BEHIND), or a branch-protection gate unsatisfied (BLOCKED — e.g. the required `pr-gate` check never ran on a PR opened before that check existed). Rebase onto current `main` first (the PR#111 silent-revert guard; a rebase also retriggers the required checks), then re-run. If BLOCKED persists after a clean green rebase, a required review or admin merge is needed — surface it, don't force it.

The script carries a **staleness guard**: if the deploy-trigger paths in `deploy*.yml` ever drift from its hardcoded list, it warns and fails *toward caution* (treats the PR as website-sensitive). Keep the path list in the script and in this section in lockstep with the workflows.

**Still human-gated levers** (unchanged): mass cross-org/fleet merges, anything that **sends** (email) or **wipes/deletes**, and **large spends**. Those stay human-gated; routine code merges do not.
