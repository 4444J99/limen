# Repository Stewardship Audit — 2026-09-10

## Scope and evidence

This audit covers `4444J99/limen` as observed on 2026-09-10. Remote GitHub state is authoritative; the local checkout is a read-only observation point. Queries covered open issues and pull requests, all remote branches, closed unmerged pull requests, workflow configuration, recent `main` runs, local worktrees, and the current branch graph. No issue, pull request, branch, workflow, or task projection was closed, deleted, force-pushed, or otherwise mutated.

| Surface | Count / result |
|---|---:|
| Open issues | 354 |
| Open pull requests | 11 |
| Remote branches | 46 |
| Closed, unmerged pull requests | 48 |
| Latest completed `main` CI | Success, run `34476328951`, head `49d90512` |
| Latest completed `main` deploy | Success, run `34488832128`, head `49d90512` |
| Local worktrees | 2; live `main` plus this isolated audit worktree |
| `BRANCHES.md` | Absent |

The open-issue count is intentionally not treated as a work count. Labels overlap: `program:production-systems` (87), `needs-human` (83), `lane:fleet` (77), `work-packet` (73), `lifecycle:delivery` (60), `bug` (16), `credential` (11), and `censor` (11) are classification signals, not independent queues.

## Default-branch health

At this audit's observation, `origin/main` was at `1ff1aa0a`, one commit ahead of this audit branch. The audit branch is based on `49d90512`; the only divergence was the expected `his-hand-levers.json` update from the latest closeout repair. It must not be reverted or merged incidentally.

The last completed `main` CI before that observation was green for `49d90512`; it did not verify `1ff1aa0a`. The recent failure history contains two actionable classes:

1. Runs `34375899662` and `34377845552` failed in `estate-contract` because the live public GitHub API returned HTTP 403. The resulting profile metadata and scheduled-run assertions were derivative failures, not evidence that the profile data itself was wrong.
2. Run `34373227039` failed in the worker runtime probe because its fake server did not become ready. The cleanup path did execute, but readiness is still a real gate failure.

The correct Wave 0 posture is therefore **last verified green commit `49d90512`, unresolved historical failure families**. Do not reopen or rewrite the default branch merely to erase historical red runs; attach fixes to the owning predicates and preserve the evidence.

## In-flight family verdict cards

### A. Backlog observability — advance

Open PRs #2599, #2597, and the related monitoring branches form one family. #2599 already contains the strongest recoverable implementation: repository discovery, issue and branch aggregates, field-level cache fallback, pagination truncation handling, and contract-backed tests. It is draft and `UNSTABLE`, but its checks currently report Semgrep/CodeRabbit success; the missing decision is scoped verification and integration, not a new design.

**Verdict:** keep one canonical implementation lane. Compare #2597 against #2599 before any further edits; supersede duplicate surface work by lineage if the implementation is equivalent. The audit does not close either PR.

### B. Clone/reaper safety — advance urgently

Open PR #2600 directly addresses issue #2484: unknown disk/resource telemetry currently falls into pressure mode and can waive clone freshness protection. The issue provides concrete live evidence and the PR includes regression coverage and bare-repository fixture work.

**Verdict:** treat #2600 as the canonical repair lane. Run the targeted reaper tests and scoped verification, then resolve remaining `UNSTABLE` causes. Do not reap branches or clones as a substitute for fixing the predicate.

### C. Recovery and custody — preserve, then converge

PRs #2573, #2576, #2569, and #2567, plus `work/recovery-*`, `work/git-finishline-*`, and the MCP estate family, are related recovery lanes. Several are `DIRTY` or based on non-`main` parents, so they cannot be merged as-is. Their commits are not disposable: they encode custody, source-separation, WAL-reader, and publication-recovery intent.

**Verdict:** designate a single recovery integration owner, derive each lane's unique commits against current `main`, and produce successor PRs where a branch's base is irreconcilable. Preserve exact branch and commit lineage in the successor; never force-push or silently delete the originals.

### D. PSP production systems — sequence, do not fan out further

The `codex/psp-*` branches and 87 `program:production-systems` issues are a program, not independent backlog items. Several branches are one-to-three commits ahead and carry contracts, evidence, freshness, authority, and off-platform-copy concerns.

**Verdict:** execute by dependency order: admission/contracts, evidence and freshness, authority parity, then delivery/convergence. Freeze new sibling branches until the current family map identifies the canonical next leaf.

### E. Security, dependency, and credential work — separate technical from human gates

Open issues #2590, #2591, #2403, #2371, and the `security/*` and `dependency-*` branches mix reproducible code work with account, approval, or credential gates.

**Verdict:** technical fixes remain ordinary PR work; account authorization and secret minting remain in their existing human/credential owners. Do not encode credentials in issues, branch names, reports, or commits. The latest dependency and MONETA workflow runs are evidence of activity, not proof that every advisory is resolved.

### F. Private custody and HOSPES/ARCA — preserve and wait on named owners

Issue #2603 records a sanitized custody receipt. Its latest comment reports two external copies and a restore test, while ten file records and three recovery investigations remain dependent on a private account export. HOSPES/ARCA issues similarly contain explicit human or external custody gates.

**Verdict:** retain the receipts and leave the human-gated atoms with their named owners. No public issue or repository artifact should receive private bytes. This is not a candidate for stale cleanup.

## Branch constitution

`BRANCHES.md` does not exist, so this audit does not invent one from a template. Actual usage supports the following constitution for a future durable document:

- `main` is protected production trunk and must only move through PR integration.
- One branch represents one intention; a PR is the durable integration owner.
- `feat/`, `fix/`, `heal/`, `chore/`, `docs/`, `refactor/`, `codex/`, `copilot/`, `security/`, `recovery/`, and `work/` are observed families, not interchangeable lifecycle states.
- Branches without an open PR require an explicit owner receipt, successor issue, or preservation record before any cleanup consideration.
- Branches based on another topic branch must declare the stack and merge order; they must not be presented as independent `main` work.
- Cleanup is allowed only after exact-head landing or an evidence-backed successor mapping. Age alone is never a cleanup predicate.

The constitution should be added only when it can be derived from and checked against the branch registry and PR metadata; this audit records the policy without pretending the missing file is already implemented.

## Ordered execution waves

### Wave 0 — verify the substrate

1. Treat `49d90512` as the last verified green commit at this audit observation; record the two CI failure classes as predicate-owned follow-up work.
2. Run `scripts/verify-scoped.sh` against each proposed repair branch before any merge or rebasing.
3. Confirm the governance registry and workflow arming state; disabled workflows are not counted as healthy automation.
4. Preserve `his-hand-levers.json` as the authoritative human-gated state.

### Wave 1 — recover canonical in-flight work

1. Advance #2600 through targeted reaper verification and review.
2. Select #2599 as the backlog-monitoring comparison baseline and reconcile #2597 against it.
3. Map unique commits for the recovery/MCP family and create lineage-preserving successors where the current base is `DIRTY`.
4. Freeze duplicate PSP fan-out until the dependency order is explicit.

### Wave 2 — integrate by dependency

Land only verified canonical lanes: reaper safety, backlog observability, recovery custody, then PSP contracts/evidence. Each lane gets one exact-tree verification batch and one PR owner.

### Wave 3 — expand observability

After the canonical feeds are integrated, use the backlog aggregates to drive issue/branch debt dashboards and health reports. Treat generated measurements as evidence, not as permission to close work.

### Wave 4 — evolve governance

Derive and add `BRANCHES.md`, wire branch-family checks into the existing governance registry, and make successor/owner receipts machine-checkable. This is the final wave because governance must encode observed reality rather than aspirational names.

## Immediate disposition

This report is the durable audit receipt for the current read-only pass. It advances the work without dismissing unresolved artifacts. The next mutation batch is narrowly bounded to Wave 0 and Wave 1 owners above; no broad branch reaping, issue closure, or PR deletion is justified by the inventory alone.
