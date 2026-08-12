# PSP-C04 proof and experience preflight relay

- Chunk: `PSP-C04` — Produce proof and design the experience
- Formal state: `PREPARED/PREFLIGHT`
- Prepared: 2026-08-10
- Limen branch: `codex/psp-c04-proof-experience-preflight`
- Limen draft checkpoint: https://github.com/organvm/limen/pull/2313
- Portfolio owner: `organvm-vii-kerygma/portfolio` (repository id `1155412125`)
- Portfolio branch: `codex/psp-p06-experience-preflight`
- Portfolio draft checkpoint: https://github.com/organvm-vii-kerygma/portfolio/pull/220 at exact head
  `fa86b67a7283c15ab801302ffac655c30898b6a1`

## Dependency boundary

`PSP-P02` is formally closed. C03 W01-W06 are formally closed on PR #2312 at exact head
`c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`. Its W06 receipt is
https://github.com/organvm/limen/issues/2187#issuecomment-5271254820 with receipt SHA-256
`260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617`.

Formal C04 activation remains blocked only on `PSP-P03-W07` and the resulting C03 formal closure.
W07 requires five blinded, target-like readers; C04 does not solicit those readers or substitute
the accepted W06 model review for that evidence. This relay remains `PREPARED/PREFLIGHT`.

The live portfolio owner is the Kerygma repository named above. This relay does not rewrite
unrelated registry state.

Relevant remote evidence snapshots consumed by this preflight:

- flagship selection: `528c94d31a426f3a9cac29a72cd38bc942d45171`;
- public evidence packets: `3a752d530633c8a2ec4b7942e325b4838e56c233`;
- claim/correction policy: `2a0550862091a976b756034d4ddfa3965fd206ec`.

C03 checkpoint integration is exact-head-only. C04 consumed the committed contract and successor
relay from `codex/psp-c03-identity-offers-preflight` at current fetched head
`c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`, including accepted W01-W06 and the
registry-alignment checkpoint `986ebb41778cf082e01ede0cb6d268cebf54a106`. C03 is not formally
closed because W07 remains open. C04 binds the accepted identity, audience, narrative, authority,
and offer-boundary tokens without copying private pricing amounts or creating a public offer.

## What can formalize automatically after W07 and C03 closure

1. Refresh and record the exact committed heads of the flagship-selection, public-evidence,
   claim-policy, and C03 contract branches.
2. Resolve the three candidate flagship claims against the merged evidence and claims ledgers.
3. Emit the surface-by-claim audit and quarantine missing, stale, contradictory, private, or
   unsupported implications.
4. Instantiate fresh exact-head reproduction receipt requests for Limen, the UCC Public-Records
   Intelligence Platform, and AI Chat Exporter.
5. Confirm the accepted C03 head descends from `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`,
   then bind its identity/audience/CTA tokens without changing route or disclosure invariants.

## What still requires the later visual-selection gate

The portfolio package intentionally contains no redesigned UI, mock, scaffold, new route, server,
deployment, or public mutation. Once C03 formally closes and its exact accepted contract is bound,
Product Design must generate exactly three materially distinct visual directions from the same
content/interaction contract. A human selects one direction before any implementation begins.
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

After W07 and C03 close, refresh this relay with the final C03 receipt, run the two preflight
validators, bind the final C03 tokens, and invoke the three-direction visual ideation gate. Do not
start visual implementation before the selection receipt exists.
