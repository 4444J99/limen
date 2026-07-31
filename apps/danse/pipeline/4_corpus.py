#!/usr/bin/env python3
"""danse — stage 4: the corpus the engine actually loads.

Stages 0–3 measured that afternoon. This one packages it, and it exists because a
browser cannot open 844 MB of camera originals.

Three products:

  room.webp     The empty room, recovered. Only one frame of 162 has no dancer in
                it, but the camera never moved — so every wall pixel is the same
                wall across all 162 exposures, and the dancer is the only thing
                that changes. Take the per-pixel MEDIAN over the frames whose
                matte says "not her" and the room comes back clean. Median, not
                mean: a mean smears her residual across the wall, while a median
                is exactly immune as long as she covers any given pixel in fewer
                than half the frames. She covers 11–18%, so it is not close.

  plates/       Two web tiers per frame, plus its matte. `browse` (512px) is the
                whole corpus, cheap enough to ship eagerly so the engine can start
                without waiting for anything. `screen` (1024px) is fetched per
                frame as the grammar selects it.

  manifest.json Everything the engine needs to choose WITHOUT downloading a
                photograph first: each frame's matte coverage, the bounding box
                and centroid of the figure, which joints Vision found and where.
                Selection is a decision about anatomy, so anatomy has to be in
                the index rather than in the pixels.

Originals stay in .work/. Only these derived plates are versioned — they are the
deployable form, and the site cannot be built from photographs that may not be in
git.

    ./4_corpus.py                      # full build
    ./4_corpus.py --room-only          # just re-derive the empty room
    ./4_corpus.py --limit 8            # a fast smoke build
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
WORK = Path(__file__).resolve().parent / ".work"
OUT = HERE.parent / "corpus"

# Measured, not guessed — see the size table in the commit that added this file.
# WebP at these widths is ~25% under JPEG at matched visual quality.
TIERS = {
    "browse": {"width": 512, "quality": 80, "eager": True},
    "screen": {"width": 1024, "quality": 82, "eager": False},
}
MATTE_QUALITY = 70  # a matte is a soft-edged blob; it survives hard compression
ROOM_WIDTH = 2048
ROOM_QUALITY = 86

MASK_THRESHOLD = 127  # white = person, per Vision's segmentation output


def frames(work: Path) -> list[tuple[str, Path, Path, Path]]:
    """(id, raw, mask, pose) for every frame that has all three."""
    out = []
    for raw in sorted((work / "raw").iterdir()):
        if raw.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        mask = work / "vision" / "mask" / f"{raw.stem}.png"
        pose = work / "vision" / "pose" / f"{raw.stem}.json"
        if mask.exists() and pose.exists():
            out.append((raw.stem, raw, mask, pose))
    return out


# ── the empty room ─────────────────────────────────────────────────────────────


def room_plate(items, width: int, cache: Path, strip_rows: int = 64) -> Image.Image:
    """Per-pixel median over the not-her pixels of every frame.

    Done in horizontal strips: the whole stack at this width would be 162 ×
    2048 × 1536 × 3 floats, which this machine will not survive. A strip is two
    orders of magnitude smaller and the median is per-pixel, so strips are exact
    rather than approximate.
    """
    height = round(width * 3 / 4)
    n = len(items)
    cache.mkdir(parents=True, exist_ok=True)
    # Keyed on the frame COUNT as well as the width: a --limit smoke run and a
    # full run must never share a cache file, or the second silently medians the
    # wrong stack.
    plates_npy = cache / f"room-plates-{width}-{n}.npy"
    her_npy = cache / f"room-mattes-{width}-{n}.npy"

    # Decode each original EXACTLY once. The naive strip loop re-opens every
    # 3264×2448 JPEG for every strip — 162 frames × 16 strips is 2,592 full
    # decodes to produce one image. Downscale once into a disk-backed array
    # instead: memory stays bounded by the strip, not by the stack, and a
    # re-run (--room-only) skips decoding altogether.
    fresh = not (plates_npy.exists() and her_npy.exists())
    plates = np.lib.format.open_memmap(
        plates_npy, mode="w+" if fresh else "r", dtype=np.uint8, shape=(n, height, width, 3)
    )
    her_all = np.lib.format.open_memmap(her_npy, mode="w+" if fresh else "r", dtype=bool, shape=(n, height, width))
    if plates.shape != (n, height, width, 3) or her_all.shape != (n, height, width):
        raise SystemExit(f"cache shape mismatch at {plates_npy} — delete {cache} and re-run")
    if fresh:
        for i, (_, raw, mask, _) in enumerate(items, 0):
            with Image.open(raw) as im:
                plates[i] = np.asarray(im.convert("RGB").resize((width, height), Image.LANCZOS))
            with Image.open(mask) as mi:
                her_all[i] = np.asarray(mi.convert("L").resize((width, height), Image.LANCZOS)) > MASK_THRESHOLD
            print(f"\r  room · decode {i + 1}/{n}", end="", flush=True)
        plates.flush()
        her_all.flush()
        print()
    else:
        print(f"  room · reusing cached stack ({plates_npy.name})")

    out = np.zeros((height, width, 3), np.uint8)
    for y0 in range(0, height, strip_rows):
        y1 = min(y0 + strip_rows, height)
        strip = plates[:, y0:y1].astype(np.float32)
        strip[her_all[:, y0:y1]] = np.nan  # she is not part of the room

        # A pixel she never vacates would come back all-NaN. At 11–18% coverage
        # over 162 frames there is no such pixel, but fall back to the unmasked
        # median rather than emitting a hole if one ever appears.
        with np.errstate(all="ignore"):
            med = np.nanmedian(strip, axis=0)
        holes = ~np.isfinite(med)
        if holes.any():
            med[holes] = np.median(plates[:, y0:y1].astype(np.float32), axis=0)[holes]
        out[y0:y1] = np.clip(np.nan_to_num(med), 0, 255).astype(np.uint8)
        print(f"\r  room · median {y1 / height:6.1%}", end="", flush=True)

    print()
    return Image.fromarray(out)


# ── per-frame index ────────────────────────────────────────────────────────────


def figure_geometry(mask_path: Path) -> dict:
    """Where she is, as numbers, so the grammar can choose without the pixels.

    All in fractions of frame size with y measured DOWN from the top — the same
    convention the score's rects and Vision's joints use, so nothing downstream
    has to remember which way is up.
    """
    with Image.open(mask_path) as mi:
        m = np.asarray(mi.convert("L"))
    her = m > MASK_THRESHOLD
    coverage = float(her.mean())
    if coverage == 0:
        return {"coverage": 0.0, "bbox": None, "centroid": None}

    h, w = her.shape
    rows, cols = np.nonzero(her)
    ys, xs = rows / h, cols / w
    return {
        "coverage": round(coverage, 5),
        "bbox": [
            round(float(xs.min()), 5),
            round(float(ys.min()), 5),
            round(float(xs.max()), 5),
            round(float(ys.max()), 5),
        ],
        "centroid": [round(float(xs.mean()), 5), round(float(ys.mean()), 5)],
    }


def joints_of(pose_path: Path, min_conf: float = 0.1) -> dict:
    """Confident joints only, flattened to {name: [x, y, conf]}."""
    data = json.loads(pose_path.read_text())
    raw = ((data.get("pose") or {}).get("joints")) or {}
    return {
        k: [round(v[0], 5), round(v[1], 5), round(v[2], 3)] for k, v in raw.items() if len(v) == 3 and v[2] >= min_conf
    }


# ── encoding ───────────────────────────────────────────────────────────────────


def encode(src: Path, dest: Path, width: int, quality: int, grey: bool = False) -> int:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as im:
        im = im.convert("L" if grey else "RGB")
        height = round(width * 3 / 4)
        im.resize((width, height), Image.LANCZOS).save(dest, "WEBP", quality=quality, method=6)
    return dest.stat().st_size


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--work", type=Path, default=WORK)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--limit", type=int, help="build only the first N frames (smoke test)")
    ap.add_argument("--room-only", action="store_true")
    ap.add_argument("--skip-room", action="store_true")
    args = ap.parse_args()

    if not (args.work / "raw").is_dir():
        print(f"no corpus at {args.work}/raw — run 0_export.sh first", file=sys.stderr)
        return 1

    items = frames(args.work)
    if args.limit:
        items = items[: args.limit]
    if not items:
        print("no frames with raw+mask+pose", file=sys.stderr)
        return 1
    print(f"{len(items)} frames with raw + matte + pose")

    args.out.mkdir(parents=True, exist_ok=True)
    room_rel = "room.webp"

    if not args.skip_room:
        img = room_plate(items, ROOM_WIDTH, args.work / "cache")
        img.save(args.out / room_rel, "WEBP", quality=ROOM_QUALITY, method=6)
        print(
            f"  room.webp · {ROOM_WIDTH}×{round(ROOM_WIDTH * 3 / 4)} · "
            f"{(args.out / room_rel).stat().st_size / 1024:.0f}K"
        )
    if args.room_only:
        return 0

    # Which frames the 2017 solve actually drew on — the engine weights toward
    # them, so the index has to say.
    score_path = args.out / "score-2017.json"
    in_score: dict[str, float] = {}
    if score_path.exists():
        score = json.loads(score_path.read_text())
        for tile in score["tiles"]:
            for layer in tile["layers"]:
                stem = Path(layer["src"]).stem
                in_score[stem] = round(in_score.get(stem, 0.0) + tile.get("area", 0.0), 5)

    entries, totals = [], {name: 0 for name in TIERS}
    for i, (fid, raw, mask, pose) in enumerate(items, 1):
        geom = figure_geometry(mask)
        for tier, spec in TIERS.items():
            totals[tier] += encode(raw, args.out / "plates" / tier / f"{fid}.webp", spec["width"], spec["quality"])
            totals[tier] += encode(
                mask, args.out / "mattes" / tier / f"{fid}.webp", spec["width"], MATTE_QUALITY, grey=True
            )
        entries.append(
            {
                "id": fid,
                "source": raw.name,
                "figure": geom,
                "joints": joints_of(pose),
                "score_area": in_score.get(fid, 0.0),
            }
        )
        print(f"\r  plates · {i}/{len(items)}", end="", flush=True)
    print()

    manifest = {
        "schema": "danse.corpus.v1",
        "shot": "2017-06-20",
        "convention": "fractions of frame size, y measured DOWN from the top",
        "room": {
            "file": room_rel,
            "width": ROOM_WIDTH,
            "height": round(ROOM_WIDTH * 3 / 4),
            "derived": "masked per-pixel median over all frames",
        },
        "tiers": {
            name: {
                "width": spec["width"],
                "height": round(spec["width"] * 3 / 4),
                "eager": spec["eager"],
                "plates": f"plates/{name}/<id>.webp",
                "mattes": f"mattes/{name}/<id>.webp",
                "bytes": totals[name],
            }
            for name, spec in TIERS.items()
        },
        "score": "score-2017.json" if score_path.exists() else None,
        "frames": entries,
    }
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")

    print(f"\nmanifest.json · {len(entries)} frames")
    for name in TIERS:
        eager = "eager" if TIERS[name]["eager"] else "lazy"
        print(f"  {name:<7} {TIERS[name]['width']:>5}px  {totals[name] / 1e6:>6.1f} MB  {eager}")
    with_joints = sum(1 for e in entries if e["joints"])
    print(f"  {with_joints}/{len(entries)} frames carry at least one confident joint")
    return 0


if __name__ == "__main__":
    sys.exit(main())
