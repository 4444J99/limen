#!/usr/bin/env python3
"""Keep Claude Code's disclaimed TCC identity on a STABLE bundle, not a rotating path.

Claude Code deliberately disclaims its inherited TCC responsibility at startup
(``process.execve(..., {macDisclaimResponsibility: true})``), so no supervising
host -- ``DomusAgentHost.app`` included -- can carry an identity into it. That is
by design: the operator should see "Claude Code" in a consent dialog, not the
terminal that happened to launch it.

Which identity it lands on is decided by one ``??`` in the vendor's own code::

    let e = await _jb() ?? process.execPath;

``_jb()`` materializes ``<store>/ClaudeCode.app`` -- a stable bundle whose
``CFBundleIdentifier`` is ``com.anthropic.claude-code`` -- and hardlinks the
running binary into it. When it succeeds the disclaimed identity is that bundle
and survives every vendor update. When it throws it returns ``None`` and the
identity becomes ``process.execPath``: ``<store>/versions/<version>``, a NEW TCC
client for every version, named by its own filename -- which is why the consent
dialog reads ``"2.1.222" would like to access ...`` instead of ``"Claude Code"``.

``_jb()`` wraps ``mkdir`` + ``writeFile`` + ``stat`` + ``unlink`` + ``link`` in a
single bare ``catch { return null }``, and it takes an EARLY RETURN when the
hardlink already has the running binary's inode::

    if ((await stat(r)).ino === n) return r;   // <- no unlink, no link, no race
    await unlink(r);
    return await link(process.execPath, r), r; // <- concurrent starts collide here

So keeping the bundle present and inode-correct is not decoration: it is what
keeps every session on the early return, where there is no window for two
concurrent starts to race the unlink/link pair into an ``EEXIST`` that silently
demotes one of them to a versioned identity.

This organ is idempotent and never edits TCC, never signs anything, and never
removes a version. It writes exactly what the vendor writes, so a live session
that runs ``_jb()`` finds its own fast path already satisfied.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "limen.claude_identity_bundle.v1"
BUNDLE_NAME = "ClaudeCode.app"
BUNDLE_ID = "com.anthropic.claude-code"

# Byte-for-byte what the vendor's `_jb()` writes. Reproduced so a keeper-written
# bundle is indistinguishable from a vendor-written one -- if these diverged, the
# vendor would rewrite the file on every start and the keeper would be noise.
INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict><key>CFBundleIdentifier</key><string>com.anthropic.claude-code</string><key>CFBundleName</key><string>Claude Code</string><key>CFBundleDisplayName</key><string>Claude Code</string><key>CFBundleExecutable</key><string>claude</string><key>CFBundlePackageType</key><string>APPL</string><key>LSUIElement</key><true/><key>NSMicrophoneUsageDescription</key><string>Claude Code uses the microphone for voice dictation.</string><key>NSAppleEventsUsageDescription</key><string>Claude Code needs to send Apple Events to open URLs and control applications you authorize.</string><key>NSLocalNetworkUsageDescription</key><string>Claude Code connects to servers and devices on your local network when commands you run need to reach them.</string></dict></plist>
"""


def _home(env: Mapping[str, str]) -> Path:
    return Path(env.get("HOME", str(Path.home())))


def _store(env: Mapping[str, str]) -> Path:
    """The Claude Code data store -- the directory holding `versions/`."""
    if override := env.get("LIMEN_CLAUDE_STORE"):
        return Path(override)
    return _home(env) / ".local/share/claude"


def _launcher(env: Mapping[str, str]) -> Path:
    if override := env.get("LIMEN_CLAUDE_LAUNCHER"):
        return Path(override)
    return _home(env) / ".local/bin/claude"


def _current_binary(env: Mapping[str, str]) -> tuple[Path | None, str | None]:
    """Resolve the version binary the launcher actually runs.

    Returns (path, error). The path must live under `<store>/versions/`, because
    that is exactly the condition under which the vendor creates a bundle at all
    (`if (!process.execPath.startsWith(join(store, "versions") + sep)) return null`).
    A launcher pointing anywhere else means the bundle path is not in play and
    there is nothing for this organ to keep.
    """
    launcher = _launcher(env)
    try:
        resolved = launcher.resolve(strict=True)
    except OSError:
        return None, f"launcher is unresolvable: {launcher}"
    versions = (_store(env) / "versions").resolve(strict=False)
    if not resolved.is_relative_to(versions):
        return None, f"launcher does not resolve under {versions}: {resolved}"
    if not os.access(resolved, os.X_OK):
        return None, f"resolved binary is not executable: {resolved}"
    return resolved, None


def _installed_versions(env: Mapping[str, str]) -> list[dict[str, Any]]:
    """Every runnable version in the store.

    More than one is a standing race risk this organ cannot remove: two DIFFERENT
    versions running concurrently have different inodes, so each start unlinks the
    other's hardlink and re-links its own, reopening the very window the early
    return exists to avoid. Reported, never silently repaired -- deleting a vendor
    version is not this organ's authority.
    """
    root = _store(env) / "versions"
    found: list[dict[str, Any]] = []
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return found
    for entry in entries:
        try:
            info = entry.stat()
        except OSError:
            continue
        if not entry.is_file():
            continue
        found.append(
            {
                "version": entry.name,
                "size_bytes": info.st_size,
                "runnable": bool(info.st_size) and os.access(entry, os.X_OK),
            }
        )
    return found


def inspect(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Read-only state of the identity bundle. Never mutates."""
    values = os.environ if env is None else env
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "platform": platform.system(),
        "platform_supported": platform.system() == "Darwin",
        "bundle_path": str(_store(values) / BUNDLE_NAME),
        "bundle_id": BUNDLE_ID,
    }
    if not payload["platform_supported"]:
        payload.update({"ok": True, "status": "not-applicable", "findings": []})
        return payload

    binary, error = _current_binary(values)
    payload["current_binary"] = str(binary) if binary else None
    payload["versions"] = _installed_versions(values)
    runnable = [item for item in payload["versions"] if item["runnable"]]
    payload["concurrent_version_race_risk"] = len(runnable) > 1

    findings: list[str] = []
    if error is not None:
        payload.update({"ok": False, "status": "unmeasured", "error": error, "findings": ["launcher_unresolvable"]})
        return payload

    assert binary is not None
    bundle = _store(values) / BUNDLE_NAME
    plist = bundle / "Contents/Info.plist"
    link = bundle / "Contents/MacOS/claude"

    payload["bundle_present"] = bundle.is_dir()
    if not payload["bundle_present"]:
        findings.append("bundle_absent")

    try:
        payload["info_plist_matches"] = plist.read_text(encoding="utf-8") == INFO_PLIST
    except OSError:
        payload["info_plist_matches"] = False
    if not payload["info_plist_matches"]:
        findings.append("info_plist_missing_or_divergent")

    try:
        payload["hardlink_inode_matches"] = link.stat().st_ino == binary.stat().st_ino
    except OSError:
        payload["hardlink_inode_matches"] = False
    if not payload["hardlink_inode_matches"]:
        findings.append("hardlink_absent_or_stale")

    payload["findings"] = findings
    payload["ok"] = not findings
    payload["status"] = "at-ideal" if not findings else "distance-remains"
    return payload


def repair(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Make the bundle present and inode-correct. Idempotent.

    Performs exactly the vendor's own operations, in the vendor's own order, so a
    repaired bundle is byte-identical to one `_jb()` would have produced.
    """
    values = os.environ if env is None else env
    before = inspect(values)
    if not before.get("platform_supported") or before.get("status") == "unmeasured":
        before["actions"] = []
        return before

    binary, error = _current_binary(values)
    if error is not None or binary is None:
        before["actions"] = []
        return before

    bundle = _store(values) / BUNDLE_NAME
    macos = bundle / "Contents/MacOS"
    plist = bundle / "Contents/Info.plist"
    link = macos / "claude"
    actions: list[str] = []

    macos.mkdir(parents=True, exist_ok=True)
    if not before.get("bundle_present"):
        actions.append("created_bundle_directory")
    if not before.get("info_plist_matches"):
        plist.write_text(INFO_PLIST, encoding="utf-8")
        actions.append("wrote_info_plist")
    if not before.get("hardlink_inode_matches"):
        try:
            link.unlink()
            actions.append("removed_stale_hardlink")
        except FileNotFoundError:
            pass
        os.link(binary, link)
        actions.append("linked_current_binary")

    after = inspect(values)
    after["actions"] = actions
    after["repaired"] = bool(actions)
    return after


RECEIPT = Path(__file__).resolve().parents[1] / "logs/claude-identity-bundle-status.json"


def _write_receipt(payload: Mapping[str, Any]) -> None:
    """Durable owner receipt for the beat's omega rung.

    Best-effort: a keeper that cannot write its log must still keep the bundle, so
    a failure here never changes the exit code. The rung reads `observed_at` as a
    volatile field, so an unchanged bundle produces a stable fixed point.
    """
    try:
        RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        document = dict(payload)
        document["observed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
        RECEIPT.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repair", action="store_true", help="make the bundle present and inode-correct")
    parser.add_argument("--json", action="store_true", help="emit the full payload as JSON")
    args = parser.parse_args(argv)

    payload = repair() if args.repair else inspect()
    _write_receipt(payload)

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(f"claude identity bundle: {payload.get('status')}")
        print(f"  bundle: {payload.get('bundle_path')} ({BUNDLE_ID})")
        if payload.get("current_binary"):
            print(f"  current binary: {payload['current_binary']}")
        if payload.get("error"):
            print(f"  error: {payload['error']}")
        for finding in payload.get("findings", []):
            print(f"  finding: {finding}")
        for action in payload.get("actions", []):
            print(f"  action: {action}")
        if payload.get("concurrent_version_race_risk"):
            runnable = [item["version"] for item in payload.get("versions", []) if item["runnable"]]
            print(f"  advisory: {len(runnable)} runnable versions present ({', '.join(runnable)}) — concurrent starts can still race")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
