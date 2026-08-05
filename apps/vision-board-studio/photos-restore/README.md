# Photos Restore — fill a board with your real originals

The Vision Board Studio app opens on **salvaged fragments** cropped from the
surviving board photo. This local companion finds the *actual high-res originals*
in your macOS **Photos.app** library and swaps them in — turning a recognizable
reconstruction into a true restoration.

It runs entirely on your machine; your photos never leave it.

## Why it's built this way

- The browser app is sandboxed and can't read Photos.app, so restoration is a
  **local Python step**, not an app feature.
- Originals are usually in **iCloud** ("optimize storage"), so we match against
  the **local thumbnails/derivatives** Photos keeps for every asset, then
  download only the chosen ~20 originals at full res.
- **Image→image matching fails** (a photo-of-a-photo is a corrupted query).
  **Text→image CLIP works**: we search the library by *description* ("a red
  Japanese pagoda with autumn maples"), which survives the degradation. A light
  image-similarity term breaks ties toward the exact shot.

## Pipeline

```bash
python3.11 -m venv clipvenv
./clipvenv/bin/pip install torch open_clip_torch pillow numpy osxphotos

# 1. Embed every local thumbnail once (cached to clip_cache.npz, ~4 min):
./clipvenv/bin/python 1_embed_library.py

# 2. Build the confirmation gallery (per-tile candidates → confirm/):
./clipvenv/bin/python 2_build_gallery.py

# 3. Confirm — the only human step:
cd confirm && python3 -m http.server 8093   # open confirm.html, pick each tile,
                                             # click "Export picks" → picks.json

# 4. Download chosen originals from iCloud + rebuild the board:
./clipvenv/bin/python 3_download_fill.py confirm/picks.json ..
#   → writes boards/tony-2017.restored.json + assets/originals/*
```

Requires Full Disk Access (to read the Photos library) and, for step 4, Automation
permission (osxphotos drives Photos.app to pull iCloud originals).

## Reuse

This is the general engine behind "restore any board from a photo": point step 1
at any Photos library, drive steps 2–4 with any board's tiles + salvage crops.
Private/derived artifacts (embeddings cache, candidate thumbnails, picks) are
`.gitignore`d — only the code is versioned.
