# Personal Control Plane Transfer Capsule

This capsule governs the durable move of repository ID `1255213941` from `organvm/limen` to
`4444J99/limen`. Anthony explicitly delegated the technical transfer, merge, activation,
deployment, installation, and restart effects to the system lane on 2026-08-25. It does not
authorize a mirror, duplicate registry, budget change, paid runner, overage, or predicate bypass.

The content-hashed pre-transfer preflight snapshot is summarized in
[public-capture-receipt.json](public-capture-receipt.json). It proves the capture machinery and its
private counterpart includes the
complete Git bundle and restore proof, every ref and open-PR head, review threads, releases, issue
denominator and assignments, labels, rulesets, branch protection, workflow and Actions settings,
environment/secret/variable names, hooks, keys, App census result, and protected-lane snapshots.
Private source, credentials, process commands, custody metadata, and protected-lane digests are not
published.

The transfer is complete. [public-postflight-receipt.json](public-postflight-receipt.json) records
the redacted acceptance proof: the stable repository ID, canonical coordinate and redirect, exact
denominators, verified restore bundle, semantic issue-type restoration, workflow freeze, and
attributed protected-lane deltas. The private preflight/postflight manifests, their sidecars, and
the private attribution receipt remain the authoritative detailed evidence.

Recovery CI is the one restored transfer-sensitive workflow. Its first manual run on the
transferred default SHA proved real public-runner admission and executed steps without a retry;
[public-ci-admission-receipt.json](public-ci-admission-receipt.json) records that proof and the
post-admission aggregate fixture failure now owned by the combined recovery head.

## One launch command

From the combined recovery worktree, run the scoped resolver on the exact unchanged head:

```bash
scripts/verify-scoped.sh
```

Its unchanged green shard receipts remain valid; only an observed failed shard is corrected and
rerun. App-dependent workflows remain fail-closed while the exact target installation is
unavailable.

## Delegated execution rail

1. Recovery CI enable and default-SHA runner admission are complete. Preserve the single-run
   receipt; do not retry the failed default-head aggregate.
2. Correct the observed aggregate fixture and live profile-count shards in the combined #2543
   batch, run the deterministic worker against that exact head, and clear every current/outdated
   review thread.
3. Continue through [runtime.md](runtime.md) and [closeout.md](closeout.md). The system lane merges via
   `scripts/await-pr.sh`, activates the heartbeat plan, installs merged artifacts, deploys, and
   re-enables effectful workflows only as their exact predicates pass.
