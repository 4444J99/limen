"""The notify gate is host-wide, not tree-local — and it fails CLOSED.

Regression pin for 2026-08-05, third recurrence. The effector gate (#1838) shipped at
19:20 and four more "LIMEN · morning — ABSENT" pops landed at 19:25/19:30/19:36/19:48,
because the gate lives in a versioned file while ``osascript`` is a machine-global
singleton: 21 of the 23 notifier copies on the host predated the fix. These tests pin the
two properties that address that, one per axis.

  in-tree   ── the gate cannot be defeated by ambient sys.path, and an unavailable
               predicate withholds the notification instead of firing it
  cross-tree ── an ungated copy anywhere on the host is DETECTED, structurally
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ── the in-tree axis: the gate does not depend on the caller's sys.path ──────────────


def test_gate_holds_without_scripts_on_sys_path(tmp_path, monkeypatch):
    """``import _root`` only worked because callers ran sys.path.insert first.

    check-effectors.py is the one _notify caller that does not, so the gate's availability
    rode on a convention. Loading by absolute path removes the dependency entirely: with
    scripts/ scrubbed from sys.path AND ``_root`` evicted from the module cache, a synthetic
    root must still be refused.
    """
    mod = _load("_notify_syspath", SCRIPTS / "_notify.py")
    monkeypatch.setattr(sys, "path", [p for p in sys.path if Path(p).resolve() != SCRIPTS])
    monkeypatch.delitem(sys.modules, "_root", raising=False)
    monkeypatch.setattr(mod, "_ROOT_MODULE", None)

    assert mod._root_may_speak(tmp_path) is False


def test_unavailable_predicate_withholds_rather_than_fires(tmp_path, capsys):
    """FAIL CLOSED — the reversal of this function's first shipped form.

    It used to ``return True`` when the predicate was unavailable. A withheld notification
    is recoverable and shows up on stderr; a false one is already on his phone. The stderr
    line is asserted too: silence must never be silent about itself.
    """
    mod = _load("_notify_closed", SCRIPTS / "_notify.py")
    mod._ROOT_MODULE = None
    mod._ROOT_MODULE_PATH = tmp_path / "definitely-not-here.py"

    assert mod._root_may_speak(tmp_path) is False
    assert "withholding notification" in capsys.readouterr().err


# ── the cross-tree axis: an ungated copy anywhere is detected ────────────────────────


@pytest.fixture()
def check_gate():
    return _load("check_notify_gate", SCRIPTS / "check-notify-gate.py")


def _write_notifier(root: Path, body: str) -> Path:
    path = root / "scripts" / "_notify.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


GATED = """
    def _root_may_speak(root):
        return True

    def notify_once(root, key, message):
        if _root_may_speak(root):
            subprocess.run(["osascript"])
"""

UNGATED = """
    def notify_once(root, key, message):
        subprocess.run(["osascript"])
"""

# The exact false positive a substring scan would produce: the identifier appears, but only
# in prose. sensors.yaml:478 records 3 such hits when the plan-mode probe was prototyped.
MENTIONS_ONLY = '''
    def notify_once(root, key, message):
        """Once gated on _root_may_speak; that call was dropped in a bad merge."""
        subprocess.run(["osascript"])
'''

# Defined but never wired into the effector — the shape a half-finished revert leaves.
DEFINED_NOT_CALLED = """
    def _root_may_speak(root):
        return True

    def notify_once(root, key, message):
        subprocess.run(["osascript"])
"""


@pytest.mark.parametrize(
    ("body", "gated"),
    [(GATED, True), (UNGATED, False), (MENTIONS_ONLY, False), (DEFINED_NOT_CALLED, False)],
)
def test_gate_state_is_structural_not_substring(tmp_path, check_gate, body, gated):
    path = _write_notifier(tmp_path, body)
    assert check_gate.gate_state(path)[0] is gated


def test_unparseable_copy_counts_as_ungated(tmp_path, check_gate):
    """Fail closed on the roster too — a file we cannot read is not a file we can clear."""
    path = _write_notifier(tmp_path, "def notify_once(:::")
    assert check_gate.gate_state(path)[0] is False


def test_survey_names_the_ungated_root(tmp_path, check_gate, monkeypatch):
    live, stale = tmp_path / "live", tmp_path / "stale"
    _write_notifier(live, GATED)
    _write_notifier(stale, UNGATED)
    monkeypatch.setattr(check_gate, "enumerate_roots", lambda _live: [live, stale])

    rows = {r["root"]: r["gated"] for r in check_gate.survey(live)}
    assert rows == {str(live): True, str(stale): False}


def test_live_root_passes_its_own_predicate():
    """The shipped notifier gates its own effector — the property every copy is measured against."""
    mod = _load("check_notify_gate_live", SCRIPTS / "check-notify-gate.py")
    gated, reason = mod.gate_state(SCRIPTS / "_notify.py")
    assert gated, reason


def test_cli_exits_nonzero_when_a_copy_is_ungated(tmp_path):
    """The predicate is only worth anything if its exit code is honest — the beat reads it."""
    stale = tmp_path / "stale"
    _write_notifier(stale, UNGATED)
    probe = tmp_path / "probe.py"
    probe.write_text(
        textwrap.dedent(f"""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("cng", r"{SCRIPTS / "check-notify-gate.py"}")
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        mod.enumerate_roots = lambda live: [__import__("pathlib").Path(r"{stale}")]
        mod._root.resolve = lambda: (__import__("pathlib").Path(r"{stale}"), "test")
        sys.exit(mod.main([]))
        """),
        encoding="utf-8",
    )
    assert subprocess.run([sys.executable, str(probe)], capture_output=True).returncode == 1
