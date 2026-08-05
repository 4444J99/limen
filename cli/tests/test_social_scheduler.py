"""Tests for the Carrier-Wave media organ outbound scheduler (drafts only, no network)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

_SCHED = Path(__file__).resolve().parents[2] / "organs" / "media" / "scheduler" / "social_scheduler.py"
_spec = importlib.util.spec_from_file_location("social_scheduler", _SCHED)
ss = importlib.util.module_from_spec(_spec)
assert _spec and _spec.loader
sys.modules["social_scheduler"] = ss  # dataclasses need the module registered before exec
_spec.loader.exec_module(ss)


def test_platform_preset_dims():
    assert ss.platform_preset("reel")["w"] == 1080
    assert ss.platform_preset("reel")["h"] == 1920
    assert ss.platform_preset("x")["aspect"] == "16:9"
    assert ss.platform_preset("feed")["kind"] == "image"


def test_platform_preset_unknown_raises():
    with pytest.raises(ValueError):
        ss.platform_preset("myspace")


def test_select_assets_by_kind_and_query(tmp_path: Path):
    (tmp_path / "wrath-of-achilles.mov").write_bytes(b"v")
    (tmp_path / "boring.mov").write_bytes(b"v")
    (tmp_path / "shot.png").write_bytes(b"i")
    vids = ss.select_assets(tmp_path, "video", None, 10)
    assert {p.name for p in vids} == {"wrath-of-achilles.mov", "boring.mov"}
    filtered = ss.select_assets(tmp_path, "video", "wrath", 10)
    assert [p.name for p in filtered] == ["wrath-of-achilles.mov"]
    imgs = ss.select_assets(tmp_path, "image", None, 10)
    assert [p.name for p in imgs] == ["shot.png"]


def test_ffmpeg_cmd_video_and_image(tmp_path: Path):
    v = ss.ffmpeg_transcode_cmd(tmp_path / "a.mov", tmp_path / "o.mp4", ss.PRESETS["reel"])
    assert "libx264" in v and any("crop=1080:1920" in x for x in v) and v[0] == "ffmpeg"
    img = ss.ffmpeg_transcode_cmd(tmp_path / "a.png", tmp_path / "o.jpg", ss.PRESETS["feed"])
    assert "-frames:v" in img and "1" in img


def test_caption_derivation():
    cap = ss.caption_for(Path("wrath_of_achilles.mov"), "reel", None)
    assert "wrath of achilles" in cap and "#reels" in cap
    assert ss.caption_for(Path("x.mov"), "x", "Custom note") == "Custom note"


def test_plan_dry_run_does_not_write_queue(tmp_path: Path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "clip.mov").write_bytes(b"v")
    qpath = tmp_path / "queue.jsonl"
    stage = tmp_path / "staged"
    items = ss.plan(
        "reel",
        src,
        None,
        5,
        None,
        "unscheduled",
        apply=False,
        stage_dir=stage,
        queue_path=qpath,
    )
    assert len(items) == 1
    assert items[0].status == "draft"
    # dry-run must NOT run ffmpeg or mutate the queue.
    assert not stage.exists()
    assert not qpath.exists()


def test_plan_apply_writes_stable_draft_queue(tmp_path: Path, monkeypatch):
    src = tmp_path / "src"
    src.mkdir()
    (src / "clip.mov").write_bytes(b"v")
    qpath = tmp_path / "queue.jsonl"
    stage = tmp_path / "staged"

    def fake_run(cmd, check, capture_output):
        assert check is True
        assert capture_output is True
        Path(cmd[-1]).parent.mkdir(parents=True, exist_ok=True)
        Path(cmd[-1]).write_bytes(b"out")

    monkeypatch.setattr(ss.subprocess, "run", fake_run)

    items = ss.plan(
        "reel",
        src,
        None,
        5,
        None,
        "unscheduled",
        apply=True,
        stage_dir=stage,
        queue_path=qpath,
    )

    assert len(items) == 1
    assert items[0].id == ss._qid(src / "clip.mov", "reel")
    assert (stage / "reel" / "clip-reel.mp4").exists()
    rows = [json.loads(x) for x in qpath.read_text().splitlines() if x.strip()]
    assert rows[0]["platform"] == "reel" and rows[0]["status"] == "draft"
    assert rows[0]["ffmpeg"][0] == "ffmpeg"
    assert rows[0]["id"] == items[0].id


def test_send_refused_without_token(tmp_path: Path, monkeypatch):
    qpath = tmp_path / "queue.jsonl"
    item = ss.QueueItem(
        id="reel-00000001",
        platform="reel",
        source="a.mov",
        staged="o.mp4",
        caption="c",
        post_at="unscheduled",
    )
    ss.append_queue(item, qpath)
    monkeypatch.delenv("IG_GRAPH_ACCESS_TOKEN", raising=False)
    # never posts: returns non-zero refusal
    assert ss.send("reel-00000001", qpath) == 2
    assert ss.send("nope", qpath) == 1


def test_queue_roundtrip(tmp_path: Path):
    qpath = tmp_path / "q.jsonl"
    ss.append_queue(
        ss.QueueItem(id="x-1", platform="x", source="s", staged="d", caption="c", post_at="unscheduled"), qpath
    )
    loaded = ss.load_queue(qpath)
    assert loaded[0]["id"] == "x-1"
