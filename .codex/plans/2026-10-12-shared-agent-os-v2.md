# Shared agent OS — accepted repairs and final observation rollout

This revision supersedes the same-day implementation checkpoint without replacing it.
The human authorized fixing checks, completing claims and available six-month evidence,
then merging and deploying both owners. Preserve dirty primary checkouts and native state.

## Accepted ownership and implementation

- Limen #2849 merged at `6100dac2c9630f3c6472f6fbf50a5bf3d9ec8f47`.
  The authenticated Worker and immutable local runtime were deployed at that revision.
  The broker now supplies a fresh, complete active storage-claim census, including a
  verified zero-active-run result. Shared growth uses filesystem free space less the
  existing machine reserve and outstanding reservations exactly once.
- Domus #420 merged at `5cddfbc0705f4bc3f9e33f11a7f70f7a42d39735` after #418.
  Reviewed canonical sources and file-only outputs were reconciled, retaining unrelated
  dirty work. Claude render parity and a second no-change apply passed.
- Domus #421 merged at `d61b735c74bf929b021479eac82a7ff1fbe1e9bd`.
  Native history compatibility, immutable-runtime process ownership and the bounded
  180-second heartbeat contract validator were repaired at source and deployed.
  Domus #422 merged at `0cc760cdfa4ede7f01c2ad8f3c18f997bbf6b054` and its history
  source was deployed. Compatibility now requires native acquisition rather than
  agreement among potentially truncated copied projections; all five readers passed.

## Final implementation

Use the existing one-shot heartbeat, not another scheduler. Keep all fifteen existing
probes and add a source-bound, record-only controller observation every 900 seconds.
The 180-second tick supplies 480 daily slots; the sixteen declared cadences require
fewer slots. Give the observation priority only when due. Simulate an entire day to
prove the 900-second cadence and that every existing probe still fires.

Bind all five Domus controller dependencies to accepted source hashes before and after
each observation. No worker apply or native history mutation is permitted. Treat exact
controller contention as deferred; source drift, incomplete census and protocol failure
use exit 78 and the existing three-consecutive-failure kill switch. Retain hard wall,
CPU, memory, child cleanup and bounded audit limits.

Repair native host health inspection through the supported DomusAgentHost route. A
divergent developer checkout may read the immutable installed native visual receipt.
The real TextEdit capture is successful; the Codex application restriction remains a
platform policy gate and must never be bypassed.

Complete the available local evidence scan over April 12 through October 12 inclusive,
using exact compressed-carrier scopes, native dates and private lineage. Inventory all
fifteen registered providers. Resolve repository-qualified remote receipts to exact
identities. Missing months, opaque payload contracts, undated artifacts and unavailable
remote records remain explicit evidence boundaries, never proof of no failures.

## Verification and release

Focused tests: 57 passed. Registry batch: nineteen cheap gates passed; the corrected
format shard also passed. The broad heavy tail was admission-denied for swap-fraction;
do not bypass machine protection or claim that the heavy suite passed. Hosted CI is
separately blocked by the account billing/spending gate already recorded in #2848.

Merge the exact verified followup head through Limen's single-owner PR rail. Install
the accepted revision using the canonical `4444J99/limen` repository. Activate only
through Domus's existing reviewed installer lifecycle. Retain an actual naturally
scheduled controller observation and independent post-deployment launch/census/source
parity receipts in the PR before closeout. Refresh existing health packets so repaired
local findings clear while the actual platform policy finding remains visible.

## Preservation and physical recovery

The sole history owner retained custody and verified all five native readers. Native
conversion accounting savings are not physical recovery. Separately, verified
regenerable Homebrew cache cleanup reduced allocated cache bytes by 2,731,327,488;
the concurrent filesystem free-space delta was +3,723,386,880 bytes. Active uv caches,
native conversations and disconnected external custody remain protected. Retain both
implementation worktrees for dirty-primary provenance and custody review; no checkout,
history or custody retirement is authorized by this rollout.
