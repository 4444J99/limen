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
import os
import re
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import limen.census as census
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
    default family (domain): family elision is a separate, separately-named subtraction."""
    ready = json.loads(run("--ready", "--json").stdout)
    in_family = [r for r in ready if r["family"] == "domain"]
    if len(in_family) < 2:
        pytest.skip("needs ≥2 ready domain streams to observe a bound")
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

    A second candidate rule is exactly what broke this path. The script and launcher now import the
    same registry-derived helper, while the issue-assignment exclusion remains a separate
    launchability predicate.
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


def test_issue_assignment_lanes_are_never_listed_as_native_workstreams() -> None:
    issue_assignment = {vendor.name for vendor in census.VENDORS if vendor.issue_assignment}

    assert issue_assignment.isdisjoint(_live_lanes())


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


def test_lane_listing_resolves_a_renamed_registry_id_through_its_distinct_binary(tmp_path: Path) -> None:
    source = next(
        vendor
        for vendor in census.VENDORS
        if vendor.status.available
        and vendor.status.state == "live"
        and (vendor.execution.transport == "native-cli" or vendor.execution.transport.startswith("ianva-"))
    )
    renamed = replace(
        source,
        name="fixture-stream-provider-renamed",
        aliases=(),
        binary="fixture-stream-provider-cli",
    )
    fixture_root = tmp_path / "fixture-limen"
    (fixture_root / "scripts").mkdir(parents=True)
    shutil.copy2(OPEN, fixture_root / "scripts" / "open-streams.sh")
    shutil.copytree(ROOT / "cli" / "src", fixture_root / "cli" / "src")
    census_path = fixture_root / "cli" / "src" / "limen" / "census.py"
    registry_source = census_path.read_text(encoding="utf-8")
    record_start = registry_source.index(f'    Vendor(\n        name="{source.name}",')
    record_end = registry_source.find("\n    Vendor(", record_start + 1)
    if record_end == -1:
        record_end = len(registry_source)
    source_record = registry_source[record_start:record_end]
    renamed_record = source_record.replace(f'name="{source.name}"', f'name="{renamed.name}"', 1)
    renamed_record = renamed_record.replace(f'binary="{source.binary}"', f'binary="{renamed.binary}"', 1)
    alias_line = next(line for line in renamed_record.splitlines() if line.strip().startswith("aliases="))
    renamed_record = renamed_record.replace(alias_line, "        aliases=(),", 1)
    census_path.write_text(
        registry_source[:record_start] + renamed_record + registry_source[record_end:],
        encoding="utf-8",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_provider = fake_bin / renamed.binary
    fake_provider.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    fake_provider.chmod(0o755)

    result = subprocess.run(
        ["bash", str(fixture_root / "scripts" / "open-streams.sh"), "--list-lanes"],
        cwd=fixture_root,
        env={**os.environ, "PATH": f"{fake_bin}:{os.environ['PATH']}"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert renamed.name in result.stdout.splitlines()
    assert source.name not in result.stdout.splitlines()


def test_the_registry_itself_stays_vendor_neutral(launcher_env):
    """--lane must not leak a vendor into declared data. The emitted argv stays `--agent auto`
    whichever lane is chosen; only the environment differs."""
    for lane in _live_lanes()[:2]:
        out = _open("--lane", lane, "--dry-run").stdout
        if "WOULD" in out:
            assert "--agent auto" in out, f"--lane {lane} pinned a vendor into the emitted command"
            assert f"--agent {lane}" not in out


# ── family selection: "open my streams" means the operator's lanes ──────────────────


def test_default_family_is_the_operators_life_domains(launcher_env):
    """The 2026-07-30 correction: "open my streams" means the operator's LIFE/WORK DOMAINS
    (correspondence, financial, representation, …) — never governance plumbing, and never one
    domain's collaborator interior opened as siblings. Both prior defects, pinned."""
    out = _open("--dry-run").stdout
    assert "family: domain" in out
    ready = json.loads(run("--ready", "--json").stdout)
    for row in ready:
        if row["family"] != "domain":
            assert f"--workstream {row['id']} " not in out.replace("\n", " ") + " ", (
                f"{row['family']} row {row['id']} leaked into the default family"
            )


def test_elided_families_are_named_never_silent(launcher_env):
    """A filtered-out row the operator cannot see reads as one that does not exist — the elision
    must name every hidden family and say how to reach it."""
    ready = json.loads(run("--ready", "--json").stdout)
    hidden = sorted({r["family"] for r in ready if r["family"] != "domain"})
    if not hidden:
        pytest.skip("no non-domain rows ready — nothing to elide")
    out = _open("--dry-run").stdout
    for fam in hidden:
        assert f"--family {fam}" in out, f"the elision must say how to reach hidden family {fam}"
    assert "--family all" in out


def test_family_all_reunites_both(launcher_env):
    out = _open("--dry-run", "--family", "all", "--max-parallel", "1").stdout
    assert "family: all" in out
    joined = out.replace("\n", " ")
    # maddie is a constellation PERSON-domain row (streams are people, never their projects —
    # the 2026-07-30 granularity correction); s10 is governance. Both visible ⟺ reunited.
    assert "maddie" in joined and "s10-axis-coverage" in joined


def test_an_unknown_family_is_refused_before_anything_opens(launcher_env):
    proc = _open("--family", "bogus", "--dry-run")
    assert proc.returncode == 2
    assert "domain|constellation|governance|all" in proc.stderr


def test_t1_lanes_open_before_t2_under_the_bound(launcher_env):
    """The RAM bound opens the FIRST N rows, so order is priority: an alphabetical T2 lane
    (content-cannibalizer) must never preempt a T1 lane the operator marked active-demand.
    Measured inside the constellation family, where register_tier is the ordering word."""
    out = _open("--dry-run", "--family", "constellation", "--max-parallel", "1").stdout
    opened = [line for line in out.splitlines() if line.lstrip().startswith("WOULD")]
    assert opened, out
    assert "(T1," in opened[0], f"the single opened slot went to a non-T1 lane: {opened[0]}"


def test_the_ratified_head_opens_first_in_the_default_family(launcher_env):
    """open_rank is the domain family's ordering word: under a bound of 1, the single slot goes
    to the roster's rank-1 domain (correspondence — the mail lane), never an alphabetical one."""
    out = _open("--dry-run", "--max-parallel", "1").stdout
    opened = [line for line in out.splitlines() if line.lstrip().startswith("WOULD")]
    assert opened, out
    assert "correspondence" in opened[0], f"the single opened slot skipped rank 1: {opened[0]}"


# ── What the FIRST LIVE LAUNCH surfaced (2026-07-29) ─────────────────────────────────────────────
# CI never opens a real stream, so two defects survived fifteen green PRs and appeared only when a
# lane actually opened on a live host. Both contracts are pinned against the shipped source because
# neither is reachable from a hermetic test: check D runs against the real repo's .worktrees/, and
# the hydrate line only matters inside a real tmux pane.


def test_check_d_accepts_the_receipt_inside_the_worktree():
    """The receipt is written ON THE STREAM'S BRANCH, inside its worktree — it reaches the main
    checkout's docs tree only at merge. Check D must accept either home, or every freshly opened
    stream turns --status into a red drift failure for the whole life of its branch."""
    src = CHECK.read_text()
    assert 'os.path.join(wt, "docs", "continuations", slug, "workstream.json")' in src, (
        "check D no longer looks for the receipt inside the worktree — an open stream will "
        "break --status until its branch merges"
    )


def test_the_launcher_hydrates_the_credential_env_before_the_agent():
    """A fresh tmux pane inherits no conduct-broker identity; without sourcing the credential
    organ's env sink the launched agent dies at birth on BrokerUnavailable. Values are sourced
    into the pane, never printed."""
    src = OPEN.read_text()
    assert '. "$HOME/.limen.env"' in src, "the pane no longer sources ~/.limen.env"
    hydrate_at = src.index('. "$HOME/.limen.env"')
    exited_at = src.index("stream %s exited")
    assert hydrate_at < exited_at, "hydration must precede the workstream command in the pane"


def test_a_kept_window_is_respawned_into_not_skipped():
    """The window survives exit by design (the closeout stays readable), so window presence must
    never be read as 'stream running' — that froze every exited lane on SKIP and broke the
    advertised exit → one command → reopen round trip. The launcher respawns the stream into its
    kept window; liveness (not window existence) is the sole idempotency authority."""
    src = OPEN.read_text()
    assert "tmux respawn-window -k" in src, "the kept-window reopen path is gone"
    assert "tmux window already open" not in src, (
        "the window-presence SKIP is back — a kept closeout window will freeze reopen forever"
    )
