---
type: prompt-relay-envelope
version: 1.0
date: 2026-08-10
from: codex-direct-psp-c09-preflight
to: next admitted Codex session for PSP-C09
scope: PSP-P10-W01-through-PSP-P10-W07
phase: PROVE
compression_level: high
counts_as_closure: false
---

# Relay — PSP-C09 qualification and conversion preflight

## Routing

- Program work: `PSP-C09`, scoped to `PSP-P10-W01` through `PSP-P10-W07`
- Conductor assignment: `gpt-5.6-sol / xhigh`
- Leaf issues: [#2240](https://github.com/organvm/limen/issues/2240) through
  [#2246](https://github.com/organvm/limen/issues/2246)
- Conduct receipt: none; this was an explicitly authorized direct-session preflight, not a formal
  leaf claim, lifecycle transition, or substitute for the dependency DAG
- State: **PREPARED/PREFLIGHT**; `counts_as_closure=false`. No C09 leaf or P10 phase predicate was run or satisfied.

## Exact source and custody receipts

| Owner | Exact remote receipt | What C09 consumes |
| --- | --- | --- |
| C00/P00 control plane | merged Limen PR [#2300](https://github.com/organvm/limen/pull/2300), merge commit `fbab1543a863ba2a86546de1eb31bdb9f0f50388` | C00/P00 is closed. The historical Agy/non-Codex identity gate is superseded and must not be reintroduced. |
| P02 evidence and adjudication | marked phase receipt [#2172](https://github.com/organvm/limen/issues/2172#issuecomment-5270095170), accepted main `8faa5fb9899231ebf5f87e78bb171544c11b79d7` | P02 is formally closed; this removes the former evidence dependency without promoting later phases. |
| C03 identity/offers | Limen PR [#2312](https://github.com/organvm/limen/pull/2312), merged from `b6af8086c9050634313f519c29a6dfcb922c3721` as `8f89ad16ca1df84b00cb8227c88f368d0d64631a`; accepted W01-W06 ancestor `c94bc3748fcf2d1dc802a4bae972df23d9a9fbec` | Current Audit/Install/Retainer artifacts are reversible preflight; formal acceptance stops at W06. W07/#2188 remains open for five genuine independent readers; C09 does not duplicate or satisfy it. |
| C04 proof experience | Limen draft [#2313](https://github.com/organvm/limen/pull/2313) at `543fa28df52c9db7be3b7307019dcf209361d0b9`; portfolio PR [#220](https://github.com/organvm-vii-kerygma/portfolio/pull/220), merged from `8974543ba9675ed0504141895812476efef5dd80` as `a01b6d85f78d2d744c0c994f7220081bb54a85c5` | PREPARED executable proof and experience contracts only; neither is formal phase evidence. |
| C05 delivery OS | private PR [#135](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/135), merged from `432c31ea6bcaf2c175b0fde08b6e1733fe4c2926` as `9172619633bb9a09ea3a05eae9f48e987f2b3e7d`; public relay [#2315](https://github.com/organvm/limen/pull/2315), merged from `d31ce37a85adf5d2e448dab8273a61e388f1e589` as `7a0682722185d17095a0b44de17d4bd5cf3284dd` | Executable W01-W08 delivery contracts, custody boundaries, and the authoritative proposal/SOW/decision/acceptance templates. C05 remains PREPARED and does not close P11 while its dependencies remain unsatisfied. |
| C06 public surfaces | portfolio draft PR [#221](https://github.com/organvm-vii-kerygma/portfolio/pull/221) at `0f09d22c051b2f84bb872c07819bf6a22d347a4b`; Limen relay [#2317](https://github.com/organvm/limen/pull/2317) at `4eb50463b7f4136b47a103c9792c1ded5caf7873` | PREPARED only. Exactly three directions remain **UNSELECTED**; no rendered surface or deployment is authorized. |
| C07 private inbound | Limen draft [#2318](https://github.com/organvm/limen/pull/2318) at `947921af6c1101acda6b1085d45381a393f3b20a` | PREPARED private-intake and threat-boundary contracts; no message, route, or external effect. |
| C08 proof-led content | draft Limen PR [#2316](https://github.com/organvm/limen/pull/2316) at `78736b8133c98e59d85069ea54eba2f20ed7b0a2` | PREPARED claim-source, correction/withdrawal, and attribution contracts. No publication or send occurred. |
| W01 public-safe package | Current branch `codex/psp-c09-qualification-conversion-relay`; exact integration head is carried by PR #2322 | ICP, committee, triggers, pains, disqualifiers, evidence signals, deterministic scorecard, and ten synthetic accounts. |
| W02/W03/W05/W06/W07 private package | PR [#136](https://github.com/organvm-iii-ergon/collaboration-operations-platform/pull/136), merged from `cd92697d596f674c9ddfc56edc919317ffb463e2` as `53784482af1a5b213dd21df7ab5bc2bd38f90f18` | Executable qualification, consent/authority, no-sign graph, CRM-safe projection, draft valves, deterministic scenarios, recruiter constraints, objection ledger, and synthetic conversion runtime. Its proposal-decision artifact is an internal conversion projection only; private #135 owns the reusable commercial templates. |
| W04 non-routable package | portfolio draft PR [#222](https://github.com/organvm-vii-kerygma/portfolio/pull/222) at `ed233074976dd566cb24a500d9ed95285769ddc2` | Executable local CTA/funnel contract and synthetic tests. No page, route, component, style, or transport is present. |

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
| W01 | `python3 scripts/positioning-qualification-preflight.py --check` → `status=ok`, 10 synthetic accounts, 8 exact assignments; focused pytest → 8 passed; Ruff → passed |
| Private conversion | focused qualification/conversion Vitest → 15 passed; TypeScript → passed; complete unchanged-tree Vitest before the terminal-route patch → 29 passed; build and no-plaintext → passed; package-owned Prettier → passed |
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
