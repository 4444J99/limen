# Parallel Cells — running many ideas (and many conductors) at once

How to work on several independent ideas simultaneously, each in its own isolated
worktree, optionally with its own scoped conductor — without stale-base forks and
without leaking disk. This is the interaction model behind `scripts/cells.sh`.

## The mental model: a CELL

A **cell** is one parallel idea made concrete:

- **one worktree** at `.claude/worktrees/<slug>` — a full, isolated checkout
- **one branch** `cell/<slug>`, always cut from `origin/main` (never your drifted local HEAD)
- **optionally one scoped conductor** — a heartbeat bound to that worktree, with its own
  `LIMEN_ROOT`, branch namespace (`cell-<slug>-`), identity receipt, lock and log; every
  task/lease transition still goes through the canonical conduct broker

Cells are isolated *by construction*, so N of them run side-by-side without racing each
other or the live daemon. Each cell tears itself down loss-free when you're done.

### Why cells exist (two bugs they kill)

1. **Stale-base forks.** Ad-hoc `git worktree add ../x -b x` branches from whatever your
   local HEAD happens to be — usually drifted behind `origin/main`. Merging such a fork
   *reverts* main. `cell new` always `git fetch`es and branches from `origin/main`
   (the #347 fix, made the default). See [[stale-base-fork-thicket]].
2. **The ~50GB leak.** The reclaim organ only swept the dispatch root
   (`~/Workspace/.limen-worktrees/`); `.claude/worktrees/` (where EnterWorktree / bg /
   interactive checkouts live) was reaped by *nothing*, so dead sessions leaked ~2.3GB
   each, forever. Cells live under the reclaim sweep now and `cell reap` is loss-free.
   See [[worktree-lifecycle-blind-spot]].

## The command set

```
cell new   <slug>            # create a cell (worktree off origin/main) → prints its path
cell ls                      # list cells: branch · ahead/behind · dirty · conductor · size
cell cd    <slug>            # print the cell path:  cd "$(cell cd foo)"
cell conduct <slug> [--loop] # start this cell's scoped conductor (bg). --loop = continuous
cell stop  <slug>            # request cooperative run stop, or gracefully stop a registration-only loop
cell merge <slug>            # push + hand off to the standing merge grant (merge-policy.sh)
cell reap  <slug>            # stop + hand off to receipt-backed reclaim/reap organs
cell reap-dead               # preview every provably-dead cell (clean+content-preserved+idle)
cell help
```

Install the shortcut once (optional — otherwise call `bash scripts/cells.sh …`):

```sh
alias cell='bash ~/Workspace/limen/scripts/cells.sh'
```

## The lifecycle, end to end

```
        cell new ──▶ (work / cell conduct) ──▶ cell merge ──▶ cell reap
          │                                                       ▲
          └──────────────── cell reap-dead (organ) ──────────────┘
```

### 1 — Spin up parallel ideas

```sh
cell new spiral-bvh         # idea A
cell new mail-digest        # idea B
cell new revenue-rail       # idea C
cd "$(cell cd spiral-bvh)"  # hop into one and start editing
```

Each is a clean checkout on `cell/<slug>` off `origin/main`. Work in as many as you like;
they never see each other's uncommitted changes.

### 2 — (Optional) give a cell its own conductor

A scoped conductor runs the autonomic cadence **inside that one cell** — it builds and
verifies on the cell's own branch namespace and does **not** perform fleet-wide GitHub
merges (those env toggles are off), so two conductors never fight over `main`.

```sh
cell conduct spiral-bvh           # one inspectable beat (drain→mine→route→dispatch), then stop
cell conduct mail-digest --loop   # continuous background conductor for this cell
cell ls                           # see which cells have a live conductor (PID) + their size
cell stop mail-digest             # stop it
```

Logs land in `logs/cells/<slug>.conduct.log`. `logs/cells/<slug>.pid` is a structured
`limen.cell_registration.v1` receipt, not a bare PID: it binds the PID to its process-start
identity, unique command marker, cell/session, run owner, and protection flag.

`cell stop` never sends `KILL`. For a conducted run it asks the broker for cooperative stop and
leaves the registration loop alive for liveness/harvest. For a registration-only loop it sends
`TERM` only after the PID, start identity, and command marker all match the receipt. Stale, reused,
foreign, or human-protected identities are refused rather than signalled.

**When to run multiple conductors:** when each idea has enough self-contained backlog to
keep a loop busy (e.g. a big refactor with its own task list). For a quick one-off edit,
skip the conductor — just work in the cell and `cell merge` it. The conductor is for
*parallel autonomy*, not for every cell.

### 3 — Land it

```sh
cell merge spiral-bvh       # commits must be in; pushes cell/spiral-bvh, hands to merge-policy
gh pr create               # if no PR yet
scripts/merge-policy.sh <PR#>   # the standing grant decides: 0=merge, 2=HOLD, 3=BLOCKED
```

`cell merge` never merges for you — it pushes and points you at `merge-policy.sh`, which
enforces the website guardrail (deploy-trigger paths need green CI; everything else merges
freely once CLEAN). See [[merge-authority-standing-grant]].

### 4 — Tear down (loss-free)

```sh
cell reap spiral-bvh        # refuses if the cell is DIRTY or has UNPUSHED commits
```

`reap` does not delete the worktree or branch directly. It stops the conductor, proves the cell is
clean and content-preserved, then delegates physical removal to the receipt-backed organs:
`docs/worktree-reclaim-acceptance.jsonl` + `reclaim-worktrees.py` for the root, and
`docs/branch-reap-acceptance.jsonl` + `reap-branches.py` for the branch ref. It will **not**
silently drop work — an empty/unpushed cell is treated as an unfulfilled intention, not garbage.
See [[empty-branch-is-a-todo-not-a-delete]].

### 5 — Sweep the dead automatically

You don't have to remember to reap. The **SPRAWL-RECLAIM organ**
(`scripts/reclaim-worktrees.py`, wired into the beat) now sweeps every known creation site:
the dispatch root, `.claude/worktrees/`, repo-local `.worktrees/`, and registered sibling
worktrees from the main repos. It reaps only cells that are **clean + content-preserved on the
remote default branch + idle past that root's age gate**, never the live checkout or a running session. Force a manual pass:

```sh
cell reap-dead              # dry-run (shows what would go, why each survivor is kept)
cell reap-dead --apply      # actually reclaim after operator acceptance
```

## Guarantees (why this is safe to use freely)

| Concern | How a cell handles it |
|---|---|
| Stale base reverting main | `new` always branches from freshly-fetched `origin/main` |
| Conductors racing `main` | scoped conductor: own branch namespace, fleet merges OFF |
| Conductors racing each other | isolated worktrees plus canonical broker leases; no cell-local board writer |
| Stale PID signalling a peer | exact PID/start/command proof; foreign and protected processes are refused |
| Losing uncommitted work | `reap` refuses dirty/unpushed; physical removal requires acceptance receipts |
| Disk leak | known worktree roots swept; loss-free gates; live-session guard |
| Hardcoded knobs | every `LIMEN_*` toggle declared in `institutio/governance/parameters.yaml` |

## Knobs (all declared in `parameters.yaml`)

| Env | Default | Meaning |
|---|---|---|
| `LIMEN_RECLAIM_CLAUDE_WT` | `1` | also sweep `.claude/worktrees/` (set `0` to disable) |
| `LIMEN_RECLAIM_CLAUDE_AGE_H` | `24` | min idle hours before a cell is reclaim-eligible |
| `LIMEN_RECLAIM_REPO_LOCAL_WT` | auto | also sweep repo-local `.worktrees/` roots under `LIMEN_RECLAIM_WORKSPACE_ROOTS` |
| `LIMEN_RECLAIM_REGISTERED_WT` | auto | also sweep registered sibling worktrees from `LIMEN_RECLAIM_MAIN_REPOS` |
| `LIMEN_RECLAIM_APPLY` | `1` | automated drain removes eligible roots by default; set `0` for preview-only |
| `LIMEN_BRANCH_PREFIX` | (derived) | scoped conductor's branch namespace (`cell-<slug>-`) |

## TL;DR

```sh
cell new myidea && cd "$(cell cd myidea)"   # isolated, off origin/main
# …edit, commit…
cell conduct myidea --loop                  # optional: its own background conductor
cell merge myidea                           # push → merge-policy decides
cell reap myidea                            # loss-free teardown (or let the organ do it)
```

One idea, one cell. Many ideas, many cells. Many cells, many conductors — each fenced in
its own worktree so nothing collides, nothing reverts main, and nothing leaks.
