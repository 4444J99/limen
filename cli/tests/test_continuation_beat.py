import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "continuation-beat.py"


def _load(monkeypatch, root: Path, photos: Path, portvs: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_PHOTOS_UNIVERSE_ROOT", str(photos))
    monkeypatch.setenv("LIMEN_PORTVS_TRIPTYCH_ROOT", str(portvs))
    spec = importlib.util.spec_from_file_location("continuation_beat_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_census_is_counts_only(tmp_path, monkeypatch):
    root = tmp_path / "limen"
    photos = tmp_path / "private-photos-root"
    portvs = tmp_path / "private-portvs-root"
    triptych = portvs / "incubator" / "triptych-video-canon"
    docs = root / "docs"
    logs = root / "logs"
    docs.mkdir(parents=True)
    logs.mkdir(parents=True)
    photos.mkdir()
    triptych.mkdir(parents=True)
    (docs / "worktree-preservation-receipts.json").write_text(
        json.dumps({"receipts": [{"root": "private-root", "path": "/private/path"}]}),
        encoding="utf-8",
    )
    (logs / "continuation-beat.json").write_text(
        json.dumps({"ok": True, "steps": {"private-step": {"detail": "private detail"}}}),
        encoding="utf-8",
    )
    (logs / "codex-token-report.json").write_text(json.dumps({"private": "token detail"}), encoding="utf-8")

    module = _load(monkeypatch, root, photos, portvs)
    census = module.census()
    encoded = json.dumps(census, sort_keys=True)

    assert census == {
        "receipts_present": True,
        "preservation_receipts": 1,
        "last_log_present": True,
        "last_step_count": 1,
        "last_ok": True,
        "token_report_present": True,
        "photos_root_present": True,
        "portvs_root_present": True,
        "triptych_root_present": True,
        "lock_present": False,
    }
    assert "private-root" not in encoded
    assert "/private/path" not in encoded
    assert "private-step" not in encoded
    assert "token detail" not in encoded
