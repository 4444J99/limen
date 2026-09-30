# Session closeout evidence

A session release ends ephemeral responsibility. It does not complete every task,
certify estate health, retire a checkout, or permit deletion. A finished session has
no successor requirement. Reuse an existing owner for a handoff; retain its real task
state and acceptance predicate. No new task registry is introduced.

## Entry point

From a verified Limen source or immutable protocol installation, run:

```sh
bash scripts/no-tasks-on-me.sh --session-id ID --worktree PATH --receipt docs/continuations/OWNER/session-closeout.json --json
```

All session modes are read-only. Exit 0 proves session release; 1 means measured
owned obligations remain; 2 means evidence is unavailable or invalid. Legacy callers
without arguments retain estate diagnostics. `closeout-fast.sh` forwards explicit
session arguments to this same checker. Historical capsule `launch.sh --check` also
requires explicit identity and evidence; its historical no-flag validator remains separate.

Use the authenticated conduct environment (the canonical bootstrap is
`workstream_hydrate_conduct_environment` in `scripts/lib/workstream-capsule.sh`). The
checker reads the existing session audit and registration. A truncated audit fails.
An absent registration requires `--native-transcript PATH` witnessing the exact native
Codex ID, plus the same published owner receipt; absence alone never means no obligations.
Do not publish raw transcripts or private artifact paths in the receipt.

## Existing owner receipt

Store `limen.session_closeout.v1` in the existing continuation's `session-closeout.json`.
The record must be committed at the inspected HEAD and that HEAD must be proven on
its live remote `publication_branch`. A detached checkout is acceptable with this proof.
For a protected historical checkout, place the receipt in an isolated owner checkout
of the same repository and pass its absolute path. Bind `subject_head` and
`subject_publication_branch` explicitly. The subject is never edited to add evidence.
Never use a cached tracking ref as evidence of publication.

Required fields:

- `schema`, `session_id`, `repository` (owner/repo), `worktree_name` (checkout basename),
  `base_head` (session start revision), `publication_branch`, and exact `owner_url` (GitHub issue or PR).
- `disposition`: `complete`, `handoff`, or `read_only`. These are receipt dispositions,
  not TABVLARIVS task states. A handoff requires an open owner.
- `owned_paths`: explicit repository-relative implementation files or directory prefixes.
  Include every changed implementation path; the receipt and evidence files are separate.
- `retained_work`: explicit objects with `paths` and an open `owner_url`, established
  from session/broker/corpus evidence before publication. Last commit author is not
  the current editor. A path absent from both sets is unknown, not implicitly a sibling's.
- `verification`: command receipts with `head`, `exit_code`, committed `evidence` path,
  and that evidence's `sha256`. Include implicated tests, required credential ownership,
  and other applicable gates. A failed task-completion check may carry
  `purpose: completion` and the same open `owner_url` only for `handoff`; its failure
  remains recorded and never proves task completion. Release/custody failures still
  block release. The checker reuses these immutable results and rejects
  subsequent changes to owned implementation. It never reruns a green full suite.
- `custody`: `verified`, committed redacted `evidence` path and `sha256`. This must cite
  actual custody checks (or verified absence of private/local-only payload). A missing
  independent restore copy cannot be papered over with a publication receipt.

The producing agent is responsible for truthful, complete scope and evidence; publishing
an empty path list cannot erase implementation. Recover legacy ownership from the exact
session and durable receipts; never guess from a nearby worktree or newest transcript.

Checks require no retained active lease/nonterminal run and no surviving or unattributed
process in the subject checkout. The current checker and its process ancestors are excluded;
other sessions are never signaled. An unavailable process census is unmeasured. Published
retained-work owners preserve concurrent edits without including their changing contents
in this session's fixed point. Unknown ownership must be reconciled in the existing owner.

## Installation and propagation

Domus resolves the verified immutable protocol bundle. Its installer isolates ambient
Git export attributes and validates policy payload digests before activation. The source
and installed checker implement the same stopping rule. Adapter skills point to the
canonical skill; instruction drift checks cover that skill and capsule doctrine.

The six-session September 30 reconciliation belongs to Limen #2763, with the existing
per-session owners retained. Domus #403 owns installed discovery. A receipt must separate
source/merge, installed adoption, scoped session release and genuine custody blockers.

## September 30 implementation receipt

Owner: [Limen #2763](https://github.com/4444J99/limen/issues/2763).
The accepted implementation removes mandatory successor work, separates release from
completion, preserves historical validators, makes observation read-only, and binds
installed policy discovery to exact source through Domus #403.

The live keeper audit of all six screenshot sessions found zero retained runs and
leases, complete retained-state coverage, and no current registration. Request history
and broker registration witness remain unmeasured. All six exact native transcript
metadata identities were independently verified. These observations do not release
any session by themselves. Preserve the native metadata and recover each
owner receipt before invoking the explicit checker. No protected checkout was changed.

| Screenshot session | Existing owner | Required reconciliation |
| --- | --- | --- |
| Plan verification and gap filling | #2739 / PR #2781 | Bind original scope and admission evidence |
| Verify and fill gaps | #2760 | Recover its own worktree scope; a sibling checkout is not evidence |
| Read closeout modules (bypass) | #2752 / PR #2758 | Preserve private payload; independent restore custody remains required |
| Read closeout modules (relay) | #2763 | Bind prior scoped checks and publication to native identity |
| Enable GitHub interaction in chats | Domus #403; Limen #2680 / #2764 | Install discovery fix; feature acceptance and private custody remain separate |
| Resolve Limen workspace drift | #2763 | Bind scoped checks; estate drift is a distinct claim |

## Implementation acceptance

The canonical session checker, adapters, installed protocol bundle and native
discovery fixes are implemented. Domus PR #405 merged as `64b4e4ef`; targeted
chezmoi adoption excludes scripts and preserves editable installations. Limen
PR #2785 owns source landing and adoption of its exact merged default-branch SHA.

CLI verification accounts for all 8,223 collected cases across bounded shards:
8,221 passed and two environment-dependent integration cases skipped. Unchanged
passing cases were retained; changed test files were rerun. The collection digest
and precise execution history are recorded in the implementation evidence below.
Five fixture repairs remove startup races, isolate healthy pressure input for the
shell-helper test, and clean up a lock-test child plus a registration monitor.
The final 31-case workstream shard passes the unchanged process-cleanup guard.
No production admission threshold or cleanup guard was weakened.

The API suite passes 52 tests; 37 focused closeout regressions, whole Python type
checking, pinned Ruff lint/format and instruction drift also pass. Domus runtime
tests pass 52 cases. Native Codex and OpenCode discovery each pass from home,
the Domus checkout and a temporary directory, with zero model turns.

The operator explicitly authorized a process-local pressure exception for this
verification. Only swap/disk pressure reasons were eligible; disk pressure was
waived in the observed runs. The machine-wide heavy lease, verifier lock and
bounded four-worker execution remained enforced. No peer was stopped, permanent
policy changed, shared checkout migrated, or successor capsule launched.

Authenticated metadata reconciled all 54 historical public candidates. The existing
withdrawal registry binds 27 positively restricted rows by digest; 27 remaining
public immutable heads verified. The candidate denominator remains 62, readiness
scores remain zero, and no transfer becomes eligible. Private contents and new
private coordinates were not published. The new-delta scoped batch passed all
eight gates, including 57+16 readiness regressions and live public verification.

Durable predicate and custody evidence:
`docs/continuations/workspace-recovery-20260916/session-closeout-implementation-20260930.md`.
Its companion JSON is the exact-session receipt. Terminal use requires verified
source landing, adoption of that merged runtime, and a passing installed session
predicate. The six historical checkouts retain the owners above; this implementation
does not bulk-certify their completion or authorize their deletion.
