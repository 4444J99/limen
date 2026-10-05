# Runtime-root reap — 2026-10-04

Operator-assigned reap of three disposable local runtime roots under the Limen checkout:

- `/Users/4jp/Workspace/limen/.agent-runtime/codex/worktrees`
- `/Users/4jp/Workspace/limen/.worktrees`
- `/Users/4jp/Workspace/limen/.claude/worktrees`

Authorization is the operator's direct-session instruction of 2026-10-04, bound verbatim in
[`reclaim-scope.json`](reclaim-scope.json) as a `limen.worktree_reclaim_scope.v1` packet.

Execution rail: `scripts/reclaim-worktrees.py --target … --scope-manifest …`, so every removal is
driven by a committed, remotely published, operator-scoped manifest rather than by ad hoc deletion.
Each removal additionally requires the tool's own gates — clean tree, live-remote reachability of
HEAD, all-local-ref remote proof for standalone clones, ignored-payload custody or regeneration
proof, no active process cwd, and no protected-exclusion match.

Per-directory receipts, live remote parity evidence, retention blockers and measured disk deltas are
in [`receipt.json`](receipt.json).

Children are processed before their shared store: `c06-portfolio` is a linked worktree whose Git
common directory lives inside `.agent-runtime/codex/worktrees/580e/portfolio/.git`, so it is reaped
before `580e`; likewise `8eef/portfolio` before `b4ca/portfolio-psp-c06`, and the nested
`lady-macbeth-macbeth-followup-20260809` before `speech-score-engine`.

## Outcome

**Status: INCOMPLETE — no completion claimed.** 26 directories are removed and the staged
private payload is remotely recoverable, but only 1 of the 3 target containers is absent.

| Target | Container | Contents |
| --- | --- | --- |
| `.agent-runtime/codex/worktrees` | **removed** | 7 entries reaped, incl. both shared stores after their children |
| `.claude/worktrees` | retained (empty) | 1 entry reaped; 0 remain |
| `.worktrees` | retained | 21 of 24 reaped; 2 remain under owner control |

Measured free-space change on `/System/Volumes/Data`: **13.63 GiB → 29.92 GiB (+16.29 GiB)**.

### What still blocks an all-absent state

| Path | Why | Owner / next action |
| --- | --- | --- |
| `.worktrees/reap-scope-20261004` | sibling recovery lane **not released** — PR 2832 open. Its HEAD *is* on the live remote, but quiesced is not finished. | its owning session closes PR 2832, then reap + `rmdir` |
| `.worktrees/speech-score-engine` | registered store for `chamber_worktrees/chamber_2/speech-score-engine/pr-1`, an external worktree outside this scope with its own live staged edit | that worktree's owner releases it |
| `.claude/worktrees` | empty, but 12 VS Code Python language servers hold it as cwd | reload or close the VS Code window, then `rmdir` |

## Custody — remote, verified, two failure domains

An earlier revision claimed custody was satisfied by two local copies. That was wrong:
same filesystem means one failure domain. It is now genuinely independent.

Payload is encrypted with `cli/src/limen/prima_materia_store.py` (AES-256-GCM, system
libcrypto EVP) under the operator's existing login-Keychain service `limen-arca-vault`,
read-only — no Keychain item was created or modified. Ciphertext bundle sha256
`c29576f52f9ee8de76e4066a8d8edca1414230ba19b174e8029bbfadb0a560f9`.

| Replica | Failure domain | Readback | Full restore |
| --- | --- | --- | --- |
| `gdrive:limen-custody/runtime-root-reap-20261004/` | `gdrive` | digest match | 5/5 member digests |
| `4444J99/arca-g3` (`custody/reap-runtime-roots-20261004`, PR 1) | `github:arca-g3` | digest match | 5/5 member digests |
| `~/.arca-vault/` + vault `manifest.json` | `physical:local-arca-vault` | convenience copy, same host |

Each remote copy was re-downloaded from the provider, its digest compared, decrypted
through `EncryptedObjectStore.restore`, and the recovered tar extracted so every member
file digest could be checked against the original. No custody evidence was minted.

The external SSDs were never required — the portable cloud transport satisfied the
two-failure-domain contract, so `limen.personal_custody` does not gate this payload.

Originals stay in local staging and same-filesystem quarantine until an independent
retention decision retires them.

## Unique work rescued before removal

- `codex/psp-c06-public-surfaces-preflight` was advertised by **no** remote ref; pushed to
  `preserve/reap-20261004/psp-c06-public-surfaces-preflight` and re-proven.
- Five uncommitted VLTIMA closeout files and the otherwise-unreachable tag `vigilia/pii-preserve-life`
  in the Claude checkout were pushed and verified by independent fetch (tree and all five blobs
  byte-identical). `4444J99/limen` is public, so the tag's content was gitleaks-scanned clean first.
  The VLTIMA `parameters.yaml` delta is **preserved but deliberately not landed** — it removes two
  parameters that are live on main.
- Five distinct workstream capsules had unique `intent.md` / `manifest.md` / `workstream.json`
  records absent from the committed object graph; those are committed under [`capsules/`](capsules).

## Retained, with named next actions

See the outcome table above. In short: `reap-scope-20261004` (unreleased sibling lane),
`speech-score-engine` (external registered-worktree store), and the two containers that
still hold them.
