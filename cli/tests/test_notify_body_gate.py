"""_notify's body-gate — only the live organism reaches the phone.

Regression pin for 2026-08-05: four real "LIMEN · morning — ABSENT" pops in one afternoon,
fired by pytest. cli/tests calls diurnal's emit() directly (bypassing main()'s has_body
guard) against a tmp root whose relief-state dies with the root, so onset dedup can never
dedupe — one notification per test run, forever. The fix gates the EFFECTOR: _notify
withholds the osascript call for any root that is not the live organism, regardless of
LIMEN_NOTIFY, so no synthetic/worktree/trial root can ever speak out loud.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import _root  # noqa: E402


def _load_notify():
    spec = importlib.util.spec_from_file_location("_notify", ROOT / "scripts" / "_notify.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_notify"] = mod
    spec.loader.exec_module(mod)
    return mod


def _organism(path: Path, voices: int) -> Path:
    (path / ".git").mkdir(parents=True, exist_ok=True)
    (path / "institutio" / "governance").mkdir(parents=True, exist_ok=True)
    (path / "institutio" / "governance" / "sensors.yaml").write_text("", encoding="utf-8")
    voice = path / "logs" / ".voice"
    voice.mkdir(parents=True, exist_ok=True)
    for i in range(voices):
        (voice / f"sensor{i}").write_text("", encoding="utf-8")
    return path


def test_a_synthetic_root_records_the_onset_but_never_speaks(tmp_path, monkeypatch):
    """THE REGRESSION. enabled=True is the strongest possible ask — a bare tmp root
    (exactly what every pytest fixture hands out) must still be withheld from osascript."""
    mod = _load_notify()
    calls: list[list[str]] = []
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    fired = mod.notify_once(tmp_path, "diurnal:morning:2026-08-05", "ABSENT — x", enabled=True)

    assert fired is True  # onset bookkeeping is untouched — dedup semantics survive
    assert calls == []  # but the phone never rings
    assert mod.active_conditions(tmp_path) == ["diurnal:morning:2026-08-05"]


def test_the_live_organism_still_speaks(tmp_path, monkeypatch):
    """The gate must not eat the beat's real escalations — a beaten primary checkout fires."""
    mod = _load_notify()
    body = _organism(tmp_path / "body", voices=_root.DEFAULT_VOICE_FLOOR)
    calls: list[list[str]] = []
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    assert mod.notify_once(body, "k", "msg", enabled=True) is True
    assert len(calls) == 1 and calls[0][0] == "osascript"


def test_a_worktree_root_is_withheld(tmp_path, monkeypatch):
    """A linked worktree (gitdir-pointer .git) with voices is still not the organism."""
    mod = _load_notify()
    wt = _organism(tmp_path / "wt", voices=_root.DEFAULT_VOICE_FLOOR)
    (wt / ".git").rmdir()
    (wt / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setattr(mod.subprocess, "run", lambda cmd, **kw: calls.append(cmd))

    assert mod.notify_once(wt, "k", "msg", enabled=True) is True
    assert calls == []
