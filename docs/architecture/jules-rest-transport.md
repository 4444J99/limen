# Jules REST transport: implementation is not activation

Coordination owner: 4444J99/limen#2680. Credential custody: #320.
Source date: 2026-09-21. Activation repair checkpoint: 2026-09-22. The user authorized repairing the Gemini/Jules pipeline using the direct API. This supersedes the earlier observation-only hold for this bounded implementation; it does not authorize parallel dispatchers, extra spending, credential disclosure, protection bypass, or cancellation/deletion of existing work.

## What changed

`limen.jules_api` implements the documented Google v1alpha sources, sessions, activities, create, approvePlan and sendMessage operations. It sends the Jules-specific API key only to the fixed HTTPS service through `X-Goog-Api-Key`, refuses redirects, bounds reads/pagination, and never prints response bodies or keys in errors. It is not the Gemini model API and a GitHub token is not a substitute for the Jules key.

`limen.jules_api_adapter` plugs into the existing `limen.fanout_execution` entry-point interface. It preserves conduct registration, claims, attempt receipts, retries, exact source/base/path verification and PatchLandingMixin. It does not create a separate queue, keeper, scheduler, or merge path. Select the `jules-api` required capability for API-only packets; do not leave a packet eligible for unrelated coding agents. CLI/native sessions remain observable and must be reconciled, not cancelled or duplicated.

The read-only `limen-jules-api observe` command emits aggregate JSON from real paginated provider reads. Missing credentials and incomplete/unknown observations exit 2 with null counts, not zero usage or a successful dispatch report. It performs no issue creation, session creation, plan approval, feedback, merge, or deletion.

Account observation requests only `name`, `id`, `state` and `createTime`, plus
`nextPageToken`, using Google's response field mask. Attempt recovery separately
requests the exact prompt/source identity and URL; full session reads remain
available for result inspection. Neither path omits pagination or assumes ordering.
The client retains a 4 MB response ceiling and 100-page ceiling. Observed account
pages take roughly 10–16 seconds each, so the default request deadline is 30 seconds
and the whole-catalog deadline is 600 seconds, not an unbounded scan. Oversized
read pages may be halved at the same cursor, at most six reductions per catalog;
an oversized single record still fails closed. Provider mutations are never retried
by this mechanism. Packet submission and integration deadlines remain independent.

## Activation prerequisites that are still real

1. Recover the existing Jules API key through the credential owner's managed secret storage. Bind it as `JULES_API_KEY` in the actual executor, never source, chat, a public receipt, or a shell command containing the literal key. A presence check in one Chat container does not prove absence from another runtime. The contract workflow tests the repository secret read-only only on an accepted default-branch push or manual default-branch run. PR jobs never receive the provider key, including same-repository PRs. A skipped PR readback is not an authenticated success.
2. Inspect the existing broker and actual native schedules and account usage. Bind the existing executor principal via `LIMEN_CONDUCT_TOKEN_JULES`. The new REST transport is explicitly unarmed unless `LIMEN_ENABLE_JULES_API=1`. The first declared lane concurrency is one; `LIMEN_JULES_API_CONCURRENCY` accepts at most fifteen. These are configured ceilings, not measured entitlement or a global account lock.
3. **Resolve the remote-deadline policy honestly.** Current `launch_ready_nodes` and `_journaled_agent_dispatch` reject remote providers when provider hard-deadline enforcement is required. The public API reference exposes no cancel or hard-deadline method. Accordingly this adapter declares `enforces_deadline=False`; no flag is forged and no existing guard is removed. Owner #2680 must implement/approve a keeper-side asynchronous policy that distinguishes a bounded submission and fenced integration deadline from provider compute cancellation. Required semantics: accepted remote work remains accounted for after lease expiry; no optimistic slot release; no publication from an expired/fenced lease; late output retained for a separately admitted recovery. `sendMessage("stop")` is not a cancellation guarantee.
4. Reconcile all callers, including the existing CLI, GitHub label webhook and Gemini timers, before admitting new work. Preserve the seven requested dispatch opportunities and three discovery/reconciliation shifts, but route admission through one account-wide broker. Do not label an issue to start Jules AND create an API session for the same work. A fresh transport is not authorization to revive the old competing Chat filler.
5. Complete one actual scheduled repair through accepted provider ID, final exact-base patch, scoped tests, allowed PR integration, and independent accepted-target readback. Only then raise admitted throughput. No new task has been launched by installing these source files.

## API semantics

- Source names come from ListSources and are checked against GitHub owner/repository fields. API startingBranch is a branch name; the adapter resolves the current default branch and verifies its head against the admitted exact base. It rejects final patches for another source/base.
- API-created plans are auto-approved by default. The bounded adapter explicitly sets `requirePlanApproval=false`; workflows that require a human plan gate must not select it without that authorization.
- This adapter leaves `AUTO_CREATE_PR` off because the existing exact-head landing owner creates the PR. The reusable client supports that option only explicitly. Provider `COMPLETED` is not merged, accepted default, or issue resolution.
- Timeout, 5xx and malformed create acknowledgement retain an indeterminate launch. The existing keeper records `launching` before calling the adapter. Recovery matches the exact first-line attempt marker AND source over fully paginated history. A miss/failed read leaves the same attempt pending; it never authorizes a blind second POST. Duplicate matches are not arbitrarily adopted.
- Waiting for a plan/user or paused sessions stay nonterminal; feedback and approval target the same provider session. Acknowledging a message is not proof that coding resumed.
- Session listing supports pageSize/pageToken, not a documented ordering/filter contract. Do not stop at the first old date. Pagination completion is not transactional snapshot isolation. Conflicting duplicates, page loops, unknown states, malformed/future timestamps or bounded-read failures do not establish free capacity.
- The observed rolling-start count is NOT the vendor billing/entitlement ledger. `vendor_quota_remaining` stays null. The published Pro rule is 100 tasks per rolling 24 hours, at most 15 concurrent, not a midnight reset. Other account activity, deletions and unknown accepted submissions require broker reconciliation. The provider remains the ultimate quota authority.

## Credential delivery without repeated secret handling

`python -m limen.jules_credentials` produces a names-only plan from an existing enabled CLAVIS map entry for `JULES_API_KEY`. When no unique source is registered, it returns `credential_source_unresolved` without reading or writing a secret. It does not invent an `op://` item or infer that no key exists in the vault.

On the existing credential runtime, `python -m limen.jules_credentials --apply` uses CLAVIS's promptless 1Password authorization, validates paginated Jules source/session reads, and streams the recovered value through `gh` stdin to the single declared `4444J99/limen` Actions secret `JULES_API_KEY`. An already-discovered reference may be supplied with `--source-ref`; that argument is a vault reference, never a literal key. No interactive unlock fallback, new vault, key minting, dispatcher, environment-file write, or activation flag is introduced. Failed provider validation prevents delivery.

The result `delivered_pending_executor_readback` proves only the reported delivery and name-presence checks. GitHub does not expose stored secret values for comparison. The protected default-branch `account-readback` job must independently prove consumption. Production executor binding, a real accepted session, and accepted-target verification remain distinct requirements. Only if canonical-store discovery proves that no Jules-issued key exists does creating one in signed-in Jules Settings become a user-owned step. Do not rotate existing keys by assumption.

## Verification and shared-gate repair

The original 46 REST and 19 adapter tests have now passed on the actual installed Limen framework in hosted CI (run `35743307887`, contract job `106799001144`). The pinned independent witness contract also passed in that run. Those are source contracts, not authenticated provider acceptance.

The same run's base-versus-head diagnostic established the identical first CLI failure on base `4d19db8eaeb689fec4f3b0e4d53f1d6e97b0edf4` and candidate `59e6a1989e18c70993c9a8822e426ba30e99ee1c`: `test_dispatch_parallel_accel_tail_is_win_class_only` attempted dispatch without the required approved priority. Both runs passed 146 tests before that failure. The repaired test explicitly declares test-only approval, exercises acceleration from one to two selections within the existing two-slot keeper ceiling, mocks the provider boundary rather than disabling production deadline enforcement, and adds a negative case proving unapproved work starts nothing.

Repeated parsing of the large parameter registry was also observed inside dispatch on the timeout path. The accessor now reuses a bounded parsed cache, rechecks the selected file's identity/timestamps/size on every call, and preserves live environment overrides and independent mutable defaults. Regression tests cover edits with preserved mtime, atomic replacement, worktree changes, invalid/deleted files, racing reads and mutation isolation. No timeout is raised, test is skipped, or admission guard removed to obtain these results.

Reproduce the focused repair suite against the actual installed framework:

```sh
python -m pip install -e 'cli[test]'
bash scripts/run-pytest-hermetic.sh \
  cli/tests/test_jules_api.py cli/tests/test_jules_api_adapter.py \
  cli/tests/test_jules_api_credentials.py cli/tests/test_jules_api_workflow.py \
  cli/tests/test_vigilia_params_cache.py cli/tests/test_vigilia.py \
  cli/tests/test_accelerator.py -q --tb=short
```

The contract workflow executes the new security/credential regressions and focused shared-gate repairs as well. The full required PR Gate remains independent and must pass at the final head; focused tests do not waive broader failures. Historical first-failure diagnostics remain manual-only, preserving the concurrent incident-workflow change. Temporary source/dependency export instrumentation is retired after reproduction.

The observed failed account-readback had an empty `JULES_API_KEY`, exited 2, and did not reach Jules. That establishes a missing binding in that job, not key absence elsewhere or provider rejection. Authenticated readback, uncancellable-provider admission/occupancy policy, schedule reconciliation, one-session accepted-target proof and throughput activation are still unproved. Do not report this PR or the 100-task pipeline as activated on source-test evidence alone.

## Primary references

- https://developers.google.com/jules/api
- https://developers.google.com/jules/api/reference/rest
- https://developers.google.com/jules/api/reference/rest/v1alpha/sessions
- https://developers.google.com/jules/api/reference/rest/v1alpha/sessions/list
- https://developers.google.com/jules/api/reference/rest/v1alpha/sessions.activities
- https://jules.google/docs/usage-limits/

## September 24 execution-policy repair

The API lane now requires an explicitly approved `deadline_policy: fenced_async`
priority in the same keeper admission that owns the packet. A provider capability
flag alone cannot authorize it. Ordinary hard-deadline providers and the legacy
CLI dispatch path retain their existing restrictions.

Both the Python and Worker keepers distinguish **execution authority** from
**provider occupancy**. A Jules attempt with accepted nonterminal or indeterminate
provider state retains its resource claims and capacity after its local lease
expires or a local failure receipt is recorded. The owning executor may then
claim an observation-only capability to update that exact attempt; it cannot
renew execution authority, change provider identity, open a replacement attempt,
or publish a result. Terminal provider evidence releases occupancy, not the
expired authority. Late output still requires a separately admitted recovery.

The REST client bounds the entire DNS/TLS/request/body operation in a process
with finite wall-clock and output ceilings. The provider key travels only over
private standard input. Timeout kills and reaps the client process but leaves a
mutating request indeterminate; it does not claim to cancel provider computation.

A native worker wake is now `submission_pending`, never a counted launch.
`targeted_launch_count` counts accepted provider identities, not preflight
failures or attempts. A read-only fanout coordination root receives no executor
capability and does not consume a worker slot; its actual child executions do.

The required CI verifier explicitly budgets up to 1,500 seconds for a gate and
1,800 seconds for the whole batch, under a 35-minute workflow-job ceiling. The
previous implicit 300-second gate cap overrode the CLI registry's existing
1,500-second declaration. The default local batch remains 600 seconds, and an
existing keeper-owned verification deadline always takes precedence. No test,
provider lease, quota boundary, or publication guard is waived.

The public-evidence audit retains a hash-bound, all-blocked historical candidate
that is no longer available for public verification as `withdrawn_unverified`.
It is not silently removed or passed, and the public runner receives no private
repository credential. The owning manifest records the explicit withdrawal;
malformed, unbound or promoted withdrawals fail verification.

Authenticated credential consumption, source/account reconciliation and a real
accepted repair remain live acceptance facts. Source regression tests cannot
supply those facts, and this documentation does not assert production activation.
