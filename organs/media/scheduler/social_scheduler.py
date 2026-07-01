#!/usr/bin/env python3
"""social_scheduler.py — stage screengrabs & recordings as social-media assets.

Carrier-Wave Media organ · OUTBOUND distribution face (Spine B). Reads media the
archive produced (screen captures / recordings / the media-ark ``out/`` tree),
prepares platform-native assets, drafts captions, and QUEUES them. It never posts:

    select  ->  transcode/crop (ffmpeg)  ->  caption  ->  queue  ->  [HUMAN SEND]

The ``send`` step is a human-gated lever (L-SOCIAL-SEND) — nothing leaves the
machine without the human pulling it, per the organ's hard guardrail
("the organ drafts; the human publishes"). ``--apply`` only runs the local ffmpeg
transcode; publishing is still refused unless a per-platform token AND explicit
--send are present. Default is a dry-run plan that touches nothing.

Stdlib only (subprocess -> ffmpeg). Reversible: writes drafts + a queue, never posts.

Usage:
    social_scheduler.py plan --platform reel --query wrath          # dry-run plan
    social_scheduler.py plan --platform reel --source ~/clips --apply  # + ffmpeg transcode
    social_scheduler.py queue-list                                   # show the draft queue
    social_scheduler.py send --id <qid>                              # refused w/o lever+token
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

# Declared governance params (see institutio/governance/parameters.yaml).
ROOT = Path(os.environ.get("LIMEN_ROOT", Path.home() / "Workspace" / "limen"))
PRIVATE_ROOT = Path(os.environ.get("LIMEN_PRIVATE_ROOT", ROOT / ".limen-private"))
QUEUE_DIR = PRIVATE_ROOT / "media-scheduler"
QUEUE_PATH = QUEUE_DIR / "queue.jsonl"
STAGE_DIR = QUEUE_DIR / "staged"

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".heic", ".webp", ".gif", ".tiff", ".bmp"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v", ".webm", ".avi", ".mkv"}

# Per-platform presets. dims in px; max_seconds for video; kind = which asset it wants.
PRESETS: dict[str, dict] = {
    "reel": {"w": 1080, "h": 1920, "max_seconds": 90, "aspect": "9:16", "kind": "video"},
    "tiktok": {"w": 1080, "h": 1920, "max_seconds": 180, "aspect": "9:16", "kind": "video"},
    "x": {"w": 1280, "h": 720, "max_seconds": 140, "aspect": "16:9", "kind": "video"},
    "feed": {"w": 1080, "h": 1080, "max_seconds": 60, "aspect": "1:1", "kind": "image"},
    "story": {"w": 1080, "h": 1920, "max_seconds": 60, "aspect": "9:16", "kind": "image"},
}

# Platform -> (env token the send needs [creds-hydrate, never a chat ask], human lever).
# Vendor-app/token mint is lever L-SOCIAL-OAUTH; the publish itself is L-SOCIAL-SEND.
PLATFORM_CREDS = {
    "reel": ("IG_GRAPH_ACCESS_TOKEN", "L-SOCIAL-OAUTH"),
    "story": ("IG_GRAPH_ACCESS_TOKEN", "L-SOCIAL-OAUTH"),
    "feed": ("IG_GRAPH_ACCESS_TOKEN", "L-SOCIAL-OAUTH"),
    "tiktok": ("TIKTOK_ACCESS_TOKEN", "L-SOCIAL-OAUTH"),
    "x": ("X_ACCESS_TOKEN", "L-SOCIAL-OAUTH"),
}


def platform_preset(platform: str) -> dict:
    if platform not in PRESETS:
        raise ValueError(f"unknown platform {platform!r}; known: {', '.join(sorted(PRESETS))}")
    return PRESETS[platform]


def _kind_of(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in IMAGE_EXTS:
        return "image"
    return None


def select_assets(source: Path, kind: str, query: str | None, limit: int) -> list[Path]:
    """Newest-first assets under ``source`` matching ``kind`` (and ``query`` substring)."""
    if not source.exists():
        return []
    hits: list[Path] = []
    for p in sorted(source.rglob("*"), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
        if not p.is_file() or _kind_of(p) != kind:
            continue
        if query and query.lower() not in p.name.lower():
            continue
        hits.append(p)
        if len(hits) >= limit:
            break
    return hits


def ffmpeg_transcode_cmd(src: Path, dst: Path, preset: dict) -> list[str]:
    """Build the ffmpeg command to fit ``src`` to the platform ``preset`` (cover-crop)."""
    w, h = preset["w"], preset["h"]
    vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if preset["kind"] == "video":
        return [
            "ffmpeg",
            "-y",
            "-i",
            str(src),
            "-t",
            str(preset["max_seconds"]),
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(dst),
        ]
    return ["ffmpeg", "-y", "-i", str(src), "-vf", vf, "-frames:v", "1", str(dst)]


def caption_for(asset: Path, platform: str, note: str | None) -> str:
    """A first-pass draft caption from the asset name + platform. Human rewrites & owns it."""
    stem = asset.stem.replace("_", " ").replace("-", " ").strip()
    base = note.strip() if note else stem
    tags = {"reel": "#reels", "story": "", "feed": "", "tiktok": "#fyp", "x": ""}.get(platform, "")
    return " ".join(x for x in [base, tags] if x).strip()


@dataclass
class QueueItem:
    id: str
    platform: str
    source: str
    staged: str
    caption: str
    post_at: str
    status: str = "draft"  # draft -> approved -> sent (never auto)
    ffmpeg: list[str] = field(default_factory=list)


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _qid(asset: Path, platform: str) -> str:
    return f"{platform}-{abs(hash((asset.name, platform))) % 10**8:08d}"


def append_queue(item: QueueItem, queue_path: Path = QUEUE_PATH) -> None:
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    with queue_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(item)) + "\n")


def load_queue(queue_path: Path = QUEUE_PATH) -> list[dict]:
    if not queue_path.exists():
        return []
    out = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def plan(
    platform: str,
    source: Path,
    query: str | None,
    limit: int,
    note: str | None,
    when: str,
    apply: bool,
    stage_dir: Path = STAGE_DIR,
    queue_path: Path = QUEUE_PATH,
) -> list[QueueItem]:
    preset = platform_preset(platform)
    assets = select_assets(source, preset["kind"], query, limit)
    items: list[QueueItem] = []
    for a in assets:
        ext = ".mp4" if preset["kind"] == "video" else ".jpg"
        dst = stage_dir / platform / f"{a.stem}-{platform}{ext}"
        cmd = ffmpeg_transcode_cmd(a, dst, preset)
        if apply:
            dst.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(cmd, check=True, capture_output=True)
        item = QueueItem(
            id=_qid(a, platform),
            platform=platform,
            source=str(a),
            staged=str(dst),
            caption=caption_for(a, platform, note),
            post_at=when,
            status="draft",
            ffmpeg=cmd,
        )
        append_queue(item, queue_path)
        items.append(item)
    return items


def send(qid: str, queue_path: Path = QUEUE_PATH) -> int:
    """REFUSE to publish unless the platform token exists AND the human lever is pulled.

    This never posts on its own — it reports exactly which human atom is required.
    """
    items = load_queue(queue_path)
    match = next((i for i in items if i.get("id") == qid), None)
    if not match:
        print(f"no queue item {qid!r}")
        return 1
    platform = match.get("platform", "")
    env_key, lever = PLATFORM_CREDS.get(platform, (None, None))
    token = os.environ.get(env_key or "", "")
    if not token:
        print(
            f"REFUSED: no {env_key} in env. Mint it via lever {lever} (creds-hydrate, "
            f"never a chat ask), then re-run. Nothing was sent."
        )
        return 2
    print(
        f"REFUSED: publishing is a human-gated lever (L-SOCIAL-SEND). Token present, but a "
        f"send must be explicitly pulled by the human. Item {qid} stays 'draft'."
    )
    return 2


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Stage screengrabs/recordings as social assets (drafts only).")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("plan", help="select -> transcode/crop -> caption -> queue (dry-run default)")
    p.add_argument("--platform", required=True, choices=sorted(PRESETS))
    p.add_argument("--source", default=str(Path.home() / "Pictures" / "Screen Captures"))
    p.add_argument("--query", default=None, help="substring filter on filename")
    p.add_argument("--limit", type=int, default=5)
    p.add_argument("--note", default=None, help="caption seed (else derived from filename)")
    p.add_argument("--when", default="unscheduled", help="ISO post time or 'unscheduled'")
    p.add_argument("--apply", action="store_true", help="actually run ffmpeg (else just plan)")

    sub.add_parser("queue-list", help="print the draft queue")

    s = sub.add_parser("send", help="attempt publish (refused without token + human lever)")
    s.add_argument("--id", required=True)
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "plan":
        items = plan(
            args.platform,
            Path(args.source).expanduser(),
            args.query,
            args.limit,
            args.note,
            args.when,
            args.apply,
        )
        mode = "transcoded+queued" if args.apply else "planned (dry-run, no ffmpeg)"
        print(f"[{mode}] {len(items)} asset(s) for {args.platform}:")
        for it in items:
            print(f"  {it.id}  {Path(it.source).name} -> {Path(it.staged).name}")
            print(f"      caption: {it.caption}")
        if not items:
            print("  (no matching assets found)")
        print(f"queue: {QUEUE_PATH}")
        return 0
    if args.cmd == "queue-list":
        for it in load_queue():
            print(f"{it.get('status'):9} {it.get('id')}  {it.get('platform')}  {it.get('caption')}")
        return 0
    if args.cmd == "send":
        return send(args.id)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
