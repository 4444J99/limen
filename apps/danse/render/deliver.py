#!/usr/bin/env python3
"""Every deliverable the call asks for, from one command. Idempotent.

The film is a pure `f(seed, t)` and the windows in `program.json` are crops of
one timeline, so most of this is not rendering — it is SELECTING. That is the
whole leverage of the spine, and it shows up here as arithmetic:

    master            RENDERED. 4K ProRes 422 HQ, the only expensive thing.
    midnight-moment   sliced from the master. ProRes is all-intra, so every
                      frame is a keyframe and a cut is frame-exact with no
                      re-encode at all — Times Square gets literally the film's
                      own frames, not a second render of them.
    screener          the master, downscaled. Better than a native 1080p render,
                      not worse: 3840 -> 1920 is supersampled.
    trailer           sliced, then downscaled. Same two reasons.
    reel              RENDERED. The one window that cannot be derived, because
                      1080x1920 is a different aspect and `cover` projection
                      therefore chooses a different field of view. A cropped
                      16:9 would be a different composition wearing the same
                      seed, which is exactly the lie the `fit` parameter exists
                      to prevent.
    stills            one-frame renders at six distinct seeds.

SOUND IS SLICED, NEVER RE-SCORED. `score.py --window trailer` is a legitimate
standalone composition, but it starts its bed and its voice phrasing at the
window's own t=0, so the same absolute moment would sound different in the
master and in the Times Square cut. Slicing one master score means a moment
sounds the way it sounds, in every crop of the film that contains it.

    apps/danse/render/deliver.py                 # everything
    apps/danse/render/deliver.py --only stills
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

# Windows that are sub-spans of the master at the same rate and aspect, so they
# can be cut from it. `copy` means stream-copy (no re-encode at all).
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


def windows(program: dict) -> dict:
    return {k: v for k, v in program["windows"].items() if isinstance(v, dict)}


def hexseed(seed: int) -> str:
    return f"0x{seed:X}"


# ── the expensive half ─────────────────────────────────────────────────────────


def master_picture(program: dict, tier: str, force: bool) -> Path:
    """Render the master, or keep it. `render.py --resume` decides per segment."""
    stem = OUT / "master-default"
    dest = stem.with_suffix(".mov")
    w = windows(program)["master"]
    want = int(round((w["t1"] - w["t0"]) * w["fps"]))
    if not force:
        got = probe(dest)
        if got and abs(got["seconds"] * w["fps"] - want) < 2:
            print(f"  master picture · kept · {got['width']}×{got['height']} @{got['fps']} · {got['seconds']:.1f}s")
            return dest
    print("  master picture · rendering (this is the long one)")
    done = subprocess.run(
        # fmt: off
        [
            sys.executable,
            str(RENDER),
            "--window",
            "master",
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
        raise SystemExit("the master would not render")
    return dest


def master_sound(force: bool) -> Path:
    """One score for the whole timeline. Every other window is cut from it."""
    dest = OUT / "master-score.wav"
    if dest.is_file() and not force:
        print(f"  master score · kept · {probe(dest)['seconds']:.1f}s")
        return dest
    print("  master score · rendering")
    done = subprocess.run([sys.executable, str(SCORE), "--window", "master", "--out", str(dest)], check=False)
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
    """A window's sound, from the master score, with edges that do not click."""
    filters = [] if fade <= 0 else [f"afade=t=in:st=0:d={fade}", f"afade=t=out:st={max(0.0, seconds - fade)}:d={fade}"]
    args = ["-ss", t0, "-t", seconds, "-i", source]
    if filters:
        args += ["-af", ",".join(filters)]
    ffmpeg([*args, dest])


# ── deliverables ───────────────────────────────────────────────────────────────


def deliver_master(picture: Path, sound: Path, force: bool) -> Path:
    dest = PACKAGE / "master.mov"
    if dest.is_file() and not force:
        return dest
    print("  master.mov · muxing")
    mux(picture, sound, dest, "pcm_s24le")
    return dest


def deliver_derived(name: str, spec: dict, program: dict, picture: Path, sound: Path, force: bool) -> Path:
    w = windows(program)[name]
    dest = PACKAGE / f"{name}{spec['suffix']}"
    if dest.is_file() and not force:
        return dest
    seconds = w["t1"] - w["t0"]
    print(f"  {dest.name} · {'slicing' if spec['mode'] == 'copy' else 'slicing + scaling'} from the master")

    tmp_v = OUT / f".{name}-v{spec['suffix']}"
    tmp_a = OUT / f".{name}-a.wav"
    if spec["mode"] == "copy":
        # ProRes is all-intra: input-seek is frame-exact and copies the film's
        # own frames rather than making new ones.
        ffmpeg(["-ss", w["t0"], "-t", seconds, "-i", picture, "-c", "copy", tmp_v])
    else:
        ffmpeg(["-ss", w["t0"], "-t", seconds, "-i", picture, "-c", "copy", OUT / f".{name}-raw.mov"])
        tmp_v = OUT / f".{name}-raw.mov"

    cut_audio(sound, w["t0"], seconds, tmp_a, fade=0.0 if name == "screener" else 0.3)
    scale = None if spec["mode"] == "copy" else f"scale={w['w']}:{w['h']}:flags=lanczos"
    mux(tmp_v, tmp_a, dest, spec["audio"], vcopy=(spec["mode"] == "copy"), vfilter=scale)
    for junk in (OUT / f".{name}-v{spec['suffix']}", OUT / f".{name}-a.wav", OUT / f".{name}-raw.mov"):
        junk.unlink(missing_ok=True)

    # A derived window is only legitimate if it is the exact span it claims.
    # Times Square wants EXACTLY 170 seconds, and a slice that lands a frame
    # either side of that is a rejected submission, not a rounding difference.
    got = probe(dest)
    want_frames = int(round(seconds * w["fps"]))
    if got:
        have = int(round(got["seconds"] * got.get("fps", w["fps"])))
        if abs(have - want_frames) > 1:
            raise SystemExit(f"{dest.name} is {have} frames, the window declares {want_frames} — the slice is wrong")
        print(f"      {got['seconds']:.3f}s · {have} frames (declared {want_frames})")
    return dest


def deliver_reel(program: dict, sound: Path, tier: str, force: bool) -> Path:
    """The one window that must be rendered — a different aspect sees differently."""
    dest = PACKAGE / "reel.mp4"
    if dest.is_file() and not force:
        return dest
    w = windows(program)["reel"]
    print("  reel.mp4 · rendering (vertical is a different field of view, not a crop)")
    stem = OUT / "reel-default"
    for junk in OUT.glob("reel-default*"):
        junk.unlink(missing_ok=True)
    done = subprocess.run(
        # fmt: off
        [
            sys.executable,
            str(RENDER),
            "--window",
            "reel",
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
    cut_audio(sound, w["t0"], w["t1"] - w["t0"], tmp_a)
    mux(picture, tmp_a, dest, "aac")
    tmp_a.unlink(missing_ok=True)
    return dest


def deliver_stills(program: dict, tier: str, force: bool) -> list[Path]:
    """Six frames, six seeds. The filename IS the provenance — `seed-0x….jpg`
    says this is one of the films, not the film."""
    sys.path.insert(0, str(DANSE / "sound"))
    from rng import hash32

    stills = PACKAGE / "stills"
    stills.mkdir(parents=True, exist_ok=True)
    w = windows(program)["master"]
    made = []
    for i, t in enumerate(STILL_TIMES):
        seed = hash32(program["seed"], 0x57111, i) & 0xFFFFFF
        dest = stills / f"seed-{hexseed(seed)}.jpg"
        if dest.is_file() and not force:
            made.append(dest)
            continue
        frame = int(round((t - w["t0"]) * w["fps"]))
        print(f"  {dest.name} · t={t:.0f}s")
        for junk in OUT.glob(f"master-{seed}*"):
            junk.unlink(missing_ok=True)
        done = subprocess.run(
            # fmt: off
            [
                sys.executable,
                str(RENDER),
                "--window",
                "master",
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
        one = OUT / f"master-{seed}-seg-{frame:03d}.mov"
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
    ap.add_argument("--only", action="append", help="master | derived | reel | stills | origin | text (repeatable)")
    ap.add_argument("--force", action="append", default=[], help="re-make an item that already exists")
    ap.add_argument("--package", type=Path, default=PACKAGE)
    args = ap.parse_args()

    program = json.loads(PROGRAM.read_text())
    only = set(args.only or ["master", "derived", "reel", "stills", "origin", "text"])
    force = set(args.force)
    PACKAGE = args.package
    PACKAGE.mkdir(parents=True, exist_ok=True)

    print(f"{program['title']} · seed {hexseed(program['seed'])} · {program['duration']}s\n")

    picture = master_picture(program, args.tier, "master" in force)
    sound = master_sound("master" in force)
    made: list[Path] = []

    if "master" in only:
        made.append(deliver_master(picture, sound, "master" in force))
    if "derived" in only:
        for name, spec in DERIVED.items():
            made.append(deliver_derived(name, spec, program, picture, sound, name in force))
    if "reel" in only:
        made.append(deliver_reel(program, sound, args.tier, "reel" in force))
    if "stills" in only:
        made += deliver_stills(program, args.tier, "stills" in force)
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
    manifest = {"title": program["title"], "seed": hexseed(program["seed"]), "items": []}
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
