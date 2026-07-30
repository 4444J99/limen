# Remote execution

Limen treats the laptop as a control plane, but off-box submission is never completion. The first
shipped slice is deliberately narrow: deterministic verification of an exact pushed commit from a
**public** repository on GitHub-hosted Actions. It does not claim that every AI provider has moved
to the cloud.

## Shipped public Actions contract

The `github_actions` lane discovers live GitHub authentication and the worker workflow before it
advertises capacity. A dispatch then:

1. accepts only a dedicated `type: verification`, `mode:verification-only` child whose
   implementation parent already has exact merged-PR or commit custody, rechecked against GitHub;
2. resolves both the target ref and a validated control branch/tag from GitHub to exact pushed
   SHAs; the control ref defaults to the live protected remote default branch and rejects `HEAD`,
   raw SHAs, pull refs, unsafe syntax, unprotected branches, and ambiguous branch/tag names;
3. validates a closed predicate grammar consisting only of an exact repository-owned
   `python3 scripts/check*.py`, `scripts/verify*.py`, `tools/check*.py`, or `tools/verify*.py`
   entrypoint and an exact typed receipt target;
4. persists a content-addressed attempt envelope before workflow mutation;
5. re-resolves the control branch/tag immediately before mutation, requires the same exact control
   SHA, dispatches the discovered workflow database identity with `--ref <control-branch-or-tag>`,
   then accepts only a run whose API identity matches the request title, nonempty exact control
   ref, head SHA, `workflow_dispatch` event, control repository, workflow ID, and workflow path;
6. checks out separately pinned control code and the exact target SHA;
7. resolves an allowlisted official Python image by immutable digest, then runs a boundary probe and
   the verifier in Docker with no network, no capabilities, no inherited environment, a read-only
   root and target-only bind, non-root UID, bounded CPU/memory/PIDs/output, and only an ephemeral
   `/tmp` tmpfs writable. The Docker socket and control/workspace siblings are never mounted;
8. rejects symlink escapes, dirty output, secrets, and contact-data-like material, and uploads only a
   counts-and-digests JSON receipt; and
9. harvests `done` only when the receipt digest, packet digest, target/control SHAs, workflow
   identity, verifier-parent context, sandbox attestation, predicate result, custody mode,
   inputs/profile digests, and exact current Actions run all match.

The lifecycle is `submit -> probe -> harvest/recover`. A stable request ID prevents retry from
creating a second run. Run discovery paginates the workflow history instead of searching only a
recent window. Terminal workflow failure needs no artifact to become `failed`; provider success
without its exact artifact becomes `failed_blocked`. Repeated harvest with unchanged state is
idempotent.

Receipts are stored content-addressed under `logs/remote-execution/` by default. Tracked board
events contain only the provider run identity, exact target/control ref and SHAs, workflow identity,
verification-context digest, state, stable request ID, and receipt path. Raw predicate output,
patches, prompts, credentials, and private paths are excluded.

## Current external capability gate

Private targets fail closed before workflow dispatch because this first contract has no live,
receipt-backed private-runner entitlement probe. This is not a claim about the account's billing
state. The implementation does not change billing, make a repository public, attach a paid runner,
or run a local runner; a later private lane must discover and attest its actual allowance/runner
capacity before advertising it.

## Provider families intentionally left on existing paths

This slice does not reroute native AI providers through the deterministic worker:

- Jules retains `jules remote new`, its task-first/no-feedback prompt, session recovery, and landing
  lifecycle.
- Copilot retains exact GitHub issue assignment. A future packet must bind the resulting PR identity
  and exact observed head before it can share this completion contract.
- Warp and Oz retain paid-service, execution-profile, Fable acceptance, live model-override, and
  secret-store gates. Their workflow is unchanged.
- Codex, Claude, OpenCode, and Agy remain on their bounded local/scratch paths. Each needs a real
  remote execution product plus live capability/auth discovery; this change does not invent one.

Those are separate provider-family child packets, not hidden completion of an all-provider task.
Models remain provider Auto/live-catalog decisions; no model ID or fixed tier table is encoded here.
