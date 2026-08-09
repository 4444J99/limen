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
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _root  # noqa: E402  — hard import: this predicate has no meaning without root resolution

NOTIFIER_REL = Path("scripts") / "_notify.py"
GATE_FUNC = "_root_may_speak"
PUBLIC_EFFECTORS = frozenset({"notify", "notify_once"})
DELIVERY_FUNC = "_deliver"

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


def _called_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    called: set[str] = set()
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name):
            called.add(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            called.add(node.func.attr)
    return called


def _gate_polarities(node: ast.AST, *, negated: bool = False) -> set[bool]:
    """Return whether each gate call is positively or negatively tested."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == GATE_FUNC:
        return {negated}
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _gate_polarities(node.operand, negated=not negated)
    polarities: set[bool] = set()
    for child in ast.iter_child_nodes(node):
        polarities.update(_gate_polarities(child, negated=negated))
    return polarities


def _has_delivery_call(node: ast.Call) -> bool:
    if isinstance(node.func, ast.Name) and node.func.id == DELIVERY_FUNC:
        return True
    literals = [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]
    return any("osascript" in value.lower() for value in literals)


def _body_exits(body: list[ast.stmt]) -> bool:
    return bool(body) and isinstance(body[-1], (ast.Return, ast.Raise))


def _condition_guarantees_gate(node: ast.AST) -> bool:
    """Return whether a true branch proves the positive liveness gate."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == GATE_FUNC:
        return True
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        return any(_condition_guarantees_gate(value) for value in node.values)
    return False


def _condition_returns_when_gate_false(node: ast.AST) -> bool:
    """Return whether the condition is guaranteed true whenever the gate is false."""
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.Not)
        and isinstance(node.operand, ast.Call)
        and isinstance(node.operand.func, ast.Name)
        and node.operand.func.id == GATE_FUNC
    ):
        return True
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return any(_condition_returns_when_gate_false(value) for value in node.values)
    return False


def _walk_delivery_paths(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef],
    *,
    gate_active: bool = False,
    stack: frozenset[tuple[str, bool]] = frozenset(),
) -> tuple[bool, bool]:
    """Return (found_delivery, every_delivery_controlled) through helper calls."""
    state = (function.name, gate_active)
    if state in stack:
        return False, True
    next_stack = stack | {state}
    found = False
    safe = True

    def inspect_expr(node: ast.AST, active: bool) -> None:
        nonlocal found, safe
        if isinstance(node, ast.Call):
            if _has_delivery_call(node):
                found = True
                safe = safe and active
            if isinstance(node.func, ast.Name) and node.func.id in functions:
                nested_found, nested_safe = _walk_delivery_paths(
                    functions[node.func.id],
                    functions,
                    gate_active=active,
                    stack=next_stack,
                )
                found = found or nested_found
                safe = safe and nested_safe
            for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
                inspect_expr(argument, active)
            return
        for child in ast.iter_child_nodes(node):
            inspect_expr(child, active)

    def inspect_block(body: list[ast.stmt], active: bool) -> None:
        nonlocal found, safe
        after_guard = active
        for statement in body:
            if isinstance(statement, ast.If):
                inspect_expr(statement.test, after_guard)
                inspect_block(
                    statement.body,
                    after_guard or _condition_guarantees_gate(statement.test),
                )
                inspect_block(statement.orelse, after_guard)
                if (
                    _condition_returns_when_gate_false(statement.test)
                    and _body_exits(statement.body)
                ):
                    after_guard = True
                continue
            inspect_expr(statement, after_guard)

    inspect_block(function.body, gate_active)
    return found, safe


def _gate_controls_delivery(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    functions: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
) -> tuple[bool, bool]:
    """Prove delivery safety and whether a route reaches the macOS effector."""
    function_map = functions or {function.name: function}
    found, safe = _walk_delivery_paths(function, function_map)
    return safe, found


def gate_state(notifier: Path) -> tuple[bool, str]:
    """Prove that every public route to the macOS effector controls delivery with the gate."""
    try:
        tree = ast.parse(notifier.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return False, f"unparseable ({exc})"

    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if GATE_FUNC not in functions:
        return False, f"no {GATE_FUNC}() — public notification routes are ungated"

    effectors: list[str] = []
    ungated: list[str] = []
    for name in sorted(PUBLIC_EFFECTORS):
        function = functions.get(name)
        if function is None:
            continue
        controlled, reaches_delivery = _gate_controls_delivery(function, functions)
        if not reaches_delivery:
            continue
        effectors.append(name)
        if not controlled:
            ungated.append(name)
    if ungated:
        return False, f"public effector(s) bypass {GATE_FUNC}(): {', '.join(sorted(ungated))}"
    if not effectors:
        return True, "no public macOS notification effector"
    return True, f"public effector(s) gated on {GATE_FUNC}(): {', '.join(sorted(effectors))}"


DIRECT_SUFFIXES = {".py", ".sh", ".bash", ".zsh"}
_DISPLAY_RE = re.compile(
    r"\bosascript\b[\s\S]{0,8192}?\bdisplay\s+notification\b",
    re.IGNORECASE,
)
_PROCESS_CALLS = frozenset({"run", "Popen", "call", "check_call", "check_output", "system"})


def _source_paths(root: Path) -> list[Path]:
    """Return only tracked sources mentioning osascript; avoid estate-wide AST parsing."""
    candidates: list[Path]
    try:
        found = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "grep",
                "-Il",
                "-e",
                "osascript",
                "--",
                "*.py",
                "*.sh",
                "*.bash",
                "*.zsh",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if found.returncode in {0, 1}:
            candidates = [root / line for line in found.stdout.splitlines() if line.strip()]
        else:
            candidates = list((root / "scripts").rglob("*"))
    except (OSError, subprocess.SubprocessError):
        candidates = list((root / "scripts").rglob("*"))
    return [
        candidate
        for candidate in candidates
        if candidate.is_file()
        and candidate.suffix in DIRECT_SUFFIXES
        and candidate != root / NOTIFIER_REL
        and "tests" not in candidate.parts
        and not candidate.name.startswith("test_")
    ]


def _static_string(node: ast.AST) -> str | None:
    """Return the statically visible text of a string or f-string expression."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_static_string(part) or " " for part in node.values)
    return None


def _static_argv(node: ast.AST) -> list[str] | None:
    if (value := _static_string(node)) is not None:
        return [value]
    if isinstance(node, (ast.List, ast.Tuple)):
        values: list[str] = []
        for element in node.elts:
            value = _static_string(element)
            if value is None:
                return None
            values.append(value)
        return values
    return None


def _python_bypasses(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, SyntaxError):
        return False
    bindings: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        value = _static_argv(node.value)
        if value is None:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                bindings[target.id] = value
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        call_name = call.func.id if isinstance(call.func, ast.Name) else (
            call.func.attr if isinstance(call.func, ast.Attribute) else ""
        )
        if call_name not in _PROCESS_CALLS:
            continue
        literals = [
            node.value
            for node in ast.walk(call)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        referenced: list[str] = []
        for node in ast.walk(call):
            if isinstance(node, ast.Name) and node.id in bindings:
                referenced.extend(bindings[node.id])
        values = [*literals, *referenced]
        has_osascript = any(value == "osascript" or value.endswith("/osascript") for value in values)
        if has_osascript and "display notification" in " ".join(values).lower():
            return True
    return False


def _shell_bypasses(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8").replace("\\\n", " ")
    except (OSError, UnicodeError):
        return False
    executable = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    return bool(re.search(r"\bosascript\b", executable, re.IGNORECASE)) and bool(
        re.search(r"\bdisplay\s+notification\b", executable, re.IGNORECASE)
    )


def direct_notification_effectors(root: Path) -> list[str]:
    """Every notification that bypasses _notify.py, relative to the surveyed root."""
    found = []
    for path in _source_paths(root):
        bypasses = _python_bypasses(path) if path.suffix == ".py" else _shell_bypasses(path)
        if bypasses:
            try:
                found.append(str(path.relative_to(root)))
            except ValueError:
                found.append(str(path))
    return sorted(found)


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
        direct_effectors = direct_notification_effectors(root)
        if notifier.is_file():
            gated, reason = gate_state(notifier)
        elif direct_effectors:
            gated = False
            reason = "shared notifier absent while direct effectors exist"
        else:
            continue
        if direct_effectors:
            gated = False
            reason = "direct display-notification effector(s) bypass _notify.py: " + ", ".join(direct_effectors)
        rows.append(
            {
                "root": str(root),
                "gated": gated,
                "reason": reason,
                "direct_effectors": direct_effectors,
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
        recordable = {
            r["root"]
            for r in ungated
            if r["executor"] != "scheduled" and not r["direct_effectors"]
        }
        write_baseline(recordable)
        print(f"check-notify-gate: baseline updated — {len(recordable)} dormant ungated copy(ies) recorded")
        return 0

    baseline = read_baseline()
    # Two independent failure conditions. A scheduled executor is a live hazard whatever the
    # baseline says — recording it would be accepting it. A new path is a regression: worktrees
    # are cut from main, so a fresh one inherits the gate; an unrecorded ungated copy means the
    # gate came off somewhere.
    scheduled_ungated = [r for r in ungated if r["executor"] == "scheduled"]
    regressions = [
        r
        for r in ungated
        if r["executor"] != "scheduled" and (r["direct_effectors"] or r["root"] not in baseline)
    ]

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
            print("  \033[32m✓\033[0m every copy gates macOS notifications on the shared liveness predicate")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
