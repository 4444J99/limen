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

Point 1 has a shipped predicate — **`scripts/no-tasks-on-me.sh`** (exit `0` ⟺ nothing hangs on the ephemeral session). It proves every his-hand item lives in the git-tracked registry with a real owner (recall-only memory at `~/.claude/…` is **not** a durable home), that no preserved work is stranded on a local-only `*-staged-*` ref (each must be merged or cited by a lever), and that the registry stays PII-clean (it publishes). Run it instead of re-auditing ownership by hand each session; a chat audit you have to repeat next session *is* leaving the discipline hanging on you.

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

## Credentials Are Organ-Owned (Never Recited At Him)

Tokens, secrets, API keys, logins, env vars are **system burden, not Anthony's** — never recited in a chat or parked as a fresh ad-hoc ask. They have **two registered homes, both on GitHub** (per the directive 2026-06-25 and the pinned Wall, `organvm/limen#320`):

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

## Standing Autonomy & Gate Reroute

His request **is** the authorization — driving it to a verified end *is* the job, not a thing to ask permission for. Re-gating his own ask behind "want me to… / should I / confirm first / your hand to pull" is the friction he most hates; delete every such hedge before ending a turn. The litmus before *any* action is one question — **am I destroying, sending, spending, or irreversibly leaking?** If no, just do it (save, commit, push, branch, open + merge a green non-deploy PR, enable a reversible agent). The genuine levers — wipe/delete/overwrite-what-I-didn't-make, **send** (email), **large spend**, mass cross-org merge, PII-to-public — get **surfaced with their cheapest fix, not asked-permission-on**; surfacing ≠ requesting approval, and the PII answer is *sanitize-and-commit-now*, never defer.

**Harness gates are mine to route around, not his to clear.** When the harness blocks a step — a settings/hook self-modification classifier, a force-push / remote-ref-delete guard — that block is a *mechanism*, not a decision handed to Anthony. First find the autonomous reroute and take it; only the truly irreducible atom gets surfaced. Concretely, from precedent:

- **Force-push / delete-remote-ref blocked** → never ask him to force-push or wipe a ref. Open a **new branch** and normal-push it as a superseding PR (then close the stale one), or rebase onto current `main`. The standing "never force-push / never delete remote refs" rule is satisfied *by the reroute*, not by escalating to him.
- **`settings.json` / hook-arming blocked** (self-modification boundary) → that single keystroke — pasting the validated block — is genuinely his, by harness design. Stage the **exact** validated file, hand him the **one** copy-paste, and do everything on either side of it yourself (branch, commit, rebase, push, PR, merge). Do not narrate the surrounding steps as if they were also his.

Never present a reroutable gate as a step **for him**. Narrating gates instead of plowing through them — surfacing five "his-hand" items when four had an autonomous reroute — is the same friction as re-asking permission for already-authorized work. Reduce every blocker to its single irreducible atom (if any), clear the rest silently, and report what was done. The [Merge & Branch Protocol](#merge--branch-protocol) below is the merge-specific instance of this reflex.

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
- exit **3 BLOCKED** → GitHub itself refuses the merge: conflicts (DIRTY), stale base (BEHIND), or a branch-protection gate unsatisfied (BLOCKED — e.g. the required `pr-gate` check never ran on a PR opened before that check existed). Rebase onto current `main` first (the PR#111 silent-revert guard; a rebase also retriggers the required checks), then re-run. If BLOCKED persists after a clean green rebase, a required review or admin merge is needed — surface it, don't force it.

The script carries a **staleness guard**: if the deploy-trigger paths in `deploy*.yml` ever drift from its hardcoded list, it warns and fails *toward caution* (treats the PR as website-sensitive). Keep the path list in the script and in this section in lockstep with the workflows.

**Still Anthony's levers** (unchanged): mass cross-org/fleet merges, anything that **sends** (email) or **wipes/deletes**, and **large spends**. Those stay human-gated; routine code merges do not.
