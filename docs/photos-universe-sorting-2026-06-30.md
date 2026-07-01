# Photos Universe Sorting Receipt - 2026-06-30

Generated: `2026-06-30T17:31:39Z`

This receipt records the virtual sorting pass for the active Photos Universe lane. It is
proof-first only: no Photos library internals were edited and no media files were deleted,
moved, imported, evicted, or album-mutated.

## Duplicate Proof Batch

Command gate:

```bash
python3 scripts/photos-duplicate-proof.py --limit-groups 25 --dry-run
python3 scripts/photos-duplicate-proof.py --limit-groups 25 --receipt docs/photos-universe-duplicate-proof-2026-06-29.json
python3 scripts/photos-duplicate-proof.py --limit-groups 50 --dry-run
python3 scripts/photos-duplicate-proof.py --limit-groups 50 --receipt docs/photos-universe-duplicate-proof-2026-06-29.json
```

Aggregate result:

- Candidate groups total: `19308`
- Hash-proof groups processed this run: `50`
- Hash-proof groups processed total: `80`
- Hash-matching duplicate groups: `79`
- Hash-rejected candidate groups: `1`
- Bytes in hash-proven duplicate groups: `663972891`
- Status counts: `all_available_match=79`, `hash_mismatch=1`
- Public receipt: `docs/photos-universe-duplicate-proof-2026-06-29.json`
- Private resumable state: `.limen-private/photos-universe/20260629-182431/duplicate-proof-state.json`

## Metadata Atomization Preview

Command gate:

```bash
LIMEN_ROOT=/Users/4jp/Workspace/photos-universe-20260629-182431 \
  python3 scripts/media-atomize.py --photos-metadata --limit 25
LIMEN_ROOT=/Users/4jp/Workspace/photos-universe-20260629-182431 \
  python3 scripts/media-atomize.py --photos-metadata --limit 50
```

Aggregate result:

- Photos assets previewed: `50`
- Preview atoms: `50`
- Screenshot-flagged preview assets: `32`
- Write mode: `preview`

## Logical Views Opened

These are logical/proof views only, not filesystem or Photos-library mutations:

- `hash_proven_duplicates`: duplicate candidate groups with matching SHA-256 evidence.
- `hash_rejected_candidates`: duplicate candidate groups rejected by bounded SHA-256 evidence.
- `screenshot_heavy_recent_assets`: read-only Photos metadata preview where `32/50` assets were
  screenshot-flagged.
- `aggregate_public_receipts`: tracked receipts that contain counts/classes only.
- `private_full_evidence`: ignored private state with raw paths and hashes for future proof batches.

## Safety Boundary

- Full media paths and hashes remain out of tracked public receipts.
- Duplicate proof is evidence, not deletion authorization.
- Album creation, delete/move operations, and Photos-library writes remain later human gates.
