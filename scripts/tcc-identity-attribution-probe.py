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
     system attributes the resolved target.
     UNRESOLVED (amended 2026-08-15; this arm previously read REFUTED). The original verdict
     compared `ps -o comm=` against the link's path. That is the kernel's ACCOUNTING STRING
     (p_comm), not the code identity a TCC client derives from — and it holds regardless of
     the deciding layer, so it could never have detected a change. The discriminator that does
     decide is a platform binary's launch constraint: a COPY of /bin/sleep at another path is
     SIGKILLed, while a SYMLINK at that same path RUNS — which is possible only if the kernel
     resolved the link to /bin/sleep before judging it. So code identity follows the target.
     Still required before anything ships: an end-to-end test that triggers a protected access
     from a symlinked binary and reads the resulting `client` column in the TCC db.

This probe re-measures both, each on its deciding layer. Exit 0 means the enclosure refutation
still holds AND code identity still resolves symlinks; exit 1 means macOS behavior CHANGED and
the finding must be revisited. That is the point — a result with no predicate decays into
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


def _code_identity_resolves_symlink(tmp: Path) -> bool | None:
    """Does the KERNEL's code-identity layer resolve a symlink before judging the binary?

    `ps -o comm=` and `proc_pidpath` disagree for a symlinked exec, and neither settles which
    one a TCC client derives from — both are strings we chose to read. A platform binary's
    launch constraint settles it, because the kernel decides the outcome and it is binary.
    /bin/sleep is constrained to its canonical path, so:

      * a COPY at another path is SIGKILLed  — the constraint saw the copy's path
      * a SYMLINK at another path RUNS       — only possible if it resolved to /bin/sleep

    Returns True when the layer resolves to the target, False when it does not, None when the
    fixture itself failed to behave (neither arm behaved as the constraint requires).
    """
    copy = tmp / "constraint-copy"
    shutil.copy("/bin/sleep", copy)
    copy_rc = subprocess.run([str(copy), "0.3"], capture_output=True).returncode

    link = tmp / "constraint-symlink"
    link.symlink_to("/bin/sleep")
    link_rc = subprocess.run([str(link), "0.3"], capture_output=True).returncode

    # subprocess reports a signal as -N; a shell would report 128+N. Accept both.
    copy_killed = copy_rc in (-9, 137)
    if not copy_killed:
        return None  # the constraint did not fire at all — fixture assumption broken
    return link_rc == 0


def measure_symlink(tmp: Path) -> dict:
    """Cure B: which path does the system attribute to an exec through a symlink?

    AMENDED 2026-08-15. The original verdict compared `ps -o comm=` against the link's path
    and called the cure refuted. That comparison is correct about `p_comm` — the kernel's
    ACCOUNTING STRING — and `p_comm` is not what a TCC client identity derives from. It will
    also hold forever regardless of the deciding layer, so as a ratchet it could never detect
    the change it existed to watch for. The code-identity discriminator below is what decides,
    and it currently shows the symlink RESOLVING to its target: cure B is not refuted, it is
    unresolved pending an end-to-end TCC-db test.
    """
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

    resolves = _code_identity_resolves_symlink(tmp)

    return {
        "cure": "symlink",
        "accounting_string_p_comm": recorded,
        "underlying_vnode": vnode,
        # The deciding layer: does code identity follow the symlink to its target?
        "code_identity_resolves_target": resolves,
        # NOT refuted while code identity resolves the target. Kept as an explicit key so a
        # reader never has to infer the verdict from the accounting string again.
        "refuted": resolves is False,
        "status": "unresolved — pending an end-to-end TCC-db attribution test",
        "inconclusive": recorded is None or resolves is None,
    }


def _ratchet_holds(findings: list[dict]) -> bool:
    """The ratchet watches each cure on the layer that actually decides it.

    Enclosure: stays refuted (CoreFoundation attribution).
    Symlink:   stays unresolved WITH code identity resolving the target. If macOS ever stops
               resolving, the cure becomes genuinely refuted — and that is a change worth
               failing on, because the receipt would then be wrong in the other direction.
    """
    by_cure = {f["cure"]: f for f in findings}
    return by_cure["enclosure"]["refuted"] and by_cure["symlink"]["code_identity_resolves_target"] is True


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
            # v2: the symlink finding reports the deciding layer
            # (`code_identity_resolves_target`) and renames the old `recorded_executable_path`
            # to `accounting_string_p_comm`, so no reader mistakes p_comm for an identity.
            json.dumps({"schema": "limen.tcc_identity_attribution.v2", "findings": findings}, indent=2, sort_keys=True)
        )
        return 0 if _ratchet_holds(findings) else 1

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
        f"  symlink   — accounting string (p_comm) is {symlink['accounting_string_p_comm']!r}; "
        f"underlying vnode is {symlink['underlying_vnode']!r}; "
        f"code identity resolves the target: {symlink['code_identity_resolves_target']}"
    )

    if _ratchet_holds(findings):
        print("OK — enclosure stays REFUTED; symlink stays UNRESOLVED with code identity")
        print("     resolving the target. Terminal fix remains upstream (anthropics/claude-code#86706).")
        return 0

    if not enclosure["refuted"]:
        print("CHANGED — macOS no longer refutes the ENCLOSURE cure. Re-open it and re-measure.")
    if symlink["code_identity_resolves_target"] is not True:
        print("CHANGED — code identity no longer resolves a symlink to its target.")
        print("          The symlink cure becomes genuinely refuted; record that and stop.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
