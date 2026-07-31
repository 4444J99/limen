"""An outward action with no reachable gate is an ungoverned effector.

The defect these pin: `scripts/hooks/outbound-preflight-guard.py` is a PreToolUse(Bash) hook. It
inspects a COMMAND STRING an agent is about to run. It cannot see — and by construction can never
see — `subprocess.run(["gh", "pr", "comment", url, ...])` executed inside a Python module, because
no shell, no command string, and no tool call exist on that path.

Every genuinely dangerous outward action in this estate takes that in-process form and runs
unattended on the beat: repo visibility flips, PR merges that auto-deploy the live site, comments
on third-party repositories, Actions-secret writes, remote-branch deletions, real SMTP sends. The
hook covers the surface where a charter-reading model is already in the loop and misses all the
sharp ones.

The hard part is that a hand grep gets this WRONG, which is why the check is mechanical. Grepping
`subprocess.run(["gh"` under-counted the live estate by 40% (17 of 24): `autonomy-governor.py`
binds `merge_cmd = ["gh", "pr", "merge", pr, "--squash"]` to a NAME and runs it later, and
`sync-hishand-issues.py` routes through a local `sh()` wrapper. Walking every list literal whose
first element is "gh" is invariant to how the argv reaches the process. Several tests below are
negative controls for exactly that miss.

The other half are negative controls against the opposite failure: a gate that fires on `gh pr
view` would make itself hostile to the read-only predicates it wants written, and the honest
response to a noisy gate is a baseline entry. False positives are how this becomes advisory.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def ce():
    spec = importlib.util.spec_from_file_location("ce_mod", ROOT / "scripts" / "check-effectors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _src(tmp_path: Path, body: str, name: str = "sender.py") -> Path:
    path = tmp_path / name
    path.write_text(body)
    return path


# ── class C: the scanner must be invariant to HOW the argv reaches the process ───────────────


def test_the_call_argument_form_is_found(ce, tmp_path):
    """The obvious shape — an argv list passed straight to subprocess.run."""
    path = _src(tmp_path, 'import subprocess\nsubprocess.run(["gh", "pr", "comment", url, "--body", b])\n')
    assert ce.scan_file(path) == {"gh pr comment"}


def test_the_assignment_form_is_found(ce, tmp_path):
    """NEGATIVE CONTROL for the grep miss.

    scripts/autonomy-governor.py:255 binds the argv to a name and runs it elsewhere. A walk over
    subprocess-call ARGUMENTS would miss the single most consequential site in that file — a merge
    to main, which auto-deploys the live site.
    """
    path = _src(tmp_path, 'merge_cmd = ["gh", "pr", "merge", pr, "--squash"]\nlater(merge_cmd)\n')
    assert ce.scan_file(path) == {"gh pr merge"}


def test_the_local_wrapper_form_is_found(ce, tmp_path):
    """scripts/sync-hishand-issues.py goes through a local `sh()`, not subprocess directly."""
    path = _src(tmp_path, 'url = sh(["gh", "issue", "create", "--label", LABEL, "--title", t])\n')
    assert ce.scan_file(path) == {"gh issue create"}


def test_a_variable_stops_the_constant_run_without_losing_the_verb(ce, tmp_path):
    """Extraction is syntactic: it stops at the first non-constant and never evaluates anything."""
    path = _src(tmp_path, 'x = ["gh", "pr", "merge", url, "--auto", "--squash"]\n')
    assert ce.scan_file(path) == {"gh pr merge"}


def test_several_distinct_verbs_in_one_file_are_reported_separately(ce, tmp_path):
    path = _src(
        tmp_path,
        'a = ["gh", "pr", "create", "--title", t]\n'
        'b = ["gh", "pr", "merge", n, "--squash"]\n'
        'c = ["gh", "pr", "create", "--title", u]\n',
    )
    assert ce.scan_file(path) == {"gh pr create", "gh pr merge"}


@pytest.mark.parametrize(
    "argv",
    [
        '["gh", "pr", "view", n, "--json", "state"]',
        '["gh", "pr", "list", "--limit", "10"]',
        '["gh", "pr", "checks", n]',
        '["gh", "pr", "diff", n]',
        '["gh", "issue", "view", n]',
        '["gh", "repo", "view", "--json", "nameWithOwner"]',
        '["gh", "api", "repos/o/r/issues/1/comments"]',
        '["gh", "auth", "status"]',
    ],
)
def test_read_verbs_are_never_flagged(ce, tmp_path, argv):
    """A gate that fires on reads is hostile to the predicates it wants written.

    Every preflight predicate in this estate is built out of `gh api` and `gh pr view`. Flagging
    those would mean the only way to satisfy class C is to stop checking reality — the precise
    inversion this whole registry exists to prevent.
    """
    assert ce.scan_file(_src(tmp_path, f"run({argv})\n")) == set()


@pytest.mark.parametrize("method,flag", [("POST", "-X"), ("PUT", "--method"), ("PATCH", "-X"), ("DELETE", "-X")])
def test_gh_api_with_a_mutating_method_is_flagged(ce, tmp_path, method, flag):
    """scripts/reap-remote-branches.py deletes remote refs this way; consolidate-github.py writes."""
    path = _src(tmp_path, f'run(["gh", "api", "{flag}", "{method}", "repos/o/r/x"])\n')
    assert ce.scan_file(path) == {f"gh api -X {method}"}


def test_gh_api_with_an_explicit_get_is_not_flagged(ce, tmp_path):
    assert ce.scan_file(_src(tmp_path, 'run(["gh", "api", "-X", "GET", "repos/o/r"])\n')) == set()


@pytest.mark.parametrize(
    "line,expected",
    [
        ("import smtplib", "import smtplib"),
        ("import yagmail", "import yagmail"),
        ("from smtplib import SMTP_SSL", "import smtplib"),
    ],
)
def test_in_process_smtp_senders_are_flagged(ce, tmp_path, line, expected):
    """organs/representation/representation_substrate.py:3255 opens SMTP_SSL itself.

    The registry's `mail.send` match list already contains the pattern `smtplib\\.SMTP` — but a
    match pattern is tested against a COMMAND STRING, so it only fires on
    `python3 -c "import smtplib; ..."`. It cannot fire on a module that imports smtplib and calls
    it, which is the form the estate actually uses.
    """
    assert ce.scan_file(_src(tmp_path, line + "\n")) == {expected}


def test_display_notification_is_deliberately_not_flagged(ce, tmp_path):
    """A local desktop toast is not an outward send.

    scripts/conducting-report.py, notify-events.py and _notify.py all shell to
    `osascript -e 'display notification ...'`. Flagging them would train readers to skim class C,
    which is how a gate becomes advisory.
    """
    path = _src(tmp_path, 'subprocess.run(["osascript", "-e", \'display notification "x" with title "y"\'])\n')
    assert ce.scan_file(path) == set()


def test_a_file_that_does_not_parse_is_skipped_not_fatal(ce, tmp_path):
    """The scanner walks the whole tree; one unparseable file must not take the gate down."""
    assert ce.scan_file(_src(tmp_path, "def broken(:\n")) == set()


def test_tests_are_excluded_from_the_scan(ce, tmp_path, monkeypatch):
    """A fixture that BUILDS `["gh", "pr", "merge", ...]` to assert a guard rejects it is the
    opposite of an ungated sender. Flagging fixtures would make a baseline entry the only honest
    response to this gate."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "real.py").write_text('run(["gh", "pr", "merge", n, "--squash"])\n')
    (tmp_path / "scripts" / "tests").mkdir()
    (tmp_path / "scripts" / "tests" / "fixture.py").write_text('run(["gh", "repo", "delete", r])\n')
    (tmp_path / "scripts" / "test_thing.py").write_text('run(["gh", "repo", "delete", r])\n')

    monkeypatch.setattr(ce, "ROOT", tmp_path)
    monkeypatch.setattr(ce, "SCAN_ROOTS", ("scripts",))
    names = {p.name for p in ce._iter_python_files()}
    assert names == {"real.py"}


# ── class A: a declared predicate that is not on disk ────────────────────────────────────────


def _registry(**effector) -> dict:
    base = {
        "title": "t",
        "match": [r"\bgh\b"],
        "target": {"kind": "gh_ref", "pattern": r"([0-9]+)"},
        "predicate": "python3 scripts/check-effectors.py --number {target}",
        "max_age_seconds": 900,
        "reason": "r",
    }
    base.update(effector)
    return {"receipts_dir": "logs/x", "effectors": {"e.one": base}}


def test_a_predicate_naming_a_missing_file_is_a_finding(ce):
    """THE generalisation of check-runner-coverage finding C.

    On 2026-07-31 `github.comment` shipped declaring scripts/preflight-thread-state.py while no
    such file existed. Because the guard fails CLOSED inside its match, arming the hook would not
    merely have left the effector unproven — it would have denied every `gh pr comment` in the
    estate.
    """
    findings: list[str] = []
    ce.check_declaration(_registry(predicate="python3 scripts/does-not-exist.py --n {target}"), findings)
    assert any(f.startswith("A predicate-missing") for f in findings), findings


def test_an_existing_predicate_is_accepted(ce):
    """Positive control — the same code path must stay quiet when the file is really there."""
    findings: list[str] = []
    ce.check_declaration(_registry(), findings)
    assert not [f for f in findings if f.startswith("A predicate-missing")], findings


def test_a_predicate_without_a_target_substitution_is_a_finding(ce):
    """No {target} means one receipt satisfies every recipient — the binding is the whole design."""
    findings: list[str] = []
    ce.check_declaration(_registry(predicate="python3 scripts/check-effectors.py"), findings)
    assert any(f.startswith("A predicate-untargeted") for f in findings), findings


def test_a_yaml_boolean_max_age_is_rejected(ce):
    """`max_age_seconds: yes` parses to True, and isinstance(True, int) is True in Python — so a
    naive check reads it as a valid one-second window."""
    findings: list[str] = []
    ce.check_declaration(_registry(max_age_seconds=True), findings)
    assert any(f.startswith("A max-age-invalid") for f in findings), findings


@pytest.mark.parametrize("age", [0, -1])
def test_a_non_positive_max_age_is_rejected(ce, age):
    findings: list[str] = []
    ce.check_declaration(_registry(max_age_seconds=age), findings)
    assert any(f.startswith("A max-age-invalid") for f in findings), findings


def test_a_missing_required_key_is_a_finding(ce):
    registry = _registry()
    del registry["effectors"]["e.one"]["reason"]
    findings: list[str] = []
    ce.check_declaration(registry, findings)
    assert any("key-missing" in f and "reason" in f for f in findings), findings


def test_a_receipts_dir_outside_logs_is_a_finding(ce):
    """Receipts are runtime state. A receipts_dir under a tracked path would commit them."""
    registry = _registry()
    registry["receipts_dir"] = "institutio/receipts"
    findings: list[str] = []
    ce.check_declaration(registry, findings)
    assert any(f.startswith("A receipts-dir-committed") for f in findings), findings


# ── class B: the single-capture-group bound ──────────────────────────────────────────────────


def test_a_two_group_target_pattern_is_a_finding(ce):
    """The silent-partial-target hazard, made checkable.

    The guard extracts `match.group(1) if match.groups() else match.group(0)`
    (outbound-preflight-guard.py:94). A two-group pattern therefore keeps the first and DISCARDS
    the second, so a well-meant `(--repo (\\S+)\\s+)?([0-9]+)` would run the predicate against the
    AMBIENT repo's #N while the command addresses a different repo's #N. Checking the wrong thread
    and reporting success is worse than refusing to look. The registry states this in a comment;
    this test is what makes the comment true.
    """
    findings: list[str] = []
    ce.check_patterns(
        {
            "e": {
                **_registry()["effectors"]["e.one"],
                "target": {"kind": "gh_ref", "pattern": r"(?:--repo\s+(\S+)\s+)?([0-9]+)"},
            }
        },
        findings,
    )
    assert any(f.startswith("B target-overgrouped") for f in findings), findings


@pytest.mark.parametrize(
    "pattern",
    [
        r"([0-9]+)",  # one group — github.comment's shape
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",  # zero groups — mail.send's actual shape
        r"(?:pr|issue)\s+comment\s+([0-9]+)",  # non-capturing group does not count
    ],
)
def test_zero_or_one_capture_group_is_accepted(ce, pattern):
    findings: list[str] = []
    ce.check_patterns(
        {"e": {**_registry()["effectors"]["e.one"], "target": {"kind": "k", "pattern": pattern}}}, findings
    )
    assert not [f for f in findings if f.startswith("B target-overgrouped")], findings


def test_an_uncompilable_match_pattern_is_a_finding(ce):
    findings: list[str] = []
    ce.check_patterns({"e": {**_registry()["effectors"]["e.one"], "match": ["([unclosed"]}}, findings)
    assert any(f.startswith("B match-uncompilable") for f in findings), findings


def test_an_empty_match_list_is_a_finding(ce):
    """An effector with no match patterns gates nothing while appearing to gate something."""
    findings: list[str] = []
    ce.check_patterns({"e": {**_registry()["effectors"]["e.one"], "match": []}}, findings)
    assert any(f.startswith("B match-empty") for f in findings), findings


# ── the live registry and the ratchet ────────────────────────────────────────────────────────


def test_the_live_registry_has_no_declaration_or_pattern_findings(ce):
    """Classes A and B are held at zero — unlike C they are not baselined, so they fail on sight."""
    bad = [f for f in ce.collect() if f.startswith(("A ", "B "))]
    assert bad == [], bad


def test_the_live_findings_and_the_baseline_agree_exactly(ce):
    """The idempotent fixed point: re-running the predicate changes nothing."""
    assert sorted(ce.collect()) == sorted(ce.read_baseline())


def test_the_baseline_pins_the_sharpest_known_sites(ce):
    """Spot-check the entries whose loss would be the most expensive to notice late."""
    joined = "\n".join(ce.read_baseline())
    for path, verb in [
        ("scripts/apply-visibility.py", "gh repo edit"),  # flips repo visibility
        ("scripts/autonomy-governor.py", "gh pr merge"),  # merge to main auto-deploys
        ("scripts/contributions-organ.py", "gh pr comment"),  # third-party repositories
        ("scripts/creds-hydrate.py", "gh secret set"),  # writes Actions secrets
        ("scripts/reap-remote-branches.py", "gh api -X DELETE"),  # deletes remote refs
        ("organs/representation/representation_substrate.py", "import smtplib"),
    ]:
        assert path in joined and verb in joined, f"{path} `{verb}` fell out of the baseline"


def test_a_new_ungated_sender_fails_the_gate(ce, monkeypatch, capsys):
    """The ratchet itself. Without this the baseline is a list, not a gate."""
    baseline = set(ce.read_baseline())
    monkeypatch.setattr(ce, "read_baseline", lambda: baseline)
    monkeypatch.setattr(ce, "collect", lambda: sorted(baseline) + ["C ungated-effector: scripts/brand-new.py ..."])
    assert ce.main([]) == 1
    assert "brand-new.py" in capsys.readouterr().out


def test_the_unchanged_estate_passes(ce, capsys):
    """Positive control for the line above: today's estate must exit 0, or the gate is unshippable."""
    assert ce.main([]) == 0
    assert "no new findings" in capsys.readouterr().out


def test_a_removed_sender_is_a_note_not_a_failure(ce, monkeypatch, capsys):
    """Fixing a sender must never fail the gate — that would penalise the repair."""
    baseline = set(ce.read_baseline()) | {"C ungated-effector: scripts/already-fixed.py ..."}
    monkeypatch.setattr(ce, "read_baseline", lambda: baseline)
    assert ce.main([]) == 0
    assert "no longer reproduces" in capsys.readouterr().out
