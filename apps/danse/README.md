# danse

A room that never repeats, built from one afternoon.

On **20 June 2017**, 161 photographs of a dancer were made in a single session — an
apartment room with a row of framed classic-horror posters standing against the wall,
carpet, a guitar. The camera barely moved. On **25 July 2017** three of those frames
were cut apart by hand and recomposed into a tiled composite: fragments of her, at
different scales and opacities, over one continuous room.

Then it sat for nine years.

This is the machine that does it now — and doesn't stop.

## What it is

A seeded generative engine. Photographs hang as translucent planes at different depths
and angles in a 3D room; the engine selects fragments — anatomy, not rectangles — from
different frames of that afternoon and composes them. It never repeats, and every state
it can reach has a number.

Five faces, one engine:

| Face | What it is |
|---|---|
| **The film** | A deterministic 4K render. A fixed cut of an unfixed thing. |
| **The page** | The engine running live, drifting, forever. |
| **The seed** | Any moment is addressable — `#s=<seed>&t=<seconds>` returns exactly it. |
| **The visitor** | Bring your own photograph; join the vocabulary. Entirely in your browser. |
| **The room** | The same engine driving real projectors onto real hanging scrim. |

## The three decisions

**Projective texturing, not per-plane UVs.** Every photograph is registered to one room
frame, and every fragment samples through a shared room-projector matrix. Two planes at
different depths and angles therefore place the floor line and the poster line on the
*same screen-space lines* — the continuity is a property of how pixels are fetched, not
a rule the generator has to remember.

**`projK` is the spine.** One uniform mixes plane-local UVs against projector UVs. At
`1.0` the stage collapses into the flat 2017 composite; at `0.0` it opens into a room.
Animating it *is* the reveal: the still was always a room.

**The engine is a pure `f(seed, t)`.** No accumulated state, no `requestAnimationFrame`
inside `engine/`. That single property buys deterministic film renders, O(1) seek,
shareable permalinks, and multi-projector sync for free.

## What the corpus turned out to be

Measured, not assumed — and it changed the design:

- **161 of 162 frames carry a person matte** at 11–18% coverage, quality 0.987–0.998.
- **Body-pose detection finds joints in only 65**, and never reaches 8 confident ones.
  The histogram says why: knees 40%, ankles 37%, hips 35% — then shoulders 3%, faces 2%.
  **The shoot frames legs.** There is no upper body for a whole-person model to anchor on.
- So the **matte is the primary instrument** and pose is an optional refinement. Gating
  on pose would have thrown away 60% of a corpus in which the subject is unmistakably
  present.
- **The camera is locked off.** The poster row sits at identical pixel coordinates across
  frames, which makes registration nearly free and is exactly why the 2017 hand-cuts
  aligned so cleanly.
- **The 2017 composite is registered to the room to within 0.4% of frame height.** Its
  horizontal seams (0.4622, 0.4857) land on the poster-rail transition measured
  independently from the one dancer-free frame (0.4661, 0.4886). The artist's own rule
  was *cut on the architecture* — so the engine derives its bands from the room rather
  than inventing a grid.

## Layout

```
apps/danse/
  index.html   the living page          film.html    render harness (no UI, no rAF)
  studio.html  seed browser             join.html    visitor upload
  engine/      gl · rng · room · grammar · renderer · corpus · clock · profile
  corpus/      manifest.json · plates/ · masks/ · transmutations/
  pipeline/    corpus preparation (local only, never deployed)
  render/      deterministic offline renderer (local only, never deployed)
```

## Pipeline

Runs on this machine, against Photos.app. Originals never enter git — `.work/` is
ignored, and only the code that regenerates everything is versioned.

```bash
cd apps/danse/pipeline
./0_export.sh                      # Photos ▸ etcetera ▸ ballerina danse ▸ danse → .work/raw
./1_vision/build.sh                # dependency-free Swift + Vision.framework
./1_vision/danse-vision .work/raw .work/vision
python3 2_measure_transmutation.py .work/reference/T-2017-full.png \
        --room-frame .work/raw/IMG_1570.JPG -o .work/reference/transmutations.json
```

## Provenance

Nothing is synthesised. Every pixel is a photograph taken on 20 June 2017. The pose
model is a measuring instrument — it locates a knee; it does not draw one. There is no
diffusion, no training on anyone else's work, and no synthetic frame anywhere in this
project.

## Run

Pure static — no build step, no dependencies.

```bash
cd apps/danse && python3 -m http.server 8080
```

Plan: [`docs/plans/2026-07-30-danse-generative-engine.md`](../../docs/plans/2026-07-30-danse-generative-engine.md)
