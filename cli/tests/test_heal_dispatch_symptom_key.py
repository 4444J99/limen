"""heal-dispatch symptom-key dedup: two invocations for the same repo+symptom must yield ONE task.

The keyed HEAL-<repo>-<symptom> singleton (ensure_heal_singleton / heal_task_key) mirrors the
check-main-green._emit_heal_task pattern: if the singleton is already active, the second call
converges silently and returns None; if it was done/archived, it reopens the SAME id.

Tests work against a temp tasks.yaml, never the live board (dispatch is paused in AUTONOMY_PAUSED).
"""

import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "heal-dispatch.py"
_spec = importlib.util.spec_from_file_location("heal_dispatch", _SCRIPT)
_hd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_hd)


def _now():
    return datetime.now(timezone.utc)


def _make_lf(*tasks):
    """Minimal LimenFile-shaped namespace for unit tests (no disk I/O required)."""
    return SimpleNamespace(tasks=list(tasks))


def _task(tid, status="open", repo="organvm/limen"):
    """Minimal Task object for testing (uses real Task model via heal_dispatch imports)."""
    from limen.models import Task  # noqa: PLC0415

    return Task(
        id=tid,
        title=f"task {tid}",
        repo=repo,
        target_agent="codex",
        status=status,
        created="2026-07-15",
        dispatch_log=[],
    )


# ─── heal_task_key ────────────────────────────────────────────────────


def test_heal_task_key_slugifies_repo():
    key = _hd.heal_task_key("organvm/limen", "dispatched-no-pr")
    assert key == "HEAL-organvm-limen-dispatched-no-pr"


def test_heal_task_key_stable():
    """Same inputs always produce the same key (deterministic)."""
    k1 = _hd.heal_task_key("organvm/limen", "closed-unmerged")
    k2 = _hd.heal_task_key("organvm/limen", "closed-unmerged")
    assert k1 == k2


# ─── ensure_heal_singleton dedup ─────────────────────────────────────


def test_two_calls_same_repo_symptom_yield_one_task():
    """Two invocations for the same repo+symptom must produce exactly ONE singleton task."""
    lf = _make_lf()
    now = _now()

    id1 = _hd.ensure_heal_singleton(lf, "organvm/limen", "dispatched-no-pr", "title", "context", now)
    id2 = _hd.ensure_heal_singleton(lf, "organvm/limen", "dispatched-no-pr", "title", "context", now)

    assert id1 is not None, "first call must return the singleton id"
    assert id2 is None, "second call must return None (already active, converge silently)"
    matching = [t for t in lf.tasks if t.id == id1]
    assert len(matching) == 1, f"exactly one singleton task; got {len(matching)}"


def test_different_symptoms_yield_different_tasks():
    """Distinct symptoms must produce separate singletons."""
    lf = _make_lf()
    now = _now()

    id1 = _hd.ensure_heal_singleton(lf, "organvm/limen", "dispatched-no-pr", "t", "c", now)
    id2 = _hd.ensure_heal_singleton(lf, "organvm/limen", "closed-unmerged", "t", "c", now)

    assert id1 != id2
    assert len(lf.tasks) == 2


def test_done_singleton_is_reopened():
    """If the singleton exists but is done, the second call reopens it (recurrence visible)."""
    lf = _make_lf()
    now = _now()

    # First call: creates it
    _hd.ensure_heal_singleton(lf, "organvm/limen", "dispatched-no-pr", "t", "c", now)
    # Simulate it being done
    singleton = next(t for t in lf.tasks if t.id == _hd.heal_task_key("organvm/limen", "dispatched-no-pr"))
    singleton.status = "done"

    # Second call: should reopen
    tid = _hd.ensure_heal_singleton(lf, "organvm/limen", "dispatched-no-pr", "new title", "new context", now)
    assert tid is not None, "reopening a done singleton must return the id"
    assert singleton.status == "open"
    assert singleton.title == "new title"


def test_active_states_prevent_duplicate_creation():
    """Every _ACTIVE_STATES value suppresses a second singleton creation."""
    for status in ("open", "dispatched", "in_progress", "needs_human", "failed_blocked"):
        lf = _make_lf()
        now = _now()
        _hd.ensure_heal_singleton(lf, "organvm/limen", "no-pr", "t", "c", now)
        # Force the status
        t = lf.tasks[0]
        t.status = status
        result = _hd.ensure_heal_singleton(lf, "organvm/limen", "no-pr", "t", "c", now)
        assert result is None, f"expected None for active status={status!r}, got {result!r}"
        assert len(lf.tasks) == 1, f"no duplicate created for status={status!r}"
