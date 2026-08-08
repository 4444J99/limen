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

**Two rails run different code, and confusing them turns a real verification into a false one.**
A `scripts/*.py` organ inserts the *live checkout's* `cli/src` at `sys.path[0]`
(`heal-board.py:49`), so it executes your merged working tree the moment `sync-release.sh`
fast-forwards it. The installed CLI does not. Measured 2026-08-07: the pin was **62 commits**
behind `origin/main`, so `BrokerQuotaExhausted` (#2057) was demonstrably live on the heal-board
rail and **absent from the deployed runtime** — `grep -c BrokerQuotaExhausted
~/.local/share/limen/current/venv/lib/python3*/site-packages/limen/conduct/client.py` → `0`.
Verifying a `cli/src` fix by driving a *script* proves nothing about `limen <verb>`, and the
reverse holds too. State which rail you drove.

The lag is already sensed — do not re-derive it:

```bash
python3 scripts/check-runtime-lag.py     # exit 1 + the exact `domus-limen-runtime install --sha` line
readlink ~/.local/share/limen/current    # what is actually installed
```

It takes no `--check` flag (passing one is an argparse error, i.e. exit 2 — not a verdict).

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
| a beat sensor (`sensors.yaml`) | `beat-sensors.py --run --source <src> --dry-run` proves it is in the execution set; its OUTPUT lands in `logs/metabolize-sensors.log` — see below, because being in the matrix is not being read |

### A sensor in the matrix is not a sensor anyone reads

`--list` and `--dry-run` answer "is it wired". Neither answers "does its finding reach a reader",
and for an advisory sensor whose entire product is a printed finding, only the second matters.

```bash
python3 scripts/beat-sensors.py --run --source metabolize --dry-run   # in the execution set?
tail -40 logs/metabolize-sensors.log                                  # what the last pass SAID
stat -f '%Sm' logs/.voice/metabolize_pass                             # when that pass ran
```

Three traps, all measured 2026-08-07 while verifying a sensor shipped hours earlier:

- **The pass used to be piped through `tail -5`.** 57 sensors and — counted from the first post-fix
  pass, not estimated — **1,784 lines**, five kept.
  The `review-harvest` sensor ran, reported unresolved findings, and no log recorded a word of it —
  the organ built to prove a finding gets *consumed* had its own finding thrown away by its runner
  (fixed: `logs/metabolize-sensors.log`, #2048). If a sensor's output is missing, check what the
  rung does with the runner's stdout before concluding the sensor did not run.
- **A voice stamp is not evidence of content.** `logs/.voice/<id>` records that a sensor VISITED,
  never what it said, and `_stamp()` only fires for sensors declaring a `cadence` — so a
  cadence-less sensor legitimately has no stamp, and a stamped one may still have been discarded.
  Absence of a stamp proves nothing in either direction.
- **Absence of the LOG proves nothing either — and that trap is one level up from the stamp.** The
  redirect truncates on write, so `logs/metabolize-sensors.log` does not exist at all until the first
  *due* pass after a daemon restart. Measured: #2048 merged 19:19:36, the daemon restarted 19:51:55
  (so it HAD the fix), and the file stayed missing until 20:33:01 — **74 minutes** during which
  "the log is missing" was true and meant nothing. Do not read that absence as the discard bug, and
  do not reach for the loop-body corollary below: check the daemon's start time against the fix's
  merge time FIRST (`ps -eo pid,lstart,command | grep heartbeat-loop` vs `git log -S`), because a
  daemon that restarted after the merge already has the change.

`source: [metabolize]` sensors do **not** run every heartbeat tick. `metabolize.sh` has no scheduler;
the daemon runs them from one wall-clock-throttled rung (`metabolize_pass_due`, hourly by
`LIMEN_METABOLIZE_SENSORS_SECS`).

**The throttle is hourly but it is evaluated ONCE PER CYCLE, and a cycle is not a tick.** The
`── tempo: … → 120s ──` line is the *sleep between cycles*, not the cycle's duration — misreading it
as the period is what makes a healthy beat look stalled. Measured cycle starts: 19:53:13 → 20:01:04
→ 20:09:19 → 20:28:29, i.e. **8 to 19 minutes each**, and the sensor pass itself ran **13+ minutes**
inside one. So the honest bound on "my sensor has not reported yet" is *the hour, plus a full cycle,
plus the pass* — call it ~90 minutes worst case, not ten. Before concluding a rung is dark, confirm
the beat is advancing at all (`tail logs/beat-rungs.jsonl`, `grep -a '──── beat' logs/heartbeat.out.log
| tail`) and check whether the cycle that would have evaluated the rung *started before it came due*.
A per-sensor `cadence` adds a second gate on top: `_due` wants `beat % cadence == 0` **or** a stamp
older than `cadence × loop_max` (for `cadence: 12` at the 1800s default, that fallback is **6 hours**),
so a cadence-declaring sensor legitimately sits out most passes.

## Start here: ask which rungs are failing on EVERY beat

Since #2050 the beat records one `{ts,rung,exit}` per rung per beat, and #2059 folds it into
per-rung consecutive-failure streaks. That makes "what is quietly broken in the live fleet" a
one-command question, and it is the cheapest high-yield probe available — **run it before
anything else.**

```bash
python3 scripts/enactment-audit.py --efficacy-only        # streaks, with the threshold applied
grep -v '"exit":0' logs/beat-rungs.jsonl                  # every non-zero outcome, raw
grep -a "RUNG FAIL" logs/heartbeat.out.log | tail -20     # the banners, with real diagnostics
sed -n '<start>,<end>p' logs/heartbeat.out.log            # the block, for the actual traceback
```

Asked once on 2026-08-07 it returned three live defects in minutes, two of them unknown:
`heal-board-canonical` (exit 75, the filed keeper-quota block), `limen-release-stale` (409 —
issue #2063), and `generate-organ-backlog` (`IntakeContractError` on a ladder row spanning two
repos). Read `exit=75` as **blocked on a filed human-owned condition** (`EX_TEMPFAIL`), not as a
fleet defect — it is deliberately reported without going RED.

Two things to keep in mind when reading a streak:

- **A streak of 1 is noise by design** (`LIMEN_RUNG_FAIL_STREAK_RED`, default 3). Do not chase it
  until it repeats; do not dismiss it either — check whether the rung even runs every beat.
- **A rung absent from the ledger is not a healthy rung.** Only ~16 labels appear after a handful
  of beats because most rungs are cadence-throttled, and a rung invoked without `beat_run` never
  records at all. `institutio/governance/beat-diagnostics-baseline.txt` names how many sites in
  each beat script are still unrecorded.

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
  R="^--- (a/|/dev/null)"                                  # the header, and ONLY the header
  git diff origin/main -- <files> | grep '^-' | grep -vE "$R"  # uncommitted: catches the clobber
  git diff origin/main...HEAD    | grep '^-' | grep -vE "$R"  # committed: resolves the merge base
  git merge-base --is-ancestor origin/main HEAD               # 0 ⟺ up to date or ahead; see below
  ```

  **Match the header's full shape; every shortcut here under-counts.** A diff prefixes each removed
  line with `-`, so a source line already starting with a dash gains one: `--flag` renders `---flag`,
  and `-- sql comment` renders `--- sql comment` — indistinguishable from the header by prefix alone.
  Measured on a fixture with **four** real removals (an ordinary line, a blank line, a `--flag` line,
  and a `-- ` comment line):

  | pattern | counts | verdict |
  |---|---|---|
  | `grep '^-'` | 5 | over by one per file — counts the header |
  | `grep -E '^-[^-]'` | **1** | **drops the blank, the `--flag`, and the `-- ` line** |
  | `grep -v '^--- '` | **3** | still **drops the `-- ` comment** — it looks exactly like a header |
  | `grep -vE '^--- (a/\|/dev/null)'` | **4** | exact: only the real header forms excluded |

  Those four numbers are asserted against the fixture by `scripts/tests/diff-removal-count.test.sh`,
  not copied from a run. The first draft of this table carried 2 and 4 where the fixture produces 1
  and 3 — wrong numbers in a table whose entire subject is counting precisely, and the gate did not
  notice because it asserted only the *relations* (this one over-counts, that one under-counts).
  A comparison that is merely directionally right is how the previous two versions of this recipe
  survived, so the counts are now checked exactly.

  Over-counting is merely noisy: you inspect a phantom line and move on. **Under-counting hides the
  clobber this check exists to find.** Two successive "fixes" here each traded one direction of error
  for the other before landing on excluding the header by its actual shape — `--- a/…` for a tracked
  file, `--- /dev/null` for a new one — rather than by counting dashes or matching `--- ` loosely.

  **`--is-ancestor` nonzero does NOT mean "behind".** It means `origin/main` is not an ancestor of
  `HEAD` — which is **behind OR diverged**, and those want different repairs (fast-forward vs rebase
  or merge). Verified while writing this: a branch cut from `origin/main` an hour earlier, one commit
  ahead with one commit landed underneath it, reads `1` — it is diverged, not behind. Get the actual
  shape before choosing:

  ```bash
  git rev-list --left-right --count origin/main...HEAD   # -> "<behind-by>  <ahead-by>"
  ```

  A long-running background `await-pr.sh` fetches, so `origin/main` advances *under you* mid-session
  and a branch that was current when you cut it is behind by the time you diff it. Observed: a clean
  branch appeared to delete an entire merged feature (`repair_canonical`, its params, its tests, its
  rung). Check ancestry first; if it is not an ancestor, get the counts, rebase, and re-diff rather
  than interpreting.
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
- **A fresh worktree has no `web/worker/node_modules`,** and `npm --prefix web/worker run check` then
  reports 4 of 5 test *files* failing with no useful summary — it looks like your change broke the
  Worker. Run one file directly to see the real cause:

  ```bash
  node --test web/worker/test/conduct-keeper.test.js   # from the repo root
  ```

  That prints `ERR_MODULE_NOT_FOUND: ajv`, which the aggregate run swallows. Fix:
  `npm --prefix web/worker ci`. Keep the `--prefix` form everywhere — a bare `npm run check` only
  works from inside `web/worker/`, and "which directory was I in?" is the ambiguity that makes this
  symptom look like a code failure twice over.
- **Load-sensitive tests are a CLASS, and every member asserts on something *bounded*** — a
  deadline, or a race against a process that must get there first. They are not randomly flaky:
  they fail under contention, which is exactly when the full suite runs, and pass when you re-run
  them alone to check. That asymmetry is what gets them dismissed. **Isolation does not settle the
  verdict** — a bare pass is consistent with both a real defect and a timing artifact. Settle it by
  finding the bound: grep the failure string to the line that emits it and read what it waits on.

  | test | the bound | tell |
  |---|---|---|
  | `test_campaign_relay_effector::test_full_relay_exec_proof_closes_while_keepalive_remains_live` | a spawned provider must write its pidfile before the parent reads it | duration — passing ~16s, failing ~4s; observed 4 fails then 3 passes on the *same* commit |
  | `test_workstream_command.py::test_autonomous_jules_workstream_uses_remote_cloud_transport` | `scripts/lib/workstream-capsule.sh` runs `run-bounded --timeout-seconds … git ls-remote origin HEAD`; the test caps that subprocess at 10s | `launch-environment error: configured remote origin is unavailable` |

  The second is the sharper trap, because **its message names a cause that is not the cause** — the
  remote is fine; a network round-trip missed a deadline. Nothing in the output says "timeout", so
  it reads as broken connectivity and sends you to `git`/DNS.

  **Do not use load average as the discriminator.** Measured on one commit, minutes apart: FAILED
  at 5-min avg **9.02**, then PASSED at **13.75**. The number was higher on the passing run. What
  differed was a second session holding the heavy-verification lease — competing *heavy* work, not
  the scalar. So "re-run on a quiet host" means check for another `verify.py`/`pytest` owner
  (`scripts/verify-scoped.sh` reports `EXIT=75 heavy-lease-held` when one is active), not check
  `uptime`. And note the suite is itself a load source: `pytest -n auto` drove this host past 13 on
  its own, so a full-gate run is never quiet in the `uptime` sense and never needs to be.

  **But the lease only covers verification owners — the BEAT is uncovered heavy work.** The `heavy`
  lease (`limen.host_admission`, denial reason built as `f"{kind}-lease-held"` at
  `host_admission.py:1092`, surfaced by `scripts/verify.py:783` as exit **75**) serializes one
  verification run against another. It knows nothing about `limen dispatch --live`, which the
  heartbeat launches on its own cadence. So **`EXIT=75` absent is not proof of a quiet host.**
  Measured 2026-08-07: a scoped run returned plain exit **1** with two contention failures
  (`test_campaign_relay_effector` plus `test_workstream_contract::test_predecessor_git_probes_fail_at_hard_output_ceilings`,
  the latter masquerading as `PermissionError: [Errno 1] Operation not permitted`) while
  `python -m limen dispatch --agent jules --live --limit 10` held 96% CPU. Before re-running, check
  for the fleet as well as for another verifier:

  ```bash
  pgrep -fl "limen dispatch .*--live"     # the beat's own heavy work; holds no heavy lease
  ```

  Wait for it to clear rather than racing it — CLAUDE.md caps concurrent heavy processes on this
  16GB host. And do not reach for `grep` to check whether a reason string like `heavy-lease-held`
  exists: it is assembled by f-string, so a literal search returns nothing and "I found nothing"
  reads identically to "the citation dangles". Grep the *construction*, not the result.
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
