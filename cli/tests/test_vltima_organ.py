from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "vltima-organ.py"


def _load(monkeypatch, tmp_path: Path, name: str = "vltima_organ_test"):
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    monkeypatch.setenv("LIMEN_PRIVATE_SESSION_CORPUS", str(tmp_path / ".limen-private" / "session-corpus"))
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _seed_vltima_surfaces(root: Path) -> None:
    docs = root / "docs"
    lifecycle = root / ".limen-private" / "session-corpus" / "lifecycle"
    docs.mkdir(parents=True)
    lifecycle.mkdir(parents=True)
    for name in (
        "vltima-absorb-cadence.md",
        "vltima-prior-excavations.md",
        "vltima-result-digest.md",
        "vltima-owner-certainty.md",
        "vltima-action-packets.md",
    ):
        (docs / name).write_text(f"# {name}\n\nGenerated: `2026-07-06T00:00:00+00:00`\n", encoding="utf-8")
    _write_json(lifecycle / "vltima-absorb-cadence.json", {"generated_at": "2026-07-06T00:00:00+00:00", "status": "ok"})
    _write_json(
        lifecycle / "vltima-prior-excavations.json",
        {"generated_at": "2026-07-06T00:00:00+00:00", "mismatches": [], "coverage": {"surface_count": 3}},
    )
    _write_json(
        lifecycle / "vltima-result-digest.json",
        {"generated_at": "2026-07-06T00:00:00+00:00", "mismatch_surfaces": [], "coverage": {"claim_count": 5}},
    )
    _write_json(
        lifecycle / "vltima-owner-certainty.json",
        {"generated_at": "2026-07-06T00:00:00+00:00", "coverage": {"unowned_dispatchable_count": 0}},
    )
    _write_json(
        lifecycle / "vltima-action-packets.json",
        {"generated_at": "2026-07-06T00:00:00+00:00", "coverage": {"packet_count": 2}},
    )


def test_build_state_passes_when_public_private_surfaces_are_consistent(tmp_path: Path, monkeypatch) -> None:
    _seed_vltima_surfaces(tmp_path)
    organ = _load(monkeypatch, tmp_path, "vltima_organ_ok")

    state = organ.build_state(include_github_meta=False)

    assert state["status"] == "ok"
    assert state["coverage"]["issues"] == 0
    assert state["coverage"]["digest_claim_count"] == 5
    assert state["coverage"]["packet_count"] == 2


def test_check_fails_when_private_index_has_no_public_doctrine(tmp_path: Path, monkeypatch) -> None:
    _seed_vltima_surfaces(tmp_path)
    (tmp_path / "docs" / "vltima-result-digest.md").unlink()
    organ = _load(monkeypatch, tmp_path, "vltima_organ_missing_doc")

    state = organ.build_state(include_github_meta=False)

    assert state["status"] == "failed"
    assert any(issue["surface"] == "result digest" for issue in state["issues"])


def test_render_ideal_doc_records_autopoietic_loop(tmp_path: Path, monkeypatch) -> None:
    _seed_vltima_surfaces(tmp_path)
    organ = _load(monkeypatch, tmp_path, "vltima_organ_doc")

    markdown = organ.render_ideal_doc(organ.build_state(include_github_meta=False))

    assert "# VLTIMA Ideal Form" in markdown
    assert "Doctrine becomes work only through bounded packets" in markdown
    assert "No `tasks.yaml` mutation in v1" in markdown

