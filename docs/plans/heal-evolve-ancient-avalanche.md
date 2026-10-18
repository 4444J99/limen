# Heal + evolve: the broker-quota launch block, 2026-10-18 (second pass)

Issue: #2054
PR: #3114

Successor of `docs/plans/patch-last-login-sun-witty-treasure.md`, whose Limen half landed as #3103
(`c80d84821`, installed as the current runtime). This plan takes the two follow-ups that plan filed
and the two asks packed into the operator's message (`merge 3029`, `patch`).

## Context

At 14:12 local the operator's terminal showed `codex` and `claude` refused to launch with
`broker_quota_exhausted` (the honest reason #3103 introduced), but the launcher still said
"preserve state and complete maintenance before launch", which sends the reader to disk cleanup.
Disk is fine; the conduct broker's Cloudflare Durable Object has spent its daily free-tier write
allowance (resets 00:00 UTC, 20:00 local). Live state re-measured this session (18:22 UTC):
`domus-agent-runtime quota --json` -> `ok:false`, `pool.denial_reasons:["broker_quota_exhausted"]`,
census complete, no disk warning.

### What is already settled (no work)

- **`merge 3029`**: PR #3029 is MERGED as `d899a2e5e` on `origin/main`, and the installed runtime
  (`c80d848…`, later on main) contains it. Report merged + live; nothing to do.
- **PR #3093**: `scripts/merge-policy.sh 3093` now returns **CLEARED** (head `b49d0c5e`), but that
  head is a merge of `origin/main` pushed at 18:22:34Z by another live session (worktree
  `chore-fewer-permission-prompts-20261018b`, locked). Cross-agent rule: never mutate a branch
  another session owns. Leave it; its owner merges. Report only.
- **`codex features --enable agent_message_board`**: operator syntax slip; the subcommand form is
  `codex features enable <name>`, and `codex features list` already shows it enabled. Durable
  feature config is owned by a chezmoi template in another session's worktree. No action.

### What the evidence says about the root (read-path trace, this session)

- `web/worker/src/conduct/durable-object.js:272-275`: capabilities is a pure GET into
  `service.call("capabilities")`.
- `keeper.js:2144-2213`: the only read-triggered write is the **rollback drain** (2147-2154), armed
  only when `LIMEN_CONDUCT_STEADY_HEARTBEAT_OVERLAY=0`; the repo never sets it
  (`parameters.yaml:1817` default `"1"`, not in `wrangler.toml` or any workflow). `capabilities` is
  not in the expiry-preflight list (2157-2167) and never sets `mutated`, so no post-call save.
- `durable-store.js:253-297`: `load()` is read-only.
- Therefore the 500 on a pure read is Cloudflare refusing storage access after the account's daily
  write cap, not a write in the read path. Cloudflare documents exactly this for D1 free tier (all
  queries fail until midnight UTC); for Durable Objects it is the same error family and the
  observed behaviour matches. Marked unverified for DO.
- Consequence: a read-only fast path would **not** unblock launches. The root fix remains #2054's
  bounded-write persistence (already designed there, `lane:fleet`, not attempted here). The write
  amplifier is every non-heartbeat mutation (`register`, `report`, expiry preflight): a full cold
  save writes `ceil(state/96KiB)` chunks + manifest and deletes the prior generation.

## Lanes

### Lane 1 (heal, domus-genoma): quota-specific launch denial

Repo `4444J99/domus-genoma-private`, chezmoi source `dot_local/libexec/domus-agent-runtime.py`.
Edit the source only; the deployed copy is already behind main (gemini legacy-home lines 646-659
pending apply) and `chezmoi diff` confirms that drift.

1. Worktree: `git -C /Users/4jp/Workspace/domus-genoma worktree add
   /Users/4jp/Workspace/.worktrees/domus-launcher-quota-hint-20261018 -b
   fix/launcher-broker-quota-hint-20261018 origin/main` (the repo's existing worktree convention;
   no writer lease is held on domus-genoma; limen host-admission's codex leases are codex surfaces).
2. `launch()` at lines 1243-1254: add a small reason -> sentence map (module constant, e.g.
   `LAUNCH_DENIAL_HINTS`) consulted for the stderr hint and the `ContainmentError` text. For
   `broker_quota_exhausted`: "conduct broker write quota is spent (Cloudflare free tier; resets 00:00
   UTC); disk is not the cause; owner 4444J99/limen#2054; retry after reset, no maintenance needed".
   Any other reason keeps today's "preserve state and complete maintenance before launch" sentence.
   Keep the leading "agent runtime containment or quota check failed;" so the existing
   `match="containment or quota"` tests hold. `failures` already mirrors `pool.denial_reasons`
   (line 1058); nothing else changes.
3. Test beside `tests/test_domus_agent_runtime.py:771` (`test_shared_exhaustion_fails_closed`):
   a probe returning `allowed False, denial_reasons ["broker_quota_exhausted"]` ->
   `launch_admission(env)["failures"] == ["broker_quota_exhausted"]`; `launch()` raises
   `ContainmentError` matching "write quota is spent" and NOT "complete maintenance";
   `_resolve_command` is never reached (reuse the `pytest.fail` monkeypatch idiom). A second row
   asserts `shared_pool_exhausted` still yields the maintenance sentence (regression).
4. Verify (bare commands, own exit codes): `python3.14 -m pytest tests/test_domus_agent_runtime.py -q`
   (python3.14 is the only PATH interpreter with pytest here; `DOMUS_TEST_PYTHON=python3.14`),
   `python3.14 -m ruff check dot_local/libexec/domus-agent-runtime.py`.
5. Ship: commit, push, PR to `4444J99/domus-genoma-private`; submit once with
   `python3.14 scripts/merge-drain.py --repo 4444J99/domus-genoma-private --pr N --expected-head SHA`
   (non-fast-lane repo rule), return control.
6. Live: after landing, `git -C /Users/4jp/Workspace/domus-genoma pull --ff-only` (live checkout is
   on main, clean apart from `.serena/project.yml`), `chezmoi diff ~/.local/libexec/domus-agent-runtime.py`,
   then `chezmoi apply ~/.local/libexec/domus-agent-runtime.py` (single target). Observe:
   `domus-agent-runtime quota --json` still `ok:false` until 00:00 UTC, and a `codex` launch prints
   the quota sentence. Report merged / live / observed separately.

### Lane 2 (evolve, limen): the register hook stops re-spending against a spent quota

`scripts/hooks/conduct-register.sh` retries registration every 120 s per background session. While
the quota is spent each attempt spawns two Python processes (caps lookup + `limen conduct register`)
on a host at 72 % swap, fills the job log with identical `BrokerQuotaExhausted` lines, and cannot
succeed before 00:00 UTC.

1. Worktree `fix-conduct-register-quota-hold-20261018` (this one); branch renamed to
   `fix/conduct-register-quota-hold-20261018` before push.
2. Hook: capture `workstream_register_conduct_session` output into a variable (then append to the
   log as today). If it contains `BrokerQuotaExhausted` or `Exceeded allowed rows written`, compute
   the next 00:00 UTC epoch (`date -u -v+1d` on macOS, with a GNU fallback) and write it as a 4th
   stamp field. On entry, a stamp whose 4th field is in the future exits 0 before any process spawn,
   logging one line `quota spent; holding registration until <ISO>` the first time only. Interval
   refresh resumes automatically at reset (the fail-open contract and the stdout-silence contract
   are unchanged; the credential still never reaches stamp/log).
3. Tests: rows in `scripts/tests/conduct-register-hook.test.sh` using the existing fake `limen`
   (extend it with `FAKE_BROKER_STDOUT`): (a) quota reply -> second firing after
   `LIMEN_CONDUCT_REGISTER_INTERVAL_SECS=0` makes **no** limen call; (b) a stamp with a past hold
   -> registers again; (c) a non-quota failure still retries after the interval (regression).
4. Gate: `LIMEN_GATE_PYTHON=python3.14 bash scripts/verify-scoped.sh` — implicates
   `conduct-register-hook-test` (cheap) plus diff/docs gates; no heavy gate, so exit 0 is reachable
   under current host admission. Commit this plan file in the same PR (plan chain: `PR:` is this PR).
5. Ship via `scripts/merge-policy.sh <PR#>` -> CLEARED -> `gh pr merge --squash --match-head-commit`.

### Lane 3 (home the evidence): #2054 comment

One comment, facts only: the read-path trace with file:line, the parameter default, the Cloudflare
account-wide-cap reading (D1 doc precedent, DO unverified), the corrected next step for the owner
(bounded writes, not a read fast path), and the one regression test this session could not run
(a zero-writes assertion for `capabilities`/`graph`/`session_audit` through
`SerializedConductService` with a delete-counting storage double needs `npm install` in
`web/worker`, a heavy admission-gated gate). Also note the launcher message fix PR.

### Closeout residue (stated once)

- `scripts/bind-running-claude-session.py` / `no-tasks-on-me.sh` are unmeasured (exit 2) for every
  session until the quota resets: BLOCKED: broker write quota (owner #2054, resets 00:00 UTC). Not
  re-surfaced.
- Interpreter fact (`python3.14` is the gate toolchain on this host) goes through
  `scripts/memory-ticket.py`, since Claude memory is keeper-owned in this repo.

## Verification summary

| Lane | Predicate | Expected |
|---|---|---|
| domus | `python3.14 -m pytest tests/test_domus_agent_runtime.py -q` | pass, new rows included |
| domus | `python3.14 -m ruff check dot_local/libexec/domus-agent-runtime.py` | clean |
| domus live | `chezmoi diff ~/.local/libexec/domus-agent-runtime.py` after apply | empty |
| limen | `LIMEN_GATE_PYTHON=python3.14 bash scripts/verify-scoped.sh` | exit 0 (cheap wave only) |
| limen | `bash scripts/merge-policy.sh <PR#>` | CLEARED |
| observed | `codex` launch while quota spent | prints the quota sentence, no "maintenance" |
