#!/usr/bin/env python3
"""reap-branches.py — the BRANCH-REAP organ (ref hygiene; the lifecycle's ref sibling).

reclaim-worktrees.py reaps dead *worktrees* and reap-clones.py reaps pure-mirror *clones*, but
neither reaps the local *branch ref* left behind. `git worktree remove` and `gh pr merge
--delete-branch` both drop the worktree and delete the *remote* branch, yet the *local* head ref
survives forever — so after every squash-merge a branch lingers showing "1 ahead / N behind" and
gets hand-waved as "housekeeping" each session. That per-session judgment IS the recurring bug;
this organ is the macro fix that ends it (memory: build-the-repeatable-process-not-the-one-off).

Like its siblings it is an ALLOWLIST, not a denylist: it deletes a branch ONLY when it can
positively prove the WORK SURVIVES THE DELETION, by ONE of exactly three strong signals. Two prove
the work LANDED on the default branch; the third proves it was DECIDED AGAINST and preserved:

  1. TIP is an ancestor of origin/main            — a real merge / fast-forward (no commit is
     off-trunk; self-protecting — a post-merge commit would break ancestry), OR
  2. its PR is MERGED (per `gh`) AND the branch tip is NOT newer than the PR's mergedAt — the
     SQUASH-MERGE signal topology cannot see, with a belt against the "force-push new commits onto
     an already-merged branch" loss path (an advanced tip → KEPT as unpushed work, never deleted), OR
  3. its PR is CLOSED-UNMERGED (per `gh`) AND the local tip is EXACTLY that PR's headRefOid — the
     DECIDED class. A human closed that PR: the rejection is already recorded, and GitHub preserves
     the exact commit at `refs/pull/N/head` forever, so `git fetch origin pull/N/head` recovers it.
     Same belt, by SHA rather than by clock: a tip that differs from the PR head carries commits
     that exist nowhere else → KEPT as `pr-closed-but-advanced` (measured 2026-08-07: 14 of 94, so
     the belt is load-bearing, not theoretical). Proof 3 is strictly tighter than proof 2 — an exact
     object identity where proof 2 compares timestamps.

Deleting a landed branch is loss-free (its diff is on main); deleting a decided branch is loss-free
(the exact commit is on GitHub's pull ref). In both cases the local commits also stay in the reflog
~90d, so a mistaken delete is even recoverable. As of 2026-07-06, `--apply` still requires a matching
human acceptance/redaction/archive event in `docs/branch-reap-acceptance.jsonl` before
`git branch -D` runs — and the DECIDED class is deliberately NOT in STANDING_GRANT_REASONS: proof 3
makes the class machine-provable and visible, but widening standing deletion authority over it is an
operator decision, not this organ's to take.

Deliberately NOT reap proofs (each would violate a hard-won rule):
  • patch-equivalence (`git cherry` all '-') — low-value here and easy to fool; dropped for a
    tighter surface, and
  • empty diff vs main — an empty/identical branch with no PR is a PLACEHOLDER, i.e. an unfulfilled
    intention (memory: empty-branch-is-a-todo); reaping it would delete intent. Kept as live-work.

Everything without a surviving-work proof FAILS SAFE to KEEP:
  • an OPEN PR                          → IN-FLIGHT (kept silently),
  • merged-PR but tip advanced past it  → LIVE-WORK (unpushed post-merge commits — surfaced),
  • closed-PR but tip differs from its  → LIVE-WORK (commits that exist nowhere else — surfaced),
    headRefOid
  • real work not on main, no PR        → LIVE-WORK: an unfulfilled intention. NEVER deleted — it is
    surfaced to a git-tracked ledger (docs/branch-hygiene.md) so it "finds its location" instead of
    hanging invisibly on a machine.

NEVER reaps: the default branch, a configured-protected branch, or ANY branch currently checked
out in a worktree (git refuses + it is in active use). Offline / no `gh` → proof 2 is skipped, so
squash-merged branches are conservatively KEPT until an online beat — never wrongly deleted.

Dry-run by default; --apply deletes (git branch -D — safe: proven landed, reflog-recoverable).
Use repeatable --branch NAME arguments for an exact allowlist; a missing name fails closed without
touching any branch. With no --branch arguments the existing whole-local-ref policy is unchanged.
--check exits 1 iff any provably-LANDED branch still LINGERS — spent for longer than the digestion
grace window (the fixed-point predicate wired into scripts/no-tasks-on-me.sh). It keys on
Verdict.landed, exactly as that field's contract always claimed; before proof 3 it keyed on
`action == "reap"` instead, which was equivalent only because every reap class was landed. The
DECIDED class is reapable but NOT landed, so it does not redden the closeout gate: a red nobody is
authorized to clear is how a gate trains its reader to stop looking (2026-08-07). A branch whose PR
merged seconds ago is mid-beat housekeeping, not hanging debt; without the grace, a continuously
merging fleet makes the closeout gate unsatisfiable at every instant. Bounded (--max), fails OPEN
per-branch, self-throttles to once per LIMEN_BRANCH_REAP_EVERY_MIN minutes, logs
logs/reap-branches.jsonl + stamps logs/reap-branches-state.json.

Env: LIMEN_ROOT, LIMEN_BRANCH_REAP_REPO_ROOT (optional target repository; receipts remain
     under LIMEN_ROOT), LIMEN_BRANCH_REAP_MAX (100), LIMEN_BRANCH_REAP_EVERY_MIN (30),
     LIMEN_BRANCH_REAP_GRACE_MIN (60; --check only: a landed branch younger than this many minutes
     is digesting, not lingering — --apply eligibility is unaffected),
     LIMEN_BRANCH_REAP_PR_LIMIT (3000; how many recent PRs to read for proofs 2/3 — hitting the
     ceiling WARNs, because an unseen PR is indistinguishable from no PR),
     LIMEN_BRANCH_REAP_PROTECT (extra protected branch names, space-separated), LIMEN_OFFLINE.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from reap_acceptance import (  # noqa: E402
    REQUIRED_ACCEPTANCE_PROOF_FIELDS as SHARED_REQUIRED_ACCEPTANCE_PROOF_FIELDS,
    has_required_acceptance_proof,
)

HOME = os.environ.get("HOME", str(Path.home()))
LIMEN_ROOT = Path(os.environ.get("LIMEN_ROOT", f"{HOME}/Workspace/limen")).resolve()
LOG = LIMEN_ROOT / "logs" / "reap-branches.jsonl"
STATE = LIMEN_ROOT / "logs" / "reap-branches-state.json"
MARKER = LIMEN_ROOT / "logs" / ".reap-branches-last"
LEDGER = LIMEN_ROOT / "docs" / "branch-hygiene.md"
BRANCH_REAP_ACCEPTANCE = LIMEN_ROOT / "docs" / "branch-reap-acceptance.jsonl"

# A merged branch whose tip commit is newer than mergedAt + this buffer (seconds) is treated as
# ADVANCED (post-merge commits) and KEPT — never reaped. Buffer absorbs clock skew / the merge itself.
ADVANCED_BUFFER_S = 300

# Branch names that are NEVER candidates regardless of landed-state (trunks / integration refs).
BASE_PROTECT = {"main", "master", "HEAD", "develop", "trunk"}
EXTRA_PROTECT = set(os.environ.get("LIMEN_BRANCH_REAP_PROTECT", "").split())

# Non-interactive git: fail (→ fail-safe KEEP) rather than block on a credential/GUI prompt.
_GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
ACCEPTED_ARCHIVE_STATUSES = {
    "verified",
    "landed_on_default_verified",
    "merged_pr_verified",
    "not_required_landed_ref",
}
ACCEPTED_REDACTION_REVIEWS = {
    "accepted",
    "not_required_landed_ref",
    "not_required_remote_only",
}
REQUIRED_ACCEPTANCE_PROOF_FIELDS = SHARED_REQUIRED_ACCEPTANCE_PROOF_FIELDS
# A standing ledger grant may cover ONLY these machine-provable classes: the classifier assigns
# them strictly after the ancestor / merged-PR-with-unadvanced-tip proof already held, so the
# per-branch human key is delegated to that proof. Every other deletion class still requires a
# per-branch, tip-matched acceptance event (Anthony, in-session 2026-07-09).
STANDING_GRANT_REASONS = {"landed-pr-merged", "landed-ancestor"}


def _int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def _float_env(name: str, default: float, *, minimum: float | None = None) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    if not math.isfinite(value):
        return default
    if minimum is not None and value < minimum:
        return default
    return value


def repository_root() -> Path:
    """Return the target repository while keeping receipts in Limen."""

    return Path(os.environ.get("LIMEN_BRANCH_REAP_REPO_ROOT", str(LIMEN_ROOT))).resolve()


def _git(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a git command against the repo. Fails OPEN (returncode!=0) — never raises."""
    try:
        return subprocess.run(
            ["git", "-C", str(repository_root()), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_GIT_ENV,
        )
    except Exception as e:  # fail open per-call
        return subprocess.CompletedProcess(args, 1, "", str(e))


def load_branch_reap_acceptance() -> list[dict]:
    try:
        lines = BRANCH_REAP_ACCEPTANCE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _branch_tip_sha(branch: str) -> str | None:
    r = _git(["rev-parse", f"refs/heads/{branch}"])
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return r.stdout.strip()


def branch_reap_accepted(branch: str, reason: str, acceptance_events: list[dict]) -> tuple[bool, str]:
    tip = _branch_tip_sha(branch)
    matched_candidate = False
    for event in reversed(acceptance_events):
        standing = event.get("standing") is True and event.get("branch") in (None, "*")
        if standing:
            if reason not in STANDING_GRANT_REASONS:
                continue
            if event.get("accepted") is not True:
                continue
        else:
            if event.get("branch") != branch:
                continue
            if event.get("accepted") is not True:
                continue
            if event.get("reason") and event.get("reason") != reason:
                continue
            if event.get("tip") and event.get("tip") != tip:
                continue
        matched_candidate = True
        archive_ok = event.get("archive_verified") is True or event.get("archive_status") in ACCEPTED_ARCHIVE_STATUSES
        if not archive_ok:
            continue
        if event.get("redaction_review") not in ACCEPTED_REDACTION_REVIEWS:
            continue
        if not has_required_acceptance_proof(event):
            continue
        return True, "branch-reap-accepted"
    if matched_candidate:
        return False, "incomplete-branch-reap-acceptance"
    return False, "missing-branch-reap-acceptance"


def default_ref() -> str:
    """The remote-tracking ref for the default branch (origin/HEAD, else origin/main/master)."""
    r = _git(["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"])
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.strip()
    for ref in ("origin/main", "origin/master"):
        if _git(["show-ref", "--verify", "--quiet", f"refs/remotes/{ref}"]).returncode == 0:
            return ref
    return "origin/main"


def default_name(dref: str) -> str:
    """Bare branch name of the default ref ('origin/main' → 'main')."""
    return dref.split("/", 1)[1] if "/" in dref else dref


def local_branches() -> list[str]:
    r = _git(["for-each-ref", "--format=%(refname:short)", "refs/heads/"])
    return [b for b in r.stdout.splitlines() if b.strip()]


def exact_branch_allowlist(branches: list[str], requested: list[str]) -> tuple[list[str], list[str]]:
    """Select only exact requested names; report typos/missing refs instead of broadening scope."""

    if not requested:
        return branches, []
    available = set(branches)
    wanted = sorted(set(requested))
    return [branch for branch in wanted if branch in available], [
        branch for branch in wanted if branch not in available
    ]


def checked_out_branches() -> set[str]:
    """Every branch currently checked out in ANY worktree — git refuses to delete these."""
    out: set[str] = set()
    r = _git(["worktree", "list", "--porcelain"])
    for line in r.stdout.splitlines():
        if line.startswith("branch refs/heads/"):
            out.add(line[len("branch refs/heads/") :].strip())
    return out


def _merged_at_epoch(iso: str | None) -> float | None:
    """Parse a GitHub ISO8601 mergedAt ('2026-07-02T11:41:23Z') → epoch seconds. None on failure."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def gh_head_states() -> tuple[dict[str, float | None], dict[str, str], dict[str, set[str]], bool]:
    """(merged heads, open head→exact SHA, closed-unmerged head→{exact SHAs}, online).

    Branch names are reusable. An open PR protects a local ref only when that ref still points at
    the PR's exact remote head; a stale same-name ancestor must remain reapable.

    The closed map is a SET of head SHAs per name for the same reason, read the other way: proof 3
    needs "some closed PR preserves THIS exact commit at its pull ref", so a name that was reused
    across several closed PRs must match on the SHA, never on the name. Collapsing it to one SHA
    (last-wins, as merged/open do) would let an unrelated PR's identity vouch for this branch.
    """
    if os.environ.get("LIMEN_OFFLINE") or not shutil.which("gh"):
        return {}, {}, {}, False
    # `gh pr list` returns the N MOST RECENT PRs, so a limit below the repo's PR count silently
    # blinds every proof for older heads — and silence here looks exactly like "no PR exists",
    # i.e. livework. Measured on organvm/limen 2026-08-07 at the former hard-coded 800: of 241
    # local branches that HAD a PR, 132 were invisible (64 CLOSED, 50 OPEN, 18 MERGED). The 50
    # OPEN ones are the sharp edge — those heads were not being protected as in-flight at all.
    # Raised, made tunable, and made LOUD on truncation (charter: no silent caps).
    pr_limit = _int_env("LIMEN_BRANCH_REAP_PR_LIMIT", 3000, minimum=1)
    try:
        res = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--state",
                "all",
                "--json",
                "headRefName,headRefOid,state,mergedAt",
                "--limit",
                str(pr_limit),
            ],
            cwd=str(LIMEN_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            env=_GIT_ENV,
        )
        if res.returncode != 0 or not res.stdout.strip():
            return {}, {}, {}, False
        prs = json.loads(res.stdout)
    except Exception:
        return {}, {}, {}, False
    if len(prs) >= pr_limit:
        # Hit the ceiling → older PRs were almost certainly dropped. This is NOT uniformly fail-safe,
        # which is why it warns instead of passing quietly: a dropped MERGED or CLOSED PR only costs
        # a proof (→ the branch is KEPT as livework), but a dropped OPEN PR removes the in-flight
        # PROTECTION, leaving that head reapable if any other proof happens to hold. Truncation can
        # therefore make the reaper both blinder AND bolder — never let it happen silently.
        print(
            f"[reap-branches] WARN — gh returned {len(prs)} PRs at the --limit ceiling ({pr_limit}); "
            "older PRs are out of view, so some heads may be misreported as live-work AND some open "
            "PRs may have lost their in-flight protection. Raise LIMEN_BRANCH_REAP_PR_LIMIT."
        )
    merged: dict[str, float | None] = {}
    open_: dict[str, str] = {}
    closed: dict[str, set[str]] = {}
    for p in prs:
        head = p.get("headRefName")
        if not head:
            continue
        state = p.get("state")
        if state == "MERGED":
            merged[head] = _merged_at_epoch(p.get("mergedAt"))
        elif state == "OPEN":
            open_[head] = str(p.get("headRefOid") or "")
        elif state == "CLOSED":
            oid = str(p.get("headRefOid") or "")
            if oid:  # an empty OID would match an unreadable local tip — never record it
                closed.setdefault(head, set()).add(oid)
    return merged, open_, closed, True


@dataclass(frozen=True)
class Facts:
    is_ancestor: bool  # proof 1: tip reachable from the default ref
    pr_merged_safe: bool  # proof 2: MERGED per gh AND tip NOT advanced past mergedAt
    pr_merged_raw: bool  # MERGED per gh (regardless of advance) — for the advanced-report case
    pr_open: bool  # an OPEN PR exists for this head
    checked_out: bool  # checked out in some worktree
    protected: bool  # trunk / configured-protected
    # Defaulted so older callers/tests constructing Facts positionally keep working; False is the
    # conservative value, so an un-updated caller can only KEEP a branch, never reap one.
    pr_closed_safe: bool = False  # proof 3: CLOSED-unmerged PR whose headRefOid IS the local tip
    pr_closed_raw: bool = False  # a CLOSED-unmerged PR exists for this head (advance-report case)


@dataclass(frozen=True)
class Verdict:
    action: str  # "reap" | "keep"
    reason: str  # landed-ancestor|landed-pr-merged|inflight|pr-merged-but-advanced|livework|protected|checked-out
    landed: bool  # provably landed AND reapable — the quantity --check asserts is zero


def classify(f: Facts) -> Verdict:
    """PURE predicate (the unit under test). Protective checks first; a surviving-work proof last.

    action="reap" means "the work provably survives deletion" and drives --apply.
    landed=True means "provably landed ON THE DEFAULT BRANCH and reapable now" and drives --check.
    They are NOT the same set: the DECIDED class (proof 3) is reapable but not landed, because its
    work never reached main — it was rejected, and preserved on GitHub's pull ref instead. A branch
    that is landed but checked-out/protected/in-flight is NOT reapable now, so landed=False for it
    (it is legitimately in use; the fixed-point predicate must not fail on it)."""
    if f.protected:
        return Verdict("keep", "protected", False)
    if f.checked_out:
        return Verdict("keep", "checked-out", False)  # in active use — reaped once its worktree frees
    if f.pr_open:
        return Verdict("keep", "inflight", False)  # a live PR — never yank it
    # Two loss-free LANDED proofs. Order only sets the reported reason.
    if f.is_ancestor:
        return Verdict("reap", "landed-ancestor", True)
    if f.pr_merged_safe:
        return Verdict("reap", "landed-pr-merged", True)  # the squash-merge case topology misses
    if f.pr_merged_raw:
        return Verdict("keep", "pr-merged-but-advanced", False)  # unpushed post-merge commits → surface
    # The DECIDED proof, strictly after every landed proof and every merged-PR report: a merged PR
    # must never be re-labelled as a rejection just because a same-named closed PR also exists.
    if f.pr_closed_safe:
        return Verdict("reap", "decided-pr-closed", False)  # rejected by a human; preserved at refs/pull/N/head
    if f.pr_closed_raw:
        return Verdict("keep", "pr-closed-but-advanced", False)  # commits that exist nowhere else → surface
    return Verdict("keep", "livework", False)  # unfulfilled intention — surfaced, never deleted


def gather_facts(
    branch: str,
    dref: str,
    checked_out: set[str],
    merged: dict[str, float | None],
    open_: dict[str, str] | set[str],
    dname: str,
    closed: dict[str, set[str]] | None = None,
) -> Facts:
    """Compute the branch's Facts via git + the precomputed gh maps. Every git/parse failure → the
    conservative value (which makes the branch HARDER to reap, never easier)."""
    ref = f"refs/heads/{branch}"
    is_ancestor = _git(["merge-base", "--is-ancestor", ref, dref]).returncode == 0
    tip_oid_result = _git(["rev-parse", ref])
    tip_oid = tip_oid_result.stdout.strip() if tip_oid_result.returncode == 0 else ""
    if isinstance(open_, set):
        # Compatibility for older callers/tests: name-only evidence is conservative and protects.
        pr_open = branch in open_
    else:
        remote_open_tip = open_.get(branch)
        pr_open = bool(remote_open_tip and tip_oid and remote_open_tip == tip_oid)
    pr_merged_raw = branch in merged
    pr_merged_safe = False
    if pr_merged_raw:
        merged_at = merged.get(branch)
        tip = _git(["log", "-1", "--format=%ct", ref])
        try:
            tip_ct = int(tip.stdout.strip()) if tip.returncode == 0 else None
        except ValueError:
            tip_ct = None
        # Reap only if we can prove the tip is NOT newer than the merge. Unknown merge time or tip
        # time → fail safe (treat as advanced → keep). A clean merge has tip_ct <= mergedAt.
        pr_merged_safe = bool(merged_at is not None and tip_ct is not None and tip_ct <= merged_at + ADVANCED_BUFFER_S)
    # Proof 3. Unreadable tip → tip_oid == "" → no match, so a git failure KEEPS the branch.
    closed_oids = (closed or {}).get(branch, set())
    pr_closed_raw = bool(closed_oids)
    pr_closed_safe = bool(tip_oid and tip_oid in closed_oids)
    return Facts(
        is_ancestor=is_ancestor,
        pr_merged_safe=pr_merged_safe,
        pr_merged_raw=pr_merged_raw,
        pr_open=pr_open,
        checked_out=branch in checked_out,
        protected=(branch == dname or branch in BASE_PROTECT or branch in EXTRA_PROTECT),
        pr_closed_safe=pr_closed_safe,
        pr_closed_raw=pr_closed_raw,
    )


def _landed_age_s(branch: str, merged: dict[str, float | None], now: float) -> float:
    """Seconds since the branch's work LANDED (how long it has been spent).

    Best signal: the PR's mergedAt (gh). Fallback: the tip's commit time — the tip predates the
    landing, so the fallback can only OVERESTIMATE the age; a young branch with an old tip fails
    toward RED (surfaced), never toward hidden. Unknown both ways → +inf (stale)."""
    merged_at = merged.get(branch)
    if merged_at is not None:
        return now - merged_at
    r = _git(["log", "-1", "--format=%ct", f"refs/heads/{branch}"])
    try:
        tip_ct = int(r.stdout.strip()) if r.returncode == 0 else None
    except ValueError:
        tip_ct = None
    return float("inf") if tip_ct is None else now - tip_ct


def _lingering(
    reap_list: list[tuple[str, str]], merged: dict[str, float | None], now: float, grace_s: float
) -> list[tuple[str, str]]:
    """--check's aging filter: a landed branch LINGERS only once older than the grace window."""
    return [(b, why) for b, why in reap_list if _landed_age_s(b, merged, now) > grace_s]


def _branch_tip_desc(branch: str) -> str:
    """A STABLE one-line descriptor of the branch tip (idempotent — no volatile timestamp)."""
    r = _git(["log", "-1", "--format=%h %s", f"refs/heads/{branch}"])
    return r.stdout.strip() if r.returncode == 0 else "(unreadable)"


def write_ledger(
    livework: list[str],
    advanced: list[str],
    inflight_n: int,
    closed_advanced: list[str] | None = None,
    decided: list[str] | None = None,
) -> None:
    """Regenerate the durable, git-tracked home for KEPT-BUT-UNDECIDED branches. Deterministic
    (sorted, stable per-branch descriptors, no volatile clock) so re-runs produce no diff unless a
    branch actually changed — an idempotent fixed point, not churn."""
    closed_advanced = closed_advanced or []
    decided = decided or []
    lines = [
        "# Branch hygiene — the unfinished-intention ledger",
        "",
        "> Auto-generated by [`scripts/reap-branches.py`](../scripts/reap-branches.py). Do not hand-edit;",
        "> re-run `python3 scripts/reap-branches.py --apply` to regenerate.",
        "",
        "Spent branches (work landed on `main`) are receipt-gated reap candidates. The branches below",
        "carry real work **not** on `main` and **not** preserved on a GitHub pull ref — never-pushed, or",
        "advanced past the merge/close its PR recorded. They are *unfulfilled intentions* (memory:",
        "empty-branch-is-a-todo), so they are **kept, never auto-deleted** — this is their git-tracked",
        "location instead of hanging invisibly.",
        "Resolve each: open a PR and land it, or delete the branch by hand if the intention is abandoned.",
        "",
    ]
    if decided:
        lines.append(f"## Decided — closed PR, work preserved ({len(decided)}) — reapable, awaiting acceptance")
        lines.append("")
        lines.append("A human CLOSED these PRs unmerged and the local tip is still that PR's exact head, so")
        lines.append("GitHub preserves the commit at `refs/pull/N/head` — `git fetch origin pull/N/head`")
        lines.append("recovers it. Deleting the local ref loses nothing. These are NOT unfulfilled intentions:")
        lines.append("the intention was already decided against. They are reap candidates gated on")
        lines.append("`docs/branch-reap-acceptance.jsonl`, not on anyone re-deciding them.")
        lines.append("")
        for b in sorted(decided):
            lines.append(f"- `{b}` — {_branch_tip_desc(b)}")
        lines.append("")
    if closed_advanced:
        lines.append(f"## Closed-but-advanced ({len(closed_advanced)}) — has commits the closed PR never saw")
        lines.append("")
        lines.append("These heads had a CLOSED-unmerged PR but the local tip DIFFERS from that PR's head, so")
        lines.append("the extra commits exist **nowhere but this machine**. Never auto-deleted.")
        lines.append("Push them as a fresh PR, or delete by hand if the extra commits are throwaway.")
        lines.append("")
        for b in sorted(closed_advanced):
            lines.append(f"- `{b}` — {_branch_tip_desc(b)}")
        lines.append("")
    if advanced:
        lines.append(f"## Merged-but-advanced ({len(advanced)}) — has commits ADDED after the PR merged")
        lines.append("")
        lines.append("These heads had a MERGED PR but the local branch has newer commits not on `main`.")
        lines.append("Push them as a follow-up PR, or delete if the extra commits are throwaway.")
        lines.append("")
        for b in sorted(advanced):
            lines.append(f"- `{b}` — {_branch_tip_desc(b)}")
        lines.append("")
    if livework:
        lines.append(f"## Live-work branches ({len(livework)}) — decide each")
        lines.append("")
        for b in sorted(livework):
            lines.append(f"- `{b}` — {_branch_tip_desc(b)}")
    else:
        lines.append("## Live-work branches (0)")
        lines.append("")
        lines.append("None — every local branch is landed (reaped), in-flight (open PR), or a trunk.")
    lines.append("")
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="Reap provably-landed local branches (loss-free).")
    ap.add_argument("--apply", action="store_true", help="actually delete landed branches (default: dry-run)")
    ap.add_argument("--check", action="store_true", help="exit 1 if any provably-landed branch lingers (read-only)")
    ap.add_argument("--force", action="store_true", help="ignore the self-throttle")
    ap.add_argument("--max", type=int, default=_int_env("LIMEN_BRANCH_REAP_MAX", 100, minimum=1))
    ap.add_argument(
        "--branch",
        action="append",
        default=[],
        help="limit inspection/reaping to this exact local branch; repeat for an allowlist",
    )
    args = ap.parse_args()

    every_min = _float_env("LIMEN_BRANCH_REAP_EVERY_MIN", 30.0, minimum=0.0)

    # Refresh the default ref so a just-merged branch is judged against current main (best-effort).
    if not args.check:
        _git(["fetch", "--prune", "--quiet", "origin", "main"], timeout=90)
    dref = default_ref()
    dname = default_name(dref)
    checked = checked_out_branches()
    merged, open_, closed, online = gh_head_states()
    branches, missing_targets = exact_branch_allowlist(local_branches(), args.branch)
    if missing_targets:
        print(
            "[reap-branches] HOLD — exact target(s) not found; no branches were reaped: " + ", ".join(missing_targets)
        )
        return 2

    # Self-throttle only applies to a real --apply beat (a --check gate always runs).
    if args.apply and not args.branch and not args.force and not args.check and MARKER.exists():
        if (time.time() - MARKER.stat().st_mtime) / 60.0 < every_min:
            print(f"[reap-branches] ran < {every_min:g}min ago — skip (--force to override)")
            return 0

    reap: list[tuple[str, str]] = []
    landed_reap: list[tuple[str, str]] = []  # the --check subset: reapable AND landed on the default ref
    inflight: list[str] = []
    livework: list[str] = []
    advanced: list[str] = []
    closed_advanced: list[str] = []
    decided: list[str] = []
    kept_reasons: dict[str, int] = {}
    for b in branches:
        f = gather_facts(b, dref, checked, merged, open_, dname, closed)
        v = classify(f)
        if v.action == "reap":
            reap.append((b, v.reason))
            if v.landed:
                landed_reap.append((b, v.reason))
            else:
                decided.append(b)
        else:
            kept_reasons[v.reason] = kept_reasons.get(v.reason, 0) + 1
            if v.reason == "inflight":
                inflight.append(b)
            elif v.reason == "pr-merged-but-advanced":
                advanced.append(b)
            elif v.reason == "pr-closed-but-advanced":
                closed_advanced.append(b)
            elif v.reason == "livework":
                livework.append(b)

    # ── --check: pure predicate. Exit 1 iff any landed branch LINGERS past the digestion grace
    # window (the fixed point). A branch spent for seconds is the beat mid-digestion, not hanging
    # debt — without the grace a continuously-merging fleet reddens every closeout (2026-07-09:
    # 176 branches accepted+reaped and fresh ones landed during the apply itself). --apply
    # eligibility is deliberately NOT graced: an accepted young branch reaps immediately.
    if args.check:
        grace_s = _float_env("LIMEN_BRANCH_REAP_GRACE_MIN", 60.0, minimum=0.0) * 60.0
        # landed_reap, NOT reap: the DECIDED class is reapable but never landed, so it is reported
        # (below) rather than asserted to zero. Gating the closeout on it would make the gate red
        # until an operator widens deletion authority — an unclearable red, which is how a gate
        # stops being read at all.
        lingering = _lingering(landed_reap, merged, time.time(), grace_s)
        young = len(landed_reap) - len(lingering)
        young_note = f" ({young} younger than the grace window — digesting, not lingering)" if young else ""
        if lingering:
            # The advice must derive from ledger state, not a static worst case: a branch whose
            # class is already covered (standing grant or per-branch event) needs only --apply —
            # prescribing "write the acceptance JSONL" for it misfiles authorized routine work as
            # an operator gate (2026-08-05: a closeout filed a standing-grant-covered reap as a
            # human-gated lever off this message).
            acceptance_events = load_branch_reap_acceptance()
            authorized = {b for b, why in lingering if branch_reap_accepted(b, why, acceptance_events)[0]}
            if len(authorized) == len(lingering):
                advice = (
                    "every one already authorized on docs/branch-reap-acceptance.jsonl — "
                    "run scripts/reap-branches.py --apply; no new ledger event needed"
                )
            elif authorized:
                advice = (
                    f"{len(authorized)} already authorized — scripts/reap-branches.py --apply reaps those; "
                    "for the rest review docs/branch-reap-acceptance.md and write "
                    "docs/branch-reap-acceptance.jsonl with archive + redaction proof first"
                )
            else:
                advice = (
                    "review docs/branch-reap-acceptance.md, write docs/branch-reap-acceptance.jsonl "
                    "with archive + redaction proof, then scripts/reap-branches.py --apply"
                )
            print(f"[reap-branches] FAIL — {len(lingering)} landed branch(es) still lingering{young_note} ({advice}):")
            for b, why in sorted(lingering)[:20]:
                mark = "authorized" if b in authorized else "needs-acceptance"
                print(f"  landed  {b}  ({why}, {mark})")
            if len(lingering) > 20:
                print(f"  … and {len(lingering) - 20} more (see scripts/reap-branches.py dry-run)")
            return 1
        note = "" if online else " (offline — gh proof-2/3 skipped; ancestor-only)"
        decided_note = (
            f" {len(decided)} decided (closed-PR, preserved at refs/pull/N/head) awaiting acceptance."
            if decided
            else ""
        )
        print(
            f"[reap-branches] ok — no provably-landed branch lingers{young_note}{note}. "
            f"{len(inflight)} in-flight, {len(advanced)} merged-advanced, "
            f"{len(closed_advanced)} closed-advanced, {len(livework)} live-work kept.{decided_note}"
        )
        return 0

    # ── dry-run / --apply ────────────────────────────────────────────────────────────────────────
    mode = "APPLY" if args.apply else "dry-run"
    online_note = "online" if online else "offline(gh proof-2/3 skipped)"
    print(
        f"[reap-branches] {mode}; default={dref}; {online_note}; "
        f"{len(reap)} reapable ({len(landed_reap)} landed, {len(decided)} decided), "
        f"{len(inflight)} in-flight, {len(advanced)} merged-advanced, "
        f"{len(closed_advanced)} closed-advanced, {len(livework)} live-work."
    )

    done = 0
    reaped_names: list[str] = []
    branch_reap_acceptance = load_branch_reap_acceptance()
    for b, why in reap:
        if done >= args.max:
            print(f"[reap-branches] hit --max={args.max}; '{b}' and any remainder LEFT for next run")
            break
        print(f"  {'REAP' if args.apply else 'WOULD reap'}: {b}  ({why})")
        if args.apply:
            accepted, accept_reason = branch_reap_accepted(b, why, branch_reap_acceptance)
            if not accepted:
                print(f"    KEEP {b}: {accept_reason}")
                kept_reasons[accept_reason] = kept_reasons.get(accept_reason, 0) + 1
                continue
            r = _git(["branch", "-D", b])
            if r.returncode != 0:
                print(f"    FAIL delete {b}: {r.stderr.strip()[:120]}")
                continue
            reaped_names.append(b)
        done += 1

    if args.apply:
        try:
            targeted = bool(args.branch)
            LOG.parent.mkdir(parents=True, exist_ok=True)
            with LOG.open("a") as fh:
                fh.write(
                    json.dumps(
                        {
                            "ts": time.time(),
                            "scope": "targeted" if targeted else "full",
                            "targets": sorted(set(args.branch)),
                            "default": dref,
                            "online": online,
                            "reaped": reaped_names,
                            "inflight": sorted(inflight),
                            "advanced": sorted(advanced),
                            "closed_advanced": sorted(closed_advanced),
                            "decided": sorted(decided),
                            "livework": sorted(livework),
                            "kept_reasons": kept_reasons,
                        }
                    )
                    + "\n"
                )
            if not targeted:
                MARKER.parent.mkdir(parents=True, exist_ok=True)
                MARKER.write_text(str(time.time()))
                STATE.write_text(
                    json.dumps(
                        {
                            "ts": time.time(),
                            "default": dref,
                            "online": online,
                            "reaped_this_run": reaped_names,
                            "inflight": sorted(inflight),
                            "advanced": sorted(advanced),
                            "closed_advanced": sorted(closed_advanced),
                            "decided": sorted(decided),
                            "livework": sorted(livework),
                        },
                        indent=2,
                    )
                )
                write_ledger(livework, advanced, len(inflight), closed_advanced, decided)
        except Exception as e:  # observability must never break the beat
            print(f"[reap-branches] note: stamp/ledger write skipped ({str(e)[:80]})")

    kr = ", ".join(f"{k}={n}" for k, n in sorted(kept_reasons.items())) or "none"
    print(
        f"[reap-branches] {'reaped' if args.apply else 'would reap'} "
        f"{len(reaped_names) if args.apply else done} branch(es); kept {sum(kept_reasons.values())} ({kr})."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
