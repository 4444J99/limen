# Paired generated-root custody

`scripts/estate-audit-paired-custody.py` composes the existing
`estate-audit-custody` rail into one admission-guarded proof across the two
registered physical devices. It is preservation-only: it never retires,
deletes, reclaims, signals, restarts, or changes host configuration.

The exact target registry is
`institutio/governance/estate-audit-custody-targets.json`. It binds:

- `archive4t` to
  `/Volumes/Archive4T/limen-private/estate-audit-git-custody`;
- `t7recovery` to
  `/Volumes/T7Recovery/limen-private/estate-audit-git-custody`.

Both registrations are tied to the device, physical-device, and volume-UUID
identities in `docs/storage-evacuation-inventory-20260727.json`. Registration is
not a claim that a current live proof exists. Every run revalidates the two
mounted identities and their physical independence before any custody write.

## Contract

The entrypoint acquires the sole `heavy` lease once. Admission denial is a
path-free blocker and invokes no custody rail. While the lease is held it:

1. validates both registered mounts, identities, target ancestry, and physical
   independence;
2. runs a fresh underlying `estate-audit-custody --check`, so the generated-root
   denominator is discovered rather than pinned;
3. independently re-derives that plan in memory and rejects a target that
   overlaps any generated source root;
4. applies and full-restores the exact plan on `archive4t`, then on
   `t7recovery`, using only the existing single-rail executable;
5. re-verifies each receipt through another fresh full restore;
6. writes one byte-identical mode-`0600` paired receipt into both custody roots
   and emits a path-free projection.

A private paired receipt is terminal only when the same bytes exist at both
registered roots. A unilateral copy after an interrupted cross-device write is
recoverable staging evidence, not a completed two-copy proof; an idempotent
rerun converges the pair before a terminal projection can be emitted.

A repeated run still performs the fresh check and both full restore proofs, but
the underlying applies and paired receipt must report `changed:false`. The
projection contains only digests, counts, registered target references, and
boolean proof fields; detailed paths and device identities remain in the two
private receipts.

## Authorized invocation

The actual run is intentionally not part of ordinary verification. It writes
to two external devices and must be entered only after the owner authorizes the
storage operation and host admission allows the sole heavy lease:

```bash
python3 scripts/estate-audit-paired-custody.py --apply --json
```

No ARCA command, source retirement, deletion, or reclaim is reachable from this
entrypoint.
