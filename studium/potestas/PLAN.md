# POTESTAS — power literacy as a studium track

> The study of how influence actually works: what the mechanisms are, how to **detect** them, what
> counters them, and — the part nothing else in this literature does — **which famous findings are
> dead.** Program: [organvm/limen#2077](https://github.com/organvm/limen/issues/2077).

## What this track is

A **recognition corpus**, not a playbook. The 48 Laws, Cialdini's principles, the propaganda model,
and the attention economy are documented here as **detection signs** — how a thing looks when it is
being done, and what to do about it — never as operating instructions.

That is a decision with a reason, and the reason is not squeamishness. The research this track
derives from states it directly:

> manipulation works best in low-trust, one-shot, low-transparency settings, and **degrades or
> backfires in repeated, high-transparency relationships.**

Which inverts into the sharpest instrument in the whole corpus: **if someone's approach toward you
only works while concealed, they have classified the relationship as non-repeated.** You need no
theory of their intent. The tactic reports the classification.

## Why it lives in `studium/`

Because the counter-system doctrine is already here. `../synthesis/counter-systems.md` states it —
*the work is its own adversary* — and the Dao De Jing sits in `../reading/tao-te-ching.md` under
*"What is the way that is not forced?"*, characterized in the curriculum seed as **"anti-heroic,
anti-force, anti-overassertion."**

That makes it the literal **anti-48-Laws, already in the canon, with a reading orientation
written.** Nothing needed importing. It needed pairing.

## The root

Everything derives from one registry. Adding a mechanism is **one entry**, never a hand-edited
consumer — the same rule GATES, SENSORS, and PARAMETERS already enforce.

| Artifact | What it is | State |
|---|---|---|
| `mechanisms.yaml` | The registry — id, family, definition, **evidence grade**, sign, counter, instance, inward | ✓ |
| `replication.md` | The epistemic-hygiene ledger: which findings are dead, and the citation that killed each | ✓ |
| `../rubric/disclosure.md` | Disclosure priced to demonstrated reception | ✓ |
| `../../scripts/check-potestas.py` | The Ω predicate — 7 rules + the PII boundary | ✓ |
| `drills/` | Inoculation drills, derived from registry `sign` fields | #2100 |
| `reading/` | Per-source-family orientations | #2094–#2098 |
| `who-benefits.md` | The one-page emotion-provenance instrument | #2101 |
| `protocol-financial-decisions.md` | No consequential decision on a synchronous channel | #2105 |
| `protocol-attraction-present.md` | Pricing before evidence of reception | #2106 |
| `prestige-ledger.md` | Dominance vs prestige, applied | #2107 |

## The Ω predicate

`python3 scripts/check-potestas.py` — exit `0` ⟺ every mechanism carries a definition, an
**evidence grade** (required, no default), a detection sign, a counter, and an instance pointer;
every `robust` claim carries a citation; **and no `debunked` mechanism is load-bearing anywhere.**

That last rule is the point of the track. Ego depletion collapsed from d=0.62 to **d=0.04**. Power
posing was disavowed by its own first author. Nudge shows *"no evidence"* after publication-bias
correction. Kalla & Broockman put conventional political persuasion at **zero**. A registry where
`evidence: debunked` is a first-class field, enforced by a gate that refuses to let a dead finding
carry weight, is the one artifact here that cannot be googled.

## Hard constraints

- **PUBLIC track, private evidence.** Mechanisms and rubrics are general and publish. Every worked
  instance lives in the private overlay behind an **opaque id**. The predicate enforces this rather
  than trusting it — the failure is irreversible, because a public repo's history keeps what a later
  commit removes.
- **Diagnostic, never gatekeeping**, per `../rubric/seminar.md`. Forward-looking, general to any
  counterparty, slow cadence, self-scored.
- **No per-person score, ever.** No index, no history, no trend line about any individual. A file
  that accumulates evidence about one person is a dossier, and building one is a way of continuing
  to think about them while calling it study.
- **Publishing is a human gate** (`../_seed/directives.md`) — never auto-post, never automatic.

## The agent layer, inverted

The source material proposed encoding the 48 Laws as agent operating principles. This track ships
the **opposite**: `AGENTS.md` gains the invariant *no play is ever run on the principal* (#2108),
with its forbidden set **derived** from the `inward: true` rows here rather than hand-listed.

The fleet is the most repeated, highest-transparency relationship its owner has, which makes
concealment-dependent laws not merely wrong there but **inoperative** — and, worse, pointed at the
one person the system exists to serve.
