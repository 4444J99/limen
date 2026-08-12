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
from types import SimpleNamespace

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

NTFY_GATED = """
    import urllib.request

    def _root_may_speak(root):
        return True

    def notify_ntfy(root, message):
        if not _root_may_speak(root):
            return False
        urllib.request.urlopen("https://example.invalid", data=message.encode())
        return True
"""

NTFY_UNGATED = """
    import urllib.request

    def notify_ntfy(root, message):
        urllib.request.urlopen("https://example.invalid", data=message.encode())
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
    [
        (GATED, True),
        (UNGATED, False),
        (MENTIONS_ONLY, False),
        (DEFINED_NOT_CALLED, False),
        (NTFY_GATED, True),
        (NTFY_UNGATED, False),
    ],
)
def test_gate_state_is_structural_not_substring(tmp_path, check_gate, body, gated):
    path = _write_notifier(tmp_path, body)
    assert check_gate.gate_state(path)[0] is gated


def test_python_test_helper_with_direct_effector_is_detected(tmp_path, check_gate):
    helper = tmp_path / "tests" / "test_helper.py"
    helper.parent.mkdir()
    helper.write_text(
        'import subprocess\nsubprocess.run(["osascript", "-e", \'display notification "x"\'])\n',
        encoding="utf-8",
    )

    assert check_gate._python_bypasses(helper) is True


def test_python_test_helper_with_concatenated_effector_command_is_detected(tmp_path, check_gate):
    helper = tmp_path / "tests" / "test_concat.py"
    helper.parent.mkdir()
    helper.write_text(
        "import subprocess\n"
        'command = "osa" + "script"\n'
        'message = "display " + "notification"\n'
        'subprocess.run([command, "-e", message])\n',
        encoding="utf-8",
    )

    assert check_gate._python_bypasses(helper) is True


def test_tracked_concatenated_executable_survives_source_prefilter(tmp_path, check_gate, monkeypatch):
    sender = tmp_path / "scripts" / "sender.py"
    sender.parent.mkdir()
    sender.write_text(
        "import subprocess\n"
        'command = "osa" + "script"\n'
        'message = "display " + "notification x"\n'
        'subprocess.run([command, "-e", message])\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(check_gate, "_clean_exact_head", lambda _root: None)
    monkeypatch.setattr(
        check_gate.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout=b"scripts/sender.py\0"),
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_shell_command_regex_accepts_path_and_arguments(check_gate):
    assert check_gate._OSASCRIPT_COMMAND_RE.search("/usr/bin/osascript -e display")
    assert check_gate._OSASCRIPT_COMMAND_RE.search("osascript -e display")
    assert check_gate._OSASCRIPT_COMMAND_RE.search('"/usr/bin/osascript" -e display')


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


def test_direct_python_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        'import subprocess\nsubprocess.run(["osascript", "-e", \'display notification "x"\'])\n',
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_list_bound_python_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        'import subprocess\ncmd = ["osascript", "-e", \'display notification "x"\']\nsubprocess.run(cmd)\n',
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


@pytest.mark.parametrize(
    "expression",
    [
        '[subprocess.run(cmd) for cmd in [["osascript", "-e", "display notification x"]]]',
        '{subprocess.run(cmd) for cmd in [["osascript", "-e", "display notification x"]]}',
        '(subprocess.run(cmd) for cmd in [["osascript", "-e", "display notification x"]])',
        '{"delivery": subprocess.run(cmd) for cmd in [["osascript", "-e", "display notification x"]]}',
    ],
)
def test_comprehension_target_notification_bypass_is_rejected(tmp_path, check_gate, expression):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(f"import subprocess\n{expression}\n", encoding="utf-8")

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


@pytest.mark.parametrize(
    "source",
    [
        'for cmd in [["osascript", "-e", "display notification x"]]:\n    subprocess.run(cmd)\n',
        'async def fire():\n    async for cmd in [["osascript", "-e", "display notification x"]]:\n'
        "        subprocess.run(cmd)\n",
    ],
)
def test_loop_target_notification_bypass_is_rejected(tmp_path, check_gate, source):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(f"import subprocess\n{source}", encoding="utf-8")

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


@pytest.mark.parametrize(
    "signature",
    [
        'cmd=["osascript", "-e", "display notification x"]',
        '*, cmd=["osascript", "-e", "display notification x"]',
    ],
)
def test_default_parameter_notification_bypass_is_rejected(tmp_path, check_gate, signature):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        f"import subprocess\ndef fire({signature}):\n    subprocess.run(cmd)\nfire()\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_destructured_python_command_binding_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        'import subprocess\ncmd, unused = (["osascript", "-e", "display notification x"], None)\nsubprocess.run(cmd)\n',
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_reassigned_python_command_uses_binding_visible_at_each_call(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        "import subprocess\n"
        "cmd = ['osascript', '-e', 'display notification \"x\"']\n"
        "subprocess.run(cmd)\n"
        "cmd = ['echo', 'clean']\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_variable_bound_python_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        "import subprocess\n"
        "script = 'display notification \"x\"'\n"
        "subprocess.run(['/usr/bin/osascript', '-e', script])\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_fstring_bound_python_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        "import subprocess\n"
        "message = 'x'\n"
        "script = f'display notification \"{message}\"'\n"
        "subprocess.run(['/usr/bin/osascript', '-e', script])\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_variable_bound_shell_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.sh").write_text(
        """script='display notification "x"'
osascript -e "$script"
""",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.sh"]


def test_direct_shell_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.sh").write_text(
        """osascript -e 'display notification "x"'\n""",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.sh"]


def test_declared_python_encoding_is_decoded(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    sender = scripts / "sender.py"
    sender.write_bytes(
        (
            "# -*- coding: latin-1 -*-\n"
            "import subprocess\n"
            "# café\n"
            'subprocess.run(["osascript", "-e", '
            "'display notification \\\"x\\\"'])\n"
        ).encode("latin-1")
    )

    assert check_gate._python_bypasses(sender) is True
    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_imported_process_alias_survives_function_class_and_if_scopes(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        "from subprocess import run as execute\n"
        "class Sender:\n"
        "    def send(self, enabled):\n"
        "        if enabled:\n"
        "            execute(['osascript', '-e', 'display notification \\\"x\\\"'])\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_conditionally_imported_process_alias_is_tracked_after_branch(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        "if enabled:\n"
        "    from subprocess import run as execute\n"
        "execute(['osascript', '-e', 'display notification \\\"x\\\"'])\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_process_attribute_assignment_alias_is_tracked(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        "import subprocess\nexecute = subprocess.run\nexecute(['osascript', '-e', 'display notification \\\"x\\\"'])\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_function_uses_module_binding_assigned_after_definition(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        "import subprocess\n"
        "def fire():\n"
        "    subprocess.run(command)\n"
        "command = ['osascript', '-e', 'display notification \\\"x\\\"']\n"
        "fire()\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_try_and_exception_command_bindings_are_merged(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        "import subprocess\n"
        "try:\n"
        "    command = ['osascript', '-e', 'display notification \\\"x\\\"']\n"
        "except OSError:\n"
        "    command = ['echo', 'quiet']\n"
        "subprocess.run(command)\n",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_os_popen_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        'import os\nos.popen("osascript -e \'display notification \\"x\\"\'")\n',
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_git_degradation_fallback_scans_beyond_scripts(tmp_path, check_gate):
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "sender.py").write_text(
        'import subprocess\nsubprocess.run(["osascript", "-e", "display notification x"])\n',
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["tools/sender.py"]


def test_git_degradation_fallback_fails_closed_at_candidate_limit(tmp_path, check_gate, monkeypatch):
    (tmp_path / "one.py").write_text("# one\n", encoding="utf-8")
    (tmp_path / "two.py").write_text("# two\n", encoding="utf-8")
    monkeypatch.setattr(check_gate, "SOURCE_FALLBACK_MAX_PATHS", 1)

    assert check_gate.direct_notification_effectors(tmp_path) == [check_gate.SOURCE_SCAN_FAILURE]


def test_clean_exact_head_reuses_source_path_scan(tmp_path, check_gate, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        'import subprocess\nsubprocess.run(["osascript", "-e", "display notification x"])\n',
        encoding="utf-8",
    )
    calls = []
    check_gate._SOURCE_PATH_CACHE.clear()
    monkeypatch.setattr(check_gate, "_clean_exact_head", lambda _root: "a" * 40)

    def fake_run(*_args, **_kwargs):
        calls.append(True)
        return SimpleNamespace(returncode=0, stdout=b"scripts/sender.py\0")

    monkeypatch.setattr(check_gate.subprocess, "run", fake_run)

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]
    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]
    assert len(calls) == 1


def test_undecodable_notification_sources_fail_closed(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    python_sender = scripts / "python_sender.py"
    shell_sender = scripts / "shell_sender.sh"
    python_sender.write_bytes(
        b"import subprocess\n# undecodable: " + bytes([0xFF]) + b"\n"
        b'subprocess.run(["osascript", "-e", "display notification x"])\n'
    )
    shell_sender.write_bytes(b"osascript -e 'display notification \"x\"' # " + bytes([0xFF]) + b"\n")

    assert check_gate._python_bypasses(python_sender) is True
    assert check_gate._shell_bypasses(shell_sender) is True
    assert set(check_gate.direct_notification_effectors(tmp_path)) == {
        "scripts/python_sender.py",
        "scripts/shell_sender.sh",
    }


def test_live_tree_has_one_mac_notification_effector(check_gate):
    assert check_gate.direct_notification_effectors(ROOT) == []


def test_delivery_result_reflects_osascript_exit_status(monkeypatch):
    mod = _load("_notify_delivery_status", SCRIPTS / "_notify.py")
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )

    assert mod._deliver("message", "title") is False


def test_ntfy_delivery_honors_liveness_and_kill_switch(tmp_path, monkeypatch):
    mod = _load("_notify_ntfy_gate", SCRIPTS / "_notify.py")
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    monkeypatch.setenv("LIMEN_NTFY_TOPIC", "test-topic")
    monkeypatch.setattr(mod, "_root_may_speak", lambda _root: True)
    monkeypatch.setattr(
        mod.urllib.request,
        "urlopen",
        lambda request, timeout: calls.append((request, timeout)) or Response(),
    )

    monkeypatch.setenv("LIMEN_NOTIFY", "0")
    assert mod.notify_ntfy(tmp_path, "message", title="title") is False
    assert calls == []

    monkeypatch.setenv("LIMEN_NOTIFY", "1")
    assert mod.notify_ntfy(tmp_path, "message", title="title") is True
    assert len(calls) == 1


def test_gate_state_follows_helper_delivery_route(tmp_path, check_gate):
    notifier = _write_notifier(
        tmp_path,
        """
        def _root_may_speak(root):
            return True

        def _deliver(message, title):
            return True

        def _send(message):
            return _deliver(message, "title")

        def notify(root, message):
            if _root_may_speak(root):
                return _send(message)
        """,
    )

    gated, reason = check_gate.gate_state(notifier)

    assert gated, reason


def test_gate_state_rejects_or_override_delivery_condition(tmp_path, check_gate):
    notifier = _write_notifier(
        tmp_path,
        """
        def _root_may_speak(root):
            return True

        def _deliver(message, title):
            return True

        def notify(root, message, override=False):
            if _root_may_speak(root) or override:
                return _deliver(message, "title")
        """,
    )

    gated, reason = check_gate.gate_state(notifier)

    assert gated is False
    assert "notify" in reason


def test_gate_state_rejects_partial_negative_guard(tmp_path, check_gate):
    notifier = _write_notifier(
        tmp_path,
        """
        def _root_may_speak(root):
            return True

        def _deliver(message, title):
            return True

        def notify(root, message, condition):
            if not _root_may_speak(root) and condition:
                return
            return _deliver(message, "title")
        """,
    )

    gated, reason = check_gate.gate_state(notifier)

    assert gated is False
    assert "notify" in reason


def test_gate_state_requires_control_dependency(tmp_path, check_gate):
    notifier = _write_notifier(
        tmp_path,
        """
        def _root_may_speak(root):
            return True

        def _deliver(message, title):
            return True

        def notify(root, message):
            _root_may_speak(root)
            return _deliver(message, "title")
        """,
    )

    gated, reason = check_gate.gate_state(notifier)

    assert gated is False
    assert "notify" in reason


def test_every_public_delivery_route_must_call_the_gate(tmp_path, check_gate):
    notifier = _write_notifier(
        tmp_path,
        """
        def _root_may_speak(root):
            return True

        def _deliver(message, title):
            return True

        def notify(root, message):
            if _root_may_speak(root):
                return _deliver(message, "title")

        def notify_once(root, key, message):
            return _deliver(message, "title")
        """,
    )

    gated, reason = check_gate.gate_state(notifier)

    assert gated is False
    assert "notify_once" in reason


def test_multiline_shell_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.sh").write_text(
        """osascript <<'APPLESCRIPT'
display notification "x"
APPLESCRIPT
""",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.sh"]


def test_non_utf8_candidate_is_reported_without_crashing_the_estate_scan(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_bytes(b"osascript\xffdisplay notification")

    # An undecodable source is unsafe evidence: report it so the estate gate fails closed.
    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_shell_string_python_notification_bypass_is_rejected(tmp_path, check_gate):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.py").write_text(
        """import os
os.system('osascript -e "display notification \\"x\\""')
""",
        encoding="utf-8",
    )

    assert check_gate.direct_notification_effectors(tmp_path) == ["scripts/sender.py"]


def test_direct_effector_is_scanned_even_without_shared_notifier(tmp_path, check_gate, monkeypatch):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "sender.sh").write_text(
        "osascript -e 'display notification \"x\"'\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(check_gate, "enumerate_roots", lambda _live: [tmp_path])

    [row] = check_gate.survey(tmp_path)

    assert row["gated"] is False
    assert row["direct_effectors"] == ["scripts/sender.sh"]


def test_netmode_binds_notifier_to_the_invoking_checkout():
    shell = (SCRIPTS / "netmode.sh").read_text(encoding="utf-8")

    assert '_notify_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"' in shell
    assert '_notify_root="${LIMEN_ROOT:-$(cd "$_notify_script_dir/.." && pwd)}"' in shell
    assert '"$_notify_script_dir/_notify.py"' in shell
    live_helper = '"$HOME/Workspace/limen/scripts/_notify.py"'
    runtime_helper = '"$HOME/.local/share/limen/current/source/scripts/_notify.py"'
    assert live_helper in shell
    assert runtime_helper in shell
    assert shell.index('"$_notify_script_dir/_notify.py"') < shell.index(live_helper)
    assert shell.index(live_helper) < shell.index(runtime_helper)
    assert '_notify_root="$(cd "$(dirname "$LIMEN_NOTIFY_HELPER")/.." && pwd)"' in shell
    assert '--root "$_notify_root"' in shell
