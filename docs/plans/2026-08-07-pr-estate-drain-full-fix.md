# PR estate drain — the full fix

Issue: #1975
PR: (pending)

> **Framing superseded by `2026-08-07-pr-estate-drain-full-fix-v2.md` (#1981).** Findings D1, D3,
> D4 and every measurement below stand. **D2 is corrected there** — its code facts were read from a
> checkout 29 commits behind `origin/main`, which carries estate-manifest v2 (#1944): a
> `lifecycle:delivery` writer *does* exist, enacted by nothing. D5 stands for draining, is
> superseded for typing. This document is left exactly as shipped; the correction is not an
> overwrite.

## Context

A 2026-08-07 session concluded that the estate's 1,293 open PRs were not draining because the
merge organs were **starved of lifecycle labels**, sealed a 278-item `lifecycle:blocked` manifest
(`plan_sha256 6c9c7197…`, 110 repos), and reported the apply as the one keystroke between the
estate and a draining backlog. The apply then failed:

```
pr-lifecycle-estate-manifest: BLOCKED — 4444J99/sovereign-systems--elevate-align#277 is no longer open
```

That diagnosis is wrong in both directions, and the block was never the bottleneck. A live
exhaustive re-measurement (below) shows the manifest had **nothing left to apply**, and that the
label it applies is one the merge rung **never acts on**. This plan replaces the whole framing.

## Ground truth (measured 2026-08-07T13:49–14:05Z)

Method, stated up front per the Data Grounding discipline: `gh repo list` over all **10** canonical
owners → **313 repositories** (72 archived) → `gh pr list --state open --limit 1000` per repo at
8-way concurrency. **0 fetch errors**, so the enumeration is exhaustive, not a sample. Wall clock
**18s**. Channels queried: GitHub PR labels, PR bodies, PR authors/draft state, issue timelines,
and the local ledger `logs/gitvs-pr-debt-facts.json` (generated `2026-08-07T00:49:00Z`).

| Fact | Live value |
|---|---|
| Open PRs | **1,298** |
| `lifecycle:blocked` | 1,146 (88.3%) |
| no lifecycle label | 132 |
| `lifecycle:active-human` | 14 |
| `lifecycle:preservation` | 6 |
| **`lifecycle:delivery`** | **0** |
| Drafts | **530** (40.8%) |
| PRs in archived repos (immutable) | 20 |
| Authors | 4444J99 627 · dependabot 361 · jules 308 · other 2 |

## Findings — five defects, in causal order

### D1 — The sealed manifest was already applied. `pending = 0`.

The 278-item plan rebuilds **bit-identically** from the 00:49Z ledger (`plan_sha256` reproduced:
`6c9c7197f5ea7aae617da8013a41fcad74ac0ee183fff60367e9696a72e3a17f`), so the seal is intact and the
item list is not in question. Replaying its preflight against live GitHub:

| Bucket | Count |
|---|---|
| already carry `lifecycle:blocked` | **249** |
| closed since the snapshot | 18 |
| became `lifecycle:active-human` | 11 |
| head drifted | 0 |
| **still pending an effect** | **0** |

The labels were written by actor `4444J99` at **2026-08-07T11:14:48Z** (issue-timeline evidence),
~2.5h before the failing invocation — a sibling background job landed a fresher 249-item plan.
The `!` command aborted on `4444J99/sovereign-systems--elevate-align#277`, which sorts **first**
alphabetically, so it wrote nothing; it would have aborted on one of the other 28 divergences in
any case.

**The structural defect behind the abort**, independent of this batch: `apply_plan` runs a full
preflight across every repo and raises `ManifestError` on the *first* of three fatal drift classes
(closed / head-drift / label-drift), aborting all 278 items in 110 repos. The ledger it seals
against refreshes at most every **20 hours** (`LIMEN_PR_DEBT_RECORD_INTERVAL_HOURS`, 900s timeout,
gitignored receipt). Requiring zero drift over 278 live PRs across a ≤20h window, in an estate
taking 361 dependabot PRs, makes a successful apply approach impossible. The seal is not
conservative — it is **unsatisfiable**, and its failure mode is indistinguishable from a real
policy violation.

### D2 — `lifecycle:delivery` has no writer anywhere. The merge rung is a no-op.

`scripts/merge-drain.py:134` merges **only** `disposition == "lifecycle:delivery"`; anything else
returns its disposition as a refusal, and a missing label returns `LIFECYCLE-UNKNOWN`. Estate-wide
count of PRs carrying `lifecycle:delivery`: **0**. A grep across `scripts/`, `institutio/`, and
`docs/` finds the string only in label-set definitions and in merge-drain's own comparison —
**no code path ever writes it**.

So the merge rung can never merge a PR, and the manifest's sole disposition —
`lifecycle:blocked`, self-described as *"fail-closed pending explicit lifecycle review"* — moves a
PR from one refusal state (UNKNOWN) to another (BLOCKED). **Landing all 278 labels advances zero
PRs toward a merge.** The claim that the drain "cascades" after labeling is false: it converts
untyped debt into typed debt and makes the ledger green.

### D3 — 124 PRs are "typed" to the ledger and unlabeled on GitHub — a latent false green.

`gitvs._pr_lifecycle` returns `("lifecycle:preservation", "legacy-preservation-marker")` when the
PR **body** contains the marker string
`` "Lifecycle preservation PR opened by `scripts/worktree-pr-receipts.py`." `` — **no label
required** — and `lifecycle_complete` is then `True`. Ledger source tally: `label` 889,
`missing-label` 278, **`legacy-preservation-marker` 124**, `repository-archived-immutable` 6.

Every effector reads **labels only** (`pr-lifecycle-manifest.lifecycle_labels`,
`merge-drain.lifecycle_disposition`). Reconciliation confirms the divergence exactly: of the 132
live-unlabeled PRs, **130 are precisely the ledger's 130 `preservation`-dispositioned rows**; only
2 are genuinely new since the snapshot.

Two consequences compound:

1. `build_plan` filters `if not row.get("lifecycle_disposition")`, so these 124 are **excluded from
   every estate manifest by construction** — that path can never label them.
2. Once the 278 land, `gitvs pr-debt --check` reports `untyped_count == 0` and goes **green** while
   124+ PRs remain `LIFECYCLE-UNKNOWN` to every organ that could act on them.

That is a false green in the exact class the charter's Definition of Done forbids: the scoreboard
and the effectors disagree, and nothing detects it.

### D4 — 530 drafts (40.8%) are structurally undrainable.

`owner_route_drain.classify` returns `SKIP("draft")` before any other test, and `merge-policy.sh`
holds drafts. Nothing in the fleet ever marks a PR ready. Of the **308** jules PRs inside the only
armed drain's scope, **250 are drafts**. No organ has a disposition for this cohort at all.

### D5 — Total armed drain capacity is 57 PRs out of 1,298 (4.4%).

`owner-route-drain` is the only armed drain. Its scope is `LIMEN_OWNERS=organvm,4444J99` (2 of 10
owners) intersected with jules authorship (`app/google-labs-jules` or `[limen jules` titles).

```
jules PRs in {organvm, 4444J99}            308
  − drafts                                −250
  − archived repo                           −1
  = actionable by the armed drain            57
```

The remaining **1,241** PRs have no organ: 627 authored by `4444J99`, 361 by dependabot, plus every
PR in the other 8 owners. Note also `enumerate_open_prs(max_total=500)` — a silent cap that the
jules cohort (372 estate-wide) does not yet hit but an estate-wide widening immediately would.

Arming `LIMEN_OWNER_ROUTE_DRAIN_APPLY=1` therefore drains **57 PRs and stops**. It is not "the
thousand-PR lane, end to end."

### Correction of record

The classifier gate on `gh pr edit` was **not** the blocker. It gated an apply with `pending = 0`,
toward a label no merge organ consumes. Nothing in this plan depends on lifting it.

## Resolved design decisions

- **D-a — The estate typer becomes a converger, not a seal.** A snapshot-sealed, all-or-nothing
  apply is the wrong shape for a live estate. Keep the digest gate on the *disposition policy*;
  drop it from the *item list*, which must be computed from live labels at the moment of effect.
- **D-b — Per-item tolerance, never a batch abort.** Closed / head-drifted / label-drifted items
  are **skipped and recorded in the receipt**, never fatal. A moving estate is the normal case.
- **D-c — Fix the merge gate at its source (W2), not by relabeling.** Adding `lifecycle:delivery`
  by hand to reach a merge would launder the guardrail. `merge-policy.sh` stays the merge verdict
  in every path, so the website guardrail is untouched.
- **D-d — Close D3 on both sides.** Materialize the 124 body-marker derivations into real labels
  *and* add the divergence gate, so the class cannot silently return.
- **D-e — The draft cohort is a policy lever, not a guess.** Marking 530 PRs ready or closing them
  is a bulk irreversible action at scale — it is filed, not decided here (W4).

## Workstreams

### W1 — Convert the estate typer from seal-and-apply to converge (`scripts/pr-lifecycle-estate-manifest.py`)

- Build the worklist from **live labels**, not from the ledger's `lifecycle_disposition` (this
  alone un-excludes D3's 124).
- `_preflight_repo` returns `(pending, skipped)` instead of raising; `apply_plan` proceeds on the
  intersection and records `skipped_closed` / `skipped_head_drift` / `skipped_label_drift` counts
  plus `pr_key`s in the receipt.
- Keep `--expected-plan-sha` bound to the **policy core** (schema, scope, disposition), not to a
  perishable item list.
- **Predicate:** a second consecutive run reports `effect_count == 0` — the idempotent fixed point.

### W2 — Give the merge rung a reachable gate — the actual unblock

Either (a) a typer that promotes non-draft, mergeable, CI-green, non-conflicting PRs to
`lifecycle:delivery`, or (b) change `merge-drain`'s gate from `== lifecycle:delivery` to
`∉ {active-human, preservation, superseded, blocked}` plus `merge-policy.sh` exit 0. **(a) is
preferred** — it matches the estate's explicit-typing posture and leaves the refusal set legible.
In both, `merge-policy.sh` remains the sole merge verdict.

- **Predicate:** `lifecycle:delivery` count > 0 **and** `merge-drain --dry-run` reports ≥ 1 MERGE
  candidate. Today both are 0, which is why the rung has never moved a PR.

### W3 — Close the ledger↔label divergence (the missing gate)

1. A rung materializing every `legacy-preservation-marker` derivation into a real
   `lifecycle:preservation` label (124 PRs).
2. `scripts/check-lifecycle-parity.py` — exit `0` ⟺ for every ledger row,
   `lifecycle_disposition` equals the live GitHub label set's derivation. Wire into the GATES
   registry (`institutio/governance/gates.yaml`) so it runs on any change to `gitvs.py` or the
   lifecycle effectors.
3. Demote `legacy-preservation-marker` from `lifecycle_complete = True` to a named debt reason, so
   the scoreboard stops reporting typed work that no effector can see.

- **Predicate:** `check-lifecycle-parity.py` exit 0 with divergence count 0 (today: **124**).

### W4 — Draft cohort disposition (530 PRs) — human-gated lever

No organ has a policy for 41% of the estate. The options (bulk mark-ready-if-green / close-if-aged
/ explicitly type and stop counting as debt) are a large irreversible action, so this is filed as a
lever in `his-hand-levers.json` — `L-PR-DRAFT-COHORT-DISPOSITION` — with the measured cohort
attached, **not** decided in-session and not recited in a closeout.

### W5 — Widen drain scope beyond the jules cohort

- `_pr_scan.enumerate_open_prs` already has an estate-wide `author=None` mode; extend
  `LIMEN_OWNERS` past `organvm,4444J99` and raise/observe the `max_total=500` cap (log the
  truncation — a silent cap reads as "covered everything").
- Add a **dependabot cohort classifier** (361 PRs): grouped-update supersession + auto-merge on
  green is a mechanical disposition, and it is the single largest tractable slice.
- The 627 `4444J99`-authored PRs need owner routing; scope in a follow-up once W2 lands.

### W6 — Separate the cheap label probe from the expensive exhaustive census

The 20h-stale ledger is what made D1's seal unfalsifiable. The census's per-repo paginated GraphQL
with total reconciliation earns its cost as the **exhaustiveness proof** and should keep its
cadence; the *label* facts effectors need are obtainable in **18s** (measured) via `gh pr list` at
8-way concurrency. Add that as a live probe the effectors read, leaving the scoreboard census
unchanged.

## Sequencing

W3.2 (the parity gate) and W1 are pure code with no outward writes — they land first and make
every later claim verifiable. W2 is the actual merge unblock and depends on nothing. W3.1 and W5
are effectors gated behind W1's converger. W4 is filed immediately and never blocks the rest.

```
W3.2 gate ─┐
W1 converge ┼─→ W3.1 materialize ─→ W5 widen ─→ (drain runs)
W2 merge gate ─────────────────────┘
W4 lever  (filed, off the critical path)
W6 probe  (independent; unblocks staleness)
```

## Definition of done

An executable predicate, per the charter — not this prose:

1. `check-lifecycle-parity.py` exit 0 (ledger ⇔ live labels; today 124 divergent).
2. Estate converger run twice → second run `effect_count == 0`.
3. `lifecycle:delivery` count > 0 and `merge-drain --dry-run` yields ≥ 1 MERGE candidate.
4. `scripts/verify-scoped.sh` green on the diff.
5. `L-PR-DRAFT-COHORT-DISPOSITION` present in `his-hand-levers.json` with the measured cohort.

Until (3) holds, no amount of labeling drains anything — that is the finding this plan exists to
correct.
