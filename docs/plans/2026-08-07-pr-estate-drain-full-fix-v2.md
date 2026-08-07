# PR estate drain — the full fix, v2: the lifecycle axis gets an ideal form

Issue: #1981
PR: (pending)

Supersedes the *framing* of `docs/plans/2026-08-07-pr-estate-drain-full-fix.md` (#1975, merged as
#1976). That plan is not overwritten and not withdrawn: its measurements stand, four of its five
findings stand, and its workstreams remain the leaf-level work. What changes is where the fix
belongs. **W1–W6 are point repairs at the leaves; the base defect is that the PR-lifecycle domain
has no ideal form at all.**

## The correction of record

The v1 diagnosis was read from the live checkout `/Users/4jp/Workspace/limen`, which the session
banner reported as **29 commits behind** `origin/main`. That checkout carries **v1** of
`scripts/pr-lifecycle-estate-manifest.py`; main carries **v2** (`cfd01fb8`, #1944 — *"per-cohort
dispositions, SHA-pinned, private rows via `--facts`"*), where the single module constant
`DISPOSITION = "lifecycle:blocked"` became `DISPOSITION_META` over all five labels selected by
`--disposition`, and `COHORT_SELECTORS` partitions the estate into
`dependabot | operator-active | operator-stale | private | all`.

| v1 finding | Verdict against `origin/main` |
|---|---|
| **D1** — the sealed manifest had `pending = 0`; `apply_plan` aborts all 278 items on the first drift | **Stands.** v2's `_preflight_repo` still raises at lines 191 / 193 / 198 for all three drift classes. |
| **D2** — *"`lifecycle:delivery` has no writer anywhere"* | **WRONG, and corrected below.** v2 can write it via `--disposition`. |
| **D3** — 124 body-marker derivations typed to the ledger, unlabeled on GitHub | **Stands.** `gitvs.py:571` is byte-identical on main. |
| **D4** — 530 drafts (40.8%) structurally undrainable | **Stands** (measured from GitHub, not from code). |
| **D5** — armed drain capacity 57 of 1,298 | **Stands for draining; superseded for typing.** v2's cohorts widen what can be *typed*; nothing widens what can be *merged*. |

### D2, corrected — the writer exists and is enacted by nothing

The defect is not a missing writer. It is three missing things behind an existing one:

1. **No enactment.** `grep -rn "pr-lifecycle-estate-manifest" institutio/ scripts/metabolize.sh
   scripts/drain.sh` returns **empty**. No `sensors.yaml` row, no `gates.yaml` row, no beat rung.
   The typer runs only when a human types it, sealed against a ledger that refreshes at most every
   20 hours. **v2 is a capability, not an organ** — which is precisely the estate's own named
   defect class `PREC-2026-07-10-declared-but-unwired-is-a-defect`.
2. **No admits-predicate.** `--disposition lifecycle:delivery` will label anything the cohort
   selector returns. There is nowhere that declares *what makes a PR merge-eligible* — so the
   parameter is a hand-typed assertion, not a derivation.
3. **No consumer derivation.** `scripts/merge-drain.py:134` still compares
   `disposition != "lifecycle:delivery"` against a string literal.

The v1 conclusion therefore survives its own wrong premise: **live `lifecycle:delivery` count is
still 0, and the merge rung has still never moved a PR.** The mechanism is different, and the
different mechanism is the whole point of this plan.

## The diagnosis one level up: this domain has no ideal form

The estate has a precise, repeated pattern for a solved axis — call it the **derive triple**:

> a **declared registry** → **consumers that derive** instead of restating → a **`check-*.py`
> parity predicate** that turns drift into a red check.

Where all three exist, adding a thing is one registry row. Seven axes have it (`gates.yaml`,
`parameters.yaml`, `sensors.yaml`, `corpora.yaml`, `convergence.yaml`, `atom-homing.yaml`,
`ideal-forms.yaml` — which names itself *"the seventh axis of the VIGILIA spine"*). The
PR-lifecycle axis has **one third of it**, and that third is the weakest third:

| Element | PR lifecycle today |
|---|---|
| Declared registry | `institutio/github/estate.yaml` `pr_debt_policy.lifecycle_labels` — **names only**, no capabilities |
| Consumers derive | **Almost never.** Four private copies of the label set: `merge-drain.py:47`, `pr-lifecycle-manifest.py:15`, `gitvs.py:554`, `pr-lifecycle-estate-manifest.py:33` (`DISPOSITION_META`). One partial exception, found by verifying this plan: `gitvs.py:568-570` **does** derive `preservation_labels`/`preservation_markers` from `estate.yaml` — so the derive pattern is already half-present in the consumer this table treats as furthest from it, and W0's `gitvs` conversion is the smallest of the four, not the largest |
| Parity predicate | **None.** A sixth disposition means editing four files and hoping |
| Ideal form | **None.** 22 ledger entries, none for lifecycle/dispositions/drain |

Three consequences follow directly, and each is a measured defect above:

- **Semantics live as literals, not capabilities.** The `sensors.yaml` header states the rule that
  the rest of the spine obeys — *"These are capabilities, not special sensor names: consumers must
  work unchanged if an id is renamed."* The lifecycle registry declares only names, so
  "merge-eligible" has no home but `merge-drain.py:134`. Rename `lifecycle:delivery` and the merge
  rung goes silently inert. **That is D2's mechanism, generalized.**
- **Two derivation sources with no reconciler.** `gitvs` derives a disposition from PR *bodies*;
  every effector reads *labels*. Nothing compares them. **That is D3.**
- **Cohorts exist in code, dispositions do not.** v2's `COHORT_SELECTORS` is a module dict, so the
  530-draft cohort has no declared disposition and no declared owner — it is an unnamed vacuum,
  which Rule #1 forbids. **That is D4.**

**The salve is the derive triple, applied to this axis.** Not a patch per effector — one registry,
one predicate, one ideal form. Everything in v1's W1–W6 then becomes a consumer conversion.

## Resolved design decisions

1. **The base fix is a registry axis, not a patch to each effector.** Ship
   `institutio/governance/lifecycle.yaml` as the eighth axis of the VIGILIA spine, with
   `scripts/check-lifecycle.py` as its drift predicate wired into `institutio/governance/gates.yaml`.
   Patching `merge-drain.py` alone would fix one symptom and leave the other three copies to drift.
2. **Consumers read by capability, never by disposition id.** `merge-drain` asks *"which
   dispositions are `merge_eligible`?"*, never `== "lifecycle:delivery"`. Enforced by check C of
   `scripts/check-lifecycle.py`, armed per-consumer through the `ratchets:` block of
   `institutio/governance/lifecycle.yaml` — the same conversion ratchet `gates.yaml` already uses.
3. **`lifecycle:delivery` is written by an organ under a declared `admits` predicate — never by
   hand, and never in place of the merge verdict.** The `admits:` block in
   `institutio/governance/lifecycle.yaml` declares what makes a PR merge-eligible (not draft,
   mergeable, required checks green, no conflicts); `scripts/merge-policy.sh` remains the sole
   merge verdict in every path, so the website guardrail is untouched. Typing a PR `delivery` by
   hand to reach a merge would launder that guardrail and is banned by check C.
4. **The estate typer becomes a converger, not a seal.** Per-item tolerance replaces the batch
   abort: closed / head-drifted / label-drifted items are skipped and recorded in the receipt,
   never fatal. `--expected-plan-sha` binds the *policy core* (schema, scope, disposition, cohort),
   not a perishable item list. Home: `scripts/pr-lifecycle-estate-manifest.py` and its receipt
   schema. Rationale: requiring zero drift across 278 live PRs over a ≤20h window, in an estate
   taking 361 dependabot PRs, is unsatisfiable — and its failure is indistinguishable from a real
   policy violation.
5. **A derivation that never becomes a label is debt, not completion.**
   `legacy-preservation-marker` is demoted from `lifecycle_complete = True` in `scripts/gitvs.py`
   to a named debt reason, and the 124 derivations are materialized into real labels. Divergence
   is measured by check F of `scripts/check-lifecycle.py` against a **shrink-only baseline**
   (today: 124), the ratchet pattern `check-params.py` and `check-root-manifest.py` already use.
6. **A typer that no beat rung invokes is a capability, not an organ.** The estate typer gets one
   row in `institutio/governance/sensors.yaml`, held by `scripts/check-sensors.py`. Precedent:
   `PREC-2026-07-10-declared-but-unwired-is-a-defect`, and IF-AMALGAMATION's own recorded history —
   its series stopped for eleven days because a producer existed and nothing ran it.
7. **The draft cohort is a named vacuum with a human owner, not a guess.** 530 PRs (40.8%) is a
   bulk irreversible action at scale, so it is filed as lever `L-PR-DRAFT-COHORT-DISPOSITION` in
   `his-hand-levers.json` with the measured cohort attached. Check E of
   `scripts/check-lifecycle.py` requires every declared cohort to carry either a
   `default_disposition` or an `owner_lever` — so an undisposed cohort is a red check, never a
   silent gap.
8. **The domain gets an ideal form whose distance is derived, never written.** Row
   `IF-PR-LIFECYCLE` in `institutio/governance/ideal-forms.yaml` plus its `### IF-PR-LIFECYCLE`
   heading in `docs/IDEAL-FORMS-LEDGER.md`, measured by `scripts/check-ideal-forms.py --measure`.
   Per that registry's contract the row carries no status and no distance — there is no field to
   lie in.
9. **The v1 record is corrected in place, not rewritten.** D2 and D5 are amended in this plan and
   in `docs/receipts/pr-estate-drain-diagnosis-20260807.json` via an explicit `corrections` block;
   the merged plan file and the merged receipt's original measurements stay exactly as shipped.
   A superseding plan that edits its predecessor's findings destroys the evidence of the error.
   Homed as case law in `censor/precedents.jsonl` →
   `PREC-2026-08-07-corrections-are-additive`. (It was homed here only by citing the receipt
   above until `scripts/check-plan-decisions.py` stopped counting a record as a registry — a
   receipt is where a measurement lives, never where a decision binds.)

## The registry — `institutio/governance/lifecycle.yaml`

Rows are dispositions; columns are **capabilities**; a second block declares cohorts; a third
declares the consumers held to parity. Sketch (the shipped file carries the full header prose the
other registries carry):

```yaml
schema_version: 0.1

dispositions:
  "lifecycle:delivery":
    label_color: "0e8a16"
    description: "Merge-eligible once required checks are green"
    merge_eligible: true          # merge-drain derives its gate from THIS, not from the id
    fail_closed: false
    human_owned: false
    terminal: false
    admits:                       # what JUSTIFIES this typing (decision 3)
      draft: false
      mergeable: true
      required_checks: green
      conflicts: none
    owner: gitvs
  "lifecycle:preservation":
    merge_eligible: false
    terminal: true
    derived_from:                 # declared derivation sources — closes D3
      labels: ["custody:preservation"]
      body_markers: ["Lifecycle preservation PR opened by `scripts/worktree-pr-receipts.py`."]
      materialize: true           # a derivation MUST become a real label
  "lifecycle:active-human":  {human_owned: true,  merge_eligible: false}
  "lifecycle:blocked":       {fail_closed: true,  merge_eligible: false}
  "lifecycle:superseded":    {terminal: true,     merge_eligible: false}

cohorts:                          # every cohort needs a disposition OR a lever (check E)
  dependabot:       {selector: ..., default_disposition: "lifecycle:delivery", drainable: true}
  operator-active:  {selector: ..., default_disposition: "lifecycle:active-human"}
  operator-stale:   {selector: ..., default_disposition: "lifecycle:blocked"}
  draft:            {selector: ..., default_disposition: null,
                     owner_lever: L-PR-DRAFT-COHORT-DISPOSITION}   # named vacuum, Rule #1
  archived-repo:    {selector: ..., immutable: true}

consumers:                        # the parity contract
  - {path: scripts/merge-drain.py,                  derives: [merge_eligible]}
  - {path: scripts/pr-lifecycle-manifest.py,        derives: [labels]}
  - {path: scripts/pr-lifecycle-estate-manifest.py, derives: [labels, label_color, description, cohorts]}
  - {path: scripts/gitvs.py,                        derives: [labels, derived_from]}

ratchets:                         # armed per-PR as each consumer converts (gates.yaml pattern)
  merge_drain_derives: false
  gitvs_derives: false
  estate_manifest_derives: false
  estate_yaml_derives: false
```

### `scripts/check-lifecycle.py` — the drift predicate

Lettered checks, in the `check-gates.py` house style. **A–C, E, G are offline** (they run in
pr-gate); **D and F need GitHub** and run in the beat and on demand.

| Check | Contract |
|---|---|
| **A** | Registry ↔ `institutio/github/estate.yaml` `lifecycle_labels` exact set equality, until `estate.yaml` converts to deriving (ratchet `estate_yaml_derives`). |
| **B** | No declared consumer contains a lifecycle-label string literal outside its registry loader. Shrink-only baseline seeded with today's four copies. |
| **C** | No declared consumer branches on a disposition **id** where a capability exists. The banned form is exactly `!= "lifecycle:delivery"`; armed per consumer via `ratchets:`. |
| **D** | Every lifecycle label live in the estate is a declared disposition, and each declared `label_color` matches the live label. Catches undeclared label drift in both directions. |
| **E** | Every cohort carries a `default_disposition` **or** an `owner_lever` that resolves in `his-hand-levers.json`. No unnamed vacuum. |
| **F** | For every row with `materialize: true`, count PRs matching `derived_from` that carry no label. Shrink-only baseline (today **124**). This is D3's gate. |
| **G** | Self-reference: the registry names its own predicate and its own `IF-PR-LIFECYCLE` row, and both exist. |

Wire into `institutio/governance/gates.yaml` with `paths` implicating
`institutio/governance/lifecycle.yaml`, `institutio/github/estate.yaml`, `scripts/merge-drain.py`,
`scripts/gitvs.py`, `scripts/pr-lifecycle*.py`. Cost tier cheap (offline checks only in the gate).

### `IF-PR-LIFECYCLE` — the ideal form

- **Ideal form:** every open PR in the estate carries exactly one *declared* disposition, written
  by an organ under a declared admits-predicate; every consumer derives its policy from the
  registry; and the estate's reach — how many PRs any organ can act on — is a registry fact rather
  than a code literal.
- **Probe:** `python3 scripts/check-lifecycle.py --measure`, `environment: network`,
  `extract` the *unreachable-PR* count (open PRs no organ can act on), `ideal_value: "0"`.
  Today that number is **1,298**. The offline `--check` is the gate; the probe measures reach —
  the same split IF-AMALGAMATION uses between `pr-debt-trend.py --check` and the census.
- **Owner:** Claude (registry + predicate) → the beat's typer and merge rungs (enactment).

## The arc — HEAL · EXPAND · EVOLVE

**W0 is the base and lands first.** Everything else is a consumer conversion, which is exactly why
the sequencing inverts the usual arc: the *evolve* structure has to exist before the *heals* have
anywhere to attach.

### W0 — the axis (base)

`lifecycle.yaml` + `check-lifecycle.py` (A–G) + `gates.yaml` row + `IF-PR-LIFECYCLE` row and
ledger heading. Pure declaration and pure predicate: **no outward writes**, so it lands first and
makes every later claim falsifiable.
**Predicate:** `python3 scripts/check-lifecycle.py --check` exit 0 with baselines seeded at
today's measured values (B: 4 copies, F: 124).

### HEAL — stop the false greens and the unsatisfiable seal

- **W1 — converger, not seal** (decision 4). Worklist built from **live labels**, not from the
  ledger's `lifecycle_disposition` — which alone un-excludes D3's 124, since `build_plan`'s
  `if not row.get("lifecycle_disposition")` filter makes that path structurally unable to reach
  them. `_preflight_repo` returns `(pending, skipped)`; the receipt records
  `skipped_closed` / `skipped_head_drift` / `skipped_label_drift` with `pr_key`s.
  **Predicate:** a second consecutive run reports `effect_count == 0` — the idempotent fixed point.
- **W3 — close the ledger↔label divergence** (decision 5). Materialize the 124; demote
  `legacy-preservation-marker` from `lifecycle_complete`. **Predicate:** check F divergence 0
  (today 124), and `gitvs pr-debt --check` can no longer be green while effectors see UNKNOWN.
- **W-consumers — convert the four copies.** `merge-drain.py`, `gitvs.py`,
  `pr-lifecycle-manifest.py`, `pr-lifecycle-estate-manifest.py` each import the registry loader and
  their ratchet arms. **Predicate:** checks B and C green with all four ratchets `true`.

### EXPAND — widen what an organ can actually reach

- **W2 — the delivery typer** (decision 3): an organ that types PRs satisfying `admits` as
  `lifecycle:delivery`. This is the actual unblock; `merge-policy.sh` stays the merge verdict.
  **Predicate:** `lifecycle:delivery` count > 0 **and** `merge-drain --dry-run` yields ≥ 1 MERGE
  candidate. Today both are 0 — which is why the rung has never moved a PR.
- **W5 — cohort reach.** Declare the dependabot cohort (361 PRs — the largest mechanically
  tractable slice: grouped-update supersession plus auto-merge on green). Widen `LIMEN_OWNERS`
  past `organvm,4444J99` (2 of 10 owners) and make `enumerate_open_prs(max_total=500)` **log its
  truncation** — a silent cap reads as "covered everything."
- **W6 — split the cheap probe from the expensive census.** The 20h-stale ledger is what made D1's
  seal unfalsifiable. The exhaustive census earns its cost as the exhaustiveness proof and keeps
  its cadence; the *label* facts effectors need were obtained in **18s** (measured) via `gh pr list`
  at 8-way concurrency. Add that as the live probe effectors read.

### EVOLVE — make the class unable to recur

- **W7 — wire the typer to the beat** (decision 6): one `sensors.yaml` row, held by
  `check-sensors.py`. Turns a capability into an organ.
- **W4 — file the draft lever** (decision 7): `L-PR-DRAFT-COHORT-DISPOSITION` with the measured
  530-PR cohort. Filed immediately, never on the critical path, and — per the closeout discipline —
  **not recited back in any closeout**.

```
W0 axis ──┬─→ HEAL:   W1 converge ─→ W3 materialize ─→ W-consumers convert
          ├─→ EXPAND: W2 delivery typer ─→ W5 cohort reach ─→ (drain runs)
          │           W6 cheap probe (independent)
          └─→ EVOLVE: W7 beat rung ─→ W4 lever (filed, off the critical path)
```

## Premortem

**What most plausibly makes this wrong or unwelcome?** Building the registry and stopping — an
eighth beautifully-declared axis that no effector derives from is the *same* defect one level up,
and it would be this plan reproducing the error it diagnoses. The `ratchets:` block is the guard:
each one arms only when its consumer actually converts, so an unconverted consumer is visible as
`false` rather than as a green check over four surviving copies. The second risk is scope: W2's
delivery typer touches merge behavior on a 1,298-PR estate, so it ships behind `--dry-run` with a
receipt before anything is armed, and `merge-policy.sh` remains the verdict in every path.

## Definition of done

Executable predicates, per the charter — not this prose:

1. `python3 scripts/check-lifecycle.py --check` exit 0, with ratchets `merge_drain_derives`,
   `gitvs_derives`, `estate_manifest_derives` all `true` (checks B and C green over zero copies).
2. Check F divergence count **0** (today 124) — ledger derivations and live labels agree.
3. `lifecycle:delivery` count > 0 **and** `scripts/merge-drain.py --dry-run` yields ≥ 1 MERGE
   candidate (today both 0).
4. Estate converger run twice → second run `effect_count == 0`.
5. `python3 scripts/check-ideal-forms.py --measure` reports `IF-PR-LIFECYCLE` with a **derived**
   distance, and `scripts/check-sensors.py` green with the typer's row present.
6. `L-PR-DRAFT-COHORT-DISPOSITION` present in `his-hand-levers.json` with the measured cohort.
7. `scripts/verify-scoped.sh` green on each branch; `scripts/merge-policy.sh <PR#>` per merge.

Until (3) holds, no amount of labeling drains anything — that is v1's finding, and it survives its
own corrected premise.
