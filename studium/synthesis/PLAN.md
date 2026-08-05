# Synthesis layer — the cross-canon vertical axis

> Operationalizes [`../thesis.md`](../thesis.md). The daily face ([`scripts/studium.py`](../../scripts/studium.py))
> reads **across** a work — one book answering many encodings on a given day. This layer reads **down** a
> concept — one encoding (violence, law, memory, fate, …) answered by many traditions at once, with the
> Eastern works set as **counter-systems** to the Western line, not appendix.

## Pieces
- [`concepts.yaml`](concepts.yaml) — the spine: 14 concepts × the works that encode each (and *how*) × the
  nearest dominant force (coloring anchor) + the counter-system pairings. Derived from `../canon.yaml` +
  `../dominant-force.yaml`.
- [`scripts/studium-synthesis.py`](../../scripts/studium-synthesis.py) — the face renderer →
  `web/app/out/synthesis.html` (mirrored to `public/`), served at `127.0.0.1:8788/synthesis.html`.
  Fail-open, atomic write, meta-refresh — same limen face idiom as `studium.py`.
- `<concept>.md` — one prose essay per concept, tracing it across the works (the file the face links to).
- [`counter-systems.md`](counter-systems.md) — the Eastern↔Western pairings as a single essay
  (the Gita against Achilles, the Dao against force, the Heike against the Iliad).

## The 14 encodings (status ✓ = essay authored)
| Concept | Force (color) | Essay |
| --- | --- | :--: |
| violence | wrath | ☐ |
| law | law | ☐ |
| memory | memory | ☐ |
| fate | fate | ☐ |
| sacrifice | sacrifice | ☐ |
| speech | revelation | ☐ |
| revelation | revelation | ☐ |
| empire | kingship | ☐ |
| desire | desire | ☐ |
| death | grief | ☐ |
| return | return | ☐ |
| transformation | metamorphosis | ☐ |
| salvation | salvation | ☐ |
| comedy | comedy | ☐ |

> Statuses are authored gap-driven (no empty stubs). The face shows "essay pending" until a `<concept>.md`
> exists, then links to it automatically.

## Method (per concept essay)
Open with the encoding (what is *fate*? what is *return*?). Walk 4–6 works from `concepts.yaml` showing how
each tradition answers it — quote the work's main question, name the force the music engine couples to it,
and surface at least one counter-system tension (a Western statement met by an Eastern answer). Close on what
the chorus of answers reveals that no single work could. One page; publishable prose (mirrors the essay layer).
