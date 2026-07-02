"""cartridge-connected — the host-is-factory / cartridge-plugged-in predicate.

Pins the one check nothing else in the fleet performs: is chezmoi pointed at the REAL
cartridge (organvm/domus-genoma) or at a scratch/dummy/local source? chezmoi verify/status/
health only validate WHATEVER source is wired, so a disconnected cartridge returns a
meaningless green. This predicate must: normalize hosted remotes to owner/repo, REJECT local /
dummy / file paths, treat a fork (same repo name, different owner) as connected (fractal), be
FAIL-OPEN when chezmoi is absent, and exit non-zero ONLY on a genuine disconnection.

Mirrors test_mcp_auth_verify.py's import pattern.
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _mod(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _cc():
    return _mod("cartridge_connected", "scripts/cartridge-connected.py")


# ---- parser ---------------------------------------------------------------


def test_normalize_remote_https_and_ssh():
    m = _cc()
    assert m.normalize_remote("https://github.com/organvm/domus-genoma.git") == "organvm/domus-genoma"
    assert m.normalize_remote("git@github.com:organvm/domus-genoma.git") == "organvm/domus-genoma"
    assert m.normalize_remote("ssh://git@github.com/organvm/domus-genoma") == "organvm/domus-genoma"
    assert m.normalize_remote("https://github.com/organvm/domus-genoma/") == "organvm/domus-genoma"


def test_normalize_remote_rejects_local_and_dummy():
    m = _cc()
    # The scratch failure mode: a bare local path is never the cartridge.
    assert m.normalize_remote("/Users/4jp/dummy-remote.git") is None
    assert m.normalize_remote("file:///tmp/x.git") is None
    assert m.normalize_remote("./relative.git") is None
    assert m.normalize_remote("~/scratch.git") is None
    assert m.normalize_remote("") is None


# ---- main() behavior ------------------------------------------------------


def _wire(m, monkeypatch, *, chezmoi="/opt/homebrew/bin/chezmoi", source, remote_origin, remotes=None):
    """Stub chezmoi presence + _run() dispatch so main() runs hermetically."""
    monkeypatch.setattr(m.shutil, "which", lambda _n: chezmoi)
    monkeypatch.setattr(sys, "argv", ["cartridge-connected.py"])

    def fake_run(cmd):
        if cmd[:1] == [chezmoi] and cmd[-1] == "source-path":
            return source
        if cmd[:2] == ["git", "-C"] and cmd[-2:] == ["get-url", "origin"]:
            return remote_origin
        if cmd[:2] == ["git", "-C"] and cmd[-1] == "remote":
            return remotes
        if cmd[:2] == ["git", "-C"] and cmd[-2] == "get-url":  # non-origin fallback
            return remote_origin
        return None

    monkeypatch.setattr(m, "_run", fake_run)


def test_main_connected(monkeypatch, tmp_path):
    m = _cc()
    _wire(m, monkeypatch, source=str(tmp_path), remote_origin="https://github.com/organvm/domus-genoma.git")
    assert m.main() == 0


def test_main_disconnected_dummy(monkeypatch, tmp_path):
    m = _cc()
    _wire(m, monkeypatch, source=str(tmp_path), remote_origin="/Users/4jp/dummy-remote.git")
    assert m.main() == 1


def test_main_no_remote_is_disconnection(monkeypatch, tmp_path):
    m = _cc()
    _wire(m, monkeypatch, source=str(tmp_path), remote_origin=None, remotes=None)
    assert m.main() == 1


def test_main_chezmoi_absent_is_failopen(monkeypatch):
    m = _cc()
    monkeypatch.setattr(m.shutil, "which", lambda _n: None)
    monkeypatch.setattr(sys, "argv", ["cartridge-connected.py"])
    assert m.main() == 0  # skip, never break the beat


def test_main_undeterminable_source_is_failopen(monkeypatch):
    m = _cc()
    _wire(m, monkeypatch, source="/nonexistent/does/not/exist", remote_origin=None)
    assert m.main() == 0  # source-path not a dir → skip


def test_main_fork_same_repo_name_is_connected(monkeypatch, tmp_path):
    m = _cc()
    # Default expected is organvm/domus-genoma; a fork under another owner still matches by repo name.
    _wire(m, monkeypatch, source=str(tmp_path), remote_origin="git@github.com:someuser/domus-genoma.git")
    assert m.main() == 0


def test_main_override_repo(monkeypatch, tmp_path):
    m = _cc()
    monkeypatch.setenv("LIMEN_CARTRIDGE_REPO", "someuser/their-cartridge")
    _wire(m, monkeypatch, source=str(tmp_path), remote_origin="https://github.com/someuser/their-cartridge.git")
    assert m.main() == 0
