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

A predicate cannot rewrite the other copies — only a rebase or a reap does that. What it CAN do
is make an ungated copy an observable, owned condition on the beat instead of a surprise on his
phone: the difference between a known N and a silent one.

SECOND PASS (same day). Reporting a known N turned out not to be enough, because N was the wrong
unit. The first version of this file printed all 20 ungated copies identically, and that
flattening HID the only one that mattered: `~/.local/share/limen/current` — the runtime launchd
executes unattended every 300s — is itself ungated, and its symlink had not been repointed in
five days. A dormant worktree speaks only if somebody runs a test inside it; that one speaks on
a timer. So rows now carry an ``executor`` classification, and a scheduled-and-ungated copy gets
its own stanza with the exact rotation command, never folded into the roster.

Two things follow from that, and they are the actual salve:

  • The count RATCHETS. `institutio/governance/notify-ungated-baseline.txt` records the dormant
    copies (the check-params.py baseline pattern), so a NEW ungated copy fails while a draining
    one does not. A scheduled executor is never recordable — writing it to the baseline would
    convert a live hazard into an accepted one with a single flag, which is the exact shape of
    guard this lineage keeps having to unlearn.
  • The blast radius is closed WITHOUT touching any of these copies, by
    `scripts/run-pytest-hermetic.sh` exporting ``LIMEN_NOTIFY=0`` after its LIMEN_* scrub. Every
    copy on this host, gated or not, honors that variable — they all carry the same `_enabled()`.
    You cannot retro-patch code that is already written; you can control the environment it runs
    in. (The wrapper was previously *un*-setting the kill-switch, restoring the speak-by-default
    behaviour in precisely the trees that lacked the in-tree gate.)

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
import time
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

# `current` is the one runtime launchd actually executes (com.limen.overnight-watch, every
# 300s, via DomusAgentHost). Resolving it is the difference between a finding and a fact:
# the first version of this predicate reported all copies identically, so the production
# daemon being ungated read exactly like a forgotten worktree. It is not the same finding.
# A dormant checkout speaks only if someone runs pytest in it; this one speaks on a timer.
INSTALL_CURRENT = Path.home() / ".local" / "share" / "limen" / "current"

# Known-ungated roots, recorded so the count can only shrink. The check-params.py baseline
# pattern: a NEW ungated copy is a regression and fails; a recorded one is reported and
# tolerated, because the drain is owned by reclaim-worktrees.py on its own cadence and by
# domus's install rotation — neither of which this predicate can perform.
BASELINE = Path(__file__).resolve().parent.parent / "institutio" / "governance" / "notify-ungated-baseline.txt"

BASELINE_HEADER = (
    "# notify-ungated-baseline — roots whose scripts/_notify.py predates the effector gate\n"
    "# (#1841) and therefore reaches osascript unguarded. Recorded, not accepted: the gate\n"
    "# fails on any NEW entry. These drain by rebase (reclaim-worktrees.py) or by domus\n"
    "# rotating the runtime install; afterwards run:\n"
    "#   python3 scripts/check-notify-gate.py --update\n"
)


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


# Rotations ran near-daily (Jul 27→31) and then stopped. A gap this size is a stall, not a
# cadence — worth saying out loud, because "it will pick up the fix next rotation" is only true
# while rotations happen.
STALE_INSTALL_DAYS = 3


def _origin_main_sha() -> str | None:
    """The merged SHA a rotation would install — so the route is a command, not a description."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "origin/main"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        sha = out.stdout.strip()
        return sha if len(sha) == 40 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _install_age_days() -> int | None:
    """Days since `current` was last repointed — measured, never asserted."""
    try:
        return int((time.time() - INSTALL_CURRENT.lstat().st_mtime) / 86400)
    except OSError:
        return None


def scheduled_root() -> Path | None:
    """The runtime launchd executes, or None when no install is present."""
    try:
        return (INSTALL_CURRENT / "source").resolve() if INSTALL_CURRENT.exists() else None
    except OSError:
        return None


def classify(root: Path, live: Path, scheduled: Path | None) -> str:
    """How this copy gets RUN — the axis that separates a hazard from a housekeeping item."""
    if scheduled is not None and root == scheduled:
        return "scheduled"  # launchd runs it on a timer, unattended
    if root == live:
        return "live"
    if INSTALL_RUNTIMES in root.parents:
        return "dormant-runtime"  # rotated out; nothing executes it
    return "worktree"  # speaks only if someone runs pytest inside it


def read_baseline(path: Path = BASELINE) -> set[str]:
    if not path.exists():
        return set()
    return {ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip() and not ln.startswith("#")}


def write_baseline(roots: set[str], path: Path = BASELINE) -> None:
    path.write_text(BASELINE_HEADER + "\n".join(sorted(roots)) + "\n", encoding="utf-8")


def survey(live: Path) -> list[dict]:
    rows = []
    scheduled = scheduled_root()
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
                "executor": classify(root, live, scheduled),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="print the roster as JSON")
    ap.add_argument("--update", action="store_true", help="rewrite the baseline to the current ungated set")
    args = ap.parse_args(argv)

    live, why = _root.resolve()
    if live is None:
        print(f"check-notify-gate: {why}", file=sys.stderr)
        return 0  # advisory: never fail the beat on an unresolvable root

    rows = survey(live)
    ungated = [r for r in rows if not r["gated"]]
    ungated_roots = {r["root"] for r in ungated}

    if args.update:
        # A scheduled executor is never recorded. The baseline means "known, draining"; writing
        # the launchd-run copy into it would convert a live hazard into an accepted one with a
        # single flag — precisely the shape of guard this lineage keeps learning not to build.
        recordable = {r["root"] for r in ungated if r["executor"] != "scheduled"}
        write_baseline(recordable)
        print(f"check-notify-gate: baseline updated — {len(recordable)} dormant ungated copy(ies) recorded")
        return 0

    baseline = read_baseline()
    # Two independent failure conditions. A scheduled executor is a live hazard whatever the
    # baseline says — recording it would be accepting it. A new path is a regression: worktrees
    # are cut from main, so a fresh one inherits the gate; an unrecorded ungated copy means the
    # gate came off somewhere.
    scheduled_ungated = [r for r in ungated if r["executor"] == "scheduled"]
    regressions = [r for r in ungated if r["root"] not in baseline and r["executor"] != "scheduled"]

    if args.json:
        print(
            json.dumps(
                {
                    "total": len(rows),
                    "ungated": len(ungated),
                    "scheduled_ungated": len(scheduled_ungated),
                    "regressions": [r["root"] for r in regressions],
                    "roots": rows,
                },
                indent=2,
            )
        )
        return 1 if (scheduled_ungated or regressions) else 0

    print(f"check-notify-gate: {len(rows)} notifier copy(ies) on this host, {len(ungated)} ungated")

    if scheduled_ungated:
        print()
        print("  \033[31m✗ SCHEDULED EXECUTOR IS UNGATED\033[0m — this one is not housekeeping.")
        for row in scheduled_ungated:
            print(f"      {row['root']}")
            print(f"      {row['reason']}")
        print("  launchd runs this copy unattended (com.limen.overnight-watch, every 300s), so it")
        print("  speaks on a timer rather than only when someone runs a test in it. Limen ships no")
        print("  installer for it — domus owns ~/.local/share/limen/runtimes and the `current`")
        print("  symlink. The route is one command, not a human decision:")
        print(f"      domus-limen-runtime install --sha {_origin_main_sha() or '<merged-main-sha>'}")
        age = _install_age_days()
        if age is not None and age >= STALE_INSTALL_DAYS:
            print(f"  The install has not rotated in {age} day(s) — this is a stall, not a slow cadence,")
            print("  so it will NOT clear on its own. Rotation is what lands the gate here.")

    dormant = [r for r in ungated if r["executor"] != "scheduled"]
    if dormant:
        print()
        print(f"  {len(dormant)} dormant copy(ies) — inert unless a test runs inside them:")
        for row in dormant:
            mark = "\033[31m✗\033[0m" if row in regressions else "·"
            print(f"    {mark} {row['executor']}: {row['root']}")

    if regressions:
        print()
        print("  \033[31m✗ NEW ungated copy(ies)\033[0m — not in the baseline. A worktree cut from main")
        print("  inherits the gate, so an unrecorded copy means it came off somewhere. Rebase or reap:")
        print("      git -C <root> rebase origin/main        # the copy inherits the gate")
        print("      python3 scripts/reclaim-worktrees.py    # the estate's reaper (worktree debt)")
        print("  If the copy is legitimately known, record it: check-notify-gate.py --update")

    if not scheduled_ungated and not regressions:
        if ungated:
            print()
            print("  \033[32m✓\033[0m no scheduled executor is ungated and no new copy appeared; the")
            print("      recorded ones drain via reclaim-worktrees.py. Gate-run tests cannot reach")
            print("      osascript regardless — run-pytest-hermetic.sh exports LIMEN_NOTIFY=0, which")
            print("      every copy on this host honors, gated or not.")
        else:
            print("  \033[32m✓\033[0m every copy gates osascript on the liveness predicate")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
