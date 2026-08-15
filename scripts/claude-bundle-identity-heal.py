#!/usr/bin/env python3
"""Give Claude Code sessions a STABLE macOS TCC identity by routing the versioned exec path
through the vendor's own app bundle (#1703).

THE DEFECT. TCC keys a permission grant on `(service, client, client_type, indirect_object)`.
A bundled app is keyed by bundle identifier, so Chrome updates without re-asking. The Claude Code
CLI is keyed by PATH (`client_type=1`), and the vendor names each build after its version:

    ~/.local/share/claude/versions/2.1.233

Every update therefore mints a brand-new TCC client with zero rows, and macOS re-asks the entire
grant set — Documents, Desktop, Downloads, Removable Volumes, FileProvider, Media Library,
AppleEvents, other-app data — under an "app" named `2.1.233`. Measured on this estate: 19 distinct
version identities since 2026-05-19, a bump every ~4.7 days, up to 9 dialogs each.

WHY IT IS LOCALLY FIXABLE. Three measurements, all on live system state:

  1. `csreq` is byte-identical across all 61 grant rows spanning 2.1.144 -> 2.1.233 (one distinct
     blob). The code requirement does not encode a per-version cdhash, so a new build at a stable
     path satisfies the requirement the operator already approved. Only the LOOKUP misses today.
  2. TCC resolves symlinks to the real file. Homebrew invokes ruby/python/tmux/bash/op through the
     `/opt/homebrew/bin` + `portable-ruby/current` symlink farm, and every one of them is recorded
     in TCC.db by its resolved Cellar path — never by the symlink. (An earlier probe claimed the
     opposite by measuring `ps -o comm=`, i.e. proc_pidpath, which is a DIFFERENT subsystem from
     the code-identity path TCC uses. See the correction in the receipts.)
  3. The vendor already ships the stable identity and does not route sessions through it:
     `~/.local/share/claude/ClaudeCode.app` is a complete bundle declaring
     `CFBundleIdentifier = com.anthropic.claude-code` plus AppleEvents/LocalNetwork/Microphone
     usage strings, and its `Contents/MacOS/claude` is the SAME INODE as the live
     `versions/<v>` (hardlink, `st_nlink == 2`).

THE HEAL. Replace the live `versions/<v>` hardlink with a SYMLINK to the bundle executable. The
bytes are unchanged (same inode, reached by a different name), so nothing is deleted and nothing is
copied. TCC then resolves every session's exec path to the bundle path, which never changes, and
the grant survives updates the way a normal app's does. No write to any TCC database, no change to
what the operator is asked to approve — only to how many times.

This is the local half of anthropics/claude-code#86706.

SAFETY. Only an entry that shares the bundle executable's inode is ever touched: that is by
construction the live version, and unlinking one of two names for a file destroys nothing. A stale
version with its own distinct inode is real, separate bytes (a rollback target) and is LEFT ALONE.
Dry-run is the default; `--apply` acts; the healed path is exec-verified immediately and rolled
back automatically if it does not run; `--revert` restores the hardlink exactly.

Idempotent: exit 0 with nothing to do once the live version is already a bundle symlink, which is
what makes it safe to wire onto the beat and re-run after every vendor update.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

SCHEMA = "limen.claude_bundle_identity_heal.v1"
EXPECTED_BUNDLE_ID = "com.anthropic.claude-code"

DEFAULT_ROOT = Path.home() / ".local" / "share" / "claude"


class HealError(RuntimeError):
    """A precondition failed hard enough that acting would be unsafe."""


def _bundle_executable(root: Path) -> Path:
    """The vendor's stable executable path, validated as a real bundle before we point anything at it."""
    app = root / "ClaudeCode.app"
    info = app / "Contents" / "Info.plist"
    if not info.is_file():
        raise HealError(f"no bundle Info.plist at {info}")

    declared = plistlib.loads(info.read_bytes())
    identifier = declared.get("CFBundleIdentifier")
    executable_name = declared.get("CFBundleExecutable")
    if identifier != EXPECTED_BUNDLE_ID:
        raise HealError(f"bundle identifier is {identifier!r}, expected {EXPECTED_BUNDLE_ID!r}")
    if not executable_name:
        raise HealError("bundle declares no CFBundleExecutable")

    # The DECLARED executable is what CoreFoundation resolves back to the .app. A binary merely
    # nested below Contents/MacOS resolves to its own parent directory instead — that was the
    # separately-refuted "enclosure" cure, and pointing at the wrong file would silently reproduce it.
    executable = app / "Contents" / "MacOS" / executable_name
    if not executable.is_file():
        raise HealError(f"bundle executable missing at {executable}")
    return executable


def _live_entries(versions: Path, executable: Path) -> list[Path]:
    """Version entries that are additional hardlinks to the bundle executable — i.e. the live build.

    Inode identity is the whole safety argument. A stale version is a distinct inode holding its own
    300MB of bytes; unlinking it would destroy a rollback target. Unlinking one of two names for the
    SAME inode destroys nothing at all.
    """
    if not versions.is_dir():
        raise HealError(f"no versions directory at {versions}")

    target_inode = executable.stat().st_ino
    live: list[Path] = []
    for entry in sorted(versions.iterdir()):
        if entry.is_symlink() or not entry.is_file():
            continue
        if entry.stat().st_ino == target_inode:
            live.append(entry)
    return live


def _already_healed(versions: Path, executable: Path) -> list[Path]:
    healed: list[Path] = []
    for entry in sorted(versions.iterdir()):
        if entry.is_symlink() and entry.resolve() == executable.resolve():
            healed.append(entry)
    return healed


def _exec_verify(path: Path) -> str | None:
    """Run the healed path and return its reported version, or None if it does not execute."""
    try:
        result = subprocess.run([str(path), "--version"], capture_output=True, text=True, timeout=120, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    output = result.stdout.strip() or result.stderr.strip()
    return output if result.returncode == 0 and output else None


def _relink(entry: Path, executable: Path) -> None:
    """Replace `entry` with a symlink to `executable`, atomically enough to never leave a hole."""
    staged = entry.with_name(entry.name + ".heal-staged")
    if staged.exists() or staged.is_symlink():
        staged.unlink()
    staged.symlink_to(executable)
    # os.replace over the existing hardlink: the name never stops resolving, so a session that
    # execs mid-heal gets either the old hardlink or the new symlink, never ENOENT.
    os.replace(staged, entry)


def heal(root: Path, apply: bool) -> dict:
    executable = _bundle_executable(root)
    versions = root / "versions"
    healed_already = _already_healed(versions, executable)
    live = _live_entries(versions, executable)

    actions: list[dict] = []
    for entry in live:
        record: dict = {"path": str(entry), "from": "hardlink", "to": str(executable)}
        if not apply:
            record["applied"] = False
            actions.append(record)
            continue

        _relink(entry, executable)
        reported = _exec_verify(entry)
        if reported is None:
            # The heal did not survive its own verification: put the hardlink back and say so.
            entry.unlink()
            os.link(executable, entry)
            record["applied"] = False
            record["rolled_back"] = True
            record["error"] = "healed path failed to execute; hardlink restored"
        else:
            record["applied"] = True
            record["verified_version"] = reported
        actions.append(record)

    return {
        "schema": SCHEMA,
        "bundle_executable": str(executable),
        "bundle_identifier": EXPECTED_BUNDLE_ID,
        "already_healed": [str(p) for p in healed_already],
        "actions": actions,
        "applied": apply,
        "ok": all(a.get("applied", False) for a in actions) if apply else True,
    }


def revert(root: Path, apply: bool) -> dict:
    executable = _bundle_executable(root)
    versions = root / "versions"
    actions: list[dict] = []
    for entry in _already_healed(versions, executable):
        record: dict = {"path": str(entry), "from": "symlink", "to": "hardlink"}
        if apply:
            entry.unlink()
            os.link(executable, entry)
            record["applied"] = True
        else:
            record["applied"] = False
        actions.append(record)
    return {"schema": SCHEMA, "reverted": actions, "applied": apply, "ok": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="perform the heal (default is dry-run)")
    parser.add_argument("--revert", action="store_true", help="restore hardlinks in place of bundle symlinks")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="claude install root")
    parser.add_argument("--json", action="store_true", help="emit the receipt as JSON")
    args = parser.parse_args()

    if sys.platform != "darwin":
        print("claude-bundle-identity-heal: non-darwin — inapplicable")
        return 0

    try:
        receipt = revert(args.root, args.apply) if args.revert else heal(args.root, args.apply)
    except HealError as exc:
        print(f"claude-bundle-identity-heal: PRECONDITION FAILED — {exc}")
        return 2

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if receipt["ok"] else 1

    if args.revert:
        for action in receipt["reverted"]:
            verb = "reverted" if action["applied"] else "would revert"
            print(f"  {verb} {action['path']} -> hardlink")
        if not receipt["reverted"]:
            print("claude-bundle-identity-heal: nothing to revert")
        return 0

    print(f"claude-bundle-identity-heal: bundle {receipt['bundle_executable']}")
    for path in receipt["already_healed"]:
        print(f"  already stable: {path}")
    for action in receipt["actions"]:
        if action.get("applied"):
            print(f"  HEALED {action['path']} -> bundle symlink (verified {action['verified_version']!r})")
        elif action.get("rolled_back"):
            print(f"  ROLLED BACK {action['path']} — {action['error']}")
        else:
            print(f"  would heal {action['path']} -> {action['to']}")

    if not receipt["actions"]:
        print("OK — the live version already resolves to the stable bundle identity; nothing to do")
        return 0
    if not args.apply:
        print("dry-run — re-run with --apply to give sessions the stable identity")
        return 0
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
