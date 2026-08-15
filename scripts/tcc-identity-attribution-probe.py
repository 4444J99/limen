#!/usr/bin/env python3
"""Guard the two REFUTED cures for Claude Code's rotating per-version TCC identity (#1703).

macOS names a disclaimed process's TCC client by the bundle enclosing the path it was exec'd
from, else by that path itself. Claude Code sessions exec `versions/<v>` and disclaim, so each
vendor update mints a new privacy client and re-asks the whole grant set. Two local cures look
obvious, and BOTH were measured false on 2026-08-15 before either shipped:

  A. ENCLOSURE — move the version store to ClaudeCode.app/Contents/MacOS/versions and symlink
     the old path, hoping the bundle lookup walks up to the .app.
     REFUTED: CoreFoundation resolves a binary nested one level below Contents/MacOS to its
     immediate PARENT DIRECTORY, exactly as it resolves a loose binary. Bundle identity
     attaches only to the declared CFBundleExecutable.

  B. SYMLINK — replace versions/<v> with a symlink to the bundle's main executable, hoping the
     kernel records the resolved target.
     REFUTED: the kernel records the path used at exec (the symlink's own path); only the
     underlying vnode (lsof txt) shows the target.

This probe re-measures both. It is a RATCHET ON A NEGATIVE RESULT: exit 0 means the refutations
still hold and neither cure is worth re-proposing; exit 1 means macOS behavior CHANGED and the
finding must be revisited. That is the point — a negative result with no predicate decays into
folklore, and the next session re-derives it at full cost (this estate has already shipped five
cures against one false premise; see IF-GATEKEEPER-INERT).

The terminal cure is upstream: anthropics/claude-code#86706. Receipts:
docs/receipts/tcc-track-c-1703/README.md.

Safe by construction: builds throwaway fixtures in a temp dir, execs nothing but a symlink to
/bin/sleep, touches no protected resource, and triggers no TCC prompt.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.util
import json
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BUNDLE_INFO = {
    "CFBundleExecutable": "tool",
    "CFBundleIdentifier": "org.limen.tcc-attribution-probe",
    "CFBundleName": "AttributionProbe",
    "CFBundlePackageType": "APPL",
}

# kCFURLPOSIXPathStyle / kCFStringEncodingUTF8
_POSIX_PATH_STYLE = 0
_UTF8 = 0x08000100


def _corefoundation():
    cf = ctypes.CDLL(ctypes.util.find_library("CoreFoundation"))
    cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
    cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_long,
        ctypes.c_bool,
    ]
    cf.CFURLCopyFileSystemPath.restype = ctypes.c_void_p
    cf.CFURLCopyFileSystemPath.argtypes = [ctypes.c_void_p, ctypes.c_int]
    cf.CFStringGetCString.restype = ctypes.c_bool
    cf.CFStringGetCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32]
    cf.CFRelease.argtypes = [ctypes.c_void_p]
    return cf


def _bundle_for_executable(cf, path: Path) -> str | None:
    """The bundle CoreFoundation attributes an executable to, or its parent when there is none."""
    resolver = getattr(cf, "_CFBundleCopyBundleURLForExecutableURL", None)
    if resolver is None:
        return None
    resolver.restype = ctypes.c_void_p
    resolver.argtypes = [ctypes.c_void_p]

    raw = str(path).encode()
    url = cf.CFURLCreateFromFileSystemRepresentation(None, raw, len(raw), False)
    try:
        found = resolver(url)
        if not found:
            return None
        string = cf.CFURLCopyFileSystemPath(found, _POSIX_PATH_STYLE)
        if not string:
            return None
        buf = ctypes.create_string_buffer(4096)
        ok = cf.CFStringGetCString(string, buf, 4096, _UTF8)
        cf.CFRelease(string)
        return buf.value.decode() if ok else None
    finally:
        cf.CFRelease(url)


def measure_enclosure(tmp: Path) -> dict:
    """Cure A: does a binary nested below Contents/MacOS inherit the enclosing bundle?"""
    cf = _corefoundation()
    app = tmp / "AttributionProbe.app"
    macos = app / "Contents" / "MacOS"
    (macos / "versions").mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(BUNDLE_INFO))

    main_exec = macos / "tool"
    nested = macos / "versions" / "0.0.0"
    loose = tmp / "loose-binary"
    for target in (main_exec, nested, loose):
        shutil.copy("/bin/echo", target)

    control = _bundle_for_executable(cf, main_exec)
    subject = _bundle_for_executable(cf, nested)
    baseline = _bundle_for_executable(cf, loose)

    return {
        "cure": "enclosure",
        "control_is_bundle": control == str(app),
        "control": control,
        "subject": subject,
        "loose_baseline": baseline,
        # Refuted <=> the nested binary does NOT resolve to the .app.
        "refuted": subject != str(app),
        "inconclusive": control != str(app),
    }


def measure_symlink(tmp: Path) -> dict:
    """Cure B: does an exec through a symlink record the resolved target or the symlink path?"""
    link = tmp / "version-shaped-symlink"
    link.symlink_to("/bin/sleep")

    proc = subprocess.Popen([str(link), "30"])
    recorded = None
    vnode = None
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            out = subprocess.run(["ps", "-p", str(proc.pid), "-o", "comm="], capture_output=True, text=True)
            candidate = out.stdout.strip()
            if candidate and candidate != "<defunct>":
                recorded = candidate
                break
            time.sleep(0.05)
        listing = subprocess.run(
            ["lsof", "-p", str(proc.pid), "-a", "-d", "txt"], capture_output=True, text=True
        ).stdout.splitlines()
        if len(listing) > 1:
            vnode = listing[1].split()[-1]
    finally:
        proc.kill()
        proc.wait()

    return {
        "cure": "symlink",
        "recorded_executable_path": recorded,
        "underlying_vnode": vnode,
        # Refuted <=> the kernel records the SYMLINK path, not the target.
        "refuted": recorded == str(link),
        "inconclusive": recorded is None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true", help="emit the measurements as JSON")
    args = parser.parse_args()

    if sys.platform != "darwin":
        print("tcc-identity-attribution-probe: non-darwin — inapplicable")
        return 0

    tmp = Path(tempfile.mkdtemp(prefix="tcc-attribution-probe-"))
    try:
        findings = [measure_enclosure(tmp), measure_symlink(tmp)]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if args.json:
        print(
            json.dumps({"schema": "limen.tcc_identity_attribution.v1", "findings": findings}, indent=2, sort_keys=True)
        )
        return 0 if all(f["refuted"] for f in findings) else 1

    inconclusive = [f for f in findings if f["inconclusive"]]
    if inconclusive:
        for finding in inconclusive:
            print(f"tcc-identity-attribution-probe: INCONCLUSIVE for cure '{finding['cure']}' — {finding}")
        return 2

    print("tcc-identity-attribution-probe:")
    enclosure, symlink = findings
    print(
        f"  enclosure — nested binary resolves to {enclosure['subject']!r}; "
        f"the .app itself resolves for the declared executable ({enclosure['control_is_bundle']})"
    )
    print(
        f"  symlink   — kernel records {symlink['recorded_executable_path']!r}; "
        f"underlying vnode is {symlink['underlying_vnode']!r}"
    )

    if all(f["refuted"] for f in findings):
        print("OK — both local cures remain REFUTED; the fix stays upstream (anthropics/claude-code#86706)")
        return 0

    revived = [f["cure"] for f in findings if not f["refuted"]]
    print(f"CHANGED — macOS no longer refutes: {', '.join(revived)}. Re-open the local cure and re-measure.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
