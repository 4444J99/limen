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
    LIMEN_HOOK_WIRING_HEAL=1 python3 scripts/heal-hook-wiring.py    # env arm, same as --apply

EXIT
    0 ⟺ the source already carries all three assertions (or they were applied and verified).
    1 ⟺ drift found on a dry-run, or drift remains after apply.
    2 ⟺ the cartridge source could not be read/parsed.
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


def fail(msg: str, code: int = 2) -> None:
    print(f"hook-wiring-heal: {msg}", file=sys.stderr)
    sys.exit(code)


def load_source() -> tuple[str, dict]:
    if not TMPL.is_file():
        fail(f"cartridge source not found: {TMPL}")
    raw = TMPL.read_text()
    try:
        # chezmoi's {{ … }} actions live inside JSON string values here, so the template is
        # itself valid JSON. If a future edit puts an action outside a string this breaks
        # loudly rather than silently text-munging a config that governs permissions.
        return raw, json.loads(raw)
    except json.JSONDecodeError as exc:
        fail(f"{TMPL} is not parseable as JSON ({exc}); refusing to text-munge a permission file")
        raise  # unreachable, keeps type-checkers happy


def already_wired(doc: dict) -> bool:
    for group in (doc.get("hooks") or {}).get("PreToolUse") or []:
        for hook in group.get("hooks") or []:
            if "allow-trusted-cd-git.sh" in str(hook.get("command", "")):
                return True
    return False


def assert_all(doc: dict) -> list[str]:
    """Mutate doc in place. Return the list of human-readable changes made."""
    changed: list[str] = []

    hooks = doc.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    if not already_wired(doc):
        # Insert directly after the host-admission group so the fast path runs early; if that
        # group is absent (a fresh cartridge), lead the list.
        idx = 0
        for i, group in enumerate(pre):
            for hook in group.get("hooks") or []:
                if "domus-claude-host-hook" in str(hook.get("command", "")):
                    idx = i + 1
        pre.insert(idx, HOOK_GROUP)
        changed.append("wired allow-trusted-cd-git.sh into hooks.PreToolUse (matcher Bash)")

    perms = doc.setdefault("permissions", {})

    if sorted(perms.get("ask") or []) != sorted(ASK_RULES):
        perms["ask"] = list(ASK_RULES)
        changed.append("restored the five destructive permissions.ask rules (fail-safe backstop)")

    automode = perms.setdefault("autoMode", {})
    if automode.get("allow") != AUTOMODE_ALLOW:
        automode["allow"] = list(AUTOMODE_ALLOW)
        changed.append('set permissions.autoMode.allow (leads with "$defaults")')

    # Never touched — see the module docstring.
    perms.setdefault("defaultMode", "auto")

    return changed


def main() -> int:
    armed = "--apply" in sys.argv or os.environ.get("LIMEN_HOOK_WIRING_HEAL") == "1"

    raw, doc = load_source()
    changed = assert_all(doc)

    if not changed:
        print("hook-wiring-heal: clean (cartridge source already carries hook + ask + autoMode)")
        return 0

    new = json.dumps(doc, indent=2) + "\n"
    diff = "".join(
        difflib.unified_diff(
            raw.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{TMPL.name}",
            tofile=f"b/{TMPL.name}",
            n=3,
        )
    )

    for line in changed:
        print(f"hook-wiring-heal: {'applied' if armed else 'would apply'} — {line}")

    if not armed:
        print()
        print(diff)
        print("hook-wiring-heal: DRY RUN. Re-run with --apply to write the cartridge source.")
        print("  python3 scripts/heal-hook-wiring.py --apply")
        return 1

    backup = TMPL.with_suffix(TMPL.suffix + ".bak")
    shutil.copy2(TMPL, backup)
    TMPL.write_text(new)
    print(f"hook-wiring-heal: wrote {TMPL} (backup at {backup})")

    # Re-read and re-assert: proves idempotence rather than trusting the write.
    _, verify = load_source()
    if assert_all(verify):
        print("hook-wiring-heal: source still drifted after write", file=sys.stderr)
        return 1

    if DOMUS is not DEFAULT_DOMUS and DOMUS != DEFAULT_DOMUS:
        # DOMUS_ROOT was overridden (a fixture, a scratch clone). Deploying the REAL target
        # from a non-canonical source is incoherent, so assert-only and stop.
        print("hook-wiring-heal: DOMUS_ROOT overridden — source asserted, deploy skipped")
        return 0

    chezmoi = shutil.which("chezmoi")
    if not chezmoi:
        print("hook-wiring-heal: chezmoi not on PATH — run `chezmoi apply ~/.claude/settings.json`")
        return 0
    proc = subprocess.run(
        [chezmoi, "apply", str(Path.home() / ".claude" / "settings.json")],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        print(f"hook-wiring-heal: chezmoi apply failed:\n{proc.stderr}", file=sys.stderr)
        print("hook-wiring-heal: source is correct; deploy by hand with:")
        print("  chezmoi apply ~/.claude/settings.json   # add --force on out-of-band drift")
        return 1

    print("hook-wiring-heal: deployed. Hooks load at session start — restart Claude Code.")
    print("hook-wiring-heal: verify with `bash scripts/dialogs-silenced.sh`")
    return 0


if __name__ == "__main__":
    sys.exit(main())
