import importlib.util
import json
import subprocess
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


def test_advance_photos_treats_nothing_to_prove_as_skip(tmp_path, monkeypatch):
    root = tmp_path / "limen"
    photos = tmp_path / "photos"
    portvs = tmp_path / "portvs"
    root.mkdir()
    photos.mkdir()
    portvs.mkdir()
    module = _load(monkeypatch, root, photos, portvs)

    monkeypatch.setattr(module, "repo_clean", lambda repo: True)
    monkeypatch.setattr(
        module,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(
            a[0],
            1,
            "",
            "[photos-duplicate-proof] candidates missing - nothing to prove",
        ),
    )

    result = module.advance_photos(apply=False, limit_groups=25)

    assert result["ok"] is True
    assert result["skipped"] == "no duplicate candidates to prove"


def test_session_value_gate_blocks_continuation_lane_switch(tmp_path, monkeypatch):
    root = tmp_path / "limen"
    photos = tmp_path / "photos"
    portvs = tmp_path / "portvs"
    root.mkdir()
    photos.mkdir()
    portvs.mkdir()
    module = _load(monkeypatch, root, photos, portvs)

    def fake_run(args, cwd, timeout=120):
        assert args[:3] == ["python3", "scripts/session-value-review.py", "--gate"]
        return subprocess.CompletedProcess(
            args,
            10,
            json.dumps(
                {
                    "action": "switch_to_packetization",
                    "reason": "lane switch required",
                    "next_commands": ["python3 scripts/prompt-packet-ledger.py --write"],
                }
            ),
            "",
        )

    monkeypatch.setattr(module, "run", fake_run)

    result = module.session_value_gate()

    assert result["ok"] is False
    assert result["returncode"] == 10
    assert result["lane_switch"] is True
    assert result["action"] == "switch_to_packetization"
    assert result["next_command"] == "python3 scripts/prompt-packet-ledger.py --write"
