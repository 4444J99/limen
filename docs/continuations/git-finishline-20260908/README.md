# Git recovery and correction owner — 2026-09-08

This continuation owns the human request to finish the 26-stash archive, the preserved PR
branches, and the nine deleted remote refs. It keeps custody, code correction, and landing
as separate claims with executable evidence.

The original cleanup transcript reported ten open PRs, but its before-and-after GitHub
receipts both contained **nine**. `pr-custody.json` preserves that exact denominator and
all nine original heads. New PRs created by parallel sessions are outside this cohort.
PR2565 subsequently merged through its PSP owner. Active sibling work remains protected.

## Custody and restoration

`stash-custody.json` records all 26 commit, worktree-tree, index-parent, and untracked-tree
identities. Each restored into a new empty bare repository using only the original bundle.
The original archive remains unchanged; no stashes were applied to the current worktree.

`branch-custody.json` records every deleted tip and its successor receipt. Eight tips are
recoverable from the original archive. The keeper's deleted board-projection tip was absent
from that bundle, so it now has a separate private companion archive, independently restored
and checksummed. The keeper remains the owner of canonical task state: this historical
projection is preservation evidence and must never be replayed as a board mutation.

Some original PR heads postdate the original archive. A small incremental PR-head
companion now preserves those exact tips; the predicate restores it after the original
archive and verifies all nine heads without access to the source object store.

Archives remain private local custody. They contain historical material and are never
committed or uploaded to this public repository. Their neutral filenames and checksums
identify the restore inputs without publishing private source bodies.

Run from the repository root, supplying the three private archive locations:

```sh
python3 docs/continuations/git-finishline-20260908/verify-custody.py --stash-bundle /path/to/limen-stash-archive-20260908.bundle --board-bundle /path/to/board-projection-20260908.bundle --pr-bundle /path/to/original-pr-heads-20260908.bundle
```

The predicate verifies checksums, reconstructs objects without source alternates, checks
all stash trees and parents, and proves recoverability of all nine deleted tips and all nine original PR heads. It does
not infer merge, deployment, or safe deletion from archive presence.

## Corrected successor

The semantic audit found one missing substantive stash intent: security headers. Index22
is now represented at actual Pages/Worker serving boundaries and the supported FastAPI
adapter. Its ineffective static-export Next headers configuration remains historical.
The manifest records a distinct evidence-backed disposition for every stash.

The recovery successor incorporates PR2564, preserves PR2550's distinct historical
receipts under `history/`, and incorporates the corrected serial governor from PR2552.
No source archive is treated as a current-state receipt. Historical architectural and
end-to-end simulation reports explicitly withdraw unsupported live verification claims.

Corrections bind required checks to the immutable default SHA and required workflow
source, consume the collector's actual custody schema, freeze reserved budget amounts,
validate repository-specific cursor generations, and require authenticated broker ownership
for notification execution. Regression tests exercise production paths with local fixtures;
they do not send notifications or activate schedulers.

The deleted-branch audit also owns surviving review findings from PR2527 and PR2529.
Their dispositions and correction evidence are recorded in `review-dispositions.json`.
Historical privacy-removal debt stays with issue2537; no removed sensitive history is republished.

## Remaining delivery authority

`receipt.json` records the actual checks and remote successor. A green custody predicate
does not authorize declaring every source PR merged. The owning source predicate and an
exact-head GitHub merge receipt decide that status.

PR2553 remains owned by its reader-mode pilot. Its former schema dependency #16 was
superseded by merged schema-definitions#17; engine#174 was superseded by open engine#175,
and editorial-standards#12 depends on that engine generation. The original PR also requires
GitHub About metadata consistent with its evidence. Draft preservation does not satisfy
the strict schema/runtime, identity, evidence, or metadata acceptance predicates.

Resume the finite correction lane by checking out the remote successor named in
`receipt.json`, reading this file and `workstream.json`, and running the scoped gate once
for any changed tree. Host admission is authoritative for heavy checks. Existing successful
shards remain evidence until their inputs change; do not poll CI or repeatedly rewrite PRs.


The single continuation launch command, from a checkout of the published successor, is:

```sh
bash docs/continuations/git-finishline-20260908/launch.sh
```

The wrapper recreates the canonical four-hour capsule from the preserved remote branch,
then uses its live-derived native launch. `--prepare-only` validates capsule preparation
without starting another agent. It preserves the existing admitted deadline on re-entry.
