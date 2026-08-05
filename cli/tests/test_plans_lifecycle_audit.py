"""Tests for scripts/plans-lifecycle-audit.py — the missing lifecycle for plan documents.

Hermetic: every corpus path is redirected to a tmp_path fixture via env overrides
(LIMEN_CLAUDE_PLANS_DIR / LIMEN_CODEX_PLANS_DIR / LIMEN_ROOT), so no test ever touches a real
~/.claude/plans, ~/.codex/plans, or this repo's own docs/plans/.
"""

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "plans-lifecycle-audit.py"


def _mod():
    # The module must be registered in sys.modules BEFORE exec — @dataclass resolves its
    # `from __future__ import annotations` string annotations via sys.modules[cls.__module__],
    # which is otherwise absent for a spec_from_file_location load and raises AttributeError.
    spec = importlib.util.spec_from_file_location("plans_lifecycle_audit_under_test", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


def _write(path: Path, *, age_days: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stub plan content\n", encoding="utf-8")
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))


def _fixture(tmp_path, monkeypatch):
    claude_dir = tmp_path / "claude-plans"
    codex_dir = tmp_path / "codex-plans"
    repo_root = tmp_path / "repo"
    docs_plans = repo_root / "docs" / "plans"

    _write(claude_dir / "fresh.md", age_days=1)
    _write(claude_dir / "stale.md", age_days=45)
    _write(claude_dir / "nested" / "also-stale.md", age_days=60)

    _write(codex_dir / "old-codex.md", age_days=40)

    _write(docs_plans / "tracked-stale.md", age_days=90)

    monkeypatch.setenv("LIMEN_CLAUDE_PLANS_DIR", str(claude_dir))
    monkeypatch.setenv("LIMEN_CODEX_PLANS_DIR", str(codex_dir))
    monkeypatch.setenv("LIMEN_ROOT", str(repo_root))

    return claude_dir, codex_dir, docs_plans


def test_report_only_never_writes(tmp_path, monkeypatch):
    claude_dir, codex_dir, docs_plans = _fixture(tmp_path, monkeypatch)
    m = _mod()

    reports = m.audit(apply=False, stale_days=30)
    by_label = {r.label: r for r in reports}

    assert by_label["claude-plans"].total == 3
    assert set(by_label["claude-plans"].stale) == {"stale.md", "nested/also-stale.md"}
    assert by_label["claude-plans"].archived == []
    assert (claude_dir / "stale.md").exists()  # untouched
    assert (claude_dir / "nested" / "also-stale.md").exists()

    assert by_label["codex-plans"].stale == ["old-codex.md"]
    assert by_label["codex-plans"].archived == []
    assert (codex_dir / "old-codex.md").exists()

    # git-tracked corpus: always flagged as stale (visible), never archived, regardless of --apply
    assert by_label["docs-plans"].archivable is False
    assert by_label["docs-plans"].stale == ["tracked-stale.md"]
    assert (docs_plans / "tracked-stale.md").exists()


def test_apply_archives_only_untracked_corpora(tmp_path, monkeypatch):
    claude_dir, codex_dir, docs_plans = _fixture(tmp_path, monkeypatch)
    m = _mod()

    reports = m.audit(apply=True, stale_days=30)
    by_label = {r.label: r for r in reports}

    # Untracked: moved into archive/, never deleted.
    assert not (claude_dir / "stale.md").exists()
    assert (claude_dir / "archive" / "stale.md").exists()
    assert not (claude_dir / "nested" / "also-stale.md").exists()
    assert (claude_dir / "archive" / "nested" / "also-stale.md").exists()
    assert (claude_dir / "fresh.md").exists()  # not stale, untouched
    assert sorted(by_label["claude-plans"].archived) == ["nested/also-stale.md", "stale.md"]

    assert not (codex_dir / "old-codex.md").exists()
    assert (codex_dir / "archive" / "old-codex.md").exists()

    # docs/plans/ is NEVER touched by --apply, no matter how stale.
    assert (docs_plans / "tracked-stale.md").exists()
    assert not (docs_plans / "archive").exists()
    assert by_label["docs-plans"].archived == []


def test_archived_entries_are_not_rescanned_next_run(tmp_path, monkeypatch):
    claude_dir, _codex_dir, _docs_plans = _fixture(tmp_path, monkeypatch)
    m = _mod()
    m.audit(apply=True, stale_days=30)

    second = m.audit(apply=False, stale_days=30)
    claude_report = next(r for r in second if r.label == "claude-plans")
    assert claude_report.stale == []  # the archived files are excluded from the corpus, not re-flagged
    assert (claude_dir / "archive" / "stale.md").exists()


def test_absent_corpus_is_reported_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_CLAUDE_PLANS_DIR", str(tmp_path / "does-not-exist"))
    monkeypatch.setenv("LIMEN_CODEX_PLANS_DIR", str(tmp_path / "also-missing"))
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path / "repo-missing"))
    m = _mod()

    reports = m.audit(apply=False, stale_days=30)
    assert all(r.present is False for r in reports)
    assert all(r.total == 0 and r.stale == [] for r in reports)


def test_json_output_is_well_formed(tmp_path, monkeypatch, capsys):
    _fixture(tmp_path, monkeypatch)
    m = _mod()

    rc = m.main(["--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["applied"] is False
    labels = {c["label"] for c in payload["corpora"]}
    assert labels == {"claude-plans", "codex-plans", "docs-plans"}
