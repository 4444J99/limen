# Prima Materia evacuation continuation

## Objective

Continue the single-purpose evacuation workstream from the exact remote head
of Limen PR #1604 until the live fixed-point predicate in
`.codex/plans/2026-07-27-finish-laptop-evacuation-v2.md` passes. The frozen
inventory denominator is bound to SHA-256
`5034e1ca795fd1900f05f34068edb028da569bebc28d020e211a35f7abfa5be6`.

Limen PR #1604 owns the coordinator, contracts, custody/reclaim rails, and
redacted projections. Merged Domus PR #354 owns the source materializer for
standing File Provider authority at reviewed head
`b45828490a03113d7249bf6b50d504435b514f81` and squash merge
`45760db8334ced1e99b112e45dabadb7d3f7df23`. Historical fixed-GiB plans and
receipts remain immutable evidence, never present execution authority.

## Authorities and prohibitions

- Proceed without confirmation for in-scope reversible inspection,
  encryption, chunking, restore probes, exact-head remote custody, redacted
  receipts, and scoped verification.
- Retain gates for destructive personal-data changes, credentials, spending,
  public sends, and runtime or host mutations.
- Use only PR #1604 for Limen control-plane source. Do not mutate the dirty main
  checkout, create another Limen control-plane PR, force-push, rewrite
  historical receipts, or resume Omega.
- Never repeat an external effect during replay without fresh effect
  authority. Never treat same-device volumes as independent custody.
- Reclaim only through the canonical SHA-bound exact-plan rail after live
  owner, content, local-ref, metadata, device-independence, and restore checks.

## First probes

1. Fetch PR #1604 and PR #354 from their remote owners; record their exact
   heads and current CI/review state.
2. Validate `workstream.json` and admit its finite runway only after live host
   admission is green.
3. Recompute the repository/File Provider/personal-root census, mounted device
   identities, active processes, source-registry digest, and selected task
   graph. New discoveries become explicit next-wave debt.
4. Evaluate the dynamic resource envelope from live RAM, swap, updater, APFS
   churn, error telemetry, task claims, staging, and rollback lifetimes.
5. Reuse unchanged exact-head predicate receipts. Run only newly implicated
   scoped checks.

## Current nonterminal evidence

The 2026-07-28 dirty-primary census is not a completion receipt. Local `main`
at `681f0294` is remotely preserved, but the checkout still has 4,207 status
entries: seven tracked projections and 4,200 untracked files. Of those,
4,191 files belong to the recipe-owned `.agent-runtime` root (1.1 GiB
aggregate). Protected peer and service CWDs remain active there, so the
canonical reclaimer must continue to reject the root. Do not hide this
denominator with ignore rules or purge it while an owner remains active.

## Executable terminal predicate

The workstream closes only when every frozen root has terminal remote or
custody evidence; every source in the frozen wave has a passing adapter,
completeness, and restoration predicate; selected private material restores
from two independent custody devices; every removed repository reconstructs
with all refs and working overlays; local repository and stale-registration
censuses are zero; a second reclaim plan has zero automatically safe roots;
the resource envelope stays nonnegative across its telemetry horizon; and
Omega remains stopped.

Every nonterminal leaf must remain with its remote PR, registry owner, exact
blocker, executable predicate, and next command. If the finite runway reaches
its boundary first, emit a successor capsule from the then-current remote head
without resetting this contract.

## Materialize or resume

If the existing isolated worktree is present and inactive, resume its private
capsule from the Limen owner checkout:

```bash
bash .worktrees/finish-laptop-evacuation-20260727/.limen-workstream/kickstart.sh
```

After that disposable worktree has been safely reaped, hydrate from the remote
receipt with provider selection left to live capability discovery:

```bash
git fetch origin work/finish-laptop-evacuation-20260727
limen workstream . finish-laptop-evacuation-20260727 --from origin/work/finish-laptop-evacuation-20260727 --workstream lifecycle-recovery --runway 12h --agent auto --prompt 'Read docs/continuations/finish-laptop-evacuation-20260727/README.md and its workstream.json. Re-derive live predicates, preserve owner and authority boundaries, and continue to the Prima Materia fixed point or emit a finite successor before zero.'
```
