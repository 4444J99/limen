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

PREDICATE — exit 0 iff ALL hold:
  1. the vault remote has been pushed within --max-age-days, AND
  2. a local vault working copy exists (absent ⇒ every run pays a full clone, which is what broke)
  3. COVERAGE: every ~/Workspace/_*-private store's on-disk content matches its sealed copy
     (delegated to `arca.sh status --json`, which owns store_hash). Added 2026-08-12 after 1+2
     reported OK while three stores held unsealed changes and a 4.9GB store had NEVER been
     sealed — over ARCA_MAX_MB=512, so silently skipped every beat since it was created.
     Recency answers "did the vault move?"; only coverage answers "did it take what changed?"

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


def _minutes_since(stamp: str) -> float | None:
    """Minutes since an ISO-8601 Z stamp, or None if it is missing/unparseable."""
    if not stamp:
        return None
    try:
        when = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - when).total_seconds() / 60.0


def _coverage(vault_dir: str, timeout: int) -> tuple[list[dict] | None, str | None]:
    """(stores, None) on success, (None, reason) on any failure. Never raises.

    COVERAGE vs RECENCY — the two halves of "is the private estate actually backed up":

      recency  (below) — did the vault repo move within --max-age-days?
      coverage (here)  — does the vault hold what is on disk RIGHT NOW?

    Recency alone is blind in exactly the way that matters. The vault moves for store A, goes
    green, and store B's change from four hours ago — or a store the ARCA_MAX_MB cap SKIPPED
    every single beat since it was created — is invisible. Both were live on 2026-08-12: three
    stores `changed`, and `_collaboration-operations-private` (4.9GB vs the 512MB cap) NEVER
    sealed, while this sensor printed OK.

    The asymmetry that makes this the right home: `arca.sh backup` (the SEALER) lives in
    metabolize.sh §5c, and the heartbeat daemon never runs metabolize — only saturate.sh does
    (heartbeat-loop.sh:590). This sensor (the OBSERVER) runs on the frequent beat. So the
    observer must carry the coverage truth; the sealer is not looking often enough to notice.

    arca.sh owns `store_hash`, so coverage is delegated rather than reimplemented — one
    definition of content identity, no digest drift between sealer and sensor.
    """
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arca.sh")
    if not os.path.isfile(script):
        return None, f"arca.sh not found beside this sensor ({script})"
    # Pin arca.sh to the SAME vault this run reports on — otherwise --vault-dir would compare
    # stores against a different generation's manifest and report coverage for a vault the
    # caller never asked about.
    env = dict(os.environ, ARCA_VAULT_DIR=vault_dir)
    try:
        proc = subprocess.run(
            ["bash", script, "status", "--json"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return None, f"arca.sh status timed out after {timeout}s (store hashing exceeded the budget)"
    except Exception as exc:  # pragma: no cover — defensive
        return None, f"arca.sh status failed: {type(exc).__name__}"
    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        return None, f"arca.sh status exit {proc.returncode}: {detail[-1][:120] if detail else 'no stderr'}"
    try:
        payload = json.loads(proc.stdout or "")
        stores = payload["stores"]
    except Exception:  # noqa: BLE001 — malformed output is a finding, not a crash
        return None, "arca.sh status returned unparseable JSON"
    return (stores, None) if isinstance(stores, list) else (None, "arca.sh status returned no store list")


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
    ap.add_argument(
        "--coverage-timeout",
        type=int,
        default=45,
        help="budget for arca.sh status (store hashing); kept under the sensor's own 90s timeout",
    )
    ap.add_argument(
        "--max-unsealed-minutes",
        type=int,
        default=180,
        help="grace for a CHANGED store: live stores are written constantly, so differing from "
        "the vault is normal between seals. Measured from the last seal, not from the change.",
    )
    ap.add_argument(
        "--skip-coverage",
        action="store_true",
        help="check recency only — the pre-2026-08-12 behaviour, blind to unsealed stores",
    )
    ap.add_argument("--json", action="store_true", dest="as_json")
    args = ap.parse_args()

    repo = args.repo or os.environ.get("ARCA_REPO") or _manifest_generation_repo(args.vault_dir) or DEF_REPO
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

    # COVERAGE — only when a local vault exists. Running it without one would make arca.sh's
    # ensure_vault attempt a full clone from inside a sensor, which is precisely the failure
    # that killed the old vault (#2072, >19GB clone death). The absent-vault case is already
    # a finding above, so skipping here loses nothing.
    stores: list[dict] | None = None
    if args.skip_coverage:
        pass
    elif not local_present:
        findings.append("coverage UNDETERMINED — no local vault working copy to compare against")
    else:
        stores, cov_reason = _coverage(args.vault_dir, args.coverage_timeout)
        if stores is None:
            findings.append(f"coverage UNDETERMINED — {cov_reason}")
        else:
            never = [s["name"] for s in stores if s.get("state") == "never_sealed"]
            if never:
                # No grace: a store that has NEVER been sealed has no off-machine copy at all,
                # and no amount of waiting produces one. Measured cause on 2026-08-12 was the
                # ARCA_MAX_MB skip, whose only alarm was a log line nothing consumed.
                findings.append(
                    f"NEVER SEALED: {', '.join(sorted(never))} — no off-machine copy has ever "
                    f"existed (check ARCA_MAX_MB: a store over the cap is skipped every beat)"
                )

            # CHANGED is graced, and the grace runs from the SEAL, not from the change. These
            # stores are written continuously (measured: 4 files changed within 3.5 minutes of a
            # successful seal), so "differs from the vault right now" is the normal state between
            # seals and would red permanently. What is NOT normal is the seal itself going stale
            # while content moves — that is the sealer failing to keep up, and it is what a
            # locked Keychain, a wedged backup, or the metabolize/daemon split actually look like.
            stale_changed = []
            for s in stores:
                if s.get("state") != "changed":
                    continue
                lag = _minutes_since(s.get("sealed_at") or "")
                if lag is None or lag > args.max_unsealed_minutes:
                    stale_changed.append(f"{s['name']} ({'unknown' if lag is None else f'{lag / 60:.1f}h'})")
            if stale_changed:
                findings.append(
                    f"UNSEALED CHANGES: {', '.join(sorted(stale_changed))} — content has been "
                    f"newer than the vault for over {args.max_unsealed_minutes / 60:.0f}h, so the "
                    f"sealer is not keeping up (it runs in metabolize §5c, which the heartbeat "
                    f"daemon does not run — only saturate.sh does)"
                )

    ok = not findings
    if args.as_json:
        print(
            json.dumps(
                {
                    "schema": "limen.arca_freshness.v2",
                    "ok": ok,
                    "repo": repo,
                    "local_vault_present": local_present,
                    "pushed_at": pushed_at,
                    "age_days": round(age_days, 2) if age_days is not None else None,
                    "max_age_days": args.max_age_days,
                    "stores": stores,
                    "findings": findings,
                },
                indent=2,
                sort_keys=True,
            )
        )
    elif ok:
        covered = "coverage skipped" if args.skip_coverage else f"{len(stores or [])} stores current"
        print(f"arca-freshness: OK — {repo} pushed {age_days:.1f}d ago; local vault present; {covered}")
    else:
        print(f"arca-freshness: FAIL — {repo}")
        for f in findings:
            print(f"  · {f}")
        print("  owner: organvm/limen#2072 (vault shape) · #719 L-ARCA-KEY-ESCROW (key escrow)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
