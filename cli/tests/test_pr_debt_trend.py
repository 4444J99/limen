"""IF-AMALGAMATION's probe: is open-PR debt going down, and is anyone still looking?

The registry row carried `probe: null` with an exact reason — "the ideal is a monotonic TREND, not
a level… a real probe needs a committed series, so the debt-trend recorder is this row's next
form." The series was already committed. `gitvs.py` writes `open_pr_count` into
`docs/github-pr-debt-ledger.json` and every write is a commit, so five observations sat in
`git log` for eleven days unread. Nothing had to be built; something had to be READ.

Two properties matter and the second is the one a naive trend predicate gets wrong:

  1. growth is measured across the series, not between two arbitrary points;
  2. STALENESS IS NOT AT-IDEAL. A debt series nobody records is not a debt trend that improved.

The second half of this file covers check-ideal-forms.py's check F, which is the same concern
seen from the enforcing side. The probe makes IF-AMALGAMATION's distance derivable; check F makes
writing one by hand impossible. Without both, the next entry drifts 15x exactly the way this one
did — the registry's header says "there is no field to lie in," and there was one, in the prose.
"""

from __future__ import annotations

import datetime
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pr-debt-trend.py"
LEDGER_REL = "docs/github-pr-debt-ledger.json"


@pytest.fixture()
def mod(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("pr_debt_trend", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["pr_debt_trend"] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "docs").mkdir()
    return tmp_path


def _observe(root: Path, count: int, stamp: str) -> None:
    """One recorded observation — exactly the shape gitvs.py writes."""
    (root / LEDGER_REL).write_text(
        json.dumps({"open_pr_count": count, "generated_at": f"{stamp}T12:00:00Z"}), encoding="utf-8"
    )
    _git(root, "add", LEDGER_REL)
    _git(root, "-c", "user.name=t", "commit", "-q", "-m", f"obs {count}", f"--date={stamp}T12:00:00")


def test_the_series_is_read_out_of_git_not_stored_anywhere(mod, repo):
    """A recorder writing its own series file would be a second copy of a number git versions."""
    for n, day in ((1059, "2026-07-22"), (1111, "2026-07-23"), (1164, "2026-07-25")):
        _observe(repo, n, day)
    rows = mod.series()
    assert [n for _, n, _ in rows] == [1059, 1111, 1164], "oldest first — a series reads forward"
    assert not (repo / "logs").exists(), "nothing is written; the observations were already committed"


def test_growth_is_reported_with_its_sign_and_the_probe_fails_on_it(mod, repo, capsys, monkeypatch):
    monkeypatch.setenv("LIMEN_PR_DEBT_MAX_AGE_DAYS", "3650")  # isolate growth from freshness
    for n, day in ((1059, "2026-07-22"), (1164, "2026-07-25")):
        _observe(repo, n, day)
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "debt_growth=+105" in out
    assert "the debt GREW by 105" in out


def test_a_falling_debt_is_at_ideal(mod, repo, capsys, monkeypatch):
    monkeypatch.setenv("LIMEN_PR_DEBT_MAX_AGE_DAYS", "3650")
    for n, day in ((1164, "2026-07-22"), (900, "2026-07-25")):
        _observe(repo, n, day)
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 0
    assert "debt_growth=-264" in capsys.readouterr().out


def test_silence_is_not_improvement(mod, repo, capsys, monkeypatch):
    """The half that matters. The debt fell, but nobody has looked in a year — that is not a pass.

    Without this the predicate would go GREEN the moment the producer died, which is the exact
    failure mode the ideal exists to prevent: debt accretes fastest when nothing is watching.
    """
    monkeypatch.setenv("LIMEN_PR_DEBT_MAX_AGE_DAYS", "3")
    for n, day in ((1164, "2025-01-01"), (900, "2025-01-04")):
        _observe(repo, n, day)
    _git(repo, "commit", "-q", "--allow-empty", "-m", "much later work")  # moves "today"
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "STALE" in out
    assert "silence is not improvement" in out
    assert mod.PRODUCER in out, "the failure must name the command that ACTUALLY writes the ledger"
    assert "pr-debt" in mod.PRODUCER, "`reconcile` is a dry effector report; it never writes the ledger"
    # ...and the owner of record for the silence. The INVARIANT here is unchanged — a STALE
    # failure must name who owns fixing it — but the ANSWER moved. This used to pin the board
    # task GITVS-UNCAPPED-PR-DEBT-0715, whose whole content was "the producer is wired to
    # nothing". The producer has since been wired to the github-pr-debt sensor, so pinning that
    # task id made this test assert that the thing it wanted fixed had STAYED broken: it went
    # red on the fix rather than on the defect, and took main's suite down with it.
    #
    # So pin the owner through the module constant (it moves with the wiring) and pin the
    # sensor by name (so a producer quietly re-orphaned still fails here, which is the whole
    # point of the row).
    assert mod.PRODUCER_OWNER in out, "the failure must name the owner of record for the silence"
    assert "github-pr-debt" in mod.PRODUCER_OWNER, "the owner is the sensor that records the series"


def test_a_single_observation_is_unmeasurable_and_that_is_a_failure(mod, repo, capsys, monkeypatch):
    """Not 'at ideal' and not drift in the probe — the evidence is absent, which is the state
    this row sat in for eleven days while reporting nothing at all."""
    _observe(repo, 1164, "2026-07-25")
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 1
    assert "UNMEASURABLE" in capsys.readouterr().out


def test_no_ledger_at_all_is_unmeasurable_not_green(mod, repo, capsys, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pr-debt-trend.py", "--check"])
    assert mod.main() == 1
    assert "UNMEASURABLE" in capsys.readouterr().out


def test_an_uncommitted_observation_still_counts(mod, repo, monkeypatch):
    """gitvs writes the file before anything commits it; freshness is about what the PRODUCER did."""
    _observe(repo, 1164, "2026-07-25")
    (repo / LEDGER_REL).write_text(
        json.dumps({"open_pr_count": 800, "generated_at": "2026-08-02T09:00:00Z"}), encoding="utf-8"
    )
    rows = mod.series()
    assert rows[-1] == ("2026-08-02", 800, "worktree")


def test_a_corrupt_snapshot_is_skipped_rather_than_crashing_the_series(mod, repo):
    _observe(repo, 1059, "2026-07-22")
    (repo / LEDGER_REL).write_text("{ not json", encoding="utf-8")
    _git(repo, "add", LEDGER_REL)
    _git(repo, "commit", "-q", "-m", "corrupt")
    _observe(repo, 1164, "2026-07-25")
    assert [n for _, n, _ in mod.series()] == [1059, 1164]


def test_the_registry_row_actually_names_this_script(mod):
    """A probe wired to a script that does not exist is the vacuum wearing a costume.

    check-ideal-forms.py's check C already asserts the file exists; this pins the pairing so a
    rename of either side cannot quietly leave IF-AMALGAMATION unprobed again.
    """
    import yaml

    row = yaml.safe_load((ROOT / "institutio/governance/ideal-forms.yaml").read_text())["ideals"]["IF-AMALGAMATION"]
    probe = row.get("probe")
    assert probe, "IF-AMALGAMATION must not go back to `probe: null`"
    assert "pr-debt-trend.py" in probe["command"]
    assert probe["at_ideal_when"] == "exit_zero"
    assert probe["environment"] == "host", "a shallow CI checkout truncates git history — never read that as at-ideal"


# ── check F: the ledger's Distance stops being a field a human can write in ────────


def _check_ideal_forms(tmp_path: Path, ledger: str, registry: str, capsys) -> tuple[int, str]:
    """Run the real predicate against a synthetic registry+ledger pair.

    In-process with its module globals repointed, not a subprocess: check-ideal-forms.py resolves
    ROOT from its own __file__, so a fixture directory passed as cwd never reaches it — it would
    have silently graded the live ledger and passed for the wrong reason.
    """
    spec = importlib.util.spec_from_file_location("check_ideal_forms", ROOT / "scripts" / "check-ideal-forms.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    reg_path = tmp_path / "ideal-forms.yaml"
    led_path = tmp_path / "IDEAL-FORMS-LEDGER.md"
    reg_path.write_text(registry, encoding="utf-8")
    led_path.write_text(ledger, encoding="utf-8")
    module.ROOT, module.REGISTRY, module.LEDGER = tmp_path, reg_path, led_path
    module.failures.clear()  # module-level accumulators; a second call would inherit the first
    module.notes.clear()

    argv = sys.argv
    sys.argv = ["check-ideal-forms.py"]
    try:
        rc = module.main()
    finally:
        sys.argv = argv
    return rc, capsys.readouterr().out


PROBED_REGISTRY = """
schema_version: 0.1
prose_status_vocabulary:
  at_ideal: [DONE]
  distance_remains: [OPEN]
ideals:
  IF-EXAMPLE:
    ideal: an example ideal
    owner: Claude
    probe:
      command: "true"
      derives: nothing at all
      environment: host
      at_ideal_when: exit_zero
"""


def _ledger(distance_line: str) -> str:
    return f"""# ledger

### IF-EXAMPLE — an example

- **Ideal form:** an example ideal.
{distance_line}
- **Status:** OPEN — still going.
- **Owner:** Claude.
"""


def test_check_f_rejects_a_hand_written_distance_on_a_probed_row(tmp_path, capsys):
    """The field check A forbids in the registry survived in the doc, which A never read."""
    rc, out = _check_ideal_forms(
        tmp_path, _ledger("- **Distance:** 75 open PRs (2026-06-25)."), PROBED_REGISTRY, capsys
    )
    assert rc == 1
    assert "[F] IF-EXAMPLE" in out
    assert "writes a Distance by hand" in out


def test_check_f_accepts_a_derived_distance(tmp_path, capsys):
    line = "- **Distance:** DERIVED — `python3 scripts/check-ideal-forms.py --measure`."
    rc, out = _check_ideal_forms(tmp_path, _ledger(line), PROBED_REGISTRY, capsys)
    assert rc == 0, out


def test_check_f_rejects_a_probed_row_with_no_distance_line_at_all(tmp_path, capsys):
    """Deleting the field is not the fix — a reader must still be told where the number comes from."""
    rc, out = _check_ideal_forms(tmp_path, _ledger("- **Evidence:** things happened."), PROBED_REGISTRY, capsys)
    assert rc == 1
    assert "no `**Distance:**` line" in out


def test_check_f_leaves_unprobed_rows_alone(tmp_path, capsys):
    """A `probe: null` row has no derivation, so prose is all it has — check E counts those."""
    registry = """
schema_version: 0.1
prose_status_vocabulary:
  at_ideal: [DONE]
  distance_remains: [OPEN]
ideals:
  IF-EXAMPLE:
    ideal: an example ideal
    owner: Claude
    probe: null
    probe_absent_reason: nothing can measure this yet
"""
    rc, out = _check_ideal_forms(tmp_path, _ledger("- **Distance:** 75 open PRs (2026-06-25)."), registry, capsys)
    assert rc == 0, out


def test_the_real_ledger_writes_no_distance_by_hand_on_any_probed_row(tmp_path):
    """The live artefact, not a fixture. 12 rows carried one when this check was written."""
    import yaml

    reg = yaml.safe_load((ROOT / "institutio/governance/ideal-forms.yaml").read_text())["ideals"]
    text = (ROOT / "docs/IDEAL-FORMS-LEDGER.md").read_text()
    heads = list(re.finditer(r"^### (IF-[A-Z0-9-]+)", text, re.M))
    spans = [m.start() for m in heads] + [len(text)]
    offenders = []
    for i, m in enumerate(heads):
        ident = m.group(1)
        if not (reg.get(ident) or {}).get("probe"):
            continue
        for line in re.findall(r"^- \*\*Distance[^:]*:\*\*\s*(.+)$", text[spans[i] : spans[i + 1]], re.M):
            if "DERIVED" not in line:
                offenders.append(ident)
    assert not offenders, f"hand-written distances survive on probed rows: {sorted(set(offenders))}"


# ---------------------------------------------------------------------------
# The recorder's change basis and its two clocks. Every test below fails against
# the first cut (#1854). PR #1859 is what the CLOCK half looked like in production:
# a second census fourteen minutes after #1857, under a twenty-hour interval.
# It is NOT evidence for the change-basis half — #1858 opened between those two
# censuses, so the PR set really had moved and 1293 held by coincidence. The
# change-basis defect is proven instead by advancing only the clock fields of the
# real ledger, which is what test_only_the_clock_moving_is_not_an_observation does.
# ---------------------------------------------------------------------------


def _census(count: int, stamp: str, *, untyped: int = 0) -> dict:
    """The shape gitvs.py actually writes — per-PR records carrying their OWN clock fields.

    Those per-PR stamps are the trap. `content_sha256` excludes only the TOP-LEVEL
    `generated_at` (gitvs.py:827), so every one of them is inside the ledger's own hash.
    """
    return {
        "open_pr_count": count,
        "classification_untyped_count": untyped,
        "generated_at": f"{stamp}Z",
        "content_sha256": f"sha-of-{stamp}",
        "pull_requests": [
            {
                "number": i,
                "classification": "active_custody",
                "age_hours": round(100.0 + i + len(stamp), 2),
                "disposition_observed_at": f"{stamp}Z",
            }
            for i in range(count)
        ],
    }


def test_only_the_clock_moving_is_not_an_observation(mod):
    """The defect that shipped noise: two censuses of an identical estate must compare EQUAL."""
    a = json.dumps(_census(3, "2026-08-06T03:17:46"))
    b = json.dumps(_census(3, "2026-08-06T03:31:47"))
    assert a != b, "the raw bytes differ on every run — that is why a byte compare was never an option"
    assert json.loads(a)["content_sha256"] != json.loads(b)["content_sha256"], (
        "and so does the ledger's own content_sha256, because the per-PR stamps are inside it — "
        "which is precisely how judging change by that field opened a PR per census"
    )
    assert mod._stable_digest(a) == mod._stable_digest(b), "nothing but time passed; nothing ships"


def test_the_estate_moving_IS_an_observation(mod):
    """The guard against 'fixing' the above by making the digest insensitive to everything."""
    base = json.dumps(_census(3, "2026-08-06T03:17:46"))
    moved_level = json.dumps(_census(4, "2026-08-06T03:17:46"))
    moved_shape = json.dumps(_census(3, "2026-08-06T03:17:46", untyped=7))
    assert mod._stable_digest(base) != mod._stable_digest(moved_level), "the debt level moved"
    assert mod._stable_digest(base) != mod._stable_digest(moved_shape), (
        "the count held but composition moved — still an observation worth recording"
    )


def test_a_recent_observation_blocks_a_checkout_that_has_never_swept(mod, repo, capsys):
    """The other half of the duplicate. The local receipt is gitignored, so a fresh worktree has
    no clock of its own — and the first cut read ONLY that clock, so it went straight to census."""
    recent = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S")
    (repo / LEDGER_REL).write_text(json.dumps(_census(2, recent)), encoding="utf-8")
    _git(repo, "add", LEDGER_REL)
    _git(repo, "commit", "-q", "-m", "someone else recorded an hour ago")
    assert not (repo / "logs").exists(), "this checkout has never run the sweep"

    assert mod.record(dry_run=True) == 0
    out = capsys.readouterr().out
    assert "not due" in out, "a fresh checkout must still see the clock every checkout shares"
    assert "an observation was recorded" in out


def test_the_digest_is_stable_on_the_REAL_ledger_not_just_a_fixture(mod):
    """The synthetic fixture above proves the idea; this proves it against the shipped artifact.

    A hand-built census carries exactly the volatile fields its author already knew about, so it
    cannot fail the way the real thing does — which is precisely how the original defect survived
    review. This walks the committed ledger (~1,300 records, every field gitvs actually emits),
    advances ONLY the clock, and requires the digest to hold.
    """
    raw = (ROOT / LEDGER_REL).read_text(encoding="utf-8")
    data = json.loads(raw)
    assert len(data["pull_requests"]) > 100, "the real ledger, not a stub"

    def advance_clock(node):
        if isinstance(node, dict):
            out = {}
            for k, v in node.items():
                if k in ("generated_at", "disposition_observed_at"):
                    out[k] = "2099-01-01T00:00:00.000000Z"
                elif k == "age_hours":
                    out[k] = (v + 999.0) if isinstance(v, (int, float)) else v
                elif k == "content_sha256":
                    out[k] = "deadbeef" * 8
                else:
                    out[k] = advance_clock(v)
            return out
        if isinstance(node, list):
            return [advance_clock(v) for v in node]
        return node

    later = json.dumps(advance_clock(data))
    assert raw != later, "the bytes must differ, or this test proves nothing"
    assert data["content_sha256"] != json.loads(later)["content_sha256"], (
        "the ledger's own hash moves on a clock-only change — the defect, pinned against real data"
    )
    assert mod._stable_digest(raw) == mod._stable_digest(later), "only time passed; nothing ships"

    moved = json.loads(raw)
    moved["open_pr_count"] -= 1
    assert mod._stable_digest(raw) != mod._stable_digest(json.dumps(moved)), "one PR left; that ships"


def test_a_stale_shared_clock_does_not_block_a_checkout_that_has_never_swept(mod, repo, capsys):
    """Negative control: the shared clock gates on AGE, not merely on an observation existing."""
    (repo / LEDGER_REL).write_text(json.dumps(_census(2, "2020-01-01T00:00:00")), encoding="utf-8")
    _git(repo, "add", LEDGER_REL)
    _git(repo, "commit", "-q", "-m", "an ancient observation")

    assert mod.record(dry_run=True) == 0
    assert "DUE" in capsys.readouterr().out


def test_a_committed_observation_is_not_re_counted_as_a_worktree_row(mod, repo):
    """The live ledger IS the newest commit's ledger — one observation, one row.

    Found by RUNNING `--series`, not by reading it: the real repo rendered its 1,293-PR ledger
    twice, once as `[05366e12]` dated 2026-08-05 and again as `[worktree]` dated 2026-08-06 with
    `+0`, while `git diff 05366e12 HEAD -- <ledger>` was empty. Same bytes, two rows. Identity was
    "is its date later?", and the two dates came off different clocks: the ledger's UTC
    `generated_at` against git's `--date=short`, which is the author's LOCAL date. Every census
    run after ~20:00 local looked a calendar day newer than the commit that held it.

    It is not cosmetic. `--check` windows back 14 days from the NEWEST row, so the phantom shifted
    the window a day forward and evicted the oldest real observation from the measurement — the
    live repo under-reported growth as +182 from 1111 when the truth was +234 from 1059.
    """
    _observe(repo, 1059, "2026-07-22")
    # A census run late in the local evening: 23:17 local on the 5th is 03:17Z on the 6th.
    (repo / LEDGER_REL).write_text(
        json.dumps({"open_pr_count": 1293, "generated_at": "2026-08-06T03:17:46Z"}), encoding="utf-8"
    )
    _git(repo, "add", LEDGER_REL)
    _git(repo, "-c", "user.name=t", "commit", "-q", "-m", "obs 1293", "--date=2026-08-05T23:17:46")

    rows = mod.series()
    assert [src for _, _, src in rows].count("worktree") == 0, "the live file is that commit, not a second one"
    assert [n for _, n, _ in rows] == [1059, 1293]


def test_a_census_that_writes_garbage_leaves_no_invalid_tracked_file(mod, repo, monkeypatch, capsys):
    """The failure path must restore too — it is the one path where the file is genuinely invalid.

    The first cut restored only when the estate held still, so a census that died mid-write left
    unparseable JSON in a TRACKED ledger for sync-release.sh and capture.sh to sweep into an
    unrelated branch. Driving the failure is what surfaced it; reading the branch did not.
    """
    _observe(repo, 1293, "2026-08-05")
    good = (repo / LEDGER_REL).read_text(encoding="utf-8")
    monkeypatch.setattr(
        mod,
        "PRODUCER_ARGV",
        [sys.executable, "-c", f"open({LEDGER_REL!r}, 'w').write('{{ truncated')"],
    )
    monkeypatch.setenv("LIMEN_PR_DEBT_RECORD_INTERVAL_HOURS", "0")

    assert mod.record(dry_run=False) == 1, "a broken census is a recording failure, never an observation"
    assert (repo / LEDGER_REL).read_text(encoding="utf-8") == good, "a tracked ledger is never left invalid"
    assert "ledger restored" in capsys.readouterr().out
