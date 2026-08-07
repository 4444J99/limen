# Reconcile the external prima-materia/consolidation charters into settled estate law

Issue: #1934
PR: #1935

## Context

On 2026-08-06 the operator delivered two externally-drafted charters —
`~/Downloads/OPERATION_PRIMA_MATERIA.md` (corpus census → intake → triage → consolidate →
surface → steady state) and `~/Downloads/consolidation-directive.md` (portvs / stratvm /
svbterranea local restructure) — with the directive to "solve this problem via healing,
expanding, and evolving the system." Both were drafted by chat sessions blind to this
estate's substrate. A three-agent ground-truth sweep (corpus substrate, naming/organ
governance, disk reality) found that they are **re-derivations of decisions this estate
already ratified in `docs/plans/2026-07-30-portvs-astra-consolidation.md`**, with degraded
conclusions where they diverge — and that the corpus ask is already tracked in
`EVERY-ASK-LEDGER.md` as a 28-ask cluster graded **drifted**, whose recorded cure is *one
bounded objective, one named owner, one executable done-predicate — not another charter*.

This plan is the reconciliation: heal the drift between the external charters and settled
law, expand by routing each genuine gap to its existing owner, and evolve by codifying the
reconcile-before-adopt rule so the next externally-drafted charter cannot re-litigate
settled decisions unnoticed.

## Resolved design decisions

- **D1 — Reconcile-before-adopt, as precedent.** An externally-drafted charter is an
  *atom for reconciliation*, never a directive for execution. Codified as censor precedent
  `PREC-2026-08-06-external-charter-reconciles-before-adoption` (this PR). Evidence: both
  charters re-derived the 2026-07-30 plan — `stratvm` where the ratified decision was
  `astra` (stratvm = fallback), "never git worktrees" where the ratified law is
  domains-persistent + Meeseeks-governed summons (`IF-SESSION-NON-CONTENTION`), `NAMES.md`
  where `spec/index-nominum/roll.yaml` is the CI-gated registry, a "ninth organ /
  STATE.yml" where rank 9 is Health and hydration is `FLAME.md` + EVOCATOR, and a
  `corpvs/_intake` tree where `institutio/governance/corpora.yaml` +
  `scripts/corpus_resolve.py` already own corpus homes.
- **D2 — The charters are archived, not adopted.** Both land verbatim under
  `docs/consolidation/external-charters/` with a provenance + verdict header (nothing
  local-only, nothing lost; disposition MERGE into the 2026-07-30 lineage). Their genuinely
  useful content — the disposition vocabulary, the batch cadence, the gap-report-is-a-
  deliverable rule — is already native law (`atom-homing.yaml`, bounded batches in the
  prompt-corpus policy, CLAUDE.md § Data Grounding).
- **D3 — The naming ruling is a lever, not a rename.** The 2026-07-30 plan decided
  `limen → astra` ("veto any in one word"); per
  `PREC-2026-07-30-plan-decisions-dont-bind` that plan-only decision binds nothing —
  `ASTRA` was never enrolled in `roll.yaml` — and the operator's 2026-08-06 transcript
  names `stratvm` instead. Two conflicting operator signals on the system's own name is an
  identity ruling only he can make: filed as lever `L-NAME-RULING-LIMEN-ASTRA-STRATVM`
  (this PR). No rename executes until the lever discharges through the nomenclator mint
  workflow (`scripts/nomenclator.py --check` → roll row → alias-layer migration per ARC 3).
- **D4 — Expansion = routing, not minting.** Every gap the charters surface routes to an
  existing owner (below). No new repo, no new registry, no new root file, no parallel
  substrate.

## Steps

1. **HEAL (this PR)** — archive both external charters under
   `docs/consolidation/external-charters/` with verdict headers; append the D1 precedent
   to `censor/precedents.jsonl`; append the D3 lever to `his-hand-levers.json`; ship this
   plan through the #1934 chain. One branch, one concern, one PR.
2. **EXPAND / already-homed (cite, do not refile)** — grok ingestion: declared vacuum
   `grok-history-memory` in `corpora.yaml` + provider bundles lever
   `L-CCE-PROVIDER-BUNDLES` (#1394). ChatGPT full export: blocked on the login atom,
   #1545. Workspace-root residue (16 loose June files, the 209-line-dirty
   `collaboration-operations-platform`, empty org dirs, the unregistered
   `.claude/worktrees/vltima-closeout-20260709` orphan): owned by the hot-cache predicate
   (`verify-hot-cache.sh` R5/R6) + the reclaim organ + ARC 5 of the 2026-07-30 plan —
   surfaced by beat sensors, not by a new cleanup charter.
3. **EXPAND / next bounded objective (successor session, its own plan+issue+PR)** —
   disposition drain pilot: the prompt-atom ledger holds 742,203 atoms with **0 assessed**
   and `validation: FAIL` (thousands of operator occurrences lacking atom coverage;
   20,462 pending files; newest event 2026-07-08). One bounded batch through the existing
   disposition axis (`docs/prompt-corpus-policy.json` weights/bands), plus cursor refresh
   so `EVERY-ASK-LEDGER.md` stops reporting a month-stale horizon. Owner:
   `scripts/prompt-atom-ledger.py` organ.
4. **EXPAND / second bounded objective (successor session)** — knowledge-corpus revival:
   `scripts/corpus-converge.py` is built, gated off (`LIMEN_CORPUS_CONVERGE=1`), and its
   target (`~/Workspace/knowledge-corpus/`, 13 faces + `00-THE-ONE.md`) is empty and not a
   git repo, while `FLAME.md` still tells every lane to read `00-THE-ONE.md`. One bounded
   converge run + making the target a real repo. Owner: convergence registry
   (`institutio/governance/convergence.yaml`).
5. **EVOLVE / owed** — Obsidian-vault openability of the corpus stores is the one
   genuinely-new capability in the charters (stores are already markdown/jsonl; a vault
   projection is cheap). owed: a `convergence.yaml` vacuum row naming it, filed when the
   knowledge-corpus revival (step 4) lands — the vault view is a projection of that
   target, not of the raw private stores (homing is distillation, never transfer).

## Premortem

- **What most plausibly makes this wrong or unwelcome?** That this plan becomes ask #29
  of the already-drifted 28-ask cluster — another multi-goal bundle. Guard: steps 3–5 are
  explicitly *not* this session's work; they are named bounded objectives with existing
  owners, and this PR's own scope is closed (archives + precedent + lever + plan). Second
  risk: the operator actually wants the rename *executed*, not filed — but with two
  conflicting signals (astra 07-30, stratvm 08-06) and ~258 `LIMEN_*` parameters,
  `com.limen.*` LaunchAgents, the CLI, the Worker, and the dashboard bound to the name,
  executing either reading tonight would be the exact charter-over-registry defect D1
  exists to stop. The lever is the fast path: one word discharges it.

## Verification

- `bash scripts/verify-scoped.sh` on the branch (implicates `session-phase` via
  `docs/plans/**`, censor/lever surfaces via their parity checks).
- `python3 scripts/check-session-phase.py` — the #1934 chain is green with `PR: (pending)`
  until `session-plan.py close` stamps the implementing PR.
- `scripts/merge-policy.sh <PR#>` — docs/registry class, non-deploy; merge on CLEARED.
- Fixed point: `scripts/no-tasks-on-me.sh` and `python3 scripts/credential-wall.py --check`
  both exit 0 after merge — the naming atom hangs on the lever registry, not on the
  operator or this session.
