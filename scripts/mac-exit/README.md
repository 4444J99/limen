# scripts/mac-exit

Tools for emptying a live Mac of git work without losing any of it. The Mac keeps running while you do this, so
**evidence goes stale in minutes**: every stage below is meant to be re-run immediately before the irreversible step, and
no stage's output may be trusted by a later one without being re-checked against the live machine.

## Pipeline, in order

| Stage | Tool | Reads | Writes |
|---|---|---|---|
| 1. sweep | `git-sweep.sh [OUT]` | every git repository and worktree under the home roots (including `~/.local/share`) | `OUT/git.tsv` |
| 2. carry forward | `merge-sweeps.py FRESH PREVIOUS OUT` | two sweep TSVs | `OUT`: all fresh rows plus previous rows whose path is gone |
| 3. classify | `classify-git-sweep.py git.tsv --out real.tsv` | a sweep TSV | the entries whose work is not provably elsewhere |
| 4. preserve | `preserve-git.sh real.tsv DEST dry\|apply` | the listed repositories (read-only) | a new `DEST/run-<UTC>/` directory |
| 5. verify | `verify-preserve.sh real.tsv RUN [SUPPLEMENTARY...]` | the run directory and the live repositories | `RUN/RESULT.txt` (first line `PASS` or `FAIL`) |
| 6. re-home | `rehome-discover.sh`, `rehome.sh` | worktrees on external volumes that point back at the Mac | standalone stores on the external, with rollback |

`rehome-selftest.sh` exercises stage 6 on fixtures. Each tool's header comment states its usage. The tools that need arguments print a
usage line when called without them; `git-sweep.sh` and `rehome-discover.sh` are read-only and run with a default output directory
under `${TMPDIR:-/tmp}` when called bare.

## Why each stage exists

* **Sweep** is a *local view*. Remote-tracking refs can lag, a repository-wide "unpushed" count includes stale bot branches,
  and a clean checkout can still be the only holder of a tip. It is a work list, not proof of safety.
* **Carry forward** exists because a fresh sweep lists only what still exists. Anything that vanished since the previous
  sweep silently leaves the universe, which is exactly how a loss hides. The merged TSV keeps those rows so a removal must be
  explained by a rescue copy or a signed waiver.
* **Classify** splits entries into safe, disposable and real exposure, counting repository-level facts from repository rows
  only (a worktree row reports its shared repository, so counting it per worktree repeats one exposure).
* **Preserve** copies, never changes: for each unique git common directory it writes a self-contained `git bundle --all`
  (all refs, tags, remotes, and the top `refs/stash` entry), every lower stash entry as a patch, a binary patch of tracked
  changes, a tar of untracked non-ignored files, head bundles for detached worktrees, and a raw working-tree tar for
  checkouts whose gitfile no longer resolves. Credential-pattern files are never copied; their names and sizes are listed.
  The network is never used (`GIT_NO_LAZY_FETCH=1`): a partial clone would otherwise write fetched objects into the repository.
* **Verify** does not trust the producer: it recomputes slugs and common directories itself, re-verifies every bundle inside
  an empty bare repository, stream-checks every pack, lists every tar, recomputes every sha256, and checks that every row is
  covered. A run that did not verify is a `FAIL`.

## Safety properties

* Stages 1 to 5 are read-only toward the repositories they inspect. `preserve-git.sh` writes only a brand-new run directory
  (it refuses to reuse one) and its scratch directory. Stage 6 is the one exception: `rehome.sh apply` rewrites the single
  `.git` pointer file of each external worktree (the old content is kept in the new store, and a rollback script is written),
  so it is run only on an explicit decision, after a `dry` run.
* Scratch lives under `PRESERVE_SCRATCH` (default `${TMPDIR:-/tmp}/preserve-git-scratch`), never inside the checkout.
* `preserve-git.sh apply` refuses a destination on the same device as `$HOME` (a copy on the disk being protected protects
  nothing); fixtures and self-tests opt out with `PRESERVE_ALLOW_SAME_DEVICE=1`.
* `PRESERVE_MIN_FREE_GIB` (default 100) is a free-space floor on the destination; `PRESERVE_SOFT_DEADLINE_SEC`
  (default 1650) bounds a run, and an overrun is a failed run, not a partial success.
* Nothing here deletes anything, anywhere. Erasing the Mac is a separate, human act.

## Reading the results

`PASS` from `verify-preserve.sh` means the run directory is internally consistent and matches the live repositories *as of
that moment*. It says nothing about repositories created or changed afterwards, and a preserved repository is not a
statement that its content exists on a remote. Re-run stages 1 to 5 immediately before any irreversible step and treat any
`FAIL` or any row that changed since as unproven.
