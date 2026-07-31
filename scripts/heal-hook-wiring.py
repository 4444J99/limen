#!/usr/bin/env python3
"""heal-hook-wiring.py — assert the trust-hook wiring in the CARTRIDGE SOURCE.

Sibling of ``heal-hook-drift.sh``. That effector keeps the deployed hook FILE in parity
with the repo canonical (dialogs-silenced class 1b); this one closes the asymmetry beside
it — class 1d, "the trust hook is not WIRED" — which until now carried only a printed cure
string while its neighbour carried an organ.

WHY THE SOURCE AND NOT THE RENDERED FILE
    ``~/.claude/settings.json`` is declared ``owner: cartridge, mechanism: template`` in
    domus-genoma ``.chezmoidata/config-ownership.json``. Editing the rendered file is futile:
    the next ``chezmoi apply`` overwrites it (Rule #6, fix bases not outputs). Everything here
    therefore targets ``private_dot_claude/settings.json.tmpl`` and lets chezmoi deploy.

WHY THIS IS OPERATOR-ARMED AND NEVER BEAT-WIRED
    Widening the agent's own permission gate is blocked by the auto-mode classifier, and that
    boundary is correct — an agent must not be the actor that widens it, wherever the file
    lives. This script preserves that intent exactly: it is dry-run by default, prints the
    full diff, and applies only under an explicit operator arm. Do NOT add it to
    ``sensors.yaml`` or ``metabolize.sh``; an auto-armed valve here would make the system
    widen its own gate unattended, which is the precise thing the classifier exists to stop.

THE SOURCE IS A TEMPLATE, NOT JSON (measured 2026-07-31)
    The first version of this script parsed the source with ``json.loads`` on the assumption
    that every chezmoi ``{{ … }}`` action lived inside a JSON string value. It does not — the
    statusLine block carries ``"command": {{ printf … | toJson }}``, an action that PRODUCES a
    JSON value at the structural level, so the source is not parseable and never will be.

    The correctness predicate was wrong, not just the parser. "Is the source valid JSON?" is
    not the property that matters; **"does the source RENDER to valid JSON carrying all three
    assertions?"** is. So this script now splices text at uniquely-anchored insertion points,
    then proves the result through ``chezmoi cat`` — the real renderer — and restores the
    backup on any failure. It never has to understand the template language.

WHAT IT ASSERTS (idempotent; re-running a healed tree is a no-op)
    1. ``hooks.PreToolUse``  — one Bash group invoking allow-trusted-cd-git.sh, guarded so a
       machine without the hook deployed cannot error.
    2. ``permissions.ask``   — exactly the five destructive rules dialogs-silenced 1c demands.
       This is the FAIL-SAFE: if the hook ever breaks, behaviour must degrade to prompting on
       rm/force-push, never to silent approval.
    3. ``permissions.autoMode.allow`` — teaches the auto-mode classifier the same trust
       boundary the hook enforces, so compound and substituted commands the hook declines to
       judge are still resolved without a modal. MUST lead with the literal "$defaults" or the
       built-in classifier rules are replaced wholesale (settings-all--reference.jsonc).

    ``permissions.defaultMode`` is left at "auto" DELIBERATELY. bypassPermissions does not
    reduce distance-from-ideal, it deletes the instrument: you cannot measure "does it ask?"
    in a world where nothing can ask, and it silently un-gates the rm class that once wiped
    the live checkout. Keep the gauge, make the hook good enough that the gauge reads zero.

USAGE
    python3 scripts/heal-hook-wiring.py              # dry-run: print the diff, exit 1 if unwired
    python3 scripts/heal-hook-wiring.py --apply      # write the source, then chezmoi apply
    python3 scripts/heal-hook-wiring.py --apply --allow-drop
                                                    # deploy even though the apply discards live
                                                    # keys the template does not declare; the
                                                    # refusal names them first, so pass this only
                                                    # after reading exactly what is lost
    python3 scripts/heal-hook-wiring.py --help       # this text
    LIMEN_HOOK_WIRING_HEAL=1 python3 scripts/heal-hook-wiring.py    # env arm, same as --apply

    Unrecognised flags are refused, never ignored — see main().

EXIT
    0 ⟺ the source already carries all three assertions (or they were applied and verified),
        or --help was requested.
    1 ⟺ drift found on a dry-run, or the render check failed and the backup was restored.
    2 ⟺ the cartridge source could not be read, an anchor was missing/ambiguous, or an
        unknown argument was passed.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_DOMUS = Path.home() / "Workspace" / "domus-genoma"
DOMUS = Path(os.environ.get("DOMUS_ROOT", DEFAULT_DOMUS))
TMPL = DOMUS / "private_dot_claude" / "settings.json.tmpl"

HOOK_CMD = 'H={{ .chezmoi.homeDir }}/.claude/hooks/allow-trusted-cd-git.sh; [ -x "$H" ] && "$H" || true'
HOOK_GROUP = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "command": HOOK_CMD,
            "timeout": 10,
            "statusMessage": "Trusted-tree fast path...",
        }
    ],
}

# dialogs-silenced.sh §1c holds the source to exactly these five, no more, no less.
ASK_RULES = [
    "Bash(git push* --force*)",
    "Bash(git push* -f*)",
    "Bash(rm:*)",
    "Bash(rmdir:*)",
    "Bash(shred:*)",
]

# "$defaults" MUST come first — it splices the built-in classifier rules back in.
AUTOMODE_ALLOW = [
    "$defaults",
    "Read, build, test, lint and format commands are allowed anywhere under the user's own "
    "trees: ~/Workspace, ~/Code, ~/.claude/worktrees, ~/.claude/jobs, $TMPDIR and /tmp.",
    "Version-control work in those trees is allowed without confirmation, including git add, "
    "commit (any message length or -F file), push, fetch, pull, checkout, switch, restore, "
    "branch, rebase, stash, worktree add/list, and the gh CLI for prs, issues, runs and api.",
    "Package and toolchain commands in those trees are allowed: npm, npx, pnpm, yarn, node, "
    "python3, pip, uv, pytest, ruff, cargo, go, make, wrangler and sqlite3.",
    "Deleting DISPOSABLE session artifacts is allowed without confirmation: anything under "
    "~/.claude/worktrees, ~/.claude/jobs, $TMPDIR or /tmp, and build artifacts strictly inside "
    "a repo under ~/Workspace or ~/Code.",
    "Still require confirmation regardless of directory: sudo, dd, mkfs, shred, chmod/chown -R, "
    "curl|sh, xargs rm, find -delete, git push --force/-f/--delete, deleting a repo root or a "
    "home directory, and git reset --hard or git clean in a primary checkout.",
]


# ── Anchors ──────────────────────────────────────────────────────────────────
# Each must appear EXACTLY once in the source. A missing or duplicated anchor is a hard
# stop (exit 2), never a guess: this file governs the permission gate.
ANCHOR_PRETOOLUSE = '"PreToolUse": ['
ANCHOR_DEFAULTMODE = '"defaultMode": "auto"'

HOOK_MARKER = "allow-trusted-cd-git.sh"
ASK_MARKER = '"ask": ['
AUTOMODE_MARKER = '"autoMode": {'

# The complete argv surface. Anything else is a usage error, not an ignorable token.
KNOWN_FLAGS = {"--apply", "--allow-drop", "-h", "--help"}


def fail(msg: str, code: int = 2) -> None:
    print(f"hook-wiring-heal: {msg}", file=sys.stderr)
    sys.exit(code)


def read_source() -> str:
    if not TMPL.is_file():
        fail(f"cartridge source not found: {TMPL}")
    return TMPL.read_text()


def anchor_at(raw: str, anchor: str) -> int:
    """Index of a must-be-unique anchor. Hard-stops on absent or ambiguous."""
    n = raw.count(anchor)
    if n != 1:
        fail(
            f"anchor {anchor!r} appears {n} times in {TMPL.name} (need exactly 1); "
            "refusing to guess an insertion point in a permission file"
        )
    return raw.index(anchor)


def indent_of(raw: str, idx: int) -> str:
    """Leading whitespace of the line containing idx."""
    line_start = raw.rfind("\n", 0, idx) + 1
    return raw[line_start : idx - len(raw[line_start:idx].lstrip())] or ""


def block(obj, indent: str) -> str:
    """json.dumps a fragment and re-indent every line to sit at `indent`."""
    text = json.dumps(obj, indent=2)
    return "\n".join((indent + line) if i else line for i, line in enumerate(text.splitlines()))


def splice(raw: str) -> tuple[str, list[str]]:
    """Return (new_source, changes). Purely textual — never parses the template."""
    changes: list[str] = []
    out = raw

    if HOOK_MARKER not in out:
        idx = anchor_at(out, ANCHOR_PRETOOLUSE) + len(ANCHOR_PRETOOLUSE)
        ind = indent_of(out, out.index(ANCHOR_PRETOOLUSE)) + "  "
        out = out[:idx] + "\n" + ind + block(HOOK_GROUP, ind) + "," + out[idx:]
        changes.append("wired allow-trusted-cd-git.sh into hooks.PreToolUse (matcher Bash)")

    # `ask` and `autoMode` are siblings of defaultMode inside `permissions`.
    need_ask = ASK_MARKER not in out
    need_automode = AUTOMODE_MARKER not in out
    if need_ask or need_automode:
        idx = anchor_at(out, ANCHOR_DEFAULTMODE)
        ind = indent_of(out, idx)
        tail = idx + len(ANCHOR_DEFAULTMODE)
        additions = []
        if need_ask:
            additions.append(f'"ask": {block(ASK_RULES, ind)}')
            changes.append("restored the five destructive permissions.ask rules (fail-safe backstop)")
        if need_automode:
            additions.append(f'"autoMode": {block({"allow": AUTOMODE_ALLOW}, ind)}')
            changes.append('set permissions.autoMode.allow (leads with "$defaults")')
        joined = "".join(f",\n{ind}{a}" for a in additions)
        out = out[:tail] + joined + out[tail:]

    return out, changes


def render(target: Path) -> str | None:
    """Render the target through chezmoi itself. None if chezmoi is unavailable."""
    chezmoi = shutil.which("chezmoi")
    if not chezmoi:
        return None
    proc = subprocess.run([chezmoi, "cat", str(target)], capture_output=True, text=True)
    if proc.returncode != 0:
        fail(f"`chezmoi cat {target}` failed:\n{proc.stderr}", code=1)
    return proc.stdout


def verify_render(text: str) -> list[str]:
    """The real predicate: the RENDER must be valid JSON carrying all three assertions."""
    problems: list[str] = []
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as exc:
        return [f"render is not valid JSON: {exc}"]

    perms = doc.get("permissions") or {}
    hooks = (doc.get("hooks") or {}).get("PreToolUse") or []

    if not any(HOOK_MARKER in str(h.get("command", "")) for g in hooks for h in (g.get("hooks") or [])):
        problems.append("rendered hooks.PreToolUse does not invoke the trust hook")
    if sorted(perms.get("ask") or []) != sorted(ASK_RULES):
        problems.append("rendered permissions.ask is not the five destructive rules")
    allow = (perms.get("autoMode") or {}).get("allow") or []
    if not allow or allow[0] != "$defaults":
        problems.append('rendered permissions.autoMode.allow does not lead with "$defaults"')
    if perms.get("defaultMode") != "auto":
        problems.append(f"defaultMode changed to {perms.get('defaultMode')!r} — must stay 'auto'")
    return problems


def deploy(target: Path, armed: bool, backup: Path | None = None) -> int:
    """Render, verify, guard the live target's app atoms, then apply.

    Shared by both paths into deployment: a source we just spliced, and a source that was
    already correct but never reached the target (the false-green defect, 2026-07-31).
    `backup` is restored on a failed render check when we wrote the source this run.
    """
    rendered = render(target)
    if rendered is None:
        print("hook-wiring-heal: chezmoi not on PATH — source correct, but UNDEPLOYED.")
        print(f"  verify: chezmoi cat {target} | python3 -m json.tool >/dev/null")
        print(f"  deploy: chezmoi apply --force {target}")
        return 1

    problems = verify_render(rendered)
    if problems:
        if backup is not None:
            shutil.copy2(backup, TMPL)
        for p in problems:
            print(f"hook-wiring-heal: RENDER CHECK FAILED — {p}", file=sys.stderr)
        fail("backup restored; source is exactly as it was" if backup else "source unchanged", code=1)

    print("hook-wiring-heal: render check PASSED (valid JSON; hook + ask + autoMode present; defaultMode 'auto')")

    # ── App-atom guard (2026-07-31) ──────────────────────────────────────────
    # `.claude/settings.json` is declared owner:cartridge/mechanism:template with NO
    # app_managed carve-out, so every key Claude Code writes into the RENDERED file —
    # `model`, and anything set via /config — is silently discarded on each apply. Measured
    # on the first real arming: the deploy would have dropped "model": "claude-fable-5[1m]".
    # That is IF-CONFIG-OWNERSHIP's failure class running in reverse (the constitution was
    # built after an APP clobbered an OWNER atom; here the cartridge clobbers an app atom).
    # Widening the permission gate must never cost an unrelated setting, so: refuse, name
    # exactly what would be lost, and leave the verified source in place undeployed.
    dropped = {}
    if target.is_file():
        try:
            live = json.loads(target.read_text())
            new_doc = json.loads(rendered)
            dropped = {k: live[k] for k in live if k not in new_doc}
        except json.JSONDecodeError:
            pass  # an unparseable live target is not this script's problem to adjudicate

    if dropped and "--allow-drop" not in sys.argv:
        print()
        print("hook-wiring-heal: REFUSING TO DEPLOY — the apply would DROP live setting(s):")
        for key, value in dropped.items():
            print(f"    {key} = {json.dumps(value)}")
        print()
        print("  The cartridge source is written and VERIFIED; only the deploy is held.")
        print("  These keys exist in the rendered file but not in the template, so chezmoi")
        print("  discards them. Pick one:")
        print("    1. Deploy anyway, then restore by hand (e.g. /model in Claude Code):")
        print("         python3 scripts/heal-hook-wiring.py --apply --allow-drop")
        print("    2. Declare them in the template so the cartridge owns them (they will then")
        print("       be reset to the declared value on every apply).")
        print("    3. The real fix — promote .claude/settings.json from `template` to")
        print("       `split` + `modify_` in domus-genoma .chezmoidata/config-ownership.json,")
        print("       owner_managed = env/permissions/hooks, app_managed = model/theme/etc.")
        print("       IF-CONFIG-OWNERSHIP already names this successor pattern.")
        return 1

    if dropped:
        print(f"hook-wiring-heal: --allow-drop — deploying; these will be lost: {sorted(dropped)}")

    chezmoi = shutil.which("chezmoi")
    # --force is REQUIRED, not a convenience: the target always carries out-of-band drift
    # (Claude Code rewrites its own settings.json), so a bare apply opens an interactive
    # confirm and dies with "could not open a new TTY" under any non-interactive caller —
    # measured on the first real arming. Forcing is safe here and only here, because by this
    # line the drift has been explicitly adjudicated: the render check proved the output is
    # valid JSON with all three assertions, and the app-atom guard above proved the apply
    # drops nothing (or the operator passed --allow-drop knowing exactly what is lost).
    proc = subprocess.run([chezmoi, "apply", "--force", str(target)], capture_output=True, text=True)
    if proc.returncode != 0:
        print(f"hook-wiring-heal: chezmoi apply failed:\n{proc.stderr}", file=sys.stderr)
        print("hook-wiring-heal: the SOURCE is correct and verified — deploy by hand:")
        print(f"  chezmoi apply {target}        # add --force on out-of-band drift")
        return 1

    print("hook-wiring-heal: deployed. Hooks load at session start — restart Claude Code.")
    print("hook-wiring-heal: verify with `bash scripts/dialogs-silenced.sh`")
    return 0


def main() -> int:
    # Argv is membership-tested, not parsed, so an unrecognised flag used to be discarded in
    # silence: `--aply` ran a dry-run the operator read as a deploy, and `--allow-drops` hit a
    # guard they believed they had waived. Both fail toward doing less, which is the right
    # direction — but an effector that widens a permission gate must never leave the operator
    # guessing which run actually happened. Name the flags, refuse the unknown ones.
    argv = sys.argv[1:]
    if "-h" in argv or "--help" in argv:
        print((__doc__ or "").strip())
        return 0
    unknown = [a for a in argv if a not in KNOWN_FLAGS]
    if unknown:
        print(f"hook-wiring-heal: unknown argument(s): {' '.join(unknown)}", file=sys.stderr)
        print(f"  known flags: {' '.join(sorted(KNOWN_FLAGS))}", file=sys.stderr)
        print("  usage: python3 scripts/heal-hook-wiring.py --help", file=sys.stderr)
        return 2

    armed = "--apply" in argv or os.environ.get("LIMEN_HOOK_WIRING_HEAL") == "1"
    fixture = DOMUS != DEFAULT_DOMUS

    # LIMEN_HOOK_WIRING_TARGET exists so the regression matrix can point the deployed-state
    # check at a fixture. It never changes behaviour on a real host.
    target = Path(os.environ.get("LIMEN_HOOK_WIRING_TARGET", Path.home() / ".claude" / "settings.json"))
    raw = read_source()
    new, changes = splice(raw)

    if not changes:
        # THE SOURCE IS THE BASE, BUT THE TARGET IS THE GATE (measured 2026-07-31).
        # v3 returned 0 right here, and that was a FALSE GREEN: the previous run had already
        # written the source and then failed at deploy (no TTY), so the next run saw a correct
        # source, printed "clean", and exited 0 — while the live settings.json still had the
        # hook unwired, ask empty and autoMode empty. "Fix bases, not outputs" says where to
        # WRITE; it does not say the deployed state stops mattering. Clean therefore requires
        # BOTH: the source carries the assertions AND the target already reflects them.
        print("hook-wiring-heal: cartridge source already carries hook + ask + autoMode")
        live_problems = verify_render(target.read_text()) if target.is_file() else ["target missing"]
        if not live_problems:
            print("hook-wiring-heal: clean (deployed target matches — nothing to do)")
            return 0
        print("hook-wiring-heal: but the DEPLOYED target is out of sync:")
        for problem in live_problems:
            print(f"    - {problem}")
        if not armed:
            print("hook-wiring-heal: DRY RUN. Re-run with --apply to deploy the existing source.")
            print("  python3 scripts/heal-hook-wiring.py --apply")
            return 1
        if fixture:
            print("hook-wiring-heal: DOMUS_ROOT overridden — out-of-sync detected; deploy skipped")
            return 1
        return deploy(target, armed)

    for line in changes:
        print(f"hook-wiring-heal: {'applying' if armed else 'would apply'} — {line}")

    if not armed:
        print()
        print(
            "".join(
                difflib.unified_diff(
                    raw.splitlines(keepends=True),
                    new.splitlines(keepends=True),
                    fromfile=f"a/{TMPL.name}",
                    tofile=f"b/{TMPL.name}",
                    n=3,
                )
            )
        )
        print("hook-wiring-heal: DRY RUN. Re-run with --apply to write the cartridge source.")
        print("  python3 scripts/heal-hook-wiring.py --apply")
        return 1

    backup = TMPL.with_suffix(TMPL.suffix + ".bak")
    shutil.copy2(TMPL, backup)
    TMPL.write_text(new)
    print(f"hook-wiring-heal: wrote {TMPL} (backup at {backup})")

    # Idempotence: a second splice over our own output must find nothing to do.
    if splice(read_source())[1]:
        shutil.copy2(backup, TMPL)
        fail("splice is not idempotent — backup restored, source unchanged", code=1)

    if fixture:
        print("hook-wiring-heal: DOMUS_ROOT overridden — splice asserted; render check + deploy skipped")
        return 0

    return deploy(target, armed, backup=backup)


if __name__ == "__main__":
    sys.exit(main())
