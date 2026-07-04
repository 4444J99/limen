# Contributions Organism — SPECVLVM — KERNEL (the mirror architecture)

> **Doctrine (load-bearing, repeated everywhere in this organ):** we contribute
> **outward** to study other projects' wiring and improve **inward**. The
> upstream project is the *lens*, not the subject — the mirror exists so the
> system can see itself in what others build. Community standing and name
> recognition are real products, but they are **byproducts** of genuine,
> useful contributions; the organ never optimizes for them directly, and it
> never sends: every outbound act (PR, comment, bump, post) stays in human
> hands, permanently.

---

## Why this organ exists

Big technology companies run an **OSPO — an Open Source Program Office** — for
exactly this reason: a standing institution that contributes to upstream
projects in order to (1) learn how the best systems are wired, (2) pull that
knowledge back into the company's own engineering, and (3) accrue reputation
and community gravity as a side effect. A solo operator has the same motive
and none of the apparatus — contributions happen in bursts, tracking decays,
and the learning is never routed anywhere.

The apparatus was in fact already built here, in pieces, many times
([[excavate-before-redoing-solved-work]]): a hub, two engines, twenty-plus
workspace repos, a backflow manifest. What was missing was the **institution**
— one pillar that owns all of it — and the **mirror**: the portal face that
shows the whole practice at a glance. This organ is that convergence, not a
rebuild.

## The 5-primitive kernel, mapped to contributions

| Primitive | Contributions meaning | Concretely |
|---|---|---|
| **Member** | an upstream relationship | the external project + its maintainers: repo, norms, review culture, the standing tie we hold there |
| **Mandate** | the contribution campaign | why we are contributing *there*: what wiring we want to study, what the useful change is |
| **Standing** | contribution lifecycle state | scouted → workspace → PR open → merged / closed / post-close → backflow absorbed |
| **Standard** | the upstream's own bar + our protocol | their CONTRIBUTING/CI/review rules; our outreach protocol (staggered bumps, no spam, genuine value only) |
| **Governance** | the human gate + the dispatch gate | every outbound send is his hand; executor packets follow the PLAN-06 dispatch gate (owner, scope, predicate, receipt) |

## Fractal deployment

- **MACRO face** — an **OSPO-in-a-box**: the scout → workspace → campaign →
  monitor → backflow machinery plus this mirror, as a pattern any solo
  operator or small org can hold to run a disciplined upstream-contribution
  practice.
- **MICRO face** — the live ORGANVM practice: the hub (`organvm/contrib`,
  generated LEDGER), engine A (`organvm_engine.contrib` in
  `a-organvm/organvm-engine`), engine B (`contrib_engine/` in
  `a-organvm/orchestration-start-here` — scanner, orchestrator, campaign
  sequencer, outreach tracker, backflow router), 22+ `contrib--*` workspace
  repos, ~19 open upstream PRs (fastmcp, MCP SDKs, anthropic-sdk-python,
  langgraph, temporal, dapr, k6, agentkit, pydantic-ai, …), and the backflow
  manifest in `organvm-corpvs-testamentvm`.

## The mirror (this organ's face)

`scripts/contributions-organ.py` renders the practice as **proof categories**
— merged · open · no-PR · closed · protocol-due · post-close — into
`organs/contributions/MIRROR.md` plus the `logs/contributions.json` health
signal. It consumes **hub-ledger outputs only** (never raw sessions or private
archaeology), redacts local paths and private notes, and — when the hub is
unreachable — renders its own staleness receipt rather than pretending: an
honest mirror shows its dust. This resolves PLAN-06 owner packet 04
(`docs/current-session-fanout/PLAN-06-contrib-mirror.md`): **limen is the
named owner surface for the public proof mirror.**

## First slice

1. This kernel + the charter (shipped together).
2. The mirror generator + its first rendered face and health signal (shipped
   together, on the beat).
3. Next: PLAN-06 owner packets 01–03 — restore/refresh the hub ledger
   (`refresh-ledger.py` seed root), then reconcile engine A and engine B
   behind the one hub-ledger contract.

## Hard guardrails

- **Never sends.** No comments, bumps, PRs, issues, or posts from the organ —
  outbound is queued as receipts for the human hand (the PLAN-06 planner
  decision, unchanged).
- **Genuine value only.** A contribution exists because the change is useful
  to the upstream, not to farm reputation; stagger rules and outreach
  protocol are part of the Standard, not optional etiquette.
- **Public surface is redacted.** The mirror renders repo names, PR
  references, and states — never local paths, private notes, or session
  material.
