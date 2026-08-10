# PSP-C03 identity and offers preflight relay

## Checkpoint contract

- Source branch: `codex/psp-c03-identity-offers-preflight`
- Stacked base: `codex/psp-p02-w03-flagship-proof-preflight`
- Exact stacked-base head at branch creation: `48bb826d875dfb905a0c5a15c64e370ab73492a7`
- Implementation anchor: the commit containing this relay on the source branch; consumers must resolve the current exact head from the draft PR before starting.
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
| PSP-P05-W04 | #2201 | gpt-5.6-mini / low | `organvm/limen`: `docs/receipts/positioning` (read effect) | Inspect existing receipts only; do not mint a fresh flagship receipt early. |
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

1. Wait for PSP-C02 and PSP-P02 to close through their sanctioned predicates and receipts.
2. Refresh the stacked base and every `C02-PROOF-*` claim from current primary evidence; narrow or withdraw any failed claim.
3. Replace provisional links with exact receipt anchors and regenerate `docs/positioning/commercial-contract.md`.
4. Split or attach PSP-P03 and PSP-P04 formal receipts exactly as their live issues require; do not reuse this preflight matrix as completion evidence.
5. Run the registry-defined leaf and chunk predicates only after dependencies are valid, integrate through the sanctioned rail, then release C04/C05 formal execution.

No outbound publishing, sending, spend, DNS, account mutation, unsupported claim, private-source disclosure, numeric public price, or contractual effect is authorized by this relay.
