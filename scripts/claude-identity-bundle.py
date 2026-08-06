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
running binary into it. When it succeeds that identity survives every vendor
update. When it throws it returns ``None`` and the identity becomes
``process.execPath``. TCC resolves a client by the bundle enclosing the path it
was exec'd from, never by the bytes: the two paths are the SAME INODE, yet only
the bundled one has an identity to resolve, so the unbundled one is named by its
own filename.

SCOPE -- what this organ does NOT fix (verified 2026-08-05 against a live process
tree, after this keeper reported ``at-ideal``):

    30699  ~/.local/bin/claude daemon run ...              (launchd-rooted)
      +- 30721  ClaudeCode.app/.../claude --bg-pty-host ... -- versions/2.1.222 ...
           +- 30826  versions/2.1.222 --session-id ...     <- disclaims; becomes "2.1.222"

The daemon runs its pty host FROM the bundle, then hands the session process its
``versions/<version>`` path as literal argv -- and that session is the one that
disclaims into its own TCC identity. So per-version consent prompts persist with
a perfectly kept bundle. That argv is composed inside the vendor binary; nothing
outside it can redirect the session onto the bundled path without patching a
signed 271MB Mach-O, which would break both its signature and auto-update. This
organ keeps the bundle correct -- a real precondition, and demonstrably not the
whole cure. Do not let a green reading here be read as "prompts are fixed."

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

SECOND SCOPE -- the Gatekeeper half (``IF-GATEKEEPER-INERT``, added 2026-08-05).
The same bundle is *also* what macOS renders as "ClaudeCode.app is damaged and
can't be opened", because a bare-Mach-O signature seals no resources
(``Sealed Resources=none``) while bundle-form ``codesign --strict`` demands a
``Contents/_CodeSignature/CodeResources`` it never sealed. The same inode passes
bare and fails bundled: the bundle is invalid BY CONSTRUCTION, every time it is
written, and cannot be made valid without re-signing a hardlink to the live
Developer-ID binary. So this organ keeping the bundle PRESENT is not in tension
with silencing that dialog -- the dialog needs a LaunchServices *registration*,
and ``execve`` needs none. ``scripts/heal-claude-lsregister.sh`` unregisters;
this keeper keeps. Deleting the bundle, which is what that effector used to do,
destroyed the very identity kept here and guaranteed the next recreate.

``inspect()`` therefore enumerates the whole vendor-bundle CLASS, not just the
store copy -- per this ledger's own rule that a count is zero "across every
service ... a lens that judges one service scores the sprawl green." What it
cannot repair (a bundle in the LaunchServices-scanned ``~/Applications`` domain)
it reports in ``class_findings`` and surfaces through ``--strict``, homed on
lever ``L-CLAUDE-DEEPLINK-REGISTRATION``. Never re-link or re-sign a vendor
bundle to "fix" it.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "limen.claude_identity_bundle.v1"
BUNDLE_NAME = "ClaudeCode.app"
BUNDLE_ID = "com.anthropic.claude-code"

# The second bundle the vendor materializes, on a 24h `startBackgroundHousekeeping()` loop rather
# than per-start. It wraps the SAME bare-signed Mach-O in a hand-written Info.plist, so it carries
# the same unassessable seal -- but it reaches the binary through a SYMLINK to the launcher
# (Contents/MacOS/claude -> ~/.local/bin/claude), not a hardlink, so it never goes stale across a
# vendor update. Its distance is registration, not freshness: it lives in ~/Applications, a
# LaunchServices-SCANNED domain, so it is permanently registered and no unregistration holds.
# The cure is the vendor's own `disableDeepLinkRegistration` setting -- lever
# L-CLAUDE-DEEPLINK-REGISTRATION -- because turning off claude-cli:// is a feature trade.
URL_HANDLER_NAME = "Claude Code URL Handler.app"

LSREGISTER = (
    "/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks"
    "/LaunchServices.framework/Support/lsregister"
)

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


def _applications_dir(env: Mapping[str, str]) -> Path:
    """Where the vendor materializes its deep-link handler bundle."""
    if override := env.get("LIMEN_CLAUDE_APPLICATIONS_DIR"):
        return Path(override)
    return _home(env) / "Applications"


def _registered_paths(env: Mapping[str, str]) -> str | None:
    """The raw LaunchServices registration dump, or None when it cannot be read.

    None is the third verdict, not a green: a run that could not ask LaunchServices
    reports `unknown` per instance rather than `not registered`. Absence of an answer
    is not an answer -- the whole reason this class recurred is that "no dialog fired"
    was read as "nothing is registered".
    """
    if env.get("LIMEN_CLAUDE_LSREGISTER_DUMP"):
        try:
            return Path(env["LIMEN_CLAUDE_LSREGISTER_DUMP"]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    if not os.access(LSREGISTER, os.X_OK):
        return None
    try:
        done = subprocess.run([LSREGISTER, "-dump"], capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout or None


def _assessable(path: Path) -> bool | None:
    """True iff Gatekeeper can assess this bundle. None when codesign is unavailable.

    A vendor bundle that wraps a BARE-signed Mach-O can never return True: the
    signature carries `Sealed Resources=none`, while bundle-form `--strict` demands a
    Contents/_CodeSignature/CodeResources it never sealed. Same inode, valid bare,
    invalid bundled. That is measured here rather than assumed.
    """
    if shutil.which("codesign") is None:
        return None
    try:
        done = subprocess.run(
            ["codesign", "--verify", "--strict", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return done.returncode == 0


def _instances(env: Mapping[str, str], binary: Path | None) -> list[dict[str, Any]]:
    """Every .app bundle the vendor materializes around the CLI binary.

    Class-wide by construction, per IF-AGENT-IDENTITY's own rule: the count is zero
    ACROSS EVERY SCANNED DOMAIN, "not merely across App Management -- a lens that
    judges one service scores the sprawl green." A keeper that watched only the store
    would report the estate clean while ~/Applications held a permanently registered,
    permanently unassessable copy.
    """
    dump = _registered_paths(env)
    candidates = [
        (_store(env) / BUNDLE_NAME, "vendor:_jb() per start", True),
        (_applications_dir(env) / URL_HANDLER_NAME, "vendor:startBackgroundHousekeeping() per 24h", False),
    ]
    found: list[dict[str, Any]] = []
    for path, source, repairable in candidates:
        record: dict[str, Any] = {
            "path": str(path),
            "source": source,
            "repairable": repairable,
            "present": path.is_dir(),
        }
        record["ls_registered"] = None if dump is None else str(path) in dump
        record["assessable"] = _assessable(path) if record["present"] else None
        link = path / "Contents/MacOS/claude"
        if binary is not None and record["present"]:
            try:
                record["inode_matches"] = link.stat().st_ino == binary.stat().st_ino
            except OSError:
                record["inode_matches"] = False
        else:
            record["inode_matches"] = None
        found.append(record)
    return found


def _class_findings(instances: list[dict[str, Any]]) -> list[str]:
    """Distance this organ MEASURES but does not have the authority to repair.

    Kept separate from `findings` so the beat step stays quiet about work it cannot
    do, while the ideal-form probe (`--strict`) still reports the honest distance.
    Same split as `concurrent_version_race_risk`: reported, never silently repaired.

    Note both operands: `ls_registered` must be exactly True and `assessable` exactly
    False. `None` on either side means the question could not be asked, and an
    unasked question is not a clean answer -- the failure mode this whole class was
    built out of was reading "no dialog fired" as "nothing is registered".
    """
    findings: list[str] = []
    if any(record["ls_registered"] is True and record["assessable"] is False for record in instances):
        findings.append("registered_unassessable_bundle")
    if any(record["present"] and record["ls_registered"] is None for record in instances):
        findings.append("registration_unmeasured")
    return findings


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
        payload.update({"ok": True, "status": "not-applicable", "findings": [], "strict_ok": True})
        return payload

    binary, error = _current_binary(values)
    payload["current_binary"] = str(binary) if binary else None
    payload["versions"] = _installed_versions(values)
    runnable = [item for item in payload["versions"] if item["runnable"]]
    payload["concurrent_version_race_risk"] = len(runnable) > 1
    payload["instances"] = _instances(values, binary)
    payload["class_findings"] = _class_findings(payload["instances"])

    findings: list[str] = []
    if error is not None:
        payload.update({"ok": False, "status": "unmeasured", "error": error, "findings": ["launcher_unresolvable"]})
        payload["strict_ok"] = False
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
    payload["strict_ok"] = not findings and not payload["class_findings"]
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
    parser.add_argument(
        "--strict",
        action="store_true",
        help="also fail on class-wide distance this organ measures but cannot repair (the IF-GATEKEEPER-INERT probe)",
    )
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
        for finding in payload.get("class_findings", []):
            print(f"  class finding: {finding} (measured here, repaired elsewhere)")
        for record in payload.get("instances", []):
            print(
                f"  instance: {record['path']} present={record['present']} "
                f"registered={record['ls_registered']} assessable={record['assessable']}"
            )
        for action in payload.get("actions", []):
            print(f"  action: {action}")
        if payload.get("concurrent_version_race_risk"):
            runnable = [item["version"] for item in payload.get("versions", []) if item["runnable"]]
            print(
                f"  advisory: {len(runnable)} runnable versions present ({', '.join(runnable)}) — concurrent starts can still race"
            )
    if args.strict:
        return 0 if payload.get("strict_ok") else 1
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
