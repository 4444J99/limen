"""Tests for the stream REOPEN path: check-session-streams.py's launch emission + open-streams.sh.

The defect these lock down is a round trip that silently did nothing. `--ready` derived the openable
set correctly, but:

  * the command it printed omitted `--agent`, and start-worktree-session.sh execs the agent kickstart
    ONLY under `launch_agent=1`, which only `--agent` sets — so pasting the registry's own command
    wrote a capsule and opened no session at all; and
  * `--ready` was a printer with no machine consumer, so acting on the derived set meant a human
    reading four blocks and retyping four commands — the hand-loop the registry exists to abolish.

Both halves are asserted here, plus the invariant that keeps them honest: the human view and the
machine view come from ONE builder, so a launcher can never run a command the operator was not shown.
"""

import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECK = ROOT / "scripts" / "check-session-streams.py"
OPEN = ROOT / "scripts" / "open-streams.sh"
STARTER = ROOT / "scripts" / "start-worktree-session.sh"


def _mod():
    spec = importlib.util.spec_from_file_location("check_session_streams_under_test", CHECK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def run(*argv):
    return subprocess.run([sys.executable, str(CHECK), *argv], cwd=ROOT, capture_output=True, text=True, check=False)


ROW = {
    "title": "t",
    "runway": "8h",
    "intent": "docs/continuations/x/intent.md",
    "job_class": "governance",
    "owner_of_record": "o",
    "max_children": 2,
}


# ── the emitted command must actually be able to open an agent ───────────────────────


def test_launch_argv_carries_agent_auto_which_is_what_makes_it_launch():
    """Without `--agent` the emitted command opens NOTHING — it writes a capsule and exits.

    This is not a style preference. start-worktree-session.sh sets `launch_agent=1` only in the
    `--agent` branch and reaches its `exec` only under that flag (both coupled below). `auto` rather
    than a vendor name because the capsule contract declares
    `lane_selection: derive_from_live_capabilities`; naming a provider here would be the violation,
    and `auto` resolves through the live census instead.
    """
    argv = _mod().launch_argv("s0-x", ROW)
    assert "--agent" in argv, "no --agent ⇒ launch_agent stays 0 ⇒ the command opens no session"
    assert argv[argv.index("--agent") + 1] == "auto", "a pinned vendor breaks derive_from_live_capabilities"


def test_the_starter_still_couples_agent_to_launching():
    """Pins the coupling the test above depends on, so the two can never drift apart silently.

    If someone reworks start-worktree-session.sh so `--agent` no longer gates the exec, the reason
    `launch_argv` passes `--agent auto` evaporates — and this fails with that explanation rather than
    leaving the previous test asserting a flag whose purpose has quietly moved.
    """
    src = STARTER.read_text()
    assert re.search(r"launch_agent=1", src), "start-worktree-session.sh no longer sets launch_agent"
    assert re.search(r'if \[\[ "\$launch_agent" -eq 1 \]\]; then\s*\n\s*exec bash', src), (
        "the --agent → exec coupling moved; re-verify why launch_argv passes --agent"
    )


# ── one builder: the human view and the machine view can never disagree ─────────────


def test_the_rendered_command_is_exactly_the_argv():
    """A second copy of the command shape is the drift this registry exists to prevent.

    Rendering is allowed to add line continuations and indentation; it may not add, drop, or reorder
    a single token. Tokenising the rendered form and comparing to argv is what proves that.
    """
    m = _mod()
    argv = m.launch_argv("s0-x", ROW)
    rendered = m.launch_command("s0-x", ROW)
    assert rendered.replace("\\\n", " ").split() == argv


def test_json_rows_carry_the_same_argv_the_text_view_prints():
    m = _mod()
    streams = m.load()
    proc = run("--ready", "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    for row in json.loads(proc.stdout):
        assert row["argv"] == m.launch_argv(row["id"], streams[row["id"]])


def test_json_and_text_agree_on_which_streams_are_ready():
    """The launcher must never open a set the operator was not shown, in either direction."""
    from_json = {row["id"] for row in json.loads(run("--ready", "--json").stdout)}
    text = run("--ready").stdout
    # The text view prints ready ids as `── <id> — <title>` headers; every other state is indented.
    from_text = set(re.findall(r"^── (\S+) —", text, re.MULTILINE))
    assert from_json == from_text


def test_json_requires_ready_rather_than_silently_meaning_something_else():
    proc = run("--json")
    assert proc.returncode != 0
    assert "--json applies to --ready" in proc.stderr


def test_drift_refuses_to_emit_machine_readable_rows_too():
    """The JSON path must inherit the same drift guard as the text path.

    open-streams.sh runs the emitted argv without reading it, so an incoherent graph reaching the
    launcher is the one failure that would open real sessions on bad data.
    """
    src = CHECK.read_text()
    guard = src.index("refusing to derive launch commands")
    emit = src.index("print_ready_json(streams) if args.json")
    assert guard < emit, "the JSON emission escaped the registry-coherence guard"


# ── the launcher ────────────────────────────────────────────────────────────────────


@pytest.fixture
def launcher_env():
    if shutil.which("limen") is None:
        pytest.skip("limen not on PATH (pip install -e cli) — the launcher refuses to open windows without it")


def _open(*argv):
    return subprocess.run(["bash", str(OPEN), *argv], cwd=ROOT, capture_output=True, text=True, check=False)


def test_dry_run_touches_nothing_and_needs_no_tmux(launcher_env):
    proc = _open("--dry-run")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DRY RUN" in proc.stdout
    assert "nothing was touched" in proc.stdout


def test_the_bound_is_enforced_and_every_deferred_stream_is_named(launcher_env):
    """A silent cap reads as "all of them opened" when it did not — so deferrals are printed WITH
    the exact command to open them later, not merely counted. Measured against the launcher's
    default family (constellation): family elision is a separate, separately-named subtraction."""
    ready = json.loads(run("--ready", "--json").stdout)
    in_family = [r for r in ready if r["family"] == "constellation"]
    if len(in_family) < 2:
        pytest.skip("needs ≥2 ready constellation streams to observe a bound")
    out = _open("--dry-run", "--max-parallel", "1").stdout
    assert out.count("\n  WOULD ") == 1
    deferred = re.findall(r"^  DEFER  (\S+)", out, re.MULTILINE)
    assert len(deferred) == len(in_family) - 1
    for sid in deferred:
        assert f"--workstream {sid}" in out, f"{sid} was dropped without printing how to open it"


def test_the_resolved_lane_is_reported_before_anything_opens(launcher_env):
    """`--agent auto` is vendor-neutral by contract, so on a stock environment the census order — not
    the operator's intent — picks the lane. Printing it up front is what keeps that from being a
    surprise discovered inside a pane."""
    out = _open("--dry-run").stdout
    assert re.search(r"^  lane: ", out, re.MULTILINE), "the launcher stopped reporting the resolved lane"


# ── --lane: which native lane opens the domains ─────────────────────────────────────
# The registry emits `--agent auto` and may never pin a provider (capsule contract:
# `lane_selection: derive_from_live_capabilities`). `auto` resolves through the live census ordered
# by $LIMEN_AGENT — so WITHOUT a choice, census ORDER decides, which on a stock host is codex, not
# claude. `--lane` is that choice, expressed in the environment rather than in declared data.


def _live_lanes():
    """Ask the SCRIPT which lanes it accepts — never re-derive the rule here.

    A second copy is exactly what broke: this test used `(vendor.name, vendor.binary)` while
    start-worktree-session.sh uses `(override, name, binary if binary == name else "")`. `copilot`
    declares binary `gh`, so the permissive copy listed a lane the launcher could not resolve. It
    passed locally (a real `copilot` binary on PATH) and failed in CI (only `gh`) — a divergence
    invisible on the machine that wrote it.
    """
    out = _open("--list-lanes")
    assert out.returncode == 0, out.stdout + out.stderr
    return out.stdout.split()


def test_each_live_lane_can_be_selected(launcher_env):
    """The operator's ask: open the domains via claude OR codex OR agy OR opencode.

    SKIPS where no lane is live. A CI runner with no agent CLI installed is a legitimate
    environment, not a failure — asserting non-empty made this test demand that the machine running
    it have agents, which is a property of the host and not of the code under test.
    """
    lanes = _live_lanes()
    if not lanes:
        pytest.skip("no live native lane on this host (e.g. CI runner without an agent CLI)")
    for lane in lanes:
        out = _open("--lane", lane, "--dry-run", "--max-parallel", "1").stdout
        assert re.search(rf"^  lane: +{re.escape(lane)}\b", out, re.MULTILINE), (
            f"--lane {lane} did not resolve to {lane}:\n{out}"
        )


def test_a_lane_that_is_not_live_is_refused_before_anything_opens(launcher_env):
    """Refused HERE, with the real alternatives named. Discovering it inside a tmux window means N
    panes each printing an error nobody is watching."""
    proc = _open("--lane", "definitely-not-a-lane", "--dry-run")
    assert proc.returncode == 2
    assert "is not a live native lane" in proc.stderr
    # Holds with zero live lanes too: the refusal then reports "(none)", which is still an honest
    # answer to "what IS available".
    for lane in _live_lanes():
        assert lane in proc.stderr, "the refusal must name what IS available, not just what is not"


def test_the_registry_itself_stays_vendor_neutral(launcher_env):
    """--lane must not leak a vendor into declared data. The emitted argv stays `--agent auto`
    whichever lane is chosen; only the environment differs."""
    for lane in _live_lanes()[:2]:
        out = _open("--lane", lane, "--dry-run").stdout
        if "WOULD" in out:
            assert "--agent auto" in out, f"--lane {lane} pinned a vendor into the emitted command"
            assert f"--agent {lane}" not in out


# ── family selection: "open my streams" means the operator's lanes ──────────────────


def test_default_family_is_the_operators_constellation(launcher_env):
    """The word "streams" is the operator's, from the constellation work (#1535). The default
    open must be his people × project lanes — governance plumbing answering "open my streams"
    is the exact defect that had the estate quoting a registry invented that morning."""
    out = _open("--dry-run").stdout
    assert "family: constellation" in out
    for sid in ("s0-corpus-custody", "s10-axis-coverage", "s2-public-distillation"):
        assert sid not in out, f"governance domain {sid} leaked into the default family"


def test_elided_governance_domains_are_named_never_silent(launcher_env):
    """A filtered-out domain the operator cannot see reads as one that does not exist."""
    out = _open("--dry-run").stdout
    assert "--family governance" in out, "the elision must say how to reach what it hid"


def test_family_all_reunites_both(launcher_env):
    out = _open("--dry-run", "--family", "all", "--max-parallel", "1").stdout
    assert "family: all" in out
    joined = out.replace("\n", " ")
    assert "spiral" in joined and "s10-axis-coverage" in joined


def test_an_unknown_family_is_refused_before_anything_opens(launcher_env):
    proc = _open("--family", "bogus", "--dry-run")
    assert proc.returncode == 2
    assert "constellation|governance|all" in proc.stderr


def test_t1_lanes_open_before_t2_under_the_bound(launcher_env):
    """The RAM bound opens the FIRST N rows, so order is priority: an alphabetical T2 lane
    (content-cannibalizer) must never preempt a T1 lane the operator marked active-demand."""
    out = _open("--dry-run", "--max-parallel", "1").stdout
    opened = [line for line in out.splitlines() if line.lstrip().startswith("WOULD")]
    assert opened, out
    assert "(T1," in opened[0], f"the single opened slot went to a non-T1 lane: {opened[0]}"
