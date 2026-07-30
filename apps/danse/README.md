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

## The 2017 piece, solved

Before evolving it, recreate it. Stage 3 does not approximate the composite — it **solves
it back into a score**: which of the 162 frames each region was cut from, and what
treatment was applied. The model per rectangle is

```
C  =  gain · S  +  lift          (per colour channel, least squares)
```

which is not merely noise-tolerant. Normal-blending a photograph over a light ground at
opacity `a` is exactly `gain = a, lift = (1-a)·ground`, and desaturating is exactly a
per-channel spread in gain. Several tiles come back at `gain ≈ 0.64, lift ≈ 0.36` — pairs
summing to 1.0. The solver was never told about opacity; it fitted a line, and the line
came back as the 2017 hand-treatment in the two numbers a shader takes.

**The result** — [`corpus/score-2017.json`](corpus/score-2017.json), 256 rectangles,
**32.3 dB PSNR**, mean absolute error 0.015:

| rectangles | 32 | 64 | 128 | 256 | 384 | 512 |
|---|---|---|---|---|---|---|
| **PSNR (dB)** | 25.98 | 29.29 | 31.18 | 32.27 | 33.11 | 33.59 |
| **frames used** | 21 | 34 | 48 | 77 | 90 | 110 |

Reading the curve: the piece is *about a hundred rectangles* — past that, fidelity is
bought a fifth of a dB at a time. Which is a statement about how much grammar the engine
actually needs.

What the solve found:

- **77 of 256 rectangles need two source layers**, at a 15% error-reduction threshold.
  The composite is not a mosaic of opaque tiles; roughly a third of its area is two
  photographs superimposed, and a one-source model produces *diagonal* residual ridges
  where a translucent limb crosses the frame beneath it.
- **77 distinct frames of 162 are in play** — but the distribution is steep. `IMG_1611`
  alone accounts for 17.5% of the picture and `IMG_1615` another 14.3%.
- **The major horizontal band edges land at 0.500 and 0.799** of frame height. Stage 2's
  independent seam measurement of the same composite said 0.486 and 0.802, and the room's
  own poster rail — measured on the one dancer-free frame — sits at 0.489. Three
  measurements, three methods, one architecture.

![provenance](reference/score-2017-provenance.png)

*The provenance map: one hue per source frame. This is the piece's genome — which instant
of that afternoon each region was drawn from. It is also the fastest correctness check
available: a real solve reads as flat contiguous plates, a failed one reads as noise.*

## Three grammars, one operation

The transmutation practice this engine generalises is older and wider than the ballet
piece. Analytic cubism's actual move is not angular shapes, it is **simultaneity**:
several viewpoints of one subject coexisting in one picture plane. The 2017 works are
three cut-geometries over that identical operation —

| Work | Corpus | Cut |
|---|---|---|
| **danse** | 162 frames, one locked-off room | rectangular grid, aligned to the room's architecture |
| **noonlight** | 21 frames, one face turning | polygonal shards with white kerf, over sky |
| **b/w remix** | supplied frames, one face | staggered bands keyed to anatomy — eyes, lips, hair, arm |

Different scissors, same cut. So `engine/grammar.js` carries a **cut vocabulary** rather
than a hard-coded grid, and the seed chooses among the geometries.

And this is why the room is not decoration. Picasso flattened his viewpoints into the
picture plane because a canvas has no depth to hang them in. Screens at different angles,
depths and transparencies put them back. `projK = 1` is literally that flattening;
animating it toward `0` is literally its undoing.

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
python3 3_reconstruct.py --target .work/reference/T-2017-full.png \
        --frames .work/raw --depth 2 --leaves 256 -o .work/reference/score-danse.json
python3 3_reconstruct.py ... --sweep 32,64,128,256,384,512   # rate/distortion curve
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
