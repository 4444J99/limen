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
import os
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


# ── the host axis: the env floor reaches copies the in-tree gate never will ───────────

WRAPPER = ROOT / "scripts" / "run-pytest-hermetic.sh"

# The shape every ungated copy on this host still has: no gate, but it DOES honor the
# kill-switch. That is the whole reason an environment floor works where a file fix cannot.
OLD_FORM_NOTIFIER = """
    import os, subprocess

    def _enabled(enabled=None):
        if enabled is not None:
            return enabled
        return os.environ.get("LIMEN_NOTIFY", "1") not in ("0", "false", "False")

    def notify_once(root, key, message, title="t", enabled=None):
        if _enabled(enabled):
            subprocess.run(["osascript", "-e", "display notification"])
            return True
        return False
"""


def test_wrapper_arms_the_killswitch_after_the_scrub():
    """Ordering is the property, not presence.

    The wrapper unsets every LIMEN_* variable so a fixture cannot read the operator's runtime.
    An `export LIMEN_NOTIFY=0` placed BEFORE that loop would be scrubbed by it and the effector
    would default back to speaking — silently, and only in the trees that matter.
    """
    text = WRAPPER.read_text(encoding="utf-8")
    scrub = text.index("compgen -A variable LIMEN_")
    arm = text.index("export LIMEN_NOTIFY=0")
    assert arm > scrub, "LIMEN_NOTIFY=0 must be re-armed AFTER the LIMEN_* scrub, or it is erased"


def test_wrapper_overrides_an_inherited_notify_setting(tmp_path):
    """End-to-end, not by reading the script: run the real wrapper and observe the env it hands down."""
    probe = tmp_path / "test_env_probe.py"
    probe.write_text("import os\ndef test_env():\n    assert os.environ['LIMEN_NOTIFY'] == '0'\n", encoding="utf-8")
    env = {**os.environ, "LIMEN_NOTIFY": "1"}  # an inherited setting that must not survive
    done = subprocess.run(
        ["bash", str(WRAPPER), str(probe), "-q"], capture_output=True, text=True, env=env, cwd=tmp_path
    )
    assert done.returncode == 0, done.stdout + done.stderr


def test_env_floor_silences_a_pre_gate_notifier(tmp_path, monkeypatch):
    """The copies that predate #1841 cannot be patched — but they still read the environment.

    This pins the property the whole host axis rests on: an OLD-form notifier, with no
    _root_may_speak anywhere in it, does not reach osascript when LIMEN_NOTIFY=0.
    """
    old = tmp_path / "old_notify.py"
    old.write_text(textwrap.dedent(OLD_FORM_NOTIFIER), encoding="utf-8")
    mod = _load("old_form_notify", old)

    calls = []
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: calls.append(a))

    monkeypatch.setenv("LIMEN_NOTIFY", "0")
    assert mod.notify_once(tmp_path, "k", "m") is False
    assert calls == [], "an ungated copy still reached osascript with the kill-switch set"

    monkeypatch.setenv("LIMEN_NOTIFY", "1")  # and the switch is real, not vacuously true
    assert mod.notify_once(tmp_path, "k", "m") is True
    assert len(calls) == 1


# ── executor classification: a timer-run copy is not a dormant one ────────────────────


def test_classify_separates_the_scheduled_executor(tmp_path, check_gate):
    live, sched = tmp_path / "live", tmp_path / "rt" / "sha" / "source"
    dormant = tmp_path / "rt" / "other" / "source"
    check_gate.INSTALL_RUNTIMES = tmp_path / "rt"

    assert check_gate.classify(sched, live, sched) == "scheduled"
    assert check_gate.classify(live, live, sched) == "live"
    assert check_gate.classify(dormant, live, sched) == "dormant-runtime"
    assert check_gate.classify(tmp_path / "wt", live, sched) == "worktree"


def test_scheduled_executor_fails_even_when_baselined(tmp_path, check_gate, monkeypatch):
    """Recording a live hazard would convert it into an accepted one with a single flag."""
    sched = tmp_path / "rt" / "sha" / "source"
    _write_notifier(sched, UNGATED)
    monkeypatch.setattr(check_gate, "enumerate_roots", lambda _live: [sched])
    monkeypatch.setattr(check_gate, "scheduled_root", lambda: sched)
    monkeypatch.setattr(check_gate, "read_baseline", lambda *a, **k: {str(sched)})
    monkeypatch.setattr(check_gate._root, "resolve", lambda: (sched, "test"))

    assert check_gate.main([]) == 1


def test_baselined_dormant_copy_does_not_fail(tmp_path, check_gate, monkeypatch):
    """The ratchet tolerates what is already draining; it fails on what is NEW."""
    live, stale = tmp_path / "live", tmp_path / "stale"
    _write_notifier(live, GATED)
    _write_notifier(stale, UNGATED)
    monkeypatch.setattr(check_gate, "enumerate_roots", lambda _live: [live, stale])
    monkeypatch.setattr(check_gate, "scheduled_root", lambda: None)
    monkeypatch.setattr(check_gate._root, "resolve", lambda: (live, "test"))

    monkeypatch.setattr(check_gate, "read_baseline", lambda *a, **k: {str(stale)})
    assert check_gate.main([]) == 0, "a recorded, draining copy must not fail the gate"

    monkeypatch.setattr(check_gate, "read_baseline", lambda *a, **k: set())
    assert check_gate.main([]) == 1, "an unrecorded ungated copy is a regression"


def test_baseline_roundtrip_ignores_comments(tmp_path, check_gate):
    path = tmp_path / "baseline.txt"
    check_gate.write_baseline({"/b/root", "/a/root"}, path=path)
    assert check_gate.read_baseline(path) == {"/a/root", "/b/root"}
    assert path.read_text(encoding="utf-8").startswith("#"), "the baseline must explain itself"


def test_shipped_baseline_excludes_the_scheduled_executor():
    """The committed file means 'known, draining' — the launchd-run copy is neither."""
    mod = _load("check_notify_gate_baseline", SCRIPTS / "check-notify-gate.py")
    sched = mod.scheduled_root()
    if sched is None:
        pytest.skip("no runtime install on this host")
    assert str(sched) not in mod.read_baseline()
