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

GitHub publication is measured through an authenticated, bounded exact-ref API read,
including private repositories and transferred aliases. The returned ref, commit type,
SHA and any required local ancestry are checked; authentication failure is unmeasured,
not a fallback to SSH. This avoids creating an ambient `ControlPersist` SSH master
during a supposedly read-only recheck. Non-GitHub/local Git publication support remains
available through its live remote-ref check; no transport or process is blanket-exempted.

## Installation and propagation

### Explicit multi-repository sessions

Use `limen.session_closeout.v2` when the native caller is a non-Git container or the
session owns several repositories. Preserve `--worktree` as the native/broker anchor
and pass repeatable `--scope-root ID=PATH` arguments using canonical absolute paths.
The mappings must match `scope_roots` exactly. No repositories are inferred by scanning
the container. V1 behavior and receipt shape remain unchanged.

V2 carries `session_root_path_sha256` (SHA-256 of the canonical path's filesystem
bytes), `receipt_root_id`, `session_id`, `owner_url`, and `disposition`. Each scope has
an opaque `id`, matching `path_sha256`, and `kind: git`, `retained`, or explicitly
evidence-backed `retired` (see below). A Git scope binds
`repository`, numeric GitHub `repository_id`, `base_head`, `publication_branch`,
`owned_paths`, and `retained_work`; all except the receipt root also bind `subject_head`.
The receipt root derives its live head, avoiding a self-referential hash. Repository
aliases are validated against GitHub's stable ID and canonical name. For non-GitHub
remotes, use the exact origin URL without its `.git` suffix as `repository`.

Retained roots require an open `owner_url` and force handoff rather than task completion.
Nested roots require `nested_in` naming the nearest declared parent and an explicit
parent `retained_work` prefix covering the child. Git scopes must be exact Git top levels.
Duplicate canonical roots and symlink aliases are rejected. Absolute private paths stay
only in local arguments; committed receipts contain opaque IDs and hashes.

Verification uses the v1 fields plus `root_id`. Evidence is committed in the receipt
repository and each Git scope independently checks publication, ancestry, dirty paths,
committed changes, and verification freshness. Failed `purpose: completion` checks may
be handed off to their exact open owner; release failures always block. `custody.root_ids`
must equal the complete scope set, with committed hash-bound custody evidence. Optional
`external_effects` entries carry `id`, `kind`, `verified`, `evidence`, and `sha256`;
unverified effects need an open owner under handoff. The producer must enumerate all
actual effects and preserve their readbacks without secret values.

For legacy native sessions, transcript metadata must bind both ID and `cwd` to the
anchor. A broker's current execution checkout may differ from that start directory
only when the receipt explicitly names `broker_scope_root_id`: a declared canonical
scope matching the same registered session's live worktree. This requires the exact
native transcript and a present broker registration; all declared scopes still undergo
their normal ownership, publication, custody and process checks. Without that explicit
witness, a transcript/broker mismatch remains unmeasured. No child checkout replaces
the native `--worktree` anchor. One
process snapshot covers exact-anchor processes, recursive declared roots, and exact
native lineage anywhere. Undeclared siblings are excluded; unknown anchor processes
still block. Shared services and foreign sessions require positive identity evidence.
V2 returns per-root `heads` and root-qualified findings without private paths.

### Already-retired original roots

A completed historical retirement does not make its original root disappear from
session scope. Keep its ID and original canonical path in `--scope-root`, and use
`kind: retired` with the original `path_sha256`. No dummy checkout is created.
Retired identities remain in custody and process coverage; the process observer
still receives their original paths. A missing root without this evidence is
unmeasured, never silently omitted. Reappeared paths and symlink aliases fail.
The receipt owner, native caller and broker execution checkout cannot be retired
through this contract. Recognition grants no new deletion authority.

`scope_retirement` is a committed `evidence`/`sha256` packet in the receipt owner.
Its `limen.scope_retirement.v1` record binds `session_id`, the complete original
`scope_paths` ID-to-path-hash map, `custody_sha256`, `retired_root_ids`, and
`executions` packets. Custody must be a fully validated portable v2 graph over
every original root, including the retired ones: exact authenticated readback,
independent full native restorations and retained custody remain mandatory.
Neither a generic verified flag nor a historical `retired_ids` list suffices.
Portable provider replicas are supported; an external drive is not required by
this acceptance path.

Each `limen.scope_retirement_execution.v1` observation repeats the exact session,
scope and custody bindings, records its non-overlapping `retired_root_ids`, aware
`executed_at`, integer `exit_code: 0`, `absence_measured: true`, and a committed
`dependencies` packet. Execution must follow both full restorations. Its
`limen.scope_retirement_dependencies.v1` observation repeats the bindings, carries
`observed_at` between restoration and execution, complete sorted `scope_root_ids`,
the execution's sorted `retired_root_ids`, `observation_complete: true`, explicit
`git_store_consumers` edges (`store_root_id`, `consumer_root_id`) and an
`external_consumers` list. A surviving Git-store consumer, external consumer or
incomplete census fails. Producers must measure the entire dependency scope,
including outside consumers; unknown coverage cannot be recorded as an empty list.
Original native link counts and group membership independently reject hardlinks
escaping the retired cut set. Lossy historical metadata is not upgraded by inference.

This consumer does not manufacture execution or dependency observations from old
summaries. Historical evidence needs a truthful producer/adapter with the original
observations and full custody graph; unavailable evidence remains unmeasured.
The read-only checker rechecks absence after process observation and preserves the
original denominator in its `scope_retirement` result. An unchanged successful
recheck creates no files, leases, worktrees, provider runs or new owners.

```sh
bash scripts/no-tasks-on-me.sh --session-id ID --worktree NATIVE_ROOT --receipt PRIVATE_RECEIPT --native-transcript TRANSCRIPT --scope-root owner=OWNER_ROOT --scope-root subject=SUBJECT_ROOT --json
```

Domus resolves the verified immutable protocol bundle. Its installer isolates ambient
Git export attributes and validates policy payload digests before activation. The source
and installed checker implement the same stopping rule. Adapter skills point to the
canonical skill; instruction drift checks cover that skill and capsule doctrine.

The six-session September 30 reconciliation belongs to Limen #2763, with the existing
per-session owners retained. Domus #403 owns installed discovery. A receipt must separate
source/merge, installed adoption, scoped session release and genuine custody blockers.

## Producer

`scripts/session-closeout-receipt.py` produces the `limen.session_closeout.v2` receipt the checker
above only judges (limen issue 2977). It imports the checker's own helpers and its real
`evaluate_scoped`, so the two cannot drift, and it derives every value from a named source. Run it
under an interpreter with `pydantic` and `PyYAML` (the cli venv). It never registers a session,
stages, commits, pushes, merges, creates a continuation owner or deletes anything.

Flow, each verb read-only except where it names the one file set it creates (create-only, mode 0644,
under the existing continuation directory):

1. `plan --manifest M` gathers git, `gh`, the broker audit and registration and the process census,
   and prints every gap. Candidate ownership paths appear only under "unattributed, NOT written".
2. `attest --manifest M --scope ID --label L --gate GATE` runs one registry-declared gate (or the
   verify-scoped wrapper) in the scope root, in its own process group with a deadline, a scrubbed
   environment and `check=False`, and records the real exit code, exact head and output digest. The
   registry is read from the scope's own git object database at the attested head (default
   `institutio/governance/gates.yaml`; `--gates-registry` takes only a repository-relative path committed at
   that head), never from an operator-supplied file. It refuses a dirty tree, a gate whose command text
   mutates git or the broker, a gate that changes HEAD, the tree or any ref while it runs, and any command
   that is not declared. `build` re-resolves every attestation the same way (gate id, command and definition
   digest at the attested head) and refuses one that does not match. Limits: the command scan is lexical, and a
   remote-only mutation or a registry the session itself committed is not detectable here; an attestation is
   unsigned, so a hand-written file that is consistent with a committed gate cannot be told from a real run.
3. `build --manifest M` re-derives everything, refuses on any gap, writes evidence then the receipt,
   runs the real checker as a labelled dry run (`non_evidence`: uncommitted bytes are overlaid and only
   the receipt root's publication is simulated) and removes the files it created if that finds anything.
   It prints the exact `git add -- <paths>` list; the operator stages and commits it and pushes through
   the normal PR rail.
4. `check --manifest M` runs the real checker in-process. `--expect-unpublished` is the dry run for the
   window between the receipt commit and its push (exit 3, never a pass); a branch never pushed makes
   `published()` raise, which the checker reports as exit 2, so the dry run names it
   `ref_absent_on_remote`. `--recheck-heads` reports which scope moved after the receipt bound its
   `subject_head`. Only a bare `check` after the push is evidence; run it twice for the fixed point.

What it derives: path hashes, `subject_head`, `repository` and numeric `repository_id`, the publication
branch (from `branch.<b>.remote/merge`, never the branch name), `base_head` (fork point of the GitHub
default branch, or an explicit revision that may not be later than it), `nested_in`, verification
`head`/`exit_code`/`sha256`, `custody.root_ids`, effect readbacks, and the disposition.

What it refuses, with an actionable `gap: <code>: <message>`: unknown ownership (`owned_paths` and
`retained_work` come only from the manifest, each retained owner must be a live-open foreign owner),
a missing or unverifiable `owner_url`, dirty or unattributed paths, an empty verification list, an
unpublished or absent remote ref, an empty attribution window (a fork point equal to HEAD), custody that
is not a scope-bound `limen.custody_receipt.v2` bundle or a provable absence (a sealed-custody tracked
receipt binds no session or scope), a reused effect file whose verdict its own readback does not support
or that was recorded for a different `expect`, a reused absence file that is not the live measurement,
effects without a non-empty `expect` or an explicit
`external_effects_enumerated` attestation, an active lease, a nonterminal run, `complete` when anything
is retained, unverified or failing, a symlink anywhere in the evidence path, and any committed byte that
matches a secret shape, an absolute private path, or a declared scope path.

`plan` also reports the census by category (no pids, no paths) and the exact broker anchor-binding
mismatch class. A session anchored at a shared directory such as HOME cannot reach a zero census while
other agents run, because every process whose cwd is exactly the anchor is counted: anchor the session
at a dedicated quiet directory. Residual risk: `path_sha256` and `session_root_path_sha256` of
well-known private paths are brute-forceable; the checker mandates them, so only opaque ids appear
anywhere else. Deliberately not done: `prune`, `--use-installed` (the checker module hash is reported
and compared with `--canonical-checker` instead), deriving the session start from broker run receipts,
candidate PR/ref discovery for effects, and retirement or lineage packets.

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

## Process ownership recovery

The process census reports checker, shared_service, foreign_session, owned_survivor,
unknown and unmeasured instances. Exact native transcript headers distinguish thread
identity from root-session membership. Native child jobs remain owned by their parent
session. Shared service authority requires the effective enabled configuration, policy
owner, exact canonical command, verified host identity and declared individual bootstrap
relationship. An app-server subtree is never an exemption. Unreadable identity, PID
reuse, missing native metadata and stale evidence fail closed. Reports omit raw argv
and environment; only allowlisted native identity keys are retained during observation.

Configured CUA helpers may declare their direct worker commands only when the live
parent is the exact configured helper. Kernel and trusted-worker scripts must have
their complete bytes embedded in that helper binary, use the helper's sibling Node
executable, and match their exact argument shape and observed working directory.
Captured script and helper digests are rechecked before issuing the contract. A
direct app-server worker must match an already registered native-host command.
These contracts still require the existing verified parent-service and host checks;
temporary paths, familiar filenames and app ancestry alone confer no authority.

Detached Serena tray managers require an explicit source-owned
`process_contract.detached_helper: serena-tray-manager` declaration. Candidate
contracts bind exact raw uv-environment commands, pinned vendor metadata and
module bytes, both native process identities, and a configured backend contract.
The backend must first be positively classified as shared under the same host
and configuration; a conflicting peer receipt cannot confer authority. The tray
also needs one PID-bound IPv4 loopback listener on port 24224, bounded typed health
without redirects or proxies, and unchanged native identity. Health alone,
matching Python binaries, or app ancestry never exempt a detached process.

A source-owned responsible host may separately declare a lifetime bridge. It requires
the fixed signed Domus host and designated-requirement receipt, the managed Codex
launcher route and file digests, and a finally verified code-mode peer under the
same native host/configuration. Two complete kernel FD censuses are bounded at
128 descriptors; truncation fails closed. Exactly one reciprocal FIFO reader/writer
pair must match handles, UID, device and inode. Native identity, command and pipe
descriptors are rechecked before granting the individual contract. An app name,
shared pipe alone, an unrelated peer, or native-session ownership never becomes
a blanket shared-service exemption.

Source-owned native-host helper declarations name one sibling executable and its
exact arguments. They bind both host and helper bytes plus policy provenance,
require a valid effective Codex configuration, and retain the assessor's exact
same-user native-host identity and direct-parent requirement. A sibling binary
without a declaration, a symlink helper, or an additional argument is not authority.

Domus provides `domus-process-ownership observe --worktree PATH --session-id ID`.
Observation does not write or signal. Explicit `adopt` records private atomic receipts
for verified existing shared services without restarting them. Native launches retain
stdio, lifetime descriptors, signals and exit status through the companion. Operational
receipts are revalidated against current PID start, command, host and configuration;
they confer no authority by themselves. A committed optional receipt sidecar is
`process_ownership: {evidence: RELATIVE_PATH, sha256: DIGEST}` with schema
`limen.process_ownership.v1` and a processes array. Stale claims are unmeasured.

Runtime acceptance remains separate from source publication and scoped release.
Limen #2763 owns reconciliation; Domus #397 and #403 own deployment and discovery.
