# Git parity T2 — deletion correction and recovery receipt

**Status:** correction to a superseded parity report. The prior report claimed "complete parity /
nothing left executable." That claim is withdrawn.
**Owners:** #2739 · #2781 · #2782 (existing estate-parity rail — this receipt does not claim a new
recovery attempt, admission, or estate acceptance).
**Scope:** repository ref topology only. No code, no runtime, no secret material.

## What happened

A parity audit classified 164 local branches and deleted 70 local refs on the reasoning that their
content was "preserved on the remote." That reasoning was sound in intent but the predicates that
implemented it were defective. 19 deletions crossed an agreed retention boundary. All 19 have been
restored at their original object IDs and verified by read-back.

## Defect classes

| # | Defect | Consequence |
|---|---|---|
| D1 | Existence treated as preservation. The `reach` predicate ran `rev-parse --verify` on the configured upstream and never tested whether that upstream *contained* the tip. Ten branches carry a self-referential upstream (`branch.<name>.remote = .`), so the branch certified itself preserved. | False-positive `PRESERVED` classification. |
| D2 | Silence treated as equivalence. `git cherry … 2>/dev/null \| grep -c '^+' \|\| true` yields `0` both when there are no differences **and** when the command fails. `git cherry` exits 128 on a nonexistent ref. | A failing verification was reported as a passing one. |
| D3 | Truncated identity. The deletion receipt stored 10-character OID prefixes. | Deletions were not bound to full identities. |
| D4 | Snapshot staleness. Worktree ownership was read once before the delete loop; remote evidence came from cached tracking refs captured earlier. | Concurrent-lane changes were invisible mid-run. |

D2 is the material one: after deleting `fix/jules-rolling-observation-20260918`, the audit re-ran
`git cherry` **against the ref it had just deleted**, suppressed the 128, read the empty output as
"0 unlanded," and reported the content as landed in `main`. That result was not evidence.

## Boundary violations and restoration

Two populations were to be retained:

1. **Pre-D3 lineage** — 48 branches quarantined in place, publish nothing.
2. **Branches with an open PR** — owned by the integration rail.

19 deletions crossed those boundaries:

- 18 branches from the pre-D3 lineage
- 1 branch carrying an open PR: `codex/context-runtime-skills-20261016` (#2867)

All 19 were restored via `git update-ref` at their recorded full OIDs (never by name resolution),
then verified by read-back. **19/19 present at recorded OID, 0 mismatches.**

## Recoverability of the remaining 51

- 51/51 objects still present in the local object store
- 70/70 original OIDs advertised by a named remote reference (`refs/pull/<N>/head`)

Ref deletion removes the ref, not the object. Nothing was lost. The harm was procedural, not data.

## Correction to an environmental claim

An earlier report stated the conduct broker was "unavailable." That was wrong. It was
**unconfigured in the agent's shell**; the broker responded normally once the documented credential
path (`scripts/set-credential.sh --check`, credentials in `~/.limen.env`) was loaded. The agent
did not attempt that bootstrap, then attributed the failure to the service. Native fanout was
available throughout.

## Standing correction for the parity predicate

Any future parity classification must test, for each local branch tip:

1. containment in a **remote** ref — `git merge-base --is-ancestor <tip> <remote-ref>` — never
   `rev-parse` existence, and never a self-referential upstream;
2. equality with a `refs/pull/*/head` advertisement (GitHub retains PR heads after branch deletion);
3. squash patch-equivalence computed with an **explicit exit-status check**, never inferred from
   empty output;
4. full 40-character OIDs throughout;
5. worktree ownership re-read immediately before each mutation, not snapshotted.

## Residuals for the owner

- 2 closed-unmerged PRs remain unresolved: `fix/jules-rolling-observation-20260918` (#2682) and
  `work/recovery-isolation-20260908` (#2576). Neither branch is landed. Both refs are restored.
- `work/spine-closeout-successor-20260926` (#2756) — see #2761, which references merged #2759.
  Not resolved by this receipt.
- `git branch -D` removes the branch reflog, so "reversible via reflog" was an incorrect assurance.
  Reversibility here rests on remote advertisement and the local object store, both verified above.

## Evidence

Recovery ledger (70 rows, full OIDs, named remote refs, PR state, quarantine epoch) and the
restoration log are retained with SHA-256 digests. See the companion artifacts referenced in the PR
body.