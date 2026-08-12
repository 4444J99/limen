# Production-Systems Program issue index

Generated from `institutio/positioning/program.yaml` and `institutio/positioning/github-map.json`. Do not edit by hand.

- Phases: **15**
- Atomic work packets: **111**
- Total projected GitHub objects: **127**
- Root model / effort: **`gpt-5.6-sol` / `ultra`**

## Phases

| Phase | Issue | Chunk(s) | Model | Effort | Leaves | Depends on | Exit gate |
|---|---:|---|---|---|---:|---|---|
| `PSP-P00` Program control plane | [#2158](https://github.com/organvm/limen/issues/2158) | `PSP-C00` | `gpt-5.6-sol` | `max` | 7 | — | All P00 leaves close and remote parity reports zero missing, duplicate, or orphan markers. |
| `PSP-P01` Foundation repair and upstream integration | [#2166](https://github.com/organvm/limen/issues/2166) | `PSP-C01` | `gpt-5.6-terra` | `high` | 5 | [#2158](https://github.com/organvm/limen/issues/2158) | PRs 2136 and 2141 have terminal owners; canonical sources are reconciled and baseline receipts are frozen. |
| `PSP-P02` Truth and evidence control plane | [#2172](https://github.com/organvm/limen/issues/2172) | `PSP-C02` | `gpt-5.6-sol` | `max` | 8 | [#2166](https://github.com/organvm/limen/issues/2166) | All selected flagships have evidence packets and every material or disputed claim has separate measurement, inference, implication, prominence, source, date, and staleness verdicts. |
| `PSP-P03` Position, narrative, and audience architecture | [#2181](https://github.com/organvm/limen/issues/2181) | `PSP-C03` | `gpt-5.6-sol` | `max` | 7 | [#2172](https://github.com/organvm/limen/issues/2172) | Target readers understand what is offered, why it is credible, and what to do next without an oral explanation. |
| `PSP-P04` Offer and commercial architecture | [#2189](https://github.com/organvm/limen/issues/2189) | `PSP-C03` | `gpt-5.6-sol` | `max` | 7 | [#2181](https://github.com/organvm/limen/issues/2181) | Audit, install, and retainer each have scope, exclusions, qualification, artifacts, economics, and contract boundaries. |
| `PSP-P05` Proof-production program | [#2197](https://github.com/organvm/limen/issues/2197) | `PSP-C04` | `gpt-5.6-sol` | `xhigh` | 6 | [#2172](https://github.com/organvm/limen/issues/2172), [#2181](https://github.com/organvm/limen/issues/2181), [#2189](https://github.com/organvm/limen/issues/2189) | The six declared proof classes exist, are public-safe, and link back to current evidence rows. |
| `PSP-P06` Portfolio experience and progressive disclosure | [#2204](https://github.com/organvm/limen/issues/2204) | `PSP-C04` | `gpt-5.6-sol` | `xhigh` | 7 | [#2181](https://github.com/organvm/limen/issues/2181), [#2197](https://github.com/organvm/limen/issues/2197) | Tested designs satisfy progressive disclosure, audience routing, accessibility, performance, and visual quality. |
| `PSP-P07` Public surfaces and deployment | [#2212](https://github.com/organvm/limen/issues/2212) | `PSP-C06` | `gpt-5.6-terra` | `high` | 9 | [#2172](https://github.com/organvm/limen/issues/2172), [#2181](https://github.com/organvm/limen/issues/2181), [#2197](https://github.com/organvm/limen/issues/2197), [#2204](https://github.com/organvm/limen/issues/2204) | All tracked public surfaces are coherent, live, linked, rollback-safe, and verified in rendered form. |
| `PSP-P08` Inbound capture and private lead operations | [#2222](https://github.com/organvm/limen/issues/2222) | `PSP-C07` | `gpt-5.6-sol` | `xhigh` | 7 | [#2189](https://github.com/organvm/limen/issues/2189), [#2212](https://github.com/organvm/limen/issues/2212) | Client and recruiter synthetic leads traverse capture, classification, routing, drafting, and reporting while no-send stays enforced. |
| `PSP-P09` Proof-led content and distribution | [#2230](https://github.com/organvm/limen/issues/2230) | `PSP-C08` | `gpt-5.6-terra` | `high` | 8 | [#2197](https://github.com/organvm/limen/issues/2197), [#2212](https://github.com/organvm/limen/issues/2212), [#2222](https://github.com/organvm/limen/issues/2222) | The flagship report and derived series are staged, owner-published where approved, measured, and linked to qualified capture. |
| `PSP-P10` Qualification, conversation, and conversion system | [#2239](https://github.com/organvm/limen/issues/2239) | `PSP-C09`, `PSP-C10` | `gpt-5.6-sol` | `xhigh` | 8 | [#2189](https://github.com/organvm/limen/issues/2189), [#2222](https://github.com/organvm/limen/issues/2222), [#2230](https://github.com/organvm/limen/issues/2230) | Client and recruiter playbooks, pipeline stages, proposal rules, objection capture, and the 90-day experiment work end to end. |
| `PSP-P11` Service-delivery operating system | [#2248](https://github.com/organvm/limen/issues/2248) | `PSP-C05` | `gpt-5.6-sol` | `max` | 8 | [#2189](https://github.com/organvm/limen/issues/2189) | A synthetic engagement traverses intake, evidence, analysis, verdict, implementation, QA, handoff, and closeout under the declared boundaries. |
| `PSP-P12` External validation and first commercial proof | [#2257](https://github.com/organvm/limen/issues/2257) | `PSP-C10` | `gpt-5.6-sol` | `max` | 6 | [#2230](https://github.com/organvm/limen/issues/2230), [#2248](https://github.com/organvm/limen/issues/2248) | The first audit outcome, external proof, and claims refresh are complete or the wedge has an evidence-backed invalidation receipt. |
| `PSP-P13` Governed foundry and domain-operator handoff | [#2264](https://github.com/organvm/limen/issues/2264) | `PSP-C11` | `gpt-5.6-sol` | `max` | 9 | [#2172](https://github.com/organvm/limen/issues/2172), [#2189](https://github.com/organvm/limen/issues/2189), [#2248](https://github.com/organvm/limen/issues/2248), [#2257](https://github.com/organvm/limen/issues/2257) | The entire product estate is scored and one transfer reaches observed operation or an evidence-backed no-go decision. |
| `PSP-P14` Return loop, measurement, rollback, and Omega | [#2274](https://github.com/organvm/limen/issues/2274) | `PSP-C12` | `gpt-5.6-sol` | `ultra` | 9 | [#2212](https://github.com/organvm/limen/issues/2212), [#2222](https://github.com/organvm/limen/issues/2222), [#2230](https://github.com/organvm/limen/issues/2230), [#2239](https://github.com/organvm/limen/issues/2239), [#2248](https://github.com/organvm/limen/issues/2248), [#2257](https://github.com/organvm/limen/issues/2257), [#2264](https://github.com/organvm/limen/issues/2264) | Two unchanged remote checks prove complete issue coverage, current claims, healthy surfaces, closed loops, and terminal receipts. |

## PSP-P00 — Program control plane

One validated source graph projects a complete, non-duplicative, cross-agent issue system.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P00-W01` Commit the canonical alpha-to-omega program manifest | [#2159](https://github.com/organvm/limen/issues/2159) | `PSP-C00` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | — |
| `PSP-P00-W02` Build structural validation and dependency-cycle detection | [#2160](https://github.com/organvm/limen/issues/2160) | `PSP-C00` | `gpt-5.6-luna` | `medium` | `organvm/limen` | `routine` | `write` | [#2159](https://github.com/organvm/limen/issues/2159) |
| `PSP-P00-W03` Build idempotent GitHub milestone, label, and issue projection | [#2161](https://github.com/organvm/limen/issues/2161) | `PSP-C00` | `gpt-5.6-sol` | `xhigh` | `organvm/limen` | `deep` | `external` | [#2160](https://github.com/organvm/limen/issues/2160) |
| `PSP-P00-W04` Publish cross-agent work-packet and relay contracts | [#2162](https://github.com/organvm/limen/issues/2162) | `PSP-C00` | `gpt-5.6-sol` | `xhigh` | `organvm/limen` | `deep` | `write` | [#2159](https://github.com/organvm/limen/issues/2159) |
| `PSP-P00-W05` Expose ready-work and model-assigned packet seeds | [#2163](https://github.com/organvm/limen/issues/2163) | `PSP-C00` | `gpt-5.6-sol` | `xhigh` | `organvm/limen` | `deep` | `write` | [#2160](https://github.com/organvm/limen/issues/2160) |
| `PSP-P00-W06` Prove issue-map parity and zero orphan program work | [#2164](https://github.com/organvm/limen/issues/2164) | `PSP-C00` | `gpt-5.4-mini` | `low` | `organvm/limen` | `routine` | `read` | [#2161](https://github.com/organvm/limen/issues/2161), [#2163](https://github.com/organvm/limen/issues/2163) |
| `PSP-P00-W07` Route ready expert-positioning work into fresh Codex tasks | [#2165](https://github.com/organvm/limen/issues/2165) | `PSP-C00` | `gpt-5.6-sol` | `max` | `organvm/limen` | `deep` | `write` | [#2163](https://github.com/organvm/limen/issues/2163), [#2164](https://github.com/organvm/limen/issues/2164) |

## PSP-P01 — Foundation repair and upstream integration

Existing truth and custody foundations merge on green CI and become the program's baseline.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P01-W01` Fix the wall-clock-dependent throughput-governor test | [#2167](https://github.com/organvm/limen/issues/2167) | `PSP-C01` | `gpt-5.6-luna` | `medium` | `organvm/limen` | `routine` | `write` | [#2164](https://github.com/organvm/limen/issues/2164) |
| `PSP-P01-W02` Land the positioning truth-reconciliation foundation | [#2168](https://github.com/organvm/limen/issues/2168) | `PSP-C01` | `gpt-5.6-sol` | `xhigh` | `organvm/limen` | `deep` | `external` | [#2167](https://github.com/organvm/limen/issues/2167) |
| `PSP-P01-W03` Land encrypted custody for private evidence artifacts | [#2169](https://github.com/organvm/limen/issues/2169) | `PSP-C01` | `gpt-5.6-sol` | `xhigh` | `organvm/limen` | `deep` | `external` | [#2167](https://github.com/organvm/limen/issues/2167) |
| `PSP-P01-W04` Reconcile old positioning doctrine and generators against the new truth contract | [#2170](https://github.com/organvm/limen/issues/2170) | `PSP-C01` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2168](https://github.com/organvm/limen/issues/2168) |
| `PSP-P01-W05` Freeze the post-merge public-surface baseline | [#2171](https://github.com/organvm/limen/issues/2171) | `PSP-C01` | `gpt-5.4-mini` | `low` | `organvm/limen` | `routine` | `read` | [#2168](https://github.com/organvm/limen/issues/2168), [#2169](https://github.com/organvm/limen/issues/2169), [#2170](https://github.com/organvm/limen/issues/2170) |

## PSP-P02 — Truth and evidence control plane

Every public statement is reproducible, classified, dated, bounded, and reversible.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P02-W01` Discover every organization and repository the owner controls | [#2173](https://github.com/organvm/limen/issues/2173) | `PSP-C02` | `gpt-5.4-mini` | `low` | `organvm/limen` | `routine` | `read` | [#2171](https://github.com/organvm/limen/issues/2171) |
| `PSP-P02-W02` Classify the full estate by role, maturity, visibility, and public relevance | [#2174](https://github.com/organvm/limen/issues/2174) | `PSP-C02` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2173](https://github.com/organvm/limen/issues/2173) |
| `PSP-P02-W03` Score and ratify the flagship proof set | [#2175](https://github.com/organvm/limen/issues/2175) | `PSP-C02` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2174](https://github.com/organvm/limen/issues/2174) |
| `PSP-P02-W04` Build a complete evidence packet for every selected flagship | [#2176](https://github.com/organvm/limen/issues/2176) | `PSP-C02` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2175](https://github.com/organvm/limen/issues/2175) |
| `PSP-P02-W05` Make every material metric and claim reproducible | [#2177](https://github.com/organvm/limen/issues/2177) | `PSP-C02` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2176](https://github.com/organvm/limen/issues/2176) |
| `PSP-P02-W06` Enforce claim policy, staleness, and privacy in generation gates | [#2178](https://github.com/organvm/limen/issues/2178) | `PSP-C02` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2177](https://github.com/organvm/limen/issues/2177) |
| `PSP-P02-W07` Establish public correction, withdrawal, and source-change protocol | [#2179](https://github.com/organvm/limen/issues/2179) | `PSP-C02` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2178](https://github.com/organvm/limen/issues/2178) |
| `PSP-P02-W08` Adjudicate research criticisms against the live profile and primary sources | [#2180](https://github.com/organvm/limen/issues/2180) | `PSP-C02` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2173](https://github.com/organvm/limen/issues/2173), [#2177](https://github.com/organvm/limen/issues/2177) |

## PSP-P03 — Position, narrative, and audience architecture

One legible identity and two audience doors communicate authority without scale theater or takeover threat.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P03-W01` Ratify the production-systems architect identity contract | [#2182](https://github.com/organvm/limen/issues/2182) | `PSP-C03` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2177](https://github.com/organvm/limen/issues/2177), [#2178](https://github.com/organvm/limen/issues/2178), [#2180](https://github.com/organvm/limen/issues/2180) |
| `PSP-P03-W02` Define the client, recruiter, and deeper operator jobs-to-be-done | [#2183](https://github.com/organvm/limen/issues/2183) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2182](https://github.com/organvm/limen/issues/2182) |
| `PSP-P03-W03` Write the ten-second, five-minute, and diligence narrative ladder | [#2184](https://github.com/organvm/limen/issues/2184) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2183](https://github.com/organvm/limen/issues/2183) |
| `PSP-P03-W04` Create the client-facing narrative and expensive-problem map | [#2185](https://github.com/organvm/limen/issues/2185) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2184](https://github.com/organvm/limen/issues/2184) |
| `PSP-P03-W05` Create the recruiter-facing narrative and role map | [#2186](https://github.com/organvm/limen/issues/2186) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2184](https://github.com/organvm/limen/issues/2184) |
| `PSP-P03-W06` Design language that reduces the spy or takeover threat response | [#2187](https://github.com/organvm/limen/issues/2187) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2185](https://github.com/organvm/limen/issues/2185), [#2186](https://github.com/organvm/limen/issues/2186) |
| `PSP-P03-W07` Run blinded target-reader comprehension and trust tests | [#2188](https://github.com/organvm/limen/issues/2188) | `PSP-C03` | `gpt-5.4-mini` | `low` | `organvm/limen` | `routine` | `read` | [#2187](https://github.com/organvm/limen/issues/2187) |

## PSP-P04 — Offer and commercial architecture

The commercial wedge is sellable, bounded, economically coherent, and expandable without becoming unbounded consulting.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P04-W01` Productize the Agentic Delivery Audit | [#2190](https://github.com/organvm/limen/issues/2190) | `PSP-C03` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2185](https://github.com/organvm/limen/issues/2185), [#2176](https://github.com/organvm/limen/issues/2176) |
| `PSP-P04-W02` Productize the Governance Install | [#2191](https://github.com/organvm/limen/issues/2191) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2190](https://github.com/organvm/limen/issues/2190) |
| `PSP-P04-W03` Define the bounded delivery-governance retainer | [#2192](https://github.com/organvm/limen/issues/2192) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2191](https://github.com/organvm/limen/issues/2191) |
| `PSP-P04-W04` Define qualification, disqualification, and escalation criteria | [#2193](https://github.com/organvm/limen/issues/2193) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2190](https://github.com/organvm/limen/issues/2190), [#2191](https://github.com/organvm/limen/issues/2191), [#2192](https://github.com/organvm/limen/issues/2192) |
| `PSP-P04-W05` Model internal pricing, capacity, and discount guardrails | [#2194](https://github.com/organvm/limen/issues/2194) | `PSP-C03` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2190](https://github.com/organvm/limen/issues/2190), [#2191](https://github.com/organvm/limen/issues/2191), [#2192](https://github.com/organvm/limen/issues/2192) |
| `PSP-P04-W06` Create proposal, SOW, and commercial-decision templates | [#2195](https://github.com/organvm/limen/issues/2195) | `PSP-C03` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2193](https://github.com/organvm/limen/issues/2193), [#2194](https://github.com/organvm/limen/issues/2194) |
| `PSP-P04-W07` Define the product-partnership offer without making it a front-door distraction | [#2196](https://github.com/organvm/limen/issues/2196) | `PSP-C03` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2193](https://github.com/organvm/limen/issues/2193) |

## PSP-P05 — Proof-production program

High-value claims are demonstrated through compact, reproducible proof objects rather than volume theater.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P05-W01` Publish the Limen engineering report source package | [#2198](https://github.com/organvm/limen/issues/2198) | `PSP-C04` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2177](https://github.com/organvm/limen/issues/2177), [#2184](https://github.com/organvm/limen/issues/2184), [#2190](https://github.com/organvm/limen/issues/2190) |
| `PSP-P05-W02` Reconcile every public surface against the claims contract | [#2199](https://github.com/organvm/limen/issues/2199) | `PSP-C04` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2198](https://github.com/organvm/limen/issues/2198), [#2178](https://github.com/organvm/limen/issues/2178) |
| `PSP-P05-W03` Produce cost-per-task and failure-mode analysis | [#2200](https://github.com/organvm/limen/issues/2200) | `PSP-C04` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2198](https://github.com/organvm/limen/issues/2198) |
| `PSP-P05-W04` Create fresh test-reproduction receipts for flagship claims | [#2201](https://github.com/organvm/limen/issues/2201) | `PSP-C04` | `gpt-5.4-mini` | `low` | `organvm/limen` | `routine` | `read` | [#2176](https://github.com/organvm/limen/issues/2176) |
| `PSP-P05-W05` Build a public-safe Limen architecture demonstration | [#2202](https://github.com/organvm/limen/issues/2202) | `PSP-C04` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2198](https://github.com/organvm/limen/issues/2198), [#2174](https://github.com/organvm/limen/issues/2174) |
| `PSP-P05-W06` Produce external validation objects | [#2203](https://github.com/organvm/limen/issues/2203) | `PSP-C04` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2201](https://github.com/organvm/limen/issues/2201), [#2202](https://github.com/organvm/limen/issues/2202) |

## PSP-P06 — Portfolio experience and progressive disclosure

The public experience feels precise and premium while the estate's density remains available on demand.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P06-W01` Establish the design context and taste brief | [#2205](https://github.com/organvm/limen/issues/2205) | `PSP-C04` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2184](https://github.com/organvm/limen/issues/2184), [#2198](https://github.com/organvm/limen/issues/2198) |
| `PSP-P06-W02` Model the content and navigation architecture | [#2206](https://github.com/organvm/limen/issues/2206) | `PSP-C04` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2205](https://github.com/organvm/limen/issues/2205), [#2183](https://github.com/organvm/limen/issues/2183) |
| `PSP-P06-W03` Design L1, L2, and L3 progressive-disclosure flows | [#2207](https://github.com/organvm/limen/issues/2207) | `PSP-C04` | `gpt-5.6-sol` | `max` | `organvm-vii-kerygma/portfolio` | `frontier_review` | `write` | [#2206](https://github.com/organvm/limen/issues/2206) |
| `PSP-P06-W04` Define reusable components and evidence-bound content interfaces | [#2208](https://github.com/organvm/limen/issues/2208) | `PSP-C04` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2207](https://github.com/organvm/limen/issues/2207), [#2178](https://github.com/organvm/limen/issues/2178) |
| `PSP-P06-W05` Adopt the approved estate design tokens without flattening surface character | [#2209](https://github.com/organvm/limen/issues/2209) | `PSP-C04` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2208](https://github.com/organvm/limen/issues/2208) |
| `PSP-P06-W06` Verify accessibility, responsiveness, performance, and reduced motion | [#2210](https://github.com/organvm/limen/issues/2210) | `PSP-C04` | `gpt-5.6-luna` | `medium` | `organvm-vii-kerygma/portfolio` | `routine` | `write` | [#2208](https://github.com/organvm/limen/issues/2208), [#2209](https://github.com/organvm/limen/issues/2209) |
| `PSP-P06-W07` Run visual and comprehension QA with target-like users | [#2211](https://github.com/organvm/limen/issues/2211) | `PSP-C04` | `gpt-5.6-sol` | `max` | `organvm-vii-kerygma/portfolio` | `frontier_review` | `read` | [#2210](https://github.com/organvm/limen/issues/2210) |

## PSP-P07 — Public surfaces and deployment

Every identity and proof surface derives from the same truth while retaining a reversible release path.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P07-W01` Preserve, audit, and evolve the personal GitHub profile front door | [#2213](https://github.com/organvm/limen/issues/2213) | `PSP-C06` | `gpt-5.6-terra` | `high` | `4444J99/4444J99` | `deep` | `write` | [#2180](https://github.com/organvm/limen/issues/2180), [#2184](https://github.com/organvm/limen/issues/2184), [#2199](https://github.com/organvm/limen/issues/2199), [#2208](https://github.com/organvm/limen/issues/2208) |
| `PSP-P07-W02` Rebuild the organization profile as an estate map | [#2214](https://github.com/organvm/limen/issues/2214) | `PSP-C06` | `gpt-5.6-terra` | `high` | `organvm/.github` | `deep` | `write` | [#2174](https://github.com/organvm/limen/issues/2174), [#2184](https://github.com/organvm/limen/issues/2184) |
| `PSP-P07-W03` Implement and deploy the canonical portfolio site | [#2215](https://github.com/organvm/limen/issues/2215) | `PSP-C06` | `gpt-5.6-sol` | `xhigh` | `organvm-vii-kerygma/portfolio` | `deep` | `external` | [#2211](https://github.com/organvm/limen/issues/2211), [#2199](https://github.com/organvm/limen/issues/2199) |
| `PSP-P07-W04` Rebuild the resume and interview evidence packet | [#2216](https://github.com/organvm/limen/issues/2216) | `PSP-C06` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2186](https://github.com/organvm/limen/issues/2186), [#2199](https://github.com/organvm/limen/issues/2199) |
| `PSP-P07-W05` Upgrade selected flagship repositories as proof destinations | [#2217](https://github.com/organvm/limen/issues/2217) | `PSP-C06` | `gpt-5.6-sol` | `xhigh` | `multi-repository:selected-flagships` | `routine` | `write` | [#2176](https://github.com/organvm/limen/issues/2176), [#2184](https://github.com/organvm/limen/issues/2184) |
| `PSP-P07-W06` Stage the LinkedIn, X, and email-signature identity package | [#2218](https://github.com/organvm/limen/issues/2218) | `PSP-C06` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2184](https://github.com/organvm/limen/issues/2184), [#2186](https://github.com/organvm/limen/issues/2186) |
| `PSP-P07-W07` Attach the approved custom-domain hierarchy | [#2219](https://github.com/organvm/limen/issues/2219) | `PSP-C06` | `gpt-5.6-terra` | `high` | `organvm/limen` | `routine` | `external` | [#2215](https://github.com/organvm/limen/issues/2215) |
| `PSP-P07-W08` Install privacy-respecting funnel analytics and door tags | [#2220](https://github.com/organvm/limen/issues/2220) | `PSP-C06` | `gpt-5.6-sol` | `xhigh` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2215](https://github.com/organvm/limen/issues/2215), [#2183](https://github.com/organvm/limen/issues/2183) |
| `PSP-P07-W09` Prove link health, release rollback, and surface parity | [#2221](https://github.com/organvm/limen/issues/2221) | `PSP-C06` | `gpt-5.6-luna` | `medium` | `organvm/limen` | `routine` | `write` | [#2213](https://github.com/organvm/limen/issues/2213), [#2214](https://github.com/organvm/limen/issues/2214), [#2215](https://github.com/organvm/limen/issues/2215), [#2216](https://github.com/organvm/limen/issues/2216), [#2217](https://github.com/organvm/limen/issues/2217), [#2218](https://github.com/organvm/limen/issues/2218), [#2219](https://github.com/organvm/limen/issues/2219), [#2220](https://github.com/organvm/limen/issues/2220) |

## PSP-P08 — Inbound capture and private lead operations

Qualified interest enters a safe, tagged, private pipeline with no unauthorized outbound effect.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P08-W01` Activate a dedicated inbound alias and tagged CTAs | [#2223](https://github.com/organvm/limen/issues/2223) | `PSP-C07` | `gpt-5.6-terra` | `high` | `organvm/limen` | `routine` | `external` | [#2221](https://github.com/organvm/limen/issues/2221) |
| `PSP-P08-W02` Design minimal client and recruiter intake flows | [#2224](https://github.com/organvm/limen/issues/2224) | `PSP-C07` | `gpt-5.6-sol` | `xhigh` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2193](https://github.com/organvm/limen/issues/2193), [#2223](https://github.com/organvm/limen/issues/2223) |
| `PSP-P08-W03` Normalize inbound mail and form submissions into private lead records | [#2225](https://github.com/organvm/limen/issues/2225) | `PSP-C07` | `gpt-5.6-sol` | `xhigh` | `organvm/universal-mail--automation` | `deep` | `write` | [#2224](https://github.com/organvm/limen/issues/2224) |
| `PSP-P08-W04` Score and route client, recruiter, operator, spam, and ambiguous leads | [#2226](https://github.com/organvm/limen/issues/2226) | `PSP-C07` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2225](https://github.com/organvm/limen/issues/2225), [#2193](https://github.com/organvm/limen/issues/2193) |
| `PSP-P08-W05` Create reply, scheduling, decline, and recruiter draft templates | [#2227](https://github.com/organvm/limen/issues/2227) | `PSP-C07` | `gpt-5.6-luna` | `medium` | `organvm/universal-mail--automation` | `routine` | `write` | [#2226](https://github.com/organvm/limen/issues/2226), [#2193](https://github.com/organvm/limen/issues/2193) |
| `PSP-P08-W06` Build the private opportunity pipeline and decision ledger | [#2228](https://github.com/organvm/limen/issues/2228) | `PSP-C07` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2225](https://github.com/organvm/limen/issues/2225), [#2226](https://github.com/organvm/limen/issues/2226) |
| `PSP-P08-W07` Prove the capture funnel end to end with the send valve closed | [#2229](https://github.com/organvm/limen/issues/2229) | `PSP-C07` | `gpt-5.6-sol` | `xhigh` | `multi-repository:limen-portfolio-mail` | `deep` | `read` | [#2223](https://github.com/organvm/limen/issues/2223), [#2224](https://github.com/organvm/limen/issues/2224), [#2225](https://github.com/organvm/limen/issues/2225), [#2226](https://github.com/organvm/limen/issues/2226), [#2227](https://github.com/organvm/limen/issues/2227), [#2228](https://github.com/organvm/limen/issues/2228) |

## PSP-P09 — Proof-led content and distribution

One flagship proof becomes a durable content engine whose derivatives attract qualified demand without claim drift.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P09-W01` Build the 90-day proof-led editorial calendar | [#2231](https://github.com/organvm/limen/issues/2231) | `PSP-C08` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2198](https://github.com/organvm/limen/issues/2198), [#2193](https://github.com/organvm/limen/issues/2193) |
| `PSP-P09-W02` Stage and owner-publish the flagship Limen engineering report | [#2232](https://github.com/organvm/limen/issues/2232) | `PSP-C08` | `gpt-5.6-sol` | `max` | `organvm-vii-kerygma/portfolio` | `frontier_review` | `external` | [#2198](https://github.com/organvm/limen/issues/2198), [#2221](https://github.com/organvm/limen/issues/2221), [#2229](https://github.com/organvm/limen/issues/2229) |
| `PSP-P09-W03` Derive the agentic-delivery failure-modes essay | [#2233](https://github.com/organvm/limen/issues/2233) | `PSP-C08` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2200](https://github.com/organvm/limen/issues/2200), [#2232](https://github.com/organvm/limen/issues/2232) |
| `PSP-P09-W04` Derive the cost-per-task and control-economics essay | [#2234](https://github.com/organvm/limen/issues/2234) | `PSP-C08` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2200](https://github.com/organvm/limen/issues/2200), [#2232](https://github.com/organvm/limen/issues/2232) |
| `PSP-P09-W05` Derive the delivery-gates walkthrough | [#2235](https://github.com/organvm/limen/issues/2235) | `PSP-C08` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2202](https://github.com/organvm/limen/issues/2202), [#2232](https://github.com/organvm/limen/issues/2232) |
| `PSP-P09-W06` Publish a candid incident and correction case study | [#2236](https://github.com/organvm/limen/issues/2236) | `PSP-C08` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2179](https://github.com/organvm/limen/issues/2179), [#2232](https://github.com/organvm/limen/issues/2232) |
| `PSP-P09-W07` Generate channel-specific derivative assets without claim drift | [#2237](https://github.com/organvm/limen/issues/2237) | `PSP-C08` | `gpt-5.6-luna` | `medium` | `organvm/limen` | `routine` | `write` | [#2233](https://github.com/organvm/limen/issues/2233), [#2234](https://github.com/organvm/limen/issues/2234), [#2235](https://github.com/organvm/limen/issues/2235), [#2236](https://github.com/organvm/limen/issues/2236) |
| `PSP-P09-W08` Execute owner-approved distribution and record channel outcomes | [#2238](https://github.com/organvm/limen/issues/2238) | `PSP-C08` | `gpt-5.6-terra` | `high` | `organvm-iii-ergon/collaboration-operations-platform` | `routine` | `external` | [#2237](https://github.com/organvm/limen/issues/2237), [#2229](https://github.com/organvm/limen/issues/2229) |

## PSP-P10 — Qualification, conversation, and conversion system

Qualified client and recruiter demand moves through repeatable decisions without over-selling or custom-scope sprawl.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P10-W01` Define the ideal client profile and live buying signals | [#2240](https://github.com/organvm/limen/issues/2240) | `PSP-C09` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2193](https://github.com/organvm/limen/issues/2193), [#2231](https://github.com/organvm/limen/issues/2231) |
| `PSP-P10-W02` Build the client discovery-call guide | [#2241](https://github.com/organvm/limen/issues/2241) | `PSP-C09` | `gpt-5.6-terra` | `high` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2240](https://github.com/organvm/limen/issues/2240), [#2190](https://github.com/organvm/limen/issues/2190) |
| `PSP-P10-W03` Build the pre-audit diagnostic questionnaire | [#2242](https://github.com/organvm/limen/issues/2242) | `PSP-C09` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2241](https://github.com/organvm/limen/issues/2241), [#2249](https://github.com/organvm/limen/issues/2249) |
| `PSP-P10-W04` Build the Agentic Delivery Audit sales page and intake path | [#2243](https://github.com/organvm/limen/issues/2243) | `PSP-C09` | `gpt-5.6-terra` | `high` | `organvm-vii-kerygma/portfolio` | `deep` | `write` | [#2190](https://github.com/organvm/limen/issues/2190), [#2224](https://github.com/organvm/limen/issues/2224), [#2240](https://github.com/organvm/limen/issues/2240) |
| `PSP-P10-W05` Implement proposal, follow-up, decision, and close-lost workflow | [#2244](https://github.com/organvm/limen/issues/2244) | `PSP-C09` | `gpt-5.6-luna` | `medium` | `organvm-iii-ergon/collaboration-operations-platform` | `routine` | `write` | [#2195](https://github.com/organvm/limen/issues/2195), [#2228](https://github.com/organvm/limen/issues/2228), [#2241](https://github.com/organvm/limen/issues/2241) |
| `PSP-P10-W06` Build the recruiter conversation and interview packet | [#2245](https://github.com/organvm/limen/issues/2245) | `PSP-C09` | `gpt-5.6-terra` | `high` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2186](https://github.com/organvm/limen/issues/2186), [#2187](https://github.com/organvm/limen/issues/2187), [#2216](https://github.com/organvm/limen/issues/2216) |
| `PSP-P10-W07` Operate a structured objection and no-outcome ledger | [#2246](https://github.com/organvm/limen/issues/2246) | `PSP-C09` | `gpt-5.6-luna` | `medium` | `organvm-iii-ergon/collaboration-operations-platform` | `routine` | `write` | [#2244](https://github.com/organvm/limen/issues/2244), [#2245](https://github.com/organvm/limen/issues/2245) |
| `PSP-P10-W08` Run and adjudicate the 90-day demand experiment | [#2247](https://github.com/organvm/limen/issues/2247) | `PSP-C10` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2238](https://github.com/organvm/limen/issues/2238), [#2246](https://github.com/organvm/limen/issues/2246), [#2259](https://github.com/organvm/limen/issues/2259) |

## PSP-P11 — Service-delivery operating system

Audit, install, and retainer engagements can be delivered safely, consistently, and with reusable evidence.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P11-W01` Define read-only evidence intake and security boundaries | [#2249](https://github.com/organvm/limen/issues/2249) | `PSP-C05` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2190](https://github.com/organvm/limen/issues/2190) |
| `PSP-P11-W02` Build the Agentic Delivery Audit methodology and runbook | [#2250](https://github.com/organvm/limen/issues/2250) | `PSP-C05` | `gpt-5.6-sol` | `max` | `organvm-iii-ergon/collaboration-operations-platform` | `frontier_review` | `write` | [#2249](https://github.com/organvm/limen/issues/2249), [#2190](https://github.com/organvm/limen/issues/2190) |
| `PSP-P11-W03` Create the audit report and executive verdict template | [#2251](https://github.com/organvm/limen/issues/2251) | `PSP-C05` | `gpt-5.6-terra` | `high` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2250](https://github.com/organvm/limen/issues/2250) |
| `PSP-P11-W04` Build the Governance Install delivery runbook | [#2252](https://github.com/organvm/limen/issues/2252) | `PSP-C05` | `gpt-5.6-terra` | `high` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2251](https://github.com/organvm/limen/issues/2251), [#2191](https://github.com/organvm/limen/issues/2191) |
| `PSP-P11-W05` Build the bounded retainer operating contract | [#2253](https://github.com/organvm/limen/issues/2253) | `PSP-C05` | `gpt-5.6-terra` | `high` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2252](https://github.com/organvm/limen/issues/2252), [#2192](https://github.com/organvm/limen/issues/2192) |
| `PSP-P11-W06` Build the private client workspace and decision log | [#2254](https://github.com/organvm/limen/issues/2254) | `PSP-C05` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2249](https://github.com/organvm/limen/issues/2249) |
| `PSP-P11-W07` Prove delivery QA, acceptance, handoff, and closeout | [#2255](https://github.com/organvm/limen/issues/2255) | `PSP-C05` | `gpt-5.6-terra` | `high` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2250](https://github.com/organvm/limen/issues/2250), [#2251](https://github.com/organvm/limen/issues/2251), [#2252](https://github.com/organvm/limen/issues/2252), [#2253](https://github.com/organvm/limen/issues/2253), [#2254](https://github.com/organvm/limen/issues/2254) |
| `PSP-P11-W08` Define consent and sanitization for public client proof | [#2256](https://github.com/organvm/limen/issues/2256) | `PSP-C05` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2255](https://github.com/organvm/limen/issues/2255) |

## PSP-P12 — External validation and first commercial proof

Real users, buyers, recruiters, or partners create evidence beyond self-authored technical output.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P12-W01` Recruit a bounded design-partner cohort | [#2258](https://github.com/organvm/limen/issues/2258) | `PSP-C10` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `external` | [#2238](https://github.com/organvm/limen/issues/2238), [#2240](https://github.com/organvm/limen/issues/2240), [#2250](https://github.com/organvm/limen/issues/2250) |
| `PSP-P12-W02` Close and deliver the first paid or explicitly bounded pilot audit | [#2259](https://github.com/organvm/limen/issues/2259) | `PSP-C10` | `gpt-5.6-sol` | `max` | `organvm-iii-ergon/collaboration-operations-platform` | `frontier_review` | `external` | [#2258](https://github.com/organvm/limen/issues/2258), [#2244](https://github.com/organvm/limen/issues/2244), [#2255](https://github.com/organvm/limen/issues/2255) |
| `PSP-P12-W03` Deliver the first Governance Install when the audit supports it | [#2260](https://github.com/organvm/limen/issues/2260) | `PSP-C10` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `external` | [#2259](https://github.com/organvm/limen/issues/2259), [#2252](https://github.com/organvm/limen/issues/2252) |
| `PSP-P12-W04` Produce the first consented public case study | [#2261](https://github.com/organvm/limen/issues/2261) | `PSP-C10` | `gpt-5.6-sol` | `max` | `organvm-vii-kerygma/portfolio` | `frontier_review` | `external` | [#2259](https://github.com/organvm/limen/issues/2259), [#2256](https://github.com/organvm/limen/issues/2256) |
| `PSP-P12-W05` Capture testimonials, references, reproductions, and independent review | [#2262](https://github.com/organvm/limen/issues/2262) | `PSP-C10` | `gpt-5.6-luna` | `medium` | `organvm/limen` | `routine` | `write` | [#2259](https://github.com/organvm/limen/issues/2259) |
| `PSP-P12-W06` Refresh positioning, proof, and offer claims from real outcomes | [#2263](https://github.com/organvm/limen/issues/2263) | `PSP-C10` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2259](https://github.com/organvm/limen/issues/2259), [#2261](https://github.com/organvm/limen/issues/2261), [#2262](https://github.com/organvm/limen/issues/2262), [#2180](https://github.com/organvm/limen/issues/2180) |

## PSP-P13 — Governed foundry and domain-operator handoff

The estate's product abundance becomes a scored portfolio whose validated products can transfer to accountable operators.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P13-W01` Inventory every product candidate across all owned organizations | [#2265](https://github.com/organvm/limen/issues/2265) | `PSP-C11` | `gpt-5.4-mini` | `low` | `organvm/limen` | `routine` | `read` | [#2173](https://github.com/organvm/limen/issues/2173), [#2174](https://github.com/organvm/limen/issues/2174) |
| `PSP-P13-W02` Score demand and market evidence for every product candidate | [#2266](https://github.com/organvm/limen/issues/2266) | `PSP-C11` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2265](https://github.com/organvm/limen/issues/2265), [#2228](https://github.com/organvm/limen/issues/2228) |
| `PSP-P13-W03` Score technical readiness, custody, and maintenance risk | [#2267](https://github.com/organvm/limen/issues/2267) | `PSP-C11` | `gpt-5.6-sol` | `xhigh` | `organvm/limen` | `deep` | `write` | [#2265](https://github.com/organvm/limen/issues/2265) |
| `PSP-P13-W04` Define the domain-operator profile and selection scorecard | [#2268](https://github.com/organvm/limen/issues/2268) | `PSP-C11` | `gpt-5.6-terra` | `high` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2266](https://github.com/organvm/limen/issues/2266), [#2267](https://github.com/organvm/limen/issues/2267) |
| `PSP-P13-W05` Establish transfer floors, economics, and kill/park rules | [#2269](https://github.com/organvm/limen/issues/2269) | `PSP-C11` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2266](https://github.com/organvm/limen/issues/2266), [#2267](https://github.com/organvm/limen/issues/2267) |
| `PSP-P13-W06` Design licensing, equity, revenue-share, custody, and return options | [#2270](https://github.com/organvm/limen/issues/2270) | `PSP-C11` | `gpt-5.6-sol` | `max` | `organvm-iii-ergon/collaboration-operations-platform` | `frontier_review` | `write` | [#2268](https://github.com/organvm/limen/issues/2268), [#2269](https://github.com/organvm/limen/issues/2269) |
| `PSP-P13-W07` Build the operator discovery, diligence, and trial pipeline | [#2271](https://github.com/organvm/limen/issues/2271) | `PSP-C11` | `gpt-5.6-sol` | `xhigh` | `organvm-iii-ergon/collaboration-operations-platform` | `deep` | `write` | [#2268](https://github.com/organvm/limen/issues/2268), [#2270](https://github.com/organvm/limen/issues/2270) |
| `PSP-P13-W08` Execute one bounded operator-handoff pilot | [#2272](https://github.com/organvm/limen/issues/2272) | `PSP-C11` | `gpt-5.6-sol` | `max` | `multi-repository:selected-product-and-private-platform` | `frontier_review` | `external` | [#2267](https://github.com/organvm/limen/issues/2267), [#2269](https://github.com/organvm/limen/issues/2269), [#2270](https://github.com/organvm/limen/issues/2270), [#2271](https://github.com/organvm/limen/issues/2271) |
| `PSP-P13-W09` Institutionalize foundry governance and product return paths | [#2273](https://github.com/organvm/limen/issues/2273) | `PSP-C11` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2272](https://github.com/organvm/limen/issues/2272) |

## PSP-P14 — Return loop, measurement, rollback, and Omega

Evidence, demand, delivery, and operator results continuously correct the system and converge without orphan work.

| Work ID | Issue | Chunk | Model | Effort | Target | Reasoning | Effect | Depends on |
|---|---:|---|---|---|---|---|---|---|
| `PSP-P14-W01` Define the end-to-end event and KPI dictionary | [#2275](https://github.com/organvm/limen/issues/2275) | `PSP-C12` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2220](https://github.com/organvm/limen/issues/2220), [#2228](https://github.com/organvm/limen/issues/2228), [#2255](https://github.com/organvm/limen/issues/2255), [#2273](https://github.com/organvm/limen/issues/2273) |
| `PSP-P14-W02` Operate the weekly execution and demand review | [#2276](https://github.com/organvm/limen/issues/2276) | `PSP-C12` | `gpt-5.6-luna` | `medium` | `organvm/limen` | `routine` | `write` | [#2275](https://github.com/organvm/limen/issues/2275), [#2165](https://github.com/organvm/limen/issues/2165) |
| `PSP-P14-W03` Operate the monthly truth, surface, and privacy audit | [#2277](https://github.com/organvm/limen/issues/2277) | `PSP-C12` | `gpt-5.6-sol` | `xhigh` | `organvm/limen` | `deep` | `write` | [#2178](https://github.com/organvm/limen/issues/2178), [#2179](https://github.com/organvm/limen/issues/2179), [#2221](https://github.com/organvm/limen/issues/2221) |
| `PSP-P14-W04` Operate the quarterly strategy and prominence review | [#2278](https://github.com/organvm/limen/issues/2278) | `PSP-C12` | `gpt-5.6-sol` | `max` | `organvm/limen` | `frontier_review` | `write` | [#2247](https://github.com/organvm/limen/issues/2247), [#2263](https://github.com/organvm/limen/issues/2263), [#2275](https://github.com/organvm/limen/issues/2275) |
| `PSP-P14-W05` Automate claim incident quarantine and correction propagation | [#2279](https://github.com/organvm/limen/issues/2279) | `PSP-C12` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2179](https://github.com/organvm/limen/issues/2179), [#2221](https://github.com/organvm/limen/issues/2221) |
| `PSP-P14-W06` Automate release-level surface rollback and recovery verification | [#2280](https://github.com/organvm/limen/issues/2280) | `PSP-C12` | `gpt-5.6-sol` | `xhigh` | `multi-repository:public-surfaces` | `deep` | `external` | [#2221](https://github.com/organvm/limen/issues/2221), [#2229](https://github.com/organvm/limen/issues/2229) |
| `PSP-P14-W07` Feed sales objections and demand outcomes back into offers | [#2281](https://github.com/organvm/limen/issues/2281) | `PSP-C12` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2246](https://github.com/organvm/limen/issues/2246), [#2247](https://github.com/organvm/limen/issues/2247) |
| `PSP-P14-W08` Feed delivery and operator outcomes back into proof and portfolio classification | [#2282](https://github.com/organvm/limen/issues/2282) | `PSP-C12` | `gpt-5.6-terra` | `high` | `organvm/limen` | `deep` | `write` | [#2263](https://github.com/organvm/limen/issues/2263), [#2272](https://github.com/organvm/limen/issues/2272), [#2273](https://github.com/organvm/limen/issues/2273) |
| `PSP-P14-W09` Prove alpha-to-omega convergence in two unchanged passes | [#2283](https://github.com/organvm/limen/issues/2283) | `PSP-C12` | `gpt-5.6-sol` | `ultra` | `organvm/limen` | `frontier_review` | `read` | [#2276](https://github.com/organvm/limen/issues/2276), [#2277](https://github.com/organvm/limen/issues/2277), [#2278](https://github.com/organvm/limen/issues/2278), [#2279](https://github.com/organvm/limen/issues/2279), [#2280](https://github.com/organvm/limen/issues/2280), [#2281](https://github.com/organvm/limen/issues/2281), [#2282](https://github.com/organvm/limen/issues/2282) |
