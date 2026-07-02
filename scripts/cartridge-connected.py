#!/usr/bin/env python3
"""cartridge-connected — assert the host's chezmoi source IS the real cartridge.

The factory/cartridge invariant (memory: host-is-factory-system-is-cartridge)
requires that ``chezmoi`` point at the sovereign cartridge repo
(``organvm/domus-genoma``) — never a scratch / dummy / local source. Without this
check the invariant fails *silently*: an agent that homes a few tools in a throwaway
chezmoi source (e.g. a local ``dummy-remote.git``) leaves ``chezmoi verify`` /
``chezmoi status`` green, because they only validate *whatever* source is wired —
and ``chezmoi-health`` only reports ahead/behind of *whatever* remote that source
has. So a completely disconnected cartridge returns a meaningless ✓.

This predicate closes that gap. It runs regardless of chezmoi's state and answers
the one question nothing else does: **is chezmoi pointed at the real cartridge?**

    exit 0  ⟺ source remote == the expected cartridge repo  (connected)
             — OR chezmoi is absent / source undeterminable  (skip, fail-open)
    exit 1  ⟺ source is a scratch / dummy / local / mismatched remote (UNPLUGGED)

Fail-open by design (mirrors creds-hydrate/mcp-auth-verify in metabolize.sh): a
missing tool or offline host must never break the beat; only a genuine
disconnection is the actionable non-zero.

Override the expected repo with ``LIMEN_CARTRIDGE_REPO=owner/repo`` so another
person's prosthesis (their fork) validates against their own cartridge — the
default is derived, not pinned per host.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys

DEFAULT_CARTRIDGE = "organvm/domus-genoma"


def _run(cmd: list[str]) -> str | None:
    """Run a command, return stripped stdout, or None on any failure."""
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def normalize_remote(url: str) -> str | None:
    """Reduce a git remote URL to ``owner/repo`` (lowercased), or None if it is
    not a hosted repo (a bare local path, a dummy scratch, etc.)."""
    url = url.strip()
    if not url:
        return None
    # A local filesystem path is never the cartridge (that is the scratch failure mode).
    if url.startswith((".", "/", "~")) or url.startswith("file:"):
        return None
    # git@host:owner/repo(.git)  |  ssh://…/owner/repo  |  https://host/owner/repo(.git)
    m = re.search(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$", url)
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    return f"{owner}/{repo}".lower()


def main() -> int:
    ap = argparse.ArgumentParser(description="Assert chezmoi is plugged into the real cartridge.")
    ap.add_argument("--quiet", action="store_true", help="only print on failure")
    args = ap.parse_args()

    expected = os.environ.get("LIMEN_CARTRIDGE_REPO", DEFAULT_CARTRIDGE).strip().lower()

    chezmoi = shutil.which("chezmoi")
    if not chezmoi:
        if not args.quiet:
            print("  cartridge-connected: chezmoi not installed — skipping (fail-open)")
        return 0

    source = _run([chezmoi, "source-path"])
    if not source or not os.path.isdir(source):
        if not args.quiet:
            print("  cartridge-connected: chezmoi source-path undeterminable — skipping (fail-open)")
        return 0

    # Prefer origin; fall back to the first configured remote.
    remote = _run(["git", "-C", source, "remote", "get-url", "origin"])
    if not remote:
        names = _run(["git", "-C", source, "remote"])
        first = names.splitlines()[0].strip() if names else None
        remote = _run(["git", "-C", source, "remote", "get-url", first]) if first else None

    if not remote:
        print(
            f"  cartridge-connected: FAIL — source {source} has no git remote "
            f"(a local scratch source, not the {expected} cartridge)"
        )
        return 1

    actual = normalize_remote(remote)
    if actual == expected or (actual and actual.split("/")[-1] == expected.split("/")[-1]):
        if not args.quiet:
            print(f"  cartridge-connected: OK — chezmoi source is {expected} ({source})")
        return 0

    shown = actual or remote
    print(f"  cartridge-connected: FAIL — chezmoi source is '{shown}', expected '{expected}'.")
    print(f"    source dir: {source}")
    print("    The cartridge is UNPLUGGED: chezmoi is managing a scratch/wrong source, so")
    print("    chezmoi verify/status/health are all meaninglessly green. Re-point without")
    print("    broad apply after the cartridge is current:")
    print("      chezmoi init --source ~/Workspace/domus-genoma --data --promptDefaults")
    print("    Then run a targeted diff before any apply.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
