import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "studium-validate.py"


def _load(monkeypatch, root):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    spec = importlib.util.spec_from_file_location("studium_validate_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_minimal_arc(root, checked=True, index_done=1):
    studium = root / "studium"
    work = studium / "music" / "sample"
    work.mkdir(parents=True)
    (studium / "dominant-force.yaml").write_text(
        "forces:\n  wrath: {requirement: pressure, color: '#c0392b', composer_hints: []}\n"
    )
    (work / "book-01.yaml").write_text(
        "work: sample\n"
        "book: 1\n"
        "title: Sample\n"
        "dominant_force: wrath\n"
        "force_arc: [wrath]\n"
        "tracks:\n"
        "  - {n: 1, scene: one, force: wrath, composer: X, work: Y, decision: added, why: z}\n"
    )
    status = "✓" if checked else "☐"
    (work / "PLAN.md").write_text(
        "# Music arcs — Sample (`sample`)\n\n"
        f"- **Progress:** {1 if checked else 0}/1 arcs authored\n\n"
        "| Book | dominant force | status |\n"
        "| --: | --- | :--: |\n"
        f"| 1 | (author) | {status} |\n"
    )
    (studium / "music" / "PLAN.md").write_text(
        f"# Music layer\n\n- [`sample`](sample/PLAN.md) — Sample · {index_done}/1 arcs\n"
    )


def test_studium_validate_rejects_stale_plan_checkmark(tmp_path, monkeypatch, capsys):
    module = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["studium-validate.py"])
    _write_minimal_arc(tmp_path, checked=False, index_done=0)

    assert module.main() == 1
    out = capsys.readouterr().out
    assert "music/sample/PLAN.md" in out
    assert "unchecked existing book(s) [1]" in out


def test_studium_validate_accepts_synced_plan_ledgers(tmp_path, monkeypatch, capsys):
    module = _load(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "argv", ["studium-validate.py"])
    _write_minimal_arc(tmp_path, checked=True, index_done=1)

    assert module.main() == 0
    out = capsys.readouterr().out
    assert "plans match files" in out
