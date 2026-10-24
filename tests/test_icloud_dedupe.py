"""tests/test_icloud_dedupe.py — safety regression suite for scripts/icloud-dedupe.py.

Ports the 2026-10-23 adversarial validation run (T1-T11, T3 aimed at /usr/bin/ditto) into asserts
on the SAFE outcome: refused / not removed / xattrs kept / exit codes. Adds coverage for the
progress emitter, the --status verb, --census and UNION_COPY.

Hermetic: every tree lives under tmp_path (synthetic CloudDocs + archive); brctl and the Finder
flags are stubbed. Nothing touches real iCloud, a phone, or /Volumes/Archive4T.
"""

from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="engine relies on darwin ditto/xattr/brctl")

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "icloud-dedupe.py"

nonroot = pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="chmod 0 does not block root")


def load_module():
    spec = importlib.util.spec_from_file_location("icloud_dedupe_under_test", SCRIPT)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def w(p, data: bytes):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)


def tree_snapshot(root):
    out = {}
    for dp, dns, fns in os.walk(root):
        for n in dns + fns:
            q = os.path.join(dp, n)
            st = os.lstat(q)
            out[q] = (st.st_size, int(st.st_mtime))
    return out


@pytest.fixture
def env(tmp_path, monkeypatch):
    m = load_module()
    cd = tmp_path / "cd"
    (cd / "Desktop").mkdir(parents=True)
    (cd / "Documents").mkdir()
    m.configure(state_dir=str(tmp_path / "state"), archive_root=str(tmp_path / "arch"))
    m.PARENTS = (("Desktop", str(cd / "Desktop")), ("Documents", str(cd / "Documents")))
    m.ARCH_VOL = "/"  # the tmp archive is on a mounted volume
    monkeypatch.setattr(m, "finder_flag", lambda k: 0)
    monkeypatch.setattr(m, "wait_settled", lambda limit=0, what="": True)
    monkeypatch.setattr(m, "PROGRESS_INTERVAL", 3600.0)
    docs = cd / "Documents"

    def run_main(*args):
        """Run main(); return (exit code or None, stdout, stderr) via the real argv path."""
        import contextlib
        import io

        out, err = io.StringIO(), io.StringIO()
        code = 0
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                m.main(list(args))
        except SystemExit as e:
            code = e.code
        return code, out.getvalue(), err.getvalue()

    def mkgroup():
        w(docs / "G 2" / "a", b"A")
        w(docs / "G 2" / "s" / "b", b"BB")
        w(docs / "G 2" / "only", b"O")
        w(docs / "G 3" / "a", b"A")
        (docs / "G 4").mkdir()

    def variant(name):
        return m.scan_variant(str(docs), name, True, os.lstat(docs / name))

    def archive(name, base="P"):
        v = variant(name)
        return m.archive_variant(v, "%s/%s/%s/" % (m.ARCH, base, name), {}, m.hash_manifest_path(base, "archive"))

    def names():
        return sorted(os.listdir(docs))

    return SimpleNamespace(m=m, tmp=tmp_path, docs=docs, run_main=run_main, mkgroup=mkgroup, variant=variant,
                           archive=archive, names=names)


# ------------------------------------------------------------------ T1: unreadable directories
@nonroot
def test_t1_unreadable_subdir_refuses_removal(env):
    d = env.docs
    w(d / "P 2" / "a.txt", b"a")
    w(d / "P 2" / "sub" / "b.txt", b"b")
    os.chmod(d / "P 2" / "sub", 0)
    try:
        with pytest.raises((RuntimeError, OSError)):
            env.archive("P 2")
    finally:
        os.chmod(d / "P 2" / "sub", 0o755)
    assert (d / "P 2" / "sub" / "b.txt").read_bytes() == b"b"
    assert (d / "P 2" / "a.txt").exists()


@nonroot
def test_t1b_copy_tree_verified_raises_on_unreadable_dir(env):
    d = env.docs
    w(d / "P 2" / "a.txt", b"a")
    (d / "P 2" / "sub").mkdir()
    os.chmod(d / "P 2" / "sub", 0)
    try:
        with pytest.raises((RuntimeError, OSError)):
            env.m.copy_tree_verified(str(d / "P 2"), str(env.tmp / "arch" / "x"))
    finally:
        os.chmod(d / "P 2" / "sub", 0o755)


# ------------------------------------------------------------------ T2: unreadable file
@nonroot
def test_t2_unreadable_file_refuses_removal(env):
    d = env.docs
    w(d / "P 2" / "a.txt", b"a")
    os.chmod(d / "P 2" / "a.txt", 0)
    try:
        with pytest.raises((RuntimeError, OSError)):
            env.archive("P 2")
    finally:
        os.chmod(d / "P 2" / "a.txt", 0o644)
    assert (d / "P 2" / "a.txt").read_bytes() == b"a"


# ------------------------------------------------------------------ T3: corrupt destination (ditto)
def _real_run():
    return subprocess.run


def test_t3_corrupt_ditto_destination_refuses_removal(env, monkeypatch):
    d = env.docs
    w(d / "P 2" / "a.txt", b"aaaa")
    real = _real_run()

    def bad(argv, *a, **k):
        r = real(argv, *a, **k)
        if argv and argv[0] == "/usr/bin/ditto":
            Path(argv[2]).write_bytes(b"XXXX")
        return r

    monkeypatch.setattr(env.m.subprocess, "run", bad)
    with pytest.raises(RuntimeError, match="post-copy hash mismatch"):
        env.archive("P 2")
    assert (d / "P 2" / "a.txt").read_bytes() == b"aaaa"


def test_t3b_ditto_dropping_xattrs_refuses_removal(env, monkeypatch):
    d = env.docs
    w(d / "P 2" / "a.txt", b"data")
    subprocess.run(["xattr", "-w", "user.note", "hello", str(d / "P 2" / "a.txt")], check=True)
    real = _real_run()

    def lossy(argv, *a, **k):
        if argv and argv[0] == "/usr/bin/ditto":
            shutil.copyfile(argv[1], argv[2])  # same bytes, xattrs dropped
            return subprocess.CompletedProcess(argv, 0)
        return real(argv, *a, **k)

    monkeypatch.setattr(env.m.subprocess, "run", lossy)
    with pytest.raises(RuntimeError, match="xattr mismatch"):
        env.archive("P 2")
    assert (d / "P 2" / "a.txt").read_bytes() == b"data"


# ------------------------------------------------------------------ T4: same-size mutation after copy
def test_t4_same_size_mutation_after_copy_leaves_source(env, monkeypatch):
    d = env.docs
    w(d / "P 2" / "a.txt", b"orig")
    real = env.m.copy_tree_verified

    def mutate_after(src, dst, *a, **k):
        r = real(src, dst, *a, **k)
        Path(src, "a.txt").write_bytes(b"NEW!")
        return r

    monkeypatch.setattr(env.m, "copy_tree_verified", mutate_after)
    with pytest.raises(RuntimeError, match="source changed after archive"):
        env.archive("P 2")
    assert (d / "P 2" / "a.txt").read_bytes() == b"NEW!"  # not unlinked
    assert (env.tmp / "arch" / "P" / "P 2" / "a.txt").read_bytes() == b"orig"


# ------------------------------------------------------------------ T5: xattrs / resource fork preserved
def test_t5_xattrs_survive_archive(env):
    d = env.docs
    f = d / "P 2" / "a.txt"
    w(f, b"data")
    subprocess.run(["xattr", "-w", "com.apple.ResourceFork", "RSRCDATA", str(f)], check=True)
    subprocess.run(["xattr", "-w", "user.note", "hello", str(f)], check=True)
    before = env.m.xattr_sig(str(f))
    assert "user.note" in before
    env.archive("P 2")
    dest = env.tmp / "arch" / "P" / "P 2" / "a.txt"
    assert not (d / "P 2").exists()
    after = env.m.xattr_sig(str(dest))
    assert after == before
    assert dest.read_bytes() == b"data"


# ------------------------------------------------------------------ T6: symlinks
def test_t6_symlinks_archived_as_links(env):
    d = env.docs
    w(d / "P 2" / "real" / "f", b"f")
    os.symlink("real", d / "P 2" / "dl")
    os.symlink("nowhere", d / "P 2" / "bl")
    env.archive("P 2")
    a = env.tmp / "arch" / "P" / "P 2"
    assert not (d / "P 2").exists()
    assert os.path.islink(a / "dl") and os.readlink(a / "dl") == "real"
    assert os.path.islink(a / "bl") and os.readlink(a / "bl") == "nowhere"
    assert (a / "real" / "f").read_bytes() == b"f"


# ------------------------------------------------------------------ T7: apply + rename + verify + tamper
def test_t7_apply_verify_and_tamper_detection(env):
    d = env.docs
    env.mkgroup()
    assert env.run_main("--replan")[0] == 0
    code, out, err = env.run_main("--apply", "--group", "G")
    assert code == 0, (out, err)
    assert env.names() == ["G"]  # siblings archived, keeper renamed to the plain name
    assert (d / "G" / "s" / "b").read_bytes() == b"BB"

    code, out, _ = env.run_main("--verify")
    assert code == 0 and "LOST=0" in out

    (d / "G" / "a").write_bytes(b"Z")  # same-size tamper of a hashed keeper file
    code, out, _ = env.run_main("--verify")
    assert code == 1 and "LOST: " in out and "keeper hash mismatch" in out
    (d / "G" / "a").write_bytes(b"A")

    arch_a = Path(env.m.ARCH) / "G" / "G 3" / "a"
    arch_a.write_bytes(b"Q")  # tamper the archived copy
    code, out, _ = env.run_main("--verify")
    assert code == 1 and "archive hash mismatch" in out
    arch_a.write_bytes(b"A")

    (d / "G" / "only").write_bytes(b"X")  # never-hashed keeper file: resolved by size only (documented)
    code, out, _ = env.run_main("--verify")
    assert code == 0
    assert "resolved_by_size_only=" in out


# ------------------------------------------------------------------ T8: plan drift gate (exit 5)
def test_t8_plan_drift_exit_5_and_nothing_moves(env):
    env.mkgroup()
    env.run_main("--replan")
    w(env.docs / "G 3" / "new", b"N")
    before = env.names()
    code, out, err = env.run_main("--apply", "--group", "G")
    assert code == 5
    assert "ABORT (exit 5)" in err
    assert env.names() == before
    assert not (Path(env.m.ARCH) / "G").exists()


def test_t8b_same_size_content_drift_aborts_before_any_move(env):
    env.mkgroup()
    env.run_main("--replan")
    (env.docs / "G 3" / "a").write_bytes(b"Z")  # size-neutral: plan sig equal, sha256 must catch it
    before = env.names()
    code, out, err = env.run_main("--apply", "--group", "G")
    assert code not in (0, None) and "hash mismatch" in str(code)
    assert env.names() == before
    assert (env.docs / "G 3" / "a").read_bytes() == b"Z"
    assert not (Path(env.m.ARCH) / "G" / "G 3").exists()


# ------------------------------------------------------------------ T9: Finder FX flags
@pytest.mark.parametrize("val", [None, 1])
def test_t9_fx_flag_refusal(env, monkeypatch, val):
    env.mkgroup()
    env.run_main("--replan")
    monkeypatch.setattr(env.m, "finder_flag", lambda k: val)
    before = env.names()
    code, out, err = env.run_main("--apply", "--group", "G")
    assert code not in (0, None) and "REFUSE" in str(code)
    assert env.names() == before


def test_t9_fx_unknown_proceeds_only_with_override(env, monkeypatch):
    env.mkgroup()
    env.run_main("--replan")
    monkeypatch.setattr(env.m, "finder_flag", lambda k: None)
    code, out, err = env.run_main("--apply", "--group", "G", "--allow-fx-unknown")
    assert code == 0 and "WARN" in out
    assert env.names() == ["G"]


def test_t9_fx_one_refuses_even_with_override(env, monkeypatch):
    env.mkgroup()
    env.run_main("--replan")
    monkeypatch.setattr(env.m, "finder_flag", lambda k: 1)
    before = env.names()
    code, out, err = env.run_main("--apply", "--group", "G", "--allow-fx-unknown")
    assert code not in (0, None) and "reads 1" in str(code)
    assert env.names() == before


# ------------------------------------------------------------------ T10: brctl settle waits (exit 4)
@pytest.mark.parametrize(
    "fail_at,expected",
    [
        (1, ["G 2", "G 3", "G 4"]),  # before any mutation: nothing changed
        (2, ["G 2"]),  # after archiving siblings: keeper rename NOT done
        (3, ["G"]),  # after the rename: state is complete, exit 4 still signals unsettled
    ],
)
def test_t10_unsettled_icloud_exits_4(env, monkeypatch, fail_at, expected):
    env.mkgroup()
    env.run_main("--replan")
    n = [0]

    def ws(limit=0, what=""):
        n[0] += 1
        return n[0] != fail_at

    monkeypatch.setattr(env.m, "wait_settled", ws)
    code, out, err = env.run_main("--apply", "--group", "G")
    assert code == 4
    assert "ABORT (exit 4)" in err
    assert env.names() == expected


# ------------------------------------------------------------------ T11: brctl output parsing
def test_t11_brctl_settled_parsing(env):
    m = env.m
    abbr = "<c{1}m.a{3}e.C{7}s[1] foreground {client:idle server:full-sync|fetched-recents|caught-up}>"
    assert m.brctl_settled(abbr)[0] is True
    assert m.brctl_settled(abbr + "\n  uploading: 3")[0] is False
    assert m.brctl_settled(abbr + "\n  uploading: 0")[0] is True
    assert m.brctl_settled("<com.apple.CloudDocs[1] {server:not caught up}>")[0] is False
    assert m.brctl_settled("<other[1] caught-up>")[0] is False  # fails closed: no CloudDocs block
    assert m.brctl_settled("")[0] is False


# ------------------------------------------------------------------ UNION_COPY never removes originals
def test_union_copy_never_removes_icloud_originals(env):
    d = env.docs
    w(d / "99_System_Backups" / "x.bin", b"one")
    w(d / "99_System_Backups 2" / "x.bin", b"two!")
    w(d / "99_System_Backups 2" / "y.bin", b"yy")
    before = tree_snapshot(d)
    assert env.run_main("--replan")[0] == 0
    code, out, err = env.run_main("--apply", "--group", "99_System_Backups")
    assert code == 0, (out, err)
    assert tree_snapshot(d) == before  # iCloud side byte-for-byte untouched
    union = Path(env.m.ARCH) / "99_System_Backups"
    assert (union / "union" / "x.bin").read_bytes() == b"one"
    assert (union / "union" / "x.v02.bin").read_bytes() == b"two!"
    assert (union / "union" / "y.bin").read_bytes() == b"yy"
    assert (union / "union.sha256").exists()


def test_divergent_group_is_not_applyable(env):
    d = env.docs
    w(d / "D" / "a", b"A")
    w(d / "D 2" / "b", b"B")  # content the keeper lacks -> DIVERGENT -> NEEDS_UNION
    env.run_main("--replan")
    before = tree_snapshot(d)
    code, out, err = env.run_main("--apply", "--group", "D")
    assert code not in (0, None) and "NEEDS_UNION" in str(code)
    assert tree_snapshot(d) == before


# ------------------------------------------------------------------ apply without a reviewed plan
def test_apply_without_plan_json_refuses(env):
    env.mkgroup()
    before = env.names()
    code, out, err = env.run_main("--apply", "--group", "G")
    assert code not in (0, None) and "REFUSE" in str(code)
    assert env.names() == before


# ------------------------------------------------------------------ state dir + census
def test_state_dir_is_created_0700_and_census_is_written(env):
    env.mkgroup()
    code, out, err = env.run_main("--census")
    assert code == 0, err
    st = os.stat(env.m.STATE_DIR)
    assert st.st_mode & 0o777 == 0o700
    census = json.loads(Path(env.m.CENSUS_JSON).read_text())
    names = sorted(v["name"] for v in census["Documents"]["G"]["variants"])
    assert names == ["G 2", "G 3", "G 4"]
    # the dry-run then sees no drift against the census it was just given
    code, out, _ = env.run_main("--dry-run")
    assert code == 0 and "drift entries: 0" in out


def test_default_state_dir_honours_custody_staging_env(monkeypatch, tmp_path):
    m = load_module()
    monkeypatch.setenv("LIMEN_CUSTODY_STAGING_ROOT", str(tmp_path / "stage"))
    assert m.default_state_dir() == str(tmp_path / "stage" / "icloud-dedupe")
    monkeypatch.delenv("LIMEN_CUSTODY_STAGING_ROOT")
    assert m.default_state_dir().endswith("/.limen-private/custody-staging/icloud-dedupe")


def test_unmounted_external_volume_never_resolves_to_root():
    m = load_module()
    assert m.mount_point("/Volumes/NoSuchVolumeXYZ/icloud-dedupe") == "/Volumes/NoSuchVolumeXYZ"


# ------------------------------------------------------------------ progress emitter
def test_progress_note_prints_flushed_line_with_counts_and_relpath(capsys):
    m = load_module()
    with m.Progress("copy X", total_files=4, total_bytes=4096, interval=0) as p:
        p.note("dir/file.bin", files=1, nbytes=1024)
    out = capsys.readouterr().out
    assert "progress [copy X] files 1/4 bytes 1.00 KiB/4.00 KiB" in out
    assert "current: dir/file.bin" in out
    assert out.rstrip().endswith("(done)")


def test_progress_watchdog_emits_during_a_blocking_call(capsys):
    m = load_module()
    with m.Progress("hash", interval=0.05) as p:
        p.current = "huge.iso"
        time.sleep(0.4)  # a single long call with no note(): the watchdog must still speak
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("progress [hash]")]
    assert len(lines) >= 3
    assert all("current: huge.iso" in ln for ln in lines)


def test_progress_is_rate_limited_by_interval(capsys):
    m = load_module()
    with m.Progress("quiet", interval=3600) as p:
        for i in range(50):
            p.note("f%d" % i, files=1)
    lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("progress [quiet]")]
    assert len(lines) == 1  # only the closing line


def test_archive_variant_emits_progress_per_file(env, monkeypatch, capsys):
    monkeypatch.setattr(env.m, "PROGRESS_INTERVAL", 0.0)
    w(env.docs / "P 2" / "one.txt", b"1")
    w(env.docs / "P 2" / "sub" / "two.txt", b"22")
    env.archive("P 2")
    out = capsys.readouterr().out
    assert "progress [copy P 2] files" in out
    assert "one.txt" in out and os.path.join("sub", "two.txt") in out
    assert "progress [rehash P 2]" in out and "progress [unlink P 2]" in out


def test_wait_settled_prints_elapsed_and_last_state(monkeypatch, capsys):
    m = load_module()
    monkeypatch.setattr(m, "PROGRESS_INTERVAL", 0.0)
    monkeypatch.setattr(m, "BRCTL_POLL", 0.01)
    calls = [0]

    def fake(argv, *a, **k):
        calls[0] += 1
        busy, done = "<com.apple.CloudDocs[1] {server:not caught up}>", "<com.apple.CloudDocs[1] caught-up>"
        body = busy if calls[0] < 4 else done
        return SimpleNamespace(stdout=body, stderr="", returncode=0)

    monkeypatch.setattr(m.subprocess, "run", fake)
    assert m.wait_settled(limit=60, what="unit") is True
    out = capsys.readouterr().out
    assert out.count("brctl: waiting to settle, elapsed ") >= 2
    assert "last state: container reports 'not caught up'" in out
    assert "brctl: settled" in out


def test_wait_settled_times_out_false(monkeypatch, capsys):
    m = load_module()
    monkeypatch.setattr(m, "BRCTL_POLL", 0.01)
    monkeypatch.setattr(
        m.subprocess, "run",
        lambda *a, **k: SimpleNamespace(stdout="<com.apple.CloudDocs[1] not caught up>", stderr="", returncode=0)
    )
    assert m.wait_settled(limit=0.05) is False
    assert "NOT settled" in capsys.readouterr().out


# ------------------------------------------------------------------ --status verb
def test_status_reports_pending_applied_union_and_lock_without_mutating(env, capsys):
    d = env.docs
    env.mkgroup()
    w(d / "99_System_Backups" / "x.bin", b"one")
    w(d / "99_System_Backups 2" / "y.bin", b"yy")
    env.run_main("--replan")

    def snap():
        return tree_snapshot(d), tree_snapshot(env.m.STATE_DIR)

    # 1. nothing applied yet
    before = snap()
    code, out, _ = env.run_main("--status")
    assert code == 0
    assert "Documents/G [PLANNED/ARCHIVE] pending" in out
    assert "Documents/99_System_Backups [UNION_COPY/UNION_COPY] pending" in out
    assert "union: 0 files" in out and "manifest absent (incomplete)" in out
    assert "writer lock:  free" in out
    assert snap() == before
    assert not os.path.exists(env.m.ARCH + "/manifests")  # status never creates the archive tree

    # 2. partial union copy is visible
    w(Path(env.m.ARCH) / "99_System_Backups" / "union" / "x.bin", b"one")
    out = env.run_main("--status")[1]
    assert "union: 1 files / 3 B" in out

    # 3. a "before" manifest without an "after" = started, not finished
    Path(env.m.MANIFESTS).mkdir(parents=True)
    w(Path(env.m.MANIFESTS) / "G.before.20261024T000000-p1.json", b"{}")
    assert "Documents/G [PLANNED/ARCHIVE] STARTED, not finished" in env.run_main("--status")[1]

    # 4. applied groups report applied
    w(Path(env.m.MANIFESTS) / "G.after.20261024T000001-p1.json", b"{}")
    assert "Documents/G [PLANNED/ARCHIVE] applied (after-manifests: 1)" in env.run_main("--status")[1]

    # 5. a held lock is reported
    lf = open(env.m.LOCK_PATH, "w")
    try:
        fcntl.flock(lf, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert "writer lock:  HELD by another writer" in env.run_main("--status")[1]
    finally:
        lf.close()
    assert "writer lock:  free" in env.run_main("--status")[1]


def test_status_without_plan_json_is_not_an_error(env):
    code, out, _ = env.run_main("--status")
    assert code == 0 and "plan.json:    unreadable" in out


def test_verbs_are_mutually_exclusive(env):
    code, out, err = env.run_main("--status", "--verify")
    assert code == 2 and "mutually exclusive" in err
