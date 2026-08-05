"""The organ must land its own pages, not merely hand them off.

`shipped.json` recorded a digest per page and nothing else — so it could say a page had been HANDED
OFF but never whether the handoff COMPLETED. On 2026-08-02 that produced five open, CLEARED,
non-deploy PRs across three days while the receipt file reported every page shipped. The named
owner of a handed-off PR is the beat's merge rung (drain.sh, heartbeat-loop.sh:466), which sits 113
lines below the paused `continue` at line 353 and had not run since 2026-07-22.

A separate file from test_diurnal.py deliberately: that file is a growing tail and conflicts
between sibling branches are certain. One concern, one file.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "diurnal.py"


@pytest.fixture()
def mod():
    spec = importlib.util.spec_from_file_location("diurnal", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["diurnal"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def root(tmp_path: Path) -> Path:
    (tmp_path / "logs" / "diurnal").mkdir(parents=True)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "ship-docs.sh").write_text("", encoding="utf-8")
    (tmp_path / "scripts" / "merge-policy.sh").write_text("", encoding="utf-8")
    (tmp_path / "scripts" / "await-pr.sh").write_text("", encoding="utf-8")
    (tmp_path / "docs" / "diurnal").mkdir(parents=True)
    return tmp_path


def _receipts(root: Path, data: dict) -> None:
    (root / "logs" / "diurnal" / "shipped.json").write_text(json.dumps(data), encoding="utf-8")


# ── the receipt shape ──────────────────────────────────────────────────────────────


def test_bare_digest_receipts_still_load(mod, root):
    """The original `{rel: digest}` form must keep working — live state is written in it."""
    _receipts(root, {"docs/diurnal/2026-08-01.md": "abc123"})
    assert mod.shipped_receipts(root) == {"docs/diurnal/2026-08-01.md": {"digest": "abc123"}}


def test_a_bare_digest_receipt_still_dedupes(mod, root):
    """Reading the old shape is not enough — it must still suppress a re-ship."""
    page = root / "docs" / "diurnal" / "2026-08-01.md"
    page.write_text("body", encoding="utf-8")
    _receipts(root, {"docs/diurnal/2026-08-01.md": mod._digest(page)})

    monkey = "?? docs/diurnal/2026-08-01.md"
    mod._run = lambda *a, **k: (0, monkey)  # noqa: SLF001 — the git status this reads
    assert mod.unshipped_pages(root) == []


# ── the reap ───────────────────────────────────────────────────────────────────────


def test_reap_merges_an_open_cleared_pr(mod, root, capsys):
    calls: list[str] = []

    def fake_run(cmd, _root, timeout=0):
        calls.append(cmd)
        if "gh pr view" in cmd:
            return 0, "OPEN\n"
        if "merge-policy.sh" in cmd:
            return 0, "VERDICT: CLEARED"
        if "await-pr.sh" in cmd:
            return 0, "MERGED"
        return 0, ""

    mod._run = fake_run  # noqa: SLF001
    assert mod.reap_shipped(root, {"docs/diurnal/2026-08-01.md": {"digest": "d", "pr": 1750}}) == 1
    assert any("await-pr.sh" in c and "1750 --merge" in c for c in calls)
    assert "MERGED" in capsys.readouterr().out


def test_reap_leaves_a_pr_merge_policy_does_not_clear(mod, root):
    """HOLD and BLOCKED are the predicate's answer, and the organ does not argue with it."""

    def fake_run(cmd, _root, timeout=0):
        if "gh pr view" in cmd:
            return 0, "OPEN\n"
        if "merge-policy.sh" in cmd:
            return 2, "VERDICT: HOLD"
        if "await-pr.sh" in cmd:
            raise AssertionError("must not wait on a PR the policy did not clear")
        return 0, ""

    mod._run = fake_run  # noqa: SLF001
    assert mod.reap_shipped(root, {"p": {"digest": "d", "pr": 99}}) == 0


def test_reap_skips_a_pr_that_is_no_longer_open(mod, root):
    def fake_run(cmd, _root, timeout=0):
        if "gh pr view" in cmd:
            return 0, "MERGED\n"
        if "merge-policy.sh" in cmd:
            raise AssertionError("a closed PR must not reach merge-policy")
        return 0, ""

    mod._run = fake_run  # noqa: SLF001
    assert mod.reap_shipped(root, {"p": {"digest": "d", "pr": 42}}) == 0


def test_reap_is_bounded_per_run(mod, root, monkeypatch):
    """A backlog must not stall the beat — the rest are retried next phase."""
    monkeypatch.setenv("LIMEN_DIURNAL_REAP_MAX", "2")
    seen: list[int] = []

    def fake_run(cmd, _root, timeout=0):
        if "gh pr view" in cmd:
            seen.append(int(cmd.split("gh pr view ")[1].split()[0]))
            return 0, "CLOSED\n"
        return 0, ""

    mod._run = fake_run  # noqa: SLF001
    receipts = {f"p{i}": {"digest": "d", "pr": 1000 + i} for i in range(5)}
    mod.reap_shipped(root, receipts)
    assert seen == [1000, 1001]


def test_reap_does_nothing_without_recorded_pr_numbers(mod, root):
    """Receipts in the original bare-digest shape carry no PR — nothing to reap, no crash."""
    mod._run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no subprocess expected"))  # noqa: SLF001
    assert mod.reap_shipped(root, {"p": {"digest": "abc"}}) == 0


# ── evening-only shipping ──────────────────────────────────────────────────────────


def test_morning_does_not_ship_todays_page(mod, root, monkeypatch):
    """Every phase rewrites the page; shipping each one opened 3 PRs for 1 file on 2026-08-01."""
    today = mod.datetime.now().strftime("%Y-%m-%d")
    monkeypatch.setattr(mod, "unshipped_pages", lambda _r: [f"docs/diurnal/{today}.md", "docs/diurnal/INDEX.md"])
    monkeypatch.setattr(mod, "reap_shipped", lambda *a: 0)
    mod._run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not ship"))  # noqa: SLF001

    assert mod.ship_pages(root, "morning") == 0


def test_morning_still_ships_a_previous_day_left_behind(mod, root, monkeypatch):
    """A crashed evening is caught the next morning, not a full day later."""
    today = mod.datetime.now().strftime("%Y-%m-%d")
    monkeypatch.setattr(
        mod,
        "unshipped_pages",
        lambda _r: ["docs/diurnal/2026-01-01.md", f"docs/diurnal/{today}.md", "docs/diurnal/INDEX.md"],
    )
    monkeypatch.setattr(mod, "reap_shipped", lambda *a: 0)
    shipped: list[str] = []

    def fake_run(cmd, _root, timeout=0):
        shipped.append(cmd)
        return 2, "ship-docs: opened PR #4242 (url)"

    mod._run = fake_run  # noqa: SLF001
    mod.ship_pages(root, "morning")

    cmd = shipped[0]
    assert "2026-01-01.md" in cmd
    assert "INDEX.md" in cmd, "the index rides along with a day that actually ships"
    assert f"{today}.md" not in cmd, "today's page waits for evening"


def test_evening_ships_today(mod, root, monkeypatch):
    today = mod.datetime.now().strftime("%Y-%m-%d")
    monkeypatch.setattr(mod, "unshipped_pages", lambda _r: [f"docs/diurnal/{today}.md"])
    monkeypatch.setattr(mod, "reap_shipped", lambda *a: 0)
    cmds: list[str] = []

    def fake_run(cmd, _root, timeout=0):
        cmds.append(cmd)
        return 2, "ship-docs: opened PR #777 (url)"

    mod._run = fake_run  # noqa: SLF001
    mod.ship_pages(root, "evening")
    assert f"{today}.md" in cmds[0]


def test_the_pr_number_is_recorded_so_the_next_run_can_reap_it(mod, root, monkeypatch):
    monkeypatch.setattr(mod, "unshipped_pages", lambda _r: ["docs/diurnal/2026-07-29.md"])
    monkeypatch.setattr(mod, "reap_shipped", lambda *a: 0)
    (root / "docs" / "diurnal" / "2026-07-29.md").write_text("x", encoding="utf-8")
    mod._run = lambda *a, **k: (2, "ship-docs: opened PR #1757 (https://github.com/o/r/pull/1757)")  # noqa: SLF001

    mod.ship_pages(root, "evening")
    assert mod.shipped_receipts(root)["docs/diurnal/2026-07-29.md"]["pr"] == 1757


def test_no_pr_is_recorded_when_ship_docs_already_merged(mod, root, monkeypatch):
    """exit 0 means it merged — there is nothing left open to reap."""
    monkeypatch.setattr(mod, "unshipped_pages", lambda _r: ["docs/diurnal/2026-07-30.md"])
    monkeypatch.setattr(mod, "reap_shipped", lambda *a: 0)
    (root / "docs" / "diurnal" / "2026-07-30.md").write_text("x", encoding="utf-8")
    mod._run = lambda *a, **k: (0, "ship-docs: opened PR #1758 (url)\nmerged")  # noqa: SLF001

    mod.ship_pages(root, "evening")
    assert mod.shipped_receipts(root)["docs/diurnal/2026-07-30.md"]["pr"] is None


def test_a_merge_prohibiting_marker_blocks_both_reap_and_ship(mod, root, monkeypatch):
    """The gate is the pause MARKER, exactly as the shipping path already read it."""
    (root / "logs").mkdir(exist_ok=True)
    (root / "logs" / "AUTONOMY_PAUSED").write_text("prohibitions: merge, dispatch\n", encoding="utf-8")
    monkeypatch.setattr(mod, "reap_shipped", lambda *a: (_ for _ in ()).throw(AssertionError("no reap")))
    mod._run = lambda *a, **k: (_ for _ in ()).throw(AssertionError("no subprocess"))  # noqa: SLF001

    assert mod.ship_pages(root, "evening") == 0
