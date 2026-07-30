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

Both registrations are tied to the volume UUIDs in
`docs/storage-evacuation-inventory-20260727.json` and require an owner-recorded
stable whole-media identity (`device_<digest>`) derived from a physical media
UUID, integrated-device path, or USB hardware serial. BSD disk numbers remain
private observational evidence, not durable identity. The tracked target
registry deliberately leaves both stable identities unset: capacity remains
red until an authorized owner records them. Registration is not a claim that a
current live proof exists.

## Contract

The entrypoint acquires the sole `heavy` lease once. Admission denial is a
path-free blocker and invokes no custody rail. While the lease is held it:

1. validates both registered mounts, stable physical identities, volume UUIDs,
   target ancestry, and physical independence;
2. runs a fresh underlying `estate-audit-custody --check`, so the generated-root
   denominator is discovered rather than pinned;
3. independently re-derives that plan in memory and rejects a target that
   overlaps any generated source root;
4. applies the exact plan on `archive4t`, then on `t7recovery`, using only the
   existing single-rail executable; each apply already performs one complete
   restore before returning;
5. requires both rail receipts to cover the same working-payload manifest;
6. writes one byte-identical mode-`0600` **prepared** record into both custody
   roots, reopens both bounded records, and only then emits a terminal path-free
   projection.

Every stored record remains explicitly nonterminal: it has `status: prepared`
and `requires_peer_match: true`, and it contains neither
`restoration_passed` nor `copy_count: 2`. A unilateral copy after an interrupted
cross-device write therefore cannot claim completion. An idempotent rerun
converges and reopens both exact records before the in-process projection may
claim two restored copies.

A repeated run still performs the fresh check and one full restore per rail,
but the underlying applies and prepared records must report `changed:false`.
The single-rail executable rechecks the expected volume UUID and stable
physical identity around every target mutation/restore boundary. The paired
layer repeats that check before and after each child apply and prepared-record
write. Child output and all receipt/registry reads are fixed-size bounded.
The projection contains only digests, counts, registered target references,
and boolean proof fields; detailed paths and device identities remain in the
two private prepared records.

## Authorized invocation

The actual run is intentionally not part of ordinary verification. It is
currently fail-closed because the stable physical identities are unregistered.
After the authorized owner records both identities, it writes to two external
devices and may be entered only with separate storage authorization and a sole
heavy lease:

```bash
python3 scripts/estate-audit-paired-custody.py --apply --json
```

No ARCA command, source retirement, deletion, or reclaim is reachable from this
entrypoint.
