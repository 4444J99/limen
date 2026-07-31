#!/usr/bin/env python3
"""Every deliverable the call asks for, from one command. Idempotent.

The river is a pure `f(seed, t)` and the captures in `program.json` are presets
for RECORDING the river starting at a given `--start` offset, so most of this is
not rendering — it is SELECTING from the recorded river. That is the whole
leverage of the spine, and it shows up here as arithmetic:

    passage           RENDERED. 4K ProRes 422 HQ (one whole passage at 4K),
                      the primary submission recording.
    midnight-moment   sliced from the passage recording. ProRes is all-intra,
                      so every frame is a keyframe and a cut is frame-exact with
                      no re-encode at all — Times Square gets literally the film's
                      own frames.
    screener          the passage recording, scaled to 1080p.
    trailer           sliced, then scaled to 1080p.
    reel              RENDERED. The one capture preset that cannot be derived,
                      because 1080x1920 is a vertical aspect and `cover`
                      projection therefore chooses a different field of view.
    stills            six one-frame renders at distinct seeds, named by seed.

SOUND IS SLICED, NEVER RE-SCORED. `score.py --capture trailer` is a legitimate
standalone composition, but it starts its bed and its voice phrasing at the
capture's own start time, so the same absolute moment would sound different in the
passage recording and in the Times Square cut. Slicing one passage score means a
moment sounds the way it sounds, in every crop of the film that contains it.

    apps/danse/render/deliver.py                 # everything
    apps/danse/render/deliver.py --only stills
    apps/danse/render/deliver.py --start 120.0   # start recording 120s into the river
    apps/danse/render/deliver.py --force reel    # re-make one that already exists
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DANSE = HERE.parent
PROGRAM = HERE / "program.json"
OUT = HERE / "out"
PACKAGE = OUT / "package"
SCORE = DANSE / "sound" / "score.py"
RENDER = HERE / "render.py"
REFERENCE = DANSE / "pipeline" / ".work" / "reference"

# The origin document. 1024x768 is not a mistake and not a downsample — it is
# the resolution the 2017 piece exists at. The film restores that composite to
# 4K from the original photographs; this is what it is being restored FROM.
ORIGIN = REFERENCE / "T-2017-full.png"

# Captures that are sub-spans or scaled versions of the primary 4K `passage` capture,
# so they can be cut/scaled from it. `copy` means stream-copy (no re-encode at all).
DERIVED = {
    "midnight-moment": {"suffix": ".mov", "mode": "copy", "audio": "pcm_s24le"},
    "trailer": {"suffix": ".mp4", "mode": "scale", "audio": "aac"},
    "screener": {"suffix": ".mp4", "mode": "scale", "audio": "aac"},
}

# Six moments, chosen to span the arc rather than to flatter one cut: the
# composite intact, the composite coming apart, the engine at full stride twice,
# a body that never existed, and a reseed.
STILL_TIMES = (55.0, 95.0, 150.0, 200.0, 250.0, 330.0)


def sh(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


def ffmpeg(args: list) -> None:
    done = sh(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *args])
    if done.returncode != 0:
        raise SystemExit(f"ffmpeg failed:\n{' '.join(str(a) for a in args)}\n{done.stderr.strip()}")


def probe(path: Path) -> dict | None:
    if not path.is_file():
        return None
    done = sh(
        # fmt: off
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size:stream=codec_type,codec_name,width,height,r_frame_rate,channels",
            "-of",
            "json",
            path,
        ]
        # fmt: on
    )
    if done.returncode != 0:
        return None
    raw = json.loads(done.stdout)
    out = {"seconds": float(raw["format"]["duration"]), "bytes": int(raw["format"]["size"])}
    for s in raw.get("streams", []):
        if s["codec_type"] == "video" and "width" not in out:
            num, den = s["r_frame_rate"].split("/")
            out |= {"width": s["width"], "height": s["height"], "fps": round(int(num) / max(int(den), 1), 3)}
            out["vcodec"] = s["codec_name"]
        elif s["codec_type"] == "audio" and "acodec" not in out:
            out |= {"acodec": s["codec_name"], "channels": s.get("channels")}
    return out


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def captures(program: dict) -> dict:
    return {k: v for k, v in program.get("captures", {}).items() if isinstance(v, dict)}


def hexseed(seed: int) -> str:
    return f"0x{seed:X}"


def query_capture_span(capture_name: str, seed: int | None = None, start: float = 0.0) -> dict:
    """Query control.mjs for exact capture span and passage details."""
    cmd = ["node", str(DANSE / "sound" / "control.mjs"), "--window", capture_name, "--from", str(start)]
    if seed is not None:
        cmd += ["--seed", str(seed)]
    done = sh(cmd)
    if done.returncode != 0:
        raise SystemExit(f"failed to query capture span for {capture_name}:\n{done.stderr.strip()}")
    data = json.loads(done.stdout)
    return {
        "t0": data["t0"],
        "t1": data["t1"],
        "duration": data["duration"],
        "seed": data["seed"],
        "capture": data["capture"],
    }


# ── the expensive half ─────────────────────────────────────────────────────────


def passage_picture(program: dict, tier: str, force: bool, start: float = 0.0) -> Path:
    """Render the primary 4K passage recording, or keep it. `render.py --resume` decides per segment."""
    stem = OUT / "passage-default"
    dest = stem.with_suffix(".mov")
    span = query_capture_span("passage", start=start)
    cap = captures(program)["passage"]
    fps = cap.get("fps", 30)
    want = int(round(span["duration"] * fps))
    if not force:
        got = probe(dest)
        if got and abs(got["seconds"] * fps - want) < 2:
            print(f"  passage picture · kept · {got['width']}×{got['height']} @{got['fps']} · {got['seconds']:.1f}s")
            return dest
    print("  passage picture · rendering (this is the long one)")
    done = subprocess.run(
        # fmt: off
        [
            sys.executable,
            str(RENDER),
            "--capture",
            "passage",
            "--start",
            str(start),
            "--tier",
            tier,
            "--codec",
            "prores",
            "--resume",
            "--quiet",
            "--out",
            str(OUT),
        ],
        # fmt: on
        check=False,
    )
    if done.returncode != 0 or not dest.is_file():
        raise SystemExit("the passage picture would not render")
    return dest


def passage_sound(force: bool, start: float = 0.0) -> Path:
    """One score for the passage recording. Every derived capture is cut from it."""
    dest = OUT / "passage-score.wav"
    if dest.is_file() and not force:
        print(f"  passage score · kept · {probe(dest)['seconds']:.1f}s")
        return dest
    print("  passage score · rendering")
    done = subprocess.run(
        [sys.executable, str(SCORE), "--window", "passage", "--from", str(start), "--out", str(dest)],
        check=False,
    )
    if done.returncode != 0 or not dest.is_file():
        raise SystemExit("the score would not render")
    return dest


def mux(video: Path, audio: Path, dest: Path, acodec: str, vcopy: bool = True, vfilter: str | None = None) -> None:
    args = ["-i", video, "-i", audio, "-map", "0:v:0", "-map", "1:a:0"]
    if vcopy:
        args += ["-c:v", "copy"]
    else:
        args += ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if vfilter:
        args += ["-vf", vfilter]
    args += ["-c:a", acodec] + (["-b:a", "320k"] if acodec == "aac" else []) + ["-shortest", dest]
    ffmpeg(args)


def cut_audio(source: Path, t0: float, seconds: float, dest: Path, fade: float = 0.3) -> None:
    """A capture's sound, from the passage score, with edges that do not click."""
    filters = [] if fade <= 0 else [f"afade=t=in:st=0:d={fade}", f"afade=t=out:st={max(0.0, seconds - fade)}:d={fade}"]
    args = ["-ss", t0, "-t", seconds, "-i", source]
    if filters:
        args += ["-af", ",".join(filters)]
    ffmpeg([*args, dest])


# ── deliverables ───────────────────────────────────────────────────────────────


def deliver_passage(picture: Path, sound: Path, force: bool) -> Path:
    dest = PACKAGE / "master.mov"
    if dest.is_file() and not force:
        return dest
    print("  master.mov (4K passage) · muxing")
    mux(picture, sound, dest, "pcm_s24le")
    return dest


def deliver_derived(name: str, spec: dict, program: dict, picture: Path, sound: Path, force: bool, start: float = 0.0) -> Path:
    cap = captures(program)[name]
    span = query_capture_span(name, start=start)
    passage_span = query_capture_span("passage", start=start)

    rel_t0 = max(0.0, span["t0"] - passage_span["t0"])
    seconds = span["duration"]
    fps = cap.get("fps", 30)
    w_out, h_out = cap.get("w", 1920), cap.get("h", 1080)

    dest = PACKAGE / f"{name}{spec['suffix']}"
    if dest.is_file() and not force:
        return dest
    print(f"  {dest.name} · {'slicing' if spec['mode'] == 'copy' else 'slicing + scaling'} from the passage recording")

    tmp_v = OUT / f".{name}-v{spec['suffix']}"
    tmp_a = OUT / f".{name}-a.wav"
    if spec["mode"] == "copy":
        ffmpeg(["-ss", rel_t0, "-t", seconds, "-i", picture, "-c", "copy", tmp_v])
    else:
        ffmpeg(["-ss", rel_t0, "-t", seconds, "-i", picture, "-c", "copy", OUT / f".{name}-raw.mov"])
        tmp_v = OUT / f".{name}-raw.mov"

    cut_audio(sound, rel_t0, seconds, tmp_a, fade=0.0 if name == "screener" else 0.3)
    scale = None if spec["mode"] == "copy" else f"scale={w_out}:{h_out}:flags=lanczos"
    mux(tmp_v, tmp_a, dest, spec["audio"], vcopy=(spec["mode"] == "copy"), vfilter=scale)
    for junk in (OUT / f".{name}-v{spec['suffix']}", OUT / f".{name}-a.wav", OUT / f".{name}-raw.mov"):
        junk.unlink(missing_ok=True)

    got = probe(dest)
    want_frames = int(round(seconds * fps))
    if got:
        have = int(round(got["seconds"] * got.get("fps", fps)))
        if abs(have - want_frames) > 1:
            raise SystemExit(f"{dest.name} is {have} frames, the capture declares {want_frames} — the slice is wrong")
        print(f"      {got['seconds']:.3f}s · {have} frames (declared {want_frames})")
    return dest


def deliver_reel(program: dict, sound: Path, tier: str, force: bool, start: float = 0.0) -> Path:
    """The one capture preset that must be rendered — vertical aspect is a different field of view."""
    dest = PACKAGE / "reel.mp4"
    if dest.is_file() and not force:
        return dest
    span = query_capture_span("reel", start=start)
    passage_span = query_capture_span("passage", start=start)
    rel_t0 = max(0.0, span["t0"] - passage_span["t0"])
    seconds = span["duration"]

    print("  reel.mp4 · rendering (vertical is a different field of view, not a crop)")
    stem = OUT / "reel-default"
    for junk in OUT.glob("reel-default*"):
        junk.unlink(missing_ok=True)
    done = subprocess.run(
        # fmt: off
        [
            sys.executable,
            str(RENDER),
            "--capture",
            "reel",
            "--start",
            str(start),
            "--tier",
            tier,
            "--codec",
            "h264",
            "--quiet",
            "--out",
            str(OUT),
        ],
        # fmt: on
        check=False,
    )
    picture = stem.with_suffix(".mp4")
    if done.returncode != 0 or not picture.is_file():
        raise SystemExit("the reel would not render")
    tmp_a = OUT / ".reel-a.wav"
    cut_audio(sound, rel_t0, seconds, tmp_a)
    mux(picture, tmp_a, dest, "aac")
    tmp_a.unlink(missing_ok=True)
    return dest


def deliver_stills(program: dict, tier: str, force: bool, start: float = 0.0) -> list[Path]:
    """Six frames, six seeds. The filename IS the provenance — `seed-0x….jpg`
    says this is one of the films, not the film."""
    sys.path.insert(0, str(DANSE / "sound"))
    from rng import hash32

    stills = PACKAGE / "stills"
    stills.mkdir(parents=True, exist_ok=True)
    cap = captures(program)["passage"]
    fps = cap.get("fps", 30)
    made = []
    for i, t in enumerate(STILL_TIMES):
        seed = hash32(program["seed"], 0x57111, i) & 0xFFFFFF
        dest = stills / f"seed-{hexseed(seed)}.jpg"
        if dest.is_file() and not force:
            made.append(dest)
            continue
        frame = int(round(t * fps))
        print(f"  {dest.name} · t={t:.0f}s")
        for junk in OUT.glob(f"passage-{seed}*"):
            junk.unlink(missing_ok=True)
        done = subprocess.run(
            # fmt: off
            [
                sys.executable,
                str(RENDER),
                "--capture",
                "passage",
                "--start",
                str(start),
                "--tier",
                tier,
                "--codec",
                "prores",
                "--seed",
                str(seed),
                "--segment",
                str(frame),
                "--segment-frames",
                "1",
                "--quiet",
                "--out",
                str(OUT),
            ],
            # fmt: on
            check=False,
        )
        one = OUT / f"passage-{seed}-seg-{frame:03d}.mov"
        if done.returncode != 0 or not one.is_file():
            raise SystemExit(f"still at t={t} would not render")
        ffmpeg(["-i", one, "-frames:v", "1", "-q:v", "2", dest])
        one.unlink(missing_ok=True)
        made.append(dest)
    return made


def deliver_text() -> list[Path]:
    """The written half, from its git-tracked source.

    These live in `submission/text/` and are COPIED here, never authored here:
    the package is a build artifact and gets wiped, and a synopsis is not
    something that should be recoverable only from a directory nobody backs up.
    """
    source = DANSE / "submission" / "text"
    if not source.is_dir():
        print(f"  text · MISSING SOURCE at {source}")
        return []
    dest = PACKAGE / "text"
    dest.mkdir(parents=True, exist_ok=True)
    made = []
    for path in sorted(source.glob("*.txt")):
        shutil.copy2(path, dest / path.name)
        made.append(dest / path.name)
    print(f"  text/ · {len(made)} files · {sum(len(p.read_text().split()) for p in made)} words")
    return made


def deliver_origin(force: bool) -> Path | None:
    dest = PACKAGE / "origin-2017.jpg"
    if dest.is_file() and not force:
        return dest
    if not ORIGIN.is_file():
        print(f"  origin-2017.jpg · MISSING SOURCE at {ORIGIN}")
        return None
    print("  origin-2017.jpg · the 2017 composite, at the resolution it exists at")
    ffmpeg(["-i", ORIGIN, "-q:v", "2", dest])
    return dest


ATTESTATIONS = """# Human assertions. Nothing here may be filled in by a machine — each line is a
# claim about an act somebody performed, and `check.py --package` reads them as
# such. Set to true only once the act is done.
#
#   final-cut-only            this is a final cut, not a work in progress
#   link-password-protected   the Vimeo link has a password set
#   link-downloadable         the Vimeo link has download ENABLED (it ships off)
#   submitted-via-submittable filed through the Submittable portal
final-cut-only: null
link-password-protected: null
link-downloadable: null
submitted-via-submittable: null
"""


def main() -> int:
    global PACKAGE
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tier", default="film", help="corpus tier for rendered items")
    ap.add_argument("--start", type=float, default=0.0, help="where in the river to begin recording (in seconds)")
    ap.add_argument("--only", action="append", help="master | derived | reel | stills | origin | text (repeatable)")
    ap.add_argument("--force", action="append", default=[], help="re-make an item that already exists")
    ap.add_argument("--package", type=Path, default=PACKAGE)
    args = ap.parse_args()

    program = json.loads(PROGRAM.read_text())
    only = set(args.only or ["master", "derived", "reel", "stills", "origin", "text"])
    force = set(args.force)
    PACKAGE = args.package
    PACKAGE.mkdir(parents=True, exist_ok=True)

    span = query_capture_span("passage", start=args.start)
    print(
        f"{program['title']} · seed {hexseed(program['seed'])} · passage seed {hexseed(span['seed'])} · "
        f"{span['duration']:.1f}s (start at {args.start:.1f}s)\n"
    )

    picture = passage_picture(program, args.tier, "master" in force, start=args.start)
    sound = passage_sound("master" in force, start=args.start)
    made: list[Path] = []

    if "master" in only:
        made.append(deliver_passage(picture, sound, "master" in force))
    if "derived" in only:
        for name, spec in DERIVED.items():
            made.append(deliver_derived(name, spec, program, picture, sound, name in force, start=args.start))
    if "reel" in only:
        made.append(deliver_reel(program, sound, args.tier, "reel" in force, start=args.start))
    if "stills" in only:
        made += deliver_stills(program, args.tier, "stills" in force, start=args.start)
    if "text" in only:
        deliver_text()
    if "origin" in only:
        got = deliver_origin("origin" in force)
        if got:
            made.append(got)

    attest = PACKAGE / "attest.yaml"
    if not attest.exists():
        attest.write_text(ATTESTATIONS)
        print("  attest.yaml · scaffold written — every line is a human's to set")

    print()
    manifest = {
        "title": program["title"],
        "seed": hexseed(program["seed"]),
        "passage_seed": hexseed(span["seed"]),
        "start": args.start,
        "items": [],
    }
    for path in made:
        info = probe(path) or {}
        size = path.stat().st_size
        manifest["items"].append(
            {"name": str(path.relative_to(PACKAGE)), "bytes": size, "sha256": digest(path), **info}
        )
        shape = f"{info.get('width', '?')}×{info.get('height', '?')}"
        rate = f"@{info['fps']}" if "fps" in info else ""
        secs = f"{info['seconds']:.1f}s " if "seconds" in info else ""
        print(f"  {str(path.relative_to(PACKAGE)):<28} {size / 1e6:>8.1f} MB  {secs}{shape} {rate}")
    (PACKAGE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    total = sum(i["bytes"] for i in manifest["items"])
    print(f"\n  {len(made)} items · {total / 1e9:.2f} GB · {PACKAGE}")
    if shutil.which("python3"):
        print("\nnext: apps/danse/submission/check.py --package " + str(PACKAGE))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
