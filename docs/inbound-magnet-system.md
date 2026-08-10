# Inbound Magnet System — evidence-led positioning

This is the design contract for positioning systems that let prospective clients and employers
understand what the operator has built and how to inspect it. It is not evidence of demand,
employment, commercial results, or product maturity. The public identity remains precise:

> Architected and directed by one person through a governed, multi-agent production system.

The operator builds systems that build products. Each public surface must show the system's current
state and distinguish inspectable evidence from repository assertions. The canonical authority is
the [claims ledger](positioning/claims-ledger.md); the authorship wording is governed by the
[authorship disclosure policy](positioning/authorship-disclosure-policy.md).

## Reconciliation inventory

The earlier doctrine mixed a useful inbound design with unsupported commercial, product, and
outcome assertions. This inventory records every conflict in that source and its replacement.

| Legacy source area | Conflict with the truth contract | Corrected rule |
|---|---|---|
| Thesis and front-door framing | Repository volume was treated as a portfolio of completed products and as evidence that inquiries will arrive. | Use dated, basis-labelled estate counts only; a repository is not necessarily a product, and a public surface may invite inspection without predicting demand. |
| Client and employer audience copy | It stated salary bands, an existing inbound posture, and a guaranteed parallel between a client engagement and a hire. | Name client and employer readers as audiences only. Describe capability through current systems and evidence, never a job outcome, compensation band, or existing pipeline. |
| Public-record case-study preface | It relied on a private anecdote as proof of market demand. | Keep private correspondence and lead history out of public positioning. A future public case study needs a separately adjudicated evidence row. |
| Public-record product description | It described full national implementation, a deployed operating service, collection scale, scoring performance, and runtime interfaces as established facts. | The public-safe description is: four implemented state collectors on a fifty-state architecture. The product state remains a working prototype until deployment and use are independently evidenced. Repository-reported test and infrastructure details require their labels. |
| Buyer economics and engagement ladder | It presented sector economics, exclusivity, deliverables, commercial anchors, and an ongoing service model as settled facts. | Keep offer and price hypotheses out of public positioning until the commercial-proof work records evidence. Public pages may offer a conversation or evidence link, but must not imply an operating service. |
| Proof-as-price argument | It used unlabeled test, infrastructure, deployment, and coverage language as a proxy for maturity. | A number or technical fact may appear only with its evidence status and date where applicable; bare "production-grade" wording is not proof. |
| Generator and front-door promise | It promised a continuously operating inbound engine and a steady outcome from the repository set. | The generator is a deterministic documentation tool. It may render approved positioning when invoked; it does not establish discoverability, capture, or commercial performance. |
| Team and ownership wording | It used plural builder language that obscured machine-assisted authorship. | Use the canonical authorship sentence above. Do not imply every line was manually authored or claim unverified ownership, client, or employer relationships. |

## Surface contract

`scripts/generate-positioning.py` is the source generator for the positioning pages under
`docs/positioning/`. It renders two deliberately separated artifacts:

- A public page with a current-state label, evidence statuses, buyer problem framing, and an
  inspection or contact path. Public pages contain no price anchors.
- An internal page for planning-only proposal notes. Internal notes are never input to a public
  renderer and are not proof of an offer, a client relationship, or a market result.

`scripts/sync-readme.py` uses the same seed data for the profile renderer. It permits only
verified proof on its Level-1 system cards and retains repository assertions on the linked Level-2
pages with their labels. The shared `scripts/positioning_claims.py` contract rejects the
ledger's prohibited claim classes before either renderer writes a public artifact.

## Evidence-led flow

```text
claims ledger + labelled seed data
               |
               v
positioning generator ----> Level-2 evidence pages
               |
               +---------> profile renderer / Level-1 cards
                                  |
                                  v
                         reader inspects evidence
                                  |
                                  v
                    optional, operator-controlled contact
```

The flow does not send messages, publish an identity change, change repository topics, or infer
reader intent. Contact is rendered only when an approved address is configured; otherwise the
call to action remains plain text. Any response, send, or external publication remains the
operator's decision.

## Build order

1. Add or update the claim's ledger row with dated, appropriate evidence.
2. Update the owned seed with an explicit maturity state and evidence labels.
3. Render the applicable positioning page or profile preview.
4. Run the claim-contract tests and inspect the generated copy against the ledger.
5. Route any publication, contact, offer, or evidence gap through its named owner rather than
   inferring a result from the rendered copy.

This keeps the value of the work visible: a governed production system and its inspectable
artifacts. It never substitutes a compelling story for proof.
