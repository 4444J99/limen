# OpenCode tranche — collector corrections and exact reclaimer qualification

## Mission and start
Own the substantial source-analysis and review tranche. Agy is the only recovery writer. Return unified patches, test specifications and qualification evidence as text to Agy; no file/scratch/ledger writes, fetching, staging, switching, commits or removal.

Read this handoff and the shared contract. Do not begin another whole-estate scan. Before source/candidate work obtain Agy's broker-admitted packet naming exact common directories, immutable repository IDs, source revision, paths, original deadline, bounded spend and receipt destination. Without it return the precise missing packet once and stop; no repeated “one more check” loop.

## Deliverable A: coherent collector correction patch
Static-review the deposited S2-evidence collectors and S2-handoff at the assigned revision. Propose one correction set:
- Preserve all remotes, multiple fetch/push URLs, upstream relationships and refspecs. Provider identities require authenticated immutable IDs.
- Advertise live heads and tags; distinguish annotated tag object OID and peeled target, comparing OIDs rather than only names.
- Classify branches using configured upstreams. Ancestry exit 0=true, 1=false, other exits/errors=unverifiable. Local ancestor of upstream means behind, not a push-forward operation.
- Capture every registered worktree HEAD and standalone porcelain flags by key presence. Enumerate complete stash reflog stacks and auxiliary parents in valid repository context.
- Read checkout .gitmodules and recursive submodule gitdirs; resolve relative alternates correctly, preserving unreadable/error states.
- Keep exclusions, cloud/symlink coverage and marker/bare-store/worktree classes explicit. Missing data cannot silently become zeros or whole-store clean-exact status.

Correct your previous review's overstatements too: git -C into a bare store is not inherently wrong; .cache pruning does not mean every directory named cache was excluded; a later timestamp/count/free-space difference does not falsify an earlier observation; alternates open failures must be described as the source actually handles them. Absence of an advertised exact tip is not absence from recoverable remote history. Do not promote samples into all-store findings.

## Deliverable B: exact linked-worktree reclaimer patch and tests
Review scripts/reclaim-worktrees.py, cli/src/limen/worktree_abandonment.py and implicated tests at the pinned revision.
- Add --candidate-path PATH with exact selection before classification. An absent/unregistered/ineligible target must not fall back to another candidate.
- Bind linked-worktree plan digest to HEAD, common-directory and target filesystem identity, protection registry digest, source revision and remote custody proof.
- Recheck these identities, ownership, clean/untracked/ignored payload and dependencies immediately before native non-forced detach.
- Retain failed/partial journal operations; success requires physical absence and absent registration, with the common store/refs intact.
- Specify tests for selector isolation; stale plan/HEAD/provider/inode/device/protection rejection; dirty/ignored/active/dependency retention; missing-object errors; local-behind direction; partial deletion/journal recovery; idempotent second pass.

Keep the smallest qualified correction. The defective standalone provider refs/heads or refs/tags versus refs/remotes boundary is separate from linked detach. Propose its strict Git-ref-syntax fix separately with matching nested validation; do not enable whole-store deletion without complete custody. The clone-reaper ignore_errors=True accounting remains unqualified and unused unless corrected and tested.

## Deliverable C: candidate qualification
For Agy's exact candidate, review immutable provider identity, full OIDs/fresh refs, path identity, source revision, plan digest, protection, actual process/lease ownership, payload/custody and dependency proof. Plists prove configuration, not loaded jobs; command-line matches do not prove cwd/activity. Parent-runtime database locks do not prove all child temporary stores are held open.

Return exactly one allowlisted operation only after every relevant proof and test passes. Otherwise return an empty allowlist naming only the remaining candidate-specific gaps, retaining the candidate. Do not repeat provisional estate-wide counts or issue new custody claims.

## Return and cadence
Deliver A+B as one bounded patch/review batch, then C for one concrete candidate. Include source revision, actual executed command exits, unexecuted checks explicitly marked, qualification decision and remaining spend. Agy applies changes and performs scoped verification. Independent acceptance must be reserved separately before removal; your proposal alone is not retirement authority.

## Shared contract
Read /Users/4jp/AGENTS.md and applicable repository/scoped instructions. Original outcome: Git parity across ~/Workspace, followed by custody-qualified local retirement. Owners: 4444J99/limen#2739, 4444J99/portvs#14, 4444J99/domus-genoma#397. Reuse these records; do not duplicate issues or close atoms.

This handoff is planning authority, not a lease or renewed budget. Original ceiling: 120 cumulative agent-minutes across all providers, descendants, inspection, consolidation and restarts; each admitted attempt at most 30 minutes, verification at most 10 minutes; one changed-input corrective retry. Native accounting checkpoint established 79.69 completed agent-minutes before additional Agy/current-turn/stopped-stream reconciliation. Neither exhaustion nor remaining allowance is established by that partial total. Re-query live records. Daily provider runs are not agent-minutes; overlapping agents' execution adds, while idle/approval gaps require separate treatment.

Known access correction: authenticated broker capabilities and native CLI capabilities succeeded after the documented bootstrap; gh auth status succeeded. Read docs/runbooks/workstream-kickstart.md. Hydrate only the broker pair from the user-owned mode-0600 ~/.limen.env through its documented path; never print credentials, copy another lane's credential, create a test-adapter keeper or rewrite policy/tasks.yaml to manufacture admission. Authentication is not executor authority, Git push proof or object custody.

Latest durable checkpoint: https://github.com/4444J99/limen/issues/2739#issuecomment-5920108825
Prompt correction: https://github.com/4444J99/limen/pull/2782#issuecomment-5920116413
Existing evidence PR: https://github.com/4444J99/limen/pull/2781
Existing prompt PR: https://github.com/4444J99/limen/pull/2782

One recovery writer: Agy. OpenCode is a read-only correction/review lane returning patches as text. Obtain broker reservations before separate execution capacity. At most four active sessions, two autonomous implementation tasks and one heavy workload. Preserve protected human sessions; do not adopt, kill, signal or retune them. No new below-admission worktree. Preserve unrelated dirty work, private originals, snapshots and native runtime consumers.

All Git reads: GIT_OPTIONAL_LOCKS=0, git -c core.fsmonitor=false, finite deadlines, actual subprocess exit codes. No force-push, reset, rebase to erase history, blanket ignored-file cleanup, reflog expiry, immediate object pruning, remote-branch deletion or clone relocation. Do not invoke clone maintenance, clone-reaper dry-run or ordinary branch-reaper dry-run as read-only inventory. Missing objects, permission errors and unknown ownership remain retaining states. Keep private inventories/content out of public artifacts.

