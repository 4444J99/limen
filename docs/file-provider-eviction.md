# File Provider eviction

`agent-state-metabolism.py cloudkit-materialized` preserves the finite materialized iCloud set in
encrypted Git and external custody before asking the Domus host cartridge to reclaim local blocks.
The integration never invokes `brctl`: it discovers `domus-file-provider-evict` through `PATH` and
fails closed when the supported adapter is absent.

## Resume contract

On `--resume`, Limen verifies and decrypts the immutable atom packs, reconstructs the original
captured file-entry set, and validates the live logical namespace. It does not make a new plan from
only the files that remain materialized. Dataless placeholders are not opened; missing files,
changed metadata, and changed content in the active batch fail before File Provider runs.

Progress defaults to a private sibling of `--private-receipt` named
`<stem>.file-provider-progress.json`. It contains only custody bindings, item hashes, status values,
and hashed provider/domain identities. A successful partial batch is not repeated. Finder metadata
such as `.DS_Store` is retained and explicitly accounted for.

## Standing campaign authority

For a corpus larger than one batch, prepare one path-free authorization request
that binds the complete immutable item-hash set:

```bash
python3 scripts/agent-state-metabolism.py cloudkit-materialized <custody-name> \
  --root <icloud-root> --vault-root <vault> --external-root <external-custody> \
  --private-receipt <private-receipt> --run-id <run-id> --resume \
  --prepare-eviction-campaign-authorization <private-authorization.json> \
  --eviction-authorizer <allowed-signers-principal>
```

Sign that exact canonical receipt with the registered OpenSSH identity and
namespace `domus-host-mutation` once. Limen and the Domus adapter migrate the
signed campaign into `domus.host_mutation_standing_authority.v1` without
another signing prompt. The standing parent has no expiry or attempt count;
it remains valid across batches, process restarts, and changed plan hashes
until an exact local revocation receipt names its opaque authority ID.

Each apply invocation derives a child capability bound to the standing
authority, action, current exact plan SHA-256, batch attempt ID, and restored
item-hash set. Continue to supply the private standing authorization and its
original migration signature:

```bash
python3 scripts/agent-state-metabolism.py cloudkit-materialized <custody-name> \
  --root <icloud-root> --vault-root <vault> --external-root <external-custody> \
  --private-receipt <private-receipt> --run-id <run-id> --resume --evict \
  --eviction-authorization <private-authorization.json> \
  --eviction-signature <private-authorization.json.sig>
```

Each invocation is serial, at most 1,000 items, and at most 15 minutes. Raw item URLs cross only the
adapter's stdin. Limen stages the next ordered batch in its private progress
ledger before mutation and never selects a recorded success again. Standing
authority admits only hashes from the restored corpus and exact-plan child;
explicit revocation fails closed. Credentials remain owner-native references
and never enter the request, progress ledger, or tracked receipt.
Stop on any partial or unexpected result; verified successes remain in private
progress for the next invocation with the same campaign signature.

`--prepare-eviction-authorization` retains the narrower legacy mode for a
single exact batch. It requires a new exact authorization before any later
batch and should not be used for a multi-batch restored corpus.

`source_retired` becomes true only when every eligible captured item has a verified `evicted` or
`already_dataless` receipt, every such item remains dataless, and retained metadata is accounted for.
