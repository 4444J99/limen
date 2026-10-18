# Keeper policy storage repair for #3022

Owner: [#3022](https://github.com/4444J99/limen/pull/3022). Implementation:
[#3027](https://github.com/4444J99/limen/pull/3027).

The intact approved candidate exceeds the provider's 5 KB variable limit.
The current reader and reconciliation installer assume plain JSON in a single
`LIMEN_EXECUTION_POLICY` binding. Preserve all policy values and canonical
fingerprints while allowing bounded transport compression.

## Implementation

1. Reproduce oversized policy readback and add failure cases before changing the reader.
2. Add a versioned gzip/base64 envelope with SHA-256 of its decoded UTF-8 JSON,
   a declared decoded length, a 64 KiB decoded cap, strict fields, and a bounded
   transport size. Legacy object JSON remains supported.
3. Resolve one policy snapshot before constructing the keeper service; reuse that
   snapshot for authenticated fingerprint/private readback. Invalid storage yields
   an empty fail-closed execution policy and a 409 readback without provider data.
4. Encode policy bindings with the Python standard library. Keep small policies
   as JSON, compress larger policies, enforce a conservative 5,000-byte output
   limit, and reject oversized/incompressible inputs. Installation of compressed
   data requires the live reader to advertise support. Default reconciliation is
   still read-only.
5. Run focused codec/integration tests and the implicated scoped verification batch.
   Keep a reviewable exact-head PR and redacted evidence.

## Acceptance

- An intact policy larger than one binding round trips with every priority and limit.
- Semantic canonical fingerprints and authenticated private readback agree.
- Bad version, digest, encoding, length, UTF-8, JSON, truncated stream and excessive
  expansion fail closed; no envelope may be mistaken for an execution policy.
- Unknown fields, missing fields and non-object payloads fail closed.
- Legacy policy behavior and role checks remain covered by the worker suite.
- An old deployed reader cannot receive compressed policy through the installer.
- No production policy, running worker, custody data or existing worktree changes.

## Deployment boundary

This change is preparation and testing. Worker rollout requires a separately
approved exact deployment. Deploy the compatible reader with the existing legacy
policy first; verify runtime identity and advertised storage capabilities; only
then prepare the already-approved policy candidate with the new encoder. Pin
the source/candidate fingerprints and verify the policy readback after installation.
Rollback before compressed policy activation can restore the prior code directly.
After activation, restore the prior legacy policy with verified readback before
rolling back to code that cannot decode compression. Never roll old code back
while leaving an encoded binding active. No priorities, budgets or gates are removed.
