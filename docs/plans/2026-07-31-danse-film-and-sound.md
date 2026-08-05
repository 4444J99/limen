# danse — root to leaf, alpha to omega

## Context

The root is finished and merged (`d55bd9fe`). The 2017 composite is an executable score, the empty
room is recovered from 162 photographs, and the engine reproduces the original at **31.60 dB against
a 31.61 dB arithmetic ceiling** — the render path is exact, and the remainder is WebP. `check-danse.py`
holds four invariants without a GPU.

What exists is an *instrument*. Nothing has been played on it. Every remaining deliverable — the film,
the stills, the Reels, the Times Square cut, the live page, the installation — is the same pure
`f(seed, t)` sampled differently. That is the whole architecture of what follows: **build the offline
renderer once, and every downstream artifact is a query against it.**

**31 days to the hard wall** (31 Aug 2026, 22:00 America/New_York — the register takes the cautious
reading of the call's ambiguous "11:00 PM EST"). Target file date **20 Aug**.

### Two facts established this session that change the design

1. **The wall is Stephen King's *Danse Macabre*.** The recovered room shows *Creature from the Black
   Lagoon*, *The Phantom of the Opera*, *Dracula*, *The Invisible Man* — propped on the floor, not
   hung — and Pink Floyd's *The Wall* at the far left, plus the classical guitar. The horror posters
   are not set dressing; the room is a deliberate homage to King's 1981 book. The title must
   acknowledge that lineage without lifting it.

2. **The sound source is real audio from that room** — varied material, not room tone. This is
   better than what was planned, and it changes the sound architecture from *synthesis* to *a second
   corpus*: the same select-by-seed machinery, running on recordings instead of photographs.

---

## The title

**THE THING WITHOUT A NAME**

King's own phrase from inside *Danse Macabre* — his third archetype, the Frankenstein figure, the
monster assembled from parts of other bodies. The lineage is exact and citable; the title is not.

It also describes the machine literally: the engine cuts a real body into ~100 rectangles and
reassembles it as a body that never existed, in a room that never existed, and never makes the same
one twice. The only name any of them has is a hex number — which is exactly what the film's last
frame says:

```
THE THING WITHOUT A NAME
Anthony J. Padavano · 6:30 · 2026

                            final frame, four seconds, white on black:

                                        seed 0x3F2A1C
```

*Runners-up if this doesn't sit right: **NO SUCH BODY**, or **THE INVISIBLE ROOM** (the room is
recovered from 162 photographs, not one of which shows it empty).* The title lands in `program.json`
as data — changing it is a one-line edit, not a re-render.

---

## The whole arc

```
ROOT      corpus + score + invariants ──────────────────── DONE, merged d55bd9fe
            │
SPINE     engine.js · program.json · clock(seed,t,PROGRAM) ── A  the film as declared data
            │
TRUNK     film.html → render.py → sink.mjs → ffmpeg ──────── B  one offline renderer
            │                                    │
            │                             sound corpus ───── C  the room's own audio
            │                                    │
BRANCH    ┌─┴────────┬──────────┬─────────┬──────┴──┐
          6:30       2:50 TSq   ≤45s      6 stills  Reels ── D  all one query
          master     cut        trailer   4K        vertical
            │
LEAF      package/ → check.py --package → Vimeo → Submittable  E  31 AUG
            │
EXTEND    ┌─┴──────────┬────────────┬──────────────┬─────────────┐
          fleet homing  live page    join.html      the room      the ladder
          chamber/gate  Pages+seed   visitor upload PoC → spec    Cinedans, TSq,
          done.sh       mechanic     (post-31 Aug)  → pitch       Locust, Mignolo
```

Everything below the trunk is a **parameter change, not new code**. That is the leverage, and it is
the reason the renderer is worth building properly before anything is cut.

---

## A. The spine (days 1–4)

The film's five movements need capability the engine does not yet have, and they must arrive as
**declared data** — the same pattern this repo already uses for `gates.yaml` and `sensors.yaml`.

**`apps/danse/render/program.json`** — the film, as a registry. One entry per movement:
`{id, t0, t1, cut, camera:{azimuth,elevation,divergence}, density, projK, reseed}`. The 6:30 cut,
the 2:50 Times Square cut, a 10-second Reel and a single still are then *four windows onto one
program*, never four edits.

**`apps/danse/engine/engine.js`** — `step(corpus, seed, t, program) → {state, cast}`. Both
`index.html` and the new `film.html` call it, so the live page and the master can never diverge.
Today `index.html:84-101` hand-rolls this loop.

**`apps/danse/engine/clock.js`** — `state(seed, t, program)`. The program is an *argument*, so purity
survives; `check-danse.py`'s out-of-order evaluation still holds. Default program = today's single
dwell cycle, so existing behavior is unchanged.

**`apps/danse/engine/grammar.js`** — two new cuts, `CUTS` 3 → 5:
- `solo` — one plane, one whole photograph (movement ONE). The existing three all *partition*; none
  can express a single undivided frame.
- `figure` — anatomical assembly (movement STILLNESS): one near-complete body from many photographs,
  cast through the existing `corpus.choose(candidates, ...words)` against the per-frame `joints`
  already in the manifest.

**Resolve `IMG_1926`** — the one 750×1334 frame that is not from the 2017 camera. Mark
`registered: false` in `manifest.json`; `corpus.candidates()` skips unregistered frames so it never
enters a *generated* cut; the score path keeps it, because the 2017 solve genuinely used it (1.46% of
the composite). At 4K, projecting a phone screenshot through the 2017 camera matrix would be visibly
soft — this is the frame where that would show.

## B. The trunk — the offline renderer (days 4–9)

**`apps/danse/film.html`** — no `requestAnimationFrame` anywhere. `window.danse.renderAt(t)` resolves
once the frame is on the canvas. This is not stylistic: CDP `Runtime.evaluate` times out at 45s while
a rAF loop runs, which is why `verify.html` exists in the shape it does.

**`apps/danse/render/render.py`** — Playwright + **system Chrome** (`channel="chrome"`); bundled
browsers aren't installed and `chrome-headless-shell` has no GPU. **Assert the renderer string
contains "Metal"/"Apple" and abort otherwise** — one line that prevents rendering an entire film on
SwiftShader and noticing at the end. Capture path is PBO `readPixels` → polled `clientWaitSync` →
`getBufferSubData` → `Blob` → POST. Direct `readPixels` is 889 ms/frame; this is 45–70 ms.

**600-frame segments, one fresh browser process each** — not an optimization. Sustained blob churn
triggers `net::ERR_BLOB_OUT_OF_MEMORY`. Segmenting caps memory by construction, makes renders
restartable, and allows 2-way parallelism. Determinism is unaffected: segment *k* renders
`t ∈ [k·10s, (k+1)·10s)` from the same pure function.

**`apps/danse/render/sink.mjs`** — node HTTP receiver → `ffmpeg` stdin. `-vf vflip` (GL readback is
bottom-up); `prores_ks -profile:v 3` for the master.

**The `film` tier** — `4_corpus.py --tier film` builds full-resolution (3264×2448) plates locally from
`.work/raw`, ~250 MB, **gitignored**. Git keeps `browse` (512) + `screen` (1024) at 28 MB, which is
the web budget. At the `screen` tier a 1/16-frame tile blown to 4K is a 256px crop stretched to 960px
— soft. The film tier is a build artifact derived from material already on this disk.

**Determinism gate on day 9, not day 20** — render segment 3 twice, `shasum` both, require equality.
Any grain must be `hash(seed, frameIndex, pixel)`, never `random()`. This is the check that catches a
leak of impurity into the engine, and it is worthless if it runs after the schedule is committed.

## C. The sound — a second corpus (days 5–14, parallel)

Rights-clean by construction and now provenance-true. The design mirrors the visual engine exactly:

**`apps/danse/sound/resolve.py`** — locate and catalog the 2017-room recordings. *Not yet found on
this machine.* Leads, in order: **Photos.app via AppleScript** (the sanctioned channel — the same one
`0_export.sh` used for the 161 stills, and where video-with-audio from that afternoon would live);
iOS Voice Memos; `/Volumes/Archive4T`. Eighteen iOS GarageBand projects exist in iCloud but date
2014–2016 and are amp-preset guitar takes — a real bank of your playing, wrong room and wrong year.
Building the resolver rather than hunting by hand is the durable form; it re-runs when you point it
somewhere new.

**`apps/danse/sound/1_bank.py`** — analyze recordings into `bank.json` + normalized grains. Split
sustained vs transient by onset and duration; index each grain by spectral centroid, brightness and
decay — the audio analogue of the per-frame `figure`/`joints` index the photographs already carry.

**`apps/danse/sound/score.py`** — `f(seed, program) → stereo WAV`, the same seed as the picture.
- **Bed** — sustained grains from the room, layered low. This is what stops it sounding synthetic.
- **Depth → pitch + reverb send.** Each active plane voices one sustained grain; far planes lower and
  wetter. As the camera moves and depth order changes, *the chord literally is the spatial
  arrangement.*
- **Limb events → transients, decimated 80–90%.** Real material from that room. Throwing most away is
  the single decision that makes it read as choreographic rather than as data — the rhythm should be
  countable by a dancer.
- **Reseed → one sub-bass swell and a silence**, shortening across the four accelerating reseeds.

Deliver stereo, ~-16 LUFS integrated, true peak ≤ -1 dBTP (it may play outdoors at Soundscape Park).
Bake beat times into `program.json` so the cut stays deterministic.

## D. The cut (days 12–19)

One 4K60 ProRes 422 HQ master at 6:30. Everything else is a window on the same program: the 2:50
Times Square cut (Midnight Moment wants exactly 170s horizontal), a ≤45s trailer, six stills at
≥3840×2160 named `seed-0x….jpg` from distinct seeds, vertical Reels rendered natively — never
letterboxed — plus the H.264 1080p screener.

Movements: **ONE** (0:00–0:45, one unaltered 2017 photograph — provenance first) · **DIVISION**
(0:45–2:00, they learn the space is impossible) · **PHRASE** (2:00–3:45, countable by a dancer) ·
**STILLNESS** (3:45–4:45, one body that never existed, held longer than is comfortable) · **RESEED**
(4:45–6:30, visibly restarts three times, accelerating, cut to black mid-phrase). The infinitude is
delivered by that compression, not asserted.

## E. The package (days 19–20)

Stage `package/` + `attest.yaml`; run `apps/danse/submission/check.py --package <dir>` to exit 0. It
currently reports exactly one open item — "not staged" — with both former blockers cleared by
evidence and the fee confirmed at zero.

Vimeo private-with-password, **download enabled** — this is the #1 mechanical failure and Vimeo ships
with it off. No expiry before December. Submit via Submittable. File by **20 Aug**: panels see
timestamps.

---

## The extensible arc (after the trunk exists)

**Fleet homing** — the piece becomes a citizen of this repo rather than a folder in it:
`organs/artist/chambers/danse.yaml` (validate-artist.py rules 1–6; standing `CATALOGED` →
`EXHIBITED`), a `deploy_triggers.danse` row in `institutio/governance/gates.yaml` mirroring a new
`.github/workflows/deploy-danse.yml` byte-for-byte (`check-gates.py` enforces set equality), a
`gates.yaml` gate entry so `check-danse.py` runs in CI on danse paths, and an
`experience-surfaces.json` overlay — 28 MB against a 1500 KB estate default needs a declared budget,
not a silent exception.

**`apps/danse/done.sh`** — the executable predicate this repo requires instead of prose. Calls
`verify-scoped.sh`, `check-danse.py`, the determinism gate, the continuity gate (two planes at known
different angles → detected floor line within 2px), and `check.py --package`.

**Public surfaces** — Cloudflare Pages deploy; `studio.html` seed browser; the seed mechanic (the
site's *first* action generates a fresh seed, renders it live, and hands back a shareable image plus
a short URL — a seed someone else chose is a link, a seed with your name on it is an object);
`join.html` visitor upload via MediaPipe `pose_landmarker`, lazy-loaded, **after 31 Aug**.

**Socials** — the project gets its own handle, `@4444jj999` becomes the feed for your visual and
audio work. Ten posts in sequence, 2×/week from now. *The AI-chat brainstorm corpus is still not on
disk — both declared stores are missing — so this sequence is my design and marked swappable.*

**The room** — PoC shoot (~$185 of chiffon, PEVA, tulle, vellum) → digital twin → costed installation
spec → pitch artifact. This is what the interactive, in-a-real-space version is pitched from.

**The ladder** — Cinedans FEST (15 Sept, free, Out-of-Competition explicitly accepts installations —
pitch the room openly there), Times Square Midnight Moment (rolling, 170s), Locust Projects (watch
weekly from 1 Sept — the #1 target, $10k budget for *new installation work*), Mignolo Brussels
(13 Oct, European premiere before Miami notification), Miami-Dade Cultural Affairs (13 Oct).

---

## Files

| Path | Change |
|---|---|
| `apps/danse/render/program.json` | **new** — the film as declared data |
| `apps/danse/engine/engine.js` | **new** — `step()`, shared by live page and film |
| `apps/danse/engine/clock.js` | `state(seed, t, program)`; program is an argument, purity preserved |
| `apps/danse/engine/grammar.js` | `+solo`, `+figure`; `CUTS` 3 → 5 |
| `apps/danse/engine/corpus.js` | `candidates()` skips `registered: false` |
| `apps/danse/pipeline/4_corpus.py` | `--tier film` (3264px, local-only); `IMG_1926` → `registered: false` |
| `apps/danse/film.html` | **new** — no-rAF stepped harness |
| `apps/danse/render/{render.py,sink.mjs}` | **new** — Playwright/Chrome + PBO + segments; ffmpeg sink |
| `apps/danse/sound/{resolve.py,1_bank.py,score.py}` | **new** — the second corpus |
| `apps/danse/index.html` | calls `engine.step()` instead of its own loop |
| `apps/danse/done.sh` | **new** — the executable predicate |
| `scripts/check-danse.py` | extend: program schema, `solo`/`figure` partition, registered-frame rule |
| `organs/artist/chambers/danse.yaml` | **new** — chamber record |
| `institutio/governance/gates.yaml` | `+deploy_triggers.danse`, `+` gate entry for `check-danse.py` |
| `.github/workflows/deploy-danse.yml` | **new** — mirrors the trigger row exactly |
| `experience-surfaces.json` | payload overlay for the 28 MB surface |

Branch per concern off `origin/main`, PR each, self-merge on `scripts/merge-policy.sh` exit 0.
`.work/` (2.8 GB) and the `film` tier never enter git.

## Verification

1. `python3 scripts/check-danse.py` → exit 0 (extended with the program + registered-frame rules).
2. `apps/danse/verify.html` → REPRODUCTION HOLDS, ≥31.45 dB. The flat state must stay the 2017 piece
   after every engine change; this is the regression net for the whole spine.
3. **Determinism:** `render.py --segment 3` twice → `shasum` equal. Day 9.
4. **Continuity:** two planes, known different angles/depths, same seed → detected floor line within
   2px on both.
5. `python3 apps/danse/submission/check.py --package package/` → exit 0.
6. `python3 organs/artist/validate-artist.py --fleet` and `python3 scripts/check-gates.py` → pass.
7. `bash apps/danse/done.sh` → exit 0, and re-running mutates nothing.
8. `scripts/verify-scoped.sh` before every push.

## What I need from you (nothing blocks starting)

- **The room recordings** — point me at them, or let `sound/resolve.py` find them once it exists. If
  the 2017 afternoon has *video*, that audio is the strongest material in the piece.
- **The title** — I'll build against `THE THING WITHOUT A NAME`; it's one line in `program.json`.
- **A new IG handle** for the project (post-submission, not urgent).

I start at A and do not stop before E.
