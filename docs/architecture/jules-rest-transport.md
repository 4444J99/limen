# Jules REST transport: implementation is not activation

Coordination owner: 4444J99/limen#2680. Credential custody: #320.
Source date: 2026-09-21. The user authorized repairing the Gemini/Jules pipeline using the direct API. This supersedes the earlier observation-only hold for this bounded implementation; it does not authorize parallel dispatchers, extra spending, credential disclosure, protection bypass, or cancellation/deletion of existing work.

## What changed

`limen.jules_api` implements the documented Google v1alpha sources, sessions, activities, create, approvePlan and sendMessage operations. It sends the Jules-specific API key only to the fixed HTTPS service through `X-Goog-Api-Key`, refuses redirects, bounds reads/pagination, and never prints response bodies or keys in errors. It is not the Gemini model API and a GitHub token is not a substitute for the Jules key.

`limen.jules_api_adapter` plugs into the existing `limen.fanout_execution` entry-point interface. It preserves conduct registration, claims, attempt receipts, retries, exact source/base/path verification and PatchLandingMixin. It does not create a separate queue, keeper, scheduler, or merge path. Select the `jules-api` required capability for API-only packets; do not leave a packet eligible for unrelated coding agents. CLI/native sessions remain observable and must be reconciled, not cancelled or duplicated.

The read-only `limen-jules-api observe` command emits aggregate JSON from real paginated provider reads. Missing credentials and incomplete/unknown observations exit 2 with null counts, not zero usage or a successful dispatch report. It performs no issue creation, session creation, plan approval, feedback, merge, or deletion.

## Activation prerequisites that are still real

1. Recover the existing Jules API key through the credential owner's managed secret storage. Bind it as `JULES_API_KEY` in the actual executor, never source, chat, a public receipt, or a shell command containing the literal key. A presence check in one Chat container does not prove absence from another runtime. The contract workflow tests an existing repository secret read-only; it does not create or replace that secret.
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

## Verification

Local command: `PYTHONPATH=cli/src python -m unittest discover -s cli/tests -p test_jules_api.py -v`.
46 isolated REST contract tests passed in the Chat execution container. An additional 19 adapter unit tests passed with the existing fanout interfaces replaced by a test-only stand-in; that is not an import/integration test of the full framework. Both source modules compile. Repository CI runs all 65 tests against the actual installed framework and checks entry-point discovery. Those are source tests, not full-repository integration, actual provider acceptance, native schedule proof or activation evidence. The added workflow additionally checks the real installed entry point and attempts a no-dispatch authenticated account read using an already stored key. Its final result must be read back independently.

## Primary references

- https://developers.google.com/jules/api
- https://developers.google.com/jules/api/reference/rest
- https://developers.google.com/jules/api/reference/rest/v1alpha/sessions
- https://developers.google.com/jules/api/reference/rest/v1alpha/sessions/list
- https://developers.google.com/jules/api/reference/rest/v1alpha/sessions.activities
- https://jules.google/docs/usage-limits/
