#!/usr/bin/env python3
"""profile-bio-sync.py — give the GitHub profile SETTINGS an owner so they stop rotting.

The profile README self-heals every build (every number is recomputed from the live API). The
GitHub account *settings* did not: the **bio** froze at stale daily counts ("91 repos, 3,586 code
files, ...") and the **website link** sat as a dead 404 (4444j99.github.io/portfolio) — both because
nothing owned them. This makes positioning-seeds.json `frontdoor.{bio,blog}` the single source of
truth and applies them; the website link is verified to resolve 200 before it's ever written, so a
dead link can't be published.

    python scripts/profile-bio-sync.py            # apply canonical bio + blog (needs the gh `user` scope)
    python scripts/profile-bio-sync.py --check     # report drift only; exit 1 if any live != canonical

Writing account settings needs the OAuth `user` scope (repo/workflow tokens can't). When absent, this
reports the exact one-command remediation and exits 0 (non-fatal) — drift is surfaced, never silently
swallowed, and never blocks a build.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parents[1]))
SEEDS = ROOT / "positioning-seeds.json"
REFRESH_HINT = "gh auth refresh -h github.com -s user"

# GitHub account fields this organ owns. verify_url => the value must resolve 200 before it's written
# (a website link that 404s must never be published — the exact failure that put a dead portfolio link
# on the profile).
FIELDS = {
    "bio": {"verify_url": False, "max_len": 160},
    "blog": {"verify_url": True, "max_len": 255},
}


def canonical(field: str) -> str:
    try:
        seeds = json.loads(SEEDS.read_text(encoding="utf-8"))
        return str(seeds.get("frontdoor", {}).get(field) or "").strip()
    except Exception as exc:
        print(f"profile-bio-sync: cannot read {SEEDS}: {exc}", file=sys.stderr)
        return ""


def live(field: str) -> str:
    proc = subprocess.run(
        ["gh", "api", "user", "--jq", f".{field}"], capture_output=True, text=True, stdin=subprocess.DEVNULL
    )
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def resolves_200(url: str) -> bool:
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status == 200
        except Exception:
            continue
    return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Own + apply the GitHub profile settings from positioning-seeds.json.")
    ap.add_argument("--check", action="store_true", help="report drift only; exit 1 if any live != canonical")
    args = ap.parse_args(argv)

    patch: dict[str, str] = {}
    drift = False
    for field, spec in FIELDS.items():
        want = canonical(field)
        if not want:
            continue
        if len(want) > spec["max_len"]:
            print(
                f"profile-bio-sync: canonical {field} is {len(want)} chars (> {spec['max_len']}) — trim it.",
                file=sys.stderr,
            )
            return 2
        if spec["verify_url"] and not resolves_200(want):
            print(
                f"profile-bio-sync: canonical {field} {want!r} does NOT resolve 200 — refusing to publish a dead "
                "link. Fix frontdoor.blog in positioning-seeds.json.",
                file=sys.stderr,
            )
            return 2
        have = live(field)
        if have == want:
            continue
        drift = True
        if args.check:
            print(f"profile-bio-sync: DRIFT [{field}] — live {have!r} != canonical {want!r}")
        else:
            patch[field] = want

    if not drift:
        print("profile-bio-sync: profile settings in sync with canonical (bio + website link).")
        return 0
    if args.check:
        return 1

    args_gh = ["gh", "api", "-X", "PATCH", "user"]
    for field, value in patch.items():
        args_gh += ["-f", f"{field}={value}"]
    proc = subprocess.run([*args_gh, "--jq", "{bio,blog}"], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if proc.returncode == 0:
        print(f"profile-bio-sync: applied {list(patch)} -> {(proc.stdout or '').strip()}")
        return 0
    # write blocked — almost always the missing `user` scope. Surface the atom, never fail the build.
    print(
        "profile-bio-sync: could not write profile settings (the GitHub `user` OAuth scope is required; "
        "repo/workflow tokens cannot set them)."
    )
    print(f"  one-time fix, then re-run this script:  {REFRESH_HINT}")
    print(f"  intended: {patch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
