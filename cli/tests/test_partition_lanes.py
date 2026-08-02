"""A heuristic must never promote work across a partner boundary.

The live defect: ``VIC-CONTRACT-002`` -- a client engagement in a private repo -- reached the top
of the personal auto-dispatch queue because ``_dispatch_focus_bucket`` free-text-matched the word
"blocker" in its prompt boilerplate. ``VIC-CLIENT-STORY-001`` followed on "custody". The repo was
not funded, its labels matched no value label, and its workstream matched no value workstream:
every declared signal said "not mine to auto-dispatch" and an incidental English word overrode all
of them.

The function could not express a refusal. It was pure inclusion -- five independent ways to return
bucket 0 and no way to return "never" -- so the fix is an exclusion axis, not a shorter keyword
list. Pruning "blocker" and "custody" would only move the collision to the next word a client's
text happens to contain.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cli" / "src"))

from limen import partition_lanes as P  # noqa: E402
from limen import dispatch as D  # noqa: E402
from limen import tabularius as T  # noqa: E402
from limen.intake import IntakeContractError  # noqa: E402
from limen.io import load_limen_file  # noqa: E402
from limen.models import Task  # noqa: E402

# The two client engagements. estate.yaml annotates both as a "partner build lane", the
# constellation register attaches a named person to both, and neither appears in value-repos.json
# -- three independent registries agreeing, which is why these are the lanes and not a guess.
VICTOROFF = "4444j99/victoroff-os"
ELEVATE = "4444j99/sovereign-systems--elevate-align"

# The board still writes the PRE-transfer owner for both (the repos moved to 4444J99 in 2026-07).
BOARD_VICTOROFF = "organvm/victoroff-os"


def _task(task_id: str, repo: str, *, context: str = "", labels: list[str] | None = None) -> Task:
    return Task(
        id=task_id,
        title="t",
        repo=repo,
        context=context,
        labels=labels or [],
        target_agent="claude",
        created=date(2026, 8, 2),
    )


# --- the boundary itself ---------------------------------------------------------------------


def test_client_lanes_are_partner_lanes() -> None:
    lanes = P.partner_lanes(ROOT)
    assert VICTOROFF in lanes
    assert ELEVATE in lanes


def test_a_transferred_repo_is_the_same_lane_under_either_owner() -> None:
    """The root cause of the leak: one repository, two names, opposite verdicts.

    estate.yaml keys the protective override on the post-transfer slug, so the pre-transfer slug
    the board still carries misses it and falls through to the ``organvm/**`` glob ->
    ``governed_public``. Every shipped estate predicate read the board's spelling and saw a public
    repo, which is why nothing caught this while estate.yaml:750 had already written the hazard
    down in prose.
    """
    assert P.is_partner_lane(BOARD_VICTOROFF, ROOT)
    assert P.canonical_slug(BOARD_VICTOROFF, ROOT) == VICTOROFF
    assert P.canonical_slug("4444J99/victoroff-os", ROOT) == VICTOROFF


def test_the_operators_own_private_work_is_not_a_partner_lane() -> None:
    """``organvm/domus-genoma`` is operation_private and entirely his.

    Private-class alone is the wrong axis -- it would quarantine 176 rows of his own work. The
    boundary is private AND third-party-attached.
    """
    assert not P.is_partner_lane("organvm/domus-genoma", ROOT)
    assert not P.is_partner_lane("organvm/limen", ROOT)


def test_override_lookup_is_case_insensitive() -> None:
    """The registries disagree on capitalisation and a case-sensitive lookup fails SILENTLY.

    estate.yaml keys the row ``4444J99/victoroff-os``; the board lowercases it. A case-sensitive
    lookup still returns a plausible non-empty lane set -- it just drops exactly the override rows
    that make a lane private. That is the one failure mode this boundary cannot have, so it gets a
    test rather than care.
    """
    for spelling in ("4444J99/victoroff-os", "4444j99/victoroff-os", "4444J99/VICTOROFF-OS"):
        assert P.is_partner_lane(spelling, ROOT), spelling


def test_partner_keywords_exclude_funded_collaborations() -> None:
    """Keywords are leak markers, so a funded product's vocabulary must not be one.

    "chess" and "hokage" belong to a funded collaboration; treating them as partner markers would
    flag every task that merely mentions chess.
    """
    keywords = P.partner_keywords(ROOT)
    assert "victoroff" in keywords
    assert "chess" not in keywords
    assert "hokage" not in keywords


# --- funding is an explicit decision, and it wins -------------------------------------------


def test_funding_exempts_a_partner_lane_from_the_heuristic_veto() -> None:
    """Four of the six partner lanes are funded products with a collaborator attached.

    Vetoing those would starve work ``value-repos.json`` deliberately buys -- 121 rows on
    mirror-mirror alone. Funding is the operator writing the repo down, which is an explicit
    decision and therefore not the accidental overlap this boundary prevents.
    """
    assert P.is_partner_lane("organvm/mirror-mirror", ROOT)
    assert P.is_funded("organvm/mirror-mirror", ROOT)
    assert P.heuristics_may_promote("organvm/mirror-mirror", ROOT)


def test_funding_is_matched_by_tail_so_a_transfer_cannot_defund_a_repo() -> None:
    """The board writes ``organvm/mirror-mirror``; value-repos.json writes ``4444J99/...``."""
    assert P.is_funded("organvm/mirror-mirror", ROOT)
    assert P.is_funded("4444J99/mirror-mirror", ROOT)


def test_unfunded_partner_lanes_are_the_ones_vetoed() -> None:
    for repo in (VICTOROFF, ELEVATE, BOARD_VICTOROFF):
        assert not P.is_funded(repo, ROOT), repo
        assert not P.heuristics_may_promote(repo, ROOT), repo


# --- failure posture ------------------------------------------------------------------------


def test_an_unreadable_registry_stops_heuristics_rather_than_dispatch(tmp_path: Path) -> None:
    """Fail-safe, not fail-dead.

    A guess is exactly what must stop when the boundary is unverifiable. Explicit
    ``value-repos.json`` repo matches are checked before this in ``_dispatch_focus_bucket``, so
    dispatch degrades to explicit-only rather than dying.
    """
    assert P.heuristics_may_promote("organvm/anything", tmp_path) is False


def test_the_predicate_path_raises_so_an_unverifiable_boundary_is_never_green(tmp_path: Path) -> None:
    with pytest.raises(P.PartitionRegistryError):
        P.partner_lanes(tmp_path)


def test_the_checkout_is_located_from_the_module_not_from_the_home_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The boundary must not depend on one machine's ~/Workspace layout.

    A ``~/Workspace/limen`` default passes on the operator host -- which is exactly where it is
    never needed -- and raises on a fresh clone, in CI, and in a worktree. Because an unreadable
    registry vetoes every heuristic, that failure would SILENTLY starve dispatch everywhere else
    while its own tests went green here. So: resolve from ``__file__``, and honour LIMEN_ROOT only
    when it actually holds the registries.
    """
    monkeypatch.delenv("LIMEN_ROOT", raising=False)
    assert P._root() == ROOT
    assert P.is_partner_lane(BOARD_VICTOROFF)

    # A caller legitimately pointing LIMEN_ROOT at a registry-less runtime data dir must not
    # collapse the boundary -- it falls back to the checkout.
    monkeypatch.setenv("LIMEN_ROOT", str(tmp_path))
    assert P._root() == ROOT
    assert P.is_partner_lane(BOARD_VICTOROFF)


def test_repo_tail_survives_every_spelling_of_a_remote() -> None:
    for spelling in (
        "organvm/victoroff-os",
        "4444J99/victoroff-os",
        "git@github.com:4444J99/victoroff-os.git",
        "https://github.com/4444J99/victoroff-os",
        "github.com/4444J99/victoroff-os/",
    ):
        assert P.repo_tail(spelling) == "victoroff-os", spelling
    assert P.repo_tail("") == ""
    assert P.repo_tail(None) == ""


def test_classification_agrees_with_gitvs() -> None:
    """``_classify`` reimplements gitvs' precedence because scripts/ is not importable from the
    installed CLI package. This is the test that keeps the copy honest."""
    import importlib.util

    import yaml

    spec = importlib.util.spec_from_file_location("gitvs_parity", ROOT / "scripts" / "gitvs.py")
    assert spec is not None and spec.loader is not None
    gitvs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gitvs)
    estate = yaml.safe_load((ROOT / "institutio" / "github" / "estate.yaml").read_text())

    for repo in ("4444J99/victoroff-os", "organvm/limen", "organvm/domus-genoma", "organvm/hospes"):
        assert P._classify(repo, estate) == gitvs.classify_repo(repo, estate), repo


# --- the dispatch integration: the actual reported defect ------------------------------------


def test_free_text_no_longer_promotes_a_client_task() -> None:
    """The exact shape of VIC-CONTRACT-002: an unfunded client lane whose prose says "blocker"."""
    task = _task("VIC-CONTRACT-002", BOARD_VICTOROFF, context="surface the blocker before merging")
    value_repos = D._value_tier_repos()

    assert D._dispatch_focus_bucket(task, value_repos) == 1
    assert D.task_passes_value_gate(task, value_repos) is False


def test_custody_no_longer_promotes_a_client_task() -> None:
    task = _task("VIC-CLIENT-STORY-001", BOARD_VICTOROFF, context="chain of custody for the proposal")
    assert D.task_passes_value_gate(task, D._value_tier_repos()) is False


def test_a_value_label_cannot_promote_a_client_task_either() -> None:
    """Every heuristic path is below the veto, not just the free-text one."""
    for labels in ([("revenue")], ["product"], ["value-tier"], ["worktree"]):
        task = _task("VIC-LABELLED", BOARD_VICTOROFF, labels=list(labels))
        assert D._dispatch_focus_bucket(task, D._value_tier_repos()) == 1, labels


def test_an_aw_prefix_cannot_promote_a_client_task() -> None:
    task = _task("AW-VICTOROFF-1", BOARD_VICTOROFF)
    assert D._dispatch_focus_bucket(task, D._value_tier_repos()) == 1


def test_the_veto_survives_the_value_gate_being_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """A confidentiality boundary an env var can switch off is not a boundary.

    ``LIMEN_VALUE_GATE=0`` makes ``task_passes_value_gate`` return True for everything, so the
    veto is checked BEFORE that branch.
    """
    monkeypatch.setenv("LIMEN_VALUE_GATE", "0")
    task = _task("VIC-CONTRACT-002", BOARD_VICTOROFF, context="blocker")
    assert D.task_passes_value_gate(task, D._value_tier_repos()) is False

    mine = _task("LIMEN-1", "organvm/limen", context="blocker")
    assert D.task_passes_value_gate(mine, D._value_tier_repos()) is True


def test_an_empty_value_repos_file_does_not_open_the_boundary() -> None:
    """``_value_gate_configured`` is False for an empty tier, which used to mean "allow all"."""
    task = _task("VIC-CONTRACT-002", BOARD_VICTOROFF, context="blocker")
    assert D.task_passes_value_gate(task, set()) is False


def test_explicit_funding_still_promotes_a_funded_partner_lane() -> None:
    """The exemption has to work through dispatch, not just in the module."""
    value_repos = D._value_tier_repos()
    task = _task("MIRROR-1", "4444J99/mirror-mirror", context="blocker")
    assert D._dispatch_focus_bucket(task, value_repos) == 0
    assert D.task_passes_value_gate(task, value_repos) is True


def test_the_operators_own_work_is_untouched_by_the_veto() -> None:
    value_repos = D._value_tier_repos()
    for repo in ("organvm/limen", "organvm/domus-genoma", "organvm/peer-audited--behavioral-blockchain"):
        task = _task("MINE-1", repo, context="surface the blocker")
        assert D._dispatch_focus_bucket(task, value_repos) == 0, repo
        assert D.task_passes_value_gate(task, value_repos) is True, repo


def test_sort_never_ranks_a_client_task_into_the_candidate_list() -> None:
    """End to end at the selection surface dispatch actually calls."""
    value_repos = D._value_tier_repos()
    client = _task("VIC-CONTRACT-002", BOARD_VICTOROFF, context="blocker")
    mine = _task("LIMEN-1", "organvm/limen", context="blocker")

    ranked = D.sort_value_gate_candidates([client, mine], value_repos)

    assert [t.id for t in ranked] == ["LIMEN-1"]


@pytest.mark.parametrize("value_repos", [set(), {"organvm/limen"}])
def test_sort_holds_the_boundary_whether_or_not_the_value_gate_is_configured(
    value_repos: set[str],
) -> None:
    """The hole CI found that this host could not: an UNCONFIGURED gate readmitted the veto.

    ``sort_value_gate_candidates`` filtered on ``task_passes_value_gate`` and then, one line later,
    did ``gated = list(candidates)`` when ``_value_gate_configured`` was False -- discarding the
    veto it had just computed.

    It was invisible locally because ``_value_tier_repos()`` defaults its file to
    ``~/Workspace/limen/value-repos.json``. That path resolves on the operator's laptop, so the
    tier is non-empty, the gate reads CONFIGURED, and the filter survives. On a CI runner or any
    fresh clone it does not resolve, the tier is empty, and client work walked back in. Both
    branches are parametrized here so neither host shape can pass alone.
    """
    client = _task("VIC-CONTRACT-002", BOARD_VICTOROFF, context="blocker")
    mine = _task("LIMEN-1", "organvm/limen", context="blocker")

    ranked = D.sort_value_gate_candidates([client, mine], value_repos)

    assert [t.id for t in ranked] == ["LIMEN-1"]


def test_disk_pressure_focus_cannot_readmit_a_client_task() -> None:
    """The other branch that re-derives its own list from `candidates`-adjacent state.

    Under disk pressure the sort narrows to bucket 0. A vetoed task is bucket 1, so it can only
    ever be dropped further -- but the assertion is cheap and the branch is exactly the shape that
    produced the readmission bug, so it is pinned rather than reasoned about.
    """
    client = _task("VIC-CONTRACT-002", BOARD_VICTOROFF, context="blocker")
    mine = _task("LIMEN-1", "organvm/limen", context="blocker")

    for repos in (set(), D._value_tier_repos()):
        ranked = D.sort_value_gate_candidates([client, mine], repos, disk_pressure=True)
        assert [t.id for t in ranked] == ["LIMEN-1"], repos


# --- the publication half: the board must not ACCEPT what it would then publish ----------------


def _valid_intake_fields(task_id: str, repo: str) -> dict[str, object]:
    """A task that satisfies every OTHER intake requirement, so the partner refusal is isolated."""
    return {
        "id": task_id,
        "title": "t",
        "repo": repo,
        "context": "",
        "target_agent": "claude",
        "created": "2026-08-02",
        "predicate": "scripts/verify-scoped.sh",
        "receipt_target": f"github:{repo}:pull-request:{task_id}",
        # work-loan underwriting, so submit_task_upsert reaches the board-write surface and the
        # refusal is what rejects the task -- not an incidental earlier validation failure.
        "source_origin": "system_debt",
        "horizon": "present",
        "value_case": "isolate the partner boundary under test",
    }


def test_a_new_client_task_cannot_enter_the_board_at_all() -> None:
    """The board-write surface is the last point where the exposure is still preventable.

    TABVLARIVS's projection is written to organvm/limen on `tabularius/board-projection`, that head
    enters the merge queue, and it lands on `main` -- a PUBLIC repo. Accepting a client engagement
    here IS publishing it, and nothing downstream can un-publish it.
    """
    for repo in (BOARD_VICTOROFF, VICTOROFF, ELEVATE):
        with pytest.raises(IntakeContractError, match="unfunded partner lane"):
            T.refuse_unfunded_partner_lane(repo, "VIC-NEW-1")


def test_the_refusal_reaches_the_producer_seam_every_generator_uses(tmp_path: Path) -> None:
    """submit_task_upsert is the documented conversion target for every writer that used to
    load -> extend -> save_limen_file, so the refusal has to bite THERE, not only in a helper."""
    with pytest.raises(IntakeContractError, match="unfunded partner lane"):
        T.submit_task_upsert(tmp_path, _valid_intake_fields("VIC-NEW-2", BOARD_VICTOROFF), agent="claude")
    assert not list(tmp_path.rglob("*.json")), "a refused ticket must not be written"


def test_the_refusal_also_covers_the_raw_ticket_side_door(tmp_path: Path) -> None:
    """submit_task_upsert is not the only way to reach submit_ticket, so the guard sits on
    submit_ticket itself -- the module's own docstring calls it the only board-write surface."""
    ticket = T.Ticket(
        ticket_id=T.new_ticket_id("s", datetime(2026, 8, 2, tzinfo=timezone.utc)),
        timestamp=datetime(2026, 8, 2, tzinfo=timezone.utc),
        agent="claude",
        session_id="s",
        intent=T.INTENT_UPSERT,
        task_id="VIC-RAW-1",
        patch={"id": "VIC-RAW-1", "repo": BOARD_VICTOROFF},
        precondition={"absent": True},
    )
    with pytest.raises(IntakeContractError, match="unfunded partner lane"):
        T.submit_ticket(tmp_path, ticket)


def test_a_transition_on_an_existing_client_row_is_not_refused(tmp_path: Path) -> None:
    """CREATES only. 411 partner-attributed rows are already on the board; refusing their
    status/result transitions would strand them mid-lifecycle with no way to close them."""
    path = T.submit_task_status(tmp_path, "VIC-CONTRACT-002", status="done", agent="claude")
    assert path.exists()


def test_own_work_and_funded_collaborations_are_never_refused() -> None:
    """The refusal must not become a general-purpose intake narrowing."""
    for repo in ("organvm/limen", "organvm/domus-genoma", "4444J99/mirror-mirror", None, ""):
        T.refuse_unfunded_partner_lane(repo, "OK-1")  # must not raise


def test_the_live_board_still_loads_end_to_end() -> None:
    """The integration assertion behind the previous test: the real 5.6MB board, really loaded."""
    board = ROOT / "tasks.yaml"
    if not board.exists():  # a clone without the projection cache
        pytest.skip("no local board projection")
    loaded = load_limen_file(board)
    assert len(loaded.tasks) > 0
