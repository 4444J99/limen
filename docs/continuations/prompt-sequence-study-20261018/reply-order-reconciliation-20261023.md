# Native reply-order correction

Owner: [#3056](https://github.com/4444J99/limen/issues/3056); integration [#3087](https://github.com/4444J99/limen/pull/3087);
coordinating closeout [#3173](https://github.com/4444J99/limen/issues/3173).

The existing three regression cases failed locally before repair. The preserved
proposed patch now filters replies by strict source order within their native turn
before choosing explicit finals or a commentary fallback. Excluded preceding
references remain visible, including rollout source-line provenance. All 15 projection
fixtures pass after repair. The prepared helper also creates its private evidence
parent in a fresh isolated checkout; its first apply attempt stopped before tests
because that directory did not exist. No original source or snapshot was overwritten.

The [machine-readable observation](reply-order-reconciliation-20261023.json) binds a
fresh, read-only replay of all 19 affected columns. All decoded source hashes match
their earlier snapshots, and each source's inode, size and modification time remains
stable across its read. Every projected input retains the same source reference,
text and structured parts. The replay uses a 20-second per-source deadline, a 4 MiB
record limit, a 128 MiB source limit and a 240-second process wall.

| Measurement | Before | Corrected derivative |
| --- | ---: | ---: |
| Earlier replies attached to later inputs | 29 | 0 |
| Changed response positions | 28 affected | 28 corrected |
| Source columns replayed | 19 | 19 |
| Displayed catalog columns | 382 | 382 |
| Displayed prompt rows | 3,500 | 3,500 |

The original snapshot and HTML hashes are unchanged. The corrected snapshot and
catalog are separate create-only artifacts in the private custody staging owner.
The renderer accepts explicit input/output paths and refuses an existing destination;
it no longer requires overwriting the frozen catalog to inspect a correction.
The actual derivative passes its DOM/render-logic check: all 3,500 prompt texts survive,
all 37 lineage views render, seven captured parents remain linked, six managed inputs
retain their exclusion labels and all 21 current proposal names remain displayed.
Browser visual inspection was attempted once. The browser security policy rejected
the local HTML URL because only HTTP(S) protocols are allowed and explicitly forbade
workarounds. No alternate browser surface or transport was used. This acceptance
gap remains with #3056; the DOM check is not presented as visual inspection.

Shared-turn causal uncertainty, incomplete retention, missing source bodies,
single-coder research limits and original task acceptance remain explicit. This
correction proves source-order repair for the affected columns. It does not prove
whole-corpus equivalence, independent intent coding, command installation, native
session release or independent restoration custody. Historical findings and their
frozen artifacts remain unchanged evidence of the pre-repair state.
