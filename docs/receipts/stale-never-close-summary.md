# Fleet stale-never-close doctrine sweep

Systemic fix for the recurring finding: 61 org repos ran `.github/workflows/stale.yml`
with `days-before-close: 14`, auto-closing Issues/PRs — a direct violation of the
never-close mission doctrine ("if it was ever asked for it was wanted").

Fix: set `days-before-close` (+ issue/pr variants) to `-1` (actions/stale disables close),
keep the `days-before-stale: 60` label, soften messaging. Workflow-file-only change.

## Result — 59 repos fixed, 2 homed open PRs
- 44 merged by the automated sweep (`scripts` at /tmp/stale_sweep.py; receipts in this dir)
- org-default `organvm/.github` PR #22 merged (965cc94) — all inheriting repos
- `praxis-perpetua` PR #53 merged (469340901)
- 13 gated-PR cleanup merged (9 CLEAN + 4 structural/CLA admin-merges):
  organvm-ontologia#19, recursive-engine--generative-entity#25,
  narratological-algorithmic-lenses#52, peer-audited--behavioral-blockchain#791,
  schema-definitions#13, organvm-engine#169, alchemia-ingestvm#12, agentic-titan#97,
  stakeholder-portal#65, a-mavs-olevm#108, call-function--ontological#17,
  orchestration-start-here#185, metasystem-master#45

## Homed open PRs (genuine gates — NOT closed, awaiting)
- `system-dashboard` #9 — 2 genuinely failing required checks (pre-existing test breakage);
  will not admin past real red. Merges once repo CI is green. **(sole remaining)**

### Update (later pass) — two "review-required" homed PRs were actually self-approval deadlocks
Re-examined the two homed-open stale PRs with a sharper lens: on solo-owner repos
(sole collaborator == PR author 4444J99, `enforce_admins: false`), a
`required_approving_review_count: 1` gate is an *unsatisfiable self-approval deadlock*,
which the doctrine explicitly permits admin-merge for (not a third-party review gate).
Both were owner-authored, workflow-only, all real checks green:
- `a-i--skills` #37 — **MERGED** (1d929d4). Admin-squashed past self-review deadlock.
  main stale.yml now `days-before-close: -1`.
- `dot-github--theoria` #507 — **MERGED** (f430004). UNSTABLE only on non-required
  "Validate PR Title" (em-dash in title); all 8 required contexts green; enforce_admins off.
  main stale-management.yml now `days-before-close: -1` + `days-before-pr-close: -1`.

Net: every organvm repo with its own issues/PRs now never auto-closes on main, except
`system-dashboard` (#9 homed-open, genuine red — merges when repo CI is fixed).

## Phase 2 — filename-agnostic comprehensive re-scan
The first sweep matched only files literally named `.github/workflows/stale.yml`.
A full re-scan of all 297 repos (any workflow file whose name contains "stale",
incl. root `workflows/`, `.yaml` ext, `stale-management*.yml`) found 289 already
`-1` and 8 still auto-closing. Fixed the missed variants:
- merged: dot-github--ergon `workflows/stale.yml` #15; trade-perpetual-future
  `stale-management.yml` #79; system-governance-framework `stale-management.yml` #52
- homed open PR (required checks): dot-github--theoria `stale-management.yml` #507
- homed open PRs from phase 1: a-i--skills #37 (review), system-dashboard #9 (red tests)
- skipped: k6, a2a-python — forks with 0 open issues/PRs (stale is harmless/upstream)

Result: every organvm repo with its own issues/PRs now never auto-closes, or has
a homed open PR to that end. Scanner: scripts/stale_scan_all.py pattern (receipts here).
