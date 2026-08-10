# PSP-C03 identity and offers preflight relay

## Checkpoint contract

- Source branch: `codex/psp-c03-identity-offers-preflight`
- Stacked base: `codex/psp-p02-w03-flagship-proof-preflight`
- Exact stacked-base head at branch creation: `48bb826d875dfb905a0c5a15c64e370ab73492a7`
- Core-contract checkpoint: `2a1a01149adc2c036b7d3da624740a78d140a672`
- Draft stacked PR: [#2312](https://github.com/organvm/limen/pull/2312), labeled `lifecycle:blocked` on PSP-C02
- Continuation anchor: consumers must resolve the current exact PR head and confirm it descends from the core-contract checkpoint before starting.
- Canonical source: `institutio/positioning/commercial-contract.yaml`
- Validation: `python3 scripts/positioning-commercial-contract.py --check`
- State: preflight is blocked on PSP-C02. PSP-P03/P04 leaves remain open; their formal receipt predicates have not run.

The checkpoint ratifies the strategy shape, not C02 evidence: production-systems architect; three audience contracts; L1/L2/L3 progressive disclosure; bounded Audit → Install → Retainer sequence; secondary partnership diligence; qualification, symbolic pricing ranges, capacity rules, templates, authority, handoff, and anti-takeover language.

## Exact successor handoff: PSP-C04

- Registry chunk: **PSP-C04**
- Canonical conductor: **gpt-5.6-sol / xhigh** (Sol / xhigh)
- Formal dependency: PSP-C03
- Parallel phases: PSP-P05 and PSP-P06
- Safe preflight rule: successors may create isolated draft branches, read this contract, inspect the named target paths, inventory reusable evidence and components, and draft placeholder-backed plans or private mocks. They must not publish, change a live public surface, run formal leaf predicates, close leaves, or claim C03 evidence as ratified before PSP-C03 formally closes.

| Leaf | Issue | Exact model | Registered target and paths | Safe preflight before C03 closure |
| --- | --- | --- | --- | --- |
| PSP-P05-W01 | #2198 | gpt-5.6-sol / max | `organvm/limen`: `docs/positioning/proof`, `docs/receipts` | Inventory source-package inputs and draft the report skeleton with provisional claim IDs. |
| PSP-P05-W02 | #2199 | gpt-5.6-terra / high | `organvm/limen`: `docs/positioning`, `scripts`, `link-surfaces.json` | Read-only surface reconciliation and a no-write replacement map. |
| PSP-P05-W03 | #2200 | gpt-5.6-terra / high | `organvm/limen`: `docs/positioning/proof`, `docs/receipts` | Inventory cost/failure evidence and mark every missing denominator or private input. |
| PSP-P05-W04 | #2201 | gpt-5.4-mini / low | `organvm/limen`: `docs/receipts/positioning` (read effect) | Inspect existing receipts only; do not mint a fresh flagship receipt early. |
| PSP-P05-W05 | #2202 | gpt-5.6-terra / high | `organvm/limen`: `web`, `docs/positioning/proof`, `assets` | Draft a non-published demo plan and bind each scene to provisional claim IDs. |
| PSP-P05-W06 | #2203 | gpt-5.6-terra / high | `organvm/limen`: `docs/positioning/proof`, `docs/receipts` | Inventory candidate external validation objects without soliciting or publishing them. |
| PSP-P06-W01 | #2205 | gpt-5.6-terra / high | `organvm/portfolio`: `docs/design`, `design` | Draft a taste brief from the identity, audience, threat, and disclosure contracts. |
| PSP-P06-W02 | #2206 | gpt-5.6-terra / high | `organvm/portfolio`: `docs`, `content` | Map L1/L2/L3 content and navigation with provisional evidence slots. |
| PSP-P06-W03 | #2207 | gpt-5.6-sol / max | `organvm/portfolio`: `design`, `docs/design` | Draft target-reader flows for clients, recruiters/executives, and gated partners. |
| PSP-P06-W04 | #2208 | gpt-5.6-terra / high | `organvm/portfolio`: `src/components`, `src/content`, `docs` | Inventory reusable disclosure and evidence components; avoid public copy changes. |
| PSP-P06-W05 | #2209 | gpt-5.6-terra / high | `organvm/portfolio`: `src/styles`, `web/tokens` | Inventory tokens and draft non-published mappings to the taste brief. |
| PSP-P06-W06 | #2210 | gpt-5.6-luna / medium | `organvm/portfolio`: `src`, `tests` | Inspect accessibility, responsive, performance, and reduced-motion baselines only. |
| PSP-P06-W07 | #2211 | gpt-5.6-sol / max (read) | `organvm/portfolio`: `docs/receipts`, `tests` | Prepare the QA rubric; do not issue a final visual or comprehension verdict early. |

C04 integration input after C03 closure: replace provisional claim IDs with C02-ratified anchors, consume the exact identity/audience/narrative hierarchy, and preserve the rule that the partnership door does not appear at L1 or L2.

## Exact successor handoff: PSP-C05

- Registry chunk: **PSP-C05**
- Canonical conductor: **gpt-5.6-sol / max** (Sol / max)
- Formal dependency: PSP-C03
- Phase: PSP-P11
- Safe preflight rule: successors may create an isolated draft branch in the registered repository, inspect the named paths, derive schemas/runbook outlines from the bounded offers, and design synthetic-only acceptance fixtures. They must not ingest client data, create a live client workspace, send terms, imply an engagement, run formal leaf predicates, or close leaves before PSP-C03 formally closes.

| Leaf | Issue | Exact model | Registered target and paths | Safe preflight before C03 closure |
| --- | --- | --- | --- | --- |
| PSP-P11-W01 | #2249 | gpt-5.6-sol / xhigh | `organvm-iii-ergon/collaboration-operations-platform`: `security`, `schemas`, `playbooks/production-systems` | Draft a read-only intake threat model and synthetic schema fixtures. |
| PSP-P11-W02 | #2250 | gpt-5.6-sol / max | same repository: `playbooks/production-systems`, `rubrics` | Map the Audit deliverables, verdicts, uncertainties, and acceptance rubric. |
| PSP-P11-W03 | #2251 | gpt-5.6-terra / high | same repository: `templates/production-systems`, `rubrics` | Draft report and executive-verdict templates with symbolic claim/evidence fields. |
| PSP-P11-W04 | #2252 | gpt-5.6-terra / high | same repository: `playbooks/production-systems`, `templates` | Draft the one-team/pipeline Governance Install runbook and handoff skeleton. |
| PSP-P11-W05 | #2253 | gpt-5.6-terra / high | same repository: `playbooks/production-systems`, `templates` | Draft the finite-cadence retainer contract; exclude on-call and unlimited delivery. |
| PSP-P11-W06 | #2254 | gpt-5.6-sol / xhigh | same repository: `schemas`, `workspaces`, `tests` | Design private-workspace boundaries and synthetic logs only; ingest no client material. |
| PSP-P11-W07 | #2255 | gpt-5.6-terra / high | same repository: `playbooks`, `checklists`, `receipts` | Draft QA, acceptance, handoff, access-removal, and closeout checklists. |
| PSP-P11-W08 | #2256 | gpt-5.6-sol / xhigh | same repository: `templates`, `security`, `playbooks` | Draft consent and sanitization gates with synthetic proof; publish nothing. |

C05 integration input after C03 closure: materialize the proposal/SOW blueprints under their registered owner, preserve the Audit/Install/Retainer authority boundaries, and require HG-PRICE-ANCHORS, HG-CONTRACT, and HG-OPERATOR-TERMS for their respective effects.

## Formal C03 integration relay

### Bounded-readiness snapshot

Observed from the live remote on 2026-08-10 at approximately 20:08 UTC:

- C03 draft PR [#2312](https://github.com/organvm/limen/pull/2312) remains open and draft at exact head `b5bc01585a10615e85e1ef5b31a2356c24fb9bc9`. Its exact-head contract validator and 12-test regression suite passed, and its remote Python, worker, web, and `pr-gate` checks succeeded. That is preflight evidence only.
- The stacked base branch has advanced to `68b65fa233dcb163d45e066537eb06d0c6569e3b`. Do not rebase or force-push C03 merely to chase it.
- C02 hardening draft PR [#2314](https://github.com/organvm/limen/pull/2314) is anchored at `b65f2c8ad95a8a3007ad7d1541e1b11228981534`; its adoption does not close PSP-P02.
- The smallest live dependency chain is [PR #2141](https://github.com/organvm/limen/pull/2141) → PSP-P01-W03 [#2169](https://github.com/organvm/limen/issues/2169) → PSP-P01-W05 [#2171](https://github.com/organvm/limen/issues/2171) → PSP-P01 [#2166](https://github.com/organvm/limen/issues/2166) → PSP-P02 [#2172](https://github.com/organvm/limen/issues/2172). Until that chain closes through its own receipts, every PSP-P03 and PSP-P04 leaf stays open.
- The preflight matrix is not a positioning receipt, a phase receipt, or evidence for issue closure.

### Immutable downstream anchors

Preserve these prepared descendants while C03 is blocked:

- C04 controller draft [#2313](https://github.com/organvm/limen/pull/2313): `codex/psp-c04-proof-experience-preflight@e9c2db2360acd5fd57a48d063e64990dc8f3a768`.
- C04 public-portfolio target draft [organvm-vii-kerygma/portfolio#220](https://github.com/organvm-vii-kerygma/portfolio/pull/220): exact head `fa86b67a7283c15ab801302ffac655c30898b6a1`.
- C05 relay draft [#2315](https://github.com/organvm/limen/pull/2315): `codex/psp-c05-delivery-os-preflight-relay@b62f83f192112f94e73735e06a765b3ad6d97d9b`.
- C05 private delivery target [organvm-iii-ergon/collaboration-operations-platform#135](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/135): exact head `4ae8e81665e35e6a5d403a3e13935021ce6544ec`.

Those heads are receipt anchors, not branches to rewrite. After formal C03 closure, each successor owner may merge the accepted C03/main head once through its own sanctioned rail. The PSP-P06 rows above reflect the current local registry alias `organvm/portfolio`; when the adopted C02 correction lands, refresh them once to the immutable repository identity `organvm-vii-kerygma/portfolio` and extend the validator to reject alias regression.

### Activation predicate

Begin formal C03 integration only when all four observations agree on the same accepted P02 state:

1. PSP-P02 issue [#2172](https://github.com/organvm/limen/issues/2172) is closed.
2. `python3 scripts/positioning-program.py --verify-phase PSP-P02` exits successfully at the exact head recorded by the final P02 phase receipt.
3. `python3 scripts/positioning-program.py --verify-remote` passes at that same head.
4. `python3 scripts/positioning-program.py --ready --json` includes `PSP-P03-W01` with its registry assignment `gpt-5.6-sol / max`.

If any observation fails or disagrees, perform no C03 mutation and do not repeat already-green C03 verification. Re-query only after the dependency state changes.

### One-time evidence refresh without history rewriting

Once the activation predicate is true:

1. Fetch once and resolve the exact `organvm/limen` head from the final PSP-P02 phase receipt.
2. Confirm that the intended accepted base contains that receipt head with `git merge-base --is-ancestor <P02-RECEIPT-HEAD> origin/main`. If it does not, stop rather than guessing at a base.
3. Merge `origin/main` into this isolated branch with a normal merge; do not rebase, force-push, or mutate C02 worktrees or branches. Retarget PR #2312 to `main` only after the ancestry check succeeds.
4. Refresh the final claims ledger, flagship proof set, flagship evidence packets, research adjudication, correction protocol, current profile README, and authorship-policy head from primary evidence. Promote, narrow, or withdraw each claim independently; never blanket-promote `provisional_c02` claims.
5. Apply the adopted portfolio repository correction, replace provisional evidence links with exact receipt URLs and heads, transition the contract from dependency-blocked to its ratified state, regenerate `docs/positioning/commercial-contract.md`, and update the validator/tests for the ratified state.
6. Materialize the acceptance artifacts still absent from this draft: identity-surface reconciliation, role-to-proof/interview map, five-reader narrative protocol and anonymized verdict, private pricing-anchor digest, bounded proposal/SOW templates in their registered repository, and product-partnership boundary verdict. No synthetic result may stand in for the five-reader verdict.
7. Run `python3 scripts/positioning-commercial-contract.py --check`, its focused test file, and `scripts/verify-scoped.sh` once for the changed exact tree. Commit and push one coherent refresh batch.

### Merge and formal receipt rail

An unmerged draft is not completion evidence. After the refreshed artifacts and acceptance-specific predicates are green, remove `lifecycle:blocked`, mark PR #2312 ready, and use the no-bypass integration rail:

```text
scripts/merge-policy.sh 2312 --expected-head <EXACT-C03-HEAD>
scripts/await-pr.sh 2312 --merge
```

Never use admin merge, force-push, or a direct `main` write. If a leaf needs a new tracked artifact after that merge, land it through one bounded follow-on PR and cite that merge head; never close against draft-only content. PSP-P04-W06 also requires its templates to merge through the registered external repository's sanctioned rail before its receipt can succeed.

Process only leaves emitted by `python3 scripts/positioning-program.py --ready --json`, in this dependency order:

1. PSP-P03: W01 → W02 → W03 → W04 and W05 → W06 → W07; then phase PSP-P03 [#2181](https://github.com/organvm/limen/issues/2181).
2. PSP-P04, only after PSP-P03 closes: W01 → W02 → W03 → W04 and W05 → W06 and W07; then phase PSP-P04 [#2189](https://github.com/organvm/limen/issues/2189).

For each ready leaf, preserve its exact live model assignment and use this receipt sequence:

```text
python3 scripts/positioning-program.py --seed <WORK-ID>
limen conduct submit --packet <WORK-PACKET>
<run the live issue's acceptance-specific predicate; never use --verify-work here>
limen conduct report <LEASE> --receipt <RUN-RECEIPT>
python3 scripts/positioning-program.py --receipt-template <WORK-ID>
<post the completed positioning receipt after <!-- positioning-receipt:<WORK-ID> --> on the live issue>
python3 scripts/positioning-program.py --verify-work <WORK-ID>
gh issue close <ISSUE> --repo organvm/limen
```

Each positioning receipt must use the current acceptance digest, record `outcome: succeeded`, cite the accepted exact head for every observed repository, list the actual changed paths, include a successful non-circular predicate with output hash and time, use durable HTTPS evidence URLs, and state rollback. Submit transitions through the conduct broker; never edit `tasks.yaml`.

After every child issue in a phase is closed:

```text
python3 scripts/positioning-program.py --phase-proof <PHASE-ID>
python3 scripts/positioning-program.py --phase-receipt-template <PHASE-ID>
<post the completed phase receipt after <!-- positioning-phase-receipt:<PHASE-ID> --> on the phase issue>
python3 scripts/positioning-program.py --verify-phase <PHASE-ID>
gh issue close <PHASE-ISSUE> --repo organvm/limen
```

Run the phase proof before minting its receipt and verify the phase while its issue is still open. After both phases close, verify `python3 scripts/positioning-program.py --chunk PSP-C03`, `--verify-remote`, and `--ready --json`; release C04/C05 formal work only if the registry now emits their first leaves.

### Open human and external gates

- `HG-PRICE-ANCHORS` (owner [#267](https://github.com/organvm/limen/issues/267)) controls the private floor, target, and exception amounts. Public artifacts retain symbolic IDs only; no numeric price belongs in this branch, relay, PR, or receipt.
- `HG-CONTRACT` controls sending, signature, liability, data, payment, and service commitments. Draft templates may be prepared, but they create no contractual effect.
- `HG-OPERATOR-TERMS` controls equity, licence, revenue, custody, access, and product-transfer terms. The partnership path remains secondary, L3-only, and non-offer until approved.
- PSP-P03-W07 requires five blinded, target-like readers to identify role, buyer, problem, proof, and next step without prompting. Do not solicit them under this preflight's no-outbound boundary or substitute an internal prose judgment.

No outbound publishing, sending, spend, DNS, account mutation, unsupported claim, private-source disclosure, numeric public price, or contractual effect is authorized by this relay.
