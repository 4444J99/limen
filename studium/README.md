# The Studium — a personal transmission curriculum (private-classes skin)

**What it is (Anthony's words):** not "reading books" — a **transmission curriculum**: epic,
scripture, language, handwriting, translation, commentary, and music, woven into one daily practice.
Read the canon; copy the original script by hand; translate a small unit; compare translations; write
one interpretive note; listen to one fitting classical composition; log the resonance. *The daily
composition is a second commentary system; the handwriting a third; translation is where the book
becomes an encounter.*

This is the **personal self-study face** of the one education organism — a sibling to the Derek
narrative program (the canonical 1-learner, reading-anchored, mentor-coached private-classes skin). It
**wires to** the shared kernel (the 5 primitives, the studium-generale Provost, the Wings artifact
framework, the reading-group community patterns); it does **not** absorb the institutional classes.

## Kernel mapping (Member · Mandate · Progression · Standard · Governance)
- **Member / Learner** → Anthony (the reader).
- **Mandate / Quest** → read the canon (Iliad → Odyssey → Aeneid → Metamorphoses → Divine Comedy →
  Bible/Torah → Qur'an → Beowulf → Canterbury Tales, an Eastern counter-system, Gilgamesh as prologue)
  *with* original-script handwriting + translation + a fitting daily classical composition. Main
  question per work in `canon.yaml`.
- **Progression** → the daily protocol (`protocol.yaml`) walked across the canon by a reading cursor,
  along a chosen ordering (`orderings.yaml`) at a chosen pace (`paces.yaml`). All paths/paces/depths
  are surfaced as living choices — *no reduction* ([[distillation-not-reduction]]).
- **Standard / Rubric** → `rubric/` — comprehension, handwriting proficiency, translation, music
  engagement (the day's KEEP/REPLACE on each pairing).
- **Governance / Institution** → Anthony as his own Provost; optional credentialing via the
  studium-generale SGO if/when he wants to formalize.

## Layout
```
studium/
  _seed/            his verbatim source (Iliad I arc, spec, directives) — provenance, never overwrite
  canon.yaml        master work list (corpus paths, source rails, divisions, main questions, orderings)
  orderings.yaml    all reading paths (interleaved / western→eastern / chronological), switchable
  paces.yaml        gentle / standard / intensive portions, switchable
  dominant-force.yaml  force → musical requirement + composer hints (the reading↔music spine)
  daily-page-template.md  his daily-page schema (exported pre-filled each day to ledger/)
  protocol.yaml     the daily study protocol (time budgets, the 7-step loop)
  thesis.md         the working thesis (how civilizations encode their forces)
  music/<work>/book-NN.yaml   curated force-matched arcs (his gold-standard format; Iliad seeded)
  essays/<work>/...           publishable per-book essays (the "why each track fits" prose)
  scripts/<lang>.md           per-script learning (alphabet/ductus · glossed reading · grammar)
  community/discord-plan.md   the (simplified) community server
  publish/_drafts/            Wings multi-channel drafts (posts/threads/playlists) — sends nothing
  rubric/                     the four rubrics
  ledger/                     exported daily pages (handwriting log)
```

## Runtime
`scripts/studium.py` renders today's passage (reading + script drill + glossed translation +
force-matched music + all orderings/paces/depths visualized) to a self-contained face at
`http://127.0.0.1:8787/studium.html`, an exported daily-page in `ledger/`, and a daily push. State
(cursor, ordering, pace, depth, streak) lives in `logs/studium-state.json` — editable; the face shows
every avenue and lets him switch. The Studium is also registered as a corpus-converge face so the
daemon keeps distilling new material into it.
