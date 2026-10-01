# S2 — Control and remaining authored-source parity · handoff

Stream: S2 (read-only inspection) · Outcome: git parity 1:1 + purge/prune local · Owner rail: limen
Observed at: 2026-09-30T20:30:26Z (agent identity `opencode`, native user `4jp`, host `Anthonys-MacBook-Pro.local`, macOS 26.7.1 arm64, git 2.56.0, git-lfs 3.8.0)

## Broker / lifecycle

`limen conduct capabilities` returned `conduct broker is not configured; set LIMEN_CONDUCT_URL and
LIMEN_CONDUCT_TOKEN`. Per packet §7 this is the sanctioned degraded path: **inspection continued with
zero lifecycle claims**. No lease, no run id, no `tasks.yaml` touch, no fabricated identity. `get_budget_status`
reports 100 daily runs, 0 spent on this track — undebited, consistent with claiming nothing.

## Scope identity and revalidated denominator

Denominator is revalidated **independently** and reproduces the 2026-09-30 checkpoint exactly:

| Measure | Checkpoint | S2 revalidation | Agreement |
|---|---|---|---|
| valid checkout paths | 208 | **208** | exact |
| common Git stores | 135 | **135** | exact |
| unresolved `.git` markers | 17 | **17** | exact |
| registered worktrees | 212 | **212** | exact |
| registered worktrees outside Workspace | 3 | **3** | exact |
| dirty paths | 44 | **44** | exact |
| stashes | 5 | **5** | exact |
| no-remote repositories | 7 | **7** | exact |
| runtime bare stores | 3,276 | **3,284** | **+8, see finding F-1** |

Dirty 44 = union(24 tracked-dirty, 29 with untracked), 2,970 untracked files total.
Stashes = 4 stash tips across 4 stores, 5 reflog entries (`the-thing-without-a-name` holds a 2-entry stack):
`domus-genoma` bf62309 (2026-07-06), `limen` 032a465 (2026-09-20), `public-record-data-scrapper` a2e8022 (2026-09-12), `the-thing-without-a-name` f6f570a (2026-08-27, ×2).

**Two method defects were found and corrected in my own instrumentation before use** (recorded so S5 does not
inherit them): (a) `os.walk` pruning `.git` from `dirnames` *before* testing for it hid every directory-style
marker, yielding 92/26 instead of 208/135; (b) `--no-optional-locks` is not a valid `git status` option, which
silently produced false `dirty=0 / untracked=0`. Both are corrected in the deposited scripts.

**Assigned-cohort reconciliation is PARTIAL and is not resolvable by inspection alone.** S0's grouping
(5 control stores/29 paths + 59 authored/80 paths = 64/109) could only be partially re-derived:

- **Control cohort resolves exactly: 5 stores / 29 paths** — `limen/.git` (21), `domus-genoma/.git` (4),
  `4444J99/portvs/.git` (1), `organvm/limen/.git` (2), `organvm-corpvs-testamentvm/.git` (1).
  This is an *inference* from the 5/29 shape, not a registry read. S0 must confirm the identity list.
- Authored remainder: my structural classifier yields **73 candidate stores / 141 paths** against the assigned
  59/80 — **9 stores / 32 paths unallocated**. The surplus is concentrated in stores whose ownership is
  ambiguous from structure alone: `limen/.worktrees/*` (11), `.limen-worktrees/m1_repos/*` (7),
  `limen/issue_backlog_work/*` (2), `chamber_worktrees/*` (2), `.social-automation-worktrees` (1),
  `domus-genoma/_agents/cache/uv/git-v*` (5), `_collaboration-operations-private/state/hydrated/*` (6).
  **I did not guess the split.** Only S0's explicit partition can close it; guessing would fabricate
  ownership boundaries across S1/S3 protected territory.

## Remote custody evidence

Every store probed with `git ls-remote` only — **no fetch, no ref write, no remote-tracking mutation**.
Accessibility: **122 OK / 6 local-path-remote / 7 no-remote / 0 unmeasured.** No access failure anywhere,
so nothing in the matrix rests on an inference.

Custody state across all 135 stores (local object IDs vs freshly advertised refs):

| State | Stores | Meaning |
|---|---|---|
| `EXACTLY_SYNCHRONIZED` | 15 | every local head byte-identical to an advertised head, no extras |
| `EXACTLY_SYNCHRONIZED_WITH_LOCAL_EXTRAS` | 32 | heads exact; local-only tags and/or detached HEAD remain |
| `RECOVERABLE_UNSYNCHRONIZED` | 35 | unsynced heads whose commits are ancestors of advertised refs — pushable, not lost |
| `UNIQUE_LOCAL_HISTORY` | 40 | unsynced heads **not** contained in any advertised history — sole copy on this host |
| `NO_AUTHORIZED_REMOTE` | 13 | no remote (7) or local-path remote only (6); a local-path remote is explicitly not custody proof |

Only **47 of 135** stores are clean-exact in the strict sense. **80 stores hold state with no landing proof.**
Divergence, not absence of work, is the dominant condition.

Control-store observed revisions:

| Store | Common dir | State | Branches | Unsynced | Unique local |
|---|---|---|---|---|---|
| limen | `limen/.git` | `UNIQUE_LOCAL_HISTORY` | 28 | 6 | 2 |
| domus-genoma | `domus-genoma/.git` | `UNIQUE_LOCAL_HISTORY` | 22 | 6 | 3 |
| organvm-corpvs-testamentvm | `organvm-corpvs-testamentvm/.git` | `UNIQUE_LOCAL_HISTORY` | 2 | 2 | 1 |
| organvm/limen | `organvm/limen/.git` | `RECOVERABLE_UNSYNCHRONIZED` | 4 | 4 | 0 |
| 4444J99/portvs | `4444J99/portvs/.git` | `UNIQUE_LOCAL_HISTORY` | 6 | 3 | 2 |

Linked dependencies: **0 alternates** estate-wide (so no cross-store object sharing — every unique-local commit
in one store is genuinely sole-copy), **1 submodule gitdir** (`charles-universe/.git/modules/...`),
**22 LFS object files / 549 MiB**, **8 detached-HEAD stores**, **2 prunable worktree registrations**.

## Protection and consumer findings (for Domus #397)

Control-source copies are **not** retirement candidates. Exact dependencies, measured not inferred:

1. **Scheduled jobs — 3 LaunchAgents hard-code `/Users/4jp/Workspace/limen`**:
   `com.ianva.gateway.plist`, `com.limen.claude-stub-heal.plist`, `com.limen.creds-hydrate.plist`.
   Out of 17 total plists. These are loaded runtime consumers; removing or relocating the limen checkout
   breaks them. No plist references domus-genoma, portvs, organvm/limen, or testamentvm.
2. **chezmoi source is domus-genoma.** `chezmoi source-path` → `/Users/4jp/Workspace/domus-genoma`;
   `chezmoi managed` enumerates **3,186** deployed targets. This is the single largest control consumer.
3. **Live sessions** referencing control stores: limen 14, domus-genoma 2, portvs 1, organvm/limen 1,
   testamentvm 1 — 19 processes total. Active-session protection applies to all five.
4. **portvs mirror is degraded (F-2):** 5 of 8 symlinks under `4444J99/portvs/skills/_arms/mirror/` are
   **dangling** — `claude`, `gemini`, `openclaw-agents`, `openclaw-extensions`, `source`. `source` points at
   `/Users/4jp/Code/organvm/a-i--skills`, which **does not exist**. Only `codex`, `opencode-commands`, and
   `agents` resolve. A mirror index that reads as complete while 5 of 8 targets are absent is a live
   control-consumer defect for #397, and it means portvs cannot be certified as a satisfied consumer root.
5. **No agent-root symlink points into Workspace** (0 found under `~/.claude`, `~/.codex`, `~/.agents`,
   `~/.config`, `~/.gemini`). Control retention therefore rests on items 1–3, not on agent-root back-references.

## Findings outside my mutation authority

- **F-1 — bare-store count 3,284, not 3,276 (+8).** 3,350 bare object stores exist Workspace-wide and the
  mass is leaked runtime temp: `limen/.agent-runtime/codex/.tmp/git-XXXXXXXX` (3,284 of them). These are
  abandoned Codex temp clones, not authored source. Not mine to remove — S3 owns runtime, and per packet §9
  I must not relocate or delete clones merely to claim cleanup. Reclaim is S3's decision, gated on proving no
  live agent holds them. This is likely the single largest disk reclaim on the host and should not be missed.
- **F-2 — portvs mirror dangling symlinks** (item 4 above). Domus #397.
- **F-3 — scratch is not durable.** A concurrent sweep deleted my working directory mid-census. Anything left
  only in `$TMPDIR/opencode` is lost. This is why the evidence below is deposited in a git-tracked home.
- **F-4 — disk free fell 24.5 → 22 GiB during inspection** (95% full). Admission pressure is real and rising;
  the F-1 reclaim is time-sensitive rather than cosmetic.
- **F-5 — two inventory gaps I could not close**, stated rather than papered over: `domus-genoma/_agents/cache/uv`
  contributed 5 of the 17 unresolved markers and 5 of the 13 no-remote stores (uv/git cache objects, not
  repositories); and `the-thing-without-a-name`, `styx-public-repo` (29 unsynced, 29 unique — the worst single
  store on the host), `hospes` (29 unsynced, 29 unique) and `public-record-data-scrapper` (9 unsynced) are
  authored but landed in no S0 group I could confirm. **These four are the highest-risk stores in the estate
  and S0 must place them explicitly before any purge pass.**

## Proposed exact operations — for S0 admission, none executed

No operation below was run. All are read-only-derived and require S0 execution plus custody first.

- **OP-1 (highest value, zero risk):** for the 35 `RECOVERABLE_UNSYNCHRONIZED` stores, fast-forward-only
  push of local tips to existing authorized owners. Every tip is already an ancestor of an advertised ref, so
  this is a pure fast-forward — **no force-push, no rebase, no reset**. Converts 35 stores to clean-exact.
- **OP-2 (preservation, mandatory before anything else):** for the 40 `UNIQUE_LOCAL_HISTORY` stores, create
  bundle/tag preservation of exact local tips under **existing** authorized owners. No new public repos, no
  pushing upstream-owned refs. Sensitive history routes to S3's existing encrypted owner. Because alternates
  are zero estate-wide, these tips have no second copy on this host — this is the highest-severity class.
- **OP-3 (detached heads / local-only tags):** the 32 `EXACTLY_SYNCHRONIZED_WITH_LOCAL_EXTRAS` stores hold
  recoverable value that no branch name references. Preserve detached tips and local-only tags under OP-2
  custody before any prune. A detached HEAD plus a local tag is invisible to `git push --all`.
- **OP-4 (stashes):** the 5 stash entries are reachable only via `refs/stash` reflog and are destroyed by
  reflog expiry. Preserve before any gc/reflog work.
- **OP-5 (reclaim, S3-gated, not mine):** the 3,284 Codex temp bare stores (F-1). Requires S3 confirmation that
  no live agent holds them. I propose it; I do not authorize it.
- **OP-6 (never):** no `git gc --prune=now`, no `reflog expire`, no `worktree prune`, no remote-branch
  deletion, no blanket `-x` clean, no clone relocation — explicitly out of bounds for this outcome.

**Retirement candidacy:** a clean-pushed inactive copy becomes a *candidate* only. **My evidence is not removal
authority.** Whole-copy retirement additionally needs S3 custody receipt plus S4 protection/consumer/landing
qualification. Branch age, closed-unmerged PRs, absent open PRs, and cached tracking refs are not landing proof —
and note that 32 of my stores are already exact against *freshly advertised* refs, which is the only landing
evidence class I could produce.

## Predicate and exit code

Independently re-executable by S5 from the deposited scripts (no network needed for the first two):

```
cd <dir>; python3 census.py     # → checkouts_resolved=208, common_dirs=135, checkouts_unresolved=17
cd <dir>; python3 inventory.py  # → stores=135, checkouts=208, registered_worktrees=212,
                                #   no_remote=7, worktrees_outside_workspace=3, dirty union=44, stashes=5
cd <dir>; python3 probe.py      # → {"OK":122,"LOCAL_PATH_REMOTE":6,"NO_REMOTE":7}   [network]
cd <dir>; python3 parity.py     # → 15/32/35/40/13 state distribution
```

S2 self-verification: census + inventory + parity re-run green; all four exit codes **0** (read each
predicate's own exit code bare, per session-discipline #6 — no pipelines). Live remote probe returned
zero unmeasured stores. Denominator reproduced exactly against the checkpoint on all nine shared measures.

## Evidence destination

- `limen/docs/continuations/git-parity-20260930/S2-evidence/parity-matrix.json` — redacted per-store custody
  matrix, 135 rows, schema `S2-EVIDENCE-V1`. Subjects and remote URLs omitted.
- `limen/docs/continuations/git-parity-20260930/S2-evidence/scripts/{census,inventory,probe,parity}.py` —
  the four read-only collectors, so S5 reproduces rather than trusts.
- **Not yet committed or pushed.** S0 owns consolidation and publication through the limen rail. Raw
  unredacted detail stayed in volatile scratch deliberately; sensitive raw evidence remains with its
  existing private owner.
- Secret/privacy scan before publication: **0 credential-bearing remote URLs** across all 135 stores
  (patterns `ghp_/gho_/ghu_/ghs_/ghr_/github_pat_/sk-/xox*/AKIA/PEM/://user:pass@`).

## Disposition and next owner/action

**Disposition: inspection complete; zero operations executed; zero lifecycle claims taken.**

| Next owner | Action |
|---|---|
| **S0** | Confirm the 64/109 partition list (9 stores/32 paths unallocated, §Scope). Admit OP-2 before OP-1 — unique-local-history custody strictly precedes any push or prune. Execute OP-1 FF-only, then OP-3/OP-4. Take F-1/F-5 to S3. |
| **S3** | F-1: rule on 3,284 Codex temp bare stores (largest reclaim, S3-gated). F-5: place the four high-risk authored stores. Encrypted custody receiver for sensitive history under OP-2. |
| **S4** | Protection/consumer/landing qualification for any retirement candidate — none of mine is qualified. Note 3 LaunchAgents + 3,186 chezmoi targets + 19 live processes pin the control cohort. |
| **Domus #397** | F-2 portvs mirror: 5 of 8 targets dangling, `source` → nonexistent `/Users/4jp/Code/organvm/a-i--skills`. No duplicate issue; add to the existing control-consumers issue. Plus the closeout loader discovery defect S0 already holds. |
| **S5** | Re-run the four predicates above rather than trusting my numbers. Two instrumentation defects are documented so they are not inherited. |

I hold no removal authority and asserted none. 80 of 135 stores lack landing proof; 40 hold sole-copy
history on this host. Nothing here is a retirement, and nothing here should be read as one.

---

## Post-handoff correction — the denominator is NOT stable (material to any purge pass)

My own verification re-run, ~10 minutes after the observation above, from the deposited scripts:

| Measure | t0 observation | t1 verification | Delta |
|---|---|---|---|
| resolved checkouts | 208 | **209** | **+1** |
| registered worktrees | 212 | **213** | **+1** |
| linked worktrees | 73 | **74** | **+1** |
| bare stores | 3,284 | **3,305** | **+21** |
| common Git stores | 135 | 135 | 0 |
| unresolved markers | 17 | 17 | 0 |
| dirty checkouts (tracked) | 24 | 24 | 0 |
| untracked files | 2,970 | 2,976 | +6 |

Verification predicates: `census.py` exit **0**, `inventory.py` exit **0**, both re-run bare with their own
exit codes read directly. The 209th checkout and 74th linked worktree appeared **during** this session —
concurrent lanes and human sessions are still creating git state.

**Operational consequence for S0:** the census is a moving target. A parity matrix is only valid for the
instant it was observed. Any admitted purge pass must **pin the exact revision snapshot it was authorized
against and re-verify immediately before executing each operation** — otherwise it acts on stale state and
can delete a checkout that was created after the matrix was built. The 135 common stores and 17 unresolved
markers were the only two stable measures across both observations, and they are the ones to trust as the
partition backbone.
