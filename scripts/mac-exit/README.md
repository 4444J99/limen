# scripts/mac-exit

Tools for emptying a live Mac of git work without losing any of it. The Mac keeps running while you do this, so
**evidence goes stale in minutes**: every stage below is meant to be re-run immediately before the irreversible step, and
no stage's output may be trusted by a later one without being re-checked against the live machine.

**These tools are diagnostics. None of them is authority to erase anything.** Not a `PASS` from the verifier, not
`PROVEN-ALL` from the prover, not even `READY` from the readiness predicate: each says what one stage could establish about the
machine at one moment. Erasing the Mac is a separate, human act, taken after the predicate has been re-run against the live
machine and every line it prints has been read.

## Pipeline, in order

| Stage | Tool | Reads | Writes |
|---|---|---|---|
| 1. sweep | `git-sweep.sh [OUT [ROOT ...]]` | every git repository, worktree and bare repository under the roots (default: the generic home roots, `~/.local/share` included) | `OUT/git.tsv`, `OUT/git.roots` (the roots walked) |
| 2. carry forward | `merge-sweeps.py FRESH PREVIOUS OUT` | two sweep TSVs and their `.roots` files | `OUT`: all fresh rows plus previous rows whose path is gone; `OUT` with `.roots` for its suffix: the union of the roots |
| 3. prove remote-held | `prove-remote-held.py --tsv git.tsv --out-dir DIR` | the sweep and, over the network, `git ls-remote` of every remote | `DIR/remote-held.tsv`, `DIR/tips.tsv`, `DIR/entries.tsv`, `DIR/summary.txt` |
| 4. classify | `classify-git-sweep.py git.tsv --out real.tsv --remote-held DIR/remote-held.tsv` | the sweep and the prover's `remote-held.tsv` (without the option: the sweep alone) | the entries whose work is not provably elsewhere: the work list `preserve-git.sh` takes |
| 5. preserve | `preserve-git.sh real.tsv DEST dry\|apply` | the listed repositories (read-only) | a new `DEST/run-<UTC>/` directory |
| 6. verify | `verify-preserve.sh real.tsv RUN [SUPPLEMENTARY...]` | the run directory and the live repositories | `RUN/RESULT.txt` (first line `PASS` or `FAIL`) |
| 7. readiness | `check-exit-ready.py --sweep git.tsv --preserve-root DEST --remote-held DIR/remote-held.tsv ...` | the sweep (and its roots file), the prover's files (`tips.tsv` beside `remote-held.tsv`), every run, the non-git homing runs, the externals | one `PASS`/`FAIL`/`UNPROVEN` line per check, then `READY` or `NOT-READY` |
| (re-home) | `rehome-discover.sh`, `rehome.sh` | worktrees on external volumes that point back at the Mac | standalone stores on the external, with rollback |

Helpers: `gh-merged-pr-proof.sh` is called by the prover for the two GitHub proofs and is not run by hand;
`prove-mutation-check.py` mutates the prover's logic and requires its self-test to notice every mutant.

Self-tests run each tool on fixtures and, for the checkers, corrupt a good result and require the checker to refuse it:
`preserve-git-selftest.sh` (stages 1, 2, 4, 5, 6), `prove-remote-held.py --self-test`, `check-exit-ready.py --self-test`,
`rehome-selftest.sh`. They are heavy; run one at a time. Each tool's header comment states its usage.

### Exit codes

* `check-exit-ready.py`: `0` READY and nothing else outstanding; `1` NOT-READY; `2` a check could not establish its answer
  (UNPROVEN); `64` usage error, `-h/--help` included; `70` internal error. `--no-deep` can never yield `READY`.
* `prove-remote-held.py`: `0` a complete run and every repository PROVEN-ALL; `1` a complete run with some repository not
  PROVEN-ALL; `64` usage error; `70` internal error or an incomplete run.
* `preserve-git.sh`, `verify-preserve.sh`: `0` success (`PASS` for the verifier), `1` verifier `FAIL`, `64` usage, `66` an
  input file is missing, `73` the destination cannot be created, `75` a refused destination.
* `classify-git-sweep.py`: `0`; `65` a `--remote-held` file that is cut short (no, a duplicated or a misplaced `#END rows=N`
  row, a wrong count, a short row) or lacks a needed column, nothing written.
* `git-sweep.sh`: `0`, `64` a root that cannot be written to the roots file, `66` an explicit root that does not exist.
  `merge-sweeps.py`: `0`, `2` a roots file that is missing (the previous sweep's, unless `MERGE_SWEEPS_LEGACY_OLD=1`) or
  has no valid `#END rows=N` row, or the sweeps' headers differ (nothing is written), `64`, `66`.

Stage 6 usage (no volume name is built into either tool):

```
rehome-discover.sh [OUT_DIR [VOLUME...]]
REHOME_SKIP_VOLUMES=NAME[,NAME...] rehome.sh OUT_DIR/discovery.tsv STORE_ROOT dry|apply [RUN_DIR]
```

* `VOLUME` is a name under `/Volumes`. Given none, discovery scans every mount point directly under `/Volumes` except the boot
  volume (realpath `/`, or the same device as `$HOME`).
* `REHOME_SKIP_VOLUMES` is required. It names the volumes `rehome.sh` must never convert, for example the independent replica.
  Unset, both `dry` and `apply` refuse (exit 64) and write nothing, so forgetting it cannot convert the replica; set but empty
  (`REHOME_SKIP_VOLUMES=`) converts every volume, deliberately. The `dry` run prints the list in force and the volume of every
  worktree it plans to convert, so read that before running `apply`.

## Why each stage exists

* **Sweep** is a *local view*. Remote-tracking refs can lag, a repository-wide "unpushed" count includes stale bot branches,
  and a clean checkout can still be the only holder of a tip. It is a work list, not proof of safety. It is also built to be
  a superset of anything that looks for repositories: no depth bound, no name prune (`node_modules` is walked), `.git`
  matches in any case, and bare repositories are rows of their own (`kind=bare`). The `kind` column is derived from git, not
  from whether `.git` is a directory: `repo` when the absolute git dir is the common dir (a submodule or separate-git-dir
  checkout included), `worktree` otherwise. `git.roots` lists the roots actually walked, one realpath per line and a
  closing `#END rows=N`; the predicate walks exactly those roots when it looks for a repository the sweep missed. The
  roots file of a sweep is the sweep path with its last suffix replaced by `.roots`.
* **Carry forward** exists because a fresh sweep lists only what still exists. Anything that vanished since the previous
  sweep silently leaves the universe, which is exactly how a loss hides. The merged TSV keeps those rows so a removal must be
  explained by a rescue copy or a signed waiver. Both sweeps need a valid roots file, so a previous sweep made before roots
  files existed is refused; `MERGE_SWEEPS_LEGACY_OLD=1` carries it forward anyway, with the merged roots then the fresh
  sweep's only (one stderr line says so). A previous roots file that exists but is malformed is refused even then.
* **Prove remote-held** replaces "the remote-tracking ref says so", which is not proof: a tracking ref can be stale, forged
  by a fetch of a branch since deleted, or point at a bare repository on this very disk. It asks every remote what it holds
  now (`git ls-remote`, never a fetch) and proves each local tip against that listing. Its `tips.tsv` is what the predicate
  binds a `PROVEN-ALL` verdict to; its `gaps` column names every documented limit of a proof.
* **Classify** splits entries into safe, disposable and real exposure, counting repository-level facts from repository and
  bare-repository rows only (a worktree row reports its shared repository, so counting it per worktree repeats one exposure).
  The sweep columns alone call a clean row whose branches are all in remote-tracking refs "safe" even when no remote holds
  everything on it (a commit only a reflog holds, a tag the remote lacks, LFS objects, filter output), and
  `preserve-git.sh` only ever sees the rows it is given. So run classify with `--remote-held <prover out>/remote-held.tsv`:
  every present row the prover does not prove `PROVEN-ALL` with empty `gaps` (or does not name at all) also enters the work
  list with the reason `remote-not-proven`, and every checkout holding bytes behind a `filter` attribute that differ from
  the index blob enters it with `filtered-content`, because a `PROVEN-ALL` remote cannot hold what git never stored. The
  file must be whole (exit 65 otherwise) and fresh: a ref that moved after the proof needs a new prove before classify, or
  the predicate fails that row closed. Without the option classify is the sweep-only view it always was.
* **Preserve** copies, never changes. For each unique git common directory it writes a self-contained `git bundle --all`
  (all refs, tags, remotes, and the top `refs/stash` entry), every lower stash entry as a patch, a binary patch of tracked
  changes, a tar of untracked non-ignored files, head bundles for detached worktrees, and a raw working-tree tar for
  checkouts whose gitfile no longer resolves. A bundle holds refs and their history and nothing else, so wherever the git
  dir holds more, it also writes `bundles/<slug>.gitdir.tar`, a raw copy of the git dir: for commits reachable only from a
  reflog (a `reset --hard`, an amend, a deleted branch, every lower stash entry), per-worktree refs (`refs/worktree/`,
  `refs/bisect/`, `refs/rewritten/`), LFS or git-annex objects and submodule git dirs, all read per git dir so a worktree whose
  checkout is gone still counts. An LFS store that `lfs.storage` moved outside the git dir gets `bundles/<slug>.lfs-storage.tar`.
  Tracked paths with a `filter` attribute (clean/smudge filters, `filter=lfs`) get `dirty/<slug>.filtered.tar` of their
  working-tree bytes: git stores what the filter outputs, so status and diff stay clean while the file is the only copy.
  Credential-pattern files are never copied; their names and sizes are listed. So is every `config` or `config.worktree`
  anywhere in a copied git dir (top level, `modules/*`, nested modules, `worktrees/*`) whose content carries a
  `user:password@` URL: it stays out of the raw copy and is listed, and the verifier requires it to be absent. The network is never used
  (`GIT_NO_LAZY_FETCH=1`): a partial clone would otherwise write fetched objects into the repository.
* **Verify** does not trust the producer: it recomputes slugs and common directories itself, re-verifies every bundle inside
  an empty bare repository, stream-checks every pack, lists every tar, recomputes every sha256, and checks that every row is
  covered. It re-derives from live git what a bundle drops and checks the copy holds it: every reflog-only commit's object,
  every per-worktree ref file and its commit, every LFS/annex file, every `modules/` entry, every file of a relocated LFS
  store, and exactly the working-tree files of each checkout's filter-attribute paths. A run that did not verify is a `FAIL`.
  `RESULT.txt` carries a `manifest_sha256=` line pinning the `MANIFEST.tsv` the verdict is about; a manifest edited
  afterwards no longer matches it.
* **Readiness** re-derives everything it can from the live machine and refuses to take a producer's word for it; see its
  docstring for every check. `READY` means every check except `human-erase` passed. It is still a diagnostic.

## Safety properties

* Stages 1 to 6 are read-only toward the repositories they inspect. `preserve-git.sh` writes only a brand-new run directory
  (it refuses to reuse one) and its scratch directory. Re-homing is the one exception: `rehome.sh apply` rewrites the single
  `.git` pointer file of each external worktree (the old content is kept in the new store, and a rollback script is written),
  so it is run only on an explicit decision, after a `dry` run.
* Scratch lives under `PRESERVE_SCRATCH` (default `${TMPDIR:-/tmp}/preserve-git-scratch`), never inside the checkout.
* `preserve-git.sh apply` refuses a destination on the same device as `$HOME` (a copy on the disk being protected protects
  nothing); fixtures and self-tests opt out with `PRESERVE_ALLOW_SAME_DEVICE=1`.
* `PRESERVE_MIN_FREE_GIB` (default 100) is a free-space floor on the destination; `PRESERVE_SOFT_DEADLINE_SEC`
  (default 1650) bounds a run, and an overrun is a failed run, not a partial success. The raw git-dir copies add to the
  bytes a run needs: most active repositories have a commit only a reflog holds (and every repository with two stash
  entries does), so expect a full copy of the git dir on top of the bundle for many of them. That cost is accepted, because
  those commits are exactly what an erase destroys; a slimmer artifact (the reflog-only commits alone) is a possible later
  optimisation.
* Nothing here deletes anything, anywhere.

## Reading the results

* `PASS` from `verify-preserve.sh` means the run directory is internally consistent and matches the live repositories *as of
  that moment*. It says nothing about repositories created or changed afterwards, and a preserved repository is not a
  statement that its content exists on a remote.
* `PROVEN-ALL` from the prover means a fresh listing of a network remote held every tip, at the time of the listing. A
  remote-tracking ref, a filesystem-path remote, or a remote on this machine or its LAN is never proof. A non-empty `gaps`
  column makes the row untrusted.
* `READY` from the predicate means no check it can run found a gap, with `human-erase` outstanding. A sweep that was not run
  immediately before, a repository created since, or a `FAIL` or `UNPROVEN` line anywhere means it is not ready, and a human
  reads the lines, not only the last one.
* Re-run stages 1 to 7 immediately before any irreversible step and treat any `FAIL`, any `UNPROVEN` and any row that
  changed since as unproven. None of these tools, alone or together, authorizes the erase.
