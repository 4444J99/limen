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

164 entries, 847.7 MB, **zero unresolved**, and **zero purge-authorized** — retention is the default
until each entry's own retirement predicate passes. The 5-file restore does not cover this set, and
the proof obligation differs by artifact class, so one test cannot serve all of them.

| Class | Entries | MB | Verdict |
| --- | --- | --- | --- |
| cache-build | 94 | 471.5 | regeneration inputs committed; rebuild not executed |
| build-export | 9 | 109.6 | regeneration inputs committed; rebuild not executed |
| source-copy | 1 | 226.1 | measured: 3774/3777 blobs committed; 2 unique under custody, 1 regenerable bytecode |
| peer-lane | 12 | 35.4 | repository-retirement-20260930 lane, not ours to purge |
| telemetry | 36 | 0.1 | derived state rewritten by the owning organ |
| tool-index | 6 | 4.1 | regenerable per-checkout tool state |
| capsule | 5 | 0.8 | remote custody verified |
| private | 1 | 0.1 | remote custody verified, key durability unresolved |

**Withdrawn:** an earlier revision used "zero tracked files under any `out/`" as evidence that the
build exports are disposable. Absence from the index shows only that an export was never committed;
it is not evidence of disposability. Those 9 entries (109.6 MB) are now bound to committed
regeneration inputs plus the standing retention rule — neither purge-authorized nor claimed as
custody-verified.

For the generated classes the demonstrated fact is that the pinning lockfile and generating script are
committed at HEAD, verified with `git cat-file -e` against the real tree. The **not** demonstrated
fact is a rebuild: none was executed this session, so reproducibility is asserted, not shown.

## Custody — owning predicate passes; recovery key UNRESOLVED

`limen.portable_custody.validate_bundle` **exits 0** against bytes read from the committed private
owner (`git show HEAD:<path>` in `4444J99/arca-g3`), never a local path or URL. The graph carries
measured logical/native capture, the RFC 8785 encryption profile measured from
`EncryptedObjectStore`, a ciphertext manifest, and per-replica authenticated readback, retention and
full-restore observations across two independent failure domains.

| Replica | Failure domain | Retention until | Full restore |
| --- | --- | --- | --- |
| `gdrive:limen-custody/runtime-root-reap-20261004/` | `gdrive` | 2027-04-03 | 5/5 member digests |
| `4444J99/arca-g3` (`custody/reap-runtime-roots-20261004`, PR 1) | `github:arca-g3` | 2027-04-03 | 5/5 member digests |
| `~/.arca-vault/` + vault manifest | `physical:local-arca-vault` | n/a | convenience copy, same host |

### Recovery key: UNRESOLVED under Wall #320

An earlier revision asserted this key "survives loss of this host". **That claim is withdrawn.**
It also cited `refs/heads/work/reap-scope-20260704`, which does not exist on the remote; the live ref
is `refs/heads/work/reap-scope-20261004`, verified with `git ls-remote` before correcting.

Verified: the secret is readable at login Keychain service `limen-arca-vault`; access was read-only;
the same key performed every encryption and restoration in this session.

No independently recoverable custody was found:
- `security list-keychains` returns only the local `login.keychain-db` and the System keychain — no
  iCloud keychain is present.
- `defaults read com.apple.security` lists only the local `login.keychain` in its `DLDBSearchList`.
- `op item list --vault Limen-Automation` returns only a Jules API key; no `limen-arca-vault` item.
- No key file in `~/.arca-vault`, and no `RECOVERY-CARD` in that vault.

**Consequence:** the replicas are recoverable only while this Mac survives. The two provider failure
domains are real, but recoverability is host-bound.

**Wall #320 acceptance predicate — measured this session, still FAIL:**
1. `python3 scripts/credential-wall.py --check` exits 0 with `limen-arca-vault` registered as a Wall
   #320 atom whose probe resolves **off this host**, **and**
2. a re-run of the key probe above shows an independently readable copy.

Both halves are required. The measured run: `--check` exited **0** and reported all 31 secret atoms
registered — but `limen-arca-vault` is **not among them**. A green `--check` that does not index the
atom in question is not evidence for this gate, so half 1 fails on its registration clause despite the
zero exit, and half 2 fails on independent readability. Status stays **UNRESOLVED**.

Next action: the operator registers the secret in the credential organ (1Password vault
`Limen-Automation`), or enables iCloud Keychain for the login keychain. Both are credential/account
actions reserved to the operator, so this session performed neither.

This blocks off-host recoverability of the private payload only — not the existence of the provider
replicas, and not any reap gate.

What remains valid: encryption at rest, two independent provider replicas, authenticated readbacks,
and full restorations.

**Purging is not authorized.** The acceptance predicate accepts the custody graph; it does not
authorize retiring quarantine originals.

## What still blocks an all-absent state

Both remaining `.worktrees` entries are **live or dependent and are left intact**.

**`speech-score-engine` — gate `registered-worktree-owner`.**
`/Users/4jp/Workspace/chamber_worktrees/chamber_2/speech-score-engine/pr-1` is registered against this
repository's common Git directory and carries an uncommitted modification, so the store is the only
object database behind that work. That path is outside the assigned TARGET_PATHs.
Owner action: `pr-1`'s owner commits or discards its change and positively releases it → verify parity
→ reap the store → `rmdir .worktrees`.

`.claude/worktrees` was removed: it held zero entries before any holder was touched, and its 12
holders measured as idle VS Code Python language servers (0 children, 0.0% CPU) — editor helpers, not
protected sessions and not dependent stores.

**`reap-scope-20261004` — awaiting positive owner release.**
This session reaped it earlier on remote parity plus process inactivity. **That was a policy error**:
neither establishes release of a protected sibling session, and positive owner release was never
obtained. It is recorded as such, not as a success. Mitigating fact: no data was lost — the lane
re-created its checkout from the pushed branch and has since advanced twice more, to remote head
`6b9ff6d05` on `refs/heads/work/reap-scope-20261004` while the local checkout sits at `295666a2`. The
lane is still writing; loss-freeness held, but that is a mitigation, not authorization. The directory
is present and in use; it stays until its owner positively releases it.

## Owner-release probe — neither owner has released

Positive release is an explicit act. Process inactivity, remote parity and a stable HEAD are
observations, not release, and were not treated as such.

| Lane | Observation | Release obtained | Disposition |
| --- | --- | --- | --- |
| `reap-scope-20261004` | head stable at `6b9ff6d05` over 20s; PR 2832 OPEN, `mergedAt=null` | **no** | intact, untouched |
| `pr-1` → gates `speech-score-engine` | `M  CLAUDE.md`, 1 dirty path | **no** | retained |

Consequence: no reap and no container removal is authorized this round. Both entries and the
quarantine (166 entries, 0 purge-authorized) are preserved.

**Next-round procedure, on positive release:** verify live remote parity for the released head → run
the applicable custody predicates (portable custody acceptance for the private payload; per-entry
retirement predicates for quarantine) → reap eligible copies through the scoped reclaim rail → `rmdir`
the now-empty `.worktrees` container.

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
