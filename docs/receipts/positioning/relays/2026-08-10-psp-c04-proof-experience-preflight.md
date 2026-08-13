# PSP-C04 proof and experience preflight relay

- Chunk: `PSP-C04` — Produce proof and design the experience
- Formal state: `PREPARED/PREFLIGHT`
- Prepared: 2026-08-10
- Limen branch: `codex/psp-c04-proof-experience-preflight`
- Limen draft checkpoint: https://github.com/organvm/limen/pull/2313
- Portfolio owner: `organvm-vii-kerygma/portfolio` (repository id `1155412125`)
- Portfolio source: https://github.com/organvm-vii-kerygma/portfolio/pull/220, merged from exact head
  `8974543ba9675ed0504141895812476efef5dd80` as
  `a01b6d85f78d2d744c0c994f7220081bb54a85c5`

## Dependency boundary

`PSP-P02` is formally closed at exact main head
`8faa5fb9899231ebf5f87e78bb171544c11b79d7`, with receipt
https://github.com/organvm/limen/issues/2172#issuecomment-5270095170 and receipt SHA-256
`f312ae3536ced23aa782701b4a437866707c2eec4b6b194ba05a735e2d8bb434`. C03 PR #2312 merged
from exact source head `b6af8086c9050634313f519c29a6dfcb922c3721` as
`8f89ad16ca1df84b00cb8227c88f368d0d64631a`; P03 W01-W06 are accepted at ancestor
`c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`, and P04's five generated offer artifacts are
integrated as a reversible contract. Its W06 receipt is
https://github.com/organvm/limen/issues/2187#issuecomment-5271254820 with receipt SHA-256
`260081dfbffc75d55824c0e6ed7d7718a7e397763afb689c94d2230963d79617`.

Formal C04 activation remains blocked only on `PSP-P03-W07` and the resulting C03 formal closure.
W07 requires five blinded, target-like readers; C04 does not solicit those readers or substitute
the accepted W06 model review for that evidence. This relay remains `PREPARED/PREFLIGHT`.

The live portfolio owner is the Kerygma repository named above. This relay does not rewrite
unrelated registry state.

Accepted PSP-P02 objects consumed from exact head
`8faa5fb9899231ebf5f87e78bb171544c11b79d7`:

- live registry blob: `de8c489667f2ad797dde60dfb84a9fa1fb4b0e16`;
- flagship selection blob: `5d4776efc7a811b0163cdfea5cf083409157feae`;
- public evidence blob: `ce59d44794f44e0511436cbabbcd4fba1a938891`;
- claim/correction policy blob: `57565f0d0dc72d2200b41be0e21fe6d323ec7f83`;
- claims-ledger blob: `3e49114563075dcd6926e3b7f8fd24bf8b9c3fee`.

C03 checkpoint integration is exact-source-and-merge-bound. C04 consumed the committed contract and
successor relay from source head
`b6af8086c9050634313f519c29a6dfcb922c3721`, including accepted W01-W06, the refreshed
commercial contract, and all five generated offer artifacts, and binds their main integration at
`8f89ad16ca1df84b00cb8227c88f368d0d64631a`. C03 is not formally closed because W07 remains open.
C04 binds the accepted identity, audience, narrative, authority, claim, and offer-boundary tokens
without copying private pricing amounts or creating a public offer.

## What can formalize automatically after W07 and C03 closure

1. Confirm that the final C03 closure head descends from
   `b6af8086c9050634313f519c29a6dfcb922c3721`, then refresh all dated evidence sources.
2. Resolve the three candidate flagship claims against the merged evidence and claims ledgers.
3. Emit the surface-by-claim audit and quarantine missing, stale, contradictory, private, or
   unsupported implications.
4. Instantiate fresh exact-head reproduction receipt requests for Limen, the UCC Public-Records
   Intelligence Platform, and AI Chat Exporter.
5. Bind the final C03 identity, audience, claim, offer, and CTA tokens without changing route or
   disclosure invariants.

## What still requires the later visual-selection gate

The portfolio P06 package contains no redesigned UI, mock, scaffold, new route, or server. Its
contract is integrated, but visual implementation remains unselected. Once C03 formally closes and
its exact accepted contract is bound,
Product Design must generate exactly three materially distinct visual directions from the same
content/interaction contract. A human selects one direction before any implementation begins.
The selection receipt must name the chosen direction, rejected directions, rationale, accessibility
risk, performance risk, and rollback to the current public release.

## Proof-package checkpoint

- Contract: `docs/positioning/proof/psp-c04-proof-contract.json`
- Narrative: `docs/positioning/proof/PSP-C04-P05-PREFLIGHT.md`
- Validator: `python3 scripts/positioning-proof-preflight.py --json`
- Upstream object binding: `python3 scripts/positioning-proof-preflight.py --mode upstream-bindings --json`
- Claim resolver: `python3 scripts/positioning-proof-preflight.py --mode resolve --json`
- Surface-audit denominator: `python3 scripts/positioning-proof-preflight.py --mode surface-audit --json`
- Focused test: `python3 -m unittest discover -s scripts/tests -p 'test_positioning_proof*.py'`

## Safety state

- This C04 package does not alter the current release.
- No publication, deployment, DNS, analytics, account, or task-board mutation.
- No outreach or send; `HG-PUBLICATION-SEND` remains unsatisfied.
- Adoption, revenue, rankings, percentiles, and private evidence remain withheld.
- No phase or issue may close from this relay.
- `counts_as_closure=false`; formal proof/experience work remains PREPARED/PREFLIGHT.

## Next action

After W07 and C03 close, refresh this relay with the final C03 receipt, run the two preflight
validators, bind the final C03 tokens, and invoke the three-direction visual ideation gate. Do not
start visual implementation before the selection receipt exists.
