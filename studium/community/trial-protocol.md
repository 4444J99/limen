# Trial protocol — the war zone (how a claim is stress-tested)

> The seminar's arena. A *claim* about a passage — an interpretation, a counter-system reading, a thesis
> about how a work encodes a force — is staged, defended, attacked, and either survives, is revised, or
> falls. The point is not to win; it is to make the idea earn the right to be transmitted. Scored by
> [`../rubric/seminar.md`](../rubric/seminar.md); logged as data via [`../analysis/events-schema.yaml`](../analysis/events-schema.yaml).

## Why the canon is its own adversary
The opposition is not invented for sport — it is built into the curriculum. The Eastern works are
**counter-systems** to the Western line (`../synthesis/counter-systems.md`): the Gita against Achilles,
the Dao against fatum, the Heike against martial glory, the Analects against Sinai. So a claim about the
Iliad's wrath is *already* opposed by the Gita's renunciation. The trial stages a collision the canon
has been holding for three thousand years.

## The five steps
1. **CLAIM** — state a falsifiable thesis tied to a specific work + division, in one sentence.
   *e.g. "The Iliad makes wrath the truth of heroic identity (Books 1, 18–22)."* → emits `claim`.
2. **GROUND** — the proponent cites the text: line, scene, or structural feature that the claim rests on.
   No grounding, no trial — an ungrounded claim is sent back to the breeding zone.
3. **ATTACK** — one or more challengers bring the **strongest** objection, by default the work's
   counter-system. The rule is steelman, not strawman: pressure the claim at its actual load-bearing
   point. *e.g. "The Gita's yoga shows the same warrior on the same field choosing to dissolve the self
   wrath would serve — so wrath is a cultural choice, not a human universal."*
4. **DEFEND / REVISE** — the proponent either holds with new evidence, or concedes *precisely* what was
   refuted and **narrows** the claim. *e.g. → "Within the Greek heroic frame, wrath is identity's truth."*
   A sharp concession scores higher than a brittle defense.
5. **SCORE + LOG** — the *conduct* of the trial is scored on `../rubric/seminar.md` (1–4); the claim's
   **fate** (held / revised / refuted) is recorded separately as data, never as a grade. → emits
   `trial_round` (claim id, fate, force, work, counter-system used, seminar score).

## What a finished trial yields
A durable artifact, not a verdict: a thesis sharpened by the strongest available objection, plus the
strongest counter, plus what the collision revealed that neither side held alone. That artifact feeds:
- `current-inquiry.md` — the season's dossier (which side keeps winning, where the claim narrowed);
- `../synthesis/concepts.yaml` / `<concept>.md` — a refinement to the encoding;
- a Watch-Along or reading prompt — the next week's orbit;
- `../analysis/` — the contested-concept heat-map (the "packaging as data analysis").

## Conduct rules (keep the arena fair)
- **Steelman the opposition.** Refuting the weakest objection scores 1; seeking the strongest scores 4.
- **Concession is strength.** Losing a trial well teaches more than never being tested ([[no-never-happens-again]]).
- **The text adjudicates, not status.** Evidence from the work outranks rhetoric or seniority.
- **One claim at a time.** A trial that sprawls into many claims is split into several.

## Posture (his gate)
This is the **format**, staged. Running live trials with real participants — and collecting their data —
is consent-gated and his to open (`interaction-model.md`, `../analysis/PLAN.md`). Until then, trials run
solo: a claim from his own daily note, defended against the canon's counter-system, scored, and logged to
his own ledger. The arena works at n=1; it scales on his go.
