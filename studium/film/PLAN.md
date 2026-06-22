# Film layer — the fourth commentary system

> Reading · handwriting · translation · **music** were the three commentary systems. **Film is the
> fourth.** A film that "relates" is not illustration — it is an independent account of the same FORCE
> (wrath, fate, grief, law …) meeting the work on its own terms. Often a film from anywhere (Vietnam,
> the Eastern Front, a samurai apocalypse) encodes a force more truthfully than any direct adaptation.

## The shape
- **One `studium/film/<work>.yaml` per work** (not per-division — film is a *weekly* medium; the protocol
  is deliberately finite). Each: `principle` · `force_coverage` · `films: [{title, director, year, force,
  scene_or_theme, why, content_note}]`. Every `force` is a key of [`../dominant-force.yaml`](../dominant-force.yaml).
- **`adaptations:`** (optional) — direct films OF the work, with `scenes: [{division, force, scene}]` tying a
  scene to its book/canto. This is the per-division **overlay** where a real adaptation exists (e.g. *Troy* ↔ Iliad).
- **Gold standard:** [`iliad.yaml`](iliad.yaml) — 9 force-matched films across the poem's spectrum + the *Troy* overlay.

## How it surfaces
- **Daily face** (`scripts/studium.py`): a 🎬 *film resonance* card lists the work's films and **highlights the
  ones whose `force` matches the day's dominant force**, with legal watch links (JustWatch + search — never a
  pirated source, mirroring the music layer's YouTube/Spotify *search* links).
- **Community** (`../community/`): the weekly **Watch-Along** ritual screens one film; `#screening-room` is its surface.
- **Rubric:** [`../rubric/film-engagement.md`](../rubric/film-engagement.md) — film as a fourth reading, diagnostic not gatekeeping.
- **Validator:** `python3 scripts/studium-validate.py --film` checks every `force` ∈ taxonomy.

## Register discipline (mirrors the music layer)
The grief / lament / mercy films (the women's lament, the enemy humanized) belong to a work's **late** movement —
its death/catastrophe divisions — exactly as the music layer reserves the funeral-march register. Note this in
each `principle` and let `scene_or_theme` point the film at the right division.

## Coverage — status (✓ = `film/<work>.yaml` authored)
| Work | Film companion |
| --- | :--: |
| The Iliad | ✓ (gold standard) |
| *all other first-pass works* | ☐ — staged in [`../expansion-backlog.yaml`](../expansion-backlog.yaml) (`film` pillar) |
| *Tier-2 works* | ☐ — staged (after the first pass) |

> Breadth (the remaining ~24 + 5 tier-2 companions) is fleet work on his gate, in the Iliad format — NOT
> ground out solo ([[token-economy-overrides-ultracode]]). Each task: tag the work's forces → pick films that
> meet each force's register → justify every choice → `studium-validate.py --film`.
