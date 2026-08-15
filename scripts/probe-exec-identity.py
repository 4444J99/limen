#!/usr/bin/env python3
"""Which path does the kernel record for a binary exec'd via bundle / hardlink / symlink?

Load-bearing for the rotating-TCC-identity cure (memory: tcc-prompts-upstream-blocked, lever
L-DIALOGS-HEAL). TCC attributes a client by the running process's recorded executable path.
Today the vendor materializes `~/.local/share/claude/versions/<v>` as a HARDLINK of the same
inode as `ClaudeCode.app/Contents/MacOS/claude`. The proposed cure replaces that with a
SYMLINK into the bundle. This probe measures what the kernel actually records.

Arms (each in its OWN root with its OWN inode, so arms cannot alias each other):
  A  bundle only, no other link           exec the bundle exec   -> baseline
  B  bundle + hardlink outside (TODAY)    exec the BUNDLE exec   -> does the outside name leak in?
  C  bundle + hardlink outside (TODAY)    exec the HARDLINK      -> today's rotating identity
  D  bundle + symlink outside (PROPOSED)  exec the SYMLINK       -> does the cure resolve?

Two fixture rules, both learned the hard way (2026-08-15):

1. NEVER use a copy of an Apple binary as the fixture. /bin/sleep and /bin/echo are PLATFORM
   binaries (`codesign -dv` -> `Platform identifier=26`) carrying a launch constraint that
   pins them to their canonical path. Exec'd from a copied path the kernel SIGKILLs them at
   exec (EXC_CRASH, Namespace CODESIGNING Code 4, Launch Constraint Violation). The first
   version of this probe did exactly that and read the corpse's path as None three times,
   misreading it as a ctypes/proc_pidpath bug. Fixture is now compiled locally (adhoc,
   linker-signed), which carries no such constraint.

2. NEVER share an inode across arms. proc_pidpath resolves a vnode through the name cache,
   so a multiply-linked inode reports an ARBITRARY alias. The second version linked all
   three arms to one inode and every arm reported the hardlink's name.

Both defects fail the same way: a broken fixture that reads as a measurement. Hence the
liveness assertion below — a dead child raises FixtureError, it never returns a datum.

Safe: throwaway temp dirs, no protected resource touched, no TCC prompt.
"""

from __future__ import annotations

import ctypes
import os
import plistlib
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

INFO = {
    "CFBundleExecutable": "tool",
    "CFBundleIdentifier": "org.limen.enclosureprobe",
    "CFBundleName": "Test",
    "CFBundlePackageType": "APPL",
}
FIXTURE_C = "#include <unistd.h>\nint main(void){ sleep(30); return 0; }\n"

libc = ctypes.CDLL(None)
libc.proc_pidpath.restype = ctypes.c_int
libc.proc_pidpath.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32]


class FixtureError(RuntimeError):
    """The child never ran. Never report this as an inconclusive measurement."""


def recorded_path(pid: int) -> str | None:
    buf = ctypes.create_string_buffer(4096)
    n = libc.proc_pidpath(pid, buf, 4096)
    return buf.value.decode() if n > 0 else None


def launch_and_read(path: Path) -> str:
    """Spawn `path`, ASSERT the child is alive, then read the kernel-recorded path."""
    proc = subprocess.Popen([str(path)])
    try:
        time.sleep(0.4)
        if proc.poll() is not None:
            raise FixtureError(
                f"child for {path} exited before measurement (returncode={proc.returncode}). "
                "The fixture is broken, not the measurement — check `codesign -dv` for a "
                "platform-binary launch constraint."
            )
        got = recorded_path(proc.pid)
        if not got:
            raise FixtureError(f"proc_pidpath returned nothing for LIVE pid {proc.pid}")
        return got
    finally:
        proc.kill()
        proc.wait()


def build_root(compiled: Path, *, with_hardlink: bool = False, with_symlink: bool = False):
    """Fresh root with a fresh inode for the bundle executable."""
    root = Path(tempfile.mkdtemp(prefix="encl-arm-"))
    app = root / "Test.app"
    macos = app / "Contents" / "MacOS"
    macos.mkdir(parents=True)
    (app / "Contents" / "Info.plist").write_bytes(plistlib.dumps(INFO))
    main_exec = macos / "tool"
    shutil.copy(compiled, main_exec)
    outside = root / "versions"
    outside.mkdir()
    hard = sym = None
    if with_hardlink:
        hard = outside / "2.1.233"
        os.link(main_exec, hard)
    if with_symlink:
        sym = outside / "2.1.233"
        sym.symlink_to(main_exec)
    return root, main_exec, hard, sym


def rel(root: Path, p: str) -> str:
    return p.replace("/private" + str(root), "<root>").replace(str(root), "<root>")


def discriminate_code_identity() -> tuple[int, int]:
    """Arm E — which path does the KERNEL's code-identity layer use for a symlink?

    proc_pidpath and `ps -o comm=` disagree for a symlinked exec: the first reports the
    vnode (the target), the second the accounting string (the link). Neither settles which
    one a TCC client identity derives from, because both are just strings we chose to read.

    A platform binary's launch constraint settles it, because the outcome is binary and the
    kernel — not us — decides it. /bin/sleep is constrained to its canonical path:
      * a COPY at another path -> SIGKILL, constraint evaluated against the copy's path
      * a SYMLINK at another path -> runs IFF the kernel resolved it to /bin/sleep first
    So a surviving symlink is direct evidence that code identity follows the target.
    """
    root = Path(tempfile.mkdtemp(prefix="encl-discriminator-"))
    try:
        copy = root / "copy-of-sleep"
        shutil.copy("/bin/sleep", copy)
        copy_rc = subprocess.run([str(copy), "0.3"], capture_output=True).returncode

        link = root / "symlink-to-sleep"
        link.symlink_to("/bin/sleep")
        link_rc = subprocess.run([str(link), "0.3"], capture_output=True).returncode
        return copy_rc, link_rc
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> int:
    roots: list[Path] = []
    try:
        stage = Path(tempfile.mkdtemp(prefix="encl-build-"))
        roots.append(stage)
        (stage / "fixture.c").write_text(FIXTURE_C)
        compiled = stage / "fixture"
        cc = subprocess.run(["cc", "-o", str(compiled), str(stage / "fixture.c")], capture_output=True, text=True)
        if cc.returncode != 0:
            raise FixtureError(f"cc failed: {cc.stderr.strip()}")

        print("== kernel-recorded exec path, one isolated inode per arm ==\n")

        root, main_exec, _, _ = build_root(compiled)
        roots.append(root)
        a = launch_and_read(main_exec)
        print(f"  A  bundle exec, no other link   -> {rel(root, a)}")

        root, main_exec, hard, _ = build_root(compiled, with_hardlink=True)
        roots.append(root)
        b = launch_and_read(main_exec)
        print(f"  B  hardlink exists, exec bundle -> {rel(root, b)}")

        root, main_exec, hard, _ = build_root(compiled, with_hardlink=True)
        roots.append(root)
        c = launch_and_read(hard)
        print(f"  C  exec the hardlink (today)    -> {rel(root, c)}")

        root, main_exec, _, sym = build_root(compiled, with_symlink=True)
        roots.append(root)
        d = launch_and_read(sym)
        print(f"  D  exec the symlink (proposed)  -> {rel(root, d)}")

        print("\n== verdicts ==")
        print("  A baseline records: " + ("the bundle path" if a.endswith("MacOS/tool") else f"UNEXPECTED {a}"))
        print(
            "  B outside-name leak: "
            + ("YES — the hardlink alias leaks into a bundle exec" if "/versions/" in b else "no — bundle path held")
        )
        print(
            "  C hardlink records: "
            + ("the versions path (rotating identity)" if "/versions/" in c else "the bundle path")
        )
        if d.endswith("Test.app/Contents/MacOS/tool"):
            print("  D symlink: proc_pidpath records the BUNDLE path (the target)")
        elif d.endswith("/versions/2.1.233"):
            print("  D symlink: proc_pidpath records the symlink's own path")
        else:
            print(f"  D UNEXPECTED -> {d}")

        copy_rc, link_rc = discriminate_code_identity()
        # subprocess reports a signal as -N; a shell reports it as 128+N. Accept both.
        copy_killed = copy_rc in (-9, 137)
        print()
        print("== arm E: code-identity discriminator (platform-binary launch constraint) ==")
        print(
            f"  copy of /bin/sleep at a temp path     -> exit {copy_rc}"
            + ("  (SIGKILL — constraint violated)" if copy_killed else "")
        )
        print(
            f"  symlink to /bin/sleep at a temp path  -> exit {link_rc}"
            + ("  (constraint SATISFIED)" if link_rc == 0 else "")
        )
        if copy_killed and link_rc == 0:
            print("  => code identity RESOLVES the symlink to its target.")
            print("     `ps -o comm=` reports the link, but it is the accounting string,")
            print("     not the identity. The symlink cure is NOT refuted.")
            return 0
        print("  => DISCRIMINATOR CHANGED — re-derive the finding before trusting it.")
        return 1
    except FixtureError as e:
        print(f"FIXTURE ERROR: {e}")
        return 3
    finally:
        for r in roots:
            shutil.rmtree(r, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
