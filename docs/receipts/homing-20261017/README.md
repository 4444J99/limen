# Local-to-remote homing receipt — 2026-10-17

Objective (direct human request): every local git state homed on a remote, then local sprawl
reclaimed so the host has room to work and the sprawl does not regrow. This receipt records what
was homed, what was refused and why, what the operator can reclaim with one script, and the
structural cause of recurrence.

Host state at start: disk 97% (16 GiB free of 460), host admission `allowed=false` on swap
fraction, five live Codex `codex-worktree-write` leases. Nothing in this session created a
worktree, moved a HEAD, or touched an index: every homing commit was built through a temporary
index (`tools/home.py`) and pushed by object id, non-force, to a named remote ref.

## Homed (content now on a remote)

| Repo | What | Remote ref |
|---|---|---|
| 4444J99/limen | live-checkout untracked plans + containment tests (5 files) | `preserve/live-checkout-untracked-20261017` |
| organvm/peer-audited--behavioral-blockchain | nested limen checkout, 18 dirty/untracked source files | `preserve/limen-nested-checkout-wip-20261017` |
| 4444J99/domus-genoma-private | stash@{0} (2026-10-12 wip), stash@{1} (2026-10-16 unstaged) | `preserve/stash-main-wip-local-snapshot-20261012`, `preserve/stash-master-local-snapshot-unstaged-20261016` |
| 4444J99/domus-genoma-private | stash@{2} (2026-07-02) — chain authored `Test User <test@example.com>`, rejected by push ruleset; homed as tree commits over PR 149 head | `preserve/security-hardening-local-tip-20261017`, `preserve/stash-security-hardening-autonomic-sync-20260702` |
| 4444J99/domus-genoma-private | live checkout dirty `.serena/project.yml`; `host-repair-20260925` worktree's 95 untracked continuation files; `fix/quota-maintenance-20261010` branch | `preserve/live-master-dirty-20261017`, `preserve/host-repair-20260925-untracked-20261017`, `fix/quota-maintenance-20261010` |
| organvm-vii-kerygma/portfolio | `remediate-198` head + its 8 dirty generated-data files; orphaned pre-rewrite heads `chamber-pr-229`, `remediate-228`, `remediate-229`; conflicted chamber merge of PR 169 (worktree snapshot) | `remediate-198`, `preserve/remediate-198-wip-20261017`, `preserve/chamber-pr-229-orphaned-history-20261017`, `preserve/remediate-228-…`, `preserve/remediate-229-…`, `preserve/chamber-pr-169-conflicted-20261017` |
| organvm/organvm-engine | chamber pr-104 staged workflows + changelog | `preserve/chamber-pr-104-staged-20261017` |
| organvm-iii-ergon/speech-score-engine | chamber pr-1 staged CLAUDE.md | `preserve/chamber-pr-1-staged-20261017` |
| organvm/the-thing-without-a-name (public) | `main` 4 commits ahead (ambisonic demo); `topic/engine-extraction-integration` | `heal/main-ahead-ambisonic-demo-20261017`, `topic/engine-extraction-integration` |
| organvm/organvm-corpvs-testamentvm, organvm-iii-ergon/public-record-data-scrapper, 4444J99/post-dsp-platform | one stash each | `preserve/stash-…-20261017` |
| organvm/application-pipeline (private), organvm/metasystem-master | doctoral `applications` and `omni` dirty files | `preserve/live-dirty-20261017` |
| 4444J99/a-i--skills | three local-only branches (two back open PRs 47/48) | `preserve/claude-default-on-skills-local-tip-20261017`, `feat/closeout-live-state-20261016`, `fix/local-skill-catalog-review-20261016` |

Already homed before this session (verified, no action): domus `master` tip is contained in
`origin/wip/master-local-snapshot-20261016`; limen stash@{0} already copied to
`limen--private` per its own message.

## Refused or held (content still local, by design or by blocker)

- **limen pre-rewrite lineage (4 objects).** `av-directory-receipt-20261010` head,
  `reap-scope-20261004` head + dirty receipts, live stash@{0}. The repo's lineage `pre-push` guard
  refused them: they carry pre-rewrite history. Disposition belongs to
  `docs/plans/2026-10-16-prerewrite-containment.md` (#2878) decisions D1/D2; step 6 of that plan
  names these worktrees. Not routed around.
- **GES worktrees (3, reassign).** `ges-native-enforcement-pilot`, `ges-wave-20261009`,
  `github-engineering-standards-a1-integration` (16 tracked-dirty files on a detached head).
  Heads are on remote; dirt is untracked evidence. `finite-workspace-recovery.md` requires
  positive owning-writer release for GES checkouts; Codex leases were live. Untouched.
- **kerygma/portfolio `chamber-pr-169` branch.** Push failed: *This repository exceeded its LFS
  budget*. Account-level blocker; the worktree snapshot of the same PR was homed without LFS objects.
- **`_people-private` (4.6 GiB, zero commits, no remote) and `.limen-private/shelter-vault`
  (3.9 GiB, no remote).** No remote is configured; choosing one is an owner decision because the
  content is restricted. Nothing pushed.
- **Media/untracked corpus** in `audiovisual-composition-system` (`god-here`, top-level Backup/,
  `.toe` files, `time-moment-brief` evidence) — not git-shaped; belongs to the AV custody rail.
- Trivial: `av-policy-readback-20261010` holds only an untracked `.pr-body.md` on PR 2844's merge commit.

## Branch classification (tools/branches.py + tools/prs.py)

| Repo | reapable (tip on remote) | squash-merged residue | pushed |
|---|---|---|---|
| limen | 2 | 27 (one is PR 2840's head) | 0 |
| domus-genoma | 8 | 1 | 2 (+2 tree commits) |
| universal-mail--automation-backup | 317 `reap-unreachable-*` | — | 0 |
| styx-public-repo / portvs / scrapper / engine / the-thing | 9 / 3 / 3 / 1 / 1 | — | 0 |
| generative-multimedia-spatial-environment | — | 2 closed dependabot | 0 |
| a-i--skills / kerygma portfolio | 0 / 2 | — | 3 / 3 |

## What the operator can reclaim now — `tools/reclaim-operator.sh`

`dry-run` derives fresh exact plans and lists; `apply` executes them; `post-check` reruns the debt
census. The permission classifier denied even organ dry-runs from the agent session, so this is the
escalation script the guard protocol calls for.

| Target | Size | Proof |
|---|---|---|
| 6 worktree roots via `reclaim-cycle.py` (exact plan sha, fail-closed) | ~370 MiB | organ remote_proof per root |
| 3 `node_modules` via `reclaim-generated-caches.py` | 852 MiB | regenerable |
| ~370 local branches | ~0 | tip contained in a remote ref, re-verified at delete time |
| 3 homed chamber worktrees | ~60 MiB | rows above |
| `_limen-worktree-abandonment/generated-*` (pycache, .cache, build out) | ≤743 MiB | generated by name |

## Where the disk actually is (owner decisions, not reclaimed here)

| Path | Size | Governing policy |
|---|---|---|
| `limen/.limen-private/custody-staging` | 16 GiB (chatgpt-live-inventory 3.9G, private-document-copy 4.0G, codex-legacy-share 3.1G, nongit-duplicates 1.8G, two codex-release-quarantines 1.6G) | custody staging: retire only through the custody rail after remote readback |
| `4444J99/.custody-20261001-uMyM2v` | 15 GiB | same |
| `limen/.agent-runtime` (codex 7.3G, gemini 6.2G, opencode 3.6G, claude 1.4G) | 18.5 GiB | vendor state; never deleted to clear quota |
| `4444J99/engineering-environment-standards` (GES `.cache` 2.2G) | 2.3 GiB | GES custody hold |
| `4444J99/styx-launch-package` (node_modules 494M, .next 115M) | 1.3 GiB | regenerable, outside this reclaimer's scope |

## Structural cause of recurrence

1. **No heartbeat is loaded.** `launchctl list` shows only `creds-hydrate`, `claude-stub-heal`,
   `moneta`, `moneta-tunnel`. The autonomic reclaim rung has not run on a schedule; the last
   `reclaim-worktrees.jsonl` applies are hand-run sessions (2026-10-13). `merge-drain.log` stops
   2026-08-21.
2. **The reclaim organs fail under bare `python3`.** `worktree-debt.py`, `worktree-reclaim-candidates.py`,
   `worktree-preserve-dirty.py` all die on `import rfc8785`; only `cli/.venv/bin/python` has it, and
   `metabolize.sh` calls bare `python3`.
3. **Preservation is local.** `worktree-preserve-dirty.py` writes to `.limen-private/session-corpus`,
   so "preserved" worktrees still consume the same disk until a separate remote step runs.
4. **Pre-rewrite lineage** (2026-10-10) orphaned local heads in limen and kerygma/portfolio; the
   lineage guard is correct but means those roots cannot be homed by push, only by the containment plan.

Observation: `scripts/check-prerewrite-containment.py` reported "manifest commit absent" even
though `git cat-file -t 66b2ee71a` resolves in the shared checkout after a fetch.

## Filed atoms

- #2916 — autonomic reclaim dead (no heartbeat loaded; organs fail under bare python3).
- #2912 — custody-bound disk retirement decision (16 + 15 + 18.5 GiB).
- #2913 — kerygma/portfolio LFS budget blocks `chamber-pr-169`.
- #2914 — promote the remote-first homing tool into `scripts/`.
- **Operator to file** (the agent session's `gh issue create` for this one was denied twice by the
  permission classifier):

```bash
gh issue create --repo 4444J99/limen --label lifecycle:active-human \
  --title "Owner decision: remote custody for _people-private (4.6 GiB, zero commits) and shelter-vault (3.9 GiB, no upstream)" \
  --body "Both repos have no remote configured. _people-private: 4.6 GiB, 'No commits yet', whole tree staged. limen/.limen-private/shelter-vault: 3.9 GiB main, no upstream, one modified custody receipt. Content is restricted; the owner picks the private remote and whether encryption precedes the push (bulk-custody policy). Receipt: docs/receipts/homing-20261017/."
```

## Not in scope

The 11 unlabeled open limen PRs are remote sprawl and were not touched (they would each return
`LIFECYCLE-UNKNOWN` from the merge drain until labelled).
