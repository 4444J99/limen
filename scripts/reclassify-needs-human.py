#!/usr/bin/env python3
"""reclassify-needs-human.py — separate the REAL human atoms from the mislabeled ones.

The `needs_human` queue regressed to 37 undifferentiated entries, but most are NOT human-blocked:
they're fleet-buildable code/docs (READMEs, landing pages, "is-LIVE" verifications) that got parked
in `needs_human` and now sit idle behind a false gate while the fleet has the capacity to do them.
This separates them so the human surface is only what genuinely needs his hand.

Classification is DERIVED from signals, never a pinned id list (the human-marker signals live in
scripts/_human_signals.py, shared with heal-dispatch.py so both sides of the truth loop agree):
  * KEEP (real human atom): needs a secret/credential/account, admin/branch-protection, the merge
    gate, or an irreversible/backup-gated cutover. Also the `BLD2-*` deploy batch (blocked on the
    Cloudflare wrangler credential — his hand).
  * CHRONIC -> failed_blocked: escalated by heal-dispatch after reopening ≥3× with zero PRs and
    carrying NO human marker — fleet debt, not his. Flipping these back to `open` is the ping-pong
    that refilled the queue (154 -> 406 in 13h on 2026-07-13); `failed_blocked` is the honest
    terminal state nothing auto-reopens.
  * FLIP -> open: a code/docs task in a repo with NO human-only signal and NO chronic history —
    the fleet can just do it.
  * STALE: its precondition is already satisfied (e.g. "live-dispatch across vendors" while the
    daemon is already dispatching) -> recommend close, don't re-queue.
  * REVIEW: an `ACTIVATION AUDIT: skip|kill` decision — "kill" is irreversible, so NEVER auto-flip;
    a one-pass human/triage call.

Dry-run by default: prints the five buckets so every decision is visible. With --apply it flips the
FLIP bucket `needs_human -> open` and parks the CHRONIC bucket `needs_human -> failed_blocked`,
lockless + atomic (re-read fresh under the limen save path, exactly like generate-revenue-backlog),
and never touches KEEP / STALE / REVIEW. Fully reversible (status flips + provenance labels).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "cli" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # sibling scripts/ for _human_signals
from limen.chronic import CHRONIC_FLEET_DEBT_LABEL, chronic_escalated_to_needs_human  # noqa: E402
from limen.io import load_limen_file, save_limen_file  # noqa: E402

from _human_signals import HUMAN_ID_PREFIXES, HUMAN_SIGNALS, LEVER_MARKER, lever_ids, task_blob  # noqa: E402

ROOT = Path(os.environ.get("LIMEN_ROOT", Path(__file__).resolve().parent.parent))

# Precondition-already-met: "live-dispatch / dispatch-drain" while the daemon is already dispatching.
_STALE_SIGNAL = re.compile(r"live-dispatch|dispatch.drain|set autonomy.*dispatch", re.IGNORECASE)
# Irreversible triage decision — surface, never auto-act.
_REVIEW_SIGNAL = re.compile(r"activation audit:\s*(skip|kill)\b", re.IGNORECASE)

_LEVER_IDS = lever_ids(ROOT)


def _chronic(task) -> bool:
    """True iff the LAST needs_human transition was a machine chronic escalation (limen.chronic).

    Last-entry-wins on purpose: a human who deliberately parks a once-chronic task back in
    needs_human overrides the machine stamp, and the shared predicate also matches the three
    legacy pre-heal-dispatch escalation strings that a `heal-dispatch:`-prefixed match misses."""
    return chronic_escalated_to_needs_human(task)


def _live_root() -> Path:
    """The live checkout, even when run from a worktree (whose logs/ are stale): strip a trailing
    .claude/worktrees/<name>. Falls back to ROOT."""
    parts = ROOT.parts
    if ".claude" in parts:
        i = parts.index(".claude")
        if parts[i:i + 2] == (".claude", "worktrees"):
            return Path(*parts[:i])
    return ROOT


def _dispatch_is_live() -> bool:
    """True if a recent tick shows the daemon dispatching (ASK-7's precondition). Reads ROOT then the
    live checkout (so it's correct from a worktree too). Fail-open False."""
    for base in (ROOT, _live_root()):
        try:
            lines = (base / "logs" / "ticks.jsonl").read_text().splitlines()
            for ln in reversed(lines[-5:]):
                t = json.loads(ln)
                if (t.get("dispatched") or 0) > 0:
                    return True
        except Exception:
            continue
    return False


def classify(task, dispatch_live: bool) -> str:
    blob = task_blob(task)
    # A lever-tagged task is his hand by definition — checked FIRST so a real lever can never leak
    # into FLIP for lack of a credential keyword. Derived from the registry, not a pinned id list.
    if LEVER_MARKER.search(blob) or any(lv in blob for lv in _LEVER_IDS):
        return "KEEP"
    if task.id.startswith(HUMAN_ID_PREFIXES):
        return "KEEP"
    if _REVIEW_SIGNAL.search(blob):
        return "REVIEW"
    if HUMAN_SIGNALS.search(blob):
        return "KEEP"
    # Chronic AFTER every human-marker check: a chronic task with a human atom stays KEEP, but a
    # chronic task without one is fleet debt — flipping it to open just re-runs the churn.
    if _chronic(task):
        return "CHRONIC"
    if _STALE_SIGNAL.search(blob) and dispatch_live:
        return "STALE"
    if task.type in ("code", "docs") and task.repo:
        return "FLIP"
    return "REVIEW"  # unknown shape -> surface, never auto-flip


_REASON = {
    "KEEP": "real human atom (secret/account/admin/merge-gate/cutover/credential-gated deploy)",
    "CHRONIC": "reopened ≥3× with zero PRs, no human atom — fleet debt, park failed_blocked",
    "FLIP": "fleet-buildable code/docs — no human-only signal",
    "STALE": "precondition already satisfied (daemon already dispatching) — recommend close",
    "REVIEW": "irreversible/ambiguous (skip-vs-kill) — one human triage pass",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=os.environ.get("LIMEN_TASKS", "tasks.yaml"))
    ap.add_argument("--apply", action="store_true",
                    help="flip ONLY the FLIP bucket needs_human->open (lockless, atomic, reversible)")
    args = ap.parse_args()

    path = Path(args.tasks)
    lf = load_limen_file(path)
    dispatch_live = _dispatch_is_live()
    nh = [t for t in lf.tasks if t.status == "needs_human"]

    buckets: dict[str, list] = {"KEEP": [], "CHRONIC": [], "FLIP": [], "STALE": [], "REVIEW": []}
    for t in nh:
        buckets[classify(t, dispatch_live)].append(t)

    # docs/RECLASSIFY-PROPOSAL.md ------------------------------------------------------------------
    md = [
        f"# Reclassify needs_human — {date.today().isoformat()}",
        "",
        f"`needs_human` holds **{len(nh)}** tasks. By signal (not by hand-picked id) they split into:",
        "",
        f"- **KEEP — {len(buckets['KEEP'])}** genuinely need your hand (secret / account / admin / "
        "merge gate / irreversible cutover / Cloudflare-credential-gated deploy).",
        f"- **CHRONIC — {len(buckets['CHRONIC'])}** churned ≥3 reopens with zero PRs and carry no "
        "human atom — fleet debt. `--apply` parks these `failed_blocked` (honest terminal state; "
        "flipping them to `open` is the ping-pong that refills this queue). Reversible.",
        f"- **FLIP — {len(buckets['FLIP'])}** are fleet-buildable code/docs parked behind a false gate. "
        "`--apply` flips these to `open` so the fleet does them. Reversible.",
        f"- **STALE — {len(buckets['STALE'])}** precondition already met — recommend close, don't re-queue.",
        f"- **REVIEW — {len(buckets['REVIEW'])}** one quick triage call (skip vs *kill* — kill is "
        "irreversible, never auto-flipped).",
        "",
        "> `--apply` changes ONLY the FLIP and CHRONIC buckets; KEEP / STALE / REVIEW are never "
        "auto-touched. Both flips are status-only + a provenance label — fully reversible.",
        "",
    ]
    for b in ("FLIP", "CHRONIC", "STALE", "REVIEW", "KEEP"):
        md += [f"## {b} — {_REASON[b]}", "", "| id | type | repo | title |", "|---|---|---|---|"]
        for t in buckets[b]:
            md.append(f"| `{t.id}` | {t.type} | {t.repo or '—'} | {(t.title or '')[:70]} |")
        md.append("")
    md += ["---", "*Generated by `scripts/reclassify-needs-human.py`. Re-run `--apply` to flip the "
           "FLIP bucket and park the CHRONIC bucket, or say the word and I will.*", ""]
    try:
        (ROOT / "docs").mkdir(parents=True, exist_ok=True)
        (ROOT / "docs" / "RECLASSIFY-PROPOSAL.md").write_text("\n".join(md))
    except OSError:
        pass

    # console -------------------------------------------------------------------------------------
    print(f"# reclassify-needs-human: {len(nh)} needs_human  (dispatch_live={dispatch_live})")
    for b in ("KEEP", "CHRONIC", "FLIP", "STALE", "REVIEW"):
        print(f"  {b:7} {len(buckets[b]):3}  — {_REASON[b]}")
    flip_ids = [t.id for t in buckets["FLIP"]]
    chronic_ids = [t.id for t in buckets["CHRONIC"]]
    print("\nFLIP -> open:")
    for t in buckets["FLIP"]:
        print(f"  {t.id:52.52} {(t.title or '')[:50]}")
    print("\nCHRONIC -> failed_blocked:")
    for t in buckets["CHRONIC"]:
        print(f"  {t.id:52.52} {(t.title or '')[:50]}")

    if not args.apply:
        print(f"\ndry-run — re-run with --apply to flip {len(flip_ids)} tasks needs_human->open "
              f"and park {len(chronic_ids)} chronic tasks needs_human->failed_blocked.")
        print("wrote docs/RECLASSIFY-PROPOSAL.md")
        return 0

    # Apply lockless + atomic: re-read fresh so we never clobber a concurrent dispatch write; the
    # set-of-ids makes this idempotent (re-running flips nothing already flipped). Never skip on
    # contention — next run simply re-applies (self-healing), mirroring generate-revenue-backlog.
    fresh = load_limen_file(path)
    flip_set = set(flip_ids)
    chronic_set = set(chronic_ids)
    stamp = date.today().isoformat()
    flipped = parked = 0
    for t in fresh.tasks:
        if t.status != "needs_human":
            continue
        if t.id in flip_set:
            t.status = "open"
            t.updated = stamp
            if "reclassified-from-needs-human" not in (t.labels or []):
                t.labels = list(t.labels or []) + ["reclassified-from-needs-human"]
            flipped += 1
        elif t.id in chronic_set:
            t.status = "failed_blocked"
            t.updated = stamp
            if CHRONIC_FLEET_DEBT_LABEL not in (t.labels or []):
                t.labels = list(t.labels or []) + [CHRONIC_FLEET_DEBT_LABEL]
            parked += 1
    if not (flipped or parked):
        print("\n(nothing to change after fresh re-read — already applied.)")
        return 0
    save_limen_file(path, fresh)
    print(f"\napplied: flipped {flipped} needs_human->open, parked {parked} needs_human->failed_blocked "
          f"-> {path} (route+dispatch separately).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
