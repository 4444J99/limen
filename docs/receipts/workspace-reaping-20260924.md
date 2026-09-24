# Workspace reaping receipt — 2026-09-24

Scope: workspace repos outside `public-record-data-scrapper` and `prds-work`. PRDS was excluded from all generated-state, clone, branch, and worktree cleanup passes.

## Completed

- Reaped 68 local branch refs across the targeted public repositories: 61 refs were revalidated against their repository's current default branch or merged PR state; seven closed-but-unmerged refs were removed only after live GitHub state showed each local tip exactly matching its retained pull-request head. The final three exact-head acceptances were peer-audited PR #952 (`95a9034dcf91c72dd955cf13a245f6ec0ad4aaf2`), Limen PR #2597 (`12975f73f0ea2ba04ae71f998123e4f9ad0f26df`), and Limen PR #2608 (`f8f31158fbc859cd8c22b113d927e92800379d5c`). No remote branch was deleted.
- Reclaimed seven worktrees across the workspace after fresh clean/idle and remote custody checks: four in the first exact-manifest batch, then Limen `engine-accepted-20260915` (clean and merged), `levers-triage` (clean and pushed), and `registry-gap-filling-20260915` (clean and pushed). The last three were applied against manifest SHA `42bdac7c7bb7d17e814b7248f2410cbc53df0ecfd6b232fd89b607ef1dcfb456`.
- Removed two clean, remote-backed mirror clones in the earlier exact clone-reaper pass.
- Removed 827.9 MiB of ignored, regenerable build and cache directories from 37 non-PRDS repository roots. The pass skipped one live-process root and 24 roots containing private or agent-runtime custody. These generated files were local cache data, not Git history or source files.
- Re-ran the Limen reclaimer after generated-state cleanup. It found three eligible worktrees and removed all three; 77 other roots remained protected by dirty state, unpushed commits, recent activity, active processes, or ignored-payload custody uncertainty.

## Recurrence finding

Branch and worktree cleanup had been left to separate manual passes, while new lanes continued to create full working trees and preserve generated build state. The landed-ref reaper and exact-manifest worktree reclaimer remove only backed, inactive work. PR #2709 adds a persistent low-storage latch to Limen's worktree admission so a drop below 50 GiB closes new worktree creation until free space reaches 200 GiB again.

## Remaining state

The Data volume still reported 50 GiB available after deleting the generated files. The two internal APFS snapshots remain as directed and are retaining blocks. Private documents, agent session histories, application containers, unknown ignored payloads, and work with unpushed commits were preserved. The cleanup therefore did not reach the 200 GiB target.

PR #2709 is at `10ee31bdc27fec7d32af9e28fc2eddf0ee641c1f`. Its CI build jobs passed, but the required `pr-gate` failed on the unrelated `positioning-foundry-technical-readiness-public-live` check with `live GitHub observation failed closed`. The change remains unmerged and the Limen runtime has not deployed it.

## Follow-up tranche — 2026-09-24

- A nested-root census found 76 Git admin roots. PRDS paths and roots inside private/custody estates were excluded from mutation.
- The GitHub-backed landed-ref reaper completed 41 public-root passes before a later slow query was interrupted. It removed 49 local refs, each proven landed on the remote default branch or covered by a merged PR and the standing landed-ref grant. It deleted no remote branches. A second, ancestry-only pass covered all 61 eligible public roots and removed no additional refs; local-only, open, advanced, and otherwise unproven refs were retained.
- A fresh Limen worktree check scanned 77 roots and found zero eligible worktrees. A fresh clone-reaper check found zero eligible clones and kept 80 paths for active-process, core, dirty/untracked, recent, linked-worktree, submodule, ignored-data, or unpushed-object reasons.
- Homebrew's own `cleanup --prune=all` removed about 3.9 GiB of regenerable downloads and formula cache. This was non-Git cache data. The Data volume then reported 48 GiB available; it did not show a net increase, consistent with the retained APFS snapshots pinning blocks and concurrent disk activity. The snapshots remain unchanged.
- No private documents, agent session history, application-container content, or PRDS checkout was removed. The 200 GiB target remains unmet; no further source or worktree candidate passed the existing custody/parity predicates in this tranche.
