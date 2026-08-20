# Prima Materia autonomous continuation v2

Status: successor plan for the session boundary after PR #1606 hardening.
Supersedes: the execution shape, but not the evidence or phase ordering, in
`2026-07-28-prima-materia-next-alpha-omega.md`.
Delivery owner: PR #1606 until its merge receipt exists.
Campaign owner: this versioned plan and the current continuation capsule.

## Goal

Reach the Prima Materia fixed point without blurring session, worktree, owner,
or evidence boundaries:

1. make PR #1606 an exact-head green, reviewable admission gate;
2. admit it through the owner-controlled merge queue and install the exact
   merged SHA only through the retained runtime gate;
3. execute restore-proven custody before any evacuation or reclaim;
4. converge two complete λ audits and, after the protected career owner closes
   its lane, two complete Ω audits;
5. keep working autonomously across clean successor sessions until the live
   predicates pass or the only remaining atoms are recorded owner gates.

The goal is executable. Narrative progress, a pushed branch, a partial census,
or an unavailable probe is never a terminal result.

## Immediate successor: finish α

The operator's closeout correction is binding: a day of safer machinery
without a merged or otherwise terminal delivery receipt is not a successful
day-level outcome. The successor therefore has one active delivery outcome:
turn PR #1606 into an exact-head green, non-draft PR owned by the merge queue.
It must not broaden the architecture, regenerate estate-wide evidence, begin
β, or start another improvement lane while that outcome remains reachable.

Read remote truth before local state:

```bash
gh pr view 1606 --repo organvm/limen \
  --json state,isDraft,headRefOid,mergeable,mergeStateStatus,statusCheckRollup,url
git ls-remote origin refs/heads/main \
  refs/heads/work/prima-materia-alpha-omega-20260728
domus-limen-runtime status
```

Then derive one action:

- If an exact-head required check is still running, use one bounded
  `scripts/await-pr.sh 1606 --repo organvm/limen` waiter. Do not hand-roll or
  re-arm polling.
- If an exact-head required check failed, inspect only that failure, make the
  smallest sound repair in the PR #1606 worktree, run only implicated
  verification, and push one new head.
- If `python` and `pr-gate` are green on the exact draft head, publish the PR
  ready. Do not merge it. Anthony owns merge-queue admission.
- If the PR merged, validate the synthetic `merge_group` receipt and exact
  remote-main SHA. Runtime installation remains a retained owner gate; do not
  manufacture authority from the merge.

Within one bounded 90-minute delivery window, the successor must produce one
of two durable outcomes:

- PR #1606 is exact-head green and published ready; or
- PR #1606 records the exact failed external predicate, its owner, and the one
  next command that clears it, after which the session rotates.

Another plan, audit, or generalized framework is not a substitute for either
outcome.

No β–Ω mutation starts while α is unmerged or uninstalled. Reversible design,
tests, and read-only truth collection may continue only when they do not
consume an unleased broker packet or touch the protected career lane.

## Better autonomous control loop

At every packet and session boundary:

1. Re-read this goal, the capsule contract, exact remote head/checks, broker
   capabilities, remaining runway, host pressure, mounted device identities,
   protected registrations, and current custody receipts.
2. Reuse unchanged passing receipts. Never rerun a green predicate merely for
   reassurance.
3. Select the highest dependency-unblocking reversible leaf that has an owner,
   finite timeout, bounded output, resource claim, executable predicate, and
   durable receipt target.
4. Acquire a scoped writer lease only for its linked worktree. Run no more than
   three local threads and at most one heavy local surface. Serialize every
   destructive batch.
5. Commit only owned paths, push the exact head, and verify remote reachability.
6. Update the owner receipt with the actual predicate and cost. Never leave an
   open atom only in chat, a local file, or process memory.
7. Re-evaluate the phase gate from live receipts. Advance only when the
   preceding gate is executable and true.

If the authenticated conduct broker is unavailable, attempt its documented
environment-owned bootstrap once without exposing credentials. Existing
authorized direct-session work may reach a safe boundary; new task claims,
children, β–Ω packets, and lifecycle transitions remain fail closed.

## Clean session rotation

Session rotation is make-before-break and never shares a mutation surface:

1. The outgoing session reaches a clean exact head and pushes it.
2. It writes a versioned relay in the owning continuation directory. Every
   residual atom is already recorded in its own owner.
3. It creates the successor with `limen workstream` /
   `scripts/start-worktree-session.sh` from that exact remote head, using a new
   `-sN` slug and a finite runway. The launcher—not prose—validates the capsule.
4. The successor capsule is committed and pushed before its provider starts.
5. The successor uses a different linked worktree. Until it owns that
   worktree's writer lease, it is read-only.
6. Only after the successor's provider/session receipt is remotely durable
   does the outgoing session release its lease and emit its single terminal
   closeout line.

The new session re-derives reality; it does not inherit an asserted verdict.
If a context boundary arrives again, it repeats this protocol and emits the
next capsule before its current finite runway expires. It never resets an
admitted capsule deadline or starts two writers in one worktree.

## Phase gates

### α — admission

- Exact PR head has green `python` and `pr-gate`.
- PR is ready, then owner-admitted through the merge queue.
- Synthetic `merge_group` passes.
- Exact merged SHA is installed and attested.
- Direct successor is registered `human_protected`.

### β — executable custody

- Streaming encrypted put/restore is bounded, resumable, authenticated, and
  has no plaintext staging.
- Source identity and drift are checked across both passes.
- Archive4T and T7Recovery are proven to have different physical parents for
  every batch.
- Each encrypted copy restores independently.
- Repository capture restores refs, index, dirty tracked and untracked bytes,
  modes, symlinks, metadata, and required auxiliary objects.
- Concrete resource claims cover disk expansion, rollback, RAM, file count,
  network, and wall time.

### γ and δ — evacuation

- Freeze fresh repository and storage denominators.
- One broker-leased, exact-plan packet owns each bounded mutation.
- Restore proof precedes reclaim, eviction, deletion, or deduplication.
- Recheck path/device identity, active CWDs, protection, authority, custody,
  resources, and plan digest immediately before each serialized action.
- The reclaimer finishes at integer zero safe candidates; `null`, timeout, or a
  disappearing root remains failure.

### ε–η — programmable matter

- Independent enumeration keeps unknown and unavailable sources visible.
- Transform and external-action receipts are emitted by manifest-driven
  runners.
- Exact, semantic, and observable-only replay classes preserve their distinct
  truth conditions.
- Empty-scratch hydrate, replay, compose, and dematerialize predicates execute
  against only the selected graph.

### λ and Ω

- Both audits independently enumerate and validate the same frozen wave.
- All 13 λ rungs are fresh, complete, dependency-valid, and true.
- Normalized predicate-bearing state digests match.
- Only the career owner publishes its terminal owner receipt.
- After registry retirement of that blocker, two further complete equal audits
  admit Ω with zero protected blockers.

## Current evidence to carry, not reinterpret

- Delivery: <https://github.com/organvm/limen/pull/1606>
- Redacted live evidence:
  `docs/continuations/prima-materia-alpha-omega-20260728/`
- Current incomplete audit facts: 84 repository roots, 18 storage roots, 113
  independently matched source instances, 13/13 λ predicates false, incomplete
  reclaim census, stale Archive4T identity, and the career lane as the sole
  protected Ω blocker.
- Protection authority:
  `institutio/governance/reconciliation-protected-exclusions.json`

No reclaim, eviction, private-data movement, dematerialization, merge,
credential action, paid spend, public send, or runtime/host mutation is implied
by this plan.

## Terminal predicate

The campaign is terminal only when:

```text
fixed_point.complete == true
fixed_point.unchanged == true
fixed_point.lambda_passed == true
fixed_point.omega_admitted == true
protected_omega_blockers == []
```

and every discovered leaf has a merged receipt, open owner PR, pushed owner
plan/task, custody receipt with next owner/action, or precise external blocker.
Re-running the terminal predicate must produce no repository change.
