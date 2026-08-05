# The Studium — a personal transmission curriculum (private-classes skin)

**What it is (Anthony's words):** not "reading books" — a **transmission curriculum**: epic,
scripture, language, handwriting, translation, commentary, music, and film, woven into one daily (and
weekly) practice. Read the canon; copy the original script by hand; translate a small unit; compare
translations; write one interpretive note; listen to one fitting classical composition; weekly, watch
one film that relates; log the resonance. *The daily composition is a second commentary system; the
handwriting a third; a film that relates a fourth; translation is where the book becomes an encounter.*
And it is built to become a **multi-medium seminar** — a community that interacts across all these
mediums, stages and battle-tests ideas (`community/`), and packages every interaction as data
(`analysis/`). See [`thesis.md`](thesis.md).

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
  engagement (the day's KEEP/REPLACE), **film engagement** (the fourth commentary), and **seminar**
  (how a claim survives trial — the war zone). All diagnostic, never gatekeeping.
- **Governance / Institution** → Anthony as his own Provost; optional credentialing via the
  studium-generale SGO if/when he wants to formalize. The **seminar** (`community/`) is the class as
  lab + arena; the **analysis** layer is its measurable record.

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
  film/<work>.yaml            the FOURTH commentary system — force-matched film companions (Iliad seeded)
  film/object-lessons.md      the selection ethos (fitting · not obvious · from film history) + the bridge
  film/object-taxonomy.yaml   the tracked-object dictionary (milk/mirror/clock/…) ↔ objectlessons.film
  essays/<work>/...           publishable per-book essays (the "why each track fits" prose)
  synthesis/                  the vertical axis — concepts across the canon + counter-systems (a face)
  scripts/<lang>.md           per-script learning (alphabet/ductus · glossed reading · grammar)
  community/                  the multi-medium seminar: discord-plan · interaction-model ·
                              current-inquiry (the TBR-book slot) · trial-protocol (the war zone)
  analysis/                   packaging the practice as data — events-schema + the analysis face
  publish/_drafts/            Wings multi-channel drafts (posts/threads/playlists) — sends nothing
  rubric/                     the six rubrics (comprehension · handwriting · translation · music ·
                              film · seminar) — diagnostic, never gatekeeping
  ledger/                     exported daily pages (handwriting log) — the solo data stream
```

## Runtime — three faces at `127.0.0.1:8788`
- `scripts/studium.py` → **`studium.html`** — today's passage (reading + script drill + glossed
  translation + force-matched music + a 🎬 **Film of the Day** — one *object-lesson* film for today's force,
  fitting + not obvious, with the rest of the companion below + day's-force films highlighted + Letterboxd
  "seen" marks + all orderings/paces/depths). Exports a daily-page to `ledger/` (with a `FILM / OBJECT LESSON`
  line) and a daily push. State lives in `logs/studium-state.json` — editable; the face shows every avenue.
  Reads ACROSS a work.
- `scripts/studium-letterboxd.py` — ingests his Letterboxd watch history (CSV export → RSS) →
  `logs/letterboxd-history.json` (read-only, fail-open; never posts). `scripts/studium-objectlessons.py` —
  joins the film picks to his 253-film **objectlessons.film** DB by Letterboxd slug → `logs/objectlessons-crosswalk.json`.
- `scripts/studium-synthesis.py` → **`synthesis.html`** — the cross-canon concept web + counter-systems.
  Reads DOWN a concept.
- `scripts/studium-analysis.py` → **`analysis.html`** — packaging the practice as data: force
  distribution across the authored canon, concept reach, his ledger cadence, and (staged) interaction
  events. Reads the practice itself.

All three are self-contained (meta-refresh, pure string templating, fail-open — no network, cannot time
out). `scripts/studium-validate.py` is the acceptance gate for every arc **and** film companion. The
Studium is also registered as a corpus-converge face so the daemon keeps distilling new material into it.
