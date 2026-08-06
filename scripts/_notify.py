#!/usr/bin/env python3
"""_notify — onset-deduped macOS notification helper (the VIGILIA escalation path).

IF-HOST-PRESSURE form 4: before 2026-07-16 the only pressure signal was an advisory
line in a beat log — the operator was the sensor of last resort. This helper gives
sensors a LOUD path (osascript display notification, the conducting-report.py
precedent; works from launchd) with onset dedup so a condition notifies once when it
begins, not once per beat.

State lives in ``logs/vigilia/relief-state.json`` under the caller's root: a key per
active condition. ``notify_once`` records + fires on first sight of a key;
``clear_condition`` removes it when the condition ends so a future onset re-fires.
Kill-switch: LIMEN_NOTIFY=0 keeps the dedup bookkeeping but never calls osascript
(also how the hermetic tests stay silent). Fail-open everywhere.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# The liveness guard lives next to this file ON DISK. Resolving it by path rather than by
# `import _root` is the whole point — see _load_root().
_ROOT_MODULE_PATH = Path(__file__).resolve().parent / "_root.py"
_ROOT_MODULE = None


def _state_path(root: Path | str) -> Path:
    return Path(root) / "logs" / "vigilia" / "relief-state.json"


def _load(root: Path | str) -> dict:
    try:
        state = json.loads(_state_path(root).read_text())
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _save(root: Path | str, state: dict) -> None:
    try:
        path = _state_path(root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=1, sort_keys=True))
    except Exception:
        pass


def _enabled(enabled: bool | None) -> bool:
    if enabled is not None:
        return enabled
    return os.environ.get("LIMEN_NOTIFY", "1") not in ("0", "false", "False")


def _load_root():
    """Load the sibling ``_root`` module BY ABSOLUTE PATH, never via ambient ``sys.path``.

    ``import _root`` resolves only when the calling script happened to run
    ``sys.path.insert(0, scripts/)`` first. Six of the seven ``_notify`` callers do;
    ``check-effectors.py`` does not. A guard whose availability depends on every caller
    remembering a convention is exactly the shape of guard a single omission defeats —
    the founding lesson of this entire lineage (``_root.py``'s own docstring: "a guard
    that a single write can satisfy is not a guard"). The module sits next to this file
    on disk, so load it from there and the whole failure mode is gone.
    """
    global _ROOT_MODULE
    if _ROOT_MODULE is None:
        spec = importlib.util.spec_from_file_location("_limen_root_for_notify", _ROOT_MODULE_PATH)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {_ROOT_MODULE_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _ROOT_MODULE = module
    return _ROOT_MODULE


def _root_may_speak(root: Path | str) -> bool:
    """Only the live organism reaches the phone.

    2026-08-05: four "LIMEN · morning — ABSENT" notifications in one afternoon, all real
    osascript pops, none from the live root. cli/tests calls diurnal's ``emit()`` directly
    (bypassing main()'s has_body guard) against a pytest tmp root whose relief-state is
    deleted with the root — so onset dedup can never dedupe, and every test run fires. The
    per-caller convention (each test remembers LIMEN_NOTIFY=0) is exactly the kind of guard
    a single omission defeats; this gates the EFFECTOR instead, at the one chokepoint every
    notifier shares. Bookkeeping still writes for any root — only the osascript call is
    withheld.

    FAIL CLOSED, reversing this function's first shipped form. It fell back to ``return
    True`` so "the live beat's escalations must not die of an import error" — but with the
    predicate now loaded by absolute path, an import error means the tree is missing its
    own ``_root.py``, and a tree that damaged is not the organism. The asymmetry decides
    it: a withheld notification is recoverable and observable in the beat log, while a
    false one is neither — it is already on his phone. The unexpected case is announced on
    stderr rather than swallowed, so silence is never silent about itself.
    """
    try:
        return bool(_load_root().has_body(Path(root))[0])
    except Exception as exc:
        print(f"_notify: withholding notification — liveness predicate unavailable ({exc})", file=sys.stderr)
        return False


def notify_once(
    root: Path | str,
    key: str,
    message: str,
    title: str = "LIMEN host pressure",
    enabled: bool | None = None,
) -> bool:
    """Fire one notification per condition onset. Returns True iff this call fired.

    The dedup record is written even when notifications are disabled, so arming
    LIMEN_NOTIFY later does not replay every already-active condition.
    """
    state = _load(root)
    if key in state:
        return False
    state[key] = {"first_seen": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "message": message[:300]}
    _save(root, state)
    if _enabled(enabled) and _root_may_speak(root):
        try:
            msg = message.replace('"', "'")
            ttl = title.replace('"', "'")
            subprocess.run(
                ["osascript", "-e", f'display notification "{msg}" with title "{ttl}"'],
                capture_output=True,
                timeout=10,
            )
        except Exception:
            pass
    return True


def clear_condition(root: Path | str, key: str) -> bool:
    """Forget an ended condition so its next onset notifies again."""
    state = _load(root)
    if key not in state:
        return False
    del state[key]
    _save(root, state)
    return True


def active_conditions(root: Path | str) -> list[str]:
    return sorted(_load(root))
