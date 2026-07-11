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

An exclusive writer lock serializes updates; journal appends are flushed before atomic projection
replacement, and the compact checkpoint is written last. Stable occurrence and atom IDs plus a
monotonic cursor merge make concurrent or repeated drains idempotent. The cursor digest is embedded
in the projection, so a cursor advance without a matching projection fails closed. Verification
rebuilds the public JSON and Markdown byte-for-byte from the private journals and detects missing,
malformed, or altered raw objects.

## Commands

The heartbeat sensor is intentionally dark (`LIMEN_PROMPT_ATOM_CONTROL=0`) and is not an Omega rung.
Activation requires a measured, resource-bounded canary that proves both a healthy first pass and a
cheap idempotent second pass. Until that receipt exists, use the commands below manually; do not turn
the gate on merely because the implementation or a narrow unit test is green.

```bash
# Lightweight incremental scan of changed recent sources.
python3 scripts/prompt-atom-ledger.py --scan --write

# One bounded all-history drain; repeat until it reports exact all/all.
python3 scripts/prompt-atom-ledger.py --scan --all --write

# Verify journals, cursor, evidence rules, redaction projection, semantic digest, and full scope.
python3 scripts/prompt-atom-ledger.py --check --require-scope all

# Only after that exact all/all check: build the atom authority queues.
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
  --public-markdown <private-redacted-markdown> --receipt <private-receipt>
```

Board work derived from unresolved atoms must still enter through TABVLARIVS. The atom ledger never
writes `tasks.yaml` and never translates its dispositions into dispatch statuses implicitly.
