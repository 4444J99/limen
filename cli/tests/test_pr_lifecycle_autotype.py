"""Hermetic tests for the continuous PR auto-typing rung (no network, fake gh)."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "pr-lifecycle-autotype.py"


def _load():
    spec = importlib.util.spec_from_file_location("pr_lifecycle_autotype_uut", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


class _R:
    def __init__(self, out: str = "", returncode: int = 0, err: str = ""):
        self.returncode = returncode
        self.stdout = out
        self.stderr = err


def _search_row(repo: str, num: int, labels: list[str] | None = None):
    return {
        "number": num,
        "repository": {"nameWithOwner": repo},
        "labels": [{"name": name} for name in (labels or [])],
    }


def _view(state: str = "OPEN", labels: list[str] | None = None, login: str = "dependabot"):
    return {
        "state": state,
        "labels": [{"name": name} for name in (labels or [])],
        "author": {"login": login},
    }


def _make_gh(search_rows, views, calls, all_rows=None, search_result=None, edit_result=None):
    """Route the module's gh() calls.

    The authored search (`--author`) yields the mechanical cohort; the authorless one yields
    `all_rows`, so `human_unlabeled_count`'s set subtraction is actually exercisable rather
    than structurally always-zero. `views` maps (repo, num) → payload or an _R for errors.
    """

    def fake(args, timeout=60):
        calls.append(list(args))
        if args[0] == "search":
            if search_result is not None:
                return search_result
            if "--author" in args:
                return _R(json.dumps(search_rows))
            return _R(json.dumps(search_rows if all_rows is None else all_rows))
        if args[:2] == ["pr", "view"]:
            key = (args[args.index("-R") + 1], int(args[2]))
            payload = views.get(key)
            if isinstance(payload, _R):
                return payload
            return _R(json.dumps(payload))
        if args[:2] == ["pr", "edit"]:
            return edit_result if edit_result is not None else _R()
        return _R()

    return fake


def _configure(
    mod,
    monkeypatch,
    tmp_path,
    *,
    search_rows,
    views,
    argv,
    pause=False,
    ensure_label=None,
    archived=(),
    all_rows=None,
    search_result=None,
    edit_result=None,
):
    calls: list[list[str]] = []
    monkeypatch.setattr(mod, "gh", _make_gh(search_rows, views, calls, all_rows, search_result, edit_result))
    monkeypatch.setattr(mod, "RECEIPTS", tmp_path / "receipts.jsonl")
    marker = tmp_path / "AUTONOMY_PAUSED"
    if pause:
        marker.write_text("paused")
    monkeypatch.setattr(mod, "PAUSE_MARKER", marker)
    monkeypatch.setattr(mod.ESTATE, "_ensure_label", ensure_label or (lambda repo, disposition: None))
    # _repo_is_archived shells out through BASE._run_gh, which the module's gh() seam does NOT
    # cover — leave it real and every test spawns `gh repo view`. Hermeticity is the point.
    archived_set = set(archived)
    monkeypatch.setattr(mod.ESTATE, "_repo_is_archived", lambda repo: repo in archived_set)
    # owners() reads institutio/github/estate.yaml; pin it so cohort tests are about the cohort.
    monkeypatch.setattr(mod, "owners", lambda: ["o"])
    monkeypatch.delenv("LIMEN_PR_AUTOTYPE_APPLY", raising=False)
    monkeypatch.setattr(sys, "argv", ["pr-lifecycle-autotype.py", *argv])
    return calls


def _receipts(tmp_path):
    path = tmp_path / "receipts.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _edits(calls):
    return [c for c in calls if c[:2] == ["pr", "edit"]]


# ---------------------------------------------------------------- scope: the predicate's scope


def test_owners_derive_from_the_estate_authority_not_a_narrower_literal(monkeypatch):
    """The rung must measure what gitvs.py pr-debt --check measures. A two-owner literal would
    leave most of the arrival stream unread while printing a confident cohort=0."""
    mod = _load()
    # An ambient override would make both sides agree trivially and could shrink the set below
    # the fallback — pin the derivation to the registry so the assertion means what it says.
    monkeypatch.delenv("LIMEN_GITVS_OWNERS", raising=False)
    derived = mod.owners()
    authoritative = [str(o) for o in mod.GITVS.owners(mod.GITVS.load_estate())]
    assert set(derived) == set(authoritative)
    assert len(derived) > len(mod.FALLBACK_OWNERS)


def test_owner_derivation_failure_is_loud_and_falls_back(monkeypatch, capsys):
    mod = _load()
    monkeypatch.setattr(mod.GITVS, "load_estate", lambda: (_ for _ in ()).throw(OSError("estate gone")))
    got = mod.owners()
    assert got == list(mod.FALLBACK_OWNERS)
    out = capsys.readouterr().out
    assert "estate owner derivation FAILED" in out
    assert "NARROWER" in out


# ---------------------------------------------------------------- the query


def test_query_carries_the_separator_and_excludes_archived_repos():
    mod = _load()
    rows = [
        _search_row("o/r", 1),
        _search_row("o/r", 2, labels=["lifecycle:blocked"]),  # search-index lag
    ]
    calls: list[list[str]] = []
    got, ok = mod.enumerate_untyped(["app/dependabot"], ["o"], _make_gh(rows, {}, calls), max_total=50)
    assert ok is True
    assert got == [("o/r", 1)]
    search = calls[0]
    # Without the "--" separator gh parses "-label:…" as an unknown flag and errors, which the
    # fail-open turns into a silent empty cohort — the separator must precede every negation.
    assert "--" in search
    assert search.index("--") < search.index("-label:lifecycle:blocked")
    # Archived repos are read-only and already census-typed; excluded at the source so they
    # cannot sit in the cohort forever consuming the effect budget.
    assert "archived:false" in search
    assert search.index("--") < search.index("archived:false")


# ---------------------------------------------------------------- absence is never health


def test_search_read_failure_is_loud_nonzero_and_receipted(monkeypatch, tmp_path, capsys):
    """A dead token must not print what a drained estate prints. The arming lever's review step
    reads this ledger; an empty file would read as 'nothing needed typing'."""
    mod = _load()
    calls = _configure(
        mod,
        monkeypatch,
        tmp_path,
        search_rows=[],
        views={},
        argv=["--apply"],
        search_result=_R("", returncode=1, err="gh: rate limit exceeded"),
    )
    assert mod.main() == 1
    out = capsys.readouterr().out
    assert "cohort=UNKNOWN" in out
    assert "cohort=0" not in out
    assert _edits(calls) == []
    rows = _receipts(tmp_path)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "read-failed"
    assert rows[0]["outcome"] == "read-failed"


def test_human_count_reports_unknown_when_only_its_search_fails(monkeypatch, tmp_path, capsys):
    mod = _load()
    seen: list[list[str]] = []

    def gh_fn(args, timeout=60):
        seen.append(list(args))
        if args[0] == "search":
            if "--author" in args:
                return _R(json.dumps([_search_row("o/r", 5)]))
            return _R("", returncode=1, err="gh: boom")  # only the authorless search fails
        if args[:2] == ["pr", "view"]:
            return _R(json.dumps(_view()))
        return _R()

    _configure(mod, monkeypatch, tmp_path, search_rows=[], views={}, argv=[])
    monkeypatch.setattr(mod, "gh", gh_fn)
    assert mod.main() == 0
    out = capsys.readouterr().out
    assert "human-residual count UNKNOWN" in out
    assert "human_unlabeled=UNKNOWN" in out


def test_human_count_subtracts_the_mechanical_cohort(monkeypatch, tmp_path, capsys):
    mod = _load()
    _configure(
        mod,
        monkeypatch,
        tmp_path,
        search_rows=[_search_row("o/r", 1)],
        all_rows=[_search_row("o/r", 1), _search_row("o/r", 2), _search_row("o/r", 3)],
        views={("o/r", 1): _view()},
        argv=[],
    )
    assert mod.main() == 0
    assert "human_unlabeled=2" in capsys.readouterr().out


def test_scan_cap_truncation_is_announced(monkeypatch, tmp_path, capsys):
    mod = _load()
    rows = [_search_row("o/r", n) for n in range(1, 4)]
    calls: list[list[str]] = []
    got, ok = mod.enumerate_untyped(["app/dependabot"], ["o"], _make_gh(rows, {}, calls), max_total=3)
    assert ok is True and len(got) == 3
    assert "hit the 3-row scan cap" in capsys.readouterr().out


# ---------------------------------------------------------------- transport errors never abort


def test_gh_converts_transport_errors_into_named_failures(monkeypatch):
    """subprocess.run(timeout=) raises TimeoutExpired; unconverted it escapes _current and kills
    the run mid-cohort — after a label landed but before its receipt was written."""
    mod = _load()

    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="gh", timeout=1)

    monkeypatch.setattr(mod.subprocess, "run", boom)
    r = mod.gh(["pr", "view", "1"])
    assert r.returncode != 0
    assert "TimeoutExpired" in r.stderr

    def missing(*a, **k):
        raise OSError("No such file or directory: 'gh'")

    monkeypatch.setattr(mod.subprocess, "run", missing)
    assert mod.gh(["pr", "view", "1"]).returncode != 0


def test_view_failure_is_a_per_item_skip_not_a_batch_abort(monkeypatch, tmp_path):
    mod = _load()
    rows = [_search_row("o/r", n) for n in (1, 2)]
    views = {("o/r", 1): _R("", returncode=124, err="gh transport: TimeoutExpired"), ("o/r", 2): _view()}
    calls = _configure(mod, monkeypatch, tmp_path, search_rows=rows, views=views, argv=["--apply"])
    assert mod.main() == 0
    receipts = {r["pr"]: r for r in _receipts(tmp_path)}
    assert receipts[1]["reason"] == "gh-view-failed"
    assert receipts[2]["outcome"] == "typed"
    assert len(_edits(calls)) == 1


def test_label_ensure_non_manifest_error_is_item_scoped(monkeypatch, tmp_path):
    """_ensure_label reaches gh through BASE._run_gh, so it can raise JSONDecodeError or a
    subprocess timeout — not only ManifestError. A narrow catch killed the run with 0 receipts."""
    mod = _load()

    def flaky_ensure(repo, disposition):
        if repo == "o/bad":
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    rows = [_search_row("o/bad", 1), _search_row("o/good", 2)]
    views = {("o/bad", 1): _view(), ("o/good", 2): _view()}
    calls = _configure(
        mod, monkeypatch, tmp_path, search_rows=rows, views=views, argv=["--apply"], ensure_label=flaky_ensure
    )
    assert mod.main() == 0
    receipts = {r["repo"]: r for r in _receipts(tmp_path)}
    assert receipts["o/bad"]["outcome"].startswith("label-ensure-failed")
    assert "ValueError" in receipts["o/bad"]["outcome"]
    assert receipts["o/good"]["outcome"] == "typed"
    assert len(_edits(calls)) == 1


def test_failed_edit_is_not_counted_as_typed(monkeypatch, tmp_path, capsys):
    mod = _load()
    calls = _configure(
        mod,
        monkeypatch,
        tmp_path,
        search_rows=[_search_row("o/r", 1)],
        views={("o/r", 1): _view()},
        argv=["--apply"],
        edit_result=_R("", returncode=1, err="label write refused"),
    )
    assert mod.main() == 0
    assert len(_edits(calls)) == 1
    rows = _receipts(tmp_path)
    assert rows[0]["outcome"].startswith("edit-failed")
    assert "typed=0" in capsys.readouterr().out


# ---------------------------------------------------------------- budgets


def test_limit_bounds_effects_not_iterations(monkeypatch, tmp_path, capsys):
    """A candidate that can never be typed must not consume the budget a real arrival needs —
    and because the cohort is sorted, it would consume the SAME leading slot every visit."""
    mod = _load()
    rows = [_search_row("o/aaa", 1), _search_row("o/bbb", 2), _search_row("o/ccc", 3)]
    views = {("o/aaa", 1): _view(), ("o/bbb", 2): _view(), ("o/ccc", 3): _view()}
    calls = _configure(
        mod,
        monkeypatch,
        tmp_path,
        search_rows=rows,
        views=views,
        argv=["--apply", "--limit", "1"],
        archived=["o/aaa"],  # permanently unresolvable, sorts first
    )
    assert mod.main() == 0
    # The old cohort[:limit] slice spent the single slot on o/aaa and typed nothing at all.
    edits = _edits(calls)
    assert len(edits) == 1
    assert "o/bbb" in edits[0]
    out = capsys.readouterr().out
    assert "typed=1" in out
    assert "examined=2" in out
    assert "residual=1" in out  # truncation is announced, never silent


def test_dry_run_default_makes_zero_mutations_and_full_receipts(monkeypatch, tmp_path):
    mod = _load()
    calls = _configure(
        mod, monkeypatch, tmp_path, search_rows=[_search_row("o/r", 7)], views={("o/r", 7): _view()}, argv=[]
    )
    assert mod.main() == 0
    assert _edits(calls) == []
    rows = _receipts(tmp_path)
    assert len(rows) == 1
    assert rows[0]["verdict"] == "type"
    assert rows[0]["applied"] is False
    assert rows[0]["outcome"] == "dry-run"
    # the whole row shape a downstream reader depends on
    assert set(rows[0]) == {"ts", "repo", "pr", "author", "verdict", "reason", "applied", "outcome", "paused"}
    assert rows[0]["ts"].endswith("+00:00")


def test_apply_types_untyped_and_respects_limit(monkeypatch, tmp_path):
    mod = _load()
    rows = [_search_row("o/r", n) for n in (1, 2, 3)]
    views = {("o/r", n): _view() for n in (1, 2, 3)}
    calls = _configure(mod, monkeypatch, tmp_path, search_rows=rows, views=views, argv=["--apply", "--limit", "2"])
    assert mod.main() == 0
    edits = _edits(calls)
    assert len(edits) == 2
    assert all("--add-label" in c and "lifecycle:blocked" in c for c in edits)
    assert [r["outcome"] for r in _receipts(tmp_path)] == ["typed", "typed"]


# ---------------------------------------------------------------- rails


def test_per_item_drift_skips_never_batch_abort(monkeypatch, tmp_path):
    mod = _load()
    rows = [_search_row("o/r", n) for n in (1, 2, 3)]
    views = {
        ("o/r", 1): _view(state="CLOSED"),
        ("o/r", 2): _view(labels=["lifecycle:active-human"]),
        ("o/r", 3): _view(),
    }
    calls = _configure(mod, monkeypatch, tmp_path, search_rows=rows, views=views, argv=["--apply"])
    assert mod.main() == 0
    receipts = {r["pr"]: r for r in _receipts(tmp_path)}
    assert receipts[1]["reason"] == "closed-since-search"
    assert receipts[2]["reason"] == "labeled-since-search"
    assert receipts[3]["outcome"] == "typed"
    assert len(_edits(calls)) == 1


def test_never_types_human_authored(monkeypatch, tmp_path):
    mod = _load()
    calls = _configure(
        mod,
        monkeypatch,
        tmp_path,
        search_rows=[_search_row("o/r", 9)],
        views={("o/r", 9): _view(login="some-human")},
        argv=["--apply"],
    )
    assert mod.main() == 0
    assert _edits(calls) == []
    rows = _receipts(tmp_path)
    assert rows[0]["reason"] == "not-mechanical"
    assert rows[0]["author"] == "some-human"


def test_archived_repo_is_skipped_without_a_view_or_an_edit(monkeypatch, tmp_path):
    """Effect-time rail behind the query's archived:false — the guarantee must not rest on one
    read's behaviour. An archived repo is read-only AND already census-typed."""
    mod = _load()
    rows = [_search_row("o/frozen", 1), _search_row("o/live", 2)]
    views = {("o/frozen", 1): _view(), ("o/live", 2): _view()}
    calls = _configure(
        mod, monkeypatch, tmp_path, search_rows=rows, views=views, argv=["--apply"], archived=["o/frozen"]
    )
    assert mod.main() == 0
    receipts = {r["repo"]: r for r in _receipts(tmp_path)}
    assert receipts["o/frozen"]["verdict"] == "skip"
    assert receipts["o/frozen"]["reason"].startswith("repo-archived-immutable")
    assert receipts["o/live"]["outcome"] == "typed"
    # The archived candidate costs no gh calls at all beyond the search — no view, no edit.
    assert [c for c in calls if c[:2] == ["pr", "view"] and "o/frozen" in c] == []
    assert len(_edits(calls)) == 1


def test_pause_marker_forces_dry_run_even_when_armed(monkeypatch, tmp_path):
    mod = _load()
    calls = _configure(
        mod,
        monkeypatch,
        tmp_path,
        search_rows=[_search_row("o/r", 4)],
        views={("o/r", 4): _view()},
        argv=["--apply"],
        pause=True,
    )
    assert mod.main() == 0
    assert _edits(calls) == []
    rows = _receipts(tmp_path)
    assert rows[0]["paused"] is True
    assert rows[0]["outcome"] == "dry-run"


def test_env_valve_arms_and_explicit_dry_run_overrides_it(monkeypatch, tmp_path):
    """The env path is how the BEAT arms this rung — the flag path is only how a human does."""
    mod = _load()
    calls = _configure(
        mod, monkeypatch, tmp_path, search_rows=[_search_row("o/r", 1)], views={("o/r", 1): _view()}, argv=[]
    )
    monkeypatch.setenv("LIMEN_PR_AUTOTYPE_APPLY", "1")
    assert mod.main() == 0
    assert len(_edits(calls)) == 1

    calls2 = _configure(
        mod,
        monkeypatch,
        tmp_path,
        search_rows=[_search_row("o/r", 1)],
        views={("o/r", 1): _view()},
        argv=["--dry-run"],
    )
    monkeypatch.setenv("LIMEN_PR_AUTOTYPE_APPLY", "1")
    assert mod.main() == 0
    assert _edits(calls2) == []


def test_gate_open_requires_the_strict_string_one(monkeypatch, tmp_path):
    mod = _load()
    calls = _configure(
        mod, monkeypatch, tmp_path, search_rows=[_search_row("o/r", 1)], views={("o/r", 1): _view()}, argv=[]
    )
    monkeypatch.setenv("LIMEN_PR_AUTOTYPE_APPLY", "true")
    assert mod.main() == 0
    assert _edits(calls) == []
