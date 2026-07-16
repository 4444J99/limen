#!/usr/bin/env python3
"""heal-convergence.py — prove the heal engine converges, or say exactly where it doesn't.

The gap this closes (retro 2026-06-24→07-08, findings 1–2): the healer opened
PRs it could not merge (growth-auditor #16–#22 all open, e2e red every time;
dot-github--theoria #492…#500 all red on the same lint gate) and NOTHING detected
the stall — 59% of heal receipts produced no PR, with no field distinguishing
"already green" from "gave up silently". Capacity burned; position not gained;
convergence could be neither asserted nor falsified.

Two rungs:
  • CHRONIC — every open heal PR (title-prefixed ``[limen HEAL-``), grouped by
    (repo, failing check). A group with ≥ --chronic-count PRs older than
    --chronic-hours failing the SAME check is a chronic non-convergence: the
    healer is re-spending capacity on a wall. Exit 1 (with --check).
  • COVERAGE — archived heal receipts (.limen-private/async-runs/archive) must
    carry the ``outcome`` field ({already_green|fixed|gave_up} + failing_checks,
    derived mechanically by async-run-one.py post-run). Reported as a ratio so
    the 855-emitted-vs-384-receipts class of gap is a number, not a vibe.

Chronic receipts (exemptions):
  A chronic group whose CI is externally blocked (billing hold, suspended project,
  etc.) can be parked with a receipt entry in ``scripts/heal-chronic-receipts.json``.
  Each entry must carry ``repo``, ``check``, ``lever`` (lever id in his-hand-levers.json),
  ``issue`` (limen issue #), and ``reason``.  A matching group is printed as EXEMPT and
  excluded from the exit-1 gate while the underlying lever remains open.
  Override the path via ``LIMEN_CHRONIC_RECEIPTS``.

Exit codes: 0 = no chronic group; 1 = chronic non-convergence (with --check).
Stamps logs/heal-convergence.json. Fixture-testable: --prs-file bypasses gh.

Usage:
  python3 scripts/heal-convergence.py            # report + stamp
  python3 scripts/heal-convergence.py --check    # gate mode
"""

import argparse
import collections
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(os.environ.get("LIMEN_ROOT", SCRIPT_ROOT))
OWNERS = [o.strip() for o in os.environ.get("LIMEN_OWNERS", "organvm,4444J99").split(",") if o.strip()]
RECEIPT_ARCHIVE = ROOT / ".limen-private" / "async-runs" / "archive"
CHRONIC_RECEIPTS_FILE = Path(os.environ.get(
    "LIMEN_CHRONIC_RECEIPTS",
    str(SCRIPT_ROOT / "scripts" / "heal-chronic-receipts.json"),
))


def gh(args, timeout=60):
    return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)


def live_heal_prs(cap=40):
    """Open heal PRs with their failing check names. One search + one view per PR."""
    r = gh(["search", "prs", "--author", "@me", "--state", "open", "[limen HEAL-",
            *sum([["--owner", o] for o in OWNERS], []),
            "--json", "number,repository,url,createdAt,title", "--limit", str(cap)])
    if r.returncode != 0:
        print(f"  (gh search failed: {r.stderr.strip()[:200]})", file=sys.stderr)
        return []
    prs = []
    for row in json.loads(r.stdout or "[]"):
        repo = row["repository"]["nameWithOwner"]
        num = row["number"]
        v = gh(["pr", "view", str(num), "-R", repo, "--json", "statusCheckRollup"])
        failing = []
        if v.returncode == 0:
            rollup = (json.loads(v.stdout or "{}") or {}).get("statusCheckRollup") or []
            failing = sorted({c.get("name", "?") for c in rollup
                              if (c.get("conclusion") or "").upper() in ("FAILURE", "TIMED_OUT", "CANCELLED")})
        prs.append(dict(repo=repo, number=num, url=row["url"], createdAt=row["createdAt"],
                        title=row.get("title", ""), failing_checks=failing))
    return prs


def chronic_groups(prs, chronic_count, chronic_hours, now=None):
    now = now or datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(hours=chronic_hours)
    groups = collections.defaultdict(list)
    for pr in prs:
        try:
            created = datetime.datetime.fromisoformat(str(pr["createdAt"]).replace("Z", "+00:00"))
        except ValueError:
            continue
        if created > cutoff:
            continue
        for check in pr.get("failing_checks") or []:
            groups[(pr["repo"], check)].append(pr)
    return {k: v for k, v in groups.items() if len(v) >= chronic_count}


def load_chronic_receipts(receipts_file=None):
    """Load exemption receipts from the git-tracked registry.

    Returns a dict keyed by (repo, check) → receipt entry.
    Missing or malformed file is silently treated as empty (fail-open for the sensor).
    """
    path = Path(receipts_file) if receipts_file else CHRONIC_RECEIPTS_FILE
    if not path.exists():
        return {}
    try:
        entries = json.loads(path.read_text()) or []
    except (OSError, json.JSONDecodeError) as exc:
        print(f"  (chronic receipts load warning: {exc})", file=sys.stderr)
        return {}
    return {(e["repo"], e["check"]): e for e in entries if "repo" in e and "check" in e}


def receipt_coverage(archive_dir):
    """(with_outcome, without_outcome) across archived HEAL receipts."""
    with_o = without = 0
    base = Path(archive_dir)
    if not base.exists():
        return 0, 0
    for f in base.rglob("*HEAL-*.json"):
        try:
            receipt = (json.loads(f.read_text()) or {}).get("receipt") or {}
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(receipt, dict) and receipt.get("outcome"):
            with_o += 1
        else:
            without += 1
    return with_o, without


def main(argv=None):
    ap = argparse.ArgumentParser(description="Heal-engine convergence report / gate.")
    ap.add_argument("--check", action="store_true", help="gate mode: exit 1 on chronic non-convergence")
    ap.add_argument("--chronic-count", type=int, default=3)
    ap.add_argument("--chronic-hours", type=int, default=48)
    ap.add_argument("--cap", type=int, default=40, help="max open heal PRs to assess per run")
    ap.add_argument("--prs-file", help="fixture JSON [{repo,number,url,createdAt,failing_checks}] — bypasses gh")
    ap.add_argument("--receipts-dir", default=str(RECEIPT_ARCHIVE))
    ap.add_argument("--chronic-receipts", default=None,
                    help="path to heal-chronic-receipts.json (default: scripts/heal-chronic-receipts.json)")
    ap.add_argument("--now", help="fixture clock (ISO-8601) for deterministic tests")
    ap.add_argument("--stamp", default=str(ROOT / "logs" / "heal-convergence.json"))
    args = ap.parse_args(argv)

    prs = json.loads(Path(args.prs_file).read_text()) if args.prs_file else live_heal_prs(args.cap)
    now = datetime.datetime.fromisoformat(args.now.replace("Z", "+00:00")) if args.now else None
    chronic = chronic_groups(prs, args.chronic_count, args.chronic_hours, now=now)
    with_o, without = receipt_coverage(args.receipts_dir)
    exemptions = load_chronic_receipts(args.chronic_receipts)

    # Partition chronic groups into exempted (lever-homed, receipt present) and active.
    exempt = {k: v for k, v in chronic.items() if k in exemptions}
    active = {k: v for k, v in chronic.items() if k not in exemptions}

    payload = dict(
        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        open_heal_prs=len(prs),
        chronic=[dict(repo=r, check=c, prs=[p["url"] for p in v]) for (r, c), v in sorted(active.items())],
        chronic_exempt=[
            dict(repo=r, check=c, prs=[p["url"] for p in v], **{
                k2: exemptions[(r, c)].get(k2) for k2 in ("lever", "issue", "reason")
            })
            for (r, c), v in sorted(exempt.items())
        ],
        receipts_with_outcome=with_o,
        receipts_without_outcome=without,
    )
    try:
        p = Path(args.stamp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(payload, indent=1) + "\n")
    except OSError as exc:
        print(f"  (stamp skipped: {exc})", file=sys.stderr)

    for (repo, check), v in sorted(exempt.items()):
        e = exemptions[(repo, check)]
        print(f"  EXEMPT {repo} · check '{check}' — {len(v)} open heal PRs (lever {e.get('lever')} / "
              f"issue #{e.get('issue')}): {e.get('reason', '—')}")
    for (repo, check), v in sorted(active.items()):
        print(f"  CHRONIC {repo} · check '{check}' — {len(v)} open heal PRs > {args.chronic_hours}h: "
              + ", ".join(f"#{p['number']}" for p in v))
    total = with_o + without
    cov = f"{with_o}/{total}" if total else "0/0"
    print(f"heal-convergence: {len(prs)} open heal PRs, {len(active)} chronic group(s) active, "
          f"{len(exempt)} exempt, receipt outcome coverage {cov}")

    if args.check and active:
        print("heal-convergence: RED — the healer is re-spending capacity on a wall; "
              "fix the named check or park the repo with a chronic receipt", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
