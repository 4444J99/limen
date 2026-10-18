# Pickup: land #3043, stage go-live, close out (OpenCode conduct access)

Issue: #2961
PR: #3043

## Context

The pasted OpenCode transcript is a *diagnosis* session. Since it ran, the situation changed: the
credential consumer it called "unstarted" was implemented by a sibling Claude session and published as
**PR #3043**, and the OpenCode lane's own dispatch envelope (comment on #2961, 2026-10-18T09:12Z) reframed
the objective to "review and land #3043, then prove it live." So "pickup, complete, verify, make green,
closeout" means: land the existing fix on the proper rail, say precisely what is and is not live, correct
the record, and close out this session. It does **not** mean re-implementing anything. The envelope and
transcript are hypotheses; everything below was re-measured this session.

## Verified state (measured 2026-10-18)

| Fact | Evidence |
|---|---|
| `main` = `1b789784c`; PR #3043 head = `2681027d77b4e86331c91defed699351b0f0b22e`, OPEN, non-draft, `mergeState=UNSTABLE` | `git log`, `gh pr view 3043` |
| `scripts/merge-policy.sh 3043 --repo 4444J99/limen` → **CLEARED**, exit 0, `MERGE-MODE: direct`, required scope 0 failing | run bare, own exit code |
| The same script **without `--repo`** → HOLD (`scope=all`, 1 failing). An **invocation artifact**: the `--prove-no-required` branch is guarded by `[ -n "$REPO" ]`, though `queue_repo` is already derived from the canonical PR URL earlier in the script. `gh pr checks --required` reports "no required checks" and `gh api …/rulesets` is empty, so nothing is required on `main`. | `merge-policy.sh` required-vs-advisory block |
| Hosted `pr-gate` (the heavy tier: `pytest-cli`, serialized) **passed on the exact head**; `python`, `contract`, `validate`, `worker`, `web`, `npm-audit`×2, `semgrep`, `CodeRabbit` pass | `statusCheckRollup` |
| Only red check: `witness-contract` — fails at `actions/checkout` of private `4444J99/ops-witness` (`OPS_SOURCE_GITHUB_TOKEN` dead). Fleet-wide, not caused by this PR; triggers only because #3043 edits `institutio/governance/parameters.yaml` (a listed path). Answers the envelope's open question. | issue #3003, `jules-api-contract.yml:9-20,101-117` |
| #3043 code review: no blocking defect. Laned client never reads generic `LIMEN_CONDUCT_TOKEN`, never returns the `LIMEN_CONDUCT_STATE` adapter, lane id regex-validated before naming a cache key, hydration leaves `os.environ` untouched, MCP engages the lane only when `LIMEN_AGENT` names a lane owning a bearer (Codex/Gemini keep today's resolution — regression test present). Tests assert refusal, not just success. | full diff read |
| #3042 (owner-gated session release, live Archive4T 3022 lane) edits `client.py` at lines 11-23 and 148-170; #3043 edits 367-398 → **disjoint hunks**, no other shared file | `gh pr diff 3042` hunk headers |
| #3043's author is done: last commit 08:48:45Z, PR untouched since 08:53:18Z, completion comment 08:49Z. Its worktree `.claude/worktrees/lane-credential-consumer-2961` is `locked` by a `bg-spare` pool pid — **not mine, not touched** | `git worktree list --porcelain`, `ps` |
| The deployed MCP server is a `uv tool` built from `/Volumes/Archive4T/limen-pr-delivery-20261016/{mcp,cli}` (`uv-receipt.toml`, `no-sources = true`, python 3.13). Merging to `main` changes **nothing** on the host. No documented reinstall path exists in `domus-mcp-*`, `domus-limen-runtime`, docs, or scripts. | `uv-receipt.toml`, greps |
| `~/.config/ianva/upstreams.json` `limen` entry has no `env`; `~/.limen.env` exists, passes `ownership_ok`, carries `LIMEN_CONDUCT_TOKEN_OPENCODE` (the envelope's §3.7 "cache absent" looked at the wrong path). `LIMEN_AGENT` is not a cache key, so `sanitize_backend_env` will not strip it. | prior-session readback + key-name list |

## Steps

**A. Preflight (read-only).** `git fetch`; re-read PR head, confirm still `2681027d7`; `logs/AUTONOMY_PAUSED`
absent; `ListAgents` for a conflicting claim on the branch. Use the `--repo` predicate form everywhere
(`merge-drain.py` calls it that way).

**B. Isolate (done).** Worktree `worktree-pickup-2961-landing` created via `EnterWorktree`. Check the writer lease
(`scripts/host-work-admission.py status --no-probe`) before heavier work; no nested clone. The harness worktree is
independent of the `limen workstream` execution-policy / host-admission / runtime-lag gates — those are **not**
blockers for this lane. This plan file lives in the worktree and ships with the closeout PR.

**C. Verify the exact tree (light tier, local).** Throwaway-merge `origin/main` + PR head (no commit), run each
bare and read its own exit code: `bash scripts/run-pytest-hermetic.sh cli/tests/test_conduct_env_cache.py -q`,
`…cli/tests/test_mcp_server.py -q`, the ianva `unittest`, `ruff check` + `ruff format --diff`, `mypy` on touched
modules, `python3 scripts/credential-wall.py --check` (expect 32/32), `bash scripts/verify-scoped.sh`. No host
interpreter has pytest — use a venv under the job tmp dir. If host admission refuses the heavy wave
(swap-fraction / heavy lease), quote the refusal; the hosted `pr-gate` on the exact head is the heavy-tier
evidence. A refusal is never reported as green.

**D. Land #3043.** `bash scripts/merge-policy.sh 3043 --repo 4444J99/limen --expected-head <SHA>` → exit 0, then
submit once: `python3 scripts/merge-drain.py --repo 4444J99/limen --pr 3043 --expected-head <SHA>`. No retry, no
polling. Prove landing positively and repository-qualified (squash repo: two-dot diff scoped by path, direction
checked). Do not touch the author's branch; no branch deletion. #3042 absorbs this on its own rebase.

**E. Observed proof of the code, not the deployment.** Stripped-env subprocess against the merged tree using a
**temp sentinel cache** (mode 600, fake tokens): the `Authorization` header selected is the lane bearer and
`os.environ` stays clean. I will **not** present the real OpenCode bearer to the broker from a Claude session —
that acts under another lane's identity, which the repo forbids. Live proof belongs to the OpenCode lane after F.

**F. Go-live — three host steps the merge does not perform. Operator decision (2026-10-18): "You proceed with all."**
I run them, in order, each preceded by its read-only check, with a backup of anything I edit and a stated
rollback. Abort and file `BLOCKED` once (script with dry-run/apply handed over) if a guard denies the same action
twice, or if a pre-check shows a non-OpenCode client on `:7666` or `env` replacement dropping `PATH`. Exact
commands and read-backs, also recorded once on #2961:
1. Reinstall the `limen-mcp` uv tool from a checkout of merged `main` (shape from `uv-receipt.toml`: `mcp` and
   `cli` directories, python 3.13, `--no-sources`). Read-back: the tool's python imports
   `limen.conduct.env_cache.lane_token_key`.
2. Add `"env": {"LIMEN_AGENT": "opencode"}` (no token) to the `limen` entry in `~/.config/ianva/upstreams.json`
   (app-owned, not chezmoi-managed; `ianva add-upstream` has no `--env`, so a backed-up direct edit). First confirm
   which clients actually use `:7666` (a shared upstream pinned to `opencode` relabels every client) and whether
   MCPHub *merges* or *replaces* upstream `env` (replacement could drop `PATH` in the child).
3. Restart: `launchctl kickstart -k gui/$(id -u)/com.ianva.gateway`, after 1 and 2. Read-back: regenerated
   `mcp_settings.json` env key names only; then an OpenCode session runs `limen-conduct_capabilities` and must
   resolve principal `opencode-direct` (generic-token or local-state resolution is a failure).

**G. Fix the base (separate small PR, one concern).** `merge-policy.sh`: give the `--prove-no-required` proof
`${REPO:-$queue_repo}` so the documented bare form `scripts/merge-policy.sh <PR#>` matches the `--repo` form;
add cases to `scripts/tests/merge-policy.test.sh` (bare + provably-no-required → CLEARED; bare + unprovable policy
→ still HOLD, failing toward caution). Three sessions mis-concluded `witness-contract` "holds merges" and spent
operator-instructed merges on it. Gate: `merge-policy-test`; merge on the same rail.

**H. #3003 left alone.** Dead CI credential, human-gated install, advisory by proof. Cited, not fixed; no edit to
the workflow or PR code; nothing copied into the Actions store.

**I. Record (one comment on #2961).** Status words separately: **merged** (commit on `origin/main`) / **live: no**
(until F) / **observed**: hermetic + sentinel-cache run only. Corrections to the 09:12Z envelope: cache path,
"witness-contract holds merges" = bare-invocation artifact, #3042 hunks disjoint. The F atoms stated once, filed
there — not recited again.

**J. Closeout.** Bind this job: `scripts/bind-running-claude-session.py` with the exact native session id (the
`projects/…/<uuid>` dir name, `a89fb304-ecdf-45a7-aef4-2cebe27d2309`, re-verify) and the worktree root. Receipt
`limen.session_closeout.v1` committed and remotely durable (carried in PR G or a docs PR via
`scripts/ship-docs.sh`), then `scripts/no-tasks-on-me.sh --session-id … --worktree … --receipt … --json` **twice**,
both bare exit 0. Hanging-work inventory first (unmerged session PRs, this plan file, worktree reap). Emit the
terminal line only after both exits are 0.

## Out of scope / forbidden

No push to the author's `worktree-lane-credential-consumer-2961`; no merge of #3042; no edit to
`logs/autonomy-policy.json`, `_SANCTIONED_LIMEN`, the Archive4T 3022 checkout or `repair-checkout.json`; no
`limen workstream`; no secret written anywhere; no OpenCode bearer used from this session; host-tool, upstream-env
and gateway changes only as step F, authorized by the operator. The owner-gated execution-policy row and host admission stay filed
on #2961 and matter only for the OpenCode repair-checkout / child-acceptance path, not for this landing.

## Verification (what "done" means)

1. `merge-policy.sh 3043 --repo …` exit 0 and the `merge-drain.py` submission recorded; PR `MERGED`, merge commit on `origin/main`.
2. Local light-tier commands each exit 0 (or the exact heavy-wave refusal quoted).
3. PR G merged; `merge-policy-test` green; bare `merge-policy.sh <PR#>` agrees with the `--repo` form.
4. `no-tasks-on-me.sh` bare exit 0 on two consecutive runs; tree clean; local:remote 1:1.
5. After F, read-backs pass (tool imports `lane_token_key`; settings env key names; gateway up). "Live" is claimed
   only if an OpenCode session observes `limen-conduct_capabilities` resolving `opencode-direct`; otherwise the
   report says "live: staged, not observed" and names that last check as the one owner atom.

## Outcome (recorded 2026-10-18 after execution)

Status words, kept separate. **merged:** #3048 (`21e3f21fb`, `check-docs-manifest` red on `main` fixed by rehoming #3039's directory), #3043 (`cf89cd825`, the lane credential consumer), #3050 (`acfa0a6ad`, merge-policy bare form judges the same policy as `--repo`), #3052 (`f2d557e5f`, registers the ianva unit-test gate), each proven an ancestor of `origin/main`. **live:** no. **observed:** hermetic tests (61), a sentinel-cache subprocess run showing the lane bearer presented and nothing leaked, scoped cheap wave 23/23 on the exact trees; the heavy wave was refused by host admission (`heavy-lease-held`, exit 75), and hosted `pr-gate` passed on #3043's pre-sync head.

What differed from the plan:

- **Step D** hit `STALE-CORE` (the PR touched `cli/src/limen/*` and its base had fallen behind). Remedy per the #2900 precedent, with the author's consent: one bounded base merge (fast-forward push `2681027d7..6b7e60fb7`), docs-only diff proved, one new submission. A superseding PR was not needed.
- **Step F (go-live) was NOT run.** The approved abort condition tripped: Codex, Gemini and OpenCode share the gateway `http://127.0.0.1:7666/mcp`, so a `LIMEN_AGENT=opencode` env on the shared `limen` upstream would relabel their conduct calls. A restart is also unsafe cold: the backend runs from an emptied `~/.npm/_npx` cache. Filed once on #2961 (comment 6248515317) with a derived per-lane-upstream recommendation.
- **Step G** landed as #3050 with an A/B against the parent script.
- **New, not planned:** `main` was red on `check-docs-manifest` (#3048), and `ianva/tests/` had no runner anywhere (#3052, with a mutation check that the gate fails when cache keys stop being stripped).
- **#3003** left alone, as planned.
- The live checkout was 4 commits behind `origin/main` at closeout (`check-live-checkout.py`, with the correct root): owned by the beat's `sync-release.sh`, not hand-fast-forwarded. The installed runtime was within tolerance (`check-runtime-lag.py` OK, 11 behind, 0.1d).
