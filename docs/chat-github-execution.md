# Chat-authored GitHub execution

Status: implementation candidate, disabled until explicit provisioning. This is
not evidence that ChatGPT.app or scheduled Chat can execute repository work.
Owner: 4444J99/limen; credential actions: issue #320.

## Trust boundary

`github_repository_context` resolves the current default branch to a commit, or
reads an exact SHA. `conduct_submit_changes` accepts one bounded `change` object:
`session_id`, `request_id`, `repository`, `base_sha`, `intent`, `changes`,
`verification_profile`, `landing`. Each change has `path`, `expected_blob_sha`
(null for creation), and `content` (null for deletion). Register a native
chatgpt/chat conductor session first through the existing MCP register tool.

Limits: 64 regular UTF-8 files, 256 KiB aggregate source, protected policy paths
excluded, explicit repository/path/profile grants, public repositories only.
Private payloads remain in keeper storage; public graphs contain only identities
and digests. The original request id is the execution policy work key: it must
already be admitted by the canonical execution-priority policy. No policy bypass
or implicit expansion is performed by the Chat tools.

The keeper creates deterministic Git objects and a `chat/` branch, never writes
main, and records a one-shot workflow dispatch before sending it. An ambiguous
dispatch is not retried. GitHub workflow identity, controller SHA, attempt 1,
actual successful verifier job and exact PR head are checked before success.
Merged success additionally requires merge-commit ancestry in the default branch.

The only initial profile is `python-canary`, which changes
`scripts/chat-github-canary.py` but cannot change its test oracle. Broader profiles
require separately reviewed immutable environments and explicit grants. Candidate
code runs inside an immutable Python container with no network or secrets, a
read-only checkout, bounded CPU/memory/processes/output/time and no Docker socket.
Trusted preparation and publication run in separate jobs. No model API is used.

## Provisioning contract (private credential owner only)

1. Auth0: authorize the tenant/client account action first. Configure an API for
   the exact HTTPS `/mcp` resource, RFC 9068 RS256 access tokens (`typ=at+jwt`),
   code + S256 PKCE, refresh as needed, resource-parameter compatibility, and the
   exact callback from the real Chat connection UI. Do not guess the callback.
2. Install `LIMEN_CONDUCT_MCP_OAUTH` using the existing v1 schema: resource,
   issuer, jwks_uri, scopes, client_id_claim=`client_id`, and explicit
   subject/client/principal bindings. Bind only the dedicated chatgpt/chat
   observer+conductor principal, not an owner/compatibility credential.
3. Provision a dedicated github_actions/workflow executor principal. Its bearer
   becomes Actions secret `LIMEN_CHAT_EXECUTOR_TOKEN`; the matching principal
   entry goes in the Worker's existing private registry. No raw bearer enters
   workflow inputs, job outputs, source, or receipts.
4. Provision a least-authority GitHub credential for the canary repository only:
   Contents read/write, Pull requests read/write and Actions read/write. Store as
   `LIMEN_CHAT_GITHUB_TOKEN` in Worker and GitHub Actions. Do not widen/reuse the
   task-projection token or relay governor installation.
5. Install private Worker `LIMEN_CHAT_GITHUB`: schema_version
   `limen.chat_github.v1`, enabled=true, control_repository=`4444J99/limen`,
   control_ref=`main`, control_sha=the reviewed deployed commit, workflow_id=the
   discovered workflow ID, executor_principal_id, grants=[{principal_id,
   repository, path_prefixes, profiles, merge}]. Missing configuration fails closed.
6. Approve exact canary work keys in the existing execution policy. Deploy via
   `deploy-worker.yml` with `expected_sha` equal to the live reviewed main SHA.
   Record deployment ID and discovery readback independently of source merge.

Account credentials are not currently available for these new bindings. Local
Docker is unavailable; container acceptance must therefore be hosted evidence.

## Acceptance and remaining implementation work

Before enabling beyond a controlled canary, add artifact-bound verification
receipts, executor-attempt accounting, crash-recovery tests around admission and
dispatch, and terminal reconciliation for queued merges, expired leases and
preparation/publication failures. Currently only verifier failures have an
explicit failure callback; an ambiguous external effect remains uncompleted.
These are engineering work, not human gates. Do not enable general execution on
the strength of the offline tests alone.

Actual acceptance requires a ChatGPT.app chat to read the canary, submit a
deliberately failing change, receive the failed executor receipt, submit a
corrected new request, and observe its exact-head PR/merge/default readback.
Then independently run the scheduled Chat case. Runtime denied desktop
inspection in this session; web or Work-mode evidence cannot substitute for
desktop Chat acceptance. Migrate eligible schedules only after these receipts.
