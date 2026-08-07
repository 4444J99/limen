#!/usr/bin/env python3
"""LIVE-TREE-COHERENCE probe — is the tree the beat actually executes identical to origin/main?

The measurement behind IF-LIVE-TREE-COHERENCE. `LIMEN_ROOT` (default ~/Workspace/limen) is the
checkout `scripts/metabolize.sh` cd's into and runs every rung from; a session worktree is NOT
that tree. Nothing looked at it, so on 2026-07-29 it was found frozen at a 2026-07-23 commit —
120 behind origin/main, one unpushed local commit, 12 dirty files — meaning every governance
axis merged in those six days (CORPORA, CONVERGENCE, ATOM-HOMING) did not exist in the files
the fleet ran. `scripts/sync-release.sh` auto-unparks only a fully-pushed, clean park and fails
open loudly otherwise; loudly into a log nothing reads is silently.

Exit 0 iff the live checkout is on the default branch, carries no unpushed commits, and its
HEAD is the CURRENT remote head.

TRUTH IS THE REMOTE, NOT THE REMOTE-TRACKING REF. The first draft of this probe compared HEAD
to the local `origin/main` ref and reported `behind=0` on a checkout whose ref had not been
fetched — a false green produced by exactly the kind of stale local state the ideal is about.
Ground truth comes from `git ls-remote` (a pure read: no local ref is written, nothing races
the running beat). The exact behind-count still needs the objects locally; when they are
absent that is itself drift, reported as such rather than silently counted as zero.

DIRTY IS NOT FAILURE. `tasks.yaml`, `his-hand-levers.json`, `logs/**` are daemon-written by
design; a live beat is expected to have a dirty tree. Dirt is REPORTED (it is why sync-release
refuses to fast-forward) but never fails this probe — failing on it would make the check red
forever and therefore ignored.

HOST-AWARE, the check-corpora/check-convergence rule: drift is only claimable where the
evidence to prove it is present. A CI runner has no LIMEN_ROOT; that absence is a host fact,
not drift, and prints `state=unverifiable-here` with exit 0.

Machine line (parsed by scripts/check-ideal-forms.py via the ideal-forms registry's `extract`):

    live-checkout: state=<state> branch=<b> drift=<n> ahead=<n> behind=<n> dirty=<n>

`drift` is the single measurement: 0 iff the fleet is running exactly what origin/main holds.

THE RECEIPT (2026-08-07, the cadence-guard arc). This probe answers only when RUN, needs a
network `git ls-remote`, and left no artifact — so no point-of-use consumer could afford to ask
it inline, and the answer existed nowhere between runs. That is how a guard came to read a
*fresh* meter file written by *stale code* and call it fine: freshness of an artifact is not
truth of its value when the writer is the stale party. Every run now also writes an OFFLINE
receipt (``logs/live-checkout-currency.json``, ``--receipt`` to override) so a guard deciding
whether to trust any beat-written artifact can read one local file with no network and no git.

The receipt carries NO wall-clock field, on purpose and for the same reason the Fable meter
does not: ``logs/`` is gitignored runtime state with exactly one writer, so the file's own mtime
IS the writer's heartbeat, and a body without a timestamp stays byte-identical across runs when
nothing changed — an idempotent artifact whose every diff is a real change. Consumers age it
with ``os.stat().st_mtime``.

Receipt absence is NOT "fine": a consumer that cannot find this file has learned that deployment
currency is unestablished, which is exactly the state that must degrade toward the warning.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_ROOT = Path.home() / "Workspace" / "limen"
DEFAULT_BRANCH = "main"
UNVERIFIABLE = "live-checkout: state=unverifiable-here branch={b} drift=0 ahead=0 behind=0 dirty=0  ({why})"

RECEIPT_SCHEMA = "limen.live_checkout_currency.v1"
RECEIPT_REL = os.path.join("logs", "live-checkout-currency.json")


def receipt_path(root: Path) -> Path:
    """Where the offline currency receipt lives. ``--receipt``/``LIMEN_LIVE_CHECKOUT_RECEIPT``
    override it (tests, alternate hosts)."""
    raw = os.environ.get("LIMEN_LIVE_CHECKOUT_RECEIPT")
    return Path(raw).expanduser() if raw else root / RECEIPT_REL


def write_receipt(path: Path, **fields) -> None:
    """Write the offline receipt. NEVER raises: a probe that cannot record its own answer must
    still report it on stdout, and an unwritable receipt reads downstream as absent — which
    already degrades toward the warning, the correct direction."""
    body = {"schema": RECEIPT_SCHEMA, **fields}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n")
    except Exception:
        pass


def git(root: Path, *args: str) -> tuple[int, str]:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout.strip()


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Is the tree the beat executes identical to origin/main?")
    ap.add_argument("--receipt", default=None, help="offline receipt path (default logs/live-checkout-currency.json)")
    ap.add_argument("--no-receipt", action="store_true", help="report only; write no receipt")
    args = ap.parse_args()

    root = Path(os.environ.get("LIMEN_ROOT", DEFAULT_ROOT)).expanduser()
    rpath = Path(args.receipt).expanduser() if args.receipt else receipt_path(root)

    def unverifiable(branch: str, why: str) -> int:
        # "I could not establish this" is its OWN state, never folded into `coherent`. A consumer
        # reading state != "coherent" degrades toward the warning; that is the whole contract.
        if not args.no_receipt:
            write_receipt(
                rpath,
                state="unverifiable-here",
                branch=branch,
                drift=0,
                ahead=0,
                behind=0,
                dirty=0,
                unfetched=False,
                root=str(root),
                detail=why,
            )
        print(UNVERIFIABLE.format(b=branch, why=why))
        return 0

    # Host-aware: no live checkout here at all (the CI case) is not drift.
    if not (root / ".git").exists():
        return unverifiable("-", f"{root} is not a checkout")

    rc, branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    if rc != 0:
        return unverifiable("-", f"git failed in {root}")
    _, head = git(root, "rev-parse", "HEAD")

    # Ground truth: what origin/main IS right now, not what this checkout last heard.
    rc, ls = git(root, "ls-remote", "origin", f"refs/heads/{DEFAULT_BRANCH}")
    if rc != 0 or not ls:
        return unverifiable(branch, "origin unreachable — cannot establish the true head")
    remote_head = ls.split()[0]

    # Exact counts need the remote objects locally. Their absence IS drift (this checkout has
    # not fetched since the remote moved) — never silently zero.
    have_remote_objects = git(root, "cat-file", "-e", f"{remote_head}^{{commit}}")[0] == 0
    unfetched = False
    if have_remote_objects:
        rc, counts = git(root, "rev-list", "--left-right", "--count", f"{remote_head}...HEAD")
        behind_s, _, ahead_s = counts.partition("\t")
        behind, ahead = int(behind_s or 0), int(ahead_s.strip() or 0)
    else:
        unfetched = True
        behind, ahead = 0, 0

    _, porcelain = git(root, "status", "--porcelain")
    dirty = len([ln for ln in porcelain.splitlines() if ln.strip()])

    problems = []
    if branch != DEFAULT_BRANCH:
        problems.append(f"parked on {branch!r}, not {DEFAULT_BRANCH} — the running fleet is pinned to a work branch")
    if unfetched:
        problems.append(
            f"HEAD {head[:8]} is not the current remote head {remote_head[:8]}, and the remote "
            "objects are not present — this checkout has not fetched since origin moved"
        )
    if behind:
        problems.append(f"behind origin/{DEFAULT_BRANCH} by {behind} commit(s) — the fleet is executing stale code")
    if ahead:
        problems.append(
            f"{ahead} unpushed commit(s) (Rule #2: on disk is not done) — this is what blocks "
            "sync-release from fast-forwarding"
        )

    drift = behind + ahead + (1 if unfetched else 0) + (0 if branch == DEFAULT_BRANCH else 1)
    state = "drift" if problems else "coherent"
    if not args.no_receipt:
        write_receipt(
            rpath,
            state=state,
            branch=branch,
            drift=drift,
            ahead=ahead,
            behind=behind,
            dirty=dirty,
            unfetched=unfetched,
            root=str(root),
            detail="; ".join(problems),
        )
    print(f"live-checkout: state={state} branch={branch} drift={drift} ahead={ahead} behind={behind} dirty={dirty}")
    print(f"  root: {root}")
    if dirty:
        print(f"  {dirty} dirty path(s) — expected on a live beat (daemon-written); reported, not failed")
    for p in problems:
        print(f"  ✗ {p}")
    if problems:
        print("  owner: scripts/sync-release.sh (the beat's unpark rung) — reconcile there, not by hand:")
        print("         a fast-forward of a daemon-contended tree races the running beat.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
