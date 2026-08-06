#!/usr/bin/env python3
"""Every copy of the notifier on this host carries the effector gate — or it is named here.

THE DEFECT THIS EXISTS FOR, measured 2026-08-05. Eight "LIMEN · morning — ABSENT —
logs/handoff.json does not exist" notifications reached the operator's phone in one
afternoon. The operator asked why it was still happening for the THIRD time. Three fixes
had already shipped, each correct, each landing in the same place:

  1. diurnal.py grew a local ``has_body`` guard.
  2. #1732 lineage: that guard was extracted to ``scripts/_root.py`` because ~232 sites
     resolved root their own way — one wrong answer surviving in a hundred places.
  3. #1838 (19:20): the guard moved to the EFFECTOR, ``_notify._root_may_speak``, plus
     ``LIMEN_NOTIFY=0`` in cli/tests/conftest.py.

Four more pops landed at 19:25, 19:30, 19:36 and 19:48 — after fix 3. Not because the fix
was wrong. Because **the fix lives in a versioned file and ``osascript`` is a machine-global
singleton.** At the moment of measurement this host carried 15 limen checkouts and 14 of
them held the PRE-fix ``_notify.py``, whose ``notify_once`` shells straight to ``osascript``
with no gate at all. Any of them running pytest — ``ship-docs.sh`` cuts a worktree and runs
the gates; a worktree's ``logs/`` is empty, so ``handoff.json`` is ABSENT and the tmp-root
dedup state dies with the root and can never dedupe — pops the phone.

So this is fix 2's own lesson one level up, on an axis it could not reach. ``_root.py``
deduplicated the guard WITHIN a tree. Nothing deduplicated it ACROSS trees, and a fix
committed to ``main`` propagates to a worktree only when that worktree rebases. Guarding a
host-global effector with a tree-local file means there are always N un-upgraded copies
holding the old, ungated behaviour.

A predicate cannot rewrite the fourteen copies — only a rebase or a reap does that. What it
CAN do is make an ungated copy an observable, owned condition on the beat instead of a
surprise on his phone: the difference between a known N and a silent one. That is the whole
job here.

Structural, never substring: the file is parsed and the gate must be a real definition that
``notify_once`` actually calls. A copy that merely mentions ``_root_may_speak`` in a comment
does not pass (the sensors.yaml:478 precedent — substring matching produced 3 false
positives when the plan-mode probe was prototyped).

    python3 scripts/check-notify-gate.py            # exit 0 iff every copy is gated
    python3 scripts/check-notify-gate.py --json     # machine-readable roster
"""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _root  # noqa: E402  — hard import: this predicate has no meaning without root resolution

NOTIFIER_REL = Path("scripts") / "_notify.py"
GATE_FUNC = "_root_may_speak"
EFFECTOR_FUNC = "notify_once"

# The runtime install tree. Domus rotates it under `runtimes/<sha>/source` and points
# `current` at one; launchd runs overnight-watch from there, so it is a real speaker even
# though it is not a git worktree and never shows up in `git worktree list`.
INSTALL_RUNTIMES = Path.home() / ".local" / "share" / "limen" / "runtimes"


def enumerate_roots(live: Path) -> list[Path]:
    """Every limen checkout this host can execute the notifier from, deduplicated."""
    roots: list[Path] = [live]

    try:
        out = subprocess.run(
            ["git", "-C", str(live), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout
        roots += [Path(line.split(" ", 1)[1].strip()) for line in out.splitlines() if line.startswith("worktree ")]
    except (OSError, subprocess.SubprocessError):
        pass  # advisory: a git failure must not blind the rest of the roster

    try:
        roots += [p / "source" for p in INSTALL_RUNTIMES.iterdir() if (p / "source").is_dir()]
    except OSError:
        pass

    seen: dict[Path, None] = {}
    for root in roots:
        try:
            seen.setdefault(root.resolve(), None)
        except OSError:
            continue
    return list(seen)


def gate_state(notifier: Path) -> tuple[bool, str]:
    """(is_gated, reason). Parsed, not grepped — a mention in a comment is not a gate."""
    try:
        tree = ast.parse(notifier.read_text(encoding="utf-8"))
    except (OSError, SyntaxError) as exc:
        return False, f"unparseable ({exc})"

    defines = {n.name for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if GATE_FUNC not in defines:
        return False, f"no {GATE_FUNC}() — notify_once reaches osascript ungated"

    effector = next(
        (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == EFFECTOR_FUNC),
        None,
    )
    if effector is None:
        return True, f"{GATE_FUNC}() defined; no {EFFECTOR_FUNC}() to gate"

    called = {n.func.id for n in ast.walk(effector) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    if GATE_FUNC not in called:
        return False, f"{GATE_FUNC}() is defined but {EFFECTOR_FUNC}() never calls it"
    return True, f"{EFFECTOR_FUNC}() is gated on {GATE_FUNC}()"


def survey(live: Path) -> list[dict]:
    rows = []
    for root in enumerate_roots(live):
        notifier = root / NOTIFIER_REL
        if not notifier.is_file():
            continue  # not every checkout ships the notifier; absent cannot pop the phone
        gated, reason = gate_state(notifier)
        rows.append(
            {
                "root": str(root),
                "gated": gated,
                "reason": reason,
                "is_live": root == live,
                "is_worktree": _root.is_worktree(root),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the roster as JSON")
    args = ap.parse_args(argv)

    live, why = _root.resolve()
    if live is None:
        print(f"check-notify-gate: {why}", file=sys.stderr)
        return 0  # advisory: never fail the beat on an unresolvable root

    rows = survey(live)
    ungated = [r for r in rows if not r["gated"]]

    if args.json:
        print(json.dumps({"total": len(rows), "ungated": len(ungated), "roots": rows}, indent=2))
        return 1 if ungated else 0

    print(f"check-notify-gate: {len(rows)} notifier copy(ies) on this host, {len(ungated)} ungated")
    for row in ungated:
        kind = "worktree" if row["is_worktree"] else "checkout"
        print(f"  \033[31m✗\033[0m {kind}: {row['root']}")
        print(f"      {row['reason']}")

    if not ungated:
        print("  \033[32m✓\033[0m every copy gates osascript on the liveness predicate")
        return 0

    print()
    print("  Each copy above can pop the operator's phone with a briefing rendered from an")
    print("  empty logs/ — the gate is in main, but these trees predate it. Rebase or reap:")
    print("      git -C <root> rebase origin/main        # the copy inherits the gate")
    print("      python3 scripts/reclaim-worktrees.py    # the estate's reaper (worktree debt)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
