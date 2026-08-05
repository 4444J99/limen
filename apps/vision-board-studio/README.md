# Vision Board Studio

Recreate a vision board from a single photo — **restore it faithfully, then fork it forward** — and export it three ways.

Born from a real loss: a 2017 vision board (Boca Raton → Texas → destroyed), surviving only as one blurry phone photo. This app is the engine behind getting it back — and it works for anyone's lost or existing board.

## What it does

- **Ingest** — upload a photo of any board and draw a box over each picture. Each box is sliced out, upscaled, and becomes an editable tile. (The seed board, `boards/tony-2017.json`, was reconstructed this way from the only surviving photo.)
- **Faithful layer** — every tile opens on its **salvaged fragment** (the actual image recovered from the photo). Swap in a high-res match via URL or upload; a one-click image search is pre-filled per tile.
- **2026 Fork** — a parallel layer on the *same* structure: re-imagine each tile for who you are now. Toggle **Faithful / 2026 / Split** to see either or both.
- **Three outputs:**
  - **Poster** — print/save the whole composition as one framed piece (PDF via browser print).
  - **Reprint kit** — a layout map + every tile at cut size, to print, cut, and pin to a real corkboard.
  - **Canvas** — the editable studio itself.
- **Save / Load** — boards are portable JSON; work auto-persists to `localStorage`.

## Run

Pure static — no build step, no dependencies.

```bash
cd apps/vision-board-studio
python3 -m http.server 8080   # then open http://localhost:8080
```

Deploys as-is to Cloudflare Pages / Netlify / any static host ($0).

## Data model

A board is `{ name, banner, aspect, tiles[] }`. Each tile carries a `faithful` layer, a `fork` layer, a `salvage` fragment (always revertible), and a percentage-based `pos` so layouts are resolution-independent.

## Roadmap

- Auto tile-detection on ingest (CV segmentation) instead of manual box-drawing.
- Per-tile image search/sourcing inline (currently opens an external image search).
- Shareable board links; theme-clustered "why this board" summary.
