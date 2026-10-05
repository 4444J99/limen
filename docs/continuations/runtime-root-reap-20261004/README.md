# Runtime-root reap — 2026-10-04

Operator-assigned reap of three disposable local runtime roots under the Limen checkout:

- `/Users/4jp/Workspace/limen/.agent-runtime/codex/worktrees`
- `/Users/4jp/Workspace/limen/.worktrees`
- `/Users/4jp/Workspace/limen/.claude/worktrees`

Authorization is the operator's direct-session instruction of 2026-10-04, bound verbatim in
[`reclaim-scope.json`](reclaim-scope.json) and its tranche packets as
`limen.worktree_reclaim_scope.v1` packets.

Execution rail: `scripts/reclaim-worktrees.py --target … --scope-manifest …`, so every removal is
driven by a committed, remotely published, operator-scoped manifest rather than by ad hoc deletion.
Each removal additionally passes the tool's own gates — clean tree, live-remote reachability of
HEAD, all-local-ref remote proof for standalone clones, ignored-payload custody or reconstruction
proof, no active process cwd, and no protected-exclusion match.

Per-directory receipts, live remote parity evidence and measured disk deltas are in
[`receipt.json`](receipt.json).

Children are processed before their shared store: `c06-portfolio` before `580e/portfolio`;
`8eef/portfolio` before `b4ca/portfolio-psp-c06`; the nested `lady-macbeth-macbeth-followup-20260809`
before `speech-score-engine`.

## Outcome

**Status: INCOMPLETE — no completion claimed.** Two of three target containers are absent;
`.worktrees` is retained because its last entry fails its real dependency predicate.

| Target | Container | Contents |
| --- | --- | --- |
| `.agent-runtime/codex/worktrees` | **absent** | 7 entries reaped, incl. both shared stores after their children |
| `.claude/worktrees` | **absent** | 1 entry reaped; container released and removed |
| `.worktrees` | retained | 22 of 23 entries reaped; 1 remains, dependency-gated |

**27 directories removed** through `scripts/reclaim-worktrees.py` under committed scope packets.
Free space at reap completion: **13.63 GiB -> 29.92 GiB (+16.29 GiB)** on `/System/Volumes/Data`,
measured by this session on the same volume. Later readings are reported in `receipt.json` as
measurements only, without attribution this session cannot evidence.

## Every quarantine entry accounted for

164 entries, 847.7 MB, **zero unresolved**. The 5-file restore does not cover this set, and the
proof obligation differs by artifact class, so one test cannot serve all of them.

| Class | Entries | MB | Verdict |
| --- | --- | --- | --- |
| cache-build | 103 | 581.1 | reconstruction demonstrated from committed lockfiles + generators |
| source-copy | 1 | 226.1 | 3774/3777 blobs in the committed graph; 2 unique files under custody, 1 regenerable bytecode |
| peer-lane | 12 | 35.4 | repository-retirement-20260930 lane, not ours to purge |
| telemetry | 36 | 0.1 | derived state rewritten by the owning organ |
| tool-index | 6 | 4.1 | regenerable per-checkout tool state |
| capsule | 5 | 0.8 | remote custody verified |
| private | 1 | 0.1 | remote custody verified |

Cache and build entries are *not* expected in the committed object graph. They are proven
reconstructible by showing the pinning lockfile and the generating source are committed at HEAD,
verified with `git cat-file -e` against the real tree. Corroboration: zero tracked files exist
under any `out/` directory in `4444J99/limen`, `hospes-operations-private` or
`speech-score-engine`, so those build exports cannot have been source.

## Custody — the owning predicate, not a generic flag

The owning contract is `limen.portable_custody.validate_bundle`, and it **exits 0** against bytes
read from the committed owner (`git show HEAD:<path>` in private `4444J99/arca-g3`), never a local
path or URL. The graph carries measured logical and native capture, the RFC 8785 encryption profile
measured from `EncryptedObjectStore`, a ciphertext manifest, and per-replica authenticated readback,
retention and full-restore observations across two independent failure domains (`gdrive`, `github`).

**Recovery key: login Keychain service `limen-arca-vault`, read-only.** No Keychain item was created
or modified. It is Keychain-backed, so it survives loss of this host — that is what keeps both
replicas independently restorable. Restoring this payload requires that service.

| Replica | Failure domain | Retention until | Full restore |
| --- | --- | --- | --- |
| `gdrive:limen-custody/runtime-root-reap-20261004/` | `gdrive` | 2027-04-03 | 5/5 member digests |
| `4444J99/arca-g3` (`custody/reap-runtime-roots-20261004`, PR 1) | `github:arca-g3` | 2027-04-03 | 5/5 member digests |
| `~/.arca-vault/` + vault manifest | `physical:local-arca-vault` | n/a | convenience copy, same host |

Three contract violations were hit and corrected rather than worked around: replica identifiers must
be base64url-style and at least 16 characters; the captured artifact identity must be the replicated
bundle digest rather than the AES-GCM chunk-stream digest; and the encryption profile must be stored
as `rfc8785.dumps(profile)` because the store digests it that way.

An earlier revision claimed custody was met by two local copies. That was wrong — same filesystem is
one failure domain. The external SSDs were never required: the portable cloud transport satisfied
the two-failure-domain contract, so `limen.personal_custody` does not apply.

**Purging is not authorized.** The acceptance predicate accepts the custody graph; it does not
authorize retiring quarantine originals. Those stay until their own owners release them.

## What still blocks an all-absent state

`.worktrees/speech-score-engine` — gate `registered-worktree-owner`.
`/Users/4jp/Workspace/chamber_worktrees/chamber_2/speech-score-engine/pr-1` is registered against
this repository's common Git directory and carries an uncommitted modification, so the store is the
only object database behind that work. That path is outside the assigned TARGET_PATHs, so this
session does not reap it.

Owner action: commit or discard `pr-1`'s change and release it, then reap the store, then
`rmdir /Users/4jp/Workspace/limen/.worktrees`.

Two holds were cleared this round because the predicates, not PR state, decide:

- **`reap-scope-20261004`** was previously gated on "PR 2832 open". That was the wrong predicate, and
  an open PR is not a reap blocker. The real predicates all passed — no process cwd, no async task,
  clean tree, zero ignored payload after loss-free quarantine of 139 peer-lane receipts staged with a
  sha256 manifest, HEAD `5f0b4604` advertised by `refs/heads/work/reap-scope-20261004` and
  `refs/pull/2832/head`, directory mtime unchanged since 19:35. Reaped as `clean+pushed+idle`.
- **`.claude/worktrees`** was held by 12 processes that proved to be idle VS Code Python language
  servers (`ms-python.isort`, `ms-python.flake8`, `ms-python.pylint`), each with 0 children and 0.0%
  CPU, on an already-empty directory. Not sessions, not dependent stores. Released, then removed.

## Unique work rescued before removal

- `codex/psp-c06-public-surfaces-preflight` was advertised by **no** remote ref; pushed to
  `preserve/reap-20261004/psp-c06-public-surfaces-preflight` and re-proven.
- Five uncommitted VLTIMA closeout files and the otherwise-unreachable tag `vigilia/pii-preserve-life`
  in the Claude checkout were pushed and verified by independent fetch (tree and all five blobs
  byte-identical). `4444J99/limen` is public, so the tag's content was gitleaks-scanned clean first.
  The VLTIMA `parameters.yaml` delta is **preserved but deliberately not landed** — it removes two
  parameters that are live on main.
- Five distinct workstream capsules had unique `intent.md` / `manifest.md` / `workstream.json`
  records absent from the committed object graph; those are committed under [`capsules/`](capsules),
  since the capsule is the intent record the workstream owed.

## Other

- 847.7 MB sits in `/Users/4jp/Workspace/_limen-worktree-abandonment` as recoverable same-filesystem
  **moves**, each with a typed receipt. Nothing was deleted.
- Repaired a dangling entry this reap created: `limen.code-workspace` pointed at the removed
  `.agent-runtime/codex/worktrees`; repointed to `.agent-runtime/codex`. Two other entries were
  already dangling before this session and were left alone as out of scope.
- The human acceptance ledger `docs/worktree-reclaim-acceptance.jsonl` was never edited.
- No custody evidence was minted and no portable-custody record was hand-authored to satisfy a gate.
