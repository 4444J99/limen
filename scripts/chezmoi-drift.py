#!/usr/bin/env python3
"""chezmoi-drift — surface a LOCAL config orphan, a WEDGED pipeline, or a STALE cartridge.

Sibling of ``cartridge-connected.py``. That predicate answers *is chezmoi plugged
into the real cartridge remote?*; this one answers the questions that stay green
even when the answer is broken:

  1. **Wedged pipeline** — one strict-``missingkey`` template error (e.g. a
     ``{{ if .some_key }}`` on an absent data key) aborts the *entire*
     ``chezmoi status`` / ``diff`` / ``apply`` run. Hydration stops and drift goes
     invisible, yet ``cartridge-connected`` still reads green because the *remote*
     is correct. This is the "meaningless green" trap, one layer up.

  2. **Stale cartridge** — the source checkout is parked on a non-default branch or
     behind ``origin`` HEAD. chezmoi then serves *stale* versions of every managed
     file: a fixed-on-master template is still broken locally, and a current
     deployed file reads as "drifted" against the stale source. Being *connected*
     is not being *current*.

  3. **Local orphan** — a managed target edited on disk without being re-added to
     the source (the chezmoi auto-capture hook only fires on the *Edit* tool, so a
     subagent's shell / ``Write`` / heredoc write escapes it). ``chezmoi apply``
     would silently clobber it: the edit was never durable.

    exit 0  ⟺ pipeline healthy, cartridge current, no managed target drifted
             — OR chezmoi absent / source undeterminable  (skip, fail-open)
    exit 1  ⟺ pipeline WEDGED, cartridge STALE, or an ORPHAN under ``--under``

Fail-open ONLY for a genuinely absent tool / undeterminable source (mirrors
cartridge-connected / creds-hydrate). A wedged pipeline is emphatically NOT
fail-open: a broken ``chezmoi status`` is the actionable non-zero, never a green.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys

# stderr fragments that mean the whole status/diff run aborted on a template.
_WEDGE_MARKERS = ("map has no entry for key", "template:", "at <.", "executing ")


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run a command; return (returncode, stdout, stderr). (-1, '', '') on OSError."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False, cwd=cwd)
    except (OSError, subprocess.SubprocessError):
        return -1, "", ""
    return out.returncode, out.stdout, out.stderr


def parse_drift(status_out: str) -> list[tuple[str, str]]:
    """Return [(actual_code, path)] for every target-modified line (2nd col non-space)."""
    drifted: list[tuple[str, str]] = []
    for line in status_out.splitlines():
        if len(line) < 3:
            continue
        actual = line[1]  # destination-vs-source column
        path = line[2:].strip()
        if actual != " " and path:
            drifted.append((actual, path))
    return drifted


def cartridge_staleness(source: str) -> str | None:
    """Return a human string if the source checkout is parked/stale, else None.

    Stale ⟺ on a non-default branch, or behind origin's default branch. Fail-open:
    any git indeterminacy returns None (never a false alarm)."""
    if not os.path.isdir(os.path.join(source, ".git")) and not os.path.isfile(os.path.join(source, ".git")):
        return None
    rc, head, _ = _run(["git", "-C", source, "rev-parse", "--abbrev-ref", "HEAD"])
    if rc != 0 or not head:
        return None
    head = head.strip()
    # origin's default branch (e.g. master/main)
    rc, ref, _ = _run(["git", "-C", source, "symbolic-ref", "refs/remotes/origin/HEAD"])
    default = ref.strip().rsplit("/", 1)[-1] if rc == 0 and ref.strip() else None
    if not default:
        return None
    rc, behind, _ = _run(["git", "-C", source, "rev-list", "--count", f"HEAD..origin/{default}"])
    n = behind.strip() if rc == 0 and behind.strip().isdigit() else "0"
    parts = []
    if head != default:
        parts.append(f"on non-default branch '{head}' (cartridge default is '{default}')")
    if n != "0":
        parts.append(f"{n} commit(s) behind origin/{default}")
    return "; ".join(parts) if parts else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Surface a chezmoi config orphan / wedged pipeline / stale cartridge.")
    ap.add_argument("--quiet", action="store_true", help="only print on a problem")
    ap.add_argument(
        "--under",
        default=".claude,.local/share/codex",
        help="comma-separated path prefixes whose drift makes this fail non-zero "
        "(default: .claude,.local/share/codex — the split-owned codex config is "
        "modify_-managed per the config-ownership constitution, so an app clobber "
        "of an owner atom surfaces as fatal drift here). "
        "Drift outside them is reported but non-fatal. Empty string = any drift fails.",
    )
    args = ap.parse_args()

    chezmoi = shutil.which("chezmoi")
    if not chezmoi:
        if not args.quiet:
            print("  chezmoi-drift: chezmoi not installed — skipping (fail-open)")
        return 0

    src_rc, src_out, _ = _run([chezmoi, "source-path"])
    source = src_out.strip()
    if src_rc != 0 or not source or not os.path.isdir(source):
        if not args.quiet:
            print("  chezmoi-drift: chezmoi source-path undeterminable — skipping (fail-open)")
        return 0

    stale = cartridge_staleness(source)
    rc, out, err = _run([chezmoi, "status"])
    wedged = rc != 0 and any(m in err for m in _WEDGE_MARKERS)

    if wedged:
        first = err.strip().splitlines()[0] if err.strip() else "(no detail)"
        print("  chezmoi-drift: PIPELINE WEDGED — `chezmoi status` aborted; hydration OFF, drift INVISIBLE.")
        print(f"    error: {first}")
        if stale:
            print(f"    root cause: the cartridge checkout is STALE ({stale}).")
            print("    A template fixed on the cartridge default branch is still broken in this stale checkout.")
            print(f"    Bring the cartridge current (unpark) at: {source}")
        else:
            print(f"    Fix the failing template at the source, then chezmoi un-wedges: {source}")
        return 1

    if rc == -1:
        if not args.quiet:
            print("  chezmoi-drift: `chezmoi status` unavailable — skipping (fail-open)")
        return 0

    drifted = parse_drift(out)

    if stale:
        print(f"  chezmoi-drift: STALE CARTRIDGE — {stale}.")
        print("    chezmoi is serving stale config; deployed files read as drifted against an old source.")
        print(f"    Bring the cartridge current (unpark) at: {source}")
        return 1

    if not drifted:
        if not args.quiet:
            print(f"  chezmoi-drift: OK — pipeline healthy, cartridge current, no managed target drifted ({source})")
        return 0

    prefixes = [p.strip().lstrip("/") for p in args.under.split(",") if p.strip()]
    fatal = [
        (c, p)
        for c, p in drifted
        if not prefixes or any(p.lstrip("/").startswith(pre) for pre in prefixes)
    ]
    other = [(c, p) for c, p in drifted if (c, p) not in fatal]

    label = {"M": "modified-locally", "A": "added-locally", "D": "deleted-locally"}
    print("  chezmoi-drift: LOCAL ORPHAN(S) — deployed config has drifted from the cartridge:")
    for code, path in fatal + other:
        scope = "" if (code, path) in fatal else "  (outside --under, non-fatal)"
        print(f"    {label.get(code, code)}: {path}{scope}")
    print("    An orphan is NOT durable — `chezmoi apply` will clobber it. Reconcile now:")
    print("      chezmoi re-add <path>   # capture the local edit INTO the cartridge (then commit+push)")
    print("      chezmoi apply <path>    # OR discard the orphan, restore the managed version")

    return 1 if fatal else 0


if __name__ == "__main__":
    sys.exit(main())
