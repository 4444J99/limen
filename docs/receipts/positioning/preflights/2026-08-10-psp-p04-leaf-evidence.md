# PSP-P04 offer and economics preflight matrix

Status: **leaf execution open; phase closure gated by PSP-P03-W07**. PSP-P02 and PSP-P03-W01 through W06 are accepted. Independently eligible P04 leaves may merge and receipt-close after their own predicates pass; the five-reader gate blocks P03/P04 phase closure only. This matrix maps each commercial decision to its reversible implementation evidence; it is not a formal work receipt.

Canonical source: `institutio/positioning/commercial-contract.yaml`

Implemented public-offer owner: `docs/positioning/offers`, generated and checked by `scripts/positioning-offer-artifacts.py`.

| Work | Live issue | Registry model | Contract evidence | Commercial boundary | Formal integration gap |
| --- | --- | --- | --- | --- | --- |
| PSP-P04-W01 | [#2190](https://github.com/organvm/limen/issues/2190) | gpt-5.6-sol / max | `offer_ladder.items.audit`; generated `docs/positioning/offers/agentic-delivery-audit.md` | Fixed-scope, read-only diagnostic; two-to-three-week delivery envelope | Once its declared leaf dependencies close, run the live leaf predicate and attach the marked receipt. |
| PSP-P04-W02 | [#2191](https://github.com/organvm/limen/issues/2191) | gpt-5.6-terra / high | `offer_ladder.items.install`; generated `docs/positioning/offers/governance-install.md` | One team or pipeline; four-to-eight-week delivery envelope; named write boundary | After W01 closes, run the live leaf predicate and attach the marked receipt. |
| PSP-P04-W03 | [#2192](https://github.com/organvm/limen/issues/2192) | gpt-5.6-terra / high | `offer_ladder.items.retainer`; generated `docs/positioning/offers/bounded-delivery-governance-retainer.md` | Finite cadence and response envelope; no on-call or outsourced ownership | After W02 closes, run the live leaf predicate and attach the marked receipt. |
| PSP-P04-W04 | [#2193](https://github.com/organvm/limen/issues/2193) | gpt-5.6-terra / high | `qualification.rules`, `qualification.scenarios`; generated `docs/positioning/offers/qualification-and-routing.md`; validator `scripts/positioning-offer-artifacts.py` | One priority-ordered route; guarded exceptions go to human review; prohibited scopes decline | After W01-W03 close, mint the scenario receipt from the unchanged generated artifact. |
| PSP-P04-W05 | [#2194](https://github.com/organvm/limen/issues/2194) | gpt-5.6-terra / high | `economics_contract`, every offer `economics` block | Symbolic floor/target/exception ranges; no public numeric price; capacity protected | Owner must approve private anchors through HG-PRICE-ANCHORS. |
| PSP-P04-W06 | [#2195](https://github.com/organvm/limen/issues/2195) | gpt-5.6-sol / xhigh | `commercial_templates`; private owner `templates/production-systems`; focused owner test `tests/production-systems/commercial-templates.test.ts`; [draft PR #135](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/135) | Four draft-only templates; no sending, signature, liability, data, payment, or service effect | After W04/W05 close, use the registered owner rail; HG-CONTRACT remains required for any sent or executed instance. |
| PSP-P04-W07 | [#2196](https://github.com/organvm/limen/issues/2196) | gpt-5.6-sol / max | `offer_ladder.secondary`; generated `docs/positioning/offers/product-operating-partnership-review.md` | Secondary, L3-only diligence; no implied economics, custody, licence, equity, or transfer | After W04 closes, mint the boundary receipt; HG-OPERATOR-TERMS remains required before any terms. |

## Preflight verdict

The offer ladder does not overlap: Audit diagnoses; Governance Install changes one bounded workflow; the retainer sustains an accepted baseline; partnership review is a secondary diligence route. Each offer specifies entry criteria, deliverables, exclusions, timeline, evidence, economics, authority, handoff, and escalation. Numeric pricing stays in its sanctioned private owner behind symbolic range and anchor IDs.

Formal rule: leaf acceptance follows each leaf's declared dependencies and predicate; PSP-P03-W07 blocks P03/P04 phase closure only. This preflight does not claim current live issue state.
