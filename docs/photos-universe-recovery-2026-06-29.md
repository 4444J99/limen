# Photos Universe recovery receipt - 2026-06-29

This records the crash recovery boundary for the Photos Universe worktree. It is
redacted for Git: full media paths, raw inventories, and prompt/session bodies
are preserved only in the ignored private owner path.

## Private recovery bundle

- Full report bundle: `.limen-private/photos-universe/20260629-182431/report/`
- Recovered session receipts: `.limen-private/photos-universe/20260629-182431/session-receipts/`
- Private receipt manifest: `.limen-private/photos-universe/20260629-182431/session-receipts/SHA256SUMS`
- Session receipt count: 21
- Private permissions: owner-only

## Recovered report counts

- Media inventory rows: 193120
- Duplicate candidate groups: 19308
- Hash-proven duplicate groups in recovered report: 0

## Live local checks

Checked at `2026-06-30T01:22:12Z` (`2026-06-29 21:22:12 EDT`).

- Screenshot capture location: `~/Pictures/Screen Captures`
- Screenshot capture type: `png`
- LaunchAgent: `com.user.photos-screen-capture-importer`
- Importer target: `~/.local/bin/photos-screen-capture-importer.sh`
- LaunchAgent plist: valid and watching the screenshot capture directory
- Importer reinstall: not run, because the installed state verified clean
- Photos DB assets: 32230
- Photos DB internal resources: 166699
- Photos DB screenshot-flagged assets: 4812
- Archive4T personal-cloud-docs source: mounted and readable
- Archive4T doc atomizer dry run: 4 docs, 22 preview atoms, 1 PDF skipped because `pdftotext` is absent

## Safety boundary

- No Photos library internals were edited.
- No media files were deleted, moved, deduplicated, bulk-imported, or evicted.
- Duplicate proof is hash evidence only; any cleanup decision remains a later human gate.
- Public duplicate receipts must contain aggregate counts only, not full paths or hashes.

## Duplicate proof slice

- Proof helper: `scripts/photos-duplicate-proof.py`
- Private proof state: `.limen-private/photos-universe/20260629-182431/duplicate-proof-state.json`
- Public aggregate receipt: `docs/photos-universe-duplicate-proof-2026-06-29.json`
- Candidate groups processed in this slice: 5
- Hash-matching groups in this slice: 5
- Files deleted or moved: 0
