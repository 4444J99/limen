# Cloud coding handoff: current admission evidence

Observed 2026-09-25, 21:35-21:38 UTC. Program #2739; source/handoff epic #2740.
Reuse existing activation owner https://github.com/4444J99/limen/issues/2680
and credential owner https://github.com/4444J99/limen/issues/320.
This is not a new dispatcher, credential request, or coding-provider launch.

## Source support is not the remaining whole blocker

At published source `ea2a11a5a74aee5e5166412643b34a31a2e2808a`,
`JulesApiExecutionAdapter.fenced_async_submission` and `launch_ready_nodes`
support the explicitly approved keeper policy `deadline_policy: fenced_async`.
It bounds submission and fences late integration; it does not cancel provider
computation. Ordinary hard-deadline paths retain their restriction. Do not
claim that this code change alone proves deployed policy, healthy executors,
account reconciliation, or permission to start this program's whole backlog.

The authenticated broker capabilities endpoint responded. Its historical
session registrations are not evidence of current provider health or quota.

## Fresh credential observations

- The existing environment loader followed by `limen.jules_api observe`
  returned exit 2, `jules_api_key_missing_or_invalid`, with no HTTP status.
  Provider usage and nonterminal counts stayed null, not zero.
- The authorized repository-secret listing succeeded; `JULES_API_KEY` was
  absent from that repository-level list. Direct lookup returned HTTP 404.
  This does not prove key absence from native secure storage or every other
  credential scope.
- The existing names-only resolver (`python -m limen.jules_credentials`,
  without `--apply`) returned `credential_source_unresolved`, exit 2.
  It performed zero provider mutations and wrote no CI secret.
- The latest default-branch push run of the Jules API contract was
  https://github.com/4444J99/limen/actions/runs/36051962430, dated September 24.
  Source and witness contracts passed; `account-readback` failed. Its actual
  log showed an empty `JULES_API_KEY` binding and exit 2. This is historical
  executor evidence, not a new September 25 account query.
- Recent successful PR contract runs do not supersede this account failure:
  the workflow intentionally withholds credentials and skips account readback
  for PRs. CI source access and autonomous coding access remain distinct.

## Owner and next action

Credential owner #320 must resolve the existing canonical credential source
through its sanctioned registry, without minting/rotating a key by assumption
or putting secrets in chat/source. Predicate: names-only resolution succeeds,
then the existing scoped delivery route and protected executor readback prove
authenticated paginated source/session reads. Its current first command is
`python -m limen.jules_credentials`; rerunning unchanged input is not progress.

Activation owner #2680 then reconciles actual account activity, native callers,
source access and keeper-approved asynchronous policy. Accept exactly one
bounded useful packet with an actual provider session ID; independently verify
its output and target integration before expanding throughput. No unrestricted
queue, alternative coding provider, new timer, or policy bypass is requested.

For this remote-first attempt: zero cloud coding sessions launched. Published
source, hosted verification and issue ownership are available remotely, while
authenticated autonomous implementation remains unproved. Independent source
custody and owner-specific local retirement need not wait for this provider.
