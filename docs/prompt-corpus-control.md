# Prompt Corpus Control Plane

The full prompt corpus is durable operating input. Its smallest accountable unit is an individual
ask, correction, constraint, acceptance criterion, or human gate—not a session, worktree, batch,
task, or pull request.

## Two concurrent loops

The corpus loop and execution loop run together:

1. Incremental ingestion preserves prompt occurrences privately and atomizes every non-excluded
   occurrence.
2. The atom projection recomputes lineage, recurrence, dependencies, priority dimensions, and
   evidence dispositions.
3. Existing authorized work continues within its resource and ownership gates.
4. New execution receipts flow back into atom outcomes. The next ranking is therefore based on
   current proof instead of chat recency or whichever code lane is easiest to see.

This is not a choice between auditing the whole and doing work. The corpus is the control plane that
keeps all work ordered while lanes execute.

## Dynamic atomization and priority

`scripts/prompt-atom-ledger.py` accepts provider-neutral normalized events. A reachable classifier may
supply atom candidates, lineage edges, dependencies, and numeric dimension overrides; no provider,
model ID, topic catalog, or fixed fallback ladder appears in the contract. When no classifier is
reachable, structural segmentation guarantees that every actionable occurrence still has at least
one atom. Uncertain provenance remains explicit rather than being silently counted as operator input.

Set `LIMEN_PROMPT_CLASSIFIER_CMD` to an opaque executable command when semantic enrichment is
available. The command receives JSONL on stdin with an occurrence ID and exact positional source
segments, and returns one JSONL row per occurrence. Limen invokes it without a shell, bounds its
runtime, rejects missing/extra occurrence IDs, and accepts only candidates grounded in those exact
segments. Canonical atom intent is reconstructed from the covered source spans; a classifier label is
retained only as a hash and cannot replace source text. Positional adjacency is a review hint, not an
authoritative correction edge—retiring an older intent requires grounded semantic lineage evidence.
A missing, malformed, or timed-out classifier leaves the structural atoms intact. Use
`--reclassify` to enrich a runtime-policy-bounded set of existing occurrences; revisions append to the
private journal and cannot orphan assessed atoms.

Priority is recomputed from the runtime policy in `docs/prompt-corpus-policy.json`. The policy weights
operator emphasis, systemic leverage, magnitude, recurrence, dependency impact, preservation risk,
recency, and cost of delay. Changing that data changes ranking without a code or model-catalog edit.

## Native source decisions

Every discovered native unit is decided by the versioned contract in
`cli/src/limen/prompt_sources.py`. A unit is either parsed by a named adapter, excluded by a narrow
structural non-prompt rule, or left as an explicit owner-routed adapter gap. Record schemas,
authority overrides, adapters, and exclusions are all part of the contract digest. Unknown schemas
and near-miss shapes remain gaps; they never inherit an exclusion or advance the cursor merely
because their filename extension resembles a known artifact.

The exclusion rules cover Claude's versioned file snapshots, generated plans, provider memory
artifacts, tool-result externalizations, workflow scripts, empty task locks, and bounded numeric task
watermarks. A root-level project memory file is excluded as a mirror only when it is byte-equal to
its canonical `memory/<same-basename>` sibling; a missing or differing sibling leaves an explicit
gap. Path role is evaluated before extension or cached parser state, so a JSON object under
`tool-results/` cannot impersonate a user turn.

Exact Claude remote-agent metadata is not excluded. The named remote-task adapter preserves its
`command` field as a delegated task frame with derived authority. Likewise, every Claude project
record under a `subagents` or `workflows` path is forced to delegated/derived authority regardless
of its `isSidechain` field, so path provenance cannot be promoted by record-local flags. Named
metadata adapters preserve subagent descriptions plus workflow arguments, phase titles/details, and
stored prompt previews as exact derived source segments; result previews, logs, and tool summaries
remain non-prompt metadata.

Only an exact depth-two Claude project session JSONL is eligible for operator authority. Generated
JSONL subtrees are derived when their path proves a subagent/workflow role and otherwise remain
unknown; a plausible `user` row cannot promote an arbitrary nested file. Recognized assistant
tool-use prompt fields (including agent/workflow delegations, scheduled prompts, task descriptions,
inter-agent messages, and future `instructions` fields) are preserved as exact derived segments.
Hook-injected additional context is also preserved with derived authority. Unknown nested prompt
carriers in an otherwise recognized assistant, attachment, or Codex user wrapper remain explicit
gaps rather than allowing the containing file to advance. `queue-operation`,
`last-prompt`, queued-command attachment text, and `goal_status.condition` are resolved within the
same session and file: an exact hash match to a primary operator row is a transport echo, while
unmatched stored text remains an explicit unknown-authority atom instead of disappearing or becoming
operator truth.

Claude `isMeta`, `isCompactSummary`, and `sourceToolAssistantUUID` user rows are synthetic context,
not operator turns: they remain derived, with compact summaries classified as continuation context.
Global assistant-tool fields such as `prompt` and `instructions` apply in addition to each named
tool's fields. Exact user content-block keysets prevent a `tool_result` sibling field from hiding a
new prompt carrier. Gemini chat rows, Codex/Agy history rows, OpenCode user parts, and Agy prompt-step
records likewise use explicit schemas; a future user-bearing shape becomes an owner-routed gap rather
than a silently converged zero-event unit.

Each excluded or adapted unit receives a private receipt bound to its file signature, rule or
adapter ID, contract version, contract digest, and any related signatures. Classifying a new unit or
refreshing a stale receipt consumes one bounded work unit; only an exact current receipt is free on
the next scan. Regular-file signatures bind size, modification time, change time, inode, and device,
so a same-length rewrite with restored modification time still invalidates cached authority. A
declared source root may itself resolve through a canonical in-home symlink, but a symlink beneath
that root cannot escape it. Once an all-history target exists, every incremental pass rediscovers the
complete unit manifest while unchanged units remain zero-work cache hits. OpenCode virtual sessions
add a per-session content digest and bind both the SQLite database and WAL generation; the scanner
uses one read transaction and refuses to advance any session if that generation changes mid-scan.
The cursor and public
redacted scope expose aggregate exclusion and adapter counts
plus receipt-set digests, not private paths or bodies. Exact `all` additionally binds the complete
source-unit key set, requires per-family discovered/converged/adapted/excluded counts to reconcile
with private unit custody, and requires canonical empty unsupported/unresolved digests. Missing
unresolved units remain durable tombstones and owner-routed gaps across unchanged scans until they
reappear with parsed or excluded resolution proof. Cursor proposals require an exact revision and
digest pair; stale proposals are rejected without changing private cursor bytes.
An exact `all` result is not self-certifying: the scanner issues an in-process attestation which the
writer seals as a private, read-only, SHA-bound `limen.prompt-source-scan.v1` receipt. That receipt
binds the running scanner code, adapter contract, CAS base, discovery specification, source manifest,
container generation, and parsed/excluded/adapted custody. The checker re-discovers those roots and
re-stats strong file and SQLite/WAL identities; a new, deleted, replaced, or racing unit makes exact
authority stale before priority queues can consume it. Full-manifest exact-CAS writes replace prior
cache custody, so legitimate session deletion converges without retaining phantom keys. A live
attested scan may replace an older receipt after scanner or contract upgrades, but an invented or
mutated proposal cannot seed exact authority.

OpenCode uses the sealed database/WAL generation as a container boundary and exact per-session
content digests as its change index. When an unrelated session changes, unchanged sessions refresh
their generation-bound signature without consuming parse work units; only content-changed sessions
enter the bounded fair-work queue. The empty-database generation is sealed too, so a first session
cannot arrive between discovery and commit without invalidating the result.
When a new contract changes authority or excludes a formerly parsed unit, the append-only journal
records a classification revision: history remains, current atoms are corrected, and any assessed
atom that would be orphaned blocks the migration.

Media-bearing user units remain explicit owner-routed gaps until a content adapter can preserve both
the media and its lineage. This covers Claude `image`/`document` content blocks and Codex
`input_image` blocks, including mixed text-plus-media turns; the scanner does not extract the text and
silently discard the attachment. Codex `pasted-text-<n>.txt` attachments are likewise gaps. A detached
file alone cannot prove whether its body is an operator instruction, quoted third-party material, or
tool input, so it must not become prompt truth until an adapter binds it to the canonical parent event
and derives authority from that lineage.

## Evidence dispositions

Atom dispositions are analytic and remain separate from Limen task states:

- `unassessed`: preserved but not yet compared with owner evidence;
- `not_done`: assessed, with no qualifying result;
- `partial`: a proved result exists and residual atom IDs are named;
- `done`: a durable reference and passing predicate prove the atom;
- `blocked`: owner, failed gate, and next command are recorded;
- `superseded`: a present successor atom and passing supersession proof are recorded.

Similarity, related files, git-history proximity, an open PR, and `owner-recorded` custody are candidate
evidence only. They cannot produce `done`.

GitHub closure evidence must be merged or default-branch reachable and bound to an existing,
SHA-256-matched GitHub verification receipt. Local task or predicate evidence must likewise resolve to
an existing repository receipt with the recorded content hash. Outcome revisions name the digest of
the immediately preceding row, advance `assessed_at`, and cannot roll a terminal `done` or
`superseded` result backward.

## Privacy and concurrency

Raw bodies, source paths, session references, full hashes, and journals live under the ignored
`.limen-private/session-corpus/prompt-atoms/` root. Exact bodies are gzip-compressed,
content-addressed private objects; each append-only event row contains its occurrence and all of its
atoms as one transaction. The compact private checkpoint does not duplicate the raw corpus. The
tracked JSON and Markdown projections contain only opaque IDs, aggregate counts, numeric dimensions,
dispositions, owner routes, and canonical receipt references.

`docs/prompt-authority-seal.json` is the bounded publication receipt for source-corpus authority. Its
schema is `limen.prompt-authority-seal.v1`; it contains only fixed numeric aggregates, safe family and
reason labels, and SHA-256 bindings to the semantic projection, cursor, manifests, adapter contract,
and sealed scan. It never contains prompt bodies, source locators, private paths, session identifiers,
or per-atom rows, and the writer refuses any receipt over 64 KiB. A zero-change rerun must leave its
bytes and modification time unchanged.

An exclusive writer lock serializes updates; journal appends are flushed before atomic projection
replacement, and the compact checkpoint is written last. Stable occurrence and atom IDs plus a
monotonic cursor merge make concurrent or repeated drains idempotent. The cursor digest is embedded
in the projection, so a cursor advance without a matching projection fails closed. Verification
rebuilds the public JSON and Markdown byte-for-byte from the private journals and detects missing,
malformed, or altered raw objects.

The priority map additionally binds the projection to the currently loaded runtime-policy digest.
A projection and private receipt that agree with each other but carry stale weights, authority bands,
thresholds, or owner routes cannot regain authority when live journals are unavailable. Grounded
correction/refinement edges retire an older intent only when the successor has provably later source
chronology; missing, equal-order, or future-predecessor edges remain validation failures.

## Commands

The heartbeat sensor is intentionally dark (`LIMEN_PROMPT_ATOM_CONTROL=0`) and is not an Omega rung.
Activation requires a measured, resource-bounded canary that proves both a healthy first pass and a
cheap idempotent second pass. The canary requires fresh canonical outputs, spends one work unit on
each of the Codex, Claude, Gemini, OpenCode, and Agy fixture families, and records run-local work-unit
use so a reused cursor cannot impersonate fresh proof. Its default mode also refuses implementation
files that differ from Git HEAD and records both the exact head and a combined implementation digest
in the private receipt. Until that receipt exists, use the commands below manually; do not turn the
gate on merely because the implementation or a narrow unit test is green.

```bash
# Incremental scan; an existing all-history target rechecks its complete manifest.
python3 scripts/prompt-atom-ledger.py --scan --write

# Bounded all-history drain. Continue until pending/errors are zero; explicit gaps remain owner-routed.
python3 scripts/prompt-atom-ledger.py --scan --all --write

# Verify journals, cursor, evidence rules, redaction projection, semantic digest, and full scope.
python3 scripts/prompt-atom-ledger.py --check --require-scope all

# Build authority queues only after the checker proves exact all/all (never from a blocked partial scope).
python3 scripts/prompt-priority-map.py --write

# Reuse exact existing owners across tasks, open PRs, and retained worktrees; never mint duplicates.
python3 scripts/prompt-estate-reconcile.py --check

# Reclassify a bounded existing slice through the configured opaque command.
LIMEN_PROMPT_CLASSIFIER_CMD='<opaque command>' \
  python3 scripts/prompt-atom-ledger.py --reclassify --write

# Run the isolated activation canary. Outputs and its redacted receipt must stay private.
python3 scripts/prompt-atom-canary.py --sandbox-root <isolated-canary-root> \
  --home <isolated-source-home> \
  --private-root <private-output> --public-snapshot <private-redacted-json> \
  --public-markdown <private-redacted-markdown> --public-seal <private-redacted-seal> \
  --receipt <private-receipt>
```

Board work derived from unresolved atoms must still enter through TABVLARIVS. The atom ledger never
writes `tasks.yaml` and never translates its dispositions into dispatch statuses implicitly.
