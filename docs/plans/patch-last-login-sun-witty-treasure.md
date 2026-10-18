# Patch: agent launches blocked by `broker_storage_census_unavailable`

Issue: #2054
PR: (pending)

## Context

On 2026-10-18 ~13:54 local, both `codex` and `claude` refused to start:

```
domus-agent-runtime: agent runtime containment or quota check failed; preserve state
and complete maintenance before launch: broker_storage_census_unavailable
```

(A second terminal at 13:18 ran `codex features --enable agent_message_board`, a syntax error.)

### What is actually wrong (measured, not inferred)

`domus-agent-runtime quota --json` shows the **local** census is fine (`census_complete: true`,
`census_errors: []`, 156k files, 24.4 GB). The denial comes from the **pool** layer
(`available_growth_bytes: null`). Reproducing `limen.storage_claim_census.broker_storage_claims()`
against the installed runtime (`~/.local/share/limen/current`) gives:

```
BrokerQuotaExhausted: conduct broker rejected request (500):
  "Exceeded allowed rows written in Durable Objects free tier."
```

So the conduct broker's Cloudflare Durable Object has spent its daily free-tier write allowance.
The launch gate needs a fresh (<=120 s) authoritative broker storage census, cannot get one, and
**fails closed** — correctly, by design ("never infer an empty graph from sessions").

Three things made this hard to see:

1. `cli/src/limen/runtime_pool.py:57-63` (`selected_claims`) collapses *every* non-`broker_storage_census_*`
   exception, including `BrokerQuotaExhausted`, into the string `broker_storage_census_unavailable`.
2. The `domus-agent-runtime` message says "complete maintenance before launch", sending the reader to
   disk cleanup. Disk is fine (5.1 GB growth headroom at 13:18; pool mode `shared_disk_aware`).
3. The lever `L-CLOUDFLARE-DO-QUOTA` is **retired** (2026-08-10); the live owner is
   `#2054` ("conduct heartbeats rewrite growing broker state and exhaust persistence writes"), open since
   August with an implementation-ready v3 persistence design but no implementing PR.

### `codex features` item

`codex features list` shows `agent_message_board  under development  true` — already enabled. The
correct form is `codex features enable <name>` (subcommand, not `--enable`). Durable feature config is
owned by chezmoi template `Workspace/limen/private_dot_agent-runtime/private_codex/modify_private_config.toml.tmpl`
in the domus-genoma worktree `chore/codex-features-round-2` (4 files modified, another session). **No
action; do not duplicate or touch it.**

## Immediate unblock

No compliant bypass exists, and none will be added (Green is additive; the gate is the point).
The quota resets at **00:00 UTC** (observed 17:56 UTC -> ~6 h; 20:00 local). Already-running sessions
(this one) are unaffected. After reset, `domus-agent-runtime quota --json` exits 0 and launches resume.
Raising the Cloudflare plan is a spend decision and stays human-gated; it is not required.

## Patch (this repo, one concern, one branch)

Branch `worktree-fix-runtime-pool-broker-quota` (already created off `origin/main`; rename to
`fix/runtime-pool-name-broker-quota` before pushing if the PR rail wants the intent prefix).

1. `cli/src/limen/runtime_pool.py` — in `selected_claims()`, catch `BrokerQuotaExhausted`
   (import from `limen.conduct.client`, already the idiom in `cli.py:14`, `scripts/self-heal.py:56`)
   **before** the generic `except Exception` and raise `PoolUnavailable("broker_quota_exhausted")`.
   Path-free, typed, no behaviour change to the allow/deny decision — still `allowed: false`; only the
   reason becomes honest. Do NOT fold other broker errors into this reason.
2. `cli/tests/` — locate existing tests via `grep -rn selected_claims cli/tests` (candidate:
   `test_runtime_pool*.py`, `test_substrate_storage_pressure.py`). Add: broker raising
   `BrokerQuotaExhausted` -> `observe()` returns `allowed False`,
   `denial_reasons == ["broker_quota_exhausted"]`, `available_growth_bytes is None`; and a regression:
   a generic `ConductError(500)` still maps to `broker_storage_census_unavailable`.
3. Consumers of the old string: `grep -rn broker_storage_census_unavailable cli scripts` — update only
   exact-reason assertions this case legitimately changes.
4. Handler comment cites `#2054` and reuses `QUOTA_OWNER` (`cli/src/limen/cli.py:52`) wording rather
   than inventing a new string; matches the existing "the write path is spent, not broken" idiom.

### Follow-ups (filed, not done here)

- **domus-genoma** (`dot_local/libexec/domus-agent-runtime.py`, chezmoi source — edit source, never the
  deployed copy; separate branch; check the writer lease first): when `denial_reasons` contains
  `broker_quota_exhausted`, print "conduct broker write quota spent (resets 00:00 UTC); owner #2054"
  instead of "complete maintenance". It already mirrors `pool.denial_reasons` into `failures`
  (line 1058), so this is message-only.
- **#2054 comment**: the launch gate couples *every* agent start to broker write quota, and
  `GET /capabilities` fails although `ConductKernel.capabilities()` (`web/worker/src/conduct/keeper.js:503`)
  is pure. Hypothesis (unverified): the 500 originates in `store.load()`, the rollback-drain
  `store.save(state)` branch in `SerializedConductService.call` (keeper.js ~2146), or a per-request
  write in the Worker fetch handler. Next step for the #2054 owner: read `ChunkedDurableStateStore.load`
  and confirm a read-only capabilities fast path. That removes the coupling at its root; a stale-census
  cache in the gate would weaken it and is rejected.

## Verification

```bash
bash scripts/run-pytest-hermetic.sh cli/tests/<file from step 2> -q
python3 -m ruff check cli/src cli/tests
python3 -m mypy --config-file cli/pyproject.toml cli/src/limen/
bash scripts/verify-scoped.sh        # bare; read its own exit code
```

A/B against the parent commit (`<sha>^`): the new test must fail there. Runtime check once the
installed runtime (`~/.local/share/limen/current`) contains the merge: while quota is spent,
`domus-agent-runtime quota --json` shows `"denial_reasons": ["broker_quota_exhausted"]`; after
00:00 UTC it shows `"ok": true`. Report merged / live / observed separately.

Merge: `scripts/merge-policy.sh <PR#>` exit 0, then one `scripts/merge-drain.py` submission (or
fast-lane `gh pr merge --match-head-commit`). Non-deploy path (`cli/**`).
