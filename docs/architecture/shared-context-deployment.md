# Shared-context deployment capability

Limen owns admission; Domus owns the producer, templates and private reference packet.
The capability permits an exact signed plan rather than granting arbitrary external
file writes or unrestricted chezmoi access.

`limen shared-context capabilities` reports the approved source revision and the
complete producer/module hashes. Source checkouts must share the configured chezmoi
Git store, be clean and committed, and retain the approved executable/template inputs.
Dated receipts and agent plans may advance without changing deployment inputs.
New input versions require a reviewed capability revision; an origin URL alone is
never source trust.

## Bootstrap

The bootstrap installs exactly two foundation files: the canonical
`$HOME/.local/bin/domus-shared-context` executable and its shared authorization
module. It does not install the context packet or agent adapters.

```sh
limen shared-context bootstrap-plan --source "$SOURCE_ROOT" --attempt-id "$ATTEMPT_ID"
limen shared-context bootstrap --plan "$PLAN" --authorization "$AUTHORIZATION" --signature "$SIGNATURE" --work-key "$WORK_KEY"
```

Planning is zero-write. The authorization request uses the existing
`domus.host_mutation_authorization.v2` contract, action `shared_context.bootstrap`,
the `domus-host-mutation` signature namespace, and the existing trusted signer
registry. The signed receipt must bind the complete plan, before-images, source
revision, attempt and digest. Bootstrap also requires the existing admitted context
outcome and an isolated source writer. No new principal role is granted.

The complete mutating operation has a 90-second wall bound. Only the two fixed
targets enter chezmoi apply; scripts and external refresh are excluded. Before-images
and failures remain in private bounded receipts under the Domus state root. An
existing attempt is never reused or overwritten. A failed or partial application
remains failed; it does not trigger deletion or silently become a verified receipt.

## Context application

The shared action policy routes both producer names and lookalikes to the exact
validator. Admission checks canonical installed bytes, module bytes, argument shape,
source identity, source hashes, destinations and before-images. Apply additionally
verifies the owner's signed authorization before acquiring the source writer.
Post-apply verify ignores only the old before-images while retaining the exact target,
mode, source, alias and synchronization bindings.

```sh
domus-shared-context plan --source "$SOURCE_ROOT" --attempt-id "$ATTEMPT_ID"
domus-shared-context apply --plan "$PLAN" --authorization "$AUTHORIZATION" --signature "$SIGNATURE"
domus-shared-context verify --plan "$PLAN"
```

The producer performs its own repeated authorization checks, bounded application,
before-image preservation and readback. The runtime gate adds no basename-only
allowlist, arbitrary destination override or pressure exemption. Bootstrap, source
merge, immutable-runtime adoption, file readback and fresh agent retrieval are
separate results. Every intended agent and supported child route must still pass
the owning private integration acceptance before overall completion is claimed.
