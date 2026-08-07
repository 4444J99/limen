# 2026-08-07 — PR-debt estate drain (GITVS-UNCAPPED-PR-DEBT-0715)

Issue: #1950
PR: #1944

## What this is

The morning board's "critical next" task — *Add an uncapped exact owner-route predicate for the
whole PR estate* — had already shipped its predicate (`scripts/gitvs.py pr-debt --check`,
exit 0 ⟺ census exhaustive AND `lifecycle_untyped_count == 0`). What kept it red, and kept the
brief re-surfacing it daily, was the data: **283 open PRs across 313 repos carried no
`lifecycle:*` label**, plus an admission bug that nagged a machine-paused task at the operator
every morning.

## The three concerns (one branch each)

1. **`fix/handoff-hold-labels` → PR #1941** — `scripts/handoff-relay.py` hand-listed two of the
   three canonical hold labels and omitted `operator-paused`; it now derives from
   `limen.progress_selection.HOLD_LABELS` with per-label reason counts. The `operator-paused`
   label on GITVS-UNCAPPED-PR-DEBT-0715 was stamped by the TABVLARIVS keeper at task intake
   (commit c34b016d, 2026-07-15) — a machine act, never an operator pause.
2. **`feat/lifecycle-cohort-manifests` → PR #1944** — `scripts/pr-lifecycle-estate-manifest.py`
   v2: disposition × cohort parameterization (`limen.pr_lifecycle_estate_manifest.v2`), the
   plan SHA binding both, fail-closed cohort selectors (operator cohorts require `--owner`,
   private requires `--facts` from the same census), and a guard refusing private rows under
   `docs/`.
3. **`heal/ianva-cli-census-drift` → PR #1946** — main went red when PR #1940 flipped copilot to
   direct HTTP but `cli/src/limen/census.py` still declared `ianva-stdio`; healed root-to-leaf
   (census transport + test shape + `gates.yaml` pytest-cli paths now include `ianva/**`).

## The drain (census 2026-08-07: 313 repos / 1300 open / 283 untyped)

| Cohort | Items | Disposition | Manifest (SHA-pinned) | Status |
|---|---|---|---|---|
| operator-stale | 25 | `lifecycle:blocked` (fail-closed) | `docs/receipts/pr-lifecycle-operator-stale-manifest-20260807.json` (b18cde39…864b) | applied_verified |
| private | 41 | per-facts | `logs/` (private) + public receipt `docs/receipts/pr-lifecycle-private-receipt-20260807.json` (218f7e50…5816) | applied_verified |
| dependabot | 200 / 94 repos | `lifecycle:blocked` (fail-closed) | `docs/receipts/pr-lifecycle-dependabot-blocked-manifest-20260807.json` (ae6ff627…e95f) | applied_verified |
| operator-active | 15 (17 planned; 2 merged first) | `lifecycle:active-human` | `docs/receipts/pr-lifecycle-operator-active-manifest-20260807-final.json` (dfc72d9f…f09e) | applied_verified |

The dependabot delivery upgrade — retyping 200 PRs to `lifecycle:delivery`, which arms
merge-drain's autonomous merge rail — is a **mass-merge human gate**, filed as lever
`L-DEPENDABOT-DELIVERY-ARM` (issue #1947), not decided here.

## Discharge sequence

Heal #1946 merges (waiter armed, auto-merge) → batch pr-gate rerun + concurrent waiters on
#1941/#1944 → re-census → operator-active apply → `gitvs.py pr-debt --check` exit 0 →
keeper-ships the green ledger (`LIMEN_PR_DEBT_RECORD_INTERVAL_HOURS=0
python3 scripts/pr-debt-trend.py --record`; the ledger is keeper-custody, never committed on a
session branch) → broker-verify the task done (predicate_exit_code 0, receipt_target
`git:organvm/limen:docs/github-pr-debt-ledger.json`).
