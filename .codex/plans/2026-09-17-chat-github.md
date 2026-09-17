# ChatGPT Chat to governed GitHub execution

Owner: direct human implementation request, 2026-09-17. Credentials: Limen #320.
Builds on merged #2622 and #2674. Relay #3 retains its independent governor scope.

## Accepted contract

Chat authors bounded, exact-base file changes. Limen's authenticated MCP surface
admits them through the canonical keeper; deterministic GitHub Actions executes
verification and the existing PR/merge rail. No model-provider fallback is allowed.
An assessment, plan, source merge, deployment, or queued handoff is not delivery.

## Implementation and acceptance checklist

- [ ] Authenticated exact-ref repository reads and bounded change submission.
- [ ] Private payload custody, canonical lease/policy admission and replay safety.
- [ ] Exact-base Git Data commits and durable one-shot Actions dispatch.
- [ ] Isolated secretless verification; trusted PR/merge finalization.
- [ ] Auth0 code/PKCE issuer, RFC 9068 access tokens, explicit Chat principal binding.
- [ ] Scoped source/security verification and published PR receipt.
- [ ] Exact-main deployment and public OAuth discovery readback.
- [ ] Real desktop Chat failing-test/correction/PR/merge/readback canary.
- [ ] Independent scheduled Chat execution, with actual experience and executor evidence.
- [ ] Eligible GitHub schedule migration verified in native settings.

Initial canary: 4444J99/limen. Existing authorized repository grants determine
further scope. Private execution requires demonstrated private runner isolation
and entitlement; source never moves to a public repository to evade that gate.

New tools: exact-ref repository context and conduct_submit_changes; progress uses
canonical graph/harvest. Changes use expected blob SHAs, UTF-8 regular files,
64-file/256-KiB bounds, deterministic request identity and explicit PR/merge intent.
Tests cover authorization, stale inputs, unsafe paths, duplicate/ambiguous effects,
wrong run/attempt artifacts, failing/zero-step verification and merge races.

Auth0 is the selected issuer: S256 PKCE, resource parameter compatibility,
RS256 RFC 9068 access tokens and the exact connection callback URI. All bindings
and credentials remain in the credential owner; no paid upgrade is authorized.

The computer-use runtime denied ChatGPT.app inspection. Desktop acceptance needs
actual Chat tool receipts; web/Work results cannot substitute. Prepare the exact
canary and complete all supported setup before any unavoidable user handoff.

## Execution record

Implementation checkout: feat/chat-github-20260917. Direct human session is
protected. No unrelated task claims or autonomous implementation children.
The documented private environment bootstrap succeeded and registered
codex-chat-github-20260917 as human-protected and not accepting autonomous work.

Source candidate includes both tools, private keeper storage, canonical admission,
one-shot Git Data/Actions execution, a secretless canary sandbox, PR publication
through the authenticated keeper, and the existing merge adapter. The MCP-builder
review added discoverable bounded field schemas and external-effect annotations.

Verification 2026-09-17: all 29 focused MCP/OAuth/Chat tests pass; four Python tests
pass. Focused tests exposed engine-dependent deep-JSON admission; an explicit
64-level bound now rejects before keeper dispatch. This final MCP change has
focused coverage but has not received a new full scoped batch.
The preceding corrected scoped batch passed all 35 cheap gates, then exited 75:
machine-wide heavy admission denied `disk-throughput`. The full Worker suite is
unverified; no bypass or green claim. Registry checks initially caught three
integration defects; those were fixed, not baselined away.

Keep this candidate as a draft PR, owned by the Chat/GitHub implementation lane.
Merge condition: resolve the engineering items in docs/chat-github-execution.md,
run admitted exact-tree scoped verification, and retain independent review.
Next verification: `bash scripts/verify-scoped.sh --base origin/main --require-base`.
No deployment, OAuth login, credential mint, Chat acceptance, schedule migration,
or completion claim occurred. Credential account/install atoms belong to #320;
runtime-denied desktop access requires actual native Chat evidence from the owner.
