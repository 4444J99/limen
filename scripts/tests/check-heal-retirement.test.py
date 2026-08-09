#!/usr/bin/env python3
"""Hermetic fixtures for check-heal-retirement.py — no network, no live board.

The first cut of this suite ran the predicate against the LIVE board and asserted exit 0. That is
not a test: it cannot fail for a code reason, it cannot pass until the whole backlog is drained,
and with --quiet it printed nothing at all — which is exactly how the gate landed red in CI with
no diagnostic (PR #2144, pr-gate run 31310529140).

What matters here is the inference the predicate makes: "this PR is absent from the open set,
therefore it is closed, therefore retire the task." Every fixture below attacks the conditions
under which that inference is unsound.
"""

from __future__ import annotations

import importlib.util
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("chr_", ROOT / "scripts" / "check-heal-retirement.py")
assert SPEC and SPEC.loader
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

failures: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  {'ok  ' if cond else 'FAIL'} {name}")
    if not cond:
        failures.append(name)


def task(tid: str, status: str, repo: str = "organvm/limen"):
    return SimpleNamespace(id=tid, status=status, repo=repo)


# --- which tasks count as active -------------------------------------------------------------
tasks = [
    task("HEAL-cifix-organvm-limen-101", "open"),
    task("HEAL-rebase-organvm-limen-102", "failed_blocked"),
    task("HEAL-rebase-stale-organvm-limen-103", "open"),  # excluded by name
    task("HEAL-cifix-organvm-limen-104", "done"),  # excluded by status
    task("GH-organvm-limen-105", "open"),  # not a HEAL task
]
active = {t.id for t in m.active_heal_tasks(tasks)}
check(
    "active set takes open and failed_blocked HEAL tasks",
    active == {"HEAL-cifix-organvm-limen-101", "HEAL-rebase-organvm-limen-102"},
)
check("HEAL-rebase-stale-* is excluded", "HEAL-rebase-stale-organvm-limen-103" not in active)
check("a done HEAL task is excluded", "HEAL-cifix-organvm-limen-104" not in active)
check("a non-HEAL task is excluded", "GH-organvm-limen-105" not in active)

# The predicate and the repair must agree on "active", or the gate has a hole (a status self-heal
# retires but the gate never inspects) or a permanent red (the reverse).
heal_src = (ROOT / "scripts" / "self-heal.py").read_text(encoding="utf-8")
check(
    "ACTIVE_STATUSES matches self-heal.py's retirement loop",
    all(f'"{s}"' in heal_src for s in m.ACTIVE_STATUSES) and len(m.ACTIVE_STATUSES) == 6,
)

# --- the core inference ------------------------------------------------------------------------
complete = {("organvm/limen", 101)}  # 101 open, 102 not
v = m.find_violations(tasks, complete)
check(
    "flags an active task whose PR is absent from a COMPLETE set",
    {x[0] for x in v} == {"HEAL-rebase-organvm-limen-102"},
)
check("leaves alone an active task whose PR is open", "HEAL-cifix-organvm-limen-101" not in {x[0] for x in v})

other_repo = [task("HEAL-cifix-organvm-other-99", "open", repo="organvm/other")]
check("scoped to organvm/limen", m.find_violations(other_repo, set()) == [])

# --- UNSOUND-INFERENCE GUARDS: the reason this gate can be trusted at all ----------------------
# The enumeration is the whole basis of the "absent ⟹ closed ⟹ retire" inference, so every way it
# can come back incomplete must be distinguishable from "complete and empty". These fixtures drive
# open_pr_set() through a fake `gh`, asserting on the STATE it reports rather than on gh itself.


class FakeRun:
    def __init__(self, code, out):
        self.returncode, self.stdout, self.stderr = code, out, ""


def fake_gh(pages):
    """pages: list of per-page JSON payloads, consumed in order."""
    seq = list(pages)

    def run(argv, **kw):
        return seq.pop(0) if seq else FakeRun(0, "[]")

    return run


def page(n, start=0):
    return FakeRun(0, json.dumps([{"number": start + i} for i in range(n)]))


# A gh failure must mean "I could not look", never "every PR is closed" — otherwise one auth blip
# or a spent pool retires the entire backlog. Measured on main 2026-08-09: that exact empty result
# was reported as "51 active HEAL tasks name closed/merged PRs", none of which was closed.
m.subprocess.run = fake_gh([FakeRun(1, "")])
_, state = m.open_pr_set()
check("REGRESSION: a failed gh call is UNREACHABLE, not 'everything closed'", state == "UNREACHABLE")

m.subprocess.run = fake_gh([FakeRun(0, "not json")])
_, state = m.open_pr_set()
check("REGRESSION: unparseable output is UNREACHABLE, not empty", state == "UNREACHABLE")

m.subprocess.run = fake_gh([FakeRun(0, "[]")])
_, state = m.open_pr_set()
check("REGRESSION: a genuinely empty repo listing is UNREACHABLE, not a clean verdict", state == "UNREACHABLE")

# A short page proves the enumeration is exhausted — this is the property gh search cannot offer.
m.subprocess.run = fake_gh([page(100), page(75, 100)])
prs, state = m.open_pr_set()
check("a short final page ends pagination and reports OK", state == "OK" and len(prs) == 175)

# Runaway pagination must never pass as complete.
m.MAX_PAGES = 2
m.subprocess.run = fake_gh([page(100), page(100, 100), page(100, 200), page(100, 300)])
_, state = m.open_pr_set()
check("REGRESSION: pagination that will not terminate is TRUNCATED, not complete", state == "TRUNCATED")
m.MAX_PAGES = 20

# --- the shrink-only baseline -------------------------------------------------------------------
with tempfile.TemporaryDirectory() as td:
    base = Path(td) / "heal-retirement-baseline.txt"
    m.BASELINE = base
    check("absent baseline reads as empty", m.baseline_ids() == set())
    base.write_text("# comment\nHEAL-rebase-organvm-limen-102\n\nHEAL-x-1  # trailing\n", encoding="utf-8")
    check(
        "baseline parses ids, skipping comments and blanks",
        m.baseline_ids() == {"HEAL-rebase-organvm-limen-102", "HEAL-x-1"},
    )
    recorded = m.baseline_ids()
    fresh = [x for x in m.find_violations(tasks, complete) if x[0] not in recorded]
    check("a baselined violation is exempt", fresh == [])
    tasks.append(task("HEAL-cifix-organvm-limen-106", "open"))
    fresh = [x for x in m.find_violations(tasks, complete) if x[0] not in recorded]
    check("a NEW violation is not exempt", {x[0] for x in fresh} == {"HEAL-cifix-organvm-limen-106"})

# --- main()'s exit contract ------------------------------------------------------------------
# An unevaluable gate must BLOCK NOTHING. pr-gate exports no GH_TOKEN, so UNREACHABLE is the normal
# state in CI; a non-zero exit there would pin the gate red forever, which is how a gate stops being
# read. It still must not report a finding — exit 0 here means "nothing demonstrated", not "clean".
board = Path(tempfile.gettempdir()) / "_hr_board.yaml"
board.write_text("version: '1.0'\ntasks: []\n", encoding="utf-8")
os.environ["LIMEN_TASKS"] = str(board)
m.BASELINE = Path(tempfile.gettempdir()) / "_hr_absent_baseline.txt"
if m.BASELINE.exists():
    m.BASELINE.unlink()
m.load_limen_file = lambda _p: SimpleNamespace(tasks=[task("HEAL-cifix-organvm-limen-9001", "open")])

m.open_pr_set = lambda: (set(), "UNREACHABLE")
check("main() exits 0 when it could not enumerate (blocks nothing)", m.main() == 0)

m.open_pr_set = lambda: ({("organvm/limen", 1)}, "OK")
check("main() exits 1 on a demonstrated fresh violation", m.main() == 1)

m.open_pr_set = lambda: ({("organvm/limen", 9001)}, "OK")
check("main() exits 0 when the named PR is genuinely open", m.main() == 0)

print()
if failures:
    print(f"check-heal-retirement.test: FAIL ({len(failures)}): {failures}")
    raise SystemExit(1)
print("check-heal-retirement.test: OK")
