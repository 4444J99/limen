# CLAUDE.md — Claude Code Operating Charter

Operating discipline for every Claude Code session in this repo. Complements (does **not** duplicate):

- `AGENTS.md` — the dispatch/task contract and `dispatch_log` done-recording.
- `GEMINI.md` — the swarm worktree-isolation and PR-babysitting lifecycle.

When a rule below also lives in those files, **they are the source of truth** and this charter points to them.

## Closeout Definition

A *closeout* means **ZERO open or dangling items** — never end one with a "but here's what's still open" caveat. Before declaring closeout:

1. **Every owner records its own remaining work** — each repo, component, and ledger carries its residual items in its *own* record; nothing is parked in your head or in a single throwaway list.
2. **An idempotent fixed point is reached** — re-running the full verification produces **no changes** (see [Definition of Done](#definition-of-done)). If a re-run still mutates state, you are not done.
3. **All loose work is committed across every repo** — no uncommitted diffs, no stranded branches; `git status` is clean wherever you touched.

If gaps remain, **close them first**, then archive and hand off. Surface genuinely human-gated items in *their owner's* record with the cheapest path to resolution — do not stop the closeout for them. Run `/closeout` to execute this discipline.

## Definition of Done

When asked to define "done" or a "goal", deliver an **executable predicate** — a script or test that *verifies* the condition — never hand-maintained prose.

- **Write the predicate first.** Before doing the work, author a `done.sh` (or a test) that checks every concrete completion criterion: tests pass, build green, no dangling items, each owner records its own remaining work. Commit it (durable predicates only — not one-off throwaways; see [Edits Policy](#edits-policy)).
- **It must be self-verifying, runnable, and idempotent.** Exit `0` ⟺ done.
- **Do not claim completion — or write any closeout — until it exits 0.** Run it and paste the output as proof. If it fails, keep iterating until it passes.
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
- **Merge is a standing grant — Claude merges its own green PRs into `main` without asking** (the routine-merge human-gate is lifted; see [Merge & Branch Protocol](#merge--branch-protocol)). Deploy is *automatic* on merge to `main` for deploy-trigger paths, so the **one guardrail** is the live website: never merge a change that breaks the deployed site/API — a website-sensitive PR requires green CI first. Mass cross-org/fleet merges, sends, wipes, and large spends stay Anthony's levers.

## Output Discipline (Concise Mode)

- Return **summaries, not file dumps.** Report **paths and diffs** — never paste large file contents back.
- **Checkpoint progress every few steps** with short factual status lines; no promotional language.
- Sub-agents return concise structured results, not raw transcripts.

## Parallel Exploration & Fan-Out

For any search or recon whose scope spans multiple domains, **fan out parallel read-only workers — one per distinct domain** (each remote, each local floor, each repo), launched in a single batch.

- Give each worker a **strict read-only scope** and require a **structured packet**: `{ found: [...], not_found: [...], confidence }`.
- **Wait for ALL workers**, then **merge into one ground-truth report that flags conflicts** between packets.
- **Never park the search early, and never guess a timeframe** — verify every location and timeframe explicitly before reporting. Default to ~3 parallel explorers for non-trivial recon.

## Worktree Isolation & CI Gate Matrix

Isolate work in a **git worktree so the live fleet is untouched** (see `GEMINI.md` for the swarm protocol). Then run the **full local gate matrix** before pushing:

| Gate | Command |
|------|---------|
| Lint | `python -m ruff check cli/src cli/tests web/api mcp` |
| Compile | `python -m py_compile web/api/main.py cli/src/limen/*.py` |
| Tests | `python -m pytest web/api/tests cli/tests -q` |
| Contracts / surfaces | `node scripts/validate-contract-schemas.mjs` |
| Worker | `npm run check` (in `web/worker`) |
| Build | `npm run build` (in `web/app`) |
| Whole-system | `scripts/verify-whole.sh` |

- For each failure, **fix root-to-leaf and re-run the full matrix** — loop until every gate passes end-to-end. Do not chase one gate green while another regresses.
- **Surface masked failures from dependency bumps** — a green that only passes because a check was skipped or a dependency silently changed behavior.
- **Only after every gate is green locally**, push and open the PR, pasting the full green run as proof. **Then merge it yourself** the moment `scripts/merge-policy.sh <PR#>` exits `0` (CLEARED) — that predicate enforces the website guardrail; never merge on a HOLD/BLOCKED. See [Merge & Branch Protocol](#merge--branch-protocol).

## Merge & Branch Protocol

Authoritative and permanent. Claude **owns the branch cadence and the merge decision** — Anthony does not have to think about either. This realizes the cascade *protocol → precedent → exploration → ideal-form*: the protocol is below; the executable predicate **`scripts/merge-policy.sh`** is the ideal-form that decides each case by logic, never by memory.

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

**Merge authority (standing grant).** Claude merges its own PRs into `main` *without asking*, the moment they are green and mergeable. No "leave it to Anthony" on routine merges. The grant has exactly one guardrail.

**The website guardrail.** A merge to `main` **auto-deploys** the live public site/API — but *only* when the diff touches a deploy-trigger path:

- **Dashboard** (`deploy.yml` → Firebase Hosting): `web/app/**`, `firebase.json`, `tasks.yaml`, `.github/workflows/deploy.yml`
- **API** (`deploy-api.yml` → Cloud Run / Worker): `web/api/**`, `cli/**`, `scripts/preflight-cloud-run.sh`, `.github/workflows/deploy-api.yml`

For a **website-sensitive** PR, merging *is* the deploy — so it requires **green CI first** (plus a local `web/app` build for dashboard changes). Never blind-merge a live deploy. For every **other** PR (docs, corpus, mcp, ianva, memory, `web/worker`, most of `scripts/**`), merge freely once CLEAN. (`web/worker` is the live runtime but deploys on-demand via wrangler, not on merge — so its merges don't auto-deploy.)

**The predicate decides — not your memory.** Run `scripts/merge-policy.sh <PR#>` (or no arg for the current branch):

- exit **0 CLEARED** → `gh pr merge <PR#> --squash --delete-branch`. Do it; don't ask.
- exit **2 HOLD** → website-sensitive with CI not yet green+complete, a draft, or non-deploy checks still running. Wait for green, then merge.
- exit **3 BLOCKED** → conflicts (DIRTY) or stale base (BEHIND). Rebase onto current `main` first (the PR#111 silent-revert guard), then re-run.

The script carries a **staleness guard**: if the deploy-trigger paths in `deploy*.yml` ever drift from its hardcoded list, it warns and fails *toward caution* (treats the PR as website-sensitive). Keep the path list in the script and in this section in lockstep with the workflows.

**Still Anthony's levers** (unchanged): mass cross-org/fleet merges, anything that **sends** (email) or **wipes/deletes**, and **large spends**. Those stay human-gated; routine code merges do not.
