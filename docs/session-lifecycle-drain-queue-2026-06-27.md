# Session Lifecycle Drain Queue - 2026-06-27

Generated: `2026-06-27T18:31:00Z`

This queue is the first executable output of the session-lifecycle intake. It is deliberately not a
`tasks.yaml` mutation: this is a direct human session, and the board should only be changed when a
specific item is claimed or dispatched.

## Guardrails

- Do not delete or remove unique work.
- Do not close prompt-started work as cancelled, forgotten, or not planned.
- Raw app/session/screenshot material stays in `.limen-private/session-corpus/`.
- Auth, secrets, login, key, token, and password issues are parked unless directly required.
- Claude is near limit; use it sparingly as a context source, not the default worker.

## Queue Order

| Rank | Item | Evidence | Next Action | Best Lane | Stop Condition |
|---:|---|---|---|---|---|
| 0 | Finish this intake patch | Updated session and prompt ledgers, screenshot batch, generator bug fix | Verify, commit, push scoped Limen docs/scripts only | Codex | `verify-whole.sh` passes; `tasks.yaml` remains unstaged |
| 1 | Preserve session-meta owner state | `session-meta` is ahead 1, behind 1, with 39 dirty entries | Inspect owner repo, preserve branch/PR or blocker, then refresh atoms | Codex or OpenCode | Owner repo is clean or has a durable PR/blocker receipt |
| 2 | Preserve knowledge-corpus owner state | `knowledge-corpus` has 3 dirty entries | Inspect owner repo and preserve the corpus changes before relying on it | Codex or OpenCode | Owner repo is clean or has a durable PR/blocker receipt |
| 3 | Create Codex quicken-style classifier | Codex sessions are indexed, but no resume/classification organ exists | Build a classifier equivalent to Claude quicken for Codex sessions | OpenCode or Agy | Re-run produces classified Codex sessions and no raw commit |
| 4 | Drain dirty/missing-remote worktrees | 6 dirty roots, 6 missing/unknown remote branches | Push branch or create draft PR per root; never clean before preserving | OpenCode or Agy | Each root has PR, owner blocker, or documented non-source residue |
| 5 | Resolve non-Git residue roots | 2 `.limen-worktrees` roots are not Git dirs | Inspect for unique artifacts; record owner receipt; do not delete blindly | Codex | Each residue has a reversible archive or owner receipt |
| 6 | Merge or supersede open PR receipts | 10 branch-linked PRs are open, 2 branch receipts already merged | Verify checks, merge when green/authorized, or record blocker | Jules/OpenCode after packetization | PR merged, preserved, or superseded by name |
| 7 | Harvest async Jules reservations | 41 dispatched Jules tasks have no PR yet | Treat as async reservations until harvest proves otherwise | Jules harvester | Completed sessions landed as PRs or reopened with evidence |
| 8 | Park remote/cloud credential gaps | Cloud env flags absent; Gemini/auth wall remains credential-gated | Keep in credential issue/workstream, not inline in intake | Human/Codex prep | Credential blocker has owner issue and no leaked secret |

## Run Notes

- 2026-06-27: `session-meta` owner state was preserved on branch
  `codex/preserve-session-meta-owner-state-20260627`, now rebased through commit `db2285a`, with
  draft PR [organvm/session-meta#130](https://github.com/organvm/session-meta/pull/130). GitHub
  marks the PR `MERGEABLE`, and the CI matrix for Python 3.10, 3.11, and 3.12 is green. The
  pre-rebase chain, including live manifest receipt `d9d9611`, is preserved on remote branch
  `backup/session-meta-pr130-before-rebase-20260627T194123Z`.
- 2026-06-27: `knowledge-corpus` owner state was preserved on branch
  `codex/preserve-knowledge-corpus-owner-state-20260627`, commit `e66199e`, with draft PR
  [organvm/knowledge-corpus#1](https://github.com/organvm/knowledge-corpus/pull/1). The local
  owner checkout is clean on the pushed branch. GitHub marks the PR `MERGEABLE`. Validation:
  `git diff --cached --check`, redaction scan `redactions: 0 {}`. Review caveat:
  `reduced/model-whole-stack-of-reality.md` currently contains a JSON-ish convergence wrapper
  with a `[Full document as in source material ...]` placeholder; the PR preserves it for
  lifecycle continuity, but it should be reviewed before merge as a likely convergence-output
  regression.

## Dirty And Missing-Remote Worktrees

| Root | Repo | Head | Remote Branch | PR Receipt | Reason | Next Action |
|---|---|---|---|---|---|---|
| `bld-my--father-mother-harden-44b2` | `organvm/my--father-mother` | `18730a2bead7` | missing | none | dirty | Inspect diff, run owner tests, push branch, open draft PR |
| `bld-promptscope-next-rev-3fde` | `organvm/promptscope` | `4fa725bd47a8` | missing | none | dirty | Inspect diff, run owner tests, push branch, open draft PR |
| `cifix-organvm-i-theoria-hierarchia-mundi-3145` | `organvm/hierarchia-mundi` | `677df2b8088a` | missing | none | dirty | Preserve CI-fix work as branch/PR or blocker |
| `gen-organvm-i-theoria-sovereign--ground-ci-green-0620-0f38` | `organvm/sovereign--ground` | `80e7617d1122` | missing | lookup incomplete | dirty | Re-run remote lookup, preserve branch/PR before cleanup |
| `gen-organvm-universal-mail--automation-test-coverage-0625-151e` | `organvm/universal-mail--automation` | `bff9ae1177cb` | missing | none | dirty | High-risk broad diff; preserve before any deletion |
| `resolve-organvm-i-theoria-.github-459-1ade` | unknown | `efff71cb1ad1` | unknown | none | dirty | Repair/identify origin, then preserve branch/PR or blocker |

## Non-Git Residue Roots

| Root | Reason | Next Action |
|---|---|---|
| `gen-organvm-the-invisible-ledger-ci-green-0625-e3c2` | not a Git dir | Verify whether only generated/cache files remain; record owner receipt before removal |
| `rev-organvm-the-invisible-ledger-revenue-readiness-0623-bd8b` | not a Git dir | Verify whether only `.vite` or cache residue remains; record owner receipt before removal |

## Open Branch-Linked PRs

| Root | PR | State | Next Action |
|---|---|---|---|
| `bld-domus-genoma-ci-23a9` | `organvm/domus-genoma#144` | open draft | Re-verify BATS blockers and merge readiness |
| `bld-media-ark-tests-2698` | `organvm/media-ark#50` | open draft | Re-verify release/test predicates |
| `bld-mirror-mirror-harden-350f` | `organvm/mirror-mirror#67` | open draft | Keep preserved; merge only when owner policy allows |
| `bld-universal-mail--automation-readme-9031` | `organvm/universal-mail--automation#108` | open draft | Re-verify docs/readme scope |
| `bld2-a-i-chat--exporter-integration-tests-a00b` | `organvm/a-i-chat--exporter#96` | open draft | Re-verify integration tests |
| `cifix-organvm-i-theoria-conversation-corpus-engine-f02e` | `organvm/conversation-corpus-engine#60` | open draft | Preserve CI pin and merge when ready |
| `discover-organvm-kerygma-profiles-6c74` | `organvm/kerygma-profiles#8` | open draft | Compare against merged #5, then merge/supersede |
| `exporter-mp` | `organvm/a-i-chat--exporter#95` | open draft | Compare against merged #27, then merge/supersede |
| `gh-organvm-object-lessons-19-605a` | `organvm/object-lessons#22` | open draft | Debt root: merge or name blocker |
| `rev-organvm-public-record-data-scrapper-revenue-readiness-0623-023f` | `organvm/public-record-data-scrapper#328` | open draft | Debt root: merge or name blocker |

## Loop Families To Classify

| Family | Source Evidence | Classification | Required System Improvement |
|---|---|---|---|
| `technical debt` | Claude UI screenshots plus local app stores | Repeated ritual and stalled loop | Convert into owner-scoped debt packets with receipts |
| `open GitHub issues review` | Claude UI screenshots | Repeated review loop | Require issue-to-PR/blocker mapping before more review |
| `convergence organ` | Codex screenshots and local Claude/Codex stores | Core convergence work, not noise | Build classifier/distiller so repeats collapse into one canon |
| `session handoff / closeout` | Claude UI screenshots and Limen logs | Lifecycle control-plane work | Keep closeout receipts in owner ledgers, not chat memory |
| `auth / provider setup` | Cloud env flags absent and credential wall | Parked blocker | Keep in credential workstream; do not solve inline |

## Agent Assignment Rule

Jules, OpenCode, Agy, and Gemini should not receive broad "clean the sprawl" prompts. They should
receive bounded packets only after this queue has an owner repo, branch, predicate, and no raw-secret
dependency. Gemini remains credential-gated unless auth is already repaired. Claude should be used
only when a Claude-only local context is required.
