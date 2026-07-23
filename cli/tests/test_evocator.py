import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "evocator.py"


def _load(monkeypatch, root: Path):
    monkeypatch.setenv("LIMEN_ROOT", str(root))
    monkeypatch.setenv("LIMEN_EVOCATOR_CANON", str(root / "spec" / "evocator" / "canon.yaml"))
    monkeypatch.setenv("LIMEN_FLAME_FILE", str(root / "FLAME.md"))
    monkeypatch.setenv("LIMEN_MEMORY_DIR", str(root / "memory"))
    monkeypatch.setenv("LIMEN_KNOWLEDGE_CORPUS", str(root / "no-knowledge-corpus"))
    spec = importlib.util.spec_from_file_location("evocator_uut", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_canon_fail_open_on_wrong_yaml_shape(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    canon = tmp_path / "spec" / "evocator" / "canon.yaml"
    canon.parent.mkdir(parents=True)
    canon.write_text("- not\n- a\n- mapping\n")

    truths, problems = module.load_canon()

    assert truths == []
    assert len(problems) == 1
    assert "canon root is list" in problems[0]
    assert "skipped" in problems[0]


def test_load_canon_normalizes_bad_channels(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    canon = tmp_path / "spec" / "evocator" / "canon.yaml"
    canon.parent.mkdir(parents=True)
    canon.write_text(
        """
truths:
  - id: EVO-TEST
    claim: Test truth
    line: Keep this present
    channels: [flame]
"""
    )

    truths, problems = module.load_canon()
    view = module.build_view(truths, [], "unchanged", "skipped", problems)
    html = module.render_html(view)

    assert truths[0]["channels"] == {}
    assert "channels is not a mapping" in problems[0]
    assert "Test truth" in html
    assert json.loads(json.dumps(view))["summary"]["problems"] == 1


def test_census_is_counts_only(tmp_path, monkeypatch):
    module = _load(monkeypatch, tmp_path)
    canon = tmp_path / "spec" / "evocator" / "canon.yaml"
    canon.parent.mkdir(parents=True)
    canon.write_text(
        """
truths:
  - id: EVO-SECRET
    claim: Secret private body
    line: Keep ssn 123-45-6789 out of public census
    summons: Full private canon text
    source_of_record: private/repo
    reversible_via: edit private/repo
    channels:
      flame: true
      corpus: true
      memory: secret-memory-slug
"""
    )

    census = module.census()
    encoded = json.dumps(census, sort_keys=True)

    assert census == {
        "truths": 1,
        "channels": {"flame": 1, "corpus": 1, "memory": 1},
        "memory_checks": 1,
        "memory_drift": 1,
        "canon_problems": 0,
        "surfaces": {"flame": False, "canon_markdown": False, "corpus": False},
    }
    assert "Secret private body" not in encoded
    assert "123-45-6789" not in encoded
    assert "secret-memory-slug" not in encoded
