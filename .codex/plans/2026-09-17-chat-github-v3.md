# Chat activation and Gemini/Jules overlap

Owner: direct human session; credential wall #320; source PR #2679 is merged.
This revision preserves v1/v2 and incorporates the September 17 Gemini/Jules
scheduling artifact. Private transcript remains outside the tracked plan.

## Correction and acceptance

Answering an incidental setup question does not terminate the active implementation
request. Continue independent reversible work; isolate only the actual sign-in,
consent, or unavailable native-UI action. Never call deployed source an activated
Chat connection. No weakened host gate or blanket remote-test waiver is inferred.

## Proven source and provisioning

- PR #2679 landed at 8a5cf764dbf9ef7529b27898af0b219f5ad772c2. Worker deployment
  run 35245608963 passed 322 tests and produced version
  4cfacc11-e786-4807-96dc-b2e6c403b602; live identity readback matched.
- Human authorized Auth0 account/client setup and dedicated credential provisioning.
- Auth0 MCP API: RFC 9068 / RS256, exact production /mcp audience, explicit
  conduct:access scope, offline access, consent retained, machine access denied.
  Dedicated third-party native client has only that API scope. Resource parameter
  compatibility and issuer-response discovery are verified. The operator's Google
  connection test created an actual verified-email user; that exact subject/client
  binding is installed privately. Production OAuth resource discovery returns 200
  with the exact issuer, resource and conduct:access scope. Native Chat callback
  allowlisting and linking remain unproved.
- Live principal guard preserved all 11 pre-existing principals before adding
  chatgpt/chat observer+conductor and github_actions/workflow executor-only.
  Legacy and separately homed inventory collector credentials were restored into
  the local registry without rotation. Post-deploy readback: 13 retained, 0 added.
- Dedicated GitHub token is restricted to 4444J99/limen with Contents, Pull requests,
  Actions read/write and implicit Metadata read. Expires 2026-10-17. Installed in
  Worker and Actions; executor bearer installed separately in Actions. No secrets
  are in this plan, source, workflow inputs, or transcript.
- Canary-only controller grant is installed. Native Chat OAuth login, hosted failure /
  corrected-success / merge canaries and scheduled Chat acceptance are NOT proven.

## One scheduler, distinct native lanes

The Gemini artifact proposes 08:00 discovery, 10:30 and 14:30 dispatch waves, and
19:00 landing review. These are proposed America/New_York windows, not receipts
that Gemini or Jules schedules exist. They overlap the existing Jules supply,
dispatch-beat, quota, throughput, owner-route drain and flywheel organs.

Use the shared broker, canonical work keys and existing landing predicates. Do not
create a second issue-label dispatcher, relaunch already leased work, or route
Chat-authored deterministic execution into Jules behind the user's back. Preserve
Gemini and Jules identities. Discovery must rank existing lifecycle debt and avoid
minting 60-80 speculative issues merely to consume an allowance.

Current official Jules documentation states Pro allows 100 tasks in a ROLLING
24-hour window and 15 concurrent tasks. It does not establish this account's
current entitlement. The old midnight-expiry assumption in quota/flywheel prose
is not vendor truth. Local UTC-day receipt counts are not vendor remaining quota.
Sources: https://jules.google/docs/usage-limits and
https://jules.google/docs/scheduled-tasks/ .

Restoration owner: https://github.com/4444J99/limen/issues/2680 .
Read-only live observations: Jules CLI session listing authenticates successfully;
returned latest sessions are 28 days old, including failed and feedback-needed
work. This bounded listing is not a complete absence proof or entitlement check.
The local dispatch governor reports observe mode (exit 2). Historical owner #1874
is closed; that is not live flywheel acceptance. Do not override observe/recovery
admission or start 30-40 jobs per wave from this transcript alone.

## Remaining executable sequence

1. Finish exact Chat callback allowlisting and authenticated issuer subject binding;
   publish OAuth discovery using the reviewed schema, then verify discovery.
2. Admit only the explicit failure/success canary keys under the canonical policy;
   run native Chat and scheduled Chat acceptance with exact run/PR/default receipts.
3. Reconcile actual native schedules and live Jules entitlement with canonical
   broker admission. Reuse existing cadence owners and repair implicated quota
   semantics before activation; retain recovery and throughput limits.
4. Record activation/expiry obligations in #320 and scheduler restoration in its
   own owner. Preserve checkout until this new branch and receipts are durable.

The temporary loopback PKCE helper encountered no enabled client connections;
it did not issue a token or install a binding. After the operator independently
authenticated through Auth0's connection tester, the helper was stopped and its
unused scratch source removed. Only the actual dashboard user record supplied
the binding. The temporary callback was removed. Google connection developer-key
posture needs production review; a successful tester login is not a production
Chat refresh-token or scheduled-run receipt.

## Finite runway

Activation attempt began approximately 16:35 UTC; 30-minute attempt including at
most 10 minutes of verification, within 120 cumulative agent-minutes. No model
fanout. A blocking native consent action pauses only that action, not sibling work.
