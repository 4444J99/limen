"""The normalized-archive store: registry rows, the kind enum, and the resolver rules.

Synthetic registries and directories only. No conversation text appears anywhere.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import corpus_resolve  # noqa: E402  (path inserted above)


def _load_check_corpora():
    spec = importlib.util.spec_from_file_location("check_corpora_under_test", SCRIPTS / "check-corpora.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def check_corpora():
    module = _load_check_corpora()
    module.FAILURES.clear()
    module.ADVISORIES.clear()
    return module


def _row(store: str, kind: str, **extra) -> dict:
    row = {"store": store, "provider": "multi", "kind": kind, "owner": "cce", "note": "synthetic"}
    row.update(extra)
    return row


def _registry(tmp_path: Path) -> dict:
    """Archive store declared FIRST so a skip by rule, not by order, is what the tests prove."""
    return {
        "stores": {
            "archive": {"root": str(tmp_path / "archive"), "remote": "none", "owner": "cce", "note": "n"},
            "sessions": {"root": str(tmp_path / "sessions"), "remote": "none", "owner": "cce", "note": "n"},
            "mixed": {"root": str(tmp_path / "mixed"), "remote": "none", "owner": "cce", "note": "n"},
            "empty": {"root": str(tmp_path / "empty"), "remote": "none", "owner": "cce", "note": "n"},
        },
        "corpora": {
            "archive-all": _row("archive", "normalized-archive"),
            "session-one": _row("sessions", "session-memory"),
            "mixed-archive": _row("mixed", "normalized-archive"),
            "mixed-session": _row("mixed", "session-memory", cce_id="mixed-alias"),
            "pathed": _row("sessions", "raw-archive", path="data/pathed"),
        },
    }


@pytest.fixture()
def populated(tmp_path, monkeypatch):
    for name in ("archive/archive-all", "sessions/session-one", "mixed/mixed-session", "empty/something"):
        (tmp_path / name).mkdir(parents=True)
    doc = _registry(tmp_path)
    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: doc)
    monkeypatch.setattr(corpus_resolve, "live_root", lambda: tmp_path / "live")
    monkeypatch.delenv("LIMEN_CORPUS_ROOT", raising=False)
    monkeypatch.delenv("CCE_SOURCE_DROP_ROOT", raising=False)
    return doc


def test_archive_only_roots_name_only_stores_whose_rows_are_all_normalized_archive(populated, tmp_path):
    assert corpus_resolve.archive_only_store_roots(populated) == {tmp_path / "archive"}


def test_corpus_home_skips_an_archive_only_store_even_when_it_is_populated_and_first(populated, tmp_path):
    assert (tmp_path / "archive" / "archive-all").is_dir()
    assert corpus_resolve.corpus_home() == tmp_path / "sessions"


def test_corpus_home_keeps_a_mixed_store_and_a_store_with_no_rows(populated, tmp_path, monkeypatch):
    sessions_doc = dict(populated)
    sessions_doc["stores"] = {k: v for k, v in populated["stores"].items() if k in ("mixed", "empty")}
    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: sessions_doc)
    assert corpus_resolve.corpus_home() == tmp_path / "mixed"
    only_empty = dict(sessions_doc)
    only_empty["stores"] = {"empty": populated["stores"]["empty"]}
    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: only_empty)
    assert corpus_resolve.corpus_home() == tmp_path / "empty"


def test_corpus_home_never_falls_back_to_the_archive_store(populated, tmp_path, monkeypatch):
    archive_only = {
        "stores": {"archive": populated["stores"]["archive"]},
        "corpora": {"archive-all": populated["corpora"]["archive-all"]},
    }
    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: archive_only)
    assert corpus_resolve.corpus_home() != tmp_path / "archive"


def test_an_explicit_corpus_root_may_name_the_archive_store(populated, tmp_path, monkeypatch):
    monkeypatch.setenv("LIMEN_CORPUS_ROOT", str(tmp_path / "archive"))
    assert corpus_resolve.corpus_home() == tmp_path / "archive"


def test_corpus_root_is_store_root_joined_with_the_registry_id(populated, tmp_path):
    assert corpus_resolve.corpus_root("archive-all") == tmp_path / "archive" / "archive-all"
    assert corpus_resolve.corpus_root("session-one") == tmp_path / "sessions" / "session-one"


def test_corpus_root_honours_a_row_path_and_a_cce_alias(populated, tmp_path):
    assert corpus_resolve.corpus_root("pathed") == tmp_path / "sessions" / "data" / "pathed"
    assert corpus_resolve.corpus_root("mixed-alias") == tmp_path / "mixed" / "mixed-session"


def test_corpus_root_names_a_declared_corpus_whose_directory_is_absent(populated, tmp_path):
    target = corpus_resolve.corpus_root("mixed-archive")
    assert target == tmp_path / "mixed" / "mixed-archive"
    assert not target.exists()


def test_corpus_root_is_none_for_an_undeclared_id_or_unknown_store(populated):
    assert corpus_resolve.corpus_root("never-declared") is None
    broken = {"stores": {}, "corpora": {"orphan": _row("missing-store", "session-memory")}}
    assert corpus_resolve.corpus_root("orphan", broken) is None


def test_corpus_root_expands_home_in_a_store_root():
    doc = {
        "stores": {"s": {"root": "~/somewhere"}},
        "corpora": {"c": _row("s", "session-memory")},
    }
    assert corpus_resolve.corpus_root("c", doc) == Path.home() / "somewhere" / "c"


# --- the committed registry itself -------------------------------------------------


def _real_registry() -> dict:
    return corpus_resolve.load_registry()


def test_registry_declares_the_archive_store_last_with_no_remote():
    stores = list(_real_registry()["stores"])
    assert stores[-1] == "limen-private-archive"
    store = _real_registry()["stores"]["limen-private-archive"]
    assert store["remote"] == "none"
    assert store["git"] is False
    assert store["owner"] == "cce"
    assert store["root"] == "~/Workspace/limen/.limen-private/session-corpus/archive"


def test_registry_declares_the_archive_row_as_unharvestable_and_unredacted():
    row = _real_registry()["corpora"]["archive-all"]
    assert row["store"] == "limen-private-archive"
    assert row["provider"] == "multi"
    assert row["kind"] == "normalized-archive"
    assert row["cce_declared"] is False
    assert row["harvestable"] is False
    assert row["redacted"] is False
    assert row["owner"] == "cce"


def test_registry_archive_store_is_archive_only_and_resolves_by_id():
    doc = _real_registry()
    assert Path("~/Workspace/limen/.limen-private/session-corpus/archive").expanduser() in (
        corpus_resolve.archive_only_store_roots(doc)
    )
    expected = Path("~/Workspace/limen/.limen-private/session-corpus/archive/archive-all").expanduser()
    assert corpus_resolve.corpus_root("archive-all", doc) == expected


def test_registry_archive_store_never_becomes_the_home_even_when_populated(tmp_path, monkeypatch):
    doc = _real_registry()
    redirected = {
        "stores": {
            name: ({**store, "root": str(tmp_path / "archive")} if name == "limen-private-archive" else store)
            for name, store in doc["stores"].items()
        },
        "corpora": doc["corpora"],
    }
    (tmp_path / "archive" / "archive-all").mkdir(parents=True)
    monkeypatch.setattr(corpus_resolve, "load_registry", lambda: redirected)
    monkeypatch.delenv("LIMEN_CORPUS_ROOT", raising=False)
    monkeypatch.delenv("CCE_SOURCE_DROP_ROOT", raising=False)
    assert corpus_resolve.corpus_home() != tmp_path / "archive"


# --- check-corpora ------------------------------------------------------------------


def test_normalized_archive_is_a_valid_kind(check_corpora):
    assert "normalized-archive" in check_corpora.VALID_KIND


def test_schema_check_accepts_a_normalized_archive_row_and_rejects_an_unknown_kind(check_corpora):
    doc = {
        "stores": {"s": {"root": "/x", "remote": "none", "owner": "cce", "note": "n"}},
        "corpora": {"good": _row("s", "normalized-archive")},
    }
    check_corpora.check_a_schema(doc)
    assert check_corpora.FAILURES == []
    doc["corpora"]["bad"] = _row("s", "not-a-kind")
    check_corpora.check_a_schema(doc)
    assert len(check_corpora.FAILURES) == 1
    assert "normalized-archive" in check_corpora.FAILURES[0]


def test_the_committed_registry_passes_schema_and_literal_checks(check_corpora):
    doc = _real_registry()
    check_corpora.check_a_schema(doc)
    check_corpora.check_d_resolver_sole(doc, check_corpora.load_baseline())
    assert check_corpora.FAILURES == []


def test_literal_check_leaves_out_an_archive_only_store_name(check_corpora):
    doc = _real_registry()
    names = check_corpora.literal_dirnames(doc)
    assert "archive" not in names
    assert "local-memory" in names
    assert "session-meta" in names


def test_literal_check_still_flags_a_session_store_name(check_corpora):
    doc = {
        "stores": {"s": {"root": "/x/_session_store_dir", "remote": "none", "owner": "cce", "note": "n"}},
        "corpora": {"c": _row("s", "session-memory")},
    }
    assert check_corpora.literal_dirnames(doc) == ["_session_store_dir"]
