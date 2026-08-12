---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: codex-direct-psp-c09-preflight
to: next admitted Codex session for PSP-C09
scope: PSP-P10-W01-through-PSP-P10-W07
phase: PROVE
compression_level: high
---

# Relay — PSP-C09 qualification and conversion preflight

## Routing

- Program work: `PSP-C09`, scoped to `PSP-P10-W01` through `PSP-P10-W07`
- Conductor assignment: `gpt-5.6-sol / xhigh`
- Leaf issues: [#2240](https://github.com/organvm/limen/issues/2240) through
  [#2246](https://github.com/organvm/limen/issues/2246)
- Conduct receipt: none; this was an explicitly authorized direct-session preflight, not a formal
  leaf claim, lifecycle transition, or substitute for the dependency DAG
- State: **PREPARED/PREFLIGHT**. No C09 leaf or P10 phase predicate was run or satisfied.

## Exact source and custody receipts

| Owner | Exact remote receipt | What C09 consumes |
| --- | --- | --- |
| C00/P00 control plane | merged Limen PR [#2300](https://github.com/organvm/limen/pull/2300), merge commit `fbab1543a863ba2a86546de1eb31bdb9f0f50388` | C00/P00 is closed. The historical Agy/non-Codex identity gate is superseded and must not be reintroduced. |
| P02 evidence and adjudication | marked phase receipt [#2172](https://github.com/organvm/limen/issues/2172#issuecomment-5270095170), accepted main `8faa5fb9899231ebf5f87e78bb171544c11b79d7` | P02 is formally closed; this removes the former evidence dependency without promoting later phases. |
| C03 identity/offers | draft Limen PR [#2312](https://github.com/organvm/limen/pull/2312), accepted W01-W06 checkpoint `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec`; current executable W07-intake head `3ad04e23f0b65d92f2cd24e742acab5a8efc7487` | Identity, audience, authority, bounded Audit/Install/Retainer shape, and symbolic commercial anchors are accepted through W06. W07/#2188 remains open for five genuine independent readers; C09 does not duplicate or satisfy it. |
| C04 proof experience | Limen draft [#2313](https://github.com/organvm/limen/pull/2313) at `5bf686f6ceba200c6157bd87eb6e5298750a4ffb`; portfolio draft [#220](https://github.com/organvm-vii-kerygma/portfolio/pull/220) at `8974543ba9675ed0504141895812476efef5dd80` | PREPARED executable proof and experience contracts only; neither is formal phase evidence. |
| C05 delivery OS | private draft PR [#135](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/135) at `2c4efce84082f344fd5e0d90cc110662a379435f`; public relay [#2315](https://github.com/organvm/limen/pull/2315) at `fdd41da45bdf5909e7b782a03dbaedf85e105c25` | Executable W01-W08 delivery contracts and custody boundaries only. C05 remains PREPARED and does not close P11 while its dependencies remain unsatisfied. |
| C06 public surfaces | portfolio draft PR [#221](https://github.com/organvm-vii-kerygma/portfolio/pull/221) at `6cb1abf0bf08e71341476886385eba5499c51bb7`; Limen relay [#2317](https://github.com/organvm/limen/pull/2317) at `4eb50463b7f4136b47a103c9792c1ded5caf7873` | PREPARED only. Exactly three directions remain **UNSELECTED**; no rendered surface or deployment is authorized. |
| C07 private inbound | Limen draft [#2318](https://github.com/organvm/limen/pull/2318) at `c3b92707a0f6d0ea3076680d100d60d0217f8fe9` | PREPARED private-intake and threat-boundary contracts; no message, route, or external effect. |
| C08 proof-led content | draft Limen PR [#2316](https://github.com/organvm/limen/pull/2316) at `ef6e4df64f97c11dba2c159752d5a13b50a96c10` | PREPARED claim-source, correction/withdrawal, and attribution contracts. No publication or send occurred. |
| W01 public-safe package | Limen implementation checkpoint `3caf35a7c5e25701320ba1303cb7f1386e6e2318` on `codex/psp-c09-qualification-conversion-relay` | ICP, committee, triggers, pains, disqualifiers, evidence signals, deterministic scorecard, and ten synthetic accounts. |
| W02/W03/W05/W06/W07 private package | draft PR [#136](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/136) at `4872b543f33bdc58f915b27b44df58d48ba41f35` | Executable qualification, consent/authority, no-sign graph, CRM-safe projection, draft valves, deterministic scenarios, recruiter constraints, objection ledger, and synthetic conversion runtime. |
| W04 non-routable package | portfolio draft PR [#222](https://github.com/organvm-vii-kerygma/portfolio/pull/222) at `da79fb63b9756b5cce0d42ed2a7722668854a228` | Executable local CTA/funnel contract and synthetic tests. No page, route, component, style, or transport is present. |

## Preserved leaf assignments

| Leaf | Exact model / effort | Preflight artifact |
| --- | --- | --- |
| `PSP-P10-W01` | `gpt-5.6-terra / high` | Public-safe ICP and scoring contract |
| `PSP-P10-W02` | `gpt-5.6-terra / high` | Client discovery architecture |
| `PSP-P10-W03` | `gpt-5.6-sol / xhigh` | Secret-rejecting pre-audit questionnaire |
| `PSP-P10-W04` | `gpt-5.6-terra / high` | Non-routable offer/intake contract and tests |
| `PSP-P10-W05` | `gpt-5.6-luna / medium` | Proposal, follow-up, terminal decision, and close-lost workflow |
| `PSP-P10-W06` | `gpt-5.6-terra / high` | Recruiter/interview story and role-fit packet |
| `PSP-P10-W07` | `gpt-5.6-luna / medium` | Append-only objection/no-outcome taxonomy and threshold |

These assignments are preserved as registry data. This conductor preflight did not impersonate the
leaf executors, reserve hidden fanout, or run any formal `--verify-work` predicate.

## Synthetic predicate receipts

| Package | Reproducible result on its exact preflight tree |
| --- | --- |
| W01 | `python3 scripts/positioning-qualification-preflight.py --check` → `status=ok`, 10 synthetic accounts, 8 exact assignments; focused pytest → 6 passed; Ruff → passed |
| Private conversion | focused qualification/conversion Vitest → 14 passed; TypeScript → passed; complete Vitest → 29 passed; build and no-plaintext → passed; package-owned Prettier → passed |
| W04 | `npm run preflight:psp-p10-w04` → 11 passed; Astro typecheck → 298 files, 0 errors/warnings/hints; Biome exact paths → passed; no PSP-C09 route or rendered artifact emitted |

All fixtures are synthetic, all draft transports have `externalEffects=[]`, and the no-send release
path fails closed. These results prove only reversible preflight behavior; they are not contact,
reader-acceptance, conversion, revenue, adoption, or commercial-outcome evidence.

## Human predicates and effect boundary

- `HG-CONTRACT` and `HG-PUBLICATION-SEND` remain unapproved for W05. Drafts may not be sent, signed,
  or converted into a real service commitment.
- `HG-PUBLIC-IDENTITY`, `HG-PUBLICATION-SEND`, and the C06 option 1/2/3 visual selection remain
  unapproved. No rendered route, page, component, visual style, navigation, public analytics, or
  deploy surface may be added before the operator selects a C06 direction.
- No contact, publication, deployment, DNS, spend, signature, account mutation, private-evidence
  exposure, human-acceptance simulation, or fabricated commercial result occurred.

## Activation predicate and next owner

Keep all three drafts PREPARED while the formal DAG is not ready. P02 is closed; C03 is accepted
through W06; C03 W07/#2188 is the first open external-evidence gate. C04-C08 remain PREPARED, not
closed. Once live registry output admits
each leaf, the assigned native leaf executor must consume the then-current exact source heads, run
the leaf-specific acceptance work and real predicate, submit its own broker receipt, and close only
that admitted leaf. W04 may add a rendered surface only after the C06 visual-selection predicate is
recorded and its own dependencies are satisfied. P10 and C09 remain open until the registered exit
predicates pass; synthetic evidence must never be promoted into real-world proof.

The fresh-agent injection phrase is:

```text
Continue from relay at <admitted-limen-checkout>/docs/receipts/positioning/relays/2026-08-10-psp-c09-qualification-conversion-preflight.md. mid-task — see Activation predicate and next owner.
```

The receiver must verify live state and obtain its own authority. This file transfers context, not
identity, lease, approval, selection, or permission.
