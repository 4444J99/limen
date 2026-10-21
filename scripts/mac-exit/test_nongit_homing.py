"""Unit tests for scripts/mac-exit/nongit_homing.py (the engine behind nongit-homing.sh).

Everything runs on throwaway trees under pytest's tmp_path; nothing outside it is read or written. The end-to-end,
process-level proof (confirmation gate, free-space refusal, a live WAL database, a real mid-copy change) is
scripts/mac-exit/nongit-homing-selftest.sh; these tests cover the engine's decisions one at a time, including the
failure paths that need a hook inside the copy (DRIFT, MISMATCH) to be deterministic.

  python3 -m pytest -p no:cacheprovider scripts/mac-exit/test_nongit_homing.py -q
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import sqlite3
import stat
import sys
import time
import types
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent / "nongit_homing.py"
EXAMPLE = Path(__file__).resolve().parent / "examples" / "nongit-items.example.tsv"


def _load():
    spec = importlib.util.spec_from_file_location("nongit_homing_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their annotations through sys.modules
    spec.loader.exec_module(module)
    return module


nh = _load()

try:
    SQLITE = nh.find_sqlite()
except nh.HomingError:
    SQLITE = None
needs_sqlite = pytest.mark.skipif(SQLITE is None, reason="sqlite3 CLI is not installed")


@pytest.fixture
def env(tmp_path):
    home = tmp_path / "home"
    ext = tmp_path / "ext"
    home.mkdir()
    ext.mkdir()
    return types.SimpleNamespace(tmp=tmp_path, home=home, ext=ext)


def put(path: Path, data: bytes | str = b"x", mode: int | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    if mode is not None:
        path.chmod(mode)
    return path


def go(env, rows, apply=True, run="run", sqlite_bin=None, **kw):
    """Parse rows (name, source, dest_rel[, globs]) and run them; returns (homer, text, code)."""
    items_tsv = env.tmp / "items.tsv"
    items_tsv.write_text("".join("\t".join(r) + "\n" for r in rows))
    items = nh.parse_items(str(items_tsv), str(env.home))
    homer = nh.Homer(apply=apply, run_dir=str(env.ext / run), sqlite_bin=sqlite_bin or SQLITE or "sqlite3", **kw)
    text, code = homer.run(items)
    return homer, text, code


def manifest(run_dir: Path) -> dict[str, str]:
    out = {}
    for line in (run_dir / "MANIFEST.sha256").read_text().splitlines():
        sha, _, rel = line.partition("  ")
        out[rel] = sha
    return out


def assert_manifest_reverifies(run_dir: Path) -> None:
    for rel, sha in manifest(run_dir).items():
        assert hashlib.sha256((run_dir / rel).read_bytes()).hexdigest() == sha, rel


# --- items file ----------------------------------------------------------------------------------------------------


def test_example_items_file_parses():
    items = nh.parse_items(str(EXAMPLE), "/h")
    assert [i.name for i in items] == [
        "example-docs",
        "example-notes-db",
        "example-projects-loose",
        "example-projects-archive",
    ]
    assert items[0].source == "/h/ExampleDocs" and items[0].globs == ("Caches", "*.tmp", "node_modules")
    assert items[2].carve == frozenset({"archive"}) and items[2].globs == ("build",)


@pytest.mark.parametrize(
    "row",
    [
        "x\t/abs\t../escape",
        "x\t/abs\ta/../../escape",
        "x\t/abs\t/abs/dest",
        "x\t/abs\t.",
        "x\t/abs\t-dash",
        "x\t/abs\ta\\b",
        "x\trelative/src\tdest",
        "x\t$OTHER/src\tdest",
        "x\t/abs",
        "x\t/abs\tdest\tg\textra",
        "\t/abs\tdest",
        "x\t\tdest",
        "x\t/abs\tdest\t=a/b",
    ],
)
def test_parse_items_rejects_unsafe_or_malformed_rows(tmp_path, row):
    f = tmp_path / "items.tsv"
    f.write_text(row + "\n")
    with pytest.raises(nh.HomingError):
        nh.parse_items(str(f), "/h")


def test_parse_items_rejects_duplicates_and_empty(tmp_path):
    f = tmp_path / "items.tsv"
    f.write_text("a\t/s1\td1\na\t/s2\td2\n")
    with pytest.raises(nh.HomingError, match="name 'a' already used"):
        nh.parse_items(str(f), "/h")
    f.write_text("a\t/s1\td\nb\t/s2\td/\n")
    with pytest.raises(nh.HomingError, match="dest_rel 'd' already used"):
        nh.parse_items(str(f), "/h")
    f.write_text("# only a comment\n\n")
    with pytest.raises(nh.HomingError, match="no items"):
        nh.parse_items(str(f), "/h")


def test_parse_items_home_forms_and_crlf(tmp_path):
    f = tmp_path / "items.tsv"
    f.write_bytes(b"a\t$HOME/x\tda\r\nb\t${HOME}/y\tdb\r\nc\t~/z\tdc\r\nd\t~\tdd\r\n")
    assert [i.source for i in nh.parse_items(str(f), "/h")] == ["/h/x", "/h/y", "/h/z", "/h"]


# --- credential, exclusion and name rules --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [".env", ".ENV", ".prod.env", ".env.local", ".netrc", "id_rsa", "id_ed25519.pub", "server.PEM", "wallet.p12",
     "a.key", "secrets.yaml", "Login Data", "Login Data-journal", "cookies.sqlite", "client_secret_123.json",
     "my-tokens.json", "api.token", ".claude.json", "mcp.json", "config.toml", "x.credentials.json"],
)  # fmt: skip
def test_credential_file_names_are_matched(name):
    assert nh.ci_match(name, nh.CRED_FILE_GLOBS)


@pytest.mark.parametrize(
    "name", ["author.txt", "environment.md", "monkey.txt", "tokenizer.py", "notes.sqlite", "readme"]
)
def test_ordinary_names_are_not_credentials(name):
    assert nh.ci_match(name, nh.CRED_FILE_GLOBS) is None


def test_credential_dir_multi_component_glob_bites_below_the_item_root(tmp_path):
    put(tmp_path / ".config" / "gh" / "hosts.yml", "FAKE")
    put(tmp_path / ".config" / "other" / "ok.txt")
    homer = nh.Homer(apply=False, run_dir=str(tmp_path / "run"), sqlite_bin="sqlite3")
    seen = [(rel, kind) for rel, kind, _ in homer.walk(str(tmp_path / ".config"), ())]
    assert ("other", "dir") in seen and ("other/ok.txt", "file") in seen
    assert not any(rel.startswith("gh") for rel, _ in seen)
    assert [r[0] for r in homer.excluded_rows] == ["credential-dir"]


def test_item_excluded_matches_rel_basename_and_prefix():
    assert nh.item_excluded("a/Caches", ["Caches"])
    assert nh.item_excluded("Caches/x/y", ["Caches"])
    assert nh.item_excluded("a/b.tmp", ["*.tmp"])
    assert not nh.item_excluded("a/b.txt", ["*.tmp", ""])


def test_exclusion_for_file_dataless_and_credential_precedence():
    placeholder = types.SimpleNamespace(st_flags=nh.SF_DATALESS)
    assert nh.exclusion_for_file("movie.mov", placeholder, nh.CRED_FILE_GLOBS)[0] == "dataless-placeholder"
    assert nh.exclusion_for_file("movie.mov", types.SimpleNamespace(st_flags=0), nh.CRED_FILE_GLOBS) is None
    assert nh.exclusion_for_file(".env", placeholder, nh.CRED_FILE_GLOBS)[0] == "credential-file"


def test_tsv_cell_escapes_separators():
    assert nh.tsv_cell("a\tb\nc\rd\\e") == "a\\tb\\nc\\rd\\\\e"


def test_walk_classifies_every_entry_kind(tmp_path):
    src = tmp_path / "src"
    put(src / "keep.txt")
    put(src / "sub" / "deep.txt")
    put(src / "Caches" / "junk.bin")
    put(src / "carved" / "x.txt")
    put(src / ".env", "FAKE")
    put(src / ".ssh" / "id_ed25519", "FAKE")
    os.symlink("keep.txt", src / "link")
    os.mkfifo(src / "pipe")
    homer = nh.Homer(apply=False, run_dir=str(tmp_path / "run"), sqlite_bin="sqlite3")
    seen = {rel: kind for rel, kind, _ in homer.walk(str(src), ("Caches",), frozenset({"carved"}))}
    assert seen == {"keep.txt": "file", "sub": "dir", "sub/deep.txt": "file", "link": "link"}
    assert sorted(r[0] for r in homer.excluded_rows) == [
        "credential-dir",
        "credential-file",
        "item-excluded",
        "special-file",
    ]
    listed = {Path(r[1]).name: r[2] for r in homer.excluded_rows}
    assert listed[".env"] == 4 and listed[".ssh"] == 4 and listed["pipe"] == 0  # name and size, never contents


# --- copy_hash -----------------------------------------------------------------------------------------------------


def test_copy_hash_returns_source_hash_and_preserves_mode_and_mtime(tmp_path):
    src = put(tmp_path / "s.bin", os.urandom(1000), mode=0o4444)  # setuid + read-only
    os.utime(src, ns=(1_700_000_000_000_000_000, 1_700_000_001_000_000_000))
    st = os.lstat(src)
    dst = tmp_path / "d.bin"
    sha = nh.copy_hash(str(src), str(dst), st)
    assert sha == hashlib.sha256(src.read_bytes()).hexdigest() and dst.read_bytes() == src.read_bytes()
    assert stat.S_IMODE(dst.stat().st_mode) == 0o644  # owner write added, setuid dropped
    assert dst.stat().st_mtime_ns == 1_700_000_001_000_000_000


def test_copy_hash_never_overwrites_follows_or_blocks(tmp_path):
    src = put(tmp_path / "s.txt", "data")
    st = os.lstat(src)
    existing = put(tmp_path / "exists.txt", "keep me")
    with pytest.raises(FileExistsError):
        nh.copy_hash(str(src), str(existing), st)
    assert existing.read_text() == "keep me"
    link = tmp_path / "link"
    os.symlink(src, link)
    with pytest.raises(OSError):  # a path swapped for a symlink after the walk is refused, not followed
        nh.copy_hash(str(link), str(tmp_path / "d1"), st)
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    with pytest.raises(OSError, match="no longer a regular file"):  # and a FIFO is refused instead of blocking
        nh.copy_hash(str(fifo), str(tmp_path / "d2"), st)


# --- a full apply --------------------------------------------------------------------------------------------------


def build_tree(home: Path) -> Path:
    src = home / "Docs"
    put(src / "a.txt", "alpha\n" * 100)
    put(src / "sub dir" / "ünï café.md", "non-ascii name")
    put(src / "sub dir" / "empty.txt", b"")
    put(src / "Caches" / "junk.bin")
    put(src / ".env", "FAKE_SECRET_VALUE")
    os.symlink("../a.txt", src / "sub dir" / "link")
    os.mkfifo(src / "pipe")
    return src


def test_apply_end_to_end(env):
    build_tree(env.home)
    homer, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs", "Caches")])
    run = env.ext / "run"
    assert code == 0 and text.endswith("RESULT: PASS\n") and (run / "RESULT.txt").read_text() == text
    assert sorted(manifest(run)) == ["home/Docs/a.txt", "home/Docs/sub dir/empty.txt", "home/Docs/sub dir/ünï café.md"]
    assert_manifest_reverifies(run)
    assert (run / "home/Docs/sub dir/link").is_symlink() and os.readlink(run / "home/Docs/sub dir/link") == "../a.txt"
    assert not (run / "home/Docs/.env").exists() and not (run / "home/Docs/Caches").exists()
    assert "FAKE_SECRET_VALUE" not in "".join(p.read_text(errors="replace") for p in run.rglob("*") if p.is_file())
    excluded = (run / "EXCLUDED.tsv").read_text().splitlines()
    assert excluded[0] == "kind\tsource_path\tbytes\treason"
    assert f"credential-file\t{env.home}/Docs/.env\t17\t.env" in excluded
    assert any(r.startswith("special-file\t") and r.endswith("/pipe\t0\tsocket/fifo/device") for r in excluded)
    tsv = (run / "MANIFEST.tsv").read_text().splitlines()
    assert tsv[0] == "sha256\tbytes\trel_path\tkind" and any(r.endswith("\tsymlink;target=../a.txt") for r in tsv)
    assert "item[docs]=files=3 " in text and homer.tot["verified"] == 3


def test_dry_run_plans_but_writes_nothing(env):
    build_tree(env.home)
    homer, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs", "Caches")], apply=False)
    assert code == 0 and "RESULT: DRY-RUN (nothing written)" in text
    assert not (env.ext / "run").exists() and list(env.ext.iterdir()) == []
    assert homer.tot["files"] == 3 and homer.tot["excluded_credential"] == 1


def test_dry_run_with_a_missing_source_is_a_failed_plan(env):
    _, text, code = go(env, [("gone", "$HOME/Nope", "home/Nope")], apply=False)
    assert code == 1 and "problem=ERROR_SOURCE_MISSING" in text and "DRY-RUN-PROBLEMS" in text


def test_apply_refuses_an_existing_run_dir_and_leaves_it_untouched(env):
    build_tree(env.home)
    go(env, [("docs", "$HOME/Docs", "home/Docs", "Caches")])
    run = env.ext / "run"
    before = {p: p.read_bytes() for p in run.rglob("*") if p.is_file()}
    with pytest.raises(nh.RunDirExists):
        go(env, [("docs", "$HOME/Docs", "home/Docs", "Caches")])
    assert {p: p.read_bytes() for p in run.rglob("*") if p.is_file()} == before


def test_a_source_that_changes_mid_copy_is_drift_never_verified(env, monkeypatch):
    src = env.home / "Docs"
    put(src / "a-stable.txt", "stable")
    moving = put(src / "z-moving.txt", "before")
    real = nh.copy_hash

    def copy_then_touch(s, d, st, check=None):
        sha = real(s, d, st, check)
        if s.endswith("z-moving.txt"):
            moving.write_text("changed after it was read")
        return sha

    monkeypatch.setattr(nh, "copy_hash", copy_then_touch)
    homer, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs")])
    assert code == 1 and homer.tot["drift"] == 1 and "problem=DRIFT" in text and "z-moving.txt" in text
    assert sorted(manifest(env.ext / "run")) == ["home/Docs/a-stable.txt"]
    assert text.endswith("RESULT: FAIL\n")


def test_a_vanished_source_is_drift(env, monkeypatch):
    src = env.home / "Docs"
    victim = put(src / "a.txt", "here")
    real = nh.copy_hash

    def copy_then_delete(s, d, st, check=None):
        sha = real(s, d, st, check)
        victim.unlink()
        return sha

    monkeypatch.setattr(nh, "copy_hash", copy_then_delete)
    homer, _, code = go(env, [("docs", "$HOME/Docs", "home/Docs")])
    assert code == 1 and homer.tot["drift"] == 1


def test_a_corrupted_destination_is_a_mismatch_never_verified(env, monkeypatch):
    src = env.home / "Docs"
    put(src / "a.txt", "alpha" * 50)
    put(src / "b.txt", "bravo" * 50)
    real = nh.copy_hash

    def copy_then_corrupt(s, d, st, check=None):
        sha = real(s, d, st, check)
        if s.endswith("b.txt"):
            with open(d, "r+b") as fh:
                fh.seek(7)
                fh.write(b"!")  # one flipped byte, same size and mtime
        return sha

    monkeypatch.setattr(nh, "copy_hash", copy_then_corrupt)
    homer, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs")])
    assert code == 1 and homer.tot["mismatch"] == 1 and "problem=MISMATCH" in text
    assert sorted(manifest(env.ext / "run")) == ["home/Docs/a.txt"]


def test_nothing_verified_is_not_a_pass(env):
    put(env.home / "Docs" / ".env", "FAKE")  # the only file is a credential: nothing gets copied
    _, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs")])
    assert code == 1 and "problem=NOTHING_VERIFIED" in text and text.endswith("RESULT: FAIL\n")


def test_unrepresentable_names_are_reported_not_copied(env):
    src = env.home / "Docs"
    put(src / "fine.txt")
    put(src / "new\nline.txt")
    put(src / "tab\there.txt")
    put(src / "back\\slash.txt")
    homer, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs")])
    assert code == 1 and homer.tot["errors"] == 3 and text.count("problem=ERROR_PATH") == 3
    assert sorted(manifest(env.ext / "run")) == ["home/Docs/fine.txt"]
    assert_manifest_reverifies(env.ext / "run")


def test_single_file_item_copies_only_that_file(env):
    put(env.home / "Data" / "one.txt", "one")
    put(env.home / "Data" / "two.txt", "two")
    _, _, code = go(env, [("one", "$HOME/Data/one.txt", "home/Data/one.txt")])
    assert code == 0 and sorted(manifest(env.ext / "run")) == ["home/Data/one.txt"]
    assert not (env.ext / "run/home/Data/two.txt").exists()


def test_loose_and_child_items_compose(env):
    put(env.home / "Proj" / "loose.txt", "loose")
    put(env.home / "Proj" / "archive" / "old.txt", "old")
    put(env.home / "Proj" / "build" / "out.o", "derived")
    _, text, code = go(
        env,
        [("loose", "$HOME/Proj", "home/Proj", "=archive;build"), ("child", "$HOME/Proj/archive", "home/Proj/archive")],
    )
    assert code == 0 and sorted(manifest(env.ext / "run")) == ["home/Proj/archive/old.txt", "home/Proj/loose.txt"]
    assert "build" in text  # the glob-excluded dir is listed; the carved-out one is not an exclusion
    assert text.count("excluded[item-excluded]") == 1


def test_a_symlink_recreated_by_one_item_cannot_redirect_a_later_item(env):
    outside = env.tmp / "outside"
    outside.mkdir()
    (env.home / "A").mkdir()
    os.symlink(outside, env.home / "A" / "x")  # absolute link, recreated verbatim in the run directory
    put(env.home / "B" / "f.txt", "must not escape")
    _, text, code = go(env, [("a", "$HOME/A", "home/a"), ("b", "$HOME/B", "home/a/x/y")])
    assert code == 1 and "DestEscapeError" in text
    assert list(outside.iterdir()) == []


# --- configuration guards ------------------------------------------------------------------------------------------


def test_check_items_refuses_overlap_unless_carved_out(env, tmp_path):
    (env.home / "P" / "sub").mkdir(parents=True)
    items_tsv = tmp_path / "i.tsv"
    items_tsv.write_text("p\t$HOME/P\tdp\nc\t$HOME/P/sub\tdc\n")
    with pytest.raises(nh.HomingError, match="overlapping items"):
        nh.check_items(nh.parse_items(str(items_tsv), str(env.home)), str(env.ext / "run"))
    items_tsv.write_text("p\t$HOME/P\tdp\t=sub\nc\t$HOME/P/sub\tdc\n")
    nh.check_items(nh.parse_items(str(items_tsv), str(env.home)), str(env.ext / "run"))
    items_tsv.write_text("p\t$HOME/P\tdp\nc\t$HOME/P\tdc\n")
    with pytest.raises(nh.HomingError, match="same source"):
        nh.check_items(nh.parse_items(str(items_tsv), str(env.home)), str(env.ext / "run"))


def test_check_items_refuses_copying_into_itself(env, tmp_path):
    (env.home / "P").mkdir()
    items_tsv = tmp_path / "i.tsv"
    items_tsv.write_text("p\t$HOME/P\tdp\n")
    items = nh.parse_items(str(items_tsv), str(env.home))
    with pytest.raises(nh.HomingError, match="inside the source"):
        nh.check_items(items, str(env.home / "P" / "run"))
    with pytest.raises(nh.HomingError, match="inside the run directory"):
        nh.check_items(items, str(env.home))


def test_check_items_refuses_a_renamed_single_file(env, tmp_path):
    put(env.home / "d" / "one.txt")
    items_tsv = tmp_path / "i.tsv"
    items_tsv.write_text("p\t$HOME/d/one.txt\thome/d/other.txt\n")
    with pytest.raises(nh.HomingError, match="must end in 'one.txt'"):
        nh.check_items(nh.parse_items(str(items_tsv), str(env.home)), str(env.ext / "run"))


def test_extra_credential_globs_are_additive(env, tmp_path):
    put(env.home / "Docs" / "wallet.dat", "FAKE")
    put(env.home / "Docs" / "ok.txt")
    _, _, code = go(
        env,
        [("docs", "$HOME/Docs", "home/Docs")],
        cred_file_globs=nh.CRED_FILE_GLOBS + ["wallet.dat"],
    )
    assert code == 0 and sorted(manifest(env.ext / "run")) == ["home/Docs/ok.txt"]
    assert nh.split_globs("a;;b;") == ["a", "b"]


def test_deadline_in_the_past_stops_the_run_with_a_fail_result(env):
    put(env.home / "Docs" / "a.txt")
    items_tsv = env.tmp / "i.tsv"
    items_tsv.write_text("docs\t$HOME/Docs\thome/Docs\n")
    homer = nh.Homer(apply=True, run_dir=str(env.ext / "run"), sqlite_bin="sqlite3", deadline_sec=5)
    homer.deadline = time.monotonic() - 1
    text, code = homer.run(nh.parse_items(str(items_tsv), str(env.home)))
    assert code == 1 and "problem=DEADLINE" in text and (env.ext / "run" / "RESULT.txt").read_text() == text
    assert manifest(env.ext / "run") == {}


# --- SQLite --------------------------------------------------------------------------------------------------------


@needs_sqlite
def test_wal_database_held_open_is_snapshotted_with_its_wal_content(env):
    db = env.home / "Docs" / "live.db"
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA wal_autocheckpoint=0")
        con.execute("CREATE TABLE t(x INTEGER)")
        con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(300)])
        con.commit()
        assert os.path.getsize(f"{db}-wal") > 0  # the rows live only in the -wal while the connection is open
        homer, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs")])
    finally:
        con.close()
    dest = env.ext / "run/home/Docs/live.db"
    assert code == 0 and homer.tot["snapshots"] == 1 and "snapshot-ok" in text
    snap = sqlite3.connect(f"file:{dest}?mode=ro", uri=True)
    try:
        assert snap.execute("select count(*) from t").fetchone() == (300,)
        assert snap.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    finally:
        snap.close()
    assert not (env.ext / "run/home/Docs/live.db-wal").exists() and not (env.ext / "run/home/Docs/live.db-shm").exists()
    assert manifest(env.ext / "run") == {"home/Docs/live.db": hashlib.sha256(dest.read_bytes()).hexdigest()}


@needs_sqlite
def test_database_is_detected_by_header_not_by_name(env):
    plain = env.home / "Docs" / "store.dat"
    plain.parent.mkdir(parents=True)
    con = sqlite3.connect(plain)
    con.execute("CREATE TABLE t(x TEXT)")
    con.executemany("INSERT INTO t VALUES (?)", [("r%d" % i,) for i in range(200)])
    con.commit()
    con.close()
    put(env.home / "Docs" / "not-a-db.dat", b"SQLite format 3\x00" + b"\x00" * 100)  # right magic but under 512 bytes
    homer, _, code = go(env, [("docs", "$HOME/Docs", "home/Docs")])
    assert code == 0 and homer.tot["snapshots"] == 1 and homer.tot["files"] == 1


@needs_sqlite
def test_quiescent_wal_database_in_a_read_only_directory_uses_the_immutable_read(env):
    d = env.home / "Docs"
    d.mkdir()
    con = sqlite3.connect(d / "q.db")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("CREATE TABLE t(x INTEGER)")
    con.executemany("INSERT INTO t VALUES (?)", [(i,) for i in range(50)])
    con.commit()
    con.close()  # last connection closed: the -wal and -shm are gone and the directory is now read-only
    d.chmod(0o555)
    try:
        homer, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs")])
    finally:
        d.chmod(0o755)
    assert code == 0 and homer.tot["snapshots"] == 1 and "snapshot-ok" in text
    snap = sqlite3.connect(f"file:{env.ext / 'run/home/Docs/q.db'}?mode=ro", uri=True)
    assert snap.execute("select count(*) from t").fetchone() == (50,)
    snap.close()


def test_failed_snapshot_falls_back_to_a_flagged_hash_verified_trio(env):
    stub = put(env.tmp / "fail-sqlite.sh", "#!/bin/sh\necho 'boom' >&2\nexit 1\n", mode=0o755)
    d = env.home / "Docs"
    put(d / "x.db", nh.SQLITE_MAGIC + b"\x00" * 1000)
    put(d / "x.db-wal", b"wal bytes")
    put(d / "x.db-shm", b"shm bytes")
    homer, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs")], sqlite_bin=str(stub))
    assert code == 0 and homer.tot["trio_fallbacks"] == 1 and "SNAPSHOT-FAILED: boom" in text
    assert sorted(manifest(env.ext / "run")) == ["home/Docs/x.db", "home/Docs/x.db-shm", "home/Docs/x.db-wal"]
    assert_manifest_reverifies(env.ext / "run")


def test_trio_fallback_of_a_single_file_item_still_takes_its_sidecars(env):
    stub = put(env.tmp / "fail-sqlite.sh", "#!/bin/sh\nexit 1\n", mode=0o755)
    put(env.home / "Docs" / "x.db", nh.SQLITE_MAGIC + b"\x00" * 1000)
    put(env.home / "Docs" / "x.db-wal", b"wal bytes")
    _, _, code = go(env, [("one", "$HOME/Docs/x.db", "home/Docs/x.db")], sqlite_bin=str(stub))
    assert code == 0 and sorted(manifest(env.ext / "run")) == ["home/Docs/x.db", "home/Docs/x.db-wal"]


def test_a_hung_sqlite_is_cut_off_by_the_run_deadline(env):
    stub = put(env.tmp / "hang-sqlite.sh", "#!/bin/sh\nexec sleep 30\n", mode=0o755)
    put(env.home / "Docs" / "x.db", nh.SQLITE_MAGIC + b"\x00" * 1000)
    started = time.monotonic()
    _, text, code = go(env, [("docs", "$HOME/Docs", "home/Docs")], sqlite_bin=str(stub), deadline_sec=1)
    assert code == 1 and "problem=DEADLINE" in text and time.monotonic() - started < 15


# --- CLI -----------------------------------------------------------------------------------------------------------


def test_main_exit_codes(env, capsys):
    build_tree(env.home)
    items_tsv = env.tmp / "items.tsv"
    items_tsv.write_text("docs\t$HOME/Docs\thome/Docs\tCaches\n")
    base = [str(env.ext / "run"), str(items_tsv), "--home", str(env.home)]
    if SQLITE:
        base += ["--sqlite", SQLITE]
    assert nh.main(["dry", *base]) == 0 and "RESULT: DRY-RUN" in capsys.readouterr().out
    assert not (env.ext / "run").exists()
    assert nh.main(["apply", *base]) == 0 and "RESULT: PASS" in capsys.readouterr().out
    assert nh.main(["apply", *base]) == nh.EXIT_RUN_DIR_EXISTS and "already exists" in capsys.readouterr().err
    items_tsv.write_text("docs\t$HOME/Docs\t../escape\n")
    assert nh.main(["dry", *base]) == nh.EXIT_USAGE and "dest_rel must be a relative path" in capsys.readouterr().err
    items_tsv.write_text("docs\t$HOME/Docs\thome/Docs\n")
    code = nh.main(
        ["dry", str(env.ext / "run2"), str(items_tsv), "--home", str(env.home), "--sqlite", "/nonexistent/sqlite3"]
    )
    assert code == nh.EXIT_NO_SQLITE
