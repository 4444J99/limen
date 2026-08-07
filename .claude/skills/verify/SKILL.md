---
name: verify
description: How to actually RUN this repo's surfaces to verify a change — the handle, the drive paths, and the gotchas that cost a session each. Read before driving a limen change at runtime.
---

# Verifying a change in limen at runtime

Recipes that worked, so the next session skips the cold start. This is not a substitute for
`scripts/verify-scoped.sh` (the push gate) — it is how to reach the *running* surface a change
touches.

## The handle: which python runs your code?

The installed CLI is an **immutable, SHA-pinned runtime** — it does not see your worktree:

```bash
/Users/4jp/.local/bin/limen            # wrapper: execs $HOME/.local/share/limen/current/venv/bin/limen
readlink ~/.local/share/limen/current  # -> runtimes/<merged-sha>
```

So `limen <verb>` runs **merged code**, never your branch. A change reaches the deployed CLI only
after merge + `domus-limen-runtime install --sha <merged-sha>`.

To drive **your** code through the real entrypoint, shadow the installed package with `PYTHONPATH`
(it precedes site-packages) while keeping the runtime's venv for dependencies:

```bash
PYTHONPATH=<worktree>/cli/src ~/.local/share/limen/current/venv/bin/limen status
# confirm the shadow took:
PYTHONPATH=<worktree>/cli/src ~/.local/share/limen/current/venv/bin/python -c \
  "import limen.tabularius as t; print(t.__file__)"
```

`python3 -m limen.cli` does **not** work from the repo root — `limen` is not on the default path.
For pytest, the system python plus `PYTHONPATH=<worktree>/cli/src` works; the pinned runtime's venv
has **no pytest**.

Some paths refuse to run outside the stable TCC principal (`StableAgentHostError` →
`BLOCKED … refusing an unstable TCC principal`). Wrap the command:

```bash
PYTHONPATH=<worktree>/cli/src ~/Applications/DomusAgentHost.app/Contents/MacOS/DomusAgentHost \
  run -- ~/.local/share/limen/current/venv/bin/limen dispatch --agent jules --limit 1 --live
```

## Drive paths by surface

| Change touches | Drive it with |
|---|---|
| `dispatch.py` selection/launch | `limen dispatch --agent <a> --limit 1` (dry-run prints `would: <argv>`), then `--live` for the real launch |
| the conduct relay (`tabularius.py`) | any live `--live` dispatch — the receipt commit runs `apply_limen_file_sync` at the end |
| `conduct/liveness.py` occupancy | `python3 scripts/session-contention.py probe --root <root>` — exit 0 `free` / exit 1 `OCCUPIED by pid N` / exit 0 `probe UNAVAILABLE` |
| `status.py` | `limen status \| head -6` |
| the Cloudflare Worker (`web/worker/`) | `npm --prefix web/worker ci` **once per worktree**, then `npm --prefix web/worker run check` (`node --check` + `node --test`) |
| the durable board | `git show origin/tabularius/board-projection:tasks.yaml` — the keeper's published projection, which is **not** `main`'s copy |

## Comparing shipped vs pre-fix code (the A/B that proves a fix)

The strongest available evidence for a behavioural fix: run the **same production entrypoint**
against the **same live state** with only the module swapped. `scripts/session-contention.py` reads
`LIMEN_ROOT` for its `sys.path`, so pointing it at a scratch tree holding the parent commit's
package makes it import old code while `--root` still names the real target:

```bash
# scratch tree with the PRE-fix module, then:
LIMEN_ROOT=/tmp/verify-NNNN python3 scripts/session-contention.py probe --root /Users/4jp/Workspace/limen
```

Extract a parent-commit blob with `subprocess.run(['git','show','<rev>^:<path>'])` and write the
bytes — **`git show <rev>:<path> --output=<file>` silently writes nothing** (`--output` is a diff
option and does not apply to blob shows).

## Gotchas that each cost a session

- **A copied macOS system binary is SIGKILLed on exec (arm64).** Faking a process shape with
  `cp /bin/cat ./claude` produces a pid that is already gone, and the probe then reports `free` —
  indistinguishable from a passing verification. Fix: `codesign --force -s - ./claude`.
- **Read the predicate's OWN exit code.** `predicate | tail` makes `$?` report tail's status. Run it
  bare and redirect, then `tail` the file: `scripts/merge-policy.sh 2001 > .mp.txt 2>&1; echo $?`.
- **`git checkout -b <new> origin/main` with a stale working tree silently clobbers newer content.**
  If your tree is N commits behind, the modified files are carried over the newer base whole. Always
  finish with `git diff origin/main -- <files> | grep '^-'` and confirm the only removed lines are
  ones you meant to replace. (This happened, and reverted another lane's feature.)
- **…but read that check with THREE dots once you have committed, or it lies the other way.**
  Two-dot `git diff origin/main` compares *trees*, so a branch that is merely **behind** renders every
  commit `main` gained as lines you deleted. Both failures print the same thing:

  ```bash
  git diff origin/main -- <files> | grep '^-'   # uncommitted work: correct, catches the clobber
  git diff origin/main...HEAD | grep -E '^-[^-]' # committed work: resolves the merge base
  git merge-base --is-ancestor origin/main HEAD  # nonzero ⟺ behind, so rebase before judging
  ```

  A long-running background `await-pr.sh` fetches, so `origin/main` advances *under you* mid-session
  and a branch that was current when you cut it is behind by the time you diff it. Observed: a clean
  branch appeared to delete an entire merged feature (`repair_canonical`, its params, its tests, its
  rung). Check `--is-ancestor` first; if behind, rebase and re-diff rather than interpreting.
- **Two rungs appended to the same region of `heartbeat-loop.sh` WILL conflict on rebase.** "Both
  additions are wanted" is semantics; git only sees two edits at one line. Resolve by keeping both and
  think about **order** — a repair rung belongs before the rung whose gate it unblocks, or the pair
  converges a beat later than it needs to. Chunking one concern per branch is still right; the
  mechanical conflict is its price.
- **The live checkout is permanently dirty by design** (`capture.sh` snapshots it to a side ref), so
  `git status` there is never clean and is not a signal.
- **Dry-run scripts can still write.** `scripts/reclassify-needs-human.py` with no flags writes
  `docs/RECLASSIFY-PROPOSAL.md`. Check for generated artifacts after a "read-only" run.
- **Worktree-isolation guard rejects compound commands.** No `cmd && cmd`, no `>` redirect combined
  with `cd`, no heredoc-into-`cat` chains. Issue plain single commands with absolute paths, or use
  the Write tool for scratch files (inside the worktree).
- **A fresh worktree has no `web/worker/node_modules`,** and `npm run check` then reports 4 of 5 test
  *files* failing with no useful summary — it looks like your change broke the Worker. Run one file
  directly to see the real cause (`ERR_MODULE_NOT_FOUND: ajv`). Fix: `npm --prefix web/worker ci`.
- **`test_campaign_relay_effector::test_full_relay_exec_proof_closes_while_keepalive_remains_live`
  is load-sensitive, not randomly flaky.** It asserts a spawned provider wrote its pidfile; under
  host contention the parent races ahead. The tell is duration — passing runs take ~16s, failing
  runs ~4s, and every failure lands while something heavy is running. Observed failing 4× then
  passing 3× on the *same commit*. Do not conclude "pre-existing on main" from an isolation
  argument: re-run it on a quiet host before believing either verdict.
- **`git checkout -- <file>` reverts the WHOLE file, including uncommitted work you meant to keep.**
  Commit before mutating an implementation to prove a test can fail, or you will revert the fix
  along with the mutation.

## Local vs canonical state — do not confuse them

`tasks.yaml` in the checkout is a **read-only projection** of the keeper, refreshed only when a
board-publication PR merges to `main`. Three different things can disagree:

```bash
md5 tasks.yaml                                              # live checkout
git show origin/main:tasks.yaml | md5                        # what main says
git show origin/tabularius/board-projection:tasks.yaml | md5 # what the KEEPER says
```

A conclusion about board state drawn from the local file is a conclusion about `main`, not about the
keeper. Every self-heal organ (`heal-board.py`, `reclassify-needs-human.py`, …) reads the local
file, so canonical-side drift is invisible to all of them.

**This is a class, not two bugs — confirmed in two unrelated gates.** Anything reading `LIMEN_TASKS`
protects the mirror, not the artifact that publishes, so it goes green while the canonical board is
red. `heal-board` reported a healthy board while the keeper carried 12 regressed `needs-human` atoms
(fixed: `--canonical`, #2014). `check-board-partition` reports
`411 findings — {row: 200, content: 16, slug: 195}` **green** locally while CI on the publication PR
reports `404 — {row: 207, content: 17, slug: 180}` **red with 8 new** (#1780). Before believing any
board-derived verdict, run it against the extracted keeper board:

```bash
git show origin/tabularius/board-projection:tasks.yaml > /tmp/canonical.yaml   # NOT --output=, it writes nothing
LIMEN_TASKS=/tmp/canonical.yaml python3 scripts/<predicate>.py --check
```

## Look for signals with no effector

The most durable defects in this estate are not missing checks — they are checks whose finding
nothing consumes. Every observable looks healthy: a marker gets written, an auditor reports RED, a
receipt records the state. Nothing acts. Grep the full touchpoint set before assuming a signal is
handled:

```bash
grep -rn '<marker-or-flag>' scripts/ organs/ institutio/    # who SETS, who READS, who ACTS?
```

`logs/.loop-update-pending` had exactly three: `sync-release.sh` set it, `sync-release.sh` reported
it, `heartbeat-loop.sh` cleared it at startup. **Zero acted** — so the flag was cleared by the very
restart it was meant to cause, and merged rungs stayed dark behind a daemon older than its own script
(fixed: #2023). Corollary specific to this repo: **a loop-body edit to `heartbeat-loop.sh` does not
take effect on merge.** `KeepAlive` restarts on EXIT and a `while true` loop never exits. Confirm with
`python3 scripts/enactment-audit.py --check`, which prints the daemon's age against its wiring's mtime.
