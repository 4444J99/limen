# Finish the Laptop Evacuation

## Objective

End the repeated recovery loop by treating the whole laptop, not the Limen repository, as the
storage denominator. Limen is only the canonical planner and durable receipt surface.

The terminal predicate is:

- stop physical deletion at or above 220 GiB available on `/System/Volumes/Data`;
- obtain two readings of at least 200 GiB available, separated by at least 30 minutes;
- leave zero repository checkouts on the laptop: every retained Git object must be reachable from
  its remote owner, and a fresh clone plus the tracked receipts must reconstruct the intended
  working state;
- make the canonical worktree reclaimer report zero automatically safe roots;
- preserve every dirty, unpushed, locked, active, unique, or restoration-unproven root;
- leave no removed root referenced by Git worktree metadata or an active process.

## Frozen authority

The operator's 2026-07-27 authorization covers deletion or eviction only for exact-plan local
copies whose remote or external custody and restoration predicates pass. It does not cover
credentials, paid spending, public sending, or deletion of unique or restoration-unproven personal
data. The old `full_non_destructive` capsule does not narrow this authority.

The operator's later correction tightens the custody predicate. Two unencrypted raw copies are
necessary staging evidence, but they are not terminal custody for personal, bulk, non-Git, dirty,
or unpushed material. Before its internal source may be deleted, that material must also pass the
canonical encrypted, chunked, content-addressed capture and restoration pipeline. Exact remote Git
custody and classified generated/reinstallable material are the only exemptions from that
encryption-and-chunking gate; both still require an exact signed reclaim plan. Material already
reclaimed into two raw staging copies remains open on the processing denominator until its
encrypted archive restores from both independent drives. Raw staging is removed only after those
two encrypted restore predicates pass.

The storage denominator is frozen to the signed machine inventory produced by this workstream.
Unrelated work discovered after that inventory receives a separate owner and cannot enlarge this
lane.

## Sweeps

### 1. Stop admission and reap remote-preserved checkouts

- Fence new Institutional Omega and successor admission without killing S18.
- Preserve PRs 1599 through 1601 and S18's final receipt.
- Reap clean, inactive local roots whose exact HEAD is reachable from a remote ref.
- Re-run the accepted planner until its candidate set is empty.

### 2. Freeze the whole-machine byte inventory

- Measure internal filesystem roots, user data, application state, caches, File Provider data, and
  agent/runtime roots.
- Record byte size, physical device, owner, custody evidence, process/worktree state, selected
  action, and the exact source plan or receipt.
- Reconcile at least 183 GiB of safe reclaim capacity, including margin for ongoing churn.
- Treat Archive4T and T7Recovery as independent copies; do not count Archive4T, Ingress, Scratch,
  and TM-Mac as independent because they share one physical disk.

### 3. Repair the Codex prerequisite

- In the Domus source owner, make relocated `CODEX_HOME` materialize canonical Codex hooks while
  preserving runtime-owned authentication, databases, and session state.
- Make read-only admission return before durable owner-ancestry resolution.
- Make missing generic agent identity fail closed instead of defaulting to Claude.
- Never edit generated `.agent-runtime/codex` or deployed home files directly.

### 4. Establish custody

- Revalidate generated-root custody against the frozen inventory.
- Put bulk, personal, non-Git, dirty, and unpushed material through the canonical encrypted,
  chunked, content-addressed capture before internal deletion.
- Materialize the final owner-organized encrypted archive on Archive4T and an independently
  verified recovery copy on T7Recovery.
- Hash both encrypted copies, perform full restoration checks, and track redacted receipts.
- Treat raw content-addressed copies as temporary staging, not as the final external layout.
  Remove the raw staging objects only after both encrypted archives restore and the owner-indexed
  manifest accounts for every source.
- Keep Backblaze repair separate; it does not block reclaim after two independent local copies and
  encrypted restoration proof exist.

### 5. Apply bounded reclaim

- Use only canonical reclaimers with their exact checked plan SHA.
- Set `LIMEN_RECLAIM_GENERATED=0`; generated worktree state enters only through the exact external
  custody contract.
- Apply one bounded batch at a time and measure available space after each batch.
- Remove only exact remote-preserved checkouts, restoration-proven generated/cache material,
  two-copy encrypted-and-restored bulk duplicates, and signed safely evictable File Provider
  material whose current metadata is bound to the encrypted capture.
- Stop physical deletion once 220 GiB is available.

### 6. Prove the fixed point

- Reconcile and push the exact heads of the final active Limen and victoroff-os worktrees, then
  remove those checkouts through Git's worktree/checkout ownership surface after their current
  processes exit.
- Require a fresh whole-laptop repository scan to return zero local checkouts.
- Prove a clean reconstruction from each remote owner and the tracked restore index without
  depending on any laptop-only file.
- Require a second canonical plan with zero automatically safe roots.
- Verify Git metadata and active-process references after removal.
- Record the retained hot-cache and owner-organized external-drive manifests.
- Require zero unprocessed raw staging objects: every temporary object is either represented by
  two restore-tested encrypted archives and removed, or retained with an exact owner and failed
  predicate.
- Record the first reading at or above 200 GiB, then a second qualifying reading at least 30
  minutes later.
- Remove the Omega admission fence only after every predicate above is green.

## Initial exact receipts

- Exact merged base: `16cbe1dc9f47cbfebb629699220d3ee1af37e7df`.
- First exact-remote checkout batch: plan
  `3b51019d29f2848e287f065c1b46d1cc3fef92d3996eff8d8df835aabd6cd72f`, 25 roots.
- Second checkout batch: plan
  `785bd45b0476f0103914bc2cedbab25f79b0cd87f4d5dce626b47a0a42ad5a7f`, 1 root.
- Tool-cache batch: plan
  `7ffe4c53e660e7f88192592dcd2cd01938e6d775ebf04e7acd2ebc0cdd1f74e8`, 127.3 MiB.
- Generated dependency-cache batch: plan
  `195fda50c9d52daa742eaea2f403d7bb26ea821e366997514f5db1b2d4904871`,
  3,634,028,544 logical bytes.
- Current generated-root custody plan:
  `e1ca7a5c3b4ec41c21d55b9be5dbe556510ded57117322679a7112ee1aed59d9`,
  56 roots, 4 repositories, 7 exact heads, restoration passed.
- Current zero-safe-root worktree plan:
  `4677b937f2a7ac1590cfe8c8eda96bc272ec816881a984cdd7e85d514a393520`.
