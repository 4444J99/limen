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

| Target | Outcome |
| --- | --- |
| `.agent-runtime/codex/worktrees` | **reaped**, container removed |
| `.claude/worktrees` | contents reaped; empty container retained (12 VS Code language servers hold it as cwd) |
| `.worktrees` | 21 of 24 entries reaped; `reap-scope-20261004` (active sibling session) and `speech-score-engine` (external registered-worktree store) retained |

26 directories removed through `scripts/reclaim-worktrees.py` under committed scope packets.
Measured free-space change on `/System/Volumes/Data`: **13.63 GiB → 29.93 GiB (+16.3 GiB)**.

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

| Path | Why | Next action |
| --- | --- | --- |
| `.worktrees/reap-scope-20261004` | active sibling session (HEAD advanced twice during this reap) | reap after its owner releases it |
| `.worktrees/speech-score-engine` | registered store for `chamber_worktrees/chamber_2/speech-score-engine/pr-1` | reap after that external worktree is released |
| `.claude/worktrees` | 12 VS Code Python language servers hold it as cwd | reload/close the VS Code window, then `rmdir` |

## Custody

723 MB sits in `/Users/4jp/Workspace/_limen-worktree-abandonment` as recoverable same-filesystem
**moves**, each with a typed receipt — not deletions. Five unique files are additionally staged under
`.limen-private/custody-staging/reap-runtime-roots-20261004/` (mode 0700/0600) with a sha256
manifest, in two independent local copies, and a local full-restore proof that **passed**.

Off-host custody is still open: `limen.personal_custody` needs `/Volumes/Archive4T` and
`/Volumes/T7Recovery`, and neither is mounted. Per the portable custody contract
(`cli/src/limen/portable_custody.py`) that gate needs provider-observed authenticated readback and
independent restoration records, which this session must not mint — so the originals are retained
until it clears rather than deleted to manufacture a green result.
