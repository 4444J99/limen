from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "merge-ready.py"


def _load():
    spec = importlib.util.spec_from_file_location("merge_ready", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _FakeMergeDrain:
    OWNERS = ["organvm"]

    @staticmethod
    def gh(_args, timeout=60):
        raise AssertionError("live gh must not be called in this test")

    @staticmethod
    def enumerate_open_prs(owners, gh_fn, max_total=500, want_url=False):
        assert owners == ["organvm"]
        assert max_total == 3
        assert want_url is False
        return [
            ("organvm/a-i-chat--exporter", 10),
            ("organvm/limen", 20),
            ("organvm/noisy", 30),
        ]

    @staticmethod
    def assess(pr):
        repo, number = pr
        if repo == "organvm/noisy":
            return repo, number, "CI-RED"
        return repo, number, "READY"


def test_merge_ready_uses_current_merge_drain_enumerator(monkeypatch, tmp_path: Path):
    mod = _load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    monkeypatch.setattr(mod, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(mod, "DOCS", tmp_path / "docs")
    monkeypatch.setattr(mod, "_load_merge_drain", lambda: _FakeMergeDrain)
    monkeypatch.setattr(mod, "_ladder_ranks", lambda: {"organvm/a-i-chat--exporter": 1})
    monkeypatch.setattr(mod, "_value_repos", lambda: {"organvm/a-i-chat--exporter"})

    assert mod.main(["--scan", "3"]) == 0

    doc = (tmp_path / "docs" / "MERGE-READY.md").read_text(encoding="utf-8")
    assert "2 are CLEAN" in doc
    assert "`organvm/a-i-chat--exporter#10`" in doc
    assert "`organvm/noisy#30`" in doc


def test_value_repos_reads_repo_list(monkeypatch, tmp_path: Path):
    mod = _load()
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    (tmp_path / "value-repos.json").write_text(
        '{"repos": ["organvm/a-i-chat--exporter", "organvm/limen"]}',
        encoding="utf-8",
    )

    assert mod._value_repos() == {"organvm/a-i-chat--exporter", "organvm/limen"}
