# Reacceptance v2 Predicates

## Historical rows

A historical row may become terminal only when it references at least one
reconciled attempt and an accepted or reverted external remedy through
`coverage`. The row must also reconcile its redacted source references,
registry-owned outputs, side effects with replay denied, owner surfaces,
executable predicate, and durable adjudication.

- `accepted` requires `repaired` coverage from an accepted external remedy.
- `superseded` requires `superseded` or evidence-backed `obsolete` coverage.
- `reverted` requires `reverted` coverage and a verified safe reversal.
- Otherwise the only honest state is `repair_required`.

## Attempts and remedies

Spend is stored once per unique owner-native trajectory attempt. Duplicate or
orphan trajectory identities and reused source, trajectory, spend,
side-effect, execution, or value receipts are invalid. Every
attempt reconciles source lineage through a corpus receipt, executor/session
identity, finite numeric token and cost spend, at least one owner output, a
no-replay effect inventory, an executable predicate, an owner surface, a
derived value classification, and durable receipts. Motion-only,
unverifiable, and failed attempts receive zero credit.
When a receipt carries both a URL and an owner-native digest, both identities
are authoritative: neither may be reused behind a different value of the
other. The same independence rule applies to private custody copies and
fixed-point refresh receipts.

Every observed effect is also crosswalked back to its frozen historical row.
Its terminal outcome must come from the row/effect owner frozen in
`scope.json`, and that owner must sign the exact row IDs, effect, outcome,
predicate, and receipt identity with a scope-pinned key. The session-value
owner cannot impersonate mail, storage, media, backup, privacy, prompt-corpus,
or worktree-custody owners.

Remedies live outside the 105-row denominator and may cover many rows and
findings. Every accepted remedy kind, including owner receipts, requires:

1. a full 40-character head;
2. complete successful exact-head CI;
3. zero unresolved current review conversations;
4. a distinct executor/reviewer approval in the complete review-gate receipt;
5. a deployed-entrypoint predicate and durable receipt no older than 24
   hours; and
6. a durable terminal adjudication; and
7. a current merged remote snapshot whose successful
   `limen.pr_review_gate.v1` CheckRun is App-bound to the configured dedicated
   publisher.

The review receipt may predate merge, but its exact head may not drift.
The configured App comes from frozen scope, never from the remedy itself.
Stored CI classifications must agree with their underlying CheckRun or status
state. Signed fallback requires distinct execution and review fingerprints.
`owner_receipt` cannot cover historical row or finding repair debt.

## Findings

Each of the frozen 208 discussion URLs remains in `findings`. `repaired`,
`obsolete`, or `reverted` is valid only after the original thread is resolved
and a coverage entry with the matching disposition binds the row, finding,
remedy, exact head, and evidence. An inaccurate reviewer claim is never
implemented merely to clear a count.

## Derived completion gates

The five gates are computed from owner evidence:

1. all five baseline-open PR rows are terminal;
2. every unique attempt has owner-native value reconciliation; non-value
   classes are derived and carry zero credit rather than disappearing;
3. immutable event-offset cutoff evidence is identical to the frozen scope,
   owner-bound, and no campaign custody is stale;
4. the exact frozen privacy denominator has clean current trees, two copies
   with equal content digests, distinct custody locations, and distinct owner
   receipts, plus completed history action wherever the frozen effects include
   public history or publicly reachable private material; and
5. a durable continuation capsule exists, two ordered complete refreshes have
   the same normalized evidence digest, and two distinct fresh owner receipts
   attest those exact refreshes. Both refresh events themselves must be fresh,
   and their exact timestamps are covered by the continuation owner's
   signature rather than normalized away.

`summary.release_ready` is derived. It is true only when all 105 rows and all
208 findings are terminal, every registered remedy is terminal, review debt is
zero, and all five gates pass. Each owner adapter receipt binds the precise
registry/denominator digest it adjudicates through a scope-pinned signature.
The privacy adapter additionally binds the frozen row/effect denominator and
the private owner's content-manifest digest; two arbitrary equal copy digests
cannot manufacture green. `--check` proves structural validity only;
`--require-release-ready` additionally rejects stale snapshots and compares
the candidate against fresh GitHub owner reads.
