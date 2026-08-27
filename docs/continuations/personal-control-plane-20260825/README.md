# Personal Control Plane Transfer Capsule

This capsule governs the durable move of repository ID `1255213941` from `organvm/limen` to
`4444J99/limen`. Anthony explicitly delegated the technical transfer, merge, activation,
deployment, installation, and restart effects to the system lane on 2026-08-25. It does not
authorize a mirror, duplicate registry, budget change, paid runner, overage, or predicate bypass.

The historical v2 pre-transfer snapshot is summarized in
[public-capture-receipt.json](public-capture-receipt.json). Its narrower evidence covers the
verified Git bundle, refs and then-open PR heads, then-open PR review threads, releases, issue
identity/assignment denominators, and the other transfer settings listed in that immutable receipt.
Neither that receipt nor its historical private manifest is retroactively expanded. The unmerged
manifest v3 interface now requires every open, closed, and merged PR head plus lifecycle/content
digests and fully paginated review threads/comments; it also requires issue lifecycle/content,
normalized milestone, and fully paginated comment evidence. Future public v3 receipts expose only
the resulting PR, review, and issue-comment denominators. Private source, credentials, process
commands, content, custody metadata, and protected-lane digests are not published.

The transfer is complete. [public-postflight-receipt.json](public-postflight-receipt.json) records
the redacted acceptance proof: the stable repository ID, canonical coordinate and redirect, exact
denominators, verified restore bundle, semantic issue-type restoration, workflow freeze, and
attributed protected-lane deltas. The private preflight/postflight manifests, their sidecars, and
the private attribution receipt remain the authoritative detailed evidence.

[public-access-receipt.json](public-access-receipt.json) records the separate live post-transfer
access predicate: zero direct grants, team grants, or pending invitations after excluding only the
personal repository owner's automatic access. The historical v2 transfer manifest did not contain
that denominator, so it is not retroactively inferred. Manifest v3 now makes the complete access
census and the `never_grant` policy mandatory before any future transfer or workflow restoration.

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
3. Continue through [runtime.md](runtime.md) and [closeout.md](closeout.md). The system lane submits
   one exact head through `scripts/merge-drain.py`, returns control, and activates the heartbeat
   plan only from a later repository-qualified `MERGED` receipt. It installs merged artifacts,
   deploys, and re-enables effectful workflows only as their exact predicates pass.
