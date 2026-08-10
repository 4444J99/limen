# PSP-C04 proof and experience preflight relay

- Chunk: `PSP-C04` — Produce proof and design the experience
- Formal state: `PREPARED/PREFLIGHT`
- Prepared: 2026-08-10
- Limen branch: `codex/psp-c04-proof-experience-preflight`
- Portfolio owner: `organvm-vii-kerygma/portfolio` (repository id `1155412125`)
- Portfolio branch: `codex/psp-p06-experience-preflight`

## Dependency boundary

Formal closure remains blocked until `PSP-C02` and `PSP-C03` close with predicate-backed receipts.
The stale `organvm/portfolio` target in `program.yaml` is recorded as a C02 adjudication dependency;
this relay does not rewrite that unrelated registry state. The live portfolio owner is the Kerygma
repository named above.

Relevant remote evidence snapshots consumed by this preflight:

- flagship selection: `528c94d31a426f3a9cac29a72cd38bc942d45171`;
- public evidence packets: `3a752d530633c8a2ec4b7942e325b4838e56c233`;
- claim/correction policy: `2a0550862091a976b756034d4ddfa3965fd206ec`.

C03 checkpoint integration is exact-head-only. C04 consumed the committed contract and successor
relay from `codex/psp-c03-identity-offers-preflight` at current fetched head
`b5bc01585a10615e85e1ef5b31a2356c24fb9bc9`, including the registry-alignment checkpoint
`986ebb41778cf082e01ede0cb6d268cebf54a106`. C03 is still dependency-blocked on C02 and is not
closed. C04 binds its public identity, audience, narrative, authority, and offer-boundary tokens
without copying private pricing amounts or creating a public offer.

## What can formalize automatically after C02 and C03

1. Refresh and record the exact committed heads of the flagship-selection, public-evidence,
   claim-policy, and C03 contract branches.
2. Resolve the three candidate flagship claims against the merged evidence and claims ledgers.
3. Emit the surface-by-claim audit and quarantine missing, stale, contradictory, private, or
   unsupported implications.
4. Instantiate fresh exact-head reproduction receipt requests for Limen, the UCC Public-Records
   Intelligence Platform, and AI Chat Exporter.
5. Refresh the bound C03 exact head, then bind its identity/audience/CTA tokens into the portfolio
   content contract without changing route or disclosure invariants.

## What still requires the later visual-selection gate

The portfolio package intentionally contains no redesigned UI, mock, scaffold, new route, server,
deployment, or public mutation. Once merged C02 evidence and the exact committed C03 contract are
bound, Product Design must generate exactly three materially distinct visual directions from the
same content/interaction contract. A human selects one direction before any implementation begins.
The selection receipt must name the chosen direction, rejected directions, rationale, accessibility
risk, performance risk, and rollback to the current public release.

## Proof-package checkpoint

- Contract: `docs/positioning/proof/psp-c04-proof-contract.json`
- Narrative: `docs/positioning/proof/PSP-C04-P05-PREFLIGHT.md`
- Validator: `python3 scripts/positioning-proof-preflight.py --json`
- Claim resolver: `python3 scripts/positioning-proof-preflight.py --mode resolve --json`
- Surface-audit denominator: `python3 scripts/positioning-proof-preflight.py --mode surface-audit --json`
- Focused test: `python3 -m unittest discover -s scripts/tests -p 'test_positioning_proof_preflight.py'`

## Safety state

- Current release untouched.
- No publication, deployment, DNS, analytics, account, or task-board mutation.
- No outreach or send; `HG-PUBLICATION-SEND` remains unsatisfied.
- Adoption, revenue, rankings, percentiles, and private evidence remain withheld.
- No phase or issue may close from this relay.

## Next action

After both predecessor chunks close, refresh this relay with their exact merged receipts, run the
two preflight validators, bind C03 tokens, and invoke the three-direction visual ideation gate. Do
not start visual implementation before the selection receipt exists.
