#!/usr/bin/env python3
"""arca-freshness.py — is the private estate ACTUALLY backed up, or has the vault gone quiet?

THE PROBLEM IT CLOSES: `scripts/arca.sh backup` is wired into every beat (metabolize.sh section 5c)
as `arca.sh backup || echo "  (arca skipped — keychain locked, offline, or vault unconfigured)"`.
That `|| echo` is deliberate — the beat is fail-open and a locked Keychain must not red it. But it
means a *permanently* dead vault is indistinguishable from a momentarily locked one: both print one
soft line and the beat stays green.

Measured 2026-08-07: the private estate had not been backed up since 2026-07-30. Eight days, every
beat printing the skip line, nothing red. The vault repo had grown past the point where arca's own
`git clone` could complete (>19 GB expanded), so every backup failed at step one. The estate's only
off-machine copy of the health chart, the legal docket, the people room and finance silently stopped
advancing, and the failure was structurally unobservable.

This is the observability half, deliberately separate from the repair: it asserts the OUTCOME
(ciphertext landed off-machine recently) rather than the mechanism, so it stays true regardless of
how the vault is later reshaped — a new generation, a different remote, a different chunking scheme.

GENERATION RESOLUTION (POTESTAS 0.3, organvm/limen#2089): the vault now rotates across
generations (organvm/arca → organvm/arca-g2 → …) and the local manifest owns which one is
CURRENT. So the repo under test is resolved in this order: explicit --repo → $ARCA_REPO → the
local manifest's `_generation.repo` → the default organvm/arca. That keeps this sensor pointing
at the LIVE generation through every future rotation with zero reconfiguration.

PREDICATE — exit 0 iff BOTH hold:
  1. the vault remote has been pushed within --max-age-days, AND
  2. a local vault working copy exists (absent ⇒ every run pays a full clone, which is what broke)

Exit 1 otherwise, INCLUDING when freshness cannot be determined. That is the point: "I could not
tell" is the exact state that hid this for eight days, so it is a finding, not a pass. Wired at
`advisory` severity, so a red here surfaces with the ↑ marker and never breaks the beat.

PII: prints repo/age/counts only — never a store's contents, never a path inside a private store.

Usage:
  python3 scripts/arca-freshness.py                    # human summary; exit 0 fresh / 1 stale
  python3 scripts/arca-freshness.py --json             # machine-readable
  python3 scripts/arca-freshness.py --max-age-days 3
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
DEF_REPO = "organvm/arca"
DEF_VAULT_DIR = os.environ.get("ARCA_VAULT_DIR", os.path.join(HOME, ".arca-vault"))
DEF_MAX_AGE_DAYS = 2


def _manifest_generation_repo(vault_dir: str) -> str:
    """Resolve the CURRENT generation repo from the local vault manifest, or '' if none.

    The manifest is the source of truth once a working vault exists, so the sensor follows
    rotations without any external reconfiguration. Any failure (no manifest, corrupt JSON,
    no metadata) yields '' — the caller then falls back to the env/default repo.
    """
    try:
        with open(os.path.join(vault_dir, "manifest.json")) as fh:
            manifest = json.load(fh)
        repo = manifest.get("_generation", {}).get("repo", "")
        return repo if isinstance(repo, str) else ""
    except Exception:  # noqa: BLE001 — read-only probe; never raise
        return ""


def _remote_pushed_at(repo: str, timeout: int) -> tuple[str | None, str | None]:
    """(iso8601, None) on success, (None, reason) on any failure. Never raises."""
    try:
        proc = subprocess.run(
            ["gh", "repo", "view", repo, "--json", "pushedAt", "-q", ".pushedAt"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return None, "gh not installed"
    except subprocess.TimeoutExpired:
        return None, f"gh timed out after {timeout}s"
    except Exception as exc:  # pragma: no cover — defensive
        return None, f"gh failed: {type(exc).__name__}"
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return None, f"gh exit {proc.returncode}: {detail[-1][:120] if detail else 'no stderr'}"
    stamp = (proc.stdout or "").strip()
    return (stamp, None) if stamp else (None, "gh returned no pushedAt")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=None, help="override generation resolution (manifest → env → default)")
    ap.add_argument("--vault-dir", default=DEF_VAULT_DIR)
    ap.add_argument("--max-age-days", type=float, default=DEF_MAX_AGE_DAYS)
    ap.add_argument("--timeout", type=int, default=30)
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    repo = (
        args.repo
        or os.environ.get("ARCA_REPO")
        or _manifest_generation_repo(args.vault_dir)
        or DEF_REPO
    )
    findings: list[str] = []

    local_present = os.path.isdir(os.path.join(args.vault_dir, ".git"))
    if not local_present:
        findings.append(f"local vault working copy absent ({args.vault_dir}) — every backup pays a full clone")

    pushed_at, reason = _remote_pushed_at(repo, args.timeout)
    age_days: float | None = None
    if pushed_at is None:
        findings.append(f"vault freshness UNDETERMINED — {reason}")
    else:
        try:
            when = datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - when).total_seconds() / 86400.0
        except ValueError:
            findings.append(f"vault freshness UNDETERMINED — unparseable pushedAt {pushed_at!r}")
        else:
            if age_days > args.max_age_days:
                findings.append(
                    f"NO BACKUP IN {age_days:.1f} DAYS — the private estate's only off-machine "
                    f"copy stopped advancing (threshold {args.max_age_days}d)"
                )

    ok = not findings
    if args.as_json:
        print(
            json.dumps(
                {
                    "schema": "limen.arca_freshness.v1",
                    "ok": ok,
                    "repo": repo,
                    "local_vault_present": local_present,
                    "pushed_at": pushed_at,
                    "age_days": round(age_days, 2) if age_days is not None else None,
                    "max_age_days": args.max_age_days,
                    "findings": findings,
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif ok:
        print(f"arca-freshness: OK — {repo} pushed {age_days:.1f}d ago; local vault present")
    else:
        print(f"arca-freshness: FAIL — {repo}")
        for f in findings:
            print(f"  · {f}")
        print("  owner: organvm/limen#2072 (vault shape) · #719 L-ARCA-KEY-ESCROW (key escrow)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
